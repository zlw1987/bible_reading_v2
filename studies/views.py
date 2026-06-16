from datetime import datetime, time

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from accounts.language import get_user_language
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
    BibleStudySession,
    BibleStudyWorshipSong,
)
from .services import (
    cancel_bible_study_lesson_with_meetings,
    sync_normal_meeting_audience_scope,
    write_normal_meeting_audience_scope,
)
from .visibility import (
    get_membership_audience_candidate_unit_ids,
    get_membership_visible_small_groups,
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
                "Legacy Bible Study sessions are archived. App-level editing is "
                "frozen. Please use the Bible Study V2 schedule and meeting flow."
            ),
        },
        "zh": {
            "no_permission": "你没有管理查经安排的权限。",
            "not_available": "这个查经安排目前不可用。",
            "saved": "查经安排已保存。",
            "cancelled": "查经安排已取消。",
            "schedule_saved": "查经安排已保存。",
            "legacy_create_retired": "旧版查经安排已停止创建，请使用新版查经排期与聚会流程。",
            "legacy_mutation_frozen": "旧版查经安排已归档，应用内编辑已冻结。请使用新版查经排期与聚会流程。",
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


def redirect_legacy_session_archive(request, session):
    if session.can_be_seen_by(request.user):
        return redirect("study_session_detail", session_id=session.id)
    return redirect("study_session_list")


def can_edit_bible_study_meeting_preparation(user, meeting):
    return can_manage_bible_studies(user)


def get_visible_study_sessions(user):
    sessions = BibleStudySession.objects.select_related(
        "series",
        "district",
        "small_group",
        "created_by",
    ).order_by("-study_datetime")

    if can_manage_bible_studies(user):
        return sessions

    visible_ids = [session.id for session in sessions if session.can_be_seen_by(user)]
    return sessions.filter(id__in=visible_ids)


def get_v2_landing_context(user):
    show_staff_links = can_manage_bible_studies(user)

    # BS-STRUCT.1E: the landing/Today read path now resolves visibility from
    # meeting audience-scope rows when present, with the legacy small_group
    # membership path kept only as a zero-row fallback. ``user_small_group`` is
    # still surfaced for existing templates, but it no longer gates audience-row
    # meeting visibility.
    visible_small_groups = get_membership_visible_small_groups(user)
    user_small_group = visible_small_groups.order_by("name").first()
    audience_candidate_unit_ids = get_membership_audience_candidate_unit_ids(user)

    # A user with neither a resolvable legacy group nor any active primary
    # membership (e.g. a profile-only user) cannot match either path.
    if user_small_group is None and not audience_candidate_unit_ids:
        return {
            "user_small_group": None,
            "primary_meeting": None,
            "upcoming_meetings": [],
            "show_no_small_group": True,
            "show_staff_links": show_staff_links,
        }

    visible_statuses = [
        BibleStudyMeeting.STATUS_PUBLISHED,
        BibleStudyMeeting.STATUS_COMPLETED,
    ]
    base_meetings = BibleStudyMeeting.objects.select_related(
        "lesson",
        "lesson__series",
        "small_group",
    ).prefetch_related(
        "audience_scope_links",
    ).filter(
        meeting_datetime__gte=timezone.now(),
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
    # membership unit or an ancestor of it, plus zero-row meetings still reached
    # through the legacy small_group fallback. ``can_be_seen_by`` remains the
    # final per-meeting authority below, so this is only a (possibly broad)
    # pre-filter; e.g. an audience-row meeting whose small_group still points at
    # the user's group is admitted here but correctly rejected by the
    # audience-row precedence in ``can_be_seen_by``.
    visibility_q = Q()
    if audience_candidate_unit_ids:
        visibility_q |= Q(
            audience_scope_links__unit_id__in=audience_candidate_unit_ids,
        )
    if visible_small_groups:
        visibility_q |= Q(small_group__in=visible_small_groups)

    if not visibility_q:
        candidate_meetings = BibleStudyMeeting.objects.none()
    else:
        candidate_meetings = (
            base_meetings.filter(visibility_q).distinct().order_by("meeting_datetime")
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
    eligible_groups = lesson.series.get_eligible_small_groups()
    existing_group_ids = set(
        lesson.meetings.filter(small_group__in=eligible_groups).values_list(
            "small_group_id",
            flat=True,
        )
    )
    missing_groups = eligible_groups.exclude(id__in=existing_group_ids)
    eligible_count = eligible_groups.count()
    existing_count = len(existing_group_ids)
    missing_count = eligible_count - existing_count
    return {
        "eligible_groups": eligible_groups,
        "missing_groups": missing_groups,
        "eligible_count": eligible_count,
        "existing_count": existing_count,
        "missing_count": missing_count,
    }


@login_required
def bible_study_schedule_manage_list(request):
    language = get_user_language(request)
    if not can_manage_bible_studies(request.user):
        messages.error(request, study_ui_text(language, "no_permission"))
        return redirect("study_session_list")

    schedules = BibleStudySeries.objects.exclude(
        status=BibleStudySeries.STATUS_CANCELLED,
    ).select_related(
        "ministry_context",
        "district",
        "small_group",
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
        BibleStudySeries.objects.select_related(
            "ministry_context",
            "district",
            "small_group",
        ).prefetch_related(
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
        "series__ministry_context",
        "series__district",
        "series__small_group",
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
            "series__ministry_context",
            "series__district",
            "series__small_group",
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
                "small_group",
                "discussion_leader_user",
            ),
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
            "series__ministry_context",
            "created_by",
        ),
        id=lesson_id,
    )
    preview = get_bible_study_meeting_generation_preview(lesson)

    if request.method == "POST":
        created_count = 0
        # BS-STRUCT.1D: groups whose newly generated meeting could not be made
        # structure-native because their small_group has no valid active
        # UNIT_SMALL_GROUP mapping. The meeting is still created (unchanged
        # legacy behavior) but is left as a legacy-only zero-row meeting and
        # surfaced as a warning rather than silently given an invalid row.
        unmapped_groups = []
        default_meeting_datetime = get_default_meeting_datetime(lesson)

        for small_group in preview["missing_groups"]:
            try:
                meeting, created = BibleStudyMeeting.objects.get_or_create(
                    lesson=lesson,
                    small_group=small_group,
                    defaults={
                        "meeting_datetime": default_meeting_datetime,
                        "status": BibleStudyMeeting.STATUS_DRAFT,
                        "created_by": request.user,
                    },
                )
            except IntegrityError:
                created = False

            if created:
                created_count += 1
                # BS-STRUCT.1D: only newly created normal group-level meetings
                # get a structure-native audience row + anchor_unit. Existing
                # meetings are never mutated here (that is BS-STRUCT.1C's job).
                if not write_normal_meeting_audience_scope(meeting):
                    unmapped_groups.append(small_group)

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

        if unmapped_groups:
            group_names = "、".join(group.name for group in unmapped_groups)
            group_names_en = ", ".join(group.name for group in unmapped_groups)
            warning = (
                f"有 {len(unmapped_groups)} 个小组未配置有效的教会结构单元，"
                f"生成的聚会暂无结构受众范围：{group_names}。"
                if language == "zh"
                else (
                    f"{len(unmapped_groups)} group(s) have no valid church "
                    "structure unit mapping; their generated meetings have no "
                    f"structure audience scope: {group_names_en}."
                )
            )
            messages.warning(request, warning)
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
    small_group_id = (request.GET.get("small_group") or "").strip()
    meetings = BibleStudyMeeting.objects.exclude(
        status=BibleStudyMeeting.STATUS_CANCELLED,
    ).select_related(
        "lesson",
        "small_group",
        "created_by",
    )

    if status:
        meetings = meetings.filter(status=status)
    if lesson_id:
        meetings = meetings.filter(lesson_id=lesson_id)
    if small_group_id:
        meetings = meetings.filter(small_group_id=small_group_id)

    status_choices = [
        choice
        for choice in BibleStudyMeeting.STATUS_CHOICES
        if choice[0] != BibleStudyMeeting.STATUS_CANCELLED
    ]

    small_group_model = BibleStudyMeeting._meta.get_field(
        "small_group"
    ).remote_field.model
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
            "small_group_options": small_group_model.objects.filter(
                is_active=True,
            ).order_by("name"),
            "status": status,
            "lesson_id": lesson_id,
            "small_group_id": small_group_id,
            "status_choices": status_choices,
        },
    )


@login_required
def bible_study_meeting_detail(request, meeting_id):
    meeting = get_object_or_404(
        BibleStudyMeeting.objects.select_related(
            "lesson",
            "lesson__series",
            "small_group",
            "discussion_leader_user",
            "service_event",
            "created_by",
        ),
        id=meeting_id,
    )

    if not meeting.can_be_seen_by(request.user):
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
                # BS-STRUCT.1H: a valid manual normal small-group meeting is
                # never left legacy-only; clean() already rejected an invalid
                # mapping, so this writes the equivalent audience row + anchor.
                sync_normal_meeting_audience_scope(meeting)
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
                # BS-STRUCT.1H: repair a zero-row meeting or realign the single
                # normal small-group row + mirror after a group change. clean()
                # already blocked invalid mappings and higher-level/joint rows.
                sync_normal_meeting_audience_scope(meeting)
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
            "small_group",
            "discussion_leader_user",
            "service_event",
            "created_by",
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
            "small_group",
        ),
        id=meeting_id,
    )

    if not can_manage_bible_studies(request.user):
        messages.error(request, study_ui_text(language, "no_permission"))
        return redirect("bible_study_meeting_detail", meeting_id=meeting.id)

    if request.method == "POST":
        form = BibleStudyMeetingRoleForm(
            request.POST,
            language=language,
            meeting=meeting,
        )
        if form.is_valid():
            role = form.save(commit=False)
            role.meeting = meeting
            role.save()
            message = (
                "聚会同工分工已保存。"
                if language == "zh"
                else study_ui_text(language, "meeting_role_saved")
            )
            messages.success(request, message)
            return redirect("manage_bible_study_meeting_roles", meeting_id=meeting.id)
    else:
        form = BibleStudyMeetingRoleForm(language=language, meeting=meeting)

    return render(
        request,
        "studies/manage_bible_study_meeting_roles.html",
        {
            "meeting": meeting,
            "meeting_roles": meeting.roles.select_related("user"),
            "form": form,
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
            "meeting__small_group",
            "user",
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
            form.save()
            message = (
                "聚会同工分工已保存。"
                if language == "zh"
                else study_ui_text(language, "meeting_role_saved")
            )
            messages.success(request, message)
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
            "small_group",
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
            "meeting__small_group",
            "worship_lead_user",
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
    tab = (request.GET.get("tab") or "upcoming").strip()

    if tab not in {"upcoming", "past", "drafts"}:
        tab = "upcoming"
    if tab == "drafts" and not can_manage:
        tab = "upcoming"

    now = timezone.now()
    sessions = get_visible_study_sessions(request.user)

    if tab == "past":
        sessions = sessions.filter(study_datetime__lt=now).exclude(
            status=BibleStudySession.STATUS_DRAFT,
        )
    elif tab == "drafts":
        sessions = sessions.filter(status=BibleStudySession.STATUS_DRAFT)
    else:
        sessions = sessions.filter(study_datetime__gte=now).exclude(
            status__in=[
                BibleStudySession.STATUS_DRAFT,
                BibleStudySession.STATUS_CANCELLED,
            ]
        )

    return render(
        request,
        "studies/study_session_list.html",
        {
            "sessions": sessions,
            "tab": tab,
            "can_manage": can_manage,
            "v2_landing": get_v2_landing_context(request.user),
        },
    )


@login_required
def study_session_detail(request, session_id):
    session = get_object_or_404(
        BibleStudySession.objects.select_related(
            "series",
            "district",
            "small_group",
            "created_by",
        ),
        id=session_id,
    )

    if not session.can_be_seen_by(request.user):
        messages.error(
            request,
            study_ui_text(get_user_language(request), "not_available"),
        )
        return redirect("study_session_list")

    guide = getattr(session, "guide", None)
    worship_songs = session.worship_songs.all()

    return render(
        request,
        "studies/study_session_detail.html",
        {
            "session_obj": session,
            "guide": guide,
            "worship_songs": worship_songs,
            "can_manage": can_manage_bible_studies(request.user),
        },
    )


@login_required
def create_study_session(request):
    language = get_user_language(request)
    messages.warning(request, study_ui_text(language, "legacy_create_retired"))
    return redirect("study_session_list")


@login_required
def edit_study_session(request, session_id):
    language = get_user_language(request)
    session = get_object_or_404(BibleStudySession, id=session_id)

    if not can_manage_bible_studies(request.user):
        messages.error(request, study_ui_text(language, "no_permission"))
    else:
        messages.warning(request, study_ui_text(language, "legacy_mutation_frozen"))
    return redirect_legacy_session_archive(request, session)


@login_required
def delete_study_session(request, session_id):
    language = get_user_language(request)
    session = get_object_or_404(BibleStudySession, id=session_id)

    if not can_manage_bible_studies(request.user):
        messages.error(request, study_ui_text(language, "no_permission"))
    else:
        messages.warning(request, study_ui_text(language, "legacy_mutation_frozen"))
    return redirect_legacy_session_archive(request, session)


@login_required
def manage_worship_songs(request, session_id):
    language = get_user_language(request)
    session = get_object_or_404(
        BibleStudySession.objects.select_related("series"),
        id=session_id,
    )

    if not can_manage_bible_studies(request.user):
        messages.error(request, study_ui_text(language, "no_permission"))
    else:
        messages.warning(request, study_ui_text(language, "legacy_mutation_frozen"))
    return redirect_legacy_session_archive(request, session)


@login_required
def edit_worship_song(request, song_id):
    language = get_user_language(request)
    song = get_object_or_404(
        BibleStudyWorshipSong.objects.select_related("session", "session__series"),
        id=song_id,
    )

    if not can_manage_bible_studies(request.user):
        messages.error(request, study_ui_text(language, "no_permission"))
    else:
        messages.warning(request, study_ui_text(language, "legacy_mutation_frozen"))
    return redirect_legacy_session_archive(request, song.session)


@login_required
def delete_worship_song(request, song_id):
    language = get_user_language(request)
    song = get_object_or_404(BibleStudyWorshipSong, id=song_id)

    if not can_manage_bible_studies(request.user):
        messages.error(request, study_ui_text(language, "no_permission"))
    else:
        messages.warning(request, study_ui_text(language, "legacy_mutation_frozen"))
    return redirect_legacy_session_archive(request, song.session)
