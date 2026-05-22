from django.contrib import admin

from .models import MinistryTeam, TeamMembership


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
        "can_lead",
        "is_active",
        "updated_at",
    )
    list_filter = ("team", "role", "can_lead", "is_active")
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
