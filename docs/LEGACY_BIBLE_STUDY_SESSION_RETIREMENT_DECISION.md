# CS-CORE.3C Legacy BibleStudySession Retirement Decision (Bible Study V1/V2 Boundary)

## 1. Purpose and Status

This began as a docs-only decision record. It clarifies the boundary between Bible Study V1 (legacy `BibleStudySession`) and Bible Study V2 (`BibleStudyMeeting` / the schedule, lesson, and meeting stack), and records the decision that legacy V1 `BibleStudySession` is a retirement candidate while Bible Study V2 is the active product path. CS-CORE.3D later froze the app-level V1 creation route while preserving existing V1 records and direct legacy access paths. CS-CORE.3E later audited the remaining V1 app-level mutation surfaces and recorded a future freeze recommendation without changing runtime behavior. CS-CORE.3F later froze the remaining V1 app-level edit/delete/worship mutation routes while preserving readable direct detail access. BS-V1-RETIRE.1A superseded that readable-detail archive policy for app runtime: V1 app-level detail/list access redirected for ordinary users and managers, and remaining V1 rows were pilot/archive data. BS-V1-SCHEMA-RETIRE.1A then removed the V1 models/tables behind a guarded migration after local dry-run preflight reported zero V1 session rows, zero V1-only child rows, zero populated V1 scope/FK counters, and zero unexpected inbound dependency rows.

CS-CORE.3C did not authorize any runtime, template, URL, form, model, schema, migration, permission, admin, test-behavior, or data change. CS-CORE.3D is the separately approved runtime slice for freezing app-level V1 creation only.

> **Current-state update — BS-V1-ADMIN-RETIRE.1A / BS-V1-SCHEMA-RETIRE.1A:** the active Django Admin surface for legacy V1 was retired first. `BibleStudySessionAdmin` and the V1-only child admins `BibleStudyGuideAdmin` / `BibleStudyWorshipSongAdmin` were **unregistered** in `studies/admin.py`, so staff can no longer create/edit/delete/maintain V1 sessions or V1-only guide/worship rows through Django Admin. BS-V1-SCHEMA-RETIRE.1A then removed `BibleStudySession`, `BibleStudyGuide`, and `BibleStudyWorshipSong` models/tables. The migration starts with a `RunPython` guard that checks the historical V1 models through `apps.get_model()` and aborts with a clear error if any target DB still has V1 session, guide, or worship-song rows. The local/current dry-run preflight before removal reported zero V1 rows, zero V1 child rows, zero V1 scope/FK counters, zero unexpected inbound dependency rows, and `data_mutated: false`. V2 `BibleStudyMeeting` admin/runtime/schema/data is unaffected. V1 is not migrated to membership-core or V2. Sentences below that describe V1 app routes/forms/templates/admin/models as still present are historical as of this update.

Related docs:

- `docs/CHURCH_STRUCTURE_CORE_MIGRATION_PLAN.md` (CS-CORE plan; legacy retirement preconditions)
- `docs/LEGACY_PROFILE_SMALL_GROUP_CONSUMER_INVENTORY.md` (CS-CORE.3A consumer inventory)
- `docs/BIBLE_STUDY_MEETING_ROLE_ASSIGNMENT_PLAN.md` (V2 meeting role direction)

## 2. The Decision

1. **`BibleStudySession` is Bible Study V1, not the current Bible Study V2 product path.** Bible Study V2 is the active product path.
2. **Legacy V1 `BibleStudySession` is retired from app-level runtime.** It should not be extended, promoted, or preserved as a parallel app archive product.
3. **Do not migrate V1 `BibleStudySession` visibility to membership-core.** Migrating `BibleStudySession.can_be_seen_by()` to `ChurchStructureMembership` would revive a deprecated product path and create two competing Bible Study systems. Future Bible Study investment goes into V2 instead.
4. **Do not add new audience-scope support to `BibleStudySession`.** New audience-scope and structure work belongs to the V2 stack only.
5. **Existing V1 data was pilot/archive cleanup context only.** BS-V1-SCHEMA-RETIRE.1A removed the V1 schema only after local/current preflight showed zero V1 session and child rows. Target DB safety is enforced by the migration guard, which aborts if any V1 rows remain. (Historical: this step originally said Django Admin emergency maintenance "may remain" until purge/schema cleanup; **BS-V1-ADMIN-RETIRE.1A has since retired that admin surface** — see the current-state update in Section 1.)

This decision follows the existing architecture direction: legacy retire / new model as core, where `ChurchStructureUnit` is the canonical church structure tree, `ChurchStructureMembership` is the canonical ordinary-user belonging model, and legacy small group retirement is consumer-by-consumer. **Current state:** `Profile.small_group` was removed in PROFILE-SG-FIELD-RETIRE.1A (migration `accounts/0012`) and must not be reintroduced; belonging is active primary `ChurchStructureMembership`. V1 schema is removed by BS-V1-SCHEMA-RETIRE.1A after a zero-row preflight. The legacy `SmallGroup` / `District` / `MinistryContext` object rows/tables and their `church_structure_unit` bridge FKs were later retired/removed by the legacy structure row/table retirement slices. (Historical: this paragraph originally said `Profile.small_group` "must remain until all legacy consumers are migrated or retired" and listed legacy structure row/table blockers; that is superseded by the later removal slices.)

## 3. The Active V2 Model Stack

Bible Study V2 is the active product path. Its model stack is:

- `BibleStudySeries` (schedule)
- `BibleStudySeriesAudienceScope` (schedule audience join to `ChurchStructureUnit`)
- `BibleStudyLesson` (weekly guide)
- `BibleStudyMeeting` (small-group meeting)
- `BibleStudyMeetingRole` (per-meeting responsibility)
- `BibleStudyMeetingWorshipSong` (worship-set item)

Current V2 structure-model status (verified against the worktree on 2026-06-12):

- **V2 schedule audience already uses `ChurchStructureUnit`** through `BibleStudySeriesAudienceScope` (`studies/models.py`, `BibleStudySeriesAudienceScope.unit`).
- **V2 meeting identity/display/generation is structure-native; the `BibleStudyMeeting.small_group` FK was removed in BS-MEETING-MIRROR.1A** (migration `studies/0011`). Generated `BibleStudyMeeting` rows no longer attach to a legacy `SmallGroup`; meeting identity/idempotency uses `generation_key`, display/grouping uses `anchor_unit`, and audience uses `BibleStudyMeetingAudienceScope` rows. The remaining legacy `SmallGroup` dependency is bridge/admin/diagnostic/table-retirement context (e.g. the `resolve_units_to_small_groups` resolver retained for coexistence/diagnostics), not a V2 meeting FK. (Historical: this bullet originally said "V2 still has a legacy `SmallGroup` generation bridge" and "generated `BibleStudyMeeting` rows still attach to legacy `SmallGroup`"; both are superseded by the FK removal.)
- **V2 ordinary-member meeting visibility uses membership-core audience rows.** `BibleStudyMeeting.can_be_seen_by()` (`studies/models.py`) delegates to `studies/visibility.py`, matching the user's single active primary `ChurchStructureMembership` against `BibleStudyMeetingAudienceScope` rows after BS-STRUCT.2A. Zero-row V2 meetings fail closed for ordinary users. (Both the former `Profile.small_group` field and the former `BibleStudyMeeting.small_group` mirror have since been removed — in PROFILE-SG-FIELD-RETIRE.1A and BS-MEETING-MIRROR.1A respectively — and grant nothing here.)
- **V2 role/worship user pickers use membership-core audience-row matching** for the meeting's audience rows, while preserving the already-selected saved user on edit.

So V2 is the structure-model investment target and V2 meeting identity/display/generation is now structure-native via `anchor_unit`, `generation_key`, and `BibleStudyMeetingAudienceScope` rows. The `BibleStudyMeeting.small_group` FK was removed in BS-MEETING-MIRROR.1A, so it no longer depends on legacy `SmallGroup` rows. The remaining legacy `SmallGroup` dependency is bridge/admin/diagnostic/table-retirement context only. (Historical: this paragraph originally said "the generation bridge and the `BibleStudyMeeting.small_group` FK still depend on legacy `SmallGroup` rows and mappings"; that is superseded by the FK removal.)

## 4. V1 State History And Current Runtime

V1 no longer exists in the current Django model/schema state after BS-V1-SCHEMA-RETIRE.1A. Its app runtime and Django Admin surface were retired first, and its tables are removed by a guarded migration:

- **`/studies/` keeps the historical view name `study_session_list`** (`studies/urls.py`), but the page now behaves as the V2 Bible Study landing surface: the view builds `get_v2_landing_context()` and the template (`templates/studies/study_session_list.html`) renders the user's V2 `BibleStudyMeeting` plus V2 staff links (schedules / weekly guides / meetings) only. The promoted member-facing UI shows V2 meetings, not legacy V1 sessions.
- **Today uses V2 `BibleStudyMeeting`**, not legacy `BibleStudySession`: `reading/views.py` reuses `get_v2_landing_context()` and surfaces linked-user `BibleStudyMeetingRole` chips.
- **Staff surfaces promote V2** schedules / guides / meetings: the staff overview counts `BibleStudySeries` / `BibleStudyLesson` / `BibleStudyMeeting` (`accounts/views.py`), and the `/studies/` staff links target the V2 manage lists. No promoted staff surface counts or links legacy V1 sessions.
- **V1 direct app routes/forms/templates were removed or retired.** The current `/studies/` route keeps the historical `study_session_list` name only as the V2 landing surface. The direct V1 create/detail/edit/delete/worship URL patterns, V1 forms, and V1 templates were removed with the schema/code retirement slice.
- **V1 app visibility is retired, not migrated.** The removed V1 path is not migrated to `ChurchStructureMembership`, not migrated to V2, and not treated as a long-term app archive product.

## 5. Recommended Future Implementation Path

Each remaining step below is future work requiring its own approval unless marked complete.

1. **Step 1:** Confirm no promoted normal/staff UI links create or manage new V1 sessions (the `/studies/` landing and staff overview already promote V2 only; re-verify before any runtime slice).
2. **Step 2:** Convert any remaining promoted V1 entry points to V2 schedule/lesson/meeting flows.
3. **Step 3:** Completed by CS-CORE.3D for app-level creation only: `studies/new/` redirects to `/studies/` with retirement messaging and no longer renders or processes the V1 creation form.
4. **Step 4:** Completed by BS-V1-RETIRE.1A: retire direct V1 app detail/list runtime for ordinary users and managers. Historical/superseded: at this step, existing V1 rows remained stored only as pilot/archive data pending explicit purge; BS-V1-SCHEMA-RETIRE.1A later removed the V1 models/tables behind a migration guard after local/current dry-run preflight showed zero V1 rows and child rows.
5. **Step 5:** Historical/superseded bridge-reduction step. V2 meeting ownership/identity is already structure-native via `anchor_unit`, `generation_key`, and `BibleStudyMeetingAudienceScope` rows; the `BibleStudyMeeting.small_group` FK was removed in BS-MEETING-MIRROR.1A (`studies/0011`), and the legacy structure object rows/tables were later removed. (Historical: this step originally referred to a V2 "generation source and `BibleStudyMeeting.small_group` ownership" bridge; the meeting FK and later legacy structure tables have since been removed.)
6. **Step 6:** BS-V1-SCHEMA-RETIRE.1A removed the V1 models/tables after the required dry-run preflight showed zero local V1 rows and child rows. The earlier purge command was retired with the removed models. Target DB protection now lives in the schema migration guard: if any V1 `BibleStudySession`, `BibleStudyGuide`, or `BibleStudyWorshipSong` rows exist, the migration aborts before deleting tables. The migration does not delete or alter V2 `BibleStudySeries`, `BibleStudyLesson`, `BibleStudyMeeting`, `BibleStudyMeetingAudienceScope`, `BibleStudyMeetingRole`, `BibleStudyMeetingWorshipSong`, or `BibleStudySeriesAudienceScope`.

## 5A. Historical CS-CORE.3D Runtime Freeze Status

This subsection is historical. BS-V1-RETIRE.1A later retired direct V1 app detail/list runtime for ordinary users and managers.

CS-CORE.3D freezes new legacy V1 `BibleStudySession` creation through the app route only.

- `GET /studies/new/` redirects to `/studies/` and does not render the V1 creation form.
- `POST /studies/new/` redirects to `/studies/` and does not create a `BibleStudySession` or `BibleStudyGuide`.
- Existing V1 records remain readable through direct allowed detail paths.
- V1 direct detail/edit/delete/worship routes and Django Admin remain in place.
- `BibleStudySessionForm`, `BibleStudySessionAdmin`, and `BibleStudySession.can_be_seen_by()` remain in place.
- V1 visibility is still legacy-driven by `Profile.small_group` / legacy scope semantics.
- V1 is not fully retired yet; no V1 data, model, table, or migration was removed by this slice.

## 5B. Historical CS-CORE.3E Archive Mutation Policy Audit

This subsection is historical. BS-V1-RETIRE.1A supersedes the readable-detail archive recommendation by retiring app-level V1 runtime.

CS-CORE.3E is a docs-only audit of the remaining legacy V1 mutation surfaces. It does not implement the freeze; it records the current state and the recommended next runtime slice.

Audit findings from the worktree on 2026-06-12:

- Direct V1 routes still exist for readable detail and app-level mutation: `study_session_detail`, `edit_study_session`, `delete_study_session`, `manage_worship_songs`, `edit_worship_song`, and `delete_worship_song` in `studies/urls.py`.
- Direct detail remains readable when `BibleStudySession.can_be_seen_by()` allows the user. Visibility is still legacy-driven and should not be migrated to membership-core.
- Direct manager mutation routes are still active in `studies/views.py`: `edit_study_session` can update the session and its `BibleStudyGuide`; `delete_study_session` cancels the session on `POST`; `manage_worship_songs` can create `BibleStudyWorshipSong` child rows; `edit_worship_song` and `delete_worship_song` can mutate or delete existing V1 worship rows.
- Promoted normal and staff UI surfaces checked do not link to V1 mutation routes. `/studies/` renders the V2 landing and V2 staff links only; Today links to the V2 meeting detail or `/studies/`; the staff overview and staff navigation link to V2 schedule/guide/meeting management pages. The ordinary top nav still links to `study_session_list`, which is now the V2 landing surface.
- The V1 detail page itself still exposes app-level management controls to users with Bible Study management capability: edit session, cancel session, and manage worship songs. The worship management page exposes add/edit/delete controls for V1 worship songs.
- Tests still protect current V1 direct-route behavior in `studies/tests.py`: direct legacy detail visibility, no-promoted-V1 landing behavior, frozen create route behavior, manager edit/cancel behavior, V1 worship management access, V1 worship add/edit/delete, and worship visibility on readable V1 details.

Policy recommendation for the next runtime slice:

- Existing V1 records should remain readable through direct allowed detail paths.
- Django Admin may remain available as the temporary emergency archival maintenance path until a formal archive policy exists.
- App-level V1 mutation routes should be frozen: the edit route should redirect to the V1 detail page or `/studies/` with archive messaging; the delete/cancel route should not mutate V1 records from the app route; V1 worship add/edit/delete routes should not create, mutate, or delete V1 worship rows from app routes; and the V1 detail page should show an archive notice instead of active management controls.
- No V1 data should be deleted, and no V1 visibility migration should be attempted as part of that freeze.

Explicit non-goals for CS-CORE.3E:

- no runtime, route, redirect, template, form, admin, model, migration, test-behavior, or data change;
- no V1 data deletion and no V1 table/model removal;
- no `BibleStudySession.can_be_seen_by()` migration to `ChurchStructureMembership`;
- no reading/progress/privacy, ServiceEvent fallback, permissions, roles, ministry, TeamAssignment, My Serving, or `Profile.small_group` change.

## 5C. Historical CS-CORE.3F App Mutation Freeze Status

This subsection is historical. BS-V1-RETIRE.1A later redirects V1 detail and mutation routes to `/studies/` for ordinary users and managers.

CS-CORE.3F freezes the remaining legacy V1 `BibleStudySession` app-level mutation routes while preserving archive readability.

- `GET` and `POST` to the V1 edit route redirect to the V1 detail page when the session is visible to the user, otherwise to `/studies/`; they no longer render or process the V1 edit form.
- `GET` and `POST` to the V1 delete/cancel route redirect to the V1 detail page when visible, otherwise to `/studies/`; they no longer cancel or mutate the `BibleStudySession`.
- `GET` and `POST` to the V1 worship management, worship edit, and worship delete routes redirect to the parent V1 detail page when visible, otherwise to `/studies/`; they no longer create, update, or delete `BibleStudyWorshipSong` rows.
- Existing V1 records remain readable through direct allowed detail paths, and existing V1 worship rows remain visible on readable V1 detail pages.
- The V1 detail page no longer exposes app-level edit, delete/cancel, or worship management controls; managers see an archive notice instead.
- Django Admin remains the temporary emergency archival maintenance path.
- No V1 data, model, table, route, form, template, admin, or migration was removed by this slice.
- V1 visibility remains legacy-driven by `BibleStudySession.can_be_seen_by()`; it was not migrated to membership-core.
- V1 is still not fully retired.

## 5D. BS-V1-RETIRE.1A App Runtime Retirement Status

BS-V1-RETIRE.1A fully retires legacy V1 `BibleStudySession` from app-level runtime.

- Ordinary users cannot open V1 detail even when their legacy `Profile.small_group` matches the V1 session's legacy scope fields.
- Staff/managers also cannot use V1 detail/edit/delete/worship routes as a normal app archive path; the routes redirect to `/studies/` with retirement messaging and do not mutate V1 rows.
- `/studies/` remains the active V2 `BibleStudyMeeting` landing. V2 `BibleStudyMeeting` behavior is unchanged.
- (Historical, as of BS-V1-RETIRE.1A: Django Admin remained the emergency maintenance path for V1.) **Superseded by BS-V1-ADMIN-RETIRE.1A**, which retired/unregistered the active V1 Django Admin surface (`BibleStudySessionAdmin`, `BibleStudyGuideAdmin`, and `BibleStudyWorshipSongAdmin` in `studies/admin.py`); there is no longer an active V1 admin maintenance surface. This was admin-only at that slice, but **BS-V1-SCHEMA-RETIRE.1A later removed the V1 model/table schema** behind the guarded `studies/0012` migration.
- Historical/superseded: at BS-V1-RETIRE.1A time, V1 rows were pilot/archive data pending explicit purge, and no V1 rows were deleted by that slice. Current state: BS-V1-SCHEMA-RETIRE.1A removes the V1 models/tables behind a migration guard after local/current preflight showed zero V1 rows and child rows.
- No V1-to-membership migration is planned, and no V1-to-V2 data migration is required unless a separate historical-content decision asks for one.

## 5E. Historical BS-V1-PURGE.1A Guarded Cleanup Command Status

BS-V1-PURGE.1A added `purge_legacy_bible_study_v1_sessions` as guarded cleanup tooling for retired V1 pilot data. BS-V1-SCHEMA-RETIRE.1A retired that command with the removed V1 models after the final local/current dry-run preflight reported zero V1 sessions, zero V1 child rows, zero populated V1 scope/FK counters, zero unexpected inbound dependency rows, and `data_mutated: false`.

- Dry-run is the default and reports matched V1 `BibleStudySession`, `BibleStudyGuide`, and `BibleStudyWorshipSong` rows without writing anything. The preflight also reports session counts by `scope_type`, sessions with `district_id`, sessions with `small_group_id`, and unexpected inbound dependency rows, so future apply approval can review V1 schema/table-retirement blockers before any destructive action.
- Destructive mode requires both `--apply` and `--confirm-v1-bible-study-retirement`.
- The command is not called by runtime code and should not be run with `--apply` against the local/dev database during the implementation task.
- Historical explicit apply command while the retired purge command existed:

  ```powershell
  .venv\Scripts\python.exe manage.py purge_legacy_bible_study_v1_sessions --apply --confirm-v1-bible-study-retirement
  ```

- The command does not delete `BibleStudySeries`, `BibleStudyLesson`, `BibleStudyMeeting`, `BibleStudyMeetingAudienceScope`, `BibleStudyMeetingRole`, `BibleStudyMeetingWorshipSong`, or church-structure rows, and it does not change V2 behavior.
- Historical while the command existed: until guarded cleanup/schema readiness was proven, `audit_legacy_structure_retirement_readiness` counted purge-pending V1 session rows and V1 child rows as data/table-retirement blockers while keeping V1 app-runtime blocker counters at zero.
- Current state: `audit_legacy_structure_retirement_readiness` reports V1 counters as zero because the V1 models are removed from the live ORM. `audit_legacy_structure_schema_retirement_readiness` classifies `BibleStudySession`, `BibleStudyGuide`, and `BibleStudyWorshipSong` as removed/historical candidates. Target DB row safety is enforced by the guarded `studies/0012` migration, not by a still-runnable purge command.

## 6. Non-Goals

The historical and current slices have different boundaries:

- CS-CORE.3C was docs-only and did not change URL, form, model, schema, migration, runtime, or data behavior.
- CS-CORE.3D and CS-CORE.3F froze app-level V1 create/edit/delete/worship routes without deleting V1 rows.
- BS-V1-RETIRE.1A changed app-level runtime/view/model-method behavior so V1 `BibleStudySession` app access was retired.
- BS-V1-SCHEMA-RETIRE.1A removes V1 models/tables behind a guarded migration; it does not apply the migration in local/dev during implementation, mutate data, run `--apply`, migrate V1 to membership-core, or migrate V1 to V2.

BS-V1-RETIRE.1A did not include or authorize:

- removing URL patterns, forms, models, templates, Django Admin access, schema, or migrations;
- deleting V1 rows or silently purging pilot/archive data;
- migrating V1 `BibleStudySession` visibility to membership-core;
- migrating V1 rows to V2 `BibleStudyMeeting` records;
- changing V2 `BibleStudyMeeting` behavior;
- reading/progress/privacy migration;
- ServiceEvent fallback migration;
- permissions/roles/ministry/team assignment migration;
- any attempt to fully remove `SmallGroup` or `Profile.small_group`.

BS-V1-PURGE.1A authorizes only explicit guarded cleanup tooling for V1 pilot rows and V1-only child rows. It still does not authorize V1 model/table removal, V2 behavior changes, membership-core migration of V1, or automatic runtime purge behavior.

Historical note: BS-V1-SCHEMA-RETIRE.1A later superseded the purge-tooling-only state. The purge command is retired with the removed V1 models, and the guarded schema migration is the target-DB protection for any database that still has V1 rows.

## 7. Verification

CS-CORE.3C was a docs-only decision record and needed no Django tests. CS-CORE.3D is a runtime freeze and should use targeted route/view tests plus the standard lightweight Django checks.

Recommended lightweight verification for CS-CORE.3D:

```powershell
python manage.py makemigrations --check
python manage.py check
python manage.py test studies.tests.BibleStudyModuleTests.test_user_with_pastor_role_is_redirected_from_create_page studies.tests.BibleStudyModuleTests.test_manager_post_to_create_route_does_not_create_session_or_guide -v 2
git diff --check
```
