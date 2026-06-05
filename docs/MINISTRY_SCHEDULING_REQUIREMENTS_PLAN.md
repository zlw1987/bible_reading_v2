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

Goal:
- Show coverage per required team on `TeamAssignment` and relevant staff/team-leader pages.

Likely scope:
- For each required team, show assigned coworkers and confirmation status.
- Show required teams with no assignment as missing or unassigned.
- Keep display usable when a team has one person, multiple people, or no assigned people.
- Link to existing assignment workflows for edits instead of creating a new scheduling engine.

Boundaries:
- Coverage display is not a checklist.
- Coverage display is not availability tracking.
- Coverage display is not automatic scheduling.
- Coverage display should not hide missing teams behind aggregate counts.

### MO-S.4 Team-Leader Scheduling Workspace for Same-Type Events

Goal:
- Give ministry team leaders an efficient entry point to schedule their own team for recurring or same-type events, especially Sunday Service rotation.

Likely scope:
- Filter events by type and date range.
- Show only teams the leader is explicitly allowed to manage.
- Let authorized team leaders create or update `TeamAssignment` records for their own team.
- Keep staff/superuser broader management separate from team-leader scoped management.

Boundaries:
- Do not infer team-leader rights from church-structure membership.
- Do not expose unrelated teams or private staff-only operational context.
- Do not add automatic rotation or copy-forward until manual flow is proven.

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
- Do not start this phase until MO-S.2 through MO-S.4 have proven the manual workflow.

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

MO-S.2 is complete. MO-S.3 should be the next safe ministry scheduling slice after manual/browser QA of the MO-S.2 UI, because coverage display depends on comparing event-level required teams against actual assignments.

MO-S.3 should keep the existing boundary: `TeamAssignment` is the actual scheduled assignment and `TeamAssignmentMember` is the assigned person plus confirmation record.
