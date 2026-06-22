from django.contrib import admin
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import SmallGroup
from comments.models import ReflectionComment, ReflectionReport
from reading.models import ActivePlan, PlanEnrollment, ReadingPlan, ReadingPlanDay


class ReflectionCommentAdminLegacyMirrorTests(TestCase):
    """REFLECTION-MIRROR.1G/1H: the admin must not expose or search the legacy
    ``small_group_at_post`` mirror. The field was removed from the model in
    REFLECTION-MIRROR.1H; this remains a regression guard against reintroducing
    any admin reference to it. The structure-native snapshot stays usable.
    """

    def setUp(self):
        self.model_admin = admin.site._registry[ReflectionComment]

    def test_admin_does_not_expose_or_search_legacy_mirror(self):
        for attr in ("list_display", "list_filter", "search_fields", "readonly_fields"):
            values = tuple(getattr(self.model_admin, attr) or ())
            self.assertNotIn(
                "small_group_at_post",
                values,
                msg=f"small_group_at_post must not appear in admin {attr}",
            )
        self.assertNotIn(
            "small_group_at_post",
            tuple(getattr(self.model_admin, "list_select_related", ()) or ()),
        )

    def test_admin_fieldsets_do_not_reference_legacy_mirror(self):
        fieldsets = getattr(self.model_admin, "fieldsets", None)
        if not fieldsets:
            return
        for _name, opts in fieldsets:
            self.assertNotIn("small_group_at_post", tuple(opts.get("fields", ()) or ()))


class ReflectionReportModerationTests(TestCase):
    def setUp(self):
        self.group = SmallGroup.objects.create(name="Rainbow 4")

        self.user = User.objects.create_user(
            username="levin",
            password="UserPass123!",
        )

        self.other_user = User.objects.create_user(
            username="other",
            password="OtherPass123!",
        )

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

    def set_language(self, language="en"):
        session = self.client.session
        session["language"] = language
        session.save()

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

        self.set_language("en")
        self.client.login(username="staff", password="StaffPass123!")

        response = self.client.get(reverse("staff_reflection_reports"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Reflection Reports")
        self.assertContains(response, "Needs review.")
        self.assertContains(response, "Reportable reflection.")

    def test_chinese_staff_report_page_uses_chinese_labels(self):
        ReflectionReport.objects.create(
            comment=self.comment,
            reporter=self.other_user,
            reason="Needs review.",
        )
        self.comment.is_hidden = True
        self.comment.hidden_reason = "Internal handling note."
        self.comment.save(update_fields=["is_hidden", "hidden_reason"])

        self.set_language("zh")
        self.client.login(username="staff", password="StaffPass123!")

        response = self.client.get(reverse("staff_reflection_reports"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "默想举报")
        self.assertContains(response, "查看被举报的默想并管理可见性")
        self.assertContains(response, "搜索")
        self.assertContains(response, "状态")
        self.assertContains(response, "未处理")
        self.assertContains(response, "筛选")
        self.assertContains(response, "作者")
        self.assertContains(response, "已隐藏")
        self.assertContains(response, "举报人")
        self.assertContains(response, "原因")
        self.assertContains(response, "隐藏原因")
        self.assertContains(response, "仅内部可见的处理原因")
        self.assertContains(response, "隐藏默想")
        self.assertContains(response, "取消隐藏默想")
        self.assertContains(response, "标记举报已处理")
        self.assertContains(response, "忽略举报")
        self.assertNotContains(response, "Reflection Reports")
        self.assertNotContains(response, "Hide Reflection")

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

    def test_hiding_reported_reflection_post_closes_open_reports(self):
        report = ReflectionReport.objects.create(
            comment=self.comment,
            reporter=self.other_user,
            reason="Inappropriate.",
        )

        self.client.login(username="staff", password="StaffPass123!")
        response = self.client.post(
            reverse("staff_reflection_action", args=[self.comment.id]),
            {"action": "hide", "reason": "Too sensitive."},
        )

        self.assertEqual(response.status_code, 302)

        self.comment.refresh_from_db()
        self.assertTrue(self.comment.is_hidden)

        report.refresh_from_db()
        self.assertEqual(report.status, ReflectionReport.STATUS_REVIEWED)
        self.assertEqual(report.reviewed_by, self.staff)
        self.assertIsNotNone(report.reviewed_at)

    def test_hiding_reported_reflection_reply_closes_open_reports(self):
        reply = ReflectionComment.objects.create(
            user=self.other_user,
            active_plan=self.active_plan,
            plan_day=self.day1,
            scripture_ref_key="John 1",
            visibility=ReflectionComment.VISIBILITY_CHURCH,
            parent=self.comment,
            body="Reportable reply.",
        )
        report = ReflectionReport.objects.create(
            comment=reply,
            reporter=self.user,
            reason="Spam.",
        )

        self.client.login(username="staff", password="StaffPass123!")
        response = self.client.post(
            reverse("staff_reflection_action", args=[reply.id]),
            {"action": "hide", "reason": "Spam."},
        )

        self.assertEqual(response.status_code, 302)

        reply.refresh_from_db()
        self.assertTrue(reply.is_hidden)

        report.refresh_from_db()
        self.assertEqual(report.status, ReflectionReport.STATUS_REVIEWED)
        self.assertEqual(report.reviewed_by, self.staff)

    def test_hiding_reflection_leaves_already_reviewed_report_untouched(self):
        # A report already resolved (dismissed) must not be re-touched or duplicated.
        dismissed = ReflectionReport.objects.create(
            comment=self.comment,
            reporter=self.other_user,
            reason="Old report.",
            status=ReflectionReport.STATUS_DISMISSED,
        )

        self.client.login(username="staff", password="StaffPass123!")
        self.client.post(
            reverse("staff_reflection_action", args=[self.comment.id]),
            {"action": "hide", "reason": "Too sensitive."},
        )

        dismissed.refresh_from_db()
        self.assertEqual(dismissed.status, ReflectionReport.STATUS_DISMISSED)
        self.assertIsNone(dismissed.reviewed_by)
        self.assertEqual(
            ReflectionReport.objects.filter(comment=self.comment).count(),
            1,
        )

    def test_re_hiding_already_hidden_reflection_is_idempotent(self):
        self.comment.is_hidden = True
        self.comment.hidden_by = self.staff
        self.comment.hidden_at = timezone.now()
        self.comment.save()

        # A report left open even though the content is already hidden.
        report = ReflectionReport.objects.create(
            comment=self.comment,
            reporter=self.other_user,
            reason="Still open.",
        )

        self.client.login(username="staff", password="StaffPass123!")
        response = self.client.post(
            reverse("staff_reflection_action", args=[self.comment.id]),
            {"action": "hide", "reason": "Too sensitive."},
        )

        self.assertEqual(response.status_code, 302)

        self.comment.refresh_from_db()
        self.assertTrue(self.comment.is_hidden)

        report.refresh_from_db()
        self.assertEqual(report.status, ReflectionReport.STATUS_REVIEWED)
        self.assertEqual(report.reviewed_by, self.staff)

    def test_hiding_reflection_does_not_close_reports_for_other_content(self):
        other_comment = ReflectionComment.objects.create(
            user=self.other_user,
            active_plan=self.active_plan,
            plan_day=self.day1,
            scripture_ref_key="John 1",
            visibility=ReflectionComment.VISIBILITY_CHURCH,
            body="Other reflection.",
        )
        target_report = ReflectionReport.objects.create(
            comment=self.comment, reporter=self.other_user, reason="A."
        )
        other_report = ReflectionReport.objects.create(
            comment=other_comment, reporter=self.user, reason="B."
        )

        self.client.login(username="staff", password="StaffPass123!")
        self.client.post(
            reverse("staff_reflection_action", args=[self.comment.id]),
            {"action": "hide", "reason": "Too sensitive."},
        )

        target_report.refresh_from_db()
        other_report.refresh_from_db()
        self.assertEqual(target_report.status, ReflectionReport.STATUS_REVIEWED)
        self.assertEqual(other_report.status, ReflectionReport.STATUS_OPEN)

    def test_non_staff_cannot_hide_reflection_or_close_reports(self):
        report = ReflectionReport.objects.create(
            comment=self.comment, reporter=self.other_user, reason="A."
        )

        self.client.login(username="other", password="OtherPass123!")
        response = self.client.post(
            reverse("staff_reflection_action", args=[self.comment.id]),
            {"action": "hide", "reason": "Nope."},
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response.url)

        self.comment.refresh_from_db()
        report.refresh_from_db()
        self.assertFalse(self.comment.is_hidden)
        self.assertEqual(report.status, ReflectionReport.STATUS_OPEN)
