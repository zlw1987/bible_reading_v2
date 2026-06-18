# LEGACY-RETIRE.1A Legacy Church Structure Retirement Execution Plan

## Current Status Summary

LEGACY-RETIRE.1A adds a read-only readiness foundation for retiring the legacy Church Structure compatibility layer. It does not delete fields, tables, models, migrations, routes, forms, templates, admin surfaces, or data. It does not change runtime visibility, permissions, membership, serving, Bible Study, ServiceEvent, reflection, or role behavior.

New audit command:

```powershell
.venv\Scripts\python.exe manage.py audit_legacy_structure_retirement_readiness
```

Options:

- `--verbose`
- `--limit N`
- `--fail-on-blockers`

The command has no `--apply`, writes nothing, and reports `runtime_mutated: false`, `data_mutated: false`, and `apply_option_present: false`.

Current runtime split:

- `Profile.small_group` has no normal app-level write path after CS-RETIRE.1A, but remains stored legacy/admin/archive/audit data.
- ServiceEvent ordinary-user visibility no longer uses zero-row legacy fallback; zero-row events are fail-closed safety states, while legacy `scope_type` / `district` / `small_group` fields remain stored/editable compatibility data.
- Bible Study V2 meeting visibility, Today/landing, and role/worship pickers use `BibleStudyMeetingAudienceScope` rows plus active primary `ChurchStructureMembership`; V1 `BibleStudySession` remains legacy/archive runtime and retirement work.
- Reflection group read/write paths use `ReflectionComment.structure_unit_at_post` plus active primary `ChurchStructureMembership`; `small_group_at_post` remains a legacy compatibility/staff-display mirror.
- Role runtime scope uses explicit `ChurchRoleAssignment.structure_unit`; legacy `district` / `small_group` role fields remain stored/admin/display/audit/backfill/rollback context only.

## Code-Level Inventory

Each row is classified into exactly one LEGACY-RETIRE.1A category.

| Consumer / surface | Representative code | Category | Retirement meaning |
| --- | --- | --- | --- |
| Switched ordinary ServiceEvent audience rows | `events.models.ServiceEvent._audience_scope_allows()` | already runtime-retired / historical only | Uses membership-core audience rows; legacy fields are not consulted when rows exist. |
| ServiceEvent zero-row ordinary visibility | `events.models.ServiceEvent.can_be_seen_by()` | already runtime-retired / historical only | Zero-row events fail closed for ordinary users; they are safety states, not legacy ordinary visibility. |
| V1 Bible Study session visibility | `studies.models.BibleStudySession.can_be_seen_by()` | current legacy/archive runtime blocker | Still reads `Profile.small_group`, `District`, `SmallGroup`, and `scope_type`; resolve/archive before retiring the compatibility layer. |
| Bible Study schedule legacy scope / generation compatibility | `BibleStudySeries.get_eligible_small_groups()`, `BibleStudySeries.scope_type`, `ministry_context`, `district`, `small_group` | generation/idempotency bridge | Kept to support coexistence and historical scope data while structure audience rows drive the current V2 path. |
| Bible Study V2 meeting `small_group` | `studies.models.BibleStudyMeeting.small_group` | stored mirror/display/history snapshot | No longer ordinary visibility source; still mirror/display/history and secondary compatibility identity. |
| Bible Study V2 generation key / anchor bridge | `studies.services.normal_generation_key_for_unit()`, `anchor_unit`, `generation_key` | generation/idempotency bridge | Structure-native idempotency is present but still coexists with legacy mirrors and pre-bridge meeting recognition. |
| Reflection legacy small-group snapshot | `comments.models.ReflectionComment.small_group_at_post` | stored mirror/display/history snapshot | No longer grants ordinary group visibility; removal waits for snapshot coverage/mismatch checks. |
| Reflection structure snapshot | `ReflectionComment.structure_unit_at_post` | already runtime-retired / historical only | Canonical group reflection read/write snapshot after CS-CORE.4G.2/4G.3. |
| Role legacy scope fields | `ChurchRoleAssignment.district`, `ChurchRoleAssignment.small_group` | stored mirror/display/history snapshot | Runtime fallback is retired; fields remain display/audit/backfill/rollback context until field-level retirement. |
| Role explicit structure scope | `ChurchRoleAssignment.structure_unit` | already runtime-retired / historical only | Current non-global role runtime scope source; membership is not used to infer role scope. |
| Legacy bridge mappings | `MinistryContext.church_structure_unit`, `District.church_structure_unit`, `SmallGroup.church_structure_unit` | generation/idempotency bridge | Still needed for setup diagnostics, Bible Study resolution/generation, and backfill/audit comparison. |
| `Profile.small_group` stored field | `accounts.models.Profile.small_group`, `ProfileAdmin` | admin/emergency-maintenance surface | No normal app-level write remains, but admin/emergency/archive display remains until full retirement. |
| Staff legacy displays | staff user list, password reset, membership request detail/list, structure map | admin/emergency-maintenance surface | Read-only context only; not runtime authority. |
| Legacy retirement/audit/backfill commands | `audit_structure_belonging`, `audit_structure_role_scopes`, `audit_service_event_fallback_retirement_readiness`, `audit_bible_study_structure_retirement_readiness`, reading/reflection audits, related backfills | diagnostic/audit/backfill tooling | Support tooling is intentionally allowed to read legacy fields and does not by itself block runtime retirement. |
| ServiceEvent legacy field removal | `ServiceEvent.scope_type`, `district`, `small_group` | candidate for later field-level removal | Remove only after stored data, rollback, admin forms, and backfill diagnostics have a separate approved plan. |
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

- Non-global or populated legacy fields block field-level retirement until a separate deprecation/removal plan handles admin forms, displays, backfill, rollback, and stored data.
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
- V1 `BibleStudySession` counts and legacy scope fields

Blockers:

- V1 `BibleStudySession` is the main current legacy/archive runtime blocker.
- V2 `BibleStudyMeeting.small_group` remains stored mirror/history/idempotency compatibility and blocks field removal even though it is no longer ordinary visibility authority.
- Active series without audience rows and normal meetings without generation keys are generation/idempotency readiness blockers.

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

1. Resolve/archive V1 `BibleStudySession` remaining legacy/archive runtime dependency.
2. Harden Bible Study V2 generation/idempotency bridge: active schedules should carry audience rows, normal meetings should carry audience rows and generation keys, and mirror/audience mismatches should be zero.
3. Plan ServiceEvent legacy scope field deprecation: stored data, forms, display, backfill/audit commands, rollback, and zero-row safety-state handling.
4. Plan role legacy field retirement after confirming no scoped assignment lacks explicit valid `structure_unit` and no legacy-vs-structure mismatch remains.
5. Plan `Profile.small_group` read-only/removal: use the audit to separate represented values from no-membership, mismatch, unmapped, or multiple-primary blockers.
6. Plan `SmallGroup` / `District` / `MinistryContext` table retirement last, after all FK references and bridge consumers are gone or explicitly archived.

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
