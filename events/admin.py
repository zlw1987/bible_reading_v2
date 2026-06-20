from django.contrib import admin

from accounts.models import ChurchStructureUnit

from .models import ServiceEvent, ServiceEventRequiredTeam


class ServiceEventRequiredTeamInline(admin.TabularInline):
    model = ServiceEventRequiredTeam
    extra = 0
    autocomplete_fields = ("ministry_team",)


@admin.register(ServiceEvent)
class ServiceEventAdmin(admin.ModelAdmin):
    inlines = (ServiceEventRequiredTeamInline,)
    list_display = (
        "title",
        "event_type",
        "start_datetime",
        "ministry_context",
        "host_language_unit",
        "rotation_anchor_team",
        "status",
        "created_by",
    )
    list_filter = (
        "event_type",
        "status",
        "ministry_context",
        "host_language_unit",
        "rotation_anchor_team",
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
        "host_language_unit__code",
        "host_language_unit__name",
        "host_language_unit__name_en",
        "rotation_anchor_team__name",
        "rotation_anchor_team__name_en",
    )
    readonly_fields = ("created_at", "updated_at", "published_at")

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        formfield = super().formfield_for_foreignkey(db_field, request, **kwargs)
        if db_field.name == "ministry_context":
            formfield.label = "Host / Language Label"
            formfield.help_text = (
                "Optional label for the host, language, or similar ministry context. "
                "This is label-only and does not control visibility, serving assignment, or permissions."
            )
        if db_field.name == "host_language_unit":
            formfield.label = "Host / Language Unit"
            formfield.queryset = ChurchStructureUnit.objects.filter(
                is_active=True,
                unit_type=ChurchStructureUnit.UNIT_MINISTRY_CONTEXT,
            ).order_by("sort_order", "code", "name")
            formfield.help_text = (
                "Structure-native display-only Host / Language context. "
                "This does not control visibility, serving assignment, or permissions."
            )
        if db_field.name == "rotation_anchor_team":
            formfield.label = "Rotation Anchor Team"
            formfield.help_text = (
                "Optional scheduling hint for future copy-forward suggestions. "
                "This does not make the team required and does not control coverage, audience, visibility, or permissions."
            )
        return formfield
