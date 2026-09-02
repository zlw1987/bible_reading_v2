"""Read-only Ministry Team stable-identity inventory.

The command prepares human review for a later, separately approved key-data
configuration slice. It never infers, creates, repairs, or requires keys.
"""

import json

from django.core.management.base import BaseCommand

from ministry.team_identity import build_identity_inventory


UNCONFIGURED = "UNCONFIGURED"
def _display(value):
    return json.dumps(value or "", ensure_ascii=False)


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
