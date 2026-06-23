# Product Architecture and Roadmap

## 1. Project Identity

This project is a lightweight church spiritual life and ministry workflow system.
It started as a Bible reading check-in app. The current core remains Daily Reading, but the roadmap includes Prayer, Bible Study, Worship Set planning, and Ministry Team Operations.
It is not intended to become a full church ERP.

The app should support spiritual practices and practical ministry coordination: daily Scripture reading, prayer, reflection, group encouragement, Bible study preparation, and eventually focused ministry workflows. It should stay simple, pastoral, and workflow-oriented rather than becoming a broad administrative system.

## 2. Current Status

Daily Reading Core V1 is feature complete and in closure/stabilization.

Prayer V1 is core-complete and in stabilization.

Bible Study Module V1 is implemented and entering QA/stabilization.

Bible Study Worship Set V1 is implemented and entering QA/stabilization.

The role/scoped permission foundation exists.

Navigation cleanup is complete.

Reading Guide Posts are implemented.

ServiceEvent Foundation V1 is implemented and entering QA/stabilization.

MinistryTeam + TeamMembership Foundation is implemented and entering QA/stabilization.

TeamAssignment V1 is implemented and entering QA/stabilization.

My Serving Page V1 is implemented and entering QA/stabilization.

Lighting Team Pilot Data import support and setup UI are implemented and entering QA/stabilization.

MO-S.1 Ministry Scheduling Requirements Plan is complete as docs-only planning for real pilot feedback about required ministry teams, assignment coverage display, and team-leader scheduling workflow. MO-S.2 Event Required-Team implementation, MO-S.3 read-only assignment coverage display, MO-S.4 team-leader scheduling workspace, MO-S.4A scheduling semantic cleanup, MO-S.5A rotation anchor foundation, and MO-S.5B limited copy-forward suggestion helper are complete.

Checklist and advanced scheduling enhancements are still future phases.

The entire project is not complete. The stable center is Daily Reading, Prayer, Bible Study, ServiceEvent foundation with required MinistryTeams and optional rotation anchors, generic MinistryTeam foundation, manual TeamAssignment V1, My Serving Page V1, limited Lighting Team Pilot Data/setup support, MO-S.1 scheduling requirements, MO-S.2 required-team data capture, MO-S.3 read-only assignment coverage display, MO-S.4 manual team-leader scheduling workspace, MO-S.4A scheduling semantic cleanup, MO-S.5A rotation anchor foundation, MO-S.5B limited copy-forward suggestions, SE-AS.1 through SE-RETIRE.1B ServiceEvent audience-row migration/guard/retirement work, DOCS-AS.1 shared audience-scope direction, BS-AS.1 / BS-AS.2 / BS-AS.2A Bible Study Schedule audience scope using `ChurchStructureUnit`, and BS-STRUCT.1L/1M/1O/1P/2A Bible Study V2 structure-native generation / audience-row visibility cleanup; future checklist, scheduling operations, ServiceEvent legacy field retirement, and future module audience work should be added deliberately and kept within clear boundaries.

Church structure domain planning is recorded for future scope and audience work. CS-F.1 adds the short-term `MinistryContext` bridge, CS-F.2 uses it for Bible Study Schedule scope eligibility, CS-F.3 adds optional ServiceEvent MinistryContext labeling, CS-H.2 adds a model-only `ChurchStructureUnit` foundation, CS-H.2A hardens tree validation, CS-H.3 records mapping/membership strategy, CS-H.3B adds nullable legacy mapping fields, CS-H.3C adds an explicit idempotent seeding/mapping command, CS-H.3D verifies GoDaddy production/staging seeding, CS-H.3E closes seeded structure data QA, CS-H.4 records the `ChurchStructureMembership` design, CS-H.5A adds the model-only membership foundation, CS-H.5B hardens membership helpers/validation, CS-H.5C adds an explicit membership backfill command, CS-H.5D records user-attested production/staging backfill verification, CS-H.5E improves Django Admin clarity for legacy structure versus future foundation models, CS-H.6/CS-H.6A/CS-H.6B add signup requested-unit design and capture, CS-H.7 through CS-H.7E add staff approval planning, staff request review, approve/reject actions, and narrow `Profile.small_group` approval sync, CS-H.8 records the integration checkpoint, CS-H.9 records membership request UX hardening, CS-H.10 records the CMS hardening checkpoint, and SE-AS.1 through SE-RETIRE.1B complete ServiceEvent audience-row visibility, apply/backfill, write-path guard, and zero-row fallback retirement while leaving legacy fields stored until field-level retirement. PP-SA.1 records staff/admin surface planning, PP-SA.2 adds the permission-protected read-only staff overview at `/staff/`, PP-SA.3 completes staff membership request workflow polish, PP-SA.4 completes a permission-protected read-only staff moderation queue at `/staff/moderation/`, and PP-SA.5 completes read-only ministry ops health indicators on `/staff/`. See `docs/CHURCH_STRUCTURE_DOMAIN_PLAN.md`, `docs/CHURCH_STRUCTURE_MAPPING_AND_MEMBERSHIP_STRATEGY.md`, `docs/CHURCH_STRUCTURE_SEEDING_VERIFICATION.md`, `docs/CHURCH_STRUCTURE_MEMBERSHIP_BACKFILL_VERIFICATION.md`, `docs/CHURCH_STRUCTURE_MEMBERSHIP_DESIGN.md`, `docs/STAFF_ADMIN_SURFACE_EXPANSION_PLAN.md`, and `docs/SERVICE_EVENT_AUDIENCE_SCOPE_REDESIGN_PLAN.md`.

Future flexible Church Structure Foundation planning should keep current `MinistryContext`, `District`, and `SmallGroup` row/table assumptions usable where they remain legacy/archive/compatibility data while leaving room for CM/EM, variable-depth branches, arbitrary future structure units, and future membership history. Long-term source of truth should be `ChurchStructureUnit` plus `ChurchStructureMembership`; runtime behavior is now consumer-specific. Nullable legacy mapping fields, verified command-based seeding/mapping, seeded data QA closure, membership design, a model-only membership table, helper hardening, explicit command-based membership backfill, user-attested production/staging backfill verification, clearer Django Admin labeling, signup/Profile requested-unit capture, staff request review, approve/reject actions, narrow approval sync, SE-AS.1 through SE-RETIRE.1B ServiceEvent audience migration, and BS-STRUCT.2A Bible Study V2 audience-row visibility now exist. For ServiceEvents, `ServiceEventAudienceScope` rows are the ordinary-user visibility source and now match by active primary `ChurchStructureMembership`; after SE-RETIRE.1B, events with no audience rows **fail closed** for ordinary users and no longer read legacy `scope_type` / `district` / `small_group` or `Profile.small_group`. SE-FIELD-RETIRE.1A later removed the legacy `scope_type` / `district` / `small_group` fields. Bible Study normal generation is structure-unit-native: it targets active `UNIT_SMALL_GROUP` leaves from `BibleStudySeriesAudienceScope`, writes meeting audience rows, and uses `generation_key` / `anchor_unit` for identity; `BibleStudyMeeting.small_group` was removed in BS-MEETING-MIRROR.1A. Since BS-STRUCT.2A, Bible Study V2 meeting visibility, `/studies/` / Today, and role/worship pickers read meeting audience rows plus active primary membership, and zero-row V2 meetings fail closed. Full legacy row/table retirement remains future and separately approved. See `docs/CHURCH_STRUCTURE_FOUNDATION_PLAN.md`, `docs/SERVICE_EVENT_AUDIENCE_SCOPE_REDESIGN_PLAN.md`, `docs/SERVICE_EVENT_AUDIENCE_RUNTIME_MIGRATION_PLAN.md`, and `docs/SERVICE_EVENT_AUDIENCE_SELECTOR_INTERACTION_PLAN.md`.

Ministry scheduling requirements from real pilot feedback are recorded in `docs/MINISTRY_SCHEDULING_REQUIREMENTS_PLAN.md`. MO-S.2 is complete: `ServiceEvent` now has required MinistryTeams through explicit `ServiceEventRequiredTeam` rows. MO-S.3 is complete as read-only coverage display comparing those required teams against `TeamAssignment` and `TeamAssignmentMember` data. MO-S.4 is complete as a team-scoped manual scheduling workspace at `/teams/<team_id>/schedule/`. MO-S.4A scheduling semantic cleanup is complete after manual QA. MO-S.5A is complete: `ServiceEvent.rotation_anchor_team` is an optional scheduling hint only. MO-S.5B is complete: the team schedule workspace can prefill editable anchor-based or team-history copy-forward suggestions and writes only on explicit save. `TeamMembership.can_lead` is deprecated/reserved and does not grant scheduling, member-management, or admin permissions; Lead and Coordinator roles can schedule their own team assignments; staff, superusers, and global assignment managers can schedule any team; ordinary members and `can_lead`-only members cannot schedule; My Serving provides Teams I manage / 我负责的团队 as the non-staff team leader entry point; the schedule defaults to All event types / 全部类型 while still showing only required-or-already-assigned events within the date window; specific event type filtering still works; ServiceEvent MinistryContext wording is Host / Language Label / 主办/语言标签（可选） and is label-only.

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

Implemented V1 module.

Includes:
- Bible study series
- Bible study sessions
- Thursday pre-study
- Friday study schedule
- Scripture reference
- Study guide
- Discussion questions
- Draft/published/completed/cancelled workflow
- Scope: global / district / small_group
- Permission-controlled editing

### D. Bible Study Worship Set

Implemented V1 module. Belongs to Bible Study sessions.

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

Does not include in V1:
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
- Scope: global / district / small_group
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

Future planning may add CM/EM participating ministry context support, but CM and EM should be modeled as ministry contexts rather than MinistryTeam records.

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
- Fellowship `SmallGroup` is not `MinistryTeam`.
- Small-group coworker roles such as C/E/O/W/F should not use TeamAssignment.
- `BibleStudyMeetingRole` is the per-meeting Bible Study responsibility model.
- CM and EM are ministry contexts / language ministries, not MinistryTeam records.
- There is no fake Combined Ministry record; combined events should involve both CM and EM.
- Community Activities should use the shared `ChurchStructureUnit`-based audience-scope foundation for signup visibility rather than being forced into ServiceEvent or inventing a separate legacy-only audience segment system.
- Future flexible hierarchy should not hard-code Church -> CM/EM -> District -> SmallGroup forever; use a future `ChurchStructureUnit` only after the need is proven.

### H. Long-Term CMS Product Scope

These are final CMS product directions, not authorization to implement them now. "Not V1" or "not now" means deferred unless separately planned and approved; it does not mean outside the final product.

Future CMS scope may include:
- Prayer Wall continued refinement.
- Bible Study / small group attendance.
- Notifications through email, SMS, WeChat, and app notifications.
- Pastor/staff announcements.
- Group leader dashboard.
- Children, family, couples, and newcomer care workflows.
- Activities signup, check-in, and capacity management.
- Resources, materials, and file center.
- Finer permission matrix for ministry role, small group leader, district leader, and staff capabilities.

The ERP boundary remains: no finance, payroll, HR/personnel system, full CRM, legal/compliance system, or broad sensitive contact import. Children/family care workflow is future CMS scope, but child security check-in is not automatically authorized by that scope.

### I. Modular Adoption and Coexistence

Recorded as a product principle from June 2026 demo feedback:

- The CMS must not require a church to replace all existing church apps at once.
- Modules should be adoptable one by one; existing module boundaries and legacy-fallback behavior already support this.
- External tools may coexist with CMS modules (for example, a small group may keep using 微读圣经 for reading/study content while the CMS provides structure, scheduling, and audience scope).
- Integration initially means link/reference/mapping, like the existing "link to Google Docs playbooks, do not import them" rule — not deep API integration or data import.
- No external-system integration work is authorized by this principle alone; any future integration requires its own separately approved plan.

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
- BibleStudySession
- BibleStudyGuide
- Thursday pre-study date/time
- Friday study date/time
- Scripture reference
- Study guide
- Discussion questions
- Draft/published/completed/cancelled workflow
- Global/district/small_group scope
- Bilingual UI
- Permission-controlled editing

V2 correction after browser review:
- The future primary Bible Study flow should be Bible Study Schedule / 查经安排 -> Weekly Bible Study Guide / 查经指引 -> generated Small Group Bible Study Meetings / 小组查经聚会.
- Existing `BibleStudySeries` should likely serve as the internal Bible Study Schedule model for now.
- Generated meetings should reference the weekly guide through `BibleStudyMeeting.lesson` and derive schedule through `meeting.lesson.series`.
- Guide content should not be copied into generated meetings; meeting detail should display current parent guide content dynamically.

### Bible Study Worship Set

- Session-level worship songs
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
- Global/district/small_group scope
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
- District
- ChurchRoleAssignment
- Capability helpers
- Scoped group progress

## 5. Current Phase

Current phase:

Reading, Prayer, Bible Study, Bible Study Worship Set, ServiceEvent Foundation, MinistryTeam Foundation, TeamAssignment V1, My Serving Page V1, and Lighting Team Pilot Data/setup support reached pilot validation on `v0.9-pilot-rc1`. Pilot validation passed with no known P0/P1 blockers.

The current next phase is Post-Pilot Backlog Triage. CS-H.1 Flexible Church Structure and Audience Scope Design Doc is complete, CS-H.2 adds the model-only `ChurchStructureUnit` foundation without changing current behavior, CS-H.2A hardens that model, CS-H.3 records mapping/membership/source-of-truth strategy, CS-H.3B adds nullable legacy mapping fields, CS-H.3C adds an explicit idempotent seeding/mapping command, CS-H.3D verifies GoDaddy production/staging seeding with a clean second dry-run, CS-H.3E closes seeded structure data QA, CS-H.4 records the membership design, CS-H.5A adds the model-only membership foundation, CS-H.5B hardens membership helpers/validation, CS-H.5C adds an explicit membership backfill command, CS-H.5D records user-attested production/staging backfill verification, CS-H.5E improves Django Admin clarity, CS-H.6 through CS-H.7E complete requested-unit capture and staff approval/sync slices, CS-H.8 integration checkpoint is complete, CS-H.9 membership request UX hardening is complete, CS-H.10 CMS hardening checkpoint is complete, PP-SA.1 Staff Admin Surface Expansion Plan is complete as docs-only planning, PP-SA.2 Read-Only Staff Dashboard Overview is complete at `/staff/`, PP-SA.3 Membership / Admin Workflow Polish is complete for the existing staff membership request workflow, PP-SA.4 Moderation / Admin Queues is complete at `/staff/moderation/`, and PP-SA.5 Ministry Ops Admin Improvements is complete on `/staff/` as read-only ministry ops health indicators. See `docs/POST_PILOT_BACKLOG_TRIAGE.md`, `docs/FLEXIBLE_CHURCH_STRUCTURE_AND_AUDIENCE_SCOPE_DESIGN.md`, `docs/CHURCH_STRUCTURE_MAPPING_AND_MEMBERSHIP_STRATEGY.md`, `docs/CHURCH_STRUCTURE_SEEDING_VERIFICATION.md`, `docs/CHURCH_STRUCTURE_MEMBERSHIP_BACKFILL_VERIFICATION.md`, `docs/CHURCH_STRUCTURE_MEMBERSHIP_DESIGN.md`, and `docs/STAFF_ADMIN_SURFACE_EXPANSION_PLAN.md`.

Current foundation step:

Bible Study V2 Flow QA has passed. CS-F.1 MinistryContext bridge foundation is complete, CS-F.2 adds MinistryContext as a Bible Study Schedule scope, and CS-F.3 adds optional ServiceEvent MinistryContext labeling. `v0.9-pilot-rc1` was deployed and pilot validation passed.

MO-S.1 records real pilot feedback that staff need required MinistryTeam selection when creating or batch-creating ServiceEvents, TeamAssignment pages need required-team coverage with assigned coworkers and confirmation status rather than only counts, and ministry team leaders need an efficient same-type event scheduling entry point for their own team. MO-S.2 completes the first implementation slice by letting staff select required teams on ServiceEvent single create/edit and recurring batch-create. MO-S.3 completes the read-only coverage slice: the `TeamAssignment` list is the primary operational coverage surface, assignment detail shows compact event coverage, ServiceEvent detail shows coverage only to staff/service-event or team-assignment managers, ordinary event viewers do not see coworker coverage, `/staff/` adds upcoming required-team gap counts, and browser automation was blocked but user-completed manual QA accepted the UI. MO-S.4 completes the manual team-leader scheduling workspace, and MO-S.4A completes scheduling semantic cleanup after manual QA: Team detail shows Schedule Team / 安排团队服事 only for users who can manage that team's assignments; staff, superusers, and global assignment managers can schedule any team; Lead and Coordinator roles can schedule their own team assignments; ordinary members, `can_lead`-only members, and unrelated users cannot schedule; `TeamMembership.can_lead` is deprecated/reserved and does not grant scheduling, member-management, or admin permissions; My Serving provides Teams I manage / 我负责的团队 as the non-staff team leader entry point; the workspace defaults to All event types / 全部类型 while still showing only required-or-already-assigned events within the date window; specific event type filtering still works; ServiceEvent MinistryContext wording is Host / Language Label / 主办/语言标签（可选） and is label-only; one active in-page schedule/edit form is selected by event or assignment query parameters.

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

Status: implemented / QA.

Includes:
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

Status: implemented / QA.

Includes:
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

Current sequence:
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
- SE-AS.3 ServiceEvent Audience Runtime Migration Plan completed as docs-only planning in `docs/SERVICE_EVENT_AUDIENCE_RUNTIME_MIGRATION_PLAN.md`. It renumbers later milestones: SE-AS.4 runtime visibility rule with legacy fallback at that time, SE-AS.5 staff audience selector UI/display, and SE-AS.6 backfill/compatibility/cleanup planning. SE-AS.6C apply/backfill, SE-AS.7A write-path guard, and SE-RETIRE.1B zero-row runtime fallback retirement are now complete; remaining ServiceEvent cleanup is field-level retirement planning for the stored legacy scope fields.
- SE-AS.4 ServiceEvent Audience Runtime Visibility Rule completed: events with `ServiceEventAudienceScope` rows use audience rows for ordinary-user visibility; at SE-AS.4 time events with no rows kept legacy `scope_type` / `district` / `small_group` plus `Profile.small_group` behavior; no SE-AS.5 selector UI, form/template audience picker, Community Activities, CS-MAP.3, or CS-SETUP.1 was added. Historical note: SE-AS.4 originally matched audience rows through the legacy belonging rule; CS-CORE.2B-A later switched those audience-row matches to active primary `ChurchStructureMembership`, SE-RETIRE.1B later retired the zero-row runtime fallback, and SE-FIELD-RETIRE.1A later removed the legacy scope fields.
- SE-AS.5A ServiceEvent Audience Selector Interaction Plan completed as docs-only planning in `docs/SERVICE_EVENT_AUDIENCE_SELECTOR_INTERACTION_PLAN.md`: picker placement, legacy fallback interaction, staff/ordinary display wording, empty/unmapped selection handling, recurring/batch behavior, and non-goals are recorded; no code, template, form, view, model, test, migration, static, backfill, or runtime behavior change was added.
- SE-AS.5 ServiceEvent Staff Audience Selector UI and Display completed: single create/edit and recurring create expose an optional `ChurchStructureUnit` audience picker; selected units save/replace `ServiceEventAudienceScope` rows; recurring preview writes no rows; recurring create applies one selected audience set to newly created events; staff detail shows Structure audience plus stored legacy-field context when relevant; ordinary detail does not expose audience architecture terms. Historical SE-AS.5 clearing/empty-picker behavior restored legacy fallback, but SE-AS.7A later superseded it: empty picker saves now convert valid legacy fields into audience rows or fail validation, and SE-RETIRE.1B makes zero-row events fail closed for ordinary users. No schema/migration, legacy-field removal/deprecation, Community Activities, CS-MAP.3, CS-SETUP.1, or Required Ministry Teams / Rotation Anchor / TeamAssignment / My Serving behavior change was added.
- SE-AS.5B post-commit cleanup completed: fallback copy now explains that legacy fields apply only when no structure audience is selected, and the read-only staff structure map now uses clearer `Church Structure & Setup Check` wording plus descendant-inclusive covered-member counts. SE-AS.5C / CS-MAP.2B corrected the tree interaction: ServiceEvent audience picker sections stay visible, and both the picker and `/staff/structure/` expand/collapse hierarchy nodes by level. No runtime visibility, schema, migration, backfill, setup/edit UI, roster, or membership-source migration was added.
- DOCS-AS.1 records the shared `ChurchStructureUnit` audience-scope direction: app modules should select `ChurchStructureUnit` rows through app-specific join models rather than adding more legacy-only multi-select scope fields.
- BS-AS.1 Bible Study Schedule audience scope using `ChurchStructureUnit` completed, as the first narrow runtime consumer implemented. `BibleStudySeriesAudienceScope` joins `BibleStudySeries / 查经安排` to `ChurchStructureUnit`; historical BS-AS.1 generation resolved selected units to eligible legacy `SmallGroup` rows. Since BS-STRUCT.1L/1M, normal generation is structure-unit-native, targets active `UNIT_SMALL_GROUP` leaves, writes meeting audience rows, and keeps `BibleStudyMeeting.small_group` only as optional legacy mirror / display / history / secondary idempotency compatibility. Since BS-STRUCT.2A, V2 visibility reads meeting audience rows plus active primary membership and zero-row V2 meetings fail closed.
- BS-AS.2 completed: reusable server-rendered `ChurchStructureUnit` audience picker (searchable, chips, tree order, no-JS fallback, vanilla-JS convenience clearing, backend validation authoritative); compact list/card scope labels and wrapped/chip detail labels with the root prefix omitted; active management lists and related detail lists hide cancelled schedules/guides/meetings; generation still treats cancelled meetings as existing/skipped.
- BS-AS.2A completed: bilingual audience-picker search `aria-label`, and chip remove buttons include the selected unit label in their `aria-label`; no behavior/schema/visibility changes.
- BS-AS QA follow-up completed; BS-AS.2B fixed the audience picker mobile CSS no-go.
- CS-MAP.1 Church Structure Map / Setup Readiness Plan completed as docs-only planning in `docs/CHURCH_STRUCTURE_MAP_AND_SETUP_READINESS_PLAN.md`, recording June 2026 demo feedback (modular adoption/coexistence; pastor/staff structure map and setup readiness). No runtime behavior changed.
- CS-MAP.2 read-only Staff Structure Map + Mapping Health completed at `/staff/structure/`: permission-protected read-only staff page rendering the active `ChurchStructureUnit` hierarchy with bilingual names, hierarchical node-level expand/collapse, descendant-inclusive covered-member counts, current data mapping context from active `MinistryContext` / `District` / `SmallGroup` rows, and setup-readiness indicators including direct active primary memberships on parent units; no write actions, no member rosters, no schema/migration changes, no runtime visibility changes, no setup/edit UI. Django Admin remains the structure write surface.
- SE-AS.5 is complete as the bounded staff selector/display implementation; SE-AS.6C apply/backfill, SE-AS.7A write-path guard, and SE-RETIRE.1B zero-row fallback retirement later completed as separate slices. Community Activities, CS-MAP.3, CS-SETUP.1, and field-level legacy cleanup are not pulled forward by SE-AS.5 completion.
- CS-MAP.3 optional setup readiness checklist remains optional and unapproved. CS-SETUP.1 limited structure setup/edit UI is not approved; it is gated on CS-MAP.2 evidence plus a separate design doc (unit↔legacy sync, edit permissions, effect on stored audience rows). CS-SETUP.1A is complete as a docs-only risk/design pass in `docs/CHURCH_STRUCTURE_MAP_AND_SETUP_READINESS_PLAN.md` Section 13: it records the risk analysis and design contract and splits CS-SETUP.1 into separately approvable CS-SETUP.1B (label/sort-order only), 1C (mapping review/edit), 1D (create/move/deactivate), and 1E (membership/belonging) sub-milestones; none of 1B–1E is approved and no runtime/schema behavior changed.
- Later ServiceEvent field-level legacy cleanup and Community Activities should reuse the same `ChurchStructureUnit` audience-scope foundation where applicable; Community Activities remains deferred and requires separate approval before implementation.
- Boundary: `ChurchStructureMembership` runtime visibility is consumer-specific. ServiceEvent structure-audience rows switched in CS-CORE.2B-A and zero-row events fail closed after SE-RETIRE.1B. Bible Study V2 audience-row visibility / Today / role-worship pickers use meeting audience rows plus active primary membership after BS-STRUCT.2A. Legacy `SmallGroup`, `District`, `MinistryContext`, and `Profile.small_group` remain compatibility/archive/display/audit sources for remaining legacy consumers such as V1 `BibleStudySession`, not a universal current visibility source.
- Later consumer migration only after phased planning.
- Later role-aware editing permissions.
- Later ServiceEvent legacy scope field retirement only after separate approval (numbering per `docs/SERVICE_EVENT_AUDIENCE_RUNTIME_MIGRATION_PLAN.md`).
- Later Community Activities V1 using the shared `ChurchStructureUnit` audience-scope foundation.
- Checklist V1 remains deferred.

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

Current foundation status:

CS-F.1 MinistryContext bridge foundation, CS-F.2 MinistryContext Bible Study Schedule scope, and CS-F.3 optional ServiceEvent MinistryContext labeling are complete after the Bible Study V2 Flow QA pass. `v0.9-pilot-rc1` was deployed and pilot validation passed.

Current post-pilot step:

PV-C.1 records pilot validation closure. Pilot validation passed on `v0.9-pilot-rc1`. CS-H.1 through CS-H.10, PP-SA.2 through PP-SA.5, MO-S.1 through MO-S.5B, SE-AS.1 through SE-RETIRE.1B, DOCS-AS.1, BS-AS.1 through BS-AS.2A, BS-STRUCT.1L/1M/1O/1P/2A, CS-MAP.2, and CS-CORE.2C-B are complete. ServiceEvent audience rows use active primary `ChurchStructureMembership`; SE-AS.6C production apply is complete, SE-AS.7A stops normal zero-row writes, and SE-RETIRE.1B retired the zero-row runtime fallback so zero-row events now fail closed for ordinary users. SE-FIELD-RETIRE.1A later removed the legacy `scope_type` / `district` / `small_group` fields. Bible Study normal generation is structure-unit-native: it targets active `UNIT_SMALL_GROUP` leaves from `BibleStudySeriesAudienceScope`, uses `generation_key = normal-unit:{unit_id}` and `anchor_unit`, and writes meeting audience rows; `BibleStudyMeeting.small_group` was removed in BS-MEETING-MIRROR.1A. Since BS-STRUCT.2A, V2 meeting visibility, `/studies/` / Today, and role/worship pickers read meeting audience rows plus active primary membership; zero-row V2 meetings fail closed. Runtime consumers are now explicitly split by consumer rather than all primarily legacy. See `docs/POST_PILOT_BACKLOG_TRIAGE.md`, `docs/FLEXIBLE_CHURCH_STRUCTURE_AND_AUDIENCE_SCOPE_DESIGN.md`, `docs/CHURCH_STRUCTURE_MAPPING_AND_MEMBERSHIP_STRATEGY.md`, `docs/CHURCH_STRUCTURE_SEEDING_VERIFICATION.md`, `docs/CHURCH_STRUCTURE_MEMBERSHIP_BACKFILL_VERIFICATION.md`, `docs/CHURCH_STRUCTURE_MEMBERSHIP_DESIGN.md`, `docs/STAFF_ADMIN_SURFACE_EXPANSION_PLAN.md`, `docs/MINISTRY_SCHEDULING_REQUIREMENTS_PLAN.md`, `docs/SERVICE_EVENT_AUDIENCE_SCOPE_REDESIGN_PLAN.md`, `docs/SERVICE_EVENT_AUDIENCE_RUNTIME_MIGRATION_PLAN.md`, and `docs/SERVICE_EVENT_AUDIENCE_SELECTOR_INTERACTION_PLAN.md`.

Future foundation planning:

`ChurchStructureUnit` seeding/mapping now exists only as an explicit management command, passed GoDaddy production/staging verification, and completed seeded structure data QA closure. SE-AS.1 records the docs-only `ServiceEvent` audience-scope redesign recommendation; SE-AS.2 adds the `ChurchStructureUnit`-linked audience scope beside legacy fields as a model-only foundation; SE-AS.4 made those rows the ServiceEvent ordinary-user visibility source when rows exist (zero-row events fell back to legacy `scope_type` / `district` / `small_group` plus `Profile.small_group` at that time); CS-CORE.2B-A switched audience-row matching to active primary membership; SE-AS.6C apply is complete; SE-AS.7A stops normal zero-row writes; SE-RETIRE.1B retired the zero-row runtime fallback, so zero-row events now fail closed for ordinary users; and SE-FIELD-RETIRE.1A later removed the legacy `scope_type` / `district` / `small_group` fields. CS-F.3 is not filtering; it is only an optional ServiceEvent label.

Large deferred items remain deferred pending feedback. MO-S.4 now supports manual team-leader scheduling, MO-S.4A completed scheduling semantic cleanup, MO-S.5A/MO-S.5B completed bounded rotation-anchor and copy-forward helper work, SE-AS.1 through SE-RETIRE.1B completed ServiceEvent audience-row migration/backfill/write-guard/fallback-retirement work, and BS-AS.1 / BS-AS.2 / BS-AS.2A plus BS-STRUCT.1L/1M/2A completed Bible Study Schedule audience scope, structure-unit-native normal generation, and V2 audience-row visibility. ServiceEvent legacy field retirement, Community Activities, notifications, attendance, automatic scheduling, availability, swaps, reminders, and Checklist V1 remain deferred unless separately planned.

Not next:
- Lighting Team-specific model
- Lighting Team scheduling algorithm
- Automatic scheduling
- Availability
- Swap requests
- Reminder automation
- Checklist engine
- Community Activities before a separate audience/operations plan
- Role-aware Bible Study editing permissions before schedule/scope alignment
- Full historical import
- Sensitive contact import

Suggested docs:
- `docs/READING_V1_QA_CHECKLIST.md`
- `docs/BIBLE_STUDY_V1_QA_CHECKLIST.md`
- `docs/BIBLE_STUDY_V2_SCHEDULE_SCOPE_REPLAN.md`
