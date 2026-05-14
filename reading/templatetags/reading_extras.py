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