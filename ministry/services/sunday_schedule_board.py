from collections import defaultdict
from urllib.parse import urlencode

from django.urls import reverse
from django.utils import timezone

from events.models import ServiceEvent

from ..models import MinistryTeam
from ..permissions import can_manage_team_assignment_for_team
from .assignment_coverage import (
    assignment_coverage_queryset,
    build_assignment_coverage,
    events_with_coverage_queryset,
)
from .worship_context import (
    CURRENT_ASSIGNMENT_STATUSES,
    WORSHIP_CONTEXT_AMBIGUOUS,
    WORSHIP_CONTEXT_ANCHOR_UNAVAILABLE,
    WORSHIP_CONTEXT_CONFLICT,
    WORSHIP_CONTEXT_NO_ANCHOR,
    build_worship_contexts,
)
from .worship_governance import inspect_worship_ownership_consistency


SUNDAY_BOARD_WINDOW_WEEKS = 8

BOARD_CELL_MISSING = "missing"
BOARD_CELL_EMPTY = "empty"
BOARD_CELL_SCHEDULED = "scheduled"
BOARD_CELL_NOT_PARTICIPATING = "not_participating"

BOARD_ASSIGNMENT_STATUSES = CURRENT_ASSIGNMENT_STATUSES


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
    receive a row only when one of their own manageable teams is required,
    actively assigned, or the exact valid selected Worship Team. Global
    assignment managers receive that same bounded operational Sunday set.

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
    ownership_inspections = {}
    valid_selected_team_ids_by_event = {}
    eligible_events = []
    for event in candidate_events:
        required_team_ids = {
            link.ministry_team_id for link in event.required_team_links.all()
        }
        required_team_ids_by_event[event.id] = required_team_ids
        valid_selected_team_id = None
        if event.rotation_anchor_team_id is not None:
            inspection = inspect_worship_ownership_consistency(event)
            ownership_inspections[event.id] = inspection
            if inspection.selected_team_is_eligible:
                valid_selected_team_id = event.rotation_anchor_team_id
        valid_selected_team_ids_by_event[event.id] = valid_selected_team_id
        participating_team_ids = (
            required_team_ids | assignment_team_ids_by_event[event.id]
        )
        if valid_selected_team_id is not None:
            participating_team_ids.add(valid_selected_team_id)
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
    display_team_ids_by_event = {}
    participating_team_ids = set()
    for event in eligible_events:
        display_team_ids = (
            required_team_ids_by_event[event.id]
            | assignment_team_ids_by_event[event.id]
        ) - {valid_selected_team_ids_by_event[event.id]}
        display_team_ids_by_event[event.id] = display_team_ids
        participating_team_ids.update(display_team_ids)

    teams = list(
        MinistryTeam.objects.filter(id__in=participating_team_ids).order_by("name", "id")
    )
    coverage_by_event = build_assignment_coverage(
        eligible_events,
        eligible_assignments,
        language=language,
    )
    worship_contexts = build_worship_contexts(
        eligible_events,
        ownership_inspections=ownership_inspections,
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
        display_team_ids = display_team_ids_by_event[event.id]
        for team in teams:
            is_required = team.id in required_team_ids
            team_assignments = assignments_by_event_team.get((event.id, team.id), [])
            participates = team.id in display_team_ids
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

        worship_context = dict(worship_contexts[event.id])
        worship_context.update(
            {
                "can_edit": False,
                "action_url": "",
                "action_kind": "",
            }
        )
        anchor_team = worship_context.get("anchor_team")
        anchor_assignments = (
            assignments_by_event_team.get((event.id, anchor_team.id), [])
            if anchor_team is not None
            else []
        )
        anchor_state_is_actionable = worship_context["state"] not in {
            WORSHIP_CONTEXT_NO_ANCHOR,
            WORSHIP_CONTEXT_ANCHOR_UNAVAILABLE,
            WORSHIP_CONTEXT_AMBIGUOUS,
            WORSHIP_CONTEXT_CONFLICT,
        }
        if (
            anchor_team is not None
            and valid_selected_team_ids_by_event[event.id] == anchor_team.id
            and anchor_state_is_actionable
            and len(anchor_assignments) <= 1
            and can_manage_team_assignment_for_team(user, anchor_team)
        ):
            worship_context["can_edit"] = True
            worship_context["action_kind"] = (
                "edit" if anchor_assignments else "schedule"
            )
            worship_context["action_url"] = _team_schedule_action_url(
                team_id=anchor_team.id,
                start_date=start_date,
                end_date=end_date,
                event_id=event.id if not anchor_assignments else None,
                assignment_id=(
                    anchor_assignments[0].id if anchor_assignments else None
                ),
            )

        rows.append(
            {
                "event": event,
                "worship_context": worship_context,
                "cells": cells,
            }
        )

    return {
        "start_date": start_date,
        "end_date": end_date,
        "teams": teams,
        "rows": rows,
    }
