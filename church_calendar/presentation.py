"""Presentation-only helpers for the Church Calendar month/day UI.

CHURCH-CALENDAR.1C. These helpers only *arrange* already-collected, member-safe
:class:`~church_calendar.providers.CalendarItem` values for display. They bucket
items into local-date month cells, split timed items from active-window
announcements, and sort deterministically.

They deliberately do NOT query a source, re-check member visibility, widen the
member-safe aggregator result, or mutate a ``CalendarItem``. All bucketing uses
aware local-date bounds (never UTC dates) with half-open ``[start, end)``
semantics, so an item ending exactly on a local-midnight boundary never leaks
onto the following day (mirroring the source providers' own overlap rule).
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

from django.utils import timezone

from . import ranges
from .providers import DISPLAY_ACTIVE_WINDOW, ITEM_TYPE_LABELS, ITEM_TYPE_ORDER

# Rows shown directly inside a month cell before the cell compacts the rest into
# an explicit "more" link. Every hidden item stays reachable on the day-detail
# page, so compacting never silently drops an item.
MONTH_CELL_ITEM_CAP = 3

# item_type -> stable index for deterministic secondary sorting of timed items.
_TYPE_ORDER_INDEX = {item_type: i for i, item_type in enumerate(ITEM_TYPE_ORDER)}


@dataclass(frozen=True)
class PresentedItem:
    """A display-ready view of one :class:`CalendarItem` (never stored)."""

    item_type: str
    source_id: Any
    title: str
    detail_url: str
    location: str
    label_en: str
    label_zh: str
    # Active-window communication (announcement) vs. a true timed appointment.
    is_announcement: bool
    # Timed item with no end (e.g. a Bible Study meeting or a start-only
    # activity): show a start time only, never a fabricated duration.
    is_point_in_time: bool
    # Ranged item whose local start/end fall on the same local day.
    same_local_day: bool
    start: datetime
    end: Optional[datetime]


def present_item(item):
    """Build a :class:`PresentedItem` from a member-safe ``CalendarItem``."""
    label_en, label_zh = ITEM_TYPE_LABELS[item.item_type]
    is_announcement = item.display_mode == DISPLAY_ACTIVE_WINDOW
    is_point_in_time = item.end is None and not is_announcement
    if item.end is not None:
        same_local_day = (
            timezone.localtime(item.start).date()
            == timezone.localtime(item.end).date()
        )
    else:
        same_local_day = True
    return PresentedItem(
        item_type=item.item_type,
        source_id=item.source_id,
        title=item.title,
        detail_url=item.detail_url,
        location=item.location,
        label_en=label_en,
        label_zh=label_zh,
        is_announcement=is_announcement,
        is_point_in_time=is_point_in_time,
        same_local_day=same_local_day,
        start=item.start,
        end=item.end,
    )


def _timed_sort_key(item):
    # Local start time, then a stable type order, then source id.
    return (item.start, _TYPE_ORDER_INDEX[item.item_type], str(item.source_id))


def _announcement_sort_key(item):
    # Publish-window start, then source id (deterministic).
    return (item.start, str(item.source_id))


def split_day_items(items):
    """Split into ``(timed, announcements)``, each deterministically sorted.

    ``items`` are raw ``CalendarItem`` values overlapping one local day.
    """
    timed = [i for i in items if i.display_mode != DISPLAY_ACTIVE_WINDOW]
    announcements = [i for i in items if i.display_mode == DISPLAY_ACTIVE_WINDOW]
    timed.sort(key=_timed_sort_key)
    announcements.sort(key=_announcement_sort_key)
    return timed, announcements


def _overlaps_day(item, day_start, day_end):
    """Half-open ``[day_start, day_end)`` overlap for one ``CalendarItem``.

    * A timed point-in-time item (``end is None``) belongs only to the local day
      its ``start`` falls on.
    * An open-ended announcement (``active_window`` + ``end is None``) is active
      on every day at or after its window start.
    * A ranged item ``[start, end)`` overlaps when ``start < day_end`` and
      ``end > day_start``; an item ending exactly at ``day_start`` (a
      local-midnight boundary) does not appear on that following day.
    """
    if item.start >= day_end:
        return False
    if item.end is None:
        if item.display_mode == DISPLAY_ACTIVE_WINDOW:
            return True
        return item.start >= day_start
    return item.end > day_start


def build_day_sections(items):
    """Presented ``timed`` / ``announcement`` sections for one local day."""
    timed, announcements = split_day_items(items)
    return {
        "timed": [present_item(i) for i in timed],
        "announcements": [present_item(i) for i in announcements],
    }


def build_month_weeks(grid_weeks, items, *, month, today, cap=MONTH_CELL_ITEM_CAP):
    """Build display cells for a month grid, bucketing ``items`` by local day.

    ``grid_weeks`` is the list of week rows of local ``date`` objects from
    :func:`church_calendar.ranges.month_grid`. Each cell carries the compacted
    ``items`` (timed first, then announcements), the hidden ``more_count`` beyond
    ``cap``, and the full ``total_count`` so no item is silently dropped. Only
    in-month cells are bucketed; out-of-month cells remain navigable placeholders.
    """
    weeks = []
    for week in grid_weeks:
        row = []
        for cell_date in week:
            in_month = cell_date.month == month
            day_items = []
            if in_month:
                day_start, day_end = ranges.day_bounds(cell_date)
                overlapping = [
                    item
                    for item in items
                    if _overlaps_day(item, day_start, day_end)
                ]
                timed, announcements = split_day_items(overlapping)
                day_items = [present_item(i) for i in timed + announcements]
            shown = day_items[:cap]
            row.append(
                {
                    "date": cell_date,
                    "in_month": in_month,
                    "is_today": cell_date == today,
                    "items": shown,
                    "more_count": len(day_items) - len(shown),
                    "total_count": len(day_items),
                }
            )
        weeks.append(row)
    return weeks
