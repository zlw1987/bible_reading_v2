from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from accounts.language import get_user_language

from .forms import (
    PrayerCommentEditForm,
    PrayerCommentForm,
    PrayerRequestEditForm,
    PrayerRequestForm,
    PrayerStatusForm,
)
from .models import PrayerComment, PrayerMark, PrayerRequest


MESSAGE_TEXT = {
    "en": {
        "prayer_posted": "Prayer request posted.",
        "view_permission": "You do not have permission to view this prayer request.",
        "edit_permission": "You do not have permission to edit this prayer request.",
        "deleted_edit": "Deleted prayer requests cannot be edited.",
        "prayer_updated": "Prayer request updated.",
        "comment_edit_permission": "You do not have permission to edit this comment.",
        "deleted_comment_edit": "Deleted comments cannot be edited.",
        "comment_updated": "Comment updated.",
        "comment_delete_permission": "You do not have permission to delete this comment.",
        "comment_deleted": "Comment deleted.",
        "pray_permission": "You do not have permission to pray for this request.",
        "marked_prayed": "Marked as prayed.",
        "already_prayed": "You have already marked this prayer request.",
        "comment_permission": "You do not have permission to comment on this prayer request.",
        "comment_posted": "Comment posted.",
        "comment_form_error": "Please correct the comment form.",
        "status_permission": "You do not have permission to update this prayer request.",
        "status_form_error": "Please correct the status form.",
        "delete_permission": "You do not have permission to delete this prayer request.",
        "prayer_deleted": "Prayer request deleted.",
    },
    "zh": {
        "prayer_posted": "代祷事项已发表。",
        "view_permission": "你没有权限查看这项代祷。",
        "edit_permission": "你没有权限编辑这项代祷。",
        "deleted_edit": "已删除的代祷事项不能编辑。",
        "prayer_updated": "代祷事项已更新。",
        "comment_edit_permission": "你没有权限编辑这条回应。",
        "deleted_comment_edit": "已删除的回应不能编辑。",
        "comment_updated": "回应已更新。",
        "comment_delete_permission": "你没有权限删除这条回应。",
        "comment_deleted": "回应已删除。",
        "pray_permission": "你没有权限为这项代祷标记已代祷。",
        "marked_prayed": "已标记为已代祷。",
        "already_prayed": "你已经为这项代祷标记过已代祷。",
        "comment_permission": "你没有权限回应这项代祷。",
        "comment_posted": "回应已发表。",
        "comment_form_error": "请修正回应表单。",
        "status_permission": "你没有权限更新这项代祷。",
        "status_form_error": "请修正状态表单。",
        "delete_permission": "你没有权限删除这项代祷。",
        "prayer_deleted": "代祷事项已删除。",
    },
}


def message_text(request, key):
    return MESSAGE_TEXT[get_user_language(request)][key]


def get_user_small_group(user):
    return getattr(getattr(user, "profile", None), "small_group", None)


def get_safe_next_url(request):
    next_url = request.POST.get("next") or request.GET.get("next")

    if next_url and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
    ):
        return next_url

    return None


def get_visible_prayer_filter(user):
    user_group = get_user_small_group(user)

    if user.is_staff:
        return Q()

    visible_filter = Q(user=user)

    visible_filter |= Q(
        is_deleted=False,
        visibility=PrayerRequest.VISIBILITY_CHURCH,
    )

    if user_group:
        visible_filter |= Q(
            is_deleted=False,
            visibility=PrayerRequest.VISIBILITY_GROUP,
            small_group_at_post=user_group,
        )

    return visible_filter


@login_required
def prayer_list(request):
    tab = (request.GET.get("tab") or "group").strip()
    status = (request.GET.get("status") or PrayerRequest.STATUS_OPEN).strip()

    if tab not in {"my", "group", "church"}:
        tab = "group"

    if status not in {
        PrayerRequest.STATUS_OPEN,
        PrayerRequest.STATUS_ANSWERED,
        PrayerRequest.STATUS_CLOSED,
        "all",
    }:
        status = PrayerRequest.STATUS_OPEN

    if request.method == "POST":
        form = PrayerRequestForm(
            request.POST,
            user=request.user,
            language=get_user_language(request),
        )

        if form.is_valid():
            prayer = form.save(commit=False)
            prayer.user = request.user

            if prayer.visibility == PrayerRequest.VISIBILITY_GROUP:
                prayer.small_group_at_post = get_user_small_group(request.user)

            prayer.save()

            messages.success(request, message_text(request, "prayer_posted"))
            return redirect("prayer_detail", prayer_id=prayer.id)
    else:
        form = PrayerRequestForm(user=request.user, language=get_user_language(request))

    base_queryset = (
        PrayerRequest.objects
        .filter(get_visible_prayer_filter(request.user))
        .annotate(pray_count=Count("prayer_marks"))
        .select_related("user", "small_group_at_post")
        .order_by("-created_at")
    )

    if status != "all":
        base_queryset = base_queryset.filter(status=status)

    user_group = get_user_small_group(request.user)

    if tab == "my":
        prayers = base_queryset.filter(user=request.user)

    elif tab == "group":
        if user_group:
            prayers = base_queryset.filter(
                Q(user=request.user)
                | Q(
                    visibility=PrayerRequest.VISIBILITY_GROUP,
                    small_group_at_post=user_group,
                )
            )
        else:
            prayers = base_queryset.filter(user=request.user)

    else:
        prayers = base_queryset.filter(
            Q(user=request.user)
            | Q(visibility=PrayerRequest.VISIBILITY_CHURCH)
        )

    return render(
        request,
        "prayers/prayer_list.html",
        {
            "form": form,
            "prayers": prayers,
            "tab": tab,
            "status": status,
        },
    )


@login_required
def prayer_detail(request, prayer_id):
    prayer = get_object_or_404(
        PrayerRequest.objects
        .annotate(pray_count=Count("prayer_marks"))
        .select_related("user", "small_group_at_post"),
        id=prayer_id,
    )

    if not prayer.can_be_seen_by(request.user):
        messages.error(request, message_text(request, "view_permission"))
        return redirect("prayer_list")

    comments = (
        PrayerComment.objects
        .filter(prayer_request=prayer, is_deleted=False)
        .select_related("user")
        .order_by("created_at")
    )

    has_prayed = PrayerMark.objects.filter(
        prayer_request=prayer,
        user=request.user,
    ).exists()

    return render(
        request,
        "prayers/prayer_detail.html",
        {
            "prayer": prayer,
            "comments": comments,
            "comment_form": PrayerCommentForm(language=get_user_language(request)),
            "status_form": PrayerStatusForm(
                instance=prayer,
                language=get_user_language(request),
            ),
            "has_prayed": has_prayed,
        },
    )

@login_required
def edit_prayer_request(request, prayer_id):
    prayer = get_object_or_404(PrayerRequest, id=prayer_id)

    if not prayer.can_be_managed_by(request.user):
        messages.error(request, message_text(request, "edit_permission"))
        return redirect("prayer_list")

    if prayer.is_deleted:
        messages.error(request, message_text(request, "deleted_edit"))
        return redirect("prayer_list")

    if request.method == "POST":
        form = PrayerRequestEditForm(
            request.POST,
            instance=prayer,
            user=request.user,
            language=get_user_language(request),
        )

        if form.is_valid():
            edited_prayer = form.save(commit=False)

            if edited_prayer.visibility == PrayerRequest.VISIBILITY_GROUP:
                edited_prayer.small_group_at_post = get_user_small_group(request.user)
            elif edited_prayer.visibility == PrayerRequest.VISIBILITY_PRIVATE:
                edited_prayer.small_group_at_post = None

            edited_prayer.save()

            messages.success(request, message_text(request, "prayer_updated"))
            return redirect("prayer_detail", prayer_id=prayer.id)
    else:
        form = PrayerRequestEditForm(
            instance=prayer,
            user=request.user,
            language=get_user_language(request),
        )

    return render(
        request,
        "prayers/edit_prayer_request.html",
        {
            "prayer": prayer,
            "form": form,
        },
    )


@login_required
def edit_prayer_comment(request, comment_id):
    comment = get_object_or_404(
        PrayerComment.objects.select_related("prayer_request", "user"),
        id=comment_id,
    )

    if comment.user != request.user and not request.user.is_staff:
        messages.error(request, message_text(request, "comment_edit_permission"))
        return redirect("prayer_list")

    if comment.is_deleted:
        messages.error(request, message_text(request, "deleted_comment_edit"))
        return redirect("prayer_detail", prayer_id=comment.prayer_request.id)

    if not comment.prayer_request.can_be_seen_by(request.user):
        messages.error(request, message_text(request, "view_permission"))
        return redirect("prayer_list")

    if request.method == "POST":
        form = PrayerCommentEditForm(
            request.POST,
            instance=comment,
            language=get_user_language(request),
        )

        if form.is_valid():
            form.save()
            messages.success(request, message_text(request, "comment_updated"))
            return redirect("prayer_detail", prayer_id=comment.prayer_request.id)
    else:
        form = PrayerCommentEditForm(
            instance=comment,
            language=get_user_language(request),
        )

    return render(
        request,
        "prayers/edit_prayer_comment.html",
        {
            "comment": comment,
            "prayer": comment.prayer_request,
            "form": form,
        },
    )


@login_required
@require_POST
def delete_prayer_comment(request, comment_id):
    comment = get_object_or_404(
        PrayerComment.objects.select_related("prayer_request", "user"),
        id=comment_id,
    )

    if comment.user != request.user and not request.user.is_staff:
        messages.error(request, message_text(request, "comment_delete_permission"))
        return redirect("prayer_list")

    comment.is_deleted = True
    comment.body = ""
    comment.save(update_fields=["is_deleted", "body"])

    messages.success(request, message_text(request, "comment_deleted"))
    return redirect("prayer_detail", prayer_id=comment.prayer_request.id)

@login_required
@require_POST
def mark_prayed(request, prayer_id):
    prayer = get_object_or_404(PrayerRequest, id=prayer_id)

    if not prayer.can_be_seen_by(request.user):
        messages.error(request, message_text(request, "pray_permission"))
        return redirect("prayer_list")

    mark, created = PrayerMark.objects.get_or_create(
        prayer_request=prayer,
        user=request.user,
    )

    if created:
        messages.success(request, message_text(request, "marked_prayed"))
    else:
        messages.info(request, message_text(request, "already_prayed"))

    safe_next_url = get_safe_next_url(request)
    if safe_next_url:
        return redirect(safe_next_url)

    return redirect("prayer_detail", prayer_id=prayer.id)


@login_required
@require_POST
def add_prayer_comment(request, prayer_id):
    prayer = get_object_or_404(PrayerRequest, id=prayer_id)

    if not prayer.can_be_seen_by(request.user):
        messages.error(request, message_text(request, "comment_permission"))
        return redirect("prayer_list")

    form = PrayerCommentForm(request.POST, language=get_user_language(request))

    if form.is_valid():
        comment = form.save(commit=False)
        comment.prayer_request = prayer
        comment.user = request.user
        comment.save()

        messages.success(request, message_text(request, "comment_posted"))
    else:
        messages.error(request, message_text(request, "comment_form_error"))

    safe_next_url = get_safe_next_url(request)
    if safe_next_url:
        return redirect(safe_next_url)

    return redirect("prayer_detail", prayer_id=prayer.id)


@login_required
@require_POST
def update_prayer_status(request, prayer_id):
    prayer = get_object_or_404(PrayerRequest, id=prayer_id)

    if not prayer.can_be_managed_by(request.user):
        messages.error(request, message_text(request, "status_permission"))
        return redirect("prayer_list")

    form = PrayerStatusForm(
        request.POST,
        instance=prayer,
        language=get_user_language(request),
    )

    if form.is_valid():
        form.save()
        messages.success(request, message_text(request, "prayer_updated"))
    else:
        messages.error(request, message_text(request, "status_form_error"))

    return redirect("prayer_detail", prayer_id=prayer.id)


@login_required
@require_POST
def delete_prayer_request(request, prayer_id):
    prayer = get_object_or_404(PrayerRequest, id=prayer_id)

    if not prayer.can_be_managed_by(request.user):
        messages.error(request, message_text(request, "delete_permission"))
        return redirect("prayer_list")

    prayer.is_deleted = True
    prayer.save(update_fields=["is_deleted"])

    messages.success(request, message_text(request, "prayer_deleted"))
    return redirect("prayer_list")
