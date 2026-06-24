from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounts.models import ChurchStructureUnit


class Command(BaseCommand):
    help = (
        "Seed/maintain canonical ChurchStructureUnit foundation rows. Defaults "
        "to dry-run; pass --apply to write changes. Legacy SmallGroup, District, "
        "and MinistryContext object rows were purged after the guarded apply, so "
        "this command no longer seeds from or updates legacy mapping rows."
    )

    ROOT_CODE = "CHURCH"

    MIRROR_FIELDS = [
        "parent",
        "unit_type",
        "code",
        "name",
        "name_en",
        "description",
        "description_en",
        "is_active",
        "sort_order",
    ]

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview changes without writing. This is the default mode.",
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Write the mirrored ChurchStructureUnit rows and mapping fields.",
        )

    def handle(self, *args, **options):
        if options["dry_run"] and options["apply"]:
            raise CommandError("Use either --dry-run or --apply, not both.")

        self.apply = options["apply"]
        self.stats = {
            "created": 0,
            "updated": 0,
            "linked": 0,
            "skipped": 0,
            "warnings": 0,
        }

        mode = "APPLY" if self.apply else "DRY RUN"
        self.stdout.write(f"Church structure unit seeding mode: {mode}")

        if self.apply:
            with transaction.atomic():
                self._run()
        else:
            self._run()

        self._write_summary()

    def _run(self):
        self._warn_for_multiple_roots()
        self._ensure_root()

    def _warn_for_multiple_roots(self):
        active_root_count = ChurchStructureUnit.objects.filter(
            unit_type=ChurchStructureUnit.UNIT_ROOT,
            is_active=True,
        ).count()
        if active_root_count > 1:
            self._warn(
                f"Found {active_root_count} active root units. "
                "This command will not destructively fix them."
            )

    def _ensure_root(self):
        existing_roots = list(
            ChurchStructureUnit.objects.filter(
                parent__isnull=True,
                code=self.ROOT_CODE,
            ).order_by("id")
        )
        if len(existing_roots) > 1:
            self._warn(
                f"Found {len(existing_roots)} parentless {self.ROOT_CODE} units. "
                "Using the first and leaving the rest unchanged."
            )

        unit = existing_roots[0] if existing_roots else None
        return self._ensure_unit(
            unit=unit,
            lookup_parent=None,
            lookup_code=self.ROOT_CODE,
            values={
                "parent": None,
                "unit_type": ChurchStructureUnit.UNIT_ROOT,
                "code": self.ROOT_CODE,
                "name": "全教会",
                "name_en": "Whole Church",
                "description": "",
                "description_en": "",
                "is_active": True,
                "sort_order": 0,
            },
            label="root CHURCH",
        )

    def _ensure_unit(self, unit, lookup_parent, lookup_code, values, label):
        if unit is None and lookup_parent is not None:
            unit = ChurchStructureUnit.objects.filter(
                parent=lookup_parent,
                code=lookup_code,
            ).first()

        if unit is None and lookup_parent is None:
            unit = ChurchStructureUnit.objects.filter(
                parent__isnull=True,
                code=lookup_code,
            ).first()

        if unit is None:
            if not self.apply:
                self._would_create(label)
                return None
            unit = ChurchStructureUnit(**values)
            self._save_unit(unit, label)
            self.stats["created"] += 1
            self.stdout.write(f"Created {label}: {unit.path_label('en')}")
            return unit

        changed_fields = self._changed_fields(unit, values)
        if not changed_fields:
            self.stats["skipped"] += 1
            return unit

        if not self.apply:
            self.stats["updated"] += 1
            self.stdout.write(
                f"Would update {label}: {', '.join(changed_fields)}"
            )
            return unit

        for field in changed_fields:
            setattr(unit, field, values[field])
        self._save_unit(unit, label)
        self.stats["updated"] += 1
        self.stdout.write(f"Updated {label}: {', '.join(changed_fields)}")
        return unit

    def _changed_fields(self, unit, values):
        changed_fields = []
        for field in self.MIRROR_FIELDS:
            current_value = getattr(unit, field)
            new_value = values[field]
            if field == "parent":
                current_value = unit.parent_id
                new_value = new_value.pk if new_value else None
            if current_value != new_value:
                changed_fields.append(field)
        return changed_fields

    def _save_unit(self, unit, label):
        try:
            unit.full_clean()
            unit.save()
        except ValidationError as exc:
            raise CommandError(f"Invalid ChurchStructureUnit for {label}: {exc}") from exc

    def _would_create(self, label):
        self.stats["created"] += 1
        self.stdout.write(f"Would create {label}")

    def _warn(self, message):
        self.stats["warnings"] += 1
        self.stdout.write(self.style.WARNING(f"WARNING: {message}"))

    def _write_summary(self):
        prefix = "" if self.apply else "would "
        self.stdout.write("Summary:")
        self.stdout.write(f"  {prefix}created: {self.stats['created']}")
        self.stdout.write(f"  {prefix}updated: {self.stats['updated']}")
        self.stdout.write(f"  legacy rows linked: {self.stats['linked']}")
        self.stdout.write(f"  skipped: {self.stats['skipped']}")
        self.stdout.write("  legacy row source: retired")
        self.stdout.write(f"  warnings: {self.stats['warnings']}")
