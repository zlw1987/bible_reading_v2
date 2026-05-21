from django.urls import path
from . import views
from . import admin_views

urlpatterns = [
    path("", views.home, name="home"),

    path("plans/my/", views.my_plans, name="my_plans"),
    path(
        "plans/<int:active_plan_id>/calendar/",
        views.active_plan_calendar,
        name="active_plan_calendar",
    ),
    path("plans/<int:active_plan_id>/intro/", views.active_plan_intro, name="active_plan_intro"),
    path("plans/<int:active_plan_id>/guides/", views.active_plan_guides, name="active_plan_guides"),
    path(
        "plans/<int:active_plan_id>/guides/new/",
        views.create_reading_guide_post,
        name="create_reading_guide_post",
    ),
    path(
        "plans/guides/<int:guide_id>/edit/",
        views.edit_reading_guide_post,
        name="edit_reading_guide_post",
    ),
    path(
        "plans/guides/<int:guide_id>/delete/",
        views.delete_reading_guide_post,
        name="delete_reading_guide_post",
    ),
    path("plans/<int:active_plan_id>/", views.active_plan_detail, name="active_plan_detail"),
    path("plans/<int:active_plan_id>/join/", views.join_active_plan, name="join_active_plan"),
    path("plans/<int:active_plan_id>/leave/", views.leave_active_plan, name="leave_active_plan"),
    path(
        "plans/<int:active_plan_id>/days/<int:plan_day_id>/memory-verse/<int:passage_index>/",
        views.memory_verse_reader,
        name="memory_verse_reader",
    ),
    path(
        "plans/<int:active_plan_id>/days/<int:plan_day_id>/check-in/",
        views.check_in,
        name="check_in",
    ),
    path(
        "plans/<int:active_plan_id>/days/<int:plan_day_id>/passages/<int:passage_index>/",
        views.passage_reader,
        name="passage_reader",
    ),

    path("groups/my/progress/", views.my_group_progress, name="my_group_progress"),
    path(
        "staff/reading-plans/",
        admin_views.staff_reading_plan_list,
        name="staff_reading_plan_list",
    ),
    path(
        "staff/reading-plans/<int:plan_id>/header/",
        admin_views.staff_reading_plan_header,
        name="staff_reading_plan_header",
    ),
    path(
        "staff/reading-plans/<int:plan_id>/days/",
        admin_views.staff_reading_plan_days,
        name="staff_reading_plan_days",
    ),
    path("reflections/passage/", views.passage_wall, name="passage_wall"),
    path(
        "plans/<int:active_plan_id>/days/<int:plan_day_id>/audio/<int:passage_index>/",
        views.audio_reader,
        name="audio_reader",
    ),
]
