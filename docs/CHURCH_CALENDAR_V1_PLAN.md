# Church Calendar V1 Plan

Status: `CHURCH-CALENDAR.0A` approved this bounded plan,
`CHURCH-CALENDAR.1A` implemented the model-free read-only foundation,
`CHURCH-CALENDAR.1B` added the four member-safe source range providers and
their visibility adapters, and `CHURCH-CALENDAR.1C` implemented the final
member-facing month grid and day detail UI (July 2026).
`CHURCH-CALENDAR.1D-A` prepared closure coverage/docs and the manual QA
checklist. `CHURCH-CALENDAR.2A` adds the signed-in user's own explicit serving
schedule as a read-only personal `my_serving` overlay (see Section 10), followed
by `CHURCH-CALENDAR.2A-FU2/FU3` and the My Serving serving-card template hotfix.
`CHURCH-CALENDAR.1D-B` records the product-owner manual QA pass after
deployment. Calendar V1 is QA-passed for limited trial/current-state use; this
is not a broad production-readiness claim.

## 1. Purpose and product boundary

Church Calendar / 教会日历 is a new independent, read-only, member-facing
surface for discovering church-life information across a date range. It fills
the deliberate gap left by Today: Today stays a low-noise agenda and action
center, while the calendar makes every currently member-visible, audience-
matching item in the selected range discoverable.

V1 aggregates four existing source types:

- Bible Study V2 `BibleStudyMeeting`;
- Church Gatherings `ServiceEvent`;
- Official Announcements `Announcement`; and
- Community Activities `CommunityActivity`.

The calendar does not own or copy those records. Each source module keeps its
own lifecycle, audience rows, detail page, bilingual display behavior, and
permission rules. Calendar rows link to the owning member-facing detail
surface and create no cross-module relationship.

Today is unchanged. The calendar must not reuse Today's item caps, signup-only
Community Activity rule, Important-only Announcement rule, action-center
items, serving notes, or manager summaries. It may follow the architectural
pattern of explicitly registered module-owned providers, but it is a separate
range-based aggregation surface.

## 2. V1 non-goals

Calendar V1 is not:

- the existing Daily Reading active-plan calendar;
- a reading-plan progress or check-in surface;
- an event, announcement, activity, or meeting authoring surface;
- a serving *management* surface or a source/writer of `TeamAssignment`,
  `TeamAssignmentMember`, or `BibleStudyMeetingRole` rows. (`CHURCH-CALENDAR.2A`
  adds a read-only personal `my_serving` overlay of the viewer's *own* explicit
  `TeamAssignmentMember` serving, but it never creates, edits, confirms, or
  otherwise mutates serving, and never infers serving from membership/audience;
  see Section 10.);
- an attendance, signup, check-in, or capacity-management surface;
- a notification, reminder, email, or push system;
- Google Calendar, iCal, or other external-calendar synchronization;
- a staff dashboard, management queue, coverage dashboard, or setup report;
- a merger of Community Activities and `ServiceEvent`; or
- authorization to change Today, My Serving, source lifecycles, audience
  semantics, or module route-hard-off behavior.

The existing `active_plan_calendar` route at
`/plans/<active_plan_id>/calendar/` remains reading-owned and separate.
Calendar V1 must not query reading-plan days, reading check-ins, reflection
data, streaks, or active-plan enrollment.

## 3. Proposed ownership and routes

The implementation should use a small independent `church_calendar` Django
app and registry key, with no V1 database models or migrations. Its only state
is request parameters and normalized provider output.

Proposed authenticated member routes:

- `/calendar/` (`church_calendar_month`) — current month by default, with a
  validated `?month=YYYY-MM` selector; and
- `/calendar/<year>/<month>/<day>/` (`church_calendar_day`) — one local-date
  detail page.

Both routes are read-only and `login_required`. They expose member-facing
links only. They must not expose edit, publish, review, assignment, attendance,
or staff-management controls.

## 4. Range-provider architecture

Use a range-based provider registry modeled after Today's explicit provider
architecture, without calling the Today providers themselves:

1. a small shared registry accepts one provider per source module;
2. each source module owns its calendar adapter, query, lifecycle filtering,
   member-safe visibility, and normalized item construction;
3. one explicit registration site wires providers in a deterministic order;
4. the calendar aggregator calls providers only for enabled source modules;
5. providers receive the signed-in user and an aware, half-open local-time
   range `[range_start, range_end)`; and
6. the aggregator validates item type, source identity, datetime range, detail
   URL, and provider ownership before sorting or grouping.

The registry is an internal contract, not a plugin-discovery framework. It
must not make source modules import one another. A source provider failure
must not silently replace member visibility with an unfiltered queryset.

Each normalized item should carry only presentation data needed by the
calendar, such as:

- `item_type`;
- stable source identity, unique as `(item_type, source_id)`;
- localized title;
- start datetime and optional end datetime;
- optional localized location;
- owning member-detail URL; and
- a display mode distinguishing timed events from active-window
  communication.

No normalized calendar item is stored. V1 performs no cross-source merge or
deduplication. In particular, `CommunityActivity` must never be converted,
linked, or merged into `ServiceEvent`. A linked Bible Study meeting and
ServiceEvent must each pass its own member-safe visibility rule; visibility of
one must never imply visibility of the other.

## 5. Item taxonomy and date semantics

The exact V1 item types are:

| `item_type` | Source | Calendar date behavior |
|---|---|---|
| `service_event` | `ServiceEvent` | Timed item using `start_datetime` and the existing effective-end rule. Include it on every local day its interval overlaps. |
| `bible_study_meeting` | `BibleStudyMeeting` | Timed point anchored to the local date of `meeting_datetime`; V1 must not invent a duration. |
| `announcement` | `Announcement` | Active-window communication, not a true event. Show it as active communication on each displayed day its currently visible publish window overlaps. |
| `community_activity` | `CommunityActivity` | Timed item using `start_datetime` and `end_datetime` when present. A start-only activity belongs to its start date; a ranged activity appears on every overlapping local day. |
| `my_serving` | `TeamAssignmentMember` (via `ServiceEvent`) | `CHURCH-CALENDAR.2A` personal, read-only overlay of the *viewer's own* explicit team-assignment serving. Timed item anchored to the linked `ServiceEvent` `start_datetime` with the existing effective-end overlap rule (multi-day events appear on every overlapping day). Owned by the `ministry` module; serving is explicit only and never inferred from membership/audience/visibility. `CHURCH-CALENDAR.2A-FU2`: the item deep-links to the viewer's own specific My Serving assignment card (`/my-serving/?tab=all#serving-assignment-<TeamAssignmentMember.id>`), not the generic My Serving page and not the ServiceEvent detail (serving does not grant event visibility). |

Range overlap uses aware datetimes in the configured local timezone and
half-open boundaries. Day grouping uses local dates, not UTC dates.

### Announcement behavior

Announcements must remain visually and semantically distinct from events:

- use the existing publication window, not a fabricated event date;
- include only announcements that are member-visible at request time;
- do not expose scheduled announcements before `publish_start`;
- do not show expired or archived announcements merely because the user is
  viewing a historical date;
- intersect each currently visible announcement's active window with the
  requested calendar range;
- treat `publish_end=None` as active through the requested range, without
  storing or inventing an end date;
- show both normal and important announcements—the calendar does not inherit
  Today's Important-only cap; and
- label or style them as active communication rather than placing them among
  timed appointments.

## 6. Member-safe visibility is mandatory

Calendar visibility means the signed-in viewer's current ordinary
audience/belonging visibility. It does not mean everything the same account
may manage as staff, superuser, creator, co-organizer, or capability holder.
A staff user viewing the member calendar must satisfy the same lifecycle,
active-window, audience-row, and active-primary-membership rules as any other
member.

The provider layer must expose or add member-safe helpers/adapters for every
source:

| Source | Required calendar visibility contract |
|---|---|
| `ServiceEvent` | Add a member-safe range helper that excludes draft/cancelled states, requires the ordinary published/completed lifecycle, requires audience rows, and matches those rows through current active primary membership. Do not use `get_visible_service_events`, `ServiceEvent.can_be_seen_by`, or `can_manage_service_events` as the final calendar authority because they allow management bypass. |
| `BibleStudyMeeting` | Add a member-safe range helper that applies the ordinary meeting/lesson/series lifecycle gates plus meeting audience-row matching through current active primary membership. Do not use `BibleStudyMeeting.can_be_seen_by` as the final calendar authority because staff/capability holders bypass its member gates. |
| `Announcement` | Reuse `member_visible_announcements_for`, not `visible_announcements_for`. Evaluate it at request time, then intersect the returned active windows with the requested range. |
| `CommunityActivity` | Add a member-safe helper that includes published, audience-matching activities only. Do not use `visible_community_activities_for` or `CommunityActivity.can_be_seen_by` as the final calendar authority because staff/superuser, creator, and co-organizer paths can see management/pre-publication records. |

All four adapters must fail closed for unauthenticated users, absent or
ambiguous current active primary membership, zero audience rows, and
nonmatching audience. Calendar code must not reconstruct historical
membership or use the viewed date as permission to expose content the user
cannot see under their current belonging.

Audience visibility remains visibility only. It never creates serving,
leadership, staff authority, signup, attendance, or a personal action.

## 7. Month grid and day detail

### Month grid

The month page is the overview and navigation surface:

- render a conventional local-date month grid with previous/next month
  navigation and a Today shortcut;
- distinguish the calendar item types with bilingual labels and accessible text,
  not color alone;
- group timed items by day and show announcements as active communication;
- keep every returned item discoverable—if a cell uses a visual compacting
  rule, it must show an explicit “more” link/count to that day's complete
  detail rather than silently dropping rows; and
- do not apply Today's per-type limits or relevance filters.

### Day detail

The day page is the complete, uncapped read-only list for one local date:

- show every member-safe item whose interval or active window overlaps that
  date;
- keep active announcements in a separate communication section;
- sort timed items by local start time, then deterministic type/source keys;
- show localized title, time/window, optional location, type label, and a
  link to the owning member detail page;
- show an honest bilingual empty state when no enabled source contributes an
  item; and
- provide no inline write, serving, attendance, review, or staff actions.

## 8. Module enablement

`church_calendar` should be a registered, default-enabled, navigation-
contributing module that requires structure Core and does not contribute to
Today. It should not declare hard dependencies on all four source modules:
the calendar remains valid when any subset is enabled.

Enablement behavior:

- disabling `church_calendar` hides its ordinary navigation entry and any
  future shared discovery link;
- under the current surface-gate architecture, direct calendar URLs remain
  login-protected rather than becoming route hard-off; adding route hard-off
  requires a separate approved change;
- disabling a source module means the calendar does not call that module's
  provider, does not query its tables, and shows no items of that type;
- enabling the calendar with no source modules produces a safe empty state;
  and
- source-module enablement must not be bypassed by staff status.

The calendar must not register the `reading` module as a source. The existing
reading calendar remains discoverable only through the reading product.

## 9. Required implementation coverage

Future implementation tests should prove:

- month and day routes require authentication and use local dates;
- invalid month/date parameters fail safely;
- each exact taxonomy value normalizes, sorts, and links correctly;
- multi-day ServiceEvents and Community Activities appear on every
  overlapping day without duplicate identity within a day;
- Bible Study meetings stay point-in-time items;
- active, open-ended, future, expired, archived, normal, and important
  Announcement behavior follows Section 5;
- ordinary matching and nonmatching members are isolated for every source;
- zero-audience and absent/ambiguous-membership records fail closed;
- staff, superuser, manager-capability, creator, and co-organizer accounts do
  not receive calendar visibility bypasses;
- disabled source providers are not called and perform no queries;
- calendar disablement follows the documented surface gate;
- every day-detail item is discoverable from the month view;
- no Today behavior change, no My Serving behavior mutation, no serving
  inference/mutation/action state, and no attendance, signup, notification,
  reading check-in, or other action state is created or changed; and
- query counts remain bounded across a month range.

## 10. Separately approvable implementation slices

### CHURCH-CALENDAR.1A — Read-only foundation

Complete. Adds the model-free `church_calendar` app, registry metadata and
default enablement, module-gated bilingual navigation, authenticated month/day
route skeletons, basic templates and safe empty states, local-date range
helpers, bilingual taxonomy labels, and the normalized `CalendarItem`
range-provider registry/aggregator contract. The registry intentionally has no
real source providers: no `ServiceEvent`, `BibleStudyMeeting`, `Announcement`,
`CommunityActivity`, or Reading data is queried. No model, migration, data
write, Today or My Serving change, notification, serving, attendance/check-in,
external-calendar sync, or CommunityActivity-to-ServiceEvent relationship was
added.

### CHURCH-CALENDAR.1B — Provider/source integration

Complete. Adds the four module-owned range providers
(`events.calendar_provider`, `studies.calendar_provider`,
`announcements.calendar_provider`, `community_events.calendar_provider`) and
the required member-safe visibility helpers/adapters
(`events.visibility.member_visible_service_events_for`,
`studies.visibility.member_visible_meetings_for`, the reused
`announcements.visibility.member_visible_announcements_for`, and
`community_events.visibility.member_visible_community_activities_for`). The
single explicit registration site is `church_calendar.registration`
(invoked from `ChurchCalendarConfig.ready()`), wiring the providers in the
deterministic order events → studies → announcements → community_events; there
is no app auto-discovery and no source module imports another source module.
Source-module enablement is enforced by the existing aggregator (disabled
sources are not called and run no query, and staff status does not bypass
disablement). Each adapter grants no staff/superuser/creator/co-organizer/
capability bypass and fails closed for unauthenticated users, absent/ambiguous
active primary membership, zero audience rows, and nonmatching audience.
Returns normalized `CalendarItem` values only; no source model, migration,
lifecycle workflow, Today, My Serving, serving, signup, attendance,
notification, external sync, or CommunityActivity-to-ServiceEvent relationship
was added. The final month/day presentation is still 1A's minimal skeleton (1C
delivers the full UI).

### CHURCH-CALENDAR.1C — Month/day UI

Complete. Implements the bilingual responsive month grid and complete day
detail on top of the 1B providers. The month view buckets member-safe items
into local-date cells (half-open overlap, so a boundary-only following day is
excluded), shows multi-day ServiceEvents / Community Activities on every
overlapping day, keeps Bible Study meetings point-in-time, treats active-window
announcements as active communication, highlights today, distinguishes
out-of-month cells, and compacts crowded cells behind an explicit bilingual
"more" link to the day detail (never silently dropping an item). The day view
lists the complete uncapped set for one local date, splitting timed items
(ServiceEvent / BibleStudyMeeting / CommunityActivity, sorted by local start
then type/source) from active announcements (sorted by publish start then id),
with localized title, type label, honest time/window text (no fabricated Bible
Study duration, no invented open-ended announcement end), optional location,
and owning member-facing detail links. Presentation-only arrangement lives in
`church_calendar.presentation`; it never queries a source, re-checks
visibility, or mutates a `CalendarItem`. Type is conveyed by a colored dot plus
a text label / legend and per-cell screen-reader type text (not color alone),
and the grid stays usable on mobile. No edit/publish/review/assignment/
attendance/staff-management control is rendered, and no Today, My Serving,
serving, source model, migration, or data write was added.

### CHURCH-CALENDAR.1D-A — Closure-prep tests/docs and QA checklist

Prepared. Reviewed existing route, provider, visibility, enablement, local-date,
accessibility, read-only, and cross-product regression coverage against this
plan; added only the missing focused co-organizer member-calendar bypass
regression test. Created the initially unchecked manual QA checklist at
[`CHURCH_CALENDAR_V1_QA_CHECKLIST.md`](CHURCH_CALENDAR_V1_QA_CHECKLIST.md) and
updated current-state docs to record that 1A/1B/1C were implemented while
manual QA still awaited product-owner confirmation. `CHURCH-CALENDAR.1D-B`
later records that confirmation. This closure-prep slice added no new product
feature scope, model, migration, data write, provider visibility expansion,
Today, My Serving, serving, signup, attendance/check-in, notification, external
sync, staff dashboard, Reading active-plan calendar/check-in, route hard-off,
broad UI redesign, or CommunityActivity-to-ServiceEvent relationship.

### CHURCH-CALENDAR.2A — Personal serving overlay

Implemented and included in the `CHURCH-CALENDAR.1D-B` product-owner QA pass.
Adds the signed-in user's own explicit serving schedule to the calendar as a new
read-only personal item type
(`my_serving` / "My Serving" / "我的服事"). This is an approved expansion after
1A/1B/1C/1D-A; it is not itself 1D QA closure.

Ownership and boundary:

- The provider is owned by the `ministry` module (`ministry.calendar_provider`)
  and registered at the existing single explicit registration site
  (`church_calendar.registration`) after the four source providers. Like every
  provider it is gated by its own module's enablement: when `ministry` is
  disabled the aggregator does not call it and runs no serving query, and staff
  status never bypasses that gate. `ministry` already depends on `events`, so
  the provider reads only `events` (a declared dependency) plus its own app and
  imports no sibling source module.
- Serving is **explicit**. An item is produced only from the viewer's own
  `TeamAssignmentMember` rows, reusing the current My Serving selector
  (`ministry.views.my_serving_assignments`, `tab="all"`): active membership on
  an active team, the assignment not cancelled, and the ServiceEvent not
  draft/cancelled. Serving is never inferred from `ChurchStructureMembership`
  (belonging), audience scopes, event/meeting visibility, or
  staff/superuser/manager authority, and only the viewer's own serving is shown.
- The item is a **timed** item anchored to the ServiceEvent `start_datetime`
  with the existing effective-end overlap rule, so a multi-day event appears on
  every day it covers. `source_id` is the `TeamAssignmentMember` id (not the
  event id), so serving two teams at one event yields two distinct items.
  `CHURCH-CALENDAR.2A-FU2`: the calendar item remains read-only and deep-links to
  the viewer's *own* existing My Serving assignment card via a stable anchor
  (`/my-serving/?tab=all#serving-assignment-<TeamAssignmentMember.id>`), never to
  the generic My Serving page, an edit/manage/assignment/confirm URL, or the
  member-facing `ServiceEvent` detail. The ServiceEvent detail is deliberately
  not used: `ServiceEvent.can_be_seen_by` grants ordinary visibility from
  audience-scope membership / manager authority only, never from serving, so an
  assigned server outside the event's audience would be turned away and routing
  through it would couple serving to audience/event visibility. The anchor points
  at the existing My Serving card (`?tab=all` so it is present for past or
  upcoming); the calendar itself renders no
  confirm/decline/check-in/attendance/serving action, and any existing actions on
  the My Serving card (e.g. detail/confirm) remain governed by My Serving and are
  unchanged. FU2 adds only a stable anchor id and changes no My Serving view logic
  or behavior.
- UI: `my_serving` flows through the existing legend, month cells, and the day
  "Timed items" section with its own bilingual type label and distinct dot /
  border color; the "more" compaction behavior is unchanged.

Bible Study linked-user serving roles (`BibleStudyMeetingRole.user`) remain a
deliberate follow-up. Folding them into this `ministry`-keyed provider would
query the `studies` source even when that module is disabled, which would break
the one-provider-per-source-module enablement gate; keeping this slice to
team-assignment serving preserves that clean boundary. A future slice may add
Bible Study serving with its own `studies` enablement handling.

Non-goals unchanged: no assignment creation/edit, no confirm/decline, no
attendance/check-in, no signup/capacity, no notifications/reminders, no external
calendar sync, no staff/team-coverage dashboard, no manager attention cards, no
setup/readiness checks, no serving inference, no Today or My Serving behavior
change, and no CommunityActivity-to-ServiceEvent relationship. No model,
migration, or data write was added.

### CHURCH-CALENDAR.1D-B — Product-owner QA closure

Complete docs-only closure. The product owner manually confirmed the deployed
Calendar V1 current state after `CHURCH-CALENDAR.1A`, `1B`, `1C`, `1D-A`, `2A`,
`CHURCH-CALENDAR.2A-FU2/FU3`, and the My Serving serving-card template
hotfix:

- `/calendar/` renders normally and the month calendar shows real Church
  Gatherings, Bible Study, Community Activities, Announcements, and My Serving
  items.
- Calendar day detail works.
- `my_serving` calendar items still deep-link to the viewer's specific My
  Serving assignment anchor
  (`/my-serving/?tab=all#serving-assignment-<TeamAssignmentMember.id>`).
- `/my-serving/` works, `/my-serving/?tab=past` no longer returns 500, the
  leaked template comment text is gone, and the serving-card template syntax
  hotfix is deployed.
- Calendar remains read-only, and My Serving keeps its own existing behavior.

This closure updates documentation only. It adds no runtime behavior, model,
migration, data write, provider visibility expansion, Today or My Serving
behavior change, serving inference/action, attendance/check-in, notification,
external sync, staff dashboard, Reading active-plan calendar/check-in, route
hard-off, broad UI redesign, or CommunityActivity-to-ServiceEvent relationship.
Calendar V1 is QA-passed for limited trial/current-state use; production
readiness is not claimed.

### CHURCH-CALENDAR.1D — Tests and docs closure

Complete through `CHURCH-CALENDAR.1D-B`. Focused provider, visibility, route,
enablement, local-date, accessibility, query-bound, and cross-product
regression coverage exists for the implemented scope; the product-owner manual
member-calendar QA pass is recorded in
[`CHURCH_CALENDAR_V1_QA_CHECKLIST.md`](CHURCH_CALENDAR_V1_QA_CHECKLIST.md); and
current-state docs now describe the verified implemented behavior. This slice
added no new product scope.

## 11. Approval boundary

`CHURCH-CALENDAR.0A` approved this plan only. `CHURCH-CALENDAR.1A` was
separately approved and implements only the foundation described above. It
does not authorize 1B source integration, 1C final UI, 1D closure/QA, or any
excluded scope without a separate task.

The following remain explicitly excluded from Calendar V1:

- reading calendar or reading check-in integration;
- notifications or reminders;
- serving inference or serving workflow;
- attendance, signup, or check-in;
- Google Calendar or external-calendar sync;
- CommunityActivity-to-ServiceEvent merge;
- broad staff dashboard behavior; and
- any change to Today.
