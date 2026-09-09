"""Read-only existing-event materialization preview."""

import json
from datetime import date

from django.core.management.base import BaseCommand, CommandError

from ministry.service_profile_required_team_materialization import (
    MaterializationInputError,
    MaterializationProfileNotFound,
    inspect_service_profile_required_team_materialization,
)


class Command(BaseCommand):
    help = "Read-only ServiceProfile required-team materialization preview; writes nothing."

    def add_arguments(self, parser):
        parser.add_argument("--profile-key", required=True)
        parser.add_argument("--start-date", required=True, type=date.fromisoformat)
        parser.add_argument("--end-date", required=True, type=date.fromisoformat)
        parser.add_argument("--json", action="store_true")

    def handle(self, *args, **options):
        try:
            result = inspect_service_profile_required_team_materialization(
                profile_key=options["profile_key"], start_date=options["start_date"], end_date=options["end_date"],
            )
        except (MaterializationInputError, ValueError) as error:
            raise CommandError(str(error)) from None
        except MaterializationProfileNotFound:
            raise CommandError(f"No Service Profile has exact key {options['profile_key']!r}.") from None
        if options["json"]:
            self.stdout.write(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
            return
        self.stdout.write("Service Profile RequiredTeam materialization preview (GENERIC-DEPLOYMENT-CONFIG.7A)")
        self.stdout.write("mode: read-only; no --apply exists; no data was changed")
        self.stdout.write(f"profile: pk={result['profile']['pk']} key={result['profile']['key']!r} event_type={result['profile']['event_type']}")
        self.stdout.write(f"scope: local dates {result['scope']['start_date']} through {result['scope']['end_date']} inclusive; FK-selected only")
        for event in result["events"]:
            self.stdout.write(f"event id={event['event_pk']} local_start={event['local_start']} lifecycle={event['lifecycle_status']} revision={event['scheduling_revision']} identity={event['identity_state']}")
            for row in event["required_team_rows"]:
                self.stdout.write(f"  stored row={row['required_team_row_pk']} team={row['team_pk']}:{row['team_key']!r} classifications={','.join(row['classifications'])}")
            for team_pk, team_key in event["missing_default_teams"]:
                self.stdout.write(f"  missing addition for later review only: team={team_pk}:{team_key!r}")
        for key, value in result["summary"].items():
            self.stdout.write(f"{key}: {value}")
        if result["summary"]["blockers"]:
            self.stdout.write("BLOCKED / INVALID PROFILE DEFAULTS OR PROFILE IDENTITY DRIFT")
        elif result["summary"]["missing_default_pairs"]:
            self.stdout.write("READY FOR REVIEW / MISSING DEFAULTS PRESENT")
        else:
            self.stdout.write("READY / NO MATERIALIZATION NEEDED")
        self.stdout.write(f"state_fingerprint ({result['version']}): {result['state_fingerprint']}")
        self.stdout.write("READ-ONLY: no ServiceEventRequiredTeam, ServiceEvent, scheduling revision, notification, audit row, or Worship selection changed.")
