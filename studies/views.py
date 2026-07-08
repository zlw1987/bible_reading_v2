from datetime import datetime, time

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from accounts.language import get_user_language
from accounts.models import ChurchStructureUnit
from accounts.ordering import order_units_by_display_label
from accounts.serving_readiness import add_serving_readiness_warnings
from accounts.permissions import (
    CAP_MANAGE_BIBLE_STUDIES,
    CAP_PUBLISH_BIBLE_STUDY_GUIDES,
    has_capability,
)

from .forms import (
    BibleStudyLessonForm,
    BibleStudyMeetingForm,
    BibleStudyMeetingPreparationForm,
    BibleStudyMeetingRoleForm,
    BibleStudyMeetingWorshipSongForm,
    BibleStudySeriesForm,
)
from .models import (
    BibleStudyLesson,
    BibleStudyMeeting,
    BibleStudyMeetingRole,
    BibleStudyMeetingWorshipSong,
    BibleStudySeries,
)
from .services import (
    GENERATION_WARNING_MISSING_SERIES_AUDIENCE,
    _collect_descendant_or_self_unit_ids,
    build_existing_normal_meeting_index,
    cancel_bible_study_lesson_with_meetings,
    create_normal_meeting_for_target,
    find_existing_meeting_for_target,
    resolve_normal_generation_targets,
    sync_normal_meeting_audience_scope_for_unit,
)
from .permissions import (
    user_has_explicit_bible_study_serving_role_for_meeting,
)
from .visibility import (
    get_membership_audience_candidate_unit_ids,
)


def study_ui_text(language, key):
    labels = {
        "en": {
            "no_permission": "You do not have permission to manage Bible studies.",
            "not_available": "This Bible study is not available.",
            "saved": "Bible study session saved.",
            "cancelled": "Bible study session cancelled.",
            "schedule_saved": "Bible Study schedule saved.",
            "lesson_saved": "Bible study guide saved.",
            "lesson_cancelled": "Bible study guide cancelled.",
            "meeting_saved": "Small group Bible Study meeting saved.",
            "meeting_cancelled": "Small group Bible Study meeting cancelled.",
            "preparation_saved": "Group preparation saved.",
            "meeting_role_saved": "Meeting role saved.",
            "meeting_role_deleted": "Meeting role deleted.",
            "meeting_worship_saved": "Worship song saved.",
            "meeting_worship_deleted": "Worship song deleted.",
            "legacy_create_retired": (
                "Legacy Bible Study sessions are retired. Please use the Bible "
                "Study V2 schedule and meeting flow."
            ),
            "legacy_mutation_frozen": (
                "Legacy Bible Study sessions are retired in the app. App-level editing is "
                "frozen. Please use the Bible Study V2 schedule and meeting flow."
            ),
            "legacy_app_runtime_retired": (
                "Legacy Bible Study sessions are retired in the app. Please use the current "
                "Bible Study schedule and meeting flow."
            ),
        },
        "zh": {
            "no_permission": "你没有管理查经安排的权限。",
            "not_available": "这个查经安排目前不可用。",
            "saved": "查经安排已保存。",
            "cancelled": "查经安排已取消。",
            "schedule_saved": "查经安排已保存。",
            "legacy_create_retired": "旧版查经安排已停止创建，请使用新版查经排期与聚会流程。",
            "legacy_mutation_frozen": "旧版查经安排已在应用中退役，应用内编辑已冻结。请使用新版查经排期与聚会流程。",
            "legacy_app_runtime_retired": "旧版查经安排已在应用中退役，请使用当前的查经排期与聚会流程。",
        },
    }
    return labels.get(language, labels["en"])[key]


def can_manage_bible_studies(user):
    return (
        getattr(user, "is_staff", False)
        or getattr(user, "is_superuser", False)
        or has_capability(user, CAP_MANAGE_BIBLE_STUDIES)
        or has_capability(user, CAP_PUBLISH_BIBLE_STUDY_GUIDES)
    )


def can_edit_bible_study_meeting_preparation(user, meeting):
    return can_manage_bible_studies(user)


def _local_midnight(local_date):
    return timezone.make_aware(
        datetime.combine(local_date, datetime.min.time()),
        timezone.get_current_timezone(),
    )


def get_v2_landing_context(user):
    show_staff_links = can_manage_bible_studies(user)

    # BS-STRUCT.2A: audience rows are the V2 runtime source of truth. Zero-row
    # meetings fail closed for ordinary users; user_small_group remains template
    # display compatibility only.
    user_small_group = getattr(getattr(user, "profile", None), "small_group", None)
    audience_candidate_unit_ids = get_membership_audience_candidate_unit_ids(user)

    # A user with no active primary membership cannot match any V2 meeting
    # audience row. Profile.small_group no longer admits zero-row meetings.
    if not audience_candidate_unit_ids:
        return {
            "user_small_group": user_small_group,
            "primary_meeting": None,
            "upcoming_meetings": [],
            "show_no_small_group": True,
            "show_staff_links": show_staff_links,
        }

    visible_statuses = [
        BibleStudyMeeting.STATUS_PUBLISHED,
        BibleStudyMeeting.STATUS_COMPLETED,
    ]
    # V2 meetings do not store an end time. Match the existing serving
    # convention: a same-day meeting remains current until next local midnight.
    today_start = _local_midnight(timezone.localdate())
    base_meetings = BibleStudyMeeting.objects.select_related(
        "lesson",
        "lesson__series",
        "anchor_unit",
    ).prefetch_related(
        "audience_scope_links__unit",
    ).filter(
        meeting_datetime__gte=today_start,
        status__in=visible_statuses,
        lesson__status__in=[
            BibleStudyLesson.STATUS_PUBLISHED,
            BibleStudyLesson.STATUS_COMPLETED,
        ],
        lesson__series__is_active=True,
        lesson__series__status__in=[
            BibleStudySeries.STATUS_PUBLISHED,
            BibleStudySeries.STATUS_COMPLETED,
        ],
    )

    # Candidate filter: audience-row meetings whose audience unit is the user's
    # membership unit or an ancestor of it. ``can_be_seen_by`` remains the final
    # per-meeting authority below.
    candidate_meetings = (
        base_meetings.filter(
            audience_scope_links__unit_id__in=audience_candidate_unit_ids,
        )
        .distinct()
        .order_by("meeting_datetime")
    )

    upcoming_meetings = []
    for meeting in candidate_meetings:
        if meeting.can_be_seen_by(user):
            upcoming_meetings.append(meeting)
        if len(upcoming_meetings) >= 3:
            break

    return {
        "user_small_group": user_small_group,
        "primary_meeting": upcoming_meetings[0] if upcoming_meetings else None,
        "upcoming_meetings": upcoming_meetings,
        "show_no_small_group": False,
        "show_staff_links": show_staff_links,
    }


def get_default_meeting_datetime(lesson):
    meeting_datetime = datetime.combine(lesson.lesson_date, time(hour=19, minute=30))
    if timezone.is_naive(meeting_datetime):
        return timezone.make_aware(
            meeting_datetime,
            timezone.get_current_timezone(),
        )
    return meeting_datetime


def get_bible_study_meeting_generation_preview(lesson):
    """Build the structure-unit-native normal generation preview (BS-STRUCT.1L).

    The preview is based on :class:`GenerationTarget` rows resolved from the
    series (each an active ``UNIT_SMALL_GROUP`` ``ChurchStructureUnit`` leaf). A
    target counts as existing when any existing meeting matches it by generation
    key or a single-unit audience row (so pre-key meetings are recognized and
    never duplicated). Cancelled meetings still count as existing and are
    deliberately not regenerated.
    """
    targets, warnings = resolve_normal_generation_targets(lesson.series)
    index = build_existing_normal_meeting_index(lesson)

    missing_targets = []
    existing_count = 0
    for target in targets:
        if find_existing_meeting_for_target(index, target) is not None:
            existing_count += 1
        else:
            missing_targets.append(target)

    # BS-STRUCT.1M: surface the fail-closed missing-series-audience state to the
    # preview so the GET page can warn before a no-op POST.
    missing_series_audience = any(
        warning.kind == GENERATION_WARNING_MISSING_SERIES_AUDIENCE
        for warning in warnings
    )

    return {
        "targets": targets,
        "missing_targets": missing_targets,
        "warnings": warnings,
        "eligible_count": len(targets),
        "existing_count": existing_count,
        "missing_count": len(missing_targets),
        "missing_series_audience": missing_series_audience,
    }


@login_required
def bible_study_schedule_manage_list(request):
    language = get_user_language(request)
    if not can_manage_bible_studies(request.user):
        messages.error(request, study_ui_text(language, "no_permission"))
        return redirect("study_session_list")

    schedules = BibleStudySeries.objects.exclude(
        status=BibleStudySeries.STATUS_CANCELLED,
    ).prefetch_related(
        "audience_scope_links__unit",
    ).annotate(
        guide_count=Count(
            "lessons",
            filter=~Q(lessons__status=BibleStudyLesson.STATUS_CANCELLED),
        ),
    ).order_by("title")

    return render(
        request,
        "studies/bible_study_schedule_manage_list.html",
        {"schedules": schedules},
    )


@login_required
def bible_study_schedule_detail(request, series_id):
    language = get_user_language(request)
    if not can_manage_bible_studies(request.user):
        messages.error(request, study_ui_text(language, "no_permission"))
        return redirect("study_session_list")

    schedule = get_object_or_404(
        BibleStudySeries.objects.prefetch_related(
            "audience_scope_links__unit",
        ).annotate(
            guide_count=Count(
                "lessons",
                filter=~Q(lessons__status=BibleStudyLesson.STATUS_CANCELLED),
            ),
        ),
        id=series_id,
    )

    return render(
        request,
        "studies/bible_study_schedule_detail.html",
        {
            "schedule": schedule,
            "lessons": schedule.lessons.exclude(
                status=BibleStudyLesson.STATUS_CANCELLED,
            ).select_related(
                "series",
                "created_by",
            ),
        },
    )


@login_required
def create_bible_study_schedule(request):
    language = get_user_language(request)
    if not can_manage_bible_studies(request.user):
        messages.error(request, study_ui_text(language, "no_permission"))
        return redirect("study_session_list")

    if request.method == "POST":
        form = BibleStudySeriesForm(request.POST, language=language)
        if form.is_valid():
            schedule = form.save(commit=False)
            schedule.created_by = request.user
            schedule.save()
            form.save_audience_units(schedule)
            messages.success(request, study_ui_text(language, "schedule_saved"))
            return redirect("bible_study_schedule_detail", series_id=schedule.id)
    else:
        form = BibleStudySeriesForm(language=language)

    return render(
        request,
        "studies/bible_study_schedule_form.html",
        {"form": form, "is_edit": False},
    )


@login_required
def edit_bible_study_schedule(request, series_id):
    language = get_user_language(request)
    if not can_manage_bible_studies(request.user):
        messages.error(request, study_ui_text(language, "no_permission"))
        return redirect("study_session_list")

    schedule = get_object_or_404(BibleStudySeries, id=series_id)

    if request.method == "POST":
        form = BibleStudySeriesForm(
            request.POST,
            instance=schedule,
            language=language,
        )
        if form.is_valid():
            schedule = form.save()
            messages.success(request, study_ui_text(language, "schedule_saved"))
            return redirect("bible_study_schedule_detail", series_id=schedule.id)
    else:
        form = BibleStudySeriesForm(instance=schedule, language=language)

    return render(
        request,
        "studies/bible_study_schedule_form.html",
        {"schedule": schedule, "form": form, "is_edit": True},
    )


@login_required
def bible_study_lesson_manage_list(request):
    language = get_user_language(request)
    if not can_manage_bible_studies(request.user):
        messages.error(request, study_ui_text(language, "no_permission"))
        return redirect("study_session_list")

    status = (request.GET.get("status") or "").strip()
    series_id = (request.GET.get("series") or "").strip()
    lessons = BibleStudyLesson.objects.exclude(
        status=BibleStudyLesson.STATUS_CANCELLED,
    ).select_related(
        "series",
        "created_by",
    ).prefetch_related("series__audience_scope_links__unit")

    if status:
        lessons = lessons.filter(status=status)
    if series_id:
        lessons = lessons.filter(series_id=series_id)

    status_choices = [
        choice
        for choice in BibleStudyLesson.STATUS_CHOICES
        if choice[0] != BibleStudyLesson.STATUS_CANCELLED
    ]

    return render(
        request,
        "studies/bible_study_lesson_manage_list.html",
        {
            "lessons": lessons,
            "series_options": BibleStudySeries.objects.filter(
                is_active=True,
            ).exclude(
                status=BibleStudySeries.STATUS_CANCELLED,
            ).order_by("title"),
            "status": status,
            "series_id": series_id,
            "status_choices": status_choices,
        },
    )


@login_required
def bible_study_lesson_detail(request, lesson_id):
    language = get_user_language(request)
    if not can_manage_bible_studies(request.user):
        messages.error(request, study_ui_text(language, "no_permission"))
        return redirect("study_session_list")

    lesson = get_object_or_404(
        BibleStudyLesson.objects.select_related(
            "series",
            "created_by",
        ).prefetch_related("series__audience_scope_links__unit"),
        id=lesson_id,
    )

    return render(
        request,
        "studies/bible_study_lesson_detail.html",
        {
            "lesson": lesson,
            "meetings": lesson.meetings.exclude(
                status=BibleStudyMeeting.STATUS_CANCELLED,
            ).select_related(
                "anchor_unit",
                "discussion_leader_user",
            ).prefetch_related(
                "audience_scope_links__unit",
            ).order_by("meeting_datetime", "id"),
            # Generation preview deliberately keeps counting cancelled meetings
            # as existing so they are skipped, not regenerated.
            "generation_preview": get_bible_study_meeting_generation_preview(lesson),
        },
    )


@login_required
def generate_bible_study_meetings(request, lesson_id):
    language = get_user_language(request)
    if not can_manage_bible_studies(request.user):
        messages.error(request, study_ui_text(language, "no_permission"))
        return redirect("study_session_list")

    lesson = get_object_or_404(
        BibleStudyLesson.objects.select_related(
            "series",
            "created_by",
        ),
        id=lesson_id,
    )
    preview = get_bible_study_meeting_generation_preview(lesson)

    if request.method == "POST":
        created_count = 0
        # BS-STRUCT.1L: each missing target is one active UNIT_SMALL_GROUP
        # ChurchStructureUnit leaf. Create one structure-native normal meeting
        # per target (audience row + anchor_unit + per-unit generation_key).
        default_meeting_datetime = get_default_meeting_datetime(lesson)

        for target in preview["missing_targets"]:
            try:
                with transaction.atomic():
                    create_normal_meeting_for_target(
                        lesson,
                        target,
                        meeting_datetime=default_meeting_datetime,
                        created_by=request.user,
                    )
                created_count += 1
            except (IntegrityError, ValidationError):
                # A meeting for this unit was created concurrently (or already
                # exists under the unique constraints); treat it as existing.
                continue

        skipped_count = preview["eligible_count"] - created_count
        message = (
            f"已生成 {created_count} 个小组查经聚会，跳过 {skipped_count} 个已存在的聚会。"
            if language == "zh"
            else (
                f"Created {created_count} small group meetings. "
                f"Skipped {skipped_count} existing meetings."
            )
        )
        messages.success(request, message)

        # BS-STRUCT.1M: a series with zero structure audience rows fails closed.
        # No meetings are generated and the manager is told to configure the
        # schedule audience scope first.
        if preview.get("missing_series_audience"):
            missing_audience_message = (
                "这个查经安排还没有设置教会结构适用范围，因此没有生成聚会。"
                "请先编辑查经安排的适用范围。"
                if language == "zh"
                else (
                    "This Bible Study schedule has no structure audience scope. "
                    "No meetings were generated. Please edit the schedule "
                    "audience scope first."
                )
            )
            messages.warning(request, missing_audience_message)

        return redirect("bible_study_lesson_detail", lesson_id=lesson.id)

    return render(
        request,
        "studies/bible_study_meeting_generation.html",
        {
            "lesson": lesson,
            "generation_preview": preview,
        },
    )


@login_required
def create_bible_study_lesson(request):
    language = get_user_language(request)
    if not can_manage_bible_studies(request.user):
        messages.error(request, study_ui_text(language, "no_permission"))
        return redirect("study_session_list")

    initial = {}
    series_id = (request.GET.get("series") or "").strip()
    if series_id.isdigit() and BibleStudySeries.objects.filter(
        id=series_id,
    ).exclude(
        status=BibleStudySeries.STATUS_CANCELLED,
    ).exists():
        initial["series"] = series_id

    if request.method == "POST":
        form = BibleStudyLessonForm(request.POST, language=language)
        if form.is_valid():
            lesson = form.save(commit=False)
            lesson.created_by = request.user
            lesson.save()
            message = (
                "查经指引已保存。"
                if language == "zh"
                else study_ui_text(language, "lesson_saved")
            )
            messages.success(request, message)
            return redirect("bible_study_lesson_detail", lesson_id=lesson.id)
    else:
        form = BibleStudyLessonForm(initial=initial, language=language)

    return render(
        request,
        "studies/bible_study_lesson_form.html",
        {"form": form, "is_edit": False},
    )


@login_required
def edit_bible_study_lesson(request, lesson_id):
    language = get_user_language(request)
    if not can_manage_bible_studies(request.user):
        messages.error(request, study_ui_text(language, "no_permission"))
        return redirect("study_session_list")

    lesson = get_object_or_404(BibleStudyLesson, id=lesson_id)

    if request.method == "POST":
        form = BibleStudyLessonForm(
            request.POST,
            instance=lesson,
            language=language,
        )
        if form.is_valid():
            lesson = form.save()
            message = (
                "查经指引已保存。"
                if language == "zh"
                else study_ui_text(language, "lesson_saved")
            )
            messages.success(request, message)
            return redirect("bible_study_lesson_detail", lesson_id=lesson.id)
    else:
        form = BibleStudyLessonForm(instance=lesson, language=language)

    return render(
        request,
        "studies/bible_study_lesson_form.html",
        {"lesson": lesson, "form": form, "is_edit": True},
    )


@login_required
def cancel_bible_study_lesson(request, lesson_id):
    language = get_user_language(request)
    if not can_manage_bible_studies(request.user):
        messages.error(request, study_ui_text(language, "no_permission"))
        return redirect("study_session_list")

    lesson = get_object_or_404(BibleStudyLesson, id=lesson_id)

    if request.method != "POST":
        return redirect("bible_study_lesson_detail", lesson_id=lesson.id)

    cancel_bible_study_lesson_with_meetings(lesson)
    message = (
        "查经指引已取消。"
        if language == "zh"
        else study_ui_text(language, "lesson_cancelled")
    )
    messages.success(request, message)
    return redirect("bible_study_lesson_manage_list")


@login_required
def bible_study_meeting_manage_list(request):
    language = get_user_language(request)
    if not can_manage_bible_studies(request.user):
        messages.error(request, study_ui_text(language, "no_permission"))
        return redirect("study_session_list")

    status = (request.GET.get("status") or "").strip()
    lesson_id = (request.GET.get("lesson") or "").strip()

    # BS-STRUCT.1N: the manage-list filter is structure-audience aware. The
    # filter GET param is ``unit`` (a ChurchStructureUnit id). BS-MEETING-MIRROR.1A
    # removed the legacy ``small_group`` mirror, so the obsolete
    # ``?small_group=<id>`` URL tolerance was retired with it; an old bookmark
    # using it now simply falls back to the unfiltered "All" view.
    unit_id = (request.GET.get("unit") or "").strip()

    selected_unit = None
    if unit_id.isdigit():
        selected_unit = ChurchStructureUnit.objects.filter(id=unit_id).first()
    # An invalid / unknown unit id fails safe: no filter is applied and the
    # select falls back to "All".
    unit_id = str(selected_unit.id) if selected_unit is not None else ""

    meetings = BibleStudyMeeting.objects.exclude(
        status=BibleStudyMeeting.STATUS_CANCELLED,
    ).select_related(
        "lesson",
        "anchor_unit",
        "created_by",
    ).prefetch_related(
        "audience_scope_links__unit",
    ).order_by("meeting_datetime", "id")

    if status:
        meetings = meetings.filter(status=status)
    if lesson_id:
        meetings = meetings.filter(lesson_id=lesson_id)
    if selected_unit is not None:
        # Match the selected unit or any descendant using audience rows only.
        # Zero-row meetings fail closed for ordinary users.
        unit_ids = _collect_descendant_or_self_unit_ids([selected_unit])
        meetings = meetings.filter(
            audience_scope_links__unit_id__in=unit_ids,
        ).distinct()

    status_choices = [
        choice
        for choice in BibleStudyMeeting.STATUS_CHOICES
        if choice[0] != BibleStudyMeeting.STATUS_CANCELLED
    ]

    return render(
        request,
        "studies/bible_study_meeting_manage_list.html",
        {
            "meetings": meetings,
            "lesson_options": BibleStudyLesson.objects.exclude(
                status=BibleStudyLesson.STATUS_CANCELLED,
            ).order_by(
                "-lesson_date",
                "title",
            ),
            "unit_options": order_units_by_display_label(
                ChurchStructureUnit.objects.filter(
                    is_active=True,
                ).exclude(
                    unit_type=ChurchStructureUnit.UNIT_ROOT,
                ),
                language,
            ),
            "status": status,
            "lesson_id": lesson_id,
            "unit_id": unit_id,
            "status_choices": status_choices,
        },
    )


@login_required
def bible_study_meeting_detail(request, meeting_id):
    meeting = get_object_or_404(
        BibleStudyMeeting.objects.select_related(
            "lesson",
            "lesson__series",
            "anchor_unit",
            "discussion_leader_user",
            "service_event",
            "created_by",
        ).prefetch_related(
            "audience_scope_links__unit",
        ),
        id=meeting_id,
    )

    # CHURCH-CALENDAR.2B: an explicit linked Bible Study serving role grants
    # read-only visibility to exactly this meeting's detail (mirroring
    # SERVING-EVENT-VISIBILITY.1A), layered beside the ordinary audience gate.
    # It never adds the viewer to the audience, reveals no other meeting, and
    # grants no management authority (management stays with can_manage below).
    if not (
        meeting.can_be_seen_by(request.user)
        or user_has_explicit_bible_study_serving_role_for_meeting(
            request.user, meeting
        )
    ):
        messages.error(
            request,
            study_ui_text(get_user_language(request), "not_available"),
        )
        return redirect("study_session_list")

    return render(
        request,
        "studies/bible_study_meeting_detail.html",
        {
            "meeting": meeting,
            "meeting_roles": meeting.roles.select_related("user"),
            "worship_songs": meeting.worship_songs.select_related(
                "worship_lead_user",
            ),
            "can_manage": can_manage_bible_studies(request.user),
            "can_edit_preparation": can_edit_bible_study_meeting_preparation(
                request.user,
                meeting,
            ),
        },
    )


@login_required
def create_bible_study_meeting(request):
    language = get_user_language(request)
    if not can_manage_bible_studies(request.user):
        messages.error(request, study_ui_text(language, "no_permission"))
        return redirect("study_session_list")

    initial = {}
    lesson_id = (request.GET.get("lesson") or "").strip()
    if lesson_id:
        initial["lesson"] = lesson_id

    if request.method == "POST":
        form = BibleStudyMeetingForm(request.POST, language=language)
        if form.is_valid():
            with transaction.atomic():
                meeting = form.save(commit=False)
                meeting.created_by = request.user
                meeting.save()
                # BS-STRUCT.1O: the form's selected structure unit is the source
                # of truth; this writes the audience row + anchor + generation
                # key. clean() already rejected duplicates and higher-level /
                # joint / multi-unit edits.
                sync_normal_meeting_audience_scope_for_unit(
                    meeting,
                    form.cleaned_data["audience_unit"],
                )
            message = (
                "小组查经聚会已保存。"
                if language == "zh"
                else study_ui_text(language, "meeting_saved")
            )
            messages.success(request, message)
            return redirect("bible_study_meeting_detail", meeting_id=meeting.id)
    else:
        form = BibleStudyMeetingForm(initial=initial, language=language)

    return render(
        request,
        "studies/bible_study_meeting_form.html",
        {"form": form, "is_edit": False},
    )


@login_required
def edit_bible_study_meeting(request, meeting_id):
    language = get_user_language(request)
    if not can_manage_bible_studies(request.user):
        messages.error(request, study_ui_text(language, "no_permission"))
        return redirect("study_session_list")

    meeting = get_object_or_404(BibleStudyMeeting, id=meeting_id)

    if request.method == "POST":
        form = BibleStudyMeetingForm(
            request.POST,
            instance=meeting,
            language=language,
        )
        if form.is_valid():
            with transaction.atomic():
                meeting = form.save()
                # BS-STRUCT.1O: realign the single normal audience row + anchor +
                # generation key to the selected structure unit. clean() already
                # blocked duplicates and higher-level / joint / multi-unit edits.
                sync_normal_meeting_audience_scope_for_unit(
                    meeting,
                    form.cleaned_data["audience_unit"],
                )
            message = (
                "小组查经聚会已保存。"
                if language == "zh"
                else study_ui_text(language, "meeting_saved")
            )
            messages.success(request, message)
            return redirect("bible_study_meeting_detail", meeting_id=meeting.id)
    else:
        form = BibleStudyMeetingForm(instance=meeting, language=language)

    return render(
        request,
        "studies/bible_study_meeting_form.html",
        {"meeting": meeting, "form": form, "is_edit": True},
    )


@login_required
def cancel_bible_study_meeting(request, meeting_id):
    language = get_user_language(request)
    if not can_manage_bible_studies(request.user):
        messages.error(request, study_ui_text(language, "no_permission"))
        return redirect("study_session_list")

    meeting = get_object_or_404(BibleStudyMeeting, id=meeting_id)

    if request.method != "POST":
        return redirect("bible_study_meeting_detail", meeting_id=meeting.id)

    meeting.status = BibleStudyMeeting.STATUS_CANCELLED
    meeting.save()
    message = (
        "小组查经聚会已取消。"
        if language == "zh"
        else study_ui_text(language, "meeting_cancelled")
    )
    messages.success(request, message)
    return redirect("bible_study_meeting_manage_list")


@login_required
def edit_bible_study_meeting_preparation(request, meeting_id):
    language = get_user_language(request)
    meeting = get_object_or_404(
        BibleStudyMeeting.objects.select_related(
            "lesson",
            "lesson__series",
            "anchor_unit",
            "discussion_leader_user",
            "service_event",
            "created_by",
        ).prefetch_related(
            "audience_scope_links__unit",
        ),
        id=meeting_id,
    )

    if not can_edit_bible_study_meeting_preparation(request.user, meeting):
        messages.error(request, study_ui_text(language, "no_permission"))
        if meeting.can_be_seen_by(request.user):
            return redirect("bible_study_meeting_detail", meeting_id=meeting.id)
        return redirect("study_session_list")

    if request.method == "POST":
        form = BibleStudyMeetingPreparationForm(
            request.POST,
            instance=meeting,
            language=language,
        )
        if form.is_valid():
            form.save()
            message = (
                "小组查经预备已保存。"
                if language == "zh"
                else study_ui_text(language, "preparation_saved")
            )
            messages.success(request, message)
            return redirect("bible_study_meeting_detail", meeting_id=meeting.id)
    else:
        form = BibleStudyMeetingPreparationForm(instance=meeting, language=language)

    return render(
        request,
        "studies/bible_study_meeting_preparation_form.html",
        {
            "meeting": meeting,
            "form": form,
        },
    )


@login_required
def manage_bible_study_meeting_roles(request, meeting_id):
    language = get_user_language(request)
    meeting = get_object_or_404(
        BibleStudyMeeting.objects.select_related(
            "lesson",
            "lesson__series",
            "anchor_unit",
        ).prefetch_related(
            "audience_scope_links__unit",
        ),
        id=meeting_id,
    )

    if not can_manage_bible_studies(request.user):
        messages.error(request, study_ui_text(language, "no_permission"))
        return redirect("bible_study_meeting_detail", meeting_id=meeting.id)

    role_selector_labels = {
        "en": {
            BibleStudyMeetingRole.ROLE_DISCUSSION_LEADER: "Discussion Leader",
            BibleStudyMeetingRole.ROLE_WORSHIP_LEAD: "Worship Lead",
            BibleStudyMeetingRole.ROLE_PIANIST: "Pianist",
            BibleStudyMeetingRole.ROLE_SUPPORT: "Support",
            BibleStudyMeetingRole.ROLE_HOST: "Host",
        },
        "zh": {
            BibleStudyMeetingRole.ROLE_DISCUSSION_LEADER: "查经带领",
            BibleStudyMeetingRole.ROLE_WORSHIP_LEAD: "敬拜带领",
            BibleStudyMeetingRole.ROLE_PIANIST: "伴奏",
            BibleStudyMeetingRole.ROLE_SUPPORT: "配搭",
            BibleStudyMeetingRole.ROLE_HOST: "接待",
        },
    }
    add_role_selector_options = [
        {
            "value": BibleStudyMeetingRole.ROLE_DISCUSSION_LEADER,
            "label": role_selector_labels[language].get(
                BibleStudyMeetingRole.ROLE_DISCUSSION_LEADER,
                "Discussion Leader",
            ),
        },
        {
            "value": BibleStudyMeetingRole.ROLE_WORSHIP_LEAD,
            "label": role_selector_labels[language].get(
                BibleStudyMeetingRole.ROLE_WORSHIP_LEAD,
                "Worship Lead",
            ),
        },
        {
            "value": BibleStudyMeetingRole.ROLE_PIANIST,
            "label": role_selector_labels[language].get(
                BibleStudyMeetingRole.ROLE_PIANIST,
                "Pianist",
            ),
        },
        {
            "value": BibleStudyMeetingRole.ROLE_SUPPORT,
            "label": role_selector_labels[language].get(
                BibleStudyMeetingRole.ROLE_SUPPORT,
                "Support",
            ),
        },
        {
            "value": BibleStudyMeetingRole.ROLE_HOST,
            "label": role_selector_labels[language].get(
                BibleStudyMeetingRole.ROLE_HOST,
                "Host",
            ),
        },
    ]
    valid_add_role_values = {
        option["value"] for option in add_role_selector_options
    }

    def normalize_add_role(value):
        if value in valid_add_role_values:
            return value
        return BibleStudyMeetingRole.ROLE_DISCUSSION_LEADER

    if request.method == "POST":
        selected_add_role = normalize_add_role(request.POST.get("role"))
        form = BibleStudyMeetingRoleForm(
            request.POST,
            language=language,
            meeting=meeting,
        )
        if form.is_valid():
            role = form.save(commit=False)
            role.meeting = meeting
            role.save()
            messages.success(
                request,
                "同工分工已保存。" if language == "zh" else "Meeting role saved.",
            )
            # SERVING-READINESS.1C: advisory, warning-only reminder for a linked
            # user. Display-name-only roles (no linked user) are not evaluated;
            # candidate filtering is unchanged and the save above is never blocked.
            add_serving_readiness_warnings(request, role.user, language=language)
            return redirect("manage_bible_study_meeting_roles", meeting_id=meeting.id)
    else:
        selected_add_role = normalize_add_role(request.GET.get("role"))
        form = BibleStudyMeetingRoleForm(
            language=language,
            meeting=meeting,
            initial={"role": selected_add_role},
        )

    return render(
        request,
        "studies/manage_bible_study_meeting_roles.html",
        {
            "meeting": meeting,
            "meeting_roles": meeting.roles.select_related("user"),
            "form": form,
            "add_role_selector_options": add_role_selector_options,
            "selected_add_role": selected_add_role,
        },
    )


@login_required
def edit_bible_study_meeting_role(request, role_id):
    language = get_user_language(request)
    meeting_role = get_object_or_404(
        BibleStudyMeetingRole.objects.select_related(
            "meeting",
            "meeting__lesson",
            "meeting__lesson__series",
            "meeting__anchor_unit",
            "user",
        ).prefetch_related(
            "meeting__audience_scope_links__unit",
        ),
        id=role_id,
    )

    if not can_manage_bible_studies(request.user):
        messages.error(request, study_ui_text(language, "no_permission"))
        return redirect(
            "bible_study_meeting_detail",
            meeting_id=meeting_role.meeting_id,
        )

    if request.method == "POST":
        form = BibleStudyMeetingRoleForm(
            request.POST,
            instance=meeting_role,
            language=language,
            meeting=meeting_role.meeting,
        )
        if form.is_valid():
            meeting_role = form.save()
            message = (
                "聚会同工分工已保存。"
                if language == "zh"
                else study_ui_text(language, "meeting_role_saved")
            )
            messages.success(request, message)
            # SERVING-READINESS.1C: advisory, warning-only reminder for a linked
            # user. Display-name-only roles (no linked user) are not evaluated;
            # candidate filtering is unchanged and the save above is never blocked.
            add_serving_readiness_warnings(
                request, meeting_role.user, language=language
            )
            return redirect(
                "manage_bible_study_meeting_roles",
                meeting_id=meeting_role.meeting_id,
            )
    else:
        form = BibleStudyMeetingRoleForm(
            instance=meeting_role,
            language=language,
            meeting=meeting_role.meeting,
        )

    return render(
        request,
        "studies/bible_study_meeting_role_form.html",
        {
            "meeting": meeting_role.meeting,
            "meeting_role": meeting_role,
            "form": form,
        },
    )


@login_required
def delete_bible_study_meeting_role(request, role_id):
    language = get_user_language(request)
    meeting_role = get_object_or_404(BibleStudyMeetingRole, id=role_id)
    meeting_id = meeting_role.meeting_id

    if not can_manage_bible_studies(request.user):
        messages.error(request, study_ui_text(language, "no_permission"))
        return redirect("bible_study_meeting_detail", meeting_id=meeting_id)

    if request.method != "POST":
        return redirect("manage_bible_study_meeting_roles", meeting_id=meeting_id)

    meeting_role.delete()
    message = (
        "聚会同工分工已删除。"
        if language == "zh"
        else study_ui_text(language, "meeting_role_deleted")
    )
    messages.success(request, message)
    return redirect("manage_bible_study_meeting_roles", meeting_id=meeting_id)


@login_required
def manage_bible_study_meeting_worship_songs(request, meeting_id):
    language = get_user_language(request)
    meeting = get_object_or_404(
        BibleStudyMeeting.objects.select_related(
            "lesson",
            "lesson__series",
            "anchor_unit",
        ).prefetch_related(
            "audience_scope_links__unit",
        ),
        id=meeting_id,
    )

    if not can_manage_bible_studies(request.user):
        messages.error(request, study_ui_text(language, "no_permission"))
        return redirect("bible_study_meeting_detail", meeting_id=meeting.id)

    if request.method == "POST":
        form = BibleStudyMeetingWorshipSongForm(
            request.POST,
            language=language,
            meeting=meeting,
        )
        if form.is_valid():
            song = form.save(commit=False)
            song.meeting = meeting
            song.save()
            message = (
                "敬拜诗歌已保存。"
                if language == "zh"
                else study_ui_text(language, "meeting_worship_saved")
            )
            messages.success(request, message)
            return redirect(
                "manage_bible_study_meeting_worship_songs",
                meeting_id=meeting.id,
            )
    else:
        next_order = (meeting.worship_songs.count() or 0) + 1
        form = BibleStudyMeetingWorshipSongForm(
            initial={"sort_order": next_order},
            language=language,
            meeting=meeting,
        )

    return render(
        request,
        "studies/manage_bible_study_meeting_worship_songs.html",
        {
            "meeting": meeting,
            "worship_songs": meeting.worship_songs.select_related(
                "worship_lead_user",
            ),
            "meeting_roles": meeting.roles.select_related("user"),
            "form": form,
        },
    )


@login_required
def edit_bible_study_meeting_worship_song(request, song_id):
    language = get_user_language(request)
    song = get_object_or_404(
        BibleStudyMeetingWorshipSong.objects.select_related(
            "meeting",
            "meeting__lesson",
            "meeting__lesson__series",
            "meeting__anchor_unit",
            "worship_lead_user",
        ).prefetch_related(
            "meeting__audience_scope_links__unit",
        ),
        id=song_id,
    )

    if not can_manage_bible_studies(request.user):
        messages.error(request, study_ui_text(language, "no_permission"))
        return redirect("bible_study_meeting_detail", meeting_id=song.meeting_id)

    if request.method == "POST":
        form = BibleStudyMeetingWorshipSongForm(
            request.POST,
            instance=song,
            language=language,
            meeting=song.meeting,
        )
        if form.is_valid():
            form.save()
            message = (
                "敬拜诗歌已保存。"
                if language == "zh"
                else study_ui_text(language, "meeting_worship_saved")
            )
            messages.success(request, message)
            return redirect(
                "manage_bible_study_meeting_worship_songs",
                meeting_id=song.meeting_id,
            )
    else:
        form = BibleStudyMeetingWorshipSongForm(
            instance=song,
            language=language,
            meeting=song.meeting,
        )

    return render(
        request,
        "studies/bible_study_meeting_worship_song_form.html",
        {
            "meeting": song.meeting,
            "song": song,
            "form": form,
        },
    )


@login_required
def delete_bible_study_meeting_worship_song(request, song_id):
    language = get_user_language(request)
    song = get_object_or_404(BibleStudyMeetingWorshipSong, id=song_id)
    meeting_id = song.meeting_id

    if not can_manage_bible_studies(request.user):
        messages.error(request, study_ui_text(language, "no_permission"))
        return redirect("bible_study_meeting_detail", meeting_id=meeting_id)

    if request.method != "POST":
        return redirect(
            "manage_bible_study_meeting_worship_songs",
            meeting_id=meeting_id,
        )

    song.delete()
    message = (
        "敬拜诗歌已删除。"
        if language == "zh"
        else study_ui_text(language, "meeting_worship_deleted")
    )
    messages.success(request, message)
    return redirect(
        "manage_bible_study_meeting_worship_songs",
        meeting_id=meeting_id,
    )


@login_required
def study_session_list(request):
    can_manage = can_manage_bible_studies(request.user)

    return render(
        request,
        "studies/study_session_list.html",
        {
            "can_manage": can_manage,
            "v2_landing": get_v2_landing_context(request.user),
        },
    )
