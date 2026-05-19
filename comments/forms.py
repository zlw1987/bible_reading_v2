from django import forms

from .models import ReflectionComment, ReflectionReport


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

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)

        self.user = user
        user_group = getattr(getattr(user, "profile", None), "small_group", None)

        if user_group:
            self.fields["visibility"].initial = ReflectionComment.VISIBILITY_GROUP
        else:
            self.fields["visibility"].initial = ReflectionComment.VISIBILITY_PRIVATE
            self.fields["visibility"].choices = [
                choice
                for choice in ReflectionComment.VISIBILITY_CHOICES
                if choice[0] != ReflectionComment.VISIBILITY_GROUP
            ]

        self.fields["is_anonymous"].required = False

    def clean(self):
        cleaned_data = super().clean()

        visibility = cleaned_data.get("visibility")
        user_group = getattr(getattr(self.user, "profile", None), "small_group", None)

        if visibility == ReflectionComment.VISIBILITY_GROUP and not user_group:
            raise forms.ValidationError(
                "You need to belong to a small group to share with your group."
            )

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

    def __init__(self, *args, user=None, is_reply=False, **kwargs):
        super().__init__(*args, **kwargs)

        self.user = user
        self.is_reply = is_reply

        if is_reply:
            self.fields.pop("visibility", None)
            self.fields["is_anonymous"].label = "Reply anonymously"
            return

        user_group = getattr(getattr(user, "profile", None), "small_group", None)

        if not user_group:
            self.fields["visibility"].choices = [
                choice
                for choice in ReflectionComment.VISIBILITY_CHOICES
                if choice[0] != ReflectionComment.VISIBILITY_GROUP
            ]

    def clean(self):
        cleaned_data = super().clean()

        if self.is_reply:
            return cleaned_data

        visibility = cleaned_data.get("visibility")
        user_group = getattr(getattr(self.user, "profile", None), "small_group", None)

        if visibility == ReflectionComment.VISIBILITY_GROUP and not user_group:
            raise forms.ValidationError(
                "You need to belong to a small group to share with your group."
            )

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