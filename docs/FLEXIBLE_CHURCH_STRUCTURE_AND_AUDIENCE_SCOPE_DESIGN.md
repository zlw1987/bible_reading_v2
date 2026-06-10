# Flexible Church Structure and Audience Scope Design

## 1. Purpose

This document records the CS-H.1 design direction for flexible church structure and audience scope. CS-H.2 has since added the model-only `ChurchStructureUnit` foundation without changing current product behavior, CS-H.2A hardens tree validation against indirect cycles, CS-H.3 records the mapping, membership, and signup/onboarding strategy, CS-H.3B adds nullable legacy-to-`ChurchStructureUnit` mapping fields, CS-H.3C adds an explicit idempotent seeding/mapping management command, CS-H.3D records successful GoDaddy production/staging seeding verification, CS-H.3E closes the remaining seeded data QA item, CS-H.4 records the `ChurchStructureMembership` design, CS-H.5A adds the model-only membership foundation, CS-H.5B hardens membership helpers/validation, CS-H.5C adds an explicit dry-run/apply membership backfill command, CS-H.5D records user-attested GoDaddy production/staging backfill verification, CS-H.5E improves Django Admin clarity for legacy structure models versus future foundation models, CS-H.6 through CS-H.7E add requested-unit capture and staff approval/sync slices, CS-H.8 records the integrated request-flow checkpoint, CS-H.9 records membership request UX hardening, and CS-H.10 records the CMS hardening checkpoint.

DOCS-AS.1 records the shared audience-scope direction. `ChurchStructureUnit` is the shared flexible structure foundation for future audience selection. App modules should use app-specific join models to `ChurchStructureUnit` rather than adding more legacy-only multi-select scope fields. Bible Study Schedule audience scope is now selected as the first narrow runtime consumer candidate, because it can safely resolve selected `ChurchStructureUnit` rows into legacy `SmallGroup` rows for meeting generation while keeping ordinary member visibility on `Profile.small_group`. ServiceEvent / Church Gatherings and future Community Activities should follow the same `ChurchStructureUnit` audience-scope foundation in later milestones. This is not a migration of ordinary user visibility to `ChurchStructureMembership`; that runtime visibility migration remains deferred.

The current short-term bridge served pilot needs:
- `MinistryContext`
- `District`
- `SmallGroup`
- `Profile.small_group`
- `District.ministry_context`
- `BibleStudySeries.ministry_context` schedule scope
- optional `ServiceEvent.ministry_context` label

Pilot validation passed on `v0.9-pilot-rc1`, and these current structures are acceptable for the pilot baseline. Future needs require a flexible hierarchy and multi-select audience scope, but this document is for future implementation planning only. It does not authorize immediate model, migration, view, form, template, filtering, or permission changes.

The project remains a lightweight Church Life workflow system. It should support spiritual practices, Bible Study, service operations, and focused community workflows without becoming a full church ERP.

## 2. Current State

### `MinistryContext`

`MinistryContext` currently represents broad ministry context or language ministry, such as CM and EM.

Current fields:
- `code`
- `name`
- `name_en`
- `description`
- `description_en`
- `is_active`
- `sort_order`
- `created_at`

CM and EM are `MinistryContext` records, not `MinistryTeam` records. There should not be a fake Combined Ministry record; combined events or activities should reference both CM and EM when the future audience model supports it.

### `District`

`District` currently represents a district in the fellowship or Bible Study structure.

Current fields:
- `name`
- `ministry_context`
- `is_active`
- `created_at`

`District.ministry_context` is the current bridge from district to CM/EM.

### `SmallGroup`

`SmallGroup` currently represents a fellowship or small-group structure, including Friday Bible Study groups.

Current fields:
- `name`
- `district`
- `is_active`

`SmallGroup` is not `MinistryTeam`. Small-group coworker roles and Friday Bible Study responsibilities should not be forced into Ministry Operations models.

### `Profile.small_group`

`Profile.small_group` stores the user's current primary small group.

This is a short-term current-state field, not membership history. It is still the baseline for current Bible Study meeting visibility and ServiceEvent district/small-group visibility.

### `BibleStudySeries` Scope Fields

`BibleStudySeries` currently acts as the Bible Study Schedule model.

Current scope fields:
- `scope_type`
- `ministry_context`
- `district`
- `small_group`

Supported schedule scope:
- whole church
- ministry context
- district
- small group

`BibleStudySeries.get_eligible_small_groups()` uses the current bridge to resolve active groups for generated small-group meetings. This works for the pilot baseline and should not be rushed into the flexible model before another consumer proves the design.

### `ServiceEvent` Scope Fields

`ServiceEvent` remains the official church gathering and operations anchor.

Current scope fields:
- `scope_type`
- `district`
- `small_group`
- `ministry_context`

Current audience scope supports only:
- whole church
- one district
- one small group

`ServiceEvent.ministry_context` is label-only. It must not drive audience filtering, My Serving visibility, TeamAssignment visibility, or MinistryTeam behavior in the current baseline.

### `TeamAssignment` and `MinistryTeam` Boundaries

`MinistryTeam` represents serving or operations teams, such as Lighting, Audio, Video, Projection, or other service teams.

`TeamAssignment` links a `ServiceEvent` to a `MinistryTeam` and assigned `TeamMembership` records. Serving assignments are manual operational assignments. Audience scope should not automatically assign serving members.

### `BibleStudyMeeting` and `BibleStudyMeetingRole` Boundaries

`BibleStudyMeeting` is anchored to a `BibleStudyLesson` and a `SmallGroup`. Normal user visibility remains tied to the user's current `Profile.small_group`.

`BibleStudyMeetingRole` represents per-meeting Bible Study responsibilities such as discussion leader, worship lead, pianist, support, or host. It is not `TeamAssignment` and should not be confused with ministry serving operations.

### ServiceEvent and CommunityActivity Boundary

`ServiceEvent` is the official church gathering/event anchor, especially when ministry teams may serve.

`CommunityActivity` is a future signup-oriented module for activities where the primary question is who can attend or sign up. It should be separate from `ServiceEvent`, though a future optional link may be considered for large events that need both signup and operations.

## 3. Problem Statement

The current fixed fields cannot express the future church structure and audience needs.

Current pain:
- `ServiceEvent` scope supports only one whole-church, district, or small-group target.
- A district selection binds to the district and does not expand child small groups.
- CM and EM together cannot be represented cleanly.
- Multiple districts cannot be selected.
- Multiple small groups cannot be selected.
- Mixed parent/child audience cannot be represented.
- Future variable-depth structure cannot be represented without more fixed columns.

Examples that current fields cannot express:
- CM as a whole.
- CM plus EM.
- EM > District A.
- District B > selected groups.
- CM as a whole plus EM > District A.
- CM > District A > Rainbow 1 and Rainbow 2.
- CM > District A plus EM > District C > Group 3.

The next design needs a tree that can represent variable depth and a selection model that can store more than one selected audience branch.

## 4. Target Hierarchy Model

Future model concept:

`ChurchStructureUnit`
- `id`
- `parent` nullable FK to self
- `unit_type`
- `code`
- `name`
- `name_en`
- `description`
- `description_en`
- `is_active`
- `sort_order`
- `created_at`
- `updated_at`

Possible `unit_type` values:
- `root`
- `ministry_context`
- `district`
- `small_group`
- `fellowship`
- `department`
- `custom`

Rules:
- Root represents Whole Church / 全教会.
- The model must not hard-code Church -> CM/EM -> District -> SmallGroup forever.
- Different branches may have different depth.
- CM and EM do not need identical depth.
- Future structures such as fellowships, departments, classes, or custom units should be possible without another schema redesign.
- Current `MinistryContext`, `District`, and `SmallGroup` can be bridged or migrated later.

Root may be persisted or virtual; this remains an open decision. Persisting root usually makes selection storage, historical display, and admin UI simpler, but it creates one special system row that must be protected.

CS-H.2 implementation note:
- `ChurchStructureUnit` exists as a model-only foundation.
- CS-H.2A rejects indirect parent cycles and makes ancestor/path display safe against corrupted cycles.
- No root, CM, EM, district, or small-group rows are created automatically by migrations or app startup.
- Existing `MinistryContext`, `District`, `SmallGroup`, and `Profile.small_group` remain the source of current behavior.
- No audience selection or filtering uses `ChurchStructureUnit` yet.
- One active Whole Church root is the intended future system shape, but root uniqueness enforcement is deferred until root seeding/mapping policy is decided.

CS-H.3 strategy note:
- Long-term source of truth should be `ChurchStructureUnit` for structure and `ChurchStructureMembership` for belonging.
- Short-term runtime behavior continues to use `MinistryContext`, `District`, `SmallGroup`, and `Profile.small_group`.
- CS-H.3B adds nullable mapping fields from `MinistryContext`, `District`, and `SmallGroup` to `ChurchStructureUnit`, but they do not drive current behavior.
- CS-H.3C adds `seed_church_structure_units` with dry-run/apply modes to seed a `CHURCH` root, mirror current structure units, and fill legacy mapping fields. It does not auto-run and still does not make `ChurchStructureUnit` drive runtime behavior.
- CS-H.3D verifies the GoDaddy apply and clean second dry-run.
- CS-H.3E records that the `Santa Clara 3` legacy data issue was handled and the seeded structure data QA item is closed, as long as final dry-run remains clean.
- CS-H.4 designs `ChurchStructureMembership` and requested-unit approval flow.
- CS-H.5A adds `ChurchStructureMembership` model/admin/tests only. It does not add signup flow, approval UI, backfill, audience selection, filtering, or consumer migration.
- CS-H.5B adds helper/query hardening only. Requested, rejected, cancelled, and ended memberships still do not grant visibility.
- CS-H.5C adds `backfill_church_structure_memberships` for explicit dry-run/apply membership backfill from mapped `Profile.small_group` values. It does not modify `Profile.small_group`, add signup or approval UI, add audience selection or filtering, or migrate any runtime consumer.
- CS-H.5D records production/staging backfill verification as user-attested. Exact command-output counts were not recorded. No runtime source-of-truth switch is authorized.
- CS-H.5E improves Django Admin clarity only. Legacy `MinistryContext`, `District`, `SmallGroup`, and `Profile.small_group` remain current runtime source during transition and must not be deleted yet.
- CS-H.6/CS-H.6B/CS-H.6D add requested-unit capture from signup and Profile for staff review, not direct final self-assignment.
- CS-H.7B/C/D/E add staff request review, approve/reject actions, and narrow `Profile.small_group` approval sync.
- CS-H.8 verified the integrated signup/Profile/staff approval flow. CS-H.9 membership request UX hardening is complete. CS-H.10 records the CMS hardening checkpoint, including deferred/accepted mobile nav polish and the root `AGENTS.md` verification policy.
- Runtime consumers still primarily use `MinistryContext`, `District`, `SmallGroup`, and `Profile.small_group`; `/studies/`, reading progress, `ServiceEvent`, My Serving, and other consumers are not yet driven by `ChurchStructureMembership`.
- See `docs/CHURCH_STRUCTURE_MAPPING_AND_MEMBERSHIP_STRATEGY.md`.

## 5. Membership Model

Future model concept:

`ChurchStructureMembership`
- `user`
- `unit`
- `role` or `membership_type`
- `start_date`
- `end_date` nullable
- `is_primary`
- `is_active` or derived from date range
- `notes` optional, non-sensitive

Rules:
- `Profile.small_group` remains the current primary-small-group field in the short term.
- Future membership history should support movement over time.
- Current visibility can continue using current active membership until historical rules are explicitly needed.
- Do not import sensitive/private data.
- Do not import phone/private contact data.
- Do not overbuild an HR/personnel system.
- Notes must be non-sensitive and operational only.

Membership should be planned separately from hierarchy. A structure unit can exist without immediately importing full membership history.

CS-H.4 design note:
- `ChurchStructureMembership` should become the eventual belonging source.
- `Profile.small_group` remains the runtime source during transition.
- Requested membership must not grant visibility.
- Only approved active membership may be considered by future consumers after explicit migration and tests.
- CS-H.5A model-only foundation exists, but current runtime still uses `Profile.small_group`.
- CS-H.5B query helpers are available for future phases, but no current consumer uses them.
- CS-H.5C backfill command exists and CS-H.5D production/staging verification is recorded by user confirmation, but no current consumer uses membership yet.
- CS-H.5E admin clarity exists to reduce staff confusion.
- CS-H.6/CS-H.6B/CS-H.6D requested-unit capture and CS-H.7B/C/D/E staff approval/sync slices exist, but consumer migration remains future.
- See `docs/CHURCH_STRUCTURE_MEMBERSHIP_DESIGN.md`.

## 6. Audience Selection Model

Future audience selection should store selected `ChurchStructureUnit` rows for a target object.

Possible generic name:

`AudienceSegment`

Possible app-specific through models:
- `ServiceEventAudienceSelection`
- `CommunityActivityAudienceSelection`
- `BibleStudySeriesAudienceSelection`

Each row should link:
- target object
- `ChurchStructureUnit`
- include/exclude flag only if needed later
- `created_at`

Recommendation for this project: use app-specific join models first.

Reason:
- Safer migrations and clearer ownership.
- Easier permissions per module.
- Easier validation per consumer.
- Avoids generic content-type complexity before the audience behavior proves stable.
- Keeps Bible Study, ServiceEvent, and CommunityActivity boundaries explicit.

V1 should be include-only unless real use proves exclusion is necessary. Exclusion adds permission and preview complexity and should not be added speculatively.

## 7. Selection Semantics

Future UI and logic rules:
- Root = Whole Church / 全教会.
- If Whole Church is selected, stop expansion and clear or disable lower-level selections.
- Every non-root level allows multi-select.
- Selecting a parent expands its children.
- If a selected parent has no selected children, the target binds to that parent.
- If a selected parent has selected children, the selected children become the effective targets for that branch.
- Each branch resolves independently.
- The final UI must show an effective audience preview.

Examples:
- Whole Church.
- CM.
- CM + EM.
- CM > District A.
- CM > District A > Rainbow 1, Rainbow 2.
- CM + EM > District B.
- CM > District A + EM > District C > Group 3.

This rule intentionally treats child selection as narrowing a selected branch. If a future workflow needs both a parent and specific children selected explicitly, that should be a later "include parent and child" mode with its own UI and tests.

## 8. Effective Audience Calculation

Conceptual algorithm:
- Input: selected tree nodes.
- Output: normalized effective target nodes.
- If root is selected, output root only.
- For each selected non-root node, check whether any selected descendant exists.
- Remove a selected parent when a selected child or descendant under that parent exists.
- Keep selected parent nodes that have no selected descendants.
- Deduplicate nodes.
- Exclude inactive units from the selectable UI.
- Preserve historical display of old selections even if a unit later becomes inactive.

Examples:
- Selected `CM` only -> effective `CM`.
- Selected `CM`, `CM > District A` -> effective `CM > District A`.
- Selected `CM`, `CM > District A`, `CM > District B` -> effective `CM > District A` and `CM > District B`.
- Selected `CM > District A`, `CM > District A > Rainbow 1` -> effective `Rainbow 1`.
- Selected root plus anything else -> effective root only.

No code is implemented in this phase.

## 9. UI Design

Future staff UI should provide:
- hierarchical selector
- multi-select at each non-root level
- child expansion for selected parents
- effective audience preview panel
- clear all / reset action
- search if the tree grows large
- bilingual labels
- mobile-friendly progressive disclosure
- staff-only structure setup and audience editing

Normal users should see readable audience labels, not complex tree controls.

Recommended display patterns:
- Whole Church / 全教会.
- Chinese Ministry / 中文事工.
- English Ministry / 英文事工.
- CM > District A.
- CM > District A > Rainbow 1, Rainbow 2.

Mobile behavior should avoid a dense full-tree panel. A step-by-step drilldown or expandable sections are preferable. Long bilingual labels must wrap cleanly.

## 10. Migration / Coexistence Strategy

### Phase CS-H.2: Model-Only Foundation

- Add `ChurchStructureUnit` model only.
- Keep old models unchanged.
- No behavior change.
- No filtering change.
- No destructive migration.
- No data seeding or mapping yet.

### Phase CS-H.3: Current Structure Mapping

- Add mapping or bridge between old models and `ChurchStructureUnit`.
- Seed root plus current `MinistryContext`, `District`, and `SmallGroup` into the tree if the mapping design chooses persisted units.
- Decide whether to enforce one active Whole Church root in the database during or before seeding.
- Keep `Profile.small_group`.
- Keep current `BibleStudySeries` scope behavior.
- Decide which model is source of truth during the bridge period.
- CS-H.3B completed nullable mapping fields.
- CS-H.3C completed explicit idempotent seeding/mapping through `python manage.py seed_church_structure_units`.
- CS-H.3D completed production/staging seeding verification. Runtime behavior still uses `MinistryContext`, `District`, `SmallGroup`, and `Profile.small_group`.
- CS-H.3E completed seeded structure data QA closure. Runtime behavior still uses `MinistryContext`, `District`, `SmallGroup`, and `Profile.small_group`.
- CS-H.4 completed membership design. Runtime behavior still uses `MinistryContext`, `District`, `SmallGroup`, and `Profile.small_group`.
- CS-H.5A completed membership model-only foundation. Runtime behavior still uses `MinistryContext`, `District`, `SmallGroup`, and `Profile.small_group`.
- CS-H.5B completed membership helper/validation hardening. Runtime behavior still uses `MinistryContext`, `District`, `SmallGroup`, and `Profile.small_group`.
- CS-H.5C completed the explicit membership backfill command.
- CS-H.5D completed production/staging backfill verification by user-attested GoDaddy run; exact output counts were not recorded. Runtime behavior still uses `MinistryContext`, `District`, `SmallGroup`, and `Profile.small_group`.
- CS-H.5E completed Django Admin clarity for legacy structure versus future structure/membership foundation. Runtime behavior still uses `MinistryContext`, `District`, `SmallGroup`, and `Profile.small_group`.
- CS-H.6/CS-H.6B/CS-H.6D completed signup/Profile requested-unit capture. Request submission does not update `Profile.small_group`.
- CS-H.7B/C/D/E completed staff request review, approve/reject actions, and narrow approval sync to `Profile.small_group`.
- CS-H.8 integration checkpoint completed. Runtime consumers still use legacy structure models and `Profile.small_group`.
- CS-H.9 membership request UX hardening completed.
- CS-H.10 CMS hardening checkpoint completed. Mobile nav polish remains deferred/accepted for now, and root `AGENTS.md` verification policy has been added.

### Later Phase: First Audience Consumer

- DOCS-AS.1 decision: Bible Study Schedule is the first narrow runtime consumer candidate for `ChurchStructureUnit` audience selection.
- Bible Study Schedule is first because it can safely resolve selected structure units into legacy `SmallGroup` rows for meeting generation while keeping member visibility on `Profile.small_group`.
- Use an app-specific join model such as `BibleStudySeriesAudienceScope` to select `ChurchStructureUnit` rows; do not add more legacy-only multi-select scope fields.
- Keep behavior narrow.
- Do not add broad filtering until the data model and UI are tested.
- Keep existing fixed fields available during coexistence.

### Later Phase: ServiceEvent and Community Activities Audience Scope

- ServiceEvent / Church Gatherings and future Community Activities should follow the same `ChurchStructureUnit` audience-scope foundation in later milestones.
- `ServiceEventAudienceScope` already exists as a model-only foundation (SE-AS.2); it does not yet drive runtime visibility. Runtime ServiceEvent visibility still uses legacy `scope_type` / `district` / `small_group` and `Profile.small_group`.
- Future Community Activities should use a `ChurchStructureUnit`-based audience-scope design rather than inventing a separate legacy-only audience segment system.
- Preserve safe `BibleStudyMeeting` visibility.
- Avoid breaking generated meeting workflows.

### Later Phase: Deprecation Consideration

- Consider deprecating old fixed fields only after safe migration, tested data reconciliation, and clear rollback strategy.
- No hard cutover.
- Avoid breaking the pilot baseline.

## 11. Module Impact

### A. Bible Study

Existing `BibleStudySeries` scope currently works. Under DOCS-AS.1, Bible Study Schedule is the first narrow `ChurchStructureUnit` audience-scope runtime consumer candidate, via a future app-specific join model such as `BibleStudySeriesAudienceScope`. Selected `ChurchStructureUnit` rows should resolve to eligible legacy `SmallGroup` rows for meeting generation; generated `BibleStudyMeeting` rows still point to legacy `SmallGroup`.

Future audience selection may support richer schedules, but `BibleStudyMeeting` visibility must remain safe. Ordinary member visibility continues to use `Profile.small_group`, and normal users should not gain cross-small-group visibility because of a structure migration.

### B. ServiceEvent

Current `ServiceEvent.ministry_context` remains label-only.

Future audience selection may replace or augment `scope_type`, `district`, and `small_group`. Filtering must be a later explicit design and should not be bundled into the structure model foundation.

### C. Community Activities

Future `CommunityActivity` should use a `ChurchStructureUnit`-based audience-scope design from the start, through an app-specific join model, rather than a separate legacy-only audience segment system. It should remain signup-oriented and separate from `ServiceEvent`.

Do not implement Community Activities as part of CS-H.1.

### D. My Serving / TeamAssignment

Serving assignments are based on `TeamAssignment`, not audience alone.

Audience selection may answer who an event or activity is for. It should not automatically assign serving members or create `TeamAssignmentMember` records.

### E. MinistryTeam

`MinistryTeam` remains a serving/operations team. It is not fellowship/church structure.

CM/EM, districts, and small groups should not be modeled as `MinistryTeam` records.

### F. Staff Admin

Future Staff Admin UI may manage structure units, mapping, and memberships.

This is not part of CS-H.1. Staff Admin Surface Expansion remains a separate planning/implementation track.

## 12. Risks

Known risks:
- Overbuilding toward a full ERP.
- Confusing audience with serving assignment.
- Permission leaks from overly broad audience joins.
- Breaking Bible Study visibility.
- Migrating too early.
- Data cleanup complexity.
- UI complexity for non-technical staff.
- Duplicate structures if `MinistryContext`, `District`, `SmallGroup`, and `ChurchStructureUnit` drift apart.
- Historical ambiguity if units are renamed, moved, merged, or deactivated without audit rules.
- Staff confusion if parent selection and child selection semantics are not previewed clearly.

Mitigation direction:
- Use phased implementation.
- Keep old models during coexistence.
- Add one consumer first.
- Require effective audience preview before publish.
- Preserve historical labels.
- Treat filtering and permissions as separate explicit work.

## 13. Non-Goals

CS-H.1 does not include:
- implementation
- models
- migrations
- templates, CSS, forms, views, tests, settings, or URLs
- full ERP
- automatic scheduling
- attendance
- HR/personnel system
- sensitive/private data import
- immediate replacement of `Profile.small_group`
- immediate replacement of existing `BibleStudySeries` scope fields
- immediate `ServiceEvent` filtering
- Community Activities implementation
- Checklist implementation
- Staff Admin Surface implementation

## 14. Recommended Next Implementation Phases

Possible next planning or implementation steps:
- CS-H.2 ChurchStructureUnit model-only foundation. Completed.
- CS-H.2A ChurchStructureUnit model hardening. Completed.
- CS-H.3 current structure mapping and membership strategy. Completed.
- CS-H.3B nullable legacy mapping fields model-only. Completed.
- CS-H.3C idempotent structure seeding command. Completed.
- CS-H.3D production/staging seeding verification closure. Completed.
- CS-H.3E seeded structure data QA closure. Completed.
- CS-H.4 ChurchStructureMembership design doc. Completed.
- CS-H.5A ChurchStructureMembership model-only foundation. Completed.
- CS-H.5B membership model hardening/tests. Completed.
- CS-H.5C membership backfill command with dry-run/apply. Completed.
- CS-H.5D production/staging backfill verification. Completed by user-attested GoDaddy run; exact output counts were not recorded.
- CS-H.5E Django Admin clarity for legacy structure vs future structure/membership foundation. Completed.
- CS-H.6/CS-H.6B/CS-H.6D signup/Profile requested-unit capture. Completed.
- CS-H.7B/C/D/E staff request review, approve/reject actions, and narrow `Profile.small_group` approval sync. Completed.
- CS-H.8 integrated membership request flow checkpoint. Completed.
- CS-H.9 membership request UX hardening. Completed.
- CS-H.10 CMS hardening checkpoint. Completed.
- Later audience selection model design for one consumer.
- CA-V1.1 Community Activities planning refinement.
- PP-SA.1 Staff Admin Surface Expansion Plan.

Choose based on real post-pilot feedback. Do not implement all of these at once.

Recommended immediate next step after CS-H.1: choose whether the first concrete follow-up should be CS-H.2 model-only foundation or PP-SA.1 Staff Admin Surface Expansion Plan based on the strongest post-pilot pain.

## 15. Decision Checklist

Open decisions:
- Generic audience model vs app-specific through models.
- Whether root is persisted or virtual.
- Whether old `MinistryContext`, `District`, and `SmallGroup` remain source of truth long-term.
- First narrow runtime consumer (DOCS-AS.1 decision): Bible Study Schedule (`BibleStudySeries`) audience scope, resolving selected `ChurchStructureUnit` rows to legacy `SmallGroup` while member visibility stays on `Profile.small_group`. ServiceEvent and Community Activities follow the same foundation later.
- How to expose structure admin UI.
- How much membership history is needed.
- Whether selection rows should store display snapshots for historical labels.
- Whether include/exclude is needed later or include-only is enough.
- How to handle moved or merged units in historical reports.

Current recommendation:
- Prefer app-specific through models first.
- Prefer include-only V1.
- Prefer no destructive migration.
- Prefer one consumer before broad adoption.
- Preserve the validated pilot baseline.
