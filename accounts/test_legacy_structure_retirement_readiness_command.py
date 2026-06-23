from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.utils import timezone

from accounts.management.commands.audit_legacy_structure_retirement_readiness import (
    run_audit,
)
from accounts.models import (
    ChurchRoleAssignment,
    ChurchStructureMembership,
    ChurchStructureUnit,
    District,
    SmallGroup,
)
from events.models import ServiceEvent
from studies.models import (
    BibleStudySeries,
    BibleStudySeriesAudienceScope,
)


User = get_user_model()


class LegacyStructureRetirementReadinessCommandTests(TestCase):
    def setUp(self):
        self.today = timezone.localdate()
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
        self.other_group_unit = ChurchStructureUnit.objects.create(
            parent=self.root,
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="R5",
            name="Rainbow 5",
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
            church_structure_unit=self.group_unit,
        )

    def make_user(self, username, *, membership_unit=None):
        user = User.objects.create_user(username=username, password="pw123456")
        if membership_unit is not None:
            ChurchStructureMembership.objects.create(
                user=user,
                unit=membership_unit,
                status=ChurchStructureMembership.STATUS_ACTIVE,
                is_primary=True,
                start_date=self.today - timezone.timedelta(days=1),
            )
        return user

    def make_service_event(self):
        return ServiceEvent.objects.create(
            title="Zero Row Gathering",
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
            start_datetime=self.now + timezone.timedelta(days=7),
            status=ServiceEvent.STATUS_PUBLISHED,
        )

    def test_reports_representative_retirement_blockers(self):
        # PROFILE-SG-FIELD-RETIRE.1A removed Profile.small_group, so the audit no
        # longer carries profile-vs-membership drift counters; belonging is
        # membership-core.
        SmallGroup.objects.create(name="Unmapped Group")
        self.make_service_event()
        # ROLE-FIELD-RETIRE.1A: scoped roles are structure-native (explicit
        # structure_unit only) and no longer carry a legacy small_group field, so
        # a valid scoped assignment is not a role retirement blocker.
        ChurchRoleAssignment.objects.create(
            user=self.make_user("leader"),
            role=ChurchRoleAssignment.ROLE_GROUP_LEADER,
            scope_type=ChurchRoleAssignment.SCOPE_SMALL_GROUP,
            structure_unit=self.group_unit,
        )

        audit = run_audit(target_date=self.today, now=self.now)
        stats = audit["stats"]

        self.assertNotIn("profile_membership_unit_mismatch_group_mapping", stats)
        self.assertNotIn("profiles_with_small_group_no_active_primary_membership", stats)
        self.assertEqual(stats["small_groups_without_church_structure_unit"], 1)
        self.assertEqual(stats["bible_study_v1_sessions_checked"], 0)
        self.assertEqual(stats["bible_study_v1_pilot_records_present"], 0)
        self.assertEqual(stats["bible_study_v1_sessions_with_district_id"], 0)
        self.assertEqual(stats["bible_study_v1_sessions_with_small_group_id"], 0)
        self.assertEqual(stats["bible_study_v1_guides_checked"], 0)
        self.assertEqual(stats["bible_study_v1_worship_songs_checked"], 0)
        self.assertEqual(stats["bible_study_v1_child_rows_purge_pending"], 0)
        self.assertEqual(stats["bible_study_v1_app_runtime_retired"], 1)
        self.assertEqual(stats["bible_study_v1_purge_pending"], 0)
        self.assertEqual(stats["bible_study_v1_app_runtime_legacy_blockers"], 0)
        self.assertEqual(
            stats["service_event_zero_row_visible_active_safety_blockers"], 1
        )
        self.assertEqual(stats["role_scoped_assignments"], 1)
        self.assertEqual(stats["role_scoped_assignments_with_structure_unit"], 1)
        self.assertEqual(stats["role_scoped_assignments_missing_structure_unit"], 0)
        self.assertEqual(
            stats["role_scoped_assignments_structure_unit_retirement_blockers"], 0
        )
        self.assertEqual(stats["bible_study_legacy_retirement_blockers"], 0)

    def test_service_event_ministry_context_no_longer_counted_after_field_removal(self):
        # SERVICE-EVENT-CONTEXT.1C removed ServiceEvent.ministry_context, so the
        # ServiceEvent FK is no longer a MinistryContext retirement blocker and
        # the umbrella audit neither counts it nor lists its retired display
        # cleanup/backfill commands.
        self.make_service_event()

        audit = run_audit(target_date=self.today, now=self.now)
        stats = audit["stats"]

        self.assertNotIn("service_events_with_ministry_context", stats)
        self.assertEqual(
            stats["ministry_context_retirement_blocker_references"],
            stats["ministry_contexts_total"]
            + stats["districts_with_ministry_context"],
        )

        out = StringIO()
        call_command("audit_legacy_structure_retirement_readiness", stdout=out)
        output = out.getvalue()
        self.assertNotIn("backfill_service_event_host_language_units", output)
        self.assertNotIn("cleanup_service_event_ministry_context_labels", output)

    def test_bible_study_series_with_audience_rows_is_not_a_blocker(self):
        # BS-SERIES-FIELD-RETIRE.1A removed the legacy series scope fields, so
        # the umbrella audit no longer counts them. A series with valid audience
        # rows is fully structure-native and is not a retirement blocker.
        series = BibleStudySeries.objects.create(
            title="Structure-native Schedule",
            status=BibleStudySeries.STATUS_PUBLISHED,
        )
        BibleStudySeriesAudienceScope.objects.create(
            series=series,
            unit=self.group_unit,
        )

        audit = run_audit(target_date=self.today, now=self.now)
        stats = audit["stats"]

        self.assertEqual(stats["bible_study_series_with_audience_rows"], 1)
        self.assertEqual(stats["bible_study_series_without_audience_rows"], 0)
        self.assertEqual(stats["bible_study_active_series_without_audience_rows"], 0)
        self.assertNotIn("bible_study_series_with_legacy_scope_fields_set", stats)
        self.assertEqual(stats["bible_study_legacy_retirement_blockers"], 0)

    def test_active_bible_study_series_without_audience_rows_is_readiness_only(self):
        BibleStudySeries.objects.create(
            title="Zero-audience Schedule",
            status=BibleStudySeries.STATUS_PUBLISHED,
            is_active=True,
        )

        audit = run_audit(target_date=self.today, now=self.now)
        stats = audit["stats"]

        self.assertEqual(stats["bible_study_series_without_audience_rows"], 1)
        self.assertEqual(stats["bible_study_active_series_without_audience_rows"], 1)
        self.assertEqual(stats["bible_study_structure_native_readiness_blockers"], 1)
        self.assertEqual(stats["bible_study_legacy_retirement_blockers"], 0)

    def test_fail_on_blockers_exits_nonzero(self):
        # setUp already created a SmallGroup row, so the SmallGroup table
        # retirement-blocker reference count is nonzero and --fail-on-blockers
        # exits nonzero.
        out = StringIO()
        with self.assertRaises(CommandError):
            call_command(
                "audit_legacy_structure_retirement_readiness",
                "--fail-on-blockers",
                stdout=out,
            )

    def test_verbose_limit_caps_example_rows(self):
        for index in range(3):
            SmallGroup.objects.create(name=f"Unmapped Verbose Group {index}")

        out = StringIO()
        call_command(
            "audit_legacy_structure_retirement_readiness",
            "--verbose",
            "--limit",
            "1",
            stdout=out,
        )

        output = out.getvalue()
        self.assertIn("small_group_unmapped (3):", output)
        self.assertIn("stopped at --limit 1", output)
        self.assertIn("diagnostic/backfill commands", output)

    def test_command_is_read_only(self):
        self.make_user("readonly")
        event = self.make_service_event()

        before_event = (event.title, event.status)
        before_counts = {
            "small_groups": SmallGroup.objects.count(),
            "memberships": ChurchStructureMembership.objects.count(),
            "service_events": ServiceEvent.objects.count(),
        }

        out = StringIO()
        call_command("audit_legacy_structure_retirement_readiness", stdout=out)
        call_command(
            "audit_legacy_structure_retirement_readiness",
            "--verbose",
            "--limit",
            "2",
            stdout=StringIO(),
        )

        event.refresh_from_db()

        self.assertEqual((event.title, event.status), before_event)
        self.assertEqual(SmallGroup.objects.count(), before_counts["small_groups"])
        self.assertEqual(
            ChurchStructureMembership.objects.count(),
            before_counts["memberships"],
        )
        self.assertEqual(ServiceEvent.objects.count(), before_counts["service_events"])
        self.assertIn("data_mutated: false", out.getvalue())
        self.assertIn("apply_option_present: false", out.getvalue())
        self.assertIn("bible_study_v1_pilot_records_present: 0", out.getvalue())
        self.assertIn("bible_study_v1_app_runtime_retired: 1", out.getvalue())
        self.assertIn("bible_study_v1_purge_pending: 0", out.getvalue())
        self.assertIn("bible_study_v1_child_rows_purge_pending: 0", out.getvalue())
        self.assertIn("legacy_bible_study_v1_status", out.getvalue())
        self.assertNotIn(
            "studies.management.commands.purge_legacy_bible_study_v1_sessions",
            out.getvalue(),
        )
        self.assertIn(
            "studies.management.commands.backfill_bible_study_v2_generation_keys",
            out.getvalue(),
        )

    def test_prayer_small_group_mirror_cleanup_command_no_longer_listed(self):
        # PRAYER-MIRROR.1D removed the cleanup command together with the
        # PrayerRequest.small_group_at_post field, so it must no longer appear
        # in the diagnostic/backfill command list.
        out = StringIO()
        call_command("audit_legacy_structure_retirement_readiness", stdout=out)

        self.assertNotIn(
            "prayers.management.commands.cleanup_prayer_small_group_mirrors",
            out.getvalue(),
        )

    def test_reflection_mirror_commands_no_longer_listed(self):
        # REFLECTION-MIRROR.1H removed ReflectionComment.small_group_at_post
        # together with the reflection mirror cleanup commands and the
        # legacy-mirror backfill/recovery/shadow tooling, so none of them may
        # appear in the diagnostic/backfill command list.
        out = StringIO()
        call_command("audit_legacy_structure_retirement_readiness", stdout=out)
        output = out.getvalue()

        for command in (
            "reading.management.commands.cleanup_reflection_small_group_mirrors",
            "reading.management.commands.cleanup_reflection_nongroup_display_mirrors",
            "reading.management.commands.backfill_reflection_structure_snapshots",
            "reading.management.commands.cleanup_reflection_snapshot_blockers",
            "reading.management.commands.audit_reading_privacy_membership_readiness",
        ):
            self.assertNotIn(command, output)

        # The structure-snapshot readiness counters survive; the legacy mirror
        # counters that queried small_group_at_post are gone.
        self.assertIn("reflection_structure_snapshot_readiness_blockers", output)
        self.assertNotIn(
            "reflection_group_comments_with_small_group_at_post", output
        )
        self.assertNotIn("reflection_small_group_at_post_removal_blockers", output)

    def test_profile_small_group_commands_no_longer_listed(self):
        # PROFILE-SG-FIELD-RETIRE.1A removed Profile.small_group together with the
        # guarded cleanup command, the profile-vs-membership belonging drift audit,
        # the membership backfill that sourced from the field, and the
        # group-progress legacy shadow diagnostic, so none of them may appear in
        # the diagnostic/backfill command list.
        out = StringIO()
        call_command("audit_legacy_structure_retirement_readiness", stdout=out)
        output = out.getvalue()

        for command in (
            "accounts.management.commands.cleanup_profile_small_group",
            "accounts.management.commands.audit_structure_belonging",
            "accounts.management.commands.backfill_church_structure_memberships",
            "reading.management.commands.audit_group_progress_shadow",
        ):
            self.assertNotIn(command, output)

        # The profile-vs-membership drift counters that queried Profile.small_group
        # are gone.
        self.assertNotIn("profiles_with_small_group", output)
        self.assertNotIn("profile_small_group_removal_blockers", output)

    def test_backfill_structure_role_scopes_command_no_longer_listed(self):
        # ROLE-FIELD-RETIRE.1A retired the backfill command together with the
        # ChurchRoleAssignment.district / small_group fields (its only source),
        # so it must no longer appear in the diagnostic/backfill command list.
        out = StringIO()
        call_command("audit_legacy_structure_retirement_readiness", stdout=out)

        self.assertNotIn(
            "accounts.management.commands.backfill_structure_role_scopes",
            out.getvalue(),
        )


class LegacyStructureRetirementReadinessV1RemovedStateTests(TestCase):
    def setUp(self):
        self.now = timezone.now()
        self.root = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_ROOT,
            code="CHURCH",
            name="Whole Church",
        )

    def test_v1_removed_state_is_not_data_or_runtime_blocker(self):
        audit = run_audit(now=self.now)
        stats = audit["stats"]

        self.assertEqual(stats["bible_study_v1_app_runtime_retired"], 1)
        self.assertEqual(stats["bible_study_v1_app_runtime_legacy_blockers"], 0)
        self.assertEqual(stats["bible_study_v1_purge_pending"], 0)
        self.assertEqual(stats["bible_study_v1_sessions_checked"], 0)
        self.assertEqual(stats["bible_study_v1_sessions_with_district_id"], 0)
        self.assertEqual(stats["bible_study_v1_sessions_with_small_group_id"], 0)
        self.assertEqual(stats["bible_study_v1_child_rows_purge_pending"], 0)
        self.assertEqual(stats["bible_study_active_series_without_audience_rows"], 0)
        self.assertEqual(stats["bible_study_v2_meetings_without_audience_rows"], 0)
        self.assertEqual(stats["bible_study_normal_meetings_missing_generation_key"], 0)
        self.assertEqual(stats["bible_study_legacy_retirement_blockers"], 0)

    def test_fail_on_blockers_no_longer_reports_v1_purge_pending(self):
        SmallGroup.objects.create(name="Remaining Row")

        out = StringIO()
        with self.assertRaises(CommandError) as context:
            call_command(
                "audit_legacy_structure_retirement_readiness",
                "--fail-on-blockers",
                stdout=out,
            )

        self.assertNotIn("bible_study_legacy_retirement_blockers", str(context.exception))
        self.assertIn("bible_study_v1_purge_pending: 0", out.getvalue())
        self.assertIn("bible_study_v1_app_runtime_legacy_blockers: 0", out.getvalue())
