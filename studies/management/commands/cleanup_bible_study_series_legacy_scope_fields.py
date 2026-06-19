"""Guarded cleanup for existing BibleStudySeries legacy scope fields.

Dry-run is the default. Apply mode only clears the legacy
``scope_type`` / ``ministry_context`` / ``district`` / ``small_group`` fields
when the series already has valid structure-native audience rows. Generation
uses ``BibleStudySeriesAudienceScope`` rows, so clearing these stored legacy
fields does not change runtime generation or ordinary-member visibility.
"""

from dataclasses import dataclass

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Prefetch

from accounts.models import ChurchStructureUnit
from studies.models import BibleStudySeries, BibleStudySeriesAudienceScope


_STAT_KEYS = (
    "series_checked",
    "series_with_legacy_scope_fields",
    "series_without_legacy_scope_fields",
    "safe_to_clear_legacy_scope_fields",
    "would_clear_legacy_scope_fields",
    "cleared_legacy_scope_fields",
    "blocked_no_audience_rows",
    "blocked_inactive_audience_unit",
    "blocked_root_combined_with_other_units",
    "blocked_ancestor_descendant_units",
    "cleanup_blockers",
)

_BLOCKER_KEYS = (
    "blocked_no_audience_rows",
    "blocked_inactive_audience_unit",
    "blocked_root_combined_with_other_units",
    "blocked_ancestor_descendant_units",
)


@dataclass(frozen=True)
class CleanupPlan:
    series_id: int


@dataclass(frozen=True)
class DecisionLine:
    series_id: int
    title: str
    status: str
    scope_type: str
    ministry_context: str
    district: str
    small_group: str
    audience_units: str
    category: str
    reason: str


def _new_stats():
    return {key: 0 for key in _STAT_KEYS}


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


def _object_label(obj):
    if obj is None:
        return "(none)"
    return f"#{obj.id} {obj}"


def _has_legacy_scope_fields(series):
    return bool(
        series.scope_type != BibleStudySeries.SCOPE_GLOBAL
        or series.ministry_context_id
        or series.district_id
        or series.small_group_id
    )


def _audience_units(series):
    return [link.unit for link in series._prefetched_audience_links]


def _audience_units_label(units):
    if not units:
        return "(none)"
    return ", ".join(_unit_label(unit) for unit in units)


def _has_ancestor_descendant_pair(units):
    selected_ids = {unit.id for unit in units}
    for unit in units:
        ancestor_ids = {
            ancestor.id for ancestor in unit.get_ancestors() if ancestor.id is not None
        }
        if ancestor_ids & selected_ids:
            return True
    return False


def _decision_line(series, *, category, reason, units=None):
    if units is None:
        units = _audience_units(series)
    return DecisionLine(
        series_id=series.id,
        title=series.title,
        status=series.status,
        scope_type=series.scope_type,
        ministry_context=_object_label(series.ministry_context),
        district=_object_label(series.district),
        small_group=_object_label(series.small_group),
        audience_units=_audience_units_label(units),
        category=category,
        reason=reason,
    )


def _format_decision_line(line):
    return (
        f"  series #{line.series_id} | title {line.title!r} "
        f"| status: {line.status} | scope_type: {line.scope_type} "
        f"| ministry_context: {line.ministry_context} "
        f"| district: {line.district} | small_group: {line.small_group} "
        f"| audience_units: {line.audience_units} | category: {line.category} "
        f"| reason: {line.reason}"
    )


def _blocked(stats, key, series, reason, *, units=None):
    stats[key] += 1
    stats["cleanup_blockers"] += 1
    return (
        _decision_line(
            series,
            category="blocked",
            reason=f"{key}: {reason}",
            units=units,
        ),
        None,
    )


def _classify_series(series, stats, *, apply_mode):
    if not _has_legacy_scope_fields(series):
        stats["series_without_legacy_scope_fields"] += 1
        return (
            _decision_line(
                series,
                category="already_clear",
                reason="BibleStudySeries legacy scope fields are already clear",
            ),
            None,
        )

    stats["series_with_legacy_scope_fields"] += 1

    units = _audience_units(series)
    if not units:
        return _blocked(
            stats,
            "blocked_no_audience_rows",
            series,
            "series has populated legacy scope fields but no audience rows",
            units=units,
        )

    inactive_units = [unit for unit in units if not unit.is_active]
    if inactive_units:
        return _blocked(
            stats,
            "blocked_inactive_audience_unit",
            series,
            "one or more audience units are inactive",
            units=units,
        )

    root_units = [
        unit for unit in units if unit.unit_type == ChurchStructureUnit.UNIT_ROOT
    ]
    if root_units and len(units) > 1:
        return _blocked(
            stats,
            "blocked_root_combined_with_other_units",
            series,
            "whole-church root audience is combined with other units",
            units=units,
        )

    if _has_ancestor_descendant_pair(units):
        return _blocked(
            stats,
            "blocked_ancestor_descendant_units",
            series,
            "audience includes both an ancestor and descendant unit",
            units=units,
        )

    stats["safe_to_clear_legacy_scope_fields"] += 1
    if apply_mode:
        category = "cleared"
        reason = "safe series legacy scope cleanup applied"
    else:
        stats["would_clear_legacy_scope_fields"] += 1
        category = "would_clear"
        reason = "safe series legacy scope cleanup candidate"

    return (
        _decision_line(
            series,
            category=category,
            reason=reason,
            units=units,
        ),
        CleanupPlan(series_id=series.id),
    )


def _series_queryset(*, series_id=None, lock=False):
    links = BibleStudySeriesAudienceScope.objects.select_related("unit").order_by("id")
    series_rows = (
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
    if lock:
        series_rows = series_rows.select_for_update()
    if series_id is not None:
        series_rows = series_rows.filter(id=series_id)
    return series_rows


def _scan_series(*, series_id=None, lock=False, apply_mode=False):
    stats = _new_stats()
    lines = []
    plans = []
    for series in _series_queryset(series_id=series_id, lock=lock):
        stats["series_checked"] += 1
        line, plan = _classify_series(series, stats, apply_mode=apply_mode)
        lines.append(line)
        if plan is not None:
            plans.append(plan)
    return stats, lines, plans


def run_audit(*, series_id=None):
    stats, lines, _plans = _scan_series(series_id=series_id)
    return stats, lines


def apply_cleanup(*, series_id=None):
    with transaction.atomic():
        stats, lines, plans = _scan_series(
            series_id=series_id,
            lock=True,
            apply_mode=True,
        )
        for plan in plans:
            series = BibleStudySeries.objects.select_for_update().get(
                id=plan.series_id,
            )
            series.scope_type = BibleStudySeries.SCOPE_GLOBAL
            series.ministry_context = None
            series.district = None
            series.small_group = None
            series.save(
                update_fields=[
                    "scope_type",
                    "ministry_context",
                    "district",
                    "small_group",
                    "updated_at",
                ]
            )
            stats["cleared_legacy_scope_fields"] += 1
    return stats, lines


class Command(BaseCommand):
    help = (
        "Dry-run-first cleanup for existing BibleStudySeries legacy scope fields "
        "(BS-SERIES-SCOPE.1B). Apply mode clears only safe rows that already "
        "have valid BibleStudySeriesAudienceScope rows. It never changes "
        "audience rows, lessons, meetings, V1 sessions, visibility, Today, "
        "role/worship pickers, or other modules."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help=(
                "Actually clear safe BibleStudySeries legacy scope fields. "
                "Requires --confirm-series-legacy-scope-retirement."
            ),
        )
        parser.add_argument(
            "--confirm-series-legacy-scope-retirement",
            action="store_true",
            help="Required with --apply to confirm this series legacy-scope cleanup.",
        )
        parser.add_argument(
            "--series-id",
            type=int,
            default=None,
            help="Process only one BibleStudySeries id.",
        )
        parser.add_argument(
            "--verbose",
            action="store_true",
            help="Print per-series cleanup decisions.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help=(
                "Limit verbose printed decisions to N series. Does not limit "
                "scan/apply scope; use --series-id to narrow scope."
            ),
        )
        parser.add_argument(
            "--fail-on-blockers",
            action="store_true",
            help="Exit nonzero when any unsafe series legacy-scope cleanup blocker is present.",
        )

    def handle(self, *args, **options):
        if options["limit"] is not None and options["limit"] < 0:
            raise CommandError("--limit must be zero or greater.")

        apply_mode = options["apply"]
        confirmed = options["confirm_series_legacy_scope_retirement"]
        if apply_mode and not confirmed:
            raise CommandError(
                "--apply requires --confirm-series-legacy-scope-retirement; "
                "no BibleStudySeries legacy scope fields were cleared."
            )

        command_kwargs = {"series_id": options["series_id"]}
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
                    "BibleStudySeries legacy scope cleanup blockers present "
                    "(--fail-on-blockers): " + ", ".join(blockers)
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
        data_mutated = bool(stats["cleared_legacy_scope_fields"])

        if apply_mode:
            write(
                "BibleStudySeries legacy scope cleanup "
                "(BS-SERIES-SCOPE.1B, APPLY mode)"
            )
        else:
            write(
                "BibleStudySeries legacy scope cleanup "
                "(BS-SERIES-SCOPE.1B, dry-run only)"
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
                "Apply mode: cleared only safe BibleStudySeries legacy scope "
                "fields; audience rows, lessons, meetings, V1 sessions, "
                "visibility, Today, role/worship pickers, and other modules "
                "were not changed."
            )
        else:
            write(
                "Dry-run only: no BibleStudySeries legacy scope field, audience "
                "row, lesson, meeting, V1 session, visibility, Today, "
                "role/worship picker, or other module data changed."
            )

        if not verbose:
            return

        write("")
        write("per-series decisions:")
        if not lines:
            write("  (no series scanned)")
            return
        shown_lines = lines if verbose_limit is None else lines[:verbose_limit]
        for line in shown_lines:
            write(_format_decision_line(line))
        if verbose_limit is not None and len(lines) > len(shown_lines):
            remaining = len(lines) - len(shown_lines)
            write(
                f"  (stopped at --limit {verbose_limit}; "
                f"{remaining} more series decision(s) not printed)"
            )
