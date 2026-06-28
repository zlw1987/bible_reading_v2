from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from events.models import ServiceEvent


class MinistryTeam(models.Model):
    # MINISTRY-STRUCTURE.1B: ``team_kind`` is descriptive taxonomy for the
    # structure map and default suggestions; it is NOT a behavior gate. The
    # authoritative gate for whether a team may be a ``TeamAssignment`` target is
    # ``is_assignable`` (enforcement is a later, separately approved slice; this
    # foundation slice only stores the flag and changes no assignment behavior).
    KIND_MINISTRY_AREA = "ministry_area"
    KIND_DEPARTMENT = "department"
    KIND_TEAM = "team"
    KIND_SUBTEAM = "subteam"
    KIND_PROJECT_GROUP = "project_group"
    KIND_CUSTOM = "custom"

    TEAM_KIND_CHOICES = [
        (KIND_MINISTRY_AREA, "Ministry Area"),
        (KIND_DEPARTMENT, "Department"),
        (KIND_TEAM, "Team"),
        (KIND_SUBTEAM, "Subteam"),
        (KIND_PROJECT_GROUP, "Project Group"),
        (KIND_CUSTOM, "Custom"),
    ]

    name = models.CharField(max_length=160)
    name_en = models.CharField(max_length=160, blank=True, default="")
    description = models.TextField(blank=True, default="")
    description_en = models.TextField(blank=True, default="")
    email_alias = models.CharField(max_length=180, blank=True, default="")
    playbook_link = models.URLField(max_length=500, blank=True, default="")
    team_kind = models.CharField(
        max_length=32,
        choices=TEAM_KIND_CHOICES,
        default=KIND_TEAM,
        help_text=(
            "Descriptive ministry-structure taxonomy for display/grouping only. "
            "Does not gate assignment, membership, visibility, or permissions."
        ),
    )
    is_assignable = models.BooleanField(
        default=True,
        help_text=(
            "Whether this team may be selected as a TeamAssignment target. "
            "Stored in MINISTRY-STRUCTURE.1B; enforcement is a later slice and "
            "does not change current assignment behavior."
        ),
    )
    role_profile = models.ForeignKey(
        "MinistryTeamRoleProfile",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="teams",
        help_text=(
            "Explicit ministry role profile for setup/readiness only. Not "
            "computed from hierarchy and does not grant membership, serving, or "
            "permissions."
        ),
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        indexes = [
            models.Index(fields=["is_active"]),
            models.Index(fields=["team_kind"]),
            models.Index(fields=["is_assignable"]),
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

    # ----------------------------------------------------------------------
    # MINISTRY-STRUCTURE.1B read-only structure helpers.
    #
    # These describe the ministry-structure *display* organization only. A
    # parent link (ministry parent_team or a ChurchStructureUnit display
    # anchor) never implies ChurchStructureMembership, audience visibility,
    # serving/TeamAssignment, My Serving, church-structure delegated
    # management, member/care-record access, or any permission. They are pure
    # read helpers and mutate nothing.
    # ----------------------------------------------------------------------
    def active_parent_links(self):
        """Active parent links for this team, ordered for display."""
        return self.parent_links.filter(is_active=True).order_by(
            "sort_order", "id"
        )

    def primary_parent_link(self):
        """The single active primary parent link, or ``None``.

        At most one active primary link is allowed (enforced in
        ``MinistryTeamParentLink.clean``); this returns the first if present.
        """
        return (
            self.parent_links.filter(is_active=True, is_primary=True)
            .order_by("sort_order", "id")
            .first()
        )

    def get_ministry_ancestors(self):
        """Ministry ancestor teams via the primary ``parent_team`` chain only.

        Returns the ancestor ``MinistryTeam`` rows ordered top-most first
        (display order), following only active primary links that point at a
        parent team. The walk stops at the first primary link that is missing,
        points at a church anchor, or would revisit a team (cycle guard).
        Church anchors are display-only and never appear in this list.
        """
        ancestors = []
        seen = {self.pk} if self.pk else set()
        current = self
        while True:
            link = current.primary_parent_link()
            if link is None or link.parent_team_id is None:
                break
            parent = link.parent_team
            if parent.pk in seen:
                break
            ancestors.append(parent)
            seen.add(parent.pk)
            current = parent
        return list(reversed(ancestors))

    def primary_church_anchor(self):
        """The ChurchStructureUnit display anchor at the top of the primary chain.

        Walks the primary parent chain upward; returns the first
        ``parent_church_unit`` reached, or ``None`` if the chain ends without a
        church anchor. Display-only: this never grants membership, visibility,
        serving, or permission.
        """
        seen = {self.pk} if self.pk else set()
        current = self
        while True:
            link = current.primary_parent_link()
            if link is None:
                return None
            if link.parent_church_unit_id is not None:
                return link.parent_church_unit
            if link.parent_team_id is None or link.parent_team.pk in seen:
                return None
            seen.add(link.parent_team.pk)
            current = link.parent_team

    def display_path_label(self, language="zh"):
        """Human-readable display breadcrumb for this ministry team.

        Combines (when present) the primary church-anchor path, then the
        ministry ancestor chain, then this team. Display/organization only.
        """
        parts = []
        anchor = self.primary_church_anchor()
        if anchor is not None:
            parts.append(anchor.path_label(language))
        for ancestor in self.get_ministry_ancestors():
            parts.append(ancestor.get_name(language))
        parts.append(self.get_name(language))
        return " > ".join(parts)

    def missing_required_role_types(self, target_date=None):
        """Required role types with no active assignment on this team.

        Mirrors ``ChurchStructureUnit.missing_required_role_types``: read-only
        setup/readiness signal. Returns an empty list when no role profile is
        set or no required role types are configured. Never blocks save,
        creation, assignment, or scheduling, and creates nothing.
        """
        if not self.role_profile_id:
            return []

        target_date = target_date or timezone.localdate()
        required_role_types = list(
            MinistryTeamRoleType.objects.filter(
                profile_requirements__profile=self.role_profile,
                profile_requirements__is_active=True,
                profile_requirements__is_required=True,
                is_active=True,
            ).distinct()
        )
        if not required_role_types:
            return []

        covered_role_type_ids = set(
            self.role_assignments.filter(
                is_active=True,
                role_type__in=required_role_types,
                start_date__lte=target_date,
            )
            .filter(
                models.Q(end_date__isnull=True)
                | models.Q(end_date__gte=target_date)
            )
            .values_list("role_type_id", flat=True)
        )

        return [
            role_type
            for role_type in required_role_types
            if role_type.id not in covered_role_type_ids
        ]


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

    def is_confirmable(self):
        return self.status in {
            self.STATUS_SCHEDULED,
            self.STATUS_PREPARED,
        }

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


# ---------------------------------------------------------------------------
# MINISTRY-STRUCTURE.1B — ministry-structure model foundation (additive only).
#
# These models upgrade the existing flat MinistryTeam into a ministry-structure
# unit by adding, around it: multi-parent display links, and a ministry role
# system (role type / profile / requirement / assignment) mirroring the church
# coworker role system in accounts.models.
#
# Boundaries (locked in docs/MINISTRY_STRUCTURE_ARCHITECTURE_PLAN.md):
# - Ministry structure is NOT church structure. A ChurchStructureUnit parent is
#   a display anchor only; it never grants ChurchStructureMembership, audience
#   visibility, serving, My Units management, or member/care-record access.
# - MinistryTeamRoleAssignment is an explicit long-term ministry role. It is
#   additive in this phase and does NOT drive can_manage_ministry_team or any
#   permission; TeamMembership.role / can_lead remains the permission source.
# - Nothing here auto-creates TeamMembership, TeamAssignment,
#   TeamAssignmentMember, ChurchStructureMembership, ChurchStructureUnitRoleAssignment,
#   or BibleStudyMeetingRole.
# ---------------------------------------------------------------------------


class MinistryTeamRoleType(models.Model):
    """A named long-term ministry role definition (lead, scheduler, etc.).

    Mirrors ``accounts.ChurchStructureUnitRoleType`` but in the ministry
    namespace and with separate semantics. Globally scoped with a globally
    unique normalized ``code``.
    """

    CODE_LEAD = "lead"
    CODE_ASSISTANT_LEAD = "assistant_lead"
    CODE_COORDINATOR = "coordinator"
    CODE_SCHEDULER = "scheduler"
    CODE_TRAINER = "trainer"
    CODE_TECHNICAL_LEAD = "technical_lead"
    CODE_EQUIPMENT_MANAGER = "equipment_manager"
    CODE_ADMIN = "admin"
    CODE_MEMBER_CARE = "member_care"

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


class MinistryTeamRoleProfile(models.Model):
    """A configurable bundle of required/optional ministry role types.

    Mirrors ``accounts.ChurchStructureUnitRoleProfile``. Selected explicitly on
    ``MinistryTeam.role_profile``; never recomputed from hierarchy.
    """

    CODE_DEFAULT_MINISTRY_UNIT = "default_ministry_unit"
    CODE_TECHNICAL_TEAM = "technical_team"
    CODE_WORSHIP_RELATED_TEAM = "worship_related_team"
    CODE_PROJECT_TEAM = "project_team"
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


class MinistryTeamRoleRequirement(models.Model):
    """Marks a role type required/optional for a ministry role profile.

    Mirrors ``accounts.ChurchStructureUnitRoleRequirement``. Drives
    ``MinistryTeam.missing_required_role_types`` (warning/readiness only).
    """

    profile = models.ForeignKey(
        MinistryTeamRoleProfile,
        on_delete=models.CASCADE,
        related_name="role_requirements",
    )
    role_type = models.ForeignKey(
        MinistryTeamRoleType,
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
                name="unique_ministry_team_role_requirement",
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


class MinistryTeamParentLink(models.Model):
    """A display/organization parent link for a ministry team.

    The parent target is EITHER another ``MinistryTeam`` (ministry hierarchy)
    OR a ``ChurchStructureUnit`` (church display anchor) — exactly one. This is
    display/organization only: a parent link never implies
    ``ChurchStructureMembership``, audience visibility, serving/TeamAssignment,
    My Serving, church-structure delegated management, member/care-record
    access, Bible Study candidacy, ServiceEvent visibility, or any permission.

    Multiple active links are allowed (a shared ministry may sit under several
    anchors). At most one active primary link per child team drives the default
    breadcrumb; other active links are "also linked under …".
    """

    child_team = models.ForeignKey(
        MinistryTeam,
        on_delete=models.CASCADE,
        related_name="parent_links",
    )
    parent_team = models.ForeignKey(
        MinistryTeam,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="child_links",
    )
    parent_church_unit = models.ForeignKey(
        "accounts.ChurchStructureUnit",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="ministry_team_parent_links",
        help_text=(
            "Display anchor only. Does not grant church membership, audience "
            "visibility, serving, delegated management, or any permission."
        ),
    )
    is_primary = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["child_team", "sort_order", "id"]
        indexes = [
            models.Index(fields=["child_team", "is_active"]),
            models.Index(fields=["parent_team", "is_active"]),
            models.Index(fields=["parent_church_unit", "is_active"]),
        ]
        constraints = [
            models.CheckConstraint(
                name="ministry_parent_link_exactly_one_target",
                condition=(
                    models.Q(
                        parent_team__isnull=False,
                        parent_church_unit__isnull=True,
                    )
                    | models.Q(
                        parent_team__isnull=True,
                        parent_church_unit__isnull=False,
                    )
                ),
            ),
        ]

    def __str__(self):
        target = self.parent_team or self.parent_church_unit
        return f"{self.child_team} <- {target}"

    def _creates_cycle(self):
        """Whether this proposed parent_team edge would close a ministry cycle.

        Walks all active ``parent_team`` ancestors of the proposed parent team;
        a cycle exists if the child team is itself an ancestor of (or equal to)
        the proposed parent. Church-anchor links never create ministry cycles.
        """
        if not self.parent_team_id or not self.child_team_id:
            return False
        if self.parent_team_id == self.child_team_id:
            return True

        target_id = self.child_team_id
        stack = [self.parent_team_id]
        seen = set()
        while stack:
            team_id = stack.pop()
            if team_id == target_id:
                return True
            if team_id in seen:
                continue
            seen.add(team_id)
            parent_ids = (
                MinistryTeamParentLink.objects.filter(
                    child_team_id=team_id,
                    is_active=True,
                    parent_team__isnull=False,
                )
                .exclude(pk=self.pk)
                .values_list("parent_team_id", flat=True)
            )
            stack.extend(parent_ids)
        return False

    def clean(self):
        errors = {}

        has_team = self.parent_team_id is not None
        has_unit = self.parent_church_unit_id is not None
        if has_team == has_unit:
            errors["__all__"] = (
                "Exactly one of parent team or parent church unit must be set."
            )

        if has_team and self.child_team_id == self.parent_team_id:
            errors["parent_team"] = "A ministry team cannot be its own parent."

        if has_team and self._creates_cycle():
            errors["parent_team"] = (
                "This parent link would create a ministry hierarchy cycle."
            )

        if self.is_active:
            if self.child_team_id and not self.child_team.is_active:
                errors["child_team"] = (
                    "Active parent links require an active child team."
                )
            if has_team and not self.parent_team.is_active:
                errors["parent_team"] = (
                    "Active parent links require an active parent team."
                )
            if has_unit and not self.parent_church_unit.is_active:
                errors["parent_church_unit"] = (
                    "Active parent links require an active parent church unit."
                )

            if self.child_team_id and (has_team or has_unit):
                duplicate_query = MinistryTeamParentLink.objects.filter(
                    child_team_id=self.child_team_id,
                    is_active=True,
                )
                if has_team:
                    duplicate_query = duplicate_query.filter(
                        parent_team_id=self.parent_team_id
                    )
                else:
                    duplicate_query = duplicate_query.filter(
                        parent_church_unit_id=self.parent_church_unit_id
                    )
                if self.pk:
                    duplicate_query = duplicate_query.exclude(pk=self.pk)
                if duplicate_query.exists():
                    errors["__all__"] = (
                        "This child team already has an active link to that parent."
                    )

            if self.is_primary and self.child_team_id:
                primary_query = MinistryTeamParentLink.objects.filter(
                    child_team_id=self.child_team_id,
                    is_active=True,
                    is_primary=True,
                )
                if self.pk:
                    primary_query = primary_query.exclude(pk=self.pk)
                if primary_query.exists():
                    errors["is_primary"] = (
                        "A child team may have at most one active primary parent link."
                    )

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def parent_label(self, language="zh"):
        if self.parent_team_id:
            return self.parent_team.get_name(language)
        if self.parent_church_unit_id:
            return self.parent_church_unit.display_name(language)
        return ""


class MinistryTeamRoleAssignment(models.Model):
    """A user's explicit long-term ministry role on a ministry team.

    Mirrors ``accounts.ChurchStructureUnitRoleAssignment``. Multiple active
    Leads are allowed. This is additive in MINISTRY-STRUCTURE.1B: it does NOT
    drive ``can_manage_ministry_team`` or any permission, is never inferred from
    ``TeamMembership``, and creates no membership/serving/assignment rows.
    """

    team = models.ForeignKey(
        MinistryTeam,
        on_delete=models.PROTECT,
        related_name="role_assignments",
    )
    role_type = models.ForeignKey(
        MinistryTeamRoleType,
        on_delete=models.PROTECT,
        related_name="team_assignments",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="ministry_team_role_assignments",
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
        ordering = ["team", "role_type__sort_order", "user__username", "id"]
        indexes = [
            models.Index(fields=["team", "is_active"]),
            models.Index(fields=["role_type", "is_active"]),
            models.Index(fields=["user", "is_active"]),
        ]

    def __str__(self):
        return f"{self.user} - {self.role_type.display_name('en')} ({self.team})"

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
            if self.team_id and not self.team.is_active:
                errors["team"] = "Active role assignments require an active team."
            if self.role_type_id and not self.role_type.is_active:
                errors["role_type"] = (
                    "Active role assignments require an active role type."
                )
            if self.user_id and not self.user.is_active:
                errors["user"] = "Active role assignments require an active user."

            if self.team_id and self.role_type_id and self.user_id and self.start_date:
                overlapping = MinistryTeamRoleAssignment.objects.filter(
                    team=self.team,
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
                        "This user already has an overlapping active ministry "
                        "role assignment for this team and role type."
                    )

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)
