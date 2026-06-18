"""BS-STRUCT.2A read-only Bible Study legacy-retirement readiness audit.

This command answers one operational question: *what remains before we can
keep zero-row V2 meetings failed closed for ordinary users?* It scans every
``BibleStudyMeeting`` row and reports human-readable counters describing how
each meeting's structure audience (``BibleStudyMeetingAudienceScope`` rows)
relates to its legacy ``small_group`` mirror, its ``anchor_unit``, and its
``meeting_kind``.

It is **strictly read-only**:

- It never creates, updates, or deletes any row (no ``--apply``; no
  ``SmallGroup`` / ``ChurchStructureUnit`` / ``ChurchStructureMembership`` /
  ``Profile`` writes).
- It changes **no** runtime behavior: visibility, landing/Today, role/worship
  pickers, generation, and forms are untouched.
- It does **not** delete legacy ``small_group`` fields or the legacy bridge.
  Those remain mirror/display/backfill context for separate retirement slices.

It audits whichever database Django is configured to use, so it needs no
production access of its own; an operator runs it against the target DB.

Hard blockers vs warnings
-------------------------

Two counters are **hard blockers** for keeping zero-row V2 meetings failed
closed without losing ordinary-member access to valid meetings:

- ``meetings_without_audience_rows`` — any meeting with zero
  ``BibleStudyMeetingAudienceScope`` rows now fails closed for ordinary users,
  so it must be backfilled or intentionally handled before publication
  (classification rule 1). This subsumes the more specific
  ``normal_meetings_without_audience_rows`` and the null-``small_group``-with-
  zero-rows case (rule 6).
- ``meetings_audience_mismatch_small_group_mirror`` — a meeting with exactly one
  small-group-type audience row whose unit disagrees with its
  ``small_group.church_structure_unit`` mirror. The row-first runtime and the
  legacy mirror point at different units; that data inconsistency is treated as
  a blocker so it is reconciled before retirement (rule 2; classification made
  explicit here as a **blocker**).

Every other reported problem is a **warning** — informational, not a
fallback-removal blocker on its own:

- ``meetings_small_group_unmapped`` / ``meetings_small_group_inactive_unit`` /
  ``meetings_small_group_wrong_unit_type`` — the legacy mirror's mapping is
  broken. When such a meeting also has zero audience rows it is already a hard
  blocker via ``meetings_without_audience_rows``; when it has audience rows the
  row-first runtime no longer depends on the mirror, so the broken mirror is
  data hygiene, not a zero-row fail-closed blocker.
- ``meetings_missing_anchor_unit`` / ``meetings_anchor_mismatch_small_group_unit``
  — ``anchor_unit`` is display/grouping/ownership only and is never a visibility
  source (see ``BibleStudyMeeting.anchor_unit``), so anchor issues are warnings
  (rule 7).

Two flags are emitted as runtime-state summaries for this slice:

- ``legacy_small_group_fallback_still_present = false`` — ordinary-member V2
  runtime visibility, landing/Today, and role/worship picker candidates no
  longer use the zero-row ``small_group`` fallback.
- ``runtime_zero_row_fallback_removed = true`` — zero-row V2 meetings fail
  closed for ordinary users. The report still surfaces
  ``db_data_blockers_clear`` so an operator can see whether any DB rows would
  now be hidden from ordinary users by that fail-closed behavior.

``Profile.small_group`` is **not** a V2 visibility/picker source and is never
consulted here (classification rule 8). V1 ``BibleStudySession`` is excluded
from this audit; it is a separate retirement target (rule 9).
"""

from collections import OrderedDict

from django.core.management.base import BaseCommand, CommandError

from accounts.models import ChurchStructureUnit
from studies.models import BibleStudyMeeting

# Ordered, stable list of the integer counters the command reports. New scopes
# append here so output stays deterministic.
_STAT_KEYS = (
    "meetings_checked",
    "meetings_with_audience_rows",
    "meetings_without_audience_rows",
    "normal_meetings_without_audience_rows",
    "meetings_with_null_small_group",
    "meetings_with_existing_audience_and_null_small_group",
    "meetings_with_single_small_group_audience",
    "meetings_with_multi_unit_audience",
    "meetings_with_higher_level_audience",
    "meetings_with_anchor_unit",
    "meetings_missing_anchor_unit",
    "meetings_anchor_mismatch_small_group_unit",
    "meetings_small_group_unmapped",
    "meetings_small_group_inactive_unit",
    "meetings_small_group_wrong_unit_type",
    "meetings_audience_mismatch_small_group_mirror",
)

# Hard blockers for keeping zero-row V2 meetings failed closed without hiding
# intended ordinary-member meetings. Only these cause a nonzero exit under
# ``--fail-on-blockers``. See the module docstring for why each is a blocker and
# why the warning counters are not.
_BLOCKER_KEYS = (
    "meetings_without_audience_rows",
    "meetings_audience_mismatch_small_group_mirror",
)

# Verbose detail categories. Each lists meeting id / title / group for the
# meetings that fell into it, to make blockers and warnings actionable.
_DETAIL_KEYS = (
    "zero_audience_rows",
    "null_small_group_zero_rows",
    "small_group_unmapped",
    "small_group_inactive_unit",
    "small_group_wrong_unit_type",
    "audience_mismatch_small_group_mirror",
    "anchor_mismatch_small_group_unit",
)


def _new_stats():
    return OrderedDict((key, 0) for key in _STAT_KEYS)


def _new_details():
    return OrderedDict((key, []) for key in _DETAIL_KEYS)


def _unit_label(unit):
    if unit is None:
        return "(none)"
    label = f"#{unit.id} {unit.code}"
    if getattr(unit, "name", ""):
        label = f"{label} {unit.name}"
    return label


def _group_label(group):
    if group is None:
        return "(none)"
    return f"#{group.id} {group.name}"


def _meeting_line(meeting, extra=""):
    title = meeting.lesson.title if meeting.lesson_id else ""
    line = (
        f"  meeting #{meeting.id}"
        f" | lesson: {title}"
        f" | small_group: {_group_label(meeting.small_group)}"
        f" | kind: {meeting.meeting_kind}"
    )
    if extra:
        line = f"{line} | {extra}"
    return line


def _resolve_small_group_unit_state(small_group):
    """Return ``(unit, state)`` for a meeting's legacy small_group mirror.

    ``state`` is one of ``"none_group"`` (no small_group at all), ``"unmapped"``,
    ``"inactive"``, ``"wrong_type"``, or ``"ok"`` (active ``UNIT_SMALL_GROUP``).
    Pure inspection; reads only the already-selected mapping.
    """
    if small_group is None:
        return None, "none_group"
    unit = small_group.church_structure_unit
    if unit is None:
        return None, "unmapped"
    if not unit.is_active:
        return unit, "inactive"
    if unit.unit_type != ChurchStructureUnit.UNIT_SMALL_GROUP:
        return unit, "wrong_type"
    return unit, "ok"


def run_audit():
    """Scan every BibleStudyMeeting row read-only.

    Returns ``(stats, details)``. Creates, edits, or deletes nothing. Audits all
    meetings regardless of status, because every meeting must carry audience rows
    before zero-row fail-closed behavior is data-safe.
    """
    stats = _new_stats()
    details = _new_details()

    meetings = (
        BibleStudyMeeting.objects.all()
        .select_related(
            "lesson",
            "small_group",
            "small_group__church_structure_unit",
            "anchor_unit",
        )
        .prefetch_related("audience_scope_links__unit")
        .order_by("id")
    )

    for meeting in meetings:
        stats["meetings_checked"] += 1

        audience_units = [link.unit for link in meeting.audience_scope_links.all()]
        n_rows = len(audience_units)

        # --- audience presence ------------------------------------------------
        if n_rows:
            stats["meetings_with_audience_rows"] += 1
        else:
            stats["meetings_without_audience_rows"] += 1
            details["zero_audience_rows"].append(_meeting_line(meeting))

        # --- null small_group -------------------------------------------------
        if meeting.small_group_id is None:
            stats["meetings_with_null_small_group"] += 1
            if n_rows:
                stats["meetings_with_existing_audience_and_null_small_group"] += 1
            else:
                details["null_small_group_zero_rows"].append(_meeting_line(meeting))

        # --- audience shape ---------------------------------------------------
        single_audience_unit = None
        if n_rows == 1:
            single_audience_unit = audience_units[0]
            if single_audience_unit.unit_type == ChurchStructureUnit.UNIT_SMALL_GROUP:
                stats["meetings_with_single_small_group_audience"] += 1
            else:
                stats["meetings_with_higher_level_audience"] += 1
        elif n_rows >= 2:
            stats["meetings_with_multi_unit_audience"] += 1

        # --- normal meeting without rows (blocker subset) ---------------------
        if meeting.meeting_kind == BibleStudyMeeting.KIND_NORMAL and not n_rows:
            stats["normal_meetings_without_audience_rows"] += 1

        # --- anchor presence --------------------------------------------------
        if meeting.anchor_unit_id is not None:
            stats["meetings_with_anchor_unit"] += 1
        else:
            stats["meetings_missing_anchor_unit"] += 1

        # --- small_group mirror mapping health --------------------------------
        sg_unit, sg_state = _resolve_small_group_unit_state(meeting.small_group)
        if sg_state == "unmapped":
            stats["meetings_small_group_unmapped"] += 1
            details["small_group_unmapped"].append(_meeting_line(meeting))
        elif sg_state == "inactive":
            stats["meetings_small_group_inactive_unit"] += 1
            details["small_group_inactive_unit"].append(
                _meeting_line(meeting, f"mapped unit: {_unit_label(sg_unit)} (inactive)")
            )
        elif sg_state == "wrong_type":
            stats["meetings_small_group_wrong_unit_type"] += 1
            details["small_group_wrong_unit_type"].append(
                _meeting_line(
                    meeting,
                    f"mapped unit: {_unit_label(sg_unit)} (unit_type={sg_unit.unit_type})",
                )
            )

        # --- anchor mismatch vs a clean small_group unit (warning) ------------
        # Only meaningful for a normal-style meeting whose mirror cleanly maps to
        # an active small-group unit; a higher-level anchor legitimately differs.
        if (
            sg_state == "ok"
            and meeting.anchor_unit_id is not None
            and meeting.anchor_unit_id != sg_unit.id
        ):
            stats["meetings_anchor_mismatch_small_group_unit"] += 1
            details["anchor_mismatch_small_group_unit"].append(
                _meeting_line(
                    meeting,
                    f"anchor: {_unit_label(meeting.anchor_unit)}"
                    f" vs small_group unit: {_unit_label(sg_unit)}",
                )
            )

        # --- single small-group row mismatching the mirror (blocker) ----------
        # Rule 2: a single small-group-type audience row should equal the
        # small_group mirror's mapped unit when that mapped unit is an active
        # UNIT_SMALL_GROUP. A disagreement means the row-first runtime and the
        # legacy mirror point at different units.
        if (
            single_audience_unit is not None
            and single_audience_unit.unit_type == ChurchStructureUnit.UNIT_SMALL_GROUP
            and sg_state == "ok"
            and single_audience_unit.id != sg_unit.id
        ):
            stats["meetings_audience_mismatch_small_group_mirror"] += 1
            details["audience_mismatch_small_group_mirror"].append(
                _meeting_line(
                    meeting,
                    f"audience unit: {_unit_label(single_audience_unit)}"
                    f" vs small_group unit: {_unit_label(sg_unit)}",
                )
            )

    return stats, details


def _blockers_present(stats):
    return any(stats[key] for key in _BLOCKER_KEYS)


class Command(BaseCommand):
    help = (
        "Read-only Bible Study legacy-retirement readiness audit (BS-STRUCT.2A). "
        "Scans every BibleStudyMeeting and reports counters describing how each "
        "meeting's BibleStudyMeetingAudienceScope rows relate to its legacy "
        "small_group mirror, anchor_unit, and meeting_kind. Creates/edits/deletes "
        "nothing and changes no runtime behavior. It does not delete legacy "
        "small_group fields or the legacy bridge. "
        "With --fail-on-blockers it exits nonzero only when a hard blocker "
        "(meetings_without_audience_rows or "
        "meetings_audience_mismatch_small_group_mirror) is present."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--verbose",
            action="store_true",
            help=(
                "Also list meeting id / lesson title / small_group for each "
                "blocker and warning category (zero-row meetings that now fail "
                "closed, "
                "null-small_group zero-row meetings, unmapped/inactive/wrong-type "
                "mirror mappings, single-row/mirror mismatches, and anchor "
                "mismatches). Independent of Django -v verbosity."
            ),
        )
        parser.add_argument(
            "--fail-on-blockers",
            action="store_true",
            help=(
                "Exit with an error when any hard blocker is present "
                "(meetings_without_audience_rows, "
                "meetings_audience_mismatch_small_group_mirror). Still read-only; "
                "nothing is changed."
            ),
        )

    def handle(self, *args, **options):
        stats, details = run_audit()
        self._print_report(stats, details, options["verbose"])

        if options["fail_on_blockers"] and _blockers_present(stats):
            present = [f"{key}={stats[key]}" for key in _BLOCKER_KEYS if stats[key]]
            raise CommandError(
                "Bible Study legacy-retirement readiness hard blockers present "
                "(--fail-on-blockers): " + ", ".join(present)
            )

    def _print_report(self, stats, details, verbose):
        write = self.stdout.write
        blockers_clear = not _blockers_present(stats)

        write(
            "Bible Study legacy-retirement readiness audit "
            "(BS-STRUCT.2A, read-only)"
        )
        write("=" * 72)
        write(f"meetings_checked                                : {stats['meetings_checked']}")
        write(f"meetings_with_audience_rows                     : {stats['meetings_with_audience_rows']}")
        write(f"meetings_without_audience_rows                  : {stats['meetings_without_audience_rows']}")
        write(f"normal_meetings_without_audience_rows           : {stats['normal_meetings_without_audience_rows']}")
        write(f"meetings_with_null_small_group                  : {stats['meetings_with_null_small_group']}")
        write(f"meetings_with_existing_audience_and_null_small_group : {stats['meetings_with_existing_audience_and_null_small_group']}")
        write(f"meetings_with_single_small_group_audience       : {stats['meetings_with_single_small_group_audience']}")
        write(f"meetings_with_multi_unit_audience               : {stats['meetings_with_multi_unit_audience']}")
        write(f"meetings_with_higher_level_audience             : {stats['meetings_with_higher_level_audience']}")
        write(f"meetings_with_anchor_unit                       : {stats['meetings_with_anchor_unit']}")
        write(f"meetings_missing_anchor_unit                    : {stats['meetings_missing_anchor_unit']}")
        write(f"meetings_anchor_mismatch_small_group_unit       : {stats['meetings_anchor_mismatch_small_group_unit']}")
        write(f"meetings_small_group_unmapped                   : {stats['meetings_small_group_unmapped']}")
        write(f"meetings_small_group_inactive_unit              : {stats['meetings_small_group_inactive_unit']}")
        write(f"meetings_small_group_wrong_unit_type            : {stats['meetings_small_group_wrong_unit_type']}")
        write(f"meetings_audience_mismatch_small_group_mirror   : {stats['meetings_audience_mismatch_small_group_mirror']}")
        write("-" * 72)
        write("blockers (hard, gate zero-row fail-closed safety):")
        for key in _BLOCKER_KEYS:
            write(f"  {key:<44}: {stats[key]}")
        write("warnings (informational, not zero-row fail-closed blockers):")
        for key in (
            "meetings_small_group_unmapped",
            "meetings_small_group_inactive_unit",
            "meetings_small_group_wrong_unit_type",
            "meetings_missing_anchor_unit",
            "meetings_anchor_mismatch_small_group_unit",
        ):
            write(f"  {key:<44}: {stats[key]}")
        write("-" * 72)
        # Runtime-state flags for this slice (see module docstring).
        write("legacy_small_group_fallback_still_present       : false")
        write(f"db_data_blockers_clear                          : {'true' if blockers_clear else 'false'}")
        write("runtime_zero_row_fallback_removed               : true")
        write("")
        write(
            "Audit only: no meeting, audience row, small_group, unit, membership, "
            "or profile was changed; no runtime behavior changed. Zero-row V2 "
            "meetings now fail closed for ordinary users in runtime code; this "
            "command reports whether database rows are clear for that behavior."
        )

        if not verbose:
            return

        write("")
        write("details (blocker and warning categories only):")
        for key in _DETAIL_KEYS:
            rows = details[key]
            write(f"{key} ({len(rows)}):")
            if rows:
                for row in rows:
                    write(row)
            else:
                write("  (none)")
