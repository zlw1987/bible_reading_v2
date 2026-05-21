from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from accounts.models import SmallGroup
from prayers.models import PrayerMark, PrayerRequest


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
        self.assertNotContains(response, "Prayer title")
        self.assertNotContains(response, "Share your prayer request")
        self.assertNotContains(response, "Post anonymously")
        self.assertNotContains(response, "Visibility")
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
