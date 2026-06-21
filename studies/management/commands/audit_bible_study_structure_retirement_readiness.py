"""BS-STRUCT.2A read-only Bible Study legacy-retirement readiness audit.

This command answers one operational question: *what remains before we can
keep zero-row V2 meetings failed closed for ordinary users?* It scans every
``BibleStudyMeeting`` row and reports human-readable counters describing each
meeting's structure audience (``BibleStudyMeetingAudienceScope`` rows),
``anchor_unit``, and audience shape.

BS-MEETING-MIRROR.1A removed the legacy ``BibleStudyMeeting.small_group``
mirror, so this audit is fully structure-native: there is no longer a per-meeting
mirror to reconcile against audience rows.

It is **strictly read-only**:

- It never creates, updates, or deletes any row (no ``--apply``).
- It changes **no** runtime behavior: visibility, landing/Today, role/worship
  pickers, generation, and forms are untouched.

It audits whichever database Django is configured to use, so it needs no
production access of its own; an operator runs it against the target DB.

Hard blocker
------------

One counter is a **hard blocker** for keeping zero-row V2 meetings failed
closed without losing ordinary-member access to valid meetings:

- ``meetings_without_audience_rows`` — any meeting with zero
  ``BibleStudyMeetingAudienceScope`` rows now fails closed for ordinary users,
  so it must be backfilled or intentionally handled before publication. This
  subsumes the more specific ``normal_meetings_without_audience_rows``.

``meetings_missing_anchor_unit`` is a **warning**: ``anchor_unit`` is
display/grouping/ownership only and is never a visibility source (see
``BibleStudyMeeting.anchor_unit``).

Two flags are emitted as runtime-state summaries for this slice:

- ``legacy_small_group_fallback_still_present = false`` — ordinary-member V2
  runtime visibility, landing/Today, and role/worship picker candidates do not
  use any ``small_group`` fallback, and the mirror field has been removed.
- ``runtime_zero_row_fallback_removed = true`` — zero-row V2 meetings fail
  closed for ordinary users.

``Profile.small_group`` is **not** a V2 visibility/picker source and is never
consulted here. V1 ``BibleStudySession`` is excluded from this audit; it is a
separate retirement target.
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
    "meetings_with_single_small_group_audience",
    "meetings_with_multi_unit_audience",
    "meetings_with_higher_level_audience",
    "meetings_with_anchor_unit",
    "meetings_missing_anchor_unit",
)

# Hard blockers for keeping zero-row V2 meetings failed closed without hiding
# intended ordinary-member meetings. Only these cause a nonzero exit under
# ``--fail-on-blockers``.
_BLOCKER_KEYS = ("meetings_without_audience_rows",)

# Verbose detail categories. Each lists meeting id / title for the meetings that
# fell into it, to make blockers and warnings actionable.
_DETAIL_KEYS = (
    "zero_audience_rows",
    "missing_anchor_unit",
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


def _meeting_line(meeting, extra=""):
    title = meeting.lesson.title if meeting.lesson_id else ""
    line = (
        f"  meeting #{meeting.id}"
        f" | lesson: {title}"
        f" | kind: {meeting.meeting_kind}"
    )
    if extra:
        line = f"{line} | {extra}"
    return line


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

        # --- audience shape ---------------------------------------------------
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
            details["missing_anchor_unit"].append(_meeting_line(meeting))

    return stats, details


def _blockers_present(stats):
    return any(stats[key] for key in _BLOCKER_KEYS)


class Command(BaseCommand):
    help = (
        "Read-only Bible Study legacy-retirement readiness audit (BS-STRUCT.2A). "
        "Scans every BibleStudyMeeting and reports counters describing each "
        "meeting's BibleStudyMeetingAudienceScope rows, anchor_unit, and audience "
        "shape. Creates/edits/deletes nothing and changes no runtime behavior. "
        "With --fail-on-blockers it exits nonzero only when a hard blocker "
        "(meetings_without_audience_rows) is present."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--verbose",
            action="store_true",
            help=(
                "Also list meeting id / lesson title for each blocker and warning "
                "category (zero-row meetings that now fail closed and "
                "missing-anchor meetings). Independent of Django -v verbosity."
            ),
        )
        parser.add_argument(
            "--fail-on-blockers",
            action="store_true",
            help=(
                "Exit with an error when the hard blocker "
                "(meetings_without_audience_rows) is present. Still read-only; "
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
        write(f"meetings_with_single_small_group_audience       : {stats['meetings_with_single_small_group_audience']}")
        write(f"meetings_with_multi_unit_audience               : {stats['meetings_with_multi_unit_audience']}")
        write(f"meetings_with_higher_level_audience             : {stats['meetings_with_higher_level_audience']}")
        write(f"meetings_with_anchor_unit                       : {stats['meetings_with_anchor_unit']}")
        write(f"meetings_missing_anchor_unit                    : {stats['meetings_missing_anchor_unit']}")
        write("-" * 72)
        write("blockers (hard, gate zero-row fail-closed safety):")
        for key in _BLOCKER_KEYS:
            write(f"  {key:<44}: {stats[key]}")
        write("warnings (informational, not zero-row fail-closed blockers):")
        for key in ("meetings_missing_anchor_unit",):
            write(f"  {key:<44}: {stats[key]}")
        write("-" * 72)
        # Runtime-state flags for this slice (see module docstring).
        write("legacy_small_group_fallback_still_present       : false")
        write(f"db_data_blockers_clear                          : {'true' if blockers_clear else 'false'}")
        write("runtime_zero_row_fallback_removed               : true")
        write("")
        write(
            "Audit only: no meeting, audience row, unit, membership, or profile "
            "was changed; no runtime behavior changed. Zero-row V2 meetings fail "
            "closed for ordinary users in runtime code; this command reports "
            "whether database rows are clear for that behavior."
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
