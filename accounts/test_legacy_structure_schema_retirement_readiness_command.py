from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.utils import timezone

from accounts.management.commands.audit_legacy_structure_schema_retirement_readiness import (
    Command,
    STATUS_DIAGNOSTIC,
    STATUS_HISTORICAL,
    STATUS_RUNTIME,
    STATUS_WRITE,
    run_audit,
)
from accounts.models import (
    ChurchRoleAssignment,
    ChurchStructureUnit,
    District,
    SmallGroup,
)
from events.models import ServiceEvent
from prayers.models import PrayerRequest
from studies.models import BibleStudySeries


User = get_user_model()


def _candidate(audit, name):
    return next(
        candidate
        for candidate in audit["candidates"]
        if candidate["candidate_name"] == name
    )


class LegacyStructureSchemaRetirementReadinessCommandTests(TestCase):
    def setUp(self):
        self.now = timezone.now()
        self.root = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_ROOT,
            code="CHURCH",
            name="Whole Church",
        )
        self.group_unit = ChurchStructureUnit.objects.create(
            parent=self.root,
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="R4",
            name="Rainbow 4",
        )
        self.district_unit = ChurchStructureUnit.objects.create(
            parent=self.root,
            unit_type=ChurchStructureUnit.UNIT_DISTRICT,
            code="D1",
            name="District 1",
        )
        self.district = District.objects.create(
            name="District 1",
            church_structure_unit=self.district_unit,
        )
        self.group = SmallGroup.objects.create(
            name="Rainbow 4",
            district=self.district,
            church_structure_unit=self.group_unit,
        )

    def make_user(self, username, *, small_group=None):
        user = User.objects.create_user(username=username, password="pw123456")
        if small_group is not None:
            user.profile.small_group = small_group
            user.profile.save(update_fields=["small_group"])
        return user

    def make_event(self, *, title="Schema Prep Event"):
        return ServiceEvent.objects.create(
            title=title,
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
            start_datetime=self.now + timezone.timedelta(days=7),
            scope_type=ServiceEvent.SCOPE_GLOBAL,
            status=ServiceEvent.STATUS_PUBLISHED,
        )

    def make_group_prayer(self, *, title="Group Prayer", small_group=None):
        owner = self.make_user(f"prayer_owner_{title}")
        return PrayerRequest.objects.create(
            user=owner,
            title=title,
            body="prayer body text",
            visibility=PrayerRequest.VISIBILITY_GROUP,
            small_group_at_post=small_group,
            structure_unit_at_post=self.group_unit,
        )

    def test_command_has_no_apply_option(self):
        parser = Command().create_parser(
            "manage.py",
            "audit_legacy_structure_schema_retirement_readiness",
        )
        option_strings = {
            option
            for action in parser._actions
            for option in getattr(action, "option_strings", [])
        }

        self.assertNotIn("--apply", option_strings)

    def test_command_is_read_only(self):
        user = self.make_user("legacy_member", small_group=self.group)
        event = self.make_event(title="READONLY_SECRET_EVENT")
        series = BibleStudySeries.objects.create(
            title="READONLY_SECRET_SERIES",
            scope_type=BibleStudySeries.SCOPE_SMALL_GROUP,
            small_group=self.group,
        )
        assignment = ChurchRoleAssignment.objects.create(
            user=user,
            role=ChurchRoleAssignment.ROLE_GROUP_LEADER,
            scope_type=ChurchRoleAssignment.SCOPE_SMALL_GROUP,
            small_group=self.group,
            structure_unit=self.group_unit,
        )
        before_counts = {
            "small_groups": SmallGroup.objects.count(),
            "districts": District.objects.count(),
            "service_events": ServiceEvent.objects.count(),
            "series": BibleStudySeries.objects.count(),
            "role_assignments": ChurchRoleAssignment.objects.count(),
        }
        before_values = {
            "profile_small_group": user.profile.small_group_id,
            "event_scope": (event.scope_type, event.district_id, event.small_group_id),
            "series_scope": (
                series.scope_type,
                series.district_id,
                series.small_group_id,
            ),
            "role_scope": (
                assignment.scope_type,
                assignment.district_id,
                assignment.small_group_id,
                assignment.structure_unit_id,
            ),
        }

        out = StringIO()
        call_command("audit_legacy_structure_schema_retirement_readiness", stdout=out)
        call_command(
            "audit_legacy_structure_schema_retirement_readiness",
            "--verbose",
            "--limit",
            "1",
            stdout=StringIO(),
        )

        user.profile.refresh_from_db()
        event.refresh_from_db()
        series.refresh_from_db()
        assignment.refresh_from_db()

        self.assertEqual(SmallGroup.objects.count(), before_counts["small_groups"])
        self.assertEqual(District.objects.count(), before_counts["districts"])
        self.assertEqual(ServiceEvent.objects.count(), before_counts["service_events"])
        self.assertEqual(BibleStudySeries.objects.count(), before_counts["series"])
        self.assertEqual(
            ChurchRoleAssignment.objects.count(),
            before_counts["role_assignments"],
        )
        self.assertEqual(user.profile.small_group_id, before_values["profile_small_group"])
        self.assertEqual(
            (event.scope_type, event.district_id, event.small_group_id),
            before_values["event_scope"],
        )
        self.assertEqual(
            (series.scope_type, series.district_id, series.small_group_id),
            before_values["series_scope"],
        )
        self.assertEqual(
            (
                assignment.scope_type,
                assignment.district_id,
                assignment.small_group_id,
                assignment.structure_unit_id,
            ),
            before_values["role_scope"],
        )
        self.assertIn("data_mutated: false", out.getvalue())
        self.assertIn("schema_mutated: false", out.getvalue())
        self.assertIn("apply_option_present: false", out.getvalue())

    def test_reports_known_candidate_names(self):
        out = StringIO()
        call_command("audit_legacy_structure_schema_retirement_readiness", stdout=out)
        output = out.getvalue()

        self.assertIn("Profile.small_group", output)
        self.assertIn("ServiceEvent.scope_type", output)
        self.assertIn("BibleStudyMeeting.small_group", output)
        self.assertIn("ReflectionComment.small_group_at_post", output)
        self.assertIn("PrayerRequest.small_group_at_post", output)
        self.assertIn("SmallGroup model/table", output)

    def test_clean_no_data_field_is_not_runtime_blocker(self):
        audit = run_audit()
        candidate = _candidate(audit, "ServiceEvent.scope_type")

        self.assertEqual(candidate["data_blocker_count"], 0)
        self.assertNotEqual(candidate["schema_removal_status"], STATUS_RUNTIME)
        self.assertEqual(candidate["live_runtime_references"], ())

    def test_static_app_write_reference_blocks_schema_removal(self):
        audit = run_audit()
        candidate = _candidate(audit, "BibleStudyMeeting.anchor_unit")

        self.assertEqual(candidate["schema_removal_status"], STATUS_WRITE)
        self.assertGreater(len(candidate["app_write_references"]), 0)

    def test_diagnostic_only_references_are_separate_from_runtime_blockers(self):
        audit = run_audit()
        candidate = _candidate(audit, "Legacy diagnostic and cleanup command surfaces")

        self.assertEqual(candidate["schema_removal_status"], STATUS_DIAGNOSTIC)
        self.assertEqual(candidate["live_runtime_references"], ())

    def test_migration_history_is_distinguished_from_live_code_blockers(self):
        audit = run_audit()
        candidate = _candidate(audit, "Historical migration references for legacy fields")

        self.assertEqual(candidate["schema_removal_status"], STATUS_HISTORICAL)
        self.assertFalse(candidate["schema_removal_status"].startswith("blocked_by_"))
        self.assertEqual(candidate["app_read_references"], ())
        self.assertEqual(candidate["diagnostic_cleanup_references"], ())

    def test_fail_on_blockers_exits_nonzero_when_blockers_exist(self):
        out = StringIO()
        with self.assertRaises(CommandError) as context:
            call_command(
                "audit_legacy_structure_schema_retirement_readiness",
                "--fail-on-blockers",
                stdout=out,
            )

        self.assertIn("Legacy schema-retirement blockers present", str(context.exception))
        self.assertIn("blocked_candidate_count", out.getvalue())

    def test_verbose_output_does_not_print_private_free_text(self):
        self.make_event(title="SECRET_EVENT_TITLE_DO_NOT_PRINT")
        BibleStudySeries.objects.create(
            title="SECRET_SERIES_TITLE_DO_NOT_PRINT",
            scope_type=BibleStudySeries.SCOPE_SMALL_GROUP,
            small_group=self.group,
        )

        out = StringIO()
        call_command(
            "audit_legacy_structure_schema_retirement_readiness",
            "--verbose",
            "--limit",
            "2",
            stdout=out,
        )
        output = out.getvalue()

        self.assertIn("prints_private_free_text: false", output)
        self.assertNotIn("SECRET_EVENT_TITLE_DO_NOT_PRINT", output)
        self.assertNotIn("SECRET_SERIES_TITLE_DO_NOT_PRINT", output)

    def test_current_expected_fixture_has_no_ordinary_member_visibility_blockers(self):
        audit = run_audit()

        self.assertEqual(
            audit["stats"]["legacy_ordinary_member_visibility_blockers"],
            0,
        )

    def test_prayer_request_mirror_is_app_write_blocker(self):
        audit = run_audit()
        candidate = _candidate(audit, "PrayerRequest.small_group_at_post")

        self.assertEqual(candidate["schema_removal_status"], STATUS_WRITE)
        self.assertGreater(len(candidate["app_write_references"]), 0)
        # Ordinary group-prayer visibility is structure-native, so the legacy
        # mirror carries no live runtime authority of its own.
        self.assertEqual(candidate["live_runtime_references"], ())

    def test_prayer_request_mirror_data_counter_increments(self):
        before = run_audit()["data_counts"]["prayer_request_small_group_at_post"]

        self.make_group_prayer(title="MIRROR_FIXTURE", small_group=self.group)

        after_audit = run_audit()
        after = after_audit["data_counts"]["prayer_request_small_group_at_post"]
        candidate = _candidate(after_audit, "PrayerRequest.small_group_at_post")

        self.assertEqual(after, before + 1)
        self.assertEqual(candidate["data_blocker_count"], after)
        # A populated mirror still reports as app-write blocked, not data blocked.
        self.assertEqual(candidate["schema_removal_status"], STATUS_WRITE)

    def test_command_does_not_mutate_prayer_request(self):
        prayer = self.make_group_prayer(title="READONLY_PRAYER", small_group=self.group)
        before = (
            PrayerRequest.objects.count(),
            prayer.small_group_at_post_id,
            prayer.structure_unit_at_post_id,
        )

        call_command(
            "audit_legacy_structure_schema_retirement_readiness",
            "--verbose",
            "--limit",
            "1",
            stdout=StringIO(),
        )

        prayer.refresh_from_db()
        self.assertEqual(
            (
                PrayerRequest.objects.count(),
                prayer.small_group_at_post_id,
                prayer.structure_unit_at_post_id,
            ),
            before,
        )

    def test_verbose_output_does_not_print_prayer_free_text(self):
        self.make_group_prayer(title="SECRET_PRAYER_TITLE_DO_NOT_PRINT", small_group=self.group)

        out = StringIO()
        call_command(
            "audit_legacy_structure_schema_retirement_readiness",
            "--verbose",
            "--limit",
            "2",
            stdout=out,
        )
        output = out.getvalue()

        self.assertIn("prints_private_free_text: false", output)
        self.assertNotIn("SECRET_PRAYER_TITLE_DO_NOT_PRINT", output)
        self.assertNotIn("prayer body text", output)
