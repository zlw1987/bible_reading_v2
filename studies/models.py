from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from accounts.models import District, SmallGroup
from accounts.permissions import (
    CAP_MANAGE_BIBLE_STUDIES,
    CAP_PUBLISH_BIBLE_STUDY_GUIDES,
    has_capability,
)


class BibleStudySeries(models.Model):
    title = models.CharField(max_length=160)
    title_en = models.CharField(max_length=160, blank=True, default="")
    description = models.TextField(blank=True, default="")
    description_en = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["title"]

    def __str__(self):
        return self.title

    def get_title(self, language="zh"):
        if language == "en" and self.title_en:
            return self.title_en
        return self.title

    def get_description(self, language="zh"):
        if language == "en" and self.description_en:
            return self.description_en or self.description
        return self.description


class BibleStudySession(models.Model):
    SCOPE_GLOBAL = "global"
    SCOPE_DISTRICT = "district"
    SCOPE_SMALL_GROUP = "small_group"

    SCOPE_CHOICES = [
        (SCOPE_GLOBAL, "Global"),
        (SCOPE_DISTRICT, "District"),
        (SCOPE_SMALL_GROUP, "Small Group"),
    ]

    STATUS_DRAFT = "draft"
    STATUS_PUBLISHED = "published"
    STATUS_COMPLETED = "completed"
    STATUS_CANCELLED = "cancelled"

    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_PUBLISHED, "Published"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_CANCELLED, "Cancelled"),
    ]

    series = models.ForeignKey(
        BibleStudySeries,
        on_delete=models.CASCADE,
        related_name="sessions",
    )
    title = models.CharField(max_length=180)
    title_en = models.CharField(max_length=180, blank=True, default="")
    scripture_reference = models.CharField(max_length=180, blank=True, default="")
    prestudy_datetime = models.DateTimeField(null=True, blank=True)
    study_datetime = models.DateTimeField()
    location = models.CharField(max_length=180, blank=True, default="")
    meeting_link = models.URLField(max_length=500, blank=True, default="")
    scope_type = models.CharField(
        max_length=32,
        choices=SCOPE_CHOICES,
        default=SCOPE_GLOBAL,
    )
    district = models.ForeignKey(
        District,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="bible_study_sessions",
    )
    small_group = models.ForeignKey(
        SmallGroup,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="bible_study_sessions",
    )
    status = models.CharField(
        max_length=32,
        choices=STATUS_CHOICES,
        default=STATUS_DRAFT,
    )
    published_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_bible_study_sessions",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-study_datetime"]

    def __str__(self):
        return self.title

    def clean(self):
        errors = {}

        if self.scope_type == self.SCOPE_GLOBAL:
            if self.district_id:
                errors["district"] = "Global sessions cannot be scoped to a district."
            if self.small_group_id:
                errors["small_group"] = "Global sessions cannot be scoped to a small group."
        elif self.scope_type == self.SCOPE_DISTRICT:
            if not self.district_id:
                errors["district"] = "District-scoped sessions require a district."
            if self.small_group_id:
                errors["small_group"] = "District-scoped sessions cannot also use a small group."
        elif self.scope_type == self.SCOPE_SMALL_GROUP:
            if not self.small_group_id:
                errors["small_group"] = "Small-group-scoped sessions require a small group."
            if self.district_id:
                errors["district"] = "Small-group-scoped sessions cannot also use a district."

        if self.status not in {
            self.STATUS_DRAFT,
            self.STATUS_PUBLISHED,
            self.STATUS_COMPLETED,
            self.STATUS_CANCELLED,
        }:
            errors["status"] = "Invalid Bible study session status."

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if self.status == self.STATUS_PUBLISHED and not self.published_at:
            self.published_at = timezone.now()
        self.full_clean()
        return super().save(*args, **kwargs)

    @property
    def is_published(self):
        return self.status in {self.STATUS_PUBLISHED, self.STATUS_COMPLETED}

    def get_title(self, language="zh"):
        if language == "en" and self.title_en:
            return self.title_en
        return self.title

    def can_be_seen_by(self, user):
        if not getattr(user, "is_authenticated", False):
            return False

        if (
            getattr(user, "is_staff", False)
            or getattr(user, "is_superuser", False)
            or has_capability(user, CAP_MANAGE_BIBLE_STUDIES)
            or has_capability(user, CAP_PUBLISH_BIBLE_STUDY_GUIDES)
        ):
            return True

        if self.status == self.STATUS_CANCELLED:
            return False

        if not self.is_published:
            return False

        if self.scope_type == self.SCOPE_GLOBAL:
            return True

        profile = getattr(user, "profile", None)
        user_group = getattr(profile, "small_group", None)
        if not user_group:
            return False

        if self.scope_type == self.SCOPE_DISTRICT:
            return bool(
                self.district_id
                and user_group.district_id
                and self.district_id == user_group.district_id
            )

        if self.scope_type == self.SCOPE_SMALL_GROUP:
            return bool(self.small_group_id and self.small_group_id == user_group.id)

        return False


class BibleStudyGuide(models.Model):
    session = models.OneToOneField(
        BibleStudySession,
        on_delete=models.CASCADE,
        related_name="guide",
    )
    guide_body = models.TextField(blank=True, default="")
    guide_body_en = models.TextField(blank=True, default="")
    discussion_questions = models.TextField(blank=True, default="")
    discussion_questions_en = models.TextField(blank=True, default="")
    prestudy_notes = models.TextField(blank=True, default="")
    prestudy_notes_en = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Guide for {self.session}"

    def get_guide_body(self, language="zh"):
        if language == "en":
            return self.guide_body_en or self.guide_body
        return self.guide_body

    def get_discussion_questions(self, language="zh"):
        if language == "en":
            return self.discussion_questions_en or self.discussion_questions
        return self.discussion_questions

    def get_prestudy_notes(self, language="zh"):
        if language == "en":
            return self.prestudy_notes_en or self.prestudy_notes
        return self.prestudy_notes
