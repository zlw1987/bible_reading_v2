"""Directed notifications for explicit Bible Study meeting serving roles.

This studies-owned producer resolves only the linked ``BibleStudyMeetingRole``
user and emits through the Core notification port. It deliberately does not
infer recipients from meeting audience, Church Structure belonging, coworker
roles, management authority, or staff status.
"""

from dataclasses import dataclass

from django.urls import reverse

from core.notification_delivery import emit_notification

from .models import (
    BibleStudyLesson,
    BibleStudyMeeting,
    BibleStudySeries,
)
from .templatetags.study_extras import meeting_role_label


@dataclass(frozen=True)
class MeetingRoleNotificationState:
    """Meaningful source facts captured before a ModelForm mutates its instance."""

    existed: bool
    user_id: int | None
    role: str | None
    meeting_id: int | None


def capture_meeting_role_notification_state(meeting_role):
    """Capture the pre-save state needed to classify one successful mutation."""

    if not meeting_role or not meeting_role.pk:
        return MeetingRoleNotificationState(
            existed=False,
            user_id=None,
            role=None,
            meeting_id=None,
        )

    return MeetingRoleNotificationState(
        existed=True,
        user_id=meeting_role.user_id,
        role=meeting_role.role,
        meeting_id=meeting_role.meeting_id,
    )


def _recipient_language(user):
    """Use the recipient's persisted preference, with an English fallback."""

    profile = getattr(user, "profile", None)
    return "zh" if getattr(profile, "preferred_language", None) == "zh" else "en"


def _is_personal_serving_eligible(meeting_role):
    """Mirror the existing explicit-serving lifecycle without an audience gate."""

    recipient = meeting_role.user
    if recipient is None or not recipient.is_active:
        return False

    meeting = meeting_role.meeting
    lesson = meeting.lesson
    series = lesson.series
    return bool(
        meeting.status
        in {
            BibleStudyMeeting.STATUS_PUBLISHED,
            BibleStudyMeeting.STATUS_COMPLETED,
        }
        and lesson.status
        in {
            BibleStudyLesson.STATUS_PUBLISHED,
            BibleStudyLesson.STATUS_COMPLETED,
        }
        and series.is_active
        and series.status
        in {
            BibleStudySeries.STATUS_PUBLISHED,
            BibleStudySeries.STATUS_COMPLETED,
        }
    )


def _notification_text(meeting_role, *, language, kind):
    if language == "zh":
        title = "新的查经服事安排" if kind == "assigned" else "查经服事安排已更新"
    else:
        title = (
            "New Bible Study serving role"
            if kind == "assigned"
            else "Bible Study serving role updated"
        )
    body = (
        f"{meeting_role.meeting.lesson.get_title(language)} · "
        f"{meeting_role_label(meeting_role, language)}"
    )
    return title, body


def _mutation_token(meeting_role):
    """Stable for repeated calls after one save and new on later genuine saves."""

    return meeting_role.updated_at.isoformat(timespec="microseconds")


def emit_meeting_role_notification(meeting_role, *, previous_state, actor=None):
    """Emit at most one NOTIFY.1D payload for a completed create/edit save."""

    if not meeting_role.pk or not _is_personal_serving_eligible(meeting_role):
        return 0

    recipient_changed_to_linked_user = (
        meeting_role.user_id is not None
        and (
            not previous_state.existed
            or previous_state.user_id != meeting_role.user_id
        )
    )
    same_user_role_changed = (
        previous_state.existed
        and previous_state.user_id is not None
        and previous_state.user_id == meeting_role.user_id
        and previous_state.role != meeting_role.role
    )

    if recipient_changed_to_linked_user:
        kind = "assigned"
    elif same_user_role_changed:
        kind = "updated"
    else:
        return 0

    language = _recipient_language(meeting_role.user)
    title, body = _notification_text(
        meeting_role,
        language=language,
        kind=kind,
    )
    scheduled = emit_notification(
        recipient=meeting_role.user,
        source_module="studies",
        notification_type=f"bible_study_role.{kind}",
        title=title,
        body=body,
        target_url=reverse(
            "bible_study_meeting_detail",
            args=[meeting_role.meeting_id],
        ),
        dedupe_key=(
            f"studies:bsmr:{meeting_role.id}:{kind}:"
            f"{_mutation_token(meeting_role)}"
        ),
        source_model_label="studies.BibleStudyMeetingRole",
        source_object_id=str(meeting_role.id),
        actor=actor,
        metadata={},
    )
    return int(scheduled)
