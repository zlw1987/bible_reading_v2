"""Comprehensive read-only legacy Church Structure retirement audit.

LEGACY-RETIRE.1A inventory/readiness command. It reports remaining data and
code-adjacent blockers before retiring legacy structure objects such as
``Profile.small_group``, ``SmallGroup``, ``District``, ``MinistryContext``,
legacy ServiceEvent/Bible Study scope fields, reflection legacy snapshots, and
legacy role-scope fields.

The command is deliberately read-only. It has no ``--apply`` option, writes no
rows, changes no runtime behavior, and never reconciles legacy fields.
"""

from collections import OrderedDict, defaultdict

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q
from django.utils import timezone

from accounts.models import (
    ChurchRoleAssignment,
    ChurchStructureMembership,
    ChurchStructureUnit,
    District,
    MinistryContext,
    Profile,
    SmallGroup,
)
from comments.models import ReflectionComment
from events.models import ServiceEvent, ServiceEventAudienceScope
from studies.models import (
    BibleStudyMeeting,
    BibleStudyMeetingAudienceScope,
    BibleStudySeries,
    BibleStudySeriesAudienceScope,
    BibleStudySession,
)


SECTION_KEYS = OrderedDict(
    [
        (
            "Profile.small_group",
            (
                "profiles_checked",
                "profiles_with_small_group",
                "profiles_without_small_group",
                "profiles_with_small_group_and_active_primary_membership",
                "profiles_with_small_group_no_active_primary_membership",
                "profile_membership_unit_matches_group_mapping",
                "profile_membership_unit_mismatch_group_mapping",
                "profile_group_unmapped",
                "multiple_active_primary_memberships",
                "profile_small_group_unrepresented_by_membership_blockers",
                "profile_small_group_removal_blockers",
            ),
        ),
        (
            "SmallGroup",
            (
                "small_groups_total",
                "active_small_groups",
                "inactive_small_groups",
                "small_groups_with_church_structure_unit",
                "small_groups_without_church_structure_unit",
                "small_groups_with_inactive_unit",
                "small_groups_with_wrong_unit_type",
                "profile_small_group_references",
                "bible_study_v2_meeting_small_group_references",
                "bible_study_v1_session_small_group_references",
                "reflection_small_group_at_post_references",
                "role_assignment_small_group_references",
                "service_event_small_group_references",
                "bible_study_series_small_group_references",
                "small_group_retirement_blocker_references",
            ),
        ),
        (
            "District",
            (
                "districts_total",
                "active_districts",
                "inactive_districts",
                "districts_with_church_structure_unit",
                "districts_without_church_structure_unit",
                "districts_with_inactive_unit",
                "districts_with_wrong_unit_type",
                "small_groups_with_district",
                "service_events_with_district",
                "bible_study_series_with_district",
                "bible_study_sessions_with_district",
                "role_assignments_with_district",
                "district_retirement_blocker_references",
            ),
        ),
        (
            "MinistryContext",
            (
                "ministry_contexts_total",
                "active_ministry_contexts",
                "inactive_ministry_contexts",
                "ministry_contexts_with_church_structure_unit",
                "ministry_contexts_without_church_structure_unit",
                "ministry_contexts_with_inactive_unit",
                "ministry_contexts_with_wrong_unit_type",
                "districts_with_ministry_context",
                "service_events_with_ministry_context",
                "bible_study_series_with_ministry_context",
                "ministry_context_retirement_blocker_references",
            ),
        ),
        (
            "ServiceEvent legacy scope fields",
            (
                "service_events_checked",
                "service_events_with_audience_rows",
                "service_events_without_audience_rows",
                "service_event_zero_row_visible_active_safety_blockers",
                "service_events_with_legacy_scope_type_non_global",
                "service_events_with_legacy_district_set",
                "service_events_with_legacy_small_group_set",
                "service_events_with_any_legacy_scope_field_set",
                "service_event_legacy_scope_field_retirement_blockers",
                "service_event_zero_row_runtime_fallback_active",
            ),
        ),
        (
            "Bible Study legacy fields / V1 / generation bridge",
            (
                "bible_study_series_checked",
                "bible_study_series_with_audience_rows",
                "bible_study_series_without_audience_rows",
                "bible_study_active_series_without_audience_rows",
                "bible_study_series_with_legacy_scope_fields_set",
                "bible_study_v2_meetings_checked",
                "bible_study_v2_meetings_with_small_group_mirror",
                "bible_study_v2_meetings_with_audience_rows",
                "bible_study_v2_meetings_without_audience_rows",
                "bible_study_v2_meeting_small_group_mirror_mismatches",
                "bible_study_normal_meetings_missing_generation_key",
                "bible_study_v1_sessions_checked",
                "bible_study_v1_sessions_with_legacy_scope_fields_set",
                "bible_study_v1_pilot_records_present",
                "bible_study_v1_app_runtime_retired",
                "bible_study_v1_purge_pending",
                "bible_study_v1_app_runtime_legacy_blockers",
                "bible_study_legacy_retirement_blockers",
            ),
        ),
        (
            "Reflection legacy snapshots",
            (
                "reflection_group_comments_checked",
                "reflection_group_comments_with_small_group_at_post",
                "reflection_group_comments_with_structure_unit_at_post",
                "reflection_group_comments_missing_structure_unit_at_post",
                "reflection_group_comments_structure_unit_inactive",
                "reflection_group_comments_structure_unit_wrong_type",
                "reflection_group_comments_small_group_unmapped",
                "reflection_group_comments_snapshot_mismatch",
                "reflection_small_group_at_post_removal_blockers",
            ),
        ),
        (
            "Role legacy fields",
            (
                "role_assignments_checked",
                "role_scoped_assignments",
                "role_scoped_assignments_with_structure_unit",
                "role_scoped_assignments_missing_structure_unit",
                "role_assignments_with_legacy_district_populated",
                "role_assignments_with_legacy_small_group_populated",
                "role_assignments_with_any_legacy_field_populated",
                "role_assignments_legacy_structure_unit_mismatch",
                "role_legacy_field_retirement_blockers",
            ),
        ),
        (
            "Diagnostic/backfill tooling",
            (
                "diagnostic_backfill_commands_listed",
                "diagnostic_backfill_commands_runtime_blockers",
            ),
        ),
    ]
)

COUNTER_KEYS = tuple(key for keys in SECTION_KEYS.values() for key in keys)

BLOCKER_KEYS = (
    "profile_small_group_removal_blockers",
    "profile_small_group_unrepresented_by_membership_blockers",
    "small_group_retirement_blocker_references",
    "district_retirement_blocker_references",
    "ministry_context_retirement_blocker_references",
    "service_event_legacy_scope_field_retirement_blockers",
    "service_event_zero_row_visible_active_safety_blockers",
    "bible_study_legacy_retirement_blockers",
    "reflection_small_group_at_post_removal_blockers",
    "role_legacy_field_retirement_blockers",
)

DETAIL_KEYS = (
    "profile_no_active_primary_membership",
    "profile_membership_unit_mismatch",
    "profile_group_unmapped",
    "profile_multiple_active_primary_memberships",
    "small_group_unmapped",
    "small_group_inactive_unit",
    "small_group_wrong_unit_type",
    "district_unmapped",
    "district_inactive_unit",
    "district_wrong_unit_type",
    "ministry_context_unmapped",
    "ministry_context_inactive_unit",
    "ministry_context_wrong_unit_type",
    "service_event_zero_row_safety_state",
    "service_event_legacy_scope_fields",
    "bible_study_v1_session",
    "bible_study_v2_meeting_zero_rows",
    "bible_study_v2_meeting_mirror_mismatch",
    "bible_study_generation_key_missing",
    "reflection_missing_structure_snapshot",
    "reflection_snapshot_mismatch",
    "role_legacy_field_populated",
    "role_legacy_structure_unit_mismatch",
)

DIAGNOSTIC_BACKFILL_COMMANDS = (
    (
        "accounts.management.commands.audit_structure_belonging",
        "diagnostic/audit/backfill support",
    ),
    (
        "accounts.management.commands.backfill_church_structure_memberships",
        "backfill support; mutation only when explicitly run with its apply option",
    ),
    (
        "accounts.management.commands.cleanup_profile_small_group",
        "guarded cleanup tooling for Profile.small_group; dry-run by default",
    ),
    (
        "accounts.management.commands.seed_church_structure_units",
        "setup/backfill support for legacy-to-structure mappings",
    ),
    (
        "accounts.management.commands.cleanup_legacy_structure_parent_links",
        (
            "guarded cleanup tooling for legacy SmallGroup.district / "
            "District.ministry_context parent links already represented by "
            "ChurchStructureUnit.parent; dry-run by default"
        ),
    ),
    (
        "accounts.management.commands.audit_structure_role_scopes",
        "diagnostic/audit/backfill support",
    ),
    (
        "accounts.management.commands.backfill_structure_role_scopes",
        "backfill support; dry-run by default",
    ),
    (
        "events.management.commands.audit_service_event_fallback_retirement_readiness",
        "standing diagnostic/audit guard",
    ),
    (
        "events.management.commands.backfill_service_event_audience_scopes",
        "backfill support for ServiceEvent audience rows",
    ),
    (
        "events.management.commands.cleanup_service_event_legacy_scope_fields",
        "guarded cleanup tooling for ServiceEvent legacy scope fields; dry-run by default",
    ),
    (
        "events.management.commands.backfill_service_event_host_language_units",
        (
            "backfill support for ServiceEvent.host_language_unit display "
            "context from legacy ServiceEvent.ministry_context mappings; "
            "dry-run by default"
        ),
    ),
    (
        "events.management.commands.cleanup_service_event_ministry_context_labels",
        (
            "guarded cleanup tooling for ServiceEvent.ministry_context display "
            "links where host_language_unit, or the audience-derived fallback "
            "when that field is blank, maps to the same ministry-context unit; "
            "dry-run by default"
        ),
    ),
    (
        "studies.management.commands.audit_bible_study_structure_retirement_readiness",
        "standing diagnostic/audit guard",
    ),
    (
        "studies.management.commands.backfill_bible_study_meeting_audience_scopes",
        "backfill support for Bible Study meeting audience rows",
    ),
    (
        "studies.management.commands.backfill_bible_study_v2_generation_keys",
        "backfill support for Bible Study V2 generation keys; dry-run by default",
    ),
    (
        "studies.management.commands.cleanup_bible_study_v2_small_group_mirrors",
        "guarded cleanup tooling for V2 meeting small_group mirrors; dry-run by default",
    ),
    (
        "studies.management.commands.cleanup_bible_study_series_legacy_scope_fields",
        "guarded cleanup tooling for BibleStudySeries legacy scope fields; dry-run by default",
    ),
    (
        "studies.management.commands.audit_bible_study_generation_bridge_retirement",
        "standing diagnostic/audit guard for Bible Study generation bridge retirement",
    ),
    (
        "studies.management.commands.purge_legacy_bible_study_v1_sessions",
        "guarded cleanup tooling for retired V1 pilot rows; dry-run by default",
    ),
    (
        "reading.management.commands.audit_reading_privacy_membership_readiness",
        "standing diagnostic/audit guard",
    ),
    (
        "reading.management.commands.audit_reading_structure_runtime_readiness",
        "standing diagnostic/audit guard",
    ),
    (
        "reading.management.commands.audit_group_progress_shadow",
        "shadow diagnostic; not an ordinary runtime blocker",
    ),
    (
        "reading.management.commands.backfill_reflection_structure_snapshots",
        "backfill support for reflection structure snapshots",
    ),
    (
        "reading.management.commands.cleanup_reflection_snapshot_blockers",
        "guarded cleanup tooling for remaining reflection snapshot blockers; dry-run by default",
    ),
    (
        "reading.management.commands.cleanup_reflection_small_group_mirrors",
        "guarded cleanup tooling for existing reflection small_group_at_post mirrors; dry-run by default",
    ),
    (
        "reading.management.commands.cleanup_reflection_nongroup_display_mirrors",
        "guarded migration of non-group reflection display context off small_group_at_post; dry-run by default",
    ),
)


def _new_stats():
    return OrderedDict((key, 0) for key in COUNTER_KEYS)


def _new_details():
    return OrderedDict((key, []) for key in DETAIL_KEYS)


def _active_primary_memberships(target_date):
    return (
        ChurchStructureMembership.objects.filter(
            status=ChurchStructureMembership.STATUS_ACTIVE,
            is_primary=True,
            start_date__lte=target_date,
        )
        .filter(Q(end_date__isnull=True) | Q(end_date__gte=target_date))
        .select_related("unit")
        .order_by("user_id", "id")
    )


def _memberships_by_user(target_date):
    memberships_by_user = defaultdict(list)
    for membership in _active_primary_memberships(target_date):
        memberships_by_user[membership.user_id].append(membership)
    return memberships_by_user


def _unit_label(unit):
    if unit is None:
        return "(none)"
    label = f"#{unit.id} {unit.code}"
    if unit.name_en:
        label = f"{label} {unit.name_en}"
    elif unit.name:
        label = f"{label} {unit.name}"
    return label


def _group_label(group):
    if group is None:
        return "(none)"
    return f"#{group.id} {group.name}"


def _district_label(district):
    if district is None:
        return "(none)"
    return f"#{district.id} {district.name}"


def _context_label(context):
    if context is None:
        return "(none)"
    return f"#{context.id} {context.code}"


def _expected_unit_state(unit, expected_unit_type):
    if unit is None:
        return "missing"
    if not unit.is_active:
        return "inactive"
    if unit.unit_type != expected_unit_type:
        return "wrong_type"
    return "ok"


def _is_service_event_visible_active_safety_state(event, now):
    if event.status == ServiceEvent.STATUS_PUBLISHED:
        return True
    if event.status == ServiceEvent.STATUS_COMPLETED:
        return bool(event.start_datetime and event.start_datetime >= now)
    return False


def _service_event_has_legacy_scope_fields(event):
    return bool(
        event.scope_type != ServiceEvent.SCOPE_GLOBAL
        or event.district_id
        or event.small_group_id
    )


def _bible_study_series_has_legacy_scope_fields(series):
    return bool(
        series.scope_type != BibleStudySeries.SCOPE_GLOBAL
        or series.ministry_context_id
        or series.district_id
        or series.small_group_id
    )


def _bible_study_session_has_legacy_scope_fields(session):
    return bool(
        session.scope_type != BibleStudySession.SCOPE_GLOBAL
        or session.district_id
        or session.small_group_id
    )


def _role_legacy_unit(assignment):
    if (
        assignment.scope_type == ChurchRoleAssignment.SCOPE_SMALL_GROUP
        and assignment.small_group is not None
    ):
        return assignment.small_group.church_structure_unit
    if (
        assignment.scope_type == ChurchRoleAssignment.SCOPE_DISTRICT
        and assignment.district is not None
    ):
        return assignment.district.church_structure_unit
    return None


def _append(details, key, line):
    details[key].append(line)


def _scan_profiles(stats, details, target_date):
    memberships_by_user = _memberships_by_user(target_date)
    profiles = (
        Profile.objects.select_related(
            "user",
            "small_group",
            "small_group__church_structure_unit",
        )
        .all()
        .order_by("user__username", "id")
    )

    for profile in profiles:
        stats["profiles_checked"] += 1
        group = profile.small_group
        memberships = memberships_by_user.get(profile.user_id, [])

        if group is None:
            stats["profiles_without_small_group"] += 1
            if len(memberships) > 1:
                stats["multiple_active_primary_memberships"] += 1
            continue

        stats["profiles_with_small_group"] += 1
        if memberships:
            stats["profiles_with_small_group_and_active_primary_membership"] += 1
        else:
            stats["profiles_with_small_group_no_active_primary_membership"] += 1
            _append(
                details,
                "profile_no_active_primary_membership",
                "user_id={user_id} username={username} profile_small_group={group}".format(
                    user_id=profile.user_id,
                    username=profile.user.get_username(),
                    group=_group_label(group),
                ),
            )

        group_unit = group.church_structure_unit
        if group_unit is None:
            stats["profile_group_unmapped"] += 1
            _append(
                details,
                "profile_group_unmapped",
                "user_id={user_id} username={username} profile_small_group={group}".format(
                    user_id=profile.user_id,
                    username=profile.user.get_username(),
                    group=_group_label(group),
                ),
            )

        if len(memberships) > 1:
            stats["multiple_active_primary_memberships"] += 1
            _append(
                details,
                "profile_multiple_active_primary_memberships",
                "user_id={user_id} username={username} membership_ids={ids}".format(
                    user_id=profile.user_id,
                    username=profile.user.get_username(),
                    ids=",".join(str(membership.id) for membership in memberships),
                ),
            )
        elif len(memberships) == 1 and group_unit is not None:
            membership = memberships[0]
            if membership.unit_id == group_unit.id:
                stats["profile_membership_unit_matches_group_mapping"] += 1
            else:
                stats["profile_membership_unit_mismatch_group_mapping"] += 1
                _append(
                    details,
                    "profile_membership_unit_mismatch",
                    (
                        "user_id={user_id} username={username} "
                        "profile_small_group={group} profile_unit={profile_unit} "
                        "membership_unit={membership_unit}"
                    ).format(
                        user_id=profile.user_id,
                        username=profile.user.get_username(),
                        group=_group_label(group),
                        profile_unit=_unit_label(group_unit),
                        membership_unit=_unit_label(membership.unit),
                    ),
                )

    stats["profile_small_group_unrepresented_by_membership_blockers"] = (
        stats["profiles_with_small_group_no_active_primary_membership"]
        + stats["profile_membership_unit_mismatch_group_mapping"]
        + stats["profile_group_unmapped"]
        + stats["multiple_active_primary_memberships"]
    )
    stats["profile_small_group_removal_blockers"] = stats["profiles_with_small_group"]


def _scan_small_groups(stats, details):
    groups = (
        SmallGroup.objects.select_related("church_structure_unit")
        .all()
        .order_by("name", "id")
    )
    for group in groups:
        stats["small_groups_total"] += 1
        if group.is_active:
            stats["active_small_groups"] += 1
        else:
            stats["inactive_small_groups"] += 1

        state = _expected_unit_state(
            group.church_structure_unit,
            ChurchStructureUnit.UNIT_SMALL_GROUP,
        )
        if state == "missing":
            stats["small_groups_without_church_structure_unit"] += 1
            _append(
                details,
                "small_group_unmapped",
                f"small_group={_group_label(group)}",
            )
        else:
            stats["small_groups_with_church_structure_unit"] += 1
            if state == "inactive":
                stats["small_groups_with_inactive_unit"] += 1
                _append(
                    details,
                    "small_group_inactive_unit",
                    "small_group={group} mapped_unit={unit}".format(
                        group=_group_label(group),
                        unit=_unit_label(group.church_structure_unit),
                    ),
                )
            elif state == "wrong_type":
                stats["small_groups_with_wrong_unit_type"] += 1
                _append(
                    details,
                    "small_group_wrong_unit_type",
                    "small_group={group} mapped_unit={unit} unit_type={unit_type}".format(
                        group=_group_label(group),
                        unit=_unit_label(group.church_structure_unit),
                        unit_type=group.church_structure_unit.unit_type,
                    ),
                )

    stats["profile_small_group_references"] = stats["profiles_with_small_group"]
    stats["bible_study_v2_meeting_small_group_references"] = (
        BibleStudyMeeting.objects.filter(small_group__isnull=False).count()
    )
    stats["bible_study_v1_session_small_group_references"] = (
        BibleStudySession.objects.filter(small_group__isnull=False).count()
    )
    stats["reflection_small_group_at_post_references"] = (
        ReflectionComment.objects.filter(small_group_at_post__isnull=False).count()
    )
    stats["role_assignment_small_group_references"] = (
        ChurchRoleAssignment.objects.filter(small_group__isnull=False).count()
    )
    stats["service_event_small_group_references"] = (
        ServiceEvent.objects.filter(small_group__isnull=False).count()
    )
    stats["bible_study_series_small_group_references"] = (
        BibleStudySeries.objects.filter(small_group__isnull=False).count()
    )
    stats["small_group_retirement_blocker_references"] = (
        stats["small_groups_total"]
        + stats["profile_small_group_references"]
        + stats["bible_study_v2_meeting_small_group_references"]
        + stats["bible_study_v1_session_small_group_references"]
        + stats["reflection_small_group_at_post_references"]
        + stats["role_assignment_small_group_references"]
        + stats["service_event_small_group_references"]
        + stats["bible_study_series_small_group_references"]
    )


def _scan_districts(stats, details):
    districts = (
        District.objects.select_related("church_structure_unit")
        .all()
        .order_by("name", "id")
    )
    for district in districts:
        stats["districts_total"] += 1
        if district.is_active:
            stats["active_districts"] += 1
        else:
            stats["inactive_districts"] += 1

        state = _expected_unit_state(
            district.church_structure_unit,
            ChurchStructureUnit.UNIT_DISTRICT,
        )
        if state == "missing":
            stats["districts_without_church_structure_unit"] += 1
            _append(
                details,
                "district_unmapped",
                f"district={_district_label(district)}",
            )
        else:
            stats["districts_with_church_structure_unit"] += 1
            if state == "inactive":
                stats["districts_with_inactive_unit"] += 1
                _append(
                    details,
                    "district_inactive_unit",
                    "district={district} mapped_unit={unit}".format(
                        district=_district_label(district),
                        unit=_unit_label(district.church_structure_unit),
                    ),
                )
            elif state == "wrong_type":
                stats["districts_with_wrong_unit_type"] += 1
                _append(
                    details,
                    "district_wrong_unit_type",
                    "district={district} mapped_unit={unit} unit_type={unit_type}".format(
                        district=_district_label(district),
                        unit=_unit_label(district.church_structure_unit),
                        unit_type=district.church_structure_unit.unit_type,
                    ),
                )

    stats["small_groups_with_district"] = (
        SmallGroup.objects.filter(district__isnull=False).count()
    )
    stats["service_events_with_district"] = (
        ServiceEvent.objects.filter(district__isnull=False).count()
    )
    stats["bible_study_series_with_district"] = (
        BibleStudySeries.objects.filter(district__isnull=False).count()
    )
    stats["bible_study_sessions_with_district"] = (
        BibleStudySession.objects.filter(district__isnull=False).count()
    )
    stats["role_assignments_with_district"] = (
        ChurchRoleAssignment.objects.filter(district__isnull=False).count()
    )
    stats["district_retirement_blocker_references"] = (
        stats["districts_total"]
        + stats["small_groups_with_district"]
        + stats["service_events_with_district"]
        + stats["bible_study_series_with_district"]
        + stats["bible_study_sessions_with_district"]
        + stats["role_assignments_with_district"]
    )


def _scan_ministry_contexts(stats, details):
    contexts = (
        MinistryContext.objects.select_related("church_structure_unit")
        .all()
        .order_by("code", "id")
    )
    for context in contexts:
        stats["ministry_contexts_total"] += 1
        if context.is_active:
            stats["active_ministry_contexts"] += 1
        else:
            stats["inactive_ministry_contexts"] += 1

        state = _expected_unit_state(
            context.church_structure_unit,
            ChurchStructureUnit.UNIT_MINISTRY_CONTEXT,
        )
        if state == "missing":
            stats["ministry_contexts_without_church_structure_unit"] += 1
            _append(
                details,
                "ministry_context_unmapped",
                f"ministry_context={_context_label(context)}",
            )
        else:
            stats["ministry_contexts_with_church_structure_unit"] += 1
            if state == "inactive":
                stats["ministry_contexts_with_inactive_unit"] += 1
                _append(
                    details,
                    "ministry_context_inactive_unit",
                    "ministry_context={context} mapped_unit={unit}".format(
                        context=_context_label(context),
                        unit=_unit_label(context.church_structure_unit),
                    ),
                )
            elif state == "wrong_type":
                stats["ministry_contexts_with_wrong_unit_type"] += 1
                _append(
                    details,
                    "ministry_context_wrong_unit_type",
                    "ministry_context={context} mapped_unit={unit} unit_type={unit_type}".format(
                        context=_context_label(context),
                        unit=_unit_label(context.church_structure_unit),
                        unit_type=context.church_structure_unit.unit_type,
                    ),
                )

    stats["districts_with_ministry_context"] = (
        District.objects.filter(ministry_context__isnull=False).count()
    )
    stats["service_events_with_ministry_context"] = (
        ServiceEvent.objects.filter(ministry_context__isnull=False).count()
    )
    stats["bible_study_series_with_ministry_context"] = (
        BibleStudySeries.objects.filter(ministry_context__isnull=False).count()
    )
    stats["ministry_context_retirement_blocker_references"] = (
        stats["ministry_contexts_total"]
        + stats["districts_with_ministry_context"]
        + stats["service_events_with_ministry_context"]
        + stats["bible_study_series_with_ministry_context"]
    )


def _scan_service_events(stats, details, now):
    event_ids_with_rows = set(
        ServiceEventAudienceScope.objects.values_list(
            "service_event_id", flat=True
        ).distinct()
    )
    events = ServiceEvent.objects.select_related(
        "district",
        "small_group",
    ).order_by("id")

    for event in events:
        stats["service_events_checked"] += 1
        has_rows = event.id in event_ids_with_rows
        if has_rows:
            stats["service_events_with_audience_rows"] += 1
        else:
            stats["service_events_without_audience_rows"] += 1
            if _is_service_event_visible_active_safety_state(event, now):
                stats["service_event_zero_row_visible_active_safety_blockers"] += 1
                _append(
                    details,
                    "service_event_zero_row_safety_state",
                    (
                        "event_id={event_id} title={title} status={status} "
                        "scope_type={scope_type}"
                    ).format(
                        event_id=event.id,
                        title=event.title,
                        status=event.status,
                        scope_type=event.scope_type,
                    ),
                )

        if event.scope_type != ServiceEvent.SCOPE_GLOBAL:
            stats["service_events_with_legacy_scope_type_non_global"] += 1
        if event.district_id:
            stats["service_events_with_legacy_district_set"] += 1
        if event.small_group_id:
            stats["service_events_with_legacy_small_group_set"] += 1
        if _service_event_has_legacy_scope_fields(event):
            stats["service_events_with_any_legacy_scope_field_set"] += 1
            _append(
                details,
                "service_event_legacy_scope_fields",
                (
                    "event_id={event_id} title={title} scope_type={scope_type} "
                    "district={district} small_group={small_group}"
                ).format(
                    event_id=event.id,
                    title=event.title,
                    scope_type=event.scope_type,
                    district=_district_label(event.district),
                    small_group=_group_label(event.small_group),
                ),
            )

    stats["service_event_legacy_scope_field_retirement_blockers"] = (
        stats["service_events_with_any_legacy_scope_field_set"]
    )
    # Current code has already retired the ordinary-user zero-row legacy fallback.
    stats["service_event_zero_row_runtime_fallback_active"] = 0


def _scan_bible_study(stats, details):
    series_ids_with_rows = set(
        BibleStudySeriesAudienceScope.objects.values_list(
            "series_id", flat=True
        ).distinct()
    )
    series_rows = BibleStudySeries.objects.order_by("id")
    for series in series_rows:
        stats["bible_study_series_checked"] += 1
        has_rows = series.id in series_ids_with_rows
        if has_rows:
            stats["bible_study_series_with_audience_rows"] += 1
        else:
            stats["bible_study_series_without_audience_rows"] += 1
            if series.is_active:
                stats["bible_study_active_series_without_audience_rows"] += 1
        if _bible_study_series_has_legacy_scope_fields(series):
            stats["bible_study_series_with_legacy_scope_fields_set"] += 1

    meeting_ids_with_rows = set(
        BibleStudyMeetingAudienceScope.objects.values_list(
            "meeting_id", flat=True
        ).distinct()
    )
    meetings = (
        BibleStudyMeeting.objects.select_related(
            "lesson",
            "small_group",
            "small_group__church_structure_unit",
        )
        .prefetch_related("audience_scope_links__unit")
        .order_by("id")
    )
    for meeting in meetings:
        stats["bible_study_v2_meetings_checked"] += 1
        if meeting.small_group_id:
            stats["bible_study_v2_meetings_with_small_group_mirror"] += 1
        has_rows = meeting.id in meeting_ids_with_rows
        if has_rows:
            stats["bible_study_v2_meetings_with_audience_rows"] += 1
        else:
            stats["bible_study_v2_meetings_without_audience_rows"] += 1
            _append(
                details,
                "bible_study_v2_meeting_zero_rows",
                "meeting_id={meeting_id} lesson={lesson} small_group={small_group}".format(
                    meeting_id=meeting.id,
                    lesson=meeting.lesson.title if meeting.lesson_id else "",
                    small_group=_group_label(meeting.small_group),
                ),
            )

        if (
            meeting.meeting_kind == BibleStudyMeeting.KIND_NORMAL
            and not meeting.generation_key
        ):
            stats["bible_study_normal_meetings_missing_generation_key"] += 1
            _append(
                details,
                "bible_study_generation_key_missing",
                "meeting_id={meeting_id} lesson={lesson} small_group={small_group}".format(
                    meeting_id=meeting.id,
                    lesson=meeting.lesson.title if meeting.lesson_id else "",
                    small_group=_group_label(meeting.small_group),
                ),
            )

        audience_units = [link.unit for link in meeting.audience_scope_links.all()]
        if len(audience_units) == 1 and meeting.small_group is not None:
            mirror_unit = meeting.small_group.church_structure_unit
            if mirror_unit is not None and mirror_unit.id != audience_units[0].id:
                stats["bible_study_v2_meeting_small_group_mirror_mismatches"] += 1
                _append(
                    details,
                    "bible_study_v2_meeting_mirror_mismatch",
                    (
                        "meeting_id={meeting_id} lesson={lesson} "
                        "small_group={small_group} mirror_unit={mirror_unit} "
                        "audience_unit={audience_unit}"
                    ).format(
                        meeting_id=meeting.id,
                        lesson=meeting.lesson.title if meeting.lesson_id else "",
                        small_group=_group_label(meeting.small_group),
                        mirror_unit=_unit_label(mirror_unit),
                        audience_unit=_unit_label(audience_units[0]),
                    ),
                )

    sessions = BibleStudySession.objects.select_related(
        "series",
        "district",
        "small_group",
    ).order_by("id")
    for session in sessions:
        stats["bible_study_v1_sessions_checked"] += 1
        if _bible_study_session_has_legacy_scope_fields(session):
            stats["bible_study_v1_sessions_with_legacy_scope_fields_set"] += 1
        _append(
            details,
            "bible_study_v1_session",
            "session_id={session_id} title={title} scope_type={scope_type}".format(
                session_id=session.id,
                title=session.title,
                scope_type=session.scope_type,
            ),
        )

    stats["bible_study_v1_pilot_records_present"] = stats[
        "bible_study_v1_sessions_checked"
    ]
    # BS-V1-RETIRE.1A: V1 app-level runtime is retired for ordinary users and
    # managers. Remaining pilot rows are data-retirement/purge work, not app
    # visibility blockers.
    stats["bible_study_v1_app_runtime_retired"] = 1
    stats["bible_study_v1_purge_pending"] = stats[
        "bible_study_v1_sessions_checked"
    ]
    stats["bible_study_v1_app_runtime_legacy_blockers"] = 0
    stats["bible_study_legacy_retirement_blockers"] = (
        stats["bible_study_active_series_without_audience_rows"]
        + stats["bible_study_series_with_legacy_scope_fields_set"]
        + stats["bible_study_v2_meetings_with_small_group_mirror"]
        + stats["bible_study_v2_meetings_without_audience_rows"]
        + stats["bible_study_v2_meeting_small_group_mirror_mismatches"]
        + stats["bible_study_normal_meetings_missing_generation_key"]
        + stats["bible_study_v1_purge_pending"]
        + stats["bible_study_v1_app_runtime_legacy_blockers"]
    )


def _scan_reflections(stats, details):
    comments = (
        ReflectionComment.objects.filter(
            visibility=ReflectionComment.VISIBILITY_GROUP
        )
        .select_related(
            "small_group_at_post",
            "small_group_at_post__church_structure_unit",
            "structure_unit_at_post",
        )
        .order_by("id")
    )
    for comment in comments:
        stats["reflection_group_comments_checked"] += 1
        small_group = comment.small_group_at_post
        structure_unit = comment.structure_unit_at_post
        if small_group is not None:
            stats["reflection_group_comments_with_small_group_at_post"] += 1
        if structure_unit is not None:
            stats["reflection_group_comments_with_structure_unit_at_post"] += 1
        else:
            stats["reflection_group_comments_missing_structure_unit_at_post"] += 1
            _append(
                details,
                "reflection_missing_structure_snapshot",
                f"comment_id={comment.id} small_group_at_post={_group_label(small_group)}",
            )

        if structure_unit is not None and not structure_unit.is_active:
            stats["reflection_group_comments_structure_unit_inactive"] += 1
        if (
            structure_unit is not None
            and structure_unit.unit_type != ChurchStructureUnit.UNIT_SMALL_GROUP
        ):
            stats["reflection_group_comments_structure_unit_wrong_type"] += 1

        small_group_unit = (
            small_group.church_structure_unit if small_group is not None else None
        )
        if small_group is not None and small_group_unit is None:
            stats["reflection_group_comments_small_group_unmapped"] += 1
        if (
            small_group_unit is not None
            and structure_unit is not None
            and small_group_unit.id != structure_unit.id
        ):
            stats["reflection_group_comments_snapshot_mismatch"] += 1
            _append(
                details,
                "reflection_snapshot_mismatch",
                (
                    "comment_id={comment_id} small_group_at_post={small_group} "
                    "small_group_unit={small_group_unit} structure_unit_at_post={structure_unit}"
                ).format(
                    comment_id=comment.id,
                    small_group=_group_label(small_group),
                    small_group_unit=_unit_label(small_group_unit),
                    structure_unit=_unit_label(structure_unit),
                ),
            )

    stats["reflection_small_group_at_post_removal_blockers"] = (
        stats["reflection_group_comments_missing_structure_unit_at_post"]
        + stats["reflection_group_comments_structure_unit_inactive"]
        + stats["reflection_group_comments_structure_unit_wrong_type"]
        + stats["reflection_group_comments_small_group_unmapped"]
        + stats["reflection_group_comments_snapshot_mismatch"]
    )


def _scan_roles(stats, details):
    assignments = (
        ChurchRoleAssignment.objects.select_related(
            "user",
            "district",
            "district__church_structure_unit",
            "small_group",
            "small_group__church_structure_unit",
            "structure_unit",
        )
        .all()
        .order_by("user__username", "role", "scope_type", "id")
    )
    for assignment in assignments:
        stats["role_assignments_checked"] += 1
        is_scoped = assignment.scope_type != ChurchRoleAssignment.SCOPE_GLOBAL
        if is_scoped:
            stats["role_scoped_assignments"] += 1
            if assignment.structure_unit_id:
                stats["role_scoped_assignments_with_structure_unit"] += 1
            else:
                stats["role_scoped_assignments_missing_structure_unit"] += 1

        has_legacy_district = bool(assignment.district_id)
        has_legacy_small_group = bool(assignment.small_group_id)
        if has_legacy_district:
            stats["role_assignments_with_legacy_district_populated"] += 1
        if has_legacy_small_group:
            stats["role_assignments_with_legacy_small_group_populated"] += 1
        if has_legacy_district or has_legacy_small_group:
            stats["role_assignments_with_any_legacy_field_populated"] += 1
            _append(
                details,
                "role_legacy_field_populated",
                (
                    "assignment_id={assignment_id} username={username} "
                    "scope_type={scope_type} district={district} small_group={small_group} "
                    "structure_unit={structure_unit}"
                ).format(
                    assignment_id=assignment.id,
                    username=assignment.user.get_username(),
                    scope_type=assignment.scope_type,
                    district=_district_label(assignment.district),
                    small_group=_group_label(assignment.small_group),
                    structure_unit=_unit_label(assignment.structure_unit),
                ),
            )

        legacy_unit = _role_legacy_unit(assignment)
        if (
            assignment.structure_unit_id
            and legacy_unit is not None
            and assignment.structure_unit_id != legacy_unit.id
        ):
            stats["role_assignments_legacy_structure_unit_mismatch"] += 1
            _append(
                details,
                "role_legacy_structure_unit_mismatch",
                (
                    "assignment_id={assignment_id} username={username} "
                    "legacy_unit={legacy_unit} structure_unit={structure_unit}"
                ).format(
                    assignment_id=assignment.id,
                    username=assignment.user.get_username(),
                    legacy_unit=_unit_label(legacy_unit),
                    structure_unit=_unit_label(assignment.structure_unit),
                ),
            )

    stats["role_legacy_field_retirement_blockers"] = (
        stats["role_assignments_with_any_legacy_field_populated"]
        + stats["role_scoped_assignments_missing_structure_unit"]
        + stats["role_assignments_legacy_structure_unit_mismatch"]
    )


def _scan_tooling(stats):
    stats["diagnostic_backfill_commands_listed"] = len(DIAGNOSTIC_BACKFILL_COMMANDS)
    stats["diagnostic_backfill_commands_runtime_blockers"] = 0


def run_audit(target_date=None, now=None):
    """Run one read-only retirement-readiness audit pass."""
    target_date = target_date or timezone.localdate()
    now = now or timezone.now()
    stats = _new_stats()
    details = _new_details()

    _scan_profiles(stats, details, target_date)
    _scan_small_groups(stats, details)
    _scan_districts(stats, details)
    _scan_ministry_contexts(stats, details)
    _scan_service_events(stats, details, now)
    _scan_bible_study(stats, details)
    _scan_reflections(stats, details)
    _scan_roles(stats, details)
    _scan_tooling(stats)

    return {
        "stats": stats,
        "details": details,
        "target_date": target_date,
        "now": now,
        "diagnostic_commands": DIAGNOSTIC_BACKFILL_COMMANDS,
    }


def _blocker_items(stats):
    return [(key, stats[key]) for key in BLOCKER_KEYS if stats[key]]


class Command(BaseCommand):
    help = (
        "LEGACY-RETIRE.1A read-only comprehensive audit for legacy Church "
        "Structure retirement readiness. Reports remaining blockers for "
        "Profile.small_group, SmallGroup, District, MinistryContext, legacy "
        "ServiceEvent/Bible Study scope fields, reflection legacy snapshots, "
        "and legacy role-scope fields. Writes nothing and has no --apply."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--verbose",
            action="store_true",
            help="Print capped example rows for blocker categories.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Maximum number of verbose example rows to print per category.",
        )
        parser.add_argument(
            "--fail-on-blockers",
            action="store_true",
            help=(
                "Exit nonzero when field/table retirement blockers are present. "
                "Still read-only; diagnostic/backfill commands alone do not fail."
            ),
        )

    def handle(self, *args, **options):
        if options["limit"] is not None and options["limit"] < 0:
            raise CommandError("--limit must be zero or greater.")

        audit = run_audit()
        self._print_report(
            audit,
            verbose=options["verbose"],
            limit=options["limit"],
        )

        blockers = _blocker_items(audit["stats"])
        if options["fail_on_blockers"] and blockers:
            raise CommandError(
                "Legacy Church Structure retirement blockers present "
                "(--fail-on-blockers): "
                + ", ".join(f"{key}={value}" for key, value in blockers)
            )

    def _print_report(self, audit, *, verbose, limit):
        write = self.stdout.write
        stats = audit["stats"]
        blockers = _blocker_items(stats)

        write(
            "Legacy Church Structure retirement readiness audit "
            "(LEGACY-RETIRE.1A, read-only)"
        )
        write("=" * 82)
        write(f"target_date: {audit['target_date'].isoformat()}")
        write("runtime_mutated: false")
        write("data_mutated: false")
        write("apply_option_present: false")
        write("")
        write("summary counters:")
        for section, keys in SECTION_KEYS.items():
            write(f"{section}:")
            for key in keys:
                write(f"  {key}: {stats[key]}")
            write("")

        write("blockers:")
        if blockers:
            for key, value in blockers:
                write(f"  {key}: {value}")
            write("retirement_readiness: BLOCKED")
        else:
            write("  (none)")
            write("retirement_readiness: CLEAN")

        write("")
        write("diagnostic/backfill commands (support tooling, not runtime blockers):")
        for command_name, classification in audit["diagnostic_commands"]:
            write(f"  {command_name} - {classification}")

        write("")
        write(
            "Audit only: no Profile.small_group, ChurchStructureMembership, "
            "ChurchStructureUnit, SmallGroup, District, MinistryContext, "
            "ServiceEvent, Bible Study, ReflectionComment, ChurchRoleAssignment, "
            "audience, role, or permission rows were changed. ServiceEvent "
            "zero-row events are currently fail-closed safety states for ordinary "
            "users, not legacy ordinary-visibility fallback."
        )

        if not verbose:
            return

        write("")
        write("examples (capped per category):")
        for key, rows in audit["details"].items():
            write(f"{key} ({len(rows)}):")
            if not rows:
                write("  (none)")
                continue

            shown = rows if limit is None else rows[:limit]
            for row in shown:
                write(f"  {row}")
            if limit is not None and len(rows) > len(shown):
                write(f"  (stopped at --limit {limit}; {len(rows) - len(shown)} more)")
