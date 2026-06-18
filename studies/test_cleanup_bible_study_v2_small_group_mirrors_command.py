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
    BibleStudySession,
)
from studies.services import normal_generation_key_for_unit


class CleanupBibleStudyV2SmallGroupMirrorsCommandTests(TestCase):
    def setUp(self):
        self.future_time = timezone.now() + timezone.timedelta(days=3)
        self.series = BibleStudySeries.objects.create(
            title="Shared Series",
            status=BibleStudySeries.STATUS_PUBLISHED,
        )
        self.root = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_ROOT,
            code="CHURCH",
            name="Whole Church",
        )
        self.group_unit = self.make_unit(
            "R4",
            ChurchStructureUnit.UNIT_SMALL_GROUP,
        )
        self.other_group_unit = self.make_unit(
            "R5",
            ChurchStructureUnit.UNIT_SMALL_GROUP,
        )
        self.district_unit = self.make_unit(
            "NORTH",
            ChurchStructureUnit.UNIT_DISTRICT,
        )
        self.group = SmallGroup.objects.create(
            name="Rainbow 4",
            church_structure_unit=self.group_unit,
        )
        self.other_group = SmallGroup.objects.create(
            name="Rainbow 5",
            church_structure_unit=self.other_group_unit,
        )
        self.series.small_group = self.group
        self.series.scope_type = BibleStudySeries.SCOPE_SMALL_GROUP
        self.series.save(update_fields=["scope_type", "small_group", "updated_at"])

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
            "title": "Lesson",
            "lesson_date": timezone.localdate() + timezone.timedelta(days=3),
            "status": BibleStudyLesson.STATUS_PUBLISHED,
        }
        data.update(overrides)
        return BibleStudyLesson.objects.create(**data)

    def make_meeting(self, *, lesson=None, small_group=None, unit=None, **overrides):
        if small_group is None:
            small_group = self.group
        if unit is None:
            unit = self.group_unit
        data = {
            "lesson": lesson or self.make_lesson(),
            "small_group": small_group,
            "anchor_unit": unit,
            "generation_key": normal_generation_key_for_unit(unit),
            "meeting_kind": BibleStudyMeeting.KIND_NORMAL,
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
            "cleanup_bible_study_v2_small_group_mirrors",
            *args,
            stdout=out,
        )
        return out.getvalue()

    def make_safe_meeting(self, **overrides):
        meeting = self.make_meeting(**overrides)
        self.add_audience(meeting, meeting.anchor_unit)
        return meeting

    def test_dry_run_safe_row_reports_would_clear_and_writes_nothing(self):
        meeting = self.make_safe_meeting()

        output = self.run_command()

        meeting.refresh_from_db()
        self.assertEqual(meeting.small_group_id, self.group.id)
        self.assertIn("safe_to_clear_small_group_mirror: 1", output)
        self.assertIn("would_clear_small_group_mirror: 1", output)
        self.assertIn("cleared_small_group_mirror: 0", output)
        self.assertIn("data_mutated: false", output)
        self.assertIn("runtime_mutated: false", output)

    def test_apply_safe_row_requires_confirmation_and_preserves_identity(self):
        lesson = self.make_lesson(title="Preserved Lesson")
        meeting = self.make_safe_meeting(lesson=lesson)
        audience_id = meeting.audience_scope_links.get().id
        expected_key = meeting.generation_key
        status = meeting.status
        kind = meeting.meeting_kind

        output = self.run_command(
            "--apply",
            "--confirm-small-group-mirror-retirement",
        )

        meeting.refresh_from_db()
        self.assertIsNone(meeting.small_group_id)
        self.assertEqual(meeting.generation_key, expected_key)
        self.assertEqual(meeting.anchor_unit_id, self.group_unit.id)
        self.assertEqual(meeting.status, status)
        self.assertEqual(meeting.lesson_id, lesson.id)
        self.assertEqual(meeting.meeting_kind, kind)
        self.assertTrue(
            BibleStudyMeetingAudienceScope.objects.filter(
                id=audience_id,
                meeting=meeting,
                unit=self.group_unit,
            ).exists()
        )
        self.assertIn("cleared_small_group_mirror: 1", output)
        self.assertIn("data_mutated: true", output)
        self.assertIn("runtime_mutated: false", output)

    def test_apply_without_confirmation_fails_and_mutates_nothing(self):
        meeting = self.make_safe_meeting()

        with self.assertRaises(CommandError):
            self.run_command("--apply")

        meeting.refresh_from_db()
        self.assertEqual(meeting.small_group_id, self.group.id)

    def test_idempotency_after_apply_reports_already_null(self):
        meeting = self.make_safe_meeting()
        self.run_command("--apply", "--confirm-small-group-mirror-retirement")

        output = self.run_command()

        meeting.refresh_from_db()
        self.assertIsNone(meeting.small_group_id)
        self.assertIn("already_null_small_group: 1", output)
        self.assertIn("would_clear_small_group_mirror: 0", output)
        self.assertIn("data_mutated: false", output)

    def test_no_audience_row_blocks(self):
        meeting = self.make_meeting()

        output = self.run_command()

        meeting.refresh_from_db()
        self.assertEqual(meeting.small_group_id, self.group.id)
        self.assertIn("blocked_no_audience_rows: 1", output)
        self.assertIn("cleanup_blockers: 1", output)

    def test_multiple_audience_rows_block(self):
        meeting = self.make_meeting()
        self.add_audience(meeting, self.group_unit)
        self.add_audience(meeting, self.other_group_unit)

        output = self.run_command()

        meeting.refresh_from_db()
        self.assertEqual(meeting.small_group_id, self.group.id)
        self.assertIn("blocked_multiple_audience_rows: 1", output)

    def test_anchor_mismatch_blocks(self):
        meeting = self.make_meeting(anchor_unit=self.other_group_unit)
        self.add_audience(meeting, self.group_unit)

        output = self.run_command()

        meeting.refresh_from_db()
        self.assertEqual(meeting.small_group_id, self.group.id)
        self.assertIn("blocked_anchor_mismatch: 1", output)

    def test_missing_generation_key_blocks(self):
        meeting = self.make_meeting(generation_key=None)
        self.add_audience(meeting, self.group_unit)

        output = self.run_command()

        meeting.refresh_from_db()
        self.assertIsNone(meeting.generation_key)
        self.assertEqual(meeting.small_group_id, self.group.id)
        self.assertIn("blocked_generation_key_missing: 1", output)

    def test_generation_key_mismatch_blocks(self):
        meeting = self.make_meeting(generation_key="normal-unit:99999")
        self.add_audience(meeting, self.group_unit)

        output = self.run_command()

        meeting.refresh_from_db()
        self.assertEqual(meeting.generation_key, "normal-unit:99999")
        self.assertEqual(meeting.small_group_id, self.group.id)
        self.assertIn("blocked_generation_key_mismatch: 1", output)

    def test_small_group_maps_to_different_unit_blocks(self):
        meeting = self.make_meeting(
            small_group=self.other_group,
            anchor_unit=self.group_unit,
            generation_key=normal_generation_key_for_unit(self.group_unit),
        )
        self.add_audience(meeting, self.group_unit)

        output = self.run_command()

        meeting.refresh_from_db()
        self.assertEqual(meeting.small_group_id, self.other_group.id)
        self.assertIn("blocked_small_group_unit_mismatch: 1", output)

    def test_non_normal_meeting_kind_blocks(self):
        meeting = self.make_meeting(meeting_kind=BibleStudyMeeting.KIND_HIGHER_LEVEL)
        self.add_audience(meeting, self.group_unit)

        output = self.run_command()

        meeting.refresh_from_db()
        self.assertEqual(meeting.small_group_id, self.group.id)
        self.assertIn("blocked_non_normal_kind: 1", output)

    def test_limit_caps_verbose_output_only_not_scan_or_apply_scope(self):
        for _index in range(3):
            self.make_safe_meeting()

        output = self.run_command(
            "--apply",
            "--confirm-small-group-mirror-retirement",
            "--verbose",
            "--limit",
            "1",
        )

        self.assertEqual(
            BibleStudyMeeting.objects.filter(small_group__isnull=True).count(),
            3,
        )
        self.assertIn("meetings_checked: 3", output)
        self.assertIn("cleared_small_group_mirror: 3", output)
        self.assertEqual(output.count("  meeting #"), 1)
        self.assertIn(
            "stopped at --limit 1; 2 more meeting decision(s) not printed",
            output,
        )

    def test_fail_on_blockers_exits_nonzero_when_blockers_exist(self):
        self.make_meeting()
        out = StringIO()

        with self.assertRaises(CommandError) as context:
            call_command(
                "cleanup_bible_study_v2_small_group_mirrors",
                "--fail-on-blockers",
                stdout=out,
            )

        self.assertIn("blocked_no_audience_rows: 1", out.getvalue())
        self.assertIn("blocked_no_audience_rows=1", str(context.exception))

    def test_command_does_not_touch_v1_session_or_series_small_group(self):
        session = BibleStudySession.objects.create(
            series=self.series,
            title="Legacy Session",
            study_datetime=timezone.now() - timezone.timedelta(days=1),
            scope_type=BibleStudySession.SCOPE_SMALL_GROUP,
            small_group=self.group,
            status=BibleStudySession.STATUS_PUBLISHED,
        )
        meeting = self.make_safe_meeting()

        self.run_command("--apply", "--confirm-small-group-mirror-retirement")

        meeting.refresh_from_db()
        session.refresh_from_db()
        self.series.refresh_from_db()
        self.assertIsNone(meeting.small_group_id)
        self.assertEqual(session.small_group_id, self.group.id)
        self.assertEqual(self.series.small_group_id, self.group.id)
