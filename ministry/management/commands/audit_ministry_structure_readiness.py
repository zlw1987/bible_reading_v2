"""Read-only Ministry Structure readiness audit command (MINISTRY-STRUCTURE.1G).

Thin wrapper over ``ministry.structure_readiness.run_audit``. It prints a
team / parent-link / role-profile / assignment readiness inventory and reports
whether any blocker stands in the way of further ministry-structure setup.

This command is **read-only**: it has no ``--apply``, writes nothing, repairs no
rows, assigns no roles, creates no defaults, and changes no permission. See
``docs/MINISTRY_STRUCTURE_ARCHITECTURE_PLAN.md``.
"""

from django.core.management.base import BaseCommand, CommandError

from ministry.models import MinistryTeam
from ministry.structure_readiness import (
    BLOCKER_KEYS,
    INFO_KEYS,
    INVENTORY_KEYS,
    VERBOSE_DETAIL_KEYS,
    WARNING_KEYS,
    run_audit,
)
from ministry.structure_map import team_kind_label


class Command(BaseCommand):
    help = (
        "Read-only MINISTRY-STRUCTURE.1G audit: inventory of ministry teams, "
        "parent-link readiness, role-profile readiness, and is_assignable "
        "assignment readiness, classified as blockers / warnings / info. Writes "
        "nothing, has no apply mode, and repairs no data."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--verbose",
            action="store_true",
            help="Print capped example rows for blocker / warning / info categories.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=20,
            help="Cap the number of verbose example rows printed per category (default 20).",
        )
        parser.add_argument(
            "--fail-on-blockers",
            action="store_true",
            help="Exit non-zero when any blocker count > 0. Still read-only.",
        )
        parser.add_argument(
            "--team-id",
            type=int,
            default=None,
            help="Restrict the audit to a single ministry team id.",
        )
        parser.add_argument(
            "--include-inactive",
            action="store_true",
            help=(
                "Also scan inactive teams in the active-team readiness checks "
                "(inventory always counts both)."
            ),
        )

    def handle(self, *args, **options):
        if options["limit"] < 0:
            raise CommandError("--limit must be zero or greater.")

        team_id = options["team_id"]
        if team_id is not None and not MinistryTeam.objects.filter(id=team_id).exists():
            raise CommandError(f"No ministry team with id={team_id}.")

        audit = run_audit(
            team_id=team_id,
            include_inactive=options["include_inactive"],
        )
        self._print_report(
            audit,
            verbose=options["verbose"],
            limit=options["limit"],
        )

        if options["fail_on_blockers"] and audit["blocker_count"] > 0:
            blocking = [
                f"{key}={audit['stats'][key]}"
                for key in BLOCKER_KEYS
                if audit["stats"][key]
            ]
            raise CommandError(
                "Ministry Structure readiness blockers detected "
                "(--fail-on-blockers): " + ", ".join(blocking)
            )

    def _print_report(self, audit, *, verbose, limit):
        write = self.stdout.write
        stats = audit["stats"]

        write("Ministry Structure readiness audit (MINISTRY-STRUCTURE.1G, read-only)")
        write("=" * 76)
        write("mode: read-only (no --apply exists; no data was changed)")
        scope = "all teams" if audit["team_id"] is None else f"team_id={audit['team_id']}"
        scan = (
            "active + inactive" if audit["include_inactive"] else "active teams"
        )
        write(f"scope: {scope} | readiness scan: {scan}")
        write(f"target_date: {audit['target_date'].isoformat()}")
        write("")

        write("team inventory:")
        for key in INVENTORY_KEYS:
            write(f"  {key}: {stats[key]}")
        write("  teams_by_kind:")
        for kind, count in audit["teams_by_kind"].items():
            write(f"    {kind} ({team_kind_label(kind, 'en')}): {count}")
        write("")

        write("blockers (nonzero blocks further setup; --fail-on-blockers exits non-zero):")
        for key in BLOCKER_KEYS:
            write(f"  {key}: {stats[key]}")
        write(
            "  => blockers present: "
            + (", ".join(audit["blockers"]) if audit["blockers"] else "none")
        )
        write("")

        write("warnings (setup gaps to review; not fatal):")
        for key in WARNING_KEYS:
            write(f"  {key}: {stats[key]}")
        write("")

        write("info (expected/by-design or low-severity context):")
        for key in INFO_KEYS:
            write(f"  {key}: {stats[key]}")
        write("")

        write("permission boundary confirmation (static, read-only):")
        for note in audit["permission_notes"]:
            write(f"  - {note}")
        write("")

        write(
            "READ-ONLY: no MinistryTeam, MinistryTeamParentLink, role type / "
            "profile / requirement / assignment, TeamMembership, TeamAssignment, "
            "TeamAssignmentMember, ChurchStructureMembership, "
            "ChurchStructureUnitRoleAssignment, or BibleStudyMeetingRole row was "
            "created, updated, or deleted. No permission, My Serving, or Today "
            "behavior was changed."
        )

        self._print_recommendations(audit)

        if verbose:
            self._print_verbose(audit, limit=limit)

    def _print_recommendations(self, audit):
        write = self.stdout.write
        stats = audit["stats"]
        write("")
        write("recommendations:")
        recommended = False
        if stats["active_assignments_on_non_assignable_team"]:
            recommended = True
            write(
                "  - Active assignments target non-assignable units. Cancel/repair "
                "them or mark the unit assignable in /teams/<id>/structure/."
            )
        if stats["teams_multiple_active_primary_links"] or stats["parent_link_cycle_teams"]:
            recommended = True
            write(
                "  - Investigate parent-link integrity (multiple primaries / cycles) "
                "via /teams/<id>/structure/. This audit does not repair links."
            )
        if stats["assignable_teams_no_role_profile"] or stats["teams_missing_required_lead"]:
            recommended = True
            write(
                "  - Assign a role profile and an active Lead in "
                "/teams/<id>/structure/ (run seed_ministry_structure_roles first "
                "if no role types/profiles exist)."
            )
        if stats["assignable_teams_no_active_membership"]:
            recommended = True
            write(
                "  - Assignable teams without active members cannot be scheduled "
                "effectively; add members on the team manage page."
            )
        if not recommended:
            write("  - No blocker or high-severity warning detected.")

    def _print_verbose(self, audit, *, limit):
        write = self.stdout.write
        write("")
        write("verbose examples (capped per category by --limit):")
        details = audit["details"]
        for category in VERBOSE_DETAIL_KEYS:
            rows = details.get(category, [])
            if not rows:
                continue
            write(f"{category}:")
            printed = 0
            for row in rows:
                if printed >= limit:
                    write(f"  (stopped at --limit {limit})")
                    break
                write(f"  {row}")
                printed += 1
