"""Read-only Bible Study generation bridge retirement inventory.

This command reports what still ties Bible Study V2 generation/idempotency,
display, admin, and diagnostics to legacy ``SmallGroup`` rows. It is strictly
read-only: no ``--apply``, no row writes, no runtime changes, and no schema
changes.
"""

from dataclasses import dataclass

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Prefetch

from accounts.models import ChurchStructureUnit
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
    "normal_series_still_using_legacy_scope_fields",
    "meetings_checked",
    "normal_meetings_checked",
    "normal_meetings_missing_anchor_unit",
    "meetings_with_generation_key",
    "meetings_missing_generation_key",
    "meetings_with_anchor_unit",
    "meetings_missing_anchor_unit",
    "meetings_with_audience_rows",
    "meetings_without_audience_rows",
    "meetings_with_small_group",
    "meetings_with_small_group_and_anchor_unit",
    "meetings_with_small_group_without_anchor_unit",
    "meetings_where_anchor_unit_matches_small_group_mapping",
    "meetings_where_anchor_unit_mismatches_small_group_mapping",
    "generation_paths_using_resolve_units_to_small_groups",
    "display_paths_using_small_group_fallback",
    "admin_paths_using_small_group",
    "cleanup_or_diagnostic_paths_using_small_group",
    "ordinary_visibility_paths_using_small_group",
    "candidate_paths_for_structure_unit_generation_switch",
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
    "generation target / idempotency bridge",
    "display fallback",
    "admin/emergency maintenance",
    "diagnostic/audit/backfill/cleanup support",
    "test fixture / migration history",
    "dead/stale",
)


@dataclass(frozen=True)
class ConsumerPath:
    category: str
    path: str
    reason: str
    uses_resolve_units_to_small_groups: bool = False
    candidate_for_generation_switch: bool = False


_CONSUMER_PATHS = (
    ConsumerPath(
        category="generation target / idempotency bridge",
        path="studies.services.GenerationTarget.small_group",
        reason=(
            "optional legacy mirror for warnings and old-row duplicate matching; "
            "new normal generation targets ChurchStructureUnit"
        ),
    ),
    ConsumerPath(
        category="generation target / idempotency bridge",
        path=(
            "studies.services.build_existing_normal_meeting_index / "
            "find_existing_meeting_for_target"
        ),
        reason=(
            "keeps pre-structure-native rows idempotent by matching existing "
            "meetings by legacy small_group when present"
        ),
    ),
    ConsumerPath(
        category="display fallback",
        path="studies.models.BibleStudyMeeting.get_structure_display_label",
        reason=(
            "falls back to BibleStudyMeeting.small_group only when anchor_unit "
            "and audience rows cannot produce a label"
        ),
    ),
    ConsumerPath(
        category="admin/emergency maintenance",
        path="studies.admin BibleStudyMeetingAdmin / inline search and filters",
        reason="Django Admin exposes stored legacy context for emergency maintenance.",
    ),
    ConsumerPath(
        category="diagnostic/audit/backfill/cleanup support",
        path=(
            "studies.models.resolve_units_to_small_groups / "
            "BibleStudySeries.get_eligible_small_groups"
        ),
        reason=(
            "legacy compatibility resolver retained for coexistence diagnostics "
            "and old fallback inspection; current normal generation no longer "
            "calls this as its target source"
        ),
        uses_resolve_units_to_small_groups=True,
    ),
    ConsumerPath(
        category="diagnostic/audit/backfill/cleanup support",
        path="studies.management.commands.backfill_bible_study_v2_generation_keys",
        reason="dry-run-first identity backfill inspects existing small_group mirrors.",
    ),
    ConsumerPath(
        category="diagnostic/audit/backfill/cleanup support",
        path="studies.management.commands.cleanup_bible_study_v2_small_group_mirrors",
        reason="guarded cleanup reads mirrors to prove they can be safely cleared.",
    ),
    ConsumerPath(
        category="diagnostic/audit/backfill/cleanup support",
        path="studies.management.commands.audit_bible_study_structure_retirement_readiness",
        reason="read-only readiness audit reports mirror/audience/anchor drift.",
    ),
    ConsumerPath(
        category="test fixture / migration history",
        path="studies tests and historical migrations",
        reason=(
            "fixtures intentionally create legacy rows to protect old-row "
            "compatibility and migration history"
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
    small_group: str
    mapped_unit: str
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


def _group_label(group):
    if group is None:
        return "(none)"
    return f"#{group.id} {group.name}"


def _clean_generation_key(value):
    return (value or "").strip()


def _series_has_legacy_scope_fields(series):
    return bool(
        series.scope_type != BibleStudySeries.SCOPE_GLOBAL
        or series.ministry_context_id
        or series.district_id
        or series.small_group_id
    )


def _series_is_active_for_generation(series):
    return bool(
        series.is_active
        and series.status
        in {
            BibleStudySeries.STATUS_DRAFT,
            BibleStudySeries.STATUS_PUBLISHED,
        }
    )


def _small_group_mapping_state(group):
    if group is None:
        return None, "none"
    unit = group.church_structure_unit
    if unit is None:
        return None, "unmapped"
    if not unit.is_active:
        return unit, "inactive"
    if unit.unit_type != ChurchStructureUnit.UNIT_SMALL_GROUP:
        return unit, "wrong_type"
    return unit, "ok"


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
        small_group=_group_label(series.small_group),
        mapped_unit="(n/a)",
        category=category,
        decision=decision,
        reason=reason,
    )


def _meeting_line(meeting, *, category, decision, reason, mapped_unit=None):
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
        small_group=_group_label(meeting.small_group),
        mapped_unit=_unit_label(mapped_unit),
        category=category,
        decision=decision,
        reason=reason,
    )


def _format_decision_line(line):
    return (
        f"  {line.object_type} #{line.object_id} | title: {line.title!r} "
        f"| date: {line.meeting_date} | status: {line.status} "
        f"| generation_key: {line.generation_key} | anchor_unit: {line.anchor_unit} "
        f"| small_group: {line.small_group} | mapped_unit: {line.mapped_unit} "
        f"| category: {line.category} | decision: {line.decision} "
        f"| reason: {line.reason}"
    )


def _consumer_category_counts():
    counts = {category: 0 for category in _CLASSIFICATION_CATEGORIES}
    for path in _CONSUMER_PATHS:
        counts[path.category] += 1
    return counts


def _apply_static_path_counts(stats):
    stats["generation_paths_using_resolve_units_to_small_groups"] = sum(
        1
        for path in _CONSUMER_PATHS
        if path.category == "generation target / idempotency bridge"
        and path.uses_resolve_units_to_small_groups
    )
    stats["display_paths_using_small_group_fallback"] = sum(
        1 for path in _CONSUMER_PATHS if path.category == "display fallback"
    )
    stats["admin_paths_using_small_group"] = sum(
        1 for path in _CONSUMER_PATHS if path.category == "admin/emergency maintenance"
    )
    stats["cleanup_or_diagnostic_paths_using_small_group"] = sum(
        1
        for path in _CONSUMER_PATHS
        if path.category == "diagnostic/audit/backfill/cleanup support"
    )
    stats["ordinary_visibility_paths_using_small_group"] = sum(
        1 for path in _CONSUMER_PATHS if path.category == "ordinary runtime visibility"
    )
    stats["candidate_paths_for_structure_unit_generation_switch"] = sum(
        1 for path in _CONSUMER_PATHS if path.candidate_for_generation_switch
    )


def _series_queryset():
    links = BibleStudySeriesAudienceScope.objects.select_related("unit").order_by("id")
    return (
        BibleStudySeries.objects.select_related(
            "ministry_context",
            "district",
            "small_group",
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


def _meeting_queryset():
    links = BibleStudyMeetingAudienceScope.objects.select_related("unit").order_by("id")
    return (
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


def _classify_series(series, stats):
    stats["series_checked"] += 1
    audience_links = list(series._prefetched_audience_links)
    if audience_links:
        stats["series_with_audience_rows"] += 1
        stats["normal_series_with_structure_audience"] += 1
        if not _series_has_legacy_scope_fields(series):
            return _series_line(
                series,
                category="generation target / idempotency bridge",
                decision="structure_audience_ready",
                reason=(
                    "series has structure audience rows; normal generation "
                    "resolves ChurchStructureUnit leaf targets"
                ),
            )
    else:
        stats["series_without_audience_rows"] += 1
        if _series_is_active_for_generation(series):
            stats["active_series_without_audience_rows"] += 1
            return _series_line(
                series,
                category="generation target / idempotency bridge",
                decision="blocker",
                reason=(
                    "active draft/published series has no "
                    "BibleStudySeriesAudienceScope rows"
                ),
            )

    if _series_has_legacy_scope_fields(series):
        stats["normal_series_still_using_legacy_scope_fields"] += 1
        return _series_line(
            series,
            category="diagnostic/audit/backfill/cleanup support",
            decision="legacy_scope_field_retained",
            reason=(
                "series still stores legacy scope fields; cleanup is a separate "
                "dry-run-first slice"
            ),
        )

    return _series_line(
        series,
        category="diagnostic/audit/backfill/cleanup support",
        decision="no_series_bridge_blocker",
        reason="series has no stored legacy scope fields requiring this bridge",
    )


def _classify_meeting(meeting, stats):
    stats["meetings_checked"] += 1
    if meeting.meeting_kind == BibleStudyMeeting.KIND_NORMAL:
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
        if meeting.meeting_kind == BibleStudyMeeting.KIND_NORMAL:
            stats["normal_meetings_missing_anchor_unit"] += 1

    audience_links = list(meeting._prefetched_audience_links)
    if audience_links:
        stats["meetings_with_audience_rows"] += 1
    else:
        stats["meetings_without_audience_rows"] += 1

    mapped_unit, mapping_state = _small_group_mapping_state(meeting.small_group)
    if meeting.small_group_id:
        stats["meetings_with_small_group"] += 1
        if meeting.anchor_unit_id:
            stats["meetings_with_small_group_and_anchor_unit"] += 1
        else:
            stats["meetings_with_small_group_without_anchor_unit"] += 1
            return _meeting_line(
                meeting,
                category="generation target / idempotency bridge",
                decision="blocker",
                reason=(
                    "legacy small_group mirror exists but anchor_unit is missing"
                ),
                mapped_unit=mapped_unit,
            )

        if mapping_state == "ok" and meeting.anchor_unit_id == mapped_unit.id:
            stats["meetings_where_anchor_unit_matches_small_group_mapping"] += 1
            return _meeting_line(
                meeting,
                category="generation target / idempotency bridge",
                decision="display_idempotency_compatibility",
                reason=(
                    "legacy mirror maps to anchor_unit; mirror is compatibility "
                    "data, not ordinary visibility"
                ),
                mapped_unit=mapped_unit,
            )

        if mapping_state != "none":
            stats["meetings_where_anchor_unit_mismatches_small_group_mapping"] += 1
            return _meeting_line(
                meeting,
                category="generation target / idempotency bridge",
                decision="blocker",
                reason=(
                    "legacy mirror mapping is missing, inactive, wrong-type, or "
                    "does not match anchor_unit"
                ),
                mapped_unit=mapped_unit,
            )

    if (
        meeting.meeting_kind == BibleStudyMeeting.KIND_NORMAL
        and current_key
        and meeting.anchor_unit_id
        and audience_links
        and not meeting.small_group_id
        and current_key.startswith(NORMAL_GENERATION_KEY_PREFIX)
    ):
        expected_key = normal_generation_key_for_unit(meeting.anchor_unit)
        if current_key == expected_key:
            return _meeting_line(
                meeting,
                category="generation target / idempotency bridge",
                decision="structure_native",
                reason=(
                    "normal meeting has generation_key, anchor_unit, audience "
                    "rows, and no legacy small_group mirror"
                ),
                mapped_unit=mapped_unit,
            )

    return _meeting_line(
        meeting,
        category="diagnostic/audit/backfill/cleanup support",
        decision="review",
        reason="meeting is retained for audit/backfill/display review",
        mapped_unit=mapped_unit,
    )


def _finalize_blockers(stats):
    stats["blockers_for_small_group_table_retirement"] = (
        stats["active_series_without_audience_rows"]
        + stats["normal_series_still_using_legacy_scope_fields"]
        + stats["meetings_with_small_group"]
        + stats["meetings_missing_generation_key"]
        + stats["normal_meetings_missing_anchor_unit"]
        + stats["meetings_where_anchor_unit_mismatches_small_group_mapping"]
    )


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
        "Inventories remaining SmallGroup bridge dependencies without changing "
        "data, schema, or runtime behavior."
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
                "Exit nonzero when data blockers for legacy SmallGroup table "
                "retirement are present. Still read-only."
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
            "audience-row + membership-core. Normal generation is already "
            "structure-unit-native; remaining legacy SmallGroup dependencies are "
            "old-row idempotency, stored mirrors, fallback display, admin, and "
            "diagnostic/cleanup support. No deletion/removal is approved here."
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
