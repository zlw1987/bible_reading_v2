"""Runtime Bible Study v2 meeting visibility helpers."""

from django.db import models
from django.utils import timezone

from accounts.models import ChurchStructureMembership, ChurchStructureUnit, SmallGroup
from accounts.permissions import (
    CAP_MANAGE_BIBLE_STUDIES,
    CAP_PUBLISH_BIBLE_STUDY_GUIDES,
    has_capability,
)


def get_small_group_structure_unit(small_group):
    """Return a legacy SmallGroup's mapped structure unit, if any."""
    if small_group is None:
        return None
    return small_group.church_structure_unit


def user_has_bible_study_manager_override(user):
    """Return whether the user bypasses Bible Study member visibility gates."""
    return (
        getattr(user, "is_staff", False)
        or getattr(user, "is_superuser", False)
        or has_capability(user, CAP_MANAGE_BIBLE_STUDIES)
        or has_capability(user, CAP_PUBLISH_BIBLE_STUDY_GUIDES)
    )


def meeting_is_member_visible(meeting):
    """Return whether a meeting passes non-belonging member visibility gates."""
    if not meeting.is_published or not meeting.lesson.is_published:
        return False

    series = meeting.lesson.series
    return bool(series.is_active and series.is_published)


def _get_single_active_primary_membership_unit(user, target_date=None):
    if not getattr(user, "is_authenticated", False):
        return None

    user_id = getattr(user, "pk", None)
    if user_id is None:
        return None

    target_date = target_date or timezone.localdate()
    memberships = list(
        ChurchStructureMembership.objects.filter(
            user_id=user_id,
            status=ChurchStructureMembership.STATUS_ACTIVE,
            is_primary=True,
            start_date__lte=target_date,
        )
        .filter(models.Q(end_date__isnull=True) | models.Q(end_date__gte=target_date))
        .select_related("unit")[:2]
    )
    if len(memberships) != 1:
        return None

    return memberships[0].unit


def _collect_unit_and_descendant_ids(unit):
    unit_ids = set()
    frontier = [unit.id] if unit and unit.id is not None else []

    while frontier:
        unit_ids.update(frontier)
        frontier = list(
            ChurchStructureUnit.objects.filter(parent_id__in=frontier)
            .exclude(id__in=unit_ids)
            .values_list("id", flat=True)
        )

    return unit_ids


def user_matches_meeting_small_group_membership(user, small_group, target_date=None):
    """Match an ordinary member to a v2 meeting's legacy SmallGroup bridge.

    Bible Study meetings are small-group meetings. A legacy group mapped to
    root, district, ministry-context, fellowship, department, or custom units is
    mapping drift for this runtime path and fails closed.
    """
    unit = get_small_group_structure_unit(small_group)
    if unit is None or unit.unit_type != ChurchStructureUnit.UNIT_SMALL_GROUP:
        return False

    membership_unit = _get_single_active_primary_membership_unit(
        user, target_date=target_date
    )
    if membership_unit is None:
        return False

    return membership_unit.id in _collect_unit_and_descendant_ids(unit)


def get_membership_visible_small_groups(user, target_date=None):
    """Return legacy SmallGroups visible to a user through membership-core."""
    membership_unit = _get_single_active_primary_membership_unit(
        user, target_date=target_date
    )
    if membership_unit is None:
        return SmallGroup.objects.none()

    candidate_unit_ids = [
        unit.id
        for unit in membership_unit.get_ancestors() + [membership_unit]
        if unit.unit_type == ChurchStructureUnit.UNIT_SMALL_GROUP
    ]
    if not candidate_unit_ids:
        return SmallGroup.objects.none()

    return SmallGroup.objects.filter(
        church_structure_unit_id__in=candidate_unit_ids,
    ).distinct()
