from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import get_object_or_404, redirect, render

from .forms import (
    ReadingPlanDayCreateForm,
    ReadingPlanDayLineForm,
    ReadingPlanHeaderForm,
)
from .models import ReadingPlan, ReadingPlanDay
from .passage_services import sync_plan_day_passages

@staff_member_required
def staff_reading_plan_list(request):
    plans = ReadingPlan.objects.order_by("name")

    return render(
        request,
        "reading/staff/reading_plan_list.html",
        {
            "plans": plans,
        },
    )


@staff_member_required
def staff_reading_plan_header(request, plan_id):
    plan = get_object_or_404(ReadingPlan, id=plan_id)

    if request.method == "POST":
        form = ReadingPlanHeaderForm(request.POST, instance=plan)

        if form.is_valid():
            form.save()
            messages.success(request, "Reading plan header saved.")
            return redirect("staff_reading_plan_header", plan_id=plan.id)
    else:
        form = ReadingPlanHeaderForm(instance=plan)

    return render(
        request,
        "reading/staff/reading_plan_header.html",
        {
            "plan": plan,
            "form": form,
        },
    )


@staff_member_required
def staff_reading_plan_days(request, plan_id):
    plan = get_object_or_404(ReadingPlan, id=plan_id)

    if request.method == "POST":
        action = request.POST.get("action")

        if action == "save_day":
            day_id = request.POST.get("day_id")
            day = get_object_or_404(
                ReadingPlanDay,
                id=day_id,
                plan=plan,
            )

            form = ReadingPlanDayLineForm(request.POST, instance=day)

            if form.is_valid():
                day = form.save()
                sync_plan_day_passages(day)
                messages.success(
                    request,
                    f"Day {day.day_number} saved.",
                )
                return redirect("staff_reading_plan_days", plan_id=plan.id)

            messages.error(request, "Please correct the error in the day row.")

        elif action == "add_day":
            form = ReadingPlanDayCreateForm(request.POST)

            if form.is_valid():
                new_day = form.save(commit=False)
                new_day.plan = plan
                new_day.save()
                sync_plan_day_passages(new_day)
                messages.success(request, f"Day {new_day.day_number} added.")
                return redirect("staff_reading_plan_days", plan_id=plan.id)

            messages.error(request, "Please correct the error in the new day form.")

        elif action == "delete_day":
            day_id = request.POST.get("day_id")
            day = get_object_or_404(
                ReadingPlanDay,
                id=day_id,
                plan=plan,
            )
            day_number = day.day_number
            day.delete()
            messages.success(request, f"Day {day_number} deleted.")
            return redirect("staff_reading_plan_days", plan_id=plan.id)

    days = ReadingPlanDay.objects.filter(plan=plan).order_by("day_number")

    day_rows = [
        {
            "day": day,
            "form": ReadingPlanDayLineForm(instance=day),
        }
        for day in days
    ]

    create_form = ReadingPlanDayCreateForm()

    return render(
        request,
        "reading/staff/reading_plan_days.html",
        {
            "plan": plan,
            "day_rows": day_rows,
            "create_form": create_form,
        },
    )