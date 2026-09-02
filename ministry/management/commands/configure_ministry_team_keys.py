"""Dry-run-first reviewed Ministry Team stable-key configuration command."""

import json

from django.core.management.base import BaseCommand, CommandError

from ministry.team_key_configuration import (
    PLAN_VERSION,
    TeamKeyConfigurationError,
    apply_team_key_configuration,
    build_team_key_configuration_plan,
    parse_mapping_values,
)


UNCONFIGURED = "UNCONFIGURED"


def _display(value):
    return json.dumps(value or "", ensure_ascii=False)


class Command(BaseCommand):
    help = (
        "Configure exact reviewed MinistryTeam.team_key mappings. Dry-run by "
        "default; apply requires --apply and the exact current confirmation token."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--mapping",
            action="append",
            required=True,
            metavar="TEAM_PK=TEAM_KEY",
            help="Exact deployment-local MinistryTeam PK to reviewed canonical key mapping.",
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Atomically apply only after a matching dry-run confirmation token.",
        )
        parser.add_argument(
            "--confirmation-token",
            default=None,
            help="Exact 64-hex reviewed-state token printed by a ready dry-run.",
        )

    def handle(self, *args, **options):
        if options["apply"] and not options["confirmation_token"]:
            raise CommandError(
                "--apply requires --confirmation-token from the exact ready dry-run."
            )
        try:
            mappings = parse_mapping_values(options["mapping"])
            plan = build_team_key_configuration_plan(mappings)
        except TeamKeyConfigurationError as exc:
            raise CommandError(str(exc)) from exc

        self._print_plan(plan, apply=options["apply"])
        if not options["apply"]:
            if options["confirmation_token"]:
                self.stdout.write(
                    "confirmation-token supplied without --apply: DRY RUN only; no data was changed."
                )
            return

        if not plan["ready"]:
            raise CommandError(
                "NOT READY: resolve every blocker and integrity problem, then run a fresh dry-run."
            )

        try:
            result = apply_team_key_configuration(
                mappings,
                options["confirmation_token"],
            )
        except TeamKeyConfigurationError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write("")
        self.stdout.write("APPLY COMPLETE")
        self.stdout.write(f"  mappings_requested: {result['mappings_requested']}")
        self.stdout.write(f"  rows_configured: {result['rows_configured']}")
        self.stdout.write("  failed_rows: 0")
        self.stdout.write(
            "Post-audit: run manage.py audit_ministry_team_identity independently."
        )

    def _print_plan(self, plan, *, apply):
        write = self.stdout.write
        write("Ministry Team key configuration preview")
        write(f"mode: {'APPLY' if apply else 'DRY RUN'}")
        write(f"plan_version: {PLAN_VERSION}")
        write("ordering: target database primary key ascending")
        write("")
        write("teams:")
        for row in plan["rows"]:
            current = (
                UNCONFIGURED
                if row["current_team_key"] is None
                else _display(row["current_team_key"])
            )
            write(f"  pk={row['pk']}")
            write(f"    current_team_key: {current}")
            write(f"    proposed_team_key: {row['proposed_team_key']}")
            write(f"    name: {_display(row['name'])}")
            write(f"    name_en: {_display(row['name_en'])}")
            write(f"    active: {str(row['is_active']).lower()}")
            write(f"    assignable: {str(row['is_assignable']).lower()}")
            write(
                "    worship_rotation_pool: "
                f"{str(row['is_worship_rotation_pool']).lower()}"
            )
            write(f"    primary_path: {_display(row['primary_path'])}")

        write("")
        write("summary:")
        for key in (
            "requested_mappings",
            "exact_teams_resolved",
            "currently_unconfigured",
            "proposed_unique_keys",
            "blockers",
            "integrity_problems",
        ):
            write(f"  {key}: {plan['summary'][key]}")

        if plan["blockers"]:
            write("blockers:")
            for blocker in plan["blockers"]:
                write(f"  - {blocker}")
        if plan["integrity_problems"]:
            write("identity_integrity_problems:")
            for problem in plan["integrity_problems"]:
                write(f"  - {problem}")

        if plan["ready"]:
            write("readiness: READY TO APPLY")
            write(f"confirmation_token: {plan['confirmation_token']}")
            write(
                "The token binds reviewed current state; it is not an authentication credential."
            )
        else:
            write("readiness: NOT READY")
            write("No actionable apply recommendation is available.")
