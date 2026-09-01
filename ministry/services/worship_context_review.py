"""Canonical fingerprint, tri-state review, protected POST state, and barrier."""

import hashlib
import hmac
import json
import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum

from django.core import signing
from django.db.models import F
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from events.models import ServiceEvent

from ..models import TeamAssignment
from .worship_context import CanonicalWorshipContext, build_canonical_worship_contexts
from .worship_governance import is_canonical_worship_rotation_team


WORSHIP_CONTEXT_FINGERPRINT_VERSION = "worship_context_v1"
UNLINKED_DISPLAY_DIGEST_DOMAIN = "worship_unlinked_display_identity_v1"
REVIEW_STATE_TYPE = "worship_context_review_state"
REVIEW_STATE_VERSION = 1
REVIEW_STATE_SIGNING_SALT = "ministry.worship_context_review_state.v1"
REVIEW_STATE_MAX_AGE_SECONDS = 1800
FINGERPRINT_RE = re.compile(r"^[0-9a-f]{64}$")
CURRENT_STATUSES = (
    TeamAssignment.STATUS_SCHEDULED,
    TeamAssignment.STATUS_CONFIRMED,
    TeamAssignment.STATUS_PREPARED,
)


class WorshipContextReviewState(StrEnum):
    UNKNOWN = "unknown"
    CURRENT = "current"
    REVIEW_RECOMMENDED = "review_recommended"


@dataclass(frozen=True)
class WorshipContextSignature:
    semantic: CanonicalWorshipContext
    fingerprint: str | None

    @property
    def available(self):
        return self.fingerprint is not None


@dataclass(frozen=True)
class RenderedWorshipReviewState:
    user_id: int
    event_id: int
    team_id: int
    assignment_id: int | None
    expected_fingerprint: str
    prior_reviewed_fingerprint: str | None
    assignment_updated_at: object | None
    assignment_state: str


class WorshipReviewStateError(ValueError):
    """Protected state is malformed, stale, expired, or mismatched."""


def _canonical_json(value):
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def digest_unlinked_display_identity(display_name):
    """Return the FU1 digest, or None for blank/malformed identity."""

    if not isinstance(display_name, str):
        return None
    normalized = unicodedata.normalize("NFC", display_name).strip()
    if not normalized:
        return None
    payload = {
        "domain": UNLINKED_DISPLAY_DIGEST_DOMAIN,
        "display_identity_utf8_length": len(normalized.encode("utf-8")),
        "display_identity": normalized,
    }
    return hashlib.sha256(_canonical_json(payload)).hexdigest()


def fingerprint_canonical_worship_context(semantic):
    """Hash only the frozen V1 canonical semantic fields."""

    if not semantic.roster_signature_available:
        return None
    payload = {
        "contract_version": WORSHIP_CONTEXT_FINGERPRINT_VERSION,
        "selected_team_id": semantic.selected_team_id,
        "semantic_state": semantic.state.value,
    }
    if semantic.assignment_id is not None:
        roster = []
        for identity in sorted(
            semantic.roster_identities,
            key=lambda item: (
                item.membership_id,
                -1 if item.user_id is None else item.user_id,
                item.display_identity_digest or "",
            ),
        ):
            item = {
                "membership_id": identity.membership_id,
                "user_id": identity.user_id,
            }
            if identity.user_id is None:
                item["display_identity_digest"] = identity.display_identity_digest
            roster.append(item)
        payload.update(
            {
                "consistent_assignment_id": semantic.assignment_id,
                "consistent_assigned_team_id": semantic.assigned_team_id,
                "active_roster_identities": roster,
            }
        )
    return hashlib.sha256(_canonical_json(payload)).hexdigest()


def signature_from_canonical_context(semantic):
    return WorshipContextSignature(
        semantic=semantic,
        fingerprint=fingerprint_canonical_worship_context(semantic),
    )


def current_worship_context_signature(event):
    semantic = build_canonical_worship_contexts([event])[event.pk]
    return signature_from_canonical_context(semantic)


def reload_current_worship_context_signature(event_id):
    event = ServiceEvent.objects.select_related("rotation_anchor_team").get(pk=event_id)
    return current_worship_context_signature(event)


def is_downstream_worship_review_assignment(assignment):
    if (
        assignment is None
        or assignment.status not in CURRENT_STATUSES
        or assignment.service_event.event_type != ServiceEvent.EVENT_SUNDAY_SERVICE
        or assignment.ministry_team_id
        == assignment.service_event.rotation_anchor_team_id
    ):
        return False
    return not is_canonical_worship_rotation_team(assignment.ministry_team)


def is_downstream_worship_review_target(event, team, *, proposed_status):
    if (
        event is None
        or team is None
        or event.event_type != ServiceEvent.EVENT_SUNDAY_SERVICE
        or proposed_status not in CURRENT_STATUSES
        or team.pk == event.rotation_anchor_team_id
    ):
        return False
    return not is_canonical_worship_rotation_team(team)


def classify_downstream_worship_review(assignment, signature):
    if not is_downstream_worship_review_assignment(assignment):
        return None
    if not signature.available:
        return WorshipContextReviewState.UNKNOWN
    reviewed = assignment.reviewed_worship_context_fingerprint
    if reviewed is None:
        return WorshipContextReviewState.UNKNOWN
    if hmac.compare_digest(reviewed, signature.fingerprint):
        return WorshipContextReviewState.CURRENT
    return WorshipContextReviewState.REVIEW_RECOMMENDED


def _valid_fingerprint(value, *, nullable):
    return (
        value is None and nullable
    ) or isinstance(value, str) and FINGERPRINT_RE.fullmatch(value) is not None


def mint_rendered_worship_review_state(*, user, event, team, assignment, signature):
    if not signature.available:
        raise WorshipReviewStateError("Canonical Worship signature is unavailable.")
    if assignment is None:
        assignment_state = "create"
        assignment_id = None
        prior = None
        updated_at = None
    else:
        assignment_state = "existing"
        assignment_id = assignment.pk
        prior = assignment.reviewed_worship_context_fingerprint
        updated_at = assignment.updated_at.isoformat(timespec="microseconds")
    payload = {
        "type": REVIEW_STATE_TYPE,
        "version": REVIEW_STATE_VERSION,
        "user_id": user.pk,
        "event_id": event.pk,
        "team_id": team.pk,
        "assignment_state": assignment_state,
        "assignment_id": assignment_id,
        "expected_fingerprint": signature.fingerprint,
        "prior_reviewed_fingerprint": prior,
        "assignment_updated_at": updated_at,
    }
    return signing.dumps(payload, compress=True, salt=REVIEW_STATE_SIGNING_SALT)


def decode_rendered_worship_review_state(
    token,
    *,
    user,
    event_id,
    team_id,
    assignment_id,
    max_age=REVIEW_STATE_MAX_AGE_SECONDS,
):
    try:
        payload = signing.loads(
            token, salt=REVIEW_STATE_SIGNING_SALT, max_age=max_age
        )
    except signing.BadSignature as exc:
        raise WorshipReviewStateError("Invalid protected review state.") from exc
    expected_keys = {
        "type", "version", "user_id", "event_id", "team_id",
        "assignment_state", "assignment_id", "expected_fingerprint",
        "prior_reviewed_fingerprint", "assignment_updated_at",
    }
    if not isinstance(payload, dict) or set(payload) != expected_keys:
        raise WorshipReviewStateError("Malformed protected review state.")
    if (
        payload["type"] != REVIEW_STATE_TYPE
        or payload["version"] != REVIEW_STATE_VERSION
        or payload["user_id"] != user.pk
        or payload["event_id"] != event_id
        or payload["team_id"] != team_id
        or payload["assignment_id"] != assignment_id
    ):
        raise WorshipReviewStateError("Protected review state does not match.")
    if not _valid_fingerprint(payload["expected_fingerprint"], nullable=False):
        raise WorshipReviewStateError("Malformed expected fingerprint.")
    if not _valid_fingerprint(payload["prior_reviewed_fingerprint"], nullable=True):
        raise WorshipReviewStateError("Malformed prior fingerprint.")

    if assignment_id is None:
        if (
            payload["assignment_state"] != "create"
            or payload["assignment_updated_at"] is not None
            or payload["prior_reviewed_fingerprint"] is not None
        ):
            raise WorshipReviewStateError("Malformed create-state baseline.")
        updated_at = None
    else:
        if (
            payload["assignment_state"] != "existing"
            or not isinstance(payload["assignment_updated_at"], str)
        ):
            raise WorshipReviewStateError("Malformed assignment baseline.")
        updated_at = parse_datetime(payload["assignment_updated_at"])
        if updated_at is None or timezone.is_naive(updated_at):
            raise WorshipReviewStateError("Malformed assignment baseline.")

    return RenderedWorshipReviewState(
        user_id=payload["user_id"],
        event_id=payload["event_id"],
        team_id=payload["team_id"],
        assignment_id=payload["assignment_id"],
        expected_fingerprint=payload["expected_fingerprint"],
        prior_reviewed_fingerprint=payload["prior_reviewed_fingerprint"],
        assignment_updated_at=updated_at,
        assignment_state=payload["assignment_state"],
    )


def establish_worship_review_writer_barrier(state, *, using="default"):
    """Acquire SQLite's first-write boundary and enforce the signed baseline."""

    if state.assignment_id is None:
        updated = ServiceEvent.objects.using(using).filter(pk=state.event_id).update(
            updated_at=F("updated_at")
        )
        if updated != 1:
            raise WorshipReviewStateError("Event is no longer available.")
        if TeamAssignment.objects.using(using).filter(
            service_event_id=state.event_id,
            ministry_team_id=state.team_id,
            status__in=CURRENT_STATUSES,
        ).exists():
            raise WorshipReviewStateError("Assignment create-state is stale.")
        return

    queryset = TeamAssignment.objects.using(using).filter(
        pk=state.assignment_id,
        service_event_id=state.event_id,
        ministry_team_id=state.team_id,
        updated_at=state.assignment_updated_at,
    )
    if state.prior_reviewed_fingerprint is None:
        queryset = queryset.filter(reviewed_worship_context_fingerprint__isnull=True)
    else:
        queryset = queryset.filter(
            reviewed_worship_context_fingerprint=state.prior_reviewed_fingerprint
        )
    updated = queryset.update(
        reviewed_worship_context_fingerprint=F(
            "reviewed_worship_context_fingerprint"
        )
    )
    if updated != 1:
        raise WorshipReviewStateError("Assignment review baseline is stale.")


def require_rendered_context_is_current(state):
    signature = reload_current_worship_context_signature(state.event_id)
    if (
        not signature.available
        or not hmac.compare_digest(signature.fingerprint, state.expected_fingerprint)
    ):
        raise WorshipReviewStateError("Rendered Worship context is stale.")
    return signature
