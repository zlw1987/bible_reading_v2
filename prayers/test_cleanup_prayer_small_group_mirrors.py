"""PRAYER-MIRROR.1B guarded legacy-mirror cleanup command tests.

Dry-run is the default. Apply requires both ``--apply`` and
``--confirm-prayer-small-group-mirror-cleanup``. The command clears the legacy
``small_group_at_post`` mirror only for rows where doing so cannot change
visibility or display: group and non-group rows whose matching active
small-group ``structure_unit_at_post`` already carries the structure identity
(including hidden/deleted rows). It performs no schema migration, no runtime
source switch, never touches ``structure_unit_at_post`` / ``visibility`` /
``body``, and never prints prayer free text.
"""

from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from accounts.management.commands.audit_legacy_structure_schema_retirement_readiness import (
    STATUS_DATA,
    STATUS_DIAGNOSTIC,
    run_audit,
)
from accounts.models import ChurchStructureUnit, SmallGroup
from prayers.management.commands.cleanup_prayer_small_group_mirrors import (
    apply_cleanup,
    run_cleanup,
)
from prayers.models import PrayerRequest


User = get_user_model()


class PrayerSmallGroupMirrorCleanupCommandTests(TestCase):
    author_counter = 0

    def run_cleanup_command(self, *args):
        output = StringIO()
        call_command(
            "cleanup_prayer_small_group_mirrors",
            *args,
            stdout=output,
        )
        return output.getvalue()

    def create_unit(self, code, *, unit_type=None, is_active=True):
        return ChurchStructureUnit.objects.create(
            unit_type=unit_type or ChurchStructureUnit.UNIT_SMALL_GROUP,
            code=code,
            name=code,
            is_active=is_active,
        )

    def create_group(self, name, *, unit=None):
        return SmallGroup.objects.create(name=name, church_structure_unit=unit)

    def create_prayer(
        self,
        *,
        small_group=None,
        structure_unit=None,
        title="Prayer title",
        body="prayer body text",
        visibility=PrayerRequest.VISIBILITY_GROUP,
        is_hidden=False,
        is_deleted=False,
    ):
        type(self).author_counter += 1
        author = User.objects.create_user(
            username=f"prayer_author_{self.author_counter}",
            password="pw123456",
        )
        return PrayerRequest.objects.create(
            user=author,
            title=title,
            body=body,
            visibility=visibility,
            small_group_at_post=small_group,
            structure_unit_at_post=structure_unit,
            is_hidden=is_hidden,
            is_deleted=is_deleted,
        )

    # --- Default mode / confirmation gating ----------------------------------

    def test_dry_run_is_default_and_read_only(self):
        unit = self.create_unit("PR-DRY")
        group = self.create_group("Prayer Dry Group", unit=unit)
        prayer = self.create_prayer(small_group=group, structure_unit=unit)

        with CaptureQueriesContext(connection) as queries:
            stats, _lines = run_cleanup()

        write_sql = [
            query["sql"]
            for query in queries
            if query["sql"].lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE"))
        ]
        self.assertEqual(write_sql, [])
        self.assertEqual(stats["prayers_with_small_group_mirror"], 1)
        self.assertEqual(stats["group_prayers_with_mirror"], 1)
        self.assertEqual(stats["eligible_to_clear"], 1)
        self.assertEqual(stats["would_clear_count"], 1)
        self.assertEqual(stats["cleared_count"], 0)
        self.assertEqual(stats["remaining_mirror_references_after_operation"], 1)
        prayer.refresh_from_db()
        self.assertEqual(prayer.small_group_at_post_id, group.id)

    def test_apply_without_confirmation_refuses_and_does_not_mutate(self):
        unit = self.create_unit("PR-NOCONFIRM")
        group = self.create_group("Prayer No Confirm Group", unit=unit)
        prayer = self.create_prayer(small_group=group, structure_unit=unit)

        with self.assertRaises(CommandError):
            self.run_cleanup_command("--apply")

        prayer.refresh_from_db()
        self.assertEqual(prayer.small_group_at_post_id, group.id)

    def test_confirmation_without_apply_remains_dry_run(self):
        unit = self.create_unit("PR-CONFONLY")
        group = self.create_group("Prayer Confirm Only Group", unit=unit)
        prayer = self.create_prayer(small_group=group, structure_unit=unit)

        output = self.run_cleanup_command(
            "--confirm-prayer-small-group-mirror-cleanup"
        )

        self.assertIn("mode: dry-run", output)
        prayer.refresh_from_db()
        self.assertEqual(prayer.small_group_at_post_id, group.id)

    # --- Category 1: group mirror rows ---------------------------------------

    def test_apply_clears_matching_group_mirror(self):
        unit = self.create_unit("PR-APPLY")
        group = self.create_group("Prayer Apply Group", unit=unit)
        prayer = self.create_prayer(small_group=group, structure_unit=unit)

        stats, _lines = apply_cleanup()

        self.assertEqual(stats["eligible_to_clear"], 1)
        self.assertEqual(stats["cleared_count"], 1)
        self.assertEqual(stats["remaining_mirror_references_after_operation"], 0)
        prayer.refresh_from_db()
        self.assertIsNone(prayer.small_group_at_post_id)
        # visibility and structure snapshot are preserved.
        self.assertEqual(prayer.visibility, PrayerRequest.VISIBILITY_GROUP)
        self.assertEqual(prayer.structure_unit_at_post_id, unit.id)

    def test_hidden_and_deleted_group_rows_are_eligible(self):
        unit = self.create_unit("PR-HIDDEN")
        group = self.create_group("Prayer Hidden Group", unit=unit)
        hidden = self.create_prayer(
            small_group=group, structure_unit=unit, is_hidden=True
        )
        deleted = self.create_prayer(
            small_group=group, structure_unit=unit, is_deleted=True
        )

        stats, _lines = apply_cleanup()

        self.assertEqual(stats["eligible_to_clear"], 2)
        self.assertEqual(stats["cleared_count"], 2)
        hidden.refresh_from_db()
        deleted.refresh_from_db()
        self.assertIsNone(hidden.small_group_at_post_id)
        self.assertIsNone(deleted.small_group_at_post_id)
        # Moderation state untouched.
        self.assertTrue(hidden.is_hidden)
        self.assertTrue(deleted.is_deleted)

    # --- Category 1 skip reasons ---------------------------------------------

    def test_group_mismatched_snapshot_is_skipped(self):
        snapshot_unit = self.create_unit("PR-SNAP")
        other_unit = self.create_unit("PR-OTHER")
        group = self.create_group("Prayer Mismatch Group", unit=other_unit)
        prayer = self.create_prayer(small_group=group, structure_unit=snapshot_unit)

        stats, _lines = apply_cleanup()

        self.assertEqual(stats["skipped_mapping_mismatch"], 1)
        self.assertEqual(stats["cleared_count"], 0)
        prayer.refresh_from_db()
        self.assertEqual(prayer.small_group_at_post_id, group.id)

    def test_group_missing_snapshot_is_skipped(self):
        group = self.create_group("Prayer Missing Snapshot Group", unit=None)
        prayer = self.create_prayer(small_group=group, structure_unit=None)

        stats, _lines = apply_cleanup()

        self.assertEqual(stats["skipped_missing_structure_snapshot"], 1)
        self.assertEqual(stats["cleared_count"], 0)
        self.assertEqual(stats["remaining_mirror_references_after_operation"], 1)
        prayer.refresh_from_db()
        self.assertEqual(prayer.small_group_at_post_id, group.id)

    def test_group_inactive_snapshot_is_skipped(self):
        inactive_unit = self.create_unit("PR-INACT", is_active=False)
        group = self.create_group("Prayer Inactive Group", unit=inactive_unit)
        prayer = self.create_prayer(small_group=group, structure_unit=inactive_unit)

        stats, _lines = apply_cleanup()

        self.assertEqual(stats["skipped_structure_snapshot_inactive"], 1)
        self.assertEqual(stats["cleared_count"], 0)
        prayer.refresh_from_db()
        self.assertEqual(prayer.small_group_at_post_id, group.id)

    def test_group_wrong_type_snapshot_is_skipped(self):
        district_unit = self.create_unit(
            "PR-DIST", unit_type=ChurchStructureUnit.UNIT_DISTRICT
        )
        group = self.create_group("Prayer Wrong Type Group", unit=district_unit)
        prayer = self.create_prayer(small_group=group, structure_unit=district_unit)

        stats, _lines = apply_cleanup()

        self.assertEqual(stats["skipped_structure_snapshot_wrong_type"], 1)
        self.assertEqual(stats["cleared_count"], 0)
        prayer.refresh_from_db()
        self.assertEqual(prayer.small_group_at_post_id, group.id)

    def test_group_unmapped_legacy_group_is_skipped(self):
        unit = self.create_unit("PR-UNMAPPED")
        # Snapshot is a valid small-group unit, but the legacy group has no
        # church_structure_unit mapping, so the mapping check blocks it.
        group = self.create_group("Prayer Unmapped Group", unit=None)
        prayer = self.create_prayer(small_group=group, structure_unit=unit)

        stats, _lines = apply_cleanup()

        self.assertEqual(stats["skipped_legacy_group_unmapped"], 1)
        self.assertEqual(stats["cleared_count"], 0)
        prayer.refresh_from_db()
        self.assertEqual(prayer.small_group_at_post_id, group.id)

    # --- Category 2 / conservative non-group skip ----------------------------

    def test_nongroup_row_with_matching_snapshot_is_cleared(self):
        unit = self.create_unit("PR-CHURCH")
        group = self.create_group("Prayer Church Group", unit=unit)
        prayer = self.create_prayer(
            small_group=group,
            structure_unit=unit,
            visibility=PrayerRequest.VISIBILITY_CHURCH,
        )

        stats, _lines = apply_cleanup()

        self.assertEqual(stats["nongroup_prayers_with_mirror"], 1)
        self.assertEqual(stats["eligible_to_clear"], 1)
        self.assertEqual(stats["cleared_count"], 1)
        prayer.refresh_from_db()
        self.assertIsNone(prayer.small_group_at_post_id)
        self.assertEqual(prayer.visibility, PrayerRequest.VISIBILITY_CHURCH)
        self.assertEqual(prayer.structure_unit_at_post_id, unit.id)

    def test_nongroup_row_without_snapshot_is_skipped_conservatively(self):
        group = self.create_group("Prayer Church No Snapshot Group", unit=None)
        prayer = self.create_prayer(
            small_group=group,
            structure_unit=None,
            visibility=PrayerRequest.VISIBILITY_PRIVATE,
        )

        stats, _lines = apply_cleanup()

        self.assertEqual(stats["nongroup_prayers_with_mirror"], 1)
        self.assertEqual(stats["skipped_display_context_uncertain"], 1)
        self.assertEqual(stats["cleared_count"], 0)
        prayer.refresh_from_db()
        self.assertEqual(prayer.small_group_at_post_id, group.id)

    # --- Output / idempotency / audit ----------------------------------------

    def test_verbose_output_does_not_print_prayer_free_text(self):
        unit = self.create_unit("PR-RO")
        group = self.create_group("Prayer Read Only Group", unit=unit)
        self.create_prayer(
            small_group=group,
            structure_unit=unit,
            title="SECRET_PRAYER_TITLE_DO_NOT_PRINT",
            body="SECRET_PRAYER_BODY_DO_NOT_PRINT",
        )
        self.create_prayer(
            small_group=group,
            structure_unit=None,
            title="SECRET_SKIP_TITLE",
            body="SECRET_SKIP_BODY",
            visibility=PrayerRequest.VISIBILITY_CHURCH,
        )

        with CaptureQueriesContext(connection) as queries:
            output = self.run_cleanup_command("--verbose", "--limit", "20")

        write_sql = [
            query["sql"]
            for query in queries
            if query["sql"].lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE"))
        ]
        self.assertEqual(write_sql, [])
        self.assertIn("mode: dry-run", output)
        self.assertNotIn("SECRET_PRAYER_TITLE_DO_NOT_PRINT", output)
        self.assertNotIn("SECRET_PRAYER_BODY_DO_NOT_PRINT", output)
        self.assertNotIn("SECRET_SKIP_TITLE", output)
        self.assertNotIn("SECRET_SKIP_BODY", output)
        self.assertNotIn("prayer body text", output)

    def test_prayer_id_filter_limits_verbose_rows_only(self):
        unit = self.create_unit("PR-FILTER")
        group = self.create_group("Prayer Filter Group", unit=unit)
        target = self.create_prayer(small_group=group, structure_unit=unit)
        self.create_prayer(small_group=group, structure_unit=unit)

        output = self.run_cleanup_command(
            "--verbose", "--prayer-id", str(target.id)
        )

        # Scan scope still covers both rows; only the printed lines are filtered.
        self.assertIn("prayers_with_small_group_mirror: 2", output)
        self.assertIn(f"prayer #{target.id} ", output)
        self.assertEqual(output.count("decision: eligible_clear"), 1)

    def test_second_apply_after_apply_is_a_no_op(self):
        unit = self.create_unit("PR-IDEM")
        group = self.create_group("Prayer Idempotent Group", unit=unit)
        self.create_prayer(small_group=group, structure_unit=unit)
        self.create_prayer(
            small_group=group,
            structure_unit=unit,
            visibility=PrayerRequest.VISIBILITY_CHURCH,
        )

        first_stats, _lines = apply_cleanup()
        self.assertEqual(first_stats["cleared_count"], 2)
        self.assertEqual(
            first_stats["remaining_mirror_references_after_operation"], 0
        )

        second_stats, _lines = apply_cleanup()
        self.assertEqual(second_stats["prayers_with_small_group_mirror"], 0)
        self.assertEqual(second_stats["eligible_to_clear"], 0)
        self.assertEqual(second_stats["cleared_count"], 0)
        self.assertEqual(
            second_stats["remaining_mirror_references_after_operation"], 0
        )

    def test_audit_reclassifies_to_diagnostic_only_after_cleanup(self):
        unit = self.create_unit("PR-AUDIT")
        group = self.create_group("Prayer Audit Group", unit=unit)
        self.create_prayer(small_group=group, structure_unit=unit)

        before = run_audit()
        before_count = before["data_counts"]["prayer_request_small_group_at_post"]
        before_candidate = next(
            c
            for c in before["candidates"]
            if c["candidate_name"] == "PrayerRequest.small_group_at_post"
        )
        self.assertEqual(before_count, 1)
        self.assertEqual(before_candidate["schema_removal_status"], STATUS_DATA)

        apply_cleanup()

        after = run_audit()
        after_count = after["data_counts"]["prayer_request_small_group_at_post"]
        after_candidate = next(
            c
            for c in after["candidates"]
            if c["candidate_name"] == "PrayerRequest.small_group_at_post"
        )
        self.assertEqual(after_count, 0)
        # With no populated rows and the PRAYER-MIRROR.1C admin/display surface
        # removal, the candidate is classified as diagnostic-tooling-only (the
        # guarded cleanup command still references it), not blocked_by_data and
        # not ready for removal.
        self.assertEqual(
            after_candidate["schema_removal_status"], STATUS_DIAGNOSTIC
        )
