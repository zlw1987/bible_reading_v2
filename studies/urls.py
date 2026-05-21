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
    path(
        "studies/<int:session_id>/worship/",
        views.manage_worship_songs,
        name="manage_worship_songs",
    ),
    path(
        "studies/worship-songs/<int:song_id>/edit/",
        views.edit_worship_song,
        name="edit_worship_song",
    ),
    path(
        "studies/worship-songs/<int:song_id>/delete/",
        views.delete_worship_song,
        name="delete_worship_song",
    ),
]
