from django.urls import path

from . import views

urlpatterns = [
    path("events/", views.service_event_list, name="service_event_list"),
    path(
        "events/worship-planning/",
        views.worship_planning,
        name="worship_planning",
    ),
    path(
        "events/worship-planning/rotation/",
        views.worship_rotation_planner,
        name="worship_rotation_planner",
    ),
    path(
        "events/worship-planning/rotation/confirm/",
        views.worship_rotation_planner_confirm,
        name="worship_rotation_planner_confirm",
    ),
    path(
        "events/worship-planning/workbook-preview/",
        views.worship_workbook_preview,
        name="worship_workbook_preview",
    ),
    path(
        "events/worship-planning/workbook-confirm/",
        views.worship_workbook_confirm,
        name="worship_workbook_confirm",
    ),
    path("events/new/", views.create_service_event, name="create_service_event"),
    path(
        "events/recurring/new/",
        views.create_recurring_service_events,
        name="create_recurring_service_events",
    ),
    path("events/<int:event_id>/", views.service_event_detail, name="service_event_detail"),
    path("events/<int:event_id>/edit/", views.edit_service_event, name="edit_service_event"),
    path(
        "events/<int:event_id>/worship-team/",
        views.change_worship_team,
        name="change_worship_team",
    ),
    path(
        "events/<int:event_id>/planners/add/",
        views.add_service_event_planner,
        name="add_service_event_planner",
    ),
    path(
        "events/<int:event_id>/planners/<int:assignment_id>/end/",
        views.end_service_event_planner,
        name="end_service_event_planner",
    ),
    path(
        "events/<int:event_id>/planners/<int:assignment_id>/restore/",
        views.restore_service_event_planner,
        name="restore_service_event_planner",
    ),
    path("events/<int:event_id>/cancel/", views.cancel_service_event, name="cancel_service_event"),
]
