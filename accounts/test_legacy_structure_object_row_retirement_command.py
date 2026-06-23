from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from accounts.management.commands.audit_legacy_structure_object_row_retirement import (
    Command,
    run_audit,
)
from accounts.models import ChurchStructureUnit, District, MinistryContext, SmallGroup


class LegacyStructureObjectRowRetirementCommandTests(TestCase):
    def setUp(self):
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
        self.inactive_group_unit = ChurchStructureUnit.objects.create(
            parent=self.district_unit,
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="INACTIVE-GROUP",
            name="Inactive Group",
            is_active=False,
        )
        self.unassigned_unit = ChurchStructureUnit.objects.create(
            parent=self.root,
            unit_type=ChurchStructureUnit.UNIT_CUSTOM,
            code="UNASSIGNED-GROUPS",
            name="Unassigned Groups",
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

    def test_command_has_no_apply_option(self):
        parser = Command().create_parser(
            "manage.py",
            "audit_legacy_structure_object_row_retirement",
        )

        option_strings = {
            option
            for action in parser._actions
            for option in getattr(action, "option_strings", [])
        }

        self.assertNotIn("--apply", option_strings)

    def test_reports_controlled_row_counts_and_active_mapped_rows(self):
        audit = run_audit()
        stats = audit["stats"]

        self.assertEqual(stats["small_groups_checked"], 1)
        self.assertEqual(stats["districts_checked"], 1)
        self.assertEqual(stats["ministry_contexts_checked"], 1)
        self.assertEqual(stats["small_groups_with_mapping_unit"], 1)
        self.assertEqual(stats["districts_with_mapping_unit"], 1)
        self.assertEqual(stats["ministry_contexts_with_mapping_unit"], 1)
        self.assertEqual(stats["wrong_type_mapping_units"], 0)
        self.assertEqual(stats["inactive_mapping_units"], 0)
        self.assertEqual(stats["unmapped_rows"], 0)
        self.assertEqual(stats["candidate_rows_for_future_archive"], 3)
        self.assertEqual(stats["candidate_rows_for_future_delete"], 0)
        self.assertEqual(stats["rows_requiring_mapping_bridge_decision"], 3)
        self.assertEqual(stats["rows_requiring_special_handling"], 0)
        self.assertEqual(stats["live_runtime_consumers_found"], 0)

    def test_reports_unmapped_inactive_wrong_type_and_special_rows(self):
        SmallGroup.objects.create(name="Unmapped Group")
        SmallGroup.objects.create(
            name="Inactive Mapped Group",
            church_structure_unit=self.inactive_group_unit,
        )
        District.objects.create(
            name="Unassigned Legacy District",
            church_structure_unit=self.unassigned_unit,
        )

        audit = run_audit()
        stats = audit["stats"]

        self.assertEqual(stats["small_groups_checked"], 3)
        self.assertEqual(stats["districts_checked"], 2)
        self.assertEqual(stats["ministry_contexts_checked"], 1)
        self.assertEqual(stats["unmapped_rows"], 1)
        self.assertEqual(stats["inactive_mapping_units"], 1)
        self.assertEqual(stats["wrong_type_mapping_units"], 1)
        self.assertEqual(stats["rows_requiring_special_handling"], 2)

        details = "\n".join(audit["details"])
        self.assertIn("object_type=SmallGroup", details)
        self.assertIn("reason=no church_structure_unit mapping", details)
        self.assertIn("unit_active=false", details)
        self.assertIn("unit_code=UNASSIGNED-GROUPS", details)
        self.assertIn("legacy unassigned/custom holding-bucket mapping", details)

    def test_fail_on_blockers_exits_nonzero_for_special_handling(self):
        District.objects.create(
            name="Unassigned Legacy District",
            church_structure_unit=self.unassigned_unit,
        )

        out = StringIO()
        with self.assertRaises(CommandError) as context:
            call_command(
                "audit_legacy_structure_object_row_retirement",
                "--fail-on-blockers",
                stdout=out,
            )

        self.assertIn("rows_requiring_special_handling=1", str(context.exception))
        self.assertIn("rows_requiring_special_handling: 1", out.getvalue())

    def test_command_is_read_only(self):
        before_counts = {
            "units": ChurchStructureUnit.objects.count(),
            "contexts": MinistryContext.objects.count(),
            "districts": District.objects.count(),
            "groups": SmallGroup.objects.count(),
        }
        before_group = (
            self.group.name,
            self.group.church_structure_unit_id,
        )

        out = StringIO()
        call_command(
            "audit_legacy_structure_object_row_retirement",
            "--verbose",
            "--limit",
            "30",
            stdout=out,
        )

        self.group.refresh_from_db()
        self.assertEqual(ChurchStructureUnit.objects.count(), before_counts["units"])
        self.assertEqual(MinistryContext.objects.count(), before_counts["contexts"])
        self.assertEqual(District.objects.count(), before_counts["districts"])
        self.assertEqual(SmallGroup.objects.count(), before_counts["groups"])
        self.assertEqual(
            (
                self.group.name,
                self.group.church_structure_unit_id,
            ),
            before_group,
        )
        self.assertIn("runtime_mutated: false", out.getvalue())
        self.assertIn("data_mutated: false", out.getvalue())
        self.assertIn("schema_mutated: false", out.getvalue())
        self.assertIn("apply_option_present: false", out.getvalue())

    def test_verbose_output_does_not_print_private_free_text(self):
        out = StringIO()
        call_command(
            "audit_legacy_structure_object_row_retirement",
            "--verbose",
            "--limit",
            "30",
            stdout=out,
        )

        output = out.getvalue()
        self.assertIn("consumer inventory:", output)
        self.assertIn("row examples:", output)
        self.assertNotIn("DO NOT PRINT PRIVATE", output)
