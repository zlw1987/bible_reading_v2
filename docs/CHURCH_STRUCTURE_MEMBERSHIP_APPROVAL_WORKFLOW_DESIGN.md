# Church Structure Membership Approval Workflow Design

## 1. Purpose

CS-H.7 designs the future staff/admin workflow for reviewing requested `ChurchStructureMembership` records and approving them into official active membership.

This workflow is needed after the CS-H.6 signup requested-unit flow because signup requests are user-submitted intent, not confirmed belonging. Requested membership cannot become active automatically because membership can affect future visibility, users can choose the wrong unit, and staff may need to resolve "Not sure / New visitor" or broader routing cases.

This is design-only. It does not change code, models, migrations, Django Admin, signup behavior, `Profile.small_group`, forms, views, templates, URLs, or any runtime consumer. CS-H.7A later records the implementation plan without changing code.

## 2. Current State

Current runtime behavior still uses:
- `MinistryContext`
- `District`
- `SmallGroup`
- `Profile.small_group`

`ChurchStructureMembership` exists and may contain requested or active records in future phases, but no runtime consumer uses it yet. Requested memberships may be created by a future signup/request-capture implementation, but that implementation does not exist today.

Historical/superseded: at this design point no approval UI existed and `Profile.small_group` remained the current runtime source for belonging behavior. Current approval/display behavior uses active primary `ChurchStructureMembership`, and `Profile.small_group` was removed in PROFILE-SG-FIELD-RETIRE.1A.

## 3. Approval Principles

Approval principles:
- Staff/admin confirms belonging before official active membership.
- Approval creates or activates official active membership.
- Requested membership grants no visibility.
- Active approved membership may be used by future consumers only after separate consumer migration.
- Membership is not permission.
- Membership is not a serving assignment.

Approval must not infer staff access, role permissions, serving assignments, or team membership. Those remain separate systems.

## 4. Staff Workflow

Future staff/admin flow:
- list pending requested memberships
- filter by requested unit, submitted date, status, and user search
- view request detail
- approve as requested
- change unit before approval
- approve as a different unit
- reject or cancel request
- mark needs clarification if the final status model supports it
- add a non-sensitive operational note
- optionally leave user unassigned or mark as visitor

The request detail should show enough context for a confident decision without turning the page into a full user-history console.

## 5. Approval Data Behavior

There are two reasonable implementation patterns.

Option A: update the same `ChurchStructureMembership` record from `requested` to `active`.
- Pros: simple lifecycle, fewer records, easier V1 implementation.
- Cons: less separation between request event and approved membership event.

Option B: create a separate active membership and mark the request closed.
- Pros: clearer request-vs-approval history, easier to preserve original requested unit if staff approves a different unit.
- Cons: more records, more status handling, more audit/UI surface.

Recommendation for V1:
- update the same record when audit needs are modest
- preserve `requested_by`, `approved_by`, `approved_at`, and non-sensitive `notes`
- keep the original request details visible enough for staff review
- avoid a separate request model unless audit needs grow

If staff changes the unit before approval, the implementation should decide whether to overwrite `unit` with the approved unit or preserve the original request in notes/history. That decision belongs in implementation planning and should be tested.

## 6. Profile.small_group Sync

During the transition, approval may optionally sync `Profile.small_group` when:
- the approved membership is active,
- the approved membership is primary,
- the approved `ChurchStructureUnit` maps to a legacy `SmallGroup`, and
- the implementation explicitly enables sync.

If the approved unit does not map to a legacy `SmallGroup`, do not force `Profile.small_group`. `Profile.small_group` remains the runtime source until consumer migration, so sync behavior must be explicit and tested.

Approval must not remove `Profile.small_group` or switch consumers to membership.

## 7. Duplicate and Conflict Handling

Future approval logic should handle:
- user already has an active primary membership
- user has multiple pending requests
- requested unit is inactive
- requested unit is not membership-eligible
- requested unit was moved or renamed
- transfer from one group to another
- request conflicts with current `Profile.small_group`

Approval should not create duplicate active primary membership. For transfers, the implementation should end the old active primary membership before activating the new primary membership, or otherwise require staff to resolve the conflict before approval.

Multiple pending requests should be deduplicated or shown clearly so staff does not approve competing requests by accident.

## 8. Permissions and Capabilities

Approval requires an explicit capability. Do not infer approval permission from membership in a unit or small group.

Potential capability name:
- `CAP_MANAGE_CHURCH_MEMBERSHIPS`

Staff/superuser override may follow the existing project pattern, but the actual capability implementation is future work. Membership approval permission should remain separate from group belonging, serving assignments, and ordinary user status.

## 9. UX Notes

The staff page should be simple and operational.

Recommended list/detail fields:
- user
- requested unit
- request note
- status
- submitted date
- current `Profile.small_group`
- existing active primary membership, if any
- warning that notes must be non-sensitive

Bilingual labels should be supported. The workflow should be reasonable on mobile, but staff desktop can be the V1 priority.

## 10. Audit and Privacy

Keep an approval trail:
- `approved_by`
- `approved_at`
- request/approval status
- non-sensitive operational notes

Notes must not contain counseling, pastoral, medical, financial, legal, sensitive family, or private contact details. Membership history should be visible only to authorized staff.

## 11. Runtime and Visibility Boundary

The approval workflow does not itself switch `/studies/`, reading progress, `ServiceEvent`, My Serving, or any other consumer to membership.

Requested membership never grants visibility. Approved active membership may become useful for future consumers only after separate design, implementation, and testing.

## 12. Risks

Known risks:
- wrong approval
- duplicate active primary membership
- drift with `Profile.small_group`
- sensitive notes
- staff confusion
- inactive or moved units
- accidentally treating membership as permission
- approving a request into an operational or non-membership unit

Mitigation direction:
- require explicit approval capability
- show current `Profile.small_group` and active membership context
- block or warn on duplicate active primary membership
- keep notes operational only
- validate requestable/approvable unit eligibility
- keep consumer migration separate

## 13. Non-Goals

CS-H.7 does not include:
- implementation
- model changes
- migrations
- signup code
- admin UI
- Django Admin changes
- forms, views, templates, or URLs
- consumer migration
- audience filtering
- Community Activities
- Staff Admin Surface expansion
- `Profile.small_group` changes

## 14. Recommended Next Phases

Recommended sequence:
- CS-H.7: Admin Approval Workflow Design Doc. Completed by this document.
- CS-H.7A: Membership Approval Workflow Implementation Plan. Completed.
- CS-H.6A: signup request capture implementation planning.
- Later: implement requested-unit capture.
- Later: implement approval workflow.
- Later: transition sync with `Profile.small_group` if selected.
- Later: migrate selected consumers from `Profile.small_group` to membership, one at a time.

Do not combine approval workflow implementation with signup capture and consumer migration in one step.
