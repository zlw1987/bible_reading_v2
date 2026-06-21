"""Backfill structure-native generation keys for existing V2 meetings.

Dry-run is the default. Apply mode only updates ``BibleStudyMeeting`` identity
fields that are safe to derive from an existing single small-group audience row:
``generation_key`` and a null ``anchor_unit``. It never mutates
``BibleStudyMeetingAudienceScope`` rows. BS-MEETING-MIRROR.1A removed the legacy
``small_group`` mirror, so there is no mirror to inspect or preserve.
"""

from dataclasses import dataclass

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Prefetch

from accounts.models import ChurchStructureUnit
from studies.models import BibleStudyMeeting, BibleStudyMeetingAudienceScope
from studies.services import normal_generation_key_for_unit


_STAT_KEYS = (
    "meetings_checked",
    "normal_meetings_checked",
    "non_normal_meetings_skipped",
    "meetings_without_audience_rows",
    "meetings_with_multiple_audience_rows",
    "meetings_with_non_small_group_audience",
    "meetings_with_inactive_audience_unit",
    "meetings_generation_key_already_correct",
    "meetings_generation_key_missing",
    "meetings_generation_key_mismatch_blocked",
    "meetings_generation_key_conflict_blocked",
    "meetings_anchor_missing",
    "meetings_anchor_already_correct",
    "meetings_anchor_mismatch_blocked",
    "would_update_generation_key",
    "would_update_anchor_unit",
    "updated_generation_key",
    "updated_anchor_unit",
)

_BLOCKER_KEYS = (
    "meetings_without_audience_rows",
    "meetings_with_multiple_audience_rows",
    "meetings_with_non_small_group_audience",
    "meetings_with_inactive_audience_unit",
    "meetings_generation_key_mismatch_blocked",
    "meetings_generation_key_conflict_blocked",
    "meetings_anchor_mismatch_blocked",
)


@dataclass(frozen=True)
class MeetingPlan:
    meeting_id: int
    update_generation_key: bool = False
    update_anchor_unit: bool = False
    expected_generation_key: str = ""
    audience_unit_id: int | None = None


@dataclass(frozen=True)
class DecisionLine:
    meeting_id: int
    lesson_id: int | None
    lesson_title: str
    current_generation_key: str
    expected_generation_key: str
    anchor_unit: str
    audience_unit: str
    category: str
    reason: str


def _new_stats():
    return {key: 0 for key in _STAT_KEYS}


def _unit_label(unit):
    if unit is None:
        return "(none)"
    label = f"#{unit.id} {unit.code}"
    name = getattr(unit, "name_en", "") or getattr(unit, "name", "")
    if name:
        label = f"{label} {name}"
    return label


def _clean_key(value):
    return (value or "").strip()


def _decision_line(
    meeting,
    *,
    category,
    reason,
    expected_generation_key="",
    audience_unit=None,
):
    return DecisionLine(
        meeting_id=meeting.id,
        lesson_id=meeting.lesson_id,
        lesson_title=meeting.lesson.title if meeting.lesson_id else "",
        current_generation_key=_clean_key(meeting.generation_key) or "(blank)",
        expected_generation_key=expected_generation_key or "(n/a)",
        anchor_unit=_unit_label(meeting.anchor_unit),
        audience_unit=_unit_label(audience_unit),
        category=category,
        reason=reason,
    )


def _format_decision_line(line):
    return (
        f"  meeting #{line.meeting_id} | lesson #{line.lesson_id or '(none)'} "
        f"{line.lesson_title!r} | generation_key: {line.current_generation_key} "
        f"| expected: {line.expected_generation_key} | anchor_unit: {line.anchor_unit} "
        f"| audience_unit: {line.audience_unit} "
        f"| category: {line.category} | reason: {line.reason}"
    )


def _has_generation_key_conflict(meeting, expected_key):
    return (
        BibleStudyMeeting.objects.filter(
            lesson_id=meeting.lesson_id,
            generation_key=expected_key,
        )
        .exclude(id=meeting.id)
        .exists()
    )


def _classify_meeting(meeting, stats):
    if meeting.meeting_kind != BibleStudyMeeting.KIND_NORMAL:
        stats["non_normal_meetings_skipped"] += 1
        return (
            _decision_line(
                meeting,
                category="non_normal_meetings_skipped",
                reason=f"meeting_kind is {meeting.meeting_kind!r}",
            ),
            None,
        )

    stats["normal_meetings_checked"] += 1
    audience_links = list(meeting._prefetched_audience_links)
    if not audience_links:
        stats["meetings_without_audience_rows"] += 1
        return (
            _decision_line(
                meeting,
                category="meetings_without_audience_rows",
                reason="normal meeting has no audience rows",
            ),
            None,
        )
    if len(audience_links) > 1:
        stats["meetings_with_multiple_audience_rows"] += 1
        return (
            _decision_line(
                meeting,
                category="meetings_with_multiple_audience_rows",
                reason="normal meeting has more than one audience row",
            ),
            None,
        )

    audience_unit = audience_links[0].unit
    expected_key = normal_generation_key_for_unit(audience_unit)
    if not audience_unit.is_active:
        stats["meetings_with_inactive_audience_unit"] += 1
        return (
            _decision_line(
                meeting,
                category="meetings_with_inactive_audience_unit",
                reason="single audience unit is inactive",
                expected_generation_key=expected_key,
                audience_unit=audience_unit,
            ),
            None,
        )
    if audience_unit.unit_type != ChurchStructureUnit.UNIT_SMALL_GROUP:
        stats["meetings_with_non_small_group_audience"] += 1
        return (
            _decision_line(
                meeting,
                category="meetings_with_non_small_group_audience",
                reason=(
                    f"single audience unit type is {audience_unit.unit_type!r}, "
                    f"not {ChurchStructureUnit.UNIT_SMALL_GROUP!r}"
                ),
                expected_generation_key=expected_key,
                audience_unit=audience_unit,
            ),
            None,
        )

    current_key = _clean_key(meeting.generation_key)
    update_generation_key = False
    if not current_key:
        stats["meetings_generation_key_missing"] += 1
        if _has_generation_key_conflict(meeting, expected_key):
            stats["meetings_generation_key_conflict_blocked"] += 1
            return (
                _decision_line(
                    meeting,
                    category="meetings_generation_key_conflict_blocked",
                    reason="another meeting for this lesson already has the expected key",
                    expected_generation_key=expected_key,
                    audience_unit=audience_unit,
                ),
                None,
            )
        update_generation_key = True
    elif current_key == expected_key:
        stats["meetings_generation_key_already_correct"] += 1
    else:
        stats["meetings_generation_key_mismatch_blocked"] += 1
        return (
            _decision_line(
                meeting,
                category="meetings_generation_key_mismatch_blocked",
                reason="existing non-empty generation_key differs from expected key",
                expected_generation_key=expected_key,
                audience_unit=audience_unit,
            ),
            None,
        )

    update_anchor_unit = False
    if meeting.anchor_unit_id is None:
        stats["meetings_anchor_missing"] += 1
        update_anchor_unit = True
    elif meeting.anchor_unit_id == audience_unit.id:
        stats["meetings_anchor_already_correct"] += 1
    else:
        stats["meetings_anchor_mismatch_blocked"] += 1
        return (
            _decision_line(
                meeting,
                category="meetings_anchor_mismatch_blocked",
                reason=(
                    "existing anchor_unit differs from the single audience unit; "
                    "row left unchanged"
                ),
                expected_generation_key=expected_key,
                audience_unit=audience_unit,
            ),
            None,
        )

    if update_generation_key:
        stats["would_update_generation_key"] += 1
    if update_anchor_unit:
        stats["would_update_anchor_unit"] += 1

    if update_generation_key or update_anchor_unit:
        category = "would_update"
        reason = "safe structure-native identity backfill"
    else:
        category = "already_correct"
        reason = "generation_key and anchor_unit are already aligned"

    return (
        _decision_line(
            meeting,
            category=category,
            reason=reason,
            expected_generation_key=expected_key,
            audience_unit=audience_unit,
        ),
        MeetingPlan(
            meeting_id=meeting.id,
            update_generation_key=update_generation_key,
            update_anchor_unit=update_anchor_unit,
            expected_generation_key=expected_key,
            audience_unit_id=audience_unit.id,
        ),
    )


def _meeting_queryset(*, meeting_id=None, lesson_id=None, lock=False):
    links = BibleStudyMeetingAudienceScope.objects.select_related("unit").order_by("id")
    meetings = (
        BibleStudyMeeting.objects.select_related(
            "lesson",
            "anchor_unit",
        )
        .prefetch_related(
            Prefetch(
                "audience_scope_links",
                queryset=links,
                to_attr="_prefetched_audience_links",
            )
        )
        .order_by("id")
    )
    if lock:
        meetings = meetings.select_for_update()
    if meeting_id is not None:
        meetings = meetings.filter(id=meeting_id)
    if lesson_id is not None:
        meetings = meetings.filter(lesson_id=lesson_id)
    return meetings


def _scan_meetings(*, meeting_id=None, lesson_id=None, lock=False):
    stats = _new_stats()
    lines = []
    plans = []
    for meeting in _meeting_queryset(
        meeting_id=meeting_id,
        lesson_id=lesson_id,
        lock=lock,
    ):
        stats["meetings_checked"] += 1
        line, plan = _classify_meeting(meeting, stats)
        lines.append(line)
        if plan and (plan.update_generation_key or plan.update_anchor_unit):
            plans.append(plan)
    return stats, lines, plans


def run_audit(*, meeting_id=None, lesson_id=None):
    stats, lines, _plans = _scan_meetings(
        meeting_id=meeting_id,
        lesson_id=lesson_id,
    )
    return stats, lines


def apply_backfill(*, meeting_id=None, lesson_id=None):
    with transaction.atomic():
        stats, lines, plans = _scan_meetings(
            meeting_id=meeting_id,
            lesson_id=lesson_id,
            lock=True,
        )
        for plan in plans:
            meeting = BibleStudyMeeting.objects.select_for_update().get(id=plan.meeting_id)
            update_fields = []
            if plan.update_generation_key:
                meeting.generation_key = plan.expected_generation_key
                update_fields.append("generation_key")
            if plan.update_anchor_unit:
                meeting.anchor_unit_id = plan.audience_unit_id
                update_fields.append("anchor_unit")
            if update_fields:
                update_fields.append("updated_at")
                meeting.save(update_fields=update_fields)
                if plan.update_generation_key:
                    stats["updated_generation_key"] += 1
                if plan.update_anchor_unit:
                    stats["updated_anchor_unit"] += 1
    return stats, lines


class Command(BaseCommand):
    help = (
        "Dry-run-first backfill for existing normal V2 BibleStudyMeeting rows "
        "missing structure-native generation_key / safe anchor_unit identity. "
        "Apply mode only touches generation_key and anchor_unit; it never "
        "mutates audience rows or runtime behavior."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help=(
                "Actually update safe rows. Without this flag the command is a "
                "read-only dry-run and writes nothing."
            ),
        )
        parser.add_argument(
            "--verbose",
            action="store_true",
            help="Print per-meeting decisions for the scanned rows.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help=(
                "Limit verbose printed examples to N meeting decisions. Does "
                "not limit scan/apply scope; use --meeting-id or --lesson-id "
                "to intentionally narrow scope."
            ),
        )
        parser.add_argument(
            "--meeting-id",
            type=int,
            default=None,
            help="Process only one BibleStudyMeeting id.",
        )
        parser.add_argument(
            "--lesson-id",
            type=int,
            default=None,
            help="Process only meetings for one BibleStudyLesson id.",
        )
        parser.add_argument(
            "--fail-on-blockers",
            action="store_true",
            help=(
                "Exit nonzero when any blocked/unsafe bucket is nonzero. Dry-run "
                "still writes nothing."
            ),
        )

    def handle(self, *args, **options):
        if options["limit"] is not None and options["limit"] < 0:
            raise CommandError("--limit must be zero or greater.")

        command_kwargs = {
            "meeting_id": options["meeting_id"],
            "lesson_id": options["lesson_id"],
        }
        apply_mode = options["apply"]
        if apply_mode:
            stats, lines = apply_backfill(**command_kwargs)
        else:
            stats, lines = run_audit(**command_kwargs)

        self._print_report(
            stats,
            lines,
            verbose=options["verbose"],
            verbose_limit=options["limit"],
            apply_mode=apply_mode,
        )

        if options["fail_on_blockers"]:
            blockers = [f"{key}={stats[key]}" for key in _BLOCKER_KEYS if stats[key]]
            if blockers:
                raise CommandError(
                    "BibleStudyMeeting V2 generation-key backfill blockers "
                    "present (--fail-on-blockers): " + ", ".join(blockers)
                )

    def _print_report(self, stats, lines, *, verbose, verbose_limit, apply_mode):
        write = self.stdout.write
        data_mutated = bool(
            stats["updated_generation_key"] or stats["updated_anchor_unit"]
        )

        if apply_mode:
            write("BibleStudyMeeting V2 generation-key backfill (BS-V2-KEY.1A, APPLY mode)")
        else:
            write(
                "BibleStudyMeeting V2 generation-key backfill "
                "(BS-V2-KEY.1A, dry-run only)"
            )
        write("=" * 78)
        for key in _STAT_KEYS:
            write(f"{key}: {stats[key]}")
        write(f"data_mutated: {str(data_mutated).lower()}")
        write("runtime_mutated: false")
        write("")
        if apply_mode:
            write(
                "Apply mode: updated safe generation_key/anchor_unit values only; "
                "audience rows were not mutated."
            )
        else:
            write(
                "Dry-run only: no generation_key, anchor_unit, audience row, or "
                "runtime behavior changed."
            )

        if not verbose:
            return

        write("")
        write("per-meeting decisions:")
        if not lines:
            write("  (no meetings scanned)")
            return
        shown_lines = lines if verbose_limit is None else lines[:verbose_limit]
        for line in shown_lines:
            write(_format_decision_line(line))
        if verbose_limit is not None and len(lines) > len(shown_lines):
            remaining = len(lines) - len(shown_lines)
            write(
                f"  (stopped at --limit {verbose_limit}; "
                f"{remaining} more meeting decision(s) not printed)"
            )
