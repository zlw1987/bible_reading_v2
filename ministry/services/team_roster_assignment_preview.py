"""Generic, signed, ZERO-WRITE Team Roster assignment preview.

``TEAM_ROSTER_PERSON_MAPPING_REVIEW_V1`` is the only proposal authority.  This
module adds current assignment/member comparison without granting write
authority.  It deliberately contains no deployment-team or workbook-column
meaning and never creates or changes a model row.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from hashlib import sha256
import re

from django.core import signing
from django.db.models import Prefetch
from django.utils import timezone

from accounts.structure_selectors import user_matches_structure_audience
from events.models import ServiceEvent, service_event_is_history
from events.service_profile_readiness import service_event_audience_readiness

from ..models import MinistryTeam, TeamAssignment, TeamAssignmentMember, TeamMembership
from .team_roster_person_mapping import (
    TEAM_ROSTER_PERSON_MAPPING_REVIEW_V1,
    TeamRosterPersonMappingStateError,
    decode_reviewed_team_roster_person_mapping,
    normalize_team_roster_visible_identity,
)
from .team_roster_workbook import (
    TEAM_ROSTER_CELL_V1,
    TeamRosterCellState,
    TeamRosterDiff,
    compute_team_roster_diff,
)
from .worship_context_review import FINGERPRINT_RE
from .worship_governance import (
    inspect_worship_ownership_consistency_for_events,
    resolve_worship_rotation_pool_for_team,
)
from .worship_xlsx_preview import (
    CONTRACT_REVISION,
    INTEGRATION_KEY,
    SIGNING_MAX_AGE_SECONDS,
)


TEAM_ROSTER_ASSIGNMENT_PREVIEW_V1 = "TEAM_ROSTER_ASSIGNMENT_PREVIEW_V1"
ASSIGNMENT_PREVIEW_STATE_TYPE = "team_roster_assignment_preview"
ASSIGNMENT_PREVIEW_SIGNING_SALT = "ministry.team_roster.assignment_preview.v1"
MAX_TEAM_ROSTER_ASSIGNMENT_PREVIEW_STATE_BYTES = 16_384

CURRENT_ASSIGNMENT_STATUSES = (
    TeamAssignment.STATUS_SCHEDULED,
    TeamAssignment.STATUS_CONFIRMED,
    TeamAssignment.STATUS_PREPARED,
)
HISTORICAL_ASSIGNMENT_STATUSES = (
    TeamAssignment.STATUS_COMPLETED,
    TeamAssignment.STATUS_CANCELLED,
)
KNOWN_ASSIGNMENT_STATUSES = frozenset(
    (*CURRENT_ASSIGNMENT_STATUSES, *HISTORICAL_ASSIGNMENT_STATUSES)
)
_SHA256_RE = re.compile(r"^[0-9A-F]{64}$")


class TeamRosterAssignmentPreviewState(StrEnum):
    NO_SOURCE_PROPOSAL = "no_source_proposal"
    CREATE_CANDIDATE = "create_candidate"
    EXACT_NOOP = "exact_noop"
    ROSTER_UPDATE_CANDIDATE = "roster_update_candidate"
    HISTORICAL_EVENT_SKIP = "historical_event_skip"
    SOURCE_BLOCKER = "source_blocker"
    INVALID_TARGET_BLOCKER = "invalid_target_blocker"
    AUDIENCE_BLOCKER = "audience_blocker"
    GOVERNANCE_BLOCKER = "governance_blocker"
    DUPLICATE_ASSIGNMENT_BLOCKER = "duplicate_assignment_blocker"
    HISTORICAL_ASSIGNMENT_BLOCKER = "historical_assignment_blocker"
    UNKNOWN_ASSIGNMENT_BLOCKER = "unknown_assignment_blocker"
    INVALID_ASSIGNMENT_BLOCKER = "invalid_assignment_blocker"
    UNSAFE_ROSTER_UPDATE_BLOCKER = "unsafe_roster_update_blocker"


class TeamRosterAssignmentReason(StrEnum):
    BLANK_NO_PROPOSAL = "blank_no_proposal"
    HISTORICAL_EVENT = "historical_event"
    SOURCE_GRAMMAR = "source_grammar"
    TARGET_INVALID = "target_invalid"
    AUDIENCE_NOT_READY = "audience_not_ready"
    OUTSIDE_AUDIENCE = "outside_audience"
    WORSHIP_GOVERNANCE = "worship_governance"
    DUPLICATE_CURRENT_ASSIGNMENTS = "duplicate_current_assignments"
    TERMINAL_ASSIGNMENT_CONFLICT = "terminal_assignment_conflict"
    UNKNOWN_ASSIGNMENT_STATUS = "unknown_assignment_status"
    INVALID_WORSHIP_FINGERPRINT = "invalid_worship_fingerprint"
    DUPLICATE_MEMBER_IDENTITY = "duplicate_member_identity"
    INVALID_MEMBER_SURFACE = "invalid_member_surface"
    CONFIRMED_PARENT_DIFFERS = "confirmed_parent_differs"
    PREPARED_PARENT_DIFFERS = "prepared_parent_differs"
    PROTECTED_MEMBER_REMOVAL = "protected_member_removal"


HARD_BLOCKER_STATES = frozenset(
    {
        TeamRosterAssignmentPreviewState.SOURCE_BLOCKER,
        TeamRosterAssignmentPreviewState.INVALID_TARGET_BLOCKER,
        TeamRosterAssignmentPreviewState.AUDIENCE_BLOCKER,
        TeamRosterAssignmentPreviewState.GOVERNANCE_BLOCKER,
        TeamRosterAssignmentPreviewState.DUPLICATE_ASSIGNMENT_BLOCKER,
        TeamRosterAssignmentPreviewState.HISTORICAL_ASSIGNMENT_BLOCKER,
        TeamRosterAssignmentPreviewState.UNKNOWN_ASSIGNMENT_BLOCKER,
        TeamRosterAssignmentPreviewState.INVALID_ASSIGNMENT_BLOCKER,
        TeamRosterAssignmentPreviewState.UNSAFE_ROSTER_UPDATE_BLOCKER,
    }
)


class TeamRosterAssignmentPreviewError(ValueError):
    pass


class TeamRosterAssignmentPreviewStateTooLarge(TeamRosterAssignmentPreviewError):
    def __init__(self, actual_bytes):
        self.actual_bytes = actual_bytes
        self.maximum_bytes = MAX_TEAM_ROSTER_ASSIGNMENT_PREVIEW_STATE_BYTES
        super().__init__(
            f"Signed assignment-preview evidence is {actual_bytes} bytes; the "
            f"existing {self.maximum_bytes}-byte bound was not raised."
        )


@dataclass(frozen=True, slots=True)
class TeamRosterPreviewMembership:
    membership_id: int
    visible_identity: str


@dataclass(frozen=True, slots=True)
class TeamRosterAssignmentPreviewRow:
    source_row: int
    source_cell: str
    local_date: date
    event_id: int
    team_id: int
    team_key: str
    team_display_name: str
    source_state: TeamRosterCellState
    workbook_roster: tuple[str, ...]
    reviewed_membership_ids: tuple[int, ...]
    reviewed_memberships: tuple[TeamRosterPreviewMembership, ...]
    current_assignment_id: int | None
    current_assignment_status: str | None
    current_membership_ids: tuple[int, ...]
    current_memberships: tuple[TeamRosterPreviewMembership, ...]
    state: TeamRosterAssignmentPreviewState
    diff: TeamRosterDiff | None
    reason_code: str | None
    preserved_assignment_member_ids: tuple[int, ...]
    preserved_memberships: tuple[TeamRosterPreviewMembership, ...]
    added_memberships: tuple[TeamRosterPreviewMembership, ...]
    removed_memberships: tuple[TeamRosterPreviewMembership, ...]

    @property
    def is_hard_blocker(self):
        return self.state in HARD_BLOCKER_STATES


@dataclass(frozen=True, slots=True)
class TeamRosterAssignmentPreview:
    filename: str
    workbook_sha256: str
    rows: tuple[TeamRosterAssignmentPreviewRow, ...]
    signed_preview_state: str
    signed_state_bytes: int
    normalized_payload: dict

    @property
    def state_counts(self):
        counts = Counter(row.state.value for row in self.rows)
        return tuple(sorted(counts.items()))

    @property
    def blocker_counts(self):
        counts = Counter(
            row.reason_code for row in self.rows if row.is_hard_blocker
        )
        return tuple(sorted((key, value) for key, value in counts.items() if key))

    @property
    def mapped_row_count(self):
        return len(self.rows)

    def count(self, state):
        return sum(row.state == state for row in self.rows)

    @property
    def no_source_proposal_count(self):
        return self.count(TeamRosterAssignmentPreviewState.NO_SOURCE_PROPOSAL)

    @property
    def historical_event_skip_count(self):
        return self.count(TeamRosterAssignmentPreviewState.HISTORICAL_EVENT_SKIP)

    @property
    def create_count(self):
        return self.count(TeamRosterAssignmentPreviewState.CREATE_CANDIDATE)

    @property
    def exact_noop_count(self):
        return self.count(TeamRosterAssignmentPreviewState.EXACT_NOOP)

    @property
    def update_count(self):
        return self.count(
            TeamRosterAssignmentPreviewState.ROSTER_UPDATE_CANDIDATE
        )

    @property
    def hard_blocker_count(self):
        return sum(row.is_hard_blocker for row in self.rows)

    @property
    def has_changes(self):
        return bool(self.create_count or self.update_count)

    @property
    def has_hard_blockers(self):
        return bool(self.hard_blocker_count)

    @property
    def future_writer_eligible(self):
        return self.has_changes and not self.has_hard_blockers


def _text_digest(value):
    return sha256(value.encode("utf-8")).hexdigest().upper()


def _safe_visible_identity(membership):
    if membership.display_name:
        value = membership.display_name
    elif membership.user_id:
        value = membership.user.get_full_name() or membership.user.get_username()
    else:
        return None
    try:
        value = normalize_team_roster_visible_identity(value)
    except TeamRosterPersonMappingStateError:
        return None
    return value or None


def _display_membership(membership):
    return TeamRosterPreviewMembership(
        membership_id=membership.pk,
        visible_identity=(
            _safe_visible_identity(membership)
            or f"Membership #{membership.pk}"
        ),
    )


def _membership_payload(membership):
    identity = _safe_visible_identity(membership)
    return {
        "id": membership.pk,
        "team_id": membership.team_id,
        "active": membership.is_active,
        "updated_at": membership.updated_at.isoformat(),
        "linked_user_id": membership.user_id,
        "linked_user_active": (
            membership.user.is_active if membership.user_id else None
        ),
        "visible_identity_digest": (
            _text_digest(identity) if identity is not None else None
        ),
    }


def _member_payload(member):
    return {
        "id": member.pk,
        "membership_id": member.membership_id,
        "created_at": member.created_at.isoformat(),
        "confirmed_at": (
            member.confirmed_at.isoformat() if member.confirmed_at else None
        ),
        "confirmation_note_digest": _text_digest(member.confirmation_note),
    }


def _assignment_payload(assignment):
    return {
        "id": assignment.pk,
        "event_id": assignment.service_event_id,
        "team_id": assignment.ministry_team_id,
        "status": assignment.status,
        "created_by_id": assignment.created_by_id,
        "created_at": assignment.created_at.isoformat(),
        "updated_at": assignment.updated_at.isoformat(),
        "reviewed_worship_context_fingerprint": (
            assignment.reviewed_worship_context_fingerprint
        ),
        "notes_digest": _text_digest(assignment.notes),
        "members": [
            _member_payload(member)
            for member in assignment.assignment_members.all()
        ],
    }


def _team_payload(team):
    return {
        "id": team.pk,
        "key": team.team_key,
        "active": team.is_active,
        "assignable": team.is_assignable,
        "updated_at": team.updated_at.isoformat(),
    }


def _audience_payload(event):
    evidence = service_event_audience_readiness(event)
    return {
        "ready": evidence["ready"],
        "invalid_reasons": evidence["invalid_reasons"],
        "units": [
            {"id": unit["id"], "active": unit["is_active"]}
            for unit in evidence["units"]
        ],
    }


def _event_payload(event, *, now, audience_evidence=None):
    return {
        "id": event.pk,
        "service_profile_id": event.service_profile_id,
        "service_profile_key": event.service_profile.key,
        "service_profile_active": event.service_profile.is_active,
        "service_profile_event_type": event.service_profile.event_type,
        "event_type": event.event_type,
        "start_datetime": event.start_datetime.isoformat(),
        "end_datetime": (
            event.end_datetime.isoformat() if event.end_datetime else None
        ),
        "status": event.status,
        "scheduling_revision": event.scheduling_revision,
        "rotation_anchor_team_id": event.rotation_anchor_team_id,
        "updated_at": event.updated_at.isoformat(),
        "historical": _event_is_historical(event, now=now),
        "audience": audience_evidence or _audience_payload(event),
    }


def _governance_payload(inspection):
    return {
        "state": inspection.state.value,
        "selected_team_id": (
            inspection.selected_team.pk if inspection.selected_team else None
        ),
        "selected_team_is_eligible": inspection.selected_team_is_eligible,
        "applicable_pools": [
            {"pool_id": item.pool.pk, "anchor_id": item.anchor.pk}
            for item in inspection.applicable_pools
        ],
        "eligible_candidates": [
            {"team_id": item.team.pk, "pool_id": item.owning_pool.pk}
            for item in inspection.eligible_candidates
        ],
        "current_assignments": [
            {
                "assignment_id": item.assignment_id,
                "team_id": item.team.pk,
                "pool_id": item.owning_pool.pk,
                "pool_usable": item.pool_is_usable,
                "pool_applicable": item.pool_is_applicable,
                "team_eligible": item.team_is_eligible,
            }
            for item in inspection.current_worship_assignments
        ],
    }


def _event_is_historical(event, *, now):
    return (
        event.status == ServiceEvent.STATUS_COMPLETED
        or service_event_is_history(event, now=now)
    )


def _target_is_valid(event, team):
    return bool(
        event.service_profile_id
        and event.service_profile.is_active
        and event.service_profile.event_type == event.event_type
        and event.status in {
            ServiceEvent.STATUS_PUBLISHED,
            ServiceEvent.STATUS_COMPLETED,
        }
        and team.team_key
        and team.is_active
        and team.is_assignable
    )


def _governance_allows(*, team, assignment, inspection, team_is_worship):
    if not team_is_worship:
        return True
    eligible_ids = {item.team.pk for item in inspection.eligible_candidates}
    other_current = [
        item
        for item in inspection.current_worship_assignments
        if assignment is None or item.assignment_id != assignment.pk
    ]
    return bool(
        inspection.selected_team is not None
        and inspection.selected_team_is_eligible
        and inspection.selected_team.pk == team.pk
        and team.pk in eligible_ids
        and not other_current
    )


def _member_invalid(member, *, team_id):
    membership = member.membership
    return bool(
        membership.team_id != team_id
        or not membership.is_active
        or membership.user_id and not membership.user.is_active
        or _safe_visible_identity(membership) is None
    )


def _outside_audience(membership, event, *, cache):
    if membership.user_id is None:
        return False
    units = list(event.get_audience_scope_units())
    unit_ids = tuple(sorted(unit.pk for unit in units))
    key = (membership.user_id, unit_ids)
    if key not in cache:
        cache[key] = not user_matches_structure_audience(membership.user, units)
    return cache[key]


def _classify_pair(
    *,
    cell,
    event,
    team,
    reviewed_ids,
    assignments,
    membership_by_id,
    inspection,
    team_is_worship,
    audience_ready,
    audience_cache,
    now,
):
    if cell["parsed_state"] == TeamRosterCellState.NO_SOURCE_PROPOSAL.value:
        return (
            TeamRosterAssignmentPreviewState.NO_SOURCE_PROPOSAL,
            TeamRosterAssignmentReason.BLANK_NO_PROPOSAL.value,
            None,
            (),
        )
    if _event_is_historical(event, now=now):
        return (
            TeamRosterAssignmentPreviewState.HISTORICAL_EVENT_SKIP,
            TeamRosterAssignmentReason.HISTORICAL_EVENT.value,
            None,
            (),
        )
    if cell["parsed_state"] != TeamRosterCellState.SUPPORTED_LITERAL.value:
        return (
            TeamRosterAssignmentPreviewState.SOURCE_BLOCKER,
            f"{TeamRosterAssignmentReason.SOURCE_GRAMMAR.value}:{cell['parsed_state']}",
            None,
            (),
        )
    if not _target_is_valid(event, team):
        return (
            TeamRosterAssignmentPreviewState.INVALID_TARGET_BLOCKER,
            TeamRosterAssignmentReason.TARGET_INVALID.value,
            None,
            (),
        )

    current = [
        item for item in assignments if item.status in CURRENT_ASSIGNMENT_STATUSES
    ]
    historical = [
        item for item in assignments if item.status in HISTORICAL_ASSIGNMENT_STATUSES
    ]
    unknown = [item for item in assignments if item.status not in KNOWN_ASSIGNMENT_STATUSES]
    if len(current) > 1:
        return (
            TeamRosterAssignmentPreviewState.DUPLICATE_ASSIGNMENT_BLOCKER,
            TeamRosterAssignmentReason.DUPLICATE_CURRENT_ASSIGNMENTS.value,
            None,
            (),
        )
    if unknown:
        return (
            TeamRosterAssignmentPreviewState.UNKNOWN_ASSIGNMENT_BLOCKER,
            TeamRosterAssignmentReason.UNKNOWN_ASSIGNMENT_STATUS.value,
            None,
            (),
        )
    if historical:
        return (
            TeamRosterAssignmentPreviewState.HISTORICAL_ASSIGNMENT_BLOCKER,
            TeamRosterAssignmentReason.TERMINAL_ASSIGNMENT_CONFLICT.value,
            None,
            (),
        )

    if not current:
        diff = compute_team_roster_diff((), reviewed_ids)
        if not audience_ready:
            return (
                TeamRosterAssignmentPreviewState.AUDIENCE_BLOCKER,
                TeamRosterAssignmentReason.AUDIENCE_NOT_READY.value,
                diff,
                (),
            )
        if not _governance_allows(
            team=team,
            assignment=None,
            inspection=inspection,
            team_is_worship=team_is_worship,
        ):
            return (
                TeamRosterAssignmentPreviewState.GOVERNANCE_BLOCKER,
                TeamRosterAssignmentReason.WORSHIP_GOVERNANCE.value,
                diff,
                (),
            )
        if any(
            _outside_audience(membership_by_id[item], event, cache=audience_cache)
            for item in diff.add_ids
        ):
            return (
                TeamRosterAssignmentPreviewState.AUDIENCE_BLOCKER,
                TeamRosterAssignmentReason.OUTSIDE_AUDIENCE.value,
                diff,
                (),
            )
        return (
            TeamRosterAssignmentPreviewState.CREATE_CANDIDATE,
            None,
            diff,
            (),
        )

    assignment = current[0]
    members = list(assignment.assignment_members.all())
    member_ids = [item.membership_id for item in members]
    if len(member_ids) != len(set(member_ids)):
        return (
            TeamRosterAssignmentPreviewState.INVALID_ASSIGNMENT_BLOCKER,
            TeamRosterAssignmentReason.DUPLICATE_MEMBER_IDENTITY.value,
            None,
            (),
        )
    diff = compute_team_roster_diff(member_ids, reviewed_ids)
    preserved_row_ids = tuple(
        sorted(item.pk for item in members if item.membership_id in diff.preserved_ids)
    )
    fingerprint = assignment.reviewed_worship_context_fingerprint
    if fingerprint is not None and FINGERPRINT_RE.fullmatch(fingerprint) is None:
        return (
            TeamRosterAssignmentPreviewState.INVALID_ASSIGNMENT_BLOCKER,
            TeamRosterAssignmentReason.INVALID_WORSHIP_FINGERPRINT.value,
            diff,
            preserved_row_ids,
        )
    invalid_members = [
        item for item in members if _member_invalid(item, team_id=team.pk)
    ]
    invalid_removed = [
        item for item in invalid_members if item.membership_id in diff.remove_ids
    ]
    if invalid_removed:
        return (
            TeamRosterAssignmentPreviewState.UNSAFE_ROSTER_UPDATE_BLOCKER,
            TeamRosterAssignmentReason.PROTECTED_MEMBER_REMOVAL.value,
            diff,
            preserved_row_ids,
        )
    if invalid_members:
        return (
            TeamRosterAssignmentPreviewState.INVALID_ASSIGNMENT_BLOCKER,
            TeamRosterAssignmentReason.INVALID_MEMBER_SURFACE.value,
            diff,
            preserved_row_ids,
        )
    if not _governance_allows(
        team=team,
        assignment=assignment,
        inspection=inspection,
        team_is_worship=team_is_worship,
    ):
        return (
            TeamRosterAssignmentPreviewState.GOVERNANCE_BLOCKER,
            TeamRosterAssignmentReason.WORSHIP_GOVERNANCE.value,
            diff,
            preserved_row_ids,
        )
    if not diff.add_ids and not diff.remove_ids:
        return (
            TeamRosterAssignmentPreviewState.EXACT_NOOP,
            None,
            diff,
            preserved_row_ids,
        )
    if assignment.status == TeamAssignment.STATUS_CONFIRMED:
        return (
            TeamRosterAssignmentPreviewState.UNSAFE_ROSTER_UPDATE_BLOCKER,
            TeamRosterAssignmentReason.CONFIRMED_PARENT_DIFFERS.value,
            diff,
            preserved_row_ids,
        )
    if assignment.status == TeamAssignment.STATUS_PREPARED:
        return (
            TeamRosterAssignmentPreviewState.UNSAFE_ROSTER_UPDATE_BLOCKER,
            TeamRosterAssignmentReason.PREPARED_PARENT_DIFFERS.value,
            diff,
            preserved_row_ids,
        )
    removed_rows = [item for item in members if item.membership_id in diff.remove_ids]
    if any(
        item.confirmed_at is not None or item.confirmation_note != ""
        for item in removed_rows
    ):
        return (
            TeamRosterAssignmentPreviewState.UNSAFE_ROSTER_UPDATE_BLOCKER,
            TeamRosterAssignmentReason.PROTECTED_MEMBER_REMOVAL.value,
            diff,
            preserved_row_ids,
        )
    if not audience_ready:
        return (
            TeamRosterAssignmentPreviewState.AUDIENCE_BLOCKER,
            TeamRosterAssignmentReason.AUDIENCE_NOT_READY.value,
            diff,
            preserved_row_ids,
        )
    if any(
        _outside_audience(membership_by_id[item], event, cache=audience_cache)
        for item in diff.add_ids
    ):
        return (
            TeamRosterAssignmentPreviewState.AUDIENCE_BLOCKER,
            TeamRosterAssignmentReason.OUTSIDE_AUDIENCE.value,
            diff,
            preserved_row_ids,
        )
    return (
        TeamRosterAssignmentPreviewState.ROSTER_UPDATE_CANDIDATE,
        None,
        diff,
        preserved_row_ids,
    )


def _assignment_queryset(event_ids, team_ids):
    member_rows = TeamAssignmentMember.objects.select_related(
        "membership", "membership__user"
    ).order_by("id")
    return (
        TeamAssignment.objects.filter(
            service_event_id__in=event_ids,
            ministry_team_id__in=team_ids,
        )
        .select_related("service_event", "ministry_team")
        .prefetch_related(Prefetch("assignment_members", queryset=member_rows))
        .order_by("service_event_id", "ministry_team_id", "id")
    )


def _team_display_name(team, language):
    primary = team.get_name(language)
    secondary = team.name_en if language == "zh" else team.name
    return f"{primary} / {secondary}" if secondary and secondary != primary else primary


def _build_preview(
    *,
    reviewed_person_state,
    user,
    language,
    max_age,
    now,
    generated_at,
    signed_token=None,
    allowed_event_revision_advances=(),
):
    try:
        authority = decode_reviewed_team_roster_person_mapping(
            reviewed_person_state,
            user=user,
            language=language,
            max_age=max_age,
            _allowed_event_revision_advances=allowed_event_revision_advances,
        )
    except TeamRosterPersonMappingStateError as exc:
        raise TeamRosterAssignmentPreviewError(
            "Reviewed person-mapping authority is invalid, expired, or stale."
        ) from exc

    classification_now = now or timezone.now()
    mapped = authority["mapped_columns"]
    cells = authority["source_cells"]
    selections = {
        (item["destination_team_id"], item["source_token"]): item["membership_id"]
        for item in authority["reviewed_selections"]
    }
    team_ids = tuple(item["destination_team_id"] for item in mapped)
    event_ids = tuple(item["event_id"] for item in authority["target_events"])
    teams = MinistryTeam.objects.in_bulk(team_ids)
    events = (
        ServiceEvent.objects.select_related(
            "service_profile", "rotation_anchor_team"
        )
        .prefetch_related("audience_scope_links__unit")
        .in_bulk(event_ids)
    )
    if len(teams) != len(team_ids) or len(events) != len(event_ids):
        raise TeamRosterAssignmentPreviewError("Current target truth changed.")

    reviewed_ids = tuple(sorted(set(selections.values())))
    memberships = TeamMembership.objects.select_related("user").in_bulk(reviewed_ids)
    if len(memberships) != len(reviewed_ids):
        raise TeamRosterAssignmentPreviewError("Reviewed membership truth changed.")

    assignments = list(_assignment_queryset(event_ids, team_ids))
    assignments_by_pair = defaultdict(list)
    all_memberships = dict(memberships)
    for assignment in assignments:
        assignments_by_pair[
            (assignment.service_event_id, assignment.ministry_team_id)
        ].append(assignment)
        for member in assignment.assignment_members.all():
            all_memberships[member.membership_id] = member.membership

    ordered_events = [events[event_id] for event_id in event_ids]
    governance = inspect_worship_ownership_consistency_for_events(ordered_events)
    audience_evidence = {
        event.pk: _audience_payload(event)
        for event in ordered_events
    }
    team_is_worship = {
        team_id: resolve_worship_rotation_pool_for_team(teams[team_id]).pool
        is not None
        for team_id in team_ids
    }
    audience_cache = {}

    rows = []
    signed_rows = []
    for cell in cells:
        event = events[cell["event_id"]]
        team = teams[cell["destination_team_id"]]
        pair_assignments = assignments_by_pair[(event.pk, team.pk)]
        if cell["parsed_state"] == TeamRosterCellState.SUPPORTED_LITERAL.value:
            row_reviewed_ids = tuple(
                sorted(selections[(team.pk, token)] for token in cell["normalized_tokens"])
            )
        else:
            row_reviewed_ids = ()
        state, reason, diff, preserved_row_ids = _classify_pair(
            cell=cell,
            event=event,
            team=team,
            reviewed_ids=row_reviewed_ids,
            assignments=pair_assignments,
            membership_by_id=all_memberships,
            inspection=governance[event.pk],
            team_is_worship=team_is_worship[team.pk],
            audience_ready=audience_evidence[event.pk]["ready"],
            audience_cache=audience_cache,
            now=classification_now,
        )
        current = [
            item
            for item in pair_assignments
            if item.status in CURRENT_ASSIGNMENT_STATUSES
        ]
        current_assignment = current[0] if len(current) == 1 else None
        current_members = (
            list(current_assignment.assignment_members.all())
            if current_assignment is not None
            else []
        )
        current_ids = tuple(sorted(item.membership_id for item in current_members))
        reviewed_displays = tuple(
            _display_membership(memberships[item]) for item in row_reviewed_ids
        )
        current_displays = tuple(
            _display_membership(item.membership)
            for item in sorted(current_members, key=lambda value: value.membership_id)
        )
        display_by_id = {
            item.membership_id: item
            for item in (*reviewed_displays, *current_displays)
        }
        rows.append(
            TeamRosterAssignmentPreviewRow(
                source_row=cell["source_row"],
                source_cell=cell["source_cell"],
                local_date=datetime.fromisoformat(cell["local_date"]).date(),
                event_id=event.pk,
                team_id=team.pk,
                team_key=team.team_key,
                team_display_name=_team_display_name(team, language),
                source_state=TeamRosterCellState(cell["parsed_state"]),
                workbook_roster=tuple(cell["normalized_tokens"]),
                reviewed_membership_ids=row_reviewed_ids,
                reviewed_memberships=reviewed_displays,
                current_assignment_id=(
                    current_assignment.pk if current_assignment else None
                ),
                current_assignment_status=(
                    current_assignment.status if current_assignment else None
                ),
                current_membership_ids=current_ids,
                current_memberships=current_displays,
                state=state,
                diff=diff,
                reason_code=reason,
                preserved_assignment_member_ids=preserved_row_ids,
                preserved_memberships=(
                    tuple(display_by_id[item] for item in diff.preserved_ids)
                    if diff is not None
                    else ()
                ),
                added_memberships=(
                    tuple(display_by_id[item] for item in diff.add_ids)
                    if diff is not None
                    else ()
                ),
                removed_memberships=(
                    tuple(display_by_id[item] for item in diff.remove_ids)
                    if diff is not None
                    else ()
                ),
            )
        )
        signed_rows.append(
            {
                "source_row": cell["source_row"],
                "source_cell": cell["source_cell"],
                "event_id": event.pk,
                "team_id": team.pk,
                "source_state": cell["parsed_state"],
                "source_token_digests": [
                    _text_digest(value) for value in cell["normalized_tokens"]
                ],
                "reviewed_membership_ids": list(row_reviewed_ids),
                "assignment_ids": [item.pk for item in pair_assignments],
                "team_is_worship": team_is_worship[team.pk],
                "state": state.value,
                "reason": reason,
                "diff": (
                    None
                    if diff is None
                    else {
                        "current": list(diff.current_membership_ids),
                        "reviewed": list(diff.reviewed_membership_ids),
                        "preserved": list(diff.preserved_ids),
                        "add": list(diff.add_ids),
                        "remove": list(diff.remove_ids),
                    }
                ),
                "preserved_assignment_member_ids": list(preserved_row_ids),
            }
        )

    summary = Counter(row.state.value for row in rows)
    blocker_counts = Counter(row.reason_code for row in rows if row.is_hard_blocker)
    payload = {
        "contract_version": TEAM_ROSTER_ASSIGNMENT_PREVIEW_V1,
        "state_type": ASSIGNMENT_PREVIEW_STATE_TYPE,
        "person_contract_version": TEAM_ROSTER_PERSON_MAPPING_REVIEW_V1,
        "person_state_sha256": _text_digest(reviewed_person_state),
        "integration_key": INTEGRATION_KEY,
        "adapter_contract_revision": CONTRACT_REVISION,
        "cell_contract_revision": TEAM_ROSTER_CELL_V1,
        "generated_at": generated_at,
        "user_id": user.pk,
        "filename": authority["filename"],
        "workbook_sha256": authority["workbook_sha256"],
        "teams": [_team_payload(teams[item]) for item in team_ids],
        "events": [
            {
                **_event_payload(
                    events[item],
                    now=classification_now,
                    audience_evidence=audience_evidence[item],
                ),
                "governance": _governance_payload(governance[item]),
            }
            for item in event_ids
        ],
        "memberships": [
            _membership_payload(all_memberships[item])
            for item in sorted(all_memberships)
        ],
        "assignments": [_assignment_payload(item) for item in assignments],
        "rows": signed_rows,
        "summary": {
            "mapped_rows": len(rows),
            "states": dict(sorted(summary.items())),
            "blockers": dict(
                sorted((key, value) for key, value in blocker_counts.items() if key)
            ),
            "has_changes": any(
                row.state
                in {
                    TeamRosterAssignmentPreviewState.CREATE_CANDIDATE,
                    TeamRosterAssignmentPreviewState.ROSTER_UPDATE_CANDIDATE,
                }
                for row in rows
            ),
            "has_hard_blockers": any(row.is_hard_blocker for row in rows),
        },
    }
    token = signed_token or signing.dumps(
        payload, salt=ASSIGNMENT_PREVIEW_SIGNING_SALT, compress=True
    )
    size = len(token.encode("utf-8"))
    if size > MAX_TEAM_ROSTER_ASSIGNMENT_PREVIEW_STATE_BYTES:
        raise TeamRosterAssignmentPreviewStateTooLarge(size)
    return TeamRosterAssignmentPreview(
        filename=authority["filename"],
        workbook_sha256=authority["workbook_sha256"],
        rows=tuple(rows),
        signed_preview_state=token,
        signed_state_bytes=size,
        normalized_payload=payload,
    )


def build_team_roster_assignment_preview(
    *, reviewed_person_state, user, language="en", now=None
):
    """Build one read-only row per exact event/mapped-team pair."""

    generated_at = timezone.now().isoformat()
    return _build_preview(
        reviewed_person_state=reviewed_person_state,
        user=user,
        language=language,
        max_age=SIGNING_MAX_AGE_SECONDS,
        now=now,
        generated_at=generated_at,
    )


_PREVIEW_KEYS = {
    "contract_version",
    "state_type",
    "person_contract_version",
    "person_state_sha256",
    "integration_key",
    "adapter_contract_revision",
    "cell_contract_revision",
    "generated_at",
    "user_id",
    "filename",
    "workbook_sha256",
    "teams",
    "events",
    "memberships",
    "assignments",
    "rows",
    "summary",
}


def decode_team_roster_assignment_preview(
    token,
    *,
    reviewed_person_state,
    user,
    language="en",
    max_age=SIGNING_MAX_AGE_SECONDS,
    now=None,
):
    """Strictly decode and recompute preview truth; still performs ZERO writes."""

    # Revalidate GENERAL.1D before any assignment query.  This also enforces the
    # integration and active-staff/superuser gates.
    try:
        decode_reviewed_team_roster_person_mapping(
            reviewed_person_state,
            user=user,
            language=language,
            max_age=max_age,
        )
    except TeamRosterPersonMappingStateError as exc:
        raise TeamRosterAssignmentPreviewError(
            "Reviewed person-mapping authority is invalid, expired, or stale."
        ) from exc
    try:
        payload = signing.loads(
            token, salt=ASSIGNMENT_PREVIEW_SIGNING_SALT, max_age=max_age
        )
    except signing.BadSignature as exc:
        raise TeamRosterAssignmentPreviewError(
            "Assignment-preview evidence is invalid or expired."
        ) from exc
    if (
        not isinstance(payload, dict)
        or set(payload) != _PREVIEW_KEYS
        or payload.get("contract_version") != TEAM_ROSTER_ASSIGNMENT_PREVIEW_V1
        or payload.get("state_type") != ASSIGNMENT_PREVIEW_STATE_TYPE
        or payload.get("person_contract_version")
        != TEAM_ROSTER_PERSON_MAPPING_REVIEW_V1
        or payload.get("person_state_sha256")
        != _text_digest(reviewed_person_state)
        or payload.get("integration_key") != INTEGRATION_KEY
        or payload.get("adapter_contract_revision") != CONTRACT_REVISION
        or payload.get("cell_contract_revision") != TEAM_ROSTER_CELL_V1
        or payload.get("user_id") != getattr(user, "pk", None)
        or not isinstance(payload.get("generated_at"), str)
        or not isinstance(payload.get("filename"), str)
        or not isinstance(payload.get("workbook_sha256"), str)
        or _SHA256_RE.fullmatch(payload["workbook_sha256"]) is None
        or not isinstance(payload.get("teams"), list)
        or not isinstance(payload.get("events"), list)
        or not isinstance(payload.get("memberships"), list)
        or not isinstance(payload.get("assignments"), list)
        or not isinstance(payload.get("rows"), list)
        or not isinstance(payload.get("summary"), dict)
    ):
        raise TeamRosterAssignmentPreviewError(
            "Assignment-preview evidence is malformed or belongs to another user."
        )
    try:
        datetime.fromisoformat(payload["generated_at"])
    except ValueError as exc:
        raise TeamRosterAssignmentPreviewError(
            "Assignment-preview timestamp is malformed."
        ) from exc

    current = _build_preview(
        reviewed_person_state=reviewed_person_state,
        user=user,
        language=language,
        max_age=max_age,
        now=now,
        generated_at=payload["generated_at"],
        signed_token=token,
    )
    if current.normalized_payload != payload:
        raise TeamRosterAssignmentPreviewError(
            "Assignment-preview evidence is stale or malformed."
        )
    return current
