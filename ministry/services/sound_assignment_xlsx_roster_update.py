"""Atomic MO-S.6F.1C Sound roster fill/replacement confirmation.

The existing MO-S.6F.1B create-only contract remains in
``sound_assignment_xlsx_confirmation``.  This module owns a separate signed
authority for batches that contain at least one existing-assignment roster
mutation.  Its first SQLite write is a conditional, value-preserving update on
each mutation parent before any roster, assignment, or audit business write.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
import re
from uuid import UUID, uuid4

from django.contrib.admin.models import ADDITION, CHANGE, LogEntry
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core import signing
from django.core.exceptions import ValidationError
from django.db import IntegrityError, OperationalError, transaction
from django.db.models import F
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from core.integration_registry import IntegrationDisabled, require_integration_enabled
from events.models import ServiceEvent
from events.scheduling_revision import (
    SchedulingRevisionBusyError,
    SchedulingRevisionError,
    claim_scheduling_revisions,
)
from events.service_profile_readiness import service_event_audience_readiness
from events.service_profile_runtime import inspect_service_profile_identity

from ..models import TeamAssignment, TeamAssignmentMember, TeamMembership
from .sound_assignment_xlsx_confirmation import (
    SoundAssignmentConfirmationAuditError,
    SoundAssignmentConfirmationBusy,
    SoundAssignmentConfirmationError,
    SoundAssignmentConfirmationProposalError,
    _audit_message as _create_audit_message,
    _canonical_json,
    _digest,
    _expected_date_for_source_row,
    user_can_confirm_sound_assignments,
)
from .sound_assignment_xlsx_preview import (
    INTEGRATION_KEY,
    PREVIEW_CONTRACT_REVISION,
    SOURCE_COLUMN,
    SOURCE_CONTRACT_REVISION,
    SOURCE_SEMANTIC,
    SVCA_SOUND_TEAM_KEY,
    WORSHIP_PARSER_CONTRACT_REVISION,
    SignedSoundPreviewError,
    SoundDestinationTeamError,
    SoundMappingStateError,
    SoundSourceState,
    SoundTargetState,
    _assignment_queryset,
    _classify_assignment,
    _event_is_historical_for_assignment_import,
    _membership_candidate,
    _membership_is_outside_event_audience,
    decode_signed_sound_assignment_preview,
    resolve_destination_team,
    resolve_target_service_profile,
)
from .worship_governance import inspect_worship_ownership_consistency
from .worship_xlsx_preview import (
    SIGNING_MAX_AGE_SECONDS,
    SUPPORTED_EVENT_TYPE,
    SUPPORTED_LOCAL_TIME,
    SUPPORTED_PROFILE_KEY,
    SUPPORTED_ROWS,
    TOKEN_ORDER,
    TargetServiceProfileError,
)


ROSTER_UPDATE_PROPOSAL_TYPE = "sound_assignment_roster_update_confirmation"
ROSTER_UPDATE_CONTRACT_REVISION = "SOUND_ASSIGNMENT_ROSTER_UPDATE_CONFIRMATION_V1"
ROSTER_UPDATE_SIGNING_VERSION = 1
ROSTER_UPDATE_SIGNING_SALT = "ministry.sound-assignment-roster-update.v1"
ROSTER_UPDATE_MAX_AGE_SECONDS = SIGNING_MAX_AGE_SECONDS

SAFE_NON_WRITE_STATES = frozenset(
    {
        SoundTargetState.NO_SOURCE_PROPOSAL,
        SoundTargetState.EXACT_NOOP,
        SoundTargetState.HISTORICAL_EVENT_BLOCKER,
    }
)
MUTATION_STATES = frozenset(
    {SoundTargetState.FILL_CANDIDATE, SoundTargetState.REPLACE_CANDIDATE}
)
CONFIRMABLE_STATES = SAFE_NON_WRITE_STATES | MUTATION_STATES | {
    SoundTargetState.CREATE_CANDIDATE
}

_SHA256_RE = re.compile(r"^[0-9A-F]{64}$")


@dataclass(frozen=True)
class SoundRosterUpdateProposal:
    operation_id: str
    normalized_payload: dict
    signed_payload: str
    create_count: int
    fill_count: int
    replace_count: int
    exact_noop_count: int
    historical_event_count: int
    no_source_count: int

    @property
    def signed_payload_bytes(self):
        return len(self.signed_payload.encode("utf-8"))

    @property
    def is_roster_update(self):
        return True


@dataclass(frozen=True)
class SoundRosterUpdateResult:
    operation_id: str
    workbook_sha256: str
    created_assignment_ids: tuple[int, ...]
    created_member_ids: tuple[int, ...]
    filled_assignment_ids: tuple[int, ...]
    replaced_assignment_ids: tuple[int, ...]
    removed_member_ids: tuple[int, ...]
    added_member_ids: tuple[int, ...]
    claimed_event_ids: tuple[int, ...]
    log_entry_count: int

    @property
    def created_count(self):
        return len(self.created_assignment_ids)

    @property
    def filled_count(self):
        return len(self.filled_assignment_ids)

    @property
    def replaced_count(self):
        return len(self.replaced_assignment_ids)


def _text_digest(value):
    return sha256(value.encode("utf-8")).hexdigest().upper()


def _valid_datetime(value, *, nullable=False):
    return (nullable and value is None) or (
        isinstance(value, str) and parse_datetime(value) is not None
    )


def _valid_hash(value):
    return isinstance(value, str) and _SHA256_RE.fullmatch(value) is not None


def _valid_membership_baseline(value):
    if not isinstance(value, dict) or set(value) != {
        "id",
        "team_id",
        "active",
        "updated_at",
        "linked_user_id",
        "linked_user_active",
        "visible_identity_digest",
    }:
        return False
    linked_id = value["linked_user_id"]
    return bool(
        type(value["id"]) is int
        and value["id"] > 0
        and type(value["team_id"]) is int
        and value["team_id"] > 0
        and type(value["active"]) is bool
        and _valid_datetime(value["updated_at"])
        and (
            linked_id is None
            and value["linked_user_active"] is None
            or type(linked_id) is int
            and linked_id > 0
            and type(value["linked_user_active"]) is bool
        )
        and _valid_hash(value["visible_identity_digest"])
    )


def _validate_assignment_baseline(value):
    if not isinstance(value, list):
        return False
    assignment_keys = {
        "id",
        "event_id",
        "team_id",
        "status",
        "created_at",
        "updated_at",
        "notes_digest",
        "created_by_id",
        "reviewed_worship_context_fingerprint",
        "members",
    }
    member_keys = {
        "id",
        "membership_id",
        "created_at",
        "confirmed_at",
        "confirmation_note_present",
        "confirmation_note_digest",
        "membership",
    }
    assignment_ids = set()
    member_ids = set()
    for assignment in value:
        fingerprint = (
            assignment.get("reviewed_worship_context_fingerprint")
            if isinstance(assignment, dict)
            else None
        )
        if (
            not isinstance(assignment, dict)
            or set(assignment) != assignment_keys
            or type(assignment["id"]) is not int
            or assignment["id"] <= 0
            or assignment["id"] in assignment_ids
            or type(assignment["event_id"]) is not int
            or assignment["event_id"] <= 0
            or type(assignment["team_id"]) is not int
            or assignment["team_id"] <= 0
            or assignment["status"] not in dict(TeamAssignment.STATUS_CHOICES)
            or not _valid_datetime(assignment["created_at"])
            or not _valid_datetime(assignment["updated_at"])
            or not _valid_hash(assignment["notes_digest"])
            or assignment["created_by_id"] is not None
            and (
                type(assignment["created_by_id"]) is not int
                or assignment["created_by_id"] <= 0
            )
            or fingerprint is not None
            and (not isinstance(fingerprint, str) or len(fingerprint) > 64)
            or not isinstance(assignment["members"], list)
        ):
            return False
        assignment_ids.add(assignment["id"])
        for member in assignment["members"]:
            if (
                not isinstance(member, dict)
                or set(member) != member_keys
                or type(member["id"]) is not int
                or member["id"] <= 0
                or member["id"] in member_ids
                or type(member["membership_id"]) is not int
                or member["membership_id"] <= 0
                or not _valid_datetime(member["created_at"])
                or not _valid_datetime(member["confirmed_at"], nullable=True)
                or type(member["confirmation_note_present"]) is not bool
                or not _valid_hash(member["confirmation_note_digest"])
                or not _valid_membership_baseline(member["membership"])
                or member["membership"]["id"] != member["membership_id"]
            ):
                return False
            member_ids.add(member["id"])
    return True


def _membership_baseline(membership):
    candidate = _membership_candidate(membership)
    return {
        "id": membership.pk,
        "team_id": membership.team_id,
        "active": membership.is_active,
        "updated_at": membership.updated_at.isoformat(),
        "linked_user_id": candidate.linked_user_id,
        "linked_user_active": candidate.linked_user_active,
        "visible_identity_digest": candidate.identity_digest,
    }


def _assignment_baseline(assignments):
    return [
        {
            "id": assignment.pk,
            "event_id": assignment.service_event_id,
            "team_id": assignment.ministry_team_id,
            "status": assignment.status,
            "created_at": assignment.created_at.isoformat(),
            "updated_at": assignment.updated_at.isoformat(),
            "notes_digest": _text_digest(assignment.notes),
            "created_by_id": assignment.created_by_id,
            "reviewed_worship_context_fingerprint": (
                assignment.reviewed_worship_context_fingerprint
            ),
            "members": [
                {
                    "id": member.pk,
                    "membership_id": member.membership_id,
                    "created_at": member.created_at.isoformat(),
                    "confirmed_at": (
                        member.confirmed_at.isoformat()
                        if member.confirmed_at is not None
                        else None
                    ),
                    "confirmation_note_present": bool(member.confirmation_note),
                    "confirmation_note_digest": _text_digest(
                        member.confirmation_note
                    ),
                    "membership": _membership_baseline(member.membership),
                }
                for member in assignment.assignment_members.all()
            ],
        }
        for assignment in assignments
    ]


def _governance_facts(event):
    inspection = inspect_worship_ownership_consistency(event)
    return {
        "state": inspection.state.value,
        "selected_team_id": (
            inspection.selected_team.pk if inspection.selected_team else None
        ),
        "selected_team_is_eligible": inspection.selected_team_is_eligible,
        "current_assignments": [
            {
                "assignment_id": item.assignment_id,
                "team_id": item.team.pk,
                "pool_is_applicable": item.pool_is_applicable,
                "team_is_eligible": item.team_is_eligible,
            }
            for item in inspection.current_worship_assignments
        ],
    }


def _event_baseline(event, *, now):
    local_start = timezone.localtime(event.start_datetime)
    audience = service_event_audience_readiness(event)
    return {
        "id": event.pk,
        "scheduling_revision": event.scheduling_revision,
        "status": event.status,
        "service_profile_id": event.service_profile_id,
        "expected_profile_key": event.service_profile.key,
        "local_date": local_start.date().isoformat(),
        "local_time": local_start.time().replace(tzinfo=None).isoformat(),
        "event_type": event.event_type,
        "historical": _event_is_historical_for_assignment_import(event, now=now),
        "audience_ready": audience["ready"],
        "audience_readiness_digest": _digest(audience),
        "worship_governance_digest": _digest(_governance_facts(event)),
    }


def _source_baseline(source):
    return {
        "row": source.source_row,
        "cell": source.source_cell,
        "local_date": source.local_date.isoformat(),
        "date_kind": source.date_kind,
        "worship_token": source.worship_token,
        "source_state": source.source_state.value,
        "token_digest": (
            _text_digest(source.normalized_token)
            if source.normalized_token is not None
            else None
        ),
    }


def _mutation_baseline(state, assignments, destination_membership_id):
    if state == SoundTargetState.CREATE_CANDIDATE:
        return {
            "action": "create",
            "assignment_id": None,
            "removed_assignment_member_id": None,
            "removed_membership_id": None,
            "added_membership_id": destination_membership_id,
        }
    if state == SoundTargetState.FILL_CANDIDATE:
        return {
            "action": "fill",
            "assignment_id": assignments[0].pk,
            "removed_assignment_member_id": None,
            "removed_membership_id": None,
            "added_membership_id": destination_membership_id,
        }
    if state == SoundTargetState.REPLACE_CANDIDATE:
        member = list(assignments[0].assignment_members.all())[0]
        return {
            "action": "replace",
            "assignment_id": assignments[0].pk,
            "removed_assignment_member_id": member.pk,
            "removed_membership_id": member.membership_id,
            "added_membership_id": destination_membership_id,
        }
    return None


def _strict_payload_shape(payload):
    top_keys = {
        "proposal_type",
        "confirmation_contract_revision",
        "confirmation_signing_version",
        "preview_contract_revision",
        "source_contract_revision",
        "worship_parser_contract_revision",
        "integration_key",
        "source_semantic",
        "source_column",
        "generated_at",
        "user_id",
        "operation_id",
        "workbook_sha256",
        "preview_digest",
        "profile",
        "team",
        "summary",
        "rows",
    }
    if not isinstance(payload, dict) or set(payload) != top_keys:
        raise SoundAssignmentConfirmationProposalError(
            "Invalid Sound roster-update proposal shape."
        )
    try:
        operation_id = UUID(payload["operation_id"])
    except (AttributeError, TypeError, ValueError) as exc:
        raise SoundAssignmentConfirmationProposalError(
            "Invalid Sound roster-update operation identifier."
        ) from exc
    if (
        payload["proposal_type"] != ROSTER_UPDATE_PROPOSAL_TYPE
        or payload["confirmation_contract_revision"]
        != ROSTER_UPDATE_CONTRACT_REVISION
        or payload["confirmation_signing_version"]
        != ROSTER_UPDATE_SIGNING_VERSION
        or payload["preview_contract_revision"] != PREVIEW_CONTRACT_REVISION
        or payload["source_contract_revision"] != SOURCE_CONTRACT_REVISION
        or payload["worship_parser_contract_revision"]
        != WORSHIP_PARSER_CONTRACT_REVISION
        or payload["integration_key"] != INTEGRATION_KEY
        or payload["source_semantic"] != SOURCE_SEMANTIC
        or payload["source_column"] != SOURCE_COLUMN
        or type(payload["user_id"]) is not int
        or payload["user_id"] <= 0
        or not _valid_datetime(payload["generated_at"])
        or str(operation_id) != payload["operation_id"]
        or not _valid_hash(payload["workbook_sha256"])
        or not _valid_hash(payload["preview_digest"])
    ):
        raise SoundAssignmentConfirmationProposalError(
            "Invalid Sound roster-update contract facts."
        )
    profile = payload["profile"]
    team = payload["team"]
    if (
        not isinstance(profile, dict)
        or set(profile) != {"id", "key", "event_type", "active"}
        or type(profile["id"]) is not int
        or profile["id"] <= 0
        or profile["key"] != SUPPORTED_PROFILE_KEY
        or profile["event_type"] != SUPPORTED_EVENT_TYPE
        or profile["active"] is not True
        or not isinstance(team, dict)
        or set(team) != {"id", "key", "active", "assignable", "updated_at"}
        or type(team["id"]) is not int
        or team["id"] <= 0
        or team["key"] != SVCA_SOUND_TEAM_KEY
        or team["active"] is not True
        or team["assignable"] is not True
        or not _valid_datetime(team["updated_at"])
    ):
        raise SoundAssignmentConfirmationProposalError(
            "Invalid Sound roster-update profile or team identity."
        )
    rows = payload["rows"]
    if not isinstance(rows, list) or len(rows) != len(SUPPORTED_ROWS):
        raise SoundAssignmentConfirmationProposalError(
            "Invalid Sound roster-update row count."
        )
    states = []
    seen_events = set()
    for expected_source_row, row in zip(SUPPORTED_ROWS, rows, strict=True):
        if not isinstance(row, dict) or set(row) != {
            "source",
            "target_state",
            "event",
            "destination_membership",
            "assignment_baseline",
            "mutation",
        }:
            raise SoundAssignmentConfirmationProposalError(
                "Invalid Sound roster-update row shape."
            )
        source = row["source"]
        try:
            state = SoundTargetState(row["target_state"])
        except (TypeError, ValueError) as exc:
            raise SoundAssignmentConfirmationProposalError(
                "Invalid Sound roster-update row state."
            ) from exc
        if (
            state not in CONFIRMABLE_STATES
            or not isinstance(source, dict)
            or set(source)
            != {
                "row",
                "cell",
                "local_date",
                "date_kind",
                "worship_token",
                "source_state",
                "token_digest",
            }
            or source.get("row") != expected_source_row
            or source.get("cell") != f"{SOURCE_COLUMN}{expected_source_row}"
            or source.get("local_date")
            != _expected_date_for_source_row(expected_source_row).isoformat()
            or source.get("date_kind")
            != ("literal" if expected_source_row == 4 else "formula_cached")
            or source.get("worship_token") not in TOKEN_ORDER
        ):
            raise SoundAssignmentConfirmationProposalError(
                "Invalid Sound roster-update source facts."
            )
        states.append(state)
        if state == SoundTargetState.NO_SOURCE_PROPOSAL:
            if (
                source.get("source_state")
                != SoundSourceState.NO_SOURCE_PROPOSAL.value
                or source.get("token_digest") is not None
                or row["event"] is not None
                or row["destination_membership"] is not None
                or row["assignment_baseline"] != []
                or row["mutation"] is not None
            ):
                raise SoundAssignmentConfirmationProposalError(
                    "Invalid blank Sound roster-update row."
                )
            continue
        event = row["event"]
        destination = row["destination_membership"]
        if (
            source.get("source_state") != SoundSourceState.SUPPORTED_LITERAL.value
            or not _valid_hash(source.get("token_digest"))
            or not isinstance(event, dict)
            or set(event)
            != {
                "id",
                "scheduling_revision",
                "status",
                "service_profile_id",
                "expected_profile_key",
                "local_date",
                "local_time",
                "event_type",
                "historical",
                "audience_ready",
                "audience_readiness_digest",
                "worship_governance_digest",
            }
            or type(event.get("id")) is not int
            or event["id"] <= 0
            or event["id"] in seen_events
            or event.get("service_profile_id") != profile["id"]
            or event.get("expected_profile_key") != SUPPORTED_PROFILE_KEY
            or event.get("event_type") != SUPPORTED_EVENT_TYPE
            or event.get("status")
            not in {ServiceEvent.STATUS_PUBLISHED, ServiceEvent.STATUS_COMPLETED}
            or type(event.get("scheduling_revision")) is not int
            or event["scheduling_revision"] < 0
            or type(event.get("historical")) is not bool
            or event.get("audience_ready") is not True
            or not _valid_hash(event.get("audience_readiness_digest"))
            or not _valid_hash(event.get("worship_governance_digest"))
            or event.get("local_date") != source.get("local_date")
            or event.get("local_time") != SUPPORTED_LOCAL_TIME.isoformat()
            or not isinstance(destination, dict)
            or not _valid_membership_baseline(destination)
            or destination.get("team_id") != team["id"]
            or destination.get("active") is not True
            or not _validate_assignment_baseline(row["assignment_baseline"])
        ):
            raise SoundAssignmentConfirmationProposalError(
                "Invalid Sound roster-update target facts."
            )
        seen_events.add(event["id"])
        mutation = row["mutation"]
        if state in MUTATION_STATES | {SoundTargetState.CREATE_CANDIDATE}:
            expected_action = {
                SoundTargetState.CREATE_CANDIDATE: "create",
                SoundTargetState.FILL_CANDIDATE: "fill",
                SoundTargetState.REPLACE_CANDIDATE: "replace",
            }[state]
            if (
                not isinstance(mutation, dict)
                or set(mutation)
                != {
                    "action",
                    "assignment_id",
                    "removed_assignment_member_id",
                    "removed_membership_id",
                    "added_membership_id",
                }
                or mutation.get("action") != expected_action
                or mutation.get("added_membership_id") != destination.get("id")
            ):
                raise SoundAssignmentConfirmationProposalError(
                    "Invalid Sound roster-update mutation facts."
                )
            baseline = row["assignment_baseline"]
            if state == SoundTargetState.CREATE_CANDIDATE:
                valid_mutation_shape = (
                    baseline == []
                    and mutation["assignment_id"] is None
                    and mutation["removed_assignment_member_id"] is None
                    and mutation["removed_membership_id"] is None
                )
            elif state == SoundTargetState.FILL_CANDIDATE:
                valid_mutation_shape = (
                    len(baseline) == 1
                    and baseline[0]["event_id"] == event["id"]
                    and baseline[0]["team_id"] == team["id"]
                    and baseline[0]["status"] == TeamAssignment.STATUS_SCHEDULED
                    and (
                        baseline[0]["reviewed_worship_context_fingerprint"] is None
                        or _valid_hash(
                            baseline[0]["reviewed_worship_context_fingerprint"]
                        )
                    )
                    and baseline[0]["members"] == []
                    and mutation["assignment_id"] == baseline[0]["id"]
                    and mutation["removed_assignment_member_id"] is None
                    and mutation["removed_membership_id"] is None
                )
            else:
                valid_mutation_shape = (
                    len(baseline) == 1
                    and baseline[0]["event_id"] == event["id"]
                    and baseline[0]["team_id"] == team["id"]
                    and baseline[0]["status"] == TeamAssignment.STATUS_SCHEDULED
                    and (
                        baseline[0]["reviewed_worship_context_fingerprint"] is None
                        or _valid_hash(
                            baseline[0]["reviewed_worship_context_fingerprint"]
                        )
                    )
                    and len(baseline[0]["members"]) == 1
                    and baseline[0]["members"][0]["membership"]["active"] is True
                    and baseline[0]["members"][0]["confirmed_at"] is None
                    and baseline[0]["members"][0]["confirmation_note_present"]
                    is False
                    and baseline[0]["members"][0]["confirmation_note_digest"]
                    == _text_digest("")
                    and baseline[0]["members"][0]["membership_id"]
                    != destination["id"]
                    and mutation["assignment_id"] == baseline[0]["id"]
                    and mutation["removed_assignment_member_id"]
                    == baseline[0]["members"][0]["id"]
                    and mutation["removed_membership_id"]
                    == baseline[0]["members"][0]["membership_id"]
                )
            if not valid_mutation_shape:
                raise SoundAssignmentConfirmationProposalError(
                    "Invalid Sound roster-update mutation baseline."
                )
        elif mutation is not None:
            raise SoundAssignmentConfirmationProposalError(
                "A non-write Sound row contains mutation authority."
            )
    counts = {
        "create_count": states.count(SoundTargetState.CREATE_CANDIDATE),
        "fill_count": states.count(SoundTargetState.FILL_CANDIDATE),
        "replace_count": states.count(SoundTargetState.REPLACE_CANDIDATE),
        "exact_noop_count": states.count(SoundTargetState.EXACT_NOOP),
        "historical_event_count": states.count(
            SoundTargetState.HISTORICAL_EVENT_BLOCKER
        ),
        "no_source_count": states.count(SoundTargetState.NO_SOURCE_PROPOSAL),
        "hard_blocker_count": 0,
    }
    if (
        payload["summary"] != counts
        or counts["fill_count"] + counts["replace_count"] <= 0
    ):
        raise SoundAssignmentConfirmationProposalError(
            "The Sound roster-update proposal is not confirmable."
        )
    return payload


def build_sound_roster_update_proposal(*, preview, user):
    """Mint 1C authority only when the safe preview contains a roster update."""

    if (
        not user_can_confirm_sound_assignments(user)
        or preview.mapping_review.parsed is None
        or preview.hard_blocker_count
        or preview.fill_candidate_count + preview.replace_candidate_count <= 0
    ):
        raise SoundAssignmentConfirmationProposalError(
            "The reviewed Sound roster-update preview is not confirmable."
        )
    if any(row.target_state not in CONFIRMABLE_STATES for row in preview.rows):
        raise SoundAssignmentConfirmationProposalError(
            "The reviewed Sound roster-update preview contains a hard blocker."
        )

    now = timezone.now()
    if preview.normalized_payload.get("user_id") != user.pk:
        raise SoundAssignmentConfirmationProposalError(
            "The reviewed Sound roster-update preview belongs to another user."
        )
    try:
        decode_signed_sound_assignment_preview(
            preview.signed_payload, user=user, now=now
        )
    except (
        SignedSoundPreviewError,
        SoundDestinationTeamError,
        TargetServiceProfileError,
        SoundMappingStateError,
    ) as exc:
        raise SoundAssignmentConfirmationProposalError(
            "The reviewed Sound roster-update preview became stale."
        ) from exc
    profile = resolve_target_service_profile()
    team = resolve_destination_team(SVCA_SOUND_TEAM_KEY)
    reviewed_team = preview.mapping_review.team
    if (
        reviewed_team.pk != team.pk
        or reviewed_team.team_key != team.team_key
        or reviewed_team.is_active != team.is_active
        or reviewed_team.is_assignable != team.is_assignable
        or reviewed_team.updated_at.isoformat() != team.updated_at.isoformat()
    ):
        raise SoundAssignmentConfirmationProposalError(
            "The reviewed Sound destination team became stale."
        )
    rows = []
    for preview_row in preview.rows:
        state = preview_row.target_state
        source = preview_row.source
        row = {
            "source": _source_baseline(source),
            "target_state": state.value,
            "event": None,
            "destination_membership": None,
            "assignment_baseline": [],
            "mutation": None,
        }
        if state != SoundTargetState.NO_SOURCE_PROPOSAL:
            event = ServiceEvent.objects.select_related("service_profile").prefetch_related(
                "audience_scope_links__unit"
            ).get(pk=preview_row.event.pk)
            destination = TeamMembership.objects.select_related("user").get(
                pk=preview_row.selected_membership.membership_id
            )
            assignments = list(_assignment_queryset((event.pk,), team))
            current_members = [
                member
                for assignment in assignments
                if assignment.status
                in {
                    TeamAssignment.STATUS_SCHEDULED,
                    TeamAssignment.STATUS_CONFIRMED,
                    TeamAssignment.STATUS_PREPARED,
                }
                for member in assignment.assignment_members.all()
            ]
            if preview_row.current_membership is not None and (
                len(current_members) != 1
                or _membership_candidate(current_members[0].membership)
                != preview_row.current_membership
            ):
                raise SoundAssignmentConfirmationProposalError(
                    "The reviewed current Sound roster identity became stale."
                )
            current_state, _current_ids, _roster, _historical_ids = (
                _classify_assignment(assignments, destination.pk)
            )
            if _event_is_historical_for_assignment_import(event, now=now):
                current_state = SoundTargetState.HISTORICAL_EVENT_BLOCKER
            elif _membership_is_outside_event_audience(
                _membership_candidate(destination), event
            ):
                current_state = SoundTargetState.AUDIENCE_SAFETY_BLOCKER
            if current_state != state:
                raise SoundAssignmentConfirmationProposalError(
                    "The reviewed Sound roster-update preview became stale."
                )
            row.update(
                {
                    "event": _event_baseline(event, now=now),
                    "destination_membership": _membership_baseline(destination),
                    "assignment_baseline": _assignment_baseline(assignments),
                    "mutation": _mutation_baseline(
                        state, assignments, destination.pk
                    ),
                }
            )
        rows.append(row)

    payload = {
        "proposal_type": ROSTER_UPDATE_PROPOSAL_TYPE,
        "confirmation_contract_revision": ROSTER_UPDATE_CONTRACT_REVISION,
        "confirmation_signing_version": ROSTER_UPDATE_SIGNING_VERSION,
        "preview_contract_revision": PREVIEW_CONTRACT_REVISION,
        "source_contract_revision": SOURCE_CONTRACT_REVISION,
        "worship_parser_contract_revision": WORSHIP_PARSER_CONTRACT_REVISION,
        "integration_key": INTEGRATION_KEY,
        "source_semantic": SOURCE_SEMANTIC,
        "source_column": SOURCE_COLUMN,
        "generated_at": now.isoformat(),
        "user_id": user.pk,
        "operation_id": str(uuid4()),
        "workbook_sha256": preview.mapping_review.parsed.sha256,
        "preview_digest": _digest(preview.normalized_payload),
        "profile": {
            "id": profile.pk,
            "key": profile.key,
            "event_type": profile.event_type,
            "active": profile.is_active,
        },
        "team": {
            "id": team.pk,
            "key": team.team_key,
            "active": team.is_active,
            "assignable": team.is_assignable,
            "updated_at": team.updated_at.isoformat(),
        },
        "summary": {
            "create_count": preview.create_candidate_count,
            "fill_count": preview.fill_candidate_count,
            "replace_count": preview.replace_candidate_count,
            "exact_noop_count": preview.exact_noop_count,
            "historical_event_count": preview.historical_event_count,
            "no_source_count": preview.no_source_count,
            "hard_blocker_count": preview.hard_blocker_count,
        },
        "rows": rows,
    }
    _strict_payload_shape(payload)
    signed = signing.dumps(
        payload, compress=True, salt=ROSTER_UPDATE_SIGNING_SALT
    )
    return SoundRosterUpdateProposal(
        operation_id=payload["operation_id"],
        normalized_payload=payload,
        signed_payload=signed,
        create_count=payload["summary"]["create_count"],
        fill_count=payload["summary"]["fill_count"],
        replace_count=payload["summary"]["replace_count"],
        exact_noop_count=payload["summary"]["exact_noop_count"],
        historical_event_count=payload["summary"]["historical_event_count"],
        no_source_count=payload["summary"]["no_source_count"],
    )


def decode_signed_sound_roster_update(
    token, *, user, max_age=ROSTER_UPDATE_MAX_AGE_SECONDS
):
    try:
        payload = signing.loads(
            token, salt=ROSTER_UPDATE_SIGNING_SALT, max_age=max_age
        )
    except signing.BadSignature as exc:
        raise SoundAssignmentConfirmationProposalError(
            "Invalid or expired Sound roster-update proposal."
        ) from exc
    _strict_payload_shape(payload)
    if (
        not user_can_confirm_sound_assignments(user)
        or payload["user_id"] != getattr(user, "pk", None)
    ):
        raise SoundAssignmentConfirmationProposalError(
            "The Sound roster-update proposal belongs to another user."
        )
    return payload


def _conditional_assignment_barriers(update_rows):
    for row in sorted(update_rows, key=lambda item: item["mutation"]["assignment_id"]):
        assignment = row["assignment_baseline"][0]
        query = TeamAssignment.objects.filter(
            pk=assignment["id"],
            service_event_id=assignment["event_id"],
            ministry_team_id=assignment["team_id"],
            status=TeamAssignment.STATUS_SCHEDULED,
            updated_at=parse_datetime(assignment["updated_at"]),
        )
        fingerprint = assignment["reviewed_worship_context_fingerprint"]
        if fingerprint is None:
            query = query.filter(reviewed_worship_context_fingerprint__isnull=True)
        else:
            query = query.filter(reviewed_worship_context_fingerprint=fingerprint)
        matched = query.update(
            reviewed_worship_context_fingerprint=F(
                "reviewed_worship_context_fingerprint"
            )
        )
        if matched != 1:
            raise SoundAssignmentConfirmationError(
                "A reviewed Sound assignment changed before the writer barrier."
            )


def _load_current_truth(payload, *, create_revision_claimed):
    now = timezone.now()
    try:
        profile = resolve_target_service_profile()
        team = resolve_destination_team(SVCA_SOUND_TEAM_KEY)
    except (TargetServiceProfileError, SoundDestinationTeamError) as exc:
        raise SoundAssignmentConfirmationError(
            "The Sound assignment profile or destination team changed after review."
        ) from exc
    if payload["profile"] != {
        "id": profile.pk,
        "key": profile.key,
        "event_type": profile.event_type,
        "active": profile.is_active,
    } or payload["team"] != {
        "id": team.pk,
        "key": team.team_key,
        "active": team.is_active,
        "assignable": team.is_assignable,
        "updated_at": team.updated_at.isoformat(),
    }:
        raise SoundAssignmentConfirmationError(
            "The Sound assignment profile or destination team changed after review."
        )

    material = [
        row
        for row in payload["rows"]
        if row["target_state"] != SoundTargetState.NO_SOURCE_PROPOSAL.value
    ]
    event_ids = [row["event"]["id"] for row in material]
    membership_ids = [row["destination_membership"]["id"] for row in material]
    events = {
        event.pk: event
        for event in ServiceEvent.objects.filter(pk__in=event_ids)
        .select_related("service_profile")
        .prefetch_related("audience_scope_links__unit")
    }
    memberships = {
        membership.pk: membership
        for membership in TeamMembership.objects.filter(pk__in=membership_ids)
        .select_related("user")
    }
    assignments_by_event = {}
    for assignment in _assignment_queryset(event_ids, team):
        assignments_by_event.setdefault(assignment.service_event_id, []).append(
            assignment
        )

    for row in material:
        state = SoundTargetState(row["target_state"])
        event = events.get(row["event"]["id"])
        destination = memberships.get(row["destination_membership"]["id"])
        if event is None or destination is None:
            raise SoundAssignmentConfirmationError(
                "A reviewed Sound event or membership no longer exists."
            )
        expected_event = deepcopy(row["event"])
        if create_revision_claimed and state == SoundTargetState.CREATE_CANDIDATE:
            expected_event["scheduling_revision"] += 1
        identity = inspect_service_profile_identity(event)
        if (
            not identity.is_exact
            or event.service_profile_id != profile.pk
            or _event_baseline(event, now=now) != expected_event
            or _membership_baseline(destination) != row["destination_membership"]
            or not destination.is_active
            or destination.team_id != team.pk
        ):
            raise SoundAssignmentConfirmationError(
                "A reviewed Sound event, audience, governance, or membership changed."
            )
        assignments = assignments_by_event.get(event.pk, [])
        if _assignment_baseline(assignments) != row["assignment_baseline"]:
            raise SoundAssignmentConfirmationError(
                "A reviewed Sound assignment or complete roster baseline changed."
            )
        current_state, _current_ids, _roster, _history = _classify_assignment(
            assignments, destination.pk
        )
        if _event_is_historical_for_assignment_import(event, now=now):
            current_state = SoundTargetState.HISTORICAL_EVENT_BLOCKER
        elif _membership_is_outside_event_audience(
            _membership_candidate(destination), event
        ):
            current_state = SoundTargetState.AUDIENCE_SAFETY_BLOCKER
        if current_state != state:
            raise SoundAssignmentConfirmationError(
                "A reviewed Sound row is no longer in its approved state."
            )
    return team, events, memberships, assignments_by_event


def _update_audit_message(*, payload, row):
    mutation = row["mutation"]
    return _canonical_json(
        {
            "action": mutation["action"],
            "added_membership_id": mutation["added_membership_id"],
            "assignment_id": mutation["assignment_id"],
            "confirmation_contract_revision": ROSTER_UPDATE_CONTRACT_REVISION,
            "event_id": row["event"]["id"],
            "operation_id": payload["operation_id"],
            "removed_membership_id": mutation["removed_membership_id"],
            "sound_team": {
                "id": payload["team"]["id"],
                "team_key": payload["team"]["key"],
            },
            "workbook_sha256": payload["workbook_sha256"],
        }
    )


def _assert_postconditions(
    *, payload, actor, team, created, changed, audit_messages
):
    content_type_id = ContentType.objects.get_for_model(TeamAssignment).pk
    for row, assignment, member in created:
        event = ServiceEvent.objects.get(pk=row["event"]["id"])
        persisted = list(_assignment_queryset((event.pk,), team))
        members = list(
            TeamAssignmentMember.objects.filter(assignment_id=assignment.pk).order_by(
                "id"
            )
        )
        if (
            event.scheduling_revision != row["event"]["scheduling_revision"] + 1
            or len(persisted) != 1
            or persisted[0].pk != assignment.pk
            or assignment.status != TeamAssignment.STATUS_SCHEDULED
            or assignment.notes != ""
            or assignment.created_by_id != actor.pk
            or assignment.reviewed_worship_context_fingerprint is not None
            or len(members) != 1
            or members[0].pk != member.pk
            or members[0].membership_id != row["destination_membership"]["id"]
            or _membership_baseline(members[0].membership)
            != row["destination_membership"]
            or members[0].confirmed_at is not None
            or members[0].confirmation_note != ""
        ):
            raise SoundAssignmentConfirmationError(
                "A created Sound assignment failed its exact postconditions."
            )

    for row, added_member in changed:
        baseline = row["assignment_baseline"][0]
        assignment = TeamAssignment.objects.get(pk=baseline["id"])
        members = list(
            TeamAssignmentMember.objects.filter(assignment=assignment)
            .select_related("membership", "membership__user")
            .order_by("id")
        )
        parent_now = _assignment_baseline([assignment])[0]
        parent_now_without_members = {**parent_now, "members": baseline["members"]}
        if (
            parent_now_without_members != baseline
            or len(members) != 1
            or members[0].pk != added_member.pk
            or members[0].membership_id != row["destination_membership"]["id"]
            or _membership_baseline(members[0].membership)
            != row["destination_membership"]
            or not members[0].membership.is_active
            or members[0].membership.team_id != team.pk
            or members[0].confirmed_at is not None
            or members[0].confirmation_note != ""
            or (
                row["mutation"]["removed_assignment_member_id"] is not None
                and TeamAssignmentMember.objects.filter(
                    pk=row["mutation"]["removed_assignment_member_id"]
                ).exists()
            )
        ):
            raise SoundAssignmentConfirmationError(
                "A Sound roster update failed its exact postconditions."
            )

    expected_logs = len(created) + len(changed)
    matching_logs = 0
    for assignment_id, (flag, message) in audit_messages.items():
        matching_logs += LogEntry.objects.filter(
            user_id=actor.pk,
            content_type_id=content_type_id,
            object_id=str(assignment_id),
            action_flag=flag,
            change_message=message,
        ).count()
    if matching_logs != expected_logs:
        raise SoundAssignmentConfirmationError(
            "The Sound roster-update audit postcondition failed."
        )

    mutation_states = {
        SoundTargetState.CREATE_CANDIDATE.value,
        SoundTargetState.FILL_CANDIDATE.value,
        SoundTargetState.REPLACE_CANDIDATE.value,
    }
    for row in payload["rows"]:
        if (
            row["target_state"]
            not in mutation_states | {SoundTargetState.NO_SOURCE_PROPOSAL.value}
        ):
            event = ServiceEvent.objects.select_related("service_profile").prefetch_related(
                "audience_scope_links__unit"
            ).get(pk=row["event"]["id"])
            destination = TeamMembership.objects.select_related("user").get(
                pk=row["destination_membership"]["id"]
            )
            assignments = list(_assignment_queryset((event.pk,), team))
            if (
                _event_baseline(event, now=timezone.now()) != row["event"]
                or _membership_baseline(destination)
                != row["destination_membership"]
                or _assignment_baseline(assignments) != row["assignment_baseline"]
            ):
                raise SoundAssignmentConfirmationError(
                    "A safe non-write Sound row changed during confirmation."
                )


def confirm_sound_roster_update(*, user, payload):
    """Apply one mixed 1C batch with deterministic assignment barriers."""

    _strict_payload_shape(payload)
    if payload["user_id"] != getattr(user, "pk", None):
        raise SoundAssignmentConfirmationProposalError(
            "The Sound roster-update proposal belongs to another user."
        )
    create_rows = [
        row
        for row in payload["rows"]
        if row["target_state"] == SoundTargetState.CREATE_CANDIDATE.value
    ]
    update_rows = [
        row
        for row in payload["rows"]
        if row["target_state"]
        in {
            SoundTargetState.FILL_CANDIDATE.value,
            SoundTargetState.REPLACE_CANDIDATE.value,
        }
    ]
    expected_revisions = {
        row["event"]["id"]: row["event"]["scheduling_revision"]
        for row in sorted(create_rows, key=lambda item: item["event"]["id"])
    }
    claim_results = []
    created = []
    changed = []
    removed_ids = []
    audit_messages = {}

    try:
        with transaction.atomic():
            actor = get_user_model()._default_manager.filter(pk=user.pk).first()
            if actor is None or not user_can_confirm_sound_assignments(actor):
                raise SoundAssignmentConfirmationError(
                    "Sound roster-update authority changed after review."
                )
            try:
                require_integration_enabled(INTEGRATION_KEY)
            except IntegrationDisabled as exc:
                raise SoundAssignmentConfirmationError(
                    "The annual workbook integration is no longer enabled."
                ) from exc

            _conditional_assignment_barriers(update_rows)
            if expected_revisions:
                claim_results = claim_scheduling_revisions(expected_revisions)

            actor = get_user_model()._default_manager.filter(pk=user.pk).first()
            if actor is None or not user_can_confirm_sound_assignments(actor):
                raise SoundAssignmentConfirmationError(
                    "Sound roster-update authority changed after the writer barrier."
                )
            try:
                require_integration_enabled(INTEGRATION_KEY)
            except IntegrationDisabled as exc:
                raise SoundAssignmentConfirmationError(
                    "The annual workbook integration became unavailable after the writer barrier."
                ) from exc

            team, events, memberships, assignments_by_event = _load_current_truth(
                payload, create_revision_claimed=bool(expected_revisions)
            )
            content_type_id = ContentType.objects.get_for_model(TeamAssignment).pk

            for row in sorted(create_rows, key=lambda item: item["event"]["id"]):
                event = events[row["event"]["id"]]
                membership = memberships[row["destination_membership"]["id"]]
                assignment = TeamAssignment(
                    service_event=event,
                    ministry_team=team,
                    status=TeamAssignment.STATUS_SCHEDULED,
                    notes="",
                    created_by=actor,
                    reviewed_worship_context_fingerprint=None,
                )
                assignment.save(force_insert=True, _skip_scheduling_revision=True)
                member = TeamAssignmentMember(
                    assignment=assignment,
                    membership=membership,
                    confirmed_at=None,
                    confirmation_note="",
                )
                member.save(force_insert=True)
                message = _create_audit_message(
                    payload=payload, assignment=assignment, membership=membership
                )
                try:
                    LogEntry.objects.log_action(
                        user_id=actor.pk,
                        content_type_id=content_type_id,
                        object_id=assignment.pk,
                        object_repr=f"TeamAssignment {assignment.pk}",
                        action_flag=ADDITION,
                        change_message=message,
                    )
                except Exception as exc:
                    raise SoundAssignmentConfirmationAuditError(
                        "Sound assignment audit write failed; the batch was rolled back."
                    ) from exc
                created.append((row, assignment, member))
                audit_messages[assignment.pk] = (ADDITION, message)

            for row in sorted(
                update_rows, key=lambda item: item["mutation"]["assignment_id"]
            ):
                mutation = row["mutation"]
                assignment = assignments_by_event[row["event"]["id"]][0]
                if mutation["action"] == "replace":
                    deleted, details = TeamAssignmentMember.objects.filter(
                        pk=mutation["removed_assignment_member_id"],
                        assignment_id=mutation["assignment_id"],
                        membership_id=mutation["removed_membership_id"],
                        confirmed_at__isnull=True,
                        confirmation_note="",
                    ).delete()
                    label = TeamAssignmentMember._meta.label
                    if deleted != 1 or details.get(label) != 1:
                        raise SoundAssignmentConfirmationError(
                            "The reviewed Sound assignment-member delete became stale."
                        )
                    removed_ids.append(mutation["removed_assignment_member_id"])
                member = TeamAssignmentMember(
                    assignment=assignment,
                    membership=memberships[mutation["added_membership_id"]],
                    confirmed_at=None,
                    confirmation_note="",
                )
                member.save(force_insert=True)
                message = _update_audit_message(payload=payload, row=row)
                try:
                    LogEntry.objects.log_action(
                        user_id=actor.pk,
                        content_type_id=content_type_id,
                        object_id=assignment.pk,
                        object_repr=f"TeamAssignment {assignment.pk}",
                        action_flag=CHANGE,
                        change_message=message,
                    )
                except Exception as exc:
                    raise SoundAssignmentConfirmationAuditError(
                        "Sound roster-update audit write failed; the batch was rolled back."
                    ) from exc
                changed.append((row, member))
                audit_messages[assignment.pk] = (CHANGE, message)

            actor = get_user_model()._default_manager.get(pk=user.pk)
            if not user_can_confirm_sound_assignments(actor):
                raise SoundAssignmentConfirmationError(
                    "Sound roster-update authority changed during apply."
                )
            _assert_postconditions(
                payload=payload,
                actor=actor,
                team=team,
                created=created,
                changed=changed,
                audit_messages=audit_messages,
            )
    except SchedulingRevisionBusyError as exc:
        raise SoundAssignmentConfirmationBusy(
            "Scheduling is busy; no Sound assignment was changed."
        ) from exc
    except SchedulingRevisionError as exc:
        raise SoundAssignmentConfirmationError(
            "A reviewed event revision is stale; the batch was rolled back."
        ) from exc
    except OperationalError as exc:
        message = str(exc).lower()
        if "database is locked" in message or "database table is locked" in message:
            raise SoundAssignmentConfirmationBusy(
                "Scheduling is busy; no Sound assignment was changed."
            ) from exc
        raise
    except (IntegrityError, ValidationError, SoundMappingStateError) as exc:
        raise SoundAssignmentConfirmationError(
            "Current Sound roster validation changed; the batch was rolled back."
        ) from exc

    return SoundRosterUpdateResult(
        operation_id=payload["operation_id"],
        workbook_sha256=payload["workbook_sha256"],
        created_assignment_ids=tuple(item[1].pk for item in created),
        created_member_ids=tuple(item[2].pk for item in created),
        filled_assignment_ids=tuple(
            item[0]["mutation"]["assignment_id"]
            for item in changed
            if item[0]["mutation"]["action"] == "fill"
        ),
        replaced_assignment_ids=tuple(
            item[0]["mutation"]["assignment_id"]
            for item in changed
            if item[0]["mutation"]["action"] == "replace"
        ),
        removed_member_ids=tuple(removed_ids),
        added_member_ids=tuple(item[1].pk for item in changed),
        claimed_event_ids=tuple(item.event_id for item in claim_results),
        log_entry_count=len(created) + len(changed),
    )
