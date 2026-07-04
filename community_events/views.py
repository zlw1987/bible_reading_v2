from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Count, Exists, OuterRef, Q
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from accounts.language import get_user_language
from accounts.structure_selectors import get_user_primary_membership_unit

from .forms import CommunityActivitySubmissionForm
from .models import (
    ActivitySignup,
    CommunityActivity,
    CommunityActivityAudienceScope,
    CommunityActivityCoOrganizer,
    CommunityActivitySubmissionBlock,
)
from .visibility import (
    user_has_community_activity_manager_override,
    visible_community_activities_for,
)


@login_required
def community_activity_list(request):
    """Independent member-facing browse and submission-status entrance.

    Lists upcoming activities the signed-in user may see through the
    structure-native visibility helper. Ordinary users see only published
    activities whose audience rows match their active primary membership unit
    or one of its ancestors; zero-row activities fail closed. Staff and
    superusers keep the helper's intentionally narrow management bypass, so
    they may also see draft/cancelled/completed rows here. The list may show
    the current user's signup state and own submissions that still need
    workflow attention, but contributes no Today or My Serving surface.
    """
    now = timezone.now()
    activities = (
        visible_community_activities_for(request.user)
        .filter(start_datetime__gte=now)
        .annotate(
            is_signed_up=Exists(
                ActivitySignup.objects.filter(
                    activity_id=OuterRef("pk"),
                    user=request.user,
                    status=ActivitySignup.STATUS_SIGNED_UP,
                )
            ),
            signup_count=Count(
                "signups",
                filter=Q(signups__status=ActivitySignup.STATUS_SIGNED_UP),
            ),
        )
        .order_by("start_datetime", "id")
    )
    submitted_activities = CommunityActivity.objects.filter(
        created_by=request.user,
        status__in=(
            CommunityActivity.STATUS_PENDING_REVIEW,
            CommunityActivity.STATUS_CHANGES_REQUESTED,
            CommunityActivity.STATUS_CANCELLED,
        ),
    ).order_by("-created_at", "-id")
    can_submit = (
        (membership_unit := get_user_primary_membership_unit(request.user))
        is not None
        and membership_unit.is_active
        and not CommunityActivitySubmissionBlock.objects.filter(
            user=request.user,
            is_active=True,
        ).exists()
    )
    return render(
        request,
        "community_events/community_activity_list.html",
        {
            "activities": activities,
            "submitted_activities": submitted_activities,
            "can_submit": can_submit,
            "can_manage": user_has_community_activity_manager_override(request.user),
        },
    )


@login_required
def community_activity_create(request):
    """Let an eligible member propose an activity for staff review."""
    membership_unit = get_user_primary_membership_unit(request.user)
    is_blocked = CommunityActivitySubmissionBlock.objects.filter(
        user=request.user,
        is_active=True,
    ).exists()
    if membership_unit is None or not membership_unit.is_active or is_blocked:
        raise PermissionDenied("Community activity submission is not available.")

    language = get_user_language(request)
    if request.method == "POST":
        form = CommunityActivitySubmissionForm(
            request.POST,
            language=language,
            acting_user=request.user,
        )
        if form.is_valid():
            audience_units = list(form.cleaned_data["audience_units"])
            co_organizers = list(form.cleaned_data["co_organizer_users"])
            with transaction.atomic():
                activity = form.save(commit=False)
                activity.status = CommunityActivity.STATUS_PENDING_REVIEW
                activity.created_by = request.user
                activity.save()
                for unit in audience_units:
                    CommunityActivityAudienceScope.objects.create(
                        activity=activity,
                        structure_unit=unit,
                    )
                for user in co_organizers:
                    CommunityActivityCoOrganizer.objects.create(
                        activity=activity,
                        user=user,
                        added_by=request.user,
                    )
            return redirect(
                "community_activity_detail",
                activity_id=activity.id,
            )
    else:
        form = CommunityActivitySubmissionForm(
            language=language,
            acting_user=request.user,
        )

    return render(
        request,
        "community_events/community_activity_form.html",
        {"form": form},
    )


@login_required
def community_activity_detail(request, activity_id):
    """Member detail page with the narrow creator-owned submission exception.

    Public ordinary access remains governed by the shared published audience
    helper. A creator may also see their own submitted activity and status.
    Other hidden activities deny with 404. No route-level module hard-off is
    applied.
    """
    activity = get_object_or_404(CommunityActivity, id=activity_id)
    if not activity.can_be_seen_by(request.user):
        raise Http404("Community activity not available.")
    signup = activity.signup_for(request.user)
    signup_count = activity.active_signup_count()
    is_full = activity.is_full(active_signup_count=signup_count)
    is_creator = activity.created_by_id == request.user.id
    is_co_organizer = activity.is_co_organizer(request.user)
    return render(
        request,
        "community_events/community_activity_detail.html",
        {
            "activity": activity,
            "can_manage": activity.can_be_managed_by(request.user),
            "is_creator": is_creator,
            "is_co_organizer": is_co_organizer,
            "is_submission_collaborator": is_creator or is_co_organizer,
            "can_edit": activity.can_be_edited_by(request.user),
            "can_signup": activity.is_signup_open(
                active_signup_count=signup_count,
            ),
            "signup_count": signup_count,
            "is_full": is_full,
            "is_signed_up": bool(signup and signup.is_active),
            "co_organizers": activity.co_organizer_links.select_related(
                "user"
            ).order_by("user__first_name", "user__last_name", "user__username"),
        },
    )


@login_required
def community_activity_edit(request, activity_id):
    """Let an approved collaborator edit while an activity awaits publication.

    The creator or a linked co-organizer may edit only while the activity is
    in ``pending_review`` or ``changes_requested``. A valid save updates the
    activity fields, replaces the audience rows with the newly selected valid
    scope units, and leaves or moves the activity to ``pending_review`` in a
    single transaction. Only the primary creator may replace co-organizer
    links. Any prior staff ``review_note`` is preserved for context; neither
    collaborator can publish.
    """
    activity = get_object_or_404(CommunityActivity, id=activity_id)
    if not activity.can_be_edited_by(request.user):
        raise Http404("Community activity is not editable.")

    language = get_user_language(request)
    can_manage_co_organizers = activity.created_by_id == request.user.id
    if request.method == "POST":
        form = CommunityActivitySubmissionForm(
            request.POST,
            instance=activity,
            language=language,
            acting_user=request.user,
            include_co_organizers=can_manage_co_organizers,
        )
        if form.is_valid():
            audience_units = list(form.cleaned_data["audience_units"])
            co_organizers = (
                list(form.cleaned_data["co_organizer_users"])
                if can_manage_co_organizers
                else None
            )
            with transaction.atomic():
                activity = form.save(commit=False)
                activity.status = CommunityActivity.STATUS_PENDING_REVIEW
                activity.save()
                activity.audience_scope_links.all().delete()
                for unit in audience_units:
                    CommunityActivityAudienceScope.objects.create(
                        activity=activity,
                        structure_unit=unit,
                    )
                if co_organizers is not None:
                    activity.co_organizer_links.all().delete()
                    for user in co_organizers:
                        CommunityActivityCoOrganizer.objects.create(
                            activity=activity,
                            user=user,
                            added_by=request.user,
                        )
            return redirect(
                "community_activity_detail",
                activity_id=activity.id,
            )
    else:
        form = CommunityActivitySubmissionForm(
            instance=activity,
            language=language,
            acting_user=request.user,
            include_co_organizers=can_manage_co_organizers,
            initial={
                "audience_units": list(
                    activity.audience_scope_links.values_list(
                        "structure_unit_id",
                        flat=True,
                    )
                ),
                "co_organizer_users": list(
                    activity.co_organizer_links.values_list(
                        "user_id",
                        flat=True,
                    )
                )
                if can_manage_co_organizers
                else [],
            },
        )

    return render(
        request,
        "community_events/community_activity_form.html",
        {
            "form": form,
            "is_edit": True,
            "is_changes_requested": (
                activity.status
                == CommunityActivity.STATUS_CHANGES_REQUESTED
            ),
            "activity": activity,
            "review_note": activity.review_note,
            "can_manage_co_organizers": can_manage_co_organizers,
        },
    )


def _can_search_activity_users(user, activity_id=None):
    membership_unit = get_user_primary_membership_unit(user)
    can_submit = (
        membership_unit is not None
        and membership_unit.is_active
        and not CommunityActivitySubmissionBlock.objects.filter(
            user=user,
            is_active=True,
        ).exists()
    )
    if can_submit:
        return True
    if not activity_id:
        return False
    activity = CommunityActivity.objects.filter(id=activity_id).first()
    return bool(
        activity
        and activity.created_by_id == user.id
        and activity.can_be_edited_by(user)
    )


@login_required
@require_GET
def community_activity_user_search(request):
    """Return minimal active-user data for the co-organizer picker."""
    activity_id = request.GET.get("activity_id")
    if not _can_search_activity_users(request.user, activity_id=activity_id):
        raise PermissionDenied("Community activity user search is not available.")

    query = (request.GET.get("q") or "").strip()
    if len(query) < 2:
        return JsonResponse({"results": []})

    users = (
        get_user_model()
        .objects.filter(is_active=True)
        .exclude(id=request.user.id)
        .filter(
            Q(username__icontains=query)
            | Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
        )
        .order_by("first_name", "last_name", "username", "id")[:20]
    )
    language = get_user_language(request)
    results = []
    for user in users:
        membership_unit = get_user_primary_membership_unit(user)
        results.append(
            {
                "id": user.id,
                "display_name": user.get_full_name().strip()
                or user.get_username(),
                "username": user.get_username(),
                "group_label": (
                    membership_unit.path_label(language)
                    if membership_unit is not None
                    else (
                        "暂无小组归属"
                        if language == "zh"
                        else "No active group"
                    )
                ),
            }
        )
    return JsonResponse({"results": results})


def _visible_activity_or_404(user, activity_id):
    activity = get_object_or_404(CommunityActivity, id=activity_id)
    if not activity.can_be_seen_by(user):
        raise Http404("Community activity not available.")
    return activity


@login_required
@require_POST
def community_activity_signup(request, activity_id):
    """Create or reactivate the current user's attendance intent."""
    activity = _visible_activity_or_404(request.user, activity_id)
    with transaction.atomic():
        activity = CommunityActivity.objects.select_for_update().get(
            pk=activity.pk,
        )
        if (
            activity.status != CommunityActivity.STATUS_PUBLISHED
            or activity.start_datetime <= timezone.now()
        ):
            raise Http404("Community activity signup not available.")

        signup = (
            ActivitySignup.objects.select_for_update()
            .filter(activity=activity, user=request.user)
            .first()
        )
        if signup and signup.is_active:
            return redirect(
                "community_activity_detail",
                activity_id=activity.id,
            )
        if activity.is_full():
            raise Http404("Community activity signup not available.")

        if signup:
            signup.status = ActivitySignup.STATUS_SIGNED_UP
            signup.save(update_fields=["status", "updated_at"])
        else:
            ActivitySignup.objects.create(
                activity=activity,
                user=request.user,
            )
    return redirect("community_activity_detail", activity_id=activity.id)


@login_required
@require_POST
def community_activity_cancel_signup(request, activity_id):
    """Cancel an existing signup without deleting its lifecycle row."""
    activity = _visible_activity_or_404(request.user, activity_id)
    ActivitySignup.objects.filter(
        activity=activity,
        user=request.user,
        status=ActivitySignup.STATUS_SIGNED_UP,
    ).update(
        status=ActivitySignup.STATUS_CANCELLED,
        updated_at=timezone.now(),
    )
    return redirect("community_activity_detail", activity_id=activity.id)


# --- Staff review inbox + request-changes loop (COMMUNITY-EVENTS.1D-B) -------

_REVIEW_STATUSES = (
    CommunityActivity.STATUS_PENDING_REVIEW,
    CommunityActivity.STATUS_CHANGES_REQUESTED,
)


def _activity_scope_labels(activity, language):
    return [
        unit.path_label(language)
        for unit in activity.get_audience_scope_units()
    ]


@staff_member_required
def community_activity_review_list(request):
    """Staff-only inbox of submissions awaiting a review decision.

    Lists pending-review and changes-requested activities newest first, with
    the creator, start time, status, selected scope labels, and any scope or
    review note, each linking to the staff review detail. This is a lightweight
    review queue, not a full event-management dashboard, and it contributes no
    Today, My Serving, Staff Overview, or serving surface.
    """
    language = get_user_language(request)
    activities = (
        CommunityActivity.objects.filter(status__in=_REVIEW_STATUSES)
        .select_related("created_by")
        .order_by("-created_at", "-id")
    )
    review_items = [
        {
            "activity": activity,
            "scope_labels": _activity_scope_labels(activity, language),
        }
        for activity in activities
    ]
    return render(
        request,
        "community_events/community_activity_review_list.html",
        {"review_items": review_items},
    )


@staff_member_required
def community_activity_review_detail(request, activity_id):
    """Staff-only review detail with publish / request-changes / cancel actions."""
    activity = get_object_or_404(CommunityActivity, id=activity_id)
    language = get_user_language(request)
    return render(
        request,
        "community_events/community_activity_review_detail.html",
        {
            "activity": activity,
            "scope_labels": _activity_scope_labels(activity, language),
            "review_note_error": request.GET.get("error") == "note",
            "can_take_review_action": activity.status in _REVIEW_STATUSES,
            "can_request_changes": (
                activity.status == CommunityActivity.STATUS_PENDING_REVIEW
            ),
        },
    )


def _record_review(activity, user, status):
    activity.status = status
    activity.reviewed_by = user
    activity.reviewed_at = timezone.now()


@staff_member_required
@require_POST
def community_activity_review_publish(request, activity_id):
    """Publish a pending-review or changes-requested activity."""
    activity = get_object_or_404(CommunityActivity, id=activity_id)
    if activity.status not in _REVIEW_STATUSES:
        raise Http404("Community activity is not awaiting review.")
    _record_review(activity, request.user, CommunityActivity.STATUS_PUBLISHED)
    activity.save()
    return redirect("community_activity_review_detail", activity_id=activity.id)


@staff_member_required
@require_POST
def community_activity_review_request_changes(request, activity_id):
    """Send a pending-review activity back to the creator with a required note."""
    activity = get_object_or_404(CommunityActivity, id=activity_id)
    if activity.status != CommunityActivity.STATUS_PENDING_REVIEW:
        raise Http404("Community activity is not awaiting review.")
    review_note = (request.POST.get("review_note") or "").strip()
    if not review_note:
        return redirect(
            reverse("community_activity_review_detail", args=[activity.id])
            + "?error=note"
        )
    activity.review_note = review_note
    _record_review(
        activity,
        request.user,
        CommunityActivity.STATUS_CHANGES_REQUESTED,
    )
    activity.save()
    return redirect("community_activity_review_detail", activity_id=activity.id)


@staff_member_required
@require_POST
def community_activity_review_cancel(request, activity_id):
    """Cancel/reject a pending-review or changes-requested activity."""
    activity = get_object_or_404(CommunityActivity, id=activity_id)
    if activity.status not in _REVIEW_STATUSES:
        raise Http404("Community activity is not awaiting review.")
    review_note = (request.POST.get("review_note") or "").strip()
    if review_note:
        activity.review_note = review_note
    _record_review(activity, request.user, CommunityActivity.STATUS_CANCELLED)
    activity.save()
    return redirect("community_activity_review_detail", activity_id=activity.id)
