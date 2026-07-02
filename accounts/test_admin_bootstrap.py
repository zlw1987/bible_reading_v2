from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from run_create_admin_godaddy import (
    BootstrapError,
    bootstrap_superuser,
    reject_default_like_password,
    resolve_password,
    resolve_username,
)


class AdminBootstrapInputTests(SimpleTestCase):
    def test_username_is_required(self):
        with self.assertRaises(BootstrapError):
            resolve_username(None, {})

    def test_noninteractive_password_requires_environment_value(self):
        with self.assertRaises(BootstrapError):
            resolve_password({}, is_interactive=False)

    def test_default_like_password_is_rejected(self):
        with self.assertRaises(BootstrapError):
            reject_default_like_password(
                "ChangeThisPasswordSoon987!",
                "deployment-admin",
            )

    def test_prompt_confirmation_must_match(self):
        prompts = iter(["Strong-Quartz-Phrase-4827!", "different"])

        with self.assertRaises(BootstrapError):
            resolve_password(
                {},
                is_interactive=True,
                password_prompt=lambda _label: next(prompts),
            )


class AdminBootstrapDatabaseTests(TestCase):
    password = "Strong-Quartz-Phrase-4827!"

    def test_create_superuser_uses_supplied_credentials(self):
        User = get_user_model()

        user, created = bootstrap_superuser(
            User,
            username="deployment-admin",
            email="deployment-admin@example.test",
            password=self.password,
        )

        self.assertTrue(created)
        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)
        self.assertTrue(user.is_active)
        self.assertTrue(user.check_password(self.password))

    def test_existing_user_requires_explicit_update_flag(self):
        User = get_user_model()
        User.objects.create_user(
            username="existing-admin",
            password="Existing-Quartz-Phrase-5938!",
        )

        with self.assertRaises(BootstrapError):
            bootstrap_superuser(
                User,
                username="existing-admin",
                email="",
                password=self.password,
            )

    def test_explicit_update_resets_existing_user_securely(self):
        User = get_user_model()
        existing = User.objects.create_user(
            username="existing-admin",
            password="Existing-Quartz-Phrase-5938!",
            is_active=False,
        )

        user, created = bootstrap_superuser(
            User,
            username="existing-admin",
            email="updated-admin@example.test",
            password=self.password,
            update_existing=True,
        )

        self.assertFalse(created)
        self.assertEqual(user.pk, existing.pk)
        self.assertEqual(user.email, "updated-admin@example.test")
        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)
        self.assertTrue(user.is_active)
        self.assertTrue(user.check_password(self.password))
