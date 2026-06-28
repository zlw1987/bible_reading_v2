"""Privacy/access helper foundation for unit member/care records.

`MEMBER-RECORD.1D`: a narrow, read-only access-tier layer for
`ChurchStructureUnitMemberRecord`. It defines *who may read which field tier*
from a unit-specific operational/care record. It is a privacy contract only:

- It adds NO non-admin UI, views, templates, or navigation.
- It exposes NO record to ordinary users in this slice.
- It changes NO Django admin behavior, NO schema, and adds NO migration.
- It grants NO permission/capability and reads NO `ChurchStructureMembership`.

Boundaries (see ``docs/MEMBER_RECORD_AND_SERVING_READINESS_PLAN.md`` C.2/C.3):

- This NEVER infers belonging. Canonical belonging stays
  `ChurchStructureMembership`; membership alone grants no access here.
- This NEVER infers serving. `TeamAssignment` / `TeamAssignmentMember` /
  `BibleStudyMeetingRole` grant no access here.
- Lead (operational) access comes ONLY from an explicit active ``lead`` coworker
  role on the record's unit or an ancestor (ancestor-or-self), reusing
  ``can_manage_unit_coworkers``. Non-lead coworkers (edify / worship / caring /
  outreach / assistant) get nothing.
- Scoped non-admin UI that would *use* this contract remains a later, separately
  approved privacy/permission slice.

Access tiers (lowest to highest), with the field tiers each may read:

- ``UNIT_MEMBER_RECORD_ACCESS_NONE`` — nothing.
- ``UNIT_MEMBER_RECORD_ACCESS_SELF_BASIC`` — basic fields only (the record's own
  user). NOT ``group_notes``, NOT ``care_followup_notes``.
- ``UNIT_MEMBER_RECORD_ACCESS_UNIT_LEAD_OPERATIONAL`` — basic fields +
  ``group_notes``. NOT ``care_followup_notes``.
- ``UNIT_MEMBER_RECORD_ACCESS_ADMIN_FULL`` — basic fields + ``group_notes`` +
  ``care_followup_notes`` (staff / superuser).

Field tiers:

- Basic: unit (display path), user display identity, ``attendance_state``,
  ``joined_unit_date``.
- Operational: ``group_notes``.
- Restricted care: ``care_followup_notes``.
"""

from .unit_management import (
    _user_is_structure_coworker_admin,
    can_manage_unit_coworkers,
)

# Access tiers.
UNIT_MEMBER_RECORD_ACCESS_NONE = "none"
UNIT_MEMBER_RECORD_ACCESS_SELF_BASIC = "self_basic"
UNIT_MEMBER_RECORD_ACCESS_UNIT_LEAD_OPERATIONAL = "unit_lead_operational"
UNIT_MEMBER_RECORD_ACCESS_ADMIN_FULL = "admin_full"

# Tiers (other than NONE) that may read each field tier.
_TIERS_WITH_BASIC = frozenset(
    {
        UNIT_MEMBER_RECORD_ACCESS_SELF_BASIC,
        UNIT_MEMBER_RECORD_ACCESS_UNIT_LEAD_OPERATIONAL,
        UNIT_MEMBER_RECORD_ACCESS_ADMIN_FULL,
    }
)
_TIERS_WITH_GROUP_NOTES = frozenset(
    {
        UNIT_MEMBER_RECORD_ACCESS_UNIT_LEAD_OPERATIONAL,
        UNIT_MEMBER_RECORD_ACCESS_ADMIN_FULL,
    }
)
_TIERS_WITH_CARE_NOTES = frozenset({UNIT_MEMBER_RECORD_ACCESS_ADMIN_FULL})


def get_unit_member_record_access_tier(user, record, target_date=None):
    """Return the access tier ``user`` has for ``record``.

    Read-only. Resolution order (highest wins), per the V1 privacy contract:

    1. Staff / superuser → ``ADMIN_FULL``. Distinguished first so a staff user
       who also leads (or owns) the record's unit still gets the full tier.
    2. Active ``lead`` ancestor-or-self for the record's unit →
       ``UNIT_LEAD_OPERATIONAL``. Derived ONLY from
       ``can_manage_unit_coworkers`` (active ``lead`` role on the unit or an
       ancestor). Because staff/superuser were already returned in step 1, the
       remaining truth of that helper here is purely the active-lead path;
       non-lead coworkers, membership, serving, and audience visibility never
       reach this tier.
    3. The record's own user (``record.user == user``) → ``SELF_BASIC``.
    4. Everyone else (including anonymous, no record, no linked user) →
       ``NONE``.

    Never reads ``ChurchStructureMembership`` and never mutates anything.
    """
    if record is None:
        return UNIT_MEMBER_RECORD_ACCESS_NONE
    if not getattr(user, "is_authenticated", False):
        return UNIT_MEMBER_RECORD_ACCESS_NONE

    user_pk = getattr(user, "pk", None)
    if user_pk is None:
        return UNIT_MEMBER_RECORD_ACCESS_NONE

    # 1. Staff / superuser see everything, distinguished before lead/self so the
    #    fuller tier always wins.
    if _user_is_structure_coworker_admin(user):
        return UNIT_MEMBER_RECORD_ACCESS_ADMIN_FULL

    # 2. Active lead ancestor-or-self on the record's unit. can_manage_unit_coworkers
    #    also covers staff/superuser, but those already returned ADMIN_FULL above,
    #    so for a non-staff user this is exactly the active-lead path.
    unit = getattr(record, "unit", None)
    if unit is not None and can_manage_unit_coworkers(
        user, unit, target_date=target_date
    ):
        return UNIT_MEMBER_RECORD_ACCESS_UNIT_LEAD_OPERATIONAL

    # 3. The record's own user, basic only.
    if getattr(record, "user_id", None) == user_pk:
        return UNIT_MEMBER_RECORD_ACCESS_SELF_BASIC

    # 4. No access.
    return UNIT_MEMBER_RECORD_ACCESS_NONE


def can_view_unit_member_record_basic(user, record, target_date=None):
    """Whether ``user`` may read the basic field tier of ``record``."""
    return (
        get_unit_member_record_access_tier(user, record, target_date=target_date)
        in _TIERS_WITH_BASIC
    )


def can_view_unit_member_record_group_notes(user, record, target_date=None):
    """Whether ``user`` may read ``record.group_notes`` (operational tier)."""
    return (
        get_unit_member_record_access_tier(user, record, target_date=target_date)
        in _TIERS_WITH_GROUP_NOTES
    )


def can_view_unit_member_record_care_notes(user, record, target_date=None):
    """Whether ``user`` may read ``record.care_followup_notes`` (admin-full)."""
    return (
        get_unit_member_record_access_tier(user, record, target_date=target_date)
        in _TIERS_WITH_CARE_NOTES
    )


def _user_display_label(record_user):
    """Human-facing label for the record's user (no raw DB id)."""
    if record_user is None:
        return ""
    full_name = record_user.get_full_name()
    if full_name:
        return full_name
    return record_user.get_username()


def build_unit_member_record_safe_snapshot(
    user, record, language="zh", target_date=None
):
    """Return a tier-limited, privacy-safe snapshot dict for ``record``.

    The snapshot contains ONLY fields the user's tier may read. It never
    includes raw internal DB ids or admin URLs, so it is safe to hand to a
    future template without leaking lower tiers' data. Read-only; mutates
    nothing.

    Always present:

    - ``access_tier``
    - ``can_view_basic`` / ``can_view_group_notes`` / ``can_view_care_notes``

    Added only when the tier allows:

    - basic: ``user_display``, ``unit_path``, ``attendance_state_display``,
      ``joined_unit_date``
    - operational: ``group_notes``
    - admin-full: ``care_followup_notes``
    """
    tier = get_unit_member_record_access_tier(
        user, record, target_date=target_date
    )

    snapshot = {
        "access_tier": tier,
        "can_view_basic": tier in _TIERS_WITH_BASIC,
        "can_view_group_notes": tier in _TIERS_WITH_GROUP_NOTES,
        "can_view_care_notes": tier in _TIERS_WITH_CARE_NOTES,
    }

    if tier == UNIT_MEMBER_RECORD_ACCESS_NONE or record is None:
        # No person/unit/care detail at all.
        return snapshot

    if tier in _TIERS_WITH_BASIC:
        record_user = getattr(record, "user", None)
        snapshot["user_display"] = _user_display_label(record_user)
        snapshot["unit_path"] = record.unit_path_label(language)
        snapshot["attendance_state_display"] = record.display_attendance_state(
            language
        )
        snapshot["joined_unit_date"] = record.joined_unit_date

    if tier in _TIERS_WITH_GROUP_NOTES:
        snapshot["group_notes"] = record.group_notes

    if tier in _TIERS_WITH_CARE_NOTES:
        snapshot["care_followup_notes"] = record.care_followup_notes

    return snapshot
