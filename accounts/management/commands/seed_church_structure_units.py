from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounts.models import ChurchStructureUnit, District, MinistryContext, SmallGroup


class Command(BaseCommand):
    help = (
        "Seed ChurchStructureUnit rows from MinistryContext, District, and "
        "SmallGroup records. Defaults to dry-run; pass --apply to write changes."
    )

    ROOT_CODE = "CHURCH"
    UNASSIGNED_DISTRICTS_CODE = "UNASSIGNED-DISTRICTS"
    UNASSIGNED_GROUPS_CODE = "UNASSIGNED-GROUPS"

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
        self.ministry_units = {}
        self.district_units = {}
        self.planned_holding_codes = set()

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
        root = self._ensure_root()
        self._seed_ministry_contexts(root)
        self._seed_districts(root)
        self._seed_small_groups(root)

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

    def _seed_ministry_contexts(self, root):
        for context in MinistryContext.objects.order_by("sort_order", "code", "id"):
            code = (context.code or f"MINISTRY-{context.id}").upper()
            unit = context.church_structure_unit
            parent = root if root else None

            unit = self._ensure_unit(
                unit=unit,
                lookup_parent=parent,
                lookup_code=code,
                values={
                    "parent": parent,
                    "unit_type": ChurchStructureUnit.UNIT_MINISTRY_CONTEXT,
                    "code": code,
                    "name": context.name,
                    "name_en": context.name_en,
                    "description": context.description,
                    "description_en": context.description_en,
                    "is_active": context.is_active,
                    "sort_order": context.sort_order,
                },
                label=f"MinistryContext {context.pk} {code}",
            )
            self.ministry_units[context.pk] = unit
            self._ensure_mapping(context, unit, "MinistryContext")

    def _seed_districts(self, root):
        for district in District.objects.select_related(
            "ministry_context",
            "church_structure_unit",
            "ministry_context__church_structure_unit",
        ).order_by("id"):
            parent = None
            if district.ministry_context_id:
                parent = self.ministry_units.get(district.ministry_context_id)
                if parent is None:
                    parent = district.ministry_context.church_structure_unit

            if parent is None:
                parent = self._ensure_holding_unit(
                    root=root,
                    code=self.UNASSIGNED_DISTRICTS_CODE,
                    name="未分配区",
                    name_en="Unassigned Districts",
                    sort_order=9000,
                    needed_label=f"District {district.pk} {district.name}",
                )

            code = f"DISTRICT-{district.id}"
            unit = self._ensure_unit(
                unit=district.church_structure_unit,
                lookup_parent=parent,
                lookup_code=code,
                values={
                    "parent": parent,
                    "unit_type": ChurchStructureUnit.UNIT_DISTRICT,
                    "code": code,
                    "name": district.name,
                    "name_en": "",
                    "description": "",
                    "description_en": "",
                    "is_active": district.is_active,
                    "sort_order": 0,
                },
                label=f"District {district.pk} {district.name}",
            )
            self.district_units[district.pk] = unit
            self._ensure_mapping(district, unit, "District")

    def _seed_small_groups(self, root):
        for group in SmallGroup.objects.select_related(
            "district",
            "church_structure_unit",
            "district__church_structure_unit",
        ).order_by("id"):
            parent = None
            if group.district_id:
                parent = self.district_units.get(group.district_id)
                if parent is None:
                    parent = group.district.church_structure_unit

            if parent is None:
                parent = self._ensure_holding_unit(
                    root=root,
                    code=self.UNASSIGNED_GROUPS_CODE,
                    name="未分配小组",
                    name_en="Unassigned Groups",
                    sort_order=9010,
                    needed_label=f"SmallGroup {group.pk} {group.name}",
                )

            code = f"SMALLGROUP-{group.id}"
            unit = self._ensure_unit(
                unit=group.church_structure_unit,
                lookup_parent=parent,
                lookup_code=code,
                values={
                    "parent": parent,
                    "unit_type": ChurchStructureUnit.UNIT_SMALL_GROUP,
                    "code": code,
                    "name": group.name,
                    "name_en": "",
                    "description": "",
                    "description_en": "",
                    "is_active": group.is_active,
                    "sort_order": 0,
                },
                label=f"SmallGroup {group.pk} {group.name}",
            )
            self._ensure_mapping(group, unit, "SmallGroup")

    def _ensure_holding_unit(self, root, code, name, name_en, sort_order, needed_label):
        if root is None and not self.apply:
            if code not in self.planned_holding_codes:
                self.planned_holding_codes.add(code)
                self._would_create(
                    f"holding unit {code} for {needed_label}; root would be its parent"
                )
            return None

        return self._ensure_unit(
            unit=None,
            lookup_parent=root,
            lookup_code=code,
            values={
                "parent": root,
                "unit_type": ChurchStructureUnit.UNIT_CUSTOM,
                "code": code,
                "name": name,
                "name_en": name_en,
                "description": "",
                "description_en": "",
                "is_active": True,
                "sort_order": sort_order,
            },
            label=f"holding unit {code}",
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

    def _ensure_mapping(self, legacy_obj, unit, legacy_label):
        if unit is None:
            if not self.apply:
                self.stats["linked"] += 1
                self.stdout.write(
                    f"Would link {legacy_label} {legacy_obj.pk} after unit creation"
                )
            return

        if legacy_obj.church_structure_unit_id == unit.pk:
            self.stats["skipped"] += 1
            return

        if not self.apply:
            self.stats["linked"] += 1
            self.stdout.write(
                f"Would link {legacy_label} {legacy_obj.pk} to {unit.path_label('en')}"
            )
            return

        legacy_obj.church_structure_unit = unit
        legacy_obj.save(update_fields=["church_structure_unit"])
        self.stats["linked"] += 1
        self.stdout.write(
            f"Linked {legacy_label} {legacy_obj.pk} to {unit.path_label('en')}"
        )

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
        self.stdout.write(f"  {prefix}linked: {self.stats['linked']}")
        self.stdout.write(f"  skipped: {self.stats['skipped']}")
        self.stdout.write(f"  warnings: {self.stats['warnings']}")
