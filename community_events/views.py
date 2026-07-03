from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Exists, OuterRef
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.language import get_user_language
from accounts.structure_selectors import get_user_primary_membership_unit

from .forms import CommunityActivitySubmissionForm
from .models import (
    ActivitySignup,
    CommunityActivity,
    CommunityActivityAudienceScope,
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
            )
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
        )
        if form.is_valid():
            audience_units = list(form.cleaned_data["audience_units"])
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
            return redirect(
                "community_activity_detail",
                activity_id=activity.id,
            )
    else:
        form = CommunityActivitySubmissionForm(language=language)

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
    is_creator = activity.created_by_id == request.user.id
    return render(
        request,
        "community_events/community_activity_detail.html",
        {
            "activity": activity,
            "can_manage": activity.can_be_managed_by(request.user),
            "is_creator": is_creator,
            "can_edit": activity.can_be_edited_by(request.user),
            "can_signup": activity.is_signup_open(),
            "is_signed_up": bool(signup and signup.is_active),
        },
    )


@login_required
def community_activity_edit(request, activity_id):
    """Let a creator edit their own activity while it awaits publication.

    Only the creator may edit, and only while the activity is in
    ``pending_review`` or ``changes_requested``. A valid save updates the
    activity fields, replaces the audience rows with the newly selected valid
    scope units, and leaves or moves the activity to ``pending_review`` in a
    single transaction. Any prior staff ``review_note`` is preserved for
    context; the creator cannot publish.
    """
    activity = get_object_or_404(CommunityActivity, id=activity_id)
    if not activity.can_be_edited_by(request.user):
        raise Http404("Community activity is not editable.")

    language = get_user_language(request)
    if request.method == "POST":
        form = CommunityActivitySubmissionForm(
            request.POST,
            instance=activity,
            language=language,
        )
        if form.is_valid():
            audience_units = list(form.cleaned_data["audience_units"])
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
            return redirect(
                "community_activity_detail",
                activity_id=activity.id,
            )
    else:
        form = CommunityActivitySubmissionForm(
            instance=activity,
            language=language,
            initial={
                "audience_units": list(
                    activity.audience_scope_links.values_list(
                        "structure_unit_id",
                        flat=True,
                    )
                ),
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
        },
    )


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
    if not activity.is_signup_open():
        raise Http404("Community activity signup not available.")

    ActivitySignup.objects.update_or_create(
        activity=activity,
        user=request.user,
        defaults={"status": ActivitySignup.STATUS_SIGNED_UP},
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
