from django.conf import settings
from django.db import models


class Notification(models.Model):
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    source_module = models.CharField(max_length=100)
    source_model_label = models.CharField(max_length=255, blank=True)
    source_object_id = models.CharField(max_length=255, blank=True)
    notification_type = models.CharField(max_length=100)
    title = models.CharField(max_length=200)
    body = models.TextField(blank=True)
    target_url = models.CharField(
        max_length=500,
        help_text=(
            "Internal navigation path only; the destination still enforces its "
            "own permissions."
        ),
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="acted_notifications",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)
    dedupe_key = models.CharField(max_length=255)
    severity = models.CharField(max_length=20, default="info")
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("-created_at", "-pk")
        constraints = [
            models.UniqueConstraint(
                fields=("recipient", "dedupe_key"),
                name="notifications_unique_recipient_dedupe",
            )
        ]
        indexes = [
            models.Index(
                fields=("recipient", "read_at", "-created_at"),
                name="notify_rec_read_created_idx",
            ),
            models.Index(
                fields=("source_module", "source_model_label", "source_object_id"),
                name="notify_source_snapshot_idx",
            ),
        ]

    def __str__(self):
        return f"{self.recipient}: {self.title}"
