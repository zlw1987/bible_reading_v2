import csv
import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.dateparse import parse_date

from reading.models import ActivePlan, ReadingPlan, ReadingPlanDay


class Command(BaseCommand):
    help = "Import legacy SVCA reading plans generated from the old PHP/MySQL dump."

    def add_arguments(self, parser):
        parser.add_argument(
            "--base-dir",
            default="data/import/legacy_svca_plans",
            help="Directory containing legacy_plan_metadata.json and plan CSV files.",
        )
        parser.add_argument(
            "--replace",
            action="store_true",
            help="Replace existing ReadingPlanDay rows for matching plan names.",
        )
        parser.add_argument(
            "--create-active-plans",
            action="store_true",
            help="Create ActivePlan rows too.",
        )
        parser.add_argument(
            "--start-date",
            help="Override ActivePlan start date. Format: YYYY-MM-DD. If omitted, uses legacy_start_date from metadata.",
        )

    def handle(self, *args, **options):
        base_dir = Path(options["base_dir"])
        metadata_path = base_dir / "legacy_plan_metadata.json"

        if not metadata_path.exists():
            raise CommandError(f"Metadata file not found: {metadata_path}")

        override_start_date = None
        if options.get("start_date"):
            override_start_date = parse_date(options["start_date"])
            if override_start_date is None:
                raise CommandError("Invalid --start-date. Use YYYY-MM-DD.")

        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))

        with transaction.atomic():
            for item in metadata:
                csv_path = Path(item["csv_file"])
                if not csv_path.exists():
                    raise CommandError(f"CSV file not found: {csv_path}")

                plan, created = ReadingPlan.objects.get_or_create(
                    name=item["name"],
                    defaults={
                        "description": item.get("description", ""),
                        "is_active": True,
                    },
                )

                if not created:
                    plan.description = item.get("description", "")
                    plan.is_active = True
                    plan.save(update_fields=["description", "is_active"])

                if options["replace"]:
                    plan.days.all().delete()
                elif plan.days.exists():
                    raise CommandError(
                        f"Reading plan already has days: {plan.name}. Use --replace."
                    )

                rows = self._read_plan_csv(csv_path)
                ReadingPlanDay.objects.bulk_create(
                    [
                        ReadingPlanDay(
                            plan=plan,
                            day_number=row["day_number"],
                            reading_text=row["reading_text"],
                            memory_verse=row["memory_verse"],
                        )
                        for row in rows
                    ]
                )

                self.stdout.write(
                    self.style.SUCCESS(f"Imported {len(rows)} days: {plan.name}")
                )

                if options["create_active_plans"]:
                    start_date = override_start_date
                    if start_date is None and item.get("legacy_start_date"):
                        start_date = parse_date(item["legacy_start_date"])

                    if start_date is None:
                        raise CommandError(
                            f"No valid start date for ActivePlan: {plan.name}"
                        )

                    ActivePlan.objects.get_or_create(
                        plan=plan,
                        start_date=start_date,
                        title=f"{plan.name} from {start_date}",
                    )

    def _read_plan_csv(self, csv_path):
        rows = []
        seen_days = set()

        with csv_path.open("r", encoding="utf-8-sig", newline="") as csv_file:
            reader = csv.DictReader(csv_file)
            required_columns = {"day_number", "reading_text"}
            headers = set(reader.fieldnames or [])
            missing = required_columns - headers
            if missing:
                raise CommandError(
                    f"{csv_path} missing required column(s): {', '.join(sorted(missing))}"
                )

            for line_number, row in enumerate(reader, start=2):
                day_number = int((row.get("day_number") or "").strip())
                reading_text = (row.get("reading_text") or "").strip()
                memory_verse = (row.get("memory_verse") or "").strip()

                if day_number <= 0:
                    raise CommandError(f"{csv_path} line {line_number}: invalid day_number.")
                if day_number in seen_days:
                    raise CommandError(f"{csv_path} line {line_number}: duplicate day_number.")
                if not reading_text:
                    raise CommandError(f"{csv_path} line {line_number}: reading_text is blank.")

                seen_days.add(day_number)
                rows.append(
                    {
                        "day_number": day_number,
                        "reading_text": reading_text,
                        "memory_verse": memory_verse,
                    }
                )

        rows.sort(key=lambda item: item["day_number"])
        return rows
