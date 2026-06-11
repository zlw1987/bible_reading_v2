# Church Structure Map and Setup Readiness Plan

## 1. Purpose and Status

CS-MAP.1 is a docs-only planning pass. No code, schema, migration, template, form, view, URL, test, settings, or runtime behavior is changed by this task.

This plan responds to two June 2026 demo feedback items:

1. IM team lead: the app cannot realistically replace every existing church app at once; it should be modular, adopted module by module, and able to coexist/integrate with existing tools (for example 微读圣经 for small-group reading/study content).
2. Pastor/elder/deacon: leadership wants a clear church structure architecture, setup support, and a visible structure map / hierarchy map; structure setup currently happens mainly through Django Admin, which is not convenient for them; they see church structure as a foundation for many future modules.

This plan defines a docs-first response: record the modular adoption principle, then propose a read-only staff structure map with mapping-health indicators (CS-MAP.2) before any setup/edit UI is considered. Later milestones each require separate explicit approval; nothing beyond this document is authorized by CS-MAP.1.

Status update: CS-MAP.2 is now complete (see Section 7 for the completion note), SE-AS.5B post-commit cleanup clarified the visible wording and count semantics on the shipped read-only map, and CS-MAP.2B updates the map tree to use the same hierarchical node-level expand/collapse mental model as the ServiceEvent audience picker. CS-MAP.3 remains optional and unapproved. CS-SETUP.1 remains explicitly unapproved and gated per Section 6.

## 2. Current Foundation Summary

Audited from the current working tree:

- `ChurchStructureUnit` (`accounts/models.py`): flexible variable-depth tree foundation with `parent`, `unit_type` (root / ministry_context / district / small_group / fellowship / department / custom), bilingual names, `is_active`, `sort_order`, unique parent+code, direct/indirect cycle validation, and cycle-safe `get_ancestors()` / `path_label()` helpers.
- `ChurchStructureMembership` (`accounts/models.py`): future belonging foundation with requested/active/ended/rejected/cancelled lifecycle, one-active-primary-per-user enforcement, date windows, approval audit fields, and `active_for_user()` / `current_primary_for_user()` helpers. It is not a runtime visibility source.
- Legacy bridge mappings: nullable `church_structure_unit` fields on `MinistryContext`, `District`, and `SmallGroup` (`accounts/models.py`), explicitly non-runtime.
- Commands: `seed_church_structure_units` (mirrors legacy structure into the unit tree under a `CHURCH` root with `UNASSIGNED-DISTRICTS` / `UNASSIGNED-GROUPS` holding nodes) and `backfill_church_structure_memberships` (creates active primary memberships from mapped `Profile.small_group`). Both default to dry-run with explicit `--apply`; production/staging runs are verified (CS-H.3D/3E, CS-H.5D).
- Bible Study Schedule is the first narrow runtime consumer: `BibleStudySeriesAudienceScope` (`studies/models.py`) resolves selected units to eligible legacy `SmallGroup` rows for meeting generation; ordinary member visibility still uses `Profile.small_group`.
- `ServiceEventAudienceScope` (`events/models.py`) is model-only and not a runtime source; ServiceEvent visibility still uses legacy `scope_type` / `district` / `small_group` and `Profile.small_group` (see `docs/SERVICE_EVENT_AUDIENCE_RUNTIME_MIGRATION_PLAN.md`).
- Staff surfaces: read-only overview at `/staff/`, membership request review/approve/reject at `/staff/membership-requests/`, moderation queue at `/staff/moderation/`. There is no staff page that renders the structure hierarchy; the shared audience picker (`templates/shared/_church_structure_unit_audience_picker.html`) renders the tree only as a form selector. Structure setup (units, districts, groups) happens only in Django Admin.

Runtime visibility sources remain the legacy scope fields and `Profile.small_group` across all consumers except the narrow Bible Study meeting-generation eligibility described above.

## 3. Product Principle: Modular Adoption and Coexistence

Recorded as a product principle from the June 2026 demo feedback:

- The CMS must not require a church to replace all existing church apps at once.
- Modules should be adoptable one by one. The existing module boundaries and legacy-fallback behavior already support this: a church can use Daily Reading without Bible Study, or My Serving without either.
- External tools may coexist with CMS modules. For example, a small group may keep using 微读圣经 for reading/study content while the CMS provides structure, scheduling, and audience scope.
- Integration initially means link/reference/mapping (the same pattern as "link to Google Docs playbooks, do not import them"), not deep API integration or data import.
- No external-system integration work (APIs, imports, embeds, sync) is authorized by this plan. Any future integration requires its own separately approved plan.

The church structure foundation is the coexistence enabler, not a competitor to external tools: the CMS owns structure, belonging, audience, and workflow; external tools can keep owning content within a group.

## 4. Pastor/Staff Expectation and Safe Response Path

Leadership needs to see and trust the church structure: a visible hierarchy map, who-belongs-where counts, and confidence that setup data is healthy. Today the unit tree is invisible outside Django Admin, and the only mapping-health reporting is CLI command dry-run output.

"Setup support" must not be read as "build edit UI now." Editing `ChurchStructureUnit` today has no runtime effect, because runtime visibility still uses legacy fields and `Profile.small_group`. A staff edit UI would therefore look authoritative while being inert — the same staff-confusion failure mode that `docs/SERVICE_EVENT_AUDIENCE_RUNTIME_MIGRATION_PLAN.md` Section 4 rejected for the audience selector. Django Admin remains the structure write surface for now: it already distinguishes legacy runtime models from future foundation models (CS-H.5E), and model `full_clean()` validation enforces tree integrity there.

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
| Audience Scope / 适用范围 | `BibleStudySeriesAudienceScope` (runtime for meeting generation), `ServiceEventAudienceScope` (model-only); legacy scope fields elsewhere | Who an event/schedule is for. Per-module join models selecting units. |
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
| SE-AS.4 | ServiceEvent audience runtime visibility rule with legacy fallback | Planned in `docs/SERVICE_EVENT_AUDIENCE_RUNTIME_MIGRATION_PLAN.md`; separate approval |
| SE-AS.5 | ServiceEvent staff audience selector UI/display | Planned; separate approval |
| CS-MAP.3 | Optional setup readiness checklist on the structure map page | Optional; separate approval |
| CA V1 | Community Activities planning, then implementation | Later; separate plan; not pulled forward by this feedback |
| CS-SETUP.1 | Limited structure setup/edit UI | Not approved; gated (see below) |

Sequencing rules:

- CS-MAP.2 landed before SE-AS.4/SE-AS.5, as recommended from a product-risk perspective: the SE-AS.5 selector's biggest operational risk is staff selecting units that match no current members, and the mapping-health surface mitigates that before the selector exists. SE-AS.4 is technically independent of CS-MAP.2 (no shared data or code path) and is the next candidate slice, but it still requires its own separate approval and must never be bundled with CS-MAP work.
- Community Activities must not be pulled forward by this feedback. Its position (after the audience foundation is proven through Bible Study and ServiceEvent) is unchanged per `docs/COMMUNITY_ACTIVITIES_V1_PLAN.md`.
- CS-SETUP.1 is explicitly not approved. It is gated on: (a) CS-MAP.2 shipped and used, with evidence that read-only visibility plus Django Admin is insufficient for a recurring staff task; (b) a separate design doc resolving unit↔legacy sync direction (today only seeding writes units from legacy; two-way sync is undesigned), edit permissions/capabilities, and the effect of unit moves/deactivation on stored audience rows; (c) separate explicit approval.
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
| The map implies the unit tree is already the runtime source of truth; staff edit units in Django Admin expecting runtime change | Reuse the existing `/staff/` transition-banner pattern; staff wording per `docs/UI_UX_GUARDRAILS.md` makes explicit that current visibility still runs on existing small-group data. |
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

## 12. Related Documents

- `docs/CHURCH_STRUCTURE_FOUNDATION_PLAN.md` — foundation history (CS-F.x, CS-H.x).
- `docs/CHURCH_STRUCTURE_MAPPING_AND_MEMBERSHIP_STRATEGY.md` — mapping/membership source-of-truth strategy.
- `docs/SERVICE_EVENT_AUDIENCE_RUNTIME_MIGRATION_PLAN.md` — SE-AS.4/5/6 plan and the concept separation table this plan extends.
- `docs/STAFF_ADMIN_SURFACE_EXPANSION_PLAN.md` — read-only staff surface pattern (PP-SA.x) that CS-MAP.2 follows.
- `docs/COMMUNITY_ACTIVITIES_V1_PLAN.md` — Community Activities position, unchanged by this plan.
- `docs/UI_UX_GUARDRAILS.md` — staff/normal-user wording rules.
- `docs/POST_PILOT_BACKLOG_TRIAGE.md` — June 2026 demo feedback record.
