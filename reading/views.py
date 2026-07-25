from collections import defaultdict
import calendar as py_calendar
from datetime import date

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Max, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme

import announcements.today_provider
import community_events.today_provider
import events.today_provider
import ministry.today_provider
import reading.today_provider
import studies.today_provider
from accounts.language import get_user_language
from core.today_providers import build_today_context
from .today_presentation import build_today_presentation
from accounts.permissions import (
    CAP_PUBLISH_READING_GUIDES,
    get_accessible_progress_groups,
    has_capability,
)
from comments.forms import ReflectionCommentForm, ReflectionReplyForm
from comments.models import ReflectionComment
from comments.reflection_visibility import (
    get_visible_group_reflection_snapshot_unit_ids,
)

from .forms import ReadingGuidePostForm
from .group_progress_shadow import (
    get_membership_core_default_progress_group,
    get_membership_core_progress_roster_users,
)
from .passage_services import get_memory_passages, get_reading_passages
from .bible_sources import parse_memory_verse_text, parse_reading_text
from .models import ActivePlan, CheckIn, PlanEnrollment, ReadingGuidePost, ReadingPlanDay

# READING-STRUCT.1E: the legacy ``get_user_small_group(user)`` helper (returned
# ``Profile.small_group``) was removed as dead code. Its last runtime callers
# were dropped when reflection read visibility moved to the structure snapshot
# (CS-CORE.4G.2) and the group-progress default stopped reading
# ``Profile.small_group`` (READING-STRUCT.1D). The ``Profile.small_group`` field
# itself was removed in PROFILE-SG-FIELD-RETIRE.1A; the membership-core helpers
# (``accounts.structure_selectors`` / ``reading.group_progress_shadow``) are the
# source of truth for belonging.


def can_publish_reading_guides(user):
    return has_capability(user, CAP_PUBLISH_READING_GUIDES)


def reading_guide_ui_message(language, key):
    messages_by_language = {
        "en": {
            "not_available": "This reading plan is not available.",
            "no_permission": "You do not have permission to publish reading guides.",
            "saved": "Reading guide saved.",
            "deleted": "Reading guide deleted.",
        },
        "zh": {
            "not_available": "这个读经计划目前不可用。",
            "no_permission": "你没有发布读经指引的权限。",
            "saved": "读经指引已保存。",
            "deleted": "读经指引已删除。",
        },
    }

    return messages_by_language.get(language, messages_by_language["en"])[key]


def user_can_view_active_plan_intro(user, active_plan):
    if not getattr(user, "is_authenticated", False):
        return False

    if active_plan.plan.is_active:
        return True

    if getattr(user, "is_staff", False) or getattr(user, "is_superuser", False):
        return True

    return PlanEnrollment.objects.filter(user=user, active_plan=active_plan).exists()


def get_visible_reflection_filter(user):
    if user.is_staff:
        return Q()

    visibility_filter = Q(user=user)

    public_visible_filter = Q(is_hidden=False, is_deleted=False) & Q(
        visibility=ReflectionComment.VISIBILITY_CHURCH
    )

    visibility_filter |= public_visible_filter

    # CS-CORE.4G.2: ordinary group visibility is structure-native. Group posts
    # are admitted only when their structure_unit_at_post matches the viewer's
    # active primary membership unit or an ancestor of it (query-level mirror of
    # ReflectionComment.can_be_seen_by). Profile.small_group does not grant
    # ordinary group visibility (the legacy small_group_at_post mirror was removed
    # in REFLECTION-MIRROR.1H).
    allowed_unit_ids = get_visible_group_reflection_snapshot_unit_ids(user)
    if allowed_unit_ids:
        visibility_filter |= Q(
            is_hidden=False,
            is_deleted=False,
            visibility=ReflectionComment.VISIBILITY_GROUP,
            structure_unit_at_post_id__in=allowed_unit_ids,
        )

    return visibility_filter

def build_comment_threads(comments, viewer):
    comment_threads = []

    for comment in comments:
        visible_replies = []

        for reply in comment.replies.all():
            if reply.can_be_seen_by(viewer):
                visible_replies.append(reply)

        comment_threads.append(
            {
                "comment": comment,
                "replies": visible_replies,
            }
        )

    return comment_threads

def get_safe_next_url(request):
    next_url = request.POST.get("next") or request.GET.get("next")

    if next_url and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
    ):
        return next_url

    return None

def get_requested_calendar_month(request):
    today = timezone.localdate()

    try:
        year = int(request.GET.get("year", today.year))
        month = int(request.GET.get("month", today.month))

        if month < 1 or month > 12:
            raise ValueError
    except (TypeError, ValueError):
        year = today.year
        month = today.month

    return year, month


def shift_month(year, month, offset):
    month_index = month - 1 + offset
    shifted_year = year + month_index // 12
    shifted_month = month_index % 12 + 1

    return shifted_year, shifted_month

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
    media_mode="text",
    scripture_ref_key="",
    comments=None,
    my_past_reflections=None,
    comment_threads=None,
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
        "media_mode": media_mode,
        "selected_language": selected_language,
        "selected_text_url": selected_text_url,
        "selected_display": selected_display,
        "audio_url": passage["audio_url"],
        "comment_threads": comment_threads or [],
        "scripture_ref_key": scripture_ref_key,
        "comments": comments or [],
        "my_past_reflections": my_past_reflections or [],
        "comment_form": None,
        "reply_form": None,
    }

    if show_completion_section:
        current_day_number = active_plan.current_day_number()
        ui_language = get_user_language(request)

        context.update(
            {
                "is_future_day": plan_day.day_number > current_day_number,
                "is_checked": CheckIn.objects.filter(
                    user=request.user,
                    active_plan=active_plan,
                    plan_day=plan_day,
                ).exists(),
                "comment_form": ReflectionCommentForm(
                    user=request.user,
                    language=ui_language,
                ),
                "reply_form": ReflectionReplyForm(language=ui_language),
            }
        )

    return context

def reading_media_reader(request, active_plan_id, plan_day_id, passage_index, media_mode):
    active_plan = get_object_or_404(
        ActivePlan.objects.select_related("plan"),
        id=active_plan_id,
    )

    plan_day = get_object_or_404(
        ReadingPlanDay,
        id=plan_day_id,
        plan=active_plan.plan,
    )

    is_enrolled = PlanEnrollment.objects.filter(
        user=request.user,
        active_plan=active_plan,
    ).exists()

    if not is_enrolled:
        messages.error(request, "You need to join this plan before reading it.")
        return redirect("home")

    passages = get_reading_passages(plan_day)

    if passage_index < 0 or passage_index >= len(passages):
        messages.error(request, "This scripture passage could not be found.")
        return redirect("active_plan_detail", active_plan_id=active_plan.id)

    passage = passages[passage_index]
    scripture_ref_key = passage["search_text"]

    visible_filter = get_visible_reflection_filter(request.user)
    if media_mode == "audio":
        reader_url_name = "audio_reader"
        reader_title = "audio_reading"
        source_label = "audio"
    else:
        media_mode = "text"
        reader_url_name = "passage_reader"
        reader_title = "scripture_reader"
        source_label = "reading"

    comments = (
        ReflectionComment.objects
        .filter(
            visible_filter,
            active_plan=active_plan,
            plan_day=plan_day,
            scripture_ref_key=scripture_ref_key,
            parent__isnull=True,
        )
        .select_related("user")
        .prefetch_related("replies", "replies__user")
        .order_by("created_at")
    )

    comment_threads = build_comment_threads(comments, request.user)

    my_past_reflections = (
        ReflectionComment.objects
        .filter(
            user=request.user,
            scripture_ref_key=scripture_ref_key,
            parent__isnull=True,
        )
        .exclude(
            active_plan=active_plan,
            plan_day=plan_day,
        )
        .select_related("active_plan", "plan_day")
        .order_by("-created_at")[:5]
    )

    context = build_reader_context(
        request,
        active_plan=active_plan,
        plan_day=plan_day,
        passage=passage,
        passage_index=passage_index,
        passages=passages,
        reader_url_name=reader_url_name,
        reader_title=reader_title,
        source_label=source_label,
        show_completion_section=True,
        media_mode=media_mode,
        scripture_ref_key=scripture_ref_key,
        comments=comments,
        comment_threads=comment_threads,
        my_past_reflections=my_past_reflections,
    )

    return render(request, "reading/passage_reader.html", context)


@login_required
def active_plan_intro(request, active_plan_id):
    active_plan = get_object_or_404(
        ActivePlan.objects.select_related("plan"),
        id=active_plan_id,
    )

    is_enrolled = PlanEnrollment.objects.filter(
        user=request.user,
        active_plan=active_plan,
    ).exists()

    if not user_can_view_active_plan_intro(request.user, active_plan):
        messages.error(
            request,
            reading_guide_ui_message(get_user_language(request), "not_available"),
        )
        return redirect("home")

    language = get_user_language(request)
    plan_days = list(
        ReadingPlanDay.objects.filter(plan=active_plan.plan).order_by("day_number")
    )
    plan_day_by_number = {day.day_number: day for day in plan_days}

    max_day_number = max(plan_day_by_number.keys(), default=0)
    total_reading_days = len(plan_days)
    total_calendar_days = max_day_number
    rest_days = max(total_calendar_days - total_reading_days, 0)
    current_day_number = active_plan.current_day_number()
    today_plan_day = plan_day_by_number.get(current_day_number)
    today_passages = get_reading_passages(today_plan_day) if today_plan_day else []
    today_memory_passages = (
        get_memory_passages(today_plan_day)
        if today_plan_day and today_plan_day.memory_verse
        else []
    )

    checked_days = 0
    progress_percent = 0

    if is_enrolled:
        checked_days = CheckIn.objects.filter(
            user=request.user,
            active_plan=active_plan,
        ).count()
        progress_percent = (
            round((checked_days / total_reading_days) * 100)
            if total_reading_days
            else 0
        )

    introduction = active_plan.plan.get_introduction(language)
    reading_guidance = active_plan.plan.get_reading_guidance(language)
    pastoral_note = active_plan.plan.get_pastoral_note(language)
    can_manage_guides = can_publish_reading_guides(request.user)
    guide_posts = active_plan.guide_posts.all()
    if not can_manage_guides:
        guide_posts = guide_posts.filter(is_published=True)
    guide_posts = guide_posts.select_related("author")[:3]

    return render(
        request,
        "reading/active_plan_intro.html",
        {
            "active_plan": active_plan,
            "is_enrolled": is_enrolled,
            "current_day_number": current_day_number,
            "today_plan_day": today_plan_day,
            "today_passages": today_passages,
            "today_memory_passages": today_memory_passages,
            "total_reading_days": total_reading_days,
            "total_calendar_days": total_calendar_days,
            "rest_days": rest_days,
            "checked_days": checked_days,
            "progress_percent": progress_percent,
            "introduction": introduction,
            "reading_guidance": reading_guidance,
            "pastoral_note": pastoral_note,
            "guide_posts": guide_posts,
            "can_manage_guides": can_manage_guides,
        },
    )


@login_required
def active_plan_guides(request, active_plan_id):
    active_plan = get_object_or_404(
        ActivePlan.objects.select_related("plan"),
        id=active_plan_id,
    )

    can_manage_guides = can_publish_reading_guides(request.user)

    if not (user_can_view_active_plan_intro(request.user, active_plan) or can_manage_guides):
        messages.error(
            request,
            reading_guide_ui_message(get_user_language(request), "not_available"),
        )
        return redirect("home")

    guide_posts = active_plan.guide_posts.select_related("author")
    if not can_manage_guides:
        guide_posts = guide_posts.filter(is_published=True)

    return render(
        request,
        "reading/active_plan_guides.html",
        {
            "active_plan": active_plan,
            "guide_posts": guide_posts,
            "can_manage_guides": can_manage_guides,
        },
    )


@login_required
def create_reading_guide_post(request, active_plan_id):
    active_plan = get_object_or_404(
        ActivePlan.objects.select_related("plan"),
        id=active_plan_id,
    )

    if not can_publish_reading_guides(request.user):
        messages.error(
            request,
            reading_guide_ui_message(get_user_language(request), "no_permission"),
        )
        return redirect("active_plan_guides", active_plan_id=active_plan.id)

    language = get_user_language(request)

    if request.method == "POST":
        form = ReadingGuidePostForm(request.POST, language=language)
        if form.is_valid():
            guide_post = form.save(commit=False)
            guide_post.active_plan = active_plan
            guide_post.author = request.user
            if guide_post.is_published and not guide_post.published_at:
                guide_post.published_at = timezone.now()
            guide_post.save()
            messages.success(request, reading_guide_ui_message(language, "saved"))
            return redirect("active_plan_guides", active_plan_id=active_plan.id)
    else:
        form = ReadingGuidePostForm(language=language)

    return render(
        request,
        "reading/guide_post_form.html",
        {
            "active_plan": active_plan,
            "form": form,
            "is_edit": False,
        },
    )


@login_required
def edit_reading_guide_post(request, guide_id):
    guide_post = get_object_or_404(
        ReadingGuidePost.objects.select_related("active_plan", "active_plan__plan"),
        id=guide_id,
    )

    if not can_publish_reading_guides(request.user):
        messages.error(
            request,
            reading_guide_ui_message(get_user_language(request), "no_permission"),
        )
        return redirect("active_plan_guides", active_plan_id=guide_post.active_plan_id)

    language = get_user_language(request)

    if request.method == "POST":
        form = ReadingGuidePostForm(
            request.POST,
            instance=guide_post,
            language=language,
        )
        if form.is_valid():
            guide_post = form.save(commit=False)
            if guide_post.is_published and not guide_post.published_at:
                guide_post.published_at = timezone.now()
            guide_post.save()
            messages.success(request, reading_guide_ui_message(language, "saved"))
            return redirect("active_plan_guides", active_plan_id=guide_post.active_plan_id)
    else:
        form = ReadingGuidePostForm(instance=guide_post, language=language)

    return render(
        request,
        "reading/guide_post_form.html",
        {
            "active_plan": guide_post.active_plan,
            "guide_post": guide_post,
            "form": form,
            "is_edit": True,
        },
    )


@login_required
def delete_reading_guide_post(request, guide_id):
    guide_post = get_object_or_404(ReadingGuidePost, id=guide_id)
    active_plan_id = guide_post.active_plan_id

    if not can_publish_reading_guides(request.user):
        messages.error(
            request,
            reading_guide_ui_message(get_user_language(request), "no_permission"),
        )
        return redirect("active_plan_guides", active_plan_id=active_plan_id)

    if request.method != "POST":
        return redirect("active_plan_guides", active_plan_id=active_plan_id)

    guide_post.delete()
    messages.success(
        request,
        reading_guide_ui_message(get_user_language(request), "deleted"),
    )
    return redirect("active_plan_guides", active_plan_id=active_plan_id)


# MODULAR-CORE.3B: the Today provider bodies live in their owning modules
# (reading/events/studies/community_events/announcements/ministry
# ``today_provider`` modules).
# This is the single explicit registration site — no app auto-discovery — kept
# in the home route's module so the registry is populated in a fixed,
# deterministic order whenever the URLConf imports reading.views, before any
# home() request. Context keys stay exclusive per provider, so the order only
# fixes key insertion order.
reading.today_provider.register()
events.today_provider.register()
studies.today_provider.register()
community_events.today_provider.register()
announcements.today_provider.register()
ministry.today_provider.register()


@login_required
def home(request):
    # MODULAR-CORE.3A: Today asks the enabled modules' registered providers
    # for their context instead of coordinating every module inline.
    context = build_today_context(request)
    # UX-MEMBER-JOURNEY.1A: reshape the aggregated reading slice into one hero
    # plus compact secondary rows. Presentation only — no queries are added
    # back into the home view.
    context.update(
        build_today_presentation(
            context,
            language=get_user_language(request),
        )
    )
    return render(request, "reading/home.html", context)


DETAIL_WEEK_LENGTH = 7


@login_required
def active_plan_detail(request, active_plan_id):
    # UX-MEMBER-JOURNEY.1A: the detail page renders a single server-side week
    # (at most seven calendar days) plus a Today's Reading block, instead of
    # materialising and rendering every day of a potentially very long plan.
    # Full-plan browsing stays on the Calendar page (active_plan_calendar).
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

    language = get_user_language(request)
    plan_day_stats = ReadingPlanDay.objects.filter(
        plan=active_plan.plan
    ).aggregate(
        total_reading_days=Count("id"),
        max_day_number=Max("day_number"),
    )
    total_reading_days = plan_day_stats["total_reading_days"]
    max_day_number = plan_day_stats["max_day_number"] or 0
    current_day_number = active_plan.current_day_number()
    total_calendar_days = max_day_number
    rest_days = max(total_calendar_days - total_reading_days, 0)

    is_not_started = current_day_number < 1
    is_ended = bool(max_day_number and current_day_number > max_day_number)
    has_configured_days = bool(max_day_number)

    # Weeks are fixed 7-day blocks of day-numbers aligned to plan day 1, so
    # every day belongs to exactly one week and "this week" is deterministic.
    # ?week= is an offset from the current week (0 = this week); out-of-range
    # values are clamped to the first/last real week rather than 404-ing.
    last_week_index = (
        (max_day_number - 1) // DETAIL_WEEK_LENGTH
        if has_configured_days
        else 0
    )
    anchor_day = min(max(current_day_number, 1), max_day_number or 1)
    current_week_index = (anchor_day - 1) // DETAIL_WEEK_LENGTH

    try:
        requested_offset = int(request.GET.get("week", 0))
    except (TypeError, ValueError):
        requested_offset = 0

    selected_week_index = max(
        0, min(current_week_index + requested_offset, last_week_index)
    )
    selected_week_offset = selected_week_index - current_week_index

    if has_configured_days:
        week_start_day = selected_week_index * DETAIL_WEEK_LENGTH + 1
        week_end_day = min(
            week_start_day + DETAIL_WEEK_LENGTH - 1,
            max_day_number,
        )
        selected_day_numbers = set(range(week_start_day, week_end_day + 1))
    else:
        week_start_day = None
        week_end_day = None
        selected_day_numbers = set()

    today_is_in_plan = 1 <= current_day_number <= max_day_number
    queried_day_numbers = set(selected_day_numbers)
    if today_is_in_plan:
        queried_day_numbers.add(current_day_number)

    plan_days = list(
        ReadingPlanDay.objects.filter(
            plan=active_plan.plan,
            day_number__in=queried_day_numbers,
        )
        .prefetch_related("structured_passages")
        .order_by("day_number")
    )
    plan_day_by_number = {day.day_number: day for day in plan_days}
    relevant_plan_day_ids = [day.id for day in plan_days]

    checkins = CheckIn.objects.filter(
        user=request.user,
        active_plan=active_plan,
    )
    checked_days = checkins.aggregate(total=Count("id"))["total"]
    checked_plan_day_ids = set(
        checkins.filter(plan_day_id__in=relevant_plan_day_ids).values_list(
            "plan_day_id",
            flat=True,
        )
    )
    progress_percent = (
        round((checked_days / total_reading_days) * 100)
        if total_reading_days
        else 0
    )

    def _build_day(day_number):
        plan_day = plan_day_by_number.get(day_number)
        calendar_date = active_plan.start_date + timezone.timedelta(days=day_number - 1)
        is_checked = bool(plan_day and plan_day.id in checked_plan_day_ids)
        is_today = day_number == current_day_number
        is_future = day_number > current_day_number
        is_rest_day = plan_day is None

        if is_rest_day and is_future:
            status = "future_rest"
        elif is_rest_day:
            status = "rest"
        elif is_checked:
            status = "checked"
        elif is_future:
            status = "future"
        else:
            status = "missing"

        return {
            "day_number": day_number,
            "plan_day": plan_day,
            "calendar_date": calendar_date,
            "passages": get_reading_passages(plan_day) if plan_day else [],
            "memory_passages": (
                get_memory_passages(plan_day)
                if plan_day and plan_day.memory_verse
                else []
            ),
            "is_checked": is_checked,
            "is_today": is_today,
            "is_future": is_future,
            "is_rest_day": is_rest_day,
            "is_reading_day": plan_day is not None,
            "status": status,
        }

    week_days = [
        _build_day(day_number)
        for day_number in sorted(selected_day_numbers)
    ]
    today_day = next(
        (day for day in week_days if day["is_today"]),
        None,
    )
    if today_day is None and today_is_in_plan:
        today_day = _build_day(current_day_number)

    today_plan_day = today_day["plan_day"] if today_day else None
    today_block = {
        "is_not_started": is_not_started,
        "is_ended": is_ended,
        "is_rest_day": (
            has_configured_days
            and not is_not_started
            and not is_ended
            and today_plan_day is None
        ),
        "is_reading_day": today_plan_day is not None,
        "plan_day": today_plan_day,
        "passages": today_day["passages"] if today_day else [],
        "memory_passages": today_day["memory_passages"] if today_day else [],
        "is_checked": today_day["is_checked"] if today_day else False,
    }

    week_range_start = (
        active_plan.start_date + timezone.timedelta(days=week_start_day - 1)
        if week_start_day is not None
        else None
    )
    week_range_end = (
        active_plan.start_date + timezone.timedelta(days=week_end_day - 1)
        if week_end_day is not None
        else None
    )

    return render(
        request,
        "reading/active_plan_detail.html",
        {
            "active_plan": active_plan,
            "current_day_number": current_day_number,
            "max_day_number": max_day_number,
            "total_reading_days": total_reading_days,
            "total_calendar_days": total_calendar_days,
            "rest_days": rest_days,
            "checked_days": checked_days,
            "progress_percent": progress_percent,
            "is_not_started": is_not_started,
            "is_ended": is_ended,
            "has_configured_days": has_configured_days,
            "introduction": active_plan.plan.get_introduction(language),
            "reading_guidance": active_plan.plan.get_reading_guidance(language),
            "today_block": today_block,
            "week_days": week_days,
            "week_range_start": week_range_start,
            "week_range_end": week_range_end,
            "selected_week_offset": selected_week_offset,
            "prev_week_offset": selected_week_offset - 1,
            "next_week_offset": selected_week_offset + 1,
            "has_prev_week": selected_week_index > 0,
            "has_next_week": selected_week_index < last_week_index,
            "is_current_week": selected_week_index == current_week_index,
        },
    )

@login_required
def active_plan_calendar(request, active_plan_id):
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

    year, month = get_requested_calendar_month(request)
    previous_year, previous_month = shift_month(year, month, -1)
    next_year, next_month = shift_month(year, month, 1)

    month_date = date(year, month, 1)

    plan_days = list(
        ReadingPlanDay.objects
        .filter(plan=active_plan.plan)
        .order_by("day_number")
    )
    plan_day_by_number = {
        plan_day.day_number: plan_day
        for plan_day in plan_days
    }

    max_day_number = max(plan_day_by_number.keys(), default=0)
    current_day_number = active_plan.current_day_number()
    today = timezone.localdate()

    checked_plan_day_ids = set(
        CheckIn.objects
        .filter(
            user=request.user,
            active_plan=active_plan,
        )
        .values_list("plan_day_id", flat=True)
    )

    calendar_builder = py_calendar.Calendar(firstweekday=6)
    calendar_weeks = []

    for week in calendar_builder.monthdatescalendar(year, month):
        week_cells = []

        for calendar_date in week:
            day_number = (calendar_date - active_plan.start_date).days + 1
            in_plan_range = 1 <= day_number <= max_day_number
            plan_day = plan_day_by_number.get(day_number)

            passages = get_reading_passages(plan_day) if plan_day else []
            memory_passages = (
                get_memory_passages(plan_day)
                if plan_day and plan_day.memory_verse
                else []
            )

            is_checked = bool(plan_day and plan_day.id in checked_plan_day_ids)
            is_today = calendar_date == today
            is_future = in_plan_range and day_number > current_day_number
            is_rest_day = in_plan_range and plan_day is None
            is_reading_day = plan_day is not None
            is_current_month = calendar_date.month == month

            if not in_plan_range:
                status = "outside"
            elif is_rest_day:
                status = "rest"
            elif is_checked:
                status = "checked"
            elif is_future:
                status = "future"
            elif is_reading_day:
                status = "missing"
            else:
                status = "outside"

            week_cells.append(
                {
                    "date": calendar_date,
                    "day_number": day_number if in_plan_range else None,
                    "plan_day": plan_day,
                    "passages": passages,
                    "memory_passages": memory_passages,
                    "is_checked": is_checked,
                    "is_today": is_today,
                    "is_future": is_future,
                    "is_rest_day": is_rest_day,
                    "is_reading_day": is_reading_day,
                    "is_current_month": is_current_month,
                    "status": status,
                }
            )

        calendar_weeks.append(week_cells)

    total_reading_days = len(plan_days)
    checked_days = len(checked_plan_day_ids)
    progress_percent = (
        round((checked_days / total_reading_days) * 100)
        if total_reading_days
        else 0
    )

    if request.GET.get("year") or request.GET.get("month"):
        today_calendar_url = f"{request.path}"
    else:
        today_calendar_url = None

    return render(
        request,
        "reading/active_plan_calendar.html",
        {
            "active_plan": active_plan,
            "calendar_weeks": calendar_weeks,
            "month_date": month_date,
            "year": year,
            "month": month,
            "previous_year": previous_year,
            "previous_month": previous_month,
            "next_year": next_year,
            "next_month": next_month,
            "total_reading_days": total_reading_days,
            "checked_days": checked_days,
            "progress_percent": progress_percent,
            "week_labels_zh": ["日", "一", "二", "三", "四", "五", "六"],
            "week_labels_en": ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"],
            "today_calendar_url": today_calendar_url,
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
    return reading_media_reader(
        request,
        active_plan_id=active_plan_id,
        plan_day_id=plan_day_id,
        passage_index=passage_index,
        media_mode="text",
    )

@login_required
def audio_reader(request, active_plan_id, plan_day_id, passage_index):
    return reading_media_reader(
        request,
        active_plan_id=active_plan_id,
        plan_day_id=plan_day_id,
        passage_index=passage_index,
        media_mode="audio",
    )


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

    is_enrolled = PlanEnrollment.objects.filter(
        user=request.user,
        active_plan=active_plan,
    ).exists()

    if not is_enrolled:
        messages.error(request, "You need to join this plan before reading it.")
        return redirect("home")

    passages = get_memory_passages(plan_day)

    if passage_index < 0 or passage_index >= len(passages):
        messages.error(request, "This memory verse could not be found.")
        return redirect("active_plan_detail", active_plan_id=active_plan.id)

    passage = passages[passage_index]

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
        media_mode="text",
        scripture_ref_key=passages[passage_index]["search_text"],
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
    language = get_user_language(request)
    groups = get_accessible_progress_groups(request.user)
    today_status_labels = {
        "not_joined": {
            "en": "Not joined",
            "zh": "未加入计划",
        },
        "no_reading_today": {
            "en": "No reading today",
            "zh": "今天没有指定读经",
        },
        "checked": {
            "en": "Checked",
            "zh": "已打卡",
        },
        "not_started": {
            "en": "Not started",
            "zh": "尚未开始",
        },
        "plan_ended": {
            "en": "Plan ended",
            "zh": "计划已结束",
        },
        "missing": {
            "en": "Missing",
            "zh": "未打卡",
        },
    }

    selected_group = None
    group_id = request.GET.get("group")

    if group_id:
        selected_group = groups.filter(id=group_id).first()

    # CS-CORE.4F.2 + READING-STRUCT.1D + LEGACY-STRUCTURE-SURFACE-RETIRE.1A:
    # when there is no usable explicit ?group=,
    # the default selected group is the permission-fenced membership-core candidate
    # (single active primary ChurchStructureMembership on an active canonical
    # small-group unit, already in the accessible `groups`). It fails closed on
    # no / multiple / inactive / wrong-type membership. READING-STRUCT.1D removed
    # the former legacy Profile.small_group default fallback, and this slice removed
    # the legacy SmallGroup row list/display dependency. When there is no membership
    # candidate the default is simply the first accessible group (role/permission
    # driven), and ordinary users with no resolvable membership fall through to the
    # safe no-group state below.
    if selected_group is None:
        membership_default = get_membership_core_default_progress_group(
            request.user, accessible_groups=groups
        )
        if membership_default is not None:
            selected_group = membership_default

    if selected_group is None:
        selected_group = groups.first()

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
                "message": (
                    "你目前还没有可查看的小组读经进度。"
                    if language == "zh"
                    else "You are not assigned to a small group yet."
                ),
            },
        )

    # CS-CORE.4F.1 + LEGACY-STRUCTURE-SURFACE-RETIRE.1A: the visible roster source
    # is active primary ChurchStructureMembership under the selected canonical unit.
    # Ordinary membership grants only own-group access; role-scoped access remains
    # explicit structure_unit permission, not serving or broad staff authority.
    group_members = get_membership_core_progress_roster_users(selected_group)

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
                "message": (
                    "这个小组目前还没有成员加入正在进行的读经计划。"
                    if language == "zh"
                    else "No active reading plan has been joined by this group yet."
                ),
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
            today_status_key = "not_joined"
        elif today_plan_day is None:
            today_status_key = "no_reading_today"
        elif today_plan_day.id in checked_day_ids:
            today_status_key = "checked"
        elif current_day_number < 1:
            today_status_key = "not_started"
        elif current_day_number > total_days:
            today_status_key = "plan_ended"
        else:
            today_status_key = "missing"

        member_rows.append(
            {
                "member": member,
                "is_enrolled": is_enrolled,
                "today_status_key": today_status_key,
                "today_status": today_status_labels[today_status_key][
                    "zh" if language == "zh" else "en"
                ],
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
def passage_wall(request):
    scripture_ref_key = (request.GET.get("ref") or "").strip()
    tab = (request.GET.get("tab") or "my").strip()

    if tab not in {"my", "group", "church"}:
        tab = "my"

    if not scripture_ref_key:
        messages.error(request, "No scripture reference was provided.")
        return redirect("home")

    parsed_passages = parse_reading_text(scripture_ref_key)

    if parsed_passages:
        passage = parsed_passages[0]
        display_zh = passage.get("display_zh", scripture_ref_key)
        display_en = passage.get("display_en", scripture_ref_key)
    else:
        display_zh = scripture_ref_key
        display_en = scripture_ref_key

    base_queryset = (
        ReflectionComment.objects
        .filter(
            scripture_ref_key=scripture_ref_key,
            parent__isnull=True,
            is_deleted=False,
        )
        .select_related(
            "user",
            "active_plan",
            "plan_day",
            "structure_unit_at_post",
        )
        .order_by("-created_at")
    )

    if tab == "my":
        reflections = base_queryset.filter(user=request.user)

    elif tab == "group":
        if request.user.is_staff:
            # Staff can review all group-shared reflections, including hidden ones.
            reflections = base_queryset.filter(
                visibility=ReflectionComment.VISIBILITY_GROUP,
            )
        else:
            # CS-CORE.4G.2: structure-native group visibility. Ordinary viewers
            # see their own posts plus group posts whose structure_unit_at_post
            # matches their active primary membership unit or an ancestor of it.
            # No membership / no snapshot match => only their own posts.
            allowed_unit_ids = get_visible_group_reflection_snapshot_unit_ids(
                request.user
            )
            group_filter = Q(user=request.user)
            if allowed_unit_ids:
                group_filter |= Q(
                    visibility=ReflectionComment.VISIBILITY_GROUP,
                    structure_unit_at_post_id__in=allowed_unit_ids,
                    is_hidden=False,
                )
            reflections = base_queryset.filter(group_filter)

    else:
        if request.user.is_staff:
            # Staff can review all Reflection Wall posts, including hidden ones.
            reflections = base_queryset.filter(
                visibility=ReflectionComment.VISIBILITY_CHURCH,
            )
        else:
            reflections = base_queryset.filter(
                Q(user=request.user)
                | Q(
                    visibility=ReflectionComment.VISIBILITY_CHURCH,
                    is_hidden=False,
                )
            )

    return render(
        request,
        "reading/passage_wall.html",
        {
            "scripture_ref_key": scripture_ref_key,
            "tab": tab,
            "display_zh": display_zh,
            "display_en": display_en,
            "reflections": reflections,
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
    joined_active_plan_ids = enrollments.values_list("active_plan_id", flat=True)

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

    available_plans = (
        ActivePlan.objects.select_related("plan")
        .filter(plan__is_active=True)
        .exclude(id__in=joined_active_plan_ids)
        .order_by("-start_date")
    )

    for active_plan in available_plans:
        active_plan.has_pinned_guide = active_plan.guide_posts.filter(
            is_pinned=True,
            is_published=True,
        ).exists()

    return render(
        request,
        "reading/my_plans.html",
        {
            "plan_rows": plan_rows,
            "available_plans": available_plans,
            "has_group_progress_access": get_accessible_progress_groups(
                request.user
            ).exists(),
        },
    )


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
