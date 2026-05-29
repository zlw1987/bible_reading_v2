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

- Document church structure domain boundaries.
- Clarify fellowship small groups vs MinistryTeam.
- Clarify small-group coworker roles vs TeamAssignment.
- Clarify CM/EM ministry contexts.
- Document two-layer Bible Study model.
- Define BibleStudyLesson and BibleStudyMeeting.
- Define group-level guide/questions.
- Define simple meeting roles.
- Define group-level worship set.
- Define ServiceEvent relationship.
- Define non-goals.

## Phase 4 - Bible Study V2 Implementation

Functional pieces now exist through BS-V2.6.6, including schedule/scope fields, staff IA cleanup, meeting generation, and normal `/studies/` V2 landing integration.

Completed BS-V2.6 sequence:
- BS-V2.6.0 - Schedule/scope replan documentation.
- BS-V2.6.1 - Staff IA cleanup.
- BS-V2.6.2 - Treat BibleStudySeries as Bible Study Schedule / 查经安排.
- BS-V2.6.3 - Add schedule lifecycle fields.
- BS-V2.6.4 - Add schedule scope fields.
- BS-V2.6.5 - Generate group meetings from guide/scope with a manual, idempotent staff action.
- BS-V2.6.6 - Normal user V2 landing integration.

Completed QA:
- BS-V2.6.7 - Bible Study V2 Flow QA passed.

Completed foundation steps:
- CS-F.1 - MinistryContext bridge foundation.
- CS-F.2 - MinistryContext Bible Study Schedule scope.

Future:
- Future foundation - flexible Church Structure Foundation only after the short-term bridge proves insufficient, before advanced mixed audience segments.
- BS-V2.7 - Role-aware editing permissions later only if needed.

Do not proceed directly to role-aware permissions or new modules after the V2 flow QA pass.
Generated small-group meetings should reference the weekly guide and derive schedule through the guide's series/schedule. Do not copy church-wide guide content into each meeting.

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

## Future Deferred Module - Community Activities V1

Plan as a separate future module after Bible Study V2 direction is resolved and after Lighting Pilot preflight validation.

Community Activities is for signup-oriented member/community/fellowship activities, such as small group meals, hiking activities, district fellowship, whole-church picnics, or special community gatherings.

Keep it separate from:
- Daily Reading
- Bible Study content
- Prayer
- Ministry Team Operations
- TeamAssignment
- ServiceEvent scheduling
- Checklist V1

ServiceEvent remains the official church gathering, operations, and ministry assignment anchor. CommunityActivity should handle the question "who wants to attend/signup?" while ServiceEvent + TeamAssignment should handle "which ministry team is serving?"

Future Community Activities planning should use audience segments rather than a single simple scope value. Audience segments may target the whole church, a ministry context such as CM/EM, selected districts, or selected small groups. Do not create a separate SpecialEvent model, and do not force CommunityActivity into ServiceEvent.

Advanced mixed audience segments should align with the future Church Structure Foundation plan. See `docs/CHURCH_STRUCTURE_FOUNDATION_PLAN.md`.

Do not add Activities to top navigation yet. A future navigation option may be:
- English: Today, Reading, Bible Study, Prayer, Activities, My Serving, Profile
- Chinese: 今日, 读经, 查经, 代祷, 活动, 我的服事, 个人资料

Checklist V1 remains deferred and should not be revived because of this module.

See `docs/COMMUNITY_ACTIVITIES_V1_PLAN.md`.

## Current Recommended Next Sequence

- Bible Study V2 Flow QA passed.
- CS-F.1 MinistryContext bridge foundation completed.
- CS-F.2 MinistryContext Bible Study Schedule scope completed.
- Flexible Church Structure Foundation planning only after the short-term bridge proves insufficient.
- Lighting Pilot preflight/validation or Community Activities planning depending on chosen priority.
- Later role-aware editing permissions.
- Later ServiceEvent participating_ministries / MinistryContext planning.
- Later Community Activities V1 with audience segments.
- Checklist V1 remains deferred until Lighting Pilot validation.
