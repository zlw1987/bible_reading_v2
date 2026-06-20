from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST
from django.contrib.admin.views.decorators import staff_member_required
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from reading.bible_sources import parse_reading_text
from reading.passage_services import get_reading_passages
from reading.models import ActivePlan, PlanEnrollment, ReadingPlanDay
from accounts.language import get_user_language

from .forms import (
    ReflectionCommentEditForm,
    ReflectionCommentForm,
    ReflectionReplyForm,
    ReflectionReportForm,
)
from .models import ReflectionComment, ReflectionReport
from .reflection_visibility import get_user_group_reflection_write_context


MESSAGE_TEXT = {
    "en": {
        "join_before_commenting": "You need to join this plan before commenting.",
        "passage_missing": "This scripture passage could not be found.",
        "reflection_posted": "Your reflection has been posted.",
        "reflection_form_error": "Please correct the reflection form.",
        "reply_permission": "You do not have permission to reply to this reflection.",
        "missing_plan_context": "This reflection is missing plan context.",
        "reply_posted": "Your reply has been posted.",
        "reply_form_error": "Please correct the reply form.",
        "edit_permission": "You do not have permission to edit this reflection.",
        "deleted_edit": "Deleted reflections cannot be edited.",
        "reflection_updated": "Reflection updated.",
        "report_permission": "You do not have permission to report this reflection.",
        "report_own": "You cannot report your own reflection.",
        "reported": "Reflection reported. Thank you.",
        "already_reported": "You have already reported this reflection.",
        "delete_permission": "You do not have permission to delete this reflection.",
        "deleted": "Reflection deleted.",
    },
    "zh": {
        "join_before_commenting": "你需要先加入这个计划，才能发表评论。",
        "passage_missing": "找不到这段经文。",
        "reflection_posted": "你的默想已发表。",
        "reflection_form_error": "请修正默想表单。",
        "reply_permission": "你没有权限回复这条默想。",
        "missing_plan_context": "这条默想缺少读经计划信息。",
        "reply_posted": "你的回复已发表。",
        "reply_form_error": "请修正回复表单。",
        "edit_permission": "你没有权限编辑这条默想。",
        "deleted_edit": "已删除的默想不能编辑。",
        "reflection_updated": "默想已更新。",
        "report_permission": "你没有权限举报这条默想。",
        "report_own": "你不能举报自己的默想。",
        "reported": "默想已举报。谢谢。",
        "already_reported": "你已经举报过这条默想。",
        "delete_permission": "你没有权限删除这条默想。",
        "deleted": "默想已删除。",
    },
}


def message_text(request, key):
    return MESSAGE_TEXT[get_user_language(request)][key]


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
        messages.error(request, message_text(request, "join_before_commenting"))
        return redirect_back_or_home(request)

    passage = get_passage_or_none(plan_day, passage_index)

    if passage is None:
        messages.error(request, message_text(request, "passage_missing"))
        return redirect_back_or_home(request)

    form = ReflectionCommentForm(
        request.POST,
        user=request.user,
        language=get_user_language(request),
    )

    if form.is_valid():
        comment = form.save(commit=False)
        comment.user = request.user
        comment.active_plan = active_plan
        comment.plan_day = plan_day
        comment.scripture_ref_key = passage["search_text"]
        comment.scripture_display_zh = passage.get("display_zh", passage["display"])
        comment.scripture_display_en = passage.get("display_en", passage["display"])

        # CS-CORE.4G.3: stamp the group reflection snapshot from the
        # membership-core write context (active primary ChurchStructureMembership),
        # never from Profile.small_group.
        write_context = get_user_group_reflection_write_context(request.user)

        if (
            comment.visibility == ReflectionComment.VISIBILITY_GROUP
            and not write_context.can_share_to_group
        ):
            # Defensive fail-closed: the form already rejects group visibility
            # without a valid membership context; never persist a group post
            # that lacks a structure snapshot.
            messages.error(request, message_text(request, "reflection_form_error"))
            return redirect_back_or_home(request)

        comment.structure_unit_at_post = write_context.structure_unit
        # REFLECTION-MIRROR.1D: stop writing the legacy small_group_at_post
        # mirror. Visibility is driven entirely by structure_unit_at_post; the
        # legacy field stays null on new posts (existing rows are untouched).
        comment.small_group_at_post = None
        comment.save()

        messages.success(request, message_text(request, "reflection_posted"))
    else:
        messages.error(request, message_text(request, "reflection_form_error"))

    return redirect_back_or_home(request)


@login_required
@require_POST
def add_reply(request, comment_id):
    parent = get_object_or_404(
        ReflectionComment.objects.select_related(
            "active_plan",
            "plan_day",
            "user",
            "structure_unit_at_post",
        ),
        id=comment_id,
        parent__isnull=True,
        is_deleted=False,
    )

    if not parent.can_be_seen_by(request.user):
        messages.error(request, message_text(request, "reply_permission"))
        return redirect_back_or_home(request)

    if parent.active_plan is None:
        messages.error(request, message_text(request, "missing_plan_context"))
        return redirect_back_or_home(request)

    form = ReflectionReplyForm(request.POST, language=get_user_language(request))

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
        # REFLECTION-MIRROR.1D: replies inherit the parent structure snapshot for
        # visibility but no longer inherit the legacy small_group_at_post mirror.
        reply.small_group_at_post = None
        reply.structure_unit_at_post = parent.structure_unit_at_post
        reply.save()

        messages.success(request, message_text(request, "reply_posted"))
    else:
        messages.error(request, message_text(request, "reply_form_error"))

    return redirect_back_or_home(request)

@login_required
def edit_comment(request, comment_id):
    comment = get_object_or_404(
        ReflectionComment.objects.select_related(
            "user",
            "parent",
            "parent__structure_unit_at_post",
            "structure_unit_at_post",
        ),
        id=comment_id,
    )

    if comment.user != request.user:
        messages.error(request, message_text(request, "edit_permission"))
        return redirect_back_or_home(request)

    if comment.is_deleted:
        messages.error(request, message_text(request, "deleted_edit"))
        return redirect_back_or_home(request)

    is_reply = comment.parent_id is not None
    pre_edit_visibility = comment.visibility
    pre_edit_structure_unit_at_post = comment.structure_unit_at_post

    if request.method == "POST":
        form = ReflectionCommentEditForm(
            request.POST,
            instance=comment,
            user=request.user,
            is_reply=is_reply,
            language=get_user_language(request),
        )

        if form.is_valid():
            edited_comment = form.save(commit=False)

            if is_reply:
                # Replies inherit the parent reflection's context for visibility.
                # REFLECTION-MIRROR.1D: inherit structure_unit_at_post but do not
                # re-write the legacy small_group_at_post mirror; the reply keeps
                # its own stored (legacy or null) value unchanged.
                edited_comment.visibility = comment.parent.visibility
                edited_comment.structure_unit_at_post = comment.parent.structure_unit_at_post
                edited_comment.scripture_ref_key = comment.parent.scripture_ref_key
                edited_comment.scripture_display_zh = comment.parent.scripture_display_zh
                edited_comment.scripture_display_en = comment.parent.scripture_display_en
            else:
                if edited_comment.visibility == ReflectionComment.VISIBILITY_GROUP:
                    if pre_edit_visibility == ReflectionComment.VISIBILITY_GROUP:
                        # Policy C: preserve the original group snapshot; never
                        # re-home an existing group post to current membership.
                        # REFLECTION-MIRROR.1D: preserve structure_unit_at_post and
                        # leave the existing small_group_at_post value untouched
                        # (no new write / reintroduction of the legacy mirror).
                        edited_comment.structure_unit_at_post = pre_edit_structure_unit_at_post
                    else:
                        # CS-CORE.4G.3: newly entering group visibility stamps the
                        # snapshot from the membership-core write context, not
                        # Profile.small_group. The form rejects this transition
                        # without a valid context, so structure_unit is set here.
                        # REFLECTION-MIRROR.1D: leave small_group_at_post null.
                        write_context = get_user_group_reflection_write_context(request.user)
                        edited_comment.structure_unit_at_post = write_context.structure_unit
                        edited_comment.small_group_at_post = None

            edited_comment.save()

            messages.success(request, message_text(request, "reflection_updated"))

            safe_next_url = get_safe_next_url(request)

            if safe_next_url:
                return redirect(safe_next_url)

            return redirect("home")
    else:
        form = ReflectionCommentEditForm(
            instance=comment,
            user=request.user,
            is_reply=is_reply,
            language=get_user_language(request),
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
        ),
        id=comment_id,
    )

    if not comment.can_be_seen_by(request.user):
        messages.error(request, message_text(request, "report_permission"))
        return redirect_back_or_home(request)

    if comment.user == request.user:
        messages.error(request, message_text(request, "report_own"))
        return redirect_back_or_home(request)

    if request.method == "POST":
        form = ReflectionReportForm(request.POST, language=get_user_language(request))

        if form.is_valid():
            report, created = ReflectionReport.objects.get_or_create(
                comment=comment,
                reporter=request.user,
                defaults={
                    "reason": form.cleaned_data.get("reason", ""),
                },
            )

            if created:
                messages.success(request, message_text(request, "reported"))
            else:
                messages.info(request, message_text(request, "already_reported"))

            safe_next_url = get_safe_next_url(request)
            if safe_next_url:
                return redirect(safe_next_url)

            return redirect("home")
    else:
        form = ReflectionReportForm(language=get_user_language(request))

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
        messages.error(request, message_text(request, "delete_permission"))
        return redirect_back_or_home(request)

    comment.is_deleted = True
    comment.body = ""
    comment.save(update_fields=["is_deleted", "body"])

    messages.success(request, message_text(request, "deleted"))
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


def close_open_reflection_reports_for_content(comment, reviewer):
    """Mark all open reports for ``comment`` as reviewed.

    Used when a comment is hidden so the moderation queue does not keep
    showing already-handled items. Returns the number of reports updated.
    """
    return ReflectionReport.objects.filter(
        comment=comment,
        status=ReflectionReport.STATUS_OPEN,
    ).update(
        status=ReflectionReport.STATUS_REVIEWED,
        reviewed_by=reviewer,
        reviewed_at=timezone.now(),
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
        with transaction.atomic():
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
            close_open_reflection_reports_for_content(comment, request.user)
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
