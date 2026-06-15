"""BS-STRUCT.1C targeted tests for the meeting audience-scope backfill command.

These tests cover the ``backfill_bible_study_meeting_audience_scopes`` command:
its classification counters, the read-only dry-run invariants, the ``--apply``
behavior (anchor_unit backfill, idempotency, never mutating ``small_group``),
and the ``--limit`` / ``--meeting-id`` / verbose options. ``--apply`` runs only
inside the Django test database; no real database is touched.
"""

from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from accounts.models import ChurchStructureUnit, SmallGroup
from studies.models import (
    BibleStudyLesson,
    BibleStudyMeeting,
    BibleStudyMeetingAudienceScope,
    BibleStudySeries,
)


class _BackfillMeetingTestMixin:
    """Shared fixtures for the dry-run and apply tests."""

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
        self.group_unit = self.make_unit("RAINBOW4", ChurchStructureUnit.UNIT_SMALL_GROUP)

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

    def run_command(self, *args):
        out = StringIO()
        call_command(
            "backfill_bible_study_meeting_audience_scopes",
            *args,
            stdout=out,
        )
        return out.getvalue()


class BackfillMeetingAudienceDryRunTests(_BackfillMeetingTestMixin, TestCase):
    def test_dry_run_proposes_row_for_mapped_active_group_and_writes_nothing(self):
        group = self.make_group("Rainbow 4", unit=self.group_unit)
        meeting = self.make_meeting(group)

        output = self.run_command()

        self.assertIn("would_create                : 1", output)
        self.assertIn("created                     : 0", output)
        self.assertIn("parity_structural_match     : 1", output)
        self.assertIn("runtime_switched            : false", output)
        self.assertFalse(meeting.audience_scope_links.exists())
        self.assertEqual(BibleStudyMeetingAudienceScope.objects.count(), 0)

    def test_null_small_group_classified_missing(self):
        self.make_meeting(None)

        output = self.run_command()

        self.assertIn("missing_small_group         : 1", output)
        self.assertIn("would_create                : 0", output)

    def test_unmapped_small_group_classified(self):
        group = self.make_group("Unmapped", unit=None)
        self.make_meeting(group)

        output = self.run_command()

        self.assertIn("unmapped_small_group        : 1", output)
        self.assertIn("would_create                : 0", output)

    def test_inactive_mapped_unit_classified(self):
        inactive_unit = self.make_unit(
            "RAINBOW9", ChurchStructureUnit.UNIT_SMALL_GROUP, is_active=False
        )
        group = self.make_group("Inactive", unit=inactive_unit)
        self.make_meeting(group)

        output = self.run_command()

        self.assertIn("inactive_structure_unit     : 1", output)
        self.assertIn("would_create                : 0", output)

    def test_wrong_unit_type_classified(self):
        district_unit = self.make_unit("NORTH", ChurchStructureUnit.UNIT_DISTRICT)
        group = self.make_group("WrongType", unit=district_unit)
        self.make_meeting(group)

        output = self.run_command()

        self.assertIn("wrong_unit_type             : 1", output)
        self.assertIn("would_create                : 0", output)

    def test_existing_audience_rows_skipped(self):
        group = self.make_group("Rainbow 4", unit=self.group_unit)
        meeting = self.make_meeting(group)
        BibleStudyMeetingAudienceScope.objects.create(
            meeting=meeting, unit=self.group_unit
        )

        output = self.run_command()

        self.assertIn("skipped_existing_audience   : 1", output)
        self.assertIn("would_create                : 0", output)

    def test_limit_option(self):
        group = self.make_group("Rainbow 4", unit=self.group_unit)
        # Two meetings for distinct lessons so both are valid would_create.
        self.make_meeting(group, lesson=self.make_lesson(title="L1"))
        self.make_meeting(group, lesson=self.make_lesson(title="L2"))

        output = self.run_command("--limit", "1")

        self.assertIn("meetings_checked            : 1", output)

    def test_meeting_id_option(self):
        group = self.make_group("Rainbow 4", unit=self.group_unit)
        target = self.make_meeting(group, lesson=self.make_lesson(title="L1"))
        self.make_meeting(group, lesson=self.make_lesson(title="L2"))

        output = self.run_command("--meeting-id", str(target.id))

        self.assertIn("meetings_checked            : 1", output)
        self.assertIn("would_create                : 1", output)

    def test_verbose_includes_per_meeting_decision(self):
        group = self.make_group("Rainbow 4", unit=self.group_unit)
        meeting = self.make_meeting(group)

        output = self.run_command("--verbose")

        self.assertIn("per-meeting decisions:", output)
        self.assertIn(f"meeting #{meeting.id}", output)
        self.assertIn("category: would_create", output)


class BackfillMeetingAudienceApplyTests(_BackfillMeetingTestMixin, TestCase):
    def test_apply_creates_one_audience_row(self):
        group = self.make_group("Rainbow 4", unit=self.group_unit)
        meeting = self.make_meeting(group)

        output = self.run_command("--apply")

        self.assertIn("created                     : 1", output)
        rows = list(meeting.audience_scope_links.all())
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].unit_id, self.group_unit.id)

    def test_apply_sets_anchor_unit_when_null(self):
        group = self.make_group("Rainbow 4", unit=self.group_unit)
        meeting = self.make_meeting(group)
        self.assertIsNone(meeting.anchor_unit_id)

        self.run_command("--apply")

        meeting.refresh_from_db()
        self.assertEqual(meeting.anchor_unit_id, self.group_unit.id)

    def test_apply_does_not_overwrite_existing_anchor_unit(self):
        other_unit = self.make_unit("OTHER", ChurchStructureUnit.UNIT_SMALL_GROUP)
        group = self.make_group("Rainbow 4", unit=self.group_unit)
        meeting = self.make_meeting(group, anchor_unit=other_unit)

        output = self.run_command("--apply")

        meeting.refresh_from_db()
        self.assertEqual(meeting.anchor_unit_id, other_unit.id)
        self.assertIn("anchor_unit_backfilled      : 0", output)

    def test_apply_never_mutates_small_group(self):
        group = self.make_group("Rainbow 4", unit=self.group_unit)
        meeting = self.make_meeting(group)

        self.run_command("--apply")

        meeting.refresh_from_db()
        self.assertEqual(meeting.small_group_id, group.id)

    def test_second_dry_run_after_apply_is_idempotent(self):
        group = self.make_group("Rainbow 4", unit=self.group_unit)
        meeting = self.make_meeting(group)

        self.run_command("--apply")
        self.assertEqual(meeting.audience_scope_links.count(), 1)

        output = self.run_command()

        self.assertIn("skipped_existing_audience   : 1", output)
        self.assertIn("would_create                : 0", output)
        self.assertEqual(meeting.audience_scope_links.count(), 1)

    def test_second_apply_creates_no_additional_row(self):
        group = self.make_group("Rainbow 4", unit=self.group_unit)
        meeting = self.make_meeting(group)

        self.run_command("--apply")
        output = self.run_command("--apply")

        self.assertIn("created                     : 0", output)
        self.assertEqual(meeting.audience_scope_links.count(), 1)

    def test_apply_skips_unsafe_meetings(self):
        unmapped_group = self.make_group("Unmapped", unit=None)
        self.make_meeting(unmapped_group)

        output = self.run_command("--apply")

        self.assertIn("created                     : 0", output)
        self.assertIn("missing_small_group         : 0", output)
        self.assertIn("unmapped_small_group        : 1", output)
        self.assertEqual(BibleStudyMeetingAudienceScope.objects.count(), 0)

    def test_fail_on_issues_raises_when_issue_present(self):
        unmapped_group = self.make_group("Unmapped", unit=None)
        self.make_meeting(unmapped_group)

        from django.core.management.base import CommandError

        with self.assertRaises(CommandError):
            self.run_command("--fail-on-issues")
