"""Runtime prayer group-visibility helpers.

Group-shared ``PrayerRequest`` visibility for ordinary members uses the
structure-native snapshot (``structure_unit_at_post``) plus the viewer's single
active primary ``ChurchStructureMembership``. Legacy ``Profile.small_group`` is
not consulted for prayer visibility; the legacy ``small_group_at_post`` mirror
field was removed in PRAYER-MIRROR.1D.
"""

from dataclasses import dataclass

from accounts.models import ChurchStructureUnit
from accounts.structure_selectors import (
    _collect_unit_and_descendant_ids,
    get_user_primary_membership_unit,
)


def snapshot_unit_is_valid_for_group_prayer_visibility(unit):
    """Return whether a snapshot unit can drive ordinary group visibility."""
    return bool(
        unit is not None
        and unit.is_active
        and unit.unit_type == ChurchStructureUnit.UNIT_SMALL_GROUP
    )


def user_matches_group_prayer_snapshot(user, prayer, target_date=None):
    """Per-row ordinary-user gate for group-shared prayer requests."""
    if not getattr(user, "is_authenticated", False):
        return False

    snapshot_unit = prayer.structure_unit_at_post
    if not snapshot_unit_is_valid_for_group_prayer_visibility(snapshot_unit):
        return False

    membership_unit = get_user_primary_membership_unit(user, target_date=target_date)
    if membership_unit is None:
        return False

    return membership_unit.id in _collect_unit_and_descendant_ids([snapshot_unit])


@dataclass(frozen=True)
class GroupPrayerWriteContext:
    """Resolved membership-core context for stamping a group prayer request."""

    structure_unit: "ChurchStructureUnit | None" = None
    reason_code: str = "no_context"

    @property
    def can_share_to_group(self):
        return self.structure_unit is not None


def get_user_group_prayer_write_context(user, target_date=None):
    """Resolve the membership-core write context for group prayer sharing."""
    if not getattr(user, "is_authenticated", False):
        return GroupPrayerWriteContext(reason_code="unauthenticated")

    membership_unit = get_user_primary_membership_unit(user, target_date=target_date)
    if membership_unit is None:
        return GroupPrayerWriteContext(
            reason_code="no_single_active_primary_membership"
        )

    if not snapshot_unit_is_valid_for_group_prayer_visibility(membership_unit):
        return GroupPrayerWriteContext(
            reason_code="membership_unit_not_active_small_group"
        )

    # The legacy SmallGroup mirror was removed in PRAYER-MIRROR.1D.
    # ``structure_unit`` is the canonical group-prayer snapshot.
    return GroupPrayerWriteContext(
        structure_unit=membership_unit,
        reason_code="ok",
    )


def get_visible_group_prayer_snapshot_unit_ids(user, target_date=None):
    """Return snapshot unit ids whose group prayers the viewer may see."""
    membership_unit = get_user_primary_membership_unit(user, target_date=target_date)
    if membership_unit is None:
        return set()

    candidate_units = membership_unit.get_ancestors() + [membership_unit]
    return {
        unit.id
        for unit in candidate_units
        if snapshot_unit_is_valid_for_group_prayer_visibility(unit)
    }
