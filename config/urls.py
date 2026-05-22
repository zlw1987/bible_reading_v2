from django.contrib import admin
from django.contrib.auth.views import LoginView, LogoutView
from django.urls import include, path

from accounts.forms import LocalizedAuthenticationForm

urlpatterns = [
    path("admin/", admin.site.urls),

    path(
        "login/",
        LoginView.as_view(
            template_name="registration/login.html",
            authentication_form=LocalizedAuthenticationForm,
        ),
        name="login",
    ),
    path("logout/", LogoutView.as_view(), name="logout"),

    path("", include("accounts.urls")),
    path("", include("comments.urls")),
    path("", include("reading.urls")),
    path("", include("prayers.urls")),
    path("", include("studies.urls")),
    path("", include("events.urls")),
    path("", include("ministry.urls")),
]
