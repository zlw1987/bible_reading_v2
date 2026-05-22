from django import template

register = template.Library()


@register.filter
def event_title(event, language):
    if not event:
        return ""
    return event.get_title(language)


@register.filter
def event_description(event, language):
    if not event:
        return ""
    return event.get_description(language)


@register.filter
def event_type_label(event, language):
    labels = {
        "zh": {
            "sunday_service": "主日崇拜",
            "bible_study": "查经",
            "special_meeting": "特别聚会",
            "conference": "特会",
            "gospel_music": "福音音乐会",
            "baptism": "洗礼",
            "other": "其他",
        },
        "en": {
            "sunday_service": "Sunday Service",
            "bible_study": "Bible Study",
            "special_meeting": "Special Meeting",
            "conference": "Conference",
            "gospel_music": "Gospel Music Night",
            "baptism": "Baptism",
            "other": "Other",
        },
    }
    return labels.get(language, labels["en"]).get(event.event_type, event.event_type)


@register.filter
def event_status_label(event, language):
    labels = {
        "zh": {
            "draft": "草稿",
            "published": "已发布",
            "completed": "已完成",
            "cancelled": "已取消",
        },
        "en": {
            "draft": "Draft",
            "published": "Published",
            "completed": "Completed",
            "cancelled": "Cancelled",
        },
    }
    return labels.get(language, labels["en"]).get(event.status, event.status)


@register.filter
def event_scope_label(event, language):
    labels = {
        "zh": {
            "global": "全教会",
            "district": "区",
            "small_group": "小组",
        },
        "en": {
            "global": "Global",
            "district": "District",
            "small_group": "Small Group",
        },
    }
    return labels.get(language, labels["en"]).get(event.scope_type, event.scope_type)
