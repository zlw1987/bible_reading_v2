from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST
from django.utils.http import url_has_allowed_host_and_scheme

from reading.models import PlanEnrollment, ReadingPlanDay
from .forms import ReflectionCommentForm
from .models import ReflectionComment


def get_safe_next_url(request):
    next_url = request.POST.get("next") or request.GET.get("next")

    if next_url and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
    ):
        return next_url

    return None


def redirect_back_or_home(request):
    safe_next_url = get_safe_next_url(request)

    if safe_next_url:
        return redirect(safe_next_url)

    return redirect("home")

def user_can_access_plan_day(user, plan_day):
    return PlanEnrollment.objects.filter(
        user=user,
        active_plan__plan=plan_day.plan,
    ).exists()


@login_required
@require_POST
def add_comment(request, plan_day_id):
    plan_day = get_object_or_404(ReadingPlanDay, id=plan_day_id)

    if not user_can_access_plan_day(request.user, plan_day):
        messages.error(request, "You need to join this plan before commenting.")
        return redirect_back_or_home(request)

    form = ReflectionCommentForm(request.POST)

    if form.is_valid():
        comment = form.save(commit=False)
        comment.user = request.user
        comment.plan_day = plan_day
        comment.save()
        messages.success(request, "Your reflection has been posted.")
    else:
        messages.error(request, "Please enter a valid reflection.")

    return redirect_back_or_home(request)


@login_required
@require_POST
def add_reply(request, comment_id):
    parent = get_object_or_404(
        ReflectionComment.objects.select_related("plan_day"),
        id=comment_id,
        parent__isnull=True,
        is_deleted=False,
    )

    if not user_can_access_plan_day(request.user, parent.plan_day):
        messages.error(request, "You need to join this plan before replying.")
        return redirect_back_or_home(request)

    form = ReflectionCommentForm(request.POST)

    if form.is_valid():
        reply = form.save(commit=False)
        reply.user = request.user
        reply.plan_day = parent.plan_day
        reply.parent = parent
        reply.save()
        messages.success(request, "Your reply has been posted.")
    else:
        messages.error(request, "Please enter a valid reply.")

    return redirect_back_or_home(request)


@login_required
@require_POST
def delete_comment(request, comment_id):
    comment = get_object_or_404(ReflectionComment, id=comment_id)

    if comment.user != request.user and not request.user.is_staff:
        messages.error(request, "You do not have permission to delete this comment.")
        return redirect_back_or_home(request)

    comment.is_deleted = True
    comment.body = ""
    comment.save(update_fields=["is_deleted", "body"])

    messages.success(request, "Comment deleted.")
    return redirect_back_or_home(request)