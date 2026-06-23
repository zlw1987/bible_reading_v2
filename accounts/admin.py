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
    "Legacy bridge/archive model / 旧模型（桥接/归档）: kept for the "
    "church_structure_unit mapping bridge, admin, audit/diagnostic, and "
    "table-retirement context. These rows are not canonical ordinary-member "
    "belonging. Migrated ordinary-member paths use active primary "
    "ChurchStructureMembership or structure snapshots, including ServiceEvent "
    "audience rows, Bible Study v2 audience rows and role/worship pickers, "
    "prayer groups, group progress, and reflection read/write paths; active "
    "primary ChurchStructureMembership is the canonical belonging source. "
    "V1 Bible Study models/tables are removed by a guarded schema migration "
    "after target DB preflight; V1 is not migrated to membership-core or V2. "
    "V2 Bible Study meeting visibility is structure-native through "
    "BibleStudyMeetingAudienceScope, and Bible Study "
    "generation stays structure-native through generation_key and anchor_unit. "
    "The legacy Profile.small_group field was "
    "removed in PROFILE-SG-FIELD-RETIRE.1A, and the legacy parent/context FKs "
    "SmallGroup.district / District.ministry_context were removed in "
    "LEGACY-PARENT-FK-FIELD-RETIRE.1A; the canonical hierarchy is "
    "ChurchStructureUnit.parent reached through the church_structure_unit "
    "mapping bridge. Zero-row ServiceEvents fail closed for ordinary users. "
    "The church_structure_unit mapping bridge remains live until a separate "
    "approved object-row/table retirement slice; do not delete legacy object "
    "tables or mapping FKs before then."
)

MINISTRY_CONTEXT_NOTE = (
    "Ministry Context / 事工范围（桥接/归档）: retained as a "
    "church_structure_unit mapping bridge and admin/diagnostic context. "
    "ServiceEvent Host/Language display no longer uses a MinistryContext FK "
    "(ServiceEvent.ministry_context was removed); it uses host_language_unit "
    "with an audience-derived structure fallback. ServiceEvent audience rows "
    "match active primary ChurchStructureMembership, and V2 Bible Study "
    "generation is structure-native through BibleStudyMeetingAudienceScope, "
    "generation_key, and anchor_unit, not this mapping bridge. The "
    "MinistryContext.church_structure_unit mapping bridge remains live until a "
    "separate approved object-row/table retirement slice; do not delete the "
    "table or mapping FK before then."
)

STRUCTURE_UNIT_NOTE = (
    "Church Structure Unit / 教会结构单元（结构基础）: flexible structure "
    "foundation and the canonical structure tree. The "
    "ChurchStructureUnit.parent hierarchy is authoritative, and audience rows "
    "and the legacy church_structure_unit mapping bridges depend on these "
    "units. ServiceEvent audience rows use selected units with active "
    "primary ChurchStructureMembership after CS-CORE.2B-A, and V2 Bible Study "
    "meeting visibility and normal generation are structure-native through "
    "BibleStudyMeetingAudienceScope, generation_key, and anchor_unit. "
    "Membership/belonging is separate from serving, TeamAssignment, and role "
    "assignments. Legacy SmallGroup / District / MinistryContext rows remain "
    "only as bridge/admin/diagnostic and table-retirement context."
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
            "Ministry Contexts / 事工范围（桥接/归档）",
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
    # LEGACY-OBJECT-ADMIN-FK.1A: the legacy District.ministry_context parent FK
    # is no longer surfaced here. The mapping bridge (church_structure_unit) and
    # mapping_status remain, since that bridge is still live and data-blocked.
    list_display = (
        "name",
        "mapping_status",
        "church_structure_unit",
        "is_active",
        "created_at",
    )
    list_filter = ("church_structure_unit", "is_active")
    search_fields = (
        "name",
        "church_structure_unit__code",
        "church_structure_unit__name",
        "church_structure_unit__name_en",
    )
    fieldsets = (
        (
            "Legacy Districts / 旧区（桥接/归档）",
            {
                "fields": (
                    "admin_runtime_note",
                    "name",
                    "is_active",
                    "mapping_status",
                    "church_structure_unit",
                )
            },
        ),
    )


@admin.register(SmallGroup)
class SmallGroupAdmin(LegacyStructureAdminMixin, admin.ModelAdmin):
    # LEGACY-OBJECT-ADMIN-FK.1A: the legacy SmallGroup.district parent FK is no
    # longer surfaced here. The mapping bridge (church_structure_unit) and
    # mapping_status remain, since that bridge is still live and data-blocked.
    list_display = (
        "name",
        "mapping_status",
        "church_structure_unit",
        "is_active",
    )
    list_filter = ("church_structure_unit", "is_active")
    search_fields = (
        "name",
        "church_structure_unit__code",
        "church_structure_unit__name",
        "church_structure_unit__name_en",
    )
    fieldsets = (
        (
            "Legacy Small Groups / 旧小组（桥接/归档）",
            {
                "fields": (
                    "admin_runtime_note",
                    "name",
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
