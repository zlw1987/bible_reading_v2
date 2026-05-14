from django import forms

from .models import ReadingPlan, ReadingPlanDay


class ReadingPlanHeaderForm(forms.ModelForm):
    class Meta:
        model = ReadingPlan
        fields = [
            "name",
            "name_en",
            "description",
            "description_en",
            "is_active",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 4}),
            "description_en": forms.Textarea(attrs={"rows": 4}),
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