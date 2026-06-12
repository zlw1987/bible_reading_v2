from django.contrib import admin
from .models import (
    ChurchRoleAssignment,
    ChurchStructureMembership,
    ChurchStructureUnit,
    District,
    MinistryContext,
    Profile,
    SmallGroup,
)


LEGACY_RUNTIME_NOTE = (
    "Legacy current-runtime / bridge model / 旧模型（当前桥接）: Bible Study "
    "generation and legacy BibleStudySession, reading/progress/privacy "
    "consumers, and ServiceEvent zero-row fallback still use this model and/or "
    "Profile.small_group. Bible Study v2 meeting visibility and role/worship "
    "pickers now use active primary ChurchStructureMembership; ServiceEvent "
    "audience rows also match active primary ChurchStructureMembership. Do not "
    "delete until migration is complete."
)

MINISTRY_CONTEXT_NOTE = (
    "Ministry Context / 事工范围（当前桥接）: Bible Study generation still uses "
    "this short-term bridge. ServiceEvent audience rows now match active "
    "primary ChurchStructureMembership instead of this mapping bridge. Do not "
    "delete until migration is complete."
)

STRUCTURE_UNIT_NOTE = (
    "Church Structure Unit / 教会结构单元（结构基础）: flexible structure "
    "foundation. ServiceEvent audience rows use selected units with active "
    "primary ChurchStructureMembership after CS-CORE.2B-A; Bible Study still "
    "resolves selected units through legacy mappings."
)

MEMBERSHIP_NOTE = (
    "Church Structure Membership / 教会结构归属（归属基础）: runtime source for "
    "ServiceEvent audience-row matching after CS-CORE.2B-A and Bible Study v2 "
    "meeting member visibility after CS-CORE.2C-B. Profile.small_group still "
    "drives reading/progress/privacy and ServiceEvent zero-row legacy fallback. "
    "Membership does not grant permissions, roles, or TeamAssignment/My Serving. "
    "Notes must stay operational and non-sensitive."
)


class LegacyStructureAdminMixin:
    readonly_fields = ("admin_runtime_note", "mapping_status")

    def admin_runtime_note(self, obj=None):
        return LEGACY_RUNTIME_NOTE

    admin_runtime_note.short_description = "Admin clarity note"

    def mapping_status(self, obj):
        if obj and obj.church_structure_unit_id:
            return "Mapped to ChurchStructureUnit / 已映射"
        return "Not mapped / 未映射"

    mapping_status.short_description = "Bridge mapping status"


@admin.register(MinistryContext)
class MinistryContextAdmin(LegacyStructureAdminMixin, admin.ModelAdmin):
    list_display = (
        "code",
        "name",
        "name_en",
        "mapping_status",
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
    fieldsets = (
        (
            "Ministry Contexts / 事工范围（当前桥接）",
            {
                "fields": (
                    "admin_runtime_note",
                    "code",
                    "name",
                    "name_en",
                    "description",
                    "description_en",
                    "is_active",
                    "sort_order",
                    "mapping_status",
                    "church_structure_unit",
                )
            },
        ),
    )

    def admin_runtime_note(self, obj=None):
        return MINISTRY_CONTEXT_NOTE

    admin_runtime_note.short_description = "Admin clarity note"


@admin.register(District)
class DistrictAdmin(LegacyStructureAdminMixin, admin.ModelAdmin):
    list_display = (
        "name",
        "ministry_context",
        "mapping_status",
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
    fieldsets = (
        (
            "Legacy Districts / 旧区（当前仍驱动系统）",
            {
                "fields": (
                    "admin_runtime_note",
                    "name",
                    "ministry_context",
                    "is_active",
                    "mapping_status",
                    "church_structure_unit",
                )
            },
        ),
    )


@admin.register(SmallGroup)
class SmallGroupAdmin(LegacyStructureAdminMixin, admin.ModelAdmin):
    list_display = (
        "name",
        "district",
        "mapping_status",
        "church_structure_unit",
        "is_active",
    )
    list_filter = ("district", "church_structure_unit", "is_active")
    search_fields = (
        "name",
        "district__name",
        "church_structure_unit__code",
        "church_structure_unit__name",
        "church_structure_unit__name_en",
    )
    fieldsets = (
        (
            "Legacy Small Groups / 旧小组（当前仍驱动系统）",
            {
                "fields": (
                    "admin_runtime_note",
                    "name",
                    "district",
                    "is_active",
                    "mapping_status",
                    "church_structure_unit",
                )
            },
        ),
    )


@admin.register(ChurchStructureUnit)
class ChurchStructureUnitAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "name",
        "name_en",
        "unit_type",
        "parent",
        "path_label_en",
        "is_active",
        "sort_order",
    )
    list_filter = ("unit_type", "is_active")
    search_fields = ("code", "name", "name_en")
    ordering = ("parent_id", "sort_order", "code")
    readonly_fields = ("admin_runtime_note", "path_label_en", "created_at", "updated_at")
    fieldsets = (
        (
            "Church Structure Units / 教会结构单元（未来结构基础）",
            {
                "fields": (
                    "admin_runtime_note",
                    "parent",
                    "unit_type",
                    "code",
                    "name",
                    "name_en",
                    "description",
                    "description_en",
                    "is_active",
                    "sort_order",
                    "path_label_en",
                    "created_at",
                    "updated_at",
                )
            },
        ),
    )

    def admin_runtime_note(self, obj=None):
        return STRUCTURE_UNIT_NOTE

    admin_runtime_note.short_description = "Admin clarity note"

    def path_label_en(self, obj):
        if not obj:
            return "Available after save / 保存后可用"
        return obj.path_label("en")

    path_label_en.short_description = "Path label"


@admin.register(ChurchStructureMembership)
class ChurchStructureMembershipAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "unit",
        "membership_type",
        "status",
        "is_primary",
        "start_date",
        "end_date",
        "approved_by",
        "approved_at",
    )
    list_filter = ("status", "membership_type", "is_primary", "unit__unit_type")
    search_fields = (
        "user__username",
        "user__email",
        "unit__code",
        "unit__name",
        "unit__name_en",
    )
    raw_id_fields = ("user", "unit", "approved_by", "requested_by")
    readonly_fields = ("admin_runtime_note", "created_at", "updated_at")
    ordering = ("user__username", "-is_primary", "status", "start_date")
    fieldsets = (
        (
            "Church Structure Memberships / 教会结构归属（未来归属基础）",
            {
                "fields": (
                    "admin_runtime_note",
                    "user",
                    "unit",
                    "membership_type",
                    "status",
                    "is_primary",
                    "start_date",
                    "end_date",
                    "approved_by",
                    "approved_at",
                    "requested_by",
                    "notes",
                    "created_at",
                    "updated_at",
                )
            },
        ),
    )

    def admin_runtime_note(self, obj=None):
        return MEMBERSHIP_NOTE

    admin_runtime_note.short_description = "Admin clarity note"


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
