"""Read-only FK/Profile identity audit."""

from django.core.management.base import BaseCommand

from events.service_profile_identity import build_service_profile_identity_inventory


class Command(BaseCommand):
    help = "Read-only ServiceProfile identity audit; writes nothing and has no --apply."

    def handle(self, *args, **options):
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
