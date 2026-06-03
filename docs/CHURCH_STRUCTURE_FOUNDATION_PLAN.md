# Church Structure Foundation Plan

## 1. Purpose

Church Structure Foundation is a future foundational module for representing the church's people and organizational structure.

It should eventually support:
- Bible Study schedule scope and meeting generation.
- Community Activities audience visibility and signup eligibility.
- Future `ServiceEvent` visibility/context, if separately planned.
- User profile scoping and membership context.

The project remains a lightweight church spiritual life and ministry workflow system, not a full church ERP.

Church Structure Foundation is not:
- `MinistryTeam`
- `TeamAssignment`
- `ServiceEvent`
- `CommunityActivity`
- `BibleStudyMeeting`
- a full ERP org chart

This began as a future planning artifact. CS-F.1 implemented the short-term `MinistryContext` bridge, CS-F.2 uses that bridge only for Bible Study Schedule scope eligibility, CS-F.3 adds optional `ServiceEvent.ministry_context` labeling only, CS-H.2 adds a model-only `ChurchStructureUnit` foundation, CS-H.2A hardens tree validation, CS-H.3 records the mapping/membership/source-of-truth strategy, CS-H.3B adds nullable legacy-to-`ChurchStructureUnit` mapping fields, CS-H.3C adds an explicit dry-run/apply seeding command, and CS-H.3D records successful GoDaddy production/staging seeding verification. Do not implement additional models, views, templates, permissions, audience selection, filtering, signup changes, or runtime behavior changes from this document without a separate implementation task.

## 2. Current Reality

Known church structure:
- CM = Chinese Ministry.
- EM = English Ministry.
- CM has districts such as District 1 / 第一区 and District 2 / 第二区.
- Districts contain fellowship small groups.
- Example fellowship small groups include Rainbow 1 and Rainbow 4.
- A person currently belongs to one fellowship small group at a time, but membership may change over time.
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

## 3. Current Code Reality

Current code assumptions:
- `District` exists.
- `SmallGroup` exists.
- `Profile.small_group` exists.
- CS-F.1 adds `MinistryContext` and nullable `District.ministry_context` as the short-term bridge.
- CS-H.2 adds `ChurchStructureUnit` as a model-only flexible tree foundation.
- CS-H.2A adds indirect cycle validation and safe ancestor/path display for corrupted tree states.
- CS-H.3 records that long-term source of truth should be `ChurchStructureUnit` for structure and `ChurchStructureMembership` for belonging.
- CS-H.3B adds nullable `church_structure_unit` mapping fields on `MinistryContext`, `District`, and `SmallGroup`.
- CS-H.3C adds `seed_church_structure_units` to explicitly seed/map current `MinistryContext`, `District`, and `SmallGroup` rows into `ChurchStructureUnit`.
- CS-H.3D verifies GoDaddy production/staging seeding: 35 units created, 33 legacy records linked, and the second dry-run reported no pending create/update/link work.
- `Santa Clara 3` is under `UNASSIGNED-GROUPS` until the legacy `SmallGroup.district` business data decision is made.
- There is no automatic `ChurchStructureUnit` data seeding through migrations or app startup.
- There is no `ChurchStructureMembership` model yet.
- Current Bible Study schedule scope uses:
  - whole church
  - ministry context
  - district
  - small group
- Current Community Activities planning expects future audience segments.

## 4. Short-Term Model Direction

CS-F.1 implements the practical near-term bridge before a flexible hierarchy is justified:

`MinistryContext`
- CM
- EM

Relationships:
- `District` belongs to `MinistryContext`.
- `SmallGroup` belongs to `District`.
- User belongs to current `SmallGroup` through `Profile.small_group`.

This fits current Bible Study V2 scope and near-term Community Activities planning with minimal migration risk.

This is not the final flexible hierarchy model if the church needs variable-depth organization.

## 5. Long-Term Flexible Hierarchy Direction

Future planning may introduce a flexible tree model.

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
- Current user small group may remain on `Profile.small_group` in the near term.
- Future membership history can be added later.
- Long-term membership source of truth should be `ChurchStructureMembership`.
- Requested signup/onboarding units should require staff approval before becoming active membership.
- Do not import phone/private/sensitive data.
- Do not do full historical import in the first version.

## 7. Relationship to Existing SmallGroup

### Option A - Keep Current District and SmallGroup Canonical

Keep existing `SmallGroup` and `District` as canonical for now. Add `MinistryContext` first if CM/EM scoping becomes necessary. Later add flexible `ChurchStructureUnit` only when proven needed.

Pros:
- Lower migration risk.
- Fits current Bible Study V2 scope.
- Preserves `Profile.small_group`.
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

Do not switch current behavior to the flexible tree immediately.

Short term:
- Keep `District` and `SmallGroup`.
- Keep `MinistryContext` as the bridge for CM/EM.
- Keep `Profile.small_group` as the current primary-small-group field.
- Keep `ChurchStructureUnit` mapping fields optional and non-runtime during seeding/mapping.
- Keep signup/onboarding assignment approval separate from final membership.

Long term:
- Map current structure into `ChurchStructureUnit` only after Bible Study V2 and Community Activities needs prove the need.
- Move belonging to `ChurchStructureMembership` only after model design, approval workflow, and visibility tests.
- Avoid destructive migration.

## 8. Relationship to Bible Study

Bible Study V2 near-term uses `BibleStudySeries` scope:
- whole church
- ministry context
- district
- small group

Schedule generation uses the current `MinistryContext` -> `District` -> `SmallGroup` bridge through `BibleStudySeries.get_eligible_small_groups()`.

Future Bible Study schedule scope may use `ChurchStructureUnit` or audience segments.

A future Bible Study schedule can target:
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

CS-F.3 adds optional `ServiceEvent.ministry_context` labeling only. It is metadata for identifying the ministry context of an official church service/event anchor and must not drive audience filtering, `TeamAssignment` visibility, My Serving visibility, or MinistryTeam behavior.

CS-F.3B clarifies the current UI wording: this field should be presented as a Ministry Context Label / 事工标签（可选）, separate from the existing single Audience Scope / 覆盖对象 fields. Flexible hierarchy, multi-select audience scope, `ChurchStructureUnit`, and CM/EM-aware ServiceEvent filtering remain future work.

CS-F.3C clarifies the limited current ServiceEvent scope UI: Audience Scope supports Whole Church, one District, or one Small Group. Selecting District binds the event at the district level and does not expand into child small-group selection. Multi-level and multi-select audience selection remain future Church Structure work. MinistryTeam handbook/manual links open in a new tab.

Future `ServiceEvent` may reference participating structure units or multiple `MinistryContext` records, but this should be separately planned.

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

Church Structure Foundation should be treated as the current foundation step:
- Bible Study V2 Flow QA has passed
- CS-F.1 implements the short-term `MinistryContext` bridge
- CS-F.2 adds `MinistryContext` as a Bible Study Schedule scope
- CS-F.3 adds optional `ServiceEvent.ministry_context` labeling only
- CS-H.2 adds model-only `ChurchStructureUnit` foundation with no seeding, no mapping, no audience selection, and no filtering
- CS-H.2A hardens `ChurchStructureUnit` cycle validation without adding seeding, mapping, audience selection, or filtering
- CS-H.3 records mapping, membership, and signup/onboarding approval strategy without implementation
- CS-H.3B adds nullable legacy mapping fields without seeding, runtime behavior changes, membership, audience selection, or filtering
- CS-H.3C adds an idempotent management command for explicit seeding/mapping, with no runtime behavior changes, membership, audience selection, or filtering
- CS-H.3D verifies production/staging command execution and idempotency, with no runtime behavior changes, membership, audience selection, or filtering
- before or alongside Community Activities implementation planning
- before implementing advanced mixed audience segments
- before implementing CM/EM-aware `ServiceEvent` filtering

Keep membership, signup approval, audience selection, Community Activities, Checklist V1, and role-aware Bible Study editing permissions deferred until separately chosen. `ChurchStructureUnit` seeding/mapping now exists only as an explicit management command and has passed GoDaddy production/staging verification. Runtime behavior still uses the legacy structure models.

## 14. Deliverable Summary

This plan documents:
- flexible hierarchy through the model-only `ChurchStructureUnit` tree foundation
- implemented short-term bridge using `MinistryContext`, `District`, `SmallGroup`, and `Profile.small_group`
- CS-H.3 long-term source-of-truth decision: `ChurchStructureUnit` plus `ChurchStructureMembership`
- CS-H.3 signup/onboarding direction: requested unit plus staff approval, not direct self-assignment
- CS-H.3B nullable mapping fields from legacy structure models to `ChurchStructureUnit`
- CS-H.3C explicit `seed_church_structure_units` command for idempotent seeding/mapping
- CS-H.3D production/staging seeding verification closure
- no automatic `ChurchStructureUnit` data seeding or source-of-truth migration
- long-term variable-depth structure with separate membership history
- Bible Study relationship through current schedule scope, including `MinistryContext`, and possible future structure-unit scope later
- Community Activities relationship through future audience segments
- ServiceEvent and Ministry Operations boundaries
- roadmap placement after Bible Study V2 Flow QA and before advanced mixed audience work
