"""Ministry module's setup/readiness check provider (MODULAR-CORE.5A).

Owns the ministry-structure and TeamAssignment / My Serving readiness sections
of the pre-user-trial setup audit. The section bodies moved here from
``accounts.trial_setup_readiness``; registration stays explicit —
``accounts.trial_setup_readiness`` calls :func:`register` at import time,
before ``run_audit`` builds the report. The provider runs only when the
``ministry`` module is enabled (``core.setup_readiness.build_readiness_sections``).

This provider is strictly read-only. Serving stays explicit
(``TeamAssignmentMember`` / linked-user ``BibleStudyMeetingRole``);
``ChurchStructureMembership`` (belonging) is never treated as serving. The
ministry-structure classification is delegated to
``ministry.structure_readiness.run_audit`` so this provider does not re-derive
(or contradict) it.
"""

from django.db.models import Prefetch

from core.setup_readiness import ReadinessSection, register_readiness_provider
from events.models import ServiceEvent
from ministry.structure_readiness import run_audit as run_ministry_audit

from .models import TeamAssignment, TeamAssignmentMember


def _build_ministry_structure_section(ministry_audit):
    section = ReadinessSection(
        "ministry_structure", "2. Ministry Teams / Ministry Structure readiness"
    )
    stats = ministry_audit["stats"]
    details = ministry_audit["details"]

    section.add_info("active_teams", stats["active_teams"])
    section.add_info("assignable_teams", stats["assignable_teams"])
    section.add_info("container_teams", stats["non_assignable_teams"])

    for key in ("teams_multiple_active_primary_links", "parent_link_cycle_teams"):
        section.blocker(key, stats[key])
        for line in details.get(key, []):
            section.detail(key, line)

    for key in (
        "teams_no_active_parent_link",
        "assignable_teams_no_role_profile",
        "teams_missing_required_lead",
        "assignable_teams_no_active_membership",
    ):
        section.warning(key, stats[key])
        for line in details.get(key, []):
            section.detail(key, line)

    return section


def _build_serving_section(ministry_audit, now):
    section = ReadinessSection(
        "team_serving", "3. TeamAssignment / My Serving readiness"
    )
    stats = ministry_audit["stats"]
    details = ministry_audit["details"]

    # Blocker reused from the ministry audit (active serving assignment whose
    # team is no longer assignable). Counted here, not in section 2, so each
    # ministry counter lands in exactly one section.
    key = "active_assignments_on_non_assignable_team"
    section.blocker(key, stats[key])
    for line in details.get(key, []):
        section.detail(key, line)

    upcoming_event_ids = set(
        ServiceEvent.objects.filter(
            status=ServiceEvent.STATUS_PUBLISHED,
            start_datetime__gte=now,
        ).values_list("id", flat=True)
    )

    upcoming_assignments = (
        TeamAssignment.objects.filter(service_event_id__in=upcoming_event_ids)
        .exclude(status=TeamAssignment.STATUS_CANCELLED)
        .count()
    )
    section.add_info("upcoming_team_assignments", upcoming_assignments)

    # Serving members who are display-name-only (no linked user) cannot have the
    # assignment personalized into their My Serving. This is a serving-setup
    # warning, not a visibility/belonging signal.
    display_only_members = (
        TeamAssignmentMember.objects.filter(
            assignment__service_event_id__in=upcoming_event_ids,
            membership__is_active=True,
            membership__user__isnull=True,
        )
        .exclude(assignment__status=TeamAssignment.STATUS_CANCELLED)
        .select_related("assignment", "assignment__ministry_team", "membership")
    )
    display_only_count = 0
    for member in display_only_members:
        display_only_count += 1
        section.detail(
            "team_assignment_members_display_name_only",
            f"assignment_id={member.assignment_id} "
            f"team=#{member.assignment.ministry_team_id} "
            f"member={member.membership.get_display_name()!r}",
        )
    section.warning(
        "team_assignment_members_display_name_only", display_only_count
    )

    # Upcoming required-team coverage gaps: a published upcoming event names a
    # required team but has no non-cancelled assignment with at least one active
    # assigned member for it.
    gaps = _count_upcoming_required_team_gaps(now, section)
    section.warning("upcoming_required_team_gaps", gaps)

    return section


def _count_upcoming_required_team_gaps(now, section):
    events = (
        ServiceEvent.objects.filter(
            status=ServiceEvent.STATUS_PUBLISHED,
            start_datetime__gte=now,
        )
        .prefetch_related(
            "required_team_links__ministry_team",
            Prefetch(
                "team_assignments",
                queryset=TeamAssignment.objects.exclude(
                    status=TeamAssignment.STATUS_CANCELLED
                ).prefetch_related("assignment_members__membership"),
            ),
        )
        .order_by("start_datetime", "id")
    )

    gaps = 0
    for event in events:
        covered_team_ids = set()
        for assignment in event.team_assignments.all():
            has_active_member = any(
                am.membership.is_active
                for am in assignment.assignment_members.all()
            )
            if has_active_member:
                covered_team_ids.add(assignment.ministry_team_id)

        for link in event.required_team_links.all():
            if link.ministry_team_id not in covered_team_ids:
                gaps += 1
                section.detail(
                    "upcoming_required_team_gaps",
                    f"event_id={event.id} team=#{link.ministry_team_id} "
                    f"({link.ministry_team.get_name('en')})",
                )
    return gaps


def build(context):
    """Ministry-structure + TeamAssignment / My Serving readiness sections.

    Runs the ministry-structure audit once and derives both sections from it,
    preserving the previous single-call behavior.
    """
    ministry_audit = run_ministry_audit()
    return [
        _build_ministry_structure_section(ministry_audit),
        _build_serving_section(ministry_audit, context.now),
    ]


def register():
    """Register the ministry readiness provider (called from the audit runner)."""
    register_readiness_provider("ministry", build, module_key="ministry")
