"""Read-only Bible Study membership-core readiness/audit helpers.

After CS-CORE.2C-B, these helpers compare the old legacy Bible Study meeting
visibility source (``Profile.small_group``) against the current membership-core
runtime source (active primary ``ChurchStructureMembership``). The audit stays
read-only: it writes no profile, membership, group, unit, or meeting data.

Scope note: the legacy v1 ``BibleStudySession`` model is intentionally not
given equivalent shadow helpers. It is a retirement target (see
``docs/CHURCH_STRUCTURE_CORE_MIGRATION_PLAN.md`` Section 12), its
global/district/small-group scope semantics do not carry over to the v2
``BibleStudyMeeting`` flow that a future membership-core switch would target,
and auditing it would not inform that switch. Its ``can_be_seen_by`` behavior
is unchanged by this module.
"""

from accounts.models import ChurchStructureMembership, ChurchStructureUnit
from accounts.structure_selectors import get_user_legacy_small_group
from .visibility import (
    get_small_group_structure_unit,
    meeting_is_member_visible,
    user_has_bible_study_manager_override,
    user_matches_meeting_small_group_membership,
)


CLASSIFICATION_SAME_VISIBLE = "same_visible"
CLASSIFICATION_SAME_HIDDEN = "same_hidden"
CLASSIFICATION_WOULD_GAIN = "would_gain"
CLASSIFICATION_WOULD_LOSE = "would_lose"

# Stable reason codes for readiness audit output.
REASON_USER_NOT_AUTHENTICATED = "user_not_authenticated"
REASON_STAFF_OR_MANAGER_OVERRIDE = "staff_or_manager_override"
REASON_MEETING_NOT_MEMBER_VISIBLE = "meeting_not_member_visible"
REASON_MEETING_UNMAPPED_SMALL_GROUP = "meeting_unmapped_small_group"
REASON_MEETING_SMALL_GROUP_WRONG_UNIT_TYPE = "meeting_small_group_wrong_unit_type"
REASON_USER_NO_PROFILE_SMALL_GROUP = "user_no_profile_small_group"
REASON_PROFILE_GROUP_MATCHES = "profile_group_matches_meeting_group"
REASON_PROFILE_GROUP_DIFFERS = "profile_group_differs_from_meeting_group"
REASON_USER_NO_ACTIVE_PRIMARY_MEMBERSHIP = "user_no_active_primary_membership"
REASON_MULTIPLE_ACTIVE_PRIMARY_MEMBERSHIPS = "multiple_active_primary_memberships"
REASON_MEMBERSHIP_UNIT_MATCHES = "membership_unit_matches_meeting_unit"
REASON_MEMBERSHIP_UNIT_DIFFERS = "membership_unit_differs_from_meeting_unit"


def get_user_active_primary_memberships(user, target_date=None):
    """Return the user's active primary memberships for the target date.

    Same activity window as the membership-core selectors: status active,
    ``is_primary=True``, started on or before the target date, and not ended
    before it. Requested/rejected/cancelled/ended/future/expired rows never
    appear here. Anonymous or unsaved users get an empty list.
    """
    if not getattr(user, "is_authenticated", False):
        return []
    if getattr(user, "pk", None) is None:
        return []
    return list(
        ChurchStructureMembership.active_for_user(user, target_date=target_date)
        .filter(is_primary=True)
        .select_related("unit")
    )


def user_matches_bible_study_meeting_legacy(user, meeting):
    """Old Bible Study meeting visibility rule (legacy source).

    Preserved as a standalone comparator after the runtime switch: staff/
    manager override, then published meeting/lesson and active published
    series, then ``Profile.small_group`` equality with the meeting's small
    group. Do not delegate this to ``BibleStudyMeeting.can_be_seen_by`` or the
    audit becomes a tautology.
    """
    if not getattr(user, "is_authenticated", False):
        return False

    if user_has_bible_study_manager_override(user):
        return True

    if not meeting_is_member_visible(meeting):
        return False

    legacy_group = get_user_legacy_small_group(user)
    return bool(legacy_group and legacy_group.id == meeting.small_group_id)


def user_matches_bible_study_meeting_membership_core(
    user, meeting, target_date=None
):
    """Current Bible Study meeting visibility rule (membership-core).

    Keeps the non-belonging gates identical to ``can_be_seen_by`` (staff/
    manager override, published meeting/lesson, active published series) but
    replaces ``Profile.small_group`` equality with membership-core matching:
    the meeting's small group must be mapped to a small-group
    ``ChurchStructureUnit``, and the user's single active primary
    ``ChurchStructureMembership`` unit must be that unit or a descendant.

    Fail-closed rules:

    - ``Profile.small_group`` alone grants nothing here.
    - Requested/rejected/cancelled/ended/future/expired memberships grant
      nothing.
    - Multiple active primary memberships fail closed for non-root units.
    - Unmapped or wrong-type meeting small-group mappings grant nothing to
      ordinary users.
    """
    if not getattr(user, "is_authenticated", False):
        return False

    if user_has_bible_study_manager_override(user):
        return True

    if not meeting_is_member_visible(meeting):
        return False

    return user_matches_meeting_small_group_membership(
        user, meeting.small_group, target_date=target_date
    )


def compare_bible_study_meeting_visibility(user, meeting, target_date=None):
    """Return a read-only comparison of legacy vs membership-core visibility.

    Returns a dict with:

    - ``legacy_visible``: bool, old ``Profile.small_group`` answer.
    - ``membership_visible``: bool, current membership-core answer.
    - ``classification``: one of ``same_visible``, ``same_hidden``,
      ``would_gain``, ``would_lose``.
    - ``reason_codes``: tuple of stable codes explaining the comparison for
      audit output. Codes never include membership notes or other private
      text.
    """
    legacy_visible = user_matches_bible_study_meeting_legacy(user, meeting)
    membership_visible = user_matches_bible_study_meeting_membership_core(
        user, meeting, target_date=target_date
    )

    reason_codes = []
    if not getattr(user, "is_authenticated", False):
        reason_codes.append(REASON_USER_NOT_AUTHENTICATED)
    elif user_has_bible_study_manager_override(user):
        reason_codes.append(REASON_STAFF_OR_MANAGER_OVERRIDE)
    else:
        if not meeting_is_member_visible(meeting):
            reason_codes.append(REASON_MEETING_NOT_MEMBER_VISIBLE)

        unit = get_small_group_structure_unit(meeting.small_group)
        if unit is None:
            reason_codes.append(REASON_MEETING_UNMAPPED_SMALL_GROUP)
        elif unit.unit_type != ChurchStructureUnit.UNIT_SMALL_GROUP:
            reason_codes.append(REASON_MEETING_SMALL_GROUP_WRONG_UNIT_TYPE)

        legacy_group = get_user_legacy_small_group(user)
        if legacy_group is None:
            reason_codes.append(REASON_USER_NO_PROFILE_SMALL_GROUP)
        elif legacy_group.id == meeting.small_group_id:
            reason_codes.append(REASON_PROFILE_GROUP_MATCHES)
        else:
            reason_codes.append(REASON_PROFILE_GROUP_DIFFERS)

        memberships = get_user_active_primary_memberships(
            user, target_date=target_date
        )
        if not memberships:
            reason_codes.append(REASON_USER_NO_ACTIVE_PRIMARY_MEMBERSHIP)
        elif len(memberships) > 1:
            reason_codes.append(REASON_MULTIPLE_ACTIVE_PRIMARY_MEMBERSHIPS)
        elif unit is not None:
            if user_matches_meeting_small_group_membership(
                user, meeting.small_group, target_date=target_date
            ):
                reason_codes.append(REASON_MEMBERSHIP_UNIT_MATCHES)
            else:
                reason_codes.append(REASON_MEMBERSHIP_UNIT_DIFFERS)

    if legacy_visible and membership_visible:
        classification = CLASSIFICATION_SAME_VISIBLE
    elif not legacy_visible and not membership_visible:
        classification = CLASSIFICATION_SAME_HIDDEN
    elif legacy_visible:
        classification = CLASSIFICATION_WOULD_LOSE
    else:
        classification = CLASSIFICATION_WOULD_GAIN

    return {
        "legacy_visible": legacy_visible,
        "membership_visible": membership_visible,
        "classification": classification,
        "reason_codes": tuple(reason_codes),
    }
