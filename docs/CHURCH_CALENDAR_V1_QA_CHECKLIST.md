# Church Calendar V1 Manual QA Checklist

Status: prepared in `CHURCH-CALENDAR.1D-A` as an unchecked, pending product
owner checklist, and extended in `CHURCH-CALENDAR.2A` with the personal serving
overlay checks below. Manual QA has not passed yet. Calendar V1 remains limited
trial / not QA-passed until the product owner explicitly confirms this checklist
was run and passed. This checklist adds no product scope.

Use this checklist in local or staging with test records only. Do not run data
backfills, cleanup commands, notification jobs, or any `--apply` command as part
of this QA pass.

## Result Summary

- [ ] Environment:
- [ ] Tester:
- [ ] Date:
- [ ] Build / commit:
- [ ] Overall result: Pending / Pass / Fail
- [ ] Notes:

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

- [ ] A user with an explicit own `TeamAssignmentMember` row sees a "My Serving"
  / "我的服事" item on the month and day views for the linked ServiceEvent date.
- [ ] The serving item links to the My Serving page and to no
  edit/manage/assignment/confirm/attendance/check-in URL.
- [ ] The serving item carries the bilingual "My Serving" / "我的服事" type label
  and its own distinct dot/border color (type is text plus styling, not color
  alone), and month cells keep the existing "more" compaction behavior.
- [ ] Another user does not see that assignment.
- [ ] A staff/superuser/manager account with no own serving row does not see
  other people's serving items.
- [ ] A user who only belongs / matches audience (no `TeamAssignmentMember` row)
  sees no serving item — belonging/audience/visibility never create serving.
- [ ] A cancelled assignment, a draft/cancelled ServiceEvent, and an inactive
  membership produce no serving item.
- [ ] A multi-day serving event appears on every overlapping local day; two
  teams at one event appear as two distinct serving items.
- [ ] Disabling `ministry` removes all serving items and runs no serving query;
  staff status does not bypass this gate. (Disabling `events` also requires
  disabling `ministry`.)
- [ ] Bible Study linked-user serving roles are intentionally NOT shown yet
  (documented follow-up); their absence is expected, not a defect.
- [ ] The calendar renders no confirm/decline/check-in/attendance/edit/manage
  serving action, and browsing changes no serving data.

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
- [ ] Disabling `studies` removes Bible Study meeting calendar items.
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
- [ ] Calendar does not change My Serving behavior (it may link to the My
  Serving page read-only, but adds/edits/confirms no serving there).
- [ ] Calendar shows only the viewer's own explicit `TeamAssignmentMember`
  serving and never infers serving from membership, audience, or visibility.
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

- [ ] Product owner confirms all required checks passed.
- [ ] Any failed checks are recorded with reproduction steps.
- [ ] Documentation is updated only after product owner confirmation if the
  status changes from pending to passed.
