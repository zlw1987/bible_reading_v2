from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from ministry.models import (
    MinistryTeamRoleProfile,
    MinistryTeamRoleRequirement,
    MinistryTeamRoleType,
)


class Command(BaseCommand):
    """MINISTRY-STRUCTURE.1E — seed default ministry-structure role config.

    Seeds/maintains default ministry role types, role profiles, and role
    requirement rows only. Defaults to dry-run; pass --apply to write.

    This command seeds configuration records only. It does NOT assign any user
    as a ministry role (no ``MinistryTeamRoleAssignment``), does NOT create or
    update ministry teams / parent links / memberships / serving assignments,
    does NOT assign a role profile to any existing team, and changes no
    permission, My Serving, Today, or visibility behavior.
    """

    help = (
        "Seed/maintain default ministry-structure role types, profiles, and "
        "requirement rows. Defaults to dry-run; pass --apply to write. This "
        "command does not assign users to ministry roles and does not mutate "
        "ministry teams, parent links, memberships, or serving assignments."
    )

    # The MinistryTeamRoleType model defines code constants up to member_care;
    # there is no CODE_CUSTOM constant for the role type, so the custom role
    # type uses the literal "custom" code (still normalized/validated by the
    # model). The profile model does define CODE_CUSTOM.
    ROLE_TYPE_CUSTOM_CODE = "custom"

    ROLE_TYPES = [
        {
            "code": MinistryTeamRoleType.CODE_LEAD,
            "name": "负责人",
            "name_en": "Lead",
            "description": "团队的默认负责人角色。",
            "description_en": "Default lead role for a ministry team.",
            "sort_order": 10,
        },
        {
            "code": MinistryTeamRoleType.CODE_ASSISTANT_LEAD,
            "name": "副负责人",
            "name_en": "Assistant Lead",
            "description": "团队的副负责人同工。",
            "description_en": "Assistant lead coworker for a ministry team.",
            "sort_order": 20,
        },
        {
            "code": MinistryTeamRoleType.CODE_COORDINATOR,
            "name": "协调同工",
            "name_en": "Coordinator",
            "description": "团队的协调同工。",
            "description_en": "Coordinating coworker for a ministry team.",
            "sort_order": 30,
        },
        {
            "code": MinistryTeamRoleType.CODE_SCHEDULER,
            "name": "排班同工",
            "name_en": "Scheduler",
            "description": "团队的排班同工。",
            "description_en": "Scheduling coworker for a ministry team.",
            "sort_order": 40,
        },
        {
            "code": MinistryTeamRoleType.CODE_TRAINER,
            "name": "培训同工",
            "name_en": "Trainer",
            "description": "团队的培训同工。",
            "description_en": "Training coworker for a ministry team.",
            "sort_order": 50,
        },
        {
            "code": MinistryTeamRoleType.CODE_TECHNICAL_LEAD,
            "name": "技术负责人",
            "name_en": "Technical Lead",
            "description": "技术相关团队的技术负责人。",
            "description_en": "Technical lead for technical ministry teams.",
            "sort_order": 60,
        },
        {
            "code": MinistryTeamRoleType.CODE_EQUIPMENT_MANAGER,
            "name": "设备管理同工",
            "name_en": "Equipment Manager",
            "description": "技术相关团队的设备管理同工。",
            "description_en": "Equipment manager for technical ministry teams.",
            "sort_order": 70,
        },
        {
            "code": MinistryTeamRoleType.CODE_MEMBER_CARE,
            "name": "关怀同工",
            "name_en": "Member Care",
            "description": "团队的关怀同工。",
            "description_en": "Member-care coworker for a ministry team.",
            "sort_order": 80,
        },
        {
            "code": MinistryTeamRoleType.CODE_ADMIN,
            "name": "行政同工",
            "name_en": "Admin",
            "description": "团队的行政同工。",
            "description_en": "Administrative coworker for a ministry team.",
            "sort_order": 90,
        },
        {
            "code": ROLE_TYPE_CUSTOM_CODE,
            "name": "自定义角色",
            "name_en": "Custom Role",
            "description": "可由团队按需配置的自定义角色。",
            "description_en": "Custom role configurable by the team.",
            "sort_order": 100,
        },
    ]

    PROFILES = [
        {
            "code": MinistryTeamRoleProfile.CODE_DEFAULT_MINISTRY_UNIT,
            "name": "默认事工单位",
            "name_en": "Default Ministry Unit",
            "description": "一般事工团队的默认角色模板。",
            "description_en": "Default role template for general ministry teams.",
            "sort_order": 10,
        },
        {
            "code": MinistryTeamRoleProfile.CODE_TECHNICAL_TEAM,
            "name": "技术团队",
            "name_en": "Technical Team",
            "description": "技术相关团队的默认角色模板。",
            "description_en": "Default role template for technical teams.",
            "sort_order": 20,
        },
        {
            "code": MinistryTeamRoleProfile.CODE_WORSHIP_RELATED_TEAM,
            "name": "敬拜相关团队",
            "name_en": "Worship-related Team",
            "description": "敬拜相关团队的默认角色模板。",
            "description_en": "Default role template for worship-related teams.",
            "sort_order": 30,
        },
        {
            "code": MinistryTeamRoleProfile.CODE_PROJECT_TEAM,
            "name": "项目团队",
            "name_en": "Project Team",
            "description": "项目型团队的默认角色模板。",
            "description_en": "Default role template for project teams.",
            "sort_order": 40,
        },
        {
            "code": MinistryTeamRoleProfile.CODE_CUSTOM,
            "name": "自定义配置",
            "name_en": "Custom Profile",
            "description": "可由团队按需配置的自定义角色模板。",
            "description_en": "Custom role template configurable by the team.",
            "sort_order": 50,
        },
    ]

    # Only ``lead`` is required by default for every seeded active profile.
    # Recommended optional roles seed an is_required=False requirement row so
    # they appear as suggestions without becoming a hard readiness blocker.
    REQUIREMENTS = {
        MinistryTeamRoleProfile.CODE_DEFAULT_MINISTRY_UNIT: {
            MinistryTeamRoleType.CODE_LEAD: True,
            MinistryTeamRoleType.CODE_COORDINATOR: False,
        },
        MinistryTeamRoleProfile.CODE_TECHNICAL_TEAM: {
            MinistryTeamRoleType.CODE_LEAD: True,
            MinistryTeamRoleType.CODE_TECHNICAL_LEAD: False,
            MinistryTeamRoleType.CODE_EQUIPMENT_MANAGER: False,
            MinistryTeamRoleType.CODE_TRAINER: False,
        },
        MinistryTeamRoleProfile.CODE_WORSHIP_RELATED_TEAM: {
            MinistryTeamRoleType.CODE_LEAD: True,
            MinistryTeamRoleType.CODE_COORDINATOR: False,
            MinistryTeamRoleType.CODE_SCHEDULER: False,
            MinistryTeamRoleType.CODE_TRAINER: False,
        },
        MinistryTeamRoleProfile.CODE_PROJECT_TEAM: {
            MinistryTeamRoleType.CODE_LEAD: True,
            MinistryTeamRoleType.CODE_COORDINATOR: False,
            MinistryTeamRoleType.CODE_SCHEDULER: False,
        },
        MinistryTeamRoleProfile.CODE_CUSTOM: {
            MinistryTeamRoleType.CODE_LEAD: True,
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
            help="Write default ministry role types, profiles, and requirements.",
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
        self.stdout.write(f"Ministry structure role seed mode: {mode}")

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
        role_type = MinistryTeamRoleType.objects.filter(
            code=values["code"]
        ).first()
        return self._ensure_object(
            obj=role_type,
            model=MinistryTeamRoleType,
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
        profile = MinistryTeamRoleProfile.objects.filter(
            code=values["code"]
        ).first()
        return self._ensure_object(
            obj=profile,
            model=MinistryTeamRoleProfile,
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
            requirement = MinistryTeamRoleRequirement.objects.filter(
                profile=profile,
                role_type=role_type,
            ).first()
        return self._ensure_object(
            obj=requirement,
            model=MinistryTeamRoleRequirement,
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
            raise CommandError(f"Invalid default ministry {label}: {exc}") from exc

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
        self.stdout.write("  role assignments created: 0")
        self.stdout.write("  ministry teams updated: 0")
        self.stdout.write("  parent links changed: 0")
        self.stdout.write(f"  warnings: {self.stats['warnings']}")
