from django import forms

from .models import PrayerComment, PrayerRequest


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

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)

        self.user = user
        user_group = getattr(getattr(user, "profile", None), "small_group", None)

        if user_group:
            self.fields["visibility"].initial = PrayerRequest.VISIBILITY_GROUP
        else:
            self.fields["visibility"].initial = PrayerRequest.VISIBILITY_PRIVATE
            self.fields["visibility"].choices = [
                choice
                for choice in PrayerRequest.VISIBILITY_CHOICES
                if choice[0] != PrayerRequest.VISIBILITY_GROUP
            ]

        self.fields["is_anonymous"].required = False

    def clean(self):
        cleaned_data = super().clean()

        visibility = cleaned_data.get("visibility")
        user_group = getattr(getattr(self.user, "profile", None), "small_group", None)

        if visibility == PrayerRequest.VISIBILITY_GROUP and not user_group:
            raise forms.ValidationError(
                "You need to belong to a small group to share with your group."
            )

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

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)

        self.user = user
        user_group = getattr(getattr(user, "profile", None), "small_group", None)

        if not user_group:
            self.fields["visibility"].choices = [
                choice
                for choice in PrayerRequest.VISIBILITY_CHOICES
                if choice[0] != PrayerRequest.VISIBILITY_GROUP
            ]

    def clean(self):
        cleaned_data = super().clean()

        visibility = cleaned_data.get("visibility")
        user_group = getattr(getattr(self.user, "profile", None), "small_group", None)

        if visibility == PrayerRequest.VISIBILITY_GROUP and not user_group:
            raise forms.ValidationError(
                "You need to belong to a small group to share with your group."
            )

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