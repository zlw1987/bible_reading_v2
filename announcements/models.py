from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from accounts.models import ChurchStructureUnit


class Announcement(models.Model):
    STATUS_DRAFT = "draft"
    STATUS_PUBLISHED = "published"
    STATUS_ARCHIVED = "archived"

    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_PUBLISHED, "Published"),
        (STATUS_ARCHIVED, "Archived"),
    ]

    PRIORITY_NORMAL = "normal"
    PRIORITY_IMPORTANT = "important"

    PRIORITY_CHOICES = [
        (PRIORITY_NORMAL, "Normal"),
        (PRIORITY_IMPORTANT, "Important"),
    ]

    title = models.CharField(max_length=180)
    title_en = models.CharField(max_length=180, blank=True, default="")
    body = models.TextField()
    body_en = models.TextField(blank=True, default="")
    status = models.CharField(
        max_length=16,
        choices=STATUS_CHOICES,
        default=STATUS_DRAFT,
    )
    priority = models.CharField(
        max_length=16,
        choices=PRIORITY_CHOICES,
        default=PRIORITY_NORMAL,
    )
    publish_start = models.DateTimeField()
    publish_end = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_announcements",
    )
    published_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="published_announcements",
    )
    published_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-publish_start", "-created_at"]
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["publish_start"]),
            models.Index(fields=["publish_end"]),
        ]
        verbose_name = "Official Announcement"
        verbose_name_plural = "Official Announcements"

    def __str__(self):
        return self.title

    def clean(self):
        errors = {}
        if (
            self.publish_start
            and self.publish_end
            and self.publish_end <= self.publish_start
        ):
            errors["publish_end"] = "Publish end must be later than publish start."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def get_title(self, language="zh"):
        if language == "en":
            return self.title_en or self.title
        return self.title

    def get_body(self, language="zh"):
        if language == "en":
            return self.body_en or self.body
        return self.body


class AnnouncementAudienceScope(models.Model):
    announcement = models.ForeignKey(
        Announcement,
        on_delete=models.CASCADE,
        related_name="audience_scope_links",
    )
    structure_unit = models.ForeignKey(
        ChurchStructureUnit,
        on_delete=models.PROTECT,
        related_name="announcement_audience_scopes",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = [
            "announcement__publish_start",
            "structure_unit__parent_id",
            "structure_unit__sort_order",
            "structure_unit__code",
            "structure_unit__name",
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["announcement", "structure_unit"],
                name="unique_announcement_audience_scope",
            )
        ]
        indexes = [
            models.Index(fields=["announcement"]),
            models.Index(fields=["structure_unit"]),
        ]
        verbose_name = "Announcement Audience Scope"
        verbose_name_plural = "Announcement Audience Scopes"

    def __str__(self):
        return f"{self.structure_unit} audience scope for {self.announcement}"

    def clean(self):
        if self.structure_unit_id and not self.structure_unit.is_active:
            raise ValidationError(
                {
                    "structure_unit": (
                        "Audience scope must use an active church structure unit."
                    )
                }
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)
