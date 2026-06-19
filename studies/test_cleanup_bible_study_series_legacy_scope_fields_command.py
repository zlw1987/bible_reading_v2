from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.utils import timezone

from accounts.management.commands.audit_legacy_structure_retirement_readiness import (
    run_audit as run_legacy_retirement_audit,
)
from accounts.models import (
    ChurchStructureUnit,
    District,
    MinistryContext,
    SmallGroup,
)
from studies.models import (
    BibleStudyLesson,
    BibleStudyMeeting,
    BibleStudyMeetingAudienceScope,
    BibleStudySeries,
    BibleStudySeriesAudienceScope,
    BibleStudySession,
)


class CleanupBibleStudySeriesLegacyScopeFieldsCommandTests(TestCase):
    def setUp(self):
        self.today = timezone.localdate()
        self.future_time = timezone.now() + timezone.timedelta(days=3)
        self.root = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_ROOT,
            code="CHURCH",
            name="Whole Church",
        )
        self.ministry_unit = self.make_unit(
            "CM",
            ChurchStructureUnit.UNIT_MINISTRY_CONTEXT,
            parent=self.root,
        )
        self.district_unit = self.make_unit(
            "NORTH",
            ChurchStructureUnit.UNIT_DISTRICT,
            parent=self.ministry_unit,
        )
        self.group_unit = self.make_unit(
            "R4",
            ChurchStructureUnit.UNIT_SMALL_GROUP,
            parent=self.district_unit,
        )
        self.other_group_unit = self.make_unit(
            "R5",
            ChurchStructureUnit.UNIT_SMALL_GROUP,
            parent=self.district_unit,
        )
        self.ministry_context = MinistryContext.objects.create(
            code="CM",
            name="Chinese Ministry",
            church_structure_unit=self.ministry_unit,
        )
        self.district = District.objects.create(
            name="North",
            ministry_context=self.ministry_context,
            church_structure_unit=self.district_unit,
        )
        self.group = SmallGroup.objects.create(
            name="Rainbow 4",
            district=self.district,
            church_structure_unit=self.group_unit,
        )

    def make_unit(self, code, unit_type, *, parent=None, is_active=True):
        return ChurchStructureUnit.objects.create(
            parent=parent or self.root,
            unit_type=unit_type,
            code=code,
            name=code,
            is_active=is_active,
        )

    def make_series(self, **overrides):
        data = {
            "title": "Legacy-scoped Series",
            "start_date": self.today,
            "end_date": self.today + timezone.timedelta(days=7),
            "status": BibleStudySeries.STATUS_PUBLISHED,
            "scope_type": BibleStudySeries.SCOPE_SMALL_GROUP,
            "small_group": self.group,
        }
        data.update(overrides)
        return BibleStudySeries.objects.create(**data)

    def add_series_audience(self, series, unit=None):
        return BibleStudySeriesAudienceScope.objects.create(
            series=series,
            unit=unit or self.group_unit,
        )

    def make_lesson(self, series, **overrides):
        data = {
            "series": series,
            "title": "Preserved Lesson",
            "lesson_date": self.today + timezone.timedelta(days=3),
            "status": BibleStudyLesson.STATUS_PUBLISHED,
        }
        data.update(overrides)
        return BibleStudyLesson.objects.create(**data)

    def make_meeting(self, lesson, **overrides):
        data = {
            "lesson": lesson,
            "meeting_datetime": self.future_time,
            "meeting_kind": BibleStudyMeeting.KIND_NORMAL,
            "status": BibleStudyMeeting.STATUS_PUBLISHED,
        }
        data.update(overrides)
        return BibleStudyMeeting.objects.create(**data)

    def run_command(self, *args):
        out = StringIO()
        call_command(
            "cleanup_bible_study_series_legacy_scope_fields",
            *args,
            stdout=out,
        )
        return out.getvalue()

    def test_dry_run_safe_series_reports_would_clear_and_writes_nothing(self):
        series = self.make_series()
        self.add_series_audience(series)

        output = self.run_command()

        series.refresh_from_db()
        self.assertEqual(series.scope_type, BibleStudySeries.SCOPE_SMALL_GROUP)
        self.assertEqual(series.small_group_id, self.group.id)
        self.assertIn("safe_to_clear_legacy_scope_fields: 1", output)
        self.assertIn("would_clear_legacy_scope_fields: 1", output)
        self.assertIn("cleared_legacy_scope_fields: 0", output)
        self.assertIn("data_mutated: false", output)
        self.assertIn("runtime_mutated: false", output)

    def test_apply_safe_series_requires_confirmation_and_preserves_related_rows(self):
        series = self.make_series(title="Preserved Series")
        audience = self.add_series_audience(series)
        lesson = self.make_lesson(series)
        meeting = self.make_meeting(lesson)
        meeting_audience = BibleStudyMeetingAudienceScope.objects.create(
            meeting=meeting,
            unit=self.group_unit,
        )
        expected = {
            "title": series.title,
            "status": series.status,
            "start_date": series.start_date,
            "end_date": series.end_date,
            "published_at": series.published_at,
            "is_active": series.is_active,
        }

        output = self.run_command(
            "--apply",
            "--confirm-series-legacy-scope-retirement",
        )

        series.refresh_from_db()
        lesson.refresh_from_db()
        meeting.refresh_from_db()
        self.assertEqual(series.scope_type, BibleStudySeries.SCOPE_GLOBAL)
        self.assertIsNone(series.ministry_context_id)
        self.assertIsNone(series.district_id)
        self.assertIsNone(series.small_group_id)
        self.assertEqual(series.title, expected["title"])
        self.assertEqual(series.status, expected["status"])
        self.assertEqual(series.start_date, expected["start_date"])
        self.assertEqual(series.end_date, expected["end_date"])
        self.assertEqual(series.published_at, expected["published_at"])
        self.assertEqual(series.is_active, expected["is_active"])
        self.assertTrue(
            BibleStudySeriesAudienceScope.objects.filter(
                id=audience.id,
                series=series,
                unit=self.group_unit,
            ).exists()
        )
        self.assertEqual(lesson.series_id, series.id)
        self.assertTrue(BibleStudyLesson.objects.filter(id=lesson.id).exists())
        self.assertTrue(BibleStudyMeeting.objects.filter(id=meeting.id).exists())
        self.assertTrue(
            BibleStudyMeetingAudienceScope.objects.filter(
                id=meeting_audience.id,
                meeting=meeting,
                unit=self.group_unit,
            ).exists()
        )
        self.assertIn("cleared_legacy_scope_fields: 1", output)
        self.assertIn("data_mutated: true", output)
        self.assertIn("runtime_mutated: false", output)

    def test_apply_without_confirmation_fails_and_mutates_nothing(self):
        series = self.make_series()
        self.add_series_audience(series)

        with self.assertRaises(CommandError):
            self.run_command("--apply")

        series.refresh_from_db()
        self.assertEqual(series.scope_type, BibleStudySeries.SCOPE_SMALL_GROUP)
        self.assertEqual(series.small_group_id, self.group.id)

    def test_idempotency_after_apply_reports_already_clear(self):
        series = self.make_series()
        self.add_series_audience(series)
        self.run_command("--apply", "--confirm-series-legacy-scope-retirement")

        output = self.run_command()

        series.refresh_from_db()
        self.assertEqual(series.scope_type, BibleStudySeries.SCOPE_GLOBAL)
        self.assertIsNone(series.small_group_id)
        self.assertIn("series_without_legacy_scope_fields: 1", output)
        self.assertIn("would_clear_legacy_scope_fields: 0", output)
        self.assertIn("category: already_clear", self.run_command("--verbose"))
        self.assertIn("data_mutated: false", output)

    def test_populated_legacy_fields_with_zero_audience_rows_blocks(self):
        series = self.make_series()

        output = self.run_command()

        series.refresh_from_db()
        self.assertEqual(series.small_group_id, self.group.id)
        self.assertIn("blocked_no_audience_rows: 1", output)
        self.assertIn("cleanup_blockers: 1", output)

    def test_inactive_audience_unit_blocks(self):
        inactive_unit = self.make_unit(
            "OLD",
            ChurchStructureUnit.UNIT_SMALL_GROUP,
            is_active=False,
        )
        series = self.make_series()
        BibleStudySeriesAudienceScope.objects.bulk_create(
            [BibleStudySeriesAudienceScope(series=series, unit=inactive_unit)]
        )

        output = self.run_command()

        series.refresh_from_db()
        self.assertEqual(series.small_group_id, self.group.id)
        self.assertIn("blocked_inactive_audience_unit: 1", output)

    def test_root_combined_with_another_unit_blocks(self):
        series = self.make_series()
        BibleStudySeriesAudienceScope.objects.bulk_create(
            [
                BibleStudySeriesAudienceScope(series=series, unit=self.root),
                BibleStudySeriesAudienceScope(series=series, unit=self.group_unit),
            ]
        )

        output = self.run_command()

        series.refresh_from_db()
        self.assertEqual(series.small_group_id, self.group.id)
        self.assertIn("blocked_root_combined_with_other_units: 1", output)

    def test_ancestor_and_descendant_audience_units_block(self):
        series = self.make_series()
        BibleStudySeriesAudienceScope.objects.bulk_create(
            [
                BibleStudySeriesAudienceScope(series=series, unit=self.district_unit),
                BibleStudySeriesAudienceScope(series=series, unit=self.group_unit),
            ]
        )

        output = self.run_command()

        series.refresh_from_db()
        self.assertEqual(series.small_group_id, self.group.id)
        self.assertIn("blocked_ancestor_descendant_units: 1", output)

    def test_limit_caps_verbose_output_only_not_scan_or_apply_scope(self):
        for index in range(3):
            series = self.make_series(title=f"Series {index}")
            self.add_series_audience(series, self.group_unit)

        output = self.run_command(
            "--apply",
            "--confirm-series-legacy-scope-retirement",
            "--verbose",
            "--limit",
            "1",
        )

        self.assertEqual(
            BibleStudySeries.objects.filter(
                scope_type=BibleStudySeries.SCOPE_GLOBAL,
                small_group__isnull=True,
            ).count(),
            3,
        )
        self.assertIn("series_checked: 3", output)
        self.assertIn("cleared_legacy_scope_fields: 3", output)
        self.assertEqual(output.count("  series #"), 1)
        self.assertIn(
            "stopped at --limit 1; 2 more series decision(s) not printed",
            output,
        )

    def test_fail_on_blockers_exits_nonzero_when_blockers_exist(self):
        self.make_series()
        out = StringIO()

        with self.assertRaises(CommandError) as context:
            call_command(
                "cleanup_bible_study_series_legacy_scope_fields",
                "--fail-on-blockers",
                stdout=out,
            )

        self.assertIn("blocked_no_audience_rows: 1", out.getvalue())
        self.assertIn("blocked_no_audience_rows=1", str(context.exception))

    def test_command_does_not_touch_v1_session_meeting_or_meeting_audience(self):
        series = self.make_series()
        self.add_series_audience(series)
        lesson = self.make_lesson(series)
        meeting = self.make_meeting(
            lesson,
            small_group=self.group,
            anchor_unit=self.group_unit,
        )
        meeting_audience = BibleStudyMeetingAudienceScope.objects.create(
            meeting=meeting,
            unit=self.group_unit,
        )
        session = BibleStudySession.objects.create(
            series=series,
            title="Legacy Session",
            study_datetime=timezone.now() - timezone.timedelta(days=1),
            scope_type=BibleStudySession.SCOPE_SMALL_GROUP,
            small_group=self.group,
            status=BibleStudySession.STATUS_PUBLISHED,
        )

        self.run_command("--apply", "--confirm-series-legacy-scope-retirement")

        series.refresh_from_db()
        meeting.refresh_from_db()
        session.refresh_from_db()
        self.assertEqual(series.scope_type, BibleStudySeries.SCOPE_GLOBAL)
        self.assertEqual(meeting.small_group_id, self.group.id)
        self.assertEqual(meeting.anchor_unit_id, self.group_unit.id)
        self.assertEqual(session.small_group_id, self.group.id)
        self.assertTrue(
            BibleStudyMeetingAudienceScope.objects.filter(
                id=meeting_audience.id,
                meeting=meeting,
                unit=self.group_unit,
            ).exists()
        )

    def test_audit_alignment_after_apply_reports_no_series_legacy_scope_fields(self):
        series = self.make_series()
        self.add_series_audience(series)

        self.run_command("--apply", "--confirm-series-legacy-scope-retirement")
        audit = run_legacy_retirement_audit(
            target_date=self.today,
            now=timezone.now(),
        )
        stats = audit["stats"]

        self.assertEqual(stats["bible_study_series_with_audience_rows"], 1)
        self.assertEqual(stats["bible_study_series_without_audience_rows"], 0)
        self.assertEqual(stats["bible_study_active_series_without_audience_rows"], 0)
        self.assertEqual(stats["bible_study_series_with_legacy_scope_fields_set"], 0)
        self.assertEqual(stats["bible_study_legacy_retirement_blockers"], 0)
