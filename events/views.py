from django.contrib import messages
from django.contrib.admin.models import CHANGE, LogEntry
from django.contrib.auth.decorators import login_required
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from accounts.language import get_user_language
from accounts.permissions import CAP_MANAGE_SERVICE_EVENTS, has_capability
from ministry.models import TeamAssignment
from ministry.permissions import (
    can_change_worship_team,
    can_manage_team_assignments,
    user_has_explicit_serving_assignment_for_event,
)
from ministry.services.assignment_coverage import (
    assignment_coverage_queryset,
    build_assignment_coverage,
    events_with_coverage_queryset,
)
from ministry.services.worship_governance import (
    WorshipOwnershipConsistencyState,
    inspect_worship_ownership_consistency,
)

from .forms import (
    RecurringServiceEventForm,
    ServiceEventForm,
    ServiceEventPlannerAssignmentForm,
    WorshipTeamSelectionForm,
)
from .models import (
    ServiceEvent,
    ServiceEventPlannerAssignment,
    current_service_event_planner_assignments,
    service_event_is_history,
)


WORSHIP_PLANNING_HORIZON_DAYS = 548


def cancel_non_final_assignments_for_event(event):
    return TeamAssignment.objects.filter(
        service_event=event,
        status__in=[
            TeamAssignment.STATUS_SCHEDULED,
            TeamAssignment.STATUS_PREPARED,
            TeamAssignment.STATUS_CONFIRMED,
        ],
    ).update(
        status=TeamAssignment.STATUS_CANCELLED,
        updated_at=timezone.now(),
    )


def event_ui_text(language, key):
    labels = {
        "en": {
            "no_permission": "You do not have permission to manage service events.",
            "not_available": "This service event is not available.",
            "saved": "Service event saved.",
            "cancelled": "Service event cancelled.",
            "planner_added": "Service planner responsibility added.",
            "planner_ended": "Service planner responsibility ended.",
            "planner_restored": "Service planner responsibility restored.",
            "planner_already_ended": "This planner responsibility is already ended.",
            "planner_already_active": "This planner responsibility is already active.",
            "planner_inactive_user": (
                "An inactive user cannot hold current planner responsibility."
            ),
            "worship_not_available": "This Worship planning action is not available.",
            "worship_saved": "Worship Team updated.",
            "worship_unchanged": "The Worship Team is unchanged.",
            "worship_stale": (
                "This event changed after you opened the form. Refresh and review "
                "the current Worship Team before trying again."
            ),
            "worship_conflict": (
                "Worship has already been scheduled for this event. Resolve or "
                "cancel the existing Worship assignment before changing the "
                "Worship Team."
            ),
        },
        "zh": {
            "no_permission": "你没有管理聚会事件的权限。",
            "not_available": "这个聚会事件目前不可用。",
            "saved": "聚会事件已保存。",
            "cancelled": "聚会事件已取消。",
            "planner_added": "已添加聚会安排责任。",
            "planner_ended": "已结束聚会安排责任。",
            "planner_restored": "已恢复聚会安排责任。",
            "planner_already_ended": "这项聚会安排责任已经结束。",
            "planner_already_active": "这项聚会安排责任目前有效。",
            "planner_inactive_user": "停用用户不能承担当前聚会安排责任。",
            "worship_not_available": "这项敬拜安排目前不可用。",
            "worship_saved": "敬拜团队已更新。",
            "worship_unchanged": "敬拜团队没有更改。",
            "worship_stale": "你打开表单后，这场聚会已有更改。请刷新并核对当前敬拜团队后再试。",
            "worship_conflict": (
                "这场聚会已经安排了敬拜服事。请先处理或取消现有敬拜排班，"
                "再更改敬拜团队。"
            ),
        },
    }
    return labels.get(language, labels["en"])[key]


def can_manage_service_events(user):
    return (
        getattr(user, "is_staff", False)
        or getattr(user, "is_superuser", False)
        or has_capability(user, CAP_MANAGE_SERVICE_EVENTS)
    )


def _service_event_edit_context(event, language, user, planner_form=None):
    return {
        "event": event,
        "form": ServiceEventForm(instance=event, language=language),
        "is_edit": True,
        "planner_form": planner_form
        or ServiceEventPlannerAssignmentForm(
            service_event=event,
            language=language,
        ),
        "current_planner_assignments": current_service_event_planner_assignments(
            event
        ),
        "noncurrent_planner_assignments": (
            ServiceEventPlannerAssignment.objects.filter(service_event=event)
            .filter(Q(is_active=False) | Q(user__is_active=False))
            .select_related("user")
            .order_by("user__username", "id")
        ),
        "can_change_worship_team": can_change_worship_team(user, event),
    }


def get_visible_service_events(user):
    events = ServiceEvent.objects.select_related(
        "host_language_unit",
        "rotation_anchor_team",
        "created_by",
    ).prefetch_related(
        # SE-AS.4: can_be_seen_by reads audience scope rows per event; the
        # prefetch keeps the per-user visibility pass to a fixed query count.
        "audience_scope_links__unit",
    ).order_by("start_datetime", "id")

    if can_manage_service_events(user):
        return events

    visible_ids = [event.id for event in events if event.can_be_seen_by(user)]
    return events.filter(id__in=visible_ids)


def worship_planning_events_for_user(user):
    """Return the bounded, narrow event set for current Worship planning."""

    now = timezone.now()
    horizon = now + timezone.timedelta(days=WORSHIP_PLANNING_HORIZON_DAYS)
    events = (
        ServiceEvent.objects.select_related("rotation_anchor_team")
        .prefetch_related("audience_scope_links__unit")
        .exclude(status=ServiceEvent.STATUS_CANCELLED)
        .filter(start_datetime__lte=horizon)
        .filter(
            Q(end_datetime__gte=now)
            | Q(
                end_datetime__isnull=True,
                start_datetime__date__gte=timezone.localdate(),
            )
        )
        .order_by("start_datetime", "id")
    )
    return [
        event
        for event in events
        if not service_event_is_history(event, now=now)
        and can_change_worship_team(user, event)
    ]


def worship_consistency_label(language, state):
    labels = {
        "en": {
            WorshipOwnershipConsistencyState.NO_SELECTION: (
                "Worship Team not selected"
            ),
            WorshipOwnershipConsistencyState.SELECTED_UNSCHEDULED: (
                "Selected but not yet scheduled"
            ),
            WorshipOwnershipConsistencyState.CONSISTENT: "Scheduled",
            WorshipOwnershipConsistencyState.INVALID_SELECTION: "Review required",
            WorshipOwnershipConsistencyState.OFF_TEAM_CONFLICT: "Review required",
            WorshipOwnershipConsistencyState.OUT_OF_SCOPE_WORSHIP_CONFLICT: (
                "Review required"
            ),
            WorshipOwnershipConsistencyState.MULTIPLE_CURRENT_WORSHIP_ASSIGNMENTS: (
                "Review required"
            ),
            WorshipOwnershipConsistencyState.DUPLICATE_SELECTED_TEAM_ASSIGNMENT: (
                "Review required"
            ),
        },
        "zh": {
            WorshipOwnershipConsistencyState.NO_SELECTION: "尚未选择敬拜团队",
            WorshipOwnershipConsistencyState.SELECTED_UNSCHEDULED: "已选择，尚未排班",
            WorshipOwnershipConsistencyState.CONSISTENT: "已排班",
            WorshipOwnershipConsistencyState.INVALID_SELECTION: "需要检查",
            WorshipOwnershipConsistencyState.OFF_TEAM_CONFLICT: "需要检查",
            WorshipOwnershipConsistencyState.OUT_OF_SCOPE_WORSHIP_CONFLICT: "需要检查",
            WorshipOwnershipConsistencyState.MULTIPLE_CURRENT_WORSHIP_ASSIGNMENTS: "需要检查",
            WorshipOwnershipConsistencyState.DUPLICATE_SELECTED_TEAM_ASSIGNMENT: "需要检查",
        },
    }
    return labels.get(language, labels["en"])[state]


def worship_planning_rows(user, language):
    rows = []
    for event in worship_planning_events_for_user(user):
        inspection = inspect_worship_ownership_consistency(event)
        rows.append(
            {
                "event": event,
                "inspection": inspection,
                "consistency_label": worship_consistency_label(
                    language, inspection.state
                ),
            }
        )
    return rows


@login_required
def service_event_list(request):
    can_manage = can_manage_service_events(request.user)
    has_worship_planning = bool(
        worship_planning_events_for_user(request.user)
    )
    tab = (request.GET.get("tab") or "upcoming").strip()

    if tab not in {"upcoming", "past", "drafts"}:
        tab = "upcoming"
    if tab == "drafts" and not can_manage:
        tab = "upcoming"

    now = timezone.now()
    events = get_visible_service_events(request.user)

    if tab == "past":
        events = sorted(
            [
                event
                for event in events.exclude(
                    status__in=[
                        ServiceEvent.STATUS_DRAFT,
                        ServiceEvent.STATUS_CANCELLED,
                    ],
                )
                if service_event_is_history(event, now=now)
            ],
            key=lambda event: (-event.start_datetime.timestamp(), event.id),
        )
    elif tab == "drafts":
        events = events.filter(status=ServiceEvent.STATUS_DRAFT).order_by(
            "start_datetime",
            "id",
        )
    else:
        events = sorted(
            [
                event
                for event in events.exclude(
                    status__in=[
                        ServiceEvent.STATUS_DRAFT,
                        ServiceEvent.STATUS_CANCELLED,
                    ],
                )
                if not service_event_is_history(event, now=now)
            ],
            key=lambda event: (event.start_datetime, event.id),
        )

    return render(
        request,
        "events/service_event_list.html",
        {
            "events": events,
            "tab": tab,
            "can_manage": can_manage,
            "has_worship_planning": has_worship_planning,
        },
    )


@login_required
def service_event_detail(request, event_id):
    event = get_object_or_404(
        events_with_coverage_queryset().prefetch_related(
            "required_teams",
            "audience_scope_links__unit",
        ),
        id=event_id,
    )

    # SERVING-EVENT-VISIBILITY.1A: ordinary discovery stays audience-only via
    # can_be_seen_by; an explicit team-serving assignment additionally grants
    # read-only serving-context visibility to *this specific* event detail (never
    # audience membership, never other events, never management authority).
    if not (
        event.can_be_seen_by(request.user)
        or user_has_explicit_serving_assignment_for_event(request.user, event)
    ):
        messages.error(
            request,
            event_ui_text(get_user_language(request), "not_available"),
        )
        return redirect("service_event_list")

    can_manage = can_manage_service_events(request.user)
    can_view_coverage = can_manage or can_manage_team_assignments(request.user)
    event_coverage = None
    if can_view_coverage:
        assignments = assignment_coverage_queryset().filter(service_event=event)
        event_coverage = build_assignment_coverage(
            [event],
            list(assignments),
            language=get_user_language(request),
        )[event.id]

    return render(
        request,
        "events/service_event_detail.html",
        {
            "event": event,
            "can_manage": can_manage,
            "required_teams": event.required_teams.all().order_by("name"),
            "can_view_coverage": can_view_coverage,
            "event_coverage": event_coverage,
            "can_change_worship_team": can_change_worship_team(
                request.user, event
            ),
        },
    )


@login_required
def create_service_event(request):
    language = get_user_language(request)
    if not can_manage_service_events(request.user):
        messages.error(request, event_ui_text(language, "no_permission"))
        return redirect("service_event_list")

    if request.method == "POST":
        form = ServiceEventForm(request.POST, language=language)
        if form.is_valid():
            with transaction.atomic():
                event = form.save(commit=False)
                event.created_by = request.user
                event.save()
                event.required_teams.set(form.cleaned_data["required_teams"])
                form.save_audience_units(event)
            messages.success(request, event_ui_text(language, "saved"))
            return redirect("service_event_detail", event_id=event.id)
    else:
        form = ServiceEventForm(language=language)

    return render(
        request,
        "events/service_event_form.html",
        {
            "form": form,
            "is_edit": False,
        },
    )


def build_recurring_event_preview(cleaned_data):
    dates_to_create = []
    dates_to_skip = []
    current_date = cleaned_data["start_date"]
    end_date = cleaned_data["end_date"]
    weekday = int(cleaned_data["weekday"])

    while current_date <= end_date:
        if current_date.weekday() == weekday:
            start_datetime = timezone.make_aware(
                timezone.datetime.combine(current_date, cleaned_data["start_time"]),
                timezone.get_current_timezone(),
            )
            duplicate_filter = {
                "start_datetime": start_datetime,
                "event_type": cleaned_data["event_type"],
                "title": cleaned_data["title"],
            }
            if (
                ServiceEvent.objects.filter(**duplicate_filter)
                .exclude(status=ServiceEvent.STATUS_CANCELLED)
                .exists()
            ):
                dates_to_skip.append(current_date)
            else:
                dates_to_create.append(current_date)
        current_date += timezone.timedelta(days=1)

    return dates_to_create, dates_to_skip


def create_recurring_events(cleaned_data, user):
    dates_to_create, dates_to_skip = build_recurring_event_preview(cleaned_data)
    created_count = 0
    required_teams = cleaned_data.get("required_teams")
    # SE-SCOPE.1A/SE-CTX.1A: recurring app creates use structure audience rows
    # only. Legacy scope/context fields remain at model defaults.
    audience_units = list(cleaned_data.get("audience_units") or [])

    with transaction.atomic():
        for event_date in dates_to_create:
            start_datetime = timezone.make_aware(
                timezone.datetime.combine(event_date, cleaned_data["start_time"]),
                timezone.get_current_timezone(),
            )
            end_datetime = None
            if cleaned_data.get("end_time"):
                end_datetime = timezone.make_aware(
                    timezone.datetime.combine(event_date, cleaned_data["end_time"]),
                    timezone.get_current_timezone(),
                )
            event = ServiceEvent.objects.create(
                title=cleaned_data["title"],
                title_en=cleaned_data.get("title_en") or "",
                description=cleaned_data.get("description") or "",
                description_en=cleaned_data.get("description_en") or "",
                event_type=cleaned_data["event_type"],
                start_datetime=start_datetime,
                end_datetime=end_datetime,
                location=cleaned_data.get("location") or "",
                meeting_link=cleaned_data.get("meeting_link") or "",
                status=cleaned_data["status"],
                created_by=user,
            )
            event.required_teams.set(required_teams)
            if audience_units:
                for unit in audience_units:
                    event.audience_scope_links.create(unit=unit)
            created_count += 1

    return created_count, len(dates_to_skip), dates_to_create, dates_to_skip


@login_required
def create_recurring_service_events(request):
    language = get_user_language(request)
    if not can_manage_service_events(request.user):
        messages.error(request, event_ui_text(language, "no_permission"))
        return redirect("service_event_list")

    preview = None
    if request.method == "POST":
        form = RecurringServiceEventForm(request.POST, language=language)
        if form.is_valid():
            if "preview" in request.POST:
                dates_to_create, dates_to_skip = build_recurring_event_preview(
                    form.cleaned_data
                )
                preview = {
                    "dates_to_create": dates_to_create,
                    "dates_to_skip": dates_to_skip,
                    "total_count": len(dates_to_create),
                }
            elif "create" in request.POST:
                created_count, skipped_count, dates_to_create, dates_to_skip = (
                    create_recurring_events(form.cleaned_data, request.user)
                )
                messages.success(
                    request,
                    f"Created: {created_count}; skipped: {skipped_count}.",
                )
                preview = {
                    "dates_to_create": dates_to_create,
                    "dates_to_skip": dates_to_skip,
                    "total_count": created_count,
                }
    else:
        form = RecurringServiceEventForm(language=language)

    return render(
        request,
        "events/recurring_service_event_form.html",
        {
            "form": form,
            "preview": preview,
        },
    )


@login_required
def edit_service_event(request, event_id):
    language = get_user_language(request)
    event = get_object_or_404(ServiceEvent, id=event_id)

    if not can_manage_service_events(request.user):
        messages.error(request, event_ui_text(language, "no_permission"))
        return redirect("service_event_list")

    if request.method == "POST":
        form = ServiceEventForm(request.POST, instance=event, language=language)
        if form.is_valid():
            with transaction.atomic():
                event = form.save(commit=False)
                event.save()
                event.required_teams.set(form.cleaned_data["required_teams"])
                form.save_audience_units(event)
            messages.success(request, event_ui_text(language, "saved"))
            return redirect("service_event_detail", event_id=event.id)
    else:
        form = ServiceEventForm(instance=event, language=language)

    return render(
        request,
        "events/service_event_form.html",
        {
            **_service_event_edit_context(event, language, request.user),
            "form": form,
        },
    )


def _worship_selector_context(event, language, inspection, form):
    return {
        "event": event,
        "inspection": inspection,
        "form": form,
        "consistency_label": worship_consistency_label(
            language, inspection.state
        ),
        "change_blocked": bool(inspection.current_worship_assignments),
    }


def _expected_event_timestamp_matches(raw_value, current_value):
    expected = parse_datetime(raw_value or "")
    if expected is None:
        return False
    if timezone.is_naive(expected):
        expected = timezone.make_aware(
            expected, timezone.get_current_timezone()
        )
    return expected == current_value


@login_required
def worship_planning(request):
    language = get_user_language(request)
    return render(
        request,
        "events/worship_planning.html",
        {"planning_rows": worship_planning_rows(request.user, language)},
    )


@login_required
def change_worship_team(request, event_id):
    language = get_user_language(request)
    event = get_object_or_404(
        ServiceEvent.objects.select_related("rotation_anchor_team").prefetch_related(
            "audience_scope_links__unit"
        ),
        id=event_id,
    )
    if not can_change_worship_team(request.user, event):
        messages.error(
            request, event_ui_text(language, "worship_not_available")
        )
        return redirect("service_event_list")

    if request.method != "POST":
        inspection = inspect_worship_ownership_consistency(event)
        form = WorshipTeamSelectionForm(
            language=language,
            candidates=inspection.eligible_candidates,
            initial={
                "worship_team": event.rotation_anchor_team_id,
                "expected_updated_at": event.updated_at.isoformat(),
                "expected_anchor_team": event.rotation_anchor_team_id or "",
            },
        )
        return render(
            request,
            "events/worship_team_form.html",
            _worship_selector_context(event, language, inspection, form),
        )

    with transaction.atomic():
        locked_event = (
            ServiceEvent.objects.select_for_update()
            .select_related("rotation_anchor_team")
            .prefetch_related("audience_scope_links__unit")
            .get(id=event.id)
        )
        if not can_change_worship_team(request.user, locked_event):
            messages.error(
                request, event_ui_text(language, "worship_not_available")
            )
            return redirect("service_event_list")

        inspection = inspect_worship_ownership_consistency(locked_event)
        form = WorshipTeamSelectionForm(
            request.POST,
            language=language,
            candidates=inspection.eligible_candidates,
        )
        expected_anchor = request.POST.get("expected_anchor_team", "")
        current_anchor = str(locked_event.rotation_anchor_team_id or "")
        stale = (
            not _expected_event_timestamp_matches(
                request.POST.get("expected_updated_at"),
                locked_event.updated_at,
            )
            or expected_anchor != current_anchor
        )
        if stale:
            form.add_error(
                None, event_ui_text(language, "worship_stale")
            )
            return render(
                request,
                "events/worship_team_form.html",
                _worship_selector_context(
                    locked_event, language, inspection, form
                ),
            )

        if not form.is_valid():
            return render(
                request,
                "events/worship_team_form.html",
                _worship_selector_context(
                    locked_event, language, inspection, form
                ),
            )

        proposed_team = form.cleaned_data["worship_team"]
        proposed_team_id = proposed_team.pk if proposed_team else None
        if proposed_team_id == locked_event.rotation_anchor_team_id:
            messages.success(
                request, event_ui_text(language, "worship_unchanged")
            )
            return redirect("change_worship_team", event_id=locked_event.id)

        eligible_team_ids = {
            candidate.team.pk for candidate in inspection.eligible_candidates
        }
        if proposed_team_id is not None and proposed_team_id not in eligible_team_ids:
            form.add_error(
                "worship_team",
                event_ui_text(language, "worship_not_available"),
            )
        elif inspection.current_worship_assignments:
            form.add_error(
                None, event_ui_text(language, "worship_conflict")
            )

        if form.errors:
            return render(
                request,
                "events/worship_team_form.html",
                _worship_selector_context(
                    locked_event, language, inspection, form
                ),
            )

        old_team = locked_event.rotation_anchor_team
        locked_event.rotation_anchor_team = proposed_team
        locked_event.save(
            update_fields=["rotation_anchor_team", "updated_at"]
        )
        LogEntry.objects.log_action(
            user_id=request.user.pk,
            content_type_id=ContentType.objects.get_for_model(
                ServiceEvent
            ).pk,
            object_id=locked_event.pk,
            object_repr=str(locked_event),
            action_flag=CHANGE,
            change_message=(
                "Changed Worship Team via governed exact-event selector "
                "(MO-S.6D-1D-B). "
                f"old_team_id={getattr(old_team, 'pk', None)!r}; "
                f"old_team={getattr(old_team, 'name', None)!r}; "
                f"new_team_id={getattr(proposed_team, 'pk', None)!r}; "
                f"new_team={getattr(proposed_team, 'name', None)!r}."
            ),
        )

    messages.success(request, event_ui_text(language, "worship_saved"))
    return redirect("change_worship_team", event_id=event.id)


@login_required
def add_service_event_planner(request, event_id):
    language = get_user_language(request)
    event = get_object_or_404(ServiceEvent, id=event_id)
    if not can_manage_service_events(request.user):
        messages.error(request, event_ui_text(language, "no_permission"))
        return redirect("service_event_list")
    if request.method != "POST":
        return redirect("edit_service_event", event_id=event.id)

    with transaction.atomic():
        event = ServiceEvent.objects.select_for_update().get(id=event.id)
        if not can_manage_service_events(request.user):
            messages.error(request, event_ui_text(language, "no_permission"))
            return redirect("service_event_list")
        planner_form = ServiceEventPlannerAssignmentForm(
            request.POST,
            service_event=event,
            language=language,
        )
        if planner_form.is_valid():
            planner_form.save()
            messages.success(
                request,
                event_ui_text(language, "planner_added"),
            )
            return redirect("edit_service_event", event_id=event.id)

    return render(
        request,
        "events/service_event_form.html",
        _service_event_edit_context(
            event,
            language,
            request.user,
            planner_form=planner_form,
        ),
        status=200,
    )


@login_required
def end_service_event_planner(request, event_id, assignment_id):
    language = get_user_language(request)
    event = get_object_or_404(ServiceEvent, id=event_id)
    if not can_manage_service_events(request.user):
        messages.error(request, event_ui_text(language, "no_permission"))
        return redirect("service_event_list")
    if request.method != "POST":
        return redirect("edit_service_event", event_id=event_id)

    with transaction.atomic():
        event = ServiceEvent.objects.select_for_update().get(id=event.id)
        if not can_manage_service_events(request.user):
            messages.error(request, event_ui_text(language, "no_permission"))
            return redirect("service_event_list")
        assignment = get_object_or_404(
            ServiceEventPlannerAssignment.objects.select_for_update().select_related(
                "user",
            ),
            id=assignment_id,
            service_event=event,
        )
        if not assignment.is_active:
            messages.error(
                request,
                event_ui_text(language, "planner_already_ended"),
            )
        else:
            assignment.is_active = False
            assignment.save(update_fields=["is_active", "updated_at"])
            messages.success(
                request,
                event_ui_text(language, "planner_ended"),
            )
    return redirect("edit_service_event", event_id=event_id)


@login_required
def restore_service_event_planner(request, event_id, assignment_id):
    language = get_user_language(request)
    event = get_object_or_404(ServiceEvent, id=event_id)
    if not can_manage_service_events(request.user):
        messages.error(request, event_ui_text(language, "no_permission"))
        return redirect("service_event_list")
    if request.method != "POST":
        return redirect("edit_service_event", event_id=event_id)

    with transaction.atomic():
        event = ServiceEvent.objects.select_for_update().get(id=event.id)
        if not can_manage_service_events(request.user):
            messages.error(request, event_ui_text(language, "no_permission"))
            return redirect("service_event_list")
        assignment = get_object_or_404(
            ServiceEventPlannerAssignment.objects.select_for_update().select_related(
                "user",
            ),
            id=assignment_id,
            service_event=event,
        )
        if assignment.is_active:
            messages.error(
                request,
                event_ui_text(language, "planner_already_active"),
            )
        elif not assignment.user.is_active:
            messages.error(
                request,
                event_ui_text(language, "planner_inactive_user"),
            )
        else:
            assignment.is_active = True
            assignment.save(update_fields=["is_active", "updated_at"])
            messages.success(
                request,
                event_ui_text(language, "planner_restored"),
            )
    return redirect("edit_service_event", event_id=event_id)


@login_required
def cancel_service_event(request, event_id):
    language = get_user_language(request)
    event = get_object_or_404(ServiceEvent, id=event_id)

    if not can_manage_service_events(request.user):
        messages.error(request, event_ui_text(language, "no_permission"))
        return redirect("service_event_list")

    if request.method != "POST":
        return redirect("service_event_detail", event_id=event.id)

    with transaction.atomic():
        event.status = ServiceEvent.STATUS_CANCELLED
        event.save(update_fields=["status", "updated_at"])
        cancel_non_final_assignments_for_event(event)
    messages.success(request, event_ui_text(language, "cancelled"))
    return redirect("service_event_list")
