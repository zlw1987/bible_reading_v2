"""Dry-run-first reviewed Service Profile mapping command."""

import hashlib
import json
import re

from django.core.management.base import BaseCommand, CommandError

from events.service_profile_mapping import (
    PLAN_VERSION,
    ServiceProfileMappingError,
    apply_service_profile_mapping,
    build_service_profile_mapping_plan,
    normalize_mapping_inputs,
)


def _display(value):
    return json.dumps(value, ensure_ascii=False)


def _bounded_text(value, limit=160):
    if len(value) <= limit:
        return _display(value)
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
    return (
        f"{_display(value[:limit])}... "
        f"(length={len(value)}, sha256={digest})"
    )


class Command(BaseCommand):
    help = (
        "Create one reviewed ServiceProfile and map every exact legacy-key "
        "ServiceEvent. Dry-run by default; apply requires the exact state token."
    )

    def add_arguments(self, parser):
        parser.add_argument("--legacy-key", required=True)
        parser.add_argument("--event-type", required=True)
        parser.add_argument("--name", required=True)
        parser.add_argument("--name-en", default="")
        parser.add_argument("--description", default="")
        parser.add_argument("--description-en", default="")
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--confirmation-token", default=None)

    def handle(self, *args, **options):
        token = options["confirmation_token"]
        if options["apply"] and not token:
            raise CommandError(
                "--apply requires --confirmation-token from the exact ready dry-run."
            )
        if options["apply"] and not re.fullmatch(r"[0-9a-f]{64}", token or ""):
            raise CommandError("--confirmation-token must be exactly 64 lowercase hex characters.")

        try:
            profile_input = normalize_mapping_inputs(
                legacy_key=options["legacy_key"],
                event_type=options["event_type"],
                name=options["name"],
                name_en=options["name_en"],
                description=options["description"],
                description_en=options["description_en"],
            )
            plan = build_service_profile_mapping_plan(profile_input)
        except ServiceProfileMappingError as exc:
            raise CommandError(str(exc)) from exc

        self._print_plan(plan, apply=options["apply"])
        if not options["apply"]:
            if token:
                self.stdout.write(
                    "confirmation-token supplied without --apply: DRY RUN only; no data was changed."
                )
            return
        try:
            result = apply_service_profile_mapping(profile_input, token)
        except ServiceProfileMappingError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write("")
        self.stdout.write("APPLY COMPLETE")
        for key, value in result.items():
            self.stdout.write(f"  {key}: {value}")
        self.stdout.write("  data_mutated: true")
        self.stdout.write(
            "  runtime_consumer_switched: false (legacy service_profile_key remains authoritative)"
        )
        self.stdout.write(
            "Post-audit: run manage.py audit_service_profile_identity independently."
        )

    def _print_plan(self, plan, *, apply):
        write = self.stdout.write
        profile = plan["profile"]
        summary = plan["summary"]
        write("Service Profile reviewed mapping preview")
        write(f"mode: {'APPLY' if apply else 'DRY RUN'}")
        write(f"plan_version: {PLAN_VERSION}")
        write("ordering: target ServiceEvent primary key ascending")
        write("")
        write("PROFILE:")
        write(f"  proposed_key: {profile['key']}")
        write(f"  proposed_event_type: {profile['event_type']}")
        write(f"  proposed_name: {_display(profile['name'])}")
        write(f"  proposed_name_en: {_display(profile['name_en'])}")
        write(f"  proposed_description: {_bounded_text(profile['description'])}")
        write(
            "  proposed_description_en: "
            f"{_bounded_text(profile['description_en'])}"
        )
        write("  proposed_is_active: true")
        write(
            "  existing_service_profile_at_key: "
            f"{plan['existing_profile_at_key']['pk'] if plan['existing_profile_at_key'] else 'NULL'}"
        )
        write("")
        write("TARGET SET:")
        write(f"  exact_target_event_count: {summary['target_event_count']}")
        write(
            "  target_event_ids: "
            f"{_display([event['pk'] for event in plan['target_events']])}"
        )
        write(
            "  earliest_start_datetime: "
            f"{summary['earliest_start_datetime'].isoformat() if summary['earliest_start_datetime'] else 'NULL'}"
        )
        write(
            "  latest_start_datetime: "
            f"{summary['latest_start_datetime'].isoformat() if summary['latest_start_datetime'] else 'NULL'}"
        )
        write(f"  status_counts: {_display(summary['status_counts'])}")
        write(f"  current_fk_null: {summary['target_fk_null']}")
        write(f"  current_fk_nonnull: {summary['target_fk_nonnull']}")
        write(f"  current_fk_drift: {summary['target_fk_drift']}")
        write(
            "  scheduling_revisions: "
            f"{_display(summary['scheduling_revisions'])}"
        )
        write("  events:")
        for event in plan["target_events"]:
            write(
                f"    pk={event['pk']} | start={event['start_datetime']} "
                f"| status={event['status']} | legacy_key={_display(event['service_profile_key'])} "
                f"| event_type={event['event_type']} "
                f"| service_profile_id={event['service_profile_id'] or 'NULL'} "
                f"| scheduling_revision={event['scheduling_revision']} "
                f"| updated_at={event['updated_at']}"
            )

        write("")
        write("summary:")
        for key in (
            "target_event_count",
            "target_fk_null",
            "target_fk_nonnull",
            "target_fk_drift",
            "blockers",
        ):
            write(f"  {key}: {summary[key]}")
        if plan["blockers"]:
            write("blockers:")
            for blocker in plan["blockers"]:
                write(f"  - {blocker}")

        if plan["ready"]:
            write("readiness: READY TO APPLY")
            write(f"confirmation_token: {plan['confirmation_token']}")
            write(
                "The token binds the complete current target set and reviewed state; it is not authentication."
            )
        else:
            write("readiness: NOT READY")
            write("No actionable apply recommendation is available.")
        write(
            "DRY-RUN CONTRACT: no profile, FK, revision, notification, assignment, or required-team row is changed."
        )
