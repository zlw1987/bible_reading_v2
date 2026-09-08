from django import forms
from django.contrib import admin
from django.db import transaction
from django.db.models import Q

from events.models import ServiceProfile
from events.scheduling_revision import advance_scheduling_revisions

from .forms import NormalizedMinistryTeamKeyFormField
from .models import (
    MinistryTeam,
    MinistryTeamParentLink,
    MinistryTeamRoleAssignment,
    MinistryTeamRoleProfile,
    MinistryTeamRoleRequirement,
    MinistryTeamRoleType,
    ServiceProfileMinistryRequirement,
    TeamAssignment,
    TeamAssignmentMember,
    TeamMembership,
)
from .services.worship_governance import (
    resolve_worship_rotation_pool_for_team,
)


# MINISTRY-STRUCTURE.1B admin. Ministry structure is NOT church
# structure; a ChurchStructureUnit parent link is a display anchor only. Parent
# links and role assignments here do not grant membership, audience visibility,
# serving, or My Serving items. After MINISTRY-ROLE-SOURCE.1C, active date-valid
# Lead/Coordinator MinistryTeamRoleAssignment rows grant exact-team management;
# other role types and TeamMembership.role/can_lead grant no such permission.
# The key warnings are also carried on model field help_text.


class MinistryTeamParentLinkInline(admin.TabularInline):
    model = MinistryTeamParentLink
    fk_name = "child_team"
    extra = 0
    raw_id_fields = ("parent_team", "parent_church_unit")
    fields = (
        "parent_team",
        "parent_church_unit",
        "is_primary",
        "is_active",
        "sort_order",
    )


@admin.register(MinistryTeam)
class MinistryTeamAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "team_key",
        "team_kind",
        "is_assignable",
        "is_worship_rotation_pool",
        "role_profile",
        "email_alias",
        "is_active",
        "updated_at",
    )
    list_filter = (
        "team_kind",
        "is_assignable",
        "is_worship_rotation_pool",
        "is_active",
    )
    search_fields = (
        "name",
        "name_en",
        "team_key",
        "description",
        "description_en",
        "email_alias",
    )
    raw_id_fields = ("role_profile",)
    inlines = (MinistryTeamParentLinkInline,)

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        if db_field.name == "team_key":
            kwargs["form_class"] = NormalizedMinistryTeamKeyFormField
        return super().formfield_for_dbfield(db_field, request, **kwargs)

    def get_inline_instances(self, request, obj=None):
        # Parent links require an existing child team; hide the inline on add.
        if obj is None:
            return []
        return super().get_inline_instances(request, obj)

    def get_readonly_fields(self, request, obj=None):
        """Keep a configured technical identity stable in ordinary Admin."""
        readonly = list(super().get_readonly_fields(request, obj))
        if obj is not None and obj.team_key is not None:
            readonly.append("team_key")
        return tuple(readonly)

    def delete_queryset(self, request, queryset):
        current_statuses = (
            TeamAssignment.STATUS_SCHEDULED,
            TeamAssignment.STATUS_CONFIRMED,
            TeamAssignment.STATUS_PREPARED,
        )
        using = queryset.db
        with transaction.atomic(using=using):
            event_ids = tuple(
                TeamAssignment.objects.using(using)
                .filter(
                    ministry_team_id__in=queryset.values("pk"),
                    status__in=current_statuses,
                )
                .values_list("service_event_id", flat=True)
                .distinct()
            )
            if event_ids:
                advance_scheduling_revisions(event_ids, using=using)
            queryset.delete()


class ServiceProfileRequirementProfileChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, profile):
        name = profile.name_en or profile.name
        return f"{name} [{profile.key}] ({profile.event_type})"


class ServiceProfileRequirementTeamChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, team):
        name = team.name_en or team.name
        key = team.team_key or "UNCONFIGURED"
        return f"{name} [{key}]"


class ServiceProfileMinistryRequirementAdminForm(forms.ModelForm):
    service_profile = ServiceProfileRequirementProfileChoiceField(
        queryset=ServiceProfile.objects.none()
    )
    ministry_team = ServiceProfileRequirementTeamChoiceField(
        queryset=MinistryTeam.objects.none()
    )

    class Meta:
        model = ServiceProfileMinistryRequirement
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        current_profile_id = (
            self.instance.service_profile_id if self.instance.pk else None
        )
        current_team_id = (
            self.instance.ministry_team_id if self.instance.pk else None
        )

        profiles = ServiceProfile.objects.filter(is_active=True)
        if current_profile_id is not None:
            profiles = ServiceProfile.objects.filter(
                Q(is_active=True) | Q(pk=current_profile_id)
            )
        self.fields["service_profile"].queryset = profiles.order_by(
            "event_type", "key", "pk"
        )

        eligible_team_ids = []
        candidates = MinistryTeam.objects.filter(
            is_active=True,
            is_assignable=True,
            is_worship_rotation_pool=False,
        ).order_by("pk")
        for team in candidates:
            if resolve_worship_rotation_pool_for_team(team).pool is None:
                eligible_team_ids.append(team.pk)
        if current_team_id is not None:
            eligible_team_ids.append(current_team_id)
        self.fields["ministry_team"].queryset = MinistryTeam.objects.filter(
            pk__in=eligible_team_ids
        ).order_by("name", "name_en", "pk")


@admin.register(ServiceProfileMinistryRequirement)
class ServiceProfileMinistryRequirementAdmin(admin.ModelAdmin):
    form = ServiceProfileMinistryRequirementAdminForm
    list_display = (
        "service_profile_name",
        "service_profile_key",
        "service_profile_event_type",
        "ministry_team_name",
        "ministry_team_key",
        "is_active",
        "sort_order",
    )
    list_filter = ("is_active", "service_profile", "ministry_team")
    search_fields = (
        "service_profile__key",
        "service_profile__name",
        "service_profile__name_en",
        "ministry_team__team_key",
        "ministry_team__name",
        "ministry_team__name_en",
    )
    ordering = (
        "service_profile__key",
        "sort_order",
        "ministry_team__name",
        "pk",
    )
    readonly_fields = ("created_at", "updated_at")
    list_select_related = ("service_profile", "ministry_team")

    @admin.display(description="Service Profile")
    def service_profile_name(self, obj):
        return obj.service_profile.name_en or obj.service_profile.name

    @admin.display(description="Profile key", ordering="service_profile__key")
    def service_profile_key(self, obj):
        return obj.service_profile.key

    @admin.display(
        description="Event type",
        ordering="service_profile__event_type",
    )
    def service_profile_event_type(self, obj):
        return obj.service_profile.event_type

    @admin.display(description="Ministry Team")
    def ministry_team_name(self, obj):
        return obj.ministry_team.name_en or obj.ministry_team.name

    @admin.display(description="Team key", ordering="ministry_team__team_key")
    def ministry_team_key(self, obj):
        return obj.ministry_team.team_key or "UNCONFIGURED"


@admin.register(TeamMembership)
class TeamMembershipAdmin(admin.ModelAdmin):
    list_display = (
        "team",
        "member_display",
        "role",
        "is_active",
        "updated_at",
    )
    list_filter = ("team", "role", "is_active")
    search_fields = (
        "team__name",
        "team__name_en",
        "user__username",
        "user__email",
        "display_name",
        "email",
    )
    readonly_fields = ("created_at", "updated_at")

    @admin.display(description="Member")
    def member_display(self, obj):
        return obj.get_display_name()


@admin.register(TeamAssignment)
class TeamAssignmentAdmin(admin.ModelAdmin):
    list_display = ("service_event", "ministry_team", "status", "created_by", "updated_at")
    list_filter = ("status", "ministry_team", "service_event")
    search_fields = ("service_event__title", "ministry_team__name", "notes")
    readonly_fields = ("created_at", "updated_at")

    def delete_queryset(self, request, queryset):
        using = queryset.db
        with transaction.atomic(using=using):
            event_ids = tuple(
                queryset.filter(
                    status__in=(
                        TeamAssignment.STATUS_SCHEDULED,
                        TeamAssignment.STATUS_CONFIRMED,
                        TeamAssignment.STATUS_PREPARED,
                    )
                )
                .values_list("service_event_id", flat=True)
                .distinct()
            )
            if event_ids:
                advance_scheduling_revisions(event_ids, using=using)
            queryset.delete()


@admin.register(TeamAssignmentMember)
class TeamAssignmentMemberAdmin(admin.ModelAdmin):
    list_display = ("assignment", "membership", "confirmed_at")
    list_filter = ("confirmed_at", "assignment__ministry_team")
    search_fields = (
        "assignment__service_event__title",
        "membership__display_name",
        "membership__user__username",
    )


# --- MINISTRY-STRUCTURE.1B ministry-structure admin (additive, display/setup) ---


@admin.register(MinistryTeamParentLink)
class MinistryTeamParentLinkAdmin(admin.ModelAdmin):
    list_display = (
        "child_team",
        "parent_team",
        "parent_church_unit",
        "is_primary",
        "is_active",
        "sort_order",
    )
    list_filter = ("is_primary", "is_active")
    search_fields = (
        "child_team__name",
        "child_team__name_en",
        "parent_team__name",
        "parent_team__name_en",
        "parent_church_unit__code",
        "parent_church_unit__name",
        "parent_church_unit__name_en",
    )
    raw_id_fields = ("child_team", "parent_team", "parent_church_unit")
    readonly_fields = ("created_at", "updated_at")


@admin.register(MinistryTeamRoleType)
class MinistryTeamRoleTypeAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "name",
        "name_en",
        "is_active",
        "is_system_default",
        "sort_order",
    )
    list_filter = ("is_active", "is_system_default")
    search_fields = ("code", "name", "name_en")
    ordering = ("sort_order", "code")
    readonly_fields = ("created_at", "updated_at")


@admin.register(MinistryTeamRoleProfile)
class MinistryTeamRoleProfileAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "name",
        "name_en",
        "is_active",
        "is_system_default",
        "sort_order",
    )
    list_filter = ("is_active", "is_system_default")
    search_fields = ("code", "name", "name_en")
    ordering = ("sort_order", "code")
    readonly_fields = ("created_at", "updated_at")


@admin.register(MinistryTeamRoleRequirement)
class MinistryTeamRoleRequirementAdmin(admin.ModelAdmin):
    list_display = (
        "profile",
        "role_type",
        "is_required",
        "is_active",
        "sort_order",
    )
    list_filter = ("profile", "role_type", "is_required", "is_active")
    search_fields = (
        "profile__code",
        "profile__name",
        "profile__name_en",
        "role_type__code",
        "role_type__name",
        "role_type__name_en",
    )
    raw_id_fields = ("profile", "role_type")
    ordering = ("profile__sort_order", "sort_order", "role_type__sort_order")
    readonly_fields = ("created_at", "updated_at")


@admin.register(MinistryTeamRoleAssignment)
class MinistryTeamRoleAssignmentAdmin(admin.ModelAdmin):
    list_display = (
        "team",
        "role_type",
        "user",
        "is_active",
        "start_date",
        "end_date",
    )
    list_filter = ("role_type", "is_active", "team__team_kind")
    search_fields = (
        "team__name",
        "team__name_en",
        "role_type__code",
        "role_type__name",
        "role_type__name_en",
        "user__username",
        "user__email",
    )
    raw_id_fields = ("team", "role_type", "user")
    ordering = ("team__name", "role_type__sort_order")
    readonly_fields = ("created_at", "updated_at")
