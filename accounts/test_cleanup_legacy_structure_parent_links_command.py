from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.utils import timezone

from accounts.management.commands.audit_legacy_structure_retirement_readiness import (
    run_audit as run_legacy_retirement_audit,
)
from accounts.management.commands.cleanup_legacy_structure_parent_links import (
    apply_cleanup,
    field_is_nullable,
    run_audit,
)
from accounts.models import (
    ChurchStructureUnit,
    District,
    MinistryContext,
    SmallGroup,
)
from events.models import ServiceEvent


User = get_user_model()


class CleanupLegacyStructureParentLinksCommandTests(TestCase):
    def setUp(self):
        self.now = timezone.now()
        self.future_time = self.now + timezone.timedelta(days=7)
        self.creator = User.objects.create_user(
            username="creator", password="pw-creator"
        )

        # --- structure hierarchy: root > ministry context > district > group
        self.root = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_ROOT,
            code="CHURCH",
            name="Whole Church",
        )
        self.context_unit = ChurchStructureUnit.objects.create(
            parent=self.root,
            unit_type=ChurchStructureUnit.UNIT_MINISTRY_CONTEXT,
            code="CM",
            name="Chinese Ministry",
        )
        self.district_unit = ChurchStructureUnit.objects.create(
            parent=self.context_unit,
            unit_type=ChurchStructureUnit.UNIT_DISTRICT,
            code="NORTH",
            name="North",
        )
        self.group_unit = ChurchStructureUnit.objects.create(
            parent=self.district_unit,
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="R4",
            name="Rainbow 4",
        )

        # --- legacy objects mapped to the matching units (eligible chain)
        self.context = MinistryContext.objects.create(
            code="CM",
            name="Chinese Ministry",
            church_structure_unit=self.context_unit,
        )
        self.district = District.objects.create(
            name="North",
            ministry_context=self.context,
            church_structure_unit=self.district_unit,
        )
        self.group = SmallGroup.objects.create(
            name="Rainbow 4",
            district=self.district,
            church_structure_unit=self.group_unit,
        )

    # ----------------------------------------------------------------- helpers
    def make_event(self, **overrides):
        data = {
            "title": "Ministry Context Labeled Event",
            "event_type": ServiceEvent.EVENT_SUNDAY_SERVICE,
            "start_datetime": self.future_time,
            "status": ServiceEvent.STATUS_PUBLISHED,
            "created_by": self.creator,
        }
        data.update(overrides)
        return ServiceEvent.objects.create(**data)

    def run_dry_run(self, **kwargs):
        out = StringIO()
        call_command(
            "cleanup_legacy_structure_parent_links", stdout=out, **kwargs
        )
        return out.getvalue()

    # ----------------------------------------------------- 1. dry-run reports SG
    def test_dry_run_reports_eligible_small_group_district_and_does_not_mutate(self):
        stats, _lines = run_audit()
        self.assertEqual(stats["small_group_district_links_present"], 1)
        self.assertEqual(stats["small_group_district_links_eligible"], 1)
        self.assertEqual(stats["small_group_district_links_would_clear"], 1)
        self.assertEqual(stats["small_group_district_links_cleared"], 0)

        self.group.refresh_from_db()
        self.assertEqual(self.group.district_id, self.district.id)

    # ----------------------------------------------- 2. apply w/o confirmation
    def test_apply_without_confirmation_refuses_and_does_not_mutate(self):
        with self.assertRaises(CommandError):
            call_command("cleanup_legacy_structure_parent_links", apply=True)

        self.group.refresh_from_db()
        self.district.refresh_from_db()
        self.assertEqual(self.group.district_id, self.district.id)
        self.assertEqual(self.district.ministry_context_id, self.context.id)

    # ----------------------------------- 3. confirmation w/o apply stays dry-run
    def test_confirmation_without_apply_stays_dry_run(self):
        output = self.run_dry_run(
            confirm_legacy_structure_parent_link_cleanup=True
        )
        self.assertIn("mode: dry-run", output)
        self.assertIn("data_mutated: false", output)

        self.group.refresh_from_db()
        self.assertEqual(self.group.district_id, self.district.id)

    # ------------------------------------------- 4. apply + confirmation clears
    def test_apply_with_confirmation_clears_eligible_small_group_district(self):
        stats, _lines = apply_cleanup()
        self.assertEqual(stats["small_group_district_links_cleared"], 1)
        self.assertEqual(
            stats["remaining_small_group_district_links_after_operation"], 0
        )

        self.group.refresh_from_db()
        self.assertIsNone(self.group.district_id)
        # mapping bridge and rows are untouched
        self.group.church_structure_unit.refresh_from_db()
        self.assertEqual(
            self.group.church_structure_unit_id, self.group_unit.id
        )
        self.assertTrue(SmallGroup.objects.filter(id=self.group.id).exists())
        self.assertTrue(District.objects.filter(id=self.district.id).exists())

    # -------------------------------------------------- 5. parent mismatch skip
    def test_parent_mismatch_is_skipped(self):
        # Re-point the group's unit under a different district unit so the
        # hierarchy no longer proves the legacy district relationship.
        other_district_unit = ChurchStructureUnit.objects.create(
            parent=self.context_unit,
            unit_type=ChurchStructureUnit.UNIT_DISTRICT,
            code="SOUTH",
            name="South",
        )
        self.group_unit.parent = other_district_unit
        self.group_unit.save(update_fields=["parent"])

        stats, _lines = run_audit()
        self.assertEqual(stats["small_group_district_links_eligible"], 0)
        self.assertEqual(stats["skipped_parent_mismatch"], 1)

        stats, _lines = apply_cleanup()
        self.assertEqual(stats["small_group_district_links_cleared"], 0)
        self.group.refresh_from_db()
        self.assertEqual(self.group.district_id, self.district.id)

    # ---------------------------------------------------- 6. missing mapping
    def test_missing_mapping_is_skipped(self):
        self.group.church_structure_unit = None
        self.group.save(update_fields=["church_structure_unit"])

        stats, _lines = run_audit()
        self.assertEqual(stats["small_group_district_links_eligible"], 0)
        self.assertEqual(stats["skipped_missing_mapping"], 1)

        apply_cleanup()
        self.group.refresh_from_db()
        self.assertEqual(self.group.district_id, self.district.id)

    # ------------------------------------------------- 7. inactive mapped unit
    def test_inactive_mapped_unit_is_skipped(self):
        self.district_unit.is_active = False
        self.district_unit.save(update_fields=["is_active"])

        stats, _lines = run_audit()
        # both the group->district (parent inactive) and district->context
        # (child inactive) links become inactive_unit skips.
        self.assertEqual(stats["small_group_district_links_eligible"], 0)
        self.assertEqual(stats["district_ministry_context_links_eligible"], 0)
        self.assertEqual(stats["skipped_inactive_unit"], 2)

        apply_cleanup()
        self.group.refresh_from_db()
        self.district.refresh_from_db()
        self.assertEqual(self.group.district_id, self.district.id)
        self.assertEqual(self.district.ministry_context_id, self.context.id)

    # --------------------------------------------------- 8. wrong unit type
    def test_wrong_unit_type_is_skipped(self):
        # District maps to a unit whose type is not "district".
        self.district_unit.unit_type = ChurchStructureUnit.UNIT_CUSTOM
        self.district_unit.save(update_fields=["unit_type"])

        stats, _lines = run_audit()
        self.assertEqual(stats["small_group_district_links_eligible"], 0)
        self.assertEqual(stats["district_ministry_context_links_eligible"], 0)
        self.assertEqual(stats["skipped_wrong_unit_type"], 2)

        apply_cleanup()
        self.group.refresh_from_db()
        self.assertEqual(self.group.district_id, self.district.id)

    # ------------------------------------------------- 9. nullability detection
    def test_target_fields_are_nullable(self):
        self.assertTrue(field_is_nullable(SmallGroup, "district"))
        self.assertTrue(field_is_nullable(District, "ministry_context"))
        self.assertTrue(field_is_nullable(ServiceEvent, "ministry_context"))

        stats, _lines = run_audit()
        self.assertEqual(stats["skipped_not_nullable"], 0)

    # ----------------------------------------- 10. dry-run reports District->MC
    def test_dry_run_reports_eligible_district_ministry_context(self):
        stats, _lines = run_audit()
        self.assertEqual(stats["district_ministry_context_links_present"], 1)
        self.assertEqual(stats["district_ministry_context_links_eligible"], 1)
        self.assertEqual(stats["district_ministry_context_links_would_clear"], 1)
        self.assertEqual(stats["district_ministry_context_links_cleared"], 0)

        self.district.refresh_from_db()
        self.assertEqual(self.district.ministry_context_id, self.context.id)

    # --------------------------------- 11. apply clears District->MC link
    def test_apply_clears_eligible_district_ministry_context(self):
        stats, _lines = apply_cleanup()
        self.assertEqual(stats["district_ministry_context_links_cleared"], 1)
        self.assertEqual(
            stats["remaining_district_ministry_context_links_after_operation"], 0
        )

        self.district.refresh_from_db()
        self.assertIsNone(self.district.ministry_context_id)
        self.assertTrue(
            MinistryContext.objects.filter(id=self.context.id).exists()
        )

    # ------------------------- 12. ServiceEvent ministry_context conservatively
    def test_service_event_ministry_context_is_skipped_not_cleared(self):
        event = self.make_event(ministry_context=self.context)

        stats, _lines = run_audit()
        self.assertEqual(
            stats["service_event_ministry_context_links_present"], 1
        )
        self.assertEqual(
            stats["service_event_ministry_context_links_eligible"], 0
        )
        self.assertEqual(
            stats["service_event_ministry_context_links_would_clear"], 0
        )
        self.assertEqual(
            stats["skipped_service_event_uncertain_display_context"], 1
        )

        stats, _lines = apply_cleanup()
        self.assertEqual(
            stats["service_event_ministry_context_links_cleared"], 0
        )
        self.assertEqual(
            stats["remaining_service_event_ministry_context_links_after_operation"],
            1,
        )
        event.refresh_from_db()
        self.assertEqual(event.ministry_context_id, self.context.id)

    # ----------------------------------------- 13. no sensitive free-text print
    def test_verbose_does_not_print_sensitive_free_text(self):
        self.make_event(
            ministry_context=self.context,
            title="Secret Event Title",
            description="PRIVATE_BODY_SHOULD_NOT_APPEAR",
            description_en="PRIVATE_BODY_EN_SHOULD_NOT_APPEAR",
        )
        output = self.run_dry_run(verbose=True)
        self.assertNotIn("PRIVATE_BODY_SHOULD_NOT_APPEAR", output)
        self.assertNotIn("PRIVATE_BODY_EN_SHOULD_NOT_APPEAR", output)
        # operational title metadata is allowed
        self.assertIn("Secret Event Title", output)

    # --------------------------------------------------------- 14. idempotency
    def test_second_dry_run_after_apply_reports_zero_would_clear(self):
        apply_cleanup()

        stats, _lines = run_audit()
        self.assertEqual(stats["small_group_district_links_present"], 0)
        self.assertEqual(stats["small_group_district_links_would_clear"], 0)
        self.assertEqual(stats["district_ministry_context_links_present"], 0)
        self.assertEqual(stats["district_ministry_context_links_would_clear"], 0)

    # ------------------------------------- 15. retirement audit reflects clears
    def test_retirement_audit_counts_drop_after_apply(self):
        before = run_legacy_retirement_audit()["stats"]
        self.assertEqual(before["small_groups_with_district"], 1)
        self.assertEqual(before["districts_with_ministry_context"], 1)

        apply_cleanup()

        after = run_legacy_retirement_audit()["stats"]
        self.assertEqual(after["small_groups_with_district"], 0)
        self.assertEqual(after["districts_with_ministry_context"], 0)

    # ------------------------------- extra: apply via call_command end-to-end
    def test_call_command_apply_with_confirmation_clears_and_reports(self):
        output = StringIO()
        call_command(
            "cleanup_legacy_structure_parent_links",
            apply=True,
            confirm_legacy_structure_parent_link_cleanup=True,
            stdout=output,
        )
        text = output.getvalue()
        self.assertIn("mode: apply", text)
        self.assertIn("data_mutated: true", text)
        self.assertIn("schema_mutated: false", text)
        self.assertIn("runtime_mutated: false", text)

        self.group.refresh_from_db()
        self.district.refresh_from_db()
        self.assertIsNone(self.group.district_id)
        self.assertIsNone(self.district.ministry_context_id)
