"""Focused tests for audit_bible_study_generation_bridge_retirement."""

from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.utils import timezone

from accounts.models import ChurchStructureUnit, SmallGroup
from studies.models import (
    BibleStudyLesson,
    BibleStudyMeeting,
    BibleStudyMeetingAudienceScope,
    BibleStudySeries,
    BibleStudySeriesAudienceScope,
)
from studies.services import normal_generation_key_for_unit


class BibleStudyGenerationBridgeRetirementCommandTests(TestCase):
    def setUp(self):
        self.future_time = timezone.now() + timezone.timedelta(days=3)
        self.root = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_ROOT,
            code="CHURCH",
            name="Church",
        )
        self.group_unit = self.make_unit("RAINBOW4")
        self.other_group_unit = self.make_unit("RAINBOW5")
        # SmallGroup mapping remains a diagnostic-resolver dependency on the
        # SmallGroup table; BS-MEETING-MIRROR.1A removed the meeting mirror, so
        # it is no longer attached to meetings.
        self.group = SmallGroup.objects.create(
            name="Rainbow 4",
            church_structure_unit=self.group_unit,
        )
        self.series = BibleStudySeries.objects.create(
            title="John Study",
            status=BibleStudySeries.STATUS_PUBLISHED,
        )

    def make_unit(self, code, *, unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP):
        return ChurchStructureUnit.objects.create(
            parent=self.root,
            unit_type=unit_type,
            code=code,
            name=code,
        )

    def add_series_audience(self, series=None, unit=None):
        return BibleStudySeriesAudienceScope.objects.create(
            series=series or self.series,
            unit=unit or self.group_unit,
        )

    def make_lesson(self, **overrides):
        data = {
            "series": self.series,
            "title": "Private guide sentinel title",
            "lesson_date": timezone.localdate() + timezone.timedelta(days=3),
            "pastor_guide_body": "DO-NOT-PRINT-PASTOR-GUIDE-BODY",
            "global_discussion_questions": "DO-NOT-PRINT-DISCUSSION-BODY",
            "prestudy_notes": "DO-NOT-PRINT-PRESTUDY-NOTES",
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

    def add_meeting_audience(self, meeting, unit=None):
        return BibleStudyMeetingAudienceScope.objects.create(
            meeting=meeting,
            unit=unit or self.group_unit,
        )

    def run_command(self, *args):
        out = StringIO()
        call_command(
            "audit_bible_study_generation_bridge_retirement",
            *args,
            stdout=out,
        )
        return out.getvalue()

    def make_structure_native_meeting(self):
        self.add_series_audience()
        meeting = self.make_meeting(
            anchor_unit=self.group_unit,
            generation_key=normal_generation_key_for_unit(self.group_unit),
        )
        self.add_meeting_audience(meeting, self.group_unit)
        return meeting

    def test_command_has_no_apply_option(self):
        with self.assertRaises(CommandError) as context:
            self.run_command("--apply")

        self.assertIn("unrecognized arguments: --apply", str(context.exception))

    def test_read_only_behavior(self):
        meeting = self.make_structure_native_meeting()
        before_series_rows = BibleStudySeriesAudienceScope.objects.count()
        before_meeting_rows = BibleStudyMeetingAudienceScope.objects.count()

        output = self.run_command("--verbose", "--limit", "10")

        meeting.refresh_from_db()
        self.assertEqual(BibleStudySeriesAudienceScope.objects.count(), before_series_rows)
        self.assertEqual(BibleStudyMeetingAudienceScope.objects.count(), before_meeting_rows)
        self.assertEqual(meeting.anchor_unit_id, self.group_unit.id)
        self.assertIn("runtime_mutated: false", output)
        self.assertIn("data_mutated: false", output)
        self.assertIn("schema_mutated: false", output)
        self.assertIn("apply_option_present: false", output)

    def test_structure_native_fixture_reports_expected_counters(self):
        self.make_structure_native_meeting()

        output = self.run_command()

        self.assertIn("series_checked: 1", output)
        self.assertIn("series_with_audience_rows: 1", output)
        self.assertIn("normal_series_with_structure_audience: 1", output)
        self.assertIn("meetings_checked: 1", output)
        self.assertIn("normal_meetings_checked: 1", output)
        self.assertIn("meetings_with_generation_key: 1", output)
        self.assertIn("meetings_missing_generation_key: 0", output)
        self.assertIn("meetings_with_anchor_unit: 1", output)
        self.assertIn("meetings_with_audience_rows: 1", output)
        self.assertIn("ordinary_visibility_paths_using_small_group: 0", output)
        self.assertIn("blockers_for_small_group_table_retirement: 0", output)

    def test_generation_key_anchor_audience_is_structure_native(self):
        meeting = self.make_structure_native_meeting()

        output = self.run_command("--verbose", "--limit", "10")

        self.assertIn(f"meeting #{meeting.id}", output)
        self.assertIn("decision: structure_native", output)

    def test_normal_meeting_missing_generation_key_is_blocker(self):
        self.add_series_audience()
        meeting = self.make_meeting(anchor_unit=self.group_unit)
        self.add_meeting_audience(meeting, self.group_unit)

        output = self.run_command("--verbose", "--limit", "10")

        self.assertIn("meetings_missing_generation_key: 1", output)
        self.assertIn("decision: blocker", output)
        self.assertNotIn("blockers_for_small_group_table_retirement: 0", output)

    def test_series_without_audience_rows_is_blocker(self):
        self.make_meeting(
            anchor_unit=self.group_unit,
            generation_key=normal_generation_key_for_unit(self.group_unit),
        )

        output = self.run_command("--verbose", "--limit", "10")

        self.assertIn("series_without_audience_rows: 1", output)
        self.assertIn("active_series_without_audience_rows: 1", output)
        self.assertIn("decision: blocker", output)

    def test_verbose_output_does_not_print_private_body_text(self):
        self.make_structure_native_meeting()

        output = self.run_command("--verbose", "--limit", "10")

        self.assertNotIn("DO-NOT-PRINT-PASTOR-GUIDE-BODY", output)
        self.assertNotIn("DO-NOT-PRINT-DISCUSSION-BODY", output)
        self.assertNotIn("DO-NOT-PRINT-PRESTUDY-NOTES", output)

    def test_fail_on_blockers_exits_nonzero_when_blockers_exist(self):
        # Active series without audience rows is a generation-readiness blocker.
        self.make_meeting(anchor_unit=self.group_unit)

        with self.assertRaises(CommandError) as context:
            self.run_command("--fail-on-blockers")

        self.assertIn(
            "blockers_for_small_group_table_retirement=",
            str(context.exception),
        )

    def test_ordinary_runtime_visibility_counter_is_zero(self):
        self.make_structure_native_meeting()

        output = self.run_command()

        self.assertIn("ordinary_visibility_paths_using_small_group: 0", output)

    def test_diagnostic_paths_counter_reports_small_group_table_dependencies(self):
        self.make_structure_native_meeting()

        output = self.run_command()

        self.assertIn("diagnostic_paths_using_small_group_table: 3", output)
