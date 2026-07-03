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
