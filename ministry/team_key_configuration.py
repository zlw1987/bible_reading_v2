"""Reviewed Ministry Team key configuration planning and atomic apply."""

import hashlib
import hmac
import json
from django.core.exceptions import ValidationError
from django.db import IntegrityError, OperationalError, transaction
from django.db.models import F
from django.utils import timezone

from .models import MinistryTeam, validate_ministry_team_key
from .team_identity import build_identity_inventory


PLAN_VERSION = "TEAM_KEY_CONFIG_PLAN_V1"


class TeamKeyConfigurationError(RuntimeError):
    """Base class for deterministic operator-facing configuration failures."""


class TeamKeyMappingError(TeamKeyConfigurationError):
    pass


class TeamKeyConfigurationNotReady(TeamKeyConfigurationError):
    pass


class TeamKeyConfigurationStale(TeamKeyConfigurationError):
    pass


class TeamKeyConfigurationBusy(TeamKeyConfigurationError):
    pass


def parse_mapping_values(values):
    """Parse repeated exact ``PK=KEY`` values into canonical PK order."""

    parsed = {}
    key_owners = {}
    max_length = MinistryTeam._meta.get_field("team_key").max_length
    for raw_mapping in values:
        if "=" not in raw_mapping:
            raise TeamKeyMappingError(
                f"Invalid --mapping {raw_mapping!r}: expected <TEAM_PK>=<TEAM_KEY>."
            )
        raw_pk, raw_key = raw_mapping.split("=", 1)
        if not raw_pk.strip():
            raise TeamKeyMappingError(
                f"Invalid --mapping {raw_mapping!r}: TEAM_PK is empty."
            )
        try:
            team_pk = int(raw_pk.strip())
        except ValueError as exc:
            raise TeamKeyMappingError(
                f"Invalid --mapping {raw_mapping!r}: TEAM_PK must be an integer."
            ) from exc
        if team_pk <= 0:
            raise TeamKeyMappingError(
                f"Invalid --mapping {raw_mapping!r}: TEAM_PK must be greater than zero."
            )
        if team_pk in parsed:
            raise TeamKeyMappingError(
                f"Duplicate TEAM_PK in this invocation: {team_pk}."
            )

        try:
            canonical_key = validate_ministry_team_key(raw_key)
        except ValidationError as exc:
            message = "; ".join(exc.messages)
            raise TeamKeyMappingError(
                f"Invalid proposed key for TEAM_PK {team_pk}: {message}"
            ) from exc
        if canonical_key is None:
            raise TeamKeyMappingError(
                f"Invalid proposed key for TEAM_PK {team_pk}: key is empty after normalization."
            )
        if len(canonical_key) > max_length:
            raise TeamKeyMappingError(
                f"Invalid proposed key for TEAM_PK {team_pk}: key exceeds {max_length} characters."
            )
        if canonical_key in key_owners:
            raise TeamKeyMappingError(
                "Duplicate normalized proposed key in this invocation: "
                f"{canonical_key!r} (TEAM_PK {key_owners[canonical_key]} and {team_pk})."
            )
        parsed[team_pk] = canonical_key
        key_owners[canonical_key] = team_pk

    return tuple(sorted(parsed.items()))


def _canonical_plan_payload(plan_rows):
    return {
        "plan_version": PLAN_VERSION,
        "teams": [
            {
                "pk": row["pk"],
                "current_team_key": row["current_team_key"],
                "proposed_team_key": row["proposed_team_key"],
                "name": row["name"],
                "name_en": row["name_en"],
                "is_active": row["is_active"],
                "is_assignable": row["is_assignable"],
                "is_worship_rotation_pool": row["is_worship_rotation_pool"],
                "primary_path_evidence": row["primary_path_evidence"],
            }
            for row in plan_rows
        ],
    }


def serialize_canonical_plan(plan_rows):
    """Serialize the versioned reviewed plan deterministically as UTF-8 JSON."""

    return json.dumps(
        _canonical_plan_payload(plan_rows),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def confirmation_token_for(plan_rows):
    return hashlib.sha256(serialize_canonical_plan(plan_rows).encode("utf-8")).hexdigest()


def build_team_key_configuration_plan(mappings, *, using="default"):
    """Build current deterministic review evidence and fail-closed readiness."""

    mappings = tuple(sorted(mappings))
    inventory = build_identity_inventory(using=using)
    inventory_by_pk = {row["pk"]: row for row in inventory["rows"]}
    blockers = []
    plan_rows = []

    for team_pk, proposed_key in mappings:
        row = inventory_by_pk.get(team_pk)
        if row is None:
            blockers.append(f"TEAM_NOT_FOUND: exact MinistryTeam pk={team_pk} does not exist")
            continue
        if row["team_key"] is not None:
            blockers.append(
                f"TARGET_ALREADY_CONFIGURED: pk={team_pk} currently owns team_key={row['team_key']!r}"
            )
        plan_rows.append(
            {
                "pk": team_pk,
                "current_team_key": row["team_key"],
                "proposed_team_key": proposed_key,
                "name": row["name"],
                "name_en": row["name_en"],
                "is_active": row["is_active"],
                "is_assignable": row["is_assignable"],
                "is_worship_rotation_pool": row["is_worship_rotation_pool"],
                "primary_path": row["primary_path"],
                "primary_path_evidence": row["primary_path_evidence"],
            }
        )

    requested_keys = {key for _, key in mappings}
    for row in inventory["rows"]:
        if row["team_key"] in requested_keys and row["pk"] not in dict(mappings):
            blockers.append(
                "PROPOSED_KEY_ALREADY_OWNED: "
                f"team_key={row['team_key']!r} is already owned by pk={row['pk']}"
            )

    integrity_problems = [
        f"pk={row['pk']}: {problem}"
        for row in inventory["rows"]
        for problem in row["integrity_problems"]
    ]
    ready = not blockers and not integrity_problems
    token = confirmation_token_for(plan_rows) if ready else None
    return {
        "plan_version": PLAN_VERSION,
        "mappings": mappings,
        "rows": plan_rows,
        "blockers": blockers,
        "integrity_problems": integrity_problems,
        "ready": ready,
        "confirmation_token": token,
        "summary": {
            "requested_mappings": len(mappings),
            "exact_teams_resolved": len(plan_rows),
            "currently_unconfigured": sum(
                row["current_team_key"] is None for row in plan_rows
            ),
            "proposed_unique_keys": len({key for _, key in mappings}),
            "blockers": len(blockers),
            "integrity_problems": len(integrity_problems),
        },
    }


def _same_ready_plan(plan, expected_token):
    return (
        plan["ready"]
        and plan["confirmation_token"] is not None
        and hmac.compare_digest(plan["confirmation_token"], expected_token)
    )


def _establish_sqlite_writer_barrier(plan, *, using):
    """Take SQLite's first-write boundary without changing stored values."""

    first = plan["rows"][0]
    updated = (
        MinistryTeam.objects.using(using)
        .filter(
            pk=first["pk"],
            team_key__isnull=True,
            name=first["name"],
            name_en=first["name_en"],
            is_active=first["is_active"],
            is_assignable=first["is_assignable"],
            is_worship_rotation_pool=first["is_worship_rotation_pool"],
        )
        .update(team_key=F("team_key"))
    )
    if updated != 1:
        raise TeamKeyConfigurationStale(
            "STALE: target state changed before the writer boundary; no keys were configured."
        )


def _cas_configure_row(row, *, using, updated_at):
    return (
        MinistryTeam.objects.using(using)
        .filter(
            pk=row["pk"],
            team_key__isnull=True,
            name=row["name"],
            name_en=row["name_en"],
            is_active=row["is_active"],
            is_assignable=row["is_assignable"],
            is_worship_rotation_pool=row["is_worship_rotation_pool"],
        )
        .update(team_key=row["proposed_team_key"], updated_at=updated_at)
    )


def apply_team_key_configuration(mappings, confirmation_token, *, using="default"):
    """Rebuild, stale-check, serialize, and atomically apply exact NULL->key rows."""

    try:
        with transaction.atomic(using=using):
            current = build_team_key_configuration_plan(mappings, using=using)
            if not current["ready"]:
                raise TeamKeyConfigurationNotReady(
                    "NOT READY: current blockers or identity-integrity problems prevent apply."
                )
            if not _same_ready_plan(current, confirmation_token):
                raise TeamKeyConfigurationStale(
                    "STALE: confirmation token does not match the complete current plan; no keys were configured."
                )

            _establish_sqlite_writer_barrier(current, using=using)
            serialized = build_team_key_configuration_plan(mappings, using=using)
            if not _same_ready_plan(serialized, confirmation_token):
                raise TeamKeyConfigurationStale(
                    "STALE: reviewed state changed at the writer boundary; no keys were configured."
                )

            updated_at = timezone.now()
            configured = 0
            for row in serialized["rows"]:
                if _cas_configure_row(row, using=using, updated_at=updated_at) != 1:
                    raise TeamKeyConfigurationStale(
                        f"STALE: NULL-to-key CAS failed for pk={row['pk']}; all key changes were rolled back."
                    )
                configured += 1
    except OperationalError as exc:
        message = str(exc).lower()
        if "database is locked" in message or "database table is locked" in message:
            raise TeamKeyConfigurationBusy(
                "BUSY: database writer boundary was unavailable; no keys were configured."
            ) from exc
        raise
    except IntegrityError as exc:
        raise TeamKeyConfigurationStale(
            "STALE: database uniqueness changed during apply; all key changes were rolled back."
        ) from exc

    return {"mappings_requested": len(mappings), "rows_configured": configured}
