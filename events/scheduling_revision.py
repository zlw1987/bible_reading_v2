"""Canonical optimistic concurrency primitives for ServiceEvent scheduling.

The configured SQLite target obtains its single-writer boundary from the first
successful UPDATE in a transaction.  These helpers deliberately use database
expressions and conditional UPDATEs; ``select_for_update()`` is not the target
guarantee.
"""

from dataclasses import dataclass
from enum import StrEnum

from django.db import OperationalError, transaction
from django.db.models import F


class RevisionClaimState(StrEnum):
    CLAIMED = "claimed"
    STALE = "stale"
    MISSING = "missing"


@dataclass(frozen=True)
class SchedulingRevisionResult:
    event_id: int
    state: RevisionClaimState
    revision: int | None

    @property
    def claimed(self):
        return self.state == RevisionClaimState.CLAIMED


class SchedulingRevisionError(RuntimeError):
    """Base class for supported scheduling-write concurrency failures."""


class SchedulingRevisionBusyError(SchedulingRevisionError):
    """SQLite could not establish the writer transaction before timeout."""


class SchedulingRevisionMissingError(SchedulingRevisionError):
    def __init__(self, event_ids):
        self.event_ids = tuple(sorted(set(event_ids)))
        super().__init__(f"ServiceEvent no longer exists: {self.event_ids}")


class SchedulingRevisionBatchClaimError(SchedulingRevisionError):
    def __init__(self, results):
        self.results = tuple(results)
        super().__init__("One or more ServiceEvent scheduling revisions were stale or missing.")


class SchedulingMutationStaleError(SchedulingRevisionError):
    """Persisted scheduling truth changed after the caller's baseline."""


def _service_event_model():
    # Local import avoids events.models -> this module -> events.models cycles.
    from .models import ServiceEvent

    return ServiceEvent


def _translate_busy(exc):
    message = str(exc).lower()
    if "database is locked" in message or "database table is locked" in message:
        raise SchedulingRevisionBusyError(
            "Scheduling is busy. Reload the current state and try again."
        ) from exc
    raise exc


def _current_revision(event_id, *, using):
    ServiceEvent = _service_event_model()
    return (
        ServiceEvent.objects.using(using)
        .filter(pk=event_id)
        .values_list("scheduling_revision", flat=True)
        .first()
    )


def advance_scheduling_revisions(event_ids, *, using="default"):
    """Advance exact events in ascending ID order, atomically and unconditionally.

    Missing IDs fail closed and roll back every earlier advance.
    """

    ServiceEvent = _service_event_model()
    ordered_ids = tuple(sorted(set(int(event_id) for event_id in event_ids)))
    results = []
    try:
        with transaction.atomic(using=using):
            for event_id in ordered_ids:
                updated = (
                    ServiceEvent.objects.using(using)
                    .filter(pk=event_id)
                    .update(scheduling_revision=F("scheduling_revision") + 1)
                )
                if updated != 1:
                    raise SchedulingRevisionMissingError((event_id,))
                results.append(
                    SchedulingRevisionResult(
                        event_id=event_id,
                        state=RevisionClaimState.CLAIMED,
                        revision=_current_revision(event_id, using=using),
                    )
                )
    except OperationalError as exc:
        _translate_busy(exc)
    return tuple(results)


def claim_scheduling_revision(event_id, expected_revision, *, using="default"):
    """Conditionally advance one event and distinguish claimed/stale/missing."""

    ServiceEvent = _service_event_model()
    event_id = int(event_id)
    expected_revision = int(expected_revision)
    try:
        with transaction.atomic(using=using):
            updated = (
                ServiceEvent.objects.using(using)
                .filter(pk=event_id, scheduling_revision=expected_revision)
                .update(scheduling_revision=F("scheduling_revision") + 1)
            )
            if updated == 1:
                return SchedulingRevisionResult(
                    event_id=event_id,
                    state=RevisionClaimState.CLAIMED,
                    revision=_current_revision(event_id, using=using),
                )
            current = _current_revision(event_id, using=using)
            return SchedulingRevisionResult(
                event_id=event_id,
                state=(
                    RevisionClaimState.MISSING
                    if current is None
                    else RevisionClaimState.STALE
                ),
                revision=current,
            )
    except OperationalError as exc:
        _translate_busy(exc)


def claim_scheduling_revisions(expected_revisions, *, using="default"):
    """Claim multiple exact events in deterministic order with no partial commit.

    ``expected_revisions`` may be a mapping or an iterable of ``(id, revision)``.
    Any stale/missing result raises with typed per-event results and rolls back
    every earlier claim.
    """

    items = (
        expected_revisions.items()
        if hasattr(expected_revisions, "items")
        else expected_revisions
    )
    ordered = tuple(sorted((int(pk), int(revision)) for pk, revision in items))
    results = []
    try:
        with transaction.atomic(using=using):
            for event_id, expected_revision in ordered:
                result = claim_scheduling_revision(
                    event_id,
                    expected_revision,
                    using=using,
                )
                results.append(result)
                if not result.claimed:
                    raise SchedulingRevisionBatchClaimError(results)
    except OperationalError as exc:
        _translate_busy(exc)
    return tuple(results)
