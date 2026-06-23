# Church Structure Membership Approval Implementation Plan

## 1. Purpose

CS-H.7A plans future implementation for staff/admin approval of requested `ChurchStructureMembership` records. It follows CS-H.6 signup requested-unit design and CS-H.7 approval workflow design.

This is docs-only. It does not change code, models, migrations, views, forms, templates, URLs, capabilities, signup behavior, `Profile.small_group`, or any runtime consumer.

Historical/superseded for this CS-H.7 planning slice: runtime still used `MinistryContext`, `District`, `SmallGroup`, and `Profile.small_group`, and no runtime consumer used `ChurchStructureMembership`. Current approved migrated consumers use active primary `ChurchStructureMembership`, `Profile.small_group` was removed, and remaining legacy object rows/mappings are bridge/admin/diagnostic/setup/table-retirement context.

## 2. Implementation Slices

Recommended small phases:
- CS-H.7B: capability constant/check implementation. Completed.
- CS-H.7C: staff-only pending requested memberships list. Completed.
- CS-H.7D: request detail with approve/reject actions. Completed.
- CS-H.7E: `Profile.small_group` sync behavior for approved mapped small-group memberships. Completed.
- CS-H.7F: browser QA and docs closure. Completed.

Each slice should preserve current runtime behavior. Do not switch `/studies/`, reading progress, `ServiceEvent`, My Serving, or any other consumer to membership in these slices.

## 3. Recommended First Implementation Slice

Recommended first code slice: CS-H.7B plus a narrow CS-H.7C.

That means:
- add or plan `CAP_MANAGE_CHURCH_MEMBERSHIPS`
- wire the staff/superuser capability check using the existing project pattern
- add a staff-only pending requested memberships list
- do not include approve/reject actions yet
- do not sync `Profile.small_group`
- do not change signup behavior

Reasoning: the pending list lets staff inspect future request data and validates permissions/query shape without introducing write actions. Approve/reject should wait until the list, authorization, and display context are proven.

CS-H.7B/C implementation status:
- `CAP_MANAGE_CHURCH_MEMBERSHIPS` exists in the project capability system.
- Staff/superuser users receive the capability through the existing override pattern.
- Pastor/elder role assignments receive the capability through the existing role capability map.
- Membership records themselves do not grant this capability.
- A read-only staff/capability-gated pending request list exists.
- The list shows only `status=requested` memberships.
- No approve, reject, cancel, needs-clarification, signup, `Profile.small_group` sync, or runtime consumer migration behavior was added.

CS-H.7D implementation status:
- A capability-gated request detail page exists for `status=requested` memberships.
- The pending request list links to request detail.
- POST-only approve updates the same requested record to active membership.
- Approve sets `is_primary=True`, `start_date` when empty, `approved_by`, and `approved_at`.
- Approve preserves `requested_by` and does not sync `Profile.small_group`.
- Approve is blocked if the user already has a current active primary membership.
- POST-only reject changes requested membership to `status=rejected` and clears primary status.
- Reject preserves `requested_by`, notes, and `Profile.small_group`.
- Signup capture, `Profile.small_group` approval sync, and consumer migration remain future work.

CS-H.7E implementation status:
- Approval syncs `Profile.small_group` only when the approved active primary membership unit maps to exactly one active legacy `SmallGroup`.
- Unmapped, multi-mapped, inactive legacy group, rejected, blocked, and non-POST cases do not sync `Profile.small_group`.
- Historical/superseded: runtime still used `Profile.small_group` in this slice; no signup capture, audience filtering, or consumer migration was added by the slice itself. Later slices removed `Profile.small_group` and switched approved consumers separately.

CS-H.7F closure status:
- Browser/manual QA was completed against an isolated local Django server and throwaway SQLite database.
- Normal users could not access staff membership request pages.
- Authorized membership managers could access the pending request list and request detail page.
- The detail page showed user, requested unit, requester, submitted/current legacy group context, request note, active-primary context, transfer/sync warning context, and approve/reject POST actions.
- GET approve remained non-mutating.
- POST approve activated the requested membership and synced `Profile.small_group` only for the exactly-one active mapped legacy `SmallGroup` case.
- POST reject changed the request to rejected and did not sync `Profile.small_group`.
- Targeted automated coverage passed for the broader no-sync cases: unmapped unit, multiple mappings, inactive mapped group, blocked active-primary conflict, GET/non-POST, and reject.
- No signup capture, consumer migration, audience filtering, model change, or migration was added.

## 4. Data Behavior

Future approval behavior:
- update the same `ChurchStructureMembership` from `requested` to `active` for V1
- preserve `requested_by`
- set `approved_by`
- set `approved_at`
- set or confirm `start_date`
- set `is_primary` according to the approved membership rule
- set or confirm `membership_type`, likely `small_group_member` for approved small-group/fellowship membership
- keep notes non-sensitive and operational only
- do not grant visibility

Approval should not create permissions, serving assignments, team membership, or audience scope access. Active membership may become a future source for consumers only after separate migration work.

## 5. Profile.small_group Sync

CS-H.7E is implemented and documented in `docs/CHURCH_STRUCTURE_PROFILE_SMALL_GROUP_SYNC_PLAN.md`.

Implemented transition sync rule:
- if the approved membership is active and primary, and the unit maps to exactly one active legacy `SmallGroup`, sync `Profile.small_group`
- if the approved unit has no legacy mapping, multiple mappings, or an inactive legacy `SmallGroup`, do not sync
- if the user already has a different `Profile.small_group`, staff sees a warning before approval
- do not remove `Profile.small_group`
- do not migrate consumers to membership

CS-H.7E should own this behavior. It should not be bundled into signup capture, consumer migration, or unrelated approval refinements.

## 6. Conflict Handling

Future implementation should handle:
- user already has an active primary membership
- user has multiple pending requests
- requested unit is inactive
- requested unit is not membership-eligible
- requested unit lacks a legacy `SmallGroup` mapping
- transfer from one group to another

Approval should not create duplicate active primary membership. Transfer behavior can be deferred unless the first approval workflow needs it immediately. If deferred, the UI should block approval or require manual staff resolution when an active primary membership already exists.

## 7. Permission and Capability

Proposed capability:
- `CAP_MANAGE_CHURCH_MEMBERSHIPS`

Capability behavior:
- approval list/detail/actions require the explicit capability
- staff/superuser override should follow the existing project pattern
- membership in a unit must not grant approval permission
- requested or active membership must not imply staff access

The initial capability implementation is complete for CS-H.7B/C. Further capability refinement can happen in later implementation slices if staff approval rules become more granular.

## 8. UI and UX

Pending list fields:
- user
- requested unit
- status
- submitted date
- current `Profile.small_group`
- existing active primary membership, if any

Detail page fields:
- user account/profile summary
- requested unit
- request note
- current status
- submitted date
- current `Profile.small_group`
- existing active primary membership
- non-sensitive notes warning

Future actions:
- approve as requested. Basic same-unit approval completed in CS-H.7D.
- approve as different unit
- reject or cancel. Basic rejection completed in CS-H.7D.
- mark needs clarification if supported

CS-H.7B/C intentionally did not include these actions. CS-H.7D adds only minimal approve/reject actions; change-unit approval, cancellation, needs-clarification, and transfer handling remain future.

Bilingual labels should be supported. Mobile should be reasonable, but staff desktop can be V1 priority.

## 9. Tests Required Later

Future tests should cover:
- permission checks for list, detail, and actions
- users without capability cannot view or approve requests
- requested memberships do not grant visibility
- approval updates status without switching consumers
- approval preserves `requested_by`
- approval sets `approved_by` and `approved_at`
- approval syncs `Profile.small_group` only when mapped and sync is enabled
- unmapped approved unit does not force `Profile.small_group`
- inactive legacy `SmallGroup` mapping does not sync
- reject and blocked approval do not sync `Profile.small_group`
- requested membership still grants no visibility before approval
- duplicate active primary membership is blocked or explicitly resolved
- `/studies/` behavior changes only when `Profile.small_group` changes
- reading progress behavior changes only when `Profile.small_group` changes
- `ServiceEvent` behavior changes only when `Profile.small_group` changes
- My Serving behavior does not change unless it already depends on `Profile.small_group`

Do not run tests as part of CS-H.7A because this task is documentation only.

## 10. Non-Goals

CS-H.7A does not include:
- implementation
- model changes
- migrations
- capability implementation
- signup implementation
- views, forms, templates, or URLs
- Django Admin changes
- `Profile.small_group` changes
- consumer migration
- audience filtering
- Community Activities
- Staff Admin Surface rewrite

## 11. Recommended Sequence

Recommended next sequence:
- CS-H.7A: Membership Approval Workflow Implementation Plan. Completed by this document.
- CS-H.7B: capability constant/check implementation. Completed.
- CS-H.7C: staff-only pending requested memberships list. Completed.
- CS-H.7D: request detail and approve/reject actions. Completed.
- CS-H.7E: explicit `Profile.small_group` sync behavior. Completed.
- CS-H.7F: browser QA and docs closure. Completed.
- CS-H.6A: signup request capture implementation planning can proceed before or after CS-H.7B/7C depending on product priority.
- Later: consumer migration from `Profile.small_group` to membership, one consumer at a time.
