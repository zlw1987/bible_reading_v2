from django.contrib import admin
from .models import ChurchRoleAssignment, District, MinistryContext, Profile, SmallGroup


@admin.register(MinistryContext)
class MinistryContextAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "name_en", "is_active", "sort_order", "created_at")
    list_filter = ("is_active",)
    search_fields = ("code", "name", "name_en", "description", "description_en")


@admin.register(District)
class DistrictAdmin(admin.ModelAdmin):
    list_display = ("name", "ministry_context", "is_active", "created_at")
    list_filter = ("ministry_context", "is_active")
    search_fields = (
        "name",
        "ministry_context__code",
        "ministry_context__name",
        "ministry_context__name_en",
    )


@admin.register(SmallGroup)
class SmallGroupAdmin(admin.ModelAdmin):
    list_display = ("name", "district", "is_active")
    list_filter = ("district", "is_active")
    search_fields = ("name", "district__name")


@admin.register(ChurchRoleAssignment)
class ChurchRoleAssignmentAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "role",
        "scope_type",
        "district",
        "small_group",
        "is_active",
        "created_at",
    )
    list_filter = ("role", "scope_type", "district", "small_group", "is_active")
    search_fields = (
        "user__username",
        "user__email",
        "district__name",
        "small_group__name",
    )


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "small_group", "preferred_language", "must_change_password")
    list_filter = ("small_group", "preferred_language", "must_change_password")
    search_fields = ("user__username", "user__email", "small_group__name")
