# Ministry Role Source-of-Truth Plan

Status: `MINISTRY-ROLE-SOURCE.1A` is a **docs + read-only audit** slice. It locks
the intended future source-of-truth boundary for long-term ministry roles and
adds a read-only drift audit. It changes **no** runtime permission, mutates no
data, switches no source of truth, runs no backfill, and adds no migration or
model-field change. Runtime permissions still read the legacy
`TeamMembership.role` (`role` in {`lead`, `coordinator`}) until later, separately
approved slices; `TeamMembership.can_lead` remains deprecated/reserved and grants
no permission.

This plan sits beside `docs/MINISTRY_STRUCTURE_ARCHITECTURE_PLAN.md` (which
introduced the ministry role system as additive) and narrows the long-term
direction for *which* model owns long-term ministry role authority.

## 1. Current problem

There are currently two places that model a long-term ministry role, and they
can disagree:

* **`TeamMembership.role`** (`member` / `lead` / `coordinator`). Today this is
  the *runtime permission source*:
  `ministry.permissions.can_manage_ministry_team` (and team-leader scheduling)
  grants team management when a user has an active `TeamMembership` on the team
  with `role` in {`lead`, `coordinator`}.
  **`TeamMembership.can_lead`** is a separate deprecated/reserved/transitional
  flag: it grants **no** scheduling, member-management, or admin permission
  today, but it still exists on the row and on the manage-members form, so this
  audit reports `can_lead=True` as a warning.
* **`MinistryTeamRoleAssignment`** (added in `MINISTRY-STRUCTURE.1B`). This is an
  explicit, dated, multi-active-allowed long-term ministry role tied to a
  `MinistryTeamRoleType` (`lead`, `assistant_lead`, `coordinator`, `scheduler`,
  …). It is the more correct long-term model, but it is currently **additive
  only**: it drives no permission and is never inferred from `TeamMembership`.

Keeping both as authoritative long-term role sources creates ambiguity: a future
reader/permission check would not know which one wins, and the two can drift
(a `lead` membership with no role assignment, a role assignment with no
membership, or the two naming different people on the same team).

`TeamMembership.role` also conflates two different ideas — "this person is in the
team's candidate pool" (membership) and "this person is a long-term lead/
coordinator" (responsibility/permission). Those should be separated.

## 2. Locked target boundary

The long-term boundary is:

* **`TeamMembership`** = team **membership / candidate pool** only. It records
  who belongs to / can be scheduled from a team. It is **not** the long-term
  role authority and is **not** event serving.
* **`MinistryTeamRoleAssignment`** = the **single source of truth for long-term
  ministry roles** and the eventual **team-management permission source**
  (e.g. lead/coordinator → may manage their team / schedule their team).
* **`TeamAssignmentMember`** = **event-specific serving assignment** (who is
  serving on a specific `ServiceEvent` via a `TeamAssignment`). Unchanged by this
  plan; serving stays separate from both membership and long-term role.

Belonging, long-term role, and event serving stay three distinct concepts. None
of them is inferred from the others.

## 3. Transitional state (current)

While the migration is incomplete:

* `TeamMembership.role` and `TeamMembership.can_lead` **remain** for current
  runtime compatibility. `can_manage_ministry_team` still reads
  `TeamMembership.role` in {`lead`, `coordinator`}.
* `MinistryTeamRoleAssignment` **remains additive** and drives no permission.
* This slice (`1A`) does **not** change any runtime permission, form, or UI. It
  only documents the decision and exposes current drift/gaps via a read-only
  audit.

## 4. Migration path

Each later step is a separate, explicitly approved slice. Do not combine them.

* **`MINISTRY-ROLE-SOURCE.1A` (this slice)** — docs + read-only drift audit.
  Locks the boundary above and ships
  `audit_ministry_role_source_alignment` (read-only, no `--apply`). No runtime
  change.
* **`MINISTRY-ROLE-SOURCE.1B`** — dry-run / optional `--apply` backfill from
  existing legacy `TeamMembership.role` (`lead` / `coordinator`) to matching
  active `MinistryTeamRoleAssignment` rows, separately approved. Dry-run by
  default; `--apply` only on explicit approval; preserves the legacy fields;
  reports `data_mutated`; never deletes membership rows; only maps user-linked
  management memberships (display-name-only ones cannot be mapped).
* **`MINISTRY-ROLE-SOURCE.1C`** — permission **read switch**: change
  `can_manage_ministry_team` (and any related management check) to read
  `MinistryTeamRoleAssignment` instead of `TeamMembership.role`, separately
  approved and only after `1B` data is in place and verified. This is the step
  that actually changes runtime authority.
* **`MINISTRY-ROLE-SOURCE.1D`** — UI cleanup so the manage-members page stops
  presenting the long-term role as the canonical role source (members page
  focuses on the candidate pool; long-term role lives on the structure / role
  assignment page), separately approved.
* **Later (optional)** — field deprecation/removal of `TeamMembership.role` /
  `TeamMembership.can_lead`, only after the data backfill (`1B`) and permission
  switch (`1C`) are complete and stable, and only via a separately approved
  audit + migration slice following the repo's field-retirement discipline.

## 5. Explicit non-goals (for `1A`)

`MINISTRY-ROLE-SOURCE.1A` does **not**:

* switch any permission or change `can_manage_ministry_team`;
* mutate any data (no `--apply`, no backfill, no role creation);
* backfill `MinistryTeamRoleAssignment` from `TeamMembership.role`;
* remove or hide `role` / `can_lead` from any form or the manage-members UI, or
  rewrite the manage-members UI;
* change `TeamAssignmentMember` / My Serving / event-serving semantics;
* infer serving from `ChurchStructureMembership`, `TeamMembership`, or
  `MinistryTeamRoleAssignment`;
* add a migration or change any model field.

It only documents the decision and reports current drift.

## 6. Read-only alignment audit

`audit_ministry_role_source_alignment` (logic in
`ministry/role_source_alignment.py`) is strictly read-only: no `--apply`, mutates
nothing, makes no permission decision, and backfills nothing. Options:
`--verbose`, `--limit N`, `--fail-on-blockers` (exits non-zero only when blocker
count > 0; warnings never fail).

Equivalent role mapping is intentionally minimal: legacy membership `lead` →
ministry role code `lead`; membership `coordinator` → ministry role code
`coordinator`. Scheduler / technical / other ministry roles are **not** inferred
from `TeamMembership`. If the `coordinator` role type is missing, that is a
config-gap warning, not a blocker; the audit creates no role types.

### Info (inventory)

* active `TeamMembership` count;
* active `TeamMembership` rows by role (`member` / `lead` / `coordinator`);
* active `TeamMembership` rows with `can_lead=True`;
* active `MinistryTeamRoleAssignment` count;
* active ministry role assignments by role-type code;
* active `MinistryTeam` count.

### Warnings (transitional drift / setup gaps — not fatal)

* active management `TeamMembership` (`role` in {`lead`, `coordinator`}) with a
  linked user but **no** equivalent active `MinistryTeamRoleAssignment` on the
  same team;
* active management `MinistryTeamRoleAssignment` (role code in {`lead`,
  `coordinator`}) whose user has **no** active linked `TeamMembership` on that
  team;
* active `TeamMembership.can_lead=True` (transitional flag, not the long-term
  role source);
* active management `TeamMembership` with **no linked user**
  (display-name-only), which cannot become a user-linked role assignment;
* teams where **both** systems carry management roles but the users disagree;
* coordinator memberships present while the `coordinator` ministry role type is
  missing (config gap).

### Blockers (conservative)

Because runtime has not switched and most divergence is expected, drift is a
**warning**, not a blocker. The only blocker is a high-confidence corruption:

* duplicate **active** `MinistryTeamRoleAssignment` rows for the same
  (team, role type, user). The model's `clean()` already rejects overlapping
  active duplicates, so this is expected to be zero against clean data; if
  present it would make a future dedup/backfill ambiguous and must be resolved
  before `1B`/`1C`.

## 7. Boundaries reminder

`ChurchStructureMembership` is church belonging and is unrelated to ministry
serving or ministry role. `TeamMembership` is ministry candidate-pool belonging.
`MinistryTeamRoleAssignment` is long-term ministry responsibility (and the
future permission source). `TeamAssignmentMember` is event serving. None of these
implies another; this plan does not change that.
