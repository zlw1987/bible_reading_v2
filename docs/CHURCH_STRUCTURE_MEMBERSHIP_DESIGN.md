# Church Structure Membership Design

## 1. Purpose

`ChurchStructureUnit` now represents the flexible church structure tree. It has been seeded and mapped from current `MinistryContext`, `District`, and `SmallGroup` data, but it is still mirror/mapped structure only.

Membership needs a separate design because user belonging affects Bible Study visibility, reading group progress, future audience eligibility, and signup/onboarding. A structure tree answers "what units exist"; membership answers "which user belongs where, when, and with what approval status."

The goal of CS-H.4 is to design membership without breaking the validated pilot baseline. CS-H.5A later added the model-only `ChurchStructureMembership` foundation. CS-H.5B hardens helper/query behavior and validation. CS-H.5C adds an explicit dry-run/apply backfill command from `Profile.small_group`. CS-H.5D records user-attested GoDaddy production/staging backfill verification without exact command-output counts. CS-H.5E improves Django Admin clarity for legacy current-runtime structure models versus future structure/membership foundation models. These steps do not authorize signup changes, custom staff admin UI, audience selection, filtering, consumer migration, or a runtime source-of-truth switch.

## 2. Current State

Current runtime belonging:
- `Profile.small_group` stores a user's current primary small group.
- `/studies/` visibility uses `Profile.small_group`.
- Reading group progress uses `Profile.small_group` and `SmallGroup`.
- `BibleStudySeries` scope behavior still uses the legacy schedule scope fields.
- `ServiceEvent` scope behavior still uses its current `scope_type`, `district`, and `small_group` fields.

Current structure state:
- `ChurchStructureUnit` exists.
- Current `MinistryContext`, `District`, and `SmallGroup` data has been seeded/mapped into `ChurchStructureUnit`.
- `ChurchStructureUnit` is not the runtime source of truth.
- CS-H.5A adds the model-only `ChurchStructureMembership` table.
- CS-H.5C adds the explicit `backfill_church_structure_memberships` command.
- CS-H.5D records production/staging backfill verification as user-attested; exact command-output counts were not recorded.
- CS-H.5E improves Django Admin clarity so legacy models and future foundation models are labeled more clearly.
- No runtime consumer uses membership yet.
- There is no requested-unit signup/onboarding flow today.
- There is no admin approval workflow today.

## 3. Long-Term Target

Long-term source of truth:
- `ChurchStructureUnit` becomes the canonical church structure source.
- `ChurchStructureMembership` becomes the canonical user belonging / membership source.

Transition target:
- `Profile.small_group` becomes a transitional compatibility field, cache, or eventually deprecated field.
- The transition must be staged and tested before any consumer switches away from `Profile.small_group`.

Boundary rules:
- Membership is about belonging, not permissions.
- `ChurchRoleAssignment` and capability helpers remain the permissions source.
- `TeamAssignment`, `TeamMembership`, and `TeamAssignmentMember` remain serving assignment sources.
- Membership must not automatically grant staff access.
- Membership must not automatically assign serving roles.

## 4. Proposed Model: ChurchStructureMembership

Model concept, implemented model-only in CS-H.5A:

`ChurchStructureMembership`
- `user` FK
- `unit` FK to `ChurchStructureUnit`
- `membership_type`
- `status`
- `is_primary`
- `start_date`
- `end_date` nullable
- `approved_by` nullable FK to user
- `approved_at` nullable datetime
- `requested_by` nullable FK to user, if needed
- `created_at`
- `updated_at`
- `notes` optional, non-sensitive

Suggested `status` values:
- `requested`
- `active`
- `ended`
- `rejected`
- `cancelled`

`withdrawn` may be useful later if normal users can cancel pending requests themselves. V1 can use `cancelled` for staff/admin cancellation and defer `withdrawn` unless the signup/request workflow needs that distinction.

Suggested `membership_type` values:
- `member`
- `visitor`
- `regular_attendee`
- `small_group_member`

Avoid broad or permission-like values in V1. In particular, `coworker` should not be added casually because it can be confused with permissions, church roles, or serving assignments. If coworker-style belonging is needed later, define it with explicit boundaries and tests.

V1 should keep `membership_type` narrow. The first useful target is approved active primary small-group/fellowship membership, not a full HR/personnel taxonomy.

CS-H.5A implementation note:
- The model exists in `accounts`.
- It has admin registration for inspection only.
- It does not change signup/onboarding.
- It does not create requested-unit UI.
- It does not backfill from `Profile.small_group`.
- It does not change `/studies/`, reading progress, `BibleStudySeries`, `ServiceEvent`, or My Serving behavior.
- Requested membership does not grant visibility.

CS-H.5B hardening note:
- Query helpers exist for active membership and current primary membership.
- Helpers count only `status=active` records within their start/end date window.
- Requested, rejected, cancelled, and ended memberships do not count as active.
- Duplicate active primary membership remains application-validated, not DB-enforced.
- No runtime consumer uses these helpers yet.

CS-H.5C backfill command note:
- `python manage.py backfill_church_structure_memberships` defaults to dry-run.
- `--apply` creates active primary `small_group_member` memberships from `Profile.small_group` when the related `SmallGroup.church_structure_unit` mapping exists.
- The command is idempotent and skips users with no profile group, unmapped groups, or an existing active primary membership.
- The command does not modify `Profile.small_group`, create requested memberships, infer permissions, infer serving assignments, or switch runtime behavior.

CS-H.5D verification note:
- GoDaddy production/staging dry-run/apply/second dry-run was completed by user confirmation.
- Exact numeric command-output counts were not provided or recorded.
- No unresolved warnings, errors, or data QA item was reported.
- Runtime still uses `Profile.small_group`; membership is not yet the source of truth.

CS-H.5E admin clarity note:
- Legacy `SmallGroup`, `District`, and `MinistryContext` remain editable because they still drive current runtime behavior.
- Django Admin now labels them as current-runtime legacy/bridge models and shows mapping status to `ChurchStructureUnit`.
- `ChurchStructureUnit` and `ChurchStructureMembership` admin pages are labeled as future foundation/mirror data.
- Custom staff admin UI remains future work.

## 5. Requested Assignment Model Options

### Option A: Store Requested Unit on Profile

Possible fields:
- `Profile.requested_unit`
- `Profile.requested_membership_note`
- `Profile.requested_membership_status`

Pros:
- Simple to query.
- Low model count.
- Easy to show on user admin pages.

Cons:
- Weak history.
- Awkward rejection and re-request handling.
- Mixes transient onboarding state into long-lived profile.
- Harder to audit who approved or changed the request.

### Option B: Separate ChurchStructureMembershipRequest

Possible model:

`ChurchStructureMembershipRequest`
- `user`
- `requested_unit`
- `status`
- `note`
- `reviewed_by`
- `reviewed_at`
- `result_membership`
- timestamps

Pros:
- Clean separation between requests and approved membership.
- Better audit history.
- Easier to support repeated requests, rejected requests, and clarification workflows.

Cons:
- More model surface.
- More admin/UI work.
- Requires careful synchronization when a request is approved into membership.

### Option C: Use ChurchStructureMembership With status=requested

Use one model for both pending requests and active/ended membership records.

Pros:
- One lifecycle table.
- Simple transition from `requested` to `active`.
- Approval fields can live on the same record.
- Easier to show full membership/request history in one place.

Cons:
- Requires clear validation so requested records do not count as active visibility.
- `ChurchStructureMembership` carries both proposed and official states, so query helpers must be disciplined.
- Rejection/cancellation history lives beside active membership and needs clean admin filters.

Recommendation for this project:
- Prefer Option C for V1 unless audit needs become more complex before implementation.
- Use `ChurchStructureMembership.status=requested` for signup/onboarding requests.
- Treat only `status=active` records as membership for visibility and eligibility.
- Keep request notes non-sensitive and operational.
- Revisit a separate request model only if staff needs richer request history, multi-step review, or external communication tracking.

## 6. Primary Membership Rules

Rules:
- A user can have multiple memberships over time.
- A user should have at most one active primary membership at a time.
- V1 should support one active primary small-group/fellowship membership.
- Future versions may allow multiple active non-primary memberships.
- Primary membership is what eventually replaces `Profile.small_group` for visibility.
- Do not switch visibility in the model-only phase.

Enforcement considerations:
- Application validation should prevent duplicate active primary memberships.
- A database constraint may be useful later, but it must be designed carefully around status, date range, and partial-index support.
- Avoid complicated database constraints until the implementation phase has concrete tests.
- Before any visibility consumer trusts membership, add tests for duplicate prevention, date windows, status filtering, and fallback behavior.

## 7. Date / History Rules

Active membership means:
- `status=active`
- `start_date <= today`
- `end_date` is empty or in the future

Ended membership:
- keeps `status=ended`
- keeps historical `start_date` and `end_date`
- should not be deleted casually

Transfers:
- end the old active primary membership
- create a new active primary membership
- keep both records for history
- optionally sync `Profile.small_group` during the transition if the new unit maps to a `SmallGroup`

Notes:
- Must be operational only.
- Must not contain counseling, pastoral, medical, financial, legal, family, or private sensitive information.

## 8. Signup / Onboarding Flow

Future compromise flow:
- User signs up with optional requested unit/small group and optional note.
- Requested unit is not final membership.
- User starts in a pending/unassigned state.
- Staff/admin reviews the request.
- Staff can approve, modify the requested unit before approval, reject, cancel, or mark needs clarification.
- Approval creates or activates membership.
- During transition, approval may update `Profile.small_group` when the approved unit maps to a `SmallGroup`.
- Normal users cannot self-assign final membership.

Visibility rule:
- Requested membership must not grant `/studies/`, reading progress, audience eligibility, or event filtering access.
- Only approved active membership may eventually drive those behaviors.

## 9. Admin Approval Workflow

Future staff workflow:
- Pending membership requests list.
- Filter by requested unit, date, and status.
- View request details.
- Approve into official unit.
- Change unit before approval.
- Reject, cancel, or mark needs clarification.
- Add optional non-sensitive operational note.
- Show bilingual UI labels when implemented.
- Require an explicit permission/capability.

Do not implement UI in CS-H.4.

Approval permission should be separate from ordinary membership. Being a member of a group should not let a user approve membership requests.

## 10. Transition With Profile.small_group

Recommended phases:
- Phase M.1: CS-H.4 design only.
- Phase M.2: add `ChurchStructureMembership` model only, no behavior change.
- Phase M.3: backfill active primary membership from `Profile.small_group`.
- Phase M.4: signup requested-unit flow stores requested membership/request, not active membership.
- Phase M.5: admin approval updates membership and syncs `Profile.small_group`.
- Phase M.6: selected consumers may read membership with fallback to `Profile.small_group`.
- Phase M.7: `Profile.small_group` becomes cache/compatibility or is deprecated after safe migration.

Important:
- Do not switch `/studies/` immediately.
- Do not remove `Profile.small_group` early.
- Do not make membership the runtime source of truth until tests and rollback planning exist.

## 11. Backfill Strategy

CS-H.5C implementation status:
- `backfill_church_structure_memberships` is an explicit management command, not an automatic migration.
- For each user with `Profile.small_group`, it finds the mapped `ChurchStructureUnit` from `SmallGroup.church_structure_unit`.
- In dry-run mode, it reports memberships that would be created without writing data.
- In apply mode, it creates an active primary membership when no active primary membership already exists.
- Users without `Profile.small_group` remain unassigned.
- Users whose small group has no mapped `ChurchStructureUnit` are skipped with a warning.
- The command is idempotent; after apply, a clean dry-run should report zero would-created rows if source data has not changed.
- Do not import sensitive/private data.
- Do not infer permissions or serving roles.

Backfill should report:
- memberships that would be created
- users skipped because they have no `Profile.small_group`
- users skipped because their small group has no mapped `ChurchStructureUnit`
- duplicate or conflicting active primary memberships
- warnings that require staff/admin data review

## 12. Visibility Migration Strategy

Future consumers:
- `/studies/`
- Reading group progress
- future Community Activities eligibility
- future audience scope
- maybe `ServiceEvent` filtering, only if separately designed

Rules:
- Visibility cannot use requested membership.
- Visibility can only use approved active membership.
- Each consumer migration should be explicit and tested.
- During transition, use fallback:
  - active primary membership if available
  - else `Profile.small_group`

Do not migrate all consumers at once. Start with the lowest-risk consumer only after model, backfill, and approval flow behavior are proven.

## 13. Permissions Boundary

Membership is not permission.

Permission sources remain:
- `ChurchRoleAssignment`
- capability helpers
- staff/superuser flags where already used

Serving assignment sources remain:
- `MinistryTeam`
- `TeamMembership`
- `TeamAssignment`
- `TeamAssignmentMember`

V1 must not infer group leader, district leader, coworker, staff, or serving permissions from membership alone.

## 14. Data Privacy / Pastoral Safety

Rules:
- no counseling notes
- no pastoral care notes
- no medical information
- no financial information
- no sensitive family/private information
- no private contact import
- notes should be operational only

When implemented, membership history should be visible only to authorized staff. Normal users should not browse other users' membership history.

## 15. Risks

Known risks:
- visibility leaks
- users self-assigning the wrong group
- duplicate active primary membership
- drift between membership and `Profile.small_group`
- confusing membership with role/permission
- confusing membership with serving assignment
- staff workload
- data cleanup and transfer complexity
- overbuilding HR/ERP behavior
- accidentally trusting requested membership for visibility

Mitigation direction:
- keep runtime behavior unchanged during model-only phases
- require staff/admin approval for final membership
- use explicit status filtering
- add focused tests before consumer migration
- keep notes non-sensitive
- use dry-run/apply backfill
- migrate one consumer at a time

## 16. Non-Goals

CS-H.4 does not include:
- implementation
- models
- migrations
- signup changes
- admin UI
- `ServiceEvent` filtering
- Community Activities
- audience selector
- removal of `Profile.small_group`
- switching `/studies/` visibility
- automatic permission inference
- serving assignment changes
- sensitive data import

## 17. Recommended Next Phases

Recommended sequence:
- CS-H.4: ChurchStructureMembership design doc. Completed by this task.
- CS-H.5A: `ChurchStructureMembership` model-only foundation. Completed.
- CS-H.5B: membership model hardening/tests. Completed.
- CS-H.5C: backfill command design/implementation with dry-run/apply. Completed.
- CS-H.5D: production/staging backfill verification. Completed by user-attested GoDaddy run; exact output counts were not recorded.
- CS-H.5E: Django Admin clarity for legacy structure vs future structure/membership foundation. Completed.
- CS-H.6: signup requested-unit design.
- CS-H.7: admin approval workflow design.
- Later: consumer migration from `Profile.small_group` to membership.

Do not implement membership, signup approval, or consumer migration all at once.

## 18. Open Decisions

Open decisions:
- single membership model with `status=requested` vs separate request model
- exact `membership_type` choices
- whether to enforce one active primary membership at the database level
- whether approved membership immediately syncs `Profile.small_group`
- who can approve membership
- how to handle transfers
- whether users can request only leaf units or broader units
- how to display membership history
- first consumer to migrate from `Profile.small_group`
- whether normal users can view their own membership history
- how much approval audit detail is needed in V1
