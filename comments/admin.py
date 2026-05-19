from django.contrib import admin
from .models import ReflectionComment, ReflectionReport


@admin.register(ReflectionComment)
class ReflectionCommentAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "active_plan",
        "plan_day",
        "scripture_ref_key",
        "visibility",
        "is_anonymous",
        "is_hidden",
        "is_deleted",
        "created_at",
    )
    list_filter = (
        "visibility",
        "is_anonymous",
        "is_hidden",
        "is_deleted",
        "created_at",
    )
    search_fields = (
        "user__username",
        "body",
        "scripture_ref_key",
        "scripture_display_zh",
        "scripture_display_en",
    )
    readonly_fields = ("created_at",)

@admin.register(ReflectionReport)
class ReflectionReportAdmin(admin.ModelAdmin):
    list_display = ("comment", "reporter", "status", "created_at", "reviewed_by", "reviewed_at")
    list_filter = ("status", "created_at")
    search_fields = ("comment__body", "reporter__username", "reason")
    readonly_fields = ("created_at", "reviewed_at")