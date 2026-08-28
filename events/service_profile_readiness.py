"""Read-only ServiceEvent profile setup/readiness audit.

MO-S.6D-PROFILE-SETUP.0A inspects one explicitly requested persisted profile
key against an independently constructed local-Sunday contract.  It never
assigns a profile key, repairs audience, imports a workbook, or writes data.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta

from django.db import connection
from django.db.migrations.recorder import MigrationRecorder
from django.utils import timezone

from .models import ServiceEvent


REQUIRED_EVENT_MIGRATIONS = (
    ("0009_serviceeventplannerassignment", "events_serviceeventplannerassignment"),
    ("0010_serviceevent_scheduling_revision", "scheduling_revision"),
    ("0011_serviceevent_service_profile_key", "service_profile_key"),
)


def build_expected_sundays(year):
    """Return every Sunday in ``year`` as local business dates."""

    year = int(year)
    first_day = date(year, 1, 1)
    first_sunday = first_day + timedelta(days=(6 - first_day.weekday()) % 7)
    sundays = []
    current = first_sunday
    while current.year == year:
        sundays.append(current)
        current += timedelta(days=7)
    return tuple(sundays)


def get_schema_readiness():
    """Return migration-recorder and physical-schema readiness without writes."""

    result = {
        "ready": False,
        "checks": [],
        "error": "",
    }
    try:
        recorder = MigrationRecorder(connection)
        applied = recorder.applied_migrations() if recorder.has_table() else set()
        with connection.cursor() as cursor:
            tables = set(connection.introspection.table_names(cursor))
            event_columns = set()
            if ServiceEvent._meta.db_table in tables:
                event_columns = {
                    column.name
                    for column in connection.introspection.get_table_description(
                        cursor, ServiceEvent._meta.db_table
                    )
                }

        for migration_name, schema_target in REQUIRED_EVENT_MIGRATIONS:
            if migration_name == "0009_serviceeventplannerassignment":
                schema_present = schema_target in tables
            else:
                schema_present = schema_target in event_columns
            result["checks"].append(
                {
                    "migration": f"events.{migration_name}",
                    "applied": ("events", migration_name) in applied,
                    "schema_present": schema_present,
                }
            )
        result["ready"] = all(
            check["applied"] and check["schema_present"]
            for check in result["checks"]
        )
    except Exception as exc:  # clean operator evidence, not a backend traceback
        result["error"] = f"Schema readiness inspection failed: {exc}"
    return result


def _local_datetime(value):
    if timezone.is_naive(value):
        value = timezone.make_aware(value, timezone.get_current_timezone())
    return timezone.localtime(value, timezone.get_current_timezone())


def _format_local_time(value):
    value = value.replace(tzinfo=None)
    if value.microsecond:
        return value.isoformat(timespec="microseconds")
    if value.second:
        return value.isoformat(timespec="seconds")
    return value.isoformat(timespec="minutes")


def _local_year_bounds(year):
    local_tz = timezone.get_current_timezone()
    start = timezone.make_aware(datetime(year, 1, 1), local_tz)
    end = timezone.make_aware(datetime(year + 1, 1, 1), local_tz)
    return start, end


def _unit_evidence(unit):
    return {
        "id": unit.pk,
        "code": unit.code,
        "path": unit.path_label("en"),
        "is_active": unit.is_active,
    }


def service_event_audience_readiness(event):
    """Return the canonical audience-readiness evidence for one event.

    This public, side-effect-free helper keeps profile setup audits and later
    exact-profile read-only consumers on the same zero-row, inactive-unit, and
    ancestor/descendant-overlap semantics.
    """

    units = [link.unit for link in event.audience_scope_links.all()]
    units.sort(key=lambda unit: (unit.code, unit.pk))
    selected_ids = {unit.pk for unit in units}
    inactive_ids = [unit.pk for unit in units if not unit.is_active]
    redundant_pairs = set()
    for unit in units:
        for ancestor in unit.get_ancestors():
            if ancestor.pk in selected_ids:
                redundant_pairs.add((ancestor.pk, unit.pk))

    invalid_reasons = []
    if not units:
        invalid_reasons.append("zero_audience_rows")
    if inactive_ids:
        invalid_reasons.append("inactive_audience_units")
    if redundant_pairs:
        invalid_reasons.append("ancestor_descendant_overlap")
    return {
        "row_count": len(units),
        "ordinary_user_fail_closed": not units,
        "ready": not invalid_reasons,
        "invalid_reasons": invalid_reasons,
        "inactive_unit_ids": inactive_ids,
        "ancestor_descendant_pairs": [
            {"ancestor_id": ancestor_id, "descendant_id": descendant_id}
            for ancestor_id, descendant_id in sorted(redundant_pairs)
        ],
        "units": [_unit_evidence(unit) for unit in units],
    }


def _event_evidence(
    event,
    *,
    expected_dates,
    expected_time,
    expected_event_type,
    tagged,
):
    local_start = _local_datetime(event.start_datetime)
    audience = service_event_audience_readiness(event)
    identity_issues = []
    if event.event_type != expected_event_type:
        identity_issues.append("wrong_event_type")
    if local_start.date() not in expected_dates:
        identity_issues.append("wrong_year_or_date")
    if local_start.time().replace(tzinfo=None) != expected_time:
        identity_issues.append("wrong_local_time")

    readiness_issues = list(identity_issues)
    if event.status == ServiceEvent.STATUS_DRAFT:
        readiness_issues.append("draft")
    elif event.status == ServiceEvent.STATUS_CANCELLED:
        readiness_issues.append("cancelled")
    elif event.status not in {
        ServiceEvent.STATUS_PUBLISHED,
        ServiceEvent.STATUS_COMPLETED,
    }:
        readiness_issues.append("unsupported_status")
    readiness_issues.extend(audience["invalid_reasons"])

    host = event.host_language_unit
    selected_team = event.rotation_anchor_team
    evidence = {
        "id": event.pk,
        "local_date": local_start.date().isoformat(),
        "local_time": _format_local_time(local_start.time()),
        "event_type": event.event_type,
        "status": event.status,
        "title": event.title,
        "location": event.location,
        "host_language_unit": _unit_evidence(host) if host else None,
        "audience": audience,
        "service_profile_key": event.service_profile_key,
        "selected_worship_team": (
            {"id": selected_team.pk, "name": selected_team.name}
            if selected_team
            else None
        ),
        "identity_exact": not identity_issues,
        "identity_issues": identity_issues,
        "readiness_issues": readiness_issues,
        "row_ready": not readiness_issues,
        "completed_historical": (
            event.status == ServiceEvent.STATUS_COMPLETED
            and local_start < timezone.localtime(
                timezone.now(), timezone.get_current_timezone()
            )
        ),
    }
    if tagged:
        evidence["classification"] = (
            "EXACT READY MATCH"
            if evidence["row_ready"]
            else "PROFILE-TAGGED ROW NOT READY"
        )
    else:
        evidence["classification"] = (
            "UNTAGGED CANDIDATE / HUMAN REVIEW REQUIRED"
        )
    return evidence


def _other_profile_exact_time_evidence(event):
    """Return safe evidence for an exact-time event owned by another profile."""

    local_start = _local_datetime(event.start_datetime)
    host = event.host_language_unit
    return {
        "id": event.pk,
        "local_date": local_start.date().isoformat(),
        "local_time": _format_local_time(local_start.time()),
        "event_type": event.event_type,
        "status": event.status,
        "title": event.title,
        "location": event.location,
        "host_language_unit": _unit_evidence(host) if host else None,
        "audience": service_event_audience_readiness(event),
        "service_profile_key": event.service_profile_key,
        "classification": (
            "EXACT-TIME EVENT OWNED BY ANOTHER PROFILE — NOT A CANDIDATE"
        ),
    }


def _empty_summary():
    return {
        "data_audit_performed": False,
        "canonical_tagged_rows": None,
        "canonical_identity_rows": None,
        "ready_exact_matches": None,
        "missing_canonical_profile_sundays": None,
        "duplicate_canonical_sundays": None,
        "wrong_time_type_or_date_profile_tagged_rows": None,
        "unexpected_profile_tagged_rows": None,
        "draft_canonical_rows": None,
        "cancelled_canonical_rows": None,
        "completed_historical_canonical_rows": None,
        "zero_audience_canonical_rows": None,
        "invalid_audience_canonical_rows": None,
        "missing_exact_time_candidate_sundays": None,
        "single_untagged_candidate_sundays": None,
        "multiple_untagged_candidate_sundays": None,
        "other_profile_exact_time_events": None,
    }


def build_audit(*, profile_key, year, target_time, event_type):
    """Build deterministic profile readiness evidence without modifying rows."""

    expected_sundays = build_expected_sundays(year)
    expected_dates = set(expected_sundays)
    schema = get_schema_readiness()
    audit = {
        "audit": "MO-S.6D-PROFILE-SETUP.0A",
        "mode": "read-only",
        "profile": {
            "profile_key": profile_key,
            "year": year,
            "local_time": target_time.isoformat(timespec="minutes"),
            "event_type": event_type,
            "timezone": str(timezone.get_current_timezone()),
        },
        "expected_sundays": [value.isoformat() for value in expected_sundays],
        "expected_sunday_count": len(expected_sundays),
        "schema": schema,
        "canonical_tagged_rows": [],
        "sundays": [],
        "summary": _empty_summary(),
        "recommendation": "NOT READY FOR SLICE 8 REAL-DATA MATCHING",
    }
    if not schema["ready"]:
        return audit

    start, end = _local_year_bounds(year)
    related = (
        "host_language_unit",
        "rotation_anchor_team",
    )
    prefetch = "audience_scope_links__unit"
    tagged_events = list(
        ServiceEvent.objects.filter(service_profile_key=profile_key)
        .select_related(*related)
        .prefetch_related(prefetch)
        .order_by("start_datetime", "id")
    )
    requested_type_events = list(
        ServiceEvent.objects.filter(
            event_type=event_type,
            start_datetime__gte=start,
            start_datetime__lt=end,
        )
        .select_related(*related)
        .prefetch_related(prefetch)
        .order_by("start_datetime", "id")
    )

    tagged_facts = [
        _event_evidence(
            event,
            expected_dates=expected_dates,
            expected_time=target_time,
            expected_event_type=event_type,
            tagged=True,
        )
        for event in tagged_events
    ]
    audit["canonical_tagged_rows"] = tagged_facts
    tagged_by_date = defaultdict(list)
    exact_by_date = defaultdict(list)
    for fact in tagged_facts:
        local_date = fact["local_date"]
        tagged_by_date[local_date].append(fact)
        if fact["identity_exact"]:
            exact_by_date[local_date].append(fact)

    services_by_date = defaultdict(list)
    for event in requested_type_events:
        services_by_date[_local_datetime(event.start_datetime).date().isoformat()].append(
            event
        )

    for expected_date in expected_sundays:
        date_key = expected_date.isoformat()
        tagged_for_date = tagged_by_date[date_key]
        exact_for_date = exact_by_date[date_key]
        day_services = services_by_date[date_key]
        other_profile_exact_time_events = [
            _other_profile_exact_time_evidence(event)
            for event in day_services
            if event.service_profile_key
            and event.service_profile_key != profile_key
            and _local_datetime(event.start_datetime)
            .time()
            .replace(tzinfo=None)
            == target_time
        ]
        candidates = []
        if not exact_for_date:
            candidates = [
                _event_evidence(
                    event,
                    expected_dates=expected_dates,
                    expected_time=target_time,
                    expected_event_type=event_type,
                    tagged=False,
                )
                for event in day_services
                if not event.service_profile_key
                and _local_datetime(event.start_datetime)
                .time()
                .replace(tzinfo=None)
                == target_time
            ]
        other_services = []
        for event in day_services:
            local_start = _local_datetime(event.start_datetime)
            if local_start.time().replace(tzinfo=None) == target_time:
                continue
            other_services.append(
                {
                    "id": event.pk,
                    "local_time": _format_local_time(local_start.time()),
                    "status": event.status,
                    "service_profile_key": event.service_profile_key,
                }
            )

        if len(exact_for_date) > 1 or len(tagged_for_date) > 1:
            classification = "DUPLICATE CANONICAL PROFILE ROWS"
        elif exact_for_date:
            classification = (
                "CANONICAL PROFILE READY"
                if exact_for_date[0]["row_ready"]
                else "CANONICAL PROFILE NOT READY"
            )
        elif len(candidates) > 1:
            classification = (
                "MULTIPLE UNTAGGED CANDIDATES — HUMAN SELECTION REQUIRED"
            )
        elif len(candidates) == 1:
            classification = "UNTAGGED CANDIDATE / HUMAN REVIEW REQUIRED"
        else:
            classification = (
                f"NO {target_time.isoformat(timespec='minutes')} CANDIDATE"
            )

        audit["sundays"].append(
            {
                "date": date_key,
                "classification": classification,
                "canonical_tagged_profile_matches": len(tagged_for_date),
                "canonical_exact_identity_matches": len(exact_for_date),
                "untagged_exact_time_candidates": len(candidates),
                "other_profile_exact_time_count": len(
                    other_profile_exact_time_events
                ),
                "other_requested_type_different_time_count": len(other_services),
                "candidates": candidates,
                "other_profile_exact_time_events": other_profile_exact_time_events,
                "other_requested_type_different_time_events": other_services,
            }
        )

    exact_facts = [fact for fact in tagged_facts if fact["identity_exact"]]
    sunday_rows = audit["sundays"]
    summary = {
        "data_audit_performed": True,
        "canonical_tagged_rows": len(tagged_facts),
        "canonical_identity_rows": len(exact_facts),
        "ready_exact_matches": sum(
            row["canonical_tagged_profile_matches"] == 1
            and row["canonical_exact_identity_matches"] == 1
            and exact_by_date[row["date"]][0]["row_ready"]
            for row in sunday_rows
        ),
        "missing_canonical_profile_sundays": sum(
            row["canonical_exact_identity_matches"] == 0 for row in sunday_rows
        ),
        "duplicate_canonical_sundays": sum(
            row["canonical_tagged_profile_matches"] > 1
            or row["canonical_exact_identity_matches"] > 1
            for row in sunday_rows
        ),
        "wrong_time_type_or_date_profile_tagged_rows": sum(
            bool(fact["identity_issues"]) for fact in tagged_facts
        ),
        "unexpected_profile_tagged_rows": sum(
            "wrong_year_or_date" in fact["identity_issues"] for fact in tagged_facts
        ),
        "draft_canonical_rows": sum(
            fact["status"] == ServiceEvent.STATUS_DRAFT for fact in exact_facts
        ),
        "cancelled_canonical_rows": sum(
            fact["status"] == ServiceEvent.STATUS_CANCELLED for fact in exact_facts
        ),
        "completed_historical_canonical_rows": sum(
            fact["completed_historical"] for fact in exact_facts
        ),
        "zero_audience_canonical_rows": sum(
            fact["audience"]["row_count"] == 0 for fact in exact_facts
        ),
        "invalid_audience_canonical_rows": sum(
            not fact["audience"]["ready"] for fact in exact_facts
        ),
        "missing_exact_time_candidate_sundays": sum(
            row["canonical_exact_identity_matches"] == 0
            and row["untagged_exact_time_candidates"] == 0
            for row in sunday_rows
        ),
        "single_untagged_candidate_sundays": sum(
            row["canonical_exact_identity_matches"] == 0
            and row["untagged_exact_time_candidates"] == 1
            for row in sunday_rows
        ),
        "multiple_untagged_candidate_sundays": sum(
            row["canonical_exact_identity_matches"] == 0
            and row["untagged_exact_time_candidates"] > 1
            for row in sunday_rows
        ),
        "other_profile_exact_time_events": sum(
            row["other_profile_exact_time_count"] for row in sunday_rows
        ),
    }
    audit["summary"] = summary
    if (
        summary["ready_exact_matches"] == len(expected_sundays)
        and summary["canonical_tagged_rows"] == len(expected_sundays)
        and summary["duplicate_canonical_sundays"] == 0
        and summary["wrong_time_type_or_date_profile_tagged_rows"] == 0
    ):
        audit["recommendation"] = "PROFILE SETUP READY"
    return audit


def render_text_report(audit):
    """Render staff/operator text; never includes roster or user data."""

    lines = [
        "Service profile readiness audit (MO-S.6D-PROFILE-SETUP.0A, read-only)",
        "=" * 78,
        "mode: read-only (no --apply exists; no data was changed)",
        f"profile: {audit['profile']['profile_key']}",
        f"contract: {audit['profile']['year']} Sundays, "
        f"{audit['profile']['local_time']} {audit['profile']['timezone']}, "
        f"event_type={audit['profile']['event_type']}",
        f"expected_sundays: {audit['expected_sunday_count']}",
        "",
        "Schema readiness:",
    ]
    for check in audit["schema"]["checks"]:
        lines.append(
            f"  {check['migration']}: applied={'YES' if check['applied'] else 'NO'}; "
            f"schema_present={'YES' if check['schema_present'] else 'NO'}"
        )
    if audit["schema"]["error"]:
        lines.append(f"  error: {audit['schema']['error']}")
    lines.append(f"  schema: {'READY' if audit['schema']['ready'] else 'NOT READY'}")
    lines.append("")

    if not audit["summary"]["data_audit_performed"]:
        lines.extend(
            [
                "ServiceEvent data audit: NOT EVALUATED (required schema is not ready)",
                "No ServiceEvent ORM query was attempted.",
                "",
                f"Recommendation: {audit['recommendation']}",
            ]
        )
        return "\n".join(lines)

    lines.append("Canonical profile-tagged rows:")
    if not audit["canonical_tagged_rows"]:
        lines.append("  (none)")
    for fact in audit["canonical_tagged_rows"]:
        issues = ",".join(fact["readiness_issues"]) or "none"
        lines.append(
            f"  event_id={fact['id']} local={fact['local_date']} "
            f"{fact['local_time']} type={fact['event_type']} status={fact['status']} "
            f"audience_rows={fact['audience']['row_count']} "
            f"audience_ready={'YES' if fact['audience']['ready'] else 'NO'} "
            f"classification={fact['classification']} issues={issues}"
        )
        for unit in fact["audience"]["units"]:
            lines.append(
                f"    audience_unit_id={unit['id']} code={unit['code']} "
                f"active={'YES' if unit['is_active'] else 'NO'} path={unit['path']!r}"
            )

    lines.extend(["", "Expected Sunday matrix:"])
    for row in audit["sundays"]:
        lines.append(
            f"  {row['date']}: tagged={row['canonical_tagged_profile_matches']} "
            f"untagged_exact_time={row['untagged_exact_time_candidates']} "
            f"other_profile_exact_time={row['other_profile_exact_time_count']} "
            f"other_requested_type_times="
            f"{row['other_requested_type_different_time_count']} "
            f"— {row['classification']}"
        )
        for candidate in row["candidates"]:
            host = candidate["host_language_unit"]
            team = candidate["selected_worship_team"]
            lines.append(
                f"    UNTAGGED CANDIDATE / HUMAN REVIEW REQUIRED: "
                f"event_id={candidate['id']} local={candidate['local_date']} "
                f"{candidate['local_time']} status={candidate['status']} "
                f"title={candidate['title']!r} location={candidate['location']!r} "
                f"service_profile_key={candidate['service_profile_key']!r}"
            )
            lines.append(
                "      host_language_unit="
                + (
                    f"id={host['id']} code={host['code']} path={host['path']!r}"
                    if host
                    else "(none)"
                )
            )
            lines.append(
                "      selected_worship_team="
                + (f"id={team['id']} name={team['name']!r}" if team else "(none)")
            )
            lines.append(
                f"      audience_rows={candidate['audience']['row_count']} "
                f"audience_ready={'YES' if candidate['audience']['ready'] else 'NO'}"
            )
            for unit in candidate["audience"]["units"]:
                lines.append(
                    f"        audience_unit_id={unit['id']} code={unit['code']} "
                    f"active={'YES' if unit['is_active'] else 'NO'} "
                    f"path={unit['path']!r}"
                )
        for other_profile_event in row["other_profile_exact_time_events"]:
            host = other_profile_event["host_language_unit"]
            lines.append(
                "    EXACT-TIME EVENT OWNED BY ANOTHER PROFILE — NOT A "
                f"CANDIDATE: event_id={other_profile_event['id']} "
                f"local={other_profile_event['local_date']} "
                f"{other_profile_event['local_time']} "
                f"status={other_profile_event['status']} "
                f"title={other_profile_event['title']!r} "
                f"location={other_profile_event['location']!r} "
                "service_profile_key="
                f"{other_profile_event['service_profile_key']!r}"
            )
            lines.append(
                "      host_language_unit="
                + (
                    f"id={host['id']} code={host['code']} path={host['path']!r}"
                    if host
                    else "(none)"
                )
            )
            lines.append(
                f"      audience_rows={other_profile_event['audience']['row_count']} "
                "audience_ready="
                f"{'YES' if other_profile_event['audience']['ready'] else 'NO'}"
            )
            for unit in other_profile_event["audience"]["units"]:
                lines.append(
                    f"        audience_unit_id={unit['id']} code={unit['code']} "
                    f"active={'YES' if unit['is_active'] else 'NO'} "
                    f"path={unit['path']!r}"
                )
        if row["other_requested_type_different_time_events"]:
            rendered = ", ".join(
                f"event_id={item['id']}@{item['local_time']} "
                f"status={item['status']} profile={item['service_profile_key']!r}"
                for item in row["other_requested_type_different_time_events"]
            )
            lines.append(
                "    other requested-type events (different time): " + rendered
            )

    summary = audit["summary"]
    lines.extend(
        [
            "",
            "Summary:",
            f"  Profile: {audit['profile']['profile_key']}",
            f"  Expected Sundays: {audit['expected_sunday_count']}",
            "  Schema: READY",
            f"  Canonical tagged rows: {summary['canonical_tagged_rows']}",
            f"  Ready exact matches: {summary['ready_exact_matches']}",
            f"  Missing canonical profile Sundays: "
            f"{summary['missing_canonical_profile_sundays']}",
            f"  Duplicate canonical Sundays: "
            f"{summary['duplicate_canonical_sundays']}",
            f"  Wrong-time/type/date profile-tagged rows: "
            f"{summary['wrong_time_type_or_date_profile_tagged_rows']}",
            f"  Unexpected profile-tagged rows: "
            f"{summary['unexpected_profile_tagged_rows']}",
            f"  Draft canonical rows: {summary['draft_canonical_rows']}",
            f"  Cancelled canonical rows: {summary['cancelled_canonical_rows']}",
            f"  Completed historical canonical rows: "
            f"{summary['completed_historical_canonical_rows']}",
            f"  Zero-audience canonical rows: "
            f"{summary['zero_audience_canonical_rows']}",
            f"  Invalid-audience canonical rows: "
            f"{summary['invalid_audience_canonical_rows']}",
            f"  Missing {audit['profile']['local_time']} candidate Sundays: "
            f"{summary['missing_exact_time_candidate_sundays']}",
            f"  Single untagged-candidate Sundays: "
            f"{summary['single_untagged_candidate_sundays']}",
            f"  Multiple untagged-candidate Sundays: "
            f"{summary['multiple_untagged_candidate_sundays']}",
            f"  Other-profile exact-time events: "
            f"{summary['other_profile_exact_time_events']}",
            f"  Recommendation: {audit['recommendation']}",
            "",
            "READ-ONLY: no event, profile key, scheduling revision, audience, "
            "serving, planner, membership, audit-log, or notification row was "
            "created, updated, or deleted. Candidate facts are review evidence "
            "only and never establish profile identity.",
        ]
    )
    return "\n".join(lines)
