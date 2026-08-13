from django.urls import path

from . import views


urlpatterns = [
    path("notifications/", views.notification_center, name="notification_center"),
    path(
        "notifications/<int:notification_id>/mark-read/",
        views.mark_notification_read,
        name="mark_notification_read",
    ),
    path(
        "notifications/mark-all-read/",
        views.mark_all_notifications_read,
        name="mark_all_notifications_read",
    ),
]
