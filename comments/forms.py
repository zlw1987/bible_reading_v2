from django import forms

from .models import ReflectionComment


class ReflectionCommentForm(forms.ModelForm):
    class Meta:
        model = ReflectionComment
        fields = ["body"]
        widgets = {
            "body": forms.Textarea(attrs={
                "rows": 4,
                "placeholder": "Share your reflection...",
            })
        }
        labels = {
            "body": "",
        }