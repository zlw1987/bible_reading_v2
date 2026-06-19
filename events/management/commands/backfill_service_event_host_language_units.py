"""Backfill ServiceEvent.host_language_unit from legacy ministry_context labels.

SERVICE-EVENT-CONTEXT.1B. ``host_language_unit`` is display-only Host /
Language context. It does not control ServiceEvent audience rows, visibility,
serving, permissions, or any other runtime authority.

Dry-run is the default. Apply mode requires BOTH ``--apply`` and
``--confirm-service-event-host-language-unit-backfill``. Apply mode only sets
``ServiceEvent.host_language_unit`` on eligible rows and never clears
``ServiceEvent.ministry_context``.
"""

from dataclasses import dataclass
from datetime import datetime

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from accounts.models import ChurchStructureUnit
from events.models import ServiceEvent


_STAT_KEYS = (
    "service_events_checked",
    "service_events_with_ministry_context",
    "service_events_with_host_language_unit",
    "candidate_events",
    "eligible_to_backfill",
    "would_update_count",
    "updated_count",
    "skipped_missing_mapped_context_unit",
    "skipped_inactive_mapped_context_unit",
    "skipped_wrong_mapped_context_unit_type",
    "remaining_candidates_after_operation",
)


@dataclass(frozen=True)
class BackfillPlan:
    event_id: int
    unit_id: int


@dataclass(frozen=True)
class DecisionLine:
    event_id: int
    title: str
    status: str
    start: str
    current_context: str
    mapped_unit: str
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


def _format_decision_line(line):
    start = line.start or "(none)"
    return (
        f"  event #{line.event_id} | title: {line.title!r} | status: {line.status} "
        f"| start: {start} | current ministry_context: {line.current_context} "
        f"| mapped unit: {line.mapped_unit} | decision: {line.category} "
        f"| reason: {line.reason}"
    )


def _event_queryset(*, lock=False):
    rows = (
        ServiceEvent.objects.select_related(
            "host_language_unit",
            "ministry_context",
            "ministry_context__church_structure_unit",
        )
        .order_by("id")
    )
    if lock:
        rows = rows.select_for_update()
    return rows


def _decision_line(event, *, mapped_unit, category, reason):
    return DecisionLine(
        event_id=event.id,
        title=event.title,
        status=event.status,
        start=_start_label(event),
        current_context=_context_label(event.ministry_context),
        mapped_unit=_unit_label(mapped_unit),
        category=category,
        reason=reason,
    )


def _classify_event(event, stats, *, apply_mode):
    mapped_unit = event.ministry_context.church_structure_unit
    if mapped_unit is None:
        stats["skipped_missing_mapped_context_unit"] += 1
        return (
            _decision_line(
                event,
                mapped_unit=None,
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
                mapped_unit=mapped_unit,
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
                mapped_unit=mapped_unit,
                category="skipped_wrong_mapped_context_unit_type",
                reason="mapped unit is not a ministry_context unit",
            ),
            None,
        )

    stats["eligible_to_backfill"] += 1
    if apply_mode:
        category = "updated"
        reason = "host_language_unit backfill applied from legacy ministry_context mapping"
    else:
        stats["would_update_count"] += 1
        category = "would_update"
        reason = "safe host_language_unit backfill candidate"

    return (
        _decision_line(
            event,
            mapped_unit=mapped_unit,
            category=category,
            reason=reason,
        ),
        BackfillPlan(event_id=event.id, unit_id=mapped_unit.id),
    )


def _scan_events(*, lock=False, apply_mode=False):
    stats = _new_stats()
    lines = []
    plans = []

    for event in _event_queryset(lock=lock):
        stats["service_events_checked"] += 1
        if event.ministry_context_id:
            stats["service_events_with_ministry_context"] += 1
        if event.host_language_unit_id:
            stats["service_events_with_host_language_unit"] += 1

        if not event.ministry_context_id or event.host_language_unit_id:
            continue

        stats["candidate_events"] += 1
        line, plan = _classify_event(event, stats, apply_mode=apply_mode)
        lines.append(line)
        if plan is not None:
            plans.append(plan)

    return stats, lines, plans


def _set_remaining_candidates(stats, *, apply_mode):
    if apply_mode:
        remaining = stats["candidate_events"] - stats["updated_count"]
    else:
        remaining = stats["candidate_events"]
    stats["remaining_candidates_after_operation"] = remaining


def run_audit():
    stats, lines, _plans = _scan_events()
    _set_remaining_candidates(stats, apply_mode=False)
    return stats, lines


def apply_backfill():
    with transaction.atomic():
        stats, lines, plans = _scan_events(lock=True, apply_mode=True)
        for plan in plans:
            updated = ServiceEvent.objects.filter(
                id=plan.event_id,
                host_language_unit__isnull=True,
            ).update(host_language_unit_id=plan.unit_id)
            if updated:
                stats["updated_count"] += 1
                stats["service_events_with_host_language_unit"] += updated
        _set_remaining_candidates(stats, apply_mode=True)
    return stats, lines


class Command(BaseCommand):
    help = (
        "Dry-run-first backfill for ServiceEvent.host_language_unit display "
        "context from legacy ServiceEvent.ministry_context mappings "
        "(SERVICE-EVENT-CONTEXT.1B). Apply mode sets only the display-only "
        "host_language_unit field and never clears ministry_context or changes "
        "audience rows/visibility."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help=(
                "Actually set ServiceEvent.host_language_unit on eligible rows. "
                "Requires --confirm-service-event-host-language-unit-backfill."
            ),
        )
        parser.add_argument(
            "--confirm-service-event-host-language-unit-backfill",
            action="store_true",
            help="Required with --apply to confirm this display-only backfill.",
        )
        parser.add_argument(
            "--verbose",
            action="store_true",
            help="Print per-event backfill decisions (non-sensitive metadata only).",
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
            "confirm_service_event_host_language_unit_backfill"
        ]
        if apply_mode and not confirmed:
            raise CommandError(
                "--apply requires "
                "--confirm-service-event-host-language-unit-backfill; "
                "no ServiceEvent.host_language_unit values were set."
            )

        if apply_mode:
            stats, lines = apply_backfill()
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
            stats["skipped_missing_mapped_context_unit"]
            + stats["skipped_inactive_mapped_context_unit"]
            + stats["skipped_wrong_mapped_context_unit_type"]
        )
        if options["fail_on_blockers"] and blocker_total:
            raise CommandError(
                "ServiceEvent host_language_unit backfill skip categories "
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
        data_mutated = bool(stats["updated_count"])

        if apply_mode:
            write("ServiceEvent host_language_unit backfill (SE-CTX.1B, APPLY mode)")
        else:
            write("ServiceEvent host_language_unit backfill (SE-CTX.1B, dry-run only)")
        write("=" * 78)
        write(f"mode: {'apply' if apply_mode else 'dry-run'}")
        write(f"apply_option_present: {str(apply_mode).lower()}")
        write(f"confirmation_option_present: {str(confirmed).lower()}")
        for key in _STAT_KEYS:
            if key == "updated_count" and not apply_mode:
                continue
            write(f"{key}: {stats[key]}")
        write(f"data_mutated: {str(data_mutated).lower()}")
        write("runtime_mutated: false")
        write("schema_mutated: false")
        write("")
        if apply_mode:
            write(
                "Apply mode: set only ServiceEvent.host_language_unit for safe "
                "rows whose legacy ministry_context maps to an active "
                "ministry-context ChurchStructureUnit. ServiceEvent.ministry_context, "
                "audience rows, audience visibility, ChurchStructureUnit, "
                "MinistryContext rows, memberships, serving assignments, and all "
                "other modules were not changed."
            )
        else:
            write(
                "Dry-run only: no ServiceEvent.host_language_unit value, "
                "ServiceEvent.ministry_context link, audience row, MinistryContext "
                "row, ChurchStructureUnit, membership, serving assignment, other "
                "module, runtime, or schema data changed."
            )

        if not verbose:
            return

        write("")
        write("per-event decisions (non-sensitive metadata only):")
        if not lines:
            write("  (no candidate events with ministry_context set and host_language_unit blank)")
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
