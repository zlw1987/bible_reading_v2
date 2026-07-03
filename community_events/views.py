from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Exists, OuterRef
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.language import get_user_language
from accounts.structure_selectors import get_user_primary_membership_unit

from .forms import CommunityActivitySubmissionForm
from .models import (
    ActivitySignup,
    CommunityActivity,
    CommunityActivityAudienceScope,
    CommunityActivitySubmissionBlock,
)
from .visibility import (
    user_has_community_activity_manager_override,
    visible_community_activities_for,
)


@login_required
def community_activity_list(request):
    """Independent member-facing browse and submission-status entrance.

    Lists upcoming activities the signed-in user may see through the
    structure-native visibility helper. Ordinary users see only published
    activities whose audience rows match their active primary membership unit
    or one of its ancestors; zero-row activities fail closed. Staff and
    superusers keep the helper's intentionally narrow management bypass, so
    they may also see draft/cancelled/completed rows here. The list may show
    the current user's signup state and own submitted activities but
    contributes no Today or My Serving surface.
    """
    now = timezone.now()
    activities = (
        visible_community_activities_for(request.user)
        .filter(start_datetime__gte=now)
        .annotate(
            is_signed_up=Exists(
                ActivitySignup.objects.filter(
                    activity_id=OuterRef("pk"),
                    user=request.user,
                    status=ActivitySignup.STATUS_SIGNED_UP,
                )
            )
        )
        .order_by("start_datetime", "id")
    )
    submitted_activities = CommunityActivity.objects.filter(
        created_by=request.user,
    ).order_by("-created_at", "-id")
    can_submit = (
        (membership_unit := get_user_primary_membership_unit(request.user))
        is not None
        and membership_unit.is_active
        and not CommunityActivitySubmissionBlock.objects.filter(
            user=request.user,
            is_active=True,
        ).exists()
    )
    return render(
        request,
        "community_events/community_activity_list.html",
        {
            "activities": activities,
            "submitted_activities": submitted_activities,
            "can_submit": can_submit,
            "can_manage": user_has_community_activity_manager_override(request.user),
        },
    )


@login_required
def community_activity_create(request):
    """Let an eligible member propose an activity for staff review."""
    membership_unit = get_user_primary_membership_unit(request.user)
    is_blocked = CommunityActivitySubmissionBlock.objects.filter(
        user=request.user,
        is_active=True,
    ).exists()
    if membership_unit is None or not membership_unit.is_active or is_blocked:
        raise PermissionDenied("Community activity submission is not available.")

    language = get_user_language(request)
    if request.method == "POST":
        form = CommunityActivitySubmissionForm(
            request.POST,
            language=language,
        )
        if form.is_valid():
            with transaction.atomic():
                activity = form.save(commit=False)
                activity.status = CommunityActivity.STATUS_PENDING_REVIEW
                activity.created_by = request.user
                activity.save()
                CommunityActivityAudienceScope.objects.create(
                    activity=activity,
                    structure_unit=membership_unit,
                )
            return redirect(
                "community_activity_detail",
                activity_id=activity.id,
            )
    else:
        form = CommunityActivitySubmissionForm(language=language)

    return render(
        request,
        "community_events/community_activity_form.html",
        {"form": form},
    )


@login_required
def community_activity_detail(request, activity_id):
    """Member detail page with the narrow creator-owned submission exception.

    Public ordinary access remains governed by the shared published audience
    helper. A creator may also see their own submitted activity and status.
    Other hidden activities deny with 404. No route-level module hard-off is
    applied.
    """
    activity = get_object_or_404(CommunityActivity, id=activity_id)
    if not activity.can_be_seen_by(request.user):
        raise Http404("Community activity not available.")
    signup = activity.signup_for(request.user)
    is_creator = activity.created_by_id == request.user.id
    return render(
        request,
        "community_events/community_activity_detail.html",
        {
            "activity": activity,
            "can_manage": activity.can_be_managed_by(request.user),
            "is_creator": is_creator,
            "can_signup": activity.is_signup_open(),
            "is_signed_up": bool(signup and signup.is_active),
        },
    )


def _visible_activity_or_404(user, activity_id):
    activity = get_object_or_404(CommunityActivity, id=activity_id)
    if not activity.can_be_seen_by(user):
        raise Http404("Community activity not available.")
    return activity


@login_required
@require_POST
def community_activity_signup(request, activity_id):
    """Create or reactivate the current user's attendance intent."""
    activity = _visible_activity_or_404(request.user, activity_id)
    if not activity.is_signup_open():
        raise Http404("Community activity signup not available.")

    ActivitySignup.objects.update_or_create(
        activity=activity,
        user=request.user,
        defaults={"status": ActivitySignup.STATUS_SIGNED_UP},
    )
    return redirect("community_activity_detail", activity_id=activity.id)


@login_required
@require_POST
def community_activity_cancel_signup(request, activity_id):
    """Cancel an existing signup without deleting its lifecycle row."""
    activity = _visible_activity_or_404(request.user, activity_id)
    ActivitySignup.objects.filter(
        activity=activity,
        user=request.user,
        status=ActivitySignup.STATUS_SIGNED_UP,
    ).update(
        status=ActivitySignup.STATUS_CANCELLED,
        updated_at=timezone.now(),
    )
    return redirect("community_activity_detail", activity_id=activity.id)
