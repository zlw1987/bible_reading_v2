"""Focused MO-S.6D-PROFILE-SETUP.1A reset-command tests."""

import re
from datetime import date, datetime, time
from io import StringIO
from unittest.mock import patch

from django.contrib.admin.models import ADDITION, LogEntry
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from accounts.models import ChurchStructureMembership, ChurchStructureUnit
from ministry.models import (
    MinistryTeam,
    MinistryTeamRoleAssignment,
    MinistryTeamRoleType,
    TeamAssignment,
    TeamAssignmentMember,
    TeamMembership,
)
from notifications.models import Notification
from reading.models import ReadingPlan
from studies.models import BibleStudyLesson, BibleStudyMeeting, BibleStudySeries

from .models import (
    ServiceEvent,
    ServiceEventAudienceScope,
    ServiceEventPlannerAssignment,
    ServiceEventRequiredTeam,
    ServiceProfile,
)
from .service_profile_readiness import build_expected_sundays
from .service_profile_setup import (
    PROFILE_KEY,
    RESET_APPROVAL_CONTRACT_VERSION,
    ProfileSetupPrerequisiteError,
    _dataset_is_canonical,
    apply_reset,
    build_reset_preview,
)


User = get_user_model()


class BethanyServiceEventResetTests(TestCase):
    def setUp(self):
        self.root = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_ROOT,
            code="CHURCH",
            name="全教会",
            name_en="Whole Church",
        )
        self.campus = ChurchStructureUnit.objects.create(
            parent=self.root,
            unit_type=ChurchStructureUnit.UNIT_CAMPUS,
            code="MAIN",
            name="母堂",
            name_en="Main Campus",
        )
        self.cm = ChurchStructureUnit.objects.create(
            parent=self.campus,
            unit_type=ChurchStructureUnit.UNIT_MINISTRY_CONTEXT,
            code="CM",
            name="中文堂",
            name_en="Chinese Ministry",
        )
        self.user = User.objects.create_user(username="setup-survivor")
        self.profile = ServiceProfile.objects.create(
            key=PROFILE_KEY,
            name="Bethany 09:30 Chinese",
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
        )

    def local_datetime(self, year=2026, month=1, day=4, hour=10):
        return timezone.make_aware(
            datetime(year, month, day, hour),
            timezone.get_current_timezone(),
        )

    def make_event(self, **overrides):
        values = {
            "title": "Disposable test event",
            "event_type": ServiceEvent.EVENT_SUNDAY_SERVICE,
            "start_datetime": self.local_datetime(),
            "status": ServiceEvent.STATUS_PUBLISHED,
        }
        values.update(overrides)
        return ServiceEvent.objects.create(**values)

    def run_command(self, *args):
        out = StringIO()
        call_command("rebuild_bethany_0930_service_events", *args, stdout=out)
        return out.getvalue()

    def approval_token(self, *, today=None):
        return build_reset_preview(today=today)["approval"]["token"]

    def apply_reviewed_reset(self, *, today=None):
        return apply_reset(
            expected_reset_token=self.approval_token(today=today),
            today=today,
        )

    def assert_no_write_queries(self, queries):
        write_sql = [
            query["sql"]
            for query in queries.captured_queries
            if query["sql"].lstrip().upper().startswith(
                ("INSERT", "UPDATE", "DELETE", "REPLACE")
            )
        ]
        self.assertEqual(write_sql, [])

    def add_full_event_owned_dataset(self):
        event = self.make_event()
        ServiceEventAudienceScope.objects.create(service_event=event, unit=self.cm)
        team = MinistryTeam.objects.create(name="Lighting", name_en="Lighting")
        membership = TeamMembership.objects.create(team=team, user=self.user)
        ServiceEventRequiredTeam.objects.create(
            service_event=event,
            ministry_team=team,
        )
        ServiceEventPlannerAssignment.objects.create(
            service_event=event,
            user=self.user,
        )
        assignment = TeamAssignment.objects.create(
            service_event=event,
            ministry_team=team,
        )
        member = TeamAssignmentMember.objects.create(
            assignment=assignment,
            membership=membership,
        )
        return event, team, membership, assignment, member

    def add_linked_bible_study_meeting(self, event):
        series = BibleStudySeries.objects.create(title="Preserved series")
        lesson = BibleStudyLesson.objects.create(
            series=series,
            title="Preserved lesson",
            lesson_date=date(2026, 1, 2),
        )
        return BibleStudyMeeting.objects.create(
            lesson=lesson,
            meeting_datetime=self.local_datetime(day=2),
            service_event=event,
        )

    def test_default_command_is_zero_write_preview_with_counts_and_52_replacements(self):
        event, _team, _membership, _assignment, _member = (
            self.add_full_event_owned_dataset()
        )
        before = {
            "events": ServiceEvent.objects.count(),
            "audience": ServiceEventAudienceScope.objects.count(),
            "required": ServiceEventRequiredTeam.objects.count(),
            "planners": ServiceEventPlannerAssignment.objects.count(),
            "assignments": TeamAssignment.objects.count(),
            "members": TeamAssignmentMember.objects.count(),
        }

        with CaptureQueriesContext(connection) as queries:
            output = self.run_command()

        self.assertIn("TEST-DATA RESET PREVIEW", output)
        self.assertIn("NO DATA CHANGED", output)
        self.assertIn("service_events_deleted: 1", output)
        self.assertIn(f"id={event.pk}; local_start=", output)
        self.assertIn("events: 52 (2026-01-04 through 2026-12-27)", output)
        self.assertEqual(output.count("  create local_start="), 52)
        self.assertRegex(output, r"Reset approval token: [0-9a-f]{16}\n")
        self.assertIn("--expected-reset-token", output)
        self.assertEqual(ServiceEvent.objects.get(), event)
        self.assertEqual(
            before,
            {
                "events": ServiceEvent.objects.count(),
                "audience": ServiceEventAudienceScope.objects.count(),
                "required": ServiceEventRequiredTeam.objects.count(),
                "planners": ServiceEventPlannerAssignment.objects.count(),
                "assignments": TeamAssignment.objects.count(),
                "members": TeamAssignmentMember.objects.count(),
            },
        )
        self.assert_no_write_queries(queries)

    def test_dry_run_approval_token_is_short_deterministic_and_zero_write(self):
        self.make_event()

        first = self.run_command()
        second = self.run_command("--dry-run")
        first_token = re.search(
            r"Reset approval token: ([0-9a-f]{16})",
            first,
        ).group(1)
        second_token = re.search(
            r"Reset approval token: ([0-9a-f]{16})",
            second,
        ).group(1)

        self.assertEqual(first_token, second_token)
        self.assertEqual(len(first_token), 16)
        self.assertRegex(
            first,
            r"Approval payload SHA-256: [0-9a-f]{64}\n",
        )
        self.assertEqual(ServiceEvent.objects.count(), 1)

    def test_v2_preview_requires_active_correct_type_service_profile(self):
        event = self.make_event()
        cases = (
            ("missing", {"delete": True}),
            ("inactive", {"is_active": False}),
            ("wrong_type", {"event_type": ServiceEvent.EVENT_BIBLE_STUDY}),
        )
        for case, change in cases:
            with self.subTest(case=case):
                if change.get("delete"):
                    self.profile.delete()
                else:
                    ServiceProfile.objects.filter(pk=self.profile.pk).update(**change)
                with CaptureQueriesContext(connection) as queries:
                    with self.assertRaises(ProfileSetupPrerequisiteError):
                        build_reset_preview()
                self.assertTrue(ServiceEvent.objects.filter(pk=event.pk).exists())
                self.assert_no_write_queries(queries)

                ServiceProfile.objects.all().delete()
                self.profile = ServiceProfile.objects.create(
                    key=PROFILE_KEY,
                    name="Bethany 09:30 Chinese",
                    event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
                )

    def test_v2_fingerprint_and_approval_bind_fk_and_profile_identity(self):
        event = self.make_event(service_profile_key=PROFILE_KEY)
        before = build_reset_preview()

        ServiceEvent.objects.filter(pk=event.pk).update(service_profile=self.profile)
        after_fk = build_reset_preview()

        self.assertNotEqual(before["before"]["fingerprint"], after_fk["before"]["fingerprint"])
        self.assertNotEqual(before["approval"]["token"], after_fk["approval"]["token"])
        self.assertEqual(
            after_fk["before"]["event_rows"][0]["service_profile_id"],
            self.profile.pk,
        )
        self.assertEqual(RESET_APPROVAL_CONTRACT_VERSION, "MO-S.6D-PROFILE-SETUP.1A-FU1-v2")

    def test_v1_approval_token_cannot_authorize_v2_apply(self):
        event = self.make_event()
        with patch(
            "events.service_profile_setup.RESET_APPROVAL_CONTRACT_VERSION",
            "MO-S.6D-PROFILE-SETUP.1A-FU1-v1",
        ):
            old_token = build_reset_preview()["approval"]["token"]

        with self.assertRaisesMessage(
            ProfileSetupPrerequisiteError,
            "Reset preview changed since product-owner review",
        ):
            apply_reset(expected_reset_token=old_token)
        self.assertTrue(ServiceEvent.objects.filter(pk=event.pk).exists())

    def test_profile_row_change_after_preview_fails_closed_before_delete(self):
        event = self.make_event()
        reviewed_token = self.approval_token()
        self.profile.delete()
        self.profile = ServiceProfile.objects.create(
            key=PROFILE_KEY,
            name="Recreated reviewed profile",
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
        )

        with self.assertRaisesMessage(
            ProfileSetupPrerequisiteError,
            "Reset preview changed since product-owner review",
        ):
            apply_reset(expected_reset_token=reviewed_token)
        self.assertTrue(ServiceEvent.objects.filter(pk=event.pk).exists())

    def test_apply_requires_acknowledgement_and_reviewed_token(self):
        event = self.make_event()

        with CaptureQueriesContext(connection) as queries:
            with self.assertRaisesMessage(
                CommandError,
                "--apply requires --confirm-test-data-reset",
            ):
                self.run_command("--apply")
            with self.assertRaisesMessage(CommandError, "either --dry-run or --apply"):
                self.run_command(
                    "--dry-run",
                    "--apply",
                    "--confirm-test-data-reset",
                )
            preview = self.run_command("--confirm-test-data-reset")

            with self.assertRaisesMessage(
                CommandError,
                "--apply requires --expected-reset-token",
            ):
                self.run_command("--apply", "--confirm-test-data-reset")
            with self.assertRaisesMessage(
                CommandError,
                "exactly 16 lowercase hexadecimal characters",
            ):
                self.run_command(
                    "--apply",
                    "--confirm-test-data-reset",
                    "--expected-reset-token",
                    "NOT-A-TOKEN",
                )
            with self.assertRaisesMessage(
                CommandError,
                "Reset preview changed since product-owner review",
            ):
                self.run_command(
                    "--apply",
                    "--confirm-test-data-reset",
                    "--expected-reset-token",
                    "0000000000000000",
                )

        self.assertIn("NO DATA CHANGED", preview)
        self.assertTrue(ServiceEvent.objects.filter(pk=event.pk).exists())
        self.assert_no_write_queries(queries)

    def test_reviewed_token_becomes_stale_when_service_event_changes(self):
        event = self.make_event()
        reviewed_token = self.approval_token()
        event.title = "Changed after review"
        event.save(update_fields=["title", "updated_at"])

        with CaptureQueriesContext(connection) as queries:
            with self.assertRaisesMessage(
                CommandError,
                "Reset preview changed since product-owner review",
            ):
                self.run_command(
                    "--apply",
                    "--confirm-test-data-reset",
                    "--expected-reset-token",
                    reviewed_token,
                )

        self.assertEqual(ServiceEvent.objects.get(pk=event.pk).title, event.title)
        self.assertEqual(ServiceEvent.objects.count(), 1)
        self.assert_no_write_queries(queries)

    def test_reviewed_token_binds_resolved_audience_path_identity(self):
        event = self.make_event()
        reviewed_token = self.approval_token()
        self.campus.code = "RENAMED"
        self.campus.save(update_fields=["code", "updated_at"])
        current_token = self.approval_token()

        self.assertNotEqual(reviewed_token, current_token)
        with CaptureQueriesContext(connection) as queries:
            with self.assertRaisesMessage(
                CommandError,
                "Reset preview changed since product-owner review",
            ):
                self.run_command(
                    "--apply",
                    "--confirm-test-data-reset",
                    "--expected-reset-token",
                    reviewed_token,
                )
        self.assertTrue(ServiceEvent.objects.filter(pk=event.pk).exists())
        self.assert_no_write_queries(queries)

    def test_reviewed_token_binds_local_today_and_lifecycle_split(self):
        first = build_reset_preview(today=date(2026, 1, 4))
        second = build_reset_preview(today=date(2026, 1, 5))

        self.assertNotEqual(first["approval"]["token"], second["approval"]["token"])
        self.assertEqual(first["replacement"]["completed"], 0)
        self.assertEqual(second["replacement"]["completed"], 1)

    def test_apply_cascades_event_owned_rows_and_preserves_unrelated_domains_and_history(self):
        event, team, membership, assignment, member = self.add_full_event_owned_dataset()
        bible_meeting = self.add_linked_bible_study_meeting(event)
        structure_membership = ChurchStructureMembership.objects.create(
            user=self.user,
            unit=self.cm,
            status=ChurchStructureMembership.STATUS_ACTIVE,
            is_primary=True,
            start_date=date(2025, 1, 1),
        )
        role_type = MinistryTeamRoleType.objects.create(
            code=MinistryTeamRoleType.CODE_LEAD,
            name="Lead",
            name_en="Lead",
        )
        role = MinistryTeamRoleAssignment.objects.create(
            team=team,
            role_type=role_type,
            user=self.user,
            start_date=date(2025, 1, 1),
        )
        reading_plan = ReadingPlan.objects.create(name="Preserved reading plan")

        event_ct = ContentType.objects.get_for_model(ServiceEvent)
        log_entry = LogEntry.objects.log_action(
            user_id=self.user.pk,
            content_type_id=event_ct.pk,
            object_id=event.pk,
            object_repr=str(event),
            action_flag=ADDITION,
            change_message="historical setup evidence",
        )
        notification = Notification.objects.create(
            recipient=self.user,
            source_module="ministry",
            source_model_label="events.ServiceEvent",
            source_object_id=str(event.pk),
            notification_type="worship_team.changed",
            title="Historical notification",
            target_url="/my-serving/",
            dedupe_key="setup-test-history",
        )

        output = self.run_command(
            "--apply",
            "--confirm-test-data-reset",
            "--expected-reset-token",
            self.approval_token(),
        )

        self.assertIn(
            "TEST ServiceEvent dataset reset and canonical Bethany 09:30 series created.",
            output,
        )
        self.assertEqual(ServiceEvent.objects.count(), 52)
        self.assertEqual(ServiceEventRequiredTeam.objects.count(), 0)
        self.assertEqual(ServiceEventPlannerAssignment.objects.count(), 0)
        self.assertEqual(TeamAssignment.objects.count(), 0)
        self.assertEqual(TeamAssignmentMember.objects.count(), 0)
        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())
        self.assertTrue(ChurchStructureUnit.objects.filter(pk=self.cm.pk).exists())
        self.assertTrue(
            ChurchStructureMembership.objects.filter(pk=structure_membership.pk).exists()
        )
        self.assertTrue(MinistryTeam.objects.filter(pk=team.pk).exists())
        self.assertTrue(TeamMembership.objects.filter(pk=membership.pk).exists())
        self.assertTrue(MinistryTeamRoleAssignment.objects.filter(pk=role.pk).exists())
        self.assertTrue(ReadingPlan.objects.filter(pk=reading_plan.pk).exists())
        bible_meeting.refresh_from_db()
        self.assertIsNone(bible_meeting.service_event_id)
        self.assertTrue(LogEntry.objects.filter(pk=log_entry.pk).exists())
        self.assertTrue(Notification.objects.filter(pk=notification.pk).exists())
        self.assertFalse(TeamAssignment.objects.filter(pk=assignment.pk).exists())
        self.assertFalse(TeamAssignmentMember.objects.filter(pk=member.pk).exists())

    def test_apply_creates_exact_local_dst_safe_canonical_contract_and_ready_audit(self):
        result = self.apply_reviewed_reset(today=date(2026, 7, 1))
        events = list(ServiceEvent.objects.order_by("start_datetime", "pk"))

        self.assertEqual(result["audit"]["recommendation"], "PROFILE SETUP READY")
        self.assertEqual(len(events), 52)
        self.assertEqual(
            [timezone.localtime(event.start_datetime).date() for event in events],
            list(build_expected_sundays(2026)),
        )
        self.assertTrue(
            all(
                timezone.localtime(event.start_datetime).time().replace(tzinfo=None)
                == time(9, 30)
                for event in events
            )
        )
        march = next(
            event
            for event in events
            if timezone.localtime(event.start_datetime).date() == date(2026, 3, 8)
        )
        november = next(
            event
            for event in events
            if timezone.localtime(event.start_datetime).date() == date(2026, 11, 1)
        )
        self.assertNotEqual(
            timezone.localtime(march.start_datetime).utcoffset(),
            timezone.localtime(november.start_datetime).utcoffset(),
        )
        self.assertTrue(all(event.service_profile_key == PROFILE_KEY for event in events))
        self.assertTrue(
            all(event.service_profile_id == self.profile.pk for event in events)
        )
        self.assertTrue(all(event.host_language_unit_id == self.cm.pk for event in events))
        self.assertTrue(all(event.rotation_anchor_team_id is None for event in events))
        self.assertTrue(all(event.scheduling_revision == 0 for event in events))
        self.assertEqual(ServiceEventAudienceScope.objects.count(), 52)
        self.assertEqual(
            set(ServiceEventAudienceScope.objects.values_list("unit_id", flat=True)),
            {self.cm.pk},
        )
        self.assertEqual(TeamAssignment.objects.count(), 0)
        self.assertEqual(Notification.objects.count(), 0)
        self.assertEqual(LogEntry.objects.count(), 0)

    def test_lifecycle_is_completed_strictly_before_local_today(self):
        self.apply_reviewed_reset(today=date(2026, 1, 4))
        first = ServiceEvent.objects.get(start_datetime=self.local_datetime(hour=9).replace(minute=30))
        second = ServiceEvent.objects.order_by("start_datetime")[1]

        self.assertEqual(first.status, ServiceEvent.STATUS_PUBLISHED)
        self.assertEqual(second.status, ServiceEvent.STATUS_PUBLISHED)

        ServiceEvent.objects.all().delete()
        self.apply_reviewed_reset(today=date(2026, 1, 5))
        first = ServiceEvent.objects.order_by("start_datetime")[0]
        self.assertEqual(first.status, ServiceEvent.STATUS_COMPLETED)
        self.assertTrue(
            all(
                event.status == (
                    ServiceEvent.STATUS_COMPLETED
                    if timezone.localtime(event.start_datetime).date() < date(2026, 1, 5)
                    else ServiceEvent.STATUS_PUBLISHED
                )
                for event in ServiceEvent.objects.all()
            )
        )

    def test_missing_wrong_or_ambiguous_cm_path_blocks_before_deletion(self):
        for case in ("missing", "wrong", "ambiguous"):
            with self.subTest(case=case):
                extra_units = []
                old_event = self.make_event(title=case)
                if case == "missing":
                    self.cm.code = "OTHER"
                    self.cm.save(update_fields=["code", "updated_at"])
                elif case == "wrong":
                    self.cm.is_active = False
                    self.cm.save(update_fields=["is_active", "updated_at"])
                else:
                    other_campus = ChurchStructureUnit.objects.create(
                        parent=self.root,
                        unit_type=ChurchStructureUnit.UNIT_CAMPUS,
                        code="OTHER",
                        name="Other Campus",
                    )
                    other_cm = ChurchStructureUnit.objects.create(
                        parent=other_campus,
                        unit_type=ChurchStructureUnit.UNIT_MINISTRY_CONTEXT,
                        code="CM",
                        name="Other Chinese Ministry",
                    )
                    extra_units = [other_cm, other_campus]

                with self.assertRaises(ProfileSetupPrerequisiteError):
                    apply_reset(
                        expected_reset_token="0000000000000000",
                        today=date(2026, 1, 1),
                    )
                self.assertTrue(ServiceEvent.objects.filter(pk=old_event.pk).exists())

                ServiceEvent.objects.all().delete()
                for unit in extra_units:
                    unit.delete()
                self.cm.code = "CM"
                self.cm.is_active = True
                self.cm.save(update_fields=["code", "is_active", "updated_at"])

    def test_creation_failure_rolls_back_deletion_and_partial_rebuild(self):
        old_event = self.make_event()
        from . import service_profile_setup

        original_create = service_profile_setup._create_canonical_event
        calls = 0

        def fail_on_third(**kwargs):
            nonlocal calls
            calls += 1
            if calls == 3:
                raise RuntimeError("injected creation failure")
            return original_create(**kwargs)

        with patch(
            "events.service_profile_setup._create_canonical_event",
            side_effect=fail_on_third,
        ):
            with self.assertRaisesMessage(RuntimeError, "injected creation failure"):
                self.apply_reviewed_reset(today=date(2026, 1, 1))

        self.assertEqual(ServiceEvent.objects.count(), 1)
        self.assertTrue(ServiceEvent.objects.filter(pk=old_event.pk).exists())

    def test_repeat_apply_is_exact_no_op_and_never_creates_104_events(self):
        first = self.apply_reviewed_reset(today=date(2026, 6, 1))
        event_ids = list(ServiceEvent.objects.order_by("pk").values_list("pk", flat=True))
        second = self.apply_reviewed_reset(today=date(2026, 6, 1))

        self.assertTrue(first["data_mutated"])
        self.assertTrue(second["no_op"])
        self.assertFalse(second["data_mutated"])
        self.assertEqual(second["deleted"]["service_events_deleted"], 0)
        self.assertEqual(ServiceEvent.objects.count(), 52)
        self.assertEqual(
            list(ServiceEvent.objects.order_by("pk").values_list("pk", flat=True)),
            event_ids,
        )

    def test_v2_canonical_postcondition_rejects_legacy_only_and_drift(self):
        self.apply_reviewed_reset(today=date(2026, 6, 1))
        first = ServiceEvent.objects.order_by("pk").first()
        ServiceEvent.objects.filter(pk=first.pk).update(service_profile=None)
        self.assertFalse(
            _dataset_is_canonical(
                profile=self.profile,
                audience=self.cm,
                today=date(2026, 6, 1),
            )
        )

        ServiceEvent.objects.filter(pk=first.pk).update(
            service_profile=self.profile,
            service_profile_key="other.profile",
        )
        self.assertFalse(
            _dataset_is_canonical(
                profile=self.profile,
                audience=self.cm,
                today=date(2026, 6, 1),
            )
        )

    def test_direct_root_cm_shape_is_not_guessed_as_bethany_campus_path(self):
        self.cm.delete()
        direct_cm = ChurchStructureUnit.objects.create(
            parent=self.root,
            unit_type=ChurchStructureUnit.UNIT_MINISTRY_CONTEXT,
            code="CM",
            name="Direct CM",
        )
        event = self.make_event(host_language_unit=direct_cm)

        with self.assertRaises(ProfileSetupPrerequisiteError):
            apply_reset(
                expected_reset_token="0000000000000000",
                today=date(2026, 1, 1),
            )

        self.assertTrue(ServiceEvent.objects.filter(pk=event.pk).exists())
