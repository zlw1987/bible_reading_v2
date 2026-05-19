from django.urls import path

from . import views

urlpatterns = [
    path(
        "plans/<int:active_plan_id>/days/<int:plan_day_id>/passages/<int:passage_index>/comments/add/",
        views.add_comment,
        name="add_comment",
    ),
    path(
        "comments/<int:comment_id>/reply/",
        views.add_reply,
        name="add_reply",
    ),
    path(
        "comments/<int:comment_id>/delete/",
        views.delete_comment,
        name="delete_comment",
    ),
    path(
        "comments/<int:comment_id>/edit/",
        views.edit_comment,
        name="edit_comment",
    ),
    path(
        "comments/<int:comment_id>/report/",
        views.report_comment,
        name="report_comment",
    ),
    path(
        "staff/reflections/reports/",
        views.staff_reflection_reports,
        name="staff_reflection_reports",
    ),
    path(
        "staff/reflections/<int:comment_id>/action/",
        views.staff_reflection_action,
        name="staff_reflection_action",
    ),
]
