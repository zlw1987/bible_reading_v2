from django import forms

from .models import CommunityActivity


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

    def __init__(self, *args, language="en", **kwargs):
        super().__init__(*args, **kwargs)
        labels = {
            "en": {
                "title": "Title",
                "title_en": "English title (optional)",
                "description": "Description",
                "description_en": "English description (optional)",
                "organizer": "Organizer (optional)",
                "start_datetime": "Start time",
                "end_datetime": "End time (optional)",
                "location": "Location (optional)",
                "location_en": "English location (optional)",
                "requested_audience_note": "Requested audience (optional)",
            },
            "zh": {
                "title": "活动名称",
                "title_en": "英文名称（可选）",
                "description": "活动说明",
                "description_en": "英文说明（可选）",
                "organizer": "发起人或团队（可选）",
                "start_datetime": "开始时间",
                "end_datetime": "结束时间（可选）",
                "location": "地点（可选）",
                "location_en": "英文地点（可选）",
                "requested_audience_note": "期望参加范围（可选）",
            },
        }
        selected_labels = labels.get(language, labels["en"])
        for field_name, label in selected_labels.items():
            self.fields[field_name].label = label

        self.fields["description"].required = True
        self.fields["requested_audience_note"].help_text = (
            "You may request a broader audience here. Staff will make the final "
            "audience and publishing decision."
            if language != "zh"
            else "你可以在这里说明期望的参加范围；最终范围和发布决定由同工审核。"
        )
