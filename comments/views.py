from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST
from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Q
from django.utils import timezone

from reading.bible_sources import parse_reading_text
from reading.passage_services import get_reading_passages
from reading.models import ActivePlan, PlanEnrollment, ReadingPlanDay

from .forms import (
    ReflectionCommentEditForm,
    ReflectionCommentForm,
    ReflectionReplyForm,
    ReflectionReportForm,
)
from .models import ReflectionComment, ReflectionReport


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
    passages = get_reading_passages(plan_day)

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

    form = ReflectionReplyForm(request.POST)

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
def edit_comment(request, comment_id):
    comment = get_object_or_404(
        ReflectionComment.objects.select_related(
            "user",
            "parent",
            "parent__small_group_at_post",
            "small_group_at_post",
        ),
        id=comment_id,
    )

    if comment.user != request.user:
        messages.error(request, "You do not have permission to edit this reflection.")
        return redirect_back_or_home(request)

    if comment.is_deleted:
        messages.error(request, "Deleted reflections cannot be edited.")
        return redirect_back_or_home(request)

    is_reply = comment.parent_id is not None

    if request.method == "POST":
        form = ReflectionCommentEditForm(
            request.POST,
            instance=comment,
            user=request.user,
            is_reply=is_reply,
        )

        if form.is_valid():
            edited_comment = form.save(commit=False)

            if is_reply:
                # Replies inherit the parent reflection's context.
                edited_comment.visibility = comment.parent.visibility
                edited_comment.small_group_at_post = comment.parent.small_group_at_post
                edited_comment.scripture_ref_key = comment.parent.scripture_ref_key
                edited_comment.scripture_display_zh = comment.parent.scripture_display_zh
                edited_comment.scripture_display_en = comment.parent.scripture_display_en
            else:
                # If sharing to group, bind it to the user's current group.
                if edited_comment.visibility == ReflectionComment.VISIBILITY_GROUP:
                    edited_comment.small_group_at_post = getattr(
                        getattr(request.user, "profile", None),
                        "small_group",
                        None,
                    )

            edited_comment.save()

            messages.success(request, "Reflection updated.")

            safe_next_url = get_safe_next_url(request)

            if safe_next_url:
                return redirect(safe_next_url)

            return redirect("home")
    else:
        form = ReflectionCommentEditForm(
            instance=comment,
            user=request.user,
            is_reply=is_reply,
        )

    return render(
        request,
        "comments/edit_comment.html",
        {
            "comment": comment,
            "form": form,
            "is_reply": is_reply,
            "return_url": get_safe_next_url(request),
        },
    )

@login_required
def report_comment(request, comment_id):
    comment = get_object_or_404(
        ReflectionComment.objects.select_related(
            "user",
            "active_plan",
            "plan_day",
            "small_group_at_post",
        ),
        id=comment_id,
    )

    if not comment.can_be_seen_by(request.user):
        messages.error(request, "You do not have permission to report this reflection.")
        return redirect_back_or_home(request)

    if comment.user == request.user:
        messages.error(request, "You cannot report your own reflection.")
        return redirect_back_or_home(request)

    if request.method == "POST":
        form = ReflectionReportForm(request.POST)

        if form.is_valid():
            report, created = ReflectionReport.objects.get_or_create(
                comment=comment,
                reporter=request.user,
                defaults={
                    "reason": form.cleaned_data.get("reason", ""),
                },
            )

            if created:
                messages.success(request, "Reflection reported. Thank you.")
            else:
                messages.info(request, "You have already reported this reflection.")

            safe_next_url = get_safe_next_url(request)
            if safe_next_url:
                return redirect(safe_next_url)

            return redirect("home")
    else:
        form = ReflectionReportForm()

    return render(
        request,
        "comments/report_comment.html",
        {
            "comment": comment,
            "form": form,
            "return_url": get_safe_next_url(request),
        },
    )

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

@staff_member_required
def staff_reflection_reports(request):
    status = (request.GET.get("status") or ReflectionReport.STATUS_OPEN).strip()
    query = (request.GET.get("q") or "").strip()

    reports = (
        ReflectionReport.objects
        .select_related(
            "comment",
            "comment__user",
            "comment__active_plan",
            "comment__plan_day",
            "comment__small_group_at_post",
            "reporter",
            "reviewed_by",
        )
        .order_by("-created_at")
    )

    if status in {
        ReflectionReport.STATUS_OPEN,
        ReflectionReport.STATUS_REVIEWED,
        ReflectionReport.STATUS_DISMISSED,
    }:
        reports = reports.filter(status=status)

    if query:
        reports = reports.filter(
            Q(comment__body__icontains=query)
            | Q(comment__user__username__icontains=query)
            | Q(reporter__username__icontains=query)
            | Q(reason__icontains=query)
            | Q(comment__scripture_ref_key__icontains=query)
        ).distinct()

    return render(
        request,
        "comments/staff/reflection_reports.html",
        {
            "reports": reports,
            "status": status,
            "query": query,
        },
    )


@staff_member_required
def staff_reflection_action(request, comment_id):
    if request.method != "POST":
        return redirect("staff_reflection_reports")

    comment = get_object_or_404(
        ReflectionComment.objects.select_related("user"),
        id=comment_id,
    )

    action = request.POST.get("action")
    reason = (request.POST.get("reason") or "").strip()

    if action == "hide":
        comment.is_hidden = True
        comment.hidden_reason = reason
        comment.hidden_by = request.user
        comment.hidden_at = timezone.now()
        comment.save(
            update_fields=[
                "is_hidden",
                "hidden_reason",
                "hidden_by",
                "hidden_at",
            ]
        )
        messages.success(request, "Reflection hidden.")

    elif action == "unhide":
        comment.is_hidden = False
        comment.hidden_reason = ""
        comment.hidden_by = None
        comment.hidden_at = None
        comment.save(
            update_fields=[
                "is_hidden",
                "hidden_reason",
                "hidden_by",
                "hidden_at",
            ]
        )
        messages.success(request, "Reflection unhidden.")

    elif action == "mark_reviewed":
        ReflectionReport.objects.filter(
            comment=comment,
            status=ReflectionReport.STATUS_OPEN,
        ).update(
            status=ReflectionReport.STATUS_REVIEWED,
            reviewed_by=request.user,
            reviewed_at=timezone.now(),
        )
        messages.success(request, "Reports marked reviewed.")

    elif action == "dismiss_reports":
        ReflectionReport.objects.filter(
            comment=comment,
            status=ReflectionReport.STATUS_OPEN,
        ).update(
            status=ReflectionReport.STATUS_DISMISSED,
            reviewed_by=request.user,
            reviewed_at=timezone.now(),
        )
        messages.success(request, "Reports dismissed.")

    else:
        messages.error(request, "Unknown moderation action.")

    return redirect("staff_reflection_reports")