"""Worship Rotation Planner proposal, signing, and confirmation contract."""

from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID, uuid4

from django.contrib.admin.models import CHANGE, LogEntry
from django.contrib.contenttypes.models import ContentType
from django.core import signing
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from events.models import ServiceEvent
from events.scheduling_revision import claim_scheduling_revisions

from ..models import MinistryTeam, TeamAssignment
from ..permissions import can_change_worship_team
from .worship_governance import (
    CURRENT_WORSHIP_ASSIGNMENT_STATUSES,
    WorshipOwnershipConsistencyState,
    inspect_worship_ownership_consistency,
    resolve_worship_rotation_pool_for_team,
)
from .worship_change_notifications import (
    WorshipTeamChangeFact,
    emit_worship_rotation_change_notifications,
)


PLANNER_CONTRACT_VERSION = 3
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


class WorshipRotationConfirmationError(RuntimeError):
    """The signed proposal no longer confirms against current scheduling truth."""


class WorshipRotationAuditError(WorshipRotationConfirmationError):
    """The shared-operation audit could not be written transactionally."""


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


@dataclass(frozen=True)
class WorshipRotationConfirmationResult:
    operation_id: str
    claimed_event_ids: tuple[int, ...]
    changed_event_ids: tuple[int, ...]


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
            "scheduling_revision": event.scheduling_revision,
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


def _is_positive_int(value):
    return type(value) is int and value > 0


def _is_optional_positive_int(value):
    return value is None or _is_positive_int(value)


def _is_datetime_value(value, *, optional=False):
    if optional and value is None:
        return True
    return isinstance(value, str) and parse_datetime(value) is not None


def _is_id_pair_list(value):
    return isinstance(value, list) and all(
        isinstance(item, list)
        and len(item) == 2
        and all(_is_positive_int(part) for part in item)
        for item in value
    )


def _fingerprint_shape_is_valid(fingerprint, *, event_id, before_team_id):
    if not isinstance(fingerprint, dict) or set(fingerprint) != {
        "event",
        "governance",
        "current_worship",
        "downstream",
    }:
        return False
    event = fingerprint["event"]
    governance = fingerprint["governance"]
    current_worship = fingerprint["current_worship"]
    downstream = fingerprint["downstream"]
    if not isinstance(event, dict) or set(event) != {
        "event_id",
        "scheduling_revision",
        "updated_at",
        "status",
        "event_type",
        "start_datetime",
        "end_datetime",
        "before_team_id",
    }:
        return False
    if (
        event.get("event_id") != event_id
        or type(event.get("scheduling_revision")) is not int
        or event["scheduling_revision"] < 0
        or not _is_datetime_value(event.get("updated_at"))
        or not isinstance(event.get("status"), str)
        or not isinstance(event.get("event_type"), str)
        or not _is_datetime_value(event.get("start_datetime"))
        or not _is_datetime_value(event.get("end_datetime"), optional=True)
        or event.get("before_team_id") != before_team_id
    ):
        return False
    if not isinstance(governance, dict) or set(governance) != {
        "audience_unit_ids",
        "applicable_pools",
        "eligible_candidates",
        "selected_team_eligible",
        "ownership_state",
    }:
        return False
    if (
        not isinstance(governance["audience_unit_ids"], list)
        or any(
            not _is_positive_int(unit_id)
            for unit_id in governance["audience_unit_ids"]
        )
        or not _is_id_pair_list(governance["applicable_pools"])
        or not _is_id_pair_list(governance["eligible_candidates"])
        or type(governance["selected_team_eligible"]) is not bool
        or governance["ownership_state"]
        not in {state.value for state in WorshipOwnershipConsistencyState}
    ):
        return False
    if not isinstance(current_worship, list) or any(
        not isinstance(item, list)
        or len(item) != 7
        or not all(_is_positive_int(part) for part in item[:3])
        or not isinstance(item[3], str)
        or not all(type(part) is bool for part in item[4:])
        for item in current_worship
    ):
        return False
    if not isinstance(downstream, dict) or set(downstream) != {
        "required_team_ids",
        "assignments",
    }:
        return False
    return (
        isinstance(downstream["required_team_ids"], list)
        and all(
            _is_positive_int(team_id)
            for team_id in downstream["required_team_ids"]
        )
        and isinstance(downstream["assignments"], list)
        and all(
            isinstance(item, list)
            and len(item) == 3
            and _is_positive_int(item[0])
            and _is_positive_int(item[1])
            and isinstance(item[2], str)
            for item in downstream["assignments"]
        )
    )


def _validate_decoded_payload_shape(payload):
    event_ids = payload.get("event_ids")
    before_ids = payload.get("before_team_ids")
    proposed_ids = payload.get("proposed_team_ids")
    fingerprints = payload.get("fingerprints")
    inserted_team_id = payload.get("inserted_team_id")
    displaced_tail_team_id = payload.get("displaced_tail_team_id")
    if (
        type(payload.get("previewing_user_id")) is not int
        or payload["previewing_user_id"] <= 0
        or not _is_datetime_value(payload.get("generated_at"))
        or not isinstance(event_ids, list)
        or not MIN_CHAIN_LENGTH <= len(event_ids) <= MAX_CHAIN_LENGTH
        or any(not _is_positive_int(event_id) for event_id in event_ids)
        or len(set(event_ids)) != len(event_ids)
        or not isinstance(before_ids, list)
        or not isinstance(proposed_ids, list)
        or not isinstance(fingerprints, list)
        or not len(event_ids)
        == len(before_ids)
        == len(proposed_ids)
        == len(fingerprints)
        or not _is_positive_int(inserted_team_id)
        or any(not _is_optional_positive_int(value) for value in before_ids)
        or any(not _is_optional_positive_int(value) for value in proposed_ids)
        or not _is_optional_positive_int(displaced_tail_team_id)
        or proposed_ids[0] != inserted_team_id
        or proposed_ids[1:] != before_ids[:-1]
        or displaced_tail_team_id != before_ids[-1]
        or any(
            not _fingerprint_shape_is_valid(
                fingerprint,
                event_id=event_id,
                before_team_id=before_team_id,
            )
            for event_id, before_team_id, fingerprint in zip(
                event_ids,
                before_ids,
                fingerprints,
            )
        )
    ):
        raise SignedProposalError("Invalid proposal shape.")


def extract_expected_scheduling_revisions(payload):
    """Return the exact signed pre-claim revisions without database access."""

    _validate_decoded_payload_shape(payload)
    return tuple(
        (event_id, fingerprint["event"]["scheduling_revision"])
        for event_id, fingerprint in zip(
            payload["event_ids"], payload["fingerprints"]
        )
    )


def decode_signed_worship_rotation_proposal(
    token, *, user, max_age=PLANNER_MAX_AGE_SECONDS
):
    """Decode and fully shape-validate the user-bound v3 proposal."""

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
    _validate_decoded_payload_shape(payload)
    try:
        tail_resolution = TailResolution(payload.get("tail_resolution"))
    except (TypeError, ValueError) as exc:
        raise SignedProposalError("Invalid tail resolution.") from exc
    inserted_team_id = payload.get("inserted_team_id")
    displaced_tail_team_id = payload.get("displaced_tail_team_id")
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


def _post_cas_fingerprints_match(
    *, signed_fingerprints, current_fingerprints, expected_revisions
):
    """Compare all semantic facts while treating revision as the pre-CAS token."""

    if len(signed_fingerprints) != len(current_fingerprints):
        return False
    expected_by_id = dict(expected_revisions)
    for signed, current in zip(signed_fingerprints, current_fingerprints):
        signed_event = signed["event"]
        current_event = current["event"]
        event_id = signed_event["event_id"]
        expected_revision = expected_by_id.get(event_id)
        if (
            expected_revision is None
            or signed_event["scheduling_revision"] != expected_revision
            or current_event.get("scheduling_revision") != expected_revision + 1
        ):
            return False
        if {
            key: value
            for key, value in signed_event.items()
            if key != "scheduling_revision"
        } != {
            key: value
            for key, value in current_event.items()
            if key != "scheduling_revision"
        }:
            return False
        for section in ("governance", "current_worship", "downstream"):
            if signed[section] != current[section]:
                return False
    return True


def revalidated_proposal_matches_signed_payload(
    *, signed_payload, current_proposal, expected_revisions
):
    """Validate recomputed shift semantics without weakening any fingerprint."""

    return (
        list(current_proposal.ordered_event_ids) == signed_payload["event_ids"]
        and getattr(current_proposal.inserted_team, "pk", None)
        == signed_payload["inserted_team_id"]
        and [row.before_team and row.before_team.pk for row in current_proposal.rows]
        == signed_payload["before_team_ids"]
        and [
            row.proposed_team and row.proposed_team.pk
            for row in current_proposal.rows
        ]
        == signed_payload["proposed_team_ids"]
        and getattr(current_proposal.displaced_tail, "pk", None)
        == signed_payload["displaced_tail_team_id"]
        and current_proposal.tail_resolution.value
        == signed_payload["tail_resolution"]
        and _post_cas_fingerprints_match(
            signed_fingerprints=signed_payload["fingerprints"],
            current_fingerprints=[
                row.fingerprints for row in current_proposal.rows
            ],
            expected_revisions=expected_revisions,
        )
    )


def confirm_worship_rotation_proposal(*, user, payload):
    """CAS, fully revalidate, mutate anchors, and audit one atomic batch."""

    expected_revisions = extract_expected_scheduling_revisions(payload)
    event_ids = tuple(payload["event_ids"])
    with transaction.atomic():
        # This conditional UPDATE sequence is intentionally the first scheduling
        # or governance database access in confirmation.
        claim_results = claim_scheduling_revisions(expected_revisions)

        reloaded_ids = tuple(
            ServiceEvent.objects.filter(pk__in=event_ids)
            .order_by("start_datetime", "id")
            .values_list("pk", flat=True)
        )
        if reloaded_ids != event_ids:
            raise WorshipRotationConfirmationError(
                "The exact event chain changed after preview."
            )
        inserted_team = MinistryTeam.objects.filter(
            pk=payload["inserted_team_id"]
        ).first()
        if inserted_team is None:
            raise WorshipRotationConfirmationError(
                "The inserted Worship Team is no longer available."
            )
        current_proposal = build_worship_rotation_proposal(
            user=user,
            event_ids=event_ids,
            inserted_team=inserted_team,
        )
        if not current_proposal.confirmable:
            raise WorshipRotationConfirmationError(
                "The recomputed proposal is not confirmable."
            )
        if not revalidated_proposal_matches_signed_payload(
            signed_payload=payload,
            current_proposal=current_proposal,
            expected_revisions=expected_revisions,
        ):
            raise WorshipRotationConfirmationError(
                "Scheduling or governance truth changed after preview."
            )

        content_type_id = ContentType.objects.get_for_model(ServiceEvent).pk
        changed_event_ids = []
        change_facts = []
        for row in current_proposal.rows:
            if not row.changed:
                continue
            event = row.event
            old_team = row.before_team
            proposed_team = row.proposed_team
            event.rotation_anchor_team = proposed_team
            event.save(
                update_fields=["rotation_anchor_team", "updated_at"],
                _skip_scheduling_revision=True,
            )
            try:
                LogEntry.objects.log_action(
                    user_id=user.pk,
                    content_type_id=content_type_id,
                    object_id=event.pk,
                    object_repr=str(event),
                    action_flag=CHANGE,
                    change_message=(
                        "Worship Rotation Planner batch confirmation "
                        "(MO-S.6D-1D-D-1B-B). "
                        f"operation_id={payload['operation_id']}; "
                        f"old_team_id={getattr(old_team, 'pk', None)!r}; "
                        f"old_team={getattr(old_team, 'name', None)!r}; "
                        f"new_team_id={getattr(proposed_team, 'pk', None)!r}; "
                        f"new_team={getattr(proposed_team, 'name', None)!r}."
                    ),
                )
            except Exception as exc:
                raise WorshipRotationAuditError(
                    "Worship Rotation Planner audit write failed."
                ) from exc
            changed_event_ids.append(event.pk)
            change_facts.append(
                WorshipTeamChangeFact(
                    event_id=event.pk,
                    event_start_datetime=event.start_datetime,
                    old_team_id=getattr(old_team, "pk", None),
                    new_team_id=getattr(proposed_team, "pk", None),
                )
            )

        emit_worship_rotation_change_notifications(
            change_facts,
            operation_id=payload["operation_id"],
            actor=user,
        )

    return WorshipRotationConfirmationResult(
        operation_id=payload["operation_id"],
        claimed_event_ids=tuple(result.event_id for result in claim_results),
        changed_event_ids=tuple(changed_event_ids),
    )
