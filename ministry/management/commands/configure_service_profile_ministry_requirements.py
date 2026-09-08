"""Dry-run-first reviewed Service Profile ministry-default configuration."""

import json
import re

from django.core.management.base import BaseCommand, CommandError

from ministry.service_profile_ministry_requirement_configuration import (
    PLAN_VERSION,
    ServiceProfileMinistryRequirementConfigurationError,
    apply_requirement_configuration,
    build_requirement_configuration_plan,
    parse_team_values,
)


def _display(value):
    return json.dumps(value, ensure_ascii=False)


class Command(BaseCommand):
    help = (
        "Configure one exact ServiceProfile's complete active static Ministry "
        "Team default set. Dry-run by default; apply requires the exact current "
        "confirmation token."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--profile-key",
            required=True,
            help="Exact persisted ServiceProfile.key; no name or fuzzy fallback.",
        )
        desired = parser.add_mutually_exclusive_group(required=True)
        desired.add_argument(
            "--team",
            action="append",
            metavar="TEAM_PK=TEAM_KEY",
            help=(
                "Exact reviewed MinistryTeam PK and persisted team_key pair; "
                "repeat for the complete desired active set."
            ),
        )
        desired.add_argument(
            "--no-teams",
            action="store_true",
            help="Explicitly review an empty desired active set.",
        )
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--confirmation-token", default=None)

    def handle(self, *args, **options):
        token = options["confirmation_token"]
        if options["apply"] and not token:
            raise CommandError(
                "--apply requires --confirmation-token from the exact ready "
                "state-changing dry-run."
            )
        if options["apply"] and not re.fullmatch(r"[0-9a-f]{64}", token or ""):
            raise CommandError(
                "--confirmation-token must be exactly 64 lowercase hex characters."
            )

        try:
            identities = parse_team_values(
                options.get("team"),
                no_teams=options["no_teams"],
            )
            plan = build_requirement_configuration_plan(
                options["profile_key"],
                identities,
            )
        except ServiceProfileMinistryRequirementConfigurationError as exc:
            raise CommandError(str(exc)) from exc

        self._print_plan(plan, apply=options["apply"])
        if not options["apply"]:
            if token:
                self.stdout.write(
                    "confirmation-token supplied without --apply: DRY RUN only; "
                    "no data was changed."
                )
            return
        if not plan["ready"]:
            raise CommandError(
                "NOT READY: resolve every blocker, then run a fresh dry-run."
            )
        if not plan["has_changes"]:
            raise CommandError(
                "NO CHANGES: current active configuration already equals the "
                "desired set; no apply token is available."
            )

        try:
            result = apply_requirement_configuration(
                options["profile_key"],
                identities,
                token,
            )
        except ServiceProfileMinistryRequirementConfigurationError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write("")
        self.stdout.write("APPLY COMPLETE")
        for key, value in result.items():
            self.stdout.write(f"  {key}: {value}")
        self.stdout.write("  data_mutated: true")
        self.stdout.write("  event_materialization: false")
        self.stdout.write(
            "Post-audit: run manage.py audit_service_profile_ministry_requirements "
            f"--profile-key {_display(options['profile_key'])} independently."
        )

    def _print_plan(self, plan, *, apply):
        write = self.stdout.write
        write("Service Profile ministry requirement reviewed configuration")
        write(f"mode: {'APPLY' if apply else 'DRY RUN'}")
        write(f"plan_version: {PLAN_VERSION}")
        write("ordering: exact MinistryTeam primary key ascending")
        write("")
        write("PROFILE:")
        profile = plan["profile"]
        write(f"  requested_key: {_display(plan['profile_key'])}")
        write(f"  resolved: {str(profile['resolved']).lower()}")
        if profile["resolved"]:
            write(f"  pk: {profile['pk']}")
            write(f"  key: {_display(profile['key'])}")
            write(f"  event_type: {profile['event_type']}")
            write(f"  active: {str(profile['is_active']).lower()}")
            write(f"  updated_at: {profile['updated_at']}")

        write("")
        write("DESIRED ACTIVE TEAM SET:")
        if not plan["desired_team_identities"]:
            write("  EMPTY (explicit --no-teams)")
        for team in plan["desired_teams"]:
            write(
                f"  pk={team['resolved_pk']} | team_key={_display(team['resolved_team_key'])} "
                f"| active={str(team['is_active']).lower()} "
                f"| assignable={str(team['is_assignable']).lower()} "
                f"| worship_pool={str(team['is_worship_rotation_pool']).lower()} "
                "| canonical_worship_child="
                f"{str(team['is_canonical_worship_child']).lower()} "
                f"| updated_at={team['updated_at']}"
            )
        for target in plan["invalid_targets"]:
            write(
                f"  pk={target['supplied_pk']} | "
                f"team_key={_display(target['supplied_team_key'])} "
                f"| classification=invalid_target | reason={target['reason']}"
            )
        for target in plan["stale_conflicts"]:
            write(
                f"  pk={target['supplied_pk']} | "
                f"team_key={_display(target['supplied_team_key'])} "
                f"| classification=stale_conflicting | reason={target['reason']}"
            )

        write("")
        write("COMPLETE CURRENT REQUIREMENT SURFACE:")
        if not plan["current_requirements"]:
            write("  NONE")
        for row in plan["current_requirements"]:
            write(
                f"  requirement_pk={row['requirement_pk']} "
                f"| profile_pk={row['service_profile_pk']} "
                f"| team_pk={row['ministry_team_pk']} "
                f"| team_key={_display(row['ministry_team_key'])} "
                f"| active={str(row['is_active']).lower()} "
                f"| sort_order={row['sort_order']} "
                f"| updated_at={row['updated_at']}"
            )

        write("")
        write("CLASSIFICATIONS:")
        for action in plan["actions"]:
            write(
                f"  {action['classification']}: "
                f"requirement_pk={action['requirement_pk'] or 'NEW'} "
                f"| team_pk={action['ministry_team_pk']} "
                f"| team_key={_display(action['ministry_team_key'])} "
                f"| sort_order={action['sort_order']}"
            )
        write("summary:")
        for key in (
            "already_active",
            "create_new",
            "reactivate_existing",
            "deactivate_existing",
            "invalid_target",
            "stale_conflicting",
            "inactive_history",
        ):
            write(f"  {key}: {plan['classification_counts'][key]}")
        if plan["blockers"]:
            write("blockers:")
            for blocker in plan["blockers"]:
                write(f"  - {blocker}")

        write(f"state_fingerprint: {plan['state_fingerprint']}")
        if plan["ready"] and plan["has_changes"]:
            write("readiness: READY TO APPLY")
            write(f"confirmation_token: {plan['confirmation_token']}")
        elif plan["ready"]:
            write("readiness: READY / NO CHANGES")
            write("No apply action or confirmation token is available.")
        else:
            write("readiness: NOT READY")
            write("No actionable apply recommendation is available.")
        if not apply:
            write("data_mutated: false")
        write(
            "BOUNDARY: configuration only; no ServiceEventRequiredTeam, "
            "ServiceEvent, scheduling revision, TeamAssignment, notification, "
            "or Worship selection is changed or materialized."
        )
