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

The ministry-structure portion delegates to
``ministry.structure_readiness.run_audit`` so this audit does not re-derive (or
contradict) the existing ministry readiness classification.
"""

from collections import OrderedDict, defaultdict

from django.contrib.auth import get_user_model
from django.db.models import Prefetch, Q
from django.utils import timezone

from accounts.models import (
    ChurchRoleAssignment,
    ChurchStructureMembership,
    ChurchStructureUnit,
)
from events.models import ServiceEvent
from ministry.models import TeamAssignment, TeamAssignmentMember
from ministry.structure_readiness import run_audit as run_ministry_audit
from studies.models import BibleStudyMeeting, BibleStudyMeetingRole
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


class _Section:
    """A single labelled report section with severity-classified counters."""

    def __init__(self, key, title):
        self.key = key
        self.title = title
        self.blockers = OrderedDict()
        self.warnings = OrderedDict()
        self.info = OrderedDict()
        self.details = defaultdict(list)

    def blocker(self, key, count):
        self.blockers[key] = count

    def warning(self, key, count):
        self.warnings[key] = count

    def add_info(self, key, count):
        self.info[key] = count

    def detail(self, key, line):
        self.details[key].append(line)

    @property
    def blocker_count(self):
        return sum(self.blockers.values())

    @property
    def warning_count(self):
        return sum(self.warnings.values())


def _build_church_structure_section(target_date):
    section = _Section(
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


def _build_ministry_structure_section(ministry_audit):
    section = _Section(
        "ministry_structure", "2. Ministry Teams / Ministry Structure readiness"
    )
    stats = ministry_audit["stats"]
    details = ministry_audit["details"]

    section.add_info("active_teams", stats["active_teams"])
    section.add_info("assignable_teams", stats["assignable_teams"])
    section.add_info("container_teams", stats["non_assignable_teams"])

    for key in ("teams_multiple_active_primary_links", "parent_link_cycle_teams"):
        section.blocker(key, stats[key])
        for line in details.get(key, []):
            section.detail(key, line)

    for key in (
        "teams_no_active_parent_link",
        "assignable_teams_no_role_profile",
        "teams_missing_required_lead",
        "assignable_teams_no_active_membership",
    ):
        section.warning(key, stats[key])
        for line in details.get(key, []):
            section.detail(key, line)

    return section


def _build_serving_section(ministry_audit, now):
    section = _Section(
        "team_serving", "3. TeamAssignment / My Serving readiness"
    )
    stats = ministry_audit["stats"]
    details = ministry_audit["details"]

    # Blocker reused from the ministry audit (active serving assignment whose
    # team is no longer assignable). Counted here, not in section 2, so each
    # ministry counter lands in exactly one section.
    key = "active_assignments_on_non_assignable_team"
    section.blocker(key, stats[key])
    for line in details.get(key, []):
        section.detail(key, line)

    upcoming_event_ids = set(
        ServiceEvent.objects.filter(
            status=ServiceEvent.STATUS_PUBLISHED,
            start_datetime__gte=now,
        ).values_list("id", flat=True)
    )

    upcoming_assignments = (
        TeamAssignment.objects.filter(service_event_id__in=upcoming_event_ids)
        .exclude(status=TeamAssignment.STATUS_CANCELLED)
        .count()
    )
    section.add_info("upcoming_team_assignments", upcoming_assignments)

    # Serving members who are display-name-only (no linked user) cannot have the
    # assignment personalized into their My Serving. This is a serving-setup
    # warning, not a visibility/belonging signal.
    display_only_members = (
        TeamAssignmentMember.objects.filter(
            assignment__service_event_id__in=upcoming_event_ids,
            membership__is_active=True,
            membership__user__isnull=True,
        )
        .exclude(assignment__status=TeamAssignment.STATUS_CANCELLED)
        .select_related("assignment", "assignment__ministry_team", "membership")
    )
    display_only_count = 0
    for member in display_only_members:
        display_only_count += 1
        section.detail(
            "team_assignment_members_display_name_only",
            f"assignment_id={member.assignment_id} "
            f"team=#{member.assignment.ministry_team_id} "
            f"member={member.membership.get_display_name()!r}",
        )
    section.warning(
        "team_assignment_members_display_name_only", display_only_count
    )

    # Upcoming required-team coverage gaps: a published upcoming event names a
    # required team but has no non-cancelled assignment with at least one active
    # assigned member for it.
    gaps = _count_upcoming_required_team_gaps(now, section)
    section.warning("upcoming_required_team_gaps", gaps)

    return section


def _count_upcoming_required_team_gaps(now, section):
    events = (
        ServiceEvent.objects.filter(
            status=ServiceEvent.STATUS_PUBLISHED,
            start_datetime__gte=now,
        )
        .prefetch_related(
            "required_team_links__ministry_team",
            Prefetch(
                "team_assignments",
                queryset=TeamAssignment.objects.exclude(
                    status=TeamAssignment.STATUS_CANCELLED
                ).prefetch_related("assignment_members__membership"),
            ),
        )
        .order_by("start_datetime", "id")
    )

    gaps = 0
    for event in events:
        covered_team_ids = set()
        for assignment in event.team_assignments.all():
            has_active_member = any(
                am.membership.is_active
                for am in assignment.assignment_members.all()
            )
            if has_active_member:
                covered_team_ids.add(assignment.ministry_team_id)

        for link in event.required_team_links.all():
            if link.ministry_team_id not in covered_team_ids:
                gaps += 1
                section.detail(
                    "upcoming_required_team_gaps",
                    f"event_id={event.id} team=#{link.ministry_team_id} "
                    f"({link.ministry_team.get_name('en')})",
                )
    return gaps


def _build_bible_study_serving_section(now):
    section = _Section(
        "bible_study_serving", "4. Bible Study meeting-serving readiness"
    )

    upcoming_meeting_ids = list(
        BibleStudyMeeting.objects.filter(
            status=BibleStudyMeeting.STATUS_PUBLISHED,
            meeting_datetime__gte=now,
        ).values_list("id", flat=True)
    )
    section.add_info("upcoming_bible_study_meetings", len(upcoming_meeting_ids))

    display_only_roles = (
        BibleStudyMeetingRole.objects.filter(
            meeting_id__in=upcoming_meeting_ids,
            user__isnull=True,
        )
        .select_related("meeting")
        .order_by("meeting_id", "role", "id")
    )
    display_only_count = 0
    for role in display_only_roles:
        display_only_count += 1
        section.detail(
            "bible_study_meeting_roles_display_name_only",
            f"meeting_id={role.meeting_id} role={role.role} "
            f"holder={role.get_display_name()!r}",
        )
    section.warning(
        "bible_study_meeting_roles_display_name_only", display_only_count
    )
    return section


def _build_audience_visibility_section(now):
    section = _Section(
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
    section = _Section(
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


def run_audit(target_date=None, now=None):
    """Return the read-only pre-user-trial setup readiness snapshot.

    The returned dict carries the ordered list of report ``sections`` (each with
    severity-classified counters and capped verbose detail rows), aggregate
    ``blocker_count`` / ``warning_count``, static ``permission_notes``, and a
    plain-language ``recommendation``. It never writes a row.
    """
    now = now or timezone.now()
    target_date = target_date or timezone.localdate()

    ministry_audit = run_ministry_audit()

    sections = [
        _build_church_structure_section(target_date),
        _build_ministry_structure_section(ministry_audit),
        _build_serving_section(ministry_audit, now),
        _build_bible_study_serving_section(now),
        _build_audience_visibility_section(now),
        _build_permission_admin_section(),
    ]

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
