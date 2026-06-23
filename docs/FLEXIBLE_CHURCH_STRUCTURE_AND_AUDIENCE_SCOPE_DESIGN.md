# Flexible Church Structure and Audience Scope Design

## 1. Purpose

This document records the CS-H.1 design direction for flexible church structure and audience scope. CS-H.2 has since added the model-only `ChurchStructureUnit` foundation without changing current product behavior, CS-H.2A hardens tree validation against indirect cycles, CS-H.3 records the mapping, membership, and signup/onboarding strategy, CS-H.3B adds nullable legacy-to-`ChurchStructureUnit` mapping fields, CS-H.3C adds an explicit idempotent seeding/mapping management command, CS-H.3D records successful GoDaddy production/staging seeding verification, CS-H.3E closes the remaining seeded data QA item, CS-H.4 records the `ChurchStructureMembership` design, CS-H.5A adds the model-only membership foundation, CS-H.5B hardens membership helpers/validation, CS-H.5C adds an explicit dry-run/apply membership backfill command, CS-H.5D records user-attested GoDaddy production/staging backfill verification, CS-H.5E improves Django Admin clarity for legacy structure models versus future foundation models, CS-H.6 through CS-H.7E add requested-unit capture and staff approval/sync slices, CS-H.8 records the integrated request-flow checkpoint, CS-H.9 records membership request UX hardening, and CS-H.10 records the CMS hardening checkpoint.

DOCS-AS.1 records the shared audience-scope direction. `ChurchStructureUnit` is the shared flexible structure foundation for future audience selection. App modules should use app-specific join models to `ChurchStructureUnit` rather than adding more legacy-only multi-select scope fields. Bible Study Schedule audience scope is implemented (BS-AS.1, with BS-AS.2 picker/display/cancelled-cleanup and BS-AS.2A accessibility polish): current normal V2 generation expands `BibleStudySeriesAudienceScope` selected units to active descendant/self `UNIT_SMALL_GROUP` `ChurchStructureUnit` leaf targets. Since CS-CORE.2C-B and BS-STRUCT.2A, Bible Study v2 `BibleStudyMeeting` ordinary-member visibility and the `/studies/` / Today meeting pre-filter use audience rows plus active primary `ChurchStructureMembership`; `Profile.small_group` alone no longer grants v2 meeting visibility. ServiceEvent / Church Gatherings follows the same `ChurchStructureUnit` audience-scope foundation as a runtime consumer: SE-AS.4 made `ServiceEventAudienceScope` rows the ordinary-user visibility source when an event has them, SE-AS.5 added the staff audience picker, CS-CORE.2B-A switched audience-row matching to active primary `ChurchStructureMembership`, and SE-RETIRE.1B retired the zero-row legacy fallback so zero-row events now fail closed for ordinary users. Future Community Activities should reuse the same foundation in a later milestone and remains deferred and separately approved. This is not full legacy object/table retirement: remaining `SmallGroup` / `District` / `MinistryContext` rows and mapping FKs are bridge/admin/diagnostic/setup/table-retirement context, not normal V2 generation authority.

The current short-term bridge served pilot needs:
- `MinistryContext`
- `District`
- `SmallGroup`
- `Profile.small_group`
- `District.ministry_context`
- `BibleStudySeries.ministry_context` schedule scope
- optional `ServiceEvent.ministry_context` label

Pilot validation passed on `v0.9-pilot-rc1`, and these current structures are acceptable for the pilot baseline. This document remains the planning record for flexible hierarchy and audience scope. Some foundation and one narrow Bible Study audience-scope consumer are now implemented, but this document still does not authorize additional model, migration, view, form, template, filtering, permission, or consumer-migration changes without a separate approved milestone.

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

Historical/superseded: `Profile.small_group` stored the user's current primary small group before PROFILE-SG-FIELD-RETIRE.1A removed the field.

Current state: active primary `ChurchStructureMembership` is the ordinary-member belonging source for migrated consumers. Bible Study V2 ordinary visibility uses meeting audience rows plus membership, and normal V2 generation targets active small-group `ChurchStructureUnit` leaves rather than legacy `SmallGroup` rows. ServiceEvent visibility uses audience rows plus membership, and zero-row events fail closed for ordinary users. The legacy ServiceEvent scope fields and `ServiceEvent.ministry_context` were removed in later field-retirement slices.

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

Historical note: this early design expected the `BibleStudySeries` eligible-small-groups helper to prefer `BibleStudySeriesAudienceScope` rows and resolve selected units to legacy `SmallGroup` rows, with legacy scope-field fallback when no audience rows existed. That bridge wording is superseded: current normal V2 generation fails closed with zero schedule audience rows and expands selected audience units directly to active small-group `ChurchStructureUnit` leaf targets.

### `ServiceEvent` Scope Fields

`ServiceEvent` remains the official church gathering and operations anchor.

Current scope fields:
- `scope_type`
- `district`
- `small_group`
- `ministry_context`

These legacy fields are stored/admin/display/audit data while field-level retirement remains separate: SE-AS.4 made `ServiceEventAudienceScope` rows the ordinary-user visibility source when an event has them (supporting multiple `ChurchStructureUnit` targets), CS-CORE.2B-A switched those rows to active primary `ChurchStructureMembership`, and SE-RETIRE.1B made zero-row events fail closed for ordinary users. SE-AS.5 adds the staff picker that writes audience rows. The legacy fields below remain editable compatibility fields:
- whole church
- one district
- one small group

`ServiceEvent.ministry_context` is label-only. It must not drive audience filtering, My Serving visibility, TeamAssignment visibility, or MinistryTeam behavior in the current baseline.

### `TeamAssignment` and `MinistryTeam` Boundaries

`MinistryTeam` represents serving or operations teams, such as Lighting, Audio, Video, Projection, or other service teams.

`TeamAssignment` links a `ServiceEvent` to a `MinistryTeam` and assigned `TeamMembership` records. Serving assignments are manual operational assignments. Audience scope should not automatically assign serving members.

### `BibleStudyMeeting` and `BibleStudyMeetingRole` Boundaries

`BibleStudyMeeting` is anchored to a `BibleStudyLesson`, `generation_key`, `anchor_unit`, and meeting audience rows. The legacy `BibleStudyMeeting.small_group` FK was removed in BS-MEETING-MIRROR.1A. Since BS-STRUCT.2A, normal user visibility is tied to the user's single active primary `ChurchStructureMembership` matching a `BibleStudyMeetingAudienceScope` unit or descendant; `Profile.small_group` alone no longer grants v2 meeting visibility.

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

The shared design uses a tree that can represent variable depth and a selection model that can store more than one selected audience branch.

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
- At the CS-H.2 stage, existing `MinistryContext`, `District`, `SmallGroup`, and `Profile.small_group` remained the source of current behavior.
- At the CS-H.2 stage, no audience selection or filtering used ChurchStructureUnit yet. Later, BS-AS.1 / BS-AS.2 / BS-AS.2A implemented Bible Study Schedule audience selection while still resolving generation to legacy `SmallGroup`; CS-CORE.2C-B later switched Bible Study v2 meeting ordinary visibility to active primary `ChurchStructureMembership`.
- One active Whole Church root is the intended future system shape, but root uniqueness enforcement is deferred until root seeding/mapping policy is decided.

CS-H.3 strategy note:
- Long-term source of truth should be `ChurchStructureUnit` for structure and `ChurchStructureMembership` for belonging.
- At the CS-H.3 stage, short-term runtime behavior continued to use `MinistryContext`, `District`, `SmallGroup`, and `Profile.small_group`.
- CS-H.3B added nullable mapping fields from `MinistryContext`, `District`, and `SmallGroup` to `ChurchStructureUnit`; at that time they did not drive current behavior.
- CS-H.3C adds `seed_church_structure_units` with dry-run/apply modes to seed a `CHURCH` root, mirror current structure units, and fill legacy mapping fields. It does not auto-run and still does not make `ChurchStructureUnit` drive runtime behavior.
- CS-H.3D verifies the GoDaddy apply and clean second dry-run.
- CS-H.3E records that the `Santa Clara 3` legacy data issue was handled and the seeded structure data QA item is closed, as long as final dry-run remains clean.
- CS-H.4 designs `ChurchStructureMembership` and requested-unit approval flow.
- CS-H.5A adds `ChurchStructureMembership` model/admin/tests only. It does not add signup flow, approval UI, backfill, audience selection, filtering, or consumer migration.
- CS-H.5B adds helper/query hardening only. Requested, rejected, cancelled, and ended memberships still do not grant visibility.
- CS-H.5C adds `backfill_church_structure_memberships` for explicit dry-run/apply membership backfill from mapped `Profile.small_group` values. It does not modify `Profile.small_group`, add signup or approval UI, add audience selection or filtering, or migrate any runtime consumer.
- CS-H.5D records production/staging backfill verification as user-attested. Exact command-output counts were not recorded. At CS-H.5D time, no runtime source-of-truth switch was authorized.
- CS-H.5E improves Django Admin clarity only. Historical/superseded: at CS-H.5E time, legacy `MinistryContext`, `District`, `SmallGroup`, and `Profile.small_group` remained current runtime source during transition and could not be deleted yet.
- CS-H.6/CS-H.6B/CS-H.6D add requested-unit capture from signup and Profile for staff review, not direct final self-assignment.
- CS-H.7B/C/D/E add staff request review, approve/reject actions, and narrow `Profile.small_group` approval sync.
- CS-H.8 verified the integrated signup/Profile/staff approval flow. CS-H.9 membership request UX hardening is complete. CS-H.10 records the CMS hardening checkpoint, including deferred/accepted mobile nav polish and the root `AGENTS.md` verification policy.
- Runtime consumers remain split by consumer. Current switched consumers use active primary `ChurchStructureMembership` or structure snapshots for ServiceEvent audience rows, Bible Study v2 audience rows / `/studies/` / Today / role-worship pickers, Prayer group requests, group-progress roster/default/ordinary own-group access, and reflection read/write paths. Legacy V1 `BibleStudySession`, TeamAssignment/My Serving, staff capabilities, role assignments, and legacy fields/tables remain separate; requested memberships still grant nothing.
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
- Historical/superseded: `Profile.small_group` was the legacy/admin/archive/audit/backfill/support primary-small-group field during transition. It was removed in PROFILE-SG-FIELD-RETIRE.1A; current belonging is active primary `ChurchStructureMembership` for migrated consumers.
- Future membership history should support movement over time.
- Current visibility can continue using current active membership until historical rules are explicitly needed.
- Do not import sensitive/private data.
- Do not import phone/private contact data.
- Do not overbuild an HR/personnel system.
- Notes must be non-sensitive and operational only.

Membership should be planned separately from hierarchy. A structure unit can exist without immediately importing full membership history.

CS-H.4 design note:
- `ChurchStructureMembership` should become the eventual belonging source.
- At CS-H.4 design time, `Profile.small_group` remained the runtime source during transition.
- Requested membership must not grant visibility.
- Only approved active membership may be considered by future consumers after explicit migration and tests.
- CS-H.5A model-only foundation existed while current runtime still used `Profile.small_group`.
- CS-H.5B query helpers were available for future phases, but no consumer used them at that time.
- CS-H.5C backfill command exists and CS-H.5D production/staging verification is recorded by user confirmation; at that time no current consumer used membership yet. Current state is different: membership is now used by the explicitly switched consumers listed above, while requested memberships still grant nothing.
- CS-H.5E admin clarity exists to reduce staff confusion.
- CS-H.6/CS-H.6B/CS-H.6D requested-unit capture and CS-H.7B/C/D/E staff approval/sync slices exist, but consumer migration remains future.
- See `docs/CHURCH_STRUCTURE_MEMBERSHIP_DESIGN.md`.

## 6. Audience Selection Model

Future audience selection should store selected `ChurchStructureUnit` rows for a target object.

Possible generic name:

`AudienceSegment`

Possible app-specific through models:

- `BibleStudySeriesAudienceScope` — implemented for Bible Study Schedule.
- `ServiceEventAudienceScope` — implemented for ServiceEvent; SE-AS.4 uses its rows as the ordinary-user visibility source when an event has them, CS-CORE.2B-A matches those rows through active primary `ChurchStructureMembership`, and SE-RETIRE.1B makes zero-row events fail closed for ordinary users. SE-AS.5 adds the staff picker.
- `CommunityActivityAudienceScope` — future suggested direction for Community Activities if/when that module is approved.


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

Audience selection should avoid saving redundant ancestor/descendant combinations.

Current and future module UI should follow these rules unless a later approved milestone explicitly designs a different mode:

- Root = Whole Church / 全教会.
- If Whole Church is selected, lower-level selections should be cleared or disabled.
- Selecting a parent unit should clear selected descendants under that parent.
- Selecting a child or descendant should clear selected ancestors for that branch.
- Sibling units may be selected together.
- Cross-branch units may be selected together.
- The backend remains the source of truth and should reject or normalize redundant ancestor/descendant combinations if they are submitted through import, stale UI, or non-browser clients.
- The final UI should show a readable audience preview.

Examples of valid saved selections:

- Whole Church.
- CM.
- CM + EM.
- CM > District A.
- CM > District A > Rainbow 1 and CM > District A > Rainbow 2.
- CM > District A + EM > District C > Group 3.

Examples of redundant selections that should not be saved together:

- Whole Church + CM.
- CM + CM > District A.
- CM > District A + CM > District A > Rainbow 1.

Narrowing a branch should be represented by replacing the broader parent selection with the narrower child/descendant selection, not by saving both parent and child.

If a future workflow truly needs “include parent and child separately” or include/exclude behavior, that should be a later explicitly approved mode with its own UI, validation, and tests.


## 8. Effective Audience Calculation

Conceptual algorithm:

- Input: selected tree nodes.
- Output: normalized effective target nodes.
- If root is selected, output root only.
- Remove duplicate nodes.
- Do not keep ancestor and descendant selections together in the normalized result.
- If a redundant ancestor/descendant combination is submitted anyway, normalize or reject it according to the owning module's validation policy.
- Exclude inactive units from the selectable UI.
- Preserve historical display of old selections if a unit later becomes inactive.

Current implemented Bible Study behavior:

- BS-AS.1 / BS-AS.2 / BS-AS.2A avoid saving ancestor/descendant combinations.
- The picker convenience behavior clears root/ancestor/descendant conflicts.
- Backend validation remains the source of truth.
- Selected `ChurchStructureUnit` rows now expand to active descendant/self `UNIT_SMALL_GROUP` `ChurchStructureUnit` leaf targets for normal V2 meeting generation.
- Ordinary member visibility uses `BibleStudyMeetingAudienceScope` rows plus active primary `ChurchStructureMembership`; generation no longer resolves selected units to eligible legacy `SmallGroup` rows.

Broader ServiceEvent and Community Activities runtime filtering remain future work and require separate approval.

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
- CS-H.3D completed production/staging seeding verification. At that time, runtime behavior still used `MinistryContext`, `District`, `SmallGroup`, and `Profile.small_group`.
- CS-H.3E completed seeded structure data QA closure. At that time, runtime behavior still used `MinistryContext`, `District`, `SmallGroup`, and `Profile.small_group`.
- CS-H.4 completed membership design. At that time, runtime behavior still used `MinistryContext`, `District`, `SmallGroup`, and `Profile.small_group`.
- CS-H.5A completed membership model-only foundation. At that time, runtime behavior still used `MinistryContext`, `District`, `SmallGroup`, and `Profile.small_group`.
- CS-H.5B completed membership helper/validation hardening. At that time, runtime behavior still used `MinistryContext`, `District`, `SmallGroup`, and `Profile.small_group`.
- CS-H.5C completed the explicit membership backfill command.
- CS-H.5D completed production/staging backfill verification by user-attested GoDaddy run; exact output counts were not recorded. At that time, runtime behavior still used `MinistryContext`, `District`, `SmallGroup`, and `Profile.small_group`.
- CS-H.5E completed Django Admin clarity for legacy structure versus future structure/membership foundation. At that time, runtime behavior still used `MinistryContext`, `District`, `SmallGroup`, and `Profile.small_group`.
- CS-H.6/CS-H.6B/CS-H.6D completed signup/Profile requested-unit capture. Request submission does not update `Profile.small_group`.
- CS-H.7B/C/D/E completed staff request review, approve/reject actions, and narrow approval sync to `Profile.small_group`.
- CS-H.8 integration checkpoint completed. At that time, runtime consumers still used legacy structure models and `Profile.small_group`; current switched consumers are listed above.
- CS-H.9 membership request UX hardening completed.
- CS-H.10 CMS hardening checkpoint completed. Mobile nav polish remains deferred/accepted for now, and root `AGENTS.md` verification policy has been added.

### First Audience Consumer (Implemented: BS-AS.1 / BS-AS.2 / BS-AS.2A)

- DOCS-AS.1 decision, now implemented: Bible Study Schedule is the first narrow runtime consumer for `ChurchStructureUnit` audience selection.
- Bible Study Schedule was first because selected structure units originally resolved to legacy `SmallGroup` rows for generation. Historical/superseded: that bridge was retired; current normal V2 generation expands selected units directly to active small-group structure-unit leaves, and v2 `BibleStudyMeeting` member visibility uses meeting audience rows plus active primary `ChurchStructureMembership`.
- Implemented with the app-specific join model `BibleStudySeriesAudienceScope` selecting `ChurchStructureUnit` rows; no legacy-only multi-select scope fields were added.
- BS-AS.2 added a reusable searchable/tree audience picker (with no-JS fallback and backend validation as source of truth), compact list/card and wrapped/chip detail scope display with the root prefix omitted, and active-list cancelled cleanup; meeting generation still treats cancelled meetings as existing/skipped. BS-AS.2A added picker accessibility polish.
- Behavior stays narrow: no broad audience filtering, and the legacy fixed fields remain available as compatibility/fallback during coexistence.

### Later Phase: ServiceEvent and Community Activities Audience Scope

- ServiceEvent / Church Gatherings now uses the same `ChurchStructureUnit` audience-scope foundation as a runtime consumer (SE-AS.4 visibility rule, SE-AS.5 staff picker); future Community Activities should follow the same foundation in a later milestone.
- `ServiceEventAudienceScope` (SE-AS.2 model foundation) now drives ordinary-user ServiceEvent visibility when an event has rows (SE-AS.4), matched through active primary `ChurchStructureMembership` after CS-CORE.2B-A. Events with no rows fail closed for ordinary users after SE-RETIRE.1B; legacy scope fields remain editable stored/admin/display/audit data until field-level retirement.
- Future Community Activities should use a `ChurchStructureUnit`-based audience-scope design rather than inventing a separate legacy-only audience segment system.
- Preserve safe `BibleStudyMeeting` visibility.
- Avoid breaking generated meeting workflows.

### Later Phase: Deprecation Consideration

- Consider deprecating old fixed fields only after safe migration, tested data reconciliation, and clear rollback strategy.
- No hard cutover.
- Avoid breaking the pilot baseline.

## 11. Module Impact

### A. Bible Study

Under DOCS-AS.1, Bible Study Schedule is the first narrow `ChurchStructureUnit` audience-scope runtime consumer, implemented (BS-AS.1 / BS-AS.2 / BS-AS.2A) via the app-specific join model `BibleStudySeriesAudienceScope`. Historical/superseded: selected `ChurchStructureUnit` rows originally resolved to eligible legacy `SmallGroup` rows for meeting generation, generated `BibleStudyMeeting` rows pointed to legacy `SmallGroup`, and legacy `BibleStudySeries` scope fields provided compatibility/fallback when a schedule had no audience-scope rows. Current normal V2 generation fails closed with zero schedule audience rows and expands selected units directly to active small-group `ChurchStructureUnit` leaf targets; `BibleStudySeries` legacy scope fields and `BibleStudyMeeting.small_group` were removed in later slices.

Future audience selection may support richer schedules, but `BibleStudyMeeting` visibility must remain safe. Current ordinary member visibility uses active primary `ChurchStructureMembership` matched to meeting audience rows; normal users should not gain cross-small-group visibility because of a structure migration.

### B. ServiceEvent

Current `ServiceEvent.ministry_context` remains label-only.

ServiceEvent audience selection is now implemented: `ServiceEventAudienceScope` rows are the ordinary-user visibility source when an event has them (SE-AS.4), the staff picker writes them (SE-AS.5), and SE-FIELD-RETIRE.1A later removed the legacy `scope_type` / `district` / `small_group` fields. Zero-row events now fail closed for ordinary users.

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

The original CS-H.1 planning milestone did not include:
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
- BS-AS.1 Bible Study Schedule audience scope using `ChurchStructureUnit`. Completed.
- BS-AS.2 audience picker UX, compact scope display, and active-list cancelled cleanup. Completed.
- BS-AS.2A audience picker accessibility polish. Completed.
- Immediate next step: manual/browser QA of the BS-AS flow after deployment or local migration, using `docs/BIBLE_STUDY_V2_FLOW_QA_CHECKLIST.md`.
- ServiceEvent / Church Gatherings staff audience UI and runtime audience visibility are now implemented (SE-AS.5 selector, SE-AS.4 visibility rule, with audience-row matching switched to active primary `ChurchStructureMembership` in CS-CORE.2B-A). SE-AS.6 backfill/compatibility cleanup (SE-AS.6A planning and SE-AS.6B dry-run audit command complete; SE-AS.6C apply future) and additional consumer/visibility migrations remain deferred and require separate approval.
- Later Community Activities V1 planning refinement using the shared `ChurchStructureUnit` audience-scope foundation through its own app-specific join model. Deferred and requires separate approval.
- Later Checklist V1 re-evaluation only if pilot feedback proves a checklist need separately from required-team coverage.
- PP-SA.1 Staff Admin Surface Expansion Plan. Completed.

## 15. Decision Checklist

Open decisions:
- Generic audience model vs app-specific through models.
- Whether root is persisted or virtual.
- Whether old `MinistryContext`, `District`, and `SmallGroup` remain source of truth long-term.
- First narrow runtime consumer (DOCS-AS.1 decision, implemented as BS-AS.1 / BS-AS.2 / BS-AS.2A): Bible Study Schedule (`BibleStudySeries`) audience scope via `BibleStudySeriesAudienceScope`, resolving selected `ChurchStructureUnit` rows to legacy `SmallGroup` for generation. Since CS-CORE.2C-B, v2 meeting member visibility uses active primary `ChurchStructureMembership`. ServiceEvent now follows the same foundation as a runtime consumer (SE-AS.4 / SE-AS.5); Community Activities follows the same foundation later and remains deferred.
- How to expose structure admin UI.
- How much membership history is needed.
- Whether selection rows should store display snapshots for historical labels.
- Whether include/exclude is needed later or include-only is enough.
- How to handle moved or merged units in historical reports.

Current recommendation:

- Continue to prefer app-specific through models first.
- Continue to prefer include-only V1 unless real use proves exclusion is necessary.
- Continue to avoid destructive migration.
- Bible Study Schedule has now proven the first narrow runtime consumer through BS-AS.1 / BS-AS.2 / BS-AS.2A.
- ServiceEvent / Church Gatherings now reuses the shared foundation as a runtime consumer (SE-AS.4 / SE-AS.5); Community Activities should reuse the same shared foundation later and remains deferred and requires separate approval.
- Preserve the validated pilot baseline and keep consumer migrations explicit: Bible Study v2 meeting visibility switched in CS-CORE.2C-B, while legacy `BibleStudySession`, reading progress, ServiceEvent legacy fallback, My Serving, and other legacy consumers remain unchanged unless separately approved.
