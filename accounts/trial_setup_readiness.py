"""Read-only pre-user-trial setup readiness audit (SETUP-READINESS.1A).

This module aggregates a single read-only setup/data readiness snapshot across
the core modules, intended to be run *before* inviting real users / co-workers
to a trial. It answers one practical question: "if I invite people now, will the
core surfaces (visibility, serving, Bible Study) actually work, or are there
setup gaps that would break the trial or quietly hide content?"

It is strictly **read-only**:

- It creates, updates, or deletes nothing.
- It has no ``--apply`` mode and performs no repair / backfill / auto-fix.
- It changes no permission, membership, serving, audience, or visibility data.
- It does not infer serving from visibility or membership. Belonging
  (``ChurchStructureMembership``) and serving (``TeamAssignmentMember`` /
  ``BibleStudyMeetingRole``) stay separate concepts here, exactly as in runtime.

It is **not** a production-deployment claim. A clean run means the local/target
data has no high-confidence trial blockers at audit time; it does not certify
deployment, security, scale, or correctness.

Severity model (mirrors the existing readiness audits in this repo):

- **blocker** — a high-confidence issue that would break a core trial flow, e.g.
  a published, upcoming, member-visible event/meeting with zero audience rows
  (ordinary users fail closed and see nothing), an active serving assignment on
  a non-assignable ministry unit, or ambiguous multiple active primary
  memberships. ``--fail-on-blockers`` exits non-zero only when blockers > 0.
- **warning** — a setup gap that may be acceptable for a trial but is worth
  fixing, e.g. an assignable team with no role profile / no required lead, a
  serving slot filled by a display-name-only person who cannot personalize
  My Serving, or upcoming required-team coverage gaps. Warnings never fail.
- **info** — neutral counts for context (active users, upcoming events, etc.).

Module-owned checks (MODULAR-CORE.5A): the section bodies are contributed by
readiness providers registered through ``core.setup_readiness``. Church
Structure and permission/admin readiness stay Core providers here (always run),
the ministry-structure / serving sections are owned by
``ministry.setup_readiness_provider``, and the Bible Study meeting-serving
section is owned by ``studies.setup_readiness_provider``. This module is the
single explicit registration site — it imports those provider modules and
registers the Core providers below in a fixed order, so the section order and
existing operator output are preserved. Module providers run only when their
module is enabled; Core providers always run. The ministry-structure portion
still delegates to ``ministry.structure_readiness.run_audit`` (inside the
ministry provider) so this audit does not re-derive (or contradict) the
existing ministry readiness classification.
"""

from collections import defaultdict

from django.contrib.auth import get_user_model
from django.db.models import Q
from django.utils import timezone

import ministry.setup_readiness_provider
import studies.setup_readiness_provider
from accounts.models import (
    ChurchRoleAssignment,
    ChurchStructureMembership,
    ChurchStructureUnit,
)
from core.setup_readiness import (
    ReadinessContext,
    ReadinessSection,
    build_readiness_sections,
    register_readiness_provider,
)
from events.models import ServiceEvent
from studies.models import BibleStudyMeeting
from studies.visibility import meeting_is_member_visible


# Human-readable labels for every counter the report prints. Keyed by the
# internal counter key so the command can render a stable, readable line.
COUNTER_LABELS = {
    # 1. Church Structure / membership
    "active_users": "active user accounts",
    "staff_or_superuser_users": "active staff / superuser accounts",
    "active_structure_units": "active church structure units",
    "active_primary_memberships": "active primary memberships (current)",
    "users_multiple_active_primary_membership": (
        "users with MULTIPLE active primary memberships (ambiguous belonging)"
    ),
    "active_users_without_active_primary_membership": (
        "active non-staff users with no active primary membership "
        "(will not see scoped content)"
    ),
    # 2. Ministry Teams / Ministry Structure
    "active_teams": "active ministry teams",
    "assignable_teams": "assignable ministry teams",
    "container_teams": "non-assignable (container) ministry teams",
    "teams_multiple_active_primary_links": (
        "teams with multiple active primary parent links"
    ),
    "parent_link_cycle_teams": "teams in an active parent-link cycle",
    "teams_no_active_parent_link": (
        "active teams unanchored in Ministry Structure (no active parent link)"
    ),
    "assignable_teams_no_role_profile": (
        "assignable teams with no role profile"
    ),
    "teams_missing_required_lead": "teams missing a required active Lead",
    "assignable_teams_no_active_membership": (
        "assignable teams with no active members"
    ),
    # 3. TeamAssignment / My Serving
    "active_assignments_on_non_assignable_team": (
        "active serving assignments on a non-assignable unit"
    ),
    "upcoming_team_assignments": "upcoming (non-cancelled) team assignments",
    "team_assignment_members_display_name_only": (
        "upcoming serving members who are display-name-only "
        "(cannot personalize My Serving)"
    ),
    "upcoming_required_team_gaps": (
        "upcoming required-team coverage gaps (no assignment / no members)"
    ),
    # 4. Bible Study meeting-serving
    "upcoming_bible_study_meetings": "upcoming published Bible Study meetings",
    "bible_study_meeting_roles_display_name_only": (
        "upcoming Bible Study meeting roles that are display-name-only "
        "(cannot personalize My Serving)"
    ),
    # 5. Audience visibility
    "upcoming_published_events": "upcoming published service events",
    "upcoming_published_events_zero_audience": (
        "upcoming published events with ZERO audience rows "
        "(invisible to ordinary users)"
    ),
    "upcoming_visible_meetings": (
        "upcoming published, member-visible Bible Study meetings"
    ),
    "upcoming_visible_meetings_zero_audience": (
        "upcoming member-visible meetings with ZERO audience rows "
        "(invisible to ordinary users)"
    ),
    # 6. Permission / admin signals
    "active_staff_users": "active staff users",
    "active_superusers": "active superusers",
    "church_role_assignments": "church role assignments (scoped/global)",
    "no_active_staff_or_superuser": (
        "no active staff or superuser account exists "
        "(no one can manage the trial)"
    ),
}

PERMISSION_NOTES = (
    "Belonging (ChurchStructureMembership) is read here only as belonging; it is "
    "never treated as serving, role grant, or staff capability.",
    "Serving (TeamAssignmentMember / BibleStudyMeetingRole) is read only as "
    "serving; it is not inferred from membership or visibility.",
    "This audit grants no permission and changes no permission.",
)


def _unit_label(unit):
    if unit is None:
        return "(none)"
    return f"#{unit.id} {unit.code}"


def _active_primary_membership_counts_by_user(target_date):
    counts = defaultdict(int)
    rows = (
        ChurchStructureMembership.objects.filter(
            status=ChurchStructureMembership.STATUS_ACTIVE,
            is_primary=True,
            start_date__lte=target_date,
        )
        .filter(Q(end_date__isnull=True) | Q(end_date__gte=target_date))
        .values_list("user_id", flat=True)
    )
    for user_id in rows:
        counts[user_id] += 1
    return counts


def _build_church_structure_section(target_date):
    section = ReadinessSection(
        "church_structure", "1. Church Structure / membership readiness"
    )
    User = get_user_model()

    active_users = User.objects.filter(is_active=True)
    active_user_ids = set(active_users.values_list("id", flat=True))
    staff_ids = set(
        active_users.filter(Q(is_staff=True) | Q(is_superuser=True)).values_list(
            "id", flat=True
        )
    )

    section.add_info("active_users", len(active_user_ids))
    section.add_info("staff_or_superuser_users", len(staff_ids))
    section.add_info(
        "active_structure_units",
        ChurchStructureUnit.objects.filter(is_active=True).count(),
    )

    membership_counts = _active_primary_membership_counts_by_user(target_date)
    section.add_info(
        "active_primary_memberships",
        sum(membership_counts.values()),
    )

    multiple = 0
    no_membership = 0
    for user_id in active_user_ids:
        count = membership_counts.get(user_id, 0)
        if count > 1:
            multiple += 1
            section.detail(
                "users_multiple_active_primary_membership",
                f"user_id={user_id} active_primary_memberships={count}",
            )
        elif count == 0 and user_id not in staff_ids:
            no_membership += 1
            section.detail(
                "active_users_without_active_primary_membership",
                f"user_id={user_id}",
            )

    section.blocker("users_multiple_active_primary_membership", multiple)
    section.warning("active_users_without_active_primary_membership", no_membership)
    return section


def _build_audience_visibility_section(now):
    section = ReadinessSection(
        "audience_visibility",
        "5. ServiceEvent / Bible Study audience visibility readiness",
    )

    events = (
        ServiceEvent.objects.filter(
            status=ServiceEvent.STATUS_PUBLISHED,
            start_datetime__gte=now,
        )
        .prefetch_related("audience_scope_links")
        .order_by("start_datetime", "id")
    )
    event_total = 0
    event_zero_audience = 0
    for event in events:
        event_total += 1
        if not event.audience_scope_links.all():
            event_zero_audience += 1
            section.detail(
                "upcoming_published_events_zero_audience",
                f"event_id={event.id} title={event.get_title('en')!r} "
                f"start={event.start_datetime.isoformat()}",
            )
    section.add_info("upcoming_published_events", event_total)
    section.blocker(
        "upcoming_published_events_zero_audience", event_zero_audience
    )

    meetings = (
        BibleStudyMeeting.objects.filter(
            status=BibleStudyMeeting.STATUS_PUBLISHED,
            meeting_datetime__gte=now,
        )
        .select_related("lesson", "lesson__series")
        .prefetch_related("audience_scope_links")
        .order_by("meeting_datetime", "id")
    )
    meeting_visible_total = 0
    meeting_zero_audience = 0
    for meeting in meetings:
        # Only meetings actually intended to be member-visible can "fail closed".
        if not meeting_is_member_visible(meeting):
            continue
        meeting_visible_total += 1
        if not meeting.audience_scope_links.all():
            meeting_zero_audience += 1
            section.detail(
                "upcoming_visible_meetings_zero_audience",
                f"meeting_id={meeting.id} lesson=#{meeting.lesson_id} "
                f"datetime={meeting.meeting_datetime.isoformat()}",
            )
    section.add_info("upcoming_visible_meetings", meeting_visible_total)
    section.blocker(
        "upcoming_visible_meetings_zero_audience", meeting_zero_audience
    )
    return section


def _build_permission_admin_section():
    section = ReadinessSection(
        "permission_admin", "6. Permission / admin setup signals"
    )
    User = get_user_model()

    active_staff = User.objects.filter(is_active=True, is_staff=True).count()
    active_super = User.objects.filter(is_active=True, is_superuser=True).count()
    section.add_info("active_staff_users", active_staff)
    section.add_info("active_superusers", active_super)
    section.add_info(
        "church_role_assignments", ChurchRoleAssignment.objects.count()
    )

    has_admin = (
        User.objects.filter(is_active=True)
        .filter(Q(is_staff=True) | Q(is_superuser=True))
        .exists()
    )
    section.warning("no_active_staff_or_superuser", 0 if has_admin else 1)
    return section


def _recommendation(blocker_count, warning_count):
    if blocker_count > 0:
        return (
            "NOT READY — resolve the blockers above before inviting real users. "
            "Each blocker would break a core trial flow (visibility or serving)."
        )
    if warning_count > 0:
        return (
            "USABLE FOR A LIMITED TRIAL — no blockers, but review the warnings; "
            "some setup gaps may degrade the experience for trial users."
        )
    return (
        "NO BLOCKERS OR WARNINGS DETECTED — setup looks ready for a limited "
        "trial. This is not a production-deployment claim."
    )


def _church_structure_provider(context):
    """Core provider: Church Structure / membership readiness (always runs)."""
    return [_build_church_structure_section(context.target_date)]


def _audience_visibility_provider(context):
    """Core provider: ServiceEvent / Bible Study audience visibility readiness.

    Kept centralized and always-run: it aggregates both events and studies
    audience rows into a single operator-facing section, and its zero-audience
    fail-closed checks are the most important trial blockers, so they run
    regardless of module enablement. See ``docs/MODULE_BOUNDARIES.md``.
    """
    return [_build_audience_visibility_section(context.now)]


def _permission_admin_provider(context):
    """Core provider: permission / admin setup signals (always runs)."""
    return [_build_permission_admin_section()]


# MODULAR-CORE.5A: this module is the single explicit registration site for the
# readiness providers (no app auto-discovery). Registration order fixes the
# operator-facing section order 1..6: Core church-structure, the ministry
# provider (sections 2 + 3), the studies provider (section 4), then the Core
# audience-visibility and permission/admin providers. Core providers always
# run; ministry / studies providers run only when their module is enabled.
register_readiness_provider("church_structure", _church_structure_provider)
ministry.setup_readiness_provider.register()
studies.setup_readiness_provider.register()
register_readiness_provider("audience_visibility", _audience_visibility_provider)
register_readiness_provider("permission_admin", _permission_admin_provider)


def run_audit(target_date=None, now=None):
    """Return the read-only pre-user-trial setup readiness snapshot.

    The returned dict carries the ordered list of report ``sections`` (each with
    severity-classified counters and capped verbose detail rows), aggregate
    ``blocker_count`` / ``warning_count``, static ``permission_notes``, and a
    plain-language ``recommendation``. It never writes a row.

    Sections come from the readiness provider registry
    (``core.setup_readiness.build_readiness_sections``): Core checks always run,
    while module-owned checks run only when their module is enabled. With the
    default all-modules-enabled configuration this yields the same six sections
    and counts as before.
    """
    now = now or timezone.now()
    target_date = target_date or timezone.localdate()

    context = ReadinessContext(now=now, target_date=target_date)
    sections = build_readiness_sections(context)

    blocker_count = sum(section.blocker_count for section in sections)
    warning_count = sum(section.warning_count for section in sections)

    return {
        "sections": sections,
        "blocker_count": blocker_count,
        "warning_count": warning_count,
        "permission_notes": list(PERMISSION_NOTES),
        "recommendation": _recommendation(blocker_count, warning_count),
        "target_date": target_date,
        "now": now,
    }
