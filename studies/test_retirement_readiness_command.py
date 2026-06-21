"""BS-STRUCT.1J targeted tests for the retirement-readiness audit command.

These cover ``audit_bible_study_structure_retirement_readiness``: its counters,
its hard-blocker classification, the ``--fail-on-blockers`` exit behavior,
``--verbose`` detail rows, and the read-only invariant that it mutates no rows.
Everything runs inside the Django test database; no real database is touched.

BS-MEETING-MIRROR.1A removed the legacy ``BibleStudyMeeting.small_group``
mirror, so the audit is fully structure-native (audience rows + anchor only).
"""

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


class _ReadinessTestMixin:
    """Shared fixtures: a small unit tree plus meeting factory."""

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
        self.district_unit = self.make_unit("NORTH", ChurchStructureUnit.UNIT_DISTRICT)
        self.group_unit = self.make_unit(
            "RAINBOW4", ChurchStructureUnit.UNIT_SMALL_GROUP, parent=self.district_unit
        )
        self.other_group_unit = self.make_unit(
            "RAINBOW5", ChurchStructureUnit.UNIT_SMALL_GROUP, parent=self.district_unit
        )

    def make_unit(self, code, unit_type, parent=None, is_active=True):
        if parent is None and unit_type != ChurchStructureUnit.UNIT_ROOT:
            parent = self.root
        return ChurchStructureUnit.objects.create(
            parent=parent,
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

    def add_row(self, meeting, unit):
        return BibleStudyMeetingAudienceScope.objects.create(meeting=meeting, unit=unit)

    def run_command(self, *args):
        out = StringIO()
        call_command(
            "audit_bible_study_structure_retirement_readiness",
            *args,
            stdout=out,
        )
        return out.getvalue()


class ReadinessCounterTests(_ReadinessTestMixin, TestCase):
    def test_fully_backfilled_meeting_has_no_blockers_and_exits_zero(self):
        meeting = self.make_meeting(anchor_unit=self.group_unit)
        self.add_row(meeting, self.group_unit)

        output = self.run_command()

        self.assertIn("meetings_checked                                : 1", output)
        self.assertIn("meetings_with_audience_rows                     : 1", output)
        self.assertIn("meetings_without_audience_rows                  : 0", output)
        self.assertIn("meetings_with_single_small_group_audience       : 1", output)
        self.assertIn("db_data_blockers_clear                          : true", output)
        self.assertIn("runtime_zero_row_fallback_removed               : true", output)
        self.assertIn("legacy_small_group_fallback_still_present       : false", output)

        # --fail-on-blockers exits 0 (no CommandError).
        self.run_command("--fail-on-blockers")

    def test_zero_row_normal_meeting_is_blocker(self):
        self.make_meeting()  # no audience rows, kind=normal

        output = self.run_command()

        self.assertIn("meetings_without_audience_rows                  : 1", output)
        self.assertIn("normal_meetings_without_audience_rows           : 1", output)
        self.assertIn("db_data_blockers_clear                          : false", output)

        with self.assertRaises(CommandError):
            self.run_command("--fail-on-blockers")

    def test_higher_level_row_is_not_blocker(self):
        meeting = self.make_meeting()
        self.add_row(meeting, self.district_unit)

        output = self.run_command()

        self.assertIn("meetings_with_audience_rows                     : 1", output)
        self.assertIn("meetings_without_audience_rows                  : 0", output)
        self.assertIn("meetings_with_higher_level_audience             : 1", output)
        self.assertIn("db_data_blockers_clear                          : true", output)

        # No blockers -> exits 0.
        self.run_command("--fail-on-blockers")

    def test_multi_unit_audience_meeting_is_counted_not_blocker(self):
        meeting = self.make_meeting()
        self.add_row(meeting, self.group_unit)
        self.add_row(meeting, self.other_group_unit)

        output = self.run_command()

        self.assertIn("meetings_with_multi_unit_audience               : 1", output)
        self.assertIn("meetings_with_single_small_group_audience       : 0", output)
        self.assertIn("meetings_without_audience_rows                  : 0", output)
        self.assertIn("db_data_blockers_clear                          : true", output)

        self.run_command("--fail-on-blockers")

    def test_missing_anchor_counted_as_warning(self):
        meeting = self.make_meeting()
        self.add_row(meeting, self.group_unit)

        output = self.run_command()

        self.assertIn("meetings_missing_anchor_unit                    : 1", output)
        self.assertIn("meetings_with_anchor_unit                       : 0", output)
        self.assertIn("db_data_blockers_clear                          : true", output)
        self.run_command("--fail-on-blockers")

    def test_verbose_lists_blocker_meeting_ids(self):
        meeting = self.make_meeting()  # zero-row blocker

        output = self.run_command("--verbose")

        self.assertIn("details (blocker and warning categories only):", output)
        self.assertIn("zero_audience_rows (1):", output)
        self.assertIn(f"meeting #{meeting.id}", output)

    def test_command_does_not_mutate_rows(self):
        meeting = self.make_meeting()
        before_meetings = BibleStudyMeeting.objects.count()
        before_rows = BibleStudyMeetingAudienceScope.objects.count()
        before_anchor = meeting.anchor_unit_id

        self.run_command()
        self.run_command("--verbose")

        self.assertEqual(BibleStudyMeeting.objects.count(), before_meetings)
        self.assertEqual(BibleStudyMeetingAudienceScope.objects.count(), before_rows)
        meeting.refresh_from_db()
        self.assertEqual(meeting.anchor_unit_id, before_anchor)
