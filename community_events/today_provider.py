"""Community Activities Today provider (COMMUNITY-EVENTS.1E-A).

Owns the small, personally relevant Community Activities contribution to
Today: upcoming published activities the current user has actively signed up
for, plus creator-owned submissions that are awaiting review or need changes.

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
    """Personally relevant Community Activities for Today / This Week."""
    now = current_time()
    today_start, tomorrow_start, week_end = get_today_week_windows()

    return {
        "community_activity_today_items": get_signed_up_activities_for_window(
            request.user,
            today_start,
            tomorrow_start,
            now,
        ),
        "community_activity_this_week_items": get_signed_up_activities_for_window(
            request.user,
            tomorrow_start,
            week_end,
            now,
        ),
        "community_activity_creator_attention_items": list(
            CommunityActivity.objects.filter(
                created_by=request.user,
                status__in=(
                    CommunityActivity.STATUS_CHANGES_REQUESTED,
                    CommunityActivity.STATUS_PENDING_REVIEW,
                ),
            ).order_by(
                "status",
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
