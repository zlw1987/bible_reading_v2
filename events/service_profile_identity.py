"""Read-only FK/Profile-authoritative Service Profile identity inventory."""

from collections import Counter

from .models import ServiceEvent, ServiceProfile


IDENTITY_AUDIT_VERSION = "SERVICE_PROFILE_IDENTITY_V2"


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
