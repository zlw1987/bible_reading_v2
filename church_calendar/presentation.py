"""Presentation-only helpers for the Church Calendar month/day UI.

CHURCH-CALENDAR.1C. These helpers only *arrange* already-collected, member-safe
:class:`~church_calendar.providers.CalendarItem` values for display. They bucket
items into local-date month cells, split timed items from active-window
announcements, and sort deterministically.

CHURCH-CALENDAR.2A-FU4 adds presentation-only occurrence grouping: timed items
that share an ``occurrence_key`` (a base ServiceEvent row plus the viewer's own
``my_serving`` rows for the same ServiceEvent) collapse into one grouped
occurrence, so the same real occurrence is one row/card and month cell
compaction counts grouped occurrences, not raw duplicate items. Grouping keys on
the underlying object identity, never on title/time/location strings, and is
presentation-only — it never re-checks or widens member-safe visibility.

They deliberately do NOT query a source, re-check member visibility, widen the
member-safe aggregator result, or mutate a ``CalendarItem``. All bucketing uses
aware local-date bounds (never UTC dates) with half-open ``[start, end)``
semantics, so an item ending exactly on a local-midnight boundary never leaks
onto the following day (mirroring the source providers' own overlap rule).
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional, Tuple

from django.utils import timezone

from . import ranges
from .providers import (
    DISPLAY_ACTIVE_WINDOW,
    DISPLAY_TIMED,
    ITEM_TYPE_LABELS,
    ITEM_TYPE_ORDER,
)

# Rows shown directly inside a month cell before the cell compacts the rest into
# an explicit "more" link. Every hidden item stays reachable on the day-detail
# page, so compacting never silently drops an item.
MONTH_CELL_ITEM_CAP = 3

# item_type -> stable index for deterministic secondary sorting of timed items.
_TYPE_ORDER_INDEX = {item_type: i for i, item_type in enumerate(ITEM_TYPE_ORDER)}


@dataclass(frozen=True)
class ServingSubitem:
    """One serving assignment attached to a grouped occurrence (never stored).

    CHURCH-CALENDAR.2A-FU4. ``role`` is the localized serving team/role label;
    ``detail_url`` is the viewer's own read-only My Serving assignment anchor,
    never an event edit/manage/confirm/attendance/check-in URL.
    """

    source_id: Any
    role: str
    detail_url: str


@dataclass(frozen=True)
class PresentedItem:
    """A display-ready view of one grouped occurrence (never stored).

    CHURCH-CALENDAR.2A-FU4: several real :class:`CalendarItem` values that share
    an ``occurrence_key`` (a base ServiceEvent row plus the viewer's own
    ``my_serving`` rows for the same ServiceEvent) collapse into one
    ``PresentedItem``. ``title`` / ``detail_url`` describe the base occurrence
    (member-facing event detail); ``serving`` lists the viewer's own serving
    subitems and ``serving_count`` their number. A plain, ungrouped item is just
    a ``PresentedItem`` with an empty ``serving`` list.
    """

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
    # The viewer's own serving assignments grouped onto this occurrence.
    serving: Tuple[ServingSubitem, ...] = ()
    serving_count: int = 0


def present_item(item):
    """Build a standalone :class:`PresentedItem` from one ``CalendarItem``."""
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


def _occurrence_key(item):
    """Grouping key for ``item``: its ``occurrence_key`` or a per-item fallback.

    An item without an ``occurrence_key`` never groups with anything else, so it
    falls back to its own identity (never a title/time string).
    """
    if item.occurrence_key:
        return item.occurrence_key
    return f"@identity:{item.item_type}:{item.source_id}"


def _occurrence_base_type(item):
    """Base ``item_type`` implied by a subitem's structured ``occurrence_key``.

    Used to label a serving-only occurrence (no base row present) as its real
    underlying type (e.g. ``service_event``) rather than ``my_serving``. Falls
    back to the item's own type for keys without a known prefix.
    """
    prefix = (item.occurrence_key or "").split(":", 1)[0]
    if prefix in ITEM_TYPE_LABELS:
        return prefix
    return item.item_type


def _present_occurrence(group_items):
    """Collapse one occurrence's items into a single :class:`PresentedItem`.

    ``group_items`` all share an ``occurrence_key``. An item with an empty
    ``occurrence_role`` is the base occurrence row; items with a role are serving
    subitems. When the base row is present it supplies the header; otherwise the
    header is reconstructed from a subitem's ``occurrence_title`` /
    ``occurrence_detail_url`` so an assigned server outside the ordinary audience
    still sees the occurrence (serving is explicit; the base provider stays
    audience-only).
    """
    base_items = [i for i in group_items if not i.occurrence_role]
    sub_items = [i for i in group_items if i.occurrence_role]

    if base_items:
        base = base_items[0]
        item_type = base.item_type
        title = base.title
        detail_url = base.detail_url
        location = base.location
        start = base.start
        end = base.end
    else:
        rep = sub_items[0]
        item_type = _occurrence_base_type(rep)
        title = rep.occurrence_title or rep.title
        detail_url = rep.occurrence_detail_url or rep.detail_url
        location = rep.location
        start = rep.start
        end = rep.end

    label_en, label_zh = ITEM_TYPE_LABELS[item_type]
    if end is not None:
        same_local_day = (
            timezone.localtime(start).date() == timezone.localtime(end).date()
        )
    else:
        same_local_day = True
    serving = tuple(
        ServingSubitem(
            source_id=i.source_id,
            role=i.occurrence_role,
            detail_url=i.detail_url,
        )
        for i in sub_items
    )
    return PresentedItem(
        item_type=item_type,
        source_id=base_items[0].source_id if base_items else sub_items[0].source_id,
        title=title,
        detail_url=detail_url,
        location=location,
        label_en=label_en,
        label_zh=label_zh,
        # Grouped occurrences are always true timed appointments, never
        # active-window announcements (announcements never carry an
        # occurrence_key, so they never enter this path).
        is_announcement=False,
        is_point_in_time=end is None,
        same_local_day=same_local_day,
        start=start,
        end=end,
        serving=serving,
        serving_count=len(serving),
    )


def present_timed_occurrences(sorted_timed_items):
    """Group already-sorted timed ``CalendarItem`` values into occurrences.

    Items sharing an ``occurrence_key`` collapse into one grouped
    :class:`PresentedItem`; grouping never depends on title/time strings. The
    first occurrence of each key follows the incoming sort order, so the grouped
    result stays deterministically ordered.
    """
    groups = {}
    order = []
    for item in sorted_timed_items:
        key = _occurrence_key(item)
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(item)
    return [_present_occurrence(groups[key]) for key in order]


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
    """Presented ``timed`` / ``announcement`` sections for one local day.

    Timed items are grouped into occurrences (a base ServiceEvent plus the
    viewer's own serving rows for it render as one card); announcements are never
    grouped.
    """
    timed, announcements = split_day_items(items)
    return {
        "timed": present_timed_occurrences(timed),
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
                # Group timed items into occurrences first, so the same real
                # ServiceEvent (base + the viewer's serving rows) is one cell row
                # and the cap / "more" count reflect grouped occurrences, not raw
                # duplicate items.
                day_items = present_timed_occurrences(timed) + [
                    present_item(i) for i in announcements
                ]
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
