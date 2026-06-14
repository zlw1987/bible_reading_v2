from django import forms

from accounts.language import normalize_language

from .models import ReflectionComment, ReflectionReport
from .reflection_visibility import get_user_group_reflection_write_context


COMMENT_FORM_TEXT = {
    "en": {
        "share_reflection": "Share your reflection...",
        "write_reply": "Write a reply...",
        "visibility": "Visibility",
        "post_anonymously": "Post anonymously",
        "reply_anonymously": "Reply anonymously",
        "reason": "Reason",
        "report_reason": "Please briefly explain why you are reporting this reflection.",
        "group_required": "You need to belong to a small group to share with your group.",
    },
    "zh": {
        "share_reflection": "分享你的默想...",
        "write_reply": "写下回复...",
        "visibility": "可见范围",
        "post_anonymously": "匿名发表",
        "reply_anonymously": "匿名回复",
        "reason": "原因",
        "report_reason": "请简要说明你举报这条默想的原因。",
        "group_required": "你需要加入小组，才能分享到小组。",
    },
}


VISIBILITY_LABELS = {
    "en": {
        ReflectionComment.VISIBILITY_PRIVATE: "Private",
        ReflectionComment.VISIBILITY_GROUP: "My Group",
        ReflectionComment.VISIBILITY_CHURCH: "Reflection Wall",
    },
    "zh": {
        ReflectionComment.VISIBILITY_PRIVATE: "私人",
        ReflectionComment.VISIBILITY_GROUP: "我的小组",
        ReflectionComment.VISIBILITY_CHURCH: "默想墙",
    },
}


def form_text(language, key):
    return COMMENT_FORM_TEXT[normalize_language(language)][key]


def localized_visibility_choices(language):
    labels = VISIBILITY_LABELS[normalize_language(language)]
    return [(value, labels[value]) for value, _label in ReflectionComment.VISIBILITY_CHOICES]


class ReflectionCommentForm(forms.ModelForm):
    class Meta:
        model = ReflectionComment
        fields = ["body", "visibility", "is_anonymous"]
        widgets = {
            "body": forms.Textarea(
                attrs={
                    "rows": 4,
                    "placeholder": "Share your reflection...",
                }
            )
        }
        labels = {
            "body": "",
            "visibility": "Visibility",
            "is_anonymous": "Post anonymously",
        }

    def __init__(self, *args, user=None, language="en", **kwargs):
        super().__init__(*args, **kwargs)

        self.user = user
        self.language = normalize_language(language)
        self.fields["body"].widget.attrs["placeholder"] = form_text(
            self.language,
            "share_reflection",
        )
        self.fields["visibility"].label = form_text(self.language, "visibility")
        self.fields["visibility"].choices = localized_visibility_choices(self.language)
        self.fields["is_anonymous"].label = form_text(self.language, "post_anonymously")
        # CS-CORE.4G.3: group sharing eligibility is membership-core. A valid
        # active primary small-group ChurchStructureMembership (not
        # Profile.small_group) offers the group choice; everyone else gets the
        # no-group default and the group choice is removed.
        self.write_context = get_user_group_reflection_write_context(user)

        if self.write_context.can_share_to_group:
            self.fields["visibility"].initial = ReflectionComment.VISIBILITY_GROUP
        else:
            self.fields["visibility"].initial = ReflectionComment.VISIBILITY_PRIVATE
            self.fields["visibility"].choices = [
                choice
                for choice in localized_visibility_choices(self.language)
                if choice[0] != ReflectionComment.VISIBILITY_GROUP
            ]

        self.fields["is_anonymous"].required = False

    def clean(self):
        cleaned_data = super().clean()

        visibility = cleaned_data.get("visibility")

        if (
            visibility == ReflectionComment.VISIBILITY_GROUP
            and not self.write_context.can_share_to_group
        ):
            raise forms.ValidationError(form_text(self.language, "group_required"))

        return cleaned_data


class ReflectionReplyForm(forms.ModelForm):
    class Meta:
        model = ReflectionComment
        fields = ["body", "is_anonymous"]
        widgets = {
            "body": forms.Textarea(
                attrs={
                    "rows": 3,
                    "placeholder": "Write a reply...",
                }
            )
        }
        labels = {
            "body": "",
            "is_anonymous": "Reply anonymously",
        }

    def __init__(self, *args, language="en", **kwargs):
        super().__init__(*args, **kwargs)

        self.language = normalize_language(language)
        self.fields["body"].widget.attrs["placeholder"] = form_text(
            self.language,
            "write_reply",
        )
        self.fields["is_anonymous"].label = form_text(self.language, "reply_anonymously")


class ReflectionCommentEditForm(forms.ModelForm):
    class Meta:
        model = ReflectionComment
        fields = ["body", "visibility", "is_anonymous"]
        widgets = {
            "body": forms.Textarea(attrs={"rows": 5}),
        }
        labels = {
            "body": "",
            "visibility": "Visibility",
            "is_anonymous": "Post anonymously",
        }

    def __init__(self, *args, user=None, is_reply=False, language="en", **kwargs):
        super().__init__(*args, **kwargs)

        self.user = user
        self.is_reply = is_reply
        self.language = normalize_language(language)
        self.fields["visibility"].label = form_text(self.language, "visibility")
        self.fields["visibility"].choices = localized_visibility_choices(self.language)
        self.fields["is_anonymous"].label = form_text(self.language, "post_anonymously")

        if is_reply:
            self.fields.pop("visibility", None)
            self.fields["is_anonymous"].label = form_text(self.language, "reply_anonymously")
            return

        # CS-CORE.4G.3: newly entering group visibility is membership-core. An
        # existing group post stays editable as group (Policy C) even if the
        # editor's current membership has changed or disappeared, so the group
        # choice is also offered when the post is already group.
        self.write_context = get_user_group_reflection_write_context(user)
        self.original_is_group = (
            self.instance.pk is not None
            and self.instance.visibility == ReflectionComment.VISIBILITY_GROUP
        )

        if not (self.write_context.can_share_to_group or self.original_is_group):
            self.fields["visibility"].choices = [
                choice
                for choice in localized_visibility_choices(self.language)
                if choice[0] != ReflectionComment.VISIBILITY_GROUP
            ]

    def clean(self):
        cleaned_data = super().clean()

        if self.is_reply:
            return cleaned_data

        visibility = cleaned_data.get("visibility")

        if (
            visibility == ReflectionComment.VISIBILITY_GROUP
            and not self.original_is_group
            and not self.write_context.can_share_to_group
        ):
            raise forms.ValidationError(form_text(self.language, "group_required"))

        return cleaned_data

class ReflectionReportForm(forms.ModelForm):
    class Meta:
        model = ReflectionReport
        fields = ["reason"]
        widgets = {
            "reason": forms.Textarea(
                attrs={
                    "rows": 4,
                    "placeholder": "Please briefly explain why you are reporting this reflection.",
                }
            )
        }
        labels = {
            "reason": "Reason",
        }

    def __init__(self, *args, language="en", **kwargs):
        super().__init__(*args, **kwargs)

        self.language = normalize_language(language)
        self.fields["reason"].label = form_text(self.language, "reason")
        self.fields["reason"].widget.attrs["placeholder"] = form_text(
            self.language,
            "report_reason",
        )
