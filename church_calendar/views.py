"""Authenticated, read-only member Church Calendar routes (CHURCH-CALENDAR.1A).

Both views are ``login_required`` and expose member-facing content only. They
carry no edit / publish / review / assignment / attendance / staff-management
controls, and they never widen visibility for staff, superuser, manager,
creator, or co-organizer accounts: they rely entirely on the member-safe
aggregator in :mod:`church_calendar.providers`.

This slice ships the month/day shells and safe empty states. Real source
provider integration and the final month/day presentation arrive in later
approved slices.
"""

from datetime import date

from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import render
from django.utils import timezone

from . import ranges
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

    weeks = []
    for week in ranges.month_grid(year, month):
        weeks.append(
            [
                {
                    "date": cell_date,
                    "in_month": cell_date.month == month,
                    "is_today": cell_date == today,
                }
                for cell_date in week
            ]
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

    today = timezone.localdate()
    context = {
        "active_nav": "church_calendar",
        "calendar_date": target_date,
        "is_today": target_date == today,
        "calendar_items": items,
        "has_items": bool(items),
        "type_legend": _type_legend(),
        "month_param": f"{target_date.year:04d}-{target_date.month:02d}",
    }
    return render(request, "church_calendar/day.html", context)
