from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from reading.bible_sources import parse_reading_text
from reading.models import ActivePlan, PlanEnrollment, ReadingPlanDay

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


def user_can_access_active_plan(user, active_plan):
    return PlanEnrollment.objects.filter(
        user=user,
        active_plan=active_plan,
    ).exists()


def get_passage_or_none(plan_day, passage_index):
    passages = parse_reading_text(plan_day.reading_text)

    if passage_index < 0 or passage_index >= len(passages):
        return None

    return passages[passage_index]


@login_required
@require_POST
def add_comment(request, active_plan_id, plan_day_id, passage_index):
    active_plan = get_object_or_404(
        ActivePlan.objects.select_related("plan"),
        id=active_plan_id,
    )

    plan_day = get_object_or_404(
        ReadingPlanDay,
        id=plan_day_id,
        plan=active_plan.plan,
    )

    if not user_can_access_active_plan(request.user, active_plan):
        messages.error(request, "You need to join this plan before commenting.")
        return redirect_back_or_home(request)

    passage = get_passage_or_none(plan_day, passage_index)

    if passage is None:
        messages.error(request, "This scripture passage could not be found.")
        return redirect_back_or_home(request)

    form = ReflectionCommentForm(request.POST, user=request.user)

    if form.is_valid():
        comment = form.save(commit=False)
        comment.user = request.user
        comment.active_plan = active_plan
        comment.plan_day = plan_day
        comment.scripture_ref_key = passage["search_text"]
        comment.scripture_display_zh = passage.get("display_zh", passage["display"])
        comment.scripture_display_en = passage.get("display_en", passage["display"])
        comment.small_group_at_post = getattr(request.user.profile, "small_group", None)
        comment.save()

        messages.success(request, "Your reflection has been posted.")
    else:
        messages.error(request, "Please correct the reflection form.")

    return redirect_back_or_home(request)


@login_required
@require_POST
def add_reply(request, comment_id):
    parent = get_object_or_404(
        ReflectionComment.objects.select_related(
            "active_plan",
            "plan_day",
            "user",
            "small_group_at_post",
        ),
        id=comment_id,
        parent__isnull=True,
        is_deleted=False,
    )

    if not parent.can_be_seen_by(request.user):
        messages.error(request, "You do not have permission to reply to this reflection.")
        return redirect_back_or_home(request)

    if parent.active_plan is None:
        messages.error(request, "This reflection is missing plan context.")
        return redirect_back_or_home(request)

    form = ReflectionCommentForm(request.POST, user=request.user)

    if form.is_valid():
        reply = form.save(commit=False)
        reply.user = request.user
        reply.active_plan = parent.active_plan
        reply.plan_day = parent.plan_day
        reply.parent = parent
        reply.scripture_ref_key = parent.scripture_ref_key
        reply.scripture_display_zh = parent.scripture_display_zh
        reply.scripture_display_en = parent.scripture_display_en
        reply.visibility = parent.visibility
        reply.small_group_at_post = parent.small_group_at_post
        reply.save()

        messages.success(request, "Your reply has been posted.")
    else:
        messages.error(request, "Please correct the reply form.")

    return redirect_back_or_home(request)


@login_required
@require_POST
def delete_comment(request, comment_id):
    comment = get_object_or_404(ReflectionComment, id=comment_id)

    if comment.user != request.user and not request.user.is_staff:
        messages.error(request, "You do not have permission to delete this reflection.")
        return redirect_back_or_home(request)

    comment.is_deleted = True
    comment.body = ""
    comment.save(update_fields=["is_deleted", "body"])

    messages.success(request, "Reflection deleted.")
    return redirect_back_or_home(request)