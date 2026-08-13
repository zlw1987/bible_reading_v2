"""Notification-owned idempotent persistence sink (NOTIFY.1A)."""

from .models import Notification


def persist_notification(payload):
    """Persist ``payload`` once per recipient and logical dedupe key.

    ``get_or_create`` is backed by the model's database uniqueness constraint,
    so concurrent duplicate attempts converge on the existing row. Defaults
    are applied only on creation and never overwrite the original snapshot.
    """

    return Notification.objects.get_or_create(
        recipient=payload.recipient,
        dedupe_key=payload.dedupe_key,
        defaults={
            "source_module": payload.source_module,
            "source_model_label": payload.source_model_label,
            "source_object_id": payload.source_object_id,
            "notification_type": payload.notification_type,
            "title": payload.title,
            "body": payload.body,
            "target_url": payload.target_url,
            "actor": payload.actor,
            "severity": payload.severity,
            "metadata": dict(payload.metadata),
        },
    )
