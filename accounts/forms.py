from django import forms
from django.contrib.auth.models import User
from django.db import transaction
from django.contrib.auth.forms import AuthenticationForm, SetPasswordForm, UserCreationForm

from .language import get_user_language
from .models import (
    ChurchStructureMembership,
    ChurchStructureUnit,
    Profile,
    SmallGroup,
)
from .ui_text import UI_TEXT


def requestable_signup_units():
    return ChurchStructureUnit.objects.filter(
        is_active=True,
        unit_type__in=[
            ChurchStructureUnit.UNIT_SMALL_GROUP,
            ChurchStructureUnit.UNIT_FELLOWSHIP,
        ],
    ).order_by("parent_id", "sort_order", "code", "name")


def create_or_update_signup_membership_request(user, requested_unit):
    membership = (
        ChurchStructureMembership.objects
        .filter(
            user=user,
            status=ChurchStructureMembership.STATUS_REQUESTED,
        )
        .order_by("id")
        .first()
    )

    if membership:
        membership.unit = requested_unit
        membership.membership_type = (
            ChurchStructureMembership.TYPE_SMALL_GROUP_MEMBER
        )
        membership.is_primary = False
        membership.requested_by = user
        membership.approved_by = None
        membership.approved_at = None
        membership.start_date = None
        membership.save()
        return membership

    return ChurchStructureMembership.objects.create(
        user=user,
        unit=requested_unit,
        membership_type=ChurchStructureMembership.TYPE_SMALL_GROUP_MEMBER,
        status=ChurchStructureMembership.STATUS_REQUESTED,
        is_primary=False,
        requested_by=user,
    )


class LocalizedAuthenticationForm(AuthenticationForm):
    def __init__(self, request=None, *args, **kwargs):
        super().__init__(request, *args, **kwargs)

        language = get_user_language(request) if request else "zh"
        ui = UI_TEXT[language]

        self.fields["username"].label = ui["username"]
        self.fields["password"].label = ui["password"]


class SignUpForm(UserCreationForm):
    email = forms.EmailField(required=False)
    requested_unit = forms.ModelChoiceField(
        queryset=ChurchStructureUnit.objects.none(),
        required=False,
        empty_label="No small group yet",
    )

    class Meta:
        model = User
        fields = ("username", "email", "requested_unit", "password1", "password2")

    def __init__(self, *args, request=None, **kwargs):
        super().__init__(*args, **kwargs)

        language = get_user_language(request) if request else "zh"
        ui = UI_TEXT[language]

        self.fields["username"].label = ui["username"]
        self.fields["email"].label = ui["email_optional"]
        self.fields["requested_unit"].queryset = requestable_signup_units()
        self.fields["requested_unit"].label = ui["requested_unit"]
        self.fields["requested_unit"].empty_label = ui["no_small_group"]
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
            profile.save()
            requested_unit = self.cleaned_data.get("requested_unit")
            if requested_unit:
                create_or_update_signup_membership_request(user, requested_unit)

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
