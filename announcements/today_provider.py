"""Low-noise Official Announcements contribution to Today.

ANNOUNCEMENTS.1D-SLIM exposes at most one important, currently published
announcement that is visible to the signed-in member. The owning announcement
detail page remains the only content surface; Today adds no feed, body copy,
serving action, staff authority, or cross-module state.
"""

from django.utils.timezone import now as current_time

from core.today_providers import register_today_provider

from .models import Announcement
from .visibility import member_visible_announcements_for

TODAY_DEFAULTS = {"announcement_today_item": None}


def announcement_today_provider(request):
    """Return the newest visible active important announcement, if any."""
    now = current_time()
    announcement = (
        member_visible_announcements_for(request.user, at=now)
        .filter(priority=Announcement.PRIORITY_IMPORTANT)
        .order_by("-publish_start", "-created_at", "-id")
        .first()
    )
    return {"announcement_today_item": announcement}


def register():
    """Register the announcements provider from ``reading.views``."""
    register_today_provider(
        "announcements",
        announcement_today_provider,
        defaults=TODAY_DEFAULTS,
    )
