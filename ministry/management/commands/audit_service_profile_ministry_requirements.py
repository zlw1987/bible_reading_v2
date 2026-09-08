"""Read-only audit of Service Profile Ministry Team defaults."""

import json

from django.core.management.base import BaseCommand, CommandError

from ministry.service_profile_ministry_requirements import (
    ServiceProfileRequirementProfileNotFound,
    inspect_service_profile_ministry_requirements,
)


def _display(value):
    return json.dumps(value or "", ensure_ascii=False)


class Command(BaseCommand):
    help = (
        "Read-only Service Profile ministry-default audit. Writes nothing, "
        "has no --apply mode, and treats zero configured defaults as ready."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--profile-key",
            help="Inspect one exact ServiceProfile.key.",
        )
        parser.add_argument(
            "--fail-on-blockers",
            action="store_true",
            help="Exit non-zero for invalid active requirements. Still read-only.",
        )

    def handle(self, *args, **options):
        try:
            inspection = inspect_service_profile_ministry_requirements(
                profile_key=options["profile_key"],
            )
        except ServiceProfileRequirementProfileNotFound:
            raise CommandError(
                f"No Service Profile has exact key {options['profile_key']!r}."
            ) from None

        write = self.stdout.write
        write(
            "Service Profile ministry requirements audit "
            "(GENERIC-DEPLOYMENT-CONFIG.6A)"
        )
        write("=" * 76)
        write("mode: read-only (no --apply exists; no data was changed)")
        scope = (
            "all Service Profiles"
            if options["profile_key"] is None
            else f"exact profile_key={_display(options['profile_key'])}"
        )
        write(f"scope: {scope}")
        write("ordering: requirement primary key ascending")
        write("")
        write("requirements:")
        for row in inspection.rows:
            reasons = (
                ",".join(reason.value for reason in row.validation_reasons)
                or "none"
            )
            write(
                f"  requirement_id={row.requirement_id} "
                f"| profile_id={row.service_profile_id} "
                f"| profile_key={_display(row.service_profile_key)} "
                f"| event_type={row.service_profile_event_type} "
                f"| profile_name={_display(row.service_profile_name)} "
                f"| profile_name_en={_display(row.service_profile_name_en)} "
                f"| profile_active={str(row.profile_is_active).lower()} "
                f"| team_id={row.ministry_team_id} "
                f"| team_key={_display(row.ministry_team_key)} "
                f"| team_name={_display(row.ministry_team_name)} "
                f"| team_name_en={_display(row.ministry_team_name_en)} "
                f"| team_active={str(row.team_is_active).lower()} "
                f"| assignable={str(row.team_is_assignable).lower()} "
                f"| worship_pool={str(row.team_is_worship_rotation_pool).lower()} "
                f"| requirement_active={str(row.requirement_is_active).lower()} "
                f"| sort_order={row.sort_order} "
                f"| state={row.validation_state.value} | reasons={reasons}"
            )

        write("")
        write("summary:")
        for key in (
            "service_profiles_with_requirements",
            "active_requirements",
            "inactive_requirements",
            "valid_active_requirements",
            "invalid_active_requirements",
            "worship_forbidden_requirements",
            "integrity_blockers",
        ):
            write(f"  {key}: {getattr(inspection, key)}")

        if not inspection.rows:
            write("READY / NO PROFILE MINISTRY DEFAULTS CONFIGURED")
        elif inspection.integrity_blockers:
            write("BLOCKED / INVALID ACTIVE PROFILE MINISTRY DEFAULTS")
        else:
            write("READY / ACTIVE PROFILE MINISTRY DEFAULTS VALID")
        write(
            "READ-ONLY: no profile, requirement, ServiceEvent, "
            "ServiceEventRequiredTeam, TeamAssignment, notification, or Worship "
            "selection was created, updated, or deleted."
        )

        if options["fail_on_blockers"] and inspection.integrity_blockers:
            raise CommandError(
                "Invalid active Service Profile ministry requirements detected "
                f"(integrity_blockers={inspection.integrity_blockers})."
            )
