"""Guarded cleanup for existing ServiceEvent.ministry_context display links.

SE-CTX.1A. ``ServiceEvent.ministry_context`` is a display-only host/language
label, not audience authority. The structure-native display fallback
(``event_host_language_label`` / ``events.ministry_context_display``) derives an
equivalent label from the event's ``ServiceEventAudienceScope`` rows. This
command clears the legacy FK only where that fallback derives the *same*
ministry-context unit, so the displayed host/language label is preserved (apart
from the accepted wording shift from the legacy context object name to the
equivalent structure-unit label).

Dry-run is the default. Apply mode requires BOTH ``--apply`` and
``--confirm-service-event-ministry-context-label-cleanup``. The only field this
command may mutate is ``ServiceEvent.ministry_context`` (set to ``None``). It
never changes audience rows, audience visibility, ChurchStructureUnit,
memberships, legacy structure rows, MinistryContext rows, Bible Study,
reflections, roles, serving assignments, permissions, reading progress, or any
schema. It does not remove the model field and does not delete MinistryContext
rows.
"""

from dataclasses import dataclass
from datetime import datetime

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Count
from django.utils import timezone

from accounts.models import ChurchStructureUnit
from events.ministry_context_display import derive_ministry_context_units
from events.models import ServiceEvent, ServiceEventAudienceScope


_STAT_KEYS = (
    "service_events_checked",
    "links_present",
    "events_with_audience_rows",
    "events_without_audience_rows",
    "eligible_to_clear",
    "would_clear_count",
    "cleared_count",
    "skipped_zero_audience_rows",
    "skipped_missing_mapped_context_unit",
    "skipped_inactive_mapped_context_unit",
    "skipped_wrong_mapped_context_unit_type",
    "skipped_no_derived_context",
    "skipped_context_mismatch",
    "skipped_multiple_derived_contexts",
    "skipped_uncertain_display_behavior",
    "remaining_service_event_ministry_context_links_after_operation",
)


@dataclass(frozen=True)
class CleanupPlan:
    event_id: int


@dataclass(frozen=True)
class DecisionLine:
    event_id: int
    title: str
    status: str
    start: str
    current_context: str
    mapped_unit: str
    derived_unit: str
    audience_units: str
    category: str
    reason: str


def _new_stats():
    return {key: 0 for key in _STAT_KEYS}


def _start_label(event):
    value = getattr(event, "start_datetime", None)
    if not value:
        return ""
    if isinstance(value, datetime) and timezone.is_aware(value):
        value = timezone.localtime(value)
    return value.strftime("%Y-%m-%d %H:%M %Z").strip()


def _context_label(context):
    if context is None:
        return "(none)"
    return f"#{context.id} {context.code} {context.name}".strip()


def _unit_label(unit):
    if unit is None:
        return "(none)"
    return f"#{unit.id} {unit.code} ({unit.unit_type})"


def _audience_units_label(units):
    if not units:
        return "(none)"
    return ", ".join(
        f"#{unit.id} {unit.code} ({unit.unit_type})" for unit in units
    )


def _format_decision_line(line):
    start = line.start or "(none)"
    return (
        f"  event #{line.event_id} | title: {line.title!r} | status: {line.status} "
        f"| start: {start} | current ministry_context: {line.current_context} "
        f"| mapped unit: {line.mapped_unit} | derived unit: {line.derived_unit} "
        f"| audience units: {line.audience_units} | decision: {line.category} "
        f"| reason: {line.reason}"
    )


def _event_queryset(*, lock=False):
    rows = (
        ServiceEvent.objects.select_related(
            "ministry_context",
            "ministry_context__church_structure_unit",
        )
        .prefetch_related("audience_scope_links__unit")
        .order_by("id")
    )
    if lock:
        rows = rows.select_for_update()
    return rows


def _audience_counts():
    return dict(
        ServiceEventAudienceScope.objects.values("service_event_id")
        .annotate(row_count=Count("id"))
        .values_list("service_event_id", "row_count")
    )


def _decision_line(event, *, audience_units, derived_unit, category, reason):
    mapped_unit = (
        event.ministry_context.church_structure_unit
        if event.ministry_context_id
        else None
    )
    return DecisionLine(
        event_id=event.id,
        title=event.title,
        status=event.status,
        start=_start_label(event),
        current_context=_context_label(event.ministry_context),
        mapped_unit=_unit_label(mapped_unit),
        derived_unit=_unit_label(derived_unit),
        audience_units=_audience_units_label(audience_units),
        category=category,
        reason=reason,
    )


def _classify_event(event, stats, *, audience_row_count, apply_mode):
    """Classify one candidate event (ministry_context is set)."""
    audience_units = [link.unit for link in event.audience_scope_links.all()]

    if audience_row_count < 1:
        stats["skipped_zero_audience_rows"] += 1
        return (
            _decision_line(
                event,
                audience_units=audience_units,
                derived_unit=None,
                category="skipped_zero_audience_rows",
                reason="candidate has a ministry_context link but no audience rows",
            ),
            None,
        )

    mapped_unit = event.ministry_context.church_structure_unit
    if mapped_unit is None:
        stats["skipped_missing_mapped_context_unit"] += 1
        return (
            _decision_line(
                event,
                audience_units=audience_units,
                derived_unit=None,
                category="skipped_missing_mapped_context_unit",
                reason="ministry_context has no mapped church_structure_unit",
            ),
            None,
        )

    if not mapped_unit.is_active:
        stats["skipped_inactive_mapped_context_unit"] += 1
        return (
            _decision_line(
                event,
                audience_units=audience_units,
                derived_unit=None,
                category="skipped_inactive_mapped_context_unit",
                reason="mapped ministry-context unit is inactive",
            ),
            None,
        )

    if mapped_unit.unit_type != ChurchStructureUnit.UNIT_MINISTRY_CONTEXT:
        stats["skipped_wrong_mapped_context_unit_type"] += 1
        return (
            _decision_line(
                event,
                audience_units=audience_units,
                derived_unit=None,
                category="skipped_wrong_mapped_context_unit_type",
                reason="mapped unit is not a ministry_context unit",
            ),
            None,
        )

    derived = derive_ministry_context_units(audience_units)
    if len(derived) == 0:
        stats["skipped_no_derived_context"] += 1
        return (
            _decision_line(
                event,
                audience_units=audience_units,
                derived_unit=None,
                category="skipped_no_derived_context",
                reason="audience rows derive no ministry-context unit",
            ),
            None,
        )

    if len(derived) > 1:
        stats["skipped_multiple_derived_contexts"] += 1
        return (
            _decision_line(
                event,
                audience_units=audience_units,
                derived_unit=None,
                category="skipped_multiple_derived_contexts",
                reason="audience rows derive multiple ministry-context units",
            ),
            None,
        )

    derived_unit = derived[0]
    if derived_unit.id != mapped_unit.id:
        stats["skipped_context_mismatch"] += 1
        return (
            _decision_line(
                event,
                audience_units=audience_units,
                derived_unit=derived_unit,
                category="skipped_context_mismatch",
                reason="derived ministry-context unit differs from mapped unit",
            ),
            None,
        )

    # Eligible: the structure-native fallback derives the same ministry-context
    # unit, so the displayed host/language label is preserved.
    stats["eligible_to_clear"] += 1
    if apply_mode:
        category = "cleared"
        reason = "safe ministry_context label cleanup applied"
    else:
        stats["would_clear_count"] += 1
        category = "would_clear"
        reason = "safe ministry_context label cleanup candidate"

    return (
        _decision_line(
            event,
            audience_units=audience_units,
            derived_unit=derived_unit,
            category=category,
            reason=reason,
        ),
        CleanupPlan(event_id=event.id),
    )


def _scan_events(*, lock=False, apply_mode=False):
    stats = _new_stats()
    lines = []
    plans = []
    counts = _audience_counts()

    for event in _event_queryset(lock=lock):
        stats["service_events_checked"] += 1
        audience_row_count = counts.get(event.id, 0)
        if audience_row_count > 0:
            stats["events_with_audience_rows"] += 1
        else:
            stats["events_without_audience_rows"] += 1

        if not event.ministry_context_id:
            continue

        stats["links_present"] += 1
        line, plan = _classify_event(
            event,
            stats,
            audience_row_count=audience_row_count,
            apply_mode=apply_mode,
        )
        lines.append(line)
        if plan is not None:
            plans.append(plan)

    return stats, lines, plans


def _set_remaining_links(stats, *, apply_mode):
    if apply_mode:
        remaining = stats["links_present"] - stats["cleared_count"]
    else:
        remaining = stats["links_present"]
    stats["remaining_service_event_ministry_context_links_after_operation"] = remaining


def run_audit():
    stats, lines, _plans = _scan_events()
    _set_remaining_links(stats, apply_mode=False)
    return stats, lines


def apply_cleanup():
    with transaction.atomic():
        stats, lines, plans = _scan_events(lock=True, apply_mode=True)
        for plan in plans:
            updated = ServiceEvent.objects.filter(id=plan.event_id).update(
                ministry_context=None,
            )
            if updated:
                stats["cleared_count"] += 1
        _set_remaining_links(stats, apply_mode=True)
    return stats, lines


class Command(BaseCommand):
    help = (
        "Dry-run-first cleanup for existing ServiceEvent.ministry_context "
        "display links (SE-CTX.1A). Apply mode clears only ServiceEvent rows "
        "where the structure-native host/language fallback derives the same "
        "ministry-context unit, preserving the displayed label. It never "
        "changes audience rows, audience visibility, ChurchStructureUnit, "
        "memberships, MinistryContext rows, legacy structure rows, Bible "
        "Study, reflections, roles, serving assignments, permissions, reading "
        "progress, or schema. It does not remove the field or delete "
        "MinistryContext rows."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help=(
                "Actually clear safe ServiceEvent.ministry_context links. "
                "Requires --confirm-service-event-ministry-context-label-cleanup."
            ),
        )
        parser.add_argument(
            "--confirm-service-event-ministry-context-label-cleanup",
            action="store_true",
            help="Required with --apply to confirm this ministry_context cleanup.",
        )
        parser.add_argument(
            "--verbose",
            action="store_true",
            help="Print per-event cleanup decisions (non-sensitive metadata only).",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help=(
                "Limit verbose printed decisions to N events. Does not limit "
                "scan/apply scope."
            ),
        )
        parser.add_argument(
            "--fail-on-blockers",
            action="store_true",
            help="Exit nonzero when any skip/blocker categories are present.",
        )

    def handle(self, *args, **options):
        if options["limit"] is not None and options["limit"] < 0:
            raise CommandError("--limit must be zero or greater.")

        apply_mode = options["apply"]
        confirmed = options[
            "confirm_service_event_ministry_context_label_cleanup"
        ]
        if apply_mode and not confirmed:
            raise CommandError(
                "--apply requires "
                "--confirm-service-event-ministry-context-label-cleanup; "
                "no ServiceEvent.ministry_context links were cleared."
            )

        if apply_mode:
            stats, lines = apply_cleanup()
        else:
            stats, lines = run_audit()

        self._print_report(
            stats,
            lines,
            verbose=options["verbose"],
            verbose_limit=options["limit"],
            apply_mode=apply_mode,
            confirmed=confirmed,
        )

        blocker_total = (
            stats["skipped_zero_audience_rows"]
            + stats["skipped_missing_mapped_context_unit"]
            + stats["skipped_inactive_mapped_context_unit"]
            + stats["skipped_wrong_mapped_context_unit_type"]
            + stats["skipped_no_derived_context"]
            + stats["skipped_context_mismatch"]
            + stats["skipped_multiple_derived_contexts"]
            + stats["skipped_uncertain_display_behavior"]
        )
        if options["fail_on_blockers"] and blocker_total:
            raise CommandError(
                "ServiceEvent ministry_context label cleanup skip categories "
                f"present (--fail-on-blockers): total={blocker_total}"
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
        data_mutated = bool(stats["cleared_count"])

        if apply_mode:
            write(
                "ServiceEvent ministry_context label cleanup "
                "(SE-CTX.1A, APPLY mode)"
            )
        else:
            write(
                "ServiceEvent ministry_context label cleanup "
                "(SE-CTX.1A, dry-run only)"
            )
        write("=" * 78)
        write(f"mode: {'apply' if apply_mode else 'dry-run'}")
        write(f"apply_option_present: {str(apply_mode).lower()}")
        write(f"confirmation_option_present: {str(confirmed).lower()}")
        for key in _STAT_KEYS:
            if key == "cleared_count" and not apply_mode:
                continue
            write(f"{key}: {stats[key]}")
        write(f"data_mutated: {str(data_mutated).lower()}")
        # Runtime label/template behavior is unchanged by running this command:
        # the structure-native fallback already renders the same host/language
        # label whether or not the legacy FK is set.
        write("runtime_mutated: false")
        write("schema_mutated: false")
        write("")
        if apply_mode:
            write(
                "Apply mode: cleared only ServiceEvent.ministry_context for safe "
                "rows whose structure-native host/language fallback derives the "
                "same ministry-context unit. Audience rows, audience visibility, "
                "ChurchStructureUnit, MinistryContext rows, memberships, legacy "
                "structure rows, serving assignments, and all other modules were "
                "not changed."
            )
        else:
            write(
                "Dry-run only: no ServiceEvent.ministry_context link, audience "
                "row, MinistryContext row, ChurchStructureUnit, membership, "
                "legacy structure row, serving assignment, other module, "
                "runtime, or schema data changed."
            )

        if not verbose:
            return

        write("")
        write("per-event decisions (non-sensitive metadata only):")
        if not lines:
            write("  (no candidate events with ministry_context links)")
            return
        shown_lines = lines if verbose_limit is None else lines[:verbose_limit]
        for line in shown_lines:
            write(_format_decision_line(line))
        if verbose_limit is not None and len(lines) > len(shown_lines):
            remaining = len(lines) - len(shown_lines)
            write(
                f"  (stopped at --limit {verbose_limit}; "
                f"{remaining} more event decision(s) not printed)"
            )
