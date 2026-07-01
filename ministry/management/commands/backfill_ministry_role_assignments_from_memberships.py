"""One-way ministry role backfill command (MINISTRY-ROLE-SOURCE.1B).

Thin wrapper over ``ministry.role_source_backfill.run_backfill``. It creates
missing ``MinistryTeamRoleAssignment`` rows from existing active, user-linked
``TeamMembership.role`` values in {``lead``, ``coordinator``}.

Dry-run by default: nothing is written unless ``--apply`` is passed. Even under
``--apply`` this command:

* changes no permission by running (after MINISTRY-ROLE-SOURCE.1C,
  ``can_manage_ministry_team`` reads active ``MinistryTeamRoleAssignment`` rows,
  role_type code in {``lead``, ``coordinator``}, not ``TeamMembership.role``);
* switches no source of truth;
* mutates no ``TeamMembership`` row (``role`` / ``can_lead`` untouched; no
  membership created / deleted / deactivated);
* never backfills from ``can_lead=True`` and infers no other role codes;
* never auto-resolves a team where the two systems name different managers (that
  is reported as a conflict and left for manual decision).

See ``docs/MINISTRY_ROLE_SOURCE_OF_TRUTH_PLAN.md``.
"""

from django.core.management.base import BaseCommand, CommandError

from ministry.models import TeamMembership
from ministry.role_source_backfill import (
    COUNTER_KEYS,
    PERMISSION_NOTES,
    VERBOSE_DETAIL_KEYS,
    run_backfill,
)

VALID_ROLES = (TeamMembership.ROLE_LEAD, TeamMembership.ROLE_COORDINATOR)


class Command(BaseCommand):
    help = (
        "MINISTRY-ROLE-SOURCE.1B backfill: create missing "
        "MinistryTeamRoleAssignment rows from active user-linked "
        "TeamMembership.role in {lead, coordinator}. Dry-run by default; writes "
        "only with --apply. Changes no permission, switches no source of truth, "
        "mutates no TeamMembership, never backfills from can_lead, and never "
        "auto-resolves manager disagreements (reported as conflicts)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help=(
                "Write missing MinistryTeamRoleAssignment rows. Without this "
                "flag the command is a read-only dry-run."
            ),
        )
        parser.add_argument(
            "--verbose",
            action="store_true",
            help="Print capped example rows per outcome category.",
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
            help="Restrict the scan to a single MinistryTeam id.",
        )
        parser.add_argument(
            "--role",
            choices=list(VALID_ROLES),
            default=None,
            help=(
                "Restrict the scan to a single legacy management membership "
                "role (lead or coordinator)."
            ),
        )

    def handle(self, *args, **options):
        if options["limit"] < 0:
            raise CommandError("--limit must be zero or greater.")

        result = run_backfill(
            apply=options["apply"],
            team_id=options["team_id"],
            role=options["role"],
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
            "Ministry role assignment backfill from TeamMembership.role "
            "(MINISTRY-ROLE-SOURCE.1B)"
        )
        write("=" * 76)
        write(f"mode: {'APPLY' if apply else 'DRY RUN'}")
        write("no permission change: this backfill switches no source of truth.")
        write(
            "no TeamMembership mutation: TeamMembership.role / can_lead are never "
            "written; no membership row is created, deleted, or deactivated."
        )
        filters = result["filters"]
        write(
            "filters: "
            f"team_id={filters['team_id']!r} role={filters['role']!r}"
        )
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
        write(f"start_date used for created rows: {result['start_date']}")
        write(self._recommendation(result))

        if verbose:
            self._print_verbose(result, limit=limit)

    def _recommendation(self, result):
        stats = result["stats"]
        apply = result["apply"]
        pending = stats["would_create"] if not apply else 0
        conflicts = stats["conflict_existing_different_user"]

        parts = []
        if not apply:
            if stats["would_create"] > 0:
                parts.append(
                    f"recommendation: {pending} role assignment(s) would be "
                    "created; rerun with --apply only after explicit approval"
                )
            else:
                parts.append(
                    "recommendation: nothing to backfill in dry-run scope"
                )
        else:
            if stats["created"] > 0:
                parts.append(
                    f"recommendation: created {stats['created']} role "
                    "assignment(s); rerun the read-only "
                    "audit_ministry_role_source_alignment to confirm alignment"
                )
            else:
                parts.append(
                    "recommendation: --apply ran but created nothing "
                    "(data_mutated false)"
                )

        if conflicts:
            parts.append(
                f"{conflicts} conflict(s) left for manual decision (same team + "
                "role type already held by a different active user; not "
                "auto-resolved)"
            )
        if stats["skipped_missing_role_type"]:
            parts.append(
                f"{stats['skipped_missing_role_type']} candidate(s) skipped for a "
                "missing/inactive mapped role type (seed via "
                "seed_ministry_structure_roles before backfilling)"
            )
        if stats["skipped_display_name_only"]:
            parts.append(
                f"{stats['skipped_display_name_only']} display-name-only "
                "management membership(s) cannot be mapped (link a user or retire "
                "the legacy role)"
            )
        return "; ".join(parts) + "."

    def _print_verbose(self, result, *, limit):
        write = self.stdout.write
        write("")
        write("verbose examples (capped per category by --limit):")
        details = result["details"]
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
