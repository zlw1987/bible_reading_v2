from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import SmallGroup
from prayers.forms import localized_visibility_choices
from prayers.models import PrayerMark, PrayerReport, PrayerRequest
from prayers.templatetags.prayer_extras import prayer_visibility_label


class PrayerRequestFlowTests(TestCase):
    def setUp(self):
        self.group = SmallGroup.objects.create(name="Rainbow 4")
        self.other_group = SmallGroup.objects.create(name="Rainbow 5")

        self.user = User.objects.create_user(
            username="levin",
            password="TestPass123!",
        )
        self.user.profile.small_group = self.group
        self.user.profile.save()

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

        self.staff_user = User.objects.create_user(
            username="staff",
            password="TestPass123!",
            is_staff=True,
        )

    def set_language(self, language="en"):
        session = self.client.session
        session["language"] = language
        session.save()

    def test_prayer_list_requires_login(self):
        response = self.client.get(reverse("prayer_list"))

        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_chinese_prayer_list_localizes_form_and_wall_names(self):
        self.set_language("zh")
        self.client.login(username="levin", password="TestPass123!")

        response = self.client.get(reverse("prayer_list"))

        self.assertContains(response, "代祷墙")
        self.assertContains(response, "新的代祷事项")
        self.assertContains(response, "代祷标题")
        self.assertContains(response, "分享你的代祷事项")
        self.assertContains(response, "发表代祷")
        self.assertContains(response, "可见范围")
        self.assertNotContains(response, "Prayer title")
        self.assertNotContains(response, "Share your prayer request")
        self.assertNotContains(response, "Post anonymously")
        # The bare substring "Visibility" also appears in base.html's
        # header-auto-hide JS (updateHeaderVisibility /
        # requestHeaderVisibilityUpdate), so assert the English visibility
        # *form label* specifically instead of the raw word.
        self.assertNotRegex(response.content.decode(), r">\s*Visibility\s*<")
        self.assertNotContains(response, "Prayer Wall")

    def test_english_prayer_list_uses_prayer_wall_names(self):
        self.set_language("en")
        self.client.login(username="levin", password="TestPass123!")

        response = self.client.get(reverse("prayer_list"))

        self.assertContains(response, "Prayer Wall")
        self.assertContains(response, "New Prayer Request")
        self.assertContains(response, "Prayer title")
        self.assertContains(response, "Share your prayer request")
        self.assertContains(response, "Post Prayer Request")

    def test_user_can_create_group_prayer_request(self):
        self.set_language("en")
        self.client.login(username="levin", password="TestPass123!")

        response = self.client.post(
            reverse("prayer_list"),
            {
                "title": "Pray for my family",
                "body": "Please pray for peace.",
                "visibility": PrayerRequest.VISIBILITY_GROUP,
                "is_anonymous": "",
            },
        )

        self.assertEqual(response.status_code, 302)

        prayer = PrayerRequest.objects.get(title="Pray for my family")

        self.assertEqual(prayer.user, self.user)
        self.assertEqual(prayer.visibility, PrayerRequest.VISIBILITY_GROUP)
        self.assertEqual(prayer.small_group_at_post, self.group)

    def test_group_prayer_visible_to_same_group_user(self):
        PrayerRequest.objects.create(
            user=self.user,
            title="Group prayer",
            body="Please pray.",
            visibility=PrayerRequest.VISIBILITY_GROUP,
            small_group_at_post=self.group,
        )

        self.set_language("en")
        self.client.login(username="same_group", password="TestPass123!")

        response = self.client.get(
            reverse("prayer_list"),
            {
                "tab": "group",
                "status": "open",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Group prayer")

    def test_group_prayer_hidden_from_other_group_user(self):
        PrayerRequest.objects.create(
            user=self.user,
            title="Hidden group prayer",
            body="Please pray.",
            visibility=PrayerRequest.VISIBILITY_GROUP,
            small_group_at_post=self.group,
        )

        self.set_language("en")
        self.client.login(username="other_group", password="TestPass123!")

        response = self.client.get(
            reverse("prayer_list"),
            {
                "tab": "group",
                "status": "open",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Hidden group prayer")

    def test_church_prayer_visible_to_other_group_user(self):
        PrayerRequest.objects.create(
            user=self.user,
            title="Church prayer",
            body="Please pray.",
            visibility=PrayerRequest.VISIBILITY_CHURCH,
        )

        self.set_language("en")
        self.client.login(username="other_group", password="TestPass123!")

        response = self.client.get(
            reverse("prayer_list"),
            {
                "tab": "church",
                "status": "open",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Church prayer")

    def test_user_can_mark_prayed_once(self):
        prayer = PrayerRequest.objects.create(
            user=self.user,
            title="Prayer count",
            body="Please pray.",
            visibility=PrayerRequest.VISIBILITY_CHURCH,
        )

        self.set_language("en")
        self.client.login(username="same_group", password="TestPass123!")

        response = self.client.post(
            reverse("mark_prayed", args=[prayer.id]),
            {
                "next": reverse("prayer_detail", args=[prayer.id]),
            },
        )

        self.assertEqual(response.status_code, 302)

        self.client.post(
            reverse("mark_prayed", args=[prayer.id]),
            {
                "next": reverse("prayer_detail", args=[prayer.id]),
            },
        )

        count = PrayerMark.objects.filter(
            prayer_request=prayer,
            user=self.same_group_user,
        ).count()

        self.assertEqual(count, 1)

    def test_owner_can_mark_prayer_answered(self):
        prayer = PrayerRequest.objects.create(
            user=self.user,
            title="Answered prayer",
            body="Please pray.",
            visibility=PrayerRequest.VISIBILITY_GROUP,
            small_group_at_post=self.group,
        )

        self.set_language("en")
        self.client.login(username="levin", password="TestPass123!")

        response = self.client.post(
            reverse("update_prayer_status", args=[prayer.id]),
            {
                "status": PrayerRequest.STATUS_ANSWERED,
                "answer_note": "God answered.",
            },
        )

        self.assertEqual(response.status_code, 302)

        prayer.refresh_from_db()

        self.assertEqual(prayer.status, PrayerRequest.STATUS_ANSWERED)
        self.assertEqual(prayer.answer_note, "God answered.")

    def test_owner_can_edit_prayer_request(self):
        prayer = PrayerRequest.objects.create(
            user=self.user,
            title="Old title",
            body="Old body",
            visibility=PrayerRequest.VISIBILITY_GROUP,
            small_group_at_post=self.group,
        )

        self.set_language("en")
        self.client.login(username="levin", password="TestPass123!")

        response = self.client.post(
            reverse("edit_prayer_request", args=[prayer.id]),
            {
                "title": "New title",
                "body": "New body",
                "visibility": PrayerRequest.VISIBILITY_CHURCH,
                "is_anonymous": "on",
            },
        )

        self.assertEqual(response.status_code, 302)

        prayer.refresh_from_db()

        self.assertEqual(prayer.title, "New title")
        self.assertEqual(prayer.body, "New body")
        self.assertEqual(prayer.visibility, PrayerRequest.VISIBILITY_CHURCH)
        self.assertTrue(prayer.is_anonymous)

    def test_other_user_cannot_edit_prayer_request(self):
        prayer = PrayerRequest.objects.create(
            user=self.user,
            title="Protected title",
            body="Protected body",
            visibility=PrayerRequest.VISIBILITY_CHURCH,
        )

        self.set_language("en")
        self.client.login(username="same_group", password="TestPass123!")

        response = self.client.post(
            reverse("edit_prayer_request", args=[prayer.id]),
            {
                "title": "Hacked title",
                "body": "Hacked body",
                "visibility": PrayerRequest.VISIBILITY_CHURCH,
                "is_anonymous": "",
            },
        )

        self.assertEqual(response.status_code, 302)

        prayer.refresh_from_db()

        self.assertEqual(prayer.title, "Protected title")
        self.assertEqual(prayer.body, "Protected body")

    def test_prayer_detail_shows_one_delete_control_for_owner(self):
        prayer = PrayerRequest.objects.create(
            user=self.user,
            title="Deletable prayer",
            body="Please pray.",
            visibility=PrayerRequest.VISIBILITY_CHURCH,
        )

        self.set_language("zh")
        self.client.login(username="levin", password="TestPass123!")

        response = self.client.get(reverse("prayer_detail", args=[prayer.id]))
        content = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            content.count(reverse("delete_prayer_request", args=[prayer.id])),
            1,
        )
        self.assertContains(response, "删除", count=1)

    def test_prayer_detail_hides_delete_control_from_non_owner(self):
        prayer = PrayerRequest.objects.create(
            user=self.user,
            title="Not deletable by viewer",
            body="Please pray.",
            visibility=PrayerRequest.VISIBILITY_CHURCH,
        )

        self.set_language("en")
        self.client.login(username="same_group", password="TestPass123!")

        response = self.client.get(reverse("prayer_detail", args=[prayer.id]))
        content = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertNotIn(reverse("delete_prayer_request", args=[prayer.id]), content)

    def test_user_can_edit_own_prayer_comment(self):
        from prayers.models import PrayerComment

        prayer = PrayerRequest.objects.create(
            user=self.user,
            title="Prayer with comment",
            body="Please pray.",
            visibility=PrayerRequest.VISIBILITY_CHURCH,
        )

        comment = PrayerComment.objects.create(
            prayer_request=prayer,
            user=self.same_group_user,
            body="Old comment.",
        )

        self.set_language("en")
        self.client.login(username="same_group", password="TestPass123!")

        response = self.client.post(
            reverse("edit_prayer_comment", args=[comment.id]),
            {
                "body": "Updated comment.",
                "is_anonymous": "on",
            },
        )

        self.assertEqual(response.status_code, 302)

        comment.refresh_from_db()

        self.assertEqual(comment.body, "Updated comment.")
        self.assertTrue(comment.is_anonymous)

    def test_other_user_cannot_edit_prayer_comment(self):
        from prayers.models import PrayerComment

        prayer = PrayerRequest.objects.create(
            user=self.user,
            title="Prayer with protected comment",
            body="Please pray.",
            visibility=PrayerRequest.VISIBILITY_CHURCH,
        )

        comment = PrayerComment.objects.create(
            prayer_request=prayer,
            user=self.same_group_user,
            body="Protected comment.",
        )

        self.set_language("en")
        self.client.login(username="other_group", password="TestPass123!")

        response = self.client.post(
            reverse("edit_prayer_comment", args=[comment.id]),
            {
                "body": "Hacked comment.",
                "is_anonymous": "",
            },
        )

        self.assertEqual(response.status_code, 302)

        comment.refresh_from_db()

        self.assertEqual(comment.body, "Protected comment.")

    def test_user_can_delete_own_prayer_comment(self):
        from prayers.models import PrayerComment

        prayer = PrayerRequest.objects.create(
            user=self.user,
            title="Prayer with deletable comment",
            body="Please pray.",
            visibility=PrayerRequest.VISIBILITY_CHURCH,
        )

        comment = PrayerComment.objects.create(
            prayer_request=prayer,
            user=self.same_group_user,
            body="Delete me.",
        )

        self.set_language("en")
        self.client.login(username="same_group", password="TestPass123!")

        response = self.client.post(
            reverse("delete_prayer_comment", args=[comment.id])
        )

        self.assertEqual(response.status_code, 302)

        comment.refresh_from_db()

        self.assertTrue(comment.is_deleted)
        self.assertEqual(comment.body, "")

    def test_user_can_report_visible_prayer_request(self):
        prayer = PrayerRequest.objects.create(
            user=self.user,
            title="Reportable prayer",
            body="Please pray.",
            visibility=PrayerRequest.VISIBILITY_CHURCH,
        )

        self.set_language("en")
        self.client.login(username="same_group", password="TestPass123!")

        response = self.client.post(
            reverse("report_prayer_request", args=[prayer.id]),
            {
                "reason": "This needs review.",
                "next": reverse("prayer_detail", args=[prayer.id]),
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("prayer_detail", args=[prayer.id]))
        self.assertTrue(
            PrayerReport.objects.filter(
                prayer_request=prayer,
                reporter=self.same_group_user,
                reason="This needs review.",
            ).exists()
        )

    def test_user_cannot_report_own_prayer_request(self):
        prayer = PrayerRequest.objects.create(
            user=self.user,
            title="Own prayer",
            body="Please pray.",
            visibility=PrayerRequest.VISIBILITY_CHURCH,
        )

        self.set_language("en")
        self.client.login(username="levin", password="TestPass123!")

        response = self.client.post(
            reverse("report_prayer_request", args=[prayer.id]),
            {"reason": "Reporting myself."},
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(PrayerReport.objects.filter(prayer_request=prayer).exists())

    def test_duplicate_report_is_not_created(self):
        prayer = PrayerRequest.objects.create(
            user=self.user,
            title="Duplicate report prayer",
            body="Please pray.",
            visibility=PrayerRequest.VISIBILITY_CHURCH,
        )

        self.set_language("en")
        self.client.login(username="same_group", password="TestPass123!")

        self.client.post(
            reverse("report_prayer_request", args=[prayer.id]),
            {"reason": "First report."},
        )
        self.client.post(
            reverse("report_prayer_request", args=[prayer.id]),
            {"reason": "Second report."},
        )

        self.assertEqual(
            PrayerReport.objects.filter(
                prayer_request=prayer,
                reporter=self.same_group_user,
            ).count(),
            1,
        )

    def test_non_staff_cannot_access_staff_prayer_reports(self):
        self.set_language("en")
        self.client.login(username="levin", password="TestPass123!")

        response = self.client.get(reverse("staff_prayer_reports"))

        self.assertEqual(response.status_code, 302)

    def test_staff_can_access_staff_prayer_reports(self):
        prayer = PrayerRequest.objects.create(
            user=self.user,
            title="Reported prayer",
            body="Please pray.",
            visibility=PrayerRequest.VISIBILITY_CHURCH,
        )
        PrayerReport.objects.create(
            prayer_request=prayer,
            reporter=self.same_group_user,
            reason="Review this.",
        )

        self.set_language("en")
        self.client.login(username="staff", password="TestPass123!")

        response = self.client.get(reverse("staff_prayer_reports"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Prayer Reports")
        self.assertContains(response, "Reported prayer")
        self.assertContains(response, "Review this.")

    def test_staff_can_hide_prayer_request(self):
        prayer = PrayerRequest.objects.create(
            user=self.user,
            title="Hide me",
            body="Please pray.",
            visibility=PrayerRequest.VISIBILITY_CHURCH,
        )

        self.set_language("en")
        self.client.login(username="staff", password="TestPass123!")

        response = self.client.post(
            reverse("staff_prayer_action", args=[prayer.id]),
            {
                "action": "hide",
                "reason": "Needs moderation.",
            },
        )

        self.assertEqual(response.status_code, 302)
        prayer.refresh_from_db()
        self.assertTrue(prayer.is_hidden)
        self.assertEqual(prayer.hidden_reason, "Needs moderation.")
        self.assertEqual(prayer.hidden_by, self.staff_user)

    def test_hidden_prayer_not_visible_to_other_regular_user_in_list(self):
        PrayerRequest.objects.create(
            user=self.user,
            title="Hidden from list",
            body="Please pray.",
            visibility=PrayerRequest.VISIBILITY_CHURCH,
            is_hidden=True,
        )

        self.set_language("en")
        self.client.login(username="same_group", password="TestPass123!")

        response = self.client.get(
            reverse("prayer_list"),
            {
                "tab": "church",
                "status": "open",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Hidden from list")

    def test_hidden_prayer_not_visible_to_other_regular_user_in_detail(self):
        prayer = PrayerRequest.objects.create(
            user=self.user,
            title="Hidden detail",
            body="Please pray.",
            visibility=PrayerRequest.VISIBILITY_CHURCH,
            is_hidden=True,
        )

        self.set_language("en")
        self.client.login(username="same_group", password="TestPass123!")

        response = self.client.get(reverse("prayer_detail", args=[prayer.id]))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("prayer_list"))

    def test_hidden_prayer_visible_to_author(self):
        prayer = PrayerRequest.objects.create(
            user=self.user,
            title="Author can see hidden",
            body="Please pray.",
            visibility=PrayerRequest.VISIBILITY_CHURCH,
            is_hidden=True,
        )

        self.set_language("en")
        self.client.login(username="levin", password="TestPass123!")

        response = self.client.get(reverse("prayer_detail", args=[prayer.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Author can see hidden")
        self.assertContains(response, "Hidden")

    def test_hidden_prayer_visible_to_staff(self):
        prayer = PrayerRequest.objects.create(
            user=self.user,
            title="Staff can see hidden",
            body="Please pray.",
            visibility=PrayerRequest.VISIBILITY_CHURCH,
            is_hidden=True,
        )

        self.set_language("en")
        self.client.login(username="staff", password="TestPass123!")

        response = self.client.get(reverse("prayer_detail", args=[prayer.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Staff can see hidden")
        self.assertContains(response, "Hidden")

    def test_staff_can_unhide_prayer_request(self):
        prayer = PrayerRequest.objects.create(
            user=self.user,
            title="Unhide me",
            body="Please pray.",
            visibility=PrayerRequest.VISIBILITY_CHURCH,
            is_hidden=True,
            hidden_reason="Needs moderation.",
            hidden_by=self.staff_user,
        )

        self.set_language("en")
        self.client.login(username="staff", password="TestPass123!")

        response = self.client.post(
            reverse("staff_prayer_action", args=[prayer.id]),
            {"action": "unhide"},
        )

        self.assertEqual(response.status_code, 302)
        prayer.refresh_from_db()
        self.assertFalse(prayer.is_hidden)
        self.assertEqual(prayer.hidden_reason, "")
        self.assertIsNone(prayer.hidden_by)

    def test_staff_can_mark_reports_reviewed(self):
        prayer = PrayerRequest.objects.create(
            user=self.user,
            title="Review reports",
            body="Please pray.",
            visibility=PrayerRequest.VISIBILITY_CHURCH,
        )
        report = PrayerReport.objects.create(
            prayer_request=prayer,
            reporter=self.same_group_user,
            reason="Review this.",
        )

        self.set_language("en")
        self.client.login(username="staff", password="TestPass123!")

        response = self.client.post(
            reverse("staff_prayer_action", args=[prayer.id]),
            {"action": "mark_reviewed"},
        )

        self.assertEqual(response.status_code, 302)
        report.refresh_from_db()
        self.assertEqual(report.status, PrayerReport.STATUS_REVIEWED)
        self.assertEqual(report.reviewed_by, self.staff_user)
        self.assertIsNotNone(report.reviewed_at)

    def test_staff_can_dismiss_reports(self):
        prayer = PrayerRequest.objects.create(
            user=self.user,
            title="Dismiss reports",
            body="Please pray.",
            visibility=PrayerRequest.VISIBILITY_CHURCH,
        )
        report = PrayerReport.objects.create(
            prayer_request=prayer,
            reporter=self.same_group_user,
            reason="Dismiss this.",
        )

        self.set_language("en")
        self.client.login(username="staff", password="TestPass123!")

        response = self.client.post(
            reverse("staff_prayer_action", args=[prayer.id]),
            {"action": "dismiss_reports"},
        )

        self.assertEqual(response.status_code, 302)
        report.refresh_from_db()
        self.assertEqual(report.status, PrayerReport.STATUS_DISMISSED)
        self.assertEqual(report.reviewed_by, self.staff_user)
        self.assertIsNotNone(report.reviewed_at)

    def test_chinese_report_page_localizes_text(self):
        prayer = PrayerRequest.objects.create(
            user=self.user,
            title="Chinese report prayer",
            body="Please pray.",
            visibility=PrayerRequest.VISIBILITY_CHURCH,
        )

        self.set_language("zh")
        self.client.login(username="same_group", password="TestPass123!")

        response = self.client.get(reverse("report_prayer_request", args=[prayer.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "举报代祷事项")
        self.assertContains(response, "被举报内容")
        self.assertContains(response, "原因")
        self.assertContains(response, "提交举报")
        self.assertNotContains(response, "Report Prayer Request")
        self.assertNotContains(response, "Prayer Request")
        self.assertNotContains(response, "Reason")
        self.assertNotContains(response, "Submit Report")

    def test_english_report_page_contains_english_text(self):
        prayer = PrayerRequest.objects.create(
            user=self.user,
            title="English report prayer",
            body="Please pray.",
            visibility=PrayerRequest.VISIBILITY_CHURCH,
        )

        self.set_language("en")
        self.client.login(username="same_group", password="TestPass123!")

        response = self.client.get(reverse("report_prayer_request", args=[prayer.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Report Prayer Request")
        self.assertContains(response, "Prayer Request")
        self.assertContains(response, "Reason")
        self.assertContains(response, "Submit Report")

    def test_hiding_reported_prayer_request_closes_open_reports(self):
        prayer = PrayerRequest.objects.create(
            user=self.user,
            title="Reportable",
            body="Please pray.",
            visibility=PrayerRequest.VISIBILITY_CHURCH,
        )
        report = PrayerReport.objects.create(
            prayer_request=prayer,
            reporter=self.same_group_user,
            reason="Inappropriate.",
        )

        self.client.login(username="staff", password="TestPass123!")
        response = self.client.post(
            reverse("staff_prayer_action", args=[prayer.id]),
            {"action": "hide", "reason": "Needs moderation."},
        )

        self.assertEqual(response.status_code, 302)

        prayer.refresh_from_db()
        self.assertTrue(prayer.is_hidden)

        report.refresh_from_db()
        self.assertEqual(report.status, PrayerReport.STATUS_REVIEWED)
        self.assertEqual(report.reviewed_by, self.staff_user)
        self.assertIsNotNone(report.reviewed_at)

    def test_hiding_prayer_leaves_already_reviewed_report_untouched(self):
        prayer = PrayerRequest.objects.create(
            user=self.user,
            title="Reportable",
            body="Please pray.",
            visibility=PrayerRequest.VISIBILITY_CHURCH,
        )
        dismissed = PrayerReport.objects.create(
            prayer_request=prayer,
            reporter=self.same_group_user,
            reason="Old report.",
            status=PrayerReport.STATUS_DISMISSED,
        )

        self.client.login(username="staff", password="TestPass123!")
        self.client.post(
            reverse("staff_prayer_action", args=[prayer.id]),
            {"action": "hide", "reason": "Needs moderation."},
        )

        dismissed.refresh_from_db()
        self.assertEqual(dismissed.status, PrayerReport.STATUS_DISMISSED)
        self.assertIsNone(dismissed.reviewed_by)
        self.assertEqual(
            PrayerReport.objects.filter(prayer_request=prayer).count(),
            1,
        )

    def test_re_hiding_already_hidden_prayer_is_idempotent(self):
        prayer = PrayerRequest.objects.create(
            user=self.user,
            title="Reportable",
            body="Please pray.",
            visibility=PrayerRequest.VISIBILITY_CHURCH,
            is_hidden=True,
            hidden_by=self.staff_user,
            hidden_at=timezone.now(),
        )
        report = PrayerReport.objects.create(
            prayer_request=prayer,
            reporter=self.same_group_user,
            reason="Still open.",
        )

        self.client.login(username="staff", password="TestPass123!")
        response = self.client.post(
            reverse("staff_prayer_action", args=[prayer.id]),
            {"action": "hide", "reason": "Needs moderation."},
        )

        self.assertEqual(response.status_code, 302)

        prayer.refresh_from_db()
        self.assertTrue(prayer.is_hidden)

        report.refresh_from_db()
        self.assertEqual(report.status, PrayerReport.STATUS_REVIEWED)
        self.assertEqual(report.reviewed_by, self.staff_user)

    def test_hiding_prayer_does_not_close_reports_for_other_content(self):
        target = PrayerRequest.objects.create(
            user=self.user,
            title="Target",
            body="Please pray.",
            visibility=PrayerRequest.VISIBILITY_CHURCH,
        )
        other = PrayerRequest.objects.create(
            user=self.user,
            title="Other",
            body="Please pray.",
            visibility=PrayerRequest.VISIBILITY_CHURCH,
        )
        target_report = PrayerReport.objects.create(
            prayer_request=target, reporter=self.same_group_user, reason="A."
        )
        other_report = PrayerReport.objects.create(
            prayer_request=other, reporter=self.same_group_user, reason="B."
        )

        self.client.login(username="staff", password="TestPass123!")
        self.client.post(
            reverse("staff_prayer_action", args=[target.id]),
            {"action": "hide", "reason": "Needs moderation."},
        )

        target_report.refresh_from_db()
        other_report.refresh_from_db()
        self.assertEqual(target_report.status, PrayerReport.STATUS_REVIEWED)
        self.assertEqual(other_report.status, PrayerReport.STATUS_OPEN)

    def test_non_staff_cannot_hide_prayer_or_close_reports(self):
        prayer = PrayerRequest.objects.create(
            user=self.user,
            title="Reportable",
            body="Please pray.",
            visibility=PrayerRequest.VISIBILITY_CHURCH,
        )
        report = PrayerReport.objects.create(
            prayer_request=prayer, reporter=self.same_group_user, reason="A."
        )

        self.client.login(username="same_group", password="TestPass123!")
        response = self.client.post(
            reverse("staff_prayer_action", args=[prayer.id]),
            {"action": "hide", "reason": "Nope."},
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response.url)

        prayer.refresh_from_db()
        report.refresh_from_db()
        self.assertFalse(prayer.is_hidden)
        self.assertEqual(report.status, PrayerReport.STATUS_OPEN)

    def test_moderation_queue_drops_open_report_after_hide(self):
        prayer = PrayerRequest.objects.create(
            user=self.user,
            title="Reportable",
            body="Please pray.",
            visibility=PrayerRequest.VISIBILITY_CHURCH,
        )
        PrayerReport.objects.create(
            prayer_request=prayer,
            reporter=self.same_group_user,
            reason="Inappropriate.",
        )

        self.client.login(username="staff", password="TestPass123!")

        before = self.client.get(reverse("staff_moderation_queue"))
        self.assertEqual(
            before.context["moderation_counts"]["reported_prayer_requests"], 1
        )

        self.client.post(
            reverse("staff_prayer_action", args=[prayer.id]),
            {"action": "hide", "reason": "Needs moderation."},
        )

        after = self.client.get(reverse("staff_moderation_queue"))
        self.assertEqual(
            after.context["moderation_counts"]["reported_prayer_requests"], 0
        )


class PrayerListTabAudienceTests(TestCase):
    """Tab filtering on /prayers/ must follow visibility, not authorship.

    Regression coverage for UI-H.1: the current user's own church-wide and
    private prayers must not leak into the group/church tabs merely because the
    user authored them.
    """

    def setUp(self):
        self.group = SmallGroup.objects.create(name="Rainbow 4")
        self.other_group = SmallGroup.objects.create(name="Rainbow 5")

        self.user = User.objects.create_user(
            username="levin",
            password="TestPass123!",
        )
        self.user.profile.small_group = self.group
        self.user.profile.save()

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

        self.no_group_user = User.objects.create_user(
            username="no_group",
            password="TestPass123!",
        )
        # no_group_user keeps the default empty small_group on their profile.

        # Prayers authored by self.user across all three visibilities.
        self.own_private = PrayerRequest.objects.create(
            user=self.user,
            title="Own private request",
            body="Please pray.",
            visibility=PrayerRequest.VISIBILITY_PRIVATE,
        )
        self.own_group = PrayerRequest.objects.create(
            user=self.user,
            title="Own group request",
            body="Please pray.",
            visibility=PrayerRequest.VISIBILITY_GROUP,
            small_group_at_post=self.group,
        )
        self.own_church = PrayerRequest.objects.create(
            user=self.user,
            title="Own church request",
            body="Please pray.",
            visibility=PrayerRequest.VISIBILITY_CHURCH,
        )
        # Prayers authored by others.
        self.same_group_group = PrayerRequest.objects.create(
            user=self.same_group_user,
            title="Same group request",
            body="Please pray.",
            visibility=PrayerRequest.VISIBILITY_GROUP,
            small_group_at_post=self.group,
        )
        self.other_user_church = PrayerRequest.objects.create(
            user=self.other_group_user,
            title="Other church request",
            body="Please pray.",
            visibility=PrayerRequest.VISIBILITY_CHURCH,
        )

    def titles_for(self, username, tab):
        self.client.login(username=username, password="TestPass123!")
        response = self.client.get(
            reverse("prayer_list"),
            {"tab": tab, "status": "all"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["tab"], tab)
        return {prayer.title for prayer in response.context["prayers"]}

    def test_my_tab_includes_own_private_group_and_church(self):
        titles = self.titles_for("levin", "my")
        self.assertIn("Own private request", titles)
        self.assertIn("Own group request", titles)
        self.assertIn("Own church request", titles)
        # The "my" tab is scoped to the author, so others' prayers stay out.
        self.assertNotIn("Same group request", titles)
        self.assertNotIn("Other church request", titles)

    def test_group_tab_includes_own_and_same_group_group_prayers(self):
        titles = self.titles_for("levin", "group")
        self.assertIn("Own group request", titles)
        self.assertIn("Same group request", titles)

    def test_group_tab_excludes_own_church_prayer(self):
        titles = self.titles_for("levin", "group")
        self.assertNotIn("Own church request", titles)

    def test_group_tab_excludes_own_private_prayer(self):
        titles = self.titles_for("levin", "group")
        self.assertNotIn("Own private request", titles)

    def test_group_tab_excludes_other_group_prayers(self):
        # other_group_user's group tab should not see Rainbow 4 group prayers.
        titles = self.titles_for("other_group", "group")
        self.assertNotIn("Own group request", titles)
        self.assertNotIn("Same group request", titles)

    def test_church_tab_includes_own_and_other_church_prayers(self):
        titles = self.titles_for("levin", "church")
        self.assertIn("Own church request", titles)
        self.assertIn("Other church request", titles)

    def test_church_tab_excludes_own_group_prayer(self):
        titles = self.titles_for("levin", "church")
        self.assertNotIn("Own group request", titles)

    def test_church_tab_excludes_own_private_prayer(self):
        titles = self.titles_for("levin", "church")
        self.assertNotIn("Own private request", titles)

    def test_no_group_user_group_tab_hides_own_church_and_private(self):
        # A user with no small group authors church + private prayers; the group
        # tab must not fall back to showing their own unrelated prayers.
        PrayerRequest.objects.create(
            user=self.no_group_user,
            title="NoGroup church request",
            body="Please pray.",
            visibility=PrayerRequest.VISIBILITY_CHURCH,
        )
        PrayerRequest.objects.create(
            user=self.no_group_user,
            title="NoGroup private request",
            body="Please pray.",
            visibility=PrayerRequest.VISIBILITY_PRIVATE,
        )

        group_titles = self.titles_for("no_group", "group")
        self.assertNotIn("NoGroup church request", group_titles)
        self.assertNotIn("NoGroup private request", group_titles)

        # Their own content is still reachable through the "my" tab.
        my_titles = self.titles_for("no_group", "my")
        self.assertIn("NoGroup church request", my_titles)
        self.assertIn("NoGroup private request", my_titles)


class PrayerVisibilityLabelConsistencyTests(TestCase):
    """UI-H.1B: visibility labels use consistent audience-scope wording.

    ``Prayer Wall / 代祷墙`` names the module/page; the church-wide audience
    scope is labelled ``Church-wide / 全教会``. These unit-level checks pin the
    label vocabulary without depending on rendered-page whitespace.
    """

    def test_english_visibility_form_choices(self):
        choices = dict(localized_visibility_choices("en"))
        self.assertEqual(choices[PrayerRequest.VISIBILITY_PRIVATE], "Private")
        self.assertEqual(choices[PrayerRequest.VISIBILITY_GROUP], "My Group")
        self.assertEqual(choices[PrayerRequest.VISIBILITY_CHURCH], "Church-wide")
        # The module/page name must not double as the audience-scope label.
        self.assertNotIn("Prayer Wall", dict(choices).values())

    def test_chinese_visibility_form_choices(self):
        choices = dict(localized_visibility_choices("zh"))
        self.assertEqual(choices[PrayerRequest.VISIBILITY_PRIVATE], "私人")
        self.assertEqual(choices[PrayerRequest.VISIBILITY_GROUP], "我的小组")
        self.assertEqual(choices[PrayerRequest.VISIBILITY_CHURCH], "全教会")
        self.assertNotIn("代祷墙", dict(choices).values())

    def test_english_badge_labels(self):
        cases = {
            PrayerRequest.VISIBILITY_PRIVATE: "Private",
            PrayerRequest.VISIBILITY_GROUP: "My Group",
            PrayerRequest.VISIBILITY_CHURCH: "Church-wide",
        }
        for value, expected in cases.items():
            prayer = PrayerRequest(visibility=value)
            self.assertEqual(prayer_visibility_label(prayer, "en"), expected)
        church = PrayerRequest(visibility=PrayerRequest.VISIBILITY_CHURCH)
        self.assertNotEqual(prayer_visibility_label(church, "en"), "Prayer Wall")

    def test_chinese_badge_labels(self):
        cases = {
            PrayerRequest.VISIBILITY_PRIVATE: "私人",
            PrayerRequest.VISIBILITY_GROUP: "我的小组",
            PrayerRequest.VISIBILITY_CHURCH: "全教会",
        }
        for value, expected in cases.items():
            prayer = PrayerRequest(visibility=value)
            self.assertEqual(prayer_visibility_label(prayer, "zh"), expected)
        church = PrayerRequest(visibility=PrayerRequest.VISIBILITY_CHURCH)
        self.assertNotEqual(prayer_visibility_label(church, "zh"), "代祷墙")

    def test_stored_values_unchanged(self):
        # Choice *values* (stored in the DB) must stay exactly as before.
        self.assertEqual(
            [value for value, _ in localized_visibility_choices("en")],
            ["private", "group", "church"],
        )


class PrayerListLabelRenderingTests(TestCase):
    """UI-H.1B: rendered prayer list uses the consistent labels."""

    def setUp(self):
        self.group = SmallGroup.objects.create(name="Rainbow 4")
        self.user = User.objects.create_user(
            username="levin",
            password="TestPass123!",
        )
        self.user.profile.small_group = self.group
        self.user.profile.save()
        # A church-wide prayer so a card (and its scope badge) renders.
        PrayerRequest.objects.create(
            user=self.user,
            title="Church scope card",
            body="Please pray.",
            visibility=PrayerRequest.VISIBILITY_CHURCH,
        )

    def set_language(self, language):
        session = self.client.session
        session["language"] = language
        session.save()

    def get_church_tab(self):
        self.client.login(username="levin", password="TestPass123!")
        return self.client.get(
            reverse("prayer_list"),
            {"tab": "church", "status": "all"},
        )

    def test_english_tab_labels_title_and_badge(self):
        self.set_language("en")
        response = self.get_church_tab()
        # Module/page title.
        self.assertContains(response, "Prayer Wall")
        # Tabs.
        self.assertContains(response, "My Requests")
        self.assertContains(response, "My Group")
        self.assertContains(response, "Church-wide")
        # Card scope badge for the church-wide prayer.
        self.assertContains(response, "Church scope card")
        self.assertEqual(
            prayer_visibility_label(
                response.context["prayers"][0], "en"
            ),
            "Church-wide",
        )

    def test_chinese_tab_labels_title_and_badge(self):
        self.set_language("zh")
        response = self.get_church_tab()
        # Module/page title.
        self.assertContains(response, "代祷墙")
        # Tabs (我的 is the My Requests tab; 我的小组 group; 全教会 church-wide).
        self.assertContains(response, "我的小组")
        self.assertContains(response, "全教会")
        # English module name must not leak into the Chinese page.
        self.assertNotContains(response, "Prayer Wall")
        self.assertNotContains(response, "Church-wide")
        # Card scope badge for the church-wide prayer.
        self.assertEqual(
            prayer_visibility_label(
                response.context["prayers"][0], "zh"
            ),
            "全教会",
        )
