from django.contrib import admin

from .models import (
    MinistryTeam,
    TeamAssignment,
    TeamAssignmentMember,
    TeamMembership,
)


@admin.register(MinistryTeam)
class MinistryTeamAdmin(admin.ModelAdmin):
    list_display = ("name", "email_alias", "is_active", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("name", "name_en", "description", "description_en", "email_alias")


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
