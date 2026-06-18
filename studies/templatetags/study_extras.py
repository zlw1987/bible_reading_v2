from django import template

register = template.Library()


@register.filter
def study_series_title(series, language):
    if not series:
        return ""
    return series.get_title(language)


@register.filter
def study_series_description(series, language):
    if not series:
        return ""
    return series.get_description(language)


@register.filter
def study_series_status_label(series, language):
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
    return labels.get(language, labels["en"]).get(series.status, series.status)


def _whole_church_label(language):
    return "全教会" if language == "zh" else "Whole Church"


def compact_unit_label(unit, language):
    """Readable unit label with the Whole Church root prefix removed.

    Example: ``Chinese Ministry > North`` instead of
    ``Whole Church > Chinese Ministry > North``.
    """
    if unit.unit_type == "root":
        return _whole_church_label(language)
    chain = [
        ancestor
        for ancestor in unit.get_ancestors()
        if ancestor.unit_type != "root"
    ]
    chain.append(unit)
    return " > ".join(node.display_name(language) for node in chain)


def _legacy_scope_label(series, language):
    def ministry_context_label():
        if not series.ministry_context_id:
            return "-"
        context = series.ministry_context
        name = context.name_en or context.name
        return f"{context.code} / {name}"

    if language == "zh":
        if series.scope_type == "global":
            return "全教会"
        if series.scope_type == "ministry_context":
            return f"事工范围：{ministry_context_label()}"
        if series.scope_type == "district":
            name = series.district.name if series.district_id else "-"
            return f"区：{name}"
        if series.scope_type == "small_group":
            name = series.small_group.name if series.small_group_id else "-"
            return f"小组：{name}"
        return series.scope_type

    if series.scope_type == "global":
        return "Whole Church"
    if series.scope_type == "ministry_context":
        return f"Ministry Context: {ministry_context_label()}"
    if series.scope_type == "district":
        name = series.district.name if series.district_id else "-"
        return f"District: {name}"
    if series.scope_type == "small_group":
        name = series.small_group.name if series.small_group_id else "-"
        return f"Small Group: {name}"
    return series.scope_type


def _scope_unit_labels(series, language):
    """Compact, root-stripped labels for a schedule's audience scope.

    Prefers BS-AS.1 ChurchStructureUnit audience rows (via the prefetched
    ``audience_scope_links``) and falls back to the legacy single scope when no
    audience rows exist.
    """
    audience_units = [link.unit for link in series.audience_scope_links.all()]
    if audience_units:
        if any(unit.unit_type == "root" for unit in audience_units):
            return [_whole_church_label(language)]
        return [compact_unit_label(unit, language) for unit in audience_units]
    return [_legacy_scope_label(series, language)]


@register.filter
def study_series_scope_unit_labels(series, language):
    """List of compact audience-scope labels, for chip/wrapped detail display."""
    if not series:
        return []
    return _scope_unit_labels(series, language)


@register.filter
def study_series_scope_compact(series, language):
    """Compact audience-scope label for list/card surfaces.

    Shows at most three labels and appends ``+ N more`` / ``另 N 个``.
    """
    if not series:
        return ""
    labels = _scope_unit_labels(series, language)
    limit = 3
    if len(labels) <= limit:
        return ", ".join(labels)
    shown = ", ".join(labels[:limit])
    remaining = len(labels) - limit
    more = f"另 {remaining} 个" if language == "zh" else f"+ {remaining} more"
    return f"{shown}, {more}"


@register.filter
def study_series_scope_label(series, language):
    """Full audience-scope label (all units, root prefix removed)."""
    if not series:
        return ""
    return ", ".join(_scope_unit_labels(series, language))


@register.filter
def study_session_title(session, language):
    if not session:
        return ""
    return session.get_title(language)


@register.filter
def study_lesson_title(lesson, language):
    if not lesson:
        return ""
    return lesson.get_title(language)


@register.filter
def study_unit_path(unit, language):
    """Render a ChurchStructureUnit's ancestor path label in the given language.

    Used by the Bible Study meeting manage-list audience-unit filter
    (BS-STRUCT.1N) so the option labels show the structure path.
    """
    if not unit:
        return ""
    return unit.path_label(language)


@register.filter
def study_meeting_structure_label(meeting, language):
    if not meeting:
        return ""
    return meeting.get_structure_display_label(language)


@register.filter
def study_lesson_pastor_guide(lesson, language):
    if not lesson:
        return ""
    return lesson.get_pastor_guide_body(language)


@register.filter
def study_lesson_global_questions(lesson, language):
    if not lesson:
        return ""
    return lesson.get_global_discussion_questions(language)


@register.filter
def study_lesson_prestudy_notes(lesson, language):
    if not lesson:
        return ""
    return lesson.get_prestudy_notes(language)


@register.filter
def study_meeting_location(meeting, language):
    if not meeting:
        return ""
    return meeting.get_location(language)


@register.filter
def study_meeting_group_direction(meeting, language):
    if not meeting:
        return ""
    return meeting.get_group_direction(language)


@register.filter
def study_meeting_group_questions(meeting, language):
    if not meeting:
        return ""
    return meeting.get_group_questions(language)


@register.filter
def meeting_role_label(role, language):
    labels = {
        "zh": {
            "discussion_leader": "查经带领",
            "worship_lead": "敬拜带领",
            "pianist": "伴奏",
            "support": "配搭",
            "host": "接待",
        },
        "en": {
            "discussion_leader": "Discussion Leader",
            "worship_lead": "Worship Lead",
            "pianist": "Pianist",
            "support": "Support",
            "host": "Host",
        },
    }
    return labels.get(language, labels["en"]).get(role.role, role.get_role_display())


@register.filter
def meeting_role_display_name(role, language):
    if not role:
        return ""
    return role.get_display_name()


@register.filter
def meeting_role_notes(role, language):
    if not role:
        return ""
    return role.get_notes(language)


@register.filter
def study_guide_body(guide, language):
    if not guide:
        return ""
    return guide.get_guide_body(language)


@register.filter
def discussion_questions(guide, language):
    if not guide:
        return ""
    return guide.get_discussion_questions(language)


@register.filter
def prestudy_notes(guide, language):
    if not guide:
        return ""
    return guide.get_prestudy_notes(language)


@register.filter
def worship_song_title(song, language):
    if not song:
        return ""
    return song.get_title(language)


@register.filter
def worship_song_note(song, language):
    if not song:
        return ""
    return song.get_note(language)


@register.filter
def meeting_worship_song_arrangement_notes(song, language):
    if not song:
        return ""
    return song.get_arrangement_notes(language)


@register.filter
def meeting_worship_song_support_notes(song, language):
    if not song:
        return ""
    return song.get_support_notes(language)


@register.filter
def meeting_worship_song_lead(song, language):
    if not song:
        return ""
    if song.worship_lead_user:
        return song.worship_lead_user.get_username()
    return song.worship_lead_name


@register.filter
def study_status_label(session, language):
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
    return labels.get(language, labels["en"]).get(session.status, session.status)


@register.filter
def study_scope_label(session, language):
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
    return labels.get(language, labels["en"]).get(
        session.scope_type,
        session.scope_type,
    )
