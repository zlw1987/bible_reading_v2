from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


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
            "Legacy-to-structure bridge for setup diagnostics and compatibility. "
            "May affect Bible Study structure-audience resolution/generation; "
            "does not directly edit memberships, audience rows, serving "
            "assignments, permissions, or ServiceEvent audience matching."
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
            "Legacy-to-structure bridge for setup diagnostics and compatibility. "
            "May affect Bible Study structure-audience resolution/generation "
            "and generated legacy SmallGroup meetings; does not directly edit "
            "memberships, audience rows, serving assignments, permissions, or "
            "ServiceEvent audience matching."
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
            "Legacy-to-structure bridge for setup diagnostics and compatibility. "
            "May affect Bible Study structure-audience resolution/generation "
            "and generated legacy SmallGroup meetings; does not directly edit "
            "memberships, audience rows, serving assignments, permissions, or "
            "ServiceEvent audience matching."
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


class ChurchStructureMembership(models.Model):
    STATUS_REQUESTED = "requested"
    STATUS_ACTIVE = "active"
    STATUS_ENDED = "ended"
    STATUS_REJECTED = "rejected"
    STATUS_CANCELLED = "cancelled"

    STATUS_CHOICES = [
        (STATUS_REQUESTED, "Requested"),
        (STATUS_ACTIVE, "Active"),
        (STATUS_ENDED, "Ended"),
        (STATUS_REJECTED, "Rejected"),
        (STATUS_CANCELLED, "Cancelled"),
    ]

    TYPE_MEMBER = "member"
    TYPE_VISITOR = "visitor"
    TYPE_REGULAR_ATTENDEE = "regular_attendee"
    TYPE_SMALL_GROUP_MEMBER = "small_group_member"

    MEMBERSHIP_TYPE_CHOICES = [
        (TYPE_MEMBER, "Member"),
        (TYPE_VISITOR, "Visitor"),
        (TYPE_REGULAR_ATTENDEE, "Regular Attendee"),
        (TYPE_SMALL_GROUP_MEMBER, "Small Group Member"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="church_structure_memberships",
    )
    unit = models.ForeignKey(
        ChurchStructureUnit,
        on_delete=models.PROTECT,
        related_name="memberships",
    )
    membership_type = models.CharField(
        max_length=32,
        choices=MEMBERSHIP_TYPE_CHOICES,
        default=TYPE_SMALL_GROUP_MEMBER,
    )
    status = models.CharField(
        max_length=32,
        choices=STATUS_CHOICES,
        default=STATUS_REQUESTED,
    )
    is_primary = models.BooleanField(default=False)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_church_structure_memberships",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="requested_church_structure_memberships",
    )
    notes = models.TextField(
        blank=True,
        help_text=(
            "Operational/non-sensitive notes only. Do not store counseling, "
            "pastoral, medical, financial, or private information."
        ),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["user__username", "-is_primary", "status", "start_date", "id"]

    def __str__(self):
        return f"{self.user} - {self.unit.display_name('en')} ({self.get_status_display()})"

    @property
    def is_requested(self):
        return self.status == self.STATUS_REQUESTED

    @property
    def is_active_membership(self):
        return self.active_for_date(timezone.localdate())

    @property
    def is_current_primary(self):
        return self.is_primary and self.is_active_membership

    @classmethod
    def active_for_user(cls, user, target_date=None):
        target_date = target_date or timezone.localdate()
        return cls.objects.filter(
            user=user,
            status=cls.STATUS_ACTIVE,
            start_date__lte=target_date,
        ).filter(
            models.Q(end_date__isnull=True) | models.Q(end_date__gte=target_date)
        )

    @classmethod
    def current_primary_for_user(cls, user, target_date=None):
        return cls.active_for_user(user, target_date=target_date).filter(
            is_primary=True
        ).first()

    def active_for_date(self, date):
        if self.status != self.STATUS_ACTIVE or not self.start_date:
            return False
        if self.start_date > date:
            return False
        if self.end_date and self.end_date < date:
            return False
        return True

    def clean(self):
        errors = {}
        today = timezone.localdate()

        if self.start_date and self.end_date and self.end_date < self.start_date:
            errors["end_date"] = "End date cannot be before start date."

        if self.status == self.STATUS_ACTIVE:
            if not self.start_date:
                errors["start_date"] = "Active membership requires a start date."
            if self.end_date and self.end_date < today:
                errors["end_date"] = (
                    "Active membership cannot have an end date in the past. "
                    "Use ended status for historical membership."
                )

        if self.status in {self.STATUS_REJECTED, self.STATUS_CANCELLED} and self.is_primary:
            errors["is_primary"] = "Rejected or cancelled membership cannot be primary."

        if (
            self.unit_id
            and self.unit
            and not self.unit.is_active
            and self.status in {self.STATUS_REQUESTED, self.STATUS_ACTIVE}
        ):
            errors["unit"] = (
                "Requested or active membership must use an active church structure unit."
            )

        if self.user_id and self.status == self.STATUS_ACTIVE and self.is_primary:
            duplicate = ChurchStructureMembership.objects.filter(
                user=self.user,
                status=self.STATUS_ACTIVE,
                is_primary=True,
            )
            if self.pk:
                duplicate = duplicate.exclude(pk=self.pk)
            if duplicate.exists():
                errors["is_primary"] = (
                    "A user can have only one active primary church structure membership."
                )

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


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
    structure_unit = models.ForeignKey(
        "ChurchStructureUnit",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="role_assignments",
        help_text=(
            "Canonical structure scope for non-global role assignments. Leave "
            "blank for global roles. District/small-group scoped roles require "
            "an explicit active ChurchStructureUnit and are the sole runtime "
            "source for scoped-role access."
        ),
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["user__username", "role", "scope_type"]

    def __str__(self):
        return f"{self.user} - {self.get_role_display()} ({self.get_scope_type_display()})"

    def clean(self):
        errors = {}
        structure_unit = None
        if self.structure_unit_id:
            try:
                structure_unit = self.structure_unit
            except ChurchStructureUnit.DoesNotExist:
                structure_unit = None

        if self.scope_type == self.SCOPE_GLOBAL:
            if self.structure_unit_id:
                errors["structure_unit"] = (
                    "Global roles cannot be scoped to a structure unit."
                )
        elif self.scope_type == self.SCOPE_DISTRICT:
            if not self.structure_unit_id:
                errors["structure_unit"] = (
                    "Scoped role assignments require a structure unit."
                )
            elif structure_unit is not None and not structure_unit.is_active:
                errors["structure_unit"] = (
                    "Scoped role assignments require an active structure unit."
                )
            elif (
                structure_unit is not None
                and structure_unit.unit_type == ChurchStructureUnit.UNIT_SMALL_GROUP
            ):
                errors["structure_unit"] = (
                    "District-scoped roles cannot use a small-group structure unit."
                )
        elif self.scope_type == self.SCOPE_SMALL_GROUP:
            if not self.structure_unit_id:
                errors["structure_unit"] = (
                    "Scoped role assignments require a structure unit."
                )
            elif structure_unit is not None and not structure_unit.is_active:
                errors["structure_unit"] = (
                    "Scoped role assignments require an active structure unit."
                )
            elif (
                structure_unit is not None
                and structure_unit.unit_type != ChurchStructureUnit.UNIT_SMALL_GROUP
            ):
                errors["structure_unit"] = (
                    "Small-group-scoped roles require a small-group structure unit."
                )

        if self.user_id and self.role and self.scope_type and self.is_active:
            duplicate_filter = {
                "user": self.user,
                "role": self.role,
                "scope_type": self.scope_type,
                "is_active": True,
            }
            if self.scope_type != self.SCOPE_GLOBAL:
                duplicate_filter["structure_unit"] = structure_unit

            duplicate = ChurchRoleAssignment.objects.filter(
                **duplicate_filter,
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
    preferred_language = models.CharField(
        max_length=2,
        choices=LANGUAGE_CHOICES,
        default="zh",
    )
    must_change_password = models.BooleanField(default=False)
    def __str__(self):
        return self.user.get_username()
