"""Reviewed create-only materialization of Service Profile static defaults.

GENERIC-DEPLOYMENT-CONFIG.7B deliberately keeps configuration and operational
truth separate.  The 7A inspector is the only classifier; this module binds its
complete payload into a distinct actor-bound plan and may create only the
missing pairs that payload reports.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import hmac
import json
import re
from uuid import uuid4

from django.contrib.admin.models import CHANGE, LogEntry
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import IntegrityError, OperationalError, transaction

from events.models import ServiceEvent, ServiceEventRequiredTeam
from events.scheduling_revision import (
    SchedulingRevisionBusyError,
    SchedulingRevisionError,
    claim_scheduling_revisions,
)

from .service_profile_required_team_materialization import (
    MaterializationProfileNotFound,
    inspect_service_profile_required_team_materialization,
    materialization_preview_state_fingerprint,
)


PLAN_VERSION = "SERVICE_PROFILE_REQUIRED_TEAM_MATERIALIZATION_PLAN_V2"
OPERATION_TYPE = "service_profile_required_team_materialization"
_TOKEN_PATTERN = re.compile(r"[0-9a-f]{64}")


class ServiceProfileRequiredTeamMaterializationError(RuntimeError):
    """Base class for deterministic operator-facing 7B failures."""


class MaterializationPlanInputError(ServiceProfileRequiredTeamMaterializationError):
    pass


class MaterializationActorError(ServiceProfileRequiredTeamMaterializationError):
    pass


class MaterializationNotReady(ServiceProfileRequiredTeamMaterializationError):
    pass


class MaterializationStale(ServiceProfileRequiredTeamMaterializationError):
    pass


class MaterializationBusy(ServiceProfileRequiredTeamMaterializationError):
    pass


class MaterializationAuditError(ServiceProfileRequiredTeamMaterializationError):
    pass


def _canonical_json(value):
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _resolve_actor(actor_user_id, *, using):
    if type(actor_user_id) is not int or actor_user_id <= 0:
        raise MaterializationPlanInputError(
            "actor_user_id must be one exact positive Django User primary key."
        )
    actor = (
        get_user_model()._default_manager.using(using).filter(pk=actor_user_id).first()
    )
    if actor is None:
        raise MaterializationActorError(
            f"ACTOR_NOT_FOUND: no Django User has exact pk={actor_user_id}."
        )
    if not actor.is_active:
        raise MaterializationActorError(
            f"ACTOR_INACTIVE: Django User pk={actor_user_id} is inactive."
        )
    if not (actor.is_staff or actor.is_superuser):
        raise MaterializationActorError(
            f"ACTOR_NOT_STAFF: Django User pk={actor_user_id} is not staff or superuser."
        )
    return actor


def _actor_fact(actor):
    return {
        "pk": actor.pk,
        "username": actor.get_username(),
        "is_active": actor.is_active,
        "is_staff": actor.is_staff,
        "is_superuser": actor.is_superuser,
    }


def _changed_event_facts(preview):
    facts = []
    for event in preview["events"]:
        if not event["missing_default_teams"]:
            continue
        facts.append(
            {
                "event_pk": event["event_pk"],
                "lifecycle_status": event["lifecycle_status"],
                "expected_scheduling_revision": event["scheduling_revision"],
                "missing_teams": [
                    {"team_pk": team_pk, "team_key": team_key}
                    for team_pk, team_key in event["missing_default_teams"]
                ],
            }
        )
    facts.sort(key=lambda row: row["event_pk"])
    for fact in facts:
        fact["missing_teams"].sort(key=lambda row: row["team_pk"])
    return facts


def _canonical_plan_payload(plan):
    return {
        "materialization_plan_version": PLAN_VERSION,
        "actor": plan["actor"],
        "profile_key": plan["profile_key"],
        "start_date": plan["start_date"],
        "end_date": plan["end_date"],
        "source_preview": plan["source_preview"],
        "changed_events": plan["changed_events"],
        "readiness": plan["readiness"],
    }


def serialize_materialization_plan(plan):
    """Return the deterministic actor- and complete-7A-state-bound contract."""

    return _canonical_json(_canonical_plan_payload(plan))


def confirmation_token_for_materialization_plan(plan):
    return hashlib.sha256(serialize_materialization_plan(plan).encode("utf-8")).hexdigest()


def build_service_profile_required_team_materialization_plan(
    *, profile_key, start_date, end_date, actor_user_id, using="default"
):
    """Build one exact reviewed 7B plan without changing database state."""

    actor = _resolve_actor(actor_user_id, using=using)
    preview = inspect_service_profile_required_team_materialization(
        profile_key=profile_key,
        start_date=start_date,
        end_date=end_date,
        using=using,
    )
    summary = preview["summary"]
    changed_events = _changed_event_facts(preview)
    if summary["blockers"]:
        readiness = "BLOCKED"
    elif not summary["missing_default_pairs"]:
        readiness = "READY_NO_MATERIALIZATION_NEEDED"
    else:
        readiness = "READY_TO_APPLY"

    plan = {
        "materialization_plan_version": PLAN_VERSION,
        "source_preview_version": preview["version"],
        "source_preview_fingerprint": preview["state_fingerprint"],
        "profile_key": profile_key,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "actor": _actor_fact(actor),
        "source_preview": preview,
        "changed_events": changed_events,
        "changed_event_count": len(changed_events),
        "complete_event_count": summary["selected_events"] - len(changed_events),
        "readiness": readiness,
        "ready": not summary["blockers"],
        "has_changes": bool(summary["missing_default_pairs"]),
    }
    plan["confirmation_token"] = (
        confirmation_token_for_materialization_plan(plan)
        if readiness == "READY_TO_APPLY"
        else None
    )
    return plan


def _without_fingerprint(preview):
    normalized = deepcopy(preview)
    normalized.pop("state_fingerprint", None)
    return normalized


def _expected_post_claim_preview(reviewed_preview, changed_event_ids):
    expected = _without_fingerprint(reviewed_preview)
    changed_event_ids = set(changed_event_ids)
    for event in expected["events"]:
        if event["event_pk"] in changed_event_ids:
            event["scheduling_revision"] += 1
    return expected


def _assert_post_claim_truth(*, reviewed_preview, current_preview, changed_event_ids):
    expected = _expected_post_claim_preview(reviewed_preview, changed_event_ids)
    expected_fingerprint = materialization_preview_state_fingerprint(expected)
    if (
        _without_fingerprint(current_preview) != expected
        or current_preview.get("state_fingerprint") != expected_fingerprint
    ):
        raise MaterializationStale(
            "STALE: profile, configuration, team, RequiredTeam, event, or scope "
            "truth changed across the scheduling writer boundary; all revision "
            "claims were rolled back."
        )


def _create_required_team(*, event_pk, team_pk, using):
    """Create one exact reviewed pair; never synchronize or replace a set."""

    row = ServiceEventRequiredTeam(
        service_event_id=event_pk,
        ministry_team_id=team_pk,
    )
    row.save(using=using, force_insert=True)
    return row


def _rows_by_pk(preview):
    return {
        row["required_team_row_pk"]: (event["event_pk"], row)
        for event in preview["events"]
        for row in event["required_team_rows"]
    }


def _assert_post_write_truth(
    *, reviewed_preview, current_preview, changed_events, created_rows
):
    if current_preview.get(
        "state_fingerprint"
    ) != materialization_preview_state_fingerprint(current_preview):
        raise MaterializationStale(
            "STALE: post-write 7A fingerprint did not match current truth."
        )
    summary = current_preview["summary"]
    if (
        summary["blockers"] != 0
        or summary["missing_default_pairs"] != 0
        or summary["already_default_pairs"] != summary["expected_default_pairs"]
    ):
        raise MaterializationStale(
            "STALE: post-write 7A inspection did not prove the exact scope fully "
            "materialized; all changes were rolled back."
        )

    reviewed_event_ids = [row["event_pk"] for row in reviewed_preview["events"]]
    current_event_ids = [row["event_pk"] for row in current_preview["events"]]
    if current_event_ids != reviewed_event_ids:
        raise MaterializationStale(
            "STALE: selected event membership changed during materialization."
        )
    if (
        current_preview["profile"] != reviewed_preview["profile"]
        or current_preview["scope"] != reviewed_preview["scope"]
        or current_preview["active_defaults"] != reviewed_preview["active_defaults"]
        or current_preview["inactive_requirement_history"]
        != reviewed_preview["inactive_requirement_history"]
        or current_preview["identity_blockers"]
        != reviewed_preview["identity_blockers"]
        or current_preview["invalid_active_requirements"]
        != reviewed_preview["invalid_active_requirements"]
    ):
        raise MaterializationStale(
            "STALE: profile or requirement configuration changed during materialization."
        )

    changed_by_id = {row["event_pk"]: row for row in changed_events}
    reviewed_by_id = {row["event_pk"]: row for row in reviewed_preview["events"]}
    for event in current_preview["events"]:
        expected_revision = reviewed_by_id[event["event_pk"]]["scheduling_revision"]
        if event["event_pk"] in changed_by_id:
            expected_revision += 1
        if event["scheduling_revision"] != expected_revision:
            raise MaterializationStale(
                "STALE: an event revision did not advance exactly as reviewed."
            )

    reviewed_rows = _rows_by_pk(reviewed_preview)
    current_rows = _rows_by_pk(current_preview)
    for row_pk, reviewed_row in reviewed_rows.items():
        if current_rows.get(row_pk) != reviewed_row:
            raise MaterializationStale(
                "STALE: an existing RequiredTeam row changed during materialization."
            )

    created_by_pk = {row.pk: (row.service_event_id, row.ministry_team_id) for row in created_rows}
    if set(current_rows) - set(reviewed_rows) != set(created_by_pk):
        raise MaterializationStale(
            "STALE: the post-write RequiredTeam surface contains an unreviewed row."
        )
    reviewed_pairs = {
        (event["event_pk"], team_pk)
        for event in reviewed_preview["events"]
        for team_pk, _team_key in event["missing_default_teams"]
    }
    if set(created_by_pk.values()) != reviewed_pairs:
        raise MaterializationStale(
            "STALE: created RequiredTeam rows differ from the reviewed missing pairs."
        )
    for row_pk, pair in created_by_pk.items():
        event_pk, row = current_rows[row_pk]
        if (
            (event_pk, row["team_pk"]) != pair
            or row["classifications"] != ["already_default"]
        ):
            raise MaterializationStale(
                "STALE: a created RequiredTeam row failed canonical classification."
            )

    for key in (
        "manual_extra_rows",
        "explicit_worship_rows",
        "invalid_explicit_rows",
        "inactive_default_history_rows",
        "events_with_review_evidence",
    ):
        if summary[key] != reviewed_preview["summary"][key]:
            raise MaterializationStale(
                "STALE: preserved RequiredTeam review evidence changed during apply."
            )


def _audit_message(
    *, operation_id, profile, scope, changed_event, created_rows
):
    created_rows = sorted(created_rows, key=lambda row: row.ministry_team_id)
    payload = {
        "operation_type": OPERATION_TYPE,
        "operation_id": operation_id,
        "plan_version": PLAN_VERSION,
        "profile": {"pk": profile["pk"], "key": profile["key"]},
        "scope": scope,
        "event_pk": changed_event["event_pk"],
        "scheduling_revision_before": changed_event[
            "expected_scheduling_revision"
        ],
        "scheduling_revision_after": changed_event[
            "expected_scheduling_revision"
        ]
        + 1,
        "created_required_team_row_ids": [row.pk for row in created_rows],
        "created_teams": [
            {"pk": item["team_pk"], "team_key": item["team_key"]}
            for item in changed_event["missing_teams"]
        ],
    }
    return _canonical_json(payload)


def apply_service_profile_required_team_materialization(
    *,
    profile_key,
    start_date,
    end_date,
    actor_user_id,
    confirmation_token,
    using="default",
):
    """Apply one exact reviewed create-only plan atomically."""

    if not isinstance(confirmation_token, str) or not _TOKEN_PATTERN.fullmatch(
        confirmation_token
    ):
        raise MaterializationPlanInputError(
            "confirmation_token must be exactly 64 lowercase hex characters."
        )

    try:
        with transaction.atomic(using=using):
            try:
                reviewed = build_service_profile_required_team_materialization_plan(
                    profile_key=profile_key,
                    start_date=start_date,
                    end_date=end_date,
                    actor_user_id=actor_user_id,
                    using=using,
                )
            except MaterializationProfileNotFound as exc:
                raise MaterializationStale(
                    "STALE: the exact Service Profile identity no longer resolves; "
                    "no materialization was committed."
                ) from exc
            current_token = reviewed["confirmation_token"] or ""
            if not hmac.compare_digest(current_token, confirmation_token):
                raise MaterializationStale(
                    "STALE: confirmation token does not match the complete current "
                    "7B plan; no materialization was committed."
                )
            if reviewed["readiness"] == "BLOCKED":
                raise MaterializationNotReady(
                    "BLOCKED: current 7A blockers prevent materialization."
                )
            if reviewed["readiness"] != "READY_TO_APPLY":
                raise MaterializationNotReady(
                    "NO MATERIALIZATION NEEDED: the exact scope has no missing defaults."
                )

            changed_events = reviewed["changed_events"]
            expected_revisions = tuple(
                (row["event_pk"], row["expected_scheduling_revision"])
                for row in changed_events
            )
            claim_results = claim_scheduling_revisions(
                expected_revisions,
                using=using,
            )

            actor = _resolve_actor(actor_user_id, using=using)
            if _actor_fact(actor) != reviewed["actor"]:
                raise MaterializationStale(
                    "STALE: actor identity or staff state changed across the "
                    "scheduling writer boundary; all claims were rolled back."
                )

            post_claim_preview = inspect_service_profile_required_team_materialization(
                profile_key=profile_key,
                start_date=start_date,
                end_date=end_date,
                using=using,
            )
            _assert_post_claim_truth(
                reviewed_preview=reviewed["source_preview"],
                current_preview=post_claim_preview,
                changed_event_ids=[row["event_pk"] for row in changed_events],
            )

            created_rows = []
            for event in changed_events:
                for team in event["missing_teams"]:
                    created_rows.append(
                        _create_required_team(
                            event_pk=event["event_pk"],
                            team_pk=team["team_pk"],
                            using=using,
                        )
                    )

            post_write_preview = inspect_service_profile_required_team_materialization(
                profile_key=profile_key,
                start_date=start_date,
                end_date=end_date,
                using=using,
            )
            _assert_post_write_truth(
                reviewed_preview=reviewed["source_preview"],
                current_preview=post_write_preview,
                changed_events=changed_events,
                created_rows=created_rows,
            )

            actor = _resolve_actor(actor_user_id, using=using)
            if _actor_fact(actor) != reviewed["actor"]:
                raise MaterializationStale(
                    "STALE: actor identity or staff state changed during "
                    "materialization; all changes were rolled back."
                )

            event_objects = ServiceEvent.objects.using(using).in_bulk(
                row["event_pk"] for row in changed_events
            )
            content_type_id = (
                ContentType.objects.db_manager(using).get_for_model(ServiceEvent).pk
            )
            operation_id = str(uuid4())
            rows_by_event = {}
            for row in created_rows:
                rows_by_event.setdefault(row.service_event_id, []).append(row)
            audit_rows_created = 0
            for event in changed_events:
                try:
                    LogEntry.objects.db_manager(using).log_action(
                        user_id=actor.pk,
                        content_type_id=content_type_id,
                        object_id=event["event_pk"],
                        object_repr=str(event_objects[event["event_pk"]]),
                        action_flag=CHANGE,
                        change_message=_audit_message(
                            operation_id=operation_id,
                            profile=reviewed["source_preview"]["profile"],
                            scope=reviewed["source_preview"]["scope"],
                            changed_event=event,
                            created_rows=rows_by_event[event["event_pk"]],
                        ),
                    )
                except Exception as exc:
                    raise MaterializationAuditError(
                        "Materialization audit write failed; all rows and revision "
                        "claims were rolled back."
                    ) from exc
                audit_rows_created += 1

    except SchedulingRevisionBusyError as exc:
        raise MaterializationBusy(
            "BUSY: scheduling writer serialization was unavailable; no "
            "materialization was committed."
        ) from exc
    except SchedulingRevisionError as exc:
        raise MaterializationStale(
            "STALE: a changed event revision was stale or missing; all claims "
            "were rolled back."
        ) from exc
    except OperationalError as exc:
        message = str(exc).lower()
        if "database is locked" in message or "database table is locked" in message:
            raise MaterializationBusy(
                "BUSY: database writer serialization was unavailable; no "
                "materialization was committed."
            ) from exc
        raise
    except (IntegrityError, ValidationError) as exc:
        raise MaterializationStale(
            "STALE: RequiredTeam uniqueness or current validation changed; all "
            "materialization was rolled back."
        ) from exc

    return {
        "operation_id": operation_id,
        "changed_event_ids": tuple(row["event_pk"] for row in changed_events),
        "claimed_revisions": tuple(
            {
                "event_pk": result.event_id,
                "revision_before": next(
                    row["expected_scheduling_revision"]
                    for row in changed_events
                    if row["event_pk"] == result.event_id
                ),
                "revision_after": result.revision,
            }
            for result in claim_results
        ),
        "required_team_rows_created": len(created_rows),
        "created_required_team_row_ids": tuple(row.pk for row in created_rows),
        "audit_rows_created": audit_rows_created,
        "data_mutated": True,
        "event_materialization": True,
    }
