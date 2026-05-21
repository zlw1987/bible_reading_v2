from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class BibleBook(models.Model):
    testament = models.CharField(
        max_length=2,
        choices=[("OT", "Old Testament"), ("NT", "New Testament")],
    )
    order = models.PositiveSmallIntegerField(unique=True)
    name_zh = models.CharField(max_length=80)
    name_en = models.CharField(max_length=80, blank=True)

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return self.name_zh


class BibleChapter(models.Model):
    book = models.ForeignKey(BibleBook, on_delete=models.CASCADE, related_name="chapters")
    chapter_number = models.PositiveSmallIntegerField()

    class Meta:
        unique_together = [("book", "chapter_number")]
        ordering = ["book__order", "chapter_number"]

    def __str__(self):
        return f"{self.book.name_zh} {self.chapter_number}"


class ReadingPlan(models.Model):
    name = models.CharField(max_length=120, unique=True)
    name_en = models.CharField(max_length=120, blank=True)
    description = models.TextField(blank=True)
    description_en = models.TextField(blank=True)
    introduction = models.TextField(blank=True, default="")
    introduction_en = models.TextField(blank=True, default="")
    reading_guidance = models.TextField(blank=True, default="")
    reading_guidance_en = models.TextField(blank=True, default="")
    pastoral_note = models.TextField(blank=True, default="")
    pastoral_note_en = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True)

    def get_name(self, language="zh"):
        if language == "en" and self.name_en:
            return self.name_en
        return self.name

    def get_description(self, language="zh"):
        if language == "en" and self.description_en:
            return self.description_en
        return self.description

    def get_introduction(self, language="zh"):
        if language == "en":
            return self.introduction_en or self.introduction or self.description_en or self.description

        return self.introduction or self.description

    def get_reading_guidance(self, language="zh"):
        if language == "en":
            return self.reading_guidance_en or self.reading_guidance

        return self.reading_guidance

    def get_pastoral_note(self, language="zh"):
        if language == "en":
            return self.pastoral_note_en or self.pastoral_note

        return self.pastoral_note

    def __str__(self):
        return self.name


class ReadingPlanDay(models.Model):
    plan = models.ForeignKey(ReadingPlan, on_delete=models.CASCADE, related_name="days")
    day_number = models.PositiveIntegerField()
    reading_text = models.TextField()
    memory_verse = models.CharField(max_length=120, blank=True)

    class Meta:
        unique_together = [("plan", "day_number")]
        ordering = ["plan", "day_number"]

    def __str__(self):
        return f"{self.plan.name} - Day {self.day_number}"

class ReadingPlanDayPassage(models.Model):
    TYPE_READING = "reading"
    TYPE_MEMORY = "memory"

    PASSAGE_TYPE_CHOICES = [
        (TYPE_READING, "Reading"),
        (TYPE_MEMORY, "Memory Verse"),
    ]

    plan_day = models.ForeignKey(
        ReadingPlanDay,
        on_delete=models.CASCADE,
        related_name="structured_passages",
    )
    passage_type = models.CharField(
        max_length=20,
        choices=PASSAGE_TYPE_CHOICES,
        db_index=True,
    )
    sort_order = models.PositiveIntegerField()

    raw_reference = models.CharField(max_length=160)
    scripture_ref_key = models.CharField(max_length=120, db_index=True)

    display_zh = models.CharField(max_length=160, blank=True, default="")
    display_en = models.CharField(max_length=160, blank=True, default="")

    text_url_zh = models.URLField(max_length=500, blank=True, default="")
    text_url_en = models.URLField(max_length=500, blank=True, default="")
    audio_url = models.URLField(max_length=500, blank=True, default="")

    class Meta:
        ordering = ["plan_day", "passage_type", "sort_order"]
        constraints = [
            models.UniqueConstraint(
                fields=["plan_day", "passage_type", "sort_order"],
                name="unique_plan_day_passage_order",
            )
        ]
        indexes = [
            models.Index(fields=["plan_day", "passage_type"]),
            models.Index(fields=["scripture_ref_key"]),
        ]

    def __str__(self):
        return f"{self.plan_day} - {self.passage_type} {self.sort_order}: {self.scripture_ref_key}"

    def as_passage_dict(self):
        return {
            "search_text": self.scripture_ref_key,
            "display": self.display_en or self.display_zh or self.raw_reference,
            "display_zh": self.display_zh or self.raw_reference,
            "display_en": self.display_en or self.raw_reference,
            "text_url_zh": self.text_url_zh,
            "text_url_en": self.text_url_en,
            "audio_url": self.audio_url,
        }

class ActivePlan(models.Model):
    plan = models.ForeignKey(ReadingPlan, on_delete=models.PROTECT, related_name="active_runs")
    start_date = models.DateField()
    title = models.CharField(max_length=150, blank=True)

    class Meta:
        ordering = ["-start_date"]

    def __str__(self):
        return self.title or f"{self.plan.name} from {self.start_date}"

    def current_day_number(self):
        delta = timezone.localdate() - self.start_date
        return delta.days + 1


class ReadingGuidePost(models.Model):
    GUIDE_GENERAL = "general"
    GUIDE_WEEKLY = "weekly"
    GUIDE_DAILY = "daily"

    GUIDE_TYPE_CHOICES = [
        (GUIDE_GENERAL, "General"),
        (GUIDE_WEEKLY, "Weekly"),
        (GUIDE_DAILY, "Daily"),
    ]

    active_plan = models.ForeignKey(
        ActivePlan,
        on_delete=models.CASCADE,
        related_name="guide_posts",
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reading_guide_posts",
    )
    title = models.CharField(max_length=160)
    title_en = models.CharField(max_length=160, blank=True, default="")
    body = models.TextField()
    body_en = models.TextField(blank=True, default="")
    guide_type = models.CharField(
        max_length=20,
        choices=GUIDE_TYPE_CHOICES,
        default=GUIDE_GENERAL,
    )
    week_number = models.PositiveIntegerField(null=True, blank=True)
    day_number = models.PositiveIntegerField(null=True, blank=True)
    is_pinned = models.BooleanField(default=False)
    is_published = models.BooleanField(default=True)
    published_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-is_pinned", "-published_at", "-created_at"]

    def __str__(self):
        return self.title

    def clean(self):
        errors = {}

        if self.guide_type == self.GUIDE_GENERAL:
            if self.week_number:
                errors["week_number"] = "General guide posts cannot have a week number."
            if self.day_number:
                errors["day_number"] = "General guide posts cannot have a day number."
        elif self.guide_type == self.GUIDE_WEEKLY:
            if not self.week_number:
                errors["week_number"] = "Weekly guide posts require a week number."
            if self.day_number:
                errors["day_number"] = "Weekly guide posts cannot have a day number."
        elif self.guide_type == self.GUIDE_DAILY:
            if not self.day_number:
                errors["day_number"] = "Daily guide posts require a day number."
            if self.week_number:
                errors["week_number"] = "Daily guide posts cannot have a week number."

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def get_title(self, language="zh"):
        if language == "en" and self.title_en:
            return self.title_en
        return self.title

    def get_body(self, language="zh"):
        if language == "en" and self.body_en:
            return self.body_en
        return self.body


class PlanEnrollment(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="plan_enrollments")
    active_plan = models.ForeignKey(ActivePlan, on_delete=models.CASCADE, related_name="enrollments")
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "active_plan"],
                name="unique_user_active_plan_enrollment",
            )
        ]

    def __str__(self):
        return f"{self.user} -> {self.active_plan}"


class CheckIn(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="checkins",
    )
    active_plan = models.ForeignKey(
        ActivePlan,
        on_delete=models.CASCADE,
        related_name="checkins",
    )
    plan_day = models.ForeignKey(
        ReadingPlanDay,
        on_delete=models.CASCADE,
        related_name="checkins",
    )
    checked_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "active_plan", "plan_day"],
                name="unique_user_active_plan_day_checkin",
            )
        ]

    def __str__(self):
        return f"{self.user} checked {self.active_plan} - {self.plan_day}"
