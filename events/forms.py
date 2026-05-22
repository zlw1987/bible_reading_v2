from django import forms

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
