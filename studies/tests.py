from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import ChurchRoleAssignment, District, SmallGroup
from .models import (
    BibleStudyGuide,
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
