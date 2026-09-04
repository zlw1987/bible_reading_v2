"""Canonical runtime interpretation and writes for Service Profile identity.

The ServiceProfile FK is the only runtime identity authority in this module.
The transitional string is read only to classify compatibility or drift; it is
never used to look up or infer a profile.
"""

from dataclasses import dataclass
from enum import StrEnum

from .models import ServiceEvent, ServiceProfile


class ServiceProfileIdentityState(StrEnum):
    PROFILELESS = "profileless"
    LEGACY_ONLY = "legacy_only"
    EXACT = "exact"
    FK_KEY_MISMATCH = "fk_key_mismatch"
    FK_BLANK_KEY = "fk_blank_key"
    EVENT_TYPE_MISMATCH = "event_type_mismatch"


@dataclass(frozen=True)
class ServiceProfileIdentity:
    state: ServiceProfileIdentityState
    event: ServiceEvent
    profile: ServiceProfile | None
    profile_id: int | None
    profile_key: str | None
    compatibility_key: str
    event_type: str
    profile_event_type: str | None

    @property
    def is_exact(self):
        return self.state == ServiceProfileIdentityState.EXACT


class ServiceProfileResolutionFailure(StrEnum):
    IDENTITY_NOT_EXACT = "identity_not_exact"
    PROFILE_INACTIVE = "profile_inactive"


class ServiceProfileResolutionError(RuntimeError):
    """A profile-required read failed with typed identity evidence."""

    def __init__(self, identity, reason):
        self.identity = identity
        self.state = identity.state
        self.reason = reason
        super().__init__(
            "Service Profile resolution failed: "
            f"reason={reason.value} state={identity.state.value}."
        )


class ServiceProfileMutationFailure(StrEnum):
    INVALID_START_STATE = "invalid_start_state"
    INVALID_PROFILE = "invalid_profile"
    LEGACY_KEY_CONFLICT = "legacy_key_conflict"
    EVENT_TYPE_MISMATCH = "event_type_mismatch"
    PROFILE_INACTIVE = "profile_inactive"


class ServiceProfileMutationError(RuntimeError):
    """A supported pair-write was rejected before changing persisted state."""

    def __init__(self, identity, reason):
        self.identity = identity
        self.state = identity.state
        self.reason = reason
        super().__init__(
            "Service Profile mutation failed: "
            f"reason={reason.value} state={identity.state.value}."
        )


def inspect_service_profile_identity(event):
    """Classify one event without writes, repair, inference, or string fallback.

    A relation already loaded with ``select_related('service_profile')`` is
    reused by Django. Otherwise, a non-null FK may require one normal relation
    query. Event-type drift takes precedence if multiple validation-bypassing
    problems overlap; all raw identity fields remain available on the result.
    """

    profile_id = event.service_profile_id
    compatibility_key = event.service_profile_key
    event_type = event.event_type

    if profile_id is None:
        state = (
            ServiceProfileIdentityState.PROFILELESS
            if compatibility_key == ""
            else ServiceProfileIdentityState.LEGACY_ONLY
        )
        return ServiceProfileIdentity(
            state=state,
            event=event,
            profile=None,
            profile_id=None,
            profile_key=None,
            compatibility_key=compatibility_key,
            event_type=event_type,
            profile_event_type=None,
        )

    profile = event.service_profile
    if profile.event_type != event_type:
        state = ServiceProfileIdentityState.EVENT_TYPE_MISMATCH
    elif compatibility_key == "":
        state = ServiceProfileIdentityState.FK_BLANK_KEY
    elif profile.key != compatibility_key:
        state = ServiceProfileIdentityState.FK_KEY_MISMATCH
    else:
        state = ServiceProfileIdentityState.EXACT

    return ServiceProfileIdentity(
        state=state,
        event=event,
        profile=profile,
        profile_id=profile_id,
        profile_key=profile.key,
        compatibility_key=compatibility_key,
        event_type=event_type,
        profile_event_type=profile.event_type,
    )


def require_service_profile(event, *, require_active=False):
    """Return the FK-linked profile only when canonical identity is exact."""

    identity = inspect_service_profile_identity(event)
    if not identity.is_exact:
        raise ServiceProfileResolutionError(
            identity,
            ServiceProfileResolutionFailure.IDENTITY_NOT_EXACT,
        )
    if require_active and not identity.profile.is_active:
        raise ServiceProfileResolutionError(
            identity,
            ServiceProfileResolutionFailure.PROFILE_INACTIVE,
        )
    return identity.profile


def _reject_invalid_mutation_start(identity):
    if identity.state in {
        ServiceProfileIdentityState.FK_KEY_MISMATCH,
        ServiceProfileIdentityState.FK_BLANK_KEY,
        ServiceProfileIdentityState.EVENT_TYPE_MISMATCH,
    }:
        raise ServiceProfileMutationError(
            identity,
            ServiceProfileMutationFailure.INVALID_START_STATE,
        )


def _save_identity_pair(event):
    if event._state.adding:
        event.save()
    else:
        event.save(
            update_fields=[
                "service_profile",
                "service_profile_key",
                "updated_at",
            ]
        )


def prepare_service_event_profile(event, profile, *, target_event_type=None):
    """Validate and prepare an exact identity pair without saving ``event``.

    ``target_event_type`` lets a form validate the submitted event type before
    Django constructs the remaining model fields.  Existing callers omit it
    and validate against the event's current type.

    Returns ``True`` when the in-memory pair changed and ``False`` for an exact
    persisted same-profile no-op. A compatible legacy-only event may be
    assigned only when the caller supplies the actual profile and its key
    exactly matches the stored compatibility key.
    """

    identity = inspect_service_profile_identity(event)
    _reject_invalid_mutation_start(identity)

    if not isinstance(profile, ServiceProfile) or profile.pk is None:
        raise ServiceProfileMutationError(
            identity,
            ServiceProfileMutationFailure.INVALID_PROFILE,
        )

    effective_event_type = target_event_type or event.event_type
    if profile.event_type != effective_event_type:
        raise ServiceProfileMutationError(
            identity,
            ServiceProfileMutationFailure.EVENT_TYPE_MISMATCH,
        )
    if (
        not event._state.adding
        and identity.is_exact
        and identity.profile_id == profile.pk
    ):
        return False
    if not profile.is_active:
        raise ServiceProfileMutationError(
            identity,
            ServiceProfileMutationFailure.PROFILE_INACTIVE,
        )
    if (
        identity.state == ServiceProfileIdentityState.LEGACY_ONLY
        and identity.compatibility_key != profile.key
    ):
        raise ServiceProfileMutationError(
            identity,
            ServiceProfileMutationFailure.LEGACY_KEY_CONFLICT,
        )

    event.service_profile = profile
    event.service_profile_key = profile.key
    return True


def prepare_clear_service_event_profile(event):
    """Prepare a clear without saving; preserve transition/drift evidence."""

    identity = inspect_service_profile_identity(event)
    _reject_invalid_mutation_start(identity)

    if identity.state == ServiceProfileIdentityState.PROFILELESS:
        return False
    if identity.state == ServiceProfileIdentityState.LEGACY_ONLY:
        raise ServiceProfileMutationError(
            identity,
            ServiceProfileMutationFailure.INVALID_START_STATE,
        )

    event.service_profile = None
    event.service_profile_key = ""
    return True


def set_service_event_profile(event, profile):
    """Assign an explicit active profile and persist the exact identity pair."""

    changed = prepare_service_event_profile(event, profile)
    if changed:
        _save_identity_pair(event)
    return changed


def clear_service_event_profile(event):
    """Clear an exact identity pair; refuse to erase transition/drift evidence."""

    changed = prepare_clear_service_event_profile(event)
    if changed:
        _save_identity_pair(event)
    return changed
