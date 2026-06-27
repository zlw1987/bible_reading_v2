from .language import get_user_language, SUPPORTED_LANGUAGES
from .ui_text import UI_TEXT
from .unit_management import should_show_my_units_nav


READING_NAV_URLS = {
    "my_plans",
    "active_plan_calendar",
    "active_plan_intro",
    "active_plan_guides",
    "create_reading_guide_post",
    "edit_reading_guide_post",
    "delete_reading_guide_post",
    "active_plan_detail",
    "join_active_plan",
    "leave_active_plan",
    "memory_verse_reader",
    "check_in",
    "passage_reader",
    "audio_reader",
    "passage_wall",
    "add_comment",
    "add_reply",
    "edit_comment",
    "delete_comment",
    "report_comment",
}

BIBLE_STUDY_NAV_URLS = {
    "study_session_list",
    "bible_study_meeting_detail",
    "edit_bible_study_meeting_preparation",
}

PRAYER_NAV_URLS = {
    "prayer_list",
    "prayer_detail",
    "mark_prayed",
    "report_prayer_request",
    "add_prayer_comment",
    "update_prayer_status",
    "delete_prayer_request",
    "edit_prayer_request",
    "edit_prayer_comment",
    "delete_prayer_comment",
}

PROFILE_NAV_URLS = {
    "profile",
    "password_change",
    "password_change_done",
}

# Member-facing event discovery pages. These read-only pages are accessible to
# ordinary members (subject to per-event visibility), so they highlight the
# primary "events" nav rather than the staff menu. Event management pages
# (create/edit/cancel/recurring) stay under STAFF_NAV_URLS below.
EVENT_NAV_URLS = {
    "service_event_list",
    "service_event_detail",
}

STAFF_NAV_URLS = {
    "staff_reading_plan_list",
    "staff_reading_plan_header",
    "staff_reading_plan_days",
    "staff_moderation_queue",
    "staff_reflection_reports",
    "staff_reflection_action",
    "staff_prayer_reports",
    "staff_prayer_action",
    "staff_user_list",
    "staff_user_password_reset",
    "staff_membership_request_list",
    "staff_membership_request_detail",
    "staff_membership_request_approve",
    "staff_membership_request_reject",
    "create_service_event",
    "create_recurring_service_events",
    "edit_service_event",
    "cancel_service_event",
    "ministry_team_list",
    "create_ministry_team",
    "ministry_team_detail",
    "team_schedule",
    "edit_ministry_team",
    "manage_team_members",
    "edit_team_membership",
    "deactivate_team_membership",
    "team_assignment_list",
    "create_team_assignment",
    "team_assignment_detail",
    "edit_team_assignment",
    "cancel_team_assignment",
    "confirm_team_assignment",
    "lighting_pilot_import",
    "bible_study_schedule_manage_list",
    "create_bible_study_schedule",
    "bible_study_schedule_detail",
    "edit_bible_study_schedule",
    "bible_study_lesson_manage_list",
    "create_bible_study_lesson",
    "bible_study_lesson_detail",
    "edit_bible_study_lesson",
    "generate_bible_study_meetings",
    "cancel_bible_study_lesson",
    "bible_study_meeting_manage_list",
    "create_bible_study_meeting",
    "edit_bible_study_meeting",
    "cancel_bible_study_meeting",
    "manage_bible_study_meeting_roles",
    "edit_bible_study_meeting_role",
    "delete_bible_study_meeting_role",
    "manage_bible_study_meeting_worship_songs",
    "edit_bible_study_meeting_worship_song",
    "delete_bible_study_meeting_worship_song",
}


def get_active_nav(request):
    resolver_match = getattr(request, "resolver_match", None)
    url_name = getattr(resolver_match, "url_name", "")

    if url_name in EVENT_NAV_URLS:
        return "events"
    if url_name in STAFF_NAV_URLS:
        return "staff"
    if url_name == "home":
        return "today"
    if url_name in READING_NAV_URLS:
        return "reading"
    if url_name in BIBLE_STUDY_NAV_URLS:
        return "bible_study"
    if url_name in PRAYER_NAV_URLS:
        return "prayer"
    if url_name == "my_serving":
        return "my_serving"
    if url_name == "my_units":
        return "my_units"
    if url_name in PROFILE_NAV_URLS:
        return "profile"

    return ""


def language_context(request):
    language = get_user_language(request)

    other_language = "en" if language == "zh" else "zh"

    return {
        "language": language,
        "language_label": SUPPORTED_LANGUAGES[language],
        "other_language": other_language,
        "other_language_label": SUPPORTED_LANGUAGES[other_language],
        "supported_languages": SUPPORTED_LANGUAGES,
        "ui": UI_TEXT[language],
        "active_nav": get_active_nav(request),
        "show_my_units_nav": should_show_my_units_nav(request.user),
    }
