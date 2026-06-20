"""Guarded cleanup for existing legacy ``PrayerRequest.small_group_at_post`` mirrors.

PRAYER-MIRROR.1B cleanup tooling. PRAYER-MIRROR.1A already stopped normal
app-level writes to the legacy ``small_group_at_post`` mirror: the prayer group
create/edit path no longer stamps or re-stamps it, new group prayers leave it
null, and ordinary edits preserve any existing stored value without
re-stamping. Ordinary group-prayer visibility keys off
``PrayerRequest.structure_unit_at_post`` plus the viewer's single active primary
``ChurchStructureMembership`` (see ``prayers.structure_visibility``). The legacy
mirror is never rendered in a prayer template; it survives only as admin
list/search context and as the stored FK that keeps the legacy ``SmallGroup``
table pinned.

This command clears the *existing* stored ``small_group_at_post`` legacy mirror
values only when doing so is provably safe -- i.e. it cannot change prayer
visibility, display, or any runtime behavior. The schema-prep audit
(``audit_legacy_structure_schema_retirement_readiness``) counts every row with a
non-null ``small_group_at_post`` as a ``blocked_by_data`` blocker while rows
remain populated, and reclassifies the candidate to
``blocked_by_display_or_admin`` once the data is cleared. Hidden / deleted rows
are in scope here when the same safety checks pass, because the stored FK pins
the legacy table regardless of moderation state and clearing it changes no
display (no prayer template renders the legacy mirror).

Eligibility categories:

Category 1 -- group-visibility rows with a valid matching structure snapshot
    Candidate: ``small_group_at_post`` is not null and ``visibility == group``.
    Eligible only if ``structure_unit_at_post`` is not null, is active, is a
    ``UNIT_SMALL_GROUP`` unit, the legacy ``small_group_at_post`` maps to a
    ``ChurchStructureUnit``, and that mapped unit *is* the same
    ``structure_unit_at_post``. Group visibility already runs entirely off the
    structure snapshot, so clearing the matching legacy mirror cannot change it.
    Decision: ``eligible_clear_group_matching_snapshot``.

Category 2 -- non-group rows that already carry a valid matching structure snapshot
    Candidate: ``small_group_at_post`` is not null and ``visibility != group``.
    Eligible only under the *same* full matching checks as Category 1
    (structure_unit_at_post non-null, active, small-group type, mapped legacy
    unit equals the snapshot). No prayer template renders the legacy mirror, and
    the structure snapshot already carries the structure identity, so clearing
    the matching legacy mirror cannot change any display. Decision:
    ``eligible_clear_nongroup_matching_snapshot``.

Conservative skip -- non-group rows with no structure snapshot
    A non-group row whose ``small_group_at_post`` is set but
    ``structure_unit_at_post`` is null is skipped
    (``skipped_display_context_uncertain``). It is left for a later, separate
    display-mirror migration rather than cleared here.

Contract (mirrors the ServiceEvent / Bible Study / reflection guarded cleanup
pattern):

- **Dry-run is the default.** It writes nothing unless apply is requested.
- Apply requires **both** ``--apply`` and
  ``--confirm-prayer-small-group-mirror-cleanup``.
- It performs no schema / model migration and no runtime source-of-truth switch.
- The only field it ever mutates is ``PrayerRequest.small_group_at_post`` (set to
  ``None``). It never touches ``title``, ``body``, ``answer_note``,
  ``visibility``, ``status``, ``structure_unit_at_post``, ``user``,
  ``is_hidden`` / ``is_deleted``, Profile, ChurchStructureMembership / Unit,
  SmallGroup, District, MinistryContext, ServiceEvent, Bible Study, reflection,
  role, ministry / serving / team-assignment, audience, permission, or
  reading-progress data.
- It never prints prayer title / body / answer-note / comment / report free text.
- It is idempotent: a second apply clears zero additional rows.
"""

from dataclasses import dataclass

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounts.models import ChurchStructureUnit
from prayers.models import PrayerRequest


# Counter keys, in display order.
_STAT_KEYS = (
    "prayers_checked",
    "prayers_with_small_group_mirror",
    "prayers_without_small_group_mirror",
    "group_prayers_with_mirror",
    "nongroup_prayers_with_mirror",
    "eligible_to_clear",
    "would_clear_count",
    "cleared_count",
    "skipped_missing_structure_snapshot",
    "skipped_legacy_group_unmapped",
    "skipped_structure_snapshot_inactive",
    "skipped_structure_snapshot_wrong_type",
    "skipped_mapping_mismatch",
    "skipped_display_context_uncertain",
    "remaining_mirror_references_after_operation",
)


@dataclass(frozen=True)
class CleanupPlan:
    prayer_id: int


@dataclass(frozen=True)
class DecisionLine:
    prayer_id: int
    username: str
    visibility: str
    small_group: str
    mapped_unit: str
    structure_unit: str
    is_hidden: bool
    is_deleted: bool
    category: str
    reason: str


def _new_stats():
    return {key: 0 for key in _STAT_KEYS}


def _group_label(group):
    if group is None:
        return "(none)"
    return f"#{group.id} {group.name}"


def _unit_label(unit):
    if unit is None:
        return "(none)"
    return f"#{unit.id} {unit.code} ({unit.unit_type}) active={unit.is_active}"


def _decision_line(prayer, *, mapped_unit, category, reason):
    return DecisionLine(
        prayer_id=prayer.id,
        username=prayer.user.get_username() if prayer.user_id else "(none)",
        visibility=prayer.visibility,
        small_group=_group_label(prayer.small_group_at_post),
        mapped_unit=_unit_label(mapped_unit),
        structure_unit=_unit_label(prayer.structure_unit_at_post),
        is_hidden=prayer.is_hidden,
        is_deleted=prayer.is_deleted,
        category=category,
        reason=reason,
    )


def _format_decision_line(line):
    return (
        f"  prayer #{line.prayer_id} | user: {line.username} "
        f"| visibility: {line.visibility} "
        f"| small_group_at_post: {line.small_group} "
        f"| mapped_unit: {line.mapped_unit} "
        f"| structure_unit_at_post: {line.structure_unit} "
        f"| is_hidden: {line.is_hidden} | is_deleted: {line.is_deleted} "
        f"| decision: {line.category} | reason: {line.reason}"
    )


def _mirror_queryset(*, lock=False):
    rows = (
        PrayerRequest.objects.filter(small_group_at_post__isnull=False)
        .select_related(
            "user",
            "small_group_at_post",
            "small_group_at_post__church_structure_unit",
            "structure_unit_at_post",
        )
        .order_by("id")
    )
    if lock:
        rows = rows.select_for_update()
    return rows


def _classify_matching_snapshot(prayer, stats, *, eligible_category, eligible_reason):
    """Shared full-matching-snapshot check for group and non-group rows."""
    snapshot = prayer.structure_unit_at_post

    if not snapshot.is_active:
        stats["skipped_structure_snapshot_inactive"] += 1
        return (
            _decision_line(
                prayer,
                mapped_unit=None,
                category="blocked",
                reason="structure_unit_at_post is inactive",
            ),
            None,
        )
    if snapshot.unit_type != ChurchStructureUnit.UNIT_SMALL_GROUP:
        stats["skipped_structure_snapshot_wrong_type"] += 1
        return (
            _decision_line(
                prayer,
                mapped_unit=None,
                category="blocked",
                reason="structure_unit_at_post is not a small_group unit",
            ),
            None,
        )

    mapped_unit = prayer.small_group_at_post.church_structure_unit
    if mapped_unit is None:
        stats["skipped_legacy_group_unmapped"] += 1
        return (
            _decision_line(
                prayer,
                mapped_unit=None,
                category="blocked",
                reason="legacy small_group_at_post has no church_structure_unit mapping",
            ),
            None,
        )
    if mapped_unit.id != snapshot.id:
        stats["skipped_mapping_mismatch"] += 1
        return (
            _decision_line(
                prayer,
                mapped_unit=mapped_unit,
                category="blocked",
                reason=(
                    "legacy small_group_at_post maps to a unit other than "
                    "structure_unit_at_post"
                ),
            ),
            None,
        )

    stats["eligible_to_clear"] += 1
    return (
        _decision_line(
            prayer,
            mapped_unit=mapped_unit,
            category=eligible_category,
            reason=eligible_reason,
        ),
        CleanupPlan(prayer_id=prayer.id),
    )


def _classify_group(prayer, stats):
    """Group-visibility mirror row (Category 1)."""
    stats["group_prayers_with_mirror"] += 1
    if prayer.structure_unit_at_post is None:
        stats["skipped_missing_structure_snapshot"] += 1
        return (
            _decision_line(
                prayer,
                mapped_unit=None,
                category="blocked",
                reason="group row has no structure_unit_at_post snapshot",
            ),
            None,
        )
    return _classify_matching_snapshot(
        prayer,
        stats,
        eligible_category="eligible_clear_group_matching_snapshot",
        eligible_reason="group mirror matches valid structure snapshot; safe to clear",
    )


def _classify_nongroup(prayer, stats):
    """Non-group-visibility mirror row (Category 2 / conservative skip)."""
    stats["nongroup_prayers_with_mirror"] += 1
    if prayer.structure_unit_at_post is None:
        # The legacy mirror is the only remaining structure context for this
        # non-group row. Leave it for a later display-mirror migration.
        stats["skipped_display_context_uncertain"] += 1
        return (
            _decision_line(
                prayer,
                mapped_unit=prayer.small_group_at_post.church_structure_unit,
                category="blocked",
                reason=(
                    "non-group row has no structure_unit_at_post; legacy mirror is "
                    "the only remaining structure context, skipped conservatively"
                ),
            ),
            None,
        )
    return _classify_matching_snapshot(
        prayer,
        stats,
        eligible_category="eligible_clear_nongroup_matching_snapshot",
        eligible_reason=(
            "non-group row carries a matching valid structure snapshot; legacy "
            "mirror is not displayed, safe to clear"
        ),
    )


def _classify_prayer(prayer, stats):
    if prayer.visibility == PrayerRequest.VISIBILITY_GROUP:
        return _classify_group(prayer, stats)
    return _classify_nongroup(prayer, stats)


def _scan(*, lock=False):
    stats = _new_stats()
    lines = []
    plans = []

    stats["prayers_checked"] = PrayerRequest.objects.count()

    for prayer in _mirror_queryset(lock=lock):
        stats["prayers_with_small_group_mirror"] += 1
        line, plan = _classify_prayer(prayer, stats)
        lines.append(line)
        if plan is not None:
            plans.append(plan)

    stats["prayers_without_small_group_mirror"] = (
        stats["prayers_checked"] - stats["prayers_with_small_group_mirror"]
    )
    stats["would_clear_count"] = stats["eligible_to_clear"]
    return stats, lines, plans


def _set_remaining(stats):
    stats["remaining_mirror_references_after_operation"] = (
        stats["prayers_with_small_group_mirror"] - stats["cleared_count"]
    )


def run_cleanup():
    stats, lines, _plans = _scan()
    _set_remaining(stats)
    return stats, lines


def apply_cleanup():
    with transaction.atomic():
        stats, lines, plans = _scan(lock=True)
        for plan in plans:
            updated = PrayerRequest.objects.filter(
                id=plan.prayer_id,
                small_group_at_post__isnull=False,
            ).update(small_group_at_post=None)
            if updated:
                stats["cleared_count"] += 1
        _set_remaining(stats)
    return stats, lines


class Command(BaseCommand):
    help = (
        "Dry-run-first guarded cleanup for existing legacy "
        "PrayerRequest.small_group_at_post mirrors (PRAYER-MIRROR.1B). Apply mode "
        "(requires --apply and --confirm-prayer-small-group-mirror-cleanup) sets "
        "small_group_at_post to null only for rows where clearing it cannot change "
        "visibility or display: group and non-group rows whose matching active "
        "small-group structure snapshot already carries the structure identity. "
        "It performs no schema migration, no runtime source switch, never prints "
        "prayer free text, and touches no other field or module's data."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help=(
                "Actually clear safe small_group_at_post mirrors. Requires "
                "--confirm-prayer-small-group-mirror-cleanup."
            ),
        )
        parser.add_argument(
            "--confirm-prayer-small-group-mirror-cleanup",
            action="store_true",
            help=(
                "Required with --apply to confirm this legacy small-group mirror "
                "cleanup."
            ),
        )
        parser.add_argument(
            "--verbose",
            action="store_true",
            help="Print per-prayer cleanup decisions (no free text).",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help=(
                "Limit verbose printed decisions to N rows. Does not limit "
                "scan/apply scope."
            ),
        )
        parser.add_argument(
            "--prayer-id",
            type=int,
            default=None,
            help=(
                "Optional: restrict verbose printed decisions to a single prayer "
                "id. Does not limit scan/apply scope."
            ),
        )

    def handle(self, *args, **options):
        if options["limit"] is not None and options["limit"] < 0:
            raise CommandError("--limit must be zero or greater.")

        apply_mode = options["apply"]
        confirmed = options["confirm_prayer_small_group_mirror_cleanup"]
        if apply_mode and not confirmed:
            raise CommandError(
                "--apply requires --confirm-prayer-small-group-mirror-cleanup; "
                "no PrayerRequest.small_group_at_post mirrors were cleared."
            )

        if apply_mode:
            stats, lines = apply_cleanup()
        else:
            stats, lines = run_cleanup()

        self._print_report(
            stats,
            lines,
            verbose=options["verbose"],
            verbose_limit=options["limit"],
            prayer_id=options["prayer_id"],
            apply_mode=apply_mode,
            confirmed=confirmed,
        )

    def _print_report(
        self,
        stats,
        lines,
        *,
        verbose,
        verbose_limit,
        prayer_id,
        apply_mode,
        confirmed,
    ):
        write = self.stdout.write
        data_mutated = bool(stats["cleared_count"])

        if apply_mode:
            write(
                "Prayer legacy small-group mirror cleanup "
                "(PRAYER-MIRROR.1B, APPLY mode)"
            )
        else:
            write(
                "Prayer legacy small-group mirror cleanup "
                "(PRAYER-MIRROR.1B, dry-run only)"
            )
        write("=" * 78)
        write(f"mode: {'apply' if apply_mode else 'dry-run'}")
        write(f"apply_option_present: {str(apply_mode).lower()}")
        write(f"confirmation_present: {str(confirmed).lower()}")
        for key in _STAT_KEYS:
            write(f"{key}: {stats[key]}")
        write(f"data_mutated: {str(data_mutated).lower()}")
        write("runtime_mutated: false")
        write("schema_mutated: false")
        write("")
        if apply_mode:
            write(
                "Apply mode: cleared only safe PrayerRequest.small_group_at_post "
                "legacy mirrors. visibility, structure_unit_at_post, status, "
                "title, body, answer_note, author, hidden/deleted state, Profile, "
                "membership, structure, SmallGroup, ServiceEvent, Bible Study, "
                "reflection, role, serving, audience, permission, and "
                "reading-progress data were not changed. No runtime source was "
                "switched and no schema migration was run. Prayer free text is "
                "never printed."
            )
        else:
            write(
                "Dry-run only: no prayer, legacy mirror, structure, membership, "
                "SmallGroup, ServiceEvent, Bible Study, reflection, role, serving, "
                "audience, permission, reading-progress, runtime, or schema data "
                "changed. Re-run with --apply "
                "--confirm-prayer-small-group-mirror-cleanup to write. Prayer free "
                "text is never printed."
            )

        if not verbose:
            return

        shown_source = lines
        if prayer_id is not None:
            shown_source = [line for line in lines if line.prayer_id == prayer_id]

        write("")
        write("per-prayer decisions:")
        if not shown_source:
            if prayer_id is not None:
                write(f"  (no legacy small-group mirror scanned for prayer #{prayer_id})")
            else:
                write("  (no legacy small-group mirrors scanned)")
            return
        shown_lines = (
            shown_source if verbose_limit is None else shown_source[:verbose_limit]
        )
        for line in shown_lines:
            write(_format_decision_line(line))
        if verbose_limit is not None and len(shown_source) > len(shown_lines):
            remaining = len(shown_source) - len(shown_lines)
            write(
                f"  (stopped at --limit {verbose_limit}; "
                f"{remaining} more prayer decision(s) not printed)"
            )
