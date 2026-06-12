from django.db import models

from accounts.models import (
    ChurchStructureUnit,
    District,
    MinistryContext,
    SmallGroup,
)


def get_user_legacy_small_group(user):
    """Return the current runtime belonging source for ordinary users."""
    profile = getattr(user, "profile", None)
    return getattr(profile, "small_group", None)


def get_user_legacy_structure_unit(user):
    """Return the structure unit derived from Profile.small_group only."""
    small_group = get_user_legacy_small_group(user)
    if small_group is None:
        return None
    return small_group.church_structure_unit


def get_user_legacy_structure_units(user, include_ancestors=False):
    """Return legacy-derived structure units for a user.

    This function intentionally derives from Profile.small_group and the legacy
    mapping bridge only. ChurchStructureMembership is diagnostic/shadow data
    and is not a runtime source in this milestone.
    """
    unit = get_user_legacy_structure_unit(user)
    if unit is None:
        return []

    if include_ancestors:
        return unit.get_ancestors() + [unit]

    return [unit]


def _collect_unit_and_descendant_ids(units):
    """Return the ids of the given ChurchStructureUnit rows plus descendants."""
    unit_ids = set()
    frontier = [unit.id for unit in units if unit.id is not None]

    while frontier:
        unit_ids.update(frontier)
        frontier = list(
            ChurchStructureUnit.objects.filter(parent_id__in=frontier)
            .exclude(id__in=unit_ids)
            .values_list("id", flat=True)
        )

    return unit_ids


def resolve_units_to_small_groups(units):
    """Resolve selected ChurchStructureUnit rows to eligible active SmallGroups.

    This is the shared legacy-parity resolver for structure audience units.
    It bridges through the optional legacy mapping fields and never consults
    ChurchStructureMembership.
    """
    groups = SmallGroup.objects.filter(is_active=True)
    units = list(units)
    if not units:
        return groups.none()

    # Root / whole church selection covers every active small group.
    if any(unit.unit_type == ChurchStructureUnit.UNIT_ROOT for unit in units):
        return groups

    target_unit_ids = _collect_unit_and_descendant_ids(units)
    if not target_unit_ids:
        return groups.none()

    context_ids = list(
        MinistryContext.objects.filter(
            church_structure_unit_id__in=target_unit_ids,
        ).values_list("id", flat=True)
    )
    district_ids = list(
        District.objects.filter(
            church_structure_unit_id__in=target_unit_ids,
        ).values_list("id", flat=True)
    )

    match = models.Q(church_structure_unit_id__in=target_unit_ids)
    if context_ids:
        match |= models.Q(district__ministry_context_id__in=context_ids)
    if district_ids:
        match |= models.Q(district_id__in=district_ids)

    return groups.filter(match).distinct()


def user_matches_structure_audience(user, units):
    """Return whether a user matches selected structure audience units.

    Matching is legacy-parity only: authenticated root audiences match all
    authenticated users, while non-root audiences match Profile.small_group
    through resolve_units_to_small_groups. ChurchStructureMembership is not
    read here.
    """
    if not getattr(user, "is_authenticated", False):
        return False

    units = list(units)
    if any(unit.unit_type == ChurchStructureUnit.UNIT_ROOT for unit in units):
        return True

    small_group = get_user_legacy_small_group(user)
    if small_group is None:
        return False

    return resolve_units_to_small_groups(units).filter(id=small_group.id).exists()
