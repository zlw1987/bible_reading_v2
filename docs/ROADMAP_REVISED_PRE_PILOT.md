# Roadmap Revised Pre-Pilot

## 1. Purpose

This revised phased roadmap reflects the new priority order before Lighting Pilot validation and before any Checklist V1 work.

The project should remain a lightweight church spiritual life and ministry workflow system, not a full church ERP.

## Phase 0 - Source Hygiene / Baseline

- Avoid treating local artifacts as product state.
- Keep repo/zip clean from `.venv`, `env`, `__pycache__`, `.vs`, and local-only artifacts where possible.
- Use current repo state as source of truth.

## Phase 1 - IA / Navigation Reset

- Define top-level navigation.
- Separate Today, Reading, Bible Study, Prayer, My Serving, Profile.
- Group staff management.
- Clarify page responsibilities.
- Fix bilingual nav labels.

## Phase 2 - Completed V1 QA / Stabilization

Items likely completed but needing QA:
- Daily Reading V1
- Prayer V1
- Reflection/reporting
- ServiceEvent Foundation
- MinistryTeam + TeamMembership
- TeamAssignment V1
- My Serving V1
- Lighting import basic flow

Work:
- Fix copy.
- Fix bilingual display.
- Fix stale docs.
- Do not add major features.

## Phase 3 - Bible Study V2 Planning

- Document two-layer Bible Study model.
- Define BibleStudyLesson and BibleStudyMeeting.
- Define group-level worship set.
- Define group-level guide/questions.
- Define simple meeting roles.
- Define ServiceEvent relationship.
- Define non-goals.

## Phase 4 - Bible Study V2 Implementation

Future only, not now:
- Add models/migration strategy.
- Add lesson UI.
- Add group meeting UI.
- Add group worship set UI.
- Add group guide/questions UI.
- Add simple role display.

## Phase 5 - Lighting Pilot Preflight Cleanup

- Fix stale Lighting QA docs.
- Validate CSV template/download flow.
- Validate bilingual data.
- Write My Serving member guide.
- Write ministry coordinator guide.
- Confirm dry-run/re-run behavior.
- Confirm no sensitive data import.

## Phase 6 - Lighting Pilot Validation

- Validate real pilot data.
- Validate user visibility.
- Validate coordinator workflow.
- Validate bilingual display.
- Validate no checklist is needed for pilot.

## Phase 7 - Checklist V1

Deferred.

Only reconsider after Lighting Pilot validation.

Keep it minimal when eventually implemented:
- generic checklist template
- assignment-level checklist items
- manual check/uncheck
- no reminders
- no enforcement engine
- no scheduling system

