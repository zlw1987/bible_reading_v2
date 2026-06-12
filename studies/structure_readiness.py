"""Read-only Bible Study membership-core readiness/shadow helpers.

CS-CORE.2C-A shadow layer. These helpers compare the current legacy Bible
Study meeting visibility source (``Profile.small_group``) against the future
membership-core candidate source (active primary ``ChurchStructureMembership``)
without changing any runtime behavior. ``BibleStudyMeeting.can_be_seen_by``
remains the only runtime visibility rule; nothing in this module grants or
denies anything to ordinary users.

Scope note: the legacy v1 ``BibleStudySession`` model is intentionally not
given equivalent shadow helpers. It is a retirement target (see
``docs/CHURCH_STRUCTURE_CORE_MIGRATION_PLAN.md`` Section 12), its
global/district/small-group scope semantics do not carry over to the v2
``BibleStudyMeeting`` flow that a future membership-core switch would target,
and auditing it would not inform that switch. Its ``can_be_seen_by`` behavior
is unchanged by this module.
"""

from accounts.permissions import (
    CAP_MANAGE_BIBLE_STUDIES,
    CAP_PUBLISH_BIBLE_STUDY_GUIDES,
    has_capability,
)
from accounts.models import ChurchStructureMembership
from accounts.structure_selectors import (
    get_user_legacy_small_group,
    user_matches_membership_structure_audience,
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
REASON_USER_NO_PROFILE_SMALL_GROUP = "user_no_profile_small_group"
REASON_PROFILE_GROUP_MATCHES = "profile_group_matches_meeting_group"
REASON_PROFILE_GROUP_DIFFERS = "profile_group_differs_from_meeting_group"
REASON_USER_NO_ACTIVE_PRIMARY_MEMBERSHIP = "user_no_active_primary_membership"
REASON_MULTIPLE_ACTIVE_PRIMARY_MEMBERSHIPS = "multiple_active_primary_memberships"
REASON_MEMBERSHIP_UNIT_MATCHES = "membership_unit_matches_meeting_unit"
REASON_MEMBERSHIP_UNIT_DIFFERS = "membership_unit_differs_from_meeting_unit"


def get_small_group_structure_unit(small_group):
    """Return the SmallGroup's mapped ChurchStructureUnit, if any.

    Returns the mapped unit even when the unit is inactive
    (``is_active=False``). This mirrors the stored-inactive-unit parity rule
    used by audience matching (CS-CORE plan Section 6.7): an existing bridge
    keeps resolving, and deactivated units are surfaced by audits rather than
    silently dropping the mapping. Returns ``None`` when ``small_group`` is
    ``None`` or has no ``church_structure_unit`` mapping.
    """
    if small_group is None:
        return None
    return small_group.church_structure_unit


def _user_has_manager_override(user):
    """Mirror the BibleStudyMeeting.can_be_seen_by staff/manager bypass."""
    return (
        getattr(user, "is_staff", False)
        or getattr(user, "is_superuser", False)
        or has_capability(user, CAP_MANAGE_BIBLE_STUDIES)
        or has_capability(user, CAP_PUBLISH_BIBLE_STUDY_GUIDES)
    )


def _meeting_is_member_visible(meeting):
    """Mirror the non-belonging publish gates of can_be_seen_by."""
    if not meeting.is_published or not meeting.lesson.is_published:
        return False
    series = meeting.lesson.series
    return bool(series.is_active and series.is_published)


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
    """Current runtime Bible Study meeting visibility (legacy source).

    Delegates to ``BibleStudyMeeting.can_be_seen_by`` so this shadow helper
    can never drift from the real runtime rule: staff/manager override, then
    published meeting/lesson and active published series, then
    ``Profile.small_group`` equality with the meeting's small group.
    """
    return meeting.can_be_seen_by(user)


def user_matches_bible_study_meeting_membership_core(
    user, meeting, target_date=None
):
    """Future-candidate Bible Study meeting visibility (membership-core).

    Shadow-only; no runtime consumer calls this. It keeps the non-belonging
    gates identical to ``can_be_seen_by`` (staff/manager override, published
    meeting/lesson, active published series) but replaces the
    ``Profile.small_group`` equality with membership-core matching: the
    meeting's small group must be mapped to a ``ChurchStructureUnit``, and the
    user's single active primary ``ChurchStructureMembership`` unit must be
    that unit or a descendant of it (same semantics as ServiceEvent
    structure-audience matching).

    Fail-closed rules:

    - ``Profile.small_group`` alone grants nothing here.
    - Requested/rejected/cancelled/ended/future/expired memberships grant
      nothing.
    - Multiple active primary memberships fail closed for non-root units.
    - An unmapped meeting small group grants nothing to ordinary users; the
      readiness audit reports it as ``meeting_unmapped_small_group``.
    """
    if not getattr(user, "is_authenticated", False):
        return False

    if _user_has_manager_override(user):
        return True

    if not _meeting_is_member_visible(meeting):
        return False

    unit = get_small_group_structure_unit(meeting.small_group)
    if unit is None:
        return False

    return user_matches_membership_structure_audience(
        user, [unit], target_date=target_date
    )


def compare_bible_study_meeting_visibility(user, meeting, target_date=None):
    """Return a read-only comparison of legacy vs membership-core visibility.

    Returns a dict with:

    - ``legacy_visible``: bool, current runtime answer.
    - ``membership_visible``: bool, future membership-core candidate answer.
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
    elif _user_has_manager_override(user):
        reason_codes.append(REASON_STAFF_OR_MANAGER_OVERRIDE)
    else:
        if not _meeting_is_member_visible(meeting):
            reason_codes.append(REASON_MEETING_NOT_MEMBER_VISIBLE)

        unit = get_small_group_structure_unit(meeting.small_group)
        if unit is None:
            reason_codes.append(REASON_MEETING_UNMAPPED_SMALL_GROUP)

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
            if user_matches_membership_structure_audience(
                user, [unit], target_date=target_date
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
