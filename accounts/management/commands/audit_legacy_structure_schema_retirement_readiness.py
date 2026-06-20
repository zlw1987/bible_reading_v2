"""Read-only schema-retirement inventory for legacy Church Structure fields.

LEGACY-SCHEMA-PREP.1A inventories legacy fields/tables before any future
field/table removal proposal. It reports current data counts plus a curated
live-code reference classification so removal planning can distinguish runtime,
write, admin/display, diagnostic cleanup, test/fixture, and migration-history
surfaces.

The command is deliberately read-only. It has no ``--apply`` option, writes no
rows, changes no schema, and changes no runtime behavior.
"""

from collections import Counter, OrderedDict
from copy import deepcopy

from django.core.management.base import BaseCommand, CommandError

from accounts.models import (
    ChurchRoleAssignment,
    District,
    MinistryContext,
    Profile,
    SmallGroup,
)
from comments.models import ReflectionComment
from events.models import ServiceEvent
from prayers.models import PrayerRequest
from studies.models import BibleStudyMeeting, BibleStudySeries, BibleStudySession


STATUS_READY = "ready_for_schema_removal"
STATUS_RUNTIME = "blocked_by_live_runtime"
STATUS_WRITE = "blocked_by_app_write"
STATUS_DISPLAY = "blocked_by_display_or_admin"
STATUS_DATA = "blocked_by_data"
STATUS_DIAGNOSTIC = "blocked_by_diagnostic_tooling"
STATUS_BRIDGE = "blocked_by_bridge_decision"
STATUS_HISTORICAL = "historical_only"

REFERENCE_BUCKETS = (
    "live_runtime_references",
    "app_write_references",
    "app_read_references",
    "admin_references",
    "template_display_references",
    "diagnostic_cleanup_references",
    "test_fixture_references",
    "migration_history_references",
)

STATUS_KEYS = (
    STATUS_READY,
    STATUS_RUNTIME,
    STATUS_WRITE,
    STATUS_DISPLAY,
    STATUS_DATA,
    STATUS_DIAGNOSTIC,
    STATUS_BRIDGE,
    STATUS_HISTORICAL,
)


def _refs(*items):
    return tuple(item for item in items if item)


CANDIDATE_DEFINITIONS = (
    {
        "candidate_name": "Profile.small_group",
        "model_table": "accounts.Profile",
        "field_name": "small_group",
        "candidate_type": "field",
        "app_read_references": _refs(
            "accounts.structure_selectors.get_user_legacy_small_group (diagnostic/helper)",
            "reading.group_progress_shadow legacy comparison baseline",
        ),
        "admin_references": _refs("accounts.admin.ProfileAdmin"),
        "template_display_references": _refs(
            "templates/accounts/staff/user_list.html",
            "templates/accounts/staff/password_reset.html",
            "membership request staff legacy/archive display",
        ),
        "diagnostic_cleanup_references": _refs(
            "audit_structure_belonging",
            "audit_group_progress_shadow",
            "cleanup_profile_small_group",
            "audit_legacy_structure_retirement_readiness",
        ),
        "test_fixture_references": _refs("focused tests create legacy profile fixtures"),
        "migration_history_references": _refs("accounts migrations"),
        "data_counter": "profile_small_group",
        "recommended_next_action": (
            "Keep field until target DB cleanup/audit confirms all stored values "
            "are cleared or explicitly archived; then remove staff/admin/display "
            "surfaces before a separate migration slice."
        ),
        "suggested_removal_phase": "phase 1 then phase 2",
    },
    {
        "candidate_name": "SmallGroup model/table",
        "model_table": "accounts.SmallGroup",
        "field_name": "",
        "candidate_type": "model/table",
        "app_read_references": _refs(
            "accounts.structure_selectors.resolve_units_to_small_groups",
            "studies.services old-row idempotency and mirror lookup",
            "reading group-progress compatibility group lists",
        ),
        "admin_references": _refs("accounts.admin.SmallGroupAdmin"),
        "template_display_references": _refs(
            "reading/group_progress selected group display",
            "Bible Study fallback meeting labels for old rows",
            "reflection legacy fallback labels for old rows",
        ),
        "diagnostic_cleanup_references": _refs(
            "cleanup_profile_small_group",
            "cleanup_bible_study_v2_small_group_mirrors",
            "cleanup_reflection_small_group_mirrors",
            "cleanup_legacy_structure_parent_links",
            "audit_legacy_structure_object_row_retirement",
        ),
        "test_fixture_references": _refs("many focused visibility/cleanup fixtures"),
        "migration_history_references": _refs("accounts/studies/events/comments migrations"),
        "data_counter": "small_group_rows",
        "recommended_next_action": (
            "Do not remove table yet. Keep as bridge/admin/diagnostic context "
            "until all inbound FKs and mapping decisions are retired or replaced."
        ),
        "suggested_removal_phase": "phase 5",
    },
    {
        "candidate_name": "SmallGroup.district",
        "model_table": "accounts.SmallGroup",
        "field_name": "district",
        "candidate_type": "bridge-field",
        "app_read_references": _refs(
            "accounts.structure_selectors.resolve_units_to_small_groups fallback branches",
            "BibleStudySeries.get_eligible_small_groups legacy fallback",
        ),
        "admin_references": _refs("accounts.admin.SmallGroupAdmin"),
        "diagnostic_cleanup_references": _refs(
            "cleanup_legacy_structure_parent_links",
            "seed_church_structure_units historical setup bridge",
        ),
        "test_fixture_references": _refs("legacy structure mapping fixtures"),
        "migration_history_references": _refs("accounts migrations"),
        "data_counter": "small_group_district",
        "recommended_next_action": (
            "Clear only through the guarded parent-link cleanup after dry-run "
            "review; do not remove the field until the bridge resolver and seed "
            "story are retired or replaced."
        ),
        "suggested_removal_phase": "phase 4",
    },
    {
        "candidate_name": "SmallGroup.church_structure_unit",
        "model_table": "accounts.SmallGroup",
        "field_name": "church_structure_unit",
        "candidate_type": "bridge-field",
        "app_read_references": _refs(
            "structure-to-legacy mapping bridge",
            "Bible Study old-row compatibility and diagnostics",
            "profile/reflection cleanup safety checks",
        ),
        "admin_references": _refs("accounts.admin.SmallGroupAdmin"),
        "diagnostic_cleanup_references": _refs(
            "seed_church_structure_units",
            "cleanup_profile_small_group",
            "cleanup_reflection_*",
            "audit_bible_study_generation_bridge_retirement",
        ),
        "test_fixture_references": _refs("mapping bridge fixtures"),
        "migration_history_references": _refs("accounts migrations"),
        "data_counter": "small_group_mapping",
        "recommended_next_action": (
            "Keep until a replacement compatibility/mapping bridge exists or all "
            "legacy object rows and FKs are retired."
        ),
        "suggested_removal_phase": "phase 4 then phase 5",
    },
    {
        "candidate_name": "District model/table",
        "model_table": "accounts.District",
        "field_name": "",
        "candidate_type": "model/table",
        "app_read_references": _refs(
            "legacy hierarchy bridge",
            "ServiceEvent/BibleStudy/role stored context",
        ),
        "admin_references": _refs("accounts.admin.DistrictAdmin"),
        "diagnostic_cleanup_references": _refs(
            "cleanup_legacy_structure_parent_links",
            "audit_legacy_structure_object_row_retirement",
        ),
        "test_fixture_references": _refs("legacy district fixtures"),
        "migration_history_references": _refs("accounts/events/studies migrations"),
        "data_counter": "district_rows",
        "recommended_next_action": (
            "Do not remove table yet. Resolve object rows, inbound FKs, and the "
            "UNASSIGNED-GROUPS placeholder decision first."
        ),
        "suggested_removal_phase": "phase 5",
    },
    {
        "candidate_name": "District.ministry_context",
        "model_table": "accounts.District",
        "field_name": "ministry_context",
        "candidate_type": "bridge-field",
        "app_read_references": _refs(
            "legacy hierarchy fallback for old Bible Study schedule scope",
            "structure mapping diagnostics",
        ),
        "admin_references": _refs("accounts.admin.DistrictAdmin"),
        "diagnostic_cleanup_references": _refs(
            "cleanup_legacy_structure_parent_links",
            "seed_church_structure_units historical setup bridge",
        ),
        "test_fixture_references": _refs("legacy hierarchy fixtures"),
        "migration_history_references": _refs("accounts migrations"),
        "data_counter": "district_ministry_context",
        "recommended_next_action": (
            "Clear only through guarded parent-link cleanup after target DB dry-run "
            "review; field removal waits for bridge/tooling retirement."
        ),
        "suggested_removal_phase": "phase 4",
    },
    {
        "candidate_name": "District.church_structure_unit",
        "model_table": "accounts.District",
        "field_name": "church_structure_unit",
        "candidate_type": "bridge-field",
        "app_read_references": _refs("legacy district to structure mapping bridge"),
        "admin_references": _refs("accounts.admin.DistrictAdmin"),
        "diagnostic_cleanup_references": _refs(
            "seed_church_structure_units",
            "cleanup_legacy_structure_parent_links",
            "backfill_structure_role_scopes diagnostics",
        ),
        "test_fixture_references": _refs("district mapping fixtures"),
        "migration_history_references": _refs("accounts migrations"),
        "data_counter": "district_mapping",
        "recommended_next_action": (
            "Keep until a replacement bridge or final District table retirement "
            "slice is approved."
        ),
        "suggested_removal_phase": "phase 4 then phase 5",
    },
    {
        "candidate_name": "MinistryContext model/table",
        "model_table": "accounts.MinistryContext",
        "field_name": "",
        "candidate_type": "model/table",
        "app_read_references": _refs(
            "ServiceEvent Host / Language legacy display context",
            "legacy Bible Study schedule fallback context",
        ),
        "admin_references": _refs("accounts.admin.MinistryContextAdmin"),
        "diagnostic_cleanup_references": _refs(
            "backfill_service_event_host_language_units",
            "cleanup_service_event_ministry_context_labels",
            "audit_legacy_structure_object_row_retirement",
        ),
        "test_fixture_references": _refs("ministry-context display/cleanup fixtures"),
        "migration_history_references": _refs("accounts/events/studies migrations"),
        "data_counter": "ministry_context_rows",
        "recommended_next_action": (
            "Do not remove table yet. Finish Host / Language display cleanup and "
            "bridge decision first."
        ),
        "suggested_removal_phase": "phase 5",
    },
    {
        "candidate_name": "MinistryContext.church_structure_unit",
        "model_table": "accounts.MinistryContext",
        "field_name": "church_structure_unit",
        "candidate_type": "bridge-field",
        "app_read_references": _refs(
            "ServiceEvent Host / Language backfill bridge",
            "legacy ministry context to structure mapping bridge",
        ),
        "admin_references": _refs("accounts.admin.MinistryContextAdmin"),
        "diagnostic_cleanup_references": _refs(
            "seed_church_structure_units",
            "backfill_service_event_host_language_units",
            "cleanup_service_event_ministry_context_labels",
        ),
        "test_fixture_references": _refs("ministry-context mapping fixtures"),
        "migration_history_references": _refs("accounts/events migrations"),
        "data_counter": "ministry_context_mapping",
        "recommended_next_action": (
            "Keep until ServiceEvent display cleanup and final MinistryContext "
            "row/table retirement are approved."
        ),
        "suggested_removal_phase": "phase 4 then phase 5",
    },
    {
        "candidate_name": "ChurchRoleAssignment.district",
        "model_table": "accounts.ChurchRoleAssignment",
        "field_name": "district",
        "candidate_type": "field",
        "admin_references": _refs("accounts.admin.ChurchRoleAssignmentAdmin"),
        "diagnostic_cleanup_references": _refs(
            "audit_structure_role_scopes diagnostic candidate unit",
            "backfill_structure_role_scopes",
            "audit_legacy_structure_retirement_readiness",
        ),
        "test_fixture_references": _refs("role-scope migration fixtures"),
        "migration_history_references": _refs("accounts migrations"),
        "data_counter": "role_district",
        "recommended_next_action": (
            "Confirm target DB has no populated legacy role fields and retire "
            "admin/display/audit surfaces before field removal."
        ),
        "suggested_removal_phase": "phase 1 then phase 2",
    },
    {
        "candidate_name": "ChurchRoleAssignment.small_group",
        "model_table": "accounts.ChurchRoleAssignment",
        "field_name": "small_group",
        "candidate_type": "field",
        "admin_references": _refs("accounts.admin.ChurchRoleAssignmentAdmin"),
        "diagnostic_cleanup_references": _refs(
            "audit_structure_role_scopes diagnostic candidate unit",
            "backfill_structure_role_scopes",
            "audit_legacy_structure_retirement_readiness",
        ),
        "test_fixture_references": _refs("role-scope migration fixtures"),
        "migration_history_references": _refs("accounts migrations"),
        "data_counter": "role_small_group",
        "recommended_next_action": (
            "Confirm target DB has no populated legacy role fields and retire "
            "admin/display/audit surfaces before field removal."
        ),
        "suggested_removal_phase": "phase 1 then phase 2",
    },
    {
        "candidate_name": "ServiceEvent.scope_type",
        "model_table": "events.ServiceEvent",
        "field_name": "scope_type",
        "candidate_type": "field",
        "app_read_references": _refs("events.templatetags.event_extras legacy label helpers"),
        "admin_references": _refs("events.admin.ServiceEventAdmin"),
        "diagnostic_cleanup_references": _refs(
            "backfill_service_event_audience_scopes",
            "cleanup_service_event_legacy_scope_fields",
            "audit_service_event_fallback_retirement_readiness",
        ),
        "test_fixture_references": _refs("ServiceEvent fallback/cleanup fixtures"),
        "migration_history_references": _refs("events migrations"),
        "data_counter": "service_event_scope_type",
        "recommended_next_action": (
            "Closest after target DB cleanup: no runtime fallback remains, but "
            "stored values, admin/display, and cleanup diagnostics must clear first."
        ),
        "suggested_removal_phase": "phase 1 then phase 3",
    },
    {
        "candidate_name": "ServiceEvent.district",
        "model_table": "events.ServiceEvent",
        "field_name": "district",
        "candidate_type": "field",
        "admin_references": _refs("events.admin.ServiceEventAdmin"),
        "template_display_references": _refs("legacy event context labels"),
        "diagnostic_cleanup_references": _refs(
            "backfill_service_event_audience_scopes",
            "cleanup_service_event_legacy_scope_fields",
            "audit_service_event_fallback_retirement_readiness",
        ),
        "test_fixture_references": _refs("ServiceEvent fallback/cleanup fixtures"),
        "migration_history_references": _refs("events migrations"),
        "data_counter": "service_event_district",
        "recommended_next_action": (
            "Clear stored values only through guarded cleanup after exact target "
            "DB dry-run review; then remove admin/display references."
        ),
        "suggested_removal_phase": "phase 1 then phase 3",
    },
    {
        "candidate_name": "ServiceEvent.small_group",
        "model_table": "events.ServiceEvent",
        "field_name": "small_group",
        "candidate_type": "field",
        "admin_references": _refs("events.admin.ServiceEventAdmin"),
        "template_display_references": _refs("legacy event context labels"),
        "diagnostic_cleanup_references": _refs(
            "backfill_service_event_audience_scopes",
            "cleanup_service_event_legacy_scope_fields",
            "audit_service_event_fallback_retirement_readiness",
        ),
        "test_fixture_references": _refs("ServiceEvent fallback/cleanup fixtures"),
        "migration_history_references": _refs("events migrations"),
        "data_counter": "service_event_small_group",
        "recommended_next_action": (
            "Clear stored values only through guarded cleanup after exact target "
            "DB dry-run review; then remove admin/display references."
        ),
        "suggested_removal_phase": "phase 1 then phase 3",
    },
    {
        "candidate_name": "ServiceEvent.ministry_context",
        "model_table": "events.ServiceEvent",
        "field_name": "ministry_context",
        "candidate_type": "display-field",
        "app_read_references": _refs("events.ministry_context_display display fallback"),
        "admin_references": _refs("events.admin.ServiceEventAdmin"),
        "template_display_references": _refs("event/ministry assignment Host / Language display"),
        "diagnostic_cleanup_references": _refs(
            "backfill_service_event_host_language_units",
            "cleanup_service_event_ministry_context_labels",
        ),
        "test_fixture_references": _refs("Host / Language display cleanup fixtures"),
        "migration_history_references": _refs("events migrations"),
        "data_counter": "service_event_ministry_context",
        "recommended_next_action": (
            "Backfill display-only host_language_unit, run guarded cleanup only "
            "with approval, then remove display/admin references before field removal."
        ),
        "suggested_removal_phase": "phase 2 then phase 3",
    },
    {
        "candidate_name": "ServiceEvent.host_language_unit",
        "model_table": "events.ServiceEvent",
        "field_name": "host_language_unit",
        "candidate_type": "display-field",
        "app_read_references": _refs("events.ministry_context_display structure-native display"),
        "admin_references": _refs("events.admin.ServiceEventAdmin"),
        "template_display_references": _refs("event/ministry assignment Host / Language display"),
        "diagnostic_cleanup_references": _refs("backfill_service_event_host_language_units"),
        "test_fixture_references": _refs("Host / Language display fixtures"),
        "migration_history_references": _refs("events migrations"),
        "data_counter": "service_event_host_language_unit",
        "recommended_next_action": (
            "Keep. This is the structure-native display replacement for legacy "
            "ServiceEvent.ministry_context, not a legacy-removal target now."
        ),
        "suggested_removal_phase": "not in legacy removal sequence",
    },
    {
        "candidate_name": "BibleStudySeries.scope_type",
        "model_table": "studies.BibleStudySeries",
        "field_name": "scope_type",
        "candidate_type": "field",
        "app_read_references": _refs("BibleStudySeries.get_eligible_small_groups zero-row legacy fallback"),
        "admin_references": _refs("studies.admin.BibleStudySeriesAdmin"),
        "diagnostic_cleanup_references": _refs(
            "cleanup_bible_study_series_legacy_scope_fields",
            "audit_bible_study_generation_bridge_retirement",
        ),
        "test_fixture_references": _refs("Bible Study series legacy-scope fixtures"),
        "migration_history_references": _refs("studies migrations"),
        "data_counter": "series_scope_type",
        "recommended_next_action": (
            "Remove only after all target DBs have audience rows, cleanup clears "
            "stored legacy scope values, and fallback/admin diagnostics are retired."
        ),
        "suggested_removal_phase": "phase 1 then phase 3",
    },
    {
        "candidate_name": "BibleStudySeries.ministry_context",
        "model_table": "studies.BibleStudySeries",
        "field_name": "ministry_context",
        "candidate_type": "field",
        "app_read_references": _refs("BibleStudySeries.get_eligible_small_groups legacy fallback"),
        "admin_references": _refs("studies.admin.BibleStudySeriesAdmin"),
        "diagnostic_cleanup_references": _refs(
            "cleanup_bible_study_series_legacy_scope_fields",
            "audit_bible_study_generation_bridge_retirement",
        ),
        "test_fixture_references": _refs("Bible Study series legacy-scope fixtures"),
        "migration_history_references": _refs("studies migrations"),
        "data_counter": "series_ministry_context",
        "recommended_next_action": (
            "Clear through guarded cleanup after target DB dry-run review; remove "
            "fallback/admin/diagnostic references before field removal."
        ),
        "suggested_removal_phase": "phase 1 then phase 3",
    },
    {
        "candidate_name": "BibleStudySeries.district",
        "model_table": "studies.BibleStudySeries",
        "field_name": "district",
        "candidate_type": "field",
        "app_read_references": _refs("BibleStudySeries.get_eligible_small_groups legacy fallback"),
        "admin_references": _refs("studies.admin.BibleStudySeriesAdmin"),
        "diagnostic_cleanup_references": _refs(
            "cleanup_bible_study_series_legacy_scope_fields",
            "audit_bible_study_generation_bridge_retirement",
        ),
        "test_fixture_references": _refs("Bible Study series legacy-scope fixtures"),
        "migration_history_references": _refs("studies migrations"),
        "data_counter": "series_district",
        "recommended_next_action": (
            "Clear through guarded cleanup after target DB dry-run review; remove "
            "fallback/admin/diagnostic references before field removal."
        ),
        "suggested_removal_phase": "phase 1 then phase 3",
    },
    {
        "candidate_name": "BibleStudySeries.small_group",
        "model_table": "studies.BibleStudySeries",
        "field_name": "small_group",
        "candidate_type": "field",
        "app_read_references": _refs("BibleStudySeries.get_eligible_small_groups legacy fallback"),
        "admin_references": _refs("studies.admin.BibleStudySeriesAdmin"),
        "diagnostic_cleanup_references": _refs(
            "cleanup_bible_study_series_legacy_scope_fields",
            "audit_bible_study_generation_bridge_retirement",
        ),
        "test_fixture_references": _refs("Bible Study series legacy-scope fixtures"),
        "migration_history_references": _refs("studies migrations"),
        "data_counter": "series_small_group",
        "recommended_next_action": (
            "Clear through guarded cleanup after target DB dry-run review; remove "
            "fallback/admin/diagnostic references before field removal."
        ),
        "suggested_removal_phase": "phase 1 then phase 3",
    },
    {
        "candidate_name": "BibleStudyMeeting.small_group",
        "model_table": "studies.BibleStudyMeeting",
        "field_name": "small_group",
        "candidate_type": "bridge-field",
        "app_read_references": _refs(
            "old-row idempotency lookup",
            "fallback display when anchor/audience data is missing",
            "forms tolerate legacy small_group URL compatibility",
        ),
        "admin_references": _refs("studies.admin.BibleStudyMeetingAdmin"),
        "template_display_references": _refs("meeting structure label fallback for old rows"),
        "diagnostic_cleanup_references": _refs(
            "cleanup_bible_study_v2_small_group_mirrors",
            "audit_bible_study_generation_bridge_retirement",
        ),
        "test_fixture_references": _refs("V2 old-row compatibility fixtures"),
        "migration_history_references": _refs("studies migrations"),
        "data_counter": "meeting_small_group",
        "recommended_next_action": (
            "Close after safe mirror cleanup and idempotency bridge replacement; "
            "do not remove while fallback display or old-row matching depends on it."
        ),
        "suggested_removal_phase": "phase 4",
    },
    {
        "candidate_name": "BibleStudyMeeting.anchor_unit",
        "model_table": "studies.BibleStudyMeeting",
        "field_name": "anchor_unit",
        "candidate_type": "field",
        "app_write_references": _refs(
            "studies.services.create_meeting_for_generation_target",
            "backfill_bible_study_v2_generation_keys apply mode",
        ),
        "app_read_references": _refs("BibleStudyMeeting.get_structure_display_label"),
        "admin_references": _refs("studies.admin.BibleStudyMeetingAdmin"),
        "template_display_references": _refs("V2 meeting member/staff labels"),
        "diagnostic_cleanup_references": _refs(
            "backfill_bible_study_v2_generation_keys",
            "cleanup_bible_study_v2_small_group_mirrors",
        ),
        "test_fixture_references": _refs("V2 generation/display fixtures"),
        "migration_history_references": _refs("studies migrations"),
        "data_counter": "meeting_anchor_unit",
        "recommended_next_action": (
            "Keep. This is structure-native display/grouping identity and not a "
            "legacy-removal target."
        ),
        "suggested_removal_phase": "not in legacy removal sequence",
    },
    {
        "candidate_name": "BibleStudyMeeting.generation_key",
        "model_table": "studies.BibleStudyMeeting",
        "field_name": "generation_key",
        "candidate_type": "field",
        "app_write_references": _refs(
            "studies.services.create_meeting_for_generation_target",
            "backfill_bible_study_v2_generation_keys apply mode",
        ),
        "app_read_references": _refs("V2 normal generation idempotency lookup"),
        "diagnostic_cleanup_references": _refs(
            "audit_bible_study_generation_bridge_retirement",
            "backfill_bible_study_v2_generation_keys",
        ),
        "test_fixture_references": _refs("V2 generation idempotency fixtures"),
        "migration_history_references": _refs("studies migrations"),
        "data_counter": "meeting_generation_key",
        "recommended_next_action": (
            "Keep. This is structure-native idempotency, not a legacy field."
        ),
        "suggested_removal_phase": "not in legacy removal sequence",
    },
    {
        "candidate_name": "BibleStudySession (V1 model/table and scope fields)",
        "model_table": "studies.BibleStudySession",
        "field_name": "scope_type, district, small_group",
        "candidate_type": "model/table",
        "admin_references": _refs("studies.admin.BibleStudySessionAdmin"),
        "diagnostic_cleanup_references": _refs(
            "purge_legacy_bible_study_v1_sessions",
            "audit_legacy_structure_retirement_readiness",
        ),
        "test_fixture_references": _refs("V1 retirement/purge fixtures"),
        "migration_history_references": _refs("studies migrations"),
        "data_counter": "v1_sessions",
        "recommended_next_action": (
            "Do not migrate V1 to membership-core. Purge pilot/archive rows only "
            "through the guarded V1 purge command, then plan a later schema slice."
        ),
        "suggested_removal_phase": "phase 5",
    },
    {
        "candidate_name": "ReflectionComment.small_group_at_post",
        "model_table": "comments.ReflectionComment",
        "field_name": "small_group_at_post",
        "candidate_type": "display-field",
        "app_read_references": _refs("legacy passage-wall label fallback for old rows"),
        "admin_references": _refs("comments.admin.ReflectionCommentAdmin search/display"),
        "template_display_references": _refs("reading passage-wall legacy fallback label"),
        "diagnostic_cleanup_references": _refs(
            "cleanup_reflection_small_group_mirrors",
            "cleanup_reflection_nongroup_display_mirrors",
            "audit_legacy_structure_retirement_readiness",
        ),
        "test_fixture_references": _refs("reflection snapshot/mirror fixtures"),
        "migration_history_references": _refs("comments migrations"),
        "data_counter": "reflection_small_group_at_post",
        "recommended_next_action": (
            "Clear existing safe mirrors through guarded cleanup, confirm no old "
            "rows still need fallback display, then remove display/admin references."
        ),
        "suggested_removal_phase": "phase 1 then phase 2",
    },
    {
        "candidate_name": "ReflectionComment.structure_unit_at_post",
        "model_table": "comments.ReflectionComment",
        "field_name": "structure_unit_at_post",
        "candidate_type": "field",
        "live_runtime_references": _refs(
            "ReflectionComment.can_be_seen_by group visibility",
            "reading.views passage-wall group filter",
            "comments.reflection_visibility write/read helpers",
        ),
        "app_write_references": _refs("reflection create/reply/edit group write path"),
        "admin_references": _refs("comments.admin.ReflectionCommentAdmin"),
        "template_display_references": _refs("passage-wall preferred group label"),
        "diagnostic_cleanup_references": _refs(
            "backfill_reflection_structure_snapshots",
            "cleanup_reflection_snapshot_blockers",
            "cleanup_reflection_nongroup_display_mirrors",
        ),
        "test_fixture_references": _refs("reflection membership-core fixtures"),
        "migration_history_references": _refs("comments migrations"),
        "data_counter": "reflection_structure_unit_at_post",
        "recommended_next_action": (
            "Keep. This is the canonical structure-native reflection snapshot."
        ),
        "suggested_removal_phase": "not in legacy removal sequence",
    },
    {
        "candidate_name": "PrayerRequest.small_group_at_post",
        "model_table": "prayers.PrayerRequest",
        "field_name": "small_group_at_post",
        "candidate_type": "bridge-field",
        "diagnostic_cleanup_references": _refs(
            "cleanup_prayer_small_group_mirrors "
            "(guarded dry-run-first cleanup of stored mirror values)",
            "prayers.structure_visibility.resolve_legacy_small_group_mirror "
            "(diagnostic/admin/future-cleanup helper, no longer a write path)",
        ),
        "test_fixture_references": _refs(
            "prayer group-visibility / legacy mirror fixtures",
        ),
        "migration_history_references": _refs("prayers migrations"),
        "data_counter": "prayer_request_small_group_at_post",
        "recommended_next_action": (
            "PRAYER-MIRROR.1A stopped the normal app-level write to this legacy "
            "SmallGroup mirror; ordinary group-prayer visibility uses "
            "PrayerRequest.structure_unit_at_post plus active primary membership. "
            "PRAYER-MIRROR.1B added the guarded dry-run-first "
            "cleanup_prayer_small_group_mirrors command and local/dev apply "
            "cleared the remaining stored mirror data blockers. PRAYER-MIRROR.1C "
            "removed the prayers.views display select_related and the "
            "PrayerRequestAdmin list/search/select_related surfaces, so only "
            "guarded cleanup/diagnostic tooling now references the field. Keep "
            "the field physically present until that cleanup/audit tooling is "
            "retired; then remove it in a separate field/table-removal slice."
        ),
        "suggested_removal_phase": "phase 3 then phase 4",
    },
    {
        "candidate_name": "Legacy diagnostic and cleanup command surfaces",
        "model_table": "management commands",
        "field_name": "",
        "candidate_type": "cleanup-tooling-only",
        "diagnostic_cleanup_references": _refs(
            "audit_legacy_structure_retirement_readiness",
            "audit_legacy_structure_object_row_retirement",
            "audit_bible_study_generation_bridge_retirement",
            "cleanup_* guarded dry-run-first commands",
        ),
        "recommended_next_action": (
            "Keep until target DB cleanup/audit passes prove these diagnostics "
            "are no longer needed; retire tooling separately from runtime code."
        ),
        "suggested_removal_phase": "phase 3",
    },
    {
        "candidate_name": "Historical migration references for legacy fields",
        "model_table": "*/migrations",
        "field_name": "",
        "candidate_type": "cleanup-tooling-only",
        "migration_history_references": _refs(
            "accounts/events/studies/comments historical migrations"
        ),
        "recommended_next_action": (
            "Do not treat migrations as live blockers; keep as immutable history."
        ),
        "suggested_removal_phase": "historical only",
    },
)


def _data_counts():
    return {
        "profile_small_group": Profile.objects.filter(
            small_group__isnull=False
        ).count(),
        "small_group_rows": SmallGroup.objects.count(),
        "small_group_district": SmallGroup.objects.filter(
            district__isnull=False
        ).count(),
        "small_group_mapping": SmallGroup.objects.filter(
            church_structure_unit__isnull=False
        ).count(),
        "district_rows": District.objects.count(),
        "district_ministry_context": District.objects.filter(
            ministry_context__isnull=False
        ).count(),
        "district_mapping": District.objects.filter(
            church_structure_unit__isnull=False
        ).count(),
        "ministry_context_rows": MinistryContext.objects.count(),
        "ministry_context_mapping": MinistryContext.objects.filter(
            church_structure_unit__isnull=False
        ).count(),
        "role_district": ChurchRoleAssignment.objects.filter(
            district__isnull=False
        ).count(),
        "role_small_group": ChurchRoleAssignment.objects.filter(
            small_group__isnull=False
        ).count(),
        "service_event_scope_type": ServiceEvent.objects.exclude(
            scope_type=ServiceEvent.SCOPE_GLOBAL
        ).count(),
        "service_event_district": ServiceEvent.objects.filter(
            district__isnull=False
        ).count(),
        "service_event_small_group": ServiceEvent.objects.filter(
            small_group__isnull=False
        ).count(),
        "service_event_ministry_context": ServiceEvent.objects.filter(
            ministry_context__isnull=False
        ).count(),
        "service_event_host_language_unit": ServiceEvent.objects.filter(
            host_language_unit__isnull=False
        ).count(),
        "series_scope_type": BibleStudySeries.objects.exclude(
            scope_type=BibleStudySeries.SCOPE_GLOBAL
        ).count(),
        "series_ministry_context": BibleStudySeries.objects.filter(
            ministry_context__isnull=False
        ).count(),
        "series_district": BibleStudySeries.objects.filter(
            district__isnull=False
        ).count(),
        "series_small_group": BibleStudySeries.objects.filter(
            small_group__isnull=False
        ).count(),
        "meeting_small_group": BibleStudyMeeting.objects.filter(
            small_group__isnull=False
        ).count(),
        "meeting_anchor_unit": BibleStudyMeeting.objects.filter(
            anchor_unit__isnull=False
        ).count(),
        "meeting_generation_key": BibleStudyMeeting.objects.exclude(
            generation_key__isnull=True
        )
        .exclude(generation_key="")
        .count(),
        "v1_sessions": BibleStudySession.objects.count(),
        "reflection_small_group_at_post": ReflectionComment.objects.filter(
            small_group_at_post__isnull=False
        ).count(),
        "reflection_structure_unit_at_post": ReflectionComment.objects.filter(
            structure_unit_at_post__isnull=False
        ).count(),
        "prayer_request_small_group_at_post": PrayerRequest.objects.filter(
            small_group_at_post__isnull=False
        ).count(),
    }


def _status_for(candidate):
    if candidate["live_runtime_references"]:
        return STATUS_RUNTIME
    if candidate["app_write_references"]:
        return STATUS_WRITE
    if candidate["data_blocker_count"]:
        return STATUS_DATA
    if candidate["admin_references"] or candidate["template_display_references"]:
        return STATUS_DISPLAY
    if candidate["diagnostic_cleanup_references"]:
        return STATUS_DIAGNOSTIC
    if candidate["migration_history_references"] and not any(
        candidate[bucket] for bucket in REFERENCE_BUCKETS[:-1]
    ):
        return STATUS_HISTORICAL
    if candidate["candidate_type"] in {"bridge-field", "cleanup-tooling-only"}:
        return STATUS_BRIDGE
    return STATUS_READY


def _candidate_has_blocker(candidate):
    return candidate["schema_removal_status"].startswith("blocked_by_")


def _reference_count(candidate, bucket):
    return len(candidate[bucket])


def run_audit():
    """Run one read-only schema-retirement inventory pass."""
    counts = _data_counts()
    candidates = []

    for definition in CANDIDATE_DEFINITIONS:
        candidate = deepcopy(definition)
        for bucket in REFERENCE_BUCKETS:
            candidate.setdefault(bucket, ())
        data_key = candidate.get("data_counter")
        candidate["data_blocker_count"] = counts.get(data_key, 0)
        candidate["schema_removal_status"] = _status_for(candidate)
        candidates.append(candidate)

    status_counts = Counter(
        candidate["schema_removal_status"] for candidate in candidates
    )
    type_counts = Counter(candidate["candidate_type"] for candidate in candidates)
    for key in STATUS_KEYS:
        status_counts.setdefault(key, 0)

    stats = OrderedDict(
        [
            ("candidate_count", len(candidates)),
            ("blocked_candidate_count", sum(_candidate_has_blocker(c) for c in candidates)),
            ("legacy_ordinary_member_visibility_blockers", 0),
            ("runtime_mutated", False),
            ("data_mutated", False),
            ("schema_mutated", False),
            ("apply_option_present", False),
        ]
    )
    for key in STATUS_KEYS:
        stats[f"{key}_count"] = status_counts[key]
    for candidate_type in sorted(type_counts):
        stats[f"candidate_type_{candidate_type}_count"] = type_counts[candidate_type]

    return {
        "stats": stats,
        "candidates": candidates,
        "data_counts": counts,
    }


def _blocking_items(candidates):
    return [
        (candidate["candidate_name"], candidate["schema_removal_status"])
        for candidate in candidates
        if _candidate_has_blocker(candidate)
    ]


class Command(BaseCommand):
    help = (
        "LEGACY-SCHEMA-PREP.1A read-only inventory for legacy Church Structure "
        "field/table schema-retirement readiness. Writes nothing and has no "
        "--apply option."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--verbose",
            action="store_true",
            help="Print reference lists for each candidate.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Maximum number of references to print per candidate bucket.",
        )
        parser.add_argument(
            "--fail-on-blockers",
            action="store_true",
            help=(
                "Exit nonzero when any schema-removal candidate remains blocked. "
                "Still read-only."
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

        blockers = _blocking_items(audit["candidates"])
        if options["fail_on_blockers"] and blockers:
            raise CommandError(
                "Legacy schema-retirement blockers present "
                "(--fail-on-blockers): "
                + ", ".join(f"{name}={status}" for name, status in blockers)
            )

    def _print_report(self, audit, *, verbose, limit):
        write = self.stdout.write
        stats = audit["stats"]
        candidates = audit["candidates"]

        write(
            "Legacy structure schema-retirement readiness inventory "
            "(LEGACY-SCHEMA-PREP.1A, read-only)"
        )
        write("=" * 88)
        write("schema_removal_preparation_only: true")
        write("field_or_table_removal_approved: false")
        write("runtime_mutated: false")
        write("data_mutated: false")
        write("schema_mutated: false")
        write("apply_option_present: false")
        write("prints_private_free_text: false")
        write("")
        write("summary counters:")
        for key, value in stats.items():
            rendered = str(value).lower() if isinstance(value, bool) else value
            write(f"  {key}: {rendered}")

        write("")
        write("candidate inventory:")
        for candidate in candidates:
            write(
                "  {name}: status={status} type={candidate_type} "
                "data_blocker_count={data_count} phase={phase}".format(
                    name=candidate["candidate_name"],
                    status=candidate["schema_removal_status"],
                    candidate_type=candidate["candidate_type"],
                    data_count=candidate["data_blocker_count"],
                    phase=candidate["suggested_removal_phase"],
                )
            )

        write("")
        write("closest-to-removal candidates:")
        close_candidates = [
            candidate
            for candidate in candidates
            if candidate["schema_removal_status"]
            in {STATUS_READY, STATUS_DISPLAY, STATUS_DIAGNOSTIC}
        ]
        if close_candidates:
            for candidate in close_candidates:
                write(
                    f"  {candidate['candidate_name']} - "
                    f"{candidate['schema_removal_status']}"
                )
        else:
            write("  (none)")

        write("")
        write("recommended removal sequence:")
        write(
            "  1. Clear clean field values only through existing guarded cleanup "
            "commands after target DB dry-run review."
        )
        write("  2. Remove/hide admin and display references for cleared fields.")
        write(
            "  3. Retire diagnostic/backfill/cleanup tooling only after final "
            "target DB audits are clean."
        )
        write(
            "  4. Replace or retire legacy mapping bridges, including "
            "church_structure_unit bridge FKs and resolver dependencies."
        )
        write(
            "  5. Remove legacy object rows/tables last, after all inbound FKs and "
            "bridge decisions are resolved."
        )

        if not verbose:
            return

        write("")
        write("verbose candidate details:")
        for candidate in candidates:
            write(f"{candidate['candidate_name']}:")
            write(f"  model/table: {candidate['model_table']}")
            write(f"  field_name: {candidate['field_name'] or '(model/table)'}")
            write(f"  candidate_type: {candidate['candidate_type']}")
            write(f"  data_blocker_count: {candidate['data_blocker_count']}")
            write(f"  schema_removal_status: {candidate['schema_removal_status']}")
            write(f"  recommended_next_action: {candidate['recommended_next_action']}")
            write(f"  suggested_removal_phase: {candidate['suggested_removal_phase']}")
            for bucket in REFERENCE_BUCKETS:
                rows = candidate[bucket]
                write(f"  {bucket}: {_reference_count(candidate, bucket)}")
                shown = rows if limit is None else rows[:limit]
                if not shown:
                    write("    (none)")
                for row in shown:
                    write(f"    - {row}")
                if limit is not None and len(rows) > len(shown):
                    write(
                        f"    (stopped at --limit {limit}; "
                        f"{len(rows) - len(shown)} more)"
                    )
