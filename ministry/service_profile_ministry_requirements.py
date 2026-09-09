"""Typed, read-only inspection for Service Profile ministry defaults."""

from dataclasses import dataclass
from enum import StrEnum

from .services.worship_governance import (
    resolve_worship_rotation_pool_for_team,
)


class RequirementValidationState(StrEnum):
    VALID_ACTIVE = "valid_active"
    INACTIVE_HISTORY = "inactive_history"
    INVALID_ACTIVE = "invalid_active"


class RequirementValidationReason(StrEnum):
    PROFILE_INACTIVE = "profile_inactive"
    TEAM_INACTIVE = "team_inactive"
    TEAM_NON_ASSIGNABLE = "team_non_assignable"
    TEAM_WORSHIP_ROTATION_POOL = "team_worship_rotation_pool"
    TEAM_UNDER_WORSHIP_ROTATION_POOL = "team_under_worship_rotation_pool"


WORSHIP_FORBIDDEN_REASONS = frozenset(
    {
        RequirementValidationReason.TEAM_WORSHIP_ROTATION_POOL,
        RequirementValidationReason.TEAM_UNDER_WORSHIP_ROTATION_POOL,
    }
)


@dataclass(frozen=True)
class ServiceProfileMinistryRequirementFact:
    requirement_id: int
    service_profile_id: int
    service_profile_key: str
    service_profile_event_type: str
    service_profile_name: str
    service_profile_name_en: str
    profile_is_active: bool
    ministry_team_id: int
    ministry_team_key: str | None
    ministry_team_name: str
    ministry_team_name_en: str
    team_is_active: bool
    team_is_assignable: bool
    team_is_worship_rotation_pool: bool
    requirement_is_active: bool
    sort_order: int
    validation_state: RequirementValidationState
    validation_reasons: tuple[RequirementValidationReason, ...]


@dataclass(frozen=True)
class ServiceProfileMinistryRequirementsInspection:
    rows: tuple[ServiceProfileMinistryRequirementFact, ...]
    service_profiles_with_requirements: int
    active_requirements: int
    inactive_requirements: int
    valid_active_requirements: int
    invalid_active_requirements: int
    worship_forbidden_requirements: int
    integrity_blockers: int


class ServiceProfileRequirementProfileNotFound(LookupError):
    pass


def active_requirement_validation_reasons(profile, team):
    """Classify current active-default validity with canonical identity only."""

    reasons = []
    if not profile.is_active:
        reasons.append(RequirementValidationReason.PROFILE_INACTIVE)
    if not team.is_active:
        reasons.append(RequirementValidationReason.TEAM_INACTIVE)
    if not team.is_assignable:
        reasons.append(RequirementValidationReason.TEAM_NON_ASSIGNABLE)
    if team.is_worship_rotation_pool:
        reasons.append(
            RequirementValidationReason.TEAM_WORSHIP_ROTATION_POOL
        )
    elif resolve_worship_rotation_pool_for_team(team).pool is not None:
        reasons.append(
            RequirementValidationReason.TEAM_UNDER_WORSHIP_ROTATION_POOL
        )
    return tuple(reasons)


def inspect_service_profile_ministry_requirements(
    *, profile_key=None, using="default"
):
    """Inspect every row in deterministic PK order without changing data."""

    from events.models import ServiceProfile

    from .models import ServiceProfileMinistryRequirement

    profile = None
    if profile_key is not None:
        try:
            profile = ServiceProfile.objects.using(using).get(key=profile_key)
        except ServiceProfile.DoesNotExist as error:
            raise ServiceProfileRequirementProfileNotFound(profile_key) from error

    queryset = ServiceProfileMinistryRequirement.objects.using(using).select_related(
        "service_profile",
        "ministry_team",
    )
    if profile is not None:
        queryset = queryset.filter(service_profile_id=profile.pk)

    facts = []
    for requirement in queryset.order_by("pk"):
        reasons = active_requirement_validation_reasons(
            requirement.service_profile,
            requirement.ministry_team,
        )
        if not requirement.is_active:
            state = RequirementValidationState.INACTIVE_HISTORY
        else:
            state = (
                RequirementValidationState.INVALID_ACTIVE
                if reasons
                else RequirementValidationState.VALID_ACTIVE
            )

        facts.append(
            ServiceProfileMinistryRequirementFact(
                requirement_id=requirement.pk,
                service_profile_id=requirement.service_profile_id,
                service_profile_key=requirement.service_profile.key,
                service_profile_event_type=requirement.service_profile.event_type,
                service_profile_name=requirement.service_profile.name,
                service_profile_name_en=requirement.service_profile.name_en,
                profile_is_active=requirement.service_profile.is_active,
                ministry_team_id=requirement.ministry_team_id,
                ministry_team_key=requirement.ministry_team.team_key,
                ministry_team_name=requirement.ministry_team.name,
                ministry_team_name_en=requirement.ministry_team.name_en,
                team_is_active=requirement.ministry_team.is_active,
                team_is_assignable=requirement.ministry_team.is_assignable,
                team_is_worship_rotation_pool=(
                    requirement.ministry_team.is_worship_rotation_pool
                ),
                requirement_is_active=requirement.is_active,
                sort_order=requirement.sort_order,
                validation_state=state,
                validation_reasons=reasons,
            )
        )

    rows = tuple(facts)
    active_rows = tuple(row for row in rows if row.requirement_is_active)
    invalid_rows = tuple(
        row
        for row in active_rows
        if row.validation_state == RequirementValidationState.INVALID_ACTIVE
    )
    return ServiceProfileMinistryRequirementsInspection(
        rows=rows,
        service_profiles_with_requirements=len(
            {row.service_profile_id for row in rows}
        ),
        active_requirements=len(active_rows),
        inactive_requirements=len(rows) - len(active_rows),
        valid_active_requirements=sum(
            row.validation_state == RequirementValidationState.VALID_ACTIVE
            for row in active_rows
        ),
        invalid_active_requirements=len(invalid_rows),
        worship_forbidden_requirements=sum(
            bool(set(row.validation_reasons) & WORSHIP_FORBIDDEN_REASONS)
            for row in invalid_rows
        ),
        integrity_blockers=len(invalid_rows),
    )
