from datetime import datetime, timedelta
from io import StringIO
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.utils.http import url_has_allowed_host_and_scheme

from accounts.language import get_user_language
from events.models import ServiceEvent

from .forms import (
    MinistryTeamForm,
    TeamAssignmentConfirmForm,
    TeamAssignmentForm,
    TeamScheduleAssignmentForm,
    TeamMembershipForm,
    assignment_form_text,
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
    can_import_lighting_pilot,
    can_view_ministry_team,
    can_view_team_assignment,
    user_team_memberships,
)
from .services.assignment_coverage import (
    assignment_member_prefetch,
    build_assignment_coverage,
    events_with_coverage_queryset,
)
from .services.copy_forward_suggestions import (
    MODE_ANCHOR,
    MODE_TEAM,
    VALID_MODES as COPY_FORWARD_MODES,
    find_copy_forward_suggestion,
)
from .services.lighting_pilot_import import (
    ImportStructureError,
    import_lighting_pilot,
    read_csv_file,
)


MY_SERVING_WEEK_DAYS = 7


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
            "event_not_available": "This service event is not available for this team schedule.",
            "duplicate_schedule_conflict": (
                "This event already has duplicate assignments for this team. "
                "Please clean up the duplicates before using a suggestion."
            ),
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
            "event_not_available": "这个聚会事件不适用于这个团队排班。",
            "duplicate_schedule_conflict": "这个聚会已经有重复的本团队排班。请先清理重复排班，再使用建议。",
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
            "service_event__host_language_unit",
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


def my_serving_assignments(user, tab="upcoming"):
    now = timezone.now()
    assignments = (
        TeamAssignmentMember.objects.select_related(
            "assignment",
            "assignment__service_event",
            "assignment__service_event__host_language_unit",
            "assignment__ministry_team",
            "membership",
            "membership__team",
            "membership__user",
        )
        .filter(
            membership__user=user,
            membership__is_active=True,
            membership__team__is_active=True,
        )
        .exclude(assignment__status=TeamAssignment.STATUS_CANCELLED)
        .exclude(
            assignment__service_event__status__in=[
                ServiceEvent.STATUS_DRAFT,
                ServiceEvent.STATUS_CANCELLED,
            ]
        )
    )

    if tab == "past":
        assignments = assignments.filter(assignment__service_event__start_datetime__lt=now)
    elif tab == "all":
        pass
    else:
        assignments = assignments.filter(assignment__service_event__start_datetime__gte=now)

    return assignments.order_by(
        "assignment__service_event__start_datetime",
        "assignment__ministry_team__name",
    )


def _local_midnight(date_value):
    local_timezone = timezone.get_current_timezone()
    midnight = datetime.combine(date_value, datetime.min.time())
    if timezone.is_naive(midnight):
        return timezone.make_aware(midnight, local_timezone)
    return midnight


def get_my_serving_windows():
    today = timezone.localdate()
    today_start = _local_midnight(today)
    tomorrow_start = _local_midnight(today + timedelta(days=1))
    week_end = _local_midnight(today + timedelta(days=1 + MY_SERVING_WEEK_DAYS))
    return today_start, tomorrow_start, week_end


def build_my_serving_sections(serving_items):
    today_start, tomorrow_start, week_end = get_my_serving_windows()
    sections = {
        "needs_attention": [],
        "today": [],
        "this_week": [],
        "later": [],
        "past": [],
    }

    for item in serving_items:
        starts_at = item.assignment.service_event.start_datetime
        if (
            starts_at >= today_start
            and not item.confirmed_at
            and item.assignment.is_confirmable()
        ):
            sections["needs_attention"].append(item)
        elif starts_at < today_start:
            sections["past"].append(item)
        elif starts_at < tomorrow_start:
            sections["today"].append(item)
        elif starts_at < week_end:
            sections["this_week"].append(item)
        else:
            sections["later"].append(item)

    return [
        {
            "key": "needs_attention",
            "items": sections["needs_attention"],
        },
        {
            "key": "today",
            "items": sections["today"],
        },
        {
            "key": "this_week",
            "items": sections["this_week"],
        },
        {
            "key": "later",
            "items": sections["later"],
        },
        {
            "key": "past",
            "items": sections["past"],
        },
    ]


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


def assignment_form_initial_from_query(request):
    initial = {}
    for field_name in ["service_event", "status", "notes"]:
        value = request.GET.get(field_name)
        if value:
            initial[field_name] = value
    return initial


def schedule_date_from_query(value, default):
    parsed = parse_date(value or "")
    return parsed or default


def schedule_filter_values(request):
    today = timezone.localdate()
    event_type = (request.GET.get("event_type") or "").strip()
    valid_event_types = {value for value, _label in ServiceEvent.EVENT_TYPE_CHOICES}
    if event_type and event_type not in valid_event_types:
        event_type = ""

    start_date = schedule_date_from_query(request.GET.get("start_date"), today)
    end_date = schedule_date_from_query(
        request.GET.get("end_date"),
        today + timezone.timedelta(weeks=8),
    )
    if start_date > end_date:
        end_date = start_date

    return {
        "event_type": event_type,
        "start_date": start_date,
        "end_date": end_date,
    }


def schedule_query_string(filters, **extra):
    params = {
        "start_date": filters["start_date"].isoformat(),
        "end_date": filters["end_date"].isoformat(),
    }
    if filters["event_type"]:
        params["event_type"] = filters["event_type"]
    for key, value in extra.items():
        if value:
            params[key] = value
    return urlencode(params)


def schedule_event_type_options(language):
    labels = {
        "en": {
            ServiceEvent.EVENT_SUNDAY_SERVICE: "Sunday Service",
            ServiceEvent.EVENT_BIBLE_STUDY: "Bible Study",
            ServiceEvent.EVENT_SPECIAL_MEETING: "Special Meeting",
            ServiceEvent.EVENT_CONFERENCE: "Conference",
            ServiceEvent.EVENT_GOSPEL_MUSIC: "Gospel Music Night",
            ServiceEvent.EVENT_BAPTISM: "Baptism",
            ServiceEvent.EVENT_OTHER: "Other",
        },
        "zh": {
            ServiceEvent.EVENT_SUNDAY_SERVICE: "主日崇拜",
            ServiceEvent.EVENT_BIBLE_STUDY: "查经",
            ServiceEvent.EVENT_SPECIAL_MEETING: "特别聚会",
            ServiceEvent.EVENT_CONFERENCE: "特会",
            ServiceEvent.EVENT_GOSPEL_MUSIC: "福音音乐会",
            ServiceEvent.EVENT_BAPTISM: "洗礼",
            ServiceEvent.EVENT_OTHER: "其他",
        },
    }.get(language, {})
    all_option = {
        "value": "",
        "label": "全部类型" if language == "zh" else "All event types",
    }
    return [all_option] + [
        {"value": value, "label": labels.get(value, label)}
        for value, label in ServiceEvent.EVENT_TYPE_CHOICES
    ]


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
            "can_import_lighting": can_import_lighting_pilot(request.user),
        },
    )


@login_required
def lighting_pilot_import(request):
    language = get_user_language(request)
    if not can_import_lighting_pilot(request.user):
        if language == "zh":
            messages.error(request, "你没有导入灯光组试点数据的权限。")
        else:
            messages.error(request, "You do not have permission to import Lighting pilot data.")
        return redirect("ministry_team_list")

    stats = None
    structure_error = ""
    dry_run = False
    if request.method == "POST":
        dry_run = "dry_run" in request.POST
        uploaded_file = request.FILES.get("csv_file")
        if not uploaded_file:
            structure_error = "CSV file is required."
        else:
            try:
                decoded_file = StringIO(uploaded_file.read().decode("utf-8-sig"))
                rows = read_csv_file(decoded_file)
                stats = import_lighting_pilot(rows, dry_run=dry_run)
            except UnicodeDecodeError:
                structure_error = "CSV file must be UTF-8 encoded."
            except ImportStructureError as exc:
                structure_error = str(exc)

    return render(
        request,
        "ministry/lighting_pilot_import.html",
        {
            "stats": stats,
            "structure_error": structure_error,
            "dry_run": dry_run,
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
            "can_schedule_team": can_manage_team_assignment_for_team(request.user, team),
        },
    )


@login_required
def team_schedule(request, team_id):
    language = get_user_language(request)
    team = get_object_or_404(MinistryTeam, id=team_id)

    if not can_manage_team_assignment_for_team(request.user, team):
        messages.error(request, ministry_ui_text(language, "no_assignment_permission"))
        return redirect("ministry_team_list")

    filters = schedule_filter_values(request)
    base_path = request.path
    event_filter = {
        "service_event__start_datetime__date__gte": filters["start_date"],
        "service_event__start_datetime__date__lte": filters["end_date"],
    }
    if filters["event_type"]:
        event_filter["service_event__event_type"] = filters["event_type"]
    assignments = list(
        TeamAssignment.objects.select_related(
            "service_event",
            "service_event__host_language_unit",
            "service_event__rotation_anchor_team",
            "ministry_team",
        )
        .prefetch_related(assignment_member_prefetch())
        .filter(ministry_team=team, **event_filter)
        .exclude(
            status__in=[
                TeamAssignment.STATUS_CANCELLED,
                TeamAssignment.STATUS_COMPLETED,
            ]
        )
        .order_by("service_event__start_datetime", "id")
    )
    assigned_event_ids = {assignment.service_event_id for assignment in assignments}
    event_filters = {
        "start_datetime__date__gte": filters["start_date"],
        "start_datetime__date__lte": filters["end_date"],
    }
    if filters["event_type"]:
        event_filters["event_type"] = filters["event_type"]
    event_queryset = (
        events_with_coverage_queryset()
        .filter(**event_filters)
        .exclude(
            status__in=[
                ServiceEvent.STATUS_DRAFT,
                ServiceEvent.STATUS_CANCELLED,
            ],
        )
        .filter(Q(required_team_links__ministry_team=team) | Q(id__in=assigned_event_ids))
        .distinct()
        .order_by("start_datetime", "title")
    )
    events = list(event_queryset)
    displayed_event_ids = {event.id for event in events}
    visible_assignment_ids = [assignment.id for assignment in assignments]
    coverage_by_event = build_assignment_coverage(
        events,
        assignments,
        language=language,
        allowed_team_ids=[team.id],
        allowed_assignment_ids=visible_assignment_ids,
    )

    assignments_by_event = {}
    for assignment in assignments:
        assignments_by_event.setdefault(assignment.service_event_id, []).append(assignment)

    active_assignment = None
    active_event = None
    action_error = False
    assignment_param = (request.GET.get("assignment") or "").strip()
    event_param = (request.GET.get("event") or "").strip()
    suggestion_mode = (request.GET.get("suggest") or "").strip()
    if suggestion_mode not in COPY_FORWARD_MODES:
        suggestion_mode = ""

    if assignment_param:
        try:
            assignment_id = int(assignment_param)
        except ValueError:
            assignment_id = None
        if assignment_id:
            active_assignment = next(
                (
                    assignment
                    for assignment in assignments
                    if assignment.id == assignment_id
                    and assignment.service_event_id in displayed_event_ids
                ),
                None,
            )
        action_error = active_assignment is None
    elif event_param:
        try:
            event_id = int(event_param)
        except ValueError:
            event_id = None
        if event_id and event_id in displayed_event_ids:
            active_assignment = next(iter(assignments_by_event.get(event_id, [])), None)
            if active_assignment is None:
                active_event = next(
                    (event for event in events if event.id == event_id),
                    None,
                )
        action_error = active_assignment is None and active_event is None and bool(event_param)

    if request.method == "POST" and action_error:
        messages.error(request, ministry_ui_text(language, "event_not_available"))
        return redirect(
            f"{base_path}?{schedule_query_string(filters)}"
        )

    active_form = None
    active_form_event = None
    active_form_assignment = active_assignment
    active_suggestion = None
    duplicate_suggestion_conflict = False
    if active_assignment is not None:
        active_form_event = active_assignment.service_event
        form_instance = active_assignment
    elif active_event is not None:
        duplicate_assignment = next(iter(assignments_by_event.get(active_event.id, [])), None)
        if duplicate_assignment is not None:
            active_form_assignment = duplicate_assignment
            active_form_event = duplicate_assignment.service_event
            form_instance = duplicate_assignment
        else:
            active_form_event = active_event
            form_instance = TeamAssignment(
                service_event=active_event,
                ministry_team=team,
                status=TeamAssignment.STATUS_SCHEDULED,
            )
    else:
        form_instance = None

    if form_instance is not None and suggestion_mode and active_form_event is not None:
        target_assignments = assignments_by_event.get(active_form_event.id, [])
        duplicate_suggestion_conflict = len(target_assignments) > 1
        if not duplicate_suggestion_conflict:
            active_suggestion = find_copy_forward_suggestion(
                active_form_event,
                team,
                suggestion_mode,
            )

    if form_instance is not None:
        if request.method == "POST":
            active_form = TeamScheduleAssignmentForm(
                request.POST,
                instance=form_instance,
                language=language,
                team=team,
            )
            if duplicate_suggestion_conflict:
                active_form.add_error(
                    None,
                    ministry_ui_text(language, "duplicate_schedule_conflict"),
                )
            if not duplicate_suggestion_conflict and active_form.is_valid():
                assignment = active_form.save(commit=False)
                assignment.service_event = active_form_event
                assignment.ministry_team = team
                if not assignment.pk:
                    assignment.created_by = request.user
                assignment.save()
                sync_assignment_members(
                    assignment,
                    active_form.cleaned_data["assigned_members"],
                )
                messages.success(request, ministry_ui_text(language, "assignment_saved"))
                return redirect(
                    f"{base_path}?{schedule_query_string(filters, assignment=assignment.id)}"
                )
        else:
            active_form = TeamScheduleAssignmentForm(
                instance=form_instance,
                language=language,
                team=team,
                suggestion_members=(
                    active_suggestion.source_members if active_suggestion else None
                ),
                suggestion_status=(
                    TeamAssignment.STATUS_SCHEDULED
                    if active_suggestion and not form_instance.pk
                    else None
                ),
            )

    schedule_rows = []
    for event in events:
        event_assignments = assignments_by_event.get(event.id, [])
        rows = coverage_by_event[event.id]["rows"]
        if not rows:
            continue
        assignment = event_assignments[0] if event_assignments else None
        anchor_suggestion = find_copy_forward_suggestion(event, team, MODE_ANCHOR)
        team_suggestion = find_copy_forward_suggestion(event, team, MODE_TEAM)
        schedule_rows.append(
            {
                "event": event,
                "coverage_rows": rows,
                "assignment": assignment,
                "action_url": (
                    f"{base_path}?{schedule_query_string(filters, assignment=assignment.id)}"
                    if assignment
                    else f"{base_path}?{schedule_query_string(filters, event=event.id)}"
                ),
                "anchor_suggestion": anchor_suggestion,
                "team_suggestion": team_suggestion,
                "anchor_suggestion_url": (
                    f"{base_path}?{schedule_query_string(filters, event=event.id, suggest=MODE_ANCHOR)}"
                    if anchor_suggestion
                    else ""
                ),
                "team_suggestion_url": (
                    f"{base_path}?{schedule_query_string(filters, event=event.id, suggest=MODE_TEAM)}"
                    if team_suggestion
                    else ""
                ),
                "is_active": (
                    bool(active_form_event)
                    and active_form_event.id == event.id
                ),
            }
        )

    return render(
        request,
        "ministry/team_schedule.html",
        {
            "team": team,
            "filters": filters,
            "event_type_options": schedule_event_type_options(language),
            "schedule_rows": schedule_rows,
            "active_form": active_form,
            "active_form_event": active_form_event,
            "active_form_assignment": active_form_assignment,
            "active_suggestion": active_suggestion,
            "duplicate_suggestion_conflict": duplicate_suggestion_conflict,
            "clear_action_url": f"{base_path}?{schedule_query_string(filters)}",
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
def my_serving(request):
    tab = (request.GET.get("tab") or "upcoming").strip()
    if tab not in {"upcoming", "past", "all"}:
        tab = "upcoming"

    serving_items = list(my_serving_assignments(request.user, tab=tab))
    pending_items = [
        item
        for item in serving_items
        if not item.confirmed_at and item.assignment.is_confirmable()
    ]
    scheduled_items = [
        item
        for item in serving_items
        if item.confirmed_at or not item.assignment.is_confirmable()
    ]
    serving_sections = build_my_serving_sections(serving_items)

    return render(
        request,
        "ministry/my_serving.html",
        {
            "serving_items": serving_items,
            "pending_items": pending_items,
            "scheduled_items": scheduled_items,
            "serving_sections": serving_sections,
            "manageable_teams": manageable_assignment_teams(request.user),
            "tab": tab,
            "confirm_form": TeamAssignmentConfirmForm(language=get_user_language(request)),
        },
    )


@login_required
def team_assignment_list(request):
    manageable_teams = manageable_assignment_teams(request.user)
    manageable_team_ids = list(manageable_teams.values_list("id", flat=True))
    can_create = bool(manageable_team_ids)
    can_show_new_assignment = can_create or can_manage_team_assignments(request.user)
    show_setup_actions = can_manage_team_assignments(request.user)
    tab = (request.GET.get("tab") or "upcoming").strip()
    if tab == "active":
        tab = "needs_confirmation"
    if tab not in {"upcoming", "needs_confirmation", "past", "cancelled"}:
        tab = "upcoming"

    now = timezone.now()
    assignments = visible_assignments_for_user(request.user)
    filter_teams = (
        MinistryTeam.objects.filter(assignments__in=assignments)
        .distinct()
        .order_by("name")
    )

    if tab == "past":
        assignments = assignments.filter(
            Q(service_event__start_datetime__lt=now)
            | Q(status=TeamAssignment.STATUS_COMPLETED)
        ).exclude(
            status=TeamAssignment.STATUS_CANCELLED,
        )
    elif tab == "needs_confirmation":
        assignments = assignments.exclude(
            status__in=[
                TeamAssignment.STATUS_CANCELLED,
                TeamAssignment.STATUS_COMPLETED,
            ]
        ).exclude(
            service_event__status__in=[
                ServiceEvent.STATUS_DRAFT,
                ServiceEvent.STATUS_CANCELLED,
            ]
        ).filter(
            assignment_members__membership__is_active=True,
            assignment_members__confirmed_at__isnull=True,
        ).distinct()
    elif tab == "cancelled":
        assignments = assignments.filter(status=TeamAssignment.STATUS_CANCELLED)
    else:
        assignments = assignments.filter(
            service_event__start_datetime__gte=now,
        ).exclude(
            service_event__status__in=[
                ServiceEvent.STATUS_DRAFT,
                ServiceEvent.STATUS_CANCELLED,
            ]
        ).exclude(
            status__in=[
                TeamAssignment.STATUS_CANCELLED,
                TeamAssignment.STATUS_COMPLETED,
            ],
        )

    status_filter = (request.GET.get("status") or "").strip()
    valid_statuses = {status for status, _label in TeamAssignment.STATUS_CHOICES}
    if status_filter in valid_statuses:
        assignments = assignments.filter(status=status_filter)
    else:
        status_filter = ""

    team_filter_id = None
    team_filter = (request.GET.get("team") or "").strip()
    if team_filter:
        try:
            team_filter_id = int(team_filter)
        except ValueError:
            team_filter_id = None
        if team_filter_id and filter_teams.filter(id=team_filter_id).exists():
            assignments = assignments.filter(ministry_team_id=team_filter_id)
        else:
            team_filter = ""
            team_filter_id = None

    visible_assignment_list = list(assignments)
    visible_assignment_ids = [assignment.id for assignment in visible_assignment_list]
    coverage_team_ids = None
    if not can_manage_team_assignments(request.user):
        coverage_team_ids = (
            manageable_team_ids
            if manageable_team_ids
            else sorted({assignment.ministry_team_id for assignment in visible_assignment_list})
        )
    if team_filter_id:
        if coverage_team_ids is None:
            coverage_team_ids = [team_filter_id]
        else:
            coverage_team_ids = [
                team_id for team_id in coverage_team_ids if team_id == team_filter_id
            ]

    event_ids = {assignment.service_event_id for assignment in visible_assignment_list}
    if tab == "upcoming" and not status_filter and (
        can_manage_team_assignments(request.user) or manageable_team_ids
    ):
        required_event_queryset = events_with_coverage_queryset().filter(
            start_datetime__gte=now,
        ).exclude(
            status__in=[
                "draft",
                "cancelled",
            ],
        )
        if coverage_team_ids is None:
            required_event_queryset = required_event_queryset.filter(
                required_team_links__isnull=False,
            )
        else:
            required_event_queryset = required_event_queryset.filter(
                required_team_links__ministry_team_id__in=coverage_team_ids,
            )
        event_ids.update(required_event_queryset.values_list("id", flat=True))

    events = list(
        events_with_coverage_queryset()
        .filter(id__in=event_ids)
        .order_by("start_datetime", "title")
    )
    coverage_by_event = build_assignment_coverage(
        events,
        visible_assignment_list,
        language=get_user_language(request),
        allowed_team_ids=coverage_team_ids,
        allowed_assignment_ids=visible_assignment_ids,
    )
    event_groups = [
        {
            "event": event,
            "coverage_rows": coverage_by_event[event.id]["rows"],
            "missing_count": coverage_by_event[event.id]["missing_count"],
        }
        for event in events
        if coverage_by_event[event.id]["rows"]
    ]

    status_text = assignment_form_text(get_user_language(request))
    status_filter_options = [
        {"value": TeamAssignment.STATUS_SCHEDULED, "label": status_text["scheduled"]},
        {"value": TeamAssignment.STATUS_CONFIRMED, "label": status_text["confirmed"]},
        {"value": TeamAssignment.STATUS_PREPARED, "label": status_text["prepared"]},
        {"value": TeamAssignment.STATUS_COMPLETED, "label": status_text["completed"]},
        {"value": TeamAssignment.STATUS_CANCELLED, "label": status_text["cancelled"]},
    ]

    return render(
        request,
        "ministry/assignment_list.html",
        {
            "assignments": assignments,
            "event_groups": event_groups,
            "tab": tab,
            "status_filter": status_filter,
            "team_filter": team_filter,
            "filter_teams": filter_teams,
            "status_filter_options": status_filter_options,
            "can_create": can_create,
            "can_show_new_assignment": can_show_new_assignment,
            "show_setup_actions": show_setup_actions,
            "can_import_lighting": can_import_lighting_pilot(request.user),
        },
    )


@login_required
def team_assignment_detail(request, assignment_id):
    language = get_user_language(request)
    assignment = get_object_or_404(
        TeamAssignment.objects.select_related(
            "service_event",
            "service_event__host_language_unit",
            "ministry_team",
            "created_by",
        ).prefetch_related(
            assignment_member_prefetch(),
            # SERVICE-EVENT-CONTEXT.1C: host/language label falls back to
            # audience-row-derived ministry context when host_language_unit is
            # blank; batch the audience rows.
            "service_event__audience_scope_links__unit",
        ),
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
    event = (
        events_with_coverage_queryset()
        .filter(id=assignment.service_event_id)
        .first()
    )
    coverage_team_ids = None
    if not can_manage_team_assignments(request.user):
        manageable_team_ids = list(
            manageable_assignment_teams(request.user).values_list("id", flat=True)
        )
        coverage_team_ids = manageable_team_ids or [assignment.ministry_team_id]
    event_coverage = build_assignment_coverage(
        [event],
        [assignment],
        language=language,
        allowed_team_ids=coverage_team_ids,
        allowed_assignment_ids=[assignment.id],
    )[event.id]

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
            "event_coverage": event_coverage,
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
        form = TeamAssignmentForm(
            initial=assignment_form_initial_from_query(request),
            language=language,
            manageable_teams=manageable_teams,
            selected_team_id=request.GET.get("ministry_team"),
        )

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
            initial=assignment_form_initial_from_query(request),
            instance=assignment,
            language=language,
            manageable_teams=manageable_teams,
            selected_team_id=request.GET.get("ministry_team"),
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

    if assignment_member is None:
        messages.error(request, ministry_ui_text(language, "assignment_not_available"))
        return redirect("team_assignment_detail", assignment_id=assignment.id)

    assignment_member.confirm(form.cleaned_data.get("confirmation_note", ""))
    if assignment.all_members_confirmed():
        assignment.status = TeamAssignment.STATUS_CONFIRMED
        assignment.save()

    messages.success(request, ministry_ui_text(language, "assignment_confirmed"))
    next_url = request.POST.get("next")
    if next_url and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(next_url)

    return redirect("team_assignment_detail", assignment_id=assignment.id)
