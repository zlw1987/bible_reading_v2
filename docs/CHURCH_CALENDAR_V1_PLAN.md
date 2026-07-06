# Church Calendar V1 Plan

Status: `CHURCH-CALENDAR.0A` approved this bounded plan,
`CHURCH-CALENDAR.1A` implemented the model-free read-only foundation,
`CHURCH-CALENDAR.1B` added the four member-safe source range providers and
their visibility adapters, and `CHURCH-CALENDAR.1C` implemented the final
member-facing month grid and day detail UI (July 2026).
`CHURCH-CALENDAR.1D-A` prepared closure coverage/docs and the pending manual QA
checklist. Manual QA remains pending, and Calendar V1 is not QA-passed.

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
- a serving schedule or source of `TeamAssignment`,
  `TeamAssignmentMember`, or `BibleStudyMeetingRole`;
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
- distinguish the four item types with bilingual labels and accessible text,
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
- no Today, My Serving, serving, attendance, signup, notification, or reading
  check-in state is created or changed; and
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

Prepared, not QA-passed. Reviewed existing route, provider, visibility,
enablement, local-date, accessibility, read-only, and cross-product regression
coverage against this plan; added only the missing focused co-organizer
member-calendar bypass regression test. Created the initially unchecked manual
QA checklist at
[`CHURCH_CALENDAR_V1_QA_CHECKLIST.md`](CHURCH_CALENDAR_V1_QA_CHECKLIST.md) and
updated current-state docs to record that 1A/1B/1C are implemented while manual
QA remains pending. This closure-prep slice added no new product feature scope,
model, migration, data write, provider visibility expansion, Today, My Serving,
serving, signup, attendance/check-in, notification, external sync, staff
dashboard, Reading active-plan calendar/check-in, route hard-off, broad UI
redesign, or CommunityActivity-to-ServiceEvent relationship.

### CHURCH-CALENDAR.1D — Tests and docs closure

Pending product-owner manual QA. Complete focused provider, visibility, route,
enablement, local-date, accessibility, query-bound, and cross-product
regression coverage; run manual member-calendar QA; and update current-state
docs from "planned" to the verified implemented behavior. This slice must not
add new product scope.

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
