from django import template
from django.utils import timezone

register = template.Library()

ZH_WEEKDAYS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


def _local_datetime(value):
    if timezone.is_naive(value):
        value = timezone.make_aware(value, timezone.get_current_timezone())
    return timezone.localtime(value, timezone.get_current_timezone())


def _format_english(value):
    hour = value.hour % 12 or 12
    period = "AM" if value.hour < 12 else "PM"
    return f"{value:%a}, {value:%b} {value.day}, {hour}:{value.minute:02d} {period}"


def _format_chinese(value):
    if value.hour < 12:
        period = "上午"
    elif value.hour < 18:
        period = "下午"
    else:
        period = "晚上"

    hour = value.hour % 12 or 12
    weekday = ZH_WEEKDAYS[value.weekday()]
    return f"{value.month}月{value.day}日（{weekday}）{period}{hour}:{value.minute:02d}"


@register.filter
def member_datetime(value, language):
    if not value:
        return ""

    local_value = _local_datetime(value)
    if language == "zh":
        return _format_chinese(local_value)
    return _format_english(local_value)
