"""One-way ministry role backfill helper (MINISTRY-ROLE-SOURCE.1B).

This module implements the *dry-run by default* backfill that creates missing
``MinistryTeamRoleAssignment`` rows from existing active, user-linked
``TeamMembership.role`` values in {``lead``, ``coordinator``}.

Locked source-of-truth direction (see
``docs/MINISTRY_ROLE_SOURCE_OF_TRUTH_PLAN.md``):

* ``TeamMembership`` = membership / candidate pool only.
* ``MinistryTeamRoleAssignment`` = canonical long-term ministry role source and
  the eventual team-management permission source.
* ``TeamAssignmentMember`` = event-specific serving.

This backfill is deliberately conservative:

* It is **one-way only** (legacy membership role → role assignment). It never
  writes back to ``TeamMembership`` and implements no bidirectional sync.
* It changes **no permission**: current runtime still reads
  ``TeamMembership.role`` in {``lead``, ``coordinator``} for
  ``can_manage_ministry_team`` until the separately approved 1C read switch.
* It creates only ``MinistryTeamRoleAssignment`` rows. It never creates
  ``TeamMembership`` rows, never deletes/deactivates/overwrites existing rows,
  and never mutates ``TeamMembership.role`` / ``TeamMembership.can_lead``.
* It never backfills from ``can_lead=True`` and never infers scheduler /
  technical / admin / member-care roles; only ``lead`` → ``lead`` and
  ``coordinator`` → ``coordinator`` are mapped.
* It does **not** auto-resolve disagreements: when a team already has an active
  management role assignment for the same role type held by a *different* user,
  the candidate is reported as a conflict and left for manual decision.

Dry-run is the default; a row is written only under ``apply=True``.
"""

from collections import OrderedDict

from django.db import transaction
from django.utils import timezone

from .models import (
    MinistryTeamRoleAssignment,
    MinistryTeamRoleType,
    TeamMembership,
)
from .role_source_alignment import MEMBERSHIP_ROLE_TO_MINISTRY_CODE

# Note stamped on every backfilled role assignment.
BACKFILL_NOTE = "Backfilled from TeamMembership.role by MINISTRY-ROLE-SOURCE.1B."

# Legacy management membership roles this backfill maps (lead / coordinator).
MANAGEMENT_MEMBERSHIP_ROLES = tuple(MEMBERSHIP_ROLE_TO_MINISTRY_CODE.keys())

# Ordered outcome counters reported by the command.
COUNTER_KEYS = (
    "candidates_checked",
    "would_create",
    "created",
    "skipped_existing",
    "skipped_display_name_only",
    "skipped_missing_role_type",
    "conflict_existing_different_user",
    "ignored_can_lead_true",
)

# Categories that carry capped example rows under ``--verbose``.
VERBOSE_DETAIL_KEYS = (
    "would_create",
    "created",
    "skipped_existing",
    "skipped_display_name_only",
    "skipped_missing_role_type",
    "conflict_existing_different_user",
    "ignored_can_lead_true",
)

PERMISSION_NOTES = (
    "No permission change: can_manage_ministry_team still reads "
    "TeamMembership.role in {lead, coordinator} until the separately approved "
    "MINISTRY-ROLE-SOURCE.1C read switch. This backfill switches no source of "
    "truth.",
    "No TeamMembership mutation: TeamMembership.role and TeamMembership.can_lead "
    "are never written; no TeamMembership row is created, deleted, or "
    "deactivated. This is a one-way membership-role → MinistryTeamRoleAssignment "
    "backfill with no bidirectional sync.",
    "Conflicts are never auto-resolved: when a team already has an active "
    "management role assignment for the same role type held by a different user, "
    "the candidate is reported as a conflict and left for manual decision (no "
    "row created, no existing row overwritten or deactivated).",
    "can_lead=True is never a backfill source; scheduler / technical / admin / "
    "member-care roles are never inferred; only lead→lead and "
    "coordinator→coordinator are mapped. Display-name-only management "
    "memberships cannot be mapped and are skipped.",
    "See docs/MINISTRY_ROLE_SOURCE_OF_TRUTH_PLAN.md.",
)


def _new_stats():
    return OrderedDict((key, 0) for key in COUNTER_KEYS)


def _membership_label(membership, *, extra=""):
    name = membership.get_display_name() or "(no name)"
    user_part = (
        f"user_id={membership.user_id}"
        if membership.user_id is not None
        else "display-name-only"
    )
    label = (
        f"membership_id={membership.id} team=#{membership.team_id} "
        f"role={membership.role} {user_part} name={name!r}"
    )
    if extra:
        label = f"{label} {extra}"
    return label


def run_backfill(*, apply=False, team_id=None, role=None):
    """Scan active user-linked management memberships and (optionally) backfill.

    Returns a dict with ``stats`` counters, capped-example ``details``,
    ``data_mutated`` (True only when at least one row was actually created under
    ``apply``), ``apply``, ``permission_notes``, and the applied ``filters``.

    ``role`` (when provided) restricts the scanned ``TeamMembership.role`` to a
    single management role; ``team_id`` restricts the scan to one team. Neither
    filter narrows a destructive scope — this command only ever *creates* role
    assignment rows.
    """
    stats = _new_stats()
    details = OrderedDict((key, []) for key in VERBOSE_DETAIL_KEYS)

    start_date = timezone.localdate()

    # Active role types keyed by code (only active types can back an active
    # assignment; an inactive/missing mapped type is a config gap, not a create).
    active_role_types_by_code = {
        role_type.code: role_type
        for role_type in MinistryTeamRoleType.objects.filter(is_active=True)
    }

    # Preload active management role assignments on active teams, keyed by
    # (team_id, role_type_id) -> set(user_ids). Maintained in-memory so that
    # apply-mode creates influence later candidates within the same run.
    assignment_users_by_team_roletype = {}
    for assignment in MinistryTeamRoleAssignment.objects.filter(
        is_active=True, team__is_active=True
    ).select_related("role_type"):
        assignment_users_by_team_roletype.setdefault(
            (assignment.team_id, assignment.role_type_id), set()
        ).add(assignment.user_id)

    # --- ignored can_lead=True transparency counter -------------------------
    # can_lead is orthogonal to role and is never a backfill source. Counted
    # over active memberships on active teams (respecting --team-id) purely as a
    # disclaimer; --role does not narrow it because can_lead is not a role.
    can_lead_qs = TeamMembership.objects.filter(
        is_active=True, team__is_active=True, can_lead=True
    ).select_related("team", "user")
    if team_id is not None:
        can_lead_qs = can_lead_qs.filter(team_id=team_id)
    for membership in can_lead_qs:
        stats["ignored_can_lead_true"] += 1
        details["ignored_can_lead_true"].append(
            _membership_label(membership, extra="(can_lead ignored, not a source)")
        )

    # --- management membership scan -----------------------------------------
    scan_roles = MANAGEMENT_MEMBERSHIP_ROLES
    if role is not None:
        scan_roles = (role,)

    membership_qs = (
        TeamMembership.objects.filter(
            is_active=True,
            team__is_active=True,
            role__in=scan_roles,
        )
        .select_related("team", "user")
        .order_by("team_id", "id")
    )
    if team_id is not None:
        membership_qs = membership_qs.filter(team_id=team_id)

    created_objects = []

    def _process(membership):
        # Display-name-only management memberships cannot become a user-linked
        # role assignment; report and skip (never create).
        if membership.user_id is None:
            stats["skipped_display_name_only"] += 1
            details["skipped_display_name_only"].append(_membership_label(membership))
            return

        stats["candidates_checked"] += 1

        target_code = MEMBERSHIP_ROLE_TO_MINISTRY_CODE[membership.role]
        role_type = active_role_types_by_code.get(target_code)
        if role_type is None:
            # Config gap: mapped ministry role type missing or inactive. Do not
            # create the role type and do not create an assignment.
            stats["skipped_missing_role_type"] += 1
            details["skipped_missing_role_type"].append(
                _membership_label(
                    membership,
                    extra=f"expected_code={target_code} (role type missing/inactive)",
                )
            )
            return

        key = (membership.team_id, role_type.id)
        existing_users = assignment_users_by_team_roletype.get(key, set())

        if membership.user_id in existing_users:
            # Exact active assignment already exists for this team+user+role_type.
            stats["skipped_existing"] += 1
            details["skipped_existing"].append(
                _membership_label(membership, extra=f"role_code={target_code}")
            )
            return

        if existing_users:
            # Same team + role_type already held by a different active user.
            # Conservative: report conflict, create nothing, overwrite nothing.
            stats["conflict_existing_different_user"] += 1
            details["conflict_existing_different_user"].append(
                _membership_label(
                    membership,
                    extra=(
                        f"role_code={target_code} "
                        f"existing_user_ids={sorted(existing_users)} "
                        "(left for manual decision)"
                    ),
                )
            )
            return

        # Otherwise: this is a clean backfill candidate.
        if not apply:
            stats["would_create"] += 1
            details["would_create"].append(
                _membership_label(membership, extra=f"-> role_code={target_code}")
            )
            return

        assignment = MinistryTeamRoleAssignment(
            team=membership.team,
            user=membership.user,
            role_type=role_type,
            is_active=True,
            start_date=start_date,
            notes=BACKFILL_NOTE,
        )
        assignment.full_clean()
        assignment.save()
        created_objects.append(assignment)
        # Reflect the new row so later candidates in this run see it.
        assignment_users_by_team_roletype.setdefault(key, set()).add(
            membership.user_id
        )
        stats["created"] += 1
        details["created"].append(
            _membership_label(
                membership,
                extra=f"-> role_code={target_code} assignment_id={assignment.id}",
            )
        )

    if apply:
        with transaction.atomic():
            for membership in membership_qs:
                _process(membership)
    else:
        for membership in membership_qs:
            _process(membership)

    data_mutated = apply and stats["created"] > 0

    return {
        "stats": stats,
        "details": details,
        "apply": apply,
        "data_mutated": data_mutated,
        "permission_notes": list(PERMISSION_NOTES),
        "filters": {"team_id": team_id, "role": role},
        "start_date": start_date,
    }
