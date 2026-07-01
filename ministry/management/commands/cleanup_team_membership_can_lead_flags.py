"""Deprecated ``TeamMembership.can_lead`` cleanup command (MINISTRY-ROLE-SOURCE.1E-A).

Thin wrapper over ``ministry.can_lead_cleanup.run_cleanup``. It clears the
deprecated/reserved ``TeamMembership.can_lead=True`` flag, which after the
MINISTRY-ROLE-SOURCE.1C read switch grants no permission (runtime team-management
authority reads active lead/coordinator ``MinistryTeamRoleAssignment`` rows for
the exact team).

Dry-run by default: nothing is written unless ``--apply`` is passed. Even under
``--apply`` this command only sets ``can_lead`` True -> False. It never mutates
``TeamMembership.role``, never creates / deletes / (de)activates a
``TeamMembership`` or ``MinistryTeamRoleAssignment`` row, infers no role from
``can_lead``, and changes no permission.

Both active and inactive memberships are in scope by default so the deprecated
flag is cleared completely; ``--team-id`` narrows the scope to one team.

See ``docs/MINISTRY_ROLE_SOURCE_OF_TRUTH_PLAN.md``.
"""

from django.core.management.base import BaseCommand, CommandError

from ministry.can_lead_cleanup import (
    COUNTER_KEYS,
    PERMISSION_NOTES,
    run_cleanup,
)


class Command(BaseCommand):
    help = (
        "MINISTRY-ROLE-SOURCE.1E-A cleanup: clear deprecated "
        "TeamMembership.can_lead=True flags. Dry-run by default; writes only "
        "with --apply. Only sets can_lead True -> False; TeamMembership.role is "
        "untouched, no membership or MinistryTeamRoleAssignment row is "
        "created/deleted/deactivated, no role is inferred from can_lead, and no "
        "permission changes."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help=(
                "Set can_lead=False on matching rows. Without this flag the "
                "command is a read-only dry-run."
            ),
        )
        parser.add_argument(
            "--verbose",
            action="store_true",
            help="Print capped example rows for the cleared / would-clear rows.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=20,
            help=(
                "Cap the number of verbose example rows printed per category "
                "(default 20). Caps verbose output only; does not narrow the "
                "scan/apply scope."
            ),
        )
        parser.add_argument(
            "--team-id",
            type=int,
            default=None,
            help="Restrict the scan/apply to a single MinistryTeam id.",
        )

    def handle(self, *args, **options):
        if options["limit"] < 0:
            raise CommandError("--limit must be zero or greater.")

        result = run_cleanup(
            apply=options["apply"],
            team_id=options["team_id"],
        )
        self._print_report(
            result,
            verbose=options["verbose"],
            limit=options["limit"],
        )

    def _print_report(self, result, *, verbose, limit):
        write = self.stdout.write
        stats = result["stats"]
        apply = result["apply"]

        write(
            "Deprecated TeamMembership.can_lead cleanup "
            "(MINISTRY-ROLE-SOURCE.1E-A)"
        )
        write("=" * 76)
        write(f"mode: {'APPLY' if apply else 'DRY RUN'}")
        write(
            "can_lead grants NO permission after MINISTRY-ROLE-SOURCE.1C; runtime "
            "team-management authority reads active lead/coordinator "
            "MinistryTeamRoleAssignment rows for the exact team."
        )
        write(
            "TeamMembership.role is left untouched; no membership or "
            "MinistryTeamRoleAssignment row is created/deleted/deactivated."
        )
        filters = result["filters"]
        write(f"filters: team_id={filters['team_id']!r}")
        write("")

        write("outcomes:")
        for key in COUNTER_KEYS:
            write(f"  {key}: {stats[key]}")
        write("")

        write("source-of-truth boundary confirmation (static):")
        for note in PERMISSION_NOTES:
            write(f"  - {note}")
        write("")

        write(f"data_mutated: {str(result['data_mutated']).lower()}")
        write(self._recommendation(result))

        if verbose:
            self._print_verbose(result, limit=limit)

    def _recommendation(self, result):
        stats = result["stats"]
        apply = result["apply"]

        if not apply:
            if stats["would_clear"] > 0:
                return (
                    f"recommendation: {stats['would_clear']} deprecated "
                    "can_lead=True flag(s) would be cleared; rerun with --apply "
                    "only after explicit approval. Nothing was changed."
                )
            return (
                "recommendation: no can_lead=True flags in scope; nothing to "
                "clear. Nothing was changed."
            )

        if stats["cleared"] > 0:
            return (
                f"recommendation: cleared {stats['cleared']} deprecated "
                "can_lead=True flag(s); rerun the read-only "
                "audit_ministry_role_source_alignment to confirm "
                "active_team_memberships_can_lead_true is 0."
            )
        return (
            "recommendation: --apply ran but no can_lead=True flags were in "
            "scope (data_mutated false)."
        )

    def _print_verbose(self, result, *, limit):
        write = self.stdout.write
        write("")
        write("verbose examples (capped per category by --limit):")
        details = result["details"]
        for category in ("would_clear", "cleared"):
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
