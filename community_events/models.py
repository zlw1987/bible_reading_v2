from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from accounts.models import ChurchStructureUnit


class CommunityActivity(models.Model):
    STATUS_DRAFT = "draft"
    STATUS_PUBLISHED = "published"
    STATUS_CANCELLED = "cancelled"
    STATUS_COMPLETED = "completed"

    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_PUBLISHED, "Published"),
        (STATUS_CANCELLED, "Cancelled"),
        (STATUS_COMPLETED, "Completed"),
    ]

    title = models.CharField(max_length=180)
    title_en = models.CharField(max_length=180, blank=True, default="")
    description = models.TextField(blank=True, default="")
    description_en = models.TextField(blank=True, default="")
    organizer = models.CharField(max_length=180, blank=True, default="")
    start_datetime = models.DateTimeField()
    end_datetime = models.DateTimeField(null=True, blank=True)
    location = models.CharField(max_length=180, blank=True, default="")
    location_en = models.CharField(max_length=180, blank=True, default="")
    status = models.CharField(
        max_length=32,
        choices=STATUS_CHOICES,
        default=STATUS_DRAFT,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_community_activities",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-start_datetime"]
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["start_datetime"]),
        ]
        verbose_name = "Community Activity"
        verbose_name_plural = "Community Activities"

    def __str__(self):
        return self.title

    def clean(self):
        errors = {}
        if (
            self.start_datetime
            and self.end_datetime
            and self.end_datetime < self.start_datetime
        ):
            errors["end_datetime"] = "End time cannot be before start time."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def get_title(self, language="zh"):
        if language == "en" and self.title_en:
            return self.title_en
        return self.title

    def get_description(self, language="zh"):
        if language == "en":
            return self.description_en or self.description
        return self.description

    def get_location(self, language="zh"):
        if language == "en" and self.location_en:
            return self.location_en
        return self.location

    def get_audience_scope_units(self):
        if not self.pk:
            return ChurchStructureUnit.objects.none()
        return ChurchStructureUnit.objects.filter(
            community_activity_audience_scopes__activity_id=self.pk
        ).distinct()

    def can_be_managed_by(self, user):
        return bool(
            getattr(user, "is_authenticated", False)
            and (
                getattr(user, "is_staff", False)
                or getattr(user, "is_superuser", False)
            )
        )

    def can_be_seen_by(self, user):
        if not self.pk or not getattr(user, "is_authenticated", False):
            return False

        if self.can_be_managed_by(user):
            return True

        from .visibility import visible_community_activities_for

        return visible_community_activities_for(
            user,
            queryset=type(self).objects.filter(pk=self.pk),
        ).exists()


class CommunityActivityAudienceScope(models.Model):
    activity = models.ForeignKey(
        CommunityActivity,
        on_delete=models.CASCADE,
        related_name="audience_scope_links",
    )
    structure_unit = models.ForeignKey(
        ChurchStructureUnit,
        on_delete=models.PROTECT,
        related_name="community_activity_audience_scopes",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = [
            "activity__start_datetime",
            "structure_unit__parent_id",
            "structure_unit__sort_order",
            "structure_unit__code",
            "structure_unit__name",
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["activity", "structure_unit"],
                name="unique_community_activity_audience_scope",
            )
        ]
        indexes = [
            models.Index(fields=["activity"]),
            models.Index(fields=["structure_unit"]),
        ]

    def __str__(self):
        return f"{self.structure_unit} audience scope for {self.activity}"

    def clean(self):
        errors = {}

        if self.structure_unit_id and not self.structure_unit.is_active:
            errors["structure_unit"] = (
                "Audience scope must use an active church structure unit."
            )

        if self.activity_id and self.structure_unit_id:
            selected_units = ChurchStructureUnit.objects.filter(
                community_activity_audience_scopes__activity_id=self.activity_id
            )
            if self.pk:
                selected_units = selected_units.exclude(
                    community_activity_audience_scopes__pk=self.pk
                )

            selected_unit_ids = set(selected_units.values_list("id", flat=True))
            ancestor_ids = {
                ancestor.id
                for ancestor in self.structure_unit.get_ancestors()
                if ancestor.id is not None
            }

            if ancestor_ids & selected_unit_ids:
                errors["structure_unit"] = (
                    "Audience scope cannot include both an ancestor and descendant "
                    "unit for the same community activity."
                )
            else:
                for selected_unit in selected_units:
                    selected_ancestor_ids = {
                        ancestor.id
                        for ancestor in selected_unit.get_ancestors()
                        if ancestor.id is not None
                    }
                    if self.structure_unit_id in selected_ancestor_ids:
                        errors["structure_unit"] = (
                            "Audience scope cannot include both an ancestor and "
                            "descendant unit for the same community activity."
                        )
                        break

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)
