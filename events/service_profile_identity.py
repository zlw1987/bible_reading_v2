"""Generic, privacy-bounded Service Profile identity inventory."""

from collections import Counter, defaultdict

from django.core.exceptions import ValidationError

from .models import ServiceEvent, ServiceProfile, validate_service_profile_key


def _canonical_problem(raw_key):
    try:
        canonical = validate_service_profile_key(raw_key)
    except ValidationError:
        return "MALFORMED_LEGACY_KEY"
    if canonical != raw_key:
        return "NONCANONICAL_LEGACY_KEY"
    return None


def _event_summary(events):
    events = list(events)
    exact = [
        event
        for event in events
        if event.service_profile_id is not None
        and event.service_profile.key == event.service_profile_key
        and event.service_profile.event_type == event.event_type
    ]
    nonnull = [event for event in events if event.service_profile_id is not None]
    starts = [event.start_datetime for event in events]
    status_counts = Counter(event.status for event in events)
    return {
        "total_event_count": len(events),
        "fk_null_count": len(events) - len(nonnull),
        "fk_nonnull_count": len(nonnull),
        "exact_match_fk_count": len(exact),
        "fk_mismatch_count": len(nonnull) - len(exact),
        "earliest_start_datetime": min(starts) if starts else None,
        "latest_start_datetime": max(starts) if starts else None,
        "status_counts": {
            value: status_counts[value]
            for value, _label in ServiceEvent.STATUS_CHOICES
            if status_counts[value]
        },
        "referenced_service_profile_ids": sorted(
            {event.service_profile_id for event in nonnull}
        ),
    }


def build_service_profile_identity_inventory(*, using="default"):
    """Return deterministic technical evidence without writing database rows."""

    events = list(
        ServiceEvent.objects.using(using)
        .select_related("service_profile")
        .order_by("service_profile_key", "event_type", "pk")
    )
    profiles = list(ServiceProfile.objects.using(using).order_by("pk"))
    profile_by_key = {profile.key: profile for profile in profiles}

    grouped = defaultdict(list)
    blank_events = []
    for event in events:
        if event.service_profile_key:
            grouped[(event.service_profile_key, event.event_type)].append(event)
        else:
            blank_events.append(event)

    types_by_key = defaultdict(set)
    for key, event_type in grouped:
        types_by_key[key].add(event_type)
    conflicting_keys = sorted(
        key for key, event_types in types_by_key.items() if len(event_types) > 1
    )

    blockers = []
    legacy_groups = []
    for (key, event_type), group_events in sorted(grouped.items()):
        key_problem = _canonical_problem(key)
        if key_problem:
            blockers.append(f"{key_problem}: legacy_key={key!r}")
        if key in conflicting_keys:
            blockers.append(
                "MULTI_TYPE_LEGACY_KEY: "
                f"legacy_key={key!r} event_types={sorted(types_by_key[key])!r}"
            )
        summary = _event_summary(group_events)
        profile = profile_by_key.get(key)
        legacy_groups.append(
            {
                "legacy_key": key,
                "event_type": event_type,
                **summary,
                "matching_service_profile_id": (
                    profile.pk
                    if profile is not None and profile.event_type == event_type
                    else None
                ),
                "matching_profile_exists": bool(
                    profile is not None and profile.event_type == event_type
                ),
                "legacy_key_integrity": key_problem or "OK",
                "multi_type_conflict": key in conflicting_keys,
            }
        )

    # A conflict is one blocker per key, even though it is visible on each group.
    blockers = list(dict.fromkeys(blockers))

    profile_rows = []
    for profile in profiles:
        linked_events = [
            event for event in events if event.service_profile_id == profile.pk
        ]
        exact_linked = [
            event
            for event in linked_events
            if event.service_profile_key == profile.key
            and event.event_type == profile.event_type
        ]
        mismatched = len(linked_events) - len(exact_linked)
        matching_group_exists = (profile.key, profile.event_type) in grouped
        profile_problem = _canonical_problem(profile.key)
        if profile_problem:
            blockers.append(
                f"{profile_problem.replace('LEGACY', 'PROFILE')}: profile_pk={profile.pk} key={profile.key!r}"
            )
        if mismatched:
            blockers.append(
                "PROFILE_LINK_DRIFT: "
                f"profile_pk={profile.pk} mismatching_linked_events={mismatched}"
            )

        statuses = []
        if not linked_events:
            statuses.append("ZERO_LINKED_EVENTS")
        if matching_group_exists:
            statuses.append("MATCHES_LEGACY_GROUP")
        else:
            statuses.append("NO_MATCHING_LEGACY_GROUP")
        if exact_linked:
            statuses.append("EXACT_LINKED_EVENTS")
        if mismatched:
            statuses.append("MISMATCHED_LINKED_EVENTS")
        profile_rows.append(
            {
                "pk": profile.pk,
                "key": profile.key,
                "event_type": profile.event_type,
                "name": profile.name,
                "name_en": profile.name_en,
                "is_active": profile.is_active,
                "linked_service_event_count": len(linked_events),
                "exact_linked_event_count": len(exact_linked),
                "mismatched_linked_event_count": mismatched,
                "legacy_consistency_status": statuses,
            }
        )

    exact_events = sum(
        row["exact_match_fk_count"] for row in legacy_groups
    )
    fk_nonnull = sum(event.service_profile_id is not None for event in events)
    drifted = fk_nonnull - exact_events
    for row in legacy_groups:
        if row["fk_mismatch_count"]:
            blockers.append(
                "EVENT_FK_DRIFT: "
                f"legacy_key={row['legacy_key']!r} event_type={row['event_type']!r} "
                f"events={row['fk_mismatch_count']}"
            )
    blank_summary = _event_summary(blank_events)
    if blank_summary["fk_nonnull_count"]:
        blockers.append(
            "BLANK_LEGACY_KEY_WITH_FK: "
            f"events={blank_summary['fk_nonnull_count']}"
        )
    blockers = list(dict.fromkeys(blockers))

    return {
        "legacy_groups": legacy_groups,
        "blank_legacy_key": blank_summary,
        "service_profiles": profile_rows,
        "conflicting_multi_type_legacy_keys": conflicting_keys,
        "integrity_blockers": blockers,
        "summary": {
            "service_events_total": len(events),
            "blank_legacy_key_events": len(blank_events),
            "nonblank_legacy_key_events": len(events) - len(blank_events),
            "distinct_nonblank_legacy_keys": len(types_by_key),
            "distinct_legacy_key_type_groups": len(legacy_groups),
            "conflicting_multi_type_legacy_keys": len(conflicting_keys),
            "service_profiles_total": len(profiles),
            "events_fk_null": len(events) - fk_nonnull,
            "events_fk_nonnull": fk_nonnull,
            "exact_dual_consistent_events": exact_events,
            "drifted_fk_events": drifted,
            "integrity_blockers": len(blockers),
        },
    }
