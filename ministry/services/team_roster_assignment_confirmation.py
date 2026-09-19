"""Generic TEAM_ROSTER_CONFIRMATION_V1 authority and atomic writer core.

This service is deliberately team- and workbook-column-neutral.  It consumes
the reviewed generic person and assignment-preview authorities, establishes
SQLite writer serialization with revision CAS / conditional parent updates,
and applies one whole-workbook transaction.  No route or UI is defined here.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
import json
import re
from uuid import UUID, uuid4

from django.contrib.admin.models import ADDITION, CHANGE, LogEntry
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core import signing
from django.core.exceptions import ValidationError
from django.db import IntegrityError, OperationalError, transaction
from django.db.models import F, Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from core.integration_registry import IntegrationDisabled, require_integration_enabled
from events.models import ServiceEvent
from events.scheduling_revision import (
    SchedulingRevisionBusyError,
    SchedulingRevisionError,
    claim_scheduling_revisions,
)

from ..models import MinistryTeam, TeamAssignment, TeamAssignmentMember, TeamMembership
from .team_roster_assignment_preview import (
    TEAM_ROSTER_ASSIGNMENT_PREVIEW_V1,
    TeamRosterAssignmentPreviewError,
    TeamRosterAssignmentPreviewState,
    _assignment_payload,
    _assignment_queryset,
    _build_preview,
    _member_payload,
    decode_team_roster_assignment_preview,
)
from .team_roster_column_mapping import user_can_review_team_roster_columns
from .team_roster_person_mapping import (
    TEAM_ROSTER_PERSON_MAPPING_REVIEW_V1,
    TeamRosterPersonMappingStateError,
    decode_reviewed_team_roster_person_mapping,
)
from .team_roster_workbook import TEAM_ROSTER_CELL_V1
from .worship_xlsx_preview import (
    CONTRACT_REVISION,
    INTEGRATION_KEY,
    SIGNING_MAX_AGE_SECONDS,
)


TEAM_ROSTER_CONFIRMATION_V1 = "TEAM_ROSTER_CONFIRMATION_V1"
TEAM_ROSTER_CONFIRMATION_STATE_TYPE = "team_roster_confirmation"
TEAM_ROSTER_CONFIRMATION_SIGNING_SALT = "ministry.team_roster.confirmation.v1"
TEAM_ROSTER_WRITABLE_ROW_V1 = "TEAM_ROSTER_WRITABLE_ROW_V1"
MAX_TEAM_ROSTER_CONFIRMATION_STATE_BYTES = 16_384
TEAM_ROSTER_CONFIRMATION_MAX_AGE_SECONDS = SIGNING_MAX_AGE_SECONDS

_SHA256_RE = re.compile(r"^[0-9A-F]{64}$")
_WRITABLE_STATES = frozenset(
    {
        TeamRosterAssignmentPreviewState.CREATE_CANDIDATE,
        TeamRosterAssignmentPreviewState.ROSTER_UPDATE_CANDIDATE,
    }
)
_CONFIRMATION_KEYS = {
    "contract_version",
    "state_type",
    "person_contract_version",
    "preview_contract_version",
    "writable_row_contract_version",
    "integration_key",
    "adapter_contract_revision",
    "cell_contract_revision",
    "generated_at",
    "user_id",
    "workbook_sha256",
    "person_state_sha256",
    "preview_state_sha256",
    "operation_id",
    "teams",
    "rows",
    "summary",
}
_ROW_KEYS = {
    "source_cell",
    "event_id",
    "team_id",
    "classification",
    "assignment_id",
    "expected_create_event_revision",
    "reviewed_membership_ids",
    "preserved_membership_ids",
    "add_membership_ids",
    "remove_membership_ids",
    "preserved_assignment_member_ids",
    "removable_assignment_member_ids",
}
_SUMMARY_KEYS = {
    "create_count",
    "update_count",
    "changed_assignment_count",
    "preserved_member_count",
    "add_member_count",
    "remove_member_count",
}


class TeamRosterConfirmationError(RuntimeError):
    """Base class for bounded generic confirmation failures."""


class TeamRosterConfirmationProposalError(TeamRosterConfirmationError):
    """Confirmation authority is invalid, ineligible, expired, or malformed."""


class TeamRosterConfirmationStateTooLarge(TeamRosterConfirmationProposalError):
    def __init__(self, actual_bytes):
        self.actual_bytes = actual_bytes
        self.maximum_bytes = MAX_TEAM_ROSTER_CONFIRMATION_STATE_BYTES
        super().__init__(
            f"Signed confirmation authority is {actual_bytes} bytes; the "
            f"{self.maximum_bytes}-byte bound was not raised."
        )


class TeamRosterConfirmationStaleError(TeamRosterConfirmationError):
    """Reviewed scheduling truth changed; the caller must review again."""


class TeamRosterConfirmationBusyError(TeamRosterConfirmationError):
    """SQLite could not establish the bounded writer transaction."""


class TeamRosterConfirmationAuditError(TeamRosterConfirmationError):
    """The privacy-bounded audit failed and the whole batch was rolled back."""


@dataclass(frozen=True, slots=True)
class TeamRosterConfirmationProposal:
    operation_id: str
    normalized_payload: dict
    signed_confirmation_state: str
    signed_state_bytes: int
    create_count: int
    update_count: int
    add_member_count: int
    remove_member_count: int


@dataclass(frozen=True, slots=True)
class TeamRosterConfirmationAuthority:
    payload: dict
    preview: object


@dataclass(frozen=True, slots=True)
class TeamRosterConfirmationResult:
    operation_id: str
    workbook_sha256: str
    created_assignment_ids: tuple[int, ...]
    updated_assignment_ids: tuple[int, ...]
    created_assignment_member_ids: tuple[int, ...]
    added_assignment_member_ids: tuple[int, ...]
    removed_assignment_member_ids: tuple[int, ...]
    claimed_event_ids: tuple[int, ...]
    log_entry_count: int


def _digest_token(value):
    return sha256(value.encode("utf-8")).hexdigest().upper()


def _canonical_json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _positive_int_list(value):
    return bool(
        isinstance(value, list)
        and all(type(item) is int and item > 0 for item in value)
        and value == sorted(set(value))
    )


def _summary_for_rows(rows):
    return {
        "create_count": sum(
            item["classification"]
            == TeamRosterAssignmentPreviewState.CREATE_CANDIDATE.value
            for item in rows
        ),
        "update_count": sum(
            item["classification"]
            == TeamRosterAssignmentPreviewState.ROSTER_UPDATE_CANDIDATE.value
            for item in rows
        ),
        "changed_assignment_count": len(rows),
        "preserved_member_count": sum(
            len(item["preserved_membership_ids"]) for item in rows
        ),
        "add_member_count": sum(len(item["add_membership_ids"]) for item in rows),
        "remove_member_count": sum(
            len(item["remove_membership_ids"]) for item in rows
        ),
    }


def _strict_payload_shape(payload):
    if (
        not isinstance(payload, dict)
        or set(payload) != _CONFIRMATION_KEYS
        or payload.get("contract_version") != TEAM_ROSTER_CONFIRMATION_V1
        or payload.get("state_type") != TEAM_ROSTER_CONFIRMATION_STATE_TYPE
        or payload.get("person_contract_version")
        != TEAM_ROSTER_PERSON_MAPPING_REVIEW_V1
        or payload.get("preview_contract_version")
        != TEAM_ROSTER_ASSIGNMENT_PREVIEW_V1
        or payload.get("writable_row_contract_version")
        != TEAM_ROSTER_WRITABLE_ROW_V1
        or payload.get("integration_key") != INTEGRATION_KEY
        or payload.get("adapter_contract_revision") != CONTRACT_REVISION
        or payload.get("cell_contract_revision") != TEAM_ROSTER_CELL_V1
        or not isinstance(payload.get("generated_at"), str)
        or type(payload.get("user_id")) is not int
        or payload["user_id"] <= 0
        or not isinstance(payload.get("workbook_sha256"), str)
        or _SHA256_RE.fullmatch(payload["workbook_sha256"]) is None
        or not isinstance(payload.get("person_state_sha256"), str)
        or _SHA256_RE.fullmatch(payload["person_state_sha256"]) is None
        or not isinstance(payload.get("preview_state_sha256"), str)
        or _SHA256_RE.fullmatch(payload["preview_state_sha256"]) is None
        or not isinstance(payload.get("operation_id"), str)
        or not isinstance(payload.get("teams"), list)
        or not isinstance(payload.get("rows"), list)
        or not isinstance(payload.get("summary"), dict)
        or set(payload["summary"]) != _SUMMARY_KEYS
    ):
        raise TeamRosterConfirmationProposalError(
            "Confirmation authority is malformed or belongs to another workflow."
        )
    try:
        datetime.fromisoformat(payload["generated_at"])
        operation_id = UUID(payload["operation_id"])
    except (TypeError, ValueError) as exc:
        raise TeamRosterConfirmationProposalError(
            "Confirmation timestamp or operation identity is malformed."
        ) from exc
    if str(operation_id) != payload["operation_id"]:
        raise TeamRosterConfirmationProposalError(
            "Confirmation operation identity is not canonical."
        )

    teams = payload["teams"]
    if any(
        not isinstance(item, list)
        or len(item) != 2
        or type(item[0]) is not int
        or item[0] <= 0
        or not isinstance(item[1], str)
        or not item[1]
        for item in teams
    ) or teams != sorted(teams, key=lambda item: item[0]):
        raise TeamRosterConfirmationProposalError("Confirmation teams are malformed.")
    if len({item[0] for item in teams}) != len(teams):
        raise TeamRosterConfirmationProposalError("Confirmation teams are malformed.")

    rows = payload["rows"]
    if not rows:
        raise TeamRosterConfirmationProposalError(
            "Confirmation authority contains no writable rows."
        )
    seen_pairs = set()
    for item in rows:
        if (
            not isinstance(item, dict)
            or set(item) != _ROW_KEYS
            or not isinstance(item["source_cell"], str)
            or not item["source_cell"]
            or type(item["event_id"]) is not int
            or item["event_id"] <= 0
            or type(item["team_id"]) is not int
            or item["team_id"] <= 0
            or item["classification"]
            not in {state.value for state in _WRITABLE_STATES}
            or type(item["assignment_id"]) is not int
            or not all(
                _positive_int_list(item[key])
                for key in (
                    "reviewed_membership_ids",
                    "preserved_membership_ids",
                    "add_membership_ids",
                    "remove_membership_ids",
                    "preserved_assignment_member_ids",
                    "removable_assignment_member_ids",
                )
            )
        ):
            raise TeamRosterConfirmationProposalError(
                "Confirmation writable rows are malformed."
            )
        classification = item["classification"]
        is_create = (
            classification == TeamRosterAssignmentPreviewState.CREATE_CANDIDATE.value
        )
        revision = item["expected_create_event_revision"]
        if is_create:
            valid_action_shape = (
                item["assignment_id"] == 0
                and type(revision) is int
                and revision >= 0
                and not item["preserved_membership_ids"]
                and not item["remove_membership_ids"]
                and not item["preserved_assignment_member_ids"]
                and not item["removable_assignment_member_ids"]
                and item["reviewed_membership_ids"] == item["add_membership_ids"]
            )
        else:
            valid_action_shape = (
                item["assignment_id"] > 0
                and revision is None
                and len(item["preserved_membership_ids"])
                == len(item["preserved_assignment_member_ids"])
                and len(item["remove_membership_ids"])
                == len(item["removable_assignment_member_ids"])
                and item["reviewed_membership_ids"]
                == sorted(
                    item["preserved_membership_ids"] + item["add_membership_ids"]
                )
                and not set(item["preserved_membership_ids"])
                & set(item["add_membership_ids"])
                and not set(item["reviewed_membership_ids"])
                & set(item["remove_membership_ids"])
            )
        pair = (item["event_id"], item["team_id"])
        if not valid_action_shape or pair in seen_pairs:
            raise TeamRosterConfirmationProposalError(
                "Confirmation writable rows are malformed."
            )
        seen_pairs.add(pair)
    if rows != sorted(
        rows, key=lambda item: (item["event_id"], item["team_id"], item["source_cell"])
    ):
        raise TeamRosterConfirmationProposalError(
            "Confirmation writable rows are not deterministic."
        )
    if {item[0] for item in teams} != {item["team_id"] for item in rows}:
        raise TeamRosterConfirmationProposalError("Confirmation teams are malformed.")
    if payload["summary"] != _summary_for_rows(rows):
        raise TeamRosterConfirmationProposalError(
            "Confirmation operation counts are malformed."
        )


def _assignment_by_id(preview_payload):
    return {item["id"]: item for item in preview_payload["assignments"]}


def _derive_writable_projection(preview):
    event_revisions = {
        item["id"]: item["scheduling_revision"]
        for item in preview.normalized_payload["events"]
    }
    assignments = _assignment_by_id(preview.normalized_payload)
    rows = []
    team_keys = {}
    for row in preview.rows:
        if row.state not in _WRITABLE_STATES:
            continue
        if row.diff is None:
            raise TeamRosterConfirmationProposalError(
                "A writable preview row has no exact roster diff."
            )
        is_create = row.state == TeamRosterAssignmentPreviewState.CREATE_CANDIDATE
        assignment_id = row.current_assignment_id or 0
        preserved_member_row_ids = []
        removable_member_row_ids = []
        if not is_create:
            assignment = assignments.get(assignment_id)
            if assignment is None:
                raise TeamRosterConfirmationProposalError(
                    "A writable preview assignment baseline is incomplete."
                )
            member_by_membership = {
                item["membership_id"]: item for item in assignment["members"]
            }
            try:
                preserved_member_row_ids = sorted(
                    member_by_membership[item]["id"]
                    for item in row.diff.preserved_ids
                )
                removable_member_row_ids = sorted(
                    member_by_membership[item]["id"] for item in row.diff.remove_ids
                )
            except KeyError as exc:
                raise TeamRosterConfirmationProposalError(
                    "A writable preview member baseline is incomplete."
                ) from exc
            if preserved_member_row_ids != sorted(
                row.preserved_assignment_member_ids
            ):
                raise TeamRosterConfirmationProposalError(
                    "A writable preview preserved-row baseline is inconsistent."
                )
        rows.append(
            {
                "source_cell": row.source_cell,
                "event_id": row.event_id,
                "team_id": row.team_id,
                "classification": row.state.value,
                "assignment_id": assignment_id,
                "expected_create_event_revision": (
                    event_revisions[row.event_id] if is_create else None
                ),
                "reviewed_membership_ids": list(row.reviewed_membership_ids),
                "preserved_membership_ids": list(row.diff.preserved_ids),
                "add_membership_ids": list(row.diff.add_ids),
                "remove_membership_ids": list(row.diff.remove_ids),
                "preserved_assignment_member_ids": preserved_member_row_ids,
                "removable_assignment_member_ids": removable_member_row_ids,
            }
        )
        team_keys[row.team_id] = row.team_key
    rows.sort(key=lambda item: (item["event_id"], item["team_id"], item["source_cell"]))
    teams = [[team_id, team_keys[team_id]] for team_id in sorted(team_keys)]
    return teams, rows, _summary_for_rows(rows)


def _load_confirmation_payload(token, *, max_age):
    if (
        not isinstance(token, str)
        or len(token.encode("utf-8")) > MAX_TEAM_ROSTER_CONFIRMATION_STATE_BYTES
    ):
        raise TeamRosterConfirmationProposalError(
            "Confirmation authority is invalid or exceeds its fixed bound."
        )
    try:
        payload = signing.loads(
            token,
            salt=TEAM_ROSTER_CONFIRMATION_SIGNING_SALT,
            max_age=max_age,
        )
    except signing.BadSignature as exc:
        raise TeamRosterConfirmationProposalError(
            "Confirmation authority is invalid or expired."
        ) from exc
    _strict_payload_shape(payload)
    return payload


def build_team_roster_confirmation_proposal(
    *,
    reviewed_person_state,
    assignment_preview_state,
    user,
    language="en",
    now=None,
    operation_id=None,
):
    """Mint distinct write authority only for a safe, changing preview."""

    try:
        preview = decode_team_roster_assignment_preview(
            assignment_preview_state,
            reviewed_person_state=reviewed_person_state,
            user=user,
            language=language,
            now=now,
        )
    except TeamRosterAssignmentPreviewError as exc:
        raise TeamRosterConfirmationProposalError(
            "Assignment-preview authority is invalid, expired, or stale."
        ) from exc
    if preview.has_hard_blockers or not preview.has_changes:
        return None
    teams, rows, summary = _derive_writable_projection(preview)
    payload = {
        "contract_version": TEAM_ROSTER_CONFIRMATION_V1,
        "state_type": TEAM_ROSTER_CONFIRMATION_STATE_TYPE,
        "person_contract_version": TEAM_ROSTER_PERSON_MAPPING_REVIEW_V1,
        "preview_contract_version": TEAM_ROSTER_ASSIGNMENT_PREVIEW_V1,
        "writable_row_contract_version": TEAM_ROSTER_WRITABLE_ROW_V1,
        "integration_key": INTEGRATION_KEY,
        "adapter_contract_revision": CONTRACT_REVISION,
        "cell_contract_revision": TEAM_ROSTER_CELL_V1,
        "generated_at": timezone.now().isoformat(),
        "user_id": user.pk,
        "workbook_sha256": preview.workbook_sha256,
        "person_state_sha256": _digest_token(reviewed_person_state),
        "preview_state_sha256": _digest_token(assignment_preview_state),
        "operation_id": str(operation_id or uuid4()),
        "teams": teams,
        "rows": rows,
        "summary": summary,
    }
    _strict_payload_shape(payload)
    token = signing.dumps(
        payload, salt=TEAM_ROSTER_CONFIRMATION_SIGNING_SALT, compress=True
    )
    size = len(token.encode("utf-8"))
    if size > MAX_TEAM_ROSTER_CONFIRMATION_STATE_BYTES:
        raise TeamRosterConfirmationStateTooLarge(size)
    return TeamRosterConfirmationProposal(
        operation_id=payload["operation_id"],
        normalized_payload=payload,
        signed_confirmation_state=token,
        signed_state_bytes=size,
        create_count=summary["create_count"],
        update_count=summary["update_count"],
        add_member_count=summary["add_member_count"],
        remove_member_count=summary["remove_member_count"],
    )


def decode_team_roster_confirmation(
    token,
    *,
    reviewed_person_state,
    assignment_preview_state,
    user,
    language="en",
    max_age=TEAM_ROSTER_CONFIRMATION_MAX_AGE_SECONDS,
    now=None,
):
    """Strictly re-decode all three authorities and require exact agreement."""

    payload = _load_confirmation_payload(token, max_age=max_age)
    try:
        decode_reviewed_team_roster_person_mapping(
            reviewed_person_state,
            user=user,
            language=language,
            max_age=max_age,
        )
        preview = decode_team_roster_assignment_preview(
            assignment_preview_state,
            reviewed_person_state=reviewed_person_state,
            user=user,
            language=language,
            max_age=max_age,
            now=now,
        )
    except (TeamRosterPersonMappingStateError, TeamRosterAssignmentPreviewError) as exc:
        raise TeamRosterConfirmationProposalError(
            "Reviewed person or assignment-preview authority is invalid, expired, or stale."
        ) from exc
    teams, rows, summary = _derive_writable_projection(preview)
    if (
        payload["user_id"] != getattr(user, "pk", None)
        or payload["person_state_sha256"] != _digest_token(reviewed_person_state)
        or payload["preview_state_sha256"] != _digest_token(assignment_preview_state)
        or payload["workbook_sha256"] != preview.workbook_sha256
        or payload["teams"] != teams
        or payload["rows"] != rows
        or payload["summary"] != summary
        or preview.has_hard_blockers
        or not preview.has_changes
    ):
        raise TeamRosterConfirmationProposalError(
            "Confirmation authority does not match the complete reviewed preview."
        )
    return TeamRosterConfirmationAuthority(payload=payload, preview=preview)


def _require_current_actor(user):
    actor = (
        get_user_model()._default_manager.filter(pk=getattr(user, "pk", None)).first()
    )
    if actor is None or not user_can_review_team_roster_columns(actor):
        raise TeamRosterConfirmationStaleError(
            "Active staff or superuser confirmation authority changed."
        )
    try:
        require_integration_enabled(INTEGRATION_KEY)
    except IntegrationDisabled as exc:
        raise TeamRosterConfirmationStaleError(
            "The annual workbook integration is no longer enabled."
        ) from exc
    return actor


def _conditional_assignment_barriers(rows, assignment_baselines):
    update_rows = [
        item
        for item in rows
        if item["classification"]
        == TeamRosterAssignmentPreviewState.ROSTER_UPDATE_CANDIDATE.value
    ]
    for row in sorted(update_rows, key=lambda item: item["assignment_id"]):
        baseline = assignment_baselines.get(row["assignment_id"])
        if baseline is None:
            raise TeamRosterConfirmationStaleError(
                "A reviewed assignment baseline is missing."
            )
        raw_notes = (
            TeamAssignment.objects.filter(pk=baseline["id"])
            .values_list("notes", flat=True)
            .first()
        )
        if raw_notes is None or _digest_token(raw_notes) != baseline["notes_digest"]:
            raise TeamRosterConfirmationStaleError(
                "A reviewed assignment note changed before the writer barrier."
            )
        query = TeamAssignment.objects.filter(
            pk=baseline["id"],
            service_event_id=baseline["event_id"],
            ministry_team_id=baseline["team_id"],
            status=baseline["status"],
            created_by_id=baseline["created_by_id"],
            created_at=parse_datetime(baseline["created_at"]),
            updated_at=parse_datetime(baseline["updated_at"]),
            notes=raw_notes,
        )
        fingerprint = baseline["reviewed_worship_context_fingerprint"]
        if fingerprint is None:
            query = query.filter(reviewed_worship_context_fingerprint__isnull=True)
        else:
            query = query.filter(reviewed_worship_context_fingerprint=fingerprint)
        matched = query.update(notes=F("notes"))
        if matched != 1:
            raise TeamRosterConfirmationStaleError(
                "A reviewed assignment changed before the writer barrier."
            )


def _writer_aware_recompute(
    *,
    reviewed_person_state,
    assignment_preview_state,
    actor,
    preview,
    create_event_ids,
    language,
    max_age,
    now,
):
    expected = deepcopy(preview.normalized_payload)
    for item in expected["events"]:
        if item["id"] in create_event_ids:
            item["scheduling_revision"] += 1
    try:
        current = _build_preview(
            reviewed_person_state=reviewed_person_state,
            user=actor,
            language=language,
            max_age=max_age,
            now=now,
            generated_at=preview.normalized_payload["generated_at"],
            signed_token=assignment_preview_state,
            allowed_event_revision_advances=create_event_ids,
        )
    except TeamRosterAssignmentPreviewError as exc:
        raise TeamRosterConfirmationStaleError(
            "Complete scheduling truth changed after writer serialization."
        ) from exc
    if current.normalized_payload != expected:
        raise TeamRosterConfirmationStaleError(
            "Complete scheduling truth changed after writer serialization."
        )
    return current


def _membership_baselines(preview_payload):
    return {item["id"]: item for item in preview_payload["memberships"]}


def _delete_exact_member(*, row, membership_id, member_id, membership_baseline):
    query = TeamAssignmentMember.objects.filter(
        pk=member_id,
        assignment_id=row["assignment_id"],
        membership_id=membership_id,
        confirmed_at__isnull=True,
        confirmation_note="",
        membership__team_id=row["team_id"],
        membership__is_active=True,
        membership__updated_at=parse_datetime(membership_baseline["updated_at"]),
        membership__user_id=membership_baseline["linked_user_id"],
    ).filter(Q(membership__user__isnull=True) | Q(membership__user__is_active=True))
    deleted, details = query.delete()
    label = TeamAssignmentMember._meta.label
    if deleted != 1 or details.get(label) != 1:
        raise TeamRosterConfirmationStaleError(
            "An exact reviewed assignment-member removal became stale."
        )


def _assert_event_revisions(preview_payload, create_event_ids):
    signed = {
        item["id"]: item["scheduling_revision"] for item in preview_payload["events"]
    }
    current = dict(
        ServiceEvent.objects.filter(pk__in=signed).values_list(
            "id", "scheduling_revision"
        )
    )
    expected = {
        event_id: revision + (1 if event_id in create_event_ids else 0)
        for event_id, revision in signed.items()
    }
    if current != expected:
        raise TeamRosterConfirmationStaleError(
            "Event revisions failed exact confirmation postconditions."
        )


def _assert_domain_postconditions(
    *,
    payload,
    preview,
    actor,
    created_by_pair,
    created_member_ids_by_pair,
    added_member_ids_by_assignment,
    create_event_ids,
):
    assignment_baselines = _assignment_by_id(preview.normalized_payload)
    rows_by_pair = {(item.event_id, item.team_id): item for item in preview.rows}
    writable_pairs = {(item["event_id"], item["team_id"]) for item in payload["rows"]}

    for row in payload["rows"]:
        pair = (row["event_id"], row["team_id"])
        assignments = list(_assignment_queryset((pair[0],), (pair[1],)))
        if row["classification"] == TeamRosterAssignmentPreviewState.CREATE_CANDIDATE.value:
            created = created_by_pair[pair]
            persisted = assignments[0] if len(assignments) == 1 else None
            members = (
                list(persisted.assignment_members.order_by("id"))
                if persisted is not None
                else []
            )
            if (
                persisted is None
                or persisted.pk != created.pk
                or persisted.service_event_id != row["event_id"]
                or persisted.ministry_team_id != row["team_id"]
                or persisted.status != TeamAssignment.STATUS_SCHEDULED
                or persisted.created_by_id != actor.pk
                or persisted.notes != ""
                or persisted.reviewed_worship_context_fingerprint is not None
                or [
                    item.membership_id
                    for item in sorted(
                        members, key=lambda value: value.membership_id
                    )
                ]
                != row["reviewed_membership_ids"]
                or {item.pk for item in members} != created_member_ids_by_pair[pair]
                or any(
                    item.confirmed_at is not None or item.confirmation_note != ""
                    for item in members
                )
            ):
                raise TeamRosterConfirmationStaleError(
                    "A created assignment failed exact postconditions."
                )
            continue

        baseline = assignment_baselines[row["assignment_id"]]
        if len(assignments) != 1 or assignments[0].pk != row["assignment_id"]:
            raise TeamRosterConfirmationStaleError(
                "An updated assignment failed exact parent postconditions."
            )
        current = assignments[0]
        current_payload = _assignment_payload(current)
        if {key: value for key, value in current_payload.items() if key != "members"} != {
            key: value for key, value in baseline.items() if key != "members"
        }:
            raise TeamRosterConfirmationStaleError(
                "An updated assignment parent changed during apply."
            )
        current_members = {item.membership_id: item for item in current.assignment_members.all()}
        if sorted(current_members) != row["reviewed_membership_ids"]:
            raise TeamRosterConfirmationStaleError(
                "An updated assignment roster failed exact postconditions."
            )
        baseline_members = {item["membership_id"]: item for item in baseline["members"]}
        for membership_id in row["preserved_membership_ids"]:
            if _member_payload(current_members[membership_id]) != baseline_members[membership_id]:
                raise TeamRosterConfirmationStaleError(
                    "A preserved assignment member changed during apply."
                )
        for member_id in row["removable_assignment_member_ids"]:
            if TeamAssignmentMember.objects.filter(pk=member_id).exists():
                raise TeamRosterConfirmationStaleError(
                    "A reviewed assignment-member removal failed."
                )
        added_ids = added_member_ids_by_assignment.get(row["assignment_id"], set())
        for membership_id in row["add_membership_ids"]:
            member = current_members[membership_id]
            if (
                member.pk not in added_ids
                or member.confirmed_at is not None
                or member.confirmation_note != ""
            ):
                raise TeamRosterConfirmationStaleError(
                    "An added assignment member failed exact postconditions."
                )

    for pair, preview_row in rows_by_pair.items():
        if pair in writable_pairs:
            continue
        current = [
            _assignment_payload(item)
            for item in _assignment_queryset((pair[0],), (pair[1],))
        ]
        baseline = [
            item
            for item in preview.normalized_payload["assignments"]
            if item["event_id"] == pair[0] and item["team_id"] == pair[1]
        ]
        if current != baseline:
            raise TeamRosterConfirmationStaleError(
                f"Non-write row {preview_row.source_cell} changed during apply."
            )
    _assert_event_revisions(preview.normalized_payload, create_event_ids)


def _audit_message(*, payload, row, assignment_id):
    action = (
        "create"
        if row["classification"]
        == TeamRosterAssignmentPreviewState.CREATE_CANDIDATE.value
        else "update"
    )
    team_keys = dict(payload["teams"])
    return _canonical_json(
        {
            "action": action,
            "added_membership_ids": row["add_membership_ids"],
            "assignment_id": assignment_id,
            "classification": row["classification"],
            "confirmation_contract_version": TEAM_ROSTER_CONFIRMATION_V1,
            "event_id": row["event_id"],
            "operation_id": payload["operation_id"],
            "preserved_membership_ids": row["preserved_membership_ids"],
            "removed_membership_ids": row["remove_membership_ids"],
            "source_cell": row["source_cell"],
            "team_id": row["team_id"],
            "team_key": team_keys[row["team_id"]],
            "workbook_sha256": payload["workbook_sha256"],
        }
    )


def apply_team_roster_confirmation(
    *,
    reviewed_person_state,
    assignment_preview_state,
    confirmation_state,
    user,
    language="en",
    max_age=TEAM_ROSTER_CONFIRMATION_MAX_AGE_SECONDS,
    now=None,
):
    """Apply one exact generic roster batch in one outer transaction."""

    classification_now = now or timezone.now()
    claim_results = ()
    created_by_pair = {}
    created_member_ids_by_pair = {}
    added_member_ids_by_assignment = {}
    removed_member_ids = []
    audit_rows = []
    try:
        with transaction.atomic():
            actor = _require_current_actor(user)
            authority = decode_team_roster_confirmation(
                confirmation_state,
                reviewed_person_state=reviewed_person_state,
                assignment_preview_state=assignment_preview_state,
                user=actor,
                language=language,
                max_age=max_age,
                now=classification_now,
            )
            payload = authority.payload
            preview = authority.preview
            rows = payload["rows"]
            create_rows = [
                item
                for item in rows
                if item["classification"]
                == TeamRosterAssignmentPreviewState.CREATE_CANDIDATE.value
            ]
            create_event_ids = frozenset(item["event_id"] for item in create_rows)
            expected_revisions = {}
            for item in create_rows:
                revision = item["expected_create_event_revision"]
                existing = expected_revisions.setdefault(item["event_id"], revision)
                if existing != revision:
                    raise TeamRosterConfirmationProposalError(
                        "Create rows disagree on their event revision baseline."
                    )
            if expected_revisions:
                claim_results = claim_scheduling_revisions(expected_revisions)

            assignment_baselines = _assignment_by_id(preview.normalized_payload)
            _conditional_assignment_barriers(rows, assignment_baselines)

            actor = _require_current_actor(actor)
            current_preview = _writer_aware_recompute(
                reviewed_person_state=reviewed_person_state,
                assignment_preview_state=assignment_preview_state,
                actor=actor,
                preview=preview,
                create_event_ids=create_event_ids,
                language=language,
                max_age=max_age,
                now=classification_now,
            )
            if (
                current_preview.normalized_payload["summary"]
                != preview.normalized_payload["summary"]
            ):
                raise TeamRosterConfirmationStaleError(
                    "Writable scheduling truth changed after serialization."
                )

            event_ids = {item["event_id"] for item in rows}
            team_ids = {item["team_id"] for item in rows}
            membership_ids = {
                membership_id
                for item in rows
                for key in (
                    "reviewed_membership_ids",
                    "preserved_membership_ids",
                    "add_membership_ids",
                    "remove_membership_ids",
                )
                for membership_id in item[key]
            }
            events = ServiceEvent.objects.in_bulk(event_ids)
            teams = MinistryTeam.objects.in_bulk(team_ids)
            memberships = TeamMembership.objects.select_related("user").in_bulk(
                membership_ids
            )
            if (
                len(events) != len(event_ids)
                or len(teams) != len(team_ids)
                or len(memberships) != len(membership_ids)
            ):
                raise TeamRosterConfirmationStaleError(
                    "Reviewed event, team, or membership truth disappeared."
                )

            for row in sorted(create_rows, key=lambda item: (item["event_id"], item["team_id"])):
                pair = (row["event_id"], row["team_id"])
                if TeamAssignment.objects.filter(
                    service_event_id=pair[0], ministry_team_id=pair[1]
                ).exists():
                    raise TeamRosterConfirmationStaleError(
                        "A create destination is no longer empty."
                    )
                assignment = TeamAssignment(
                    service_event=events[pair[0]],
                    ministry_team=teams[pair[1]],
                    status=TeamAssignment.STATUS_SCHEDULED,
                    notes="",
                    created_by=actor,
                    reviewed_worship_context_fingerprint=None,
                )
                assignment.save(force_insert=True, _skip_scheduling_revision=True)
                member_ids = set()
                for membership_id in row["reviewed_membership_ids"]:
                    member = TeamAssignmentMember(
                        assignment=assignment,
                        membership=memberships[membership_id],
                        confirmed_at=None,
                        confirmation_note="",
                    )
                    member.save(force_insert=True)
                    member_ids.add(member.pk)
                created_by_pair[pair] = assignment
                created_member_ids_by_pair[pair] = member_ids
                audit_rows.append((assignment.pk, ADDITION, row))

            membership_baselines = _membership_baselines(preview.normalized_payload)
            update_rows = [
                item
                for item in rows
                if item["classification"]
                == TeamRosterAssignmentPreviewState.ROSTER_UPDATE_CANDIDATE.value
            ]
            for row in sorted(update_rows, key=lambda item: item["assignment_id"]):
                assignment = TeamAssignment.objects.get(pk=row["assignment_id"])
                baseline = assignment_baselines[row["assignment_id"]]
                baseline_member_by_membership = {
                    item["membership_id"]: item for item in baseline["members"]
                }
                for membership_id in row["remove_membership_ids"]:
                    member_id = baseline_member_by_membership[membership_id]["id"]
                    if member_id not in row["removable_assignment_member_ids"]:
                        raise TeamRosterConfirmationStaleError(
                            "A removable through-row identity is inconsistent."
                        )
                    _delete_exact_member(
                        row=row,
                        membership_id=membership_id,
                        member_id=member_id,
                        membership_baseline=membership_baselines[membership_id],
                    )
                    removed_member_ids.append(member_id)
                added_ids = set()
                for membership_id in row["add_membership_ids"]:
                    member = TeamAssignmentMember(
                        assignment=assignment,
                        membership=memberships[membership_id],
                        confirmed_at=None,
                        confirmation_note="",
                    )
                    member.save(force_insert=True)
                    added_ids.add(member.pk)
                added_member_ids_by_assignment[assignment.pk] = added_ids
                audit_rows.append((assignment.pk, CHANGE, row))

            _assert_domain_postconditions(
                payload=payload,
                preview=preview,
                actor=actor,
                created_by_pair=created_by_pair,
                created_member_ids_by_pair=created_member_ids_by_pair,
                added_member_ids_by_assignment=added_member_ids_by_assignment,
                create_event_ids=create_event_ids,
            )

            content_type_id = ContentType.objects.get_for_model(TeamAssignment).pk
            written_audits = []
            for assignment_id, action_flag, row in sorted(
                audit_rows, key=lambda item: item[0]
            ):
                message = _audit_message(
                    payload=payload, row=row, assignment_id=assignment_id
                )
                try:
                    LogEntry.objects.log_action(
                        user_id=actor.pk,
                        content_type_id=content_type_id,
                        object_id=assignment_id,
                        object_repr=f"TeamAssignment #{assignment_id}",
                        action_flag=action_flag,
                        change_message=message,
                    )
                except Exception as exc:
                    raise TeamRosterConfirmationAuditError(
                        "Confirmation audit failed; the whole batch was rolled back."
                    ) from exc
                written_audits.append((assignment_id, action_flag, message))
            for assignment_id, action_flag, message in written_audits:
                if LogEntry.objects.filter(
                    user_id=actor.pk,
                    content_type_id=content_type_id,
                    object_id=str(assignment_id),
                    action_flag=action_flag,
                    change_message=message,
                ).count() != 1:
                    raise TeamRosterConfirmationAuditError(
                        "Confirmation audit postcondition failed; the batch was rolled back."
                    )
    except TeamRosterConfirmationBusyError:
        raise
    except SchedulingRevisionBusyError as exc:
        raise TeamRosterConfirmationBusyError(
            "Scheduling is busy; no team roster was changed."
        ) from exc
    except SchedulingRevisionError as exc:
        raise TeamRosterConfirmationStaleError(
            "A reviewed event revision is stale; the whole batch was rolled back."
        ) from exc
    except OperationalError as exc:
        message = str(exc).lower()
        if "database is locked" in message or "database table is locked" in message:
            raise TeamRosterConfirmationBusyError(
                "Scheduling is busy; no team roster was changed."
            ) from exc
        raise
    except TeamRosterConfirmationError:
        raise
    except (
        IntegrityError,
        ValidationError,
        TeamRosterAssignmentPreviewError,
        TeamRosterPersonMappingStateError,
        IntegrationDisabled,
    ) as exc:
        raise TeamRosterConfirmationStaleError(
            "Reviewed scheduling truth changed; the whole batch was rolled back."
        ) from exc

    created_assignments = tuple(
        assignment.pk for _pair, assignment in sorted(created_by_pair.items())
    )
    updated_assignments = tuple(
        sorted(
            item[0]
            for item in audit_rows
            if item[1] == CHANGE
        )
    )
    return TeamRosterConfirmationResult(
        operation_id=payload["operation_id"],
        workbook_sha256=payload["workbook_sha256"],
        created_assignment_ids=created_assignments,
        updated_assignment_ids=updated_assignments,
        created_assignment_member_ids=tuple(
            sorted(
                member_id
                for member_ids in created_member_ids_by_pair.values()
                for member_id in member_ids
            )
        ),
        added_assignment_member_ids=tuple(
            sorted(
                member_id
                for member_ids in added_member_ids_by_assignment.values()
                for member_id in member_ids
            )
        ),
        removed_assignment_member_ids=tuple(sorted(removed_member_ids)),
        claimed_event_ids=tuple(item.event_id for item in claim_results),
        log_entry_count=len(audit_rows),
    )
