# ServiceEvent Audience Runtime Migration Plan

## 1. Purpose and Status

SE-AS.3 recorded the implementation plan for migrating ServiceEvent / Church Gatherings audience scope from the legacy `scope_type` / `district` / `small_group` fields toward the `ChurchStructureUnit` audience-scope foundation (`ServiceEventAudienceScope`).

Status: SE-AS.3 is complete as docs-only planning. SE-AS.4 is complete as the runtime visibility rule with legacy fallback: events with one or more `ServiceEventAudienceScope` rows use those audience rows for ordinary-user visibility; events with zero rows keep the existing legacy `scope_type` / `district` / `small_group` plus `Profile.small_group` behavior. SE-AS.5 is complete as the staff selector UI/display: staff can select optional `ChurchStructureUnit` audience rows on single create/edit and recurring create; staff detail shows effective audience source and readable labels. `ChurchStructureMembership` still does not grant ServiceEvent visibility, and legacy scope fields remain preserved/editable as fallback. No SE-AS.6 backfill, setup/edit UI, CS-MAP.3, CS-SETUP.1, Community Activities, schema change, or migration was added.

Milestone renumbering note: `docs/SERVICE_EVENT_AUDIENCE_SCOPE_REDESIGN_PLAN.md` (SE-AS.1) originally labeled "SE-AS.3" as the future staff create/edit UI. This plan re-scopes SE-AS.3 as the runtime migration plan itself and renumbers later milestones (see Section 5). Where older docs say "SE-AS.3 staff UI selector," that work is now SE-AS.5 in this plan.

SE-AS.5A is complete as the docs-only staff audience selector interaction plan in `docs/SERVICE_EVENT_AUDIENCE_SELECTOR_INTERACTION_PLAN.md`. SE-AS.5 implementation is complete.

SE-AS.6A is complete as a docs-only planning checkpoint. It records the backfill / compatibility contract, hard invariants, parity requirement, and report categories in Section 8A, and recommends splitting any future backfill work into SE-AS.6B (dry-run audit command only) and SE-AS.6C (optional apply after dry-run review). SE-AS.6A adds no management command, test, schema, migration, or runtime change.

SE-AS.6B is complete as the dry-run audit command only. The `backfill_service_event_audience_scopes` management command (in the `events` app) scans `ServiceEvent` rows read-only and reports the Section 8A.5 categories; it has no `--apply`, creates no `ServiceEventAudienceScope` rows, and mutates no legacy field, unit, membership, profile, or group. SE-AS.6C (optional apply) remains a future milestone and requires separate explicit approval.

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
| ChurchStructureMembership | membership rows (approved/requested) | Future belonging source. Not current runtime visibility; not changed by this plan. |

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
- Non-root rows match only through the user's current `Profile.small_group`; `ChurchStructureMembership` is not consulted.
- Stored rows whose units are later deactivated keep matching per the Section 7 parity decision.
- SE-AS.4 itself added no selector UI, no ServiceEvent form/template audience picker, no backfill command, no Community Activities, no CS-MAP.3, and no CS-SETUP.1 work. SE-AS.5 later added the selector/display only.

### SE-AS.5 — Staff Audience Selector UI and Display

Completed. Planning preflight SE-AS.5A is complete in `docs/SERVICE_EVENT_AUDIENCE_SELECTOR_INTERACTION_PLAN.md`.

- Reuses the BS-AS.2 audience picker partial on ServiceEvent single create/edit and recurring batch-create.
- Single create saves selected `ServiceEventAudienceScope` rows; empty picker saves zero rows and keeps legacy fallback.
- Single edit preselects existing rows; saving selected units replaces rows; clearing all units deletes rows and restores legacy fallback. Legacy fields are not auto-converted into rows.
- Recurring create applies one selected audience set to all newly created events; preview creates no rows; skipped duplicates are not modified or backfilled.
- Staff detail displays effective source (`Structure audience` or `Legacy fallback audience`) plus readable labels and an unmapped-selection warning when selected units resolve to no active legacy groups.
- Ordinary detail does not expose structure/fallback architecture terms, model names, unit IDs, or unit codes.
- Backend validation remains authoritative (active unit, no ancestor/descendant redundancy).
- Legacy scope fields remain editable and are visually grouped/labeled as fallback audience settings during the transition; an event with audience rows is governed by those rows, and an event without rows keeps legacy behavior.

### SE-AS.6 — Backfill, Compatibility Monitoring, and Cleanup Planning

Backfill is optional and is not a prerequisite for ServiceEvent correctness (see Section 8A). It is now split into a docs-only checkpoint plus two narrow future implementation slices:

- **SE-AS.6A — docs-only planning checkpoint (complete with this task).** Records the future backfill / compatibility contract, hard invariants, parity requirement, dry-run report categories, and risk areas in Section 8A. No command, test, schema, migration, or runtime change.
- **SE-AS.6B — dry-run audit command only (complete).** Implements `backfill_service_event_audience_scopes` (in the `events` app) as a read-only audit that scans events and reports the Section 8A categories. It creates nothing and has no `--apply` path. An optional `--verbose-events` flag prints a per-event decision line.
- **SE-AS.6C — optional apply mode (future, separate approval, only after SE-AS.6B dry-run output is reviewed in production).** Adds an explicit `--apply` that creates audience rows only for events proven parity-safe by the dry-run rules.
- **Later — legacy fallback deprecation planning (future, separate approval).** Plan-only evaluation of eventual legacy `scope_type` / `district` / `small_group` field deprecation (the old SE-AS.6 scope from SE-AS.1); no destructive change until audience rows have proven stable in production.

Staff/admin clarity for which source governs each event (audience rows vs legacy fallback) already shipped with SE-AS.5 staff detail display.

## 6. Recommended Future `ServiceEvent.can_be_seen_by` Rule

Implemented by SE-AS.4. The runtime rule, in order:

1. Unauthenticated users: denied (unchanged).
2. `can_be_managed_by` (staff, superuser, `CAP_MANAGE_SERVICE_EVENTS`): allowed, including drafts (unchanged — managers keep broader access).
3. Draft/cancelled, or any non-published/completed status: denied for ordinary users (unchanged).
4. If the event has one or more `ServiceEventAudienceScope` rows: those rows are the audience source. The user is in the audience iff they match the selected units per Section 7.
5. Otherwise (no audience rows): fall back to legacy `scope_type` / `district` / `small_group` exactly as today.
6. Ordinary-user matching uses `Profile.small_group` only. `ChurchStructureMembership` is not consulted; requested/unapproved memberships must never grant visibility. Migrating matching to membership is a separate, unapproved, future decision.

Justification: the fallback rule means the migration never has a flag-day; every existing event is untouched until staff (or an explicit backfill) give it audience rows, and removing rows restores legacy behavior per event.

## 7. Unit-to-User Resolution for Ordinary Users

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
- Use `ChurchStructureMembership` as a ServiceEvent visibility source or as a backfill mapping input. Membership grants no ServiceEvent visibility.
- Backfill an event that already has one or more audience rows (skip it; it is already governed by its rows).
- Change My Serving, `TeamAssignment` / `TeamAssignmentMember`, required-team coverage, rotation anchor / copy-forward, `ministry_context` (Host / Language Label), or any other ministry-scheduling behavior.
- Remove, hide, deprecate, or disable the legacy fallback fields. They remain editable fallback fields throughout SE-AS.6.

### 8A.4 Parity requirement (binding)

- For every event a future command proposes to backfill, the ordinary-user visibility **after** creating audience rows must equal the ordinary-user visibility under the **pre-backfill legacy rule**, for every ordinary user. Backfill must be visibility-neutral.
- Parity is computed using the same unit-to-user resolution as the runtime rule (Section 7), so the comparison is: legacy-rule audience set vs. resolved-unit audience set.
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

### 8A.6 Risk areas to keep visible

- **Active/inactive mapping assumptions must not silently change visibility.** Validation forbids selecting inactive units at create time, but the runtime rule keeps matching a stored row whose unit later went inactive (Section 7 parity decision). Backfill must not exploit or contradict this: it maps only through currently-active mappings and skips when the mapping is inactive, so a backfilled row never changes who can see an event versus the legacy rule.
- **Custom / unmapped units may match no ordinary users.** A unit with no legacy `SmallGroup` mapping at or beneath it resolves to an empty ordinary audience. Backfill must not point a legacy event at such a unit when the legacy rule matched real users — that would fail parity and must be skipped.
- **Root maps to all authenticated users, including users without `Profile.small_group`.** This is the only mapping that reaches users with no current small group, and it is the correct parity target for legacy `global` events.
- **Non-root unit matching still depends on each user's current `Profile.small_group`.** District/small-group backfilled rows match exactly the users the legacy district/small-group rule matched, because both resolve through `Profile.small_group`; this is what makes district/small-group backfill parity-safe when the mapping exists and is active.

### 8A.7 Recommended future milestone split

- **SE-AS.6A** — docs-only planning checkpoint (this task).
- **SE-AS.6B** — dry-run audit command only, no apply. Reports the 8A.5 categories; creates nothing.
- **SE-AS.6C** — optional apply mode, only after SE-AS.6B dry-run output has been reviewed in production; creates rows only for parity-safe events behind an explicit `--apply`.
- **Later** — legacy fallback deprecation planning, only after audience rows have proven stable in production. No destructive change before then.

## 9. Staff UI Strategy (for SE-AS.5)

- Reuse the shared BS-AS.2 `ChurchStructureUnit` audience picker partial (search, chips, tree order, no-JS fallback, vanilla-JS convenience clearing, backend validation authoritative, bilingual aria labels).
- Field wording:
  - Audience Scope / 适用范围 — the picker.
  - Host / Language Label / 主办/语言标签 — the existing `ministry_context` field, kept visually and textually separate (separate form section or distinct help text) so staff cannot read it as audience.
- Because SE-AS.5 ships only after the runtime rule is live (Option C), the selector controls visibility from the day it appears. Help text should say plainly: selecting units controls which members can see this gathering; leaving it empty keeps the current legacy scope behavior. Do not ship the selector with "this does not affect visibility yet" copy — if the runtime rule is not live, do not show the selector at all.
- Show a normalized effective-audience preview before save/publish; warn when the selection matches no ordinary users (custom/unmapped units).
- Ordinary users see readable audience labels only (no codes, IDs, or architecture terms), consistent with the BS-AS.2 compact/chip display with root prefix omitted.
- Batch-create applies one selection to all created events, mirroring required-teams batch behavior.

## 10. Testing / QA Matrix (for SE-AS.4/SE-AS.5 implementation)

Legacy fallback parity:

- Event with zero audience rows: global/district/small_group visibility identical to current behavior for ordinary users (with and without `Profile.small_group`).
- Existing event test suite passes unchanged.

Audience-row visibility:

- Root unit row → visible to all authenticated ordinary users, including users with no small group.
- Ministry-context unit row → visible to users whose `Profile.small_group.district.ministry_context` maps to the unit (or descendant mapping); invisible to the other ministry context.
- District unit row → visible to users whose small group is in that district; invisible to sibling districts.
- Small-group unit row → visible only to that group's members; no leakage to unrelated small groups in the same district.
- Multi-unit sibling selection (two groups) and cross-branch selection (CM district + EM group) → union visibility, nothing else.
- Custom/unmapped unit row → no ordinary user sees it; managers still do.
- Unit inactive after selection → behavior matches the Section 7 decision, asserted explicitly.
- User with no `Profile.small_group` → sees root-audience events only.

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

- Final bilingual wording for SE-AS.5B is implemented as Audience Scope / 适用范围 for the new picker and Used when no structure audience is selected / 未选择上方范围时使用（旧版） for legacy fallback fields.
- Legacy scope field editability for SE-AS.5 is answered and implemented: keep `scope_type`, `district`, and `small_group` editable, but group/label them as legacy fallback fields used when no structure audience is selected; no deletion, deprecation, schema change, or data migration.
- Whether/when to run the SE-AS.6 backfill at all, and whether to include global events in it.
