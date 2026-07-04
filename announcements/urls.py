from django.urls import path

from . import views


urlpatterns = [
    path(
        "staff/announcements/",
        views.staff_announcement_list,
        name="staff_announcement_list",
    ),
    path(
        "staff/announcements/new/",
        views.create_announcement,
        name="create_announcement",
    ),
    path(
        "staff/announcements/<int:announcement_id>/edit/",
        views.edit_announcement,
        name="edit_announcement",
    ),
    path(
        "staff/announcements/<int:announcement_id>/publish/",
        views.publish_announcement,
        name="publish_announcement",
    ),
    path(
        "staff/announcements/<int:announcement_id>/archive/",
        views.archive_announcement,
        name="archive_announcement",
    ),
    path(
        "announcements/",
        views.announcement_list,
        name="announcement_list",
    ),
    path(
        "announcements/<int:announcement_id>/",
        views.announcement_detail,
        name="announcement_detail",
    ),
]
