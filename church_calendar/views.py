"""Authenticated, read-only member Church Calendar routes (CHURCH-CALENDAR.1A).

Both views are ``login_required`` and expose member-facing content only. They
carry no edit / publish / review / assignment / attendance / staff-management
controls, and they never widen visibility for staff, superuser, manager,
creator, or co-organizer accounts: they rely entirely on the member-safe
aggregator in :mod:`church_calendar.providers`.

CHURCH-CALENDAR.1C renders the final member-facing month grid and day detail on
top of the 1B source providers. Presentation-only arrangement (local-day
bucketing, timed/announcement split, deterministic sorting) lives in
:mod:`church_calendar.presentation`; these views never re-check visibility or
widen the member-safe aggregator result.
"""

from datetime import date

from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import render
from django.utils import timezone

from . import presentation, ranges
from .providers import ITEM_TYPE_LABELS, ITEM_TYPE_ORDER, collect_calendar_items


def _type_legend():
    """Bilingual type-legend / placeholder labels in stable display order."""
    return [
        {
            "item_type": item_type,
            "label_en": ITEM_TYPE_LABELS[item_type][0],
            "label_zh": ITEM_TYPE_LABELS[item_type][1],
        }
        for item_type in ITEM_TYPE_ORDER
    ]


@login_required
def church_calendar_month(request):
    """Month overview shell for the signed-in member's visible calendar items.

    Defaults to the current local month; an optional ``?month=YYYY-MM`` selects
    another month and fails safe to the current month when invalid.
    """
    today = timezone.localdate()
    year, month = ranges.parse_month_param(
        request.GET.get("month"),
        default=(today.year, today.month),
    )

    range_start, range_end = ranges.month_bounds(year, month)
    items = collect_calendar_items(request.user, range_start, range_end)

    weeks = presentation.build_month_weeks(
        ranges.month_grid(year, month),
        items,
        month=month,
        today=today,
    )

    previous_year, previous_month = ranges.shift_month(year, month, -1)
    next_year, next_month = ranges.shift_month(year, month, 1)

    context = {
        "active_nav": "church_calendar",
        "calendar_year": year,
        "calendar_month": month,
        "month_start": date(year, month, 1),
        "calendar_weeks": weeks,
        "calendar_items": items,
        "has_items": bool(items),
        "type_legend": _type_legend(),
        "previous_month_param": f"{previous_year:04d}-{previous_month:02d}",
        "next_month_param": f"{next_year:04d}-{next_month:02d}",
        "is_current_month": year == today.year and month == today.month,
    }
    return render(request, "church_calendar/month.html", context)


@login_required
def church_calendar_day(request, year, month, day):
    """Day detail shell for one local date's visible calendar items."""
    try:
        target_date = date(year, month, day)
    except ValueError:
        raise Http404("Invalid calendar date.")

    range_start, range_end = ranges.day_bounds(target_date)
    items = collect_calendar_items(request.user, range_start, range_end)
    sections = presentation.build_day_sections(items)

    today = timezone.localdate()
    context = {
        "active_nav": "church_calendar",
        "calendar_date": target_date,
        "is_today": target_date == today,
        "calendar_items": items,
        "has_items": bool(items),
        "timed_items": sections["timed"],
        "announcement_items": sections["announcements"],
        "type_legend": _type_legend(),
        "month_param": f"{target_date.year:04d}-{target_date.month:02d}",
    }
    return render(request, "church_calendar/day.html", context)
