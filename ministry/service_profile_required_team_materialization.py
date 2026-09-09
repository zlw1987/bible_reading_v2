"""Read-only existing-event preview for Service Profile static defaults.

This module deliberately plans nothing: it reports the current relationship
between reviewed profile configuration and persisted event requirements.
"""

from dataclasses import asdict, dataclass
from datetime import date
from enum import StrEnum
import hashlib
import json

from django.utils import timezone

from events.models import ServiceEvent, ServiceProfile
from events.service_profile_runtime import (
    ServiceProfileIdentityState,
    inspect_service_profile_identity,
)

from .models import ServiceProfileMinistryRequirement
from .service_profile_ministry_requirements import (
    RequirementValidationState,
    active_requirement_validation_reasons,
    inspect_service_profile_ministry_requirements,
)
from .services.worship_governance import resolve_worship_rotation_pool_for_team


PREVIEW_VERSION = "SERVICE_PROFILE_REQUIRED_TEAM_MATERIALIZATION_PREVIEW_V1"


class MaterializationPreviewError(RuntimeError):
    pass


class MaterializationProfileNotFound(MaterializationPreviewError):
    pass


class MaterializationInputError(MaterializationPreviewError):
    pass


class RequiredTeamClassification(StrEnum):
    ALREADY_DEFAULT = "already_default"
    MANUAL_EXTRA = "manual_extra"
    EXPLICIT_WORSHIP = "explicit_worship"
    INVALID_EXPLICIT = "invalid_explicit"
    INACTIVE_DEFAULT_HISTORY = "inactive_default_history"


@dataclass(frozen=True)
class TeamValidityFact:
    team_pk: int
    team_key: str | None
    is_active: bool
    is_assignable: bool
    is_worship_rotation_pool: bool
    resolves_worship_rotation_pool_pk: int | None
    validation_reasons: tuple[str, ...]


@dataclass(frozen=True)
class DefaultFact:
    requirement_pk: int
    team_pk: int
    team_key: str | None
    requirement_updated_at: str
    sort_order: int
    team_validity: TeamValidityFact


@dataclass(frozen=True)
class RequiredTeamRowFact:
    required_team_row_pk: int
    team_pk: int
    team_key: str | None
    created_at: str
    classifications: tuple[RequiredTeamClassification, ...]
    team_validity: TeamValidityFact


@dataclass(frozen=True)
class EventFact:
    event_pk: int
    profile_fk: int | None
    local_start: str
    lifecycle_status: str
    scheduling_revision: int
    identity_state: str
    required_team_row_ids: tuple[int, ...]
    required_team_rows: tuple[RequiredTeamRowFact, ...]
    missing_default_teams: tuple[tuple[int, str | None], ...]


def _iso(value):
    return value.isoformat(timespec="microseconds")


def _team_validity(team, profile):
    resolution = resolve_worship_rotation_pool_for_team(team)
    return TeamValidityFact(
        team_pk=team.pk,
        team_key=team.team_key,
        is_active=team.is_active,
        is_assignable=team.is_assignable,
        is_worship_rotation_pool=team.is_worship_rotation_pool,
        resolves_worship_rotation_pool_pk=(
            resolution.pool.pk if resolution.pool is not None else None
        ),
        validation_reasons=tuple(
            reason.value
            for reason in active_requirement_validation_reasons(profile, team)
        ),
    )


def _fingerprint(payload):
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def inspect_service_profile_required_team_materialization(
    *, profile_key, start_date, end_date
):
    """Inspect one exact active profile in an inclusive local-date range.

    The only event identity selection is ``ServiceEvent.service_profile``.  The
    runtime seam then separately proves each selected event's dual identity.
    """

    if not isinstance(start_date, date) or not isinstance(end_date, date):
        raise MaterializationInputError("start_date and end_date must be dates.")
    if start_date > end_date:
        raise MaterializationInputError("start_date must not be after end_date.")
    try:
        profile = ServiceProfile.objects.get(key=profile_key)
    except ServiceProfile.DoesNotExist as error:
        raise MaterializationProfileNotFound(profile_key) from error

    requirements = inspect_service_profile_ministry_requirements(
        profile_key=profile_key
    )
    active_rows = tuple(
        row for row in requirements.rows if row.requirement_is_active
    )
    invalid_active_rows = tuple(
        row
        for row in active_rows
        if row.validation_state == RequirementValidationState.INVALID_ACTIVE
    )
    active_default_ids = {row.ministry_team_id for row in active_rows}
    materializable_default_ids = {
        row.ministry_team_id
        for row in active_rows
        if row.validation_state == RequirementValidationState.VALID_ACTIVE
    }
    inactive_default_ids = {
        row.ministry_team_id
        for row in requirements.rows
        if not row.requirement_is_active
    }
    requirement_models = {
        requirement.ministry_team_id: requirement
        for requirement in ServiceProfileMinistryRequirement.objects.filter(
            service_profile=profile, is_active=True
        ).select_related("ministry_team").order_by("ministry_team_id", "pk")
    }
    requirement_models_all = {
        requirement.pk: requirement
        for requirement in ServiceProfileMinistryRequirement.objects.filter(
            service_profile=profile
        ).select_related("ministry_team").order_by("pk")
    }
    defaults = tuple(
        DefaultFact(
            requirement_pk=requirement.pk,
            team_pk=requirement.ministry_team_id,
            team_key=requirement.ministry_team.team_key,
            requirement_updated_at=_iso(requirement.updated_at),
            sort_order=requirement.sort_order,
            team_validity=_team_validity(requirement.ministry_team, profile),
        )
        for requirement in requirement_models.values()
    )

    # Database datetime ``__date`` conversion is deployment-timezone dependent;
    # derive the requested configured-local date from each FK-selected event.
    candidates = ServiceEvent.objects.filter(service_profile=profile).select_related(
        "service_profile", "rotation_anchor_team"
    ).prefetch_related(
        "required_team_links__ministry_team"
    )
    events = [
        event
        for event in candidates
        if start_date <= timezone.localtime(event.start_datetime).date() <= end_date
    ]
    events.sort(key=lambda event: (timezone.localtime(event.start_datetime), event.pk))

    event_facts = []
    identity_blockers = []
    for event in events:
        identity = inspect_service_profile_identity(event)
        if identity.state != ServiceProfileIdentityState.EXACT:
            identity_blockers.append({
                "event_pk": event.pk,
                "identity_state": identity.state.value,
            })
        required_links = sorted(
            event.required_team_links.all(), key=lambda link: (link.ministry_team_id, link.pk)
        )
        existing_team_ids = {link.ministry_team_id for link in required_links}
        rows = []
        for link in required_links:
            validity = _team_validity(link.ministry_team, profile)
            classifications = []
            if link.ministry_team_id in active_default_ids:
                classifications.append(RequiredTeamClassification.ALREADY_DEFAULT)
            if validity.is_worship_rotation_pool or validity.resolves_worship_rotation_pool_pk:
                classifications.append(RequiredTeamClassification.EXPLICIT_WORSHIP)
            if validity.validation_reasons:
                classifications.append(RequiredTeamClassification.INVALID_EXPLICIT)
            if link.ministry_team_id in inactive_default_ids:
                classifications.append(RequiredTeamClassification.INACTIVE_DEFAULT_HISTORY)
            if not classifications:
                classifications.insert(0, RequiredTeamClassification.MANUAL_EXTRA)
            rows.append(RequiredTeamRowFact(
                required_team_row_pk=link.pk,
                team_pk=link.ministry_team_id,
                team_key=link.ministry_team.team_key,
                created_at=_iso(link.created_at),
                classifications=tuple(classifications),
                team_validity=validity,
            ))
        missing = tuple(
            (default.team_pk, default.team_key)
            for default in defaults
            if (
                default.team_pk in materializable_default_ids
                and default.team_pk not in existing_team_ids
            )
        )
        event_facts.append(EventFact(
            event_pk=event.pk,
            profile_fk=event.service_profile_id,
            local_start=_iso(timezone.localtime(event.start_datetime)),
            lifecycle_status=event.status,
            scheduling_revision=event.scheduling_revision,
            identity_state=identity.state.value,
            required_team_row_ids=tuple(link.pk for link in required_links),
            required_team_rows=tuple(rows),
            missing_default_teams=missing,
        ))

    row_facts = tuple(row for event in event_facts for row in event.required_team_rows)
    summary = {
        "selected_events": len(event_facts),
        "active_defaults": len(defaults),
        "expected_default_pairs": len(event_facts) * len(materializable_default_ids),
        "already_default_pairs": sum(
            RequiredTeamClassification.ALREADY_DEFAULT in row.classifications
            for row in row_facts
        ),
        "missing_default_pairs": sum(len(event.missing_default_teams) for event in event_facts),
        "manual_extra_rows": sum(RequiredTeamClassification.MANUAL_EXTRA in row.classifications for row in row_facts),
        "explicit_worship_rows": sum(RequiredTeamClassification.EXPLICIT_WORSHIP in row.classifications for row in row_facts),
        "invalid_explicit_rows": sum(RequiredTeamClassification.INVALID_EXPLICIT in row.classifications for row in row_facts),
        "inactive_default_history_rows": sum(RequiredTeamClassification.INACTIVE_DEFAULT_HISTORY in row.classifications for row in row_facts),
        "events_with_missing_defaults": sum(bool(event.missing_default_teams) for event in event_facts),
        "events_with_review_evidence": sum(
            any(len(row.classifications) != 1 or row.classifications[0] != RequiredTeamClassification.ALREADY_DEFAULT for row in event.required_team_rows)
            for event in event_facts
        ),
        "blockers": len(invalid_active_rows) + len(identity_blockers) + (0 if profile.is_active else 1),
    }
    payload = {
        "version": PREVIEW_VERSION,
        "profile": {
            "pk": profile.pk, "key": profile.key, "event_type": profile.event_type,
            "is_active": profile.is_active, "updated_at": _iso(profile.updated_at),
        },
        "scope": {"start_date": start_date.isoformat(), "end_date": end_date.isoformat()},
        "active_defaults": [asdict(item) for item in defaults],
        "inactive_requirement_history": [
            {
                "requirement_pk": row.requirement_id,
                "team_pk": row.ministry_team_id,
                "team_key": row.ministry_team_key,
                "is_active": False,
                "sort_order": requirement_models_all[row.requirement_id].sort_order,
                "updated_at": _iso(requirement_models_all[row.requirement_id].updated_at),
                "team_validity": asdict(_team_validity(
                    requirement_models_all[row.requirement_id].ministry_team,
                    profile,
                )),
            }
            for row in requirements.rows if not row.requirement_is_active
        ],
        "events": [asdict(item) for item in event_facts],
        "identity_blockers": identity_blockers,
        "invalid_active_requirements": [row.requirement_id for row in invalid_active_rows],
        "summary": summary,
    }
    # The public result is intentionally plain deterministic JSON-compatible
    # data; tuple/enums remain an internal typed implementation detail.
    payload = json.loads(json.dumps(payload, default=str))
    payload["state_fingerprint"] = _fingerprint(payload)
    return payload
