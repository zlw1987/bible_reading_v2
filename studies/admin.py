from django.contrib import admin

from .models import (
    BibleStudyLesson,
    BibleStudyMeeting,
    BibleStudyMeetingRole,
    BibleStudyMeetingWorshipSong,
    BibleStudySeries,
)

# BS-V1-ADMIN-RETIRE.1A retired the active Django Admin surface for the legacy
# V1 Bible Study path. ``BibleStudySession`` and its V1-only child models
# ``BibleStudyGuide`` / ``BibleStudyWorshipSong`` are intentionally NOT
# registered: V1 app-level runtime is already retired (BS-V1-RETIRE.1A) and
# there is no longer a staff create/edit/delete/maintenance surface for V1
# sessions. The models, tables, and rows are unchanged; remaining V1 rows are
# purged only through the guarded ``purge_legacy_bible_study_v1_sessions``
# command, and V1 model/table/schema removal stays a later separate slice.
# Do not re-register these admins. The active V2 path uses ``BibleStudyMeeting``.


@admin.register(BibleStudySeries)
class BibleStudySeriesAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "title_en",
        "start_date",
        "end_date",
        "status",
        "is_active",
    )
    list_filter = (
        "status",
        "is_active",
    )
    search_fields = ("title", "title_en")
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
        "structure_label",
        "meeting_datetime",
        "status",
        "discussion_leader_user",
        "created_by",
    )
    list_filter = ("status", "anchor_unit", "meeting_datetime")
    search_fields = (
        "lesson__title",
        "lesson__title_en",
        "location",
        "location_en",
        "discussion_leader_name",
        "group_direction",
        "group_questions",
    )
    readonly_fields = ("created_at", "updated_at")
    ordering = ("-meeting_datetime",)

    @admin.display(description="Audience Unit")
    def structure_label(self, obj):
        return obj.get_structure_display_label("en")

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related("anchor_unit")
            .prefetch_related("audience_scope_links__unit")
        )


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
    )
    readonly_fields = ("created_at", "updated_at")
    ordering = ("meeting", "sort_order", "id")

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related(
                "meeting",
                "meeting__anchor_unit",
            )
            .prefetch_related("meeting__audience_scope_links__unit")
        )


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
    )
    readonly_fields = ("created_at", "updated_at")
    ordering = ("meeting", "role", "id")

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related(
                "meeting",
                "meeting__anchor_unit",
                "user",
            )
            .prefetch_related("meeting__audience_scope_links__unit")
        )


# NOTE: BibleStudyGuideAdmin and BibleStudyWorshipSongAdmin (the V1-only child
# models keyed on BibleStudySession) were unregistered in BS-V1-ADMIN-RETIRE.1A
# together with BibleStudySessionAdmin. See the module header. The active V2
# worship surface is BibleStudyMeetingWorshipSongAdmin above.
