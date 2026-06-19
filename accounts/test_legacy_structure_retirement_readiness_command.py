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
    BibleStudySession,
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
            district=self.district,
            church_structure_unit=self.group_unit,
        )

    def make_user(self, username, *, small_group=None, membership_unit=None):
        user = User.objects.create_user(username=username, password="pw123456")
        if small_group is not None:
            user.profile.small_group = small_group
            user.profile.save()
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
            scope_type=ServiceEvent.SCOPE_GLOBAL,
            status=ServiceEvent.STATUS_PUBLISHED,
        )

    def make_v1_session(self):
        series = BibleStudySeries.objects.create(title="Legacy Schedule")
        return BibleStudySession.objects.create(
            series=series,
            title="Legacy Session",
            study_datetime=self.now + timezone.timedelta(days=3),
            scope_type=BibleStudySession.SCOPE_SMALL_GROUP,
            small_group=self.group,
            status=BibleStudySession.STATUS_PUBLISHED,
        )

    def test_reports_representative_retirement_blockers(self):
        self.make_user(
            "mismatch",
            small_group=self.group,
            membership_unit=self.other_group_unit,
        )
        unmapped_group = SmallGroup.objects.create(name="Unmapped Group")
        self.make_user("missing_membership", small_group=unmapped_group)
        self.make_service_event()
        self.make_v1_session()
        ChurchRoleAssignment.objects.create(
            user=self.make_user("leader"),
            role=ChurchRoleAssignment.ROLE_GROUP_LEADER,
            scope_type=ChurchRoleAssignment.SCOPE_SMALL_GROUP,
            small_group=self.group,
            structure_unit=self.group_unit,
        )

        audit = run_audit(target_date=self.today, now=self.now)
        stats = audit["stats"]

        self.assertEqual(stats["profile_membership_unit_mismatch_group_mapping"], 1)
        self.assertEqual(stats["profiles_with_small_group_no_active_primary_membership"], 1)
        self.assertEqual(stats["small_groups_without_church_structure_unit"], 1)
        self.assertEqual(stats["bible_study_v1_sessions_checked"], 1)
        self.assertEqual(stats["bible_study_v1_pilot_records_present"], 1)
        self.assertEqual(stats["bible_study_v1_app_runtime_retired"], 1)
        self.assertEqual(stats["bible_study_v1_purge_pending"], 1)
        self.assertEqual(stats["bible_study_v1_app_runtime_legacy_blockers"], 0)
        self.assertEqual(
            stats["service_event_zero_row_visible_active_safety_blockers"], 1
        )
        self.assertEqual(
            stats["role_assignments_with_legacy_small_group_populated"], 1
        )
        self.assertGreater(stats["bible_study_legacy_retirement_blockers"], 0)
        self.assertGreater(stats["role_legacy_field_retirement_blockers"], 0)

    def test_bible_study_series_legacy_scope_fields_remain_retirement_blockers(self):
        series = BibleStudySeries.objects.create(
            title="Legacy-scoped Schedule",
            status=BibleStudySeries.STATUS_PUBLISHED,
            scope_type=BibleStudySeries.SCOPE_SMALL_GROUP,
            small_group=self.group,
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
        self.assertEqual(stats["bible_study_series_with_legacy_scope_fields_set"], 1)
        self.assertEqual(stats["bible_study_legacy_retirement_blockers"], 1)

    def test_fail_on_blockers_exits_nonzero(self):
        self.make_user("blocked", small_group=self.group)

        out = StringIO()
        with self.assertRaises(CommandError):
            call_command(
                "audit_legacy_structure_retirement_readiness",
                "--fail-on-blockers",
                stdout=out,
            )

    def test_verbose_limit_caps_example_rows(self):
        for index in range(3):
            user = self.make_user(f"blocked_{index}", small_group=self.group)
            user.church_structure_memberships.all().delete()

        out = StringIO()
        call_command(
            "audit_legacy_structure_retirement_readiness",
            "--verbose",
            "--limit",
            "1",
            stdout=out,
        )

        output = out.getvalue()
        self.assertIn("profile_no_active_primary_membership (3):", output)
        self.assertIn("stopped at --limit 1", output)
        self.assertIn("diagnostic/backfill commands", output)

    def test_command_is_read_only(self):
        user = self.make_user("readonly", small_group=self.group)
        event = self.make_service_event()
        session = self.make_v1_session()

        before_profile_group = user.profile.small_group_id
        before_event = (event.scope_type, event.district_id, event.small_group_id)
        before_session = (session.scope_type, session.district_id, session.small_group_id)
        before_counts = {
            "small_groups": SmallGroup.objects.count(),
            "memberships": ChurchStructureMembership.objects.count(),
            "service_events": ServiceEvent.objects.count(),
            "sessions": BibleStudySession.objects.count(),
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

        user.profile.refresh_from_db()
        event.refresh_from_db()
        session.refresh_from_db()

        self.assertEqual(user.profile.small_group_id, before_profile_group)
        self.assertEqual(
            (event.scope_type, event.district_id, event.small_group_id),
            before_event,
        )
        self.assertEqual(
            (session.scope_type, session.district_id, session.small_group_id),
            before_session,
        )
        self.assertEqual(SmallGroup.objects.count(), before_counts["small_groups"])
        self.assertEqual(
            ChurchStructureMembership.objects.count(),
            before_counts["memberships"],
        )
        self.assertEqual(ServiceEvent.objects.count(), before_counts["service_events"])
        self.assertEqual(BibleStudySession.objects.count(), before_counts["sessions"])
        self.assertIn("data_mutated: false", out.getvalue())
        self.assertIn("apply_option_present: false", out.getvalue())
        self.assertIn("bible_study_v1_pilot_records_present: 1", out.getvalue())
        self.assertIn("bible_study_v1_app_runtime_retired: 1", out.getvalue())
        self.assertIn("bible_study_v1_purge_pending: 1", out.getvalue())
        self.assertIn(
            "studies.management.commands.purge_legacy_bible_study_v1_sessions",
            out.getvalue(),
        )
        self.assertIn(
            "studies.management.commands.backfill_bible_study_v2_generation_keys",
            out.getvalue(),
        )


class LegacyStructureRetirementReadinessV1PurgePendingTests(TestCase):
    def setUp(self):
        self.now = timezone.now()
        self.root = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_ROOT,
            code="CHURCH",
            name="Whole Church",
        )

    def make_v1_only_purge_pending_session(self):
        series = BibleStudySeries.objects.create(
            title="Legacy Schedule With Audience",
            status=BibleStudySeries.STATUS_PUBLISHED,
        )
        BibleStudySeriesAudienceScope.objects.create(
            series=series,
            unit=self.root,
        )
        return BibleStudySession.objects.create(
            series=series,
            title="Legacy Global Session",
            study_datetime=self.now + timezone.timedelta(days=3),
            scope_type=BibleStudySession.SCOPE_GLOBAL,
            status=BibleStudySession.STATUS_PUBLISHED,
        )

    def test_v1_purge_pending_counts_as_data_retirement_blocker_not_runtime_blocker(self):
        self.make_v1_only_purge_pending_session()

        audit = run_audit(now=self.now)
        stats = audit["stats"]

        self.assertEqual(stats["bible_study_v1_app_runtime_retired"], 1)
        self.assertEqual(stats["bible_study_v1_app_runtime_legacy_blockers"], 0)
        self.assertEqual(stats["bible_study_v1_purge_pending"], 1)
        self.assertEqual(stats["bible_study_active_series_without_audience_rows"], 0)
        self.assertEqual(stats["bible_study_series_with_legacy_scope_fields_set"], 0)
        self.assertEqual(stats["bible_study_v2_meetings_with_small_group_mirror"], 0)
        self.assertEqual(stats["bible_study_v2_meetings_without_audience_rows"], 0)
        self.assertEqual(stats["bible_study_v2_meeting_small_group_mirror_mismatches"], 0)
        self.assertEqual(stats["bible_study_normal_meetings_missing_generation_key"], 0)
        self.assertEqual(stats["bible_study_legacy_retirement_blockers"], 1)

    def test_fail_on_blockers_exits_nonzero_for_v1_purge_pending_data_blocker(self):
        self.make_v1_only_purge_pending_session()

        out = StringIO()
        with self.assertRaises(CommandError) as context:
            call_command(
                "audit_legacy_structure_retirement_readiness",
                "--fail-on-blockers",
                stdout=out,
            )

        self.assertIn("bible_study_legacy_retirement_blockers=1", str(context.exception))
        self.assertIn("bible_study_v1_purge_pending: 1", out.getvalue())
        self.assertIn("bible_study_v1_app_runtime_legacy_blockers: 0", out.getvalue())
