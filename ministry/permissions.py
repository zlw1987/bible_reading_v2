from django.db.models import Q
from django.utils import timezone

from accounts.permissions import (
    CAP_MANAGE_SERVICE_EVENTS,
    CAP_MANAGE_MINISTRY_TEAMS,
    CAP_MANAGE_TEAM_ASSIGNMENTS,
    has_capability,
)
from core.module_registry import get_enabled_module_keys

from .models import (
    MinistryTeamRoleAssignment,
    MinistryTeamRoleType,
    TeamAssignment,
    TeamAssignmentMember,
    TeamMembership,
)


# Ministry role-type codes that grant runtime team-management / team-scheduling
# authority for the exact team the role is held on. Kept intentionally minimal:
# assistant_lead / scheduler / technical_lead / admin / member_care / custom do
# NOT grant team management here.
MANAGEMENT_ROLE_TYPE_CODES = (
    MinistryTeamRoleType.CODE_LEAD,
    MinistryTeamRoleType.CODE_COORDINATOR,
)


def _active_management_role_assignments(user):
    """Base queryset of the user's date-valid active lead/coordinator role
    assignments on active teams.

    Source of truth after MINISTRY-ROLE-SOURCE.1C: runtime ministry
    team-management authority reads active ``MinistryTeamRoleAssignment`` rows,
    not ``TeamMembership.role``. Exact-team only — ancestor ministry teams,
    church-structure anchors, ``ChurchStructureMembership`` and
    ``ChurchStructureUnitRoleAssignment`` are not consulted here.
    """
    if not getattr(user, "is_authenticated", False):
        return MinistryTeamRoleAssignment.objects.none()

    today = timezone.localdate()
    return (
        MinistryTeamRoleAssignment.objects.filter(
            user=user,
            is_active=True,
            team__is_active=True,
            role_type__is_active=True,
            role_type__code__in=MANAGEMENT_ROLE_TYPE_CODES,
            start_date__lte=today,
        )
        .filter(Q(end_date__isnull=True) | Q(end_date__gte=today))
    )


def user_has_active_ministry_management_role(user, team):
    """True when the user holds an active lead/coordinator
    ``MinistryTeamRoleAssignment`` for exactly ``team`` (date-window valid).

    ``TeamMembership.role`` and ``TeamMembership.can_lead`` grant nothing here
    after MINISTRY-ROLE-SOURCE.1C.
    """
    if team is None or not getattr(user, "is_authenticated", False):
        return False

    return _active_management_role_assignments(user).filter(team=team).exists()


def user_managed_team_ids(user):
    """Distinct team ids the user can manage via active lead/coordinator role
    assignments (exact-team only)."""
    return (
        _active_management_role_assignments(user)
        .values_list("team_id", flat=True)
        .distinct()
    )


def can_manage_ministry_teams(user):
    return (
        getattr(user, "is_staff", False)
        or getattr(user, "is_superuser", False)
        or has_capability(user, CAP_MANAGE_MINISTRY_TEAMS)
    )


def user_team_memberships(user):
    if not getattr(user, "is_authenticated", False):
        return TeamMembership.objects.none()

    return (
        TeamMembership.objects.filter(user=user, is_active=True, team__is_active=True)
        .select_related("team", "user")
        .order_by("team__name", "role", "display_name")
    )


def can_view_ministry_team(user, team):
    if team is None or not getattr(user, "is_authenticated", False):
        return False

    if can_manage_ministry_teams(user):
        return True

    return user_team_memberships(user).filter(team=team).exists()


def can_manage_ministry_team(user, team):
    if team is None or not getattr(user, "is_authenticated", False):
        return False

    if can_manage_ministry_teams(user):
        return True

    # MINISTRY-ROLE-SOURCE.1C: team-management authority now comes from an
    # active lead/coordinator MinistryTeamRoleAssignment on this exact team, not
    # from TeamMembership.role. Membership remains candidate pool only.
    return user_has_active_ministry_management_role(user, team)


def can_manage_team_memberships(user, team):
    return can_manage_ministry_team(user, team)


def can_manage_team_assignments(user):
    return (
        getattr(user, "is_staff", False)
        or getattr(user, "is_superuser", False)
        or has_capability(user, CAP_MANAGE_TEAM_ASSIGNMENTS)
    )


def can_import_lighting_pilot(user):
    if not getattr(user, "is_authenticated", False):
        return False

    if getattr(user, "is_staff", False) or getattr(user, "is_superuser", False):
        return True

    return (
        has_capability(user, CAP_MANAGE_SERVICE_EVENTS)
        and has_capability(user, CAP_MANAGE_MINISTRY_TEAMS)
        and has_capability(user, CAP_MANAGE_TEAM_ASSIGNMENTS)
    )


def can_manage_team_assignment_for_team(user, team):
    if team is None or not getattr(user, "is_authenticated", False):
        return False

    if can_manage_team_assignments(user):
        return True

    return can_manage_ministry_team(user, team)


def can_view_team_assignment(user, assignment):
    if assignment is None or not getattr(user, "is_authenticated", False):
        return False

    if can_manage_team_assignment_for_team(user, assignment.ministry_team):
        return True

    return assignment.assignment_members.filter(
        membership__user=user,
        membership__is_active=True,
    ).exists()


def user_has_explicit_serving_assignment_for_event(user, event):
    """True when ``user`` has an active explicit ``TeamAssignmentMember`` serving
    assignment for exactly this ``ServiceEvent``.

    SERVING-EVENT-VISIBILITY.1A: the read-visibility grant predicate for a single
    ServiceEvent detail. Serving is explicit only and mirrors the My Serving /
    calendar 2A semantics: the signed-in user's own *active* team membership on an
    *active* team, a non-cancelled assignment, and a non-draft/non-cancelled
    ServiceEvent — scoped to this exact event. It never adds the user to the event
    audience, never grants visibility to any other event, and applies no
    staff/superuser/manager bypass (management visibility stays with
    ``ServiceEvent.can_be_managed_by``). It is intended only as an additional
    read gate for the event detail, layered beside ``ServiceEvent.can_be_seen_by``;
    the ordinary member-safe calendar/list audience visibility is unchanged and
    must not consult this helper.

    Fails closed for anonymous users, a missing event, and draft/cancelled events.
    When the ``ministry`` module is disabled it returns ``False`` and runs no
    serving query, so a disabled ministry never grants serving-based visibility.
    """
    if event is None or not getattr(user, "is_authenticated", False):
        return False

    # Draft/cancelled events never become visible through serving.
    if event.status in {event.STATUS_DRAFT, event.STATUS_CANCELLED}:
        return False

    # Disabled ministry grants no serving visibility and runs no serving query.
    if "ministry" not in get_enabled_module_keys():
        return False

    return (
        TeamAssignmentMember.objects.filter(
            membership__user=user,
            membership__is_active=True,
            membership__team__is_active=True,
            assignment__service_event=event,
        )
        .exclude(assignment__status=TeamAssignment.STATUS_CANCELLED)
        .exists()
    )


def can_confirm_team_assignment(user, assignment):
    if assignment is None or not getattr(user, "is_authenticated", False):
        return False

    if not assignment.is_confirmable():
        return False

    return assignment.assignment_members.filter(
        membership__user=user,
        membership__is_active=True,
    ).exists()
