"""BS-STRUCT.1C backfill/audit for BibleStudyMeeting audience-scope rows.

This command scans existing ``BibleStudyMeeting`` rows and reports which ones
can be safely converted from their legacy ``small_group`` FK onto an explicit
``BibleStudyMeetingAudienceScope`` row, following the SE-AS.6B/6C dry-run-first
pattern already used by ``backfill_service_event_audience_scopes`` and the
BS-STRUCT.1C contract in
``docs/BIBLE_STUDY_STRUCTURE_NATIVE_MIGRATION_PLAN.md`` (Section 6).

It runs as a read-only **dry-run by default**. With the explicit ``--apply``
flag it additionally creates one ``BibleStudyMeetingAudienceScope`` row per
safe, valid, no-existing-audience meeting, and backfills ``anchor_unit`` only
when it is currently null. Dry-run and apply use the exact same classification
pass, so apply never creates a row the dry-run would not have reported as
``would_create``.

In **both** modes it never:

- mutates the legacy ``BibleStudyMeeting.small_group`` FK (the reported
  ``legacy_small_group_mutated`` counter is ``0`` by construction);
- changes any runtime visibility / generation / landing-Today / role-worship
  picker behavior (audience rows stay inert in this slice — the reported
  ``runtime_switched`` flag is always ``false``);
- touches ``ChurchStructureUnit``, ``ChurchStructureMembership``, ``Profile``,
  or ``SmallGroup`` rows; the proposed unit is derived only from the meeting's
  own ``small_group.church_structure_unit`` mapping.

Meetings that already have audience rows are skipped in both modes, so apply is
idempotent: a second dry-run after apply reports them as
``skipped_existing_audience`` with zero ``would_create``.

Parity (conservative, structural).
Current Bible Study meeting runtime visibility is already membership-core
(CS-CORE.2C-B) but keyed off ``meeting.small_group`` →
``small_group.church_structure_unit`` and only matches when that mapped unit is
``UNIT_SMALL_GROUP`` (see ``studies.visibility``). The proposed audience unit
for a safe meeting is exactly that same mapped small-group unit, so the
post-row audience unit is structurally identical to the unit the current
runtime already matches against. The command confirms this structural
equivalence per ``would_create`` meeting (``parity_structural_match``) and skips
any candidate whose proposed unit would not match the runtime's small-group
unit. A full per-user parity matrix is intentionally **not** rebuilt here: that
comparison already has a dedicated command,
``audit_bible_study_membership_readiness``. Keeping 1C's classification strict
(active, ``UNIT_SMALL_GROUP``, no existing rows, validation-clean) is what makes
the structural parity sufficient for this additive backfill.
"""

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounts.models import ChurchStructureUnit
from studies.models import BibleStudyMeeting, BibleStudyMeetingAudienceScope
from studies.visibility import get_small_group_structure_unit

# Ordered, stable list of the counters the command reports. New scopes append
# here so output stays deterministic.
_STAT_KEYS = (
    "meetings_checked",
    "skipped_existing_audience",
    "would_create",
    "created",
    "missing_small_group",
    "unmapped_small_group",
    "inactive_structure_unit",
    "wrong_unit_type",
    "validation_error",
    "parity_structural_match",
    "anchor_unit_backfilled",
    "legacy_small_group_mutated",
)

# Buckets that represent a meeting the backfill could not safely convert. Used
# by the optional ``--fail-on-issues`` flag. ``skipped_existing_audience`` is
# intentionally excluded: an already-converted meeting is not an issue.
_ISSUE_KEYS = (
    "missing_small_group",
    "unmapped_small_group",
    "inactive_structure_unit",
    "wrong_unit_type",
    "validation_error",
)


def _new_stats():
    return {key: 0 for key in _STAT_KEYS}


def _unit_label(unit):
    if unit is None:
        return ""
    label = f"#{unit.id} {unit.code}"
    if getattr(unit, "name", ""):
        label = f"{label} {unit.name}"
    return label


def _group_label(group):
    if group is None:
        return ""
    return f"#{group.id} {group.name}"


def _format_meeting_line(meeting, category, reason, proposed_unit=None):
    parts = [
        f"meeting #{meeting.id}",
        f"small_group: {_group_label(meeting.small_group) or '(none)'}",
        f"anchor_unit: {_unit_label(meeting.anchor_unit) or '(none)'}",
        f"category: {category}",
    ]
    proposed_label = _unit_label(proposed_unit)
    if proposed_label:
        parts.append(f"proposed unit: {proposed_label}")
    parts.append(f"reason: {reason}")
    return "  " + " | ".join(parts)


def _classify_meeting(meeting):
    """Return ``(category, reason, bucket, proposed_unit)`` for one meeting.

    Pure inspection; never writes anything. The single safe outcome is
    ``would_create`` with a concrete proposed ``UNIT_SMALL_GROUP`` unit; every
    other outcome is a skip bucket with ``proposed_unit`` ``None``.
    """
    if meeting.audience_scope_links.exists():
        return (
            "skipped_existing_audience",
            "already has audience rows",
            "skipped_existing_audience",
            None,
        )

    small_group = meeting.small_group
    if small_group is None:
        return (
            "missing_small_group",
            "meeting has no legacy small_group; audience cannot be inferred",
            "missing_small_group",
            None,
        )

    unit = get_small_group_structure_unit(small_group)
    if unit is None:
        return (
            "unmapped_small_group",
            "small_group has no church_structure_unit mapping",
            "unmapped_small_group",
            None,
        )

    if not unit.is_active:
        return (
            "inactive_structure_unit",
            "mapped small_group unit is inactive",
            "inactive_structure_unit",
            None,
        )

    if unit.unit_type != ChurchStructureUnit.UNIT_SMALL_GROUP:
        return (
            "wrong_unit_type",
            f"mapped unit is {unit.unit_type!r}, not {ChurchStructureUnit.UNIT_SMALL_GROUP!r}",
            "wrong_unit_type",
            None,
        )

    # Conservative structural parity: the proposed unit must be the same unit
    # the current small-group runtime path already matches against. Because both
    # are derived from ``small_group.church_structure_unit`` and gated on
    # ``UNIT_SMALL_GROUP``, this holds by construction for the safe case; the
    # check exists so any future divergence fails closed instead of silently
    # creating a non-parity row.
    runtime_unit = get_small_group_structure_unit(small_group)
    if (
        runtime_unit is None
        or runtime_unit.id != unit.id
        or runtime_unit.unit_type != ChurchStructureUnit.UNIT_SMALL_GROUP
    ):
        return (
            "validation_error",
            "proposed unit does not match current runtime small-group unit",
            "validation_error",
            None,
        )

    # Pre-validate the row exactly as apply will create it, so dry-run and apply
    # agree and any conflict surfaces as ``validation_error`` without writing.
    candidate = BibleStudyMeetingAudienceScope(meeting=meeting, unit=unit)
    try:
        candidate.full_clean()
    except ValidationError as exc:
        return (
            "validation_error",
            f"audience scope validation failed: {exc.messages}",
            "validation_error",
            None,
        )

    return (
        "would_create",
        "safe: maps to active UNIT_SMALL_GROUP unit with no existing audience rows",
        "would_create",
        unit,
    )


def _scan_meetings(*, limit=None, meeting_id=None):
    """Single read-only decision pass over BibleStudyMeeting rows.

    Returns ``(stats, meeting_lines, plan)`` where ``plan`` is a deterministic
    list of ``(meeting, proposed_unit)`` pairs for safe ``would_create``
    meetings. This is the one shared decision path used by both the dry-run
    audit and the ``--apply`` backfill, so apply can never act on a meeting the
    dry-run would not have reported. This function creates, edits, or deletes
    nothing.
    """
    stats = _new_stats()
    meeting_lines = []
    plan = []

    meetings = (
        BibleStudyMeeting.objects.all()
        .select_related(
            "small_group",
            "small_group__church_structure_unit",
            "anchor_unit",
        )
        .order_by("id")
    )
    if meeting_id is not None:
        meetings = meetings.filter(id=meeting_id)
    if limit is not None:
        meetings = meetings[:limit]

    for meeting in meetings:
        stats["meetings_checked"] += 1
        category, reason, bucket, proposed_unit = _classify_meeting(meeting)
        stats[bucket] += 1
        if category == "would_create":
            stats["parity_structural_match"] += 1
            plan.append((meeting, proposed_unit))
        meeting_lines.append(
            _format_meeting_line(meeting, category, reason, proposed_unit)
        )

    return stats, meeting_lines, plan


def run_audit(*, limit=None, meeting_id=None):
    """Scan BibleStudyMeeting rows read-only and return ``(stats, lines)``.

    Nothing is created, edited, or deleted.
    """
    stats, meeting_lines, _plan = _scan_meetings(limit=limit, meeting_id=meeting_id)
    return stats, meeting_lines


def apply_backfill(*, limit=None, meeting_id=None):
    """Create audience rows for safe ``would_create`` meetings.

    Returns ``(stats, meeting_lines)``. Runs inside a single atomic
    transaction: if anything unexpected happens while creating rows the whole
    apply rolls back rather than leaving a partial backfill. Only
    ``BibleStudyMeetingAudienceScope`` rows are created and ``anchor_unit`` is
    set when (and only when) it is currently null; ``small_group`` and every
    other legacy/runtime field is left untouched. Idempotent: meetings that
    already have audience rows are skipped by the shared scan, so a second run
    creates ``0`` additional rows.
    """
    with transaction.atomic():
        stats, meeting_lines, plan = _scan_meetings(limit=limit, meeting_id=meeting_id)
        for meeting, proposed_unit in plan:
            _obj, was_created = BibleStudyMeetingAudienceScope.objects.get_or_create(
                meeting=meeting,
                unit=proposed_unit,
            )
            if was_created:
                stats["created"] += 1

            # Backfill anchor_unit only when null; never overwrite an existing
            # anchor and never touch small_group. ``update_fields`` keeps the
            # UPDATE scoped to anchor_unit so the legacy group column is never
            # rewritten.
            if meeting.anchor_unit_id is None:
                meeting.anchor_unit = proposed_unit
                meeting.save(update_fields=["anchor_unit", "updated_at"])
                stats["anchor_unit_backfilled"] += 1

    return stats, meeting_lines


class Command(BaseCommand):
    help = (
        "Audit (and optionally backfill) which BibleStudyMeeting rows can be "
        "safely converted from their legacy small_group onto a "
        "BibleStudyMeetingAudienceScope row (BS-STRUCT.1C). Dry-run by default: "
        "creates, edits, and deletes nothing. With --apply it creates one "
        "audience row per safe meeting and backfills a null anchor_unit only. "
        "It never mutates small_group and never changes runtime visibility, "
        "generation, Today/landing, or picker behavior."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help=(
                "Actually create BibleStudyMeetingAudienceScope rows for safe "
                "meetings and backfill a null anchor_unit. Without this flag the "
                "command is a read-only dry-run and changes nothing. Apply never "
                "mutates small_group, skips meetings that already have audience "
                "rows, and is idempotent."
            ),
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Process at most N meetings (ordered by id).",
        )
        parser.add_argument(
            "--meeting-id",
            type=int,
            default=None,
            help="Process only the meeting with this id.",
        )
        parser.add_argument(
            "--verbose",
            "--verbose-events",
            action="store_true",
            dest="verbose_events",
            help=(
                "Also print a per-meeting decision line (meeting id, small_group, "
                "decision, and reason). Independent of Django -v verbosity."
            ),
        )
        parser.add_argument(
            "--fail-on-issues",
            action="store_true",
            help=(
                "Exit with an error when any issue bucket is nonzero "
                "(missing_small_group, unmapped_small_group, "
                "inactive_structure_unit, wrong_unit_type, validation_error). "
                "Still never writes in dry-run."
            ),
        )

    def handle(self, *args, **options):
        if options["limit"] is not None and options["limit"] < 0:
            raise CommandError("--limit must be zero or greater.")

        apply_mode = options["apply"]
        limit = options["limit"]
        meeting_id = options["meeting_id"]

        if apply_mode:
            stats, meeting_lines = apply_backfill(limit=limit, meeting_id=meeting_id)
        else:
            stats, meeting_lines = run_audit(limit=limit, meeting_id=meeting_id)

        self._print_report(
            stats, meeting_lines, options["verbose_events"], apply_mode
        )

        if options["fail_on_issues"]:
            issues = [
                f"{key}={stats[key]}" for key in _ISSUE_KEYS if stats[key]
            ]
            if issues:
                raise CommandError(
                    "BibleStudyMeeting audience backfill issues detected "
                    "(--fail-on-issues): " + ", ".join(issues)
                )

    def _print_report(self, stats, meeting_lines, verbose_events, apply_mode):
        write = self.stdout.write

        if apply_mode:
            write("BibleStudyMeeting audience-scope backfill (BS-STRUCT.1C, APPLY mode)")
        else:
            write(
                "BibleStudyMeeting audience-scope backfill audit "
                "(BS-STRUCT.1C, dry-run only)"
            )
        write("=" * 70)
        write(f"meetings_checked            : {stats['meetings_checked']}")
        write(f"skipped_existing_audience   : {stats['skipped_existing_audience']}")
        write(f"would_create                : {stats['would_create']}")
        write(f"created                     : {stats['created']}")
        write(f"missing_small_group         : {stats['missing_small_group']}")
        write(f"unmapped_small_group        : {stats['unmapped_small_group']}")
        write(f"inactive_structure_unit     : {stats['inactive_structure_unit']}")
        write(f"wrong_unit_type             : {stats['wrong_unit_type']}")
        write(f"validation_error            : {stats['validation_error']}")
        write(f"parity_structural_match     : {stats['parity_structural_match']}")
        write(f"anchor_unit_backfilled      : {stats['anchor_unit_backfilled']}")
        write(f"legacy_small_group_mutated  : {stats['legacy_small_group_mutated']}")
        write("runtime_switched            : false")
        write("")
        if apply_mode:
            write(
                f"Apply mode: created {stats['created']} "
                "BibleStudyMeetingAudienceScope row(s) and backfilled "
                f"{stats['anchor_unit_backfilled']} null anchor_unit value(s); "
                "small_group was not mutated and no runtime behavior changed."
            )
        else:
            write(
                "Audit only: no BibleStudyMeetingAudienceScope rows created, no "
                "anchor_unit set, small_group not mutated, and no runtime "
                "behavior changed."
            )

        if verbose_events:
            write("")
            write("per-meeting decisions:")
            if meeting_lines:
                for line in meeting_lines:
                    write(line)
            else:
                write("  (no meetings scanned)")
