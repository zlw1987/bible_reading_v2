from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import ChurchRoleAssignment, District, SmallGroup
from events.models import ServiceEvent
from ministry.models import TeamAssignment
from .forms import (
    BibleStudyMeetingForm,
    BibleStudyMeetingPreparationForm,
    BibleStudyMeetingRoleForm,
    BibleStudyMeetingWorshipSongForm,
)
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

    def create_meeting_role(self, meeting, **overrides):
        data = {
            "meeting": meeting,
            "role": BibleStudyMeetingRole.ROLE_DISCUSSION_LEADER,
            "user": self.user,
            "display_name": "",
            "notes": "角色备注",
            "notes_en": "Role notes",
        }
        data.update(overrides)
        return BibleStudyMeetingRole.objects.create(**data)

    def meeting_role_post_data(self, **overrides):
        data = {
            "role": BibleStudyMeetingRole.ROLE_DISCUSSION_LEADER,
            "user": self.user.id,
            "display_name": "",
            "notes": "查经带领备注",
            "notes_en": "Discussion leader notes",
        }
        data.update(overrides)
        return data

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
            "worship_lead_user": self.user.id,
            "worship_lead_name": "Lead fallback",
            "support_notes": "小组配搭备注",
            "support_notes_en": "Group support notes",
        }
        data.update(overrides)
        return data

    def schedule_post_data(self, **overrides):
        start_date = timezone.localdate() + timezone.timedelta(days=7)
        end_date = start_date + timezone.timedelta(days=84)
        data = {
            "title": "春季查经安排",
            "title_en": "Spring Bible Study Schedule",
            "description": "春季每周查经安排",
            "description_en": "Spring weekly Bible Study schedule",
            "start_date": start_date.strftime("%Y-%m-%d"),
            "end_date": end_date.strftime("%Y-%m-%d"),
            "status": BibleStudySeries.STATUS_PUBLISHED,
            "scope_type": BibleStudySeries.SCOPE_GLOBAL,
            "district": "",
            "small_group": "",
            "is_active": "on",
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
        self.assertContains(response, "Weekly Bible Study Guides")
        self.assertContains(response, "New Weekly Bible Study Guide")
        self.assertContains(response, "Bible Study Schedule")

    def test_staff_can_access_schedule_management_list(self):
        self.set_language("en")
        self.create_lesson(series=self.series)
        self.client.login(username="study_staff", password="testpass123")

        response = self.client.get(reverse("bible_study_schedule_manage_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Bible Study Schedules")
        self.assertContains(response, "Manage Bible Study schedules")
        self.assertContains(response, "New Bible Study Schedule")
        self.assertContains(response, "John Bible Study")
        self.assertContains(response, "Date Range")
        self.assertContains(response, "Scope")
        self.assertContains(response, "Whole Church")
        self.assertContains(response, "Status")
        self.assertContains(response, "Weekly Guides")
        self.assertContains(response, "1")
        self.assertNotContains(response, "Series")

    def test_regular_user_cannot_access_schedule_management_list(self):
        self.set_language("en")
        self.client.login(username="regular", password="testpass123")

        response = self.client.get(reverse("bible_study_schedule_manage_list"))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("study_session_list"))

    def test_staff_can_create_bible_study_schedule(self):
        self.set_language("en")
        self.client.login(username="study_staff", password="testpass123")

        response = self.client.post(
            reverse("create_bible_study_schedule"),
            self.schedule_post_data(),
        )

        schedule = BibleStudySeries.objects.get(title="春季查经安排")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.url,
            reverse("bible_study_schedule_detail", args=[schedule.id]),
        )
        self.assertEqual(schedule.title_en, "Spring Bible Study Schedule")
        self.assertEqual(schedule.status, BibleStudySeries.STATUS_PUBLISHED)
        self.assertEqual(schedule.scope_type, BibleStudySeries.SCOPE_GLOBAL)
        self.assertIsNone(schedule.district)
        self.assertIsNone(schedule.small_group)
        self.assertIsNotNone(schedule.published_at)
        self.assertEqual(schedule.created_by, self.staff)
        self.assertTrue(schedule.is_active)

    def test_staff_can_create_bible_study_schedule_with_district_scope(self):
        self.set_language("en")
        self.client.login(username="study_staff", password="testpass123")

        response = self.client.post(
            reverse("create_bible_study_schedule"),
            self.schedule_post_data(
                title="分区查经安排",
                title_en="District Bible Study Schedule",
                scope_type=BibleStudySeries.SCOPE_DISTRICT,
                district=self.north.id,
            ),
        )

        schedule = BibleStudySeries.objects.get(title="分区查经安排")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(schedule.scope_type, BibleStudySeries.SCOPE_DISTRICT)
        self.assertEqual(schedule.district, self.north)
        self.assertIsNone(schedule.small_group)

    def test_staff_can_create_bible_study_schedule_with_small_group_scope(self):
        self.set_language("en")
        self.client.login(username="study_staff", password="testpass123")

        response = self.client.post(
            reverse("create_bible_study_schedule"),
            self.schedule_post_data(
                title="小组查经安排",
                title_en="Small Group Bible Study Schedule",
                scope_type=BibleStudySeries.SCOPE_SMALL_GROUP,
                small_group=self.group.id,
            ),
        )

        schedule = BibleStudySeries.objects.get(title="小组查经安排")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(schedule.scope_type, BibleStudySeries.SCOPE_SMALL_GROUP)
        self.assertEqual(schedule.small_group, self.group)
        self.assertIsNone(schedule.district)

    def test_staff_can_edit_bible_study_schedule(self):
        self.set_language("en")
        self.client.login(username="study_staff", password="testpass123")
        original_created_by = self.series.created_by
        start_date = timezone.localdate() + timezone.timedelta(days=14)
        end_date = start_date + timezone.timedelta(days=70)
        post_data = self.schedule_post_data(
            title="更新后的查经安排",
            title_en="Updated Bible Study Schedule",
            start_date=start_date.strftime("%Y-%m-%d"),
            end_date=end_date.strftime("%Y-%m-%d"),
            status=BibleStudySeries.STATUS_COMPLETED,
        )
        post_data.pop("is_active")

        response = self.client.post(
            reverse("edit_bible_study_schedule", args=[self.series.id]),
            post_data,
        )

        self.assertEqual(response.status_code, 302)
        self.series.refresh_from_db()
        self.assertEqual(self.series.title, "更新后的查经安排")
        self.assertEqual(self.series.title_en, "Updated Bible Study Schedule")
        self.assertEqual(self.series.start_date, start_date)
        self.assertEqual(self.series.end_date, end_date)
        self.assertEqual(self.series.status, BibleStudySeries.STATUS_COMPLETED)
        self.assertEqual(self.series.scope_type, BibleStudySeries.SCOPE_GLOBAL)
        self.assertEqual(self.series.created_by, original_created_by)
        self.assertFalse(self.series.is_active)

    def test_staff_can_edit_bible_study_schedule_to_district_scope(self):
        self.set_language("en")
        self.client.login(username="study_staff", password="testpass123")

        response = self.client.post(
            reverse("edit_bible_study_schedule", args=[self.series.id]),
            self.schedule_post_data(
                title=self.series.title,
                title_en=self.series.title_en,
                scope_type=BibleStudySeries.SCOPE_DISTRICT,
                district=self.north.id,
            ),
        )

        self.assertEqual(response.status_code, 302)
        self.series.refresh_from_db()
        self.assertEqual(self.series.scope_type, BibleStudySeries.SCOPE_DISTRICT)
        self.assertEqual(self.series.district, self.north)
        self.assertIsNone(self.series.small_group)

    def test_staff_can_edit_bible_study_schedule_to_small_group_scope(self):
        self.set_language("en")
        self.client.login(username="study_staff", password="testpass123")

        response = self.client.post(
            reverse("edit_bible_study_schedule", args=[self.series.id]),
            self.schedule_post_data(
                title=self.series.title,
                title_en=self.series.title_en,
                scope_type=BibleStudySeries.SCOPE_SMALL_GROUP,
                small_group=self.group.id,
            ),
        )

        self.assertEqual(response.status_code, 302)
        self.series.refresh_from_db()
        self.assertEqual(self.series.scope_type, BibleStudySeries.SCOPE_SMALL_GROUP)
        self.assertEqual(self.series.small_group, self.group)
        self.assertIsNone(self.series.district)

    def test_schedule_detail_shows_related_weekly_guides(self):
        self.set_language("en")
        self.series.start_date = timezone.localdate() + timezone.timedelta(days=7)
        self.series.end_date = self.series.start_date + timezone.timedelta(days=84)
        self.series.status = BibleStudySeries.STATUS_PUBLISHED
        self.series.save()
        lesson = self.create_lesson(
            series=self.series,
            status=BibleStudyLesson.STATUS_PUBLISHED,
            title_en="Schedule Detail Guide",
        )
        self.client.login(username="study_staff", password="testpass123")

        response = self.client.get(
            reverse("bible_study_schedule_detail", args=[self.series.id]),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Bible Study Schedule")
        self.assertContains(response, "Date Range")
        self.assertContains(response, "Scope")
        self.assertContains(response, "Whole Church")
        self.assertContains(response, "Published")
        self.assertContains(response, "Schedule Detail Guide")
        self.assertContains(response, "John 15:1-17")
        self.assertContains(response, "Add Weekly Bible Study Guide")
        self.assertContains(
            response,
            f"{reverse('create_bible_study_lesson')}?series={self.series.id}",
        )
        self.assertContains(
            response,
            reverse("bible_study_lesson_detail", args=[lesson.id]),
        )
        self.assertContains(
            response,
            "Meeting generation from guide/scope is planned for a later phase.",
        )
        self.assertNotContains(response, "Series")

    def test_schedule_form_uses_schedule_labels(self):
        self.set_language("en")
        self.client.login(username="study_staff", password="testpass123")

        response = self.client.get(reverse("create_bible_study_schedule"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "New Bible Study Schedule")
        self.assertContains(response, "Bible Study Schedule Title")
        self.assertContains(response, "English Schedule Title")
        self.assertContains(response, "Start Date")
        self.assertContains(response, "End Date")
        self.assertContains(response, "Status")
        self.assertContains(response, "Scope")
        self.assertContains(response, "Whole Church")
        self.assertContains(response, "District")
        self.assertContains(response, "Small Group")
        self.assertNotContains(response, "Series")

    def test_chinese_schedule_pages_use_schedule_wording(self):
        self.set_language("zh")
        self.client.login(username="study_staff", password="testpass123")

        list_response = self.client.get(reverse("bible_study_schedule_manage_list"))
        form_response = self.client.get(reverse("create_bible_study_schedule"))
        detail_response = self.client.get(
            reverse("bible_study_schedule_detail", args=[self.series.id]),
        )

        for response in [list_response, form_response, detail_response]:
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "查经安排")
            self.assertContains(response, "全教会")
            self.assertNotContains(response, "系列")
            self.assertNotContains(response, "查经课程")

        self.assertContains(form_response, "区")
        self.assertContains(form_response, "小组")

    def test_schedule_list_and_detail_display_district_scope_label(self):
        self.set_language("en")
        self.series.scope_type = BibleStudySeries.SCOPE_DISTRICT
        self.series.district = self.north
        self.series.save()
        self.client.login(username="study_staff", password="testpass123")

        list_response = self.client.get(reverse("bible_study_schedule_manage_list"))
        detail_response = self.client.get(
            reverse("bible_study_schedule_detail", args=[self.series.id]),
        )

        self.assertContains(list_response, "District: North")
        self.assertContains(detail_response, "District: North")

    def test_schedule_list_and_detail_display_small_group_scope_label(self):
        self.set_language("en")
        self.series.scope_type = BibleStudySeries.SCOPE_SMALL_GROUP
        self.series.small_group = self.group
        self.series.save()
        self.client.login(username="study_staff", password="testpass123")

        list_response = self.client.get(reverse("bible_study_schedule_manage_list"))
        detail_response = self.client.get(
            reverse("bible_study_schedule_detail", args=[self.series.id]),
        )

        self.assertContains(list_response, "Small Group: Rainbow 4")
        self.assertContains(detail_response, "Small Group: Rainbow 4")

    def test_create_weekly_guide_can_preselect_schedule(self):
        self.set_language("en")
        self.client.login(username="study_staff", password="testpass123")

        response = self.client.get(
            reverse("create_bible_study_lesson"),
            {"series": str(self.series.id)},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["form"]["series"].value(), str(self.series.id))

    def test_create_weekly_guide_ignores_invalid_schedule_initial(self):
        self.set_language("en")
        self.client.login(username="study_staff", password="testpass123")

        response = self.client.get(
            reverse("create_bible_study_lesson"),
            {"series": "not-a-schedule"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context["form"]["series"].value())

    def test_bible_study_schedule_default_scope_is_global(self):
        schedule = BibleStudySeries.objects.create(title="默认范围查经安排")

        self.assertEqual(schedule.scope_type, BibleStudySeries.SCOPE_GLOBAL)
        self.assertIsNone(schedule.district)
        self.assertIsNone(schedule.small_group)

    def test_bible_study_schedule_global_scope_rejects_district_or_group(self):
        schedule = BibleStudySeries(
            title="错误全教会范围",
            scope_type=BibleStudySeries.SCOPE_GLOBAL,
            district=self.north,
            small_group=self.group,
        )

        with self.assertRaises(ValidationError):
            schedule.full_clean()

    def test_bible_study_schedule_district_scope_requires_district(self):
        missing_district = BibleStudySeries(
            title="缺少区查经安排",
            scope_type=BibleStudySeries.SCOPE_DISTRICT,
        )
        with_group = BibleStudySeries(
            title="区和小组同时设置",
            scope_type=BibleStudySeries.SCOPE_DISTRICT,
            district=self.north,
            small_group=self.group,
        )

        with self.assertRaises(ValidationError):
            missing_district.full_clean()
        with self.assertRaises(ValidationError):
            with_group.full_clean()

    def test_bible_study_schedule_small_group_scope_requires_small_group(self):
        missing_group = BibleStudySeries(
            title="缺少小组查经安排",
            scope_type=BibleStudySeries.SCOPE_SMALL_GROUP,
        )
        with_district = BibleStudySeries(
            title="小组和区同时设置",
            scope_type=BibleStudySeries.SCOPE_SMALL_GROUP,
            district=self.north,
            small_group=self.group,
        )

        with self.assertRaises(ValidationError):
            missing_group.full_clean()
        with self.assertRaises(ValidationError):
            with_district.full_clean()

    def test_bible_study_schedule_get_eligible_small_groups_global_scope(self):
        inactive_group = SmallGroup.objects.create(
            name="Inactive Group",
            district=self.north,
            is_active=False,
        )
        schedule = BibleStudySeries.objects.create(
            title="全教会范围查经安排",
            scope_type=BibleStudySeries.SCOPE_GLOBAL,
        )

        groups = list(schedule.get_eligible_small_groups())

        self.assertIn(self.group, groups)
        self.assertIn(self.same_group, groups)
        self.assertIn(self.other_group, groups)
        self.assertNotIn(inactive_group, groups)

    def test_bible_study_schedule_get_eligible_small_groups_district_scope(self):
        inactive_group = SmallGroup.objects.create(
            name="Inactive North Group",
            district=self.north,
            is_active=False,
        )
        schedule = BibleStudySeries.objects.create(
            title="北区查经安排",
            scope_type=BibleStudySeries.SCOPE_DISTRICT,
            district=self.north,
        )

        groups = list(schedule.get_eligible_small_groups())

        self.assertIn(self.group, groups)
        self.assertIn(self.same_group, groups)
        self.assertNotIn(self.other_group, groups)
        self.assertNotIn(inactive_group, groups)

    def test_bible_study_schedule_get_eligible_small_groups_small_group_scope(self):
        schedule = BibleStudySeries.objects.create(
            title="单小组查经安排",
            scope_type=BibleStudySeries.SCOPE_SMALL_GROUP,
            small_group=self.group,
        )

        self.assertEqual(list(schedule.get_eligible_small_groups()), [self.group])

    def test_bible_study_schedule_get_eligible_small_groups_excludes_inactive_group_scope(self):
        inactive_group = SmallGroup.objects.create(
            name="Inactive Scoped Group",
            district=self.north,
            is_active=False,
        )
        schedule = BibleStudySeries.objects.create(
            title="停用小组查经安排",
            scope_type=BibleStudySeries.SCOPE_SMALL_GROUP,
            small_group=inactive_group,
        )

        self.assertEqual(list(schedule.get_eligible_small_groups()), [])

    def test_bible_study_schedule_can_store_schedule_fields(self):
        start_date = timezone.localdate()
        end_date = start_date + timezone.timedelta(days=90)

        schedule = BibleStudySeries.objects.create(
            title="夏季查经安排",
            title_en="Summer Bible Study Schedule",
            description="夏季查经",
            description_en="Summer study",
            start_date=start_date,
            end_date=end_date,
            status=BibleStudySeries.STATUS_DRAFT,
            created_by=self.manager,
        )

        self.assertEqual(schedule.start_date, start_date)
        self.assertEqual(schedule.end_date, end_date)
        self.assertEqual(schedule.status, BibleStudySeries.STATUS_DRAFT)
        self.assertEqual(schedule.created_by, self.manager)
        self.assertFalse(schedule.is_published)

    def test_bible_study_schedule_published_status_stamps_published_at(self):
        schedule = BibleStudySeries.objects.create(
            title="发布查经安排",
            status=BibleStudySeries.STATUS_PUBLISHED,
        )

        self.assertIsNotNone(schedule.published_at)
        self.assertTrue(schedule.is_published)

    def test_bible_study_schedule_completed_status_is_published(self):
        schedule = BibleStudySeries.objects.create(
            title="完成查经安排",
            status=BibleStudySeries.STATUS_COMPLETED,
        )

        self.assertTrue(schedule.is_published)
        self.assertIsNone(schedule.published_at)

    def test_bible_study_schedule_rejects_end_date_before_start_date(self):
        start_date = timezone.localdate()
        schedule = BibleStudySeries(
            title="日期错误查经安排",
            start_date=start_date,
            end_date=start_date - timezone.timedelta(days=1),
        )

        with self.assertRaises(ValidationError):
            schedule.full_clean()

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

    def test_staff_sees_generate_meetings_control_on_guide_detail(self):
        self.set_language("en")
        lesson = self.create_lesson()
        self.client.login(username="study_staff", password="testpass123")

        response = self.client.get(
            reverse("bible_study_lesson_detail", args=[lesson.id]),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Generate Small Group Meetings")
        self.assertContains(response, "Generate Missing Meetings")
        self.assertContains(response, "Eligible Small Groups")
        self.assertContains(
            response,
            reverse("generate_bible_study_meetings", args=[lesson.id]),
        )

    def test_regular_user_cannot_access_generate_meetings_route(self):
        self.set_language("en")
        lesson = self.create_lesson(status=BibleStudyLesson.STATUS_PUBLISHED)
        self.client.login(username="regular", password="testpass123")

        get_response = self.client.get(
            reverse("generate_bible_study_meetings", args=[lesson.id]),
        )
        post_response = self.client.post(
            reverse("generate_bible_study_meetings", args=[lesson.id]),
        )

        self.assertEqual(get_response.status_code, 302)
        self.assertEqual(get_response.url, reverse("study_session_list"))
        self.assertEqual(post_response.status_code, 302)
        self.assertEqual(post_response.url, reverse("study_session_list"))
        self.assertFalse(BibleStudyMeeting.objects.filter(lesson=lesson).exists())

    def test_generate_meetings_preview_shows_counts(self):
        self.set_language("en")
        lesson = self.create_lesson()
        self.create_meeting(lesson=lesson, small_group=self.group)
        self.client.login(username="study_staff", password="testpass123")

        response = self.client.get(
            reverse("generate_bible_study_meetings", args=[lesson.id]),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Generate Small Group Meetings")
        self.assertContains(response, "Eligible Small Groups")
        self.assertContains(response, "Existing Meetings")
        self.assertContains(response, "Meetings to Create")
        self.assertEqual(response.context["generation_preview"]["eligible_count"], 3)
        self.assertEqual(response.context["generation_preview"]["existing_count"], 1)
        self.assertEqual(response.context["generation_preview"]["missing_count"], 2)

    def test_generate_meetings_creates_draft_meetings_for_global_scope(self):
        self.set_language("en")
        lesson = self.create_lesson(
            status=BibleStudyLesson.STATUS_PUBLISHED,
            lesson_date=timezone.localdate() + timezone.timedelta(days=9),
        )
        self.client.login(username="study_staff", password="testpass123")

        response = self.client.post(
            reverse("generate_bible_study_meetings", args=[lesson.id]),
            follow=True,
        )

        meetings = BibleStudyMeeting.objects.filter(lesson=lesson).order_by(
            "small_group__name",
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Created 3 small group meetings")
        self.assertEqual(meetings.count(), 3)
        self.assertEqual(
            set(meetings.values_list("small_group", flat=True)),
            {self.group.id, self.same_group.id, self.other_group.id},
        )
        for meeting in meetings:
            self.assertEqual(meeting.status, BibleStudyMeeting.STATUS_DRAFT)
            self.assertEqual(meeting.created_by, self.staff)
            self.assertEqual(meeting.lesson, lesson)
            self.assertEqual(meeting.lesson.series, self.series)
            self.assertEqual(timezone.localtime(meeting.meeting_datetime).date(), lesson.lesson_date)
            self.assertEqual(timezone.localtime(meeting.meeting_datetime).hour, 19)
            self.assertEqual(timezone.localtime(meeting.meeting_datetime).minute, 30)
            self.assertEqual(meeting.location, "")
            self.assertEqual(meeting.location_en, "")
            self.assertEqual(meeting.meeting_link, "")
            self.assertEqual(meeting.group_direction, "")
            self.assertEqual(meeting.group_direction_en, "")
            self.assertEqual(meeting.group_questions, "")
            self.assertEqual(meeting.group_questions_en, "")
            self.assertIsNone(meeting.service_event)
            self.assertIsNone(meeting.discussion_leader_user)
            self.assertEqual(meeting.discussion_leader_name, "")

    def test_generate_meetings_uses_district_scope(self):
        self.set_language("en")
        self.series.scope_type = BibleStudySeries.SCOPE_DISTRICT
        self.series.district = self.north
        self.series.save()
        lesson = self.create_lesson(status=BibleStudyLesson.STATUS_PUBLISHED)
        self.client.login(username="study_staff", password="testpass123")

        response = self.client.post(
            reverse("generate_bible_study_meetings", args=[lesson.id]),
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            set(BibleStudyMeeting.objects.filter(lesson=lesson).values_list(
                "small_group",
                flat=True,
            )),
            {self.group.id, self.same_group.id},
        )

    def test_generate_meetings_uses_small_group_scope(self):
        self.set_language("en")
        self.series.scope_type = BibleStudySeries.SCOPE_SMALL_GROUP
        self.series.small_group = self.group
        self.series.save()
        lesson = self.create_lesson(status=BibleStudyLesson.STATUS_PUBLISHED)
        self.client.login(username="study_staff", password="testpass123")

        response = self.client.post(
            reverse("generate_bible_study_meetings", args=[lesson.id]),
        )

        self.assertEqual(response.status_code, 302)
        meetings = BibleStudyMeeting.objects.filter(lesson=lesson)
        self.assertEqual(meetings.count(), 1)
        self.assertEqual(meetings.get().small_group, self.group)

    def test_generate_meetings_excludes_inactive_small_groups(self):
        self.set_language("en")
        inactive_group = SmallGroup.objects.create(
            name="Inactive Generate Group",
            district=self.north,
            is_active=False,
        )
        self.series.scope_type = BibleStudySeries.SCOPE_SMALL_GROUP
        self.series.small_group = inactive_group
        self.series.save()
        lesson = self.create_lesson(status=BibleStudyLesson.STATUS_PUBLISHED)
        self.client.login(username="study_staff", password="testpass123")

        response = self.client.post(
            reverse("generate_bible_study_meetings", args=[lesson.id]),
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Created 0 small group meetings")
        self.assertFalse(BibleStudyMeeting.objects.filter(lesson=lesson).exists())

    def test_generate_meetings_skips_existing_without_overwriting(self):
        self.set_language("en")
        lesson = self.create_lesson(status=BibleStudyLesson.STATUS_PUBLISHED)
        existing = self.create_meeting(
            lesson=lesson,
            small_group=self.group,
            status=BibleStudyMeeting.STATUS_PUBLISHED,
            location="Do not overwrite",
            group_direction="Existing group preparation",
        )
        self.client.login(username="study_staff", password="testpass123")

        response = self.client.post(
            reverse("generate_bible_study_meetings", args=[lesson.id]),
            follow=True,
        )

        existing.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Skipped 1 existing meetings")
        self.assertEqual(existing.status, BibleStudyMeeting.STATUS_PUBLISHED)
        self.assertEqual(existing.location, "Do not overwrite")
        self.assertEqual(existing.group_direction, "Existing group preparation")
        self.assertEqual(BibleStudyMeeting.objects.filter(lesson=lesson).count(), 3)

    def test_generate_meetings_is_idempotent(self):
        self.set_language("en")
        lesson = self.create_lesson(status=BibleStudyLesson.STATUS_PUBLISHED)
        self.client.login(username="study_staff", password="testpass123")

        first_response = self.client.post(
            reverse("generate_bible_study_meetings", args=[lesson.id]),
            follow=True,
        )
        second_response = self.client.post(
            reverse("generate_bible_study_meetings", args=[lesson.id]),
            follow=True,
        )

        self.assertContains(first_response, "Created 3 small group meetings")
        self.assertContains(second_response, "Created 0 small group meetings")
        self.assertContains(second_response, "Skipped 3 existing meetings")
        self.assertEqual(BibleStudyMeeting.objects.filter(lesson=lesson).count(), 3)

    def test_generate_meetings_does_not_create_related_operations_records(self):
        self.set_language("en")
        lesson = self.create_lesson(status=BibleStudyLesson.STATUS_PUBLISHED)
        self.client.login(username="study_staff", password="testpass123")

        self.client.post(reverse("generate_bible_study_meetings", args=[lesson.id]))

        meetings = BibleStudyMeeting.objects.filter(lesson=lesson)
        self.assertEqual(meetings.count(), 3)
        self.assertEqual(ServiceEvent.objects.count(), 0)
        self.assertEqual(TeamAssignment.objects.count(), 0)
        self.assertEqual(BibleStudyMeetingRole.objects.filter(meeting__in=meetings).count(), 0)
        self.assertEqual(
            BibleStudyMeetingWorshipSong.objects.filter(meeting__in=meetings).count(),
            0,
        )

    def test_guide_detail_shows_generated_meetings_after_generation(self):
        self.set_language("en")
        lesson = self.create_lesson(status=BibleStudyLesson.STATUS_PUBLISHED)
        self.client.login(username="study_staff", password="testpass123")

        self.client.post(reverse("generate_bible_study_meetings", args=[lesson.id]))
        response = self.client.get(reverse("bible_study_lesson_detail", args=[lesson.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Rainbow 4")
        self.assertContains(response, "Rainbow 4B")
        self.assertContains(response, "Rainbow 5")

    def test_chinese_generate_meetings_page_uses_expected_wording(self):
        self.set_language("zh")
        lesson = self.create_lesson(status=BibleStudyLesson.STATUS_PUBLISHED)
        self.client.login(username="study_staff", password="testpass123")

        response = self.client.get(
            reverse("generate_bible_study_meetings", args=[lesson.id]),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "生成小组查经聚会")
        self.assertContains(response, "符合范围的小组")
        self.assertContains(response, "已存在的聚会")
        self.assertContains(response, "将要生成的聚会")
        self.assertNotContains(response, "查经课程")

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

    def test_meeting_form_deemphasizes_compatibility_leader_fields(self):
        form = BibleStudyMeetingForm()

        self.assertEqual(form.fields["lesson"].label, "Weekly Bible Study Guide")
        self.assertNotIn("discussion_leader_user", form.fields)
        self.assertNotIn("discussion_leader_name", form.fields)
        self.assertFalse(form.fields["service_event"].required)
        self.assertEqual(
            form.fields["service_event"].label,
            "Optional Service Event Link",
        )
        self.assertIn(
            "Leave blank for normal small-group Bible Study",
            form.fields["service_event"].help_text,
        )

    def test_chinese_meeting_form_labels_parent_guide_and_service_event(self):
        form = BibleStudyMeetingForm(language="zh")

        self.assertEqual(form.fields["lesson"].label, "每周查经指引")
        self.assertEqual(form.fields["service_event"].label, "关联聚会事件（可选）")
        self.assertIn("一般小组查经可以留空", form.fields["service_event"].help_text)

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

    def test_meeting_role_form_filters_users_to_meeting_small_group(self):
        meeting = self.create_meeting(status=BibleStudyMeeting.STATUS_PUBLISHED)

        form = BibleStudyMeetingRoleForm(meeting=meeting)

        self.assertIn(self.user, form.fields["user"].queryset)
        self.assertNotIn(self.other_user, form.fields["user"].queryset)
        self.assertEqual(
            list(form.fields),
            ["role", "user", "display_name", "notes", "notes_en"],
        )

    def test_staff_can_access_meeting_role_management_page(self):
        self.set_language("en")
        meeting = self.create_meeting(status=BibleStudyMeeting.STATUS_PUBLISHED)
        self.create_meeting_role(meeting, role=BibleStudyMeetingRole.ROLE_WORSHIP_LEAD)
        self.client.login(username="study_staff", password="testpass123")

        response = self.client.get(
            reverse("manage_bible_study_meeting_roles", args=[meeting.id]),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Manage Meeting Roles")
        self.assertContains(response, "Add Meeting Role")
        self.assertContains(response, "Worship Lead")

    def test_regular_user_cannot_access_meeting_role_management_page(self):
        self.set_language("en")
        meeting = self.create_meeting(status=BibleStudyMeeting.STATUS_PUBLISHED)
        self.client.login(username="regular", password="testpass123")

        response = self.client.get(
            reverse("manage_bible_study_meeting_roles", args=[meeting.id]),
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.url,
            reverse("bible_study_meeting_detail", args=[meeting.id]),
        )

    def test_staff_can_add_meeting_role(self):
        self.set_language("en")
        meeting = self.create_meeting(status=BibleStudyMeeting.STATUS_PUBLISHED)
        self.client.login(username="study_staff", password="testpass123")

        response = self.client.post(
            reverse("manage_bible_study_meeting_roles", args=[meeting.id]),
            self.meeting_role_post_data(),
        )

        self.assertEqual(response.status_code, 302)
        role = BibleStudyMeetingRole.objects.get(meeting=meeting)
        self.assertEqual(role.role, BibleStudyMeetingRole.ROLE_DISCUSSION_LEADER)
        self.assertEqual(role.user, self.user)
        self.assertEqual(role.notes_en, "Discussion leader notes")

    def test_staff_can_edit_meeting_role(self):
        self.set_language("en")
        meeting = self.create_meeting(status=BibleStudyMeeting.STATUS_PUBLISHED)
        role = self.create_meeting_role(meeting)
        self.client.login(username="study_staff", password="testpass123")

        response = self.client.post(
            reverse("edit_bible_study_meeting_role", args=[role.id]),
            self.meeting_role_post_data(
                role=BibleStudyMeetingRole.ROLE_PIANIST,
                user="",
                display_name="Guest Pianist",
                notes_en="Updated pianist notes",
            ),
        )

        self.assertEqual(response.status_code, 302)
        role.refresh_from_db()
        self.assertEqual(role.role, BibleStudyMeetingRole.ROLE_PIANIST)
        self.assertIsNone(role.user)
        self.assertEqual(role.display_name, "Guest Pianist")
        self.assertEqual(role.notes_en, "Updated pianist notes")

    def test_staff_can_delete_meeting_role(self):
        self.set_language("en")
        meeting = self.create_meeting(status=BibleStudyMeeting.STATUS_PUBLISHED)
        role = self.create_meeting_role(meeting)
        self.client.login(username="study_staff", password="testpass123")

        response = self.client.post(
            reverse("delete_bible_study_meeting_role", args=[role.id]),
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(BibleStudyMeetingRole.objects.filter(id=role.id).exists())

    def test_regular_user_cannot_edit_or_delete_meeting_role(self):
        self.set_language("en")
        meeting = self.create_meeting(status=BibleStudyMeeting.STATUS_PUBLISHED)
        role = self.create_meeting_role(meeting)
        self.client.login(username="regular", password="testpass123")

        edit_response = self.client.get(
            reverse("edit_bible_study_meeting_role", args=[role.id]),
        )
        delete_response = self.client.post(
            reverse("delete_bible_study_meeting_role", args=[role.id]),
        )

        self.assertEqual(edit_response.status_code, 302)
        self.assertEqual(
            edit_response.url,
            reverse("bible_study_meeting_detail", args=[meeting.id]),
        )
        self.assertEqual(delete_response.status_code, 302)
        self.assertTrue(BibleStudyMeetingRole.objects.filter(id=role.id).exists())

    def test_meeting_detail_displays_roles_to_own_group_user(self):
        self.set_language("en")
        meeting = self.create_meeting(status=BibleStudyMeeting.STATUS_PUBLISHED)
        self.create_meeting_role(
            meeting,
            user=None,
            display_name="Guest Leader",
            notes_en="Lead the opening discussion.",
        )
        self.client.login(username="regular", password="testpass123")

        response = self.client.get(
            reverse("bible_study_meeting_detail", args=[meeting.id]),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Meeting Roles")
        self.assertContains(response, "Discussion Leader")
        self.assertContains(response, "Guest Leader")
        self.assertContains(response, "Lead the opening discussion.")

    def test_meeting_detail_hides_roles_when_parent_meeting_not_visible(self):
        self.set_language("en")
        meeting = self.create_meeting(small_group=self.other_group)
        self.create_meeting_role(
            meeting,
            user=None,
            display_name="Hidden Leader",
        )
        self.client.login(username="regular", password="testpass123")

        response = self.client.get(
            reverse("bible_study_meeting_detail", args=[meeting.id]),
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("study_session_list"))

    def test_meeting_detail_role_controls_are_manager_only(self):
        self.set_language("en")
        meeting = self.create_meeting(status=BibleStudyMeeting.STATUS_PUBLISHED)

        self.client.login(username="study_staff", password="testpass123")
        manager_response = self.client.get(
            reverse("bible_study_meeting_detail", args=[meeting.id]),
        )
        self.assertContains(manager_response, "Manage Meeting Roles")
        self.assertContains(
            manager_response,
            reverse("manage_bible_study_meeting_roles", args=[meeting.id]),
        )

        self.client.logout()
        self.client.login(username="regular", password="testpass123")
        member_response = self.client.get(
            reverse("bible_study_meeting_detail", args=[meeting.id]),
        )
        self.assertEqual(member_response.status_code, 200)
        self.assertNotContains(member_response, "Manage Meeting Roles")
        self.assertNotContains(member_response, "Edit Meeting Role")
        self.assertNotContains(member_response, "Delete")

    def test_chinese_meeting_role_labels_render(self):
        self.set_language("zh")
        meeting = self.create_meeting(status=BibleStudyMeeting.STATUS_PUBLISHED)
        self.create_meeting_role(
            meeting,
            role=BibleStudyMeetingRole.ROLE_WORSHIP_LEAD,
            user=None,
            display_name="敬拜同工",
            notes="敬拜预备备注",
        )
        self.client.login(username="regular", password="testpass123")

        response = self.client.get(
            reverse("bible_study_meeting_detail", args=[meeting.id]),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "查经聚会同工分工")
        self.assertContains(response, "敬拜带领")
        self.assertContains(response, "敬拜同工")
        self.assertNotContains(response, "查经课程")

    def test_staff_can_access_meeting_worship_management_page(self):
        self.set_language("en")
        meeting = self.create_meeting(status=BibleStudyMeeting.STATUS_PUBLISHED)
        self.create_meeting_role(
            meeting,
            role=BibleStudyMeetingRole.ROLE_WORSHIP_LEAD,
            user=None,
            display_name="Worship Context Lead",
        )
        self.create_meeting_worship_song(meeting, title_en="Visible Worship Song")
        self.client.login(username="study_staff", password="testpass123")

        response = self.client.get(
            reverse("manage_bible_study_meeting_worship_songs", args=[meeting.id]),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Manage Worship Set")
        self.assertContains(response, "Add Worship Song")
        self.assertContains(response, "Visible Worship Song")
        self.assertContains(response, "Meeting Time")
        self.assertContains(response, "Meeting Roles")
        self.assertContains(response, "Worship Lead")
        self.assertContains(response, "Worship Context Lead")

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
        self.assertEqual(song.worship_lead_user, self.user)

    def test_meeting_worship_song_form_filters_worship_lead_to_meeting_group(self):
        meeting = self.create_meeting(status=BibleStudyMeeting.STATUS_PUBLISHED)

        form = BibleStudyMeetingWorshipSongForm(meeting=meeting)

        users = list(form.fields["worship_lead_user"].queryset)
        self.assertIn(self.user, users)
        self.assertNotIn(self.other_user, users)
        self.assertNotIn("meeting", form.fields)

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
        self.assertContains(response, "Small Group Meetings for This Guide")
        self.assertContains(response, "Bible Study Schedule")
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

        role_response = self.client.get(
            reverse("manage_bible_study_meeting_roles", args=[meeting.id]),
        )
        self.assertEqual(role_response.status_code, 200)
        self.assertNotContains(role_response, "查经课程")

        worship_response = self.client.get(
            reverse("manage_bible_study_meeting_worship_songs", args=[meeting.id]),
        )
        self.assertEqual(worship_response.status_code, 200)
        self.assertNotContains(worship_response, "查经课程")

    def test_study_list_shows_v2_current_bible_study_for_own_group_meeting(self):
        self.set_language("en")
        self.series.status = BibleStudySeries.STATUS_PUBLISHED
        self.series.save()
        lesson = self.create_lesson(
            status=BibleStudyLesson.STATUS_PUBLISHED,
            title_en="Weekly Guide",
            pastor_guide_body_en="Detailed pastor guide belongs on detail page",
        )
        meeting = self.create_meeting(
            lesson=lesson,
            status=BibleStudyMeeting.STATUS_PUBLISHED,
        )
        legacy_session = self.create_session(title_en="Fallback V1 Session")
        self.client.login(username="regular", password="testpass123")

        response = self.client.get(reverse("study_session_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Current Bible Study")
        self.assertContains(response, "My Small Group Meeting")
        self.assertContains(response, "Bible Study Schedule")
        self.assertContains(response, "John Bible Study")
        self.assertContains(response, "Weekly Bible Study Guide")
        self.assertContains(response, "Weekly Guide")
        self.assertContains(response, "John 15:1-17")
        self.assertContains(response, "Rainbow 4")
        self.assertContains(response, "Small group home")
        self.assertContains(response, "Open My Group Meeting")
        self.assertContains(
            response,
            reverse("bible_study_meeting_detail", args=[meeting.id]),
        )
        self.assertNotContains(response, "Detailed pastor guide belongs on detail page")
        self.assertContains(response, "Other Bible Study Sessions")
        self.assertContains(response, legacy_session.title_en)

    def test_study_list_hides_other_group_v2_meeting_from_normal_user(self):
        self.set_language("en")
        self.series.status = BibleStudySeries.STATUS_PUBLISHED
        self.series.save()
        other_lesson = self.create_lesson(
            status=BibleStudyLesson.STATUS_PUBLISHED,
            title_en="Other Group Weekly Guide",
        )
        self.create_meeting(
            lesson=other_lesson,
            small_group=self.other_group,
            status=BibleStudyMeeting.STATUS_PUBLISHED,
        )
        self.client.login(username="regular", password="testpass123")

        response = self.client.get(reverse("study_session_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "No current small-group Bible Study meeting is available yet.",
        )
        self.assertNotContains(response, "Other Group Weekly Guide")

    def test_study_list_hides_draft_and_cancelled_v2_meetings_from_normal_user(self):
        self.set_language("en")
        self.series.status = BibleStudySeries.STATUS_PUBLISHED
        self.series.save()
        draft_lesson = self.create_lesson(
            status=BibleStudyLesson.STATUS_PUBLISHED,
            title_en="Draft Meeting Guide",
        )
        cancelled_lesson = self.create_lesson(
            status=BibleStudyLesson.STATUS_PUBLISHED,
            title_en="Cancelled Meeting Guide",
        )
        self.create_meeting(
            lesson=draft_lesson,
            status=BibleStudyMeeting.STATUS_DRAFT,
        )
        self.create_meeting(
            lesson=cancelled_lesson,
            status=BibleStudyMeeting.STATUS_CANCELLED,
        )
        self.client.login(username="regular", password="testpass123")

        response = self.client.get(reverse("study_session_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "No current small-group Bible Study meeting is available yet.",
        )
        self.assertNotContains(response, "Draft Meeting Guide")
        self.assertNotContains(response, "Cancelled Meeting Guide")

    def test_study_list_hides_v2_meeting_under_draft_guide_from_normal_user(self):
        self.set_language("en")
        self.series.status = BibleStudySeries.STATUS_PUBLISHED
        self.series.save()
        draft_lesson = self.create_lesson(
            status=BibleStudyLesson.STATUS_DRAFT,
            title_en="Draft Weekly Guide",
        )
        self.create_meeting(
            lesson=draft_lesson,
            status=BibleStudyMeeting.STATUS_PUBLISHED,
        )
        self.client.login(username="regular", password="testpass123")

        response = self.client.get(reverse("study_session_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "No current small-group Bible Study meeting is available yet.",
        )
        self.assertNotContains(response, "Draft Weekly Guide")

    def test_study_list_user_without_small_group_gets_safe_v2_empty_state(self):
        self.set_language("en")
        self.user.profile.small_group = None
        self.user.profile.save()
        self.client.login(username="regular", password="testpass123")

        response = self.client.get(reverse("study_session_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Your profile is not linked to a small group yet.")

    def test_study_list_staff_sees_v2_management_links(self):
        self.set_language("en")
        self.client.login(username="study_staff", password="testpass123")

        response = self.client.get(reverse("study_session_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Bible Study Schedules")
        self.assertContains(response, "Weekly Bible Study Guides")
        self.assertContains(response, "Small Group Meetings")
        self.assertContains(response, reverse("bible_study_schedule_manage_list"))
        self.assertContains(response, reverse("bible_study_lesson_manage_list"))
        self.assertContains(response, reverse("bible_study_meeting_manage_list"))

    def test_chinese_study_list_uses_expected_v2_landing_wording(self):
        self.set_language("zh")
        self.client.login(username="study_staff", password="testpass123")

        response = self.client.get(reverse("study_session_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "当前查经")
        self.assertContains(response, "查经安排")
        self.assertContains(response, "每周查经指引")
        self.assertNotContains(response, "查经课程")
        self.assertNotContains(response, "查经管理")

    def test_v1_studies_list_route_still_uses_session_page(self):
        self.set_language("en")
        self.create_session(title_en="V1 Session")
        self.client.login(username="regular", password="testpass123")

        response = self.client.get(reverse("study_session_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Bible Studies")
        self.assertContains(response, "V1 Session")
        self.assertContains(response, "Other Bible Study Sessions")

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
