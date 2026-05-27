# Bible Study V2 Flow QA Checklist

## 1. Purpose

Use this checklist for manual/browser QA after the Bible Study V2 functional chain is in place:

- Bible Study Guides / 查经指引
- Small Group Bible Study Meetings / 小组查经聚会
- Group preparation / 小组方向与问题
- Meeting Roles / 查经聚会同工分工
- Worship Set / 敬拜诗歌安排

This checklist verifies that the current V2 workflow is usable, correctly scoped, bilingual, and compatible with existing V1 Bible Study behavior.

This is not a feature roadmap. Do not use this checklist to justify adding Checklist V1, automatic scheduling, reminders, availability, swap requests, attendance tracking, Community Activities, or role-aware editing permissions.

## 2. Test Accounts Needed

- Staff or superuser account.
- User with Bible Study management capability.
- Regular user in Small Group A, for example Rainbow 4.
- Regular user in Small Group B, for example Rainbow 1.
- Regular user with no small group, if supported by the current test data.
- Optional pastor/coworker role user, if existing permissions support it.
- Optional Chinese-language test user.
- Optional English-language test user.

## 3. Pre-QA Setup Data

Confirm or create:

- At least one `BibleStudySeries`.
- At least one published `BibleStudyLesson` / Bible Study Guide.
- At least one draft `BibleStudyLesson`.
- At least two `SmallGroup` records.
- At least one published `BibleStudyMeeting` for Small Group A.
- At least one published `BibleStudyMeeting` for Small Group B.
- At least one draft meeting.
- At least one cancelled meeting.
- Group direction/questions for one meeting.
- Meeting roles:
  - discussion leader
  - worship lead
  - pianist
  - support
  - host, if useful
- Worship songs:
  - at least two songs with `sort_order`
  - song key
  - YouTube link
  - chord link
  - lyrics link
  - arrangement notes
  - support notes

## 4. Suggested Commands Before Browser QA

Run targeted checks only:

```powershell
$env:PYTHONPATH='C:\dev\bible_reading_v2\env\Lib\site-packages'
python manage.py check
python manage.py test studies accounts -v 2
python manage.py makemigrations --check
python manage.py runserver
```

The full suite remains user-run unless explicitly requested. Do not run the full suite as part of this checklist by default.

## 5. Staff / Manager Flow

Verify staff/manager can:

- Open Staff menu > Content Management > Bible Study Guides / 查经指引.
- List Bible Study Guides.
- Create a Bible Study Guide.
- Edit a Bible Study Guide.
- Publish a Bible Study Guide.
- Soft-cancel a Bible Study Guide if implemented.
- Open guide detail.
- See related Small Group Meetings on guide detail.
- Create a Small Group Meeting under a guide.
- Edit meeting setup fields.
- Soft-cancel a meeting if implemented.
- Open meeting detail.
- Edit group preparation.
- Manage meeting roles.
- Manage worship set.

## 6. Bible Study Guide QA

Verify:

- Guide title displays.
- Scripture reference displays.
- Lesson date / pre-study datetime display.
- Pastor guide displays.
- Global discussion questions display.
- Pre-study notes display.
- Status displays correctly.
- `published_at` behavior appears correct after publishing.
- Chinese label uses 查经指引, not 查经课程.
- English label uses Bible Study Guide / Bible Study Guides, not course wording.

## 7. Small Group Meeting QA

Verify:

- Meeting is linked to the correct parent guide.
- Meeting is linked to the correct `SmallGroup`.
- Meeting date/time displays.
- Location/link displays if present.
- Status displays.
- Parent guide content is visible on meeting detail.
- Group direction displays.
- Group questions display.
- Empty group direction/questions state does not look broken.
- `service_event` is optional and not required.
- Meeting detail does not look like `ServiceEvent` or `TeamAssignment`.

## 8. Group Preparation QA

Verify:

- Manager can edit group direction/questions.
- Form edits only:
  - `group_direction`
  - `group_direction_en`
  - `group_questions`
  - `group_questions_en`
- Form does not allow changing:
  - lesson
  - small group
  - meeting date/time
  - status
  - location
  - meeting link
  - `service_event`
  - worship songs
  - roles
- Regular users cannot access preparation edit page.
- Other-group users cannot edit.
- Chinese labels are natural:
  - 编辑小组查经预备
  - 小组方向
  - 小组讨论问题

## 9. Meeting Roles QA

Verify:

- Manager can open Manage Meeting Roles / 管理聚会同工分工.
- Manager can add role.
- Manager can edit role.
- Manager can delete role.
- Meeting detail displays role section.
- Role labels display naturally:
  - Discussion Leader / 查经带领
  - Worship Lead / 敬拜带领
  - Pianist / 伴奏
  - Support / 配搭
  - Host / 接待
- User field is filtered to active users in the meeting `SmallGroup` if current implementation supports this.
- `display_name` fallback works.
- Normal users can view roles only through a visible parent meeting.
- Normal users do not see manage/edit/delete controls.
- Roles do not create scheduling, rotation, availability, reminder, or swap workflows.

## 10. Worship Set QA

Verify:

- Manager can open Manage Worship Set / 管理敬拜诗歌安排.
- Worship management page shows meeting context.
- Worship management page shows Meeting Roles context only.
- Manager can add worship song.
- Manager can edit worship song.
- Manager can delete worship song.
- Duplicate `sort_order` for the same meeting is rejected or handled gracefully.
- Same `sort_order` for different meetings is allowed if current tests support it.
- Meeting detail displays worship songs in correct order.
- Worship set displays:
  - song title
  - key
  - YouTube link
  - chord link
  - lyrics link
  - arrangement notes
  - support notes
  - worship lead
- Normal users can view worship set only through a visible parent meeting.
- Normal users do not see manage/edit/delete controls.
- No song library behavior appears.
- No worship ministry system behavior appears.
- No auto-sync from Meeting Roles to `worship_lead_user`.
- No worship-lead edit permission is added yet.

## 11. Normal User Flow

For user in Small Group A, verify:

- Can open Bible Study top nav.
- Can access own group published/completed meeting if linked or visible.
- Can view parent Bible Study Guide content.
- Can view own group direction/questions.
- Can view meeting roles.
- Can view worship set.
- Cannot see manager controls.
- Cannot edit guide.
- Cannot edit meeting.
- Cannot edit group preparation.
- Cannot manage roles.
- Cannot manage worship set.

For user in Small Group B, verify:

- Cannot view Small Group A meeting.
- Cannot see Small Group A group preparation.
- Cannot see Small Group A roles.
- Cannot see Small Group A worship set.

For user without small group, verify:

- Behavior is safe and does not crash.
- User does not see group-scoped meeting content unless explicitly allowed.

## 12. Privacy / Permission QA

Verify:

- Draft guide is hidden from regular users if applicable.
- Cancelled guide is hidden from regular users if applicable.
- Draft meeting is hidden from regular users.
- Cancelled meeting is hidden from regular users.
- Other-group meeting is hidden from regular users.
- Staff/manager can see draft/cancelled/all groups.
- Normal users do not see edit/manage controls.
- Hidden group content does not leak through direct URL.
- Worship songs do not leak when parent meeting is hidden.
- Roles do not leak when parent meeting is hidden.

## 13. V1 Compatibility QA

Verify existing V1 still works:

- `/studies/` normal user page still loads.
- V1 `BibleStudySession` list still works.
- V1 `BibleStudySession` detail still works.
- V1 session-level worship songs still work.
- V1 create/edit/session management still works for managers if still intended.
- V1 terminology does not contradict V2 direction.
- V1 is understood as legacy/stabilization behavior, not the future model.

## 14. Navigation / IA QA

Verify:

- Normal user top nav includes Bible Study / 查经.
- Bible Study is not hidden under Daily Reading.
- Daily Reading does not own Bible Study.
- My Serving does not contain Bible Study meeting roles.
- Staff menu keeps Bible Study management under Content Management.
- No top-nav clutter is introduced.
- No Activities top-nav item is added yet.
- No Checklist top-nav item is added.

## 15. Bilingual QA

Verify English and Chinese pages use:

- Bible Study Guides / 查经指引
- New Bible Study Guide / 新增查经指引
- Edit Bible Study Guide / 编辑查经指引
- Small Group Bible Study Meeting / 小组查经聚会
- Group Direction / 小组方向
- Group Discussion Questions / 小组讨论问题
- Meeting Roles / 查经聚会同工分工
- Worship Set / 敬拜诗歌安排
- Arrangement Notes / 编排备注
- Support Notes / 配搭备注

Explicitly check that touched V2 UI does not show:

- 查经课程

## 16. Mobile / Usability QA

Verify:

- Guide list/detail usable on narrow screen.
- Meeting detail readable on mobile.
- Long pastor guide content readable.
- Long group questions readable.
- Role section not cramped.
- Worship links tappable.
- Management forms usable.
- Buttons visually clear.
- Staff pages remain navigable.

## 17. Non-Goals Checklist

Explicitly verify no accidental feature creep:

- No Checklist V1.
- No automatic scheduling.
- No availability matrix.
- No swap request.
- No reminders.
- No attendance tracking.
- No `ServiceEvent` requirement for `BibleStudyMeeting`.
- No Community Activities implementation.
- No full worship song library.
- No worship ministry system.
- No small-group coworker role model.
- No `BibleStudyMeetingRole` as `TeamAssignment`.
- No `SmallGroup` as `MinistryTeam`.
- No Google Docs full-content migration.
- No sensitive/private data import.

## 18. Known Deferred Work

Deferred work includes:

- Role-aware editing permissions.
- Small-group coworker role model.
- Small-group leader/coordinator Bible Study edit permissions.
- V2 normal-user landing page integration if not yet complete.
- V1 compatibility/migration cleanup.
- Optional `ServiceEvent` link behavior.
- Future Community Activities with audience segments.
- Future `ServiceEvent.participating_ministries` / `MinistryContext` planning.
- Checklist V1 after Lighting Pilot validation only.

## 19. Release / Readiness Decision

Bible Study V2 flow can be considered ready for the next UX step only if:

- Staff guide creation works.
- Staff meeting creation works.
- Group preparation display works.
- Roles display works.
- Worship set display works.
- Normal user can view own group content.
- Other groups cannot see private group content.
- Bilingual labels are acceptable.
- V1 `/studies/` still works.
- No scope creep appeared.

Tester decision:

- Pass.
- Pass with minor UI issues.
- Blocked by permission issue.
- Blocked by visibility/privacy issue.
- Blocked by bilingual issue.
- Blocked by V1 compatibility issue.

## 20. Recommended Next Step After QA

After this checklist is manually reviewed, choose one:

A. Fix Bible Study V2 UI/flow issues found in QA.
B. Integrate V2 content into the normal `/studies/` landing page more clearly.
C. Plan narrow role-aware editing permissions.
D. Pause Bible Study V2 and return to Lighting Pilot preflight validation.

Do not automatically proceed to role-aware permissions without browser QA.
