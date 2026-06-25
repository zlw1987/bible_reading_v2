from django.db.models import Case, CharField, F, Q, Value, When
from django.db.models.functions import Concat, Lower


def _user_visible_identity_expression(prefix=""):
    return Lower(
        Case(
            When(
                **{
                    f"{prefix}first_name": "",
                    f"{prefix}last_name": "",
                    "then": F(f"{prefix}username"),
                }
            ),
            When(**{f"{prefix}first_name": "", "then": F(f"{prefix}last_name")}),
            When(**{f"{prefix}last_name": "", "then": F(f"{prefix}first_name")}),
            default=Concat(
                f"{prefix}first_name",
                Value(" "),
                f"{prefix}last_name",
            ),
            output_field=CharField(),
        )
    )


def order_users_by_visible_identity(queryset):
    """Order users by their visible full-name-or-username label."""
    return queryset.annotate(
        _visible_identity_order=_user_visible_identity_expression(),
    ).order_by("_visible_identity_order", Lower("username"), "id")


def order_by_related_user_visible_identity(queryset, prefix="user"):
    field_prefix = f"{prefix}__"
    return queryset.annotate(
        _visible_identity_order=_user_visible_identity_expression(field_prefix),
    ).order_by(
        "_visible_identity_order",
        Lower(f"{field_prefix}username"),
        "id",
    )


def _structure_unit_label_expression(language="zh"):
    if language == "en":
        return Case(
            When(name_en="", then=F("name")),
            default=F("name_en"),
            output_field=CharField(),
        )
    return F("name")


def order_units_by_display_label(queryset, language="zh"):
    """Order a flat unit list by the same label the user sees."""
    return queryset.annotate(
        _unit_label_order=Lower(_structure_unit_label_expression(language)),
    ).order_by("_unit_label_order", "code", "id")


def order_units_by_sibling_key(queryset, language="zh"):
    """Order units for parent-local sibling display."""
    return queryset.annotate(
        _unit_label_order=Lower(_structure_unit_label_expression(language)),
    ).order_by("sort_order", "_unit_label_order", "code", "id")


def structure_unit_sibling_sort_key(unit, language="zh"):
    return (
        unit.sort_order,
        (unit.display_name(language) or "").casefold(),
        unit.code or "",
        unit.id or 0,
    )


def _team_membership_visible_identity_expression():
    return Lower(
        Case(
            When(~Q(display_name=""), then=F("display_name")),
            When(user__first_name="", user__last_name="", then=F("user__username")),
            When(user__first_name="", then=F("user__last_name")),
            When(user__last_name="", then=F("user__first_name")),
            When(
                user__isnull=False,
                then=Concat("user__first_name", Value(" "), "user__last_name"),
            ),
            default=F("email"),
            output_field=CharField(),
        )
    )


def order_team_memberships_by_visible_identity(queryset):
    return queryset.annotate(
        _member_label_order=_team_membership_visible_identity_expression(),
    ).order_by("_member_label_order", "user__username", "id")
