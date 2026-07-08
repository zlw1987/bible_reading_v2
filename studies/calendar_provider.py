"""Church Calendar range provider for Bible Study V2 (CHURCH-CALENDAR.1B / 2B).

Owns two kinds of normalized :class:`~church_calendar.providers.CalendarItem`
values for the signed-in viewer in a half-open local range, both emitted by the
single ``studies`` provider (the registry allows one provider per source module,
so both stay gated by ``studies`` enablement):

* ``bible_study_meeting`` — ordinary member-visible V2 meetings. Visibility is
  the member-safe :func:`studies.visibility.member_visible_meetings_for` (no
  staff/capability bypass); a meeting is a point-in-time item anchored to
  ``meeting_datetime`` with no invented duration. This remains audience-only.

* ``bible_study_serving`` (CHURCH-CALENDAR.2B) — the viewer's OWN explicit Bible
  Study serving schedule. Serving is EXPLICIT: an item exists only from the
  viewer's own linked ``BibleStudyMeetingRole.user`` rows on a published/completed
  meeting whose lesson is published/completed and whose series is active. Serving
  is never inferred from ``ChurchStructureMembership`` (belonging), audience
  scopes, meeting visibility, or staff/superuser/manager authority, and other
  people's roles are never shown. Unlinked (display-name-only) roles create no
  personal item.

  The serving overlay is deliberately NOT gated on ordinary audience visibility:
  an explicit role holder outside the meeting audience still receives their own
  serving occurrence, mirroring the ServiceEvent SERVING-EVENT-VISIBILITY.1A
  end-state. The matching read gate for the meeting detail is the ``studies``-owned
  :func:`studies.permissions.user_has_explicit_bible_study_serving_role_for_meeting`,
  so an eligible role holder can open exactly that meeting's detail. This does not
  add them to the audience, does not reveal any other meeting, and grants no
  management authority. Ordinary ``bible_study_meeting`` calendar/list visibility
  is unchanged.

CHURCH-CALENDAR.2A-FU4 occurrence grouping: both item kinds carry the shared
presentation-only ``occurrence_key = "bible_study_meeting:<meeting.id>"``. The
calendar presentation layer therefore collapses the base meeting row and the
viewer's own serving rows for that same meeting into one occurrence (a month
serving summary / day subitems), instead of duplicate rows. ``occurrence_key`` is
presentation-only, never authorization; each serving item is emitted per role
(``source_id`` = ``BibleStudyMeetingRole.id``) so identities stay collision-safe
and the day view can list one subitem per role.

This module owns the studies adapter, query, lifecycle filtering, and item
construction. ``church_calendar`` is the only importer, via its explicit
registration site; this module imports no sibling source module (in particular it
does not import ``ministry`` — the explicit Bible Study serving semantics live in
``studies`` so the module stays self-contained and ``ministry`` never queries
``studies``).
"""

from django.urls import reverse

from church_calendar.providers import (
    ITEM_TYPE_BIBLE_STUDY_MEETING,
    ITEM_TYPE_BIBLE_STUDY_SERVING,
    CalendarItem,
    register_range_provider,
)

from .models import (
    BibleStudyLesson,
    BibleStudyMeeting,
    BibleStudyMeetingRole,
    BibleStudySeries,
)
from .templatetags.study_extras import meeting_role_label
from .visibility import member_visible_meetings_for


def _meeting_occurrence_key(meeting_id):
    """Shared FU4 grouping key for a meeting and its serving rows."""
    return f"bible_study_meeting:{meeting_id}"


def _build_meeting_item(meeting):
    detail_url = reverse("bible_study_meeting_detail", args=[meeting.id])
    return CalendarItem(
        item_type=ITEM_TYPE_BIBLE_STUDY_MEETING,
        source_id=meeting.id,
        title=meeting.lesson.get_title(),
        start=meeting.meeting_datetime,
        # Point-in-time: V1 plan forbids inventing a meeting duration.
        end=None,
        location=meeting.get_location() or "",
        detail_url=detail_url,
        # CHURCH-CALENDAR.2A-FU4: group the base meeting with the viewer's own
        # serving rows for it. Presentation-only, not authorization.
        occurrence_key=_meeting_occurrence_key(meeting.id),
        occurrence_title=meeting.lesson.get_title(),
        occurrence_detail_url=detail_url,
    )


def provide_bible_study_meeting_items(user, range_start, range_end):
    """Member-visible V2 meetings whose ``meeting_datetime`` is in the range.

    Point-in-time membership: a meeting belongs to the half-open range when
    ``range_start <= meeting_datetime < range_end``. This stays audience-only via
    the member-safe adapter; serving never widens it.
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
    return [_build_meeting_item(meeting) for meeting in meetings]


def _build_serving_item(role):
    """Build one ``bible_study_serving`` item from one linked serving role.

    ``source_id`` is the ``BibleStudyMeetingRole`` id (one item per role), so the
    identity ``(bible_study_serving, role_id)`` never collides with the meeting
    identity ``(bible_study_meeting, meeting_id)``, with sibling roles on the same
    meeting, or with the ministry ``my_serving`` items. FU4 grouping collapses all
    of a meeting's serving rows under one occurrence via the shared
    ``occurrence_key``; ``occurrence_role`` supplies the per-role label used as the
    month summary and day subitem.

    The item is read-only and deep-links to the member-facing
    ``bible_study_meeting_detail``. That is safe because
    :func:`studies.permissions.user_has_explicit_bible_study_serving_role_for_meeting`
    grants an explicit role holder read visibility to exactly that meeting detail;
    it never routes through an edit/manage/confirm/attendance/staff URL.
    """
    meeting = role.meeting
    role_label = meeting_role_label(role, "zh")
    lesson_title = meeting.lesson.get_title()
    detail_url = reverse("bible_study_meeting_detail", args=[meeting.id])
    return CalendarItem(
        item_type=ITEM_TYPE_BIBLE_STUDY_SERVING,
        source_id=role.id,
        title=f"{lesson_title} · {role_label}" if role_label else lesson_title,
        start=meeting.meeting_datetime,
        # Point-in-time: a Bible Study meeting has no stored end; do not invent
        # a serving duration.
        end=None,
        location=meeting.get_location() or "",
        detail_url=detail_url,
        occurrence_key=_meeting_occurrence_key(meeting.id),
        occurrence_role=role_label,
        occurrence_title=lesson_title,
        occurrence_detail_url=detail_url,
    )


def provide_bible_study_serving_items(user, range_start, range_end):
    """The viewer's OWN explicit Bible Study serving roles overlapping the range.

    Explicit personal serving only: linked ``BibleStudyMeetingRole.user == user``
    rows on a meeting whose ``meeting_datetime`` is in the half-open range and
    whose meeting/lesson/series lifecycle is published-or-completed with an active
    series. One item is emitted per role. Other people's roles, display-name-only
    (unlinked) roles, and membership/audience visibility alone never create an
    item.

    Deliberately NOT gated on ordinary meeting audience visibility: an explicit
    role holder outside the audience still receives their own serving occurrence
    (mirroring SERVING-EVENT-VISIBILITY.1A). The paired meeting-detail read gate is
    :func:`studies.permissions.user_has_explicit_bible_study_serving_role_for_meeting`.
    This never widens ordinary meeting list/calendar visibility and never reveals
    any meeting the viewer does not personally serve.
    """
    if not getattr(user, "is_authenticated", False):
        return []

    roles = (
        BibleStudyMeetingRole.objects.select_related(
            "meeting",
            "meeting__lesson",
            "meeting__lesson__series",
        )
        .filter(
            user=user,
            meeting__meeting_datetime__gte=range_start,
            meeting__meeting_datetime__lt=range_end,
            meeting__status__in=[
                BibleStudyMeeting.STATUS_PUBLISHED,
                BibleStudyMeeting.STATUS_COMPLETED,
            ],
            meeting__lesson__status__in=[
                BibleStudyLesson.STATUS_PUBLISHED,
                BibleStudyLesson.STATUS_COMPLETED,
            ],
            meeting__lesson__series__is_active=True,
            meeting__lesson__series__status__in=[
                BibleStudySeries.STATUS_PUBLISHED,
                BibleStudySeries.STATUS_COMPLETED,
            ],
        )
        .order_by("meeting__meeting_datetime", "meeting_id", "role", "id")
    )
    return [_build_serving_item(role) for role in roles]


def provide_studies_calendar_items(user, range_start, range_end):
    """Both ordinary Bible Study meeting items and personal serving items.

    A viewer who both belongs to a meeting's audience and serves it receives the
    base ``bible_study_meeting`` item plus one ``bible_study_serving`` item per
    role, all with distinct identities. FU4 grouping then presents them as one
    occurrence (base meeting + serving subitems), never a silent collision.
    """
    return [
        *provide_bible_study_meeting_items(user, range_start, range_end),
        *provide_bible_study_serving_items(user, range_start, range_end),
    ]


def register():
    """Register the Bible Study calendar provider (idempotent)."""
    from church_calendar.providers import get_registered_range_provider_keys

    if "studies" in get_registered_range_provider_keys():
        return
    register_range_provider("studies", provide_studies_calendar_items)
