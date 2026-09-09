"""Dry-run-first reviewed Service Profile RequiredTeam materialization."""

import json
import re
from datetime import date

from django.core.management.base import BaseCommand, CommandError

from ministry.service_profile_required_team_materialization import (
    MaterializationInputError,
    MaterializationProfileNotFound,
)
from ministry.service_profile_required_team_materialization_apply import (
    PLAN_VERSION,
    ServiceProfileRequiredTeamMaterializationError,
    apply_service_profile_required_team_materialization,
    build_service_profile_required_team_materialization_plan,
)


def _display(value):
    return json.dumps(value, ensure_ascii=False)


class Command(BaseCommand):
    help = (
        "Materialize reviewed missing Service Profile static defaults into "
        "explicit existing-event RequiredTeam rows. Dry-run by default."
    )

    def add_arguments(self, parser):
        parser.add_argument("--profile-key", required=True)
        parser.add_argument("--start-date", required=True, type=date.fromisoformat)
        parser.add_argument("--end-date", required=True, type=date.fromisoformat)
        parser.add_argument("--actor-user-id", required=True, type=int)
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--confirmation-token", default=None)
        parser.add_argument("--json", action="store_true")

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
            plan = build_service_profile_required_team_materialization_plan(
                profile_key=options["profile_key"],
                start_date=options["start_date"],
                end_date=options["end_date"],
                actor_user_id=options["actor_user_id"],
            )
        except MaterializationProfileNotFound:
            raise CommandError(
                f"No Service Profile has exact key {options['profile_key']!r}."
            ) from None
        except (MaterializationInputError, ValueError) as exc:
            raise CommandError(str(exc)) from exc
        except ServiceProfileRequiredTeamMaterializationError as exc:
            raise CommandError(str(exc)) from exc

        if options["json"] and not options["apply"]:
            self.stdout.write(json.dumps(plan, ensure_ascii=False, sort_keys=True, indent=2))
            return
        self._print_plan(plan, apply=options["apply"])
        if not options["apply"]:
            if token:
                self.stdout.write(
                    "confirmation-token supplied without --apply: DRY RUN only; "
                    "no data was changed."
                )
            return
        if plan["readiness"] == "BLOCKED":
            raise CommandError(
                "BLOCKED: resolve every 7A blocker, then run a fresh dry-run."
            )
        if plan["readiness"] != "READY_TO_APPLY":
            raise CommandError(
                "READY / NO MATERIALIZATION NEEDED: no apply token is available."
            )

        try:
            result = apply_service_profile_required_team_materialization(
                profile_key=options["profile_key"],
                start_date=options["start_date"],
                end_date=options["end_date"],
                actor_user_id=options["actor_user_id"],
                confirmation_token=token,
            )
        except (ServiceProfileRequiredTeamMaterializationError, MaterializationInputError) as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write("")
        self.stdout.write("APPLY COMPLETE")
        self.stdout.write(f"operation_id: {result['operation_id']}")
        self.stdout.write(
            "changed_events: "
            + ",".join(str(value) for value in result["changed_event_ids"])
        )
        for claim in result["claimed_revisions"]:
            self.stdout.write(
                "claimed_revision: "
                f"event={claim['event_pk']} "
                f"revision_before={claim['revision_before']} "
                f"revision_after={claim['revision_after']}"
            )
        self.stdout.write(
            f"required_team_rows_created: {result['required_team_rows_created']}"
        )
        self.stdout.write(f"audit_rows_created: {result['audit_rows_created']}")
        self.stdout.write("data_mutated: true")
        self.stdout.write("event_materialization: true (RequiredTeam operational rows)")
        if options["json"]:
            self.stdout.write(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))

    def _print_plan(self, plan, *, apply):
        write = self.stdout.write
        preview = plan["source_preview"]
        summary = preview["summary"]
        actor = plan["actor"]
        write("Service Profile RequiredTeam reviewed materialization")
        write(f"mode: {'APPLY' if apply else 'DRY RUN'}")
        write(f"source_preview_version: {plan['source_preview_version']}")
        write(f"source_preview_fingerprint: {plan['source_preview_fingerprint']}")
        write(f"materialization_plan_version: {PLAN_VERSION}")
        write(
            "actor: "
            f"pk={actor['pk']} username={_display(actor['username'])} "
            f"active={str(actor['is_active']).lower()} "
            f"staff={str(actor['is_staff']).lower()} "
            f"superuser={str(actor['is_superuser']).lower()}"
        )
        profile = preview["profile"]
        write(
            "profile: "
            f"pk={profile['pk']} key={_display(profile['key'])} "
            f"event_type={profile['event_type']} active={str(profile['is_active']).lower()}"
        )
        write(
            "scope: configured-local dates "
            f"{preview['scope']['start_date']} through {preview['scope']['end_date']} inclusive"
        )
        write(f"selected_events: {summary['selected_events']}")
        write(f"changed_events: {plan['changed_event_count']}")
        write(f"complete_noop_events: {plan['complete_event_count']}")
        for key in (
            "active_defaults",
            "expected_default_pairs",
            "already_default_pairs",
            "missing_default_pairs",
            "manual_extra_rows",
            "explicit_worship_rows",
            "invalid_explicit_rows",
            "inactive_default_history_rows",
            "events_with_review_evidence",
            "blockers",
        ):
            write(f"{key}: {summary[key]}")
        for event in preview["events"]:
            write(
                f"event id={event['event_pk']} lifecycle={event['lifecycle_status']} "
                f"expected_revision={event['scheduling_revision']}"
            )
            for team_pk, team_key in event["missing_default_teams"]:
                write(f"  missing/create team={team_pk}:{_display(team_key)}")
        if preview["invalid_active_requirements"]:
            write(
                "invalid_active_requirements: "
                + ",".join(
                    str(value) for value in preview["invalid_active_requirements"]
                )
            )
        for blocker in preview["identity_blockers"]:
            write(
                "identity_blocker: "
                f"event={blocker['event_pk']} state={blocker['identity_state']}"
            )

        if plan["readiness"] == "BLOCKED":
            write("readiness: BLOCKED")
            write("No confirmation token is available.")
        elif plan["readiness"] == "READY_TO_APPLY":
            write("readiness: READY TO APPLY")
            write(f"confirmation_token: {plan['confirmation_token']}")
        else:
            write("readiness: READY / NO MATERIALIZATION NEEDED")
            write("No confirmation token is available.")
        if not apply:
            write("data_mutated: false")
            write("event_materialization: false")
        write(
            "BOUNDARY: create-only missing static-default RequiredTeam pairs; "
            "existing/manual/history/Worship rows are preserved; no assignment, "
            "notification, Worship selection, or new event is created."
        )
