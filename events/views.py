from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from accounts.language import get_user_language
from accounts.permissions import CAP_MANAGE_SERVICE_EVENTS, has_capability

from .forms import RecurringServiceEventForm, ServiceEventForm
from .models import ServiceEvent


def event_ui_text(language, key):
    labels = {
        "en": {
            "no_permission": "You do not have permission to manage service events.",
            "not_available": "This service event is not available.",
            "saved": "Service event saved.",
            "cancelled": "Service event cancelled.",
        },
        "zh": {
            "no_permission": "你没有管理聚会事件的权限。",
            "not_available": "这个聚会事件目前不可用。",
            "saved": "聚会事件已保存。",
            "cancelled": "聚会事件已取消。",
        },
    }
    return labels.get(language, labels["en"])[key]


def can_manage_service_events(user):
    return (
        getattr(user, "is_staff", False)
        or getattr(user, "is_superuser", False)
        or has_capability(user, CAP_MANAGE_SERVICE_EVENTS)
    )


def get_visible_service_events(user):
    events = ServiceEvent.objects.select_related(
        "district",
        "ministry_context",
        "small_group",
        "created_by",
    ).order_by("-start_datetime")

    if can_manage_service_events(user):
        return events

    visible_ids = [event.id for event in events if event.can_be_seen_by(user)]
    return events.filter(id__in=visible_ids)


@login_required
def service_event_list(request):
    can_manage = can_manage_service_events(request.user)
    tab = (request.GET.get("tab") or "upcoming").strip()

    if tab not in {"upcoming", "past", "drafts"}:
        tab = "upcoming"
    if tab == "drafts" and not can_manage:
        tab = "upcoming"

    now = timezone.now()
    events = get_visible_service_events(request.user)

    if tab == "past":
        events = events.filter(start_datetime__lt=now).exclude(
            status=ServiceEvent.STATUS_DRAFT,
        )
    elif tab == "drafts":
        events = events.filter(status=ServiceEvent.STATUS_DRAFT)
    else:
        events = events.filter(start_datetime__gte=now).exclude(
            status__in=[ServiceEvent.STATUS_DRAFT, ServiceEvent.STATUS_CANCELLED]
        )

    return render(
        request,
        "events/service_event_list.html",
        {
            "events": events,
            "tab": tab,
            "can_manage": can_manage,
        },
    )


@login_required
def service_event_detail(request, event_id):
    event = get_object_or_404(
        ServiceEvent.objects.select_related(
            "district",
            "ministry_context",
            "small_group",
            "created_by",
        ).prefetch_related("required_teams"),
        id=event_id,
    )

    if not event.can_be_seen_by(request.user):
        messages.error(
            request,
            event_ui_text(get_user_language(request), "not_available"),
        )
        return redirect("service_event_list")

    return render(
        request,
        "events/service_event_detail.html",
        {
            "event": event,
            "can_manage": can_manage_service_events(request.user),
            "required_teams": event.required_teams.all().order_by("name"),
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
            event = form.save(commit=False)
            event.created_by = request.user
            event.save()
            event.required_teams.set(form.cleaned_data["required_teams"])
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
                "scope_type": cleaned_data["scope_type"],
                "district": cleaned_data.get("district"),
                "small_group": cleaned_data.get("small_group"),
            }
            if ServiceEvent.objects.filter(**duplicate_filter).exists():
                dates_to_skip.append(current_date)
            else:
                dates_to_create.append(current_date)
        current_date += timezone.timedelta(days=1)

    return dates_to_create, dates_to_skip


def create_recurring_events(cleaned_data, user):
    dates_to_create, dates_to_skip = build_recurring_event_preview(cleaned_data)
    created_count = 0
    required_teams = cleaned_data.get("required_teams")

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
            scope_type=cleaned_data["scope_type"],
            district=cleaned_data.get("district"),
            small_group=cleaned_data.get("small_group"),
            status=cleaned_data["status"],
            created_by=user,
        )
        event.required_teams.set(required_teams)
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
            event = form.save(commit=False)
            event.save()
            event.required_teams.set(form.cleaned_data["required_teams"])
            messages.success(request, event_ui_text(language, "saved"))
            return redirect("service_event_detail", event_id=event.id)
    else:
        form = ServiceEventForm(instance=event, language=language)

    return render(
        request,
        "events/service_event_form.html",
        {
            "event": event,
            "form": form,
            "is_edit": True,
        },
    )


@login_required
def cancel_service_event(request, event_id):
    language = get_user_language(request)
    event = get_object_or_404(ServiceEvent, id=event_id)

    if not can_manage_service_events(request.user):
        messages.error(request, event_ui_text(language, "no_permission"))
        return redirect("service_event_list")

    if request.method != "POST":
        return redirect("service_event_detail", event_id=event.id)

    event.status = ServiceEvent.STATUS_CANCELLED
    event.save()
    messages.success(request, event_ui_text(language, "cancelled"))
    return redirect("service_event_list")
