"""Read-only Service Profile identity inventories.

The normal inventory is FK/Profile-authoritative.  The sole permitted reader
of ``ServiceEvent.service_profile_key`` is the explicit pre-drop inventory
below, retained only to gate the separately approved column-removal slice.
"""

from collections import Counter

from django.core.exceptions import ValidationError

from .models import ServiceEvent, ServiceProfile, validate_service_profile_key


IDENTITY_AUDIT_VERSION = "SERVICE_PROFILE_IDENTITY_V2"
PRE_DROP_LEGACY_KEY_AUDIT_VERSION = "SERVICE_PROFILE_LEGACY_KEY_PRE_DROP_V2"


def build_service_profile_identity_inventory(*, using="default"):
    """Return deterministic permanent FK/Profile evidence without writes."""

    events = list(
        ServiceEvent.objects.using(using)
        .select_related("service_profile")
        .order_by("service_profile_id", "event_type", "pk")
    )
    profiles = list(ServiceProfile.objects.using(using).order_by("pk"))
    linked_by_profile = Counter(event.service_profile_id for event in events)
    type_mismatches = [
        event
        for event in events
        if event.service_profile_id is not None
        and event.service_profile.event_type != event.event_type
    ]
    profile_rows = [
        {
            "pk": profile.pk,
            "key": profile.key,
            "event_type": profile.event_type,
            "name": profile.name,
            "name_en": profile.name_en,
            "is_active": profile.is_active,
            "linked_service_event_count": linked_by_profile[profile.pk],
        }
        for profile in profiles
    ]
    blockers = [
        "EVENT_PROFILE_TYPE_MISMATCH: "
        f"event_id={event.pk} profile_id={event.service_profile_id}"
        for event in type_mismatches
    ]
    return {
        "version": IDENTITY_AUDIT_VERSION,
        "service_profiles": profile_rows,
        "event_profile_type_mismatches": [
            {
                "event_id": event.pk,
                "profile_id": event.service_profile_id,
                "event_type": event.event_type,
                "profile_event_type": event.service_profile.event_type,
            }
            for event in type_mismatches
        ],
        "integrity_blockers": blockers,
        "summary": {
            "service_events_total": len(events),
            "profileless_events": sum(
                event.service_profile_id is None for event in events
            ),
            "fk_linked_events": sum(
                event.service_profile_id is not None for event in events
            ),
            "service_profiles_total": len(profiles),
            "active_service_profiles": sum(profile.is_active for profile in profiles),
            "inactive_service_profiles": sum(
                not profile.is_active for profile in profiles
            ),
            "event_profile_type_mismatch_events": len(type_mismatches),
            "integrity_blockers": len(blockers),
        },
    }


def _legacy_key_problem(raw_key):
    if not raw_key:
        return None
    try:
        canonical = validate_service_profile_key(raw_key)
    except ValidationError:
        return "MALFORMED_LEGACY_KEY"
    return "NONCANONICAL_LEGACY_KEY" if canonical != raw_key else None


def build_pre_drop_legacy_key_inventory(*, using="default"):
    """Read temporary legacy storage only for the Stage-2 pre-drop gate.

    This function never repairs, infers, maps, or writes.  Do not call it from
    normal runtime, readiness, setup, or creation paths.
    """

    events = list(
        ServiceEvent.objects.using(using)
        .select_related("service_profile")
        .order_by("pk")
    )
    rows = []
    counts = Counter()
    for event in events:
        key = event.service_profile_key
        profile = event.service_profile if event.service_profile_id else None
        key_problem = _legacy_key_problem(key)
        states = []
        if profile is None and key:
            states.append("LEGACY_ONLY_BLOCKER")
        if profile is None and not key:
            states.append("PROFILELESS_BLANK")
        if profile is not None and not key:
            states.append("FK_ONLY_BLANK_LEGACY")
        if profile is not None and key and profile.key != key:
            states.append("LEGACY_MISMATCH_BLOCKER")
        if profile is not None and profile.event_type != event.event_type:
            states.append("EVENT_TYPE_BLOCKER")
        if key_problem:
            states.append("MALFORMED_LEGACY_BLOCKER")
        if (
            profile is not None
            and key == profile.key
            and profile.event_type == event.event_type
        ):
            states.append("EXACT_LEGACY_RESIDUE")
        for state in states:
            counts[state] += 1
        rows.append(
            {
                "event_id": event.pk,
                "service_profile_id": event.service_profile_id,
                "profile_key": profile.key if profile is not None else None,
                "event_type": event.event_type,
                "profile_event_type": profile.event_type if profile is not None else None,
                "legacy_key": key,
                "states": states,
            }
        )
    allowed_states = {
        "PROFILELESS_BLANK",
        "FK_ONLY_BLANK_LEGACY",
        "EXACT_LEGACY_RESIDUE",
    }
    blockers = [
        row
        for row in rows
        if any(state not in allowed_states for state in row["states"])
    ]
    return {
        "version": PRE_DROP_LEGACY_KEY_AUDIT_VERSION,
        "rows": rows,
        "blockers": blockers,
        "summary": {
            "total_events": len(events),
            "profileless_blank": counts["PROFILELESS_BLANK"],
            "fk_only_blank_legacy": counts["FK_ONLY_BLANK_LEGACY"],
            "exact_legacy_residue": counts["EXACT_LEGACY_RESIDUE"],
            "legacy_only_blockers": counts["LEGACY_ONLY_BLOCKER"],
            "legacy_mismatch_blockers": counts["LEGACY_MISMATCH_BLOCKER"],
            "malformed_legacy_blockers": counts["MALFORMED_LEGACY_BLOCKER"],
            "event_type_blockers": counts["EVENT_TYPE_BLOCKER"],
            "blocker_rows": len(blockers),
            "ready_for_column_removal": not blockers,
        },
    }
