"""Events module's Today provider (MODULAR-CORE.3B).

Owns the Today / This Week Church Gathering rows of the home context. The
provider bodies moved here from ``reading.views``; registration stays
explicit — ``reading.views`` calls :func:`register` at import time, before
any ``home()`` request.

Visibility is unchanged: ``get_visible_service_events`` (audience-scope rows
matched through active primary membership; zero-row events fail closed for
ordinary users). The compact per-gathering serving note is ministry-owned
(``ministry.today_provider.get_week_serving_notes``) and stays an empty
mapping when the ministry module is disabled — audience visibility is not
serving, and the note never creates a serving row.
"""

from core.today_providers import register_today_provider
from core.today_windows import get_today_week_windows
from ministry.today_provider import get_week_serving_notes

from .models import ServiceEvent, get_service_event_effective_end
from .views import can_manage_service_events, get_visible_service_events

THIS_WEEK_STAFF_EVENT_CAP = 5

TODAY_DEFAULTS = {
    "today_gatherings": [],
    "show_all_today_gatherings_link": False,
    "week_gatherings": [],
    "show_all_gatherings_link": False,
}


def get_gatherings_for_window(user, start_datetime, end_datetime):
    """Visible Church Gatherings in a half-open datetime window."""
    events = (
        get_visible_service_events(user)
        .exclude(
            status__in=[
                ServiceEvent.STATUS_DRAFT,
                ServiceEvent.STATUS_CANCELLED,
            ],
        )
        .filter(
            start_datetime__lt=end_datetime,
        )
        .order_by("start_datetime", "id")
    )
    return [
        event
        for event in events
        if get_service_event_effective_end(event) >= start_datetime
    ]


def attach_serving_notes(events, user):
    serving_notes = get_week_serving_notes(user)
    return [
        {"event": event, "serving_note": serving_notes.get(event.id)}
        for event in events
    ]


def get_gathering_rows_for_window(user, start_datetime, end_datetime):
    """Visible Church Gatherings in a local-date bucket, with serving notes.

    Draft and cancelled events are excluded for everyone, including staff, so
    Today never becomes a staff manage queue. Ordinary users see all visible
    gatherings in the requested local-date window; event managers are capped
    and offered a link to the full Church Gatherings list.
    """
    events = get_gatherings_for_window(user, start_datetime, end_datetime)

    show_all_events_link = False
    if can_manage_service_events(user) and len(events) > THIS_WEEK_STAFF_EVENT_CAP:
        events = events[:THIS_WEEK_STAFF_EVENT_CAP]
        show_all_events_link = True

    return attach_serving_notes(events, user), show_all_events_link


def events_today_provider(request):
    """Today / This Week Church Gatherings (audience-visible, with the
    per-gathering serving note from get_week_serving_notes, which stays empty
    when ministry is disabled)."""
    today_start, tomorrow_start, week_end = get_today_week_windows()

    today_gatherings, show_all_today_gatherings_link = get_gathering_rows_for_window(
        request.user,
        today_start,
        tomorrow_start,
    )
    week_gatherings, show_all_gatherings_link = get_gathering_rows_for_window(
        request.user,
        tomorrow_start,
        week_end,
    )

    # Today de-duplication: a Church Gathering already shown in today's bucket
    # should not appear again in the This Week bucket. get_gatherings_for_window()
    # intentionally uses overlap-window semantics for long events, so do the
    # final presentation-level de-dupe here.
    today_gathering_event_ids = {
        row["event"].id
        for row in today_gatherings
    }
    week_gatherings = [
        row
        for row in week_gatherings
        if row["event"].id not in today_gathering_event_ids
    ]
    if not week_gatherings:
        show_all_gatherings_link = False

    return {
        "today_gatherings": today_gatherings,
        "show_all_today_gatherings_link": show_all_today_gatherings_link,
        "week_gatherings": week_gatherings,
        "show_all_gatherings_link": show_all_gatherings_link,
    }


def register():
    """Register the events Today provider (called from ``reading.views``)."""
    register_today_provider(
        "events",
        events_today_provider,
        defaults=TODAY_DEFAULTS,
    )
