from collections import defaultdict

from django.db.models import Prefetch

from ..models import TeamAssignment, TeamAssignmentMember


WORSHIP_CONTEXT_NO_ANCHOR = "no_anchor"
WORSHIP_CONTEXT_ANCHOR_UNAVAILABLE = "anchor_unavailable"
WORSHIP_CONTEXT_UNSCHEDULED = "unscheduled"
WORSHIP_CONTEXT_EMPTY = "empty"
WORSHIP_CONTEXT_SCHEDULED = "scheduled"
WORSHIP_CONTEXT_AMBIGUOUS = "ambiguous"

CURRENT_ASSIGNMENT_STATUSES = (
    TeamAssignment.STATUS_SCHEDULED,
    TeamAssignment.STATUS_CONFIRMED,
    TeamAssignment.STATUS_PREPARED,
)


def _context(*, anchor_team=None, state, member_names=None):
    """Return the intentionally narrow scheduler coordination projection."""

    return {
        "anchor_team": anchor_team,
        "state": state,
        "member_names": list(member_names or []),
    }


def build_worship_contexts(events):
    """Project current Worship context for already-authorized scheduler rows.

    The configured ``rotation_anchor_team`` is the only anchor. A current
    Worship assignment must match both the event and that exact team, and must
    use one of the shared operational statuses. Duplicate matches fail closed.

    This service is presentation-only and deliberately returns no assignment
    object, notes, confirmation details, contact fields, profile data, or links.
    Its callers remain responsible for the scheduler-only access boundary.
    """

    events = list(events)
    contexts = {}
    eligible_events = []
    for event in events:
        anchor_team = event.rotation_anchor_team
        if anchor_team is None:
            contexts[event.id] = _context(state=WORSHIP_CONTEXT_NO_ANCHOR)
        elif not anchor_team.is_active or not anchor_team.is_assignable:
            contexts[event.id] = _context(
                anchor_team=anchor_team,
                state=WORSHIP_CONTEXT_ANCHOR_UNAVAILABLE,
            )
        else:
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
