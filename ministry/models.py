from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class MinistryTeam(models.Model):
    name = models.CharField(max_length=160)
    name_en = models.CharField(max_length=160, blank=True, default="")
    description = models.TextField(blank=True, default="")
    description_en = models.TextField(blank=True, default="")
    email_alias = models.CharField(max_length=180, blank=True, default="")
    playbook_link = models.URLField(max_length=500, blank=True, default="")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        indexes = [
            models.Index(fields=["is_active"]),
        ]

    def __str__(self):
        return self.name

    def get_name(self, language="zh"):
        if language == "en" and self.name_en:
            return self.name_en
        return self.name

    def get_description(self, language="zh"):
        if language == "en":
            return self.description_en or self.description
        return self.description


class TeamMembership(models.Model):
    ROLE_MEMBER = "member"
    ROLE_LEAD = "lead"
    ROLE_COORDINATOR = "coordinator"

    ROLE_CHOICES = [
        (ROLE_MEMBER, "Member"),
        (ROLE_LEAD, "Lead"),
        (ROLE_COORDINATOR, "Coordinator"),
    ]

    team = models.ForeignKey(
        MinistryTeam,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ministry_memberships",
    )
    display_name = models.CharField(max_length=120, blank=True, default="")
    email = models.EmailField(blank=True, default="")
    role = models.CharField(max_length=32, choices=ROLE_CHOICES, default=ROLE_MEMBER)
    skill_level = models.CharField(max_length=80, blank=True, default="")
    can_lead = models.BooleanField(default=False)
    notes = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["team", "role", "display_name"]
        indexes = [
            models.Index(fields=["team"]),
            models.Index(fields=["user"]),
            models.Index(fields=["is_active"]),
            models.Index(fields=["role"]),
        ]

    def __str__(self):
        return f"{self.get_display_name()} - {self.team}"

    def clean(self):
        errors = {}

        if not self.user_id and not self.display_name.strip():
            errors["display_name"] = "Display name is required when no user is linked."

        if self.user_id and self.team_id and self.is_active:
            duplicate_query = TeamMembership.objects.filter(
                team_id=self.team_id,
                user_id=self.user_id,
                is_active=True,
            )
            if self.pk:
                duplicate_query = duplicate_query.exclude(pk=self.pk)
            if duplicate_query.exists():
                errors["user"] = "This user already has an active membership in this team."

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def get_display_name(self):
        if self.display_name:
            return self.display_name
        if self.user:
            full_name = self.user.get_full_name()
            if full_name:
                return full_name
            return self.user.username
        return self.email

    def is_leadership(self):
        return self.role in {self.ROLE_LEAD, self.ROLE_COORDINATOR} or self.can_lead
