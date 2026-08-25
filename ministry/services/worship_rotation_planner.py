"""Read-only Worship Rotation Planner proposal and signing contract.

MO-S.6D-1D-D-1A deliberately stops at proposal/preview.  This module performs
no writes and keeps the normalized proposal reusable by the future locked 1B
confirmation slice.
"""

from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID, uuid4

from django.core import signing
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from events.models import ServiceEvent

from ..models import MinistryTeam, TeamAssignment
from ..permissions import can_change_worship_team
from .worship_governance import (
    CURRENT_WORSHIP_ASSIGNMENT_STATUSES,
    WorshipOwnershipConsistencyState,
    inspect_worship_ownership_consistency,
    resolve_worship_rotation_pool_for_team,
)


PLANNER_CONTRACT_VERSION = 2
PLANNER_SIGNING_VERSION = 1
PLANNER_OPERATION_TYPE = "insert_shift_later"
PLANNER_SIGNING_SALT = "ministry.worship-rotation-planner.v1"
PLANNER_MAX_AGE_SECONDS = 1800
MIN_CHAIN_LENGTH = 2
MAX_CHAIN_LENGTH = 53


class PlannerBlocker(StrEnum):
    CHAIN_LENGTH = "chain_length"
    DUPLICATE_EVENT = "duplicate_event"
    EVENT_NOT_FOUND = "event_not_found"
    INVALID_EVENT = "invalid_event"
    NOT_SUNDAY = "not_sunday"
    SAME_SUNDAY = "same_sunday"
    WEEKLY_GAP = "weekly_gap"
    INTERIOR_BLANK = "interior_blank"
    INVALID_SOURCE = "invalid_source"
    DESTINATION_INELIGIBLE = "destination_ineligible"
    UNAUTHORIZED = "unauthorized"
    WORSHIP_ASSIGNMENT = "worship_assignment"
    OWNERSHIP_CONFLICT = "ownership_conflict"
    DISPLACED_TAIL = "displaced_tail"


class TailResolution(StrEnum):
    TERMINAL_BLANK = "terminal_blank"
    CYCLE_CLOSED = "cycle_closed"
    DISPLACED = "displaced"


class SignedProposalError(ValueError):
    pass


class SignedProposalUserMismatch(SignedProposalError):
    pass


@dataclass(frozen=True)
class DownstreamImpact:
    team: MinistryTeam
    participation: str
    assignment_state: str
    statuses: tuple[str, ...]


@dataclass(frozen=True)
class PlannerRow:
    event: ServiceEvent
    before_team: MinistryTeam | None
    proposed_team: MinistryTeam | None
    changed: bool
    destination_eligible: bool
    authorized: bool
    ownership_state: WorshipOwnershipConsistencyState
    worship_assignment_informational: bool
    downstream_impacts: tuple[DownstreamImpact, ...]
    blockers: tuple[PlannerBlocker, ...]
    fingerprints: dict


@dataclass(frozen=True)
class WorshipRotationProposal:
    operation_id: str
    generated_at: str
    previewing_user_id: int
    ordered_event_ids: tuple[int, ...]
    inserted_team: MinistryTeam | None
    rows: tuple[PlannerRow, ...]
    displaced_tail: MinistryTeam | None
    tail_resolution: TailResolution
    blockers: tuple[PlannerBlocker, ...]
    normalized_payload: dict
    signed_payload: str

    @property
    def confirmable(self):
        return not self.blockers


def _team_is_worship(team):
    resolution = resolve_worship_rotation_pool_for_team(team)
    return resolution.pool is not None


def _downstream_projection(event):
    required_team_ids = set(
        event.required_team_links.values_list("ministry_team_id", flat=True)
    )
    assignments = list(
        TeamAssignment.objects.filter(
            service_event=event,
            status__in=CURRENT_WORSHIP_ASSIGNMENT_STATUSES,
        )
        .select_related("ministry_team")
        .order_by("ministry_team_id", "id")
    )
    assignments_by_team = {}
    teams = {}
    for assignment in assignments:
        if _team_is_worship(assignment.ministry_team):
            continue
        teams[assignment.ministry_team_id] = assignment.ministry_team
        assignments_by_team.setdefault(assignment.ministry_team_id, []).append(
            assignment
        )
    for team in MinistryTeam.objects.filter(id__in=required_team_ids).order_by("id"):
        if _team_is_worship(team):
            continue
        teams[team.pk] = team

    impacts = []
    for team_id in sorted(teams):
        team_assignments = assignments_by_team.get(team_id, [])
        if not team_assignments:
            assignment_state = "none"
        elif len(team_assignments) == 1:
            assignment_state = "one"
        else:
            assignment_state = "duplicate"
        impacts.append(
            DownstreamImpact(
                team=teams[team_id],
                participation=(
                    "required" if team_id in required_team_ids else "additional"
                ),
                assignment_state=assignment_state,
                statuses=tuple(
                    assignment.status for assignment in team_assignments
                ),
            )
        )
    fingerprint = {
        "required_team_ids": sorted(
            team_id for team_id in required_team_ids if team_id in teams
        ),
        "assignments": sorted(
            [assignment.pk, assignment.ministry_team_id, assignment.status]
            for assignment in assignments
            if assignment.ministry_team_id in teams
        ),
    }
    return tuple(impacts), fingerprint


def _fingerprints(event, inspection, downstream_fingerprint):
    assignment_statuses = dict(
        TeamAssignment.objects.filter(
            pk__in=[
                item.assignment_id
                for item in inspection.current_worship_assignments
            ]
        ).values_list("id", "status")
    )
    return {
        "event": {
            "event_id": event.pk,
            "updated_at": event.updated_at.isoformat(),
            "status": event.status,
            "event_type": event.event_type,
            "start_datetime": event.start_datetime.isoformat(),
            "end_datetime": (
                event.end_datetime.isoformat() if event.end_datetime else None
            ),
            "before_team_id": event.rotation_anchor_team_id,
        },
        "governance": {
            "audience_unit_ids": sorted(
                event.audience_scope_links.filter(unit__is_active=True)
                .values_list("unit_id", flat=True)
            ),
            "applicable_pools": sorted(
                [item.pool.pk, item.anchor.pk]
                for item in inspection.applicable_pools
            ),
            "eligible_candidates": sorted(
                [item.team.pk, item.owning_pool.pk]
                for item in inspection.eligible_candidates
            ),
            "selected_team_eligible": inspection.selected_team_is_eligible,
            "ownership_state": inspection.state.value,
        },
        "current_worship": sorted(
            [
                item.assignment_id,
                item.team.pk,
                item.owning_pool.pk,
                assignment_statuses.get(item.assignment_id),
                item.pool_is_usable,
                item.pool_is_applicable,
                item.team_is_eligible,
            ]
            for item in inspection.current_worship_assignments
        ),
        "downstream": downstream_fingerprint,
    }


def _unique(values):
    return tuple(dict.fromkeys(values))


def _resolve_tail_resolution(*, inserted_team, displaced_tail):
    if displaced_tail is None:
        return TailResolution.TERMINAL_BLANK
    if inserted_team is not None and displaced_tail.pk == inserted_team.pk:
        return TailResolution.CYCLE_CLOSED
    return TailResolution.DISPLACED


def _cycle_closed_multiset_is_preserved(before_teams, proposed_teams):
    before_ids = sorted(team.pk for team in before_teams if team is not None)
    proposed_ids = sorted(team.pk for team in proposed_teams if team is not None)
    return before_ids == proposed_ids


def build_worship_rotation_proposal(*, user, event_ids, inserted_team, now=None):
    """Build and sign one deterministic, side-effect-free shift proposal."""

    now = now or timezone.now()
    raw_event_ids = tuple(int(event_id) for event_id in event_ids)
    global_blockers = []
    if not MIN_CHAIN_LENGTH <= len(raw_event_ids) <= MAX_CHAIN_LENGTH:
        global_blockers.append(PlannerBlocker.CHAIN_LENGTH)
    if len(set(raw_event_ids)) != len(raw_event_ids):
        global_blockers.append(PlannerBlocker.DUPLICATE_EVENT)

    events_by_id = {
        event.pk: event
        for event in ServiceEvent.objects.filter(pk__in=set(raw_event_ids))
        .select_related("rotation_anchor_team", "host_language_unit")
        .prefetch_related("audience_scope_links__unit", "required_team_links__ministry_team")
    }
    if set(events_by_id) != set(raw_event_ids):
        global_blockers.append(PlannerBlocker.EVENT_NOT_FOUND)
    events = sorted(
        events_by_id.values(), key=lambda event: (event.start_datetime, event.pk)
    )

    local_dates = []
    for event in events:
        local_start = timezone.localtime(event.start_datetime)
        local_dates.append(local_start.date())
        if (
            event.event_type != ServiceEvent.EVENT_SUNDAY_SERVICE
            or event.status != ServiceEvent.STATUS_PUBLISHED
            or event.start_datetime <= now
        ):
            global_blockers.append(PlannerBlocker.INVALID_EVENT)
        if local_start.weekday() != 6:
            global_blockers.append(PlannerBlocker.NOT_SUNDAY)
    if len(set(local_dates)) != len(local_dates):
        global_blockers.append(PlannerBlocker.SAME_SUNDAY)
    if any(
        (current - previous).days != 7
        for previous, current in zip(local_dates, local_dates[1:])
    ):
        global_blockers.append(PlannerBlocker.WEEKLY_GAP)

    before_teams = [event.rotation_anchor_team for event in events]
    if any(team is None for team in before_teams[:-1]):
        global_blockers.append(PlannerBlocker.INTERIOR_BLANK)
    displaced_tail = before_teams[-1] if before_teams else None
    tail_resolution = _resolve_tail_resolution(
        inserted_team=inserted_team,
        displaced_tail=displaced_tail,
    )
    if tail_resolution == TailResolution.DISPLACED:
        global_blockers.append(PlannerBlocker.DISPLACED_TAIL)

    proposed_teams = []
    if events:
        proposed_teams = [inserted_team, *before_teams[:-1]]
    if (
        tail_resolution == TailResolution.CYCLE_CLOSED
        and not _cycle_closed_multiset_is_preserved(before_teams, proposed_teams)
    ):
        raise ValueError(
            "Cycle-closed shift did not preserve the selected-range team multiset."
        )

    rows = []
    all_blockers = list(global_blockers)
    conflict_states = {
        WorshipOwnershipConsistencyState.INVALID_SELECTION,
        WorshipOwnershipConsistencyState.OFF_TEAM_CONFLICT,
        WorshipOwnershipConsistencyState.OUT_OF_SCOPE_WORSHIP_CONFLICT,
        WorshipOwnershipConsistencyState.MULTIPLE_CURRENT_WORSHIP_ASSIGNMENTS,
        WorshipOwnershipConsistencyState.DUPLICATE_SELECTED_TEAM_ASSIGNMENT,
    }
    for event, proposed_team in zip(events, proposed_teams):
        inspection = inspect_worship_ownership_consistency(event)
        changed = event.rotation_anchor_team_id != getattr(proposed_team, "pk", None)
        eligible_ids = {
            candidate.team.pk for candidate in inspection.eligible_candidates
        }
        destination_eligible = (
            proposed_team is not None and proposed_team.pk in eligible_ids
        )
        authorized = (not changed) or can_change_worship_team(user, event)
        row_blockers = []
        if inspection.state in conflict_states:
            row_blockers.append(PlannerBlocker.OWNERSHIP_CONFLICT)
        if not destination_eligible:
            row_blockers.append(PlannerBlocker.DESTINATION_INELIGIBLE)
        if not authorized:
            row_blockers.append(PlannerBlocker.UNAUTHORIZED)
        if changed and inspection.current_worship_assignments:
            row_blockers.append(PlannerBlocker.WORSHIP_ASSIGNMENT)
        if (
            event.rotation_anchor_team_id is not None
            and not inspection.selected_team_is_eligible
        ):
            row_blockers.append(PlannerBlocker.INVALID_SOURCE)

        downstream, downstream_fingerprint = _downstream_projection(event)
        fingerprints = _fingerprints(
            event, inspection, downstream_fingerprint
        )
        row = PlannerRow(
            event=event,
            before_team=event.rotation_anchor_team,
            proposed_team=proposed_team,
            changed=changed,
            destination_eligible=destination_eligible,
            authorized=authorized,
            ownership_state=inspection.state,
            worship_assignment_informational=(
                not changed
                and inspection.state == WorshipOwnershipConsistencyState.CONSISTENT
                and len(inspection.current_worship_assignments) == 1
            ),
            downstream_impacts=downstream,
            blockers=_unique(row_blockers),
            fingerprints=fingerprints,
        )
        rows.append(row)
        all_blockers.extend(row.blockers)

    operation_id = str(uuid4())
    generated_at = now.isoformat()
    payload = {
        "contract_version": PLANNER_CONTRACT_VERSION,
        "signing_version": PLANNER_SIGNING_VERSION,
        "operation_type": PLANNER_OPERATION_TYPE,
        "operation_id": operation_id,
        "generated_at": generated_at,
        "previewing_user_id": user.pk,
        "event_ids": [event.pk for event in events],
        "inserted_team_id": getattr(inserted_team, "pk", None),
        "before_team_ids": [event.rotation_anchor_team_id for event in events],
        "proposed_team_ids": [
            getattr(team, "pk", None) for team in proposed_teams
        ],
        "displaced_tail_team_id": getattr(displaced_tail, "pk", None),
        "tail_resolution": tail_resolution.value,
        "fingerprints": [row.fingerprints for row in rows],
    }
    signed_payload = signing.dumps(
        payload, compress=True, salt=PLANNER_SIGNING_SALT
    )
    return WorshipRotationProposal(
        operation_id=operation_id,
        generated_at=generated_at,
        previewing_user_id=user.pk,
        ordered_event_ids=tuple(event.pk for event in events),
        inserted_team=inserted_team,
        rows=tuple(rows),
        displaced_tail=displaced_tail,
        tail_resolution=tail_resolution,
        blockers=_unique(all_blockers),
        normalized_payload=payload,
        signed_payload=signed_payload,
    )


def decode_signed_worship_rotation_proposal(
    token, *, user, max_age=PLANNER_MAX_AGE_SECONDS
):
    """Decode and validate the reusable 1B proposal boundary."""

    try:
        payload = signing.loads(
            token, salt=PLANNER_SIGNING_SALT, max_age=max_age
        )
    except signing.BadSignature as exc:
        raise SignedProposalError("Invalid or expired proposal.") from exc
    if not isinstance(payload, dict):
        raise SignedProposalError("Invalid proposal shape.")
    if (
        payload.get("contract_version") != PLANNER_CONTRACT_VERSION
        or payload.get("signing_version") != PLANNER_SIGNING_VERSION
        or payload.get("operation_type") != PLANNER_OPERATION_TYPE
    ):
        raise SignedProposalError("Unsupported proposal contract.")
    try:
        UUID(str(payload.get("operation_id")))
    except (TypeError, ValueError) as exc:
        raise SignedProposalError("Invalid operation identifier.") from exc
    if (
        not getattr(user, "is_authenticated", False)
        or not getattr(user, "is_active", False)
        or payload.get("previewing_user_id") != user.pk
    ):
        raise SignedProposalUserMismatch("Proposal belongs to another user.")
    event_ids = payload.get("event_ids")
    before_ids = payload.get("before_team_ids")
    proposed_ids = payload.get("proposed_team_ids")
    fingerprints = payload.get("fingerprints")
    try:
        tail_resolution = TailResolution(payload.get("tail_resolution"))
    except (TypeError, ValueError) as exc:
        raise SignedProposalError("Invalid tail resolution.") from exc
    inserted_team_id = payload.get("inserted_team_id")
    displaced_tail_team_id = payload.get("displaced_tail_team_id")
    team_id_values = [
        payload.get("inserted_team_id"),
        payload.get("displaced_tail_team_id"),
        *(before_ids if isinstance(before_ids, list) else []),
        *(proposed_ids if isinstance(proposed_ids, list) else []),
    ]
    if (
        not isinstance(payload.get("previewing_user_id"), int)
        or parse_datetime(payload.get("generated_at") or "") is None
        or not isinstance(event_ids, list)
        or not MIN_CHAIN_LENGTH <= len(event_ids) <= MAX_CHAIN_LENGTH
        or any(not isinstance(event_id, int) for event_id in event_ids)
        or len(set(event_ids)) != len(event_ids)
        or not isinstance(before_ids, list)
        or not isinstance(proposed_ids, list)
        or not isinstance(fingerprints, list)
        or not len(event_ids) == len(before_ids) == len(proposed_ids) == len(fingerprints)
        or any(value is not None and not isinstance(value, int) for value in team_id_values)
        or any(not isinstance(item, dict) for item in fingerprints)
    ):
        raise SignedProposalError("Invalid proposal shape.")
    tail_resolution_is_consistent = (
        tail_resolution == TailResolution.TERMINAL_BLANK
        and displaced_tail_team_id is None
    ) or (
        tail_resolution == TailResolution.CYCLE_CLOSED
        and inserted_team_id is not None
        and displaced_tail_team_id == inserted_team_id
    ) or (
        tail_resolution == TailResolution.DISPLACED
        and displaced_tail_team_id is not None
        and displaced_tail_team_id != inserted_team_id
    )
    if not tail_resolution_is_consistent:
        raise SignedProposalError("Inconsistent tail resolution.")
    return payload
