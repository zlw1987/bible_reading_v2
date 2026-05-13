from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.db import transaction

from .models import Profile, SmallGroup


class SignUpForm(UserCreationForm):
    email = forms.EmailField(required=True)
    small_group = forms.ModelChoiceField(
        queryset=SmallGroup.objects.filter(is_active=True),
        required=False,
        label="Small group",
        empty_label="No small group yet",
    )

    class Meta:
        model = User
        fields = ("username", "email", "small_group", "password1", "password2")

    @transaction.atomic
    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]

        if commit:
            user.save()
            profile, _ = Profile.objects.get_or_create(user=user)
            profile.small_group = self.cleaned_data.get("small_group")
            profile.save()

        return user