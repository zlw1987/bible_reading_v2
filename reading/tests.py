import os
import tempfile

from django.core.management import call_command
from django.core.management.base import CommandError
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from django.contrib.auth.models import User

from accounts.models import SmallGroup
from comments.models import ReflectionComment
from reading.bible_sources import parse_reading_text
from reading.models import (
    ActivePlan,
    CheckIn,
    PlanEnrollment,
    ReadingPlan,
    ReadingPlanDay,
)

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
        self.assertContains(response, "John 1")

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
        self.assertContains(response, "Rest / Catch-up Day")
        self.assertContains(response, "There is no assigned reading today")


    def test_home_shows_not_started_plan(self):
        PlanEnrollment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
        )

        self.active_plan.start_date = timezone.localdate() + timezone.timedelta(days=1)
        self.active_plan.save()

        self.client.login(username="levin", password="testpass123")

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "This reading plan has not started yet.")


    def test_home_shows_ended_plan(self):
        PlanEnrollment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
        )

        self.active_plan.start_date = timezone.localdate() - timezone.timedelta(days=20)
        self.active_plan.save()

        self.client.login(username="levin", password="testpass123")

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "This reading plan has ended.")

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
        self.assertContains(response, "Rest / Catch-up Day")
        self.assertContains(response, "No assigned reading for this day")


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
        self.assertContains(response, "1 / 3 reading days checked")
        self.assertContains(response, "Calendar length: 10 days")
        self.assertContains(response, "Rest / catch-up days: 7")

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


    def test_left_plan_no_longer_appears_in_my_plans(self):
        enrollment = PlanEnrollment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
        )

        enrollment.delete()

        self.client.login(username="levin", password="testpass123")

        response = self.client.get(reverse("my_plans"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "You have not joined any reading plan yet.")
        self.assertNotContains(response, "May Test Plan")


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
        self.assertContains(response, "biblegateway.com")
        self.assertContains(response, "Open scripture")
        self.assertContains(response, "Open audio")


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
        self.assertContains(response, "John 1")
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
        self.assertContains(response, "Memory Verse")
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
        self.assertContains(response, "Memory Verse")
        self.assertContains(response, "马可福音 第 6 章 41 节")
        self.assertContains(response, "Mark 6:41")
        self.assertContains(response, "Open Chinese scripture")
        self.assertContains(response, "Open English scripture")


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
        self.assertContains(response, "Continue to Next Passage")
        self.assertNotContains(response, "I finished today")


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
        self.assertContains(response, "Reflection")
        self.assertContains(response, "Finish Today")
        self.assertContains(response, "I finished today")


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
            reverse("add_comment", args=[self.day1.id]),
            {
                "body": "This is my reflection.",
                "next": next_url,
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, next_url)

        self.assertTrue(
            ReflectionComment.objects.filter(
                user=self.user,
                plan_day=self.day1,
                body="This is my reflection.",
            ).exists()
        )