# Lighting Pilot Preflight Requirements

## 1. Purpose

This document records why Lighting Pilot should not proceed to Checklist V1 yet, and what must be validated first.

## 2. Current Decision

Do not proceed to Checklist V1 yet.

Reason:
- The project still needs IA cleanup.
- Bible Study flow needs clarification.
- Bilingual data display needs validation.
- Pilot setup/import behavior needs validation with real pilot-shaped data.

## 3. Preconditions Before Lighting Pilot Can Be Considered Ready

### IA

- User can clearly distinguish Today, Reading, Bible Study, Prayer, My Serving, and Staff Management.
- My Serving is the independent serving entry point.
- Daily Reading does not absorb serving operations.

### Import/Setup

- Lighting pilot import supports dry-run.
- Re-run should not create duplicates.
- Import should only create/update appropriate ServiceEvent, MinistryTeam, TeamMembership, TeamAssignment data.
- No sensitive fields should be imported.

### Bilingual Data

- Chinese UI should show 主日崇拜 / 灯光组.
- English UI should show Sunday Service / Lighting Team.
- Import/setup should support both Chinese and English event/team names where applicable.

### Documentation

- Need a member-facing My Serving guide.
- Need a coordinator-facing ministry assignment guide.
- Existing Lighting QA docs must not contradict current product direction.
- If any old document says Upcoming Serving appears on the home page, that should be revised if the product direction is that My Serving owns serving details.

## 4. Recommended Additional Docs

### docs/MY_SERVING_MEMBER_GUIDE.md

Should cover:
- How to find My Serving.
- How to read assignment details.
- How to confirm serving.
- What to do if assignment is missing or wrong.
- What information should not be shared in notes.

### docs/MINISTRY_COORDINATOR_GUIDE.md

Should cover:
- How to confirm ServiceEvent setup.
- How to check MinistryTeam and TeamMembership.
- How to create/update TeamAssignment.
- How to review confirmation status.
- What sensitive data must not be entered.

## 5. Checklist V1 Is Deferred

Checklist V1 should only be reconsidered after:
- IA is cleaned up.
- Bible Study V2 direction is documented.
- Lighting Pilot import/setup is validated.
- Bilingual data display is validated.
- Team member/coordinator guides are available.
- Pilot users can complete the workflow without checklist support.

## 6. Non-Goals

- No automatic reminders.
- No scheduling engine.
- No availability matrix.
- No swap requests.
- No full historical import.
- No LightingTeam-specific model.

## 7. Documentation Consistency Status

The previously identified stale documentation items have been cleaned up:
- `docs/LIGHTING_TEAM_PILOT_QA_CHECKLIST.md` no longer treats the home page as the serving management surface.
- `docs/READING_V1_QA_CHECKLIST.md` now reflects the intended top-level navigation with My Serving.
- `docs/BIBLE_STUDY_V1_QA_CHECKLIST.md` now treats Bible Study V1 as existing functionality superseded for future planning by Bible Study V2.
- `docs/MINISTRY_TEAM_OPERATIONS_V1_PLAN.md` now treats My Serving as the independent user serving surface.

Future doc updates should continue to preserve the current boundaries: My Serving owns serving details, Today stays lightweight, Bible Study V2 governs future Bible Study planning, and Checklist V1 remains deferred until preflight validation is complete.
