from django.contrib import admin
from .models import (
    ChurchRoleAssignment,
    ChurchStructureMembership,
    ChurchStructureUnit,
    ChurchStructureUnitRoleAssignment,
    ChurchStructureUnitRoleProfile,
    ChurchStructureUnitRoleRequirement,
    ChurchStructureUnitRoleType,
    Profile,
)

STRUCTURE_UNIT_NOTE = (
    "Church Structure Unit / 教会结构单元（结构基础）: flexible structure "
    "foundation and the canonical structure tree. The "
    "ChurchStructureUnit.parent hierarchy is authoritative, and audience rows "
    "depend on these units. ServiceEvent audience rows use selected units with active "
    "primary ChurchStructureMembership after CS-CORE.2B-A, and V2 Bible Study "
    "meeting visibility and normal generation are structure-native through "
    "BibleStudyMeetingAudienceScope, generation_key, and anchor_unit. "
    "Membership/belonging is separate from serving, TeamAssignment, and role "
    "assignments. Legacy SmallGroup / District / MinistryContext object rows "
    "and schema surfaces have been retired/removed."
)

MEMBERSHIP_NOTE = (
    "Church Structure Membership / 教会结构归属（归属基础）: active primary "
    "membership is the canonical belonging source and the runtime source for "
    "several ordinary-member visibility/access paths, including ServiceEvent "
    "audience rows, Bible Study v2 audience rows and role/worship pickers, "
    "prayer groups, group progress, and reflection read/write paths. The "
    "legacy Profile.small_group field was removed in "
    "PROFILE-SG-FIELD-RETIRE.1A, and V1 Bible Study models/tables are removed "
    "by guarded schema migration. Zero-row ServiceEvents fail closed for ordinary "
    "users. Membership does "
    "not grant staff capabilities, role assignments, or TeamAssignment/My "
    "Serving. Notes must stay operational and non-sensitive."
)


@admin.register(ChurchStructureUnit)
class ChurchStructureUnitAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "name",
        "name_en",
        "unit_type",
        "role_profile",
        "parent",
        "path_label_en",
        "is_active",
        "sort_order",
    )
    list_filter = ("unit_type", "role_profile", "is_active")
    search_fields = ("code", "name", "name_en")
    ordering = ("parent_id", "sort_order", "code")
    readonly_fields = ("admin_runtime_note", "path_label_en", "created_at", "updated_at")
    fieldsets = (
        (
            "Church Structure Units / 教会结构单元（结构基础）",
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
                    "role_profile",
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


@admin.register(ChurchStructureUnitRoleType)
class ChurchStructureUnitRoleTypeAdmin(admin.ModelAdmin):
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


@admin.register(ChurchStructureUnitRoleProfile)
class ChurchStructureUnitRoleProfileAdmin(admin.ModelAdmin):
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


@admin.register(ChurchStructureUnitRoleRequirement)
class ChurchStructureUnitRoleRequirementAdmin(admin.ModelAdmin):
    list_display = (
        "profile",
        "role_type",
        "is_required",
        "is_active",
        "sort_order",
    )
    list_filter = (
        "profile",
        "role_type",
        "is_required",
        "is_active",
    )
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


@admin.register(ChurchStructureUnitRoleAssignment)
class ChurchStructureUnitRoleAssignmentAdmin(admin.ModelAdmin):
    list_display = (
        "unit",
        "role_type",
        "user",
        "is_active",
        "start_date",
        "end_date",
    )
    list_filter = (
        "role_type",
        "is_active",
        "unit__unit_type",
    )
    search_fields = (
        "unit__code",
        "unit__name",
        "unit__name_en",
        "role_type__code",
        "role_type__name",
        "role_type__name_en",
        "user__username",
        "user__email",
    )
    raw_id_fields = ("unit", "role_type", "user")
    ordering = ("unit__parent_id", "unit__sort_order", "role_type__sort_order")
    readonly_fields = ("created_at", "updated_at")


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
            "Church Structure Memberships / 教会结构归属（归属基础）",
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
        "structure_unit",
        "is_active",
        "created_at",
    )
    list_filter = ("role", "scope_type", "structure_unit", "is_active")
    search_fields = (
        "user__username",
        "user__email",
        "structure_unit__code",
        "structure_unit__name",
    )


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "preferred_language", "must_change_password")
    list_filter = ("preferred_language", "must_change_password")
    search_fields = ("user__username", "user__email")
