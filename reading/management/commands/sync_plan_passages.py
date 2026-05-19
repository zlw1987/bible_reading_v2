from django.core.management.base import BaseCommand, CommandError

from reading.models import ReadingPlan, ReadingPlanDay
from reading.passage_services import sync_plan_day_passages


class Command(BaseCommand):
    help = "Sync structured passages for reading plan days."

    def add_arguments(self, parser):
        parser.add_argument(
            "--plan-id",
            type=int,
            help="Sync only one reading plan by ID.",
        )
        parser.add_argument(
            "--all",
            action="store_true",
            help="Sync all reading plans.",
        )

    def handle(self, *args, **options):
        plan_id = options.get("plan_id")
        sync_all = options.get("all")

        if not plan_id and not sync_all:
            raise CommandError("Use --plan-id <id> or --all.")

        plans = ReadingPlan.objects.all().order_by("id")

        if plan_id:
            plans = plans.filter(id=plan_id)

            if not plans.exists():
                raise CommandError(f"ReadingPlan {plan_id} was not found.")

        total_days = 0
        total_passages = 0

        for plan in plans:
            days = ReadingPlanDay.objects.filter(plan=plan).order_by("day_number")

            for day in days:
                created_count = sync_plan_day_passages(day)
                total_days += 1
                total_passages += created_count

        self.stdout.write(
            self.style.SUCCESS(
                f"Synced {total_passages} passages from {total_days} reading days."
            )
        )