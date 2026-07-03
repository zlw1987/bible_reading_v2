from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from .models import CommunityActivity
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
    they may also see draft/cancelled/completed rows here. This entrance
    contributes no signup, Today, or My Serving surface.
    """
    now = timezone.now()
    activities = (
        visible_community_activities_for(request.user)
        .filter(start_datetime__gte=now)
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
    return render(
        request,
        "community_events/community_activity_detail.html",
        {
            "activity": activity,
            "can_manage": activity.can_be_managed_by(request.user),
        },
    )
