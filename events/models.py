from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from accounts.models import ChurchStructureUnit, District, SmallGroup
from accounts.permissions import CAP_MANAGE_SERVICE_EVENTS, has_capability


class ServiceEvent(models.Model):
    EVENT_SUNDAY_SERVICE = "sunday_service"
    EVENT_BIBLE_STUDY = "bible_study"
    EVENT_SPECIAL_MEETING = "special_meeting"
    EVENT_CONFERENCE = "conference"
    EVENT_GOSPEL_MUSIC = "gospel_music"
    EVENT_BAPTISM = "baptism"
    EVENT_OTHER = "other"

    EVENT_TYPE_CHOICES = [
        (EVENT_SUNDAY_SERVICE, "Sunday Service"),
        (EVENT_BIBLE_STUDY, "Bible Study"),
        (EVENT_SPECIAL_MEETING, "Special Meeting"),
        (EVENT_CONFERENCE, "Conference"),
        (EVENT_GOSPEL_MUSIC, "Gospel Music Night"),
        (EVENT_BAPTISM, "Baptism"),
        (EVENT_OTHER, "Other"),
    ]

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

    title = models.CharField(max_length=180)
    title_en = models.CharField(max_length=180, blank=True, default="")
    description = models.TextField(blank=True, default="")
    description_en = models.TextField(blank=True, default="")
    event_type = models.CharField(max_length=40, choices=EVENT_TYPE_CHOICES)
    start_datetime = models.DateTimeField()
    end_datetime = models.DateTimeField(null=True, blank=True)
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
        related_name="service_events",
    )
    small_group = models.ForeignKey(
        SmallGroup,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="service_events",
    )
    ministry_context = models.ForeignKey(
        "accounts.MinistryContext",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="service_events",
    )
    rotation_anchor_team = models.ForeignKey(
        "ministry.MinistryTeam",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="rotation_anchor_service_events",
    )
    required_teams = models.ManyToManyField(
        "ministry.MinistryTeam",
        through="ServiceEventRequiredTeam",
        related_name="required_service_events",
        blank=True,
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
        related_name="created_service_events",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-start_datetime"]
        indexes = [
            models.Index(fields=["event_type"]),
            models.Index(fields=["status"]),
            models.Index(fields=["start_datetime"]),
            models.Index(fields=["scope_type"]),
        ]

    def __str__(self):
        return self.title

    def clean(self):
        errors = {}

        if self.scope_type == self.SCOPE_GLOBAL:
            if self.district_id:
                errors["district"] = "Global events cannot be scoped to a district."
            if self.small_group_id:
                errors["small_group"] = "Global events cannot be scoped to a small group."
        elif self.scope_type == self.SCOPE_DISTRICT:
            if not self.district_id:
                errors["district"] = "District-scoped events require a district."
            if self.small_group_id:
                errors["small_group"] = "District-scoped events cannot also use a small group."
        elif self.scope_type == self.SCOPE_SMALL_GROUP:
            if not self.small_group_id:
                errors["small_group"] = "Small-group-scoped events require a small group."
            if self.district_id:
                errors["district"] = "Small-group-scoped events cannot also use a district."

        if self.end_datetime and self.start_datetime and self.end_datetime < self.start_datetime:
            errors["end_datetime"] = "End time cannot be before start time."

        if self.status not in {
            self.STATUS_DRAFT,
            self.STATUS_PUBLISHED,
            self.STATUS_COMPLETED,
            self.STATUS_CANCELLED,
        }:
            errors["status"] = "Invalid service event status."

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if self.status == self.STATUS_PUBLISHED and not self.published_at:
            self.published_at = timezone.now()
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

    def get_audience_scope_units(self):
        if not self.pk:
            return ChurchStructureUnit.objects.none()
        return ChurchStructureUnit.objects.filter(
            service_event_audience_scope_links__service_event=self
        )

    def can_be_managed_by(self, user):
        return (
            getattr(user, "is_staff", False)
            or getattr(user, "is_superuser", False)
            or has_capability(user, CAP_MANAGE_SERVICE_EVENTS)
        )

    def can_be_seen_by(self, user):
        if not getattr(user, "is_authenticated", False):
            return False

        if self.can_be_managed_by(user):
            return True

        if self.status in {self.STATUS_DRAFT, self.STATUS_CANCELLED}:
            return False

        if self.status not in {self.STATUS_PUBLISHED, self.STATUS_COMPLETED}:
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


class ServiceEventRequiredTeam(models.Model):
    service_event = models.ForeignKey(
        ServiceEvent,
        on_delete=models.CASCADE,
        related_name="required_team_links",
    )
    ministry_team = models.ForeignKey(
        "ministry.MinistryTeam",
        on_delete=models.PROTECT,
        related_name="required_event_links",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["service_event__start_datetime", "ministry_team__name"]
        constraints = [
            models.UniqueConstraint(
                fields=["service_event", "ministry_team"],
                name="unique_service_event_required_team",
            )
        ]
        indexes = [
            models.Index(fields=["service_event"]),
            models.Index(fields=["ministry_team"]),
        ]

    def __str__(self):
        return f"{self.ministry_team} required for {self.service_event}"


class ServiceEventAudienceScope(models.Model):
    service_event = models.ForeignKey(
        ServiceEvent,
        on_delete=models.CASCADE,
        related_name="audience_scope_links",
    )
    unit = models.ForeignKey(
        "accounts.ChurchStructureUnit",
        on_delete=models.PROTECT,
        related_name="service_event_audience_scope_links",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = [
            "service_event__start_datetime",
            "unit__parent_id",
            "unit__sort_order",
            "unit__code",
            "unit__name",
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["service_event", "unit"],
                name="unique_service_event_audience_scope",
            )
        ]
        indexes = [
            models.Index(fields=["service_event"]),
            models.Index(fields=["unit"]),
        ]

    def __str__(self):
        return f"{self.unit} audience scope for {self.service_event}"

    def clean(self):
        errors = {}

        if self.unit_id and not self.unit.is_active:
            errors["unit"] = "Audience scope must use an active church structure unit."

        if self.service_event_id and self.unit_id:
            selected_units = ChurchStructureUnit.objects.filter(
                service_event_audience_scope_links__service_event_id=self.service_event_id
            )
            if self.pk:
                selected_units = selected_units.exclude(
                    service_event_audience_scope_links__pk=self.pk
                )

            selected_unit_ids = set(selected_units.values_list("id", flat=True))
            ancestor_ids = {
                ancestor.id
                for ancestor in self.unit.get_ancestors()
                if ancestor.id is not None
            }

            if ancestor_ids & selected_unit_ids:
                errors["unit"] = (
                    "Audience scope cannot include both an ancestor and descendant "
                    "unit for the same service event."
                )
            else:
                for selected_unit in selected_units:
                    selected_ancestor_ids = {
                        ancestor.id
                        for ancestor in selected_unit.get_ancestors()
                        if ancestor.id is not None
                    }
                    if self.unit_id in selected_ancestor_ids:
                        errors["unit"] = (
                            "Audience scope cannot include both an ancestor and "
                            "descendant unit for the same service event."
                        )
                        break

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)
