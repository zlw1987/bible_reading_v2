from django.shortcuts import redirect
from django.urls import reverse


class ForcePasswordChangeMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            profile = getattr(request.user, "profile", None)

            if profile and profile.must_change_password:
                allowed_paths = {
                    reverse("password_change"),
                    reverse("password_change_done"),
                    reverse("logout"),
                    reverse("change_language"),
                }

                is_allowed_path = (
                    request.path in allowed_paths
                    or request.path.startswith("/static/")
                )

                if not is_allowed_path:
                    return redirect("password_change")

        return self.get_response(request)