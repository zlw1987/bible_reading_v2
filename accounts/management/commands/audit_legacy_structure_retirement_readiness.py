"""Comprehensive read-only legacy Church Structure retirement audit.

LEGACY-RETIRE.1A inventory/readiness command. It reports remaining data and
code-adjacent blockers before retiring legacy structure objects such as
``SmallGroup``, ``District``, and ``MinistryContext``. (``Profile.small_group``,
legacy ServiceEvent/Bible Study scope fields, reflection legacy snapshots, and
legacy role-scope fields have already been removed; only immutable historical
migrations still name them.)

The command is deliberately read-only. It has no ``--apply`` option, writes no
rows, changes no runtime behavior, and never reconciles legacy fields.
"""

from collections import OrderedDict

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from accounts.models import (
    ChurchRoleAssignment,
    ChurchStructureUnit,
    District,
    MinistryContext,
    SmallGroup,
)
from comments.models import ReflectionComment
from events.models import ServiceEvent, ServiceEventAudienceScope
from studies.models import (
    BibleStudyMeeting,
    BibleStudyMeetingAudienceScope,
    BibleStudySeries,
    BibleStudySeriesAudienceScope,
)


SECTION_KEYS = OrderedDict(
    [
        # PROFILE-SG-FIELD-RETIRE.1A removed Profile.small_group; its data
        # counters (profiles_with_small_group, profile_small_group_removal_blockers,
        # etc.) were retired with the field. Belonging is membership-core
        # (ChurchStructureMembership). Only immutable historical migrations still
        # name the field.
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
                "service_event_small_group_references",
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
                "bible_study_sessions_with_district",
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
                "ministry_context_retirement_blocker_references",
            ),
        ),
        (
            # SE-FIELD-RETIRE.1A removed ServiceEvent.scope_type / district /
            # small_group. This section now only tracks audience-row readiness
            # and the (historical, always-0) zero-row runtime fallback marker.
            "ServiceEvent audience rows",
            (
                "service_events_checked",
                "service_events_with_audience_rows",
                "service_events_without_audience_rows",
                "service_event_zero_row_visible_active_safety_blockers",
                "service_event_zero_row_runtime_fallback_active",
            ),
        ),
        (
            "Bible Study legacy fields / V1 / structure-native readiness",
            (
                "bible_study_series_checked",
                "bible_study_series_with_audience_rows",
                "bible_study_series_without_audience_rows",
                "bible_study_active_series_without_audience_rows",
                "bible_study_v2_meetings_checked",
                "bible_study_v2_meetings_with_audience_rows",
                "bible_study_v2_meetings_without_audience_rows",
                "bible_study_normal_meetings_missing_generation_key",
                "bible_study_structure_native_readiness_blockers",
                "bible_study_v1_sessions_checked",
                "bible_study_v1_sessions_with_legacy_scope_fields_set",
                "bible_study_v1_sessions_with_district_id",
                "bible_study_v1_sessions_with_small_group_id",
                "bible_study_v1_guides_checked",
                "bible_study_v1_worship_songs_checked",
                "bible_study_v1_child_rows_purge_pending",
                "bible_study_v1_pilot_records_present",
                "bible_study_v1_app_runtime_retired",
                "bible_study_v1_purge_pending",
                "bible_study_v1_app_runtime_legacy_blockers",
                "bible_study_legacy_retirement_blockers",
            ),
        ),
        (
            "Reflection structure snapshots",
            (
                "reflection_group_comments_checked",
                "reflection_group_comments_with_structure_unit_at_post",
                "reflection_group_comments_missing_structure_unit_at_post",
                "reflection_group_comments_structure_unit_inactive",
                "reflection_group_comments_structure_unit_wrong_type",
                "reflection_structure_snapshot_readiness_blockers",
            ),
        ),
        (
            "Role structure scope",
            (
                "role_assignments_checked",
                "role_scoped_assignments",
                "role_scoped_assignments_with_structure_unit",
                "role_scoped_assignments_missing_structure_unit",
                "role_scoped_assignments_structure_unit_retirement_blockers",
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
    "small_group_retirement_blocker_references",
    "district_retirement_blocker_references",
    "ministry_context_retirement_blocker_references",
    "service_event_zero_row_visible_active_safety_blockers",
    "bible_study_legacy_retirement_blockers",
    "reflection_structure_snapshot_readiness_blockers",
    "role_scoped_assignments_structure_unit_retirement_blockers",
)

DETAIL_KEYS = (
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
    "bible_study_v1_session",
    "bible_study_v2_meeting_zero_rows",
    "bible_study_generation_key_missing",
    "reflection_missing_structure_snapshot",
    "role_scoped_assignment_missing_structure_unit",
)

DIAGNOSTIC_BACKFILL_COMMANDS = (
    # PROFILE-SG-FIELD-RETIRE.1A removed Profile.small_group together with its
    # guarded cleanup command (cleanup_profile_small_group), the legacy
    # profile-vs-membership belonging drift audit (audit_structure_belonging),
    # and the membership backfill that sourced from the field
    # (backfill_church_structure_memberships), so none are listed here.
    (
        "accounts.management.commands.seed_church_structure_units",
        (
            "canonical ChurchStructureUnit root seed support; after "
            "LEGACY-STRUCTURE-SURFACE-RETIRE.1A it no longer reads or rebuilds "
            "SmallGroup, District, or MinistryContext rows"
        ),
    ),
    (
        "accounts.management.commands.audit_legacy_structure_object_row_retirement",
        (
            "read-only final proof that SmallGroup, District, and MinistryContext "
            "rows remain purged before the separate model/table deletion slice; "
            "not runtime authority and not a data mutation command"
        ),
    ),
    # LEGACY-PARENT-FK-FIELD-RETIRE.1A removed SmallGroup.district /
    # District.ministry_context together with their only guarded cleanup tooling
    # (cleanup_legacy_structure_parent_links), so it is no longer listed here.
    (
        "accounts.management.commands.audit_structure_role_scopes",
        "read-only diagnostic validating explicit structure_unit role scope",
    ),
    # SE-FIELD-RETIRE.1A removed ServiceEvent.scope_type / district / small_group
    # together with their legacy-scope tooling
    # (audit_service_event_fallback_retirement_readiness,
    # backfill_service_event_audience_scopes,
    # cleanup_service_event_legacy_scope_fields). SERVICE-EVENT-CONTEXT.1C then
    # removed ServiceEvent.ministry_context together with its display tooling
    # (backfill_service_event_host_language_units,
    # cleanup_service_event_ministry_context_labels). None are listed here.
    # ServiceEvent visibility remains ServiceEventAudienceScope rows plus active
    # primary ChurchStructureMembership; zero-row events fail closed. Host /
    # Language display uses ServiceEvent.host_language_unit plus the
    # audience-derived structure fallback.
    (
        "studies.management.commands.audit_bible_study_structure_retirement_readiness",
        "standing diagnostic/audit guard",
    ),
    # BS-MEETING-MIRROR.1A removed BibleStudyMeeting.small_group; the one-time
    # mirror->audience-row backfill (backfill_bible_study_meeting_audience_scopes)
    # derived rows from that FK and was retired with it, so it is no longer listed.
    (
        "studies.management.commands.backfill_bible_study_v2_generation_keys",
        "backfill support for Bible Study V2 generation keys; dry-run by default",
    ),
    # BS-MEETING-MIRROR.1A removed BibleStudyMeeting.small_group together with its
    # guarded cleanup tooling (cleanup_bible_study_v2_small_group_mirrors) and the
    # legacy-vs-membership shadow audit (audit_bible_study_membership_readiness),
    # so neither is listed here.
    (
        "studies.management.commands.audit_bible_study_generation_bridge_retirement",
        "standing diagnostic/audit guard for Bible Study generation bridge retirement",
    ),
    # BS-V1-SCHEMA-RETIRE.1A retires the V1 purge command together with the
    # removed V1 models. Target DB safety now lives in the guarded schema
    # migration preflight.
    (
        "reading.management.commands.audit_reading_structure_runtime_readiness",
        "standing diagnostic/audit guard",
    ),
    # PROFILE-SG-FIELD-RETIRE.1A removed Profile.small_group together with the
    # legacy group-progress shadow diagnostic (audit_group_progress_shadow), which
    # compared the legacy Profile.small_group roster against the membership-core
    # roster, so it is no longer listed here.
    # REFLECTION-MIRROR.1H removed ReflectionComment.small_group_at_post together
    # with the reflection mirror cleanup commands
    # (cleanup_reflection_small_group_mirrors,
    # cleanup_reflection_nongroup_display_mirrors) and the legacy-mirror
    # backfill/recovery/shadow tooling
    # (backfill_reflection_structure_snapshots, cleanup_reflection_snapshot_blockers,
    # audit_reading_privacy_membership_readiness), so they are no longer listed here.
    # PRAYER-MIRROR.1D likewise removed prayers.management.commands.
    # cleanup_prayer_small_group_mirrors together with the
    # PrayerRequest.small_group_at_post field, so it is no longer listed here.
)


def _new_stats():
    return OrderedDict((key, 0) for key in COUNTER_KEYS)


def _new_details():
    return OrderedDict((key, []) for key in DETAIL_KEYS)


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


def _append(details, key, line):
    details[key].append(line)


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

    # PROFILE-SG-FIELD-RETIRE.1A removed Profile.small_group, so profiles are no
    # longer an inbound SmallGroup reference.
    stats["profile_small_group_references"] = 0
    # BS-MEETING-MIRROR.1A removed BibleStudyMeeting.small_group, so the V2
    # meeting is no longer an inbound SmallGroup reference.
    stats["bible_study_v2_meeting_small_group_references"] = 0
    # BS-V1-SCHEMA-RETIRE.1A removes BibleStudySession.small_group, so V1 no
    # longer contributes an active inbound SmallGroup FK blocker after migration.
    stats["bible_study_v1_session_small_group_references"] = 0
    # REFLECTION-MIRROR.1H removed ReflectionComment.small_group_at_post, so the
    # SmallGroup table no longer has any reflection inbound reference to count.
    # SE-FIELD-RETIRE.1A removed ServiceEvent.small_group, so ServiceEvent is no
    # longer an inbound SmallGroup reference either.
    stats["service_event_small_group_references"] = 0
    # BS-SERIES-FIELD-RETIRE.1A removed BibleStudySeries.small_group, so the
    # series is no longer an inbound SmallGroup reference.
    stats["small_group_retirement_blocker_references"] = (
        stats["small_groups_total"]
        + stats["profile_small_group_references"]
        + stats["bible_study_v2_meeting_small_group_references"]
        + stats["bible_study_v1_session_small_group_references"]
        + stats["service_event_small_group_references"]
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

    # LEGACY-PARENT-FK-FIELD-RETIRE.1A removed SmallGroup.district, so the small
    # group is no longer an inbound District reference.
    stats["small_groups_with_district"] = 0
    # SE-FIELD-RETIRE.1A removed ServiceEvent.district, so ServiceEvent is no
    # longer an inbound District reference.
    stats["service_events_with_district"] = 0
    # BS-SERIES-FIELD-RETIRE.1A removed BibleStudySeries.district, so the series
    # is no longer an inbound District reference.
    # BS-V1-SCHEMA-RETIRE.1A removes BibleStudySession.district, so V1 no longer
    # contributes an active inbound District FK blocker after migration.
    stats["bible_study_sessions_with_district"] = 0
    stats["district_retirement_blocker_references"] = (
        stats["districts_total"]
        + stats["small_groups_with_district"]
        + stats["service_events_with_district"]
        + stats["bible_study_sessions_with_district"]
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

    # LEGACY-PARENT-FK-FIELD-RETIRE.1A removed District.ministry_context, so the
    # district is no longer an inbound MinistryContext reference.
    stats["districts_with_ministry_context"] = 0
    # SERVICE-EVENT-CONTEXT.1C removed ServiceEvent.ministry_context and
    # BS-SERIES-FIELD-RETIRE.1A removed BibleStudySeries.ministry_context, so
    # neither FK is a MinistryContext retirement blocker and neither is counted
    # here.
    stats["ministry_context_retirement_blocker_references"] = (
        stats["ministry_contexts_total"]
        + stats["districts_with_ministry_context"]
    )


def _scan_service_events(stats, details, now):
    # SE-FIELD-RETIRE.1A removed ServiceEvent.scope_type / district /
    # small_group. This scan now only measures audience-row readiness and the
    # zero-row fail-closed safety state; there are no legacy scope fields left to
    # count.
    event_ids_with_rows = set(
        ServiceEventAudienceScope.objects.values_list(
            "service_event_id", flat=True
        ).distinct()
    )
    events = ServiceEvent.objects.order_by("id")

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
                    "event_id={event_id} title={title} status={status}".format(
                        event_id=event.id,
                        title=event.title,
                        status=event.status,
                    ),
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

    meeting_ids_with_rows = set(
        BibleStudyMeetingAudienceScope.objects.values_list(
            "meeting_id", flat=True
        ).distinct()
    )
    # BS-MEETING-MIRROR.1A removed BibleStudyMeeting.small_group, so V2 meeting
    # readiness is now audience-row + generation-key only; there is no meeting
    # mirror to count or reconcile.
    meetings = (
        BibleStudyMeeting.objects.select_related("lesson")
        .order_by("id")
    )
    for meeting in meetings:
        stats["bible_study_v2_meetings_checked"] += 1
        has_rows = meeting.id in meeting_ids_with_rows
        if has_rows:
            stats["bible_study_v2_meetings_with_audience_rows"] += 1
        else:
            stats["bible_study_v2_meetings_without_audience_rows"] += 1
            _append(
                details,
                "bible_study_v2_meeting_zero_rows",
                "meeting_id={meeting_id} lesson={lesson}".format(
                    meeting_id=meeting.id,
                    lesson=meeting.lesson.title if meeting.lesson_id else "",
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
                "meeting_id={meeting_id} lesson={lesson}".format(
                    meeting_id=meeting.id,
                    lesson=meeting.lesson.title if meeting.lesson_id else "",
                ),
            )

    # BS-V1-SCHEMA-RETIRE.1A removes V1 BibleStudySession/BibleStudyGuide/
    # BibleStudyWorshipSong models and their tables behind a target-DB migration
    # guard. There are no live V1 ORM counters after the schema slice; any
    # target DB that still has V1 rows must abort during migration preflight.
    stats["bible_study_v1_sessions_checked"] = 0
    stats["bible_study_v1_sessions_with_legacy_scope_fields_set"] = 0
    stats["bible_study_v1_sessions_with_district_id"] = 0
    stats["bible_study_v1_sessions_with_small_group_id"] = 0
    stats["bible_study_v1_guides_checked"] = 0
    stats["bible_study_v1_worship_songs_checked"] = 0
    stats["bible_study_v1_child_rows_purge_pending"] = 0
    stats["bible_study_v1_pilot_records_present"] = 0
    stats["bible_study_v1_app_runtime_retired"] = 1
    stats["bible_study_v1_purge_pending"] = 0
    stats["bible_study_v1_app_runtime_legacy_blockers"] = 0
    stats["bible_study_structure_native_readiness_blockers"] = (
        stats["bible_study_active_series_without_audience_rows"]
        + stats["bible_study_v2_meetings_without_audience_rows"]
        + stats["bible_study_normal_meetings_missing_generation_key"]
    )
    stats["bible_study_legacy_retirement_blockers"] = (
        + stats["bible_study_v1_purge_pending"]
        + stats["bible_study_v1_app_runtime_legacy_blockers"]
    )


def _scan_reflections(stats, details):
    # REFLECTION-MIRROR.1H removed ReflectionComment.small_group_at_post. Ordinary
    # group-reflection visibility is structure-native (CS-CORE.4G.2): it keys off
    # structure_unit_at_post plus active primary ChurchStructureMembership. This
    # scan now measures only structure-snapshot readiness; the legacy mirror and
    # its mirror-vs-snapshot comparison counters were retired with the field.
    comments = (
        ReflectionComment.objects.filter(
            visibility=ReflectionComment.VISIBILITY_GROUP
        )
        .select_related("structure_unit_at_post")
        .order_by("id")
    )
    for comment in comments:
        stats["reflection_group_comments_checked"] += 1
        structure_unit = comment.structure_unit_at_post
        if structure_unit is not None:
            stats["reflection_group_comments_with_structure_unit_at_post"] += 1
        else:
            stats["reflection_group_comments_missing_structure_unit_at_post"] += 1
            _append(
                details,
                "reflection_missing_structure_snapshot",
                f"comment_id={comment.id}",
            )

        if structure_unit is not None and not structure_unit.is_active:
            stats["reflection_group_comments_structure_unit_inactive"] += 1
        if (
            structure_unit is not None
            and structure_unit.unit_type != ChurchStructureUnit.UNIT_SMALL_GROUP
        ):
            stats["reflection_group_comments_structure_unit_wrong_type"] += 1

    stats["reflection_structure_snapshot_readiness_blockers"] = (
        stats["reflection_group_comments_missing_structure_unit_at_post"]
        + stats["reflection_group_comments_structure_unit_inactive"]
        + stats["reflection_group_comments_structure_unit_wrong_type"]
    )


def _scan_roles(stats, details):
    # ROLE-FIELD-RETIRE.1A removed ChurchRoleAssignment.district / small_group.
    # Scoped-role runtime now uses the explicit structure_unit only, so the only
    # remaining role retirement blocker is a non-global scoped assignment that is
    # missing structure_unit (fail-closed).
    assignments = (
        ChurchRoleAssignment.objects.select_related("user", "structure_unit")
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
                _append(
                    details,
                    "role_scoped_assignment_missing_structure_unit",
                    (
                        "assignment_id={assignment_id} username={username} "
                        "role={role} scope_type={scope_type}"
                    ).format(
                        assignment_id=assignment.id,
                        username=assignment.user.get_username(),
                        role=assignment.role,
                        scope_type=assignment.scope_type,
                    ),
                )

    stats["role_scoped_assignments_structure_unit_retirement_blockers"] = (
        stats["role_scoped_assignments_missing_structure_unit"]
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
        "SmallGroup, District, and MinistryContext (Profile.small_group, legacy "
        "ServiceEvent/Bible Study scope fields, reflection legacy snapshots, "
        "and legacy role-scope fields have already been removed). Writes nothing "
        "and has no --apply."
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
        write(
            "legacy_object_row_status: SmallGroup, District, and MinistryContext "
            "rows were purged by the guarded apply; any remaining rows are final "
            "table-retirement blockers, not ordinary-member runtime visibility "
            "blockers."
        )
        write(
            "legacy_object_row_schema_gate: final SmallGroup, District, and "
            "MinistryContext model/table deletion remains a separate guarded "
            "migration slice; do not delete ChurchStructureUnit or runtime "
            "product rows."
        )
        write(
            "legacy_bible_study_v1_status: app runtime/admin are retired; "
            "BibleStudySession, BibleStudyGuide, and BibleStudyWorshipSong are "
            "removed by the guarded BS-V1-SCHEMA-RETIRE.1A migration after "
            "target DB preflight. V1 no longer actively blocks SmallGroup or "
            "District table retirement after that migration is applied."
        )
        write("")
        write("diagnostic/backfill commands (support tooling, not runtime blockers):")
        for command_name, classification in audit["diagnostic_commands"]:
            write(f"  {command_name} - {classification}")

        write("")
        write(
            "Audit only: no ChurchStructureMembership, "
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
