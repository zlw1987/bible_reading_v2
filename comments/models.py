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
        (VISIBILITY_CHURCH, "Reflection Wall"),
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
    structure_unit_at_post = models.ForeignKey(
        "accounts.ChurchStructureUnit",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reflection_comments_at_post",
        help_text=(
            "Structure snapshot driving group reflection visibility since "
            "CS-CORE.4G.2: ordinary group read visibility matches this snapshot "
            "unit against the viewer's active primary ChurchStructureMembership. "
            "small_group_at_post remains legacy compatibility / staff-display / "
            "write-path data."
        ),
    )

    body = models.TextField(max_length=3000)
    created_at = models.DateTimeField(auto_now_add=True)
    is_deleted = models.BooleanField(default=False)
    is_hidden = models.BooleanField(default=False)
    hidden_reason = models.CharField(max_length=255, blank=True, default="")
    hidden_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="hidden_reflection_comments",
    )
    hidden_at = models.DateTimeField(null=True, blank=True)

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

        if self.is_deleted:
            return self.user_id == user.id or user.is_staff

        if self.is_hidden:
            return self.user_id == user.id or user.is_staff

        if self.user_id == user.id:
            return True

        if user.is_staff:
            return True

        if self.visibility == self.VISIBILITY_CHURCH:
            return True

        if self.visibility == self.VISIBILITY_GROUP:
            # CS-CORE.4G.2: ordinary group visibility is structure-native. The
            # post must carry a valid structure_unit_at_post snapshot and the
            # viewer must have a single active primary ChurchStructureMembership
            # in that unit or a descendant. Profile.small_group /
            # small_group_at_post no longer grant ordinary group visibility.
            from comments.reflection_visibility import (
                user_matches_group_reflection_snapshot,
            )

            return user_matches_group_reflection_snapshot(user, self)

        return False

class ReflectionReport(models.Model):
    STATUS_OPEN = "open"
    STATUS_REVIEWED = "reviewed"
    STATUS_DISMISSED = "dismissed"

    STATUS_CHOICES = [
        (STATUS_OPEN, "Open"),
        (STATUS_REVIEWED, "Reviewed"),
        (STATUS_DISMISSED, "Dismissed"),
    ]

    comment = models.ForeignKey(
        ReflectionComment,
        on_delete=models.CASCADE,
        related_name="reports",
    )
    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="reflection_reports",
    )
    reason = models.TextField(max_length=1000, blank=True)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_OPEN,
        db_index=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_reflection_reports",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["comment", "reporter"],
                name="unique_report_per_user_per_reflection",
            )
        ]

    def __str__(self):
        return f"Report by {self.reporter} on comment {self.comment_id}"
