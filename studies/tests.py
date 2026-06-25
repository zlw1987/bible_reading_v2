from datetime import date, datetime, timezone as datetime_timezone
from io import StringIO
from unittest import mock

from django.contrib import admin
from django.contrib.auth.models import AnonymousUser, User
from django.core.exceptions import ValidationError
from django.core.management import call_command, CommandError
from django.db import connection
from django.db.models import ProtectedError
from django.test import SimpleTestCase, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from accounts.models import (
    ChurchRoleAssignment,
    ChurchStructureMembership,
    ChurchStructureUnit,
)
from events.models import ServiceEvent
from ministry.models import TeamAssignment
from .forms import (
    BibleStudyLessonForm,
    BibleStudyMeetingForm,
    BibleStudyMeetingPreparationForm,
    BibleStudyMeetingRoleForm,
    BibleStudyMeetingWorshipSongForm,
    BibleStudySeriesForm,
)
from .models import (
    BibleStudyLesson,
    BibleStudyMeeting,
    BibleStudyMeetingAudienceScope,
    BibleStudyMeetingRole,
    BibleStudyMeetingWorshipSong,
    BibleStudySeries,
    BibleStudySeriesAudienceScope,
)
from .services import (
    cancel_bible_study_lesson_with_meetings,
    resolve_normal_generation_targets,
)


class BibleStudyModuleTests(TestCase):
    def setUp(self):
        # ChurchStructureUnit tree used by the structure-native schedule/audience paths.
        self.root_unit = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_ROOT,
            code="CHURCH",
            name="全教会",
            name_en="Whole Church",
        )
        self.cm_unit = ChurchStructureUnit.objects.create(
            parent=self.root_unit,
            unit_type=ChurchStructureUnit.UNIT_MINISTRY_CONTEXT,
            code="CM",
            name="中文事工",
            name_en="Chinese Ministry",
        )
        self.em_unit = ChurchStructureUnit.objects.create(
            parent=self.root_unit,
            unit_type=ChurchStructureUnit.UNIT_MINISTRY_CONTEXT,
            code="EM",
            name="英文事工",
            name_en="English Ministry",
        )
        self.north_unit = ChurchStructureUnit.objects.create(
            parent=self.cm_unit,
            unit_type=ChurchStructureUnit.UNIT_DISTRICT,
            code="NORTH",
            name="North",
            name_en="North",
        )
        self.south_unit = ChurchStructureUnit.objects.create(
            parent=self.em_unit,
            unit_type=ChurchStructureUnit.UNIT_DISTRICT,
            code="SOUTH",
            name="South",
            name_en="South",
        )
        self.group_unit = ChurchStructureUnit.objects.create(
            parent=self.north_unit,
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="RAINBOW4",
            name="Rainbow 4",
            name_en="Rainbow 4",
        )
        self.same_group_unit = ChurchStructureUnit.objects.create(
            parent=self.north_unit,
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="RAINBOW4B",
            name="Rainbow 4B",
            name_en="Rainbow 4B",
        )
        self.other_group_unit = ChurchStructureUnit.objects.create(
            parent=self.south_unit,
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="RAINBOW5",
            name="Rainbow 5",
            name_en="Rainbow 5",
        )
        self.user = User.objects.create_user(
            username="regular",
            email="regular@example.com",
            password="testpass123",
        )

        self.same_district_user = User.objects.create_user(
            username="same_district",
            email="same@example.com",
            password="testpass123",
        )

        self.other_user = User.objects.create_user(
            username="other_group",
            email="other@example.com",
            password="testpass123",
        )

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
            status=BibleStudySeries.STATUS_PUBLISHED,
        )
        self.future_time = timezone.now() + timezone.timedelta(days=3)
        self.prestudy_time = timezone.now() + timezone.timedelta(days=2)

    def set_language(self, language="en"):
        session = self.client.session
        session["language"] = language
        session.save()

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

    def create_membership(self, user, unit, **overrides):
        data = {
            "user": user,
            "unit": unit,
            "status": ChurchStructureMembership.STATUS_ACTIVE,
            "is_primary": True,
            "start_date": timezone.localdate() - timezone.timedelta(days=1),
        }
        data.update(overrides)
        return ChurchStructureMembership.objects.create(**data)

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
            "audience_units": [self.root_unit.id],
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
            "audience_unit": self.group_unit.id,
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
        # Whole-church scope is now expressed by a root-unit audience row
        # (BS-SERIES-FIELD-RETIRE.1A removed the legacy global scope_type).
        BibleStudySeriesAudienceScope.objects.create(
            series=self.series, unit=self.root_unit
        )
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
        self.assertContains(response, "schedule-list-card")
        self.assertContains(response, "schedule-meta-grid")
        self.assertContains(response, "View")
        self.assertContains(response, "Edit")
        self.assertNotContains(response, "bible-study-schedule-table")
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
        self.assertIsNotNone(schedule.published_at)
        self.assertEqual(schedule.created_by, self.staff)
        self.assertTrue(schedule.is_active)
        self.assertEqual(
            list(schedule.get_audience_scope_units()),
            [self.root_unit],
        )

    def test_staff_can_create_bible_study_schedule_with_district_scope(self):
        self.set_language("en")
        self.client.login(username="study_staff", password="testpass123")

        response = self.client.post(
            reverse("create_bible_study_schedule"),
            self.schedule_post_data(
                title="分区查经安排",
                title_en="District Bible Study Schedule",
                audience_units=[self.north_unit.id],
            ),
        )

        schedule = BibleStudySeries.objects.get(title="分区查经安排")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            list(schedule.get_audience_scope_units()),
            [self.north_unit],
        )

    def test_staff_can_create_bible_study_schedule_with_ministry_context_scope(self):
        self.set_language("en")
        self.client.login(username="study_staff", password="testpass123")

        response = self.client.post(
            reverse("create_bible_study_schedule"),
            self.schedule_post_data(
                title="中文事工查经安排",
                title_en="CM Bible Study Schedule",
                audience_units=[self.cm_unit.id],
            ),
        )

        schedule = BibleStudySeries.objects.get(title="中文事工查经安排")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            list(schedule.get_audience_scope_units()),
            [self.cm_unit],
        )

    def test_staff_can_create_bible_study_schedule_with_small_group_scope(self):
        self.set_language("en")
        self.client.login(username="study_staff", password="testpass123")

        response = self.client.post(
            reverse("create_bible_study_schedule"),
            self.schedule_post_data(
                title="小组查经安排",
                title_en="Small Group Bible Study Schedule",
                audience_units=[self.group_unit.id],
            ),
        )

        schedule = BibleStudySeries.objects.get(title="小组查经安排")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            list(schedule.get_audience_scope_units()),
            [self.group_unit],
        )

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
                audience_units=[self.north_unit.id],
            ),
        )

        self.assertEqual(response.status_code, 302)
        self.series.refresh_from_db()
        self.assertEqual(
            list(self.series.get_audience_scope_units()),
            [self.north_unit],
        )

    def test_staff_can_edit_bible_study_schedule_to_small_group_scope(self):
        self.set_language("en")
        self.client.login(username="study_staff", password="testpass123")

        response = self.client.post(
            reverse("edit_bible_study_schedule", args=[self.series.id]),
            self.schedule_post_data(
                title=self.series.title,
                title_en=self.series.title_en,
                audience_units=[self.group_unit.id],
            ),
        )

        self.assertEqual(response.status_code, 302)
        self.series.refresh_from_db()
        self.assertEqual(
            list(self.series.get_audience_scope_units()),
            [self.group_unit],
        )

    def test_schedule_detail_shows_related_weekly_guides(self):
        self.set_language("en")
        self.series.start_date = timezone.localdate() + timezone.timedelta(days=7)
        self.series.end_date = self.series.start_date + timezone.timedelta(days=84)
        self.series.status = BibleStudySeries.STATUS_PUBLISHED
        self.series.save()
        BibleStudySeriesAudienceScope.objects.create(
            series=self.series, unit=self.root_unit
        )
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
            "Small-group meetings are generated from weekly guides and "
            "this schedule’s scope.",
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
        self.assertContains(response, "Audience Scope")
        self.assertContains(
            response,
            "The selected units determine which small groups receive generated "
            "Bible Study meetings.",
        )
        # Unit options render with readable bilingual path labels.
        self.assertContains(response, "Whole Church")
        self.assertContains(response, "Chinese Ministry &gt; North")
        self.assertNotContains(response, "Series")

    def test_chinese_schedule_pages_use_schedule_wording(self):
        self.set_language("zh")
        self.series.start_date = date(2026, 5, 29)
        self.series.end_date = date(2026, 5, 29)
        self.series.save(update_fields=["start_date", "end_date"])
        BibleStudySeriesAudienceScope.objects.create(
            series=self.series, unit=self.root_unit
        )
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

        self.assertContains(form_response, "适用范围")
        self.assertContains(form_response, "小组")
        self.assertContains(list_response, "日期范围")
        self.assertContains(list_response, "范围")
        self.assertContains(list_response, "状态")
        self.assertContains(list_response, "启用")
        self.assertContains(list_response, "每周指引")
        self.assertContains(list_response, "2026-05-29")
        self.assertContains(list_response, "至")
        self.assertContains(list_response, "查看")
        self.assertContains(list_response, "编辑")
        self.assertContains(list_response, "schedule-description-text")
        self.assertContains(list_response, "schedule-list-card")
        self.assertNotContains(list_response, "bible-study-schedule-table")
        schedule_list_markup = list_response.content.decode().split(
            '<div class="schedule-list">',
            1,
        )[1]
        self.assertNotIn("每周查经指引", schedule_list_markup)

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

    def test_create_weekly_guide_form_excludes_cancelled_schedules(self):
        self.set_language("en")
        cancelled = BibleStudySeries.objects.create(
            title="Cancelled Option Schedule",
            title_en="Cancelled Option Schedule",
            status=BibleStudySeries.STATUS_CANCELLED,
        )
        self.client.login(username="study_staff", password="testpass123")

        response = self.client.get(reverse("create_bible_study_lesson"))

        series_options = list(response.context["form"].fields["series"].queryset)
        self.assertIn(self.series, series_options)
        self.assertNotIn(cancelled, series_options)

    def test_edit_weekly_guide_keeps_current_cancelled_schedule_selectable(self):
        self.set_language("en")
        schedule = BibleStudySeries.objects.create(
            title="Soon Cancelled Schedule",
            title_en="Soon Cancelled Schedule",
            status=BibleStudySeries.STATUS_PUBLISHED,
        )
        lesson = self.create_lesson(series=schedule)
        schedule.status = BibleStudySeries.STATUS_CANCELLED
        schedule.save()
        other_cancelled = BibleStudySeries.objects.create(
            title="Other Cancelled Schedule",
            title_en="Other Cancelled Schedule",
            status=BibleStudySeries.STATUS_CANCELLED,
        )
        self.client.login(username="study_staff", password="testpass123")

        response = self.client.get(
            reverse("edit_bible_study_lesson", args=[lesson.id]),
        )

        series_options = list(response.context["form"].fields["series"].queryset)
        self.assertIn(schedule, series_options)
        self.assertNotIn(other_cancelled, series_options)

    def test_create_weekly_guide_ignores_cancelled_schedule_preselect(self):
        self.set_language("en")
        cancelled = BibleStudySeries.objects.create(
            title="Cancelled Preselect Schedule",
            title_en="Cancelled Preselect Schedule",
            status=BibleStudySeries.STATUS_CANCELLED,
        )
        self.client.login(username="study_staff", password="testpass123")

        response = self.client.get(
            reverse("create_bible_study_lesson"),
            {"series": str(cancelled.id)},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context["form"]["series"].value())

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

    def test_new_lesson_form_does_not_offer_cancelled_status(self):
        form = BibleStudyLessonForm(language="en")

        self.assertEqual(
            [choice[0] for choice in form.fields["status"].choices],
            [
                BibleStudyLesson.STATUS_DRAFT,
                BibleStudyLesson.STATUS_PUBLISHED,
                BibleStudyLesson.STATUS_COMPLETED,
            ],
        )

    def test_active_lesson_edit_form_does_not_offer_cancelled_status(self):
        lesson = self.create_lesson(status=BibleStudyLesson.STATUS_PUBLISHED)
        form = BibleStudyLessonForm(instance=lesson, language="en")

        self.assertEqual(
            [choice[0] for choice in form.fields["status"].choices],
            [
                BibleStudyLesson.STATUS_DRAFT,
                BibleStudyLesson.STATUS_PUBLISHED,
                BibleStudyLesson.STATUS_COMPLETED,
            ],
        )

    def test_cancelled_lesson_edit_form_only_offers_cancelled_status(self):
        lesson = self.create_lesson(status=BibleStudyLesson.STATUS_CANCELLED)
        form = BibleStudyLessonForm(instance=lesson, language="en")

        self.assertEqual(
            [choice[0] for choice in form.fields["status"].choices],
            [BibleStudyLesson.STATUS_CANCELLED],
        )

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

    def test_cancelling_bible_study_lesson_cancels_active_meetings(self):
        self.set_language("en")
        lesson = self.create_lesson(status=BibleStudyLesson.STATUS_PUBLISHED)
        draft = self.create_meeting(
            lesson=lesson,
            status=BibleStudyMeeting.STATUS_DRAFT,
        )
        published = self.create_meeting(
            lesson=lesson,
            status=BibleStudyMeeting.STATUS_PUBLISHED,
        )
        self.client.login(username="study_staff", password="testpass123")

        response = self.client.post(
            reverse("cancel_bible_study_lesson", args=[lesson.id]),
        )

        self.assertEqual(response.status_code, 302)
        draft.refresh_from_db()
        published.refresh_from_db()
        self.assertEqual(draft.status, BibleStudyMeeting.STATUS_CANCELLED)
        self.assertEqual(published.status, BibleStudyMeeting.STATUS_CANCELLED)

    def test_cancelling_bible_study_lesson_leaves_final_meetings_unchanged(self):
        lesson = self.create_lesson(status=BibleStudyLesson.STATUS_PUBLISHED)
        completed = self.create_meeting(
            lesson=lesson,
            status=BibleStudyMeeting.STATUS_COMPLETED,
        )
        cancelled = self.create_meeting(
            lesson=lesson,
            status=BibleStudyMeeting.STATUS_CANCELLED,
        )

        cancel_bible_study_lesson_with_meetings(lesson)

        completed.refresh_from_db()
        cancelled.refresh_from_db()
        self.assertEqual(completed.status, BibleStudyMeeting.STATUS_COMPLETED)
        self.assertEqual(cancelled.status, BibleStudyMeeting.STATUS_CANCELLED)

    def test_cancelling_bible_study_lesson_preserves_meeting_child_data(self):
        lesson = self.create_lesson(status=BibleStudyLesson.STATUS_PUBLISHED)
        meeting = self.create_meeting(
            lesson=lesson,
            status=BibleStudyMeeting.STATUS_PUBLISHED,
        )
        role = self.create_meeting_role(meeting)
        song = self.create_meeting_worship_song(meeting)

        cancel_bible_study_lesson_with_meetings(lesson)

        meeting.refresh_from_db()
        self.assertEqual(meeting.status, BibleStudyMeeting.STATUS_CANCELLED)
        self.assertTrue(BibleStudyMeetingRole.objects.filter(id=role.id).exists())
        self.assertTrue(
            BibleStudyMeetingWorshipSong.objects.filter(id=song.id).exists()
        )

    def test_cancelling_bible_study_lesson_is_atomic(self):
        lesson = self.create_lesson(status=BibleStudyLesson.STATUS_PUBLISHED)
        meeting = self.create_meeting(
            lesson=lesson,
            status=BibleStudyMeeting.STATUS_PUBLISHED,
        )

        with mock.patch(
            "studies.services.cancel_non_final_meetings_for_lesson",
            side_effect=RuntimeError("meeting cancellation failed"),
        ):
            with self.assertRaises(RuntimeError):
                cancel_bible_study_lesson_with_meetings(lesson)

        lesson.refresh_from_db()
        meeting.refresh_from_db()
        self.assertEqual(lesson.status, BibleStudyLesson.STATUS_PUBLISHED)
        self.assertEqual(meeting.status, BibleStudyMeeting.STATUS_PUBLISHED)

    def test_lesson_edit_form_cannot_bypass_cancellation_consistency(self):
        self.set_language("en")
        lesson = self.create_lesson(status=BibleStudyLesson.STATUS_PUBLISHED)
        meeting = self.create_meeting(
            lesson=lesson,
            status=BibleStudyMeeting.STATUS_PUBLISHED,
        )
        self.client.login(username="study_staff", password="testpass123")

        response = self.client.post(
            reverse("edit_bible_study_lesson", args=[lesson.id]),
            self.lesson_post_data(status=BibleStudyLesson.STATUS_CANCELLED),
        )

        self.assertEqual(response.status_code, 200)
        lesson.refresh_from_db()
        meeting.refresh_from_db()
        self.assertEqual(lesson.status, BibleStudyLesson.STATUS_PUBLISHED)
        self.assertEqual(meeting.status, BibleStudyMeeting.STATUS_PUBLISHED)

    def test_cancelled_lesson_edit_form_cannot_reactivate_to_published(self):
        self.set_language("en")
        lesson = self.create_lesson(status=BibleStudyLesson.STATUS_CANCELLED)
        meeting = self.create_meeting(
            lesson=lesson,
            status=BibleStudyMeeting.STATUS_CANCELLED,
        )
        self.client.login(username="study_staff", password="testpass123")

        response = self.client.post(
            reverse("edit_bible_study_lesson", args=[lesson.id]),
            self.lesson_post_data(status=BibleStudyLesson.STATUS_PUBLISHED),
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["form"].is_valid())
        lesson.refresh_from_db()
        meeting.refresh_from_db()
        self.assertEqual(lesson.status, BibleStudyLesson.STATUS_CANCELLED)
        self.assertEqual(meeting.status, BibleStudyMeeting.STATUS_CANCELLED)

    def test_cancelled_lesson_edit_form_cannot_reactivate_to_draft_or_completed(self):
        self.set_language("en")
        lesson = self.create_lesson(status=BibleStudyLesson.STATUS_CANCELLED)
        draft_meeting = self.create_meeting(
            lesson=lesson,
            status=BibleStudyMeeting.STATUS_CANCELLED,
        )
        completed_meeting = self.create_meeting(
            lesson=lesson,
            status=BibleStudyMeeting.STATUS_COMPLETED,
        )
        self.client.login(username="study_staff", password="testpass123")

        for status in [
            BibleStudyLesson.STATUS_DRAFT,
            BibleStudyLesson.STATUS_COMPLETED,
        ]:
            response = self.client.post(
                reverse("edit_bible_study_lesson", args=[lesson.id]),
                self.lesson_post_data(status=status),
            )

            self.assertEqual(response.status_code, 200)
            self.assertFalse(response.context["form"].is_valid())
            lesson.refresh_from_db()
            draft_meeting.refresh_from_db()
            completed_meeting.refresh_from_db()
            self.assertEqual(lesson.status, BibleStudyLesson.STATUS_CANCELLED)
            self.assertEqual(
                draft_meeting.status,
                BibleStudyMeeting.STATUS_CANCELLED,
            )
            self.assertEqual(
                completed_meeting.status,
                BibleStudyMeeting.STATUS_COMPLETED,
            )

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
        self.assertContains(response, "guide-list-card")
        self.assertContains(response, "schedule-meta-grid")
        self.assertContains(response, "Bible Study Schedule")
        self.assertContains(response, "Guide Date")
        self.assertContains(response, "Thursday Pre-study")
        self.assertContains(response, "Scope")
        self.assertContains(response, "View")
        self.assertContains(response, "Edit")
        self.assertNotContains(response, "<table")
        self.assertContains(
            response,
            reverse("bible_study_lesson_detail", args=[lesson.id]),
        )

    def test_chinese_lesson_management_list_uses_mobile_card_labels(self):
        self.set_language("zh")
        lesson = self.create_lesson(
            title="很长的每周查经指引用来确认手机布局不会把中文挤成竖排",
            scripture_reference="约翰福音 17:1-26",
        )
        self.client.login(username="study_staff", password="testpass123")

        response = self.client.get(reverse("bible_study_lesson_manage_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "每周查经指引")
        self.assertContains(response, "很长的每周查经指引")
        self.assertContains(response, "查经安排")
        self.assertContains(response, "指引日期")
        self.assertContains(response, "周四预查")
        self.assertContains(response, "范围")
        self.assertContains(response, "查看")
        self.assertContains(response, "编辑")
        self.assertContains(response, "guide-list-card")
        self.assertContains(response, "guide-list-scripture")
        self.assertNotContains(response, "<table")
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
        # BS-STRUCT.1M: generation requires structure audience rows; a root-unit
        # row expands to all active small-group units (the old global behavior).
        BibleStudySeriesAudienceScope.objects.create(
            series=self.series, unit=self.root_unit
        )
        lesson = self.create_lesson()
        # Existing structure-native meeting for the group_unit target so the
        # preview recognizes it via generation_key (1 existing of 3 eligible).
        self.create_meeting(
            lesson=lesson,
            generation_key=f"normal-unit:{self.group_unit.id}",
        )
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
        # BS-STRUCT.1M: root-unit audience row == old global scope.
        BibleStudySeriesAudienceScope.objects.create(
            series=self.series, unit=self.root_unit
        )
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
            "anchor_unit__name",
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Created 3 small group meetings")
        self.assertEqual(meetings.count(), 3)
        self.assertEqual(
            set(meetings.values_list("anchor_unit_id", flat=True)),
            {self.group_unit.id, self.same_group_unit.id, self.other_group_unit.id},
        )
        for meeting in meetings:
            self.assertEqual(
                meeting.generation_key, f"normal-unit:{meeting.anchor_unit_id}"
            )
            self.assertEqual(
                list(meeting.audience_scope_links.values_list("unit_id", flat=True)),
                [meeting.anchor_unit_id],
            )
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
        # BS-STRUCT.1M: a district-unit audience row expands to its descendant
        # small-group units (North => Rainbow 4 + Rainbow 4B).
        BibleStudySeriesAudienceScope.objects.create(
            series=self.series, unit=self.north_unit
        )
        lesson = self.create_lesson(status=BibleStudyLesson.STATUS_PUBLISHED)
        self.client.login(username="study_staff", password="testpass123")

        response = self.client.post(
            reverse("generate_bible_study_meetings", args=[lesson.id]),
        )

        self.assertEqual(response.status_code, 302)
        meetings = BibleStudyMeeting.objects.filter(lesson=lesson)
        self.assertEqual(meetings.count(), 2)
        self.assertEqual(
            set(meetings.values_list("anchor_unit_id", flat=True)),
            {self.group_unit.id, self.same_group_unit.id},
        )
        for meeting in meetings:
            self.assertEqual(
                meeting.generation_key, f"normal-unit:{meeting.anchor_unit_id}"
            )
            self.assertEqual(
                list(meeting.audience_scope_links.values_list("unit_id", flat=True)),
                [meeting.anchor_unit_id],
            )

    def test_generate_meetings_preview_uses_ministry_context_scope(self):
        self.set_language("en")
        # BS-STRUCT.1M: a ministry-context-unit audience row expands to its
        # descendant small-group units (CM => North => Rainbow 4 + Rainbow 4B).
        BibleStudySeriesAudienceScope.objects.create(
            series=self.series, unit=self.cm_unit
        )
        lesson = self.create_lesson(status=BibleStudyLesson.STATUS_PUBLISHED)
        # Existing structure-native meeting for the group_unit target.
        self.create_meeting(
            lesson=lesson,
            generation_key=f"normal-unit:{self.group_unit.id}",
        )
        self.client.login(username="study_staff", password="testpass123")

        response = self.client.get(
            reverse("generate_bible_study_meetings", args=[lesson.id]),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["generation_preview"]["eligible_count"], 2)
        self.assertEqual(response.context["generation_preview"]["existing_count"], 1)
        self.assertEqual(response.context["generation_preview"]["missing_count"], 1)

    def test_generate_meetings_uses_ministry_context_scope_idempotently(self):
        self.set_language("en")
        # BS-STRUCT.1M: CM ministry-context-unit audience row => North groups.
        BibleStudySeriesAudienceScope.objects.create(
            series=self.series, unit=self.cm_unit
        )
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

        meetings = BibleStudyMeeting.objects.filter(lesson=lesson)
        self.assertContains(first_response, "Created 2 small group meetings")
        self.assertContains(second_response, "Created 0 small group meetings")
        self.assertContains(second_response, "Skipped 2 existing meetings")
        self.assertEqual(meetings.count(), 2)
        self.assertEqual(
            set(meetings.values_list("anchor_unit_id", flat=True)),
            {self.group_unit.id, self.same_group_unit.id},
        )
        self.assertFalse(meetings.filter(anchor_unit=self.other_group_unit).exists())

    def test_generate_meetings_uses_small_group_scope(self):
        self.set_language("en")
        # BS-STRUCT.1M / BS-SERIES-SCOPE.1A: a single small-group-unit
        # audience row generates one meeting without needing legacy series FKs.
        BibleStudySeriesAudienceScope.objects.create(
            series=self.series, unit=self.group_unit
        )
        lesson = self.create_lesson(status=BibleStudyLesson.STATUS_PUBLISHED)
        self.client.login(username="study_staff", password="testpass123")

        response = self.client.post(
            reverse("generate_bible_study_meetings", args=[lesson.id]),
        )

        self.assertEqual(response.status_code, 302)
        meetings = BibleStudyMeeting.objects.filter(lesson=lesson)
        self.assertEqual(meetings.count(), 1)
        meeting = meetings.get()
        self.assertEqual(meeting.anchor_unit_id, self.group_unit.id)
        self.assertEqual(meeting.generation_key, f"normal-unit:{self.group_unit.id}")
        self.assertEqual(
            list(meeting.audience_scope_links.values_list("unit_id", flat=True)),
            [self.group_unit.id],
        )

    def test_generate_meetings_uses_series_audience_rows(self):
        self.set_language("en")
        BibleStudySeriesAudienceScope.objects.create(
            series=self.series, unit=self.group_unit
        )
        lesson = self.create_lesson(status=BibleStudyLesson.STATUS_PUBLISHED)
        self.client.login(username="study_staff", password="testpass123")

        response = self.client.post(
            reverse("generate_bible_study_meetings", args=[lesson.id]),
        )

        self.assertEqual(response.status_code, 302)
        meetings = BibleStudyMeeting.objects.filter(lesson=lesson)
        self.assertEqual(meetings.count(), 1)
        meeting = meetings.get()
        self.assertEqual(meeting.anchor_unit_id, self.group_unit.id)
        self.assertNotEqual(meeting.anchor_unit_id, self.other_group_unit.id)
        self.assertEqual(meeting.generation_key, f"normal-unit:{self.group_unit.id}")

    def test_generate_meetings_excludes_inactive_units(self):
        self.set_language("en")
        # BS-STRUCT.1M: an audience row on an active district whose only
        # descendant small-group unit is inactive expands to zero active leaf
        # units, so no meeting is generated. (Audience rows themselves must
        # reference an active unit, so the inactivity lives on the descendant.)
        empty_district = ChurchStructureUnit.objects.create(
            parent=self.cm_unit,
            unit_type=ChurchStructureUnit.UNIT_DISTRICT,
            code="EMPTYDIST",
            name="Empty District",
        )
        ChurchStructureUnit.objects.create(
            parent=empty_district,
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="INACTIVEGEN",
            name="Inactive Generate Unit",
            is_active=False,
        )
        BibleStudySeriesAudienceScope.objects.create(
            series=self.series, unit=empty_district
        )
        lesson = self.create_lesson(status=BibleStudyLesson.STATUS_PUBLISHED)
        self.client.login(username="study_staff", password="testpass123")

        response = self.client.post(
            reverse("generate_bible_study_meetings", args=[lesson.id]),
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Created 0 small group meetings")
        self.assertFalse(BibleStudyMeeting.objects.filter(lesson=lesson).exists())
        # A structure audience row is present, so the missing-audience warning
        # must not fire.
        self.assertNotContains(response, "no structure audience scope")

    def test_generate_meetings_skips_existing_without_overwriting(self):
        self.set_language("en")
        BibleStudySeriesAudienceScope.objects.create(
            series=self.series, unit=self.root_unit
        )
        lesson = self.create_lesson(status=BibleStudyLesson.STATUS_PUBLISHED)
        existing = self.create_meeting(
            lesson=lesson,
            status=BibleStudyMeeting.STATUS_PUBLISHED,
            location="Do not overwrite",
            group_direction="Existing group preparation",
            generation_key=f"normal-unit:{self.group_unit.id}",
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

    def test_generate_meetings_treats_cancelled_meeting_as_existing(self):
        self.set_language("en")
        BibleStudySeriesAudienceScope.objects.create(
            series=self.series, unit=self.root_unit
        )
        lesson = self.create_lesson(status=BibleStudyLesson.STATUS_PUBLISHED)
        existing = self.create_meeting(
            lesson=lesson,
            status=BibleStudyMeeting.STATUS_CANCELLED,
            generation_key=f"normal-unit:{self.group_unit.id}",
        )
        self.client.login(username="study_staff", password="testpass123")

        response = self.client.post(
            reverse("generate_bible_study_meetings", args=[lesson.id]),
            follow=True,
        )

        existing.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Skipped 1 existing meetings")
        self.assertEqual(existing.status, BibleStudyMeeting.STATUS_CANCELLED)
        self.assertEqual(BibleStudyMeeting.objects.filter(lesson=lesson).count(), 3)

    def test_generate_meetings_does_not_reactivate_cancelled_meeting(self):
        self.set_language("en")
        BibleStudySeriesAudienceScope.objects.create(
            series=self.series, unit=self.group_unit
        )
        lesson = self.create_lesson(status=BibleStudyLesson.STATUS_PUBLISHED)
        existing = self.create_meeting(
            lesson=lesson,
            status=BibleStudyMeeting.STATUS_CANCELLED,
            generation_key=f"normal-unit:{self.group_unit.id}",
        )
        self.client.login(username="study_staff", password="testpass123")

        response = self.client.post(
            reverse("generate_bible_study_meetings", args=[lesson.id]),
            follow=True,
        )

        existing.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Created 0 small group meetings")
        self.assertContains(response, "Skipped 1 existing meetings")
        self.assertEqual(existing.status, BibleStudyMeeting.STATUS_CANCELLED)
        self.assertEqual(BibleStudyMeeting.objects.filter(lesson=lesson).count(), 1)

    def test_generate_meetings_is_idempotent(self):
        self.set_language("en")
        BibleStudySeriesAudienceScope.objects.create(
            series=self.series, unit=self.root_unit
        )
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
        BibleStudySeriesAudienceScope.objects.create(
            series=self.series, unit=self.root_unit
        )
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
        BibleStudySeriesAudienceScope.objects.create(
            series=self.series, unit=self.root_unit
        )
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

    # ------------------------------------------------------------------
    # BS-STRUCT.1D: normal generation also writes meeting audience rows.
    # ------------------------------------------------------------------
    def test_generate_meetings_writes_one_audience_row_per_created_meeting(self):
        self.set_language("en")
        BibleStudySeriesAudienceScope.objects.create(
            series=self.series, unit=self.root_unit
        )
        lesson = self.create_lesson(status=BibleStudyLesson.STATUS_PUBLISHED)
        self.client.login(username="study_staff", password="testpass123")

        self.client.post(reverse("generate_bible_study_meetings", args=[lesson.id]))

        meetings = BibleStudyMeeting.objects.filter(lesson=lesson)
        self.assertEqual(meetings.count(), 3)
        expected_unit = {
            self.group_unit.id,
            self.same_group_unit.id,
            self.other_group_unit.id,
        }
        seen_units = set()
        for meeting in meetings:
            rows = list(meeting.audience_scope_links.all())
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0].unit_id, meeting.anchor_unit_id)
            self.assertEqual(
                meeting.generation_key, f"normal-unit:{meeting.anchor_unit_id}"
            )
            seen_units.add(meeting.anchor_unit_id)
            # meeting_kind stays normal for generated meetings.
            self.assertEqual(meeting.meeting_kind, BibleStudyMeeting.KIND_NORMAL)
            self.assertEqual(meeting.status, BibleStudyMeeting.STATUS_DRAFT)
        self.assertEqual(seen_units, expected_unit)

    def test_generate_meetings_audience_rows_are_idempotent(self):
        self.set_language("en")
        BibleStudySeriesAudienceScope.objects.create(
            series=self.series, unit=self.root_unit
        )
        lesson = self.create_lesson(status=BibleStudyLesson.STATUS_PUBLISHED)
        self.client.login(username="study_staff", password="testpass123")

        self.client.post(reverse("generate_bible_study_meetings", args=[lesson.id]))
        self.client.post(reverse("generate_bible_study_meetings", args=[lesson.id]))

        self.assertEqual(BibleStudyMeeting.objects.filter(lesson=lesson).count(), 3)
        self.assertEqual(
            BibleStudyMeetingAudienceScope.objects.filter(
                meeting__lesson=lesson
            ).count(),
            3,
        )

    def test_generate_meetings_does_not_backfill_existing_meeting(self):
        self.set_language("en")
        BibleStudySeriesAudienceScope.objects.create(
            series=self.series, unit=self.root_unit
        )
        lesson = self.create_lesson(status=BibleStudyLesson.STATUS_PUBLISHED)
        # Recognized via generation_key alone (no audience row / anchor), so the
        # skip path is exercised without the existing meeting being backfilled.
        existing = self.create_meeting(
            lesson=lesson,
            generation_key=f"normal-unit:{self.group_unit.id}",
        )
        self.client.login(username="study_staff", password="testpass123")

        self.client.post(reverse("generate_bible_study_meetings", args=[lesson.id]))

        existing.refresh_from_db()
        # Generation only writes rows for meetings it creates; the existing
        # meeting is skipped and never mutated.
        self.assertEqual(existing.audience_scope_links.count(), 0)
        self.assertIsNone(existing.anchor_unit_id)
        created = BibleStudyMeeting.objects.filter(lesson=lesson).exclude(
            id=existing.id
        )
        self.assertEqual(created.count(), 2)
        for meeting in created:
            self.assertEqual(meeting.audience_scope_links.count(), 1)

    def test_generate_meetings_district_scope_writes_rows_for_each_group(self):
        self.set_language("en")
        BibleStudySeriesAudienceScope.objects.create(
            series=self.series, unit=self.north_unit
        )
        lesson = self.create_lesson(status=BibleStudyLesson.STATUS_PUBLISHED)
        self.client.login(username="study_staff", password="testpass123")

        self.client.post(reverse("generate_bible_study_meetings", args=[lesson.id]))

        meetings = BibleStudyMeeting.objects.filter(lesson=lesson)
        self.assertEqual(meetings.count(), 2)
        for meeting in meetings:
            rows = list(meeting.audience_scope_links.all())
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0].unit_id, meeting.anchor_unit_id)
            self.assertIn(
                meeting.anchor_unit_id,
                {self.group_unit.id, self.same_group_unit.id},
            )

    # BS-STRUCT.1M: the pre-1L legacy-fallback generation tests
    # (unmapped / inactive-unit / wrong-type legacy group skipped with warning)
    # were removed. Normal generation no longer consults legacy groups at all; a
    # series with zero structure audience rows now fails closed (see
    # test_generate_meetings_without_series_audience_fails_closed below), so the
    # invalid-legacy-mapping cases they covered are unreachable from generation.

    # ------------------------------------------------------------------
    # BS-STRUCT.1M: generation requires series audience rows (fail closed).
    # ------------------------------------------------------------------
    def test_generate_meetings_without_series_audience_fails_closed(self):
        self.set_language("en")
        # self.series has zero BibleStudySeriesAudienceScope rows: generation
        # must create nothing and warn the manager. BS-SERIES-FIELD-RETIRE.1A
        # removed the legacy scope fields, so there is no legacy fallback.
        self.assertFalse(self.series.audience_scope_links.exists())
        lesson = self.create_lesson(status=BibleStudyLesson.STATUS_PUBLISHED)
        self.client.login(username="study_staff", password="testpass123")

        get_response = self.client.get(
            reverse("generate_bible_study_meetings", args=[lesson.id]),
        )
        self.assertEqual(get_response.status_code, 200)
        self.assertTrue(
            get_response.context["generation_preview"]["missing_series_audience"]
        )
        self.assertEqual(
            get_response.context["generation_preview"]["eligible_count"], 0
        )
        self.assertContains(get_response, "no structure audience scope")

        response = self.client.post(
            reverse("generate_bible_study_meetings", args=[lesson.id]),
            follow=True,
        )

        self.assertEqual(BibleStudyMeeting.objects.filter(lesson=lesson).count(), 0)
        self.assertContains(response, "no structure audience scope")

    def test_generate_meetings_without_series_audience_fails_closed_zh(self):
        self.set_language("zh")
        self.assertFalse(self.series.audience_scope_links.exists())
        lesson = self.create_lesson(status=BibleStudyLesson.STATUS_PUBLISHED)
        self.client.login(username="study_staff", password="testpass123")

        response = self.client.post(
            reverse("generate_bible_study_meetings", args=[lesson.id]),
            follow=True,
        )

        self.assertEqual(BibleStudyMeeting.objects.filter(lesson=lesson).count(), 0)
        self.assertContains(response, "还没有设置教会结构适用范围")

    # ------------------------------------------------------------------
    # BS-STRUCT.1L: normal generation targets ChurchStructureUnit leaves.
    # ------------------------------------------------------------------
    def test_generate_meetings_uses_structure_audience_descendant_units(self):
        self.set_language("en")
        # Series audience on a district unit generates one meeting per active
        # descendant UNIT_SMALL_GROUP unit, keyed on units (not legacy groups).
        BibleStudySeriesAudienceScope.objects.create(
            series=self.series, unit=self.north_unit
        )
        lesson = self.create_lesson(status=BibleStudyLesson.STATUS_PUBLISHED)
        self.client.login(username="study_staff", password="testpass123")

        self.client.post(reverse("generate_bible_study_meetings", args=[lesson.id]))

        meetings = BibleStudyMeeting.objects.filter(lesson=lesson)
        self.assertEqual(meetings.count(), 2)
        self.assertEqual(
            set(meetings.values_list("anchor_unit_id", flat=True)),
            {self.group_unit.id, self.same_group_unit.id},
        )
        for meeting in meetings:
            rows = list(meeting.audience_scope_links.all())
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0].unit_id, meeting.anchor_unit_id)
            self.assertEqual(
                meeting.generation_key, f"normal-unit:{meeting.anchor_unit_id}"
            )
            self.assertEqual(meeting.meeting_kind, BibleStudyMeeting.KIND_NORMAL)

    def test_generate_meetings_structure_native_unit_without_legacy_mirror(self):
        self.set_language("en")
        bare_unit = ChurchStructureUnit.objects.create(
            parent=self.north_unit,
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="BAREGRP",
            name="Bare Structure Group",
            name_en="Bare Structure Group",
        )
        BibleStudySeriesAudienceScope.objects.create(
            series=self.series, unit=bare_unit
        )
        lesson = self.create_lesson(status=BibleStudyLesson.STATUS_PUBLISHED)
        self.client.login(username="study_staff", password="testpass123")

        self.client.post(reverse("generate_bible_study_meetings", args=[lesson.id]))

        meeting = BibleStudyMeeting.objects.get(lesson=lesson)
        # Structure-native meeting (anchor_unit + generation_key + audience row).
        self.assertEqual(meeting.anchor_unit_id, bare_unit.id)
        self.assertEqual(meeting.generation_key, f"normal-unit:{bare_unit.id}")
        rows = list(meeting.audience_scope_links.all())
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].unit_id, bare_unit.id)
        self.assertEqual(meeting.meeting_kind, BibleStudyMeeting.KIND_NORMAL)

    def test_generate_meetings_structure_audience_is_idempotent(self):
        self.set_language("en")
        BibleStudySeriesAudienceScope.objects.create(
            series=self.series, unit=self.north_unit
        )
        lesson = self.create_lesson(status=BibleStudyLesson.STATUS_PUBLISHED)
        self.client.login(username="study_staff", password="testpass123")

        self.client.post(reverse("generate_bible_study_meetings", args=[lesson.id]))
        self.client.post(reverse("generate_bible_study_meetings", args=[lesson.id]))

        self.assertEqual(BibleStudyMeeting.objects.filter(lesson=lesson).count(), 2)
        self.assertEqual(
            BibleStudyMeetingAudienceScope.objects.filter(
                meeting__lesson=lesson
            ).count(),
            2,
        )

    def test_generate_meetings_recognizes_pre_1l_meeting_without_generation_key(self):
        self.set_language("en")
        # BS-STRUCT.1M: the schedule must carry a structure audience row for
        # generation to run; target the single small-group unit.
        BibleStudySeriesAudienceScope.objects.create(
            series=self.series, unit=self.group_unit
        )
        lesson = self.create_lesson(status=BibleStudyLesson.STATUS_PUBLISHED)
        # A pre-generation-key meeting: a single audience row but no
        # generation_key (recognized by the single-audience-unit index).
        existing = self.create_meeting(lesson=lesson)
        BibleStudyMeetingAudienceScope.objects.create(
            meeting=existing, unit=self.group_unit
        )
        self.assertIsNone(existing.generation_key)
        self.client.login(username="study_staff", password="testpass123")

        response = self.client.post(
            reverse("generate_bible_study_meetings", args=[lesson.id]),
            follow=True,
        )

        # Recognized as existing; not duplicated, not mutated.
        self.assertContains(response, "Created 0 small group meetings")
        self.assertContains(response, "Skipped 1 existing meetings")
        self.assertEqual(BibleStudyMeeting.objects.filter(lesson=lesson).count(), 1)
        self.assertEqual(
            BibleStudyMeetingAudienceScope.objects.filter(meeting=existing).count(), 1
        )

    def test_generate_meetings_audience_rows_do_not_broaden_runtime_visibility(self):
        BibleStudySeriesAudienceScope.objects.create(
            series=self.series, unit=self.root_unit
        )
        lesson = self.create_lesson(status=BibleStudyLesson.STATUS_PUBLISHED)
        self.client.login(username="study_staff", password="testpass123")
        self.client.post(reverse("generate_bible_study_meetings", args=[lesson.id]))

        group_meeting = BibleStudyMeeting.objects.get(
            lesson=lesson, anchor_unit=self.group_unit
        )
        group_meeting.status = BibleStudyMeeting.STATUS_PUBLISHED
        group_meeting.save()

        self.create_membership(self.user, self.group_unit)
        self.create_membership(self.other_user, self.other_group_unit)

        # Runtime keys visibility off audience rows + active primary membership,
        # not the legacy mirror: a member of the meeting's unit sees it; a member
        # of a different group does not.
        self.assertTrue(group_meeting.can_be_seen_by(self.user))
        self.assertFalse(group_meeting.can_be_seen_by(self.other_user))

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

    # ------------------------------------------------------------------
    # BS-STRUCT.1N: manage-list filter is structure-audience aware.
    # ------------------------------------------------------------------
    def test_meeting_manage_list_filters_by_small_group_unit(self):
        self.set_language("en")
        lesson = self.create_lesson(status=BibleStudyLesson.STATUS_PUBLISHED)
        match = self.create_meeting(lesson=lesson)
        BibleStudyMeetingAudienceScope.objects.create(
            meeting=match, unit=self.group_unit
        )
        other = self.create_meeting(lesson=lesson)
        BibleStudyMeetingAudienceScope.objects.create(
            meeting=other, unit=self.other_group_unit
        )
        self.client.login(username="study_staff", password="testpass123")

        response = self.client.get(
            reverse("bible_study_meeting_manage_list"),
            {"unit": self.group_unit.id},
        )

        listed = list(response.context["meetings"])
        self.assertIn(match, listed)
        self.assertNotIn(other, listed)
        self.assertEqual(response.context["unit_id"], str(self.group_unit.id))

    def test_meeting_manage_list_district_unit_includes_descendant(self):
        self.set_language("en")
        lesson = self.create_lesson(status=BibleStudyLesson.STATUS_PUBLISHED)
        match = self.create_meeting(lesson=lesson)
        BibleStudyMeetingAudienceScope.objects.create(
            meeting=match, unit=self.group_unit
        )
        self.client.login(username="study_staff", password="testpass123")

        response = self.client.get(
            reverse("bible_study_meeting_manage_list"),
            {"unit": self.north_unit.id},
        )

        # group_unit is a descendant of north_unit, so the meeting matches.
        self.assertIn(match, list(response.context["meetings"]))

    def test_meeting_manage_list_wrong_branch_unit_excludes(self):
        self.set_language("en")
        lesson = self.create_lesson(status=BibleStudyLesson.STATUS_PUBLISHED)
        north_meeting = self.create_meeting(lesson=lesson)
        BibleStudyMeetingAudienceScope.objects.create(
            meeting=north_meeting, unit=self.group_unit
        )
        self.client.login(username="study_staff", password="testpass123")

        response = self.client.get(
            reverse("bible_study_meeting_manage_list"),
            {"unit": self.south_unit.id},
        )

        self.assertNotIn(north_meeting, list(response.context["meetings"]))

    def test_meeting_manage_list_zero_row_meeting_excluded_by_unit_filter(self):
        self.set_language("en")
        lesson = self.create_lesson(status=BibleStudyLesson.STATUS_PUBLISHED)
        # A zero-row meeting: no audience rows at all.
        zero_row = self.create_meeting(lesson=lesson)
        self.assertEqual(zero_row.audience_scope_links.count(), 0)
        self.client.login(username="study_staff", password="testpass123")

        by_group_unit = self.client.get(
            reverse("bible_study_meeting_manage_list"),
            {"unit": self.group_unit.id},
        )
        by_district = self.client.get(
            reverse("bible_study_meeting_manage_list"),
            {"unit": self.north_unit.id},
        )

        # Unit filtering now matches audience rows only; zero-row meetings no
        # longer match through the legacy small_group mirror.
        self.assertNotIn(zero_row, list(by_group_unit.context["meetings"]))
        self.assertNotIn(zero_row, list(by_district.context["meetings"]))

    def test_meeting_manage_list_invalid_unit_fails_safe(self):
        self.set_language("en")
        lesson = self.create_lesson(status=BibleStudyLesson.STATUS_PUBLISHED)
        meeting = self.create_meeting(lesson=lesson)
        self.client.login(username="study_staff", password="testpass123")

        non_numeric = self.client.get(
            reverse("bible_study_meeting_manage_list"),
            {"unit": "not-a-number"},
        )
        unknown = self.client.get(
            reverse("bible_study_meeting_manage_list"),
            {"unit": "99999999"},
        )

        # No crash; no filter applied; select falls back to "All".
        self.assertEqual(non_numeric.status_code, 200)
        self.assertEqual(non_numeric.context["unit_id"], "")
        self.assertIn(meeting, list(non_numeric.context["meetings"]))
        self.assertEqual(unknown.status_code, 200)
        self.assertEqual(unknown.context["unit_id"], "")
        self.assertIn(meeting, list(unknown.context["meetings"]))

    def test_meeting_manage_list_template_uses_unit_filter_not_small_group(self):
        self.set_language("en")
        self.client.login(username="study_staff", password="testpass123")

        response = self.client.get(reverse("bible_study_meeting_manage_list"))

        self.assertContains(response, 'name="unit"')
        self.assertContains(response, "Audience Unit")
        self.assertNotContains(response, 'name="small_group"')

    def test_meeting_manage_list_status_and_unit_filter_combine(self):
        self.set_language("en")
        lesson = self.create_lesson(status=BibleStudyLesson.STATUS_PUBLISHED)
        published = self.create_meeting(
            lesson=lesson,
            status=BibleStudyMeeting.STATUS_PUBLISHED,
        )
        BibleStudyMeetingAudienceScope.objects.create(
            meeting=published, unit=self.group_unit
        )
        draft = self.create_meeting(
            lesson=lesson,
            status=BibleStudyMeeting.STATUS_DRAFT,
        )
        BibleStudyMeetingAudienceScope.objects.create(
            meeting=draft, unit=self.group_unit
        )
        self.client.login(username="study_staff", password="testpass123")

        response = self.client.get(
            reverse("bible_study_meeting_manage_list"),
            {"unit": self.group_unit.id, "status": BibleStudyMeeting.STATUS_PUBLISHED},
        )

        listed = list(response.context["meetings"])
        self.assertIn(published, listed)
        self.assertNotIn(draft, listed)

    def test_staff_can_create_bible_study_meeting(self):
        self.set_language("en")
        lesson = self.create_lesson(status=BibleStudyLesson.STATUS_PUBLISHED)
        self.client.login(username="study_staff", password="testpass123")

        response = self.client.post(
            reverse("create_bible_study_meeting"),
            self.meeting_post_data(lesson=lesson),
        )

        meeting = BibleStudyMeeting.objects.get(lesson=lesson)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.url,
            reverse("bible_study_meeting_detail", args=[meeting.id]),
        )
        self.assertEqual(meeting.created_by, self.staff)
        self.assertIsNone(meeting.service_event)
        self.assertEqual(meeting.anchor_unit_id, self.group_unit.id)

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

    def test_meeting_audience_unit_selector_orders_by_visible_name(self):
        zeta = ChurchStructureUnit.objects.create(
            parent=self.north_unit,
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="AAA-STUDY",
            name="Zeta Study Group",
            name_en="Zeta Study Group",
        )
        alpha = ChurchStructureUnit.objects.create(
            parent=self.north_unit,
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="ZZZ-STUDY",
            name="Alpha Study Group",
            name_en="Alpha Study Group",
        )

        form = BibleStudyMeetingForm(language="en")

        unit_ids = [unit.id for unit in form.fields["audience_unit"].queryset]
        self.assertLess(unit_ids.index(alpha.id), unit_ids.index(zeta.id))

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

    # --- BS-STRUCT.1O: manual meeting form is structure-unit-native ---

    def test_meeting_form_uses_audience_unit_not_small_group(self):
        form = BibleStudyMeetingForm()

        self.assertIn("audience_unit", form.fields)
        self.assertNotIn("small_group", form.fields)
        # The picker only offers active small-group structure units.
        unit_ids = set(
            form.fields["audience_unit"].queryset.values_list("id", flat=True)
        )
        self.assertIn(self.group_unit.id, unit_ids)
        self.assertNotIn(self.north_unit.id, unit_ids)
        self.assertNotIn(self.root_unit.id, unit_ids)

    def test_meeting_form_audience_unit_label_is_bilingual(self):
        self.assertEqual(
            BibleStudyMeetingForm().fields["audience_unit"].label,
            "Audience Unit",
        )
        self.assertEqual(
            BibleStudyMeetingForm(language="zh").fields["audience_unit"].label,
            "适用单位",
        )

    def test_meeting_form_page_has_no_legacy_small_group_select(self):
        self.set_language("en")
        self.client.login(username="study_staff", password="testpass123")

        response = self.client.get(reverse("create_bible_study_meeting"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'name="small_group"')
        self.assertContains(response, 'name="audience_unit"')

    def test_manual_create_writes_audience_row_and_anchor(self):
        self.set_language("en")
        lesson = self.create_lesson(status=BibleStudyLesson.STATUS_PUBLISHED)
        self.client.login(username="study_staff", password="testpass123")

        response = self.client.post(
            reverse("create_bible_study_meeting"),
            self.meeting_post_data(lesson=lesson, audience_unit=self.group_unit.id),
        )

        self.assertEqual(response.status_code, 302)
        meeting = BibleStudyMeeting.objects.get(lesson=lesson)
        rows = list(meeting.audience_scope_links.all())
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].unit_id, self.group_unit.id)
        self.assertEqual(meeting.anchor_unit_id, self.group_unit.id)
        self.assertEqual(meeting.meeting_kind, BibleStudyMeeting.KIND_NORMAL)

    def test_manual_create_sets_anchor_and_generation_key(self):
        self.set_language("en")
        lesson = self.create_lesson(status=BibleStudyLesson.STATUS_PUBLISHED)
        self.client.login(username="study_staff", password="testpass123")

        self.client.post(
            reverse("create_bible_study_meeting"),
            self.meeting_post_data(lesson=lesson, audience_unit=self.group_unit.id),
        )

        meeting = BibleStudyMeeting.objects.get(lesson=lesson)
        self.assertEqual(meeting.anchor_unit_id, self.group_unit.id)
        self.assertEqual(meeting.generation_key, f"normal-unit:{self.group_unit.id}")
        self.assertEqual(meeting.meeting_kind, BibleStudyMeeting.KIND_NORMAL)

    def test_manual_create_unit_without_legacy_group_is_structure_native(self):
        self.set_language("en")
        # An active small-group unit with no legacy SmallGroup mapped to it.
        lonely_unit = ChurchStructureUnit.objects.create(
            parent=self.north_unit,
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="LONELY",
            name="Lonely Group",
            name_en="Lonely Group",
        )
        lesson = self.create_lesson(status=BibleStudyLesson.STATUS_PUBLISHED)
        self.client.login(username="study_staff", password="testpass123")

        response = self.client.post(
            reverse("create_bible_study_meeting"),
            self.meeting_post_data(lesson=lesson, audience_unit=lonely_unit.id),
        )

        self.assertEqual(response.status_code, 302)
        meeting = BibleStudyMeeting.objects.get(lesson=lesson)
        rows = list(meeting.audience_scope_links.all())
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].unit_id, lonely_unit.id)
        self.assertEqual(meeting.anchor_unit_id, lonely_unit.id)

    def test_manual_create_duplicate_unit_is_rejected(self):
        self.set_language("en")
        lesson = self.create_lesson(status=BibleStudyLesson.STATUS_PUBLISHED)
        self.client.login(username="study_staff", password="testpass123")

        self.client.post(
            reverse("create_bible_study_meeting"),
            self.meeting_post_data(lesson=lesson, audience_unit=self.group_unit.id),
        )
        response = self.client.post(
            reverse("create_bible_study_meeting"),
            self.meeting_post_data(lesson=lesson, audience_unit=self.group_unit.id),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "already exists")
        self.assertEqual(
            BibleStudyMeeting.objects.filter(lesson=lesson).count(), 1
        )

    def test_manual_edit_zero_row_meeting_creates_missing_row(self):
        self.set_language("en")
        meeting = self.create_meeting(status=BibleStudyMeeting.STATUS_DRAFT)
        # Pre-condition: zero-row meeting (no audience rows, no anchor).
        self.assertEqual(meeting.audience_scope_links.count(), 0)
        self.assertIsNone(meeting.anchor_unit_id)
        self.client.login(username="study_staff", password="testpass123")

        response = self.client.post(
            reverse("edit_bible_study_meeting", args=[meeting.id]),
            self.meeting_post_data(
                lesson=meeting.lesson, audience_unit=self.group_unit.id
            ),
        )

        self.assertEqual(response.status_code, 302)
        meeting.refresh_from_db()
        rows = list(meeting.audience_scope_links.all())
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].unit_id, self.group_unit.id)
        self.assertEqual(meeting.anchor_unit_id, self.group_unit.id)
        self.assertEqual(meeting.generation_key, f"normal-unit:{self.group_unit.id}")

    def test_manual_edit_changing_unit_replaces_row_and_drops_stale(self):
        self.set_language("en")
        meeting = self.create_meeting(status=BibleStudyMeeting.STATUS_DRAFT)
        # Give it the equivalent normal small-group row + anchor first.
        BibleStudyMeetingAudienceScope.objects.create(
            meeting=meeting, unit=self.group_unit
        )
        meeting.anchor_unit = self.group_unit
        meeting.save(update_fields=["anchor_unit"])
        self.client.login(username="study_staff", password="testpass123")

        response = self.client.post(
            reverse("edit_bible_study_meeting", args=[meeting.id]),
            self.meeting_post_data(
                lesson=meeting.lesson, audience_unit=self.same_group_unit.id
            ),
        )

        self.assertEqual(response.status_code, 302)
        meeting.refresh_from_db()
        rows = list(meeting.audience_scope_links.all())
        # Exactly one row, pointing at the new unit; the stale old row is gone.
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].unit_id, self.same_group_unit.id)
        self.assertFalse(
            meeting.audience_scope_links.filter(unit=self.group_unit).exists()
        )
        # Anchor and generation_key follow the selected unit.
        self.assertEqual(meeting.anchor_unit_id, self.same_group_unit.id)
        self.assertEqual(
            meeting.generation_key, f"normal-unit:{self.same_group_unit.id}"
        )

    def test_manual_edit_duplicate_unit_is_rejected(self):
        self.set_language("en")
        lesson = self.create_lesson(status=BibleStudyLesson.STATUS_PUBLISHED)
        self.client.login(username="study_staff", password="testpass123")

        # Meeting A already targets group_unit for this lesson.
        self.client.post(
            reverse("create_bible_study_meeting"),
            self.meeting_post_data(lesson=lesson, audience_unit=self.group_unit.id),
        )
        # Meeting B targets a different unit for the same lesson.
        self.client.post(
            reverse("create_bible_study_meeting"),
            self.meeting_post_data(
                lesson=lesson, audience_unit=self.same_group_unit.id
            ),
        )
        meeting_b = BibleStudyMeeting.objects.get(
            lesson=lesson, generation_key__endswith=f":{self.same_group_unit.id}"
        )

        # Editing B onto group_unit collides with A and must be rejected.
        response = self.client.post(
            reverse("edit_bible_study_meeting", args=[meeting_b.id]),
            self.meeting_post_data(
                lesson=lesson, audience_unit=self.group_unit.id
            ),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "already exists")
        meeting_b.refresh_from_db()
        self.assertEqual(
            list(meeting_b.audience_scope_links.values_list("unit_id", flat=True)),
            [self.same_group_unit.id],
        )

    def test_manual_create_unit_not_blocked_by_unrelated_zero_row_meeting(self):
        # No false positive: a selected unit must not be blocked by an unrelated
        # zero-row meeting (no audience rows, no generation_key) for the lesson.
        self.set_language("en")
        lonely_unit = ChurchStructureUnit.objects.create(
            parent=self.north_unit,
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="LONELYFU1",
            name="Lonely Group FU1",
            name_en="Lonely Group FU1",
        )
        lesson = self.create_lesson(status=BibleStudyLesson.STATUS_PUBLISHED)
        # An unrelated old zero-row meeting on a different group.
        self.create_meeting(
            lesson=lesson,
            status=BibleStudyMeeting.STATUS_DRAFT,
        )
        self.client.login(username="study_staff", password="testpass123")

        response = self.client.post(
            reverse("create_bible_study_meeting"),
            self.meeting_post_data(lesson=lesson, audience_unit=lonely_unit.id),
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            BibleStudyMeeting.objects.filter(lesson=lesson).count(), 2
        )
        new_meeting = BibleStudyMeeting.objects.get(lesson=lesson, anchor_unit=lonely_unit)

    def test_manual_edit_does_not_clobber_multi_unit_audience(self):
        self.set_language("en")
        meeting = self.create_meeting(status=BibleStudyMeeting.STATUS_DRAFT)
        # A multi-unit (joint) audience that this small-group form must not touch.
        BibleStudyMeetingAudienceScope.objects.create(
            meeting=meeting, unit=self.group_unit
        )
        BibleStudyMeetingAudienceScope.objects.create(
            meeting=meeting, unit=self.other_group_unit
        )
        self.client.login(username="study_staff", password="testpass123")

        response = self.client.post(
            reverse("edit_bible_study_meeting", args=[meeting.id]),
            self.meeting_post_data(
                lesson=meeting.lesson, audience_unit=self.group_unit.id
            ),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "higher-level, joint, or multi-unit")
        meeting.refresh_from_db()
        self.assertEqual(
            set(meeting.audience_scope_links.values_list("unit_id", flat=True)),
            {self.group_unit.id, self.other_group_unit.id},
        )

    def test_manual_edit_does_not_clobber_higher_level_audience(self):
        self.set_language("en")
        meeting = self.create_meeting(
            status=BibleStudyMeeting.STATUS_DRAFT,
            meeting_kind=BibleStudyMeeting.KIND_HIGHER_LEVEL,
        )
        # A single district (higher-level) audience row.
        BibleStudyMeetingAudienceScope.objects.create(
            meeting=meeting, unit=self.north_unit
        )
        self.client.login(username="study_staff", password="testpass123")

        response = self.client.post(
            reverse("edit_bible_study_meeting", args=[meeting.id]),
            self.meeting_post_data(
                lesson=meeting.lesson, audience_unit=self.group_unit.id
            ),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "higher-level, joint, or multi-unit")
        meeting.refresh_from_db()
        self.assertEqual(
            list(meeting.audience_scope_links.values_list("unit_id", flat=True)),
            [self.north_unit.id],
        )
        self.assertEqual(meeting.meeting_kind, BibleStudyMeeting.KIND_HIGHER_LEVEL)

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
        original_datetime = meeting.meeting_datetime
        self.client.login(username="study_staff", password="testpass123")

        response = self.client.post(
            reverse("edit_bible_study_meeting_preparation", args=[meeting.id]),
            self.meeting_preparation_post_data(
                lesson=other_lesson.id,
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
        self.assertEqual(meeting.meeting_datetime, original_datetime)
        self.assertEqual(meeting.status, BibleStudyMeeting.STATUS_PUBLISHED)

    def test_regular_member_cannot_access_meeting_preparation_edit_page(self):
        self.set_language("en")
        meeting = self.create_meeting(status=BibleStudyMeeting.STATUS_PUBLISHED)
        BibleStudyMeetingAudienceScope.objects.create(
            meeting=meeting,
            unit=self.group_unit,
        )
        # The regular member must be able to *see* the meeting (audience row)
        # so the preparation-edit guard redirects them to meeting detail rather
        # than the list. They still cannot edit preparation.
        self.create_membership(self.user, self.group_unit)
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
        BibleStudyMeetingAudienceScope.objects.create(
            meeting=meeting,
            unit=self.group_unit,
        )
        # The regular member needs audience-row visibility to load the
        # meeting detail (200); the manager path below is unaffected by this.
        self.create_membership(self.user, self.group_unit)

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

    def test_meeting_role_form_filters_users_to_meeting_membership_core(self):
        meeting = self.create_meeting(status=BibleStudyMeeting.STATUS_PUBLISHED)
        BibleStudyMeetingAudienceScope.objects.create(
            meeting=meeting,
            unit=self.group_unit,
        )
        membership_user = User.objects.create_user(
            username="role_membership_match",
            password="testpass123",
        )
        self.create_membership(membership_user, self.group_unit)
        profile_only_user = User.objects.create_user(
            username="role_profile_only_match",
            password="testpass123",
        )

        form = BibleStudyMeetingRoleForm(meeting=meeting)

        users = form.fields["user"].queryset
        self.assertIn(membership_user, users)
        self.assertNotIn(profile_only_user, users)
        self.assertNotIn(self.user, users)
        self.assertEqual(
            list(form.fields),
            ["role", "user", "display_name", "notes", "notes_en"],
        )

    def test_meeting_role_form_orders_users_by_visible_identity(self):
        meeting = self.create_meeting(status=BibleStudyMeeting.STATUS_PUBLISHED)
        BibleStudyMeetingAudienceScope.objects.create(
            meeting=meeting,
            unit=self.group_unit,
        )
        zed = User.objects.create_user(
            username="aaa_role",
            password="testpass123",
            first_name="Zed",
            last_name="Role",
        )
        amy = User.objects.create_user(
            username="zzz_role",
            password="testpass123",
            first_name="Amy",
            last_name="Role",
        )
        self.create_membership(zed, self.group_unit)
        self.create_membership(amy, self.group_unit)

        form = BibleStudyMeetingRoleForm(meeting=meeting)

        user_ids = [user.id for user in form.fields["user"].queryset]
        self.assertLess(user_ids.index(amy.id), user_ids.index(zed.id))

    def test_meeting_role_form_keeps_selected_user_available_on_edit(self):
        meeting = self.create_meeting(status=BibleStudyMeeting.STATUS_PUBLISHED)
        BibleStudyMeetingAudienceScope.objects.create(
            meeting=meeting,
            unit=self.group_unit,
        )
        self.create_membership(self.user, self.group_unit)
        role = self.create_meeting_role(meeting, user=self.other_user)

        form = BibleStudyMeetingRoleForm(instance=role, meeting=meeting)

        users = form.fields["user"].queryset
        self.assertIn(self.user, users)
        self.assertIn(self.other_user, users)

    # ------------------------------------------------------------------
    # BS-STRUCT.1F: role picker reads meeting audience rows when present.
    # ------------------------------------------------------------------

    def test_meeting_role_form_audience_row_includes_membership_user_null_group(self):
        member = User.objects.create_user(
            username="role_audience_member",
            password="testpass123",
        )
        self.create_membership(member, self.group_unit)
        meeting = self.create_meeting(
            status=BibleStudyMeeting.STATUS_PUBLISHED,
        )
        BibleStudyMeetingAudienceScope.objects.create(
            meeting=meeting,
            unit=self.group_unit,
        )

        form = BibleStudyMeetingRoleForm(meeting=meeting)

        self.assertIn(member, form.fields["user"].queryset)

    def test_meeting_role_form_audience_district_includes_descendant_member(self):
        member = User.objects.create_user(
            username="role_audience_descendant",
            password="testpass123",
        )
        self.create_membership(member, self.group_unit)
        meeting = self.create_meeting(
            status=BibleStudyMeeting.STATUS_PUBLISHED,
        )
        # Audience targets the district; a small-group member below it matches.
        BibleStudyMeetingAudienceScope.objects.create(
            meeting=meeting,
            unit=self.north_unit,
        )

        form = BibleStudyMeetingRoleForm(meeting=meeting)

        self.assertIn(member, form.fields["user"].queryset)

    def test_meeting_role_form_audience_row_excludes_wrong_branch_user(self):
        member = User.objects.create_user(
            username="role_audience_wrong_branch",
            password="testpass123",
        )
        self.create_membership(member, self.other_group_unit)
        meeting = self.create_meeting(
            status=BibleStudyMeeting.STATUS_PUBLISHED,
        )
        BibleStudyMeetingAudienceScope.objects.create(
            meeting=meeting,
            unit=self.group_unit,
        )

        form = BibleStudyMeetingRoleForm(meeting=meeting)

        self.assertNotIn(member, form.fields["user"].queryset)

    def test_meeting_role_form_audience_row_excludes_profile_only_user(self):
        # self.user has Profile.small_group but no ChurchStructureMembership.
        meeting = self.create_meeting(
            status=BibleStudyMeeting.STATUS_PUBLISHED,
        )
        BibleStudyMeetingAudienceScope.objects.create(
            meeting=meeting,
            unit=self.group_unit,
        )

        form = BibleStudyMeetingRoleForm(meeting=meeting)

        self.assertNotIn(self.user, form.fields["user"].queryset)

    def test_meeting_role_form_audience_row_excludes_multiple_primary(self):
        member = User.objects.create_user(
            username="role_audience_multi_primary",
            password="testpass123",
        )
        today = timezone.localdate()
        # bulk_create bypasses single-active-primary model validation to set up
        # the fail-closed condition the picker must still guard against.
        ChurchStructureMembership.objects.bulk_create(
            [
                ChurchStructureMembership(
                    user=member,
                    unit=unit,
                    status=ChurchStructureMembership.STATUS_ACTIVE,
                    is_primary=True,
                    start_date=today - timezone.timedelta(days=1),
                )
                for unit in (self.group_unit, self.same_group_unit)
            ]
        )
        meeting = self.create_meeting(
            status=BibleStudyMeeting.STATUS_PUBLISHED,
        )
        BibleStudyMeetingAudienceScope.objects.create(
            meeting=meeting,
            unit=self.group_unit,
        )

        form = BibleStudyMeetingRoleForm(meeting=meeting)

        self.assertNotIn(member, form.fields["user"].queryset)

    def test_meeting_role_form_zero_row_meeting_has_no_ordinary_candidates(self):
        member = User.objects.create_user(
            username="role_zero_row_member",
            password="testpass123",
        )
        self.create_membership(member, self.group_unit)
        meeting = self.create_meeting(status=BibleStudyMeeting.STATUS_PUBLISHED)

        self.assertEqual(meeting.audience_scope_links.count(), 0)
        form = BibleStudyMeetingRoleForm(meeting=meeting)

        self.assertNotIn(member, form.fields["user"].queryset)

    def test_meeting_role_form_candidates_come_from_audience_row(self):
        rainbow4_member = User.objects.create_user(
            username="role_precedence_r4",
            password="testpass123",
        )
        self.create_membership(rainbow4_member, self.group_unit)
        rainbow5_member = User.objects.create_user(
            username="role_precedence_r5",
            password="testpass123",
        )
        self.create_membership(rainbow5_member, self.other_group_unit)
        # The audience row targets Rainbow 5, so only Rainbow 5 members are
        # candidates.
        meeting = self.create_meeting(
            status=BibleStudyMeeting.STATUS_PUBLISHED,
        )
        BibleStudyMeetingAudienceScope.objects.create(
            meeting=meeting,
            unit=self.other_group_unit,
        )

        form = BibleStudyMeetingRoleForm(meeting=meeting)

        users = form.fields["user"].queryset
        self.assertIn(rainbow5_member, users)
        self.assertNotIn(rainbow4_member, users)

    def test_meeting_role_form_keeps_selected_user_outside_audience_on_edit(self):
        # other_user belongs to Rainbow 5, outside the Rainbow 4 audience row.
        self.create_membership(self.other_user, self.other_group_unit)
        meeting = self.create_meeting(
            status=BibleStudyMeeting.STATUS_PUBLISHED,
        )
        BibleStudyMeetingAudienceScope.objects.create(
            meeting=meeting,
            unit=self.group_unit,
        )
        role = self.create_meeting_role(meeting, user=self.other_user)

        form = BibleStudyMeetingRoleForm(instance=role, meeting=meeting)

        self.assertIn(self.other_user, form.fields["user"].queryset)

    def test_meeting_role_form_rejects_blank_assignee(self):
        meeting = self.create_meeting(status=BibleStudyMeeting.STATUS_PUBLISHED)
        form = BibleStudyMeetingRoleForm(
            data=self.meeting_role_post_data(user="", display_name=""),
            meeting=meeting,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("display_name", form.errors)
        self.assertIn(
            "Choose a user or enter a display name for this role.",
            form.errors["display_name"],
        )

    def test_meeting_role_form_accepts_linked_user_without_display_name(self):
        meeting = self.create_meeting(status=BibleStudyMeeting.STATUS_PUBLISHED)
        BibleStudyMeetingAudienceScope.objects.create(
            meeting=meeting,
            unit=self.group_unit,
        )
        self.create_membership(self.user, self.group_unit)
        form = BibleStudyMeetingRoleForm(
            data=self.meeting_role_post_data(user=self.user.id, display_name=""),
            meeting=meeting,
        )

        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data["user"], self.user)
        self.assertEqual(form.cleaned_data["display_name"], "")

    def test_meeting_role_form_accepts_display_name_fallback_without_user(self):
        meeting = self.create_meeting(status=BibleStudyMeeting.STATUS_PUBLISHED)
        form = BibleStudyMeetingRoleForm(
            data=self.meeting_role_post_data(
                user="",
                display_name="Guest Leader",
            ),
            meeting=meeting,
        )

        self.assertTrue(form.is_valid())
        self.assertIsNone(form.cleaned_data["user"])
        self.assertEqual(form.cleaned_data["display_name"], "Guest Leader")

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
        self.assertContains(
            response,
            'personalized Today &quot;my role&quot; display',
        )
        self.assertContains(
            response,
            'cannot be treated as &quot;my role&quot;',
        )

    def test_chinese_meeting_role_management_help_text_renders(self):
        self.set_language("zh")
        meeting = self.create_meeting(status=BibleStudyMeeting.STATUS_PUBLISHED)
        self.client.login(username="study_staff", password="testpass123")

        response = self.client.get(
            reverse("manage_bible_study_meeting_roles", args=[meeting.id]),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "如果这位同工已有账号，请选择用户")
        self.assertContains(response, "只填写显示姓名的分工仍会显示在聚会详情")

    def test_regular_user_cannot_access_meeting_role_management_page(self):
        self.set_language("en")
        meeting = self.create_meeting(status=BibleStudyMeeting.STATUS_PUBLISHED)
        BibleStudyMeetingAudienceScope.objects.create(
            meeting=meeting,
            unit=self.group_unit,
        )
        self.create_membership(self.user, self.group_unit)
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
        BibleStudyMeetingAudienceScope.objects.create(
            meeting=meeting,
            unit=self.group_unit,
        )
        self.create_membership(self.user, self.group_unit)
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

    def test_staff_can_add_display_name_fallback_meeting_role(self):
        self.set_language("en")
        meeting = self.create_meeting(status=BibleStudyMeeting.STATUS_PUBLISHED)
        self.client.login(username="study_staff", password="testpass123")

        response = self.client.post(
            reverse("manage_bible_study_meeting_roles", args=[meeting.id]),
            self.meeting_role_post_data(user="", display_name="Guest Host"),
        )

        self.assertEqual(response.status_code, 302)
        role = BibleStudyMeetingRole.objects.get(meeting=meeting)
        self.assertEqual(role.display_name, "Guest Host")
        self.assertIsNone(role.user)

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
        BibleStudyMeetingAudienceScope.objects.create(
            meeting=meeting,
            unit=self.group_unit,
        )
        role = self.create_meeting_role(meeting)
        self.create_membership(self.user, self.group_unit)
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

    def test_regular_user_cannot_post_meeting_role(self):
        self.set_language("en")
        meeting = self.create_meeting(status=BibleStudyMeeting.STATUS_PUBLISHED)
        BibleStudyMeetingAudienceScope.objects.create(
            meeting=meeting,
            unit=self.group_unit,
        )
        self.create_membership(self.user, self.group_unit)
        self.client.login(username="regular", password="testpass123")

        response = self.client.post(
            reverse("manage_bible_study_meeting_roles", args=[meeting.id]),
            self.meeting_role_post_data(),
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.url,
            reverse("bible_study_meeting_detail", args=[meeting.id]),
        )
        self.assertFalse(BibleStudyMeetingRole.objects.filter(meeting=meeting).exists())

    def test_meeting_detail_displays_roles_to_own_group_user(self):
        self.set_language("en")
        meeting = self.create_meeting(status=BibleStudyMeeting.STATUS_PUBLISHED)
        BibleStudyMeetingAudienceScope.objects.create(
            meeting=meeting,
            unit=self.group_unit,
        )
        self.create_membership(self.user, self.group_unit)
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
        meeting = self.create_meeting()
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
        BibleStudyMeetingAudienceScope.objects.create(
            meeting=meeting,
            unit=self.group_unit,
        )

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
        self.create_membership(self.user, self.group_unit)
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
        BibleStudyMeetingAudienceScope.objects.create(
            meeting=meeting,
            unit=self.group_unit,
        )
        self.create_meeting_role(
            meeting,
            role=BibleStudyMeetingRole.ROLE_WORSHIP_LEAD,
            user=None,
            display_name="敬拜同工",
            notes="敬拜预备备注",
        )
        self.create_membership(self.user, self.group_unit)
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
        BibleStudyMeetingAudienceScope.objects.create(
            meeting=meeting,
            unit=self.group_unit,
        )
        self.create_membership(self.user, self.group_unit)
        self.client.login(username="study_staff", password="testpass123")

        response = self.client.post(
            reverse("manage_bible_study_meeting_worship_songs", args=[meeting.id]),
            self.meeting_worship_song_post_data(),
        )

        self.assertEqual(response.status_code, 302)
        song = BibleStudyMeetingWorshipSong.objects.get(meeting=meeting)
        self.assertEqual(song.title_en, "Group Worship Song")
        self.assertEqual(song.worship_lead_user, self.user)

    def test_meeting_worship_song_form_filters_worship_lead_to_membership_core(self):
        meeting = self.create_meeting(status=BibleStudyMeeting.STATUS_PUBLISHED)
        BibleStudyMeetingAudienceScope.objects.create(
            meeting=meeting,
            unit=self.group_unit,
        )
        membership_user = User.objects.create_user(
            username="worship_membership_match",
            password="testpass123",
        )
        self.create_membership(membership_user, self.group_unit)
        profile_only_user = User.objects.create_user(
            username="worship_profile_only_match",
            password="testpass123",
        )

        form = BibleStudyMeetingWorshipSongForm(meeting=meeting)

        users = list(form.fields["worship_lead_user"].queryset)
        self.assertIn(membership_user, users)
        self.assertNotIn(profile_only_user, users)
        self.assertNotIn(self.user, users)
        self.assertNotIn("meeting", form.fields)

    def test_meeting_worship_song_form_orders_users_by_visible_identity(self):
        meeting = self.create_meeting(status=BibleStudyMeeting.STATUS_PUBLISHED)
        BibleStudyMeetingAudienceScope.objects.create(
            meeting=meeting,
            unit=self.group_unit,
        )
        zed = User.objects.create_user(
            username="aaa_worship",
            password="testpass123",
            first_name="Zed",
            last_name="Worship",
        )
        amy = User.objects.create_user(
            username="zzz_worship",
            password="testpass123",
            first_name="Amy",
            last_name="Worship",
        )
        self.create_membership(zed, self.group_unit)
        self.create_membership(amy, self.group_unit)

        form = BibleStudyMeetingWorshipSongForm(meeting=meeting)

        user_ids = [user.id for user in form.fields["worship_lead_user"].queryset]
        self.assertLess(user_ids.index(amy.id), user_ids.index(zed.id))

    def test_meeting_worship_song_form_keeps_selected_lead_available_on_edit(self):
        meeting = self.create_meeting(status=BibleStudyMeeting.STATUS_PUBLISHED)
        BibleStudyMeetingAudienceScope.objects.create(
            meeting=meeting,
            unit=self.group_unit,
        )
        self.create_membership(self.user, self.group_unit)
        song = self.create_meeting_worship_song(
            meeting,
            worship_lead_user=self.other_user,
        )

        form = BibleStudyMeetingWorshipSongForm(instance=song, meeting=meeting)

        users = form.fields["worship_lead_user"].queryset
        self.assertIn(self.user, users)
        self.assertIn(self.other_user, users)

    # ------------------------------------------------------------------
    # BS-STRUCT.1F: worship picker reads meeting audience rows when present.
    # ------------------------------------------------------------------

    def test_meeting_worship_form_audience_row_includes_membership_user(self):
        member = User.objects.create_user(
            username="worship_audience_member",
            password="testpass123",
        )
        self.create_membership(member, self.group_unit)
        meeting = self.create_meeting(
            status=BibleStudyMeeting.STATUS_PUBLISHED,
        )
        BibleStudyMeetingAudienceScope.objects.create(
            meeting=meeting,
            unit=self.group_unit,
        )

        form = BibleStudyMeetingWorshipSongForm(meeting=meeting)

        self.assertIn(member, form.fields["worship_lead_user"].queryset)

    def test_meeting_worship_form_audience_district_includes_descendant_member(self):
        member = User.objects.create_user(
            username="worship_audience_descendant",
            password="testpass123",
        )
        self.create_membership(member, self.group_unit)
        meeting = self.create_meeting(
            status=BibleStudyMeeting.STATUS_PUBLISHED,
        )
        BibleStudyMeetingAudienceScope.objects.create(
            meeting=meeting,
            unit=self.north_unit,
        )

        form = BibleStudyMeetingWorshipSongForm(meeting=meeting)

        self.assertIn(member, form.fields["worship_lead_user"].queryset)

    def test_meeting_worship_form_audience_row_excludes_wrong_branch_and_profile(self):
        wrong_branch = User.objects.create_user(
            username="worship_audience_wrong_branch",
            password="testpass123",
        )
        self.create_membership(wrong_branch, self.other_group_unit)
        meeting = self.create_meeting(
            status=BibleStudyMeeting.STATUS_PUBLISHED,
        )
        BibleStudyMeetingAudienceScope.objects.create(
            meeting=meeting,
            unit=self.group_unit,
        )

        form = BibleStudyMeetingWorshipSongForm(meeting=meeting)

        users = form.fields["worship_lead_user"].queryset
        self.assertNotIn(wrong_branch, users)
        # self.user is profile-only (no ChurchStructureMembership).
        self.assertNotIn(self.user, users)

    def test_meeting_worship_form_zero_row_meeting_has_no_ordinary_candidates(self):
        member = User.objects.create_user(
            username="worship_zero_row_member",
            password="testpass123",
        )
        self.create_membership(member, self.group_unit)
        meeting = self.create_meeting(status=BibleStudyMeeting.STATUS_PUBLISHED)

        self.assertEqual(meeting.audience_scope_links.count(), 0)
        form = BibleStudyMeetingWorshipSongForm(meeting=meeting)

        self.assertNotIn(member, form.fields["worship_lead_user"].queryset)

    def test_meeting_worship_form_candidates_come_from_audience_row(self):
        rainbow4_member = User.objects.create_user(
            username="worship_precedence_r4",
            password="testpass123",
        )
        self.create_membership(rainbow4_member, self.group_unit)
        rainbow5_member = User.objects.create_user(
            username="worship_precedence_r5",
            password="testpass123",
        )
        self.create_membership(rainbow5_member, self.other_group_unit)
        meeting = self.create_meeting(
            status=BibleStudyMeeting.STATUS_PUBLISHED,
        )
        BibleStudyMeetingAudienceScope.objects.create(
            meeting=meeting,
            unit=self.other_group_unit,
        )

        form = BibleStudyMeetingWorshipSongForm(meeting=meeting)

        users = form.fields["worship_lead_user"].queryset
        self.assertIn(rainbow5_member, users)
        self.assertNotIn(rainbow4_member, users)

    def test_meeting_worship_form_keeps_selected_lead_outside_audience_on_edit(self):
        self.create_membership(self.other_user, self.other_group_unit)
        meeting = self.create_meeting(
            status=BibleStudyMeeting.STATUS_PUBLISHED,
        )
        BibleStudyMeetingAudienceScope.objects.create(
            meeting=meeting,
            unit=self.group_unit,
        )
        song = self.create_meeting_worship_song(
            meeting,
            worship_lead_user=self.other_user,
        )

        form = BibleStudyMeetingWorshipSongForm(instance=song, meeting=meeting)

        self.assertIn(self.other_user, form.fields["worship_lead_user"].queryset)

    def test_staff_can_edit_meeting_worship_song(self):
        self.set_language("en")
        meeting = self.create_meeting(status=BibleStudyMeeting.STATUS_PUBLISHED)
        BibleStudyMeetingAudienceScope.objects.create(
            meeting=meeting,
            unit=self.group_unit,
        )
        song = self.create_meeting_worship_song(meeting)
        self.create_membership(self.user, self.group_unit)
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
        BibleStudyMeetingAudienceScope.objects.create(
            meeting=meeting,
            unit=self.group_unit,
        )
        self.create_meeting_worship_song(meeting, sort_order=1)
        self.create_membership(self.user, self.group_unit)
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
        BibleStudyMeetingAudienceScope.objects.create(
            meeting=meeting,
            unit=self.group_unit,
        )
        self.create_membership(self.user, self.group_unit)
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
        meeting = self.create_meeting()
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
        BibleStudyMeetingAudienceScope.objects.create(
            meeting=meeting,
            unit=self.group_unit,
        )

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
        self.create_membership(self.user, self.group_unit)
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
        # anchor_unit drives the structure display label (".. > Rainbow 4").
        meeting = self.create_meeting(lesson=lesson, anchor_unit=self.group_unit)
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
        meeting = self.create_meeting(
            meeting_datetime=datetime(2026, 6, 12, 19, 30, tzinfo=datetime_timezone.utc),
            status=BibleStudyMeeting.STATUS_PUBLISHED,
        )
        BibleStudyMeetingAudienceScope.objects.create(
            meeting=meeting,
            unit=self.group_unit,
        )
        self.create_membership(self.user, self.group_unit)
        self.client.login(username="regular", password="testpass123")

        response = self.client.get(
            reverse("bible_study_meeting_detail", args=[meeting.id]),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Small Group Bible Study Meeting")
        self.assertContains(response, "Fri, Jun 12, 7:30 PM")
        self.assertNotContains(response, "June 12, 2026")
        self.assertContains(response, "Pastor study guide")
        self.assertContains(response, "Group direction")
        self.assertContains(response, "Group Discussion Questions")

    def test_membership_only_user_can_view_v2_meeting_detail(self):
        self.set_language("en")
        member = User.objects.create_user(
            username="detail_membership_only",
            password="testpass123",
        )
        self.create_membership(member, self.group_unit)
        meeting = self.create_meeting(status=BibleStudyMeeting.STATUS_PUBLISHED)
        BibleStudyMeetingAudienceScope.objects.create(
            meeting=meeting,
            unit=self.group_unit,
        )
        self.client.login(username="detail_membership_only", password="testpass123")

        response = self.client.get(
            reverse("bible_study_meeting_detail", args=[meeting.id]),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Small Group Bible Study Meeting")

    def test_profile_only_user_cannot_view_v2_meeting_detail(self):
        self.set_language("en")
        meeting = self.create_meeting(status=BibleStudyMeeting.STATUS_PUBLISHED)
        self.client.login(username="regular", password="testpass123")

        response = self.client.get(
            reverse("bible_study_meeting_detail", args=[meeting.id]),
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("study_session_list"))

    def test_descendant_membership_user_can_view_v2_meeting_detail(self):
        self.set_language("en")
        child_unit = ChurchStructureUnit.objects.create(
            parent=self.group_unit,
            unit_type=ChurchStructureUnit.UNIT_CUSTOM,
            code="DETAIL-R4-CHILD",
            name="Detail Rainbow 4 Child",
        )
        member = User.objects.create_user(
            username="detail_descendant",
            password="testpass123",
        )
        self.create_membership(member, child_unit)
        meeting = self.create_meeting(status=BibleStudyMeeting.STATUS_PUBLISHED)
        BibleStudyMeetingAudienceScope.objects.create(
            meeting=meeting,
            unit=self.group_unit,
        )
        self.client.login(username="detail_descendant", password="testpass123")

        response = self.client.get(
            reverse("bible_study_meeting_detail", args=[meeting.id]),
        )

        self.assertEqual(response.status_code, 200)

    def test_wrong_branch_membership_user_cannot_view_v2_meeting_detail(self):
        self.set_language("en")
        member = User.objects.create_user(
            username="detail_wrong_branch",
            password="testpass123",
        )
        self.create_membership(member, self.other_group_unit)
        meeting = self.create_meeting(status=BibleStudyMeeting.STATUS_PUBLISHED)
        self.client.login(username="detail_wrong_branch", password="testpass123")

        response = self.client.get(
            reverse("bible_study_meeting_detail", args=[meeting.id]),
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("study_session_list"))

    def test_requested_and_inactive_memberships_cannot_view_v2_meeting_detail(self):
        self.set_language("en")
        today = timezone.localdate()
        meeting = self.create_meeting(status=BibleStudyMeeting.STATUS_PUBLISHED)
        requested = User.objects.create_user(
            username="detail_requested",
            password="testpass123",
        )
        ended = User.objects.create_user(
            username="detail_ended",
            password="testpass123",
        )
        future = User.objects.create_user(
            username="detail_future",
            password="testpass123",
        )
        ChurchStructureMembership.objects.bulk_create(
            [
                ChurchStructureMembership(
                    user=requested,
                    unit=self.group_unit,
                    status=ChurchStructureMembership.STATUS_REQUESTED,
                    is_primary=True,
                    start_date=today - timezone.timedelta(days=1),
                ),
                ChurchStructureMembership(
                    user=ended,
                    unit=self.group_unit,
                    status=ChurchStructureMembership.STATUS_ENDED,
                    is_primary=True,
                    start_date=today - timezone.timedelta(days=10),
                    end_date=today - timezone.timedelta(days=1),
                ),
                ChurchStructureMembership(
                    user=future,
                    unit=self.group_unit,
                    status=ChurchStructureMembership.STATUS_ACTIVE,
                    is_primary=True,
                    start_date=today + timezone.timedelta(days=1),
                ),
            ]
        )

        for user in (requested, ended, future):
            self.client.force_login(user)
            response = self.client.get(
                reverse("bible_study_meeting_detail", args=[meeting.id]),
            )
            self.assertEqual(response.status_code, 302)
            self.assertEqual(response.url, reverse("study_session_list"))

    def test_multiple_active_primary_memberships_cannot_view_v2_meeting_detail(self):
        self.set_language("en")
        member = User.objects.create_user(
            username="detail_multi_primary",
            password="testpass123",
        )
        today = timezone.localdate()
        ChurchStructureMembership.objects.bulk_create(
            [
                ChurchStructureMembership(
                    user=member,
                    unit=unit,
                    status=ChurchStructureMembership.STATUS_ACTIVE,
                    is_primary=True,
                    start_date=today - timezone.timedelta(days=1),
                )
                for unit in (self.group_unit, self.other_group_unit)
            ]
        )
        meeting = self.create_meeting(status=BibleStudyMeeting.STATUS_PUBLISHED)
        self.client.force_login(member)

        response = self.client.get(
            reverse("bible_study_meeting_detail", args=[meeting.id]),
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("study_session_list"))

    def test_meeting_without_audience_rows_cannot_view_v2_meeting_detail(self):
        self.set_language("en")
        member = User.objects.create_user(
            username="detail_no_audience",
            password="testpass123",
        )
        self.create_membership(member, self.group_unit)
        unmapped_meeting = self.create_meeting(
            status=BibleStudyMeeting.STATUS_PUBLISHED,
        )
        wrong_type_meeting = self.create_meeting(
            lesson=self.create_lesson(status=BibleStudyLesson.STATUS_PUBLISHED),
            status=BibleStudyMeeting.STATUS_PUBLISHED,
        )
        self.client.force_login(member)

        for meeting in (unmapped_meeting, wrong_type_meeting):
            response = self.client.get(
                reverse("bible_study_meeting_detail", args=[meeting.id]),
            )
            self.assertEqual(response.status_code, 302)
            self.assertEqual(response.url, reverse("study_session_list"))

    def test_manager_override_can_view_v2_meeting_detail_without_membership(self):
        self.set_language("en")
        meeting = self.create_meeting(status=BibleStudyMeeting.STATUS_PUBLISHED)
        self.client.login(username="pastor_study", password="testpass123")

        response = self.client.get(
            reverse("bible_study_meeting_detail", args=[meeting.id]),
        )

        self.assertEqual(response.status_code, 200)

    def test_normal_user_cannot_view_another_group_meeting(self):
        self.set_language("en")
        meeting = self.create_meeting()
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
        self.create_membership(self.user, self.group_unit)
        self.client.login(username="regular", password="testpass123")

        draft_response = self.client.get(
            reverse("bible_study_meeting_detail", args=[draft.id]),
        )
        cancelled_response = self.client.get(
            reverse("bible_study_meeting_detail", args=[cancelled.id]),
        )

        self.assertEqual(draft_response.status_code, 302)
        self.assertEqual(cancelled_response.status_code, 302)

    def test_normal_user_cannot_view_meeting_when_parent_series_inactive(self):
        self.set_language("en")
        self.series.is_active = False
        self.series.save()
        meeting = self.create_meeting(status=BibleStudyMeeting.STATUS_PUBLISHED)
        self.create_membership(self.user, self.group_unit)
        self.client.login(username="regular", password="testpass123")

        response = self.client.get(
            reverse("bible_study_meeting_detail", args=[meeting.id]),
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("study_session_list"))

    def test_normal_user_cannot_view_meeting_when_parent_series_not_visible(self):
        self.set_language("en")
        self.series.status = BibleStudySeries.STATUS_DRAFT
        self.series.save()
        meeting = self.create_meeting(status=BibleStudyMeeting.STATUS_PUBLISHED)
        self.create_membership(self.user, self.group_unit)
        self.client.login(username="regular", password="testpass123")

        response = self.client.get(
            reverse("bible_study_meeting_detail", args=[meeting.id]),
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("study_session_list"))

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

    def test_staff_can_view_meeting_when_parent_series_not_public(self):
        self.set_language("en")
        self.series.status = BibleStudySeries.STATUS_DRAFT
        self.series.is_active = False
        self.series.save()
        meeting = self.create_meeting(status=BibleStudyMeeting.STATUS_PUBLISHED)
        self.client.login(username="study_staff", password="testpass123")

        response = self.client.get(
            reverse("bible_study_meeting_detail", args=[meeting.id]),
        )

        self.assertEqual(response.status_code, 200)

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
            meeting_datetime=datetime(2026, 6, 12, 19, 30, tzinfo=datetime_timezone.utc),
            status=BibleStudyMeeting.STATUS_PUBLISHED,
        )
        BibleStudyMeetingAudienceScope.objects.create(
            meeting=meeting,
            unit=self.group_unit,
        )
        # Pin the membership start well before the fixed meeting date so it is
        # still active once "now" is pinned just before that date below.
        self.create_membership(
            self.user,
            self.group_unit,
            start_date=date(2026, 1, 1),
        )
        self.client.login(username="regular", password="testpass123")

        # This test pins the meeting to a fixed Friday to assert member-facing
        # datetime formatting, so pin "now" just before it; otherwise the
        # landing's upcoming-meeting filter (meeting_datetime >= now) drops it
        # once the wall clock passes that date.
        fixed_now = datetime(2026, 6, 12, 9, 0, tzinfo=datetime_timezone.utc)
        with mock.patch("studies.views.timezone.now", return_value=fixed_now):
            response = self.client.get(reverse("study_session_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Current Bible Study")
        self.assertContains(response, "My Small Group Meeting")
        self.assertContains(response, "Bible Study Schedule")
        self.assertContains(response, "John Bible Study")
        self.assertContains(response, "Weekly Bible Study Guide")
        self.assertContains(response, "Weekly Guide")
        self.assertContains(response, "John 15:1-17")
        self.assertContains(response, "Fri, Jun 12, 7:30 PM")
        self.assertNotContains(response, "June 12, 2026")
        self.assertContains(response, "Rainbow 4")
        self.assertContains(response, "Small group home")
        self.assertContains(response, "Open My Group Meeting")
        self.assertContains(
            response,
            reverse("bible_study_meeting_detail", args=[meeting.id]),
        )
        self.assertNotContains(response, "Detailed pastor guide belongs on detail page")
        self.assertNotContains(response, "Other Bible Study Sessions")
        self.assertNotContains(response, "Legacy Bible Study Sessions")

    def test_study_list_shows_v2_current_bible_study_for_membership_only_user(self):
        self.set_language("en")
        lesson = self.create_lesson(
            status=BibleStudyLesson.STATUS_PUBLISHED,
            title_en="Membership Only Guide",
        )
        meeting = self.create_meeting(
            lesson=lesson,
            status=BibleStudyMeeting.STATUS_PUBLISHED,
        )
        BibleStudyMeetingAudienceScope.objects.create(
            meeting=meeting,
            unit=self.group_unit,
        )
        self.create_membership(self.user, self.group_unit)
        self.client.login(username="regular", password="testpass123")

        response = self.client.get(reverse("study_session_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Membership Only Guide")
        self.assertContains(
            response,
            reverse("bible_study_meeting_detail", args=[meeting.id]),
        )

    def test_study_list_keeps_same_day_started_v2_meeting_current(self):
        self.set_language("en")
        today_start = timezone.make_aware(
            datetime.combine(timezone.localdate(), datetime.min.time()),
            timezone.get_current_timezone(),
        )
        lesson = self.create_lesson(
            status=BibleStudyLesson.STATUS_PUBLISHED,
            title_en="Started Today Guide",
        )
        meeting = self.create_meeting(
            lesson=lesson,
            meeting_datetime=today_start,
            status=BibleStudyMeeting.STATUS_PUBLISHED,
        )
        BibleStudyMeetingAudienceScope.objects.create(
            meeting=meeting,
            unit=self.group_unit,
        )
        self.create_membership(self.user, self.group_unit)
        self.client.login(username="regular", password="testpass123")

        response = self.client.get(reverse("study_session_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Started Today Guide")
        self.assertIn(meeting, response.context["v2_landing"]["upcoming_meetings"])

    def test_study_list_orders_visible_v2_meetings_by_meeting_datetime(self):
        self.set_language("en")
        later_lesson = self.create_lesson(
            status=BibleStudyLesson.STATUS_PUBLISHED,
            title_en="Later Visible Guide",
        )
        earlier_lesson = self.create_lesson(
            status=BibleStudyLesson.STATUS_PUBLISHED,
            title_en="Earlier Visible Guide",
        )
        later = self.create_meeting(
            lesson=later_lesson,
            meeting_datetime=timezone.now() + timezone.timedelta(days=3),
            status=BibleStudyMeeting.STATUS_PUBLISHED,
        )
        earlier = self.create_meeting(
            lesson=earlier_lesson,
            meeting_datetime=timezone.now() + timezone.timedelta(days=1),
            status=BibleStudyMeeting.STATUS_PUBLISHED,
        )
        for meeting in (later, earlier):
            BibleStudyMeetingAudienceScope.objects.create(
                meeting=meeting,
                unit=self.group_unit,
            )
        self.create_membership(self.user, self.group_unit)
        self.client.login(username="regular", password="testpass123")

        response = self.client.get(reverse("study_session_list"))

        meeting_ids = [
            meeting.id for meeting in response.context["v2_landing"]["upcoming_meetings"]
        ]
        self.assertLess(meeting_ids.index(earlier.id), meeting_ids.index(later.id))

    def test_study_list_shows_meeting_for_descendant_membership(self):
        self.set_language("en")
        child_unit = ChurchStructureUnit.objects.create(
            parent=self.group_unit,
            unit_type=ChurchStructureUnit.UNIT_CUSTOM,
            code="RAINBOW4-CHILD",
            name="Rainbow 4 Child Unit",
        )
        lesson = self.create_lesson(
            status=BibleStudyLesson.STATUS_PUBLISHED,
            title_en="Descendant Membership Guide",
        )
        meeting = self.create_meeting(
            lesson=lesson,
            status=BibleStudyMeeting.STATUS_PUBLISHED,
        )
        BibleStudyMeetingAudienceScope.objects.create(
            meeting=meeting,
            unit=self.group_unit,
        )
        self.create_membership(self.user, child_unit)
        self.client.login(username="regular", password="testpass123")

        response = self.client.get(reverse("study_session_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Descendant Membership Guide")

    def test_study_list_profile_only_user_does_not_see_v2_meeting(self):
        self.set_language("en")
        lesson = self.create_lesson(
            status=BibleStudyLesson.STATUS_PUBLISHED,
            title_en="Profile Only Hidden Guide",
        )
        self.create_meeting(
            lesson=lesson,
            status=BibleStudyMeeting.STATUS_PUBLISHED,
        )
        self.client.login(username="regular", password="testpass123")

        response = self.client.get(reverse("study_session_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Your confirmed group membership is not ready yet, so no current Bible Study is available.",
        )
        self.assertNotContains(response, "Profile Only Hidden Guide")

    def test_study_list_hides_other_group_v2_meeting_from_normal_user(self):
        self.set_language("en")
        self.series.status = BibleStudySeries.STATUS_PUBLISHED
        self.series.save()
        self.create_membership(self.user, self.group_unit)
        other_lesson = self.create_lesson(
            status=BibleStudyLesson.STATUS_PUBLISHED,
            title_en="Other Group Weekly Guide",
        )
        self.create_meeting(
            lesson=other_lesson,
            status=BibleStudyMeeting.STATUS_PUBLISHED,
        )
        self.client.login(username="regular", password="testpass123")

        response = self.client.get(reverse("study_session_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "No current Bible Study is available yet.",
        )
        self.assertNotContains(response, "Other Bible Study Sessions")
        self.assertNotContains(response, "Other Group Weekly Guide")

    def test_study_list_hides_draft_and_cancelled_v2_meetings_from_normal_user(self):
        self.set_language("en")
        self.series.status = BibleStudySeries.STATUS_PUBLISHED
        self.series.save()
        self.create_membership(self.user, self.group_unit)
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
            "No current Bible Study is available yet.",
        )
        self.assertNotContains(response, "Draft Meeting Guide")
        self.assertNotContains(response, "Cancelled Meeting Guide")

    def test_study_list_hides_v2_meeting_under_draft_guide_from_normal_user(self):
        self.set_language("en")
        self.series.status = BibleStudySeries.STATUS_PUBLISHED
        self.series.save()
        self.create_membership(self.user, self.group_unit)
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
            "No current Bible Study is available yet.",
        )
        self.assertNotContains(response, "Draft Weekly Guide")

    def test_study_list_hides_v2_meeting_under_unpublished_or_inactive_schedule(self):
        self.set_language("en")
        self.create_membership(self.user, self.group_unit)
        draft_schedule = BibleStudySeries.objects.create(
            title="Draft Schedule",
            title_en="Draft Schedule",
            status=BibleStudySeries.STATUS_DRAFT,
        )
        inactive_schedule = BibleStudySeries.objects.create(
            title="Inactive Schedule",
            title_en="Inactive Schedule",
            status=BibleStudySeries.STATUS_PUBLISHED,
            is_active=False,
        )
        draft_schedule_lesson = self.create_lesson(
            series=draft_schedule,
            status=BibleStudyLesson.STATUS_PUBLISHED,
            title_en="Draft Schedule Guide",
        )
        inactive_schedule_lesson = self.create_lesson(
            series=inactive_schedule,
            status=BibleStudyLesson.STATUS_PUBLISHED,
            title_en="Inactive Schedule Guide",
        )
        self.create_meeting(
            lesson=draft_schedule_lesson,
            status=BibleStudyMeeting.STATUS_PUBLISHED,
        )
        self.create_meeting(
            lesson=inactive_schedule_lesson,
            status=BibleStudyMeeting.STATUS_PUBLISHED,
        )
        self.client.login(username="regular", password="testpass123")

        response = self.client.get(reverse("study_session_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No current Bible Study is available yet.")
        self.assertNotContains(response, "Draft Schedule")
        self.assertNotContains(response, "Draft Schedule Guide")
        self.assertNotContains(response, "Inactive Schedule")
        self.assertNotContains(response, "Inactive Schedule Guide")

    def test_study_list_user_without_small_group_gets_safe_v2_empty_state(self):
        self.set_language("en")
        self.client.login(username="regular", password="testpass123")

        response = self.client.get(reverse("study_session_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Your confirmed group membership is not ready yet, so no current Bible Study is available.",
        )

    def test_study_list_staff_sees_v2_management_links(self):
        self.set_language("en")
        self.client.login(username="study_staff", password="testpass123")

        response = self.client.get(reverse("study_session_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Current Bible Study")
        self.assertContains(
            response,
            "Your confirmed group membership is not ready yet, so no current Bible Study is available.",
        )
        self.assertContains(response, "Staff Links")
        self.assertContains(response, "Bible Study Schedules")
        self.assertContains(response, "Weekly Bible Study Guides")
        self.assertContains(response, "Small Group Meetings")
        self.assertContains(response, reverse("bible_study_schedule_manage_list"))
        self.assertContains(response, reverse("bible_study_lesson_manage_list"))
        self.assertContains(response, reverse("bible_study_meeting_manage_list"))
        content = response.content.decode()
        self.assertLess(content.index("Current Bible Study"), content.index("Staff Links"))
        self.assertNotContains(response, "Legacy Bible Study Sessions")
        self.assertNotContains(response, "/studies/new/")

    def test_chinese_study_list_uses_expected_v2_landing_wording(self):
        self.set_language("zh")
        self.client.login(username="study_staff", password="testpass123")

        response = self.client.get(reverse("study_session_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "当前查经")
        self.assertContains(response, "查经安排")
        self.assertContains(response, "每周查经指引")
        self.assertContains(response, "小组查经聚会")
        self.assertNotContains(response, "旧版查经安排")
        self.assertNotContains(response, "查经课程")
        self.assertNotContains(response, "查经管理")

    def test_studies_list_route_preserves_v2_landing_without_promoting_v1(self):
        self.set_language("en")
        self.client.login(username="regular", password="testpass123")

        response = self.client.get(reverse("study_session_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Bible Studies")
        self.assertContains(response, "Current Bible Study")
        self.assertNotContains(response, "V1 Session")
        self.assertNotContains(response, "Other Bible Study Sessions")
        self.assertNotContains(response, "Legacy Bible Study Sessions")

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
        self.assertIsNone(meeting.service_event)

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
        BibleStudyMeetingAudienceScope.objects.create(
            meeting=meeting,
            unit=self.group_unit,
        )
        self.create_membership(self.user, self.group_unit)

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

    def test_bible_study_meeting_role_confirm_sets_timestamp_and_preserves_first_timestamp(self):
        meeting = self.create_meeting()
        role = BibleStudyMeetingRole.objects.create(
            meeting=meeting,
            role=BibleStudyMeetingRole.ROLE_DISCUSSION_LEADER,
            user=self.manager,
        )

        role.confirm("Ready.")
        role.refresh_from_db()
        first_confirmed_at = role.confirmed_at

        self.assertIsNotNone(first_confirmed_at)
        self.assertEqual(role.confirmation_note, "Ready.")

        role.confirm("Updated note.")
        role.refresh_from_db()

        self.assertEqual(role.confirmed_at, first_confirmed_at)
        self.assertEqual(role.confirmation_note, "Updated note.")

        role.confirm("")
        role.refresh_from_db()

        self.assertEqual(role.confirmed_at, first_confirmed_at)
        self.assertEqual(role.confirmation_note, "Updated note.")

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

    # ------------------------------------------------------------------
    # BS-AS.1: Bible Study Schedule audience scope using ChurchStructureUnit
    # ------------------------------------------------------------------

    def _make_unit_series(self, *units, **overrides):
        data = {
            "title": "范围查经安排",
            "status": BibleStudySeries.STATUS_PUBLISHED,
        }
        data.update(overrides)
        series = BibleStudySeries.objects.create(**data)
        for unit in units:
            BibleStudySeriesAudienceScope.objects.create(series=series, unit=unit)
        return series

    def test_audience_scope_row_can_use_active_unit(self):
        series = BibleStudySeries.objects.create(title="活跃单元安排")
        link = BibleStudySeriesAudienceScope.objects.create(
            series=series,
            unit=self.group_unit,
        )

        self.assertEqual(list(series.get_audience_scope_units()), [self.group_unit])
        self.assertEqual(link.unit, self.group_unit)

    def test_audience_scope_duplicate_series_unit_rejected(self):
        series = BibleStudySeries.objects.create(title="重复单元安排")
        BibleStudySeriesAudienceScope.objects.create(
            series=series,
            unit=self.group_unit,
        )

        with self.assertRaises(ValidationError):
            BibleStudySeriesAudienceScope.objects.create(
                series=series,
                unit=self.group_unit,
            )

    def test_audience_scope_inactive_unit_rejected(self):
        inactive_unit = ChurchStructureUnit.objects.create(
            parent=self.north_unit,
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="INACTUNIT",
            name="Inactive Unit",
            is_active=False,
        )
        series = BibleStudySeries.objects.create(title="停用单元安排")

        with self.assertRaises(ValidationError):
            BibleStudySeriesAudienceScope.objects.create(
                series=series,
                unit=inactive_unit,
            )

    def test_audience_scope_ancestor_and_descendant_rejected(self):
        series = BibleStudySeries.objects.create(title="父子冲突安排")
        BibleStudySeriesAudienceScope.objects.create(
            series=series,
            unit=self.cm_unit,
        )

        with self.assertRaises(ValidationError):
            BibleStudySeriesAudienceScope.objects.create(
                series=series,
                unit=self.group_unit,
            )

    def test_audience_scope_root_then_other_unit_rejected(self):
        series = BibleStudySeries.objects.create(title="全教会加其他安排")
        BibleStudySeriesAudienceScope.objects.create(
            series=series,
            unit=self.root_unit,
        )

        with self.assertRaises(ValidationError):
            BibleStudySeriesAudienceScope.objects.create(
                series=series,
                unit=self.em_unit,
            )

    def test_audience_scope_other_then_root_unit_rejected(self):
        series = BibleStudySeries.objects.create(title="其他加全教会安排")
        BibleStudySeriesAudienceScope.objects.create(
            series=series,
            unit=self.em_unit,
        )

        with self.assertRaises(ValidationError):
            BibleStudySeriesAudienceScope.objects.create(
                series=series,
                unit=self.root_unit,
            )

    def test_audience_scope_sibling_units_allowed(self):
        series = BibleStudySeries.objects.create(title="兄弟单元安排")
        BibleStudySeriesAudienceScope.objects.create(
            series=series,
            unit=self.group_unit,
        )
        BibleStudySeriesAudienceScope.objects.create(
            series=series,
            unit=self.same_group_unit,
        )

        self.assertEqual(
            set(series.get_audience_scope_units()),
            {self.group_unit, self.same_group_unit},
        )

    def test_deleting_series_cascades_audience_scope_rows(self):
        series = BibleStudySeries.objects.create(title="删除安排")
        BibleStudySeriesAudienceScope.objects.create(
            series=series,
            unit=self.group_unit,
        )
        series_id = series.id

        series.delete()

        self.assertFalse(
            BibleStudySeriesAudienceScope.objects.filter(series_id=series_id).exists()
        )

    def test_deleting_referenced_unit_is_protected(self):
        series = BibleStudySeries.objects.create(title="保护单元安排")
        BibleStudySeriesAudienceScope.objects.create(
            series=series,
            unit=self.same_group_unit,
        )

        with self.assertRaises(ProtectedError):
            self.same_group_unit.delete()

    # ------------------------------------------------------------------
    # BS-STRUCT.1B: Bible Study meeting audience model foundation (inert)
    # ------------------------------------------------------------------

    def test_meeting_audience_scope_row_can_use_active_unit(self):
        meeting = self.create_meeting()
        link = BibleStudyMeetingAudienceScope.objects.create(
            meeting=meeting,
            unit=self.group_unit,
        )

        self.assertEqual(link.unit, self.group_unit)
        self.assertEqual(list(meeting.get_audience_scope_units()), [self.group_unit])

    def test_meeting_audience_scope_duplicate_meeting_unit_rejected(self):
        meeting = self.create_meeting()
        BibleStudyMeetingAudienceScope.objects.create(
            meeting=meeting,
            unit=self.group_unit,
        )

        with self.assertRaises(ValidationError):
            BibleStudyMeetingAudienceScope.objects.create(
                meeting=meeting,
                unit=self.group_unit,
            )

    def test_meeting_audience_scope_inactive_unit_rejected(self):
        inactive_unit = ChurchStructureUnit.objects.create(
            parent=self.north_unit,
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="INACTMEET",
            name="Inactive Meeting Unit",
            is_active=False,
        )
        meeting = self.create_meeting()

        with self.assertRaises(ValidationError):
            BibleStudyMeetingAudienceScope.objects.create(
                meeting=meeting,
                unit=inactive_unit,
            )

    def test_meeting_audience_scope_root_then_other_unit_rejected(self):
        meeting = self.create_meeting()
        BibleStudyMeetingAudienceScope.objects.create(
            meeting=meeting,
            unit=self.root_unit,
        )

        with self.assertRaises(ValidationError):
            BibleStudyMeetingAudienceScope.objects.create(
                meeting=meeting,
                unit=self.em_unit,
            )

    def test_meeting_audience_scope_other_then_root_unit_rejected(self):
        meeting = self.create_meeting()
        BibleStudyMeetingAudienceScope.objects.create(
            meeting=meeting,
            unit=self.em_unit,
        )

        with self.assertRaises(ValidationError):
            BibleStudyMeetingAudienceScope.objects.create(
                meeting=meeting,
                unit=self.root_unit,
            )

    def test_meeting_audience_scope_ancestor_then_descendant_rejected(self):
        meeting = self.create_meeting()
        BibleStudyMeetingAudienceScope.objects.create(
            meeting=meeting,
            unit=self.cm_unit,
        )

        with self.assertRaises(ValidationError):
            BibleStudyMeetingAudienceScope.objects.create(
                meeting=meeting,
                unit=self.group_unit,
            )

    def test_meeting_audience_scope_descendant_then_ancestor_rejected(self):
        meeting = self.create_meeting()
        BibleStudyMeetingAudienceScope.objects.create(
            meeting=meeting,
            unit=self.group_unit,
        )

        with self.assertRaises(ValidationError):
            BibleStudyMeetingAudienceScope.objects.create(
                meeting=meeting,
                unit=self.cm_unit,
            )

    def test_meeting_audience_scope_sibling_units_allowed(self):
        meeting = self.create_meeting()
        BibleStudyMeetingAudienceScope.objects.create(
            meeting=meeting,
            unit=self.group_unit,
        )
        BibleStudyMeetingAudienceScope.objects.create(
            meeting=meeting,
            unit=self.same_group_unit,
        )

        self.assertEqual(
            set(meeting.get_audience_scope_units()),
            {self.group_unit, self.same_group_unit},
        )

    def test_meeting_audience_scope_cross_branch_units_allowed(self):
        meeting = self.create_meeting()
        BibleStudyMeetingAudienceScope.objects.create(
            meeting=meeting,
            unit=self.group_unit,
        )
        BibleStudyMeetingAudienceScope.objects.create(
            meeting=meeting,
            unit=self.other_group_unit,
        )

        self.assertEqual(
            set(meeting.get_audience_scope_units()),
            {self.group_unit, self.other_group_unit},
        )

    def test_deleting_meeting_cascades_audience_scope_rows(self):
        meeting = self.create_meeting()
        BibleStudyMeetingAudienceScope.objects.create(
            meeting=meeting,
            unit=self.group_unit,
        )
        meeting_id = meeting.id

        meeting.delete()

        self.assertFalse(
            BibleStudyMeetingAudienceScope.objects.filter(
                meeting_id=meeting_id,
            ).exists()
        )

    def test_deleting_meeting_referenced_unit_is_protected(self):
        meeting = self.create_meeting()
        BibleStudyMeetingAudienceScope.objects.create(
            meeting=meeting,
            unit=self.same_group_unit,
        )

        with self.assertRaises(ProtectedError):
            self.same_group_unit.delete()

    def test_meeting_get_audience_scope_units_returns_selected_units(self):
        meeting = self.create_meeting()
        BibleStudyMeetingAudienceScope.objects.create(
            meeting=meeting,
            unit=self.group_unit,
        )

        self.assertEqual(list(meeting.get_audience_scope_units()), [self.group_unit])

    def test_higher_level_meeting_validates_with_audience_row(self):
        meeting = self.create_meeting(
            anchor_unit=self.north_unit,
            meeting_kind=BibleStudyMeeting.KIND_HIGHER_LEVEL,
        )

        # Model validation passes for a higher-level / joint-ready meeting, and
        # an audience row can still be attached to it.
        meeting.full_clean()
        self.assertEqual(meeting.anchor_unit, self.north_unit)
        BibleStudyMeetingAudienceScope.objects.create(
            meeting=meeting,
            unit=self.north_unit,
        )
        self.assertEqual(list(meeting.get_audience_scope_units()), [self.north_unit])

    def test_generation_key_duplicate_rejected_when_non_null(self):
        lesson = self.create_lesson(status=BibleStudyLesson.STATUS_PUBLISHED)
        self.create_meeting(
            lesson=lesson,
            generation_key="joint-1",
        )

        with self.assertRaises(ValidationError):
            self.create_meeting(
                lesson=lesson,
                generation_key="joint-1",
            )

    def test_multiple_null_generation_keys_allowed(self):
        lesson = self.create_lesson(status=BibleStudyLesson.STATUS_PUBLISHED)
        first = self.create_meeting(lesson=lesson)
        second = self.create_meeting(lesson=lesson)

        self.assertIsNone(first.generation_key)
        self.assertIsNone(second.generation_key)
        self.assertEqual(
            BibleStudyMeeting.objects.filter(
                lesson=lesson,
                generation_key__isnull=True,
            ).count(),
            2,
        )

    def test_generation_key_blank_normalized_to_none(self):
        meeting = self.create_meeting(generation_key="")

        self.assertIsNone(meeting.generation_key)
        meeting.refresh_from_db()
        self.assertIsNone(meeting.generation_key)

    def test_generation_key_whitespace_normalized_to_none(self):
        meeting = self.create_meeting(generation_key="   ")

        self.assertIsNone(meeting.generation_key)
        meeting.refresh_from_db()
        self.assertIsNone(meeting.generation_key)

    def test_multiple_blank_generation_keys_allowed_after_normalization(self):
        lesson = self.create_lesson(status=BibleStudyLesson.STATUS_PUBLISHED)
        first = self.create_meeting(lesson=lesson, generation_key="")
        second = self.create_meeting(
            lesson=lesson,
            generation_key="   ",
        )

        self.assertIsNone(first.generation_key)
        self.assertIsNone(second.generation_key)
        self.assertEqual(
            BibleStudyMeeting.objects.filter(
                lesson=lesson,
                generation_key__isnull=True,
            ).count(),
            2,
        )

    def test_generation_key_stripped_when_set(self):
        meeting = self.create_meeting(
            generation_key="  joint-7  ",
        )

        self.assertEqual(meeting.generation_key, "joint-7")

    def test_meeting_kind_defaults_to_normal(self):
        meeting = self.create_meeting()

        self.assertEqual(meeting.meeting_kind, BibleStudyMeeting.KIND_NORMAL)

    def test_generation_targets_expand_root_to_all_active_small_group_units(self):
        inactive_unit = ChurchStructureUnit.objects.create(
            parent=self.root_unit,
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="INACTIVE",
            name="Inactive Group",
            is_active=False,
        )
        series = self._make_unit_series(self.root_unit)

        targets, warnings = resolve_normal_generation_targets(series)
        target_units = {target.unit for target in targets}

        self.assertEqual(warnings, [])
        self.assertIn(self.group_unit, target_units)
        self.assertIn(self.same_group_unit, target_units)
        self.assertIn(self.other_group_unit, target_units)
        self.assertNotIn(inactive_unit, target_units)

    def test_generation_targets_expand_ministry_context_unit(self):
        series = self._make_unit_series(self.cm_unit)

        targets, warnings = resolve_normal_generation_targets(series)

        self.assertEqual(warnings, [])
        self.assertEqual(
            {target.unit for target in targets},
            {self.group_unit, self.same_group_unit},
        )

    def test_generation_targets_union_multiple_district_units(self):
        series = self._make_unit_series(self.north_unit, self.south_unit)

        targets, warnings = resolve_normal_generation_targets(series)

        self.assertEqual(warnings, [])
        self.assertEqual(
            {target.unit for target in targets},
            {self.group_unit, self.same_group_unit, self.other_group_unit},
        )

    def test_generation_targets_resolve_multiple_small_group_units(self):
        series = self._make_unit_series(self.group_unit, self.other_group_unit)

        targets, warnings = resolve_normal_generation_targets(series)

        self.assertEqual(warnings, [])
        self.assertEqual(
            {target.unit for target in targets},
            {self.group_unit, self.other_group_unit},
        )

    def test_generation_targets_cross_branch_has_no_duplicates(self):
        series = self._make_unit_series(self.cm_unit, self.other_group_unit)

        targets, warnings = resolve_normal_generation_targets(series)
        target_units = [target.unit for target in targets]

        self.assertEqual(warnings, [])
        self.assertEqual(
            len(target_units),
            len({unit.id for unit in target_units}),
        )
        self.assertEqual(
            set(target_units),
            {self.group_unit, self.same_group_unit, self.other_group_unit},
        )

    def test_generation_targets_exclude_inactive_units(self):
        inactive_unit = ChurchStructureUnit.objects.create(
            parent=self.north_unit,
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="INACTIVE-NORTH",
            name="Inactive North Unit Group",
            is_active=False,
        )
        series = self._make_unit_series(self.north_unit)

        targets, warnings = resolve_normal_generation_targets(series)

        self.assertEqual(warnings, [])
        self.assertNotIn(inactive_unit, [target.unit for target in targets])

    def test_generation_targets_without_audience_rows_fail_closed(self):
        series = BibleStudySeries.objects.create(title="无范围安排")

        targets, warnings = resolve_normal_generation_targets(series)

        self.assertFalse(series.audience_scope_links.exists())
        self.assertEqual(targets, [])
        self.assertEqual(len(warnings), 1)

    def test_custom_audience_unit_without_small_group_leaf_resolves_empty(self):
        custom_unit = ChurchStructureUnit.objects.create(
            parent=self.root_unit,
            unit_type=ChurchStructureUnit.UNIT_CUSTOM,
            code="CUSTOMUNIT",
            name="Custom Unit",
        )
        series = self._make_unit_series(custom_unit)

        targets, warnings = resolve_normal_generation_targets(series)

        self.assertEqual(warnings, [])
        self.assertEqual(targets, [])

    def test_schedule_form_saves_multiple_audience_units(self):
        self.set_language("en")
        self.client.login(username="study_staff", password="testpass123")

        response = self.client.post(
            reverse("create_bible_study_schedule"),
            self.schedule_post_data(
                title="多单元安排",
                title_en="Multi Unit Schedule",
                audience_units=[self.north_unit.id, self.south_unit.id],
            ),
        )

        schedule = BibleStudySeries.objects.get(title="多单元安排")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            set(schedule.get_audience_scope_units()),
            {self.north_unit, self.south_unit},
        )
        targets, warnings = resolve_normal_generation_targets(schedule)
        self.assertEqual(warnings, [])
        self.assertEqual(
            {target.unit for target in targets},
            {self.group_unit, self.same_group_unit, self.other_group_unit},
        )

    def test_editing_schedule_replaces_audience_units(self):
        self.set_language("en")
        BibleStudySeriesAudienceScope.objects.create(
            series=self.series,
            unit=self.north_unit,
        )
        BibleStudySeriesAudienceScope.objects.create(
            series=self.series,
            unit=self.south_unit,
        )
        self.client.login(username="study_staff", password="testpass123")

        response = self.client.post(
            reverse("edit_bible_study_schedule", args=[self.series.id]),
            self.schedule_post_data(
                title=self.series.title,
                title_en=self.series.title_en,
                audience_units=[self.group_unit.id],
            ),
        )

        self.assertEqual(response.status_code, 302)
        self.series.refresh_from_db()
        self.assertEqual(
            list(self.series.get_audience_scope_units()),
            [self.group_unit],
        )
        self.assertEqual(self.series.audience_scope_links.count(), 1)

    def test_schedule_form_rejects_ancestor_descendant_selection(self):
        self.set_language("en")
        self.client.login(username="study_staff", password="testpass123")

        response = self.client.post(
            reverse("create_bible_study_schedule"),
            self.schedule_post_data(
                title="冲突安排",
                audience_units=[self.cm_unit.id, self.group_unit.id],
            ),
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(BibleStudySeries.objects.filter(title="冲突安排").exists())
        self.assertIn("audience_units", response.context["form"].errors)

    def test_schedule_form_requires_audience_unit_for_new_schedule(self):
        self.set_language("en")
        self.client.login(username="study_staff", password="testpass123")

        response = self.client.post(
            reverse("create_bible_study_schedule"),
            self.schedule_post_data(title="缺范围安排", audience_units=[]),
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(BibleStudySeries.objects.filter(title="缺范围安排").exists())
        self.assertIn("audience_units", response.context["form"].errors)

    def test_schedule_pages_display_unit_scope_label(self):
        self.set_language("en")
        BibleStudySeriesAudienceScope.objects.create(
            series=self.series,
            unit=self.north_unit,
        )
        self.client.login(username="study_staff", password="testpass123")

        list_response = self.client.get(reverse("bible_study_schedule_manage_list"))
        detail_response = self.client.get(
            reverse("bible_study_schedule_detail", args=[self.series.id]),
        )

        # Compact/full labels omit the Whole Church root prefix.
        self.assertContains(list_response, "Chinese Ministry &gt; North")
        self.assertContains(detail_response, "Chinese Ministry &gt; North")
        self.assertNotContains(
            list_response,
            "Whole Church &gt; Chinese Ministry &gt; North",
        )

    def test_schedule_list_compact_label_truncates_many_units(self):
        self.set_language("en")
        # Four sibling small-group units (no ancestor/descendant conflict).
        extra_units = [self.group_unit, self.same_group_unit]
        for code in ("RAINBOW6", "RAINBOW7"):
            extra_units.append(
                ChurchStructureUnit.objects.create(
                    parent=self.north_unit,
                    unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
                    code=code,
                    name=code.title(),
                    name_en=code.title(),
                )
            )
        for unit in extra_units:
            BibleStudySeriesAudienceScope.objects.create(
                series=self.series, unit=unit
            )
        self.client.login(username="study_staff", password="testpass123")

        response = self.client.get(reverse("bible_study_schedule_manage_list"))

        # 4 units selected -> compact shows 3 then "+ 1 more".
        self.assertContains(response, "+ 1 more")

    def test_schedule_label_shows_whole_church_for_root_unit(self):
        self.set_language("en")
        BibleStudySeriesAudienceScope.objects.create(
            series=self.series,
            unit=self.root_unit,
        )
        self.client.login(username="study_staff", password="testpass123")

        detail_response = self.client.get(
            reverse("bible_study_schedule_detail", args=[self.series.id]),
        )

        self.assertContains(detail_response, "Whole Church")

    def test_lesson_pages_show_inherited_schedule_scope(self):
        self.set_language("en")
        BibleStudySeriesAudienceScope.objects.create(
            series=self.series,
            unit=self.north_unit,
        )
        lesson = self.create_lesson(series=self.series)
        self.client.login(username="study_staff", password="testpass123")

        list_response = self.client.get(reverse("bible_study_lesson_manage_list"))
        detail_response = self.client.get(
            reverse("bible_study_lesson_detail", args=[lesson.id]),
        )

        self.assertContains(list_response, "Scope from Schedule")
        self.assertContains(detail_response, "Scope from Schedule")
        self.assertContains(detail_response, "Chinese Ministry &gt; North")

    def test_chinese_lesson_detail_shows_inherited_scope_wording(self):
        self.set_language("zh")
        BibleStudySeriesAudienceScope.objects.create(
            series=self.series,
            unit=self.north_unit,
        )
        lesson = self.create_lesson(series=self.series)
        self.client.login(username="study_staff", password="testpass123")

        response = self.client.get(
            reverse("bible_study_lesson_detail", args=[lesson.id]),
        )

        self.assertContains(response, "适用范围（来自查经安排）")

    def test_lesson_form_has_no_independent_scope_fields(self):
        self.set_language("en")
        self.client.login(username="study_staff", password="testpass123")

        response = self.client.get(reverse("create_bible_study_lesson"))

        form = response.context["form"]
        for field_name in (
            "scope_type",
            "ministry_context",
            "district",
            "small_group",
            "audience_units",
        ):
            self.assertNotIn(field_name, form.fields)

    def test_generate_meetings_uses_audience_scope_units(self):
        self.set_language("en")
        BibleStudySeriesAudienceScope.objects.create(
            series=self.series,
            unit=self.north_unit,
        )
        BibleStudySeriesAudienceScope.objects.create(
            series=self.series,
            unit=self.south_unit,
        )
        lesson = self.create_lesson(
            series=self.series,
            status=BibleStudyLesson.STATUS_PUBLISHED,
        )
        self.client.login(username="study_staff", password="testpass123")

        response = self.client.post(
            reverse("generate_bible_study_meetings", args=[lesson.id]),
        )

        self.assertEqual(response.status_code, 302)
        meetings = BibleStudyMeeting.objects.filter(lesson=lesson)
        self.assertEqual(
            set(meetings.values_list("anchor_unit_id", flat=True)),
            {self.group_unit.id, self.same_group_unit.id, self.other_group_unit.id},
        )
        for meeting in meetings:
            self.assertEqual(
                meeting.generation_key, f"normal-unit:{meeting.anchor_unit_id}"
            )
            self.assertEqual(
                list(meeting.audience_scope_links.values_list("unit_id", flat=True)),
                [meeting.anchor_unit_id],
            )

    def test_generate_meetings_with_audience_scope_is_idempotent(self):
        self.set_language("en")
        BibleStudySeriesAudienceScope.objects.create(
            series=self.series,
            unit=self.north_unit,
        )
        lesson = self.create_lesson(
            series=self.series,
            status=BibleStudyLesson.STATUS_PUBLISHED,
        )
        self.client.login(username="study_staff", password="testpass123")

        self.client.post(reverse("generate_bible_study_meetings", args=[lesson.id]))
        self.client.post(reverse("generate_bible_study_meetings", args=[lesson.id]))

        meetings = BibleStudyMeeting.objects.filter(lesson=lesson)
        self.assertEqual(meetings.count(), 2)
        self.assertEqual(
            set(meetings.values_list("anchor_unit_id", flat=True)),
            {self.group_unit.id, self.same_group_unit.id},
        )

    def test_audience_scope_generation_rows_do_not_broaden_member_visibility(self):
        self.set_language("en")
        BibleStudySeriesAudienceScope.objects.create(
            series=self.series,
            unit=self.root_unit,
        )
        lesson = self.create_lesson(
            series=self.series,
            status=BibleStudyLesson.STATUS_PUBLISHED,
        )
        meeting = self.create_meeting(
            lesson=lesson,
            status=BibleStudyMeeting.STATUS_PUBLISHED,
        )
        BibleStudyMeetingAudienceScope.objects.create(
            meeting=meeting,
            unit=self.group_unit,
        )
        self.create_membership(self.user, self.group_unit)

        # The schedule audience still only controls generated legacy meetings;
        # the meeting itself is visible through its own audience row.
        self.assertTrue(meeting.can_be_seen_by(self.user))
        self.assertFalse(meeting.can_be_seen_by(self.other_user))

    def test_membership_rows_are_meeting_visibility_source(self):
        active_member = User.objects.create_user(
            username="study_active_membership",
            password="testpass123",
        )
        profile_only_member = User.objects.create_user(
            username="study_profile_only",
            password="testpass123",
        )
        requested_member = User.objects.create_user(
            username="study_requested_membership",
            password="testpass123",
        )
        ChurchStructureMembership.objects.create(
            user=active_member,
            unit=self.group_unit,
            status=ChurchStructureMembership.STATUS_ACTIVE,
            is_primary=True,
            start_date=timezone.localdate(),
        )
        ChurchStructureMembership.objects.create(
            user=requested_member,
            unit=self.group_unit,
            status=ChurchStructureMembership.STATUS_REQUESTED,
        )
        lesson = self.create_lesson(
            series=self.series,
            status=BibleStudyLesson.STATUS_PUBLISHED,
        )
        meeting = self.create_meeting(
            lesson=lesson,
            status=BibleStudyMeeting.STATUS_PUBLISHED,
        )
        BibleStudyMeetingAudienceScope.objects.create(
            meeting=meeting,
            unit=self.group_unit,
        )

        self.assertTrue(meeting.can_be_seen_by(active_member))
        self.assertFalse(meeting.can_be_seen_by(profile_only_member))
        self.assertFalse(meeting.can_be_seen_by(requested_member))

    # ------------------------------------------------------------------
    # BS-STRUCT.1E: meeting audience-row visibility + V2 landing read switch
    # ------------------------------------------------------------------

    def test_meeting_structure_display_prefers_anchor_over_audience_rows(self):
        meeting = self.create_meeting(
            anchor_unit=self.north_unit,
        )
        BibleStudyMeetingAudienceScope.objects.create(
            meeting=meeting,
            unit=self.group_unit,
        )

        self.assertEqual(
            meeting.get_structure_display_label("en"),
            "Whole Church > Chinese Ministry > North",
        )

    def test_meeting_structure_display_uses_anchor_without_audience_row(self):
        meeting = self.create_meeting(
            anchor_unit=self.group_unit,
        )
        BibleStudyMeetingAudienceScope.objects.create(
            meeting=meeting,
            unit=self.group_unit,
        )

        self.assertEqual(
            meeting.get_structure_display_label("en"),
            "Whole Church > Chinese Ministry > North > Rainbow 4",
        )

    def test_meeting_structure_display_uses_single_audience_without_anchor(self):
        meeting = self.create_meeting()
        BibleStudyMeetingAudienceScope.objects.create(
            meeting=meeting,
            unit=self.group_unit,
        )

        self.assertEqual(
            meeting.get_structure_display_label("en"),
            "Whole Church > Chinese Ministry > North > Rainbow 4",
        )

    def test_meeting_structure_display_joins_multiple_audience_units(self):
        meeting = self.create_meeting()
        BibleStudyMeetingAudienceScope.objects.create(
            meeting=meeting,
            unit=self.group_unit,
        )
        BibleStudyMeetingAudienceScope.objects.create(
            meeting=meeting,
            unit=self.other_group_unit,
        )

        self.assertEqual(
            meeting.get_structure_display_label("en"),
            (
                "Whole Church > Chinese Ministry > North > Rainbow 4, "
                "Whole Church > English Ministry > South > Rainbow 5"
            ),
        )

    def test_meeting_structure_display_unassigned_without_anchor_or_audience(self):
        # BS-MEETING-MIRROR.1A removed the legacy small_group fallback, so a
        # meeting with no anchor_unit and no audience rows is Unassigned.
        meeting = self.create_meeting()

        self.assertEqual(
            meeting.get_structure_display_label("en"),
            "Unassigned / 未指定",
        )

    def test_audience_row_membership_user_can_view_with_null_small_group(self):
        member = User.objects.create_user(
            username="bse_audience_member",
            password="testpass123",
        )
        self.create_membership(member, self.group_unit)
        meeting = self.create_meeting(
            status=BibleStudyMeeting.STATUS_PUBLISHED,
        )
        BibleStudyMeetingAudienceScope.objects.create(
            meeting=meeting,
            unit=self.group_unit,
        )

        self.assertTrue(meeting.can_be_seen_by(member))

    def test_audience_row_descendant_membership_can_view(self):
        child_unit = ChurchStructureUnit.objects.create(
            parent=self.group_unit,
            unit_type=ChurchStructureUnit.UNIT_CUSTOM,
            code="BSE-R4-CHILD",
            name="BSE Rainbow 4 Child",
        )
        member = User.objects.create_user(
            username="bse_descendant_member",
            password="testpass123",
        )
        self.create_membership(member, child_unit)
        meeting = self.create_meeting(
            status=BibleStudyMeeting.STATUS_PUBLISHED,
        )
        # Audience targets the ancestor group unit; a descendant member matches.
        BibleStudyMeetingAudienceScope.objects.create(
            meeting=meeting,
            unit=self.group_unit,
        )

        self.assertTrue(meeting.can_be_seen_by(member))

    def test_audience_row_district_membership_can_view_district_meeting(self):
        member = User.objects.create_user(
            username="bse_district_member",
            password="testpass123",
        )
        self.create_membership(member, self.north_unit)
        meeting = self.create_meeting(
            status=BibleStudyMeeting.STATUS_PUBLISHED,
        )
        BibleStudyMeetingAudienceScope.objects.create(
            meeting=meeting,
            unit=self.north_unit,
        )

        self.assertTrue(meeting.can_be_seen_by(member))

    def test_audience_row_wrong_branch_membership_cannot_view(self):
        member = User.objects.create_user(
            username="bse_wrong_branch",
            password="testpass123",
        )
        self.create_membership(member, self.other_group_unit)
        meeting = self.create_meeting(
            status=BibleStudyMeeting.STATUS_PUBLISHED,
        )
        BibleStudyMeetingAudienceScope.objects.create(
            meeting=meeting,
            unit=self.group_unit,
        )

        self.assertFalse(meeting.can_be_seen_by(member))

    def test_audience_row_profile_only_user_cannot_view(self):
        # self.user has Profile.small_group but no ChurchStructureMembership.
        meeting = self.create_meeting(
            status=BibleStudyMeeting.STATUS_PUBLISHED,
        )
        BibleStudyMeetingAudienceScope.objects.create(
            meeting=meeting,
            unit=self.group_unit,
        )

        self.assertFalse(meeting.can_be_seen_by(self.user))

    def test_audience_row_multiple_active_primary_memberships_fail_closed(self):
        member = User.objects.create_user(
            username="bse_multi_primary",
            password="testpass123",
        )
        today = timezone.localdate()
        # bulk_create bypasses the single-active-primary model validation to set
        # up the fail-closed condition the runtime must still guard against.
        ChurchStructureMembership.objects.bulk_create(
            [
                ChurchStructureMembership(
                    user=member,
                    unit=unit,
                    status=ChurchStructureMembership.STATUS_ACTIVE,
                    is_primary=True,
                    start_date=today - timezone.timedelta(days=1),
                )
                for unit in (self.group_unit, self.same_group_unit)
            ]
        )
        meeting = self.create_meeting(
            status=BibleStudyMeeting.STATUS_PUBLISHED,
        )
        BibleStudyMeetingAudienceScope.objects.create(
            meeting=meeting,
            unit=self.group_unit,
        )

        self.assertFalse(meeting.can_be_seen_by(member))

    def test_audience_row_manager_override_can_view(self):
        meeting = self.create_meeting(
            status=BibleStudyMeeting.STATUS_PUBLISHED,
        )
        BibleStudyMeetingAudienceScope.objects.create(
            meeting=meeting,
            unit=self.group_unit,
        )

        self.assertTrue(meeting.can_be_seen_by(self.manager))
        self.assertTrue(meeting.can_be_seen_by(self.staff))

    def test_zero_row_meeting_fails_closed_for_member_but_allows_manager_override(self):
        member = User.objects.create_user(
            username="bse_zero_row_member",
            password="testpass123",
        )
        self.create_membership(member, self.group_unit)
        meeting = self.create_meeting(
            status=BibleStudyMeeting.STATUS_PUBLISHED,
        )

        self.assertEqual(meeting.audience_scope_links.count(), 0)
        self.assertFalse(meeting.can_be_seen_by(member))
        self.assertFalse(meeting.can_be_seen_by(self.other_user))
        self.assertTrue(meeting.can_be_seen_by(self.manager))
        self.assertTrue(meeting.can_be_seen_by(self.staff))

    def test_audience_row_is_the_only_visibility_source(self):
        in_group_member = User.objects.create_user(
            username="bse_precedence_in_group",
            password="testpass123",
        )
        in_audience_member = User.objects.create_user(
            username="bse_precedence_in_audience",
            password="testpass123",
        )
        self.create_membership(in_group_member, self.group_unit)
        self.create_membership(in_audience_member, self.other_group_unit)
        # The audience row targets other_group_unit; only a member of that unit
        # sees the meeting. There is no longer any small_group mirror fallback.
        meeting = self.create_meeting(
            status=BibleStudyMeeting.STATUS_PUBLISHED,
        )
        BibleStudyMeetingAudienceScope.objects.create(
            meeting=meeting,
            unit=self.other_group_unit,
        )

        self.assertFalse(meeting.can_be_seen_by(in_group_member))
        self.assertTrue(meeting.can_be_seen_by(in_audience_member))

    def test_landing_shows_audience_row_meeting_with_null_small_group(self):
        self.set_language("en")
        lesson = self.create_lesson(
            status=BibleStudyLesson.STATUS_PUBLISHED,
            title_en="Audience Row Landing Guide",
        )
        meeting = self.create_meeting(
            lesson=lesson,
            status=BibleStudyMeeting.STATUS_PUBLISHED,
        )
        BibleStudyMeetingAudienceScope.objects.create(
            meeting=meeting,
            unit=self.group_unit,
        )
        self.create_membership(self.user, self.group_unit)
        self.client.login(username="regular", password="testpass123")

        response = self.client.get(reverse("study_session_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Audience Row Landing Guide")
        self.assertContains(
            response,
            "Whole Church &gt; Chinese Ministry &gt; North &gt; Rainbow 4",
        )
        self.assertContains(
            response,
            reverse("bible_study_meeting_detail", args=[meeting.id]),
        )

    def test_landing_shows_district_audience_meeting_for_descendant_membership(self):
        self.set_language("en")
        lesson = self.create_lesson(
            status=BibleStudyLesson.STATUS_PUBLISHED,
            title_en="District Audience Landing Guide",
        )
        meeting = self.create_meeting(
            lesson=lesson,
            status=BibleStudyMeeting.STATUS_PUBLISHED,
        )
        BibleStudyMeetingAudienceScope.objects.create(
            meeting=meeting,
            unit=self.north_unit,
        )
        # group_unit is a descendant of the district north_unit.
        self.create_membership(self.user, self.group_unit)
        self.client.login(username="regular", password="testpass123")

        response = self.client.get(reverse("study_session_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "District Audience Landing Guide")

    def test_landing_hides_audience_row_meeting_from_wrong_branch_membership(self):
        self.set_language("en")
        lesson = self.create_lesson(
            status=BibleStudyLesson.STATUS_PUBLISHED,
            title_en="Wrong Branch Audience Guide",
        )
        meeting = self.create_meeting(
            lesson=lesson,
            status=BibleStudyMeeting.STATUS_PUBLISHED,
        )
        BibleStudyMeetingAudienceScope.objects.create(
            meeting=meeting,
            unit=self.group_unit,
        )
        self.create_membership(self.user, self.other_group_unit)
        self.client.login(username="regular", password="testpass123")

        response = self.client.get(reverse("study_session_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No current Bible Study is available yet.")
        self.assertNotContains(response, "Wrong Branch Audience Guide")

    def test_landing_zero_row_meeting_fails_closed(self):
        self.set_language("en")
        lesson = self.create_lesson(
            status=BibleStudyLesson.STATUS_PUBLISHED,
            title_en="Zero Row Fallback Guide",
        )
        meeting = self.create_meeting(
            lesson=lesson,
            status=BibleStudyMeeting.STATUS_PUBLISHED,
        )
        self.assertEqual(meeting.audience_scope_links.count(), 0)
        self.create_membership(self.user, self.group_unit)
        self.client.login(username="regular", password="testpass123")

        response = self.client.get(reverse("study_session_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No current Bible Study is available yet.")
        self.assertNotContains(response, "Zero Row Fallback Guide")
        self.assertNotContains(
            response,
            reverse("bible_study_meeting_detail", args=[meeting.id]),
        )

    def test_landing_precedence_hides_meeting_from_original_group_member(self):
        self.set_language("en")
        lesson = self.create_lesson(
            status=BibleStudyLesson.STATUS_PUBLISHED,
            title_en="Precedence Landing Guide",
        )
        meeting = self.create_meeting(
            lesson=lesson,
            status=BibleStudyMeeting.STATUS_PUBLISHED,
        )
        # Audience row targets a different branch, so a member of the original
        # group does not see the meeting.
        BibleStudyMeetingAudienceScope.objects.create(
            meeting=meeting,
            unit=self.other_group_unit,
        )
        self.create_membership(self.user, self.group_unit)
        self.client.login(username="regular", password="testpass123")

        response = self.client.get(reverse("study_session_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No current Bible Study is available yet.")
        self.assertNotContains(response, "Precedence Landing Guide")

    def test_landing_profile_only_user_does_not_see_audience_row_meeting(self):
        self.set_language("en")
        lesson = self.create_lesson(
            status=BibleStudyLesson.STATUS_PUBLISHED,
            title_en="Profile Only Audience Guide",
        )
        meeting = self.create_meeting(
            lesson=lesson,
            status=BibleStudyMeeting.STATUS_PUBLISHED,
        )
        BibleStudyMeetingAudienceScope.objects.create(
            meeting=meeting,
            unit=self.group_unit,
        )
        # self.user keeps its Profile.small_group but has no membership.
        self.client.login(username="regular", password="testpass123")

        response = self.client.get(reverse("study_session_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Your confirmed group membership is not ready yet, so no current Bible Study is available.",
        )
        self.assertNotContains(response, "Profile Only Audience Guide")

    def test_landing_staff_links_render_with_audience_row_meeting_present(self):
        self.set_language("en")
        lesson = self.create_lesson(
            status=BibleStudyLesson.STATUS_PUBLISHED,
            title_en="Staff Audience Guide",
        )
        meeting = self.create_meeting(
            lesson=lesson,
            status=BibleStudyMeeting.STATUS_PUBLISHED,
        )
        BibleStudyMeetingAudienceScope.objects.create(
            meeting=meeting,
            unit=self.group_unit,
        )
        self.client.login(username="study_staff", password="testpass123")

        response = self.client.get(reverse("study_session_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Staff Links")
        self.assertContains(response, reverse("bible_study_meeting_manage_list"))

    # ------------------------------------------------------------------
    # BS-AS.2: audience picker UX, compact display, cancelled list cleanup
    # ------------------------------------------------------------------

    def test_audience_picker_renders_english_search_placeholder(self):
        self.set_language("en")
        self.client.login(username="study_staff", password="testpass123")

        response = self.client.get(reverse("create_bible_study_schedule"))

        self.assertContains(response, "data-audience-picker")
        self.assertContains(response, "Search audience scope...")

    def test_audience_picker_search_input_has_aria_label(self):
        self.set_language("en")
        self.client.login(username="study_staff", password="testpass123")

        response = self.client.get(reverse("create_bible_study_schedule"))

        self.assertContains(response, 'aria-label="Search audience scope"')

    def test_audience_picker_remove_label_includes_unit_label(self):
        self.set_language("en")
        self.client.login(username="study_staff", password="testpass123")

        response = self.client.get(reverse("create_bible_study_schedule"))

        # Each chip carries the readable unit label, and the remove button's
        # aria-label is built from "Remove" + that label.
        self.assertContains(response, 'data-chip-label="Chinese Ministry &gt; North"')
        self.assertContains(response, 'REMOVE_LABEL + " " + chipLabel')

    def test_audience_picker_renders_chinese_search_placeholder(self):
        self.set_language("zh")
        self.client.login(username="study_staff", password="testpass123")

        response = self.client.get(reverse("create_bible_study_schedule"))

        self.assertContains(response, "data-audience-picker")
        self.assertContains(response, "搜索适用范围...")

    def test_audience_picker_renders_tree_readable_labels(self):
        self.set_language("en")
        self.client.login(username="study_staff", password="testpass123")

        response = self.client.get(reverse("create_bible_study_schedule"))

        # Rows are checkboxes named audience_units, depth-indented, with readable
        # path labels (root prefix removed) on the chip/title attributes.
        self.assertContains(response, 'name="audience_units"')
        self.assertContains(response, "--audience-depth:")
        self.assertContains(response, 'data-chip-label="Chinese Ministry &gt; North"')
        self.assertNotContains(
            response,
            'data-chip-label="Whole Church &gt; Chinese Ministry &gt; North"',
        )

    def test_audience_picker_marks_existing_units_selected_on_edit(self):
        self.set_language("en")
        BibleStudySeriesAudienceScope.objects.create(
            series=self.series,
            unit=self.north_unit,
        )
        self.client.login(username="study_staff", password="testpass123")

        response = self.client.get(
            reverse("edit_bible_study_schedule", args=[self.series.id]),
        )

        options = response.context["form"].audience_unit_options()
        selected = [opt for opt in options if opt["selected"]]
        self.assertEqual([opt["id"] for opt in selected], [self.north_unit.id])
        self.assertContains(response, "checked")

    def test_schedule_detail_renders_scope_chips(self):
        self.set_language("en")
        BibleStudySeriesAudienceScope.objects.create(
            series=self.series,
            unit=self.north_unit,
        )
        self.client.login(username="study_staff", password="testpass123")

        response = self.client.get(
            reverse("bible_study_schedule_detail", args=[self.series.id]),
        )

        self.assertContains(response, "scope-chip")
        self.assertContains(response, "Chinese Ministry &gt; North")

    def test_lesson_list_shows_compact_inherited_scope(self):
        self.set_language("en")
        BibleStudySeriesAudienceScope.objects.create(
            series=self.series,
            unit=self.north_unit,
        )
        self.create_lesson(series=self.series)
        self.client.login(username="study_staff", password="testpass123")

        response = self.client.get(reverse("bible_study_lesson_manage_list"))

        self.assertContains(response, "Scope from Schedule")
        self.assertContains(response, "Chinese Ministry &gt; North")

    def test_schedule_manage_list_hides_cancelled_schedules(self):
        self.set_language("en")
        active = BibleStudySeries.objects.create(
            title="Active Schedule",
            title_en="Active Schedule",
            status=BibleStudySeries.STATUS_PUBLISHED,
        )
        cancelled = BibleStudySeries.objects.create(
            title="Cancelled Schedule",
            title_en="Cancelled Schedule",
            status=BibleStudySeries.STATUS_CANCELLED,
        )
        self.client.login(username="study_staff", password="testpass123")

        response = self.client.get(reverse("bible_study_schedule_manage_list"))

        listed = list(response.context["schedules"])
        self.assertIn(active, listed)
        self.assertNotIn(cancelled, listed)
        self.assertNotContains(response, "Cancelled Schedule")

    def test_schedule_manage_list_guide_count_ignores_cancelled_lessons(self):
        self.set_language("en")
        schedule = BibleStudySeries.objects.create(
            title="Count Schedule",
            status=BibleStudySeries.STATUS_PUBLISHED,
        )
        self.create_lesson(series=schedule, status=BibleStudyLesson.STATUS_PUBLISHED)
        self.create_lesson(
            series=schedule,
            status=BibleStudyLesson.STATUS_CANCELLED,
            lesson_date=timezone.localdate() + timezone.timedelta(days=20),
        )
        self.client.login(username="study_staff", password="testpass123")

        response = self.client.get(reverse("bible_study_schedule_manage_list"))

        listed = {item.id: item for item in response.context["schedules"]}
        self.assertEqual(listed[schedule.id].guide_count, 1)

    def test_lesson_manage_list_hides_cancelled_lessons(self):
        self.set_language("en")
        active = self.create_lesson(
            series=self.series,
            title_en="Active Guide",
            status=BibleStudyLesson.STATUS_PUBLISHED,
        )
        cancelled = self.create_lesson(
            series=self.series,
            title_en="Cancelled Guide",
            status=BibleStudyLesson.STATUS_CANCELLED,
            lesson_date=timezone.localdate() + timezone.timedelta(days=21),
        )
        self.client.login(username="study_staff", password="testpass123")

        response = self.client.get(reverse("bible_study_lesson_manage_list"))

        listed = list(response.context["lessons"])
        self.assertIn(active, listed)
        self.assertNotIn(cancelled, listed)

    def test_lesson_manage_list_filter_choices_exclude_cancelled(self):
        self.set_language("en")
        self.client.login(username="study_staff", password="testpass123")

        response = self.client.get(reverse("bible_study_lesson_manage_list"))

        choice_values = [value for value, _ in response.context["status_choices"]]
        self.assertNotIn(BibleStudyLesson.STATUS_CANCELLED, choice_values)

    def test_lesson_manage_list_schedule_filter_excludes_cancelled_schedules(self):
        self.set_language("en")
        cancelled = BibleStudySeries.objects.create(
            title="Cancelled Filter Schedule",
            title_en="Cancelled Filter Schedule",
            status=BibleStudySeries.STATUS_CANCELLED,
        )
        self.client.login(username="study_staff", password="testpass123")

        response = self.client.get(reverse("bible_study_lesson_manage_list"))

        options = list(response.context["series_options"])
        self.assertIn(self.series, options)
        self.assertNotIn(cancelled, options)

    def test_schedule_detail_hides_cancelled_lessons(self):
        self.set_language("en")
        active = self.create_lesson(
            series=self.series,
            title_en="Active Detail Guide",
            status=BibleStudyLesson.STATUS_PUBLISHED,
        )
        cancelled = self.create_lesson(
            series=self.series,
            title_en="Cancelled Detail Guide",
            status=BibleStudyLesson.STATUS_CANCELLED,
            lesson_date=timezone.localdate() + timezone.timedelta(days=22),
        )
        self.client.login(username="study_staff", password="testpass123")

        response = self.client.get(
            reverse("bible_study_schedule_detail", args=[self.series.id]),
        )

        listed = list(response.context["lessons"])
        self.assertIn(active, listed)
        self.assertNotIn(cancelled, listed)

    def test_meeting_manage_list_hides_cancelled_meetings(self):
        self.set_language("en")
        lesson = self.create_lesson(
            series=self.series,
            status=BibleStudyLesson.STATUS_PUBLISHED,
        )
        active = self.create_meeting(
            lesson=lesson,
            status=BibleStudyMeeting.STATUS_PUBLISHED,
        )
        cancelled = self.create_meeting(
            lesson=lesson,
            status=BibleStudyMeeting.STATUS_CANCELLED,
        )
        self.client.login(username="study_staff", password="testpass123")

        response = self.client.get(reverse("bible_study_meeting_manage_list"))

        listed = list(response.context["meetings"])
        self.assertIn(active, listed)
        self.assertNotIn(cancelled, listed)

    def test_meeting_manage_list_filter_choices_exclude_cancelled(self):
        self.set_language("en")
        self.client.login(username="study_staff", password="testpass123")

        response = self.client.get(reverse("bible_study_meeting_manage_list"))

        choice_values = [value for value, _ in response.context["status_choices"]]
        self.assertNotIn(BibleStudyMeeting.STATUS_CANCELLED, choice_values)

    def test_lesson_detail_hides_cancelled_meetings(self):
        self.set_language("en")
        # BS-STRUCT.1M: generation preview needs structure audience rows; North
        # expands to Rainbow 4 + Rainbow 4B (the two meetings below).
        BibleStudySeriesAudienceScope.objects.create(
            series=self.series, unit=self.north_unit
        )
        lesson = self.create_lesson(
            series=self.series,
            status=BibleStudyLesson.STATUS_PUBLISHED,
        )
        # Two structure-native meetings, one per North descendant group, so the
        # generation preview recognizes both targets as existing.
        active = self.create_meeting(
            lesson=lesson,
            status=BibleStudyMeeting.STATUS_PUBLISHED,
            generation_key=f"normal-unit:{self.group_unit.id}",
        )
        cancelled = self.create_meeting(
            lesson=lesson,
            status=BibleStudyMeeting.STATUS_CANCELLED,
            generation_key=f"normal-unit:{self.same_group_unit.id}",
        )
        self.client.login(username="study_staff", password="testpass123")

        response = self.client.get(
            reverse("bible_study_lesson_detail", args=[lesson.id]),
        )

        listed = list(response.context["meetings"])
        self.assertIn(active, listed)
        self.assertNotIn(cancelled, listed)
        # Generation preview still treats the cancelled meeting as existing.
        self.assertEqual(response.context["generation_preview"]["existing_count"], 2)


class BibleStudyV2AdminSurfaceTests(SimpleTestCase):
    """The active V2 admin surface remains registered after V1 schema removal."""

    def test_v2_meeting_admin_remains_registered(self):
        # The active V2 Bible Study path must remain administrable.
        self.assertIn(BibleStudyMeeting, admin.site._registry)
        self.assertIn(BibleStudyMeetingWorshipSong, admin.site._registry)
