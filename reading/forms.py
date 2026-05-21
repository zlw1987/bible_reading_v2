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
