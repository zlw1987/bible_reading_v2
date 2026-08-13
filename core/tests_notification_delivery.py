from unittest.mock import Mock

from django.contrib.auth import get_user_model
from django.core.exceptions import ImproperlyConfigured
from django.db import transaction
from django.test import SimpleTestCase, TestCase, TransactionTestCase, override_settings

from notifications.models import Notification

from .notification_delivery import (
    NotificationPayload,
    _deliver_now,
    emit_notification,
    notification_sink_override_for_tests,
    register_notification_sink,
)


User = get_user_model()


def payload_for(recipient, **overrides):
    values = {
        "recipient": recipient,
        "source_module": "events",
        "notification_type": "assignment.created",
        "title": "Assignment updated",
        "body": "Open My Serving for details.",
        "target_url": "/my-serving/",
        "dedupe_key": "events:assignment:1:created",
    }
    values.update(overrides)
    return NotificationPayload(**values)


class NotificationSinkRegistrationTests(SimpleTestCase):
    def test_first_and_same_sink_registration_are_deterministic(self):
        sink = Mock()
        with notification_sink_override_for_tests(None):
            self.assertIs(register_notification_sink(sink), sink)
            self.assertIs(register_notification_sink(sink), sink)

    def test_different_second_sink_fails_loudly(self):
        first_sink = Mock()
        with notification_sink_override_for_tests(None):
            register_notification_sink(first_sink)
            with self.assertRaises(ImproperlyConfigured):
                register_notification_sink(Mock())

    def test_test_override_restores_prior_sink(self):
        original = Mock()
        replacement = Mock()
        with notification_sink_override_for_tests(original):
            with notification_sink_override_for_tests(replacement):
                _deliver_now(payload_for(object()), strict=True)
            _deliver_now(payload_for(object()), strict=True)
        replacement.assert_called_once()
        original.assert_called_once()

    def test_missing_sink_strict_raises_and_normal_logs(self):
        payload = payload_for(object())
        with notification_sink_override_for_tests(None):
            with self.assertRaises(ImproperlyConfigured):
                _deliver_now(payload, strict=True)
            with self.assertLogs("core.notification_delivery", level="ERROR"):
                self.assertIsNone(_deliver_now(payload))

    def test_sink_exception_strict_raises_and_normal_logs(self):
        def failing_sink(payload):
            raise RuntimeError("persistence failed")

        payload = payload_for(object())
        with notification_sink_override_for_tests(failing_sink):
            with self.assertRaisesRegex(RuntimeError, "persistence failed"):
                _deliver_now(payload, strict=True)
            with self.assertLogs("core.notification_delivery", level="ERROR"):
                self.assertIsNone(_deliver_now(payload))

    def test_payload_accepts_only_relative_internal_target_paths(self):
        valid_targets = (
            "/my-serving/",
            "/my-serving/?tab=all#assignment",
            "/activities/42/",
        )
        invalid_targets = (
            "https://example.com/private",
            "http://example.com/private",
            "//example.com/private",
            r"/\example.com/private",
            r"/\\example.com/private",
            "not-an-internal-path",
        )

        for target_url in valid_targets:
            with self.subTest(target_url=target_url):
                self.assertEqual(
                    payload_for(object(), target_url=target_url).target_url,
                    target_url,
                )
        for target_url in invalid_targets:
            with self.subTest(target_url=target_url):
                with self.assertRaisesRegex(ValueError, "relative internal path"):
                    payload_for(object(), target_url=target_url)
        with self.assertRaisesMessage(
            ValueError,
            "Notification target_url is required.",
        ):
            payload_for(object(), target_url="")

    def test_payload_copies_top_level_metadata(self):
        metadata = {"safe": "value"}
        payload = payload_for(object(), metadata=metadata)
        metadata["later"] = "change"
        self.assertEqual(dict(payload.metadata), {"safe": "value"})


class NotificationDeliveryTestCaseTests(TestCase):
    def setUp(self):
        self.recipient = User.objects.create_user(username="notify-recipient")

    @override_settings(CMS_ENABLED_MODULES=[])
    def test_disabled_notifications_is_safe_noop_without_callback_or_row(self):
        sink = Mock()
        with notification_sink_override_for_tests(sink):
            with self.captureOnCommitCallbacks(execute=True) as callbacks:
                scheduled = emit_notification(**payload_for(self.recipient).__dict__)
        self.assertFalse(scheduled)
        self.assertEqual(callbacks, [])
        sink.assert_not_called()
        self.assertFalse(Notification.objects.exists())

    @override_settings(CMS_ENABLED_MODULES=["notifications"])
    def test_payload_delivers_to_exactly_one_already_resolved_recipient(self):
        sink = Mock()
        with notification_sink_override_for_tests(sink):
            with self.assertNumQueries(0):
                with self.captureOnCommitCallbacks(execute=True):
                    emit_notification(**payload_for(self.recipient).__dict__)

        sink.assert_called_once()
        delivered = sink.call_args.args[0]
        self.assertIs(delivered.recipient, self.recipient)
        self.assertEqual(delivered.dedupe_key, "events:assignment:1:created")

    @override_settings(CMS_ENABLED_MODULES=["notifications"])
    def test_emit_snapshots_nested_metadata_before_on_commit_delivery(self):
        sink = Mock()
        metadata = {"context": {"roles": ["lead"]}}

        with notification_sink_override_for_tests(sink):
            with self.captureOnCommitCallbacks(execute=True):
                emit_notification(
                    recipient=self.recipient,
                    source_module="events",
                    notification_type="assignment.created",
                    title="Assignment updated",
                    body="Open My Serving for details.",
                    target_url="/my-serving/",
                    dedupe_key="events:assignment:nested-metadata",
                    metadata=metadata,
                )
                metadata["context"]["roles"].append("changed")
                metadata["context"]["new"] = True

        sink.assert_called_once()
        delivered = sink.call_args.args[0]
        self.assertEqual(
            dict(delivered.metadata),
            {"context": {"roles": ["lead"]}},
        )


@override_settings(CMS_ENABLED_MODULES=["notifications"])
class NotificationTransactionTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.recipient = User.objects.create_user(username="transaction-recipient")

    def emit(self, **overrides):
        payload = payload_for(self.recipient, **overrides)
        return emit_notification(**payload.__dict__)

    def test_enabled_delivery_runs_after_successful_commit(self):
        with transaction.atomic():
            self.assertTrue(self.emit())
            self.assertFalse(Notification.objects.exists())
        self.assertEqual(Notification.objects.count(), 1)

    def test_outside_transaction_uses_normal_immediate_on_commit_behavior(self):
        self.assertTrue(
            self.emit(dedupe_key="events:assignment:outside-transaction")
        )
        self.assertEqual(Notification.objects.count(), 1)

    def test_source_transaction_rollback_discards_delivery(self):
        with self.assertRaisesRegex(RuntimeError, "roll back source"):
            with transaction.atomic():
                self.emit()
                raise RuntimeError("roll back source")
        self.assertFalse(Notification.objects.exists())

    def test_normal_sink_failure_is_contained_after_source_commit(self):
        def failing_sink(payload):
            raise RuntimeError("database unavailable")

        with notification_sink_override_for_tests(failing_sink):
            with self.assertLogs("core.notification_delivery", level="ERROR"):
                with transaction.atomic():
                    User.objects.create_user(username="committed-source-write")
                    self.emit(dedupe_key="events:assignment:2:created")

        self.assertTrue(User.objects.filter(username="committed-source-write").exists())
        self.assertFalse(Notification.objects.exists())
