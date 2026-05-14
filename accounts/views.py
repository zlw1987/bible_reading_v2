from django.contrib import messages
from django.contrib.auth import login
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme

from .forms import SignUpForm
from .language import set_user_language


def signup(request):
    if request.method == "POST":
        form = SignUpForm(request.POST, request=request)

        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, "Your account has been created.")
            return redirect("home")
    else:
        form = SignUpForm(request=request)

    return render(request, "registration/signup.html", {"form": form})


def change_language(request):
    if request.method != "POST":
        return redirect("home")

    language = request.POST.get("language", "zh")
    set_user_language(request, language)

    next_url = request.POST.get("next")

    if next_url and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
    ):
        return redirect(next_url)

    return redirect("home")