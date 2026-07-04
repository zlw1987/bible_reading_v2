from django.contrib import admin

from .models import (
    ActivitySignup,
    CommunityActivity,
    CommunityActivityAudienceScope,
    CommunityActivityCoOrganizer,
    CommunityActivitySubmissionBlock,
)


class CommunityActivityAudienceScopeInline(admin.TabularInline):
    model = CommunityActivityAudienceScope
    extra = 0
    autocomplete_fields = ("structure_unit",)


class CommunityActivityCoOrganizerInline(admin.TabularInline):
    model = CommunityActivityCoOrganizer
    extra = 0
    autocomplete_fields = ("user", "added_by")
    readonly_fields = ("created_at",)


@admin.register(CommunityActivity)
class CommunityActivityAdmin(admin.ModelAdmin):
    inlines = (
        CommunityActivityAudienceScopeInline,
        CommunityActivityCoOrganizerInline,
    )
    list_display = (
        "title",
        "start_datetime",
        "status",
        "organizer",
        "created_by",
    )
    list_filter = ("status", "start_datetime")
    search_fields = (
        "title",
        "title_en",
        "description",
        "description_en",
        "organizer",
        "location",
        "location_en",
        "requested_audience_note",
        "review_note",
    )
    readonly_fields = ("reviewed_by", "reviewed_at", "created_at", "updated_at")
    ordering = ("-start_datetime",)


@admin.register(CommunityActivityCoOrganizer)
class CommunityActivityCoOrganizerAdmin(admin.ModelAdmin):
    list_display = ("activity", "user", "added_by", "created_at")
    search_fields = (
        "activity__title",
        "activity__title_en",
        "user__username",
        "user__first_name",
        "user__last_name",
    )
    autocomplete_fields = ("activity", "user", "added_by")
    readonly_fields = ("created_at",)
    ordering = ("-created_at",)


@admin.register(ActivitySignup)
class ActivitySignupAdmin(admin.ModelAdmin):
    list_display = ("activity", "user", "status", "created_at", "updated_at")
    list_filter = ("status", "created_at")
    search_fields = (
        "activity__title",
        "activity__title_en",
        "user__username",
        "user__email",
    )
    autocomplete_fields = ("activity", "user")
    readonly_fields = ("activity", "user", "status", "created_at", "updated_at")
    ordering = ("-created_at",)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(CommunityActivitySubmissionBlock)
class CommunityActivitySubmissionBlockAdmin(admin.ModelAdmin):
    list_display = ("user", "is_active", "created_by", "created_at", "updated_at")
    list_filter = ("is_active", "created_at")
    search_fields = ("user__username", "user__email", "reason")
    autocomplete_fields = ("user",)
    readonly_fields = ("created_by", "created_at", "updated_at")
    ordering = ("-is_active", "user__username")

    def save_model(self, request, obj, form, change):
        if not obj.created_by_id:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)
