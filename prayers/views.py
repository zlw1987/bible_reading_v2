from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .forms import (
    PrayerCommentEditForm,
    PrayerCommentForm,
    PrayerRequestEditForm,
    PrayerRequestForm,
    PrayerStatusForm,
)
from .models import PrayerComment, PrayerMark, PrayerRequest


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
        form = PrayerRequestForm(request.POST, user=request.user)

        if form.is_valid():
            prayer = form.save(commit=False)
            prayer.user = request.user

            if prayer.visibility == PrayerRequest.VISIBILITY_GROUP:
                prayer.small_group_at_post = get_user_small_group(request.user)

            prayer.save()

            messages.success(request, "Prayer request posted.")
            return redirect("prayer_detail", prayer_id=prayer.id)
    else:
        form = PrayerRequestForm(user=request.user)

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
        messages.error(request, "You do not have permission to view this prayer request.")
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
            "comment_form": PrayerCommentForm(),
            "status_form": PrayerStatusForm(instance=prayer),
            "has_prayed": has_prayed,
        },
    )

@login_required
def edit_prayer_request(request, prayer_id):
    prayer = get_object_or_404(PrayerRequest, id=prayer_id)

    if not prayer.can_be_managed_by(request.user):
        messages.error(request, "You do not have permission to edit this prayer request.")
        return redirect("prayer_list")

    if prayer.is_deleted:
        messages.error(request, "Deleted prayer requests cannot be edited.")
        return redirect("prayer_list")

    if request.method == "POST":
        form = PrayerRequestEditForm(
            request.POST,
            instance=prayer,
            user=request.user,
        )

        if form.is_valid():
            edited_prayer = form.save(commit=False)

            if edited_prayer.visibility == PrayerRequest.VISIBILITY_GROUP:
                edited_prayer.small_group_at_post = get_user_small_group(request.user)
            elif edited_prayer.visibility == PrayerRequest.VISIBILITY_PRIVATE:
                edited_prayer.small_group_at_post = None

            edited_prayer.save()

            messages.success(request, "Prayer request updated.")
            return redirect("prayer_detail", prayer_id=prayer.id)
    else:
        form = PrayerRequestEditForm(
            instance=prayer,
            user=request.user,
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
        messages.error(request, "You do not have permission to edit this comment.")
        return redirect("prayer_list")

    if comment.is_deleted:
        messages.error(request, "Deleted comments cannot be edited.")
        return redirect("prayer_detail", prayer_id=comment.prayer_request.id)

    if not comment.prayer_request.can_be_seen_by(request.user):
        messages.error(request, "You do not have permission to view this prayer request.")
        return redirect("prayer_list")

    if request.method == "POST":
        form = PrayerCommentEditForm(request.POST, instance=comment)

        if form.is_valid():
            form.save()
            messages.success(request, "Comment updated.")
            return redirect("prayer_detail", prayer_id=comment.prayer_request.id)
    else:
        form = PrayerCommentEditForm(instance=comment)

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
        messages.error(request, "You do not have permission to delete this comment.")
        return redirect("prayer_list")

    comment.is_deleted = True
    comment.body = ""
    comment.save(update_fields=["is_deleted", "body"])

    messages.success(request, "Comment deleted.")
    return redirect("prayer_detail", prayer_id=comment.prayer_request.id)

@login_required
@require_POST
def mark_prayed(request, prayer_id):
    prayer = get_object_or_404(PrayerRequest, id=prayer_id)

    if not prayer.can_be_seen_by(request.user):
        messages.error(request, "You do not have permission to pray for this request.")
        return redirect("prayer_list")

    mark, created = PrayerMark.objects.get_or_create(
        prayer_request=prayer,
        user=request.user,
    )

    if created:
        messages.success(request, "Marked as prayed.")
    else:
        messages.info(request, "You have already marked this prayer request.")

    safe_next_url = get_safe_next_url(request)
    if safe_next_url:
        return redirect(safe_next_url)

    return redirect("prayer_detail", prayer_id=prayer.id)


@login_required
@require_POST
def add_prayer_comment(request, prayer_id):
    prayer = get_object_or_404(PrayerRequest, id=prayer_id)

    if not prayer.can_be_seen_by(request.user):
        messages.error(request, "You do not have permission to comment on this prayer request.")
        return redirect("prayer_list")

    form = PrayerCommentForm(request.POST)

    if form.is_valid():
        comment = form.save(commit=False)
        comment.prayer_request = prayer
        comment.user = request.user
        comment.save()

        messages.success(request, "Comment posted.")
    else:
        messages.error(request, "Please correct the comment form.")

    safe_next_url = get_safe_next_url(request)
    if safe_next_url:
        return redirect(safe_next_url)

    return redirect("prayer_detail", prayer_id=prayer.id)


@login_required
@require_POST
def update_prayer_status(request, prayer_id):
    prayer = get_object_or_404(PrayerRequest, id=prayer_id)

    if not prayer.can_be_managed_by(request.user):
        messages.error(request, "You do not have permission to update this prayer request.")
        return redirect("prayer_list")

    form = PrayerStatusForm(request.POST, instance=prayer)

    if form.is_valid():
        form.save()
        messages.success(request, "Prayer request updated.")
    else:
        messages.error(request, "Please correct the status form.")

    return redirect("prayer_detail", prayer_id=prayer.id)


@login_required
@require_POST
def delete_prayer_request(request, prayer_id):
    prayer = get_object_or_404(PrayerRequest, id=prayer_id)

    if not prayer.can_be_managed_by(request.user):
        messages.error(request, "You do not have permission to delete this prayer request.")
        return redirect("prayer_list")

    prayer.is_deleted = True
    prayer.save(update_fields=["is_deleted"])

    messages.success(request, "Prayer request deleted.")
    return redirect("prayer_list")