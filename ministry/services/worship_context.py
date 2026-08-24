from collections import defaultdict

from django.db.models import Prefetch

from ..models import TeamAssignment, TeamAssignmentMember
from .worship_governance import (
    CURRENT_WORSHIP_ASSIGNMENT_STATUSES,
    WorshipOwnershipConsistencyState,
    inspect_worship_ownership_consistency,
)


WORSHIP_CONTEXT_NO_ANCHOR = "no_anchor"
WORSHIP_CONTEXT_ANCHOR_UNAVAILABLE = "anchor_unavailable"
WORSHIP_CONTEXT_UNSCHEDULED = "unscheduled"
WORSHIP_CONTEXT_EMPTY = "empty"
WORSHIP_CONTEXT_SCHEDULED = "scheduled"
WORSHIP_CONTEXT_AMBIGUOUS = "ambiguous"
WORSHIP_CONTEXT_CONFLICT = "conflict"

# Backward-compatible presentation alias. The canonical current-status tuple
# lives in the pool-aware governance service.
CURRENT_ASSIGNMENT_STATUSES = CURRENT_WORSHIP_ASSIGNMENT_STATUSES


def _context(*, anchor_team=None, state, member_names=None):
    """Return the intentionally narrow scheduler coordination projection."""

    return {
        "anchor_team": anchor_team,
        "state": state,
        "member_names": list(member_names or []),
    }


def build_worship_contexts(events, *, ownership_inspections=None):
    """Project current Worship context for already-authorized scheduler rows.

    Canonical ownership inspection distinguishes valid selected-team states
    from invalid, conflicting, and ambiguous ownership. Only a consistent
    exact selected-team assignment projects its active member display names.

    This service is presentation-only and deliberately returns no assignment
    object, notes, confirmation details, contact fields, profile data, or links.
    Its callers remain responsible for the scheduler-only access boundary.
    """

    events = list(events)
    ownership_inspections = dict(ownership_inspections or {})
    contexts = {}
    eligible_events = []
    for event in events:
        anchor_team = event.rotation_anchor_team
        inspection = ownership_inspections.get(event.id)
        if inspection is None:
            inspection = inspect_worship_ownership_consistency(event)
            ownership_inspections[event.id] = inspection

        if inspection.state == WorshipOwnershipConsistencyState.NO_SELECTION:
            contexts[event.id] = _context(state=WORSHIP_CONTEXT_NO_ANCHOR)
            continue
        if inspection.state == WorshipOwnershipConsistencyState.INVALID_SELECTION:
            contexts[event.id] = _context(
                anchor_team=anchor_team,
                state=WORSHIP_CONTEXT_ANCHOR_UNAVAILABLE,
            )
            continue
        if inspection.state in {
            WorshipOwnershipConsistencyState.OFF_TEAM_CONFLICT,
            WorshipOwnershipConsistencyState.OUT_OF_SCOPE_WORSHIP_CONFLICT,
        }:
            contexts[event.id] = _context(
                anchor_team=anchor_team,
                state=WORSHIP_CONTEXT_CONFLICT,
            )
            continue
        if inspection.state in {
            WorshipOwnershipConsistencyState.MULTIPLE_CURRENT_WORSHIP_ASSIGNMENTS,
            WorshipOwnershipConsistencyState.DUPLICATE_SELECTED_TEAM_ASSIGNMENT,
        }:
            contexts[event.id] = _context(
                anchor_team=anchor_team,
                state=WORSHIP_CONTEXT_AMBIGUOUS,
            )
            continue
        if (
            inspection.state
            == WorshipOwnershipConsistencyState.SELECTED_UNSCHEDULED
        ):
            contexts[event.id] = _context(
                anchor_team=anchor_team,
                state=WORSHIP_CONTEXT_UNSCHEDULED,
            )
            continue
        eligible_events.append(event)

    if not eligible_events:
        return contexts

    eligible_event_ids = [event.id for event in eligible_events]
    anchor_team_ids = {
        event.rotation_anchor_team_id for event in eligible_events
    }
    assignments = (
        TeamAssignment.objects.select_related("service_event", "ministry_team")
        .prefetch_related(
            Prefetch(
                "assignment_members",
                queryset=(
                    TeamAssignmentMember.objects.select_related(
                        "membership",
                        "membership__user",
                    )
                    .filter(membership__is_active=True)
                    .order_by(
                        "membership__display_name",
                        "membership__user__first_name",
                        "membership__user__username",
                        "id",
                    )
                ),
                to_attr="worship_context_members",
            )
        )
        .filter(
            service_event_id__in=eligible_event_ids,
            ministry_team_id__in=anchor_team_ids,
            status__in=CURRENT_ASSIGNMENT_STATUSES,
        )
        .order_by("service_event_id", "id")
    )

    assignments_by_event = defaultdict(list)
    anchor_team_id_by_event = {
        event.id: event.rotation_anchor_team_id for event in eligible_events
    }
    for assignment in assignments:
        if assignment.ministry_team_id != anchor_team_id_by_event.get(
            assignment.service_event_id
        ):
            continue
        assignments_by_event[assignment.service_event_id].append(assignment)

    for event in eligible_events:
        anchor_team = event.rotation_anchor_team
        current_assignments = assignments_by_event[event.id]
        if not current_assignments:
            contexts[event.id] = _context(
                anchor_team=anchor_team,
                state=WORSHIP_CONTEXT_UNSCHEDULED,
            )
            continue
        if len(current_assignments) > 1:
            contexts[event.id] = _context(
                anchor_team=anchor_team,
                state=WORSHIP_CONTEXT_AMBIGUOUS,
            )
            continue

        member_names = [
            assignment_member.membership.get_display_name()
            for assignment_member in current_assignments[0].worship_context_members
        ]
        contexts[event.id] = _context(
            anchor_team=anchor_team,
            state=(
                WORSHIP_CONTEXT_SCHEDULED
                if member_names
                else WORSHIP_CONTEXT_EMPTY
            ),
            member_names=member_names,
        )

    return contexts
