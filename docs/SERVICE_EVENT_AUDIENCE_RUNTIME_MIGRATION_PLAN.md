# ServiceEvent Audience Runtime Migration Plan

## 1. Purpose and Status

SE-AS.3 recorded the implementation plan for migrating ServiceEvent / Church Gatherings audience scope from the legacy `scope_type` / `district` / `small_group` fields toward the `ChurchStructureUnit` audience-scope foundation (`ServiceEventAudienceScope`).

Status: SE-AS.3 is complete as docs-only planning. SE-AS.4 is complete as the runtime visibility rule with legacy fallback: events with one or more `ServiceEventAudienceScope` rows use those audience rows for ordinary-user visibility; events with zero rows keep the existing legacy `scope_type` / `district` / `small_group` plus `Profile.small_group` behavior. SE-AS.5 is complete as the staff selector UI/display: staff can select optional `ChurchStructureUnit` audience rows on single create/edit and recurring create; staff detail shows effective audience source and readable labels. Historical note: at SE-AS.4/SE-AS.5 time, audience-row matching was not yet membership-core; CS-CORE.2B-A later switched ServiceEvent audience-row matching to active primary `ChurchStructureMembership`, while zero-row events still use legacy fallback. Legacy scope fields remain preserved/editable as fallback. SE-AS.6B is complete as an audit-only dry-run command, including SE-AS.6B.1 verbose output polish. SE-AS.6C is complete as an explicit `--apply` mode on the same command (dry-run remains the default; apply creates `ServiceEventAudienceScope` rows only for parity-safe `would-create` events, never mutating legacy fields, and is idempotent). **SE-AS.6C production apply is complete:** it has been run against production, so all 37 production ServiceEvents now have audience rows; the post-apply dry-run reports skipped-existing-rows 37, would-create 0, parity-mismatch 0, and legacy-fields-mutated 0 (details below). The zero-row legacy fallback is not retired; it remains only as a runtime safety net. SE-AS.7A is complete as the write-path guard that stops normal create/edit/recurring flows from saving new zero-row legacy-fallback events (details below). No setup/edit UI, CS-MAP.3, CS-SETUP.1, Community Activities, schema change, or migration was added.

Milestone renumbering note: `docs/SERVICE_EVENT_AUDIENCE_SCOPE_REDESIGN_PLAN.md` (SE-AS.1) originally labeled "SE-AS.3" as the future staff create/edit UI. This plan re-scopes SE-AS.3 as the runtime migration plan itself and renumbers later milestones (see Section 5). Where older docs say "SE-AS.3 staff UI selector," that work is now SE-AS.5 in this plan.

SE-AS.5A is complete as the docs-only staff audience selector interaction plan in `docs/SERVICE_EVENT_AUDIENCE_SELECTOR_INTERACTION_PLAN.md`. SE-AS.5 implementation is complete.

SE-AS.6A is complete as a docs-only planning checkpoint. It records the backfill / compatibility contract, hard invariants, parity requirement, and report categories in Section 8A, and recommends splitting any future backfill work into SE-AS.6B (dry-run audit command only) and SE-AS.6C (optional apply after dry-run review). SE-AS.6A adds no management command, test, schema, migration, or runtime change.

SE-AS.6B is complete as the dry-run audit command. The `backfill_service_event_audience_scopes` management command (in the `events` app) scans `ServiceEvent` rows read-only and reports the Section 8A.5 categories; by default it creates no `ServiceEventAudienceScope` rows and mutates no legacy field, unit, membership, profile, or group. SE-AS.6B.1 is complete as verbose-output polish: `--verbose-events` prints event id, title/date when available, legacy scope/status, decision category, proposed unit label/path when available, and reason text.

SE-AS.6C is complete as the explicit apply mode on the same command. Adding `--apply` makes the command create `ServiceEventAudienceScope` rows for events the dry-run classifies as parity-safe `would-create`; without `--apply` the command stays a read-only dry-run that changes nothing. Dry-run and apply share one decision path (`_scan_events`), so apply can never act on an event the dry-run would not have reported. Apply runs in a single atomic transaction, skips events that already have audience rows, is idempotent (a second run creates `0` additional rows), and never mutates `ServiceEvent.scope_type` / `district` / `small_group` / `ministry_context`, `ChurchStructureUnit`, `ChurchStructureMembership`, `Profile`, `SmallGroup`, `District`, or `MinistryContext`. Apply-mode output is clearly distinguished (`APPLY mode` header) and adds a `created audience rows : N` count; `legacy-fields-mutated (must be 0)` stays `0`.

SE-AS.6C parity correction (current-runtime parity): the parity check compares **pre-backfill legacy zero-row visibility** (matched directly through `Profile.small_group`) against **post-backfill membership-core visibility** (the active primary `ChurchStructureMembership` rule the runtime actually applies once an event has rows, per CS-CORE.2B-A), via the canonical `accounts.structure_selectors.user_matches_structure_audience` matcher. It no longer uses `studies.models.resolve_units_to_small_groups()` as the proposed post-row audience truth. The command compares the actual ordinary-user ID sets the two rules produce (managers excluded, since `can_be_managed_by` overrides both paths); if creating a row would add or drop even one ordinary user, the event is classified parity-mismatch and skipped. Global events still map to the active root unit, which both rules treat as all authenticated users, so global backfill stays parity-safe by construction.

Production-data dry-run review caveat (historical, now resolved): the previously captured GoDaddy dry-run (37 scanned / 1 skipped-existing / 36 would-create / 0 root skipped / 0 district skipped / 0 small-group skipped / 0 parity mismatch / 0 legacy mutation) was produced by the **old legacy-resolver parity logic** and was therefore not treated as final apply approval. The production-data dry-run was subsequently rerun under the corrected membership-core parity logic, re-reviewed, and the production apply was run (see the completion note below). The zero-row legacy fallback remains in place as a runtime safety net and is **not** retired.

SE-AS.6C production apply — completed. The corrected membership-core apply has now been run against production: all 37 production ServiceEvents have `ServiceEventAudienceScope` rows, and a dry-run rerun after apply reports `skipped existing rows: 37`, `would-create: 0`, `parity-mismatch: 0`, and `legacy-fields-mutated: 0`. No legacy field was mutated and the zero-row runtime fallback remains in place as a safety net. This records a completed real-database apply; it does not retire the fallback or change the runtime rule.

SE-AS.7A is complete as the write-path guard that stops new zero-row legacy-fallback events. With production backfilled, ordinary ServiceEvent create/edit/recurring write paths now refuse to save an event into the zero-`ServiceEventAudienceScope` legacy-fallback state. When staff select audience units, those rows are saved as before. When staff leave the audience picker empty, the legacy `scope_type` / `district` / `small_group` fields are converted into a structure audience row using the same mapping rules as the SE-AS.6 backfill: `global` -> the single active root unit; `district` -> `district.church_structure_unit` when present and active; `small_group` -> `small_group.church_structure_unit` when present and active. The conversion lives in the new app helper `events.forms.resolve_legacy_service_event_scope_to_structure_units(...)`, enforced authoritatively in form validation (`AudienceUnitOptionsMixin.clean_resolved_audience_units`) on both `ServiceEventForm` (single create/edit) and `RecurringServiceEventForm` (recurring create); the recurring create view persists the resolved units to every created event. If the required mapping is missing, inactive, or the active root is missing/ambiguous, form validation fails with clear bilingual copy and saves nothing (no event, no rows) rather than silently dropping into the zero-row fallback. Edit saves are held to the same rule: clearing the audience selection converts the legacy fields instead of leaving zero rows. There is no ordinary emergency/admin-only zero-row write path in these forms, so none was preserved. SE-AS.7A does **not** delete legacy fields, does **not** remove the runtime fallback, does **not** change Bible Study or TeamAssignment / My Serving / required-team logic, and adds no data migration: `ServiceEvent.can_be_seen_by` keeps its zero-row legacy fallback unchanged for events created outside these guarded forms (e.g. directly via the ORM), which remain a safety net. Help text on both forms was updated (bilingual) to say an empty selection is converted from the fallback fields and that saving requires a valid structure mapping.

## 2. Historical State Audit at SE-AS.3 Planning Time

This section is preserved as historical context: it records the state originally audited from docs plus light code reading during SE-AS.3 planning, before SE-AS.4/SE-AS.5 shipped. It does not describe current behavior. Current implemented status is in Section 1 and Sections 5–7.

### 2.1 Legacy runtime visibility at original audit time

- `ServiceEvent.can_be_seen_by` (`events/models.py`):
  - unauthenticated users: denied.
  - users passing `can_be_managed_by` (staff, superuser, `CAP_MANAGE_SERVICE_EVENTS`): always allowed, including drafts.
  - draft/cancelled events: hidden from ordinary users; only published/completed are visible.
  - `scope_type == global`: visible to all authenticated users.
  - `scope_type == district`: visible when `Profile.small_group.district_id` equals `ServiceEvent.district_id`.
  - `scope_type == small_group`: visible when `Profile.small_group.id` equals `ServiceEvent.small_group_id`.
  - Users without a `Profile.small_group` see only global events (plus anything they can manage).
- List/detail views (`events/views.py`): `get_visible_service_events` filters the queryset by calling `can_be_seen_by` per event; event detail checks `can_be_seen_by` directly. There is no separate query-level filter to keep in sync — `can_be_seen_by` is the single visibility gate.
- `ServiceEvent.clean()` enforces legacy scope consistency (global has no district/small_group; district requires district only; small_group requires small_group only).

### 2.2 ServiceEventAudienceScope model-only foundation at original audit time (SE-AS.2)

- Links `ServiceEvent` to `ChurchStructureUnit` (`unit`), CASCADE on event delete, PROTECT on unit delete, unique event+unit constraint.
- Validation: unit must be active at save; redundant ancestor/descendant combinations for the same event are rejected; siblings and cross-branch selections are allowed.
- `ServiceEvent.get_audience_scope_units()` returns selected units.
- No admin surface, form, view, template, management command, or backfill exists. Nothing in the app currently creates these rows, so the table is effectively empty in normal operation.
- It does not affect `can_be_seen_by` or any other runtime behavior.

### 2.3 Adjacent concepts that must not be conflated

- `ServiceEvent.ministry_context` — Host / Language Label / 主办/语言标签 only. Display label; never visibility, serving, or permissions.
- `ServiceEvent.required_teams` (`ServiceEventRequiredTeam`) — Required Ministry Teams: event-level coverage expectations, compared against assignments for coverage display. Not audience.
- `ServiceEvent.rotation_anchor_team` — scheduling suggestion anchor only (MO-S.5A/5B copy-forward). Not audience or permission.
- `TeamAssignment` / `TeamAssignmentMember` — actual serving assignments, managed by staff/global assignment managers/team Lead/Coordinator.
- My Serving (`ministry/views.py: my_serving_assignments`) — queries `TeamAssignmentMember` rows for the user directly. It excludes draft/cancelled events and cancelled assignments but never calls `can_be_seen_by`. A user assigned to serve sees their assignment even if they are outside the event audience. This behavior must be preserved by the runtime migration.
- Staff management pages (event create/edit/batch-create, coverage display, team schedule workspace) — gated by `can_be_managed_by` / team-scoped scheduling permissions, not by audience scope.
- `ChurchStructureMembership` — future belonging source. Backfilled and approvable, but no runtime consumer uses it for visibility. Requested/unapproved memberships grant nothing.

### 2.4 Relevant proven pattern from Bible Study

- `BibleStudySeriesAudienceScope` is the first narrow runtime consumer: `resolve_units_to_small_groups` (`studies/models.py`) resolves selected units to active legacy `SmallGroup` rows via the nullable `church_structure_unit` mapping fields on `MinistryContext`, `District`, and `SmallGroup` (root unit → all active groups; otherwise selected units plus descendants matched against the three mapping fields). Ordinary visibility stays on `Profile.small_group`.
- The BS-AS.2 reusable audience picker partial (searchable, chips, no-JS fallback, backend validation authoritative) is the UI pattern to reuse.
- `seed_church_structure_units` already seeds a `CHURCH` root and mirrors legacy structure with mapping fields; production/staging seeding is verified (CS-H.3C/3D/3E).

## 3. Concept Separation (binding for all later milestones)

| Concept | Source | Role |
| --- | --- | --- |
| Audience Scope / 适用范围 | `ServiceEventAudienceScope` units when rows exist; otherwise legacy `scope_type`/`district`/`small_group` fallback | Who the event/gathering is for. The only concept this plan migrates. |
| Host / Language Label / 主办/语言标签 | `ServiceEvent.ministry_context` | Display label only. Never visibility. |
| Required Ministry Teams / 需要的事工团队 | `ServiceEventRequiredTeam` | Which teams need coverage. Not audience. |
| Rotation Anchor Team / 配搭参考团队 | `ServiceEvent.rotation_anchor_team` | Scheduling suggestion anchor only. |
| TeamAssignment / 服事安排 | `TeamAssignment(Member)` | Actual serving assignment. |
| My Serving / 我的服事 | user's `TeamAssignmentMember` rows | User's own assignments; independent of audience. |
| ChurchStructureMembership | membership rows (approved/requested) | As of CS-CORE.2B-A, the active primary membership is the runtime visibility source for ServiceEvent rows that **have** audience rows (via `user_matches_structure_audience`). Zero-row events still fall back to legacy `Profile.small_group`. Requested/unapproved/inactive memberships grant nothing. This plan does not change the membership model itself. |

Note: SE-AS.1 used "Coverage Scope / 覆盖对象" as the preferred wording. This plan standardizes on Audience Scope / 适用范围 for the ServiceEvent staff UI; final copy should be confirmed once at SE-AS.5 implementation so both docs and UI agree.

## 4. Runtime Migration Strategy Decision

The core risk: staff must never believe an audience selector controls visibility while it is actually model-only or display-only.

### Option A: Selector UI first, legacy fields keep controlling visibility

- Pros: smallest first UI slice; staff can pre-populate audience data; runtime change ships later against real data.
- Cons: the selector is a lie until runtime ships — it looks like it controls who sees the event but does not.
- User/staff confusion risk: high. Even with warning help text, a staff member who selects "District A" and sees no visibility effect (or assumes one) can mis-publish.
- Permission/visibility risk: low in code (no runtime change), high operationally (staff acting on a false mental model).
- Migration complexity: low per slice, but creates a window where stored audience rows and legacy fields can drift before the runtime rule exists.
- Rollback: trivial (hide selector); stored rows remain inert.
- Verdict: rejected. The confusion window is exactly the failure mode this plan must avoid.

### Option B: Selector UI + runtime visibility migration in one milestone (legacy fallback when no rows)

- Pros: no confusion window — the day the selector appears, it really controls visibility; fallback keeps old events unchanged.
- Cons: one large milestone bundling a permission-affecting runtime change with new UI, forms, validation, and display; harder to review and QA in one slice; violates the project's small-slice discipline.
- User/staff confusion risk: low.
- Permission/visibility risk: medium — runtime change and UI bugs land together, so a selector bug can directly cause a visibility leak in the same release.
- Migration complexity: highest single-release complexity.
- Rollback: must roll back UI and runtime together; deleting audience rows restores legacy behavior per event.
- Verdict: acceptable but bundles too much.

### Option C (recommended): Keep selector hidden until runtime is ready; ship runtime first, then selector

- Sequence: implement and fully test the new `can_be_seen_by` rule with legacy fallback first (SE-AS.4). Because nothing in the app creates `ServiceEventAudienceScope` rows yet, this change is behavior-inert at ship time: every event falls back to legacy fields, and targeted tests prove parity. Then ship the staff selector + display (SE-AS.5) on top of an already-proven runtime rule.
- Pros: each release is narrow; the runtime rule is tested and live before any staff can create audience rows; when the selector appears it genuinely controls visibility from day one; per-event rollback is "delete the audience rows."
- Cons: the runtime code path for audience rows is briefly live but unexercised in production between SE-AS.4 and SE-AS.5 (mitigated by the test matrix in Section 10); two releases instead of one.
- User/staff confusion risk: minimal — staff never see an inert selector.
- Permission/visibility risk: lowest — the only release that changes visibility logic changes no observable behavior, and the only release that changes staff workflow reuses a proven rule.
- Migration complexity: moderate, spread across two small slices.
- Rollback strategy: SE-AS.4 can be reverted cleanly (no data depends on it); after SE-AS.5, removing an event's audience rows reverts that event to legacy behavior; disabling the selector reverts the workflow without data loss.

Decision: Option C, with the runtime rule shipped first as an inert, fallback-complete slice, then the selector. Option B's "fallback to legacy when no rows" rule is still adopted as the runtime rule itself.

## 5. Phased Milestones

Each milestone is separately approved and intentionally narrow.

### SE-AS.3 — Runtime Migration Plan (this document)

Docs-only. Complete. No code changes.

### SE-AS.4 — Runtime Visibility Rule with Legacy Fallback

Completed. `ServiceEvent.can_be_seen_by` now applies the Section 6 rule: staff/superuser/service-event managers keep the existing override; draft/cancelled and non-published statuses stay hidden from ordinary users; events with `ServiceEventAudienceScope` rows use those rows for ordinary-user visibility; events with no rows fall back to legacy `scope_type` / `district` / `small_group` and `Profile.small_group` behavior exactly.

Implementation notes:

- Unit matching reuses `studies.models.resolve_units_to_small_groups()` so ServiceEvent and Bible Study Schedule share the same `ChurchStructureUnit` to legacy `SmallGroup` resolution semantics.
- Root unit rows behave like legacy global scope and match all authenticated ordinary users, including users without a current small group.
- Non-root rows matched only through the user's current `Profile.small_group` **at SE-AS.4 time**; `ChurchStructureMembership` was not consulted then. **Superseded by CS-CORE.2B-A:** non-root audience-row matching now uses the user's single active primary `ChurchStructureMembership` (see Section 1 and the canonical `accounts.structure_selectors.user_matches_structure_audience`). Zero-row events still fall back to `Profile.small_group`.
- Stored rows whose units are later deactivated keep matching per the Section 7 parity decision.
- SE-AS.4 itself added no selector UI, no ServiceEvent form/template audience picker, no backfill command, no Community Activities, no CS-MAP.3, and no CS-SETUP.1 work. SE-AS.5 later added the selector/display only.

### SE-AS.5 — Staff Audience Selector UI and Display

Completed. Planning preflight SE-AS.5A is complete in `docs/SERVICE_EVENT_AUDIENCE_SELECTOR_INTERACTION_PLAN.md`.

- Reuses the BS-AS.2 audience picker partial on ServiceEvent single create/edit and recurring batch-create.
- **SE-AS.5-time write behavior, superseded by SE-AS.7A:** at SE-AS.5 an empty picker saved zero rows and kept legacy fallback; single edit clearing all units deleted rows and restored legacy fallback; legacy fields were not auto-converted into rows. **After SE-AS.7A this is no longer how the normal write paths behave** — see the SE-AS.7A bullet below. The SE-AS.5 selector/display UI itself (picker reuse, preselection, staff/ordinary display) is unchanged.
- Recurring create applies one selected audience set to all newly created events; preview creates no rows; skipped duplicates are not modified or backfilled.
- Staff detail displays effective source (`Structure audience` or `Legacy fallback audience`) plus readable labels and an unmapped-selection warning when selected units resolve to no active legacy groups.
- Ordinary detail does not expose structure/fallback architecture terms, model names, unit IDs, or unit codes.
- Backend validation remains authoritative (active unit, no ancestor/descendant redundancy).
- Legacy scope fields remain editable and are visually grouped/labeled as fallback audience settings during the transition; an event with audience rows is governed by those rows, and an event without rows keeps legacy runtime behavior (the zero-row runtime fallback is unchanged).

### SE-AS.6 — Backfill, Compatibility Monitoring, and Cleanup Planning

Backfill is optional and is not a prerequisite for ServiceEvent correctness (see Section 8A). It is now split into a docs-only checkpoint plus two narrow future implementation slices:

- **SE-AS.6A — docs-only planning checkpoint (complete with this task).** Records the future backfill / compatibility contract, hard invariants, parity requirement, dry-run report categories, and risk areas in Section 8A. No command, test, schema, migration, or runtime change.
- **SE-AS.6B — dry-run audit command only (complete).** Implements `backfill_service_event_audience_scopes` (in the `events` app) as a read-only audit that scans events and reports the Section 8A categories. It creates nothing and has no `--apply` path. SE-AS.6B.1 verbose-output polish is complete: `--verbose-events` prints event id, title/date when available, legacy scope/status, decision category, proposed unit label/path when available, and reason text.
- **SE-AS.6C — apply mode (implemented, with CS-CORE.2B-A parity correction).** Adds an explicit `--apply` to the same command that creates audience rows only for events proven parity-safe by the dry-run rules. Dry-run remains the default; apply shares the dry-run decision path, runs in one atomic transaction, skips events that already have rows, is idempotent, mutates no legacy field, and reports a `created audience rows` count. **Parity is current-runtime parity:** pre-backfill legacy zero-row visibility (`Profile.small_group`) vs post-backfill membership-core visibility (active primary `ChurchStructureMembership` via `user_matches_structure_audience`), not the legacy `resolve_units_to_small_groups` resolver. The earlier GoDaddy dry-run (37 scanned / 1 skipped-existing / 36 would-create / 0 skipped / 0 parity mismatch / 0 legacy mutation) was produced by the **old legacy-resolver parity logic** and was not used as apply approval; the production-data dry-run was rerun under the corrected membership-core logic, re-reviewed, and **the production apply has now been run** (all 37 production ServiceEvents have audience rows; post-apply dry-run: skipped-existing 37 / would-create 0 / parity-mismatch 0 / legacy-fields-mutated 0). The zero-row legacy fallback is not retired by this slice; it remains a runtime safety net.
- **Later — legacy fallback deprecation planning (future, separate approval).** Plan-only evaluation of eventual legacy `scope_type` / `district` / `small_group` field deprecation (the old SE-AS.6 scope from SE-AS.1); no destructive change until audience rows have proven stable in production.

Staff/admin clarity for which source governs each event (audience rows vs legacy fallback) already shipped with SE-AS.5 staff detail display.

### SE-AS.7A — Stop new zero-row legacy-fallback writes

Completed. With production backfilled (SE-AS.6C apply), the normal ServiceEvent write paths now refuse to save an event into the zero-`ServiceEventAudienceScope` legacy-fallback state. This supersedes the SE-AS.5-time write behavior noted above.

- Single create, single edit, and recurring create: when staff select audience units, those rows are saved as before.
- When staff leave the picker empty, the legacy `scope_type` / `district` / `small_group` fields are converted into a structure audience row using the same mapping rules as the SE-AS.6 backfill: `global` -> the single active root unit; `district` -> `district.church_structure_unit` when present and active; `small_group` -> `small_group.church_structure_unit` when present and active.
- Single edit clearing all units converts the legacy fields the same way instead of leaving zero rows; recurring create converts for every newly created event; preview still creates no rows.
- If the required mapping is missing, inactive, or the active root is missing/ambiguous, form validation fails with clear bilingual copy and saves nothing (no event, no rows) rather than silently dropping into the zero-row fallback. Backend validation is authoritative.
- Conversion lives in the app helper `events.forms.resolve_legacy_service_event_scope_to_structure_units(...)`, enforced in `AudienceUnitOptionsMixin.clean_resolved_audience_units` on `ServiceEventForm` and `RecurringServiceEventForm`. Form help text (bilingual) now says an empty selection is converted from the fallback fields and that saving requires a valid, active structure mapping.
- Non-goals (unchanged by SE-AS.7A): legacy `scope_type` / `district` / `small_group` fields are not deleted; the runtime zero-row fallback in `ServiceEvent.can_be_seen_by` is not removed (events created outside these guarded forms, e.g. directly via the ORM, still use it as a safety net); Bible Study, TeamAssignment / My Serving, and required-team logic are unchanged; no schema, migration, or data migration was added.

## 6. Recommended Future `ServiceEvent.can_be_seen_by` Rule

Implemented by SE-AS.4. The runtime rule, in order:

1. Unauthenticated users: denied (unchanged).
2. `can_be_managed_by` (staff, superuser, `CAP_MANAGE_SERVICE_EVENTS`): allowed, including drafts (unchanged — managers keep broader access).
3. Draft/cancelled, or any non-published/completed status: denied for ordinary users (unchanged).
4. If the event has one or more `ServiceEventAudienceScope` rows: those rows are the audience source. The user is in the audience iff they match the selected units. **At SE-AS.4 time this matched via Section 7 (`Profile.small_group`); as of CS-CORE.2B-A it matches via the user's single active primary `ChurchStructureMembership`** through `accounts.structure_selectors.user_matches_structure_audience` (root rows still match all authenticated users).
5. Otherwise (no audience rows): fall back to legacy `scope_type` / `district` / `small_group` exactly as today, matched through `Profile.small_group`.
6. **Zero-row (fallback) matching** uses `Profile.small_group` only. **Audience-row matching** now consults active primary `ChurchStructureMembership` (CS-CORE.2B-A); in both paths requested/unapproved/inactive memberships must never grant visibility. (The earlier statement that audience-row matching never consults membership applied only before CS-CORE.2B-A.)

Justification: the fallback rule means the migration never has a flag-day; every existing event is untouched until staff (or an explicit backfill) give it audience rows, and removing rows restores legacy behavior per event.

## 7. Unit-to-User Resolution for Ordinary Users

**Scope note (CS-CORE.2B-A correction).** This section describes the **legacy `Profile.small_group` resolver** (`resolve_units_to_small_groups`) only. As shipped at SE-AS.4 this was also how ServiceEvent audience rows matched, but **that is no longer current ServiceEvent behavior**: as of CS-CORE.2B-A a ServiceEvent that has audience rows matches ordinary users through the user's single active primary `ChurchStructureMembership` via `accounts.structure_selectors.user_matches_structure_audience`, **not** through `Profile.small_group`. The `Profile.small_group` resolver below now describes (a) the **zero-row legacy fallback** for ServiceEvents and (b) the separate **Bible Study** generation/visibility path, which still resolves through `Profile.small_group`. Read this section as legacy/Bible-Study resolver semantics, not as the current ServiceEvent audience-row runtime.

Selected `ChurchStructureUnit` rows map to current users through the legacy mapping fields, mirroring the proven Bible Study resolver:

- Root unit selected → all authenticated users (parity with legacy `global`). This is the only case that matches users who have no `Profile.small_group`.
- Otherwise compute the target set = selected units plus all their descendants, then a user with `Profile.small_group` matches when any of:
  - `Profile.small_group.church_structure_unit` is in the target set (small-group unit selected);
  - `Profile.small_group.district.church_structure_unit` is in the target set (district unit selected);
  - `Profile.small_group.district.ministry_context.church_structure_unit` is in the target set (ministry-context unit selected, e.g. CM/EM).
- Equivalently: the user matches iff their current small group is in the resolved eligible-group set for the selected units. Reusing one resolver keeps Bible Study and ServiceEvent semantics identical.
- Custom or unmapped units (no legacy mapping anywhere beneath them) match no ordinary users until separately mapped. They are not an error; staff display should make the empty ordinary-audience consequence visible.
- Multi-unit selections are a union: sibling and cross-branch selections each contribute their matched users.
- Inactive units: validation prevents selecting inactive units, but a stored selection whose unit later becomes inactive should keep matching for parity and historical continuity (legacy district/small-group checks do not test `is_active` either). SE-AS.4 confirmed this with an explicit test; if product later wants inactive units to stop matching, that is a deliberate behavior choice to record, not an accident.

## 8. Migration / Backfill Strategy

Backfill is optional, not required for correctness: the fallback rule keeps every legacy event behaving identically with zero audience rows. Recommended only as a later convergence step (SE-AS.6), after the selector has been in real use.

If/when a management command is approved (suggested name `backfill_service_event_audience_scopes`):

- `scope_type=global` → one row pointing at the root unit, only if exactly one active root unit exists; otherwise skip.
- `scope_type=district` → one row pointing at `district.church_structure_unit`, only if the mapping exists and the unit is active; otherwise skip.
- `scope_type=small_group` → one row pointing at `small_group.church_structure_unit`, only if the mapping exists and the unit is active; otherwise skip.
- Unmapped or ambiguous events: leave zero audience rows; legacy fallback keeps governing them. Report them in command output.
- Never create root or structure units; seeding stays exclusively in `seed_church_structure_units`.
- Never mutate or clear legacy `scope_type` / `district` / `small_group` during backfill — non-destructive only.
- Skip events that already have audience rows (idempotent; re-running changes nothing).
- Dry-run by default (or require an explicit `--apply`), reporting per-scope counts: would-create, skipped-unmapped, skipped-existing, skipped-ambiguous-root.
- Acceptance check: for every backfilled event, the new rule's ordinary-user audience equals the legacy rule's audience (tested at the command level before any production apply, then verified by production dry-run output review).

Note that backfilling `global` events is pure convergence with no behavior difference (root ≡ global), so a conservative first apply may backfill district/small_group events only, or nothing at all.

## 8A. SE-AS.6A Backfill / Compatibility Planning Checkpoint (docs-only)

SE-AS.6A is a **docs-only planning checkpoint, not implementation**. It defines the contract that any future backfill work (SE-AS.6B audit, SE-AS.6C apply) must satisfy. It adds no management command, test, schema, migration, or runtime change. Section 8 above remains the high-level strategy; this section is the binding contract that supersedes it where they differ.

### 8A.1 Backfill is optional, not required for correctness

- The SE-AS.4 fallback rule makes a ServiceEvent with **zero `ServiceEventAudienceScope` rows** behave exactly as it did under the legacy `scope_type` / `district` / `small_group` + `Profile.small_group` rule. Zero audience rows are therefore always safe.
- Backfill is a **convergence / operational cleanup** step (moving legacy events onto explicit structure rows), not a prerequisite for ServiceEvent visibility correctness. The product is correct with no backfill ever run.
- Nothing depends on backfill having been run. It can be deferred indefinitely, run partially (for example district/small-group events only), or skipped entirely.

### 8A.2 Future command contract (`backfill_service_event_audience_scopes`)

- **Dry-run / audit first.** The first implementation slice (SE-AS.6B) is a read-only audit that scans events and reports the Section 8A.5 categories. It creates, edits, or deletes nothing.
- **No automatic apply in SE-AS.6A**, and no apply in SE-AS.6B. SE-AS.6A is docs-only; SE-AS.6B is audit-only.
- **Apply is a separate, later slice (SE-AS.6C)** behind an explicit `--apply` flag, approved only after SE-AS.6B dry-run output has been reviewed against real production data. Apply creates rows only for events the dry-run rules proved parity-safe (8A.4).
- The command is idempotent: re-running the dry-run reports the same categories; re-running apply changes nothing for events that already have rows.

### 8A.3 Hard invariants (binding on SE-AS.6B and SE-AS.6C)

A future command must **never**:

- Mutate, clear, or rewrite `scope_type`, `district`, or `small_group` on any event. Backfill is additive (it only creates `ServiceEventAudienceScope` rows) and non-destructive to legacy fields.
- Create, edit, deactivate, move, or otherwise modify `ChurchStructureUnit` rows. Unit seeding stays exclusively in `seed_church_structure_units`.
- Use `ChurchStructureMembership` as a backfill **mapping input** (the proposed unit is derived only from the legacy `church_structure_unit` mapping of the event's district/small group, never from membership rows). Note (CS-CORE.2B-A correction): membership **is** the runtime visibility source for events that have audience rows, so the parity check legitimately reads active primary membership to compute the proposed post-row audience; it just must not use membership to choose which unit to map an event to.
- Backfill an event that already has one or more audience rows (skip it; it is already governed by its rows).
- Change My Serving, `TeamAssignment` / `TeamAssignmentMember`, required-team coverage, rotation anchor / copy-forward, `ministry_context` (Host / Language Label), or any other ministry-scheduling behavior.
- Remove, hide, deprecate, or disable the legacy fallback fields. They remain editable fallback fields throughout SE-AS.6.

### 8A.4 Parity requirement (binding)

- For every event a future command proposes to backfill, the ordinary-user visibility **after** creating audience rows must equal the ordinary-user visibility under the **pre-backfill legacy rule**, for every ordinary user. Backfill must be visibility-neutral.
- **Current-runtime parity (CS-CORE.2B-A correction).** Parity is computed against the rule the runtime actually applies, not the legacy resolver: the comparison is **legacy zero-row audience** (matched directly through `Profile.small_group`) vs. **membership-core post-row audience** (active primary `ChurchStructureMembership`, via `accounts.structure_selectors.user_matches_structure_audience`). The command must **not** use `resolve_units_to_small_groups()` as the proposed post-row audience truth for ServiceEvent rows. The comparison is over the actual ordinary-user ID sets the two rules produce, excluding managers (`can_be_managed_by` overrides both paths). Root/global remains parity-safe because both rules treat the active root unit as all authenticated users.
- If parity cannot be proven for an event (unmapped/inactive/ambiguous mapping, or any resolution that would add or drop even one user), the command must **skip** that event, leave zero audience rows on it, and report it.
- The dry-run report must explicitly include **parity-mismatch** and **skipped-for-safety** categories so a reviewer sees exactly which events were not backfilled and why. Silent skips are not acceptable.

### 8A.5 Recommended dry-run report categories (for SE-AS.6B)

The audit report should include at least:

- total events scanned;
- skipped because the event already has audience rows;
- global events mappable to exactly one active root unit;
- global events skipped because the root is missing or ambiguous (zero or multiple active roots);
- district events mapped and parity-safe;
- district events skipped because unmapped, mapped-but-inactive, or otherwise unsafe;
- small-group events mapped and parity-safe;
- small-group events skipped because unmapped, mapped-but-inactive, or otherwise unsafe;
- parity-mismatch skipped (resolved audience would differ from legacy audience);
- events by status if cheap to compute: draft / published / completed / cancelled;
- would-create audience-row count;
- legacy-fields-mutated count, which must always be `0` (a non-zero value is a bug and an apply must abort).

### 8A.6 Staging / production dry-run review checklist

This checklist is a procedure for future staging/production review. It does **not** record that a production or staging dry-run has already been performed.

Before considering SE-AS.6C:

1. Confirm the current branch, deployment target, and database target are the intended staging or production environment.
2. Run a database backup or confirm a current recoverable backup exists before any future apply/backfill discussion.
3. Run the audit command with verbose event output:

   ```bash
   python manage.py backfill_service_event_audience_scopes --verbose-events
   ```

4. Capture the full command output in the deployment/release notes for review.
5. Review the summary totals:
   - total events scanned;
   - skipped because the event already has audience rows;
   - global mappable to a single active root unit;
   - global skipped because the root is missing or ambiguous;
   - district mapped and parity-safe;
   - district skipped because unmapped, mapped-but-inactive, or otherwise unsafe;
   - small-group mapped and parity-safe;
   - small-group skipped because unmapped, mapped-but-inactive, or otherwise unsafe;
   - parity-mismatch skipped;
   - would-create audience-row count;
   - legacy-fields-mutated, which must be `0`.
6. Review every verbose per-event decision line for suspicious mappings, surprising labels, unexpected dates, or unexpected proposed unit paths.
7. Specifically investigate any event categorized as:
   - `skipped-root-missing-or-ambiguous`;
   - `skipped-unmapped`;
   - `skipped-inactive-or-unsafe`;
   - `skipped-parity-mismatch`.
8. Do not proceed to SE-AS.6C if any unexpected mismatch, suspicious mapping, non-zero `legacy-fields-mutated`, or unreviewed skip category appears.

The parity invariant remains binding: for every event proposed as `would-create`, post-backfill ordinary-user visibility must equal pre-backfill legacy visibility. If parity cannot be proven, the event must be skipped and reported; the command must not create rows for that event.

SE-AS.6B.1 does not approve apply/backfill. SE-AS.6C remains unapproved and requires a separate explicit approval after real dry-run output has been captured and reviewed.

### 8A.7 Risk areas to keep visible

- **Active/inactive mapping assumptions must not silently change visibility.** Validation forbids selecting inactive units at create time, but the runtime rule keeps matching a stored row whose unit later went inactive (Section 7 parity decision). Backfill must not exploit or contradict this: it maps only through currently-active mappings and skips when the mapping is inactive, so a backfilled row never changes who can see an event versus the legacy rule.
- **Custom / unmapped units may match no ordinary users.** A unit with no legacy `SmallGroup` mapping at or beneath it resolves to an empty ordinary audience. Backfill must not point a legacy event at such a unit when the legacy rule matched real users — that would fail parity and must be skipped.
- **Root maps to all authenticated users, including users without `Profile.small_group`.** This is the only mapping that reaches users with no current small group, and it is the correct parity target for legacy `global` events.
- **Non-root post-row matching depends on active primary `ChurchStructureMembership`, not `Profile.small_group` (CS-CORE.2B-A correction).** Once an event has audience rows the runtime matches a non-root district/small-group row through the user's single active primary membership unit. District/small-group backfill is therefore parity-safe only when, for every ordinary user, the legacy `Profile.small_group` rule and the membership-core rule pick the same users — i.e. legacy group and active primary membership are aligned. A user who matched the legacy rule via `Profile.small_group` but has no active primary membership (or whose membership points elsewhere) is a parity mismatch and forces the event to be skipped. (Earlier revisions of this plan incorrectly stated both sides resolve through `Profile.small_group`; that was the pre-CS-CORE.2B-A behavior.)

### 8A.8 Recommended future milestone split

- **SE-AS.6A** — docs-only planning checkpoint (this task).
- **SE-AS.6B** — dry-run audit command only, no apply. Reports the 8A.5 categories; creates nothing. SE-AS.6B.1 verbose output polish is complete.
- **SE-AS.6C** — apply mode (implemented; parity corrected to current-runtime membership-core per CS-CORE.2B-A). Creates rows only for parity-safe events behind an explicit `--apply`; dry-run stays the default. The earlier GoDaddy dry-run (Section 1) used the old legacy-resolver parity logic; the production-data dry-run was rerun under the corrected membership-core parity, re-reviewed, and **the production apply has now been run** (all 37 production ServiceEvents have audience rows; post-apply dry-run: skipped-existing 37 / would-create 0 / parity-mismatch 0 / legacy-fields-mutated 0).
- **SE-AS.7A** — stop new zero-row legacy-fallback writes (implemented; see Section 5). Normal create/edit/recurring write paths convert an empty audience selection from the legacy fields into a structure audience row, or reject the save when the mapping is missing/inactive/ambiguous; the runtime zero-row fallback is kept as a safety net, not retired.
- **Later** — legacy fallback deprecation planning, only after audience rows have proven stable in production. No destructive change before then; the zero-row fallback is not retired by SE-AS.6C or SE-AS.7A.

## 8B. SE-AS.6C.0 Optional Apply-Mode Preflight Design (docs-only)

SE-AS.6C.0 was the design-only preflight for apply mode. **Status update:** SE-AS.6C apply mode is now implemented (with the CS-CORE.2B-A current-runtime parity correction), so an `--apply` flag now exists. The guardrails in this section remain binding on that implementation and on any production apply. Implementation is **not** approval to run apply against a real database: production apply still requires explicit human action, a current backup, and a fresh production-data dry-run reviewed under the corrected membership-core parity logic.

### 8B.1 Preconditions before SE-AS.6C can be approved

Before any implementation prompt may approve SE-AS.6C apply mode:

1. Staging or production dry-run output has been captured with `--verbose-events`.
2. The captured dry-run output has been reviewed by staff/development reviewers who understand the target data.
3. A current recoverable database backup exists, or the backup process has been confirmed before any future apply discussion.
4. Root ambiguity, unmapped rows, inactive mappings, and parity-mismatch rows have been reviewed event by event.
5. Expected skipped rows are documented, including why each category is safe to leave on legacy fallback.
6. Any unexpected parity mismatch blocks apply until the data, mapping, or implementation plan is corrected and reviewed through another dry-run.

### 8B.2 Future apply-mode guardrails

If SE-AS.6C is later approved, apply mode must satisfy all of these guardrails:

- Dry-run remains the default behavior.
- `--apply` must be explicit; there must be no implicit apply through environment, deployment target, or confirmation prompt alone.
- Apply is additive only.
- Apply may create only `ServiceEventAudienceScope` rows.
- Apply must never mutate `ServiceEvent.scope_type`, `ServiceEvent.district`, or `ServiceEvent.small_group`.
- Apply must never mutate `ChurchStructureUnit`, `ChurchStructureMembership`, `Profile`, `SmallGroup`, `District`, or `MinistryContext`.
- Apply must skip events that already have one or more audience rows.
- Apply may create rows only for events the dry-run classifies as parity-safe.
- Apply must run in an atomic transaction scope appropriate to the approved implementation, so partial creation is not silently treated as success.
- Apply must be idempotent: rerunning it must not duplicate rows or change events already governed by audience rows.
- Apply must report created and skipped counts after it completes, including the same skip categories used by the dry-run review.

### 8B.3 Rollback / recovery design

Legacy fields remain preserved throughout SE-AS.6. Because an event with zero `ServiceEventAudienceScope` rows falls back to legacy `scope_type` / `district` / `small_group`, deleting the created audience rows for a specific event returns that event to legacy fallback behavior.

Rollback must be manual and explicit, not automatic in SE-AS.6C. Any rollback command, bulk deletion helper, or production recovery procedure would require separate approval and its own review guardrails.

### 8B.4 Stop conditions

Do not proceed with apply approval or execution if any of these appear in dry-run review:

- any unexpected parity mismatch;
- active root count is not exactly one for a global apply candidate;
- suspicious proposed unit path, label, or hierarchy placement;
- unexpected inactive mapping;
- any staging or production dry-run count that staff/development reviewers cannot explain;
- any non-zero legacy-field mutation indicator.

### 8B.5 Parity invariant

The parity invariant is binding on any future apply mode: post-backfill ordinary-user visibility must equal pre-backfill legacy visibility for each proposed event. If parity cannot be proven for an event, apply must skip that event and report it; it must not create audience rows.

## 9. Staff UI Strategy (for SE-AS.5)

- Reuse the shared BS-AS.2 `ChurchStructureUnit` audience picker partial (search, chips, tree order, no-JS fallback, vanilla-JS convenience clearing, backend validation authoritative, bilingual aria labels).
- Field wording:
  - Audience Scope / 适用范围 — the picker.
  - Host / Language Label / 主办/语言标签 — the existing `ministry_context` field, kept visually and textually separate (separate form section or distinct help text) so staff cannot read it as audience.
- Because SE-AS.5 ships only after the runtime rule is live (Option C), the selector controls visibility from the day it appears. Do not ship the selector with "this does not affect visibility yet" copy — if the runtime rule is not live, do not show the selector at all.
- Current help-text behavior (SE-AS.7A; supersedes the SE-AS.5-time "leaving it empty keeps the current legacy scope behavior" wording): selecting units controls which members can see this gathering; leaving the picker empty converts the fallback `scope_type` / `district` / `small_group` fields into a structure audience row when a valid, active structure mapping exists; saving requires that valid mapping (missing/inactive/ambiguous mappings reject the save with bilingual copy). The zero-row legacy fallback in `can_be_seen_by` remains runtime safety only and is not the normal write path.
- Show a normalized effective-audience preview before save/publish; warn when the selection matches no ordinary users (custom/unmapped units).
- Ordinary users see readable audience labels only (no codes, IDs, or architecture terms), consistent with the BS-AS.2 compact/chip display with root prefix omitted.
- Batch-create applies one selection to all created events, mirroring required-teams batch behavior.

## 10. Testing / QA Matrix (for SE-AS.4/SE-AS.5 implementation)

Legacy fallback parity:

- Event with zero audience rows: global/district/small_group visibility identical to current behavior for ordinary users (with and without `Profile.small_group`).
- Existing event test suite passes unchanged.

Audience-row visibility (ServiceEvent, membership-core as of CS-CORE.2B-A):

For ServiceEvents that **have** audience rows, ordinary-user matching is through the user's single active primary `ChurchStructureMembership` unit via `accounts.structure_selectors.user_matches_structure_audience`, **not** `Profile.small_group`. (Zero-row events keep the legacy `Profile.small_group` fallback covered under "Legacy fallback parity" above. Bible Study's own audience path is separate and still resolves through `Profile.small_group`.) A non-root row matches when the user's active primary membership unit is the selected unit or a descendant of it; requested/unapproved/inactive memberships never match.

- Root unit row → visible to all authenticated ordinary users, including users with no membership/small group.
- Ministry-context unit row → visible to users whose active primary membership unit is the ministry-context unit or a descendant of it; invisible to the other ministry context.
- District unit row → visible to users whose active primary membership unit is the district unit or a descendant (e.g. a child small-group unit); invisible to sibling districts.
- Small-group unit row → visible only to users whose active primary membership unit is that group's unit; no leakage to unrelated small groups in the same district.
- Multi-unit sibling selection (two groups) and cross-branch selection (CM district + EM group) → union visibility, nothing else.
- Custom/unmapped unit row → no ordinary user sees it; managers still do.
- Unit inactive after selection → behavior matches the Section 7 decision, asserted explicitly.
- User with no active primary membership → sees root-audience events only (and, for zero-row events, whatever the legacy `Profile.small_group` fallback grants).

Boundaries preserved:

- Requested/unapproved (and rejected/ended) `ChurchStructureMembership` grants no visibility in any scenario above.
- Staff/superuser/`CAP_MANAGE_SERVICE_EVENTS` access unchanged, including drafts.
- Draft/cancelled events stay hidden from ordinary users even when they match audience rows.
- My Serving still shows the user's assignments for events outside their audience; assignment exclusion rules (draft/cancelled) unchanged.
- TeamAssignment pages, required-team coverage display, rotation anchor/copy-forward, and team schedule workspace behavior unchanged.
- `ministry_context` (Host / Language Label) has no effect on visibility regardless of audience rows.
- Event list and detail agree (list filtering via `get_visible_service_events` matches per-event `can_be_seen_by`).
- No regression to Bible Study: `BibleStudySeries` scope, meeting generation, and meeting visibility unchanged (especially if the resolver is shared).

Backfill command (SE-AS.6, if approved):

- Dry-run creates nothing and reports accurate counts.
- Apply is idempotent; mapped global/district/small_group events get exactly one correct row; unmapped/ambiguous events get none; legacy fields untouched.
- Post-backfill audience equals pre-backfill legacy audience for every backfilled event.

## 11. Explicit Non-Goals

SE-AS.3 (this task) does NOT implement, and this plan by itself does not authorize:

- Staff audience selector UI or any form/template/admin change.
- Automatic notifications, attendance, availability, swap requests, reminders, automatic scheduling, or checklist.
- Community Activities (still unimplemented; future module reuses the same foundation via its own join model).
- `ChurchStructureMembership` visibility migration for any consumer.
- My Serving redesign or TeamAssignment redesign.
- Deletion or deprecation of legacy `scope_type` / `district` / `small_group` fields.
- Any migration, data backfill, or seed/root creation.

## 12. Open Decisions for Later Milestones

Resolved (kept for history):

- **Resolved.** Final bilingual wording for the picker is Audience Scope / 适用范围. The legacy fallback section wording was Used when no structure audience is selected / 未选择上方范围时使用（旧版） at SE-AS.5B and was updated by SE-AS.7A to Converted when no structure audience is selected / 未选择上方范围时用于转换, reflecting that an empty selection is now converted from the fallback fields on save.
- **Resolved.** Legacy scope field editability: keep `scope_type`, `district`, and `small_group` editable, grouped/labeled as fallback fields; no deletion, deprecation, schema change, or data migration. Still current after SE-AS.7A (these fields are now converted into a structure audience row on save instead of governing a zero-row event).
- **Resolved.** Whether/when to run the SE-AS.6 backfill and whether to include global events: the SE-AS.6C apply has been run against production, global events included; all 37 production ServiceEvents have audience rows (post-apply dry-run: skipped-existing 37 / would-create 0 / parity-mismatch 0 / legacy-fields-mutated 0).

Still open:

- Legacy `scope_type` / `district` / `small_group` field deprecation/removal: timing and approach. Not in scope for SE-AS.7A; requires separate approval and stays deferred until audience rows have proven stable in production. No destructive change before then.
- Whether/when to retire the zero-row runtime fallback in `ServiceEvent.can_be_seen_by`. SE-AS.7A stops new zero-row writes but deliberately keeps the runtime fallback as a safety net; retiring it is a separate, later decision.
