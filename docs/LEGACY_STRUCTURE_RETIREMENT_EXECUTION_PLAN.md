# LEGACY-RETIRE.1A Legacy Church Structure Retirement Execution Plan

## Current Status Summary

LEGACY-RETIRE.1A adds a read-only readiness foundation for retiring the legacy Church Structure compatibility layer. It does not delete fields, tables, models, migrations, routes, forms, templates, admin surfaces, or data. It did not change runtime visibility, permissions, membership, serving, Bible Study, ServiceEvent, reflection, or role behavior. BS-V1-RETIRE.1A later retired legacy V1 `BibleStudySession` from app-level runtime while preserving rows for explicit cleanup. BS-V1-PURGE.1A adds a guarded dry-run-first purge command for V1 pilot rows and V1-only child rows; the command is not automatically run by runtime code. BS-V2-MIRROR.1A later moved V2 Bible Study display labels toward `anchor_unit` / meeting audience units without changing runtime behavior, data, schema, forms, generation, or audience rows. BS-V2-MIRROR.1B later stopped new V2 normal meeting writes from setting `BibleStudyMeeting.small_group`; BS-V2-MIRROR.1C adds a dry-run-first guarded cleanup command for existing mirror values, but no cleanup runs automatically. BS-SERIES-SCOPE.1A stops normal app-level Bible Study schedule create/edit saves from writing legacy `BibleStudySeries.scope_type`, `ministry_context`, `district`, or `small_group`; BS-SERIES-SCOPE.1B adds the dry-run-first guarded `cleanup_bible_study_series_legacy_scope_fields` command for existing values. SE-SCOPE.1A stops normal app-level ServiceEvent create/edit and recurring saves from writing legacy `ServiceEvent.scope_type`, `district`, or `small_group`; SE-SCOPE.1B adds the dry-run-first guarded `cleanup_service_event_legacy_scope_fields` command for existing values. PROFILE-SG.1B adds the dry-run-first guarded `cleanup_profile_small_group` command for existing `Profile.small_group` values that are already safely represented by a single active primary membership mapped to the same active small-group unit. Safe cleanup only clears ServiceEvent rows that already have `ServiceEventAudienceScope` rows, series rows that already have valid `BibleStudySeriesAudienceScope` rows, and profile rows whose active primary membership safely represents the same legacy group mapping. Unsafe/mismatched rows remain blocked for review, no cleanup runs automatically, and model-field/DB-constraint cleanup remains separate.

New audit command:

```powershell
.venv\Scripts\python.exe manage.py audit_legacy_structure_retirement_readiness
```

Options:

- `--verbose`
- `--limit N`
- `--fail-on-blockers`

The command has no `--apply`, writes nothing, and reports `runtime_mutated: false`, `data_mutated: false`, and `apply_option_present: false`.

Profile legacy group cleanup command:

```powershell
.venv\Scripts\python.exe manage.py cleanup_profile_small_group
```

`cleanup_profile_small_group` is dry-run by default. It does not remove the
`Profile.small_group` field, does not remove `SmallGroup`, does not change
normal profile display, does not change membership requests, and does not run
automatically. Apply requires both explicit flags:

```powershell
.venv\Scripts\python.exe manage.py cleanup_profile_small_group --apply --confirm-profile-small-group-cleanup
```

Do not run that `--apply` command against the local/dev database during the
PROFILE-SG.1B implementation task. Field/schema cleanup remains later.

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

Current runtime split:

- `Profile.small_group` has no normal app-level write path after CS-RETIRE.1A, but remains stored legacy/admin/archive/audit data. PROFILE-SG.1B adds guarded cleanup tooling only; it can clear the field only for rows whose single active primary membership already safely represents the same mapped active small-group unit, and it does not run automatically.
- ServiceEvent ordinary-user visibility no longer uses zero-row legacy fallback; zero-row events are fail-closed safety states, and SE-SCOPE.1A stops normal app-level writes to legacy `scope_type` / `district` / `small_group`. SE-SCOPE.1B adds guarded cleanup tooling for existing stored values, but cleanup is explicit and not automatic.
- Bible Study V2 meeting visibility, Today/landing, and role/worship pickers use `BibleStudyMeetingAudienceScope` rows plus active primary `ChurchStructureMembership`; V2 display labels now prefer `anchor_unit` / meeting audience units after BS-V2-MIRROR.1A, and BS-V2-MIRROR.1B stops new normal meeting writes from setting `BibleStudyMeeting.small_group`. BS-V2-MIRROR.1C adds `cleanup_bible_study_v2_small_group_mirrors`, a dry-run-first command that can clear existing mirrors only when `generation_key`, `anchor_unit`, and exactly one matching active small-group audience row already prove structure-native identity. Normal V2 schedule saves now write `BibleStudySeriesAudienceScope` rows without writing/updating legacy series scope fields; generation/preview read those audience rows and fail closed with zero rows. BS-SERIES-SCOPE.1B adds `cleanup_bible_study_series_legacy_scope_fields`, a dry-run-first command that can clear existing series legacy scope values only when the series already has valid `BibleStudySeriesAudienceScope` rows. Unsafe/mismatched rows remain blocked for review, no cleanup runs automatically, and model-field/DB-constraint cleanup remains a separate migration. V1 `BibleStudySession` app runtime is retired after BS-V1-RETIRE.1A and remaining V1 rows are pilot/archive data removable only by the explicit guarded BS-V1-PURGE.1A command.
- Reflection group read/write paths use `ReflectionComment.structure_unit_at_post` plus active primary `ChurchStructureMembership`; `small_group_at_post` remains a legacy compatibility/staff-display mirror. REFLECTION-MIRROR.1D stops normal app-level writes to `small_group_at_post` (create, reply, and edit-into-group paths leave it null; group→group Policy C edits preserve the existing value without re-stamping it), and the passage-wall group label now prefers `structure_unit_at_post` with legacy `small_group_at_post` fallback only for old rows. It does not clear existing stored values and does not remove the field.
- Role runtime scope uses explicit `ChurchRoleAssignment.structure_unit`; legacy `district` / `small_group` role fields remain stored/admin/display/audit/backfill/rollback context only.

## Code-Level Inventory

Each row is classified into exactly one LEGACY-RETIRE.1A category.

| Consumer / surface | Representative code | Category | Retirement meaning |
| --- | --- | --- | --- |
| Switched ordinary ServiceEvent audience rows | `events.models.ServiceEvent._audience_scope_allows()` | already runtime-retired / historical only | Uses membership-core audience rows; legacy fields are not consulted when rows exist. |
| ServiceEvent zero-row ordinary visibility | `events.models.ServiceEvent.can_be_seen_by()` | already runtime-retired / historical only | Zero-row events fail closed for ordinary users; they are safety states, not legacy ordinary visibility. |
| V1 Bible Study session visibility | `studies.models.BibleStudySession.can_be_seen_by()` | retired app runtime / pilot data pending explicit purge | BS-V1-RETIRE.1A makes app-level V1 visibility fail closed for ordinary users and managers. `Profile.small_group`, `District`, `SmallGroup`, and `scope_type` no longer grant V1 app access. BS-V1-PURGE.1A adds guarded cleanup tooling; runtime code does not run it automatically. |
| Bible Study schedule audience rows | `BibleStudySeriesAudienceScope`; `studies.services.resolve_normal_generation_targets()` | already runtime-retired / historical only | Normal app schedule saves write audience rows only. Generation/preview use those rows and fail closed with zero rows; legacy series scope fields are not a generation source. |
| Bible Study schedule legacy scope fields | `BibleStudySeries.get_eligible_small_groups()`, `BibleStudySeries.scope_type`, `ministry_context`, `district`, `small_group` | stored mirror/history snapshot and audit blocker | Existing values are kept for compatibility/display/coexistence. BS-SERIES-SCOPE.1B adds guarded dry-run-first cleanup for rows that already have valid `BibleStudySeriesAudienceScope` rows; unsafe/mismatched rows stay blocked. Field/table retirement still requires a later schema slice. |
| Bible Study V2 meeting `small_group` | `studies.models.BibleStudyMeeting.small_group` | stored mirror/history snapshot and fallback label | No longer ordinary visibility source and no longer the preferred V2 member/staff display label after BS-V2-MIRROR.1A. BS-V2-MIRROR.1B stops new normal generation/manual-create writes from setting it. BS-V2-MIRROR.1C adds a guarded cleanup command for existing values; it only clears rows with correct structure-native identity already present and does not remove the field or DB constraint. |
| Bible Study V2 generation key / anchor bridge | `studies.services.normal_generation_key_for_unit()`, `anchor_unit`, `generation_key`, `backfill_bible_study_v2_generation_keys` | generation/idempotency bridge | Structure-native idempotency is present; BS-V2-KEY.1A adds dry-run-first support to backfill missing safe keys/anchors without changing runtime behavior, audience rows, or the `small_group` mirror. |
| Reflection legacy small-group snapshot | `comments.models.ReflectionComment.small_group_at_post` | stored mirror/display/history snapshot | No longer grants ordinary group visibility. REFLECTION-MIRROR.1D stops normal app-level writes (create/reply/edit-into-group leave it null; Policy C group→group edits preserve existing values without re-stamping). Existing stored values are untouched; a later guarded cleanup clears them and removal waits for snapshot coverage/mismatch checks. |
| Reflection structure snapshot | `ReflectionComment.structure_unit_at_post` | already runtime-retired / historical only | Canonical group reflection read/write snapshot after CS-CORE.4G.2/4G.3. |
| Role legacy scope fields | `ChurchRoleAssignment.district`, `ChurchRoleAssignment.small_group` | stored mirror/display/history snapshot | Runtime fallback is retired; fields remain display/audit/backfill/rollback context until field-level retirement. |
| Role explicit structure scope | `ChurchRoleAssignment.structure_unit` | already runtime-retired / historical only | Current non-global role runtime scope source; membership is not used to infer role scope. |
| Legacy bridge mappings | `MinistryContext.church_structure_unit`, `District.church_structure_unit`, `SmallGroup.church_structure_unit` | generation/idempotency bridge | Still needed for setup diagnostics, Bible Study resolution/generation, and backfill/audit comparison. |
| `Profile.small_group` stored field | `accounts.models.Profile.small_group`, `ProfileAdmin` | admin/emergency-maintenance surface | No normal app-level write remains, but admin/emergency/archive display remains until full retirement. |
| Staff legacy displays | staff user list, password reset, membership request detail/list, structure map | admin/emergency-maintenance surface | Read-only context only; not runtime authority. |
| Legacy retirement/audit/backfill/cleanup commands | `audit_structure_belonging`, `audit_structure_role_scopes`, `audit_service_event_fallback_retirement_readiness`, `cleanup_service_event_legacy_scope_fields`, `cleanup_profile_small_group`, `cleanup_reflection_snapshot_blockers`, `audit_bible_study_structure_retirement_readiness`, reading/reflection audits, related backfills/cleanups | diagnostic/audit/backfill/cleanup tooling | Support tooling is intentionally allowed to read legacy fields and does not by itself block runtime retirement. Cleanup tooling is dry-run-first and must not run apply without explicit approval. |
| ServiceEvent legacy field removal | `ServiceEvent.scope_type`, `district`, `small_group` | candidate for later field-level removal | SE-SCOPE.1A stops normal app writes, and SE-SCOPE.1B adds guarded cleanup for stored values on rows with audience rows. Remove fields only after cleanup has been reviewed/applied per target DB and rollback, admin forms, displays, and diagnostics have a separate approved plan. |
| Role legacy field removal | `ChurchRoleAssignment.district`, `small_group` | candidate for later field-level removal | Runtime already explicit-structure-only; stored fields still need field-level retirement planning. |
| Historical migrations, old docs, stale raw search hits | migrations, superseded docs sections, test fixture setup | not relevant / false positive | Do not treat historical references as current runtime consumers without matching live code. |

## Remaining Blockers by Legacy Object

### `Profile.small_group`

Audit counters:

- `profiles_checked`
- `profiles_with_small_group`
- `profiles_without_small_group`
- `profiles_with_small_group_and_active_primary_membership`
- `profiles_with_small_group_no_active_primary_membership`
- `profile_membership_unit_matches_group_mapping`
- `profile_membership_unit_mismatch_group_mapping`
- `profile_group_unmapped`
- `multiple_active_primary_memberships`
- `profile_small_group_unrepresented_by_membership_blockers`
- `profile_small_group_removal_blockers`

Blockers:

- Any remaining non-null `Profile.small_group` value blocks simple field removal until an approved archive/removal step exists.
- Missing active primary membership, mismatched mapped unit, unmapped group, or multiple active primary memberships block lossless retirement of the legacy profile field.
- PROFILE-SG.1B adds `cleanup_profile_small_group`, a dry-run-first command that clears only `Profile.small_group` for rows with exactly one active primary membership matching the legacy small group's active small-group structure unit. It does not remove the field/table, does not change normal profile display or membership requests, and does not mutate memberships, structure rows, legacy `SmallGroup`/`District`/`MinistryContext` rows, app data, permissions, serving, runtime behavior, or schema.

### `SmallGroup`

Audit counters include active/inactive rows, mapped/unmapped rows, inactive/wrong-type mapped units, and references from:

- `Profile.small_group`
- `BibleStudyMeeting.small_group`
- V1 `BibleStudySession.small_group`
- `ReflectionComment.small_group_at_post`
- `ChurchRoleAssignment.small_group`
- `ServiceEvent.small_group`
- `BibleStudySeries.small_group`

Blockers:

- Existing `SmallGroup` rows and FK references block table retirement.
- Unmapped/inactive/wrong-type bridge mappings are readiness blockers for any non-lossy migration or final archive step.

### `District`

Audit counters include active/inactive rows, mapped/unmapped rows, inactive/wrong-type mapped units, and references from:

- `SmallGroup.district`
- `ServiceEvent.district`
- `BibleStudySeries.district`
- V1 `BibleStudySession.district`
- `ChurchRoleAssignment.district`

Blockers:

- Existing rows and FK references block table retirement.
- Wrong/missing bridge mappings block safe bridge-based backfill, audit, or final archive decisions.

### `MinistryContext`

Audit counters include active/inactive rows, mapped/unmapped rows, inactive/wrong-type mapped units, and references from:

- `District.ministry_context`
- `ServiceEvent.ministry_context`
- `BibleStudySeries.ministry_context`

Blockers:

- Existing rows and references block table retirement.
- ServiceEvent `ministry_context` is label/context data, not audience authority, but it is still a FK reference that must be handled before table retirement.

### ServiceEvent Legacy Scope Fields

Audit counters:

- `service_events_checked`
- `service_events_with_audience_rows`
- `service_events_without_audience_rows`
- `service_event_zero_row_visible_active_safety_blockers`
- `service_events_with_legacy_scope_type_non_global`
- `service_events_with_legacy_district_set`
- `service_events_with_legacy_small_group_set`
- `service_events_with_any_legacy_scope_field_set`
- `service_event_legacy_scope_field_retirement_blockers`
- `service_event_zero_row_runtime_fallback_active`

Blockers:

- Non-global or populated legacy fields block field-level retirement until guarded cleanup is intentionally run and re-audited. SE-SCOPE.1B adds `cleanup_service_event_legacy_scope_fields`, which is dry-run by default, requires `--apply` plus `--confirm-service-event-legacy-scope-cleanup`, clears only `scope_type` / `district` / `small_group`, skips zero-row blockers, and does not change runtime visibility or schema. Field removal still requires a separate plan for admin forms, displays, backfill diagnostics, rollback, and schema removal.
- Visible/active zero-row events are reported as safety-state blockers: they are not ordinary-user legacy fallback, but they indicate audience-row data that needs review before declaring the path fully clean.

### Bible Study Legacy Fields / V1 Sessions / Generation Bridge

Audit counters:

- series with/without audience rows
- active series without audience rows
- series with legacy scope fields set
- V2 meetings with `small_group` mirror
- V2 meetings with/without audience rows
- V2 mirror/audience mismatches
- normal meetings missing `generation_key`
- V1 `BibleStudySession` counts, legacy scope fields, pilot records present, app-runtime-retired state, and purge-pending rows

Blockers:

- V1 `BibleStudySession` rows are no longer ordinary or manager app-runtime blockers after BS-V1-RETIRE.1A. They remain data/table-retirement blockers until an explicit guarded purge handles the pilot rows and their dependent V1 guide/worship data. After staff run `purge_legacy_bible_study_v1_sessions --apply --confirm-v1-bible-study-retirement` successfully, V1 `BibleStudySession` and V1-only child rows no longer block future V1 field/table cleanup.
- The audit preserves that split: `bible_study_v1_app_runtime_legacy_blockers` remains `0`, while `bible_study_v1_purge_pending` contributes to `bible_study_legacy_retirement_blockers` as a data/table-retirement blocker.
- BS-V1-PURGE.1A does not delete V2 `BibleStudyMeeting` data, does not change V2 behavior, and does not remove V1 models/tables. Schema cleanup remains a later migration slice.
- V2 `BibleStudyMeeting.small_group` remains stored mirror/history/idempotency compatibility and blocks field removal even though it is no longer ordinary visibility authority or the preferred member/staff display label.
- Active series without audience rows, populated `BibleStudySeries` legacy scope fields, and normal meetings without generation keys are generation/idempotency or field-retirement readiness blockers. BS-SERIES-SCOPE.1A stops new normal app schedule saves from adding/updating the legacy series scope blockers. BS-SERIES-SCOPE.1B adds a guarded dry-run-first cleanup command for existing populated series values, but no cleanup runs automatically and unsafe/mismatched rows stay blocked for review. BS-V2-KEY.1A support can reduce `bible_study_normal_meetings_missing_generation_key` after a separately approved future `--apply` run.

### Reflection Legacy Snapshots

Audit counters:

- group comments with `small_group_at_post`
- group comments with `structure_unit_at_post`
- missing structure snapshots
- inactive/wrong-type structure snapshots
- unmapped legacy small-group snapshots
- mismatched legacy-vs-structure snapshots

Blockers:

- Missing, invalid, unmapped, or mismatched snapshots block safe `small_group_at_post` removal.
- Matching legacy snapshots are not runtime authority, but they remain stored staff-display/history context until an approved field-retirement slice.
- READING-STRUCT.1B `backfill_reflection_structure_snapshots` resolves missing snapshots whose legacy `small_group_at_post` maps to an active small-group unit. REFLECTION-SNAPSHOT.1C adds the guarded dry-run-first `cleanup_reflection_snapshot_blockers` command for the remaining safe missing-snapshot blockers: it backfills `structure_unit_at_post` for mapped group rows (including hidden/deleted rows) and demotes top-level orphan group rows with no recoverable group identity and no child replies from `group` to `private`. It requires `--apply` plus `--confirm-reflection-snapshot-cleanup`, performs no schema migration or runtime source switch, never prints reflection body text, leaves `small_group_at_post` untouched, and skips/preserves orphan replies, orphans with replies, and rows with unmapped/inactive/wrong-type legacy mappings. No cleanup runs automatically.

### Role Legacy Fields

Audit counters:

- scoped assignments
- scoped assignments with/missing explicit `structure_unit`
- legacy `district` / `small_group` fields still populated
- mismatch between explicit `structure_unit` and legacy fields

Blockers:

- Any populated legacy role field blocks field-level retirement.
- Any scoped assignment missing explicit `structure_unit` blocks clean retirement even though runtime already fails closed for such a row.
- Mismatch rows need explicit data decision before legacy fields are removed.

## Recommended Next Sequence

1. Run the explicit V1 pilot-data purge procedure only when staff intentionally approve it: dry-run `purge_legacy_bible_study_v1_sessions`, review matched rows, then run `purge_legacy_bible_study_v1_sessions --apply --confirm-v1-bible-study-retirement` against the target database. Do not treat this command as ordinary runtime, and do not run `--apply` during the BS-V1-PURGE.1A local/dev implementation task.
2. Harden Bible Study V2 generation/idempotency bridge: active schedules should carry audience rows, normal meetings should carry audience rows and generation keys, legacy series scope fields should be cleared only by a future guarded cleanup after audit, and mirror/audience mismatches should be zero. Run `backfill_bible_study_v2_generation_keys` in dry-run mode first; apply only when intentionally approved.
3. Run ServiceEvent legacy scope cleanup only when staff intentionally approve it for the target DB: dry-run `cleanup_service_event_legacy_scope_fields`, review zero-row blockers/output, then run `cleanup_service_event_legacy_scope_fields --apply --confirm-service-event-legacy-scope-cleanup` only after explicit approval. Field/schema deprecation remains a later plan covering forms, display, backfill/audit commands, rollback, and zero-row safety-state handling.
4. Run reflection snapshot cleanup only when staff intentionally approve it for the target DB: dry-run `cleanup_reflection_snapshot_blockers`, review the per-row decisions/blockers, then run `cleanup_reflection_snapshot_blockers --apply --confirm-reflection-snapshot-cleanup` only after explicit approval. It backfills mapped group snapshots and demotes safe top-level orphan group rows to private; orphan replies, orphans with replies, and unmapped/inactive/wrong-type rows stay blocked for review. `small_group_at_post` field/schema deprecation remains a later separate plan.
5. Plan role legacy field retirement after confirming no scoped assignment lacks explicit valid `structure_unit` and no legacy-vs-structure mismatch remains.
6. Run `Profile.small_group` cleanup only when staff intentionally approve it for the target DB: dry-run `cleanup_profile_small_group`, review skipped rows/output, then run `cleanup_profile_small_group --apply --confirm-profile-small-group-cleanup` only after explicit approval. Field/schema deprecation remains a later plan covering admin display, fallback/audit references, rollback, and model/table removal.
7. Plan `SmallGroup` / `District` / `MinistryContext` table retirement last, after all FK references and bridge consumers are gone or explicitly archived.

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

Do not run full app suites for this slice unless a later reviewer explicitly asks.
