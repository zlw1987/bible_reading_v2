from collections import defaultdict

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db.models import Max
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme

from accounts.language import get_user_language
from accounts.models import SmallGroup
from comments.forms import ReflectionCommentForm
from comments.models import ReflectionComment

from .bible_sources import parse_memory_verse_text, parse_reading_text
from .models import ActivePlan, CheckIn, PlanEnrollment, ReadingPlanDay


def get_safe_next_url(request):
    next_url = request.POST.get("next") or request.GET.get("next")

    if next_url and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
    ):
        return next_url

    return None


def get_scripture_language(request):
    lang = request.GET.get("lang") or get_user_language(request)

    if lang not in {"zh", "en"}:
        return "zh"

    return lang


def build_reader_context(
    request,
    *,
    active_plan,
    plan_day,
    passage,
    passage_index,
    passages,
    reader_url_name,
    reader_title,
    source_label,
    show_completion_section,
):
    selected_language = get_scripture_language(request)

    if selected_language == "en":
        selected_text_url = passage["text_url_en"]
        selected_display = passage["display_en"]
    else:
        selected_text_url = passage["text_url_zh"]
        selected_display = passage["display_zh"]

    previous_index = passage_index - 1 if passage_index > 0 else None
    next_index = passage_index + 1 if passage_index < len(passages) - 1 else None

    context = {
        "reader_title": reader_title,
        "source_label": source_label,
        "active_plan": active_plan,
        "plan_day": plan_day,
        "passage": passage,
        "passage_index": passage_index,
        "previous_index": previous_index,
        "next_index": next_index,
        "has_previous": previous_index is not None,
        "has_next": next_index is not None,
        "is_last_passage": next_index is None,
        "reader_url_name": reader_url_name,
        "show_completion_section": show_completion_section,
        "selected_language": selected_language,
        "selected_text_url": selected_text_url,
        "selected_display": selected_display,
    }

    if show_completion_section:
        current_day_number = active_plan.current_day_number()
        context.update(
            {
                "is_future_day": plan_day.day_number > current_day_number,
                "is_checked": CheckIn.objects.filter(
                    user=request.user,
                    active_plan=active_plan,
                    plan_day=plan_day,
                ).exists(),
                "comments": (
                    ReflectionComment.objects.filter(
                        plan_day=plan_day,
                        parent__isnull=True,
                    )
                    .select_related("user")
                    .prefetch_related("replies", "replies__user")
                ),
                "comment_form": ReflectionCommentForm(),
                "reply_form": ReflectionCommentForm(),
            }
        )

    return context


@login_required
def home(request):
    enrollments = (
        PlanEnrollment.objects.filter(user=request.user)
        .select_related("active_plan", "active_plan__plan")
        .order_by("-joined_at")
    )

    joined_active_plan_ids = enrollments.values_list("active_plan_id", flat=True)

    active_plans = (
        ActivePlan.objects.select_related("plan")
        .filter(plan__is_active=True)
        .exclude(id__in=joined_active_plan_ids)
        .order_by("-start_date")
    )

    today_items = []

    for enrollment in enrollments:
        active_plan = enrollment.active_plan
        current_day_number = active_plan.current_day_number()

        plan_days = list(
            ReadingPlanDay.objects.filter(plan=active_plan.plan).order_by("day_number")
        )

        total_reading_days = len(plan_days)
        max_day_number = max([day.day_number for day in plan_days], default=0)

        checked_days = CheckIn.objects.filter(
            user=request.user,
            active_plan=active_plan,
        ).count()

        progress_percent = (
            round((checked_days / total_reading_days) * 100)
            if total_reading_days
            else 0
        )

        plan_day = None
        passages = []
        memory_passages = []
        is_checked = False

        is_not_started = current_day_number < 1
        is_ended = bool(max_day_number and current_day_number > max_day_number)
        is_rest_day = False
        is_reading_day = False

        if not is_not_started and not is_ended:
            plan_day = next(
                (day for day in plan_days if day.day_number == current_day_number),
                None,
            )

            if plan_day:
                is_reading_day = True
                passages = parse_reading_text(plan_day.reading_text)
                memory_passages = (
                    parse_memory_verse_text(plan_day.memory_verse)
                    if plan_day.memory_verse
                    else []
                )
                is_checked = CheckIn.objects.filter(
                    user=request.user,
                    active_plan=active_plan,
                    plan_day=plan_day,
                ).exists()
            else:
                is_rest_day = True

        today_items.append(
            {
                "active_plan": active_plan,
                "current_day_number": current_day_number,
                "max_day_number": max_day_number,
                "plan_day": plan_day,
                "passages": passages,
                "memory_passages": memory_passages,
                "is_checked": is_checked,
                "is_not_started": is_not_started,
                "is_ended": is_ended,
                "is_rest_day": is_rest_day,
                "is_reading_day": is_reading_day,
                "checked_days": checked_days,
                "total_reading_days": total_reading_days,
                "progress_percent": progress_percent,
            }
        )

    return render(
        request,
        "reading/home.html",
        {
            "active_plans": active_plans,
            "today_items": today_items,
        },
    )


@login_required
def active_plan_detail(request, active_plan_id):
    active_plan = get_object_or_404(
        ActivePlan.objects.select_related("plan"),
        id=active_plan_id,
    )

    is_enrolled = PlanEnrollment.objects.filter(
        user=request.user,
        active_plan=active_plan,
    ).exists()

    if not is_enrolled:
        messages.error(request, "You need to join this plan before viewing it.")
        return redirect("home")

    plan_days = list(
        ReadingPlanDay.objects.filter(plan=active_plan.plan).order_by("day_number")
    )
    plan_day_by_number = {day.day_number: day for day in plan_days}

    max_day_number = max(plan_day_by_number.keys(), default=0)
    current_day_number = active_plan.current_day_number()

    checked_plan_day_ids = set(
        CheckIn.objects.filter(user=request.user, active_plan=active_plan).values_list(
            "plan_day_id", flat=True
        )
    )

    day_items = []

    for day_number in range(1, max_day_number + 1):
        plan_day = plan_day_by_number.get(day_number)
        calendar_date = active_plan.start_date + timezone.timedelta(days=day_number - 1)

        day_items.append(
            {
                "day_number": day_number,
                "plan_day": plan_day,
                "calendar_date": calendar_date,
                "passages": parse_reading_text(plan_day.reading_text) if plan_day else [],
                "memory_passages": (
                    parse_memory_verse_text(plan_day.memory_verse)
                    if plan_day and plan_day.memory_verse
                    else []
                ),
                "is_checked": bool(plan_day and plan_day.id in checked_plan_day_ids),
                "is_today": day_number == current_day_number,
                "is_future": day_number > current_day_number,
                "is_rest_day": plan_day is None,
                "is_reading_day": plan_day is not None,
            }
        )

    total_reading_days = len(plan_days)
    total_calendar_days = max_day_number
    rest_days = total_calendar_days - total_reading_days
    checked_days = len(checked_plan_day_ids)
    progress_percent = (
        round((checked_days / total_reading_days) * 100)
        if total_reading_days
        else 0
    )

    return render(
        request,
        "reading/active_plan_detail.html",
        {
            "active_plan": active_plan,
            "day_items": day_items,
            "total_reading_days": total_reading_days,
            "total_calendar_days": total_calendar_days,
            "rest_days": rest_days,
            "checked_days": checked_days,
            "progress_percent": progress_percent,
        },
    )


@login_required
def join_active_plan(request, active_plan_id):
    if request.method != "POST":
        return redirect("home")

    active_plan = get_object_or_404(ActivePlan, id=active_plan_id)

    enrollment, created = PlanEnrollment.objects.get_or_create(
        user=request.user,
        active_plan=active_plan,
    )

    if created:
        messages.success(request, "You joined the reading plan.")
    else:
        messages.info(request, "You have already joined this plan.")

    return redirect("home")


@login_required
def passage_reader(request, active_plan_id, plan_day_id, passage_index):
    active_plan = get_object_or_404(
        ActivePlan.objects.select_related("plan"),
        id=active_plan_id,
    )
    plan_day = get_object_or_404(
        ReadingPlanDay,
        id=plan_day_id,
        plan=active_plan.plan,
    )

    if not PlanEnrollment.objects.filter(user=request.user, active_plan=active_plan).exists():
        messages.error(request, "You need to join this plan before reading it.")
        return redirect("home")

    passages = parse_reading_text(plan_day.reading_text)

    if passage_index < 0 or passage_index >= len(passages):
        messages.error(request, "This scripture passage could not be found.")
        return redirect("active_plan_detail", active_plan_id=active_plan.id)

    context = build_reader_context(
        request,
        active_plan=active_plan,
        plan_day=plan_day,
        passage=passages[passage_index],
        passage_index=passage_index,
        passages=passages,
        reader_url_name="passage_reader",
        reader_title="scripture_reader",
        source_label="reading",
        show_completion_section=True,
    )
    return render(request, "reading/passage_reader.html", context)


@login_required
def memory_verse_reader(request, active_plan_id, plan_day_id, passage_index):
    active_plan = get_object_or_404(
        ActivePlan.objects.select_related("plan"),
        id=active_plan_id,
    )
    plan_day = get_object_or_404(
        ReadingPlanDay,
        id=plan_day_id,
        plan=active_plan.plan,
    )

    if not PlanEnrollment.objects.filter(user=request.user, active_plan=active_plan).exists():
        messages.error(request, "You need to join this plan before reading it.")
        return redirect("home")

    passages = parse_memory_verse_text(plan_day.memory_verse)

    if passage_index < 0 or passage_index >= len(passages):
        messages.error(request, "This memory verse could not be found.")
        return redirect("active_plan_detail", active_plan_id=active_plan.id)

    context = build_reader_context(
        request,
        active_plan=active_plan,
        plan_day=plan_day,
        passage=passages[passage_index],
        passage_index=passage_index,
        passages=passages,
        reader_url_name="memory_verse_reader",
        reader_title="memory_verse",
        source_label="memory_verse",
        show_completion_section=False,
    )
    return render(request, "reading/passage_reader.html", context)


@login_required
def check_in(request, active_plan_id, plan_day_id):
    if request.method != "POST":
        return redirect("home")

    active_plan = get_object_or_404(
        ActivePlan.objects.select_related("plan"),
        id=active_plan_id,
    )
    plan_day = get_object_or_404(
        ReadingPlanDay,
        id=plan_day_id,
        plan=active_plan.plan,
    )

    safe_next_url = get_safe_next_url(request)

    if not PlanEnrollment.objects.filter(user=request.user, active_plan=active_plan).exists():
        messages.error(request, "You need to join this plan before checking in.")
        return redirect("home")

    current_day_number = active_plan.current_day_number()

    if plan_day.day_number > current_day_number:
        messages.error(request, "You cannot check in for a future reading day.")
        if safe_next_url:
            return redirect(safe_next_url)
        return redirect("active_plan_detail", active_plan_id=active_plan.id)

    checkin, created = CheckIn.objects.get_or_create(
        user=request.user,
        active_plan=active_plan,
        plan_day=plan_day,
    )

    if created:
        messages.success(request, "Check-in completed.")
    else:
        messages.info(request, "You have already checked in for this reading.")

    if safe_next_url:
        return redirect(safe_next_url)

    return redirect("active_plan_detail", active_plan_id=active_plan.id)


@login_required
def my_group_progress(request):
    User = get_user_model()
    user_profile = getattr(request.user, "profile", None)
    groups = SmallGroup.objects.filter(is_active=True).order_by("name")

    selected_group = None

    if request.user.is_staff:
        group_id = request.GET.get("group")

        if group_id:
            selected_group = groups.filter(id=group_id).first()

        if selected_group is None:
            selected_group = (
                user_profile.small_group
                if user_profile and user_profile.small_group
                else groups.first()
            )
    else:
        selected_group = user_profile.small_group if user_profile else None

    if selected_group is None:
        return render(
            request,
            "reading/group_progress.html",
            {
                "selected_group": None,
                "selected_group_id": None,
                "groups": groups,
                "active_plans": [],
                "selected_active_plan": None,
                "selected_active_plan_id": None,
                "member_rows": [],
                "message": "You are not assigned to a small group yet.",
            },
        )

    group_members = User.objects.filter(profile__small_group=selected_group).order_by(
        "username"
    )

    active_plans = (
        ActivePlan.objects.filter(
            plan__is_active=True,
            enrollments__user__in=group_members,
        )
        .select_related("plan")
        .distinct()
        .order_by("-start_date")
    )

    active_plan_id = request.GET.get("active_plan")
    selected_active_plan = None

    if active_plan_id:
        selected_active_plan = active_plans.filter(id=active_plan_id).first()

    if selected_active_plan is None:
        selected_active_plan = active_plans.first()

    if selected_active_plan is None:
        return render(
            request,
            "reading/group_progress.html",
            {
                "selected_group": selected_group,
                "selected_group_id": selected_group.id if selected_group else None,
                "groups": groups,
                "active_plans": active_plans,
                "selected_active_plan": None,
                "selected_active_plan_id": None,
                "member_rows": [],
                "message": "No active reading plan has been joined by this group yet.",
            },
        )

    plan_days = list(
        ReadingPlanDay.objects.filter(plan=selected_active_plan.plan).order_by(
            "day_number"
        )
    )
    total_days = len(plan_days)
    current_day_number = selected_active_plan.current_day_number()
    today_plan_day = next(
        (day for day in plan_days if day.day_number == current_day_number),
        None,
    )

    enrolled_user_ids = set(
        PlanEnrollment.objects.filter(
            active_plan=selected_active_plan,
            user__in=group_members,
        ).values_list("user_id", flat=True)
    )

    checked_by_user = defaultdict(set)
    checkins = CheckIn.objects.filter(
        active_plan=selected_active_plan,
        user__in=group_members,
    ).values_list("user_id", "plan_day_id")

    for user_id, plan_day_id in checkins:
        checked_by_user[user_id].add(plan_day_id)

    member_rows = []

    for member in group_members:
        is_enrolled = member.id in enrolled_user_ids

        if is_enrolled:
            checked_day_ids = checked_by_user.get(member.id, set())
            checked_days = len(checked_day_ids)
        else:
            checked_day_ids = set()
            checked_days = 0

        progress_percent = round((checked_days / total_days) * 100) if total_days else 0

        if not is_enrolled:
            today_status = "Not joined"
        elif today_plan_day is None:
            today_status = "No reading today"
        elif today_plan_day.id in checked_day_ids:
            today_status = "Checked"
        elif current_day_number < 1:
            today_status = "Not started"
        elif current_day_number > total_days:
            today_status = "Plan ended"
        else:
            today_status = "Missing"

        member_rows.append(
            {
                "member": member,
                "is_enrolled": is_enrolled,
                "today_status": today_status,
                "checked_days": checked_days,
                "total_days": total_days,
                "progress_percent": progress_percent,
            }
        )

    return render(
        request,
        "reading/group_progress.html",
        {
            "selected_group": selected_group,
            "selected_group_id": selected_group.id if selected_group else None,
            "groups": groups,
            "active_plans": active_plans,
            "selected_active_plan": selected_active_plan,
            "selected_active_plan_id": selected_active_plan.id if selected_active_plan else None,
            "member_rows": member_rows,
            "message": "",
        },
    )


@login_required
def my_plans(request):
    enrollments = (
        PlanEnrollment.objects.filter(user=request.user)
        .select_related("active_plan", "active_plan__plan")
        .order_by("-joined_at")
    )

    plan_rows = []

    for enrollment in enrollments:
        active_plan = enrollment.active_plan
        plan_days = list(
            ReadingPlanDay.objects.filter(plan=active_plan.plan).order_by("day_number")
        )
        total_reading_days = len(plan_days)

        checked_days = CheckIn.objects.filter(
            user=request.user,
            active_plan=active_plan,
        ).count()

        progress_percent = (
            round((checked_days / total_reading_days) * 100)
            if total_reading_days
            else 0
        )

        max_day_number = (
            ReadingPlanDay.objects.filter(plan=active_plan.plan)
            .aggregate(max_day=Max("day_number"))
            .get("max_day")
            or 0
        )

        current_day_number = active_plan.current_day_number()

        if current_day_number < 1:
            status = "Not started"
        elif max_day_number and current_day_number > max_day_number:
            status = "Ended"
        else:
            status = "In progress"

        plan_rows.append(
            {
                "enrollment": enrollment,
                "active_plan": active_plan,
                "status": status,
                "checked_days": checked_days,
                "total_reading_days": total_reading_days,
                "progress_percent": progress_percent,
            }
        )

    return render(request, "reading/my_plans.html", {"plan_rows": plan_rows})


@login_required
def leave_active_plan(request, active_plan_id):
    if request.method != "POST":
        return redirect("my_plans")

    enrollment = (
        PlanEnrollment.objects.filter(
            user=request.user,
            active_plan_id=active_plan_id,
        )
        .select_related("active_plan")
        .first()
    )

    if enrollment is None:
        messages.info(request, "You are not enrolled in this reading plan.")
        return redirect("my_plans")

    active_plan_name = str(enrollment.active_plan)
    enrollment.delete()

    messages.success(request, f"You left the reading plan: {active_plan_name}.")
    return redirect("my_plans")
