"""Recipient-scoped Notification Center views (NOTIFY.1B)."""

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from accounts.language import get_user_language
from core.module_registry import get_module

from .models import Notification


NOTIFICATIONS_PER_PAGE = 25


def _is_safe_internal_target(target_url):
    """Keep persisted historical targets from becoming open redirects."""

    return (
        isinstance(target_url, str)
        and target_url.startswith("/")
        and not target_url.startswith("//")
        and url_has_allowed_host_and_scheme(target_url, allowed_hosts=set())
    )


def _notification_center_redirect(page_value):
    """Return to a positive integer center page without accepting arbitrary URLs."""

    try:
        page_number = int(page_value)
    except (TypeError, ValueError):
        return redirect("notification_center")
    if page_number < 1:
        return redirect("notification_center")
    return redirect(f"{reverse('notification_center')}?page={page_number}")


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
    page_obj = Paginator(notifications, NOTIFICATIONS_PER_PAGE).get_page(
        request.GET.get("page")
    )
    notification_items = [
        {
            "notification": notification,
            "source_label": _source_label(notification.source_module, language),
        }
        for notification in page_obj.object_list
    ]
    return render(
        request,
        "notifications/notification_center.html",
        {
            "active_nav": "notifications",
            "notification_items": notification_items,
            "page_obj": page_obj,
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
    return _notification_center_redirect(request.POST.get("page"))


@login_required
@require_POST
def open_notification(request, notification_id):
    """Mark a recipient notification read, then open its safe stored target."""

    notification = get_object_or_404(
        Notification,
        pk=notification_id,
        recipient=request.user,
    )
    if not _is_safe_internal_target(notification.target_url):
        # Do not expose, repair, or follow unsafe historical/direct-ORM targets.
        raise Http404("Notification target not available.")
    if notification.read_at is None:
        Notification.objects.filter(
            pk=notification.pk,
            read_at__isnull=True,
        ).update(read_at=timezone.now())
    return redirect(notification.target_url)


@login_required
@require_POST
def mark_all_notifications_read(request):
    """Mark only this recipient's unread Notification rows read."""

    Notification.objects.filter(
        recipient=request.user,
        read_at__isnull=True,
    ).update(read_at=timezone.now())
    return redirect("notification_center")
