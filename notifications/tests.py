from django.contrib import admin
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase

from core.notification_delivery import NotificationPayload

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
