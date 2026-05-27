from django import template

register = template.Library()


@register.filter
def study_series_title(series, language):
    if not series:
        return ""
    return series.get_title(language)


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
