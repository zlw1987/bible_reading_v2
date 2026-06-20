"""Runtime reflection group-visibility helpers (CS-CORE.4G.2).

Group-shared ``ReflectionComment`` visibility for ordinary members now uses the
structure-native snapshot (``structure_unit_at_post``) plus the viewer's single
active primary ``ChurchStructureMembership``, replacing legacy
``Profile.small_group`` (the legacy ``ReflectionComment.small_group_at_post``
mirror was removed in REFLECTION-MIRROR.1H).

Matching rule: a viewer can see a group-shared reflection when the viewer's
active primary membership unit is the post's ``structure_unit_at_post`` snapshot
unit *or a descendant of it*. This preserves current small-group semantics while
allowing nested structure units, mirroring the Bible Study v2 meeting visibility
rule (``studies.visibility``).

Fail-closed for ordinary users: missing / inactive / wrong-type snapshot, no
active primary membership, or multiple active primary memberships all deny
group visibility. ``Profile.small_group`` no longer grants ordinary group
reflection visibility.

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

from dataclasses import dataclass

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
    ``False``. ``Profile.small_group`` is never consulted here.
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


@dataclass(frozen=True)
class GroupReflectionWriteContext:
    """Resolved membership-core context for stamping a group reflection.

    ``structure_unit`` is the canonical group reflection snapshot source; it is
    set only when the author has a valid write context. ``reason_code`` records
    why the context resolved the way it did, for diagnostics. (The legacy
    ``small_group_at_post`` mirror and its resolver were removed in
    REFLECTION-MIRROR.1H.)
    """

    structure_unit: "ChurchStructureUnit | None" = None
    reason_code: str = "no_context"

    @property
    def can_share_to_group(self):
        return self.structure_unit is not None


def get_user_group_reflection_write_context(user, target_date=None):
    """Resolve the membership-core write context for group reflection sharing.

    Fail-closed mirror of the 4G.2 read gate's belonging rule. A user may stamp
    a group reflection only when they have exactly one active primary
    ``ChurchStructureMembership`` whose unit is an active
    ``UNIT_SMALL_GROUP``. ``Profile.small_group`` is never consulted to decide
    eligibility or to stamp the structure snapshot. No active primary,
    multiple active primaries, an inactive unit, or a wrong-type unit all
    resolve to a context with no ``structure_unit``.
    """
    if not getattr(user, "is_authenticated", False):
        return GroupReflectionWriteContext(reason_code="unauthenticated")

    membership_unit = get_user_primary_membership_unit(user, target_date=target_date)
    if membership_unit is None:
        return GroupReflectionWriteContext(
            reason_code="no_single_active_primary_membership"
        )

    if not snapshot_unit_is_valid_for_group_visibility(membership_unit):
        return GroupReflectionWriteContext(
            reason_code="membership_unit_not_active_small_group"
        )

    return GroupReflectionWriteContext(
        structure_unit=membership_unit,
        reason_code="ok",
    )


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
