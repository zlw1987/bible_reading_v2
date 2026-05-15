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
]