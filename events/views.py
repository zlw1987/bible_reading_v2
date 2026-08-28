from django.contrib import messages
from django.contrib.admin.models import CHANGE, LogEntry
from django.contrib.auth.decorators import login_required
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.http import require_http_methods, require_POST

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
    eligible_worship_team_candidates,
    inspect_worship_ownership_consistency,
)
from ministry.services.worship_change_notifications import (
    WorshipTeamChangeFact,
    emit_worship_team_change_notifications,
)
from ministry.services.worship_rotation_planner import (
    PlannerBlocker,
    SignedProposalError,
    WorshipRotationConfirmationError,
    build_worship_rotation_proposal,
    confirm_worship_rotation_proposal,
    decode_signed_worship_rotation_proposal,
)
from ministry.services.worship_xlsx_preview import (
    CONTRACT_REVISION,
    SUPPORTED_SHEET,
    MappingValidationError,
    PreviewBlocker,
    PreviewClassification,
    SignedWorkbookStateError,
    WorkbookContractError,
    WorkbookErrorCode,
    build_worship_import_preview,
    decode_parsed_workbook,
    mapping_candidate_teams,
    parse_known_worship_workbook,
    sign_parsed_workbook,
)

from .scheduling_revision import (
    SchedulingMutationStaleError,
    SchedulingRevisionError,
    advance_scheduling_revisions,
)

from .forms import (
    RecurringServiceEventForm,
    ServiceEventForm,
    ServiceEventPlannerAssignmentForm,
    WorshipRotationConfirmationForm,
    WorshipRotationPlannerForm,
    WorshipTeamSelectionForm,
    WorshipWorkbookMappingForm,
    WorshipWorkbookUploadForm,
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
            "scheduling_retry": (
                "Scheduling changed or is busy. Reload the current state and try again."
            ),
            "rotation_confirmation_retry": (
                "Scheduling changed or is busy. Generate a new preview and try again."
            ),
            "rotation_confirmation_saved": "Worship rotation updated.",
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
            "scheduling_retry": "排班资料已有变化或系统正忙。请刷新当前状态后重试。",
            "rotation_confirmation_retry": (
                "排班资料已有变化或系统正忙。请重新生成预览后再试。"
            ),
            "rotation_confirmation_saved": "敬拜轮值已更新。",
        },
    }
    return labels.get(language, labels["en"])[key]


def can_manage_service_events(user):
    return (
        getattr(user, "is_staff", False)
        or getattr(user, "is_superuser", False)
        or has_capability(user, CAP_MANAGE_SERVICE_EVENTS)
    )


def can_preview_worship_workbook(user):
    return bool(
        getattr(user, "is_authenticated", False)
        and getattr(user, "is_active", False)
        and (
            getattr(user, "is_staff", False)
            or getattr(user, "is_superuser", False)
        )
    )


def _validate_current_service_event_authority(user, _event):
    if not can_manage_service_events(user):
        raise SchedulingMutationStaleError(
            "Service-event management authority changed before the write."
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


def worship_rotation_planner_events_for_user(user):
    """Exact future Sunday choices bounded by existing per-event authority."""

    now = timezone.now()
    events = (
        ServiceEvent.objects.filter(
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
            status=ServiceEvent.STATUS_PUBLISHED,
            start_datetime__gt=now,
            start_datetime__lte=now
            + timezone.timedelta(days=WORSHIP_PLANNING_HORIZON_DAYS),
        )
        .select_related("rotation_anchor_team", "host_language_unit")
        .prefetch_related("audience_scope_links__unit")
        .order_by("start_datetime", "id")
    )
    return [
        event
        for event in events
        if timezone.localtime(event.start_datetime).weekday() == 6
        and can_change_worship_team(user, event)
    ]


def _planner_candidate_union(events):
    candidates_by_id = {}
    for event in events:
        for candidate in eligible_worship_team_candidates(event):
            candidates_by_id[candidate.team.pk] = candidate
    return tuple(
        sorted(
            candidates_by_id.values(),
            key=lambda item: (
                item.team.name,
                item.team.name_en,
                item.team.pk,
            ),
        )
    )


def _planner_blocker_text(language, blocker):
    labels = {
        "en": {
            PlannerBlocker.CHAIN_LENGTH: "Select between 2 and 53 exact events.",
            PlannerBlocker.DUPLICATE_EVENT: "Each exact event may appear only once.",
            PlannerBlocker.EVENT_NOT_FOUND: "One or more selected events are no longer available.",
            PlannerBlocker.INVALID_EVENT: "Every event must be a published future Sunday Service.",
            PlannerBlocker.NOT_SUNDAY: "Every selected event must start on a local Sunday.",
            PlannerBlocker.SAME_SUNDAY: "Choose exactly one event for each represented Sunday.",
            PlannerBlocker.WEEKLY_GAP: "The selected Sundays must be exactly seven days apart.",
            PlannerBlocker.INTERIOR_BLANK: "An interior Worship Team is blank; the shift cannot jump over it.",
            PlannerBlocker.INVALID_SOURCE: "The stored Worship Team is no longer valid for this event.",
            PlannerBlocker.DESTINATION_INELIGIBLE: "The proposed Worship Team is not eligible for this exact event.",
            PlannerBlocker.UNAUTHORIZED: "You cannot change the Worship Team for this exact event.",
            PlannerBlocker.WORSHIP_ASSIGNMENT: "Current Worship schedule blocks this change.",
            PlannerBlocker.OWNERSHIP_CONFLICT: "Current Worship ownership needs review before shifting.",
            PlannerBlocker.DISPLACED_TAIL: "A Worship Team would be displaced after the selected range.",
        },
        "zh": {
            PlannerBlocker.CHAIN_LENGTH: "请选择 2 至 53 场明确聚会。",
            PlannerBlocker.DUPLICATE_EVENT: "每场明确聚会只能出现一次。",
            PlannerBlocker.EVENT_NOT_FOUND: "一场或多场所选聚会已不可用。",
            PlannerBlocker.INVALID_EVENT: "每场聚会都必须是已发布且未来举行的主日崇拜。",
            PlannerBlocker.NOT_SUNDAY: "每场所选聚会都必须在本地星期日开始。",
            PlannerBlocker.SAME_SUNDAY: "每个所列主日只能明确选择一场聚会。",
            PlannerBlocker.WEEKLY_GAP: "所选主日之间必须正好相隔七天。",
            PlannerBlocker.INTERIOR_BLANK: "范围中间有空白敬拜团队，不能跨过空白顺延。",
            PlannerBlocker.INVALID_SOURCE: "当前保存的敬拜团队已不适用于这场聚会。",
            PlannerBlocker.DESTINATION_INELIGIBLE: "新安排的敬拜团队不适用于这场明确聚会。",
            PlannerBlocker.UNAUTHORIZED: "你无权更改这场明确聚会的敬拜团队。",
            PlannerBlocker.WORSHIP_ASSIGNMENT: "当前已有敬拜排班，无法顺延此项。",
            PlannerBlocker.OWNERSHIP_CONFLICT: "当前敬拜安排需要先检查，才能顺延。",
            PlannerBlocker.DISPLACED_TAIL: "范围结束后仍有一个敬拜团队被顺延出范围。",
        },
    }
    return labels.get(language, labels["en"])[blocker]


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
            try:
                with transaction.atomic():
                    event = form.save(commit=False)
                    event.save(
                        _post_scheduling_revision_validate=lambda current: (
                            _validate_current_service_event_authority(
                                request.user, current
                            )
                        )
                    )
                    event.required_teams.set(form.cleaned_data["required_teams"])
                    form.save_audience_units(event)
            except SchedulingRevisionError:
                form.add_error(None, event_ui_text(language, "scheduling_retry"))
            else:
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
    planner_events = worship_rotation_planner_events_for_user(request.user)
    return render(
        request,
        "events/worship_planning.html",
        {
            "planning_rows": worship_planning_rows(request.user, language),
            "rotation_planner_available": len(planner_events) >= 2,
            "worship_workbook_preview_available": can_preview_worship_workbook(
                request.user
            ),
        },
    )


def _workbook_error_text(language, error):
    labels = {
        "en": {
            WorkbookErrorCode.INVALID_XLSX: "Invalid XLSX workbook.",
            WorkbookErrorCode.ENCRYPTED_XLSX: (
                "Password-protected or encrypted workbooks are not supported."
            ),
            WorkbookErrorCode.CONTRACT_MISMATCH: (
                "Workbook contract mismatch. Use the supported 2026 master workbook."
            ),
            WorkbookErrorCode.SHEET_MISSING: "Required sheet 'All 930' is missing.",
            WorkbookErrorCode.HEADER_MISMATCH: (
                "Workbook title or operational headers do not match."
            ),
            WorkbookErrorCode.DATE_MISMATCH: (
                "A supported Sunday date does not match the frozen contract."
            ),
            WorkbookErrorCode.FORMULA_CACHE_MISMATCH: (
                "A formula-backed date or its cached result does not match."
            ),
            WorkbookErrorCode.UNSUPPORTED_TOKEN: (
                "A supported Sunday row has an unrecognized rotation token."
            ),
            WorkbookErrorCode.RESOURCE_LIMIT: (
                "The XLSX archive exceeds the supported resource limits."
            ),
        },
        "zh": {
            WorkbookErrorCode.INVALID_XLSX: "XLSX 工作簿无效。",
            WorkbookErrorCode.ENCRYPTED_XLSX: "不支持有密码或加密的工作簿。",
            WorkbookErrorCode.CONTRACT_MISMATCH: "工作簿结构不符合支持的 2026 总表。",
            WorkbookErrorCode.SHEET_MISSING: "缺少必需的“All 930”工作表。",
            WorkbookErrorCode.HEADER_MISMATCH: "工作簿标题或操作栏标题不符合要求。",
            WorkbookErrorCode.DATE_MISMATCH: "支持的主日日期不符合固定契约。",
            WorkbookErrorCode.FORMULA_CACHE_MISMATCH: "公式日期或其缓存结果不一致。",
            WorkbookErrorCode.UNSUPPORTED_TOKEN: "主日行包含不支持的轮值代码。",
            WorkbookErrorCode.RESOURCE_LIMIT: "XLSX 压缩包超过支持的资源上限。",
        },
    }
    base = labels.get(language, labels["en"])[error.code]
    return f"{base} {error.detail}" if language == "en" else base


def _workbook_row_labels(language, row):
    classification = {
        "en": {
            PreviewClassification.NO_OP: "No-op",
            PreviewClassification.PROPOSED_CHANGE: "Proposed change",
            PreviewClassification.BLOCKED: "Blocked",
        },
        "zh": {
            PreviewClassification.NO_OP: "无需更改",
            PreviewClassification.PROPOSED_CHANGE: "建议更改",
            PreviewClassification.BLOCKED: "已阻止",
        },
    }
    blockers = {
        "en": {
            PreviewBlocker.TARGET_MISSING: "No exact target event.",
            PreviewBlocker.TARGET_AMBIGUOUS: "Multiple exact target events.",
            PreviewBlocker.TARGET_LIFECYCLE: "Exact target is draft or cancelled.",
            PreviewBlocker.TARGET_AUDIENCE: "Exact target audience is not ready.",
            PreviewBlocker.MAPPING_UNRESOLVED: (
                "Mapping unresolved — select an eligible Worship Team."
            ),
            PreviewBlocker.TEAM_INELIGIBLE: (
                "Mapped team is not eligible for this exact event."
            ),
            PreviewBlocker.OWNERSHIP_CONFLICT: (
                "Current Worship ownership needs review."
            ),
            PreviewBlocker.CURRENT_WORSHIP_ASSIGNMENT: (
                "A current Worship assignment blocks an ordinary team change."
            ),
        },
        "zh": {
            PreviewBlocker.TARGET_MISSING: "没有完全匹配的目标聚会。",
            PreviewBlocker.TARGET_AMBIGUOUS: "存在多个完全匹配的目标聚会。",
            PreviewBlocker.TARGET_LIFECYCLE: "目标聚会是草稿或已取消。",
            PreviewBlocker.TARGET_AUDIENCE: "目标聚会的适用范围尚未就绪。",
            PreviewBlocker.MAPPING_UNRESOLVED: (
                "映射尚未完成——请选择符合条件的敬拜团队。"
            ),
            PreviewBlocker.TEAM_INELIGIBLE: "所选团队不适用于这场聚会。",
            PreviewBlocker.OWNERSHIP_CONFLICT: "当前敬拜归属需要检查。",
            PreviewBlocker.CURRENT_WORSHIP_ASSIGNMENT: "现有敬拜排班阻止一般团队更改。",
        },
    }
    return {
        "row": row,
        "classification_label": classification.get(language, classification["en"])[
            row.classification
        ],
        "blocker_label": (
            blockers.get(language, blockers["en"])[row.blocker]
            if row.blocker
            else ""
        ),
    }


def _workbook_preview_context(
    *, language, upload_form=None, parsed=None, mapping_form=None, preview=None
):
    mapping_rows = []
    if mapping_form is not None and parsed is not None:
        for token in parsed.token_counts:
            mapping_rows.append(
                {
                    "token": token,
                    "count": parsed.token_counts[token],
                    "field": mapping_form[f"mapping_{token.lower()}"],
                    "selected_team": (
                        preview.mappings.get(token) if preview is not None else None
                    ),
                }
            )
    return {
        "upload_form": upload_form
        or WorshipWorkbookUploadForm(language=language),
        "parsed": parsed,
        "mapping_form": mapping_form,
        "mapping_rows": mapping_rows,
        "preview": preview,
        "preview_rows": (
            [_workbook_row_labels(language, row) for row in preview.rows]
            if preview is not None
            else []
        ),
        "parser_contract": CONTRACT_REVISION,
        "supported_sheet": SUPPORTED_SHEET,
    }


@login_required
@require_http_methods(["GET", "POST"])
def worship_workbook_preview(request):
    """Staff/superuser-only, request-scoped, zero-write XLSX preview."""

    if not can_preview_worship_workbook(request.user):
        raise PermissionDenied
    language = get_user_language(request)
    if request.method == "GET":
        return render(
            request,
            "events/worship_workbook_preview.html",
            _workbook_preview_context(language=language),
        )

    if request.FILES:
        upload_form = WorshipWorkbookUploadForm(
            request.POST, request.FILES, language=language
        )
        if not upload_form.is_valid():
            return render(
                request,
                "events/worship_workbook_preview.html",
                _workbook_preview_context(
                    language=language, upload_form=upload_form
                ),
            )
        uploaded = upload_form.cleaned_data["workbook"]
        try:
            parsed = parse_known_worship_workbook(
                uploaded.read(), filename=uploaded.name
            )
        except WorkbookContractError as exc:
            upload_form.add_error("workbook", _workbook_error_text(language, exc))
            return render(
                request,
                "events/worship_workbook_preview.html",
                _workbook_preview_context(
                    language=language, upload_form=upload_form
                ),
            )
        signed_workbook = sign_parsed_workbook(parsed, user=request.user)
        candidate_teams = mapping_candidate_teams(parsed)
        mapping_form = WorshipWorkbookMappingForm(
            language=language,
            token_counts=parsed.token_counts,
            candidate_teams=candidate_teams,
            initial={"signed_workbook": signed_workbook},
        )
        return render(
            request,
            "events/worship_workbook_preview.html",
            _workbook_preview_context(
                language=language,
                upload_form=upload_form,
                parsed=parsed,
                mapping_form=mapping_form,
            ),
        )

    signed_workbook = request.POST.get("signed_workbook", "")
    try:
        parsed = decode_parsed_workbook(signed_workbook, user=request.user)
    except SignedWorkbookStateError:
        upload_form = WorshipWorkbookUploadForm(language=language)
        upload_form.add_error(
            None,
            "预览状态无效或已过期，请重新上传工作簿。"
            if language == "zh"
            else "Preview state is invalid or expired. Upload the workbook again.",
        )
        return render(
            request,
            "events/worship_workbook_preview.html",
            _workbook_preview_context(language=language, upload_form=upload_form),
        )

    candidate_teams = mapping_candidate_teams(parsed)
    mapping_form = WorshipWorkbookMappingForm(
        request.POST,
        language=language,
        token_counts=parsed.token_counts,
        candidate_teams=candidate_teams,
    )
    preview = None
    if mapping_form.is_valid():
        try:
            preview = build_worship_import_preview(
                parsed=parsed,
                mapping=mapping_form.selected_mapping(),
                user=request.user,
            )
        except MappingValidationError as exc:
            mapping_form.add_error(None, str(exc))
    return render(
        request,
        "events/worship_workbook_preview.html",
        _workbook_preview_context(
            language=language,
            parsed=parsed,
            mapping_form=mapping_form,
            preview=preview,
        ),
    )


@login_required
def worship_rotation_planner(request):
    language = get_user_language(request)
    available_events = worship_rotation_planner_events_for_user(request.user)
    candidates = _planner_candidate_union(available_events)
    proposal = None
    if request.method == "POST":
        form = WorshipRotationPlannerForm(
            request.POST,
            language=language,
            events=available_events,
            candidates=candidates,
        )
        if form.is_valid():
            proposal = build_worship_rotation_proposal(
                user=request.user,
                event_ids=[event.pk for event in form.cleaned_data["events"]],
                inserted_team=form.cleaned_data["inserted_team"],
            )
    else:
        form = WorshipRotationPlannerForm(
            language=language,
            events=available_events,
            candidates=candidates,
        )

    preview_rows = []
    proposal_blockers = []
    confirmation_form = None
    if proposal is not None:
        proposal_blockers = [
            _planner_blocker_text(language, blocker)
            for blocker in proposal.blockers
        ]
        preview_rows = [
            {
                "row": row,
                "blockers": [
                    _planner_blocker_text(language, blocker)
                    for blocker in row.blockers
                ],
            }
            for row in proposal.rows
        ]
        if proposal.confirmable:
            confirmation_form = WorshipRotationConfirmationForm(
                initial={"proposal": proposal.signed_payload}
            )

    return render(
        request,
        "events/worship_rotation_planner.html",
        {
            "form": form,
            "proposal": proposal,
            "proposal_blockers": proposal_blockers,
            "preview_rows": preview_rows,
            "available_events": available_events,
            "confirmation_form": confirmation_form,
        },
    )


@login_required
@require_POST
def worship_rotation_planner_confirm(request):
    language = get_user_language(request)
    form = WorshipRotationConfirmationForm(request.POST)
    if not form.is_valid():
        messages.error(
            request,
            event_ui_text(language, "rotation_confirmation_retry"),
        )
        return redirect("worship_rotation_planner")

    try:
        payload = decode_signed_worship_rotation_proposal(
            form.cleaned_data["proposal"],
            user=request.user,
        )
        confirm_worship_rotation_proposal(user=request.user, payload=payload)
    except (
        SignedProposalError,
        SchedulingRevisionError,
        WorshipRotationConfirmationError,
    ):
        messages.error(
            request,
            event_ui_text(language, "rotation_confirmation_retry"),
        )
        return redirect("worship_rotation_planner")

    messages.success(
        request,
        event_ui_text(language, "rotation_confirmation_saved"),
    )
    return redirect("worship_planning")


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

        baseline_updated_at = locked_event.updated_at
        baseline_anchor_team_id = locked_event.rotation_anchor_team_id
        baseline_revision = locked_event.scheduling_revision
        try:
            revision_result = advance_scheduling_revisions((locked_event.pk,))[0]
        except SchedulingRevisionError:
            messages.error(request, event_ui_text(language, "scheduling_retry"))
            transaction.set_rollback(True)
            return redirect(
                "change_worship_team", event_id=locked_event.pk
            )
        locked_event = (
            ServiceEvent.objects.select_for_update()
            .select_related("rotation_anchor_team")
            .prefetch_related("audience_scope_links__unit")
            .get(pk=locked_event.pk)
        )
        post_barrier_stale = (
            locked_event.updated_at != baseline_updated_at
            or locked_event.rotation_anchor_team_id != baseline_anchor_team_id
            or revision_result.revision != baseline_revision + 1
        )
        if post_barrier_stale:
            messages.error(request, event_ui_text(language, "worship_stale"))
            transaction.set_rollback(True)
            return redirect(
                "change_worship_team", event_id=locked_event.pk
            )

        if not can_change_worship_team(request.user, locked_event):
            transaction.set_rollback(True)
            messages.error(
                request, event_ui_text(language, "worship_not_available")
            )
            return redirect("service_event_list")

        inspection = inspect_worship_ownership_consistency(locked_event)
        eligible_team_ids = {
            candidate.team.pk for candidate in inspection.eligible_candidates
        }
        if proposed_team_id is not None and proposed_team_id not in eligible_team_ids:
            form.add_error(
                "worship_team",
                event_ui_text(language, "worship_not_available"),
            )
        elif inspection.current_worship_assignments:
            form.add_error(None, event_ui_text(language, "worship_conflict"))
        if form.errors:
            messages.error(request, event_ui_text(language, "worship_stale"))
            transaction.set_rollback(True)
            return redirect(
                "change_worship_team", event_id=locked_event.pk
            )

        old_team = locked_event.rotation_anchor_team
        locked_event.rotation_anchor_team = proposed_team
        locked_event.save(
            update_fields=["rotation_anchor_team", "updated_at"],
            _skip_scheduling_revision=True,
        )
        log_entry = LogEntry.objects.log_action(
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
        emit_worship_team_change_notifications(
            WorshipTeamChangeFact(
                event_id=locked_event.pk,
                event_start_datetime=locked_event.start_datetime,
                old_team_id=getattr(old_team, "pk", None),
                new_team_id=getattr(proposed_team, "pk", None),
            ),
            logentry_id=log_entry.pk,
            actor=request.user,
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

    try:
        with transaction.atomic():
            event.status = ServiceEvent.STATUS_CANCELLED
            event.save(
                update_fields=["status", "updated_at"],
                _post_scheduling_revision_validate=lambda current: (
                    _validate_current_service_event_authority(
                        request.user, current
                    )
                ),
            )
            cancel_non_final_assignments_for_event(event)
    except SchedulingRevisionError:
        messages.error(request, event_ui_text(language, "scheduling_retry"))
        return redirect("service_event_detail", event_id=event.id)
    messages.success(request, event_ui_text(language, "cancelled"))
    return redirect("service_event_list")
