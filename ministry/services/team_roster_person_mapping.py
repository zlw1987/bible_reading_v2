"""ZERO-WRITE person review for mapped annual Team Roster workbook columns.

GENERAL.1D requires the uploader to present the exact same workbook again.  A
strictly decoded GENERAL.1C token remains the authority for column/team choices;
the upload supplies only the mapped roster cells whose SHA-256 matches that
authority.  This module never reads assignment tables and never writes data.
"""

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from hashlib import sha256
import re
import unicodedata

from django.core import signing
from django.utils import timezone

from core.integration_registry import require_integration_enabled
from events.models import ServiceEvent
from events.service_profile_readiness import service_event_audience_readiness
from ministry.integrations.svca_bethany_2026_worship_xlsx.team_roster_sources import (
    read_reviewed_team_roster_cells,
)
from ministry.models import MinistryTeam, TeamMembership
from ministry.services.team_roster_column_mapping import (
    TEAM_ROSTER_REVIEWED_COLUMN_MAPPING_V1,
    ReviewedTeamRosterColumnChoice,
    TeamRosterColumnMappingStateError,
    decode_reviewed_team_roster_column_mapping,
    user_can_review_team_roster_columns,
)
from ministry.services.team_roster_workbook import (
    MAX_PERSON_TOKEN_LENGTH,
    MAX_ROSTER_MEMBERS_PER_CELL,
    MAX_SOURCE_LITERAL_LENGTH,
    ReviewedTeamRosterColumn,
    TEAM_ROSTER_CELL_V1,
    TeamRosterCellState,
    parse_team_roster_cell,
)
from ministry.services.worship_xlsx_preview import (
    CONTRACT_REVISION,
    INTEGRATION_KEY,
    SIGNING_MAX_AGE_SECONDS,
    SUPPORTED_ROWS,
    SUPPORTED_SHEET,
)


TEAM_ROSTER_PERSON_MAPPING_INPUT_V1 = "TEAM_ROSTER_PERSON_MAPPING_INPUT_V1"
TEAM_ROSTER_PERSON_MAPPING_REVIEW_V1 = "TEAM_ROSTER_PERSON_MAPPING_REVIEW_V1"
PERSON_INPUT_STATE_TYPE = "team_roster_person_mapping_input"
PERSON_REVIEWED_STATE_TYPE = "team_roster_reviewed_person_mapping"
PERSON_INPUT_SIGNING_SALT = "ministry.team_roster.person_mapping.input.v1"
PERSON_REVIEWED_SIGNING_SALT = "ministry.team_roster.person_mapping.reviewed.v1"
MAX_PERSON_MAPPING_STATE_BYTES = 16_384

_SHA256_RE = re.compile(r"^[0-9A-F]{64}$")


class TeamRosterPersonMappingStateError(ValueError):
    pass


class TeamRosterWorkbookMismatch(TeamRosterPersonMappingStateError):
    pass


class TeamRosterPersonMappingValidationError(ValueError):
    pass


class TeamRosterPersonMappingStateTooLarge(TeamRosterPersonMappingStateError):
    def __init__(self, actual_bytes):
        self.actual_bytes = actual_bytes
        self.maximum_bytes = MAX_PERSON_MAPPING_STATE_BYTES
        super().__init__(
            f"Signed person-mapping evidence is {actual_bytes} bytes; the "
            f"existing {MAX_PERSON_MAPPING_STATE_BYTES}-byte bound was not raised."
        )


@dataclass(frozen=True, slots=True)
class TeamRosterMembershipCandidate:
    membership_id: int
    visible_identity: str
    visible_identity_digest: str
    linked_user_id: int | None
    linked_user_active: bool | None
    membership_updated_at: str

    @property
    def linked_state(self):
        return "linked" if self.linked_user_id is not None else "display_name_only"

    @property
    def usable(self):
        return self.linked_user_id is None or self.linked_user_active is True


@dataclass(frozen=True, slots=True)
class TeamRosterMappedCellEvidence:
    source_row: int
    source_cell: str
    local_date: date
    event_id: int
    sheet_name: str
    column: str
    observed_header: str
    destination_team_id: int
    destination_team_key: str
    parsed_state: TeamRosterCellState
    normalized_tokens: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TeamRosterTokenReview:
    token: str
    occurrence_count: int
    source_cells: tuple[str, ...]
    exact_match_ids: tuple[int, ...]
    prefill_membership_id: int | None
    review_state: str


@dataclass(frozen=True, slots=True)
class TeamRosterPersonMappingGroup:
    team_id: int
    team_key: str
    team_display_name: str
    candidates: tuple[TeamRosterMembershipCandidate, ...]
    diagnostic_inactive_user_count: int
    token_reviews: tuple[TeamRosterTokenReview, ...]


@dataclass(frozen=True, slots=True)
class TeamRosterPersonMappingInputReview:
    filename: str
    workbook_sha256: str
    mapped_columns: tuple[ReviewedTeamRosterColumnChoice, ...]
    cells: tuple[TeamRosterMappedCellEvidence, ...]
    groups: tuple[TeamRosterPersonMappingGroup, ...]
    signed_reviewed_column_state: str
    signed_input_state: str
    signed_state_bytes: int

    @property
    def mapped_count(self):
        return len(self.mapped_columns)

    @property
    def distinct_token_count(self):
        return sum(len(group.token_reviews) for group in self.groups)

    @property
    def source_blocker_count(self):
        safe = {
            TeamRosterCellState.NO_SOURCE_PROPOSAL,
            TeamRosterCellState.SUPPORTED_LITERAL,
        }
        return sum(cell.parsed_state not in safe for cell in self.cells)


@dataclass(frozen=True, slots=True)
class ReviewedTeamRosterPersonMapping:
    filename: str
    workbook_sha256: str
    mapped_column_count: int
    reviewed_token_count: int
    signed_reviewed_state: str
    signed_state_bytes: int


def normalize_team_roster_visible_identity(value):
    if not isinstance(value, str):
        raise TeamRosterPersonMappingStateError("Visible membership identity is invalid.")
    return unicodedata.normalize("NFC", value).strip()


def _identity_digest(value):
    return sha256(
        normalize_team_roster_visible_identity(value).encode("utf-8")
    ).hexdigest().upper()


def _privacy_safe_visible_identity(membership):
    if membership.display_name:
        value = membership.display_name
    elif membership.user_id:
        value = membership.user.get_full_name() or membership.user.get_username()
    else:
        raise TeamRosterPersonMappingStateError(
            "An active Team Membership has no privacy-safe visible identity."
        )
    value = normalize_team_roster_visible_identity(value)
    if not value:
        raise TeamRosterPersonMappingStateError(
            "An active Team Membership has no privacy-safe visible identity."
        )
    return value


def _candidate(membership):
    visible = _privacy_safe_visible_identity(membership)
    return TeamRosterMembershipCandidate(
        membership_id=membership.pk,
        visible_identity=visible,
        visible_identity_digest=_identity_digest(visible),
        linked_user_id=membership.user_id,
        linked_user_active=(membership.user.is_active if membership.user_id else None),
        membership_updated_at=membership.updated_at.isoformat(),
    )


def _candidate_payload(candidate):
    return {
        "membership_id": candidate.membership_id,
        "visible_identity": candidate.visible_identity,
        "visible_identity_digest": candidate.visible_identity_digest,
        "linked_user_id": candidate.linked_user_id,
        "linked_user_active": candidate.linked_user_active,
        "membership_updated_at": candidate.membership_updated_at,
        "usable": candidate.usable,
    }


def _team_payload(team):
    return {
        "team_id": team.pk,
        "team_key": team.team_key,
        "active": team.is_active,
        "assignable": team.is_assignable,
    }


def _event_payload(event):
    audience = service_event_audience_readiness(event)
    return {
        "event_id": event.pk,
        "service_profile_id": event.service_profile_id,
        "service_profile_key": event.service_profile.key,
        "service_profile_active": event.service_profile.is_active,
        "service_profile_event_type": event.service_profile.event_type,
        "event_type": event.event_type,
        "start_datetime": event.start_datetime.isoformat(),
        "status": event.status,
        "scheduling_revision": event.scheduling_revision,
        "audience": {
            "ready": audience["ready"],
            "invalid_reasons": audience["invalid_reasons"],
            "units": [
                {"id": unit["id"], "is_active": unit["is_active"]}
                for unit in audience["units"]
            ],
        },
    }


def _mapping_payload(choice):
    return {
        "sheet": choice.sheet_name,
        "column": choice.column,
        "header": choice.observed_header,
        "destination_team_id": choice.destination_team_id,
        "destination_team_key": choice.destination_team_key,
    }


def _cell_payload(cell):
    return {
        "source_row": cell.source_row,
        "source_cell": cell.source_cell,
        "local_date": cell.local_date.isoformat(),
        "event_id": cell.event_id,
        "sheet": cell.sheet_name,
        "column": cell.column,
        "header": cell.observed_header,
        "destination_team_id": cell.destination_team_id,
        "destination_team_key": cell.destination_team_key,
        "parsed_state": cell.parsed_state.value,
        "normalized_tokens": list(cell.normalized_tokens),
    }


def _sign_bounded(payload, *, salt):
    token = signing.dumps(payload, salt=salt, compress=True)
    actual = len(token.encode("utf-8"))
    if actual > MAX_PERSON_MAPPING_STATE_BYTES:
        raise TeamRosterPersonMappingStateTooLarge(actual)
    return token


def _safe_filename(value):
    if not isinstance(value, str):
        return None
    return value.replace("\\", "/").rsplit("/", 1)[-1]


def _current_candidates_by_team(team_ids):
    grouped = defaultdict(list)
    queryset = (
        TeamMembership.objects.filter(team_id__in=team_ids, is_active=True)
        .select_related("user")
        .order_by("team_id", "id")
    )
    for membership in queryset:
        grouped[membership.team_id].append(_candidate(membership))
    return {team_id: tuple(grouped[team_id]) for team_id in team_ids}


def _team_display_name(team, language):
    primary = team.get_name(language)
    secondary = team.name_en if language == "zh" else team.name
    return f"{primary} / {secondary}" if secondary and secondary != primary else primary


def _build_groups(*, mapped_columns, teams, candidates_by_team, cells, language):
    cells_by_team = defaultdict(list)
    for cell in cells:
        cells_by_team[cell.destination_team_id].append(cell)
    groups = []
    for choice in mapped_columns:
        team = teams[choice.destination_team_id]
        candidates = candidates_by_team[team.pk]
        usable = tuple(item for item in candidates if item.usable)
        tokens = []
        occurrences = Counter()
        source_cells = defaultdict(list)
        for cell in cells_by_team[team.pk]:
            if cell.parsed_state != TeamRosterCellState.SUPPORTED_LITERAL:
                continue
            for token in cell.normalized_tokens:
                occurrences[token] += 1
                source_cells[token].append(cell.source_cell)
                if token not in tokens:
                    tokens.append(token)
        reviews = []
        for token in tokens:
            exact_ids = tuple(
                item.membership_id
                for item in usable
                if normalize_team_roster_visible_identity(item.visible_identity) == token
            )
            if len(exact_ids) == 1:
                state = "exact_prefill_available"
                prefill = exact_ids[0]
            elif len(exact_ids) > 1:
                state = "ambiguous_manual_review_required"
                prefill = None
            else:
                state = "manual_review_required"
                prefill = None
            reviews.append(
                TeamRosterTokenReview(
                    token=token,
                    occurrence_count=occurrences[token],
                    source_cells=tuple(source_cells[token]),
                    exact_match_ids=exact_ids,
                    prefill_membership_id=prefill,
                    review_state=state,
                )
            )
        groups.append(
            TeamRosterPersonMappingGroup(
                team_id=team.pk,
                team_key=team.team_key,
                team_display_name=_team_display_name(team, language),
                candidates=usable,
                diagnostic_inactive_user_count=sum(not item.usable for item in candidates),
                token_reviews=tuple(reviews),
            )
        )
    return tuple(groups)


def _event_baselines(decoded):
    event_ids = [item.event_id for item in decoded.target_evidence]
    if any(type(value) is not int or value <= 0 for value in event_ids):
        raise TeamRosterPersonMappingStateError("Target event evidence is incomplete.")
    events = (
        ServiceEvent.objects.select_related("service_profile")
        .prefetch_related("audience_scope_links__unit")
        .in_bulk(event_ids)
    )
    if len(events) != len(event_ids):
        raise TeamRosterPersonMappingStateError("Target event evidence changed.")
    return tuple(_event_payload(events[event_id]) for event_id in event_ids)


def _require_actor_and_integration(user):
    require_integration_enabled(INTEGRATION_KEY)
    if not user_can_review_team_roster_columns(user):
        raise TeamRosterPersonMappingValidationError(
            "Active staff or superuser access is required."
        )


def _decode_reviewed_columns(token, *, user, language, max_age=SIGNING_MAX_AGE_SECONDS):
    try:
        return decode_reviewed_team_roster_column_mapping(
            token, user=user, language=language, max_age=max_age
        )
    except TeamRosterColumnMappingStateError as exc:
        raise TeamRosterPersonMappingStateError(
            "Reviewed column authority is invalid, expired, or stale."
        ) from exc


def prepare_team_roster_person_mapping(
    *, content, filename, reviewed_column_state, user, language="en"
):
    """Verify same-workbook continuity, parse mapped cells, and offer candidates."""

    _require_actor_and_integration(user)
    decoded = _decode_reviewed_columns(
        reviewed_column_state, user=user, language=language
    )
    uploaded_sha = sha256(content).hexdigest().upper()
    if uploaded_sha != decoded.workbook_sha256:
        raise TeamRosterWorkbookMismatch(
            "The re-uploaded workbook is not the exact workbook reviewed earlier."
        )

    mapped_columns = tuple(choice for choice in decoded.choices if not choice.is_ignored)
    adapter_columns = tuple(
        ReviewedTeamRosterColumn(
            sheet_name=choice.sheet_name,
            column=choice.column,
            observed_header=choice.observed_header,
            destination_team_id=choice.destination_team_id,
            destination_team_key=choice.destination_team_key,
        )
        for choice in mapped_columns
    )
    extracted = read_reviewed_team_roster_cells(
        content,
        parsed_workbook=decoded.parsed_workbook,
        mapped_columns=adapter_columns,
    )
    target_by_row = {item.source_row: item.event_id for item in decoded.target_evidence}
    cells = []
    for source in extracted:
        parsed = parse_team_roster_cell(source.cell_input)
        event_id = target_by_row.get(source.source_row)
        if type(event_id) is not int or event_id <= 0:
            raise TeamRosterPersonMappingStateError("Target event evidence changed.")
        cells.append(
            TeamRosterMappedCellEvidence(
                source_row=source.source_row,
                source_cell=source.source_cell,
                local_date=source.local_date,
                event_id=event_id,
                sheet_name=source.sheet_name,
                column=source.column,
                observed_header=source.observed_header,
                destination_team_id=source.destination_team_id,
                destination_team_key=source.destination_team_key,
                parsed_state=parsed.state,
                normalized_tokens=parsed.person_tokens,
            )
        )

    team_ids = tuple(choice.destination_team_id for choice in mapped_columns)
    teams = MinistryTeam.objects.in_bulk(team_ids)
    if len(teams) != len(team_ids):
        raise TeamRosterPersonMappingStateError("A mapped destination team changed.")
    candidates_by_team = _current_candidates_by_team(team_ids)
    groups = _build_groups(
        mapped_columns=mapped_columns,
        teams=teams,
        candidates_by_team=candidates_by_team,
        cells=tuple(cells),
        language=language,
    )
    event_baselines = _event_baselines(decoded)
    team_evidence = [
        {
            **_team_payload(teams[team_id]),
            "candidates": [
                _candidate_payload(item) for item in candidates_by_team[team_id]
            ],
        }
        for team_id in team_ids
    ]
    payload = {
        "contract_version": TEAM_ROSTER_PERSON_MAPPING_INPUT_V1,
        "state_type": PERSON_INPUT_STATE_TYPE,
        "reviewed_column_contract_version": TEAM_ROSTER_REVIEWED_COLUMN_MAPPING_V1,
        "reviewed_column_state_sha256": sha256(
            reviewed_column_state.encode("utf-8")
        ).hexdigest().upper(),
        "integration_key": INTEGRATION_KEY,
        "adapter_contract_revision": CONTRACT_REVISION,
        "cell_contract_revision": TEAM_ROSTER_CELL_V1,
        "generated_at": timezone.now().isoformat(),
        "user_id": user.pk,
        "filename": decoded.filename,
        "workbook_sha256": decoded.workbook_sha256,
        "supported_sheet": SUPPORTED_SHEET,
        "mapped_columns": [_mapping_payload(item) for item in mapped_columns],
        "source_cells": [_cell_payload(item) for item in cells],
        "team_candidates": team_evidence,
        "target_events": list(event_baselines),
    }
    signed = _sign_bounded(payload, salt=PERSON_INPUT_SIGNING_SALT)
    return TeamRosterPersonMappingInputReview(
        filename=decoded.filename,
        workbook_sha256=decoded.workbook_sha256,
        mapped_columns=mapped_columns,
        cells=tuple(cells),
        groups=groups,
        signed_reviewed_column_state=reviewed_column_state,
        signed_input_state=signed,
        signed_state_bytes=len(signed.encode("utf-8")),
    )


def _loads(token, *, salt, max_age, expected_version, expected_type, user):
    try:
        payload = signing.loads(token, salt=salt, max_age=max_age)
    except signing.BadSignature as exc:
        raise TeamRosterPersonMappingStateError(
            "Person-mapping evidence is invalid or expired."
        ) from exc
    if (
        not isinstance(payload, dict)
        or payload.get("contract_version") != expected_version
        or payload.get("state_type") != expected_type
        or payload.get("integration_key") != INTEGRATION_KEY
        or payload.get("adapter_contract_revision") != CONTRACT_REVISION
        or payload.get("cell_contract_revision") != TEAM_ROSTER_CELL_V1
        or payload.get("user_id") != getattr(user, "pk", None)
    ):
        raise TeamRosterPersonMappingStateError(
            "Person-mapping evidence is malformed or belongs to another user."
        )
    return payload


def _validate_common_payload(payload, *, expected_keys, user, language):
    if (
        set(payload) != expected_keys
        or payload.get("reviewed_column_contract_version")
        != TEAM_ROSTER_REVIEWED_COLUMN_MAPPING_V1
        or not isinstance(payload.get("generated_at"), str)
        or _safe_filename(payload.get("filename")) != payload.get("filename")
        or not isinstance(payload.get("workbook_sha256"), str)
        or _SHA256_RE.fullmatch(payload["workbook_sha256"]) is None
        or payload.get("supported_sheet") != SUPPORTED_SHEET
    ):
        raise TeamRosterPersonMappingStateError("Person-mapping evidence is malformed.")
    try:
        datetime.fromisoformat(payload["generated_at"])
    except ValueError as exc:
        raise TeamRosterPersonMappingStateError(
            "Person-mapping timestamp is malformed."
        ) from exc

    mappings = payload.get("mapped_columns")
    if not isinstance(mappings, list) or len(mappings) > 7:
        raise TeamRosterPersonMappingStateError("Mapped-column evidence is malformed.")
    choices = []
    seen_columns = set()
    seen_teams = set()
    for item in mappings:
        if (
            not isinstance(item, dict)
            or set(item)
            != {
                "sheet",
                "column",
                "header",
                "destination_team_id",
                "destination_team_key",
            }
            or item["sheet"] != SUPPORTED_SHEET
            or item["column"] not in "CDEFGHI"
            or item["column"] in seen_columns
            or not isinstance(item["header"], str)
            or len(item["header"]) > 255
            or type(item["destination_team_id"]) is not int
            or item["destination_team_id"] <= 0
            or not isinstance(item["destination_team_key"], str)
            or not item["destination_team_key"]
            or item["destination_team_id"] in seen_teams
        ):
            raise TeamRosterPersonMappingStateError("Mapped-column evidence is malformed.")
        seen_columns.add(item["column"])
        seen_teams.add(item["destination_team_id"])
        choices.append(
            ReviewedTeamRosterColumnChoice(
                sheet_name=item["sheet"],
                column=item["column"],
                observed_header=item["header"],
                destination_team_id=item["destination_team_id"],
                destination_team_key=item["destination_team_key"],
                destination_display_name=None,
            )
        )
    if [item.column for item in choices] != sorted(
        (item.column for item in choices), key="CDEFGHI".index
    ):
        raise TeamRosterPersonMappingStateError("Mapped-column evidence is malformed.")

    team_ids = tuple(item.destination_team_id for item in choices)
    teams = MinistryTeam.objects.in_bulk(team_ids)
    if len(teams) != len(team_ids):
        raise TeamRosterPersonMappingStateError("A mapped destination team changed.")
    for choice in choices:
        team = teams[choice.destination_team_id]
        if (
            team.team_key != choice.destination_team_key
            or not team.is_active
            or not team.is_assignable
        ):
            raise TeamRosterPersonMappingStateError("A mapped destination team changed.")
    choices = tuple(
        ReviewedTeamRosterColumnChoice(
            sheet_name=choice.sheet_name,
            column=choice.column,
            observed_header=choice.observed_header,
            destination_team_id=choice.destination_team_id,
            destination_team_key=choice.destination_team_key,
            destination_display_name=_team_display_name(
                teams[choice.destination_team_id], language
            ),
        )
        for choice in choices
    )

    team_candidates = payload.get("team_candidates")
    if not isinstance(team_candidates, list) or len(team_candidates) != len(team_ids):
        raise TeamRosterPersonMappingStateError("Membership candidate evidence is malformed.")
    current_candidates = _current_candidates_by_team(team_ids)
    for team_id, item in zip(team_ids, team_candidates, strict=True):
        if (
            not isinstance(item, dict)
            or set(item)
            != {"team_id", "team_key", "active", "assignable", "candidates"}
            or item != {
                **_team_payload(teams[team_id]),
                "candidates": [
                    _candidate_payload(candidate)
                    for candidate in current_candidates[team_id]
                ],
            }
        ):
            raise TeamRosterPersonMappingStateError(
                "Membership identity/activity evidence changed."
            )

    target_events = payload.get("target_events")
    if not isinstance(target_events, list) or len(target_events) != len(SUPPORTED_ROWS):
        raise TeamRosterPersonMappingStateError("Target-event evidence is malformed.")
    event_ids = []
    for item in target_events:
        if (
            not isinstance(item, dict)
            or set(item)
            != {
                "event_id",
                "service_profile_id",
                "service_profile_key",
                "service_profile_active",
                "service_profile_event_type",
                "event_type",
                "start_datetime",
                "status",
                "scheduling_revision",
                "audience",
            }
            or type(item["event_id"]) is not int
            or item["event_id"] <= 0
        ):
            raise TeamRosterPersonMappingStateError("Target-event evidence is malformed.")
        event_ids.append(item["event_id"])
    if len(event_ids) != len(set(event_ids)):
        raise TeamRosterPersonMappingStateError("Target-event evidence is malformed.")
    events = (
        ServiceEvent.objects.select_related("service_profile")
        .prefetch_related("audience_scope_links__unit")
        .in_bulk(event_ids)
    )
    if len(events) != len(event_ids) or target_events != [
        _event_payload(events[event_id]) for event_id in event_ids
    ]:
        raise TeamRosterPersonMappingStateError("Target-event evidence changed.")

    source_cells = payload.get("source_cells")
    expected_count = len(SUPPORTED_ROWS) * len(choices)
    if not isinstance(source_cells, list) or len(source_cells) != expected_count:
        raise TeamRosterPersonMappingStateError("Mapped source-cell evidence is malformed.")
    expected_pairs = [
        (source_row, choice)
        for source_row in SUPPORTED_ROWS
        for choice in choices
    ]
    cells = []
    event_id_by_row = dict(zip(SUPPORTED_ROWS, event_ids, strict=True))
    parsed_rows_by_number = {}
    for source_row, item in zip(expected_pairs, source_cells, strict=True):
        row_number, choice = source_row
        if not isinstance(item, dict) or set(item) != {
            "source_row",
            "source_cell",
            "local_date",
            "event_id",
            "sheet",
            "column",
            "header",
            "destination_team_id",
            "destination_team_key",
            "parsed_state",
            "normalized_tokens",
        }:
            raise TeamRosterPersonMappingStateError("Mapped source-cell evidence is malformed.")
        try:
            local_date = date.fromisoformat(item["local_date"])
            state = TeamRosterCellState(item["parsed_state"])
        except (TypeError, ValueError) as exc:
            raise TeamRosterPersonMappingStateError(
                "Mapped source-cell evidence is malformed."
            ) from exc
        tokens = item["normalized_tokens"]
        tokens_are_bounded = (
            isinstance(tokens, list)
            and len(tokens) <= MAX_SOURCE_LITERAL_LENGTH + 1
            and all(
                isinstance(token, str)
                and token == normalize_team_roster_visible_identity(token)
                and len(token) <= MAX_SOURCE_LITERAL_LENGTH
                for token in tokens
            )
        )
        state_shape_is_valid = False
        if tokens_are_bounded:
            if state == TeamRosterCellState.SUPPORTED_LITERAL:
                state_shape_is_valid = (
                    1 <= len(tokens) <= MAX_ROSTER_MEMBERS_PER_CELL
                    and all(tokens)
                    and len(tokens) == len(set(tokens))
                    and all(len(token) <= MAX_PERSON_TOKEN_LENGTH for token in tokens)
                )
            elif state in {
                TeamRosterCellState.NO_SOURCE_PROPOSAL,
                TeamRosterCellState.FORMULA_BLOCKED,
                TeamRosterCellState.ERROR_BLOCKED,
                TeamRosterCellState.NON_TEXT_BLOCKED,
                TeamRosterCellState.SOURCE_LITERAL_TOO_LONG,
            }:
                state_shape_is_valid = not tokens
            elif state == TeamRosterCellState.TOO_MANY_MEMBERS:
                state_shape_is_valid = (
                    len(tokens) > MAX_ROSTER_MEMBERS_PER_CELL and all(tokens)
                )
            elif state == TeamRosterCellState.TOKEN_TOO_LONG:
                state_shape_is_valid = (
                    1 <= len(tokens) <= MAX_ROSTER_MEMBERS_PER_CELL
                    and all(tokens)
                    and any(len(token) > MAX_PERSON_TOKEN_LENGTH for token in tokens)
                )
            elif state == TeamRosterCellState.EMPTY_SEGMENT:
                state_shape_is_valid = bool(tokens) and any(not token for token in tokens)
            elif state == TeamRosterCellState.DUPLICATE_TOKEN:
                state_shape_is_valid = (
                    1 <= len(tokens) <= MAX_ROSTER_MEMBERS_PER_CELL
                    and all(tokens)
                    and len(tokens) != len(set(tokens))
                )
            elif state == TeamRosterCellState.UNSUPPORTED_SYNTAX:
                state_shape_is_valid = True
        if (
            item["source_row"] != row_number
            or item["source_cell"] != f"{choice.column}{row_number}"
            or item["event_id"] != event_id_by_row[row_number]
            or item["sheet"] != choice.sheet_name
            or item["column"] != choice.column
            or item["header"] != choice.observed_header
            or item["destination_team_id"] != choice.destination_team_id
            or item["destination_team_key"] != choice.destination_team_key
            or not state_shape_is_valid
        ):
            raise TeamRosterPersonMappingStateError("Mapped source-cell evidence is malformed.")
        parsed_rows_by_number.setdefault(row_number, local_date)
        if parsed_rows_by_number[row_number] != local_date:
            raise TeamRosterPersonMappingStateError("Mapped source-cell evidence is malformed.")
        cells.append(
            TeamRosterMappedCellEvidence(
                source_row=row_number,
                source_cell=item["source_cell"],
                local_date=local_date,
                event_id=item["event_id"],
                sheet_name=item["sheet"],
                column=item["column"],
                observed_header=item["header"],
                destination_team_id=item["destination_team_id"],
                destination_team_key=item["destination_team_key"],
                parsed_state=state,
                normalized_tokens=tuple(tokens),
            )
        )
        if timezone.localtime(events[item["event_id"]].start_datetime).date() != local_date:
            raise TeamRosterPersonMappingStateError("Mapped source-cell evidence is malformed.")
    groups = _build_groups(
        mapped_columns=tuple(choices),
        teams=teams,
        candidates_by_team=current_candidates,
        cells=tuple(cells),
        language=language,
    )
    return tuple(choices), tuple(cells), groups, teams, current_candidates


_INPUT_KEYS = {
    "contract_version",
    "state_type",
    "reviewed_column_contract_version",
    "reviewed_column_state_sha256",
    "integration_key",
    "adapter_contract_revision",
    "cell_contract_revision",
    "generated_at",
    "user_id",
    "filename",
    "workbook_sha256",
    "supported_sheet",
    "mapped_columns",
    "source_cells",
    "team_candidates",
    "target_events",
}


def decode_team_roster_person_mapping_input(
    token,
    *,
    reviewed_column_state,
    user,
    language="en",
    max_age=SIGNING_MAX_AGE_SECONDS,
):
    _require_actor_and_integration(user)
    payload = _loads(
        token,
        salt=PERSON_INPUT_SIGNING_SALT,
        max_age=max_age,
        expected_version=TEAM_ROSTER_PERSON_MAPPING_INPUT_V1,
        expected_type=PERSON_INPUT_STATE_TYPE,
        user=user,
    )
    if payload.get("reviewed_column_state_sha256") != sha256(
        reviewed_column_state.encode("utf-8")
    ).hexdigest().upper():
        raise TeamRosterPersonMappingStateError(
            "Reviewed column authority does not match person-mapping evidence."
        )
    decoded_columns = _decode_reviewed_columns(
        reviewed_column_state,
        user=user,
        language=language,
        max_age=max_age,
    )
    choices, cells, groups, _teams, _candidates = _validate_common_payload(
        payload, expected_keys=_INPUT_KEYS, user=user, language=language
    )
    expected_mappings = tuple(
        item for item in decoded_columns.choices if not item.is_ignored
    )
    if (
        payload["filename"] != decoded_columns.filename
        or payload["workbook_sha256"] != decoded_columns.workbook_sha256
        or tuple(_mapping_payload(item) for item in choices)
        != tuple(_mapping_payload(item) for item in expected_mappings)
    ):
        raise TeamRosterPersonMappingStateError(
            "Reviewed column authority changed. Re-upload the workbook."
        )
    return TeamRosterPersonMappingInputReview(
        filename=payload["filename"],
        workbook_sha256=payload["workbook_sha256"],
        mapped_columns=choices,
        cells=cells,
        groups=groups,
        signed_reviewed_column_state=reviewed_column_state,
        signed_input_state=token,
        signed_state_bytes=len(token.encode("utf-8")),
    )


def finalize_team_roster_person_mapping(
    *,
    input_state,
    reviewed_column_state,
    selected_membership_ids,
    user,
    language="en",
):
    _require_actor_and_integration(user)
    review = decode_team_roster_person_mapping_input(
        input_state,
        reviewed_column_state=reviewed_column_state,
        user=user,
        language=language,
    )
    expected_pairs = {
        (group.team_id, token_review.token)
        for group in review.groups
        for token_review in group.token_reviews
    }
    if set(selected_membership_ids) != expected_pairs:
        raise TeamRosterPersonMappingValidationError(
            "Submitted person mappings do not match the reviewed team/token pairs."
        )
    group_by_team = {group.team_id: group for group in review.groups}
    selections = {}
    selection_payload = []
    for team_id, token in sorted(
        expected_pairs, key=lambda item: (item[0], item[1])
    ):
        membership_id = selected_membership_ids[(team_id, token)]
        if type(membership_id) is not int or membership_id <= 0:
            raise TeamRosterPersonMappingValidationError(
                "Every source person requires an explicit Team Membership review."
            )
        candidate_by_id = {
            item.membership_id: item
            for item in group_by_team[team_id].candidates
            if item.usable
        }
        candidate = candidate_by_id.get(membership_id)
        if candidate is None:
            raise TeamRosterPersonMappingValidationError(
                "A selected membership is inactive, belongs to another team, or has an inactive linked user."
            )
        selections[(team_id, token)] = candidate
        selection_payload.append(
            {
                "destination_team_id": team_id,
                "destination_team_key": group_by_team[team_id].team_key,
                "source_token": token,
                "membership_id": membership_id,
            }
        )

    for cell in review.cells:
        if cell.parsed_state != TeamRosterCellState.SUPPORTED_LITERAL:
            continue
        membership_ids = [
            selections[(cell.destination_team_id, token)].membership_id
            for token in cell.normalized_tokens
        ]
        if len(membership_ids) != len(set(membership_ids)):
            raise TeamRosterPersonMappingValidationError(
                "Two source people in one destination team/date roster cannot map to the same membership."
            )

    input_payload = signing.loads(input_state, salt=PERSON_INPUT_SIGNING_SALT)
    payload = {
        **{
            key: input_payload[key]
            for key in _INPUT_KEYS
            if key
            not in {
                "contract_version",
                "state_type",
                "generated_at",
                "reviewed_column_state_sha256",
            }
        },
        "contract_version": TEAM_ROSTER_PERSON_MAPPING_REVIEW_V1,
        "state_type": PERSON_REVIEWED_STATE_TYPE,
        "reviewed_column_contract_version": TEAM_ROSTER_REVIEWED_COLUMN_MAPPING_V1,
        "reviewed_column_state_sha256": input_payload[
            "reviewed_column_state_sha256"
        ],
        "generated_at": timezone.now().isoformat(),
        "reviewed_selections": selection_payload,
    }
    signed = _sign_bounded(payload, salt=PERSON_REVIEWED_SIGNING_SALT)
    return ReviewedTeamRosterPersonMapping(
        filename=review.filename,
        workbook_sha256=review.workbook_sha256,
        mapped_column_count=review.mapped_count,
        reviewed_token_count=len(selection_payload),
        signed_reviewed_state=signed,
        signed_state_bytes=len(signed.encode("utf-8")),
    )


_REVIEWED_KEYS = (_INPUT_KEYS - {"contract_version", "state_type"}) | {
    "contract_version",
    "state_type",
    "reviewed_selections",
}


def decode_reviewed_team_roster_person_mapping(
    token, *, user, language="en", max_age=SIGNING_MAX_AGE_SECONDS
):
    """Revalidate final zero-write person authority against current truth."""

    _require_actor_and_integration(user)
    payload = _loads(
        token,
        salt=PERSON_REVIEWED_SIGNING_SALT,
        max_age=max_age,
        expected_version=TEAM_ROSTER_PERSON_MAPPING_REVIEW_V1,
        expected_type=PERSON_REVIEWED_STATE_TYPE,
        user=user,
    )
    choices, cells, groups, _teams, _candidates = _validate_common_payload(
        payload, expected_keys=_REVIEWED_KEYS, user=user, language=language
    )
    selections = payload.get("reviewed_selections")
    expected_pairs = {
        (group.team_id, review.token)
        for group in groups
        for review in group.token_reviews
    }
    if not isinstance(selections, list) or len(selections) != len(expected_pairs):
        raise TeamRosterPersonMappingStateError("Reviewed person mappings are malformed.")
    group_by_team = {group.team_id: group for group in groups}
    resolved = {}
    for item in selections:
        if not isinstance(item, dict) or set(item) != {
            "destination_team_id",
            "destination_team_key",
            "source_token",
            "membership_id",
        }:
            raise TeamRosterPersonMappingStateError("Reviewed person mappings are malformed.")
        pair = (item["destination_team_id"], item["source_token"])
        group = group_by_team.get(item["destination_team_id"])
        if (
            pair not in expected_pairs
            or pair in resolved
            or group is None
            or item["destination_team_key"] != group.team_key
            or type(item["membership_id"]) is not int
        ):
            raise TeamRosterPersonMappingStateError("Reviewed person mappings are malformed.")
        candidate = next(
            (
                candidate
                for candidate in group.candidates
                if candidate.membership_id == item["membership_id"]
                and candidate.usable
            ),
            None,
        )
        if candidate is None:
            raise TeamRosterPersonMappingStateError(
                "A reviewed membership is stale, inactive, or belongs to another team."
            )
        resolved[pair] = candidate
    if set(resolved) != expected_pairs:
        raise TeamRosterPersonMappingStateError("Reviewed person mappings are malformed.")
    for cell in cells:
        if cell.parsed_state != TeamRosterCellState.SUPPORTED_LITERAL:
            continue
        ids = [
            resolved[(cell.destination_team_id, token)].membership_id
            for token in cell.normalized_tokens
        ]
        if len(ids) != len(set(ids)):
            raise TeamRosterPersonMappingStateError(
                "One roster maps two source people to the same membership."
            )
    return payload
