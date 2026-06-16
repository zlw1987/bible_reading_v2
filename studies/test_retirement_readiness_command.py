"""BS-STRUCT.1J targeted tests for the retirement-readiness audit command.

These cover ``audit_bible_study_structure_retirement_readiness``: its counters,
its hard-blocker vs warning classification, the ``--fail-on-blockers`` exit
behavior, ``--verbose`` detail rows, and the read-only invariant that it mutates
no rows. Everything runs inside the Django test database; no real database is
touched.
"""

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
)


class _ReadinessTestMixin:
    """Shared fixtures: a small unit tree plus meeting/group factories."""

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

    def make_group(self, name, unit=None):
        return SmallGroup.objects.create(name=name, church_structure_unit=unit)

    def make_lesson(self, **overrides):
        data = {
            "series": self.series,
            "title": "约翰十五章",
            "lesson_date": timezone.localdate() + timezone.timedelta(days=3),
            "status": BibleStudyLesson.STATUS_PUBLISHED,
        }
        data.update(overrides)
        return BibleStudyLesson.objects.create(**data)

    def make_meeting(self, small_group, *, lesson=None, **overrides):
        data = {
            "lesson": lesson or self.make_lesson(),
            "small_group": small_group,
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
        group = self.make_group("Rainbow 4", unit=self.group_unit)
        meeting = self.make_meeting(group, anchor_unit=self.group_unit)
        self.add_row(meeting, self.group_unit)

        output = self.run_command()

        self.assertIn("meetings_checked                                : 1", output)
        self.assertIn("meetings_with_audience_rows                     : 1", output)
        self.assertIn("meetings_without_audience_rows                  : 0", output)
        self.assertIn("meetings_with_single_small_group_audience       : 1", output)
        self.assertIn("db_data_blockers_clear                          : true", output)
        self.assertIn("runtime_zero_row_fallback_removable             : false", output)
        self.assertIn("legacy_small_group_fallback_still_present       : true", output)

        # --fail-on-blockers exits 0 (no CommandError).
        self.run_command("--fail-on-blockers")

    def test_zero_row_normal_meeting_is_blocker(self):
        group = self.make_group("Rainbow 4", unit=self.group_unit)
        self.make_meeting(group)  # no audience rows, kind=normal

        output = self.run_command()

        self.assertIn("meetings_without_audience_rows                  : 1", output)
        self.assertIn("normal_meetings_without_audience_rows           : 1", output)
        self.assertIn("db_data_blockers_clear                          : false", output)

        with self.assertRaises(CommandError):
            self.run_command("--fail-on-blockers")

    def test_null_small_group_zero_rows_is_blocker(self):
        self.make_meeting(None)  # null small_group, no rows

        output = self.run_command()

        self.assertIn("meetings_with_null_small_group                  : 1", output)
        self.assertIn("meetings_without_audience_rows                  : 1", output)
        self.assertIn("db_data_blockers_clear                          : false", output)

        with self.assertRaises(CommandError):
            self.run_command("--fail-on-blockers")

    def test_null_small_group_with_higher_level_row_is_not_blocker(self):
        meeting = self.make_meeting(None)
        self.add_row(meeting, self.district_unit)

        output = self.run_command()

        self.assertIn("meetings_with_audience_rows                     : 1", output)
        self.assertIn("meetings_without_audience_rows                  : 0", output)
        self.assertIn("meetings_with_existing_audience_and_null_small_group : 1", output)
        self.assertIn("meetings_with_higher_level_audience             : 1", output)
        self.assertIn("db_data_blockers_clear                          : true", output)

        # No blockers -> exits 0.
        self.run_command("--fail-on-blockers")

    def test_multi_unit_audience_meeting_is_counted_not_blocker(self):
        meeting = self.make_meeting(None)
        self.add_row(meeting, self.group_unit)
        self.add_row(meeting, self.other_group_unit)

        output = self.run_command()

        self.assertIn("meetings_with_multi_unit_audience               : 1", output)
        self.assertIn("meetings_with_single_small_group_audience       : 0", output)
        self.assertIn("meetings_without_audience_rows                  : 0", output)
        self.assertIn("db_data_blockers_clear                          : true", output)

        self.run_command("--fail-on-blockers")

    def test_unmapped_small_group_counted_as_warning(self):
        # Audience row present so the meeting is not a zero-row blocker; the
        # broken mirror is a warning only.
        group = self.make_group("Unmapped", unit=None)
        meeting = self.make_meeting(group)
        self.add_row(meeting, self.group_unit)

        output = self.run_command()

        self.assertIn("meetings_small_group_unmapped                   : 1", output)
        self.assertIn("db_data_blockers_clear                          : true", output)
        self.run_command("--fail-on-blockers")

    def test_inactive_small_group_unit_counted_as_warning(self):
        inactive_unit = self.make_unit(
            "RAINBOW9", ChurchStructureUnit.UNIT_SMALL_GROUP, is_active=False
        )
        group = self.make_group("Inactive", unit=inactive_unit)
        meeting = self.make_meeting(group)
        self.add_row(meeting, self.group_unit)

        output = self.run_command()

        self.assertIn("meetings_small_group_inactive_unit              : 1", output)
        self.assertIn("db_data_blockers_clear                          : true", output)
        self.run_command("--fail-on-blockers")

    def test_wrong_type_small_group_unit_counted_as_warning(self):
        group = self.make_group("WrongType", unit=self.district_unit)
        meeting = self.make_meeting(group)
        # Single small-group row, mirror maps to a district (wrong type) -> no
        # mismatch blocker (rule 2 only compares to an active UNIT_SMALL_GROUP).
        self.add_row(meeting, self.group_unit)

        output = self.run_command()

        self.assertIn("meetings_small_group_wrong_unit_type            : 1", output)
        self.assertIn("meetings_audience_mismatch_small_group_mirror   : 0", output)
        self.assertIn("db_data_blockers_clear                          : true", output)
        self.run_command("--fail-on-blockers")

    def test_single_row_mismatching_mirror_is_blocker(self):
        # small_group maps to group_unit but the single audience row points at a
        # different active small-group unit -> mismatch blocker (rule 2).
        group = self.make_group("Rainbow 4", unit=self.group_unit)
        meeting = self.make_meeting(group)
        self.add_row(meeting, self.other_group_unit)

        output = self.run_command()

        self.assertIn("meetings_audience_mismatch_small_group_mirror   : 1", output)
        self.assertIn("db_data_blockers_clear                          : false", output)

        with self.assertRaises(CommandError):
            self.run_command("--fail-on-blockers")

    def test_anchor_mismatch_counted_as_warning(self):
        group = self.make_group("Rainbow 4", unit=self.group_unit)
        meeting = self.make_meeting(group, anchor_unit=self.other_group_unit)
        self.add_row(meeting, self.group_unit)

        output = self.run_command()

        self.assertIn("meetings_anchor_mismatch_small_group_unit       : 1", output)
        self.assertIn("db_data_blockers_clear                          : true", output)
        self.run_command("--fail-on-blockers")

    def test_missing_anchor_counted_as_warning(self):
        group = self.make_group("Rainbow 4", unit=self.group_unit)
        meeting = self.make_meeting(group)
        self.add_row(meeting, self.group_unit)

        output = self.run_command()

        self.assertIn("meetings_missing_anchor_unit                    : 1", output)
        self.assertIn("meetings_with_anchor_unit                       : 0", output)
        self.assertIn("db_data_blockers_clear                          : true", output)
        self.run_command("--fail-on-blockers")

    def test_verbose_lists_blocker_meeting_ids(self):
        group = self.make_group("Rainbow 4", unit=self.group_unit)
        meeting = self.make_meeting(group)  # zero-row blocker

        output = self.run_command("--verbose")

        self.assertIn("details (blocker and warning categories only):", output)
        self.assertIn("zero_audience_rows (1):", output)
        self.assertIn(f"meeting #{meeting.id}", output)

    def test_command_does_not_mutate_rows(self):
        group = self.make_group("Rainbow 4", unit=self.group_unit)
        meeting = self.make_meeting(group)
        before_meetings = BibleStudyMeeting.objects.count()
        before_rows = BibleStudyMeetingAudienceScope.objects.count()
        before_anchor = meeting.anchor_unit_id
        before_small_group = meeting.small_group_id

        self.run_command()
        self.run_command("--verbose")

        self.assertEqual(BibleStudyMeeting.objects.count(), before_meetings)
        self.assertEqual(BibleStudyMeetingAudienceScope.objects.count(), before_rows)
        meeting.refresh_from_db()
        self.assertEqual(meeting.anchor_unit_id, before_anchor)
        self.assertEqual(meeting.small_group_id, before_small_group)
