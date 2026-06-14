"""Group progress membership-core shadow comparison + runtime selectors (CS-CORE.4E/4F).

This module computes a **shadow** membership-core candidate answer for the group
progress default group and roster, alongside the legacy ``Profile.small_group``
baseline answer, so that divergence can be observed (``compute_group_progress_shadow``
/ ``compute_group_progress_roster_shadow``). That legacy baseline is now a
diagnostic / rollback comparison, not the page's live source for the switched pieces.
This module also hosts the membership-core *runtime* selectors that the page now uses:
the visible roster source (``get_membership_core_progress_roster_users``, switched in
CS-CORE.4F.1) and the permission-fenced default selected group
(``get_membership_core_default_progress_group``, switched in CS-CORE.4F.2).

Hard rules (binding, see
``docs/READING_PROGRESS_REFLECTION_PRIVACY_MIGRATION_PLAN.md`` Section 4 and the
no-go rules):

- The shadow functions are a **comparison-only** layer: they must never grant or deny
  access and must never change the roster, default selected group, or permissions.
- The group-progress permission gate and the accessible group list keep using legacy
  ``accounts.permissions.get_accessible_progress_groups()`` and
  ``accounts.permissions.can_view_group_progress_for()``. The 4F.2 default helper is
  **permission-fenced**: it can only suggest a group already in the legacy-accessible
  set, never expand it.
- The membership-core candidate is a *roster/default* source only. Ordinary
  ``ChurchStructureMembership`` must never be used to infer group-progress permission
  (privacy invariant 5).

The candidate fails closed on ambiguity (no active primary membership, multiple
active primary memberships, an unmapped selected legacy group, or a membership unit
that is not a mapped small-group unit), mirroring the conservatism of the existing
membership-core selectors in ``accounts/structure_selectors.py`` and the
``audit_reading_privacy_membership_readiness`` command.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from typing import FrozenSet, List, Optional, Tuple

from django.contrib.auth import get_user_model
from django.db.models import Q, QuerySet
from django.utils import timezone

from accounts.models import ChurchStructureMembership, ChurchStructureUnit, SmallGroup


# Reason codes describe which conditions held when the shadow was computed. They are
# boring, additive labels: presence means the condition applied. They never gate
# anything; they are observation only.
REASON_LEGACY_NO_SELECTED_GROUP = "legacy_no_selected_group"
REASON_MEMBERSHIP_NO_ACTIVE_PRIMARY = "membership_no_active_primary"
REASON_MEMBERSHIP_MULTIPLE_ACTIVE_PRIMARY = "membership_multiple_active_primary"
REASON_MEMBERSHIP_UNIT_UNMAPPED = "membership_unit_unmapped"
REASON_SELECTED_GROUP_UNMAPPED = "selected_group_unmapped"
REASON_PROFILE_MEMBERSHIP_MISMATCH = "profile_membership_mismatch"
REASON_DEFAULT_SAME = "default_same"
REASON_DEFAULT_WOULD_CHANGE = "default_would_change"
REASON_ROSTER_SAME = "roster_same"
REASON_ROSTER_WOULD_GAIN = "roster_would_gain"
REASON_ROSTER_WOULD_LOSE = "roster_would_lose"


@dataclass(frozen=True)
class GroupProgressRosterShadow:
    """Read-only roster comparison for a single selected legacy ``SmallGroup``.

    This is the group-level half of :class:`GroupProgressShadow`: it compares the
    legacy ``Profile.small_group`` roster with the membership-core candidate roster
    for one selected group, and never depends on a particular viewer. It changes
    nothing and never grants or denies access.
    """

    selected_group_id: Optional[int]
    legacy_roster_user_ids: FrozenSet[int]
    membership_roster_user_ids: FrozenSet[int]
    same_roster: bool
    would_gain_user_ids: FrozenSet[int]
    would_lose_user_ids: FrozenSet[int]
    reason_codes: Tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class GroupProgressShadow:
    """Read-only comparison between the legacy and membership-core candidates.

    None of these fields drive runtime behavior; this dataclass is a diagnostic /
    rollback comparison only and never grants, denies, or mutates anything.
    ``legacy_selected_group_id`` and ``legacy_roster_user_ids`` are the **legacy
    baseline** (the pre-switch ``Profile.small_group`` answer), kept for comparison
    and rollback — they are no longer what the page renders for the switched pieces.
    The live page now builds its visible roster from the membership-core candidate
    (CS-CORE.4F.1) and prefers a permission-fenced membership-core default selected
    group when no ``?group=`` is given (CS-CORE.4F.2), so the ``membership_`` fields
    mirror the live roster/default source for those switched pieces only. The
    group-progress permission and accessible group list remain legacy-driven and are
    not represented here.
    """

    legacy_selected_group_id: Optional[int]
    membership_candidate_group_id: Optional[int]
    legacy_roster_user_ids: FrozenSet[int]
    membership_roster_user_ids: FrozenSet[int]
    same_default: bool
    same_roster: bool
    would_gain_user_ids: FrozenSet[int]
    would_lose_user_ids: FrozenSet[int]
    reason_codes: Tuple[str, ...] = field(default_factory=tuple)


def _profile_small_group(user):
    profile = getattr(user, "profile", None)
    return getattr(profile, "small_group", None)


def _active_primary_memberships(user, target_date):
    """Return up to two active primary memberships for ``user`` (fail-closed probe).

    Capping at two is enough to distinguish the zero / one / many cases the
    candidate needs to fail closed on, matching ``get_user_primary_membership_unit``.
    """
    if not getattr(user, "is_authenticated", False):
        return []

    user_id = getattr(user, "pk", None)
    if user_id is None:
        return []

    return list(
        ChurchStructureMembership.objects.filter(
            user_id=user_id,
            status=ChurchStructureMembership.STATUS_ACTIVE,
            is_primary=True,
            start_date__lte=target_date,
        )
        .filter(Q(end_date__isnull=True) | Q(end_date__gte=target_date))
        .select_related("unit")[:2]
    )


def _candidate_group_for_unit(unit):
    """Map a membership unit to its single active legacy SmallGroup, or None.

    Fails closed when the unit is not a small-group-type unit, or when it does not
    map to exactly one active legacy ``SmallGroup``.
    """
    if unit is None or unit.unit_type != ChurchStructureUnit.UNIT_SMALL_GROUP:
        return None

    groups = list(
        SmallGroup.objects.filter(is_active=True, church_structure_unit=unit)[:2]
    )
    if len(groups) != 1:
        return None
    return groups[0]


def _membership_core_candidate_default_group(user, target_date):
    """Return ``(candidate_group, reason_code)`` for the user's membership default.

    The candidate is the single active legacy ``SmallGroup`` mapped from the user's
    one active primary ``ChurchStructureMembership`` unit, as of ``target_date``.
    ``reason_code`` is ``None`` on success, otherwise the fail-closed reason:

    - no active primary membership -> ``REASON_MEMBERSHIP_NO_ACTIVE_PRIMARY``
    - more than one active primary membership -> ``REASON_MEMBERSHIP_MULTIPLE_ACTIVE_PRIMARY``
    - unit not a mapped single small-group unit -> ``REASON_MEMBERSHIP_UNIT_UNMAPPED``

    This computes a *candidate only*: it never consults permissions and never grants
    access. It is shared by :func:`compute_group_progress_shadow` (which reports the
    reason code) and :func:`get_membership_core_default_progress_group` (which adds
    the permission fence).
    """
    memberships = _active_primary_memberships(user, target_date)
    if not memberships:
        return None, REASON_MEMBERSHIP_NO_ACTIVE_PRIMARY
    if len(memberships) > 1:
        return None, REASON_MEMBERSHIP_MULTIPLE_ACTIVE_PRIMARY
    candidate_group = _candidate_group_for_unit(memberships[0].unit)
    if candidate_group is None:
        return None, REASON_MEMBERSHIP_UNIT_UNMAPPED
    return candidate_group, None


def _candidate_in_accessible(candidate_group, accessible_groups):
    """Return ``True`` only if ``candidate_group`` is in ``accessible_groups``.

    ``accessible_groups`` is the legacy ``get_accessible_progress_groups()`` result
    and may be a ``QuerySet``, a list/set of ``SmallGroup`` objects, or a list/set of
    group ids. ``None`` (no fence supplied) yields ``False`` so the helper never
    suggests a default without an explicit legacy-accessible set to fence against.
    """
    if candidate_group is None or accessible_groups is None:
        return False

    candidate_id = candidate_group.pk
    if isinstance(accessible_groups, QuerySet):
        return accessible_groups.filter(pk=candidate_id).exists()

    for item in accessible_groups:
        if isinstance(item, int):
            if item == candidate_id:
                return True
        elif getattr(item, "pk", None) == candidate_id:
            return True
    return False


def get_membership_core_default_progress_group(
    user, *, accessible_groups=None, target_date=None
):
    """Permission-fenced membership-core default group for group progress (CS-CORE.4F.2).

    Returns the legacy ``SmallGroup`` that the group-progress page should *prefer* as
    the default selected group when the viewer did not pass an explicit ``?group=``,
    or ``None`` when there is no safe membership-core candidate.

    The candidate is computed by :func:`_membership_core_candidate_default_group`
    (exactly one active primary ``ChurchStructureMembership`` mapped to exactly one
    active legacy ``SmallGroup``; it fails closed on no/multiple active primary
    memberships and on an unmapped/ambiguous unit).

    It is then **permission-fenced**: the candidate is returned only when its id is
    already present in ``accessible_groups`` (the legacy
    ``accounts.permissions.get_accessible_progress_groups()`` result). When
    ``accessible_groups`` is not supplied, or the candidate is not in it, this returns
    ``None``. This helper therefore never grants progress access on its own and never
    expands the accessible group list; ordinary ``ChurchStructureMembership`` confers
    no progress access (privacy invariant 5).
    """
    target_date = target_date or timezone.localdate()
    candidate_group, _reason = _membership_core_candidate_default_group(
        user, target_date
    )
    if candidate_group is None:
        return None
    if not _candidate_in_accessible(candidate_group, accessible_groups):
        return None
    return candidate_group


def _unit_and_descendant_ids(unit):
    """Return the id set of ``unit`` plus all of its descendant units."""
    unit_ids = set()
    frontier = [unit.id]
    while frontier:
        unit_ids.update(frontier)
        frontier = list(
            ChurchStructureUnit.objects.filter(parent_id__in=frontier)
            .exclude(id__in=unit_ids)
            .values_list("id", flat=True)
        )
    return unit_ids


def _legacy_roster_user_ids(selected_group):
    User = get_user_model()
    return set(
        User.objects.filter(profile__small_group=selected_group).values_list(
            "id", flat=True
        )
    )


def _membership_roster_user_ids(selected_group, target_date):
    """Membership-core candidate roster for ``selected_group``.

    A user is in the candidate roster when they have exactly one active primary
    membership whose unit is the selected group's mapped ``ChurchStructureUnit`` or
    a descendant of it. Users with multiple active primary memberships fail closed
    (ambiguous) and are excluded.
    """
    unit = getattr(selected_group, "church_structure_unit", None)
    if unit is None or unit.unit_type != ChurchStructureUnit.UNIT_SMALL_GROUP:
        return set(), True  # unmapped

    target_unit_ids = _unit_and_descendant_ids(unit)

    units_by_user = defaultdict(list)
    rows = (
        ChurchStructureMembership.objects.filter(
            status=ChurchStructureMembership.STATUS_ACTIVE,
            is_primary=True,
            start_date__lte=target_date,
        )
        .filter(Q(end_date__isnull=True) | Q(end_date__gte=target_date))
        .values_list("user_id", "unit_id")
    )
    for user_id, unit_id in rows:
        units_by_user[user_id].append(unit_id)

    roster = set()
    for user_id, unit_ids in units_by_user.items():
        if len(unit_ids) == 1 and unit_ids[0] in target_unit_ids:
            roster.add(user_id)
    return roster, False


def compute_group_progress_roster_shadow(
    selected_group,
    *,
    legacy_roster_user_ids=None,
    target_date=None,
):
    """Compare the legacy vs membership-core roster for one selected legacy group.

    ``selected_group`` is the legacy ``SmallGroup`` to compare. The legacy roster is
    ``User.objects.filter(profile__small_group=selected_group)`` (or the
    ``legacy_roster_user_ids`` the caller already computed); the membership-core
    candidate roster is the set of users with exactly one active primary membership
    whose unit is the group's mapped ``ChurchStructureUnit`` or a descendant.

    The candidate fails closed on an unmapped or wrong-type selected group (it then
    yields an empty candidate roster and the ``selected_group_unmapped`` reason).
    This function only reads; it never grants/denies access and never writes.
    """
    target_date = target_date or timezone.localdate()
    reasons: List[str] = []

    if selected_group is None:
        # Nothing to compare; there is no legacy group to build a roster from.
        return GroupProgressRosterShadow(
            selected_group_id=None,
            legacy_roster_user_ids=frozenset(),
            membership_roster_user_ids=frozenset(),
            same_roster=True,
            would_gain_user_ids=frozenset(),
            would_lose_user_ids=frozenset(),
            reason_codes=(REASON_LEGACY_NO_SELECTED_GROUP,),
        )

    if legacy_roster_user_ids is None:
        legacy_roster = _legacy_roster_user_ids(selected_group)
    else:
        legacy_roster = set(legacy_roster_user_ids)

    membership_roster, unmapped = _membership_roster_user_ids(
        selected_group, target_date
    )
    if unmapped:
        reasons.append(REASON_SELECTED_GROUP_UNMAPPED)

    would_gain = membership_roster - legacy_roster
    would_lose = legacy_roster - membership_roster
    same_roster = legacy_roster == membership_roster

    if same_roster:
        reasons.append(REASON_ROSTER_SAME)
    if would_gain:
        reasons.append(REASON_ROSTER_WOULD_GAIN)
    if would_lose:
        reasons.append(REASON_ROSTER_WOULD_LOSE)

    return GroupProgressRosterShadow(
        selected_group_id=selected_group.id,
        legacy_roster_user_ids=frozenset(legacy_roster),
        membership_roster_user_ids=frozenset(membership_roster),
        same_roster=same_roster,
        would_gain_user_ids=frozenset(would_gain),
        would_lose_user_ids=frozenset(would_lose),
        reason_codes=tuple(reasons),
    )


def get_membership_core_progress_roster_users(selected_group, *, target_date=None):
    """Runtime membership-core roster for the group-progress page (CS-CORE.4F.1).

    Returns the ``User`` queryset that should populate the group-progress roster
    (``member_rows``) for ``selected_group`` using the membership-core candidate
    rule instead of legacy ``Profile.small_group``. A user is included when they
    have exactly one active primary ``ChurchStructureMembership`` whose unit is the
    selected group's mapped small-group ``ChurchStructureUnit`` or a descendant of
    it, evaluated as of ``target_date`` (today by default).

    This is **roster only**, never permission. The caller must already have decided,
    via legacy ``accounts.permissions``, that the viewer may see ``selected_group``;
    ordinary ``ChurchStructureMembership`` confers no progress access on its own
    (privacy invariant 5). It reuses the same fail-closed roster logic as
    :func:`compute_group_progress_roster_shadow`, so it returns an empty queryset
    when ``selected_group`` is ``None``, unmapped, or not a small-group-type unit,
    and excludes users with multiple active primary memberships (ambiguous).

    Ordered by username then id for a deterministic roster compatible with the
    legacy page ordering (legacy used ``order_by("username")``).
    """
    User = get_user_model()
    if selected_group is None:
        return User.objects.none()

    target_date = target_date or timezone.localdate()
    roster_user_ids, unmapped = _membership_roster_user_ids(selected_group, target_date)
    if unmapped or not roster_user_ids:
        return User.objects.none()

    return User.objects.filter(id__in=roster_user_ids).order_by("username", "id")


def compute_group_progress_shadow(
    user,
    selected_group,
    *,
    legacy_roster_user_ids=None,
    target_date=None,
):
    """Compute the legacy-vs-membership-core shadow comparison.

    ``selected_group`` is the ``SmallGroup`` the page actually selected (or ``None``
    when the page had no selectable group); since CS-CORE.4F.2 that selection may
    itself be the permission-fenced membership-core default rather than the legacy
    ``Profile.small_group`` default. ``legacy_roster_user_ids`` is the **legacy
    baseline** roster (the pre-4F.1 ``Profile.small_group`` answer) used for the
    comparison; it may be supplied by the caller, and when omitted it is derived from
    ``Profile.small_group`` here. Note this baseline is no longer the page's live
    roster source — that switched to the membership-core candidate in CS-CORE.4F.1.

    This function only reads. It returns a :class:`GroupProgressShadow` and changes
    nothing.
    """
    target_date = target_date or timezone.localdate()
    reasons: List[str] = []

    legacy_selected_group_id = selected_group.id if selected_group is not None else None
    if selected_group is None:
        reasons.append(REASON_LEGACY_NO_SELECTED_GROUP)

    # Membership-core candidate default group (fail closed on ambiguity). This shares
    # the same candidate logic the runtime CS-CORE.4F.2 default-group helper uses; the
    # reason code (when any) is surfaced here for the shadow/audit comparison only.
    candidate_group, candidate_reason = _membership_core_candidate_default_group(
        user, target_date
    )
    if candidate_reason is not None:
        reasons.append(candidate_reason)

    membership_candidate_group_id = (
        candidate_group.id if candidate_group is not None else None
    )

    same_default = legacy_selected_group_id == membership_candidate_group_id
    reasons.append(REASON_DEFAULT_SAME if same_default else REASON_DEFAULT_WOULD_CHANGE)

    # Profile/membership mismatch is observed against the viewer's own legacy group.
    profile_group = _profile_small_group(user)
    if (
        profile_group is not None
        and candidate_group is not None
        and profile_group.id != candidate_group.id
    ):
        reasons.append(REASON_PROFILE_MEMBERSHIP_MISMATCH)

    # Roster comparison for the selected legacy group only, reusing the group-level
    # helper. The no-selected-group reason is owned by this function (above), so the
    # helper's own REASON_LEGACY_NO_SELECTED_GROUP is dropped here to avoid a
    # duplicate; the public output is otherwise unchanged.
    roster_shadow = compute_group_progress_roster_shadow(
        selected_group,
        legacy_roster_user_ids=legacy_roster_user_ids,
        target_date=target_date,
    )
    if selected_group is not None:
        reasons.extend(
            code
            for code in roster_shadow.reason_codes
            if code != REASON_LEGACY_NO_SELECTED_GROUP
        )

    return GroupProgressShadow(
        legacy_selected_group_id=legacy_selected_group_id,
        membership_candidate_group_id=membership_candidate_group_id,
        legacy_roster_user_ids=roster_shadow.legacy_roster_user_ids,
        membership_roster_user_ids=roster_shadow.membership_roster_user_ids,
        same_default=same_default,
        same_roster=roster_shadow.same_roster,
        would_gain_user_ids=roster_shadow.would_gain_user_ids,
        would_lose_user_ids=roster_shadow.would_lose_user_ids,
        reason_codes=tuple(reasons),
    )
