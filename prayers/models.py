from django.conf import settings
from django.db import models

from .structure_visibility import user_matches_group_prayer_snapshot


class PrayerRequest(models.Model):
    VISIBILITY_PRIVATE = "private"
    VISIBILITY_GROUP = "group"
    VISIBILITY_CHURCH = "church"

    VISIBILITY_CHOICES = [
        (VISIBILITY_PRIVATE, "Private"),
        (VISIBILITY_GROUP, "My Small Group"),
        (VISIBILITY_CHURCH, "Prayer Wall"),
    ]

    STATUS_OPEN = "open"
    STATUS_ANSWERED = "answered"
    STATUS_CLOSED = "closed"

    STATUS_CHOICES = [
        (STATUS_OPEN, "Open"),
        (STATUS_ANSWERED, "Answered"),
        (STATUS_CLOSED, "Closed"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="prayer_requests",
    )
    title = models.CharField(max_length=140)
    body = models.TextField(max_length=3000)

    visibility = models.CharField(
        max_length=20,
        choices=VISIBILITY_CHOICES,
        default=VISIBILITY_GROUP,
        db_index=True,
    )
    is_anonymous = models.BooleanField(default=False)

    structure_unit_at_post = models.ForeignKey(
        "accounts.ChurchStructureUnit",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="prayer_requests_at_post",
        help_text=(
            "Structure-native snapshot driving group prayer visibility."
        ),
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_OPEN,
        db_index=True,
    )
    answer_note = models.TextField(blank=True, default="")

    is_deleted = models.BooleanField(default=False)
    is_hidden = models.BooleanField(default=False)
    hidden_reason = models.CharField(max_length=255, blank=True, default="")
    hidden_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="hidden_prayer_requests",
    )
    hidden_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["visibility", "status"]),
            models.Index(fields=["user", "status"]),
            models.Index(fields=["structure_unit_at_post", "status"]),
        ]

    def __str__(self):
        return self.title

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
            return user_matches_group_prayer_snapshot(user, self)

        return False

    def can_be_managed_by(self, user):
        return user.is_authenticated and (self.user_id == user.id or user.is_staff)


class PrayerMark(models.Model):
    prayer_request = models.ForeignKey(
        PrayerRequest,
        on_delete=models.CASCADE,
        related_name="prayer_marks",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="prayer_marks",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["prayer_request", "user"],
                name="unique_prayer_mark_per_user",
            )
        ]

    def __str__(self):
        return f"{self.user} prayed for {self.prayer_request_id}"


class PrayerComment(models.Model):
    prayer_request = models.ForeignKey(
        PrayerRequest,
        on_delete=models.CASCADE,
        related_name="comments",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="prayer_comments",
    )
    body = models.TextField(max_length=2000)
    is_anonymous = models.BooleanField(default=False)
    is_deleted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.user}: {self.body[:30]}"

    def can_be_seen_by(self, user):
        return self.prayer_request.can_be_seen_by(user)


class PrayerReport(models.Model):
    STATUS_OPEN = "open"
    STATUS_REVIEWED = "reviewed"
    STATUS_DISMISSED = "dismissed"

    STATUS_CHOICES = [
        (STATUS_OPEN, "Open"),
        (STATUS_REVIEWED, "Reviewed"),
        (STATUS_DISMISSED, "Dismissed"),
    ]

    prayer_request = models.ForeignKey(
        PrayerRequest,
        on_delete=models.CASCADE,
        related_name="reports",
    )
    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="prayer_reports",
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
        related_name="reviewed_prayer_reports",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["prayer_request", "reporter"],
                name="unique_report_per_user_per_prayer",
            )
        ]

    def __str__(self):
        return f"Report by {self.reporter} on prayer {self.prayer_request_id}"
