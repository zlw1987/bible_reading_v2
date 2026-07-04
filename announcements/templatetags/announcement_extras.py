from django import template


register = template.Library()


@register.filter
def announcement_title(announcement, language):
    if not announcement:
        return ""
    return announcement.get_title(language)


@register.filter
def announcement_body(announcement, language):
    if not announcement:
        return ""
    return announcement.get_body(language)
