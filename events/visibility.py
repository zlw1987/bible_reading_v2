"""Member-safe ServiceEvent visibility for read-only discovery surfaces.

Unlike ``events.views.get_visible_service_events`` /
``ServiceEvent.can_be_seen_by`` / ``can_manage_service_events``, this helper
grants **no** staff, superuser, or manage-capability bypass. Every viewer is
held to the ordinary published/completed lifecycle, ``ServiceEventAudienceScope``
rows, and their *current* single active primary ``ChurchStructureMembership``.

It fails closed for unauthenticated users, absent or ambiguous active primary
membership, zero audience rows, and nonmatching audience. Introduced for the
member-facing Church Calendar (CHURCH-CALENDAR.1B), which must never widen
member visibility through management authority. It intentionally does not use
the root-audience "matches every authenticated user" shortcut of the shared
selector: a viewer without a single active primary membership fails closed here,
mirroring ``announcements.member_visible_announcements_for``.
"""

from accounts.structure_selectors import get_user_primary_membership_unit

from .models import ServiceEvent


def member_visible_service_events_for(user, queryset=None, target_date=None):
    """Return published/completed events audience-matching the viewer's membership.

    ``target_date`` defaults to the current local date (calendar visibility means
    *current* belonging, never reconstructed historical membership).
    """
    queryset = queryset if queryset is not None else ServiceEvent.objects.all()

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
        status__in=[
            ServiceEvent.STATUS_PUBLISHED,
            ServiceEvent.STATUS_COMPLETED,
        ],
        audience_scope_links__unit_id__in=matching_unit_ids,
    ).distinct()
