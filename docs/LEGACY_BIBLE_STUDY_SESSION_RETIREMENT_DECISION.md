# CS-CORE.3C Legacy BibleStudySession Retirement Decision (Bible Study V1/V2 Boundary)

## 1. Purpose and Status

This began as a docs-only decision record. It clarifies the boundary between Bible Study V1 (legacy `BibleStudySession`) and Bible Study V2 (the schedule/lesson/meeting stack), and records the decision that legacy V1 `BibleStudySession` is a retirement/archive candidate while Bible Study V2 is the active product path. CS-CORE.3D later froze the app-level V1 creation route while preserving existing V1 records and direct legacy access paths.

CS-CORE.3C did not authorize any runtime, template, URL, form, model, schema, migration, permission, admin, test-behavior, or data change. CS-CORE.3D is the separately approved runtime slice for freezing app-level V1 creation only.

Related docs:

- `docs/CHURCH_STRUCTURE_CORE_MIGRATION_PLAN.md` (CS-CORE plan; legacy retirement preconditions)
- `docs/LEGACY_PROFILE_SMALL_GROUP_CONSUMER_INVENTORY.md` (CS-CORE.3A consumer inventory)
- `docs/BIBLE_STUDY_MEETING_ROLE_ASSIGNMENT_PLAN.md` (V2 meeting role direction)

## 2. The Decision

1. **`BibleStudySession` is Bible Study V1, not the current Bible Study V2 product path.** Bible Study V2 is the active product path.
2. **Legacy V1 `BibleStudySession` is a retirement/archive candidate.** It should be frozen as legacy archive/fallback content, not extended and not promoted.
3. **Do not migrate V1 `BibleStudySession` visibility to membership-core.** Migrating `BibleStudySession.can_be_seen_by()` to `ChurchStructureMembership` would revive a deprecated product path and create two competing Bible Study systems. Future Bible Study investment goes into V2 instead.
4. **Do not add new audience-scope support to `BibleStudySession`.** New audience-scope and structure work belongs to the V2 stack only.
5. **Existing V1 data must not be deleted.** Existing V1 direct access and admin behavior are not changed by this docs-only slice.

This decision follows the existing architecture direction: legacy retire / new model as core, where `ChurchStructureUnit` is the canonical church structure tree, `ChurchStructureMembership` is becoming the canonical ordinary-user belonging model, and legacy small group retirement is consumer-by-consumer. Legacy is not fully retired, `Profile.small_group` must remain until all legacy consumers are migrated or retired, and V2 is not fully structure-native yet.

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
- **V2 still has a legacy `SmallGroup` generation bridge.** Meeting generation and schedule eligibility resolve selected structure units to legacy `SmallGroup` rows through `resolve_units_to_small_groups` (`studies/models.py` wrapper over `accounts/structure_selectors.py`), and generated `BibleStudyMeeting` rows still attach to legacy `SmallGroup`.
- **V2 ordinary-member meeting visibility already uses membership-core logic.** `BibleStudyMeeting.can_be_seen_by()` (`studies/models.py`) delegates to `studies/visibility.py`, matching the user's single active primary `ChurchStructureMembership` against the meeting legacy `SmallGroup`'s mapped small-group unit or a descendant (CS-CORE.2C-B). `Profile.small_group` alone grants nothing here.
- **V2 role/worship user pickers use membership-core matching** for the meeting's legacy `SmallGroup` (CS-CORE.3B).

So V2 is the structure-model investment target, but V2 is not fully structure-native yet: the generation bridge and the `BibleStudyMeeting.small_group` FK still depend on legacy `SmallGroup` rows and mappings.

## 4. Current V1 State (verified against the worktree on 2026-06-12)

V1 still exists but is no longer the promoted surface:

- **`/studies/` keeps the historical view name `study_session_list`** (`studies/urls.py`), but the page now behaves as the V2 Bible Study landing surface: the view builds `get_v2_landing_context()` and the template (`templates/studies/study_session_list.html`) renders the user's V2 `BibleStudyMeeting` plus V2 staff links (schedules / weekly guides / meetings) only. The promoted member-facing UI shows V2 meetings, not legacy V1 sessions.
- **Today uses V2 `BibleStudyMeeting`**, not legacy `BibleStudySession`: `reading/views.py` reuses `get_v2_landing_context()` and surfaces linked-user `BibleStudyMeetingRole` chips.
- **Staff surfaces promote V2** schedules / guides / meetings: the staff overview counts `BibleStudySeries` / `BibleStudyLesson` / `BibleStudyMeeting` (`accounts/views.py`), and the `/studies/` staff links target the V2 manage lists. No promoted staff surface counts or links legacy V1 sessions.
- **V1 direct routes still exist** (`studies/urls.py`): `studies/new/`, `studies/<int:session_id>/`, `studies/<int:session_id>/edit/`, `studies/<int:session_id>/delete/`, `studies/<int:session_id>/worship/` (plus V1 worship-song edit/delete routes).
- **V1 forms/templates/admin/tests still exist**: `BibleStudySessionForm` (`studies/forms.py`), `templates/studies/study_session_detail.html` and `study_session_form.html`, `BibleStudySessionAdmin` (`studies/admin.py`), and `BibleStudySession` coverage in `studies/tests.py`.
- **V1 visibility is still legacy-driven**: `BibleStudySession.can_be_seen_by()` (`studies/models.py`) still uses legacy `Profile.small_group` / `District` / `SmallGroup` `scope_type` semantics. Per this decision, that stays as-is until V1 is retired; do not migrate V1 `BibleStudySession` visibility to membership-core.

## 5. Recommended Future Implementation Path

Each remaining step below is future work requiring its own approval. CS-CORE.3D is the only runtime step recorded here as complete.

1. **Step 1:** Confirm no promoted normal/staff UI links create or manage new V1 sessions (the `/studies/` landing and staff overview already promote V2 only; re-verify before any runtime slice).
2. **Step 2:** Convert any remaining promoted V1 entry points to V2 schedule/lesson/meeting flows.
3. **Step 3:** Completed by CS-CORE.3D for app-level creation only: `studies/new/` redirects to `/studies/` with retirement messaging and no longer renders or processes the V1 creation form.
4. **Step 4:** Keep existing V1 records readable until a data/archive policy is approved.
5. **Step 5:** Continue reducing V2's legacy `SmallGroup` bridge in a later architecture slice (generation source and `BibleStudyMeeting.small_group` ownership; see `docs/CHURCH_STRUCTURE_CORE_MIGRATION_PLAN.md` Section 12).
6. **Step 6:** Do not delete V1 tables/models/data until the project has a formal data retirement policy.

## 5A. CS-CORE.3D Runtime Freeze Status

CS-CORE.3D freezes new legacy V1 `BibleStudySession` creation through the app route only.

- `GET /studies/new/` redirects to `/studies/` and does not render the V1 creation form.
- `POST /studies/new/` redirects to `/studies/` and does not create a `BibleStudySession` or `BibleStudyGuide`.
- Existing V1 records remain readable through direct allowed detail paths.
- V1 direct detail/edit/delete/worship routes and Django Admin remain in place.
- `BibleStudySessionForm`, `BibleStudySessionAdmin`, and `BibleStudySession.can_be_seen_by()` remain in place.
- V1 visibility is still legacy-driven by `Profile.small_group` / legacy scope semantics.
- V1 is not fully retired yet; no V1 data, model, table, or migration was removed by this slice.

## 6. Non-Goals

CS-CORE.3C did not include or authorize, and CS-CORE.3D still does not include or authorize:

- any template, URL, form, model, schema, or migration change;
- deletion of any V1 data;
- removing V1 detail/edit/delete/worship routes, forms, admin, model behavior, or legacy visibility;
- reading/progress/privacy migration;
- ServiceEvent fallback migration;
- permissions/roles/ministry/team assignment migration;
- any attempt to fully remove `SmallGroup` or `Profile.small_group`.

## 7. Verification

CS-CORE.3C was a docs-only decision record and needed no Django tests. CS-CORE.3D is a runtime freeze and should use targeted route/view tests plus the standard lightweight Django checks.

Recommended lightweight verification for CS-CORE.3D:

```powershell
python manage.py makemigrations --check
python manage.py check
python manage.py test studies.tests.BibleStudyModuleTests.test_user_with_pastor_role_is_redirected_from_create_page studies.tests.BibleStudyModuleTests.test_manager_post_to_create_route_does_not_create_session_or_guide -v 2
git diff --check
```
