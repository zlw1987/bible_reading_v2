from collections import defaultdict

from django.db.models import Prefetch

from events.models import ServiceEvent, ServiceEventRequiredTeam

from ..models import TeamAssignment, TeamAssignmentMember


COVERAGE_ASSIGNED = "assigned"
COVERAGE_EMPTY_ASSIGNMENT = "empty_assignment"
COVERAGE_UNASSIGNED = "unassigned"
COVERAGE_ADDITIONAL = "additional"


def coverage_text(language):
    labels = {
        "en": {
            "assigned": "Assigned",
            "assigned_people": "Assigned {count} people",
            "assigned_person": "Assigned 1 person",
            "empty_assignment": "Assignment exists, no people assigned",
            "unassigned": "Unassigned",
            "additional": "Additional assignment",
            "confirmed": "Confirmed",
            "awaiting": "Awaiting confirmation",
        },
        "zh": {
            "assigned": "已安排",
            "assigned_people": "已安排 {count} 人",
            "assigned_person": "已安排 1 人",
            "empty_assignment": "已有排班，暂无成员",
            "unassigned": "未安排",
            "additional": "额外安排",
            "confirmed": "已确认",
            "awaiting": "待确认",
        },
    }
    return labels.get(language, labels["en"])


def required_team_prefetch():
    return Prefetch(
        "required_team_links",
        queryset=ServiceEventRequiredTeam.objects.select_related("ministry_team").order_by(
            "ministry_team__name",
        ),
    )


def assignment_member_prefetch():
    return Prefetch(
        "assignment_members",
        queryset=TeamAssignmentMember.objects.select_related(
            "membership",
            "membership__user",
        ).order_by(
            "membership__display_name",
            "membership__user__first_name",
            "membership__user__username",
        ),
    )


def assignment_coverage_queryset():
    return TeamAssignment.objects.select_related(
        "service_event",
        "service_event__ministry_context",
        "service_event__rotation_anchor_team",
        "ministry_team",
    ).prefetch_related(
        assignment_member_prefetch(),
        # SE-CTX.1A: host/language label falls back to audience-row-derived
        # ministry context when the legacy FK is null; batch the audience rows.
        "service_event__audience_scope_links__unit",
    ).order_by(
        "service_event__start_datetime",
        "ministry_team__name",
    )


def events_with_coverage_queryset():
    return ServiceEvent.objects.select_related(
        "district",
        "host_language_unit",
        "ministry_context",
        "rotation_anchor_team",
        "small_group",
        "created_by",
    ).prefetch_related(
        required_team_prefetch(),
        # SE-CTX.1A: host/language label falls back to audience-row-derived
        # ministry context when the legacy FK is null; batch the audience rows.
        "audience_scope_links__unit",
    )


def member_display(assignment_member, language="en"):
    text = coverage_text(language)
    return {
        "name": assignment_member.membership.get_display_name(),
        "confirmed": bool(assignment_member.confirmed_at),
        "status_label": (
            text["confirmed"] if assignment_member.confirmed_at else text["awaiting"]
        ),
    }


def build_assignment_coverage(
    events,
    assignments,
    *,
    language="en",
    allowed_team_ids=None,
    allowed_assignment_ids=None,
):
    text = coverage_text(language)
    restrict_teams = allowed_team_ids is not None
    restrict_assignments = allowed_assignment_ids is not None
    allowed_team_ids = set(allowed_team_ids or [])
    allowed_assignment_ids = set(allowed_assignment_ids or [])

    assignments_by_event = defaultdict(list)
    assignments_by_event_team = defaultdict(list)
    for assignment in assignments:
        if restrict_assignments and assignment.id not in allowed_assignment_ids:
            continue
        if restrict_teams and assignment.ministry_team_id not in allowed_team_ids:
            continue
        assignments_by_event[assignment.service_event_id].append(assignment)
        assignments_by_event_team[
            (assignment.service_event_id, assignment.ministry_team_id)
        ].append(assignment)

    coverage_by_event = {}
    for event in events:
        rows = []
        required_team_ids = []
        required_links = list(getattr(event, "required_team_links").all())

        for required_link in required_links:
            team = required_link.ministry_team
            if restrict_teams and team.id not in allowed_team_ids:
                continue

            required_team_ids.append(team.id)
            team_assignments = assignments_by_event_team.get((event.id, team.id), [])
            if not team_assignments:
                rows.append(
                    {
                        "kind": COVERAGE_UNASSIGNED,
                        "team": team,
                        "assignment": None,
                        "members": [],
                        "count": 0,
                        "summary_label": text["unassigned"],
                    }
                )
                continue

            for assignment in team_assignments:
                members = [
                    member_display(assignment_member, language)
                    for assignment_member in assignment.assignment_members.all()
                    if assignment_member.membership.is_active
                ]
                count = len(members)
                if count == 0:
                    kind = COVERAGE_EMPTY_ASSIGNMENT
                    summary = text["empty_assignment"]
                else:
                    kind = COVERAGE_ASSIGNED
                    summary = (
                        text["assigned_person"]
                        if count == 1
                        else text["assigned_people"].format(count=count)
                    )
                rows.append(
                    {
                        "kind": kind,
                        "team": team,
                        "assignment": assignment,
                        "members": members,
                        "count": count,
                        "summary_label": summary,
                    }
                )

        required_team_id_set = set(required_team_ids)
        for assignment in assignments_by_event.get(event.id, []):
            if assignment.ministry_team_id in required_team_id_set:
                continue
            members = [
                member_display(assignment_member, language)
                for assignment_member in assignment.assignment_members.all()
                if assignment_member.membership.is_active
            ]
            rows.append(
                {
                    "kind": COVERAGE_ADDITIONAL,
                    "team": assignment.ministry_team,
                    "assignment": assignment,
                    "members": members,
                    "count": len(members),
                    "summary_label": text["additional"],
                }
            )

        coverage_by_event[event.id] = {
            "event": event,
            "rows": rows,
            "missing_count": sum(
                1 for row in rows if row["kind"] == COVERAGE_UNASSIGNED
            ),
        }

    return coverage_by_event


def count_upcoming_required_team_gaps(events, assignments):
    coverage = build_assignment_coverage(events, assignments, language="en")
    return sum(event_coverage["missing_count"] for event_coverage in coverage.values())
