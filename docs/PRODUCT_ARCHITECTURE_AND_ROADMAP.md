# Product Architecture and Roadmap

Status: canonical current-state product architecture and roadmap, updated
through the docs-only Official Announcements V1 plan (July 2026).

## 1. Project Identity

This project is a lightweight church spiritual life and ministry workflow system.
It started as a Bible reading check-in app. The current core remains Daily Reading, but the roadmap includes Prayer, Bible Study, Worship Set planning, and Ministry Team Operations.
It is not intended to become a full church ERP.

The app should support spiritual practices and practical ministry coordination: daily Scripture reading, prayer, reflection, group encouragement, Bible study preparation, and eventually focused ministry workflows. It should stay simple, pastoral, and workflow-oriented rather than becoming a broad administrative system.

## 2. Current Status

Daily Reading Core V1 is feature complete and in closure/stabilization.

Prayer V1 is core-complete and in stabilization.

Bible Study V2 is the active Bible Study path. The old V1 `BibleStudySession` / guide / worship-song schema has been retired and removed from current models.

Bible Study meeting worship-set planning is implemented on the V2 meeting path.

The role/scoped permission foundation exists.

Navigation cleanup is complete. The authenticated navbar information architecture has been reorganized: primary nav keeps the main user workflows, while staff/admin and account functions are grouped into caret dropdowns, and the staff menu includes a Structure Setup / 结构设置 section linking both Church Structure and Ministry Structure.

Reading Guide Posts are implemented.

ServiceEvent Foundation V1 is implemented and pilot-validated.

MinistryTeam + TeamMembership Foundation is implemented and pilot-validated.

TeamAssignment V1 is implemented and pilot-validated.

My Serving Page V1 is implemented and pilot-validated.

Lighting Team Pilot Data import support and setup UI are implemented and pilot-validated. The Lighting Pilot Import is retired from the normal discoverable UI while its route/view/service/command remain available.

Ministry Structure architecture is implemented through `MINISTRY-STRUCTURE.1A`–`1H`: `MinistryTeam` was upgraded in place into the ministry-structure unit (kind / assignable / role profile, `MinistryTeamParentLink`, and the additive ministry role system), with a read-only staff Ministry Structure map at `/structure/`, staff-only structure setup and long-term ministry-role assignment UI at `/teams/<id>/structure/`, a seed command, a readiness audit, and `is_assignable` enforcement for new serving assignments. The Ministry Structure setup foundation is complete enough for the current product stage. Ministry Teams / Ministry Structure UI polish is complete: `/teams/` has search and readiness filters, and the `/teams/` ↔ `/structure/` relationship is clearer. The authenticated navbar IA cleanup is complete (see "Navigation cleanup" above).

Manual QA passed for the navbar IA and Ministry Structure cleanup, covering desktop ordinary user, desktop staff user, the mobile hamburger drawer, the Staff dropdown, the account dropdown, the Today / My Serving / Bible Study serving core flows, and the Ministry Teams / Ministry Structure core flows. No product boundary changed: Today remains a general agenda/dashboard (not a serving workspace), My Serving remains the serving workspace, visibility / membership / audience scope still does not imply serving, only explicit `TeamAssignmentMember` and linked-user `BibleStudyMeetingRole.user` personalize serving, and `MinistryTeamRoleAssignment` remains long-term structure responsibility — not weekly/event serving (at that time it also drove no permission; `MINISTRY-ROLE-SOURCE.1C` later made active lead/coordinator role assignments the runtime team-management permission source).

`MINISTRY-ROLE-SOURCE.1A` (docs + read-only audit) locked `MinistryTeamRoleAssignment` as the single source of truth for long-term ministry roles; `MINISTRY-ROLE-SOURCE.1A-FU1` clarified that assignable teams (`is_assignable=True`) expect role holders to also be active members while non-assignable container teams do not, and adjusted the read-only alignment audit accordingly. `MINISTRY-ROLE-SOURCE.1B` (implemented) added the dry-run-by-default backfill that creates missing `MinistryTeamRoleAssignment` rows from active user-linked `TeamMembership.role` in {`lead`, `coordinator`}. **`MINISTRY-ROLE-SOURCE.1C` (implemented) switched the runtime read:** `can_manage_ministry_team`, `manageable_assignment_teams`, team scheduling, manage-members, and My Serving "Teams I manage" now resolve team-management authority from active `MinistryTeamRoleAssignment` rows (role_type code in {`lead`, `coordinator`}) for the exact team, not `TeamMembership.role`. After `1C`, `TeamMembership.role` is legacy compatibility data and grants no runtime team-management permission; `TeamMembership.can_lead` remains deprecated/reserved and grants none. `1C` is exact-team only, leaves staff / superuser / global capability behavior unchanged, and changes no model or migration. **`MINISTRY-ROLE-SOURCE.1D` (implemented)** cleaned up the manage-members UI: `TeamMembershipForm` no longer includes `role` (normal creates default to `member`; existing legacy `role` is preserved untouched on edit) and never included `can_lead`, so neither can be set from that UI; the members list shows canonical long-term roles from active `MinistryTeamRoleAssignment` rows only and links staff to structure setup. **`MINISTRY-ROLE-SOURCE.1E-A` (implemented)** added the dry-run-by-default `cleanup_team_membership_can_lead_flags` command that clears deprecated `can_lead=True` flags under explicit `--apply` (only sets `can_lead` `True` → `False`; never touches `role`, membership rows, or role assignments; changes no permission). See `docs/MINISTRY_ROLE_SOURCE_OF_TRUTH_PLAN.md`. Later legacy field retirement is optional and should not be reopened without a production blocker or audit warning.

`TODAY-AGENDA.1A` and `MY-SERVING-BS.1B` are complete. Today now keeps reading,
visible Church Gatherings, and visible Bible Study meetings as agenda; shows
pending explicit `TeamAssignmentMember` and linked-user
`BibleStudyMeetingRole` serving in its action center; and keeps manager-only
Leader Needs Attention separate from personal serving. My Serving remains the
workspace for team and Bible Study confirmation. Audience visibility,
`ChurchStructureMembership`, display-name-only Bible Study roles, and
`MinistryTeamRoleAssignment` alone never become personal serving.

`COMMUNITY-EVENTS.1E-A` adds the minimal Community Activities Today provider.
It contributes only active-signup published visible activities happening
today, plus creator-owned `changes_requested` reminders. Later-this-week
signups and `pending_review` submissions stay off Today. It adds no My Serving
or serving action-center item, no serving record, and no `ServiceEvent`
relationship.

`COMMUNITY-EVENTS.1F-A` allows the primary creator to edit an activity while
it remains `pending_review`. It does not expose the activity to selected-scope
ordinary users or change staff review authority.

`COMMUNITY-EVENTS.1F-B` adds an optional participant limit to Community
Activities. Null means unlimited; a positive integer caps active signup rows.
Full activities fail closed for new/reactivated signups, cancelled rows do not
count, and already-active signup posts remain idempotent. Capacity is
attendance-intent management only; it creates no serving or `ServiceEvent`
state. Waitlist, attendee list, notifications, check-in, and signup deadlines
remain deferred.

`COMMUNITY-EVENTS.1H-A` adds a bounded member-facing draft workflow. Eligible
creators may save a complete validated activity as draft, continue editing and
managing co-organizers, then submit it for staff review. Linked co-organizers
may view and edit draft details and Activity Scope but cannot change the
co-organizer list or submit the draft. Drafts are preparation only: they are
invisible to selected-scope ordinary users, absent from the staff review inbox,
not signup-eligible, and absent from Today, My Serving, serving state, and
`ServiceEvent`.

`COMMUNITY-EVENTS-STABILIZATION.1A` records the full V1 manual QA checkpoint
in `docs/COMMUNITY_ACTIVITIES_V1_PLAN.md`, and
`COMMUNITY-EVENTS-STABILIZATION.1B` records that manual QA passed by user
confirmation. The latest setup-readiness audit reports 0 blockers and 19
documented setup/data warnings, so the project is usable for a limited trial
under the existing stabilization boundary. This is not a production deployment
claim. New operations, shared surfaces, or cross-module integrations require
separate approval.

Official Announcements V1 is now bounded as a docs-only plan in
`docs/ANNOUNCEMENTS_V1_PLAN.md`. The future independent `announcements` module
is for staff-authored official communication with structure-native audience
rows, published-window visibility, member list/detail, and an important-only
two-item Today reminder. It is not implemented or registered, and planning does
not authorize runtime work. It remains separate from Community Activities,
`ServiceEvent`, notifications, Staff Overview, My Serving, and all serving
state.

MO-S.1 Ministry Scheduling Requirements Plan is complete as docs-only planning for real pilot feedback about required ministry teams, assignment coverage display, and team-leader scheduling workflow. MO-S.2 Event Required-Team implementation, MO-S.3 read-only assignment coverage display, MO-S.4 team-leader scheduling workspace, MO-S.4A scheduling semantic cleanup, MO-S.5A rotation anchor foundation, and MO-S.5B limited copy-forward suggestion helper are complete.

Checklist and advanced scheduling enhancements are still future phases.

The entire project is not complete. The stable center is Daily Reading, Prayer, Bible Study V2, ServiceEvent foundation with required MinistryTeams and optional rotation anchors, generic MinistryTeam foundation, manual TeamAssignment V1, My Serving Page V1, limited Lighting Team Pilot Data/setup support, MO-S.1 scheduling requirements, MO-S.2 required-team data capture, MO-S.3 read-only assignment coverage display, MO-S.4 manual team-leader scheduling workspace, MO-S.4A scheduling semantic cleanup, MO-S.5A rotation anchor foundation, MO-S.5B limited copy-forward suggestions, SE-AS.1 through SERVICE-EVENT-CONTEXT.1C ServiceEvent audience-row migration/guard/retirement work, DOCS-AS.1 shared audience-scope direction, BS-AS.1 / BS-AS.2 / BS-AS.2A Bible Study Schedule audience scope using `ChurchStructureUnit`, BS-STRUCT.1L/1M/1O/1P/2A Bible Study V2 structure-native generation / audience-row visibility cleanup, BS-MEETING-MIRROR.1A mirror removal, BS-V1-SCHEMA-RETIRE.1A V1 schema retirement, and My Serving Bible Study role confirmation; future checklist, scheduling operations, and future module audience work should be added deliberately and kept within clear boundaries.

Church structure domain planning is now implemented for approved local runtime consumers. `ChurchStructureUnit` is the canonical local structure model, `ChurchStructureMembership` is the canonical local belonging model for migrated consumers, and app-specific audience rows such as `ServiceEventAudienceScope`, `BibleStudySeriesAudienceScope`, and `BibleStudyMeetingAudienceScope` drive approved visibility/generation paths. Legacy `Profile.small_group`, `SmallGroup`, `District`, `MinistryContext`, ServiceEvent legacy scope fields, Bible Study Series legacy scope fields, and the V2 meeting `small_group` mirror have been retired from current models. PP-SA.1 records staff/admin surface planning, PP-SA.2 adds the permission-protected read-only staff overview at `/staff/`, PP-SA.3 completes staff membership request workflow polish, PP-SA.4 completes a permission-protected read-only staff moderation queue at `/staff/moderation/`, and PP-SA.5 completes read-only ministry ops health indicators on `/staff/`. See `docs/CHURCH_STRUCTURE_DOMAIN_PLAN.md`, `docs/CHURCH_STRUCTURE_MAPPING_AND_MEMBERSHIP_STRATEGY.md`, `docs/CHURCH_STRUCTURE_SEEDING_VERIFICATION.md`, `docs/CHURCH_STRUCTURE_MEMBERSHIP_BACKFILL_VERIFICATION.md`, `docs/CHURCH_STRUCTURE_MEMBERSHIP_DESIGN.md`, `docs/STAFF_ADMIN_SURFACE_EXPANSION_PLAN.md`, and `docs/SERVICE_EVENT_AUDIENCE_SCOPE_REDESIGN_PLAN.md`.

`GROUP-MEMBERSHIP-MANAGE.1A` and `GROUP-MEMBERSHIP-REQUEST.1B` are complete and
QA-passed. On a small-group My Units detail page, staff/superusers and authorized
active `lead` role holders on that unit or an ancestor can add a user who has no
current/future active primary membership and no pending request, end an active
small-group membership without deleting the row or user, and approve/reject
pending requested memberships for that managed small group. The global staff
membership-request queue remains available. "Unassigned" is a candidate state,
not a `ChurchStructureUnit`: no fake Unassigned group exists or should be
created. Existing active-primary conflicts are blocked and a one-click transfer
workflow remains deferred. These actions change belonging only; they never grant
serving, coworker roles, permissions, TeamAssignment / My Serving, or Bible Study
serving. This closes the limited-trial gap where small-group leaders had no
direct way to maintain group belonging.

Current architecture snapshot: Church Structure is canonical locally; legacy structure objects and bridge fields are retired from current models; Bible Study V2 (`BibleStudySeries` + `BibleStudyMeeting`) is active while V1 schema is removed; Today remains a general dashboard; My Serving is the explicit-assignment workspace, including Bible Study meeting role confirmation; external structure database integration is future architecture work. If that integration is pursued, prefer a sync/adaptor/local-shadow model that feeds local `ChurchStructureUnit` / `ChurchStructureMembership`, not direct module dependency on an external database. For ServiceEvents, `ServiceEventAudienceScope` rows are the ordinary-user visibility source and match by active primary `ChurchStructureMembership`; zero-row events fail closed for ordinary users. Bible Study normal generation is structure-unit-native: it targets active `UNIT_SMALL_GROUP` leaves from `BibleStudySeriesAudienceScope`, writes meeting audience rows, and uses `generation_key` / `anchor_unit` for identity. Since BS-STRUCT.2A, Bible Study V2 meeting visibility, `/studies/` / Today, and role/worship pickers read meeting audience rows plus active primary membership, and zero-row V2 meetings fail closed. See `docs/CHURCH_STRUCTURE_FOUNDATION_PLAN.md`, `docs/SERVICE_EVENT_AUDIENCE_SCOPE_REDESIGN_PLAN.md`, `docs/SERVICE_EVENT_AUDIENCE_RUNTIME_MIGRATION_PLAN.md`, and `docs/SERVICE_EVENT_AUDIENCE_SELECTOR_INTERACTION_PLAN.md`.

Ministry scheduling requirements from real pilot feedback are recorded in `docs/MINISTRY_SCHEDULING_REQUIREMENTS_PLAN.md`. MO-S.2 is complete: `ServiceEvent` now has required MinistryTeams through explicit `ServiceEventRequiredTeam` rows. MO-S.3 is complete as read-only coverage display comparing those required teams against `TeamAssignment` and `TeamAssignmentMember` data. MO-S.4 is complete as a team-scoped manual scheduling workspace at `/teams/<team_id>/schedule/`. MO-S.4A scheduling semantic cleanup is complete after manual QA. MO-S.5A is complete: `ServiceEvent.rotation_anchor_team` is an optional scheduling hint only. MO-S.5B is complete: the team schedule workspace can prefill editable anchor-based or team-history copy-forward suggestions and writes only on explicit save. `TeamMembership.can_lead` is deprecated/reserved and does not grant scheduling, member-management, or admin permissions; after `MINISTRY-ROLE-SOURCE.1C`, holders of an active lead/coordinator `MinistryTeamRoleAssignment` on a team can schedule that team's assignments (this authority no longer comes from `TeamMembership.role`); staff, superusers, and global assignment managers can schedule any team; ordinary members, membership-`role`-only leads/coordinators without a matching role assignment, and `can_lead`-only members cannot schedule; My Serving provides Teams I manage / 我负责的团队 as the non-staff team leader entry point; the schedule defaults to All event types / 全部类型 while still showing only required-or-already-assigned events within the date window; specific event type filtering still works; ServiceEvent Host / Language display now uses `host_language_unit` and the audience-derived structure fallback, not the retired `ministry_context` FK.

The lightweight modular CMS foundation is implemented through
`MODULAR-CORE.6B`:

- `MODULAR-CORE.1A + FU1` added the central registry, the
  `CMS_ENABLED_MODULES` setting, capability/dependency metadata, feature-gate
  helpers, and template enablement context.
- `MODULAR-CORE.2A` validates registered keys and dependencies (`ministry`
  requires `events`), and `MODULAR-CORE.2B` covers disabled-module surfaces.
- `MODULAR-CORE.3A + FU1` added typed, validated Today provider aggregation;
  `MODULAR-CORE.3B` moved provider bodies into their owning modules.
- `MODULAR-CORE.4A` made ordinary authenticated-user primary module navigation
  registry-driven. Today remains an always-available Core link.
- `MODULAR-CORE.5A` made setup/readiness aggregation provider-based. Ministry
  and studies own their module-specific sections; Church Structure and
  permission/admin checks stay Core, and the shared audience-visibility
  section always runs.
- `MODULAR-CORE.6A` gates module-owned staff-dropdown links, and
  `MODULAR-CORE.6B` gates module-owned Staff Overview cards, counts, queries,
  and workflow links. The `/staff/` route and its Core/staff cards remain
  reachable.

Module disablement is a discoverability/surface gate, not app unloading or
route-level hard-off. Direct module URLs, apps, models, admin registrations,
permissions, setup routes, and the setup/readiness command retain their
existing behavior. `COMMUNITY-EVENTS.1A` builds on this foundation with an
independent registered app, models, admin, and visibility helper. `COMMUNITY-EVENTS.1B`
adds the independent member-facing browse/detail entrance
(`community_activity_list` / `community_activity_detail`) and the ordinary
"Activities" primary-nav entry (gated by module enablement, no route hard-off).
`COMMUNITY-EVENTS.1C` adds the one-row-per-user/activity `ActivitySignup`
lifecycle and POST-only signup/cancel actions for visible published upcoming
activities. Signup remains attendance intent and creates no serving state.
`COMMUNITY-EVENTS.1D-A` adds the bounded member submission + admin publish
gate: active-primary members who are not actively blocked may create
pending-review activities. `COMMUNITY-EVENTS.1D-A-FU1` adds a required
member-selected `ChurchStructureUnit` Activity Scope picker; selected active,
non-overlapping units are saved as audience rows, while the optional scope note
remains staff review context only. Creators may see their own pending rows, and
staff/superusers adjust audience and publish in Django admin. Selected-scope
members gain no pending visibility or signup access. `COMMUNITY-EVENTS.1D-B`
adds a lightweight staff review inbox and request-changes loop: a
staff/superuser-only inbox (`/activities/review/`) and POST-only publish /
request-changes / cancel-reject actions, plus a creator edit + resubmit path
for `changes_requested` activities that returns them to `pending_review`. It
adds the `changes_requested` status and `review_note` / `reviewed_by` /
`reviewed_at` fields and a module-gated staff-dropdown review link, without
Staff Overview counts, Today, My Serving, notifications, or a `ServiceEvent`
link. `COMMUNITY-EVENTS.1E-A` later adds only the minimal module-owned Today
provider for same-day active signups and creator-requested changes.
`COMMUNITY-EVENTS.1F-A` adds primary-creator editing while an activity remains
`pending_review`; `1F-B` adds optional capacity; `1G-A` adds bounded
user-linked co-organizers; and `1H-A` adds complete validated member drafts.
`COMMUNITY-EVENTS-STABILIZATION.1A` moved the implemented lifecycle to manual
QA, and `COMMUNITY-EVENTS-STABILIZATION.1B` records the user-confirmed pass. A
limited trial is acceptable under the existing stabilization boundary.
Waitlist, attendee list, check-in, notifications, comments, payments, calendar
integration, broader Today browse/discovery, Staff Overview cards,
setup/readiness, any `ServiceEvent` relationship, My Serving integration, and
the separate Checklist product require separately approved slices. See
`docs/MODULE_BOUNDARIES.md` for the canonical boundary details.

`RELEASE-HYGIENE.0A` is complete. The GoDaddy administrator bootstrap helper no
longer contains or prints default credentials, fails closed on unsafe password
or existing-user cases unless explicitly overridden, and supports protected
environment configuration for non-interactive use. Repository ignore rules now
cover local secrets, databases/backups, logs, audit output, and agent/browser
artifacts, and committed local ServiceEvent audit outputs were removed. This
milestone did not create an external release archive; the future allowlist-based
release boundary is documented in `docs/DEPLOYMENT_SECURITY.md`.

## 3. Module Boundaries

### A. Daily Reading

Includes:
- Reading plans
- Active plans
- Plan introduction page
- Reading guide posts
- Text reader
- Audio reader
- Structured passages
- Check-in
- Reading calendar
- Group progress
- Reflections / replies
- Reflection Wall
- Reflection reporting/moderation

Does not include:
- Bible study schedule
- Worship songs
- Service team scheduling
- Lighting team operations

### B. Prayer

Includes:
- Prayer requests
- Prayer Wall
- Visibility
- Anonymous posts
- I prayed
- Answered / Closed status
- Comments / encouragement
- Reporting / hiding / moderation

Does not include:
- Pastoral counseling case management
- Private counseling notes
- Sensitive personal data beyond the prayer request itself

### C. Bible Study

Implemented V2 module. V1 `BibleStudySession` / guide / worship-song schema is retired and removed from current models.

Includes:
- Bible study series
- Bible study meetings
- Thursday pre-study
- Friday study schedule
- Scripture reference
- Study guide
- Discussion questions
- Draft/published/completed/cancelled workflow
- Structure audience rows and active primary membership for approved ordinary visibility
- Bible Study meeting roles with My Serving confirmation for linked users
- Permission-controlled editing

### D. Bible Study Worship Set

Implemented on the V2 Bible Study meeting path.

Includes:
- Songs before Bible study
- Song order
- Title
- Key
- YouTube link
- Chord link
- Lyrics link
- Pianist / worship lead notes
- Manager-only editing

Does not include:
- Full song library
- Automatic transposition
- Copyright management
- Full worship ministry system

### E. ServiceEvent Foundation

Implemented V1 foundation.

Includes:
- Generic church event abstraction
- Sunday service
- Bible study event
- Special meeting
- Conference
- Gospel music night
- Baptism
- Other event type
- Start/end date and time
- Location and meeting link
- Draft/published/completed/cancelled workflow
- Audience rows through `ServiceEventAudienceScope`
- Host / Language display through `host_language_unit`
- Permission-controlled editing

Does not include:
- Ministry team scheduling
- Team assignments
- Availability
- Swap requests
- Checklists
- Service review notes
- Worship flow management
- Replacement for BibleStudyMeeting or CommunityActivity

Future planning may add CM/EM participating structure context, but it should use
appropriate `ChurchStructureUnit` rows rather than `MinistryTeam` records or a
revived legacy `MinistryContext` model.

### F. Ministry Operations

Ministry Operations is partially implemented.

Implemented V1 foundation includes:
- Ministry teams
- Team memberships
- Team leaders/coordinators
- User-linked and display-name-only memberships
- ServiceEvent-based manual team assignments
- Required MinistryTeams on ServiceEvent through an explicit `ServiceEventRequiredTeam` relationship
- TeamAssignment
- TeamAssignmentMember
- Per-member confirmation
- My Serving Page
- Lighting Team Pilot Data import support
- Lighting Team Pilot setup UI
- Playbook link
- Non-sensitive assignment notes

Future pieces include:
- Basic checklist
- Service review notes
- Availability
- Swap requests
- Reminder automation
- Multi-team dashboard
- Limited rotation/copy-forward helper, completed as bounded MO-S.5A/MO-S.5B ministry scheduling work

Lighting Team should be the first pilot, but there should not be a LightingTeam-specific data model. Models should remain generic enough for other ministry teams.

### G. Church Structure Boundaries

Planning clarification:
- Fellowship / small-group structure is not `MinistryTeam`.
- Small-group coworker roles such as C/E/O/W/F should not use TeamAssignment.
- `BibleStudyMeetingRole` is the per-meeting Bible Study responsibility model.
- CM and EM are ministry contexts / language ministries, not MinistryTeam records.
- There is no fake Combined Ministry record; combined events should involve both CM and EM.
- Community Activities should use the shared `ChurchStructureUnit`-based audience-scope foundation for signup visibility rather than being forced into ServiceEvent or inventing a separate legacy-only audience segment system.
- The current local hierarchy should not hard-code Church -> CM/EM -> District -> SmallGroup forever; use `ChurchStructureUnit` and explicit audience rows rather than reintroducing legacy structure tables.

### H. Long-Term CMS Product Scope

These are final CMS product directions, not authorization to implement them now. "Not V1" or "not now" means deferred unless separately planned and approved; it does not mean outside the final product.

Future CMS scope may include:
- Prayer Wall continued refinement.
- Bible Study / small group attendance.
- Notifications through email, SMS, WeChat, and app notifications.
- Pastor/staff Official Announcements V1 is now bounded in
  `docs/ANNOUNCEMENTS_V1_PLAN.md`; implementation remains unapproved and not
  started.
- Group leader dashboard.
- Children, family, couples, and newcomer care workflows.
- Activities signup, check-in, and capacity management.
- Resources, materials, and file center.
- Finer permission matrix for ministry role, small group leader, district leader, and staff capabilities.

The ERP boundary remains: no finance, payroll, HR/personnel system, full CRM, legal/compliance system, or broad sensitive contact import. Children/family care workflow is future CMS scope, but child security check-in is not automatically authorized by that scope.

### I. Modular Adoption and Coexistence

Recorded as a product principle from June 2026 demo feedback:

- The CMS must not require a church to replace all existing church apps at once.
- Modules should be adoptable one by one; existing module boundaries and the local Church Structure model support this without requiring every external church system to be replaced at once.
- External tools may coexist with CMS modules (for example, a small group may keep using 微读圣经 for reading/study content while the CMS provides structure, scheduling, and audience scope).
- Integration initially means link/reference/mapping, like the existing "link to Google Docs playbooks, do not import them" rule. Future structure-database integration, if approved, should be a sync/adaptor/local-shadow design into local Church Structure models, not direct module coupling to an external database.
- No external-system integration work is implemented or authorized by this principle alone; any future integration requires its own separately approved plan.

See `docs/CHURCH_STRUCTURE_MAP_AND_SETUP_READINESS_PLAN.md`.

## 4. Completed V1 Features

### Daily Reading

- ReadingPlan / ActivePlan
- Plan Introduction
- Reading Guide Posts
- Structured ReadingPlanDayPassage
- Text reader
- Audio reader
- Check-in
- Reading calendar
- Group progress
- Reflection / reply
- Reflection Wall
- Anonymous display
- Report / hide / moderation
- Staff reading plan editor
- Bilingual UI

### Prayer

- Prayer requests
- Prayer Wall
- Visibility
- Anonymous display
- I prayed
- Answered / Closed
- Comments
- Edit / delete
- Report / hide / moderation

### Bible Study

- BibleStudySeries
- BibleStudyMeeting
- BibleStudyLesson / guide content on the V2 path
- BibleStudyMeetingRole with My Serving confirmation state
- Thursday pre-study date/time
- Friday study date/time
- Scripture reference
- Study guide
- Discussion questions
- Draft/published/completed/cancelled workflow
- Structure audience rows plus active primary membership for approved ordinary visibility
- Bilingual UI
- Permission-controlled editing

Current V2 correction after browser review:
- The active Bible Study flow is Bible Study Schedule / 查经安排 -> Weekly Bible Study Guide / 查经指引 -> generated Small Group Bible Study Meetings / 小组查经聚会.
- `BibleStudySeries` serves as the internal Bible Study Schedule model.
- Generated meetings reference the weekly guide through `BibleStudyMeeting.lesson` and derive schedule through `meeting.lesson.series`.
- Guide content is not copied into generated meetings; meeting detail displays current parent guide content dynamically.

### Bible Study Worship Set

- Meeting-level worship songs
- Song order
- Title / title_en
- Key
- YouTube link
- Chord link
- Lyrics link
- Notes
- Bilingual display
- Manager-only editing

### ServiceEvent Foundation

- ServiceEvent
- Sunday Service / Bible Study / Special Meeting / Conference / Gospel Music Night / Baptism / Other event types
- Start and end datetime
- Location
- Meeting link
- Draft/published/completed/cancelled workflow
- Audience rows through `ServiceEventAudienceScope`
- Active primary `ChurchStructureMembership` matching for ordinary visibility
- Zero-row ordinary-user fail-closed behavior
- Bilingual UI
- Permission-controlled editing

### Ministry Team Operations Foundation

- MinistryTeam
- TeamMembership
- TeamAssignment
- TeamAssignmentMember
- Team leaders/coordinators
- User-linked and display-name-only memberships
- Manual ServiceEvent-based team assignments
- Per-member confirmation
- Playbook link
- Non-sensitive notes
- Bilingual UI
- Permission-controlled team management
- Team lead/coordinator scoped member management
- Team lead/coordinator scoped assignment management

### Accounts / Permissions

- Profile
- Password reset support for users without email
- Staff user admin
- ChurchRoleAssignment
- Capability helpers
- Scoped group progress

## 5. Current Phase

Current phase:

Reading, Prayer, Bible Study, Bible Study Worship Set, ServiceEvent Foundation, MinistryTeam Foundation, TeamAssignment V1, My Serving Page V1, and Lighting Team Pilot Data/setup support reached pilot validation on `v0.9-pilot-rc1`. Pilot validation passed with no known P0/P1 blockers.

Post-Pilot Backlog Triage led into the completed Church Structure migration and related retirement work. CS-H.1 through CS-H.10, PP-SA.1 through PP-SA.5, ServiceEvent audience/legacy-field retirement, Bible Study V2 structure-native generation/visibility, V1 schema retirement, and legacy structure table retirement are complete for the current codebase. See `docs/POST_PILOT_BACKLOG_TRIAGE.md`, `docs/FLEXIBLE_CHURCH_STRUCTURE_AND_AUDIENCE_SCOPE_DESIGN.md`, `docs/CHURCH_STRUCTURE_MAPPING_AND_MEMBERSHIP_STRATEGY.md`, `docs/CHURCH_STRUCTURE_SEEDING_VERIFICATION.md`, `docs/CHURCH_STRUCTURE_MEMBERSHIP_BACKFILL_VERIFICATION.md`, `docs/CHURCH_STRUCTURE_MEMBERSHIP_DESIGN.md`, and `docs/STAFF_ADMIN_SURFACE_EXPANSION_PLAN.md`.

Current foundation step:

Bible Study V2 Flow QA has passed. Historical CS-F bridge work served the pilot baseline; current Bible Study V2 and ServiceEvent paths use Church Structure audience rows plus active primary membership, and the retired `MinistryContext` table/FK paths should not be described as active runtime structure.

MO-S.1 records real pilot feedback that staff need required MinistryTeam selection when creating or batch-creating ServiceEvents, TeamAssignment pages need required-team coverage with assigned coworkers and confirmation status rather than only counts, and ministry team leaders need an efficient same-type event scheduling entry point for their own team. MO-S.2 completes the first implementation slice by letting staff select required teams on ServiceEvent single create/edit and recurring batch-create. MO-S.3 completes the read-only coverage slice: the `TeamAssignment` list is the primary operational coverage surface, assignment detail shows compact event coverage, ServiceEvent detail shows coverage only to staff/service-event or team-assignment managers, ordinary event viewers do not see coworker coverage, `/staff/` adds upcoming required-team gap counts, and browser automation was blocked but user-completed manual QA accepted the UI. MO-S.4 completes the manual team-leader scheduling workspace, and MO-S.4A completes scheduling semantic cleanup after manual QA: Team detail shows Schedule Team / 安排团队服事 only for users who can manage that team's assignments; staff, superusers, and global assignment managers can schedule any team; Lead and Coordinator roles can schedule their own team assignments; ordinary members, `can_lead`-only members, and unrelated users cannot schedule; `TeamMembership.can_lead` is deprecated/reserved and does not grant scheduling, member-management, or admin permissions; My Serving provides Teams I manage / 我负责的团队 as the non-staff team leader entry point; the workspace defaults to All event types / 全部类型 while still showing only required-or-already-assigned events within the date window; specific event type filtering still works; ServiceEvent Host / Language display is structure-native; one active in-page schedule/edit form is selected by event or assignment query parameters.

Required-team coverage is a ministry scheduling clarity need, not Checklist V1. Checklist, availability, swap requests, reminder automation, notifications, automatic scheduling, and advanced scheduling remain future unless separately planned.
Checklist V1 remains deferred and should not be revived without pilot feedback proving checklist need separately from required-team coverage.

Before new large features:
- Keep tests passing.
- Preserve bilingual behavior.
- Avoid top-nav clutter; the normal logged-in top nav may include My Serving, but not Ministry Teams or Team Assignments.
- Keep Daily Reading from absorbing unrelated ministry workflows.
- Keep Bible Study from becoming a full event or ministry scheduling system.
- Keep ServiceEvent, MinistryTeam, TeamAssignment, and My Serving workflows generic until pilot workflows are separately planned.

## 6. Roadmap

### Phase 1: Daily Reading Core V1 Closure

Status: mostly complete / stabilization.

Tasks:
- Manual QA checklist
- UI polish
- Production readiness review
- Regression tests for visibility / hidden / language behavior
- No more major Daily Reading features unless necessary

### Phase 2: Prayer V1 Stabilization

Status: mostly complete / stabilization.

Tasks:
- UI polish
- Regression tests
- Possible future digest/reminder only after real use

### Phase 3: Bible Study Module V1

Status: historical/superseded. V1 was implemented for the pilot era, then retired from app/admin runtime and removed from current schema. The active path is Bible Study V2.

Historical V1 included:
- BibleStudySeries
- BibleStudySession
- Thursday pre-study date
- Friday study date
- Scripture reference
- Study guide
- Discussion questions
- Draft/published/completed/cancelled status
- Scope: global / district / small_group
- Permission-controlled editing

### Phase 4: Bible Study Worship Set V1

Status: historical/superseded. V1 session-level worship schema was removed with V1; current worship-set planning belongs to V2 `BibleStudyMeeting`.

Historical V1 included:
- Session-level worship songs
- Song order
- Title
- Key
- YouTube link
- Chord link
- Lyrics link
- Worship lead / pianist notes

Do not build a full song library.

### Phase 5: ServiceEvent Foundation

Status: implemented / QA.

Includes:
- Generic church event abstraction
- Sunday service
- Bible study event
- Special meeting
- Conference
- Gospel music night
- Baptism

This should prepare future ministry scheduling, not become a full event-management system.

### Phase 6: Ministry Team Operations V1

Status: MinistryTeam + TeamMembership Foundation, TeamAssignment V1, My Serving Page V1, and limited Lighting Team Pilot Data/setup support implemented / QA.

Implemented:
- MinistryTeam
- TeamMembership
- TeamAssignment
- TeamAssignmentMember
- Assignment confirmation
- My Serving Page
- Lighting Team Pilot Data import support
- Lighting Team Pilot setup UI
- Playbook link
- Non-sensitive assignment notes

Future:
- Basic checklist
- Review notes

Lighting Team is the pilot, but models must remain generic.

### Phase 7: Lighting Team Pilot

Status: limited pilot data import and setup UI support implemented / QA.

Only import or model:
- Future 2-3 months of assignments
- Lighting team members
- Assigned person
- Special event note
- Playbook link

Do not import all historical 2021-2026 data initially.

Do not add a LightingTeam-specific model. Pilot data should continue to use the generic ServiceEvent, MinistryTeam, TeamMembership, TeamAssignment, and TeamAssignmentMember models.

### Phase 8: Ministry Operations Enhancements

Only after real use:
- Availability
- Swap request
- Reminder automation
- Multi-team dashboard
- Advanced checklist
- Service review history

### Phase 9: Church Structure / Bible Study Roles / Community Activities Planning

Historical milestone sequence (retained as chronology, not current schema or
runtime guidance; use Section 2 and the canonical documents in
`docs/README.md` for current truth):
- Church structure domain plan completed.
- Small group coworker roles planning completed.
- BS-V2.5A Simple `BibleStudyMeetingRole` UI completed.
- BS-V2.5B Group-level worship set UI completed.
- BS-V2.6.0 Bible Study V2 Schedule/Scope Replan completed.
- BS-V2.6.1 Staff IA cleanup completed.
- BS-V2.6.2 Treat `BibleStudySeries` as Bible Study Schedule / 查经安排 completed.
- BS-V2.6.3 Schedule lifecycle fields completed.
- BS-V2.6.4 Schedule scope fields completed.
- BS-V2.6.5 Manual idempotent generation of small-group meetings from guide/scope completed.
- BS-V2.6.6 Normal user V2 landing integration completed.
- BS-V2.6.7 Bible Study V2 Flow QA passed.
- CS-F.1 MinistryContext bridge foundation completed.
- CS-F.2 MinistryContext Bible Study Schedule scope completed.
- CS-F.3 optional ServiceEvent MinistryContext label foundation completed.
- CS-H.1 Flexible Church Structure and Audience Scope Design Doc completed.
- CS-H.2 model-only `ChurchStructureUnit` foundation completed.
- CS-H.2A `ChurchStructureUnit` model hardening completed.
- CS-H.3 current structure mapping and membership strategy completed.
- CS-H.3B nullable legacy mapping fields completed.
- CS-H.3C idempotent structure seeding/mapping command completed.
- CS-H.3D production/staging seeding verification completed.
- CS-H.3E seeded structure data QA closure completed.
- CS-H.4 ChurchStructureMembership Design Doc completed.
- CS-H.5A ChurchStructureMembership model-only foundation completed.
- CS-H.5B ChurchStructureMembership helper/validation hardening completed.
- CS-H.5C ChurchStructureMembership backfill command completed.
- CS-H.5D ChurchStructureMembership production/staging backfill verification completed by user-attested GoDaddy run; exact output counts were not recorded.
- CS-H.5E Admin clarity for legacy structure vs future structure/membership foundation completed.
- CS-H.6 Signup requested-unit flow design completed.
- CS-H.6A Signup request capture implementation planning completed.
- CS-H.6B Signup request capture completed.
- CS-H.6D Profile request capture completed.
- CS-H.7 Admin approval workflow design completed.
- CS-H.7A Membership approval workflow implementation plan completed.
- CS-H.7B/C Membership approval capability + pending request list completed.
- CS-H.7D Membership request detail + approve/reject actions completed.
- CS-H.7E `Profile.small_group` approval sync completed.
- CS-H.8 Integrated membership request flow checkpoint completed.
- CS-H.9 Membership request UX hardening completed.
- CS-H.10 CMS hardening checkpoint completed.
- GROUP-MEMBERSHIP-MANAGE.1A delegated small-group member add/end in My Units completed and QA-passed.
- GROUP-MEMBERSHIP-REQUEST.1B delegated small-group pending-request approve/reject in My Units completed and QA-passed; the global staff queue remains available.
- PP-SA.1 Staff Admin Surface Expansion Plan completed as docs-only planning.
- PP-SA.2 Read-Only Staff Dashboard Overview completed at `/staff/` with counts and links only for existing workflows.
- PP-SA.3 Membership / Admin Workflow Polish completed as staff membership request workflow polish.
- PP-SA.4 Moderation / Admin Queues completed at `/staff/moderation/` as a read-only queue over existing report/hidden data.
- PP-SA.5 Ministry Ops Admin Improvements completed on `/staff/` as read-only ministry ops health indicators.
- MO-S.1 Ministry Scheduling Requirements Plan completed as docs-only planning from real pilot feedback.
- MO-S.2 event required-team model/design implementation completed.
- MO-S.3 assignment coverage display for required teams completed.
- MO-S.4 team-leader scheduling workspace for same-type events completed.
- MO-S.4A scheduling semantic cleanup completed after manual QA.
- MO-S.5A rotation anchor foundation completed.
- MO-S.5B limited copy-forward suggestion helper completed.
- SE-AS.1 ServiceEvent Audience Scope Redesign Plan completed as docs-only planning.
- SE-AS.2 model-only `ServiceEventAudienceScope` foundation completed.
- SE-AS.3 ServiceEvent Audience Runtime Migration Plan completed as docs-only planning in `docs/SERVICE_EVENT_AUDIENCE_RUNTIME_MIGRATION_PLAN.md`. It renumbers later milestones: SE-AS.4 runtime visibility rule with legacy fallback at that time, SE-AS.5 staff audience selector UI/display, and SE-AS.6 backfill/compatibility/cleanup planning. SE-AS.6C apply/backfill, SE-AS.7A write-path guard, SE-RETIRE.1B zero-row runtime fallback retirement, SE-FIELD-RETIRE.1A legacy scope field removal, and SERVICE-EVENT-CONTEXT.1C Host / Language FK removal are now complete.
- SE-AS.4 ServiceEvent Audience Runtime Visibility Rule completed: events with `ServiceEventAudienceScope` rows use audience rows for ordinary-user visibility; at SE-AS.4 time events with no rows kept legacy `scope_type` / `district` / `small_group` plus `Profile.small_group` behavior; no SE-AS.5 selector UI, form/template audience picker, Community Activities, CS-MAP.3, or CS-SETUP.1 was added. Historical note: SE-AS.4 originally matched audience rows through the legacy belonging rule; CS-CORE.2B-A later switched those audience-row matches to active primary `ChurchStructureMembership`, SE-RETIRE.1B later retired the zero-row runtime fallback, and SE-FIELD-RETIRE.1A later removed the legacy scope fields.
- SE-AS.5A ServiceEvent Audience Selector Interaction Plan completed as docs-only planning in `docs/SERVICE_EVENT_AUDIENCE_SELECTOR_INTERACTION_PLAN.md`: picker placement, legacy fallback interaction, staff/ordinary display wording, empty/unmapped selection handling, recurring/batch behavior, and non-goals are recorded; no code, template, form, view, model, test, migration, static, backfill, or runtime behavior change was added.
- SE-AS.5 ServiceEvent Staff Audience Selector UI and Display completed: single create/edit and recurring create expose an optional `ChurchStructureUnit` audience picker; selected units save/replace `ServiceEventAudienceScope` rows; recurring preview writes no rows; recurring create applies one selected audience set to newly created events; staff detail shows Structure audience plus stored legacy-field context when relevant; ordinary detail does not expose audience architecture terms. Historical SE-AS.5 clearing/empty-picker behavior restored legacy fallback, but SE-AS.7A later superseded it: empty picker saves now convert valid legacy fields into audience rows or fail validation, and SE-RETIRE.1B makes zero-row events fail closed for ordinary users. No schema/migration, legacy-field removal/deprecation, Community Activities, CS-MAP.3, CS-SETUP.1, or Required Ministry Teams / Rotation Anchor / TeamAssignment / My Serving behavior change was added.
- SE-AS.5B post-commit cleanup completed: fallback copy now explains that legacy fields apply only when no structure audience is selected, and the read-only staff structure map now uses clearer `Church Structure & Setup Check` wording plus descendant-inclusive covered-member counts. SE-AS.5C / CS-MAP.2B corrected the tree interaction: ServiceEvent audience picker sections stay visible, and both the picker and `/staff/structure/` expand/collapse hierarchy nodes by level. No runtime visibility, schema, migration, backfill, setup/edit UI, roster, or membership-source migration was added.
- DOCS-AS.1 records the shared `ChurchStructureUnit` audience-scope direction: app modules should select `ChurchStructureUnit` rows through app-specific join models rather than adding more legacy-only multi-select scope fields.
- BS-AS.1 Bible Study Schedule audience scope using `ChurchStructureUnit` completed, as the first narrow runtime consumer implemented. `BibleStudySeriesAudienceScope` joins `BibleStudySeries / 查经安排` to `ChurchStructureUnit`; historical BS-AS.1 generation resolved selected units to eligible legacy `SmallGroup` rows. Current normal generation is structure-unit-native, targets active `UNIT_SMALL_GROUP` leaves, writes meeting audience rows, and uses `generation_key` / `anchor_unit`; `BibleStudyMeeting.small_group` was removed in BS-MEETING-MIRROR.1A. Since BS-STRUCT.2A, V2 visibility reads meeting audience rows plus active primary membership and zero-row V2 meetings fail closed.
- BS-AS.2 completed: reusable server-rendered `ChurchStructureUnit` audience picker (searchable, chips, tree order, no-JS fallback, vanilla-JS convenience clearing, backend validation authoritative); compact list/card scope labels and wrapped/chip detail labels with the root prefix omitted; active management lists and related detail lists hide cancelled schedules/guides/meetings; generation still treats cancelled meetings as existing/skipped.
- BS-AS.2A completed: bilingual audience-picker search `aria-label`, and chip remove buttons include the selected unit label in their `aria-label`; no behavior/schema/visibility changes.
- BS-AS QA follow-up completed; BS-AS.2B fixed the audience picker mobile CSS no-go.
- CS-MAP.1 Church Structure Map / Setup Readiness Plan completed as docs-only planning in `docs/CHURCH_STRUCTURE_MAP_AND_SETUP_READINESS_PLAN.md`, recording June 2026 demo feedback (modular adoption/coexistence; pastor/staff structure map and setup readiness). No runtime behavior changed.
- CS-MAP.2 read-only Staff Structure Map + Mapping Health completed at `/staff/structure/`: permission-protected read-only staff page rendering the active `ChurchStructureUnit` hierarchy with bilingual names, hierarchical node-level expand/collapse, descendant-inclusive covered-member counts, and setup-readiness indicators including direct active primary memberships on parent units. Historical/superseded: at CS-MAP.2 time this page still showed mapping context from active legacy rows; those legacy structure rows/tables were later retired. No write actions, no member rosters, no runtime visibility changes.
- SE-AS.5 is complete as the bounded staff selector/display implementation; SE-AS.6C apply/backfill, SE-AS.7A write-path guard, and SE-RETIRE.1B zero-row fallback retirement later completed as separate slices. Community Activities, CS-MAP.3, CS-SETUP.1, and field-level legacy cleanup are not pulled forward by SE-AS.5 completion.
- CS-MAP.3 optional setup readiness checklist remains optional and unapproved. CS-SETUP.1 limited structure setup/edit UI is not approved; it is gated on CS-MAP.2 evidence plus a separate design doc (unit↔legacy sync, edit permissions, effect on stored audience rows). CS-SETUP.1A is complete as a docs-only risk/design pass in `docs/CHURCH_STRUCTURE_MAP_AND_SETUP_READINESS_PLAN.md` Section 13: it records the risk analysis and design contract and splits CS-SETUP.1 into separately approvable CS-SETUP.1B (label/sort-order only), 1C (mapping review/edit), 1D (create/move/deactivate), and 1E (membership/belonging) sub-milestones; none of 1B–1E is approved and no runtime/schema behavior changed.
- `COMMUNITY-EVENTS.1A` adds the independent `community_events` module,
  `CommunityActivity`, and its app-specific
  `CommunityActivityAudienceScope`. Ordinary visibility requires a published
  activity plus an audience row matching the user's active primary membership
  unit or an ancestor; zero rows fail closed. The slice adds Django admin but
  no member routes/templates, signup, primary nav, Today, My Serving, or
  `ServiceEvent` relationship.
- `COMMUNITY-EVENTS.1B` adds the independent member-facing browse/detail
  entrance (`community_activity_list` at `/activities/` and
  `community_activity_detail` at `/activities/<id>/`) plus the ordinary
  "Activities" / "活动" primary-nav entry (after Church Gatherings, before My
  Serving), gated by module enablement with no route hard-off. The list uses
  the structure-native visibility helper for upcoming published activities; the
  detail view denies with 404 when `can_be_seen_by` is false.
- `COMMUNITY-EVENTS.1C` adds `ActivitySignup` plus POST-only signup and
  cancellation. A cancelled row is retained and reactivated by a later signup;
  new signup requires a visible, published, upcoming activity for every user,
  including staff. It adds no approval, capacity/waitlist, Today, My Serving,
  Staff Overview, setup/readiness, serving records, or `ServiceEvent`
  relationship.
- `COMMUNITY-EVENTS.1D-A` adds member submission at `/activities/new/` plus
  the Django-admin publish gate. Eligible members create `pending_review`
  activities; active submission blocks deny creation. The follow-up
  `COMMUNITY-EVENTS.1D-A-FU1` requires members to select one or more active,
  non-overlapping structure units and saves those selections as audience rows
  in the same transaction. The optional Activity Scope note never controls
  visibility. Creators may see pending submissions, but selected-scope ordinary
  users cannot see them before staff publication.
- `COMMUNITY-EVENTS.1D-B` adds a lightweight staff review inbox and
  request-changes loop. It adds the `changes_requested` status and
  `review_note` / `reviewed_by` / `reviewed_at` fields, a staff/superuser-only
  inbox at `/activities/review/`, POST-only publish / request-changes (note
  required) / cancel-reject actions on `/activities/<id>/review/`, and a
  creator edit + resubmit path at `/activities/<id>/edit/` that transactionally
  replaces audience rows and returns the activity to `pending_review`. A
  module-gated staff-dropdown review link was added. It adds no Staff Overview
  counts, Today, My Serving, notifications, serving records, or `ServiceEvent`
  relationship, and never makes pending-review or changes-requested activities
  visible to selected-scope ordinary users.
- `COMMUNITY-EVENTS.1F-A` allows the primary creator to edit an activity while
  it stays `pending_review`; selected-scope ordinary visibility and staff
  review authority are unchanged.
- `COMMUNITY-EVENTS.1E-A` adds the module-owned minimal Today provider. It
  shows active-signup published visible activities happening today and
  creator-owned `changes_requested` reminders only. Later-this-week signups
  and `pending_review` submissions are not rendered. Module disablement skips the provider and its queries. It
  adds no My Serving or serving action-center context, serving record, Staff
  Overview, setup/readiness, notification, capacity/waitlist, or
  `ServiceEvent` relationship.
- `COMMUNITY-EVENTS.1F-B` adds nullable `capacity_limit` to
  `CommunityActivity`, the shared create/edit field, active-signup counts on
  list/detail, and a serialized full-capacity guard on signup/reactivation.
  Null means unlimited and a positive integer is the maximum active
  `signed_up` count. It adds no waitlist, attendee list, check-in,
  notification, serving state, or `ServiceEvent` relationship.
- `COMMUNITY-EVENTS.1H-A` adds complete validated member drafts. Create and
  draft-edit surfaces offer Save draft and Submit for review to the primary
  creator; audience rows, capacity, and co-organizers save transactionally.
  Linked co-organizers may view/edit a draft but cannot manage links or submit
  it. Drafts are hidden from selected-scope ordinary users, signup, the review
  inbox, Today, My Serving, serving state, and `ServiceEvent`.
- `COMMUNITY-EVENTS-STABILIZATION.1A` moves V1 to manual QA and stabilization.
  `COMMUNITY-EVENTS-STABILIZATION.1B` records the user-confirmed manual QA pass,
  and the latest setup-readiness audit records 0 blockers and 19 warnings.
  The project is usable for a limited trial under the existing stabilization
  boundary, not certified for production deployment. These checkpoints add no
  runtime behavior.
- Boundary: `ChurchStructureMembership` runtime visibility is consumer-specific. ServiceEvent structure-audience rows switched in CS-CORE.2B-A and zero-row events fail closed after SE-RETIRE.1B. Bible Study V2 audience-row visibility / Today / role-worship pickers use meeting audience rows plus active primary membership after BS-STRUCT.2A. Legacy `SmallGroup`, `District`, `MinistryContext`, `Profile.small_group`, and V1 `BibleStudySession` are removed from current models; historical docs and immutable migrations may still name them.
- Later consumer migration only after phased planning.
- Later role-aware editing permissions.
- ServiceEvent legacy scope field retirement is complete (SE-FIELD-RETIRE.1A);
  only immutable historical migrations/docs should still name those fields.
- No further Community Activities expansion without separate approval,
  including waitlist, attendee list, check-in, notifications, comments,
  payments, calendar integration, broader Today browse/discovery, Staff
  Overview cards, setup/readiness, a `ServiceEvent` relationship, or My Serving
  integration.
- Checklist V1 remains deferred.
- Official Announcements implementation is split into
  `ANNOUNCEMENTS.1A`–`1E`; this docs-only plan does not approve any runtime
  slice.

## 7. Explicit Non-Goals

This project should not become a full church ERP.

Do not build:
- Finance / offering
- Payroll
- Full CRM
- Child security check-in unless separately authorized
- Legal/compliance system
- Asset management
- Complete HR/personnel system
- Automatic scheduling algorithm in early phases
- Full worship song library in early phases
- Complex lighting scene database
- ShowXpress training database
- Private counseling notes
- Zoom passwords
- Broad sensitive contact import

Do not copy entire Google Docs or Google Sheets into the database.
The system should manage structured workflow and responsibility, not swallow every document.
Training docs, useful links, and detailed tips can remain in Google Docs and be linked.

## 8. Permission Model

Do not model church roles as a strict hierarchy. Use capability-based permissions.

Current roles may include:
- pastor
- elder
- deacon
- district_leader
- group_leader
- coworker

Capabilities are granted through active ChurchRoleAssignment rows, plus staff/superuser override.

Existing examples:
- CAP_PUBLISH_READING_GUIDES
- CAP_MANAGE_BIBLE_STUDIES
- CAP_PUBLISH_BIBLE_STUDY_GUIDES
- View group/district/all progress capabilities
- Moderation capabilities
- Manage reading plans / users where applicable

Future capabilities should be added only when a future workflow needs them.

Implemented service and ministry foundation capabilities:
- CAP_MANAGE_SERVICE_EVENTS
- CAP_MANAGE_MINISTRY_TEAMS
- CAP_MANAGE_TEAM_ASSIGNMENTS

## 9. Codex Task Rules

For future Codex prompts:
- Run tests before and after substantial changes.
- Keep each task narrow.
- Do not add unrelated features.
- Do not rename URLs unless explicitly requested.
- Do not add top-nav clutter beyond the intentional My Serving entry for normal logged-in users.
- Preserve bilingual UI.
- Tests with language-specific text must set `session["language"]`.
- Prefer contextual links over global navigation.
- Respect module boundaries.
- Do not introduce sensitive data fields without explicit approval.
- Do not build automatic scheduling until manual scheduling workflow is proven.
- Do not replace Google Docs for playbooks; link to them.

## 10. Definition of Done

For feature tasks:
- Model/design fits module boundary.
- Permissions are clear.
- User-facing text is bilingual.
- Normal user and staff behavior are tested.
- Hidden/private/group-scoped data does not leak.
- Existing all-app tests pass.
- Navigation is not cluttered.
- No unnecessary migrations.
- No unrelated refactors.

## 11. Next Recommended Work

Current direction: the limited trial readiness closure is complete, with
Community Activities V1 QA-passed by user confirmation and the setup-readiness
audit reporting 0 blockers plus 19 warnings. Before starting the limited trial,
the product owner intends to separately approve and implement
`ANNOUNCEMENTS.1A`–`1E`, then create a bilingual staff setup guide that includes
the shipped announcements setup flow. The current docs-only plan does not
authorize those runtime slices or the guide. Do not reopen legacy Church
Structure cleanup or add Community Activities features merely because the trial
is starting.

Short next-candidate list:

- separately approve and implement the bounded Official Announcements V1
  slices in `docs/ANNOUNCEMENTS_V1_PLAN.md`;
- after Announcements QA closure, write the bilingual staff setup guide from
  shipped behavior;
- Church Structure + Ministry + Bible Study setup/trial-readiness review;
- manual-QA polish based on a real demo;
- My Serving polish only when users report concrete confusion;
- no broad refactors.

Pre-user-trial readiness tooling: SETUP-READINESS.1A is implemented and provides `audit_trial_setup_readiness`, a single **read-only** management command that summarizes setup/data readiness across the core modules (Church Structure / membership, Ministry Teams, TeamAssignment / My Serving, Bible Study serving, audience visibility, permission/admin) as blockers / warnings / info before inviting real users to a trial. It mutates nothing, has no `--apply`, infers no serving from membership/visibility, and is **not** a production-deployment claim. The ministry-structure portion delegates to `ministry.structure_readiness.run_audit`. The latest recorded run (`--verbose --limit 20 --fail-on-blockers`) reported 0 blockers and 19 warnings: 2 active non-staff users without active primary membership, 6 assignable teams without a role profile, 3 teams missing a required active Lead, 4 assignable teams without active members, and 4 upcoming required-team coverage gaps. Community Activities V1 manual/browser QA passed by user confirmation; `community_events` migrations through `0006` are applied and `migrate --plan` reports no planned operations. See `docs/TRIAL_SETUP_READINESS_RUNBOOK.md`.

Ministry role source-of-truth alignment: MINISTRY-ROLE-SOURCE.1A is a **docs + read-only audit** slice that locks the long-term boundary between `TeamMembership` (membership / candidate pool) and `MinistryTeamRoleAssignment` (the single source of truth for long-term ministry roles and the team-management permission source), with `TeamAssignmentMember` staying event-specific serving and `TeamMembership.role` / `can_lead` kept as transitional/legacy compatibility fields only. It adds `audit_ministry_role_source_alignment` (logic in `ministry/role_source_alignment.py`), a **read-only** command (no `--apply`) that reports drift between the legacy membership roles and the ministry role assignments as blockers / warnings / info. 1A itself changed no permission, mutated no data, switched no source of truth, ran no backfill, and added no migration. MINISTRY-ROLE-SOURCE.1B is implemented as `backfill_ministry_role_assignments_from_memberships` (logic in `ministry/role_source_backfill.py`), a **dry-run-by-default** one-way backfill (membership `lead`/`coordinator` → `MinistryTeamRoleAssignment`) that writes only under explicit `--apply`, changes no permission by running, mutates no `TeamMembership`, never backfills from `can_lead`, and reports team-level manager disagreements as conflicts rather than auto-resolving them (`--apply` not run without explicit approval). **MINISTRY-ROLE-SOURCE.1C is implemented:** `can_manage_ministry_team`, `manageable_assignment_teams`, and related team-management / team-scheduling checks now read active `MinistryTeamRoleAssignment` rows (role_type code in {`lead`, `coordinator`}) for the exact team, not `TeamMembership.role`. After 1C, `TeamMembership.role` is legacy compatibility data and grants no runtime team-management permission; `TeamMembership.can_lead` remains deprecated/reserved and grants none; staff / superuser / global capability behavior is unchanged; the slice is exact-team only and changes no model or migration. **MINISTRY-ROLE-SOURCE.1D is implemented:** the manage-members UI no longer presents `TeamMembership.role` / `can_lead` as a leadership/permission control — `TeamMembershipForm` dropped `role` (normal creates default to `member`; existing legacy `role` preserved untouched on edit) and never included `can_lead`, and the members list shows canonical long-term roles from active `MinistryTeamRoleAssignment` rows only, linking staff to structure setup. **MINISTRY-ROLE-SOURCE.1E-A is implemented** as the dry-run-by-default `cleanup_team_membership_can_lead_flags` command (logic in `ministry/can_lead_cleanup.py`) that clears deprecated `can_lead=True` flags (active + inactive rows, `--team-id` scope) under explicit `--apply`, only setting `can_lead` `True` → `False` and never touching `role`, membership rows, role assignments, or permissions. Later legacy field retirement remains optional and is not the current priority. See `docs/MINISTRY_ROLE_SOURCE_OF_TRUTH_PLAN.md`.

Current foundation status:

CS-F.1 MinistryContext bridge foundation, CS-F.2 MinistryContext Bible Study Schedule scope, and CS-F.3 optional ServiceEvent MinistryContext labeling are complete after the Bible Study V2 Flow QA pass. `v0.9-pilot-rc1` was deployed and pilot validation passed.

Current post-pilot step:

PV-C.1 records pilot validation closure. Pilot validation passed on `v0.9-pilot-rc1`. CS-H.1 through CS-H.10, PP-SA.2 through PP-SA.5, MO-S.1 through MO-S.5B, SE-AS.1 through SERVICE-EVENT-CONTEXT.1C, DOCS-AS.1, BS-AS.1 through BS-AS.2A, BS-STRUCT.1L/1M/1O/1P/2A, BS-MEETING-MIRROR.1A, BS-V1-SCHEMA-RETIRE.1A, CS-MAP.2, and CS-CORE.2C-B are complete. ServiceEvent audience rows use active primary `ChurchStructureMembership`; zero-row events fail closed for ordinary users; legacy scope fields and the legacy `ministry_context` display FK are removed. Bible Study normal generation is structure-unit-native: it targets active `UNIT_SMALL_GROUP` leaves from `BibleStudySeriesAudienceScope`, uses `generation_key = normal-unit:{unit_id}` and `anchor_unit`, and writes meeting audience rows; `BibleStudyMeeting.small_group` was removed in BS-MEETING-MIRROR.1A; V1 schema was removed in `studies/0012`; role confirmation fields were added in `studies/0013` and My Serving owns the confirm action. Since BS-STRUCT.2A, V2 meeting visibility, `/studies/` / Today, and role/worship pickers read meeting audience rows plus active primary membership; zero-row V2 meetings fail closed. Runtime consumers are now explicitly split by consumer rather than all primarily legacy. See `docs/POST_PILOT_BACKLOG_TRIAGE.md`, `docs/FLEXIBLE_CHURCH_STRUCTURE_AND_AUDIENCE_SCOPE_DESIGN.md`, `docs/CHURCH_STRUCTURE_MAPPING_AND_MEMBERSHIP_STRATEGY.md`, `docs/CHURCH_STRUCTURE_SEEDING_VERIFICATION.md`, `docs/CHURCH_STRUCTURE_MEMBERSHIP_BACKFILL_VERIFICATION.md`, `docs/CHURCH_STRUCTURE_MEMBERSHIP_DESIGN.md`, `docs/STAFF_ADMIN_SURFACE_EXPANSION_PLAN.md`, `docs/MINISTRY_SCHEDULING_REQUIREMENTS_PLAN.md`, `docs/SERVICE_EVENT_AUDIENCE_SCOPE_REDESIGN_PLAN.md`, `docs/SERVICE_EVENT_AUDIENCE_RUNTIME_MIGRATION_PLAN.md`, and `docs/SERVICE_EVENT_AUDIENCE_SELECTOR_INTERACTION_PLAN.md`.

Future foundation planning:

`ChurchStructureUnit` seeding/mapping now exists only as an explicit management command, passed GoDaddy production/staging verification, and completed seeded structure data QA closure. SE-AS.1 records the docs-only `ServiceEvent` audience-scope redesign recommendation; SE-AS.2 adds the `ChurchStructureUnit`-linked audience scope beside legacy fields as a model-only foundation; SE-AS.4 made those rows the ServiceEvent ordinary-user visibility source when rows exist (zero-row events fell back to legacy `scope_type` / `district` / `small_group` plus `Profile.small_group` at that time); CS-CORE.2B-A switched audience-row matching to active primary membership; SE-AS.6C apply is complete; SE-AS.7A stops normal zero-row writes; SE-RETIRE.1B retired the zero-row runtime fallback, so zero-row events now fail closed for ordinary users; and SE-FIELD-RETIRE.1A later removed the legacy `scope_type` / `district` / `small_group` fields. CS-F.3 is not filtering; it is only an optional ServiceEvent label.

Large deferred items remain deferred pending feedback. MO-S.4 now supports manual team-leader scheduling, MO-S.4A completed scheduling semantic cleanup, MO-S.5A/MO-S.5B completed bounded rotation-anchor and copy-forward helper work, SE-AS.1 through SERVICE-EVENT-CONTEXT.1C completed ServiceEvent audience-row migration/backfill/write-guard/fallback and legacy-field retirement work, and BS-AS.1 / BS-AS.2 / BS-AS.2A plus BS-STRUCT.1L/1M/2A completed Bible Study Schedule audience scope, structure-unit-native normal generation, V2 audience-row visibility, V1 schema retirement, and My Serving Bible Study role confirmation. `COMMUNITY-EVENTS.1A` provides the independent Community Activities model/admin/visibility foundation, `1B` adds browse/detail/nav, `1C` adds minimal signup/cancel, `1D-A` adds member submission plus the Django-admin publish gate, `1D-A-FU1` adds required member-selected Activity Scope rows, `1D-B` adds the lightweight staff review + creator resubmit loop, `1E-A` adds the minimal Today provider for active signups and creator review reminders, `1F-A` adds pending-review creator editing, `1F-B` adds optional active-signup capacity, `1G-A` adds bounded linked co-organizers, and `1H-A` adds complete validated member drafts that remain outside review, signup, Today, My Serving, serving, and `ServiceEvent`. `COMMUNITY-EVENTS-STABILIZATION.1A` moved this V1 lifecycle to manual QA, and `COMMUNITY-EVENTS-STABILIZATION.1B` records the user-confirmed pass; a limited trial is acceptable under the existing stabilization boundary. Waitlist, notifications, comments, payments, calendar integration, attendee-list/check-in behavior, broader shared surfaces, automatic scheduling, availability, swaps, reminders, and Checklist V1 remain deferred unless separately planned.

Not next:
- Lighting Team-specific model
- Lighting Team scheduling algorithm
- Automatic scheduling
- Availability
- Swap requests
- Reminder automation
- Checklist engine
- Further Community Activities signup expansion, approval, management, or
  shared-surface work without a separately approved implementation slice
- Role-aware Bible Study editing permissions before schedule/scope alignment
- Full historical import
- Sensitive contact import

Suggested docs:
- `docs/READING_V1_QA_CHECKLIST.md`
- `docs/BIBLE_STUDY_V1_QA_CHECKLIST.md`
- `docs/BIBLE_STUDY_V2_SCHEDULE_SCOPE_REPLAN.md`
