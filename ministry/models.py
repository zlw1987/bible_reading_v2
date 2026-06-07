from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from events.models import ServiceEvent


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
        return self.role in {self.ROLE_LEAD, self.ROLE_COORDINATOR}


class TeamAssignment(models.Model):
    STATUS_SCHEDULED = "scheduled"
    STATUS_CONFIRMED = "confirmed"
    STATUS_PREPARED = "prepared"
    STATUS_COMPLETED = "completed"
    STATUS_CANCELLED = "cancelled"

    STATUS_CHOICES = [
        (STATUS_SCHEDULED, "Scheduled"),
        (STATUS_CONFIRMED, "Confirmed"),
        (STATUS_PREPARED, "Prepared"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_CANCELLED, "Cancelled"),
    ]

    service_event = models.ForeignKey(
        ServiceEvent,
        on_delete=models.CASCADE,
        related_name="team_assignments",
    )
    ministry_team = models.ForeignKey(
        MinistryTeam,
        on_delete=models.CASCADE,
        related_name="assignments",
    )
    assigned_members = models.ManyToManyField(
        TeamMembership,
        through="TeamAssignmentMember",
        related_name="assignments",
        blank=True,
    )
    status = models.CharField(
        max_length=32,
        choices=STATUS_CHOICES,
        default=STATUS_SCHEDULED,
    )
    notes = models.TextField(blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_team_assignments",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["service_event__start_datetime", "ministry_team__name"]
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["ministry_team"]),
            models.Index(fields=["service_event"]),
        ]

    def __str__(self):
        return f"{self.ministry_team} - {self.service_event}"

    def clean(self):
        errors = {}

        if not self.service_event_id:
            errors["service_event"] = "Service event is required."
        if not self.ministry_team_id:
            errors["ministry_team"] = "Ministry team is required."
        if self.status not in {
            self.STATUS_SCHEDULED,
            self.STATUS_CONFIRMED,
            self.STATUS_PREPARED,
            self.STATUS_COMPLETED,
            self.STATUS_CANCELLED,
        }:
            errors["status"] = "Invalid team assignment status."

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def is_cancelled(self):
        return self.status == self.STATUS_CANCELLED

    def active_assignment_members(self):
        return self.assignment_members.filter(
            membership__is_active=True,
        ).select_related("membership", "membership__user")

    def confirmed_count(self):
        return self.active_assignment_members().filter(confirmed_at__isnull=False).count()

    def total_assigned_count(self):
        return self.active_assignment_members().count()

    def all_members_confirmed(self):
        total = self.total_assigned_count()
        return total > 0 and self.confirmed_count() == total


class TeamAssignmentMember(models.Model):
    assignment = models.ForeignKey(
        TeamAssignment,
        on_delete=models.CASCADE,
        related_name="assignment_members",
    )
    membership = models.ForeignKey(
        TeamMembership,
        on_delete=models.CASCADE,
        related_name="assignment_memberships",
    )
    confirmed_at = models.DateTimeField(null=True, blank=True)
    confirmation_note = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["assignment", "membership__display_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["assignment", "membership"],
                name="unique_team_assignment_member",
            )
        ]

    def __str__(self):
        return f"{self.membership} - {self.assignment}"

    def clean(self):
        errors = {}

        if self.assignment_id and self.membership_id:
            if self.membership.team_id != self.assignment.ministry_team_id:
                errors["membership"] = "Assigned member must belong to the assignment team."
            if not self.membership.is_active:
                errors["membership"] = "Inactive memberships cannot be assigned."
            duplicate_query = TeamAssignmentMember.objects.filter(
                assignment_id=self.assignment_id,
                membership_id=self.membership_id,
            )
            if self.pk:
                duplicate_query = duplicate_query.exclude(pk=self.pk)
            if duplicate_query.exists():
                errors["membership"] = "This member is already assigned."

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def confirm(self, note=""):
        if not self.confirmed_at:
            self.confirmed_at = timezone.now()
        if note:
            self.confirmation_note = note
        self.save()
