"""Read-only MO-S.6D-PROFILE-SETUP.0A management command."""

import json
import re
from datetime import time

from django.core.management.base import BaseCommand, CommandError
from django.core.exceptions import ValidationError

from events.models import ServiceEvent, ServiceProfile, validate_service_profile_key
from events.service_profile_readiness import build_audit, render_text_report


class Command(BaseCommand):
    help = (
        "Read-only ServiceEvent profile setup audit. Defaults to the approved "
        "2026 bethany_0930_cm Sunday 09:30 contract; writes nothing, has no "
        "apply mode, does not tag events, and does not read an Excel workbook."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--profile-key",
            default="bethany_0930_cm",
            help="Persisted ServiceProfile key (default: bethany_0930_cm).",
        )
        parser.add_argument(
            "--year",
            type=int,
            default=2026,
            help="Local contract year (default: 2026).",
        )
        parser.add_argument(
            "--time",
            dest="target_time",
            default="09:30",
            help="Exact local HH:MM business time (default: 09:30).",
        )
        parser.add_argument(
            "--event-type",
            choices=[value for value, _label in ServiceEvent.EVENT_TYPE_CHOICES],
            default=ServiceEvent.EVENT_SUNDAY_SERVICE,
            help="Expected ServiceEvent type (default: sunday_service).",
        )
        parser.add_argument(
            "--json",
            action="store_true",
            help="Print deterministic privacy-bounded JSON to stdout.",
        )

    def handle(self, *args, **options):
        profile_key = options["profile_key"]
        try:
            canonical_profile_key = validate_service_profile_key(profile_key)
        except ValidationError as exc:
            raise CommandError(
                "--profile-key must use lowercase ASCII letters, digits, "
                "underscores, hyphens, or periods."
            ) from exc
        if canonical_profile_key != profile_key:
            raise CommandError("--profile-key must already be canonical.")
        profile_key_max_length = ServiceProfile._meta.get_field("key").max_length
        if len(profile_key) > profile_key_max_length:
            raise CommandError(
                f"--profile-key must be at most {profile_key_max_length} characters."
            )
        year = options["year"]
        if year < 1 or year > 9998:
            raise CommandError("--year must be between 1 and 9998.")
        raw_time = options["target_time"]
        if not re.fullmatch(r"\d{2}:\d{2}", raw_time):
            raise CommandError("--time must use exact HH:MM format.")
        try:
            hour, minute = (int(part) for part in raw_time.split(":"))
            target_time = time(hour, minute)
        except ValueError as exc:
            raise CommandError("--time must be a valid local HH:MM time.") from exc

        audit = build_audit(
            profile_key=profile_key,
            year=year,
            target_time=target_time,
            event_type=options["event_type"],
        )
        if options["json"]:
            self.stdout.write(
                json.dumps(audit, ensure_ascii=False, indent=2, sort_keys=True)
            )
        else:
            self.stdout.write(render_text_report(audit))
