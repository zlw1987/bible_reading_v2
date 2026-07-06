"""Church Calendar range provider for ServiceEvents (CHURCH-CALENDAR.1B).

Emits normalized ``service_event`` :class:`~church_calendar.providers.CalendarItem`
values for the signed-in viewer in a half-open local range. Visibility is the
member-safe :func:`events.visibility.member_visible_service_events_for` (no
staff/manager bypass); overlap uses ``start_datetime`` and the existing
effective-end rule. This module owns the events adapter, query, lifecycle
filtering, and item construction. ``church_calendar`` is the only importer, via
its explicit registration site; this module imports no sibling source module.
"""

from django.urls import reverse

from church_calendar.providers import (
    ITEM_TYPE_SERVICE_EVENT,
    CalendarItem,
    register_range_provider,
)

from .models import get_service_event_effective_end
from .visibility import member_visible_service_events_for


def _build_item(event):
    return CalendarItem(
        item_type=ITEM_TYPE_SERVICE_EVENT,
        source_id=event.id,
        title=event.get_title(),
        start=event.start_datetime,
        end=event.end_datetime or None,
        location=event.location or "",
        detail_url=reverse("service_event_detail", args=[event.id]),
    )


def provide_service_event_items(user, range_start, range_end):
    """Member-visible ServiceEvents overlapping ``[range_start, range_end)``.

    An event overlaps the half-open range when it starts before ``range_end``
    and its effective end is after ``range_start`` (a multi-day / long event
    therefore appears on every day its interval covers).
    """
    events = (
        member_visible_service_events_for(user)
        .filter(start_datetime__lt=range_end)
        .order_by("start_datetime", "id")
    )
    return [
        _build_item(event)
        for event in events
        if get_service_event_effective_end(event) > range_start
    ]


def register():
    """Register the ServiceEvent calendar provider (idempotent)."""
    from church_calendar.providers import get_registered_range_provider_keys

    if "events" in get_registered_range_provider_keys():
        return
    register_range_provider("events", provide_service_event_items)
