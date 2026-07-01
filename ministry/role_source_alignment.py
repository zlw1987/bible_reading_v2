"""Read-only ministry role source-of-truth alignment audit (MINISTRY-ROLE-SOURCE.1A).

This module reports **drift** between the two ways a long-term ministry role is
currently expressed:

* the transitional/legacy ``TeamMembership.role`` (``lead`` / ``coordinator``),
  which still drives runtime permissions (``can_manage_ministry_team`` /
  team-leader scheduling), plus the deprecated/reserved ``TeamMembership.can_lead``
  flag, which grants **no** permission today but is still audited as a warning; and
* the newer, explicit ``MinistryTeamRoleAssignment`` long-term ministry role,
  which is the *intended future single source of truth* but does **not** yet
  drive any permission.

The locked source-of-truth direction is documented in
``docs/MINISTRY_ROLE_SOURCE_OF_TRUTH_PLAN.md``:

* ``TeamMembership`` = team membership / candidate pool only.
* ``MinistryTeamRoleAssignment`` = long-term ministry responsibility and the
  eventual team-management permission source.
* ``TeamAssignmentMember`` = event-specific serving assignment.
* ``TeamMembership.role`` / ``TeamMembership.can_lead`` are transitional / legacy
  fields kept only for current runtime compatibility.

This audit is strictly **read-only**: it creates, updates, or deletes nothing,
has no apply mode, makes no permission decision, switches no source of truth,
backfills no role assignments, and never infers serving from membership. The
runtime permission source is unchanged by running it.

Because runtime has not switched yet, most divergence is expected and is
reported as a **warning** (transitional drift / setup gap), not a blocker.
Blockers are reserved for high-confidence corruption that would make a future
backfill/permission switch unsafe to automate.
"""

from collections import OrderedDict

from django.db.models import Count

from .models import (
    MinistryTeam,
    MinistryTeamRoleAssignment,
    MinistryTeamRoleType,
    TeamMembership,
)


# Equivalent role mapping (intentionally minimal): a legacy management
# ``TeamMembership.role`` maps to a ministry role-type ``code``. We deliberately
# do NOT infer scheduler / technical / other ministry roles from membership.
MEMBERSHIP_ROLE_TO_MINISTRY_CODE = OrderedDict(
    [
        (TeamMembership.ROLE_LEAD, MinistryTeamRoleType.CODE_LEAD),
        (TeamMembership.ROLE_COORDINATOR, MinistryTeamRoleType.CODE_COORDINATOR),
    ]
)

# Legacy membership roles treated as "management" for alignment purposes.
MANAGEMENT_MEMBERSHIP_ROLES = tuple(MEMBERSHIP_ROLE_TO_MINISTRY_CODE.keys())

# Ministry role-type codes treated as long-term management roles.
MANAGEMENT_MINISTRY_CODES = tuple(MEMBERSHIP_ROLE_TO_MINISTRY_CODE.values())


# Inventory counters (plain summary; not severity-classified).
#
# ``container_management_role_assignment_without_membership`` is an **allowed**
# info counter, not a warning: for non-assignable container teams a long-term
# ``MinistryTeamRoleAssignment`` may name a leader without a candidate-pool
# ``TeamMembership`` (a container team has no concrete schedulable member pool).
# See MINISTRY-ROLE-SOURCE.1A-FU1 in docs/MINISTRY_ROLE_SOURCE_OF_TRUTH_PLAN.md.
INFO_KEYS = (
    "active_team_memberships",
    "team_memberships_role_member",
    "team_memberships_role_lead",
    "team_memberships_role_coordinator",
    "team_memberships_can_lead_true",
    "active_role_assignments",
    "active_ministry_teams",
    "container_management_role_assignment_without_membership",
)

# Drift that is expected while runtime still reads the legacy fields. None of
# these are fatal; they are the migration backlog this slice exposes.
WARNING_KEYS = (
    "legacy_management_membership_without_role_assignment",
    "management_role_assignment_without_membership",
    "active_team_memberships_can_lead_true",
    "legacy_management_membership_display_name_only",
    "teams_management_role_user_disagreement",
    "coordinator_membership_without_coordinator_role_type",
)

# High-confidence corruption that would make a future backfill / permission
# switch unsafe to automate. Conservative by design: the model's
# ``MinistryTeamRoleAssignment.clean`` already rejects overlapping active
# duplicates, so this is expected to be zero against clean data.
BLOCKER_KEYS = (
    "duplicate_active_role_assignment_user_team_role",
)

# Info-level counters that also carry capped verbose example rows. The
# container-team drift is allowed (info), but examples are still useful when
# reviewing which container role assignments have no membership.
INFO_DETAIL_KEYS = (
    "container_management_role_assignment_without_membership",
)

# Categories that carry capped example rows under ``--verbose``.
VERBOSE_DETAIL_KEYS = BLOCKER_KEYS + WARNING_KEYS + INFO_DETAIL_KEYS

PERMISSION_NOTES = (
    "Read-only: this audit changes no permission and switches no source of "
    "truth. can_manage_ministry_team still reads TeamMembership.role "
    "(role in {lead, coordinator}); TeamMembership.can_lead is "
    "deprecated/reserved and grants no permission; MinistryTeamRoleAssignment "
    "still drives no permission.",
    "Locked target: MinistryTeamRoleAssignment becomes the single source of "
    "truth for long-term ministry roles in a later, separately approved slice "
    "(MINISTRY-ROLE-SOURCE.1B backfill, 1C permission read switch).",
    "TeamMembership stays the membership / candidate pool; TeamAssignmentMember "
    "stays the event-specific serving source. Neither membership nor a role "
    "assignment implies serving.",
    "For assignable teams (is_assignable=True), management role holders should "
    "also have an active TeamMembership because the team has a concrete "
    "schedulable member pool and may be a ServiceEvent required-team / "
    "TeamAssignment target (any event type). For non-assignable container teams "
    "(is_assignable=False) MinistryTeamRoleAssignment may name long-term leaders "
    "without requiring TeamMembership, so that case is reported as allowed info, "
    "not a warning.",
    "See docs/MINISTRY_ROLE_SOURCE_OF_TRUTH_PLAN.md.",
)

ALL_COUNTER_KEYS = INFO_KEYS + WARNING_KEYS + BLOCKER_KEYS


def _new_stats():
    return OrderedDict((key, 0) for key in ALL_COUNTER_KEYS)


def _membership_label(membership):
    name = membership.get_display_name() or "(no name)"
    user_part = (
        f"user_id={membership.user_id}"
        if membership.user_id is not None
        else "display-name-only"
    )
    return (
        f"membership_id={membership.id} team=#{membership.team_id} "
        f"role={membership.role} {user_part} name={name!r}"
    )


def run_alignment_audit(target_date=None):
    """Return read-only ministry role source-of-truth alignment counters/samples.

    Read-only: never creates, edits, or deletes a row, and makes no permission
    decision. ``target_date`` is accepted for signature parity with the other
    ministry audits but is not currently used (``is_active`` is the active flag
    for both membership and role assignment).
    """
    stats = _new_stats()
    details = OrderedDict((key, []) for key in VERBOSE_DETAIL_KEYS)

    existing_role_type_codes = set(
        MinistryTeamRoleType.objects.filter(is_active=True).values_list(
            "code", flat=True
        )
    )

    stats["active_ministry_teams"] = MinistryTeam.objects.filter(
        is_active=True
    ).count()

    # --- Membership inventory (active memberships) -------------------------
    active_memberships = list(
        TeamMembership.objects.filter(is_active=True).select_related("team", "user")
    )
    stats["active_team_memberships"] = len(active_memberships)
    for membership in active_memberships:
        if membership.role == TeamMembership.ROLE_MEMBER:
            stats["team_memberships_role_member"] += 1
        elif membership.role == TeamMembership.ROLE_LEAD:
            stats["team_memberships_role_lead"] += 1
        elif membership.role == TeamMembership.ROLE_COORDINATOR:
            stats["team_memberships_role_coordinator"] += 1

        if membership.can_lead:
            stats["team_memberships_can_lead_true"] += 1
            stats["active_team_memberships_can_lead_true"] += 1
            details["active_team_memberships_can_lead_true"].append(
                _membership_label(membership)
            )

    # --- Role assignment inventory (active assignments on active teams) -----
    active_role_assignments = list(
        MinistryTeamRoleAssignment.objects.filter(
            is_active=True, team__is_active=True
        ).select_related("team", "role_type", "user")
    )
    stats["active_role_assignments"] = len(active_role_assignments)

    by_code = OrderedDict()
    for assignment in active_role_assignments:
        code = assignment.role_type.code
        by_code[code] = by_code.get(code, 0) + 1

    # Lookups keyed by team for the drift comparisons below. We scope drift to
    # active teams (a role assignment requires an active team; membership on an
    # inactive team cannot back a future active role assignment).
    role_assign_users_by_team_code = {}
    mgmt_assignment_users_by_team = {}
    for assignment in active_role_assignments:
        role_assign_users_by_team_code.setdefault(
            (assignment.team_id, assignment.role_type.code), set()
        ).add(assignment.user_id)
        if assignment.role_type.code in MANAGEMENT_MINISTRY_CODES:
            mgmt_assignment_users_by_team.setdefault(
                assignment.team_id, set()
            ).add(assignment.user_id)

    membership_users_by_team = {}
    mgmt_membership_users_by_team = {}
    for membership in active_memberships:
        if not membership.team.is_active:
            continue
        if membership.user_id is not None:
            membership_users_by_team.setdefault(membership.team_id, set()).add(
                membership.user_id
            )
        if membership.role in MANAGEMENT_MEMBERSHIP_ROLES and (
            membership.user_id is not None
        ):
            mgmt_membership_users_by_team.setdefault(membership.team_id, set()).add(
                membership.user_id
            )

    # --- Warning: legacy management membership vs role assignment ----------
    for membership in active_memberships:
        if not membership.team.is_active:
            continue
        if membership.role not in MANAGEMENT_MEMBERSHIP_ROLES:
            continue

        # Display-name-only management memberships cannot become a user-linked
        # role assignment at all.
        if membership.user_id is None:
            stats["legacy_management_membership_display_name_only"] += 1
            details["legacy_management_membership_display_name_only"].append(
                _membership_label(membership)
            )
            continue

        target_code = MEMBERSHIP_ROLE_TO_MINISTRY_CODE[membership.role]
        if target_code not in existing_role_type_codes:
            # Config gap: the equivalent ministry role type does not exist, so
            # the legacy role cannot be mapped yet. Reported as a config-gap
            # warning, never a blocker; we do not create role types here.
            if membership.role == TeamMembership.ROLE_COORDINATOR:
                stats["coordinator_membership_without_coordinator_role_type"] += 1
                details[
                    "coordinator_membership_without_coordinator_role_type"
                ].append(_membership_label(membership))
            else:
                # An equally unmapped lead is still surfaced (rare; lead is a
                # seeded default) as a missing-role-assignment warning.
                stats["legacy_management_membership_without_role_assignment"] += 1
                details[
                    "legacy_management_membership_without_role_assignment"
                ].append(
                    _membership_label(membership)
                    + f" expected_code={target_code} (role type missing)"
                )
            continue

        covered_users = role_assign_users_by_team_code.get(
            (membership.team_id, target_code), set()
        )
        if membership.user_id not in covered_users:
            stats["legacy_management_membership_without_role_assignment"] += 1
            details["legacy_management_membership_without_role_assignment"].append(
                _membership_label(membership) + f" expected_code={target_code}"
            )

    # --- Management role assignment without active membership ----------------
    # For assignable teams this is a warning (the team has a concrete
    # schedulable member pool, so a management role holder should also be an
    # active TeamMembership). For non-assignable container teams it is allowed
    # and reported only as an info counter (MINISTRY-ROLE-SOURCE.1A-FU1).
    for assignment in active_role_assignments:
        if assignment.role_type.code not in MANAGEMENT_MINISTRY_CODES:
            continue
        team_member_users = membership_users_by_team.get(assignment.team_id, set())
        if assignment.user_id in team_member_users:
            continue
        label = (
            f"assignment_id={assignment.id} team=#{assignment.team_id} "
            f"user_id={assignment.user_id} role_code={assignment.role_type.code}"
        )
        if assignment.team.is_assignable:
            stats["management_role_assignment_without_membership"] += 1
            details["management_role_assignment_without_membership"].append(label)
        else:
            stats[
                "container_management_role_assignment_without_membership"
            ] += 1
            details[
                "container_management_role_assignment_without_membership"
            ].append(label + " is_assignable=False (allowed for container team)")

    # --- Warning: both systems carry management roles but users disagree ----
    for team_id, member_users in mgmt_membership_users_by_team.items():
        assignment_users = mgmt_assignment_users_by_team.get(team_id)
        if assignment_users and member_users != assignment_users:
            stats["teams_management_role_user_disagreement"] += 1
            details["teams_management_role_user_disagreement"].append(
                f"team=#{team_id} "
                f"membership_users={sorted(member_users)} "
                f"role_assignment_users={sorted(assignment_users)}"
            )

    # --- Blocker: exact duplicate active (team, role_type, user) rows ------
    # The model's clean() rejects overlapping active duplicates, so this catches
    # only corrupt data inserted around validation. Such a duplicate makes a
    # future dedup/backfill ambiguous, so it is the one conservative blocker.
    duplicate_groups = (
        MinistryTeamRoleAssignment.objects.filter(is_active=True)
        .values("team_id", "role_type_id", "user_id")
        .annotate(n=Count("id"))
        .filter(n__gt=1)
    )
    for group in duplicate_groups:
        stats["duplicate_active_role_assignment_user_team_role"] += 1
        details["duplicate_active_role_assignment_user_team_role"].append(
            f"team=#{group['team_id']} role_type_id={group['role_type_id']} "
            f"user_id={group['user_id']} active_rows={group['n']}"
        )

    blockers = [key for key in BLOCKER_KEYS if stats[key]]
    warnings = [key for key in WARNING_KEYS if stats[key]]
    info = [key for key in INFO_KEYS if stats[key]]

    return {
        "stats": stats,
        "active_role_assignments_by_code": by_code,
        "details": details,
        "blockers": blockers,
        "warnings": warnings,
        "info": info,
        "blocker_count": sum(stats[key] for key in BLOCKER_KEYS),
        "warning_count": sum(stats[key] for key in WARNING_KEYS),
        "permission_notes": list(PERMISSION_NOTES),
    }
