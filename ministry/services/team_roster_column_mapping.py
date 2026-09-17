"""Zero-write reviewed column mapping for the annual Team Roster workbook.

This service deliberately stops before roster-cell parsing or person identity.
The deployment-owned adapter supplies exact A:O inventory and event-target
evidence; this module signs that evidence, presents current active/assignable
teams, and mints a distinct reviewed column-mapping state.
"""

from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
import json
import re

from django.core import signing
from django.utils import timezone

from ministry.integrations.svca_bethany_2026_worship_xlsx.team_roster_sources import (
    TEAM_ROSTER_COLUMN_HINTS,
    TEAM_ROSTER_COLUMN_SCOPE,
    TeamRosterColumnScope,
    inventory_team_roster_columns,
)
from ministry.models import (
    MINISTRY_TEAM_KEY_PATTERN,
    MinistryTeam,
    normalize_ministry_team_key,
)
from ministry.services.team_roster_workbook import (
    ReviewedTeamRosterColumn,
    resolve_exact_team_roster_column_hint,
)
from ministry.services.worship_xlsx_preview import (
    CONTRACT_REVISION,
    INTEGRATION_KEY,
    SIGNING_MAX_AGE_SECONDS,
    SUPPORTED_SHEET,
    TargetMatchState,
    decode_parsed_workbook,
    match_exact_service_event_targets,
    sign_parsed_workbook,
)


TEAM_ROSTER_COLUMN_MAPPING_REVIEW_V1 = "TEAM_ROSTER_COLUMN_MAPPING_REVIEW_V1"
TEAM_ROSTER_REVIEWED_COLUMN_MAPPING_V1 = (
    "TEAM_ROSTER_REVIEWED_COLUMN_MAPPING_V1"
)
INVENTORY_STATE_TYPE = "team_roster_column_inventory_review"
REVIEWED_STATE_TYPE = "team_roster_reviewed_column_mapping"
INVENTORY_SIGNING_SALT = (
    "ministry.team_roster.column_mapping.inventory.v1"
)
REVIEWED_SIGNING_SALT = (
    "ministry.team_roster.column_mapping.reviewed.v1"
)
MAX_COLUMN_MAPPING_STATE_BYTES = 16_384

_SHA256_RE = re.compile(r"^[0-9A-F]{64}$")
_TEAM_ROSTER_DESTINATION_KEY_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]*$")
_COLUMNS = tuple("ABCDEFGHIJKLMNO")
_CANDIDATE_COLUMNS = tuple("CDEFGHI")


class TeamRosterColumnMappingStateError(ValueError):
    """Signed inventory state is malformed, stale, or no longer current."""


class TeamRosterColumnMappingValidationError(ValueError):
    """A submitted reviewed mapping is not valid."""


class TeamRosterColumnMappingTargetBlocked(ValueError):
    """Exact adapter event targets are not ready for next-stage authority."""


@dataclass(frozen=True, slots=True)
class TeamRosterDestinationOption:
    team_id: int
    team_key: str
    display_name: str


@dataclass(frozen=True, slots=True)
class TeamRosterColumnReviewRow:
    sheet_name: str
    column: str
    observed_header: str
    scope: TeamRosterColumnScope
    hint_team_key: str | None
    prefill_team_id: int | None
    hint_warning: str | None

    @property
    def is_candidate(self):
        return self.scope == TeamRosterColumnScope.TARGET_PROFILE_REVIEW_CANDIDATE


@dataclass(frozen=True, slots=True)
class TeamRosterTargetEvidence:
    source_row: int
    state: str
    event_id: int | None
    exact_target_ids: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class TeamRosterColumnMappingReview:
    filename: str
    workbook_sha256: str
    sheet_name: str
    columns: tuple[TeamRosterColumnReviewRow, ...]
    destination_options: tuple[TeamRosterDestinationOption, ...]
    target_evidence: tuple[TeamRosterTargetEvidence, ...]
    signed_inventory_state: str
    signed_state_bytes: int
    offered_team_identities: tuple[tuple[int, str], ...]

    @property
    def target_gate_ready(self):
        return bool(self.target_evidence) and all(
            item.state == TargetMatchState.EXACT_TARGET_MATCHED.value
            for item in self.target_evidence
        )

    @property
    def target_blocker_count(self):
        return sum(
            item.state != TargetMatchState.EXACT_TARGET_MATCHED.value
            for item in self.target_evidence
        )

    @property
    def target_state_counts(self):
        return tuple(sorted(Counter(item.state for item in self.target_evidence).items()))


@dataclass(frozen=True, slots=True)
class ReviewedTeamRosterColumnChoice:
    sheet_name: str
    column: str
    observed_header: str
    destination_team_id: int | None
    destination_team_key: str | None
    destination_display_name: str | None

    @property
    def is_ignored(self):
        return self.destination_team_id is None


@dataclass(frozen=True, slots=True)
class ReviewedTeamRosterColumnMapping:
    filename: str
    workbook_sha256: str
    sheet_name: str
    choices: tuple[ReviewedTeamRosterColumnChoice, ...]
    signed_reviewed_state: str
    signed_state_bytes: int

    @property
    def mapped_count(self):
        return sum(not choice.is_ignored for choice in self.choices)

    @property
    def ignored_count(self):
        return sum(choice.is_ignored for choice in self.choices)


def user_can_review_team_roster_columns(user):
    return bool(
        getattr(user, "is_authenticated", False)
        and getattr(user, "is_active", False)
        and (getattr(user, "is_staff", False) or getattr(user, "is_superuser", False))
    )


def _is_canonical_team_key(value):
    if not isinstance(value, str) or not value:
        return False
    try:
        normalized = normalize_ministry_team_key(value)
    except Exception:
        return False
    return (
        normalized == value
        and MINISTRY_TEAM_KEY_PATTERN.fullmatch(value) is not None
        and _TEAM_ROSTER_DESTINATION_KEY_RE.fullmatch(value) is not None
    )


def _eligible_team(team):
    return bool(
        team.is_active
        and team.is_assignable
        and _is_canonical_team_key(team.team_key)
    )


def _team_display_name(team, language):
    primary = team.get_name(language)
    secondary = team.name_en if language == "zh" else team.name
    if secondary and secondary != primary:
        return f"{primary} / {secondary}"
    return primary


def _team_sort_key(team, language):
    return (
        _team_display_name(team, language).casefold(),
        (team.name or "").casefold(),
        team.pk,
    )


def _all_teams():
    return list(MinistryTeam.objects.all().order_by("id"))


def _eligible_identities(teams):
    return tuple(
        sorted(
            (team.pk, team.team_key)
            for team in teams
            if _eligible_team(team)
        )
    )


def _destination_options(teams, *, offered_identities, language):
    offered = dict(offered_identities)
    current = [
        team
        for team in teams
        if _eligible_team(team) and offered.get(team.pk) == team.team_key
    ]
    current.sort(key=lambda team: _team_sort_key(team, language))
    return tuple(
        TeamRosterDestinationOption(
            team_id=team.pk,
            team_key=team.team_key,
            display_name=_team_display_name(team, language),
        )
        for team in current
    )


def _hint_resolution(hint_team_key, teams, offered_identities):
    if hint_team_key is None:
        return None, None
    exact = [team for team in teams if team.team_key == hint_team_key]
    offered = dict(offered_identities)
    if len(exact) == 1:
        team = exact[0]
        if not team.is_active:
            return None, "inactive"
        if not team.is_assignable:
            return None, "nonassignable"
        if not _is_canonical_team_key(team.team_key):
            return None, "malformed_or_drifted"
        if offered.get(team.pk) != team.team_key:
            return None, "stale_identity"
        return team.pk, None
    if len(exact) > 1:
        return None, "ambiguous"
    for team in teams:
        try:
            if normalize_ministry_team_key(team.team_key) == hint_team_key:
                return None, "malformed_or_drifted"
        except Exception:
            continue
    return None, "missing"


def _serialize_columns(inventory):
    return [
        {
            "sheet": item.observed_column.sheet_name,
            "column": item.observed_column.column,
            "header": item.observed_column.observed_header,
            "scope": item.scope.value,
            "hint_team_key": (
                item.matched_hint.destination_team_key
                if item.matched_hint is not None
                else None
            ),
        }
        for item in inventory.observed_columns
    ]


def _serialize_target_matches(matches):
    serialized = []
    for match in matches:
        event = match.event
        serialized.append(
            {
                "source_row": match.row.source_row,
                "state": match.state.value,
                "event_id": event.pk if event is not None else None,
                "event_start": (
                    event.start_datetime.isoformat() if event is not None else None
                ),
                "event_status": event.status if event is not None else None,
                "event_revision": (
                    event.scheduling_revision if event is not None else None
                ),
                "event_profile_id": (
                    event.service_profile_id if event is not None else None
                ),
                "exact_target_ids": list(match.exact_target_ids),
            }
        )
    return serialized


def _evidence_for_digest(payload):
    return {
        "integration_key": payload["integration_key"],
        "adapter_contract_revision": payload["adapter_contract_revision"],
        "filename": payload["filename"],
        "workbook_sha256": payload["workbook_sha256"],
        "supported_sheet": payload["supported_sheet"],
        "columns": payload["columns"],
        "target_evidence": payload["target_evidence"],
        "offered_teams": payload["offered_teams"],
    }


def _evidence_digest(payload):
    encoded = json.dumps(
        _evidence_for_digest(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(encoded).hexdigest().upper()


def _sign_bounded(payload, *, salt):
    token = signing.dumps(payload, salt=salt, compress=True)
    if len(token.encode("utf-8")) > MAX_COLUMN_MAPPING_STATE_BYTES:
        raise TeamRosterColumnMappingStateError(
            "Signed column-mapping evidence exceeds its size bound."
        )
    return token


def _inventory_payload(inventory, *, user, teams):
    parsed_state = sign_parsed_workbook(inventory.parsed_workbook, user=user)
    payload = {
        "contract_version": TEAM_ROSTER_COLUMN_MAPPING_REVIEW_V1,
        "state_type": INVENTORY_STATE_TYPE,
        "integration_key": inventory.integration_key,
        "adapter_contract_revision": inventory.source_contract_revision,
        "generated_at": timezone.now().isoformat(),
        "user_id": user.pk,
        "filename": inventory.filename,
        "workbook_sha256": inventory.workbook_sha256,
        "supported_sheet": inventory.sheet_name,
        "parsed_workbook_state": parsed_state,
        "columns": _serialize_columns(inventory),
        "target_evidence": _serialize_target_matches(inventory.target_matches),
        "offered_teams": [
            {"team_id": team_id, "team_key": team_key}
            for team_id, team_key in _eligible_identities(teams)
        ],
    }
    payload["evidence_digest"] = _evidence_digest(payload)
    return payload


def _loads(token, *, user, max_age):
    try:
        payload = signing.loads(
            token,
            salt=INVENTORY_SIGNING_SALT,
            max_age=max_age,
        )
    except signing.BadSignature as exc:
        raise TeamRosterColumnMappingStateError(
            "Column-mapping review is invalid or expired."
        ) from exc
    if not isinstance(payload, dict):
        raise TeamRosterColumnMappingStateError("Column-mapping state is malformed.")
    required = {
        "contract_version",
        "state_type",
        "integration_key",
        "adapter_contract_revision",
        "generated_at",
        "user_id",
        "filename",
        "workbook_sha256",
        "supported_sheet",
        "parsed_workbook_state",
        "columns",
        "target_evidence",
        "offered_teams",
        "evidence_digest",
    }
    if (
        set(payload) != required
        or payload.get("contract_version") != TEAM_ROSTER_COLUMN_MAPPING_REVIEW_V1
        or payload.get("state_type") != INVENTORY_STATE_TYPE
        or payload.get("integration_key") != INTEGRATION_KEY
        or payload.get("adapter_contract_revision") != CONTRACT_REVISION
        or payload.get("user_id") != getattr(user, "pk", None)
        or not isinstance(payload.get("generated_at"), str)
        or not isinstance(payload.get("filename"), str)
        or payload["filename"].replace("\\", "/").rsplit("/", 1)[-1]
        != payload["filename"]
        or not isinstance(payload.get("workbook_sha256"), str)
        or _SHA256_RE.fullmatch(payload["workbook_sha256"]) is None
        or payload.get("supported_sheet") != SUPPORTED_SHEET
        or not isinstance(payload.get("parsed_workbook_state"), str)
        or payload.get("evidence_digest") != _evidence_digest(payload)
    ):
        raise TeamRosterColumnMappingStateError("Column-mapping state is malformed.")
    try:
        datetime.fromisoformat(payload["generated_at"])
    except ValueError as exc:
        raise TeamRosterColumnMappingStateError(
            "Column-mapping timestamp is malformed."
        ) from exc
    return payload


def _validate_columns(value):
    if not isinstance(value, list) or len(value) != len(_COLUMNS):
        raise TeamRosterColumnMappingStateError("Column evidence is malformed.")
    rows = []
    for expected_column, item in zip(_COLUMNS, value, strict=True):
        if not isinstance(item, dict) or set(item) != {
            "sheet",
            "column",
            "header",
            "scope",
            "hint_team_key",
        }:
            raise TeamRosterColumnMappingStateError("Column evidence is malformed.")
        if (
            item["sheet"] != SUPPORTED_SHEET
            or item["column"] != expected_column
            or not isinstance(item["header"], str)
            or len(item["header"]) > 255
            or item["scope"] != TEAM_ROSTER_COLUMN_SCOPE[expected_column].value
        ):
            raise TeamRosterColumnMappingStateError("Column evidence is malformed.")
        expected_hint = None
        if TEAM_ROSTER_COLUMN_SCOPE[expected_column] == (
            TeamRosterColumnScope.TARGET_PROFILE_REVIEW_CANDIDATE
        ):
            resolved = resolve_exact_team_roster_column_hint(
                item["header"], TEAM_ROSTER_COLUMN_HINTS
            )
            expected_hint = (
                resolved.destination_team_key if resolved is not None else None
            )
        if item["hint_team_key"] != expected_hint:
            raise TeamRosterColumnMappingStateError("Column hint evidence is stale.")
        rows.append(item)
    return tuple(rows)


def _validate_offered_teams(value):
    if not isinstance(value, list):
        raise TeamRosterColumnMappingStateError("Team option evidence is malformed.")
    identities = []
    for item in value:
        if (
            not isinstance(item, dict)
            or set(item) != {"team_id", "team_key"}
            or type(item["team_id"]) is not int
            or item["team_id"] <= 0
            or not _is_canonical_team_key(item["team_key"])
        ):
            raise TeamRosterColumnMappingStateError("Team option evidence is malformed.")
        identities.append((item["team_id"], item["team_key"]))
    if identities != sorted(identities) or len({item[0] for item in identities}) != len(
        identities
    ):
        raise TeamRosterColumnMappingStateError("Team option evidence is malformed.")
    return tuple(identities)


def _validate_target_evidence(value, parsed):
    if not isinstance(value, list) or len(value) != len(parsed.rows):
        raise TeamRosterColumnMappingStateError("Event-target evidence is malformed.")
    allowed_states = {state.value for state in TargetMatchState}
    for row, item in zip(parsed.rows, value, strict=True):
        if not isinstance(item, dict) or set(item) != {
            "source_row",
            "state",
            "event_id",
            "event_start",
            "event_status",
            "event_revision",
            "event_profile_id",
            "exact_target_ids",
        }:
            raise TeamRosterColumnMappingStateError("Event-target evidence is malformed.")
        exact_ids = item["exact_target_ids"]
        if (
            item["source_row"] != row.source_row
            or item["state"] not in allowed_states
            or (
                item["event_id"] is not None
                and (type(item["event_id"]) is not int or item["event_id"] <= 0)
            )
            or not isinstance(exact_ids, list)
            or any(type(value) is not int or value <= 0 for value in exact_ids)
            or len(set(exact_ids)) != len(exact_ids)
        ):
            raise TeamRosterColumnMappingStateError("Event-target evidence is malformed.")
    return tuple(value)


def _require_current_target_evidence(parsed, signed_evidence):
    current_matches = match_exact_service_event_targets(parsed)
    current = _serialize_target_matches(current_matches)
    if current != list(signed_evidence):
        raise TeamRosterColumnMappingStateError(
            "Exact ServiceProfile or ServiceEvent target evidence changed."
        )
    return current_matches


def _build_review(payload, *, parsed, teams, language, signed_state):
    columns = _validate_columns(payload["columns"])
    offered = _validate_offered_teams(payload["offered_teams"])
    target_evidence = _validate_target_evidence(payload["target_evidence"], parsed)
    rows = []
    for item in columns:
        prefill_team_id, hint_warning = _hint_resolution(
            item["hint_team_key"], teams, offered
        )
        rows.append(
            TeamRosterColumnReviewRow(
                sheet_name=item["sheet"],
                column=item["column"],
                observed_header=item["header"],
                scope=TeamRosterColumnScope(item["scope"]),
                hint_team_key=item["hint_team_key"],
                prefill_team_id=prefill_team_id,
                hint_warning=hint_warning,
            )
        )
    return TeamRosterColumnMappingReview(
        filename=payload["filename"],
        workbook_sha256=payload["workbook_sha256"],
        sheet_name=payload["supported_sheet"],
        columns=tuple(rows),
        destination_options=_destination_options(
            teams, offered_identities=offered, language=language
        ),
        target_evidence=tuple(
            TeamRosterTargetEvidence(
                source_row=item["source_row"],
                state=item["state"],
                event_id=item["event_id"],
                exact_target_ids=tuple(item["exact_target_ids"]),
            )
            for item in target_evidence
        ),
        signed_inventory_state=signed_state,
        signed_state_bytes=len(signed_state.encode("utf-8")),
        offered_team_identities=offered,
    )


def prepare_team_roster_column_mapping_review(*, content, filename, user, language="en"):
    inventory = inventory_team_roster_columns(content, filename=filename)
    teams = _all_teams()
    payload = _inventory_payload(inventory, user=user, teams=teams)
    signed_state = _sign_bounded(payload, salt=INVENTORY_SIGNING_SALT)
    parsed = decode_parsed_workbook(payload["parsed_workbook_state"], user=user)
    return _build_review(
        payload,
        parsed=parsed,
        teams=teams,
        language=language,
        signed_state=signed_state,
    )


def decode_team_roster_column_mapping_review(
    token, *, user, language="en", max_age=SIGNING_MAX_AGE_SECONDS
):
    payload = _loads(token, user=user, max_age=max_age)
    try:
        parsed = decode_parsed_workbook(
            payload["parsed_workbook_state"], user=user, max_age=max_age
        )
    except Exception as exc:
        raise TeamRosterColumnMappingStateError(
            "The signed workbook evidence is invalid, expired, or stale."
        ) from exc
    if (
        parsed.filename != payload["filename"]
        or parsed.sha256 != payload["workbook_sha256"]
    ):
        raise TeamRosterColumnMappingStateError(
            "Workbook identity evidence is inconsistent."
        )
    signed_evidence = _validate_target_evidence(payload["target_evidence"], parsed)
    _require_current_target_evidence(parsed, signed_evidence)
    teams = _all_teams()
    return _build_review(
        payload,
        parsed=parsed,
        teams=teams,
        language=language,
        signed_state=token,
    )


def _resolve_selected_teams(review, selected_team_ids):
    if set(selected_team_ids) != set(_CANDIDATE_COLUMNS):
        raise TeamRosterColumnMappingValidationError(
            "Submitted columns do not match the reviewed candidate columns."
        )
    selected_ids = [
        team_id for team_id in selected_team_ids.values() if team_id is not None
    ]
    if any(type(team_id) is not int or team_id <= 0 for team_id in selected_ids):
        raise TeamRosterColumnMappingValidationError(
            "Destination Team IDs are malformed."
        )
    if len(set(selected_ids)) != len(selected_ids):
        raise TeamRosterColumnMappingValidationError(
            "Each destination team may be selected by only one workbook column."
        )
    current = MinistryTeam.objects.in_bulk(selected_ids)
    offered = dict(review.offered_team_identities)
    resolved = {}
    for column, team_id in selected_team_ids.items():
        if team_id is None:
            resolved[column] = None
            continue
        team = current.get(team_id)
        if (
            team is None
            or not _eligible_team(team)
            or offered.get(team_id) != team.team_key
        ):
            raise TeamRosterColumnMappingValidationError(
                "A selected destination team is inactive, nonassignable, malformed, "
                "unknown, or has changed identity."
            )
        resolved[column] = team
    return resolved


def finalize_team_roster_column_mapping(
    *, review, selected_team_ids, user, language="en"
):
    if not user_can_review_team_roster_columns(user):
        raise TeamRosterColumnMappingValidationError(
            "Active staff or superuser access is required."
        )
    # Treat only the signed, freshly decoded inventory as authority.  The
    # dataclass passed by the view is rendering convenience, not a trust seam.
    review = decode_team_roster_column_mapping_review(
        review.signed_inventory_state,
        user=user,
        language=language,
    )
    if not review.target_gate_ready:
        raise TeamRosterColumnMappingTargetBlocked(
            "Exact ServiceProfile/ServiceEvent target evidence is blocked; "
            "next-stage authority was not minted."
        )
    resolved = _resolve_selected_teams(review, selected_team_ids)
    column_by_name = {row.column: row for row in review.columns}
    choices = []
    reviewed_payload = []
    for column in _CANDIDATE_COLUMNS:
        row = column_by_name[column]
        team = resolved[column]
        if team is None:
            choice = ReviewedTeamRosterColumnChoice(
                sheet_name=row.sheet_name,
                column=row.column,
                observed_header=row.observed_header,
                destination_team_id=None,
                destination_team_key=None,
                destination_display_name=None,
            )
        else:
            reviewed = ReviewedTeamRosterColumn(
                sheet_name=row.sheet_name,
                column=row.column,
                observed_header=row.observed_header,
                destination_team_id=team.pk,
                destination_team_key=team.team_key,
            )
            choice = ReviewedTeamRosterColumnChoice(
                sheet_name=reviewed.sheet_name,
                column=reviewed.column,
                observed_header=reviewed.observed_header,
                destination_team_id=reviewed.destination_team_id,
                destination_team_key=reviewed.destination_team_key,
                destination_display_name=_team_display_name(team, language),
            )
        choices.append(choice)
        reviewed_payload.append(
            {
                "sheet": choice.sheet_name,
                "column": choice.column,
                "header": choice.observed_header,
                "destination_team_id": choice.destination_team_id,
                "destination_team_key": choice.destination_team_key,
            }
        )

    inventory_payload = _loads(
        review.signed_inventory_state,
        user=user,
        max_age=SIGNING_MAX_AGE_SECONDS,
    )
    parsed = decode_parsed_workbook(inventory_payload["parsed_workbook_state"], user=user)
    signed_evidence = _validate_target_evidence(
        inventory_payload["target_evidence"], parsed
    )
    current_matches = _require_current_target_evidence(parsed, signed_evidence)
    if any(
        match.state != TargetMatchState.EXACT_TARGET_MATCHED
        for match in current_matches
    ):
        raise TeamRosterColumnMappingTargetBlocked(
            "Exact ServiceProfile/ServiceEvent target evidence is blocked; "
            "next-stage authority was not minted."
        )

    payload = {
        "contract_version": TEAM_ROSTER_REVIEWED_COLUMN_MAPPING_V1,
        "state_type": REVIEWED_STATE_TYPE,
        "integration_key": INTEGRATION_KEY,
        "adapter_contract_revision": CONTRACT_REVISION,
        "generated_at": timezone.now().isoformat(),
        "user_id": user.pk,
        "filename": review.filename,
        "workbook_sha256": review.workbook_sha256,
        "supported_sheet": review.sheet_name,
        "parsed_workbook_state": inventory_payload["parsed_workbook_state"],
        "columns": inventory_payload["columns"],
        "target_evidence": _serialize_target_matches(current_matches),
        "reviewed_mappings": reviewed_payload,
    }
    signed_reviewed_state = _sign_bounded(payload, salt=REVIEWED_SIGNING_SALT)
    return ReviewedTeamRosterColumnMapping(
        filename=review.filename,
        workbook_sha256=review.workbook_sha256,
        sheet_name=review.sheet_name,
        choices=tuple(choices),
        signed_reviewed_state=signed_reviewed_state,
        signed_state_bytes=len(signed_reviewed_state.encode("utf-8")),
    )
