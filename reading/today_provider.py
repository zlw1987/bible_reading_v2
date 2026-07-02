"""Reading module's Today provider (MODULAR-CORE.3B).

Owns the "Today's Reading" slice of the home context: the signed-in user's
own plan enrollments, current-day passages, and check-in state. The provider
body moved here from ``reading.views`` so each module owns its Today slice;
registration stays explicit — ``reading.views`` (the home route's module)
calls :func:`register` at import time, before any ``home()`` request.
"""

from core.today_providers import register_today_provider

from .models import CheckIn, PlanEnrollment, ReadingPlanDay
from .passage_services import get_memory_passages, get_reading_passages

TODAY_DEFAULTS = {"today_items": [], "ended_plan_count": 0}


def reading_today_provider(request):
    """Today's Reading: the user's own plan enrollments and check-ins."""
    enrollments = (
        PlanEnrollment.objects.filter(user=request.user)
        .select_related("active_plan", "active_plan__plan")
        .order_by("-joined_at")
    )

    today_items = []
    ended_plan_count = 0

    for enrollment in enrollments:
        active_plan = enrollment.active_plan
        current_day_number = active_plan.current_day_number()

        plan_days = list(
            ReadingPlanDay.objects.filter(plan=active_plan.plan).order_by("day_number")
        )

        total_reading_days = len(plan_days)
        max_day_number = max([day.day_number for day in plan_days], default=0)

        checked_days = CheckIn.objects.filter(
            user=request.user,
            active_plan=active_plan,
        ).count()

        progress_percent = (
            round((checked_days / total_reading_days) * 100)
            if total_reading_days
            else 0
        )

        plan_day = None
        passages = []
        memory_passages = []
        is_checked = False

        is_not_started = current_day_number < 1
        is_ended = bool(max_day_number and current_day_number > max_day_number)
        is_rest_day = False
        is_reading_day = False

        if is_ended:
            ended_plan_count += 1
            continue
        if is_not_started:
            continue

        if not is_not_started and not is_ended:
            plan_day = next(
                (day for day in plan_days if day.day_number == current_day_number),
                None,
            )

            if plan_day:
                is_reading_day = True
                passages = get_reading_passages(plan_day)
                memory_passages = get_memory_passages(plan_day) if plan_day.memory_verse else []
                is_checked = CheckIn.objects.filter(
                    user=request.user,
                    active_plan=active_plan,
                    plan_day=plan_day,
                ).exists()
            else:
                is_rest_day = True

        today_items.append(
            {
                "active_plan": active_plan,
                "has_pinned_guide": active_plan.guide_posts.filter(
                    is_pinned=True,
                    is_published=True,
                ).exists(),
                "current_day_number": current_day_number,
                "max_day_number": max_day_number,
                "plan_day": plan_day,
                "passages": passages,
                "memory_passages": memory_passages,
                "is_checked": is_checked,
                "is_not_started": is_not_started,
                "is_ended": is_ended,
                "is_rest_day": is_rest_day,
                "is_reading_day": is_reading_day,
                "checked_days": checked_days,
                "total_reading_days": total_reading_days,
                "progress_percent": progress_percent,
            }
        )

    return {
        "today_items": today_items,
        "ended_plan_count": ended_plan_count,
    }


def register():
    """Register the reading Today provider (called from ``reading.views``)."""
    register_today_provider(
        "reading",
        reading_today_provider,
        defaults=TODAY_DEFAULTS,
    )
