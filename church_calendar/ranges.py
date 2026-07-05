"""Local-date range and month-grid helpers for the Church Calendar.

All range bounds are aware, half-open ``[start, end)`` datetimes in the
configured local timezone, and all grouping uses local dates (never UTC
dates), per the calendar plan's date semantics.
"""

import calendar as _calendar
from datetime import date, datetime, timedelta

from django.utils import timezone


def parse_month_param(raw, *, default):
    """Parse a ``YYYY-MM`` string into ``(year, month)``.

    Missing, blank, or malformed input returns ``default`` (a ``(year, month)``
    tuple), so an invalid ``?month=`` never raises — the month view fails safe
    to the current month instead of erroring.
    """
    if not raw:
        return default

    parts = raw.split("-")
    if len(parts) != 2:
        return default

    year_text, month_text = parts
    if len(year_text) != 4:
        return default

    try:
        year = int(year_text)
        month = int(month_text)
    except (TypeError, ValueError):
        return default

    if not (1 <= month <= 12):
        return default
    if not (1 <= year <= 9999):
        return default

    return (year, month)


def shift_month(year, month, offset):
    """Return the ``(year, month)`` ``offset`` months from the given month."""
    index = month - 1 + offset
    return year + index // 12, index % 12 + 1


def _local_midnight(a_date):
    """Aware local-midnight datetime at the start of ``a_date``."""
    naive = datetime(a_date.year, a_date.month, a_date.day)
    return timezone.make_aware(naive, timezone.get_current_timezone())


def month_bounds(year, month):
    """Aware half-open ``[start, end)`` covering the whole local month."""
    start = _local_midnight(date(year, month, 1))
    next_year, next_month = shift_month(year, month, 1)
    end = _local_midnight(date(next_year, next_month, 1))
    return start, end


def day_bounds(a_date):
    """Aware half-open ``[start, end)`` covering one local day."""
    start = _local_midnight(a_date)
    end = _local_midnight(a_date + timedelta(days=1))
    return start, end


def month_grid(year, month):
    """Weeks (Sunday-first) of local ``date`` objects covering the month grid."""
    builder = _calendar.Calendar(firstweekday=6)
    return builder.monthdatescalendar(year, month)
