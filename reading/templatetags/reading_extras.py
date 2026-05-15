from django import template

register = template.Library()


@register.filter
def active_plan_name(active_plan, language):
    if not active_plan:
        return ""

    if active_plan.title:
        return active_plan.title

    return active_plan.plan.get_name(language)


@register.filter
def reading_plan_name(plan, language):
    if not plan:
        return ""

    return plan.get_name(language)


@register.filter
def reading_plan_description(plan, language):
    if not plan:
        return ""

    return plan.get_description(language)


@register.filter
def passage_display(passage, language):
    if not passage:
        return ""

    if language == "en":
        return passage.get("display_en") or passage.get("display")

    return passage.get("display_zh") or passage.get("display")

@register.filter
def comment_author(comment, viewer):
    if not comment:
        return ""

    if comment.is_deleted:
        return ""

    if comment.is_anonymous:
        if viewer.is_staff:
            return f"Anonymous ({comment.user.username})"

        if comment.user_id == viewer.id:
            return "Anonymous (you)"

        return "Anonymous"

    return comment.user.username


@register.filter
def visibility_label(comment, language):
    if not comment:
        return ""

    if language == "zh":
        labels = {
            "private": "私人",
            "group": "小组",
            "church": "经文墙",
        }
    else:
        labels = {
            "private": "Private",
            "group": "My Group",
            "church": "Passage Wall",
        }

    return labels.get(comment.visibility, comment.visibility)