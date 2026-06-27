from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class ChurchStructureUnitRoleType(models.Model):
    CODE_LEAD = "lead"
    CODE_ASSISTANT_LEAD = "assistant_lead"
    CODE_CARING = "caring"
    CODE_EDIFY = "edify"
    CODE_OUTREACH = "outreach"
    CODE_WORSHIP = "worship"

    code = models.CharField(max_length=64, unique=True)
    name = models.CharField(max_length=120)
    name_en = models.CharField(max_length=120, blank=True)
    description = models.TextField(blank=True)
    description_en = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    is_system_default = models.BooleanField(default=False)
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "code"]

    def __str__(self):
        return f"{self.code} - {self.name}"

    def clean(self):
        if self.code:
            self.code = self.code.strip().lower()

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def display_name(self, language="zh"):
        if language == "en" and self.name_en:
            return self.name_en
        return self.name


class ChurchStructureUnitRoleProfile(models.Model):
    CODE_GENERAL_UNIT = "general_unit"
    CODE_DISTRICT_UNIT = "district_unit"
    CODE_SMALL_GROUP_UNIT = "small_group_unit"
    CODE_DEPARTMENT_UNIT = "department_unit"
    CODE_CUSTOM = "custom"

    code = models.CharField(max_length=64, unique=True)
    name = models.CharField(max_length=120)
    name_en = models.CharField(max_length=120, blank=True)
    description = models.TextField(blank=True)
    description_en = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    is_system_default = models.BooleanField(default=False)
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "code"]

    def __str__(self):
        return f"{self.code} - {self.name}"

    def clean(self):
        if self.code:
            self.code = self.code.strip().lower()

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def display_name(self, language="zh"):
        if language == "en" and self.name_en:
            return self.name_en
        return self.name


class ChurchStructureUnitRoleRequirement(models.Model):
    profile = models.ForeignKey(
        ChurchStructureUnitRoleProfile,
        on_delete=models.CASCADE,
        related_name="role_requirements",
    )
    role_type = models.ForeignKey(
        ChurchStructureUnitRoleType,
        on_delete=models.PROTECT,
        related_name="profile_requirements",
    )
    is_required = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["profile__sort_order", "sort_order", "role_type__sort_order"]
        constraints = [
            models.UniqueConstraint(
                fields=["profile", "role_type"],
                name="unique_structure_unit_role_requirement",
            ),
        ]

    def __str__(self):
        required_label = "required" if self.is_required else "optional"
        return f"{self.profile.code}: {self.role_type.code} ({required_label})"

    def clean(self):
        errors = {}

        if self.is_active:
            if self.profile_id and not self.profile.is_active:
                errors["profile"] = "Active requirements must use an active role profile."
            if self.role_type_id and not self.role_type.is_active:
                errors["role_type"] = "Active requirements must use an active role type."

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


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
    role_profile = models.ForeignKey(
        ChurchStructureUnitRoleProfile,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="units",
        help_text=(
            "Explicit coworker-role profile for setup/readiness. This is not "
            "computed from leaf-node status and does not grant membership, "
            "permissions, or serving assignments."
        ),
    )
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

        if self.role_profile_id and not self.role_profile.is_active:
            errors["role_profile"] = "Church structure units require an active role profile."

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

    def missing_required_role_types(self, target_date=None):
        if not self.role_profile_id:
            return []

        target_date = target_date or timezone.localdate()
        required_role_types = list(
            ChurchStructureUnitRoleType.objects.filter(
                profile_requirements__profile=self.role_profile,
                profile_requirements__is_active=True,
                profile_requirements__is_required=True,
                is_active=True,
            ).distinct()
        )
        if not required_role_types:
            return []

        covered_role_type_ids = set(
            self.coworker_role_assignments.filter(
                is_active=True,
                role_type__in=required_role_types,
                start_date__lte=target_date,
            )
            .filter(models.Q(end_date__isnull=True) | models.Q(end_date__gte=target_date))
            .values_list("role_type_id", flat=True)
        )

        return [
            role_type
            for role_type in required_role_types
            if role_type.id not in covered_role_type_ids
        ]


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


class ChurchStructureUnitRoleAssignment(models.Model):
    unit = models.ForeignKey(
        ChurchStructureUnit,
        on_delete=models.PROTECT,
        related_name="coworker_role_assignments",
    )
    role_type = models.ForeignKey(
        ChurchStructureUnitRoleType,
        on_delete=models.PROTECT,
        related_name="unit_assignments",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="structure_unit_role_assignments",
    )
    is_active = models.BooleanField(default=True)
    start_date = models.DateField(default=timezone.localdate)
    end_date = models.DateField(null=True, blank=True)
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
        ordering = ["unit", "role_type__sort_order", "user__username", "id"]
        indexes = [
            models.Index(fields=["unit", "is_active"]),
            models.Index(fields=["role_type", "is_active"]),
            models.Index(fields=["user", "is_active"]),
        ]

    def __str__(self):
        return f"{self.user} - {self.role_type.display_name('en')} ({self.unit})"

    def active_for_date(self, date):
        if not self.is_active or not self.start_date:
            return False
        if self.start_date > date:
            return False
        if self.end_date and self.end_date < date:
            return False
        return True

    def clean(self):
        errors = {}

        if self.start_date and self.end_date and self.end_date < self.start_date:
            errors["end_date"] = "End date cannot be before start date."

        if self.is_active:
            if self.unit_id and not self.unit.is_active:
                errors["unit"] = "Active coworker role assignments require an active unit."
            if self.role_type_id and not self.role_type.is_active:
                errors["role_type"] = (
                    "Active coworker role assignments require an active role type."
                )
            if self.user_id and not self.user.is_active:
                errors["user"] = "Active coworker role assignments require an active user."

            if self.unit_id and self.role_type_id and self.user_id and self.start_date:
                overlapping = ChurchStructureUnitRoleAssignment.objects.filter(
                    unit=self.unit,
                    role_type=self.role_type,
                    user=self.user,
                    is_active=True,
                ).filter(
                    models.Q(end_date__isnull=True)
                    | models.Q(end_date__gte=self.start_date)
                )
                if self.end_date:
                    overlapping = overlapping.filter(start_date__lte=self.end_date)
                if self.pk:
                    overlapping = overlapping.exclude(pk=self.pk)
                if overlapping.exists():
                    errors["user"] = (
                        "This user already has an overlapping active coworker "
                        "role assignment for this unit and role type."
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


class ChurchMemberRecord(models.Model):
    """Global church member fact record (MEMBER-RECORD.1B).

    One row per user, recording stable church-wide facts (Faith Statement and
    baptism) that are directly relevant to future formal membership / formal
    serving-readiness evaluation.

    This is NOT belonging (`ChurchStructureMembership`), NOT serving
    (`TeamAssignmentMember` / `BibleStudyMeetingRole`), and NOT a capability
    grant. It does not store course/training/discipleship progress (e.g. C201 /
    认识我们的教会 / 福音真理班 / 受浸预备班 / 基础真理班) — those varying
    pathways are deferred to a future course/training module. It also does not
    store or imply serving readiness; readiness is future configurable,
    warning-only policy computed on demand, never a stored boolean here.
    """

    FAITH_STATEMENT_UNKNOWN = "unknown"
    FAITH_STATEMENT_NOT_STARTED = "not_started"
    FAITH_STATEMENT_SENT_PENDING_SIGNATURE = "sent_pending_signature"
    FAITH_STATEMENT_SIGNED = "signed"
    FAITH_STATEMENT_WAIVED = "waived"
    FAITH_STATEMENT_DECLINED = "declined"
    FAITH_STATEMENT_NOT_REQUIRED = "not_required"

    FAITH_STATEMENT_STATUS_CHOICES = [
        (FAITH_STATEMENT_UNKNOWN, "Unknown"),
        (FAITH_STATEMENT_NOT_STARTED, "Not started"),
        (FAITH_STATEMENT_SENT_PENDING_SIGNATURE, "Sent, pending signature"),
        (FAITH_STATEMENT_SIGNED, "Signed"),
        (FAITH_STATEMENT_WAIVED, "Waived"),
        (FAITH_STATEMENT_DECLINED, "Declined"),
        (FAITH_STATEMENT_NOT_REQUIRED, "Not required"),
    ]

    FAITH_STATEMENT_STATUS_LABELS_ZH = {
        FAITH_STATEMENT_UNKNOWN: "未知",
        FAITH_STATEMENT_NOT_STARTED: "未开始",
        FAITH_STATEMENT_SENT_PENDING_SIGNATURE: "已发送，待签署",
        FAITH_STATEMENT_SIGNED: "已签署",
        FAITH_STATEMENT_WAIVED: "已豁免",
        FAITH_STATEMENT_DECLINED: "已婉拒",
        FAITH_STATEMENT_NOT_REQUIRED: "无需",
    }

    BAPTISM_UNKNOWN = "unknown"
    BAPTISM_NOT_BAPTIZED = "not_baptized"
    BAPTISM_BAPTIZED = "baptized"
    BAPTISM_RECOGNIZED = "recognized"
    BAPTISM_WAIVED = "waived"
    BAPTISM_NOT_REQUIRED = "not_required"

    BAPTISM_STATUS_CHOICES = [
        (BAPTISM_UNKNOWN, "Unknown"),
        (BAPTISM_NOT_BAPTIZED, "Not baptized"),
        (BAPTISM_BAPTIZED, "Baptized"),
        (BAPTISM_RECOGNIZED, "Recognized (baptized elsewhere)"),
        (BAPTISM_WAIVED, "Waived"),
        (BAPTISM_NOT_REQUIRED, "Not required"),
    ]

    BAPTISM_STATUS_LABELS_ZH = {
        BAPTISM_UNKNOWN: "未知",
        BAPTISM_NOT_BAPTIZED: "未受浸",
        BAPTISM_BAPTIZED: "已受浸",
        BAPTISM_RECOGNIZED: "已认可（在他处受浸）",
        BAPTISM_WAIVED: "已豁免",
        BAPTISM_NOT_REQUIRED: "无需",
    }

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="church_member_record",
    )
    faith_statement_status = models.CharField(
        max_length=32,
        choices=FAITH_STATEMENT_STATUS_CHOICES,
        default=FAITH_STATEMENT_UNKNOWN,
        help_text=(
            "Faith Statement / 信仰宣言 acceptance-and-signature state. This is "
            "specifically the Faith Statement status, not a generic spiritual "
            "status, and not course/training progress."
        ),
    )
    faith_statement_signed_date = models.DateField(null=True, blank=True)
    baptism_status = models.CharField(
        max_length=32,
        choices=BAPTISM_STATUS_CHOICES,
        default=BAPTISM_UNKNOWN,
    )
    baptism_date = models.DateField(null=True, blank=True)
    notes = models.TextField(
        blank=True,
        help_text=(
            "Operational membership notes only. Do not store counseling, "
            "medical, financial, immigration, or highly sensitive pastoral "
            "details."
        ),
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_church_member_records",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="updated_church_member_records",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["user__username", "id"]

    def __str__(self):
        return f"Member record: {self.user.get_username()}"

    def faith_statement_status_label(self, language="zh"):
        if language == "en":
            return dict(self.FAITH_STATEMENT_STATUS_CHOICES).get(
                self.faith_statement_status, self.faith_statement_status
            )
        return self.FAITH_STATEMENT_STATUS_LABELS_ZH.get(
            self.faith_statement_status, self.faith_statement_status
        )

    def baptism_status_label(self, language="zh"):
        if language == "en":
            return dict(self.BAPTISM_STATUS_CHOICES).get(
                self.baptism_status, self.baptism_status
            )
        return self.BAPTISM_STATUS_LABELS_ZH.get(
            self.baptism_status, self.baptism_status
        )


class ServingReadinessPolicy(models.Model):
    """Configurable church serving-readiness policy (SERVING-READINESS.1A).

    A policy is a data-driven church rule describing which `ChurchMemberRecord`
    facts (and which statuses) are required for "ready to serve." It is
    warning-only and advisory:

    - It does NOT grant any permission/capability.
    - It does NOT block any assignment surface by itself (V1 readiness is
      warning-only; see the serving-readiness plan, Section D.6).
    - It does NOT store a per-user readiness result; readiness is computed on
      demand by the evaluator in `accounts.serving_readiness`.

    Belonging stays `ChurchStructureMembership`; serving stays
    `TeamAssignmentMember` / `BibleStudyMeetingRole`. A policy never reads
    membership to infer facts.
    """

    code = models.CharField(
        max_length=64,
        unique=True,
        help_text="Stable lower-case identifier, e.g. svca_default_formal_serving.",
    )
    name = models.CharField(max_length=120)
    name_en = models.CharField(max_length=120, blank=True)
    description = models.TextField(blank=True)
    description_en = models.TextField(blank=True)
    is_default = models.BooleanField(
        default=False,
        help_text=(
            "When set, this policy is the default the evaluator resolves when no "
            "explicit policy is passed. At most one active default is allowed."
        ),
    )
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "code"]
        verbose_name_plural = "Serving readiness policies"

    def __str__(self):
        return f"{self.code} - {self.name}"

    def clean(self):
        errors = {}

        if self.code:
            self.code = self.code.strip().lower()

        if self.is_default and self.is_active:
            duplicates = ServingReadinessPolicy.objects.filter(
                is_default=True,
                is_active=True,
            )
            if self.pk:
                duplicates = duplicates.exclude(pk=self.pk)
            if duplicates.exists():
                errors["is_default"] = (
                    "Only one active default serving-readiness policy is allowed."
                )

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def display_name(self, language="zh"):
        if language == "en" and self.name_en:
            return self.name_en
        return self.name

    def display_description(self, language="zh"):
        if language == "en" and self.description_en:
            return self.description_en
        return self.description


class ServingReadinessRequirement(models.Model):
    """A single member-fact requirement within a `ServingReadinessPolicy`.

    Each requirement checks one supported `ChurchMemberRecord` fact field
    against a configured set of accepted status codes. Accepted statuses are
    stored as a portable, comma-separated, normalized lower-case string (no
    PostgreSQL-only ArrayField) and validated against the member-record choice
    set for the requirement type.

    Requirements are advisory inputs to the warning-only evaluator. They do not
    grant permissions, create assignments, or read membership.
    """

    REQUIREMENT_FAITH_STATEMENT = "faith_statement"
    REQUIREMENT_BAPTISM = "baptism"

    REQUIREMENT_TYPE_CHOICES = [
        (REQUIREMENT_FAITH_STATEMENT, "Faith Statement"),
        (REQUIREMENT_BAPTISM, "Baptism"),
    ]

    SEVERITY_REQUIRED = "required"
    SEVERITY_RECOMMENDED = "recommended"

    SEVERITY_CHOICES = [
        (SEVERITY_REQUIRED, "Required"),
        (SEVERITY_RECOMMENDED, "Recommended"),
    ]

    policy = models.ForeignKey(
        ServingReadinessPolicy,
        on_delete=models.CASCADE,
        related_name="requirements",
    )
    requirement_type = models.CharField(
        max_length=32,
        choices=REQUIREMENT_TYPE_CHOICES,
        help_text=(
            "Supported V1 fact sources: faith_statement and baptism, both read "
            "from ChurchMemberRecord. Course/training requirement types are not "
            "supported by the V1 evaluator."
        ),
    )
    accepted_statuses = models.CharField(
        max_length=255,
        help_text=(
            "Comma-separated member-record status codes that satisfy this "
            "requirement, validated against the requirement type's choices."
        ),
    )
    severity = models.CharField(
        max_length=16,
        choices=SEVERITY_CHOICES,
        default=SEVERITY_REQUIRED,
        help_text=(
            "required severity affects is_ready; recommended is warning-only. "
            "Even required requirements are warning-only at assignment surfaces "
            "in V1."
        ),
    )
    label = models.CharField(max_length=120)
    label_en = models.CharField(max_length=120, blank=True)
    message = models.TextField(blank=True)
    message_en = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["policy__sort_order", "sort_order", "id"]

    def __str__(self):
        return f"{self.policy.code}: {self.requirement_type} ({self.severity})"

    @classmethod
    def valid_status_codes_for_type(cls, requirement_type):
        """Return the member-record status codes valid for a requirement type.

        Returns None for unsupported types so callers/validation can reject
        them clearly.
        """
        if requirement_type == cls.REQUIREMENT_FAITH_STATEMENT:
            return {
                code for code, _ in ChurchMemberRecord.FAITH_STATEMENT_STATUS_CHOICES
            }
        if requirement_type == cls.REQUIREMENT_BAPTISM:
            return {code for code, _ in ChurchMemberRecord.BAPTISM_STATUS_CHOICES}
        return None

    @staticmethod
    def normalize_status_tokens(raw):
        """Split/trim/lower a comma-separated status string, de-duplicated."""
        cleaned = []
        seen = set()
        for token in (raw or "").split(","):
            token = token.strip().lower()
            if not token or token in seen:
                continue
            seen.add(token)
            cleaned.append(token)
        return cleaned

    def accepted_status_set(self):
        return set(self.normalize_status_tokens(self.accepted_statuses))

    def clean(self):
        errors = {}

        requirement_type = (self.requirement_type or "").strip().lower()
        self.requirement_type = requirement_type

        valid_codes = self.valid_status_codes_for_type(requirement_type)
        if valid_codes is None:
            errors["requirement_type"] = (
                "Unsupported requirement type. The V1 evaluator supports only "
                "faith_statement and baptism."
            )

        cleaned_statuses = self.normalize_status_tokens(self.accepted_statuses)
        self.accepted_statuses = ",".join(cleaned_statuses)
        if not cleaned_statuses:
            errors["accepted_statuses"] = "At least one accepted status is required."
        elif valid_codes is not None:
            unknown = [code for code in cleaned_statuses if code not in valid_codes]
            if unknown:
                errors["accepted_statuses"] = (
                    f"Unknown status code(s) for {requirement_type}: "
                    f"{', '.join(unknown)}."
                )

        if self.is_active:
            if self.policy_id and not self.policy.is_active:
                errors["policy"] = (
                    "Active requirements must belong to an active policy."
                )
            if self.policy_id and valid_codes is not None:
                duplicates = ServingReadinessRequirement.objects.filter(
                    policy_id=self.policy_id,
                    requirement_type=requirement_type,
                    is_active=True,
                )
                if self.pk:
                    duplicates = duplicates.exclude(pk=self.pk)
                if duplicates.exists():
                    errors["requirement_type"] = (
                        "This policy already has an active requirement of type "
                        f"{requirement_type}."
                    )

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def display_label(self, language="zh"):
        if language == "en" and self.label_en:
            return self.label_en
        return self.label

    def display_message(self, language="zh"):
        if language == "en" and self.message_en:
            return self.message_en
        return self.message
