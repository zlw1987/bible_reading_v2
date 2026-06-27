from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounts.models import ServingReadinessPolicy, ServingReadinessRequirement


class Command(BaseCommand):
    help = (
        "Seed/maintain the default SVCA serving-readiness policy and its "
        "requirement rows. Defaults to dry-run; pass --apply to write. The "
        "policy is warning-only and advisory: it does not grant permissions, "
        "does not create member records, and does not create assignments. No "
        "rows are deleted."
    )

    POLICY = {
        "code": "svca_default_formal_serving",
        "name": "SVCA 正式服事默认资格",
        "name_en": "SVCA Default Formal Serving Readiness",
        "description": (
            "SVCA 默认的正式服事预备政策：信仰宣言已签署/豁免/无需，且有受洗或"
            "受洗认可记录。仅作提醒，不阻止任何指派。"
        ),
        "description_en": (
            "SVCA default formal-serving readiness: Faith Statement signed/"
            "waived/not required, plus a baptism or recognized-baptism record. "
            "Warning-only; it does not block any assignment."
        ),
        "is_default": True,
        "is_active": True,
        "sort_order": 10,
    }

    REQUIREMENTS = [
        {
            "requirement_type": ServingReadinessRequirement.REQUIREMENT_FAITH_STATEMENT,
            "accepted_statuses": "signed,waived,not_required",
            "severity": ServingReadinessRequirement.SEVERITY_REQUIRED,
            "label": "信仰宣言",
            "label_en": "Faith Statement",
            "message": "信仰宣言尚未签署或确认。",
            "message_en": "Faith Statement is not signed or confirmed.",
            "sort_order": 10,
        },
        {
            "requirement_type": ServingReadinessRequirement.REQUIREMENT_BAPTISM,
            "accepted_statuses": "baptized,recognized,waived,not_required",
            "severity": ServingReadinessRequirement.SEVERITY_REQUIRED,
            "label": "受洗",
            "label_en": "Baptism",
            "message": "尚未有受洗或受洗认可记录。",
            "message_en": "No baptism or recognized baptism record.",
            "sort_order": 20,
        },
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
            help="Write the default serving-readiness policy and requirements.",
        )

    def handle(self, *args, **options):
        if options["dry_run"] and options["apply"]:
            raise CommandError("Use either --dry-run or --apply, not both.")

        self.apply = options["apply"]
        self.stats = {
            "policies_created": 0,
            "policies_updated": 0,
            "policies_skipped": 0,
            "requirements_created": 0,
            "requirements_updated": 0,
            "requirements_skipped": 0,
        }

        mode = "APPLY" if self.apply else "DRY RUN"
        self.stdout.write(f"Serving readiness policy seed mode: {mode}")

        if self.apply:
            with transaction.atomic():
                self._run()
        else:
            self._run()

        self._write_summary()

    def _run(self):
        policy = self._ensure_policy(self.POLICY)
        for values in self.REQUIREMENTS:
            self._ensure_requirement(policy, values)

    def _ensure_policy(self, values):
        policy = ServingReadinessPolicy.objects.filter(code=values["code"]).first()
        return self._ensure_object(
            obj=policy,
            model=ServingReadinessPolicy,
            lookup={"code": values["code"]},
            values=values,
            fields=[
                "name",
                "name_en",
                "description",
                "description_en",
                "is_default",
                "is_active",
                "sort_order",
            ],
            label=f"policy {values['code']}",
            created_key="policies_created",
            updated_key="policies_updated",
            skipped_key="policies_skipped",
        )

    def _ensure_requirement(self, policy, values):
        requirement_values = {
            **values,
            "policy": policy,
            "is_active": True,
        }
        if not self.apply and policy.pk is None:
            requirement = None
        else:
            requirement = ServingReadinessRequirement.objects.filter(
                policy=policy,
                requirement_type=values["requirement_type"],
            ).first()
        return self._ensure_object(
            obj=requirement,
            model=ServingReadinessRequirement,
            lookup={"policy": policy, "requirement_type": values["requirement_type"]},
            values=requirement_values,
            fields=[
                "accepted_statuses",
                "severity",
                "label",
                "label_en",
                "message",
                "message_en",
                "is_active",
                "sort_order",
            ],
            label=f"requirement {policy.code}/{values['requirement_type']}",
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
        write_values = {key: values[key] for key in fields}

        if obj is None:
            self.stats[created_key] += 1
            if not self.apply:
                self.stdout.write(f"Would create {label}")
                return model(**{**lookup, **write_values})

            obj = model(**{**lookup, **write_values})
            self._save_object(obj, label)
            self.stdout.write(f"Created {label}")
            return obj

        changed_fields = [
            field_name
            for field_name in fields
            if getattr(obj, field_name) != values[field_name]
        ]
        if not changed_fields:
            self.stats[skipped_key] += 1
            return obj

        self.stats[updated_key] += 1
        if not self.apply:
            self.stdout.write(
                f"Would update {label}: {', '.join(changed_fields)}"
            )
            return obj

        for field_name in changed_fields:
            setattr(obj, field_name, values[field_name])
        self._save_object(obj, label)
        self.stdout.write(f"Updated {label}: {', '.join(changed_fields)}")
        return obj

    def _save_object(self, obj, label):
        try:
            obj.full_clean()
            obj.save()
        except ValidationError as exc:
            raise CommandError(
                f"Invalid default serving readiness {label}: {exc}"
            ) from exc

    def _write_summary(self):
        prefix = "" if self.apply else "would "
        self.stdout.write("Summary:")
        self.stdout.write(
            f"  policies {prefix}created: {self.stats['policies_created']}"
        )
        self.stdout.write(
            f"  policies {prefix}updated: {self.stats['policies_updated']}"
        )
        self.stdout.write(
            f"  policies skipped: {self.stats['policies_skipped']}"
        )
        self.stdout.write(
            f"  requirements {prefix}created: {self.stats['requirements_created']}"
        )
        self.stdout.write(
            f"  requirements {prefix}updated: {self.stats['requirements_updated']}"
        )
        self.stdout.write(
            f"  requirements skipped: {self.stats['requirements_skipped']}"
        )
        self.stdout.write("  member records created: 0")
        self.stdout.write("  assignments created: 0")
