"""Canonical Worship ownership validation for TeamAssignment writes."""

from django.core.exceptions import NON_FIELD_ERRORS, ValidationError

from .worship_governance import (
    CURRENT_WORSHIP_ASSIGNMENT_STATUSES,
    inspect_worship_ownership_consistency,
    resolve_worship_rotation_pool_for_team,
)


WORSHIP_ASSIGNMENT_OWNERSHIP_ERROR_CODE = "worship_assignment_ownership"
WORSHIP_ASSIGNMENT_RETARGET_ERROR_CODE = "worship_assignment_retarget"

WORSHIP_ASSIGNMENT_OWNERSHIP_ERROR = (
    "This Worship assignment does not match the event's selected Worship Team. "
    "Select the exact eligible Worship Team first, or resolve the existing "
    "Worship assignment conflict."
)
WORSHIP_ASSIGNMENT_RETARGET_ERROR = (
    "A Worship assignment cannot be moved to another event or team. Cancel or "
    "complete it without changing its event or team, then create a separate "
    "assignment if needed."
)


def team_resolves_through_worship_pool(team):
    resolution = resolve_worship_rotation_pool_for_team(team)
    return resolution.pool is not None


def _error(message, code):
    raise ValidationError(
        {NON_FIELD_ERRORS: ValidationError(message, code=code)}
    )


def _persisted_assignment(assignment):
    if not getattr(assignment, "pk", None):
        return None
    return (
        assignment.__class__.objects.select_related(
            "service_event",
            "service_event__rotation_anchor_team",
            "ministry_team",
        )
        .filter(pk=assignment.pk)
        .first()
    )


def worship_assignment_serialization_event_ids(assignment):
    """Return ServiceEvent ids that serialize a current Worship write.

    Current writes that touch either side of the Worship boundary serialize on
    the exact ServiceEvent row(s). Pure downstream writes and safe transitions
    out of the current operational set do not use this Worship-specific step.
    """

    if (
        not assignment.service_event_id
        or not assignment.ministry_team_id
        or assignment.status not in CURRENT_WORSHIP_ASSIGNMENT_STATUSES
    ):
        return ()

    persisted = _persisted_assignment(assignment)
    proposed_is_worship = team_resolves_through_worship_pool(
        assignment.ministry_team
    )
    persisted_is_worship = bool(
        persisted
        and team_resolves_through_worship_pool(persisted.ministry_team)
    )
    if not proposed_is_worship and not persisted_is_worship:
        return ()

    event_ids = {assignment.service_event_id}
    if persisted is not None:
        event_ids.add(persisted.service_event_id)
    return tuple(sorted(event_ids))


def lock_service_events_for_worship_assignment_write(assignment, *, using):
    """Read Worship-write serialization points in stable id order.

    ``select_for_update()`` adds row locks on supporting databases. SQLite does
    not provide that guarantee; the event scheduling-revision write performed
    by the caller is the target SQLite serialization boundary.
    """

    event_ids = worship_assignment_serialization_event_ids(assignment)
    if not event_ids:
        return {}

    # Local import avoids an events.models -> ministry.models load cycle.
    from events.models import ServiceEvent

    locked_events = {
        event.pk: event
        for event in ServiceEvent.objects.using(using)
        .select_for_update()
        .filter(pk__in=event_ids)
        .order_by("pk")
    }
    if set(locked_events) != set(event_ids):
        _error(
            WORSHIP_ASSIGNMENT_OWNERSHIP_ERROR,
            WORSHIP_ASSIGNMENT_OWNERSHIP_ERROR_CODE,
        )
    return locked_events


def validate_worship_assignment_write(assignment):
    """Fail closed when a proposed TeamAssignment violates Worship ownership.

    Safe transitions out of the current operational set remain available.  A
    persisted Worship row may be cancelled or completed without first repairing
    an existing conflict, but that repair action may not also retarget the row.
    """

    if not assignment.service_event_id or not assignment.ministry_team_id:
        return

    persisted = _persisted_assignment(assignment)
    proposed_is_worship = team_resolves_through_worship_pool(
        assignment.ministry_team
    )
    persisted_is_worship = bool(
        persisted
        and team_resolves_through_worship_pool(persisted.ministry_team)
    )
    identity_changed = bool(
        persisted
        and (
            persisted.service_event_id != assignment.service_event_id
            or persisted.ministry_team_id != assignment.ministry_team_id
        )
    )

    if identity_changed and (persisted_is_worship or proposed_is_worship):
        # Worship-boundary identity is immutable for valid current, conflicting,
        # and historical rows alike.  Repair is an in-place transition out of
        # the current set followed by a separate assignment when needed.
        _error(
            WORSHIP_ASSIGNMENT_RETARGET_ERROR,
            WORSHIP_ASSIGNMENT_RETARGET_ERROR_CODE,
        )

    if assignment.status not in CURRENT_WORSHIP_ASSIGNMENT_STATUSES:
        return
    if not proposed_is_worship:
        return

    inspection = inspect_worship_ownership_consistency(
        assignment.service_event
    )
    eligible_team_ids = {
        candidate.team.pk for candidate in inspection.eligible_candidates
    }
    other_current = tuple(
        reference
        for reference in inspection.current_worship_assignments
        if reference.assignment_id != assignment.pk
    )
    if (
        inspection.selected_team is None
        or not inspection.selected_team_is_eligible
        or assignment.ministry_team_id != inspection.selected_team.pk
        or assignment.ministry_team_id not in eligible_team_ids
        or other_current
    ):
        _error(
            WORSHIP_ASSIGNMENT_OWNERSHIP_ERROR,
            WORSHIP_ASSIGNMENT_OWNERSHIP_ERROR_CODE,
        )
