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
    church_structure_unit = models.ForeignKey(
        "ChurchStructureUnit",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="legacy_ministry_contexts",
        help_text=(
            "Optional bridge to the future ChurchStructureUnit tree. "
            "Not required and does not change current runtime behavior."
        ),
    )
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
    church_structure_unit = models.ForeignKey(
        "ChurchStructureUnit",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="legacy_districts",
        help_text=(
            "Optional bridge to the future ChurchStructureUnit tree. "
            "Not required and does not change current runtime behavior."
        ),
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
    church_structure_unit = models.ForeignKey(
        "ChurchStructureUnit",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="legacy_small_groups",
        help_text=(
            "Optional bridge to the future ChurchStructureUnit tree. "
            "Not required and does not change current runtime behavior."
        ),
    )
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class ChurchStructureUnit(models.Model):
    UNIT_ROOT = "root"
    UNIT_MINISTRY_CONTEXT = "ministry_context"
    UNIT_DISTRICT = "district"
    UNIT_SMALL_GROUP = "small_group"
    UNIT_FELLOWSHIP = "fellowship"
    UNIT_DEPARTMENT = "department"
    UNIT_CUSTOM = "custom"

    UNIT_TYPE_CHOICES = [
        (UNIT_ROOT, "Root"),
        (UNIT_MINISTRY_CONTEXT, "Ministry Context"),
        (UNIT_DISTRICT, "District"),
        (UNIT_SMALL_GROUP, "Small Group"),
        (UNIT_FELLOWSHIP, "Fellowship"),
        (UNIT_DEPARTMENT, "Department"),
        (UNIT_CUSTOM, "Custom"),
    ]

    parent = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="children",
    )
    unit_type = models.CharField(max_length=32, choices=UNIT_TYPE_CHOICES)
    code = models.CharField(max_length=32)
    name = models.CharField(max_length=120)
    name_en = models.CharField(max_length=120, blank=True)
    description = models.TextField(blank=True)
    description_en = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["parent_id", "sort_order", "code", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["parent", "code"],
                name="unique_church_structure_unit_parent_code",
            ),
        ]

    def __str__(self):
        return f"{self.code} - {self.name}"

    def clean(self):
        errors = {}

        if self.code:
            self.code = self.code.upper()

        if self.parent_id and self.pk and self.parent_id == self.pk:
            errors["parent"] = "A church structure unit cannot be its own parent."

        if self.parent is self:
            errors["parent"] = "A church structure unit cannot be its own parent."

        if self.unit_type == self.UNIT_ROOT and self.parent_id:
            errors["parent"] = "Root church structure units cannot have a parent."

        seen_parent_ids = set()
        current = self.parent

        while current:
            current_id = current.pk

            if current is self or (self.pk and current_id == self.pk):
                errors["parent"] = "A church structure unit cannot be its own ancestor."
                break

            if current_id is None:
                break

            if current_id in seen_parent_ids:
                errors["parent"] = "Parent chain contains a cycle."
                break

            seen_parent_ids.add(current_id)
            current = current.parent

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def display_name(self, language="zh"):
        if language == "en" and self.name_en:
            return self.name_en
        return self.name

    def get_ancestors(self):
        ancestors = []
        current = self.parent
        seen_ids = {self.pk} if self.pk else set()

        while current:
            current_id = current.pk

            if current_id is None or current_id in seen_ids:
                break

            ancestors.append(current)
            seen_ids.add(current_id)
            current = current.parent

        return list(reversed(ancestors))

    def path_label(self, language="zh"):
        units = self.get_ancestors() + [self]
        return " > ".join(unit.display_name(language) for unit in units)


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
