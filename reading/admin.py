from django.contrib import admin
from .models import (
    BibleBook,
    BibleChapter,
    ReadingPlan,
    ReadingPlanDay,
    ActivePlan,
    PlanEnrollment,
    CheckIn,
)


class ReadingPlanDayInline(admin.TabularInline):
    model = ReadingPlanDay
    extra = 1


@admin.register(BibleBook)
class BibleBookAdmin(admin.ModelAdmin):
    list_display = ("order", "name_zh", "name_en", "testament")
    list_filter = ("testament",)
    search_fields = ("name_zh", "name_en")
    ordering = ("order",)


@admin.register(BibleChapter)
class BibleChapterAdmin(admin.ModelAdmin):
    list_display = ("book", "chapter_number")
    list_filter = ("book__testament", "book")
    search_fields = ("book__name_zh", "book__name_en")


@admin.register(ReadingPlan)
class ReadingPlanAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "description")
    inlines = [ReadingPlanDayInline]


@admin.register(ReadingPlanDay)
class ReadingPlanDayAdmin(admin.ModelAdmin):
    list_display = ("plan", "day_number", "memory_verse")
    list_filter = ("plan",)
    search_fields = ("reading_text", "memory_verse")
    ordering = ("plan", "day_number")


@admin.register(ActivePlan)
class ActivePlanAdmin(admin.ModelAdmin):
    list_display = ("__str__", "plan", "start_date")
    list_filter = ("plan", "start_date")
    search_fields = ("title", "plan__name")


@admin.register(PlanEnrollment)
class PlanEnrollmentAdmin(admin.ModelAdmin):
    list_display = ("user", "active_plan", "joined_at")
    list_filter = ("active_plan",)
    search_fields = ("user__username", "active_plan__plan__name")


@admin.register(CheckIn)
class CheckInAdmin(admin.ModelAdmin):
    list_display = ("user", "plan_day", "checked_at")
    list_filter = ("plan_day__plan", "checked_at")
    search_fields = ("user__username", "plan_day__reading_text")