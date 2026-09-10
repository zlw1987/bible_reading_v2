"""Reviewed, create-only ServiceEvent initialization.

Service Profile ministry requirements are suggestions reviewed at creation
time.  The rows written here are explicit per-event operational truth; this
module provides no live inheritance and is never used by event editing.
"""

from dataclasses import dataclass
from enum import StrEnum
import hashlib
import json

from django.core import signing
from django.db import IntegrityError, OperationalError, transaction
from django.utils import timezone

from accounts.models import ChurchStructureUnit
from ministry.models import MinistryTeam, ServiceProfileMinistryRequirement
from ministry.service_profile_ministry_requirements import (
    RequirementValidationState,
    inspect_service_profile_ministry_requirements,
)

from .models import (
    ServiceEvent,
    ServiceEventAudienceScope,
    ServiceEventRequiredTeam,
    ServiceProfile,
)
from .service_profile_runtime import prepare_service_event_profile


REVIEW_CONTRACT = "SERVICE_EVENT_PROFILE_CREATION_REVIEW_V1"
REVIEW_SIGNING_SALT = "events.service-event-profile-creation-review.v1"
REVIEW_MAX_AGE_SECONDS = 30 * 60


class CreationReviewFailure(StrEnum):
    REVIEW_REQUIRED = "review_required"
    INVALID_REVIEW = "invalid_review"
    PROFILE_UNAVAILABLE = "profile_unavailable"
    PROFILE_TYPE_MISMATCH = "profile_type_mismatch"
    PROFILE_DEFAULTS_CHANGED = "profile_defaults_changed"
    INVALID_PROFILE_DEFAULTS = "invalid_profile_defaults"
    TEAM_CONFIGURATION_CHANGED = "team_configuration_changed"
    AUDIENCE_CHANGED = "audience_changed"
    RECURRING_SET_CHANGED = "recurring_set_changed"
    BUSY = "busy"
    POSTCONDITION = "postcondition"


class ServiceEventCreationError(Exception):
    def __init__(self, failure, detail=""):
        self.failure = CreationReviewFailure(failure)
        self.detail = detail
        super().__init__(detail or self.failure.value)


@dataclass(frozen=True)
class CreationReview:
    signed_payload: str
    profile: ServiceProfile | None
    default_teams: tuple[MinistryTeam, ...]
    inactive_requirement_count: int
    candidate_dates: tuple
    dates_to_create: tuple
    dates_to_skip: tuple


@dataclass(frozen=True)
class CreationResult:
    events: tuple[ServiceEvent, ...]
    dates_to_create: tuple
    dates_to_skip: tuple


def _iso(value):
    return value.isoformat() if value is not None else None


def _fingerprint(value):
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _resolve_profile(profile_id, event_type, *, using="default"):
    if profile_id in (None, ""):
        return None
    try:
        profile = ServiceProfile.objects.using(using).get(pk=int(profile_id))
    except (ServiceProfile.DoesNotExist, TypeError, ValueError) as exc:
        raise ServiceEventCreationError(
            CreationReviewFailure.PROFILE_UNAVAILABLE
        ) from exc
    if not profile.is_active:
        raise ServiceEventCreationError(CreationReviewFailure.PROFILE_UNAVAILABLE)
    if profile.event_type != event_type:
        raise ServiceEventCreationError(
            CreationReviewFailure.PROFILE_TYPE_MISMATCH
        )
    return profile


def _profile_state(profile, *, using="default"):
    if profile is None:
        return None, (), 0

    inspection = inspect_service_profile_ministry_requirements(
        profile_key=profile.key,
        using=using,
    )
    if inspection.invalid_active_requirements:
        raise ServiceEventCreationError(
            CreationReviewFailure.INVALID_PROFILE_DEFAULTS
        )

    requirement_rows = {
        row.pk: row
        for row in ServiceProfileMinistryRequirement.objects.using(using)
        .filter(service_profile_id=profile.pk)
        .select_related("ministry_team")
        .order_by("pk")
    }
    surface = []
    valid_rows = []
    for fact in inspection.rows:
        requirement = requirement_rows.get(fact.requirement_id)
        if requirement is None:
            raise ServiceEventCreationError(
                CreationReviewFailure.PROFILE_DEFAULTS_CHANGED
            )
        surface.append(
            {
                "requirement_id": fact.requirement_id,
                "team_id": fact.ministry_team_id,
                "is_active": fact.requirement_is_active,
                "sort_order": fact.sort_order,
                "requirement_updated_at": _iso(requirement.updated_at),
                "team_updated_at": _iso(requirement.ministry_team.updated_at),
                "validation_state": fact.validation_state.value,
                "validation_reasons": sorted(
                    reason.value for reason in fact.validation_reasons
                ),
            }
        )
        if fact.validation_state == RequirementValidationState.VALID_ACTIVE:
            valid_rows.append((fact.sort_order, fact.requirement_id, requirement))

    valid_rows.sort(key=lambda value: (value[0], value[1], value[2].ministry_team_id))
    default_teams = tuple(row.ministry_team for _, _, row in valid_rows)
    state = {
        "profile": {
            "id": profile.pk,
            "key": profile.key,
            "event_type": profile.event_type,
            "is_active": profile.is_active,
            "updated_at": _iso(profile.updated_at),
        },
        "requirements": surface,
    }
    return state, default_teams, inspection.inactive_requirements


def _normal_team_state(*, using="default"):
    surface = [
        {
            "id": team.pk,
            "is_active": team.is_active,
            "is_assignable": team.is_assignable,
        }
        for team in MinistryTeam.objects.using(using)
        .filter(is_active=True, is_assignable=True)
        .order_by("pk")
    ]
    return _fingerprint(surface)


def _audience_state(audience_ids, *, using="default"):
    requested = tuple(sorted({int(value) for value in audience_ids}))
    if not requested:
        raise ServiceEventCreationError(CreationReviewFailure.AUDIENCE_CHANGED)
    selected = {
        unit.pk: unit
        for unit in ChurchStructureUnit.objects.using(using)
        .filter(pk__in=requested)
        .select_related("parent")
    }
    if set(selected) != set(requested) or any(
        not unit.is_active for unit in selected.values()
    ):
        raise ServiceEventCreationError(CreationReviewFailure.AUDIENCE_CHANGED)

    selected_ids = set(requested)
    surface = []
    for unit_id in requested:
        unit = selected[unit_id]
        ancestor_ids = tuple(ancestor.pk for ancestor in unit.get_ancestors())
        if selected_ids.intersection(ancestor_ids):
            raise ServiceEventCreationError(CreationReviewFailure.AUDIENCE_CHANGED)
        surface.append(
            {
                "id": unit.pk,
                "parent_id": unit.parent_id,
                "unit_type": unit.unit_type,
                "is_active": unit.is_active,
                "ancestor_ids": ancestor_ids,
            }
        )
    return requested, _fingerprint(surface)


def _review_state(profile_id, event_type, audience_ids, *, using="default"):
    profile = _resolve_profile(profile_id, event_type, using=using)
    profile_state, default_teams, inactive_count = _profile_state(
        profile,
        using=using,
    )
    normalized_audience_ids, audience_fingerprint = _audience_state(
        audience_ids,
        using=using,
    )
    return {
        "profile": profile_state["profile"] if profile_state else None,
        "profile_fingerprint": _fingerprint(profile_state),
        "default_team_ids": [team.pk for team in default_teams],
        "team_fingerprint": _normal_team_state(using=using),
        "audience_ids": list(normalized_audience_ids),
        "audience_fingerprint": audience_fingerprint,
    }, profile, default_teams, inactive_count


def _recurring_inputs(cleaned_data):
    return {
        "title": cleaned_data["title"],
        "title_en": cleaned_data.get("title_en") or "",
        "description": cleaned_data.get("description") or "",
        "description_en": cleaned_data.get("description_en") or "",
        "event_type": cleaned_data["event_type"],
        "start_date": _iso(cleaned_data["start_date"]),
        "end_date": _iso(cleaned_data["end_date"]),
        "weekday": int(cleaned_data["weekday"]),
        "start_time": _iso(cleaned_data["start_time"]),
        "end_time": _iso(cleaned_data.get("end_time")),
        "location": cleaned_data.get("location") or "",
        "meeting_link": cleaned_data.get("meeting_link") or "",
        "status": cleaned_data["status"],
    }


def _candidate_dates(cleaned_data):
    result = []
    current_date = cleaned_data["start_date"]
    weekday = int(cleaned_data["weekday"])
    while current_date <= cleaned_data["end_date"]:
        if current_date.weekday() == weekday:
            result.append(current_date)
        current_date += timezone.timedelta(days=1)
    return tuple(result)


def _start_datetime(event_date, cleaned_data):
    return timezone.make_aware(
        timezone.datetime.combine(event_date, cleaned_data["start_time"]),
        timezone.get_current_timezone(),
    )


def _recurring_classification(cleaned_data, *, using="default", ignore_event_id=None):
    candidates = _candidate_dates(cleaned_data)
    create_dates = []
    skip_dates = []
    evidence = []
    for event_date in candidates:
        matches = ServiceEvent.objects.using(using).filter(
            start_datetime=_start_datetime(event_date, cleaned_data),
            event_type=cleaned_data["event_type"],
            title=cleaned_data["title"],
        ).exclude(status=ServiceEvent.STATUS_CANCELLED)
        if ignore_event_id is not None:
            matches = matches.exclude(pk=ignore_event_id)
        rows = list(matches.order_by("pk").values("id", "status", "updated_at"))
        serialized = [
            {
                "id": row["id"],
                "status": row["status"],
                "updated_at": _iso(row["updated_at"]),
            }
            for row in rows
        ]
        evidence.append({"date": _iso(event_date), "matches": serialized})
        (skip_dates if rows else create_dates).append(event_date)
    return {
        "inputs": _recurring_inputs(cleaned_data),
        "candidate_dates": [_iso(value) for value in candidates],
        "create_dates": [_iso(value) for value in create_dates],
        "skip_dates": [_iso(value) for value in skip_dates],
        "duplicate_fingerprint": _fingerprint(evidence),
    }


def build_recurring_event_preview(cleaned_data):
    """Return the existing exact create/skip classification without writing."""

    state = _recurring_classification(cleaned_data)
    return (
        [
            timezone.datetime.fromisoformat(value).date()
            for value in state["create_dates"]
        ],
        [
            timezone.datetime.fromisoformat(value).date()
            for value in state["skip_dates"]
        ],
    )


def build_creation_review(
    *, mode, user, profile_id, event_type, audience_ids, recurring_data=None
):
    if mode not in {"single", "recurring"}:
        raise ServiceEventCreationError(CreationReviewFailure.INVALID_REVIEW)
    state, profile, default_teams, inactive_count = _review_state(
        profile_id,
        event_type,
        audience_ids,
    )
    recurring = None
    if mode == "recurring":
        if recurring_data is None:
            raise ServiceEventCreationError(CreationReviewFailure.INVALID_REVIEW)
        recurring = _recurring_classification(recurring_data)
    payload = {
        "contract": REVIEW_CONTRACT,
        "mode": mode,
        "user_id": int(user.pk),
        "event_type": event_type,
        "generated_at": _iso(timezone.now()),
        "state": state,
        "recurring": recurring,
    }
    token = signing.dumps(payload, compress=True, salt=REVIEW_SIGNING_SALT)
    return CreationReview(
        signed_payload=token,
        profile=profile,
        default_teams=default_teams,
        inactive_requirement_count=inactive_count,
        candidate_dates=tuple(
            timezone.datetime.fromisoformat(value).date()
            for value in (recurring or {}).get("candidate_dates", [])
        ),
        dates_to_create=tuple(
            timezone.datetime.fromisoformat(value).date()
            for value in (recurring or {}).get("create_dates", [])
        ),
        dates_to_skip=tuple(
            timezone.datetime.fromisoformat(value).date()
            for value in (recurring or {}).get("skip_dates", [])
        ),
    )


def _decode_review(token, *, user, mode):
    if not token:
        raise ServiceEventCreationError(CreationReviewFailure.REVIEW_REQUIRED)
    try:
        payload = signing.loads(
            token,
            salt=REVIEW_SIGNING_SALT,
            max_age=REVIEW_MAX_AGE_SECONDS,
        )
    except signing.BadSignature as exc:
        raise ServiceEventCreationError(CreationReviewFailure.INVALID_REVIEW) from exc
    if not isinstance(payload, dict) or set(payload) != {
        "contract",
        "mode",
        "user_id",
        "event_type",
        "generated_at",
        "state",
        "recurring",
    }:
        raise ServiceEventCreationError(CreationReviewFailure.INVALID_REVIEW)
    state = payload.get("state")
    recurring = payload.get("recurring")
    if (
        payload["contract"] != REVIEW_CONTRACT
        or payload["mode"] != mode
        or type(payload["user_id"]) is not int
        or payload["user_id"] != int(user.pk)
        or not isinstance(payload["event_type"], str)
        or not isinstance(payload["generated_at"], str)
        or not isinstance(state, dict)
        or set(state)
        != {
            "profile",
            "profile_fingerprint",
            "default_team_ids",
            "team_fingerprint",
            "audience_ids",
            "audience_fingerprint",
        }
        or not isinstance(state["default_team_ids"], list)
        or any(type(value) is not int for value in state["default_team_ids"])
        or not isinstance(state["audience_ids"], list)
        or any(type(value) is not int for value in state["audience_ids"])
        or not all(
            isinstance(state[key], str) and len(state[key]) == 64
            for key in (
                "profile_fingerprint",
                "team_fingerprint",
                "audience_fingerprint",
            )
        )
    ):
        raise ServiceEventCreationError(CreationReviewFailure.INVALID_REVIEW)
    profile = state["profile"]
    if profile is not None and (
        not isinstance(profile, dict)
        or set(profile)
        != {"id", "key", "event_type", "is_active", "updated_at"}
        or type(profile["id"]) is not int
        or not isinstance(profile["key"], str)
        or not isinstance(profile["event_type"], str)
        or type(profile["is_active"]) is not bool
        or not isinstance(profile["updated_at"], str)
    ):
        raise ServiceEventCreationError(CreationReviewFailure.INVALID_REVIEW)
    if mode == "single":
        if recurring is not None:
            raise ServiceEventCreationError(CreationReviewFailure.INVALID_REVIEW)
    elif (
        not isinstance(recurring, dict)
        or set(recurring)
        != {
            "inputs",
            "candidate_dates",
            "create_dates",
            "skip_dates",
            "duplicate_fingerprint",
        }
        or not isinstance(recurring["inputs"], dict)
        or set(recurring["inputs"])
        != {
            "title",
            "title_en",
            "description",
            "description_en",
            "event_type",
            "start_date",
            "end_date",
            "weekday",
            "start_time",
            "end_time",
            "location",
            "meeting_link",
            "status",
        }
        or any(
            not isinstance(recurring["inputs"][key], str)
            for key in (
                "title",
                "title_en",
                "description",
                "description_en",
                "event_type",
                "start_date",
                "end_date",
                "start_time",
                "location",
                "meeting_link",
                "status",
            )
        )
        or type(recurring["inputs"]["weekday"]) is not int
        or (
            recurring["inputs"]["end_time"] is not None
            and not isinstance(recurring["inputs"]["end_time"], str)
        )
        or any(
            not isinstance(recurring[key], list)
            or any(not isinstance(value, str) for value in recurring[key])
            for key in ("candidate_dates", "create_dates", "skip_dates")
        )
        or not isinstance(recurring["duplicate_fingerprint"], str)
        or len(recurring["duplicate_fingerprint"]) != 64
    ):
        raise ServiceEventCreationError(CreationReviewFailure.INVALID_REVIEW)
    return payload


def _validate_snapshot(
    payload, *, profile_id, event_type, audience_ids, recurring_data=None, using="default"
):
    if payload["event_type"] != event_type:
        raise ServiceEventCreationError(CreationReviewFailure.INVALID_REVIEW)
    current, profile, defaults, inactive_count = _review_state(
        profile_id,
        event_type,
        audience_ids,
        using=using,
    )
    reviewed = payload["state"]
    if reviewed.get("profile") != current["profile"]:
        raise ServiceEventCreationError(
            CreationReviewFailure.PROFILE_DEFAULTS_CHANGED
        )
    if reviewed.get("profile_fingerprint") != current["profile_fingerprint"]:
        raise ServiceEventCreationError(
            CreationReviewFailure.PROFILE_DEFAULTS_CHANGED
        )
    if reviewed.get("default_team_ids") != current["default_team_ids"]:
        raise ServiceEventCreationError(
            CreationReviewFailure.PROFILE_DEFAULTS_CHANGED
        )
    if reviewed.get("team_fingerprint") != current["team_fingerprint"]:
        raise ServiceEventCreationError(
            CreationReviewFailure.TEAM_CONFIGURATION_CHANGED
        )
    if (
        reviewed.get("audience_ids") != current["audience_ids"]
        or reviewed.get("audience_fingerprint") != current["audience_fingerprint"]
    ):
        raise ServiceEventCreationError(CreationReviewFailure.AUDIENCE_CHANGED)
    if recurring_data is not None:
        current_recurring = _recurring_classification(
            recurring_data,
            using=using,
        )
        if payload.get("recurring") != current_recurring:
            raise ServiceEventCreationError(
                CreationReviewFailure.RECURRING_SET_CHANGED
            )
    return current, profile, defaults, inactive_count


def _require_same_review_state(reviewed, current):
    if (
        reviewed["profile"] != current["profile"]
        or reviewed["profile_fingerprint"] != current["profile_fingerprint"]
        or reviewed["default_team_ids"] != current["default_team_ids"]
    ):
        raise ServiceEventCreationError(
            CreationReviewFailure.PROFILE_DEFAULTS_CHANGED
        )
    if reviewed["team_fingerprint"] != current["team_fingerprint"]:
        raise ServiceEventCreationError(
            CreationReviewFailure.TEAM_CONFIGURATION_CHANGED
        )
    if (
        reviewed["audience_ids"] != current["audience_ids"]
        or reviewed["audience_fingerprint"] != current["audience_fingerprint"]
    ):
        raise ServiceEventCreationError(CreationReviewFailure.AUDIENCE_CHANGED)


def _validated_team_ids(team_ids, *, using="default"):
    normalized = tuple(sorted({int(value) for value in team_ids}))
    valid = set(
        MinistryTeam.objects.using(using)
        .filter(pk__in=normalized, is_active=True, is_assignable=True)
        .values_list("pk", flat=True)
    )
    if valid != set(normalized):
        raise ServiceEventCreationError(
            CreationReviewFailure.TEAM_CONFIGURATION_CHANGED
        )
    return normalized


def _event_kwargs(cleaned_data, user, event_date=None):
    if event_date is None:
        return {
            key: cleaned_data[key]
            for key in (
                "title",
                "title_en",
                "description",
                "description_en",
                "event_type",
                "start_datetime",
                "end_datetime",
                "location",
                "meeting_link",
                "status",
            )
        } | {"created_by": user, "scheduling_revision": 0}
    end_datetime = None
    if cleaned_data.get("end_time"):
        end_datetime = timezone.make_aware(
            timezone.datetime.combine(event_date, cleaned_data["end_time"]),
            timezone.get_current_timezone(),
        )
    return {
        "title": cleaned_data["title"],
        "title_en": cleaned_data.get("title_en") or "",
        "description": cleaned_data.get("description") or "",
        "description_en": cleaned_data.get("description_en") or "",
        "event_type": cleaned_data["event_type"],
        "start_datetime": _start_datetime(event_date, cleaned_data),
        "end_datetime": end_datetime,
        "location": cleaned_data.get("location") or "",
        "meeting_link": cleaned_data.get("meeting_link") or "",
        "status": cleaned_data["status"],
        "created_by": user,
        "scheduling_revision": 0,
    }


def _insert_event(event_kwargs, profile):
    event = ServiceEvent(**event_kwargs)
    if profile is not None:
        prepare_service_event_profile(
            event,
            profile,
            target_event_type=event.event_type,
        )
    else:
        event.service_profile = None
        event.service_profile_key = ""
    event.save(force_insert=True)
    return event


def _create_children(event, team_ids, audience_ids):
    for team_id in team_ids:
        ServiceEventRequiredTeam.objects.create(
            service_event_id=event.pk,
            ministry_team_id=team_id,
        )
    for unit_id in audience_ids:
        ServiceEventAudienceScope.objects.create(
            service_event_id=event.pk,
            unit_id=unit_id,
        )


def _verify_event(event, profile, team_ids, audience_ids):
    event.refresh_from_db()
    expected_profile_id = profile.pk if profile is not None else None
    expected_key = profile.key if profile is not None else ""
    if (
        event.scheduling_revision != 0
        or event.service_profile_id != expected_profile_id
        or event.service_profile_key != expected_key
        or set(event.required_team_links.values_list("ministry_team_id", flat=True))
        != set(team_ids)
        or set(event.audience_scope_links.values_list("unit_id", flat=True))
        != set(audience_ids)
    ):
        raise ServiceEventCreationError(CreationReviewFailure.POSTCONDITION)


def create_single_service_event(
    *, cleaned_data, user, profile_id, review_token, team_ids, audience_ids
):
    event_type = cleaned_data["event_type"]
    team_ids = _validated_team_ids(team_ids)
    if profile_id:
        payload = _decode_review(review_token, user=user, mode="single")
        baseline, profile, _, _ = _validate_snapshot(
            payload,
            profile_id=profile_id,
            event_type=event_type,
            audience_ids=audience_ids,
        )
    else:
        baseline, profile, _, _ = _review_state(None, event_type, audience_ids)
    audience_ids = tuple(baseline["audience_ids"])

    try:
        with transaction.atomic():
            event = _insert_event(_event_kwargs(cleaned_data, user), profile)
            current, current_profile, _, _ = _review_state(
                profile_id,
                event_type,
                audience_ids,
            )
            _require_same_review_state(baseline, current)
            current_team_ids = _validated_team_ids(team_ids)
            _create_children(event, current_team_ids, audience_ids)
            _verify_event(event, current_profile, current_team_ids, audience_ids)
    except OperationalError as exc:
        raise ServiceEventCreationError(CreationReviewFailure.BUSY) from exc
    except IntegrityError as exc:
        raise ServiceEventCreationError(CreationReviewFailure.POSTCONDITION) from exc
    return CreationResult((event,), (), ())


def create_recurring_service_events(
    *, cleaned_data, user, profile_id, review_token, team_ids, audience_ids
):
    event_type = cleaned_data["event_type"]
    team_ids = _validated_team_ids(team_ids)
    if review_token:
        payload = _decode_review(review_token, user=user, mode="recurring")
        baseline, profile, _, _ = _validate_snapshot(
            payload,
            profile_id=profile_id,
            event_type=event_type,
            audience_ids=audience_ids,
            recurring_data=cleaned_data,
        )
        reviewed_recurring = payload["recurring"]
    elif profile_id:
        raise ServiceEventCreationError(CreationReviewFailure.REVIEW_REQUIRED)
    else:
        baseline, profile, _, _ = _review_state(None, event_type, audience_ids)
        reviewed_recurring = _recurring_classification(cleaned_data)

    audience_ids = tuple(baseline["audience_ids"])
    create_dates = tuple(
        timezone.datetime.fromisoformat(value).date()
        for value in reviewed_recurring["create_dates"]
    )
    skip_dates = tuple(
        timezone.datetime.fromisoformat(value).date()
        for value in reviewed_recurring["skip_dates"]
    )
    if not create_dates:
        return CreationResult((), create_dates, skip_dates)

    events = []
    try:
        with transaction.atomic():
            first = _insert_event(
                _event_kwargs(cleaned_data, user, create_dates[0]),
                profile,
            )
            events.append(first)
            current, current_profile, _, _ = _review_state(
                profile_id,
                event_type,
                audience_ids,
            )
            _require_same_review_state(baseline, current)
            post_insert = _recurring_classification(
                cleaned_data,
                ignore_event_id=first.pk,
            )
            if post_insert != reviewed_recurring:
                raise ServiceEventCreationError(
                    CreationReviewFailure.RECURRING_SET_CHANGED
                )
            current_team_ids = _validated_team_ids(team_ids)
            for event_date in create_dates[1:]:
                events.append(
                    _insert_event(
                        _event_kwargs(cleaned_data, user, event_date),
                        current_profile,
                    )
                )
            for event in events:
                _create_children(event, current_team_ids, audience_ids)
                _verify_event(event, current_profile, current_team_ids, audience_ids)
            final = _recurring_classification(
                cleaned_data,
                ignore_event_id=first.pk,
            )
            created_other_ids = [event.pk for event in events[1:]]
            if created_other_ids:
                # Exclude every transaction-local event before comparing the
                # final external duplicate truth with the reviewed snapshot.
                final = _recurring_classification_excluding(
                    cleaned_data,
                    created_event_ids=[event.pk for event in events],
                )
            if final != reviewed_recurring:
                raise ServiceEventCreationError(
                    CreationReviewFailure.RECURRING_SET_CHANGED
                )
    except OperationalError as exc:
        raise ServiceEventCreationError(CreationReviewFailure.BUSY) from exc
    except IntegrityError as exc:
        raise ServiceEventCreationError(CreationReviewFailure.POSTCONDITION) from exc
    return CreationResult(tuple(events), create_dates, skip_dates)


def _recurring_classification_excluding(cleaned_data, *, created_event_ids):
    candidates = _candidate_dates(cleaned_data)
    create_dates = []
    skip_dates = []
    evidence = []
    for event_date in candidates:
        rows = list(
            ServiceEvent.objects.filter(
                start_datetime=_start_datetime(event_date, cleaned_data),
                event_type=cleaned_data["event_type"],
                title=cleaned_data["title"],
            )
            .exclude(status=ServiceEvent.STATUS_CANCELLED)
            .exclude(pk__in=created_event_ids)
            .order_by("pk")
            .values("id", "status", "updated_at")
        )
        serialized = [
            {
                "id": row["id"],
                "status": row["status"],
                "updated_at": _iso(row["updated_at"]),
            }
            for row in rows
        ]
        evidence.append({"date": _iso(event_date), "matches": serialized})
        (skip_dates if rows else create_dates).append(event_date)
    return {
        "inputs": _recurring_inputs(cleaned_data),
        "candidate_dates": [_iso(value) for value in candidates],
        "create_dates": [_iso(value) for value in create_dates],
        "skip_dates": [_iso(value) for value in skip_dates],
        "duplicate_fingerprint": _fingerprint(evidence),
    }
