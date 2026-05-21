from django.urls import path

from . import views

urlpatterns = [
    path("studies/", views.study_session_list, name="study_session_list"),
    path("studies/new/", views.create_study_session, name="create_study_session"),
    path(
        "studies/<int:session_id>/",
        views.study_session_detail,
        name="study_session_detail",
    ),
    path(
        "studies/<int:session_id>/edit/",
        views.edit_study_session,
        name="edit_study_session",
    ),
    path(
        "studies/<int:session_id>/delete/",
        views.delete_study_session,
        name="delete_study_session",
    ),
]
