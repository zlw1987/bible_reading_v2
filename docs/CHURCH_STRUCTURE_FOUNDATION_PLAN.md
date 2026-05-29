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

This began as a future planning artifact. CS-F.1 implements only the short-term `MinistryContext` bridge; do not implement additional models, migrations, views, templates, permissions, or data migration from this document without a separate implementation task.

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
- There is no flexible `OrganizationUnit` or `ChurchStructureUnit` tree yet.
- Current Bible Study schedule scope uses:
  - whole church
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
- Different branches can have different depths.
- CM and EM do not need identical depth.
- Do not create a fake Combined Ministry.
- Combined events or activities should reference multiple units or audience segments.

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

Do not implement the flexible tree immediately.

Short term:
- Keep `District` and `SmallGroup`.
- Plan `MinistryContext` as the bridge for CM/EM when needed.

Long term:
- Introduce `ChurchStructureUnit` only after Bible Study V2 and Community Activities needs prove the need.
- Avoid destructive migration.

## 8. Relationship to Bible Study

Bible Study V2 near-term should continue using `BibleStudySeries` scope:
- whole church
- district
- small group

Schedule generation should continue using the current `District` / `SmallGroup` helper direction.

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

Future `ServiceEvent` may reference participating structure units or `MinistryContext`, but this should be separately planned.

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
- before or alongside Community Activities implementation planning
- before implementing advanced mixed audience segments
- before implementing CM/EM-aware `ServiceEvent` filtering

Keep flexible `ChurchStructureUnit` work, Community Activities, Checklist V1, and role-aware Bible Study editing permissions deferred until separately chosen.

## 14. Deliverable Summary

This plan documents:
- flexible hierarchy through a future `ChurchStructureUnit` tree
- implemented short-term bridge using `MinistryContext`, `District`, `SmallGroup`, and `Profile.small_group`
- long-term variable-depth structure with separate membership history
- Bible Study relationship through current schedule scope now and possible future structure-unit scope later
- Community Activities relationship through future audience segments
- ServiceEvent and Ministry Operations boundaries
- roadmap placement after Bible Study V2 Flow QA and before advanced mixed audience work
