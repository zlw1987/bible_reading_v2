from django.contrib import admin

from .models import PrayerComment, PrayerMark, PrayerReport, PrayerRequest


@admin.register(PrayerRequest)
class PrayerRequestAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "user",
        "visibility",
        "status",
        "is_anonymous",
        "is_hidden",
        "is_deleted",
        "created_at",
    )
    list_filter = (
        "visibility",
        "status",
        "is_anonymous",
        "is_hidden",
        "is_deleted",
        "created_at",
    )
    search_fields = (
        "title",
        "body",
        "user__username",
        "small_group_at_post__name",
        "hidden_reason",
    )
    readonly_fields = ("created_at", "updated_at", "hidden_at")


@admin.register(PrayerMark)
class PrayerMarkAdmin(admin.ModelAdmin):
    list_display = ("prayer_request", "user", "created_at")
    search_fields = ("prayer_request__title", "user__username")
    readonly_fields = ("created_at",)


@admin.register(PrayerComment)
class PrayerCommentAdmin(admin.ModelAdmin):
    list_display = ("prayer_request", "user", "is_anonymous", "is_deleted", "created_at")
    list_filter = ("is_anonymous", "is_deleted", "created_at")
    search_fields = ("prayer_request__title", "body", "user__username")
    readonly_fields = ("created_at",)


@admin.register(PrayerReport)
class PrayerReportAdmin(admin.ModelAdmin):
    list_display = ("prayer_request", "reporter", "status", "created_at", "reviewed_by")
    list_filter = ("status", "created_at")
    search_fields = (
        "prayer_request__title",
        "prayer_request__body",
        "reporter__username",
        "reason",
    )
    readonly_fields = ("created_at", "reviewed_at")
