# ServiceEvent Audience Runtime Migration Plan

## 1. Purpose and Status

SE-AS.3 recorded the implementation plan for migrating ServiceEvent / Church Gatherings audience scope from the legacy `scope_type` / `district` / `small_group` fields toward the `ChurchStructureUnit` audience-scope foundation (`ServiceEventAudienceScope`).

Status: SE-AS.3 is complete as docs-only planning. SE-AS.4 is complete as the runtime visibility rule that first introduced audience-row visibility with a zero-row legacy fallback at that time. SE-AS.5 is complete as the staff selector UI/display: staff can select optional `ChurchStructureUnit` audience rows on single create/edit and recurring create; staff detail shows effective audience source and readable labels. Historical note: at SE-AS.4/SE-AS.5 time, audience-row matching was not yet membership-core; CS-CORE.2B-A later switched ServiceEvent audience-row matching to active primary `ChurchStructureMembership`, and SE-RETIRE.1B later retired the zero-row legacy runtime fallback so zero-row events now fail closed for ordinary users. Legacy scope fields remain preserved as stored/admin/display/backfill/audit/rollback data until cleanup/field-level retirement, but SE-SCOPE.1A stops normal app-level create/edit and recurring flows from writing `scope_type`, `district`, or `small_group`, and SE-SCOPE.1B adds the guarded dry-run-first `cleanup_service_event_legacy_scope_fields` command for existing stored values. SE-AS.6B is complete as an audit-only dry-run command, including SE-AS.6B.1 verbose output polish. SE-AS.6C is complete as an explicit `--apply` mode on the same command (dry-run remains the default; apply creates `ServiceEventAudienceScope` rows only for parity-safe `would-create` events, never mutating legacy fields, and is idempotent). **SE-AS.6C production apply is complete:** it has been run against production, so all 37 production ServiceEvents now have audience rows; the post-apply dry-run reports skipped-existing-rows 37, would-create 0, parity-mismatch 0, and legacy-fields-mutated 0 (details below). SE-AS.7A is complete as the write-path guard that stopped normal create/edit/recurring flows from saving new zero-row legacy-fallback events at that time (details below); SE-SCOPE.1A later made those normal app write paths structure-audience-row native by removing normal form writes to the legacy scope fields. SE-SCOPE.1B does not remove fields, change runtime visibility, or automatically run cleanup. No setup/edit UI, CS-MAP.3, CS-SETUP.1, Community Activities, schema change, or migration was added.

Milestone renumbering note: `docs/SERVICE_EVENT_AUDIENCE_SCOPE_REDESIGN_PLAN.md` (SE-AS.1) originally labeled "SE-AS.3" as the future staff create/edit UI. This plan re-scopes SE-AS.3 as the runtime migration plan itself and renumbers later milestones (see Section 5). Where older docs say "SE-AS.3 staff UI selector," that work is now SE-AS.5 in this plan.

SE-AS.5A is complete as the docs-only staff audience selector interaction plan in `docs/SERVICE_EVENT_AUDIENCE_SELECTOR_INTERACTION_PLAN.md`. SE-AS.5 implementation is complete.

SE-AS.6A is complete as a docs-only planning checkpoint. It records the backfill / compatibility contract, hard invariants, parity requirement, and report categories in Section 8A, and recommends splitting any future backfill work into SE-AS.6B (dry-run audit command only) and SE-AS.6C (optional apply after dry-run review). SE-AS.6A adds no management command, test, schema, migration, or runtime change.

SE-AS.6B is complete as the dry-run audit command. The `backfill_service_event_audience_scopes` management command (in the `events` app) scans `ServiceEvent` rows read-only and reports the Section 8A.5 categories; by default it creates no `ServiceEventAudienceScope` rows and mutates no legacy field, unit, membership, profile, or group. SE-AS.6B.1 is complete as verbose-output polish: `--verbose-events` prints event id, title/date when available, legacy scope/status, decision category, proposed unit label/path when available, and reason text.

SE-AS.6C is complete as the explicit apply mode on the same command. Adding `--apply` makes the command create `ServiceEventAudienceScope` rows for events the dry-run classifies as parity-safe `would-create`; without `--apply` the command stays a read-only dry-run that changes nothing. Dry-run and apply share one decision path (`_scan_events`), so apply can never act on an event the dry-run would not have reported. Apply runs in a single atomic transaction, skips events that already have audience rows, is idempotent (a second run creates `0` additional rows), and never mutates `ServiceEvent.scope_type` / `district` / `small_group` / `ministry_context`, `ChurchStructureUnit`, `ChurchStructureMembership`, `Profile`, `SmallGroup`, `District`, or `MinistryContext`. Apply-mode output is clearly distinguished (`APPLY mode` header) and adds a `created audience rows : N` count; `legacy-fields-mutated (must be 0)` stays `0`.

SE-AS.6C parity correction (current-runtime parity): the parity check compares **pre-backfill legacy zero-row visibility** (matched directly through `Profile.small_group`) against **post-backfill membership-core visibility** (the active primary `ChurchStructureMembership` rule the runtime actually applies once an event has rows, per CS-CORE.2B-A), via the canonical `accounts.structure_selectors.user_matches_structure_audience` matcher. It no longer uses `studies.models.resolve_units_to_small_groups()` as the proposed post-row audience truth. The command compares the actual ordinary-user ID sets the two rules produce (managers excluded, since `can_be_managed_by` overrides both paths); if creating a row would add or drop even one ordinary user, the event is classified parity-mismatch and skipped. Global events still map to the active root unit, which both rules treat as all authenticated users, so global backfill stays parity-safe by construction.

Production-data dry-run review caveat (historical, now resolved): the previously captured GoDaddy dry-run (37 scanned / 1 skipped-existing / 36 would-create / 0 root skipped / 0 district skipped / 0 small-group skipped / 0 parity mismatch / 0 legacy mutation) was produced by the **old legacy-resolver parity logic** and was therefore not treated as final apply approval. The production-data dry-run was subsequently rerun under the corrected membership-core parity logic, re-reviewed, and the production apply was run (see the completion note below). The zero-row legacy fallback was still present at SE-AS.6C time; it was later retired in SE-RETIRE.1B, so zero-row events now fail closed for ordinary users.

SE-AS.6C production apply — completed. The corrected membership-core apply has now been run against production: all 37 production ServiceEvents have `ServiceEventAudienceScope` rows, and a dry-run rerun after apply reports `skipped existing rows: 37`, `would-create: 0`, `parity-mismatch: 0`, and `legacy-fields-mutated: 0`. No legacy field was mutated. This records the completed real-database apply that later made SE-RETIRE.1B possible; SE-RETIRE.1B is the separate slice that retired the zero-row runtime fallback.

SE-AS.7A is complete as the historical write-path guard that stopped new zero-row legacy-fallback events by converting empty-picker saves from legacy scope fields into audience rows. SE-SCOPE.1A supersedes the normal app form portion of that design: normal ServiceEvent single create/edit and recurring create no longer expose or write `ServiceEvent.scope_type`, `district`, or `small_group`. Normal app saves now require at least one selected structure audience unit instead of converting empty selections through the legacy fields or saving normal app zero-row events. When staff select audience units, those `ServiceEventAudienceScope` rows are the structure-native source. Existing stored legacy values are not bulk-cleared by SE-SCOPE.1A. SE-SCOPE.1B adds `cleanup_service_event_legacy_scope_fields`, a guarded dry-run-first command that clears only `scope_type`, `district`, and `small_group` for events that already have at least one `ServiceEventAudienceScope` row; it does not run automatically. SE-RETIRE.1B remains the runtime rule: zero-row events fail closed for ordinary users, while manager/staff override and audience-row membership-core visibility are unchanged. SE-SCOPE.1B does **not** delete legacy fields, does **not** change Bible Study or TeamAssignment / My Serving / required-team logic, adds no schema/migration, and does not run a data cleanup during implementation.

SE-RETIRE.1A is complete as a **read-only retirement-readiness audit** for the zero-audience-row legacy fallback (see Section 13). It added the `audit_service_event_fallback_retirement_readiness` management command, which reported which zero-row events still relied on the legacy `scope_type` / `district` / `small_group` plus `Profile.small_group` fallback, which were backfillable into equivalent audience rows, and which blocked fallback removal at that time. It did **not** remove the zero-row fallback, change `ServiceEvent.can_be_seen_by`, hide or remove legacy form fields, add schema/migration, or touch production database. SE-RETIRE.1B later completed the approved fallback-removal slice after the audit ran clean on production.

SE-RETIRE.1B is complete as the **runtime retirement of the zero-audience-row legacy fallback for ordinary users** (see Section 14). After the SE-RETIRE.1A audit ran clean on production (37/37 events carry audience rows, zero blockers), `ServiceEvent.can_be_seen_by` no longer consults the legacy `scope_type` / `district` / `small_group` fields or `Profile.small_group` for ordinary-user visibility of an event that has **zero** `ServiceEventAudienceScope` rows. Such an event now **fails closed** for ordinary users — a zero-row event is an invalid/safety state, not a legacy fallback. Manager/staff/event-manager override (`can_be_managed_by`), unauthenticated denial, draft/cancelled/status gates, and the audience-row membership-core path are all unchanged. SE-RETIRE.1B did not delete or rename the legacy fields, remove `backfill_service_event_audience_scopes` or `audit_service_event_fallback_retirement_readiness`, add schema/migration, or change Bible Study / Reading / Profile / TeamAssignment / My Serving runtime. SE-SCOPE.1A later stopped normal app-level writes to the legacy fields; existing stored values remain display/admin/backfill/audit/rollback context and cleanup blockers.

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
| Audience Scope / 适用范围 | `ServiceEventAudienceScope` units. As of SE-RETIRE.1B a zero-row event fails closed for ordinary users. As of SE-FIELD-RETIRE.1A the legacy `scope_type`/`district`/`small_group` fields are removed (migration `events/0007`); only immutable historical migrations still name them. | Who the event/gathering is for. The only concept this plan migrates. |
| Host / Language Label / 主办/语言标签 | `ServiceEvent.ministry_context` | Display label only. Never visibility. |
| Required Ministry Teams / 需要的事工团队 | `ServiceEventRequiredTeam` | Which teams need coverage. Not audience. |
| Rotation Anchor Team / 配搭参考团队 | `ServiceEvent.rotation_anchor_team` | Scheduling suggestion anchor only. |
| TeamAssignment / 服事安排 | `TeamAssignment(Member)` | Actual serving assignment. |
| My Serving / 我的服事 | user's `TeamAssignmentMember` rows | User's own assignments; independent of audience. |
| ChurchStructureMembership | membership rows (approved/requested) | As of CS-CORE.2B-A, the active primary membership is the runtime visibility source for ServiceEvent rows that **have** audience rows (via `user_matches_structure_audience`). As of SE-RETIRE.1B, zero-row events fail closed for ordinary users (no `Profile.small_group` fallback). Requested/unapproved/inactive memberships grant nothing. This plan does not change the membership model itself. |

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

- Historical pros at Option B planning time: no confusion window — the day the selector appears, it really controls visibility; the then-active fallback kept old events unchanged.
- Cons: one large milestone bundling a permission-affecting runtime change with new UI, forms, validation, and display; harder to review and QA in one slice; violates the project's small-slice discipline.
- User/staff confusion risk: low.
- Permission/visibility risk: medium — runtime change and UI bugs land together, so a selector bug can directly cause a visibility leak in the same release.
- Migration complexity: highest single-release complexity.
- Historical rollback at Option B planning time: UI and runtime would have needed rollback together; before SE-RETIRE.1B, deleting audience rows restored legacy behavior per event. Current behavior after SE-RETIRE.1B is different: zero-row events fail closed for ordinary users.
- Verdict: acceptable but bundles too much.

### Option C (recommended): Keep selector hidden until runtime is ready; ship runtime first, then selector

- Sequence: implement and fully test the new `can_be_seen_by` rule with legacy fallback first (SE-AS.4). Because nothing in the app creates `ServiceEventAudienceScope` rows yet, this change is behavior-inert at ship time: every event falls back to legacy fields, and targeted tests prove parity. Then ship the staff selector + display (SE-AS.5) on top of an already-proven runtime rule.
- Pros: each release is narrow; the runtime rule is tested and live before any staff can create audience rows; when the selector appears it genuinely controls visibility from day one. Historical pre-SE-RETIRE.1B per-event rollback was "delete the audience rows"; current rollback to legacy ordinary visibility would require deliberate code rollback or another approved recovery slice.
- Cons: the runtime code path for audience rows is briefly live but unexercised in production between SE-AS.4 and SE-AS.5 (mitigated by the test matrix in Section 10); two releases instead of one.
- User/staff confusion risk: minimal — staff never see an inert selector.
- Permission/visibility risk: lowest — the only release that changes visibility logic changes no observable behavior, and the only release that changes staff workflow reuses a proven rule.
- Migration complexity: moderate, spread across two small slices.
- Historical rollback strategy: SE-AS.4 could be reverted cleanly (no data depended on it); after SE-AS.5 and before SE-RETIRE.1B, removing an event's audience rows reverted that event to legacy behavior; disabling the selector reverted the workflow without data loss. Current behavior after SE-RETIRE.1B is fail-closed for zero-row ordinary-user visibility.

Historical decision: Option C originally shipped the zero-row legacy fallback runtime rule first at SE-AS.4 time, then the selector. That fallback was later retired by SE-RETIRE.1B, so the current runtime rule is audience rows when present and fail-closed for ordinary users when rows are absent.

## 5. Phased Milestones

Each milestone is separately approved and intentionally narrow.

### SE-AS.3 — Runtime Migration Plan (this document)

Docs-only. Complete. No code changes.

### SE-AS.4 — Runtime Visibility Rule with Legacy Fallback

Completed. At SE-AS.4 time, `ServiceEvent.can_be_seen_by` applied the Section 6 rule with a zero-row legacy fallback: staff/superuser/service-event managers kept the existing override; draft/cancelled and non-published statuses stayed hidden from ordinary users; events with `ServiceEventAudienceScope` rows used those rows for ordinary-user visibility; events with no rows fell back to legacy `scope_type` / `district` / `small_group` and `Profile.small_group` behavior exactly. This historical zero-row fallback was later retired in SE-RETIRE.1B; zero-row events now fail closed for ordinary users.

Implementation notes:

- Unit matching reuses `studies.models.resolve_units_to_small_groups()` so ServiceEvent and Bible Study Schedule share the same `ChurchStructureUnit` to legacy `SmallGroup` resolution semantics.
- Root unit rows behave like legacy global scope and match all authenticated ordinary users, including users without a current small group.
- Non-root rows matched only through the user's current `Profile.small_group` **at SE-AS.4 time**; `ChurchStructureMembership` was not consulted then. **Superseded by CS-CORE.2B-A:** non-root audience-row matching now uses the user's single active primary `ChurchStructureMembership` (see Section 1 and the canonical `accounts.structure_selectors.user_matches_structure_audience`). **Superseded by SE-RETIRE.1B:** zero-row events now fail closed for ordinary users.
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
- Historical SE-AS.5/SE-AS.7A transition note: legacy scope fields were once editable in the normal app form as stored fallback-context settings. After SE-SCOPE.1A, normal app create/edit and recurring forms no longer expose or write those fields; existing stored values remain admin/display/backfill/audit/rollback data and cleanup blockers. Since SE-RETIRE.1B, an event without rows fails closed for ordinary users rather than keeping legacy runtime behavior.

### SE-AS.6 — Backfill, Compatibility Monitoring, and Cleanup Planning

Backfill is optional and is not a prerequisite for ServiceEvent correctness (see Section 8A). It is now split into a docs-only checkpoint plus two narrow future implementation slices:

- **SE-AS.6A — docs-only planning checkpoint (complete with this task).** Records the future backfill / compatibility contract, hard invariants, parity requirement, dry-run report categories, and risk areas in Section 8A. No command, test, schema, migration, or runtime change.
- **SE-AS.6B — dry-run audit command only (complete).** Implements `backfill_service_event_audience_scopes` (in the `events` app) as a read-only audit that scans events and reports the Section 8A categories. It creates nothing and has no `--apply` path. SE-AS.6B.1 verbose-output polish is complete: `--verbose-events` prints event id, title/date when available, legacy scope/status, decision category, proposed unit label/path when available, and reason text.
- **SE-AS.6C — apply mode (implemented, with CS-CORE.2B-A parity correction).** Adds an explicit `--apply` to the same command that creates audience rows only for events proven parity-safe by the dry-run rules. Dry-run remains the default; apply shares the dry-run decision path, runs in one atomic transaction, skips events that already have rows, is idempotent, mutates no legacy field, and reports a `created audience rows` count. **Parity is current-runtime parity:** pre-backfill legacy zero-row visibility (`Profile.small_group`) vs post-backfill membership-core visibility (active primary `ChurchStructureMembership` via `user_matches_structure_audience`), not the legacy `resolve_units_to_small_groups` resolver. The earlier GoDaddy dry-run (37 scanned / 1 skipped-existing / 36 would-create / 0 skipped / 0 parity mismatch / 0 legacy mutation) was produced by the **old legacy-resolver parity logic** and was not used as apply approval; the production-data dry-run was rerun under the corrected membership-core logic, re-reviewed, and **the production apply has now been run** (all 37 production ServiceEvents have audience rows; post-apply dry-run: skipped-existing 37 / would-create 0 / parity-mismatch 0 / legacy-fields-mutated 0). SE-RETIRE.1B later retired the zero-row legacy runtime fallback.
- **SE-SCOPE.1B — guarded legacy scope field cleanup command (implemented).** Adds `cleanup_service_event_legacy_scope_fields`, which is dry-run by default and requires both `--apply` and `--confirm-service-event-legacy-scope-cleanup` before mutating data. It clears only `ServiceEvent.scope_type`, `district`, and `small_group`, and only for events that already have `ServiceEventAudienceScope` rows. It never mutates audience rows, `ministry_context`, required teams, rotation anchor team, Church Structure rows/memberships, Profile/SmallGroup/District/MinistryContext rows, Bible Study, Prayer, Reading, Reflection, Role, Ministry, or TeamAssignment data, and it does not change runtime visibility semantics.
- **SE-FIELD-RETIRE.1A — legacy scope field removal (complete).** After SE-RETIRE.1B retired the zero-row runtime fallback and local/dev audit confirmed all 37 ServiceEvents have audience rows with zero populated legacy scope fields, the `ServiceEvent.scope_type`, `district`, and `small_group` model fields were removed (migration `events/0007`). The legacy-scope tooling (`cleanup_service_event_legacy_scope_fields`, `backfill_service_event_audience_scopes`, `audit_service_event_fallback_retirement_readiness`) was retired with the fields. ServiceEvent visibility remains `ServiceEventAudienceScope` rows plus active primary `ChurchStructureMembership`; zero-row events stay fail-closed for ordinary users. This did not affect `ServiceEvent.ministry_context`, `host_language_unit`, `ServiceEventAudienceScope`, or the `SmallGroup`/`District` tables. Only immutable historical migrations still name the removed fields.

Staff/admin clarity for which source governs each event (audience rows vs legacy fallback) already shipped with SE-AS.5 staff detail display.

### SE-AS.7A — Stop new zero-row legacy-fallback writes

Historical status. With production backfilled (SE-AS.6C apply), SE-AS.7A stopped normal ServiceEvent write paths from saving events into the zero-`ServiceEventAudienceScope` legacy-fallback state by converting the then-editable legacy scope fields into audience rows. SE-SCOPE.1A later superseded the normal app form portion of this approach:

- Single create, single edit, and recurring create no longer expose or save legacy `scope_type`, `district`, or `small_group`.
- When staff select audience units, those `ServiceEventAudienceScope` rows are saved as the structure-native source.
- Existing stored legacy field values are not reconciled or bulk-cleared on edit; SE-SCOPE.1B provides guarded cleanup tooling, but cleanup is explicit and not automatic.
- Preview still creates no rows.
- Non-goals remain unchanged: legacy fields are not deleted, Bible Study, TeamAssignment / My Serving, and required-team logic are unchanged, and no schema, migration, or data migration was added. SE-RETIRE.1B remains the runtime rule: zero-row events fail closed for ordinary users.

## 6. Recommended Future `ServiceEvent.can_be_seen_by` Rule

Implemented by SE-AS.4. The runtime rule, in order:

1. Unauthenticated users: denied (unchanged).
2. `can_be_managed_by` (staff, superuser, `CAP_MANAGE_SERVICE_EVENTS`): allowed, including drafts (unchanged — managers keep broader access).
3. Draft/cancelled, or any non-published/completed status: denied for ordinary users (unchanged).
4. If the event has one or more `ServiceEventAudienceScope` rows: those rows are the audience source. The user is in the audience iff they match the selected units. **At SE-AS.4 time this matched via Section 7 (`Profile.small_group`); as of CS-CORE.2B-A it matches via the user's single active primary `ChurchStructureMembership`** through `accounts.structure_selectors.user_matches_structure_audience` (root rows still match all authenticated users).
5. Otherwise (no audience rows): **as of SE-RETIRE.1B, ordinary users fail closed.** The legacy `scope_type` / `district` / `small_group` fields and `Profile.small_group` are no longer consulted for ordinary visibility. (Before SE-RETIRE.1B this step fell back to the legacy fields matched through `Profile.small_group`; that fallback is retired — see Section 14.)
6. **Audience-row matching** consults active primary `ChurchStructureMembership` (CS-CORE.2B-A); requested/unapproved/inactive memberships never grant visibility. There is no longer a zero-row `Profile.small_group` matching path for ordinary users (retired in SE-RETIRE.1B). (The earlier statement that audience-row matching never consults membership applied only before CS-CORE.2B-A.)

Historical justification at SE-AS.4 time: the then-active fallback rule meant the migration did not have a flag-day; every existing event was untouched until staff (or an explicit backfill) gave it audience rows, and removing rows restored legacy behavior per event. Current behavior is different after SE-RETIRE.1B: removing all audience rows no longer restores ordinary-user legacy visibility; a zero-row event fails closed for ordinary users.

## 7. Unit-to-User Resolution for Ordinary Users

**Scope note (CS-CORE.2B-A correction).** This section describes the **legacy `Profile.small_group` resolver** (`resolve_units_to_small_groups`) only. As shipped at SE-AS.4 this was also how ServiceEvent audience rows matched, but **that is no longer current ServiceEvent behavior**: as of CS-CORE.2B-A a ServiceEvent that has audience rows matches ordinary users through the user's single active primary `ChurchStructureMembership` via `accounts.structure_selectors.user_matches_structure_audience`, **not** through `Profile.small_group`. The `Profile.small_group` resolver below now describes only the separate **Bible Study** generation/visibility path, which still resolves through `Profile.small_group`. It **no longer** describes any ServiceEvent path: as of SE-RETIRE.1B the ServiceEvent zero-row legacy fallback is retired and zero-row events fail closed for ordinary users (Section 14). Read this section as legacy/Bible-Study resolver semantics, not as any current ServiceEvent runtime.

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

Historical SE-AS.6 planning context: before SE-RETIRE.1B, backfill was optional for correctness because the fallback rule kept every legacy event behaving identically with zero audience rows. Current behavior after SE-RETIRE.1B is different: zero-row ServiceEvents fail closed for ordinary users, so backfill/apply history should not be read as a current fallback guarantee.

If/when a management command is approved (suggested name `backfill_service_event_audience_scopes`):

- `scope_type=global` → one row pointing at the root unit, only if exactly one active root unit exists; otherwise skip.
- `scope_type=district` → one row pointing at `district.church_structure_unit`, only if the mapping exists and the unit is active; otherwise skip.
- `scope_type=small_group` → one row pointing at `small_group.church_structure_unit`, only if the mapping exists and the unit is active; otherwise skip.
- Historical pre-SE-RETIRE.1B strategy for unmapped or ambiguous events: leave zero audience rows and report them in command output. Current behavior after SE-RETIRE.1B: if such a zero-row event exists, it fails closed for ordinary users; legacy fallback no longer governs it.
- Never create root or structure units; seeding stays exclusively in `seed_church_structure_units`.
- Never mutate or clear legacy `scope_type` / `district` / `small_group` during backfill — non-destructive only.
- Skip events that already have audience rows (idempotent; re-running changes nothing).
- Dry-run by default (or require an explicit `--apply`), reporting per-scope counts: would-create, skipped-unmapped, skipped-existing, skipped-ambiguous-root.
- Acceptance check: for every backfilled event, the new rule's ordinary-user audience equals the legacy rule's audience (tested at the command level before any production apply, then verified by production dry-run output review).

Note that backfilling `global` events is pure convergence with no behavior difference (root ≡ global), so a conservative first apply may backfill district/small_group events only, or nothing at all.

## 8A. SE-AS.6A Backfill / Compatibility Planning Checkpoint (docs-only)

SE-AS.6A is a **docs-only planning checkpoint, not implementation**. It defines the contract that any future backfill work (SE-AS.6B audit, SE-AS.6C apply) must satisfy. It adds no management command, test, schema, migration, or runtime change. Section 8 above remains the high-level strategy; this section is the binding contract that supersedes it where they differ.

### 8A.1 Backfill is optional, not required for correctness

- Historical pre-SE-RETIRE.1B behavior: the SE-AS.4 fallback rule made a ServiceEvent with **zero `ServiceEventAudienceScope` rows** behave exactly as it did under the legacy `scope_type` / `district` / `small_group` + `Profile.small_group` rule. At that time, zero audience rows were safe.
- Current behavior after SE-RETIRE.1B: zero-row ServiceEvents fail closed for ordinary users, and removing rows no longer restores legacy visibility.
- Backfill was a **convergence / operational cleanup** step (moving legacy events onto explicit structure rows) before fallback retirement. The production apply has since run and enabled SE-RETIRE.1B; do not read this historical strategy as authorizing current zero-row fallback behavior.

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

Historical note: at SE-AS.6B.1 time, apply/backfill was not yet approved; SE-AS.6C required separate explicit approval after real dry-run output had been captured and reviewed. SE-AS.6C has since completed, and SE-RETIRE.1B later retired the zero-row runtime fallback.

### 8A.7 Risk areas to keep visible

- **Active/inactive mapping assumptions must not silently change visibility.** Validation forbids selecting inactive units at create time, but the runtime rule keeps matching a stored row whose unit later went inactive (Section 7 parity decision). Backfill must not exploit or contradict this: it maps only through currently-active mappings and skips when the mapping is inactive, so a backfilled row never changes who can see an event versus the legacy rule.
- **Custom / unmapped units may match no ordinary users.** A unit with no legacy `SmallGroup` mapping at or beneath it resolves to an empty ordinary audience. Backfill must not point a legacy event at such a unit when the legacy rule matched real users — that would fail parity and must be skipped.
- **Root maps to all authenticated users, including users without `Profile.small_group`.** This is the only mapping that reaches users with no current small group, and it is the correct parity target for legacy `global` events.
- **Non-root post-row matching depends on active primary `ChurchStructureMembership`, not `Profile.small_group` (CS-CORE.2B-A correction).** Once an event has audience rows the runtime matches a non-root district/small-group row through the user's single active primary membership unit. District/small-group backfill is therefore parity-safe only when, for every ordinary user, the legacy `Profile.small_group` rule and the membership-core rule pick the same users — i.e. legacy group and active primary membership are aligned. A user who matched the legacy rule via `Profile.small_group` but has no active primary membership (or whose membership points elsewhere) is a parity mismatch and forces the event to be skipped. (Earlier revisions of this plan incorrectly stated both sides resolve through `Profile.small_group`; that was the pre-CS-CORE.2B-A behavior.)

### 8A.8 Recommended future milestone split

- **SE-AS.6A** — docs-only planning checkpoint (this task).
- **SE-AS.6B** — dry-run audit command only, no apply. Reports the 8A.5 categories; creates nothing. SE-AS.6B.1 verbose output polish is complete.
- **SE-AS.6C** — apply mode (implemented; parity corrected to current-runtime membership-core per CS-CORE.2B-A). Creates rows only for parity-safe events behind an explicit `--apply`; dry-run stays the default. The earlier GoDaddy dry-run (Section 1) used the old legacy-resolver parity logic; the production-data dry-run was rerun under the corrected membership-core parity, re-reviewed, and **the production apply has now been run** (all 37 production ServiceEvents have audience rows; post-apply dry-run: skipped-existing 37 / would-create 0 / parity-mismatch 0 / legacy-fields-mutated 0).
- **SE-AS.7A** — stop new zero-row legacy-fallback writes (implemented; see Section 5). Historically converted empty audience selections from the legacy fields into structure rows.
- **SE-RETIRE.1B** — retire the zero-row legacy runtime fallback for ordinary users (implemented; see Section 14). Zero-row events now fail closed; legacy fields remain stored display/admin/backfill/audit/rollback data.
- **SE-SCOPE.1A** — stop normal app-level legacy ServiceEvent scope field writes (implemented). Normal create/edit and recurring app flows no longer expose or save `scope_type`, `district`, or `small_group`.
- **SE-SCOPE.1B** — add guarded dry-run-first cleanup for existing ServiceEvent legacy scope field values (implemented). Apply requires `--apply` plus `--confirm-service-event-legacy-scope-cleanup`, clears only rows that already have audience rows, and does not remove fields or change runtime visibility.
- **Later** — legacy scope field deprecation/removal planning. No field hiding/removal before rollback and display/admin needs are separately approved.

## 8B. SE-AS.6C.0 Optional Apply-Mode Preflight Design (docs-only)

SE-AS.6C.0 was the design-only preflight for apply mode. **Status update:** SE-AS.6C apply mode is now implemented (with the CS-CORE.2B-A current-runtime parity correction), so an `--apply` flag now exists. The guardrails in this section remain binding on that implementation and on any production apply. Implementation is **not** approval to run apply against a real database: production apply still requires explicit human action, a current backup, and a fresh production-data dry-run reviewed under the corrected membership-core parity logic.

### 8B.1 Preconditions before SE-AS.6C can be approved

Before any implementation prompt may approve SE-AS.6C apply mode:

1. Staging or production dry-run output has been captured with `--verbose-events`.
2. The captured dry-run output has been reviewed by staff/development reviewers who understand the target data.
3. A current recoverable database backup exists, or the backup process has been confirmed before any future apply discussion.
4. Root ambiguity, unmapped rows, inactive mappings, and parity-mismatch rows have been reviewed event by event.
5. Expected skipped rows are documented, including the historical pre-SE-RETIRE.1B reason each category was left on legacy fallback and the current consequence after SE-RETIRE.1B: a zero-row event is a diagnostic/safety state that fails closed for ordinary users.
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

Legacy fields remain preserved throughout SE-AS.6 for display/admin/backfill/audit/rollback context. Historically, before SE-RETIRE.1B, an event with zero `ServiceEventAudienceScope` rows fell back to legacy `scope_type` / `district` / `small_group`, so deleting the created audience rows for a specific event returned that event to legacy fallback behavior. Current behavior after SE-RETIRE.1B is different: deleting all audience rows no longer restores ordinary-user legacy visibility, and a zero-row ServiceEvent fails closed for ordinary users. Any rollback to legacy ordinary visibility would require a deliberate code rollback of SE-RETIRE.1B or another separately approved recovery slice, not merely deleting rows.

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
- Current help-text behavior after SE-SCOPE.1A: selecting units controls which members can see this gathering, and normal app forms require at least one selected unit before saving. Normal app forms no longer expose or write the legacy `scope_type` / `district` / `small_group` fields. Since SE-RETIRE.1B, if a zero-row event exists through an import, Django Admin/manual edit, or other unguarded data state, it is an invalid/safety state and fails closed for ordinary users; `can_be_seen_by` no longer uses the zero-row legacy fallback.
- Show a normalized effective-audience preview before save/publish; warn when the selection matches no ordinary users (custom/unmapped units).
- Ordinary users see readable audience labels only (no codes, IDs, or architecture terms), consistent with the BS-AS.2 compact/chip display with root prefix omitted.
- Batch-create applies one selection to all created events, mirroring required-teams batch behavior.

## 10. Testing / QA Matrix (for SE-AS.4/SE-AS.5 implementation)

Historical SE-AS.4 legacy fallback parity:

- Event with zero audience rows: at SE-AS.4 time, global/district/small_group visibility stayed identical to the legacy behavior for ordinary users (with and without `Profile.small_group`). Since SE-RETIRE.1B, the current expected behavior is fail-closed for ordinary users; legacy parity tests are historical and retirement tests cover the new rule.
- Existing event test suite passes unchanged.

Audience-row visibility (ServiceEvent, membership-core as of CS-CORE.2B-A):

For ServiceEvents that **have** audience rows, ordinary-user matching is through the user's single active primary `ChurchStructureMembership` unit via `accounts.structure_selectors.user_matches_structure_audience`, **not** `Profile.small_group`. Zero-row events now fail closed for ordinary users after SE-RETIRE.1B. Bible Study's own audience path is separate; since BS-STRUCT.2A, Bible Study V2 meeting visibility reads meeting audience rows rather than `Profile.small_group`. A non-root row matches when the user's active primary membership unit is the selected unit or a descendant of it; requested/unapproved/inactive memberships never match.

- Root unit row → visible to all authenticated ordinary users, including users with no membership/small group.
- Ministry-context unit row → visible to users whose active primary membership unit is the ministry-context unit or a descendant of it; invisible to the other ministry context.
- District unit row → visible to users whose active primary membership unit is the district unit or a descendant (e.g. a child small-group unit); invisible to sibling districts.
- Small-group unit row → visible only to users whose active primary membership unit is that group's unit; no leakage to unrelated small groups in the same district.
- Multi-unit sibling selection (two groups) and cross-branch selection (CM district + EM group) → union visibility, nothing else.
- Custom/unmapped unit row → no ordinary user sees it; managers still do.
- Unit inactive after selection → behavior matches the Section 7 decision, asserted explicitly.
- User with no active primary membership → sees root-audience events only; zero-row events fail closed for ordinary users after SE-RETIRE.1B.

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

- **Resolved historically.** Final bilingual wording for the picker is Audience Scope / 适用范围. The legacy fallback section wording was Used when no structure audience is selected / 未选择上方范围时使用（旧版） at SE-AS.5B and was updated by SE-AS.7A to Converted when no structure audience is selected / 未选择上方范围时用于转换. SE-SCOPE.1A later removed that normal app fallback section and stopped normal app writes to the legacy fields.
- **Resolved historically; superseded by SE-SCOPE.1A for normal forms.** SE-AS.7A kept `scope_type`, `district`, and `small_group` editable and converted them into structure audience rows. SE-SCOPE.1A removes those fields from normal create/edit/recurring app flows without deleting the model fields, changing schema, or clearing existing stored values.
- **Resolved.** Whether/when to run the SE-AS.6 backfill and whether to include global events: the SE-AS.6C apply has been run against production, global events included; all 37 production ServiceEvents have audience rows (post-apply dry-run: skipped-existing 37 / would-create 0 / parity-mismatch 0 / legacy-fields-mutated 0).

Still open:

- Legacy `scope_type` / `district` / `small_group` field deprecation/removal: timing and approach. SE-SCOPE.1A stops new normal app writes, and SE-SCOPE.1B adds guarded dry-run-first cleanup tooling for existing stored values. Running cleanup against any target database and later field/schema removal remain separate approvals.
- **Resolved (SE-RETIRE.1B).** The zero-row runtime fallback in `ServiceEvent.can_be_seen_by` is retired: zero-row events now fail closed for ordinary users (Section 14). SE-AS.7A stopped new zero-row writes at that time; SE-RETIRE.1A gated the decision with a clean production audit; SE-RETIRE.1B removed the runtime fallback. Legacy `scope_type` / `district` / `small_group` fields remain stored admin/display/backfill/audit/rollback context until guarded cleanup and separate field retirement (the bullet above).

## 13. SE-RETIRE.1A — Zero-Row Fallback Retirement Readiness Audit (read-only)

SE-RETIRE.1A adds a read-only audit that answers one question: **can the
zero-audience-row legacy fallback in `ServiceEvent.can_be_seen_by` be safely
removed or made fail-closed yet?** It is the readiness gate for a future,
separately-approved fallback-removal slice. It does not remove the fallback.

Command: `audit_service_event_fallback_retirement_readiness` (in the `events`
app). It is **read-only** — no `--apply`, no runtime change, no schema or
migration, no production-DB write. It never mutates any `ServiceEvent`,
`ServiceEventAudienceScope`, legacy `scope_type` / `district` / `small_group`
field, `ChurchStructureUnit`, `ChurchStructureMembership`, `Profile`,
`SmallGroup`, `District`, or `MinistryContext` row. `legacy_fields_mutated` is
always `0` and `runtime_switched` is always `false` by construction.

Backfillability is delegated to the existing
`backfill_service_event_audience_scopes` decision path (`_classify_event`): an
event is "backfillable" exactly when that command would classify it as a
parity-safe `would-create` (convertible to an equivalent membership-core
audience row under the current runtime, CS-CORE.2B-A). The two commands stay in
agreement by construction.

Reported counters: `events_checked`, `events_with_audience_rows`,
`events_without_audience_rows`, `published_without_audience_rows`,
`future_or_upcoming_without_audience_rows`,
`active_visible_without_audience_rows`, `zero_row_global_fallback`,
`zero_row_district_fallback`, `zero_row_small_group_fallback`,
`zero_row_unscoped_or_invalid`, `zero_row_backfillable`,
`zero_row_not_backfillable`, `blocker_visible_zero_row_events`,
`blocker_not_backfillable_zero_row_events`, `blockers_total`,
`legacy_fields_mutated` (always `0`), plus `runtime_switched` (always `false`).

Blocker policy (what currently prevents fallback removal):

- A zero-row event is **blocking** when removing the fallback would change what
  an ordinary user sees: it is ordinary-user-visible today (status published or
  completed) **and** still active/upcoming (published, or an upcoming start).
- Draft and cancelled events are never ordinary-user-visible, and purely past
  completed events are treated as harmless archive, so neither is a blocker.
- Among blocking zero-row events, those that are **not backfillable** (unmapped
  / inactive / wrong-type / invalid / parity-mismatch legacy fields) are the
  hard blockers, counted separately.

Options: `--verbose` (per-event lines listing id / title / status / start /
scope labels only — never description/body text), `--limit N`, `--event-id ID`,
and `--fail-on-blockers` (exits nonzero when `blockers_total > 0`; still
read-only).

A clean audit (`blockers_total == 0`) means every ordinary-user-visible, active
event already carries audience rows, so the zero-row fallback can be retired
without changing any current audience. That condition was met before
SE-RETIRE.1B. Backfillable-but-not-yet-backfilled events would have blocked
removal until `backfill_service_event_audience_scopes --apply` had been run and
the audit re-ran clean on the target data.

**Fallback removal required this audit to run clean on the target (production)
data** and its own approved slice; SE-RETIRE.1A itself neither removed the
fallback nor hid any legacy form field. SE-RETIRE.1B later completed that
approved runtime retirement.

## 14. SE-RETIRE.1B — Retire the Zero-Row Runtime Fallback (fail closed)

SE-RETIRE.1B retires the zero-audience-row legacy **runtime** fallback in
`ServiceEvent.can_be_seen_by` for ordinary users. It was applied after the
SE-RETIRE.1A audit ran clean on production (`events_checked: 37`,
`events_with_audience_rows: 37`, `events_without_audience_rows: 0`, all zero-row
scope/blocker counters `0`, `legacy_fields_mutated: 0`, `runtime_switched:
false`, `--fail-on-blockers` passed).

New runtime behavior for `ServiceEvent.can_be_seen_by`:

- Unauthenticated users: denied (unchanged).
- `can_be_managed_by` (staff, superuser, `CAP_MANAGE_SERVICE_EVENTS`): allowed,
  including drafts and including zero-row events (unchanged manager override).
- Draft/cancelled, or any non-published/completed status: denied for ordinary
  users (unchanged).
- Event **with** one or more `ServiceEventAudienceScope` rows: those rows are
  the audience source, matched by active primary `ChurchStructureMembership`
  (CS-CORE.2B-A) — **unchanged**.
- Event with **zero** audience rows: **ordinary users fail closed.** The legacy
  `scope_type` / `district` / `small_group` fields and `Profile.small_group`
  are **no longer consulted** for ordinary visibility. A zero-row event is now
  an invalid/safety state, not a legacy fallback.

What SE-RETIRE.1B deliberately does **not** do:

- It does **not** delete or rename the legacy `scope_type` / `district` /
  `small_group` fields. They remain stored display/admin/backfill/audit/
  rollback context only. SE-SCOPE.1A later stops normal app-level writes to
  these fields; legacy-field cleanup and retirement are still separate, later,
  gated decisions (Section 12).
- It did not hide or remove the legacy fallback form fields in SE-RETIRE.1B;
  that normal app form change landed later in SE-SCOPE.1A without deleting the
  model fields.
- It does **not** remove `backfill_service_event_audience_scopes` (tooling
  still converts legacy fields into audience rows) or
  `audit_service_event_fallback_retirement_readiness`.
- It does **not** change the SE-AS.7A write-path guard, Bible Study, Reading,
  Profile, TeamAssignment, or My Serving runtime, and adds no schema/migration.

`audit_service_event_fallback_retirement_readiness` remains useful **after**
SE-RETIRE.1B: it is now a standing guard/diagnostic that detects and explains
any accidental zero-row event (which would now be invisible to ordinary users),
and supports rollback reasoning. Its blocker policy is unchanged — it still
reports any visible/active zero-row event as a blocker — so a clean audit
(`blockers_total == 0`) confirms no ordinary-user-visible event depends on a
zero-row state.
