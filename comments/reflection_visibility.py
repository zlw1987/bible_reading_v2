"""Runtime reflection group-visibility helpers (CS-CORE.4G.2).

Group-shared ``ReflectionComment`` visibility for ordinary members now uses the
structure-native snapshot (``structure_unit_at_post``) plus the viewer's single
active primary ``ChurchStructureMembership``, replacing legacy
``Profile.small_group`` + ``ReflectionComment.small_group_at_post``.

Matching rule: a viewer can see a group-shared reflection when the viewer's
active primary membership unit is the post's ``structure_unit_at_post`` snapshot
unit *or a descendant of it*. This preserves current small-group semantics while
allowing nested structure units, mirroring the Bible Study v2 meeting visibility
rule (``studies.visibility``).

Fail-closed for ordinary users: missing / inactive / wrong-type snapshot, no
active primary membership, or multiple active primary memberships all deny
group visibility. ``small_group_at_post`` and ``Profile.small_group`` no longer
grant ordinary group reflection visibility; they remain stored legacy
compatibility data.

Two helpers stay in lockstep on purpose:

- ``user_matches_group_reflection_snapshot`` is the per-row gate used by
  ``ReflectionComment.can_be_seen_by``.
- ``get_visible_group_reflection_snapshot_unit_ids`` is the queryset-level
  equivalent used by ``reading.views.get_visible_reflection_filter`` and the
  ``passage_wall`` group tab.

In a tree, "membership unit is the snapshot unit or a descendant of it" is
equivalent to "the snapshot unit is the membership unit or one of its
ancestors," so the gate walks down from the snapshot and the filter walks up
from the membership unit; both honour the same active/small-group validity check
on the snapshot unit.
"""

from accounts.models import ChurchStructureUnit
from accounts.structure_selectors import (
    _collect_unit_and_descendant_ids,
    get_user_primary_membership_unit,
)


def snapshot_unit_is_valid_for_group_visibility(unit):
    """Return whether a snapshot unit can drive ordinary group visibility.

    A group-shared reflection is a small-group post; a snapshot mapped to root,
    ministry-context, district, fellowship, department, or custom units, or an
    inactive/missing unit, is drift for this runtime path and fails closed.
    """
    return bool(
        unit is not None
        and unit.is_active
        and unit.unit_type == ChurchStructureUnit.UNIT_SMALL_GROUP
    )


def user_matches_group_reflection_snapshot(user, comment, target_date=None):
    """Per-row gate: can an ordinary user see this group-shared reflection?

    Fail-closed: missing/inactive/wrong-type ``structure_unit_at_post``, no
    active primary membership, or multiple active primary memberships all return
    ``False``. ``Profile.small_group`` and ``small_group_at_post`` are never
    consulted here.
    """
    if not getattr(user, "is_authenticated", False):
        return False

    snapshot_unit = comment.structure_unit_at_post
    if not snapshot_unit_is_valid_for_group_visibility(snapshot_unit):
        return False

    membership_unit = get_user_primary_membership_unit(user, target_date=target_date)
    if membership_unit is None:
        return False

    return membership_unit.id in _collect_unit_and_descendant_ids([snapshot_unit])


def get_visible_group_reflection_snapshot_unit_ids(user, target_date=None):
    """Queryset-level mirror of ``user_matches_group_reflection_snapshot``.

    Return the set of ``structure_unit_at_post`` ids whose group-shared
    reflections the viewer may see: the viewer's active primary membership unit
    and its ancestors, restricted to active small-group-type units. Returns an
    empty set when the viewer has no single active primary membership.
    """
    membership_unit = get_user_primary_membership_unit(user, target_date=target_date)
    if membership_unit is None:
        return set()

    candidate_units = membership_unit.get_ancestors() + [membership_unit]
    return {
        unit.id
        for unit in candidate_units
        if snapshot_unit_is_valid_for_group_visibility(unit)
    }
