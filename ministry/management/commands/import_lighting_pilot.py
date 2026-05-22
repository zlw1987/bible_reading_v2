from django.core.management.base import BaseCommand, CommandError

from ministry.services.lighting_pilot_import import (
    ImportStructureError,
    import_lighting_pilot,
    read_csv_path,
)


class Command(BaseCommand):
    help = "Import limited Lighting Team pilot data into generic Ministry Operations models."

    def add_arguments(self, parser):
        parser.add_argument("--csv", required=True, help="Path to the pilot CSV file.")
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Validate and report changes without writing to the database.",
        )
        parser.add_argument(
            "--allow-past",
            action="store_true",
            help="Allow rows older than today. Default rejects past rows.",
        )

    def handle(self, *args, **options):
        try:
            rows = read_csv_path(options["csv"])
        except ImportStructureError as exc:
            raise CommandError(str(exc)) from exc

        stats = import_lighting_pilot(
            rows,
            dry_run=options["dry_run"],
            allow_past=options["allow_past"],
        )

        for message in stats.row_messages:
            self.stdout.write(message)
        if options["dry_run"]:
            self.stdout.write("Dry run complete. No database changes were saved.")
        for key, count in stats.summary_items():
            self.stdout.write(f"{key}={count}")
        if stats.errors:
            self.stdout.write("Row errors:")
            for error in stats.errors:
                self.stdout.write(f"- {error}")
