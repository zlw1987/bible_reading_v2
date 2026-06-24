"""Read-only Bible Study generation bridge retirement inventory.

This command reports post-retirement Bible Study V2 generation/idempotency
readiness after the legacy ``SmallGroup`` table bridge was retired.
BS-MEETING-MIRROR.1A removed the legacy
``BibleStudyMeeting.small_group`` mirror field and
BS-SMALLGROUP-GENERATION-BRIDGE-RETIRE.1A retired the normal-generation bridge,
so normal V2 generation is structure-native. Remaining Bible Study blockers are
series audience-row coverage and structure-native generation-key / anchor
readiness, not legacy object-table access.

It is strictly read-only: no ``--apply``, no row writes, no runtime changes, and
no schema changes.
"""

from dataclasses import dataclass

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Prefetch

from studies.models import (
    BibleStudyMeeting,
    BibleStudyMeetingAudienceScope,
    BibleStudySeries,
    BibleStudySeriesAudienceScope,
)
from studies.services import NORMAL_GENERATION_KEY_PREFIX, normal_generation_key_for_unit


_STAT_KEYS = (
    "series_checked",
    "series_with_audience_rows",
    "series_without_audience_rows",
    "active_series_without_audience_rows",
    "normal_series_with_structure_audience",
    "meetings_checked",
    "normal_meetings_checked",
    "normal_meetings_missing_anchor_unit",
    "meetings_with_generation_key",
    "meetings_missing_generation_key",
    "meetings_with_anchor_unit",
    "meetings_missing_anchor_unit",
    "meetings_with_audience_rows",
    "meetings_without_audience_rows",
    "normal_meetings_without_audience_rows",
    "diagnostic_paths_using_small_group_table",
    "ordinary_visibility_paths_using_small_group",
    "structure_native_generation_readiness_blockers",
    "blockers_for_small_group_table_retirement",
)

_BOOLEAN_FLAGS = (
    "runtime_mutated",
    "data_mutated",
    "schema_mutated",
    "apply_option_present",
)

_CLASSIFICATION_CATEGORIES = (
    "ordinary runtime visibility",
    "structure-native generation / idempotency",
    "diagnostic/audit/backfill/cleanup support",
    "test fixture / migration history",
    "dead/stale",
)


@dataclass(frozen=True)
class ConsumerPath:
    category: str
    path: str
    reason: str


# Historical references after BS-MEETING-MIRROR.1A removed the
# ``BibleStudyMeeting.small_group`` mirror and LEGACY-STRUCTURE-TABLE-RETIRE.1A
# removes the legacy object table.
_CONSUMER_PATHS = (
    ConsumerPath(
        category="test fixture / migration history",
        path="studies tests and historical migrations",
        reason=(
            "immutable migrations still name the removed BibleStudyMeeting.small_group "
            "field and legacy object table"
        ),
    ),
)


@dataclass(frozen=True)
class DecisionLine:
    object_type: str
    object_id: int
    title: str
    status: str
    meeting_date: str
    generation_key: str
    anchor_unit: str
    category: str
    decision: str
    reason: str


def _new_stats():
    stats = {key: 0 for key in _STAT_KEYS}
    for key in _BOOLEAN_FLAGS:
        stats[key] = False
    return stats


def _unit_label(unit):
    if unit is None:
        return "(none)"
    label = f"#{unit.id} {unit.code or '(no-code)'}"
    if getattr(unit, "unit_type", ""):
        label = f"{label} type={unit.unit_type}"
    name = getattr(unit, "name_en", "") or getattr(unit, "name", "")
    if name:
        label = f"{label} {name}"
    return label


def _clean_generation_key(value):
    return (value or "").strip()


def _series_is_active_for_generation(series):
    return bool(
        series.is_active
        and series.status
        in {
            BibleStudySeries.STATUS_DRAFT,
            BibleStudySeries.STATUS_PUBLISHED,
        }
    )


def _series_line(series, *, category, decision, reason):
    units = [link.unit for link in series._prefetched_audience_links]
    return DecisionLine(
        object_type="series",
        object_id=series.id,
        title=series.title,
        status=series.status,
        meeting_date="(n/a)",
        generation_key="(n/a)",
        anchor_unit=", ".join(_unit_label(unit) for unit in units) or "(none)",
        category=category,
        decision=decision,
        reason=reason,
    )


def _meeting_line(meeting, *, category, decision, reason):
    return DecisionLine(
        object_type="meeting",
        object_id=meeting.id,
        title=meeting.lesson.title if meeting.lesson_id else "",
        status=meeting.status,
        meeting_date=(
            meeting.meeting_datetime.date().isoformat()
            if meeting.meeting_datetime
            else "(none)"
        ),
        generation_key=_clean_generation_key(meeting.generation_key) or "(blank)",
        anchor_unit=_unit_label(meeting.anchor_unit),
        category=category,
        decision=decision,
        reason=reason,
    )


def _format_decision_line(line):
    return (
        f"  {line.object_type} #{line.object_id} | title: {line.title!r} "
        f"| date: {line.meeting_date} | status: {line.status} "
        f"| generation_key: {line.generation_key} | anchor_unit: {line.anchor_unit} "
        f"| category: {line.category} | decision: {line.decision} "
        f"| reason: {line.reason}"
    )


def _consumer_category_counts():
    counts = {category: 0 for category in _CLASSIFICATION_CATEGORIES}
    for path in _CONSUMER_PATHS:
        counts[path.category] += 1
    return counts


def _apply_static_path_counts(stats):
    stats["diagnostic_paths_using_small_group_table"] = sum(
        1
        for path in _CONSUMER_PATHS
        if path.category == "diagnostic/audit/backfill/cleanup support"
    )
    stats["ordinary_visibility_paths_using_small_group"] = sum(
        1 for path in _CONSUMER_PATHS if path.category == "ordinary runtime visibility"
    )


def _series_queryset():
    links = BibleStudySeriesAudienceScope.objects.select_related("unit").order_by("id")
    return (
        BibleStudySeries.objects
        .prefetch_related(
            Prefetch(
                "audience_scope_links",
                queryset=links,
                to_attr="_prefetched_audience_links",
            )
        )
        .order_by("id")
    )


def _meeting_queryset():
    links = BibleStudyMeetingAudienceScope.objects.select_related("unit").order_by("id")
    return (
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


def _classify_series(series, stats):
    stats["series_checked"] += 1
    audience_links = list(series._prefetched_audience_links)
    if audience_links:
        stats["series_with_audience_rows"] += 1
        stats["normal_series_with_structure_audience"] += 1
        return _series_line(
            series,
            category="structure-native generation / idempotency",
            decision="structure_audience_ready",
            reason=(
                "series has structure audience rows; normal generation "
                "resolves ChurchStructureUnit leaf targets"
            ),
        )

    stats["series_without_audience_rows"] += 1
    if _series_is_active_for_generation(series):
        stats["active_series_without_audience_rows"] += 1
        return _series_line(
            series,
            category="structure-native generation / idempotency",
            decision="blocker",
            reason=(
                "active draft/published series has no "
                "BibleStudySeriesAudienceScope rows"
            ),
        )

    return _series_line(
        series,
        category="diagnostic/audit/backfill/cleanup support",
        decision="inactive_series_without_audience_rows",
        reason="inactive/cancelled series has no audience rows and is not a generation target",
    )


def _classify_meeting(meeting, stats):
    stats["meetings_checked"] += 1
    is_normal = meeting.meeting_kind == BibleStudyMeeting.KIND_NORMAL
    if is_normal:
        stats["normal_meetings_checked"] += 1

    current_key = _clean_generation_key(meeting.generation_key)
    if current_key:
        stats["meetings_with_generation_key"] += 1
    else:
        stats["meetings_missing_generation_key"] += 1

    if meeting.anchor_unit_id:
        stats["meetings_with_anchor_unit"] += 1
    else:
        stats["meetings_missing_anchor_unit"] += 1
        if is_normal:
            stats["normal_meetings_missing_anchor_unit"] += 1

    audience_links = list(meeting._prefetched_audience_links)
    if audience_links:
        stats["meetings_with_audience_rows"] += 1
    else:
        stats["meetings_without_audience_rows"] += 1
        if is_normal:
            stats["normal_meetings_without_audience_rows"] += 1

    if is_normal and (not current_key or not meeting.anchor_unit_id or not audience_links):
        return _meeting_line(
            meeting,
            category="structure-native generation / idempotency",
            decision="blocker",
            reason=(
                "normal meeting is missing generation_key, anchor_unit, or "
                "audience rows"
            ),
        )

    if (
        is_normal
        and current_key
        and meeting.anchor_unit_id
        and audience_links
        and current_key.startswith(NORMAL_GENERATION_KEY_PREFIX)
        and current_key == normal_generation_key_for_unit(meeting.anchor_unit)
    ):
        return _meeting_line(
            meeting,
            category="structure-native generation / idempotency",
            decision="structure_native",
            reason=(
                "normal meeting has generation_key, anchor_unit, and audience rows"
            ),
        )

    return _meeting_line(
        meeting,
        category="diagnostic/audit/backfill/cleanup support",
        decision="review",
        reason="meeting is retained for audit/display review",
    )


def _finalize_blockers(stats):
    stats["structure_native_generation_readiness_blockers"] = (
        stats["active_series_without_audience_rows"]
        + stats["normal_meetings_without_audience_rows"]
        + stats["meetings_missing_generation_key"]
        + stats["normal_meetings_missing_anchor_unit"]
    )
    stats["blockers_for_small_group_table_retirement"] = 0


def run_audit():
    stats = _new_stats()
    lines = []
    _apply_static_path_counts(stats)

    for series in _series_queryset():
        lines.append(_classify_series(series, stats))

    for meeting in _meeting_queryset():
        lines.append(_classify_meeting(meeting, stats))

    _finalize_blockers(stats)
    return stats, lines, _consumer_category_counts()


def _blockers_present(stats):
    return bool(stats["blockers_for_small_group_table_retirement"])


class Command(BaseCommand):
    help = (
        "Read-only Bible Study generation/idempotency bridge retirement audit. "
        "Inventories structure-native generation readiness and remaining non-V2 "
        "SmallGroup table dependencies without changing data, schema, or runtime "
        "behavior."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--verbose",
            action="store_true",
            help="Print capped per-series/per-meeting decisions and path inventory.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help=(
                "Limit verbose printed examples to N decisions. Does not limit "
                "scan scope."
            ),
        )
        parser.add_argument(
            "--fail-on-blockers",
            action="store_true",
            help=(
                "Exit nonzero when Bible Study generation-readiness blockers for "
                "legacy SmallGroup table retirement are present. Still read-only."
            ),
        )

    def handle(self, *args, **options):
        if options["limit"] is not None and options["limit"] < 0:
            raise CommandError("--limit must be zero or greater.")

        stats, lines, category_counts = run_audit()
        self._print_report(
            stats,
            lines,
            category_counts,
            verbose=options["verbose"],
            verbose_limit=options["limit"],
        )

        if options["fail_on_blockers"] and _blockers_present(stats):
            raise CommandError(
                "Bible Study generation bridge retirement blockers present "
                "(--fail-on-blockers): "
                f"blockers_for_small_group_table_retirement="
                f"{stats['blockers_for_small_group_table_retirement']}"
            )

    def _print_report(
        self,
        stats,
        lines,
        category_counts,
        *,
        verbose,
        verbose_limit,
    ):
        write = self.stdout.write
        write("Bible Study generation bridge retirement audit (read-only)")
        write("=" * 78)
        for key in _STAT_KEYS:
            write(f"{key}: {stats[key]}")
        for key in _BOOLEAN_FLAGS:
            write(f"{key}: {str(stats[key]).lower()}")
        write("")
        write("classification_counts:")
        for category in _CLASSIFICATION_CATEGORIES:
            write(f"  {category}: {category_counts[category]}")
        write("")
        write(
            "Recommendation: ordinary Bible Study V2 visibility is already "
            "audience-row + membership-core, and BS-MEETING-MIRROR.1A removed the "
            "legacy BibleStudyMeeting.small_group mirror. Remaining Bible Study "
            "readiness work is series audience-row coverage and structure-native "
            "generation-key / anchor readiness; this is not a SmallGroup table "
            "retirement blocker. LEGACY-STRUCTURE-TABLE-RETIRE.1A removes the "
            "legacy object table behind its own migration guard."
        )
        write(
            "Audit only: no series, meeting, audience row, SmallGroup, unit, "
            "membership, runtime behavior, schema, or local/dev data was changed."
        )

        if not verbose:
            return

        write("")
        write("consumer inventory:")
        for path in _CONSUMER_PATHS:
            write(f"  {path.category}: {path.path} | {path.reason}")

        write("")
        write("per-row decisions:")
        if not lines:
            write("  (no series or meetings scanned)")
            return
        shown_lines = lines if verbose_limit is None else lines[:verbose_limit]
        for line in shown_lines:
            write(_format_decision_line(line))
        if verbose_limit is not None and len(lines) > len(shown_lines):
            remaining = len(lines) - len(shown_lines)
            write(
                f"  (stopped at --limit {verbose_limit}; "
                f"{remaining} more decision(s) not printed)"
            )
