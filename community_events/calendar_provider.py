"""Church Calendar range provider for Community Activities (CHURCH-CALENDAR.1B).

Emits normalized ``community_activity``
:class:`~church_calendar.providers.CalendarItem` values for the signed-in viewer
in a half-open local range. Visibility is the member-safe
:func:`community_events.visibility.member_visible_community_activities_for` (no
staff / superuser / creator / co-organizer bypass). A start-only activity
belongs to its start date; a ranged activity overlaps every local day its
interval covers. This module owns the community_events adapter, query, and item
construction and imports no sibling source module. There is no
CommunityActivity-to-ServiceEvent relationship.
"""

from django.urls import reverse

from church_calendar.providers import (
    ITEM_TYPE_COMMUNITY_ACTIVITY,
    CalendarItem,
    register_range_provider,
)

from .visibility import member_visible_community_activities_for


def _build_item(activity):
    return CalendarItem(
        item_type=ITEM_TYPE_COMMUNITY_ACTIVITY,
        source_id=activity.id,
        title=activity.get_title(),
        start=activity.start_datetime,
        end=activity.end_datetime or None,
        location=activity.get_location() or "",
        detail_url=reverse(
            "community_activity_detail",
            args=[activity.id],
        ),
    )


def _overlaps_range(start, end, range_start, range_end):
    """Whether the activity overlaps the half-open ``[range_start, range_end)``.

    A start-only activity (``end is None``) is the instant ``start`` and belongs
    to the range only when ``range_start <= start < range_end``. A ranged
    activity is the half-open interval ``[start, end)``: it overlaps only when
    ``start < range_end`` and ``end > range_start``, so an activity ending
    exactly at ``range_start`` (e.g. ending at a day's 00:00 boundary) does not
    appear on that following day.
    """
    if start >= range_end:
        return False
    if end is None:
        return start >= range_start
    return end > range_start


def provide_community_activity_items(user, range_start, range_end):
    """Member-visible published activities overlapping the range."""
    activities = member_visible_community_activities_for(user).order_by(
        "start_datetime",
        "id",
    )
    return [
        _build_item(activity)
        for activity in activities
        if _overlaps_range(
            activity.start_datetime,
            activity.end_datetime,
            range_start,
            range_end,
        )
    ]


def register():
    """Register the CommunityActivity calendar provider (idempotent)."""
    from church_calendar.providers import get_registered_range_provider_keys

    if "community_events" in get_registered_range_provider_keys():
        return
    register_range_provider("community_events", provide_community_activity_items)
