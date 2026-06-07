# Ministry Scheduling Requirements Plan

## 1. Purpose

MO-S.1 is a docs-only planning pass for real pilot feedback about ministry scheduling.

This plan records the workflow need, names the likely model boundary, and proposes phased implementation without changing app code, templates, CSS, JavaScript, tests, migrations, permissions, or runtime behavior.

## 2. Pilot Feedback Recorded

Pilot users need ServiceEvent and TeamAssignment workflows to show ministry coverage more clearly:

- When staff create or batch-create `ServiceEvent` records, they need to select the required `MinistryTeam` records for each event.
- `TeamAssignment` pages need to show required teams and assigned coworkers, not only assignment counts.
- A required team with assigned people should show each assigned coworker and confirmation status. Example: Lighting Team: assigned 1 person: Levin.
- If multiple people are assigned for a required team, show all assigned members and each confirmation state.
- If a required team has no `TeamAssignment`, show it as missing or unassigned.
- Ministry team leaders need an efficient entry point to schedule their own team for recurring or same-type events, especially Sunday Service rotation.

This is real near-term P2 ministry operations feedback. It improves staff and team-leader usability, but it does not invalidate the pilot baseline and is not a P0/P1 blocker.

## 3. Likely Model Boundary

Recommended boundary:

- `ServiceEvent` required teams are event-level expectations.
- `TeamAssignment` remains the actual scheduled assignment for a specific `ServiceEvent` and `MinistryTeam`.
- `TeamAssignmentMember` remains the assigned people and their confirmation state.

The required-team concept should answer, "Which teams are expected for this event?" Actual assignments should still answer, "Who is scheduled for this team on this event?"

This avoids turning missing coverage into fake assignments and avoids treating assignment counts as coverage proof.

## 4. Generic Modeling Requirements

- Keep models generic.
- Do not add a LightingTeam-specific model.
- Keep Lighting Team as pilot data using generic `MinistryTeam`, `TeamMembership`, `TeamAssignment`, and `TeamAssignmentMember` concepts.
- Keep `ServiceEvent` generic; do not turn it into Community Activities.
- Do not add audience filtering as part of this work.
- Do not infer serving permissions, team leadership, or team assignments from `ChurchStructureMembership`.
- Team leaders may manage their own team assignments only through existing or future explicit `MinistryTeam` / `TeamAssignment` capabilities.
- `TeamMembership.can_lead` is deprecated/reserved for now and does not grant scheduling, member-management, or admin permissions.

## 5. Phased Implementation

### MO-S.1 Docs Plan Only

Status: this document.

Deliverables:
- Record pilot feedback.
- Define model and permission boundaries.
- Sequence later implementation phases.
- Keep all runtime behavior unchanged.

### MO-S.2 Event Required-Team Model / Design Implementation

Status: completed.

Goal:
- Add a generic way for staff to mark required `MinistryTeam` records on `ServiceEvent`.

Completed scope:
- `ServiceEvent` now records required `MinistryTeam` records through the explicit `ServiceEventRequiredTeam` through model.
- `ServiceEventRequiredTeam.ministry_team` uses `PROTECT`; teams referenced by event requirements should be deactivated rather than deleted.
- Staff single create/edit and recurring batch-create can select required teams.
- Batch-created `ServiceEvent` records share the required-team selection from the batch form.
- Existing events remain valid with no required teams.
- Active teams are selectable; already-selected inactive teams remain visible/removable on edit.
- ServiceEvent detail shows required teams as plain metadata only.
- No `TeamAssignment` or `TeamAssignmentMember` is auto-created.

Boundaries:
- No automatic assignments.
- No assignment coverage display, missing/unassigned status, team-leader scheduling workspace, rotation/copy-forward, availability, swaps, reminders, notifications, checklist, attendance, Community Activities, audience filtering, consumer migration, ChurchStructureMembership serving inference, or LightingTeam-specific model.
- Browser/mobile QA was blocked by Windows sandbox/endpoint/browser issues and requires manual QA if not already manually verified.

### MO-S.3 Assignment Coverage Display for Required Teams

Status: completed.

Completed scope:
- Added read-only assignment coverage display that compares `ServiceEvent` required teams against actual `TeamAssignment` and `TeamAssignmentMember` data.
- `TeamAssignment` list is the primary operational coverage surface.
- `TeamAssignment` detail shows compact event coverage.
- `ServiceEvent` detail shows coverage only to staff/service-event or team-assignment managers; ordinary event viewers do not see coworker coverage.
- `/staff/` adds an upcoming required-team gap count.
- Coverage states include required team assigned with members, required team with assignment but no active members, required team unassigned/missing, and non-required additional assignment.
- Multiple assigned coworkers display with confirmation status.
- Browser automation was blocked; user completed manual QA and accepted the MO-S.3 UI.

Boundaries:
- Coverage display is not a checklist.
- Coverage display is not availability tracking.
- Coverage display is not automatic scheduling.
- Coverage display should not hide missing teams behind aggregate counts.
- No schema changes, migrations, assignment auto-creation, workflow-state changes, new permissions, team-leader scheduling workspace, rotation/copy-forward, availability, swaps, reminders, notifications, checklist, attendance, Community Activities, audience filtering, consumer migration, ChurchStructureMembership serving inference, or LightingTeam-specific model were added.

### MO-S.4 Team-Leader Scheduling Workspace for Same-Type Events

Status: completed.

Goal:
- Give ministry team leaders an efficient entry point to schedule their own team for recurring or same-type events, especially Sunday Service rotation.

Completed scope:
- Added a team-scoped manual scheduling workspace at `/teams/<team_id>/schedule/`.
- Team detail shows the contextual Schedule Team / 安排团队服事 link only for users who can manage that team's assignments.
- Staff, superusers, and global assignment managers can schedule any team.
- Lead and Coordinator roles can schedule their own team assignments.
- Ordinary members, `can_lead`-only members, and unrelated users cannot schedule.
- My Serving provides the non-staff team leader entry point through Teams I manage / 我负责的团队.
- The default view uses All event types / 全部类型 across the upcoming 8-week window.
- The workspace shows events where the selected team is required or already assigned.
- Specific event type filtering still works.
- Scheduling uses one active in-page schedule/edit form selected by event or assignment query parameters.
- `service_event` and `ministry_team` are server-locked.
- Existing event/team assignments are updated instead of duplicated.
- Loading the workspace creates no assignments.
- ServiceEvent MinistryContext visible wording is Host / Language Label / 主办/语言标签（可选） and is label-only; it does not control visibility, serving assignment, or permissions and does not replace future ChurchStructureUnit-based audience or coverage scope.
- MO-S.4A scheduling semantic cleanup was completed after manual QA.
- Browser automation was blocked by the Windows browser sandbox issue; user manually QA'd and accepted the MO-S.4A cleanup.

Boundaries:
- Do not infer team-leader rights from church-structure membership.
- Do not expose unrelated teams or private staff-only operational context.
- Do not add automatic rotation or copy-forward until manual flow is proven.
- No schema changes, migrations, MO-S.5 implementation, rotation/copy-forward, availability tracking, swaps, reminders, notifications, checklist, attendance, Community Activities, audience filtering, consumer migration, ChurchStructureMembership serving inference, or LightingTeam-specific model were added.

### MO-S.5 Limited Rotation Helper / Copy-Forward Workflow

Goal:
- After manual scheduling is proven, consider a limited helper that copies prior assignments or drafts a simple rotation for review.

Likely scope:
- Copy assignments forward from a previous same-type event or date range.
- Require review before publish/use.
- Keep humans responsible for final assignment choices.

Boundaries:
- This is not a full automatic scheduling engine.
- Do not add availability matrices, swap requests, reminder automation, notifications, or complex optimization unless separately planned.
- Do not start this phase until MO-S.2 through MO-S.4A have proven the manual workflow.

## 6. Explicitly Deferred

The following remain deferred unless separately planned:

- Automatic scheduling engine.
- Availability tracking.
- Swap requests.
- Reminder automation.
- Notifications.
- Checklist engine.
- Service review notes.
- Community Activities.
- Audience filtering or visibility migration.
- ChurchStructureMembership-driven serving permissions.

Required-team coverage is a scheduling clarity feature. It is not a checklist, availability system, swap workflow, reminder workflow, notification system, or automatic scheduler.

## 7. Recommended Next Implementation Slice

MO-S.3 is complete as a read-only assignment coverage display after user-completed manual QA.

MO-S.4 is complete as a team-scoped manual scheduling workspace that stays scoped to explicit `MinistryTeam` / `TeamAssignment` capabilities and does not add rotation/copy-forward or automation.

MO-S.4A is complete as scheduling semantic cleanup after manual QA. The next safe ministry scheduling phase is MO-S.5 planning/design only if the team wants to continue and the manual scheduling workflow is accepted in real use; this document does not authorize implementation.
