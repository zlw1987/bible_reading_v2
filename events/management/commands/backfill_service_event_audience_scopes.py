"""SE-AS.6B/6C backfill for ServiceEvent audience-scope rows.

This command scans existing ``ServiceEvent`` rows and reports which ones could
be safely converted from their legacy ``scope_type`` / ``district`` /
``small_group`` fields onto explicit ``ServiceEventAudienceScope`` rows,
following the binding SE-AS.6A contract in
``docs/SERVICE_EVENT_AUDIENCE_RUNTIME_MIGRATION_PLAN.md`` (Section 8A).

It runs as a read-only **dry-run by default** (SE-AS.6B). With the explicit
``--apply`` flag (SE-AS.6C) it additionally creates ``ServiceEventAudienceScope``
rows, but only for events the shared decision path classifies as parity-safe
``would-create``. Dry-run and apply use the exact same classification, so apply
never creates a row the dry-run would not have reported.

In **both** modes it never mutates any legacy field
(``scope_type`` / ``district`` / ``small_group`` / ``ministry_context``),
``ChurchStructureUnit``, ``ChurchStructureMembership``, ``Profile``,
``SmallGroup``, ``District``, or ``MinistryContext`` row, and it never uses
``ChurchStructureMembership`` as a mapping input (the proposed unit is derived
only from the event's legacy district/small-group ``church_structure_unit``
mapping, never from membership rows). The parity check **does** read active
primary ``ChurchStructureMembership`` to compute the post-row audience, because
that is the rule the current runtime applies once an event has audience rows
(CS-CORE.2B-A). The reported ``legacy-fields-mutated`` count is always ``0`` by
construction. Events that already have audience rows are skipped in both modes,
so apply is idempotent.

Parity (Section 8A.4) — current-runtime parity, not legacy-resolver parity:
for every event the audit marks as "would-create", the post-backfill audience
must equal the pre-backfill audience **under the actual current runtime
(CS-CORE.2B-A)**, for every ordinary (non-manager) user:

- *pre-backfill* is the zero-row legacy rule, matched directly via
  ``Profile.small_group`` (global → all authenticated; district →
  ``profile.small_group.district_id == event.district_id``; small group →
  ``profile.small_group_id == event.small_group_id``);
- *post-backfill* is the membership-core structure-audience rule the runtime
  actually applies once an event has rows, via the canonical
  ``accounts.structure_selectors.user_matches_structure_audience`` (active
  primary ``ChurchStructureMembership``), **not** the legacy
  ``resolve_units_to_small_groups`` resolver.

The audit compares the actual ordinary-user ID sets these two rules produce.
Managers (``ServiceEvent.can_be_managed_by``) are excluded because they have
the same override on both paths. If creating the row would add or drop even one
ordinary user, the event is classified as parity-mismatch and skipped, never
silently dropped. Global events map to the active root unit, which both the
legacy global rule and the membership-core root rule treat as every
authenticated user, so global backfill stays parity-safe by construction.
"""

from datetime import datetime

from django.contrib.auth import get_user_model
from django.core.exceptions import FieldDoesNotExist
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from accounts.models import ChurchStructureUnit
from accounts.structure_selectors import (
    get_user_legacy_small_group,
    user_matches_structure_audience,
)

from events.models import ServiceEvent, ServiceEventAudienceScope

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


def _legacy_event_match(event, user):
    """Pre-backfill zero-row legacy visibility for one ordinary user.

    Mirrors the legacy branch of ``ServiceEvent.can_be_seen_by`` exactly: it
    matches directly through ``Profile.small_group`` and never consults
    ``ChurchStructureMembership``. This is the audience an event keeps while it
    has zero ``ServiceEventAudienceScope`` rows.
    """
    scope = event.scope_type

    if scope == ServiceEvent.SCOPE_GLOBAL:
        return True

    small_group = get_user_legacy_small_group(user)
    if small_group is None:
        return False

    if scope == ServiceEvent.SCOPE_DISTRICT:
        return bool(
            event.district_id
            and small_group.district_id
            and event.district_id == small_group.district_id
        )

    if scope == ServiceEvent.SCOPE_SMALL_GROUP:
        return bool(event.small_group_id and event.small_group_id == small_group.id)

    return False


def _proposed_event_match(event, proposed_unit, user):
    """Post-backfill visibility for one ordinary user under current runtime.

    Once an event has audience rows, ``ServiceEvent.can_be_seen_by`` matches
    through the canonical membership-core selector (CS-CORE.2B-A), so this uses
    the same ``user_matches_structure_audience`` helper rather than the legacy
    ``resolve_units_to_small_groups`` resolver.
    """
    return user_matches_structure_audience(user, [proposed_unit])


def _parity_holds(event, proposed_unit, ordinary_users):
    """Return whether creating ``proposed_unit`` keeps current-runtime parity.

    Compares, per ordinary (non-manager) user, the pre-backfill legacy audience
    against the post-backfill membership-core audience. Managers are skipped
    because ``can_be_managed_by`` already grants them visibility on both paths.
    Returns ``False`` as soon as any ordinary user would be added or dropped.
    """
    for user in ordinary_users:
        if event.can_be_managed_by(user):
            continue
        if _legacy_event_match(event, user) != _proposed_event_match(
            event, proposed_unit, user
        ):
            return False
    return True


def _model_has_field(model, field_name):
    try:
        model._meta.get_field(field_name)
    except FieldDoesNotExist:
        return False
    return True


def _event_label(event):
    for field_name in ("title", "name", "title_en"):
        if not _model_has_field(ServiceEvent, field_name):
            continue
        value = getattr(event, field_name, "")
        if value:
            value = str(value).strip()
            if value:
                return value
    return ""


def _event_start_label(event):
    for field_name in ("start_datetime", "start_date", "event_date", "date"):
        if not _model_has_field(ServiceEvent, field_name):
            continue
        value = getattr(event, field_name, None)
        if not value:
            continue
        if hasattr(value, "strftime"):
            if isinstance(value, datetime) and timezone.is_aware(value):
                value = timezone.localtime(value)
            return value.strftime("%Y-%m-%d %H:%M %Z").strip()
        return str(value).strip()
    return ""


def _unit_label(unit):
    if unit is None:
        return ""

    if hasattr(unit, "path_label"):
        label = unit.path_label()
    else:
        label = str(unit)

    if getattr(unit, "code", ""):
        return f"{label} ({unit.code})"
    return label


def _format_event_line(event, category, reason, proposed_unit=None):
    parts = [f"event #{event.id}"]

    label = _event_label(event)
    if label:
        parts.append(f"title: {label}")

    start_label = _event_start_label(event)
    if start_label:
        parts.append(f"starts: {start_label}")

    parts.extend(
        [
            f"legacy: {event.scope_type}/{event.status}",
            f"category: {category}",
        ]
    )

    proposed_label = _unit_label(proposed_unit)
    if proposed_label:
        parts.append(f"proposed unit: {proposed_label}")

    parts.append(f"reason: {reason}")
    return "  " + " | ".join(parts)


def _classify_mapped(
    *,
    event,
    related,
    missing_reason,
    unmapped_reason,
    inactive_reason,
    safe_bucket,
    unsafe_bucket,
    ordinary_users,
):
    if related is None:
        return ("skipped-unmapped", missing_reason, unsafe_bucket, None)

    unit = related.church_structure_unit
    if unit is None:
        return ("skipped-unmapped", unmapped_reason, unsafe_bucket, None)
    if not unit.is_active:
        return ("skipped-inactive-or-unsafe", inactive_reason, unsafe_bucket, unit)

    if _parity_holds(event, unit, ordinary_users):
        return (
            "would-create",
            "legacy audience matches proposed membership-core audience",
            safe_bucket,
            unit,
        )

    return (
        "skipped-parity-mismatch",
        "parity mismatch: membership-core audience differs from legacy audience",
        "parity_mismatch_skipped",
        unit,
    )


def _classify_event(event, single_active_root, ordinary_users):
    """Return ``(category, reason, stats_bucket, proposed_unit)`` for one event.

    Pure inspection; never writes anything. ``ordinary_users`` is the shared
    list of users compared for current-runtime parity (Section 8A.4).
    """
    scope = event.scope_type

    if scope == ServiceEvent.SCOPE_GLOBAL:
        if single_active_root is None:
            return (
                "skipped-root-missing-or-ambiguous",
                "global root missing or ambiguous (need exactly one active root unit)",
                "global_skipped_root",
                None,
            )
        # Root unit is global-equivalent by construction: both the legacy global
        # rule and the membership-core root rule treat it as every authenticated
        # user, so global backfill is pure convergence and inherently
        # parity-safe under the current runtime.
        return (
            "would-create",
            "global -> active root unit",
            "global_mappable",
            single_active_root,
        )

    if scope == ServiceEvent.SCOPE_DISTRICT:
        return _classify_mapped(
            event=event,
            related=event.district,
            missing_reason="district missing on event",
            unmapped_reason="district has no church structure unit mapping",
            inactive_reason="mapped district unit is inactive",
            safe_bucket="district_mapped_parity_safe",
            unsafe_bucket="district_skipped_unsafe",
            ordinary_users=ordinary_users,
        )

    if scope == ServiceEvent.SCOPE_SMALL_GROUP:
        return _classify_mapped(
            event=event,
            related=event.small_group,
            missing_reason="small group missing on event",
            unmapped_reason="small group has no church structure unit mapping",
            inactive_reason="mapped small-group unit is inactive",
            safe_bucket="small_group_mapped_parity_safe",
            unsafe_bucket="small_group_skipped_unsafe",
            ordinary_users=ordinary_users,
        )

    return (
        "skipped-unmapped",
        f"unrecognized scope_type {scope!r}",
        "other_skipped",
        None,
    )


def _count_status(event, stats):
    key = {
        ServiceEvent.STATUS_DRAFT: "status_draft",
        ServiceEvent.STATUS_PUBLISHED: "status_published",
        ServiceEvent.STATUS_COMPLETED: "status_completed",
        ServiceEvent.STATUS_CANCELLED: "status_cancelled",
    }.get(event.status, "status_other")
    stats[key] += 1


def _scan_events():
    """Single read-only decision pass over every ServiceEvent.

    Returns ``(stats, event_lines, plan)`` where ``plan`` is a deterministic
    list of ``(event, proposed_unit)`` pairs for parity-safe ``would-create``
    events. This is the one shared decision path used by both the dry-run
    audit and the ``--apply`` backfill, so apply can never act on an event the
    dry-run would not have reported as ``would-create``. This function itself
    creates, edits, or deletes nothing.
    """
    stats = _new_stats()
    event_lines = []
    plan = []

    events = (
        ServiceEvent.objects.all()
        .select_related(
            "district",
            "district__church_structure_unit",
            "small_group",
            "small_group__church_structure_unit",
        )
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

    # Resolve the ordinary-user population once; current-runtime parity is a
    # per-user comparison (Section 8A.4) and the user set never changes during a
    # read-only scan. Managers are filtered per event by ``can_be_managed_by``.
    User = get_user_model()
    ordinary_users = list(
        User.objects.all().select_related("profile", "profile__small_group")
    )

    for event in events:
        stats["total"] += 1
        _count_status(event, stats)

        if event.audience_scope_links.exists():
            stats["skipped_existing_rows"] += 1
            event_lines.append(
                _format_event_line(
                    event,
                    "skipped-existing-rows",
                    "already has audience rows",
                )
            )
            continue

        category, reason, bucket, proposed_unit = _classify_event(
            event, single_active_root, ordinary_users
        )
        stats[bucket] += 1
        if category == "would-create":
            stats["would_create_rows"] += 1
            plan.append((event, proposed_unit))
        event_lines.append(_format_event_line(event, category, reason, proposed_unit))

    return stats, event_lines, plan


def run_audit():
    """Scan ServiceEvent rows read-only and return ``(stats, event_lines)``.

    ``stats`` is a dict keyed by ``_STAT_KEYS``. ``event_lines`` is a
    deterministic list of per-event decision strings for optional verbose
    output. Nothing is created, edited, or deleted.
    """
    stats, event_lines, _plan = _scan_events()
    return stats, event_lines


def apply_backfill():
    """Create audience rows for parity-safe ``would-create`` events.

    Returns ``(stats, event_lines, created)``. Runs inside a single atomic
    transaction: if anything unexpected happens while creating rows the whole
    apply rolls back rather than leaving a partial backfill. Only
    ``ServiceEventAudienceScope`` rows are created; no legacy field, unit,
    membership, profile, or group is touched. Idempotent: events that already
    have audience rows are skipped by the shared scan, so a second run creates
    ``0`` additional rows.
    """
    created = 0
    with transaction.atomic():
        stats, event_lines, plan = _scan_events()
        for event, proposed_unit in plan:
            _obj, was_created = ServiceEventAudienceScope.objects.get_or_create(
                service_event=event,
                unit=proposed_unit,
            )
            if was_created:
                created += 1
    return stats, event_lines, created


class Command(BaseCommand):
    help = (
        "Audit (and optionally backfill) which ServiceEvent rows can be safely "
        "converted from legacy audience fields into ServiceEventAudienceScope "
        "rows. Dry-run by default (SE-AS.6B): creates, edits, and deletes "
        "nothing. With --apply (SE-AS.6C) it creates audience rows only for "
        "events the dry-run classifies as parity-safe; legacy fields are never "
        "mutated."
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
        parser.add_argument(
            "--apply",
            action="store_true",
            help=(
                "Actually create ServiceEventAudienceScope rows for parity-safe "
                "events (SE-AS.6C). Without this flag the command is a read-only "
                "dry-run and changes nothing. Apply never mutates legacy fields, "
                "skips events that already have audience rows, and is idempotent."
            ),
        )

    def handle(self, *args, **options):
        apply_mode = options["apply"]
        if apply_mode:
            stats, event_lines, created = apply_backfill()
        else:
            stats, event_lines = run_audit()
            created = 0
        self._print_report(
            stats, event_lines, options["verbose_events"], apply_mode, created
        )

    def _print_report(
        self, stats, event_lines, verbose_events, apply_mode=False, created=0
    ):
        write = self.stdout.write

        if apply_mode:
            write("ServiceEvent audience-scope backfill (SE-AS.6C, APPLY mode)")
        else:
            write(
                "ServiceEvent audience-scope backfill audit (SE-AS.6B, dry-run only)"
            )
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
        if apply_mode:
            write(
                f"created audience rows                         : "
                f"{created}"
            )
        write("")
        if apply_mode:
            write(
                f"Apply mode: created {created} ServiceEventAudienceScope row(s) "
                "for parity-safe events; no legacy fields mutated."
            )
        else:
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
