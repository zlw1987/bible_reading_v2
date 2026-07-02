"""Studies module's Today provider (MODULAR-CORE.3B).

Owns the Bible Study V2 landing context and the Today / This Week visible
meeting rows of the home context. The provider bodies moved here from
``reading.views``; registration stays explicit — ``reading.views`` calls
:func:`register` at import time, before any ``home()`` request.

Visibility is unchanged: ``BibleStudyMeetingAudienceScope`` rows matched
through active primary membership are only a pre-filter, each meeting's
``can_be_seen_by`` stays the final authority, and zero-row meetings fail
closed for ordinary users. Meeting visibility is never serving — the signed-in
user's roles are recognised only via linked-user
``BibleStudyMeetingRole.user`` rows on an already-visible meeting.
"""

from core.today_providers import register_today_provider
from core.today_windows import get_today_week_windows

from .models import (
    BibleStudyLesson,
    BibleStudyMeeting,
    BibleStudyMeetingRole,
    BibleStudySeries,
)
from .visibility import get_membership_audience_candidate_unit_ids
from .views import get_v2_landing_context

TODAY_DEFAULTS = {
    "study_meeting_context": {},
    "today_study_meetings": [],
    "week_study_meetings": [],
}


def get_visible_study_meetings_for_window(user, start_datetime, end_datetime, limit=3):
    """Visible V2 Bible Study meetings in a local-date bucket.

    This mirrors ``get_v2_landing_context``: audience-row candidates from the
    user's active primary membership are only a pre-filter, and each meeting's
    ``can_be_seen_by`` remains the final authority.
    """
    audience_candidate_unit_ids = get_membership_audience_candidate_unit_ids(user)
    if not audience_candidate_unit_ids:
        return []

    visible_statuses = [
        BibleStudyMeeting.STATUS_PUBLISHED,
        BibleStudyMeeting.STATUS_COMPLETED,
    ]
    base_meetings = BibleStudyMeeting.objects.select_related(
        "lesson",
        "lesson__series",
        "anchor_unit",
    ).prefetch_related(
        "audience_scope_links__unit",
    ).filter(
        meeting_datetime__gte=start_datetime,
        meeting_datetime__lt=end_datetime,
        status__in=visible_statuses,
        lesson__status__in=[
            BibleStudyLesson.STATUS_PUBLISHED,
            BibleStudyLesson.STATUS_COMPLETED,
        ],
        lesson__series__is_active=True,
        lesson__series__status__in=[
            BibleStudySeries.STATUS_PUBLISHED,
            BibleStudySeries.STATUS_COMPLETED,
        ],
        audience_scope_links__unit_id__in=audience_candidate_unit_ids,
    ).distinct().order_by("meeting_datetime")

    meetings = []
    for meeting in base_meetings:
        if meeting.can_be_seen_by(user):
            meetings.append(meeting)
        if len(meetings) >= limit:
            break
    return meetings


def get_my_study_meeting_roles(user, meeting):
    """The signed-in user's linked roles for an already-visible meeting.

    Identity is recognised only via ``BibleStudyMeetingRole.user == user``. The
    meeting must already have passed the existing visible-meeting logic (this
    helper is only called with ``study_meeting_context["primary_meeting"]``).
    Display-name-only rows, other people's roles, and other groups' meetings are
    never matched, so Today never guesses role ownership from free-text names.
    """
    if meeting is None:
        return []
    return list(
        BibleStudyMeetingRole.objects.filter(meeting=meeting, user=user)
        .select_related("user")
        .order_by("role", "id")
    )


def get_study_meeting_rows_for_window(user, start_datetime, end_datetime):
    return [
        {
            "meeting": meeting,
            "roles": get_my_study_meeting_roles(user, meeting),
        }
        for meeting in get_visible_study_meetings_for_window(
            user,
            start_datetime,
            end_datetime,
        )
    ]


def studies_today_provider(request):
    """Bible Study V2 landing context plus Today / This Week visible meetings
    (audience rows + membership; meeting visibility is not serving)."""
    today_start, tomorrow_start, week_end = get_today_week_windows()

    return {
        "study_meeting_context": get_v2_landing_context(request.user),
        "today_study_meetings": get_study_meeting_rows_for_window(
            request.user,
            today_start,
            tomorrow_start,
        ),
        "week_study_meetings": get_study_meeting_rows_for_window(
            request.user,
            tomorrow_start,
            week_end,
        ),
    }


def register():
    """Register the studies Today provider (called from ``reading.views``)."""
    register_today_provider(
        "studies",
        studies_today_provider,
        defaults=TODAY_DEFAULTS,
    )
