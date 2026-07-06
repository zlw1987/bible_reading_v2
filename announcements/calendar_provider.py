"""Church Calendar range provider for Announcements (CHURCH-CALENDAR.1B).

Emits normalized ``announcement``
:class:`~church_calendar.providers.CalendarItem` values in the
``active_window`` display mode — active-window communication, not timed
appointments. Visibility reuses the member-safe
:func:`announcements.visibility.member_visible_announcements_for` evaluated at
request time (no staff bypass; draft / archived / future / expired /
zero-audience / nonmatching announcements are already excluded), and both normal
and important announcements are included. Each currently visible active window
is then intersected with the requested range; ``publish_end=None`` stays
open-ended through the range without inventing an end date. This module owns the
announcements adapter and item construction and imports no sibling source module.
"""

from django.urls import reverse
from django.utils import timezone

from church_calendar.providers import (
    DISPLAY_ACTIVE_WINDOW,
    ITEM_TYPE_ANNOUNCEMENT,
    CalendarItem,
    register_range_provider,
)

from .visibility import member_visible_announcements_for


def _overlaps_range(publish_start, publish_end, range_start, range_end):
    """Whether ``[publish_start, publish_end?)`` overlaps ``[range_start, range_end)``.

    ``publish_end=None`` is treated as open-ended (active through the range).
    """
    if publish_start >= range_end:
        return False
    if publish_end is not None and publish_end <= range_start:
        return False
    return True


def _build_item(announcement):
    return CalendarItem(
        item_type=ITEM_TYPE_ANNOUNCEMENT,
        source_id=announcement.id,
        title=announcement.get_title(),
        # The item carries the real publish window; None end stays open-ended.
        start=announcement.publish_start,
        end=announcement.publish_end,
        display_mode=DISPLAY_ACTIVE_WINDOW,
        detail_url=reverse(
            "announcement_detail",
            args=[announcement.id],
        ),
    )


def provide_announcement_items(user, range_start, range_end):
    """Member-visible active announcements whose window overlaps the range."""
    now = timezone.now()
    announcements = member_visible_announcements_for(user, at=now)
    return [
        _build_item(announcement)
        for announcement in announcements
        if _overlaps_range(
            announcement.publish_start,
            announcement.publish_end,
            range_start,
            range_end,
        )
    ]


def register():
    """Register the Announcement calendar provider (idempotent)."""
    from church_calendar.providers import get_registered_range_provider_keys

    if "announcements" in get_registered_range_provider_keys():
        return
    register_range_provider("announcements", provide_announcement_items)
