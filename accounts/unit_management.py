"""Delegated unit-management helpers (UNIT-LEAD-MANAGE.1B, read-only).

These helpers answer "which structure units may this user manage coworkers
for" for the read-only ``/my-units/`` discovery surface. They are deliberately
narrow:

- Management is granted only by staff/superuser status or an explicit active
  ``lead`` coworker role assignment on the unit itself or an ancestor
  (ancestor-or-self), per the recommended permission model in
  ``docs/MEMBER_RECORD_AND_SERVING_READINESS_PLAN.md`` (Section A.2).
- Management is NEVER inferred from ``ChurchStructureMembership`` (belonging),
  audience visibility, ``TeamAssignment`` / ``TeamAssignmentMember`` / My
  Serving, Bible Study visibility, or ordinary (non-lead) coworker roles.
- These helpers are read-only. They do not create, end, or mutate any
  assignment, membership, capability, or serving row.

The dedicated central capability ``CAP_MANAGE_STRUCTURE_COWORKERS`` described in
the plan (Section A.3) is intentionally NOT implemented in this slice; staff /
superuser is the only global manage path for now. Adding that capability is a
separate approved slice.
"""

from django.db.models import Q
from django.utils import timezone

from .models import (
    ChurchStructureUnit,
    ChurchStructureUnitRoleAssignment,
    ChurchStructureUnitRoleType,
)
from .ordering import structure_unit_sibling_sort_key
from .structure_selectors import _collect_unit_and_descendant_ids


def _user_is_structure_coworker_admin(user):
    """Whether the user has the central manage-all-coworkers capability.

    V1 read-only scope: only Django staff / superuser. The dedicated
    ``CAP_MANAGE_STRUCTURE_COWORKERS`` capability from the plan is deferred to a
    separate slice, so it is not consulted here yet.
    """
    return bool(
        getattr(user, "is_staff", False) or getattr(user, "is_superuser", False)
    )


def _active_lead_assignment_queryset(user, target_date=None):
    """Active ``lead`` coworker role assignments for ``user`` on ``target_date``.

    "Active" matches ``ChurchStructureUnitRoleAssignment.active_for_date``:
    ``is_active`` true, ``start_date`` reached, and ``end_date`` null or not yet
    past. Only the ``lead`` role type grants management in this surface.
    """
    if not getattr(user, "is_authenticated", False):
        return ChurchStructureUnitRoleAssignment.objects.none()

    user_id = getattr(user, "pk", None)
    if user_id is None:
        return ChurchStructureUnitRoleAssignment.objects.none()

    target_date = target_date or timezone.localdate()
    return (
        ChurchStructureUnitRoleAssignment.objects.filter(
            user_id=user_id,
            is_active=True,
            role_type__code=ChurchStructureUnitRoleType.CODE_LEAD,
            start_date__lte=target_date,
        )
        .filter(Q(end_date__isnull=True) | Q(end_date__gte=target_date))
    )


def get_user_active_lead_units(user, target_date=None):
    """Return active units where the user holds an active ``lead`` assignment.

    De-duplicated and limited to active units (an inactive unit is not a
    manageable surface). Order is unspecified here; callers that display the
    result should order it (see :func:`get_manageable_structure_units`).
    """
    assignments = _active_lead_assignment_queryset(
        user, target_date=target_date
    ).select_related("unit")

    units = {}
    for assignment in assignments:
        unit = assignment.unit
        if unit.is_active and unit.id not in units:
            units[unit.id] = unit
    return list(units.values())


def can_manage_unit_coworkers(user, unit, target_date=None):
    """Whether ``user`` may manage/read coworkers for ``unit`` in this surface.

    Read-only permission check. Returns ``True`` when any of:

    - ``user`` is staff / superuser (central manage-all path); or
    - ``user`` has an active ``lead`` coworker assignment on ``unit`` itself or
      any ancestor of ``unit`` (ancestor-or-self), where "active" matches
      ``ChurchStructureUnitRoleAssignment.active_for_date(target_date)``.

    Membership/belonging, audience visibility, serving, and ordinary (non-lead)
    coworker roles never grant management. Fails closed when ``unit`` is missing
    or the user is anonymous.
    """
    if unit is None:
        return False
    if not getattr(user, "is_authenticated", False):
        return False
    # Inactive units are not a manageable surface here, for everyone (including
    # staff/superuser). This read-only "My Units" surface only ever lists/manages
    # active units; editing an inactive unit's coworkers belongs to the admin
    # structure tree, not this delegated surface.
    if not unit.is_active:
        return False
    if _user_is_structure_coworker_admin(user):
        return True

    ancestor_or_self_ids = {ancestor.id for ancestor in unit.get_ancestors()}
    if unit.id is not None:
        ancestor_or_self_ids.add(unit.id)
    if not ancestor_or_self_ids:
        return False

    return (
        _active_lead_assignment_queryset(user, target_date=target_date)
        .filter(unit_id__in=ancestor_or_self_ids)
        .exists()
    )


def should_show_my_units_nav(user, target_date=None):
    """Cheap check for whether to surface the "My Units" nav entry.

    True for staff/superuser, or for a non-staff user with at least one active
    ``lead`` assignment **on an active unit** (i.e. a non-empty
    :func:`get_user_active_lead_units`). A lead whose only lead assignment is on
    an inactive unit has nothing manageable here, so the nav link stays hidden,
    matching :func:`get_manageable_structure_units`. Read-only.
    """
    if not getattr(user, "is_authenticated", False):
        return False
    if _user_is_structure_coworker_admin(user):
        return True
    return bool(get_user_active_lead_units(user, target_date=target_date))


def get_manageable_structure_units(user, target_date=None):
    """Return the ordered list of structure units the user may manage.

    - Staff / superuser see every active unit.
    - A lead sees each active unit they lead plus all active descendant units
      of those lead units (overlapping subtrees de-duplicated).
    - Anyone else sees nothing.

    The result is ordered hierarchy/path-aware (each unit sorts after its
    ancestors and among siblings by the same sibling key used elsewhere), so the
    list reads like the structure tree. Descendants are resolved on demand via
    the canonical ``ChurchStructureUnit.parent`` hierarchy; no legacy structure
    models/fields are consulted. Read-only.
    """
    if not getattr(user, "is_authenticated", False):
        return []

    if _user_is_structure_coworker_admin(user):
        units = ChurchStructureUnit.objects.filter(is_active=True)
        return _order_units_path_aware(units, target_date=target_date)

    lead_units = get_user_active_lead_units(user, target_date=target_date)
    if not lead_units:
        return []

    manageable_ids = _collect_unit_and_descendant_ids(lead_units)
    units = ChurchStructureUnit.objects.filter(
        id__in=manageable_ids, is_active=True
    )
    return _order_units_path_aware(units, target_date=target_date)


def _order_units_path_aware(units, language="zh", target_date=None):
    """Order units so each sorts after its ancestors, siblings by sibling key.

    ``target_date`` is accepted for signature symmetry but unused; ordering is
    purely structural. The whole unit tree is loaded once into an in-memory map
    so ancestor walks do not issue a query per unit (the tree is small).
    """
    units = list(units)
    if not units:
        return []

    tree = {
        unit.id: unit
        for unit in ChurchStructureUnit.objects.all().only(
            "id", "parent_id", "sort_order", "name", "name_en", "code"
        )
    }

    def sort_key(unit):
        chain = []
        current = tree.get(unit.id, unit)
        seen = set()
        while current is not None and current.id not in seen:
            seen.add(current.id)
            chain.append(structure_unit_sibling_sort_key(current, language))
            parent_id = getattr(current, "parent_id", None)
            current = tree.get(parent_id) if parent_id else None
        return list(reversed(chain))

    return sorted(units, key=sort_key)
