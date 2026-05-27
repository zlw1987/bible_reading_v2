# Church Structure Domain Plan

## 1. Purpose

This document records church structure and domain boundaries for future planning in `bible_reading_v2`.

The project remains a lightweight church spiritual life and ministry workflow system, not a full church ERP.

This is a planning artifact only. Do not implement models, migrations, views, templates, or permission changes from this document without a separate implementation task.

## 2. Fellowship Small Groups

Fellowship small groups are the smallest Friday Bible Study unit.

Examples:
- Rainbow 1
- Rainbow 4

A person currently belongs to one fellowship small group at a time, represented today by `SmallGroup` and `Profile.small_group`.

Future planning may consider historical membership:

`SmallGroupMembership`
- `user`
- `small_group`
- `start_date`
- `end_date`
- `is_active`

Do not implement this now.

Important distinctions:
- Fellowship `SmallGroup` is not the same as `MinistryTeam`.
- Friday Bible Study happens at the fellowship small group level.
- `BibleStudyMeeting` should remain anchored to `SmallGroup`.
- `SmallGroup` membership may change over time, but current app behavior can continue using the current active group until historical membership is planned.

## 3. Small Group Coworker Structure

Each fellowship small group has an internal coworker structure.

Common roles:
- Group Leader / 组长
- C = Caring / 关怀同工
- E = Edify / 查经同工
- O = Outreach / 外展同工
- W = Worship / 敬拜同工
- F = Finance / 管账同工

Some groups may define additional roles:
- A = Activity / 活动同工
- other group-defined roles

These are fellowship small-group coworker roles.

They should not be modeled as `MinistryTeam`.
They should not use `TeamAssignment`.
They should not be confused with church-level ministry teams such as Lighting, Audio, Video, or Projection.

Future planning may consider:

`SmallGroupCoworkerRoleDefinition`
- `code`
- `name`
- `name_en`
- `description`
- `is_system_default`
- `small_group` nullable for custom group roles

`SmallGroupCoworkerAssignment`
- `small_group`
- `user`
- `role`
- `start_date`
- `end_date`
- `is_active`

Do not implement these now.

## 4. Friday Bible Study Roles

Friday Bible Study uses rotating responsibilities.

Examples:
- E coworkers rotate leading Bible Study.
- W coworkers rotate leading worship.
- Pianist/accompanist/support coworkers may also be assigned.
- Host or support roles may be used by some groups.

Per-meeting responsibilities should be represented by `BibleStudyMeetingRole`.

Difference between long-term group role and one-meeting responsibility:

`SmallGroupCoworkerAssignment`
- Long-term role inside a fellowship small group.
- Example: this person is one of Rainbow 4's E coworkers.

`BibleStudyMeetingRole`
- Responsibility for one specific `BibleStudyMeeting`.
- Example: this week this E coworker leads Bible Study.

`BibleStudyMeetingRole` is not `TeamAssignment`.
It is not automatic scheduling.
It is not availability, swap request, or reminder workflow.
It is simple per-meeting preparation responsibility.

Manual assignment should come first. Do not implement automatic rotation/scheduling yet.

## 5. Bible Study V2 Phase Order

The real workflow suggests meeting roles should come before deeper worship-set ownership logic.

BS-V2.5A and BS-V2.5B have now produced the basic meeting roles and group-level worship set surfaces. Browser review showed that the next correction is not role-aware permissions yet; it is schedule/scope and staff IA alignment.

Updated recommended Bible Study sequence:
- BS-V2.6.0 - Schedule/scope replan documentation
- BS-V2.6.1 - Staff IA cleanup
- BS-V2.6.2 - Treat `BibleStudySeries` as Bible Study Schedule / 查经安排
- BS-V2.6.5 - Manual idempotent meeting generation from guide/scope
- BS-V2.6.6 - Normal user V2 landing integration
- BS-V2.6.7 - Bible Study V2 Flow QA
- BS-V2.7 - Role-aware editing permissions, if needed later

Earlier sequence now completed:
- BS-V2.5A - Simple `BibleStudyMeetingRole` UI
- BS-V2.5B - Group-level worship set UI

Reason:
- Worship set ownership depends on knowing who the worship lead, support, and pianist are.
- Simple meeting roles clarify preparation responsibility before permission rules become more specific.
- The schedule/scope layer clarifies how weekly guides produce in-scope small-group meetings before staff or role holders receive more editing powers.
- Generated small-group meetings should reference the weekly guide, derive schedule through the guide's series/schedule, and display updated parent guide content without copying it into each meeting.

If worship set UI already exists before the role UI, keep it manager-controlled until meeting roles are available and validated. Do not retroactively force worship responsibilities into `TeamAssignment`.

## 6. Church-Level Ministry Operations

Church-level ministry operations are separate from fellowship small group coworker roles.

Existing `ServiceEvent` + `MinistryTeam` + `TeamAssignment` should remain the structure for official church service operations.

Examples of official church service operations:
- Sunday Service / 主日崇拜
- combined worship service
- official church event requiring ministry team service

Examples of church ministry teams/departments:
- DM = Digital Ministry
  - Lighting / 灯光组
  - Video / 视频 / 直播录像
  - Audio / 音控
  - Projection / 投影 / 幻灯片
- IM = Internet Mission
  - CTC website/system development and maintenance

Clarifications:
- Lighting/Video/Audio/Projection service assignments belong to `MinistryTeam` + `TeamAssignment`.
- Small group Bible Study leading/worship/accompaniment belongs to `BibleStudyMeetingRole`.
- IM/CTC project work may need future planning, but should not be forced into `TeamAssignment` unless it is event-based serving.
- Do not add a LightingTeam-specific model.

## 7. CM / EM Ministry Contexts

The church has:
- CM = Chinese Ministry
- EM = English Ministry

CM and EM are ministry contexts / language ministries.
They should not be modeled as `MinistryTeam`.

There is no separate "Combined Ministry".
Combined events should be represented by an event/activity involving both CM and EM.

Future planning may consider:

`MinistryContext`
- `code`: CM / EM
- `name`
- `name_en`
- `is_active`

For `ServiceEvent`, future planning may consider:
- `participating_ministries`: ManyToMany to `MinistryContext`
- `lead_ministry`: optional FK to `MinistryContext`, if ownership/leadership needs to be tracked

Important distinction:
- `participating_ministries` answers: who is this event for / who participates?
- `lead_ministry` answers: who is responsible for leading/owning it?

Examples:
- CM Sunday Service: `participating_ministries = [CM]`
- EM Sunday Service: `participating_ministries = [EM]`
- Monthly combined Sunday Service: `participating_ministries = [CM, EM]`

Do not create a fake COMBINED ministry record.
Do not implement this now.

## 8. ServiceEvent Relationship

`ServiceEvent` remains the official church gathering / operations / ministry assignment anchor.

Use `ServiceEvent` when the main question is:
- Which ministry team is serving?
- Which service/event needs Lighting/Audio/Video/Projection?
- What official church gathering needs operations support?

`ServiceEvent` should not replace:
- `BibleStudyMeeting`
- `CommunityActivity`
- `SmallGroupCoworkerAssignment`
- `BibleStudyMeetingRole`

`BibleStudyMeeting` may optionally link to `ServiceEvent` for operations anchoring, but Bible Study remains the source of truth for Bible Study content and preparation.

## 9. Community Activities and Audience Segments

Community Activities should remain a future/deferred module for signup-oriented activities.

Do not merge it into `ServiceEvent`.
Do not create a separate `SpecialEvent` model.

"Special event" is not one model by itself. Choose the model based on the main question:
- If the main question is "which ministry team is serving?", use `ServiceEvent` + `TeamAssignment`.
- If the main question is "who can attend/signup?", use `CommunityActivity` + `ActivitySignup`.

If a large event needs both signup and ministry operations, future planning may allow `CommunityActivity` to optionally link to `ServiceEvent`, but not in V1.

The simple single `scope_type` idea is not enough for real scenarios.

Real scenarios include:
- entire EM plus several CM small groups
- EM plus one CM district
- several CM small groups
- whole church
- selected districts
- selected groups across ministries

Recommended future concept:

`CommunityActivity`
- `title`
- `title_en`
- `description`
- `description_en`
- `organizer`
- `start_datetime`
- `end_datetime`
- `location`
- `location_en`
- `capacity` optional
- `signup_deadline` optional
- `status`
- `requires_approval`
- `created_by`
- `approved_by`
- `approved_at`

`CommunityActivityAudience`
- `activity`
- `audience_type`:
  - `whole_church`
  - `ministry_context`
  - `district`
  - `small_group`
- `ministry_context` nullable
- `district` nullable
- `small_group` nullable

`ActivitySignup`
- `activity`
- `user`
- `status`:
  - `signed_up`
  - `cancelled`
  - `waitlisted` optional/future
- `note` optional
- `created_at`
- `updated_at`

Examples:

Entire EM + CM Rainbow 1 + CM Rainbow 4:
- audience segment: `ministry_context = EM`
- audience segment: `small_group = Rainbow 1`
- audience segment: `small_group = Rainbow 4`

EM + CM District 1:
- audience segment: `ministry_context = EM`
- audience segment: `district = CM District 1`

CM selected small groups:
- audience segment: `small_group = Rainbow 1`
- audience segment: `small_group = Rainbow 4`

Whole church:
- audience segment: `whole_church`

Visibility rule:
A user can see/signup if any audience segment matches the user:
- whole church
- user's ministry context
- user's district
- user's small group

Avoid exposing private membership lists in UI. The list should answer "can this user see this activity?" rather than reveal all internal membership structures.

## 10. District Relationship

District may need to relate to `MinistryContext` in the future.

Examples:
- CM District 1 / 第一区
- CM District 2 / 第二区

Future planning may consider:
- `District.ministry_context`
- `SmallGroup -> District -> MinistryContext`

Do not implement this now.

## 11. Roadmap Implications

Recommended next sequence:
- Church structure domain plan
- Small group coworker roles planning
- BS-V2.5A Simple `BibleStudyMeetingRole` UI
- BS-V2.5B Group-level worship set UI
- Bible Study V2 Schedule/Scope Replan
- Staff IA cleanup
- Schedule/scope alignment and meeting generation
- Later role-aware editing permissions
- Later `ServiceEvent` participating_ministries / `MinistryContext` planning
- Later Community Activities V1 with audience segments
- Checklist V1 remains deferred

Checklist V1 should remain deferred until Lighting Pilot validation and should not be revived because of Community Activities.

## 12. Non-Goals

Do not build:
- full church ERP
- automatic scheduling
- availability matrix
- swap requests
- reminders
- full historical import
- sensitive/private data import
- Google Docs full-content migration
- forcing small group coworkers into `MinistryTeam`
- forcing `BibleStudyMeetingRole` into `TeamAssignment`
- forcing `CommunityActivity` into `ServiceEvent`
- fake Combined Ministry record
- `ServiceEvent` replacement
- `SpecialEvent` model unless a future need is separately proven
