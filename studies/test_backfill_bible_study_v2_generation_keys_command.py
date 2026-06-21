from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.utils import timezone

from accounts.models import ChurchStructureUnit
from studies.models import (
    BibleStudyLesson,
    BibleStudyMeeting,
    BibleStudyMeetingAudienceScope,
    BibleStudySeries,
)
from studies.services import normal_generation_key_for_unit


class BackfillBibleStudyV2GenerationKeysCommandTests(TestCase):
    def setUp(self):
        self.future_time = timezone.now() + timezone.timedelta(days=3)
        self.series = BibleStudySeries.objects.create(
            title="约翰福音查经",
            status=BibleStudySeries.STATUS_PUBLISHED,
        )
        self.root = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_ROOT,
            code="CHURCH",
            name="全教会",
        )
        self.group_unit = self.make_unit(
            "RAINBOW4",
            ChurchStructureUnit.UNIT_SMALL_GROUP,
        )
        self.other_group_unit = self.make_unit(
            "RAINBOW5",
            ChurchStructureUnit.UNIT_SMALL_GROUP,
        )
        self.district_unit = self.make_unit(
            "NORTH",
            ChurchStructureUnit.UNIT_DISTRICT,
        )

    def make_unit(self, code, unit_type, *, is_active=True):
        return ChurchStructureUnit.objects.create(
            parent=self.root,
            unit_type=unit_type,
            code=code,
            name=code,
            is_active=is_active,
        )

    def make_lesson(self, **overrides):
        data = {
            "series": self.series,
            "title": "约翰十五章",
            "lesson_date": timezone.localdate() + timezone.timedelta(days=3),
            "status": BibleStudyLesson.STATUS_PUBLISHED,
        }
        data.update(overrides)
        return BibleStudyLesson.objects.create(**data)

    def make_meeting(self, *, lesson=None, **overrides):
        data = {
            "lesson": lesson or self.make_lesson(),
            "meeting_datetime": self.future_time,
            "status": BibleStudyMeeting.STATUS_PUBLISHED,
        }
        data.update(overrides)
        return BibleStudyMeeting.objects.create(**data)

    def add_audience(self, meeting, unit=None):
        return BibleStudyMeetingAudienceScope.objects.create(
            meeting=meeting,
            unit=unit or self.group_unit,
        )

    def run_command(self, *args):
        out = StringIO()
        call_command(
            "backfill_bible_study_v2_generation_keys",
            *args,
            stdout=out,
        )
        return out.getvalue()

    def test_dry_run_reports_would_update_and_writes_nothing(self):
        meeting = self.make_meeting()
        audience = self.add_audience(meeting)

        output = self.run_command()

        meeting.refresh_from_db()
        audience.refresh_from_db()
        self.assertIsNone(meeting.generation_key)
        self.assertIsNone(meeting.anchor_unit_id)
        self.assertEqual(audience.unit_id, self.group_unit.id)
        self.assertIn("would_update_generation_key: 1", output)
        self.assertIn("would_update_anchor_unit: 1", output)
        self.assertIn("data_mutated: false", output)
        self.assertIn("runtime_mutated: false", output)

    def test_apply_updates_safe_row_without_mutating_audience(self):
        meeting = self.make_meeting()
        audience = self.add_audience(meeting)
        expected_key = normal_generation_key_for_unit(self.group_unit)

        output = self.run_command("--apply")

        meeting.refresh_from_db()
        audience.refresh_from_db()
        self.assertEqual(meeting.generation_key, expected_key)
        self.assertEqual(meeting.anchor_unit_id, self.group_unit.id)
        self.assertEqual(audience.unit_id, self.group_unit.id)
        self.assertIn("updated_generation_key: 1", output)
        self.assertIn("updated_anchor_unit: 1", output)
        self.assertIn("data_mutated: true", output)

    def test_already_correct_row_is_skipped(self):
        expected_key = normal_generation_key_for_unit(self.group_unit)
        meeting = self.make_meeting(
            generation_key=expected_key,
            anchor_unit=self.group_unit,
        )
        self.add_audience(meeting)

        output = self.run_command()

        meeting.refresh_from_db()
        self.assertEqual(meeting.generation_key, expected_key)
        self.assertEqual(meeting.anchor_unit_id, self.group_unit.id)
        self.assertIn("meetings_generation_key_already_correct: 1", output)
        self.assertIn("meetings_anchor_already_correct: 1", output)
        self.assertIn("would_update_generation_key: 0", output)
        self.assertIn("would_update_anchor_unit: 0", output)
        self.assertIn("data_mutated: false", output)

    def test_multiple_audience_rows_are_blocked(self):
        meeting = self.make_meeting()
        self.add_audience(meeting)
        self.add_audience(meeting, self.other_group_unit)

        output = self.run_command()

        meeting.refresh_from_db()
        self.assertIsNone(meeting.generation_key)
        self.assertIn("meetings_with_multiple_audience_rows: 1", output)
        self.assertIn("would_update_generation_key: 0", output)

    def test_non_small_group_audience_is_blocked(self):
        meeting = self.make_meeting()
        self.add_audience(meeting, self.district_unit)

        output = self.run_command()

        meeting.refresh_from_db()
        self.assertIsNone(meeting.generation_key)
        self.assertIn("meetings_with_non_small_group_audience: 1", output)
        self.assertIn("would_update_generation_key: 0", output)

    def test_existing_conflicting_generation_key_is_blocked(self):
        lesson = self.make_lesson()
        expected_key = normal_generation_key_for_unit(self.group_unit)
        self.make_meeting(
            lesson=lesson,
            generation_key=expected_key,
        )
        target = self.make_meeting(lesson=lesson)
        self.add_audience(target)

        output = self.run_command()

        target.refresh_from_db()
        self.assertIsNone(target.generation_key)
        self.assertIn("meetings_generation_key_missing: 1", output)
        self.assertIn("meetings_generation_key_conflict_blocked: 1", output)
        self.assertIn("would_update_generation_key: 0", output)

    def test_existing_mismatched_generation_key_is_blocked(self):
        meeting = self.make_meeting(generation_key="normal-unit:99999")
        self.add_audience(meeting)

        output = self.run_command()

        meeting.refresh_from_db()
        self.assertEqual(meeting.generation_key, "normal-unit:99999")
        self.assertIn("meetings_generation_key_mismatch_blocked: 1", output)
        self.assertIn("would_update_generation_key: 0", output)

    def test_anchor_mismatch_blocks_whole_row_including_missing_key(self):
        meeting = self.make_meeting(anchor_unit=self.other_group_unit)
        self.add_audience(meeting)

        output = self.run_command()

        meeting.refresh_from_db()
        self.assertIsNone(meeting.generation_key)
        self.assertEqual(meeting.anchor_unit_id, self.other_group_unit.id)
        self.assertIn("meetings_generation_key_missing: 1", output)
        self.assertIn("meetings_anchor_mismatch_blocked: 1", output)
        self.assertIn("would_update_generation_key: 0", output)
        self.assertIn("would_update_anchor_unit: 0", output)

    def test_verbose_includes_capped_identity_context_without_content_fields(self):
        meeting = self.make_meeting()
        self.add_audience(meeting)

        output = self.run_command("--verbose", "--limit", "1")

        self.assertIn("per-meeting decisions:", output)
        self.assertIn(f"meeting #{meeting.id}", output)
        self.assertIn("generation_key: (blank)", output)
        self.assertIn(f"expected: normal-unit:{self.group_unit.id}", output)
        self.assertIn(f"audience_unit: #{self.group_unit.id}", output)

    def test_verbose_limit_caps_output_but_not_scan_scope(self):
        for _index in range(3):
            meeting = self.make_meeting()
            self.add_audience(meeting)

        output = self.run_command("--verbose", "--limit", "1")

        self.assertIn("meetings_checked: 3", output)
        self.assertIn("would_update_generation_key: 3", output)
        self.assertEqual(output.count("  meeting #"), 1)
        self.assertIn(
            "stopped at --limit 1; 2 more meeting decision(s) not printed",
            output,
        )

    def test_limit_zero_scans_all_but_prints_no_decision_lines(self):
        for _index in range(2):
            meeting = self.make_meeting()
            self.add_audience(meeting)

        output = self.run_command("--verbose", "--limit", "0")

        self.assertIn("meetings_checked: 2", output)
        self.assertIn("would_update_generation_key: 2", output)
        self.assertIn("per-meeting decisions:", output)
        self.assertNotIn("  meeting #", output)
        self.assertIn(
            "stopped at --limit 0; 2 more meeting decision(s) not printed",
            output,
        )

    def test_fail_on_blockers_checks_rows_beyond_verbose_limit(self):
        safe = self.make_meeting()
        self.add_audience(safe)
        blocked = self.make_meeting()
        self.add_audience(blocked)
        self.add_audience(blocked, self.other_group_unit)

        out = StringIO()
        with self.assertRaises(CommandError) as context:
            call_command(
                "backfill_bible_study_v2_generation_keys",
                "--verbose",
                "--limit",
                "1",
                "--fail-on-blockers",
                stdout=out,
            )

        self.assertIn("meetings_checked: 2", out.getvalue())
        self.assertIn("meetings_with_multiple_audience_rows: 1", out.getvalue())
        self.assertEqual(out.getvalue().count("  meeting #"), 1)
        self.assertIn("meetings_with_multiple_audience_rows=1", str(context.exception))
