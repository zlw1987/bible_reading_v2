from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from accounts.language import get_user_language
from accounts.permissions import (
    CAP_MANAGE_BIBLE_STUDIES,
    CAP_PUBLISH_BIBLE_STUDY_GUIDES,
    has_capability,
)

from .forms import (
    BibleStudyGuideForm,
    BibleStudyLessonForm,
    BibleStudyMeetingForm,
    BibleStudyMeetingPreparationForm,
    BibleStudyMeetingRoleForm,
    BibleStudyMeetingWorshipSongForm,
    BibleStudySessionForm,
    BibleStudyWorshipSongForm,
)
from .models import (
    BibleStudyGuide,
    BibleStudyLesson,
    BibleStudyMeeting,
    BibleStudyMeetingRole,
    BibleStudyMeetingWorshipSong,
    BibleStudySeries,
    BibleStudySession,
    BibleStudyWorshipSong,
)


def study_ui_text(language, key):
    labels = {
        "en": {
            "no_permission": "You do not have permission to manage Bible studies.",
            "not_available": "This Bible study is not available.",
            "saved": "Bible study session saved.",
            "cancelled": "Bible study session cancelled.",
            "lesson_saved": "Bible study guide saved.",
            "lesson_cancelled": "Bible study guide cancelled.",
            "meeting_saved": "Small group Bible Study meeting saved.",
            "meeting_cancelled": "Small group Bible Study meeting cancelled.",
            "preparation_saved": "Group preparation saved.",
            "meeting_role_saved": "Meeting role saved.",
            "meeting_role_deleted": "Meeting role deleted.",
            "meeting_worship_saved": "Worship song saved.",
            "meeting_worship_deleted": "Worship song deleted.",
        },
        "zh": {
            "no_permission": "你没有管理查经安排的权限。",
            "not_available": "这个查经安排目前不可用。",
            "saved": "查经安排已保存。",
            "cancelled": "查经安排已取消。",
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


@login_required
def bible_study_lesson_manage_list(request):
    language = get_user_language(request)
    if not can_manage_bible_studies(request.user):
        messages.error(request, study_ui_text(language, "no_permission"))
        return redirect("study_session_list")

    status = (request.GET.get("status") or "").strip()
    series_id = (request.GET.get("series") or "").strip()
    lessons = BibleStudyLesson.objects.select_related("series", "created_by")

    if status:
        lessons = lessons.filter(status=status)
    if series_id:
        lessons = lessons.filter(series_id=series_id)

    return render(
        request,
        "studies/bible_study_lesson_manage_list.html",
        {
            "lessons": lessons,
            "series_options": BibleStudySeries.objects.filter(
                is_active=True,
            ).order_by("title"),
            "status": status,
            "series_id": series_id,
            "status_choices": BibleStudyLesson.STATUS_CHOICES,
        },
    )


@login_required
def bible_study_lesson_detail(request, lesson_id):
    language = get_user_language(request)
    if not can_manage_bible_studies(request.user):
        messages.error(request, study_ui_text(language, "no_permission"))
        return redirect("study_session_list")

    lesson = get_object_or_404(
        BibleStudyLesson.objects.select_related("series", "created_by"),
        id=lesson_id,
    )

    return render(
        request,
        "studies/bible_study_lesson_detail.html",
        {
            "lesson": lesson,
            "meetings": lesson.meetings.select_related(
                "small_group",
                "discussion_leader_user",
            ),
        },
    )


@login_required
def create_bible_study_lesson(request):
    language = get_user_language(request)
    if not can_manage_bible_studies(request.user):
        messages.error(request, study_ui_text(language, "no_permission"))
        return redirect("study_session_list")

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
        form = BibleStudyLessonForm(language=language)

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

    lesson.status = BibleStudyLesson.STATUS_CANCELLED
    lesson.save()
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
    meetings = BibleStudyMeeting.objects.select_related(
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

    small_group_model = BibleStudyMeeting._meta.get_field(
        "small_group"
    ).remote_field.model
    return render(
        request,
        "studies/bible_study_meeting_manage_list.html",
        {
            "meetings": meetings,
            "lesson_options": BibleStudyLesson.objects.order_by(
                "-lesson_date",
                "title",
            ),
            "small_group_options": small_group_model.objects.filter(
                is_active=True,
            ).order_by("name"),
            "status": status,
            "lesson_id": lesson_id,
            "small_group_id": small_group_id,
            "status_choices": BibleStudyMeeting.STATUS_CHOICES,
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
            meeting = form.save(commit=False)
            meeting.created_by = request.user
            meeting.save()
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
            meeting = form.save()
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
    if not can_manage_bible_studies(request.user):
        messages.error(request, study_ui_text(language, "no_permission"))
        return redirect("study_session_list")

    if request.method == "POST":
        session_form = BibleStudySessionForm(request.POST, language=language)
        guide_form = BibleStudyGuideForm(request.POST, language=language)
        if session_form.is_valid() and guide_form.is_valid():
            session = session_form.save(commit=False)
            session.created_by = request.user
            session.save()
            guide = guide_form.save(commit=False)
            guide.session = session
            guide.save()
            messages.success(request, study_ui_text(language, "saved"))
            return redirect("study_session_detail", session_id=session.id)
    else:
        session_form = BibleStudySessionForm(language=language)
        guide_form = BibleStudyGuideForm(language=language)

    return render(
        request,
        "studies/study_session_form.html",
        {
            "session_form": session_form,
            "guide_form": guide_form,
            "is_edit": False,
        },
    )


@login_required
def edit_study_session(request, session_id):
    language = get_user_language(request)
    session = get_object_or_404(BibleStudySession, id=session_id)

    if not can_manage_bible_studies(request.user):
        messages.error(request, study_ui_text(language, "no_permission"))
        return redirect("study_session_list")

    guide, _created = BibleStudyGuide.objects.get_or_create(session=session)

    if request.method == "POST":
        session_form = BibleStudySessionForm(
            request.POST,
            instance=session,
            language=language,
        )
        guide_form = BibleStudyGuideForm(
            request.POST,
            instance=guide,
            language=language,
        )
        if session_form.is_valid() and guide_form.is_valid():
            session = session_form.save()
            guide_form.save()
            messages.success(request, study_ui_text(language, "saved"))
            return redirect("study_session_detail", session_id=session.id)
    else:
        session_form = BibleStudySessionForm(instance=session, language=language)
        guide_form = BibleStudyGuideForm(instance=guide, language=language)

    return render(
        request,
        "studies/study_session_form.html",
        {
            "session_obj": session,
            "session_form": session_form,
            "guide_form": guide_form,
            "is_edit": True,
        },
    )


@login_required
def delete_study_session(request, session_id):
    language = get_user_language(request)
    session = get_object_or_404(BibleStudySession, id=session_id)

    if not can_manage_bible_studies(request.user):
        messages.error(request, study_ui_text(language, "no_permission"))
        return redirect("study_session_list")

    if request.method != "POST":
        return redirect("study_session_detail", session_id=session.id)

    session.status = BibleStudySession.STATUS_CANCELLED
    session.save()
    messages.success(request, study_ui_text(language, "cancelled"))
    return redirect("study_session_list")


@login_required
def manage_worship_songs(request, session_id):
    language = get_user_language(request)
    session = get_object_or_404(
        BibleStudySession.objects.select_related("series"),
        id=session_id,
    )

    if not can_manage_bible_studies(request.user):
        messages.error(request, study_ui_text(language, "no_permission"))
        return redirect("study_session_detail", session_id=session.id)

    if request.method == "POST":
        form = BibleStudyWorshipSongForm(request.POST, language=language)
        if form.is_valid():
            song = form.save(commit=False)
            song.session = session
            song.save()
            messages.success(
                request,
                "敬拜诗歌已保存。" if language == "zh" else "Worship song saved.",
            )
            return redirect("manage_worship_songs", session_id=session.id)
    else:
        next_order = (session.worship_songs.count() or 0) + 1
        form = BibleStudyWorshipSongForm(
            initial={"sort_order": next_order},
            language=language,
        )

    return render(
        request,
        "studies/manage_worship_songs.html",
        {
            "session_obj": session,
            "worship_songs": session.worship_songs.all(),
            "form": form,
        },
    )


@login_required
def edit_worship_song(request, song_id):
    language = get_user_language(request)
    song = get_object_or_404(
        BibleStudyWorshipSong.objects.select_related("session", "session__series"),
        id=song_id,
    )

    if not can_manage_bible_studies(request.user):
        messages.error(request, study_ui_text(language, "no_permission"))
        return redirect("study_session_detail", session_id=song.session_id)

    if request.method == "POST":
        form = BibleStudyWorshipSongForm(
            request.POST,
            instance=song,
            language=language,
        )
        if form.is_valid():
            form.save()
            messages.success(
                request,
                "敬拜诗歌已保存。" if language == "zh" else "Worship song saved.",
            )
            return redirect("manage_worship_songs", session_id=song.session_id)
    else:
        form = BibleStudyWorshipSongForm(instance=song, language=language)

    return render(
        request,
        "studies/worship_song_form.html",
        {
            "session_obj": song.session,
            "song": song,
            "form": form,
        },
    )


@login_required
def delete_worship_song(request, song_id):
    language = get_user_language(request)
    song = get_object_or_404(BibleStudyWorshipSong, id=song_id)
    session_id = song.session_id

    if not can_manage_bible_studies(request.user):
        messages.error(request, study_ui_text(language, "no_permission"))
        return redirect("study_session_detail", session_id=session_id)

    if request.method != "POST":
        return redirect("manage_worship_songs", session_id=session_id)

    song.delete()
    messages.success(
        request,
        "敬拜诗歌已删除。" if language == "zh" else "Worship song deleted.",
    )
    return redirect("manage_worship_songs", session_id=session_id)
