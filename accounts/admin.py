from django.contrib import admin
from .models import SmallGroup, Profile


@admin.register(SmallGroup)
class SmallGroupAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name",)


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "small_group", "preferred_language", "must_change_password")
    list_filter = ("small_group", "preferred_language", "must_change_password")
    search_fields = ("user__username", "user__email", "small_group__name")