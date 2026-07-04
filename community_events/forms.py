from django import forms
from django.contrib.auth import get_user_model

from accounts.models import ChurchStructureUnit
from accounts.ordering import (
    order_units_by_sibling_key,
    structure_unit_sibling_sort_key,
)

from .models import CommunityActivity


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


class CommunityActivitySubmissionForm(forms.ModelForm):
    class Meta:
        model = CommunityActivity
        fields = [
            "title",
            "title_en",
            "description",
            "description_en",
            "organizer",
            "start_datetime",
            "end_datetime",
            "location",
            "location_en",
            "requested_audience_note",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 4}),
            "description_en": forms.Textarea(attrs={"rows": 4}),
            "requested_audience_note": forms.Textarea(attrs={"rows": 3}),
            "start_datetime": forms.DateTimeInput(
                attrs={"type": "datetime-local"},
                format="%Y-%m-%dT%H:%M",
            ),
            "end_datetime": forms.DateTimeInput(
                attrs={"type": "datetime-local"},
                format="%Y-%m-%dT%H:%M",
            ),
        }

    def __init__(
        self,
        *args,
        language="en",
        acting_user=None,
        include_co_organizers=True,
        **kwargs,
    ):
        self.language = language
        self.acting_user = acting_user
        self.include_co_organizers = include_co_organizers
        super().__init__(*args, **kwargs)
        labels = {
            "en": {
                "title": "Title",
                "title_en": "English title (optional)",
                "description": "Description",
                "description_en": "English description (optional)",
                "organizer": "Organizer (optional)",
                "co_organizer_users": "Co-organizers (optional)",
                "start_datetime": "Start time",
                "end_datetime": "End time (optional)",
                "location": "Location (optional)",
                "location_en": "English location (optional)",
                "audience_units": "Activity scope",
                "requested_audience_note": "Activity scope note (optional)",
            },
            "zh": {
                "title": "活动名称",
                "title_en": "英文名称（可选）",
                "description": "活动说明",
                "description_en": "英文说明（可选）",
                "organizer": "发起人或团队（可选）",
                "co_organizer_users": "共同发起人（可选）",
                "start_datetime": "开始时间",
                "end_datetime": "结束时间（可选）",
                "location": "地点（可选）",
                "location_en": "英文地点（可选）",
                "audience_units": "活动范围",
                "requested_audience_note": "活动范围说明（可选）",
            },
        }
        selected_labels = labels.get(language, labels["en"])
        if include_co_organizers:
            self.fields["co_organizer_users"] = forms.ModelMultipleChoiceField(
                queryset=get_user_model().objects.filter(is_active=True),
                required=False,
                label=selected_labels["co_organizer_users"],
                widget=forms.MultipleHiddenInput,
                help_text=(
                    "Linked co-organizers may edit this activity while it is "
                    "awaiting publication. The organizer text above remains "
                    "public display copy only."
                    if language != "zh"
                    else "关联的共同发起人可在活动发布前参与修改；上方的发起人文字仍只用于公开显示。"
                ),
            )
        self.fields["audience_units"] = ChurchStructureUnitMultipleChoiceField(
            language=language,
            queryset=order_units_by_sibling_key(
                ChurchStructureUnit.objects.filter(is_active=True),
                language,
            ),
            required=True,
            label=selected_labels["audience_units"],
            help_text=(
                "Choose one or more church groups for the requested activity "
                "scope. The selected scope is not public until staff publish "
                "the activity."
                if language != "zh"
                else "请选择一个或多个教会群体作为申请的活动范围；同工发布活动前，所选范围不会公开。"
            ),
        )
        self.order_fields(
            [
                "title",
                "title_en",
                "description",
                "description_en",
                "organizer",
                "co_organizer_users",
                "start_datetime",
                "end_datetime",
                "location",
                "location_en",
                "audience_units",
                "requested_audience_note",
            ]
        )
        for field_name, label in selected_labels.items():
            if field_name in self.fields:
                self.fields[field_name].label = label

        self.fields["description"].required = True
        self.fields["requested_audience_note"].help_text = (
            "You may explain why you chose this scope or note any scope adjustment "
            "for staff review. Staff will make the final audience and publishing "
            "decision."
            if language != "zh"
            else "你可以在这里说明为什么选择这个范围，或希望同工审核时注意的范围调整。最终范围和发布决定由同工审核。"
        )

    def clean_co_organizer_users(self):
        users = self.cleaned_data.get("co_organizer_users")
        if (
            users is not None
            and self.acting_user is not None
            and users.filter(pk=self.acting_user.pk).exists()
        ):
            raise forms.ValidationError(
                "You are already the primary creator and cannot also be "
                "selected as a co-organizer."
                if self.language != "zh"
                else "你已经是主要发起人，不能再把自己选为共同发起人。"
            )
        return users

    def co_organizer_selected_options(self):
        if "co_organizer_users" not in self.fields:
            return []
        raw_values = self["co_organizer_users"].value() or []
        selected_ids = []
        for value in raw_values:
            try:
                user_id = int(value)
            except (TypeError, ValueError):
                continue
            if user_id not in selected_ids:
                selected_ids.append(user_id)
        users = {
            user.id: user
            for user in get_user_model().objects.filter(
                is_active=True,
                id__in=selected_ids,
            )
        }
        return [
            {
                "id": user_id,
                "display_name": users[user_id].get_full_name().strip()
                or users[user_id].get_username(),
                "username": users[user_id].get_username(),
            }
            for user_id in selected_ids
            if user_id in users
        ]

    def clean(self):
        cleaned_data = super().clean()
        units = list(cleaned_data.get("audience_units") or [])
        if any(
            unit.unit_type == ChurchStructureUnit.UNIT_ROOT for unit in units
        ) and len(units) > 1:
            self.add_error(
                "audience_units",
                (
                    "Whole Church cannot be combined with other units."
                    if self.language != "zh"
                    else "全教会不能与其他单元同时选择。"
                ),
            )
            return cleaned_data

        unit_ids = {unit.id for unit in units}
        for unit in units:
            ancestor_ids = {
                ancestor.id
                for ancestor in unit.get_ancestors()
                if ancestor.id is not None
            }
            if ancestor_ids & unit_ids:
                self.add_error(
                    "audience_units",
                    (
                        "Do not select both a unit and one of its parent or child "
                        "units."
                        if self.language != "zh"
                        else "不要同时选择一个单元及其上级或下级单元。"
                    ),
                )
                break
        return cleaned_data

    def audience_selected_ids(self):
        raw = self["audience_units"].value() or []
        selected = set()
        for value in raw:
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
                visited.add(unit.id)
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
