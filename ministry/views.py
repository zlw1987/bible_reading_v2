from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from accounts.language import get_user_language

from .forms import (
    MinistryTeamForm,
    TeamAssignmentConfirmForm,
    TeamAssignmentForm,
    TeamMembershipForm,
)
from .models import (
    MinistryTeam,
    TeamAssignment,
    TeamAssignmentMember,
    TeamMembership,
)
from .permissions import (
    can_manage_ministry_team,
    can_manage_ministry_teams,
    can_manage_team_assignment_for_team,
    can_manage_team_assignments,
    can_manage_team_memberships,
    can_confirm_team_assignment,
    can_view_ministry_team,
    can_view_team_assignment,
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
            "assignment_saved": "Team assignment saved.",
            "assignment_cancelled": "Team assignment cancelled.",
            "assignment_confirmed": "Team assignment confirmed.",
            "no_assignment_permission": "You do not have permission to manage team assignments.",
            "assignment_not_available": "This team assignment is not available.",
        },
        "zh": {
            "no_permission": "你没有管理事工团队的权限。",
            "not_available": "这个事工团队目前不可用。",
            "team_saved": "事工团队已保存。",
            "membership_saved": "成员已保存。",
            "membership_deactivated": "成员已停用。",
            "assignment_saved": "服事排班已保存。",
            "assignment_cancelled": "服事排班已取消。",
            "assignment_confirmed": "服事安排已确认。",
            "no_assignment_permission": "你没有管理服事排班的权限。",
            "assignment_not_available": "这个服事排班目前不可用。",
        },
    }
    return labels.get(language, labels["en"])[key]


def visible_teams_for_user(user):
    teams = MinistryTeam.objects.order_by("name")
    if can_manage_ministry_teams(user):
        return teams

    team_ids = user_team_memberships(user).values_list("team_id", flat=True)
    return teams.filter(id__in=team_ids, is_active=True)


def manageable_assignment_teams(user):
    teams = MinistryTeam.objects.order_by("name")
    if can_manage_team_assignments(user):
        return teams

    team_ids = [
        membership.team_id
        for membership in user_team_memberships(user)
        if membership.is_leadership()
    ]
    return teams.filter(id__in=team_ids, is_active=True)


def visible_assignments_for_user(user):
    assignments = (
        TeamAssignment.objects.select_related(
            "service_event",
            "ministry_team",
            "created_by",
        )
        .prefetch_related(
            "assignment_members",
            "assignment_members__membership",
            "assignment_members__membership__user",
        )
        .order_by("service_event__start_datetime", "ministry_team__name")
    )

    if can_manage_team_assignments(user):
        return assignments

    manageable_team_ids = manageable_assignment_teams(user).values_list("id", flat=True)
    return assignments.filter(
        Q(ministry_team_id__in=manageable_team_ids)
        | Q(
            assignment_members__membership__user=user,
            assignment_members__membership__is_active=True,
        )
    ).distinct()


def sync_assignment_members(assignment, memberships):
    selected_ids = {membership.id for membership in memberships}
    assignment.assignment_members.exclude(membership_id__in=selected_ids).delete()

    existing_ids = set(
        assignment.assignment_members.filter(membership_id__in=selected_ids)
        .values_list("membership_id", flat=True)
    )
    for membership in memberships:
        if membership.id not in existing_ids:
            TeamAssignmentMember.objects.create(
                assignment=assignment,
                membership=membership,
            )


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


@login_required
def team_assignment_list(request):
    can_create = manageable_assignment_teams(request.user).exists()
    tab = (request.GET.get("tab") or "upcoming").strip()
    if tab not in {"upcoming", "past", "active", "cancelled"}:
        tab = "upcoming"

    now = timezone.now()
    assignments = visible_assignments_for_user(request.user)

    if tab == "past":
        assignments = assignments.filter(service_event__start_datetime__lt=now).exclude(
            status=TeamAssignment.STATUS_CANCELLED,
        )
    elif tab == "active":
        assignments = assignments.exclude(status=TeamAssignment.STATUS_CANCELLED)
    elif tab == "cancelled":
        assignments = assignments.filter(status=TeamAssignment.STATUS_CANCELLED)
    else:
        assignments = assignments.filter(service_event__start_datetime__gte=now).exclude(
            status=TeamAssignment.STATUS_CANCELLED,
        )

    return render(
        request,
        "ministry/assignment_list.html",
        {
            "assignments": assignments,
            "tab": tab,
            "can_create": can_create,
        },
    )


@login_required
def team_assignment_detail(request, assignment_id):
    language = get_user_language(request)
    assignment = get_object_or_404(
        TeamAssignment.objects.select_related("service_event", "ministry_team", "created_by"),
        id=assignment_id,
    )

    if not can_view_team_assignment(request.user, assignment):
        messages.error(request, ministry_ui_text(language, "assignment_not_available"))
        return redirect("team_assignment_list")

    assignment_members = assignment.assignment_members.select_related(
        "membership",
        "membership__user",
    )
    user_assignment_member = assignment_members.filter(
        membership__user=request.user,
        membership__is_active=True,
    ).first()

    return render(
        request,
        "ministry/assignment_detail.html",
        {
            "assignment": assignment,
            "assignment_members": assignment_members,
            "can_manage_assignment": can_manage_team_assignment_for_team(
                request.user,
                assignment.ministry_team,
            ),
            "can_confirm_assignment": can_confirm_team_assignment(request.user, assignment),
            "user_assignment_member": user_assignment_member,
            "confirm_form": TeamAssignmentConfirmForm(language=language),
        },
    )


@login_required
def create_team_assignment(request):
    language = get_user_language(request)
    manageable_teams = manageable_assignment_teams(request.user)
    if not manageable_teams.exists():
        messages.error(request, ministry_ui_text(language, "no_assignment_permission"))
        return redirect("team_assignment_list")

    if request.method == "POST":
        form = TeamAssignmentForm(
            request.POST,
            language=language,
            manageable_teams=manageable_teams,
        )
        if form.is_valid():
            assignment = form.save(commit=False)
            assignment.created_by = request.user
            assignment.save()
            sync_assignment_members(assignment, form.cleaned_data["assigned_members"])
            messages.success(request, ministry_ui_text(language, "assignment_saved"))
            return redirect("team_assignment_detail", assignment_id=assignment.id)
    else:
        form = TeamAssignmentForm(language=language, manageable_teams=manageable_teams)

    return render(
        request,
        "ministry/assignment_form.html",
        {
            "form": form,
            "is_edit": False,
        },
    )


@login_required
def edit_team_assignment(request, assignment_id):
    language = get_user_language(request)
    assignment = get_object_or_404(TeamAssignment, id=assignment_id)
    manageable_teams = manageable_assignment_teams(request.user)

    if not can_manage_team_assignment_for_team(request.user, assignment.ministry_team):
        messages.error(request, ministry_ui_text(language, "no_assignment_permission"))
        return redirect("team_assignment_list")

    if request.method == "POST":
        form = TeamAssignmentForm(
            request.POST,
            instance=assignment,
            language=language,
            manageable_teams=manageable_teams,
        )
        if form.is_valid():
            assignment = form.save()
            sync_assignment_members(assignment, form.cleaned_data["assigned_members"])
            messages.success(request, ministry_ui_text(language, "assignment_saved"))
            return redirect("team_assignment_detail", assignment_id=assignment.id)
    else:
        form = TeamAssignmentForm(
            instance=assignment,
            language=language,
            manageable_teams=manageable_teams,
        )

    return render(
        request,
        "ministry/assignment_form.html",
        {
            "assignment": assignment,
            "form": form,
            "is_edit": True,
        },
    )


@login_required
def cancel_team_assignment(request, assignment_id):
    language = get_user_language(request)
    assignment = get_object_or_404(TeamAssignment, id=assignment_id)

    if not can_manage_team_assignment_for_team(request.user, assignment.ministry_team):
        messages.error(request, ministry_ui_text(language, "no_assignment_permission"))
        return redirect("team_assignment_list")

    if request.method != "POST":
        return redirect("team_assignment_detail", assignment_id=assignment.id)

    assignment.status = TeamAssignment.STATUS_CANCELLED
    assignment.save()
    messages.success(request, ministry_ui_text(language, "assignment_cancelled"))
    return redirect("team_assignment_detail", assignment_id=assignment.id)


@login_required
def confirm_team_assignment(request, assignment_id):
    language = get_user_language(request)
    assignment = get_object_or_404(TeamAssignment, id=assignment_id)

    if request.method != "POST":
        return redirect("team_assignment_detail", assignment_id=assignment.id)

    if not can_confirm_team_assignment(request.user, assignment):
        messages.error(request, ministry_ui_text(language, "assignment_not_available"))
        return redirect("team_assignment_list")

    form = TeamAssignmentConfirmForm(request.POST, language=language)
    if not form.is_valid():
        return redirect("team_assignment_detail", assignment_id=assignment.id)

    assignment_member = assignment.assignment_members.filter(
        membership__user=request.user,
        membership__is_active=True,
    ).first()
    if assignment_member is None and can_manage_team_assignment_for_team(
        request.user,
        assignment.ministry_team,
    ):
        assignment_member = assignment.assignment_members.filter(
            membership__is_active=True,
            confirmed_at__isnull=True,
        ).first()

    if assignment_member is None:
        messages.error(request, ministry_ui_text(language, "assignment_not_available"))
        return redirect("team_assignment_detail", assignment_id=assignment.id)

    assignment_member.confirm(form.cleaned_data.get("confirmation_note", ""))
    if assignment.all_members_confirmed():
        assignment.status = TeamAssignment.STATUS_CONFIRMED
        assignment.save()

    messages.success(request, ministry_ui_text(language, "assignment_confirmed"))
    return redirect("team_assignment_detail", assignment_id=assignment.id)
