"""Runtime Bible Study v2 meeting visibility helpers."""

from django.db import models
from django.utils import timezone

from accounts.models import ChurchStructureMembership, ChurchStructureUnit
from accounts.permissions import (
    CAP_MANAGE_BIBLE_STUDIES,
    CAP_PUBLISH_BIBLE_STUDY_GUIDES,
    has_capability,
)


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


def _collect_units_and_descendant_ids(unit_ids):
    collected = set()
    frontier = [unit_id for unit_id in unit_ids if unit_id is not None]

    while frontier:
        collected.update(frontier)
        frontier = list(
            ChurchStructureUnit.objects.filter(parent_id__in=frontier)
            .exclude(id__in=collected)
            .values_list("id", flat=True)
        )

    return collected


def meeting_has_audience_scope_rows(meeting):
    """Return whether a meeting has any BibleStudyMeetingAudienceScope rows."""
    return meeting.audience_scope_links.exists()


def user_matches_meeting_audience_scopes(user, meeting, target_date=None):
    """Match an ordinary member to a meeting via its audience-scope rows.

    BS-STRUCT.1E: a meeting with one or more ``BibleStudyMeetingAudienceScope``
    rows uses those rows as the visibility source of truth. The user matches
    when their single active primary ``ChurchStructureMembership.unit`` is one of
    the meeting's audience units or a descendant of one of them. Unlike the
    legacy ``small_group`` path, the audience unit may be any structure level
    (small group, district, CM/EM, ...), so no ``UNIT_SMALL_GROUP`` gate is
    applied here. ``Profile.small_group`` is never consulted.

    Fail-closed: no audience rows, no single active primary membership, or a
    membership outside every audience unit's subtree all return ``False``.
    """
    audience_unit_ids = list(
        meeting.audience_scope_links.values_list("unit_id", flat=True)
    )
    if not audience_unit_ids:
        return False

    membership_unit = _get_single_active_primary_membership_unit(
        user, target_date=target_date
    )
    if membership_unit is None:
        return False

    return membership_unit.id in _collect_units_and_descendant_ids(audience_unit_ids)


def get_membership_audience_candidate_unit_ids(user, target_date=None):
    """Return ancestor-or-self unit ids of a user's active primary membership.

    BS-STRUCT.1E: a meeting whose audience-scope row targets any of these units
    includes the user, because the user's membership unit is that unit or a
    descendant of it. Returns an empty list when the user has no single active
    primary membership. Used to pre-filter audience-row meetings for the V2
    landing/Today read path; final per-meeting authority stays with
    ``BibleStudyMeeting.can_be_seen_by``.
    """
    membership_unit = _get_single_active_primary_membership_unit(
        user, target_date=target_date
    )
    if membership_unit is None:
        return []

    return [
        unit.id
        for unit in membership_unit.get_ancestors() + [membership_unit]
        if unit.id is not None
    ]


def filter_users_for_meeting_audience(users, meeting, target_date=None):
    """Filter a user queryset to a meeting's audience-row candidate members.

    BS-STRUCT.2A: role / worship pickers read meeting audience rows.
    When a meeting has one or more ``BibleStudyMeetingAudienceScope`` rows, the
    candidates are users with exactly one active primary
    ``ChurchStructureMembership`` whose unit is one of the meeting's audience
    units or a descendant of one of them. The audience unit may be any structure
    level (small group, district, CM/EM, custom/fellowship, ...), so no
    ``UNIT_SMALL_GROUP`` gate is applied and ``Profile.small_group`` is never
    consulted. The legacy ``BibleStudyMeeting.small_group`` mirror was removed
    in BS-MEETING-MIRROR.1A.

    Fail-closed: no meeting, zero audience rows, no single active primary
    membership, or a membership outside every audience unit's subtree excludes
    the user.
    """
    if meeting is None:
        return users.none()

    audience_unit_ids = list(
        meeting.audience_scope_links.values_list("unit_id", flat=True)
    )
    if not audience_unit_ids:
        return users.none()

    target_date = target_date or timezone.localdate()
    active_primary_memberships = ChurchStructureMembership.objects.filter(
        status=ChurchStructureMembership.STATUS_ACTIVE,
        is_primary=True,
        start_date__lte=target_date,
    ).filter(models.Q(end_date__isnull=True) | models.Q(end_date__gte=target_date))
    single_active_primary_user_ids = (
        active_primary_memberships.values("user_id")
        .annotate(active_primary_count=models.Count("id"))
        .filter(active_primary_count=1)
        .values("user_id")
    )
    matching_user_ids = active_primary_memberships.filter(
        unit_id__in=_collect_units_and_descendant_ids(audience_unit_ids),
    ).values("user_id")

    return users.filter(id__in=matching_user_ids).filter(
        id__in=single_active_primary_user_ids,
    )
