# Church Structure Signup Request Flow Design

## 1. Purpose

CS-H.6 designs a future signup/onboarding flow where a user can request a church structure unit or small group, but staff/admin approval is required before that request becomes official active membership.

This flow is needed because new users often know the group they attend, but signup is not a safe place to grant final belonging automatically. Group membership affects current and future visibility decisions, including Bible Study access and future audience eligibility. Direct self-assignment is unsafe because users can choose the wrong group, misunderstand the hierarchy, or accidentally gain visibility they should not have.

This is design-only. It does not change signup behavior, models, migrations, views, forms, templates, URLs, admin UI, `Profile.small_group`, or any runtime consumer.

## 2. Current Signup State

Current runtime behavior still uses:
- `MinistryContext`
- `District`
- `SmallGroup`
- `Profile.small_group`

`Profile.small_group` remains the current runtime belonging field. `/studies/`, reading progress, `ServiceEvent`, signup behavior, and My Serving must not switch to `ChurchStructureMembership` as part of this design.

`ChurchStructureUnit` has been seeded/mapped from current structure data, but it is not the runtime source of truth. `ChurchStructureMembership` exists and has been backfilled, but no runtime consumer uses it yet. Signup/onboarding does not create requested memberships today.

## 3. Future Signup Fields

Recommended future signup/onboarding fields:
- normal account fields
- language
- requested unit or requested small group
- optional note
- "Not sure / New visitor" option

The requested unit field should be optional. Choosing a requested unit should create or update a pending request only; it must not assign final active membership.

The optional note should be short and operational, such as "I attend Rainbow 1" or "I am new." It must not invite sensitive pastoral, medical, financial, legal, family, counseling, or private information.

## 4. Requestable Unit Rules

Recommended rules:
- Prefer active small-group/fellowship leaf units as requestable choices.
- Provide a clear "Not sure / New visitor" choice.
- Allow an optional note so staff can resolve uncertainty.
- Do not allow arbitrary `MinistryTeam`, serving, operational, or permission-like units.

Users should usually request the most specific active small-group/fellowship unit they know. If they are unsure, the better path is "Not sure / New visitor" plus an optional note.

Allowing district or ministry-context requests may be useful only as a fallback if staff want broader routing choices. If implemented, these broader choices should remain pending request metadata and should not become active membership unless staff resolves them to an appropriate membership unit.

## 5. Data Model Approach

Use the existing `ChurchStructureMembership` model with `status=requested` for V1 unless implementation later discovers a strong audit or workflow reason for a separate request model.

Design rules:
- `status=requested` does not grant visibility or eligibility.
- Only `status=active` membership may be used by future consumers.
- `requested_by` can point to the user who submitted the request.
- `notes` must be non-sensitive and operational.
- Approval may change the existing requested record to `active`, or create a separate active membership from the request, depending on final implementation details.

Using `ChurchStructureMembership.status=requested` keeps request and membership history in one lifecycle table. A separate request model should be reconsidered only if staff need richer multi-step review, external communication tracking, or more detailed audit history than the membership table can safely represent.

## 6. Signup States

Future signup/request states:
- `no request`: the user skipped group/unit selection.
- `requested / pending review`: the user requested a unit and staff has not reviewed it.
- `needs clarification`: staff needs more information before approval.
- `rejected/cancelled`: the request should not become active membership.
- `approved active membership`: staff approved official active membership.
- `unassigned visitor`: the user is known but not assigned to an official active small group/fellowship.

These states are conceptual. This task does not add fields, status values, UI, or workflow logic.

## 7. Staff/Admin Review Handoff

Future staff/admin workflow should include:
- pending request list
- approve request
- change requested unit before approval
- reject or cancel request
- mark request as needing clarification
- assign "Not sure / New visitor" users to an appropriate state or unit
- add non-sensitive operational notes

During the transition, approval of a primary small-group/fellowship membership may sync `Profile.small_group` when the approved `ChurchStructureUnit` maps to a legacy `SmallGroup`. That sync should be explicit, tested, and reversible enough for the transition period.

This document does not add custom staff admin UI. CS-H.7 separately documents the future approval workflow in `docs/CHURCH_STRUCTURE_MEMBERSHIP_APPROVAL_WORKFLOW_DESIGN.md`.

## 8. Visibility and Permission Rules

Requested membership grants no `/studies/` visibility, reading progress visibility, audience eligibility, event filtering access, or other consumer access.

Only approved active membership may be used by future consumers, and each consumer migration must be separately designed and tested. Membership is belonging, not permission. It does not grant staff/admin access and does not create serving assignments.

Permission sources remain separate, such as `ChurchRoleAssignment`, capability helpers, and existing staff/superuser checks. Serving assignment sources remain separate, such as `TeamAssignment`, `TeamMembership`, and `TeamAssignmentMember`.

## 9. Transition With Profile.small_group

For now, `Profile.small_group` remains the runtime source for current belonging behavior. Do not remove it and do not switch existing consumers in CS-H.6.

Future approval may sync `Profile.small_group` when:
- the approved active membership is primary,
- the approved unit maps to a legacy `SmallGroup`, and
- the transition implementation explicitly chooses to keep `Profile.small_group` aligned.

This sync should be treated as compatibility behavior during coexistence, not as permission or serving assignment logic.

## 10. UX Notes

Signup should stay simple:
- avoid exposing the full hierarchy to new users
- show a mobile-friendly selector
- support bilingual labels
- make "I'm not sure" obvious
- keep optional note copy short and non-sensitive
- avoid ministry-team or operational terminology in the normal signup path

Users should not need to understand the full `ChurchStructureUnit` tree to create an account.

## 11. Risks

Known risks:
- user chooses the wrong group
- visibility leak if requested membership is trusted
- staff review workload
- confusion between unit membership and ministry team participation
- sensitive information entered into notes
- duplicate pending requests
- drift between approved membership and `Profile.small_group`
- overloading signup with too much hierarchy

Mitigation direction:
- require staff/admin approval
- filter future consumers to active approved membership only
- keep request notes operational
- make "Not sure / New visitor" prominent
- deduplicate pending requests during implementation
- keep runtime consumers unchanged until separately migrated

## 12. Non-Goals

CS-H.6 does not include:
- implementation
- model changes
- migrations
- signup code changes
- forms, views, templates, or URLs
- admin approval UI
- `Profile.small_group` changes
- `/studies/` migration
- reading progress migration
- `ServiceEvent` changes
- My Serving changes
- audience selection or filtering
- Community Activities
- Staff Admin Surface implementation

## 13. Recommended Next Phases

Recommended sequence:
- CS-H.6: Signup Requested-Unit Flow Design Doc. Completed by this document.
- CS-H.6A: model/form implementation planning if needed.
- CS-H.7: admin approval workflow design. Completed.
- CS-H.7A: membership approval workflow implementation plan. Completed.
- Later: implement requested-unit capture.
- Later: implement staff/admin approval workflow.
- Later: transition sync with `Profile.small_group` if selected.
- Later: migrate selected consumers from `Profile.small_group` to active approved membership, one at a time.

Do not combine signup request capture, admin approval, and consumer migration into one implementation step.
