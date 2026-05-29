# Bible Study V2 Flow QA Checklist

Manual/browser QA checklist for the complete Bible Study V2 staff-to-normal-user flow after BS-V2.6.6.

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
- At least two active small groups.
- At least one inactive small group.
- At least one district with at least one active small group, if district data exists.
- At least one existing V1 `BibleStudySession` record, if available, to verify it is preserved but not visibly promoted.

Recommended QA names:

- Small Group A: `QA Small Group A`
- Small Group B: `QA Small Group B`
- Inactive group: `QA Inactive Small Group`
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

Verify user without small group:

- Sees the safe empty state: Your profile is not linked to a small group yet.
- Sees the Chinese equivalent in Chinese mode: 你的个人资料还没有关联小组。
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
- MinistryContext.
- CM/EM filtering.
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
- User without small group:
- Data set used:
- Scope cases tested:
- Blocking issues:
- Minor follow-up issues:
- Go/no-go decision:
