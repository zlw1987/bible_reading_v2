from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from accounts.models import ChurchStructureMembership


class Command(BaseCommand):
    help = (
        "Backfill ChurchStructureMembership rows from Profile.small_group. "
        "Defaults to dry-run; pass --apply to write changes."
    )

    BACKFILL_NOTE = "Backfilled from Profile.small_group."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview changes without writing. This is the default mode.",
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Create active primary memberships from mapped Profile.small_group values.",
        )

    def handle(self, *args, **options):
        if options["dry_run"] and options["apply"]:
            raise CommandError("Use either --dry-run or --apply, not both.")

        self.apply = options["apply"]
        self.stats = {
            "created": 0,
            "skipped_no_profile_group": 0,
            "skipped_unmapped_group": 0,
            "skipped_existing_active_primary": 0,
            "warnings": 0,
            "errors": 0,
        }

        mode = "APPLY" if self.apply else "DRY RUN"
        self.stdout.write(f"Church structure membership backfill mode: {mode}")

        try:
            if self.apply:
                with transaction.atomic():
                    self._run()
            else:
                self._run()
        except CommandError:
            self._write_summary()
            raise

        self._write_summary()

    def _run(self):
        User = get_user_model()
        users = User.objects.select_related(
            "profile__small_group__church_structure_unit"
        ).order_by("username", "id")

        for user in users:
            self._process_user(user)

    def _process_user(self, user):
        try:
            profile = user.profile
        except ObjectDoesNotExist:
            self.stats["skipped_no_profile_group"] += 1
            return

        group = profile.small_group
        if group is None:
            self.stats["skipped_no_profile_group"] += 1
            return

        unit = group.church_structure_unit
        if unit is None:
            self.stats["skipped_unmapped_group"] += 1
            self._warn(
                f"User {user.get_username()} has Profile.small_group "
                f"'{group}' without a ChurchStructureUnit mapping."
            )
            return

        existing_primary = ChurchStructureMembership.current_primary_for_user(user)
        if existing_primary is not None:
            self.stats["skipped_existing_active_primary"] += 1
            return

        if not self.apply:
            self.stats["created"] += 1
            self.stdout.write(
                "Would create active primary membership for "
                f"{user.get_username()} -> {unit.path_label('en')}"
            )
            return

        membership = ChurchStructureMembership(
            user=user,
            unit=unit,
            membership_type=ChurchStructureMembership.TYPE_SMALL_GROUP_MEMBER,
            status=ChurchStructureMembership.STATUS_ACTIVE,
            is_primary=True,
            start_date=timezone.localdate(),
            approved_by=None,
            approved_at=None,
            requested_by=None,
            notes=self.BACKFILL_NOTE,
        )
        self._save_membership(membership, user)
        self.stats["created"] += 1
        self.stdout.write(
            "Created active primary membership for "
            f"{user.get_username()} -> {unit.path_label('en')}"
        )

    def _save_membership(self, membership, user):
        try:
            membership.full_clean()
            membership.save()
        except ValidationError as exc:
            self.stats["errors"] += 1
            raise CommandError(
                "Invalid ChurchStructureMembership for "
                f"{user.get_username()}: {exc}"
            ) from exc

    def _warn(self, message):
        self.stats["warnings"] += 1
        self.stdout.write(self.style.WARNING(f"WARNING: {message}"))

    def _write_summary(self):
        created_label = "created" if self.apply else "would_created"
        self.stdout.write("Summary:")
        self.stdout.write(f"  {created_label}: {self.stats['created']}")
        self.stdout.write(
            f"  skipped_no_profile_group: {self.stats['skipped_no_profile_group']}"
        )
        self.stdout.write(
            f"  skipped_unmapped_group: {self.stats['skipped_unmapped_group']}"
        )
        self.stdout.write(
            "  skipped_existing_active_primary: "
            f"{self.stats['skipped_existing_active_primary']}"
        )
        self.stdout.write(f"  warnings: {self.stats['warnings']}")
        self.stdout.write(f"  errors: {self.stats['errors']}")
