from django.urls import path

from . import views

urlpatterns = [
    path("teams/", views.ministry_team_list, name="ministry_team_list"),
    path("teams/new/", views.create_ministry_team, name="create_ministry_team"),
    path("teams/<int:team_id>/", views.ministry_team_detail, name="ministry_team_detail"),
    path("teams/<int:team_id>/edit/", views.edit_ministry_team, name="edit_ministry_team"),
    path("teams/<int:team_id>/members/", views.manage_team_members, name="manage_team_members"),
    path(
        "teams/memberships/<int:membership_id>/edit/",
        views.edit_team_membership,
        name="edit_team_membership",
    ),
    path(
        "teams/memberships/<int:membership_id>/deactivate/",
        views.deactivate_team_membership,
        name="deactivate_team_membership",
    ),
]
