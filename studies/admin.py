from django.contrib import admin

from .models import (
    BibleStudyGuide,
    BibleStudyLesson,
    BibleStudyMeeting,
    BibleStudyMeetingRole,
    BibleStudyMeetingWorshipSong,
    BibleStudySeries,
    BibleStudySession,
    BibleStudyWorshipSong,
)


@admin.register(BibleStudySeries)
class BibleStudySeriesAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "title_en",
        "start_date",
        "end_date",
        "status",
        "scope_type",
        "ministry_context",
        "district",
        "small_group",
        "is_active",
    )
    list_filter = (
        "status",
        "scope_type",
        "ministry_context",
        "district",
        "is_active",
    )
    search_fields = ("title", "title_en")
    readonly_fields = ("created_at", "updated_at", "published_at")


@admin.register(BibleStudySession)
class BibleStudySessionAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "series",
        "study_datetime",
        "prestudy_datetime",
        "scope_type",
        "status",
        "created_by",
    )
    list_filter = ("status", "scope_type", "series", "study_datetime")
    search_fields = ("title", "title_en", "scripture_reference", "location")
    readonly_fields = ("created_at", "updated_at", "published_at")


@admin.register(BibleStudyLesson)
class BibleStudyLessonAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "series",
        "lesson_date",
        "prestudy_datetime",
        "status",
        "created_by",
    )
    list_filter = ("status", "series", "lesson_date")
    search_fields = (
        "title",
        "title_en",
        "scripture_reference",
        "pastor_guide_body",
        "global_discussion_questions",
    )
    readonly_fields = ("created_at", "updated_at", "published_at")
    ordering = ("-lesson_date", "-prestudy_datetime")


@admin.register(BibleStudyMeeting)
class BibleStudyMeetingAdmin(admin.ModelAdmin):
    list_display = (
        "lesson",
        "small_group",
        "meeting_datetime",
        "status",
        "discussion_leader_user",
        "created_by",
    )
    list_filter = ("status", "small_group", "meeting_datetime")
    search_fields = (
        "lesson__title",
        "lesson__title_en",
        "small_group__name",
        "location",
        "location_en",
        "discussion_leader_name",
        "group_direction",
        "group_questions",
    )
    readonly_fields = ("created_at", "updated_at")
    ordering = ("-meeting_datetime",)


@admin.register(BibleStudyMeetingWorshipSong)
class BibleStudyMeetingWorshipSongAdmin(admin.ModelAdmin):
    list_display = ("meeting", "sort_order", "title", "song_key", "updated_at")
    list_filter = ("meeting",)
    search_fields = (
        "title",
        "title_en",
        "song_key",
        "arrangement_notes",
        "support_notes",
        "meeting__lesson__title",
        "meeting__small_group__name",
    )
    readonly_fields = ("created_at", "updated_at")
    ordering = ("meeting", "sort_order", "id")


@admin.register(BibleStudyMeetingRole)
class BibleStudyMeetingRoleAdmin(admin.ModelAdmin):
    list_display = ("meeting", "role", "user", "display_name", "updated_at")
    list_filter = ("role", "meeting")
    search_fields = (
        "display_name",
        "notes",
        "notes_en",
        "user__username",
        "user__first_name",
        "user__last_name",
        "meeting__lesson__title",
        "meeting__small_group__name",
    )
    readonly_fields = ("created_at", "updated_at")
    ordering = ("meeting", "role", "id")


@admin.register(BibleStudyGuide)
class BibleStudyGuideAdmin(admin.ModelAdmin):
    list_display = ("session", "updated_at")
    search_fields = (
        "session__title",
        "guide_body",
        "discussion_questions",
        "prestudy_notes",
    )
    readonly_fields = ("created_at", "updated_at")


@admin.register(BibleStudyWorshipSong)
class BibleStudyWorshipSongAdmin(admin.ModelAdmin):
    list_display = ("session", "sort_order", "title", "song_key", "updated_at")
    list_filter = ("session",)
    search_fields = (
        "title",
        "title_en",
        "song_key",
        "note",
        "note_en",
        "session__title",
    )
    readonly_fields = ("created_at", "updated_at")
