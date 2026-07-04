from django.urls import path

from . import views


urlpatterns = [
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
