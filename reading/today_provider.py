"""Reading module's Today provider (MODULAR-CORE.3B).

Owns the "Today's Reading" slice of the home context: the signed-in user's
own plan enrollments, current-day passages, and check-in state. The provider
body moved here from ``reading.views`` so each module owns its Today slice;
registration stays explicit — ``reading.views`` (the home route's module)
calls :func:`register` at import time, before any ``home()`` request.
"""

from core.today_providers import register_today_provider
from django.db.models import Count, Exists, Max, OuterRef, Q

from .models import CheckIn, PlanEnrollment, ReadingGuidePost, ReadingPlanDay
from .passage_services import get_memory_passages, get_reading_passages

TODAY_DEFAULTS = {
    "today_items": [],
    "ended_plan_count": 0,
    "other_plan_items": [],
}


def reading_today_provider(request):
    """Today's Reading: the user's own plan enrollments and check-ins.

    ``today_items`` holds only *in-progress* plans (a reading day or a rest
    day today) — the plans that can be a Today hero. ``other_plan_items`` holds
    the user's not-started and ended plans in a compact shape so the Today
    presentation layer (``reading.today_presentation``) can list them as
    secondary rows when a hero exists, without changing which plans are
    eligible to be the hero. ``ended_plan_count`` is preserved for the
    single-plan / no-hero empty-state copy and stays authoritative.
    """
    enrollments = list(
        PlanEnrollment.objects.filter(user=request.user)
        .select_related("active_plan", "active_plan__plan")
        .annotate(
            has_pinned_guide=Exists(
                ReadingGuidePost.objects.filter(
                    active_plan_id=OuterRef("active_plan_id"),
                    is_pinned=True,
                    is_published=True,
                )
            ),
            today_total_reading_days=Count(
                "active_plan__plan__days",
                distinct=True,
            ),
            today_max_day_number=Max(
                "active_plan__plan__days__day_number",
            ),
        )
        .order_by("-joined_at")
    )

    enrollment_states = []
    current_day_pairs = set()
    for enrollment in enrollments:
        active_plan = enrollment.active_plan
        current_day_number = active_plan.current_day_number()
        total_reading_days = enrollment.today_total_reading_days
        max_day_number = enrollment.today_max_day_number or 0
        has_configured_days = total_reading_days > 0
        is_not_started = current_day_number < 1
        is_ended = bool(
            has_configured_days and current_day_number > max_day_number
        )
        if has_configured_days and not is_not_started and not is_ended:
            current_day_pairs.add((active_plan.plan_id, current_day_number))
        enrollment_states.append(
            {
                "enrollment": enrollment,
                "active_plan": active_plan,
                "current_day_number": current_day_number,
                "total_reading_days": total_reading_days,
                "max_day_number": max_day_number,
                "has_configured_days": has_configured_days,
                "is_not_started": is_not_started,
                "is_ended": is_ended,
            }
        )

    current_day_conditions = Q()
    for plan_id, day_number in current_day_pairs:
        current_day_conditions |= Q(
            plan_id=plan_id,
            day_number=day_number,
        )
    current_plan_days = (
        list(
            ReadingPlanDay.objects.filter(current_day_conditions)
            .prefetch_related("structured_passages")
            .order_by("plan_id", "day_number")
        )
        if current_day_pairs
        else []
    )
    current_plan_day_by_pair = {
        (plan_day.plan_id, plan_day.day_number): plan_day
        for plan_day in current_plan_days
    }

    checkin_summary = {
        row["active_plan_id"]: row
        for row in (
            CheckIn.objects.filter(
                user=request.user,
                active_plan_id__in=[
                    state["active_plan"].id for state in enrollment_states
                ],
            )
            .values("active_plan_id")
            .annotate(checked_days=Count("id"))
        )
    }

    exact_today_pairs = {
        (
            state["active_plan"].id,
            current_plan_day_by_pair[
                (
                    state["active_plan"].plan_id,
                    state["current_day_number"],
                )
            ].id,
        )
        for state in enrollment_states
        if (
            state["active_plan"].plan_id,
            state["current_day_number"],
        )
        in current_plan_day_by_pair
    }
    today_checkin_conditions = Q()
    for active_plan_id, plan_day_id in exact_today_pairs:
        today_checkin_conditions |= Q(
            active_plan_id=active_plan_id,
            plan_day_id=plan_day_id,
        )
    checked_today_pairs = (
        set(
            CheckIn.objects.filter(
                today_checkin_conditions,
                user=request.user,
            ).values_list("active_plan_id", "plan_day_id")
        )
        if exact_today_pairs
        else set()
    )

    today_items = []
    ended_plan_count = 0
    other_plan_items = []

    for state in enrollment_states:
        enrollment = state["enrollment"]
        active_plan = state["active_plan"]
        current_day_number = state["current_day_number"]
        total_reading_days = state["total_reading_days"]
        max_day_number = state["max_day_number"]
        has_configured_days = state["has_configured_days"]
        checkins = checkin_summary.get(active_plan.id, {})
        checked_days = checkins.get("checked_days", 0)

        progress_percent = (
            round((checked_days / total_reading_days) * 100)
            if total_reading_days
            else 0
        )

        plan_day = None
        passages = []
        memory_passages = []
        is_checked = False

        is_not_started = state["is_not_started"]
        is_ended = state["is_ended"]
        is_rest_day = False
        is_reading_day = False

        if is_ended or is_not_started:
            if is_ended:
                ended_plan_count += 1
            other_plan_items.append(
                {
                    "active_plan": active_plan,
                    "current_day_number": current_day_number,
                    "max_day_number": max_day_number,
                    "checked_days": checked_days,
                    "total_reading_days": total_reading_days,
                    "progress_percent": progress_percent,
                    "has_configured_days": has_configured_days,
                    "is_not_started": is_not_started,
                    "is_ended": is_ended,
                }
            )
            continue

        if not is_not_started and not is_ended:
            plan_day = current_plan_day_by_pair.get(
                (active_plan.plan_id, current_day_number)
            )
            if plan_day:
                is_reading_day = True
                passages = get_reading_passages(plan_day)
                memory_passages = get_memory_passages(plan_day) if plan_day.memory_verse else []
                is_checked = (
                    active_plan.id,
                    plan_day.id,
                ) in checked_today_pairs
            elif has_configured_days:
                is_rest_day = True

        today_items.append(
            {
                "active_plan": active_plan,
                "has_pinned_guide": enrollment.has_pinned_guide,
                "current_day_number": current_day_number,
                "max_day_number": max_day_number,
                "plan_day": plan_day,
                "passages": passages,
                "memory_passages": memory_passages,
                "is_checked": is_checked,
                "is_not_started": is_not_started,
                "is_ended": is_ended,
                "has_configured_days": has_configured_days,
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
        "other_plan_items": other_plan_items,
    }


def register():
    """Register the reading Today provider (called from ``reading.views``)."""
    register_today_provider(
        "reading",
        reading_today_provider,
        defaults=TODAY_DEFAULTS,
    )
