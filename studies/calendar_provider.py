"""Church Calendar range provider for Bible Study V2 meetings (CHURCH-CALENDAR.1B).

Emits normalized ``bible_study_meeting``
:class:`~church_calendar.providers.CalendarItem` values for the signed-in viewer
in a half-open local range. Visibility is the member-safe
:func:`studies.visibility.member_visible_meetings_for` (no staff/capability
bypass); a meeting is a point-in-time item anchored to ``meeting_datetime`` with
no invented duration. This module owns the studies adapter, query, lifecycle
filtering, and item construction. ``church_calendar`` is the only importer, via
its explicit registration site; this module imports no sibling source module.
"""

from django.urls import reverse

from church_calendar.providers import (
    ITEM_TYPE_BIBLE_STUDY_MEETING,
    CalendarItem,
    register_range_provider,
)

from .visibility import member_visible_meetings_for


def _build_item(meeting):
    return CalendarItem(
        item_type=ITEM_TYPE_BIBLE_STUDY_MEETING,
        source_id=meeting.id,
        title=meeting.lesson.get_title(),
        start=meeting.meeting_datetime,
        # Point-in-time: V1 plan forbids inventing a meeting duration.
        end=None,
        location=meeting.get_location() or "",
        detail_url=reverse("bible_study_meeting_detail", args=[meeting.id]),
    )


def provide_bible_study_meeting_items(user, range_start, range_end):
    """Member-visible V2 meetings whose ``meeting_datetime`` is in the range.

    Point-in-time membership: a meeting belongs to the half-open range when
    ``range_start <= meeting_datetime < range_end``.
    """
    meetings = (
        member_visible_meetings_for(user)
        .filter(
            meeting_datetime__gte=range_start,
            meeting_datetime__lt=range_end,
        )
        .select_related("lesson")
        .order_by("meeting_datetime", "id")
    )
    return [_build_item(meeting) for meeting in meetings]


def register():
    """Register the Bible Study meeting calendar provider (idempotent)."""
    from church_calendar.providers import get_registered_range_provider_keys

    if "studies" in get_registered_range_provider_keys():
        return
    register_range_provider("studies", provide_bible_study_meeting_items)
