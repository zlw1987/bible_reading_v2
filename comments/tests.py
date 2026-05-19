from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from accounts.models import SmallGroup
from comments.models import ReflectionComment, ReflectionReport
from reading.models import ActivePlan, PlanEnrollment, ReadingPlan, ReadingPlanDay


class ReflectionReportModerationTests(TestCase):
    def setUp(self):
        self.group = SmallGroup.objects.create(name="Rainbow 4")

        self.user = User.objects.create_user(
            username="levin",
            password="UserPass123!",
        )
        self.user.profile.small_group = self.group
        self.user.profile.save()

        self.other_user = User.objects.create_user(
            username="other",
            password="OtherPass123!",
        )
        self.other_user.profile.small_group = self.group
        self.other_user.profile.save()

        self.staff = User.objects.create_user(
            username="staff",
            password="StaffPass123!",
            is_staff=True,
        )

        self.plan = ReadingPlan.objects.create(
            name="Test Plan",
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
            start_date="2026-05-18",
            title="Test Active Plan",
        )

        PlanEnrollment.objects.create(user=self.user, active_plan=self.active_plan)
        PlanEnrollment.objects.create(user=self.other_user, active_plan=self.active_plan)

        self.comment = ReflectionComment.objects.create(
            user=self.user,
            active_plan=self.active_plan,
            plan_day=self.day1,
            scripture_ref_key="John 1",
            scripture_display_zh="约翰福音 第 1 章",
            scripture_display_en="John 1",
            visibility=ReflectionComment.VISIBILITY_CHURCH,
            body="Reportable reflection.",
        )

    def test_user_can_report_visible_reflection(self):
        self.client.login(username="other", password="OtherPass123!")

        response = self.client.post(
            reverse("report_comment", args=[self.comment.id]),
            {
                "reason": "This seems inappropriate.",
            },
        )

        self.assertEqual(response.status_code, 302)

        self.assertTrue(
            ReflectionReport.objects.filter(
                comment=self.comment,
                reporter=self.other_user,
                reason="This seems inappropriate.",
            ).exists()
        )

    def test_user_cannot_report_own_reflection(self):
        self.client.login(username="levin", password="UserPass123!")

        response = self.client.post(
            reverse("report_comment", args=[self.comment.id]),
            {
                "reason": "Reporting myself.",
            },
        )

        self.assertEqual(response.status_code, 302)

        self.assertFalse(
            ReflectionReport.objects.filter(
                comment=self.comment,
                reporter=self.user,
            ).exists()
        )

    def test_duplicate_report_is_not_created(self):
        ReflectionReport.objects.create(
            comment=self.comment,
            reporter=self.other_user,
            reason="First report.",
        )

        self.client.login(username="other", password="OtherPass123!")

        self.client.post(
            reverse("report_comment", args=[self.comment.id]),
            {
                "reason": "Second report.",
            },
        )

        count = ReflectionReport.objects.filter(
            comment=self.comment,
            reporter=self.other_user,
        ).count()

        self.assertEqual(count, 1)

    def test_staff_can_view_report_page(self):
        ReflectionReport.objects.create(
            comment=self.comment,
            reporter=self.other_user,
            reason="Needs review.",
        )

        self.client.login(username="staff", password="StaffPass123!")

        response = self.client.get(reverse("staff_reflection_reports"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Reflection Reports")
        self.assertContains(response, "Needs review.")
        self.assertContains(response, "Reportable reflection.")

    def test_non_staff_cannot_view_report_page(self):
        self.client.login(username="levin", password="UserPass123!")

        response = self.client.get(reverse("staff_reflection_reports"))

        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response.url)

    def test_staff_can_hide_reflection(self):
        self.client.login(username="staff", password="StaffPass123!")

        response = self.client.post(
            reverse("staff_reflection_action", args=[self.comment.id]),
            {
                "action": "hide",
                "reason": "Too sensitive.",
            },
        )

        self.assertEqual(response.status_code, 302)

        self.comment.refresh_from_db()

        self.assertTrue(self.comment.is_hidden)
        self.assertEqual(self.comment.hidden_reason, "Too sensitive.")
        self.assertEqual(self.comment.hidden_by, self.staff)

    def test_hidden_reflection_not_visible_to_other_regular_user(self):
        self.comment.is_hidden = True
        self.comment.hidden_reason = "Too sensitive."
        self.comment.hidden_by = self.staff
        self.comment.save()

        self.client.login(username="other", password="OtherPass123!")

        response = self.client.get(
            reverse("passage_reader", args=[self.active_plan.id, self.day1.id, 0])
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Reportable reflection.")

    def test_hidden_reflection_visible_to_author(self):
        self.comment.is_hidden = True
        self.comment.save()

        self.client.login(username="levin", password="UserPass123!")

        response = self.client.get(
            reverse("passage_reader", args=[self.active_plan.id, self.day1.id, 0])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Reportable reflection.")

    def test_staff_can_unhide_reflection(self):
        self.comment.is_hidden = True
        self.comment.hidden_reason = "Too sensitive."
        self.comment.hidden_by = self.staff
        self.comment.save()

        self.client.login(username="staff", password="StaffPass123!")

        response = self.client.post(
            reverse("staff_reflection_action", args=[self.comment.id]),
            {
                "action": "unhide",
            },
        )

        self.assertEqual(response.status_code, 302)

        self.comment.refresh_from_db()

        self.assertFalse(self.comment.is_hidden)
        self.assertEqual(self.comment.hidden_reason, "")
        self.assertIsNone(self.comment.hidden_by)