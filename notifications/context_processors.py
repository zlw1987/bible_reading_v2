"""Notification-owned shared-shell data (NOTIFY.1B)."""

from core.module_registry import is_module_enabled

from .models import Notification


def notification_context(request):
    """Expose the authenticated recipient's unread count to the shared shell.

    Core deliberately does not import Notification ORM code.  Keeping this
    small context processor in the notifications app also lets module
    disablement and anonymous requests avoid the query entirely.
    """

    enabled = is_module_enabled("notifications")
    if not enabled or not request.user.is_authenticated:
        return {
            "notifications_enabled": enabled,
            "unread_notification_count": 0,
        }

    return {
        "notifications_enabled": True,
        "unread_notification_count": Notification.objects.filter(
            recipient=request.user,
            read_at__isnull=True,
        ).count(),
    }
