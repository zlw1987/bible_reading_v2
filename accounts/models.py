from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class MinistryContext(models.Model):
    code = models.CharField(max_length=16, unique=True)
    name = models.CharField(max_length=120)
    name_en = models.CharField(max_length=120, blank=True)
    description = models.TextField(blank=True)
    description_en = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sort_order", "code"]

    def __str__(self):
        return f"{self.code} - {self.name}"

    def clean(self):
        if self.code:
            self.code = self.code.upper()

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class District(models.Model):
    name = models.CharField(max_length=120, unique=True)
    ministry_context = models.ForeignKey(
        MinistryContext,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="districts",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class SmallGroup(models.Model):
    name = models.CharField(max_length=80, unique=True)
    district = models.ForeignKey(
        District,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="small_groups",
    )
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class ChurchRoleAssignment(models.Model):
    ROLE_PASTOR = "pastor"
    ROLE_ELDER = "elder"
    ROLE_DEACON = "deacon"
    ROLE_DISTRICT_LEADER = "district_leader"
    ROLE_GROUP_LEADER = "group_leader"
    ROLE_COWORKER = "coworker"

    ROLE_CHOICES = [
        (ROLE_PASTOR, "Pastor"),
        (ROLE_ELDER, "Elder"),
        (ROLE_DEACON, "Deacon"),
        (ROLE_DISTRICT_LEADER, "District Leader"),
        (ROLE_GROUP_LEADER, "Group Leader"),
        (ROLE_COWORKER, "Coworker"),
    ]

    SCOPE_GLOBAL = "global"
    SCOPE_DISTRICT = "district"
    SCOPE_SMALL_GROUP = "small_group"

    SCOPE_CHOICES = [
        (SCOPE_GLOBAL, "Global"),
        (SCOPE_DISTRICT, "District"),
        (SCOPE_SMALL_GROUP, "Small Group"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="church_role_assignments",
    )
    role = models.CharField(max_length=32, choices=ROLE_CHOICES)
    scope_type = models.CharField(max_length=32, choices=SCOPE_CHOICES)
    district = models.ForeignKey(
        District,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="role_assignments",
    )
    small_group = models.ForeignKey(
        SmallGroup,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="role_assignments",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["user__username", "role", "scope_type"]

    def __str__(self):
        return f"{self.user} - {self.get_role_display()} ({self.get_scope_type_display()})"

    def clean(self):
        errors = {}

        if self.scope_type == self.SCOPE_GLOBAL:
            if self.district_id:
                errors["district"] = "Global roles cannot be scoped to a district."
            if self.small_group_id:
                errors["small_group"] = "Global roles cannot be scoped to a small group."
        elif self.scope_type == self.SCOPE_DISTRICT:
            if not self.district_id:
                errors["district"] = "District-scoped roles require a district."
            if self.small_group_id:
                errors["small_group"] = "District-scoped roles cannot also use a small group."
        elif self.scope_type == self.SCOPE_SMALL_GROUP:
            if not self.small_group_id:
                errors["small_group"] = "Small-group-scoped roles require a small group."
            if self.district_id:
                errors["district"] = "Small-group-scoped roles cannot also use a district."

        if self.user_id and self.role and self.scope_type and self.is_active:
            duplicate = ChurchRoleAssignment.objects.filter(
                user=self.user,
                role=self.role,
                scope_type=self.scope_type,
                district=self.district,
                small_group=self.small_group,
                is_active=True,
            )
            if self.pk:
                duplicate = duplicate.exclude(pk=self.pk)
            if duplicate.exists():
                errors["role"] = "This active role assignment already exists."

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class Profile(models.Model):
    LANGUAGE_CHOICES = [
        ("zh", "中文"),
        ("en", "English"),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
    )
    small_group = models.ForeignKey(
        SmallGroup,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="members",
    )
    preferred_language = models.CharField(
        max_length=2,
        choices=LANGUAGE_CHOICES,
        default="zh",
    )
    must_change_password = models.BooleanField(default=False)
    def __str__(self):
        return self.user.get_username()
