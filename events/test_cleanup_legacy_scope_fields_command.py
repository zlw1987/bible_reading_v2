from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.utils import timezone

from accounts.management.commands.audit_legacy_structure_retirement_readiness import (
    run_audit as run_legacy_retirement_audit,
)
from accounts.models import (
    ChurchStructureMembership,
    ChurchStructureUnit,
    District,
    MinistryContext,
    SmallGroup,
)
from ministry.models import MinistryTeam

from events.models import (
    ServiceEvent,
    ServiceEventAudienceScope,
    ServiceEventRequiredTeam,
)


User = get_user_model()


class CleanupServiceEventLegacyScopeFieldsCommandTests(TestCase):
    def setUp(self):
        self.today = timezone.localdate()
        self.future_time = timezone.now() + timezone.timedelta(days=3)
        self.creator = User.objects.create_user(
            username="event_creator",
            password="pw123456",
        )
        self.member = User.objects.create_user(
            username="event_member",
            password="pw123456",
        )
        self.root = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_ROOT,
            code="CHURCH",
            name="Whole Church",
        )
        self.ministry_unit = ChurchStructureUnit.objects.create(
            parent=self.root,
            unit_type=ChurchStructureUnit.UNIT_MINISTRY_CONTEXT,
            code="CM",
            name="Chinese Ministry",
        )
        self.district_unit = ChurchStructureUnit.objects.create(
            parent=self.ministry_unit,
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
        self.ministry_context = MinistryContext.objects.create(
            code="CM",
            name="Chinese Ministry",
            church_structure_unit=self.ministry_unit,
        )
        self.district = District.objects.create(
            name="North",
            ministry_context=self.ministry_context,
            church_structure_unit=self.district_unit,
        )
        self.group = SmallGroup.objects.create(
            name="Rainbow 4",
            district=self.district,
            church_structure_unit=self.group_unit,
        )
        self.member.profile.small_group = self.group
        self.member.profile.save()
        ChurchStructureMembership.objects.create(
            user=self.member,
            unit=self.group_unit,
            status=ChurchStructureMembership.STATUS_ACTIVE,
            is_primary=True,
            start_date=self.today - timezone.timedelta(days=1),
        )

    def make_event(self, **overrides):
        data = {
            "title": "Legacy Scoped Gathering",
            "title_en": "Legacy Scoped Gathering",
            "event_type": ServiceEvent.EVENT_SUNDAY_SERVICE,
            "start_datetime": self.future_time,
            "location": "Sanctuary",
            "scope_type": ServiceEvent.SCOPE_SMALL_GROUP,
            "small_group": self.group,
            "status": ServiceEvent.STATUS_PUBLISHED,
            "created_by": self.creator,
        }
        data.update(overrides)
        return ServiceEvent.objects.create(**data)

    def add_audience(self, event, unit=None):
        return ServiceEventAudienceScope.objects.create(
            service_event=event,
            unit=unit or self.group_unit,
        )

    def run_command(self, *args):
        out = StringIO()
        call_command(
            "cleanup_service_event_legacy_scope_fields",
            *args,
            stdout=out,
        )
        return out.getvalue()

    def test_dry_run_safe_event_reports_would_clear_and_writes_nothing(self):
        event = self.make_event()
        self.add_audience(event)

        output = self.run_command()

        event.refresh_from_db()
        self.assertEqual(event.scope_type, ServiceEvent.SCOPE_SMALL_GROUP)
        self.assertEqual(event.small_group_id, self.group.id)
        self.assertIn("mode: dry-run", output)
        self.assertIn("candidates_with_legacy_fields: 1", output)
        self.assertIn("would_clear_count: 1", output)
        self.assertIn("data_mutated: false", output)
        self.assertIn("runtime_mutated: false", output)
        self.assertIn("schema_mutated: false", output)

    def test_apply_without_confirmation_fails_and_mutates_nothing(self):
        event = self.make_event()
        self.add_audience(event)

        with self.assertRaises(CommandError):
            self.run_command("--apply")

        event.refresh_from_db()
        self.assertEqual(event.scope_type, ServiceEvent.SCOPE_SMALL_GROUP)
        self.assertEqual(event.small_group_id, self.group.id)

    def test_confirmation_without_apply_remains_dry_run_and_mutates_nothing(self):
        event = self.make_event()
        self.add_audience(event)

        output = self.run_command("--confirm-service-event-legacy-scope-cleanup")

        event.refresh_from_db()
        self.assertEqual(event.scope_type, ServiceEvent.SCOPE_SMALL_GROUP)
        self.assertEqual(event.small_group_id, self.group.id)
        self.assertIn("mode: dry-run", output)
        self.assertIn("apply_option_present: false", output)
        self.assertIn("confirmation_option_present: true", output)
        self.assertIn("data_mutated: false", output)

    def test_apply_with_confirmation_clears_only_safe_candidate_rows(self):
        safe = self.make_event(title="Safe")
        self.add_audience(safe)
        blocked = self.make_event(title="Blocked")
        clear = self.make_event(
            title="Already Clear",
            scope_type=ServiceEvent.SCOPE_GLOBAL,
            small_group=None,
        )
        self.add_audience(clear)

        output = self.run_command(
            "--apply",
            "--confirm-service-event-legacy-scope-cleanup",
        )

        safe.refresh_from_db()
        blocked.refresh_from_db()
        clear.refresh_from_db()
        self.assertEqual(safe.scope_type, ServiceEvent.SCOPE_GLOBAL)
        self.assertIsNone(safe.district_id)
        self.assertIsNone(safe.small_group_id)
        self.assertEqual(blocked.scope_type, ServiceEvent.SCOPE_SMALL_GROUP)
        self.assertEqual(blocked.small_group_id, self.group.id)
        self.assertEqual(clear.scope_type, ServiceEvent.SCOPE_GLOBAL)
        self.assertIsNone(clear.small_group_id)
        self.assertIn("mode: apply", output)
        self.assertIn("candidates_with_legacy_fields: 2", output)
        self.assertIn("already_clear_count: 1", output)
        self.assertIn("cleared_count: 1", output)
        self.assertIn("skipped_zero_row_blockers: 1", output)
        self.assertIn("remaining_blockers_after_operation: 1", output)
        self.assertIn("data_mutated: true", output)

    def test_zero_audience_row_candidate_is_blocked_and_preserved(self):
        event = self.make_event()

        output = self.run_command("--verbose")

        event.refresh_from_db()
        self.assertEqual(event.scope_type, ServiceEvent.SCOPE_SMALL_GROUP)
        self.assertEqual(event.small_group_id, self.group.id)
        self.assertIn("skipped_zero_row_blockers: 1", output)
        self.assertIn("decision: blocked", output)
        self.assertIn("audience_row_count: 0", output)

    def test_already_clear_rows_are_ignored(self):
        event = self.make_event(
            scope_type=ServiceEvent.SCOPE_GLOBAL,
            small_group=None,
        )

        output = self.run_command("--verbose")

        event.refresh_from_db()
        self.assertEqual(event.scope_type, ServiceEvent.SCOPE_GLOBAL)
        self.assertIsNone(event.small_group_id)
        self.assertIn("already_clear_count: 1", output)
        self.assertIn("would_clear_count: 0", output)
        self.assertIn("decision: already_clear", output)

    def test_apply_preserves_unrelated_service_event_and_related_data(self):
        rotation_team = MinistryTeam.objects.create(name="Rotation Team")
        required_team = MinistryTeam.objects.create(name="Required Team")
        event = self.make_event(
            title="Preserved",
            scope_type=ServiceEvent.SCOPE_DISTRICT,
            district=self.district,
            small_group=None,
            ministry_context=self.ministry_context,
            rotation_anchor_team=rotation_team,
        )
        audience = self.add_audience(event, self.district_unit)
        event.required_teams.add(required_team)
        before = {
            "title": event.title,
            "title_en": event.title_en,
            "start_datetime": event.start_datetime,
            "status": event.status,
            "created_by_id": event.created_by_id,
            "ministry_context_id": event.ministry_context_id,
            "rotation_anchor_team_id": event.rotation_anchor_team_id,
            "required_team_ids": list(event.required_teams.values_list("id", flat=True)),
            "audience_count": ServiceEventAudienceScope.objects.count(),
        }

        self.run_command("--apply", "--confirm-service-event-legacy-scope-cleanup")

        event.refresh_from_db()
        self.assertEqual(event.scope_type, ServiceEvent.SCOPE_GLOBAL)
        self.assertIsNone(event.district_id)
        self.assertIsNone(event.small_group_id)
        self.assertEqual(event.title, before["title"])
        self.assertEqual(event.title_en, before["title_en"])
        self.assertEqual(event.start_datetime, before["start_datetime"])
        self.assertEqual(event.status, before["status"])
        self.assertEqual(event.created_by_id, before["created_by_id"])
        self.assertEqual(event.ministry_context_id, before["ministry_context_id"])
        self.assertEqual(
            event.rotation_anchor_team_id,
            before["rotation_anchor_team_id"],
        )
        self.assertEqual(
            list(event.required_teams.values_list("id", flat=True)),
            before["required_team_ids"],
        )
        self.assertEqual(
            ServiceEventAudienceScope.objects.count(),
            before["audience_count"],
        )
        self.assertTrue(
            ServiceEventAudienceScope.objects.filter(
                id=audience.id,
                service_event=event,
                unit=self.district_unit,
            ).exists()
        )
        self.assertTrue(
            ServiceEventRequiredTeam.objects.filter(
                service_event=event,
                ministry_team=required_team,
            ).exists()
        )

    def test_idempotency_after_apply_reports_zero_would_clear_rows(self):
        event = self.make_event()
        self.add_audience(event)
        self.run_command("--apply", "--confirm-service-event-legacy-scope-cleanup")

        output = self.run_command("--verbose")

        event.refresh_from_db()
        self.assertEqual(event.scope_type, ServiceEvent.SCOPE_GLOBAL)
        self.assertIsNone(event.small_group_id)
        self.assertIn("already_clear_count: 1", output)
        self.assertIn("would_clear_count: 0", output)
        self.assertIn("remaining_blockers_after_operation: 0", output)
        self.assertIn("decision: already_clear", output)

    def test_runtime_visibility_is_unchanged_when_audience_rows_control_visibility(self):
        event = self.make_event()
        self.add_audience(event)

        self.assertTrue(event.can_be_seen_by(self.member))
        self.run_command("--apply", "--confirm-service-event-legacy-scope-cleanup")
        event.refresh_from_db()

        self.assertTrue(event.can_be_seen_by(self.member))

    def test_audit_alignment_after_apply_reports_no_service_event_legacy_blockers(self):
        event = self.make_event()
        self.add_audience(event)

        self.run_command("--apply", "--confirm-service-event-legacy-scope-cleanup")
        audit = run_legacy_retirement_audit(
            target_date=self.today,
            now=timezone.now(),
        )
        stats = audit["stats"]

        self.assertEqual(stats["service_events_with_audience_rows"], 1)
        self.assertEqual(stats["service_events_without_audience_rows"], 0)
        self.assertEqual(stats["service_events_with_any_legacy_scope_field_set"], 0)
        self.assertEqual(
            stats["service_event_legacy_scope_field_retirement_blockers"],
            0,
        )
