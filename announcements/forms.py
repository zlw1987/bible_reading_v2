from django import forms
from django.db import transaction

from accounts.models import ChurchStructureUnit
from accounts.ordering import (
    order_units_by_sibling_key,
    structure_unit_sibling_sort_key,
)

from .models import Announcement, AnnouncementAudienceScope


FORM_TEXT = {
    "en": {
        "title": "Title",
        "title_en": "English title (optional)",
        "body": "Body",
        "body_en": "English body (optional)",
        "priority": "Priority",
        "publish_start": "Publish start",
        "publish_end": "Publish end (optional)",
        "audience_units": "Audience scope",
        "audience_help": (
            "Choose the active church structure units whose members may see "
            "this announcement after it is published. A draft may be saved "
            "without an audience, but publishing requires one."
        ),
        "root_overlap": "Whole Church cannot be combined with other units.",
        "ancestor_overlap": (
            "Do not select both a unit and one of its parent or child units."
        ),
    },
    "zh": {
        "title": "标题",
        "title_en": "英文标题（可选）",
        "body": "正文",
        "body_en": "英文正文（可选）",
        "priority": "优先级",
        "publish_start": "开始显示时间",
        "publish_end": "结束显示时间（可选）",
        "audience_units": "适用范围",
        "audience_help": (
            "请选择公告发布后可查看它的教会结构单元。草稿可以暂时不选择范围，"
            "但发布前必须至少选择一个有效范围。"
        ),
        "root_overlap": "全教会不能与其他单元同时选择。",
        "ancestor_overlap": "不要同时选择一个单元及其上级或下级单元。",
    },
}


class ChurchStructureUnitMultipleChoiceField(forms.ModelMultipleChoiceField):
    def __init__(self, *args, language="en", **kwargs):
        self.language = language
        super().__init__(*args, **kwargs)

    def label_from_instance(self, unit):
        return unit.path_label(self.language)


def _compact_unit_label(unit, language):
    if unit.unit_type == ChurchStructureUnit.UNIT_ROOT:
        return "全教会" if language == "zh" else "Whole Church"
    chain = [
        ancestor
        for ancestor in unit.get_ancestors()
        if ancestor.unit_type != ChurchStructureUnit.UNIT_ROOT
    ]
    chain.append(unit)
    return " > ".join(node.display_name(language) for node in chain)


class AnnouncementForm(forms.ModelForm):
    class Meta:
        model = Announcement
        fields = [
            "title",
            "title_en",
            "body",
            "body_en",
            "priority",
            "publish_start",
            "publish_end",
        ]
        widgets = {
            "body": forms.Textarea(attrs={"rows": 6}),
            "body_en": forms.Textarea(attrs={"rows": 6}),
            "publish_start": forms.DateTimeInput(
                attrs={"type": "datetime-local"},
                format="%Y-%m-%dT%H:%M",
            ),
            "publish_end": forms.DateTimeInput(
                attrs={"type": "datetime-local"},
                format="%Y-%m-%dT%H:%M",
            ),
        }

    def __init__(self, *args, language="en", **kwargs):
        self.language = language
        super().__init__(*args, **kwargs)
        text = FORM_TEXT.get(language, FORM_TEXT["en"])
        self.fields["audience_units"] = ChurchStructureUnitMultipleChoiceField(
            language=language,
            queryset=order_units_by_sibling_key(
                ChurchStructureUnit.objects.filter(is_active=True),
                language,
            ),
            required=False,
            label=text["audience_units"],
            help_text=text["audience_help"],
        )
        if self.instance.pk:
            self.fields["audience_units"].initial = list(
                self.instance.audience_scope_links.values_list(
                    "structure_unit_id",
                    flat=True,
                )
            )
        self.order_fields(
            [
                "title",
                "title_en",
                "body",
                "body_en",
                "priority",
                "publish_start",
                "publish_end",
                "audience_units",
            ]
        )
        for field_name, label in text.items():
            if field_name in self.fields:
                self.fields[field_name].label = label
        self.fields["publish_start"].input_formats = ["%Y-%m-%dT%H:%M"]
        self.fields["publish_end"].input_formats = ["%Y-%m-%dT%H:%M"]

    def clean(self):
        cleaned_data = super().clean()
        units = list(cleaned_data.get("audience_units") or [])
        text = FORM_TEXT.get(self.language, FORM_TEXT["en"])
        if any(
            unit.unit_type == ChurchStructureUnit.UNIT_ROOT for unit in units
        ) and len(units) > 1:
            self.add_error("audience_units", text["root_overlap"])
            return cleaned_data

        unit_ids = {unit.id for unit in units}
        for unit in units:
            ancestor_ids = {
                ancestor.id
                for ancestor in unit.get_ancestors()
                if ancestor.id is not None
            }
            if ancestor_ids & unit_ids:
                self.add_error("audience_units", text["ancestor_overlap"])
                break
        return cleaned_data

    def audience_selected_ids(self):
        raw_values = self["audience_units"].value() or []
        selected = set()
        for value in raw_values:
            try:
                selected.add(int(value))
            except (TypeError, ValueError):
                continue
        return selected

    def _audience_option(
        self,
        unit,
        depth,
        ancestor_ids,
        selected,
        *,
        has_children=False,
        orphan=False,
    ):
        compact = _compact_unit_label(unit, self.language)
        return {
            "id": unit.id,
            "parent_id": unit.parent_id,
            "label": unit.display_name(self.language),
            "path_label": compact,
            "search": f"{compact} {unit.code}".lower(),
            "depth": depth,
            "unit_type": unit.unit_type,
            "ancestor_ids": ancestor_ids,
            "has_children": has_children,
            "selected": unit.id in selected,
            "orphan": orphan,
        }

    def audience_unit_options(self):
        selected = self.audience_selected_ids()
        units = list(
            order_units_by_sibling_key(
                ChurchStructureUnit.objects.filter(is_active=True),
                self.language,
            )
        )
        children = {}
        for unit in units:
            children.setdefault(unit.parent_id, []).append(unit)
        for group in children.values():
            group.sort(
                key=lambda unit: structure_unit_sibling_sort_key(
                    unit,
                    self.language,
                )
            )

        options = []
        visited = set()

        def walk(unit, depth, ancestor_ids):
            if unit.id in visited:
                return
            visited.add(unit.id)
            options.append(
                self._audience_option(
                    unit,
                    depth,
                    ancestor_ids,
                    selected,
                    has_children=bool(children.get(unit.id)),
                )
            )
            for child in children.get(unit.id, []):
                walk(child, depth + 1, ancestor_ids + [unit.id])

        roots = [unit for unit in units if unit.parent_id is None]
        roots.sort(
            key=lambda unit: (
                unit.unit_type != ChurchStructureUnit.UNIT_ROOT,
                *structure_unit_sibling_sort_key(unit, self.language),
            )
        )
        for root in roots:
            walk(root, 0, [])

        for unit in units:
            if unit.id not in visited:
                options.append(
                    self._audience_option(
                        unit,
                        0,
                        [],
                        selected,
                        has_children=bool(children.get(unit.id)),
                        orphan=True,
                    )
                )
        return options

    def save_with_audience(self, *, created_by=None):
        """Save announcement fields and replace audience rows atomically."""
        with transaction.atomic():
            announcement = super().save(commit=False)
            if announcement.pk is None:
                announcement.status = Announcement.STATUS_DRAFT
                announcement.created_by = created_by
            announcement.save()
            announcement.audience_scope_links.all().delete()
            for unit in self.cleaned_data.get("audience_units") or []:
                AnnouncementAudienceScope.objects.create(
                    announcement=announcement,
                    structure_unit=unit,
                )
        return announcement
