# ServiceEvent Audience Scope Redesign Plan

## 1. Purpose

SE-AS.1 is a docs-only redesign plan for future `ServiceEvent` audience scope.

Historical/superseded goal: define how `ServiceEvent` audience selection should eventually move from the then-current legacy scope fields to the flexible `ChurchStructureUnit` tree, without changing runtime behavior in that docs-only slice. Current ServiceEvent visibility uses `ServiceEventAudienceScope` rows plus active primary `ChurchStructureMembership`, zero-row events fail closed, and the legacy scope fields were removed in SE-FIELD-RETIRE.1A.

This plan does not implement app code, schema changes, migrations, filtering, permissions, or consumer migration.

DOCS-AS.1 alignment: `ServiceEvent` / Church Gatherings shares the same `ChurchStructureUnit` audience-scope foundation as Bible Study Schedule and future Community Activities. Under DOCS-AS.1, Bible Study Schedule audience scope was the first narrow runtime consumer (BS-AS.1 / BS-AS.2 / BS-AS.2A). Historical note: it originally resolved selected `ChurchStructureUnit` rows into legacy `SmallGroup` rows for meeting generation and kept member visibility on `Profile.small_group`. **Current status:** Bible Study V2 generation is structure-native; `ServiceEventAudienceScope` rows are the ordinary-user visibility source, CS-CORE.2B-A switched audience-row matching to active primary `ChurchStructureMembership`, SE-RETIRE.1B retired the zero-row fallback, and SE-FIELD-RETIRE.1A removed the legacy `scope_type` / `district` / `small_group` fields. This SE-AS.1 plan is the historical redesign record; it did not itself migrate `ServiceEvent` runtime.

## 2. Current State

> **Current status (superseded):** This section captured the SE-AS.1-era state. ServiceEvent visibility later moved to `ServiceEventAudienceScope` rows when an event has them (SE-AS.4), SE-AS.5 added the staff audience picker, CS-CORE.2B-A switched audience-row matching to active primary `ChurchStructureMembership`, SE-RETIRE.1B retired the zero-row legacy fallback, and SE-FIELD-RETIRE.1A removed the legacy `scope_type` / `district` / `small_group` fields. The legacy behavior below is historical design context only.

Historical/superseded SE-AS.1-era behavior: `ServiceEvent` audience behavior still used legacy fields:

- `scope_type`
  - `global`
  - `district`
  - `small_group`
- `district`
- `small_group`

Historical/superseded SE-AS.1-era visibility: normal-user visibility still depended on `Profile.small_group`:

- Global published/completed events can be seen by normal authenticated users.
- District-scoped events are visible when the user's current `Profile.small_group` belongs to the matching legacy district.
- Small-group-scoped events are visible when the user's current `Profile.small_group` matches the event small group.
- Staff/service-event managers can see events through existing management rules.

SE-AS.1-era supporting fields, now partly superseded by later field retirements:

- `ServiceEvent.ministry_context` is Host / Language Label / 主办/语言标签 only. It may describe broad context, language ministry, host, or legacy grouping, but it must not control visibility, serving assignment, or permissions.
- `ServiceEvent.required_teams` records Required Ministry Teams / 需要的事工团队 as event-level scheduling expectations.
- `ServiceEvent.rotation_anchor_team` is Rotation Anchor Team / 配搭参考团队, a scheduling hint only.
- `TeamAssignment` remains the actual scheduled servant/team assignment layer.

Current church-structure foundations:

- `ChurchStructureUnit` is the flexible structure tree.
- `ChurchStructureMembership` is the ordinary-member belonging source for migrated consumers, including ServiceEvent audience-row matching.
- `ServiceEventAudienceScope` links `ServiceEvent` to `ChurchStructureUnit` and is the current ordinary-user runtime visibility source when rows exist.
- Historical/superseded: at SE-AS.1 time, legacy `MinistryContext`, `District`, `SmallGroup`, and `Profile.small_group` remained the current runtime source until separately approved consumer migration. That is no longer current ServiceEvent behavior.
- Requested memberships do not grant access.

## 3. Target Model

Future `ServiceEvent` audience scope should use the `ChurchStructureUnit` tree.

Recommended target behavior:

- A `ServiceEvent` can select one or more `ChurchStructureUnit` rows as audience targets.
- Selecting a parent unit includes all descendants unless a narrower descendant selection is used to narrow that branch.
- The model must support flexible depth and should not hard-code Church -> CM/EM -> District -> SmallGroup.
- Whole Church / 全教会 is represented by the root unit.
- CM / 中文部, EM / English Ministry, districts, groups, classes, fellowships, and future sub-units are all tree units, not separate hard-coded audience concepts.

Selection examples:

- Whole Church / 全教会 means all descendants.
- CM / 中文部 means all CM descendants when no narrower CM descendant is selected.
- A district means all groups under that district when no narrower group is selected.
- A small group means only that group.
- EM can support its own relevant sub-units such as groups, classes, or fellowships without schema changes.

Redundant selection handling:

- If a parent unit is selected, descendant units are already included.
- The saved effective audience should not need both a parent and its descendant.
- A later staff UI should prevent redundant descendant selection while the parent branch remains selected.
- If staff intentionally narrow a branch, the UI should replace the broader parent target with the narrower descendant target.
- If redundant ancestor-plus-descendant selections are submitted or imported anyway, the effective-audience calculation should normalize them to one meaning before display or filtering.
- Default normalization should prefer the broader selected ancestor and drop redundant descendants. Narrowing should be represented by saving the narrower descendant without the broader ancestor.
- Example: `CM` alone means all CM descendants. `CM > District A` alone means that district branch. `CM` plus `CM > District A` should normalize back to `CM` unless a reviewed migration explicitly rewrites the stored target to `CM > District A`.
- The stored model may preserve raw selections for audit/debug in an early phase, but all runtime display and future filtering should use the normalized effective audience.

Concept separation:

| Concept | English label | Chinese label | Meaning |
| --- | --- | --- | --- |
| Audience / Coverage Scope | Coverage Scope | 覆盖对象 | Who this event is for. Future source: selected `ChurchStructureUnit` rows. |
| Host / Language Label | Host / Language Label | 主办/语言标签 | Optional label for host, language, or ministry background. Not visibility. |
| Required Ministry Teams | Required Ministry Teams | 需要的事工团队 | Teams expected to serve. Not audience. |
| Rotation Anchor Team | Rotation Anchor Team | 配搭参考团队 | Scheduling/copy-forward hint. Not audience or permission. |
| Actual scheduled servants | TeamAssignment | 服事安排 | Actual team and member assignment for an event. |

## 4. Migration Options

### Option A: Add ServiceEventAudienceScope Beside Legacy Fields

Add a future model such as `ServiceEventAudienceScope` or `ServiceEventAudienceSelection`:

- `service_event`
- `church_structure_unit`
- optional metadata such as `created_at`

Keep current `scope_type`, `district`, and `small_group` fields intact during coexistence.

Pros:

- Existing events keep working.
- Existing visibility behavior remains unchanged until explicitly migrated.
- Missing or ambiguous legacy-to-`ChurchStructureUnit` mappings do not break runtime behavior.
- Staff can review and compare legacy scope against future scope before filtering changes.
- Rollback is simpler because the legacy fields remain source of truth during early phases.

Cons:

- Coexistence requires clear UI labels and admin display.
- Temporary dual data can drift if edit rules are unclear.
- Later consumer migration still needs careful tests.

### Option B: Replace or Extend Current Scope Fields Directly

Change current `scope_type`, `district`, and `small_group` behavior to use `ChurchStructureUnit` directly.

Pros:

- Fewer long-term fields.
- Less coexistence surface after completion.

Cons:

- Higher risk to existing event visibility.
- Harder to handle unmapped or ambiguous legacy records safely.
- More likely to bundle schema change, UI change, and visibility migration together.
- Harder to roll back if normal-user visibility changes unexpectedly.

Recommendation:

Use Option A. Add a separate future audience-scope foundation first, keep legacy fields intact, and do not migrate visibility until a later explicitly approved phase.

## 5. Phased Implementation Proposal

Renumbering note: SE-AS.3 has been re-scoped as the docs-only ServiceEvent Audience Runtime Migration Plan, completed in `docs/SERVICE_EVENT_AUDIENCE_RUNTIME_MIGRATION_PLAN.md`. That plan supersedes the SE-AS.3 through SE-AS.6 numbering below: runtime visibility rule with legacy fallback is SE-AS.4, staff selector UI and display is SE-AS.5, and backfill/compatibility/cleanup planning is SE-AS.6. The phase content below remains valid as design background.

### SE-AS.1 Docs Plan Only

Status: completed by this planning document.

Scope:

- Define current state, target model, migration options, phased plan, UI wording, compatibility, and non-goals.
- No runtime behavior changes.

### SE-AS.2 Model-Only Audience Scope Foundation

Status: complete as a data/model foundation only.

Completed scope:

- Added the `ServiceEventAudienceScope` model linking `ServiceEvent` to `ChurchStructureUnit` (`unit`), with a `created_at` timestamp.
- `ServiceEvent` delete cascades audience scope rows; `ChurchStructureUnit` delete is protected (`PROTECT`) while referenced.
- A unique `ServiceEvent` + `ChurchStructureUnit` constraint prevents duplicate selections.
- Validation requires an active unit, rejects redundant ancestor/descendant selection for the same event, and allows sibling unit selections.
- `ServiceEvent.get_audience_scope_units()` returns the selected units for a saved event.
- An existing `ServiceEvent` with no audience scope rows remains valid; adding audience scope rows does not change `ServiceEvent.can_be_seen_by`.
- Model and tests were added; no admin, management command, data backfill, or other surfaces were added.

Explicitly not included (still future):

- Historical/superseded for SE-AS.1 only: runtime `ServiceEvent` visibility still used legacy `scope_type` / `district` / `small_group` and `Profile.small_group`, and `ServiceEventAudienceScope` was not yet the current runtime source of truth. Current ServiceEvent visibility uses audience rows plus active primary membership, zero-row events fail closed, and the legacy scope fields were removed.
- No staff UI selector, forms, templates, routes, admin surface, or read-only display.
- No audience filtering, visibility migration, or consumer migration.
- No `ServiceEvent.can_be_seen_by` change; requested `ChurchStructureMembership` still does not grant event visibility.
- Legacy `scope_type`, `district`, and `small_group` fields are not deprecated.
- The staff UI selector and the visibility/filtering consumer migration remain future and require separate approval (SE-AS.5 and SE-AS.4 under the renumbering in `docs/SERVICE_EVENT_AUDIENCE_RUNTIME_MIGRATION_PLAN.md`).

### SE-AS.3 Staff Create/Edit UI

Future implementation only.

Likely scope:

- Add staff-facing hierarchical audience selection for `ChurchStructureUnit`.
- Present it as audience selection, not internal model editing.
- Prefer preventing redundant descendant selection when a parent branch is selected.
- Show a normalized effective-audience preview.
- Keep legacy fields visible or bridged behind a compatibility layer until migration is approved.

### SE-AS.4 Read-Only Display and Admin Clarity

Future implementation only.

Likely scope:

- Show future audience scope read-only on event detail/admin surfaces for staff clarity.
- Clearly distinguish current legacy visibility fields from future audience-scope data.
- Preserve normal-user copy without internal unit codes, IDs, or implementation labels.

### SE-AS.5 Consumer Migration Plan for Visibility

Future planning and implementation only after explicit approval.

Likely scope:

- Decide how `ServiceEvent.can_be_seen_by` should use approved active `ChurchStructureMembership`.
- Define fallback behavior when mappings are missing or ambiguous.
- Add tests for whole-church, CM/EM, district, group, inactive units, requested memberships, ended memberships, and manager access.
- Do not infer serving permissions from membership.

### SE-AS.6 Legacy Field Deprecation

Future implementation only after validation.

Likely scope:

- Consider deprecating `scope_type`, `district`, and `small_group` only after data migration, visibility validation, staff QA, rollback planning, and production confidence.
- No destructive migration until the future audience model has proven stable.

## 6. Compatibility Rules

- Existing events must keep working.
- Historical/superseded: at SE-AS.1 time, global/district/small_group scope had to continue driving runtime visibility until a separately approved migration.
- Where legacy records already map to `ChurchStructureUnit`, they can inform future scope backfill or preview.
- Missing or ambiguous mapping must not break event detail, event lists, staff workflows, or normal-user visibility.
- No observable `ServiceEvent` visibility behavior should change through SE-AS.3.
- Under the renumbered plan, SE-AS.4 may add the runtime audience-row visibility rule, but it must preserve exact legacy fallback behavior for events with no audience rows and requires a preflight check for any existing `ServiceEventAudienceScope` rows.
- No consumer migration is authorized by this plan.
- Requested memberships must not grant event visibility.
- Only approved active memberships may eventually count when a future consumer migration is explicitly approved.

## 7. UI / UX Direction

Staff UI should feel like hierarchical audience selection:

- Use user-facing tree labels.
- Show parent/child structure clearly.
- Make parent selection behavior obvious.
- Show normalized effective audience before save or publish.
- Prevent or clearly mark redundant descendant selections.
- Preserve inactive historical selections for display if needed, but do not offer inactive units for new selection.

Normal-user UI:

- Do not expose internal model names, IDs, codes, enum values, or source-of-truth language.
- Show readable audience labels only when appropriate.

Preferred wording:

- Coverage Scope / 覆盖对象
- Host / Language Label / 主办/语言标签
- Required Ministry Teams / 需要的事工团队
- Rotation Anchor Team / 配搭参考团队

## 8. Permissions and Boundaries

Permissions:

- Do not infer event visibility from requested memberships.
- Do not infer serving permissions from `ChurchStructureMembership`.
- Do not infer team leadership from church-structure membership.
- Do not affect `TeamAssignment`, My Serving, required teams, rotation anchor behavior, or ministry scheduling permissions.

Non-goals:

- No app code changes in SE-AS.1.
- No schema changes or migrations in SE-AS.1.
- No audience filtering implementation.
- No consumer migration.
- No Community Activities.
- No notifications.
- No attendance.
- No MinistryTeam or TeamAssignment changes.
- No required-team behavior changes.
- No rotation-anchor behavior changes.
- No changes to `ServiceEvent.can_be_seen_by`.
