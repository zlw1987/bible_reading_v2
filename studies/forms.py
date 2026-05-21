from django import forms

from .models import BibleStudyGuide, BibleStudySeries, BibleStudySession


FORM_TEXT = {
    "en": {
        "series_title": "Title",
        "series_title_en": "English title",
        "description": "Description",
        "description_en": "English description",
        "is_active": "Active",
        "series": "Series",
        "title": "Title",
        "title_en": "English title",
        "scripture_reference": "Scripture",
        "prestudy_datetime": "Thursday Pre-study",
        "study_datetime": "Friday Bible Study",
        "location": "Location",
        "meeting_link": "Meeting Link",
        "scope_type": "Scope",
        "district": "District",
        "small_group": "Small Group",
        "status": "Status",
        "guide_body": "Study Guide",
        "guide_body_en": "English study guide",
        "discussion_questions": "Discussion Questions",
        "discussion_questions_en": "English discussion questions",
        "prestudy_notes": "Pre-study Notes",
        "prestudy_notes_en": "English pre-study notes",
        "global": "Global",
        "scope_district": "District",
        "scope_small_group": "Small Group",
        "draft": "Draft",
        "published": "Published",
        "completed": "Completed",
        "cancelled": "Cancelled",
        "title_placeholder": "Bible study session title",
        "scripture_placeholder": "John 15:1-17",
        "guide_placeholder": "Guidance for leaders and participants.",
        "questions_placeholder": "One question per line works well.",
        "notes_placeholder": "Notes for Thursday pre-study.",
    },
    "zh": {
        "series_title": "标题",
        "series_title_en": "英文标题",
        "description": "描述",
        "description_en": "英文描述",
        "is_active": "启用",
        "series": "系列",
        "title": "标题",
        "title_en": "英文标题",
        "scripture_reference": "经文",
        "prestudy_datetime": "周四预查",
        "study_datetime": "周五查经",
        "location": "地点",
        "meeting_link": "会议链接",
        "scope_type": "范围",
        "district": "区",
        "small_group": "小组",
        "status": "状态",
        "guide_body": "查经指引",
        "guide_body_en": "英文查经指引",
        "discussion_questions": "讨论问题",
        "discussion_questions_en": "英文讨论问题",
        "prestudy_notes": "预查备注",
        "prestudy_notes_en": "英文预查备注",
        "global": "全教会",
        "scope_district": "区",
        "scope_small_group": "小组",
        "draft": "草稿",
        "published": "已发布",
        "completed": "已完成",
        "cancelled": "已取消",
        "title_placeholder": "查经标题",
        "scripture_placeholder": "约翰福音 15:1-17",
        "guide_placeholder": "给带领者和参与者的查经指引。",
        "questions_placeholder": "可以每行一个讨论问题。",
        "notes_placeholder": "周四预查备注。",
    },
}


def form_text(language):
    return FORM_TEXT.get(language, FORM_TEXT["en"])


class BibleStudySeriesForm(forms.ModelForm):
    class Meta:
        model = BibleStudySeries
        fields = ["title", "title_en", "description", "description_en", "is_active"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 4}),
            "description_en": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, language="en", **kwargs):
        super().__init__(*args, **kwargs)
        text = form_text(language)
        self.fields["title"].label = text["series_title"]
        self.fields["title_en"].label = text["series_title_en"]
        self.fields["description"].label = text["description"]
        self.fields["description_en"].label = text["description_en"]
        self.fields["is_active"].label = text["is_active"]


class BibleStudySessionForm(forms.ModelForm):
    class Meta:
        model = BibleStudySession
        fields = [
            "series",
            "title",
            "title_en",
            "scripture_reference",
            "prestudy_datetime",
            "study_datetime",
            "location",
            "meeting_link",
            "scope_type",
            "district",
            "small_group",
            "status",
        ]
        widgets = {
            "prestudy_datetime": forms.DateTimeInput(
                attrs={"type": "datetime-local"},
                format="%Y-%m-%dT%H:%M",
            ),
            "study_datetime": forms.DateTimeInput(
                attrs={"type": "datetime-local"},
                format="%Y-%m-%dT%H:%M",
            ),
        }

    def __init__(self, *args, language="en", **kwargs):
        super().__init__(*args, **kwargs)
        text = form_text(language)

        for field_name in self.fields:
            self.fields[field_name].label = text[field_name]

        self.fields["scope_type"].choices = [
            (BibleStudySession.SCOPE_GLOBAL, text["global"]),
            (BibleStudySession.SCOPE_DISTRICT, text["scope_district"]),
            (BibleStudySession.SCOPE_SMALL_GROUP, text["scope_small_group"]),
        ]
        self.fields["status"].choices = [
            (BibleStudySession.STATUS_DRAFT, text["draft"]),
            (BibleStudySession.STATUS_PUBLISHED, text["published"]),
            (BibleStudySession.STATUS_COMPLETED, text["completed"]),
            (BibleStudySession.STATUS_CANCELLED, text["cancelled"]),
        ]
        self.fields["title"].widget.attrs.update(
            {"placeholder": text["title_placeholder"]}
        )
        self.fields["scripture_reference"].widget.attrs.update(
            {"placeholder": text["scripture_placeholder"]}
        )
        self.fields["prestudy_datetime"].input_formats = ["%Y-%m-%dT%H:%M"]
        self.fields["study_datetime"].input_formats = ["%Y-%m-%dT%H:%M"]


class BibleStudyGuideForm(forms.ModelForm):
    class Meta:
        model = BibleStudyGuide
        fields = [
            "guide_body",
            "guide_body_en",
            "discussion_questions",
            "discussion_questions_en",
            "prestudy_notes",
            "prestudy_notes_en",
        ]
        widgets = {
            "guide_body": forms.Textarea(attrs={"rows": 6}),
            "guide_body_en": forms.Textarea(attrs={"rows": 6}),
            "discussion_questions": forms.Textarea(attrs={"rows": 5}),
            "discussion_questions_en": forms.Textarea(attrs={"rows": 5}),
            "prestudy_notes": forms.Textarea(attrs={"rows": 4}),
            "prestudy_notes_en": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, language="en", **kwargs):
        super().__init__(*args, **kwargs)
        text = form_text(language)

        for field_name in self.fields:
            self.fields[field_name].label = text[field_name]

        self.fields["guide_body"].widget.attrs.update(
            {"placeholder": text["guide_placeholder"]}
        )
        self.fields["discussion_questions"].widget.attrs.update(
            {"placeholder": text["questions_placeholder"]}
        )
        self.fields["prestudy_notes"].widget.attrs.update(
            {"placeholder": text["notes_placeholder"]}
        )
