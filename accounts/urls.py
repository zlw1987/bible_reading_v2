from django.contrib.auth.views import PasswordChangeDoneView
from django.urls import path

from . import views

urlpatterns = [
    path("signup/", views.signup, name="signup"),
    path("language/", views.change_language, name="change_language"),

    path("accounts/profile/", views.profile, name="profile"),
    path(
        "accounts/password/change/",
        views.ProfilePasswordChangeView.as_view(),
        name="password_change",
    ),
    path(
        "accounts/password/change/done/",
        PasswordChangeDoneView.as_view(
            template_name="accounts/password_change_done.html",
        ),
        name="password_change_done",
    ),

    path("staff/", views.staff_overview, name="staff_overview"),
    path(
        "staff/structure/",
        views.staff_structure_map,
        name="staff_structure_map",
    ),
    path(
        "staff/structure/<int:unit_id>/rename/",
        views.staff_structure_unit_rename,
        name="staff_structure_unit_rename",
    ),
    path(
        "staff/structure/units/<int:parent_id>/children/add/",
        views.staff_structure_unit_add_child,
        name="staff_structure_unit_add_child",
    ),
    path(
        "staff/structure/units/<int:unit_id>/disable/",
        views.staff_structure_unit_disable,
        name="staff_structure_unit_disable",
    ),
    path(
        "staff/structure/units/<int:unit_id>/enable/",
        views.staff_structure_unit_enable,
        name="staff_structure_unit_enable",
    ),
    path(
        "staff/structure/units/<int:unit_id>/",
        views.church_structure_unit_detail,
        name="church_structure_unit_detail",
    ),
    path(
        "staff/structure/units/<int:unit_id>/members/add/",
        views.add_structure_membership,
        name="add_structure_membership",
    ),
    path(
        "staff/structure/memberships/<int:membership_id>/end/",
        views.end_structure_membership,
        name="end_structure_membership",
    ),
    path(
        "staff/structure/memberships/<int:membership_id>/set-primary/",
        views.set_primary_structure_membership,
        name="set_primary_structure_membership",
    ),
    path(
        "staff/moderation/",
        views.staff_moderation_queue,
        name="staff_moderation_queue",
    ),
    path("staff/users/", views.staff_user_list, name="staff_user_list"),
    path(
        "staff/membership-requests/",
        views.staff_membership_request_list,
        name="staff_membership_request_list",
    ),
    path(
        "staff/membership-requests/<int:membership_id>/",
        views.staff_membership_request_detail,
        name="staff_membership_request_detail",
    ),
    path(
        "staff/membership-requests/<int:membership_id>/approve/",
        views.staff_membership_request_approve,
        name="staff_membership_request_approve",
    ),
    path(
        "staff/membership-requests/<int:membership_id>/reject/",
        views.staff_membership_request_reject,
        name="staff_membership_request_reject",
    ),
    path(
        "staff/users/<int:user_id>/password/",
        views.staff_user_password_reset,
        name="staff_user_password_reset",
    ),
]
