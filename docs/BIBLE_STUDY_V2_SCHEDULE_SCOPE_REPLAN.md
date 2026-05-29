# Bible Study V2 Schedule / Scope Replan

## 1. Problem Statement

Bible Study V2 now has the schedule/scope layer and meeting generation pieces in place. This document remains useful as the planning record for why the hierarchy exists and how later scope work should align.

Completed pieces include:
- church-wide Bible Study Guides
- small-group Bible Study Meetings
- group preparation
- meeting roles
- worship set management

The top-level concept is Bible Study Schedule / 查经安排: one quarter, season, or planned sequence of Bible Study work.

Earlier staff IA made V1 `BibleStudySession`, V2 `BibleStudyLesson`, and V2 `BibleStudyMeeting` look like parallel systems. Staff and normal navigation should now present one coherent V2 Bible Study experience instead of promoting V1 as a visible second Bible Study system.

The real workflow should be hierarchical:

```text
Bible Study Schedule / 查经安排
-> Weekly Bible Study Guide / 每周查经指引
-> Small Group Bible Study Meetings / 小组查经聚会
-> Group preparation / 小组查经预备
-> Meeting roles / 查经聚会同工分工
-> Worship set / 敬拜诗歌安排
```

The system should preserve this hierarchy so users understand one workflow rather than three unrelated Bible Study tools.

## 2. Current Code Inventory Summary

Current V1:

`BibleStudySession`
- `series`
- `title` / `title_en`
- `scripture_reference`
- `prestudy_datetime`
- `study_datetime`
- `location`
- `meeting_link`
- `scope_type`
- `district`
- `small_group`
- `status`
- `published_at`

`BibleStudyGuide`
- one-to-one with `BibleStudySession`
- `guide_body`
- `discussion_questions`
- `prestudy_notes`

`BibleStudyWorshipSong`
- session-level worship songs
- order, title, key, links, and notes

Current V2:

`BibleStudySeries`
- functions as Bible Study Schedule / 查经安排
- fields: `title`, `title_en`, `description`, `description_en`, `is_active`, `start_date`, `end_date`, `status`, `published_at`, `created_by`, `scope_type`, `ministry_context`, `district`, `small_group`
- `get_eligible_small_groups()` supports whole church/global, ministry_context, district, and small_group scope for generation
- `BibleStudyLesson.series` is the schedule relationship
- `BibleStudyMeeting` derives schedule through `meeting.lesson.series`

`BibleStudyLesson`
- church-wide guide material
- linked to `BibleStudySeries`
- includes scripture, guide date, pre-study datetime, pastor guide, church-wide questions, pre-study notes, status, and publish timestamp

`BibleStudyMeeting`
- linked to `BibleStudyLesson` and `SmallGroup`
- per-group meeting setup and group preparation
- optional `service_event`
- unique `(lesson, small_group)` constraint, useful for idempotent generation
- currently still includes discussion leader fields even though `BibleStudyMeetingRole` now owns meeting responsibilities

`BibleStudyMeetingRole`
- per-meeting responsibilities such as discussion leader, worship lead, pianist, support, host

`BibleStudyMeetingWorshipSong`
- per-meeting worship set with sort order, title, key, links, arrangement notes, support notes, and worship lead fallback

Current staff navigation exposes V1 and V2 concepts side-by-side:
- V1 Bible Study Admin via `/studies/`
- V2 Bible Study Guides
- V2 Small Group Meetings

This is accurate to the code, but confusing as product IA.

## 3. Corrected Domain Model

### BibleStudySchedule / 查经安排

Represents a quarter, season, or planned series of Bible Study.

User-facing term:
- English: Bible Study Schedule
- Chinese: 查经安排

It may be implemented by enhancing existing `BibleStudySeries`, or by adding a new `BibleStudySchedule` model. This replan recommends treating existing `BibleStudySeries` as the internal schedule model for now.

### BibleStudyGuide / 每周查经指引

Represents one weekly church-wide guide under a Bible Study Schedule.

Current internal model may remain `BibleStudyLesson`.

Belongs under:
- `BibleStudySeries` as schedule, or a future `BibleStudySchedule`

Contains:
- scripture reference
- pastor guide
- church-wide discussion questions
- pre-study notes
- guide date
- pre-study datetime
- status

### BibleStudyMeeting / 小组查经聚会

Represents one generated or manually created meeting for one `SmallGroup` under one weekly guide.

It should be linked to the weekly guide.

It should derive its schedule through `meeting.lesson.series` unless a future reason requires a direct schedule FK.

Contains:
- meeting time
- location
- meeting link
- group direction/questions
- status

It does not own church-wide guide content.

It must display updated guide content whenever the parent guide is updated.

`ServiceEvent` remains optional and advanced.

### BibleStudyMeetingRole / 查经聚会同工分工

Represents per-meeting roles only.

It is not:
- long-term C/E/O/W/F coworker structure
- `TeamAssignment`
- automatic scheduling
- availability
- swap request
- reminder workflow

### BibleStudyMeetingWorshipSong / 敬拜诗歌安排

Represents the per-meeting worship set.

It is not:
- a full worship song library
- a worship ministry scheduling system
- a replacement for meeting roles

## 4. Recommendation: Reuse BibleStudySeries or Add BibleStudySchedule?

### Option A - Enhance Existing BibleStudySeries

Pros:
- Existing `BibleStudyLesson` already links to `BibleStudySeries`.
- Generated `BibleStudyMeeting` can link to schedule through `meeting.lesson.series`.
- Less disruptive.
- Fewer migrations.
- Best fit for current code.
- Preserves existing relationships and tests.

Cons:
- Internal name "Series" does not perfectly express "Schedule".
- Existing UI/tests may need wording cleanup.
- Future developers need a clear note that `BibleStudySeries` is functioning as the schedule container.

### Option B - Add New BibleStudySchedule

Pros:
- Clearer model name.
- Better long-term domain clarity.
- Easier for new developers to understand from code names alone.

Cons:
- Requires more migration and refactor.
- Existing lesson relation must be changed or duplicated.
- Higher risk during the current phase.
- Could create a duplicate source of truth if both series and schedule exist.
- Could create another parallel concept while staff IA is already confusing.

### Recommendation

Treat existing `BibleStudySeries` as the internal model for Bible Study Schedule for now.

Use user-facing wording:
- English: Bible Study Schedule
- Chinese: 查经安排

Add schedule-oriented fields to `BibleStudySeries` later if needed.

Use `BibleStudyLesson.series` as the schedule relationship.

Let `BibleStudyMeeting` derive schedule through `meeting.lesson.series`.

Do not destructively rename models now.

Later, consider a true `BibleStudySchedule` model or model rename only if `BibleStudySeries` becomes too limiting after schedule fields, scope/audience, and generation behavior are proven.

## 5. Schedule Scope / Audience Model

Bible Study Schedule or weekly guide needs a scope/audience concept so staff can generate meetings for the correct groups.

Church hierarchy to plan around:
- Whole church / 全教会
- MinistryContext: CM / EM
- District / 区
- SmallGroup / 小组

Current code has:
- `MinistryContext`
- `District`
- `SmallGroup`
- `Profile.small_group`
- nullable `District.ministry_context`

Implemented bridge:
- `MinistryContext` represents contexts such as CM and EM without hard-coding the only allowed values.
- `District` may belong to `MinistryContext`.
- `SmallGroup` belongs to `District` and can therefore derive `MinistryContext`.
- Do not create a fake Combined Ministry.
- Combined means multiple participating ministry contexts.

Near-term Bible Study V2 should support current available structure first:
- whole church
- ministry context
- district
- small group

Future enhancement:
- mixed audience segments if needed
- flexible `ChurchStructureUnit` scope only after a separate Church Structure Foundation step proves the need

Recommended future audience segment concept:

`BibleStudyScheduleAudience` or `BibleStudyGuideAudience`
- `schedule` or `guide`
- `audience_type`
  - `whole_church`
  - `ministry_context`
  - `district`
  - `small_group`
- `ministry_context` nullable
- `district` nullable
- `small_group` nullable

Do not implement this now.

See `docs/CHURCH_STRUCTURE_FOUNDATION_PLAN.md` for the future flexible hierarchy direction. Near-term Bible Study V2 should continue with whole church / ministry context / district / small group scope and current `MinistryContext` / `District` / `SmallGroup` meeting generation helpers.

## 6. Meeting Generation From Schedule / Guide Scope

Future behavior should support staff-created or staff-published:
- Bible Study Schedule / 查经安排
- weekly Bible Study Guides under that schedule

Then the system generates Small Group Bible Study Meetings for the in-scope small groups.

Generation may be triggered by:
- explicit staff action: Generate Small Group Meetings
- controlled publish action if later chosen

Recommendation:
- Use explicit staff action first for safety.
- It is still automatic generation across eligible groups.
- Staff controls when it runs.
- This avoids accidental mass creation while drafts are incomplete.

Examples:
- Whole church: create `BibleStudyMeeting` for every active `SmallGroup`.
- Ministry context: create `BibleStudyMeeting` for every active `SmallGroup` whose district belongs to that `MinistryContext`.
- District: create `BibleStudyMeeting` for every active `SmallGroup` in that district.
- Small group: create `BibleStudyMeeting` only for that group.

Generation behavior:
- System-generated based on scope/audience.
- Must not require staff to manually create each group meeting one by one.
- Idempotent:
  - create missing meetings only
  - skip existing meetings
  - do not overwrite group-specific data
  - do not delete meetings automatically
- Respect existing unique constraint: one meeting per lesson + small group.
- Show preview:
  - eligible small groups
  - number of meetings to be created
  - number already existing/skipped
- Allow default meeting datetime/location/link/status if appropriate.
- Set each generated meeting's `lesson` to the weekly guide.
- Derive schedule linkage through `meeting.lesson.series` unless a direct FK is later justified.
- Display parent guide content dynamically, not copied content.
- Do not assign discussion leaders, worship leads, pianists, or support automatically.
- Do not create `BibleStudyMeetingRole` automatically.
- Do not create worship songs automatically.
- Do not create `TeamAssignment`.
- Do not create `ServiceEvent` automatically.

Generation must not implement availability, swap, reminder, or scheduling logic.

## 7. Guide Update Propagation

If a weekly Bible Study Guide is updated:
- all linked small-group meetings should show the updated guide content
- parent guide content should not be copied into `BibleStudyMeeting`
- group-specific fields remain on `BibleStudyMeeting`
- church-wide fields remain on `BibleStudyLesson`

Group-specific fields:
- `group_direction`
- `group_questions`
- meeting roles
- worship set

Church-wide fields:
- pastor guide
- global discussion questions
- pre-study notes
- scripture

Meeting detail should display both:
- parent guide content from `BibleStudyLesson`
- group-specific preparation from `BibleStudyMeeting`

## 8. V1 BibleStudySession Relationship

V1 `BibleStudySession` is not useless. It contains concepts similar to the desired schedule/scope/guide setup, but it mixes too many layers.

V1 should be treated as compatibility/legacy behavior:
- Keep V1 `BibleStudySession` available for now.
- Do not treat it as the future primary model.
- Do not delete or migrate V1 data immediately.
- V1 models, routes, and data may remain internally preserved for compatibility.
- Normal and staff UI should not promote V1 as a visible second Bible Study system.

V1 routes may remain accessible internally or by direct URL if needed for compatibility, but normal/staff navigation should present the V2 schedule -> guide -> meeting workflow.

Future migration may map V1 sessions to:
- `BibleStudySeries` / Bible Study Schedule
- `BibleStudyLesson` / Weekly Bible Study Guide
- `BibleStudyMeeting`

That migration should be planned separately and should preserve data.

## 9. Staff IA Recommendation

Preferred visible staff Bible Study menu under Content Management:

English:
- Bible Study Schedules
- Weekly Bible Study Guides
- Small Group Meetings

Chinese:
- 查经安排
- 每周查经指引
- 小组查经聚会

Guides should be accessed primarily through a schedule detail page:
- Schedule detail shows weekly guides.
- Weekly guide detail shows generated small-group meetings.
- Small Group Meetings page remains useful for filtering/reviewing all meetings.

Avoid staff menu showing V1 and V2 as parallel Bible Study systems, or showing these as unrelated peer concepts:
- 查经管理
- 查经指引
- 小组查经聚会
- 旧版查经安排 / Legacy Bible Study Sessions

## 10. Bible Study Schedule Page Flow

Future staff flow:

A. Schedule list:
- list active/upcoming/past schedules
- create new schedule
- filter by status

B. Schedule detail:
- schedule title/date range/status/description
- list weekly Bible Study Guides under this schedule
- action: add weekly guide
- action: view generated meetings summary

C. Weekly guide detail:
- church-wide guide content
- related small group meetings
- action: generate small group meetings from scope/audience
- action: add one-off small group meeting manually

D. Meeting detail:
- group-specific preparation
- meeting roles
- worship set
- parent guide content visible and dynamically updated from guide

## 11. Small Group Meeting Form Cleanup Direction

Future cleanup:
- Meeting setup form should be lighter.
- Parent guide should be clearly labeled Bible Study Guide / 查经指引.
- `ServiceEvent` should be optional/advanced:
  - 关联聚会事件（可选）
  - leave blank for normal small-group Bible Study
- `discussion_leader_user` and `discussion_leader_name` should be removed from or de-emphasized in the main meeting setup form because `BibleStudyMeetingRole` now owns 查经带领.
- Group direction/questions may remain in the meeting setup form or move mostly to the preparation edit page.
- The flow should avoid duplicated/confusing fields.
- Manually creating one meeting should remain possible for exceptions, but the normal flow should be generation from schedule/guide scope.

## 12. Normal User Flow

Future normal user flow:
- Top nav Bible Study / 查经 eventually shows V2 content clearly.
- User sees:
  - current Bible Study Schedule
  - current weekly guide
  - their own generated `SmallGroup` meeting
  - parent guide content
  - group direction/questions
  - meeting roles
  - worship set
- User should not have to understand the V1/V2 split.
- User should not see other groups' private meeting content.
- V1 `/studies/` can remain until V2 landing is ready.

## 13. ServiceEvent Boundary

`ServiceEvent` is an optional operations/calendar anchor.

Normal small-group Bible Study should not require `ServiceEvent`.

`BibleStudyMeeting` is the Bible Study source of truth.

Do not:
- create `ServiceEvent` automatically when generating `BibleStudyMeeting`
- make `ServiceEvent` the parent of `BibleStudyMeeting`
- use `ServiceEvent` as the source of Bible Study guide content

`ServiceEvent` belongs to Ministry Operations, not Bible Study content.

## 14. Non-Goals

Do not build:
- model rename now
- destructive migration
- V1 data deletion
- copying guide content into each group meeting
- automatic scheduling of E/W coworkers
- availability matrix
- swap requests
- reminders
- Checklist V1
- Community Activities implementation
- `ServiceEvent` ministry context implementation yet
- additional `MinistryContext` integrations beyond Bible Study Schedule scope
- full ERP
- Google Docs full-content migration
- sensitive/private data import

## 15. Revised Implementation Phases

### BS-V2.6.0 - Schedule / Scope Replan Documentation

- Completed.

### BS-V2.6.1 - Staff IA Cleanup

- Completed.
- Staff navigation should present the V2 schedule/guide/meeting hierarchy.
- Do not show Legacy Bible Study Sessions / 旧版查经安排 as a visible staff menu item.

### BS-V2.6.2 - Treat BibleStudySeries as Bible Study Schedule

- Completed.
- `BibleStudySeries` is presented as Bible Study Schedule / 查经安排.
- Internal model name remains `BibleStudySeries`.

### BS-V2.6.3 - Add Schedule Fields

- Completed.
- Schedule lifecycle fields include `start_date`, `end_date`, `status`, `published_at`, and `created_by`.

### BS-V2.6.4 - Add Scope Fields

- Completed.
- Short-term scope supports whole church / district / small group using existing models.
- CS-F.2 adds `MinistryContext` as a Bible Study Schedule scope using the bridge from `MinistryContext` to `District` to `SmallGroup`.
- Future scope: audience segments only if needed.

### BS-V2.6.5 - Generate Group Meetings From Guide / Scope

- Completed.
- Explicit staff action creates missing `BibleStudyMeeting` rows for each eligible small group.
- Idempotent.
- Preview before create.
- No automatic role/worship assignment.
- No `TeamAssignment`.
- No automatic `ServiceEvent`.
- Guide content remains referenced, not copied.

### BS-V2.6.6 - Normal User V2 Landing Integration

- Completed.
- `/studies/` and Bible Study top nav show the current V2 schedule/guide/own-group meeting experience.
- V1 remains internally preserved for compatibility, but normal users should not see or need to understand a V1/V2 split.

### BS-V2.6.7 - Bible Study V2 Flow QA Checklist

- Run manual/browser QA after IA and schedule/scope alignment.
- Use `docs/BIBLE_STUDY_V2_FLOW_QA_CHECKLIST.md`.

### BS-V2.7 - Later Role-Aware Editing Permissions

- Discussion leader may edit group preparation.
- Worship lead may edit worship set.
- Only after role model and permissions are proven.

## 16. Roadmap Update Direction

Current recommended sequence:
- Bible Study V2 Flow QA passed.
- CS-F.1 MinistryContext bridge foundation completed.
- CS-F.2 MinistryContext Bible Study Schedule scope completed.
- Future flexible Church Structure Foundation planning only after the short-term bridge proves insufficient.
- Later role-aware editing permissions only if needed.

Checklist V1 remains deferred.

Lighting Pilot remains paused until IA/Bible Study flow stabilizes.
