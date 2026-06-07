from dataclasses import dataclass

from events.models import ServiceEvent

from ..models import TeamAssignment, TeamAssignmentMember


MODE_ANCHOR = "anchor"
MODE_TEAM = "team"
VALID_MODES = {MODE_ANCHOR, MODE_TEAM}


@dataclass
class CopyForwardSuggestion:
    mode: str
    source_assignment: TeamAssignment
    source_members: list


def _source_assignment_queryset(target_event, ministry_team):
    return (
        TeamAssignment.objects.select_related(
            "service_event",
            "service_event__rotation_anchor_team",
            "ministry_team",
        )
        .filter(
            ministry_team=ministry_team,
            service_event__event_type=target_event.event_type,
            service_event__start_datetime__lt=target_event.start_datetime,
        )
        .exclude(
            service_event__status__in=[
                ServiceEvent.STATUS_DRAFT,
                ServiceEvent.STATUS_CANCELLED,
            ]
        )
        .exclude(status=TeamAssignment.STATUS_CANCELLED)
        .order_by("-service_event__start_datetime", "-id")
    )


def find_copy_forward_suggestion(target_event, ministry_team, mode):
    if mode not in VALID_MODES:
        return None

    queryset = _source_assignment_queryset(target_event, ministry_team)
    if mode == MODE_ANCHOR:
        if not target_event.rotation_anchor_team_id:
            return None
        queryset = queryset.filter(
            service_event__rotation_anchor_team_id=target_event.rotation_anchor_team_id,
        )

    for source_assignment in queryset:
        source_members = list(
            TeamAssignmentMember.objects.select_related(
                "membership",
                "membership__user",
            )
            .filter(
                assignment=source_assignment,
                membership__is_active=True,
            )
            .order_by(
                "membership__display_name",
                "membership__user__first_name",
                "membership__user__username",
            )
        )
        if source_members:
            return CopyForwardSuggestion(
                mode=mode,
                source_assignment=source_assignment,
                source_members=[
                    assignment_member.membership for assignment_member in source_members
                ],
            )

    return None
