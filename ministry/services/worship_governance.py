"""Read-only Worship applicability, candidate, and ownership consistency.

MO-S.6D-1D-A establishes domain facts only.  Nothing in this module accepts a
user, grants authority, changes an event or assignment, exposes a roster, or
emits a notification.  Mutation and UI consumers remain separately governed.

``build_worship_contexts()`` consumes the pool-aware consistency result for
fail-closed scheduler presentation and projects roster names only for one
consistent exact selected-team assignment. Mutation/UI work must reuse these
facts instead of inventing a second ownership rule.
"""

from dataclasses import dataclass
from enum import StrEnum

from accounts.models import ChurchStructureUnit

from ..models import MinistryTeam, TeamAssignment
from ..worship_rotation_pool import (
    WorshipRotationPoolInspection,
    inspect_worship_rotation_pool,
)


CURRENT_WORSHIP_ASSIGNMENT_STATUSES = (
    TeamAssignment.STATUS_SCHEDULED,
    TeamAssignment.STATUS_CONFIRMED,
    TeamAssignment.STATUS_PREPARED,
)


class WorshipOwnershipConsistencyState(StrEnum):
    NO_SELECTION = "no_selection"
    INVALID_SELECTION = "invalid_selection"
    SELECTED_UNSCHEDULED = "selected_unscheduled"
    CONSISTENT = "consistent"
    OFF_TEAM_CONFLICT = "off_team_conflict"
    OUT_OF_SCOPE_WORSHIP_CONFLICT = "out_of_scope_worship_conflict"
    MULTIPLE_CURRENT_WORSHIP_ASSIGNMENTS = (
        "multiple_current_worship_assignments"
    )
    DUPLICATE_SELECTED_TEAM_ASSIGNMENT = "duplicate_selected_team_assignment"


@dataclass(frozen=True)
class ApplicableWorshipPool:
    pool: MinistryTeam
    anchor: ChurchStructureUnit


@dataclass(frozen=True)
class WorshipTeamCandidate:
    team: MinistryTeam
    owning_pool: MinistryTeam


@dataclass(frozen=True)
class CurrentWorshipAssignmentReference:
    """Privacy-safe reference to one current operational Worship assignment."""

    assignment_id: int
    team: MinistryTeam
    owning_pool: MinistryTeam
    pool_is_usable: bool
    pool_is_applicable: bool
    team_is_eligible: bool


@dataclass(frozen=True)
class WorshipOwnershipConsistencyInspection:
    state: WorshipOwnershipConsistencyState
    selected_team: MinistryTeam | None
    selected_team_is_eligible: bool
    applicable_pools: tuple[ApplicableWorshipPool, ...]
    eligible_candidates: tuple[WorshipTeamCandidate, ...]
    current_worship_assignments: tuple[CurrentWorshipAssignmentReference, ...]
    matching_assignment_ids: tuple[int, ...]
    conflicting_assignment_ids: tuple[int, ...]


@dataclass(frozen=True)
class _PrimaryWorshipPoolResolution:
    pool: MinistryTeam | None = None
    pool_inspection: WorshipRotationPoolInspection | None = None
    path_is_active: bool = False


def _unit_is_equal_or_descendant_of_any(unit, ancestor_ids):
    """Cycle-safe Church Structure ancestry check with no name/type inference."""

    path_ids = []
    seen_ids = set()
    current = unit
    while current is not None:
        current_id = current.pk
        if current_id is None or current_id in seen_ids:
            return False
        seen_ids.add(current_id)
        path_ids.append(current_id)
        current = current.parent
    return bool(set(path_ids) & ancestor_ids)


def applicable_worship_rotation_pools(event):
    """Return operational Worship pools applicable to ``event`` audience.

    Only active stored audience units participate.  Pool structure is delegated
    to ``inspect_worship_rotation_pool()``; Host / Language, location, names,
    memberships, selected team, and database-id conventions are never inputs.
    """

    if event is None or not getattr(event, "pk", None):
        return ()

    audience_unit_ids = set(
        event.audience_scope_links.filter(unit__is_active=True).values_list(
            "unit_id", flat=True
        )
    )
    if not audience_unit_ids:
        return ()

    applicable = []
    pools = MinistryTeam.objects.filter(
        is_worship_rotation_pool=True
    ).order_by("name", "name_en", "id")
    for pool in pools:
        inspection = inspect_worship_rotation_pool(pool)
        if not inspection.is_usable or inspection.anchor is None:
            continue
        if _unit_is_equal_or_descendant_of_any(
            inspection.anchor, audience_unit_ids
        ):
            applicable.append(
                ApplicableWorshipPool(pool=pool, anchor=inspection.anchor)
            )
    return tuple(applicable)


def _resolve_primary_worship_pool(team):
    """Resolve the nearest configured pool on one deterministic primary path.

    Inactive teams remain traceable for conflict diagnosis but make the path
    ineligible for candidate selection.  Missing, ambiguous, broken, or cyclic
    primary paths fail closed without following secondary/display links.
    """

    if team is None or team.pk is None:
        return _PrimaryWorshipPoolResolution()

    current = team
    seen_team_ids = set()
    path_is_active = True
    while True:
        if current.pk is None or current.pk in seen_team_ids:
            return _PrimaryWorshipPoolResolution()
        seen_team_ids.add(current.pk)
        path_is_active = path_is_active and current.is_active

        if current.is_worship_rotation_pool:
            inspection = inspect_worship_rotation_pool(current)
            return _PrimaryWorshipPoolResolution(
                pool=current,
                pool_inspection=inspection,
                path_is_active=path_is_active,
            )

        primary_links = list(
            current.parent_links.filter(is_active=True, is_primary=True)
            .select_related("parent_team", "parent_church_unit")
            .order_by("sort_order", "id")[:2]
        )
        if len(primary_links) != 1:
            return _PrimaryWorshipPoolResolution()

        link = primary_links[0]
        has_parent_team = link.parent_team_id is not None
        has_church_anchor = link.parent_church_unit_id is not None
        if has_parent_team == has_church_anchor:
            return _PrimaryWorshipPoolResolution()
        if has_church_anchor:
            return _PrimaryWorshipPoolResolution()
        if link.parent_team is None:
            return _PrimaryWorshipPoolResolution()
        current = link.parent_team


def resolve_worship_rotation_pool_for_team(team):
    """Return the canonical primary-path Worship-pool resolution for ``team``.

    Mutation guards use the same fail-closed hierarchy resolution as the
    read-only ownership inspection.  The result grants no authority and makes
    no write; callers must still evaluate event applicability and candidates.
    """

    return _resolve_primary_worship_pool(team)


def _eligible_worship_team_candidates(applicable_pools):
    applicable_pool_ids = {item.pool.pk for item in applicable_pools}
    if not applicable_pool_ids:
        return ()

    candidates = []
    teams = MinistryTeam.objects.filter(
        is_active=True,
        is_assignable=True,
    ).order_by("name", "name_en", "id")
    for team in teams:
        resolution = _resolve_primary_worship_pool(team)
        if (
            resolution.pool is None
            or resolution.pool_inspection is None
            or not resolution.path_is_active
            or not resolution.pool_inspection.is_usable
            or resolution.pool.pk not in applicable_pool_ids
        ):
            continue
        candidates.append(
            WorshipTeamCandidate(team=team, owning_pool=resolution.pool)
        )
    return tuple(candidates)


def eligible_worship_team_candidates(event):
    """Return the deterministic union of eligible Worship Team candidates."""

    return _eligible_worship_team_candidates(
        applicable_worship_rotation_pools(event)
    )


def _current_worship_assignment_references(
    event, applicable_pools, eligible_candidates
):
    if event is None or not getattr(event, "pk", None):
        return ()

    applicable_pool_ids = {item.pool.pk for item in applicable_pools}
    eligible_team_ids = {item.team.pk for item in eligible_candidates}
    references = []
    assignments = (
        TeamAssignment.objects.filter(
            service_event=event,
            status__in=CURRENT_WORSHIP_ASSIGNMENT_STATUSES,
        )
        .select_related("ministry_team")
        .order_by("id")
    )
    for assignment in assignments:
        resolution = _resolve_primary_worship_pool(assignment.ministry_team)
        if resolution.pool is None or resolution.pool_inspection is None:
            continue
        references.append(
            CurrentWorshipAssignmentReference(
                assignment_id=assignment.pk,
                team=assignment.ministry_team,
                owning_pool=resolution.pool,
                pool_is_usable=resolution.pool_inspection.is_usable,
                pool_is_applicable=(
                    resolution.pool.pk in applicable_pool_ids
                    and resolution.pool_inspection.is_usable
                ),
                team_is_eligible=assignment.ministry_team_id in eligible_team_ids,
            )
        )
    return tuple(references)


def inspect_worship_ownership_consistency(event):
    """Inspect selected-team/current-assignment ownership without side effects."""

    applicable_pools = applicable_worship_rotation_pools(event)
    candidates = _eligible_worship_team_candidates(applicable_pools)
    eligible_team_ids = {candidate.team.pk for candidate in candidates}
    selected_team = getattr(event, "rotation_anchor_team", None)
    selected_team_id = getattr(event, "rotation_anchor_team_id", None)
    selected_is_eligible = selected_team_id in eligible_team_ids
    current = _current_worship_assignment_references(
        event, applicable_pools, candidates
    )
    matching_ids = tuple(
        reference.assignment_id
        for reference in current
        if reference.team.pk == selected_team_id
    )

    if len(current) > 1:
        if selected_team_id is not None and len(matching_ids) == len(current):
            state = (
                WorshipOwnershipConsistencyState.DUPLICATE_SELECTED_TEAM_ASSIGNMENT
            )
        else:
            state = (
                WorshipOwnershipConsistencyState.MULTIPLE_CURRENT_WORSHIP_ASSIGNMENTS
            )
    elif current:
        reference = current[0]
        if not reference.pool_is_applicable:
            state = (
                WorshipOwnershipConsistencyState.OUT_OF_SCOPE_WORSHIP_CONFLICT
            )
        elif reference.team.pk != selected_team_id:
            state = WorshipOwnershipConsistencyState.OFF_TEAM_CONFLICT
        elif not selected_is_eligible or not reference.team_is_eligible:
            state = WorshipOwnershipConsistencyState.INVALID_SELECTION
        else:
            state = WorshipOwnershipConsistencyState.CONSISTENT
    elif selected_team_id is None:
        state = WorshipOwnershipConsistencyState.NO_SELECTION
    elif not selected_is_eligible:
        state = WorshipOwnershipConsistencyState.INVALID_SELECTION
    else:
        state = WorshipOwnershipConsistencyState.SELECTED_UNSCHEDULED

    conflicting_ids = (
        ()
        if state
        in {
            WorshipOwnershipConsistencyState.NO_SELECTION,
            WorshipOwnershipConsistencyState.SELECTED_UNSCHEDULED,
            WorshipOwnershipConsistencyState.CONSISTENT,
        }
        else tuple(reference.assignment_id for reference in current)
    )
    return WorshipOwnershipConsistencyInspection(
        state=state,
        selected_team=selected_team,
        selected_team_is_eligible=selected_is_eligible,
        applicable_pools=applicable_pools,
        eligible_candidates=candidates,
        current_worship_assignments=current,
        matching_assignment_ids=matching_ids,
        conflicting_assignment_ids=conflicting_ids,
    )
