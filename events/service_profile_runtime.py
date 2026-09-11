"""Canonical FK-only runtime interpretation and writes for Service Profiles.

The temporary compatibility column remains physically stored until the
separately approved Stage 2 schema slice. Ordinary runtime does not read,
repair, or write it; the explicit pre-drop audit is its sole reader.
"""

from dataclasses import dataclass
from enum import StrEnum

from .models import ServiceEvent, ServiceProfile


class ServiceProfileIdentityState(StrEnum):
    PROFILELESS = "profileless"
    EXACT = "exact"
    EVENT_TYPE_MISMATCH = "event_type_mismatch"


@dataclass(frozen=True)
class ServiceProfileIdentity:
    state: ServiceProfileIdentityState
    event: ServiceEvent
    profile: ServiceProfile | None
    profile_id: int | None
    profile_key: str | None
    event_type: str
    profile_event_type: str | None

    @property
    def is_exact(self):
        return self.state == ServiceProfileIdentityState.EXACT


class ServiceProfileResolutionFailure(StrEnum):
    IDENTITY_NOT_EXACT = "identity_not_exact"
    PROFILE_INACTIVE = "profile_inactive"


class ServiceProfileResolutionError(RuntimeError):
    """A profile-required read failed with typed permanent identity evidence."""

    def __init__(self, identity, reason):
        self.identity = identity
        self.state = identity.state
        self.reason = reason
        super().__init__(
            "Service Profile resolution failed: "
            f"reason={reason.value} state={identity.state.value}."
        )


class ServiceProfileMutationFailure(StrEnum):
    INVALID_PROFILE = "invalid_profile"
    EVENT_TYPE_MISMATCH = "event_type_mismatch"
    PROFILE_INACTIVE = "profile_inactive"


class ServiceProfileMutationError(RuntimeError):
    """A supported FK-only write was rejected before persistence."""

    def __init__(self, identity, reason):
        self.identity = identity
        self.state = identity.state
        self.reason = reason
        super().__init__(
            "Service Profile mutation failed: "
            f"reason={reason.value} state={identity.state.value}."
        )


def inspect_service_profile_identity(event):
    """Classify permanent FK/Profile facts without legacy-column inspection."""

    profile_id = event.service_profile_id
    event_type = event.event_type
    if profile_id is None:
        return ServiceProfileIdentity(
            state=ServiceProfileIdentityState.PROFILELESS,
            event=event,
            profile=None,
            profile_id=None,
            profile_key=None,
            event_type=event_type,
            profile_event_type=None,
        )

    profile = event.service_profile
    state = (
        ServiceProfileIdentityState.EVENT_TYPE_MISMATCH
        if profile.event_type != event_type
        else ServiceProfileIdentityState.EXACT
    )
    return ServiceProfileIdentity(
        state=state,
        event=event,
        profile=profile,
        profile_id=profile_id,
        profile_key=profile.key,
        event_type=event_type,
        profile_event_type=profile.event_type,
    )


def require_service_profile(event, *, require_active=False):
    """Return the FK-linked profile only when permanent identity is valid."""

    identity = inspect_service_profile_identity(event)
    if not identity.is_exact:
        raise ServiceProfileResolutionError(
            identity, ServiceProfileResolutionFailure.IDENTITY_NOT_EXACT
        )
    if require_active and not identity.profile.is_active:
        raise ServiceProfileResolutionError(
            identity, ServiceProfileResolutionFailure.PROFILE_INACTIVE
        )
    return identity.profile


def _save_profile_fk(event):
    if event._state.adding:
        event.save()
    else:
        event.save(update_fields=["service_profile", "updated_at"])


def prepare_service_event_profile(event, profile, *, target_event_type=None):
    """Validate and prepare an FK assignment without saving ``event``.

    ``target_event_type`` lets forms validate submitted type before Django
    constructs remaining fields. This helper intentionally does not inspect or
    synchronize the temporary compatibility column.
    """

    identity = inspect_service_profile_identity(event)
    if not isinstance(profile, ServiceProfile) or profile.pk is None:
        raise ServiceProfileMutationError(
            identity, ServiceProfileMutationFailure.INVALID_PROFILE
        )
    effective_event_type = target_event_type or event.event_type
    if profile.event_type != effective_event_type:
        raise ServiceProfileMutationError(
            identity, ServiceProfileMutationFailure.EVENT_TYPE_MISMATCH
        )
    if not event._state.adding and identity.profile_id == profile.pk:
        return False
    if not profile.is_active:
        raise ServiceProfileMutationError(
            identity, ServiceProfileMutationFailure.PROFILE_INACTIVE
        )
    event.service_profile = profile
    return True


def prepare_clear_service_event_profile(event):
    """Prepare an FK clear without rewriting temporary legacy storage."""

    identity = inspect_service_profile_identity(event)
    if identity.state == ServiceProfileIdentityState.PROFILELESS:
        return False
    event.service_profile = None
    return True


def set_service_event_profile(event, profile):
    """Assign an explicit active profile and persist its FK only."""

    changed = prepare_service_event_profile(event, profile)
    if changed:
        _save_profile_fk(event)
    return changed


def clear_service_event_profile(event):
    """Clear a profile FK without rewriting compatibility storage."""

    changed = prepare_clear_service_event_profile(event)
    if changed:
        _save_profile_fk(event)
    return changed
