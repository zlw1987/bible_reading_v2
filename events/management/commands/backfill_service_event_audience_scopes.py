"""SE-AS.6B dry-run audit for ServiceEvent audience-scope backfill.

This command is **audit-only**. It scans existing ``ServiceEvent`` rows and
reports which ones could be safely converted from their legacy
``scope_type`` / ``district`` / ``small_group`` fields onto explicit
``ServiceEventAudienceScope`` rows, following the binding SE-AS.6A contract in
``docs/SERVICE_EVENT_AUDIENCE_RUNTIME_MIGRATION_PLAN.md`` (Section 8A).

It creates, edits, or deletes nothing. There is intentionally no ``--apply``
flag (that is the future SE-AS.6C slice). It does not mutate any legacy field,
``ChurchStructureUnit``, ``ChurchStructureMembership``, ``Profile``,
``SmallGroup``, ``District``, or ``MinistryContext`` row, and it never consults
``ChurchStructureMembership`` for visibility. The reported
``legacy-fields-mutated`` count is always ``0`` by construction.

Parity (Section 8A.4): for every event the audit marks as "would-create", the
ordinary-user audience produced by the proposed unit row must equal the
ordinary-user audience under the pre-backfill legacy rule. Parity is compared
on the resolved ``SmallGroup`` sets (ordinary-user matching is entirely through
``Profile.small_group``), reusing ``studies.models.resolve_units_to_small_groups``
so the proposed-row audience matches the live runtime rule exactly. Events that
cannot be proven parity-safe are skipped and reported, never silently dropped.
"""

from django.core.management.base import BaseCommand

from accounts.models import ChurchStructureUnit, SmallGroup
from studies.models import resolve_units_to_small_groups

from events.models import ServiceEvent

# Sentinel meaning "every authenticated ordinary user" (legacy global / root
# unit). Distinct from any ``frozenset`` of small-group ids so the two audience
# shapes never compare equal by accident.
_ALL_USERS = "__ALL_AUTHENTICATED_USERS__"

# Ordered, stable list of the counters the audit reports. New scopes append
# here so output stays deterministic.
_STAT_KEYS = (
    "total",
    "skipped_existing_rows",
    "global_mappable",
    "global_skipped_root",
    "district_mapped_parity_safe",
    "district_skipped_unsafe",
    "small_group_mapped_parity_safe",
    "small_group_skipped_unsafe",
    "parity_mismatch_skipped",
    "other_skipped",
    "would_create_rows",
    "legacy_fields_mutated",
    "status_draft",
    "status_published",
    "status_completed",
    "status_cancelled",
    "status_other",
)


def _new_stats():
    return {key: 0 for key in _STAT_KEYS}


def _legacy_district_signature(event):
    # Legacy district matching is `user.profile.small_group.district_id ==
    # event.district_id`, regardless of small-group active state, so the legacy
    # audience is every small group in the district (active or not).
    return frozenset(
        SmallGroup.objects.filter(district_id=event.district_id).values_list(
            "id", flat=True
        )
    )


def _legacy_small_group_signature(event):
    # Legacy small-group matching is `small_group_id == user_group.id`,
    # regardless of active state, so the legacy audience is exactly that group.
    return frozenset({event.small_group_id})


def _proposed_signature(unit):
    # Mirrors the live SE-AS.4 runtime rule: a root unit reaches every
    # authenticated ordinary user; any other unit reaches the active legacy
    # small groups the shared resolver maps it to.
    if unit.unit_type == ChurchStructureUnit.UNIT_ROOT:
        return _ALL_USERS
    return frozenset(
        resolve_units_to_small_groups([unit]).values_list("id", flat=True)
    )


def _classify_mapped(
    *,
    related,
    missing_reason,
    unmapped_reason,
    inactive_reason,
    legacy_signature,
    safe_bucket,
    unsafe_bucket,
):
    if related is None:
        return ("skipped", missing_reason, unsafe_bucket)

    unit = related.church_structure_unit
    if unit is None:
        return ("skipped", unmapped_reason, unsafe_bucket)
    if not unit.is_active:
        return ("skipped", inactive_reason, unsafe_bucket)

    if _proposed_signature(unit) == legacy_signature:
        return ("would-create", "legacy audience matches proposed unit row", safe_bucket)

    return (
        "skipped",
        "parity mismatch: proposed unit audience differs from legacy audience",
        "parity_mismatch_skipped",
    )


def _classify_event(event, single_active_root):
    """Return ``(decision, reason, stats_bucket)`` for one event.

    ``decision`` is ``"would-create"`` or ``"skipped"``. Pure inspection; never
    writes anything.
    """
    scope = event.scope_type

    if scope == ServiceEvent.SCOPE_GLOBAL:
        if single_active_root is None:
            return (
                "skipped",
                "global root missing or ambiguous (need exactly one active root unit)",
                "global_skipped_root",
            )
        # Root unit is global-equivalent by construction (both resolve to every
        # authenticated ordinary user), so global backfill is pure convergence
        # and inherently parity-safe.
        return ("would-create", "global -> active root unit", "global_mappable")

    if scope == ServiceEvent.SCOPE_DISTRICT:
        return _classify_mapped(
            related=event.district,
            missing_reason="district missing on event",
            unmapped_reason="district has no church structure unit mapping",
            inactive_reason="mapped district unit is inactive",
            legacy_signature=_legacy_district_signature(event),
            safe_bucket="district_mapped_parity_safe",
            unsafe_bucket="district_skipped_unsafe",
        )

    if scope == ServiceEvent.SCOPE_SMALL_GROUP:
        return _classify_mapped(
            related=event.small_group,
            missing_reason="small group missing on event",
            unmapped_reason="small group has no church structure unit mapping",
            inactive_reason="mapped small-group unit is inactive",
            legacy_signature=_legacy_small_group_signature(event),
            safe_bucket="small_group_mapped_parity_safe",
            unsafe_bucket="small_group_skipped_unsafe",
        )

    return ("skipped", f"unrecognized scope_type {scope!r}", "other_skipped")


def _count_status(event, stats):
    key = {
        ServiceEvent.STATUS_DRAFT: "status_draft",
        ServiceEvent.STATUS_PUBLISHED: "status_published",
        ServiceEvent.STATUS_COMPLETED: "status_completed",
        ServiceEvent.STATUS_CANCELLED: "status_cancelled",
    }.get(event.status, "status_other")
    stats[key] += 1


def run_audit():
    """Scan ServiceEvent rows read-only and return ``(stats, event_lines)``.

    ``stats`` is a dict keyed by ``_STAT_KEYS``. ``event_lines`` is a
    deterministic list of per-event decision strings for optional verbose
    output. Nothing is created, edited, or deleted.
    """
    stats = _new_stats()
    event_lines = []

    events = (
        ServiceEvent.objects.all()
        .select_related("district", "small_group")
        .order_by("id")
    )

    # Resolve the active-root situation once; it is shared by every global event
    # and never changes during a read-only scan.
    active_roots = list(
        ChurchStructureUnit.objects.filter(
            unit_type=ChurchStructureUnit.UNIT_ROOT,
            is_active=True,
        )
    )
    single_active_root = active_roots[0] if len(active_roots) == 1 else None

    for event in events:
        stats["total"] += 1
        _count_status(event, stats)

        if event.audience_scope_links.exists():
            stats["skipped_existing_rows"] += 1
            event_lines.append(
                f"  event #{event.id} [{event.scope_type}/{event.status}] "
                f"skipped: already has audience rows"
            )
            continue

        decision, reason, bucket = _classify_event(event, single_active_root)
        stats[bucket] += 1
        if decision == "would-create":
            stats["would_create_rows"] += 1
        event_lines.append(
            f"  event #{event.id} [{event.scope_type}/{event.status}] "
            f"{decision}: {reason}"
        )

    return stats, event_lines


class Command(BaseCommand):
    help = (
        "Audit which ServiceEvent rows could be safely backfilled from legacy "
        "audience fields into ServiceEventAudienceScope rows. Read-only: "
        "creates, edits, and deletes nothing (SE-AS.6B, no --apply)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--verbose-events",
            action="store_true",
            help=(
                "Also print a per-event decision line (event id, scope, "
                "decision, and reason). Independent of Django -v verbosity."
            ),
        )

    def handle(self, *args, **options):
        stats, event_lines = run_audit()
        self._print_report(stats, event_lines, options["verbose_events"])

    def _print_report(self, stats, event_lines, verbose_events):
        write = self.stdout.write

        write("ServiceEvent audience-scope backfill audit (SE-AS.6B, dry-run only)")
        write("=" * 68)
        write(f"total events scanned                          : {stats['total']}")
        write(
            f"skipped (already has audience rows)           : "
            f"{stats['skipped_existing_rows']}"
        )
        write("")
        write("global:")
        write(
            f"  mappable to single active root unit         : "
            f"{stats['global_mappable']}"
        )
        write(
            f"  skipped (root missing or ambiguous)         : "
            f"{stats['global_skipped_root']}"
        )
        write("district:")
        write(
            f"  mapped and parity-safe                      : "
            f"{stats['district_mapped_parity_safe']}"
        )
        write(
            f"  skipped (unmapped / inactive / unsafe)      : "
            f"{stats['district_skipped_unsafe']}"
        )
        write("small group:")
        write(
            f"  mapped and parity-safe                      : "
            f"{stats['small_group_mapped_parity_safe']}"
        )
        write(
            f"  skipped (unmapped / inactive / unsafe)      : "
            f"{stats['small_group_skipped_unsafe']}"
        )
        write("")
        write(
            f"parity-mismatch skipped                       : "
            f"{stats['parity_mismatch_skipped']}"
        )
        if stats["other_skipped"]:
            write(
                f"other skipped (unrecognized scope)            : "
                f"{stats['other_skipped']}"
            )
        write("")
        write("events by status:")
        write(f"  draft                                       : {stats['status_draft']}")
        write(
            f"  published                                   : "
            f"{stats['status_published']}"
        )
        write(
            f"  completed                                   : "
            f"{stats['status_completed']}"
        )
        write(
            f"  cancelled                                   : "
            f"{stats['status_cancelled']}"
        )
        if stats["status_other"]:
            write(
                f"  other                                       : "
                f"{stats['status_other']}"
            )
        write("")
        write(
            f"would-create audience rows                    : "
            f"{stats['would_create_rows']}"
        )
        write(
            f"legacy-fields-mutated (must be 0)             : "
            f"{stats['legacy_fields_mutated']}"
        )
        write("")
        write(
            "Audit only: no ServiceEventAudienceScope rows created and no "
            "fields mutated."
        )

        if verbose_events:
            write("")
            write("per-event decisions:")
            if event_lines:
                for line in event_lines:
                    write(line)
            else:
                write("  (no events scanned)")
