from accounts.permissions import (
    CAP_MANAGE_MINISTRY_TEAMS,
    CAP_MANAGE_TEAM_ASSIGNMENTS,
    has_capability,
)

from .models import TeamMembership


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

    return user_team_memberships(user).filter(team=team).filter(
        role__in=[
            TeamMembership.ROLE_LEAD,
            TeamMembership.ROLE_COORDINATOR,
        ]
    ).exists() or user_team_memberships(user).filter(team=team, can_lead=True).exists()


def can_manage_team_memberships(user, team):
    return can_manage_ministry_team(user, team)


def can_manage_team_assignments(user):
    return (
        getattr(user, "is_staff", False)
        or getattr(user, "is_superuser", False)
        or has_capability(user, CAP_MANAGE_TEAM_ASSIGNMENTS)
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


def can_confirm_team_assignment(user, assignment):
    if assignment is None or not getattr(user, "is_authenticated", False):
        return False

    return assignment.assignment_members.filter(
        membership__user=user,
        membership__is_active=True,
    ).exists()
