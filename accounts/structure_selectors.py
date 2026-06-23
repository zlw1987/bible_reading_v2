from django.db import models
from django.utils import timezone

from accounts.models import (
    ChurchStructureMembership,
    ChurchStructureUnit,
    SmallGroup,
)


def get_user_primary_membership_unit(user, target_date=None):
    """Return the unit of the user's single active primary membership.

    Membership-core belonging source (CS-CORE.2B-A). Active means
    ``status=STATUS_ACTIVE``, ``is_primary=True``, ``start_date <= target_date``
    and ``end_date`` null or ``>= target_date``. Requested, rejected,
    cancelled, ended, future, and expired memberships never count.

    Fails closed: anonymous/unsaved users return ``None``, and a user with
    multiple active primary memberships returns ``None`` instead of silently
    picking one row.
    """
    if not getattr(user, "is_authenticated", False):
        return None

    user_id = getattr(user, "pk", None)
    if user_id is None:
        return None

    target_date = target_date or timezone.localdate()
    memberships = list(
        ChurchStructureMembership.objects.filter(
            user_id=user_id,
            status=ChurchStructureMembership.STATUS_ACTIVE,
            is_primary=True,
            start_date__lte=target_date,
        )
        .filter(
            models.Q(end_date__isnull=True) | models.Q(end_date__gte=target_date)
        )
        .select_related("unit")[:2]
    )
    if len(memberships) != 1:
        return None

    return memberships[0].unit


def get_user_membership_structure_units(user, include_ancestors=False, target_date=None):
    """Return membership-core structure units for a user.

    Derives only from the single active primary ChurchStructureMembership
    unit; Profile.small_group is never read here. With
    ``include_ancestors=True`` the result is ancestors plus the own unit.
    """
    unit = get_user_primary_membership_unit(user, target_date=target_date)
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

    This is the shared resolver for structure audience units. It maps through
    ``SmallGroup.church_structure_unit`` only: a non-root selection resolves to
    the active groups whose mapped unit is one of the selected units or a
    descendant of one (via ``ChurchStructureUnit.parent``). It does not read the
    legacy parent/context fields ``SmallGroup.district`` or
    ``District.ministry_context`` and never consults ChurchStructureMembership.
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

    return groups.filter(church_structure_unit_id__in=target_unit_ids).distinct()


def user_matches_membership_structure_audience(user, units, target_date=None):
    """Return whether a user matches audience units via membership-core.

    Root audiences match every authenticated user. Non-root audiences match
    when the user's single active primary ChurchStructureMembership unit is
    one of the selected units or a descendant of one. Profile.small_group is
    never read here; requested/inactive memberships and ambiguous multiple
    active primary memberships fail closed.
    """
    if not getattr(user, "is_authenticated", False):
        return False

    units = list(units)
    if any(unit.unit_type == ChurchStructureUnit.UNIT_ROOT for unit in units):
        return True

    membership_unit = get_user_primary_membership_unit(user, target_date=target_date)
    if membership_unit is None:
        return False

    return membership_unit.id in _collect_unit_and_descendant_ids(units)


def user_matches_structure_audience(user, units):
    """Return whether a user matches selected structure audience units.

    Canonical matcher for ServiceEvent structure-audience rows. As of
    CS-CORE.2B-A this delegates to membership-core matching
    (ChurchStructureMembership active primary). Events with zero audience
    rows never reach this helper and fail closed for ordinary users.
    """
    return user_matches_membership_structure_audience(user, units)
