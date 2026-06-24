from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from accounts.management.commands.audit_legacy_structure_object_row_retirement import (
    Command,
    run_audit,
)
from accounts.models import ChurchStructureUnit


class LegacyStructureObjectRowRetirementCommandTests(TestCase):
    def setUp(self):
        self.root = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_ROOT,
            code="CHURCH",
            name="Whole Church",
            description="DO NOT PRINT PRIVATE ROOT NOTE",
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

    def test_reports_removed_or_empty_legacy_tables_without_model_imports(self):
        audit = run_audit()
        stats = audit["stats"]

        self.assertEqual(stats["small_groups_checked"], 0)
        self.assertEqual(stats["districts_checked"], 0)
        self.assertEqual(stats["ministry_contexts_checked"], 0)
        self.assertEqual(stats["final_table_retirement_blocker_rows"], 0)
        self.assertEqual(stats["rows_requiring_mapping_bridge_decision"], 0)
        self.assertEqual(stats["rows_requiring_special_handling"], 0)
        self.assertEqual(stats["live_runtime_consumers_found"], 0)
        self.assertEqual(audit["details"], [])

    def test_command_is_read_only(self):
        before_units = ChurchStructureUnit.objects.count()

        out = StringIO()
        call_command(
            "audit_legacy_structure_object_row_retirement",
            "--verbose",
            "--limit",
            "30",
            stdout=out,
        )

        self.assertEqual(ChurchStructureUnit.objects.count(), before_units)
        output = out.getvalue()
        self.assertIn("runtime_mutated: false", output)
        self.assertIn("data_mutated: false", output)
        self.assertIn("schema_mutated: false", output)
        self.assertIn("apply_option_present: false", output)
        self.assertIn(
            "legacy_object_rows_are: final table-retirement blockers",
            output,
        )
        self.assertIn(
            "next_schema_gate: remove SmallGroup, District, and MinistryContext",
            output,
        )
        self.assertIn("row examples:", output)
        self.assertIn("  (none)", output)

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
        self.assertNotIn("purge_legacy_structure_object_rows", output)
        self.assertIn("row examples:", output)
        self.assertNotIn("DO NOT PRINT PRIVATE", output)
