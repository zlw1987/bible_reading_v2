from django.contrib import admin

from .models import ServiceEvent


@admin.register(ServiceEvent)
class ServiceEventAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "event_type",
        "start_datetime",
        "ministry_context",
        "scope_type",
        "status",
        "created_by",
    )
    list_filter = (
        "event_type",
        "status",
        "scope_type",
        "ministry_context",
        "start_datetime",
    )
    search_fields = (
        "title",
        "title_en",
        "description",
        "description_en",
        "location",
        "ministry_context__code",
        "ministry_context__name",
        "ministry_context__name_en",
    )
    readonly_fields = ("created_at", "updated_at", "published_at")

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        formfield = super().formfield_for_foreignkey(db_field, request, **kwargs)
        if db_field.name == "ministry_context":
            formfield.label = "Ministry Context Label"
            formfield.help_text = (
                "Optional label for CM, EM, or a similar ministry context. "
                "This does not control visibility, assignment filtering, or audience scope."
            )
        return formfield
