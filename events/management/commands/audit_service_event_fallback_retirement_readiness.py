"""Read-only ServiceEvent zero-row safety-state diagnostic.

SE-RETIRE.1A introduced this command as the retirement-readiness audit for the
zero-audience-row legacy fallback. SE-RETIRE.1B later retired that ordinary-user
runtime fallback: ``ServiceEvent.can_be_seen_by`` now fails closed for ordinary
users when an event has zero ``ServiceEventAudienceScope`` rows. The legacy
``scope_type`` / ``district`` / ``small_group`` fields remain stored/admin/
display/backfill/audit/rollback context only.

This command now remains as a standing guard/diagnostic. It answers:

    "Which events still have zero audience rows, what legacy scope data would
    map them to for backfill/audit purposes, and which visible/active safety
    states need review before legacy field retirement?"

It is **read-only**. It has no ``--apply``. It never mutates any
``ServiceEvent``, ``ServiceEventAudienceScope``, legacy ``scope_type`` /
``district`` / ``small_group`` field, ``ChurchStructureUnit``,
``ChurchStructureMembership``, ``Profile``, ``SmallGroup``, ``District``, or
``MinistryContext`` row. It changes no ServiceEvent runtime behavior and does
not switch runtime behavior; ``runtime_changed_by_this_audit`` is always ``false`` and
``legacy_fields_mutated`` is always ``0`` by construction.

Backfillability is delegated to the existing
``backfill_service_event_audience_scopes`` decision path (``_classify_event``):
an event is "backfillable" exactly when that command would classify it as a
parity-safe ``would-create``, i.e. it can be converted into an equivalent
``ServiceEventAudienceScope`` row under the current membership-core runtime.
Reusing that decision keeps this audit and the backfill in agreement.

Blocker policy (what currently prevents declaring this path clean):

- A zero-row event is **blocking-visible** when its status/timing says it would
  normally be ordinary-user-relevant if it had audience rows: status published,
  or completed with an upcoming start. Since SE-RETIRE.1B such a row already
  fails closed for ordinary users; the blocker means "safety state needing
  review/backfill," not "legacy fallback currently grants access."
- Among blocking-visible zero-row events, any that are **not backfillable**
  (unmapped / inactive / wrong-type / invalid / parity-mismatch legacy fields)
  are the hard blockers: they cannot even be converted to equivalent rows.

A clean audit (zero blockers) means every ordinary-user-visible, active event
already carries audience rows, and any zero-row events are draft/cancelled/past
archive safety states. Backfillable-but-not-yet-backfilled safety states still
need an approved data/backfill decision before legacy field retirement.
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from accounts.models import ChurchStructureUnit

from events.management.commands.backfill_service_event_audience_scopes import (
    _classify_event,
    _event_label,
    _event_start_label,
    _unit_label,
)
from events.models import ServiceEvent

# Ordered, stable list of reported counters. Append new keys to keep output
# deterministic.
_STAT_KEYS = (
    "events_checked",
    "events_with_audience_rows",
    "events_without_audience_rows",
    "published_without_audience_rows",
    "future_or_upcoming_without_audience_rows",
    "active_visible_without_audience_rows",
    "zero_row_global_fallback",
    "zero_row_district_fallback",
    "zero_row_small_group_fallback",
    "zero_row_unscoped_or_invalid",
    "zero_row_backfillable",
    "zero_row_not_backfillable",
    "blocker_visible_zero_row_events",
    "blocker_not_backfillable_zero_row_events",
    "blockers_total",
    "legacy_fields_mutated",
)

# Statuses that ``ServiceEvent.can_be_seen_by`` shows to ordinary users.
_VISIBLE_STATUSES = {ServiceEvent.STATUS_PUBLISHED, ServiceEvent.STATUS_COMPLETED}


def _new_stats():
    return {key: 0 for key in _STAT_KEYS}


def _is_visible_to_ordinary(event):
    """Whether ordinary users can see this event today (status gate only)."""
    return event.status in _VISIBLE_STATUSES


def _is_upcoming(event, now):
    start = getattr(event, "start_datetime", None)
    if start is None:
        return False
    return start >= now


def _is_blocking_visibility(event, now):
    """Whether a zero-row event is ordinary-user-relevant enough to review.

    Blocking when the event has a visible/active status and is still active or
    upcoming: a published event, or any completed event whose start is in the
    future. Since SE-RETIRE.1B zero-row events already fail closed for ordinary
    users; this is a safety-state review policy, not a runtime fallback gate.
    Draft / cancelled and purely past completed events are not blockers.
    """
    if not _is_visible_to_ordinary(event):
        return False
    if event.status == ServiceEvent.STATUS_PUBLISHED:
        return True
    return _is_upcoming(event, now)


def _zero_row_scope_bucket(event):
    scope = event.scope_type
    if scope == ServiceEvent.SCOPE_GLOBAL:
        return "zero_row_global_fallback"
    if scope == ServiceEvent.SCOPE_DISTRICT:
        return "zero_row_district_fallback"
    if scope == ServiceEvent.SCOPE_SMALL_GROUP:
        return "zero_row_small_group_fallback"
    return "zero_row_unscoped_or_invalid"


def _scope_label(event):
    return f"{event.scope_type}/{event.status}"


def _format_event_line(event, category, reason, proposed_unit=None):
    """Build a non-sensitive per-event verbose line.

    Lists id / title / status / start / scope labels only. Never includes the
    event description or any other free-text body content.
    """
    parts = [f"event #{event.id}"]

    label = _event_label(event)
    if label:
        parts.append(f"title: {label}")

    start_label = _event_start_label(event)
    if start_label:
        parts.append(f"starts: {start_label}")

    parts.append(f"scope: {_scope_label(event)}")
    parts.append(f"category: {category}")

    proposed_label = _unit_label(proposed_unit)
    if proposed_label:
        parts.append(f"backfill unit: {proposed_label}")

    parts.append(f"reason: {reason}")
    return "  " + " | ".join(parts)


def _scan(event_id=None):
    """Single read-only pass over ServiceEvent rows.

    Returns ``(stats, event_lines)``. Creates, edits, or deletes nothing.
    """
    stats = _new_stats()
    event_lines = []
    now = timezone.now()

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
    if event_id is not None:
        events = events.filter(id=event_id)

    # Shared inputs for the backfill decision path, resolved once for the scan.
    active_roots = list(
        ChurchStructureUnit.objects.filter(
            unit_type=ChurchStructureUnit.UNIT_ROOT,
            is_active=True,
        )
    )
    single_active_root = active_roots[0] if len(active_roots) == 1 else None

    User = get_user_model()
    ordinary_users = list(
        User.objects.all().select_related("profile", "profile__small_group")
    )

    for event in events:
        stats["events_checked"] += 1

        if event.audience_scope_links.exists():
            stats["events_with_audience_rows"] += 1
            event_lines.append(
                _format_event_line(
                    event,
                    "has-audience-rows",
                    "membership-core via audience rows; not a zero-row safety state",
                )
            )
            continue

        # Zero-row event: ordinary-user runtime fails closed after SE-RETIRE.1B.
        # Legacy fields are inspected only as stored diagnostic/backfill context.
        stats["events_without_audience_rows"] += 1
        stats[_zero_row_scope_bucket(event)] += 1

        if event.status == ServiceEvent.STATUS_PUBLISHED:
            stats["published_without_audience_rows"] += 1
        if _is_visible_to_ordinary(event):
            stats["active_visible_without_audience_rows"] += 1
            if _is_upcoming(event, now):
                stats["future_or_upcoming_without_audience_rows"] += 1

        category, reason, _bucket, proposed_unit = _classify_event(
            event, single_active_root, ordinary_users
        )
        backfillable = category == "would-create"
        if backfillable:
            stats["zero_row_backfillable"] += 1
        else:
            stats["zero_row_not_backfillable"] += 1

        blocking_visible = _is_blocking_visibility(event, now)
        is_blocker = False
        if blocking_visible:
            stats["blocker_visible_zero_row_events"] += 1
            is_blocker = True
            if not backfillable:
                stats["blocker_not_backfillable_zero_row_events"] += 1

        if is_blocker:
            line_category = (
                "blocker-not-backfillable"
                if not backfillable
                else "blocker-backfillable"
            )
            line_reason = (
                f"visible/active zero-row safety state needs review; "
                f"backfillable={backfillable} ({reason})"
            )
        else:
            line_category = "harmless-zero-row"
            line_reason = (
                f"not ordinary-visible/active (status {event.status}); "
                f"backfillable={backfillable}"
            )
        event_lines.append(
            _format_event_line(event, line_category, line_reason, proposed_unit)
        )

    stats["blockers_total"] = (
        stats["blocker_visible_zero_row_events"]
        + stats["blocker_not_backfillable_zero_row_events"]
    )
    return stats, event_lines


def run_audit(event_id=None):
    """Read-only scan; returns ``(stats, event_lines)``. Nothing is mutated."""
    return _scan(event_id=event_id)


class Command(BaseCommand):
    help = (
        "Read-only ServiceEvent zero-row safety-state diagnostic. Reports which "
        "events have zero audience rows, which stored legacy "
        "scope_type/district/small_group fields can be mapped into equivalent "
        "audience rows for audit/backfill context, and which visible/active "
        "safety states need review before legacy field retirement. Read-only: "
        "no --apply, no runtime change, no migration, and no legacy field is "
        "ever mutated."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--verbose",
            action="store_true",
            help=(
                "Also print a per-event line (id, title, status, start, scope, "
                "category, reason). Never prints description/body text."
            ),
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Cap the number of per-event verbose lines printed.",
        )
        parser.add_argument(
            "--event-id",
            type=int,
            default=None,
            help="Audit only the ServiceEvent with this id.",
        )
        parser.add_argument(
            "--fail-on-blockers",
            action="store_true",
            help=(
                "Exit with a nonzero status when any blocker category is "
                "nonzero. Read-only regardless."
            ),
        )

    def handle(self, *args, **options):
        stats, event_lines = run_audit(event_id=options["event_id"])
        self._print_report(stats, event_lines, options["verbose"], options["limit"])

        if options["fail_on_blockers"] and stats["blockers_total"] > 0:
            raise CommandError(
                "ServiceEvent zero-row safety-state blockers present: "
                f"{stats['blocker_visible_zero_row_events']} visible/active "
                "zero-row event(s) need review "
                f"({stats['blocker_not_backfillable_zero_row_events']} not "
                "backfillable). Read-only audit; nothing was changed."
            )

    def _print_report(self, stats, event_lines, verbose, limit):
        write = self.stdout.write

        write(
            "ServiceEvent zero-row safety-state diagnostic "
            "(SE-RETIRE.1A/1B, read-only)"
        )
        write("=" * 72)
        write(f"events checked                                : {stats['events_checked']}")
        write(
            f"  with audience rows (membership-core)        : "
            f"{stats['events_with_audience_rows']}"
        )
        write(
            f"  without audience rows (fail-closed safety) : "
            f"{stats['events_without_audience_rows']}"
        )
        write("")
        write("zero-row events with ordinary-visible status/timing:")
        write(
            f"  published without audience rows             : "
            f"{stats['published_without_audience_rows']}"
        )
        write(
            f"  future/upcoming without audience rows       : "
            f"{stats['future_or_upcoming_without_audience_rows']}"
        )
        write(
            f"  active/visible without audience rows        : "
            f"{stats['active_visible_without_audience_rows']}"
        )
        write("")
        write("zero-row events by stored legacy scope fields:")
        write(
            f"  global legacy scope                         : "
            f"{stats['zero_row_global_fallback']}"
        )
        write(
            f"  district legacy scope                       : "
            f"{stats['zero_row_district_fallback']}"
        )
        write(
            f"  small-group legacy scope                    : "
            f"{stats['zero_row_small_group_fallback']}"
        )
        write(
            f"  unscoped / invalid                          : "
            f"{stats['zero_row_unscoped_or_invalid']}"
        )
        write("")
        write("zero-row backfillability (vs backfill_service_event_audience_scopes):")
        write(
            f"  backfillable into equivalent rows           : "
            f"{stats['zero_row_backfillable']}"
        )
        write(
            f"  not backfillable                            : "
            f"{stats['zero_row_not_backfillable']}"
        )
        write("")
        write("blockers (visible/active zero-row safety states):")
        write(
            f"  visible/active zero-row events              : "
            f"{stats['blocker_visible_zero_row_events']}"
        )
        write(
            f"  of which not backfillable                   : "
            f"{stats['blocker_not_backfillable_zero_row_events']}"
        )
        write(
            f"  blockers total                              : "
            f"{stats['blockers_total']}"
        )
        write("")
        write(
            f"legacy-fields-mutated (must be 0)             : "
            f"{stats['legacy_fields_mutated']}"
        )
        write("runtime-changed-by-this-audit (must be false): false")
        write("")
        if stats["blockers_total"] == 0:
            write(
                "Retirement-readiness: CLEAN. No visible/active zero-row events "
                "need safety-state review on this data. The zero-row ordinary-user "
                "fallback is already retired; this audit changed nothing."
            )
        else:
            write(
                "Retirement-readiness: BLOCKED. Visible/active zero-row events "
                "are fail-closed safety states that need review/backfill before "
                "legacy field retirement confidence. Resolve the not-backfillable "
                "ones, handle the backfillable ones under a separate approved "
                "data run, then re-audit. This audit changed nothing."
            )

        if verbose:
            write("")
            write("per-event decisions:")
            if not event_lines:
                write("  (no events scanned)")
            else:
                shown = event_lines if limit is None else event_lines[:limit]
                for line in shown:
                    write(line)
                if limit is not None and len(event_lines) > len(shown):
                    write(
                        f"  ... {len(event_lines) - len(shown)} more "
                        "(raise --limit to see)"
                    )
