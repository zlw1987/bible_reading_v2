from collections import defaultdict
from urllib.parse import urlencode

from django.urls import reverse
from django.utils import timezone

from events.models import ServiceEvent

from ..models import MinistryTeam, TeamAssignment
from ..permissions import can_manage_team_assignment_for_team
from .assignment_coverage import (
    assignment_coverage_queryset,
    build_assignment_coverage,
    events_with_coverage_queryset,
)


SUNDAY_BOARD_WINDOW_WEEKS = 8

BOARD_CELL_MISSING = "missing"
BOARD_CELL_EMPTY = "empty"
BOARD_CELL_SCHEDULED = "scheduled"
BOARD_CELL_NOT_PARTICIPATING = "not_participating"

BOARD_ASSIGNMENT_STATUSES = (
    TeamAssignment.STATUS_SCHEDULED,
    TeamAssignment.STATUS_CONFIRMED,
    TeamAssignment.STATUS_PREPARED,
)


def sunday_board_window(today=None):
    start_date = today or timezone.localdate()
    return start_date, start_date + timezone.timedelta(weeks=SUNDAY_BOARD_WINDOW_WEEKS)


def _team_schedule_action_url(
    *, team_id, start_date, end_date, event_id=None, assignment_id=None
):
    params = {
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "event_type": ServiceEvent.EVENT_SUNDAY_SERVICE,
    }
    if assignment_id is not None:
        params["assignment"] = assignment_id
    elif event_id is not None:
        params["event"] = event_id
    return f"{reverse('team_schedule', args=[team_id])}?{urlencode(params)}"


def build_sunday_schedule_board(
    *,
    user,
    manageable_team_ids,
    global_assignment_manager,
    language="en",
    today=None,
):
    """Build the side-effect-free MO-S.6B Sunday coordination projection.

    Row eligibility intentionally follows the approved operational scheduling
    rule, not ordinary ServiceEvent audience visibility. Exact-team schedulers
    receive a row only when one of their own manageable teams is required or
    actively assigned. Global assignment managers receive the bounded Sunday
    set with any required team or active assignment.

    Returned cells are projection dictionaries. They never include assignment
    notes, member contact/profile fields, or confirmation detail.
    """

    start_date, end_date = sunday_board_window(today=today)
    manageable_team_ids = set(manageable_team_ids)

    candidate_events = list(
        events_with_coverage_queryset()
        .filter(
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
            start_datetime__date__gte=start_date,
            start_datetime__date__lte=end_date,
        )
        .exclude(
            status__in=[
                ServiceEvent.STATUS_DRAFT,
                ServiceEvent.STATUS_CANCELLED,
            ]
        )
        .order_by("start_datetime", "id")
    )
    candidate_event_ids = [event.id for event in candidate_events]
    assignments = list(
        assignment_coverage_queryset()
        .filter(
            service_event_id__in=candidate_event_ids,
            status__in=BOARD_ASSIGNMENT_STATUSES,
        )
        .order_by(
            "service_event__start_datetime",
            "ministry_team__name",
            "id",
        )
    )

    assignments_by_event_team = defaultdict(list)
    assignment_team_ids_by_event = defaultdict(set)
    for assignment in assignments:
        assignments_by_event_team[
            (assignment.service_event_id, assignment.ministry_team_id)
        ].append(assignment)
        assignment_team_ids_by_event[assignment.service_event_id].add(
            assignment.ministry_team_id
        )

    required_team_ids_by_event = {}
    eligible_events = []
    for event in candidate_events:
        required_team_ids = {
            link.ministry_team_id for link in event.required_team_links.all()
        }
        required_team_ids_by_event[event.id] = required_team_ids
        participating_team_ids = required_team_ids | assignment_team_ids_by_event[event.id]
        if not participating_team_ids:
            continue
        if not global_assignment_manager and not (
            participating_team_ids & manageable_team_ids
        ):
            continue
        eligible_events.append(event)

    eligible_event_ids = {event.id for event in eligible_events}
    eligible_assignments = [
        assignment
        for assignment in assignments
        if assignment.service_event_id in eligible_event_ids
    ]
    participating_team_ids = set()
    for event in eligible_events:
        participating_team_ids.update(required_team_ids_by_event[event.id])
        participating_team_ids.update(assignment_team_ids_by_event[event.id])

    teams = list(
        MinistryTeam.objects.filter(id__in=participating_team_ids).order_by("name", "id")
    )
    coverage_by_event = build_assignment_coverage(
        eligible_events,
        eligible_assignments,
        language=language,
    )
    coverage_rows_by_event_team = defaultdict(list)
    for event_id, coverage in coverage_by_event.items():
        for coverage_row in coverage["rows"]:
            coverage_rows_by_event_team[(event_id, coverage_row["team"].id)].append(
                coverage_row
            )

    rows = []
    for event in eligible_events:
        cells = []
        required_team_ids = required_team_ids_by_event[event.id]
        event_assignment_team_ids = assignment_team_ids_by_event[event.id]
        for team in teams:
            is_required = team.id in required_team_ids
            team_assignments = assignments_by_event_team.get((event.id, team.id), [])
            participates = is_required or team.id in event_assignment_team_ids
            if not participates:
                cells.append(
                    {
                        "team": team,
                        "participates": False,
                        "is_required": False,
                        "is_additional": False,
                        "state": BOARD_CELL_NOT_PARTICIPATING,
                        "member_names": [],
                        "has_duplicate_assignments": False,
                        "can_edit": False,
                        "action_url": "",
                    }
                )
                continue

            projection_rows = coverage_rows_by_event_team[(event.id, team.id)]
            member_names = []
            seen_member_names = set()
            for projection_row in projection_rows:
                for member in projection_row["members"]:
                    name = member["name"]
                    if name not in seen_member_names:
                        seen_member_names.add(name)
                        member_names.append(name)

            if not team_assignments:
                state = BOARD_CELL_MISSING
            elif member_names:
                state = BOARD_CELL_SCHEDULED
            else:
                state = BOARD_CELL_EMPTY

            has_duplicate_assignments = len(team_assignments) > 1
            can_edit = (
                not has_duplicate_assignments
                and team.is_active
                and team.is_assignable
                and can_manage_team_assignment_for_team(user, team)
            )
            action_url = ""
            if can_edit:
                action_url = _team_schedule_action_url(
                    team_id=team.id,
                    start_date=start_date,
                    end_date=end_date,
                    event_id=event.id if not team_assignments else None,
                    assignment_id=(team_assignments[0].id if team_assignments else None),
                )

            cells.append(
                {
                    "team": team,
                    "participates": True,
                    "is_required": is_required,
                    "is_additional": not is_required,
                    "state": state,
                    "member_names": member_names,
                    "has_duplicate_assignments": has_duplicate_assignments,
                    "can_edit": can_edit,
                    "action_url": action_url,
                }
            )

        rows.append({"event": event, "cells": cells})

    return {
        "start_date": start_date,
        "end_date": end_date,
        "teams": teams,
        "rows": rows,
    }
