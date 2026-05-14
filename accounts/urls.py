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

    path("staff/users/", views.staff_user_list, name="staff_user_list"),
    path(
        "staff/users/<int:user_id>/password/",
        views.staff_user_password_reset,
        name="staff_user_password_reset",
    ),
]