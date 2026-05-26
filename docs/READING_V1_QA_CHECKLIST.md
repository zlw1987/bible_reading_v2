# Daily Reading Core V1 QA Checklist

Reference: `docs/ROADMAP_REVISED_PRE_PILOT.md` and `docs/IA_NAVIGATION_REDESIGN_PLAN.md` are the current sources for product boundaries and navigation direction.

## 1. Purpose

This checklist verifies the Daily Reading Core V1 user experience.

It is not a feature roadmap. Use it before deployment and after major changes to confirm the browser flows, bilingual UI, privacy rules, and staff workflows still feel stable.

Daily Reading is one module within a lightweight church spiritual life and ministry workflow system. It owns plans, daily reading, check-in, reading guide, and reflection/comment flow where applicable. It does not own Bible Study, My Serving, Team Assignments, or Ministry Operations.

Automated tests still matter, but manual QA is needed for UI, flow, mobile usability, and bilingual review.

## 2. Test Accounts Needed

- [ ] Regular user with small group
- [ ] Regular user without small group
- [ ] Same-group user
- [ ] Different-group user
- [ ] Staff user
- [ ] User with `CAP_PUBLISH_READING_GUIDES`
- [ ] User without email
- [ ] Optional: pastor role test user
- [ ] Optional: group leader role test user
- [ ] Optional: district leader role test user

Do not record real passwords in this checklist.

## 3. Pre-QA Setup

- [ ] Run migrations only when QA is being performed for an implementation change.
- [ ] Run targeted tests only when QA is being performed for an implementation change.
- [ ] Confirm sample active plan exists.
- [ ] Confirm active plan has an introduction.
- [ ] Confirm active plan has reading days.
- [ ] Confirm active plan has a memory verse.
- [ ] Confirm active plan has structured passages.
- [ ] Confirm active plan has a reading guide post.
- [ ] Confirm active plan has a rest / catch-up day if possible.
- [ ] Confirm at least two small groups exist.
- [ ] Confirm one user is enrolled in active plan.
- [ ] Confirm one user is not enrolled.

Commands:

```powershell
python manage.py check
python manage.py test accounts comments reading prayers -v 2
python manage.py runserver
```

## 4. Authentication / Account Flow

- [ ] Login works.
- [ ] Logout works.
- [ ] Signup works without email.
- [ ] Profile page opens.
- [ ] User can update email.
- [ ] User can update small group.
- [ ] User can update language.
- [ ] User can change password.
- [ ] Staff can reset password for user without email.
- [ ] Forced password change works.

## 5. Navigation

- [ ] Normal user top nav follows the intended structure: Today, Reading, Bible Study, Prayer, My Serving, Profile.
- [ ] Intended Chinese normal user top nav is 今日, 读经, 查经, 代祷, 我的服事, 个人资料.
- [ ] My Serving is independent and not nested under Daily Reading.
- [ ] Bible Study is independent and not nested under Daily Reading.
- [ ] Staff user sees grouped Staff menu.
- [ ] Staff menu includes Plan Admin.
- [ ] Staff menu includes User Admin.
- [ ] Staff menu includes Reflection Reports.
- [ ] Staff menu includes Prayer Reports.
- [ ] Staff menu includes Django Admin.
- [ ] Calendar is not top-nav clutter.
- [ ] Reflection Wall is not top-nav clutter.
- [ ] Group Progress is not top-nav clutter.
- [ ] Chinese nav labels render correctly.
- [ ] English nav labels render correctly.

## 6. Reading Plan Discovery / Enrollment

- [ ] User can see available active plans.
- [ ] User can open plan introduction before joining if active.
- [ ] Inactive plans are not visible to regular non-enrolled users.
- [ ] Staff can view inactive plan intro.
- [ ] Non-enrolled user sees Join Plan button.
- [ ] User can join active plan.
- [ ] Joined plan appears in My Plans.
- [ ] Joined plan appears in Reading / My Plans.
- [ ] Today may show a lightweight reading summary if relevant.
- [ ] User can leave plan if that feature exists.

## 7. Reading Plan Introduction

- [ ] Intro page opens.
- [ ] Plan name displays.
- [ ] Active plan title displays.
- [ ] Overview displays.
- [ ] How to Read displays.
- [ ] Reading Guidance displays.
- [ ] Pastoral / coworker note displays if present.
- [ ] Plan stats show start date.
- [ ] Plan stats show total reading days.
- [ ] Plan stats show calendar length.
- [ ] Plan stats show rest / catch-up days.
- [ ] Plan stats show current day.
- [ ] Enrolled user sees Start Today's Reading if available.
- [ ] Enrolled user sees Listen to Today's Reading if available.
- [ ] Enrolled user sees Calendar.
- [ ] Enrolled user sees Schedule.
- [ ] Enrolled user sees Reading Guides.
- [ ] Non-enrolled user sees Join Plan.
- [ ] Chinese page is fully Chinese.
- [ ] English page is fully English.

## 8. Reading Guides

- [ ] Published guide post visible to regular user.
- [ ] Draft guide post hidden from regular user.
- [ ] Staff can view drafts.
- [ ] User with `CAP_PUBLISH_READING_GUIDES` can view drafts.
- [ ] Authorized user can create guide.
- [ ] Authorized user can edit guide.
- [ ] Authorized user can delete guide.
- [ ] Pinned guide appears before regular guides.
- [ ] General guide type displays correctly.
- [ ] Weekly guide type displays correctly.
- [ ] Daily guide type displays correctly.
- [ ] Chinese labels display correctly.
- [ ] English labels display correctly.

## 9. Today Page

- [ ] Today page loads.
- [ ] Active enrolled plans are shown.
- [ ] Today remains a lightweight summary surface, not a management workflow.
- [ ] Today reading day is shown.
- [ ] Text reading button works.
- [ ] Audio reading button works.
- [ ] Calendar link works.
- [ ] Learn More / Intro link works.
- [ ] If no reading today, page gives clear message.
- [ ] Rest / catch-up day message is clear if applicable.
- [ ] Chinese Today page does not show unintended English.
- [ ] English Today page works.

## 10. Plan Detail / Schedule

- [ ] Plan Detail page loads.
- [ ] Reading schedule is visible.
- [ ] Each reading passage has text reader link.
- [ ] Each reading passage has audio reader link.
- [ ] Memory verse link works.
- [ ] Calendar link works.
- [ ] Plan Introduction link works.
- [ ] Reading Guides link works.
- [ ] Checked days display correctly.
- [ ] Future days behave correctly.
- [ ] Rest / catch-up days display correctly.

## 11. Text Reader

- [ ] Text reader opens from Today.
- [ ] Text reader opens from Plan Detail.
- [ ] Text iframe loads.
- [ ] Chinese / English scripture tab works.
- [ ] Previous / Next passage navigation works.
- [ ] Next button stays in text reader path.
- [ ] Reflection/comment section appears.
- [ ] Check-in appears only at correct completion point.
- [ ] Future day cannot be checked in.
- [ ] User can check in after finishing.
- [ ] After check-in, page shows checked state.

## 12. Audio Reader

- [ ] Audio reader opens from Today.
- [ ] Audio reader opens from Plan Detail.
- [ ] Audio iframe loads.
- [ ] Audio reader does not show text iframe.
- [ ] Previous / Next passage navigation works.
- [ ] Next button stays in audio reader path.
- [ ] Reflection/comment section appears.
- [ ] Check-in flow works the same as text reader.
- [ ] After check-in, calendar and progress update.

## 13. Reading Calendar

- [ ] Calendar page opens.
- [ ] Current month displays.
- [ ] Previous / Next month navigation works.
- [ ] Back to current month works.
- [ ] Legend is color-coded for checked.
- [ ] Legend is color-coded for missing.
- [ ] Legend is color-coded for rest / catch-up.
- [ ] Legend is color-coded for future.
- [ ] Legend is color-coded for today.
- [ ] Today is highlighted.
- [ ] Checked day has correct color.
- [ ] Missing past day has correct color.
- [ ] Rest / catch-up day has correct color.
- [ ] Future day has correct color.
- [ ] Read link works.
- [ ] Audio link works.
- [ ] Mobile / narrow width remains usable.

## 14. Check-in / Progress

- [ ] Check-in creates exactly one check-in per user / active plan / day.
- [ ] Repeated check-in does not duplicate.
- [ ] Progress percentage updates.
- [ ] My Plans progress updates.
- [ ] Group progress includes checked user.
- [ ] Group progress does not expose unrelated group data.
- [ ] Regular user sees own group progress.
- [ ] Group leader scoped access works.
- [ ] District leader scoped access works.
- [ ] Staff can view all groups.

## 15. Reflection / Comments

- [ ] User can post new reflection.
- [ ] User can choose Private.
- [ ] User can choose My Group.
- [ ] User can choose Reflection Wall.
- [ ] User can post anonymously.
- [ ] User can reply to own reflection.
- [ ] User can reply to another visible reflection.
- [ ] Reply inherits parent visibility.
- [ ] Reply form is collapsed or visually natural.
- [ ] User can edit own reflection.
- [ ] User can edit own reply.
- [ ] User can delete own reflection/reply.
- [ ] Staff can delete inappropriate reflection/reply.
- [ ] Existing comments display in a natural thread.
- [ ] My Past Reflections display.
- [ ] Chinese labels are correct.
- [ ] English labels are correct.

## 16. Reflection Visibility / Privacy

- [ ] Private reflection visible only to author and staff.
- [ ] Group reflection visible to same group.
- [ ] Group reflection hidden from different group.
- [ ] Reflection Wall reflection visible to logged-in users who can access.
- [ ] Anonymous reflection hides author from regular users.
- [ ] Anonymous reflection reveals author to staff.
- [ ] Hidden reflection hidden from other regular users.
- [ ] Hidden reflection visible to author with hidden badge.
- [ ] Hidden reflection visible to staff.

## 17. Reflection Wall

- [ ] Reflection Wall opens from reader.
- [ ] Page title says Reflection Wall / 默想墙.
- [ ] Page does not say Passage Wall / 经文墙.
- [ ] My Past tab works.
- [ ] My Group tab works.
- [ ] Reflection Wall tab works.
- [ ] Hidden/private/group-scoped data does not leak.
- [ ] Report link works for other users.
- [ ] Author cannot report own reflection.

## 18. Reflection Moderation

- [ ] User can report visible reflection.
- [ ] Duplicate report does not create duplicate row.
- [ ] Staff can open Reflection Reports.
- [ ] Staff can search/filter reports.
- [ ] Staff can hide reflection.
- [ ] Staff can unhide reflection.
- [ ] Staff can mark reports reviewed.
- [ ] Staff can dismiss reports.
- [ ] Hidden reflection behavior is correct after moderation.

## 19. Staff Reading Plan Editor

- [ ] Staff can open plan admin.
- [ ] Header fields save separately.
- [ ] Introduction/guidance/pastoral note fields save.
- [ ] Line-level reading day save works.
- [ ] Adding a reading day works.
- [ ] Editing `reading_text` syncs structured passages.
- [ ] Editing `memory_verse` syncs structured memory passages.
- [ ] Save does not trigger "too many modify" issue.
- [ ] Non-staff cannot access staff editor.

## 20. Structured Passages

- [ ] Existing plans can sync structured passages.
- [ ] Text reader uses structured passage if available.
- [ ] Audio reader uses structured passage if available.
- [ ] Fallback parser still works if structured passage missing.
- [ ] Reflection key stays stable.
- [ ] Memory verse reader works.

## 21. Bilingual Review

- [ ] Switch language to Chinese.
- [ ] Review Today.
- [ ] Review My Plans.
- [ ] Review Plan Intro.
- [ ] Review Calendar.
- [ ] Review Text Reader.
- [ ] Review Audio Reader.
- [ ] Review Reflection Wall.
- [ ] Review Group Progress.
- [ ] Review Profile.
- [ ] Chinese UI does not show targeted English leftover: Passage Wall.
- [ ] Chinese UI does not show targeted English leftover: Share your reflection.
- [ ] Chinese UI does not show targeted English leftover: Post anonymously.
- [ ] Chinese UI does not show targeted English leftover: Reply anonymously.
- [ ] Chinese UI does not show targeted English leftover: Prayer title on reading pages.
- [ ] Switch language to English and verify English UI.

## 22. Mobile / Elder Usability

- [ ] Top nav usable on narrow screen.
- [ ] Calendar horizontally scrolls or remains readable.
- [ ] Text/audio buttons are tappable.
- [ ] Audio icon is clear.
- [ ] Forms are not too cramped.
- [ ] Reflection reply UI is not overwhelming.
- [ ] Font size is readable.
- [ ] Buttons are visually distinct.

## 23. Known Non-Goals for Reading V1

- [ ] Bible Study schedule is not part of Daily Reading.
- [ ] Worship songs are not part of Daily Reading.
- [ ] Ministry team scheduling is not part of Daily Reading.
- [ ] Lighting team operations are not part of Daily Reading.
- [ ] Team Assignments are not part of Daily Reading.
- [ ] My Serving is not part of Daily Reading.
- [ ] Automatic reminders are not required for Reading V1.
- [ ] Native Bible text storage is not required for Reading V1.
- [ ] Full offline support is not required for Reading V1.

## 24. Release Readiness Decision

- [ ] All automated tests pass.
- [ ] Manual QA critical flows pass.
- [ ] No privacy leakage found.
- [ ] Bilingual review passes.
- [ ] Staff flows pass.
- [ ] Mobile basic review passes.
- [ ] Known issues documented.
- [ ] Daily Reading V1 can be considered closed/stable.

## 25. Next Phase

After Reading V1 closure, future planning should follow the revised roadmap: IA/navigation reset, V1 stabilization, then Bible Study V2 planning and implementation.

Do not begin:
- [ ] Lighting Team scheduling
- [ ] My Serving or Ministry Operations inside Daily Reading
- [ ] Full ServiceEvent expansion

from the Daily Reading track. Bible Study V1 exists, but future Bible Study planning is superseded by the Bible Study V2 group meeting model direction.
