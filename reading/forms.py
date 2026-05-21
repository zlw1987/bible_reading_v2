from django import forms

from .models import ReadingGuidePost, ReadingPlan, ReadingPlanDay


GUIDE_FORM_TEXT = {
    "en": {
        "title": "Title",
        "title_en": "English title",
        "body": "Body",
        "body_en": "English body",
        "guide_type": "Guide type",
        "week_number": "Week",
        "day_number": "Day",
        "is_pinned": "Pinned",
        "is_published": "Published",
        "title_placeholder": "Short guide title",
        "title_en_placeholder": "Optional English title",
        "body_placeholder": "Share pastoral or coworker guidance for this plan.",
        "body_en_placeholder": "Optional English guidance.",
        "week_placeholder": "Week number",
        "day_placeholder": "Day number",
        "general": "General",
        "weekly": "Weekly",
        "daily": "Daily",
    },
    "zh": {
        "title": "标题",
        "title_en": "英文标题",
        "body": "内容",
        "body_en": "英文内容",
        "guide_type": "指引类型",
        "week_number": "周",
        "day_number": "日",
        "is_pinned": "置顶",
        "is_published": "已发布",
        "title_placeholder": "简短的指引标题",
        "title_en_placeholder": "可选英文标题",
        "body_placeholder": "分享给这个读经计划的牧者或同工指引。",
        "body_en_placeholder": "可选英文指引内容。",
        "week_placeholder": "周数",
        "day_placeholder": "天数",
        "general": "通用",
        "weekly": "每周",
        "daily": "每日",
    },
}


class ReadingPlanHeaderForm(forms.ModelForm):
    class Meta:
        model = ReadingPlan
        fields = [
            "name",
            "name_en",
            "description",
            "description_en",
            "introduction",
            "introduction_en",
            "reading_guidance",
            "reading_guidance_en",
            "pastoral_note",
            "pastoral_note_en",
            "is_active",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 4}),
            "description_en": forms.Textarea(attrs={"rows": 4}),
            "introduction": forms.Textarea(attrs={"rows": 5}),
            "introduction_en": forms.Textarea(attrs={"rows": 5}),
            "reading_guidance": forms.Textarea(attrs={"rows": 5}),
            "reading_guidance_en": forms.Textarea(attrs={"rows": 5}),
            "pastoral_note": forms.Textarea(attrs={"rows": 5}),
            "pastoral_note_en": forms.Textarea(attrs={"rows": 5}),
        }


class ReadingPlanDayLineForm(forms.ModelForm):
    class Meta:
        model = ReadingPlanDay
        fields = [
            "day_number",
            "reading_text",
            "memory_verse",
        ]
        widgets = {
            "reading_text": forms.Textarea(attrs={"rows": 3}),
        }


class ReadingPlanDayCreateForm(forms.ModelForm):
    class Meta:
        model = ReadingPlanDay
        fields = [
            "day_number",
            "reading_text",
            "memory_verse",
        ]
        widgets = {
            "reading_text": forms.Textarea(attrs={"rows": 3}),
        }


class ReadingGuidePostForm(forms.ModelForm):
    class Meta:
        model = ReadingGuidePost
        fields = [
            "title",
            "title_en",
            "body",
            "body_en",
            "guide_type",
            "week_number",
            "day_number",
            "is_pinned",
            "is_published",
        ]
        widgets = {
            "body": forms.Textarea(attrs={"rows": 6}),
            "body_en": forms.Textarea(attrs={"rows": 6}),
        }

    def __init__(self, *args, language="en", **kwargs):
        super().__init__(*args, **kwargs)
        text = GUIDE_FORM_TEXT.get(language, GUIDE_FORM_TEXT["en"])

        for field_name in self.fields:
            self.fields[field_name].label = text[field_name]

        self.fields["guide_type"].choices = [
            (ReadingGuidePost.GUIDE_GENERAL, text["general"]),
            (ReadingGuidePost.GUIDE_WEEKLY, text["weekly"]),
            (ReadingGuidePost.GUIDE_DAILY, text["daily"]),
        ]

        self.fields["title"].widget.attrs.update(
            {"placeholder": text["title_placeholder"]}
        )
        self.fields["title_en"].widget.attrs.update(
            {"placeholder": text["title_en_placeholder"]}
        )
        self.fields["body"].widget.attrs.update(
            {"placeholder": text["body_placeholder"]}
        )
        self.fields["body_en"].widget.attrs.update(
            {"placeholder": text["body_en_placeholder"]}
        )
        self.fields["week_number"].widget.attrs.update(
            {"placeholder": text["week_placeholder"]}
        )
        self.fields["day_number"].widget.attrs.update(
            {"placeholder": text["day_placeholder"]}
        )
