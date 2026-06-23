# CS-CORE.3C Legacy BibleStudySession Retirement Decision (Bible Study V1/V2 Boundary)

## 1. Purpose and Status

This began as a docs-only decision record. It clarifies the boundary between Bible Study V1 (legacy `BibleStudySession`) and Bible Study V2 (`BibleStudyMeeting` / the schedule, lesson, and meeting stack), and records the decision that legacy V1 `BibleStudySession` is a retirement candidate while Bible Study V2 is the active product path. CS-CORE.3D later froze the app-level V1 creation route while preserving existing V1 records and direct legacy access paths. CS-CORE.3E later audited the remaining V1 app-level mutation surfaces and recorded a future freeze recommendation without changing runtime behavior. CS-CORE.3F later froze the remaining V1 app-level edit/delete/worship mutation routes while preserving readable direct detail access. BS-V1-RETIRE.1A supersedes that readable-detail archive policy for app runtime: V1 app-level detail/list access now redirects for ordinary users and managers, and remaining V1 rows are pilot/archive data. BS-V1-PURGE.1A adds a guarded dry-run-first purge command for those rows and V1-only child rows, but runtime code does not run it automatically.

CS-CORE.3C did not authorize any runtime, template, URL, form, model, schema, migration, permission, admin, test-behavior, or data change. CS-CORE.3D is the separately approved runtime slice for freezing app-level V1 creation only.

> **Current-state update — BS-V1-ADMIN-RETIRE.1A / BS-V1-SCHEMA-RETIRE-GATE.1A:** the active Django Admin surface for legacy V1 was retired. `BibleStudySessionAdmin` and the V1-only child admins `BibleStudyGuideAdmin` / `BibleStudyWorshipSongAdmin` were **unregistered** in `studies/admin.py`, so staff can no longer create/edit/delete/maintain V1 sessions or V1-only guide/worship rows through Django Admin. This was admin-only: no V1 data was deleted, no V1 model/table/field was removed, the guarded `purge_legacy_bible_study_v1_sessions` command was not run with `--apply`, and no V2 admin/runtime/schema/data changed (V2 `BibleStudyMeeting` admin is unaffected). `BS-V1-SCHEMA-RETIRE-GATE.1A` then hardened the dry-run purge preflight and retirement audits so V1 `BibleStudySession` rows, V1-only child rows, `BibleStudySession.small_group`, and `BibleStudySession.district` are explicit purge/schema blockers for later `SmallGroup` / `District` table retirement. V1 app runtime/admin remain retired; V1 model/table/schema removal stays a later separately approved slice. Sentences below that describe `BibleStudySessionAdmin` / Django Admin as still present are historical as of this update.

Related docs:

- `docs/CHURCH_STRUCTURE_CORE_MIGRATION_PLAN.md` (CS-CORE plan; legacy retirement preconditions)
- `docs/LEGACY_PROFILE_SMALL_GROUP_CONSUMER_INVENTORY.md` (CS-CORE.3A consumer inventory)
- `docs/BIBLE_STUDY_MEETING_ROLE_ASSIGNMENT_PLAN.md` (V2 meeting role direction)

## 2. The Decision

1. **`BibleStudySession` is Bible Study V1, not the current Bible Study V2 product path.** Bible Study V2 is the active product path.
2. **Legacy V1 `BibleStudySession` is retired from app-level runtime.** It should not be extended, promoted, or preserved as a parallel app archive product.
3. **Do not migrate V1 `BibleStudySession` visibility to membership-core.** Migrating `BibleStudySession.can_be_seen_by()` to `ChurchStructureMembership` would revive a deprecated product path and create two competing Bible Study systems. Future Bible Study investment goes into V2 instead.
4. **Do not add new audience-scope support to `BibleStudySession`.** New audience-scope and structure work belongs to the V2 stack only.
5. **Existing V1 data is pilot/archive data.** BS-V1-RETIRE.1A did not delete it. BS-V1-PURGE.1A adds explicit cleanup tooling that can purge V1 rows and V1-only dependent data only when staff run the guarded apply command. (Historical: this step originally said Django Admin emergency maintenance "may remain" until purge/schema cleanup; **BS-V1-ADMIN-RETIRE.1A has since retired that admin surface** — see the current-state update in Section 1.)

This decision follows the existing architecture direction: legacy retire / new model as core, where `ChurchStructureUnit` is the canonical church structure tree, `ChurchStructureMembership` is the canonical ordinary-user belonging model, and legacy small group retirement is consumer-by-consumer. **Current state:** `Profile.small_group` was removed in PROFILE-SG-FIELD-RETIRE.1A (migration `accounts/0012`) and must not be reintroduced; belonging is active primary `ChurchStructureMembership`. Legacy is not yet fully retired, but the remaining legacy blockers are the legacy `SmallGroup` / `District` / `MinistryContext` object rows/tables (with their bridge/admin/diagnostic surfaces) and V1 `BibleStudySession` schema cleanup — not `Profile.small_group`. (Historical: this paragraph originally said `Profile.small_group` "must remain until all legacy consumers are migrated or retired"; that is superseded by its removal.)

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

V1 still exists in the schema, but it is no longer the promoted surface, is retired from app-level runtime, and (after BS-V1-ADMIN-RETIRE.1A) no longer has an active Django Admin surface:

- **`/studies/` keeps the historical view name `study_session_list`** (`studies/urls.py`), but the page now behaves as the V2 Bible Study landing surface: the view builds `get_v2_landing_context()` and the template (`templates/studies/study_session_list.html`) renders the user's V2 `BibleStudyMeeting` plus V2 staff links (schedules / weekly guides / meetings) only. The promoted member-facing UI shows V2 meetings, not legacy V1 sessions.
- **Today uses V2 `BibleStudyMeeting`**, not legacy `BibleStudySession`: `reading/views.py` reuses `get_v2_landing_context()` and surfaces linked-user `BibleStudyMeetingRole` chips.
- **Staff surfaces promote V2** schedules / guides / meetings: the staff overview counts `BibleStudySeries` / `BibleStudyLesson` / `BibleStudyMeeting` (`accounts/views.py`), and the `/studies/` staff links target the V2 manage lists. No promoted staff surface counts or links legacy V1 sessions.
- **V1 direct app routes still exist but are retired/frozen** (`studies/urls.py`): `studies/new/`, `studies/<int:session_id>/`, `studies/<int:session_id>/edit/`, `studies/<int:session_id>/delete/`, `studies/<int:session_id>/worship/` (plus V1 worship-song edit/delete routes) redirect to `/studies/` and do not render or mutate V1 app content.
- **V1 forms/templates/tests still exist; the V1 admin surface is retired**: `BibleStudySessionForm` (`studies/forms.py`), legacy templates, and `BibleStudySession` coverage in `studies/tests.py` still exist, but **`BibleStudySessionAdmin` (and the V1-only `BibleStudyGuideAdmin` / `BibleStudyWorshipSongAdmin`) were unregistered in BS-V1-ADMIN-RETIRE.1A** (`studies/admin.py`), so there is no active V1 Django Admin maintenance surface. The app no longer treats the legacy detail template as a normal archive product surface.
- **V1 app visibility is retired, not migrated.** `BibleStudySession.can_be_seen_by()` (`studies/models.py`) now fails closed for app users. `Profile.small_group`, `District`, `SmallGroup`, and `scope_type` no longer grant V1 app access. V1 is not migrated to `ChurchStructureMembership`.

## 5. Recommended Future Implementation Path

Each remaining step below is future work requiring its own approval unless marked complete.

1. **Step 1:** Confirm no promoted normal/staff UI links create or manage new V1 sessions (the `/studies/` landing and staff overview already promote V2 only; re-verify before any runtime slice).
2. **Step 2:** Convert any remaining promoted V1 entry points to V2 schedule/lesson/meeting flows.
3. **Step 3:** Completed by CS-CORE.3D for app-level creation only: `studies/new/` redirects to `/studies/` with retirement messaging and no longer renders or processes the V1 creation form.
4. **Step 4:** Completed by BS-V1-RETIRE.1A: retire direct V1 app detail/list runtime for ordinary users and managers. Existing V1 rows remain stored only as pilot/archive data pending explicit purge.
5. **Step 5:** Reduce/replace the remaining legacy `SmallGroup` bridge/admin/diagnostic/table-retirement context in a later architecture slice (see `docs/CHURCH_STRUCTURE_CORE_MIGRATION_PLAN.md` Section 12). V2 meeting ownership/identity is already structure-native via `anchor_unit`, `generation_key`, and `BibleStudyMeetingAudienceScope` rows; the `BibleStudyMeeting.small_group` FK was removed in BS-MEETING-MIRROR.1A (`studies/0011`), so this step no longer concerns a meeting-owning FK. (Historical: this step originally referred to a V2 "generation source and `BibleStudyMeeting.small_group` ownership" bridge; the meeting FK has since been removed.)
6. **Step 6:** BS-V1-PURGE.1A adds the guarded dry-run-first purge command:

   ```powershell
   .venv\Scripts\python.exe manage.py purge_legacy_bible_study_v1_sessions --apply --confirm-v1-bible-study-retirement
   ```

   The command is not automatically run by runtime code. No V1 rows are deleted unless staff explicitly run the apply command above; this implementation task must not run `--apply` against the local/dev database. After a successful explicit purge, V1 `BibleStudySession` and V1-only child rows no longer block future field/table cleanup. The purge does not delete V2 `BibleStudyMeeting` data and does not change V2 behavior. It does not remove the V1 models/tables yet; schema cleanup remains a later migration slice.

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
- (Historical, as of BS-V1-RETIRE.1A: Django Admin remained the emergency maintenance path for V1.) **Superseded by BS-V1-ADMIN-RETIRE.1A**, which retired/unregistered the active V1 Django Admin surface (`BibleStudySessionAdmin`, `BibleStudyGuideAdmin`, and `BibleStudyWorshipSongAdmin` in `studies/admin.py`); there is no longer an active V1 admin maintenance surface. This was admin-only — no V1 data was deleted and no V1 model/table/field was removed; V1 model/table/schema removal remains a later separate slice.
- V1 rows are pilot/archive data pending explicit purge. No V1 rows are deleted by this slice.
- No V1-to-membership migration is planned, and no V1-to-V2 data migration is required unless a separate historical-content decision asks for one.

## 5E. BS-V1-PURGE.1A Guarded Cleanup Command Status

BS-V1-PURGE.1A adds `purge_legacy_bible_study_v1_sessions` as guarded cleanup tooling for retired V1 pilot data.

- Dry-run is the default and reports matched V1 `BibleStudySession`, `BibleStudyGuide`, and `BibleStudyWorshipSong` rows without writing anything. The preflight also reports session counts by `scope_type`, sessions with `district_id`, sessions with `small_group_id`, and unexpected inbound dependency rows, so future apply approval can review V1 schema/table-retirement blockers before any destructive action.
- Destructive mode requires both `--apply` and `--confirm-v1-bible-study-retirement`.
- The command is not called by runtime code and should not be run with `--apply` against the local/dev database during the implementation task.
- The explicit apply command is:

  ```powershell
  .venv\Scripts\python.exe manage.py purge_legacy_bible_study_v1_sessions --apply --confirm-v1-bible-study-retirement
  ```

- The command does not delete `BibleStudySeries`, `BibleStudyLesson`, `BibleStudyMeeting`, `BibleStudyMeetingAudienceScope`, `BibleStudyMeetingRole`, `BibleStudyMeetingWorshipSong`, or church-structure rows, and it does not change V2 behavior.
- Until the guarded apply succeeds, `audit_legacy_structure_retirement_readiness` counts purge-pending V1 session rows and V1 child rows as data/table-retirement blockers while keeping V1 app-runtime blocker counters at zero.
- The V1 models/tables and the V1 `district` / `small_group` schema fields remain after the purge tooling; schema cleanup is a later migration slice.

## 6. Non-Goals

The historical and current slices have different boundaries:

- CS-CORE.3C was docs-only and did not change URL, form, model, schema, migration, runtime, or data behavior.
- CS-CORE.3D and CS-CORE.3F froze app-level V1 create/edit/delete/worship routes without deleting V1 rows.
- BS-V1-RETIRE.1A does change app-level runtime/view/model-method behavior so V1 `BibleStudySession` app access is retired.

BS-V1-RETIRE.1A does not include or authorize:

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

## 7. Verification

CS-CORE.3C was a docs-only decision record and needed no Django tests. CS-CORE.3D is a runtime freeze and should use targeted route/view tests plus the standard lightweight Django checks.

Recommended lightweight verification for CS-CORE.3D:

```powershell
python manage.py makemigrations --check
python manage.py check
python manage.py test studies.tests.BibleStudyModuleTests.test_user_with_pastor_role_is_redirected_from_create_page studies.tests.BibleStudyModuleTests.test_manager_post_to_create_route_does_not_create_session_or_guide -v 2
git diff --check
```
