from django import forms

from accounts.language import normalize_language

from .models import PrayerComment, PrayerReport, PrayerRequest


PRAYER_FORM_TEXT = {
    "en": {
        "title": "Title",
        "prayer_title": "Prayer title",
        "share_prayer": "Share your prayer request...",
        "visibility": "Visibility",
        "post_anonymously": "Post anonymously",
        "comment_anonymously": "Comment anonymously",
        "comment_placeholder": "Write an update or encouragement...",
        "status": "Status",
        "answer_note": "Answer / closing note",
        "answer_note_placeholder": "Optional note about how this prayer was answered or closed.",
        "report_reason": "Reason",
        "report_reason_placeholder": "Please briefly explain why you are reporting this prayer request.",
        "group_required": "You need to belong to a small group to share with your group.",
    },
    "zh": {
        "title": "标题",
        "prayer_title": "代祷标题",
        "share_prayer": "分享你的代祷事项...",
        "visibility": "可见范围",
        "post_anonymously": "匿名发表",
        "comment_anonymously": "匿名回应",
        "comment_placeholder": "写下更新或鼓励...",
        "status": "状态",
        "answer_note": "回应 / 关闭说明",
        "answer_note_placeholder": "可选：说明这项代祷如何被回应或关闭。",
        "report_reason": "原因",
        "report_reason_placeholder": "请简要说明你举报这项代祷的原因。",
        "group_required": "你需要加入小组，才能分享到小组。",
    },
}


VISIBILITY_LABELS = {
    "en": {
        PrayerRequest.VISIBILITY_PRIVATE: "Private",
        PrayerRequest.VISIBILITY_GROUP: "My Group",
        PrayerRequest.VISIBILITY_CHURCH: "Prayer Wall",
    },
    "zh": {
        PrayerRequest.VISIBILITY_PRIVATE: "私人",
        PrayerRequest.VISIBILITY_GROUP: "我的小组",
        PrayerRequest.VISIBILITY_CHURCH: "代祷墙",
    },
}


STATUS_LABELS = {
    "en": {
        PrayerRequest.STATUS_OPEN: "Open",
        PrayerRequest.STATUS_ANSWERED: "Answered",
        PrayerRequest.STATUS_CLOSED: "Closed",
    },
    "zh": {
        PrayerRequest.STATUS_OPEN: "代祷中",
        PrayerRequest.STATUS_ANSWERED: "已回应",
        PrayerRequest.STATUS_CLOSED: "已关闭",
    },
}


def form_text(language, key):
    return PRAYER_FORM_TEXT[normalize_language(language)][key]


def localized_visibility_choices(language):
    labels = VISIBILITY_LABELS[normalize_language(language)]
    return [(value, labels[value]) for value, _label in PrayerRequest.VISIBILITY_CHOICES]


def localized_status_choices(language):
    labels = STATUS_LABELS[normalize_language(language)]
    return [(value, labels[value]) for value, _label in PrayerRequest.STATUS_CHOICES]


class PrayerRequestForm(forms.ModelForm):
    class Meta:
        model = PrayerRequest
        fields = ["title", "body", "visibility", "is_anonymous"]
        widgets = {
            "title": forms.TextInput(
                attrs={
                    "placeholder": "Prayer title",
                }
            ),
            "body": forms.Textarea(
                attrs={
                    "rows": 4,
                    "placeholder": "Share your prayer request...",
                }
            ),
        }
        labels = {
            "title": "Title",
            "body": "",
            "visibility": "Visibility",
            "is_anonymous": "Post anonymously",
        }

    def __init__(self, *args, user=None, language="en", **kwargs):
        super().__init__(*args, **kwargs)

        self.user = user
        self.language = normalize_language(language)
        self.fields["title"].label = form_text(self.language, "title")
        self.fields["title"].widget.attrs["placeholder"] = form_text(
            self.language,
            "prayer_title",
        )
        self.fields["body"].widget.attrs["placeholder"] = form_text(
            self.language,
            "share_prayer",
        )
        self.fields["visibility"].label = form_text(self.language, "visibility")
        self.fields["visibility"].choices = localized_visibility_choices(self.language)
        self.fields["is_anonymous"].label = form_text(self.language, "post_anonymously")
        user_group = getattr(getattr(user, "profile", None), "small_group", None)

        if user_group:
            self.fields["visibility"].initial = PrayerRequest.VISIBILITY_GROUP
        else:
            self.fields["visibility"].initial = PrayerRequest.VISIBILITY_PRIVATE
            self.fields["visibility"].choices = [
                choice
                for choice in localized_visibility_choices(self.language)
                if choice[0] != PrayerRequest.VISIBILITY_GROUP
            ]

        self.fields["is_anonymous"].required = False

    def clean(self):
        cleaned_data = super().clean()

        visibility = cleaned_data.get("visibility")
        user_group = getattr(getattr(self.user, "profile", None), "small_group", None)

        if visibility == PrayerRequest.VISIBILITY_GROUP and not user_group:
            raise forms.ValidationError(form_text(self.language, "group_required"))

        return cleaned_data


class PrayerCommentForm(forms.ModelForm):
    class Meta:
        model = PrayerComment
        fields = ["body", "is_anonymous"]
        widgets = {
            "body": forms.Textarea(
                attrs={
                    "rows": 3,
                    "placeholder": "Write an update or encouragement...",
                }
            )
        }
        labels = {
            "body": "",
            "is_anonymous": "Comment anonymously",
        }

    def __init__(self, *args, language="en", **kwargs):
        super().__init__(*args, **kwargs)

        self.language = normalize_language(language)
        self.fields["body"].widget.attrs["placeholder"] = form_text(
            self.language,
            "comment_placeholder",
        )
        self.fields["is_anonymous"].label = form_text(self.language, "comment_anonymously")


class PrayerStatusForm(forms.ModelForm):
    class Meta:
        model = PrayerRequest
        fields = ["status", "answer_note"]
        widgets = {
            "answer_note": forms.Textarea(
                attrs={
                    "rows": 3,
                    "placeholder": "Optional note about how this prayer was answered or closed.",
                }
            )
        }
        labels = {
            "status": "Status",
            "answer_note": "Answer / closing note",
        }

    def __init__(self, *args, language="en", **kwargs):
        super().__init__(*args, **kwargs)

        self.language = normalize_language(language)
        self.fields["status"].label = form_text(self.language, "status")
        self.fields["status"].choices = localized_status_choices(self.language)
        self.fields["answer_note"].label = form_text(self.language, "answer_note")
        self.fields["answer_note"].widget.attrs["placeholder"] = form_text(
            self.language,
            "answer_note_placeholder",
        )

class PrayerRequestEditForm(forms.ModelForm):
    class Meta:
        model = PrayerRequest
        fields = ["title", "body", "visibility", "is_anonymous"]
        widgets = {
            "title": forms.TextInput(
                attrs={
                    "placeholder": "Prayer title",
                }
            ),
            "body": forms.Textarea(
                attrs={
                    "rows": 5,
                    "placeholder": "Share your prayer request...",
                }
            ),
        }
        labels = {
            "title": "Title",
            "body": "",
            "visibility": "Visibility",
            "is_anonymous": "Post anonymously",
        }

    def __init__(self, *args, user=None, language="en", **kwargs):
        super().__init__(*args, **kwargs)

        self.user = user
        self.language = normalize_language(language)
        self.fields["title"].label = form_text(self.language, "title")
        self.fields["title"].widget.attrs["placeholder"] = form_text(
            self.language,
            "prayer_title",
        )
        self.fields["body"].widget.attrs["placeholder"] = form_text(
            self.language,
            "share_prayer",
        )
        self.fields["visibility"].label = form_text(self.language, "visibility")
        self.fields["visibility"].choices = localized_visibility_choices(self.language)
        self.fields["is_anonymous"].label = form_text(self.language, "post_anonymously")
        user_group = getattr(getattr(user, "profile", None), "small_group", None)

        if not user_group:
            self.fields["visibility"].choices = [
                choice
                for choice in localized_visibility_choices(self.language)
                if choice[0] != PrayerRequest.VISIBILITY_GROUP
            ]

    def clean(self):
        cleaned_data = super().clean()

        visibility = cleaned_data.get("visibility")
        user_group = getattr(getattr(self.user, "profile", None), "small_group", None)

        if visibility == PrayerRequest.VISIBILITY_GROUP and not user_group:
            raise forms.ValidationError(form_text(self.language, "group_required"))

        return cleaned_data


class PrayerCommentEditForm(forms.ModelForm):
    class Meta:
        model = PrayerComment
        fields = ["body", "is_anonymous"]
        widgets = {
            "body": forms.Textarea(
                attrs={
                    "rows": 4,
                    "placeholder": "Write an update or encouragement...",
                }
            )
        }
        labels = {
            "body": "",
            "is_anonymous": "Comment anonymously",
        }

    def __init__(self, *args, language="en", **kwargs):
        super().__init__(*args, **kwargs)

        self.language = normalize_language(language)
        self.fields["body"].widget.attrs["placeholder"] = form_text(
            self.language,
            "comment_placeholder",
        )
        self.fields["is_anonymous"].label = form_text(self.language, "comment_anonymously")


class PrayerReportForm(forms.ModelForm):
    class Meta:
        model = PrayerReport
        fields = ["reason"]
        widgets = {
            "reason": forms.Textarea(
                attrs={
                    "rows": 4,
                    "placeholder": "Please briefly explain why you are reporting this prayer request.",
                }
            )
        }
        labels = {
            "reason": "Reason",
        }

    def __init__(self, *args, language="en", **kwargs):
        super().__init__(*args, **kwargs)

        self.language = normalize_language(language)
        self.fields["reason"].label = form_text(self.language, "report_reason")
        self.fields["reason"].widget.attrs["placeholder"] = form_text(
            self.language,
            "report_reason_placeholder",
        )
