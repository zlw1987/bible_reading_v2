from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from accounts.models import SmallGroup

class AccountProfileTests(TestCase):
    def setUp(self):
        self.group = SmallGroup.objects.create(name="Rainbow 4")
        self.other_group = SmallGroup.objects.create(name="Rainbow 5")

        self.user = User.objects.create_user(
            username="levin",
            email="",
            password="OldPass123!",
        )

        self.user.profile.small_group = self.group
        self.user.profile.preferred_language = "zh"
        self.user.profile.save()

    def test_profile_requires_login(self):
        response = self.client.get(reverse("profile"))

        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_profile_page_shows_user_info(self):
        self.client.login(username="levin", password="OldPass123!")

        response = self.client.get(reverse("profile"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "levin")
        self.assertContains(response, "Rainbow 4")

    def test_user_can_update_profile_without_email(self):
        self.client.login(username="levin", password="OldPass123!")

        response = self.client.post(
            reverse("profile"),
            {
                "email": "",
                "small_group": self.other_group.id,
                "preferred_language": "en",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("profile"))

        self.user.refresh_from_db()
        self.user.profile.refresh_from_db()

        self.assertEqual(self.user.email, "")
        self.assertEqual(self.user.profile.small_group, self.other_group)
        self.assertEqual(self.user.profile.preferred_language, "en")
        self.assertEqual(self.client.session["language"], "en")

    def test_user_can_update_email(self):
        self.client.login(username="levin", password="OldPass123!")

        response = self.client.post(
            reverse("profile"),
            {
                "email": "levin@example.com",
                "small_group": self.group.id,
                "preferred_language": "zh",
            },
        )

        self.assertEqual(response.status_code, 302)

        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "levin@example.com")

    def test_password_change_page_requires_login(self):
        response = self.client.get(reverse("password_change"))

        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_user_can_change_password(self):
        self.client.login(username="levin", password="OldPass123!")

        response = self.client.post(
            reverse("password_change"),
            {
                "old_password": "OldPass123!",
                "new_password1": "NewStrongPass123!",
                "new_password2": "NewStrongPass123!",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("password_change_done"))

        self.client.logout()

        login_success = self.client.login(
            username="levin",
            password="NewStrongPass123!",
        )

        self.assertTrue(login_success)

class StaffPasswordResetTests(TestCase):
    def setUp(self):
        self.group = SmallGroup.objects.create(name="Rainbow 4")

        self.staff = User.objects.create_user(
            username="staff",
            email="staff@example.com",
            password="StaffPass123!",
            is_staff=True,
        )

        self.user = User.objects.create_user(
            username="elder",
            email="",
            password="OldPass123!",
        )

        self.user.profile.small_group = self.group
        self.user.profile.save()

    def test_staff_user_list_requires_staff(self):
        self.client.login(username="elder", password="OldPass123!")

        response = self.client.get(reverse("staff_user_list"))

        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response.url)

    def test_staff_can_access_user_list(self):
        self.client.login(username="staff", password="StaffPass123!")

        response = self.client.get(reverse("staff_user_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "User Admin")
        self.assertContains(response, "elder")

    def test_staff_can_search_user_list(self):
        self.client.login(username="staff", password="StaffPass123!")

        response = self.client.get(reverse("staff_user_list"), {"q": "Rainbow"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "elder")

    def test_staff_can_reset_user_password(self):
        self.client.login(username="staff", password="StaffPass123!")

        response = self.client.post(
            reverse("staff_user_password_reset", args=[self.user.id]),
            {
                "new_password1": "TempPass123!",
                "new_password2": "TempPass123!",
                "require_password_change": "on",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("staff_user_list"))

        self.user.refresh_from_db()
        self.user.profile.refresh_from_db()

        self.assertTrue(self.user.check_password("TempPass123!"))
        self.assertTrue(self.user.profile.must_change_password)

    def test_user_with_must_change_password_is_redirected(self):
        self.user.profile.must_change_password = True
        self.user.profile.save()

        self.client.login(username="elder", password="OldPass123!")

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("password_change"))

    def test_password_change_clears_must_change_password_flag(self):
        self.user.set_password("TempPass123!")
        self.user.save()

        self.user.profile.must_change_password = True
        self.user.profile.save()

        self.client.login(username="elder", password="TempPass123!")

        response = self.client.post(
            reverse("password_change"),
            {
                "old_password": "TempPass123!",
                "new_password1": "NewStrongPass123!",
                "new_password2": "NewStrongPass123!",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("password_change_done"))

        self.user.profile.refresh_from_db()

        self.assertFalse(self.user.profile.must_change_password)

        self.client.logout()

        login_success = self.client.login(
            username="elder",
            password="NewStrongPass123!",
        )

        self.assertTrue(login_success)

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


