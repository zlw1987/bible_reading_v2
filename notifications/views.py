"""Recipient-scoped Notification Center views (NOTIFY.1B)."""

from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.language import get_user_language
from core.module_registry import get_module

from .models import Notification


def _source_label(source_module, language):
    """Return registry label metadata without loading source module code."""

    try:
        module = get_module(source_module)
    except KeyError:
        # Historical/removed keys remain a bounded stored snapshot.  Do not
        # resolve a model or import its former source module just for display.
        return source_module
    return module.label_zh if language == "zh" else module.label_en


@login_required
def notification_center(request):
    """Render only the requesting recipient's newest Notification snapshots."""

    language = get_user_language(request)
    notifications = Notification.objects.filter(recipient=request.user).order_by(
        "-created_at",
        "-pk",
    )
    notification_items = [
        {
            "notification": notification,
            "source_label": _source_label(notification.source_module, language),
        }
        for notification in notifications
    ]
    return render(
        request,
        "notifications/notification_center.html",
        {
            "active_nav": "notifications",
            "notification_items": notification_items,
        },
    )


@login_required
@require_POST
def mark_notification_read(request, notification_id):
    """Mark one current recipient notification read without replacing read_at."""

    updated = Notification.objects.filter(
        pk=notification_id,
        recipient=request.user,
        read_at__isnull=True,
    ).update(read_at=timezone.now())
    if not updated and not Notification.objects.filter(
        pk=notification_id,
        recipient=request.user,
    ).exists():
        # Do not reveal whether another recipient has this identifier.
        raise Http404("Notification not available.")
    return redirect("notification_center")


@login_required
@require_POST
def mark_all_notifications_read(request):
    """Mark only this recipient's unread Notification rows read."""

    Notification.objects.filter(
        recipient=request.user,
        read_at__isnull=True,
    ).update(read_at=timezone.now())
    return redirect("notification_center")
