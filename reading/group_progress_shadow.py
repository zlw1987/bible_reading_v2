"""Group progress membership-core runtime selectors (CS-CORE.4F).

This module hosts the membership-core *runtime* selectors that the group-progress
page uses: the visible roster source (``get_membership_core_progress_roster_users``,
switched in CS-CORE.4F.1) and the permission-fenced default selected group
(``get_membership_core_default_progress_group``, switched in CS-CORE.4F.2).

The former legacy-vs-membership shadow comparison layer
(``compute_group_progress_shadow`` / ``compute_group_progress_roster_shadow`` and
their dataclasses) read the legacy ``Profile.small_group`` baseline and was retired
in PROFILE-SG-FIELD-RETIRE.1A together with the ``Profile.small_group`` field. Group
progress is now fully membership-core; ``Profile.small_group`` no longer exists.

Hard rules (binding, see
``docs/READING_PROGRESS_REFLECTION_PRIVACY_MIGRATION_PLAN.md`` Section 4 and the
no-go rules):

- The group-progress permission gate and the accessible group list use
  ``accounts.permissions.get_accessible_progress_groups()`` and
  ``accounts.permissions.can_view_group_progress_for()``. The 4F.2 default helper is
  **permission-fenced**: it can only suggest a group already in the accessible
  set, never expand it.
- The membership-core candidate is a *roster/default* source only. Ordinary
  ``ChurchStructureMembership`` must never be used to infer group-progress permission
  (privacy invariant 5).

The candidate fails closed on ambiguity (no active primary membership, multiple
active primary memberships, an unmapped selected legacy group, or a membership unit
that is not a mapped small-group unit), mirroring the conservatism of the existing
membership-core selectors in ``accounts/structure_selectors.py``.
"""

from collections import defaultdict

from django.contrib.auth import get_user_model
from django.db.models import Q, QuerySet
from django.utils import timezone

from accounts.models import ChurchStructureMembership, ChurchStructureUnit
from accounts.ordering import order_users_by_visible_identity


# Reason codes describe which fail-closed condition held when the membership-core
# default candidate could not be resolved. They never gate anything; they are
# observation only.
REASON_MEMBERSHIP_NO_ACTIVE_PRIMARY = "membership_no_active_primary"
REASON_MEMBERSHIP_MULTIPLE_ACTIVE_PRIMARY = "membership_multiple_active_primary"
REASON_MEMBERSHIP_UNIT_UNMAPPED = "membership_unit_unmapped"


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
    """Return an active small-group unit candidate, or None.

    Fails closed when the unit is inactive or not a small-group-type unit.
    """
    if (
        unit is None
        or not unit.is_active
        or unit.unit_type != ChurchStructureUnit.UNIT_SMALL_GROUP
    ):
        return None
    return unit


def _membership_core_candidate_default_group(user, target_date):
    """Return ``(candidate_group, reason_code)`` for the user's membership default.

    The candidate is the user's one active primary ``ChurchStructureMembership``
    unit, as of ``target_date``.
    ``reason_code`` is ``None`` on success, otherwise the fail-closed reason:

    - no active primary membership -> ``REASON_MEMBERSHIP_NO_ACTIVE_PRIMARY``
    - more than one active primary membership -> ``REASON_MEMBERSHIP_MULTIPLE_ACTIVE_PRIMARY``
    - unit not an active small-group unit -> ``REASON_MEMBERSHIP_UNIT_UNMAPPED``

    This computes a *candidate only*: it never consults permissions and never grants
    access. :func:`get_membership_core_default_progress_group` adds the permission
    fence on top.
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
    and may be a ``QuerySet``, a list/set of ``ChurchStructureUnit`` objects, or a
    list/set of group-unit ids. ``None`` (no fence supplied) yields ``False`` so the helper never
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

    Returns the canonical small-group unit that the group-progress page should prefer as
    the default selected group when the viewer did not pass an explicit ``?group=``,
    or ``None`` when there is no safe membership-core candidate.

    The candidate is computed by :func:`_membership_core_candidate_default_group`
    (exactly one active primary ``ChurchStructureMembership`` on an active
    small-group unit; it fails closed on no/multiple active primary memberships
    and on inactive/wrong-type units).

    It is then **permission-fenced**: the candidate is returned only when its id is
    already present in ``accessible_groups`` (the
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


def _membership_roster_user_ids(selected_group, target_date):
    """Membership-core candidate roster for ``selected_group``.

    A user is in the candidate roster when they have exactly one active primary
    membership whose unit is the selected canonical small-group unit or a
    descendant of it. Users with multiple active primary memberships fail closed
    (ambiguous) and are excluded. Returns ``(roster_user_ids, invalid_unit)``.
    """
    unit = getattr(selected_group, "church_structure_unit", None) or selected_group
    if (
        unit is None
        or not getattr(unit, "is_active", False)
        or unit.unit_type != ChurchStructureUnit.UNIT_SMALL_GROUP
    ):
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


def get_membership_core_progress_roster_users(selected_group, *, target_date=None):
    """Runtime membership-core roster for the group-progress page (CS-CORE.4F.1).

    Returns the ``User`` queryset that should populate the group-progress roster
    (``member_rows``) for ``selected_group`` using the membership-core candidate
    rule. A user is included when they have exactly one active primary
    ``ChurchStructureMembership`` whose unit is the selected group's mapped
    small-group ``ChurchStructureUnit`` or a descendant of it, evaluated as of
    ``target_date`` (today by default).

    This is **roster only**, never permission. The caller must already have decided,
    via legacy ``accounts.permissions``, that the viewer may see ``selected_group``;
    ordinary ``ChurchStructureMembership`` confers no progress access on its own
    (privacy invariant 5). It returns an empty queryset when ``selected_group`` is
    ``None``, unmapped, or not a small-group-type unit, and excludes users with
    multiple active primary memberships (ambiguous).

    Ordered by visible full-name-or-username label for a deterministic roster.
    """
    User = get_user_model()
    if selected_group is None:
        return User.objects.none()

    target_date = target_date or timezone.localdate()
    roster_user_ids, invalid_unit = _membership_roster_user_ids(selected_group, target_date)
    if invalid_unit or not roster_user_ids:
        return User.objects.none()

    return order_users_by_visible_identity(User.objects.filter(id__in=roster_user_ids))
