# Church Calendar V1 Manual QA Checklist

Status: product-owner manual QA passed in `CHURCH-CALENDAR.1D-B` after
deployment. The recorded pass is the baseline that covers the Calendar V1
limited-trial state after `CHURCH-CALENDAR.1A`, `1B`, `1C`, `1D-A`, `2A`,
`CHURCH-CALENDAR.2A-FU2/FU3`, and the My Serving serving-card template hotfix.
`CHURCH-CALENDAR.2B-QA-CLOSURE` records a second product-owner manual QA pass for
the `CHURCH-CALENDAR.2B` `studies`-owned personal `bible_study_serving` overlay
(grouped under the Bible Study meeting occurrence). That pass also confirmed the
`CHURCH-CALENDAR.2A-FU4` occurrence grouping — ServiceEvent serving grouping still
works and My Serving behavior is unchanged — so both the FU4 grouping checks and
the Bible Study serving checks below are marked passed. This is not a broad
production readiness claim. This checklist adds no product scope.

Use this checklist in local or staging with test records only for future reruns.
Do not run data backfills, cleanup commands, notification jobs, or any `--apply`
command as part of this QA pass.

## Result Summary

- [x] Environment: deployed app after the Calendar and My Serving hotfixes.
- [x] Tester: product owner.
- [x] Date: 2026-07-07.
- [x] Build / commit: deployed state including `CHURCH-CALENDAR.1A`, `1B`,
  `1C`, `1D-A`, `2A`, `CHURCH-CALENDAR.2A-FU2/FU3`, and the serving-card
  template syntax hotfix.
- [x] Overall result: Pass for the Calendar V1 baseline limited-trial /
  product-owner QA (through `2A` / `FU2` / `FU3`).
- [x] Notes: product owner confirmed the required deployed Calendar pass. The
  detailed matrix below remains useful for future regression reruns; this
  closure records the confirmed pass without expanding scope or claiming broad
  production readiness. The `CHURCH-CALENDAR.2A-FU4` occurrence-grouping checks
  were NOT part of this baseline pass; they were subsequently confirmed in
  `CHURCH-CALENDAR.2B-QA-CLOSURE` (see below).

## Result Summary — CHURCH-CALENDAR.2B-QA-CLOSURE

- [x] Environment: deployed app after `CHURCH-CALENDAR.2B-ADAPT` was committed,
  pushed, and deployed.
- [x] Tester: product owner.
- [x] Date: 2026-07-08.
- [x] Build / commit: deployed state including `CHURCH-CALENDAR.2A-FU4` and
  `CHURCH-CALENDAR.2B` (`studies`-owned `bible_study_serving`).
- [x] Overall result: Pass for the `CHURCH-CALENDAR.2B` Bible Study serving
  integration, including the `CHURCH-CALENDAR.2A-FU4` occurrence-grouping
  regression.
- [x] Notes: product owner confirmed a linked-user Bible Study role holder sees
  the grouped serving occurrence; a visible-and-serving user sees one grouped
  occurrence (no meeting + serving duplication); an out-of-audience linked-user
  role holder can open that one meeting's detail for serving but cannot see other
  meetings in that audience without ordinary visibility or an explicit role; the
  Calendar shows no edit/manage/confirm/check-in/attendance/staff controls;
  ServiceEvent serving grouping still works; and My Serving behavior is unchanged.
  This closure records the confirmed pass without expanding scope or claiming
  broad production readiness.

## Product-Owner Confirmed Pass Items (CHURCH-CALENDAR.1D-B)

- [x] `/calendar/` renders normally.
- [x] Month calendar shows real items including Church Gatherings, Bible Study,
  Community Activities, Announcements, and My Serving.
- [x] Calendar day detail works.
- [x] `my_serving` calendar items deep-link to
  `/my-serving/?tab=all#serving-assignment-<TeamAssignmentMember.id>`, targeting
  the viewer's specific existing My Serving assignment card.
- [x] `/my-serving/` works.
- [x] `/my-serving/?tab=past` no longer returns 500.
- [x] The leaked template comment text is gone.
- [x] The serving-card template syntax hotfix is deployed.
- [x] Calendar remains read-only; My Serving keeps its own existing behavior.

## Preconditions

- [ ] The app is running with `church_calendar` enabled.
- [ ] Structure Core has active `ChurchStructureUnit` rows and active primary
  `ChurchStructureMembership` rows for the test accounts.
- [ ] Test accounts exist for: matching ordinary member, nonmatching ordinary
  member, no active membership, ambiguous active primary membership,
  staff/superuser with nonmatching membership, ServiceEvent manager with
  nonmatching membership, Community Activity creator with nonmatching
  membership, and Community Activity co-organizer with nonmatching membership.
- [ ] Test data includes visible and hidden examples for `ServiceEvent`,
  `BibleStudyMeeting`, `Announcement`, and `CommunityActivity`.
- [ ] For the personal serving overlay (`CHURCH-CALENDAR.2A`): one account with
  its own explicit `TeamAssignmentMember` serving row on an in-range,
  non-cancelled ServiceEvent (via an active membership on an active team), and a
  control account that only belongs / matches audience but has no serving row.
- [ ] For the Bible Study serving overlay (`CHURCH-CALENDAR.2B`): one account with
  its own explicit linked `BibleStudyMeetingRole` on an in-range, member-visible
  `BibleStudyMeeting`, a control account that only matches the meeting audience
  but holds no role, and a display-name-only (unlinked) role example.
- [ ] Each source has at least one zero-audience row to confirm fail-closed
  behavior.
- [ ] Browser language or `?lang=en` / `?lang=zh` can be used to check both
  English and Chinese copy.
- [ ] No production or GoDaddy data is being modified.

## Account And Membership Scenarios

- [ ] A matching ordinary member sees only records whose audience rows match
  their current active primary membership unit or an ancestor.
- [ ] A nonmatching ordinary member does not see records for other groups.
- [ ] A user with no active primary membership sees an empty calendar.
- [ ] A user with ambiguous active primary memberships sees an empty calendar.
- [ ] A staff or superuser account with nonmatching membership does not receive
  member-calendar visibility bypass.
- [ ] A ServiceEvent manager/capability holder with nonmatching membership does
  not receive member-calendar visibility bypass.
- [ ] A Community Activity creator with nonmatching membership does not receive
  member-calendar visibility bypass.
- [ ] A Community Activity co-organizer with nonmatching membership does not
  receive member-calendar visibility bypass.

## Month Page Checks

- [ ] `/calendar/` requires login.
- [ ] `/calendar/` defaults to the current local month.
- [ ] `?month=YYYY-MM` opens the requested month.
- [ ] Invalid month parameters fail safely to the current month.
- [ ] Previous, next, and current-month navigation work.
- [ ] The month grid uses local dates, not UTC dates.
- [ ] Type is visible as text plus styling, not color alone.
- [ ] Crowded day cells show an explicit "more" / "更多" link instead of
  silently dropping items.
- [ ] The "more" link opens the complete day detail.
- [ ] Empty month state is honest and bilingual.

## Day Page Checks

- [ ] `/calendar/<year>/<month>/<day>/` requires login.
- [ ] Invalid dates, such as February 30, return a safe 404.
- [ ] Day detail lists all visible timed items for that local date, uncapped.
- [ ] Announcements render in a separate communication section.
- [ ] Empty day state is honest and bilingual.
- [ ] Links go to the owning member-facing detail pages only.
- [ ] No edit, publish, review, assignment, attendance, check-in, staff, or
  management controls appear.

## Source Visibility Checks

- [ ] Published/completed `ServiceEvent` rows with matching audience appear.
- [ ] Draft/cancelled `ServiceEvent` rows stay hidden.
- [ ] Zero-audience `ServiceEvent` rows fail closed.
- [ ] Published `BibleStudyMeeting` rows with matching meeting audience appear.
- [ ] Draft/cancelled meeting, draft lesson, inactive/draft series, and
  zero-audience meeting rows stay hidden.
- [ ] Published active-window `Announcement` rows with matching audience appear,
  including normal and important announcements.
- [ ] Future, expired, archived, zero-audience, and nonmatching announcements
  stay hidden.
- [ ] Published `CommunityActivity` rows with matching audience appear.
- [ ] Draft, pending-review, changes-requested, cancelled, completed,
  zero-audience, and nonmatching activities stay hidden.

## Personal Serving Overlay Checks (CHURCH-CALENDAR.2A)

- [ ] A user with an explicit own `TeamAssignmentMember` row sees their serving
  for the linked ServiceEvent date on the month and day views. (Since
  `CHURCH-CALENDAR.2A-FU4` this renders as part of the grouped ServiceEvent
  occurrence, not a standalone `my_serving` row — see the FU4 checks below.)
- [ ] The serving subitem deep-links to the viewer's own specific My Serving
  assignment card (`/my-serving/?tab=all#serving-assignment-<TeamAssignmentMember.id>`,
  CHURCH-CALENDAR.2A-FU2), and to no generic My Serving page or
  edit/manage/assignment/confirm/attendance/check-in URL. Clicking it lands on
  that specific assignment card.
- [ ] Another user does not see that assignment.
- [ ] A staff/superuser/manager account with no own serving row does not see
  other people's serving items.
- [ ] A user who only belongs / matches audience (no `TeamAssignmentMember` row)
  sees no serving item — belonging/audience/visibility never create serving.
- [ ] A cancelled assignment, a draft/cancelled ServiceEvent, and an inactive
  membership produce no serving item.
- [ ] A multi-day serving event appears on every overlapping local day.
- [ ] Disabling `ministry` removes all serving items and runs no serving query;
  staff status does not bypass this gate. (Disabling `events` also requires
  disabling `ministry`.)
- [ ] The calendar renders no confirm/decline/check-in/attendance/edit/manage
  serving action, and browsing changes no serving data.

## Occurrence Grouping Checks (CHURCH-CALENDAR.2A-FU4)

> Passed: product owner confirmed these grouping regression checks as part of
> `CHURCH-CALENDAR.2B-QA-CLOSURE` (ServiceEvent serving grouping still works).
> They were not part of the `CHURCH-CALENDAR.1D-B` baseline pass.

- [x] A ServiceEvent for which the viewer both sees the base event (audience) and
  has one or more own serving rows appears ONCE on the month grid (one grouped
  occurrence), not once per serving assignment.
- [x] Month grid: with one serving assignment the row shows `<event> · <team>`
  (e.g. `Sunday Worship · Camera Team` / `主日崇拜 · 摄像团队`); with two or more it
  shows `<event> · Serving ×N` / `<event> · 服事 N项`.
- [x] Day detail: the same ServiceEvent shows one card with the base
  title/time/location/type, and the viewer's serving assignments listed
  underneath as subitems (each linking to its My Serving anchor).
- [x] The grouped occurrence header links to the member-facing `ServiceEvent`
  detail (`/events/<id>/`), not an edit/manage/assignment/confirm/attendance/
  check-in URL.
- [x] Month cell "more" compaction counts grouped occurrences, not raw duplicate
  items (a base + two serving rows occupy ONE cell row).
- [x] An assigned server outside the ordinary audience still sees the grouped
  occurrence (SERVING-EVENT-VISIBILITY.1A grants read visibility to that specific
  ServiceEvent detail); a non-assigned non-audience user still sees nothing.
- [x] Two unrelated ServiceEvents sharing a title/time are NOT merged into one
  occurrence (grouping keys on the event id, never on title/time strings).
- [x] Another user, and staff/superuser/manager authority, see the base event but
  never the viewer's serving subitems.

## Bible Study Serving Overlay Checks (CHURCH-CALENDAR.2B) — passed

> Passed: product owner confirmed these Bible Study serving checks in
> `CHURCH-CALENDAR.2B-QA-CLOSURE`. The `bible_study_serving` overlay is grouped
> with the Bible Study meeting occurrence under the `CHURCH-CALENDAR.2A-FU4`
> contract (`occurrence_key = bible_study_meeting:<id>`), so it is not a
> standalone row.

- [x] A user with an explicit own linked `BibleStudyMeetingRole` on an in-range
  meeting sees the serving grouped into that meeting's occurrence on the month
  and day views for the meeting date (not a separate standalone row).
- [x] Month grid: one role shows `<lesson> · <role>` (e.g. `约翰十五章 · 查经带领`);
  two or more roles on one meeting show `<lesson> · Serving ×N` / `<lesson> · 服事 N项`.
- [x] Day detail: one meeting card lists the viewer's Bible Study serving role(s)
  as subitem(s); multiple roles on one meeting do not duplicate the occurrence.
- [x] The grouped occurrence header links to the member-facing Bible Study meeting
  detail (`/studies/meetings/<id>/`), never an edit/manage/confirm/attendance/
  check-in/staff URL.
- [x] A user with an explicit linked role who is OUTSIDE the meeting's ordinary
  audience still sees that meeting occurrence for serving and can open exactly
  that meeting's detail (studies-owned mirror of SERVING-EVENT-VISIBILITY.1A);
  this does not add them to the audience and does not reveal any other meeting.
- [x] A user who only belongs / matches the meeting audience (no linked role)
  sees the meeting but no serving subitem — belonging/audience/meeting visibility
  never create serving.
- [x] A display-name-only (unlinked) role produces no personal serving item.
- [x] Another user, and a staff/superuser/Bible-Study-capability/manager account
  with no own role, see the meeting but never the viewer's serving subitems.
- [x] The ordinary `bible_study_meeting` calendar/list provider remains
  audience-only (a role never widens which meetings appear in the ordinary list).
- [x] A draft/cancelled meeting, draft lesson, and inactive/draft series produce
  no serving item and no serving-based detail read; an in-range completed meeting
  the viewer serves still appears.
- [x] Disabling `studies` removes both Bible Study meeting and Bible Study
  serving items and runs no Bible Study calendar query, and grants no serving-
  based meeting-detail read; staff status does not bypass this gate.
- [x] The calendar renders no confirm/decline/check-in/attendance/edit/manage
  Bible Study serving action, and browsing changes no serving data.

## Date Semantics

- [ ] Multi-day `ServiceEvent` rows appear on every local day they overlap.
- [ ] `ServiceEvent` rows ending exactly at local midnight do not appear on the
  following day.
- [ ] Multi-day `CommunityActivity` rows appear on every local day they overlap.
- [ ] `CommunityActivity` rows ending exactly at local midnight do not appear on
  the following day.
- [ ] Start-only `CommunityActivity` rows appear only on their start date.
- [ ] `BibleStudyMeeting` rows appear only at their meeting date/time; no
  duration is invented.
- [ ] Open-ended active announcements appear across the viewed active range
  without inventing an end date.

## Disabled Module / Gate Checks

- [ ] Disabling `church_calendar` hides the ordinary Calendar nav link.
- [ ] Direct calendar URLs remain login-protected under the current
  surface-gate architecture; this is not a route hard-off.
- [ ] Disabling `events` removes ServiceEvent calendar items.
- [ ] Disabling `studies` removes Bible Study meeting AND Bible Study serving
  (`bible_study_serving`) calendar items.
- [ ] Disabling `announcements` removes announcement calendar items.
- [ ] Disabling `community_events` removes Community Activity calendar items.
- [ ] Disabling `ministry` removes personal serving (`my_serving`) items.
- [ ] Staff status does not bypass disabled-source behavior.
- [ ] Enabling the calendar with no source modules shows a safe empty state.

## Bilingual And Accessibility Checks

- [ ] Month page labels, navigation, type legend, empty state, and "more" link
  are clear in English.
- [ ] Month page labels, navigation, type legend, empty state, and "更多" link
  are clear in Chinese.
- [ ] Day page headings, empty state, announcement copy, and back link are clear
  in English.
- [ ] Day page headings, empty state, announcement copy, and back link are clear
  in Chinese.
- [ ] Keyboard navigation reaches month/day links in a sensible order.
- [ ] Screen-reader-visible type text is present for calendar items.

## Mobile / Responsive Checks

- [ ] Month grid remains usable on a phone-width viewport.
- [ ] Day detail remains readable on a phone-width viewport.
- [ ] Long titles and locations do not overlap adjacent content.
- [ ] Navigation controls remain reachable without horizontal layout breakage
  beyond the intended grid scroll behavior.

## Boundary / Negative Checks

- [ ] Calendar does not show Reading active-plan days, check-ins, reflections,
  progress, or streak content.
- [ ] Calendar does not add, change, or depend on Today cards or item caps.
- [ ] Calendar does not change My Serving behavior (the calendar item remains
  read-only and deep-links to the existing My Serving assignment card via a stable
  anchor id; existing My Serving actions, if any, remain governed by My Serving
  and are unchanged, and the calendar adds/edits/confirms no serving and changes
  no My Serving view logic).
- [ ] Calendar shows only the viewer's own explicit serving
  (`TeamAssignmentMember` and linked `BibleStudyMeetingRole`) and never infers
  serving from membership, audience, or visibility.
- [ ] (`SERVING-EVENT-VISIBILITY.1A`) An explicit team-serving assignment lets the
  assignee open only that one `ServiceEvent` detail (read-only), not other events
  in that audience, and grants no manage/edit/coverage/attendance/check-in. The
  ordinary member-safe calendar/list ServiceEvent visibility stays audience-only
  and is unchanged; a scheduler who assigns — or moves/reactivates an assignment
  onto — an event whose defined audience excludes a linked-user member is warned
  and must acknowledge before saving (`SERVING-EVENT-VISIBILITY.1A-FU1`; no data
  field/migration added; cancelled and zero-audience saves are not nagged). The
  same warning/acknowledgement also applies on the team-schedule scheduler path
  (`SERVING-EVENT-VISIBILITY.1B`, `TeamScheduleAssignmentForm`); the event is
  fixed by the row there, so re-checks happen on create or reactivation.
- [ ] (`CHURCH-CALENDAR.2B`) An explicit linked `BibleStudyMeetingRole` lets the
  assignee open only that one Bible Study meeting detail (read-only), not other
  meetings in that audience, and grants no manage/edit/role-management/attendance/
  check-in. The ordinary member-safe `bible_study_meeting` calendar/list
  visibility stays audience-only and is unchanged (studies-owned mirror of
  SERVING-EVENT-VISIBILITY.1A; no data field/migration added).
- [ ] Calendar does not expose signup, capacity management, attendance, or
  check-in controls.
- [ ] Calendar does not create notifications, reminders, email, push, Google
  Calendar, iCal, or external sync behavior.
- [ ] Calendar does not merge `CommunityActivity` into `ServiceEvent` or create
  any relationship between them.
- [ ] Calendar does not expose staff dashboard behavior.
- [ ] No source records, memberships, signups, assignments, notifications, or
  reading data are mutated while browsing month/day pages.

## Sign-Off

- [x] Product owner confirms all required checks passed for the
  `CHURCH-CALENDAR.1D-B` limited-trial Calendar QA closure.
- [x] Product owner confirms all required `CHURCH-CALENDAR.2B` Bible Study
  serving checks passed (`CHURCH-CALENDAR.2B-QA-CLOSURE`), including the
  `CHURCH-CALENDAR.2A-FU4` occurrence-grouping regression and unchanged My
  Serving behavior.
- [x] No failed checks were reported in the product-owner confirmation above.
- [x] Documentation is updated only after product owner confirmation if the
  status changes from pending to passed.
