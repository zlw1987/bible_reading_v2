from django.contrib import admin
from .models import ReflectionComment


@admin.register(ReflectionComment)
class ReflectionCommentAdmin(admin.ModelAdmin):
    list_display = ("user", "plan_day", "parent", "is_deleted", "created_at")
    list_filter = ("is_deleted", "created_at", "plan_day__plan")
    search_fields = ("user__username", "body")
    readonly_fields = ("created_at",)