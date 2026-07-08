"""Church Calendar range provider for the viewer's own serving (CHURCH-CALENDAR.2A).

Emits normalized ``my_serving`` :class:`~church_calendar.providers.CalendarItem`
values for the *signed-in viewer's own* explicit serving schedule in a half-open
local range. This is a personal, read-only overlay ("my serving schedule"), not
a team/staff scheduling dashboard.

Serving is EXPLICIT. An item exists only from the viewer's own
``TeamAssignmentMember`` rows, reusing the current My Serving selector
(:func:`ministry.views.my_serving_assignments`) so the calendar agrees with My
Serving on which assignments count: active membership on an active team, the
assignment not cancelled, and the ServiceEvent not draft/cancelled. Serving is
never inferred from ``ChurchStructureMembership`` (belonging), audience scopes,
event visibility, or staff/superuser/manager authority, and other people's
assignments are never shown.

Bible Study linked-user serving roles (``BibleStudyMeetingRole.user``) are a
deliberate follow-up (see ``docs/CHURCH_CALENDAR_V1_PLAN.md``): folding them into
this ``ministry``-keyed provider would query ``studies`` even when that source
module is disabled, so keeping this slice to team-assignment serving preserves
the one-provider-per-source-module enablement gate. This module reads only
``events`` (a declared ``ministry`` dependency) plus its own app; it imports no
sibling source module and is imported only by the ``church_calendar`` explicit
registration site.
"""

from django.urls import reverse

from church_calendar.providers import (
    ITEM_TYPE_MY_SERVING,
    CalendarItem,
    register_range_provider,
)
from events.models import get_service_event_effective_end

from .views import my_serving_assignments


def _event_detail_url(event):
    """Member-facing ServiceEvent detail URL for the grouped occurrence header.

    This is read-only visibility only: SERVING-EVENT-VISIBILITY.1A grants an
    explicitly assigned server read access to that specific ServiceEvent detail
    (layered beside ``ServiceEvent.can_be_seen_by`` in the event detail view),
    so a serving-only occurrence can safely surface the base event detail link.
    It is never an edit/manage/assignment/confirm/attendance/check-in URL.
    """
    return reverse("service_event_detail", args=[event.id])


def _build_item(member):
    """Build a ``my_serving`` item from one ``TeamAssignmentMember`` row.

    ``source_id`` is the assignment-member row id (not the event id), so a viewer
    serving two teams at the same ServiceEvent yields two distinct, non-colliding
    items.

    The calendar item remains read-only and deep-links to the viewer's *own*
    existing My Serving assignment card via a stable
    ``#serving-assignment-<TeamAssignmentMember.id>`` anchor (with ``?tab=all`` so
    the card is present regardless of past/upcoming), never to an
    edit/manage/assignment/confirm URL. The anchor targets the viewer's exact
    existing My Serving assignment card and preserves current Calendar behavior;
    it is unchanged by ``SERVING-EVENT-VISIBILITY.1A``.

    CHURCH-CALENDAR.2A-FU4 adds presentation-only grouping metadata so the
    calendar collapses this serving row into the same real occurrence as the
    base ServiceEvent (and any sibling serving rows for the same event):

    * ``occurrence_key`` = ``"service_event:<ServiceEvent.id>"`` — shared with
      the ``events`` provider's base row so both refer to one occurrence. It
      encodes the ServiceEvent id, never a title/time string, and is not
      authorization.
    * ``occurrence_role`` = the serving team name — marks this as a serving
      *subitem* of the occurrence and supplies the concise per-team label.
    * ``occurrence_title`` / ``occurrence_detail_url`` carry the base event
      title and member-facing event detail link so the grouped occurrence header
      still renders when the base ``service_event`` row is absent (an assigned
      server outside the ordinary audience): the base provider stays
      audience-only, while SERVING-EVENT-VISIBILITY.1A still grants that server
      read-only visibility to the event detail.

    The item's own ``detail_url`` stays the read-only My Serving assignment
    anchor, so serving subitems keep deep-linking to the viewer's My Serving
    card, never to an event edit/manage/confirm/attendance/check-in URL. The
    calendar renders no confirm/edit/manage/attendance/check-in action; any
    existing actions on the My Serving card remain governed by My Serving and are
    unchanged.
    """
    assignment = member.assignment
    event = assignment.service_event
    team = assignment.ministry_team
    return CalendarItem(
        item_type=ITEM_TYPE_MY_SERVING,
        source_id=member.id,
        title=f"{event.get_title()} · {team.get_name()}",
        start=event.start_datetime,
        end=event.end_datetime or None,
        location=event.location or "",
        detail_url=f"{reverse('my_serving')}?tab=all#serving-assignment-{member.id}",
        occurrence_key=f"service_event:{event.id}",
        occurrence_role=team.get_name(),
        occurrence_title=event.get_title(),
        occurrence_detail_url=_event_detail_url(event),
    )


def provide_my_serving_items(user, range_start, range_end):
    """The viewer's own serving rows overlapping ``[range_start, range_end)``.

    A serving item overlaps the half-open range when its ServiceEvent starts
    before ``range_end`` and the event's effective end is after ``range_start``
    (a multi-day / long event therefore appears on every day its interval
    covers, mirroring the ServiceEvent provider's overlap rule). ``tab="all"``
    is used so past and future serving both appear — the calendar is a range
    surface, not the My Serving upcoming/past agenda.
    """
    items = []
    for member in my_serving_assignments(user, tab="all"):
        event = member.assignment.service_event
        if event.start_datetime >= range_end:
            continue
        if get_service_event_effective_end(event) <= range_start:
            continue
        items.append(_build_item(member))
    return items


def register():
    """Register the personal serving calendar provider (idempotent)."""
    from church_calendar.providers import get_registered_range_provider_keys

    if "ministry" in get_registered_range_provider_keys():
        return
    register_range_provider("ministry", provide_my_serving_items)
