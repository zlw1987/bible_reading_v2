from django import forms
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from accounts.models import ChurchStructureUnit
from accounts.ordering import (
    order_units_by_sibling_key,
    structure_unit_sibling_sort_key,
)
from ministry.models import MinistryTeam

from .models import (
    ServiceEvent,
    ServiceEventAudienceScope,
    ServiceEventPlannerAssignment,
)


User = get_user_model()


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
        "required_teams": "Required Ministry Teams",
        "audience_units": "Audience Scope",
        "audience_units_help": (
            "Selected units control which ordinary users can see this gathering. "
            "Select one or more units before saving. Host / Language display is "
            "derived from the selected audience when a matching context exists."
        ),
        "audience_scope_root_combo": "Whole Church cannot be combined with other units.",
        "audience_scope_ancestor_combo": (
            "Do not select both a unit and one of its parent or child units."
        ),
        "status": "Status",
        "sunday_service": "Sunday Service",
        "bible_study": "Bible Study",
        "special_meeting": "Special Meeting",
        "conference": "Conference",
        "gospel_music": "Gospel Music Night",
        "baptism": "Baptism",
        "other": "Other",
        "required_teams_help": (
            "Select teams expected for this event. "
            "This records expectations only and does not create team assignments."
        ),
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
        "audience_units": "适用范围",
        "audience_units_help": (
            "选择的教会结构单元会决定普通用户能否看到这个聚会。"
            "保存前请至少选择一个单元。主办/语言显示会在有对应范围时由所选范围推导。"
        ),
        "audience_scope_root_combo": "全教会不能与其他单元同时选择。",
        "audience_scope_ancestor_combo": "不要同时选择一个单元及其上级或下级单元。",
        "required_teams": "需要的事工团队",
        "status": "状态",
        "sunday_service": "主日崇拜",
        "bible_study": "查经",
        "special_meeting": "特别聚会",
        "conference": "特会",
        "gospel_music": "福音音乐会",
        "baptism": "洗礼",
        "other": "其他",
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
            queryset=order_units_by_sibling_key(
                ChurchStructureUnit.objects.filter(is_active=True),
                self.language,
            ),
            required=True,
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
            order_units_by_sibling_key(
                ChurchStructureUnit.objects.filter(is_active=True),
                self.language,
            )
        )

        children = {}
        for unit in units:
            children.setdefault(unit.parent_id, []).append(unit)
        for group in children.values():
            group.sort(key=lambda u: structure_unit_sibling_sort_key(u, self.language))

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
                *structure_unit_sibling_sort_key(u, self.language),
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
            "required_teams",
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
                "required_teams": "需要的事工团队",
                "required_teams_help": (
                    "选择这个聚会预期需要的事工团队。"
                    "这里只记录需要，不会自动建立服事排班。"
                ),
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
        self.fields["required_teams"].help_text = text["required_teams_help"]
        self.fields["required_teams"].language = language
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
        text = form_text(self.language)
        self.clean_audience_units_combination(cleaned_data, text)
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


class WorshipTeamSelectionForm(forms.Form):
    worship_team = MinistryTeamChoiceField(
        queryset=MinistryTeam.objects.none(),
        required=False,
    )
    expected_updated_at = forms.CharField(widget=forms.HiddenInput)
    expected_anchor_team = forms.CharField(
        required=False,
        widget=forms.HiddenInput,
    )

    def __init__(self, *args, language="en", candidates=(), **kwargs):
        super().__init__(*args, **kwargs)
        candidate_ids = [candidate.team.pk for candidate in candidates]
        self.fields["worship_team"].queryset = MinistryTeam.objects.filter(
            pk__in=candidate_ids
        ).order_by("name", "name_en", "id")
        self.fields["worship_team"].language = language
        self.fields["worship_team"].label = (
            "敬拜团队" if language == "zh" else "Worship Team"
        )
        self.fields["worship_team"].empty_label = (
            "尚未选择敬拜团队"
            if language == "zh"
            else "Worship Team not selected"
        )


class RotationPlannerEventChoiceField(forms.ModelMultipleChoiceField):
    def __init__(self, *args, language="en", **kwargs):
        self.language = language
        super().__init__(*args, **kwargs)

    def label_from_instance(self, event):
        local_start = timezone.localtime(event.start_datetime)
        timestamp = local_start.strftime("%Y-%m-%d %H:%M")
        return f"{timestamp} — {event.get_title(self.language)}"


class WorshipRotationPlannerForm(forms.Form):
    events = RotationPlannerEventChoiceField(
        queryset=ServiceEvent.objects.none(),
        widget=forms.CheckboxSelectMultiple,
    )
    inserted_team = MinistryTeamChoiceField(
        queryset=MinistryTeam.objects.none(),
        required=True,
    )

    def __init__(self, *args, language="en", events=(), candidates=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.language = language
        event_ids = [event.pk for event in events]
        candidate_ids = [candidate.team.pk for candidate in candidates]
        self.fields["events"].queryset = (
            ServiceEvent.objects.filter(pk__in=event_ids)
            .select_related("rotation_anchor_team")
            .order_by("start_datetime", "id")
        )
        self.fields["events"].language = language
        self.fields["inserted_team"].queryset = MinistryTeam.objects.filter(
            pk__in=candidate_ids
        ).order_by("name", "name_en", "id")
        self.fields["inserted_team"].language = language
        if language == "zh":
            self.fields["events"].label = "明确选择每个主日聚会（2–53 场）"
            self.fields["events"].help_text = (
                "若同一主日有多场聚会，请明确选择其中一场；系统不会自动代选。"
            )
            self.fields["inserted_team"].label = "插入的敬拜团队"
        else:
            self.fields["events"].label = (
                "Explicitly select each Sunday event (2–53 events)"
            )
            self.fields["events"].help_text = (
                "When a Sunday has parallel services, explicitly choose one; "
                "the planner never chooses automatically."
            )
            self.fields["inserted_team"].label = "Inserted Worship Team"

    def clean_events(self):
        events = list(self.cleaned_data["events"])
        if not 2 <= len(events) <= 53:
            raise ValidationError(
                "请选择 2 至 53 场聚会。"
                if self.language == "zh"
                else "Select between 2 and 53 events."
            )
        local_dates = [timezone.localtime(event.start_datetime).date() for event in events]
        if len(set(local_dates)) != len(local_dates):
            raise ValidationError(
                "同一主日只能明确选择一场聚会。"
                if self.language == "zh"
                else "Select exactly one event for each represented Sunday."
            )
        return events


class WorshipRotationConfirmationForm(forms.Form):
    proposal = forms.CharField(widget=forms.HiddenInput)


class WorshipWorkbookUploadForm(forms.Form):
    workbook = forms.FileField()

    def __init__(self, *args, language="en", **kwargs):
        super().__init__(*args, **kwargs)
        self.language = language
        self.fields["workbook"].label = (
            "上传 XLSX 工作簿" if language == "zh" else "Upload XLSX workbook"
        )
        self.fields["workbook"].widget.attrs.update(
            {"accept": ".xlsx", "aria-describedby": "xlsx-upload-help"}
        )

    def clean_workbook(self):
        from ministry.services.worship_xlsx_preview import MAX_UPLOAD_BYTES

        uploaded = self.cleaned_data["workbook"]
        if not uploaded.name.lower().endswith(".xlsx"):
            raise ValidationError(
                "只接受 .xlsx 文件。"
                if self.language == "zh"
                else "Only .xlsx files are accepted."
            )
        if uploaded.size > MAX_UPLOAD_BYTES:
            raise ValidationError(
                "文件超过 5 MiB 上限。"
                if self.language == "zh"
                else "The file exceeds the 5 MiB upload limit."
            )
        if uploaded.size <= 0:
            raise ValidationError(
                "上传的文件为空。"
                if self.language == "zh"
                else "The uploaded file is empty."
            )
        return uploaded


class WorshipWorkbookMappingForm(forms.Form):
    signed_workbook = forms.CharField(widget=forms.HiddenInput)

    def __init__(
        self,
        *args,
        language="en",
        token_counts=None,
        candidate_teams=None,
        **kwargs,
    ):
        from ministry.services.worship_xlsx_preview import TOKEN_ORDER

        super().__init__(*args, **kwargs)
        self.language = language
        token_counts = token_counts or {}
        candidate_teams = candidate_teams or {}
        for token in TOKEN_ORDER:
            count = token_counts.get(token, 0)
            if not count:
                continue
            teams = tuple(candidate_teams.get(token, ()))
            field = MinistryTeamChoiceField(
                queryset=MinistryTeam.objects.filter(
                    pk__in=[team.pk for team in teams]
                ).order_by("name", "name_en", "id"),
                required=False,
                language=language,
            )
            field.label = (
                f"工作簿代码 {token} — {count} 个主日"
                if language == "zh"
                else f"Workbook token {token} — {count} Sundays"
            )
            field.empty_label = (
                "请选择符合条件的敬拜团队"
                if language == "zh"
                else "Select an eligible Worship Team"
            )
            if not teams:
                field.help_text = (
                    "目前没有可供此代码选择的有效敬拜团队；相关行将无法完成映射。"
                    if language == "zh"
                    else (
                        "No current canonical Worship candidate is available "
                        "for this token's matched destinations."
                    )
                )
            self.fields[f"mapping_{token.lower()}"] = field

    def selected_mapping(self):
        from ministry.services.worship_xlsx_preview import TOKEN_ORDER

        return {
            token: self.cleaned_data.get(f"mapping_{token.lower()}")
            for token in TOKEN_ORDER
            if f"mapping_{token.lower()}" in self.fields
        }


class WorshipWorkbookConfirmationForm(forms.Form):
    confirmation_proposal = forms.CharField(widget=forms.HiddenInput)


class PlannerUserChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, user):
        full_name = user.get_full_name().strip()
        if full_name:
            return f"{full_name} ({user.get_username()})"
        return user.get_username()


class ServiceEventPlannerAssignmentForm(forms.ModelForm):
    user = PlannerUserChoiceField(queryset=User.objects.none())

    class Meta:
        model = ServiceEventPlannerAssignment
        fields = ["user", "notes"]
        widgets = {"notes": forms.Textarea(attrs={"rows": 2})}

    def __init__(self, *args, service_event, language="en", **kwargs):
        super().__init__(*args, **kwargs)
        self.service_event = service_event
        self.language = language
        self.instance.service_event = service_event
        self.fields["user"].queryset = User.objects.filter(is_active=True).order_by(
            "last_name",
            "first_name",
            "username",
        )

        if language == "zh":
            self.fields["user"].label = "聚会安排人 / 协调人"
            self.fields["user"].help_text = "只能选择当前启用的用户。"
            self.fields["notes"].label = "协调备注（可选）"
            self.fields["notes"].help_text = (
                "只填写非敏感的工作备注；不要填写牧养、医疗、财务或其他隐私信息。"
            )
        else:
            self.fields["user"].label = "Service planner / coordinator"
            self.fields["user"].help_text = "Only currently active users can be selected."
            self.fields["notes"].label = "Coordination notes (optional)"
            self.fields["notes"].help_text = (
                "Operational, non-sensitive notes only; do not include pastoral, "
                "medical, financial, or other private information."
            )

    def clean_user(self):
        user = self.cleaned_data["user"]
        if not user.is_active:
            raise ValidationError(
                "只能选择当前启用的用户。"
                if self.language == "zh"
                else "Only currently active users can be selected."
            )
        if ServiceEventPlannerAssignment.objects.filter(
            service_event=self.service_event,
            user=user,
        ).exists():
            raise ValidationError(
                "这个用户已经有此聚会的安排责任记录；请使用下方的明确恢复操作。"
                if self.language == "zh"
                else (
                    "This user already has a planner responsibility record for "
                    "this event; use the explicit restore action below."
                )
            )
        return user


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
    status = forms.ChoiceField(choices=ServiceEvent.STATUS_CHOICES)
    required_teams = RequiredTeamChoiceField(
        queryset=MinistryTeam.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
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
            "required_teams",
            "status",
        ]:
            self.fields[field_name].label = text[field_name]
        for field_name, label in recurring_labels.items():
            self.fields[field_name].label = label

        service_event_form = ServiceEventForm(language=language)
        self.fields["event_type"].choices = service_event_form.fields[
            "event_type"
        ].choices
        self.fields["status"].choices = service_event_form.fields[
            "status"
        ].choices
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
            status=cleaned_data.get("status") or ServiceEvent.STATUS_PUBLISHED,
        )
        try:
            event.clean()
        except ValidationError as exc:
            for field, errors in exc.message_dict.items():
                self.add_error(field if field in self.fields else None, errors)

        text = form_text(self.language)
        self.clean_audience_units_combination(cleaned_data, text)
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
