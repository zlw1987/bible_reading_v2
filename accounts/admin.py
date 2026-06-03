from django.contrib import admin
from .models import (
    ChurchRoleAssignment,
    ChurchStructureUnit,
    District,
    MinistryContext,
    Profile,
    SmallGroup,
)


@admin.register(MinistryContext)
class MinistryContextAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "name",
        "name_en",
        "church_structure_unit",
        "is_active",
        "sort_order",
        "created_at",
    )
    list_filter = ("is_active", "church_structure_unit")
    search_fields = (
        "code",
        "name",
        "name_en",
        "description",
        "description_en",
        "church_structure_unit__code",
        "church_structure_unit__name",
        "church_structure_unit__name_en",
    )


@admin.register(District)
class DistrictAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "ministry_context",
        "church_structure_unit",
        "is_active",
        "created_at",
    )
    list_filter = ("ministry_context", "church_structure_unit", "is_active")
    search_fields = (
        "name",
        "ministry_context__code",
        "ministry_context__name",
        "ministry_context__name_en",
        "church_structure_unit__code",
        "church_structure_unit__name",
        "church_structure_unit__name_en",
    )


@admin.register(SmallGroup)
class SmallGroupAdmin(admin.ModelAdmin):
    list_display = ("name", "district", "church_structure_unit", "is_active")
    list_filter = ("district", "church_structure_unit", "is_active")
    search_fields = (
        "name",
        "district__name",
        "church_structure_unit__code",
        "church_structure_unit__name",
        "church_structure_unit__name_en",
    )


@admin.register(ChurchStructureUnit)
class ChurchStructureUnitAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "name",
        "name_en",
        "unit_type",
        "parent",
        "is_active",
        "sort_order",
    )
    list_filter = ("unit_type", "is_active")
    search_fields = ("code", "name", "name_en")
    ordering = ("parent_id", "sort_order", "code")


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
