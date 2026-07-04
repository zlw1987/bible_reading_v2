from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.language import get_user_language

from .forms import AnnouncementForm
from .models import Announcement
from .visibility import member_visible_announcements_for


@login_required
def announcement_list(request):
    """List only currently published announcements visible to this member."""
    announcements = member_visible_announcements_for(request.user).order_by(
        "-publish_start",
        "-created_at",
        "-id",
    )
    return render(
        request,
        "announcements/announcement_list.html",
        {"announcements": announcements},
    )


@login_required
def announcement_detail(request, announcement_id):
    """Show one member-visible announcement or deny its existence with 404."""
    announcement = get_object_or_404(
        member_visible_announcements_for(request.user),
        id=announcement_id,
    )
    return render(
        request,
        "announcements/announcement_detail.html",
        {"announcement": announcement},
    )


def _message(language, english, chinese):
    return chinese if language == "zh" else english


@staff_member_required
def staff_announcement_list(request):
    """Staff-only management view across every announcement lifecycle state."""
    language = get_user_language(request)
    announcements = (
        Announcement.objects.select_related("created_by", "published_by")
        .prefetch_related("audience_scope_links__structure_unit")
        .order_by("-updated_at", "-id")
    )
    announcement_items = [
        {
            "announcement": announcement,
            "audience_labels": [
                link.structure_unit.path_label(language)
                for link in announcement.audience_scope_links.all()
            ],
        }
        for announcement in announcements
    ]
    return render(
        request,
        "announcements/staff_announcement_list.html",
        {"announcement_items": announcement_items},
    )


@staff_member_required
def create_announcement(request):
    language = get_user_language(request)
    form = AnnouncementForm(
        request.POST or None,
        language=language,
    )
    if request.method == "POST" and form.is_valid():
        announcement = form.save_with_audience(created_by=request.user)
        messages.success(
            request,
            _message(
                language,
                "Announcement draft created.",
                "公告草稿已建立。",
            ),
        )
        return redirect("edit_announcement", announcement_id=announcement.id)
    return render(
        request,
        "announcements/announcement_form.html",
        {"form": form, "is_edit": False},
    )


@staff_member_required
def edit_announcement(request, announcement_id):
    language = get_user_language(request)
    announcement = get_object_or_404(Announcement, id=announcement_id)
    form = AnnouncementForm(
        request.POST or None,
        instance=announcement,
        language=language,
    )
    if request.method == "POST" and form.is_valid():
        announcement = form.save_with_audience()
        messages.success(
            request,
            _message(
                language,
                "Announcement saved without changing its lifecycle status.",
                "公告已保存，生命周期状态未改变。",
            ),
        )
        return redirect("edit_announcement", announcement_id=announcement.id)
    return render(
        request,
        "announcements/announcement_form.html",
        {
            "announcement": announcement,
            "form": form,
            "is_edit": True,
        },
    )


def _publish_error(announcement):
    if announcement.status == Announcement.STATUS_ARCHIVED:
        return "archived"
    if announcement.status != Announcement.STATUS_DRAFT:
        return "not_draft"
    try:
        announcement.full_clean()
    except ValidationError:
        return "invalid"
    if not announcement.audience_scope_links.filter(
        structure_unit__is_active=True
    ).exists():
        return "audience"
    return ""


@staff_member_required
@require_POST
def publish_announcement(request, announcement_id):
    language = get_user_language(request)
    with transaction.atomic():
        announcement = get_object_or_404(
            Announcement.objects.select_for_update(),
            id=announcement_id,
        )
        error = _publish_error(announcement)
        if not error:
            announcement.status = Announcement.STATUS_PUBLISHED
            announcement.published_by = request.user
            announcement.published_at = timezone.now()
            announcement.save()

    if error:
        error_messages = {
            "archived": (
                "Archived announcements cannot be published.",
                "已归档的公告不能发布。",
            ),
            "not_draft": (
                "Only draft announcements can be published.",
                "只有草稿公告可以发布。",
            ),
            "invalid": (
                "Fix the announcement fields and publish window before publishing.",
                "请先修正公告字段和发布时间范围，再进行发布。",
            ),
            "audience": (
                "Choose at least one active audience unit before publishing.",
                "发布前请至少选择一个有效的适用范围。",
            ),
        }
        english, chinese = error_messages[error]
        messages.error(request, _message(language, english, chinese))
    else:
        messages.success(
            request,
            _message(language, "Announcement published.", "公告已发布。"),
        )
    return redirect("staff_announcement_list")


@staff_member_required
@require_POST
def archive_announcement(request, announcement_id):
    language = get_user_language(request)
    with transaction.atomic():
        announcement = get_object_or_404(
            Announcement.objects.select_for_update(),
            id=announcement_id,
        )
        announcement.status = Announcement.STATUS_ARCHIVED
        announcement.save()
    messages.success(
        request,
        _message(language, "Announcement archived.", "公告已归档。"),
    )
    return redirect("staff_announcement_list")
