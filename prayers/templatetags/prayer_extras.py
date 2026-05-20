from django import template

register = template.Library()


@register.filter
def prayer_author(prayer, viewer):
    if not prayer:
        return ""

    if prayer.is_anonymous:
        if viewer.is_staff:
            return f"Anonymous ({prayer.user.username})"

        if prayer.user_id == viewer.id:
            return "Anonymous (you)"

        return "Anonymous"

    return prayer.user.username


@register.filter
def prayer_comment_author(comment, viewer):
    if not comment:
        return ""

    if comment.is_anonymous:
        if viewer.is_staff:
            return f"Anonymous ({comment.user.username})"

        if comment.user_id == viewer.id:
            return "Anonymous (you)"

        return "Anonymous"

    return comment.user.username


@register.filter
def prayer_visibility_label(prayer, language):
    if not prayer:
        return ""

    if language == "zh":
        labels = {
            "private": "私人",
            "group": "小组",
            "church": "代祷墙",
        }
    else:
        labels = {
            "private": "Private",
            "group": "My Group",
            "church": "Prayer Wall",
        }

    return labels.get(prayer.visibility, prayer.visibility)


@register.filter
def prayer_status_label(prayer, language):
    if not prayer:
        return ""

    if language == "zh":
        labels = {
            "open": "代祷中",
            "answered": "已回应",
            "closed": "已关闭",
        }
    else:
        labels = {
            "open": "Open",
            "answered": "Answered",
            "closed": "Closed",
        }

    return labels.get(prayer.status, prayer.status)