from django.contrib import admin

from .models import BibleStudyGuide, BibleStudySeries, BibleStudySession


@admin.register(BibleStudySeries)
class BibleStudySeriesAdmin(admin.ModelAdmin):
    list_display = ("title", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("title", "title_en", "description", "description_en")


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
