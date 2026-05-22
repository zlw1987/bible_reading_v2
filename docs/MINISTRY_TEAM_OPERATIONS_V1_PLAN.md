# Ministry Team Operations V1 Plan

Source of product boundaries: `docs/PRODUCT_ARCHITECTURE_AND_ROADMAP.md`.

## 1. Purpose

Ministry Team Operations V1 supports church service-team coordination.

It is built on top of ServiceEvent Foundation, so team responsibilities attach to generic church gatherings rather than creating a separate scheduling universe.

Lighting Team is likely the first real pilot, but models must remain generic. The system should use reusable MinistryTeam, TeamMembership, and TeamAssignment concepts rather than LightingTeam-specific models.

This is not a full church ERP. It is not automatic scheduling. It should manage structured workflow and responsibility while continuing to link to existing Google Docs or Google Sheets where long-form playbooks and training details already live.

## 2. Product Boundary

In scope for V1:
- Ministry teams
- Team memberships
- Team leaders/coordinators
- ServiceEvent-based assignments
- Assignment status
- Basic confirmation
- Basic notes
- Playbook link
- Simple staff/team-lead management

Out of scope for V1:
- Automatic scheduling
- Availability matrix
- Swap requests
- Reminder automation
- Full checklist engine
- Service review history
- Full lighting scene database
- ShowXpress training database
- Phone number import
- Private notes
- Prayer requests
- Zoom passwords
- Historical 2021-2026 full schedule import
- Full multi-team dashboard

## 3. Relationship to Existing Modules

Daily Reading:
- No direct relationship.
- MinistryTeam should not appear in Daily Reading flows.

Prayer:
- No direct relationship.
- Do not mix prayer requests with team operations.

Bible Study:
- Future ServiceEvents may represent Bible Study events.
- Team assignments may later attach to Bible Study ServiceEvents if needed.

Bible Study Worship Set:
- Separate from MinistryTeam.
- Worship Set is song planning for a study session, not worship ministry scheduling.

ServiceEvent:
- MinistryTeam Operations depends on ServiceEvent.
- Assignments should attach to ServiceEvent.

Accounts / Permissions:
- Use the existing capability-based permission system.
- Do not build role hierarchy.

## 4. Proposed Data Models

These are recommended model directions, not implemented in this planning task.

### MinistryTeam

Possible fields:
- name
- name_en
- description
- description_en
- email_alias
- playbook_link
- is_active
- created_at
- updated_at

Examples:
- Lighting Team
- Worship Team
- Sound Team
- Projection Team
- Usher Team
- Children Ministry
- Meal / Hospitality Team

### TeamMembership

Prefer this over a standalone MinistryMember model.

Possible fields:
- team
- user nullable
- display_name
- email optional
- role: member / lead / coordinator
- skill_level optional
- can_lead
- is_active
- notes optional, but avoid sensitive/private notes in V1
- created_at
- updated_at

Important:
- If user exists, link to User.
- If no account exists yet, display_name/email can allow lightweight tracking.
- Do not add phone number in V1.

### TeamAssignment

Possible fields:
- service_event
- ministry_team
- assigned_members ManyToMany TeamMembership
- status:
  - scheduled
  - confirmed
  - prepared
  - completed
  - cancelled
- confirmed_at
- prepared_at optional
- completed_at optional
- notes
- created_by
- created_at
- updated_at

Important:
- No automatic assignment logic in V1.
- Assignment is manually created by manager/coordinator.
- Support multiple assigned members if needed.

## 5. Permission Model

Use capability-based permission.

Future capabilities may include:
- CAP_MANAGE_MINISTRY_TEAMS
- CAP_MANAGE_TEAM_ASSIGNMENTS

Possible behavior:
- Staff/superuser can manage all teams and assignments.
- User with `CAP_MANAGE_MINISTRY_TEAMS` can create/edit teams.
- User with `CAP_MANAGE_TEAM_ASSIGNMENTS` can create/edit assignments.
- Team lead/coordinator can manage assignments for their own team.
- Regular team member can view own assignments and confirm them.
- Regular church user should not see unrelated team operation details.

Do not add sensitive team contact info without explicit approval.

## 6. MVP User Flows

### Staff / Coordinator

- Create MinistryTeam.
- Add team members.
- Link playbook.
- Create ServiceEvent if needed.
- Create TeamAssignment for ServiceEvent.
- Assign one or more team members.
- Mark assignment scheduled / confirmed / completed / cancelled.
- Add basic assignment notes.

### Team Member

- See "My Serving" or equivalent page.
- View upcoming assignments.
- Confirm assignment.
- View event details.
- View team playbook link.
- See assignment notes.

### Regular User

- Should not see internal team assignment details unless explicitly allowed later.

## 7. Lighting Team Pilot Boundary

Lighting Team pilot should only use generic models.

Allowed pilot data:
- Lighting Team as a MinistryTeam
- Future 2-3 months of assignments
- Assigned lighting member
- ServiceEvent date/type
- Special event note
- Playbook link to existing Google Doc

Do not import:
- Full 2021-2026 history
- Full availability matrix
- Phone numbers
- Private notes
- Zoom passwords
- All ShowXpress training content
- Complex color/status logic from spreadsheet
- Automatic scheduling logic

## 8. Suggested V1 Pages

Possible pages, not implemented in this planning task:

- `/teams/`
  - team list for managers/staff
- `/teams/<id>/`
  - team detail
- `/teams/<id>/members/`
  - membership management
- `/assignments/`
  - assignments list for managers
- `/assignments/<id>/`
  - assignment detail
- `/my-serving/`
  - logged-in user's upcoming service assignments

Navigation principle:
- Do not add top-nav clutter for normal users.
- Staff menu may include Ministry Teams later.
- My Serving may become a normal-user nav item only if real users need it frequently.
- Prefer contextual links first.

## 9. V1 Non-Goals

- No automatic scheduling.
- No availability matrix.
- No swap request workflow.
- No reminder automation.
- No full checklist system.
- No advanced service review history.
- No multi-team dashboard.
- No full service flow management.
- No worship song library.
- No lighting scene database.
- No Google Doc content migration.
- No sensitive contact import.
- No full historical schedule import.

## 10. Implementation Phases After This Plan

Recommended sequence:

### Task 1: MinistryTeam + TeamMembership Foundation

- Models
- Admin
- Basic manager views
- Tests
- No assignments yet

### Task 2: TeamAssignment V1

- Assign team members to ServiceEvent
- Status
- Confirmation
- Notes
- Tests

### Task 3: My Serving Page

- User can see own upcoming assignments
- Confirm assignment
- View playbook link
- Tests

### Task 4: Lighting Team Pilot Data

- Create Lighting Team
- Manually enter or import limited future assignments
- No sensitive data
- No full historical import

### Task 5: Checklist V1

- Only after assignments are proven useful
- Basic checklist template / assignment checklist
- No complex automation

### Task 6: Enhancements

- Availability
- Swap request
- Reminders
- Dashboard
- Only after real usage

## 11. Definition of Done for Future Implementation

- Generic models, no LightingTeam-specific model.
- Permissions clear.
- Bilingual UI.
- Normal user data exposure controlled.
- Team lead/coordinator behavior tested.
- Staff behavior tested.
- Existing all-app tests pass.
- No top-nav clutter.
- No sensitive data imported.
- No automatic scheduling.

## Verification for This Planning Task

- Do not run the full test suite.
- Confirm only `docs/MINISTRY_TEAM_OPERATIONS_V1_PLAN.md` was created.
- Confirm no migrations were created.
- Confirm no business logic, models, views, forms, templates, URLs, settings, or tests were changed.
