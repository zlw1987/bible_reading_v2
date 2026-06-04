from django.contrib import messages
from django.utils.http import url_has_allowed_host_and_scheme
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import get_user_model, login
from django.contrib.auth.views import PasswordChangeView
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme


from .forms import ProfileForm, SignUpForm, StaffPasswordResetForm
from .language import get_user_language, set_user_language
from .ui_text import UI_TEXT
from .models import ChurchStructureMembership, Profile
from .permissions import CAP_MANAGE_CHURCH_MEMBERSHIPS, has_capability


def can_manage_church_memberships(user):
    return has_capability(user, CAP_MANAGE_CHURCH_MEMBERSHIPS)

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

@login_required
def profile(request):
    if request.method == "POST":
        form = ProfileForm(request.POST, user=request.user, request=request)

        if form.is_valid():
            profile_obj = form.save()
            set_user_language(request, profile_obj.preferred_language)
            messages.success(request, UI_TEXT[profile_obj.preferred_language]["profile_saved"])
            return redirect("profile")
    else:
        form = ProfileForm(user=request.user, request=request)

    return render(
        request,
        "accounts/profile.html",
        {
            "form": form,
        },
    )

class ProfilePasswordChangeView(PasswordChangeView):
    template_name = "accounts/password_change_form.html"
    success_url = reverse_lazy("password_change_done")

    def form_valid(self, form):
        response = super().form_valid(form)

        profile, _ = Profile.objects.get_or_create(user=self.request.user)

        if profile.must_change_password:
            profile.must_change_password = False
            profile.save(update_fields=["must_change_password"])

        return response


@staff_member_required
def staff_user_list(request):
    User = get_user_model()

    query = (request.GET.get("q") or "").strip()

    users = (
        User.objects
        .select_related("profile", "profile__small_group")
        .order_by("username")
    )

    if query:
        users = users.filter(
            Q(username__icontains=query)
            | Q(email__icontains=query)
            | Q(profile__small_group__name__icontains=query)
        ).distinct()

    return render(
        request,
        "accounts/staff/user_list.html",
        {
            "users": users,
            "query": query,
        },
    )


@staff_member_required
def staff_user_password_reset(request, user_id):
    User = get_user_model()

    target_user = get_object_or_404(
        User.objects.select_related("profile", "profile__small_group"),
        id=user_id,
    )

    if request.method == "POST":
        form = StaffPasswordResetForm(target_user, request.POST)

        if form.is_valid():
            form.save()

            profile, _ = Profile.objects.get_or_create(user=target_user)
            profile.must_change_password = form.cleaned_data.get(
                "require_password_change",
                False,
            )
            profile.save(update_fields=["must_change_password"])

            messages.success(
                request,
                f"Password reset for {target_user.username}.",
            )

            return redirect("staff_user_list")
    else:
        form = StaffPasswordResetForm(target_user)

    return render(
        request,
        "accounts/staff/password_reset.html",
        {
            "target_user": target_user,
            "form": form,
        },
    )


@user_passes_test(can_manage_church_memberships)
def staff_membership_request_list(request):
    memberships = (
        ChurchStructureMembership.objects
        .filter(status=ChurchStructureMembership.STATUS_REQUESTED)
        .select_related(
            "user",
            "user__profile",
            "user__profile__small_group",
            "unit",
            "unit__parent",
            "requested_by",
        )
        .order_by("-created_at", "user__username", "id")
    )
    language = get_user_language(request)
    membership_rows = [
        {
            "membership": membership,
            "unit_path": membership.unit.path_label(language),
        }
        for membership in memberships
    ]

    return render(
        request,
        "accounts/staff/membership_request_list.html",
        {
            "membership_rows": membership_rows,
        },
    )


def get_requested_membership_or_404(membership_id):
    return get_object_or_404(
        ChurchStructureMembership.objects.select_related(
            "user",
            "user__profile",
            "user__profile__small_group",
            "unit",
            "unit__parent",
            "requested_by",
        ),
        id=membership_id,
        status=ChurchStructureMembership.STATUS_REQUESTED,
    )


@user_passes_test(can_manage_church_memberships)
def staff_membership_request_detail(request, membership_id):
    membership = get_requested_membership_or_404(membership_id)
    language = get_user_language(request)
    active_primary = ChurchStructureMembership.current_primary_for_user(
        membership.user,
    )

    return render(
        request,
        "accounts/staff/membership_request_detail.html",
        {
            "membership": membership,
            "unit_path": membership.unit.path_label(language),
            "active_primary": active_primary,
            "active_primary_path": (
                active_primary.unit.path_label(language) if active_primary else ""
            ),
        },
    )


@user_passes_test(can_manage_church_memberships)
def staff_membership_request_approve(request, membership_id):
    if request.method != "POST":
        return redirect("staff_membership_request_detail", membership_id=membership_id)

    membership = get_requested_membership_or_404(membership_id)
    active_primary = ChurchStructureMembership.current_primary_for_user(
        membership.user,
    )

    if active_primary:
        messages.error(
            request,
            "Approval blocked: user already has an active primary membership.",
        )
        return redirect("staff_membership_request_detail", membership_id=membership.id)

    membership.status = ChurchStructureMembership.STATUS_ACTIVE
    membership.is_primary = True
    if not membership.membership_type:
        membership.membership_type = ChurchStructureMembership.TYPE_SMALL_GROUP_MEMBER
    if not membership.start_date:
        membership.start_date = timezone.localdate()
    membership.approved_by = request.user
    membership.approved_at = timezone.now()
    membership.save()

    messages.success(request, "Membership request approved.")
    return redirect("staff_membership_request_list")


@user_passes_test(can_manage_church_memberships)
def staff_membership_request_reject(request, membership_id):
    if request.method != "POST":
        return redirect("staff_membership_request_detail", membership_id=membership_id)

    membership = get_requested_membership_or_404(membership_id)
    membership.status = ChurchStructureMembership.STATUS_REJECTED
    membership.is_primary = False
    membership.save()

    messages.success(request, "Membership request rejected.")
    return redirect("staff_membership_request_list")
