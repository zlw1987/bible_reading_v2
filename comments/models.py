from django.conf import settings
from django.db import models

from reading.models import ActivePlan, ReadingPlanDay


class ReflectionComment(models.Model):
    VISIBILITY_PRIVATE = "private"
    VISIBILITY_GROUP = "group"
    VISIBILITY_CHURCH = "church"

    VISIBILITY_CHOICES = [
        (VISIBILITY_PRIVATE, "Private"),
        (VISIBILITY_GROUP, "My Small Group"),
        (VISIBILITY_CHURCH, "Passage Wall"),
    ]

    active_plan = models.ForeignKey(
        ActivePlan,
        on_delete=models.CASCADE,
        related_name="reflection_comments",
        null=True,
        blank=True,
    )
    plan_day = models.ForeignKey(
        ReadingPlanDay,
        on_delete=models.CASCADE,
        related_name="comments",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="reflection_comments",
    )
    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="replies",
    )

    scripture_ref_key = models.CharField(
        max_length=120,
        db_index=True,
        blank=True,
        default="",
    )
    scripture_display_zh = models.CharField(
        max_length=160,
        blank=True,
        default="",
    )
    scripture_display_en = models.CharField(
        max_length=160,
        blank=True,
        default="",
    )

    visibility = models.CharField(
        max_length=20,
        choices=VISIBILITY_CHOICES,
        default=VISIBILITY_GROUP,
        db_index=True,
    )
    is_anonymous = models.BooleanField(default=False)

    small_group_at_post = models.ForeignKey(
        "accounts.SmallGroup",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reflection_comments",
    )

    body = models.TextField(max_length=3000)
    created_at = models.DateTimeField(auto_now_add=True)
    is_deleted = models.BooleanField(default=False)

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["active_plan", "plan_day", "scripture_ref_key"]),
            models.Index(fields=["scripture_ref_key", "visibility"]),
            models.Index(fields=["user", "scripture_ref_key"]),
            models.Index(fields=["small_group_at_post", "scripture_ref_key"]),
        ]

    def __str__(self):
        return f"{self.user}: {self.body[:30]}"

    def can_be_seen_by(self, user):
        if not user.is_authenticated:
            return False

        if self.user_id == user.id:
            return True

        if user.is_staff:
            return True

        if self.visibility == self.VISIBILITY_CHURCH:
            return True

        if self.visibility == self.VISIBILITY_GROUP:
            user_group = getattr(getattr(user, "profile", None), "small_group", None)
            return bool(user_group and self.small_group_at_post_id == user_group.id)

        return False