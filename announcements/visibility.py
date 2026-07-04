from datetime import datetime

from django.db import models
from django.utils import timezone

from accounts.structure_selectors import get_user_primary_membership_unit


def user_has_announcement_manager_override(user):
    """Return the intentionally narrow ANNOUNCEMENTS.1A management bypass."""
    return bool(
        getattr(user, "is_authenticated", False)
        and (
            getattr(user, "is_staff", False)
            or getattr(user, "is_superuser", False)
        )
    )


def member_visible_announcements_for(user, queryset=None, at=None):
    """Return announcements safe for ordinary member-facing surfaces.

    Every authenticated viewer, including staff and superusers, is subject to
    published status, the active publish window, and structure-audience
    matching. Zero audience rows and missing or nonmatching membership fail
    closed. Management surfaces must use ``visible_announcements_for`` when
    they intentionally need its lifecycle-state bypass.
    """
    from .models import Announcement

    queryset = queryset if queryset is not None else Announcement.objects.all()

    if not getattr(user, "is_authenticated", False):
        return queryset.none()

    at = at or timezone.now()
    target_date = timezone.localdate(at) if isinstance(at, datetime) else at
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
        status=Announcement.STATUS_PUBLISHED,
        publish_start__lte=at,
        audience_scope_links__structure_unit_id__in=matching_unit_ids,
    ).filter(
        models.Q(publish_end__isnull=True) | models.Q(publish_end__gt=at)
    ).distinct()


def visible_announcements_for(user, queryset=None, at=None):
    """Return announcements visible under the ANNOUNCEMENTS.1A rules.

    Staff and superusers may inspect every announcement for future management
    surfaces. Other users use the same published member visibility enforced by
    ``member_visible_announcements_for``.
    """
    from .models import Announcement

    queryset = queryset if queryset is not None else Announcement.objects.all()

    if not getattr(user, "is_authenticated", False):
        return queryset.none()

    if user_has_announcement_manager_override(user):
        return queryset

    return member_visible_announcements_for(user, queryset=queryset, at=at)
