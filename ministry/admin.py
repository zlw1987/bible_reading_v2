from django.contrib import admin

from .models import (
    MinistryTeam,
    MinistryTeamParentLink,
    MinistryTeamRoleAssignment,
    MinistryTeamRoleProfile,
    MinistryTeamRoleRequirement,
    MinistryTeamRoleType,
    TeamAssignment,
    TeamAssignmentMember,
    TeamMembership,
)


# MINISTRY-STRUCTURE.1B admin (additive). Ministry structure is NOT church
# structure; a ChurchStructureUnit parent link is a display anchor only. Parent
# links and role assignments here do not grant membership, audience visibility,
# serving, or runtime permissions. TeamMembership.role / can_lead remains the
# current permission source; MinistryTeamRoleAssignment is additive only in this
# foundation phase. The key warnings are also carried on model field help_text.


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
        "team_kind",
        "is_assignable",
        "role_profile",
        "email_alias",
        "is_active",
        "updated_at",
    )
    list_filter = ("team_kind", "is_assignable", "is_active")
    search_fields = ("name", "name_en", "description", "description_en", "email_alias")
    raw_id_fields = ("role_profile",)
    inlines = (MinistryTeamParentLinkInline,)

    def get_inline_instances(self, request, obj=None):
        # Parent links require an existing child team; hide the inline on add.
        if obj is None:
            return []
        return super().get_inline_instances(request, obj)


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
