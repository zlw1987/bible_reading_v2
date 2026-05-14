from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.models import User
from django.db import transaction
from django.contrib.auth.forms import AuthenticationForm, SetPasswordForm, UserCreationForm

from .language import get_user_language
from .models import Profile, SmallGroup
from .ui_text import UI_TEXT


class LocalizedAuthenticationForm(AuthenticationForm):
    def __init__(self, request=None, *args, **kwargs):
        super().__init__(request, *args, **kwargs)

        language = get_user_language(request) if request else "zh"
        ui = UI_TEXT[language]

        self.fields["username"].label = ui["username"]
        self.fields["password"].label = ui["password"]


class SignUpForm(UserCreationForm):
    email = forms.EmailField(required=False)
    small_group = forms.ModelChoiceField(
        queryset=SmallGroup.objects.filter(is_active=True),
        required=False,
        empty_label="No small group yet",
    )

    class Meta:
        model = User
        fields = ("username", "email", "small_group", "password1", "password2")

    def __init__(self, *args, request=None, **kwargs):
        super().__init__(*args, **kwargs)

        language = get_user_language(request) if request else "zh"
        ui = UI_TEXT[language]

        self.fields["username"].label = ui["username"]
        self.fields["email"].label = ui["email_optional"]
        self.fields["small_group"].label = ui["small_group"]
        self.fields["small_group"].empty_label = ui["no_small_group"]
        self.fields["password1"].label = ui["password"]
        self.fields["password2"].label = ui["password_confirmation"]

        self.fields["email"].required = False

    @transaction.atomic
    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data.get("email", "") or ""

        if commit:
            user.save()
            profile, _ = Profile.objects.get_or_create(user=user)
            profile.small_group = self.cleaned_data.get("small_group")
            profile.save()

        return user

class ProfileForm(forms.Form):
    email = forms.EmailField(required=False)
    small_group = forms.ModelChoiceField(
        queryset=SmallGroup.objects.filter(is_active=True),
        required=False,
    )
    preferred_language = forms.ChoiceField(
        choices=Profile.LANGUAGE_CHOICES,
        required=True,
    )

    def __init__(self, *args, user=None, request=None, **kwargs):
        super().__init__(*args, **kwargs)

        if user is None:
            raise ValueError("ProfileForm requires a user.")

        self.user = user
        self.profile, _ = Profile.objects.get_or_create(user=user)

        language = get_user_language(request) if request else self.profile.preferred_language
        ui = UI_TEXT[language]

        self.fields["email"].label = ui["email_optional"]
        self.fields["small_group"].label = ui["small_group"]
        self.fields["small_group"].empty_label = ui["no_small_group"]
        self.fields["preferred_language"].label = ui["preferred_language"]

        if not self.is_bound:
            self.initial["email"] = user.email or ""
            self.initial["small_group"] = self.profile.small_group
            self.initial["preferred_language"] = self.profile.preferred_language

    def save(self):
        email = self.cleaned_data.get("email", "") or ""
        small_group = self.cleaned_data.get("small_group")
        preferred_language = self.cleaned_data["preferred_language"]

        self.user.email = email
        self.user.save(update_fields=["email"])

        self.profile.small_group = small_group
        self.profile.preferred_language = preferred_language
        self.profile.save(update_fields=["small_group", "preferred_language"])

        return self.profile

class StaffPasswordResetForm(SetPasswordForm):
    require_password_change = forms.BooleanField(
        required=False,
        initial=True,
        label="Require user to change password on next login",
    )