from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.utils import timezone

from accounts.models import ChurchStructureUnit, SmallGroup
from studies.models import (
    BibleStudyGuide,
    BibleStudyLesson,
    BibleStudyMeeting,
    BibleStudyMeetingAudienceScope,
    BibleStudyMeetingRole,
    BibleStudyMeetingWorshipSong,
    BibleStudySeries,
    BibleStudySession,
    BibleStudyWorshipSong,
)


class PurgeLegacyBibleStudyV1SessionsCommandTests(TestCase):
    def setUp(self):
        self.now = timezone.now()
        self.series = BibleStudySeries.objects.create(
            title="Legacy/V2 Shared Series",
            status=BibleStudySeries.STATUS_PUBLISHED,
        )
        self.root = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_ROOT,
            code="CHURCH",
            name="Whole Church",
        )
        self.group_unit = ChurchStructureUnit.objects.create(
            parent=self.root,
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="R4",
            name="Rainbow 4",
        )
        self.group = SmallGroup.objects.create(
            name="Rainbow 4",
            church_structure_unit=self.group_unit,
        )

    def run_command(self, *args):
        out = StringIO()
        call_command("purge_legacy_bible_study_v1_sessions", *args, stdout=out)
        return out.getvalue()

    def make_v1_session(self, **overrides):
        data = {
            "series": self.series,
            "title": "Legacy V1 Session",
            "study_datetime": self.now - timezone.timedelta(days=3),
            "scope_type": BibleStudySession.SCOPE_SMALL_GROUP,
            "small_group": self.group,
            "status": BibleStudySession.STATUS_PUBLISHED,
        }
        data.update(overrides)
        session = BibleStudySession.objects.create(**data)
        BibleStudyGuide.objects.create(
            session=session,
            guide_body="Pastor guide body should never print in verbose output.",
            discussion_questions="Discussion questions should not print.",
        )
        BibleStudyWorshipSong.objects.create(
            session=session,
            sort_order=1,
            title="Legacy Song",
            note="Worship notes should not print.",
        )
        return session

    def make_v2_stack(self):
        lesson = BibleStudyLesson.objects.create(
            series=self.series,
            title="V2 Lesson",
            lesson_date=timezone.localdate() + timezone.timedelta(days=7),
            status=BibleStudyLesson.STATUS_PUBLISHED,
        )
        meeting = BibleStudyMeeting.objects.create(
            lesson=lesson,
            small_group=self.group,
            meeting_datetime=self.now + timezone.timedelta(days=7),
            status=BibleStudyMeeting.STATUS_PUBLISHED,
        )
        audience = BibleStudyMeetingAudienceScope.objects.create(
            meeting=meeting,
            unit=self.group_unit,
        )
        role = BibleStudyMeetingRole.objects.create(
            meeting=meeting,
            role=BibleStudyMeetingRole.ROLE_HOST,
            display_name="Host",
        )
        song = BibleStudyMeetingWorshipSong.objects.create(
            meeting=meeting,
            sort_order=1,
            title="V2 Song",
        )
        return {
            "lesson": lesson,
            "meeting": meeting,
            "audience": audience,
            "role": role,
            "song": song,
        }

    def test_dry_run_reports_matches_and_writes_nothing(self):
        session = self.make_v1_session()

        output = self.run_command()

        self.assertTrue(BibleStudySession.objects.filter(id=session.id).exists())
        self.assertTrue(BibleStudyGuide.objects.filter(session=session).exists())
        self.assertTrue(BibleStudyWorshipSong.objects.filter(session=session).exists())
        self.assertIn("mode: dry-run", output)
        self.assertIn("apply_option_present: false", output)
        self.assertIn("confirmation_present: false", output)
        self.assertIn("data_mutated: false", output)
        self.assertIn("v1_sessions_matched: 1", output)
        self.assertIn("v1_guides_matched: 1", output)
        self.assertIn("v1_worship_songs_matched: 1", output)
        self.assertIn("v2_meetings_deleted: 0", output)

    def test_apply_without_confirmation_fails_and_deletes_nothing(self):
        session = self.make_v1_session()

        with self.assertRaises(CommandError):
            self.run_command("--apply")

        self.assertTrue(BibleStudySession.objects.filter(id=session.id).exists())
        self.assertEqual(BibleStudyGuide.objects.count(), 1)
        self.assertEqual(BibleStudyWorshipSong.objects.count(), 1)

    def test_apply_with_confirmation_deletes_only_v1_rows(self):
        session = self.make_v1_session()
        v2 = self.make_v2_stack()

        output = self.run_command(
            "--apply",
            "--confirm-v1-bible-study-retirement",
        )

        self.assertFalse(BibleStudySession.objects.filter(id=session.id).exists())
        self.assertEqual(BibleStudyGuide.objects.count(), 0)
        self.assertEqual(BibleStudyWorshipSong.objects.count(), 0)
        self.assertTrue(BibleStudySeries.objects.filter(id=self.series.id).exists())
        self.assertTrue(BibleStudyLesson.objects.filter(id=v2["lesson"].id).exists())
        self.assertTrue(BibleStudyMeeting.objects.filter(id=v2["meeting"].id).exists())
        self.assertTrue(
            BibleStudyMeetingAudienceScope.objects.filter(
                id=v2["audience"].id,
            ).exists()
        )
        self.assertTrue(BibleStudyMeetingRole.objects.filter(id=v2["role"].id).exists())
        self.assertTrue(
            BibleStudyMeetingWorshipSong.objects.filter(id=v2["song"].id).exists()
        )
        self.assertIn("mode: apply", output)
        self.assertIn("data_mutated: true", output)
        self.assertIn("v1_sessions_deleted: 1", output)
        self.assertIn("v1_guides_deleted: 1", output)
        self.assertIn("v1_worship_songs_deleted: 1", output)
        self.assertIn("v2_series_deleted: 0", output)
        self.assertIn("v2_lessons_deleted: 0", output)
        self.assertIn("v2_meetings_deleted: 0", output)
        self.assertIn("v2_meeting_roles_deleted: 0", output)
        self.assertIn("v2_meeting_worship_songs_deleted: 0", output)
        self.assertIn("church_structure_rows_deleted: 0", output)

    def test_session_id_filter_deletes_only_matching_v1_session(self):
        target = self.make_v1_session(title="Target")
        other = self.make_v1_session(title="Other")

        output = self.run_command(
            "--apply",
            "--confirm-v1-bible-study-retirement",
            "--session-id",
            str(target.id),
        )

        self.assertFalse(BibleStudySession.objects.filter(id=target.id).exists())
        self.assertTrue(BibleStudySession.objects.filter(id=other.id).exists())
        self.assertEqual(BibleStudyGuide.objects.count(), 1)
        self.assertEqual(BibleStudyWorshipSong.objects.count(), 1)
        self.assertIn("filter_session_id: {id}".format(id=target.id), output)
        self.assertIn("v1_sessions_matched: 1", output)
        self.assertIn("v1_sessions_deleted: 1", output)

    def test_verbose_limit_caps_examples_without_printing_long_child_text(self):
        first = self.make_v1_session(title="First Legacy Session")
        self.make_v1_session(title="Second Legacy Session")

        output = self.run_command("--verbose", "--limit", "1")

        self.assertIn("matched_v1_session_examples:", output)
        self.assertIn(f"session id: {first.id}", output)
        self.assertIn("stopped at --limit 1", output)
        self.assertIn("1 more matched V1 session(s) not printed", output)
        self.assertNotIn("Pastor guide body", output)
        self.assertNotIn("Discussion questions", output)
        self.assertNotIn("Worship notes", output)

    def test_reports_stable_zero_v2_deletion_counters_in_dry_run(self):
        self.make_v1_session()
        self.make_v2_stack()

        output = self.run_command("--verbose", "--limit", "1")

        self.assertIn("v2_series_deleted: 0", output)
        self.assertIn("v2_lessons_deleted: 0", output)
        self.assertIn("v2_meetings_deleted: 0", output)
        self.assertIn("v2_meeting_roles_deleted: 0", output)
        self.assertIn("v2_meeting_worship_songs_deleted: 0", output)
        self.assertIn("church_structure_rows_deleted: 0", output)
