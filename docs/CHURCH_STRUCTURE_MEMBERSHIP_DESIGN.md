# Church Structure Membership Design

> **Current-state update:** this CS-H-era membership design predates the completed
> Church Structure migration. `ChurchStructureUnit` is now the canonical local
> structure model, and active primary `ChurchStructureMembership` is the ordinary
> belonging source for approved migrated consumers. ServiceEvent audience rows,
> Bible Study V2 meeting audience rows / `/studies/` / Today / role-worship
> pickers, Prayer, group progress, and Reflection migrated consumer-by-consumer.
> `Profile.small_group`, legacy structure tables, ServiceEvent legacy scope fields,
> Bible Study Series legacy scope fields, the V2 meeting `small_group` mirror, and
> V1 Bible Study schema were removed. Statements below that describe membership as
> future-only or legacy models/fields as current runtime are historical bridge
> context only. My Serving and serving assignments remain explicit-assignment
> driven; membership never implies serving.

## 1. Purpose

`ChurchStructureUnit` represents the flexible church structure tree.
Historical/superseded: during CS-H.4 it had been seeded and mapped from
then-current `MinistryContext`, `District`, and `SmallGroup` data, but was still
mirror/mapped structure only.

Membership needs a separate design because user belonging affects Bible Study visibility, reading group progress, future audience eligibility, and signup/onboarding. A structure tree answers "what units exist"; membership answers "which user belongs where, when, and with what approval status."

The goal of CS-H.4 was to design membership without breaking the validated pilot baseline. CS-H.5A later added the model-only `ChurchStructureMembership` foundation. CS-H.5B hardened helper/query behavior and validation. CS-H.5C added an explicit dry-run/apply backfill command from `Profile.small_group`. CS-H.5D records user-attested GoDaddy production/staging backfill verification without exact command-output counts. CS-H.5E was admin clarity for the then-current legacy runtime models versus future structure/membership foundation models; that framing is historical/superseded now that the legacy fields/tables are retired and `ChurchStructureUnit` / `ChurchStructureMembership` are current models for approved migrated consumers. CS-H.6 records the signup requested-unit flow design, CS-H.6A/CS-H.6B add signup request capture planning and implementation, and CS-H.6D adds Profile request capture. CS-H.7 records the admin approval workflow design, and CS-H.7A through CS-H.7E add approval planning, staff request review, approve/reject actions, and historical narrow `Profile.small_group` approval sync. CS-H.8 records the integration checkpoint, CS-H.9 records membership request UX hardening, and CS-H.10 records the CMS hardening checkpoint. These historical steps did not by themselves authorize audience selection, filtering, consumer migration, or a runtime source-of-truth switch.

## 2. Historical Current State

Historical/superseded runtime belonging at the CS-H.4 design point:
- `Profile.small_group` stores a user's current primary small group.
- `/studies/` v2 meeting visibility uses active primary `ChurchStructureMembership` after CS-CORE.2C-B; historical `BibleStudySession` visibility was unchanged at that point.
- Reading group progress uses `Profile.small_group` and `SmallGroup`.
- `BibleStudySeries` schedule audience resolution and meeting generation still resolve to legacy `SmallGroup` rows.
- `ServiceEvent` structure-audience rows use membership-core matching when present; zero-row events still use legacy `scope_type`, `district`, and `small_group` fallback.

Historical/superseded structure state at the CS-H.4 design point:
- `ChurchStructureUnit` exists.
- Current `MinistryContext`, `District`, and `SmallGroup` data has been seeded/mapped into `ChurchStructureUnit`.
- `ChurchStructureUnit` is not the runtime source of truth.
- CS-H.5A adds the model-only `ChurchStructureMembership` table.
- CS-H.5C adds the explicit `backfill_church_structure_memberships` command.
- CS-H.5D records production/staging backfill verification as user-attested; exact command-output counts were not recorded.
- CS-H.5E improves Django Admin clarity so legacy models and future foundation models are labeled more clearly.
- CS-H.6 documents the signup requested-unit flow; CS-H.6A/CS-H.6B add signup request capture planning and implementation.
- CS-H.6D adds Profile request capture.
- CS-H.7 documents the admin approval workflow; CS-H.7A through CS-H.7E add approval planning, staff request review, approve/reject actions, and narrow `Profile.small_group` approval sync.
- CS-H.8 integration checkpoint is complete.
- CS-H.9 membership request UX hardening is complete.
- CS-H.10 CMS hardening checkpoint is complete, including deferred/accepted mobile nav polish and the root `AGENTS.md` verification policy.
- Runtime membership use is consumer-specific: ServiceEvent structure-audience rows, Bible Study v2 visibility/pickers, Prayer, group progress, and reflection use their approved membership/audience/snapshot paths.
- Historical/superseded: reading progress, legacy `BibleStudySession`, ServiceEvent zero-row fallback, and other consumers still used legacy models and `Profile.small_group` at this planning point. Current ServiceEvent and Bible Study zero-row cases fail closed, V1 schema is removed, and `Profile.small_group` is removed.

## 3. Long-Term Target

Long-term source of truth:
- `ChurchStructureUnit` is now the canonical local church structure source.
- `ChurchStructureMembership` is the canonical user belonging / membership source for approved migrated consumers.

Historical transition target:
- `Profile.small_group` would become a transitional compatibility field, cache, or eventually deprecated field.
- The transition had to be staged and tested before any consumer switched away from `Profile.small_group`.

Current resolution: `Profile.small_group` was removed after the approved staged
migration/retirement work.

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
- Historical/superseded: no runtime consumer used these helpers yet at CS-H.5B time. Current approved migrated consumers use membership helpers/active primary membership where explicitly switched.

CS-H.5C backfill command note:
- `python manage.py backfill_church_structure_memberships` defaults to dry-run.
- `--apply` creates active primary `small_group_member` memberships from `Profile.small_group` when the related `SmallGroup.church_structure_unit` mapping exists.
- The command is idempotent and skips users with no profile group, unmapped groups, or an existing active primary membership.
- The command does not modify `Profile.small_group`, create requested memberships, infer permissions, infer serving assignments, or switch runtime behavior.

CS-H.5D verification note:
- GoDaddy production/staging dry-run/apply/second dry-run was completed by user confirmation.
- Exact numeric command-output counts were not provided or recorded.
- No unresolved warnings, errors, or data QA item was reported.
- Historical note: this was true before the consumer switches. Later slices moved the approved consumers to membership/audience/snapshot paths, retired the ServiceEvent and Bible Study zero-row fallbacks, removed V1 schema, and removed `Profile.small_group`.

CS-H.5E admin clarity note (historical/superseded):
- Legacy `SmallGroup`, `District`, and `MinistryContext` remained editable at that bridge point because they still drove then-current runtime behavior.
- Django Admin labeled them as current-runtime legacy/bridge models and showed mapping status to `ChurchStructureUnit`.
- `ChurchStructureUnit` and `ChurchStructureMembership` admin pages were labeled as future foundation/mirror data at that time.
- Current state supersedes this: legacy structure models/tables are removed, `ChurchStructureUnit` is canonical local structure, and `ChurchStructureMembership` is current belonging for approved migrated consumers.
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
- Historical/superseded: primary membership was intended to eventually replace `Profile.small_group` for visibility; the approved migrated consumers now use membership, and `Profile.small_group` is removed.
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
- historical/superseded: optionally sync `Profile.small_group` during the transition if the new unit maps to a `SmallGroup`

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
- Historical/superseded: during transition, approval could update `Profile.small_group` when the approved unit mapped to a `SmallGroup`; this sync was later retired and the field removed.
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

CS-H.7B/C/D implemented the first staff request review UI and approve/reject actions. Broader staff admin expansion, richer request routing, needs-clarification handling, and history views remain future work.

Approval permission should be separate from ordinary membership. Being a member of a group should not let a user approve membership requests.

## 10. Transition With Profile.small_group

Recommended phases:
- Phase M.1: CS-H.4 design only.
- Phase M.2: add `ChurchStructureMembership` model only, no behavior change.
- Phase M.3: backfill active primary membership from `Profile.small_group`.
- Phase M.4: signup/Profile requested-unit flow stores requested membership/request, not active membership. Completed.
- Phase M.5: historical admin approval sync to `Profile.small_group` for the narrow exactly-one active mapped legacy `SmallGroup` case. Completed at the time, later retired.
- Phase M.6: selected consumers may read membership with carefully tested fallback or fail-closed behavior. Partially complete: ServiceEvent structure-audience rows switched in CS-CORE.2B-A, and Bible Study v2 meeting visibility switched in CS-CORE.2C-B.
- Phase M.7: `Profile.small_group` becomes cache/compatibility or is deprecated after safe migration. Superseded by later removal.

Important:
- Historical note: `/studies/` v2 meeting visibility switched in CS-CORE.2C-B; later approved consumers switched in separate slices.
- Historical rule: do not remove `Profile.small_group` early. It was later removed after approved retirement work.
- Historical rule: do not make membership the runtime source of truth until tests and rollback planning exist. Current migrated consumers have that explicit approval/history.

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

Future or partially migrated consumers:
- `/studies/` v2 meeting visibility (switched in CS-CORE.2C-B)
- Reading group progress
- future Community Activities eligibility
- future audience scope
- maybe `ServiceEvent` filtering, only if separately designed

Rules:
- Visibility cannot use requested membership.
- Visibility can only use approved active membership.
- Each consumer migration should be explicit and tested.
- During transition, each consumer must define its own rollback/fallback behavior. CS-CORE.2C-B makes v2 meeting visibility fail closed when the active-primary membership or mapped small-group unit is not valid, instead of falling back to `Profile.small_group`.

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
- CS-H.6: signup requested-unit design. Completed.
- CS-H.7: admin approval workflow design. Completed.
- CS-H.6A/CS-H.6B: signup request capture planning and implementation. Completed.
- CS-H.6D: Profile request capture. Completed.
- CS-H.7A: membership approval workflow implementation plan. Completed.
- CS-H.7B/C: membership approval capability plus pending request list. Completed.
- CS-H.7D: membership request detail plus approve/reject actions. Completed.
- CS-H.7E: historical narrow `Profile.small_group` approval sync. Completed at that time, later retired.
- CS-H.8: integrated membership request flow checkpoint. Completed.
- CS-H.9: membership request UX hardening. Completed.
- CS-H.10: CMS hardening checkpoint. Completed.
- Historical/superseded later step: consumer migration from `Profile.small_group` to membership. Approved migrated consumers have since moved, and `Profile.small_group` was removed.

Do not implement new audience filtering or additional consumer migration without a separate plan. Historical/superseded: this section previously warned not to migrate reading progress, legacy `BibleStudySession`, ServiceEvent legacy fallback, My Serving, or other consumers from `Profile.small_group` until explicitly authorized. Later approved slices migrated/retired those applicable consumers; My Serving remains assignment-based and is not inferred from membership.

## 18. Historical / Resolved Decisions

Historical/resolved decisions:
- `membership_type` choices were implemented for the membership model.
- Active-primary enforcement and helper behavior were implemented in the approved membership slices.
- Approved membership no longer syncs `Profile.small_group`; the sync was retired and the field removed.
- Approval capability and staff/superuser override rules were implemented in the membership request workflow.
- Transfer handling remains a product/workflow topic, not a reason to treat `Profile.small_group` as current.
- Request routing uses the approved requested-unit flow unless a future product slice expands it.
- Membership history display remains a product UX topic.
- The first consumer migrations from `Profile.small_group` have already happened; current docs should follow the per-consumer current-state sections.
- Normal-user membership-history visibility and approval audit detail remain UX/audit follow-ups, not blockers for the current migration truth.
