from django.db import transaction
from django.utils import timezone

from .models import BibleStudyLesson, BibleStudyMeeting


def cancel_non_final_meetings_for_lesson(lesson):
    return lesson.meetings.filter(
        status__in=[
            BibleStudyMeeting.STATUS_DRAFT,
            BibleStudyMeeting.STATUS_PUBLISHED,
        ],
    ).update(
        status=BibleStudyMeeting.STATUS_CANCELLED,
        updated_at=timezone.now(),
    )


def cancel_bible_study_lesson_with_meetings(lesson):
    with transaction.atomic():
        lesson.status = BibleStudyLesson.STATUS_CANCELLED
        lesson.save()
        return cancel_non_final_meetings_for_lesson(lesson)
