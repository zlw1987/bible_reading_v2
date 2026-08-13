from django.contrib import admin

from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = (
        "recipient",
        "notification_type",
        "source_module",
        "severity",
        "created_at",
        "read_at",
    )
    list_filter = ("source_module", "notification_type", "severity", "read_at")
    search_fields = (
        "recipient__username",
        "recipient__first_name",
        "recipient__last_name",
        "title",
        "notification_type",
        "dedupe_key",
    )
    date_hierarchy = "created_at"
    ordering = ("-created_at",)
