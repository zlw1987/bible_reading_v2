# Bible Study V2 Flow QA Checklist

Manual/browser QA checklist for the complete Bible Study V2 flow after BS-V2.6.6.

This checklist verifies the end-to-end user and staff experience for:

- Bible Study Schedule / 查经安排
- Weekly Bible Study Guide / 每周查经指引
- Small Group Bible Study Meeting / 小组查经聚会
- Group Preparation / 小组查经预备
- Meeting Roles / 查经聚会同工分工
- Worship Set / 敬拜诗歌安排
- Normal `/studies/` V2 landing integration

This document is a QA aid only. It is not a feature roadmap and should not be used to expand scope during QA.

## 1. Test Accounts/Data Needed

Prepare or identify:

- Staff or superuser account.
- Bible Study manager account with Bible Study management permission.
- Normal user in Small Group A.
- Normal user in Small Group B.
- Normal user without a small group.
- At least two active small groups.
- At least one inactive small group.
- At least one district, if district data is available.

Recommended naming during manual QA:

- Small Group A: `QA Small Group A`
- Small Group B: `QA Small Group B`
- Inactive group: `QA Inactive Small Group`
- Schedule: `QA Spring Bible Study Schedule`
- Weekly guide: `QA Weekly Bible Study Guide`

## 2. Pre-QA Data Setup

Create or confirm this data before browser QA:

- Create and publish a Bible Study Schedule / 查经安排.
- Set schedule date range, status, and scope.
- Test each schedule scope type as data allows:
  - Whole church.
  - District.
  - Small group.
- Create a Weekly Bible Study Guide / 每周查经指引 under the schedule.
- Include scripture reference, pastor guide content, discussion questions, and pre-study notes.
- Generate Small Group Meetings / 小组查经聚会 from the weekly guide.
- Publish at least one generated meeting for Small Group A.
- Publish at least one generated meeting for Small Group B.
- Leave at least one generated meeting as draft.
- Cancel at least one meeting for visibility testing.
- Add group preparation to one meeting:
  - Group direction.
  - Group questions.
- Add meeting roles:
  - Discussion leader.
  - Worship lead.
  - Pianist, support, or host if useful.
- Add worship songs:
  - Song title.
  - Key.
  - YouTube/chord/lyrics links if available.
  - Arrangement notes.
  - Support notes.

## 3. Staff Flow QA

Verify staff can:

- Open Bible Study Schedules from the Staff menu.
- Create a Bible Study Schedule / 查经安排.
- Edit schedule title, date range, status, and active flag.
- Set schedule scope to whole church.
- Set schedule scope to district.
- Set schedule scope to small group.
- Create a Weekly Bible Study Guide / 每周查经指引 under the schedule.
- Open guide detail.
- See related small-group meetings from guide detail.
- Generate missing small-group meetings from the guide.
- Review generation preview/counts before generation.
- Confirm generation count matches the schedule scope.
- Repeat generation and verify existing meetings are skipped.
- Confirm repeated generation does not overwrite existing meeting content.
- Confirm generated meetings start as draft.
- Confirm no `ServiceEvent` records are auto-created.
- Confirm no `TeamAssignment` records are auto-created.
- Confirm no meeting roles are auto-created.
- Confirm no worship songs are auto-created.

## 4. Normal User `/studies/` QA

Verify for a normal user in Small Group A:

- Top nav Bible Study / 查经 opens `/studies/`.
- `/studies/` shows Current Bible Study / 当前查经.
- User sees only their own Small Group Meeting / 我的小组查经聚会.
- User does not see Small Group B meeting.
- Landing card displays schedule title / 查经安排.
- Landing card displays weekly guide title / 每周查经指引.
- Landing card displays scripture reference / 经文.
- Landing card displays meeting time / 聚会时间.
- Landing card displays small group / 小组.
- Landing card displays status / 状态.
- Landing card displays location / 地点 when present.
- CTA says Open My Group Meeting / 查看我的小组查经聚会.
- CTA opens the existing meeting detail page.
- Landing page does not copy full guide content; full guide content remains on detail.
- Page does not show Legacy Bible Study Sessions.
- Page does not show 旧版查经安排.

Verify empty states:

- User without small group sees: Your profile is not linked to a small group yet.
- User without small group sees: 你的个人资料还没有关联小组。
- User with no current visible meeting sees: No current Bible Study is available yet.
- User with no current visible meeting sees: 目前还没有可见的查经安排。
- Empty states do not crash and do not reveal other groups' meetings.

## 5. Meeting Detail QA

Verify on an accessible meeting detail page:

- Parent Weekly Bible Study Guide title displays.
- Parent schedule context is understandable.
- Scripture reference displays.
- Meeting time displays.
- Small group displays.
- Status displays.
- Location and meeting link display when present.
- Parent weekly guide content displays dynamically from `meeting.lesson`.
- Updating guide content appears on linked meeting detail after refresh.
- Group direction displays.
- Group questions display.
- Meeting roles display.
- Worship set displays.
- Normal user cannot edit guide.
- Normal user cannot edit meeting setup.
- Normal user cannot edit group preparation.
- Normal user cannot manage meeting roles.
- Normal user cannot manage worship set.
- Staff sees appropriate management links.
- Staff management links do not turn the detail page into a separate staff dashboard.

## 6. Privacy QA

Verify normal user visibility:

- Small Group A user cannot see Small Group B meeting on `/studies/`.
- Small Group A user using a direct URL to Small Group B meeting is denied.
- Small Group B user cannot see Small Group A group preparation.
- Small Group B user cannot see Small Group A meeting roles.
- Small Group B user cannot see Small Group A worship set.
- Draft meetings are hidden from normal users.
- Cancelled meetings are hidden from normal users.
- Meetings under draft/unpublished guides are hidden from normal users.
- Meetings under inactive schedules are hidden from the `/studies/` landing.
- Meetings under unpublished schedules are hidden from the `/studies/` landing.
- User without small group does not see group-scoped meeting content.

Verify staff/manager visibility:

- Staff/manager can access appropriate staff management pages.
- Staff/manager can inspect draft/cancelled meetings where intended.
- Staff/manager quick links on `/studies/` are secondary to the normal Current Bible Study section.
- Staff management remains under Staff menu and staff management routes.

## 7. Bilingual QA

Verify Chinese labels:

- 查经安排
- 每周查经指引
- 小组查经聚会
- 当前查经
- 我的小组查经聚会
- 小组查经预备
- 查经聚会同工分工
- 敬拜诗歌安排

Verify English labels:

- Bible Study Schedule
- Weekly Bible Study Guide
- Small Group Bible Study Meeting
- Current Bible Study
- My Small Group Meeting
- Group Preparation
- Meeting Roles
- Worship Set

Forbidden visible wording:

- 查经课程
- 查经管理
- 旧版查经安排
- Legacy Bible Study Sessions
- Series as a main user-facing label

Check both desktop and mobile in Chinese and English where possible.

## 8. Mobile QA

Verify on a narrow/mobile viewport:

- `/studies/` landing is readable.
- Current Bible Study card does not overflow.
- CTA is easy to tap.
- Meeting detail is readable.
- Long guide content wraps cleanly.
- Long discussion questions wrap cleanly.
- Long worship notes wrap cleanly.
- Meeting roles section is readable.
- Worship links are tappable.
- Staff dropdown remains usable.
- Staff forms do not overflow badly.
- Schedule, guide, meeting, role, and worship forms remain navigable.

## 9. Regression QA

Verify unrelated areas still work in browser:

- Today page still works.
- Reading page still works.
- Prayer page still works.
- My Serving still works.
- Profile page still works.
- Staff menu still works.
- Staff Content Management links still work.
- V1 direct routes, if preserved, do not crash.
- V1 data is not deleted.
- V1 models/routes/data remain preserved internally.
- V1/legacy Bible Study UI is not visibly promoted on the normal `/studies/` landing.
- No Checklist V1 appears.
- No Community Activities appears.
- No new top-nav item was introduced for Checklist or Community Activities.

## 10. Non-Goals Reminder

Do not treat QA findings as permission to implement these during this pass:

- No role-aware permissions yet.
- No automatic coworker rotation.
- No availability matrix.
- No swap requests.
- No reminders.
- No attendance.
- No Checklist V1.
- No Community Activities.
- No CM/EM MinistryContext.
- No full ERP.
- No automatic scheduling.
- No worship ministry system.
- No small-group coworker role model.
- No `BibleStudyMeetingRole` as `TeamAssignment`.
- No `SmallGroup` as `MinistryTeam`.
- No destructive V1 migration.

## 11. Go / No-Go Decision

Final QA decision:

- [ ] Pass.
- [ ] Pass with minor UI issues.
- [ ] Blocked by data setup.
- [ ] Blocked by permission/privacy issue.
- [ ] Blocked by bilingual issue.
- [ ] Blocked by mobile usability issue.
- [ ] Blocked by staff workflow issue.

Required sign-off notes:

- Tester:
- Date:
- Browser/device:
- Language tested:
- Data set used:
- Blocking issues:
- Minor follow-up issues:
