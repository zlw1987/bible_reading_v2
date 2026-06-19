"""SE-CTX.1B tests for ServiceEvent Host / Language cleanup commands."""

from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.utils import timezone

from accounts.management.commands.audit_legacy_structure_retirement_readiness import (
    run_audit as run_legacy_retirement_audit,
)
from accounts.models import ChurchStructureUnit, MinistryContext
from events.models import ServiceEvent, ServiceEventAudienceScope


User = get_user_model()


class CleanupServiceEventMinistryContextLabelsCommandTests(TestCase):
    def setUp(self):
        self.today = timezone.localdate()
        self.future_time = timezone.now() + timezone.timedelta(days=3)
        self.creator = User.objects.create_user(
            username="ctx_creator",
            password="pw123456",
        )

        self.root = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_ROOT,
            code="CHURCH",
            name="Whole Church",
        )
        self.cm_unit = ChurchStructureUnit.objects.create(
            parent=self.root,
            unit_type=ChurchStructureUnit.UNIT_MINISTRY_CONTEXT,
            code="CM",
            name="中文事工",
            name_en="Chinese Ministry",
        )
        self.em_unit = ChurchStructureUnit.objects.create(
            parent=self.root,
            unit_type=ChurchStructureUnit.UNIT_MINISTRY_CONTEXT,
            code="EM",
            name="英文事工",
            name_en="English Ministry",
        )
        self.district_unit = ChurchStructureUnit.objects.create(
            parent=self.cm_unit,
            unit_type=ChurchStructureUnit.UNIT_DISTRICT,
            code="NORTH",
            name="北区",
            name_en="North",
        )
        self.group_unit = ChurchStructureUnit.objects.create(
            parent=self.district_unit,
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="R4",
            name="彩虹四组",
            name_en="Rainbow 4",
        )
        self.cm_context = MinistryContext.objects.create(
            code="CM",
            name="中文事工",
            name_en="Chinese Ministry",
            church_structure_unit=self.cm_unit,
        )
        self.em_context = MinistryContext.objects.create(
            code="EM",
            name="英文事工",
            name_en="English Ministry",
            church_structure_unit=self.em_unit,
        )

    def make_event(self, *, ministry_context, **overrides):
        data = {
            "title": "Host Labeled Gathering",
            "title_en": "Host Labeled Gathering",
            "event_type": ServiceEvent.EVENT_SUNDAY_SERVICE,
            "start_datetime": self.future_time,
            "status": ServiceEvent.STATUS_PUBLISHED,
            "created_by": self.creator,
            "ministry_context": ministry_context,
        }
        data.update(overrides)
        return ServiceEvent.objects.create(**data)

    def add_audience(self, event, unit):
        return ServiceEventAudienceScope.objects.create(
            service_event=event,
            unit=unit,
        )

    def run_command(self, *args):
        out = StringIO()
        call_command(
            "cleanup_service_event_ministry_context_labels",
            *args,
            stdout=out,
        )
        return out.getvalue()

    def run_backfill_command(self, *args):
        out = StringIO()
        call_command(
            "backfill_service_event_host_language_units",
            *args,
            stdout=out,
        )
        return out.getvalue()

    def test_backfill_dry_run_reports_eligible_and_writes_nothing(self):
        event = self.make_event(ministry_context=self.cm_context)
        self.add_audience(event, self.root)

        output = self.run_backfill_command()

        event.refresh_from_db()
        self.assertIsNone(event.host_language_unit_id)
        self.assertEqual(event.ministry_context_id, self.cm_context.id)
        self.assertIn("mode: dry-run", output)
        self.assertIn("candidate_events: 1", output)
        self.assertIn("eligible_to_backfill: 1", output)
        self.assertIn("would_update_count: 1", output)
        self.assertIn("data_mutated: false", output)
        self.assertIn("runtime_mutated: false", output)
        self.assertIn("schema_mutated: false", output)

    def test_backfill_apply_without_confirmation_fails_and_mutates_nothing(self):
        event = self.make_event(ministry_context=self.cm_context)

        with self.assertRaises(CommandError):
            self.run_backfill_command("--apply")

        event.refresh_from_db()
        self.assertIsNone(event.host_language_unit_id)
        self.assertEqual(event.ministry_context_id, self.cm_context.id)

    def test_backfill_apply_sets_host_language_unit_from_valid_mapping(self):
        event = self.make_event(ministry_context=self.cm_context)
        self.add_audience(event, self.root)

        output = self.run_backfill_command(
            "--apply",
            "--confirm-service-event-host-language-unit-backfill",
        )

        event.refresh_from_db()
        self.assertEqual(event.host_language_unit_id, self.cm_unit.id)
        self.assertEqual(event.ministry_context_id, self.cm_context.id)
        self.assertIn("mode: apply", output)
        self.assertIn("eligible_to_backfill: 1", output)
        self.assertIn("updated_count: 1", output)
        self.assertIn("data_mutated: true", output)
        self.assertEqual(ServiceEventAudienceScope.objects.count(), 1)
        self.assertTrue(MinistryContext.objects.filter(id=self.cm_context.id).exists())

    def test_backfill_skips_missing_inactive_and_wrong_type_mappings(self):
        missing_context = MinistryContext.objects.create(
            code="UNMAPPED",
            name="Unmapped",
            church_structure_unit=None,
        )
        inactive_context = MinistryContext.objects.create(
            code="INACTIVE",
            name="Inactive",
            church_structure_unit=self.cm_unit,
        )
        self.cm_unit.is_active = False
        self.cm_unit.save()
        wrong_type_context = MinistryContext.objects.create(
            code="WRONG",
            name="Wrong Type",
            church_structure_unit=self.district_unit,
        )
        missing_event = self.make_event(ministry_context=missing_context)
        inactive_event = self.make_event(
            ministry_context=inactive_context,
            title="Inactive Host",
        )
        wrong_type_event = self.make_event(
            ministry_context=wrong_type_context,
            title="Wrong Host",
        )

        output = self.run_backfill_command(
            "--apply",
            "--confirm-service-event-host-language-unit-backfill",
        )

        for event in (missing_event, inactive_event, wrong_type_event):
            event.refresh_from_db()
            self.assertIsNone(event.host_language_unit_id)
        self.assertIn("skipped_missing_mapped_context_unit: 1", output)
        self.assertIn("skipped_inactive_mapped_context_unit: 1", output)
        self.assertIn("skipped_wrong_mapped_context_unit_type: 1", output)
        self.assertIn("updated_count: 0", output)

    def test_backfill_verbose_does_not_print_sensitive_text(self):
        event = self.make_event(
            ministry_context=self.cm_context,
            description="SECRET private description body",
            description_en="SECRET private english body",
        )
        self.add_audience(event, self.root)

        output = self.run_backfill_command("--verbose", "--limit", "20")

        self.assertNotIn("SECRET", output)
        self.assertIn("decision: would_update", output)

    def test_dry_run_reports_eligible_and_writes_nothing(self):
        event = self.make_event(ministry_context=self.cm_context)
        self.add_audience(event, self.cm_unit)

        output = self.run_command()

        event.refresh_from_db()
        self.assertEqual(event.ministry_context_id, self.cm_context.id)
        self.assertIn("mode: dry-run", output)
        self.assertIn("links_present: 1", output)
        self.assertIn("eligible_to_clear: 1", output)
        self.assertIn("would_clear_count: 1", output)
        self.assertIn("data_mutated: false", output)
        self.assertIn("runtime_mutated: false", output)
        self.assertIn("schema_mutated: false", output)

    def test_apply_without_confirmation_fails_and_mutates_nothing(self):
        event = self.make_event(ministry_context=self.cm_context)
        self.add_audience(event, self.cm_unit)

        with self.assertRaises(CommandError):
            self.run_command("--apply")

        event.refresh_from_db()
        self.assertEqual(event.ministry_context_id, self.cm_context.id)

    def test_confirmation_without_apply_remains_dry_run(self):
        event = self.make_event(ministry_context=self.cm_context)
        self.add_audience(event, self.cm_unit)

        output = self.run_command(
            "--confirm-service-event-ministry-context-label-cleanup"
        )

        event.refresh_from_db()
        self.assertEqual(event.ministry_context_id, self.cm_context.id)
        self.assertIn("mode: dry-run", output)
        self.assertIn("apply_option_present: false", output)
        self.assertIn("confirmation_option_present: true", output)
        self.assertIn("data_mutated: false", output)

    def test_apply_with_confirmation_clears_eligible_link(self):
        event = self.make_event(ministry_context=self.cm_context)
        self.add_audience(event, self.group_unit)  # derives CM via ancestry

        output = self.run_command(
            "--apply",
            "--confirm-service-event-ministry-context-label-cleanup",
        )

        event.refresh_from_db()
        self.assertIsNone(event.ministry_context_id)
        self.assertIn("mode: apply", output)
        self.assertIn("eligible_to_clear: 1", output)
        self.assertIn("cleared_count: 1", output)
        self.assertIn(
            "remaining_service_event_ministry_context_links_after_operation: 0",
            output,
        )
        self.assertIn("data_mutated: true", output)
        # MinistryContext rows and audience rows are preserved.
        self.assertTrue(MinistryContext.objects.filter(id=self.cm_context.id).exists())
        self.assertEqual(ServiceEventAudienceScope.objects.count(), 1)

    def test_apply_clears_root_audience_when_host_language_unit_matches(self):
        event = self.make_event(
            ministry_context=self.cm_context,
            host_language_unit=self.cm_unit,
        )
        self.add_audience(event, self.root)

        output = self.run_command(
            "--apply",
            "--confirm-service-event-ministry-context-label-cleanup",
        )

        event.refresh_from_db()
        self.assertIsNone(event.ministry_context_id)
        self.assertEqual(event.host_language_unit_id, self.cm_unit.id)
        self.assertIn("events_with_host_language_unit: 1", output)
        self.assertIn("eligible_to_clear: 1", output)
        self.assertIn("cleared_count: 1", output)
        self.assertEqual(ServiceEventAudienceScope.objects.count(), 1)

    def test_zero_audience_event_is_skipped(self):
        event = self.make_event(ministry_context=self.cm_context)

        output = self.run_command(
            "--apply",
            "--confirm-service-event-ministry-context-label-cleanup",
        )

        event.refresh_from_db()
        self.assertEqual(event.ministry_context_id, self.cm_context.id)
        self.assertIn("skipped_zero_audience_rows: 1", output)
        self.assertIn("cleared_count: 0", output)

    def test_missing_mapped_context_unit_is_skipped(self):
        context = MinistryContext.objects.create(
            code="UNMAPPED",
            name="Unmapped",
            church_structure_unit=None,
        )
        event = self.make_event(ministry_context=context)
        self.add_audience(event, self.cm_unit)

        output = self.run_command(
            "--apply",
            "--confirm-service-event-ministry-context-label-cleanup",
        )

        event.refresh_from_db()
        self.assertEqual(event.ministry_context_id, context.id)
        self.assertIn("skipped_missing_mapped_context_unit: 1", output)
        self.assertIn("cleared_count: 0", output)

    def test_inactive_mapped_unit_is_skipped(self):
        self.cm_unit.is_active = False
        self.cm_unit.save()
        event = self.make_event(ministry_context=self.cm_context)
        self.add_audience(event, self.em_unit)

        output = self.run_command(
            "--apply",
            "--confirm-service-event-ministry-context-label-cleanup",
        )

        event.refresh_from_db()
        self.assertEqual(event.ministry_context_id, self.cm_context.id)
        self.assertIn("skipped_inactive_mapped_context_unit: 1", output)
        self.assertIn("cleared_count: 0", output)

    def test_wrong_type_mapped_unit_is_skipped(self):
        context = MinistryContext.objects.create(
            code="WRONG",
            name="Wrong Type",
            church_structure_unit=self.district_unit,  # not a ministry_context unit
        )
        event = self.make_event(ministry_context=context)
        self.add_audience(event, self.district_unit)

        output = self.run_command(
            "--apply",
            "--confirm-service-event-ministry-context-label-cleanup",
        )

        event.refresh_from_db()
        self.assertEqual(event.ministry_context_id, context.id)
        self.assertIn("skipped_wrong_mapped_context_unit_type: 1", output)
        self.assertIn("cleared_count: 0", output)

    def test_no_derived_context_is_skipped(self):
        event = self.make_event(ministry_context=self.cm_context)
        self.add_audience(event, self.root)  # root has no ministry-context ancestor

        output = self.run_command(
            "--apply",
            "--confirm-service-event-ministry-context-label-cleanup",
        )

        event.refresh_from_db()
        self.assertEqual(event.ministry_context_id, self.cm_context.id)
        self.assertIn("skipped_no_derived_context: 1", output)
        self.assertIn("cleared_count: 0", output)

    def test_context_mismatch_is_skipped(self):
        event = self.make_event(ministry_context=self.cm_context)
        self.add_audience(event, self.em_unit)  # derives EM, mapped is CM

        output = self.run_command(
            "--apply",
            "--confirm-service-event-ministry-context-label-cleanup",
        )

        event.refresh_from_db()
        self.assertEqual(event.ministry_context_id, self.cm_context.id)
        self.assertIn("skipped_context_mismatch: 1", output)
        self.assertIn("cleared_count: 0", output)

    def test_host_language_unit_mismatch_is_skipped(self):
        event = self.make_event(
            ministry_context=self.cm_context,
            host_language_unit=self.em_unit,
        )
        self.add_audience(event, self.root)

        output = self.run_command(
            "--apply",
            "--confirm-service-event-ministry-context-label-cleanup",
        )

        event.refresh_from_db()
        self.assertEqual(event.ministry_context_id, self.cm_context.id)
        self.assertEqual(event.host_language_unit_id, self.em_unit.id)
        self.assertIn("skipped_context_mismatch: 1", output)
        self.assertIn("cleared_count: 0", output)

    def test_multiple_derived_contexts_is_skipped(self):
        event = self.make_event(ministry_context=self.cm_context)
        self.add_audience(event, self.cm_unit)
        self.add_audience(event, self.em_unit)

        output = self.run_command(
            "--apply",
            "--confirm-service-event-ministry-context-label-cleanup",
        )

        event.refresh_from_db()
        self.assertEqual(event.ministry_context_id, self.cm_context.id)
        self.assertIn("skipped_multiple_derived_contexts: 1", output)
        self.assertIn("cleared_count: 0", output)

    def test_verbose_does_not_print_sensitive_text(self):
        event = self.make_event(
            ministry_context=self.cm_context,
            description="SECRET private description body",
            description_en="SECRET private english body",
        )
        self.add_audience(event, self.cm_unit)

        output = self.run_command("--verbose", "--limit", "20")

        self.assertNotIn("SECRET", output)
        self.assertIn("decision: would_clear", output)

    def test_idempotency_second_dry_run_after_apply_reports_zero(self):
        event = self.make_event(ministry_context=self.cm_context)
        self.add_audience(event, self.cm_unit)
        self.run_command(
            "--apply",
            "--confirm-service-event-ministry-context-label-cleanup",
        )

        output = self.run_command()

        event.refresh_from_db()
        self.assertIsNone(event.ministry_context_id)
        self.assertIn("links_present: 0", output)
        self.assertIn("would_clear_count: 0", output)
        self.assertIn("eligible_to_clear: 0", output)

    def test_audit_alignment_after_apply(self):
        event = self.make_event(ministry_context=self.cm_context)
        self.add_audience(event, self.cm_unit)

        before = run_legacy_retirement_audit(
            target_date=self.today,
            now=timezone.now(),
        )["stats"]
        self.assertEqual(before["service_events_with_ministry_context"], 1)

        self.run_command(
            "--apply",
            "--confirm-service-event-ministry-context-label-cleanup",
        )

        after = run_legacy_retirement_audit(
            target_date=self.today,
            now=timezone.now(),
        )["stats"]
        self.assertEqual(after["service_events_with_ministry_context"], 0)
        self.assertEqual(
            before["ministry_context_retirement_blocker_references"]
            - after["ministry_context_retirement_blocker_references"],
            1,
        )

    def test_backfill_then_cleanup_reduces_audit_for_root_audience_event(self):
        event = self.make_event(ministry_context=self.cm_context)
        self.add_audience(event, self.root)

        before = run_legacy_retirement_audit(
            target_date=self.today,
            now=timezone.now(),
        )["stats"]
        self.assertEqual(before["service_events_with_ministry_context"], 1)

        self.run_backfill_command(
            "--apply",
            "--confirm-service-event-host-language-unit-backfill",
        )
        self.run_command(
            "--apply",
            "--confirm-service-event-ministry-context-label-cleanup",
        )

        event.refresh_from_db()
        self.assertIsNone(event.ministry_context_id)
        self.assertEqual(event.host_language_unit_id, self.cm_unit.id)
        after = run_legacy_retirement_audit(
            target_date=self.today,
            now=timezone.now(),
        )["stats"]
        self.assertEqual(after["service_events_with_ministry_context"], 0)
        self.assertEqual(
            before["ministry_context_retirement_blocker_references"]
            - after["ministry_context_retirement_blocker_references"],
            1,
        )
