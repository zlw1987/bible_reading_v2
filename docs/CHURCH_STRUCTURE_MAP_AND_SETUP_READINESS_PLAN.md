# Church Structure Map and Setup Readiness Plan

## 1. Purpose and Status

CS-MAP.1 is a docs-only planning pass. No code, schema, migration, template, form, view, URL, test, settings, or runtime behavior is changed by this task.

This plan responds to two June 2026 demo feedback items:

1. IM team lead: the app cannot realistically replace every existing church app at once; it should be modular, adopted module by module, and able to coexist/integrate with existing tools (for example 微读圣经 for small-group reading/study content).
2. Pastor/elder/deacon: leadership wants a clear church structure architecture, setup support, and a visible structure map / hierarchy map; structure setup currently happens mainly through Django Admin, which is not convenient for them; they see church structure as a foundation for many future modules.

This plan defines a docs-first response: record the modular adoption principle, then propose a read-only staff structure map with mapping-health indicators (CS-MAP.2) before any setup/edit UI is considered. Later milestones each require separate explicit approval; nothing beyond this document is authorized by CS-MAP.1.

Status update: CS-MAP.2 is now complete (see Section 7 for the completion note), SE-AS.5B post-commit cleanup clarified the visible wording and count semantics on the shipped read-only map, and CS-MAP.2B updates the map tree to use the same hierarchical node-level expand/collapse mental model as the ServiceEvent audience picker. CS-MAP.3 remains optional and unapproved. CS-SETUP.1 remains explicitly unapproved and gated per Section 6; CS-SETUP.1A is a docs-only risk/design pass that defines the design contract a future setup/edit UI must satisfy and splits CS-SETUP.1 into separately approvable sub-milestones (see Section 12). CS-SETUP.1A changes no code, schema, migration, template, view, or runtime behavior. CS-SETUP.1B is now implemented as the lowest-risk slice only: an opt-in edit mode on `/staff/structure/` with a per-row action menu offering Rename (display name + bilingual name) and a Details (Django Admin) link; it adds no schema/migration and changes no runtime visibility (see Section 12.6). CS-SETUP.1C.1 is now implemented as a read-only mapping review page at `/staff/structure/mappings/` that lists the legacy-to-structure mappings with simple status labels; CS-SETUP.1C.2 adds read-only summary counts and filters; both add no schema/migration and change no runtime visibility (see Section 12.7). CS-SETUP.1D.0 is a docs-only plan for the next safe mapping-maintenance slice: edit one existing legacy row's mapping to one existing active structure unit, with no unit lifecycle, membership, audience-row, or runtime visibility change (see Section 12.8). CS-SETUP.1D.1 is now implemented as that narrow slice: a permission-gated staff edit page that updates one legacy row's `church_structure_unit` to one active matching-type unit via explicit POST with type/active/duplicate validation and `LogEntry` audit; it adds no schema/migration and changes no unit lifecycle, membership, audience-row, or runtime visibility (see Section 12.8). CS-SETUP.1D.2 optional warning polish and CS-SETUP.1E future structure unit lifecycle design remain unapproved.

## 2. Current Foundation Summary

Audited from the current working tree:

- `ChurchStructureUnit` (`accounts/models.py`): flexible variable-depth tree foundation with `parent`, `unit_type` (root / ministry_context / district / small_group / fellowship / department / custom), bilingual names, `is_active`, `sort_order`, unique parent+code, direct/indirect cycle validation, and cycle-safe `get_ancestors()` / `path_label()` helpers.
- `ChurchStructureMembership` (`accounts/models.py`): future belonging foundation with requested/active/ended/rejected/cancelled lifecycle, one-active-primary-per-user enforcement, date windows, approval audit fields, and `active_for_user()` / `current_primary_for_user()` helpers. It is not a runtime visibility source.
- Legacy bridge mappings: nullable `church_structure_unit` fields on `MinistryContext`, `District`, and `SmallGroup` (`accounts/models.py`), explicitly non-runtime.
- Commands: `seed_church_structure_units` (mirrors legacy structure into the unit tree under a `CHURCH` root with `UNASSIGNED-DISTRICTS` / `UNASSIGNED-GROUPS` holding nodes) and `backfill_church_structure_memberships` (creates active primary memberships from mapped `Profile.small_group`). Both default to dry-run with explicit `--apply`; production/staging runs are verified (CS-H.3D/3E, CS-H.5D).
- Bible Study Schedule is the first narrow runtime consumer: `BibleStudySeriesAudienceScope` (`studies/models.py`) resolves selected units to eligible legacy `SmallGroup` rows for meeting generation; ordinary member visibility still uses `Profile.small_group`.
- `ServiceEventAudienceScope` (`events/models.py`) is now a runtime visibility source for ServiceEvent (SE-AS.4/SE-AS.5 complete): an event with one or more audience rows uses those rows for ordinary-user visibility, and an event with zero rows falls back to legacy `scope_type` / `district` / `small_group` and `Profile.small_group`. Ordinary-user matching still resolves through `Profile.small_group`; `ChurchStructureMembership` is not consulted (see `docs/SERVICE_EVENT_AUDIENCE_RUNTIME_MIGRATION_PLAN.md`).
- Staff surfaces: read-only overview at `/staff/`, membership request review/approve/reject at `/staff/membership-requests/`, moderation queue at `/staff/moderation/`. `/staff/structure/` now renders the structure hierarchy (CS-MAP.2/2B) as a permission-gated map; CS-SETUP.1B adds only an opt-in edit mode there with per-row rename (display name only) and a Details link for admin-capable staff. `/staff/structure/mappings/` (CS-SETUP.1C.1) is a read-only legacy-to-structure mapping review page that lists each `MinistryContext` / `District` / `SmallGroup` row beside its mapped unit with a simple mapping-status label; it has no edit affordance. The shared audience picker (`templates/shared/_church_structure_unit_audience_picker.html`) renders the tree as a form selector in other modules. Broader structure setup (create/move/deactivate units, districts, groups) still happens only in Django Admin.

Ordinary-user matching still depends on legacy `Profile.small_group` across consumers. On top of that: ServiceEvent now uses `ServiceEventAudienceScope` as the event-level audience source when an event has rows, while zero-row ServiceEvents fall back to legacy `scope_type` / `district` / `small_group`; Bible Study Schedule uses structure audience rows for meeting-generation eligibility, with ordinary member visibility still resolved through `Profile.small_group`.

## 3. Product Principle: Modular Adoption and Coexistence

Recorded as a product principle from the June 2026 demo feedback:

- The CMS must not require a church to replace all existing church apps at once.
- Modules should be adoptable one by one. The existing module boundaries and legacy-fallback behavior already support this: a church can use Daily Reading without Bible Study, or My Serving without either.
- External tools may coexist with CMS modules. For example, a small group may keep using 微读圣经 for reading/study content while the CMS provides structure, scheduling, and audience scope.
- Integration initially means link/reference/mapping (the same pattern as "link to Google Docs playbooks, do not import them"), not deep API integration or data import.
- No external-system integration work (APIs, imports, embeds, sync) is authorized by this plan. Any future integration requires its own separately approved plan.

The church structure foundation is the coexistence enabler, not a competitor to external tools: the CMS owns structure, belonging, audience, and workflow; external tools can keep owning content within a group.

## 4. Pastor/Staff Expectation and Safe Response Path

Leadership needs to see and trust the church structure: a visible hierarchy map, who-belongs-where counts, and confidence that setup data is healthy. Before CS-MAP.2 the unit tree was invisible outside Django Admin, and the only mapping-health reporting was CLI command dry-run output. CS-MAP.2/2B now provide `/staff/structure/` as a permission-gated hierarchy map with mapping-health indicators, and CS-SETUP.1B adds only an opt-in display-name rename / Details affordance there for admin-capable staff; broader structure setup remains in Django Admin.

"Setup support" must not be read as "build edit UI now." Editing `ChurchStructureUnit` is no longer merely cosmetic: ServiceEvent audience rows (`ServiceEventAudienceScope`) and Bible Study Schedule audience rows (`BibleStudySeriesAudienceScope`) can depend on the unit tree and its legacy mappings, so unit moves, deactivation, or mapping drift can change resolved audiences for events and schedules that already have rows. A higher-risk staff edit UI would therefore have real runtime consequences while exposing none of the rules needed to make those changes safe — the same staff-confusion failure mode that `docs/SERVICE_EVENT_AUDIENCE_RUNTIME_MIGRATION_PLAN.md` Section 4 rejected for the audience selector. The broader CS-SETUP.1D.1/1D.2/1E/1F surfaces therefore remain unapproved: before a mapping, create/move/deactivate, or membership edit UI is safe it needs explicit rules for unit moves, unit deactivation, legacy-mapping drift, and the effect of each on stored audience rows and legacy fallback behavior. Only CS-SETUP.1B — the separately approved low-risk slice that renames display labels and links to Details — is implemented; rename changes display names only and cannot move units, change mappings, or alter any audience rows. CS-SETUP.1D.0 is planning only. Django Admin remains the structure write surface for everything beyond approved narrow slices: it already distinguishes legacy runtime models from future foundation models (CS-H.5E), and model `full_clean()` validation enforces tree integrity there.

The safe path is staged:

1. See — render the structure hierarchy on a read-only staff page.
2. Verify — show counts and mapping context so staff can confirm the tree matches reality.
3. Diagnose — show mapping-health / setup-readiness indicators that point staff to the existing Django Admin or staff workflows that fix each issue.
4. Later, and only if read-only usage proves a real recurring need — consider a limited setup/edit UI (CS-SETUP.1) with its own design doc and approval.

## 5. Concept Separation (binding for CS-MAP work)

| Concept | Source | Role |
| --- | --- | --- |
| Church Structure Unit | `ChurchStructureUnit` | Future flexible structure foundation (tree of church/ministry/district/group units). Not a runtime visibility source. |
| Church Structure Membership | `ChurchStructureMembership` | Future belonging foundation plus current staff request/approval workflow data. Not a runtime visibility source; requested/rejected/ended/cancelled rows grant nothing. |
| Audience Scope / 适用范围 | `BibleStudySeriesAudienceScope` (runtime for meeting generation), `ServiceEventAudienceScope` (runtime for ServiceEvent visibility when rows exist, else legacy fallback); legacy scope fields elsewhere | Who an event/schedule is for. Per-module join models selecting units. |
| Host / Language Label / 主办/语言标签 | `ServiceEvent.ministry_context` | Display label only. Never visibility, serving, or permissions. |
| Required Ministry Teams / 需要的事工团队 | `ServiceEventRequiredTeam` | Which teams need coverage on an event. Not audience, not structure. |
| Rotation Anchor Team / 配搭参考团队 | `ServiceEvent.rotation_anchor_team` | Scheduling suggestion anchor only. |
| TeamAssignment / 服事安排 | `TeamAssignment` / `TeamAssignmentMember` | Actual serving assignments. Serving operations, not church structure. |
| My Serving / 我的服事 | user's `TeamAssignmentMember` rows | User's own assignments; independent of audience and structure. |
| Legacy `Profile.small_group` | `Profile.small_group` | Current runtime belonging source for visibility across consumers. |
| Legacy `District` / `SmallGroup` / `MinistryContext` | legacy structure models | Current runtime structure models, bridged to units via nullable mapping fields. |

The structure map must display structure and membership concepts only. It must not display, imply, or link serving assignments, required teams, rotation anchors, or host labels as structure or audience.

## 6. Proposed Milestone Sequence

| Milestone | Scope | Status |
| --- | --- | --- |
| CS-MAP.1 | Docs-only Church Structure Map / Setup Readiness Plan (this document) | Complete with this task |
| CS-MAP.2 | Read-only Staff Structure Map + Mapping Health at `/staff/structure/` | Completed; implemented read-only (see Section 7) |
| SE-AS.4 | ServiceEvent audience runtime visibility rule with legacy fallback | Completed (see `docs/SERVICE_EVENT_AUDIENCE_RUNTIME_MIGRATION_PLAN.md`) |
| SE-AS.5 | ServiceEvent staff audience selector UI/display | Completed |
| SE-AS.6A | Docs-only backfill / compatibility planning checkpoint | Completed docs-only (see migration plan Section 8A) |
| SE-AS.6B | ServiceEvent audience dry-run audit command only | Completed; audit-only command implemented |
| SE-AS.6C | ServiceEvent audience optional apply mode, after dry-run review | Future; separate approval |
| CS-MAP.3 | Optional setup readiness checklist on the structure map page | Optional; separate approval |
| CA V1 | Community Activities planning, then implementation | Later; separate plan; not pulled forward by this feedback |
| CS-SETUP.1 | Limited structure setup/edit UI (umbrella; now split into CS-SETUP.1A–1F) | Not approved; gated (see below and Section 12) |
| CS-SETUP.1A | Docs-only setup/edit UI risk/design plan and design contract | Complete with this task (Section 12); docs-only, no implementation |
| CS-SETUP.1B | Label / bilingual-name / sort-order-only staff edit UI | Implemented as edit mode + rename/detail only (display name + bilingual name); sort-order edit deferred. See Section 12.6 |
| CS-SETUP.1C.1 / 1C.2 | Legacy-to-unit mapping review UI | Implemented read-only: mapping review page plus summary counts and filters (Section 12.7); no write UI |
| CS-SETUP.1D.0 | Legacy Mapping Maintenance Next-Slice Plan | Complete with this docs-only pass (Section 12.8); no implementation |
| CS-SETUP.1D.1 | Legacy mapping maintenance implementation | Implemented: staff-only per-row edit of one legacy row's `church_structure_unit` to one active matching-type unit, gated by the legacy model's Django change permission, explicit POST, type/active/duplicate validation, and `LogEntry` audit (Section 12.8); no unit lifecycle, membership, audience, or runtime visibility change |
| CS-SETUP.1D.2 | Optional mapping warning polish / conflict indicators | Future; separate approval after 1D.1 |
| CS-SETUP.1E | Future structure unit lifecycle design | Future design only; create/move/delete/deactivate requires separate plan and approval |
| CS-SETUP.1F | Membership / belonging management UI | Not approved; separate from structure editing, separate approval (Section 12) |

Sequencing rules:

- CS-MAP.2 landed before SE-AS.4/SE-AS.5, as originally recommended from a product-risk perspective: the SE-AS.5 selector's biggest operational risk is staff selecting units that match no current members, and the mapping-health surface mitigates that before the selector exists. SE-AS.4 and SE-AS.5 are now complete. Future ServiceEvent audience apply/backfill work must proceed through review of SE-AS.6B dry-run output first, not direct apply/backfill, and must never be bundled with CS-MAP work.
- Community Activities must not be pulled forward by this feedback. Its position (after the audience foundation is proven through Bible Study and ServiceEvent) is unchanged per `docs/COMMUNITY_ACTIVITIES_V1_PLAN.md`.
- CS-SETUP.1 is explicitly not approved as an umbrella edit surface. It is gated on: (a) CS-MAP.2 shipped and used, with evidence that read-only visibility plus Django Admin is insufficient for a recurring staff task; (b) a separate design doc resolving unit↔legacy sync direction (today only seeding writes units from legacy; two-way sync is undesigned), edit permissions/capabilities, and the effect of unit moves/deactivation on stored audience rows; (c) separate explicit approval. CS-SETUP.1A (Section 12) is the docs-only response to gate (b): it records the risk analysis and the design contract, and splits the umbrella CS-SETUP.1 into separately approvable sub-slices so that the lowest-risk surfaces can be approved independently of the high-risk create/move/deactivate surface. CS-SETUP.1D.0 plans the next narrow mapping-maintenance slice only; it does not approve implementation.
- Do not bundle ServiceEvent runtime visibility migration, Community Activities, and `ChurchStructureMembership` runtime migration with each other or with CS-MAP work.

## 7. CS-MAP.2 Implementation Contract

Status: completed. CS-MAP.2 is implemented as the read-only staff Church Structure Map at `/staff/structure/`: it renders the active `ChurchStructureUnit` hierarchy with bilingual names, counts-only membership/mapping context, and the Section 8 setup-readiness indicators; it has no write actions (GET-only), no schema/migration changes, no runtime visibility changes, and no setup/edit UI. SE-AS.5B clarified the page as `Church Structure & Setup Check` / `教会结构与设置检查`, renamed per-row mappings to `Current data mapping` / `当前资料对应`, and changed the main per-row member number to descendant-inclusive `Covered members` / `覆盖成员`. CS-MAP.2B keeps root-level units visible by default and lets staff expand descendants one level at a time; parent covered-member counts remain descendant-inclusive. Django Admin remains the structure write surface.

- Route: suggested `/staff/structure/`, linked from the existing `/staff/` overview.
- Access: permission-protected, matching the existing staff overview gating pattern (staff/superuser or existing staff capability); ordinary users denied. No new capability unless implementation review proves a real gap.
- Renders the active `ChurchStructureUnit` hierarchy with indentation/path context and node-level expand/collapse controls, using `display_name(language)` for bilingual names where available; inactive units remain hidden from the active tree.
- Per-unit context is counts only: descendant-inclusive active primary `ChurchStructureMembership` covered-member count, and which active legacy `MinistryContext` / `District` / `SmallGroup` rows map to the unit as current data mapping. No member name rosters.
- Shows the mapping-health / setup-readiness indicators defined in Section 8, each linking to the existing Django Admin or staff workflow where the issue can be reviewed — no fix actions on the page itself.
- Zero write actions. Zero schema changes. Zero runtime behavior changes anywhere else: event/study/reading visibility untouched, no new queries on non-staff paths.
- Staff wording follows `docs/UI_UX_GUARDRAILS.md` staff rules: transition state explicit (current runtime small group vs future foundation membership), no "runtime source of truth" / "legacy sync target" architecture jargon in visible UI, EN/ZH copy paired.
- The page should reuse existing query logic where practical (for example the unmapped/mapping checks already computed inside the seed/backfill command dry-runs) rather than duplicating definitions.

## 8. Mapping Health / Setup Readiness Indicators

These are health indicators / setup readiness indicators, following the PP-SA.5 precedent: each indicator is a separately defined bucket; the same record may appear in more than one indicator; any aggregate shown is a sum of indicator buckets, not a unique problem-record count, and must be labeled accordingly. Individual indicators below state what they uniquely count.

1. Unmapped active legacy rows: active `MinistryContext`, `District`, and `SmallGroup` rows whose `church_structure_unit` is null. Three separate unique-record counts (one per model).
2. Active non-root units with no legacy mapping at-or-beneath them: active units (excluding the root) where neither the unit nor any descendant is referenced by any legacy mapping field. If selected as an audience, such units match no ordinary users today. Unique unit count.
3. Units under `UNASSIGNED-*` holding nodes: active units whose ancestor chain includes a holding node seeded as `UNASSIGNED-DISTRICTS` or `UNASSIGNED-GROUPS`. These represent legacy rows that lacked a proper parent at seeding time. Unique unit count.
4. Users whose current group is unmapped: users with `Profile.small_group` set where that `SmallGroup` has no `church_structure_unit`. Unique user count.
5. Runtime/foundation belonging drift: users with an active primary `ChurchStructureMembership` whose membership unit differs from `Profile.small_group.church_structure_unit`, including cases where either side is missing (active primary membership but no runtime group, or runtime group but no active primary membership). Unique user count per drift category; categories should be displayed separately, not summed into one number.
6. Active root units: the count of active units with `unit_type = root`. Exactly one is expected; zero or more than one is flagged. (The database does not enforce a single root; seeding creates one `CHURCH` root.)
7. Direct member records on parent units: active primary `ChurchStructureMembership` users assigned directly to a non-leaf active unit. This is a setup warning only; it does not block model saves or approval workflow.
8. Optional, if cheap at implementation time — inactive units still referenced: inactive units referenced by legacy mapping fields or by stored audience rows (`BibleStudySeriesAudienceScope`, `ServiceEventAudienceScope`). Display-only context: stored audience rows on later-inactivated units are not automatically an error (see the SE-AS plan's parity note), but staff should be able to see them. Unique unit count.

Each indicator's exact queryset is part of the CS-MAP.2 implementation contract and must have a targeted test against constructed fixture data.

## 9. Non-Goals

CS-MAP.1 and CS-MAP.2 do not include:

- Create/edit/delete UI for units, districts, groups, memberships, or any structure data (CS-SETUP.1 is separate, gated, and not approved).
- Schema changes or migrations of any kind.
- ServiceEvent runtime visibility migration (SE-AS.4) or any `ServiceEvent.can_be_seen_by` change.
- ServiceEvent staff audience selector (SE-AS.5).
- Community Activities planning changes or implementation.
- Migration of any consumer from `Profile.small_group` / legacy models to `ChurchStructureMembership`.
- Member name rosters, per-person drill-down, or any sensitive/pastoral data display.
- External-system integration (微读圣经 or any other tool): no APIs, imports, embeds, or sync.
- Permission/capability redesign or permission matrix expansion.
- Auto-fix actions for health indicators; indicators link to existing workflows only.
- Notifications, checklists, attendance, announcements, care workflows, file center, availability, swaps, reminders, or scheduling automation.

## 10. Risks and Mitigations

| Risk | Mitigation |
| --- | --- |
| The map makes the unit tree look like a universal runtime source of truth; staff edit units or mappings in Django Admin without understanding module-specific effects | Staff wording must stay explicit: ordinary-user matching still resolves through legacy `Profile.small_group` and legacy mappings, while per-module audience rows such as `ServiceEventAudienceScope` and `BibleStudySeriesAudienceScope` can depend on the unit tree. CS-SETUP.1 remains gated until unit moves, deactivation, mapping drift, and stored audience-row effects are explicitly designed. |
| Staff expect an edit UI because the map exists | The page states that setup changes happen in Django Admin and links there; CS-SETUP.1 stays gated on evidence and separate approval. |
| Health counts mislead (double counting, aggregate read as unique problems) | Section 8 wording rules: per-indicator unique-count definitions, drift categories displayed separately, aggregates labeled as bucket sums (PP-SA.5 precedent). |
| Mapping drift between legacy structure and future foundation grows silently | That is precisely what indicators 1, 4, and 5 surface; the page makes drift visible instead of CLI-only. |
| Privacy: structure page exposes member rosters | Counts only in CS-MAP.2; no rosters, no per-person listing; page is permission-protected staff-only. |
| Scope creep into SE-AS.4/SE-AS.5, Community Activities, or membership migration | Explicit non-goals (Section 9); each milestone separately approved; bundling prohibited (Section 6). |
| Performance on production data | The unit tree is small (~35 seeded units); build the tree from one ordered queryset (as the audience picker options helper does) and use single aggregate queries per indicator; no per-node N+1. |

## 11. CS-MAP.2 Acceptance Criteria

These criteria were the CS-MAP.2 implementation contract; the completed slice was verified against them with targeted tests and browser/mobile QA.

1. Access control: page requires the agreed staff gating; ordinary authenticated users and anonymous users are denied; tested for allowed and denied cases.
2. Tree rendering: active units render in hierarchy order with bilingual names via `display_name(language)`; inactive units distinct or toggled; tested against fixture trees including at least one multi-depth branch.
3. Mapping health indicators: every Section 8 indicator implemented with its exact queryset and a targeted test using constructed fixture data covering the flagged and non-flagged case.
4. Counts only: no member names or rosters anywhere on the page.
5. Bilingual staff wording: EN/ZH paired labels, transition-state wording per `docs/UI_UX_GUARDRAILS.md`; language-dependent tests set `session["language"]`.
6. Mobile-safe layout: tables/trees degrade into usable stacked layouts at mobile width.
7. Zero write actions and zero runtime visibility change: no POST handlers on the page; no changes to event/study/reading visibility code paths; existing targeted visibility tests untouched and passing.
8. Verification commands clean at implementation time: `.venv\Scripts\python.exe manage.py makemigrations --check`, `.venv\Scripts\python.exe manage.py check`, and `git diff --check`.
9. Targeted tests only: page permission, rendering, and indicator tests; no full `accounts` suite run (report the recommended manual command instead, per root `AGENTS.md`).
10. Browser/mobile QA performed per the endpoint-safe rules in root `AGENTS.md`, or reported as blocked with exact manual QA steps; never claimed if not performed.

## 12. CS-SETUP.1A — Setup/Edit UI Risk Design and Design Contract (docs-only)

CS-SETUP.1A is a docs-only risk/design pass. It implements nothing and approves nothing. Its job is to explain why a staff structure setup/edit UI cannot be built safely today, to separate the candidate edit surfaces rather than bundle them, to define the safety rules any implementation must satisfy first, and to split CS-SETUP.1 into independently approvable sub-milestones. No CS-SETUP.1B–1F work is authorized by this section.

### 12.1 Why a setup/edit UI is risky now

- **Some unit edits now have runtime consequences through stored audience rows.** Unit moves and deactivation can change what `ServiceEventAudienceScope` and `BibleStudySeriesAudienceScope` rows resolve to; legacy mapping edits can change who matches a unit today. Renames and sort-order changes are lower risk because they affect display labels/order rather than matching, but they still need permission, audit, and clear staff wording. A ServiceEvent or Bible Study series that already stored audience rows pointing at a unit or its descendants can silently gain or lose audience when staff edit the tree shape or mapping bridge. A "setup" UI that looks cosmetic is therefore not always cosmetic.
- **Legacy mappings remain the ordinary-user matching bridge.** Ordinary-user matching still resolves through `Profile.small_group` and the nullable `church_structure_unit` mappings on `MinistryContext`, `District`, and `SmallGroup`. Editing the unit tree without touching those legacy rows changes one side of the bridge only; editing the legacy mappings changes who matches today. These are different actions with different blast radius and must not be presented as one "edit structure" button.
- **`ChurchStructureMembership` is not the runtime visibility source.** Editing membership/belonging rows changes the future foundation and staff workflow data, not who currently sees an event or study. A UI that mixes membership edits with structure edits invites staff to believe a membership change altered visibility (it did not) or that a structure change is "just bookkeeping" (it can move stored audiences).
- **Four edit concepts are easy to confuse.** Structure edits (the unit tree), membership edits (`ChurchStructureMembership`), legacy mapping edits (`MinistryContext` / `District` / `SmallGroup` → unit), and audience edits (per-module `*AudienceScope` rows) all touch overlapping nouns ("group", "district") but have different sources of truth and different runtime effects. Without explicit separation and wording, a single edit screen would reproduce exactly the staff-confusion failure mode that `docs/SERVICE_EVENT_AUDIENCE_RUNTIME_MIGRATION_PLAN.md` Section 4 rejected for the audience selector.

### 12.2 Candidate future edit surfaces (kept separate, not bundled)

These are listed in roughly increasing blast radius. Each is a candidate only; none is approved here, and they must not be shipped as a single combined editor.

1. **Display labels / bilingual names / sort order only.** Edit a unit's EN/ZH display name and `sort_order`. No tree-shape change, no activation change, no mapping change. Lowest risk: does not change which legacy rows or members resolve under a unit, and does not change stored audience resolution.
2. **Legacy-to-unit mappings.** Set or clear the `church_structure_unit` on a `MinistryContext` / `District` / `SmallGroup`. Directly changes the matching bridge and therefore can change who matches a unit-based audience today. Higher risk; needs audience-impact warnings.
3. **Create new units.** Add a unit under a parent. Lower runtime risk on its own (a brand-new unit has no members, mappings, or audience rows), but it is the entry point to tree-shape editing and must enforce parent/cycle/`unit_type` rules.
4. **Move units in the tree.** Re-parent a unit. Changes descendant-inclusive resolution for any audience row or count that depends on ancestry; high risk because effects are indirect (a moved subtree changes what its ancestors "cover").
5. **Deactivate units.** Set `is_active = false`. Removes the unit from the active tree and pickers, but stored audience rows and legacy mappings referencing it do not disappear. High risk: can strand audience rows and is the most likely silent-visibility-change vector.
6. **Membership / belonging changes.** Create/approve/end `ChurchStructureMembership` rows. This is belonging-foundation and staff-workflow data, not runtime visibility. Must be treated as a separate product surface from structure editing, with its own approval, precisely so staff do not read it as a visibility control.

### 12.3 Required safety rules before any implementation

Any CS-SETUP.1B–1F implementation must satisfy all of the following before it is approved:

- **Explicit permission/capability boundary.** Define exactly which staff capability may edit each surface; do not reuse the read-only map's view gate as a write gate. Higher-blast-radius surfaces (move/deactivate, mapping edits) should require a stricter capability than label/sort-order edits. No new capability is created by CS-SETUP.1A.
- **Audit/logging expectation.** Every write records who changed what, when, and the before/after value. Structure, mapping, and membership edits are auditable separately. No silent edits.
- **No silent runtime visibility changes.** Any edit that could change a resolved audience (mapping edits, moves, deactivation) must surface the impact before saving and must never change ordinary-user visibility as an invisible side effect. Visibility-affecting edits are an explicit, acknowledged action, not a byproduct of "tidying the tree".
- **Warnings when a unit is referenced by stored audience rows.** Before editing/moving/deactivating a unit, show whether and how many `ServiceEventAudienceScope` and `BibleStudySeriesAudienceScope` rows reference that unit (directly or via descendants), so staff see the blast radius first.
- **Rules for inactive units referenced by existing rows.** Deactivating a unit that is referenced by stored audience rows or legacy mappings must not auto-delete or auto-rewrite those rows. Define the chosen behavior explicitly (block, warn-and-allow, or require a follow-up cleanup step) and make stranded references visible (this extends Section 8 indicator 8).
- **Rules for moving units with descendants.** Moving a non-leaf unit must state how descendant-inclusive counts and audience resolution change, validate against cycles (reuse existing `full_clean()` cycle checks, do not bypass them), and warn when the move changes what an ancestor covers.
- **Rules for mapping drift between legacy rows and `ChurchStructureUnit`.** Mapping edits must make drift visible (the Section 8 indicators 1, 4, 5 definitions are the reference) and must not be presented as a structure edit. Two-way unit↔legacy sync remains undesigned; an edit UI must not silently invent it.
- **Rollback / manual recovery plan.** Define how a mistaken edit is reversed: at minimum, audit records sufficient to reconstruct the prior state, and a documented manual recovery path (Django Admin remains the backstop). No destructive edit without a recovery story.
- **Clear staff wording distinguishing structure, membership, mapping, and audience.** Per `docs/UI_UX_GUARDRAILS.md` staff rules: each surface must name which concept it edits and explicitly state what it does *not* change (e.g. "editing this label does not change who sees any event or study"). EN/ZH paired, no "runtime source of truth" / "legacy sync target" architecture jargon in visible UI.

### 12.4 Recommended milestone split

- **CS-SETUP.1A** — this docs-only risk/design plan and design contract. Complete with this task.
- **CS-SETUP.1B** — label / bilingual-name / sort-order-only staff edit UI, if approved. Lowest blast radius; must still meet the Section 12.3 permission, audit, and wording rules.
- **CS-SETUP.1C.1 / 1C.2** — legacy-to-unit mapping review UI. Complete as read-only review, summary counts, and filters. No write action.
- **CS-SETUP.1D.0** — legacy mapping maintenance next-slice plan. Complete with this docs-only pass. It narrows the next possible implementation to editing one existing legacy row's mapping to one existing active unit.
- **CS-SETUP.1D.1** — docs-reviewed mapping maintenance implementation, if explicitly approved. Must edit one mapping at a time and satisfy Section 12.8.
- **CS-SETUP.1D.2** — optional warning polish / conflict indicators, if explicitly approved after 1D.1.
- **CS-SETUP.1E** — future structure unit lifecycle design only. Create, move, delete, merge/split, or deactivate structure units remains too risky for implementation without a separate design.
- **CS-SETUP.1F** — membership / belonging management UI, separate from structure editing and only after its own approval; must not be read as a runtime visibility control.

Each sub-milestone requires its own explicit approval. Approving one does not approve the next. They must not be bundled with each other, with SE-AS.6C apply/backfill, with `ChurchStructureMembership` runtime migration, or with Community Activities.

### 12.5 CS-SETUP.1A explicit non-goals

CS-SETUP.1A does not include and does not authorize (as of the CS-SETUP.1A docs-only pass, no edit/setup UI was authorized):

- No implementation of any edit/setup UI at CS-SETUP.1A time. (Later, CS-SETUP.1B was separately approved and implements rename/detail only — see Section 12.6; CS-SETUP.1C.1/1C.2 were separately approved and implement read-only mapping review only — see Section 12.7; CS-SETUP.1D.0 is docs-only planning; CS-SETUP.1D.1/1D.2/1E/1F remain unapproved.)
- No schema changes or migrations of any kind.
- No runtime visibility change anywhere (event/study/reading visibility untouched).
- No automatic unit↔legacy sync (one-way or two-way).
- No membership-driven visibility; `ChurchStructureMembership` is not made a runtime visibility source.
- No ServiceEvent audience backfill/apply (SE-AS.6C remains separate and future).
- No Community Activities planning or implementation work.
- No broad Staff Admin rewrite or permission-matrix expansion.

### 12.6 CS-SETUP.1B — implemented slice (edit mode + rename/detail only)

CS-SETUP.1B is implemented as the lowest-risk first slice only. It does **not** implement the full "label / sort-order" surface described in Section 12.4; sort-order editing, add-child, deactivate, delete, move, mapping, and membership actions are intentionally excluded and remain unapproved (CS-SETUP.1D.1/1D.2/1E/1F unchanged).

What was implemented on `/staff/structure/`:

- The default page stays clean and read-only. An opt-in edit mode is entered via `?edit=1` and exited via a plain link back to the page; the edit affordances render only for staff who can change `ChurchStructureUnit` in Django Admin (`accounts.change_churchstructureunit`).
- Edit mode shows a banner stating it can only change display names and does not change membership, mappings, event audience, serving assignments, or permissions.
- Each unit row in edit mode shows a compact `操作 / Actions` menu (HTML `<details>`), containing only `重命名 / Rename` (non-root) and `详细资料 / Details` (admin change-page link). The root unit shows no Rename.
- Rename is a separate POST + CSRF endpoint (`staff_structure_unit_rename`) that updates only `name` and `name_en`, refuses root units, and is gated on `accounts.change_churchstructureunit` (staff who can only view the map cannot rename). It does not touch `parent`, `unit_type`, `code`, `is_active`, `sort_order`, legacy mappings, memberships, `ServiceEventAudienceScope`, or `BibleStudySeriesAudienceScope`, and changes no runtime visibility.
- Audit uses Django admin `LogEntry` (CHANGE) per rename; no new model or migration was added.

This satisfies the Section 12.3 permission, audit, and wording rules for the rename surface. All Section 12.5 CS-SETUP.1A non-goals remain in force.

### 12.7 CS-SETUP.1C.1 — implemented slice (read-only mapping review only)

CS-SETUP.1C.1 is a **read-only** review slice of CS-SETUP.1C. It does **not** implement any mapping edit. Mapping edit (CS-SETUP.1D.1), create/move/deactivate (CS-SETUP.1E), and membership management (CS-SETUP.1F) remain unapproved and unimplemented.

What was implemented on `/staff/structure/mappings/` (`staff_structure_mapping_review`):

- A staff-only, read-only page (`@staff_member_required` + `@require_GET`; access at least as strict as `/staff/structure/`; ordinary and anonymous users denied; POST returns 405).
- Three review tables — Ministry Contexts / 事工范围, Districts / 区, Small Groups / 小组 — listing every legacy row with: legacy label, legacy active/inactive status, mapped `ChurchStructureUnit` path label (when present), mapped unit status, and a simple mapping-status label (mapped to active unit / unmapped / mapped to inactive unit / mapped under holding-unassigned node).
- Django Admin edit links are display-only and permission-gated: the legacy-row change link appears only with the matching legacy change permission (`accounts.change_ministrycontext` / `change_district` / `change_smallgroup`), and the mapped-unit change link only with `accounts.change_churchstructureunit`. No new permission or capability was added.
- A bilingual safety note states the page reviews current data mapping only and does not change membership, event audience, Bible Study audience, serving assignments, or permissions.
- A link from `/staff/structure/` (near the setup-readiness / mapping-health actions) points to this page.
- No POST handler, no form, no inline edit, no save action, and no schema/migration. It changes no mappings, units, memberships, or audience rows, and alters no runtime visibility behavior; `ChurchStructureMembership` is not used as a visibility source and ordinary-user matching still resolves through `Profile.small_group` / legacy mappings.

CS-SETUP.1C.2 is a follow-up **read-only usability** slice on the same page. It adds a summary count area (all rows, mapped to active unit, unmapped, mapped to inactive unit, mapped under holding/unassigned node, and a needs-review total = unmapped + mapped inactive + mapped holding) and `?status=` GET filter links (`all`, `needs_review`, `mapped_active`, `unmapped`, `mapped_inactive`, `mapped_holding`) so a long mapping list can be narrowed to the rows that need attention. The page still defaults to all rows; the filter only shows/hides already-loaded rows and, when a section has no matching rows, shows a clear empty state. CS-SETUP.1C.2 adds no POST, no form, no inline edit, no save, no mapping/unit/membership/audience write, and no schema/migration. It **does not** implement mapping edit (future CS-SETUP.1D.1), and changes no runtime visibility behavior; `ChurchStructureMembership` is still not a visibility source and ordinary-user matching is untouched.

All Section 12.5 CS-SETUP.1A non-goals remain in force.

### 12.8 CS-SETUP.1D.0 — Legacy Mapping Maintenance Next-Slice Plan

CS-SETUP.1D.0 is a docs-only plan for the safest next Church Structure setup/edit slice after the read-only mapping review. It authorizes no code, schema, migration, template, view, test, data, or runtime behavior change.

Current state:

- `/staff/structure/` exists as the read-only structure map with setup-readiness / mapping-health context.
- CS-SETUP.1B exists as opt-in rename-only edit for `ChurchStructureUnit` display names; it cannot move units, change mappings, or affect audience rows.
- `/staff/structure/mappings/` exists as read-only legacy mapping review for `MinistryContext`, `District`, and `SmallGroup`.
- CS-SETUP.1C.2 adds summary counts and filters so staff can find unmapped, mapped-inactive, and holding-node mappings.
- No staff mapping write UI exists yet. Django Admin remains the only write surface for legacy-to-structure mapping fields.

Problem:

- Staff can now see unmapped rows, rows mapped to inactive units, and rows under holding/unassigned nodes.
- Staff cannot correct the `MinistryContext` / `District` / `SmallGroup` to `ChurchStructureUnit` mapping from staff UI yet.
- Django Admin can still make these changes, but it is a technical backstop rather than a guided staff workflow.
- The fix must not blur mapping maintenance with unit lifecycle editing, membership editing, or audience editing.

Recommended next implementation slice:

- Build a narrow mapping-maintenance UI for existing legacy rows only.
- Support only setting or changing one existing `MinistryContext`, `District`, or `SmallGroup` row's `church_structure_unit` to an existing active `ChurchStructureUnit`.
- Do not create, delete, activate, deactivate, move, merge, or split legacy rows.
- Do not create, delete, activate, deactivate, move, merge, split, or rename structure units in this slice.
- Do not edit `ChurchStructureMembership` rows or member rosters.
- Do not migrate runtime visibility, backfill audience rows, apply ServiceEvent audience scopes, remove legacy fields, or change consumer matching rules.

Safety rules for CS-SETUP.1D.1:

- Access is limited to staff with an explicit authorized structure setup/mapping capability; do not treat read-only map access as write access.
- Start from the read-only `/staff/structure/mappings/` page. Show an `Edit Mapping` / `编辑对应关系` action only to authorized staff.
- Use GET review plus explicit POST update. No inline auto-save.
- Require a selected target unit to be active.
- Require the target unit type to match the legacy object type:
  - `MinistryContext` -> `ministry_context` unit.
  - `District` -> `district` unit.
  - `SmallGroup` -> `small_group` unit.
- Prevent assigning the same active structure unit to multiple active legacy rows of the same type unless implementation review confirms the existing model rules allow it and the implementation plan explicitly justifies the exception.
- Do not alter `ServiceEventAudienceScope`, `BibleStudySeriesAudienceScope`, `TeamAssignment`, `Profile.small_group`, or `ChurchStructureMembership` rows when a mapping changes.
- Do not alter ServiceEvent visibility, Bible Study visibility, reading visibility, My Serving behavior, or ordinary-user matching.
- Write an audit record through Django `LogEntry` or the existing project audit pattern, including before/after mapped unit values and the acting user.
- Backend validation remains authoritative; UI filtering is only a convenience.

UX proposal:

- Entry point: `/staff/structure/mappings/`.
- Each eligible row has an `Edit Mapping` / `编辑对应关系` action.
- The edit page or card shows the legacy object name, legacy type, and active/inactive status.
- It shows the current mapped unit path and status, including clear empty state copy when unmapped.
- It offers a target-unit dropdown filtered to active units of the matching type.
- It shows a warning: `This only updates the setup mapping for future checks and helpers. It does not move members or change who can see events or Bible Study.` / `这里只更新设置对应关系，供后续检查和辅助选择使用；不会移动成员，也不会改变谁可以看到聚会或查经。`
- Buttons: `Save mapping` / `保存对应关系` and `Cancel` / `取消`.
- Empty/unmapped states should be plain and actionable: `No mapped structure unit yet` / `尚未对应教会结构单位`.
- Staff wording should name the action as mapping maintenance, not structure editing, membership editing, or audience editing.

Data contract:

- Mapping changes affect setup readiness indicators and future generation/selection helpers that depend on the legacy-to-unit bridge.
- Mapping changes do not automatically change existing `ServiceEventAudienceScope` rows.
- Mapping changes do not automatically change existing `BibleStudySeriesAudienceScope` rows.
- Mapping changes do not change existing `TeamAssignment` or `TeamAssignmentMember` rows.
- Mapping changes do not change `Profile.small_group`.
- Mapping changes do not create, update, end, approve, reject, or cancel `ChurchStructureMembership` rows.
- Mapping changes do not make `ChurchStructureMembership` a runtime visibility source.

Non-goals:

- No hierarchy create/move/delete/deactivate.
- No unit merge/split.
- No member roster management.
- No membership approval workflow changes.
- No audience-scope backfill/apply.
- No consumer migration.
- No Community Activities.
- No broad drag-and-drop hierarchy editing.
- No legacy field removal or deprecation.

Implementation milestone split:

- **CS-SETUP.1D.1 docs-reviewed implementation** — one mapping at a time, with permission, type/active validation, duplicate protection, explicit POST, audit, warnings, and targeted tests.
- **CS-SETUP.1D.2 optional warning polish / conflict indicators** — add richer conflict indicators after 1D.1 proves useful, such as clearer duplicate-risk, inactive-target, or holding-node cues.
- **CS-SETUP.1E future structure unit lifecycle design** — design only for create/move/delete/deactivate/merge/split. No implementation until separately approved.

Future implementation tests:

- Permission required: unauthorized users cannot see edit actions, GET the edit page, or POST updates.
- GET edit page renders the legacy object, current mapping, filtered active matching-type target choices, warning copy, Save, and Cancel.
- Valid mapping update changes only the selected legacy row's `church_structure_unit`.
- Reject inactive target unit.
- Reject wrong unit type.
- Reject duplicate active mapping when duplicate prevention applies.
- Audit log is created with before/after mapping context.
- No changes to `ServiceEventAudienceScope`.
- No changes to `BibleStudySeriesAudienceScope`.
- No changes to `ChurchStructureMembership`.
- No changes to `Profile.small_group`.
- Bilingual EN/ZH copy renders for warning, empty state, action, save, and cancel labels.

Risks:

- Mapping edits can affect future helpers, setup-readiness indicators, and staff interpretation even when runtime visibility is unchanged.
- Staff may misunderstand mapping maintenance as moving members, changing group membership, or changing who can see events/studies.
- Therefore CS-SETUP.1D.1 needs warning copy, a narrow edit surface, strict type/active validation, audit, and explicit non-goals before implementation.

Implementation note (CS-SETUP.1D.1, implemented): the staff mapping review page (`/staff/structure/mappings/`) now shows an `Edit Mapping / 编辑对应关系` action on each legacy row, gated by the matching Django change permission (`accounts.change_ministrycontext` / `change_district` / `change_smallgroup`) on top of `staff_member_required`. The new edit page (`staff_structure_mapping_edit`) renders the legacy object name/type/status, the current mapped unit and its status, and a target dropdown limited to active units of the matching `ChurchStructureUnit` type, with the required warning copy and Save/Cancel. Save is an explicit CSRF POST that updates only `church_structure_unit` (`update_fields`) after authoritative backend validation (required / exists / active / type-match / duplicate-active, with the current row allowed to keep its existing mapping), writes a Django `LogEntry` CHANGE record with before/after unit context, shows a success message, and redirects back to the review page preserving the prior `status` filter. It changes no unit lifecycle, membership, `ServiceEventAudienceScope`, `BibleStudySeriesAudienceScope`, `TeamAssignment`, `Profile.small_group`, or runtime visibility, and adds no schema/migration.

## 13. Related Documents

- `docs/CHURCH_STRUCTURE_FOUNDATION_PLAN.md` — foundation history (CS-F.x, CS-H.x).
- `docs/CHURCH_STRUCTURE_MAPPING_AND_MEMBERSHIP_STRATEGY.md` — mapping/membership source-of-truth strategy.
- `docs/SERVICE_EVENT_AUDIENCE_RUNTIME_MIGRATION_PLAN.md` — SE-AS.4/5/6 plan and the concept separation table this plan extends.
- `docs/STAFF_ADMIN_SURFACE_EXPANSION_PLAN.md` — read-only staff surface pattern (PP-SA.x) that CS-MAP.2 follows.
- `docs/COMMUNITY_ACTIVITIES_V1_PLAN.md` — Community Activities position, unchanged by this plan.
- `docs/UI_UX_GUARDRAILS.md` — staff/normal-user wording rules.
- `docs/POST_PILOT_BACKLOG_TRIAGE.md` — June 2026 demo feedback record.
