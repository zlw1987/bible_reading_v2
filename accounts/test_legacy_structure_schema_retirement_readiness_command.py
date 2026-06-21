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
            status=ServiceEvent.STATUS_PUBLISHED,
        )

    def make_group_prayer(self, *, title="Group Prayer"):
        owner = self.make_user(f"prayer_owner_{title}")
        return PrayerRequest.objects.create(
            user=owner,
            title=title,
            body="prayer body text",
            visibility=PrayerRequest.VISIBILITY_GROUP,
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
        )
        assignment = ChurchRoleAssignment.objects.create(
            user=user,
            role=ChurchRoleAssignment.ROLE_GROUP_LEADER,
            scope_type=ChurchRoleAssignment.SCOPE_SMALL_GROUP,
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
            "event_scope": (event.title, event.status),
            "series_scope": (series.title, series.status),
            "role_scope": (
                assignment.scope_type,
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
        self.assertEqual((event.title, event.status), before_values["event_scope"])
        self.assertEqual(
            (series.title, series.status),
            before_values["series_scope"],
        )
        self.assertEqual(
            (
                assignment.scope_type,
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
        self.assertIn("ServiceEvent.scope_type (removed)", output)
        self.assertIn("BibleStudyMeeting.small_group", output)
        self.assertIn("ReflectionComment.small_group_at_post", output)
        self.assertIn("PrayerRequest.small_group_at_post", output)
        self.assertIn("SmallGroup model/table", output)

    def test_service_event_legacy_scope_fields_are_historical_after_field_removal(self):
        # SE-FIELD-RETIRE.1A removed ServiceEvent.scope_type / district /
        # small_group after SE-RETIRE.1B retired the zero-row runtime fallback
        # and local/dev audit confirmed zero populated legacy scope fields. Only
        # immutable historical migrations still name them, so the candidates are
        # now classified as historical-only with no active schema blocker, and
        # none of them has a queryable data counter.
        audit = run_audit()
        for name in (
            "ServiceEvent.scope_type (removed)",
            "ServiceEvent.district (removed)",
            "ServiceEvent.small_group (removed)",
        ):
            candidate = _candidate(audit, name)
            self.assertEqual(candidate["live_runtime_references"], ())
            self.assertEqual(candidate["app_write_references"], ())
            self.assertEqual(candidate["app_read_references"], ())
            self.assertEqual(candidate["admin_references"], ())
            self.assertEqual(candidate["template_display_references"], ())
            self.assertEqual(candidate["diagnostic_cleanup_references"], ())
            self.assertEqual(candidate["data_blocker_count"], 0)
            self.assertEqual(candidate["schema_removal_status"], STATUS_HISTORICAL)
            self.assertFalse(
                candidate["schema_removal_status"].startswith("blocked_by_")
            )

        self.assertNotIn("service_event_scope_type", audit["data_counts"])
        self.assertNotIn("service_event_district", audit["data_counts"])
        self.assertNotIn("service_event_small_group", audit["data_counts"])

    def test_service_event_ministry_context_is_historical_after_field_removal(self):
        # SERVICE-EVENT-CONTEXT.1C removed ServiceEvent.ministry_context (the
        # legacy Host / Language display FK). Only immutable historical
        # migrations still name it, so the candidate is classified as
        # historical-only with no active schema blocker, no live references, and
        # no queryable data counter. Host / Language display now uses
        # ServiceEvent.host_language_unit plus the audience-derived fallback.
        audit = run_audit()
        candidate = _candidate(audit, "ServiceEvent.ministry_context (removed)")

        self.assertEqual(candidate["live_runtime_references"], ())
        self.assertEqual(candidate["app_write_references"], ())
        self.assertEqual(candidate["app_read_references"], ())
        self.assertEqual(candidate["admin_references"], ())
        self.assertEqual(candidate["template_display_references"], ())
        self.assertEqual(candidate["diagnostic_cleanup_references"], ())
        self.assertEqual(candidate["data_blocker_count"], 0)
        self.assertEqual(candidate["schema_removal_status"], STATUS_HISTORICAL)
        self.assertFalse(candidate["schema_removal_status"].startswith("blocked_by_"))

        self.assertNotIn("service_event_ministry_context", audit["data_counts"])

        # host_language_unit remains the structure-native display field and is
        # not a legacy-removal target.
        host_language = _candidate(audit, "ServiceEvent.host_language_unit")
        self.assertEqual(
            host_language["suggested_removal_phase"],
            "not in legacy removal sequence",
        )

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

    def test_prayer_request_mirror_is_historical_after_field_removal(self):
        # PRAYER-MIRROR.1D removed the PrayerRequest.small_group_at_post model
        # field after 1A-1C retired its write/display/admin surfaces and the
        # guarded cleanup cleared stored data. Only immutable historical
        # migrations still name it, so the candidate is now classified as
        # historical-only with no active schema blocker.
        audit = run_audit()
        candidate = _candidate(audit, "PrayerRequest.small_group_at_post (removed)")

        self.assertEqual(candidate["live_runtime_references"], ())
        self.assertEqual(candidate["app_write_references"], ())
        self.assertEqual(candidate["app_read_references"], ())
        self.assertEqual(candidate["admin_references"], ())
        self.assertEqual(candidate["template_display_references"], ())
        self.assertEqual(candidate["diagnostic_cleanup_references"], ())
        self.assertEqual(candidate["data_blocker_count"], 0)
        self.assertEqual(candidate["schema_removal_status"], STATUS_HISTORICAL)
        self.assertFalse(candidate["schema_removal_status"].startswith("blocked_by_"))
        # The removed field no longer has a queryable data counter.
        self.assertNotIn(
            "prayer_request_small_group_at_post", audit["data_counts"]
        )

    def test_role_legacy_fields_are_historical_after_field_removal(self):
        # ROLE-FIELD-RETIRE.1A removed ChurchRoleAssignment.district /
        # small_group after ROLE-RETIRE.1B retired the runtime fallback and
        # local/dev audit confirmed zero populated legacy role values. Only
        # immutable historical migrations still name them, so the candidates are
        # now classified as historical-only with no active schema blocker, and
        # neither field has a queryable data counter.
        audit = run_audit()
        for name in (
            "ChurchRoleAssignment.district (removed)",
            "ChurchRoleAssignment.small_group (removed)",
        ):
            candidate = _candidate(audit, name)
            self.assertEqual(candidate["live_runtime_references"], ())
            self.assertEqual(candidate["app_write_references"], ())
            self.assertEqual(candidate["app_read_references"], ())
            self.assertEqual(candidate["admin_references"], ())
            self.assertEqual(candidate["template_display_references"], ())
            self.assertEqual(candidate["diagnostic_cleanup_references"], ())
            self.assertEqual(candidate["data_blocker_count"], 0)
            self.assertEqual(candidate["schema_removal_status"], STATUS_HISTORICAL)
            self.assertFalse(
                candidate["schema_removal_status"].startswith("blocked_by_")
            )

        self.assertNotIn("role_district", audit["data_counts"])
        self.assertNotIn("role_small_group", audit["data_counts"])

    def test_bible_study_series_scope_fields_are_historical_after_field_removal(self):
        # BS-SERIES-FIELD-RETIRE.1A removed BibleStudySeries.scope_type /
        # ministry_context / district / small_group after BS-SERIES-SCOPE.1A/1B
        # stopped normal app writes and cleared stored values. Only immutable
        # historical migrations still name them, so the candidates are now
        # historical-only with no active schema blocker, and none has a queryable
        # data counter. Normal generation is structure-unit-native.
        audit = run_audit()
        for name in (
            "BibleStudySeries.scope_type (removed)",
            "BibleStudySeries.ministry_context (removed)",
            "BibleStudySeries.district (removed)",
            "BibleStudySeries.small_group (removed)",
        ):
            candidate = _candidate(audit, name)
            self.assertEqual(candidate["live_runtime_references"], ())
            self.assertEqual(candidate["app_write_references"], ())
            self.assertEqual(candidate["app_read_references"], ())
            self.assertEqual(candidate["admin_references"], ())
            self.assertEqual(candidate["template_display_references"], ())
            self.assertEqual(candidate["diagnostic_cleanup_references"], ())
            self.assertEqual(candidate["data_blocker_count"], 0)
            self.assertEqual(candidate["schema_removal_status"], STATUS_HISTORICAL)
            self.assertFalse(
                candidate["schema_removal_status"].startswith("blocked_by_")
            )

        self.assertNotIn("series_scope_type", audit["data_counts"])
        self.assertNotIn("series_ministry_context", audit["data_counts"])
        self.assertNotIn("series_district", audit["data_counts"])
        self.assertNotIn("series_small_group", audit["data_counts"])

    def test_reflection_mirror_is_historical_after_field_removal(self):
        # REFLECTION-MIRROR.1H removed the ReflectionComment.small_group_at_post
        # model field (migration comments/0007) after 1D-1G retired its
        # write/display/admin surfaces and the guarded cleanup cleared stored
        # data. The reflection mirror cleanup commands and the legacy-mirror
        # backfill/recovery/shadow tooling were retired with the field. Only
        # immutable historical migrations still name it, so the candidate is now
        # classified as historical-only with no active schema blocker.
        audit = run_audit()
        candidate = _candidate(audit, "ReflectionComment.small_group_at_post (removed)")

        self.assertEqual(candidate["live_runtime_references"], ())
        self.assertEqual(candidate["app_write_references"], ())
        self.assertEqual(candidate["app_read_references"], ())
        self.assertEqual(candidate["admin_references"], ())
        self.assertEqual(candidate["template_display_references"], ())
        self.assertEqual(candidate["diagnostic_cleanup_references"], ())
        self.assertEqual(candidate["data_blocker_count"], 0)
        self.assertEqual(candidate["schema_removal_status"], STATUS_HISTORICAL)
        self.assertFalse(candidate["schema_removal_status"].startswith("blocked_by_"))
        # The removed field no longer has a queryable data counter.
        self.assertNotIn("reflection_small_group_at_post", audit["data_counts"])

    def test_command_does_not_mutate_prayer_request(self):
        prayer = self.make_group_prayer(title="READONLY_PRAYER")
        before = (
            PrayerRequest.objects.count(),
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
                prayer.structure_unit_at_post_id,
            ),
            before,
        )

    def test_verbose_output_does_not_print_prayer_free_text(self):
        self.make_group_prayer(title="SECRET_PRAYER_TITLE_DO_NOT_PRINT")

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
