# LEGACY-RETIRE.1A Legacy Church Structure Retirement Execution Plan

## Current Status Summary

LEGACY-RETIRE.1A adds a read-only readiness foundation for retiring the legacy Church Structure compatibility layer. It does not delete fields, tables, models, migrations, routes, forms, templates, admin surfaces, or data. It did not change runtime visibility, permissions, membership, serving, Bible Study, ServiceEvent, reflection, or role behavior. BS-V1-RETIRE.1A later retired legacy V1 `BibleStudySession` from app-level runtime while preserving rows for explicit cleanup. BS-V1-PURGE.1A adds a guarded dry-run-first purge command for V1 pilot rows and V1-only child rows; the command is not automatically run by runtime code. BS-V2-MIRROR.1A later moved V2 Bible Study display labels toward `anchor_unit` / meeting audience units without changing runtime behavior, data, schema, forms, generation, or audience rows. BS-V2-MIRROR.1B later stopped new V2 normal meeting writes from setting `BibleStudyMeeting.small_group`; BS-V2-MIRROR.1C adds a dry-run-first guarded cleanup command for existing mirror values, but no cleanup runs automatically. BS-SERIES-SCOPE.1A stops normal app-level Bible Study schedule create/edit saves from writing legacy `BibleStudySeries.scope_type`, `ministry_context`, `district`, or `small_group`; BS-SERIES-SCOPE.1B added the dry-run-first guarded `cleanup_bible_study_series_legacy_scope_fields` command for existing values. **BS-SERIES-FIELD-RETIRE.1A then removed those four legacy `BibleStudySeries` scope fields** (migration `studies/0010`) after local/dev audit confirmed zero populated legacy scope fields with all series carrying `BibleStudySeriesAudienceScope` rows; normal generation is structure-unit-native and fails closed on zero audience rows, and the now-orphaned `cleanup_bible_study_series_legacy_scope_fields` command was retired with the fields. This did not remove `BibleStudyMeeting.anchor_unit`, `generation_key`, `BibleStudySeriesAudienceScope`, `BibleStudyMeetingAudienceScope`, V1 `BibleStudySession`, or the `SmallGroup` / `District` / `MinistryContext` tables. STRUCTURE-BRIDGE.1A adds the read-only `audit_bible_study_generation_bridge_retirement` inventory: ordinary Bible Study V2 visibility is already audience-row + membership-core, normal generation is already structure-unit-native. **BS-MEETING-MIRROR.1A then removed the legacy `BibleStudyMeeting.small_group` mirror FK** (migration `studies/0011`) after preflight audits confirmed zero populated values and no live runtime/visibility/display/admin/generation dependency; V2 meeting visibility remains `BibleStudyMeetingAudienceScope` rows plus active primary `ChurchStructureMembership`, normal generation stays structure-unit-native via `generation_key` and `anchor_unit`, and display/grouping uses `anchor_unit` and audience rows. The guarded mirror cleanup command (`cleanup_bible_study_v2_small_group_mirrors`), the one-time mirror→audience backfill (`backfill_bible_study_meeting_audience_scopes`), and the legacy-vs-membership shadow audit (`audit_bible_study_membership_readiness`) were retired with the field, and the meeting-mirror counters were removed from the generation-bridge / schema / umbrella retirement audits. This did not remove V1 `BibleStudySession` or the `SmallGroup` / `District` / `MinistryContext` tables. SE-SCOPE.1A stops normal app-level ServiceEvent create/edit and recurring saves from writing legacy `ServiceEvent.scope_type`, `district`, or `small_group`; SE-SCOPE.1B adds the dry-run-first guarded `cleanup_service_event_legacy_scope_fields` command for existing values. SERVICE-EVENT-CONTEXT.1A added an audience-derived Host / Language display fallback for `ServiceEvent.ministry_context` and stopped normal app-level writes to that FK; SERVICE-EVENT-CONTEXT.1B adds display-only `ServiceEvent.host_language_unit`, dry-run-first `backfill_service_event_host_language_units`, and cleanup support so matching legacy FK values can be cleared after the structure-native display context is populated. PROFILE-SG.1B adds the dry-run-first guarded `cleanup_profile_small_group` command for existing `Profile.small_group` values that are already safely represented by a single active primary membership mapped to the same active small-group unit. Safe cleanup only clears ServiceEvent rows with matching structure-native Host / Language display context, series rows that already have valid `BibleStudySeriesAudienceScope` rows, and profile rows whose active primary membership safely represents the same legacy group mapping. Unsafe/mismatched rows remain blocked for review, no cleanup runs automatically, and model-field/DB-constraint cleanup remains separate. **Current state (post-checkpoint):** the field-retirement slices referenced above as "stops writes / adds cleanup" have since completed — `ServiceEvent.scope_type` / `district` / `small_group` (SE-FIELD-RETIRE.1A, `events/0007`), `ServiceEvent.ministry_context` (SERVICE-EVENT-CONTEXT.1C, `events/0008`), `BibleStudySeries.scope_type` / `ministry_context` / `district` / `small_group` (BS-SERIES-FIELD-RETIRE.1A, `studies/0010`), `BibleStudyMeeting.small_group` (BS-MEETING-MIRROR.1A, `studies/0011`), `ChurchRoleAssignment.district` / `small_group` (ROLE-FIELD-RETIRE.1A, `accounts/0011`), `PrayerRequest.small_group_at_post` (PRAYER-MIRROR.1D, `prayers/0004`), `ReflectionComment.small_group_at_post` (REFLECTION-MIRROR.1H, `comments/0007`), and `Profile.small_group` (PROFILE-SG-FIELD-RETIRE.1A, `accounts/0012`) are all removed, each retiring its now-orphaned cleanup/backfill/audit tooling; only immutable historical migrations still name them. **BS-V1-ADMIN-RETIRE.1A** then retired the active V1 Django Admin surface (unregistered `BibleStudySessionAdmin` plus the V1-only `BibleStudyGuideAdmin` / `BibleStudyWorshipSongAdmin` in `studies/admin.py`); this was admin-only — no V1 data was deleted, no V1 model/table/field was removed, and the guarded purge was not applied — so V1 `BibleStudySession` is no longer a display/admin blocker and the schema-retirement audit reclassifies it from `blocked_by_display_or_admin` to `blocked_by_diagnostic_tooling` (purge/audit tooling, test fixtures, immutable historical migrations). **LEGACY-PARENT-FK-FIELD-RETIRE.1A** then removed the now-redundant legacy parent/context FK fields `SmallGroup.district` and `District.ministry_context` (migration `accounts/0013`) after their admin display (LEGACY-OBJECT-ADMIN-FK.1A/1B) and resolver fallback (LEGACY-BRIDGE-RESOLVER-NARROW.1A) reads were already retired and target-DB dry-run confirmed parent/context links already clear (0 present, `data_blocker_count=0`); the guarded `cleanup_legacy_structure_parent_links` command (its only purpose being to clear those two fields before removal) was retired with them, and `seed_church_structure_units` no longer reconstructs the `District` / `SmallGroup` hierarchy from raw legacy links. This did not remove the `SmallGroup` / `District` / `MinistryContext` rows/tables or the `church_structure_unit` mapping FKs. Remaining blockers are the legacy `SmallGroup` / `District` / `MinistryContext` rows/tables, their bridge mapping fields, admin/diagnostic/setup surfaces, and V1 `BibleStudySession` pilot/archive cleanup plus its later model/table/schema removal slice.

New audit command:

```powershell
.venv\Scripts\python.exe manage.py audit_legacy_structure_retirement_readiness
```

Options:

- `--verbose`
- `--limit N`
- `--fail-on-blockers`

The command has no `--apply`, writes nothing, and reports `runtime_mutated: false`, `data_mutated: false`, and `apply_option_present: false`.

Object-row retirement inventory command:

```powershell
.venv\Scripts\python.exe manage.py audit_legacy_structure_object_row_retirement
```

ROW-RETIRE.1A adds this second read-only command for the final legacy
`SmallGroup` / `District` / `MinistryContext` row-retirement decision. It
classifies live consumers into exactly one retirement category, counts the
remaining object rows and their `church_structure_unit` mappings, and prints
capped non-sensitive examples with a final-retirement recommendation. It has
`--verbose`, `--limit N`, and `--fail-on-blockers`; it has no `--apply`, writes
no data, changes no schema, and changes no runtime behavior.

Current local/dev row-retirement state after ServiceEvent Host / Language
cleanup: remaining blockers are the legacy object rows themselves and their
bridge/admin/diagnostic role, not ordinary-member runtime visibility authority.
`ChurchStructureUnit` is the canonical structure tree, and
`ChurchStructureMembership` is the canonical belonging source for migrated
ordinary-member paths. The legacy rows must not be used as ordinary-member
visibility authority. Final table/field deletion is not approved yet.

Schema-retirement preparation inventory command:

```powershell
.venv\Scripts\python.exe manage.py audit_legacy_structure_schema_retirement_readiness
```

LEGACY-SCHEMA-PREP.1A adds this read-only command for field/table retirement
planning. It does not approve or perform field removal, table removal, row
deletion, cleanup applies, runtime behavior changes, or migrations. It reports
each candidate field/table with data counts plus curated live-code reference
categories: runtime, app write, app read, admin, template/display,
diagnostic/cleanup, tests/fixtures, and migration history. Migration references
are reported as historical context only, not live blockers; diagnostic and
cleanup tooling is kept separate from runtime blockers; and the command prints
no private/free-text content.

Current expected schema-prep conclusions are conservative: legacy object tables
remain last, mapping FKs remain until the bridge decision is replaced or
retired, and structure-native fields such as `BibleStudyMeeting.anchor_unit`,
`BibleStudyMeeting.generation_key`, and
`ReflectionComment.structure_unit_at_post` are not legacy-removal targets. The
closest legacy field candidates still require admin/display/diagnostic cleanup
and target-DB dry-run review before any separate schema migration can be
proposed.

**`PrayerRequest.small_group_at_post` has been removed (PRAYER-MIRROR.1D).**
PRAYER-MIRROR.1A stopped the normal app-level writes, 1B added the guarded
dry-run-first `cleanup_prayer_small_group_mirrors` command and the local/dev
apply cleared the stored mirror data blockers, and 1C removed the prayer
display/admin surfaces. With no stored data and no write/display/admin
references left, PRAYER-MIRROR.1D dropped the model field (Django migration
`prayers/0004_remove_prayerrequest_prayers_pra_small_g_c02632_idx_and_more.py`,
which removes the `small_group_at_post` field and its index), retired the
now-orphaned `cleanup_prayer_small_group_mirrors` command and the
`prayers.structure_visibility.resolve_legacy_small_group_mirror` helper, and
reclassified the schema-prep candidate as historical-only (no active blocker).
`PrayerRequest.structure_unit_at_post` plus active primary
`ChurchStructureMembership` remains the canonical and only group-prayer
visibility snapshot. `Profile.small_group` and the legacy `SmallGroup` model no
longer participate in prayer visibility, writes, display, admin, cleanup, or
schema. This was a prayer-only field removal: it does not remove the
`SmallGroup` table and does not affect ServiceEvent, Bible Study, reflection,
role, or profile schema.

**REFLECTION-MIRROR.1G removed the reflection legacy mirror display/admin
surfaces.** It deleted the `templates/reading/passage_wall.html`
`reflection.small_group_at_post` fallback label branch (the passage-wall group
label now relies solely on `structure_unit_at_post`) and the dead display-only
`select_related`/`prefetch_related` references to `small_group_at_post` in
`reading/views.py` (passage reader and passage wall) and `comments/views.py`
(reply/edit/report/staff-reports). `comments.admin.ReflectionCommentAdmin` never
listed or searched the field, so there was no admin surface to remove. The
schema-prep candidate for `ReflectionComment.small_group_at_post` is now
classified as `blocked_by_diagnostic_tooling` (the only remaining live-code
references are the guarded cleanup/diagnostic commands). 1G did **not** remove
the model field, add a migration, change reflection visibility/write semantics,
or delete any cleanup command — field/schema removal remains a separate later
REFLECTION-MIRROR.1H slice. Reflection runtime visibility is unchanged:
`structure_unit_at_post` plus active primary `ChurchStructureMembership`.

**`ReflectionComment.small_group_at_post` has been removed (REFLECTION-MIRROR.1H).**
After REFLECTION-MIRROR.1D stopped the normal app-level writes, 1E/1F cleared the
stored mirror data, and 1G removed the display/read/admin surfaces, 1H dropped the
model field (Django migration
`comments/0007_remove_reflectioncomment_small_group_at_post.py`, which removes the
field and its `(small_group_at_post, scripture_ref_key)` index). The reflection
mirror cleanup commands (`cleanup_reflection_small_group_mirrors`,
`cleanup_reflection_nongroup_display_mirrors`) and the legacy-mirror
backfill/recovery/shadow tooling
(`backfill_reflection_structure_snapshots`, `cleanup_reflection_snapshot_blockers`,
`audit_reading_privacy_membership_readiness`, and the
`reading.reflection_privacy_shadow` helper) were retired with the field, along with
the `comments.reflection_visibility.resolve_legacy_small_group_mirror` helper and
the `GroupReflectionWriteContext.legacy_small_group` attribute. The schema-prep
candidate is reclassified as historical-only and the
`reflection_small_group_at_post` data counter / umbrella mirror counters were
dropped. `ReflectionComment.structure_unit_at_post` plus active primary
`ChurchStructureMembership` remains the canonical and only group-reflection
visibility snapshot. `Profile.small_group` and the legacy `SmallGroup` model no
longer participate in reflection visibility, writes, display, admin, cleanup, or
schema. This was a reflection-only field removal: it does not remove the
`SmallGroup` table and does not affect Prayer, ServiceEvent, Bible Study, role, or
profile schema.

Docs-only later-cleanup note (not changed in this slice): `reading/views.py`
still imports `accounts.models.SmallGroup` although the only remaining reference
is a comment (an unused import that can be dropped in a later tiny cleanup). This
is a code-hygiene item, not a schema blocker, and is intentionally left
untouched here.

Profile legacy group cleanup command (retired — historical note):

`cleanup_profile_small_group` was the dry-run-first guarded command (PROFILE-SG.1B)
for clearing stored `Profile.small_group` values. **It no longer exists.**
PROFILE-SG-FIELD-RETIRE.1A removed the `Profile.small_group` field (migration
`accounts/0012`) and retired the command with it, together with
`audit_structure_belonging`, `backfill_church_structure_memberships`, and
`audit_group_progress_shadow`. `ChurchStructureMembership` is the canonical
belonging source; only immutable historical migrations and docs may still name
the field. There is no profile cleanup command to run.

V1 cleanup command:

```powershell
.venv\Scripts\python.exe manage.py purge_legacy_bible_study_v1_sessions
```

The purge command is dry-run by default. It deletes no V1 rows unless staff explicitly run:

```powershell
.venv\Scripts\python.exe manage.py purge_legacy_bible_study_v1_sessions --apply --confirm-v1-bible-study-retirement
```

Do not run that `--apply` command against the local/dev database during the BS-V1-PURGE.1A implementation task.

V2 generation-key backfill command:

```powershell
.venv\Scripts\python.exe manage.py backfill_bible_study_v2_generation_keys
```

BS-V2-KEY.1A adds this dry-run-first command to backfill structure-native
`generation_key` (`normal-unit:{unit_id}`) and a safe null `anchor_unit` for
existing normal V2 meetings that already have exactly one active small-group
`BibleStudyMeetingAudienceScope` row. It does not change V2 visibility/runtime
behavior, does not delete or alter `small_group`, and does not modify audience
rows. Future apply, when intentionally approved, would be:

```powershell
.venv\Scripts\python.exe manage.py backfill_bible_study_v2_generation_keys --apply
```

For this command, `--limit N` only caps verbose printed examples; it does not
narrow dry-run scan scope or apply scope. Use `--meeting-id` or `--lesson-id` to
intentionally narrow the matching rows.

Do not run that `--apply` command against the local/dev database during the
BS-V2-KEY.1A implementation task. Field/schema cleanup remains later.

Bible Study generation bridge retirement inventory:

```powershell
.venv\Scripts\python.exe manage.py audit_bible_study_generation_bridge_retirement
```

STRUCTURE-BRIDGE.1A adds this read-only command for the remaining V2 generation
/ idempotency bridge decision. It has `--verbose`, `--limit N`, and
`--fail-on-blockers`; it has no `--apply`, writes no data, changes no schema,
and changes no runtime behavior. Its counters distinguish series audience-row
coverage, meeting `generation_key` / `anchor_unit` coverage, meeting audience
rows, static consumer categories, and
`blockers_for_small_group_table_retirement`. (The `BibleStudyMeeting.small_group`
mirror and mirror-to-anchor agreement counters were dropped in BS-MEETING-MIRROR.1A
when that mirror FK was removed.)

The current code state is important: normal V2 generation targets active
small-group `ChurchStructureUnit` leaves and writes `normal-unit:{unit_id}`,
`anchor_unit`, and `BibleStudyMeetingAudienceScope` rows. The legacy
`BibleStudyMeeting.small_group` mirror was removed in BS-MEETING-MIRROR.1A
(migration `studies/0011`), so it is no longer a dependency. Remaining legacy
`SmallGroup` dependencies are compatibility blockers for final table/field
retirement: bridge/admin/diagnostic/setup consumers outside V2 generation and
display. No deletion, field removal, or
replacement bridge is approved by this slice.

Legacy structure parent/context FK fields removed (LEGACY-PARENT-FK-FIELD-RETIRE.1A):

**LEGACY-PARENT-FK-FIELD-RETIRE.1A removed the legacy parent/context FK fields
`SmallGroup.district` and `District.ministry_context`** (migration
`accounts/0013`). They duplicated the canonical `ChurchStructureUnit.parent`
hierarchy and were no longer read by live runtime/admin/display/resolver code
after LEGACY-OBJECT-ADMIN-FK.1A/1B (admin display),
SE-EVENT-LEGACY-WARNING-RETIRE.1A, and LEGACY-BRIDGE-RESOLVER-NARROW.1A
(resolver fallback). Parent/context links were confirmed already clear
(`small_group_district_links_present: 0`,
`district_ministry_context_links_present: 0`, both `data_blocker_count=0`) on
the target DB before removal.

The dry-run-first `cleanup_legacy_structure_parent_links` command — whose only
purpose was to clear these two fields before removal — was retired in the same
slice along with its test module
(`accounts/test_cleanup_legacy_structure_parent_links_command.py`). Only
immutable historical migrations still name the two fields.

This did **not** remove the `SmallGroup` / `District` / `MinistryContext` rows or
tables, the `church_structure_unit` mapping bridge FKs, or any V1
`BibleStudySession` legacy scope field. Ordinary visibility still runs on
audience rows plus active primary `ChurchStructureMembership`, and the retained
`accounts.structure_selectors.resolve_units_to_small_groups()` bridge maps only
through `ChurchStructureUnit` hierarchy descendants and
`SmallGroup.church_structure_unit`.

Seed command after field retirement: `seed_church_structure_units` no longer
reads the removed legacy parent/context FKs and can no longer reconstruct the
`District` / `SmallGroup` hierarchy from raw legacy links. `MinistryContext`
units (whose parent is always the root) are still seeded normally; for already-
mapped `District` / `SmallGroup` rows the existing `ChurchStructureUnit.parent`
and `church_structure_unit` mapping are authoritative and are never reparented.
Unmapped `District` / `SmallGroup` rows are now reported as needing manual
placement (counted as `unreconstructable`) instead of being silently reparented
to an "Unassigned" holding unit; the seed no longer creates
`UNASSIGNED-DISTRICTS` / `UNASSIGNED-GROUPS` buckets for them.

Do not run that `--apply` command against the local/dev database during the
LEGACY-OBJECT-LINKS.1A implementation task. This task does not delete
`SmallGroup`, `District`, or `MinistryContext` rows, does not remove fields, and
only prepares link cleanup where the relationship is already represented by
`ChurchStructureUnit`. Final row/table/field deletion remains a later approved
schema slice.

ServiceEvent Host / Language display FK retirement (SERVICE-EVENT-CONTEXT.1C, complete):

SERVICE-EVENT-CONTEXT.1A kept `ServiceEvent.ministry_context` as stored legacy
display context only and added an audience-derived fallback. SERVICE-EVENT-CONTEXT.1B
added `ServiceEvent.host_language_unit` (structure-native display-only Host /
Language context), stopped normal app-level writes to `ministry_context`, and
added guarded `backfill_service_event_host_language_units` /
`cleanup_service_event_ministry_context_labels` tooling.

SERVICE-EVENT-CONTEXT.1C then **removed** `ServiceEvent.ministry_context`
(migration `events/0008`) after local/dev audit confirmed zero populated
`ministry_context` rows. Host / Language display now uses
`ServiceEvent.host_language_unit` and, when that is blank, derives a safe
fallback from `ServiceEventAudienceScope` units by walking
`ChurchStructureUnit.parent` to the nearest ministry-context unit. Root-audience
events can keep a whole-church audience while displaying an explicit Host /
Language unit. Rows with no stored display unit and no derivable context render
no derived label, and rows spanning multiple derived ministry contexts render a
generic mixed-context label. Neither display field is audience authority, and
neither controls visibility, serving assignments, permissions, required teams,
or TeamAssignment/My Serving behavior.

The display-only cleanup/backfill tooling
(`backfill_service_event_host_language_units`,
`cleanup_service_event_ministry_context_labels`) was retired with the field,
and its references were removed from the umbrella/schema retirement audits.
The normal app-level ServiceEvent create/edit and recurring-create forms do not
expose or save `host_language_unit`; forged POST values are ignored. This slice
did not remove the `MinistryContext` table, `MinistryContext.church_structure_unit`,
`ServiceEvent.host_language_unit`, or `ServiceEventAudienceScope`, and did not
change ServiceEvent audience/runtime semantics; zero-row events remain
fail-closed for ordinary users.

Current runtime split:

- `Profile.small_group` was removed in PROFILE-SG-FIELD-RETIRE.1A (migration `accounts/0012`) after preflight audits confirmed zero populated values and no live runtime/app-write/display/admin dependency. Belonging is `ChurchStructureMembership`; the profile cleanup/belonging-drift/backfill/shadow tooling and the legacy profile selector helpers were retired with the field.
- ServiceEvent ordinary-user visibility no longer uses zero-row legacy fallback; zero-row events are fail-closed safety states. **SE-FIELD-RETIRE.1A removed the legacy `ServiceEvent.scope_type` / `district` / `small_group` fields** (migration `events/0007`) and **SERVICE-EVENT-CONTEXT.1C removed the legacy `ServiceEvent.ministry_context` display FK** (migration `events/0008`); the legacy-scope and display-only backfill/cleanup tooling was retired with those fields. Visibility uses `ServiceEventAudienceScope` rows plus active primary `ChurchStructureMembership`; Host / Language display uses structure-native `ServiceEvent.host_language_unit` plus the audience-derived structure fallback.
- Bible Study V2 meeting visibility, Today/landing, and role/worship pickers use `BibleStudyMeetingAudienceScope` rows plus active primary `ChurchStructureMembership`; display/grouping uses `anchor_unit` / meeting audience units. **BS-MEETING-MIRROR.1A removed the `BibleStudyMeeting.small_group` mirror FK** (migration `studies/0011`) after BS-V2-MIRROR.1A/1B/1C moved display off the mirror, stopped writes, and cleared values; the mirror cleanup command (`cleanup_bible_study_v2_small_group_mirrors`), the mirror→audience backfill (`backfill_bible_study_meeting_audience_scopes`), and the shadow audit (`audit_bible_study_membership_readiness`) were retired with it. V2 meeting identity is structure-native via `generation_key` and `anchor_unit`. Normal V2 schedule saves write `BibleStudySeriesAudienceScope` rows; generation/preview read those audience rows and fail closed with zero rows through `studies.services.resolve_normal_generation_targets()`. BS-SERIES-FIELD-RETIRE.1A removed the legacy `BibleStudySeries.scope_type` / `ministry_context` / `district` / `small_group` fields (migration `studies/0010`), and the `cleanup_bible_study_series_legacy_scope_fields` command was retired with the fields. BS-SMALLGROUP-GENERATION-BRIDGE-RETIRE.1A later removed the dead `BibleStudySeries` eligible-small-groups helper. V1 `BibleStudySession` app runtime is retired after BS-V1-RETIRE.1A and remaining V1 rows are pilot/archive data removable only by the explicit guarded BS-V1-PURGE.1A command.
- Reflection group read/write paths use `ReflectionComment.structure_unit_at_post` plus active primary `ChurchStructureMembership`. **`small_group_at_post` was removed in REFLECTION-MIRROR.1H** (migration `comments/0007`), after 1D stopped the writes, 1E/1F cleared the stored mirror data, and 1G removed the display/read/admin surfaces. The reflection mirror cleanup commands (`cleanup_reflection_small_group_mirrors`, `cleanup_reflection_nongroup_display_mirrors`) and the legacy-mirror backfill/recovery/shadow tooling (`backfill_reflection_structure_snapshots`, `cleanup_reflection_snapshot_blockers`, `audit_reading_privacy_membership_readiness`, `reading.reflection_privacy_shadow`) were retired with the field, along with the `resolve_legacy_small_group_mirror` helper and the `GroupReflectionWriteContext.legacy_small_group` attribute. `Profile.small_group` and the legacy `SmallGroup` model no longer participate in reflection visibility, writes, display, admin, cleanup, or schema. This was a reflection-only field removal; it does not remove the `SmallGroup` table or affect other modules.
- Role runtime scope uses explicit `ChurchRoleAssignment.structure_unit` as the sole scoped-role source. **ROLE-FIELD-RETIRE.1A removed the `ChurchRoleAssignment.district` and `ChurchRoleAssignment.small_group` model fields** (migration `accounts/0011`) after ROLE-RETIRE.1B retired their runtime fallback and local/dev audit confirmed zero populated legacy role fields and zero scoped assignments missing `structure_unit`. The now-orphaned `backfill_structure_role_scopes` command was retired with the fields because its only source no longer exists; `audit_structure_role_scopes` now validates explicit `structure_unit` readiness only. This did not change permissions or group-progress access and did not affect `Profile.small_group`, `SmallGroup`, `District`, `MinistryContext`, ServiceEvent, Bible Study, Reflection, or Prayer schema.
- Prayer group visibility uses `PrayerRequest.structure_unit_at_post` plus active primary `ChurchStructureMembership`. PRAYER-MIRROR.1A–1C stopped the legacy `small_group_at_post` writes, cleared the stored data (local/dev apply of the guarded `cleanup_prayer_small_group_mirrors` command), and removed the display/admin surfaces. **PRAYER-MIRROR.1D removed the `PrayerRequest.small_group_at_post` model field** (migration `prayers/0004`), retired the now-orphaned `cleanup_prayer_small_group_mirrors` command and the `prayers.structure_visibility.resolve_legacy_small_group_mirror` helper, and reclassified the schema-prep candidate as historical-only. `Profile.small_group` and the legacy `SmallGroup` model no longer participate in prayer visibility, writes, display, admin, cleanup, or schema. This was a prayer-only field removal; it does not remove the `SmallGroup` table or affect other modules.

## Code-Level Inventory

Each row is classified into exactly one LEGACY-RETIRE.1A category.

| Consumer / surface | Representative code | Category | Retirement meaning |
| --- | --- | --- | --- |
| Switched ordinary ServiceEvent audience rows | `events.models.ServiceEvent._audience_scope_allows()` | already runtime-retired / historical only | Uses membership-core audience rows; legacy fields are not consulted when rows exist. |
| ServiceEvent zero-row ordinary visibility | `events.models.ServiceEvent.can_be_seen_by()` | already runtime-retired / historical only | Zero-row events fail closed for ordinary users; they are safety states, not legacy ordinary visibility. |
| V1 Bible Study session visibility | `studies.models.BibleStudySession.can_be_seen_by()` | retired app runtime / pilot data pending explicit purge | BS-V1-RETIRE.1A makes app-level V1 visibility fail closed for ordinary users and managers. `Profile.small_group`, `District`, `SmallGroup`, and `scope_type` no longer grant V1 app access. BS-V1-PURGE.1A adds guarded cleanup tooling; runtime code does not run it automatically. |
| Bible Study schedule audience rows | `BibleStudySeriesAudienceScope`; `studies.services.resolve_normal_generation_targets()` | already runtime-retired / historical only | Normal app schedule saves write audience rows only. Generation/preview use those rows and fail closed with zero rows; legacy series scope fields are not a generation source. |
| Bible Study schedule legacy scope fields | `BibleStudySeries.scope_type`, `ministry_context`, `district`, `small_group` | **removed (BS-SERIES-FIELD-RETIRE.1A, migration `studies/0010`)** | The four legacy series scope fields were removed after BS-SERIES-SCOPE.1A/1B stopped writes and cleared values. Normal generation now reads `BibleStudySeriesAudienceScope` rows through structure-native target resolution (empty / fail closed when no rows). The `cleanup_bible_study_series_legacy_scope_fields` command was retired with the fields, and BS-SMALLGROUP-GENERATION-BRIDGE-RETIRE.1A removed the dead eligible-small-groups compatibility helper. Only immutable historical migrations still name these fields. |
| Bible Study V2 meeting `small_group` | `studies.models.BibleStudyMeeting.small_group` (**removed in BS-MEETING-MIRROR.1A**) | removed / historical only | **Removed in BS-MEETING-MIRROR.1A** (migration `studies/0011`) after BS-V2-MIRROR.1A/1B/1C moved display off the mirror, stopped writes, and the guarded cleanup cleared stored values; preflight audits confirmed zero populated values and no live runtime/visibility/display/admin/generation dependency. V2 meeting visibility is `BibleStudyMeetingAudienceScope` rows + active primary `ChurchStructureMembership`; generation/display stay structure-native via `generation_key` / `anchor_unit`. The mirror cleanup command (`cleanup_bible_study_v2_small_group_mirrors`), the mirror→audience backfill (`backfill_bible_study_meeting_audience_scopes`), and the shadow audit (`audit_bible_study_membership_readiness`) were retired with the field. Only immutable historical migrations still name it. |
| Bible Study V2 generation key / anchor readiness | `studies.services.normal_generation_key_for_unit()`, `anchor_unit`, `generation_key`, `backfill_bible_study_v2_generation_keys` | structure-native readiness / diagnostic tooling | Structure-native idempotency is present; BS-V2-KEY.1A adds dry-run-first support to backfill missing safe keys/anchors without changing runtime behavior or audience rows. This is not a legacy `SmallGroup` generation bridge; the `BibleStudyMeeting.small_group` mirror was removed in BS-MEETING-MIRROR.1A. |
| Reflection legacy small-group snapshot | `comments.models.ReflectionComment.small_group_at_post` (**removed in REFLECTION-MIRROR.1H**) | (removed) | **Removed in REFLECTION-MIRROR.1H** (migration `comments/0007`) after 1D stopped writes, 1E/1F cleared stored data, and 1G removed display/read/admin surfaces. The reflection mirror cleanup commands and the legacy-mirror backfill/recovery/shadow tooling were retired with the field. Reflection group visibility is `ReflectionComment.structure_unit_at_post` + active primary `ChurchStructureMembership`. Only immutable historical migrations still name the field; this was a reflection-only field removal and does not remove the `SmallGroup` table. |
| Reflection structure snapshot | `ReflectionComment.structure_unit_at_post` | already runtime-retired / historical only | Canonical group reflection read/write snapshot after CS-CORE.4G.2/4G.3. |
| Prayer legacy small-group mirror | `prayers.models.PrayerRequest` (field removed) | removed / historical only | **Removed in PRAYER-MIRROR.1D.** Ordinary group-prayer visibility uses `PrayerRequest.structure_unit_at_post` plus active primary membership. 1A stopped the write, 1B cleared the stored data via the guarded `cleanup_prayer_small_group_mirrors` command, 1C removed the display/admin surfaces, and 1D dropped the model field (migration `prayers/0004`), retired the `cleanup_prayer_small_group_mirrors` command and the `resolve_legacy_small_group_mirror` helper, and reclassified the schema-prep candidate as historical-only. Prayer-only field removal; the `SmallGroup` table is unaffected. |
| Role legacy scope fields | `ChurchRoleAssignment.district`, `ChurchRoleAssignment.small_group` (fields removed) | removed / historical only | **Removed in ROLE-FIELD-RETIRE.1A** (migration `accounts/0011`). Runtime fallback was already retired in ROLE-RETIRE.1B; only immutable historical migrations still name these fields. |
| Role explicit structure scope | `ChurchRoleAssignment.structure_unit` | already runtime-retired / historical only | Current non-global role runtime scope source; membership is not used to infer role scope. |
| Legacy bridge mappings | `MinistryContext.church_structure_unit`, `District.church_structure_unit`, `SmallGroup.church_structure_unit` | setup/admin/diagnostic bridge | Still needed for setup diagnostics, remaining bridge/admin surfaces, object-row retirement planning, and historical/test compatibility. Normal Bible Study V2 generation is structure-native and no longer depends on these mappings. |
| Legacy object-row retirement inventory | `accounts.management.commands.audit_legacy_structure_object_row_retirement` | diagnostic/audit/backfill/cleanup tooling | Read-only inventory for remaining `SmallGroup`, `District`, and `MinistryContext` rows. It classifies consumers, reports mapped/unmapped/inactive/wrong-type rows, and highlights the `UNASSIGNED-GROUPS` custom-unit placeholder decision without deleting rows or changing schema/runtime behavior. |
| Legacy structure parent/context links | `SmallGroup.district`, `District.ministry_context` (**removed in LEGACY-PARENT-FK-FIELD-RETIRE.1A**) | removed / historical only | **Removed in LEGACY-PARENT-FK-FIELD-RETIRE.1A** (migration `accounts/0013`) after LEGACY-OBJECT-ADMIN-FK.1A/1B retired their admin display and LEGACY-BRIDGE-RESOLVER-NARROW.1A retired the resolver fallback read; target-DB dry-run confirmed 0 links present (`data_blocker_count=0`). The canonical hierarchy is `ChurchStructureUnit.parent` via the `church_structure_unit` mapping bridge. The guarded `cleanup_legacy_structure_parent_links` command (its only purpose being to clear these two fields) was retired with them, and `seed_church_structure_units` no longer reconstructs the `District` / `SmallGroup` hierarchy from raw legacy links. The legacy-parity resolver `resolve_units_to_small_groups()` now maps through `SmallGroup.church_structure_unit` only. Only immutable historical migrations still name these fields; the `SmallGroup` / `District` / `MinistryContext` rows/tables and `church_structure_unit` mapping FKs remain. |
| ServiceEvent Host / Language display | `ServiceEvent.host_language_unit`, `events.templatetags.event_extras.event_host_language_label`, `events.ministry_context_display` | removed / historical only (display now structure-native) | **`ServiceEvent.ministry_context` was removed in SERVICE-EVENT-CONTEXT.1C** (migration `events/0008`). "Host / Language" display now uses structure-native `ServiceEvent.host_language_unit`, then an audience-derived `ChurchStructureUnit.parent` fallback; `host_language_unit` is display-only and does not control audience/visibility. The display-only backfill/cleanup tooling (`backfill_service_event_host_language_units`, `cleanup_service_event_ministry_context_labels`) was retired with the field. This did not remove the `MinistryContext` table, whose row/table retirement remains a later decision. |
| `Profile.small_group` field removal | `accounts.models.Profile.small_group`, `ProfileAdmin` | completed field-level removal | **Done in PROFILE-SG-FIELD-RETIRE.1A** (migration `accounts/0012`). No normal app-level write remained; preflight audits confirmed zero populated values and no live runtime/app-write/display/admin dependency. Belonging is `ChurchStructureMembership`. Staff/admin/template display surfaces, the profile cleanup/belonging-drift/backfill/shadow tooling, and the legacy profile selector helpers were retired with the field. `SmallGroup`/`District`/`MinistryContext` tables were untouched. |
| Staff legacy displays | staff user list, password reset, membership request detail/list, structure map | admin/emergency-maintenance surface | Read-only context only; not runtime authority. The `Profile.small_group` display rows and the profile-vs-membership drift indicators were removed in PROFILE-SG-FIELD-RETIRE.1A. |
| Legacy retirement/audit/backfill/cleanup commands | `audit_structure_role_scopes`, `audit_bible_study_structure_retirement_readiness`, `audit_reading_structure_runtime_readiness`, related backfills/cleanups | diagnostic/audit/backfill/cleanup tooling | Support tooling is intentionally allowed to read legacy fields and does not by itself block runtime retirement. Cleanup tooling is dry-run-first and must not run apply without explicit approval. The reflection mirror cleanup/backfill/recovery/shadow commands were retired in REFLECTION-MIRROR.1H with the `ReflectionComment.small_group_at_post` field. The ServiceEvent legacy-scope tooling was retired in SE-FIELD-RETIRE.1A with the ServiceEvent legacy scope fields. The profile cleanup/belonging-drift/backfill/shadow commands (`cleanup_profile_small_group`, `audit_structure_belonging`, `backfill_church_structure_memberships`, `audit_group_progress_shadow`) were retired in PROFILE-SG-FIELD-RETIRE.1A with the `Profile.small_group` field. |
| ServiceEvent legacy field removal | `ServiceEvent.scope_type`, `district`, `small_group` | completed field-level removal | **Done in SE-FIELD-RETIRE.1A** (migration `events/0007`). SE-RETIRE.1B had already retired the zero-row runtime fallback and local/dev audit confirmed all 37 ServiceEvents have audience rows with zero populated legacy scope fields. Visibility stays `ServiceEventAudienceScope` + active primary `ChurchStructureMembership`; zero-row events fail closed. Admin/display/templatetag surfaces and the legacy-scope cleanup/backfill/fallback-audit tooling were retired with the fields. `ServiceEvent.ministry_context`, `host_language_unit`, `ServiceEventAudienceScope`, and the `SmallGroup`/`District` tables were untouched. |
| Role legacy field removal | `ChurchRoleAssignment.district`, `small_group` | completed field-level removal | **Done in ROLE-FIELD-RETIRE.1A** (migration `accounts/0011`). Runtime was already explicit-structure-only; the `backfill_structure_role_scopes` command was retired with the fields. No permission or group-progress behavior changed. |
| Historical migrations, old docs, stale raw search hits | migrations, superseded docs sections, test fixture setup | not relevant / false positive | Do not treat historical references as current runtime consumers without matching live code. |

## Remaining Blockers by Legacy Object

### `Profile.small_group` — REMOVED (PROFILE-SG-FIELD-RETIRE.1A)

**`Profile.small_group` was removed in PROFILE-SG-FIELD-RETIRE.1A** (migration `accounts/0012`) after preflight audits (`audit_legacy_structure_schema_retirement_readiness`, `audit_legacy_structure_retirement_readiness`, `cleanup_profile_small_group`, `audit_structure_belonging`) confirmed zero populated values, zero `profile_small_group_removal_blockers`, and no live runtime/app-write/display/admin dependency. `ChurchStructureMembership` is the canonical user belonging source for migrated runtime paths; normal app-level membership approval/profile flows do not write any legacy profile group field.

Retired with the field:

- the guarded profile cleanup command `cleanup_profile_small_group` (its target field no longer exists);
- the profile-vs-membership belonging drift audit `audit_structure_belonging` (its sole purpose was that drift);
- the membership backfill `backfill_church_structure_memberships` (its only data source was the removed field);
- the group-progress legacy shadow comparison `audit_group_progress_shadow` plus the shadow functions/dataclasses in `reading.group_progress_shadow` (the membership-core runtime selectors `get_membership_core_progress_roster_users` / `get_membership_core_default_progress_group` remain);
- the legacy `Profile.small_group`-reading selector helpers in `accounts.structure_selectors` (`get_user_legacy_small_group`, `get_user_legacy_structure_unit`, `get_user_legacy_structure_units`, `user_matches_legacy_structure_audience`);
- the profile-vs-membership drift counters in the umbrella/schema retirement audits and the `/staff/structure/` map drift indicators.

This did **not** remove the `SmallGroup`, `District`, or `MinistryContext` tables, and did not affect ServiceEvent, Prayer, Reflection, Role, Bible Study, TeamAssignment, or V1 schema. The schema-prep candidate is now classified historical-only. Only immutable historical migrations still name the field.

### `SmallGroup`

Audit counters include active/inactive rows, mapped/unmapped rows, inactive/wrong-type mapped units, and references from:

- `Profile.small_group` (removed in PROFILE-SG-FIELD-RETIRE.1A; no longer an inbound `SmallGroup` reference)
- `BibleStudyMeeting.small_group` (removed in BS-MEETING-MIRROR.1A; no longer an inbound `SmallGroup` reference)
- V1 `BibleStudySession.small_group`
- `ReflectionComment.small_group_at_post` (removed in REFLECTION-MIRROR.1H; no longer an inbound `SmallGroup` reference)
- `PrayerRequest.small_group_at_post` (removed in PRAYER-MIRROR.1D; no longer an inbound `SmallGroup` reference)
- `ChurchRoleAssignment.small_group` (removed in ROLE-FIELD-RETIRE.1A; no longer an inbound `SmallGroup` reference)
- `ServiceEvent.small_group`
- `BibleStudySeries.small_group` (removed in BS-SERIES-FIELD-RETIRE.1A; no longer an inbound `SmallGroup` reference)

Blockers:

- Existing `SmallGroup` rows and FK references block table retirement.
- `PrayerRequest.small_group_at_post`: **removed in PRAYER-MIRROR.1D.** After 1A stopped the write, 1B cleared the stored data, and 1C removed the admin/display read surfaces, 1D dropped the model field (migration `prayers/0004`), retired the `cleanup_prayer_small_group_mirrors` command and `resolve_legacy_small_group_mirror` helper, and reclassified the schema-prep candidate as historical-only. This inbound `SmallGroup` reference no longer exists. The `SmallGroup` table itself is unaffected by this prayer-only field removal.
- Unmapped/inactive/wrong-type bridge mappings are readiness blockers for any non-lossy migration or final archive step.
- `SmallGroup.district`: **removed in LEGACY-PARENT-FK-FIELD-RETIRE.1A** (migration `accounts/0013`). The legacy parent FK was redundant with `ChurchStructureUnit.parent`; after its admin display and resolver fallback reads were retired and target-DB dry-run confirmed 0 links present, the field was removed and the guarded `cleanup_legacy_structure_parent_links` command was retired with it. This inbound `District` reference no longer exists. The `SmallGroup` rows/table and `church_structure_unit` mapping FK are unaffected.
- ROW-RETIRE.1A separately counts the remaining `SmallGroup` rows as future
  archive candidates when they map to active small-group units, but it does not
  approve deletion. If a dedicated compatibility/mapping model replaces the old
  model rows, migrate that bridge explicitly before dropping the table.

### `District`

Audit counters include active/inactive rows, mapped/unmapped rows, inactive/wrong-type mapped units, and references from:

- `SmallGroup.district` (removed in LEGACY-PARENT-FK-FIELD-RETIRE.1A; no longer an inbound `District` reference)
- `ServiceEvent.district`
- `BibleStudySeries.district` (removed in BS-SERIES-FIELD-RETIRE.1A; no longer an inbound `District` reference)
- V1 `BibleStudySession.district`
- `ChurchRoleAssignment.district` (removed in ROLE-FIELD-RETIRE.1A; no longer an inbound `District` reference)

Blockers:

- Existing rows and FK references block table retirement.
- Wrong/missing bridge mappings block safe bridge-based backfill, audit, or final archive decisions.
- `District.ministry_context`: **removed in LEGACY-PARENT-FK-FIELD-RETIRE.1A** (migration `accounts/0013`). The legacy parent/context FK was redundant with `ChurchStructureUnit.parent`; after its admin display and resolver fallback reads were retired and target-DB dry-run confirmed 0 links present, the field was removed and the guarded `cleanup_legacy_structure_parent_links` command was retired with it. This inbound `MinistryContext` reference no longer exists. The `District` rows/table and `church_structure_unit` mapping FK are unaffected.
- ROW-RETIRE.1A highlights `District #13 未分配小组` mapped to
  `#22 UNASSIGNED-GROUPS` as special handling: the mapped unit is `custom`, not
  `district`, so it is likely a legacy placeholder/holding bucket. Do not
  "fix" this by converting it into a district unit during row inventory. The
  final retirement decision should choose whether to archive/delete the legacy
  row, keep it as an explicit bridge, or replace it with a dedicated
  compatibility/mapping model.

### `MinistryContext`

Audit counters include active/inactive rows, mapped/unmapped rows, inactive/wrong-type mapped units, and references from:

- (`District.ministry_context` was removed in LEGACY-PARENT-FK-FIELD-RETIRE.1A and is no longer a `MinistryContext` inbound reference.)
- (`BibleStudySeries.ministry_context` was removed in BS-SERIES-FIELD-RETIRE.1A and is no longer a `MinistryContext` inbound reference.)
- (`ServiceEvent.ministry_context` was removed in SERVICE-EVENT-CONTEXT.1C and is no longer a `MinistryContext` inbound reference.)

Blockers:

- Existing rows and references block table retirement.
- `District.ministry_context` was removed in LEGACY-PARENT-FK-FIELD-RETIRE.1A (migration `accounts/0013`), removing this inbound `MinistryContext` reference. `ServiceEvent.ministry_context` was removed in SERVICE-EVENT-CONTEXT.1C (migration `events/0008`); Host / Language display now uses structure-native `ServiceEvent.host_language_unit` plus the audience-derived structure fallback, and the display-only backfill/cleanup tooling (`backfill_service_event_host_language_units`, `cleanup_service_event_ministry_context_labels`) was retired with it. The `MinistryContext` rows and table remain.
- ROW-RETIRE.1A counts all remaining `MinistryContext` rows as bridge/admin/
  diagnostic row-retirement blockers until the Host / Language display cleanup,
  mapping bridge, and final table-retirement path are explicitly approved.

### ServiceEvent Legacy Scope Fields — removed (SE-FIELD-RETIRE.1A)

**`ServiceEvent.scope_type` / `district` / `small_group` were removed in SE-FIELD-RETIRE.1A** (migration `events/0007`) after SE-RETIRE.1B retired the zero-row runtime fallback and local/dev audit confirmed all events carry audience rows with zero populated legacy scope fields. The legacy-scope tooling (`cleanup_service_event_legacy_scope_fields`, `backfill_service_event_audience_scopes`, `audit_service_event_fallback_retirement_readiness`) and the umbrella audit's `service_event_*legacy_scope*` counters were retired with the fields.

Current state:

- ServiceEvent visibility is `ServiceEventAudienceScope` rows + active primary `ChurchStructureMembership`.
- Zero-row events fail closed for ordinary users — a safety state, not a legacy fallback (manager/staff override unchanged).
- Only immutable historical migrations still name the legacy scope fields; there is no remaining ServiceEvent legacy-scope field-retirement blocker or cleanup command to run.

### Bible Study Legacy Fields / V1 Sessions / Generation Bridge

Audit counters:

- series with/without audience rows
- active series without audience rows
- V2 meetings with/without audience rows
- normal meetings missing `generation_key`
- normal meetings missing `anchor_unit`
- V1 `BibleStudySession` counts, pilot records present, app-runtime-retired state, and purge-pending rows

(The legacy `BibleStudySeries` scope-field counters were dropped in BS-SERIES-FIELD-RETIRE.1A, and the V2 `BibleStudyMeeting.small_group` mirror / mirror-vs-audience mismatch counters were dropped in BS-MEETING-MIRROR.1A, when those fields were removed.)

Blockers:

- V1 `BibleStudySession` rows are no longer ordinary or manager app-runtime blockers after BS-V1-RETIRE.1A. They remain data/table-retirement blockers until an explicit guarded purge handles the pilot rows and their dependent V1 guide/worship data. After staff run `purge_legacy_bible_study_v1_sessions --apply --confirm-v1-bible-study-retirement` successfully, V1 `BibleStudySession` and V1-only child rows no longer block future V1 field/table cleanup.
- The audit preserves that split: `bible_study_v1_app_runtime_legacy_blockers` remains `0`, while `bible_study_v1_purge_pending` contributes to `bible_study_legacy_retirement_blockers` as a data/table-retirement blocker.
- BS-V1-PURGE.1A does not delete V2 `BibleStudyMeeting` data, does not change V2 behavior, and does not remove V1 models/tables. Schema cleanup remains a later migration slice.
- V2 `BibleStudyMeeting.small_group` was removed in BS-MEETING-MIRROR.1A (migration `studies/0011`); it is no longer a `SmallGroup` inbound reference, a field-removal blocker, or a display/idempotency dependency. V2 meeting identity/idempotency is structure-native via `generation_key` and `anchor_unit`.
- Active series without audience rows, normal meetings without generation keys, and normal meetings without `anchor_unit` are structure-native generation/idempotency readiness blockers, not legacy `SmallGroup` table-retirement blockers. The legacy `BibleStudySeries` scope fields were removed in BS-SERIES-FIELD-RETIRE.1A (migration `studies/0010`) after BS-SERIES-SCOPE.1A/1B stopped writes and cleared values, and the `BibleStudyMeeting.small_group` mirror was removed in BS-MEETING-MIRROR.1A (migration `studies/0011`), so neither is a blocker; the `cleanup_bible_study_series_legacy_scope_fields` and `cleanup_bible_study_v2_small_group_mirrors` commands were retired with them. BS-V2-KEY.1A support can reduce `bible_study_normal_meetings_missing_generation_key` after a separately approved future `--apply` run. The bridge-retirement audits now inventory remaining non-V2 bridge/admin/diagnostic dependencies before final `SmallGroup` table retirement or a replacement compatibility bridge can be planned.

### Reflection Legacy Snapshots

Audit counters (after REFLECTION-MIRROR.1H removed the legacy mirror, these are
structure-snapshot-only; the mirror-vs-snapshot comparison counters were dropped):

- group comments checked
- group comments with `structure_unit_at_post`
- missing structure snapshots
- inactive/wrong-type structure snapshots
- structure-snapshot readiness blockers

Blockers:

- Missing, inactive, or wrong-type structure snapshots are `reflection_structure_snapshot_readiness_blockers`; a group-visible reflection with no valid snapshot is invisible to ordinary viewers (fail-closed).
- REFLECTION-MIRROR.1H removed `ReflectionComment.small_group_at_post`, so there is no longer a legacy mirror to compare against or a `small_group_at_post`-removal blocker.
- (Historical — all retired in REFLECTION-MIRROR.1H.) READING-STRUCT.1B `backfill_reflection_structure_snapshots` resolved missing snapshots whose legacy `small_group_at_post` mapped to an active small-group unit. REFLECTION-SNAPSHOT.1C added the guarded dry-run-first `cleanup_reflection_snapshot_blockers` command (since **retired in REFLECTION-MIRROR.1H**) for the remaining safe missing-snapshot blockers: it backfilled `structure_unit_at_post` for mapped group rows (including hidden/deleted rows) and demoted top-level orphan group rows with no recoverable group identity and no child replies from `group` to `private`. It required `--apply` plus `--confirm-reflection-snapshot-cleanup`, performed no schema migration or runtime source switch, never printed reflection body text, left `small_group_at_post` untouched, and skipped/preserved orphan replies, orphans with replies, and rows with unmapped/inactive/wrong-type legacy mappings.
- (Historical — retired in REFLECTION-MIRROR.1H.) REFLECTION-MIRROR.1D stopped normal app-level writes to `small_group_at_post`. REFLECTION-MIRROR.1E added the complementary guarded dry-run-first `cleanup_reflection_small_group_mirrors` command (since **retired in REFLECTION-MIRROR.1H**) for the *existing* stored mirror values: it sets `small_group_at_post = None` only when clearing cannot change visibility or display — Category A group rows whose `structure_unit_at_post` is non-null, active, a small-group unit, and equal to the mapped legacy unit (group replies only on their own valid snapshot, never inferred from a parent); and Category B non-group rows that carry a `structure_unit_at_post` (so the passage-wall label no longer depends on the legacy mirror). It requires `--apply` plus `--confirm-reflection-small-group-mirror-cleanup`, only ever mutates `small_group_at_post`, performs no schema migration or runtime source switch, never prints reflection body text, and conservatively skips non-group rows with no structure snapshot and group rows with missing/inactive/wrong-type/unmapped/mismatched snapshots. It does not remove the field; field/schema retirement remains a separate later slice and no cleanup runs automatically.
- (Historical — retired in REFLECTION-MIRROR.1H.) REFLECTION-MIRROR.1F added the complementary guarded dry-run-first `cleanup_reflection_nongroup_display_mirrors` command (since **retired in REFLECTION-MIRROR.1H**) for the remaining Category B non-group display-context rows that the 1E command conservatively skipped (those with no `structure_unit_at_post`). For a non-group row (`small_group_at_post` set, `visibility != group`, `structure_unit_at_post` null) whose legacy `small_group_at_post` maps to an active small-group unit, it sets `structure_unit_at_post` to that mapped unit and clears `small_group_at_post`, carrying the passage-wall display label forward onto the structure snapshot while removing the legacy `SmallGroup` FK. It requires `--apply` plus `--confirm-reflection-nongroup-display-mirror-cleanup`, only ever mutates `structure_unit_at_post` and `small_group_at_post`, never changes `visibility`/`parent`/`body`, never prints reflection body text, uses only the row's own mapping (no parent inference for replies), and handles hidden/deleted rows when the mapping is valid. It skips group-visibility rows (owned by `cleanup_reflection_small_group_mirrors`), non-group rows that already carry a structure snapshot, and rows whose legacy mapping is missing/inactive/wrong-type. It does not remove the field; field/schema retirement remains a separate later slice and no cleanup runs automatically.
- REFLECTION-MIRROR.1G removed the remaining normal app display/read and admin surfaces for `small_group_at_post`: the `templates/reading/passage_wall.html` legacy fallback label branch and the dead display-only `select_related`/`prefetch_related` references in `reading/views.py` (passage reader + passage wall) and `comments/views.py` (reply/edit/report/staff-reports). `comments.admin.ReflectionCommentAdmin` never listed or searched the field, so there was no admin surface to remove. The passage-wall group label now relies solely on `structure_unit_at_post`. The field is physically unchanged and is now diagnostic-cleanup-only: the only remaining live-code references are the guarded `cleanup_reflection_small_group_mirrors`, `cleanup_reflection_nongroup_display_mirrors`, and audit tooling, so the schema-prep candidate is reclassified from `blocked_by_display_or_admin` to `blocked_by_diagnostic_tooling`. 1G did not remove the field, add a migration, change reflection visibility/write semantics, or delete any cleanup command. Field/schema removal is a separate later REFLECTION-MIRROR.1H slice.
- **REFLECTION-MIRROR.1H removed the `ReflectionComment.small_group_at_post` model field** (migration `comments/0007_remove_reflectioncomment_small_group_at_post.py`, which drops the field and its `(small_group_at_post, scripture_ref_key)` index). With stored mirror data clear and no live write/display/admin reference left, 1H also retired the reflection mirror cleanup commands (`cleanup_reflection_small_group_mirrors`, `cleanup_reflection_nongroup_display_mirrors`) and the legacy-mirror backfill/recovery/shadow tooling (`backfill_reflection_structure_snapshots`, `cleanup_reflection_snapshot_blockers`, `audit_reading_privacy_membership_readiness`, `reading.reflection_privacy_shadow`), plus the `resolve_legacy_small_group_mirror` helper and the `GroupReflectionWriteContext.legacy_small_group` attribute. The schema-prep candidate is reclassified as historical-only, the `reflection_small_group_at_post` data counter and the umbrella mirror counters (`reflection_group_comments_with_small_group_at_post`, `reflection_group_comments_small_group_unmapped`, `reflection_group_comments_snapshot_mismatch`, `reflection_small_group_at_post_removal_blockers`) were dropped, and `audit_reading_structure_runtime_readiness` now keys its reflection readiness solely off the structure snapshot. 1H changed no reflection visibility/write semantics, deleted no reflection rows, and did not alter `structure_unit_at_post` (only a help_text refresh) or touch the `SmallGroup` table or any other module's schema.

### Prayer Legacy Small-Group Mirror

Status: **`PrayerRequest.small_group_at_post` was removed in PRAYER-MIRROR.1D.**

Summary of the completed slice sequence:

- PRAYER-MIRROR.1A stopped the normal app-level writes; the group-prayer
  create/edit path stamps only the structure-native
  `PrayerRequest.structure_unit_at_post`.
- PRAYER-MIRROR.1B added the guarded dry-run-first
  `cleanup_prayer_small_group_mirrors` command and the local/dev `--apply`
  cleared the stored mirror data blockers.
- PRAYER-MIRROR.1C removed the prayer display `select_related` and the
  `PrayerRequestAdmin` list/search/`list_select_related` surfaces.
- PRAYER-MIRROR.1D removed the model field itself (Django migration
  `prayers/0004_remove_prayerrequest_prayers_pra_small_g_c02632_idx_and_more.py`,
  which removes the `small_group_at_post` field and its index), retired the
  now-orphaned `cleanup_prayer_small_group_mirrors` command and the
  `prayers.structure_visibility.resolve_legacy_small_group_mirror` helper,
  dropped the `prayer_request_small_group_at_post` schema-prep data counter, and
  reclassified the schema-prep candidate as historical-only (no active blocker).

Current state:

- Ordinary group-prayer visibility is structure-native and unchanged:
  `PrayerRequest.structure_unit_at_post` plus the viewer's single active primary
  `ChurchStructureMembership`. Zero-snapshot group prayers fail closed for
  non-owners.
- `Profile.small_group` and the legacy `SmallGroup` model no longer participate
  in prayer visibility, writes, display, admin, cleanup, or schema.
- This was a prayer-only field removal. It does not remove the `SmallGroup`
  table and does not affect ServiceEvent, Bible Study, reflection, role, or
  profile schema. The `cleanup_prayer_small_group_mirrors` command no longer
  exists; it was retired only after the stored data was cleared.

### Role Structure Scope

**ROLE-FIELD-RETIRE.1A removed the `ChurchRoleAssignment.district` and `ChurchRoleAssignment.small_group` fields** (migration `accounts/0011`). Scoped-role runtime now uses explicit `ChurchRoleAssignment.structure_unit` only. The legacy-field counters and the `backfill_structure_role_scopes` command were retired with the fields; `audit_structure_role_scopes` now validates explicit `structure_unit` readiness only.

Audit counters (umbrella audit, `Role structure scope` section):

- `role_assignments_checked`
- `role_scoped_assignments`
- `role_scoped_assignments_with_structure_unit`
- `role_scoped_assignments_missing_structure_unit`
- `role_scoped_assignments_structure_unit_retirement_blockers`

Blockers:

- Any scoped assignment missing explicit `structure_unit` is the only remaining role retirement blocker; runtime already fails closed for such a row. Local/dev audit shows zero.
- There are no longer any legacy `district` / `small_group` role-field counters to query; the schema-retirement audit classifies both removed fields as historical-only.

## Recommended Next Sequence

1. Run the explicit V1 pilot-data purge procedure only when staff intentionally approve it: dry-run `purge_legacy_bible_study_v1_sessions`, review matched rows, then run `purge_legacy_bible_study_v1_sessions --apply --confirm-v1-bible-study-retirement` against the target database. Do not treat this command as ordinary runtime, and do not run `--apply` during the BS-V1-PURGE.1A local/dev implementation task.
2. Complete Bible Study V2 structure-native readiness: active schedules should carry audience rows, and normal meetings should carry audience rows, generation keys, and `anchor_unit`. The legacy `BibleStudySeries` scope fields were removed in BS-SERIES-FIELD-RETIRE.1A (migration `studies/0010`) and the `BibleStudyMeeting.small_group` mirror in BS-MEETING-MIRROR.1A (migration `studies/0011`), so neither requires cleanup and there is no longer a mirror/audience mismatch to drive to zero. Run `backfill_bible_study_v2_generation_keys` in dry-run mode first; apply only when intentionally approved.
3. ServiceEvent legacy scope cleanup is complete: SE-FIELD-RETIRE.1A removed `ServiceEvent.scope_type`, `district`, and `small_group` (migration `events/0007`) after local/dev audit confirmed all ServiceEvents have audience rows with zero populated legacy scope fields. The `cleanup_service_event_legacy_scope_fields`, `backfill_service_event_audience_scopes`, and `audit_service_event_fallback_retirement_readiness` commands were retired with the fields, and the forms/display/admin surfaces no longer reference them. ServiceEvent visibility remains `ServiceEventAudienceScope` + active primary `ChurchStructureMembership`; zero-row events fail closed for ordinary users.
4. Reflection snapshot cleanup is **done/retired**: `ReflectionComment.small_group_at_post` was removed in REFLECTION-MIRROR.1H (migration `comments/0007`), and the guarded `cleanup_reflection_snapshot_blockers`, `cleanup_reflection_small_group_mirrors`, and `cleanup_reflection_nongroup_display_mirrors` commands plus the reflection backfill/recovery/shadow tooling were retired with the field. Reflection group visibility uses `ReflectionComment.structure_unit_at_post` plus active primary `ChurchStructureMembership`. No reflection cleanup command remains to run.
5. Prayer legacy small-group mirror cleanup is **done/retired**: `PrayerRequest.small_group_at_post` was removed in PRAYER-MIRROR.1D (migration `prayers/0004`), and the guarded `cleanup_prayer_small_group_mirrors` command and the `resolve_legacy_small_group_mirror` helper were retired with the field. Prayer group visibility uses `PrayerRequest.structure_unit_at_post` plus active primary `ChurchStructureMembership`. No prayer cleanup command remains to run.
6. Role legacy field retirement is **done** (ROLE-FIELD-RETIRE.1A removed `ChurchRoleAssignment.district` / `small_group`, migration `accounts/0011`). The only remaining role readiness check is that no scoped assignment lacks an explicit valid `structure_unit`; local/dev audit shows zero.
7. `Profile.small_group` cleanup is **done/retired**: the field was removed in PROFILE-SG-FIELD-RETIRE.1A (migration `accounts/0012`), and the guarded `cleanup_profile_small_group` command plus `audit_structure_belonging`, `backfill_church_structure_memberships`, and `audit_group_progress_shadow` were retired with it. `ChurchStructureMembership` is the canonical belonging source. No profile cleanup command remains to run.
8. Legacy parent/context FK field retirement is **done/retired**: the redundant `SmallGroup.district` / `District.ministry_context` parent FKs were removed in LEGACY-PARENT-FK-FIELD-RETIRE.1A (migration `accounts/0013`) after their admin display and resolver fallback reads were retired and target-DB dry-run confirmed 0 links present (`data_blocker_count=0`). The guarded `cleanup_legacy_structure_parent_links` command (its only purpose being to clear those two fields before removal) was retired with them, and `seed_church_structure_units` no longer reconstructs the `District` / `SmallGroup` hierarchy from raw legacy links. No parent-link cleanup command remains to run; only immutable historical migrations still name the two fields. The `SmallGroup` / `District` / `MinistryContext` rows/tables and `church_structure_unit` mapping FKs remain.
9. ServiceEvent Host / Language display retirement is **done/retired**: `ServiceEvent.ministry_context` was removed in SERVICE-EVENT-CONTEXT.1C (migration `events/0008`), and the display-only `backfill_service_event_host_language_units` / `cleanup_service_event_ministry_context_labels` tooling was retired with it. Host / Language display uses structure-native `ServiceEvent.host_language_unit` plus the audience-derived structure fallback. The `MinistryContext` row/table retirement decision remains later (see steps 11–12).
10. Run `audit_legacy_structure_schema_retirement_readiness --verbose --limit 50`
   before proposing any field/table removal. Use it to identify which legacy
   fields are blocked by stored data, app writes, admin/display references,
   diagnostic cleanup tooling, bridge decisions, or only historical migrations.
   This command is schema-removal preparation only; no removal is approved by
   its output.
11. Run `audit_legacy_structure_object_row_retirement --verbose --limit 30`
   before proposing any final row/table action. Use it to decide between:
   archive/delete rows later, keep rows temporarily as the mapping bridge,
   replace bridge fields with a dedicated compatibility/mapping model, or remove
   old models/tables only after all code/admin/backfill/seed dependencies are
   handled. The current recommendation is conservative: keep the rows as a
   bridge until a separate final-retirement slice is approved, and treat
   `UNASSIGNED-GROUPS` as a special placeholder decision.
12. Plan `SmallGroup` / `District` / `MinistryContext` table/field retirement last, after all FK references and bridge consumers are gone or explicitly archived.

## Verification for LEGACY-RETIRE.1A

Run targeted checks only:

```powershell
.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.venv\Scripts\python.exe manage.py check
.venv\Scripts\python.exe manage.py test accounts.test_legacy_structure_retirement_readiness_command.LegacyStructureRetirementReadinessCommandTests -v 2
git diff --check
git diff --stat
git status --short
```

LEGACY-OBJECT-LINKS.1A's `cleanup_legacy_structure_parent_links` command and its
test module were retired in LEGACY-PARENT-FK-FIELD-RETIRE.1A together with the
`SmallGroup.district` / `District.ministry_context` fields, so there is no
longer a parent-link command or test to run.

For ROW-RETIRE.1A, also run:

```powershell
.venv\Scripts\python.exe manage.py test accounts.test_legacy_structure_object_row_retirement_command -v 2
.venv\Scripts\python.exe manage.py audit_legacy_structure_object_row_retirement --verbose --limit 30
```

For LEGACY-SCHEMA-PREP.1A, also run:

```powershell
.venv\Scripts\python.exe manage.py test accounts.test_legacy_structure_schema_retirement_readiness_command -v 2
.venv\Scripts\python.exe manage.py audit_legacy_structure_schema_retirement_readiness --verbose --limit 50
```

For STRUCTURE-BRIDGE.1A, also run:

```powershell
.venv\Scripts\python.exe manage.py test studies.test_bible_study_generation_bridge_retirement_command -v 2
.venv\Scripts\python.exe manage.py audit_bible_study_generation_bridge_retirement --verbose --limit 30
```

Do not run full app suites for this slice unless a later reviewer explicitly asks.
