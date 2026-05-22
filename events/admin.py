from django.contrib import admin

from .models import ServiceEvent


@admin.register(ServiceEvent)
class ServiceEventAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "event_type",
        "start_datetime",
        "scope_type",
        "status",
        "created_by",
    )
    list_filter = ("event_type", "status", "scope_type", "start_datetime")
    search_fields = ("title", "title_en", "description", "description_en", "location")
    readonly_fields = ("created_at", "updated_at", "published_at")
