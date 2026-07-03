from django import template

register = template.Library()


@register.filter
def activity_title(activity, language):
    if not activity:
        return ""
    return activity.get_title(language)


@register.filter
def activity_description(activity, language):
    if not activity:
        return ""
    return activity.get_description(language)


@register.filter
def activity_location(activity, language):
    if not activity:
        return ""
    return activity.get_location(language)


@register.filter
def activity_status_label(activity, language):
    labels = {
        "zh": {
            "draft": "草稿",
            "published": "已发布",
            "cancelled": "已取消",
            "completed": "已结束",
        },
        "en": {
            "draft": "Draft",
            "published": "Published",
            "cancelled": "Cancelled",
            "completed": "Completed",
        },
    }
    return labels.get(language, labels["en"]).get(activity.status, activity.status)
