"""Guarded cleanup for existing V2 BibleStudyMeeting.small_group mirrors.

Dry-run is the default. Apply mode only clears the legacy ``small_group``
mirror when the meeting already has complete structure-native identity:
exactly one active small-group audience row, matching ``anchor_unit``, matching
``generation_key``, and a legacy SmallGroup mapping to that same unit.
"""

from dataclasses import dataclass

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Prefetch

from accounts.models import ChurchStructureUnit
from studies.models import BibleStudyMeeting, BibleStudyMeetingAudienceScope
from studies.services import normal_generation_key_for_unit
from studies.visibility import get_small_group_structure_unit


_STAT_KEYS = (
    "meetings_checked",
    "meetings_with_small_group_mirror",
    "safe_to_clear_small_group_mirror",
    "would_clear_small_group_mirror",
    "cleared_small_group_mirror",
    "already_null_small_group",
    "blocked_non_normal_kind",
    "blocked_no_audience_rows",
    "blocked_multiple_audience_rows",
    "blocked_inactive_audience_unit",
    "blocked_non_small_group_audience_unit",
    "blocked_anchor_missing",
    "blocked_anchor_mismatch",
    "blocked_generation_key_missing",
    "blocked_generation_key_mismatch",
    "blocked_small_group_unmapped",
    "blocked_small_group_unit_mismatch",
    "cleanup_blockers",
)

_BLOCKER_KEYS = (
    "blocked_non_normal_kind",
    "blocked_no_audience_rows",
    "blocked_multiple_audience_rows",
    "blocked_inactive_audience_unit",
    "blocked_non_small_group_audience_unit",
    "blocked_anchor_missing",
    "blocked_anchor_mismatch",
    "blocked_generation_key_missing",
    "blocked_generation_key_mismatch",
    "blocked_small_group_unmapped",
    "blocked_small_group_unit_mismatch",
)


@dataclass(frozen=True)
class CleanupPlan:
    meeting_id: int


@dataclass(frozen=True)
class DecisionLine:
    meeting_id: int
    lesson_id: int | None
    lesson_title: str
    small_group: str
    audience_unit: str
    anchor_unit: str
    generation_key: str
    category: str
    reason: str


def _new_stats():
    return {key: 0 for key in _STAT_KEYS}


def _clean_key(value):
    return (value or "").strip()


def _unit_label(unit):
    if unit is None:
        return "(none)"
    try:
        path = unit.path_label("en")
    except AttributeError:
        path = getattr(unit, "name_en", "") or getattr(unit, "name", "")
    if not path:
        path = getattr(unit, "code", "")
    return f"#{unit.id} {path}".strip()


def _group_label(group):
    if group is None:
        return "(none)"
    return f"#{group.id} {group.name}"


def _decision_line(meeting, *, category, reason, audience_unit=None):
    return DecisionLine(
        meeting_id=meeting.id,
        lesson_id=meeting.lesson_id,
        lesson_title=meeting.lesson.title if meeting.lesson_id else "",
        small_group=_group_label(meeting.small_group),
        audience_unit=_unit_label(audience_unit),
        anchor_unit=_unit_label(meeting.anchor_unit),
        generation_key=_clean_key(meeting.generation_key) or "(blank)",
        category=category,
        reason=reason,
    )


def _format_decision_line(line):
    return (
        f"  meeting #{line.meeting_id} | lesson #{line.lesson_id or '(none)'} "
        f"{line.lesson_title!r} | small_group: {line.small_group} "
        f"| audience_unit: {line.audience_unit} | anchor_unit: {line.anchor_unit} "
        f"| generation_key: {line.generation_key} | category: {line.category} "
        f"| reason: {line.reason}"
    )


def _blocked(stats, key, meeting, reason, *, audience_unit=None):
    stats[key] += 1
    stats["cleanup_blockers"] += 1
    return (
        _decision_line(
            meeting,
            category="blocked",
            reason=f"{key}: {reason}",
            audience_unit=audience_unit,
        ),
        None,
    )


def _classify_meeting(meeting, stats, *, apply_mode):
    if meeting.small_group_id is None:
        stats["already_null_small_group"] += 1
        return (
            _decision_line(
                meeting,
                category="already_null",
                reason="BibleStudyMeeting.small_group is already null",
            ),
            None,
        )

    stats["meetings_with_small_group_mirror"] += 1

    if meeting.meeting_kind != BibleStudyMeeting.KIND_NORMAL:
        return _blocked(
            stats,
            "blocked_non_normal_kind",
            meeting,
            f"meeting_kind is {meeting.meeting_kind!r}",
        )

    audience_links = list(meeting._prefetched_audience_links)
    if not audience_links:
        return _blocked(
            stats,
            "blocked_no_audience_rows",
            meeting,
            "normal meeting has no audience rows",
        )
    if len(audience_links) > 1:
        return _blocked(
            stats,
            "blocked_multiple_audience_rows",
            meeting,
            "normal meeting has more than one audience row",
        )

    audience_unit = audience_links[0].unit
    if not audience_unit.is_active:
        return _blocked(
            stats,
            "blocked_inactive_audience_unit",
            meeting,
            "single audience unit is inactive",
            audience_unit=audience_unit,
        )
    if audience_unit.unit_type != ChurchStructureUnit.UNIT_SMALL_GROUP:
        return _blocked(
            stats,
            "blocked_non_small_group_audience_unit",
            meeting,
            (
                f"single audience unit type is {audience_unit.unit_type!r}, "
                f"not {ChurchStructureUnit.UNIT_SMALL_GROUP!r}"
            ),
            audience_unit=audience_unit,
        )

    if meeting.anchor_unit_id is None:
        return _blocked(
            stats,
            "blocked_anchor_missing",
            meeting,
            "anchor_unit is missing",
            audience_unit=audience_unit,
        )
    if meeting.anchor_unit_id != audience_unit.id:
        return _blocked(
            stats,
            "blocked_anchor_mismatch",
            meeting,
            "anchor_unit differs from the single audience unit",
            audience_unit=audience_unit,
        )

    expected_key = normal_generation_key_for_unit(audience_unit)
    current_key = _clean_key(meeting.generation_key)
    if not current_key:
        return _blocked(
            stats,
            "blocked_generation_key_missing",
            meeting,
            "generation_key is missing",
            audience_unit=audience_unit,
        )
    if current_key != expected_key:
        return _blocked(
            stats,
            "blocked_generation_key_mismatch",
            meeting,
            f"generation_key {current_key!r} does not equal {expected_key!r}",
            audience_unit=audience_unit,
        )

    small_group_unit = get_small_group_structure_unit(meeting.small_group)
    if small_group_unit is None:
        return _blocked(
            stats,
            "blocked_small_group_unmapped",
            meeting,
            "legacy small_group has no ChurchStructureUnit mapping",
            audience_unit=audience_unit,
        )
    if small_group_unit.id != audience_unit.id:
        return _blocked(
            stats,
            "blocked_small_group_unit_mismatch",
            meeting,
            "legacy small_group mapping differs from the single audience unit",
            audience_unit=audience_unit,
        )

    stats["safe_to_clear_small_group_mirror"] += 1
    if apply_mode:
        category = "cleared"
        reason = "safe mirror cleanup applied"
    else:
        stats["would_clear_small_group_mirror"] += 1
        category = "would_clear"
        reason = "safe mirror cleanup candidate"

    return (
        _decision_line(
            meeting,
            category=category,
            reason=reason,
            audience_unit=audience_unit,
        ),
        CleanupPlan(meeting_id=meeting.id),
    )


def _meeting_queryset(*, meeting_id=None, lesson_id=None, lock=False):
    links = BibleStudyMeetingAudienceScope.objects.select_related("unit").order_by("id")
    meetings = (
        BibleStudyMeeting.objects.select_related(
            "lesson",
            "small_group",
            "small_group__church_structure_unit",
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


def _scan_meetings(*, meeting_id=None, lesson_id=None, lock=False, apply_mode=False):
    stats = _new_stats()
    lines = []
    plans = []
    for meeting in _meeting_queryset(
        meeting_id=meeting_id,
        lesson_id=lesson_id,
        lock=lock,
    ):
        stats["meetings_checked"] += 1
        line, plan = _classify_meeting(meeting, stats, apply_mode=apply_mode)
        lines.append(line)
        if plan is not None:
            plans.append(plan)
    return stats, lines, plans


def run_audit(*, meeting_id=None, lesson_id=None):
    stats, lines, _plans = _scan_meetings(
        meeting_id=meeting_id,
        lesson_id=lesson_id,
    )
    return stats, lines


def apply_cleanup(*, meeting_id=None, lesson_id=None):
    with transaction.atomic():
        stats, lines, plans = _scan_meetings(
            meeting_id=meeting_id,
            lesson_id=lesson_id,
            lock=True,
            apply_mode=True,
        )
        for plan in plans:
            meeting = BibleStudyMeeting.objects.select_for_update().get(
                id=plan.meeting_id,
            )
            meeting.small_group = None
            meeting.save(update_fields=["small_group", "updated_at"])
            stats["cleared_small_group_mirror"] += 1
    return stats, lines


class Command(BaseCommand):
    help = (
        "Dry-run-first cleanup for existing V2 BibleStudyMeeting.small_group "
        "mirrors (BS-V2-MIRROR.1C). Apply mode clears only safe rows that "
        "already have generation_key, anchor_unit, and exactly one matching "
        "small-group audience row. It never changes visibility, audience rows, "
        "generation identity, V1 sessions, or BibleStudySeries.small_group."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help=(
                "Actually clear safe BibleStudyMeeting.small_group mirrors. "
                "Requires --confirm-small-group-mirror-retirement."
            ),
        )
        parser.add_argument(
            "--confirm-small-group-mirror-retirement",
            action="store_true",
            help="Required with --apply to confirm this mirror-retirement cleanup.",
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
            "--verbose",
            action="store_true",
            help="Print per-meeting cleanup decisions.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help=(
                "Limit verbose printed decisions to N meetings. Does not limit "
                "scan/apply scope; use --meeting-id or --lesson-id to narrow scope."
            ),
        )
        parser.add_argument(
            "--fail-on-blockers",
            action="store_true",
            help="Exit nonzero when any unsafe mirror-cleanup blocker is present.",
        )

    def handle(self, *args, **options):
        if options["limit"] is not None and options["limit"] < 0:
            raise CommandError("--limit must be zero or greater.")

        apply_mode = options["apply"]
        confirmed = options["confirm_small_group_mirror_retirement"]
        if apply_mode and not confirmed:
            raise CommandError(
                "--apply requires --confirm-small-group-mirror-retirement; "
                "no BibleStudyMeeting.small_group mirrors were cleared."
            )

        command_kwargs = {
            "meeting_id": options["meeting_id"],
            "lesson_id": options["lesson_id"],
        }
        if apply_mode:
            stats, lines = apply_cleanup(**command_kwargs)
        else:
            stats, lines = run_audit(**command_kwargs)

        self._print_report(
            stats,
            lines,
            verbose=options["verbose"],
            verbose_limit=options["limit"],
            apply_mode=apply_mode,
            confirmed=confirmed,
        )

        if options["fail_on_blockers"]:
            blockers = [f"{key}={stats[key]}" for key in _BLOCKER_KEYS if stats[key]]
            if blockers:
                raise CommandError(
                    "BibleStudyMeeting.small_group mirror cleanup blockers "
                    "present (--fail-on-blockers): " + ", ".join(blockers)
                )

    def _print_report(
        self,
        stats,
        lines,
        *,
        verbose,
        verbose_limit,
        apply_mode,
        confirmed,
    ):
        write = self.stdout.write
        data_mutated = bool(stats["cleared_small_group_mirror"])

        if apply_mode:
            write(
                "BibleStudyMeeting.small_group mirror cleanup "
                "(BS-V2-MIRROR.1C, APPLY mode)"
            )
        else:
            write(
                "BibleStudyMeeting.small_group mirror cleanup "
                "(BS-V2-MIRROR.1C, dry-run only)"
            )
        write("=" * 78)
        write(f"mode: {'apply' if apply_mode else 'dry-run'}")
        write(f"apply_option_present: {str(apply_mode).lower()}")
        write(f"confirmation_present: {str(confirmed).lower()}")
        for key in _STAT_KEYS:
            write(f"{key}: {stats[key]}")
        write(f"data_mutated: {str(data_mutated).lower()}")
        write("runtime_mutated: false")
        write("")
        if apply_mode:
            write(
                "Apply mode: cleared only safe BibleStudyMeeting.small_group "
                "mirrors; generation_key, anchor_unit, audience rows, V1 sessions, "
                "series mirrors, and runtime behavior were not changed."
            )
        else:
            write(
                "Dry-run only: no BibleStudyMeeting.small_group mirror, "
                "generation_key, anchor_unit, audience row, V1 session, series "
                "mirror, or runtime behavior changed."
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
