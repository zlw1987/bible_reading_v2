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

Checklist and scheduling enhancements are still future phases.

The entire project is not complete. The stable center is Daily Reading, Prayer, Bible Study, ServiceEvent foundation, generic MinistryTeam foundation, manual TeamAssignment V1, My Serving Page V1, and limited Lighting Team Pilot Data/setup support; future checklist and scheduling operations should be added deliberately and kept within clear boundaries.

Church structure domain planning is recorded for future scope and audience work. See `docs/CHURCH_STRUCTURE_DOMAIN_PLAN.md`.

Future flexible Church Structure Foundation planning should keep current `District`, `SmallGroup`, and `Profile.small_group` assumptions usable while leaving room for CM/EM, variable-depth branches, and arbitrary future structure units. See `docs/CHURCH_STRUCTURE_FOUNDATION_PLAN.md`.

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

Lighting Team should be the first pilot, but there should not be a LightingTeam-specific data model. Models should remain generic enough for other ministry teams.

### G. Church Structure Boundaries

Planning clarification:
- Fellowship `SmallGroup` is not `MinistryTeam`.
- Small-group coworker roles such as C/E/O/W/F should not use TeamAssignment.
- `BibleStudyMeetingRole` is the per-meeting Bible Study responsibility model.
- CM and EM are ministry contexts / language ministries, not MinistryTeam records.
- There is no fake Combined Ministry record; combined events should involve both CM and EM.
- Community Activities should use future audience segments for signup visibility rather than being forced into ServiceEvent.
- Future flexible hierarchy should not hard-code Church -> CM/EM -> District -> SmallGroup forever; use a future `ChurchStructureUnit` only after the need is proven.

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

Reading, Prayer, Bible Study, Bible Study Worship Set, ServiceEvent Foundation, MinistryTeam Foundation, TeamAssignment V1, My Serving Page V1, and Lighting Team Pilot Data/setup support are in closure / QA / stabilization.

Next major product/domain phase:

Bible Study V2 Flow QA using `docs/BIBLE_STUDY_V2_FLOW_QA_CHECKLIST.md`, followed by fixes for QA findings before starting new modules.

Checklist, availability, swap requests, reminder automation, and advanced scheduling remain future.
Checklist V1 remains deferred until Lighting Pilot validation and should not be revived because of Community Activities.

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
- Next: Bible Study V2 Flow QA.
- Church Structure Foundation planning after Bible Study V2 Flow QA and before advanced mixed audience segments.
- Later role-aware editing permissions.
- Later ServiceEvent participating_ministries / MinistryContext planning.
- Later Community Activities V1 with audience segments.
- Checklist V1 remains deferred.

## 7. Explicit Non-Goals

This project should not become a full church ERP.

Do not build:
- Finance / offering
- Payroll
- Full CRM
- Children check-in
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

Next documentation/QA task:

Use `docs/BIBLE_STUDY_V2_FLOW_QA_CHECKLIST.md` for manual browser QA of the full Bible Study V2 flow.

Next major development task:

Fix Bible Study V2 QA findings before starting new modules.

Future foundation planning:

Church Structure Foundation remains future planning/foundation work after Bible Study V2 Flow QA and before advanced mixed audience segments or CM/EM-aware `ServiceEvent` filtering. It is not the immediate implementation task.

Checklist V1 remains deferred until Lighting Pilot validation.

Not next:
- Lighting Team-specific model
- Lighting Team scheduling algorithm
- Automatic scheduling
- Availability
- Swap requests
- Reminder automation
- Checklist engine
- Role-aware Bible Study editing permissions before schedule/scope alignment
- Full historical import
- Sensitive contact import

Suggested docs:
- `docs/READING_V1_QA_CHECKLIST.md`
- `docs/BIBLE_STUDY_V1_QA_CHECKLIST.md`
- `docs/BIBLE_STUDY_V2_SCHEDULE_SCOPE_REPLAN.md`
