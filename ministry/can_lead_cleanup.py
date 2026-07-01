"""Deprecated ``TeamMembership.can_lead`` flag cleanup (MINISTRY-ROLE-SOURCE.1E-A).

After the MINISTRY-ROLE-SOURCE.1C read switch, runtime ministry team-management /
scheduling authority comes from active lead/coordinator
``MinistryTeamRoleAssignment`` rows for the exact team — **not** from
``TeamMembership.role`` and **not** from ``TeamMembership.can_lead``.
``TeamMembership.can_lead`` is a deprecated/reserved boolean that grants no
permission; leaving ``can_lead=True`` rows around is only stale legacy data that
the alignment audit reports as a warning.

This module clears the deprecated flag. It is deliberately narrow and safe:

* dry-run by default — the caller must pass ``apply=True`` to write;
* only ever sets ``can_lead`` from ``True`` to ``False``;
* never touches ``TeamMembership.role`` or any other membership field;
* never creates / deletes / (de)activates a ``TeamMembership`` row;
* never creates / deletes / (de)activates a ``MinistryTeamRoleAssignment`` row;
* changes no permission and infers no role from ``can_lead``.

Both active and inactive memberships are in scope by default so the deprecated
flag is cleared completely; ``team_id`` narrows the scope to one team.

See ``docs/MINISTRY_ROLE_SOURCE_OF_TRUTH_PLAN.md``.
"""

from collections import OrderedDict

from .models import TeamMembership


COUNTER_KEYS = (
    "candidates_checked",
    "would_clear",
    "cleared",
)

PERMISSION_NOTES = (
    "TeamMembership.can_lead is deprecated/reserved and grants NO permission "
    "after MINISTRY-ROLE-SOURCE.1C; runtime team-management / scheduling "
    "authority reads active lead/coordinator MinistryTeamRoleAssignment rows for "
    "the exact team.",
    "This cleanup only sets can_lead True -> False. TeamMembership.role is left "
    "untouched, no membership is created/deleted/deactivated, and no "
    "MinistryTeamRoleAssignment is created/deleted/deactivated.",
    "No role is inferred from can_lead and no permission changes by running this "
    "command.",
    "See docs/MINISTRY_ROLE_SOURCE_OF_TRUTH_PLAN.md.",
)


def _membership_label(membership):
    name = membership.get_display_name() or "(no name)"
    user_part = (
        f"user_id={membership.user_id}"
        if membership.user_id is not None
        else "display-name-only"
    )
    return (
        f"membership_id={membership.id} team=#{membership.team_id} "
        f"{user_part} name={name!r} role={membership.role}"
    )


def run_cleanup(*, apply=False, team_id=None):
    """Clear deprecated ``can_lead=True`` flags. Dry-run unless ``apply``.

    Returns a result dict with counters, verbose example details, the resolved
    filters, and ``data_mutated``. Read-only unless ``apply=True``; even then it
    only sets ``can_lead=False`` and mutates nothing else.
    """
    stats = OrderedDict((key, 0) for key in COUNTER_KEYS)
    details = OrderedDict((key, []) for key in ("would_clear", "cleared"))

    candidates = TeamMembership.objects.filter(can_lead=True).select_related(
        "team", "user"
    )
    if team_id is not None:
        candidates = candidates.filter(team_id=team_id)
    candidates = candidates.order_by("team_id", "id")

    cleared_ids = []
    for membership in candidates:
        stats["candidates_checked"] += 1
        if apply:
            stats["cleared"] += 1
            details["cleared"].append(_membership_label(membership))
            cleared_ids.append(membership.id)
        else:
            stats["would_clear"] += 1
            details["would_clear"].append(_membership_label(membership))

    if apply and cleared_ids:
        # Update only the deprecated flag in bulk. ``update()`` deliberately
        # bypasses ``TeamMembership.save()``/``full_clean()`` so nothing else on
        # the row (including ``role``) is re-validated or rewritten, and no
        # ``updated_at`` side effects beyond the single flag occur.
        TeamMembership.objects.filter(id__in=cleared_ids).update(can_lead=False)

    data_mutated = bool(apply and stats["cleared"] > 0)

    return {
        "stats": stats,
        "details": details,
        "filters": {"team_id": team_id},
        "apply": apply,
        "data_mutated": data_mutated,
        "permission_notes": list(PERMISSION_NOTES),
    }
