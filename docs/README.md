# Documentation Index

Status: canonical documentation entry point, current through
`CHURCH-CALENDAR.1A-FU1`. `CHURCH-CALENDAR.1A` implements the model-free,
read-only Church Calendar foundation; real source providers, the final
month/day UI, and tests/docs closure remain pending (July 2026).

Use this page to distinguish current architecture and operating guidance from
historical design, migration, and execution records. Historical documents are
kept for decisions, rollout evidence, and rollback context; they are not current
schema or runtime instructions unless their opening status note says otherwise.

## Canonical Current-State Documents

| Area | Canonical document | What it owns |
|---|---|---|
| Product architecture and roadmap | [`PRODUCT_ARCHITECTURE_AND_ROADMAP.md`](PRODUCT_ARCHITECTURE_AND_ROADMAP.md) | Current product shape, implemented foundations, and deliberately deferred work. |
| Module boundaries | [`MODULE_BOUNDARIES.md`](MODULE_BOUNDARIES.md) | Core versus modules, registry keys, `CMS_ENABLED_MODULES`, dependencies, and present surface-gate limits. |
| Community Activities | [`COMMUNITY_ACTIVITIES_V1_PLAN.md`](COMMUNITY_ACTIVITIES_V1_PLAN.md) | Current implemented V1 lifecycle through 1H-A, including browse/detail, signup/cancel, member drafts and submission, Activity Scope, review/request-changes, pending-review creator editing, capacity, co-organizers, and low-noise Today reminders. It also records the user-confirmed V1 manual QA pass and owns the stabilization boundary; expansion requires separate approval. |
| Official Announcements | [`ANNOUNCEMENTS_V1_PLAN.md`](ANNOUNCEMENTS_V1_PLAN.md) | Canonical bounded V1 plan and QA record. `ANNOUNCEMENTS.1A` through `ANNOUNCEMENTS.1D-SLIM` implement the bounded app, member/staff surfaces, and one-item important-announcement Today reminder. `ANNOUNCEMENTS.1E` adds docs/QA closure only; `ANNOUNCEMENTS-QA-PASS.1A` records the user-confirmed manual-QA pass. Limited trial use is acceptable under the existing trial boundary; this is not a production-readiness claim. |
| Church Calendar | [`CHURCH_CALENDAR_V1_PLAN.md`](CHURCH_CALENDAR_V1_PLAN.md) | Canonical bounded V1 plan and current implementation boundary. `CHURCH-CALENDAR.1A` implements the model-free app, registry/nav foundation, authenticated month/day route shells, safe empty states, and provider contract. Real source/member-safe adapters (1B), final UI (1C), and tests/docs closure and QA (1D) remain pending. |
| Church Structure architecture | [`CHURCH_STRUCTURE_FOUNDATION_PLAN.md`](CHURCH_STRUCTURE_FOUNDATION_PLAN.md) | Current canonical structure/belonging models and the boundary between Church Structure and product-specific consumers. |
| Today versus My Serving | [`TODAY_AND_MY_SERVING_PRODUCT_BOUNDARIES.md`](TODAY_AND_MY_SERVING_PRODUCT_BOUNDARIES.md) | Agenda, personal serving, manager attention, and belonging-versus-serving rules. |
| Deployment security and release hygiene | [`DEPLOYMENT_SECURITY.md`](DEPLOYMENT_SECURITY.md) | Secure administrator bootstrap, repository hygiene completed in `RELEASE-HYGIENE.0A`, and the still-future external archive boundary. |
| Trial setup operations | [`TRIAL_SETUP_READINESS_RUNBOOK.md`](TRIAL_SETUP_READINESS_RUNBOOK.md) | Current read-only setup audit, operator review flow, and latest limited-trial readiness closure. |
| Staff/internal user guide | [`STAFF_SETUP_GUIDE.md`](STAFF_SETUP_GUIDE.md) | Canonical index for the separate [English](STAFF_SETUP_GUIDE.en.md) and [Chinese](STAFF_SETUP_GUIDE.zh.md) practical church-staff guides covering current Church Structure, audience, Today, My Serving, Official Announcements, Community Activities, Church Gatherings, and Bible Study behavior. Deployment/audit procedures remain in the separate trial setup runbook. This is not an ordinary-member help surface or a production-readiness certification. `/staff/setup-guide/` selects one language and remains staff/superuser-gated. |

When these documents conflict with an older plan, use the canonical document
and current code/migrations. `AGENTS.md` remains the standing agent workflow and
migration-safety instruction source.

## Current Architecture Snapshot

- `ChurchStructureUnit` is the canonical local hierarchy.
  `ChurchStructureMembership` is the canonical belonging source for approved
  migrated consumers. Belonging does not imply serving, staff authority, or
  role grants.
- Legacy `SmallGroup`, `District`, and `MinistryContext` models/tables are
  removed. `Profile.small_group` is removed. Historical migrations and
  explicitly historical documents may still name them.
- Bible Study V2 (`BibleStudySeries` + `BibleStudyLesson` +
  `BibleStudyMeeting`) is active. V1 `BibleStudySession`, `BibleStudyGuide`, and
  the V1-only `BibleStudyWorshipSong` schema are retired and removed.
- ServiceEvent ordinary visibility uses `ServiceEventAudienceScope` rows
  matched through active primary membership. Zero-row events fail closed for
  ordinary users.
- The module registry contains `reading`, `prayers`, `studies`, `events`,
  `community_events`, `announcements`, `church_calendar`, and `ministry`.
  `CMS_ENABLED_MODULES` defaults to all
  registered modules. Unknown keys and unmet dependencies raise
  `ImproperlyConfigured`; `ministry` requires `events`. The `announcements`
  module has no registered-module dependency; its member list/detail uses
  published active-window audience visibility even for staff, and zero audience
  rows fail closed.
- `CHURCH-CALENDAR.1A` adds the independent, default-enabled
  `church_calendar` module, module-gated bilingual navigation, authenticated
  read-only `/calendar/` and `/calendar/<year>/<month>/<day>/` routes, basic
  month/day templates and safe empty states, local-date range helpers, and the
  model-free `CalendarItem` provider registry/aggregator foundation. No real
  source provider or member-safe adapter is integrated yet, so the foundation
  queries no `ServiceEvent`, `BibleStudyMeeting`, `Announcement`,
  `CommunityActivity`, or Reading data and shows no real source items.
  Separation from `active_plan_calendar`, reading check-ins, Today, My Serving,
  serving, attendance, notifications, external-calendar sync, and staff
  dashboards remains explicit.
- `COMMUNITY-EVENTS.1A` adds the independent `community_events` app,
  `CommunityActivity`, `CommunityActivityAudienceScope`, Django admin, and
  published/activity-audience visibility through active primary membership.
  Zero-row activities fail closed for ordinary users.
- `COMMUNITY-EVENTS.1B` adds the independent member-facing browse/detail
  entrance (`/activities/` and `/activities/<id>/`, route names
  `community_activity_list` / `community_activity_detail`) and the ordinary
  "Activities" / "活动" primary-nav entry (after Church Gatherings, before My
  Serving), gated by module enablement. The list shows visible upcoming
  published activities via the structure-native helper; detail denies with 404
  when hidden, and the routes have no module hard-off.
- `COMMUNITY-EVENTS.1C` adds `ActivitySignup` and authenticated POST-only
  signup/cancel actions for visible, published, upcoming activities. One row
  per activity/user is retained across cancellation and reactivation; signup
  is attendance intent only and creates no serving records. Approval, capacity,
  waitlist, Today, My Serving, Staff Overview, setup/readiness, and any
  `ServiceEvent` relationship remain deferred.
- `COMMUNITY-EVENTS.1D-A` adds `/activities/new/` for ordinary authenticated
  users with an active primary membership who are not actively blocked by
  `CommunityActivitySubmissionBlock`. Submissions start `pending_review`,
  record the creator, and remain hidden from other ordinary users until
  publication.
- `COMMUNITY-EVENTS.1D-A-FU1` replaces the submission page's note-only scope
  request with a required `ChurchStructureUnit` Activity Scope picker.
  Selected active, non-overlapping units are saved atomically as
  `CommunityActivityAudienceScope` rows; the renamed optional scope note stays
  staff review context. Staff/superusers may adjust the rows and publish in
  Django admin. The creator can see the pending submission, but the selected
  audience cannot see or sign up for it until staff publish.
- `COMMUNITY-EVENTS.1D-B` adds a lightweight staff review inbox and
  request-changes loop. It adds a `changes_requested` status plus
  `review_note` / `reviewed_by` / `reviewed_at` fields
  (migration `community_events/0004`). A staff/superuser-only inbox
  (`/activities/review/`) lists pending-review and changes-requested
  submissions newest first, and `/activities/<id>/review/` offers POST-only
  publish, request changes (requires a note), and cancel/reject actions that
  record the reviewer/time and never delete the activity or its audience rows.
  Creators may edit + resubmit their own `changes_requested` activity
  (`/activities/<id>/edit/`), which transactionally replaces the audience rows
  and returns the activity to `pending_review`. A module-gated staff-dropdown
  "Activity Review" / "活动审核" link was added. No Staff Overview counts, Today,
  My Serving, notifications, or `ServiceEvent` link was added.
- `COMMUNITY-EVENTS.1E-A` adds the module-owned minimal Today provider and
  card. It shows only published visible activities happening today backed by
  the current user's active signup, plus the creator's own
  `changes_requested` edit reminder. Later-this-week signups and
  `pending_review` submissions are not rendered on Today. Disabling
  `community_events` skips the provider and its
  activity/signup queries. This is attendance intent and review status only:
  no My Serving or serving action-center context, Staff Overview,
  setup/readiness, capacity/waitlist, notification, serving record, or
  `ServiceEvent` relationship is added.
- `COMMUNITY-EVENTS.1F-A`, `1F-B`, `1G-A`, and `1H-A` complete the bounded V1
  lifecycle: the primary creator may edit while an activity stays
  `pending_review`; optional capacity supports unlimited and capped active
  signups; active user-linked co-organizers receive bounded pre-publication
  editing; and eligible members may save and continue complete validated
  drafts. These features create no serving or `ServiceEvent` state.
- `COMMUNITY-EVENTS-STABILIZATION.1A` documents the full manual lifecycle QA
  checkpoint, and `COMMUNITY-EVENTS-STABILIZATION.1B` records that manual QA
  passed by user confirmation. A limited trial is acceptable under the
  existing stabilization boundary.
- Disabled modules are surface-gated: primary navigation, module-owned staff
  dropdown links, module-owned Staff Overview cards/counts/links
  (`MODULAR-CORE.6B`, the `/staff/` route and its Core/staff cards stay
  reachable), their Today aggregation/cards/actions, and the profile My
  Serving card where applicable are hidden. Today context is aggregated
  through per-module providers
  (`core/today_providers.py`, `MODULAR-CORE.3A`): enabled modules' registered
  providers are called and disabled modules keep safe default context. The
  provider bodies live in each module's `today_provider` module
  (`MODULAR-CORE.3B`), registered explicitly from `reading.views`. Setup/
  readiness checks follow the same pattern (`MODULAR-CORE.5A`,
  `core/setup_readiness.py`): the `audit_trial_setup_readiness` sections come
  from registered providers — ministry and studies own their sections, Church
  Structure / permission-admin and the always-run audience-visibility section
  stay Core — aggregated for enabled modules only, registered explicitly from
  `accounts.trial_setup_readiness`. This is not app unloading or route-level
  hard-off; direct URLs, the Staff Overview and setup routes, the
  setup/readiness command, and admin routes keep their existing access
  behavior. Only the module-owned overview content and readiness sections
  described above are surface-gated.
- `RELEASE-HYGIENE.0A` secured the deployment admin bootstrap, expanded
  ignore rules for local secrets/databases/backups/logs/audit output, and
  removed committed local audit artifacts. It did not build an external release
  archive; that remains a separate future allowlist-based task.

## Historical Design and Execution Records

The following groups remain useful, but should be read as chronology rather
than pending work:

- Church Structure migration and retirement:
  [`CHURCH_STRUCTURE_CORE_MIGRATION_PLAN.md`](CHURCH_STRUCTURE_CORE_MIGRATION_PLAN.md),
  [`CHURCH_STRUCTURE_MAPPING_AND_MEMBERSHIP_STRATEGY.md`](CHURCH_STRUCTURE_MAPPING_AND_MEMBERSHIP_STRATEGY.md),
  [`LEGACY_STRUCTURE_RETIREMENT_EXECUTION_PLAN.md`](LEGACY_STRUCTURE_RETIREMENT_EXECUTION_PLAN.md),
  and the signup/profile/membership transition plans.
- Bible Study evolution:
  [`BIBLE_STUDY_V2_IMPLEMENTATION_STRATEGY.md`](BIBLE_STUDY_V2_IMPLEMENTATION_STRATEGY.md),
  [`BIBLE_STUDY_V2_GROUP_MEETING_MODEL_PLAN.md`](BIBLE_STUDY_V2_GROUP_MEETING_MODEL_PLAN.md),
  [`BIBLE_STUDY_STRUCTURE_NATIVE_MIGRATION_PLAN.md`](BIBLE_STUDY_STRUCTURE_NATIVE_MIGRATION_PLAN.md),
  and [`LEGACY_BIBLE_STUDY_SESSION_RETIREMENT_DECISION.md`](LEGACY_BIBLE_STUDY_SESSION_RETIREMENT_DECISION.md).
- ServiceEvent audience migration:
  [`SERVICE_EVENT_AUDIENCE_SCOPE_REDESIGN_PLAN.md`](SERVICE_EVENT_AUDIENCE_SCOPE_REDESIGN_PLAN.md)
  and [`SERVICE_EVENT_AUDIENCE_RUNTIME_MIGRATION_PLAN.md`](SERVICE_EVENT_AUDIENCE_RUNTIME_MIGRATION_PLAN.md).
- Reading/reflection migration:
  [`READING_PROGRESS_REFLECTION_PRIVACY_MIGRATION_PLAN.md`](READING_PROGRESS_REFLECTION_PRIVACY_MIGRATION_PLAN.md)
  and [`READING_STRUCTURE_RUNTIME_MIGRATION_PLAN.md`](READING_STRUCTURE_RUNTIME_MIGRATION_PLAN.md).
- Roadmap ledgers and pilot-era plans:
  [`ROADMAP_REVISED_PRE_PILOT.md`](ROADMAP_REVISED_PRE_PILOT.md) and
  [`POST_PILOT_BACKLOG_TRIAGE.md`](POST_PILOT_BACKLOG_TRIAGE.md).

QA checklists tied to retired schema, especially
[`BIBLE_STUDY_V1_QA_CHECKLIST.md`](BIBLE_STUDY_V1_QA_CHECKLIST.md), are
historical evidence rather than current test instructions.

## Current Stabilization and Deferred Product Plans

Community Events/Activities V1 is implemented through `1H-A`: independent
model/admin/visibility, browse/detail/nav, signup/cancel, member drafts and
submission with Activity Scope, staff review/request-changes, pending-review
creator editing, low-noise Today reminders, optional capacity, and bounded
user-linked co-organizers. `COMMUNITY-EVENTS-STABILIZATION.1A` moved this
lifecycle to manual QA, and `COMMUNITY-EVENTS-STABILIZATION.1B` records the
user-confirmed pass. The latest setup-readiness audit reports 0 blockers and
19 documented setup/data warnings, so the project is usable for a limited trial
under the existing stabilization boundary. This is not a production deployment
claim. See
[`TRIAL_SETUP_READINESS_RUNBOOK.md`](TRIAL_SETUP_READINESS_RUNBOOK.md) for the
recorded audit command, warning breakdown, verification, and migration status.

Community Activities remains a secondary independent module, not official
Church Gatherings, My Serving, `ServiceEvent`, or serving. Waitlist, attendee
list, check-in, notifications, comments, payments, calendar integration,
broader Today browse/discovery, Staff Overview cards, setup/readiness, any
`ServiceEvent` relationship, My Serving integration, and the separate
Checklist product remain deferred and require separately approved slices.
The `CHURCH-CALENDAR.1A` foundation does not query Community Activities.
Pending 1B may add a member-safe range adapter for published, visible
activities; neither slice adds a Community Activity calendar workflow, changes
signup, or creates a `CommunityActivity`–`ServiceEvent` relationship.

Official Announcements V1 is now bounded in
[`ANNOUNCEMENTS_V1_PLAN.md`](ANNOUNCEMENTS_V1_PLAN.md) as an independent
staff-authored communication module. `ANNOUNCEMENTS.1A` implements its
app/model/admin/visibility foundation, and `ANNOUNCEMENTS.1B` implements
registry/default enablement, module-gated bilingual navigation, and
authenticated member list/detail. `ANNOUNCEMENTS.1C` implements a bounded
staff/superuser management list, atomic create/edit with structure audience
rows, and POST-only publish/archive actions. `ANNOUNCEMENTS.1D-SLIM` implements
a module-owned Today provider and compact bilingual card for at most one
member-visible active important announcement, title/detail link only; disabling
the module keeps a safe empty default and skips the announcement query.
Announcements
must remain distinct from Community Activities, `ServiceEvent`, notifications,
Staff Overview, and serving/My Serving state. `ANNOUNCEMENTS.1E` adds docs/QA
closure only. `ANNOUNCEMENTS-QA-PASS.1A` records that the product owner
manually ran the checklist and confirmed it passed across staff lifecycle,
audience visibility, bilingual display, Today/module gates, and cross-module
non-goals. Announcements V1 is acceptable for limited trial use under the
existing trial boundary, without claiming production readiness. The
staff/internal-only user guide index is
[`STAFF_SETUP_GUIDE.md`](STAFF_SETUP_GUIDE.md), with separate
[English](STAFF_SETUP_GUIDE.en.md) and [Chinese](STAFF_SETUP_GUIDE.zh.md)
sources written as practical church-staff manuals rather than developer
deployment/audit instructions. `/staff/setup-guide/` (route name
`staff_setup_guide`, linked from the Staff dropdown) selects the current
language and renders readable, escaped guide sections under the existing
staff/superuser gate. It adds no member-facing surface.

Church Calendar V1 is bounded in
[`CHURCH_CALENDAR_V1_PLAN.md`](CHURCH_CALENDAR_V1_PLAN.md).
`CHURCH-CALENDAR.1A` implements the model-free read-only foundation: the app is
registered and default-enabled, authenticated month/day routes and basic
templates exist, safe empty states render, and a normalized range-provider
registry/aggregator contract exists. The registry intentionally has no real
source providers, so the calendar does not yet show actual events,
announcements, activities, meetings, or Reading data. 1B member-safe source
adapters, the final 1C month/day UI, and 1D tests/docs closure and manual QA
remain pending. Calendar V1 is not complete or QA-passed. It continues to
exclude the reading active-plan calendar and check-ins, serving inference,
attendance/check-in, notifications, Google Calendar sync, Community
Activity/ServiceEvent merging, staff dashboard behavior, and any Today or My
Serving change.

Do not use planning documentation as authorization to expand signup beyond the
implemented lifecycle, add shared user surfaces, route hard-off gates,
staff/setup extraction, or package extraction.
