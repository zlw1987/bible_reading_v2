from django import template

from events.ministry_context_display import (
    derive_ministry_context_units,
    ministry_context_unit_label,
    multiple_contexts_label,
)

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


def _whole_church_label(language):
    return "全教会" if language == "zh" else "Whole Church"


def _compact_unit_label(unit, language):
    if unit.unit_type == "root":
        return _whole_church_label(language)
    chain = [
        ancestor
        for ancestor in unit.get_ancestors()
        if ancestor.unit_type != "root"
    ]
    chain.append(unit)
    return " > ".join(node.display_name(language) for node in chain)


def _audience_units(event):
    return [link.unit for link in event.audience_scope_links.all()]


@register.filter
def event_uses_structure_audience(event):
    return bool(event and _audience_units(event))


@register.filter
def event_effective_audience_labels(event, language):
    # SE-FIELD-RETIRE.1A: audience display is sourced solely from
    # ServiceEventAudienceScope rows. The legacy scope_type/district/small_group
    # fallback labels were removed with the fields; a zero-row event has no
    # audience labels and is fail-closed for ordinary users.
    if not event:
        return []

    units = _audience_units(event)
    if not units:
        return []
    if any(unit.unit_type == "root" for unit in units):
        return [_whole_church_label(language)]
    return [_compact_unit_label(unit, language) for unit in units]


@register.filter
def event_host_language_label(event, language):
    """Host/language ("ministry context") label with structure-native fallback.

    The structure-native ``host_language_unit`` display context is used when
    set. When it is blank, the label is derived from the event's
    ``ServiceEventAudienceScope`` rows via ``ChurchStructureUnit.parent``.
    This is display only; it never affects audience visibility.
    """
    if not event:
        return ""

    if event.host_language_unit_id:
        return ministry_context_unit_label(event.host_language_unit, language)

    derived = derive_ministry_context_units(_audience_units(event))
    if len(derived) == 1:
        return ministry_context_unit_label(derived[0], language)
    if len(derived) > 1:
        return multiple_contexts_label(language)
    return ""


@register.filter
def ministry_team_name(team, language):
    if not team:
        return ""
    return team.get_name(language)
