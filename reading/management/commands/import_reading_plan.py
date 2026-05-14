import csv
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.dateparse import parse_date

from reading.models import ActivePlan, ReadingPlan, ReadingPlanDay


class Command(BaseCommand):
    help = "Import a reading plan from a CSV file."

    def add_arguments(self, parser):
        parser.add_argument("--name-en", default="", help="English reading plan name.")
        parser.add_argument("--description-en", default="", help="English reading plan description.")
        parser.add_argument(
            "--name",
            required=True,
            help="Reading plan name.",
        )
        parser.add_argument(
            "--description",
            default="",
            help="Reading plan description.",
        )
        parser.add_argument(
            "--file",
            required=True,
            help="Path to CSV file.",
        )
        parser.add_argument(
            "--replace",
            action="store_true",
            help="Delete existing plan days before importing.",
        )
        parser.add_argument(
            "--start-date",
            help="Optional start date for creating an ActivePlan. Format: YYYY-MM-DD.",
        )
        parser.add_argument(
            "--active-title",
            default="",
            help="Optional title for the created ActivePlan.",
        )

    def handle(self, *args, **options):
        plan_name = options["name"].strip()
        name_en = options.get("name_en", "").strip()
        description = options["description"].strip()
        description_en = options.get("description_en", "").strip()
        file_path = Path(options["file"])
        replace = options["replace"]
        start_date_raw = options.get("start_date")
        active_title = options.get("active_title", "").strip()

        if not plan_name:
            raise CommandError("Plan name cannot be blank.")

        if not file_path.exists():
            raise CommandError(f"CSV file does not exist: {file_path}")

        start_date = None
        if start_date_raw:
            start_date = parse_date(start_date_raw)
            if start_date is None:
                raise CommandError("Invalid --start-date. Use YYYY-MM-DD.")

        rows = self._read_csv(file_path)

        with transaction.atomic():
            plan, created = ReadingPlan.objects.get_or_create(
                name=plan_name,
                defaults={
                    "name_en": name_en,
                    "description": description,
                    "description_en": description_en,
                    "is_active": True,
                },
            )

            if not created:
                if name_en:
                    plan.name_en = name_en
                if description:
                    plan.description = description
                if description_en:
                    plan.description_en = description_en
                plan.is_active = True
                plan.save()

            if replace:
                plan.days.all().delete()
            else:
                existing_days = set(
                    plan.days.values_list("day_number", flat=True)
                )
                incoming_days = {row["day_number"] for row in rows}
                duplicate_days = existing_days.intersection(incoming_days)

                if duplicate_days:
                    duplicate_list = ", ".join(str(day) for day in sorted(duplicate_days))
                    raise CommandError(
                        f"Plan already has day(s): {duplicate_list}. "
                        f"Use --replace to overwrite existing days."
                    )

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

            active_plan = None
            if start_date:
                title = active_title or f"{plan.name} from {start_date}"
                active_plan = ActivePlan.objects.create(
                    plan=plan,
                    start_date=start_date,
                    title=title,
                )

        self.stdout.write(
            self.style.SUCCESS(
                f"Imported {len(rows)} day(s) into reading plan: {plan.name}"
            )
        )

        if active_plan:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Created active plan: {active_plan}"
                )
            )

    def _read_csv(self, file_path):
        rows = []
        seen_days = set()

        with file_path.open("r", encoding="utf-8-sig", newline="") as csv_file:
            reader = csv.DictReader(csv_file)

            required_columns = {"day_number", "reading_text"}
            headers = set(reader.fieldnames or [])

            missing_columns = required_columns - headers
            if missing_columns:
                missing_list = ", ".join(sorted(missing_columns))
                raise CommandError(f"CSV missing required column(s): {missing_list}")

            for line_number, row in enumerate(reader, start=2):
                raw_day_number = (row.get("day_number") or "").strip()
                reading_text = (row.get("reading_text") or "").strip()
                memory_verse = (row.get("memory_verse") or "").strip()

                try:
                    day_number = int(raw_day_number)
                except ValueError:
                    raise CommandError(
                        f"Line {line_number}: day_number must be an integer."
                    )

                if day_number <= 0:
                    raise CommandError(
                        f"Line {line_number}: day_number must be greater than 0."
                    )

                if day_number in seen_days:
                    raise CommandError(
                        f"Line {line_number}: duplicate day_number {day_number}."
                    )

                if not reading_text:
                    raise CommandError(
                        f"Line {line_number}: reading_text cannot be blank."
                    )

                seen_days.add(day_number)

                rows.append(
                    {
                        "day_number": day_number,
                        "reading_text": reading_text,
                        "memory_verse": memory_verse,
                    }
                )

        if not rows:
            raise CommandError("CSV file has no reading days.")

        rows.sort(key=lambda item: item["day_number"])
        return rows