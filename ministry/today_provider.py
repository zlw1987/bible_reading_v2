"""Ministry module's Today provider (MODULAR-CORE.3B).

Owns the Today action-center serving summary and the manager-only Leader
Needs Attention summary, plus the per-gathering serving-note lookup that the
events Today provider reuses. The provider bodies moved here from
``reading.views``; registration stays explicit — ``reading.views`` calls
:func:`register` at import time, before any ``home()`` request.

Today / My Serving boundary (unchanged): personal serving comes only from
explicit ``TeamAssignmentMember`` rows and linked-user
``BibleStudyMeetingRole.user`` roles. ``ChurchStructureMembership``
(belonging), audience visibility, and ``MinistryTeamRoleAssignment`` (team
management authority) never count as personal serving.
"""

from datetime import timedelta

from django.utils import timezone

from accounts.language import get_user_language
from core.module_registry import is_module_enabled
from core.today_providers import register_today_provider
from core.today_windows import THIS_WEEK_DAYS

from .models import TeamAssignment
from .views import (
    get_serving_item_sort_key,
    get_serving_item_starts_at,
    leader_needs_attention_rows,
    my_bible_study_role_serving_items,
    my_serving_assignments,
    serving_item_kind,
    serving_item_needs_attention,
)

NEEDS_ATTENTION_CAP = 5
# Window for surfacing a confirmed assignment as a lightweight upcoming reminder
# when nothing is pending confirmation.
NEAR_TERM_CONFIRMED_DAYS = 30

TODAY_DEFAULTS = {"serving_summary": None, "leader_summary": None}


def _user_serving_members(user):
    """Personal, non-cancelled upcoming team serving rows (My Serving semantics).

    Team-assignment serving only. Used for the compact per-gathering serving
    note; Bible Study serving is a separate agenda concept and is never folded
    into a Church Gathering row.
    """
    return [
        member
        for member in my_serving_assignments(user, tab="upcoming")
        if member.assignment.status not in {
            TeamAssignment.STATUS_CANCELLED,
            TeamAssignment.STATUS_COMPLETED,
        }
    ]


def _user_serving_items(user):
    """Personal upcoming serving items across team assignments and linked-user
    Bible Study meeting roles, in My Serving order.

    Team serving comes from ``TeamAssignmentMember`` rows (candidate-pool
    ``TeamMembership`` alone is not serving). Bible Study serving comes from
    ``BibleStudyMeetingRole.user == user`` on a visible meeting only:
    display-name-only roles, other users' roles, and audience visibility alone
    never count as personal serving. ``MinistryTeamRoleAssignment`` (team
    management) and ``ChurchStructureMembership`` (belonging) are not serving and
    are never included here.
    """
    team_items = _user_serving_members(user)
    bible_study_items = list(my_bible_study_role_serving_items(user, tab="upcoming"))
    return sorted(
        [*team_items, *bible_study_items],
        key=get_serving_item_sort_key,
    )


def _serving_summary_row(item):
    """Normalise a team or Bible Study serving item into a compact Today row.

    ``is_pending`` reuses My Serving's ``serving_item_needs_attention`` so the
    Today action center and My Serving agree on what counts as awaiting
    confirmation for each serving kind.
    """
    starts_at = get_serving_item_starts_at(item)
    is_pending = serving_item_needs_attention(item)
    if serving_item_kind(item) == "bible_study_role":
        return {
            "kind": "bible_study",
            "meeting": item.meeting,
            "roles": item.roles,
            "starts_at": starts_at,
            "is_pending": is_pending,
        }
    return {
        "kind": "team",
        "assignment": item.assignment,
        "starts_at": starts_at,
        "is_pending": is_pending,
    }


def get_today_serving_summary(user):
    """Count-aware Today serving reminder for the signed-in user (action center).

    Covers both team-assignment serving and linked-user Bible Study serving.
    Pending confirmations take priority: the summary reports the total pending
    count (``pending_count``) across both serving kinds and surfaces the
    near-term pending rows (this-week window) so a far-future pending item is
    counted but not shown as a full row. When nothing is pending, a confirmed
    upcoming serving item within ``NEAR_TERM_CONFIRMED_DAYS`` surfaces as a
    lightweight reminder instead.

    Reuses My Serving's personal serving selectors and needs-attention
    semantics. Returns ``None`` when there is nothing to show, hiding the
    section on Today.
    """
    if not is_module_enabled("ministry"):
        return None
    now = timezone.now()
    rows = [_serving_summary_row(item) for item in _user_serving_items(user)]

    pending_rows = [row for row in rows if row["is_pending"]]
    pending_count = len(pending_rows)
    if pending_count:
        week_cutoff = now + timedelta(days=THIS_WEEK_DAYS)
        near_term = [
            row
            for row in pending_rows[:NEEDS_ATTENTION_CAP]
            if row["starts_at"] <= week_cutoff
        ]
        return {
            "is_pending": True,
            "pending_count": pending_count,
            "items": near_term or pending_rows[:1],
        }

    confirmed_upcoming = next(
        (
            row
            for row in rows
            if not row["is_pending"]
            and row["starts_at"] <= now + timedelta(days=NEAR_TERM_CONFIRMED_DAYS)
        ),
        None,
    )
    if confirmed_upcoming:
        return {
            "is_pending": False,
            "pending_count": 0,
            "items": [confirmed_upcoming],
        }

    return None


def get_week_serving_notes(user):
    """Map service_event_id -> 'pending'/'confirmed' for the user's serving.

    Used to attach a compact serving note to a Church Gathering row instead of
    rendering a second full assignment row (Today deduplication rule). Called
    by the events Today provider even when ministry is disabled, so the
    module gate stays inside this helper and returns an empty mapping then.
    """
    if not is_module_enabled("ministry"):
        return {}
    notes = {}
    for member in _user_serving_members(user):
        event_id = member.assignment.service_event_id
        if event_id in notes:
            continue
        notes[event_id] = "confirmed" if member.confirmed_at else "pending"
    return notes


def get_today_leader_summary(user, *, language="en"):
    """Compact manager-only "Leader Needs Attention" summary for Today.

    Reuses My Serving's ``leader_needs_attention_rows``, which is manager-gated:
    it returns rows only for a global assignment manager (staff / capability) or a
    user with an active lead/coordinator ``MinistryTeamRoleAssignment`` on the
    exact required team. ``TeamMembership.role`` / ``can_lead`` grant no manager
    authority, so those users get no rows and no section. This is team-management
    responsibility, not personal serving, and is never surfaced as My Serving.

    Returns ``None`` (hiding the section) when there is nothing to act on, so an
    ordinary user — and a manager whose teams are already covered — sees no card.
    """
    if not is_module_enabled("ministry"):
        return None
    rows = leader_needs_attention_rows(user, language=language)
    if not rows:
        return None
    return {
        "count": len(rows),
        "items": rows[:NEEDS_ATTENTION_CAP],
    }


def ministry_today_provider(request):
    """Action-center serving summary and manager-only Leader Needs Attention.

    Personal serving stays explicit (TeamAssignmentMember / linked-user
    BibleStudyMeetingRole.user); belonging and audience visibility never count.
    """
    return {
        "serving_summary": get_today_serving_summary(request.user),
        "leader_summary": get_today_leader_summary(
            request.user,
            language=get_user_language(request),
        ),
    }


def register():
    """Register the ministry Today provider (called from ``reading.views``)."""
    register_today_provider(
        "ministry",
        ministry_today_provider,
        defaults=TODAY_DEFAULTS,
    )
