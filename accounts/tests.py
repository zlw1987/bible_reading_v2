from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from accounts.models import SmallGroup


class AccountSignupLanguageTests(TestCase):
    def setUp(self):
        self.group = SmallGroup.objects.create(name="Rainbow 4")

    def test_signup_does_not_require_email(self):
        response = self.client.post(
            reverse("signup"),
            {
                "username": "elder_user",
                "email": "",
                "small_group": self.group.id,
                "password1": "StrongPass123!",
                "password2": "StrongPass123!",
            },
        )

        self.assertEqual(response.status_code, 302)

        user = User.objects.get(username="elder_user")
        self.assertEqual(user.email, "")
        self.assertEqual(user.profile.small_group, self.group)

    def test_language_switch_updates_session(self):
        response = self.client.post(
            reverse("change_language"),
            {
                "language": "en",
                "next": reverse("login"),
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("login"))
        self.assertEqual(self.client.session["language"], "en")

    def test_signup_page_can_render_chinese_labels(self):
        self.client.post(
            reverse("change_language"),
            {
                "language": "zh",
                "next": reverse("signup"),
            },
        )

        response = self.client.get(reverse("signup"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Email（可选）")
        self.assertContains(response, "小组")

    def test_signup_page_can_render_english_labels(self):
        self.client.post(
            reverse("change_language"),
            {
                "language": "en",
                "next": reverse("signup"),
            },
        )

        response = self.client.get(reverse("signup"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Email (optional)")
        self.assertContains(response, "Small group")
