"""Reviewed Service Profile creation and exact legacy-key FK backfill."""

import copy
import hashlib
import hmac
import json
from collections import Counter

from django.core.exceptions import ValidationError
from django.db import IntegrityError, OperationalError, transaction

from .models import ServiceEvent, ServiceProfile, validate_service_profile_key
from .scheduling_revision import (
    SchedulingRevisionBatchClaimError,
    SchedulingRevisionBusyError,
    claim_scheduling_revisions,
)


PLAN_VERSION = "SERVICE_PROFILE_MAPPING_PLAN_V1"


class ServiceProfileMappingError(RuntimeError):
    """Base class for deterministic operator-facing mapping failures."""


class ServiceProfileMappingInputError(ServiceProfileMappingError):
    pass


class ServiceProfileMappingNotReady(ServiceProfileMappingError):
    pass


class ServiceProfileMappingStale(ServiceProfileMappingError):
    pass


class ServiceProfileMappingBusy(ServiceProfileMappingError):
    pass


def normalize_mapping_inputs(
    *, legacy_key, event_type, name, name_en="", description="", description_en=""
):
    """Normalize and validate only operator-supplied profile metadata."""

    try:
        canonical_key = validate_service_profile_key(legacy_key)
    except ValidationError as exc:
        raise ServiceProfileMappingInputError(
            "Invalid --legacy-key: " + "; ".join(exc.messages)
        ) from exc

    valid_event_types = {value for value, _label in ServiceEvent.EVENT_TYPE_CHOICES}
    if event_type not in valid_event_types:
        raise ServiceProfileMappingInputError(
            "Invalid --event-type. Choose one of: "
            + ", ".join(sorted(valid_event_types))
        )

    values = {
        "key": canonical_key,
        "event_type": event_type,
        "name": name,
        "name_en": name_en or "",
        "description": description or "",
        "description_en": description_en or "",
        "is_active": True,
    }
    candidate = ServiceProfile(**values)
    try:
        candidate.full_clean(validate_unique=False, validate_constraints=False)
    except ValidationError as exc:
        messages = []
        for field, errors in sorted(exc.error_dict.items()):
            messages.extend(f"{field}: {error.message}" for error in errors)
        raise ServiceProfileMappingInputError(
            "Invalid reviewed profile metadata: " + "; ".join(messages)
        ) from exc
    return values


def _iso(value):
    return value.isoformat(timespec="microseconds")


def _event_state(event):
    return {
        "pk": event.pk,
        "start_datetime": _iso(event.start_datetime),
        "status": event.status,
        "service_profile_key": event.service_profile_key,
        "event_type": event.event_type,
        "service_profile_id": event.service_profile_id,
        "scheduling_revision": event.scheduling_revision,
        "updated_at": _iso(event.updated_at),
    }


def _profile_state(profile):
    if profile is None:
        return None
    return {
        "pk": profile.pk,
        "key": profile.key,
        "event_type": profile.event_type,
        "name": profile.name,
        "name_en": profile.name_en,
        "description": profile.description,
        "description_en": profile.description_en,
        "is_active": profile.is_active,
        "created_at": _iso(profile.created_at),
        "updated_at": _iso(profile.updated_at),
    }


def _canonical_plan_payload(plan):
    return {
        "plan_version": PLAN_VERSION,
        "profile": plan["profile"],
        "existing_profile_at_key": plan["existing_profile_at_key"],
        "canonical_equivalent_legacy_keys": plan[
            "canonical_equivalent_legacy_keys"
        ],
        "target_event_count": len(plan["target_events"]),
        "target_events": plan["target_events"],
    }


def serialize_canonical_plan(plan):
    return json.dumps(
        _canonical_plan_payload(plan),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def state_token_for_plan(plan):
    return hashlib.sha256(serialize_canonical_plan(plan).encode("utf-8")).hexdigest()


def _canonical_equivalent_keys(canonical_key, *, using):
    equivalent = []
    raw_keys = (
        ServiceEvent.objects.using(using)
        .exclude(service_profile_key="")
        .values_list("service_profile_key", flat=True)
        .distinct()
    )
    for raw_key in raw_keys:
        try:
            normalized = validate_service_profile_key(raw_key)
        except ValidationError:
            continue
        if normalized == canonical_key:
            equivalent.append(raw_key)
    return sorted(equivalent)


def build_service_profile_mapping_plan(profile_input, *, using="default"):
    """Build complete current review evidence for one exact legacy key."""

    profile_input = dict(profile_input)
    key = profile_input["key"]
    events = list(
        ServiceEvent.objects.using(using)
        .filter(service_profile_key=key)
        .order_by("pk")
    )
    existing_profile = (
        ServiceProfile.objects.using(using).filter(key=key).order_by("pk").first()
    )
    equivalent_keys = _canonical_equivalent_keys(key, using=using)
    target_events = [_event_state(event) for event in events]
    blockers = []

    if not events:
        blockers.append(
            f"NO_TARGET_EVENTS: no ServiceEvent has exact legacy key {key!r}"
        )
    noncanonical = [raw_key for raw_key in equivalent_keys if raw_key != key]
    if noncanonical:
        blockers.append(
            "NONCANONICAL_PERSISTED_LEGACY_KEY: canonical-equivalent stored "
            f"keys require separate repair/review: {noncanonical!r}"
        )
    event_types = sorted({event.event_type for event in events})
    if any(event_type != profile_input["event_type"] for event_type in event_types):
        blockers.append(
            "LEGACY_KEY_EVENT_TYPE_CONFLICT: "
            f"reviewed={profile_input['event_type']!r} stored={event_types!r}"
        )
    if len(event_types) > 1:
        blockers.append(
            "MULTI_TYPE_LEGACY_KEY: one deployment-global key cannot map "
            f"automatically across event types {event_types!r}"
        )
    nonnull = [event for event in events if event.service_profile_id is not None]
    if nonnull:
        blockers.append(
            "TARGET_FK_ALREADY_NON_NULL: initial mapping requires every target "
            f"FK to be NULL; event_ids={[event.pk for event in nonnull]!r}"
        )
    drifted = [
        event
        for event in nonnull
        if event.service_profile.key != event.service_profile_key
        or event.service_profile.event_type != event.event_type
    ]
    if drifted:
        blockers.append(
            "TARGET_FK_DRIFT: mismatching FK identity on event_ids="
            f"{[event.pk for event in drifted]!r}"
        )
    if existing_profile is not None:
        blockers.append(
            "SERVICE_PROFILE_KEY_ALREADY_EXISTS: initial mapping cannot reuse, "
            f"rename, or remap ServiceProfile pk={existing_profile.pk}"
        )

    plan = {
        "plan_version": PLAN_VERSION,
        "profile": profile_input,
        "existing_profile_at_key": _profile_state(existing_profile),
        "canonical_equivalent_legacy_keys": equivalent_keys,
        "target_events": target_events,
        "blockers": blockers,
        "ready": not blockers,
        "summary": {
            "target_event_count": len(events),
            "target_fk_null": len(events) - len(nonnull),
            "target_fk_nonnull": len(nonnull),
            "target_fk_drift": len(drifted),
            "earliest_start_datetime": (
                min((event.start_datetime for event in events), default=None)
            ),
            "latest_start_datetime": (
                max((event.start_datetime for event in events), default=None)
            ),
            "status_counts": dict(
                sorted(Counter(event.status for event in events).items())
            ),
            "scheduling_revisions": [
                {"pk": event.pk, "scheduling_revision": event.scheduling_revision}
                for event in events
            ],
            "blockers": len(blockers),
        },
    }
    plan["state_token"] = state_token_for_plan(plan)
    plan["confirmation_token"] = plan["state_token"] if plan["ready"] else None
    return plan


def _same_token(plan, supplied_token):
    return hmac.compare_digest(plan["state_token"], supplied_token)


def _expected_post_claim_payload(plan):
    expected = copy.deepcopy(_canonical_plan_payload(plan))
    for event in expected["target_events"]:
        event["scheduling_revision"] += 1
    return expected


def _post_claim_state_matches(reviewed_plan, current_plan):
    return _expected_post_claim_payload(reviewed_plan) == _canonical_plan_payload(
        current_plan
    )


def _assign_profile_to_event(event_id, profile, *, using):
    event = ServiceEvent.objects.using(using).get(pk=event_id)
    event.service_profile = profile
    event.save(
        using=using,
        update_fields=["service_profile", "updated_at"],
        _skip_scheduling_revision=True,
    )


def apply_service_profile_mapping(
    profile_input, confirmation_token, *, using="default"
):
    """Atomically create one profile and map the complete exact target set."""

    try:
        with transaction.atomic(using=using):
            reviewed = build_service_profile_mapping_plan(profile_input, using=using)
            if not _same_token(reviewed, confirmation_token):
                raise ServiceProfileMappingStale(
                    "STALE: confirmation token does not match the complete current "
                    "plan; no profile or FK change was committed."
                )
            if not reviewed["ready"]:
                raise ServiceProfileMappingNotReady(
                    "NOT READY: current blockers prevent initial profile mapping."
                )

            expected_revisions = {
                event["pk"]: event["scheduling_revision"]
                for event in reviewed["target_events"]
            }
            try:
                claim_scheduling_revisions(expected_revisions, using=using)
            except SchedulingRevisionBatchClaimError as exc:
                raise ServiceProfileMappingStale(
                    "STALE: one or more target scheduling revisions changed; all "
                    "revision claims were rolled back."
                ) from exc
            except SchedulingRevisionBusyError as exc:
                raise ServiceProfileMappingBusy(
                    "BUSY: SQLite writer serialization was unavailable; no profile "
                    "or FK change was committed."
                ) from exc

            serialized = build_service_profile_mapping_plan(
                profile_input, using=using
            )
            if not serialized["ready"] or not _post_claim_state_matches(
                reviewed, serialized
            ):
                raise ServiceProfileMappingStale(
                    "STALE: reviewed target state changed at the SQLite writer "
                    "boundary; all revision claims were rolled back."
                )

            profile = ServiceProfile.objects.using(using).create(**profile_input)
            for event in serialized["target_events"]:
                _assign_profile_to_event(event["pk"], profile, using=using)
    except OperationalError as exc:
        message = str(exc).lower()
        if "database is locked" in message or "database table is locked" in message:
            raise ServiceProfileMappingBusy(
                "BUSY: database writer serialization was unavailable; no profile "
                "or FK change was committed."
            ) from exc
        raise
    except IntegrityError as exc:
        raise ServiceProfileMappingStale(
            "STALE: profile uniqueness or target integrity changed; the entire "
            "operation was rolled back."
        ) from exc

    return {
        "service_profile_id": profile.pk,
        "service_profiles_created": 1,
        "service_events_mapped": len(reviewed["target_events"]),
        "scheduling_revisions_advanced": len(reviewed["target_events"]),
    }
