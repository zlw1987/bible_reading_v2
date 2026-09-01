"""Central canonical Worship context semantic and narrow presentation."""

from dataclasses import dataclass
from enum import StrEnum

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

CURRENT_ASSIGNMENT_STATUSES = CURRENT_WORSHIP_ASSIGNMENT_STATUSES


class CanonicalWorshipSemanticState(StrEnum):
    NO_SELECTION = "no_selection"
    UNAVAILABLE = "unavailable"
    SELECTED_UNSCHEDULED = "selected_unscheduled"
    CONSISTENT_EMPTY = "consistent_empty"
    CONSISTENT_ROSTER = "consistent_roster"
    CONFLICT = "conflict"
    AMBIGUOUS = "ambiguous"


@dataclass(frozen=True)
class CanonicalWorshipRosterIdentity:
    membership_id: int
    user_id: int | None
    display_identity_digest: str | None = None


@dataclass(frozen=True)
class CanonicalWorshipContext:
    selected_team: object | None
    state: CanonicalWorshipSemanticState
    assignment_id: int | None = None
    assigned_team_id: int | None = None
    roster_identities: tuple[CanonicalWorshipRosterIdentity, ...] = ()
    member_names: tuple[str, ...] = ()
    roster_signature_available: bool = True

    @property
    def selected_team_id(self):
        return getattr(self.selected_team, "pk", None)


OWNERSHIP_TO_CANONICAL_STATE = {
    WorshipOwnershipConsistencyState.NO_SELECTION: CanonicalWorshipSemanticState.NO_SELECTION,
    WorshipOwnershipConsistencyState.INVALID_SELECTION: CanonicalWorshipSemanticState.UNAVAILABLE,
    WorshipOwnershipConsistencyState.SELECTED_UNSCHEDULED: CanonicalWorshipSemanticState.SELECTED_UNSCHEDULED,
    WorshipOwnershipConsistencyState.OFF_TEAM_CONFLICT: CanonicalWorshipSemanticState.CONFLICT,
    WorshipOwnershipConsistencyState.OUT_OF_SCOPE_WORSHIP_CONFLICT: CanonicalWorshipSemanticState.CONFLICT,
    WorshipOwnershipConsistencyState.MULTIPLE_CURRENT_WORSHIP_ASSIGNMENTS: CanonicalWorshipSemanticState.AMBIGUOUS,
    WorshipOwnershipConsistencyState.DUPLICATE_SELECTED_TEAM_ASSIGNMENT: CanonicalWorshipSemanticState.AMBIGUOUS,
}

CANONICAL_TO_PRESENTATION_STATE = {
    CanonicalWorshipSemanticState.NO_SELECTION: WORSHIP_CONTEXT_NO_ANCHOR,
    CanonicalWorshipSemanticState.UNAVAILABLE: WORSHIP_CONTEXT_ANCHOR_UNAVAILABLE,
    CanonicalWorshipSemanticState.SELECTED_UNSCHEDULED: WORSHIP_CONTEXT_UNSCHEDULED,
    CanonicalWorshipSemanticState.CONSISTENT_EMPTY: WORSHIP_CONTEXT_EMPTY,
    CanonicalWorshipSemanticState.CONSISTENT_ROSTER: WORSHIP_CONTEXT_SCHEDULED,
    CanonicalWorshipSemanticState.CONFLICT: WORSHIP_CONTEXT_CONFLICT,
    CanonicalWorshipSemanticState.AMBIGUOUS: WORSHIP_CONTEXT_AMBIGUOUS,
}


def _unlinked_display_digest(display_name):
    from .worship_context_review import digest_unlinked_display_identity

    return digest_unlinked_display_identity(display_name)


def build_canonical_worship_contexts(events, *, ownership_inspections=None):
    """Return the one typed semantic used by presentation and fingerprinting."""

    events = list(events)
    ownership_inspections = dict(ownership_inspections or {})
    contexts = {}
    consistent = []
    for event in events:
        inspection = ownership_inspections.get(event.id)
        if inspection is None:
            inspection = inspect_worship_ownership_consistency(event)
            ownership_inspections[event.id] = inspection
        if inspection.state == WorshipOwnershipConsistencyState.CONSISTENT:
            consistent.append((event, inspection))
        else:
            contexts[event.id] = CanonicalWorshipContext(
                selected_team=event.rotation_anchor_team,
                state=OWNERSHIP_TO_CANONICAL_STATE[inspection.state],
            )

    assignment_ids = [
        inspection.matching_assignment_ids[0]
        for _event, inspection in consistent
        if len(inspection.matching_assignment_ids) == 1
    ]
    assignments = (
        TeamAssignment.objects.select_related("ministry_team")
        .prefetch_related(
            Prefetch(
                "assignment_members",
                queryset=(
                    TeamAssignmentMember.objects.select_related(
                        "membership", "membership__user"
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
        .filter(pk__in=assignment_ids, status__in=CURRENT_ASSIGNMENT_STATUSES)
    )
    assignments_by_id = {assignment.pk: assignment for assignment in assignments}

    for event, inspection in consistent:
        assignment = (
            assignments_by_id.get(inspection.matching_assignment_ids[0])
            if len(inspection.matching_assignment_ids) == 1
            else None
        )
        if (
            assignment is None
            or assignment.ministry_team_id != event.rotation_anchor_team_id
        ):
            contexts[event.id] = CanonicalWorshipContext(
                selected_team=event.rotation_anchor_team,
                state=CanonicalWorshipSemanticState.UNAVAILABLE,
                roster_signature_available=False,
            )
            continue

        roster_identities = []
        member_names = []
        signature_available = True
        for assignment_member in assignment.worship_context_members:
            membership = assignment_member.membership
            member_names.append(membership.get_display_name())
            if membership.user_id is not None:
                roster_identities.append(
                    CanonicalWorshipRosterIdentity(
                        membership_id=membership.pk,
                        user_id=membership.user_id,
                    )
                )
                continue
            display_digest = _unlinked_display_digest(membership.display_name)
            if display_digest is None:
                signature_available = False
                continue
            roster_identities.append(
                CanonicalWorshipRosterIdentity(
                    membership_id=membership.pk,
                    user_id=None,
                    display_identity_digest=display_digest,
                )
            )

        contexts[event.id] = CanonicalWorshipContext(
            selected_team=event.rotation_anchor_team,
            state=(
                CanonicalWorshipSemanticState.CONSISTENT_ROSTER
                if member_names
                else CanonicalWorshipSemanticState.CONSISTENT_EMPTY
            ),
            assignment_id=assignment.pk,
            assigned_team_id=assignment.ministry_team_id,
            roster_identities=tuple(roster_identities),
            member_names=tuple(member_names),
            roster_signature_available=signature_available,
        )
    return contexts


def build_worship_contexts(
    events, *, ownership_inspections=None, canonical_contexts=None
):
    """Project existing display behavior from the shared typed semantic."""

    events = list(events)
    canonical_contexts = canonical_contexts or build_canonical_worship_contexts(
        events, ownership_inspections=ownership_inspections
    )
    return {
        event.id: {
            "anchor_team": canonical_contexts[event.id].selected_team,
            "state": CANONICAL_TO_PRESENTATION_STATE[
                canonical_contexts[event.id].state
            ],
            "member_names": list(canonical_contexts[event.id].member_names),
        }
        for event in events
    }
