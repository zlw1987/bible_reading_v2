"""Read-only Ministry Structure readiness audit (MINISTRY-STRUCTURE.1G).

This module inventories the ministry-structure foundation
(``MinistryTeam`` + ``MinistryTeamParentLink`` + the ministry role system added
in MINISTRY-STRUCTURE.1B, the ``is_assignable`` gate enforced in
MINISTRY-STRUCTURE.1F) and surfaces setup gaps as blockers / warnings / info.

It is strictly **read-only**: it creates, updates, or deletes nothing, has no
apply mode, makes no permission decision, and never repairs data. It does not
read ``ChurchStructureMembership`` as belonging-to-serving and does not treat
``MinistryTeamRoleAssignment`` as a permission source — those boundaries are
unchanged by this audit (see ``permission_notes``).

The findings mirror the locked architecture in
``docs/MINISTRY_STRUCTURE_ARCHITECTURE_PLAN.md``. Existing/historical/cancelled
serving assignments are preserved by design, so cancelled/completed assignments
on a now-non-assignable team are reported as *info*, while a genuinely active
(non-cancelled, non-completed) assignment on a non-assignable team is a blocker.
"""

from collections import OrderedDict

from django.db.models import Count, Q
from django.utils import timezone

from events.models import ServiceEventRequiredTeam

from .models import (
    MinistryTeam,
    MinistryTeamParentLink,
    MinistryTeamRoleAssignment,
    MinistryTeamRoleRequirement,
    TeamAssignment,
    TeamMembership,
)


LEAD_ROLE_CODE = "lead"

# Truly active (non-cancelled, non-completed) serving states. An assignment in
# one of these states on a non-assignable team is a blocker after 1F.
ACTIVE_ASSIGNMENT_STATUSES = (
    TeamAssignment.STATUS_SCHEDULED,
    TeamAssignment.STATUS_CONFIRMED,
    TeamAssignment.STATUS_PREPARED,
)

LEADERSHIP_ROLES = (TeamMembership.ROLE_LEAD, TeamMembership.ROLE_COORDINATOR)


# Inventory counters (plain summary; not severity-classified).
INVENTORY_KEYS = (
    "total_teams",
    "active_teams",
    "inactive_teams",
    "assignable_teams",
    "non_assignable_teams",
)

# Severity-classified counters. ``run_audit`` reports which of these are nonzero
# under ``blockers`` / ``warnings`` / ``info``.
BLOCKER_KEYS = (
    "active_assignments_on_non_assignable_team",
    "teams_multiple_active_primary_links",
    "parent_link_cycle_teams",
)

WARNING_KEYS = (
    "teams_no_active_parent_link",
    "teams_no_primary_parent_link",
    "teams_link_to_inactive_parent_team",
    "assignable_teams_no_role_profile",
    "teams_inactive_role_profile",
    "teams_missing_required_roles",
    "teams_missing_required_lead",
    "active_role_assignments_inactive_role_type",
    "duplicate_active_user_team_role_assignments",
    "required_event_links_to_non_assignable_team",
    "assignable_teams_no_active_membership",
    "assignable_teams_no_active_leadership",
)

INFO_KEYS = (
    "inactive_teams",
    "shared_teams_multi_active_parent_link",
    "teams_no_church_anchor",
    "teams_no_role_profile",
    "teams_with_optional_role_gaps",
    "cancelled_assignments_on_non_assignable_team",
    "completed_assignments_on_non_assignable_team",
)

# Categories that carry capped example rows under ``--verbose``.
VERBOSE_DETAIL_KEYS = BLOCKER_KEYS + WARNING_KEYS + (
    "shared_teams_multi_active_parent_link",
    "cancelled_assignments_on_non_assignable_team",
    "completed_assignments_on_non_assignable_team",
)

PERMISSION_NOTES = (
    "MinistryTeamRoleAssignment does NOT drive can_manage_ministry_team; "
    "TeamMembership.role / can_lead remains the permission source.",
    "CAP_MANAGE_MINISTRY_STRUCTURE is not wired into accounts/permissions yet.",
    "Delegated ministry management (ancestor-or-self lead) remains deferred.",
    "My Serving does not show ministry role assignments; Today is unchanged.",
)

ALL_COUNTER_KEYS = (
    INVENTORY_KEYS + BLOCKER_KEYS + WARNING_KEYS
    + tuple(k for k in INFO_KEYS if k not in INVENTORY_KEYS)
)


def _new_stats():
    stats = OrderedDict((key, 0) for key in ALL_COUNTER_KEYS)
    return stats


def _team_label(team):
    name = team.name_en or team.name
    return f"#{team.id} {name}"


def _detect_cycle_team_ids(active_team_edges):
    """Return the set of team ids that participate in an active parent cycle.

    ``active_team_edges`` maps child_id -> list of parent_team_ids (active links
    only). ``MinistryTeamParentLink.clean`` prevents creating cycles, so this is
    expected to be empty; it is computed defensively against bad DB state. The
    walk is bounded by ``seen`` so it terminates even on cyclic data.
    """
    cycle_ids = set()
    WHITE, GREY, BLACK = 0, 1, 2
    color = {}

    def visit(start):
        # Iterative DFS with an explicit stack to stay safe on large/cyclic data.
        stack = [(start, iter(active_team_edges.get(start, [])))]
        color[start] = GREY
        path = [start]
        while stack:
            node, children = stack[-1]
            advanced = False
            for parent in children:
                if color.get(parent, WHITE) == WHITE:
                    color[parent] = GREY
                    stack.append((parent, iter(active_team_edges.get(parent, []))))
                    path.append(parent)
                    advanced = True
                    break
                if color.get(parent) == GREY:
                    # Back-edge: everything currently on the path from parent up
                    # is part of a cycle.
                    if parent in path:
                        idx = path.index(parent)
                        cycle_ids.update(path[idx:])
            if advanced:
                continue
            color[node] = BLACK
            stack.pop()
            if path and path[-1] == node:
                path.pop()

    for team_id in active_team_edges:
        if color.get(team_id, WHITE) == WHITE:
            visit(team_id)
    return cycle_ids


def run_audit(team_id=None, include_inactive=False, target_date=None):
    """Return read-only ministry-structure readiness counters and samples.

    Read-only: never creates, edits, or deletes a row, and makes no permission
    decision. ``team_id`` narrows every check to a single team; the scanned set
    for active-team checks is active teams only unless ``include_inactive``.
    """
    target_date = target_date or timezone.localdate()
    stats = _new_stats()
    details = OrderedDict((key, []) for key in VERBOSE_DETAIL_KEYS)

    base_qs = MinistryTeam.objects.all().select_related("role_profile")
    if team_id is not None:
        base_qs = base_qs.filter(id=team_id)
    teams = list(base_qs)
    teams_by_id = {team.id: team for team in teams}

    # --- Inventory (all teams in scope) -----------------------------------
    teams_by_kind = OrderedDict()
    for value, _label in MinistryTeam.TEAM_KIND_CHOICES:
        teams_by_kind[value] = 0
    for team in teams:
        stats["total_teams"] += 1
        if team.is_active:
            stats["active_teams"] += 1
        else:
            stats["inactive_teams"] += 1
        if team.is_assignable:
            stats["assignable_teams"] += 1
        else:
            stats["non_assignable_teams"] += 1
        teams_by_kind[team.team_kind] = teams_by_kind.get(team.team_kind, 0) + 1

    # Scanned set for active-team readiness checks.
    scanned = [t for t in teams if include_inactive or t.is_active]
    scanned_ids = [t.id for t in scanned]

    # --- Active parent links ----------------------------------------------
    active_links = list(
        MinistryTeamParentLink.objects.filter(is_active=True)
        .select_related("parent_team", "parent_church_unit")
        .order_by("child_team_id", "sort_order", "id")
    )
    links_by_child = {}
    active_team_edges = {}
    for link in active_links:
        links_by_child.setdefault(link.child_team_id, []).append(link)
        if link.parent_team_id is not None:
            active_team_edges.setdefault(link.child_team_id, []).append(
                link.parent_team_id
            )

    cycle_team_ids = _detect_cycle_team_ids(active_team_edges)

    for team in scanned:
        links = links_by_child.get(team.id, [])
        primary_links = [link for link in links if link.is_primary]

        if not links:
            stats["teams_no_active_parent_link"] += 1
            details["teams_no_active_parent_link"].append(_team_label(team))
        else:
            if len(links) > 1:
                stats["shared_teams_multi_active_parent_link"] += 1
                details["shared_teams_multi_active_parent_link"].append(
                    f"{_team_label(team)} active_links={len(links)}"
                )
            if not primary_links:
                stats["teams_no_primary_parent_link"] += 1
                details["teams_no_primary_parent_link"].append(_team_label(team))

        if len(primary_links) > 1:
            stats["teams_multiple_active_primary_links"] += 1
            details["teams_multiple_active_primary_links"].append(
                f"{_team_label(team)} active_primary_links={len(primary_links)}"
            )

        inactive_parent = any(
            link.parent_team_id is not None and not link.parent_team.is_active
            for link in links
        )
        if inactive_parent:
            stats["teams_link_to_inactive_parent_team"] += 1
            details["teams_link_to_inactive_parent_team"].append(_team_label(team))

        if team.id in cycle_team_ids:
            stats["parent_link_cycle_teams"] += 1
            details["parent_link_cycle_teams"].append(_team_label(team))

        # Unanchored: no church anchor reachable via the primary chain.
        if team.primary_church_anchor() is None:
            stats["teams_no_church_anchor"] += 1

    # --- Role profile / role assignment readiness -------------------------
    # Optional-requirement role-type ids per profile (for optional-gap info).
    optional_by_profile = {}
    for req in MinistryTeamRoleRequirement.objects.filter(
        is_active=True, is_required=False, role_type__is_active=True
    ).values("profile_id", "role_type_id"):
        optional_by_profile.setdefault(req["profile_id"], set()).add(
            req["role_type_id"]
        )

    for team in scanned:
        profile = team.role_profile
        if profile is None:
            stats["teams_no_role_profile"] += 1
            if team.is_assignable:
                stats["assignable_teams_no_role_profile"] += 1
                details["assignable_teams_no_role_profile"].append(_team_label(team))
            continue

        if not profile.is_active:
            stats["teams_inactive_role_profile"] += 1
            details["teams_inactive_role_profile"].append(
                f"{_team_label(team)} profile={profile.code}"
            )

        missing = team.missing_required_role_types(target_date)
        if missing:
            stats["teams_missing_required_roles"] += 1
            details["teams_missing_required_roles"].append(
                f"{_team_label(team)} missing="
                + ",".join(role_type.code for role_type in missing)
            )
            if any(role_type.code == LEAD_ROLE_CODE for role_type in missing):
                stats["teams_missing_required_lead"] += 1
                details["teams_missing_required_lead"].append(_team_label(team))

        optional_ids = optional_by_profile.get(profile.id)
        if optional_ids:
            covered = set(
                team.role_assignments.filter(
                    is_active=True,
                    role_type_id__in=optional_ids,
                    start_date__lte=target_date,
                )
                .filter(
                    Q(end_date__isnull=True) | Q(end_date__gte=target_date)
                )
                .values_list("role_type_id", flat=True)
            )
            if optional_ids - covered:
                stats["teams_with_optional_role_gaps"] += 1

    # Active role assignments whose role_type is inactive (scanned teams only).
    inactive_role_type_assignments = (
        MinistryTeamRoleAssignment.objects.filter(
            is_active=True,
            role_type__is_active=False,
            team_id__in=scanned_ids,
        )
        .select_related("team", "role_type")
        .order_by("team_id", "id")
    )
    for assignment in inactive_role_type_assignments:
        stats["active_role_assignments_inactive_role_type"] += 1
        details["active_role_assignments_inactive_role_type"].append(
            f"assignment_id={assignment.id} team=#{assignment.team_id} "
            f"role_type={assignment.role_type.code}"
        )

    # Overlapping duplicate active (team, role_type, user) groups.
    duplicate_groups = (
        MinistryTeamRoleAssignment.objects.filter(
            is_active=True, team_id__in=scanned_ids
        )
        .values("team_id", "role_type_id", "user_id")
        .annotate(n=Count("id"))
        .filter(n__gt=1)
    )
    for group in duplicate_groups:
        stats["duplicate_active_user_team_role_assignments"] += 1
        details["duplicate_active_user_team_role_assignments"].append(
            f"team=#{group['team_id']} role_type_id={group['role_type_id']} "
            f"user_id={group['user_id']} active_rows={group['n']}"
        )

    # --- Assignment readiness (is_assignable enforcement, 1F) --------------
    assignment_qs = TeamAssignment.objects.filter(
        ministry_team__is_assignable=False
    ).select_related("ministry_team")
    if team_id is not None:
        assignment_qs = assignment_qs.filter(ministry_team_id=team_id)
    for assignment in assignment_qs.order_by("ministry_team_id", "id"):
        status = assignment.status
        line = (
            f"assignment_id={assignment.id} team=#{assignment.ministry_team_id} "
            f"status={status} event_id={assignment.service_event_id}"
        )
        if status == TeamAssignment.STATUS_CANCELLED:
            stats["cancelled_assignments_on_non_assignable_team"] += 1
            details["cancelled_assignments_on_non_assignable_team"].append(line)
        elif status == TeamAssignment.STATUS_COMPLETED:
            stats["completed_assignments_on_non_assignable_team"] += 1
            details["completed_assignments_on_non_assignable_team"].append(line)
        elif status in ACTIVE_ASSIGNMENT_STATUSES:
            stats["active_assignments_on_non_assignable_team"] += 1
            details["active_assignments_on_non_assignable_team"].append(line)

    required_links_qs = ServiceEventRequiredTeam.objects.filter(
        ministry_team__is_assignable=False
    ).select_related("ministry_team")
    if team_id is not None:
        required_links_qs = required_links_qs.filter(ministry_team_id=team_id)
    for link in required_links_qs.order_by("ministry_team_id", "id"):
        stats["required_event_links_to_non_assignable_team"] += 1
        details["required_event_links_to_non_assignable_team"].append(
            f"required_link_id={link.id} team=#{link.ministry_team_id} "
            f"event_id={link.service_event_id}"
        )

    # Assignable active teams missing an active membership / leadership.
    assignable_active_teams = [
        team for team in scanned if team.is_active and team.is_assignable
    ]
    assignable_ids = [team.id for team in assignable_active_teams]
    member_team_ids = set(
        TeamMembership.objects.filter(
            is_active=True, team_id__in=assignable_ids
        ).values_list("team_id", flat=True)
    )
    leadership_team_ids = set(
        TeamMembership.objects.filter(
            is_active=True,
            team_id__in=assignable_ids,
            role__in=LEADERSHIP_ROLES,
        ).values_list("team_id", flat=True)
    )
    for team in assignable_active_teams:
        if team.id not in member_team_ids:
            stats["assignable_teams_no_active_membership"] += 1
            details["assignable_teams_no_active_membership"].append(_team_label(team))
        if team.id not in leadership_team_ids:
            stats["assignable_teams_no_active_leadership"] += 1
            details["assignable_teams_no_active_leadership"].append(_team_label(team))

    blockers = [key for key in BLOCKER_KEYS if stats[key]]
    warnings = [key for key in WARNING_KEYS if stats[key]]
    info = [key for key in INFO_KEYS if stats[key]]

    return {
        "stats": stats,
        "teams_by_kind": teams_by_kind,
        "details": details,
        "blockers": blockers,
        "warnings": warnings,
        "info": info,
        "blocker_count": sum(stats[key] for key in BLOCKER_KEYS),
        "permission_notes": list(PERMISSION_NOTES),
        "target_date": target_date,
        "include_inactive": include_inactive,
        "team_id": team_id,
    }
