"""Community Activities Today provider (COMMUNITY-EVENTS.1E-A).

Owns the small, personally relevant Community Activities contribution to
Today: published visible activities happening today that the current user has
actively signed up for, plus creator-owned submissions that need changes.

Activity signup is attendance intent only. This provider does not contribute
to the serving action center, My Serving, TeamAssignment, Bible Study roles,
Staff Overview, setup/readiness, or ServiceEvent.
"""

from django.utils.timezone import now as current_time

from core.today_providers import register_today_provider
from core.today_windows import get_today_week_windows

from .models import ActivitySignup, CommunityActivity
from .visibility import visible_community_activities_for

TODAY_DEFAULTS = {
    "community_activity_today_items": [],
    "community_activity_this_week_items": [],
    "community_activity_creator_attention_items": [],
}


def get_signed_up_activities_for_window(user, start_datetime, end_datetime, now):
    """Visible, published, active-signup activities in one Today date bucket."""
    return list(
        visible_community_activities_for(user)
        .filter(
            status=CommunityActivity.STATUS_PUBLISHED,
            start_datetime__gt=now,
            start_datetime__gte=start_datetime,
            start_datetime__lt=end_datetime,
            signups__user=user,
            signups__status=ActivitySignup.STATUS_SIGNED_UP,
        )
        .order_by("start_datetime", "id")
    )


def community_activity_today_provider(request):
    """Low-noise Community Activity reminders for Today."""
    now = current_time()
    today_start, tomorrow_start, _week_end = get_today_week_windows()

    return {
        "community_activity_today_items": get_signed_up_activities_for_window(
            request.user,
            today_start,
            tomorrow_start,
            now,
        ),
        # Keep the declared key as a safe compatibility default, but do not
        # populate or render later-this-week activities on the low-noise Today
        # surface. The full activity list remains the main entrance.
        "community_activity_this_week_items": [],
        "community_activity_creator_attention_items": list(
            CommunityActivity.objects.filter(
                created_by=request.user,
                status=CommunityActivity.STATUS_CHANGES_REQUESTED,
            ).order_by(
                "-updated_at",
                "-id",
            )
        ),
    }


def register():
    """Register the Community Activities provider from ``reading.views``."""
    register_today_provider(
        "community_events",
        community_activity_today_provider,
        defaults=TODAY_DEFAULTS,
    )
