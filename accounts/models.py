from django.conf import settings
from django.db import models


class SmallGroup(models.Model):
    name = models.CharField(max_length=80, unique=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class Profile(models.Model):
    LANGUAGE_CHOICES = [
        ("zh", "中文"),
        ("en", "English"),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
    )
    small_group = models.ForeignKey(
        SmallGroup,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="members",
    )
    preferred_language = models.CharField(
        max_length=2,
        choices=LANGUAGE_CHOICES,
        default="zh",
    )
    must_change_password = models.BooleanField(default=False)
    def __str__(self):
        return self.user.get_username()