# LEGACY-RETIRE.1A Legacy Church Structure Retirement Execution Plan

## Current Status Summary

LEGACY-RETIRE.1A adds a read-only readiness foundation for retiring the legacy Church Structure compatibility layer. It does not delete fields, tables, models, migrations, routes, forms, templates, admin surfaces, or data. It did not change runtime visibility, permissions, membership, serving, Bible Study, ServiceEvent, reflection, or role behavior. BS-V1-RETIRE.1A later retired legacy V1 `BibleStudySession` from app-level runtime while preserving rows for explicit cleanup. BS-V1-PURGE.1A adds a guarded dry-run-first purge command for V1 pilot rows and V1-only child rows; the command is not automatically run by runtime code. BS-V2-MIRROR.1A later moved V2 Bible Study display labels toward `anchor_unit` / meeting audience units without changing runtime behavior, data, schema, forms, generation, or audience rows. BS-V2-MIRROR.1B later stopped new V2 normal meeting writes from setting `BibleStudyMeeting.small_group`; BS-V2-MIRROR.1C adds a dry-run-first guarded cleanup command for existing mirror values, but no cleanup runs automatically. BS-SERIES-SCOPE.1A stops normal app-level Bible Study schedule create/edit saves from writing legacy `BibleStudySeries.scope_type`, `ministry_context`, `district`, or `small_group`; BS-SERIES-SCOPE.1B adds the dry-run-first guarded `cleanup_bible_study_series_legacy_scope_fields` command for existing values. STRUCTURE-BRIDGE.1A adds the read-only `audit_bible_study_generation_bridge_retirement` inventory: ordinary Bible Study V2 visibility is already audience-row + membership-core, normal generation is already structure-unit-native, and the remaining legacy `SmallGroup` dependencies are old-row idempotency, stored mirrors, fallback display, admin, and diagnostic/cleanup support. SE-SCOPE.1A stops normal app-level ServiceEvent create/edit and recurring saves from writing legacy `ServiceEvent.scope_type`, `district`, or `small_group`; SE-SCOPE.1B adds the dry-run-first guarded `cleanup_service_event_legacy_scope_fields` command for existing values. SERVICE-EVENT-CONTEXT.1A added an audience-derived Host / Language display fallback for `ServiceEvent.ministry_context` and stopped normal app-level writes to that FK; SERVICE-EVENT-CONTEXT.1B adds display-only `ServiceEvent.host_language_unit`, dry-run-first `backfill_service_event_host_language_units`, and cleanup support so matching legacy FK values can be cleared after the structure-native display context is populated. PROFILE-SG.1B adds the dry-run-first guarded `cleanup_profile_small_group` command for existing `Profile.small_group` values that are already safely represented by a single active primary membership mapped to the same active small-group unit. Safe cleanup only clears ServiceEvent rows with matching structure-native Host / Language display context, series rows that already have valid `BibleStudySeriesAudienceScope` rows, and profile rows whose active primary membership safely represents the same legacy group mapping. Unsafe/mismatched rows remain blocked for review, no cleanup runs automatically, and model-field/DB-constraint cleanup remains separate.

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

Bible Study generation bridge retirement inventory:

```powershell
.venv\Scripts\python.exe manage.py audit_bible_study_generation_bridge_retirement
```

STRUCTURE-BRIDGE.1A adds this read-only command for the remaining V2 generation
/ idempotency bridge decision. It has `--verbose`, `--limit N`, and
`--fail-on-blockers`; it has no `--apply`, writes no data, changes no schema,
and changes no runtime behavior. Its counters distinguish series audience-row
coverage, legacy series scope fields, meeting `generation_key` / `anchor_unit`
coverage, meeting audience rows, `BibleStudyMeeting.small_group` mirrors,
mirror-to-anchor mapping agreement, static consumer categories, and
`blockers_for_small_group_table_retirement`.

The current code state is important: normal V2 generation now targets active
small-group `ChurchStructureUnit` leaves, writes `normal-unit:{unit_id}`,
`anchor_unit`, and `BibleStudyMeetingAudienceScope` rows, and leaves the legacy
`small_group` mirror unset for new normal generated rows. Remaining legacy
`SmallGroup` dependencies are compatibility blockers for final table/field
retirement: old-row idempotency matching, stored mirrors, fallback display,
admin maintenance, and diagnostic/backfill/cleanup tooling. No deletion,
field removal, mirror cleanup, or replacement bridge is approved by this slice.

Legacy structure parent/context link cleanup command:

```powershell
.venv\Scripts\python.exe manage.py cleanup_legacy_structure_parent_links
```

LEGACY-OBJECT-LINKS.1A adds this dry-run-first command. It clears legacy
parent/context FK links that are already fully represented by the
`ChurchStructureUnit` hierarchy:

- `SmallGroup.district` → `None`, and
- `District.ministry_context` → `None`.

A link is cleared only when both the child and parent legacy objects map to
active `ChurchStructureUnit` rows of the expected unit types and the child
unit's `parent` already equals the parent legacy object's mapped unit (so
`ChurchStructureUnit.parent` already proves the same relationship). Links whose
mapping is missing, inactive, wrong-type, or whose hierarchy parent does not
match are skipped and reported. Both target FKs were verified nullable before
implementation; a non-nullable target would be detected, reported via
`skipped_not_nullable`, and left untouched.

`ServiceEvent.ministry_context` is **not** cleared by this command. It is a
staff/member "Host / Language Label" surfaced in the event detail/list and
ministry assignment detail/list displays, not pure hierarchy redundancy, so
those rows are reported and conservatively skipped
(`skipped_service_event_uncertain_display_context`). SERVICE-EVENT-CONTEXT.1B
now handles that FK separately with structure-native `host_language_unit`
display context, stopped normal app-level writes, and the guarded
`backfill_service_event_host_language_units` /
`cleanup_service_event_ministry_context_labels` command sequence.

Apply requires both explicit flags:

```powershell
.venv\Scripts\python.exe manage.py cleanup_legacy_structure_parent_links --apply --confirm-legacy-structure-parent-link-cleanup
```

`--verbose` prints per-link decisions (object type, id/name/title, legacy FK
id/name/code, mapped/parent unit id/code/type, decision/reason) and never prints
event descriptions or other free-text body content. `--limit N` caps printed
rows per object type only; it does not narrow scan or apply scope. The command
deletes no `SmallGroup` / `District` / `MinistryContext` rows, removes no
fields, runs no schema migration (`schema_mutated: false`), and switches no
runtime source of truth (`runtime_mutated: false`).

This is safe for the migrated runtime because ordinary visibility already runs
on audience rows plus active primary `ChurchStructureMembership`, and the
remaining legacy-parity resolver `resolve_units_to_small_groups()` matches
eligible groups through `ChurchStructureUnit` hierarchy descendants — its
`SmallGroup.district` / `District.ministry_context` branches are redundant for
exactly the links this command clears. `BibleStudySeries.get_eligible_small_groups()`
only uses those legacy branches as a coexistence fallback for series with
legacy scope and **no** audience rows (current data: zero such series).

Caution for re-seeding: `seed_church_structure_units` derives a unit's parent
from these legacy links when first building the tree. After the links are
cleared, the hierarchy lives authoritatively in `ChurchStructureUnit.parent`;
do not re-run the seed command in `--apply` mode expecting it to re-derive
parents from the (now cleared) legacy links — it would reparent affected units
under the "Unassigned" holding units. Treat the seed command as superseded for
already-mapped rows.

Do not run that `--apply` command against the local/dev database during the
LEGACY-OBJECT-LINKS.1A implementation task. This task does not delete
`SmallGroup`, `District`, or `MinistryContext` rows, does not remove fields, and
only prepares link cleanup where the relationship is already represented by
`ChurchStructureUnit`. Final row/table/field deletion remains a later approved
schema slice.

ServiceEvent ministry-context label cleanup command:

```powershell
.venv\Scripts\python.exe manage.py cleanup_service_event_ministry_context_labels
```

SERVICE-EVENT-CONTEXT.1A kept `ServiceEvent.ministry_context` as stored legacy
display context only and added an audience-derived fallback. SERVICE-EVENT-CONTEXT.1B
adds `ServiceEvent.host_language_unit`, a structure-native
display-only Host / Language context. Neither field is audience authority, and
neither controls visibility, serving assignments, permissions, required teams,
or TeamAssignment/My Serving behavior. Member/staff Host / Language displays
now prefer the stored legacy FK while it exists, then `host_language_unit`, then
derive a safe fallback from `ServiceEventAudienceScope` units by walking
`ChurchStructureUnit.parent` to the nearest ministry-context unit. Root-audience
events can therefore keep a whole-church audience while displaying an explicit
Host / Language unit. Rows with no stored display unit and no derivable context
render no derived label, and rows spanning multiple derived ministry contexts
render a generic mixed-context label.

The normal app-level ServiceEvent create/edit form and recurring-create form no
longer expose or save `ServiceEvent.ministry_context`, and they do not expose or
save `host_language_unit` in this slice; forged POST values for either field are
ignored. Django Admin may still expose both fields as maintenance surfaces while
the model fields exist. This slice does not remove `ServiceEvent.ministry_context`,
does not delete `MinistryContext` rows, and does not change ServiceEvent
audience/runtime semantics.

Backfill the structure-native display context before clearing the legacy FK:

```powershell
.venv\Scripts\python.exe manage.py backfill_service_event_host_language_units
```

`backfill_service_event_host_language_units` is dry-run by default. It sets only
`ServiceEvent.host_language_unit`, and only for rows where
`ServiceEvent.ministry_context.church_structure_unit` is an active
ministry-context `ChurchStructureUnit`. Apply requires both explicit flags:

```powershell
.venv\Scripts\python.exe manage.py backfill_service_event_host_language_units --apply --confirm-service-event-host-language-unit-backfill
```

`cleanup_service_event_ministry_context_labels` is dry-run by default. It clears
only `ServiceEvent.ministry_context = None`, and only when `host_language_unit`,
or the audience-derived fallback when that field is blank, maps to the same
active ministry-context unit as the current legacy FK mapping. It never mutates
`ServiceEventAudienceScope`, `ChurchStructureUnit`, `ChurchStructureMembership`,
`SmallGroup`, `District`, `MinistryContext`, Bible Study, ReflectionComment,
Profile, Role, ministry team/serving assignments, permissions, reading progress,
runtime behavior, or schema. Apply requires both explicit flags:

```powershell
.venv\Scripts\python.exe manage.py cleanup_service_event_ministry_context_labels --apply --confirm-service-event-ministry-context-label-cleanup
```

Do not run that `--apply` command without first reviewing the dry-run output for
the exact target database. Field/schema/table retirement remains a later
approved slice after cleanup and audit blockers are reviewed.

Current runtime split:

- `Profile.small_group` has no normal app-level write path after CS-RETIRE.1A, but remains stored legacy/admin/archive/audit data. PROFILE-SG.1B adds guarded cleanup tooling only; it can clear the field only for rows whose single active primary membership already safely represents the same mapped active small-group unit, and it does not run automatically.
- ServiceEvent ordinary-user visibility no longer uses zero-row legacy fallback; zero-row events are fail-closed safety states, and SE-SCOPE.1A stops normal app-level writes to legacy `scope_type` / `district` / `small_group`. SE-SCOPE.1B adds guarded cleanup tooling for existing stored values, but cleanup is explicit and not automatic. SERVICE-EVENT-CONTEXT.1B separately keeps normal app writes to `ServiceEvent.ministry_context` stopped, adds display-only `host_language_unit`, and adds guarded backfill/cleanup for matching stored FK values.
- Bible Study V2 meeting visibility, Today/landing, and role/worship pickers use `BibleStudyMeetingAudienceScope` rows plus active primary `ChurchStructureMembership`; V2 display labels now prefer `anchor_unit` / meeting audience units after BS-V2-MIRROR.1A, and BS-V2-MIRROR.1B stops new normal meeting writes from setting `BibleStudyMeeting.small_group`. BS-V2-MIRROR.1C adds `cleanup_bible_study_v2_small_group_mirrors`, a dry-run-first command that can clear existing mirrors only when `generation_key`, `anchor_unit`, and exactly one matching active small-group audience row already prove structure-native identity. Normal V2 schedule saves now write `BibleStudySeriesAudienceScope` rows without writing/updating legacy series scope fields; generation/preview read those audience rows and fail closed with zero rows. BS-SERIES-SCOPE.1B adds `cleanup_bible_study_series_legacy_scope_fields`, a dry-run-first command that can clear existing series legacy scope values only when the series already has valid `BibleStudySeriesAudienceScope` rows. Unsafe/mismatched rows remain blocked for review, no cleanup runs automatically, and model-field/DB-constraint cleanup remains a separate migration. V1 `BibleStudySession` app runtime is retired after BS-V1-RETIRE.1A and remaining V1 rows are pilot/archive data removable only by the explicit guarded BS-V1-PURGE.1A command.
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
| Bible Study schedule legacy scope fields | `BibleStudySeries.get_eligible_small_groups()`, `BibleStudySeries.scope_type`, `ministry_context`, `district`, `small_group` | stored mirror/history snapshot and audit blocker | Existing values are kept for compatibility/display/coexistence. BS-SERIES-SCOPE.1B adds guarded dry-run-first cleanup for rows that already have valid `BibleStudySeriesAudienceScope` rows; unsafe/mismatched rows stay blocked. Field/table retirement still requires a later schema slice. |
| Bible Study V2 meeting `small_group` | `studies.models.BibleStudyMeeting.small_group` | stored mirror/history snapshot and fallback label | No longer ordinary visibility source and no longer the preferred V2 member/staff display label after BS-V2-MIRROR.1A. BS-V2-MIRROR.1B stops new normal generation/manual-create writes from setting it. BS-V2-MIRROR.1C adds a guarded cleanup command for existing values; it only clears rows with correct structure-native identity already present and does not remove the field or DB constraint. |
| Bible Study V2 generation key / anchor bridge | `studies.services.normal_generation_key_for_unit()`, `anchor_unit`, `generation_key`, `backfill_bible_study_v2_generation_keys` | generation/idempotency bridge | Structure-native idempotency is present; BS-V2-KEY.1A adds dry-run-first support to backfill missing safe keys/anchors without changing runtime behavior, audience rows, or the `small_group` mirror. |
| Reflection legacy small-group snapshot | `comments.models.ReflectionComment.small_group_at_post` (**removed in REFLECTION-MIRROR.1H**) | (removed) | **Removed in REFLECTION-MIRROR.1H** (migration `comments/0007`) after 1D stopped writes, 1E/1F cleared stored data, and 1G removed display/read/admin surfaces. The reflection mirror cleanup commands and the legacy-mirror backfill/recovery/shadow tooling were retired with the field. Reflection group visibility is `ReflectionComment.structure_unit_at_post` + active primary `ChurchStructureMembership`. Only immutable historical migrations still name the field; this was a reflection-only field removal and does not remove the `SmallGroup` table. |
| Reflection structure snapshot | `ReflectionComment.structure_unit_at_post` | already runtime-retired / historical only | Canonical group reflection read/write snapshot after CS-CORE.4G.2/4G.3. |
| Prayer legacy small-group mirror | `prayers.models.PrayerRequest` (field removed) | removed / historical only | **Removed in PRAYER-MIRROR.1D.** Ordinary group-prayer visibility uses `PrayerRequest.structure_unit_at_post` plus active primary membership. 1A stopped the write, 1B cleared the stored data via the guarded `cleanup_prayer_small_group_mirrors` command, 1C removed the display/admin surfaces, and 1D dropped the model field (migration `prayers/0004`), retired the `cleanup_prayer_small_group_mirrors` command and the `resolve_legacy_small_group_mirror` helper, and reclassified the schema-prep candidate as historical-only. Prayer-only field removal; the `SmallGroup` table is unaffected. |
| Role legacy scope fields | `ChurchRoleAssignment.district`, `ChurchRoleAssignment.small_group` (fields removed) | removed / historical only | **Removed in ROLE-FIELD-RETIRE.1A** (migration `accounts/0011`). Runtime fallback was already retired in ROLE-RETIRE.1B; only immutable historical migrations still name these fields. |
| Role explicit structure scope | `ChurchRoleAssignment.structure_unit` | already runtime-retired / historical only | Current non-global role runtime scope source; membership is not used to infer role scope. |
| Legacy bridge mappings | `MinistryContext.church_structure_unit`, `District.church_structure_unit`, `SmallGroup.church_structure_unit` | generation/idempotency bridge | Still needed for setup diagnostics, Bible Study resolution/generation, and backfill/audit comparison. |
| Legacy object-row retirement inventory | `accounts.management.commands.audit_legacy_structure_object_row_retirement` | diagnostic/audit/backfill/cleanup tooling | Read-only inventory for remaining `SmallGroup`, `District`, and `MinistryContext` rows. It classifies consumers, reports mapped/unmapped/inactive/wrong-type rows, and highlights the `UNASSIGNED-GROUPS` custom-unit placeholder decision without deleting rows or changing schema/runtime behavior. |
| Legacy structure parent/context links | `SmallGroup.district`, `District.ministry_context` | stored hierarchy duplicate and table-retirement blocker | Redundant with `ChurchStructureUnit.parent` for the migrated runtime. LEGACY-OBJECT-LINKS.1A adds dry-run-first `cleanup_legacy_structure_parent_links`, which nulls these FKs only when the child unit's `parent` already equals the parent legacy object's mapped active unit. The legacy-parity resolver `resolve_units_to_small_groups()` still matches eligible groups through hierarchy descendants. Field/table retirement remains a later slice. |
| ServiceEvent ministry-context label | `ServiceEvent.ministry_context`, `ServiceEvent.host_language_unit`, `events.templatetags.event_extras.event_host_language_label`, `events.ministry_context_display`, `backfill_service_event_host_language_units`, `cleanup_service_event_ministry_context_labels` | stored display label and audit/cleanup blocker | "Host / Language" display now uses the legacy FK while present, then structure-native `host_language_unit`, then an audience-derived `ChurchStructureUnit.parent` fallback. `host_language_unit` is display-only and does not control audience/visibility. Normal app create/edit/recurring flows no longer expose or save either display field; Django Admin remains maintenance-only while the fields exist. SERVICE-EVENT-CONTEXT.1B adds guarded dry-run-first backfill for `host_language_unit`; cleanup can then clear matching legacy FK values. `ServiceEvent.ministry_context` is not removed, `MinistryContext` rows are not deleted, and field/table retirement remains later. |
| `Profile.small_group` stored field | `accounts.models.Profile.small_group`, `ProfileAdmin` | admin/emergency-maintenance surface | No normal app-level write remains, but admin/emergency/archive display remains until full retirement. |
| Staff legacy displays | staff user list, password reset, membership request detail/list, structure map | admin/emergency-maintenance surface | Read-only context only; not runtime authority. |
| Legacy retirement/audit/backfill/cleanup commands | `audit_structure_belonging`, `audit_structure_role_scopes`, `audit_service_event_fallback_retirement_readiness`, `cleanup_service_event_legacy_scope_fields`, `cleanup_profile_small_group`, `audit_bible_study_structure_retirement_readiness`, `audit_reading_structure_runtime_readiness`, `audit_group_progress_shadow`, related backfills/cleanups | diagnostic/audit/backfill/cleanup tooling | Support tooling is intentionally allowed to read legacy fields and does not by itself block runtime retirement. Cleanup tooling is dry-run-first and must not run apply without explicit approval. The reflection mirror cleanup/backfill/recovery/shadow commands were retired in REFLECTION-MIRROR.1H with the `ReflectionComment.small_group_at_post` field. |
| ServiceEvent legacy field removal | `ServiceEvent.scope_type`, `district`, `small_group` | candidate for later field-level removal | SE-SCOPE.1A stops normal app writes, and SE-SCOPE.1B adds guarded cleanup for stored values on rows with audience rows. Remove fields only after cleanup has been reviewed/applied per target DB and rollback, admin forms, displays, and diagnostics have a separate approved plan. |
| Role legacy field removal | `ChurchRoleAssignment.district`, `small_group` | completed field-level removal | **Done in ROLE-FIELD-RETIRE.1A** (migration `accounts/0011`). Runtime was already explicit-structure-only; the `backfill_structure_role_scopes` command was retired with the fields. No permission or group-progress behavior changed. |
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
- `ReflectionComment.small_group_at_post` (removed in REFLECTION-MIRROR.1H; no longer an inbound `SmallGroup` reference)
- `PrayerRequest.small_group_at_post` (removed in PRAYER-MIRROR.1D; no longer an inbound `SmallGroup` reference)
- `ChurchRoleAssignment.small_group` (removed in ROLE-FIELD-RETIRE.1A; no longer an inbound `SmallGroup` reference)
- `ServiceEvent.small_group`
- `BibleStudySeries.small_group`

Blockers:

- Existing `SmallGroup` rows and FK references block table retirement.
- `PrayerRequest.small_group_at_post`: **removed in PRAYER-MIRROR.1D.** After 1A stopped the write, 1B cleared the stored data, and 1C removed the admin/display read surfaces, 1D dropped the model field (migration `prayers/0004`), retired the `cleanup_prayer_small_group_mirrors` command and `resolve_legacy_small_group_mirror` helper, and reclassified the schema-prep candidate as historical-only. This inbound `SmallGroup` reference no longer exists. The `SmallGroup` table itself is unaffected by this prayer-only field removal.
- Unmapped/inactive/wrong-type bridge mappings are readiness blockers for any non-lossy migration or final archive step.
- `SmallGroup.district` parent links are redundant with `ChurchStructureUnit.parent`. LEGACY-OBJECT-LINKS.1A adds dry-run-first `cleanup_legacy_structure_parent_links` to clear eligible links (child unit `parent` equals the district's mapped active district unit); unsafe/mismatched links stay set. This does not delete `SmallGroup` rows or remove the field.
- ROW-RETIRE.1A separately counts the remaining `SmallGroup` rows as future
  archive candidates when they map to active small-group units, but it does not
  approve deletion. If a dedicated compatibility/mapping model replaces the old
  model rows, migrate that bridge explicitly before dropping the table.

### `District`

Audit counters include active/inactive rows, mapped/unmapped rows, inactive/wrong-type mapped units, and references from:

- `SmallGroup.district`
- `ServiceEvent.district`
- `BibleStudySeries.district`
- V1 `BibleStudySession.district`
- `ChurchRoleAssignment.district` (removed in ROLE-FIELD-RETIRE.1A; no longer an inbound `District` reference)

Blockers:

- Existing rows and FK references block table retirement.
- Wrong/missing bridge mappings block safe bridge-based backfill, audit, or final archive decisions.
- `District.ministry_context` parent links are redundant with `ChurchStructureUnit.parent`. LEGACY-OBJECT-LINKS.1A's `cleanup_legacy_structure_parent_links` clears eligible links (district unit `parent` equals the ministry context's mapped active ministry-context unit); unsafe/mismatched links stay set. It does not delete `District` rows or remove the field.
- ROW-RETIRE.1A highlights `District #13 未分配小组` mapped to
  `#22 UNASSIGNED-GROUPS` as special handling: the mapped unit is `custom`, not
  `district`, so it is likely a legacy placeholder/holding bucket. Do not
  "fix" this by converting it into a district unit during row inventory. The
  final retirement decision should choose whether to archive/delete the legacy
  row, keep it as an explicit bridge, or replace it with a dedicated
  compatibility/mapping model.

### `MinistryContext`

Audit counters include active/inactive rows, mapped/unmapped rows, inactive/wrong-type mapped units, and references from:

- `District.ministry_context`
- `ServiceEvent.ministry_context`
- `BibleStudySeries.ministry_context`

Blockers:

- Existing rows and references block table retirement.
- ServiceEvent `ministry_context` is label/context data, not audience authority, but it is still a FK reference that must be cleaned or otherwise approved before table retirement.
- `District.ministry_context` parent links are cleared (when eligible) by LEGACY-OBJECT-LINKS.1A's `cleanup_legacy_structure_parent_links`, reducing `MinistryContext` inbound references. `ServiceEvent.ministry_context` is handled separately by SERVICE-EVENT-CONTEXT.1B: normal app writes are stopped, display uses structure-native `host_language_unit` (then the existing audience-derived fallback when no explicit display unit exists), `backfill_service_event_host_language_units` can populate the display-only unit from valid legacy mappings, and `cleanup_service_event_ministry_context_labels` can clear matching stored FK values after dry-run review and explicit apply approval. The legacy field and `MinistryContext` rows remain.
- ROW-RETIRE.1A counts all remaining `MinistryContext` rows as bridge/admin/
  diagnostic row-retirement blockers until the Host / Language display cleanup,
  mapping bridge, and final table-retirement path are explicitly approved.

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
- Active series without audience rows, populated `BibleStudySeries` legacy scope fields, normal meetings without generation keys, normal meetings without `anchor_unit`, and any remaining `BibleStudyMeeting.small_group` mirror rows are generation/idempotency or field-retirement readiness blockers. BS-SERIES-SCOPE.1A stops new normal app schedule saves from adding/updating the legacy series scope blockers. BS-SERIES-SCOPE.1B adds a guarded dry-run-first cleanup command for existing populated series values, but no cleanup runs automatically and unsafe/mismatched rows stay blocked for review. BS-V2-KEY.1A support can reduce `bible_study_normal_meetings_missing_generation_key` after a separately approved future `--apply` run. STRUCTURE-BRIDGE.1A does not change those rows; it inventories which blockers remain before final `SmallGroup` table retirement or a replacement compatibility bridge can be planned.

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
- READING-STRUCT.1B `backfill_reflection_structure_snapshots` resolves missing snapshots whose legacy `small_group_at_post` maps to an active small-group unit. REFLECTION-SNAPSHOT.1C adds the guarded dry-run-first `cleanup_reflection_snapshot_blockers` command for the remaining safe missing-snapshot blockers: it backfills `structure_unit_at_post` for mapped group rows (including hidden/deleted rows) and demotes top-level orphan group rows with no recoverable group identity and no child replies from `group` to `private`. It requires `--apply` plus `--confirm-reflection-snapshot-cleanup`, performs no schema migration or runtime source switch, never prints reflection body text, leaves `small_group_at_post` untouched, and skips/preserves orphan replies, orphans with replies, and rows with unmapped/inactive/wrong-type legacy mappings. No cleanup runs automatically.
- REFLECTION-MIRROR.1D stopped normal app-level writes to `small_group_at_post`. REFLECTION-MIRROR.1E adds the complementary guarded dry-run-first `cleanup_reflection_small_group_mirrors` command for the *existing* stored mirror values: it sets `small_group_at_post = None` only when clearing cannot change visibility or display — Category A group rows whose `structure_unit_at_post` is non-null, active, a small-group unit, and equal to the mapped legacy unit (group replies only on their own valid snapshot, never inferred from a parent); and Category B non-group rows that carry a `structure_unit_at_post` (so the passage-wall label no longer depends on the legacy mirror). It requires `--apply` plus `--confirm-reflection-small-group-mirror-cleanup`, only ever mutates `small_group_at_post`, performs no schema migration or runtime source switch, never prints reflection body text, and conservatively skips non-group rows with no structure snapshot and group rows with missing/inactive/wrong-type/unmapped/mismatched snapshots. It does not remove the field; field/schema retirement remains a separate later slice and no cleanup runs automatically.
- REFLECTION-MIRROR.1F adds the complementary guarded dry-run-first `cleanup_reflection_nongroup_display_mirrors` command for the remaining Category B non-group display-context rows that the 1E command conservatively skipped (those with no `structure_unit_at_post`). For a non-group row (`small_group_at_post` set, `visibility != group`, `structure_unit_at_post` null) whose legacy `small_group_at_post` maps to an active small-group unit, it sets `structure_unit_at_post` to that mapped unit and clears `small_group_at_post`, carrying the passage-wall display label forward onto the structure snapshot while removing the legacy `SmallGroup` FK. It requires `--apply` plus `--confirm-reflection-nongroup-display-mirror-cleanup`, only ever mutates `structure_unit_at_post` and `small_group_at_post`, never changes `visibility`/`parent`/`body`, never prints reflection body text, uses only the row's own mapping (no parent inference for replies), and handles hidden/deleted rows when the mapping is valid. It skips group-visibility rows (owned by `cleanup_reflection_small_group_mirrors`), non-group rows that already carry a structure snapshot, and rows whose legacy mapping is missing/inactive/wrong-type. It does not remove the field; field/schema retirement remains a separate later slice and no cleanup runs automatically.
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
2. Harden Bible Study V2 generation/idempotency bridge: active schedules should carry audience rows, normal meetings should carry audience rows and generation keys, legacy series scope fields should be cleared only by a future guarded cleanup after audit, and mirror/audience mismatches should be zero. Run `backfill_bible_study_v2_generation_keys` in dry-run mode first; apply only when intentionally approved.
3. Run ServiceEvent legacy scope cleanup only when staff intentionally approve it for the target DB: dry-run `cleanup_service_event_legacy_scope_fields`, review zero-row blockers/output, then run `cleanup_service_event_legacy_scope_fields --apply --confirm-service-event-legacy-scope-cleanup` only after explicit approval. Field/schema deprecation remains a later plan covering forms, display, backfill/audit commands, rollback, and zero-row safety-state handling.
4. Run reflection snapshot cleanup only when staff intentionally approve it for the target DB: dry-run `cleanup_reflection_snapshot_blockers`, review the per-row decisions/blockers, then run `cleanup_reflection_snapshot_blockers --apply --confirm-reflection-snapshot-cleanup` only after explicit approval. It backfills mapped group snapshots and demotes safe top-level orphan group rows to private; orphan replies, orphans with replies, and unmapped/inactive/wrong-type rows stay blocked for review. `small_group_at_post` field/schema deprecation remains a later separate plan.
5. Run prayer legacy small-group mirror cleanup only when staff intentionally approve it for the target DB: dry-run `cleanup_prayer_small_group_mirrors`, review the per-prayer decisions/blockers, then run `cleanup_prayer_small_group_mirrors --apply --confirm-prayer-small-group-mirror-cleanup` only after explicit approval. It clears `PrayerRequest.small_group_at_post` only for group and non-group rows whose matching active small-group `structure_unit_at_post` already carries the structure identity; non-group rows with no structure snapshot and group rows with missing/inactive/wrong-type/unmapped/mismatched snapshots stay blocked. It changes no visibility or structure snapshot and removes no field. `small_group_at_post` field/schema and `SmallGroup` table retirement remain later separate plans.
6. Role legacy field retirement is **done** (ROLE-FIELD-RETIRE.1A removed `ChurchRoleAssignment.district` / `small_group`, migration `accounts/0011`). The only remaining role readiness check is that no scoped assignment lacks an explicit valid `structure_unit`; local/dev audit shows zero.
7. Run `Profile.small_group` cleanup only when staff intentionally approve it for the target DB: dry-run `cleanup_profile_small_group`, review skipped rows/output, then run `cleanup_profile_small_group --apply --confirm-profile-small-group-cleanup` only after explicit approval. Field/schema deprecation remains a later plan covering admin display, fallback/audit references, rollback, and model/table removal.
8. Retire redundant legacy parent/context links before table retirement: dry-run `cleanup_legacy_structure_parent_links`, review the per-link decisions, then run `cleanup_legacy_structure_parent_links --apply --confirm-legacy-structure-parent-link-cleanup` only after explicit approval per target DB. This clears only `SmallGroup.district` / `District.ministry_context` links already represented by `ChurchStructureUnit.parent`; `ServiceEvent.ministry_context` has its own SERVICE-EVENT-CONTEXT.1B display-context backfill/cleanup path. It deletes no rows and removes no fields.
9. Run ServiceEvent Host / Language display backfill and ministry-context label cleanup only when staff intentionally approve it for the target DB: dry-run `backfill_service_event_host_language_units`, review mapping skip categories, run `backfill_service_event_host_language_units --apply --confirm-service-event-host-language-unit-backfill` only after explicit approval, then dry-run `cleanup_service_event_ministry_context_labels`, review matching/skip categories, and run `cleanup_service_event_ministry_context_labels --apply --confirm-service-event-ministry-context-label-cleanup` only after separate explicit approval. Backfill sets only display-only `host_language_unit`; cleanup clears only matching `ServiceEvent.ministry_context` FK values. Field/schema deprecation and `MinistryContext` row/table retirement remain later.
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

For LEGACY-OBJECT-LINKS.1A, also run:

```powershell
.venv\Scripts\python.exe manage.py test accounts.test_cleanup_legacy_structure_parent_links_command -v 2
.venv\Scripts\python.exe manage.py cleanup_legacy_structure_parent_links --verbose --limit 30
```

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
