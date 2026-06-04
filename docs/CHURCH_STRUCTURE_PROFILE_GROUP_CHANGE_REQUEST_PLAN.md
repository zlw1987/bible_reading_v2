# Church Structure Profile Group-Change Request Plan

## 1. Purpose

CS-H.6C planned a future implementation slice for logged-in users to request a group/unit change from Profile without directly editing `Profile.small_group`. CS-H.6D implements the normal-user Profile request capture portion of that plan.

CS-H.6C was planning/docs only. CS-H.6D changes only normal-user Profile request capture, focused tests, and narrow profile copy. It does not change models, migrations, signup behavior, staff approval ownership, or any runtime consumer.

Runtime remains legacy `Profile.small_group` based until a separate consumer migration is designed and implemented. Staff approval remains owned by the existing CS-H.7 membership approval pages. Approval sync behavior remains owned by CS-H.7E.

## 2. Current Profile Risk

Current `ProfileForm` exposes legacy `small_group` to logged-in users and saves it directly to `Profile.small_group`.

Risk:
- a normal user can self-edit their legacy group assignment
- current `/studies/`, reading progress, `ServiceEvent`, and related behavior still trust `Profile.small_group`
- a mistaken or self-serving profile edit can immediately change runtime visibility
- this bypasses the `ChurchStructureMembership(status=requested)` review path implemented for signup in CS-H.6B
- this bypasses the existing CS-H.7 staff approval context, conflict handling, and CS-H.7E transition sync rule

CS-H.6C should close this normal-user self-assignment gap without removing the legacy field from staff/admin support paths prematurely.

## 3. Normal User Profile Behavior

After CS-H.6D, normal logged-in users can:
- show username read-only as today
- keep email editable as today
- keep preferred language editable as today
- show current `Profile.small_group` as read-only context
- expose an optional requested unit selector for group/unit change requests
- create or update a pending `ChurchStructureMembership(status=requested)` when a requested unit is submitted
- not update `Profile.small_group` at request time
- not approve automatically
- hand off review to the existing CS-H.7 staff membership request list/detail/approve/reject flow

CS-H.6D does not implement request note capture. Notes remain empty for profile-created requests until a later safe note field is explicitly implemented.

The requested unit selector should use the same requestable choices as signup:
- active `ChurchStructureUnit` rows with `unit_type=small_group` or `unit_type=fellowship`
- no inactive, root, ministry-context, department, custom, serving/team, permission-like, audience, or Community Activities choices

If no requested unit is selected, normal profile save should update only email/language and leave membership requests unchanged.

## 4. Request Creation Behavior

When a normal user submits a requested unit from Profile:
- create or update one pending `ChurchStructureMembership`
- set `unit` to the selected requestable `ChurchStructureUnit`
- set `status=requested`
- set `membership_type=small_group_member`
- set `is_primary=False`
- set `requested_by` to the same user
- leave `start_date`, `approved_by`, and `approved_at` empty
- leave notes empty unless CS-H.6C explicitly adds a safe non-sensitive note field

Request submission must not:
- update `Profile.small_group`
- end or replace active memberships
- grant visibility
- infer permissions
- create serving assignments
- update audience eligibility

## 5. Duplicate Pending Handling

If the user already has a pending `status=requested` membership:
- update the existing pending request instead of creating another pending row
- update the requested unit
- update the non-sensitive note only if CS-H.6C implements a note field
- preserve `requested_by` as the submitting user
- do not alter active, rejected, cancelled, or ended history rows

If the user has multiple pending rows because of older data or manual admin edits:
- use the oldest pending row for normal-user update
- do not silently delete or merge the others
- staff should resolve duplicate history through the approval/admin process

## 6. Active Primary and Legacy Conflict Handling

If the user already has a current active primary `ChurchStructureMembership`:
- normal Profile request capture may still create/update a pending request
- it must not end the active primary membership
- it must not create a new active primary membership
- CS-H.7 approval should continue to block or require staff resolution for active-primary conflicts

If the user already has `Profile.small_group`:
- Profile should show it as current group context
- requested unit submission must not change it
- staff detail should continue to show current `Profile.small_group`
- CS-H.7E alone decides whether approval syncs `Profile.small_group` after staff approval

If the requested unit maps to no active legacy `SmallGroup`, multiple active legacy groups, or an inactive legacy group:
- request capture should still be allowed if the unit is requestable
- approval may activate membership but CS-H.7E no-sync rules continue to apply

## 7. Staff and Superuser Behavior

Do not break current staff support flow without an explicit staff-admin plan.

Recommended CS-H.6C boundary:
- normal user Profile should stop directly editing `Profile.small_group`
- staff/superuser support surfaces may continue to edit `Profile.small_group` where they already can, including Django Admin or staff user-support flows
- any staff direct edit should remain understood as legacy runtime support, not membership approval
- CS-H.7 pages remain the official membership request approval path

If a future staff profile-edit UI shares the same `ProfileForm`, implementation should split normal-user and staff-capable profile forms rather than giving normal users the staff edit surface.

## 8. User-Facing Messaging

Profile copy should make clear:
- current group is shown for reference
- selecting a requested unit sends a request to staff
- the request does not immediately change group access
- staff approval is required
- notes, if added, must be brief and non-sensitive

Avoid promising approval, access, transfer timing, or visibility changes.

## 9. Tests Required For Future Implementation

Future tests should cover:
- normal profile page shows current `Profile.small_group` read-only
- normal profile form no longer accepts direct `small_group` self-edit
- email/language profile updates still work
- submitting no requested unit creates no membership request
- submitting a requestable active small-group unit creates one pending request
- submitting a requestable active fellowship unit creates one pending request
- inactive and non-requestable units are rejected by form validation
- profile request does not update `Profile.small_group`
- duplicate pending request updates the existing pending row
- active primary membership remains unchanged and request stays pending
- requested profile change grants no `/studies/`, reading progress, `ServiceEvent`, My Serving, permission, serving assignment, audience, or Community Activities access
- staff membership request list/detail show the profile-created request
- staff/superuser direct legacy support path remains available if intentionally retained

## 10. Non-Goals

CS-H.6C does not include:
- implementation
- model changes
- migrations
- views, forms, templates, URLs, tests, or runtime behavior changes
- signup changes
- automatic approval
- `Profile.small_group` update at request time
- CS-H.7 approval rewrite
- CS-H.7E sync behavior changes
- consumer migration from `Profile.small_group` to `ChurchStructureMembership`
- audience selection or filtering
- Community Activities
- `/studies/`, reading progress, `ServiceEvent`, or My Serving changes
- broad roadmap rewrites

## 11. Recommended Sequence

Recommended next sequence:
- CS-H.6C: profile group-change request capture planning. Completed by this document.
- CS-H.6D: implement normal-user Profile request capture only, with focused tests. Completed.
- CS-H.6D.1: rendered-page/manual QA and docs closure for normal-user Profile request capture. Completed.
- Later: decide whether staff support surfaces need a dedicated legacy `Profile.small_group` edit form.
- CS-H.7 approval flow continues to own staff review, approve/reject, and transition `Profile.small_group` sync.
- Later: migrate selected consumers from `Profile.small_group` to approved active membership, one consumer at a time.

Do not bundle profile request capture with approval rewrites, consumer migration, audience filtering, or Community Activities.

## 12. CS-H.6D.1 QA Closure

CS-H.6D.1 verified the rendered Profile request flow with local QA data.

Verified:
- normal Profile shows current `Profile.small_group` as read-only context
- normal Profile no longer renders an editable `small_group` field
- email and preferred language still save
- tampered `small_group` POST data does not update `Profile.small_group`
- saving with no `requested_unit` creates no membership request
- active requestable small-group/fellowship units create or update one pending `ChurchStructureMembership`
- inactive and non-requestable units are rejected by normal form validation
- profile-created requests appear in the existing CS-H.7 staff membership request list and detail pages
- requested profile changes do not grant `/studies/`, reading, `ServiceEvent`, My Serving, permission, serving assignment, audience, or Community Activities access

No signup behavior, models, migrations, approval ownership, consumer migration, audience filtering, or Community Activities behavior changed in CS-H.6D.1.
