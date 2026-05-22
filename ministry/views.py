from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from accounts.language import get_user_language

from .forms import MinistryTeamForm, TeamMembershipForm
from .models import MinistryTeam, TeamMembership
from .permissions import (
    can_manage_ministry_team,
    can_manage_ministry_teams,
    can_manage_team_memberships,
    can_view_ministry_team,
    user_team_memberships,
)


def ministry_ui_text(language, key):
    labels = {
        "en": {
            "no_permission": "You do not have permission to manage ministry teams.",
            "not_available": "This ministry team is not available.",
            "team_saved": "Ministry team saved.",
            "membership_saved": "Member saved.",
            "membership_deactivated": "Member deactivated.",
        },
        "zh": {
            "no_permission": "你没有管理事工团队的权限。",
            "not_available": "这个事工团队目前不可用。",
            "team_saved": "事工团队已保存。",
            "membership_saved": "成员已保存。",
            "membership_deactivated": "成员已停用。",
        },
    }
    return labels.get(language, labels["en"])[key]


def visible_teams_for_user(user):
    teams = MinistryTeam.objects.order_by("name")
    if can_manage_ministry_teams(user):
        return teams

    team_ids = user_team_memberships(user).values_list("team_id", flat=True)
    return teams.filter(id__in=team_ids, is_active=True)


@login_required
def ministry_team_list(request):
    can_manage = can_manage_ministry_teams(request.user)
    teams = visible_teams_for_user(request.user)

    return render(
        request,
        "ministry/team_list.html",
        {
            "teams": teams,
            "can_manage": can_manage,
        },
    )


@login_required
def ministry_team_detail(request, team_id):
    language = get_user_language(request)
    team = get_object_or_404(MinistryTeam, id=team_id)

    if not can_view_ministry_team(request.user, team):
        messages.error(request, ministry_ui_text(language, "not_available"))
        return redirect("ministry_team_list")

    memberships = (
        team.memberships.filter(is_active=True)
        .select_related("user")
        .order_by("role", "display_name")
    )

    return render(
        request,
        "ministry/team_detail.html",
        {
            "team": team,
            "memberships": memberships,
            "can_manage_team": can_manage_ministry_team(request.user, team),
            "can_manage_members": can_manage_team_memberships(request.user, team),
        },
    )


@login_required
def create_ministry_team(request):
    language = get_user_language(request)
    if not can_manage_ministry_teams(request.user):
        messages.error(request, ministry_ui_text(language, "no_permission"))
        return redirect("ministry_team_list")

    if request.method == "POST":
        form = MinistryTeamForm(request.POST, language=language)
        if form.is_valid():
            team = form.save()
            messages.success(request, ministry_ui_text(language, "team_saved"))
            return redirect("ministry_team_detail", team_id=team.id)
    else:
        form = MinistryTeamForm(language=language)

    return render(
        request,
        "ministry/team_form.html",
        {
            "form": form,
            "is_edit": False,
        },
    )


@login_required
def edit_ministry_team(request, team_id):
    language = get_user_language(request)
    team = get_object_or_404(MinistryTeam, id=team_id)

    if not can_manage_ministry_team(request.user, team):
        messages.error(request, ministry_ui_text(language, "no_permission"))
        return redirect("ministry_team_list")

    if request.method == "POST":
        form = MinistryTeamForm(request.POST, instance=team, language=language)
        if form.is_valid():
            team = form.save()
            messages.success(request, ministry_ui_text(language, "team_saved"))
            return redirect("ministry_team_detail", team_id=team.id)
    else:
        form = MinistryTeamForm(instance=team, language=language)

    return render(
        request,
        "ministry/team_form.html",
        {
            "team": team,
            "form": form,
            "is_edit": True,
        },
    )


@login_required
def manage_team_members(request, team_id):
    language = get_user_language(request)
    team = get_object_or_404(MinistryTeam, id=team_id)

    if not can_manage_team_memberships(request.user, team):
        messages.error(request, ministry_ui_text(language, "no_permission"))
        return redirect("ministry_team_list")

    if request.method == "POST":
        form = TeamMembershipForm(request.POST, language=language, team=team)
        if form.is_valid():
            membership = form.save(commit=False)
            membership.team = team
            membership.save()
            messages.success(request, ministry_ui_text(language, "membership_saved"))
            return redirect("manage_team_members", team_id=team.id)
    else:
        form = TeamMembershipForm(language=language, team=team)

    memberships = team.memberships.select_related("user").order_by(
        "-is_active",
        "role",
        "display_name",
    )

    return render(
        request,
        "ministry/manage_team_members.html",
        {
            "team": team,
            "memberships": memberships,
            "form": form,
        },
    )


@login_required
def edit_team_membership(request, membership_id):
    language = get_user_language(request)
    membership = get_object_or_404(
        TeamMembership.objects.select_related("team", "user"),
        id=membership_id,
    )

    if not can_manage_team_memberships(request.user, membership.team):
        messages.error(request, ministry_ui_text(language, "no_permission"))
        return redirect("ministry_team_list")

    if request.method == "POST":
        form = TeamMembershipForm(
            request.POST,
            instance=membership,
            language=language,
            team=membership.team,
        )
        if form.is_valid():
            membership = form.save()
            messages.success(request, ministry_ui_text(language, "membership_saved"))
            return redirect("manage_team_members", team_id=membership.team_id)
    else:
        form = TeamMembershipForm(
            instance=membership,
            language=language,
            team=membership.team,
        )

    return render(
        request,
        "ministry/membership_form.html",
        {
            "membership": membership,
            "team": membership.team,
            "form": form,
        },
    )


@login_required
def deactivate_team_membership(request, membership_id):
    language = get_user_language(request)
    membership = get_object_or_404(TeamMembership, id=membership_id)
    team_id = membership.team_id

    if not can_manage_team_memberships(request.user, membership.team):
        messages.error(request, ministry_ui_text(language, "no_permission"))
        return redirect("ministry_team_list")

    if request.method != "POST":
        return redirect("manage_team_members", team_id=team_id)

    membership.is_active = False
    membership.save()
    messages.success(request, ministry_ui_text(language, "membership_deactivated"))
    return redirect("manage_team_members", team_id=team_id)
