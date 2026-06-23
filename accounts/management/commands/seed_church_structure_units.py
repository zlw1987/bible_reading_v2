from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounts.models import ChurchStructureUnit, District, MinistryContext, SmallGroup


class Command(BaseCommand):
    help = (
        "Seed/maintain ChurchStructureUnit rows for MinistryContext, District, "
        "and SmallGroup records. Defaults to dry-run; pass --apply to write "
        "changes. After LEGACY-PARENT-FK-FIELD-RETIRE.1A the legacy parent/context "
        "FKs (SmallGroup.district, District.ministry_context) no longer exist, so "
        "this command can no longer reconstruct the District/SmallGroup hierarchy "
        "from raw legacy links. MinistryContext units (whose parent is always the "
        "root) are still seeded normally; for District/SmallGroup rows the existing "
        "ChurchStructureUnit.parent and church_structure_unit mapping are treated "
        "as authoritative. Unmapped District/SmallGroup rows are reported as "
        "needing manual placement instead of being silently reparented to an "
        "unassigned holding unit."
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
            "unreconstructable": 0,
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
            self._ensure_mapping(context, unit, "MinistryContext")

    def _seed_districts(self, root):
        # LEGACY-PARENT-FK-FIELD-RETIRE.1A removed District.ministry_context, so the
        # district hierarchy can no longer be reconstructed from a legacy parent FK.
        # Only already-mapped districts are maintained (their existing
        # ChurchStructureUnit.parent is authoritative and is never changed here);
        # unmapped districts are reported for manual placement.
        for district in District.objects.select_related(
            "church_structure_unit"
        ).order_by("id"):
            unit = district.church_structure_unit
            if unit is None:
                self._warn_unreconstructable(
                    legacy_label=f"District {district.pk} {district.name}",
                    legacy_kind="District",
                )
                continue

            self._maintain_mapped_unit(
                legacy_obj=district,
                unit=unit,
                unit_type=ChurchStructureUnit.UNIT_DISTRICT,
                name=district.name,
                is_active=district.is_active,
                legacy_label=f"District {district.pk} {district.name}",
                legacy_kind="District",
            )

    def _seed_small_groups(self, root):
        # LEGACY-PARENT-FK-FIELD-RETIRE.1A removed SmallGroup.district, so the
        # small-group hierarchy can no longer be reconstructed from a legacy parent
        # FK. Only already-mapped groups are maintained (their existing
        # ChurchStructureUnit.parent is authoritative and is never changed here);
        # unmapped groups are reported for manual placement.
        for group in SmallGroup.objects.select_related(
            "church_structure_unit"
        ).order_by("id"):
            unit = group.church_structure_unit
            if unit is None:
                self._warn_unreconstructable(
                    legacy_label=f"SmallGroup {group.pk} {group.name}",
                    legacy_kind="SmallGroup",
                )
                continue

            self._maintain_mapped_unit(
                legacy_obj=group,
                unit=unit,
                unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
                name=group.name,
                is_active=group.is_active,
                legacy_label=f"SmallGroup {group.pk} {group.name}",
                legacy_kind="SmallGroup",
            )

    def _maintain_mapped_unit(
        self, legacy_obj, unit, unit_type, name, is_active, legacy_label, legacy_kind
    ):
        # The existing mapped unit's parent and code are authoritative and are
        # preserved; only the descriptive name/active fields are refreshed from the
        # legacy row. This never reparents and never moves rows between branches.
        self._ensure_unit(
            unit=unit,
            lookup_parent=unit.parent,
            lookup_code=unit.code,
            values={
                "parent": unit.parent,
                "unit_type": unit_type,
                "code": unit.code,
                "name": name,
                "name_en": unit.name_en,
                "description": unit.description,
                "description_en": unit.description_en,
                "is_active": is_active,
                "sort_order": unit.sort_order,
            },
            label=legacy_label,
        )
        self._ensure_mapping(legacy_obj, unit, legacy_kind)

    def _warn_unreconstructable(self, legacy_label, legacy_kind):
        self.stats["unreconstructable"] += 1
        self._warn(
            f"{legacy_label} has no church_structure_unit mapping. The legacy "
            f"{legacy_kind} parent/context FK was removed in "
            "LEGACY-PARENT-FK-FIELD-RETIRE.1A, so this command can no longer "
            "rebuild its hierarchy from raw legacy links. Map it via the staff "
            "structure mapping tools; it was not reparented to an unassigned "
            "holding unit."
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
        self.stdout.write(
            f"  unreconstructable (unmapped District/SmallGroup, manual placement "
            f"needed): {self.stats['unreconstructable']}"
        )
        self.stdout.write(f"  warnings: {self.stats['warnings']}")
