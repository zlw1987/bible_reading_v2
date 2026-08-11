# Structure Membership Primary Integrity Plan

Status: canonical plan and implementation record for
`STRUCTURE-MEMBERSHIP-PRIMARY-INTEGRITY-HARDENING.1A` and
`STRUCTURE-MEMBERSHIP-PRIMARY-INTEGRITY-HARDENING.1A-FU1`.

Date: 2026-08-11.

Source finding: `AUDIT-DATA-001` - Active/current primary membership integrity
and concurrency hardening.

This file is the continuation source for Church Structure primary-membership
integrity. It supersedes conversation memory for this slice.

## Exact Invariant

`ChurchStructureMembership` is belonging only. It is not serving, staff
authority, leadership, permission/capability, ministry-team membership,
audience-management authority, or My Serving assignment state.

The runtime read-time current-primary definition is date-window aware:

- `status == active`;
- `is_primary == True`;
- `start_date <= target_date`;
- `end_date` is null or `end_date >= target_date`;
- exactly one row for the user must match.

If zero rows match, the user has no current primary belonging for migrated
consumers. If more than one row matches, selectors fail closed and return no
unit rather than choosing one.

The current application write-time policy is stricter than the read-time
current definition: normal validated writes allow at most one
`status=active, is_primary=True` row per user, regardless of date window. This
means a future-dated active primary row is legal by itself and is ignored by
read-time current selectors until its `start_date`, but it still blocks approval
or creation of another active primary row under today's lifecycle policy.

`status=active` alone is not sufficient to mean current. A future active row
and an active row whose end date is before the target date are not current.
Application validation also rejects active rows with a missing `start_date` and
active rows whose `end_date` is already in the past; historical rows should use
`status=ended`.

`is_primary=True` is meaningful on historical `ended` rows as retained history.
It is rejected on `rejected` and `cancelled` rows. Requested rows do not count
for visibility, even if drifted data has `is_primary=True`.

## Legal Lifecycle Examples

- One current active primary row:
  `status=active`, `is_primary=True`, `start_date=today`, `end_date=null`.
- One future active primary row by itself:
  `status=active`, `is_primary=True`, `start_date=tomorrow`; it is not current
  today, but it is an active-primary write conflict.
- Ended historical primary plus current primary:
  old row `status=ended`, `is_primary=True`, ended before today; new row
  `status=active`, `is_primary=True`, current today.
- Active non-primary row plus active primary row:
  secondary active membership can coexist when `is_primary=False`.
- Requested pending row plus current active primary:
  allowed as a request/change workflow; requested rows grant no visibility and
  approval remains blocked until staff resolves the active-primary conflict.

## Illegal Or Conflicting Examples

- Two rows for the same user with `status=active` and `is_primary=True`, even
  when one is future-dated. Model validation rejects this; normal product
  approval/add paths now fail closed cleanly.
- Two current active primary rows for the same user. Selectors fail closed, and
  readiness reports a blocker.
- `status=active` with no `start_date`.
- `status=active` with an `end_date` in the past.
- `status=rejected` or `status=cancelled` with `is_primary=True`.
- Requested membership used for visibility or serving. Requested rows are
  pending belonging requests only.

## Mutation-Path Inventory

| Path | Function / form | Authorization | Transaction? | Row locking? | Model validation? | Can create primary? | Can change currentness? | Conflict handling | Notes |
|---|---|---|---|---|---|---|---|---|---|
| Signup request capture | `SignUpForm.save()` -> `create_or_update_signup_membership_request()` | New self-signup | No explicit membership transaction | No | Yes, via model `save()` | No | No; creates/updates `requested` only | Updates oldest pending request; no active conflict check needed | Requested row grants no visibility. |
| Profile request capture | `ProfileForm.save()` -> `create_or_update_signup_membership_request()` | Logged-in self profile | No explicit membership transaction | No | Yes, via model `save()` | No | No; creates/updates `requested` only | Existing active primary may coexist with pending request | Approval is the staff resolution point. |
| Staff request approval | `staff_membership_request_approve()` -> `approve_membership_request()` | `can_manage_church_memberships` | Yes, hardened in 1A/FU1 | Locks user row and existing membership rows with `select_for_update()` where backend supports it; refetches target row after lock | Yes | Yes | Yes; requested row becomes active primary | Blocks if any other active primary exists or target is no longer requested; row stays pending/processed | 1A fixed future-active-primary conflicts; FU1 preserves processed rows when a stale object is used. |
| Delegated My Units approval | `approve_my_unit_member_request()` -> `approve_membership_request()` | `can_manage_unit_members` for the requested small-group unit | Yes, through shared helper | Same shared lock scope and post-lock target refetch | Yes | Yes | Yes | Same as staff approval | Belonging only; no serving/coworker/role rows. |
| Staff request rejection | `staff_membership_request_reject()` -> `reject_membership_request()` | `can_manage_church_memberships` | Yes, hardened in FU1 | Locks user row and existing membership rows with `select_for_update()` where backend supports it; refetches target row after lock | Yes | No | Yes; requested row becomes rejected | No-ops if target is no longer requested | FU1 prevents stale reject objects from overwriting already approved/rejected requests. |
| Delegated My Units rejection | `reject_my_unit_member_request()` -> `reject_membership_request()` | `can_manage_unit_members` for the requested small-group unit | Yes, through shared helper | Same shared lock scope and post-lock target refetch | Yes | No | Yes | Same as staff rejection | Belonging only; no serving/coworker/role rows. |
| Direct staff membership add | `add_structure_membership()` -> `StructureMembershipAddForm.save()` | `can_manage_church_memberships` | Yes | 1A locks user row and existing membership rows | Yes | Optional | Yes | If primary is checked, existing active primaries are unset before create | This is an intentional manual staff replacement path, unlike request approval. |
| Delegated My Units member add | `add_my_unit_member()` -> `MyUnitMemberAddForm.save()` | `can_manage_unit_members` for small-group unit | Yes | 1A locks user row and existing membership rows | Yes | Yes | Yes | Candidate/clean and 1A in-transaction recheck block current/future active membership or pending request | Creates only active primary belonging. |
| Staff end membership | `end_structure_membership()` | `can_manage_church_memberships` | Yes, hardened in 1A/FU1 | Locks user row and existing membership rows; FU1 refetches target row after lock | Yes | No | Yes; row becomes ended and not primary | No replacement is created | Retains row and user. |
| Delegated My Units end | `end_my_unit_member()` | `can_manage_unit_members` for membership unit | Yes, hardened in 1A/FU1 | Locks user row and existing membership rows; FU1 refetches target row and rechecks authorization/current-active state after lock | Yes | No | Yes | Requires latest row to be currently active before ending | Retains row and user. |
| Staff set primary | `set_primary_structure_membership()` | `can_manage_church_memberships` | Yes | 1A locks user row and existing membership rows, then refreshes/rechecks row state | Yes | Promotes existing active row | Yes | Unsets other active primaries, then saves target as primary | Intentional manual replacement path; FU1 reviewed and retained the post-lock recheck. |
| Django Admin direct edit | `ChurchStructureMembershipAdmin` / default admin model form | Django admin permissions | Admin-managed request transaction only; no custom atomic block | No custom lock | Yes via model validation and model `save()` | Yes | Yes | Model rejects duplicate active primary | Admin is exceptional support; no 1A custom admin workflow added. |
| Management/import/seed paths | Current commands by inventory | Operator/developer only | N/A | N/A | N/A | No current command creates memberships | N/A | No active current command found | Retired backfill references are historical. |
| Tests/utilities/bulk writes | `bulk_create`, `bulk_update`, raw SQL, shell | Developer/operator exceptional path | Depends on caller | Depends on caller | Bypasses model validation for bulk/raw writes | Yes | Yes | Drift is detected by selectors/readiness, not prevented | Used intentionally in tests to prove fail-closed behavior. |

## Defense Layers

- UI/form validation: signup/profile only create requested rows; staff/direct
  forms block duplicate unit membership and My Units add blocks users with
  current/future active membership or pending requests.
- Model validation: active membership requires `start_date`, rejects past
  active end dates, rejects rejected/cancelled primaries, rejects requested or
  active memberships on inactive units, and rejects a second active primary
  row for the same user.
- Transactional mutation logic: 1A added per-user membership scope locking and
  in-transaction rechecks to normal product paths that create, promote, end, or
  replace active primary state. FU1 finished the lock-after-read pattern for
  request rejection and end paths by refetching target membership rows after
  acquiring the mutation-scope lock before deciding or writing.
- Selector fail-closed behavior: `accounts.structure_selectors` returns no unit
  when multiple current active primary rows exist.
- Readiness/drift detection: `audit_trial_setup_readiness` keeps the
  date-window-aware current-primary count for visibility/no-current warnings and
  separately detects users with more than one `status=active, is_primary=True`
  row as blockers, so current+future and future+future write-policy drift is
  visible before a future row becomes current.
- Optional future DB enforcement: still deferred; see below.

## Concurrency Behavior

The logical application invariant is: normal product writes must not leave more
than one active primary membership row for a user, and runtime selectors must
fail closed if drift still occurs.

1A wraps normal primary-affecting product writes in `transaction.atomic()` and
locks the membership owner user row plus existing membership rows through
`select_for_update()`. On the current SQLite backend, Django's
`select_for_update()` does not provide PostgreSQL-style row locks, so this slice
does not claim a proven row-level concurrency guarantee for SQLite. SQLite's
coarse write behavior may still serialize some writes in practice, but tests in
this repository should not be treated as proof of production row-lock behavior.

On a future row-locking backend, the user-row lock is the important
serialization point, including the "no existing membership rows yet" case where
locking only existing membership rows would not lock a gap. Backend-independent
protections that remain useful are shared conflict checks, model validation,
fail-closed selectors, and read-only readiness detection.

## Existing Readiness And Drift Detection

`accounts.trial_setup_readiness._active_primary_membership_counts_by_user()`
uses the same current date-window as selectors: active status, primary flag,
`start_date <= target_date`, and null-or-future `end_date`. The Church
Structure readiness section uses this for current-membership info and
`active_users_without_active_primary_membership` warnings for non-staff active
users.

FU1 added a separate write-time active-primary counter for the existing
`users_multiple_active_primary_membership` blocker. It counts all
`status=active, is_primary=True` rows for a user, regardless of date window,
while excluding ended, rejected, cancelled, and requested rows. One future
active primary by itself is not a multiple-primary blocker; current+future and
future+future active primaries are blockers. No duplicate read-only command was
added.

## Database-Constraint Feasibility

| Option | Semantic accuracy | SQLite compatibility | Migration required | Operational risk | Complexity | Recommendation |
|---|---|---|---|---|---|---|
| No DB constraint | Matches current non-schema state but allows bulk/raw drift | Fully compatible | No | Drift remains possible outside validated writes | Low | Accept only as current 1A state with readiness detection. |
| Application transaction/locking only | Accurate for normal product paths | `select_for_update()` is no-op on SQLite | No | Does not stop bulk/manual writes or prove SQLite races | Low/medium | Implemented as bounded 1A hardening. |
| `UniqueConstraint(fields=["user"], condition=Q(status="active", is_primary=True))` | Matches today's write policy, but is stricter than read-time currentness and would forbid current+future active primary scheduling | Partial indexes are generally supported by SQLite, but migration behavior must be verified | Yes | Could block future transfer/scheduled-primary lifecycle if that becomes desired | Low/medium | Candidate only after separate approval. |
| Simpler DB constraint plus lifecycle redesign | Could be accurate if lifecycle formally forbids future/current active primary coexistence forever | Likely compatible depending on constraint | Yes | Product semantics change if not already agreed | Medium | Do not do in 1A. |
| Denormalized current-primary representation | Could make the current row directly unique | Compatible with design work | Yes | Larger schema/workflow redesign | High | Not justified for this slice. |
| Exclusion/date-overlap constraint | Best match for date-window overlap semantics if future/current coexistence is desired | Not portable to SQLite | Yes | Backend-specific and operationally heavier | High | Defer unless backend and lifecycle change. |

Decision: B. A DB constraint may be useful but requires a separately approved
design/migration. The simple active-primary partial unique constraint appears
aligned with today's write policy, but schema work is not authorized in 1A and
future scheduled-transfer semantics should be explicitly confirmed before
encoding that rule in the database.

Candidate future slice, not approved here:
`STRUCTURE-MEMBERSHIP-PRIMARY-DB-CONSTRAINT.1B`.

## 1A Implementation Decision

Implemented in 1A:

- Added model helpers for active-primary conflict queries and per-user
  membership-scope locking.
- Reused those helpers in staff direct add, delegated My Units add, staff and
  delegated approval, staff and delegated end, and staff set-primary paths.
- Changed shared request approval to reject any existing active primary row
  cleanly inside a transaction, including a future-dated active primary.
- Added focused tests for future active primary conflicts on model validation,
  staff approval, delegated approval, and readiness ambiguous-primary drift.

Implemented in 1A-FU1:

- Kept read-time current-primary readiness date-window-aware while adding
  broader active-primary write-invariant blocker detection.
- Refetched request rejection and end targets after acquiring the per-user
  membership mutation-scope lock.
- Made shared request rejection no-op/return `False` when the target row is no
  longer requested, preventing stale reject objects from overwriting approved
  requests.
- Added serialized stale-state tests for approve-vs-reject and processed-row
  behavior, plus readiness tests for current+future, future+future, future-only,
  and ended+current primary cases.

Deliberately not implemented in 1A:

- No migration or database constraint.
- No database backend change.
- No lifecycle redesign allowing automatic transfer or concurrent scheduled
  primary rows.
- No new membership request UX.
- No serving, permission, audience, or My Serving behavior.
- No duplicate drift command; existing setup readiness is the canonical
  read-only detector.

## Tests

Targeted tests for 1A:

- `accounts.tests.ChurchStructureMembershipFoundationTests`
- `accounts.tests.StaffMembershipRequestListTests`
- `accounts.tests.MyUnitMemberRequestReviewTests`
- `accounts.test_trial_setup_readiness_command.TrialSetupReadinessCommandTests`

The 1A targeted run passed locally on 2026-08-11. FU1 expanded the same focused
membership/readiness run to 88 tests and it passed locally on 2026-08-11.
SQLite tests verify state
correctness, idempotent fail-closed behavior, and readiness classification; they
do not prove row-level race behavior on a future backend.

## Rollout And Rollback

Rollout is code/docs-only. No data migration and no data mutation are required.
The safest rollout verification is targeted tests, `manage.py check`,
`makemigrations --check --dry-run`, and `git diff --check`.

Rollback is reverting the code/docs changes from this slice. Because no schema
or data changes are introduced, rollback does not require database migration or
data repair. If production data already contains ambiguous current primaries,
rollback does not repair or worsen that data; selectors continue to fail closed
and readiness continues to report blockers.
