# Bible Study V2 Schedule / Scope Replan

> **Current-state update:** this replan preserves the historical path to the V2
> schedule/guide/meeting hierarchy. Current Bible Study uses `BibleStudySeries` +
> `BibleStudyLesson` + `BibleStudyMeeting`; V1 schema is removed; normal
> generation is structure-unit-native from `BibleStudySeriesAudienceScope` rows;
> V2 meeting visibility / `/studies/` / Today / role-worship pickers use
> `BibleStudyMeetingAudienceScope` rows plus active primary
> `ChurchStructureMembership`; and zero-row V2 meetings fail closed. Body text
> that says visibility remains on `Profile.small_group`, generation resolves to
> legacy `SmallGroup`, or ServiceEvent remains a later audience consumer is
> historical/superseded.

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

## 2. Historical Code Inventory Summary At Replan Time

Historical V1 at the time of this replan:

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

Historical V2 at the time of this replan:

`BibleStudySeries`
- functions as Bible Study Schedule / 查经安排
- historical fields then included: `title`, `title_en`, `description`, `description_en`, `is_active`, `start_date`, `end_date`, `status`, `published_at`, `created_by`, `scope_type`, `ministry_context`, `district`, `small_group`
- Historical/superseded: the old eligible-small-groups helper supported whole church/global, ministry_context, district, and small_group scope for generation. Current normal V2 generation uses `BibleStudySeriesAudienceScope` rows and expands selected units to active small-group `ChurchStructureUnit` leaf targets.
- `BibleStudyLesson.series` is the schedule relationship
- `BibleStudyMeeting` derives schedule through `meeting.lesson.series`

`BibleStudyLesson`
- church-wide guide material
- linked to `BibleStudySeries`
- includes scripture, guide date, pre-study datetime, pastor guide, church-wide questions, pre-study notes, status, and publish timestamp

`BibleStudyMeeting`
- historical/superseded: linked to `BibleStudyLesson` and legacy `SmallGroup` at the time of this inventory
- per-group meeting setup and group preparation
- optional `service_event`
- Historical/superseded: the old unique `(lesson, small_group)` constraint supported legacy idempotent generation; current V2 idempotency is structure-native through `generation_key`, `anchor_unit`, and matching meeting audience rows.
- currently still includes discussion leader fields even though `BibleStudyMeetingRole` now owns meeting responsibilities

`BibleStudyMeetingRole`
- per-meeting responsibilities such as discussion leader, worship lead, pianist, support, host

`BibleStudyMeetingWorshipSong`
- per-meeting worship set with sort order, title, key, links, arrangement notes, support notes, and worship lead fallback

Historical staff navigation exposed V1 and V2 concepts side-by-side:
- V1 Bible Study Admin via `/studies/`
- V2 Bible Study Guides
- V2 Small Group Meetings

This was accurate to the code at the replan point, but is now historical. Current
code has removed V1 schema and uses V2 `BibleStudySeries` / `BibleStudyLesson` /
`BibleStudyMeeting` plus audience rows.

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

Represents one generated or manually created meeting for one small-group
structure-unit target under one weekly guide. Historical/superseded: the
original replan described this as one legacy `SmallGroup`.

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

Historical church hierarchy considered at the replan point:
- Whole church / 全教会
- MinistryContext: CM / EM
- District / 区
- SmallGroup / 小组

Historical code then had:
- `MinistryContext`
- `District`
- `SmallGroup`
- `Profile.small_group`
- nullable `District.ministry_context`

Historical implemented bridge:
- `MinistryContext` represents contexts such as CM and EM without hard-coding the only allowed values.
- `District` may belong to `MinistryContext`.
- `SmallGroup` belongs to `District` and can therefore derive `MinistryContext`.
- Do not create a fake Combined Ministry.
- Combined means multiple participating ministry contexts.

Current schedule audience uses `BibleStudySeriesAudienceScope` rows selecting
`ChurchStructureUnit` units. Legacy `BibleStudySeries` scope fields and legacy
structure tables are removed.
- district
- small group

Historical: this originally used the legacy `BibleStudySeries` scope fields (`scope_type`, `ministry_context`, `district`, `small_group`). Those four fields were **removed in BS-SERIES-FIELD-RETIRE.1A** (migration `studies/0010`); schedule audience/eligibility and normal generation now use `BibleStudySeriesAudienceScope` rows and structure-unit-native targets, failing closed on zero rows.

### BS-AS direction (supersedes the earlier legacy-only future plan)

The earlier near-term plan to add another legacy-only audience segment model (`BibleStudyScheduleAudience` / `BibleStudyGuideAudience` with `audience_type` plus nullable `ministry_context` / `district` / `small_group`) is superseded by the DOCS-AS.1 shared audience-scope direction.

The new direction is:
- `ChurchStructureUnit` is the shared flexible structure / audience-selection foundation.
- Bible Study Schedule audience scope should use an app-specific join model to `ChurchStructureUnit`, e.g. `BibleStudySeriesAudienceScope`, rather than adding more legacy-only multi-select scope fields.
- `BibleStudySeries / 查经安排` owns the audience scope.
- `BibleStudyLesson / 查经指引` continues to inherit/display schedule scope; do not add independent lesson-level scope in BS-AS.1. A future lesson-level override may be considered later, but it is out of scope now.
- Historical/superseded: at BS-AS.1 time, meeting generation resolved selected
  `ChurchStructureUnit` rows to eligible legacy `SmallGroup` rows, generated
  `BibleStudyMeeting` rows still pointed to legacy `SmallGroup`, ordinary member
  visibility stayed on `Profile.small_group`, and the slice did not migrate
  ordinary user visibility to `ChurchStructureMembership`.
- Current state: normal generation is structure-unit-native, generated meetings
  use `generation_key`, `anchor_unit`, and meeting audience rows, and ordinary
  member visibility uses `BibleStudyMeetingAudienceScope` plus active primary
  `ChurchStructureMembership`.

Status: implemented. BS-AS.1, BS-AS.2, and BS-AS.2A are complete (see the milestone entries in section 15). Bible Study Schedule was the first narrow `ChurchStructureUnit` audience-scope runtime consumer. ServiceEvent / Church Gatherings later reused the same foundation as an implemented runtime consumer; Community Activities remains deferred and separately approved.

See `docs/FLEXIBLE_CHURCH_STRUCTURE_AND_AUDIENCE_SCOPE_DESIGN.md` for the shared `ChurchStructureUnit` audience-scope direction and `docs/CHURCH_STRUCTURE_FOUNDATION_PLAN.md` for the flexible hierarchy background. The legacy `BibleStudySeries.scope_type` / `ministry_context` / `district` / `small_group` fields were **removed in BS-SERIES-FIELD-RETIRE.1A** (migration `studies/0010`); schedule audience/eligibility now uses `BibleStudySeriesAudienceScope` rows only.

## 6. Meeting Generation From Schedule / Guide Scope

Future behavior should support staff-created or staff-published:
- Bible Study Schedule / 查经安排
- weekly Bible Study Guides under that schedule

Then the system generates small-group Bible Study Meetings for the in-scope
structure-unit targets.

Generation may be triggered by:
- explicit staff action: Generate Small Group Meetings
- controlled publish action if later chosen

Recommendation:
- Use explicit staff action first for safety.
- It is still automatic generation across eligible groups.
- Staff controls when it runs.
- This avoids accidental mass creation while drafts are incomplete.

Current generation examples:
- Whole church/root audience: create `BibleStudyMeeting` rows for active descendant/self `UNIT_SMALL_GROUP` `ChurchStructureUnit` leaf targets.
- Ministry/district-like structure unit audience: create meetings for active descendant small-group structure units.
- Small-group structure unit audience: create the meeting for that unit.
- Mixed audience rows: union the active small-group leaf targets and create one meeting per lesson/target identity.

Generation behavior:
- System-generated based on scope/audience.
- Must not require staff to manually create each group meeting one by one.
- Idempotent:
  - create missing meetings only
  - skip existing meetings
  - do not overwrite group-specific data
  - do not delete meetings automatically
- Respect current idempotency: one generated meeting per lesson + structure-unit target identity through `generation_key`, `anchor_unit`, and meeting audience rows.
- Show preview:
  - eligible structure-unit small-group targets
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

Historical/superseded: V1 `BibleStudySession` contained concepts similar to the desired schedule/scope/guide setup, but mixed too many layers.

Current state: V1 schema was removed behind the approved migration guard after
zero-row preflight. V1 must not be revived as a visible second Bible Study
system.

Historical/superseded: V1 routes could remain accessible internally or by direct
URL if needed for compatibility. Current normal/staff navigation should present
the V2 schedule -> guide -> meeting workflow.

Historical migration idea, superseded by V1 schema removal, could have mapped V1 sessions to:
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
  - their own generated small-group structure-unit meeting
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

- Completed historically.
- Historical/superseded: short-term scope supported whole church / district / small group using existing models.
- Historical/superseded: CS-F.2 added `MinistryContext` as a Bible Study Schedule scope using the bridge from `MinistryContext` to `District` to `SmallGroup`.
- Current state: `BibleStudySeriesAudienceScope` rows are the schedule audience source; legacy scope fields were removed.

### BS-V2.6.5 - Generate Group Meetings From Guide / Scope

- Completed.
- Note: the milestone name `BS-V2.6.5` has already been used for this "Generate Group Meetings From Guide / Scope" work and must not be reused for the new `ChurchStructureUnit` audience-scope work. Use the `BS-AS.1` name instead.
- Explicit staff action now creates missing `BibleStudyMeeting` rows for each eligible structure-unit target.
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

### BS-AS.1 - Bible Study Schedule audience scope using ChurchStructureUnit

- Completed. Supersedes the earlier legacy-only future scope plan.
- Added `BibleStudySeriesAudienceScope`, the app-specific join model selecting `ChurchStructureUnit` rows for `BibleStudySeries / 查经安排`.
- `BibleStudySeries` owns the audience scope; `BibleStudyLesson / 查经指引` inherits/displays the schedule scope. No independent lesson-level scope was added.
- Historical/superseded: at BS-AS.1 time, meeting generation resolved selected
  `ChurchStructureUnit` rows to eligible legacy `SmallGroup` rows, generated
  `BibleStudyMeeting` rows still pointed to legacy `SmallGroup`, ordinary member
  visibility continued to use `Profile.small_group`, and the slice did not
  migrate ordinary user visibility to `ChurchStructureMembership`.
- Current state: normal generation is structure-unit-native and V2 meeting
  visibility uses `BibleStudyMeetingAudienceScope` rows plus active primary
  membership.
- Legacy `scope_type` / `ministry_context` / `district` / `small_group` were removed in BS-SERIES-FIELD-RETIRE.1A (migration `studies/0010`); audience rows are the sole schedule audience source.
- A future lesson-level override may be considered later, but it is out of scope now.
- The already-used `BS-V2.6.5` milestone name was not reused for this work.

### BS-AS.2 - Audience picker UX, compact scope display, active-list cancelled cleanup

- Completed.
- Replaced the raw flat audience multi-select with a reusable server-rendered `ChurchStructureUnit` audience picker partial: searchable list, selected chips, tree/grouped ordering, no-JS checkbox fallback, and vanilla-JS root/ancestor/descendant convenience clearing. Backend validation remains the source of truth.
- Scope display now uses compact labels on list/card surfaces and wrapped/chip labels on detail surfaces; the Whole Church root prefix is omitted from non-root labels.
- Normal active management lists hide cancelled schedules/guides/meetings by default, and schedule/lesson detail related lists hide cancelled guides/meetings.
- Meeting generation still treats cancelled meetings as existing/skipped so they are not regenerated or reactivated.

### BS-AS.2A - Audience picker accessibility polish

- Completed.
- Audience picker search input has a bilingual `aria-label`.
- Selected chip remove buttons include the selected unit label in the `aria-label`.
- No behavior, schema, or visibility changes.

### BS-V2.7 - Later Role-Aware Editing Permissions

- Discussion leader may edit group preparation.
- Worship lead may edit worship set.
- Only after role model and permissions are proven.

## 16. Roadmap Update Direction

Current recommended sequence:
- Bible Study V2 Flow QA passed.
- CS-F.1 MinistryContext bridge foundation completed.
- CS-F.2 MinistryContext Bible Study Schedule scope completed.
- DOCS-AS.1 records the shared `ChurchStructureUnit` audience-scope direction.
- BS-AS.1 Bible Study Schedule audience scope using `ChurchStructureUnit` is
  complete, as the first narrow runtime audience-scope consumer. Historical:
  BS-AS.1 originally resolved selected units to legacy `SmallGroup` for meeting
  generation and kept member visibility on `Profile.small_group`; current normal
  generation and V2 visibility are structure-native as described above.
- BS-AS.2 (audience picker UX, compact scope display, active-list cancelled cleanup) and BS-AS.2A (audience picker accessibility polish) are complete.
- Immediate next step: manual/browser QA of the BS-AS flow after deployment/local migrate, using `docs/BIBLE_STUDY_V2_FLOW_QA_CHECKLIST.md`.
- ServiceEvent / Church Gatherings now reuses the same `ChurchStructureUnit`
  audience-scope foundation as an implemented runtime consumer. Future Community
  Activities should reuse it later and remains deferred pending separate approval.
- Later role-aware editing permissions only if needed.

Checklist V1 remains deferred.

Lighting Pilot remains paused until IA/Bible Study flow stabilizes.
