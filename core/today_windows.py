"""Shared local-date window helper for the Today / This Week buckets.

Extracted from ``reading.views`` in MODULAR-CORE.3B so the events / studies /
ministry Today providers can share the same date windows without importing
``reading.views``. This is presentation-time bucketing only: no visibility,
audience, belonging, or serving semantics live here.
"""

from datetime import datetime, timedelta

from django.utils import timezone

THIS_WEEK_DAYS = 7


def _local_midnight(local_date):
    return timezone.make_aware(
        datetime.combine(local_date, datetime.min.time()),
        timezone.get_current_timezone(),
    )


def get_today_week_windows():
    """Return local-date datetime windows for Today and This Week."""
    today_date = timezone.localdate()
    today_start = _local_midnight(today_date)
    tomorrow_start = _local_midnight(today_date + timedelta(days=1))
    week_end = _local_midnight(today_date + timedelta(days=1 + THIS_WEEK_DAYS))
    return today_start, tomorrow_start, week_end
