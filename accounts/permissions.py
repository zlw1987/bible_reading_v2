from .models import ChurchRoleAssignment, ChurchStructureUnit, SmallGroup
from .structure_selectors import (
    _collect_unit_and_descendant_ids,
    get_user_primary_membership_unit,
)

CAP_MANAGE_READING_PLANS = "manage_reading_plans"
CAP_PUBLISH_READING_GUIDES = "publish_reading_guides"
CAP_MANAGE_BIBLE_STUDIES = "manage_bible_studies"
CAP_PUBLISH_BIBLE_STUDY_GUIDES = "publish_bible_study_guides"
CAP_MANAGE_SERVICE_EVENTS = "manage_service_events"
CAP_MANAGE_MINISTRY_TEAMS = "manage_ministry_teams"
CAP_MANAGE_TEAM_ASSIGNMENTS = "manage_team_assignments"
CAP_VIEW_GROUP_PROGRESS = "view_group_progress"
CAP_VIEW_DISTRICT_PROGRESS = "view_district_progress"
CAP_VIEW_ALL_GROUP_PROGRESS = "view_all_group_progress"
CAP_MODERATE_REFLECTIONS = "moderate_reflections"
CAP_MODERATE_PRAYERS = "moderate_prayers"
CAP_MANAGE_USERS = "manage_users"
CAP_MANAGE_CHURCH_MEMBERSHIPS = "manage_church_memberships"

ALL_CAPABILITIES = {
    CAP_MANAGE_READING_PLANS,
    CAP_PUBLISH_READING_GUIDES,
    CAP_MANAGE_BIBLE_STUDIES,
    CAP_PUBLISH_BIBLE_STUDY_GUIDES,
    CAP_MANAGE_SERVICE_EVENTS,
    CAP_MANAGE_MINISTRY_TEAMS,
    CAP_MANAGE_TEAM_ASSIGNMENTS,
    CAP_VIEW_GROUP_PROGRESS,
    CAP_VIEW_DISTRICT_PROGRESS,
    CAP_VIEW_ALL_GROUP_PROGRESS,
    CAP_MODERATE_REFLECTIONS,
    CAP_MODERATE_PRAYERS,
    CAP_MANAGE_USERS,
    CAP_MANAGE_CHURCH_MEMBERSHIPS,
}

ROLE_CAPABILITIES = {
    ChurchRoleAssignment.ROLE_PASTOR: {
        CAP_PUBLISH_READING_GUIDES,
        CAP_MANAGE_BIBLE_STUDIES,
        CAP_PUBLISH_BIBLE_STUDY_GUIDES,
        CAP_MANAGE_SERVICE_EVENTS,
        CAP_MANAGE_MINISTRY_TEAMS,
        CAP_MANAGE_TEAM_ASSIGNMENTS,
        CAP_VIEW_ALL_GROUP_PROGRESS,
        CAP_MODERATE_REFLECTIONS,
        CAP_MODERATE_PRAYERS,
        CAP_MANAGE_CHURCH_MEMBERSHIPS,
    },
    ChurchRoleAssignment.ROLE_ELDER: {
        CAP_MANAGE_BIBLE_STUDIES,
        CAP_PUBLISH_BIBLE_STUDY_GUIDES,
        CAP_MANAGE_SERVICE_EVENTS,
        CAP_MANAGE_MINISTRY_TEAMS,
        CAP_MANAGE_TEAM_ASSIGNMENTS,
        CAP_VIEW_ALL_GROUP_PROGRESS,
        CAP_MODERATE_REFLECTIONS,
        CAP_MODERATE_PRAYERS,
        CAP_MANAGE_CHURCH_MEMBERSHIPS,
    },
    ChurchRoleAssignment.ROLE_DEACON: {
        CAP_VIEW_ALL_GROUP_PROGRESS,
        CAP_MANAGE_USERS,
    },
    ChurchRoleAssignment.ROLE_DISTRICT_LEADER: {
        CAP_VIEW_DISTRICT_PROGRESS,
    },
    ChurchRoleAssignment.ROLE_GROUP_LEADER: {
        CAP_VIEW_GROUP_PROGRESS,
    },
    ChurchRoleAssignment.ROLE_COWORKER: {
        CAP_MANAGE_READING_PLANS,
        CAP_MANAGE_BIBLE_STUDIES,
        CAP_PUBLISH_BIBLE_STUDY_GUIDES,
        CAP_MANAGE_SERVICE_EVENTS,
        CAP_MANAGE_MINISTRY_TEAMS,
        CAP_MANAGE_TEAM_ASSIGNMENTS,
    },
}


def get_user_active_role_assignments(user):
    if not getattr(user, "is_authenticated", False):
        return ChurchRoleAssignment.objects.none()

    return (
        ChurchRoleAssignment.objects.filter(user=user, is_active=True)
        .select_related(
            "district",
            "district__church_structure_unit",
            "small_group",
            "small_group__church_structure_unit",
            "structure_unit",
        )
        .order_by("role", "scope_type")
    )


def get_role_assignment_structure_unit(assignment):
    """Resolve a role assignment's *runtime* structure-unit scope (explicit only).

    Read-only. Returns the canonical ``structure_unit`` when set, otherwise
    ``None`` (including global roles and any non-global scoped row that is missing
    ``structure_unit``). Ordinary ``ChurchStructureMembership`` is intentionally
    never consulted here: belonging does not decide role scope.

    ROLE-RETIRE.1B: the legacy ``district`` / ``small_group`` runtime fallback was
    retired. Runtime scoped role access now uses ``structure_unit`` only, so a
    non-global scoped assignment with a missing ``structure_unit`` fails closed.
    The legacy ``district`` / ``small_group`` fields are retained only for
    stored/admin/display/audit/backfill/rollback context and must not grant
    runtime access; diagnostics that still need to derive a candidate unit from
    those legacy fields use
    :func:`resolve_role_assignment_structure_unit_for_diagnostics` instead.

    Introduced as the CS-CORE.2D-A foundation; CS-CORE.2D-B used it to drive the
    group-progress permission / accessible group list at runtime
    (``get_accessible_progress_groups`` / ``can_view_group_progress_for``).
    """
    if assignment is None:
        return None

    if assignment.structure_unit_id:
        return assignment.structure_unit

    return None


def resolve_role_assignment_structure_unit_for_diagnostics(assignment):
    """Diagnostic-only structure-unit resolution with the legacy fallback.

    NOT a runtime permission path. Read-only. Prefers the canonical
    ``structure_unit``; otherwise derives a candidate unit from the legacy
    ``small_group`` / ``district`` mapped ``church_structure_unit``. Returns
    ``None`` when nothing can be resolved (including global roles).

    This is used exclusively by the audit / backfill / rollback tooling so it can
    still inspect what a legacy scope *would* map to for migration context.
    Runtime must never call this helper: the legacy runtime fallback was retired
    in ROLE-RETIRE.1B (use :func:`get_role_assignment_structure_unit` for any
    permission decision). Ordinary ``ChurchStructureMembership`` is never read.
    """
    if assignment is None:
        return None

    if assignment.structure_unit_id:
        return assignment.structure_unit

    small_group = assignment.small_group
    if small_group is not None and small_group.church_structure_unit_id:
        return small_group.church_structure_unit

    district = assignment.district
    if district is not None and district.church_structure_unit_id:
        return district.church_structure_unit

    return None


def assignment_scope_includes_unit(assignment, unit):
    """Return True when a role assignment's structure scope covers ``unit``.

    Read-only. The assignment's runtime structure unit (explicit ``structure_unit``
    only; see :func:`get_role_assignment_structure_unit`) covers ``unit`` when it is
    the same unit or an ancestor of ``unit`` (so a district-like unit scope covers
    its descendant small-group units). Fails closed when the target ``unit`` is
    missing or the scope unit is missing — including a non-global scoped assignment
    with no ``structure_unit`` after the ROLE-RETIRE.1B legacy-fallback retirement.
    Ordinary ``ChurchStructureMembership`` is never consulted.

    Added as the CS-CORE.2D-A foundation and consistent with the CS-CORE.2D-B
    structure-aware group-progress permission behavior (the same unit-plus-descendant
    scope rule ``get_accessible_progress_groups`` applies).
    """
    if unit is None:
        return False

    scope_unit = get_role_assignment_structure_unit(assignment)
    if scope_unit is None:
        return False

    current = unit
    seen_ids = set()
    while current is not None and current.id not in seen_ids:
        if current.id == scope_unit.id:
            return True
        seen_ids.add(current.id)
        current = current.parent

    return False


def has_capability(user, capability):
    if not getattr(user, "is_authenticated", False):
        return False

    if getattr(user, "is_staff", False) or getattr(user, "is_superuser", False):
        return capability in ALL_CAPABILITIES

    for assignment in get_user_active_role_assignments(user):
        if capability in ROLE_CAPABILITIES.get(assignment.role, set()):
            return True

    return False


def get_user_membership_progress_own_group(user, target_date=None):
    """Resolve a user's own-group progress group from membership-core (CS-CORE.2D-B).

    Membership-core replacement for the legacy ``Profile.small_group`` own-group
    progress rule. Resolves the user's single active primary
    ``ChurchStructureMembership`` unit to exactly one active legacy ``SmallGroup``
    mapped to that unit. ``Profile.small_group`` is never read.

    Fails closed (returns ``None``) on:

    - no active primary membership, or multiple active primary memberships
      (ambiguous, via :func:`get_user_primary_membership_unit`);
    - a membership unit that is not a ``small_group``-type unit; or
    - a unit that does not map to exactly one active legacy ``SmallGroup``.

    This grants *own-group* progress access only (the single mapped group); it is
    never a broad role/capability grant and never reaches sibling or descendant
    groups (privacy invariant 5 / concept separation).
    """
    unit = get_user_primary_membership_unit(user, target_date=target_date)
    if unit is None or unit.unit_type != ChurchStructureUnit.UNIT_SMALL_GROUP:
        return None

    groups = list(
        SmallGroup.objects.filter(is_active=True, church_structure_unit=unit)[:2]
    )
    if len(groups) != 1:
        return None
    return groups[0]


def get_accessible_progress_groups(user, target_date=None):
    """Active legacy ``SmallGroup`` rows the user may view group progress for.

    CS-CORE.2D-B structure-aware switch. Staff / superuser / the global
    ``CAP_VIEW_ALL_GROUP_PROGRESS`` capability still see every active group, and
    global role behavior is unchanged. Scoped access is otherwise the union of:

    - **Structure-aware role scopes:** for the two progress-relevant scoped roles
      (district leader on a district scope, group leader on a small-group scope),
      the scope unit is resolved by :func:`get_role_assignment_structure_unit`
      (explicit ``structure_unit`` only). A scope covers active legacy
      ``SmallGroup`` rows whose mapped ``church_structure_unit`` is that unit or a
      descendant. ROLE-RETIRE.1B retired the legacy ``district`` / ``small_group``
      runtime fallback, so a scoped role assignment with no ``structure_unit`` (or
      one that does not resolve) fails closed.
    - **Own-group:** the membership-core own group from
      :func:`get_user_membership_progress_own_group` (no longer
      ``Profile.small_group``).

    Ordinary ``ChurchStructureMembership`` grants only the single mapped own group,
    never a broader set.
    """
    groups = SmallGroup.objects.filter(is_active=True).order_by("name")

    if not getattr(user, "is_authenticated", False):
        return groups.none()

    if (
        getattr(user, "is_staff", False)
        or getattr(user, "is_superuser", False)
        or has_capability(user, CAP_VIEW_ALL_GROUP_PROGRESS)
    ):
        return groups

    accessible_ids = set()

    # Structure-aware role scopes. Only the two progress-relevant scoped roles grant
    # group access, matching the legacy role gating; the scope unit is resolved via
    # the CS-CORE.2D-A helper (explicit structure_unit only after ROLE-RETIRE.1B)
    # and covers the unit plus its descendants.
    scope_unit_ids = set()
    for assignment in get_user_active_role_assignments(user):
        is_district_scope = (
            assignment.role == ChurchRoleAssignment.ROLE_DISTRICT_LEADER
            and assignment.scope_type == ChurchRoleAssignment.SCOPE_DISTRICT
        )
        is_group_scope = (
            assignment.role == ChurchRoleAssignment.ROLE_GROUP_LEADER
            and assignment.scope_type == ChurchRoleAssignment.SCOPE_SMALL_GROUP
        )
        if not (is_district_scope or is_group_scope):
            continue
        scope_unit = get_role_assignment_structure_unit(assignment)
        if scope_unit is not None:
            scope_unit_ids |= _collect_unit_and_descendant_ids([scope_unit])

    if scope_unit_ids:
        accessible_ids.update(
            groups.filter(
                church_structure_unit_id__in=scope_unit_ids
            ).values_list("id", flat=True)
        )

    # Ordinary own-group access, migrated from Profile.small_group to membership-core.
    own_group = get_user_membership_progress_own_group(user, target_date=target_date)
    if own_group is not None and own_group.is_active:
        accessible_ids.add(own_group.id)

    if not accessible_ids:
        return groups.none()

    return groups.filter(id__in=accessible_ids).order_by("name")


def can_view_group_progress_for(user, small_group, target_date=None):
    """Whether ``user`` may view group progress for ``small_group``.

    Agrees exactly with :func:`get_accessible_progress_groups`: it is true iff
    ``small_group`` is in that accessible set. There is no separate staff
    short-circuit, so the single-group gate never diverges from the list (staff /
    global capability still match because the accessible set is every active group).
    """
    if small_group is None:
        return False

    return (
        get_accessible_progress_groups(user, target_date=target_date)
        .filter(id=small_group.id)
        .exists()
    )
