from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone

from .models import ServiceEvent


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
        "scope_type": "Scope",
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
        "scope_type": "范围",
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


class ServiceEventForm(forms.ModelForm):
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
        text = form_text(language)

        for field_name in self.fields:
            self.fields[field_name].label = text[field_name]

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
        self.fields["status"].choices = [
            (ServiceEvent.STATUS_DRAFT, text["draft"]),
            (ServiceEvent.STATUS_PUBLISHED, text["published"]),
            (ServiceEvent.STATUS_COMPLETED, text["completed"]),
            (ServiceEvent.STATUS_CANCELLED, text["cancelled"]),
        ]
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
        self.fields["start_datetime"].input_formats = ["%Y-%m-%dT%H:%M"]
        self.fields["end_datetime"].input_formats = ["%Y-%m-%dT%H:%M"]


class RecurringServiceEventForm(forms.Form):
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
    description = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 4}))
    description_en = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 4}))

    def __init__(self, *args, language="en", **kwargs):
        super().__init__(*args, **kwargs)
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
            "scope_type",
            "district",
            "small_group",
            "status",
        ]:
            self.fields[field_name].label = text[field_name]
        for field_name, label in recurring_labels.items():
            self.fields[field_name].label = label

        self.fields["event_type"].choices = ServiceEventForm(language=language).fields[
            "event_type"
        ].choices
        self.fields["scope_type"].choices = ServiceEventForm(language=language).fields[
            "scope_type"
        ].choices
        self.fields["status"].choices = ServiceEventForm(language=language).fields[
            "status"
        ].choices
        self.fields["weekday"].choices = weekday_choices(language)

        if not self.is_bound:
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
