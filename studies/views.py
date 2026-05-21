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

from .forms import BibleStudyGuideForm, BibleStudySessionForm
from .models import BibleStudyGuide, BibleStudySession


def study_ui_text(language, key):
    labels = {
        "en": {
            "no_permission": "You do not have permission to manage Bible studies.",
            "not_available": "This Bible study is not available.",
            "saved": "Bible study session saved.",
            "cancelled": "Bible study session cancelled.",
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

    return render(
        request,
        "studies/study_session_detail.html",
        {
            "session_obj": session,
            "guide": guide,
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
