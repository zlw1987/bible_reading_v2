from accounts.structure_selectors import get_user_primary_membership_unit


def user_has_community_activity_manager_override(user):
    """Return the intentionally narrow 1A management bypass."""
    return bool(
        getattr(user, "is_authenticated", False)
        and (
            getattr(user, "is_staff", False)
            or getattr(user, "is_superuser", False)
        )
    )


def member_visible_community_activities_for(user, queryset=None, target_date=None):
    """Return published activities audience-matching the viewer's membership.

    Member-safe helper for the Church Calendar (CHURCH-CALENDAR.1B). Unlike
    :func:`visible_community_activities_for` and
    ``CommunityActivity.can_be_seen_by``, it grants **no** staff / superuser /
    creator / co-organizer bypass, so pre-publication (draft, pending_review,
    changes_requested) and cancelled/completed activities are never surfaced to
    the member calendar. Only ``published`` activities whose audience rows match
    the viewer's current single active primary ``ChurchStructureMembership`` unit
    or one of its ancestors are returned.

    Fails closed for unauthenticated users, absent or ambiguous active primary
    membership, zero audience rows, and nonmatching audience. ``target_date``
    defaults to the current local date (current belonging only).
    """
    from .models import CommunityActivity

    queryset = queryset if queryset is not None else CommunityActivity.objects.all()

    if not getattr(user, "is_authenticated", False):
        return queryset.none()

    membership_unit = get_user_primary_membership_unit(
        user,
        target_date=target_date,
    )
    if membership_unit is None:
        return queryset.none()

    matching_unit_ids = {
        unit.id
        for unit in [membership_unit, *membership_unit.get_ancestors()]
        if unit.id is not None
    }
    return queryset.filter(
        status=CommunityActivity.STATUS_PUBLISHED,
        audience_scope_links__structure_unit_id__in=matching_unit_ids,
    ).distinct()


def visible_community_activities_for(user, queryset=None, target_date=None):
    """Return activities visible under the COMMUNITY-EVENTS.1A rules.

    Staff and superusers may manage every activity. Ordinary users see only
    published activities with at least one audience row selecting their active
    primary membership unit or one of that unit's ancestors. Zero-row
    activities and users without exactly one active primary membership fail
    closed.
    """
    from .models import CommunityActivity

    queryset = queryset if queryset is not None else CommunityActivity.objects.all()

    if not getattr(user, "is_authenticated", False):
        return queryset.none()

    if user_has_community_activity_manager_override(user):
        return queryset

    membership_unit = get_user_primary_membership_unit(
        user,
        target_date=target_date,
    )
    if membership_unit is None:
        return queryset.none()

    matching_unit_ids = {
        unit.id
        for unit in [membership_unit, *membership_unit.get_ancestors()]
        if unit.id is not None
    }
    return queryset.filter(
        status=CommunityActivity.STATUS_PUBLISHED,
        audience_scope_links__structure_unit_id__in=matching_unit_ids,
    ).distinct()
