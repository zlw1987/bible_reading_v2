from django.contrib import admin
from django import forms
from django.forms.models import (
    BaseInlineFormSet,
    InlineForeignKeyField,
    construct_instance,
)
from django.db.models import Q

from accounts.models import ChurchStructureUnit
from accounts.ordering import order_units_by_sibling_key

from .models import ServiceEvent, ServiceEventAudienceScope, ServiceEventRequiredTeam


class ServiceEventAudienceScopeInlineFormSet(BaseInlineFormSet):
    zero_message = "Select at least one audience scope unit."
    duplicate_message = "Audience scope cannot include the same unit more than once."
    inactive_message = "Audience scope must use an active church structure unit."
    ancestor_message = (
        "Audience scope cannot include both an ancestor and descendant unit."
    )

    def clean(self):
        if any(self.errors):
            return

        units = []
        for form in self.forms:
            cleaned_data = getattr(form, "cleaned_data", {})
            if not cleaned_data or cleaned_data.get("DELETE"):
                continue

            unit = cleaned_data.get("unit")
            if unit is None:
                continue
            if not unit.is_active:
                form.add_error("unit", self.inactive_message)
                continue
            units.append(unit)

        if any(form.errors for form in self.forms):
            return

        if not units:
            raise forms.ValidationError(self.zero_message)

        unit_ids = [unit.id for unit in units]
        if len(unit_ids) != len(set(unit_ids)):
            raise forms.ValidationError(self.duplicate_message)

        selected_ids = set(unit_ids)
        for unit in units:
            ancestor_ids = {
                ancestor.id
                for ancestor in unit.get_ancestors()
                if ancestor.id is not None
            }
            if ancestor_ids & selected_ids:
                raise forms.ValidationError(self.ancestor_message)

        super().clean()


class ServiceEventAudienceScopeInlineForm(forms.ModelForm):
    """Admin-only form that leaves cross-row audience checks to the formset."""

    inactive_unit_repair_message = (
        "Inactive unit - delete this audience row and add an active replacement "
        "if needed."
    )

    class Meta:
        model = ServiceEventAudienceScope
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            unit_field = self.fields["unit"]
            if self.instance.unit_id:
                unit_field.queryset = order_units_by_sibling_key(
                    ChurchStructureUnit.objects.filter(
                        Q(is_active=True) | Q(pk=self.instance.unit_id)
                    ),
                    "en",
                )
            unit_field.disabled = True

    def _post_clean(self):
        exclude = self._get_validation_exclusions()

        for name, field in self.fields.items():
            if isinstance(field, InlineForeignKeyField):
                exclude.add(name)

        try:
            self.instance = construct_instance(
                self,
                self.instance,
                self._meta.fields,
                self._meta.exclude,
            )
        except forms.ValidationError as exc:
            self._update_errors(exc)

        try:
            self.instance.clean_fields(exclude=exclude)
        except forms.ValidationError as exc:
            self._update_errors(exc)

        try:
            self.instance.validate_constraints(exclude=exclude)
        except forms.ValidationError as exc:
            self._update_errors(exc)

        if self._validate_unique:
            self.validate_unique()


class ServiceEventRequiredTeamInline(admin.TabularInline):
    model = ServiceEventRequiredTeam
    extra = 0
    autocomplete_fields = ("ministry_team",)


class ServiceEventAudienceScopeInline(admin.TabularInline):
    model = ServiceEventAudienceScope
    form = ServiceEventAudienceScopeInlineForm
    formset = ServiceEventAudienceScopeInlineFormSet
    fields = ("unit", "inactive_unit_repair")
    readonly_fields = ("inactive_unit_repair",)
    extra = 1
    min_num = 1

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "unit":
            kwargs["queryset"] = order_units_by_sibling_key(
                ChurchStructureUnit.objects.filter(is_active=True),
                "en",
            )
        formfield = super().formfield_for_foreignkey(db_field, request, **kwargs)
        if db_field.name == "unit":
            formfield.label_from_instance = lambda unit: unit.path_label("en")
        return formfield

    @admin.display(description="Inactive unit")
    def inactive_unit_repair(self, obj):
        if obj and obj.unit_id and not obj.unit.is_active:
            return ServiceEventAudienceScopeInlineForm.inactive_unit_repair_message
        return ""


@admin.register(ServiceEvent)
class ServiceEventAdmin(admin.ModelAdmin):
    inlines = (ServiceEventRequiredTeamInline, ServiceEventAudienceScopeInline)
    list_display = (
        "title",
        "event_type",
        "start_datetime",
        "host_language_unit",
        "rotation_anchor_team",
        "status",
        "created_by",
    )
    list_filter = (
        "event_type",
        "status",
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
        "host_language_unit__code",
        "host_language_unit__name",
        "host_language_unit__name_en",
        "rotation_anchor_team__name",
        "rotation_anchor_team__name_en",
    )
    readonly_fields = ("created_at", "updated_at", "published_at")

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        formfield = super().formfield_for_foreignkey(db_field, request, **kwargs)
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
