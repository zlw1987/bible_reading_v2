import os
import tempfile

from django.core.management import call_command
from django.core.management.base import CommandError
from django.core.exceptions import ValidationError
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from django.contrib.auth.models import User

from accounts.models import ChurchRoleAssignment, District, SmallGroup
from comments.models import ReflectionComment
from events.models import ServiceEvent
from ministry.models import (
    MinistryTeam,
    TeamAssignment,
    TeamAssignmentMember,
    TeamMembership,
)
from reading.bible_sources import parse_reading_text
from reading.models import (
    ActivePlan,
    CheckIn,
    PlanEnrollment,
    ReadingGuidePost,
    ReadingPlan,
    ReadingPlanDay,
)

class StructuredPassageModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="passage_user",
            password="TestPass123!",
        )

        self.plan = ReadingPlan.objects.create(
            name="Structured Passage Plan",
            is_active=True,
        )

        self.day1 = ReadingPlanDay.objects.create(
            plan=self.plan,
            day_number=1,
            reading_text="John 1, John 2",
            memory_verse="John 1:1",
        )

        self.active_plan = ActivePlan.objects.create(
            plan=self.plan,
            start_date=timezone.localdate(),
            title="Structured Active Plan",
        )

        PlanEnrollment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
        )

    def set_language(self, language="en"):
        session = self.client.session
        session["language"] = language
        session.save()

    def test_sync_plan_day_passages_creates_reading_and_memory_passages(self):
        from reading.models import ReadingPlanDayPassage
        from reading.passage_services import sync_plan_day_passages

        created_count = sync_plan_day_passages(self.day1)

        self.assertGreaterEqual(created_count, 3)

        reading_count = ReadingPlanDayPassage.objects.filter(
            plan_day=self.day1,
            passage_type=ReadingPlanDayPassage.TYPE_READING,
        ).count()

        memory_count = ReadingPlanDayPassage.objects.filter(
            plan_day=self.day1,
            passage_type=ReadingPlanDayPassage.TYPE_MEMORY,
        ).count()

        self.assertEqual(reading_count, 2)
        self.assertEqual(memory_count, 1)

    def test_get_reading_passages_uses_structured_passages_when_available(self):
        from reading.models import ReadingPlanDayPassage
        from reading.passage_services import get_reading_passages

        ReadingPlanDayPassage.objects.create(
            plan_day=self.day1,
            passage_type=ReadingPlanDayPassage.TYPE_READING,
            sort_order=0,
            raw_reference="John 9",
            scripture_ref_key="John 9",
            display_zh="约翰福音 第 9 章",
            display_en="John 9",
            text_url_zh="https://example.com/zh",
            text_url_en="https://example.com/en",
            audio_url="https://example.com/audio",
        )

        passages = get_reading_passages(self.day1)

        self.assertEqual(len(passages), 1)
        self.assertEqual(passages[0]["search_text"], "John 9")
        self.assertEqual(passages[0]["display_en"], "John 9")
        self.assertEqual(passages[0]["audio_url"], "https://example.com/audio")

    def test_passage_reader_can_use_structured_passage(self):
        from reading.models import ReadingPlanDayPassage

        ReadingPlanDayPassage.objects.create(
            plan_day=self.day1,
            passage_type=ReadingPlanDayPassage.TYPE_READING,
            sort_order=0,
            raw_reference="John 9",
            scripture_ref_key="John 9",
            display_zh="约翰福音 第 9 章",
            display_en="John 9",
            text_url_zh="https://example.com/zh",
            text_url_en="https://example.com/en",
            audio_url="https://example.com/audio",
        )

        self.set_language("en")
        self.client.login(username="passage_user", password="TestPass123!")

        response = self.client.get(
            reverse("passage_reader", args=[self.active_plan.id, self.day1.id, 0])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "John 9")
        self.assertContains(response, "https://example.com/en")

    def test_audio_reader_can_use_structured_passage(self):
        from reading.models import ReadingPlanDayPassage

        ReadingPlanDayPassage.objects.create(
            plan_day=self.day1,
            passage_type=ReadingPlanDayPassage.TYPE_READING,
            sort_order=0,
            raw_reference="John 9",
            scripture_ref_key="John 9",
            display_zh="约翰福音 第 9 章",
            display_en="John 9",
            text_url_zh="https://example.com/zh",
            text_url_en="https://example.com/en",
            audio_url="https://example.com/audio",
        )

        self.set_language("en")
        self.client.login(username="passage_user", password="TestPass123!")

        response = self.client.get(
            reverse("audio_reader", args=[self.active_plan.id, self.day1.id, 0])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "John 9")
        self.assertContains(response, "https://example.com/audio")
        self.assertContains(response, "audio-frame-compact")

class ReadingCalendarViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="calendar_user",
            password="TestPass123!",
        )

        self.plan = ReadingPlan.objects.create(
            name="Calendar Test Plan",
            is_active=True,
        )

        today = timezone.localdate()

        self.day1 = ReadingPlanDay.objects.create(
            plan=self.plan,
            day_number=1,
            reading_text="John 1",
            memory_verse="John 1:1",
        )

        # Day 2 intentionally missing = rest / catch-up day.

        self.day3 = ReadingPlanDay.objects.create(
            plan=self.plan,
            day_number=3,
            reading_text="John 3",
            memory_verse="John 3:16",
        )

        self.active_plan = ActivePlan.objects.create(
            plan=self.plan,
            start_date=today - timezone.timedelta(days=1),
            title="Calendar Active Plan",
        )

    def set_language(self, language="en"):
        session = self.client.session
        session["language"] = language
        session.save()

    def test_calendar_requires_enrollment(self):
        self.client.login(username="calendar_user", password="TestPass123!")

        response = self.client.get(
            reverse("active_plan_calendar", args=[self.active_plan.id])
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("home"))

    def test_calendar_shows_checked_rest_and_future_states(self):
        PlanEnrollment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
        )

        CheckIn.objects.create(
            user=self.user,
            active_plan=self.active_plan,
            plan_day=self.day1,
        )

        self.client.login(username="calendar_user", password="TestPass123!")
        self.set_language("en")
        today = timezone.localdate()

        response = self.client.get(
            reverse("active_plan_calendar", args=[self.active_plan.id]),
            {
                "year": today.year,
                "month": today.month,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Reading Calendar")
        self.assertContains(response, "calendar-day-checked")
        self.assertContains(response, "calendar-day-rest")
        self.assertContains(response, "calendar-day-future")
        self.assertContains(
            response,
            reverse("passage_reader", args=[self.active_plan.id, self.day1.id, 0]),
        )
        self.assertContains(
            response,
            reverse("audio_reader", args=[self.active_plan.id, self.day1.id, 0]),
        )

    def test_calendar_month_navigation_links_render(self):
        PlanEnrollment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
        )

        self.client.login(username="calendar_user", password="TestPass123!")
        self.set_language("en")
        today = timezone.localdate()

        response = self.client.get(
            reverse("active_plan_calendar", args=[self.active_plan.id]),
            {
                "year": today.year,
                "month": today.month,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Previous")
        self.assertContains(response, "Next")
        self.assertContains(response, "month=")

class ReflectionWallVisibilityRegressionTests(TestCase):
    def setUp(self):
        self.group = SmallGroup.objects.create(name="Rainbow 4")
        self.other_group = SmallGroup.objects.create(name="Rainbow 5")

        self.author = User.objects.create_user(
            username="author",
            password="TestPass123!",
        )
        self.author.profile.small_group = self.group
        self.author.profile.save()

        self.same_group_user = User.objects.create_user(
            username="same_group",
            password="TestPass123!",
        )
        self.same_group_user.profile.small_group = self.group
        self.same_group_user.profile.save()

        self.other_group_user = User.objects.create_user(
            username="other_group",
            password="TestPass123!",
        )
        self.other_group_user.profile.small_group = self.other_group
        self.other_group_user.profile.save()

        self.staff = User.objects.create_user(
            username="staff",
            password="TestPass123!",
            is_staff=True,
        )

        self.plan = ReadingPlan.objects.create(
            name="Regression Test Plan",
            is_active=True,
        )

        self.day1 = ReadingPlanDay.objects.create(
            plan=self.plan,
            day_number=1,
            reading_text="John 1",
            memory_verse="John 1:1",
        )

        self.active_plan = ActivePlan.objects.create(
            plan=self.plan,
            start_date=timezone.localdate(),
            title="Regression Active Plan",
        )

        for user in [
            self.author,
            self.same_group_user,
            self.other_group_user,
            self.staff,
        ]:
            PlanEnrollment.objects.create(
                user=user,
                active_plan=self.active_plan,
            )

    def make_reflection(
        self,
        *,
        user=None,
        body="Test reflection.",
        visibility=ReflectionComment.VISIBILITY_GROUP,
        is_hidden=False,
        is_anonymous=False,
        small_group=None,
        parent=None,
    ):
        if user is None:
            user = self.author

        if small_group is None:
            small_group = self.group

        return ReflectionComment.objects.create(
            user=user,
            active_plan=self.active_plan,
            plan_day=self.day1,
            parent=parent,
            scripture_ref_key="John 1",
            scripture_display_zh="约翰福音 第 1 章",
            scripture_display_en="John 1",
            visibility=visibility,
            is_hidden=is_hidden,
            is_anonymous=is_anonymous,
            small_group_at_post=small_group,
            body=body,
        )

    def test_reader_shows_comment_thread_and_visible_reply(self):
        parent = self.make_reflection(
            body="Parent reflection.",
            visibility=ReflectionComment.VISIBILITY_GROUP,
        )

        self.make_reflection(
            user=self.same_group_user,
            parent=parent,
            body="Visible reply.",
            visibility=ReflectionComment.VISIBILITY_GROUP,
            small_group=self.group,
        )

        self.client.login(username="same_group", password="TestPass123!")

        response = self.client.get(
            reverse("passage_reader", args=[self.active_plan.id, self.day1.id, 0])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Parent reflection.")
        self.assertContains(response, "Visible reply.")

    def test_text_reader_and_audio_reader_share_reflection_flow(self):
        self.make_reflection(
            body="Shared reflection.",
            visibility=ReflectionComment.VISIBILITY_GROUP,
        )

        self.client.login(username="same_group", password="TestPass123!")

        text_response = self.client.get(
            reverse("passage_reader", args=[self.active_plan.id, self.day1.id, 0])
        )

        audio_response = self.client.get(
            reverse("audio_reader", args=[self.active_plan.id, self.day1.id, 0])
        )

        self.assertEqual(text_response.status_code, 200)
        self.assertEqual(audio_response.status_code, 200)

        self.assertContains(text_response, "Shared reflection.")
        self.assertContains(audio_response, "Shared reflection.")

        self.assertContains(text_response, "scripture-frame")
        self.assertNotContains(text_response, "audio-frame-compact")

        self.assertContains(audio_response, "audio-frame-compact")
        self.assertNotContains(audio_response, "scripture-frame")

    def test_group_reflection_is_visible_to_same_group_user(self):
        self.make_reflection(
            body="Same group reflection.",
            visibility=ReflectionComment.VISIBILITY_GROUP,
            small_group=self.group,
        )

        self.client.login(username="same_group", password="TestPass123!")

        response = self.client.get(
            reverse("passage_wall"),
            {
                "ref": "John 1",
                "tab": "group",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Same group reflection.")

    def test_group_reflection_is_hidden_from_other_group_user(self):
        self.make_reflection(
            body="Hidden from other group.",
            visibility=ReflectionComment.VISIBILITY_GROUP,
            small_group=self.group,
        )

        self.client.login(username="other_group", password="TestPass123!")

        response = self.client.get(
            reverse("passage_wall"),
            {
                "ref": "John 1",
                "tab": "group",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Hidden from other group.")

    def test_church_reflection_is_visible_on_reflection_wall(self):
        self.make_reflection(
            body="Church-wide reflection.",
            visibility=ReflectionComment.VISIBILITY_CHURCH,
        )

        self.client.login(username="other_group", password="TestPass123!")

        response = self.client.get(
            reverse("passage_wall"),
            {
                "ref": "John 1",
                "tab": "church",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Church-wide reflection.")

    def test_hidden_reflection_is_not_visible_to_other_regular_user_on_wall(self):
        self.make_reflection(
            body="Hidden wall reflection.",
            visibility=ReflectionComment.VISIBILITY_CHURCH,
            is_hidden=True,
        )

        self.client.login(username="other_group", password="TestPass123!")

        response = self.client.get(
            reverse("passage_wall"),
            {
                "ref": "John 1",
                "tab": "church",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Hidden wall reflection.")

    def test_hidden_reflection_is_visible_to_author_on_wall(self):
        self.make_reflection(
            body="My hidden reflection.",
            visibility=ReflectionComment.VISIBILITY_CHURCH,
            is_hidden=True,
        )

        self.client.login(username="author", password="TestPass123!")

        response = self.client.get(
            reverse("passage_wall"),
            {
                "ref": "John 1",
                "tab": "church",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "My hidden reflection.")
        self.assertContains(response, "已隐藏")

    def test_hidden_reflection_is_visible_to_staff_on_wall(self):
        self.make_reflection(
            body="Staff-visible hidden reflection.",
            visibility=ReflectionComment.VISIBILITY_CHURCH,
            is_hidden=True,
        )

        self.client.login(username="staff", password="TestPass123!")

        response = self.client.get(
            reverse("passage_wall"),
            {
                "ref": "John 1",
                "tab": "church",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Staff-visible hidden reflection.")
        self.assertContains(response, "已隐藏")

    def test_anonymous_reflection_hides_author_from_regular_user(self):
        self.make_reflection(
            body="Anonymous reflection.",
            visibility=ReflectionComment.VISIBILITY_CHURCH,
            is_anonymous=True,
        )

        self.client.login(username="other_group", password="TestPass123!")

        response = self.client.get(
            reverse("passage_wall"),
            {
                "ref": "John 1",
                "tab": "church",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Anonymous reflection.")
        self.assertContains(response, "Anonymous")
        self.assertNotContains(response, "author")

    def test_staff_can_see_anonymous_author(self):
        self.make_reflection(
            body="Anonymous staff-visible reflection.",
            visibility=ReflectionComment.VISIBILITY_CHURCH,
            is_anonymous=True,
        )

        self.client.login(username="staff", password="TestPass123!")

        response = self.client.get(
            reverse("passage_wall"),
            {
                "ref": "John 1",
                "tab": "church",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Anonymous staff-visible reflection.")
        self.assertContains(response, "Anonymous (author)")

class ImportReadingPlanCommandTests(TestCase):
    def setUp(self):
        self.temp_files = []

    def tearDown(self):
        for file_path in self.temp_files:
            if os.path.exists(file_path):
                os.remove(file_path)

    def make_csv(self, content):
        temp_file = tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".csv",
            encoding="utf-8",
            newline="",
            delete=False,
        )
        temp_file.write(content)
        temp_file.close()

        self.temp_files.append(temp_file.name)
        return temp_file.name

    def test_import_reading_plan_creates_plan_and_days(self):
        csv_path = self.make_csv(
            "day_number,reading_text,memory_verse\n"
            "1,John 1,John 1:1\n"
            "2,John 2,John 2:11\n"
        )

        call_command(
            "import_reading_plan",
            "--name",
            "Imported John Plan",
            "--file",
            csv_path,
        )

        plan = ReadingPlan.objects.get(name="Imported John Plan")

        self.assertEqual(plan.days.count(), 2)
        self.assertTrue(
            ReadingPlanDay.objects.filter(
                plan=plan,
                day_number=1,
                reading_text="John 1",
                memory_verse="John 1:1",
            ).exists()
        )

    def test_import_reading_plan_with_start_date_creates_active_plan(self):
        csv_path = self.make_csv(
            "day_number,reading_text,memory_verse\n"
            "1,John 1,John 1:1\n"
        )

        call_command(
            "import_reading_plan",
            "--name",
            "Plan With Active Run",
            "--file",
            csv_path,
            "--start-date",
            "2026-05-12",
            "--active-title",
            "May Active Run",
        )

        plan = ReadingPlan.objects.get(name="Plan With Active Run")

        self.assertTrue(
            ActivePlan.objects.filter(
                plan=plan,
                start_date="2026-05-12",
                title="May Active Run",
            ).exists()
        )

    def test_import_reading_plan_rejects_duplicate_day_numbers(self):
        csv_path = self.make_csv(
            "day_number,reading_text,memory_verse\n"
            "1,John 1,John 1:1\n"
            "1,John 2,John 2:11\n"
        )

        with self.assertRaises(CommandError):
            call_command(
                "import_reading_plan",
                "--name",
                "Bad Duplicate Plan",
                "--file",
                csv_path,
            )

    def test_import_reading_plan_rejects_blank_reading_text(self):
        csv_path = self.make_csv(
            "day_number,reading_text,memory_verse\n"
            "1,,John 1:1\n"
        )

        with self.assertRaises(CommandError):
            call_command(
                "import_reading_plan",
                "--name",
                "Bad Blank Plan",
                "--file",
                csv_path,
            )

    def test_import_reading_plan_replace_overwrites_existing_days(self):
        plan = ReadingPlan.objects.create(
            name="Replace Plan",
            description="Old",
            is_active=True,
        )

        ReadingPlanDay.objects.create(
            plan=plan,
            day_number=1,
            reading_text="Old Reading",
            memory_verse="Old Verse",
        )

        csv_path = self.make_csv(
            "day_number,reading_text,memory_verse\n"
            "1,New Reading,New Verse\n"
            "2,Second Reading,\n"
        )

        call_command(
            "import_reading_plan",
            "--name",
            "Replace Plan",
            "--file",
            csv_path,
            "--replace",
        )

        plan.refresh_from_db()

        self.assertEqual(plan.days.count(), 2)
        self.assertTrue(
            ReadingPlanDay.objects.filter(
                plan=plan,
                day_number=1,
                reading_text="New Reading",
                memory_verse="New Verse",
            ).exists()
        )
        self.assertFalse(
            ReadingPlanDay.objects.filter(
                plan=plan,
                reading_text="Old Reading",
            ).exists()
        )

class BibleReadingFlowTests(TestCase):
    def setUp(self):
        self.group = SmallGroup.objects.create(name="Rainbow 4")

        self.user = User.objects.create_user(
            username="levin",
            email="levin@example.com",
            password="testpass123",
        )

        self.other_user = User.objects.create_user(
            username="other",
            email="other@example.com",
            password="testpass123",
        )

        self.admin = User.objects.create_user(
            username="admin",
            email="admin@example.com",
            password="testpass123",
            is_staff=True,
        )

        self.plan = ReadingPlan.objects.create(
            name="Test 7-Day Bible Reading",
            description="Test plan",
            is_active=True,
        )

        self.day1 = ReadingPlanDay.objects.create(
            plan=self.plan,
            day_number=1,
            reading_text="John 1",
            memory_verse="John 1:1",
        )

        self.day2 = ReadingPlanDay.objects.create(
            plan=self.plan,
            day_number=2,
            reading_text="John 2",
            memory_verse="John 2:11",
        )

        self.future_day = ReadingPlanDay.objects.create(
            plan=self.plan,
            day_number=10,
            reading_text="John 10",
            memory_verse="John 10:11",
        )

        self.active_plan = ActivePlan.objects.create(
            plan=self.plan,
            start_date=timezone.localdate(),
            title="May Test Plan",
        )

    def set_language(self, language="en"):
        session = self.client.session
        session["language"] = language
        session.save()

    def create_guide_publisher(self, username="pastor_user"):
        publisher = User.objects.create_user(
            username=username,
            email=f"{username}@example.com",
            password="testpass123",
        )
        ChurchRoleAssignment.objects.create(
            user=publisher,
            role=ChurchRoleAssignment.ROLE_PASTOR,
            scope_type=ChurchRoleAssignment.SCOPE_GLOBAL,
        )
        return publisher

    def test_login_required_for_home(self):
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_user_can_join_active_plan(self):
        self.client.login(username="levin", password="testpass123")

        response = self.client.post(
            reverse("join_active_plan", args=[self.active_plan.id])
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            PlanEnrollment.objects.filter(
                user=self.user,
                active_plan=self.active_plan,
            ).exists()
        )

    def test_user_cannot_join_same_plan_twice(self):
        self.client.login(username="levin", password="testpass123")

        self.client.post(reverse("join_active_plan", args=[self.active_plan.id]))
        self.client.post(reverse("join_active_plan", args=[self.active_plan.id]))

        count = PlanEnrollment.objects.filter(
            user=self.user,
            active_plan=self.active_plan,
        ).count()

        self.assertEqual(count, 1)

    def test_unenrolled_user_cannot_view_plan_detail(self):
        self.client.login(username="levin", password="testpass123")

        response = self.client.get(
            reverse("active_plan_detail", args=[self.active_plan.id])
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("home"))

    def test_intro_page_requires_login(self):
        response = self.client.get(
            reverse("active_plan_intro", args=[self.active_plan.id])
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_enrolled_user_can_view_intro_page(self):
        self.set_language("en")
        PlanEnrollment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
        )

        self.client.login(username="levin", password="testpass123")

        response = self.client.get(
            reverse("active_plan_intro", args=[self.active_plan.id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Reading Plan Introduction")
        self.assertContains(response, "May Test Plan")

    def test_non_enrolled_user_can_view_active_plan_intro(self):
        self.set_language("en")
        self.client.login(username="levin", password="testpass123")

        response = self.client.get(
            reverse("active_plan_intro", args=[self.active_plan.id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Reading Plan Introduction")

    def test_non_enrolled_user_sees_join_plan_button_on_intro(self):
        self.set_language("en")
        self.client.login(username="levin", password="testpass123")

        response = self.client.get(
            reverse("active_plan_intro", args=[self.active_plan.id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("join_active_plan", args=[self.active_plan.id]))
        self.assertContains(response, "Join this plan")

    def test_enrolled_user_sees_calendar_and_schedule_actions_on_intro(self):
        self.set_language("en")
        PlanEnrollment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
        )

        self.client.login(username="levin", password="testpass123")

        response = self.client.get(
            reverse("active_plan_intro", args=[self.active_plan.id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "View Calendar")
        self.assertContains(response, "View Schedule")
        self.assertContains(response, reverse("active_plan_calendar", args=[self.active_plan.id]))
        self.assertContains(response, reverse("active_plan_detail", args=[self.active_plan.id]))

    def test_intro_shows_today_text_and_audio_actions_for_enrolled_user(self):
        self.set_language("en")
        PlanEnrollment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
        )

        self.client.login(username="levin", password="testpass123")

        response = self.client.get(
            reverse("active_plan_intro", args=[self.active_plan.id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Start Today’s Reading")
        self.assertContains(response, "Listen to Today’s Reading")
        self.assertContains(
            response,
            reverse("passage_reader", args=[self.active_plan.id, self.day1.id, 0]),
        )
        self.assertContains(
            response,
            reverse("audio_reader", args=[self.active_plan.id, self.day1.id, 0]),
        )

    def test_inactive_plan_intro_hidden_from_regular_non_enrolled_user(self):
        self.plan.is_active = False
        self.plan.save()

        self.set_language("en")
        self.client.login(username="levin", password="testpass123")

        response = self.client.get(
            reverse("active_plan_intro", args=[self.active_plan.id])
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("home"))

    def test_staff_can_view_inactive_plan_intro(self):
        self.plan.is_active = False
        self.plan.save()

        self.set_language("en")
        self.client.login(username="admin", password="testpass123")

        response = self.client.get(
            reverse("active_plan_intro", args=[self.active_plan.id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Reading Plan Introduction")

    def test_chinese_intro_page_shows_chinese_labels(self):
        self.set_language("zh")
        self.client.login(username="levin", password="testpass123")

        response = self.client.get(
            reverse("active_plan_intro", args=[self.active_plan.id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "读经计划介绍")
        self.assertContains(response, "计划简介")
        self.assertContains(response, "如何读")
        self.assertContains(response, "读经指引")

    def test_english_intro_page_shows_english_labels(self):
        self.set_language("en")
        self.client.login(username="levin", password="testpass123")

        response = self.client.get(
            reverse("active_plan_intro", args=[self.active_plan.id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Reading Plan Introduction")
        self.assertContains(response, "Overview")
        self.assertContains(response, "How to Read")
        self.assertContains(response, "Reading Guidance")

    def test_regular_enrolled_user_can_view_published_guide_posts(self):
        self.set_language("en")
        PlanEnrollment.objects.create(user=self.user, active_plan=self.active_plan)
        ReadingGuidePost.objects.create(
            active_plan=self.active_plan,
            title="本周提醒",
            title_en="This Week's Focus",
            body="中文内容",
            body_en="Notice the signs in John.",
            is_published=True,
            published_at=timezone.now(),
        )

        self.client.login(username="levin", password="testpass123")

        response = self.client.get(
            reverse("active_plan_guides", args=[self.active_plan.id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Reading Guides")
        self.assertContains(response, "This Week&#x27;s Focus")

    def test_regular_enrolled_user_cannot_view_draft_guide_posts(self):
        self.set_language("en")
        PlanEnrollment.objects.create(user=self.user, active_plan=self.active_plan)
        ReadingGuidePost.objects.create(
            active_plan=self.active_plan,
            title="Draft Guide",
            body="Draft body",
            is_published=False,
        )

        self.client.login(username="levin", password="testpass123")

        response = self.client.get(
            reverse("active_plan_guides", args=[self.active_plan.id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Draft Guide")

    def test_non_enrolled_user_can_view_published_guides_for_active_plan(self):
        self.set_language("en")
        ReadingGuidePost.objects.create(
            active_plan=self.active_plan,
            title="Open Guide",
            body="Visible before joining.",
            is_published=True,
            published_at=timezone.now(),
        )

        self.client.login(username="levin", password="testpass123")

        response = self.client.get(
            reverse("active_plan_guides", args=[self.active_plan.id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Open Guide")

    def test_non_enrolled_regular_user_cannot_view_guides_for_inactive_plan(self):
        self.plan.is_active = False
        self.plan.save()
        ReadingGuidePost.objects.create(
            active_plan=self.active_plan,
            title="Inactive Guide",
            body="Hidden",
            is_published=True,
            published_at=timezone.now(),
        )

        self.set_language("en")
        self.client.login(username="levin", password="testpass123")

        response = self.client.get(
            reverse("active_plan_guides", args=[self.active_plan.id])
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("home"))

    def test_staff_can_view_guides_for_inactive_plan(self):
        self.plan.is_active = False
        self.plan.save()
        ReadingGuidePost.objects.create(
            active_plan=self.active_plan,
            title="Staff Guide",
            body="Visible to staff",
            is_published=True,
            published_at=timezone.now(),
        )

        self.set_language("en")
        self.client.login(username="admin", password="testpass123")

        response = self.client.get(
            reverse("active_plan_guides", args=[self.active_plan.id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Staff Guide")

    def test_user_without_publish_capability_cannot_access_create_guide_page(self):
        self.set_language("en")
        self.client.login(username="levin", password="testpass123")

        response = self.client.get(
            reverse("create_reading_guide_post", args=[self.active_plan.id])
        )

        self.assertEqual(response.status_code, 302)

    def test_user_with_pastor_role_can_access_create_guide_page(self):
        self.set_language("en")
        self.create_guide_publisher()
        self.client.login(username="pastor_user", password="testpass123")

        response = self.client.get(
            reverse("create_reading_guide_post", args=[self.active_plan.id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "New Reading Guide")

    def test_user_with_capability_can_create_published_guide_post(self):
        self.set_language("en")
        self.create_guide_publisher()
        self.client.login(username="pastor_user", password="testpass123")

        response = self.client.post(
            reverse("create_reading_guide_post", args=[self.active_plan.id]),
            {
                "title": "Published Guide",
                "title_en": "Published Guide EN",
                "body": "中文指引",
                "body_en": "English guide",
                "guide_type": ReadingGuidePost.GUIDE_GENERAL,
                "is_published": "on",
            },
        )

        self.assertEqual(response.status_code, 302)
        guide_post = ReadingGuidePost.objects.get(title="Published Guide")
        self.assertTrue(guide_post.is_published)
        self.assertIsNotNone(guide_post.published_at)

    def test_user_with_capability_can_create_draft_guide_post(self):
        self.set_language("en")
        self.create_guide_publisher()
        self.client.login(username="pastor_user", password="testpass123")

        response = self.client.post(
            reverse("create_reading_guide_post", args=[self.active_plan.id]),
            {
                "title": "Draft Guide",
                "body": "Draft body",
                "guide_type": ReadingGuidePost.GUIDE_GENERAL,
            },
        )

        self.assertEqual(response.status_code, 302)
        guide_post = ReadingGuidePost.objects.get(title="Draft Guide")
        self.assertFalse(guide_post.is_published)
        self.assertIsNone(guide_post.published_at)

    def test_draft_guide_visible_to_capability_user_but_not_regular_user(self):
        self.set_language("en")
        self.create_guide_publisher()
        ReadingGuidePost.objects.create(
            active_plan=self.active_plan,
            title="Internal Draft",
            body="Only publishers should see this.",
            is_published=False,
        )

        self.client.login(username="pastor_user", password="testpass123")
        response = self.client.get(
            reverse("active_plan_guides", args=[self.active_plan.id])
        )
        self.assertContains(response, "Internal Draft")
        self.client.logout()

        self.client.login(username="levin", password="testpass123")
        response = self.client.get(
            reverse("active_plan_guides", args=[self.active_plan.id])
        )
        self.assertNotContains(response, "Internal Draft")

    def test_user_with_capability_can_edit_guide_post(self):
        self.set_language("en")
        self.create_guide_publisher()
        guide_post = ReadingGuidePost.objects.create(
            active_plan=self.active_plan,
            title="Original Guide",
            body="Original body",
            is_published=False,
        )

        self.client.login(username="pastor_user", password="testpass123")

        response = self.client.post(
            reverse("edit_reading_guide_post", args=[guide_post.id]),
            {
                "title": "Edited Guide",
                "body": "Edited body",
                "guide_type": ReadingGuidePost.GUIDE_GENERAL,
                "is_published": "on",
            },
        )

        self.assertEqual(response.status_code, 302)
        guide_post.refresh_from_db()
        self.assertEqual(guide_post.title, "Edited Guide")
        self.assertTrue(guide_post.is_published)
        self.assertIsNotNone(guide_post.published_at)

    def test_user_with_capability_can_delete_guide_post(self):
        self.set_language("en")
        self.create_guide_publisher()
        guide_post = ReadingGuidePost.objects.create(
            active_plan=self.active_plan,
            title="Delete Me",
            body="Delete body",
            is_published=True,
            published_at=timezone.now(),
        )

        self.client.login(username="pastor_user", password="testpass123")

        response = self.client.post(
            reverse("delete_reading_guide_post", args=[guide_post.id])
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(ReadingGuidePost.objects.filter(id=guide_post.id).exists())

    def test_reading_guide_post_type_validation(self):
        weekly = ReadingGuidePost(
            active_plan=self.active_plan,
            title="Weekly",
            body="Body",
            guide_type=ReadingGuidePost.GUIDE_WEEKLY,
        )
        daily = ReadingGuidePost(
            active_plan=self.active_plan,
            title="Daily",
            body="Body",
            guide_type=ReadingGuidePost.GUIDE_DAILY,
        )
        general = ReadingGuidePost(
            active_plan=self.active_plan,
            title="General",
            body="Body",
            guide_type=ReadingGuidePost.GUIDE_GENERAL,
            week_number=1,
        )

        with self.assertRaises(ValidationError):
            weekly.full_clean()
        with self.assertRaises(ValidationError):
            daily.full_clean()
        with self.assertRaises(ValidationError):
            general.full_clean()

    def test_chinese_guide_page_contains_chinese_labels(self):
        self.set_language("zh")
        ReadingGuidePost.objects.create(
            active_plan=self.active_plan,
            title="置顶指引",
            body="请留意约翰福音中的记号。",
            is_pinned=True,
            is_published=True,
            published_at=timezone.now(),
        )

        self.client.login(username="levin", password="testpass123")

        response = self.client.get(
            reverse("active_plan_guides", args=[self.active_plan.id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "读经指引")
        self.assertContains(response, "置顶")
        self.assertContains(response, "已发布")

    def test_english_guide_page_contains_english_labels(self):
        self.set_language("en")
        ReadingGuidePost.objects.create(
            active_plan=self.active_plan,
            title="置顶指引",
            title_en="Pinned Guide",
            body="中文内容",
            body_en="English body",
            is_pinned=True,
            is_published=True,
            published_at=timezone.now(),
        )

        self.client.login(username="levin", password="testpass123")

        response = self.client.get(
            reverse("active_plan_guides", args=[self.active_plan.id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Reading Guides")
        self.assertContains(response, "Pinned")
        self.assertContains(response, "Published")

    def test_active_plan_intro_page_links_to_guides(self):
        self.set_language("en")
        self.client.login(username="levin", password="testpass123")

        response = self.client.get(
            reverse("active_plan_intro", args=[self.active_plan.id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("active_plan_guides", args=[self.active_plan.id]))

    def test_enrolled_user_can_view_plan_detail(self):
        PlanEnrollment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
        )

        self.client.login(username="levin", password="testpass123")

        response = self.client.get(
            reverse("active_plan_detail", args=[self.active_plan.id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "May Test Plan")
        self.assertContains(response, "约翰福音 第 1 章")

    def test_enrolled_user_can_check_in_today(self):
        PlanEnrollment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
        )

        self.client.login(username="levin", password="testpass123")

        response = self.client.post(
            reverse("check_in", args=[self.active_plan.id, self.day1.id])
        )

        self.assertEqual(response.status_code, 302)

        self.assertTrue(
            CheckIn.objects.filter(
                user=self.user,
                active_plan=self.active_plan,
                plan_day=self.day1,
            ).exists()
        )

    def test_user_cannot_check_in_same_day_twice(self):
        PlanEnrollment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
        )

        self.client.login(username="levin", password="testpass123")

        url = reverse("check_in", args=[self.active_plan.id, self.day1.id])
        self.client.post(url)
        self.client.post(url)

        count = CheckIn.objects.filter(
            user=self.user,
            active_plan=self.active_plan,
            plan_day=self.day1,
        ).count()

        self.assertEqual(count, 1)

    def test_unenrolled_user_cannot_check_in(self):
        self.client.login(username="levin", password="testpass123")

        response = self.client.post(
            reverse("check_in", args=[self.active_plan.id, self.day1.id])
        )

        self.assertEqual(response.status_code, 302)

        self.assertFalse(
            CheckIn.objects.filter(
                user=self.user,
                active_plan=self.active_plan,
                plan_day=self.day1,
            ).exists()
        )

    def test_user_cannot_check_in_future_day(self):
        PlanEnrollment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
        )

        self.client.login(username="levin", password="testpass123")

        response = self.client.post(
            reverse("check_in", args=[self.active_plan.id, self.future_day.id])
        )

        self.assertEqual(response.status_code, 302)

        self.assertFalse(
            CheckIn.objects.filter(
                user=self.user,
                active_plan=self.active_plan,
                plan_day=self.future_day,
            ).exists()
        )

    def test_checkin_is_scoped_to_active_plan(self):
        another_active_plan = ActivePlan.objects.create(
            plan=self.plan,
            start_date=timezone.localdate(),
            title="Another Run",
        )

        PlanEnrollment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
        )
        PlanEnrollment.objects.create(
            user=self.user,
            active_plan=another_active_plan,
        )

        CheckIn.objects.create(
            user=self.user,
            active_plan=self.active_plan,
            plan_day=self.day1,
        )

        self.assertFalse(
            CheckIn.objects.filter(
                user=self.user,
                active_plan=another_active_plan,
                plan_day=self.day1,
            ).exists()
        )

    def test_comment_owner_can_soft_delete_comment(self):
        comment = ReflectionComment.objects.create(
            user=self.user,
            plan_day=self.day1,
            body="My reflection",
            active_plan=self.active_plan,
            scripture_ref_key="John 1",
            scripture_display_zh="约翰福音 第 1 章",
            scripture_display_en="John 1",
            visibility=ReflectionComment.VISIBILITY_GROUP,
            small_group_at_post=self.group,
        )

        self.client.login(username="levin", password="testpass123")

        response = self.client.post(
            reverse("delete_comment", args=[comment.id])
        )

        self.assertEqual(response.status_code, 302)

        comment.refresh_from_db()
        self.assertTrue(comment.is_deleted)
        self.assertEqual(comment.body, "")

    def test_non_owner_cannot_delete_comment(self):
        comment = ReflectionComment.objects.create(
            user=self.user,
            plan_day=self.day1,
            body="My reflection",
            active_plan=self.active_plan,
            scripture_ref_key="John 1",
            scripture_display_zh="约翰福音 第 1 章",
            scripture_display_en="John 1",
            visibility=ReflectionComment.VISIBILITY_GROUP,
            small_group_at_post=self.group,
        )

        self.client.login(username="other", password="testpass123")

        response = self.client.post(
            reverse("delete_comment", args=[comment.id])
        )

        self.assertEqual(response.status_code, 302)

        comment.refresh_from_db()
        self.assertFalse(comment.is_deleted)
        self.assertEqual(comment.body, "My reflection")

    def test_staff_can_soft_delete_any_comment(self):
        comment = ReflectionComment.objects.create(
            user=self.user,
            plan_day=self.day1,
            body="My reflection",
            active_plan=self.active_plan,
            scripture_ref_key="John 1",
            scripture_display_zh="约翰福音 第 1 章",
            scripture_display_en="John 1",
            visibility=ReflectionComment.VISIBILITY_GROUP,
            small_group_at_post=self.group,
        )

        self.client.login(username="admin", password="testpass123")

        response = self.client.post(
            reverse("delete_comment", args=[comment.id])
        )

        self.assertEqual(response.status_code, 302)

        comment.refresh_from_db()
        self.assertTrue(comment.is_deleted)
        self.assertEqual(comment.body, "")

    def test_group_progress_requires_login(self):
        response = self.client.get(reverse("my_group_progress"))

        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_user_without_group_sees_clear_message(self):
        self.user.profile.small_group = None
        self.user.profile.save()

        self.client.login(username="levin", password="testpass123")

        response = self.client.get(reverse("my_group_progress"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "You are not assigned to a small group yet.")

    def test_group_progress_shows_same_group_members_only(self):
        other_group = SmallGroup.objects.create(name="Other Group")

        self.user.profile.small_group = self.group
        self.user.profile.save()

        self.other_user.profile.small_group = self.group
        self.other_user.profile.save()

        outside_user = User.objects.create_user(
            username="outside",
            email="outside@example.com",
            password="testpass123",
        )
        outside_user.profile.small_group = other_group
        outside_user.profile.save()

        PlanEnrollment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
        )
        PlanEnrollment.objects.create(
            user=self.other_user,
            active_plan=self.active_plan,
        )
        PlanEnrollment.objects.create(
            user=outside_user,
            active_plan=self.active_plan,
        )

        self.client.login(username="levin", password="testpass123")

        response = self.client.get(reverse("my_group_progress"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "levin")
        self.assertContains(response, "other")
        self.assertNotContains(response, "outside")

    def test_group_progress_shows_checked_and_missing_status(self):
        self.user.profile.small_group = self.group
        self.user.profile.save()

        self.other_user.profile.small_group = self.group
        self.other_user.profile.save()

        PlanEnrollment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
        )
        PlanEnrollment.objects.create(
            user=self.other_user,
            active_plan=self.active_plan,
        )

        CheckIn.objects.create(
            user=self.user,
            active_plan=self.active_plan,
            plan_day=self.day1,
        )

        self.client.login(username="levin", password="testpass123")

        response = self.client.get(reverse("my_group_progress"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Checked")
        self.assertContains(response, "Missing")

    def test_group_progress_shows_not_joined_member(self):
        self.user.profile.small_group = self.group
        self.user.profile.save()

        self.other_user.profile.small_group = self.group
        self.other_user.profile.save()

        PlanEnrollment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
        )

        self.client.login(username="levin", password="testpass123")

        response = self.client.get(reverse("my_group_progress"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "levin")
        self.assertContains(response, "other")
        self.assertContains(response, "Not joined")

    def test_group_leader_can_view_assigned_group_progress(self):
        self.set_language("en")
        leader = User.objects.create_user(
            username="group_leader",
            email="leader@example.com",
            password="testpass123",
        )
        assigned_group = SmallGroup.objects.create(name="Assigned Group")
        other_group = SmallGroup.objects.create(name="Outside Group")
        ChurchRoleAssignment.objects.create(
            user=leader,
            role=ChurchRoleAssignment.ROLE_GROUP_LEADER,
            scope_type=ChurchRoleAssignment.SCOPE_SMALL_GROUP,
            small_group=assigned_group,
        )

        self.client.login(username="group_leader", password="testpass123")

        response = self.client.get(reverse("my_group_progress"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Assigned Group")
        self.assertNotContains(response, "Outside Group")

    def test_district_leader_can_select_group_in_assigned_district(self):
        self.set_language("en")
        district = District.objects.create(name="North District")
        group_a = SmallGroup.objects.create(name="North Group A", district=district)
        group_b = SmallGroup.objects.create(name="North Group B", district=district)
        leader = User.objects.create_user(
            username="district_leader",
            email="district@example.com",
            password="testpass123",
        )
        ChurchRoleAssignment.objects.create(
            user=leader,
            role=ChurchRoleAssignment.ROLE_DISTRICT_LEADER,
            scope_type=ChurchRoleAssignment.SCOPE_DISTRICT,
            district=district,
        )

        self.client.login(username="district_leader", password="testpass123")

        response = self.client.get(
            reverse("my_group_progress"),
            {"group": group_b.id},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "North Group A")
        self.assertContains(response, "North Group B")
        self.assertContains(response, f'value="{group_b.id}" selected')

    def test_district_leader_cannot_access_group_outside_district(self):
        self.set_language("en")
        district = District.objects.create(name="East District")
        outside_district = District.objects.create(name="West District")
        inside_group = SmallGroup.objects.create(name="East Group", district=district)
        outside_group = SmallGroup.objects.create(
            name="West Group",
            district=outside_district,
        )
        leader = User.objects.create_user(
            username="limited_leader",
            email="limited@example.com",
            password="testpass123",
        )
        ChurchRoleAssignment.objects.create(
            user=leader,
            role=ChurchRoleAssignment.ROLE_DISTRICT_LEADER,
            scope_type=ChurchRoleAssignment.SCOPE_DISTRICT,
            district=district,
        )

        self.client.login(username="limited_leader", password="testpass123")

        response = self.client.get(
            reverse("my_group_progress"),
            {"group": outside_group.id},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "East Group")
        self.assertNotContains(response, "West Group")
        self.assertEqual(response.context["selected_group"], inside_group)

    def test_staff_can_select_any_group_progress(self):
        self.set_language("en")
        other_group = SmallGroup.objects.create(name="Staff Visible Group")

        self.client.login(username="admin", password="testpass123")

        response = self.client.get(
            reverse("my_group_progress"),
            {"group": other_group.id},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Staff Visible Group")
        self.assertEqual(response.context["selected_group"], other_group)

    def test_home_shows_rest_day_when_today_has_no_plan_day(self):
        PlanEnrollment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
        )

        self.active_plan.start_date = timezone.localdate() - timezone.timedelta(days=5)
        self.active_plan.save()

        self.client.login(username="levin", password="testpass123")

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "休息 / 补读日")
        self.assertContains(response, "今天没有指定读经")


    def test_home_hides_not_started_plan_and_links_to_reading(self):
        self.set_language("en")
        PlanEnrollment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
        )

        self.active_plan.start_date = timezone.localdate() + timezone.timedelta(days=1)
        self.active_plan.save()

        self.client.login(username="levin", password="testpass123")

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Not started")
        self.assertContains(response, "You do not have an active reading plan right now.")
        self.assertContains(response, reverse("my_plans"))


    def test_home_does_not_show_ended_plan_as_primary_card(self):
        self.set_language("en")
        PlanEnrollment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
        )

        self.active_plan.start_date = timezone.localdate() - timezone.timedelta(days=20)
        self.active_plan.save()

        self.client.login(username="levin", password="testpass123")

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Ended")
        self.assertNotContains(response, "May Test Plan")
        self.assertContains(response, "Completed reading plans are available on the Reading page.")

        my_plans_response = self.client.get(reverse("my_plans"))
        self.assertContains(my_plans_response, "May Test Plan")
        self.assertContains(my_plans_response, "Ended")

    def test_plan_detail_shows_rest_days_for_missing_day_numbers(self):
        PlanEnrollment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
        )

        self.client.login(username="levin", password="testpass123")

        response = self.client.get(
            reverse("active_plan_detail", args=[self.active_plan.id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Day 3")
        self.assertContains(response, "休息 / 补读日")
        self.assertContains(response, "这一天没有指定读经")


    def test_plan_detail_progress_uses_reading_days_not_calendar_days(self):
        PlanEnrollment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
        )

        CheckIn.objects.create(
            user=self.user,
            active_plan=self.active_plan,
            plan_day=self.day1,
        )

        self.client.login(username="levin", password="testpass123")

        response = self.client.get(
            reverse("active_plan_detail", args=[self.active_plan.id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "1 / 3 读经日")
        self.assertContains(response, "总日历天数：10")
        self.assertContains(response, "休息 / 补读日：7")

    def test_my_plans_requires_login(self):
        response = self.client.get(reverse("my_plans"))

        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)


    def test_my_plans_shows_joined_plan(self):
        PlanEnrollment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
        )

        self.client.login(username="levin", password="testpass123")

        response = self.client.get(reverse("my_plans"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "May Test Plan")
        self.assertContains(response, "Progress")


    def test_home_uses_lightweight_reading_cta_without_available_plan_grid(self):
        self.set_language("en")
        self.client.login(username="levin", password="testpass123")

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "You do not have an active reading plan right now.")
        self.assertContains(response, "Browse reading plans")
        self.assertContains(response, reverse("my_plans"))
        self.assertNotContains(response, "Available Reading Plans")
        self.assertNotContains(response, "Join this plan")


    def test_my_plans_shows_available_plan_discovery(self):
        self.set_language("en")
        self.client.login(username="levin", password="testpass123")

        response = self.client.get(reverse("my_plans"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Available Reading Plans")
        self.assertContains(response, "May Test Plan")
        self.assertContains(response, "Join this plan")


    def test_user_can_leave_active_plan(self):
        PlanEnrollment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
        )

        self.client.login(username="levin", password="testpass123")

        response = self.client.post(
            reverse("leave_active_plan", args=[self.active_plan.id])
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("my_plans"))

        self.assertFalse(
            PlanEnrollment.objects.filter(
                user=self.user,
                active_plan=self.active_plan,
            ).exists()
        )


    def test_leave_plan_does_not_delete_checkins(self):
        PlanEnrollment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
        )

        CheckIn.objects.create(
            user=self.user,
            active_plan=self.active_plan,
            plan_day=self.day1,
        )

        self.client.login(username="levin", password="testpass123")

        self.client.post(
            reverse("leave_active_plan", args=[self.active_plan.id])
        )

        self.assertTrue(
            CheckIn.objects.filter(
                user=self.user,
                active_plan=self.active_plan,
                plan_day=self.day1,
            ).exists()
        )


    def test_left_plan_no_longer_appears_as_joined_in_my_plans(self):
        enrollment = PlanEnrollment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
        )

        enrollment.delete()

        self.set_language("en")
        self.client.login(username="levin", password="testpass123")

        response = self.client.get(reverse("my_plans"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "You have not joined any reading plan yet.")
        self.assertContains(response, "Available Reading Plans")
        self.assertContains(response, "May Test Plan")
        self.assertNotContains(response, "Progress:")
        self.assertNotContains(response, "Leave Plan")


    def test_user_cannot_leave_other_users_enrollment(self):
        PlanEnrollment.objects.create(
            user=self.other_user,
            active_plan=self.active_plan,
        )

        self.client.login(username="levin", password="testpass123")

        self.client.post(
            reverse("leave_active_plan", args=[self.active_plan.id])
        )

        self.assertTrue(
            PlanEnrollment.objects.filter(
                user=self.other_user,
                active_plan=self.active_plan,
            ).exists()
        )

    def test_parse_reading_text_extracts_chapters_and_verse_ranges(self):
        passages = parse_reading_text(
            "创世记第 1 章，马可福音第 9 章 1-29 节"
        )

        self.assertEqual(len(passages), 2)

        self.assertEqual(passages[0]["display"], "创世记 第 1 章")
        self.assertEqual(passages[0]["search_text"], "Genesis 1")

        self.assertEqual(passages[1]["display"], "马可福音 第 9 章 1-29 节")
        self.assertEqual(passages[1]["search_text"], "Mark 9:1-29")


    def test_home_shows_scripture_reader_links(self):
        self.day1.reading_text = "创世记第 1 章，马可福音第 9 章 1-29 节"
        self.day1.save()

        PlanEnrollment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
        )

        self.client.login(username="levin", password="testpass123")

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "创世记 第 1 章")
        self.assertContains(response, "马可福音 第 9 章 1-29 节")


    def test_passage_reader_requires_enrollment(self):
        self.day1.reading_text = "创世记第 1 章"
        self.day1.save()

        self.client.login(username="levin", password="testpass123")

        response = self.client.get(
            reverse("passage_reader", args=[self.active_plan.id, self.day1.id, 0])
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("home"))


    def test_enrolled_user_can_open_passage_reader(self):
        self.day1.reading_text = "创世记第 1 章"
        self.day1.save()

        PlanEnrollment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
        )

        self.client.login(username="levin", password="testpass123")

        response = self.client.get(
            reverse("passage_reader", args=[self.active_plan.id, self.day1.id, 0])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "创世记 第 1 章")

        # Text reader should show scripture iframe.
        self.assertContains(response, "scripture-frame")

        # Text reader should not show audio iframe.
        self.assertNotContains(response, "audio-frame-compact")
        self.assertNotContains(response, "interface=amp")

        # Text reader should still have reflection and check-in flow.
        self.assertContains(
            response,
            reverse("add_comment", args=[self.active_plan.id, self.day1.id, 0]),
        )
        self.assertContains(
            response,
            reverse("check_in", args=[self.active_plan.id, self.day1.id]),
        )

    def test_chinese_reflection_reader_localizes_form_and_wall_names(self):
        self.set_language("zh")
        self.day1.reading_text = "John 1"
        self.day1.save()

        self.user.profile.small_group = self.group
        self.user.profile.save()
        PlanEnrollment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
        )
        ReflectionComment.objects.create(
            user=self.other_user,
            active_plan=self.active_plan,
            plan_day=self.day1,
            scripture_ref_key="John 1",
            scripture_display_zh="约翰福音 第 1 章",
            scripture_display_en="John 1",
            visibility=ReflectionComment.VISIBILITY_CHURCH,
            body="Visible reflection.",
        )

        self.client.login(username="levin", password="testpass123")

        response = self.client.get(
            reverse("passage_reader", args=[self.active_plan.id, self.day1.id, 0])
        )

        self.assertContains(response, "默想墙")
        self.assertContains(response, "分享你的默想")
        self.assertContains(response, "匿名发表")
        self.assertContains(response, "匿名回复")
        self.assertNotContains(response, "Share your reflection")
        self.assertNotContains(response, "Post anonymously")
        self.assertNotContains(response, "Reply anonymously")
        self.assertNotContains(response, "Visibility")
        self.assertNotContains(response, "Passage " + "Wall")
        self.assertNotContains(response, "经文" + "墙")

    def test_english_reflection_reader_uses_reflection_wall_names(self):
        self.set_language("en")
        self.day1.reading_text = "John 1"
        self.day1.save()

        self.user.profile.small_group = self.group
        self.user.profile.save()
        PlanEnrollment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
        )
        ReflectionComment.objects.create(
            user=self.other_user,
            active_plan=self.active_plan,
            plan_day=self.day1,
            scripture_ref_key="John 1",
            scripture_display_zh="约翰福音 第 1 章",
            scripture_display_en="John 1",
            visibility=ReflectionComment.VISIBILITY_CHURCH,
            body="Visible reflection.",
        )

        self.client.login(username="levin", password="testpass123")

        response = self.client.get(
            reverse("passage_reader", args=[self.active_plan.id, self.day1.id, 0])
        )

        self.assertContains(response, "Reflection Wall")
        self.assertContains(response, "Share your reflection")
        self.assertContains(response, "Post anonymously")
        self.assertContains(response, "Reply anonymously")
        self.assertNotContains(response, "Passage " + "Wall")
        self.assertNotContains(response, "经文" + "墙")


    def test_passage_reader_rejects_invalid_index(self):
        self.day1.reading_text = "创世记第 1 章"
        self.day1.save()

        PlanEnrollment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
        )

        self.client.login(username="levin", password="testpass123")

        response = self.client.get(
            reverse("passage_reader", args=[self.active_plan.id, self.day1.id, 99])
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.url,
            reverse("active_plan_detail", args=[self.active_plan.id]),
        )

    def test_parse_reading_text_extracts_english_chapters(self):
        passages = parse_reading_text("John 1")

        self.assertEqual(len(passages), 1)
        self.assertEqual(passages[0]["display"], "John 1")
        self.assertEqual(passages[0]["search_text"], "John 1")


    def test_parse_reading_text_extracts_english_verse_ranges(self):
        passages = parse_reading_text("John 1:1-18, 1 Corinthians 13")

        self.assertEqual(len(passages), 2)

        self.assertEqual(passages[0]["display"], "John 1:1-18")
        self.assertEqual(passages[0]["search_text"], "John 1:1-18")

        self.assertEqual(passages[1]["display"], "1 Corinthians 13")
        self.assertEqual(passages[1]["search_text"], "1 Corinthians 13")


    def test_home_shows_scripture_reader_link_for_english_reading_text(self):
        self.day1.reading_text = "John 1"
        self.day1.save()

        PlanEnrollment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
        )

        self.client.login(username="levin", password="testpass123")

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "约翰福音 第 1 章")
        self.assertNotContains(response, "No scripture links could be generated")

    def test_parse_reading_text_extracts_chinese_compact_memory_verse(self):
        passages = parse_reading_text("马可福音 6:41")

        self.assertEqual(len(passages), 1)
        self.assertEqual(passages[0]["display"], "马可福音 第 6 章 41 节")
        self.assertEqual(passages[0]["display_zh"], "马可福音 第 6 章 41 节")
        self.assertEqual(passages[0]["display_en"], "Mark 6:41")
        self.assertEqual(passages[0]["search_text"], "Mark 6:41")
        self.assertIn("version=CUVS", passages[0]["text_url_zh"])
        self.assertIn("version=NIV", passages[0]["text_url_en"])


    def test_home_shows_memory_verse_reader_link(self):
        self.day1.reading_text = "John 1"
        self.day1.memory_verse = "马可福音 6:41"
        self.day1.save()

        PlanEnrollment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
        )

        self.client.login(username="levin", password="testpass123")

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "背诵经文")
        self.assertContains(response, "马可福音 第 6 章 41 节")
        self.assertContains(
            response,
            reverse("memory_verse_reader", args=[self.active_plan.id, self.day1.id, 0]),
        )


    def test_enrolled_user_can_open_memory_verse_reader(self):
        self.day1.memory_verse = "马可福音 6:41"
        self.day1.save()

        PlanEnrollment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
        )

        self.client.login(username="levin", password="testpass123")

        response = self.client.get(
            reverse("memory_verse_reader", args=[self.active_plan.id, self.day1.id, 0])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "马可福音 第 6 章 41 节")
        self.assertContains(response, "scripture-frame")

        # Memory verse reader is text-only.
        self.assertNotContains(response, "audio-frame-compact")
        self.assertNotContains(response, "interface=amp")

        # Memory verse reader should not show check-in / reflection flow.
        self.assertNotContains(
            response,
            reverse("check_in", args=[self.active_plan.id, self.day1.id]),
        )


    def test_memory_verse_reader_requires_enrollment(self):
        self.day1.memory_verse = "马可福音 6:41"
        self.day1.save()

        self.client.login(username="levin", password="testpass123")

        response = self.client.get(
            reverse("memory_verse_reader", args=[self.active_plan.id, self.day1.id, 0])
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("home"))

    def test_first_passage_does_not_show_check_in_when_multiple_passages(self):
        self.day1.reading_text = "John 1, John 2"
        self.day1.save()

        PlanEnrollment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
        )

        self.client.login(username="levin", password="testpass123")

        response = self.client.get(
            reverse("passage_reader", args=[self.active_plan.id, self.day1.id, 0])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "继续下一段经文")
        self.assertNotContains(response, "我已完成今日读经")


    def test_last_passage_shows_reflection_and_check_in(self):
        self.day1.reading_text = "John 1, John 2"
        self.day1.save()

        PlanEnrollment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
        )

        self.client.login(username="levin", password="testpass123")

        response = self.client.get(
            reverse("passage_reader", args=[self.active_plan.id, self.day1.id, 1])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "默想 / 评论")
        self.assertContains(response, "发表默想")
        self.assertContains(response, "现有默想")
        self.assertContains(response, "完成今日读经")
        self.assertContains(response, "我已完成今日读经")


    def test_check_in_from_passage_reader_redirects_back_to_reader(self):
        self.day1.reading_text = "John 1"
        self.day1.save()

        PlanEnrollment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
        )

        self.client.login(username="levin", password="testpass123")

        next_url = reverse(
            "passage_reader",
            args=[self.active_plan.id, self.day1.id, 0],
        )

        response = self.client.post(
            reverse("check_in", args=[self.active_plan.id, self.day1.id]),
            {"next": next_url},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, next_url)

        self.assertTrue(
            CheckIn.objects.filter(
                user=self.user,
                active_plan=self.active_plan,
                plan_day=self.day1,
            ).exists()
        )


    def test_comment_from_passage_reader_redirects_back_to_reader(self):
        self.day1.reading_text = "John 1"
        self.day1.save()

        self.user.profile.small_group = self.group
        self.user.profile.save()

        PlanEnrollment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
        )

        self.client.login(username="levin", password="testpass123")

        next_url = reverse(
            "passage_reader",
            args=[self.active_plan.id, self.day1.id, 0],
        )

        response = self.client.post(
            reverse("add_comment", args=[self.active_plan.id, self.day1.id, 0]),
            {
                "body": "This is my reflection.",
                "visibility": ReflectionComment.VISIBILITY_GROUP,
                "is_anonymous": "",
                "next": next_url,
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, next_url)

        self.assertTrue(
            ReflectionComment.objects.filter(
                user=self.user,
                active_plan=self.active_plan,
                plan_day=self.day1,
                scripture_ref_key="John 1",
                visibility=ReflectionComment.VISIBILITY_GROUP,
                body="This is my reflection.",
            ).exists()
        )

    def test_passage_reader_defaults_to_chinese_tab(self):
        self.day1.reading_text = "John 1"
        self.day1.save()

        PlanEnrollment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
        )

        self.client.login(username="levin", password="testpass123")

        response = self.client.get(
            reverse("passage_reader", args=[self.active_plan.id, self.day1.id, 0])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "中文")
        self.assertContains(response, "English")
        self.assertContains(response, "约翰福音 第 1 章")
        self.assertContains(response, "version=CUVS")
        self.assertNotContains(response, "version=NIV")

    def test_passage_reader_can_switch_to_english_tab(self):
        self.day1.reading_text = "John 1"
        self.day1.save()

        PlanEnrollment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
        )

        self.client.login(username="levin", password="testpass123")

        response = self.client.get(
            reverse("passage_reader", args=[self.active_plan.id, self.day1.id, 0]) + "?lang=en"
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "中文")
        self.assertContains(response, "English")
        self.assertContains(response, "John 1")
        self.assertContains(response, "version=NIV")
        self.assertNotContains(response, "version=CUVS")

    def test_plan_detail_hides_raw_reading_text_when_passage_links_exist(self):
        self.day1.reading_text = "John 1"
        self.day1.save()

        PlanEnrollment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
        )

        self.client.login(username="levin", password="testpass123")

        response = self.client.get(
            reverse("active_plan_detail", args=[self.active_plan.id])
        )

        self.assertEqual(response.status_code, 200)

        # There should be a generated passage button/link.
        self.assertContains(response, "约翰福音 第 1 章")

        # But the raw-text failure message should not appear.
        self.assertNotContains(response, "No scripture links could be generated")

    def test_memory_verse_reader_single_passage_does_not_reverse_none_next_index(self):
        self.day1.memory_verse = "马可福音 6:41"
        self.day1.save()

        PlanEnrollment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
        )

        self.client.login(username="levin", password="testpass123")

        response = self.client.get(
            reverse("memory_verse_reader", args=[self.active_plan.id, self.day1.id, 0])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "背诵经文")
        self.assertContains(response, "返回计划")
        self.assertNotContains(response, "继续下一段经文")
        self.assertNotContains(response, "我已完成今日读经")

    def test_scripture_reader_last_passage_still_shows_check_in(self):
        self.day1.reading_text = "John 1"
        self.day1.save()

        PlanEnrollment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
        )

        self.client.login(username="levin", password="testpass123")

        response = self.client.get(
            reverse("passage_reader", args=[self.active_plan.id, self.day1.id, 0])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "完成今日读经")
        self.assertContains(response, "我已完成今日读经")

    def test_home_dashboard_shows_start_reading_button(self):
        self.day1.reading_text = "John 1"
        self.day1.save()

        PlanEnrollment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
        )

        self.client.login(username="levin", password="testpass123")

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "今日经文")
        self.assertContains(response, "开始今日读经")
        self.assertContains(response, "约翰福音 第 1 章")

    def test_home_dashboard_does_not_show_reflection_form(self):
        self.day1.reading_text = "John 1"
        self.day1.save()

        PlanEnrollment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
        )

        self.client.login(username="levin", password="testpass123")

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "发表默想")

    def test_home_shows_pending_serving_summary_for_current_user(self):
        team = MinistryTeam.objects.create(name="Lighting Team", name_en="Lighting Team")
        membership = TeamMembership.objects.create(team=team, user=self.user)
        event = ServiceEvent.objects.create(
            title="主日崇拜",
            title_en="Sunday Service",
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
            start_datetime=timezone.now() + timezone.timedelta(days=7),
            scope_type=ServiceEvent.SCOPE_GLOBAL,
            status=ServiceEvent.STATUS_PUBLISHED,
        )
        assignment = TeamAssignment.objects.create(
            service_event=event,
            ministry_team=team,
            status=TeamAssignment.STATUS_SCHEDULED,
        )
        TeamAssignmentMember.objects.create(assignment=assignment, membership=membership)
        PlanEnrollment.objects.create(user=self.user, active_plan=self.active_plan)
        self.set_language("en")
        self.client.login(username="levin", password="testpass123")

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "My Serving")
        self.assertContains(response, "You have 1 serving assignment waiting for confirmation.")
        self.assertContains(response, "Pending confirmation")
        self.assertContains(response, "Sunday Service")
        self.assertContains(response, "Lighting Team")
        self.assertContains(response, reverse("my_serving"))
        self.assertContains(response, "Today&#x27;s Reading")

    def test_staff_can_access_reading_plan_admin_list(self):
        self.client.login(username="admin", password="testpass123")

        response = self.client.get(reverse("staff_reading_plan_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Reading Plan Admin")
        self.assertContains(response, self.plan.name)


    def test_non_staff_cannot_access_reading_plan_admin_list(self):
        self.client.login(username="levin", password="testpass123")

        response = self.client.get(reverse("staff_reading_plan_list"))

        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response.url)


    def test_staff_can_update_reading_plan_header_without_days_inline(self):
        self.client.login(username="admin", password="testpass123")

        response = self.client.post(
            reverse("staff_reading_plan_header", args=[self.plan.id]),
            {
                "name": self.plan.name,
                "name_en": "English Test Plan",
                "description": "中文说明",
                "description_en": "English description",
                "introduction": "中文计划简介",
                "introduction_en": "English introduction",
                "reading_guidance": "中文如何读",
                "reading_guidance_en": "English reading guidance",
                "pastoral_note": "中文读经指引",
                "pastoral_note_en": "English pastoral note",
                "is_active": "on",
            },
        )

        self.assertEqual(response.status_code, 302)

        self.plan.refresh_from_db()

        self.assertEqual(self.plan.name_en, "English Test Plan")
        self.assertEqual(self.plan.description_en, "English description")
        self.assertEqual(self.plan.introduction, "中文计划简介")
        self.assertEqual(self.plan.introduction_en, "English introduction")
        self.assertEqual(self.plan.reading_guidance, "中文如何读")
        self.assertEqual(self.plan.reading_guidance_en, "English reading guidance")
        self.assertEqual(self.plan.pastoral_note, "中文读经指引")
        self.assertEqual(self.plan.pastoral_note_en, "English pastoral note")
        self.assertTrue(self.plan.is_active)


    def test_staff_can_update_single_reading_plan_day_line(self):
        self.client.login(username="admin", password="testpass123")

        response = self.client.post(
            reverse("staff_reading_plan_days", args=[self.plan.id]),
            {
                "action": "save_day",
                "day_id": self.day1.id,
                "day_number": "1",
                "reading_text": "Updated John 1",
                "memory_verse": "John 1:1",
            },
        )

        self.assertEqual(response.status_code, 302)

        self.day1.refresh_from_db()
        self.day2.refresh_from_db()

        self.assertEqual(self.day1.reading_text, "Updated John 1")
        self.assertEqual(self.day2.reading_text, "John 2")


    def test_staff_can_add_reading_plan_day_line(self):
        self.client.login(username="admin", password="testpass123")

        response = self.client.post(
            reverse("staff_reading_plan_days", args=[self.plan.id]),
            {
                "action": "add_day",
                "day_number": "11",
                "reading_text": "John 11",
                "memory_verse": "John 11:25",
            },
        )

        self.assertEqual(response.status_code, 302)

        self.assertTrue(
            ReadingPlanDay.objects.filter(
                plan=self.plan,
                day_number=11,
                reading_text="John 11",
                memory_verse="John 11:25",
            ).exists()
        )

    def test_comment_is_saved_with_passage_visibility_and_group_scope(self):
        self.day1.reading_text = "John 1"
        self.day1.save()

        self.user.profile.small_group = self.group
        self.user.profile.save()

        PlanEnrollment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
        )

        self.client.login(username="levin", password="testpass123")

        next_url = reverse(
            "passage_reader",
            args=[self.active_plan.id, self.day1.id, 0],
        )

        response = self.client.post(
            reverse("add_comment", args=[self.active_plan.id, self.day1.id, 0]),
            {
                "body": "My group reflection.",
                "visibility": ReflectionComment.VISIBILITY_GROUP,
                "is_anonymous": "",
                "next": next_url,
            },
        )

        self.assertEqual(response.status_code, 302)

        comment = ReflectionComment.objects.get(body="My group reflection.")

        self.assertEqual(comment.active_plan, self.active_plan)
        self.assertEqual(comment.plan_day, self.day1)
        self.assertEqual(comment.scripture_ref_key, "John 1")
        self.assertEqual(comment.visibility, ReflectionComment.VISIBILITY_GROUP)
        self.assertEqual(comment.small_group_at_post, self.group)


    def test_private_reflection_is_not_visible_to_other_user(self):
        self.day1.reading_text = "John 1"
        self.day1.save()

        PlanEnrollment.objects.create(user=self.user, active_plan=self.active_plan)
        PlanEnrollment.objects.create(user=self.other_user, active_plan=self.active_plan)

        ReflectionComment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
            plan_day=self.day1,
            scripture_ref_key="John 1",
            scripture_display_zh="约翰福音 第 1 章",
            scripture_display_en="John 1",
            visibility=ReflectionComment.VISIBILITY_PRIVATE,
            body="Private reflection.",
        )

        self.client.login(username="other", password="testpass123")

        response = self.client.get(
            reverse("passage_reader", args=[self.active_plan.id, self.day1.id, 0])
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Private reflection.")


    def test_group_reflection_is_visible_to_same_group_member(self):
        self.day1.reading_text = "John 1"
        self.day1.save()

        self.user.profile.small_group = self.group
        self.user.profile.save()

        self.other_user.profile.small_group = self.group
        self.other_user.profile.save()

        PlanEnrollment.objects.create(user=self.user, active_plan=self.active_plan)
        PlanEnrollment.objects.create(user=self.other_user, active_plan=self.active_plan)

        ReflectionComment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
            plan_day=self.day1,
            scripture_ref_key="John 1",
            scripture_display_zh="约翰福音 第 1 章",
            scripture_display_en="John 1",
            visibility=ReflectionComment.VISIBILITY_GROUP,
            small_group_at_post=self.group,
            body="Group reflection.",
        )

        self.client.login(username="other", password="testpass123")

        response = self.client.get(
            reverse("passage_reader", args=[self.active_plan.id, self.day1.id, 0])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Group reflection.")


    def test_group_reflection_is_not_visible_to_different_group_member(self):
        other_group = SmallGroup.objects.create(name="Other Group")

        self.day1.reading_text = "John 1"
        self.day1.save()

        self.user.profile.small_group = self.group
        self.user.profile.save()

        self.other_user.profile.small_group = other_group
        self.other_user.profile.save()

        PlanEnrollment.objects.create(user=self.user, active_plan=self.active_plan)
        PlanEnrollment.objects.create(user=self.other_user, active_plan=self.active_plan)

        ReflectionComment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
            plan_day=self.day1,
            scripture_ref_key="John 1",
            scripture_display_zh="约翰福音 第 1 章",
            scripture_display_en="John 1",
            visibility=ReflectionComment.VISIBILITY_GROUP,
            small_group_at_post=self.group,
            body="Hidden group reflection.",
        )

        self.client.login(username="other", password="testpass123")

        response = self.client.get(
            reverse("passage_reader", args=[self.active_plan.id, self.day1.id, 0])
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Hidden group reflection.")


    def test_church_reflection_is_visible_to_other_enrolled_user(self):
        self.day1.reading_text = "John 1"
        self.day1.save()

        PlanEnrollment.objects.create(user=self.user, active_plan=self.active_plan)
        PlanEnrollment.objects.create(user=self.other_user, active_plan=self.active_plan)

        ReflectionComment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
            plan_day=self.day1,
            scripture_ref_key="John 1",
            scripture_display_zh="约翰福音 第 1 章",
            scripture_display_en="John 1",
            visibility=ReflectionComment.VISIBILITY_CHURCH,
            body="Church-wide reflection.",
        )

        self.client.login(username="other", password="testpass123")

        response = self.client.get(
            reverse("passage_reader", args=[self.active_plan.id, self.day1.id, 0])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Church-wide reflection.")


    def test_anonymous_reflection_hides_author_from_regular_user(self):
        self.day1.reading_text = "John 1"
        self.day1.save()

        PlanEnrollment.objects.create(user=self.user, active_plan=self.active_plan)
        PlanEnrollment.objects.create(user=self.other_user, active_plan=self.active_plan)

        ReflectionComment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
            plan_day=self.day1,
            scripture_ref_key="John 1",
            scripture_display_zh="约翰福音 第 1 章",
            scripture_display_en="John 1",
            visibility=ReflectionComment.VISIBILITY_CHURCH,
            is_anonymous=True,
            body="Anonymous reflection.",
        )

        self.client.login(username="other", password="testpass123")

        response = self.client.get(
            reverse("passage_reader", args=[self.active_plan.id, self.day1.id, 0])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Anonymous reflection.")
        self.assertContains(response, "Anonymous")
        self.assertNotContains(response, "levin")


    def test_staff_can_see_anonymous_author(self):
        self.day1.reading_text = "John 1"
        self.day1.save()

        PlanEnrollment.objects.create(user=self.admin, active_plan=self.active_plan)

        ReflectionComment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
            plan_day=self.day1,
            scripture_ref_key="John 1",
            scripture_display_zh="约翰福音 第 1 章",
            scripture_display_en="John 1",
            visibility=ReflectionComment.VISIBILITY_CHURCH,
            is_anonymous=True,
            body="Anonymous but staff visible.",
        )

        self.client.login(username="admin", password="testpass123")

        response = self.client.get(
            reverse("passage_reader", args=[self.active_plan.id, self.day1.id, 0])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Anonymous (levin)")


    def test_passage_wall_shows_my_past_reflections(self):
        ReflectionComment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
            plan_day=self.day1,
            scripture_ref_key="John 1",
            scripture_display_zh="约翰福音 第 1 章",
            scripture_display_en="John 1",
            visibility=ReflectionComment.VISIBILITY_PRIVATE,
            body="My old reflection.",
        )

        self.client.login(username="levin", password="testpass123")

        response = self.client.get(
            reverse("passage_wall"),
            {
                "ref": "John 1",
                "tab": "my",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "My old reflection.")


    def test_passage_wall_church_tab_shows_church_reflections(self):
        ReflectionComment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
            plan_day=self.day1,
            scripture_ref_key="John 1",
            scripture_display_zh="约翰福音 第 1 章",
            scripture_display_en="John 1",
            visibility=ReflectionComment.VISIBILITY_CHURCH,
            body="Wall reflection.",
        )

        self.client.login(username="other", password="testpass123")

        response = self.client.get(
            reverse("passage_wall"),
            {
                "ref": "John 1",
                "tab": "church",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Wall reflection.")

    def test_audio_reader_shows_audio_and_completion_section(self):
        self.day1.reading_text = "John 1"
        self.day1.save()

        PlanEnrollment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
        )

        self.client.login(username="levin", password="testpass123")

        response = self.client.get(
            reverse("audio_reader", args=[self.active_plan.id, self.day1.id, 0])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "audio-frame-compact")
        self.assertContains(response, 'allow="autoplay"')
        self.assertContains(response, "interface=amp")
        self.assertContains(response, "audio-frame-compact")
        self.assertContains(response, 'allow="autoplay"')
        self.assertContains(response, "interface=amp")

        self.assertContains(
            response,
            reverse("add_comment", args=[self.active_plan.id, self.day1.id, 0]),
        )

        self.assertContains(
            response,
            reverse("check_in", args=[self.active_plan.id, self.day1.id]),
        )


    def test_audio_reader_does_not_show_scripture_iframe(self):
        self.day1.reading_text = "John 1"
        self.day1.save()

        PlanEnrollment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
        )

        self.client.login(username="levin", password="testpass123")

        response = self.client.get(
            reverse("audio_reader", args=[self.active_plan.id, self.day1.id, 0])
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "scripture-frame")
        self.assertNotContains(response, "open scripture directly")


    def test_text_reader_does_not_show_audio_iframe(self):
        self.day1.reading_text = "John 1"
        self.day1.save()

        PlanEnrollment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
        )

        self.client.login(username="levin", password="testpass123")

        response = self.client.get(
            reverse("passage_reader", args=[self.active_plan.id, self.day1.id, 0])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "scripture-frame")
        self.assertNotContains(response, "audio-frame-compact")


    def test_check_in_from_audio_reader_redirects_back_to_audio_reader(self):
        self.day1.reading_text = "John 1"
        self.day1.save()

        PlanEnrollment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
        )

        self.client.login(username="levin", password="testpass123")

        next_url = reverse(
            "audio_reader",
            args=[self.active_plan.id, self.day1.id, 0],
        )

        response = self.client.post(
            reverse("check_in", args=[self.active_plan.id, self.day1.id]),
            {"next": next_url},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, next_url)

        self.assertTrue(
            CheckIn.objects.filter(
                user=self.user,
                active_plan=self.active_plan,
                plan_day=self.day1,
            ).exists()
        )


    def test_comment_from_audio_reader_redirects_back_to_audio_reader(self):
        self.day1.reading_text = "John 1"
        self.day1.save()

        self.user.profile.small_group = self.group
        self.user.profile.save()

        PlanEnrollment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
        )

        self.client.login(username="levin", password="testpass123")

        next_url = reverse(
            "audio_reader",
            args=[self.active_plan.id, self.day1.id, 0],
        )

        response = self.client.post(
            reverse("add_comment", args=[self.active_plan.id, self.day1.id, 0]),
            {
                "body": "Audio reflection.",
                "visibility": ReflectionComment.VISIBILITY_GROUP,
                "is_anonymous": "",
                "next": next_url,
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, next_url)

        self.assertTrue(
            ReflectionComment.objects.filter(
                user=self.user,
                active_plan=self.active_plan,
                plan_day=self.day1,
                scripture_ref_key="John 1",
                body="Audio reflection.",
            ).exists()
        )

    def test_user_can_edit_own_reflection_body_visibility_and_anonymous(self):
        self.user.profile.small_group = self.group
        self.user.profile.save()

        comment = ReflectionComment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
            plan_day=self.day1,
            scripture_ref_key="John 1",
            scripture_display_zh="约翰福音 第 1 章",
            scripture_display_en="John 1",
            visibility=ReflectionComment.VISIBILITY_GROUP,
            small_group_at_post=self.group,
            body="Old reflection.",
        )

        self.client.login(username="levin", password="testpass123")

        response = self.client.post(
            reverse("edit_comment", args=[comment.id]),
            {
                "body": "Updated reflection.",
                "visibility": ReflectionComment.VISIBILITY_CHURCH,
                "is_anonymous": "on",
            },
        )

        self.assertEqual(response.status_code, 302)

        comment.refresh_from_db()

        self.assertEqual(comment.body, "Updated reflection.")
        self.assertEqual(comment.visibility, ReflectionComment.VISIBILITY_CHURCH)
        self.assertTrue(comment.is_anonymous)


    def test_user_cannot_edit_other_users_reflection(self):
        comment = ReflectionComment.objects.create(
            user=self.other_user,
            active_plan=self.active_plan,
            plan_day=self.day1,
            scripture_ref_key="John 1",
            scripture_display_zh="约翰福音 第 1 章",
            scripture_display_en="John 1",
            visibility=ReflectionComment.VISIBILITY_CHURCH,
            body="Other user's reflection.",
        )

        self.client.login(username="levin", password="testpass123")

        response = self.client.post(
            reverse("edit_comment", args=[comment.id]),
            {
                "body": "Hacked.",
                "visibility": ReflectionComment.VISIBILITY_CHURCH,
                "is_anonymous": "",
            },
        )

        self.assertEqual(response.status_code, 302)

        comment.refresh_from_db()

        self.assertEqual(comment.body, "Other user's reflection.")


    def test_user_cannot_edit_deleted_reflection(self):
        comment = ReflectionComment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
            plan_day=self.day1,
            scripture_ref_key="John 1",
            scripture_display_zh="约翰福音 第 1 章",
            scripture_display_en="John 1",
            visibility=ReflectionComment.VISIBILITY_PRIVATE,
            body="Deleted reflection.",
            is_deleted=True,
        )

        self.client.login(username="levin", password="testpass123")

        response = self.client.post(
            reverse("edit_comment", args=[comment.id]),
            {
                "body": "Updated deleted reflection.",
                "visibility": ReflectionComment.VISIBILITY_PRIVATE,
                "is_anonymous": "",
            },
        )

        self.assertEqual(response.status_code, 302)

        comment.refresh_from_db()

        self.assertEqual(comment.body, "Deleted reflection.")
        self.assertTrue(comment.is_deleted)


    def test_reply_edit_does_not_change_parent_visibility(self):
        parent = ReflectionComment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
            plan_day=self.day1,
            scripture_ref_key="John 1",
            scripture_display_zh="约翰福音 第 1 章",
            scripture_display_en="John 1",
            visibility=ReflectionComment.VISIBILITY_GROUP,
            small_group_at_post=self.group,
            body="Parent reflection.",
        )

        reply = ReflectionComment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
            plan_day=self.day1,
            parent=parent,
            scripture_ref_key="John 1",
            scripture_display_zh="约翰福音 第 1 章",
            scripture_display_en="John 1",
            visibility=ReflectionComment.VISIBILITY_GROUP,
            small_group_at_post=self.group,
            body="Old reply.",
        )

        self.client.login(username="levin", password="testpass123")

        response = self.client.post(
            reverse("edit_comment", args=[reply.id]),
            {
                "body": "Updated reply.",
                "visibility": ReflectionComment.VISIBILITY_CHURCH,
                "is_anonymous": "on",
            },
        )

        self.assertEqual(response.status_code, 302)

        reply.refresh_from_db()

        self.assertEqual(reply.body, "Updated reply.")
        self.assertEqual(reply.visibility, ReflectionComment.VISIBILITY_GROUP)
        self.assertTrue(reply.is_anonymous)

    def test_reader_shows_new_comment_form_and_reply_form(self):
        self.day1.reading_text = "John 1"
        self.day1.save()

        PlanEnrollment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
        )

        ReflectionComment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
            plan_day=self.day1,
            scripture_ref_key="John 1",
            scripture_display_zh="约翰福音 第 1 章",
            scripture_display_en="John 1",
            visibility=ReflectionComment.VISIBILITY_PRIVATE,
            body="Existing reflection.",
        )

        self.client.login(username="levin", password="testpass123")

        response = self.client.get(
            reverse("passage_reader", args=[self.active_plan.id, self.day1.id, 0])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "默想 / 评论")
        self.assertContains(response, "发表默想")
        self.assertContains(response, "现有默想")
        self.assertContains(response, "Existing reflection.")
        self.assertContains(response, "回复")


    def test_user_can_reply_to_own_comment(self):
        self.day1.reading_text = "John 1"
        self.day1.save()

        PlanEnrollment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
        )

        parent = ReflectionComment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
            plan_day=self.day1,
            scripture_ref_key="John 1",
            scripture_display_zh="约翰福音 第 1 章",
            scripture_display_en="John 1",
            visibility=ReflectionComment.VISIBILITY_PRIVATE,
            body="My own reflection.",
        )

        self.client.login(username="levin", password="testpass123")

        response = self.client.post(
            reverse("add_reply", args=[parent.id]),
            {
                "body": "Replying to myself.",
                "is_anonymous": "",
                "next": reverse("passage_reader", args=[self.active_plan.id, self.day1.id, 0]),
            },
        )

        self.assertEqual(response.status_code, 302)

        self.assertTrue(
            ReflectionComment.objects.filter(
                parent=parent,
                user=self.user,
                body="Replying to myself.",
            ).exists()
        )


    def test_user_can_reply_to_other_visible_comment(self):
        self.day1.reading_text = "John 1"
        self.day1.save()

        self.user.profile.small_group = self.group
        self.user.profile.save()

        self.other_user.profile.small_group = self.group
        self.other_user.profile.save()

        PlanEnrollment.objects.create(user=self.user, active_plan=self.active_plan)
        PlanEnrollment.objects.create(user=self.other_user, active_plan=self.active_plan)

        parent = ReflectionComment.objects.create(
            user=self.other_user,
            active_plan=self.active_plan,
            plan_day=self.day1,
            scripture_ref_key="John 1",
            scripture_display_zh="约翰福音 第 1 章",
            scripture_display_en="John 1",
            visibility=ReflectionComment.VISIBILITY_GROUP,
            small_group_at_post=self.group,
            body="Other user's reflection.",
        )

        self.client.login(username="levin", password="testpass123")

        response = self.client.post(
            reverse("add_reply", args=[parent.id]),
            {
                "body": "Replying to another user.",
                "is_anonymous": "",
                "next": reverse("passage_reader", args=[self.active_plan.id, self.day1.id, 0]),
            },
        )

        self.assertEqual(response.status_code, 302)

        self.assertTrue(
            ReflectionComment.objects.filter(
                parent=parent,
                user=self.user,
                body="Replying to another user.",
            ).exists()
        )


    def test_reader_shows_replies_under_parent_comment(self):
        self.day1.reading_text = "John 1"
        self.day1.save()

        PlanEnrollment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
        )

        parent = ReflectionComment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
            plan_day=self.day1,
            scripture_ref_key="John 1",
            scripture_display_zh="约翰福音 第 1 章",
            scripture_display_en="John 1",
            visibility=ReflectionComment.VISIBILITY_PRIVATE,
            body="Parent reflection.",
        )

        ReflectionComment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
            plan_day=self.day1,
            parent=parent,
            scripture_ref_key="John 1",
            scripture_display_zh="约翰福音 第 1 章",
            scripture_display_en="John 1",
            visibility=ReflectionComment.VISIBILITY_PRIVATE,
            body="Child reply.",
        )

        self.client.login(username="levin", password="testpass123")

        response = self.client.get(
            reverse("passage_reader", args=[self.active_plan.id, self.day1.id, 0])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Parent reflection.")
        self.assertContains(response, "Child reply.")
