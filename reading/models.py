from django.conf import settings
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
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

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
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="checkins")
    plan_day = models.ForeignKey(ReadingPlanDay, on_delete=models.CASCADE, related_name="checkins")
    checked_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "plan_day"],
                name="unique_user_plan_day_checkin",
            )
        ]

    def __str__(self):
        return f"{self.user} checked {self.plan_day}"