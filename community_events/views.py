from django.contrib.auth.decorators import login_required
from django.db.models import Exists, OuterRef
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import ActivitySignup, CommunityActivity
from .visibility import (
    user_has_community_activity_manager_override,
    visible_community_activities_for,
)


@login_required
def community_activity_list(request):
    """Independent member-facing browse entrance (COMMUNITY-EVENTS.1B).

    Lists upcoming activities the signed-in user may see through the
    structure-native visibility helper. Ordinary users see only published
    activities whose audience rows match their active primary membership unit
    or one of its ancestors; zero-row activities fail closed. Staff and
    superusers keep the helper's intentionally narrow management bypass, so
    they may also see draft/cancelled/completed rows here. The list may show
    the current user's signup state but contributes no Today or My Serving
    surface.
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
    return render(
        request,
        "community_events/community_activity_list.html",
        {
            "activities": activities,
            "can_manage": user_has_community_activity_manager_override(request.user),
        },
    )


@login_required
def community_activity_detail(request, activity_id):
    """Member-facing detail page, governed by the shared visibility helper.

    Denies with 404 when ``can_be_seen_by`` is false so a hidden activity is
    indistinguishable from a missing one. No route-level module hard-off is
    applied; visibility remains the sole gate.
    """
    activity = get_object_or_404(CommunityActivity, id=activity_id)
    if not activity.can_be_seen_by(request.user):
        raise Http404("Community activity not available.")
    signup = activity.signup_for(request.user)
    return render(
        request,
        "community_events/community_activity_detail.html",
        {
            "activity": activity,
            "can_manage": activity.can_be_managed_by(request.user),
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
