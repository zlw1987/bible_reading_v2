"""Read-only Ministry Team stable-identity inventory.

The command prepares human review for a later, separately approved key-data
configuration slice. It never infers, creates, repairs, or requires keys.
"""

import json
from collections import defaultdict

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand

from ministry.models import (
    MinistryTeam,
    validate_ministry_team_key,
)


UNCONFIGURED = "UNCONFIGURED"
UNRESOLVED_MULTIPLE_PRIMARY_LINKS = "UNRESOLVED_MULTIPLE_PRIMARY_LINKS"
UNRESOLVED_PRIMARY_PATH_CYCLE = "UNRESOLVED_PRIMARY_PATH_CYCLE"


def _display(value):
    return json.dumps(value or "", ensure_ascii=False)


def _safe_primary_path(team):
    """Resolve the canonical primary path, or an explicit fail-closed marker."""
    ministry_names = [team.get_name("zh")]
    seen = {team.pk}
    current = team
    while True:
        links = list(
            current.parent_links.filter(is_active=True, is_primary=True)
            .select_related("parent_team", "parent_church_unit")
            .order_by("sort_order", "id")[:2]
        )
        if len(links) > 1:
            return UNRESOLVED_MULTIPLE_PRIMARY_LINKS
        if not links:
            return " > ".join(reversed(ministry_names))

        link = links[0]
        if link.parent_church_unit_id is not None:
            return " > ".join(
                [link.parent_church_unit.path_label("zh")]
                + list(reversed(ministry_names))
            )

        parent = link.parent_team
        if parent is None or parent.pk in seen:
            return UNRESOLVED_PRIMARY_PATH_CYCLE
        seen.add(parent.pk)
        ministry_names.append(parent.get_name("zh"))
        current = parent


def build_identity_inventory():
    """Return deterministic, privacy-bounded identity evidence for all teams."""
    teams = list(MinistryTeam.objects.all().order_by("id"))
    rows = []
    canonical_key_owners = defaultdict(list)

    for team in teams:
        raw_key = team.team_key
        integrity_problems = []
        if raw_key is not None:
            try:
                canonical_key = validate_ministry_team_key(raw_key)
            except ValidationError:
                canonical_key = None
                integrity_problems.append("MALFORMED_TEAM_KEY")
            else:
                if canonical_key != raw_key:
                    integrity_problems.append("NONCANONICAL_TEAM_KEY")
                if canonical_key is not None:
                    canonical_key_owners[canonical_key].append(team.id)

        rows.append(
            {
                "pk": team.pk,
                "team_key": raw_key,
                "name": team.name,
                "name_en": team.name_en,
                "is_active": team.is_active,
                "is_assignable": team.is_assignable,
                "is_worship_rotation_pool": team.is_worship_rotation_pool,
                "primary_path": _safe_primary_path(team),
                "integrity_problems": integrity_problems,
            }
        )

    duplicate_ids = {
        team_id
        for owner_ids in canonical_key_owners.values()
        if len(owner_ids) > 1
        for team_id in owner_ids
    }
    for row in rows:
        if row["pk"] in duplicate_ids:
            row["integrity_problems"].append("DUPLICATE_CANONICAL_TEAM_KEY")

    configured = sum(row["team_key"] is not None for row in rows)
    return {
        "rows": rows,
        "summary": {
            "total_teams": len(rows),
            "active_teams": sum(row["is_active"] for row in rows),
            "configured_team_keys": configured,
            "unconfigured_team_keys": len(rows) - configured,
            "integrity_problem_teams": sum(
                bool(row["integrity_problems"]) for row in rows
            ),
        },
    }


class Command(BaseCommand):
    help = (
        "Read-only inventory of MinistryTeam stable technical identity. Writes "
        "nothing, has no --apply mode, and does not treat unconfigured teams as "
        "trial-readiness blockers."
    )

    def handle(self, *args, **options):
        inventory = build_identity_inventory()
        write = self.stdout.write
        write("Ministry Team identity inventory (GENERIC-DEPLOYMENT-CONFIG.1A)")
        write("=" * 72)
        write("mode: read-only (no --apply exists; no data was changed)")
        write("ordering: database primary key ascending")
        write("")
        write("teams:")
        for row in inventory["rows"]:
            key = UNCONFIGURED if row["team_key"] is None else _display(row["team_key"])
            problems = ",".join(row["integrity_problems"]) or "none"
            write(
                f"  pk={row['pk']} | team_key={key} | name={_display(row['name'])} "
                f"| name_en={_display(row['name_en'])} | active={str(row['is_active']).lower()} "
                f"| assignable={str(row['is_assignable']).lower()} "
                f"| worship_rotation_pool={str(row['is_worship_rotation_pool']).lower()} "
                f"| primary_path={_display(row['primary_path'])} "
                f"| integrity={problems}"
            )

        summary = inventory["summary"]
        write("")
        write("summary:")
        for key in (
            "total_teams",
            "active_teams",
            "configured_team_keys",
            "unconfigured_team_keys",
            "integrity_problem_teams",
        ):
            write(f"  {key}: {summary[key]}")
        write(
            "  unconfigured_policy: informational only; a missing team_key is "
            "not a trial-readiness blocker"
        )
        write(
            "READ-ONLY: no key was generated, inferred, created, updated, or "
            "deleted. Names, paths, taxonomy, assignability, Worship metadata, "
            "roles, membership, and serving were not treated as identity."
        )
