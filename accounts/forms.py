from django import forms
from django.contrib.auth import password_validation
from django.contrib.auth import get_user_model
from django.contrib.auth.models import User
from django.contrib.auth.validators import UnicodeUsernameValidator
from django.db import transaction
from django.utils import timezone
from django.contrib.auth.forms import (
    AuthenticationForm,
    PasswordChangeForm,
    SetPasswordForm,
    UserCreationForm,
)

from .language import get_user_language
from .models import (
    ChurchStructureMembership,
    ChurchStructureUnit,
    Profile,
)
from .ordering import (
    order_units_by_display_label,
    order_users_by_visible_identity,
)
from .ui_text import UI_TEXT


def requestable_signup_units(language="zh"):
    return order_units_by_display_label(
        ChurchStructureUnit.objects.filter(
            is_active=True,
            unit_type__in=[
                ChurchStructureUnit.UNIT_SMALL_GROUP,
                ChurchStructureUnit.UNIT_FELLOWSHIP,
            ],
        ),
        language,
    )


class RequestableUnitChoiceField(forms.ModelChoiceField):
    def __init__(self, *args, language="zh", **kwargs):
        self.language = language
        super().__init__(*args, **kwargs)

    def label_from_instance(self, obj):
        return obj.display_name(self.language)


class StructureSetupUserChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        label = obj.get_full_name() or obj.username
        if obj.email:
            return f"{label} ({obj.username}, {obj.email})"
        if label != obj.username:
            return f"{label} ({obj.username})"
        return obj.username


class StructureMembershipAddForm(forms.Form):
    user = StructureSetupUserChoiceField(queryset=User.objects.none())
    membership_type = forms.ChoiceField(
        choices=ChurchStructureMembership.MEMBERSHIP_TYPE_CHOICES,
        initial=ChurchStructureMembership.TYPE_MEMBER,
    )
    start_date = forms.DateField(
        initial=timezone.localdate,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    is_primary = forms.BooleanField(required=False)
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text=(
            "Operational/non-sensitive notes only. Do not store counseling, "
            "pastoral, medical, financial, or private information."
        ),
    )

    def __init__(self, *args, unit=None, **kwargs):
        super().__init__(*args, **kwargs)
        if unit is None:
            raise ValueError("StructureMembershipAddForm requires a unit.")
        self.unit = unit
        UserModel = get_user_model()
        self.fields["user"].queryset = order_users_by_visible_identity(
            UserModel.objects.filter(is_active=True)
        )

    def clean(self):
        cleaned_data = super().clean()
        user = cleaned_data.get("user")
        start_date = cleaned_data.get("start_date")

        if self.unit and not self.unit.is_active:
            raise forms.ValidationError(
                "Active memberships can only be added to active structure units."
            )

        if user and start_date:
            duplicate = ChurchStructureMembership.active_for_user(
                user,
                target_date=start_date,
            ).filter(unit=self.unit)
            if duplicate.exists():
                raise forms.ValidationError(
                    "This user already has an active membership for this unit."
                )

        return cleaned_data

    @transaction.atomic
    def save(self, *, approved_by):
        user = self.cleaned_data["user"]
        is_primary = self.cleaned_data.get("is_primary", False)

        if is_primary:
            ChurchStructureMembership.objects.filter(
                user=user,
                status=ChurchStructureMembership.STATUS_ACTIVE,
                is_primary=True,
            ).update(is_primary=False)

        return ChurchStructureMembership.objects.create(
            user=user,
            unit=self.unit,
            membership_type=self.cleaned_data["membership_type"],
            status=ChurchStructureMembership.STATUS_ACTIVE,
            is_primary=is_primary,
            start_date=self.cleaned_data["start_date"],
            requested_by=approved_by,
            approved_by=approved_by,
            approved_at=timezone.now(),
            notes=self.cleaned_data.get("notes", ""),
        )


class ChurchStructureUnitChildForm(forms.ModelForm):
    class Meta:
        model = ChurchStructureUnit
        fields = ["name", "name_en", "code", "unit_type", "sort_order"]

    def __init__(self, *args, parent=None, **kwargs):
        super().__init__(*args, **kwargs)
        if parent is None:
            raise ValueError("ChurchStructureUnitChildForm requires a parent.")
        self.parent = parent
        self.instance.parent = parent
        self.instance.is_active = True
        self.fields["unit_type"].choices = [
            choice
            for choice in ChurchStructureUnit.UNIT_TYPE_CHOICES
            if choice[0] != ChurchStructureUnit.UNIT_ROOT
        ]

    def clean(self):
        cleaned_data = super().clean()
        if not self.parent.is_active:
            raise forms.ValidationError(
                "Child units can only be added under active structure units."
            )
        if cleaned_data.get("unit_type") == ChurchStructureUnit.UNIT_ROOT:
            raise forms.ValidationError("Root units cannot be created as children.")
        return cleaned_data


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


# Django's built-in password validators raise ValidationError with a stable
# ``code`` per failure. We translate by code (not by matching the English
# string) so behaviour stays version-robust.
PASSWORD_VALIDATION_MESSAGES = {
    "zh": {
        "password_too_short": "密码太短，至少需要 8 个字符。",
        "password_too_common": "这个密码太常见，请换一个更安全的密码。",
        "password_entirely_numeric": "密码不能全部是数字。",
        "password_too_similar": "密码不能与用户名或个人资料太相似。",
    },
}


class LocalizedPasswordValidationMixin:
    """Localize built-in password-validator error messages by error code.

    Django runs every configured ``AUTH_PASSWORD_VALIDATORS`` validator through
    ``validate_password_for_user``. We keep that call exactly as-is, so the
    validation itself is unchanged, and only swap the *displayed* message for
    known error codes when the active language is Chinese. Unknown codes fall
    back to Django's original message, and English keeps Django's defaults.
    """

    password_error_language = "en"

    def validate_password_for_user(self, user, password_field_name="password2"):
        password = self.cleaned_data.get(password_field_name)
        if not password:
            return
        try:
            password_validation.validate_password(password, user)
        except forms.ValidationError as error:
            self.add_error(password_field_name, self._localize_password_error(error))

    def _localize_password_error(self, error):
        messages = PASSWORD_VALIDATION_MESSAGES.get(self.password_error_language)
        if not messages:
            return error

        localized = []
        for sub_error in error.error_list:
            code = getattr(sub_error, "code", None)
            message = messages.get(code)
            if message:
                localized.append(forms.ValidationError(message, code=code))
            else:
                localized.append(sub_error)
        return forms.ValidationError(localized)

    def localize_set_password_fields(self, language):
        """Localize new-password labels/help/mismatch error for set-password
        style forms (``SetPasswordForm`` / ``PasswordChangeForm`` subclasses)."""
        self.password_error_language = language
        ui = UI_TEXT[language]
        self.fields["new_password1"].label = ui["new_password"]
        self.fields["new_password2"].label = ui["new_password_confirmation"]
        if language == "zh":
            self.fields["new_password1"].help_text = ui["password_help"]
            self.fields["new_password2"].help_text = ui["password_confirmation_help"]
            self.error_messages["password_mismatch"] = ui["password_mismatch"]


class LocalizedAuthenticationForm(AuthenticationForm):
    def __init__(self, request=None, *args, **kwargs):
        super().__init__(request, *args, **kwargs)

        language = get_user_language(request) if request else "zh"
        ui = UI_TEXT[language]

        self.fields["username"].label = ui["username"]
        self.fields["password"].label = ui["password"]

        if language == "zh":
            # English login errors are reasonable as-is; localize for Chinese.
            self.error_messages["invalid_login"] = ui["invalid_login"]


class LocalizedPasswordChangeForm(LocalizedPasswordValidationMixin, PasswordChangeForm):
    def __init__(self, user, *args, request=None, **kwargs):
        super().__init__(user, *args, **kwargs)

        language = get_user_language(request) if request else "zh"
        ui = UI_TEXT[language]

        self.fields["old_password"].label = ui["old_password"]
        # Localizes new-password labels/help/mismatch + enables zh validator
        # error translation (validators themselves are unchanged).
        self.localize_set_password_fields(language)

        if language == "zh":
            self.error_messages["password_incorrect"] = ui["old_password_incorrect"]


class SignUpForm(LocalizedPasswordValidationMixin, UserCreationForm):
    email = forms.EmailField(required=False)
    requested_unit = RequestableUnitChoiceField(
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
        self.language = language
        self._ui = ui
        self.password_error_language = language

        self.fields["username"].label = ui["username"]
        self.fields["email"].label = ui["email_optional"]
        self.fields["requested_unit"].queryset = requestable_signup_units(language)
        self.fields["requested_unit"].language = language
        self.fields["requested_unit"].label = ui["requested_small_group"]
        self.fields["requested_unit"].empty_label = ui["no_small_group"]
        self.fields["requested_unit"].help_text = ui["requested_small_group_help"]
        self.fields["password1"].label = ui["password"]
        self.fields["password2"].label = ui["password_confirmation"]

        if language == "zh":
            # Django's defaults for these help texts / errors are English only.
            # Replace the displayed strings for Chinese without touching the
            # password validators themselves (validation behaviour unchanged).
            self.fields["username"].help_text = ui["username_help"]
            self.fields["password1"].help_text = ui["password_help"]
            self.fields["password2"].help_text = ui["password_confirmation_help"]
            self.error_messages["password_mismatch"] = ui["password_mismatch"]
            self._localize_username_invalid_message(ui["username_invalid"])

        self.fields["email"].required = False

    def _localize_username_invalid_message(self, message):
        # Replace only the username regex validator with a fresh instance that
        # carries a localized message. A new instance avoids mutating Django's
        # shared module-level validator (which would leak across all forms); the
        # regex/behaviour is identical, only the displayed message changes.
        localized = []
        for validator in self.fields["username"].validators:
            if getattr(validator, "code", None) == "invalid":
                localized.append(UnicodeUsernameValidator(message=message))
            else:
                localized.append(validator)
        self.fields["username"].validators = localized

    def clean_username(self):
        # Preserve the pre-existing duplicate-username behaviour. Before UI-H.6
        # this form had no clean_username and inherited Django's
        # UserCreationForm.clean_username, which rejects usernames differing only
        # in case (docstring "Reject usernames that differ only in case.";
        # query username__iexact). We keep that exact semantics and only swap in
        # a localized message — switching to an exact match would *loosen*
        # uniqueness and change behaviour, which is out of scope for an i18n task.
        username = self.cleaned_data.get("username")
        if (
            username
            and self._meta.model.objects.filter(username__iexact=username).exists()
        ):
            raise forms.ValidationError(self._ui["username_taken"], code="unique")
        return username

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
    requested_unit = RequestableUnitChoiceField(
        queryset=ChurchStructureUnit.objects.none(),
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
        self.fields["requested_unit"].queryset = requestable_signup_units(language)
        self.fields["requested_unit"].language = language
        self.fields["requested_unit"].label = ui["requested_small_group"]
        self.fields["requested_unit"].empty_label = ui["no_small_group"]
        self.fields["requested_unit"].help_text = ui["profile_requested_small_group_help"]
        self.fields["preferred_language"].label = ui["preferred_language"]

        if not self.is_bound:
            self.initial["email"] = user.email or ""
            self.initial["preferred_language"] = self.profile.preferred_language

    @transaction.atomic
    def save(self):
        email = self.cleaned_data.get("email", "") or ""
        requested_unit = self.cleaned_data.get("requested_unit")
        preferred_language = self.cleaned_data["preferred_language"]

        self.user.email = email
        self.user.save(update_fields=["email"])

        self.profile.preferred_language = preferred_language
        self.profile.save(update_fields=["preferred_language"])

        if requested_unit:
            create_or_update_signup_membership_request(self.user, requested_unit)

        return self.profile

class StaffPasswordResetForm(LocalizedPasswordValidationMixin, SetPasswordForm):
    require_password_change = forms.BooleanField(
        required=False,
        initial=True,
        label="Require user to change password on next login",
    )

    def __init__(self, user, *args, request=None, **kwargs):
        super().__init__(user, *args, **kwargs)

        language = get_user_language(request) if request else "zh"
        ui = UI_TEXT[language]
        # Localizes new-password labels/help/mismatch + zh validator errors.
        self.localize_set_password_fields(language)
        self.fields["require_password_change"].label = ui["require_password_change_label"]
