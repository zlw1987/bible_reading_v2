from django import forms
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from accounts.models import ChurchStructureUnit, MinistryContext
from ministry.models import MinistryTeam

from .models import ServiceEvent, ServiceEventAudienceScope


FORM_TEXT = {
    "en": {
        "title": "Title",
        "title_en": "English title",
        "description": "Description",
        "description_en": "English description",
        "event_type": "Event Type",
        "start_datetime": "Start Time",
        "end_datetime": "End Time",
        "location": "Location",
        "meeting_link": "Meeting Link",
        "ministry_context": "Host / Language Label",
        "rotation_anchor_team": "Rotation Anchor Team",
        "required_teams": "Required Ministry Teams",
        "audience_units": "Audience Scope",
        "audience_units_help": (
            "Selected units control which ordinary users can see this gathering. "
            "Leave this empty to use the Whole Church / District / Small Group settings below."
        ),
        "audience_scope_root_combo": "Whole Church cannot be combined with other units.",
        "audience_scope_ancestor_combo": (
            "Do not select both a unit and one of its parent or child units."
        ),
        "scope_type": "Audience Scope",
        "district": "District",
        "small_group": "Small Group",
        "status": "Status",
        "sunday_service": "Sunday Service",
        "bible_study": "Bible Study",
        "special_meeting": "Special Meeting",
        "conference": "Conference",
        "gospel_music": "Gospel Music Night",
        "baptism": "Baptism",
        "other": "Other",
        "global": "Global",
        "scope_district": "District",
        "scope_small_group": "Small Group",
        "ministry_context_help": (
            "Optional label for the host, language, or similar ministry context. "
            "Blank can mean whole-church, combined, legacy, or uncategorized. "
            "This is label-only and does not control visibility, serving assignment, or permissions."
        ),
        "rotation_anchor_team_help": (
            "Optional scheduling hint for future copy-forward suggestions, such as Worship C1/C2/C3/A. "
            "This does not make the team required and does not control coverage, audience, visibility, or permissions."
        ),
        "required_teams_help": (
            "Select teams expected for this event. "
            "This records expectations only and does not create team assignments."
        ),
        "scope_type_help": (
            "Current version supports Whole Church, one District, or one Small Group. "
            "Selecting District binds the event at the district level; it does not expand into child small-group selection. "
            "Multi-level and multi-select audience selection belongs to future Church Structure work."
        ),
        "district_help": "Use only when Audience Scope is District.",
        "small_group_help": "Use only when Audience Scope is Small Group.",
        "draft": "Draft",
        "published": "Published",
        "completed": "Completed",
        "cancelled": "Cancelled",
        "title_placeholder": "Service event title",
        "description_placeholder": "Simple event description.",
        "location_placeholder": "Sanctuary, fellowship hall, or online",
        "meeting_link_placeholder": "https://...",
    },
    "zh": {
        "title": "标题",
        "title_en": "英文标题",
        "description": "描述",
        "description_en": "英文描述",
        "event_type": "聚会类型",
        "start_datetime": "开始时间",
        "end_datetime": "结束时间",
        "location": "地点",
        "meeting_link": "会议链接",
        "rotation_anchor_team": "配搭参考团队",
        "audience_units": "适用范围",
        "audience_units_help": (
            "选择的教会结构单元会决定普通用户能否看到这个聚会。"
            "留空则使用下方的全教会 / 区 / 小组设置。"
        ),
        "audience_scope_root_combo": "全教会不能与其他单元同时选择。",
        "audience_scope_ancestor_combo": "不要同时选择一个单元及其上级或下级单元。",
        "scope_type": "范围",
        "required_teams": "需要的事工团队",
        "district": "区",
        "small_group": "小组",
        "status": "状态",
        "sunday_service": "主日崇拜",
        "bible_study": "查经",
        "special_meeting": "特别聚会",
        "conference": "特会",
        "gospel_music": "福音音乐会",
        "baptism": "洗礼",
        "other": "其他",
        "global": "全教会",
        "scope_district": "区",
        "scope_small_group": "小组",
        "draft": "草稿",
        "published": "已发布",
        "completed": "已完成",
        "cancelled": "已取消",
        "title_placeholder": "聚会标题",
        "description_placeholder": "简短说明这个聚会。",
        "location_placeholder": "主堂、副堂、团契厅或线上",
        "meeting_link_placeholder": "https://...",
    },
}


def form_text(language):
    return FORM_TEXT.get(language, FORM_TEXT["en"])


class RequiredTeamChoiceField(forms.ModelMultipleChoiceField):
    def __init__(self, *args, language="en", **kwargs):
        self.language = language
        super().__init__(*args, **kwargs)

    def label_from_instance(self, team):
        return team.get_name(self.language)


class MinistryTeamChoiceField(forms.ModelChoiceField):
    def __init__(self, *args, language="en", **kwargs):
        self.language = language
        super().__init__(*args, **kwargs)

    def label_from_instance(self, team):
        return team.get_name(self.language)


class ChurchStructureUnitMultipleChoiceField(forms.ModelMultipleChoiceField):
    def __init__(self, *args, language="en", **kwargs):
        self.language = language
        super().__init__(*args, **kwargs)

    def label_from_instance(self, unit):
        return unit.path_label(self.language)


def compact_unit_label(unit, language):
    if unit.unit_type == ChurchStructureUnit.UNIT_ROOT:
        return "全教会" if language == "zh" else "Whole Church"
    chain = [
        ancestor
        for ancestor in unit.get_ancestors()
        if ancestor.unit_type != ChurchStructureUnit.UNIT_ROOT
    ]
    chain.append(unit)
    return " > ".join(node.display_name(language) for node in chain)


def validate_audience_unit_combination(form, units, text):
    if any(
        unit.unit_type == ChurchStructureUnit.UNIT_ROOT for unit in units
    ) and len(units) > 1:
        form.add_error("audience_units", text["audience_scope_root_combo"])
        return

    unit_ids = {unit.id for unit in units}
    for unit in units:
        ancestor_ids = {
            ancestor.id for ancestor in unit.get_ancestors() if ancestor.id is not None
        }
        if ancestor_ids & unit_ids:
            form.add_error("audience_units", text["audience_scope_ancestor_combo"])
            return


def save_service_event_audience_units(event, units):
    units = list(units or [])
    with transaction.atomic():
        event.audience_scope_links.all().delete()
        for unit in units:
            ServiceEventAudienceScope.objects.create(service_event=event, unit=unit)


class AudienceUnitOptionsMixin:
    language = "en"

    def add_audience_units_field(self, text):
        self.fields["audience_units"] = ChurchStructureUnitMultipleChoiceField(
            language=self.language,
            queryset=ChurchStructureUnit.objects.filter(is_active=True).order_by(
                "parent_id",
                "sort_order",
                "code",
                "name",
            ),
            required=False,
            label=text["audience_units"],
            help_text=text["audience_units_help"],
        )
        self.fields["audience_units"].initial = self._initial_audience_unit_ids()

    def _initial_audience_unit_ids(self):
        instance = getattr(self, "instance", None)
        if not instance or not instance.pk:
            return []
        return list(instance.get_audience_scope_units().values_list("id", flat=True))

    def clean_audience_units_combination(self, cleaned_data, text):
        validate_audience_unit_combination(
            self,
            list(cleaned_data.get("audience_units") or []),
            text,
        )

    def save_audience_units(self, event):
        save_service_event_audience_units(
            event,
            list(self.cleaned_data.get("audience_units") or []),
        )

    def audience_selected_ids(self):
        raw = self["audience_units"].value() or []
        selected = set()
        for value in raw:
            try:
                selected.add(int(value))
            except (TypeError, ValueError):
                continue
        return selected

    def audience_summary(self):
        count = len(self.audience_selected_ids())
        if self.language == "zh":
            if count:
                return f"适用范围：已选择 {count} 个"
            return "适用范围：未选择"
        if count:
            return f"Audience Scope: {count} selected"
        return "Audience Scope: none selected"

    def _audience_option(
        self,
        unit,
        depth,
        ancestor_ids,
        selected,
        has_children=False,
        orphan=False,
    ):
        compact = compact_unit_label(unit, self.language)
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
            ChurchStructureUnit.objects.filter(is_active=True).order_by(
                "sort_order",
                "code",
                "name",
            )
        )

        children = {}
        for unit in units:
            children.setdefault(unit.parent_id, []).append(unit)
        for group in children.values():
            group.sort(key=lambda u: (u.sort_order, u.code, u.name))

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
            key=lambda u: (
                u.unit_type != ChurchStructureUnit.UNIT_ROOT,
                u.sort_order,
                u.code,
                u.name,
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


class ServiceEventForm(AudienceUnitOptionsMixin, forms.ModelForm):
    rotation_anchor_team = MinistryTeamChoiceField(
        queryset=MinistryTeam.objects.none(),
        required=False,
    )
    required_teams = RequiredTeamChoiceField(
        queryset=MinistryTeam.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )

    class Meta:
        model = ServiceEvent
        fields = [
            "title",
            "title_en",
            "description",
            "description_en",
            "event_type",
            "start_datetime",
            "end_datetime",
            "location",
            "meeting_link",
            "ministry_context",
            "rotation_anchor_team",
            "required_teams",
            "scope_type",
            "district",
            "small_group",
            "status",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 4}),
            "description_en": forms.Textarea(attrs={"rows": 4}),
            "start_datetime": forms.DateTimeInput(
                attrs={"type": "datetime-local"},
                format="%Y-%m-%dT%H:%M",
            ),
            "end_datetime": forms.DateTimeInput(
                attrs={"type": "datetime-local"},
                format="%Y-%m-%dT%H:%M",
            ),
        }

    def __init__(self, *args, language="en", **kwargs):
        super().__init__(*args, **kwargs)
        self.language = language
        text = form_text(language)
        if language == "zh":
            text = {
                **text,
                "ministry_context": "主办/语言标签（可选）",
                "rotation_anchor_team": "配搭参考团队",
                "required_teams": "需要的事工团队",
                "scope_type": "覆盖对象",
                "district": "适用区",
                "small_group": "适用小组",
                "ministry_context_help": (
                    "仅用于标记主办、语言或类似事工背景。"
                    "留空可以表示全教会、联合、旧数据或未分类。"
                    "这是标签用途，不会控制可见范围、服事分配或用户权限。"
                ),
                "required_teams_help": (
                    "选择这个聚会预期需要的事工团队。"
                    "这里只记录需要，不会自动建立服事排班。"
                ),
                "rotation_anchor_team_help": (
                    "可选，用于以后提供复制排班建议，例如 Worship C1/C2/C3/A。"
                    "这不是需要的事工团队，不会控制服事覆盖、覆盖对象、可见范围或用户权限。"
                ),
                "scope_type_help": (
                    "当前版本支持全教会、单一区或单一小组。"
                    "选择“区”表示此聚会事件绑定在区这一层级，不会继续展开下属小组。"
                    "多层级、多选覆盖对象属于后续 Church Structure 工作。"
                ),
                "district_help": "仅在覆盖对象为“区”时使用。",
                "small_group_help": "仅在覆盖对象为“小组”时使用。",
            }

        self.add_audience_units_field(text)

        for field_name in self.fields:
            self.fields[field_name].label = text.get(
                field_name,
                FORM_TEXT["en"].get(field_name, field_name),
            )

        self.fields["event_type"].choices = [
            (ServiceEvent.EVENT_SUNDAY_SERVICE, text["sunday_service"]),
            (ServiceEvent.EVENT_BIBLE_STUDY, text["bible_study"]),
            (ServiceEvent.EVENT_SPECIAL_MEETING, text["special_meeting"]),
            (ServiceEvent.EVENT_CONFERENCE, text["conference"]),
            (ServiceEvent.EVENT_GOSPEL_MUSIC, text["gospel_music"]),
            (ServiceEvent.EVENT_BAPTISM, text["baptism"]),
            (ServiceEvent.EVENT_OTHER, text["other"]),
        ]
        self.fields["scope_type"].choices = [
            (ServiceEvent.SCOPE_GLOBAL, text["global"]),
            (ServiceEvent.SCOPE_DISTRICT, text["scope_district"]),
            (ServiceEvent.SCOPE_SMALL_GROUP, text["scope_small_group"]),
        ]
        if self.instance.status == ServiceEvent.STATUS_CANCELLED:
            status_choices = [(ServiceEvent.STATUS_CANCELLED, text["cancelled"])]
        else:
            status_choices = [
                (ServiceEvent.STATUS_DRAFT, text["draft"]),
                (ServiceEvent.STATUS_PUBLISHED, text["published"]),
                (ServiceEvent.STATUS_COMPLETED, text["completed"]),
            ]
        self.fields["status"].choices = status_choices
        self.fields["title"].widget.attrs.update(
            {"placeholder": text["title_placeholder"]}
        )
        self.fields["description"].widget.attrs.update(
            {"placeholder": text["description_placeholder"]}
        )
        self.fields["location"].widget.attrs.update(
            {"placeholder": text["location_placeholder"]}
        )
        self.fields["meeting_link"].widget.attrs.update(
            {"placeholder": text["meeting_link_placeholder"]}
        )
        self.fields["ministry_context"].help_text = text["ministry_context_help"]
        self.fields["rotation_anchor_team"].help_text = text["rotation_anchor_team_help"]
        self.fields["rotation_anchor_team"].language = language
        self.fields["required_teams"].help_text = text["required_teams_help"]
        self.fields["required_teams"].language = language
        self.fields["scope_type"].help_text = text["scope_type_help"]
        self.fields["district"].help_text = text["district_help"]
        self.fields["small_group"].help_text = text["small_group_help"]
        ministry_context_filter = Q(is_active=True)
        if self.instance.ministry_context_id:
            ministry_context_filter |= Q(id=self.instance.ministry_context_id)
        self.fields["ministry_context"].queryset = MinistryContext.objects.filter(
            ministry_context_filter,
        )
        rotation_anchor_filter = Q(is_active=True)
        if self.instance.rotation_anchor_team_id:
            rotation_anchor_filter |= Q(id=self.instance.rotation_anchor_team_id)
        self.fields["rotation_anchor_team"].queryset = (
            MinistryTeam.objects.filter(rotation_anchor_filter)
            .distinct()
            .order_by("name")
        )
        required_team_filter = Q(is_active=True)
        if self.instance.pk:
            required_team_filter |= Q(required_service_events=self.instance)
        self.fields["required_teams"].queryset = (
            MinistryTeam.objects.filter(required_team_filter)
            .distinct()
            .order_by("name")
        )
        self.fields["start_datetime"].input_formats = ["%Y-%m-%dT%H:%M"]
        self.fields["end_datetime"].input_formats = ["%Y-%m-%dT%H:%M"]

    def clean(self):
        cleaned_data = super().clean()
        self.clean_audience_units_combination(cleaned_data, form_text(self.language))
        return cleaned_data

    def clean_status(self):
        status = self.cleaned_data["status"]
        if (
            self.instance.status == ServiceEvent.STATUS_CANCELLED
            and status != ServiceEvent.STATUS_CANCELLED
        ):
            raise ValidationError(
                "Cancelled service events cannot be reactivated from this form."
            )
        if (
            status == ServiceEvent.STATUS_CANCELLED
            and self.instance.status != ServiceEvent.STATUS_CANCELLED
        ):
            raise ValidationError(
                "Use the dedicated cancel action to cancel a service event."
            )
        return status


class RecurringServiceEventForm(AudienceUnitOptionsMixin, forms.Form):
    WEEKDAY_CHOICES = [
        (0, "Monday"),
        (1, "Tuesday"),
        (2, "Wednesday"),
        (3, "Thursday"),
        (4, "Friday"),
        (5, "Saturday"),
        (6, "Sunday"),
    ]

    title = forms.CharField(max_length=180)
    title_en = forms.CharField(max_length=180, required=False)
    event_type = forms.ChoiceField(choices=ServiceEvent.EVENT_TYPE_CHOICES)
    start_date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    end_date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    weekday = forms.ChoiceField(choices=WEEKDAY_CHOICES)
    start_time = forms.TimeField(
        widget=forms.TimeInput(attrs={"type": "time"}),
        input_formats=["%H:%M"],
    )
    end_time = forms.TimeField(
        required=False,
        widget=forms.TimeInput(attrs={"type": "time"}),
        input_formats=["%H:%M"],
    )
    location = forms.CharField(max_length=180, required=False)
    meeting_link = forms.URLField(max_length=500, required=False)
    ministry_context = forms.ModelChoiceField(
        queryset=MinistryContext.objects.none(),
        required=False,
    )
    scope_type = forms.ChoiceField(choices=ServiceEvent.SCOPE_CHOICES)
    district = forms.ModelChoiceField(
        queryset=ServiceEvent._meta.get_field("district").remote_field.model.objects.all(),
        required=False,
    )
    small_group = forms.ModelChoiceField(
        queryset=ServiceEvent._meta.get_field("small_group").remote_field.model.objects.all(),
        required=False,
    )
    status = forms.ChoiceField(choices=ServiceEvent.STATUS_CHOICES)
    required_teams = RequiredTeamChoiceField(
        queryset=MinistryTeam.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )
    rotation_anchor_team = MinistryTeamChoiceField(
        queryset=MinistryTeam.objects.none(),
        required=False,
    )
    description = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 4}))
    description_en = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 4}))

    def __init__(self, *args, language="en", **kwargs):
        super().__init__(*args, **kwargs)
        self.language = language
        text = form_text(language)
        recurring_labels = {
            "en": {
                "start_date": "Start Date",
                "end_date": "End Date",
                "weekday": "Weekday",
                "start_time": "Start Time",
                "end_time": "End Time",
            },
            "zh": {
                "start_date": "开始日期",
                "end_date": "结束日期",
                "weekday": "星期",
                "start_time": "开始时间",
                "end_time": "结束时间",
            },
        }.get(language, {})

        for field_name in [
            "title",
            "title_en",
            "description",
            "description_en",
            "event_type",
            "location",
            "meeting_link",
            "rotation_anchor_team",
            "required_teams",
            "scope_type",
            "district",
            "small_group",
            "status",
        ]:
            self.fields[field_name].label = text[field_name]
        for field_name, label in recurring_labels.items():
            self.fields[field_name].label = label

        service_event_form = ServiceEventForm(language=language)
        self.fields["ministry_context"].label = service_event_form.fields[
            "ministry_context"
        ].label
        self.fields["ministry_context"].help_text = service_event_form.fields[
            "ministry_context"
        ].help_text
        self.fields["ministry_context"].queryset = MinistryContext.objects.filter(
            is_active=True,
        )
        self.fields["event_type"].choices = service_event_form.fields[
            "event_type"
        ].choices
        self.fields["scope_type"].choices = service_event_form.fields[
            "scope_type"
        ].choices
        self.fields["status"].choices = service_event_form.fields[
            "status"
        ].choices
        for field_name in ["scope_type", "district", "small_group"]:
            self.fields[field_name].label = service_event_form.fields[field_name].label
            self.fields[field_name].help_text = service_event_form.fields[
                field_name
            ].help_text
        self.fields["rotation_anchor_team"].label = service_event_form.fields[
            "rotation_anchor_team"
        ].label
        self.fields["rotation_anchor_team"].help_text = service_event_form.fields[
            "rotation_anchor_team"
        ].help_text
        self.fields["rotation_anchor_team"].language = language
        self.fields["rotation_anchor_team"].queryset = MinistryTeam.objects.filter(
            is_active=True,
        ).order_by("name")
        self.fields["required_teams"].label = service_event_form.fields[
            "required_teams"
        ].label
        self.fields["required_teams"].help_text = service_event_form.fields[
            "required_teams"
        ].help_text
        self.fields["required_teams"].language = language
        self.fields["required_teams"].queryset = MinistryTeam.objects.filter(
            is_active=True,
        ).order_by("name")
        self.add_audience_units_field(text)
        self.fields["weekday"].choices = weekday_choices(language)

        if not self.is_bound:
            self.fields["title"].initial = "主日崇拜"
            self.fields["title_en"].initial = "Sunday Service"
            self.fields["event_type"].initial = ServiceEvent.EVENT_SUNDAY_SERVICE
            self.fields["weekday"].initial = 6
            self.fields["start_time"].initial = "10:00"
            self.fields["end_time"].initial = "11:30"
            self.fields["scope_type"].initial = ServiceEvent.SCOPE_GLOBAL
            self.fields["status"].initial = ServiceEvent.STATUS_PUBLISHED

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get("start_date")
        end_date = cleaned_data.get("end_date")

        if start_date and end_date:
            if start_date > end_date:
                self.add_error("end_date", "End date must be on or after start date.")
            if (end_date - start_date).days > 548:
                self.add_error("end_date", "Date range cannot be longer than 18 months.")

        start_time = cleaned_data.get("start_time")
        end_time = cleaned_data.get("end_time")
        if start_time and end_time and end_time < start_time:
            self.add_error("end_time", "End time cannot be before start time.")

        event = ServiceEvent(
            title=cleaned_data.get("title") or "",
            title_en=cleaned_data.get("title_en") or "",
            description=cleaned_data.get("description") or "",
            description_en=cleaned_data.get("description_en") or "",
            event_type=cleaned_data.get("event_type") or ServiceEvent.EVENT_SUNDAY_SERVICE,
            start_datetime=timezone.now(),
            scope_type=cleaned_data.get("scope_type") or ServiceEvent.SCOPE_GLOBAL,
            district=cleaned_data.get("district"),
            small_group=cleaned_data.get("small_group"),
            status=cleaned_data.get("status") or ServiceEvent.STATUS_PUBLISHED,
        )
        try:
            event.clean()
        except ValidationError as exc:
            for field, errors in exc.message_dict.items():
                self.add_error(field if field in self.fields else None, errors)

        self.clean_audience_units_combination(cleaned_data, form_text(self.language))
        return cleaned_data


def weekday_choices(language):
    if language == "zh":
        return [
            (0, "星期一"),
            (1, "星期二"),
            (2, "星期三"),
            (3, "星期四"),
            (4, "星期五"),
            (5, "星期六"),
            (6, "星期日"),
        ]
    return RecurringServiceEventForm.WEEKDAY_CHOICES
