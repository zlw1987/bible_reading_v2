from django.contrib import admin

from .models import Announcement, AnnouncementAudienceScope


class AnnouncementAudienceScopeInline(admin.TabularInline):
    model = AnnouncementAudienceScope
    extra = 0
    autocomplete_fields = ("structure_unit",)
    readonly_fields = ("created_at",)


@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    inlines = (AnnouncementAudienceScopeInline,)
    list_display = (
        "title",
        "status",
        "priority",
        "publish_start",
        "publish_end",
        "created_by",
        "published_by",
        "published_at",
    )
    list_filter = ("status", "priority", "publish_start", "publish_end")
    search_fields = ("title", "title_en", "body", "body_en")
    autocomplete_fields = ("created_by", "published_by")
    readonly_fields = ("created_at", "updated_at")
    ordering = ("-publish_start",)

    def save_model(self, request, obj, form, change):
        if not obj.created_by_id:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(AnnouncementAudienceScope)
class AnnouncementAudienceScopeAdmin(admin.ModelAdmin):
    list_display = ("announcement", "structure_unit", "created_at")
    list_filter = ("created_at", "structure_unit__unit_type")
    search_fields = (
        "announcement__title",
        "announcement__title_en",
        "structure_unit__code",
        "structure_unit__name",
        "structure_unit__name_en",
    )
    autocomplete_fields = ("announcement", "structure_unit")
    readonly_fields = ("created_at",)
    ordering = ("-created_at",)
