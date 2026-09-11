"""Read-only FK/Profile identity and explicit legacy-column pre-drop audit."""

from django.core.management.base import BaseCommand

from events.service_profile_identity import (
    build_pre_drop_legacy_key_inventory,
    build_service_profile_identity_inventory,
)


class Command(BaseCommand):
    help = "Read-only ServiceProfile identity audit; writes nothing and has no --apply."

    def add_arguments(self, parser):
        parser.add_argument(
            "--pre-drop-legacy-key",
            action="store_true",
            help=(
                "Read temporary ServiceEvent.service_profile_key storage only for "
                "the separately approved Stage-2 column-removal preflight."
            ),
        )

    def handle(self, *args, **options):
        if options["pre_drop_legacy_key"]:
            inventory = build_pre_drop_legacy_key_inventory()
            self.stdout.write("PRE-DROP LEGACY COLUMN AUDIT")
            self.stdout.write(inventory["version"])
            self.stdout.write("READ-ONLY")
            self.stdout.write("NO DATA CHANGED")
            self.stdout.write("=" * 76)
            for row in inventory["rows"]:
                self.stdout.write(
                    f"event_id={row['event_id']} profile_id={row['service_profile_id']} "
                    f"profile_key={row['profile_key']!r} legacy_key={row['legacy_key']!r} "
                    f"states={','.join(row['states']) or 'NONE'}"
                )
            self.stdout.write("summary:")
            for key, value in inventory["summary"].items():
                self.stdout.write(f"  {key}: {value}")
            self.stdout.write(
                "READINESS: "
                + (
                    "READY FOR COLUMN REMOVAL"
                    if inventory["summary"]["ready_for_column_removal"]
                    else "BLOCKED / HUMAN REVIEW REQUIRED"
                )
            )
            return

        inventory = build_service_profile_identity_inventory()
        self.stdout.write("Service Profile FK identity inventory")
        self.stdout.write(inventory["version"])
        self.stdout.write("READ-ONLY")
        self.stdout.write("NO DATA CHANGED")
        self.stdout.write("=" * 76)
        self.stdout.write("service_profiles:")
        for row in inventory["service_profiles"]:
            self.stdout.write(
                f"  pk={row['pk']} key={row['key']!r} type={row['event_type']} "
                f"active={str(row['is_active']).lower()} "
                f"linked_events={row['linked_service_event_count']}"
            )
        self.stdout.write("integrity_blockers:")
        for blocker in inventory["integrity_blockers"] or ("  none",):
            self.stdout.write(f"  {blocker}")
        self.stdout.write("summary:")
        for key, value in inventory["summary"].items():
            self.stdout.write(f"  {key}: {value}")
