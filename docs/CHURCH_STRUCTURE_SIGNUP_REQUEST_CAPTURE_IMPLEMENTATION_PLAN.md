# Church Structure Signup Request Capture Implementation Plan

## 1. Purpose

CS-H.6A planned a future implementation slice for capturing a user's requested `ChurchStructureMembership` unit during normal signup/profile onboarding. CS-H.6B implements the signup-only portion of that plan.

CS-H.6A was planning/docs only. CS-H.6B changes only normal signup request capture and focused tests. It does not change models, migrations, profile behavior, `Profile.small_group`, approval ownership, or any runtime consumer.

Runtime remains legacy `Profile.small_group` based until a separate consumer migration is designed and implemented. Requested membership grants no visibility.

## 2. Current Runtime Baseline

Current signup/profile behavior after CS-H.6B:
- `SignUpForm` exposes optional `requested_unit` choices backed by active small-group/fellowship `ChurchStructureUnit` rows.
- Signup creates a pending `ChurchStructureMembership` when a requested unit is selected.
- Signup does not write `Profile.small_group` at request time.
- `ProfileForm` also exposes and updates legacy `Profile.small_group`.
- `/studies/`, reading progress, `ServiceEvent`, My Serving, and other existing consumers continue to use legacy fields.

Current membership workflow state:
- `ChurchStructureMembership` exists and supports `status=requested`.
- CS-H.7B through CS-H.7F implemented and verified the staff approval flow for pending requested memberships.
- Staff approval can activate a requested membership and, during transition, sync `Profile.small_group` only for the exactly-one active mapped legacy `SmallGroup` case.
- Signup creates requested memberships only through CS-H.6B request capture.

## 3. Implementation Slice Recommendation

CS-H.6B implemented signup-only request capture:
- replace the signup self-assignment behavior with request capture for normal new users
- create or update a pending `ChurchStructureMembership` with `status=requested`
- do not approve automatically
- do not update `Profile.small_group` at request time
- hand the request to the existing staff membership request list/detail/approve/reject flow
- defer signup request note capture because no signup note field exists in CS-H.6B

Profile-based change requests remain deferred to CS-H.6C. Signup is the narrower, lower-conflict entry point because brand-new users often have no current active primary membership.

## 4. Requested Unit Capture Surface

Signup should capture:
- account fields already present today
- optional requested church structure unit
- optional short operational note in a later slice; CS-H.6B does not implement note capture
- a clear "Not sure / New visitor" option

Profile may later capture:
- optional requested church structure unit for users who want to request a group change
- optional short operational note
- current pending request status, if one exists

The signup/profile UI should not expose the full church structure tree. It should present active requestable small-group/fellowship choices in a simple list, plus the "Not sure / New visitor" path.

## 5. Requestable Choices

Requestable choices for V1:
- active `ChurchStructureUnit` records with `unit_type=small_group` or `unit_type=fellowship`
- leaf-like units intended for normal belonging, preferably units mapped from active legacy `SmallGroup` rows
- "Not sure / New visitor" as a non-final routing option

Do not allow normal users to request:
- inactive units
- root, ministry-context, department, custom, permission-like, operational, or serving/team units
- arbitrary IDs outside the curated requestable queryset
- audience segments or future Community Activities categories

If broader district/ministry-context routing is needed later, it should be a separate staff-oriented routing decision or a later explicit design update.

## 6. Requested Membership Creation

When a user submits a requested unit:
- create a `ChurchStructureMembership` for the submitted user
- set `unit` to the selected requestable `ChurchStructureUnit`
- set `status=requested`
- set `membership_type=small_group_member`
- set `is_primary=False`
- leave `start_date`, `approved_by`, and `approved_at` empty
- set `requested_by` to the same user for normal self-submitted signup/profile requests
- leave notes empty in CS-H.6B because signup does not yet expose a request note field
- when note capture is added later, store only non-sensitive operational notes

When the user chooses "Not sure / New visitor":
- do not create an active membership
- preferred V1 option: do not create a `ChurchStructureMembership` unless a real requestable unit is selected
- preserve any non-sensitive note only if the implementation has an existing safe place to show it to staff
- if staff need these visible in the existing approval list, add a separate later design for a routing/visitor request representation rather than overloading an arbitrary structure unit

Do not add a new model in CS-H.6A unless implementation discovers a blocking requirement that cannot be represented safely with `ChurchStructureMembership.status=requested`.

## 7. Duplicate and Conflict Handling

Pending duplicate rule:
- if the user already has a pending `status=requested` membership, update the existing pending request rather than creating another pending row
- update the requested unit and keep `requested_by` as the submitting user
- note updates remain deferred until a note field exists
- do not alter rejected, cancelled, ended, or active history rows

Active primary conflict rule:
- if the user already has a current active primary membership, profile-based request capture may create/update a pending request for staff review, but it must not end or replace the active membership
- staff approval remains responsible for blocking or resolving active-primary conflicts
- signup should rarely hit this case, but the implementation should still preserve the same non-mutating request behavior

Legacy `Profile.small_group` conflict rule:
- request submission must not update `Profile.small_group`
- if the requested unit maps to a different legacy `SmallGroup` than the user's current `Profile.small_group`, staff will see the current legacy group and sync warning in the existing CS-H.7 approval detail flow

Invalid request rule:
- inactive or non-requestable submitted units should fail form validation
- request submission should be atomic with account creation when used during signup
- if account creation succeeds but request creation fails unexpectedly, prefer failing the whole signup transaction over creating a user with an inconsistent hidden request state

## 8. Staff Approval Handoff

After request capture, staff should see the request in the existing CS-H.7 pages:
- pending request list shows `status=requested`
- detail page shows user, requested unit, requested_by, submitted date, current `Profile.small_group`, request note, and active-primary context
- CS-H.6B-created requests have an empty request note until note capture is implemented later
- approve activates the requested membership
- reject changes it to rejected and does not sync `Profile.small_group`
- approval syncs `Profile.small_group` only under the CS-H.7E exactly-one active mapped legacy `SmallGroup` rule

CS-H.6A should not add a separate staff queue, new approval route, or alternate approval behavior.

## 9. User-Facing Messaging

Signup/profile copy should make these points:
- the selected group/unit is a request, not final membership
- staff will review the request
- choosing a unit does not immediately change access
- notes must be brief and non-sensitive
- users who are unsure should choose "Not sure / New visitor"

Avoid promising access, approval, visibility, automatic assignment, or immediate group transfer.

## 10. Tests Required For Future Implementation

Future implementation tests should cover:
- signup with no requested unit keeps current behavior boundary and creates no requested membership
- signup with requested unit creates one `status=requested` membership
- requested membership has `requested_by=user`, no approval metadata, no start date, and `is_primary=False`
- signup request does not update `Profile.small_group`
- profile request does not update `Profile.small_group`
- duplicate pending submission updates the pending request rather than creating another pending row
- active primary conflict remains pending and does not mutate active membership
- invalid/inactive/non-requestable unit is rejected
- requested membership grants no `/studies/`, reading progress, `ServiceEvent`, My Serving, permission, serving assignment, or audience access
- staff list/detail display the captured request context for approval

## 11. Non-Goals

CS-H.6A does not include:
- implementation
- model changes
- migrations
- views, forms, templates, URLs, tests, or runtime behavior changes
- automatic approval
- direct user self-assignment to active membership
- `Profile.small_group` updates at request time
- consumer migration from `Profile.small_group` to `ChurchStructureMembership`
- audience selection or filtering
- Community Activities
- `/studies/`, reading progress, `ServiceEvent`, or My Serving changes
- staff approval workflow rewrites
- broad roadmap rewrites

## 12. Recommended Sequence

Recommended next sequence:
- CS-H.6A: signup request capture implementation planning. Completed by this document.
- CS-H.6B: implement signup request capture only, with focused tests. Completed.
- CS-H.6C: optionally implement profile-based request/change capture, with focused tests.
- CS-H.7 approval flow continues to own staff review, approve/reject, and transition `Profile.small_group` sync.
- Later: migrate selected consumers from `Profile.small_group` to approved active membership, one consumer at a time.

Do not bundle signup request capture with staff approval rewrites, consumer migration, audience filtering, or Community Activities.
