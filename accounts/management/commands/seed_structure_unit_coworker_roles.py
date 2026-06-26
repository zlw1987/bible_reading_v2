from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounts.models import (
    ChurchStructureUnitRoleProfile,
    ChurchStructureUnitRoleRequirement,
    ChurchStructureUnitRoleType,
)


class Command(BaseCommand):
    help = (
        "Seed/maintain default structure-unit coworker role types, profiles, "
        "and requirement rows. Defaults to dry-run; pass --apply to write. "
        "This command does not assign users and does not mutate structure units."
    )

    ROLE_TYPES = [
        {
            "code": ChurchStructureUnitRoleType.CODE_LEAD,
            "name": "负责人",
            "name_en": "Lead",
            "description": "默认负责人角色，可代表主任牧师、区长或小组长。",
            "description_en": (
                "Default lead role for a unit, such as senior pastor, district "
                "leader, or small-group leader."
            ),
            "sort_order": 10,
        },
        {
            "code": ChurchStructureUnitRoleType.CODE_ASSISTANT_LEAD,
            "name": "副组长",
            "name_en": "Assistant Lead",
            "description": "小组型单元的副带领同工。",
            "description_en": "Assistant lead coworker for small-group-like units.",
            "sort_order": 20,
        },
        {
            "code": ChurchStructureUnitRoleType.CODE_CARING,
            "name": "关怀同工",
            "name_en": "Caring",
            "description": "小组型单元的关怀同工。",
            "description_en": "Caring coworker for small-group-like units.",
            "sort_order": 30,
        },
        {
            "code": ChurchStructureUnitRoleType.CODE_EDIFY,
            "name": "带查经同工",
            "name_en": "Edify",
            "description": "小组型单元的查经带领候选同工。",
            "description_en": (
                "Bible Study discussion-leading coworker for small-group-like units."
            ),
            "sort_order": 40,
        },
        {
            "code": ChurchStructureUnitRoleType.CODE_OUTREACH,
            "name": "福音同工",
            "name_en": "Outreach",
            "description": "小组型单元的福音外展同工。",
            "description_en": "Outreach coworker for small-group-like units.",
            "sort_order": 50,
        },
        {
            "code": ChurchStructureUnitRoleType.CODE_WORSHIP,
            "name": "敬拜同工",
            "name_en": "Worship",
            "description": "小组型单元的敬拜带领候选同工。",
            "description_en": (
                "Worship-leading coworker for small-group-like units."
            ),
            "sort_order": 60,
        },
    ]

    PROFILES = [
        {
            "code": ChurchStructureUnitRoleProfile.CODE_GENERAL_UNIT,
            "name": "一般单元",
            "name_en": "General Unit",
            "description": "一般结构单元的默认角色模板。",
            "description_en": "Default role template for general structure units.",
            "sort_order": 10,
        },
        {
            "code": ChurchStructureUnitRoleProfile.CODE_DISTRICT_UNIT,
            "name": "区级单元",
            "name_en": "District Unit",
            "description": "区级结构单元的默认角色模板。",
            "description_en": "Default role template for district-level units.",
            "sort_order": 20,
        },
        {
            "code": ChurchStructureUnitRoleProfile.CODE_SMALL_GROUP_UNIT,
            "name": "小组型单元",
            "name_en": "Small-Group Unit",
            "description": "小组型结构单元的默认同工角色模板。",
            "description_en": (
                "Default coworker role template for small-group-like units."
            ),
            "sort_order": 30,
        },
        {
            "code": ChurchStructureUnitRoleProfile.CODE_DEPARTMENT_UNIT,
            "name": "部门单元",
            "name_en": "Department Unit",
            "description": "部门型结构单元的默认角色模板。",
            "description_en": "Default role template for department units.",
            "sort_order": 40,
        },
        {
            "code": ChurchStructureUnitRoleProfile.CODE_CUSTOM,
            "name": "自定义",
            "name_en": "Custom",
            "description": "可由教会按需配置的自定义角色模板。",
            "description_en": "Custom role template configurable by the church.",
            "sort_order": 50,
        },
    ]

    REQUIREMENTS = {
        ChurchStructureUnitRoleProfile.CODE_GENERAL_UNIT: {
            ChurchStructureUnitRoleType.CODE_LEAD: True,
        },
        ChurchStructureUnitRoleProfile.CODE_DISTRICT_UNIT: {
            ChurchStructureUnitRoleType.CODE_LEAD: True,
        },
        ChurchStructureUnitRoleProfile.CODE_SMALL_GROUP_UNIT: {
            ChurchStructureUnitRoleType.CODE_LEAD: True,
            ChurchStructureUnitRoleType.CODE_ASSISTANT_LEAD: True,
            ChurchStructureUnitRoleType.CODE_CARING: True,
            ChurchStructureUnitRoleType.CODE_EDIFY: True,
            ChurchStructureUnitRoleType.CODE_OUTREACH: True,
            ChurchStructureUnitRoleType.CODE_WORSHIP: False,
        },
        ChurchStructureUnitRoleProfile.CODE_DEPARTMENT_UNIT: {
            ChurchStructureUnitRoleType.CODE_LEAD: True,
        },
        ChurchStructureUnitRoleProfile.CODE_CUSTOM: {
            ChurchStructureUnitRoleType.CODE_LEAD: True,
        },
    }

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview changes without writing. This is the default mode.",
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Write default coworker role types, profiles, and requirements.",
        )

    def handle(self, *args, **options):
        if options["dry_run"] and options["apply"]:
            raise CommandError("Use either --dry-run or --apply, not both.")

        self.apply = options["apply"]
        self.stats = {
            "role_types_created": 0,
            "role_types_updated": 0,
            "role_types_skipped": 0,
            "profiles_created": 0,
            "profiles_updated": 0,
            "profiles_skipped": 0,
            "requirements_created": 0,
            "requirements_updated": 0,
            "requirements_skipped": 0,
            "warnings": 0,
        }

        mode = "APPLY" if self.apply else "DRY RUN"
        self.stdout.write(f"Structure unit coworker role seed mode: {mode}")

        if self.apply:
            with transaction.atomic():
                self._run()
        else:
            self._run()

        self._write_summary()

    def _run(self):
        role_types = {
            role_type.code: role_type
            for role_type in [
                self._ensure_role_type(values) for values in self.ROLE_TYPES
            ]
            if role_type is not None
        }
        profiles = {
            profile.code: profile
            for profile in [
                self._ensure_profile(values) for values in self.PROFILES
            ]
            if profile is not None
        }

        for profile_code, requirement_map in self.REQUIREMENTS.items():
            profile = profiles.get(profile_code)
            if profile is None:
                self._warn(
                    f"Skipping requirements for {profile_code}: profile missing in dry-run."
                )
                continue

            for role_type_code, is_required in requirement_map.items():
                role_type = role_types.get(role_type_code)
                if role_type is None:
                    self._warn(
                        "Skipping requirement "
                        f"{profile_code}/{role_type_code}: role type missing in dry-run."
                    )
                    continue
                self._ensure_requirement(
                    profile=profile,
                    role_type=role_type,
                    is_required=is_required,
                )

    def _ensure_role_type(self, values):
        values = {
            **values,
            "is_active": True,
            "is_system_default": True,
        }
        role_type = ChurchStructureUnitRoleType.objects.filter(
            code=values["code"]
        ).first()
        return self._ensure_object(
            obj=role_type,
            model=ChurchStructureUnitRoleType,
            lookup={"code": values["code"]},
            values=values,
            fields=[
                "name",
                "name_en",
                "description",
                "description_en",
                "is_active",
                "is_system_default",
                "sort_order",
            ],
            label=f"role type {values['code']}",
            created_key="role_types_created",
            updated_key="role_types_updated",
            skipped_key="role_types_skipped",
        )

    def _ensure_profile(self, values):
        values = {
            **values,
            "is_active": True,
            "is_system_default": True,
        }
        profile = ChurchStructureUnitRoleProfile.objects.filter(
            code=values["code"]
        ).first()
        return self._ensure_object(
            obj=profile,
            model=ChurchStructureUnitRoleProfile,
            lookup={"code": values["code"]},
            values=values,
            fields=[
                "name",
                "name_en",
                "description",
                "description_en",
                "is_active",
                "is_system_default",
                "sort_order",
            ],
            label=f"role profile {values['code']}",
            created_key="profiles_created",
            updated_key="profiles_updated",
            skipped_key="profiles_skipped",
        )

    def _ensure_requirement(self, profile, role_type, is_required):
        values = {
            "profile": profile,
            "role_type": role_type,
            "is_required": is_required,
            "is_active": True,
            "sort_order": role_type.sort_order,
        }
        if not self.apply and (profile.pk is None or role_type.pk is None):
            requirement = None
        else:
            requirement = ChurchStructureUnitRoleRequirement.objects.filter(
                profile=profile,
                role_type=role_type,
            ).first()
        return self._ensure_object(
            obj=requirement,
            model=ChurchStructureUnitRoleRequirement,
            lookup={"profile": profile, "role_type": role_type},
            values=values,
            fields=["is_required", "is_active", "sort_order"],
            label=f"requirement {profile.code}/{role_type.code}",
            created_key="requirements_created",
            updated_key="requirements_updated",
            skipped_key="requirements_skipped",
        )

    def _ensure_object(
        self,
        *,
        obj,
        model,
        lookup,
        values,
        fields,
        label,
        created_key,
        updated_key,
        skipped_key,
    ):
        if obj is None:
            self.stats[created_key] += 1
            if not self.apply:
                self.stdout.write(f"Would create {label}")
                return model(**{**lookup, **values})

            obj = model(**{**lookup, **values})
            self._save_object(obj, label)
            self.stdout.write(f"Created {label}")
            return obj

        changed_fields = [
            field
            for field in fields
            if getattr(obj, field) != values[field]
        ]
        if not changed_fields:
            self.stats[skipped_key] += 1
            return obj

        self.stats[updated_key] += 1
        if not self.apply:
            self.stdout.write(f"Would update {label}: {', '.join(changed_fields)}")
            return obj

        for field in changed_fields:
            setattr(obj, field, values[field])
        self._save_object(obj, label)
        self.stdout.write(f"Updated {label}: {', '.join(changed_fields)}")
        return obj

    def _save_object(self, obj, label):
        try:
            obj.full_clean()
            obj.save()
        except ValidationError as exc:
            raise CommandError(f"Invalid default coworker {label}: {exc}") from exc

    def _warn(self, message):
        self.stats["warnings"] += 1
        self.stdout.write(self.style.WARNING(f"WARNING: {message}"))

    def _write_summary(self):
        prefix = "" if self.apply else "would "
        self.stdout.write("Summary:")
        self.stdout.write(f"  role types {prefix}created: {self.stats['role_types_created']}")
        self.stdout.write(f"  role types {prefix}updated: {self.stats['role_types_updated']}")
        self.stdout.write(f"  role types skipped: {self.stats['role_types_skipped']}")
        self.stdout.write(f"  profiles {prefix}created: {self.stats['profiles_created']}")
        self.stdout.write(f"  profiles {prefix}updated: {self.stats['profiles_updated']}")
        self.stdout.write(f"  profiles skipped: {self.stats['profiles_skipped']}")
        self.stdout.write(
            f"  requirements {prefix}created: {self.stats['requirements_created']}"
        )
        self.stdout.write(
            f"  requirements {prefix}updated: {self.stats['requirements_updated']}"
        )
        self.stdout.write(f"  requirements skipped: {self.stats['requirements_skipped']}")
        self.stdout.write("  user assignments created: 0")
        self.stdout.write("  structure units updated: 0")
        self.stdout.write(f"  warnings: {self.stats['warnings']}")
