"""Guarded cleanup for existing ServiceEvent legacy audience fields.

Dry-run is the default. Apply mode requires both ``--apply`` and
``--confirm-service-event-legacy-scope-cleanup``. It clears only
``scope_type`` / ``district`` / ``small_group`` on ServiceEvent rows that
already have at least one ServiceEventAudienceScope row, so it does not change
runtime visibility semantics after SE-RETIRE.1B.
"""

from dataclasses import dataclass
from datetime import datetime

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Count
from django.utils import timezone

from events.models import ServiceEvent, ServiceEventAudienceScope


_STAT_KEYS = (
    "events_checked",
    "already_clear_count",
    "candidates_with_legacy_fields",
    "would_clear_count",
    "cleared_count",
    "skipped_zero_row_blockers",
    "remaining_blockers_after_operation",
    "legacy_fields_mutated_count",
    "legacy_field_values_mutated_count",
)


@dataclass(frozen=True)
class CleanupPlan:
    event_id: int
    changed_value_count: int


@dataclass(frozen=True)
class DecisionLine:
    event_id: int
    title: str
    start: str
    status: str
    scope_type: str
    district: str
    small_group: str
    audience_row_count: int
    category: str
    reason: str


def _new_stats():
    return {key: 0 for key in _STAT_KEYS}


def _object_label(obj):
    if obj is None:
        return "(none)"
    return f"#{obj.id} {obj}"


def _start_label(event):
    value = getattr(event, "start_datetime", None)
    if not value:
        return ""
    if isinstance(value, datetime) and timezone.is_aware(value):
        value = timezone.localtime(value)
    return value.strftime("%Y-%m-%d %H:%M %Z").strip()


def _has_legacy_scope_fields(event):
    return bool(
        event.scope_type != ServiceEvent.SCOPE_GLOBAL
        or event.district_id
        or event.small_group_id
    )


def _changed_value_count(event):
    return int(event.scope_type != ServiceEvent.SCOPE_GLOBAL) + int(
        bool(event.district_id)
    ) + int(bool(event.small_group_id))


def _decision_line(event, *, audience_row_count, category, reason):
    return DecisionLine(
        event_id=event.id,
        title=event.title,
        start=_start_label(event),
        status=event.status,
        scope_type=event.scope_type,
        district=_object_label(event.district),
        small_group=_object_label(event.small_group),
        audience_row_count=audience_row_count,
        category=category,
        reason=reason,
    )


def _format_decision_line(line):
    start = line.start or "(none)"
    return (
        f"  event #{line.event_id} | title: {line.title!r} | start: {start} "
        f"| status: {line.status} | current legacy scope values: "
        f"scope_type={line.scope_type}, district={line.district}, "
        f"small_group={line.small_group} | audience_row_count: "
        f"{line.audience_row_count} | decision: {line.category} "
        f"| reason: {line.reason}"
    )


def _event_queryset(*, lock=False):
    rows = ServiceEvent.objects.select_related("district", "small_group").order_by("id")
    if lock:
        rows = rows.select_for_update()
    return rows


def _audience_counts():
    return dict(
        ServiceEventAudienceScope.objects.values("service_event_id")
        .annotate(row_count=Count("id"))
        .values_list("service_event_id", "row_count")
    )


def _classify_event(event, stats, *, audience_row_count, apply_mode):
    if not _has_legacy_scope_fields(event):
        stats["already_clear_count"] += 1
        return (
            _decision_line(
                event,
                audience_row_count=audience_row_count,
                category="already_clear",
                reason="ServiceEvent legacy scope fields are already clear",
            ),
            None,
        )

    stats["candidates_with_legacy_fields"] += 1
    if audience_row_count < 1:
        stats["skipped_zero_row_blockers"] += 1
        return (
            _decision_line(
                event,
                audience_row_count=audience_row_count,
                category="blocked",
                reason=(
                    "candidate has populated legacy scope fields but no "
                    "ServiceEventAudienceScope rows"
                ),
            ),
            None,
        )

    changed_value_count = _changed_value_count(event)
    if apply_mode:
        category = "cleared"
        reason = "safe ServiceEvent legacy scope cleanup applied"
    else:
        stats["would_clear_count"] += 1
        category = "would_clear"
        reason = "safe ServiceEvent legacy scope cleanup candidate"

    return (
        _decision_line(
            event,
            audience_row_count=audience_row_count,
            category=category,
            reason=reason,
        ),
        CleanupPlan(
            event_id=event.id,
            changed_value_count=changed_value_count,
        ),
    )


def _scan_events(*, lock=False, apply_mode=False):
    stats = _new_stats()
    lines = []
    plans = []
    counts = _audience_counts()

    for event in _event_queryset(lock=lock):
        stats["events_checked"] += 1
        line, plan = _classify_event(
            event,
            stats,
            audience_row_count=counts.get(event.id, 0),
            apply_mode=apply_mode,
        )
        lines.append(line)
        if plan is not None:
            plans.append(plan)

    return stats, lines, plans


def _set_remaining_blockers(stats, *, apply_mode):
    if apply_mode:
        remaining = stats["candidates_with_legacy_fields"] - stats["cleared_count"]
    else:
        remaining = stats["candidates_with_legacy_fields"]
    stats["remaining_blockers_after_operation"] = remaining


def run_audit():
    stats, lines, _plans = _scan_events()
    _set_remaining_blockers(stats, apply_mode=False)
    return stats, lines


def apply_cleanup():
    with transaction.atomic():
        stats, lines, plans = _scan_events(lock=True, apply_mode=True)
        for plan in plans:
            updated = ServiceEvent.objects.filter(id=plan.event_id).update(
                scope_type=ServiceEvent.SCOPE_GLOBAL,
                district=None,
                small_group=None,
            )
            if updated:
                stats["cleared_count"] += 1
                stats["legacy_fields_mutated_count"] += 1
                stats["legacy_field_values_mutated_count"] += plan.changed_value_count
        _set_remaining_blockers(stats, apply_mode=True)
    return stats, lines


class Command(BaseCommand):
    help = (
        "Dry-run-first cleanup for existing ServiceEvent legacy scope fields "
        "(SE-SCOPE.1B). Apply mode clears only safe rows that already have "
        "ServiceEventAudienceScope rows. It never changes audience rows, "
        "ministry context, serving/team assignment data, membership, legacy "
        "structure rows, or runtime visibility semantics."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help=(
                "Actually clear safe ServiceEvent legacy scope fields. Requires "
                "--confirm-service-event-legacy-scope-cleanup."
            ),
        )
        parser.add_argument(
            "--confirm-service-event-legacy-scope-cleanup",
            action="store_true",
            help="Required with --apply to confirm this ServiceEvent cleanup.",
        )
        parser.add_argument(
            "--verbose",
            action="store_true",
            help="Print per-event cleanup decisions.",
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
            help="Exit nonzero when zero-row cleanup blockers are present.",
        )

    def handle(self, *args, **options):
        if options["limit"] is not None and options["limit"] < 0:
            raise CommandError("--limit must be zero or greater.")

        apply_mode = options["apply"]
        confirmed = options["confirm_service_event_legacy_scope_cleanup"]
        if apply_mode and not confirmed:
            raise CommandError(
                "--apply requires --confirm-service-event-legacy-scope-cleanup; "
                "no ServiceEvent legacy scope fields were cleared."
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

        if options["fail_on_blockers"] and stats["skipped_zero_row_blockers"]:
            raise CommandError(
                "ServiceEvent legacy scope cleanup blockers present "
                "(--fail-on-blockers): "
                f"skipped_zero_row_blockers={stats['skipped_zero_row_blockers']}"
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
            write("ServiceEvent legacy scope cleanup (SE-SCOPE.1B, APPLY mode)")
        else:
            write("ServiceEvent legacy scope cleanup (SE-SCOPE.1B, dry-run only)")
        write("=" * 76)
        write(f"mode: {'apply' if apply_mode else 'dry-run'}")
        write(f"apply_option_present: {str(apply_mode).lower()}")
        write(f"confirmation_option_present: {str(confirmed).lower()}")
        for key in _STAT_KEYS:
            if key == "cleared_count" and not apply_mode:
                continue
            write(f"{key}: {stats[key]}")
        write(f"data_mutated: {str(data_mutated).lower()}")
        write("runtime_mutated: false")
        write("schema_mutated: false")
        write("")
        if apply_mode:
            write(
                "Apply mode: cleared only ServiceEvent.scope_type, district, "
                "and small_group for safe rows with audience rows. Audience "
                "rows, ministry context, required teams, rotation anchor team, "
                "membership, legacy structure rows, other modules, and runtime "
                "visibility were not changed."
            )
        else:
            write(
                "Dry-run only: no ServiceEvent legacy field, audience row, "
                "ministry context, required team, rotation anchor team, "
                "membership, legacy structure row, other module, runtime, or "
                "schema data changed."
            )

        if not verbose:
            return

        write("")
        write("per-event decisions:")
        if not lines:
            write("  (no events scanned)")
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
