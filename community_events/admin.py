from django.contrib import admin

from .models import CommunityActivity, CommunityActivityAudienceScope


class CommunityActivityAudienceScopeInline(admin.TabularInline):
    model = CommunityActivityAudienceScope
    extra = 0
    autocomplete_fields = ("structure_unit",)


@admin.register(CommunityActivity)
class CommunityActivityAdmin(admin.ModelAdmin):
    inlines = (CommunityActivityAudienceScopeInline,)
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
    )
    readonly_fields = ("created_at", "updated_at")
    ordering = ("-start_datetime",)
