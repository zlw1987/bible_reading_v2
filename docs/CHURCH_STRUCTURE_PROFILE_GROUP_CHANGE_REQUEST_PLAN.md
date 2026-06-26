# Church Structure Profile Group-Change Request Plan

> **Status note (superseded):** this is the CS-H.6C/6D transition plan from
> before `Profile.small_group` field retirement. `Profile.small_group` was later
> removed in PROFILE-SG-FIELD-RETIRE.1A, and approved migrated runtime paths now
> use active primary `ChurchStructureMembership` or structure/audience rows as
> documented in `docs/LEGACY_PROFILE_SMALL_GROUP_CONSUMER_INVENTORY.md`.
> Statements below that call `Profile.small_group` current runtime or current
> Profile form state are preserved as historical implementation context only.

## 1. Purpose

CS-H.6C planned a future implementation slice for logged-in users to request a group/unit change from Profile without directly editing `Profile.small_group`. CS-H.6D implements the normal-user Profile request capture portion of that plan.

CS-H.6C was planning/docs only. CS-H.6D changed only normal-user Profile request capture, focused tests, and narrow profile copy. At that transition point, it did not change models, migrations, signup behavior, staff approval ownership, or any runtime consumer.

Historical/superseded: runtime remained legacy `Profile.small_group` based until later consumer and field-retirement slices were designed and implemented. Staff approval remains owned by the membership approval pages; CS-H.7E approval sync behavior was transition-only and later retired with `Profile.small_group`.

## 2. Historical Profile Risk

Historical/superseded: `ProfileForm` exposed legacy `small_group` to logged-in users and saved it directly to `Profile.small_group`.

Risk:
- a normal user can self-edit their legacy group assignment
- then-current `/studies/`, reading progress, `ServiceEvent`, and related behavior still trusted `Profile.small_group`
- a mistaken or self-serving profile edit can immediately change runtime visibility
- this bypasses the `ChurchStructureMembership(status=requested)` review path implemented for signup in CS-H.6B
- this bypasses the existing CS-H.7 staff approval context, conflict handling, and CS-H.7E transition sync rule

CS-H.6C should close this normal-user self-assignment gap without removing the legacy field from staff/admin support paths prematurely.

## 3. Historical CS-H.6D Normal User Profile Behavior

After CS-H.6D, normal logged-in users could:
- show username read-only as today
- keep email editable as today
- keep preferred language editable as today
- historical/superseded: show then-current `Profile.small_group` as read-only context
- expose an optional requested unit selector for group/unit change requests
- create or update a pending `ChurchStructureMembership(status=requested)` when a requested unit is submitted
- not update `Profile.small_group` at request time while that field still existed
- not approve automatically
- hand off review to the existing CS-H.7 staff membership request list/detail/approve/reject flow

Current profile group context should come from active primary `ChurchStructureMembership`, not a legacy profile group field.

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

## 6. Active Primary and Historical Legacy Conflict Handling

If the user already has a current active primary `ChurchStructureMembership`:
- normal Profile request capture may still create/update a pending request
- it must not end the active primary membership
- it must not create a new active primary membership
- CS-H.7 approval should continue to block or require staff resolution for active-primary conflicts

Historical/superseded: if the user already had `Profile.small_group` during the bridge period:
- Profile should show it as then-current group context
- requested unit submission must not change it
- staff detail should continue to show then-current `Profile.small_group`
- CS-H.7E alone decides whether approval syncs `Profile.small_group` after staff approval

Historical/superseded: if the requested unit mapped to no active legacy `SmallGroup`, multiple active legacy groups, or an inactive legacy group:
- request capture should still be allowed if the unit is requestable
- approval may activate membership but CS-H.7E no-sync rules continue to apply

## 7. Staff and Superuser Behavior

Do not break staff support flow without an explicit staff-admin plan.

Historical/superseded CS-H.6C boundary:
- normal user Profile should stop directly editing `Profile.small_group`
- staff/superuser support surfaces could continue to edit `Profile.small_group` where they already could, including Django Admin or staff user-support flows
- any staff direct edit was understood as legacy runtime support, not membership approval
- CS-H.7 pages remain the official membership request approval path

If a future staff profile-edit UI shares the same profile form concepts, implementation should keep normal-user request capture separate from staff-capable membership support surfaces.

## 8. User-Facing Messaging

Profile copy should make clear:
- current group is shown for reference
- selecting a requested unit sends a request to staff
- the request does not immediately change group access
- staff approval is required
- notes, if added, must be brief and non-sensitive

Avoid promising approval, access, transfer timing, or visibility changes.

## 9. Transition-Era Tests

CS-H.6D transition-era tests covered or planned:
- normal profile page shows then-current `Profile.small_group` read-only
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
- historical/superseded: CS-H.7E sync behavior changes
- historical/superseded: consumer migration from `Profile.small_group` to `ChurchStructureMembership`
- audience selection or filtering
- Community Activities
- `/studies/`, reading progress, `ServiceEvent`, or My Serving changes
- broad roadmap rewrites

## 11. Recommended Sequence

Recommended next sequence:
- CS-H.6C: profile group-change request capture planning. Completed by this document.
- CS-H.6D: implement normal-user Profile request capture only, with focused tests. Completed.
- CS-H.6D.1: rendered-page/manual QA and docs closure for normal-user Profile request capture. Completed.
- CS-H.7 approval flow owns staff review and approve/reject behavior.
- historical/superseded: staff legacy `Profile.small_group` edit-form decisions, CS-H.7E transition sync, and consumer migration from `Profile.small_group` were bridge-period concerns later retired by field and consumer migration slices.

Do not bundle profile request capture with approval rewrites, consumer migration, audience filtering, or Community Activities.

## 12. CS-H.6D.1 QA Closure

CS-H.6D.1 verified the rendered Profile request flow with local QA data.

Verified:
- historical/superseded: normal Profile showed then-current `Profile.small_group` as read-only context
- normal Profile no longer renders an editable `small_group` field
- email and preferred language still save
- tampered `small_group` POST data does not update `Profile.small_group`
- saving with no `requested_unit` creates no membership request
- active requestable small-group/fellowship units create or update one pending `ChurchStructureMembership`
- inactive and non-requestable units are rejected by normal form validation
- profile-created requests appear in the existing CS-H.7 staff membership request list and detail pages
- requested profile changes do not grant `/studies/`, reading, `ServiceEvent`, My Serving, permission, serving assignment, audience, or Community Activities access

No signup behavior, models, migrations, approval ownership, consumer migration, audience filtering, or Community Activities behavior changed in CS-H.6D.1.
