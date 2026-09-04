"""Atomic confirmation for the reviewed annual Worship workbook proposal.

The Slice 8 parser/preview remains side-effect free.  This module owns the
distinct, user-bound Slice 9 confirmation artifact and the one atomic write
boundary.  It deliberately reuses the canonical ServiceEvent scheduling CAS
and Worship governance helpers and registers no notification producer.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
import re
from uuid import UUID, uuid4

from django.contrib.admin.models import CHANGE, LogEntry
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core import signing
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from events.models import ServiceEvent
from events.scheduling_revision import claim_scheduling_revisions
from events.service_profile_readiness import service_event_audience_readiness
from events.service_profile_runtime import inspect_service_profile_identity

from ..models import MinistryTeam
from .worship_governance import (
    WorshipOwnershipConsistencyState,
    inspect_worship_ownership_consistency,
)
from .worship_xlsx_preview import (
    CONTRACT_REVISION as PARSER_CONTRACT_REVISION,
    INTEGRATION_KEY,
    NORMALIZED_PREVIEW_CONTRACT_REVISION,
    SUPPORTED_EVENT_TYPE,
    SUPPORTED_LOCAL_TIME,
    SUPPORTED_PROFILE_KEY,
    SUPPORTED_ROWS,
    SUPPORTED_SHEET,
    TOKEN_ORDER,
    PreviewClassification,
    TargetServiceProfileError,
    TargetServiceProfileIdentity,
    TargetMatchState,
    resolve_target_service_profile,
)


CONFIRMATION_PROPOSAL_TYPE = "annual_worship_workbook_confirmation"
CONFIRMATION_CONTRACT_REVISION = "SVCA_BETHANY_0930_2026_CONFIRM_V2"
CONFIRMATION_SIGNING_VERSION = 2
CONFIRMATION_SIGNING_SALT = "ministry.worship-xlsx-confirmation.v2"
CONFIRMATION_MAX_AGE_SECONDS = 1800

_SHA256_RE = re.compile(r"^[0-9A-Fa-f]{64}$")
_VALID_CHANGE_OWNERSHIP_STATES = {
    WorshipOwnershipConsistencyState.NO_SELECTION,
    WorshipOwnershipConsistencyState.SELECTED_UNSCHEDULED,
}
_VALID_NO_OP_OWNERSHIP_STATES = {
    WorshipOwnershipConsistencyState.SELECTED_UNSCHEDULED,
    WorshipOwnershipConsistencyState.CONSISTENT,
}


class WorshipWorkbookConfirmationProposalError(ValueError):
    """A confirmation proposal is malformed, expired, or user-mismatched."""


class WorshipWorkbookConfirmationError(RuntimeError):
    """Current truth no longer permits the reviewed all-or-nothing write."""


class WorshipWorkbookConfirmationAuditError(WorshipWorkbookConfirmationError):
    """The transactional annual-import audit could not be written."""


@dataclass(frozen=True)
class WorshipWorkbookConfirmationProposal:
    operation_id: str
    normalized_payload: dict
    signed_payload: str
    selected_count: int
    changed_count: int
    no_op_count: int

    @property
    def signed_payload_bytes(self):
        return len(self.signed_payload.encode("utf-8"))


@dataclass(frozen=True)
class WorshipWorkbookConfirmationChange:
    event_id: int
    local_date: date
    old_team: MinistryTeam | None
    new_team: MinistryTeam


@dataclass(frozen=True)
class WorshipWorkbookConfirmationResult:
    filename: str
    workbook_sha256: str
    operation_id: str
    claimed_event_ids: tuple[int, ...]
    changes: tuple[WorshipWorkbookConfirmationChange, ...]
    no_op_count: int
    log_entry_count: int

    @property
    def selected_count(self):
        return len(self.claimed_event_ids)

    @property
    def changed_count(self):
        return len(self.changes)


def user_can_confirm_worship_workbook(user):
    return bool(
        getattr(user, "is_authenticated", False)
        and getattr(user, "is_active", False)
        and (
            getattr(user, "is_staff", False)
            or getattr(user, "is_superuser", False)
        )
    )


def _is_positive_int(value):
    return type(value) is int and value > 0


def _is_nonnegative_int(value):
    return type(value) is int and value >= 0


def _is_optional_positive_int(value):
    return value is None or _is_positive_int(value)


def _expected_date_for_source_row(source_row):
    index = 0 if source_row == 4 else source_row - 5
    return date(2026, 1, 4) + timedelta(weeks=index)


def _filename_is_sanitized(value):
    return (
        isinstance(value, str)
        and 0 < len(value) <= 255
        and "\x00" not in value
        and "/" not in value
        and "\\" not in value
        and value not in {".", ".."}
    )


def _strict_payload_shape(payload):
    required_top_level = {
        "proposal_type",
        "confirmation_contract_revision",
        "confirmation_signing_version",
        "parser_contract_revision",
        "preview_contract_revision",
        "integration_key",
        "profile_id",
        "profile_key",
        "profile_event_type",
        "generated_at",
        "user_id",
        "operation_id",
        "filename",
        "workbook_sha256",
        "supported_sheet",
        "mapping_team_ids",
        "rows",
    }
    if not isinstance(payload, dict) or set(payload) != required_top_level:
        raise WorshipWorkbookConfirmationProposalError(
            "Invalid confirmation proposal shape."
        )
    if (
        payload["proposal_type"] != CONFIRMATION_PROPOSAL_TYPE
        or payload["confirmation_contract_revision"]
        != CONFIRMATION_CONTRACT_REVISION
        or payload["confirmation_signing_version"]
        != CONFIRMATION_SIGNING_VERSION
        or payload["parser_contract_revision"] != PARSER_CONTRACT_REVISION
        or payload["preview_contract_revision"]
        != NORMALIZED_PREVIEW_CONTRACT_REVISION
        or payload["integration_key"] != INTEGRATION_KEY
        or not _is_positive_int(payload["profile_id"])
        or not isinstance(payload["profile_key"], str)
        or payload["profile_key"] != SUPPORTED_PROFILE_KEY
        or not isinstance(payload["profile_event_type"], str)
        or payload["profile_event_type"] != SUPPORTED_EVENT_TYPE
        or payload["supported_sheet"] != SUPPORTED_SHEET
        or not _is_positive_int(payload["user_id"])
        or not isinstance(payload["generated_at"], str)
        or parse_datetime(payload["generated_at"]) is None
        or not _filename_is_sanitized(payload["filename"])
        or not isinstance(payload["workbook_sha256"], str)
        or _SHA256_RE.fullmatch(payload["workbook_sha256"]) is None
    ):
        raise WorshipWorkbookConfirmationProposalError(
            "Invalid confirmation proposal contract facts."
        )

    operation_id = payload["operation_id"]
    try:
        parsed_operation_id = UUID(operation_id)
    except (AttributeError, TypeError, ValueError) as exc:
        raise WorshipWorkbookConfirmationProposalError(
            "Invalid confirmation operation identifier."
        ) from exc
    if str(parsed_operation_id) != operation_id:
        raise WorshipWorkbookConfirmationProposalError(
            "Invalid confirmation operation identifier."
        )

    rows = payload["rows"]
    mapping = payload["mapping_team_ids"]
    row_keys = {
        "source_row",
        "local_date",
        "token",
        "event_id",
        "expected_service_profile_id",
        "expected_scheduling_revision",
        "expected_before_team_id",
        "proposed_team_id",
    }
    if (
        not isinstance(rows, list)
        or len(rows) != len(SUPPORTED_ROWS)
        or not isinstance(mapping, dict)
        or any(not isinstance(row, dict) or set(row) != row_keys for row in rows)
    ):
        raise WorshipWorkbookConfirmationProposalError(
            "Invalid confirmation row shape."
        )

    source_rows = [row["source_row"] for row in rows]
    if source_rows != list(SUPPORTED_ROWS) or len(set(source_rows)) != len(source_rows):
        raise WorshipWorkbookConfirmationProposalError(
            "Invalid confirmation source-row set."
        )
    event_ids = [row["event_id"] for row in rows]
    if any(not _is_positive_int(value) for value in event_ids) or len(
        set(event_ids)
    ) != len(event_ids):
        raise WorshipWorkbookConfirmationProposalError(
            "Invalid confirmation event identifiers."
        )

    tokens = []
    for row in rows:
        source_row = row["source_row"]
        try:
            local_date = date.fromisoformat(row["local_date"])
        except (TypeError, ValueError) as exc:
            raise WorshipWorkbookConfirmationProposalError(
                "Invalid confirmation Sunday date."
            ) from exc
        token = row["token"]
        if (
            local_date != _expected_date_for_source_row(source_row)
            or local_date.weekday() != 6
            or not isinstance(token, str)
            or token not in TOKEN_ORDER
            or row["expected_service_profile_id"] != payload["profile_id"]
            or not _is_nonnegative_int(row["expected_scheduling_revision"])
            or not _is_optional_positive_int(row["expected_before_team_id"])
            or not _is_positive_int(row["proposed_team_id"])
        ):
            raise WorshipWorkbookConfirmationProposalError(
                "Invalid confirmation row contract facts."
            )
        tokens.append(token)

    present_tokens = {token for token in TOKEN_ORDER if token in tokens}
    if set(mapping) != present_tokens or any(
        not _is_positive_int(team_id) for team_id in mapping.values()
    ):
        raise WorshipWorkbookConfirmationProposalError(
            "Invalid confirmation token mapping."
        )
    if any(row["proposed_team_id"] != mapping[row["token"]] for row in rows):
        raise WorshipWorkbookConfirmationProposalError(
            "Confirmation rows do not match the explicit token mapping."
        )
    if not any(
        row["expected_before_team_id"] != row["proposed_team_id"] for row in rows
    ):
        raise WorshipWorkbookConfirmationProposalError(
            "The confirmation proposal contains no change."
        )
    return payload


def build_worship_workbook_confirmation_proposal(*, preview, user):
    """Mint one distinct confirmation artifact from a fully reviewed preview."""

    if not user_can_confirm_worship_workbook(user):
        raise WorshipWorkbookConfirmationProposalError(
            "Current user cannot confirm an annual Worship workbook."
        )
    if (
        len(preview.rows) != len(SUPPORTED_ROWS)
        or preview.matched_target_count != len(SUPPORTED_ROWS)
        or not preview.mapping_complete
        or preview.blocked_count != 0
        or preview.proposed_change_count <= 0
    ):
        raise WorshipWorkbookConfirmationProposalError(
            "The reviewed workbook preview is not confirmable."
        )
    target_profile = preview.target_profile
    expected_target_profile = {
        "profile_id": target_profile.profile_id,
        "profile_key": target_profile.profile_key,
        "profile_event_type": target_profile.profile_event_type,
    }
    if (
        preview.normalized_payload.get("contract_revision")
        != NORMALIZED_PREVIEW_CONTRACT_REVISION
        or preview.normalized_payload.get("parser_contract_revision")
        != PARSER_CONTRACT_REVISION
        or preview.normalized_payload.get("integration_key") != INTEGRATION_KEY
        or preview.normalized_payload.get("target_profile")
        != expected_target_profile
    ):
        raise WorshipWorkbookConfirmationProposalError(
            "The reviewed workbook preview Service Profile is invalid."
        )

    normalized_rows = []
    for row in preview.rows:
        if (
            row.target_state != TargetMatchState.EXACT_TARGET_MATCHED
            or row.classification
            not in {
                PreviewClassification.NO_OP,
                PreviewClassification.PROPOSED_CHANGE,
            }
            or row.event is None
            or row.proposed_team is None
            or not isinstance(row.fingerprints, dict)
        ):
            raise WorshipWorkbookConfirmationProposalError(
                "The reviewed workbook preview is not confirmable."
            )
        revision = row.fingerprints.get("event", {}).get("scheduling_revision")
        if not _is_nonnegative_int(revision):
            raise WorshipWorkbookConfirmationProposalError(
                "The reviewed event revision is invalid."
            )
        normalized_rows.append(
            {
                "source_row": row.source.source_row,
                "local_date": row.source.local_date.isoformat(),
                "token": row.source.token,
                "event_id": row.event.pk,
                "expected_service_profile_id": row.event.service_profile_id,
                "expected_scheduling_revision": revision,
                "expected_before_team_id": row.event.rotation_anchor_team_id,
                "proposed_team_id": row.proposed_team.pk,
            }
        )

    operation_id = str(uuid4())
    payload = {
        "proposal_type": CONFIRMATION_PROPOSAL_TYPE,
        "confirmation_contract_revision": CONFIRMATION_CONTRACT_REVISION,
        "confirmation_signing_version": CONFIRMATION_SIGNING_VERSION,
        "parser_contract_revision": PARSER_CONTRACT_REVISION,
        "preview_contract_revision": NORMALIZED_PREVIEW_CONTRACT_REVISION,
        "integration_key": INTEGRATION_KEY,
        "profile_id": target_profile.profile_id,
        "profile_key": target_profile.profile_key,
        "profile_event_type": target_profile.profile_event_type,
        "generated_at": timezone.now().isoformat(),
        "user_id": user.pk,
        "operation_id": operation_id,
        "filename": preview.parsed.filename,
        "workbook_sha256": preview.parsed.sha256,
        "supported_sheet": SUPPORTED_SHEET,
        "mapping_team_ids": {
            token: preview.mappings[token].pk
            for token in TOKEN_ORDER
            if token in preview.parsed.token_counts
        },
        "rows": normalized_rows,
    }
    _strict_payload_shape(payload)
    signed_payload = signing.dumps(
        payload,
        compress=True,
        salt=CONFIRMATION_SIGNING_SALT,
    )
    return WorshipWorkbookConfirmationProposal(
        operation_id=operation_id,
        normalized_payload=payload,
        signed_payload=signed_payload,
        selected_count=len(normalized_rows),
        changed_count=preview.proposed_change_count,
        no_op_count=preview.no_op_count,
    )


def decode_signed_worship_workbook_confirmation(
    token, *, user, max_age=CONFIRMATION_MAX_AGE_SECONDS
):
    """Decode and strictly validate the distinct user-bound proposal."""

    try:
        payload = signing.loads(
            token,
            salt=CONFIRMATION_SIGNING_SALT,
            max_age=max_age,
        )
    except signing.BadSignature as exc:
        raise WorshipWorkbookConfirmationProposalError(
            "Invalid or expired annual-workbook confirmation proposal."
        ) from exc
    _strict_payload_shape(payload)
    if (
        not user_can_confirm_worship_workbook(user)
        or payload["user_id"] != getattr(user, "pk", None)
    ):
        raise WorshipWorkbookConfirmationProposalError(
            "The annual-workbook proposal belongs to another user."
        )
    try:
        current_profile = resolve_target_service_profile()
    except TargetServiceProfileError as exc:
        raise WorshipWorkbookConfirmationProposalError(
            "The annual-workbook Service Profile is no longer current. "
            "Generate a new workbook preview."
        ) from exc
    current_identity = TargetServiceProfileIdentity(
        profile_id=current_profile.pk,
        profile_key=current_profile.key,
        profile_event_type=current_profile.event_type,
    )
    signed_identity = TargetServiceProfileIdentity(
        profile_id=payload["profile_id"],
        profile_key=payload["profile_key"],
        profile_event_type=payload["profile_event_type"],
    )
    if signed_identity != current_identity:
        raise WorshipWorkbookConfirmationProposalError(
            "The annual-workbook Service Profile changed. "
            "Generate a new workbook preview."
        )
    return payload


def _annual_import_change_message(*, payload, row):
    return (
        "source=annual_worship_workbook_import;"
        f"operation_id={payload['operation_id']};"
        f"workbook_sha256={payload['workbook_sha256']};"
        f"integration_key={payload['integration_key']};"
        f"profile_id={payload['profile_id']};"
        f"profile_key={payload['profile_key']};"
        f"profile_event_type={payload['profile_event_type']};"
        f"parser_contract_revision={payload['parser_contract_revision']};"
        "confirmation_contract_revision="
        f"{payload['confirmation_contract_revision']};"
        f"event_id={row['event_id']};"
        f"local_date={row['local_date']};"
        f"old_team_id={row['expected_before_team_id']};"
        f"new_team_id={row['proposed_team_id']}."
    )


def confirm_worship_workbook(*, user, payload):
    """Claim all 52 revisions, recompute truth, save changes, and audit once."""

    _strict_payload_shape(payload)
    if payload["user_id"] != getattr(user, "pk", None):
        raise WorshipWorkbookConfirmationProposalError(
            "The annual-workbook proposal belongs to another user."
        )
    expected_revisions = tuple(
        (row["event_id"], row["expected_scheduling_revision"])
        for row in payload["rows"]
    )
    event_ids = tuple(row["event_id"] for row in payload["rows"])

    with transaction.atomic():
        actor = get_user_model()._default_manager.filter(pk=user.pk).first()
        if actor is None or not user_can_confirm_worship_workbook(actor):
            raise WorshipWorkbookConfirmationError(
                "Annual-workbook authority changed after preview."
            )

        claim_results = claim_scheduling_revisions(expected_revisions)

        try:
            current_profile = resolve_target_service_profile()
        except TargetServiceProfileError as exc:
            raise WorshipWorkbookConfirmationError(
                "The annual-workbook Service Profile changed after review."
            ) from exc
        current_profile_identity = TargetServiceProfileIdentity(
            profile_id=current_profile.pk,
            profile_key=current_profile.key,
            profile_event_type=current_profile.event_type,
        )
        signed_profile_identity = TargetServiceProfileIdentity(
            profile_id=payload["profile_id"],
            profile_key=payload["profile_key"],
            profile_event_type=payload["profile_event_type"],
        )
        if current_profile_identity != signed_profile_identity:
            raise WorshipWorkbookConfirmationError(
                "The annual-workbook Service Profile changed after review."
            )

        reloaded_events = {
            event.pk: event
            for event in ServiceEvent.objects.filter(pk__in=event_ids)
            .select_related("service_profile", "rotation_anchor_team")
            .prefetch_related("audience_scope_links__unit")
        }
        if set(reloaded_events) != set(event_ids):
            raise WorshipWorkbookConfirmationError(
                "An exact annual-workbook target no longer exists."
            )

        mapped_team_ids = set(payload["mapping_team_ids"].values())
        mapped_teams = MinistryTeam.objects.in_bulk(mapped_team_ids)
        if set(mapped_teams) != mapped_team_ids or any(
            not team.is_active or not team.is_assignable
            for team in mapped_teams.values()
        ):
            raise WorshipWorkbookConfirmationError(
                "A mapped Worship Team is no longer available."
            )

        validated = []
        local_tz = timezone.get_current_timezone()
        for row in payload["rows"]:
            event = reloaded_events[row["event_id"]]
            profile_identity = inspect_service_profile_identity(event)
            expected_revision = row["expected_scheduling_revision"]
            local_start = timezone.localtime(event.start_datetime, local_tz)
            if (
                event.scheduling_revision != expected_revision + 1
                or not profile_identity.is_exact
                or profile_identity.profile_id != current_profile.pk
                or row["expected_service_profile_id"] != current_profile.pk
                or local_start.date() != date.fromisoformat(row["local_date"])
                or local_start.time().replace(tzinfo=None) != SUPPORTED_LOCAL_TIME
                or event.status
                not in {
                    ServiceEvent.STATUS_PUBLISHED,
                    ServiceEvent.STATUS_COMPLETED,
                }
                or not service_event_audience_readiness(event)["ready"]
                or event.rotation_anchor_team_id
                != row["expected_before_team_id"]
            ):
                raise WorshipWorkbookConfirmationError(
                    "An annual-workbook target changed after review."
                )

            proposed_team = mapped_teams[row["proposed_team_id"]]
            inspection = inspect_worship_ownership_consistency(event)
            eligible_team_ids = {
                candidate.team.pk for candidate in inspection.eligible_candidates
            }
            if proposed_team.pk not in eligible_team_ids:
                raise WorshipWorkbookConfirmationError(
                    "A mapped Worship Team is no longer eligible."
                )

            changed = event.rotation_anchor_team_id != proposed_team.pk
            if changed:
                if (
                    inspection.current_worship_assignments
                    or inspection.state not in _VALID_CHANGE_OWNERSHIP_STATES
                ):
                    raise WorshipWorkbookConfirmationError(
                        "Current Worship ownership blocks this change."
                    )
            elif inspection.state not in _VALID_NO_OP_OWNERSHIP_STATES:
                raise WorshipWorkbookConfirmationError(
                    "Current Worship ownership is not a safe no-op."
                )
            validated.append((row, event, proposed_team, changed))

        content_type_id = ContentType.objects.get_for_model(ServiceEvent).pk
        changes = []
        log_entry_count = 0
        for row, event, proposed_team, changed in validated:
            if not changed:
                continue
            old_team = event.rotation_anchor_team
            event.rotation_anchor_team = proposed_team
            event.save(
                update_fields=["rotation_anchor_team", "updated_at"],
                _skip_scheduling_revision=True,
            )
            try:
                LogEntry.objects.log_action(
                    user_id=actor.pk,
                    content_type_id=content_type_id,
                    object_id=event.pk,
                    object_repr=str(event),
                    action_flag=CHANGE,
                    change_message=_annual_import_change_message(
                        payload=payload,
                        row=row,
                    ),
                )
            except Exception as exc:
                raise WorshipWorkbookConfirmationAuditError(
                    "Annual Worship workbook audit write failed."
                ) from exc
            changes.append(
                WorshipWorkbookConfirmationChange(
                    event_id=event.pk,
                    local_date=date.fromisoformat(row["local_date"]),
                    old_team=old_team,
                    new_team=proposed_team,
                )
            )
            log_entry_count += 1

    return WorshipWorkbookConfirmationResult(
        filename=payload["filename"],
        workbook_sha256=payload["workbook_sha256"],
        operation_id=payload["operation_id"],
        claimed_event_ids=tuple(result.event_id for result in claim_results),
        changes=tuple(changes),
        no_op_count=len(payload["rows"]) - len(changes),
        log_entry_count=log_entry_count,
    )
