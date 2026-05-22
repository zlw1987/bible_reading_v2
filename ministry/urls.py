from django.urls import path

from . import views

urlpatterns = [
    path("my-serving/", views.my_serving, name="my_serving"),
    path(
        "teams/import/lighting-pilot/",
        views.lighting_pilot_import,
        name="lighting_pilot_import",
    ),
    path("assignments/", views.team_assignment_list, name="team_assignment_list"),
    path("assignments/new/", views.create_team_assignment, name="create_team_assignment"),
    path(
        "assignments/<int:assignment_id>/",
        views.team_assignment_detail,
        name="team_assignment_detail",
    ),
    path(
        "assignments/<int:assignment_id>/edit/",
        views.edit_team_assignment,
        name="edit_team_assignment",
    ),
    path(
        "assignments/<int:assignment_id>/cancel/",
        views.cancel_team_assignment,
        name="cancel_team_assignment",
    ),
    path(
        "assignments/<int:assignment_id>/confirm/",
        views.confirm_team_assignment,
        name="confirm_team_assignment",
    ),
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
