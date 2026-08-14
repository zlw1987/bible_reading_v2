"""Directed notifications for explicit ServiceEvent serving assignments.

This ministry-owned producer resolves one linked serving user per current
``TeamAssignmentMember`` and emits only through Core. It deliberately does not
infer recipients from event audience, church belonging, management authority,
or any other source.
"""

from dataclasses import dataclass

from django.urls import reverse

from core.notification_delivery import emit_notification

from ..models import TeamAssignment


@dataclass(frozen=True)
class AssignmentNotificationState:
    """The source facts needed to compare one successful assignment mutation."""

    existed: bool
    service_event_id: int | None
    status: str | None
    membership_ids: frozenset[int]


def capture_assignment_notification_state(assignment):
    """Capture assignment/member state before a form mutates its instance."""

    if not assignment or not assignment.pk:
        return AssignmentNotificationState(
            existed=False,
            service_event_id=None,
            status=None,
            membership_ids=frozenset(),
        )

    return AssignmentNotificationState(
        existed=True,
        service_event_id=assignment.service_event_id,
        status=assignment.status,
        membership_ids=frozenset(
            assignment.assignment_members.values_list("membership_id", flat=True)
        ),
    )


def _recipient_language(user):
    """Use the recipient's persisted preference, with an English fallback."""

    profile = getattr(user, "profile", None)
    return "zh" if getattr(profile, "preferred_language", None) == "zh" else "en"


def _notification_text(assignment, *, language, kind):
    if language == "zh":
        title = "新的服事安排" if kind == "assigned" else "服事安排已更新"
    else:
        title = (
            "New serving assignment"
            if kind == "assigned"
            else "Serving assignment updated"
        )
    body = (
        f"{assignment.service_event.get_title(language)} · "
        f"{assignment.ministry_team.get_name(language)}"
    )
    return title, body


def _updated_mutation_token(assignment):
    """Stable for repeated producer calls after one save; new on later saves."""

    return assignment.updated_at.isoformat(timespec="microseconds")


def emit_assignment_notifications(assignment, *, previous_state, actor=None):
    """Emit the low-noise NOTIFY.1C payloads for one completed source write.

    Newly created member rows take priority and receive ``assigned``. Retained
    rows receive at most one ``updated`` payload when the assignment moved to a
    different ServiceEvent and/or transitioned from cancelled to active.
    """

    event_changed = (
        previous_state.existed
        and previous_state.service_event_id != assignment.service_event_id
    )
    reactivated = (
        previous_state.existed
        and previous_state.status == TeamAssignment.STATUS_CANCELLED
        and assignment.status != TeamAssignment.STATUS_CANCELLED
    )

    if assignment.status == TeamAssignment.STATUS_CANCELLED:
        return 0
    if not assignment.ministry_team.is_active:
        return 0
    if assignment.service_event.status in {
        assignment.service_event.STATUS_DRAFT,
        assignment.service_event.STATUS_CANCELLED,
    }:
        return 0

    emitted_count = 0
    mutation_token = _updated_mutation_token(assignment)
    members = (
        assignment.assignment_members.select_related(
            "membership__user__profile",
            "assignment__service_event",
            "assignment__ministry_team",
        )
        .filter(membership__is_active=True, membership__user__isnull=False)
        .order_by("id")
    )
    for member in members:
        is_new = member.membership_id not in previous_state.membership_ids
        if is_new:
            kind = "assigned"
            dedupe_key = f"ministry:tam:{member.id}:assigned"
        elif event_changed or reactivated:
            kind = "updated"
            dedupe_key = (
                f"ministry:tam:{member.id}:updated:{mutation_token}"
            )
        else:
            continue

        recipient = member.membership.user
        language = _recipient_language(recipient)
        title, body = _notification_text(
            assignment,
            language=language,
            kind=kind,
        )
        scheduled = emit_notification(
            recipient=recipient,
            source_module="ministry",
            notification_type=f"team_assignment.{kind}",
            title=title,
            body=body,
            target_url=(
                f"{reverse('my_serving')}?tab=all"
                f"#serving-assignment-{member.id}"
            ),
            dedupe_key=dedupe_key,
            source_model_label="ministry.TeamAssignmentMember",
            source_object_id=str(member.id),
            actor=actor,
            metadata={},
        )
        emitted_count += int(scheduled)

    return emitted_count
