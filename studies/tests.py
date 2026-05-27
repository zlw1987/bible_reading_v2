from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import ChurchRoleAssignment, District, SmallGroup
from .forms import BibleStudyMeetingPreparationForm
from .models import (
    BibleStudyGuide,
    BibleStudyLesson,
    BibleStudyMeeting,
    BibleStudyMeetingRole,
    BibleStudyMeetingWorshipSong,
    BibleStudySeries,
    BibleStudySession,
    BibleStudyWorshipSong,
)


class BibleStudyModuleTests(TestCase):
    def setUp(self):
        self.north = District.objects.create(name="North")
        self.south = District.objects.create(name="South")
        self.group = SmallGroup.objects.create(name="Rainbow 4", district=self.north)
        self.same_group = SmallGroup.objects.create(name="Rainbow 4B", district=self.north)
        self.other_group = SmallGroup.objects.create(name="Rainbow 5", district=self.south)

        self.user = User.objects.create_user(
            username="regular",
            email="regular@example.com",
            password="testpass123",
        )
        self.user.profile.small_group = self.group
        self.user.profile.save()

        self.same_district_user = User.objects.create_user(
            username="same_district",
            email="same@example.com",
            password="testpass123",
        )
        self.same_district_user.profile.small_group = self.same_group
        self.same_district_user.profile.save()

        self.other_user = User.objects.create_user(
            username="other_group",
            email="other@example.com",
            password="testpass123",
        )
        self.other_user.profile.small_group = self.other_group
        self.other_user.profile.save()

        self.staff = User.objects.create_user(
            username="study_staff",
            email="staff@example.com",
            password="testpass123",
            is_staff=True,
        )

        self.manager = User.objects.create_user(
            username="pastor_study",
            email="pastor@example.com",
            password="testpass123",
        )
        ChurchRoleAssignment.objects.create(
            user=self.manager,
            role=ChurchRoleAssignment.ROLE_PASTOR,
            scope_type=ChurchRoleAssignment.SCOPE_GLOBAL,
        )

        self.series = BibleStudySeries.objects.create(
            title="约翰福音查经",
            title_en="John Bible Study",
            description="一起查考约翰福音",
            description_en="Study John together",
        )
        self.future_time = timezone.now() + timezone.timedelta(days=3)
        self.prestudy_time = timezone.now() + timezone.timedelta(days=2)

    def set_language(self, language="en"):
        session = self.client.session
        session["language"] = language
        session.save()

    def create_session(self, **overrides):
        data = {
            "series": self.series,
            "title": "约翰十五章",
            "title_en": "John 15",
            "scripture_reference": "John 15:1-17",
            "prestudy_datetime": self.prestudy_time,
            "study_datetime": self.future_time,
            "scope_type": BibleStudySession.SCOPE_GLOBAL,
            "status": BibleStudySession.STATUS_PUBLISHED,
        }
        data.update(overrides)
        return BibleStudySession.objects.create(**data)

    def create_lesson(self, **overrides):
        data = {
            "series": self.series,
            "title": "约翰十五章",
            "title_en": "John 15",
            "scripture_reference": "John 15:1-17",
            "lesson_date": timezone.localdate() + timezone.timedelta(days=3),
            "prestudy_datetime": self.prestudy_time,
            "pastor_guide_body": "牧者查经指引",
            "pastor_guide_body_en": "Pastor study guide",
            "global_discussion_questions": "全教会讨论问题",
            "global_discussion_questions_en": "Church-wide questions",
            "prestudy_notes": "预查备注",
            "prestudy_notes_en": "Pre-study notes",
            "status": BibleStudyLesson.STATUS_DRAFT,
            "created_by": self.manager,
        }
        data.update(overrides)
        return BibleStudyLesson.objects.create(**data)

    def create_meeting(self, **overrides):
        lesson = overrides.pop("lesson", None) or self.create_lesson(
            status=BibleStudyLesson.STATUS_PUBLISHED,
        )
        data = {
            "lesson": lesson,
            "small_group": self.group,
            "meeting_datetime": self.future_time,
            "location": "小组家",
            "location_en": "Small group home",
            "meeting_link": "https://example.com/group-study",
            "discussion_leader_user": self.manager,
            "discussion_leader_name": "Leader fallback",
            "group_direction": "小组方向",
            "group_direction_en": "Group direction",
            "group_questions": "小组问题",
            "group_questions_en": "Group questions",
            "status": BibleStudyMeeting.STATUS_PUBLISHED,
            "created_by": self.manager,
        }
        data.update(overrides)
        return BibleStudyMeeting.objects.create(**data)

    def create_guide(self, session):
        return BibleStudyGuide.objects.create(
            session=session,
            guide_body="留意葡萄树与枝子的关系。",
            guide_body_en="Notice the vine and branches.",
            discussion_questions="我们如何常在主里面？",
            discussion_questions_en="How do we abide in Christ?",
            prestudy_notes="预查时先读上下文。",
            prestudy_notes_en="Read the context before pre-study.",
        )

    def session_post_data(self, **overrides):
        data = {
            "series": self.series.id,
            "title": "新查经",
            "title_en": "New Study",
            "scripture_reference": "John 16",
            "prestudy_datetime": self.prestudy_time.strftime("%Y-%m-%dT%H:%M"),
            "study_datetime": self.future_time.strftime("%Y-%m-%dT%H:%M"),
            "location": "Fellowship Hall",
            "meeting_link": "https://example.com/study",
            "scope_type": BibleStudySession.SCOPE_GLOBAL,
            "status": BibleStudySession.STATUS_PUBLISHED,
            "guide_body": "中文指引",
            "guide_body_en": "English guide",
            "discussion_questions": "中文问题",
            "discussion_questions_en": "English questions",
            "prestudy_notes": "中文备注",
            "prestudy_notes_en": "English notes",
        }
        data.update(overrides)
        return data

    def worship_song_post_data(self, **overrides):
        data = {
            "sort_order": 1,
            "title": "奇异恩典",
            "title_en": "Amazing Grace",
            "song_key": "G",
            "youtube_url": "https://example.com/youtube",
            "chord_url": "https://example.com/chords",
            "lyrics_url": "https://example.com/lyrics",
            "note": "司琴请用慢速。",
            "note_en": "Pianist, please use a slower tempo.",
        }
        data.update(overrides)
        return data

    def create_worship_song(self, session, **overrides):
        data = self.worship_song_post_data(**overrides)
        data["session"] = session
        return BibleStudyWorshipSong.objects.create(**data)

    def create_meeting_worship_song(self, meeting, **overrides):
        data = {
            "meeting": meeting,
            "sort_order": 1,
            "title": "奇异恩典",
            "title_en": "Amazing Grace",
            "song_key": "G",
            "youtube_url": "https://example.com/youtube",
            "chord_url": "https://example.com/chords",
            "lyrics_url": "https://example.com/lyrics",
            "arrangement_notes": "慢速开始",
            "arrangement_notes_en": "Start slowly",
            "worship_lead_user": self.manager,
            "worship_lead_name": "Worship fallback",
            "support_notes": "支援备注",
            "support_notes_en": "Support notes",
        }
        data.update(overrides)
        return BibleStudyMeetingWorshipSong.objects.create(**data)

    def meeting_worship_song_post_data(self, **overrides):
        data = {
            "sort_order": 1,
            "title": "小组敬拜诗歌",
            "title_en": "Group Worship Song",
            "song_key": "G",
            "youtube_url": "https://example.com/group-youtube",
            "chord_url": "https://example.com/group-chords",
            "lyrics_url": "https://example.com/group-lyrics",
            "arrangement_notes": "小组编排备注",
            "arrangement_notes_en": "Group arrangement notes",
            "worship_lead_user": self.manager.id,
            "worship_lead_name": "Lead fallback",
            "support_notes": "小组配搭备注",
            "support_notes_en": "Group support notes",
        }
        data.update(overrides)
        return data

    def lesson_post_data(self, **overrides):
        data = {
            "series": self.series.id,
            "title": "新查经指引",
            "title_en": "New Bible Study Guide",
            "scripture_reference": "John 16:1-15",
            "lesson_date": (
                timezone.localdate() + timezone.timedelta(days=7)
            ).strftime("%Y-%m-%d"),
            "prestudy_datetime": self.prestudy_time.strftime("%Y-%m-%dT%H:%M"),
            "pastor_guide_body": "牧者指引",
            "pastor_guide_body_en": "Pastor guide",
            "global_discussion_questions": "全教会问题",
            "global_discussion_questions_en": "Church-wide questions",
            "prestudy_notes": "预查备注",
            "prestudy_notes_en": "Pre-study notes",
            "status": BibleStudyLesson.STATUS_DRAFT,
        }
        data.update(overrides)
        return data

    def meeting_post_data(self, **overrides):
        lesson = overrides.pop("lesson", None) or self.create_lesson(
            status=BibleStudyLesson.STATUS_PUBLISHED,
        )
        data = {
            "lesson": lesson.id,
            "small_group": self.group.id,
            "meeting_datetime": self.future_time.strftime("%Y-%m-%dT%H:%M"),
            "location": "小组家",
            "location_en": "Small group home",
            "meeting_link": "https://example.com/group-study",
            "discussion_leader_user": self.manager.id,
            "discussion_leader_name": "Leader fallback",
            "group_direction": "小组方向",
            "group_direction_en": "Group direction",
            "group_questions": "小组问题",
            "group_questions_en": "Group questions",
            "status": BibleStudyMeeting.STATUS_PUBLISHED,
            "service_event": "",
        }
        data.update(overrides)
        return data

    def meeting_preparation_post_data(self, **overrides):
        data = {
            "group_direction": "Updated group direction",
            "group_direction_en": "Updated English group direction",
            "group_questions": "Updated group questions",
            "group_questions_en": "Updated English group questions",
        }
        data.update(overrides)
        return data

    def test_staff_can_access_lesson_management_list(self):
        self.set_language("en")
        self.client.login(username="study_staff", password="testpass123")

        response = self.client.get(reverse("bible_study_lesson_manage_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Bible Study Guides")
        self.assertContains(response, "New Bible Study Guide")

    def test_regular_user_cannot_access_lesson_management_list(self):
        self.set_language("en")
        self.client.login(username="regular", password="testpass123")

        response = self.client.get(reverse("bible_study_lesson_manage_list"))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("study_session_list"))

    def test_pastor_can_access_lesson_management_list(self):
        self.set_language("en")
        self.client.login(username="pastor_study", password="testpass123")

        response = self.client.get(reverse("bible_study_lesson_manage_list"))

        self.assertEqual(response.status_code, 200)

    def test_staff_can_create_bible_study_lesson(self):
        self.set_language("en")
        self.client.login(username="study_staff", password="testpass123")

        response = self.client.post(
            reverse("create_bible_study_lesson"),
            self.lesson_post_data(),
        )

        lesson = BibleStudyLesson.objects.get(title="新查经指引")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.url,
            reverse("bible_study_lesson_detail", args=[lesson.id]),
        )
        self.assertEqual(lesson.created_by, self.staff)
        self.assertEqual(lesson.status, BibleStudyLesson.STATUS_DRAFT)

    def test_staff_can_edit_bible_study_lesson(self):
        self.set_language("en")
        lesson = self.create_lesson(status=BibleStudyLesson.STATUS_DRAFT)
        self.client.login(username="study_staff", password="testpass123")

        response = self.client.post(
            reverse("edit_bible_study_lesson", args=[lesson.id]),
            self.lesson_post_data(
                title="编辑后的查经指引",
                title_en="Edited Bible Study Guide",
                status=BibleStudyLesson.STATUS_PUBLISHED,
            ),
        )

        self.assertEqual(response.status_code, 302)
        lesson.refresh_from_db()
        self.assertEqual(lesson.title, "编辑后的查经指引")
        self.assertEqual(lesson.title_en, "Edited Bible Study Guide")
        self.assertEqual(lesson.status, BibleStudyLesson.STATUS_PUBLISHED)
        self.assertIsNotNone(lesson.published_at)

    def test_staff_can_cancel_bible_study_lesson(self):
        self.set_language("en")
        lesson = self.create_lesson(status=BibleStudyLesson.STATUS_PUBLISHED)
        self.client.login(username="study_staff", password="testpass123")

        response = self.client.post(
            reverse("cancel_bible_study_lesson", args=[lesson.id]),
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("bible_study_lesson_manage_list"))
        lesson.refresh_from_db()
        self.assertEqual(lesson.status, BibleStudyLesson.STATUS_CANCELLED)

    def test_lesson_management_list_displays_created_lessons(self):
        self.set_language("en")
        lesson = self.create_lesson(
            title_en="Visible Lesson",
            scripture_reference="John 17",
        )
        self.client.login(username="study_staff", password="testpass123")

        response = self.client.get(reverse("bible_study_lesson_manage_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Visible Lesson")
        self.assertContains(response, "John 17")
        self.assertContains(
            response,
            reverse("bible_study_lesson_detail", args=[lesson.id]),
        )

    def test_lesson_detail_displays_church_wide_content(self):
        self.set_language("en")
        lesson = self.create_lesson()
        self.client.login(username="study_staff", password="testpass123")

        response = self.client.get(
            reverse("bible_study_lesson_detail", args=[lesson.id]),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Pastor Guide")
        self.assertContains(response, "Pastor study guide")
        self.assertContains(response, "Church-wide Discussion Questions")
        self.assertContains(response, "Church-wide questions")
        self.assertContains(response, "Pre-study Notes")

    def test_staff_can_access_meeting_management_list(self):
        self.set_language("en")
        self.client.login(username="study_staff", password="testpass123")

        response = self.client.get(reverse("bible_study_meeting_manage_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Small Group Bible Study Meetings")
        self.assertContains(response, "New Small Group Meeting")

    def test_regular_user_cannot_access_meeting_management_list(self):
        self.set_language("en")
        self.client.login(username="regular", password="testpass123")

        response = self.client.get(reverse("bible_study_meeting_manage_list"))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("study_session_list"))

    def test_staff_can_create_bible_study_meeting(self):
        self.set_language("en")
        lesson = self.create_lesson(status=BibleStudyLesson.STATUS_PUBLISHED)
        self.client.login(username="study_staff", password="testpass123")

        response = self.client.post(
            reverse("create_bible_study_meeting"),
            self.meeting_post_data(lesson=lesson),
        )

        meeting = BibleStudyMeeting.objects.get(lesson=lesson, small_group=self.group)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.url,
            reverse("bible_study_meeting_detail", args=[meeting.id]),
        )
        self.assertEqual(meeting.created_by, self.staff)
        self.assertIsNone(meeting.service_event)

    def test_duplicate_meeting_for_same_guide_and_group_is_rejected(self):
        lesson = self.create_lesson(status=BibleStudyLesson.STATUS_PUBLISHED)
        self.create_meeting(lesson=lesson, small_group=self.group)
        duplicate = BibleStudyMeeting(
            lesson=lesson,
            small_group=self.group,
            meeting_datetime=self.future_time,
        )

        with self.assertRaises(ValidationError):
            duplicate.full_clean()

    def test_staff_can_edit_bible_study_meeting(self):
        self.set_language("en")
        meeting = self.create_meeting(status=BibleStudyMeeting.STATUS_DRAFT)
        self.client.login(username="study_staff", password="testpass123")

        response = self.client.post(
            reverse("edit_bible_study_meeting", args=[meeting.id]),
            self.meeting_post_data(
                lesson=meeting.lesson,
                location="Updated Room",
                location_en="Updated Room",
                group_direction="更新后的小组方向",
                group_direction_en="Updated direction",
                status=BibleStudyMeeting.STATUS_PUBLISHED,
            ),
        )

        self.assertEqual(response.status_code, 302)
        meeting.refresh_from_db()
        self.assertEqual(meeting.location, "Updated Room")
        self.assertEqual(meeting.group_direction_en, "Updated direction")
        self.assertEqual(meeting.status, BibleStudyMeeting.STATUS_PUBLISHED)

    def test_staff_can_cancel_bible_study_meeting(self):
        self.set_language("en")
        meeting = self.create_meeting(status=BibleStudyMeeting.STATUS_PUBLISHED)
        self.client.login(username="study_staff", password="testpass123")

        response = self.client.post(
            reverse("cancel_bible_study_meeting", args=[meeting.id]),
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("bible_study_meeting_manage_list"))
        meeting.refresh_from_db()
        self.assertEqual(meeting.status, BibleStudyMeeting.STATUS_CANCELLED)

    def test_preparation_form_only_exposes_group_content_fields(self):
        form = BibleStudyMeetingPreparationForm()

        self.assertEqual(
            list(form.fields),
            [
                "group_direction",
                "group_direction_en",
                "group_questions",
                "group_questions_en",
            ],
        )

    def test_staff_can_access_meeting_preparation_edit_page(self):
        self.set_language("en")
        meeting = self.create_meeting(status=BibleStudyMeeting.STATUS_PUBLISHED)
        self.client.login(username="study_staff", password="testpass123")

        response = self.client.get(
            reverse("edit_bible_study_meeting_preparation", args=[meeting.id]),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Edit Group Preparation")
        self.assertContains(response, "Group Direction")
        self.assertContains(response, "Group Discussion Questions")
        self.assertNotContains(response, "Meeting Time")
        self.assertNotContains(response, "Status")

    def test_staff_can_update_meeting_preparation_only(self):
        self.set_language("en")
        other_lesson = self.create_lesson(
            status=BibleStudyLesson.STATUS_PUBLISHED,
            title_en="Different Guide",
        )
        meeting = self.create_meeting(status=BibleStudyMeeting.STATUS_PUBLISHED)
        original_lesson = meeting.lesson
        original_group = meeting.small_group
        original_datetime = meeting.meeting_datetime
        self.client.login(username="study_staff", password="testpass123")

        response = self.client.post(
            reverse("edit_bible_study_meeting_preparation", args=[meeting.id]),
            self.meeting_preparation_post_data(
                lesson=other_lesson.id,
                small_group=self.other_group.id,
                meeting_datetime=(self.future_time + timezone.timedelta(days=2)).strftime(
                    "%Y-%m-%dT%H:%M"
                ),
                status=BibleStudyMeeting.STATUS_CANCELLED,
                service_event="",
            ),
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.url,
            reverse("bible_study_meeting_detail", args=[meeting.id]),
        )
        meeting.refresh_from_db()
        self.assertEqual(meeting.group_direction, "Updated group direction")
        self.assertEqual(meeting.group_direction_en, "Updated English group direction")
        self.assertEqual(meeting.group_questions, "Updated group questions")
        self.assertEqual(meeting.group_questions_en, "Updated English group questions")
        self.assertEqual(meeting.lesson, original_lesson)
        self.assertEqual(meeting.small_group, original_group)
        self.assertEqual(meeting.meeting_datetime, original_datetime)
        self.assertEqual(meeting.status, BibleStudyMeeting.STATUS_PUBLISHED)

    def test_regular_member_cannot_access_meeting_preparation_edit_page(self):
        self.set_language("en")
        meeting = self.create_meeting(status=BibleStudyMeeting.STATUS_PUBLISHED)
        self.client.login(username="regular", password="testpass123")

        response = self.client.get(
            reverse("edit_bible_study_meeting_preparation", args=[meeting.id]),
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.url,
            reverse("bible_study_meeting_detail", args=[meeting.id]),
        )

    def test_other_group_user_cannot_access_meeting_preparation_edit_page(self):
        self.set_language("en")
        meeting = self.create_meeting(status=BibleStudyMeeting.STATUS_PUBLISHED)
        self.client.login(username="other_group", password="testpass123")

        response = self.client.get(
            reverse("edit_bible_study_meeting_preparation", args=[meeting.id]),
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("study_session_list"))

    def test_meeting_detail_shows_preparation_edit_link_only_to_manager(self):
        self.set_language("en")
        meeting = self.create_meeting(status=BibleStudyMeeting.STATUS_PUBLISHED)

        self.client.login(username="study_staff", password="testpass123")
        manager_response = self.client.get(
            reverse("bible_study_meeting_detail", args=[meeting.id]),
        )
        self.assertContains(manager_response, "Edit Group Preparation")
        self.assertContains(
            manager_response,
            reverse("edit_bible_study_meeting_preparation", args=[meeting.id]),
        )

        self.client.logout()
        self.client.login(username="regular", password="testpass123")
        member_response = self.client.get(
            reverse("bible_study_meeting_detail", args=[meeting.id]),
        )
        self.assertEqual(member_response.status_code, 200)
        self.assertNotContains(member_response, "Edit Group Preparation")

    def test_staff_can_access_meeting_worship_management_page(self):
        self.set_language("en")
        meeting = self.create_meeting(status=BibleStudyMeeting.STATUS_PUBLISHED)
        self.create_meeting_worship_song(meeting, title_en="Visible Worship Song")
        self.client.login(username="study_staff", password="testpass123")

        response = self.client.get(
            reverse("manage_bible_study_meeting_worship_songs", args=[meeting.id]),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Manage Worship Set")
        self.assertContains(response, "Add Worship Song")
        self.assertContains(response, "Visible Worship Song")

    def test_regular_user_cannot_access_meeting_worship_management_page(self):
        self.set_language("en")
        meeting = self.create_meeting(status=BibleStudyMeeting.STATUS_PUBLISHED)
        self.client.login(username="regular", password="testpass123")

        response = self.client.get(
            reverse("manage_bible_study_meeting_worship_songs", args=[meeting.id]),
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.url,
            reverse("bible_study_meeting_detail", args=[meeting.id]),
        )

    def test_regular_user_cannot_edit_or_delete_meeting_worship_song(self):
        self.set_language("en")
        meeting = self.create_meeting(status=BibleStudyMeeting.STATUS_PUBLISHED)
        song = self.create_meeting_worship_song(meeting)
        self.client.login(username="regular", password="testpass123")

        edit_response = self.client.get(
            reverse("edit_bible_study_meeting_worship_song", args=[song.id]),
        )
        delete_response = self.client.post(
            reverse("delete_bible_study_meeting_worship_song", args=[song.id]),
        )

        self.assertEqual(edit_response.status_code, 302)
        self.assertEqual(
            edit_response.url,
            reverse("bible_study_meeting_detail", args=[meeting.id]),
        )
        self.assertEqual(delete_response.status_code, 302)
        self.assertTrue(BibleStudyMeetingWorshipSong.objects.filter(id=song.id).exists())

    def test_staff_can_add_meeting_worship_song(self):
        self.set_language("en")
        meeting = self.create_meeting(status=BibleStudyMeeting.STATUS_PUBLISHED)
        self.client.login(username="study_staff", password="testpass123")

        response = self.client.post(
            reverse("manage_bible_study_meeting_worship_songs", args=[meeting.id]),
            self.meeting_worship_song_post_data(),
        )

        self.assertEqual(response.status_code, 302)
        song = BibleStudyMeetingWorshipSong.objects.get(meeting=meeting)
        self.assertEqual(song.title_en, "Group Worship Song")
        self.assertEqual(song.worship_lead_user, self.manager)

    def test_staff_can_edit_meeting_worship_song(self):
        self.set_language("en")
        meeting = self.create_meeting(status=BibleStudyMeeting.STATUS_PUBLISHED)
        song = self.create_meeting_worship_song(meeting)
        self.client.login(username="study_staff", password="testpass123")

        response = self.client.post(
            reverse("edit_bible_study_meeting_worship_song", args=[song.id]),
            self.meeting_worship_song_post_data(
                title="更新诗歌",
                title_en="Updated Worship Song",
                song_key="D",
                arrangement_notes_en="Updated arrangement",
                support_notes_en="Updated support",
            ),
        )

        self.assertEqual(response.status_code, 302)
        song.refresh_from_db()
        self.assertEqual(song.title_en, "Updated Worship Song")
        self.assertEqual(song.song_key, "D")
        self.assertEqual(song.arrangement_notes_en, "Updated arrangement")
        self.assertEqual(song.support_notes_en, "Updated support")

    def test_staff_can_delete_meeting_worship_song(self):
        self.set_language("en")
        meeting = self.create_meeting(status=BibleStudyMeeting.STATUS_PUBLISHED)
        song = self.create_meeting_worship_song(meeting)
        self.client.login(username="study_staff", password="testpass123")

        response = self.client.post(
            reverse("delete_bible_study_meeting_worship_song", args=[song.id]),
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(BibleStudyMeetingWorshipSong.objects.filter(id=song.id).exists())

    def test_duplicate_meeting_worship_sort_order_is_rejected(self):
        self.set_language("en")
        meeting = self.create_meeting(status=BibleStudyMeeting.STATUS_PUBLISHED)
        self.create_meeting_worship_song(meeting, sort_order=1)
        self.client.login(username="study_staff", password="testpass123")

        response = self.client.post(
            reverse("manage_bible_study_meeting_worship_songs", args=[meeting.id]),
            self.meeting_worship_song_post_data(sort_order=1, title_en="Duplicate"),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "This meeting already has a worship song with this order.",
        )
        self.assertEqual(meeting.worship_songs.count(), 1)

    def test_same_meeting_worship_sort_order_allowed_for_different_meetings(self):
        first_meeting = self.create_meeting(status=BibleStudyMeeting.STATUS_PUBLISHED)
        second_meeting = self.create_meeting(
            lesson=self.create_lesson(status=BibleStudyLesson.STATUS_PUBLISHED),
            status=BibleStudyMeeting.STATUS_PUBLISHED,
        )

        first = self.create_meeting_worship_song(first_meeting, sort_order=1)
        second = self.create_meeting_worship_song(second_meeting, sort_order=1)

        self.assertEqual(first.sort_order, second.sort_order)
        self.assertNotEqual(first.meeting, second.meeting)

    def test_meeting_detail_displays_worship_set_to_own_group_user(self):
        self.set_language("en")
        meeting = self.create_meeting(status=BibleStudyMeeting.STATUS_PUBLISHED)
        self.create_meeting_worship_song(
            meeting,
            title_en="Meeting Detail Song",
            arrangement_notes_en="Arrangement detail",
            support_notes_en="Support detail",
            worship_lead_user=None,
            worship_lead_name="Worship Lead Fallback",
        )
        self.client.login(username="regular", password="testpass123")

        response = self.client.get(
            reverse("bible_study_meeting_detail", args=[meeting.id]),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Worship Set")
        self.assertContains(response, "Meeting Detail Song")
        self.assertContains(response, "Key: G")
        self.assertContains(response, "Chord Link")
        self.assertContains(response, "Lyrics Link")
        self.assertContains(response, "Arrangement detail")
        self.assertContains(response, "Support detail")
        self.assertContains(response, "Worship Lead Fallback")

    def test_meeting_detail_hides_worship_set_when_parent_meeting_not_visible(self):
        self.set_language("en")
        meeting = self.create_meeting(small_group=self.other_group)
        self.create_meeting_worship_song(meeting, title_en="Hidden Meeting Song")
        self.client.login(username="regular", password="testpass123")

        response = self.client.get(
            reverse("bible_study_meeting_detail", args=[meeting.id]),
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("study_session_list"))

    def test_meeting_detail_worship_controls_are_manager_only(self):
        self.set_language("en")
        meeting = self.create_meeting(status=BibleStudyMeeting.STATUS_PUBLISHED)

        self.client.login(username="study_staff", password="testpass123")
        manager_response = self.client.get(
            reverse("bible_study_meeting_detail", args=[meeting.id]),
        )
        self.assertContains(manager_response, "Manage Worship Set")
        self.assertContains(
            manager_response,
            reverse("manage_bible_study_meeting_worship_songs", args=[meeting.id]),
        )

        self.client.logout()
        self.client.login(username="regular", password="testpass123")
        member_response = self.client.get(
            reverse("bible_study_meeting_detail", args=[meeting.id]),
        )
        self.assertEqual(member_response.status_code, 200)
        self.assertNotContains(member_response, "Manage Worship Set")
        self.assertNotContains(member_response, "Edit Worship Song")
        self.assertNotContains(member_response, "Delete")

    def test_manager_guide_detail_shows_related_meetings(self):
        self.set_language("en")
        lesson = self.create_lesson(
            status=BibleStudyLesson.STATUS_PUBLISHED,
            title_en="Guide With Meeting",
        )
        meeting = self.create_meeting(lesson=lesson, small_group=self.group)
        self.client.login(username="study_staff", password="testpass123")

        response = self.client.get(
            reverse("bible_study_lesson_detail", args=[lesson.id]),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Small Group Bible Study Meetings")
        self.assertContains(response, "Rainbow 4")
        self.assertContains(
            response,
            reverse("bible_study_meeting_detail", args=[meeting.id]),
        )

    def test_normal_user_can_view_own_published_group_meeting(self):
        self.set_language("en")
        meeting = self.create_meeting(status=BibleStudyMeeting.STATUS_PUBLISHED)
        self.client.login(username="regular", password="testpass123")

        response = self.client.get(
            reverse("bible_study_meeting_detail", args=[meeting.id]),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Small Group Bible Study Meeting")
        self.assertContains(response, "Pastor study guide")
        self.assertContains(response, "Group direction")
        self.assertContains(response, "Group Discussion Questions")

    def test_normal_user_cannot_view_another_group_meeting(self):
        self.set_language("en")
        meeting = self.create_meeting(small_group=self.other_group)
        self.client.login(username="regular", password="testpass123")

        response = self.client.get(
            reverse("bible_study_meeting_detail", args=[meeting.id]),
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("study_session_list"))

    def test_normal_user_cannot_view_draft_or_cancelled_meeting(self):
        self.set_language("en")
        draft = self.create_meeting(status=BibleStudyMeeting.STATUS_DRAFT)
        cancelled = self.create_meeting(
            lesson=self.create_lesson(status=BibleStudyLesson.STATUS_PUBLISHED),
            status=BibleStudyMeeting.STATUS_CANCELLED,
        )
        self.client.login(username="regular", password="testpass123")

        draft_response = self.client.get(
            reverse("bible_study_meeting_detail", args=[draft.id]),
        )
        cancelled_response = self.client.get(
            reverse("bible_study_meeting_detail", args=[cancelled.id]),
        )

        self.assertEqual(draft_response.status_code, 302)
        self.assertEqual(cancelled_response.status_code, 302)

    def test_staff_can_view_draft_and_cancelled_meeting(self):
        self.set_language("en")
        draft = self.create_meeting(status=BibleStudyMeeting.STATUS_DRAFT)
        cancelled = self.create_meeting(
            lesson=self.create_lesson(status=BibleStudyLesson.STATUS_PUBLISHED),
            status=BibleStudyMeeting.STATUS_CANCELLED,
        )
        self.client.login(username="study_staff", password="testpass123")

        draft_response = self.client.get(
            reverse("bible_study_meeting_detail", args=[draft.id]),
        )
        cancelled_response = self.client.get(
            reverse("bible_study_meeting_detail", args=[cancelled.id]),
        )

        self.assertEqual(draft_response.status_code, 200)
        self.assertEqual(cancelled_response.status_code, 200)

    def test_touched_chinese_guide_pages_do_not_use_course_label(self):
        self.set_language("zh")
        lesson = self.create_lesson()
        meeting = self.create_meeting(lesson=lesson)
        self.client.login(username="study_staff", password="testpass123")

        responses = [
            self.client.get(reverse("bible_study_lesson_manage_list")),
            self.client.get(reverse("bible_study_lesson_detail", args=[lesson.id])),
            self.client.get(reverse("create_bible_study_lesson")),
            self.client.get(reverse("bible_study_meeting_manage_list")),
            self.client.get(reverse("bible_study_meeting_detail", args=[meeting.id])),
            self.client.get(reverse("create_bible_study_meeting")),
        ]

        for response in responses:
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "查经指引")
            self.assertNotContains(response, "查经课程")

        preparation_response = self.client.get(
            reverse("edit_bible_study_meeting_preparation", args=[meeting.id]),
        )
        self.assertEqual(preparation_response.status_code, 200)
        self.assertNotContains(preparation_response, "查经课程")

        worship_response = self.client.get(
            reverse("manage_bible_study_meeting_worship_songs", args=[meeting.id]),
        )
        self.assertEqual(worship_response.status_code, 200)
        self.assertNotContains(worship_response, "查经课程")

    def test_v1_studies_list_route_still_uses_session_page(self):
        self.set_language("en")
        self.create_session(title_en="V1 Session")
        self.client.login(username="regular", password="testpass123")

        response = self.client.get(reverse("study_session_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Bible Studies")
        self.assertContains(response, "V1 Session")
        self.assertNotContains(response, "Bible Study Guides")

    def test_bible_study_lesson_can_be_created(self):
        lesson = self.create_lesson()

        self.assertEqual(lesson.series, self.series)
        self.assertEqual(lesson.created_by, self.manager)
        self.assertEqual(lesson.status, BibleStudyLesson.STATUS_DRAFT)

    def test_bible_study_lesson_bilingual_helpers_fall_back(self):
        lesson = self.create_lesson(
            title_en="",
            pastor_guide_body_en="",
            global_discussion_questions_en="",
            prestudy_notes_en="",
        )

        self.assertEqual(lesson.get_title("zh"), "约翰十五章")
        self.assertEqual(lesson.get_title("en"), "约翰十五章")
        self.assertEqual(lesson.get_pastor_guide_body("en"), "牧者查经指引")
        self.assertEqual(
            lesson.get_global_discussion_questions("en"),
            "全教会讨论问题",
        )
        self.assertEqual(lesson.get_prestudy_notes("en"), "预查备注")

        lesson.title_en = "John 15"
        lesson.pastor_guide_body_en = "Pastor study guide"
        lesson.global_discussion_questions_en = "Church-wide questions"
        lesson.prestudy_notes_en = "Pre-study notes"
        self.assertEqual(lesson.get_title("en"), "John 15")
        self.assertEqual(lesson.get_pastor_guide_body("en"), "Pastor study guide")
        self.assertEqual(
            lesson.get_global_discussion_questions("en"),
            "Church-wide questions",
        )
        self.assertEqual(lesson.get_prestudy_notes("en"), "Pre-study notes")

    def test_bible_study_lesson_sets_published_at_when_published(self):
        lesson = self.create_lesson()
        self.assertIsNone(lesson.published_at)

        lesson.status = BibleStudyLesson.STATUS_PUBLISHED
        lesson.save()

        self.assertIsNotNone(lesson.published_at)

    def test_bible_study_meeting_can_be_created_for_lesson_and_group(self):
        lesson = self.create_lesson(status=BibleStudyLesson.STATUS_PUBLISHED)
        meeting = self.create_meeting(lesson=lesson)

        self.assertEqual(meeting.lesson, lesson)
        self.assertEqual(meeting.small_group, self.group)
        self.assertIsNone(meeting.service_event)

    def test_bible_study_meeting_enforces_unique_lesson_small_group(self):
        lesson = self.create_lesson(status=BibleStudyLesson.STATUS_PUBLISHED)
        self.create_meeting(lesson=lesson, small_group=self.group)
        duplicate = BibleStudyMeeting(
            lesson=lesson,
            small_group=self.group,
            meeting_datetime=self.future_time,
        )

        with self.assertRaises(ValidationError):
            duplicate.full_clean()

    def test_bible_study_meeting_service_event_is_optional(self):
        meeting = self.create_meeting(service_event=None)

        self.assertIsNone(meeting.service_event)

    def test_bible_study_meeting_bilingual_helpers_work(self):
        meeting = self.create_meeting(
            location_en="",
            group_direction_en="",
            group_questions_en="",
        )

        self.assertEqual(meeting.get_location("en"), "小组家")
        self.assertEqual(meeting.get_group_direction("en"), "小组方向")
        self.assertEqual(meeting.get_group_questions("en"), "小组问题")

        meeting.location_en = "Small group home"
        meeting.group_direction_en = "Group direction"
        meeting.group_questions_en = "Group questions"
        self.assertEqual(meeting.get_location("en"), "Small group home")
        self.assertEqual(meeting.get_group_direction("en"), "Group direction")
        self.assertEqual(meeting.get_group_questions("en"), "Group questions")

    def test_bible_study_meeting_visibility_helper_is_group_scoped(self):
        meeting = self.create_meeting()

        self.assertTrue(meeting.can_be_seen_by(self.user))
        self.assertFalse(meeting.can_be_seen_by(self.other_user))
        self.assertTrue(meeting.can_be_seen_by(self.staff))

    def test_bible_study_meeting_worship_song_orders_by_sort_order(self):
        meeting = self.create_meeting()
        second = self.create_meeting_worship_song(
            meeting,
            sort_order=2,
            title="第二首",
        )
        first = self.create_meeting_worship_song(
            meeting,
            sort_order=1,
            title="第一首",
        )

        self.assertEqual(
            list(BibleStudyMeetingWorshipSong.objects.filter(meeting=meeting)),
            [first, second],
        )

    def test_bible_study_meeting_worship_song_enforces_unique_order(self):
        meeting = self.create_meeting()
        self.create_meeting_worship_song(meeting, sort_order=1)
        duplicate = BibleStudyMeetingWorshipSong(
            meeting=meeting,
            sort_order=1,
            title="Duplicate Song",
        )

        with self.assertRaises(ValidationError):
            duplicate.full_clean()

    def test_bible_study_meeting_worship_song_bilingual_helpers_work(self):
        meeting = self.create_meeting()
        song = self.create_meeting_worship_song(
            meeting,
            title_en="",
            arrangement_notes_en="",
            support_notes_en="",
        )

        self.assertEqual(song.get_title("en"), "奇异恩典")
        self.assertEqual(song.get_arrangement_notes("en"), "慢速开始")
        self.assertEqual(song.get_support_notes("en"), "支援备注")

        song.title_en = "Amazing Grace"
        song.arrangement_notes_en = "Start slowly"
        song.support_notes_en = "Support notes"
        self.assertEqual(song.get_title("en"), "Amazing Grace")
        self.assertEqual(song.get_arrangement_notes("en"), "Start slowly")
        self.assertEqual(song.get_support_notes("en"), "Support notes")

    def test_bible_study_meeting_role_accepts_allowed_role_choice(self):
        meeting = self.create_meeting()
        role = BibleStudyMeetingRole.objects.create(
            meeting=meeting,
            role=BibleStudyMeetingRole.ROLE_DISCUSSION_LEADER,
            user=self.manager,
            display_name="",
            notes="角色备注",
            notes_en="Role notes",
        )

        self.assertEqual(role.role, BibleStudyMeetingRole.ROLE_DISCUSSION_LEADER)
        self.assertEqual(role.get_display_name(), self.manager.get_username())
        self.assertEqual(role.get_notes("en"), "Role notes")

    def test_bible_study_meeting_role_rejects_invalid_role_choice(self):
        meeting = self.create_meeting()
        role = BibleStudyMeetingRole(
            meeting=meeting,
            role="scheduler",
            display_name="Invalid Role",
        )

        with self.assertRaises(ValidationError):
            role.full_clean()

    def test_study_list_requires_login(self):
        response = self.client.get(reverse("study_session_list"))

        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_published_global_session_visible_to_regular_user(self):
        self.set_language("en")
        session = self.create_session()

        self.client.login(username="regular", password="testpass123")
        response = self.client.get(reverse("study_session_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, session.title_en)

    def test_draft_session_hidden_from_regular_user(self):
        self.set_language("en")
        self.create_session(title="Draft Study", status=BibleStudySession.STATUS_DRAFT)

        self.client.login(username="regular", password="testpass123")
        response = self.client.get(reverse("study_session_list"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Draft Study")

    def test_draft_session_visible_to_staff(self):
        self.set_language("en")
        self.create_session(
            title="Draft Study",
            title_en="Draft Study",
            status=BibleStudySession.STATUS_DRAFT,
        )

        self.client.login(username="study_staff", password="testpass123")
        response = self.client.get(reverse("study_session_list"), {"tab": "drafts"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Draft Study")

    def test_district_scoped_session_visible_to_matching_district_user(self):
        self.set_language("en")
        session = self.create_session(
            title_en="North Study",
            scope_type=BibleStudySession.SCOPE_DISTRICT,
            district=self.north,
        )

        self.client.login(username="same_district", password="testpass123")
        response = self.client.get(reverse("study_session_detail", args=[session.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "North Study")

    def test_district_scoped_session_hidden_from_outside_district_user(self):
        self.set_language("en")
        session = self.create_session(
            title_en="North Study",
            scope_type=BibleStudySession.SCOPE_DISTRICT,
            district=self.north,
        )

        self.client.login(username="other_group", password="testpass123")
        response = self.client.get(reverse("study_session_detail", args=[session.id]))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("study_session_list"))

    def test_small_group_scoped_session_visible_to_same_group_user(self):
        self.set_language("en")
        session = self.create_session(
            title_en="Group Study",
            scope_type=BibleStudySession.SCOPE_SMALL_GROUP,
            small_group=self.group,
        )

        self.client.login(username="regular", password="testpass123")
        response = self.client.get(reverse("study_session_detail", args=[session.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Group Study")

    def test_small_group_scoped_session_hidden_from_different_group_user(self):
        self.set_language("en")
        session = self.create_session(
            title_en="Group Study",
            scope_type=BibleStudySession.SCOPE_SMALL_GROUP,
            small_group=self.group,
        )

        self.client.login(username="other_group", password="testpass123")
        response = self.client.get(reverse("study_session_detail", args=[session.id]))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("study_session_list"))

    def test_user_without_management_capability_cannot_access_create_page(self):
        self.set_language("en")
        self.client.login(username="regular", password="testpass123")

        response = self.client.get(reverse("create_study_session"))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("study_session_list"))

    def test_user_with_pastor_role_can_access_create_page(self):
        self.set_language("en")
        self.client.login(username="pastor_study", password="testpass123")

        response = self.client.get(reverse("create_study_session"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "New Bible Study Session")

    def test_manager_can_create_published_session_with_guide(self):
        self.set_language("en")
        self.client.login(username="pastor_study", password="testpass123")

        response = self.client.post(
            reverse("create_study_session"),
            self.session_post_data(),
        )

        self.assertEqual(response.status_code, 302)
        session = BibleStudySession.objects.get(title="新查经")
        self.assertEqual(session.created_by, self.manager)
        self.assertEqual(session.status, BibleStudySession.STATUS_PUBLISHED)
        self.assertIsNotNone(session.published_at)
        self.assertEqual(session.guide.guide_body, "中文指引")

    def test_manager_can_create_draft_session_with_guide(self):
        self.set_language("en")
        self.client.login(username="pastor_study", password="testpass123")

        response = self.client.post(
            reverse("create_study_session"),
            self.session_post_data(status=BibleStudySession.STATUS_DRAFT),
        )

        self.assertEqual(response.status_code, 302)
        session = BibleStudySession.objects.get(title="新查经")
        self.assertEqual(session.status, BibleStudySession.STATUS_DRAFT)
        self.assertIsNone(session.published_at)
        self.assertEqual(session.guide.discussion_questions, "中文问题")

    def test_manager_can_edit_session_and_guide(self):
        self.set_language("en")
        session = self.create_session(status=BibleStudySession.STATUS_DRAFT)
        self.create_guide(session)
        self.client.login(username="pastor_study", password="testpass123")

        response = self.client.post(
            reverse("edit_study_session", args=[session.id]),
            self.session_post_data(
                title="编辑后的查经",
                title_en="Edited Study",
                guide_body="更新后的指引",
                status=BibleStudySession.STATUS_PUBLISHED,
            ),
        )

        self.assertEqual(response.status_code, 302)
        session.refresh_from_db()
        self.assertEqual(session.title, "编辑后的查经")
        self.assertEqual(session.guide.guide_body, "更新后的指引")
        self.assertIsNotNone(session.published_at)

    def test_cancelling_session_hides_it_from_regular_users(self):
        self.set_language("en")
        session = self.create_session(title_en="Cancel Me")
        self.client.login(username="pastor_study", password="testpass123")
        response = self.client.post(reverse("delete_study_session", args=[session.id]))
        self.assertEqual(response.status_code, 302)
        self.client.logout()

        self.client.login(username="regular", password="testpass123")
        response = self.client.get(reverse("study_session_detail", args=[session.id]))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("study_session_list"))

    def test_scope_validation(self):
        global_session = BibleStudySession(
            series=self.series,
            title="Invalid Global",
            study_datetime=self.future_time,
            scope_type=BibleStudySession.SCOPE_GLOBAL,
            district=self.north,
        )
        district_session = BibleStudySession(
            series=self.series,
            title="Invalid District",
            study_datetime=self.future_time,
            scope_type=BibleStudySession.SCOPE_DISTRICT,
        )
        group_session = BibleStudySession(
            series=self.series,
            title="Invalid Group",
            study_datetime=self.future_time,
            scope_type=BibleStudySession.SCOPE_SMALL_GROUP,
        )

        with self.assertRaises(ValidationError):
            global_session.full_clean()
        with self.assertRaises(ValidationError):
            district_session.full_clean()
        with self.assertRaises(ValidationError):
            group_session.full_clean()

    def test_chinese_list_and_detail_pages_show_chinese_labels(self):
        self.set_language("zh")
        session = self.create_session()
        self.create_guide(session)

        self.client.login(username="regular", password="testpass123")
        list_response = self.client.get(reverse("study_session_list"))
        detail_response = self.client.get(reverse("study_session_detail", args=[session.id]))

        self.assertContains(list_response, "查经安排")
        self.assertContains(list_response, "周四预查")
        self.assertContains(list_response, "周五查经")
        self.assertContains(detail_response, "查经指引")
        self.assertContains(detail_response, "讨论问题")

    def test_english_list_and_detail_pages_show_english_labels(self):
        self.set_language("en")
        session = self.create_session()
        self.create_guide(session)

        self.client.login(username="regular", password="testpass123")
        list_response = self.client.get(reverse("study_session_list"))
        detail_response = self.client.get(reverse("study_session_detail", args=[session.id]))

        self.assertContains(list_response, "Bible Studies")
        self.assertContains(list_response, "Thursday Pre-study")
        self.assertContains(list_response, "Friday Bible Study")
        self.assertContains(detail_response, "Study Guide")
        self.assertContains(detail_response, "Discussion Questions")

    def test_home_page_shows_upcoming_visible_published_bible_study(self):
        self.set_language("en")
        session = self.create_session(title_en="Home Visible Study")

        self.client.login(username="regular", password="testpass123")
        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Bible Studies")
        self.assertContains(response, "Home Visible Study")
        self.assertContains(response, reverse("study_session_detail", args=[session.id]))

    def test_regular_user_can_see_worship_songs_on_visible_session(self):
        self.set_language("en")
        session = self.create_session()
        self.create_worship_song(session)

        self.client.login(username="regular", password="testpass123")
        response = self.client.get(reverse("study_session_detail", args=[session.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Worship Songs")
        self.assertContains(response, "Amazing Grace")
        self.assertContains(response, "Key: G")
        self.assertContains(response, "Chord Link")
        self.assertContains(response, "Lyrics Link")

    def test_regular_user_cannot_access_manage_worship_songs(self):
        self.set_language("en")
        session = self.create_session()

        self.client.login(username="regular", password="testpass123")
        response = self.client.get(reverse("manage_worship_songs", args=[session.id]))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("study_session_detail", args=[session.id]))

    def test_manager_can_access_manage_worship_songs(self):
        self.set_language("en")
        session = self.create_session()

        self.client.login(username="pastor_study", password="testpass123")
        response = self.client.get(reverse("manage_worship_songs", args=[session.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Manage Worship Songs")
        self.assertContains(response, "Add Worship Song")

    def test_manager_can_add_worship_song(self):
        self.set_language("en")
        session = self.create_session()

        self.client.login(username="pastor_study", password="testpass123")
        response = self.client.post(
            reverse("manage_worship_songs", args=[session.id]),
            self.worship_song_post_data(),
        )

        self.assertEqual(response.status_code, 302)
        song = BibleStudyWorshipSong.objects.get(session=session)
        self.assertEqual(song.title, "奇异恩典")
        self.assertEqual(song.song_key, "G")

    def test_manager_can_edit_worship_song(self):
        self.set_language("en")
        session = self.create_session()
        song = self.create_worship_song(session)

        self.client.login(username="pastor_study", password="testpass123")
        response = self.client.post(
            reverse("edit_worship_song", args=[song.id]),
            self.worship_song_post_data(
                title="新的诗歌",
                title_en="Updated Song",
                song_key="D",
            ),
        )

        self.assertEqual(response.status_code, 302)
        song.refresh_from_db()
        self.assertEqual(song.title, "新的诗歌")
        self.assertEqual(song.title_en, "Updated Song")
        self.assertEqual(song.song_key, "D")

    def test_manager_can_delete_worship_song(self):
        self.set_language("en")
        session = self.create_session()
        song = self.create_worship_song(session)

        self.client.login(username="pastor_study", password="testpass123")
        response = self.client.post(reverse("delete_worship_song", args=[song.id]))

        self.assertEqual(response.status_code, 302)
        self.assertFalse(BibleStudyWorshipSong.objects.filter(id=song.id).exists())

    def test_worship_songs_render_in_sort_order(self):
        self.set_language("en")
        session = self.create_session()
        second = self.create_worship_song(
            session,
            sort_order=2,
            title="第二首",
            title_en="Second Song",
        )
        first = self.create_worship_song(
            session,
            sort_order=1,
            title="第一首",
            title_en="First Song",
        )

        self.client.login(username="regular", password="testpass123")
        response = self.client.get(reverse("study_session_detail", args=[session.id]))

        self.assertEqual(response.status_code, 200)
        songs = list(response.context["worship_songs"])
        self.assertEqual(songs, [first, second])
        self.assertContains(response, "1. First Song")
        self.assertContains(response, "2. Second Song")

    def test_chinese_detail_page_shows_worship_song_labels(self):
        self.set_language("zh")
        session = self.create_session()
        self.create_worship_song(session)

        self.client.login(username="pastor_study", password="testpass123")
        response = self.client.get(reverse("study_session_detail", args=[session.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "查经前敬拜诗歌")
        self.assertContains(response, "管理敬拜诗歌")

    def test_english_detail_page_shows_worship_song_labels(self):
        self.set_language("en")
        session = self.create_session()
        self.create_worship_song(session)

        self.client.login(username="pastor_study", password="testpass123")
        response = self.client.get(reverse("study_session_detail", args=[session.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Worship Songs")
        self.assertContains(response, "Manage Worship Songs")

    def test_regular_user_sees_localized_empty_state_when_no_worship_songs(self):
        self.set_language("zh")
        session = self.create_session()

        self.client.login(username="regular", password="testpass123")
        response = self.client.get(reverse("study_session_detail", args=[session.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "还没有添加敬拜诗歌。")

    def test_worship_songs_hidden_when_session_not_visible(self):
        self.set_language("en")
        session = self.create_session(
            scope_type=BibleStudySession.SCOPE_SMALL_GROUP,
            small_group=self.group,
        )
        self.create_worship_song(session, title_en="Hidden Song")

        self.client.login(username="other_group", password="testpass123")
        response = self.client.get(reverse("study_session_detail", args=[session.id]))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("study_session_list"))
