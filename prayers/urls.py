from django.urls import path

from . import views

urlpatterns = [
    path("prayers/", views.prayer_list, name="prayer_list"),
    path("prayers/<int:prayer_id>/", views.prayer_detail, name="prayer_detail"),
    path("prayers/<int:prayer_id>/pray/", views.mark_prayed, name="mark_prayed"),
    path(
        "prayers/<int:prayer_id>/comments/add/",
        views.add_prayer_comment,
        name="add_prayer_comment",
    ),
    path(
        "prayers/<int:prayer_id>/status/",
        views.update_prayer_status,
        name="update_prayer_status",
    ),
    path(
        "prayers/<int:prayer_id>/delete/",
        views.delete_prayer_request,
        name="delete_prayer_request",
    ),
    path(
        "prayers/<int:prayer_id>/edit/",
        views.edit_prayer_request,
        name="edit_prayer_request",
    ),
    path(
        "prayers/comments/<int:comment_id>/edit/",
        views.edit_prayer_comment,
        name="edit_prayer_comment",
    ),
    path(
        "prayers/comments/<int:comment_id>/delete/",
        views.delete_prayer_comment,
        name="delete_prayer_comment",
    ),
]