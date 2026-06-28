from django.contrib import admin
from .models import (
    ChurchMemberRecord,
    ChurchRoleAssignment,
    ChurchStructureMembership,
    ChurchStructureUnit,
    ChurchStructureUnitMemberRecord,
    ChurchStructureUnitRoleAssignment,
    ChurchStructureUnitRoleProfile,
    ChurchStructureUnitRoleRequirement,
    ChurchStructureUnitRoleType,
    Profile,
    ServingReadinessPolicy,
    ServingReadinessRequirement,
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


MEMBER_RECORD_NOTE = (
    "Church Member Record / 教会成员记录（成员事实）: a global, church-wide "
    "member fact record. V1 records Faith Statement / 信仰宣言 status and "
    "baptism facts only. Course/training progress (e.g. C201 / 认识我们的教会 / "
    "福音真理班 / 受浸预备班 / 基础真理班) belongs to a future course/training "
    "module and is NOT stored here. This record does not grant serving "
    "eligibility by itself; serving readiness is future configurable, "
    "warning-only policy computed on demand, never a stored boolean. Belonging "
    "remains ChurchStructureMembership; serving assignments remain "
    "TeamAssignmentMember / BibleStudyMeetingRole. Notes must stay operational "
    "and non-sensitive."
)


UNIT_MEMBER_RECORD_NOTE = (
    "Church Structure Unit Member Record / 单元成员记录（单元关怀）: "
    "unit-specific operational/care data (attendance state, when the person "
    "joined this unit, unit-local group notes, and restricted care/follow-up "
    "notes). This is NOT canonical belonging — canonical belonging remains "
    "ChurchStructureMembership. Global church-wide facts (Faith Statement / "
    "信仰宣言, baptism) remain ChurchMemberRecord. Serving remains "
    "TeamAssignmentMember / BibleStudyMeetingRole. A unit member record does "
    "not grant membership, serving, audience visibility, permissions, or "
    "management rights. Privacy boundary: group_notes and care_followup_notes "
    "are sensitive and must NOT be exposed to ordinary users or delegated unit "
    "leads until a later privacy/permission slice explicitly approves scoped "
    "access; this data is admin-only for now."
)

SERVING_READINESS_POLICY_NOTE = (
    "Serving Readiness Policy / 服事预备政策（仅提醒）: a configurable, "
    "warning-only church rule describing which ChurchMemberRecord facts and "
    "statuses count as 'ready to serve.' It does NOT grant any permission or "
    "capability, does NOT block any assignment by itself, and does NOT store a "
    "per-user readiness result — readiness is computed on demand by the "
    "evaluator (accounts.serving_readiness), never a stored boolean. "
    "Requirements currently support Faith Statement and baptism facts from "
    "ChurchMemberRecord only. Belonging remains ChurchStructureMembership and "
    "serving remains TeamAssignmentMember / BibleStudyMeetingRole."
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


@admin.register(ChurchMemberRecord)
class ChurchMemberRecordAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "faith_statement_status",
        "baptism_status",
        "updated_at",
    )
    list_filter = ("faith_statement_status", "baptism_status")
    search_fields = (
        "user__username",
        "user__first_name",
        "user__last_name",
        "user__email",
    )
    raw_id_fields = ("user", "created_by", "updated_by")
    readonly_fields = ("admin_runtime_note", "created_at", "updated_at")
    ordering = ("user__username",)
    fieldsets = (
        (
            "Church Member Records / 教会成员记录（成员事实）",
            {
                "fields": (
                    "admin_runtime_note",
                    "user",
                    "faith_statement_status",
                    "faith_statement_signed_date",
                    "baptism_status",
                    "baptism_date",
                    "notes",
                    "created_by",
                    "updated_by",
                    "created_at",
                    "updated_at",
                )
            },
        ),
    )

    def admin_runtime_note(self, obj=None):
        return MEMBER_RECORD_NOTE

    admin_runtime_note.short_description = "Admin clarity note"


@admin.register(ChurchStructureUnitMemberRecord)
class ChurchStructureUnitMemberRecordAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "unit",
        "attendance_state",
        "joined_unit_date",
        "updated_at",
    )
    list_filter = ("attendance_state", "unit__unit_type")
    search_fields = (
        "user__username",
        "user__email",
        "user__first_name",
        "user__last_name",
        "unit__code",
        "unit__name",
        "unit__name_en",
    )
    raw_id_fields = ("user", "unit", "updated_by")
    readonly_fields = ("admin_runtime_note", "created_at", "updated_at")
    ordering = ("unit", "user__username")
    fieldsets = (
        (
            "Unit Member Records / 单元成员记录（单元关怀）",
            {
                "fields": (
                    "admin_runtime_note",
                    "unit",
                    "user",
                    "attendance_state",
                    "joined_unit_date",
                    "group_notes",
                    "care_followup_notes",
                    "updated_by",
                    "created_at",
                    "updated_at",
                )
            },
        ),
    )

    def admin_runtime_note(self, obj=None):
        return UNIT_MEMBER_RECORD_NOTE

    admin_runtime_note.short_description = "Admin clarity note"


class ServingReadinessRequirementInline(admin.TabularInline):
    model = ServingReadinessRequirement
    extra = 0
    fields = (
        "requirement_type",
        "accepted_statuses",
        "severity",
        "label",
        "label_en",
        "is_active",
        "sort_order",
    )


@admin.register(ServingReadinessPolicy)
class ServingReadinessPolicyAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "display_name",
        "is_default",
        "is_active",
        "sort_order",
    )
    list_filter = ("is_default", "is_active")
    search_fields = ("code", "name", "name_en")
    readonly_fields = ("admin_runtime_note", "created_at", "updated_at")
    ordering = ("sort_order", "code")
    inlines = (ServingReadinessRequirementInline,)
    fieldsets = (
        (
            "Serving Readiness Policy / 服事预备政策（仅提醒）",
            {
                "fields": (
                    "admin_runtime_note",
                    "code",
                    "name",
                    "name_en",
                    "description",
                    "description_en",
                    "is_default",
                    "is_active",
                    "sort_order",
                    "created_at",
                    "updated_at",
                )
            },
        ),
    )

    def display_name(self, obj):
        return obj.display_name("zh")

    display_name.short_description = "Name"

    def admin_runtime_note(self, obj=None):
        return SERVING_READINESS_POLICY_NOTE

    admin_runtime_note.short_description = "Admin clarity note"


@admin.register(ServingReadinessRequirement)
class ServingReadinessRequirementAdmin(admin.ModelAdmin):
    list_display = (
        "policy",
        "requirement_type",
        "severity",
        "accepted_statuses",
        "is_active",
        "sort_order",
    )
    list_filter = ("policy", "requirement_type", "severity", "is_active")
    search_fields = (
        "policy__code",
        "policy__name",
        "label",
        "label_en",
    )
    autocomplete_fields = ("policy",)
    readonly_fields = ("admin_runtime_note", "created_at", "updated_at")
    ordering = ("policy", "sort_order")
    fieldsets = (
        (
            "Serving Readiness Requirement / 服事预备要求（仅提醒）",
            {
                "fields": (
                    "admin_runtime_note",
                    "policy",
                    "requirement_type",
                    "accepted_statuses",
                    "severity",
                    "label",
                    "label_en",
                    "message",
                    "message_en",
                    "is_active",
                    "sort_order",
                    "created_at",
                    "updated_at",
                )
            },
        ),
    )

    def admin_runtime_note(self, obj=None):
        return SERVING_READINESS_POLICY_NOTE

    admin_runtime_note.short_description = "Admin clarity note"


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "preferred_language", "must_change_password")
    list_filter = ("preferred_language", "must_change_password")
    search_fields = ("user__username", "user__email")
