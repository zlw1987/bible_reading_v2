"""Studies module's setup/readiness check provider (MODULAR-CORE.5A).

Owns the Bible Study meeting-serving readiness section of the pre-user-trial
setup audit. The section body moved here from
``accounts.trial_setup_readiness``; registration stays explicit —
``accounts.trial_setup_readiness`` calls :func:`register` at import time,
before ``run_audit`` builds the report. The provider runs only when the
``studies`` module is enabled (``core.setup_readiness.build_readiness_sections``).

This provider is strictly read-only. It reports Bible Study meeting roles that
are display-name-only (cannot personalize My Serving) as a serving-setup
warning; serving stays explicit (linked-user ``BibleStudyMeetingRole.user``)
and ``ChurchStructureMembership`` (belonging) is never treated as serving. The
zero-audience meeting *blocker* is deliberately not moved here — it stays in
the shared audience-visibility section so fail-closed visibility checks keep
running regardless of module enablement (see
``docs/MODULE_BOUNDARIES.md``).
"""

from core.setup_readiness import ReadinessSection, register_readiness_provider

from .models import BibleStudyMeeting, BibleStudyMeetingRole


def _build_bible_study_serving_section(now):
    section = ReadinessSection(
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


def build(context):
    """Bible Study meeting-serving readiness section."""
    return [_build_bible_study_serving_section(context.now)]


def register():
    """Register the studies readiness provider (called from the audit runner)."""
    register_readiness_provider("studies", build, module_key="studies")
