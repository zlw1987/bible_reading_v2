"""Reviewed Service Profile ministry-default planning and atomic apply."""

import hashlib
import hmac
import json

from django.core.exceptions import ValidationError
from django.db import IntegrityError, OperationalError, transaction
from django.utils import timezone

from events.models import ServiceProfile

from .models import (
    MinistryTeam,
    ServiceProfileMinistryRequirement,
    validate_ministry_team_key,
)
from .service_profile_ministry_requirements import (
    active_requirement_validation_reasons,
)
from .services.worship_governance import (
    resolve_worship_rotation_pool_for_team,
)


PLAN_VERSION = "SERVICE_PROFILE_MINISTRY_REQUIREMENT_CONFIG_V1"


class ServiceProfileMinistryRequirementConfigurationError(RuntimeError):
    """Base class for deterministic operator-facing configuration failures."""


class RequirementConfigurationInputError(
    ServiceProfileMinistryRequirementConfigurationError
):
    pass


class RequirementConfigurationNotReady(
    ServiceProfileMinistryRequirementConfigurationError
):
    pass


class RequirementConfigurationStale(
    ServiceProfileMinistryRequirementConfigurationError
):
    pass


class RequirementConfigurationBusy(
    ServiceProfileMinistryRequirementConfigurationError
):
    pass


def _iso(value):
    return value.isoformat(timespec="microseconds")


def parse_team_values(values, *, no_teams=False):
    """Parse exact repeated ``TEAM_PK=TEAM_KEY`` reviewed identities."""

    values = tuple(values or ())
    if no_teams and values:
        raise RequirementConfigurationInputError(
            "--no-teams cannot be combined with --team."
        )
    if not no_teams and not values:
        raise RequirementConfigurationInputError(
            "Supply at least one --team TEAM_PK=TEAM_KEY or explicitly use "
            "--no-teams."
        )

    parsed = {}
    key_owners = {}
    max_length = MinistryTeam._meta.get_field("team_key").max_length
    for raw_value in values:
        if "=" not in raw_value:
            raise RequirementConfigurationInputError(
                f"Invalid --team {raw_value!r}: expected <TEAM_PK>=<TEAM_KEY>."
            )
        raw_pk, supplied_key = raw_value.split("=", 1)
        try:
            team_pk = int(raw_pk)
        except ValueError as exc:
            raise RequirementConfigurationInputError(
                f"Invalid --team {raw_value!r}: TEAM_PK must be an integer."
            ) from exc
        if str(team_pk) != raw_pk or team_pk <= 0:
            raise RequirementConfigurationInputError(
                f"Invalid --team {raw_value!r}: TEAM_PK must be a canonical "
                "positive integer."
            )
        if team_pk in parsed:
            raise RequirementConfigurationInputError(
                f"Duplicate TEAM_PK in this invocation: {team_pk}."
            )
        if not supplied_key:
            raise RequirementConfigurationInputError(
                f"Invalid --team {raw_value!r}: TEAM_KEY is empty."
            )
        try:
            canonical_key = validate_ministry_team_key(supplied_key)
        except ValidationError as exc:
            raise RequirementConfigurationInputError(
                f"Invalid TEAM_KEY for TEAM_PK {team_pk}: "
                + "; ".join(exc.messages)
            ) from exc
        if canonical_key != supplied_key:
            raise RequirementConfigurationInputError(
                f"Invalid TEAM_KEY for TEAM_PK {team_pk}: supply the exact "
                "canonical persisted key without normalization."
            )
        if len(supplied_key) > max_length:
            raise RequirementConfigurationInputError(
                f"Invalid TEAM_KEY for TEAM_PK {team_pk}: key exceeds "
                f"{max_length} characters."
            )
        if supplied_key in key_owners:
            raise RequirementConfigurationInputError(
                "Duplicate TEAM_KEY in this invocation: "
                f"{supplied_key!r} (TEAM_PK {key_owners[supplied_key]} and "
                f"{team_pk})."
            )
        parsed[team_pk] = supplied_key
        key_owners[supplied_key] = team_pk

    return tuple(sorted(parsed.items()))


def _profile_state(profile, requested_key):
    if profile is None:
        return {"requested_key": requested_key, "resolved": False}
    return {
        "requested_key": requested_key,
        "resolved": True,
        "pk": profile.pk,
        "key": profile.key,
        "event_type": profile.event_type,
        "is_active": profile.is_active,
        "updated_at": _iso(profile.updated_at),
    }


def _requirement_state(requirement):
    return {
        "requirement_pk": requirement.pk,
        "service_profile_pk": requirement.service_profile_id,
        "ministry_team_pk": requirement.ministry_team_id,
        "ministry_team_key": requirement.ministry_team.team_key,
        "is_active": requirement.is_active,
        "sort_order": requirement.sort_order,
        "updated_at": _iso(requirement.updated_at),
    }


def _desired_team_state(team, supplied_pk, supplied_key):
    resolution = resolve_worship_rotation_pool_for_team(team)
    return {
        "supplied_pk": supplied_pk,
        "supplied_team_key": supplied_key,
        "resolved_pk": team.pk,
        "resolved_team_key": team.team_key,
        "is_active": team.is_active,
        "is_assignable": team.is_assignable,
        "is_worship_rotation_pool": team.is_worship_rotation_pool,
        "is_canonical_worship_child": resolution.pool is not None,
        "updated_at": _iso(team.updated_at),
    }


def _canonical_plan_payload(plan):
    return {
        "plan_version": PLAN_VERSION,
        "profile": plan["profile"],
        "current_requirements": plan["current_requirements"],
        "desired_teams": plan["desired_teams"],
    }


def serialize_canonical_plan(plan):
    return json.dumps(
        _canonical_plan_payload(plan),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def state_fingerprint_for_plan(plan):
    return hashlib.sha256(serialize_canonical_plan(plan).encode("utf-8")).hexdigest()


def build_requirement_configuration_plan(
    profile_key,
    desired_team_identities,
    *,
    using="default",
):
    """Build exact current-state review evidence for one complete desired set."""

    desired_team_identities = tuple(sorted(desired_team_identities))
    profile = (
        ServiceProfile.objects.using(using)
        .filter(key=profile_key)
        .order_by("pk")
        .first()
    )
    blockers = []
    invalid_targets = []
    stale_conflicts = []

    if profile is None:
        blockers.append(
            f"PROFILE_NOT_FOUND: no ServiceProfile has exact key {profile_key!r}"
        )
        requirements = []
    else:
        if not profile.is_active:
            blockers.append(
                f"PROFILE_INACTIVE: ServiceProfile pk={profile.pk} is inactive"
            )
        requirements = list(
            ServiceProfileMinistryRequirement.objects.using(using)
            .select_related("ministry_team")
            .filter(service_profile_id=profile.pk)
            .order_by("pk")
        )

    current_by_team_id = {
        requirement.ministry_team_id: requirement for requirement in requirements
    }
    desired_teams = []
    desired_team_objects = {}
    actions = []

    for supplied_pk, supplied_key in desired_team_identities:
        team_at_pk = (
            MinistryTeam.objects.using(using)
            .filter(pk=supplied_pk)
            .order_by("pk")
            .first()
        )
        team_at_key = (
            MinistryTeam.objects.using(using)
            .filter(team_key=supplied_key)
            .order_by("pk")
            .first()
        )
        reason = None
        failure_classification = "invalid_target"
        if team_at_pk is None:
            reason = f"TEAM_NOT_FOUND: exact MinistryTeam pk={supplied_pk} does not exist"
        elif team_at_pk.team_key is None:
            reason = (
                f"TEAM_KEY_UNCONFIGURED: MinistryTeam pk={supplied_pk} has NULL team_key"
            )
        elif team_at_pk.team_key != supplied_key:
            reason = (
                "TEAM_PK_KEY_MISMATCH: supplied pk/key do not identify the same "
                f"row (pk={supplied_pk}, team_key={supplied_key!r})"
            )
            failure_classification = "stale_conflicting"
        elif team_at_key is None:
            reason = (
                "TEAM_KEY_NOT_FOUND: no MinistryTeam has exact "
                f"team_key={supplied_key!r}"
            )
        elif team_at_pk.pk != team_at_key.pk or team_at_pk.team_key != supplied_key:
            reason = (
                "TEAM_PK_KEY_MISMATCH: supplied pk/key do not identify the same "
                f"row (pk={supplied_pk}, team_key={supplied_key!r})"
            )
            failure_classification = "stale_conflicting"

        if reason is not None:
            failure = {
                "supplied_pk": supplied_pk,
                "supplied_team_key": supplied_key,
                "classification": failure_classification,
                "reason": reason,
            }
            if failure_classification == "stale_conflicting":
                stale_conflicts.append(failure)
            else:
                invalid_targets.append(failure)
            blockers.append(reason)
            continue

        team = team_at_pk
        team_state = _desired_team_state(team, supplied_pk, supplied_key)
        desired_teams.append(team_state)
        desired_team_objects[team.pk] = team
        if profile is None:
            invalid_targets.append(
                {
                    **team_state,
                    "classification": "invalid_target",
                    "reason": "INVALID_TARGET_PROFILE_UNRESOLVED",
                }
            )
            continue
        validation_reasons = tuple(
            reason.value
            for reason in active_requirement_validation_reasons(profile, team)
        )
        if validation_reasons:
            reason = (
                f"INVALID_ACTIVE_TARGET: MinistryTeam pk={team.pk} fails current "
                f"6A validation: {','.join(validation_reasons)}"
            )
            invalid_targets.append(
                {
                    **team_state,
                    "classification": "invalid_target",
                    "reason": reason,
                }
            )
            blockers.append(reason)
            continue

        existing = current_by_team_id.get(team.pk)
        if existing is None:
            classification = "create_new"
            requirement_pk = None
        elif existing.is_active:
            classification = "already_active"
            requirement_pk = existing.pk
        else:
            classification = "reactivate_existing"
            requirement_pk = existing.pk
        actions.append(
            {
                "classification": classification,
                "requirement_pk": requirement_pk,
                "ministry_team_pk": team.pk,
                "ministry_team_key": team.team_key,
                "sort_order": existing.sort_order if existing is not None else 0,
            }
        )

    desired_ids = {team_pk for team_pk, _team_key in desired_team_identities}
    for requirement in requirements:
        if requirement.ministry_team_id in desired_ids:
            continue
        actions.append(
            {
                "classification": (
                    "deactivate_existing"
                    if requirement.is_active
                    else "inactive_history"
                ),
                "requirement_pk": requirement.pk,
                "ministry_team_pk": requirement.ministry_team_id,
                "ministry_team_key": requirement.ministry_team.team_key,
                "sort_order": requirement.sort_order,
            }
        )

    actions.sort(
        key=lambda row: (
            row["ministry_team_pk"],
            row["requirement_pk"] or 0,
            row["classification"],
        )
    )
    desired_teams.sort(key=lambda row: row["supplied_pk"])
    current_requirements = [_requirement_state(row) for row in requirements]
    counts = {
        classification: sum(
            row["classification"] == classification for row in actions
        )
        for classification in (
            "already_active",
            "create_new",
            "reactivate_existing",
            "deactivate_existing",
            "inactive_history",
        )
    }
    counts["invalid_target"] = len(invalid_targets)
    counts["stale_conflicting"] = len(stale_conflicts)
    has_changes = any(
        counts[key]
        for key in ("create_new", "reactivate_existing", "deactivate_existing")
    )
    plan = {
        "plan_version": PLAN_VERSION,
        "profile_key": profile_key,
        "profile_object": profile,
        "profile": _profile_state(profile, profile_key),
        "desired_team_identities": desired_team_identities,
        "desired_team_objects": desired_team_objects,
        "desired_teams": desired_teams,
        "current_requirements": current_requirements,
        "actions": actions,
        "invalid_targets": invalid_targets,
        "stale_conflicts": stale_conflicts,
        "blockers": blockers,
        "classification_counts": counts,
        "ready": not blockers and not stale_conflicts,
        "has_changes": has_changes,
    }
    plan["state_fingerprint"] = state_fingerprint_for_plan(plan)
    plan["confirmation_token"] = (
        plan["state_fingerprint"] if plan["ready"] and has_changes else None
    )
    return plan


def _cas_requirement_state(requirement_state, *, is_active, using, updated_at):
    return (
        ServiceProfileMinistryRequirement.objects.using(using)
        .filter(
            pk=requirement_state["requirement_pk"],
            service_profile_id=requirement_state["service_profile_pk"],
            ministry_team_id=requirement_state["ministry_team_pk"],
            is_active=not is_active,
            sort_order=requirement_state["sort_order"],
            updated_at=requirement_state["updated_at"],
        )
        .update(is_active=is_active, updated_at=updated_at)
    )


def _create_requirement(profile, team, *, using):
    requirement = ServiceProfileMinistryRequirement(
        service_profile=profile,
        ministry_team=team,
        is_active=True,
        sort_order=0,
    )
    requirement.save(using=using, force_insert=True)
    return requirement


def apply_requirement_configuration(
    profile_key,
    desired_team_identities,
    confirmation_token,
    *,
    using="default",
):
    """Re-resolve, stale-check, and atomically apply reviewed lifecycle changes."""

    try:
        with transaction.atomic(using=using):
            reviewed = build_requirement_configuration_plan(
                profile_key,
                desired_team_identities,
                using=using,
            )
            if not hmac.compare_digest(
                reviewed["state_fingerprint"], confirmation_token
            ):
                raise RequirementConfigurationStale(
                    "STALE: confirmation token does not match complete current "
                    "profile requirement state; no configuration was changed."
                )
            if not reviewed["ready"]:
                raise RequirementConfigurationNotReady(
                    "NOT READY: current profile/team blockers prevent apply."
                )
            if not reviewed["has_changes"]:
                raise RequirementConfigurationNotReady(
                    "NO CHANGES: current active configuration already equals the "
                    "reviewed desired set."
                )

            current_by_pk = {
                row["requirement_pk"]: row
                for row in reviewed["current_requirements"]
            }
            now = timezone.now()
            created = reactivated = deactivated = 0
            for action in reviewed["actions"]:
                classification = action["classification"]
                if classification == "create_new":
                    _create_requirement(
                        reviewed["profile_object"],
                        reviewed["desired_team_objects"][action["ministry_team_pk"]],
                        using=using,
                    )
                    created += 1
                elif classification == "reactivate_existing":
                    if _cas_requirement_state(
                        current_by_pk[action["requirement_pk"]],
                        is_active=True,
                        using=using,
                        updated_at=now,
                    ) != 1:
                        raise RequirementConfigurationStale(
                            "STALE: requirement reactivation CAS failed; all "
                            "configuration changes were rolled back."
                        )
                    reactivated += 1
                elif classification == "deactivate_existing":
                    if _cas_requirement_state(
                        current_by_pk[action["requirement_pk"]],
                        is_active=False,
                        using=using,
                        updated_at=now,
                    ) != 1:
                        raise RequirementConfigurationStale(
                            "STALE: requirement deactivation CAS failed; all "
                            "configuration changes were rolled back."
                        )
                    deactivated += 1

            post_apply = build_requirement_configuration_plan(
                profile_key,
                desired_team_identities,
                using=using,
            )
            if not post_apply["ready"] or post_apply["has_changes"]:
                raise RequirementConfigurationStale(
                    "STALE: post-write current truth does not equal the reviewed "
                    "desired set; all configuration changes were rolled back."
                )
    except OperationalError as exc:
        message = str(exc).lower()
        if "database is locked" in message or "database table is locked" in message:
            raise RequirementConfigurationBusy(
                "BUSY: database writer serialization was unavailable; no "
                "configuration was changed."
            ) from exc
        raise
    except (IntegrityError, ValidationError) as exc:
        raise RequirementConfigurationStale(
            "STALE: requirement uniqueness or active validation changed during "
            "apply; all configuration changes were rolled back."
        ) from exc

    return {
        "created": created,
        "reactivated": reactivated,
        "deactivated": deactivated,
        "rows_mutated": created + reactivated + deactivated,
    }
