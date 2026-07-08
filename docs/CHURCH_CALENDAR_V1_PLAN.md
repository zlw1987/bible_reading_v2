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
`CHURCH-CALENDAR.2A-FU4` implements presentation-only occurrence grouping: it groups the base
`ServiceEvent` and the viewer's own serving rows for it into one presentation
occurrence (see Section 10). `CHURCH-CALENDAR.2B` adds the signed-in user's own
explicit Bible Study serving roles as a read-only personal `bible_study_serving`
overlay owned by `studies`, grouped under the same FU4 contract by
`bible_study_meeting:<id>` (see Section 10); an explicit linked role additionally
grants read-only visibility to that one meeting's detail (studies-owned mirror of
SERVING-EVENT-VISIBILITY.1A). `CHURCH-CALENDAR.1D-B` records the product-owner
manual QA pass after deployment as the baseline Calendar V1 closure. Calendar V1
is QA-passed for limited trial/current-state use at that baseline; FU4 grouping
has focused automated tests but no product-owner manual regression pass yet, and
`CHURCH-CALENDAR.2B` Bible Study serving is likewise implemented with focused
tests but pending product-owner manual QA. This
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
  `TeamAssignmentMember` serving, and `CHURCH-CALENDAR.2B` adds a read-only
  personal `bible_study_serving` overlay of the viewer's *own* explicit linked
  `BibleStudyMeetingRole` serving, but neither ever creates, edits, confirms, or
  otherwise mutates serving, and neither infers serving from membership/audience;
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
| `my_serving` | `TeamAssignmentMember` (via `ServiceEvent`) | `CHURCH-CALENDAR.2A` personal, read-only overlay of the *viewer's own* explicit team-assignment serving. Timed item anchored to the linked `ServiceEvent` `start_datetime` with the existing effective-end overlap rule (multi-day events appear on every overlapping day). Owned by the `ministry` module; serving is explicit only and never inferred from membership/audience/visibility. `CHURCH-CALENDAR.2A-FU2`: the serving subitem deep-links to the viewer's own specific My Serving assignment card (`/my-serving/?tab=all#serving-assignment-<TeamAssignmentMember.id>`), not the generic My Serving page — the anchor targets that exact card and preserves current Calendar behavior. `CHURCH-CALENDAR.2A-FU4`: a `my_serving` row no longer renders as its own separate calendar row; it is grouped (via a shared `occurrence_key = "service_event:<id>"`) into the base `ServiceEvent` occurrence as a serving summary (month) / subitem (day), and the grouped occurrence header links to the member-facing `ServiceEvent` detail (read visibility granted by `SERVING-EVENT-VISIBILITY.1A`). |
| `bible_study_serving` | `BibleStudyMeetingRole` (via `BibleStudyMeeting`) | `CHURCH-CALENDAR.2B` personal, read-only overlay of the *viewer's own* explicit linked Bible Study serving roles. Timed point anchored to the local date of `meeting_datetime`, no invented duration (like `bible_study_meeting`). Owned by the `studies` module (emitted by the single `studies` calendar provider, so gated by `studies` enablement; `ministry` never queries `studies`). Serving is explicit only (linked `BibleStudyMeetingRole.user`) and never inferred from membership/audience/meeting visibility/staff authority. One item is emitted per role (`source_id` is the `BibleStudyMeetingRole.id`; the distinct `bible_study_serving` item type also prevents any `bible_study_meeting` identity collision). `CHURCH-CALENDAR.2A-FU4`: each `bible_study_serving` row is grouped (via a shared `occurrence_key = "bible_study_meeting:<id>"`) into the base `BibleStudyMeeting` occurrence as a serving summary (month) / subitem (day); the grouped occurrence header links to the member-facing `bible_study_meeting_detail`. Unlike the old parked design it is NOT gated on ordinary audience visibility: an explicit role holder outside the audience still sees their own occurrence, and the studies-owned mirror of SERVING-EVENT-VISIBILITY.1A (`user_has_explicit_bible_study_serving_role_for_meeting`) grants read-only detail visibility to exactly that one meeting. It never links to an edit/manage/confirm/attendance/staff URL, never adds the user to the audience, and the ordinary `bible_study_meeting` provider stays audience-only. |

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
  the generic My Serving page or an edit/manage/assignment/confirm URL. The anchor
  targets the viewer's exact existing My Serving assignment card and preserves
  current Calendar behavior (`?tab=all` so it is present for past or upcoming); the
  calendar itself renders no confirm/decline/check-in/attendance/serving action,
  and any existing actions on the My Serving card (e.g. detail/confirm) remain
  governed by My Serving and are unchanged. FU2 adds only a stable anchor id and
  changes no My Serving view logic or behavior.
- UI: `my_serving` flows through the existing legend, month cells, and the day
  "Timed items" section with its own bilingual type label and distinct dot /
  border color; the "more" compaction behavior is unchanged. (Superseded by
  `CHURCH-CALENDAR.2A-FU4`: a `my_serving` row is no longer a standalone calendar
  row — it is grouped into its base `ServiceEvent` occurrence as a serving
  summary / subitem. The legend still lists the My Serving type.)

> Update (`SERVING-EVENT-VISIBILITY.1A`): an explicit `TeamAssignmentMember`
> assignment now grants the assignee read-only visibility to *that specific*
> `ServiceEvent` detail (never audience membership, never other events, never
> management authority; ordinary member-safe calendar/list visibility stays
> audience-only). At the time it did not change the 2A calendar link, but it
> removed the blocker for pointing the grouped occurrence at the event detail and
> resolved the "serving-without-base-visibility" case. `CHURCH-CALENDAR.2A-FU4`
> now relies on this: the grouped occurrence header links to the base
> `ServiceEvent` detail (which the assignee can open), while serving subitems keep
> deep-linking to the My Serving assignment card.

Bible Study linked-user serving roles (`BibleStudyMeetingRole.user`) were left as
a deliberate follow-up here because folding them into this `ministry`-keyed
provider would query the `studies` source even when that module is disabled,
which would break the one-provider-per-source-module enablement gate. That
follow-up is now delivered by `CHURCH-CALENDAR.2B` below, owned and gated by
`studies`.

Non-goals unchanged: no assignment creation/edit, no confirm/decline, no
attendance/check-in, no signup/capacity, no notifications/reminders, no external
calendar sync, no staff/team-coverage dashboard, no manager attention cards, no
setup/readiness checks, no serving inference, no Today or My Serving behavior
change, and no CommunityActivity-to-ServiceEvent relationship. No model,
migration, or data write was added.

### CHURCH-CALENDAR.2A-FU4 — Occurrence grouping

Fixes the 2A UX duplication where one real ServiceEvent could appear several
times on the calendar — once as the base `service_event` row plus one
`my_serving` row per serving assignment (e.g. "Sunday Worship", "Sunday Worship ·
Camera Team", "Sunday Worship · Lighting Team"). The same real occurrence now
renders once, with the viewer's serving assignments attached as a summary
(month) or subitems (day).

Grouping is **presentation-only** and never authorization:

- `CalendarItem` gains optional grouping metadata: `occurrence_key`,
  `occurrence_role`, `occurrence_title`, `occurrence_detail_url`. Item identity
  stays `(item_type, source_id)`; member-safe visibility is unchanged.
- The `events` provider sets `occurrence_key = "service_event:<ServiceEvent.id>"`
  on its base row; the `ministry` provider sets the same key on each `my_serving`
  row for that event, plus `occurrence_role` = the serving team name and
  `occurrence_title` / `occurrence_detail_url` = the base event title and
  member-facing event detail URL.
- Grouping keys on the underlying object identity (the ServiceEvent id), **never**
  on title/time/location strings, so two unrelated events that merely share a
  title/time are never merged. The key is deliberately generic so future keys
  (e.g. `"bible_study_meeting:<id>"`) group the same way with no contract change.
- The presentation layer collapses items sharing an `occurrence_key` into one
  grouped occurrence. Month cell compaction / "more" counts grouped occurrences,
  not raw duplicate items.

Display and link behavior:

- Month grid: the grouped row shows the base title; with one serving assignment
  it appends `· <team>` (e.g. `Sunday Worship · Camera Team` / `主日崇拜 · 摄像团队`),
  with two or more a concise summary `· Serving ×N` / `· 服事 N项`.
- Day detail: one card shows the base event title/time/location/type, with the
  viewer's serving assignments listed underneath as subitems.
- The grouped occurrence header links to the member-facing `ServiceEvent` detail
  (`service_event_detail`). This is safe because `SERVING-EVENT-VISIBILITY.1A`
  grants an explicitly assigned server read-only visibility to *that specific*
  event detail, so a serving-only occurrence (assigned server outside the
  ordinary audience, base row absent) is reconstructed from the `my_serving`
  row's `occurrence_title` / `occurrence_detail_url` and still opens. Serving
  subitems keep deep-linking to the viewer's own read-only My Serving assignment
  anchor. No confirm/edit/manage/assignment/attendance/check-in URL is rendered.

Boundaries preserved: the base `service_event` provider stays audience-only
(`events.visibility.member_visible_service_events_for`); serving stays explicit
(`TeamAssignmentMember`) and is never inferred from membership/audience/
visibility; other users and staff/superuser/manager authority never see the
viewer's serving subitems; a non-assigned non-audience user still cannot see the
occurrence; and `ServiceEvent.can_be_seen_by` behavior is unchanged. The calendar
stays read-only. No model, migration, or data write was added.

### CHURCH-CALENDAR.2B — Bible Study serving overlay

Implemented; manual QA pending product-owner confirmation. Adds the signed-in
user's own explicit Bible Study serving roles to the calendar as a new read-only
personal item type (`bible_study_serving` / "Bible Study Serving" / "查经服事"),
grouped under the `CHURCH-CALENDAR.2A-FU4` occurrence contract. This completes the
`CHURCH-CALENDAR.2A` documented follow-up for `BibleStudyMeetingRole.user`
serving, adapted to FU4 grouping and to the SERVING-EVENT-VISIBILITY.1A serving-
detail-read boundary.

Ownership and boundary:

- The provider is owned by the `studies` module. Because the registry accepts one
  provider per source module, the existing `studies.calendar_provider` was
  extended: its single registered callable now returns both ordinary
  `bible_study_meeting` visibility items and the viewer's own
  `bible_study_serving` items. It is therefore gated by the `studies` source
  module's enablement — when `studies` is disabled the aggregator does not call it
  and runs **no** Bible Study calendar query (meeting or serving), and staff
  status never bypasses that gate. `studies` imports no sibling source module; in
  particular it does **not** import `ministry`, so the Bible Study serving
  semantics live natively inside `studies`.
- Serving is **explicit**. An item is produced only from the viewer's own linked
  `BibleStudyMeetingRole.user` rows on a published/completed meeting whose lesson
  is published/completed and whose series is active. Serving is never inferred from
  `ChurchStructureMembership` (belonging), audience scopes, meeting visibility, or
  staff/superuser/capability/manager authority, and only the viewer's own serving
  is shown. A display-name-only (unlinked) role creates no personal item.
- Unlike the ordinary meeting provider, the `bible_study_serving` overlay is
  **not** gated on audience visibility: an explicit role holder outside the
  meeting audience still receives their own serving occurrence, mirroring the
  ServiceEvent `SERVING-EVENT-VISIBILITY.1A` end-state. The matching meeting-detail
  read gate is the studies-owned
  `studies.permissions.user_has_explicit_bible_study_serving_role_for_meeting`,
  layered beside `BibleStudyMeeting.can_be_seen_by` in the
  `bible_study_meeting_detail` view only. It grants read-only visibility to exactly
  that one meeting, never adds the user to the audience, never reveals any other
  meeting, and grants no manage/edit/role-management/attendance/check-in authority.
  The ordinary `bible_study_meeting` calendar/list provider stays audience-only.
- The item is a **timed** point-in-time item anchored to `meeting_datetime` with
  no invented duration (like `bible_study_meeting`). One item is emitted per role;
  `source_id` is the `BibleStudyMeetingRole.id`, and the distinct
  `bible_study_serving` item type keeps its identity from ever colliding with the
  meeting's `bible_study_meeting` item, sibling roles, or any `my_serving` item.
- FU4 grouping: both the base `bible_study_meeting` item and each
  `bible_study_serving` item carry the shared
  `occurrence_key = "bible_study_meeting:<id>"`, so the presentation layer
  collapses them into one occurrence — a serving summary on the month grid
  (`<lesson> · <role>` for one role, `<lesson> · Serving ×N` / `· 服事 N项` for
  several) and per-role subitems on the day card. The grouped occurrence header
  links to the member-facing `bible_study_meeting_detail`; a serving-only
  occurrence (role holder outside the audience, base row absent) is reconstructed
  from the serving row's `occurrence_title` / `occurrence_detail_url` and still
  opens via the read gate above. The legend still lists the `bible_study_serving`
  type with its own bilingual label and dot / border color.

Non-goals unchanged: no role creation/edit, no confirm/decline, no
attendance/check-in, no signup/capacity, no notifications/reminders, no external
calendar sync, no staff/team-coverage dashboard, no manager attention cards, no
setup/readiness checks, no serving inference, no audience-membership change, no
broad role management, and no Today or My Serving behavior change. No model,
migration, or data write was added; the calendar remains read-only.

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
