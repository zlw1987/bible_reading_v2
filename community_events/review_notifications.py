"""Directed notifications for Community Activity staff review outcomes.

This Community Activities-owned producer resolves only the primary creator and
emits through the Core notification port. It deliberately does not infer
recipients from co-organizers, audience scope, signups, Church Structure
belonging, submission eligibility, or staff authority.
"""

from django.urls import reverse

from core.notification_delivery import emit_notification

from .models import CommunityActivity


_OUTCOMES = {
    CommunityActivity.STATUS_CHANGES_REQUESTED: (
        "changes_requested",
        "Changes requested for your activity",
        "你的活动需要修改",
    ),
    CommunityActivity.STATUS_PUBLISHED: (
        "published",
        "Your activity was published",
        "你的活动已发布",
    ),
    CommunityActivity.STATUS_CANCELLED: (
        "cancelled",
        "Your activity was not approved",
        "活动审核未通过",
    ),
}


def _recipient_language(user):
    """Use the creator's persisted preference, with an English fallback."""

    profile = getattr(user, "profile", None)
    return "zh" if getattr(profile, "preferred_language", None) == "zh" else "en"


def _review_mutation_token(activity):
    """Identify one applied staff review mutation without Notification lookup."""

    return activity.reviewed_at.isoformat(timespec="microseconds")


def emit_review_outcome_notification(activity, *, actor=None):
    """Emit at most one primary-creator payload for one applied staff review.

    The caller owns the review lifecycle and must invoke this only after a
    successful source save. Missing/inactive creators and rows without a
    supported saved review outcome safely produce no payload.
    """

    outcome = _OUTCOMES.get(activity.status)
    recipient = activity.created_by
    if (
        not activity.pk
        or outcome is None
        or activity.reviewed_at is None
        or recipient is None
        or not recipient.is_active
    ):
        return 0

    outcome_key, title_en, title_zh = outcome
    language = _recipient_language(recipient)
    scheduled = emit_notification(
        recipient=recipient,
        source_module="community_events",
        notification_type=f"community_activity.review_{outcome_key}",
        title=title_zh if language == "zh" else title_en,
        body=activity.get_title(language),
        target_url=reverse("community_activity_detail", args=[activity.id]),
        dedupe_key=(
            f"community:activity:{activity.id}:review:{outcome_key}:"
            f"{_review_mutation_token(activity)}"
        ),
        source_model_label="community_events.CommunityActivity",
        source_object_id=str(activity.id),
        actor=actor,
        metadata={},
    )
    return int(scheduled)
