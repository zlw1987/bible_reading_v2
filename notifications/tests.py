from datetime import timedelta
from unittest.mock import patch

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.db import IntegrityError, transaction
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core.notification_delivery import NotificationPayload

from .context_processors import notification_context
from .models import Notification
from .services import persist_notification


User = get_user_model()


class NotificationModelAndPersistenceTests(TestCase):
    def setUp(self):
        self.recipient = User.objects.create_user(username="recipient")
        self.actor = User.objects.create_user(username="actor")

    def payload(self, **overrides):
        values = {
            "recipient": self.recipient,
            "source_module": "studies",
            "source_model_label": "studies.BibleStudyMeeting",
            "source_object_id": "42",
            "notification_type": "role.assigned",
            "title": "You have a Bible Study role",
            "body": "Open the meeting for details.",
            "target_url": "/studies/meetings/42/",
            "actor": self.actor,
            "dedupe_key": "studies:meeting:42:role:7:assigned",
            "severity": "info",
            "metadata": {"role": "facilitator"},
        }
        values.update(overrides)
        return NotificationPayload(**values)

    def test_notification_creation_has_optional_actor_and_unread_default(self):
        notification, created = persist_notification(self.payload())
        self.assertTrue(created)
        self.assertEqual(notification.recipient, self.recipient)
        self.assertEqual(notification.actor, self.actor)
        self.assertIsNone(notification.read_at)
        self.assertEqual(notification.source_object_id, "42")

    def test_actor_may_be_omitted(self):
        notification, created = persist_notification(
            self.payload(actor=None, dedupe_key="studies:meeting:42:no-actor")
        )
        self.assertTrue(created)
        self.assertIsNone(notification.actor)

    def test_recipient_is_database_required(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Notification.objects.create(
                    source_module="events",
                    notification_type="test",
                    title="Required recipient",
                    target_url="/events/",
                    dedupe_key="required-recipient",
                )

    def test_same_recipient_and_dedupe_key_cannot_duplicate(self):
        persist_notification(self.payload())
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Notification.objects.create(
                    recipient=self.recipient,
                    source_module="studies",
                    notification_type="role.assigned",
                    title="Duplicate",
                    target_url="/studies/meetings/42/",
                    dedupe_key="studies:meeting:42:role:7:assigned",
                )

    def test_same_dedupe_key_is_allowed_for_different_recipients(self):
        other = User.objects.create_user(username="other-recipient")
        first, _ = persist_notification(self.payload())
        second, _ = persist_notification(self.payload(recipient=other))
        self.assertNotEqual(first.pk, second.pk)
        self.assertEqual(Notification.objects.count(), 2)

    def test_repeated_delivery_reuses_row_without_overwriting_snapshot(self):
        original, created = persist_notification(self.payload())
        duplicate, duplicate_created = persist_notification(
            self.payload(
                title="Changed title",
                body="Changed body",
                target_url="/changed/",
                metadata={"private": "replacement"},
            )
        )
        original.refresh_from_db()
        self.assertTrue(created)
        self.assertFalse(duplicate_created)
        self.assertEqual(duplicate.pk, original.pk)
        self.assertEqual(original.title, "You have a Bible Study role")
        self.assertEqual(original.body, "Open the meeting for details.")
        self.assertEqual(original.target_url, "/studies/meetings/42/")
        self.assertEqual(original.metadata, {"role": "facilitator"})

    def test_metadata_default_is_not_shared(self):
        first = Notification(
            recipient=self.recipient,
            source_module="events",
            notification_type="one",
            title="One",
            target_url="/one/",
            dedupe_key="one",
        )
        second = Notification(
            recipient=self.recipient,
            source_module="events",
            notification_type="two",
            title="Two",
            target_url="/two/",
            dedupe_key="two",
        )
        first.metadata["changed"] = True
        self.assertEqual(second.metadata, {})

    def test_admin_is_registered(self):
        self.assertTrue(admin.site.is_registered(Notification))

    def test_constraint_and_indexes_are_explicit(self):
        self.assertIn(
            "notifications_unique_recipient_dedupe",
            {constraint.name for constraint in Notification._meta.constraints},
        )
        self.assertEqual(
            {index.name for index in Notification._meta.indexes},
            {
                "notify_rec_read_created_idx",
                "notify_source_snapshot_idx",
            },
        )


class NotificationCenterTests(TestCase):
    def setUp(self):
        self.recipient = User.objects.create_user(username="recipient")
        self.other = User.objects.create_user(username="other")
        self.staff = User.objects.create_user(username="staff", is_staff=True)

    def set_language(self, language):
        session = self.client.session
        session["language"] = language
        session.save()

    def create_notification(self, recipient=None, **overrides):
        recipient = recipient or self.recipient
        values = {
            "recipient": recipient,
            "source_module": "studies",
            "source_model_label": "studies.BibleStudyMeeting",
            "source_object_id": "42",
            "notification_type": "role.assigned",
            "title": "Meeting role update",
            "body": "Open the meeting for details.",
            "target_url": "/studies/meetings/42/",
            "dedupe_key": f"notification-{Notification.objects.count() + 1}",
        }
        values.update(overrides)
        return Notification.objects.create(**values)

    def test_center_requires_authentication(self):
        notification = self.create_notification()

        response = self.client.get(reverse("notification_center"))
        mark_response = self.client.post(
            reverse("mark_notification_read", args=[notification.id])
        )
        mark_all_response = self.client.post(reverse("mark_all_notifications_read"))

        self.assertRedirects(
            response,
            f"{reverse('login')}?next={reverse('notification_center')}",
        )
        self.assertEqual(mark_response.status_code, 302)
        self.assertEqual(mark_all_response.status_code, 302)
        notification.refresh_from_db()
        self.assertIsNone(notification.read_at)

    def test_center_is_recipient_scoped_for_member_and_staff(self):
        self.create_notification(title="Recipient only", body="Recipient body")
        self.create_notification(
            self.other,
            title="Other private title",
            body="Other private body",
            target_url="/private-other/",
        )
        self.set_language("en")
        self.client.force_login(self.recipient)

        response = self.client.get(reverse("notification_center"))

        self.assertContains(response, "Recipient only")
        self.assertNotContains(response, "Other private title")
        self.assertNotContains(response, "Other private body")
        self.assertNotContains(response, "/private-other/")

        self.client.force_login(self.staff)
        response = self.client.get(reverse("notification_center"))

        self.assertNotContains(response, "Recipient only")
        self.assertNotContains(response, "Other private title")

    def test_center_renders_newest_first_and_stored_target_without_source_lookup(self):
        older = self.create_notification(title="Older notification")
        newer = self.create_notification(title="Newer notification")
        Notification.objects.filter(pk=older.pk).update(
            created_at=timezone.now() - timedelta(days=1)
        )
        Notification.objects.filter(pk=newer.pk).update(created_at=timezone.now())
        self.set_language("en")
        self.client.force_login(self.recipient)

        response = self.client.get(reverse("notification_center"))
        content = response.content.decode()

        self.assertLess(content.index("Newer notification"), content.index("Older notification"))
        self.assertContains(response, "/studies/meetings/42/")
        self.assertContains(response, "Bible Study")

    def test_empty_state_is_localized(self):
        self.client.force_login(self.recipient)
        self.set_language("en")
        response = self.client.get(reverse("notification_center"))
        self.assertContains(response, "No notifications yet")

        self.set_language("zh")
        response = self.client.get(reverse("notification_center"))
        self.assertContains(response, "暂时没有通知")

    def test_read_and_unread_states_are_textually_distinct(self):
        self.create_notification(title="Unread row")
        self.create_notification(title="Read row", read_at=timezone.now())
        self.set_language("en")
        self.client.force_login(self.recipient)

        response = self.client.get(reverse("notification_center"))

        self.assertContains(response, "Unread")
        self.assertContains(response, "Read")
        self.assertContains(response, "Mark as read")

    def test_center_escapes_stored_snapshot_text(self):
        self.create_notification(
            title="<strong>Untrusted title</strong>",
            body="<script>alert('untrusted')</script>",
        )
        self.set_language("en")
        self.client.force_login(self.recipient)

        response = self.client.get(reverse("notification_center"))

        self.assertContains(response, "&lt;strong&gt;Untrusted title&lt;/strong&gt;")
        self.assertContains(response, "&lt;script&gt;alert(&#x27;untrusted&#x27;)&lt;/script&gt;")
        self.assertNotContains(response, "<strong>Untrusted title</strong>")
        self.assertNotContains(response, "<script>alert('untrusted')</script>")

    def test_source_label_uses_registered_bilingual_metadata_or_safe_fallback(self):
        self.create_notification(source_module="studies", title="Registered source")
        self.create_notification(
            source_module="historical_source",
            title="Historical source",
        )
        self.client.force_login(self.recipient)
        self.set_language("zh")

        response = self.client.get(reverse("notification_center"))

        self.assertContains(response, "查经")
        self.assertContains(response, "historical_source")

    def test_mark_one_read_is_post_only_idempotent_and_preserves_snapshot(self):
        notification = self.create_notification()
        original_snapshot = (
            notification.title,
            notification.body,
            notification.target_url,
            notification.source_module,
        )
        self.client.force_login(self.recipient)

        get_response = self.client.get(
            reverse("mark_notification_read", args=[notification.id])
        )
        self.assertEqual(get_response.status_code, 405)
        notification.refresh_from_db()
        self.assertIsNone(notification.read_at)

        response = self.client.post(
            reverse("mark_notification_read", args=[notification.id])
        )
        self.assertRedirects(response, reverse("notification_center"))
        notification.refresh_from_db()
        first_read_at = notification.read_at
        self.assertIsNotNone(first_read_at)
        self.assertEqual(
            (
                notification.title,
                notification.body,
                notification.target_url,
                notification.source_module,
            ),
            original_snapshot,
        )

        self.client.post(reverse("mark_notification_read", args=[notification.id]))
        notification.refresh_from_db()
        self.assertEqual(notification.read_at, first_read_at)

    def test_mark_one_read_fails_closed_for_another_recipient(self):
        notification = self.create_notification(self.other)
        self.client.force_login(self.recipient)

        response = self.client.post(
            reverse("mark_notification_read", args=[notification.id])
        )

        self.assertEqual(response.status_code, 404)
        notification.refresh_from_db()
        self.assertIsNone(notification.read_at)

    def test_mark_all_read_is_post_only_recipient_scoped_and_idempotent(self):
        unread_one = self.create_notification(title="Unread one")
        unread_two = self.create_notification(title="Unread two")
        earlier_read_at = timezone.now() - timedelta(hours=1)
        already_read = self.create_notification(
            title="Already read",
            read_at=earlier_read_at,
        )
        other_unread = self.create_notification(self.other, title="Other unread")
        self.client.force_login(self.recipient)

        get_response = self.client.get(reverse("mark_all_notifications_read"))
        self.assertEqual(get_response.status_code, 405)
        self.assertIsNone(unread_one.read_at)

        response = self.client.post(reverse("mark_all_notifications_read"))
        self.assertRedirects(response, reverse("notification_center"))
        unread_one.refresh_from_db()
        unread_two.refresh_from_db()
        already_read.refresh_from_db()
        other_unread.refresh_from_db()
        self.assertIsNotNone(unread_one.read_at)
        self.assertIsNotNone(unread_two.read_at)
        self.assertEqual(already_read.read_at, earlier_read_at)
        self.assertIsNone(other_unread.read_at)

        first_read_at = unread_one.read_at
        self.client.post(reverse("mark_all_notifications_read"))
        unread_one.refresh_from_db()
        self.assertEqual(unread_one.read_at, first_read_at)

    def test_authenticated_bell_is_localized_and_counts_only_own_unread_rows(self):
        self.create_notification(title="Unread one")
        self.create_notification(title="Unread two")
        self.create_notification(title="Read", read_at=timezone.now())
        self.create_notification(self.other, title="Other unread")
        self.client.force_login(self.recipient)
        self.set_language("en")

        response = self.client.get(reverse("profile"))

        self.assertContains(response, reverse("notification_center"))
        self.assertContains(response, 'aria-label="Notifications, 2 unread"')
        self.assertContains(response, 'class="notification-unread-badge"')
        self.assertContains(response, ">2</span>")

        self.set_language("zh")
        response = self.client.get(reverse("profile"))
        self.assertContains(response, 'aria-label="通知，2 条未读"')

    def test_zero_unread_keeps_bell_without_badge(self):
        self.create_notification(read_at=timezone.now())
        self.client.force_login(self.recipient)
        self.set_language("en")

        response = self.client.get(reverse("profile"))

        self.assertContains(response, reverse("notification_center"))
        self.assertContains(response, 'aria-label="Notifications"')
        self.assertNotContains(response, 'class="notification-unread-badge"')

    @override_settings(CMS_ENABLED_MODULES=[])
    def test_disabled_notifications_hide_bell_and_context_avoids_orm_query(self):
        request = RequestFactory().get("/")
        request.user = self.recipient
        with patch("notifications.context_processors.Notification.objects.filter") as filter_mock:
            context = notification_context(request)

        self.assertFalse(context["notifications_enabled"])
        self.assertEqual(context["unread_notification_count"], 0)
        filter_mock.assert_not_called()

        self.client.force_login(self.recipient)
        response = self.client.get(reverse("profile"))
        self.assertNotContains(response, reverse("notification_center"))

    def test_anonymous_context_avoids_notification_orm_query(self):
        request = RequestFactory().get("/")
        request.user = AnonymousUser()
        with patch("notifications.context_processors.Notification.objects.filter") as filter_mock:
            context = notification_context(request)

        self.assertTrue(context["notifications_enabled"])
        self.assertEqual(context["unread_notification_count"], 0)
        filter_mock.assert_not_called()
