# Bible Study V2 Flow QA Checklist

Manual/browser QA checklist for the complete Bible Study V2 staff-to-normal-user flow after BS-V2.6.6 and the CS-F.2 MinistryContext schedule-scope bridge.

This checklist verifies:

- Bible Study Schedule / 查经安排
- Weekly Bible Study Guide / 每周查经指引
- Small Group Bible Study Meeting / 小组查经聚会
- Group Preparation / 小组查经预备
- Meeting Roles / 查经聚会同工分工
- Worship Set / 敬拜诗歌安排
- Normal `/studies/` V2 landing integration
- V1 internal/direct-route compatibility without visible normal/staff promotion

This is a QA aid only. It is not a feature roadmap and must not be used to expand scope during QA.

## 1. Required Test Accounts And Data

Prepare or identify:

- Staff or superuser account.
- Bible Study manager account with Bible Study management access.
- Normal user in Small Group A.
- Normal user in Small Group B.
- Normal user without a small group.
- MinistryContext CM / Chinese Ministry.
- MinistryContext EM / English Ministry.
- At least one district under CM.
- At least one district under EM.
- At least two active small groups under CM districts.
- At least one active small group under an EM district.
- At least two active small groups.
- At least one inactive small group.
- At least one district with at least one active small group, if district data exists.
- At least one existing V1 `BibleStudySession` record, if available, to verify it is preserved but not visibly promoted.

Recommended QA names:

- Small Group A: `QA Small Group A`
- Small Group B: `QA Small Group B`
- Inactive group: `QA Inactive Small Group`
- CM context: `CM / Chinese Ministry`
- EM context: `EM / English Ministry`
- CM district: `QA CM District`
- EM district: `QA EM District`
- CM groups: `QA CM Small Group A`, `QA CM Small Group B`
- EM group: `QA EM Small Group A`
- District: `QA District`
- Schedule: `QA Spring Bible Study Schedule`
- Weekly guide: `QA Weekly Bible Study Guide`
- V1 session: `QA Legacy Bible Study Session`

## 2. Pre-QA Setup

Create the main happy-path data:

- Create a Bible Study Schedule / 查经安排.
- Set the schedule status to Published or Completed.
- Keep the schedule active.
- Set a date range that includes the weekly guide date.
- Create a Weekly Bible Study Guide / 每周查经指引 under the schedule.
- Set the guide status to Published or Completed.
- Include guide title, scripture reference, pastor guide content, discussion questions, and pre-study notes.
- Generate Small Group Bible Study Meetings / 小组查经聚会 from the weekly guide.
- Publish or complete the generated meetings for Small Group A and Small Group B.
- Add location and/or meeting link to at least one meeting.
- Add group preparation to Small Group A's meeting.
- Add meeting roles to Small Group A's meeting.
- Add worship songs to Small Group A's meeting.

Create hidden-state data:

- One generated or manual meeting left as Draft.
- One generated or manual meeting set to Cancelled.
- One meeting under a Draft guide.
- One meeting under a Cancelled guide, if easy to prepare.
- One meeting under a Draft schedule.
- One meeting under an inactive schedule.
- One meeting for Small Group B with content that should not appear for Small Group A.

Create scope-specific data:

- Whole-church schedule: should target all active small groups.
- MinistryContext schedule for CM: should target only active small groups under CM districts.
- MinistryContext schedule for EM: should target only active small groups under EM districts.
- District schedule: should target only active small groups in the selected district.
- Small-group schedule: should target only the selected active small group.
- Inactive small groups should not be generated from any schedule scope.

## 3. Staff Schedule Management

Verify staff can:

- Open Staff > Bible Study Schedules / 查经安排.
- See only the V2 Bible Study staff items in the visible Staff Bible Study area:
  - Bible Study Schedules / 查经安排
  - Weekly Bible Study Guides / 每周查经指引
  - Small Group Meetings / 小组查经聚会
- Create a Bible Study Schedule / 查经安排.
- Edit schedule title, English title, description, date range, status, and active flag.
- See schedule status labels for Draft, Published, Completed, and Cancelled.
- Open schedule detail.
- See related Weekly Bible Study Guides / 每周查经指引 under the schedule.
- Use the schedule detail action to add a weekly guide under that schedule.
- Confirm schedule detail wording does not imply meeting generation is unavailable if generation is already available from the weekly guide.
- Confirm V1 labels are not visibly promoted in normal/staff navigation:
  - No Legacy Bible Study Sessions.
  - No 旧版查经安排.

## 4. Weekly Guide Creation Under Schedule

Verify staff can:

- Open Staff > Weekly Bible Study Guides / 每周查经指引.
- Filter or select guides by Bible Study Schedule / 查经安排.
- Create a Weekly Bible Study Guide / 每周查经指引 under the schedule.
- Confirm a guide created from schedule detail is pre-associated with that schedule.
- Edit guide title, English title, guide date, scripture reference, guide body, discussion questions, pre-study notes, and status.
- Open guide detail.
- See the parent Bible Study Schedule / 查经安排 context on guide detail.
- See existing Small Group Meetings / 小组查经聚会 for the guide.
- Cancel a guide only when intentionally testing hidden-state behavior.

## 5. Schedule Scope Selection

Verify schedule scope choices:

- Whole Church / 全教会 can be selected without district or small group.
- District / 区 requires a district and does not also allow a small group.
- Small Group / 小组 requires a small group and does not also allow a district.
- Scope labels display correctly in schedule list and detail.
- Active district and active small group options are selectable.
- Existing inactive district/group records, if already attached to an existing schedule, remain reviewable without making inactive options broadly promoted.

Verify generation eligibility:

- Whole-church schedule preview counts all active small groups.
- District schedule preview counts only active small groups in the selected district.
- Small-group schedule preview counts only the selected active small group.
- Inactive small groups are excluded from generation preview/counts.

## 5A. MinistryContext Scope Browser QA

This section is the focused CS-F.2A closure path for MinistryContext-scoped Bible Study Schedules. It verifies the legacy schedule-generation bridge:

```text
MinistryContext -> District -> SmallGroup
```

Historical note: this checklist section predates CS-CORE.2C-B. As of CS-CORE.2C-B, ordinary `/studies/` and v2 `BibleStudyMeeting` visibility moved to active primary `ChurchStructureMembership`; later slices made normal V2 generation structure-native through schedule audience rows, `generation_key`, `anchor_unit`, and meeting audience rows. `Profile.small_group` and the removed `BibleStudyMeeting.small_group` field no longer grant v2 meeting visibility. Legacy `BibleStudySession` app runtime was later retired and remains archive/schema cleanup context.

It must not expand scope into Community Activities, ServiceEvent audience filtering, Checklist V1, scheduling, reminders, attendance, availability, swaps, or role-aware permissions.

### 5A.1 Test Data Setup

Prepare or confirm:

- MinistryContext: `CM / Chinese Ministry`.
- MinistryContext: `EM / English Ministry`.
- At least one District under CM.
- At least one District under EM.
- At least two active SmallGroups under CM districts.
- At least one active SmallGroup under an EM district.
- At least one inactive SmallGroup under CM or EM.
- Normal user with an active primary membership matching a CM meeting's mapped small-group unit.
- Normal user with an active primary membership matching an EM meeting's mapped small-group unit.
- Normal user with no active primary membership.
- Staff or Bible Study manager user.

Record the exact data used:

- CM MinistryContext:
- EM MinistryContext:
- CM District(s):
- EM District(s):
- CM active SmallGroups:
- EM active SmallGroups:
- Inactive SmallGroup:
- CM normal user:
- EM normal user:
- No-small-group user:
- Staff/manager user:

### 5A.2 Staff Schedule Creation QA

Manual steps:

- Log in as staff or Bible Study manager.
- Open Staff > Bible Study Schedules / 查经安排.
- Create a Bible Study Schedule scoped to Whole Church / 全教会.
- Create a Bible Study Schedule scoped to Ministry Context / 事工范围 = CM.
- Create a Bible Study Schedule scoped to Ministry Context / 事工范围 = EM.
- Create a Bible Study Schedule scoped to District / 区.
- Create a Bible Study Schedule scoped to Small Group / 小组.
- Try saving a MinistryContext-scoped schedule with no MinistryContext selected.

Expected:

- Scope fields are understandable.
- MinistryContext field appears only as needed, or remains clearly understandable when shown with other scope fields.
- English and Chinese labels are clear.
- Whole Church, District, and Small Group behavior still makes sense.
- Staff can save a MinistryContext-scoped schedule when a MinistryContext is selected.
- Missing MinistryContext for `ministry_context` scope is rejected.
- No fake Combined Ministry option is required or created.

### 5A.3 Weekly Guide Creation Under MinistryContext Schedule

Manual steps:

- Create a Weekly Bible Study Guide / 每周查经指引 under the CM-scoped schedule.
- Create a Weekly Bible Study Guide / 每周查经指引 under the EM-scoped schedule.
- Publish or complete the schedules and guides as needed for visibility checks.
- Open each guide detail page.

Expected:

- Guide detail shows the parent Bible Study Schedule / 查经安排 clearly.
- Staff can identify the schedule and scope before generating meetings.
- The guide remains church-wide guide content; it does not copy per-group meeting content.

### 5A.4 Meeting Generation Preview And Confirmation

Manual steps for CM:

- Open the CM-scoped weekly guide.
- Open Review Generation Preview / 查看生成预览.
- Verify Eligible Small Groups / 符合范围的小组 count.
- Confirm Generate Missing Meetings / 生成缺少的小组聚会.
- Repeat generation for the same guide.

Expected for CM:

- Only active small groups under CM districts are counted.
- EM small groups are excluded.
- Inactive small groups are excluded.
- Generated meetings default to Draft.
- Generated meetings default to the guide date at 19:30 local timezone.
- Generated meetings link to the weekly guide through `meeting.lesson`.
- Re-running generation is idempotent and does not duplicate meetings.
- Existing meeting location, preparation, status, roles, worship set, and notes are not overwritten.

Repeat equivalent steps for EM:

- Only active small groups under EM districts are counted.
- CM small groups are excluded.
- Inactive small groups are excluded.
- Re-running generation is idempotent.

### 5A.5 Normal `/studies/` Visibility

Manual steps:

- Log in as the CM member user.
- Visit `/studies/`.
- Open the user's own visible meeting, if one is published/completed.
- Log out.
- Log in as the EM member user.
- Visit `/studies/`.
- Open the user's own visible meeting, if one is published/completed.
- Log out.
- Log in as the user with no active primary membership.
- Visit `/studies/`.

Expected:

- CM user sees only their own small group's published/completed current meeting where applicable.
- EM user does not see CM meetings.
- CM user does not see EM meetings.
- User with no active primary membership sees a safe empty state.
- No cross-small-group leakage.
- No cross-MinistryContext leakage.
- Direct URL access to another group's meeting redirects or is denied safely.

### 5A.6 Staff Meeting List And Detail Sanity

Manual steps:

- Staff opens Small Group Meetings / 小组查经聚会.
- Confirm generated CM and EM meetings are distinguishable by schedule, guide, and group.
- Open a generated CM meeting detail page.
- Open a generated EM meeting detail page.

Expected:

- Staff can tell what meeting belongs to what guide, schedule, and group.
- Staff detail page displays enough parent guide/schedule context to understand the meeting.
- No confusing legacy V1 UI is visible.
- Legacy Bible Study Sessions / 旧版查经安排 is not visible in the normal/staff visible Bible Study flow.

### 5A.7 Bilingual UI

Check English and Chinese labels:

- Bible Study Schedule / 查经安排
- Weekly Bible Study Guide / 每周查经指引
- Small Group Meeting / 小组查经聚会
- Ministry Context / 事工范围
- Whole Church / 全教会
- District / 区
- Small Group / 小组

Expected:

- English and Chinese UI are understandable.
- No old confusing Bible Study Admin / 查经管理 label reappears.
- Legacy Bible Study Sessions / 旧版查经安排 is not visible in normal/staff visible UI.

### 5A.8 Mobile QA

Manual steps at mobile width:

- Test staff Bible Study menu.
- Create and edit schedule form.
- Schedule detail.
- Weekly guide detail.
- Meeting generation page.
- Normal `/studies/` landing.

Expected:

- Scope fields are usable.
- Staff dropdown remains usable.
- No horizontal overflow.
- Buttons are reachable.
- Long schedule names and scope labels do not break layout badly.
- MinistryContext names such as `CM / Chinese Ministry` and `EM / English Ministry` wrap acceptably.

### 5A.9 Regression Checks

Quick browser checks:

- Today still loads.
- Reading still loads.
- Prayer still loads.
- My Serving still loads.
- Profile still loads.
- Staff menu still groups correctly.
- Bible Study normal `/studies/` remains V2, not legacy V1.
- Meeting generation for whole church/global still works.
- Meeting generation for district still works.
- Meeting generation for small group still works.

### 5A.10 Go / No-Go Decision

Go if:

- MinistryContext scope generates correct meetings.
- No duplicate generation.
- No cross-context visibility leakage.
- Staff can understand schedule, guide, and meeting relationship.
- Normal users see only appropriate own-group content.
- Bilingual and mobile checks pass.

No-go if:

- CM/EM groups leak across users.
- Inactive groups receive meetings.
- Re-generation duplicates meetings.
- Staff cannot tell which scope generated which meetings.
- Legacy V1 UI reappears visibly.
- Mobile schedule/generation flow is unusable.

Sign-off:

- [ ] Go: pass.
- [ ] Go with minor non-blocking UI issues.
- [ ] No-go: blocked by data setup.
- [ ] No-go: blocked by MinistryContext scope selection.
- [ ] No-go: blocked by meeting generation/idempotency.
- [ ] No-go: blocked by cross-context visibility/privacy.
- [ ] No-go: blocked by staff context clarity.
- [ ] No-go: blocked by bilingual wording.
- [ ] No-go: blocked by mobile usability.

Notes:

- Tester:
- Date:
- Browser/device:
- Desktop viewport tested:
- Mobile viewport tested:
- Language(s) tested:
- CM member user:
- EM member user:
- User without active primary membership:
- Staff/manager user:
- Scope cases tested:
- Blocking issues:
- Minor follow-up issues:
- Go/no-go decision:

## 6. Meeting Generation From Guide/Scope

Verify staff can generate from a weekly guide:

- Open the Weekly Bible Study Guide / 每周查经指引 detail page.
- Find Generate Small Group Meetings / 生成小组查经聚会.
- Review Eligible Small Groups / 符合范围的小组.
- Review Existing Meetings / 已存在的聚会.
- Review Meetings to Create / 将要生成的聚会.
- Open Review Generation Preview / 查看生成预览.
- Confirm preview counts match the schedule scope.
- Submit Generate Missing Meetings / 生成缺少的小组聚会.
- Confirm generated meeting count matches the missing active eligible groups.
- Confirm skipped count matches existing meetings.
- Confirm each eligible active group has no more than one meeting for the guide.

## 7. Generated Meeting Defaults And Idempotency

Verify generated meetings:

- Belong to the weekly guide used for generation.
- Use the small group from the schedule scope eligibility result.
- Default to Draft.
- Use the guide date at 19:30 local timezone.
- Do not copy guide content into meeting fields.
- Continue to display updated guide content through the live `meeting.lesson` relationship after guide edits.
- Do not create `ServiceEvent` records.
- Do not create `TeamAssignment` records.
- Do not auto-create meeting roles.
- Do not auto-create worship songs.
- Do not overwrite existing meeting location, preparation, roles, worship set, status, or notes on repeat generation.
- Skip existing meetings on repeat generation.
- Leave manually edited meetings intact after repeat generation.

## 8. Meeting Detail Display

Verify an accessible meeting detail page displays:

- Small Group Bible Study Meeting / 小组查经聚会 heading.
- Parent Weekly Bible Study Guide / 每周查经指引 title.
- Parent Bible Study Schedule / 查经安排 context.
- Scripture reference.
- Meeting time.
- Small group.
- Status.
- Location, when present.
- Meeting link, when present.
- Pastor guide content from the parent weekly guide.
- Discussion questions from the parent weekly guide.
- Pre-study notes from the parent weekly guide.
- Group Preparation / 小组查经预备.
- Meeting Roles / 查经聚会同工分工.
- Worship Set / 敬拜诗歌安排.

Verify permissions on detail:

- Normal user can read their own published/completed meeting.
- Normal user cannot edit guide content.
- Normal user cannot edit meeting setup.
- Normal user cannot manage meeting roles.
- Normal user cannot manage worship set.
- Staff/manager sees appropriate management links.
- Staff management links remain actions on the meeting flow, not a separate unrelated dashboard.

## 9. Group Preparation

Verify staff or an allowed preparation editor can:

- Open Edit Group Preparation / 编辑小组查经预备 from meeting detail when allowed.
- Save group direction.
- Save English group direction.
- Save group questions.
- Save English group questions.
- Return to meeting detail after saving.
- See saved preparation on meeting detail.

Verify normal user behavior:

- Small Group A user can see Small Group A preparation on their own visible meeting.
- Small Group A user cannot see Small Group B preparation.
- User without a small group cannot see group-scoped preparation content.

## 10. Meeting Roles

Verify staff/manager can:

- Open Manage Meeting Roles / 管理聚会同工分工.
- Add Discussion Leader / 查经带领.
- Add Worship Lead / 敬拜带领.
- Add Pianist / 伴奏, Support / 配搭, or Host / 接待 if useful.
- Select active users from the meeting small group.
- Use display name fallback when no user is selected, if needed.
- Add role notes and English notes.
- Edit an existing role.
- Delete an existing role.
- See roles on meeting detail.

Verify boundaries:

- Meeting roles remain `BibleStudyMeetingRole`, not `TeamAssignment`.
- No automatic coworker rotation is expected.
- No role-aware edit permissions are expected yet.
- Normal users cannot manage roles.

## 11. Worship Set

Verify staff/manager can:

- Open Manage Worship Set / 管理敬拜诗歌安排.
- See existing Meeting Roles / 查经聚会同工分工 context on the worship management page.
- Add a worship song with order, title, English title, key, YouTube link, chord link, lyrics link, arrangement notes, English arrangement notes, support notes, and English support notes.
- Select a worship lead user from the meeting small group.
- Use worship lead name fallback when no user is selected, if needed.
- Edit an existing worship song.
- Delete an existing worship song.
- Confirm duplicate sort order is rejected or handled safely.
- See worship songs ordered correctly on meeting detail.
- Confirm worship links are clickable.

Verify boundaries:

- Worship set remains meeting-level `BibleStudyMeetingWorshipSong`.
- No worship ministry scheduling system is expected.
- No automatic worship assignment is expected.
- Normal users cannot manage worship songs.

## 12. Normal `/studies/` V2 Landing

Verify for a normal user in Small Group A:

- Top navigation Bible Study / 查经 opens `/studies/`.
- Page title shows Bible Studies / 查经安排.
- The first main section shows Current Bible Study / 当前查经.
- The landing shows My Small Group Meeting / 我的小组查经聚会 when a current visible meeting exists.
- The landing card displays Bible Study Schedule / 查经安排.
- The landing card displays Weekly Bible Study Guide / 每周查经指引.
- The landing card displays Scripture / 经文 when present.
- The landing card displays Meeting Time / 聚会时间.
- The landing card displays Small Group / 小组.
- The landing card displays Status / 状态.
- The landing card displays Location / 地点 when present.
- CTA says Open My Group Meeting / 查看我的小组查经聚会.
- CTA opens the V2 meeting detail page.
- Landing page summarizes the current meeting and does not copy the full guide content.
- Staff links, if the user is not staff/manager, are not visible.

Verify for staff/manager:

- `/studies/` still starts with Current Bible Study / 当前查经.
- Staff Links / 同工入口 appears after the normal current Bible Study section.
- Staff links point to V2 schedule, guide, and meeting management pages.
- Staff links do not expose Legacy Bible Study Sessions / 旧版查经安排.

## 13. Visibility And Privacy By Small Group

Verify Small Group A user:

- Sees only Small Group A published/completed meeting under a published/completed guide and active published/completed schedule.
- Does not see Small Group B meeting on `/studies/`.
- Cannot access Small Group B meeting detail by direct URL.
- Cannot see Small Group B group preparation.
- Cannot see Small Group B meeting roles.
- Cannot see Small Group B worship set.

Verify Small Group B user:

- Sees only Small Group B published/completed meeting under a published/completed guide and active published/completed schedule.
- Does not see Small Group A meeting on `/studies/`.
- Cannot access Small Group A meeting detail by direct URL.

Verify user without active primary membership:

- Sees the safe empty state for no visible current Bible Study meeting.
- Does not see any group-scoped meeting content.
- Does not see preparation, roles, or worship set for any group.
- Direct URL access to a group meeting is denied or redirected safely.

Verify hidden states for normal users:

- Draft meetings are hidden.
- Cancelled meetings are hidden.
- Meetings under Draft guides are hidden.
- Meetings under Cancelled guides are hidden.
- Meetings under Draft schedules are hidden.
- Meetings under Cancelled schedules are hidden.
- Meetings under inactive schedules are hidden.
- Meetings under inactive small groups are not generated and are not promoted.
- Empty state says No current Bible Study is available yet.
- Chinese empty state says 目前还没有可见的查经安排。

Verify staff/manager visibility:

- Staff/manager can inspect draft/cancelled meetings from intended staff management pages.
- Staff/manager can filter staff meeting list by status, guide, and small group.
- Staff/manager access does not make draft/cancelled meetings visible to normal users.

## 14. Bilingual UI

Verify expected Chinese labels:

- 查经
- 查经安排
- 每周查经指引
- 小组查经聚会
- 当前查经
- 我的小组查经聚会
- 小组查经预备
- 查经聚会同工分工
- 敬拜诗歌安排
- 全教会
- 区
- 小组
- 生成小组查经聚会
- 查看生成预览
- 生成缺少的小组聚会
- 同工入口

Verify expected English labels:

- Bible Study
- Bible Study Schedule
- Bible Study Schedules
- Weekly Bible Study Guide
- Weekly Bible Study Guides
- Small Group Bible Study Meeting
- Small Group Meetings
- Current Bible Study
- My Small Group Meeting
- Group Preparation
- Meeting Roles
- Worship Set
- Whole Church
- District
- Small Group
- Generate Small Group Meetings
- Review Generation Preview
- Generate Missing Meetings
- Staff Links

Forbidden visible wording in normal/staff visible UI:

- 查经课程
- 查经管理
- 旧版查经安排
- Legacy Bible Study Sessions
- Other Bible Study Sessions
- Series as a main user-facing label

Check both desktop and mobile in Chinese and English where possible.

## 15. Mobile Usability

Verify on a narrow/mobile viewport:

- Top navigation remains usable.
- Staff dropdown remains usable.
- `/studies/` landing is readable.
- Current Bible Study card does not overflow.
- CTA is easy to tap.
- Meeting detail is readable.
- Long guide content wraps cleanly.
- Long discussion questions wrap cleanly.
- Long group preparation wraps cleanly.
- Long role notes wrap cleanly.
- Long worship notes wrap cleanly.
- Worship links are tappable and do not overflow badly.
- Schedule forms remain navigable.
- Guide forms remain navigable.
- Meeting forms remain navigable.
- Role forms remain navigable.
- Worship forms remain navigable.
- Staff tables remain readable or horizontally scrollable without breaking the page.

## 16. Regression Checks

Verify unrelated user areas still work in browser:

- Today page.
- Reading page.
- Bible Study top nav points to `/studies/`.
- Prayer page.
- My Serving page.
- Profile page.
- Language switch, if available in the test environment.

Verify staff areas still work in browser:

- Staff menu opens on desktop.
- Staff menu opens on mobile.
- Staff Content Management links still work.
- Staff Ministry Operations links still work.
- Staff Users and Review links still work.
- Visible Bible Study staff links are V2 links only.

Verify deferred/non-current modules did not appear:

- No Checklist V1 appears in normal top nav.
- No Checklist V1 appears in visible Bible Study staff UI.
- No Community Activities appears in normal top nav.
- No Community Activities appears in visible Bible Study staff UI.
- No Church Structure Foundation implementation UI appears as part of this Bible Study flow.

Verify V1 preservation without visible promotion:

- Existing V1 direct routes, if known, do not crash for authorized staff/direct-route compatibility.
- Existing V1 data is not deleted.
- V1 routes/models/data remain internally preserved.
- V1 is not promoted on `/studies/`.
- V1 is not exposed as Legacy Bible Study Sessions / 旧版查经安排 in normal/staff visible UI.

## 17. Non-Goals During This QA Pass

Do not treat QA findings as permission to implement or expect:

- Checklist V1.
- Community Activities.
- Church Structure Foundation implementation.
- Automatic scheduling.
- Availability matrix.
- Swap requests.
- Reminders.
- Attendance.
- Role-aware permissions.
- Coworker rotation.
- Additional MinistryContext integrations beyond Bible Study Schedule scope.
- Mixed CM/EM audience segment filtering.
- Full ERP behavior.
- Worship ministry scheduling system.
- Small-group coworker role model.
- `BibleStudyMeetingRole` as `TeamAssignment`.
- `SmallGroup` as `MinistryTeam`.
- Automatic `ServiceEvent` creation.
- Destructive V1 migration.

## 18. Go / No-Go Sign-Off

Final QA decision:

- [ ] Go: pass.
- [ ] Go with minor non-blocking UI issues.
- [ ] No-go: blocked by data setup.
- [ ] No-go: blocked by staff workflow issue.
- [ ] No-go: blocked by meeting generation/idempotency issue.
- [ ] No-go: blocked by permission/privacy issue.
- [ ] No-go: blocked by hidden-state visibility issue.
- [ ] No-go: blocked by bilingual wording issue.
- [ ] No-go: blocked by mobile usability issue.
- [ ] No-go: blocked by V1 visibility/preservation issue.
- [ ] No-go: blocked by unrelated navigation/regression issue.

Required sign-off notes:

- Tester:
- Date:
- Browser/device:
- Desktop viewport tested:
- Mobile viewport tested:
- Language(s) tested:
- Staff account used:
- Small Group A user:
- Small Group B user:
- User without active primary membership:
- Data set used:
- Scope cases tested:
- Blocking issues:
- Minor follow-up issues:
- Go/no-go decision:
