"""Read-only ministry role source-of-truth alignment audit (MINISTRY-ROLE-SOURCE.1A).

Thin wrapper over ``ministry.role_source_alignment.run_alignment_audit``. It
prints a membership / role-assignment inventory and reports **drift** between:

* the transitional legacy ``TeamMembership.role`` (``lead`` / ``coordinator``),
  which still drives current runtime team-management permission;
* the deprecated/reserved ``TeamMembership.can_lead`` flag, which grants no
  permission and is audited as a warning; and
* the newer ``MinistryTeamRoleAssignment`` long-term ministry role (the intended
  future single source of truth),

classified as blockers / warnings / info.

This command is **read-only**: it has no ``--apply``, writes nothing, repairs no
rows, assigns no roles, backfills nothing, switches no source of truth, and
changes no permission. Current runtime team-management permission still reads
``TeamMembership.role`` in {``lead``, ``coordinator``} until a later, separately
approved migration slice. See ``docs/MINISTRY_ROLE_SOURCE_OF_TRUTH_PLAN.md``.
"""

from django.core.management.base import BaseCommand, CommandError

from ministry.role_source_alignment import (
    BLOCKER_KEYS,
    INFO_KEYS,
    VERBOSE_DETAIL_KEYS,
    WARNING_KEYS,
    run_alignment_audit,
)


class Command(BaseCommand):
    help = (
        "Read-only MINISTRY-ROLE-SOURCE.1A audit: inventory of TeamMembership "
        "roles and MinistryTeamRoleAssignment rows plus drift between the "
        "legacy membership role/can_lead fields and the long-term ministry "
        "role model, classified as blockers / warnings / info. Writes nothing, "
        "has no apply mode, and changes no permission."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--verbose",
            action="store_true",
            help="Print capped example rows for blocker / warning categories.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=20,
            help=(
                "Cap the number of verbose example rows printed per category "
                "(default 20)."
            ),
        )
        parser.add_argument(
            "--fail-on-blockers",
            action="store_true",
            help="Exit non-zero when any blocker count > 0. Still read-only.",
        )

    def handle(self, *args, **options):
        if options["limit"] < 0:
            raise CommandError("--limit must be zero or greater.")

        audit = run_alignment_audit()
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
                "Ministry role source alignment blockers detected "
                "(--fail-on-blockers): " + ", ".join(blocking)
            )

    def _print_report(self, audit, *, verbose, limit):
        write = self.stdout.write
        stats = audit["stats"]

        write(
            "Ministry role source-of-truth alignment audit "
            "(MINISTRY-ROLE-SOURCE.1A, read-only)"
        )
        write("=" * 76)
        write("mode: read-only (no --apply exists; no data was changed)")
        write(
            "this audit does NOT change permissions and does NOT switch the "
            "source of truth."
        )
        write(
            "current runtime still uses TeamMembership.role (role in {lead, "
            "coordinator}) for can_manage_ministry_team until a future "
            "migration slice; TeamMembership.can_lead is deprecated/reserved and "
            "grants no permission (audited as a warning)."
        )
        write("")

        write("inventory (info):")
        for key in INFO_KEYS:
            write(f"  {key}: {stats[key]}")
        write(
            "  note: container_management_role_assignment_without_membership is "
            "ALLOWED info, not a warning — for non-assignable "
            "(is_assignable=False) container teams a MinistryTeamRoleAssignment "
            "may name a long-term leader without a candidate-pool TeamMembership. "
            "The membership expectation applies to assignable "
            "(is_assignable=True) teams, which may be ServiceEvent required-team "
            "/ TeamAssignment targets for any event type."
        )
        write("  active_role_assignments_by_code:")
        by_code = audit["active_role_assignments_by_code"]
        if by_code:
            for code, count in by_code.items():
                write(f"    {code}: {count}")
        else:
            write("    (none)")
        write("")

        write(
            "blockers (high-confidence corruption; --fail-on-blockers exits "
            "non-zero):"
        )
        for key in BLOCKER_KEYS:
            write(f"  {key}: {stats[key]}")
        write(
            "  => blockers present: "
            + (", ".join(audit["blockers"]) if audit["blockers"] else "none")
        )
        write("")

        write("warnings (transitional drift / setup gaps to review; not fatal):")
        for key in WARNING_KEYS:
            write(f"  {key}: {stats[key]}")
        write("")

        write("source-of-truth boundary confirmation (static, read-only):")
        for note in audit["permission_notes"]:
            write(f"  - {note}")
        write("")

        write(
            "READ-ONLY: no TeamMembership, MinistryTeamRoleAssignment, "
            "MinistryTeamRoleType, MinistryTeam, TeamAssignment, or "
            "TeamAssignmentMember row was created, updated, or deleted. No "
            "permission, source-of-truth, My Serving, or Today behavior was "
            "changed, and no role was backfilled."
        )

        self._print_summary(audit)

        if verbose:
            self._print_verbose(audit, limit=limit)

    def _print_summary(self, audit):
        write = self.stdout.write
        write("")
        write(f"blockers: {audit['blocker_count']}")
        write(f"warnings: {audit['warning_count']}")
        write(self._recommendation(audit))

    def _recommendation(self, audit):
        stats = audit["stats"]
        if audit["blocker_count"] > 0:
            return (
                "recommendation: resolve the duplicate active role assignment "
                "rows before any MINISTRY-ROLE-SOURCE.1B backfill or 1C "
                "permission switch; automated migration is unsafe while they "
                "exist."
            )
        if audit["warning_count"] == 0:
            return (
                "recommendation: legacy membership roles and ministry role "
                "assignments are aligned; the 1B backfill / 1C permission "
                "switch can proceed when separately approved."
            )

        hints = []
        if stats["legacy_management_membership_without_role_assignment"]:
            hints.append(
                "create matching MinistryTeamRoleAssignment rows for legacy "
                "lead/coordinator memberships (1B backfill, when approved)"
            )
        if stats["legacy_management_membership_display_name_only"]:
            hints.append(
                "link a user (or retire the legacy role) on display-name-only "
                "lead/coordinator memberships; they cannot become role "
                "assignments"
            )
        if stats["management_role_assignment_without_membership"]:
            hints.append(
                "confirm whether role-assigned managers also need an active "
                "TeamMembership candidate-pool row"
            )
        if stats["teams_management_role_user_disagreement"]:
            hints.append(
                "reconcile teams where the two systems name different managers"
            )
        if stats["coordinator_membership_without_coordinator_role_type"]:
            hints.append(
                "seed/configure the coordinator ministry role type "
                "(seed_ministry_structure_roles) before backfilling coordinators"
            )
        if stats["active_team_memberships_can_lead_true"]:
            hints.append(
                "review can_lead=True memberships; can_lead is transitional and "
                "is not the long-term role source"
            )
        return (
            "recommendation: transitional drift only (no blockers). Before the "
            "1B backfill / 1C permission switch, "
            + "; ".join(hints)
            + "."
        )

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
