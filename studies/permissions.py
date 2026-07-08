"""Studies-owned read-visibility predicates (CHURCH-CALENDAR.2B).

SERVING-EVENT-VISIBILITY.1A established that an explicit ServiceEvent serving
assignment grants read-only visibility to that one event's detail (layered beside
``ServiceEvent.can_be_seen_by`` in the event detail view only). This module
mirrors that boundary for Bible Study: an explicit linked
``BibleStudyMeetingRole`` grants the assignee read-only visibility to that one
meeting's detail, and nothing else.

It never adds the user to the meeting audience, never grants visibility to any
other meeting, applies no staff/superuser/manager bypass (management stays with
the existing Bible Study management permissions), and is an *additional* read gate
for the single meeting detail only. Ordinary member-safe list/calendar audience
visibility must not consult it.
"""

from core.module_registry import get_enabled_module_keys

from .models import (
    BibleStudyLesson,
    BibleStudyMeetingRole,
    BibleStudySeries,
)


def user_has_explicit_bible_study_serving_role_for_meeting(user, meeting):
    """True when ``user`` holds an explicit linked serving role on exactly ``meeting``.

    CHURCH-CALENDAR.2B read-visibility grant predicate for a single Bible Study
    meeting detail, mirroring SERVING-EVENT-VISIBILITY.1A. Serving is explicit
    only: the signed-in user's own linked ``BibleStudyMeetingRole`` on this exact
    meeting, with the meeting/lesson/series in a published-or-completed lifecycle
    and the series active (the same lifecycle the ``bible_study_serving`` calendar
    overlay uses). It never adds the user to the meeting audience, never grants
    visibility to any other meeting, and applies no staff/superuser/manager bypass.

    Fails closed for anonymous users, a missing meeting, and draft/cancelled
    meetings. When the ``studies`` module is disabled it returns ``False`` and runs
    no query, so a disabled studies never grants serving-based visibility.
    """
    if meeting is None or not getattr(user, "is_authenticated", False):
        return False

    # Draft/cancelled meetings never become visible through serving.
    if meeting.status in {meeting.STATUS_DRAFT, meeting.STATUS_CANCELLED}:
        return False

    # Disabled studies grants no serving visibility and runs no serving query.
    if "studies" not in get_enabled_module_keys():
        return False

    return BibleStudyMeetingRole.objects.filter(
        meeting=meeting,
        user=user,
        meeting__lesson__status__in=[
            BibleStudyLesson.STATUS_PUBLISHED,
            BibleStudyLesson.STATUS_COMPLETED,
        ],
        meeting__lesson__series__is_active=True,
        meeting__lesson__series__status__in=[
            BibleStudySeries.STATUS_PUBLISHED,
            BibleStudySeries.STATUS_COMPLETED,
        ],
    ).exists()
