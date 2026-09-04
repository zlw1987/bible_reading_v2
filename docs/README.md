# Documentation Index

Status: canonical documentation entry point, runtime current through `NOTIFY.1F`
(notification app/model/admin/Core delivery-port foundation, recipient UI, the
ministry-owned explicit ServiceEvent serving-assignment producer, and the
studies-owned explicit Bible Study meeting-role producer, plus the Community
Activities-owned primary-creator review-outcome producer after
`REPOSITORY-AUDIT-CLOSEOUT.1A`), plus the docs-only `NOTIFY.1G-0A` contract and
implemented `NOTIFY.1G` Direct Worship Team Change producer.
Church Calendar V1 remains implemented as a
model-free, read-only aggregation surface with source providers, month/day UI,
grouping, and personal explicit-serving overlays through `CHURCH-CALENDAR.2B`.
The later Portal, Community hardening, and repository-audit closeout records are
linked below. This is not a broad production-readiness claim.

Use this page to distinguish current architecture and operating guidance from
historical design, migration, and execution records. Historical documents are
kept for decisions, rollout evidence, and rollback context; they are not current
schema or runtime instructions unless their opening status note says otherwise.

## Canonical Current-State Documents

| Area | Canonical document | What it owns |
|---|---|---|
| Product architecture and roadmap | [`PRODUCT_ARCHITECTURE_AND_ROADMAP.md`](PRODUCT_ARCHITECTURE_AND_ROADMAP.md) | Current product shape, implemented foundations, and deliberately deferred work. |
| Generic deployment configuration | [`GENERIC_DEPLOYMENT_CONFIGURATION_ARCHITECTURE.md`](GENERIC_DEPLOYMENT_CONFIGURATION_ARCHITECTURE.md) · [`Slice 5 implementation plan`](GENERIC_DEPLOYMENT_CONFIGURATION_SLICE5_PLAN.md) | Frozen architecture; 1A/2A implement Ministry Team key identity/configuration tooling. 3A adds ServiceProfile/FK schema, and 4A is production-applied/post-audit-verified for one reviewed SVCA mapping (one profile, 52 exact dual-consistent events, zero drift, revisions `1 -> 2` once). 5A audits/plans; 5B adds the default-off integration registry and lazy adapter gates; 5C adds the typed FK-authoritative runtime seam; 5D implements FK-owned readiness V2, the retained dual-safe Bethany TEST reset V2, and FK-selecting ServiceEvent Admin; and `GENERIC-DEPLOYMENT-CONFIG.5E` is IMPLEMENTED / LOCAL VERIFIED for FK/Profile-authoritative Worship XLSX matching and confirmation plus strict V2 parsed/normalized/confirmation contracts binding integration and exact profile identity. V1 artifacts fail closed; no reset, schema, migration, backfill, or production operation occurred. All known profile-aware runtime consumers are switched, but 5F closure proof remains pending and `runtime_consumer_switched` remains false globally. Profile defaults/materialization, MO-S.REQUIRED runtime, external mapping, 5F closure, and legacy-key retirement remain pending. |
| Repository audit gap completion | [`REPOSITORY_AUDIT_GAP_COMPLETION_PLAN.md`](REPOSITORY_AUDIT_GAP_COMPLETION_PLAN.md) | Repository-wide gap audit, classification counts, no-blocker/high conclusion, hardening-cycle closeout, and bounded disposition of completed, deferred/conditional, and opportunistic roadmap slices. |
| Module boundaries | [`MODULE_BOUNDARIES.md`](MODULE_BOUNDARIES.md) | Core versus modules, registry keys, `CMS_ENABLED_MODULES`, dependencies, and present surface-gate limits. |
| Community Activities | [`COMMUNITY_ACTIVITIES_V1_PLAN.md`](COMMUNITY_ACTIVITIES_V1_PLAN.md) | Current implemented V1 lifecycle through 1H-A, including browse/detail, signup/cancel, member drafts and submission, Activity Scope, review/request-changes, pending-review creator editing, capacity, co-organizers, low-noise Today/This Week reminders, completed review-transition/stale-form hardening through `COMMUNITY-REVIEW-TRANSITION-LOCK.1A-FU2`, and the narrow `NOTIFY.1E` active `created_by` primary-creator review outcomes for successful staff request-changes/publish/cancel-reject transitions. It also records the user-confirmed V1 manual QA pass and owns the stabilization boundary; broader notification/product expansion requires separate approval. |
| Community signup cancellation policy | [`COMMUNITY_SIGNUP_CANCELLATION_POLICY_PLAN.md`](COMMUNITY_SIGNUP_CANCELLATION_POLICY_PLAN.md) | Current V1 policy and implementation record for member signup cancellation: retain `ActivitySignup` rows with `signed_up` / `cancelled` status, count active rows only, allow immediate pre-start self-service cancellation without review, freeze signup state at activity start time, and keep Community Activities separate from serving, official events, Calendar writes, and signup notifications. |
| Official Announcements | [`ANNOUNCEMENTS_V1_PLAN.md`](ANNOUNCEMENTS_V1_PLAN.md) | Canonical bounded V1 plan and QA record. `ANNOUNCEMENTS.1A` through `ANNOUNCEMENTS.1D-SLIM` implement the bounded app, member/staff surfaces, and one-item important-announcement Today reminder. `ANNOUNCEMENTS.1E` adds docs/QA closure only; `ANNOUNCEMENTS-QA-PASS.1A` records the user-confirmed manual-QA pass. Limited trial use is acceptable under the existing trial boundary; this is not a production-readiness claim. |
| Church Calendar | [`CHURCH_CALENDAR_V1_PLAN.md`](CHURCH_CALENDAR_V1_PLAN.md) | Canonical bounded V1 plan and current implementation boundary. `CHURCH-CALENDAR.1A` implements the model-free app, registry/nav foundation, authenticated month/day routes, safe empty states, and provider contract; `CHURCH-CALENDAR.1B` implements the four member-safe source providers/adapters; `CHURCH-CALENDAR.1C` implements the month/day UI; `CHURCH-CALENDAR.1D-A` prepares closure docs/checklist plus a missing focused regression test; and `CHURCH-CALENDAR.2A` adds the `ministry`-owned read-only personal `my_serving` overlay of the viewer's own explicit `TeamAssignmentMember` serving (registered after the four sources, gated by `ministry` enablement, deep-links to the existing My Serving assignment card, serving never inferred); `CHURCH-CALENDAR.2A-FU4` groups the base ServiceEvent and the viewer's own serving rows for it into one presentation occurrence (shared `occurrence_key`, month serving summary / day subitems, header links to the member-facing ServiceEvent detail). `CHURCH-CALENDAR.2B` adds the `studies`-owned `bible_study_serving` overlay grouped by `bible_study_meeting:<id>` and records product-owner manual QA passed in `CHURCH-CALENDAR.2B-QA-CLOSURE`. `CHURCH-CALENDAR.1D-B` records the product-owner manual QA pass after deployment, including the `/my-serving/?tab=past` hotfix and assignment-anchor deep-link verification. Calendar V1 is QA-passed for limited trial/current-state use, without claiming broad production readiness. See [`CHURCH_CALENDAR_V1_QA_CHECKLIST.md`](CHURCH_CALENDAR_V1_QA_CHECKLIST.md). |
| Notification V0 | [`NOTIFICATIONS_V0_PLAN.md`](NOTIFICATIONS_V0_PLAN.md) | Canonical runtime boundary through implemented `NOTIFY.1G`: registered/gateable notifications app, model/admin, Core directed-delivery port, notifications-owned persistence, recipient center/bell/read state, recipient-scoped POST Open, 25-row pagination, retain-for-now policy, three earlier narrow producers, and the bounded direct Worship Team change producer. This is not browser automation or a broad production-readiness claim. |
| Sunday Ministry Scheduling | [`SUNDAY_MINISTRY_SCHEDULING_PLAN.md`](SUNDAY_MINISTRY_SCHEDULING_PLAN.md) | Current MO-S.6 plan through implemented Board/context, Campus, Worship pool,
event-planner, governed exact-event selection, operational reachability,
rotation-planner confirmation/shared audit, bounded NOTIFY.1G, stable
ServiceEvent profile identity, production-smoke-passed XLSX preview, and
production-verified atomic annual Worship Team workbook confirmation through
MO-S.6D-SLICE9.1A. Assignment/member import and MO-S.6E roster-change staleness
remain separately deferred. |
| Worship Rotation Governance | [`WORSHIP_ROTATION_GOVERNANCE_PLAN.md`](WORSHIP_ROTATION_GOVERNANCE_PLAN.md) | Canonical multi-campus Worship invariants through governed selection,
operational reachability, planner confirmation/shared audit, bounded NOTIFY.1G,
stable profile identity, and production-verified annual workbook confirmation.
Assignment/member import remains deferred. |
| Worship Rotation Planner | [`WORSHIP_ROTATION_PLANNER_PLAN.md`](WORSHIP_ROTATION_PLANNER_PLAN.md) | `MO-S.6D-1D-D-0A` V1 contract plus implemented read-only `1A` proposal/preview, `1B-A1` scheduling-revision foundation, and `1B-B` POST-only optimistic confirmation/shared audit: exact bounded shift semantics, no tail loss, destination eligibility, per-event authority, roster blocker, roster-free downstream impact, signed fingerprint-v3 stale protection, all-or-nothing anchor updates, and changed-only shared-operation audit. |
| Church Structure architecture | [`CHURCH_STRUCTURE_FOUNDATION_PLAN.md`](CHURCH_STRUCTURE_FOUNDATION_PLAN.md) | Current canonical structure/belonging models and the boundary between Church Structure and product-specific consumers. |
| Church Structure primary membership integrity | [`STRUCTURE_MEMBERSHIP_PRIMARY_INTEGRITY_PLAN.md`](STRUCTURE_MEMBERSHIP_PRIMARY_INTEGRITY_PLAN.md) | Current primary-membership invariant, mutation-path inventory, 1A hardening, readiness detection, and deferred DB-constraint design. |
| Today versus My Serving | [`TODAY_AND_MY_SERVING_PRODUCT_BOUNDARIES.md`](TODAY_AND_MY_SERVING_PRODUCT_BOUNDARIES.md) | Agenda, personal serving, manager attention, and belonging-versus-serving rules. |
| Portal UX and Help Center | [`PORTAL_UX_AND_HELP_CENTER_PLAN.md`](PORTAL_UX_AND_HELP_CENTER_PLAN.md) | Current top-navigation shell, Staff dropdown grouping, authenticated Help Center foundation, guide taxonomy, recommendation rules, permission boundaries, completed 1A work plus 1A-FU1 ministry-gate/content hardening, and deferred portal/help slices. |
| Deployment security and release hygiene | [`DEPLOYMENT_SECURITY.md`](DEPLOYMENT_SECURITY.md) | Secure administrator bootstrap, repository hygiene through `RELEASE-HYGIENE.1A`, and the still-future external archive boundary. See also the local-only GoDaddy static audit: [`GODADDY_PRODUCTION_SECURITY_AUDIT.md`](GODADDY_PRODUCTION_SECURITY_AUDIT.md). |
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
  `community_events`, `announcements`, `notifications`, `church_calendar`, and
  `ministry`.
  `CMS_ENABLED_MODULES` defaults to all
  registered modules. Unknown keys and unmet dependencies raise
  `ImproperlyConfigured`; `ministry` requires `events`. The `announcements`
  module has no registered-module dependency; its member list/detail uses
  published active-window audience visibility even for staff, and zero audience
  rows fail closed.
- `NOTIFY.1A` implements the registered/default-enabled `notifications` app,
  Notification model/migration/admin, the Core directed payload and single-sink
  delivery port, the registered notifications-owned persistence sink,
  recipient-plus-dedupe database idempotency, disabled-module no-op,
  post-commit dispatch, contained/logged normal failures, and a strict
  development/test seam. Source modules still resolve recipients and import no
  notifications code. The module has no source dependency and contributes no
  ordinary primary nav, Today, setup/readiness, or Staff Overview surface.
  `NOTIFY.1B` adds the authenticated recipient-only `/notifications/` center,
  newest-first bounded snapshot list, textually visible read/unread state,
  POST-only mark-one/mark-all read actions, and an enabled-only bilingual
  utility bell/unread count. The stored target remains permission-neutral.
  Product-owner manual rendered QA passed for the bounded UI/navigation scope;
  this supports limited-trial/current-product use, not broad production,
  accessibility, security, or hosting readiness.
  `NOTIFY.1C` adds the first narrow source producer, owned by `ministry`, for
  successful interactive TeamAssignment create/edit/team-schedule writes. New
  eligible linked-user member rows receive one assigned payload; retained rows
  receive at most one updated payload for ServiceEvent change and/or
  cancelled-to-active reactivation. Display-name-only members and
  audience/belonging/manager/staff users are not inferred; ordinary edits,
  confirmation, removal/cancellation, previews, imports/admin/direct ORM, and
  failed writes emit nothing. The target is the existing exact My Serving
  member-row anchor, with no permission, audience, serving-read, UI, Calendar,
  or My Serving behavior change.
  The product owner completed the defined deployed `NOTIFY.1C` producer smoke
  QA and confirmed the implemented serving-assignment notification workflow
  worked as expected; this is a narrow workflow result, not browser automation
  or a production/security/accessibility/hosting certification.
  `NOTIFY.1D` adds the second narrow source producer, owned by `studies`, after
  successful interactive `BibleStudyMeetingRole` create/edit saves only. The
  active linked `role.user` is the sole recipient. New linked roles,
  display-only-to-linked changes, and reassignment emit assigned; same-user
  role-type changes emit updated, with reassignment taking priority. Display
  names, audience, belonging, coworker roles, managers, and staff do not infer
  recipients. Notes/display-name edits, unchanged saves, confirmation,
  deletion/removal, lifecycle changes, admin/direct ORM, generation/setup/import,
  and failed writes remain non-notifying. Eligibility uses the existing explicit
  serving lifecycle without an audience requirement, and the target is the
  member-facing meeting detail. Outside-audience explicit roles create no
  audience/membership row and grant only the existing exact-meeting read gate,
  not management. No model, migration, UI, Today, My Serving, Calendar,
  permission, visibility, audience, belonging, or serving behavior changed.
  The product owner completed deployed `NOTIFY.1D` smoke QA successfully; this
  is a narrow user-confirmed smoke result, not browser automation or a broad
  production/security/accessibility/hosting certification.
  `NOTIFY.1E` adds the third narrow source producer, owned by
  `community_events`, inside the existing applied locked staff review seam.
  Successful request-changes, publish, and cancel/reject outcomes notify only
  the active `created_by` primary creator. Co-organizers, audience/signup users,
  memberships, staff authority, and display text do not infer recipients;
  submission/resubmission, ordinary edits, stale/invalid review actions,
  signup lifecycle, admin/direct ORM/setup/import, and reads remain
  non-notifying. The target is the creator-safe activity detail and the bounded
  localized snapshot excludes `review_note` and other private source content.
  No schema, signal, UI, permission, lifecycle, visibility, Calendar, serving,
  My Serving, or `ServiceEvent` relationship changed. `NOTIFY.1F` then adds
  recipient-scoped POST Open/read behavior, 25-row center pagination, and a
  retain-for-now policy without a cleanup command; the product owner completed
  deployed `NOTIFY.1E` smoke QA successfully for the implemented primary-creator
  workflow. That narrow confirmation is not browser automation or a broad
  production/security/accessibility/hosting certification. Later producers,
  Calendar/Staff Overview integration, announcement fanout, external channels,
  schedulers, background jobs, and retention cleanup remain future work.
  `NOTIFY.1G-0A` closes the docs-only direct Worship Team change contract and
  `NOTIFY.1G` implements its exact selector/`1B-B` actual-change triggers,
  exact active/date-valid
  Lead/Coordinator recipients, current-operational downstream status semantics,
  recipient-specific batch subsets, stable audit/operation dedupe identities,
  bounded recipient-language snapshots, and the permission-neutral My Serving
  target. It adds no schema, permission, UI, background job, external delivery,
  or MO-S.6E roster-staleness behavior.
- `CHURCH-CALENDAR.1A` adds the independent, default-enabled
  `church_calendar` module, module-gated bilingual navigation, authenticated
  read-only `/calendar/` and `/calendar/<year>/<month>/<day>/` routes, basic
  month/day templates and safe empty states, local-date range helpers, and the
  model-free `CalendarItem` provider registry/aggregator foundation.
  `CHURCH-CALENDAR.1B` adds the four member-safe source providers/adapters for
  `ServiceEvent`, `BibleStudyMeeting`, `Announcement`, and
  `CommunityActivity`, with disabled-source no-call/no-query behavior and no
  staff/superuser/manager/creator/co-organizer bypass. `CHURCH-CALENDAR.1C`
  adds the responsive member-facing month grid and complete day detail UI.
  `CHURCH-CALENDAR.1D-A` prepares closure docs/checklist and a missing focused
  regression test. `CHURCH-CALENDAR.2A` adds a fifth provider: the
  `ministry`-owned read-only personal `my_serving` overlay of the viewer's own
  explicit `TeamAssignmentMember` serving (registered after the four sources,
  gated by `ministry` enablement, timed to the linked ServiceEvent, deep-links to
  the existing My Serving assignment card; existing My Serving actions remain
  governed by My Serving). Serving stays explicit only — never inferred from
  membership/audience/visibility or staff/manager authority — and the calendar
  creates/edits/confirms no serving. `CHURCH-CALENDAR.2B` completes the Bible
  Study serving follow-up: the `studies`-owned personal `bible_study_serving`
  overlay of the viewer's own explicit linked `BibleStudyMeetingRole` serving,
  emitted by the existing single `studies` calendar provider (so gated by
  `studies` enablement; disabled `studies` runs no Bible Study calendar query),
  grouped under the FU4 `bible_study_meeting:<id>` occurrence. The ordinary
  `bible_study_meeting` calendar/list provider stays audience-only; an explicit
  linked role additionally grants read-only visibility to exactly that one
  meeting's detail (studies-owned mirror of SERVING-EVENT-VISIBILITY.1A), never
  adding the user to the audience or revealing any other meeting, and the grouped
  occurrence links to the member-facing meeting detail (product-owner manual QA
  passed, `CHURCH-CALENDAR.2B-QA-CLOSURE`). `CHURCH-CALENDAR.1D-B` records product-owner manual QA
  passed after deployment for the current limited-trial state, including
  `/calendar/`, day detail, real source items, My Serving assignment-anchor
  deep links, `/my-serving/?tab=past` no longer returning 500, and the removed
  leaked template comment text. Separation from `active_plan_calendar`, reading
  check-ins, Today, and My Serving *behavior*, plus attendance, notifications,
  external-calendar sync, and staff dashboards, remains explicit.
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
- `COMMUNITY-EVENTS.1E-A` adds the module-owned minimal Today and This Week
  home-page reminders. Today shows same-day published visible activities backed
  by the current user's active signup; This Week shows later-this-week active
  signup reminders; creator attention shows the creator's own
  `changes_requested` edit reminder. `pending_review` submissions and unsigned
  visible activities are not rendered in these reminder surfaces. Disabling
  `community_events` skips the provider and its activity/signup queries. This
  is attendance intent and review status only:
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
  removed committed local audit artifacts. `RELEASE-HYGIENE.1A` removed
  unreferenced local Calendar/My Serving recovery snapshots and added ignore
  coverage for local recovery/editor-conflict scratch files. Neither milestone
  built an external release archive; delivery-layer material such as
  `ship-pack v0.9.2` remains separate.

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
list, check-in, broader Community Activity notifications beyond the implemented
primary-creator review outcomes, comments, payments, Community Activity-owned
writable calendar workflow, external-calendar sync, broader Today
browse/discovery, Staff Overview cards, setup/readiness, any `ServiceEvent`
relationship, My Serving integration, and the separate Checklist product remain
deferred and require separately approved slices.
The Church Calendar source adapter for Community Activities is read-only and
member-safe: it can show published visible activities in the calendar when the
`community_events` module is enabled, but it does not add a Community Activity
calendar workflow, change signup, or create a `CommunityActivity`–`ServiceEvent`
relationship.

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
registry/aggregator contract exists. `CHURCH-CALENDAR.1B` implements the four
module-owned member-safe range providers/adapters for `ServiceEvent`,
`BibleStudyMeeting`, `Announcement`, and `CommunityActivity`; disabled source
modules are not called and run no query, and staff/superuser/manager/creator/
co-organizer status does not widen member-calendar visibility.
`CHURCH-CALENDAR.1C` implements the responsive month grid and complete day
detail UI on top of those providers. `CHURCH-CALENDAR.1D-A` prepared the
unchecked manual QA checklist
([`CHURCH_CALENDAR_V1_QA_CHECKLIST.md`](CHURCH_CALENDAR_V1_QA_CHECKLIST.md)),
updated current-state docs, and added only a missing focused co-organizer
member-calendar bypass regression test. `CHURCH-CALENDAR.2A` added the
`ministry`-owned read-only personal `my_serving` overlay for the viewer's own
explicit `TeamAssignmentMember` serving, and the `CHURCH-CALENDAR.2A-FU2/FU3`
plus hotfix set keeps the calendar item anchored to the existing My Serving
assignment card while fixing the My Serving serving-card template path.
`CHURCH-CALENDAR.1D-B` records that the product owner manually confirmed the
deployed Calendar V1 pass:
`/calendar/` renders, month and day views work with real Church Gatherings,
Bible Study, Community Activities, Announcements, and My Serving items,
`/my-serving/?tab=past` no longer returns 500, leaked template comment text is
gone, and Calendar remains read-only while My Serving keeps its own behavior.
`CHURCH-CALENDAR.2B` then added the `studies`-owned personal
`bible_study_serving` overlay of the viewer's own explicit linked
`BibleStudyMeetingRole` serving by extending the single `studies` calendar
provider to emit both meeting-visibility and serving items (gated by `studies`
enablement, no cross-module import of `ministry`); `CHURCH-CALENDAR.2B-QA-CLOSURE`
records the product-owner manual QA pass, which also confirmed ServiceEvent
serving grouping still works and My Serving behavior is unchanged.
Calendar V1 is QA-passed for limited trial/current-state use, but this is not a
production-readiness claim. It continues to exclude the reading active-plan
calendar and check-ins, serving inference, attendance/check-in, notifications,
Google Calendar sync, Community Activity/ServiceEvent merging, staff dashboard
behavior, and any Today or My Serving behavior change.

Do not use planning documentation as authorization to expand signup beyond the
implemented lifecycle, add shared user surfaces, route hard-off gates,
staff/setup extraction, or package extraction.
