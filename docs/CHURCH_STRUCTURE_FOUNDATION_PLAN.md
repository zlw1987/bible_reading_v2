# Church Structure Foundation Plan

## 1. Purpose

Church Structure Foundation began as a future foundational module for representing
the church's people and organizational structure.

Current-state update: the flexible foundation is now implemented for the current
codebase. `ChurchStructureUnit` is the canonical local structure model, active
primary `ChurchStructureMembership` is the canonical local belonging source for
migrated consumers, and the legacy `Profile.small_group`, `SmallGroup`,
`District`, `MinistryContext`, `SmallGroup.district`, and
`District.ministry_context` runtime/schema surfaces are removed. Historical
sections below that mention those legacy objects describe the bridge period and
must not be read as current schema/runtime guidance.

It should support, through separately approved consumers:
- Bible Study schedule scope and meeting generation.
- Community Activities audience visibility and signup eligibility.
- ServiceEvent visibility/context through `ServiceEventAudienceScope` and
  `host_language_unit`.
- User profile scoping and membership context.

The project remains a lightweight church spiritual life and ministry workflow system, not a full church ERP.

Church Structure Foundation is not:
- `MinistryTeam`
- `TeamAssignment`
- `ServiceEvent`
- `CommunityActivity`
- `BibleStudyMeeting`
- a full ERP org chart

This began as a future planning artifact. CS-F.1 implemented the short-term
`MinistryContext` bridge, CS-F.2 used that bridge only for Bible Study Schedule
scope eligibility, and CS-F.3 added optional `ServiceEvent.ministry_context`
labeling only. Those bridge surfaces are now historical/superseded. Later CS-H
and CS-CORE slices implemented `ChurchStructureUnit`, `ChurchStructureMembership`,
structure audience rows, migrated approved consumers, and retired the legacy
structure fields/tables. Do not implement additional models, views, templates,
permissions, audience selection, filtering, signup changes, custom staff admin UI,
or runtime behavior changes from this document without a separate implementation
task.

## 2. Current Reality

Known church structure:
- CM = Chinese Ministry.
- EM = English Ministry.
- CM has districts such as District 1 / 第一区 and District 2 / 第二区.
- Districts contain fellowship small groups.
- Example fellowship small groups include Rainbow 1 and Rainbow 4.
- Current migrated belonging is active primary `ChurchStructureMembership`;
  historical planning assumed a person belonged to one fellowship small group at a
  time.
- Friday Bible Study uses fellowship small group as the smallest unit.

Example structure:

```text
Church
-> CM
   -> District 1
      -> Rainbow 1
      -> Rainbow 4
   -> District 2
-> EM
   -> EM Group A
   -> EM Group B
```

This example should not become a permanent hard-coded schema assumption. Future church structures may need more or fewer levels, and different branches may need different depth.

## 3. Historical Code Reality

Historical/superseded code assumptions from the bridge period:
- `District` existed.
- `SmallGroup` existed.
- `Profile.small_group` existed.
- CS-F.1 added `MinistryContext` and nullable `District.ministry_context` as the short-term bridge.
- CS-H.2 adds `ChurchStructureUnit` as a model-only flexible tree foundation.
- CS-H.2A adds indirect cycle validation and safe ancestor/path display for corrupted tree states.
- CS-H.3 recorded that long-term source of truth should be `ChurchStructureUnit` for structure and `ChurchStructureMembership` for belonging; current state uses those models for the approved migrated consumers.
- CS-H.3B added nullable `church_structure_unit` mapping fields on `MinistryContext`, `District`, and `SmallGroup`; those legacy tables and bridge FKs were later removed.
- CS-H.3C added `seed_church_structure_units` to explicitly seed/map then-current `MinistryContext`, `District`, and `SmallGroup` rows into `ChurchStructureUnit`.
- CS-H.3D verifies GoDaddy production/staging seeding: 35 units created, 33 legacy records linked, and the second dry-run reported no pending create/update/link work.
- CS-H.3E records that the `Santa Clara 3` legacy data issue was corrected or otherwise handled and the seeded structure data QA item is closed, provided final dry-run remains clean.
- CS-H.4 designs `ChurchStructureMembership`, requested-unit approval, backfill, and visibility migration strategy without implementation.
- CS-H.5A adds `ChurchStructureMembership` as a model-only foundation with admin registration and tests.
- CS-H.5B adds active/date-window membership helpers and validation tests.
- CS-H.5C adds `backfill_church_structure_memberships`, an explicit dry-run/apply command that can create active primary memberships from mapped `Profile.small_group` values.
- CS-H.5D records production/staging backfill verification as user-attested. Exact command-output counts were not recorded.
- CS-H.5E improves Django Admin clarity so legacy current-runtime models and future foundation models are clearly distinguished.
- There is no automatic `ChurchStructureUnit` data seeding through migrations or app startup.
- Historical/superseded: at this stage there was no automatic membership backfill, signup/onboarding approval flow, or membership-driven visibility yet.
- Historical/superseded: Bible Study schedule scope used legacy whole church / ministry context / district / small group fields at this stage. Current Bible Study schedule audience uses `BibleStudySeriesAudienceScope` rows, normal V2 generation is structure-unit-native, and meeting visibility uses `BibleStudyMeetingAudienceScope` plus active primary membership.
- Current Community Activities planning expects future audience segments.

## 4. Historical Short-Term Model Direction

Historical/superseded: CS-F.1 implemented the practical near-term bridge before a flexible hierarchy was justified:

`MinistryContext`
- CM
- EM

Historical relationships:
- `District` belonged to `MinistryContext`.
- `SmallGroup` belonged to `District`.
- User belonged to the then-current `SmallGroup` through `Profile.small_group`.

This fit the then-current Bible Study V2 scope and near-term Community Activities planning with minimal migration risk.

This was not the final flexible hierarchy model. Current structure is `ChurchStructureUnit`.

## 5. Long-Term Flexible Hierarchy Direction

Historical/superseded: future planning was expected to introduce a flexible tree
model. Current structure uses `ChurchStructureUnit`.

Suggested concept:

`ChurchStructureUnit`
- `id`
- `parent` nullable
- `unit_type`
- `code`
- `name`
- `name_en`
- `description`
- `description_en`
- `is_active`
- `sort_order`

Possible `unit_type` values:
- `church`
- `ministry_context`
- `district`
- `fellowship_group`
- `small_group`
- `class`
- `department`
- `custom`

Rules:
- `unit_type` should allow known system types plus future custom types.
- `parent` creates the tree hierarchy.
- A unit cannot be its own parent or ancestor.
- Ancestor/path helpers should not hang if corrupted data contains a cycle.
- Different branches can have different depths.
- CM and EM do not need identical depth.
- Do not create a fake Combined Ministry.
- Combined events or activities should reference multiple units or audience segments.
- One active Whole Church root is intended, but database enforcement is deferred until root seeding and mapping policy are decided.

## 6. Membership Direction

Membership should be planned separately from structure.

Suggested concept:

`ChurchStructureMembership`
- `user`
- `unit`
- `role` optional
- `start_date`
- `end_date`
- `is_active`
- `note` optional

Rules:
- Historical/superseded: at this planning stage, the user's then-current small group could remain on `Profile.small_group` in the near term. Current belonging for migrated consumers is active primary `ChurchStructureMembership`, and `Profile.small_group` was removed.
- Future membership history can be added later.
- Current migrated belonging source is `ChurchStructureMembership`; richer membership history remains future planning.
- Requested signup/onboarding units should require staff approval before becoming active membership.
- CS-H.4 recommends keeping requested membership separate from visibility; only approved active membership should count for future consumers.
- Historical/superseded: CS-H.5A added the membership table only while runtime behavior still used `Profile.small_group`.
- CS-H.5B query helpers count only active memberships within their date window; requested, rejected, cancelled, and ended memberships are excluded.
- Historical/superseded: CS-H.5C added a command to backfill active primary memberships from existing `Profile.small_group` values where the small group was mapped to `ChurchStructureUnit`; it did not change `Profile.small_group` or switch runtime consumers in that slice.
- CS-H.5D records production/staging backfill verification by user confirmation; membership still does not drive runtime visibility.
- CS-H.5E improves admin clarity only. Historical/superseded: at that point legacy `SmallGroup`, `District`, `MinistryContext`, and `Profile.small_group` remained current runtime source during transition. Current migrated runtime uses structure units / memberships where separately switched, and `Profile.small_group` has been removed.
- Do not import phone/private/sensitive data.
- Do not do full historical import in the first version.

## 7. Relationship to Existing SmallGroup

### Option A - Historical: Keep District and SmallGroup Canonical

Historical/superseded option: keep existing `SmallGroup` and `District` as canonical for the bridge period. Add `MinistryContext` first if CM/EM scoping becomes necessary. Later add flexible `ChurchStructureUnit` only when proven needed.

Pros:
- Lower migration risk.
- Fits current Bible Study V2 scope.
- Preserved `Profile.small_group` during the bridge period.
- Avoids broad data conversion before real product need is proven.

Cons:
- Less flexible for variable-depth structures.
- Future mixed structures may need additional mapping.

### Option B - Add ChurchStructureUnit and Map Existing Structure

Add `ChurchStructureUnit` and gradually map `District` and `SmallGroup` into it.

Pros:
- Higher long-term flexibility.
- Better fit for branches with different depth.
- Can support future groups, ministries, classes, and fellowships without another schema redesign.

Cons:
- More migration complexity.
- Higher risk of duplicate sources of truth.
- Requires careful reporting and historical membership planning.

### Recommendation

Historical/superseded: do not switch then-current behavior to the flexible tree immediately.

Short term:
- Historical/superseded: keep `District` and `SmallGroup`.
- Historical/superseded: keep `MinistryContext` as the bridge for CM/EM.
- Historical/superseded: keep `Profile.small_group` as the current primary-small-group field.
- Keep `ChurchStructureUnit` mapping fields optional and non-runtime during seeding/mapping.
- Keep signup/onboarding assignment approval separate from final membership.

Long term:
- Historical/superseded: map then-current structure into `ChurchStructureUnit`
  only after Bible Study V2 and Community Activities needs prove the need.
- Move belonging to `ChurchStructureMembership` only after model design, approval workflow, and visibility tests.
- Avoid destructive migration.

## 8. Relationship to Bible Study

Bible Study V2 near-term uses `BibleStudySeries` scope:
- whole church
- ministry context
- district
- small group

Historical note: early schedule generation used the `MinistryContext` -> `District` -> `SmallGroup` bridge through the `BibleStudySeries` eligible-small-groups helper. Current normal V2 generation is structure-native from `BibleStudySeriesAudienceScope` rows to active small-group `ChurchStructureUnit` leaf targets.

Current Bible Study schedule scope uses `BibleStudySeriesAudienceScope` rows to
`ChurchStructureUnit`; normal V2 meeting generation and visibility are
structure-native through audience rows, `generation_key`, `anchor_unit`, and
active primary membership.

A Bible Study schedule can target, through structure audience rows:
- whole church
- CM
- EM
- district
- group
- custom unit

Generation should create meetings for eligible fellowship or small-group leaf units.

Do not implement this now.

## 9. Relationship to Community Activities

Community Activities should eventually use audience segments.

Future audience segments can target:
- whole church
- ministry context
- district
- small group
- arbitrary `ChurchStructureUnit`

Examples:
- entire EM plus CM District 1
- CM Rainbow 1 and Rainbow 4
- EM plus several CM small groups

Do not implement this now.

## 10. Relationship to ServiceEvent / Ministry Operations

`ServiceEvent` is the official church event and operations anchor.

`MinistryTeam` is a serving team, such as Lighting, Audio, Video, or Projection.

`ChurchStructureUnit` is people, audience, and organizational structure.

Important boundaries:
- `MinistryTeam` should not be replaced by `ChurchStructureUnit`.
- Small group coworker roles are not `MinistryTeam`.
- `TeamAssignment` remains for ministry serving assignments.
- `BibleStudyMeetingRole` remains for one-meeting Bible Study responsibilities.
- `CommunityActivity` remains for signup-oriented activities.

Historical/superseded: CS-F.3 added optional `ServiceEvent.ministry_context`
labeling only. It was metadata for identifying the ministry context of an
official church service/event anchor and did not drive audience filtering,
`TeamAssignment` visibility, My Serving visibility, or MinistryTeam behavior.
Current Host / Language display uses `ServiceEvent.host_language_unit` plus the
audience-derived structure fallback.

Historical/superseded: CS-F.3B clarified the then-current UI wording for the
removed label field. Flexible hierarchy and multi-select ServiceEvent audience
scope are no longer future work for the current codebase: ServiceEvent visibility
uses `ServiceEventAudienceScope` rows plus active primary membership, and zero-row
events fail closed for ordinary users.

Historical/superseded: CS-F.3C clarified the limited then-current ServiceEvent
scope UI where Audience Scope supported Whole Church, one District, or one Small
Group. Current ServiceEvent audience selection is row-based through
`ServiceEventAudienceScope`; the legacy fixed scope fields were removed.

Current `ServiceEvent` audience references structure units through
`ServiceEventAudienceScope`; `MinistryContext` records are removed.

## 11. Flexible Hierarchy Rules

Rules:
- Structure can have variable depth.
- Nodes can be active or inactive.
- Inactive nodes should not be selected for new scopes unless explicitly shown for history.
- Moving a group between parents should be planned carefully because it affects historical reporting.
- Current membership and historical membership should be separate.
- Visibility checks should use active/current structure only unless history is needed.
- Mixed-scope events and activities should reference multiple units or audience segments rather than inventing a fake Combined Ministry node.

## 12. Non-Goals

Do not build:
- immediate code implementation
- destructive migration
- full church ERP
- automatic scheduling
- availability matrix
- swap requests
- reminders
- sensitive/private data import
- full historical import
- replacing `MinistryTeam`
- replacing `TeamAssignment`
- replacing `BibleStudyMeeting`
- replacing `CommunityActivity`
- fake Combined Ministry record

## 13. Roadmap Placement

Historical roadmap placement for the foundation step:
- Bible Study V2 Flow QA has passed
- CS-F.1 implemented the short-term `MinistryContext` bridge
- CS-F.2 added `MinistryContext` as a Bible Study Schedule scope
- CS-F.3 added optional `ServiceEvent.ministry_context` labeling only
- CS-H.2 adds model-only `ChurchStructureUnit` foundation with no seeding, no mapping, no audience selection, and no filtering
- CS-H.2A hardens `ChurchStructureUnit` cycle validation without adding seeding, mapping, audience selection, or filtering
- CS-H.3 records mapping, membership, and signup/onboarding approval strategy without implementation
- CS-H.3B adds nullable legacy mapping fields without seeding, runtime behavior changes, membership, audience selection, or filtering
- CS-H.3C adds an idempotent management command for explicit seeding/mapping, with no runtime behavior changes, membership, audience selection, or filtering
- CS-H.3D verifies production/staging command execution and idempotency, with no runtime behavior changes, membership, audience selection, or filtering
- CS-H.3E closes seeded structure data QA, with no runtime behavior changes, membership, audience selection, or filtering
- CS-H.4 designs membership and requested-unit approval, with no model, signup, admin UI, consumer migration, or runtime behavior changes
- CS-H.5A adds membership model-only foundation, with no signup, admin approval UI, backfill, consumer migration, or runtime behavior changes
- CS-H.5B hardens membership helpers/validation, with no signup, backfill, consumer migration, or runtime behavior changes
- CS-H.5C adds an explicit membership backfill command, with no signup, admin approval UI, consumer migration, or runtime behavior changes
- CS-H.5D records production/staging backfill verification by user-attested GoDaddy run, with no runtime behavior changes
- CS-H.5E improves Django Admin clarity, with no custom staff admin UI, consumer migration, or runtime behavior changes
- before or alongside Community Activities implementation planning
- before implementing advanced mixed audience segments
- before implementing CM/EM-aware `ServiceEvent` filtering

Historical/superseded: at this roadmap point, signup approval, audience selection,
Community Activities, Checklist V1, and role-aware Bible Study editing permissions
remained deferred until separately chosen, and runtime behavior still used legacy
structure models plus `Profile.small_group`. Current approved runtime consumers
now use the structure-native sources documented above, while Community Activities,
Checklist V1, and broader role-aware editing remain separately approved future work.

CS-MAP (`docs/CHURCH_STRUCTURE_MAP_AND_SETUP_READINESS_PLAN.md`) is the staff-facing visibility/setup-readiness layer over this foundation: CS-MAP.1 is the completed docs-only plan, CS-MAP.2 proposes a read-only staff structure map with mapping-health indicators, CS-MAP.3 is an optional setup readiness checklist, and CS-SETUP.1 (limited setup/edit UI) is explicitly not approved. Django Admin remains the structure write surface during transition; CS-MAP work changes no schema or runtime behavior.

## 14. Deliverable Summary

This plan documents:
- flexible hierarchy through the model-only `ChurchStructureUnit` tree foundation
- historical short-term bridge using `MinistryContext`, `District`, `SmallGroup`, and `Profile.small_group`
- CS-H.3 long-term source-of-truth decision, now implemented for approved consumers: `ChurchStructureUnit` plus `ChurchStructureMembership`
- CS-H.3 signup/onboarding direction: requested unit plus staff approval, not direct self-assignment
- CS-H.3B nullable mapping fields from legacy structure models to `ChurchStructureUnit`
- CS-H.3C explicit `seed_church_structure_units` command for idempotent seeding/mapping
- CS-H.3D production/staging seeding verification closure
- CS-H.3E seeded structure data QA closure
- CS-H.4 `ChurchStructureMembership` design
- CS-H.5A `ChurchStructureMembership` model-only foundation
- CS-H.5B `ChurchStructureMembership` helper/validation hardening
- CS-H.5C `ChurchStructureMembership` backfill command
- CS-H.5D `ChurchStructureMembership` production/staging backfill verification
- CS-H.5E Django Admin clarity for legacy structure vs future structure/membership foundation
- no automatic `ChurchStructureUnit` data seeding or source-of-truth migration
- long-term variable-depth structure with separate membership history
- Bible Study relationship through historical schedule scope, including `MinistryContext`, and current structure-unit audience scope
- Community Activities relationship through future audience segments
- ServiceEvent and Ministry Operations boundaries
- roadmap placement after Bible Study V2 Flow QA and before advanced mixed audience work
