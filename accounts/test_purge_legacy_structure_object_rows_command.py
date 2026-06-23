from io import StringIO
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.utils import timezone

from accounts.management.commands import purge_legacy_structure_object_rows
from accounts.management.commands.purge_legacy_structure_object_rows import (
    CONFIRM_FLAG,
    Command,
    collect_plan,
)
from accounts.models import (
    ChurchRoleAssignment,
    ChurchStructureMembership,
    ChurchStructureUnit,
    District,
    MinistryContext,
    SmallGroup,
)
from events.models import ServiceEvent
from studies.models import BibleStudyLesson, BibleStudyMeeting, BibleStudySeries


User = get_user_model()


class PurgeLegacyStructureObjectRowsCommandTests(TestCase):
    def setUp(self):
        self.today = timezone.localdate()
        self.now = timezone.now()
        self.root = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_ROOT,
            code="CHURCH",
            name="Whole Church",
            description="DO NOT PRINT PRIVATE ROOT NOTE",
        )
        self.ministry_unit = ChurchStructureUnit.objects.create(
            parent=self.root,
            unit_type=ChurchStructureUnit.UNIT_MINISTRY_CONTEXT,
            code="CM",
            name="Chinese Ministry",
            description="DO NOT PRINT PRIVATE MINISTRY NOTE",
        )
        self.district_unit = ChurchStructureUnit.objects.create(
            parent=self.ministry_unit,
            unit_type=ChurchStructureUnit.UNIT_DISTRICT,
            code="CM-D1",
            name="District 1",
            description="DO NOT PRINT PRIVATE DISTRICT NOTE",
        )
        self.group_unit = ChurchStructureUnit.objects.create(
            parent=self.district_unit,
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="CM-D1-G1",
            name="Group 1",
            description="DO NOT PRINT PRIVATE GROUP NOTE",
        )
        self.unassigned_unit = ChurchStructureUnit.objects.create(
            parent=self.root,
            unit_type=ChurchStructureUnit.UNIT_CUSTOM,
            code="UNASSIGNED-GROUPS",
            name="Unassigned Groups",
            description="DO NOT PRINT PRIVATE UNASSIGNED NOTE",
        )
        self.inactive_group_unit = ChurchStructureUnit.objects.create(
            parent=self.district_unit,
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="INACTIVE-GROUP",
            name="Inactive Group",
            is_active=False,
        )

        self.context = MinistryContext.objects.create(
            code="CM",
            name="Chinese Ministry",
            description="DO NOT PRINT PRIVATE CONTEXT NOTE",
            church_structure_unit=self.ministry_unit,
        )
        self.district = District.objects.create(
            name="District 1",
            church_structure_unit=self.district_unit,
        )
        self.group = SmallGroup.objects.create(
            name="Group 1",
            church_structure_unit=self.group_unit,
        )

    def make_unrelated_runtime_rows(self):
        user = User.objects.create_user(username="member", password="pw123456")
        membership = ChurchStructureMembership.objects.create(
            user=user,
            unit=self.group_unit,
            status=ChurchStructureMembership.STATUS_ACTIVE,
            is_primary=True,
            start_date=self.today - timezone.timedelta(days=1),
        )
        role = ChurchRoleAssignment.objects.create(
            user=user,
            role=ChurchRoleAssignment.ROLE_GROUP_LEADER,
            scope_type=ChurchRoleAssignment.SCOPE_SMALL_GROUP,
            structure_unit=self.group_unit,
        )
        event = ServiceEvent.objects.create(
            title="Protected Service Event",
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
            start_datetime=self.now + timezone.timedelta(days=7),
            status=ServiceEvent.STATUS_PUBLISHED,
            host_language_unit=self.ministry_unit,
        )
        series = BibleStudySeries.objects.create(title="Protected Series")
        lesson = BibleStudyLesson.objects.create(
            series=series,
            title="Protected Lesson",
            lesson_date=self.today + timezone.timedelta(days=7),
        )
        meeting = BibleStudyMeeting.objects.create(
            lesson=lesson,
            anchor_unit=self.group_unit,
            generation_key="protected-generation-key",
            meeting_datetime=self.now + timezone.timedelta(days=7),
        )
        return {
            "user": user,
            "membership": membership,
            "role": role,
            "event": event,
            "series": series,
            "lesson": lesson,
            "meeting": meeting,
        }

    def test_command_has_apply_and_confirmation_flags(self):
        parser = Command().create_parser(
            "manage.py",
            "purge_legacy_structure_object_rows",
        )
        option_strings = {
            option
            for action in parser._actions
            for option in getattr(action, "option_strings", [])
        }

        self.assertIn("--apply", option_strings)
        self.assertIn(CONFIRM_FLAG, option_strings)

    def test_dry_run_reports_counts_special_rows_and_writes_nothing(self):
        SmallGroup.objects.create(name="Unmapped Group")
        SmallGroup.objects.create(
            name="Inactive Mapped Group",
            church_structure_unit=self.inactive_group_unit,
        )
        District.objects.create(
            name="Unassigned Legacy District",
            church_structure_unit=self.unassigned_unit,
        )
        before_counts = {
            "units": ChurchStructureUnit.objects.count(),
            "contexts": MinistryContext.objects.count(),
            "districts": District.objects.count(),
            "groups": SmallGroup.objects.count(),
        }

        out = StringIO()
        call_command(
            "purge_legacy_structure_object_rows",
            "--verbose",
            "--limit",
            "20",
            stdout=out,
        )

        self.assertEqual(ChurchStructureUnit.objects.count(), before_counts["units"])
        self.assertEqual(MinistryContext.objects.count(), before_counts["contexts"])
        self.assertEqual(District.objects.count(), before_counts["districts"])
        self.assertEqual(SmallGroup.objects.count(), before_counts["groups"])

        output = out.getvalue()
        self.assertIn("dry_run: true", output)
        self.assertIn("apply_option_present: true", output)
        self.assertIn("apply_requested: false", output)
        self.assertIn("confirmation_present: false", output)
        self.assertIn("data_mutated: false", output)
        self.assertIn("small_groups_matched: 3", output)
        self.assertIn("districts_matched: 2", output)
        self.assertIn("ministry_contexts_matched: 1", output)
        self.assertIn("small_groups_mapped: 2", output)
        self.assertIn("small_groups_unmapped: 1", output)
        self.assertIn("wrong_type_mapping_rows: 1", output)
        self.assertIn("inactive_mapping_rows: 1", output)
        self.assertIn("special_unassigned_groups_rows: 1", output)
        self.assertIn("unit_code=UNASSIGNED-GROUPS", output)
        self.assertIn("protected deletion counters:", output)
        self.assertIn("accounts.ChurchStructureUnit: to_delete=0 deleted=0", output)
        self.assertNotIn("DO NOT PRINT PRIVATE", output)

    def test_apply_without_confirmation_fails_and_deletes_nothing(self):
        before_counts = {
            "units": ChurchStructureUnit.objects.count(),
            "contexts": MinistryContext.objects.count(),
            "districts": District.objects.count(),
            "groups": SmallGroup.objects.count(),
        }

        out = StringIO()
        with self.assertRaises(CommandError) as context:
            call_command(
                "purge_legacy_structure_object_rows",
                "--apply",
                stdout=out,
            )

        self.assertIn("requires", str(context.exception))
        self.assertIn(CONFIRM_FLAG, str(context.exception))
        self.assertEqual(ChurchStructureUnit.objects.count(), before_counts["units"])
        self.assertEqual(MinistryContext.objects.count(), before_counts["contexts"])
        self.assertEqual(District.objects.count(), before_counts["districts"])
        self.assertEqual(SmallGroup.objects.count(), before_counts["groups"])
        self.assertIn("apply_requested: true", out.getvalue())
        self.assertIn("confirmation_present: false", out.getvalue())
        self.assertIn("data_mutated: false", out.getvalue())

    def test_apply_with_confirmation_deletes_only_legacy_object_rows(self):
        runtime_rows = self.make_unrelated_runtime_rows()
        District.objects.create(
            name="Unassigned Legacy District",
            church_structure_unit=self.unassigned_unit,
        )
        before_unit_ids = set(ChurchStructureUnit.objects.values_list("id", flat=True))

        out = StringIO()
        call_command(
            "purge_legacy_structure_object_rows",
            "--apply",
            CONFIRM_FLAG,
            "--verbose",
            "--limit",
            "20",
            stdout=out,
        )

        self.assertEqual(SmallGroup.objects.count(), 0)
        self.assertEqual(District.objects.count(), 0)
        self.assertEqual(MinistryContext.objects.count(), 0)
        self.assertEqual(
            set(ChurchStructureUnit.objects.values_list("id", flat=True)),
            before_unit_ids,
        )
        self.assertTrue(User.objects.filter(pk=runtime_rows["user"].pk).exists())
        self.assertTrue(
            ChurchStructureMembership.objects.filter(
                pk=runtime_rows["membership"].pk
            ).exists()
        )
        self.assertTrue(
            ChurchRoleAssignment.objects.filter(pk=runtime_rows["role"].pk).exists()
        )
        self.assertTrue(ServiceEvent.objects.filter(pk=runtime_rows["event"].pk).exists())
        self.assertTrue(BibleStudySeries.objects.filter(pk=runtime_rows["series"].pk).exists())
        self.assertTrue(BibleStudyLesson.objects.filter(pk=runtime_rows["lesson"].pk).exists())
        self.assertTrue(BibleStudyMeeting.objects.filter(pk=runtime_rows["meeting"].pk).exists())

        output = out.getvalue()
        self.assertIn("apply_requested: true", output)
        self.assertIn("confirmation_present: true", output)
        self.assertIn("data_mutated: true", output)
        self.assertIn("legacy_rows_deleted: 4", output)
        self.assertIn("legacy_small_groups_deleted: 1", output)
        self.assertIn("legacy_districts_deleted: 2", output)
        self.assertIn("legacy_ministry_contexts_deleted: 1", output)
        self.assertIn("runtime_rows_deleted: 0", output)
        self.assertIn("protected_church_structure_units_deleted: 0", output)
        self.assertIn("apply_result: completed", output)

    def test_collect_plan_reports_no_unexpected_dependencies_for_clean_fixture(self):
        plan = collect_plan()
        stats = plan["stats"]

        self.assertTrue(plan["safe_to_apply"])
        self.assertEqual(stats["unexpected_inbound_dependency_rows"], 0)
        self.assertEqual(stats["collector_field_update_rows"], 0)
        self.assertEqual(stats["collector_fast_delete_rows"], 0)
        self.assertEqual(stats["collector_protected_rows"], 0)
        self.assertEqual(stats["collector_restricted_rows"], 0)

    def test_apply_aborts_when_collector_would_delete_unexpected_models(self):
        before_counts = {
            "contexts": MinistryContext.objects.count(),
            "districts": District.objects.count(),
            "groups": SmallGroup.objects.count(),
        }

        out = StringIO()
        with mock.patch.object(
            purge_legacy_structure_object_rows,
            "LEGACY_MODEL_LABELS",
            set(),
        ):
            with self.assertRaises(CommandError) as context:
                call_command(
                    "purge_legacy_structure_object_rows",
                    "--apply",
                    CONFIRM_FLAG,
                    "--verbose",
                    stdout=out,
                )

        self.assertIn("Unsafe legacy structure object row purge plan", str(context.exception))
        self.assertEqual(MinistryContext.objects.count(), before_counts["contexts"])
        self.assertEqual(District.objects.count(), before_counts["districts"])
        self.assertEqual(SmallGroup.objects.count(), before_counts["groups"])
        self.assertIn("unexpected_inbound_dependency_rows: 3", out.getvalue())
        self.assertIn("data_mutated: false", out.getvalue())
