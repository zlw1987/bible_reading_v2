"""Create-only atomic confirmation for reviewed Column-F Sound assignments.

MO-S.6F.1A remains evidence-only.  This module owns the distinct, expiring,
user-bound MO-S.6F.1B write proposal and its single transaction.  The first
write is the canonical expected-revision CAS for exactly the create events;
the later TeamAssignment saves retain normal validation while deliberately
skipping only their otherwise duplicate scheduling-revision advance.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import date, timedelta
from hashlib import sha256
import json
import re
from uuid import UUID, uuid4

from django.contrib.admin.models import ADDITION, LogEntry
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core import signing
from django.core.exceptions import ValidationError
from django.db import IntegrityError, OperationalError, transaction
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
from .sound_assignment_xlsx_preview import (
    INTEGRATION_KEY,
    PREVIEW_CONTRACT_REVISION,
    SOURCE_COLUMN,
    SOURCE_CONTRACT_REVISION,
    SOURCE_SEMANTIC,
    SVCA_SOUND_TEAM_KEY,
    WORSHIP_PARSER_CONTRACT_REVISION,
    SoundDestinationTeamError,
    SoundMappingStateError,
    SoundSourceState,
    SoundTargetState,
    _assignment_baseline,
    _assignment_queryset,
    _classify_assignment,
    _event_is_historical_for_assignment_import,
    _event_payload,
    _identity_digest,
    _membership_candidate,
    _membership_is_outside_event_audience,
    resolve_destination_team,
    resolve_target_service_profile,
    user_can_preview_sound_assignments,
)
from .worship_xlsx_preview import (
    SIGNING_MAX_AGE_SECONDS,
    SUPPORTED_EVENT_TYPE,
    SUPPORTED_LOCAL_TIME,
    SUPPORTED_PROFILE_KEY,
    SUPPORTED_ROWS,
    TOKEN_ORDER,
    TargetServiceProfileError,
)


CONFIRMATION_PROPOSAL_TYPE = "sound_assignment_create_only_confirmation"
CONFIRMATION_CONTRACT_REVISION = "SOUND_ASSIGNMENT_CONFIRMATION_V1"
CONFIRMATION_SIGNING_VERSION = 1
CONFIRMATION_SIGNING_SALT = "ministry.sound-assignment-confirmation.v1"
CONFIRMATION_MAX_AGE_SECONDS = SIGNING_MAX_AGE_SECONDS

SAFE_NON_WRITE_STATES = frozenset(
    {
        SoundTargetState.NO_SOURCE_PROPOSAL,
        SoundTargetState.EXACT_NOOP,
        SoundTargetState.HISTORICAL_EVENT_BLOCKER,
    }
)
CONFIRMABLE_STATES = SAFE_NON_WRITE_STATES | {SoundTargetState.CREATE_CANDIDATE}

_SHA256_RE = re.compile(r"^[0-9A-F]{64}$")
_FINGERPRINT_RE = re.compile(r"^[0-9A-Fa-f]{64}$")


class SoundAssignmentConfirmationProposalError(ValueError):
    """The separate 1B proposal is malformed, expired, or user-mismatched."""


class SoundAssignmentConfirmationError(RuntimeError):
    """Current truth no longer permits the reviewed all-or-nothing create."""


class SoundAssignmentConfirmationBusy(SoundAssignmentConfirmationError):
    pass


class SoundAssignmentConfirmationAuditError(SoundAssignmentConfirmationError):
    pass


@dataclass(frozen=True)
class SoundAssignmentConfirmationProposal:
    operation_id: str
    normalized_payload: dict
    signed_payload: str
    create_count: int
    exact_noop_count: int
    historical_event_count: int
    no_source_count: int

    @property
    def signed_payload_bytes(self):
        return len(self.signed_payload.encode("utf-8"))


@dataclass(frozen=True)
class SoundAssignmentConfirmationResult:
    operation_id: str
    workbook_sha256: str
    created_assignment_ids: tuple[int, ...]
    created_member_ids: tuple[int, ...]
    claimed_event_ids: tuple[int, ...]
    log_entry_count: int

    @property
    def created_count(self):
        return len(self.created_assignment_ids)


def user_can_confirm_sound_assignments(user):
    return user_can_preview_sound_assignments(user)


def _canonical_json(value):
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )


def _digest(value):
    return sha256(_canonical_json(value).encode("utf-8")).hexdigest().upper()


def _is_positive_int(value):
    return type(value) is int and value > 0


def _is_nonnegative_int(value):
    return type(value) is int and value >= 0


def _filename_is_sanitized(value):
    return (
        isinstance(value, str)
        and 0 < len(value) <= 255
        and "\x00" not in value
        and "/" not in value
        and "\\" not in value
        and value not in {".", ".."}
    )


def _expected_date_for_source_row(source_row):
    index = 0 if source_row == 4 else source_row - 5
    return date(2026, 1, 4) + timedelta(weeks=index)


def _validate_assignment_baseline(value):
    if not isinstance(value, list):
        raise SoundAssignmentConfirmationProposalError(
            "Invalid Sound assignment baseline."
        )
    assignment_keys = {
        "id",
        "status",
        "updated_at",
        "reviewed_worship_context_fingerprint",
        "members",
    }
    member_keys = {
        "assignment_member_id",
        "membership_id",
        "membership_active",
        "confirmed",
    }
    seen_assignments = set()
    for assignment in value:
        if (
            not isinstance(assignment, dict)
            or set(assignment) != assignment_keys
            or not _is_positive_int(assignment["id"])
            or assignment["id"] in seen_assignments
            or assignment["status"] not in dict(TeamAssignment.STATUS_CHOICES)
            or not isinstance(assignment["updated_at"], str)
            or parse_datetime(assignment["updated_at"]) is None
            or assignment["reviewed_worship_context_fingerprint"] is not None
            and (
                not isinstance(
                    assignment["reviewed_worship_context_fingerprint"], str
                )
                or _FINGERPRINT_RE.fullmatch(
                    assignment["reviewed_worship_context_fingerprint"]
                )
                is None
            )
            or not isinstance(assignment["members"], list)
        ):
            raise SoundAssignmentConfirmationProposalError(
                "Invalid Sound assignment baseline."
            )
        seen_assignments.add(assignment["id"])
        seen_members = set()
        for member in assignment["members"]:
            if (
                not isinstance(member, dict)
                or set(member) != member_keys
                or not _is_positive_int(member["assignment_member_id"])
                or not _is_positive_int(member["membership_id"])
                or type(member["membership_active"]) is not bool
                or type(member["confirmed"]) is not bool
                or member["assignment_member_id"] in seen_members
            ):
                raise SoundAssignmentConfirmationProposalError(
                    "Invalid Sound assignment-member baseline."
                )
            seen_members.add(member["assignment_member_id"])


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
        "filename",
        "workbook_sha256",
        "preview_digest",
        "profile",
        "team",
        "summary",
        "rows",
    }
    if not isinstance(payload, dict) or set(payload) != top_keys:
        raise SoundAssignmentConfirmationProposalError(
            "Invalid Sound confirmation proposal shape."
        )
    try:
        operation_id = UUID(payload["operation_id"])
    except (AttributeError, TypeError, ValueError) as exc:
        raise SoundAssignmentConfirmationProposalError(
            "Invalid Sound confirmation operation identifier."
        ) from exc
    if (
        payload["proposal_type"] != CONFIRMATION_PROPOSAL_TYPE
        or payload["confirmation_contract_revision"]
        != CONFIRMATION_CONTRACT_REVISION
        or payload["confirmation_signing_version"] != CONFIRMATION_SIGNING_VERSION
        or payload["preview_contract_revision"] != PREVIEW_CONTRACT_REVISION
        or payload["source_contract_revision"] != SOURCE_CONTRACT_REVISION
        or payload["worship_parser_contract_revision"]
        != WORSHIP_PARSER_CONTRACT_REVISION
        or payload["integration_key"] != INTEGRATION_KEY
        or payload["source_semantic"] != SOURCE_SEMANTIC
        or payload["source_column"] != SOURCE_COLUMN
        or not _is_positive_int(payload["user_id"])
        or not isinstance(payload["generated_at"], str)
        or parse_datetime(payload["generated_at"]) is None
        or str(operation_id) != payload["operation_id"]
        or not _filename_is_sanitized(payload["filename"])
        or not isinstance(payload["workbook_sha256"], str)
        or _SHA256_RE.fullmatch(payload["workbook_sha256"]) is None
        or not isinstance(payload["preview_digest"], str)
        or _SHA256_RE.fullmatch(payload["preview_digest"]) is None
    ):
        raise SoundAssignmentConfirmationProposalError(
            "Invalid Sound confirmation contract facts."
        )

    if payload["profile"] != {
        "id": payload["profile"].get("id") if isinstance(payload["profile"], dict) else None,
        "key": SUPPORTED_PROFILE_KEY,
        "event_type": SUPPORTED_EVENT_TYPE,
    } or not _is_positive_int(payload["profile"]["id"]):
        raise SoundAssignmentConfirmationProposalError(
            "Invalid Sound confirmation Service Profile identity."
        )
    if payload["team"] != {
        "id": payload["team"].get("id") if isinstance(payload["team"], dict) else None,
        "key": SVCA_SOUND_TEAM_KEY,
        "active": True,
        "assignable": True,
    } or not _is_positive_int(payload["team"]["id"]):
        raise SoundAssignmentConfirmationProposalError(
            "Invalid Sound confirmation team identity."
        )

    rows = payload["rows"]
    row_keys = {
        "source",
        "target_state",
        "event",
        "membership",
        "assignment_baseline",
    }
    source_keys = {
        "row",
        "cell",
        "local_date",
        "date_kind",
        "worship_token",
        "source_state",
        "token_digest",
    }
    event_keys = {
        "id",
        "service_profile_id",
        "expected_profile_key",
        "scheduling_revision",
        "local_date",
        "local_time",
        "event_type",
        "status",
    }
    membership_keys = {
        "id",
        "team_id",
        "active",
        "updated_at",
        "linked_user_id",
        "linked_user_active",
        "visible_identity_digest",
    }
    if not isinstance(rows, list) or len(rows) != len(SUPPORTED_ROWS):
        raise SoundAssignmentConfirmationProposalError(
            "Invalid Sound confirmation row count."
        )
    seen_event_ids = set()
    states = []
    for expected_source_row, row in zip(SUPPORTED_ROWS, rows, strict=True):
        if not isinstance(row, dict) or set(row) != row_keys:
            raise SoundAssignmentConfirmationProposalError(
                "Invalid Sound confirmation row shape."
            )
        source = row["source"]
        try:
            state = SoundTargetState(row["target_state"])
            source_state = SoundSourceState(source["source_state"])
            local_date = date.fromisoformat(source["local_date"])
        except (KeyError, TypeError, ValueError) as exc:
            raise SoundAssignmentConfirmationProposalError(
                "Invalid Sound confirmation row facts."
            ) from exc
        if (
            not isinstance(source, dict)
            or set(source) != source_keys
            or state not in CONFIRMABLE_STATES
            or source["row"] != expected_source_row
            or source["cell"] != f"{SOURCE_COLUMN}{expected_source_row}"
            or local_date != _expected_date_for_source_row(expected_source_row)
            or source["date_kind"]
            != ("literal" if expected_source_row == 4 else "formula_cached")
            or source["worship_token"] not in TOKEN_ORDER
        ):
            raise SoundAssignmentConfirmationProposalError(
                "Invalid Sound confirmation source facts."
            )

        states.append(state)
        if state == SoundTargetState.NO_SOURCE_PROPOSAL:
            if (
                source_state != SoundSourceState.NO_SOURCE_PROPOSAL
                or source["token_digest"] is not None
                or row["event"] is not None
                or row["membership"] is not None
                or row["assignment_baseline"] != []
            ):
                raise SoundAssignmentConfirmationProposalError(
                    "Invalid blank Sound confirmation row."
                )
            continue

        event = row["event"]
        membership = row["membership"]
        if (
            source_state != SoundSourceState.SUPPORTED_LITERAL
            or not isinstance(source["token_digest"], str)
            or _SHA256_RE.fullmatch(source["token_digest"]) is None
            or not isinstance(event, dict)
            or set(event) != event_keys
            or not _is_positive_int(event["id"])
            or event["id"] in seen_event_ids
            or event["service_profile_id"] != payload["profile"]["id"]
            or event["expected_profile_key"] != SUPPORTED_PROFILE_KEY
            or not _is_nonnegative_int(event["scheduling_revision"])
            or event["local_date"] != source["local_date"]
            or event["local_time"] != SUPPORTED_LOCAL_TIME.isoformat()
            or event["event_type"] != SUPPORTED_EVENT_TYPE
            or event["status"]
            not in {ServiceEvent.STATUS_PUBLISHED, ServiceEvent.STATUS_COMPLETED}
            or not isinstance(membership, dict)
            or set(membership) != membership_keys
            or not _is_positive_int(membership["id"])
            or membership["team_id"] != payload["team"]["id"]
            or membership["active"] is not True
            or not isinstance(membership["updated_at"], str)
            or parse_datetime(membership["updated_at"]) is None
            or membership["linked_user_id"] is not None
            and not _is_positive_int(membership["linked_user_id"])
            or membership["linked_user_id"] is None
            and membership["linked_user_active"] is not None
            or membership["linked_user_id"] is not None
            and type(membership["linked_user_active"]) is not bool
            or not isinstance(membership["visible_identity_digest"], str)
            or _SHA256_RE.fullmatch(membership["visible_identity_digest"]) is None
        ):
            raise SoundAssignmentConfirmationProposalError(
                "Invalid Sound confirmation target facts."
            )
        seen_event_ids.add(event["id"])
        _validate_assignment_baseline(row["assignment_baseline"])
        if state == SoundTargetState.CREATE_CANDIDATE and row["assignment_baseline"]:
            raise SoundAssignmentConfirmationProposalError(
                "A create candidate has a non-empty assignment baseline."
            )

    counts = {
        "create_count": states.count(SoundTargetState.CREATE_CANDIDATE),
        "exact_noop_count": states.count(SoundTargetState.EXACT_NOOP),
        "historical_event_count": states.count(
            SoundTargetState.HISTORICAL_EVENT_BLOCKER
        ),
        "no_source_count": states.count(SoundTargetState.NO_SOURCE_PROPOSAL),
        "hard_blocker_count": 0,
    }
    if payload["summary"] != counts or counts["create_count"] <= 0:
        raise SoundAssignmentConfirmationProposalError(
            "The Sound confirmation proposal is not confirmable."
        )
    return payload


def _proposal_membership_payload(value):
    return {
        "id": value["id"],
        "team_id": value["team_id"],
        "active": value["active"],
        "updated_at": value["updated_at"],
        "linked_user_id": value["linked_user_id"],
        "linked_user_active": value["linked_user_active"],
        "visible_identity_digest": value["visible_identity_digest"],
    }


def build_sound_assignment_confirmation_proposal(*, preview, user):
    """Mint the distinct 1B authority only from a fully safe 1A review."""

    if not user_can_confirm_sound_assignments(user):
        raise SoundAssignmentConfirmationProposalError(
            "Current user cannot confirm Sound assignments."
        )
    if len(preview.rows) != len(SUPPORTED_ROWS) or not preview.is_confirmable:
        raise SoundAssignmentConfirmationProposalError(
            "The reviewed Sound assignment preview is not confirmable."
        )
    if (
        preview.normalized_payload.get("contract_revision")
        != PREVIEW_CONTRACT_REVISION
        or preview.normalized_payload.get("source_contract_revision")
        != SOURCE_CONTRACT_REVISION
        or preview.normalized_payload.get("worship_parser_contract_revision")
        != WORSHIP_PARSER_CONTRACT_REVISION
        or preview.normalized_payload.get("integration_key") != INTEGRATION_KEY
        or preview.normalized_payload.get("source_semantic") != SOURCE_SEMANTIC
        or preview.normalized_payload.get("source_column") != SOURCE_COLUMN
    ):
        raise SoundAssignmentConfirmationProposalError(
            "The reviewed Sound assignment preview contract changed."
        )

    proposal_by_cell = {
        item["source"]["cell"]: item
        for item in preview.normalized_payload.get("rows", [])
    }
    rows = []
    for preview_row in preview.rows:
        state = preview_row.target_state
        if state not in CONFIRMABLE_STATES:
            raise SoundAssignmentConfirmationProposalError(
                "The reviewed Sound assignment preview contains a hard blocker."
            )
        source = preview_row.source
        normalized = {
            "source": {
                "row": source.source_row,
                "cell": source.source_cell,
                "local_date": source.local_date.isoformat(),
                "date_kind": source.date_kind,
                "worship_token": source.worship_token,
                "source_state": source.source_state.value,
                "token_digest": (
                    _identity_digest(source.normalized_token)
                    if source.normalized_token is not None
                    else None
                ),
            },
            "target_state": state.value,
            "event": None,
            "membership": None,
            "assignment_baseline": [],
        }
        if state != SoundTargetState.NO_SOURCE_PROPOSAL:
            evidence = proposal_by_cell.get(source.source_cell)
            if (
                evidence is None
                or evidence.get("target_state") != state.value
                or preview_row.event is None
                or preview_row.selected_membership is None
            ):
                raise SoundAssignmentConfirmationProposalError(
                    "The reviewed Sound assignment evidence is incomplete."
                )
            normalized["event"] = deepcopy(evidence["event"])
            normalized["membership"] = _proposal_membership_payload(
                evidence["membership"]
            )
            normalized["assignment_baseline"] = deepcopy(
                evidence["assignment_baseline"]
            )
        rows.append(normalized)

    operation_id = str(uuid4())
    payload = {
        "proposal_type": CONFIRMATION_PROPOSAL_TYPE,
        "confirmation_contract_revision": CONFIRMATION_CONTRACT_REVISION,
        "confirmation_signing_version": CONFIRMATION_SIGNING_VERSION,
        "preview_contract_revision": PREVIEW_CONTRACT_REVISION,
        "source_contract_revision": SOURCE_CONTRACT_REVISION,
        "worship_parser_contract_revision": WORSHIP_PARSER_CONTRACT_REVISION,
        "integration_key": INTEGRATION_KEY,
        "source_semantic": SOURCE_SEMANTIC,
        "source_column": SOURCE_COLUMN,
        "generated_at": timezone.now().isoformat(),
        "user_id": user.pk,
        "operation_id": operation_id,
        "filename": preview.mapping_review.parsed.filename,
        "workbook_sha256": preview.mapping_review.parsed.sha256,
        "preview_digest": _digest(preview.normalized_payload),
        "profile": deepcopy(preview.normalized_payload["profile"]),
        "team": {
            "id": preview.mapping_review.team.pk,
            "key": preview.mapping_review.team.team_key,
            "active": preview.mapping_review.team.is_active,
            "assignable": preview.mapping_review.team.is_assignable,
        },
        "summary": {
            "create_count": preview.create_candidate_count,
            "exact_noop_count": preview.exact_noop_count,
            "historical_event_count": preview.historical_event_count,
            "no_source_count": preview.no_source_count,
            "hard_blocker_count": preview.hard_blocker_count,
        },
        "rows": rows,
    }
    _strict_payload_shape(payload)
    signed_payload = signing.dumps(
        payload,
        compress=True,
        salt=CONFIRMATION_SIGNING_SALT,
    )
    return SoundAssignmentConfirmationProposal(
        operation_id=operation_id,
        normalized_payload=payload,
        signed_payload=signed_payload,
        create_count=payload["summary"]["create_count"],
        exact_noop_count=payload["summary"]["exact_noop_count"],
        historical_event_count=payload["summary"]["historical_event_count"],
        no_source_count=payload["summary"]["no_source_count"],
    )


def decode_signed_sound_assignment_confirmation(
    token, *, user, max_age=CONFIRMATION_MAX_AGE_SECONDS
):
    """Decode the separate 1B proposal; this operation performs no write."""

    try:
        payload = signing.loads(
            token,
            salt=CONFIRMATION_SIGNING_SALT,
            max_age=max_age,
        )
    except signing.BadSignature as exc:
        raise SoundAssignmentConfirmationProposalError(
            "Invalid or expired Sound assignment confirmation proposal."
        ) from exc
    _strict_payload_shape(payload)
    if (
        not user_can_confirm_sound_assignments(user)
        or payload["user_id"] != getattr(user, "pk", None)
    ):
        raise SoundAssignmentConfirmationProposalError(
            "The Sound assignment proposal belongs to another user."
        )
    return payload


def _current_membership_payload(membership):
    candidate = _membership_candidate(membership)
    return {
        "id": candidate.membership_id,
        "team_id": membership.team_id,
        "active": membership.is_active,
        "updated_at": candidate.updated_at,
        "linked_user_id": candidate.linked_user_id,
        "linked_user_active": candidate.linked_user_active,
        "visible_identity_digest": candidate.identity_digest,
    }


def _revalidate_current_truth(payload, *, create_revision_claimed, skip_create=False):
    """Recompute complete signed truth after the SQLite writer boundary."""

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
    } or payload["team"] != {
        "id": team.pk,
        "key": team.team_key,
        "active": team.is_active,
        "assignable": team.is_assignable,
    }:
        raise SoundAssignmentConfirmationError(
            "The Sound assignment profile or destination team changed after review."
        )

    material_rows = [
        row
        for row in payload["rows"]
        if row["target_state"] != SoundTargetState.NO_SOURCE_PROPOSAL.value
        and not (
            skip_create
            and row["target_state"] == SoundTargetState.CREATE_CANDIDATE.value
        )
    ]
    event_ids = [row["event"]["id"] for row in material_rows]
    membership_ids = [row["membership"]["id"] for row in material_rows]
    events = {
        event.pk: event
        for event in ServiceEvent.objects.filter(pk__in=event_ids)
        .select_related("service_profile")
        .prefetch_related("audience_scope_links__unit")
    }
    memberships = {
        item.pk: item
        for item in TeamMembership.objects.filter(pk__in=membership_ids).select_related(
            "user"
        )
    }
    assignments_by_event = {}
    for assignment in _assignment_queryset(event_ids, team):
        assignments_by_event.setdefault(assignment.service_event_id, []).append(
            assignment
        )

    classification_now = timezone.now()
    for row in material_rows:
        event = events.get(row["event"]["id"])
        membership = memberships.get(row["membership"]["id"])
        if event is None or membership is None:
            raise SoundAssignmentConfirmationError(
                "A reviewed Sound event or membership no longer exists."
            )
        expected_event = deepcopy(row["event"])
        if (
            create_revision_claimed
            and row["target_state"] == SoundTargetState.CREATE_CANDIDATE.value
        ):
            expected_event["scheduling_revision"] += 1
        identity = inspect_service_profile_identity(event)
        local_start = timezone.localtime(event.start_datetime)
        if (
            _event_payload(event) != expected_event
            or not identity.is_exact
            or event.service_profile_id != profile.pk
            or event.service_profile.key != SUPPORTED_PROFILE_KEY
            or event.event_type != SUPPORTED_EVENT_TYPE
            or local_start.time().replace(tzinfo=None) != SUPPORTED_LOCAL_TIME
            or event.status
            not in {ServiceEvent.STATUS_PUBLISHED, ServiceEvent.STATUS_COMPLETED}
            or not service_event_audience_readiness(event)["ready"]
            or not membership.is_active
            or membership.team_id != team.pk
            or _current_membership_payload(membership) != row["membership"]
        ):
            raise SoundAssignmentConfirmationError(
                "A reviewed Sound event, membership, or audience changed."
            )

        assignments = assignments_by_event.get(event.pk, [])
        if _assignment_baseline(assignments) != row["assignment_baseline"]:
            raise SoundAssignmentConfirmationError(
                "A reviewed Sound assignment baseline changed."
            )
        current_state, _current_ids, _roster, _historical_ids = _classify_assignment(
            assignments, membership.pk
        )
        if _event_is_historical_for_assignment_import(event, now=classification_now):
            current_state = SoundTargetState.HISTORICAL_EVENT_BLOCKER
        elif _membership_is_outside_event_audience(
            _membership_candidate(membership), event
        ):
            current_state = SoundTargetState.AUDIENCE_SAFETY_BLOCKER
        if current_state.value != row["target_state"]:
            raise SoundAssignmentConfirmationError(
                "A reviewed Sound row is no longer in its approved state."
            )
    return profile, team, events, memberships


def _audit_message(*, payload, assignment, membership):
    return _canonical_json(
        {
            "action": "create",
            "confirmation_contract_revision": payload[
                "confirmation_contract_revision"
            ],
            "created_team_assignment_id": assignment.pk,
            "event_id": assignment.service_event_id,
            "operation_id": payload["operation_id"],
            "selected_team_membership_id": membership.pk,
            "sound_team": {
                "id": assignment.ministry_team_id,
                "team_key": SVCA_SOUND_TEAM_KEY,
            },
            "workbook_sha256": payload["workbook_sha256"],
        }
    )


def _assert_postconditions(
    *, payload, actor, team, created_assignments, created_members, audit_messages
):
    content_type_id = ContentType.objects.get_for_model(TeamAssignment).pk
    for row, assignment, member in zip(
        sorted(
            [
            item
            for item in payload["rows"]
            if item["target_state"] == SoundTargetState.CREATE_CANDIDATE.value
            ],
            key=lambda item: item["event"]["id"],
        ),
        created_assignments,
        created_members,
        strict=True,
    ):
        event = ServiceEvent.objects.get(pk=row["event"]["id"])
        assignments = list(_assignment_queryset((event.pk,), team))
        members = list(
            TeamAssignmentMember.objects.filter(assignment_id=assignment.pk).order_by(
                "id"
            )
        )
        logs = list(
            LogEntry.objects.filter(
                user_id=actor.pk,
                content_type_id=content_type_id,
                object_id=str(assignment.pk),
                action_flag=ADDITION,
                change_message=audit_messages[assignment.pk],
            )
        )
        persisted_assignment = assignments[0] if len(assignments) == 1 else None
        persisted_member = members[0] if len(members) == 1 else None
        if (
            event.scheduling_revision != row["event"]["scheduling_revision"] + 1
            or persisted_assignment is None
            or persisted_assignment.pk != assignment.pk
            or persisted_assignment.service_event_id != event.pk
            or persisted_assignment.ministry_team_id != team.pk
            or persisted_assignment.status != TeamAssignment.STATUS_SCHEDULED
            or persisted_assignment.notes != ""
            or persisted_assignment.created_by_id != actor.pk
            or persisted_assignment.reviewed_worship_context_fingerprint is not None
            or persisted_member is None
            or persisted_member.pk != member.pk
            or persisted_member.membership_id != row["membership"]["id"]
            or persisted_member.confirmed_at is not None
            or persisted_member.confirmation_note != ""
            or len(logs) != 1
        ):
            raise SoundAssignmentConfirmationError(
                "A created Sound assignment failed its exact postconditions."
            )


def confirm_sound_assignments(*, user, payload):
    """Claim create-event revisions, revalidate, create, audit, and prove."""

    _strict_payload_shape(payload)
    if payload["user_id"] != getattr(user, "pk", None):
        raise SoundAssignmentConfirmationProposalError(
            "The Sound assignment proposal belongs to another user."
        )
    create_rows = [
        row
        for row in payload["rows"]
        if row["target_state"] == SoundTargetState.CREATE_CANDIDATE.value
    ]
    expected_revisions = {
        row["event"]["id"]: row["event"]["scheduling_revision"]
        for row in create_rows
    }

    try:
        with transaction.atomic():
            actor = get_user_model()._default_manager.filter(pk=user.pk).first()
            if actor is None or not user_can_confirm_sound_assignments(actor):
                raise SoundAssignmentConfirmationError(
                    "Sound assignment confirmation authority changed after review."
                )
            try:
                require_integration_enabled(INTEGRATION_KEY)
            except IntegrationDisabled as exc:
                raise SoundAssignmentConfirmationError(
                    "The annual workbook integration is no longer enabled."
                ) from exc

            claim_results = claim_scheduling_revisions(expected_revisions)
            actor = get_user_model()._default_manager.filter(pk=user.pk).first()
            if actor is None or not user_can_confirm_sound_assignments(actor):
                raise SoundAssignmentConfirmationError(
                    "Sound assignment confirmation authority changed after "
                    "the event revision claim."
                )
            try:
                require_integration_enabled(INTEGRATION_KEY)
            except IntegrationDisabled as exc:
                raise SoundAssignmentConfirmationError(
                    "The annual workbook integration became unavailable after "
                    "the event revision claim."
                ) from exc

            _profile, team, events, memberships = _revalidate_current_truth(
                payload, create_revision_claimed=True
            )

            created_assignments = []
            created_members = []
            audit_messages = {}
            content_type_id = ContentType.objects.get_for_model(TeamAssignment).pk
            for row in sorted(create_rows, key=lambda item: item["event"]["id"]):
                event = events[row["event"]["id"]]
                membership = memberships[row["membership"]["id"]]
                assignment = TeamAssignment(
                    service_event=event,
                    ministry_team=team,
                    status=TeamAssignment.STATUS_SCHEDULED,
                    notes="",
                    created_by=actor,
                    reviewed_worship_context_fingerprint=None,
                )
                assignment.save(
                    force_insert=True,
                    _skip_scheduling_revision=True,
                )
                member = TeamAssignmentMember(
                    assignment=assignment,
                    membership=membership,
                    confirmed_at=None,
                    confirmation_note="",
                )
                member.save(force_insert=True)
                message = _audit_message(
                    payload=payload,
                    assignment=assignment,
                    membership=membership,
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
                created_assignments.append(assignment)
                created_members.append(member)
                audit_messages[assignment.pk] = message

            _revalidate_current_truth(
                payload,
                create_revision_claimed=True,
                skip_create=True,
            )
            actor = get_user_model()._default_manager.get(pk=user.pk)
            if not user_can_confirm_sound_assignments(actor):
                raise SoundAssignmentConfirmationError(
                    "Sound assignment confirmation authority changed during apply."
                )
            _assert_postconditions(
                payload=payload,
                actor=actor,
                team=team,
                created_assignments=created_assignments,
                created_members=created_members,
                audit_messages=audit_messages,
            )
    except SchedulingRevisionBusyError as exc:
        raise SoundAssignmentConfirmationBusy(
            "Scheduling is busy; no Sound assignment was created."
        ) from exc
    except SchedulingRevisionError as exc:
        raise SoundAssignmentConfirmationError(
            "A reviewed event revision is stale or missing; the batch was rolled back."
        ) from exc
    except OperationalError as exc:
        message = str(exc).lower()
        if "database is locked" in message or "database table is locked" in message:
            raise SoundAssignmentConfirmationBusy(
                "Scheduling is busy; no Sound assignment was created."
            ) from exc
        raise
    except (IntegrityError, ValidationError, SoundMappingStateError) as exc:
        raise SoundAssignmentConfirmationError(
            "Current Sound assignment validation changed; the batch was rolled back."
        ) from exc

    return SoundAssignmentConfirmationResult(
        operation_id=payload["operation_id"],
        workbook_sha256=payload["workbook_sha256"],
        created_assignment_ids=tuple(item.pk for item in created_assignments),
        created_member_ids=tuple(item.pk for item in created_members),
        claimed_event_ids=tuple(item.event_id for item in claim_results),
        log_entry_count=len(created_assignments),
    )
