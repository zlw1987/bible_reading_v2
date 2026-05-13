from django.urls import path

from . import views

urlpatterns = [
    path("days/<int:plan_day_id>/comments/add/", views.add_comment, name="add_comment"),
    path("comments/<int:comment_id>/reply/", views.add_reply, name="add_reply"),
    path("comments/<int:comment_id>/delete/", views.delete_comment, name="delete_comment"),
]