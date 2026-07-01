# Ministry Role Source-of-Truth Plan

Status: `MINISTRY-ROLE-SOURCE.1A` is a **docs + read-only audit** slice. It locks
the intended future source-of-truth boundary for long-term ministry roles and
adds a read-only drift audit. It changes **no** runtime permission, mutates no
data, switches no source of truth, runs no backfill, and adds no migration or
model-field change.

`MINISTRY-ROLE-SOURCE.1C` is **implemented**: runtime ministry team-management
permission now reads active `MinistryTeamRoleAssignment` rows (role_type code in
{`lead`, `coordinator`}) for the exact team, not `TeamMembership.role`.
`can_manage_ministry_team`, `can_manage_team_assignment_for_team`,
team scheduling, manage-members, and the My Serving "Teams I manage" section all
follow this role-assignment source. `TeamMembership.role` is now legacy
compatibility data only and no longer grants runtime team-management permission;
`TeamMembership.can_lead` remains deprecated/reserved and grants no permission.
Staff / superuser / global capability behavior is unchanged, and this slice is
exact-team only (no ancestor ministry teams, church-structure anchors,
`ChurchStructureMembership`, or `ChurchStructureUnitRoleAssignment`; no
`CAP_MANAGE_MINISTRY_STRUCTURE` wiring; no model or migration change).

`MINISTRY-ROLE-SOURCE.1A-FU1` is a docs + read-only-audit follow-up that
clarifies the membership expectation for management-role holders by team kind
(assignable vs container; Section 2.1) and adjusts the alignment audit so the
"management role assignment without membership" signal is a warning only for
`is_assignable=True` teams and an allowed info counter for `is_assignable=False`
container teams. It changes no permission, mutates no data, adds no migration or
model-field change, and does not switch the source of truth.

`MINISTRY-ROLE-SOURCE.1B` is **implemented** as a dry-run-by-default backfill
command (`backfill_ministry_role_assignments_from_memberships`, logic in
`ministry/role_source_backfill.py`). It creates missing
`MinistryTeamRoleAssignment` rows from existing active, user-linked
`TeamMembership.role` in {`lead`, `coordinator`}. It is dry-run by default and
writes only under explicit `--apply`; it changes **no** permission, switches no
source of truth, mutates no `TeamMembership` row, never backfills from
`can_lead`, and never auto-resolves manager disagreements. See Section 6.1. The
`--apply` mode is not run without explicit user approval.

`MINISTRY-ROLE-SOURCE.1D` is **implemented**: the normal manage-members UI no
longer presents `TeamMembership.role` or `TeamMembership.can_lead` as a
leadership/permission control. `TeamMembershipForm` no longer includes `role`
(normal creates use the model default `member`; existing legacy `role` values are
preserved untouched on edit) and never included `can_lead`, so a save cannot set
either from this UI (a malicious `can_lead=on` / `role=lead` POST is ignored).
The manage-members page now shows canonical long-term roles from active
`MinistryTeamRoleAssignment` rows (never from `TeamMembership.role`) and links
staff to the structure-setup Long-term Ministry Roles section. It changes no
runtime permission, mutates no data, removes no model field, and adds no
migration.

`MINISTRY-ROLE-SOURCE.1E-A` is **implemented** as a dry-run-by-default cleanup
command (`cleanup_team_membership_can_lead_flags`, logic in
`ministry/can_lead_cleanup.py`). It clears deprecated `TeamMembership.can_lead=True`
flags (active and inactive rows; `--team-id` narrows scope). Dry-run by default;
writes only under explicit `--apply`, and even then it only sets `can_lead`
`True` → `False`. It never mutates `TeamMembership.role`, never
creates/deletes/(de)activates a `TeamMembership` or `MinistryTeamRoleAssignment`
row, infers no role from `can_lead`, and changes no permission. See Section 6.2.
The `--apply` mode is not run without explicit user approval.

This plan sits beside `docs/MINISTRY_STRUCTURE_ARCHITECTURE_PLAN.md` (which
introduced the ministry role system as additive) and narrows the long-term
direction for *which* model owns long-term ministry role authority.

## 1. Current problem

There are currently two places that model a long-term ministry role, and they
can disagree:

* **`TeamMembership.role`** (`member` / `lead` / `coordinator`). Historically
  (before `1C`) this was the runtime permission source for
  `ministry.permissions.can_manage_ministry_team` and team-leader scheduling.
  After `1C` it is **legacy compatibility data only** and grants no runtime
  team-management permission.
  **`TeamMembership.can_lead`** is a separate deprecated/reserved/transitional
  flag: it grants **no** scheduling, member-management, or admin permission. It
  still exists on `TeamMembership` rows, but after `1D` it is not editable from
  the normal manage-members UI (`TeamMembershipForm` does not include it). The
  audit reports `can_lead=True` rows as a warning until
  `cleanup_team_membership_can_lead_flags --apply` is explicitly approved/run
  (see Section 6.2).
* **`MinistryTeamRoleAssignment`** (added in `MINISTRY-STRUCTURE.1B`). This is an
  explicit, dated, multi-active-allowed long-term ministry role tied to a
  `MinistryTeamRoleType` (`lead`, `assistant_lead`, `coordinator`, `scheduler`,
  …). After `1C` it is the **runtime team-management permission source** (role
  code in {`lead`, `coordinator`} on the exact team) and is never inferred from
  `TeamMembership`.

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

### 2.1 Assignable vs container teams (source-of-truth clarifications, `1A-FU1`)

These decisions are **locked** for the long-term direction:

* **`MinistryTeamRoleAssignment` remains the canonical source for long-term
  ministry roles, including Lead.** It is not demoted, and it is not one of two
  co-equal sources; it is the intended single source of truth.
* **Do not remove Lead from Ministry Structure.** Lead is a long-term ministry
  role expressed as a `MinistryTeamRoleAssignment` (role code `lead`), and it
  stays part of the structure/role model.
* **Do not make `TeamMembership.role` the future canonical Lead source.**
  `TeamMembership.role` is transitional/legacy; after the `1C` read switch it
  drives no runtime team-management permission, and it is never promoted to the
  long-term role authority.
* **Do not use bidirectional sync** between `TeamMembership.role` and
  `MinistryTeamRoleAssignment`. Only the `1B` one-way backfill (legacy membership
  role → role assignment) is planned; the reverse write-back is explicitly not a
  goal.
* **Multiple UI entry points are allowed in the future**, but **all canonical
  role writes must go to `MinistryTeamRoleAssignment`.** A convenience shortcut
  (for example, a future manage-members action) may exist, but it must write the
  canonical role assignment rather than create a second source of truth.

Membership expectation by team kind (`MinistryTeam.is_assignable`):

* **`is_assignable=True` (assignable team):** management-role holders (`lead` /
  `coordinator` `MinistryTeamRoleAssignment`) **should also be active
  `TeamMembership` rows on that team.** An assignable team has a concrete
  schedulable member pool, so a long-term manager is expected to be in that pool.
  `is_assignable=True` means the team **may be selected for ServiceEvent required
  teams / `TeamAssignment` across any event type** (not just Sunday worship), so
  it needs a real candidate pool.
* **`is_assignable=False` (container team):** management-role holders **do not
  need a `TeamMembership`.** A container team is **structure/container only and
  is not a direct `TeamAssignment` target**, so it has no schedulable member
  pool; a `MinistryTeamRoleAssignment` may name a long-term leader without a
  membership row. This case is reported by the alignment audit as an **allowed
  info counter**, not a warning.

The alignment audit reflects this: `management_role_assignment_without_membership`
is a **warning only for `is_assignable=True` teams**; for `is_assignable=False`
container teams the same shape is recorded as the allowed info counter
`container_management_role_assignment_without_membership`. Team-level
disagreement (`teams_management_role_user_disagreement`) stays a warning
regardless of team kind, because both systems are then explicitly naming
management users and they differ.

## 3. State after `1C`

After the `1C` read switch:

* `MinistryTeamRoleAssignment` (role code in {`lead`, `coordinator`}, active and
  date-valid, on the exact team) is the **runtime team-management permission
  source**. `can_manage_ministry_team`, `can_manage_team_assignment_for_team`,
  team scheduling, manage-members, and the My Serving "Teams I manage" section
  all read it.
* `TeamMembership.role` and `TeamMembership.can_lead` **remain on the model as
  legacy compatibility data**, but grant no runtime team-management permission.
  They are not removed in `1C`. (In `1C` they were still on the manage-members
  form; `1D` later removed `role` from that form and confirmed `can_lead` is not
  editable there — see Section 4.)
* `TeamMembership` stays candidate-pool only; `TeamAssignmentMember` stays
  event-specific serving only. Neither is inferred from the other or from a role
  assignment.
* `1C` is exact-team only and changes no model field, migration, or the
  manage-members UI layout.

## 4. Migration path

Each later step is a separate, explicitly approved slice. Do not combine them.

* **`MINISTRY-ROLE-SOURCE.1A`** — docs + read-only drift audit.
  Locks the boundary above and ships
  `audit_ministry_role_source_alignment` (read-only, no `--apply`). No runtime
  change.
* **`MINISTRY-ROLE-SOURCE.1A-FU1`** — assignable/container membership expectation
  clarification (Section 2.1) + read-only audit adjustment: the "management role
  assignment without membership" signal becomes a warning only for
  `is_assignable=True` teams and an allowed info counter
  (`container_management_role_assignment_without_membership`) for
  `is_assignable=False` container teams. Docs + audit only; no runtime change, no
  migration, no data mutation, no source-of-truth switch.
* **`MINISTRY-ROLE-SOURCE.1B`** — dry-run / optional `--apply` backfill from
  existing legacy `TeamMembership.role` (`lead` / `coordinator`) to matching
  active `MinistryTeamRoleAssignment` rows. **Implemented** as
  `backfill_ministry_role_assignments_from_memberships` (Section 6.1). Dry-run by
  default; `--apply` only on explicit approval; preserves the legacy fields;
  reports `data_mutated`; never deletes membership rows; only maps user-linked
  management memberships (display-name-only ones cannot be mapped); conservative
  conflict policy (Section 6.1) so a team where the two systems name different
  managers is reported, not auto-resolved.
* **`MINISTRY-ROLE-SOURCE.1C`** — permission **read switch**. **Implemented.**
  `can_manage_ministry_team`, `manageable_assignment_teams`, and related
  management checks now read active `MinistryTeamRoleAssignment` rows (role code
  in {`lead`, `coordinator`}, exact team) instead of `TeamMembership.role`. This
  is the step that actually changed runtime authority. Exact-team only; staff /
  superuser / global capability behavior unchanged; no model or migration change.
* **`MINISTRY-ROLE-SOURCE.1D`** — manage-members UI cleanup. **Implemented.**
  The manage-members page stops presenting the long-term role as the canonical
  role source: `TeamMembershipForm` no longer includes `role` (normal creates use
  the model default `member`; existing legacy `role` values are preserved
  untouched on edit) and never included `can_lead`, so neither can be set from
  this UI. The members list shows canonical long-term roles from active
  `MinistryTeamRoleAssignment` rows (never from `TeamMembership.role`) and links
  staff to the structure-setup Long-term Ministry Roles section. This slice adds
  no manage-members write shortcut for canonical roles; any future one must write
  `MinistryTeamRoleAssignment` and must not create a second source of truth or
  bidirectional sync. No runtime permission change, no model-field removal, no
  migration.
* **`MINISTRY-ROLE-SOURCE.1E-A`** — deprecated `can_lead` flag cleanup command.
  **Implemented** as `cleanup_team_membership_can_lead_flags` (Section 6.2).
  Dry-run by default; `--apply` only on explicit approval; clears
  `can_lead=True` → `False` on active and inactive rows (`--team-id` narrows
  scope); reports `data_mutated`; never touches `TeamMembership.role`, never
  creates/deletes/(de)activates a membership or role assignment, and changes no
  permission. This closes the remaining `active_team_memberships_can_lead_true`
  alignment warning without removing the field.
* **Later (optional)** — field deprecation/removal of `TeamMembership.role` /
  `TeamMembership.can_lead`, only after the data backfill (`1B`), permission
  switch (`1C`), UI cleanup (`1D`), and `can_lead` data cleanup (`1E-A`) are
  complete and stable, and only via a separately approved audit + migration slice
  following the repo's field-retirement discipline.

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
* active `MinistryTeam` count;
* `container_management_role_assignment_without_membership` — **allowed** count
  of management role assignments on `is_assignable=False` container teams whose
  user has no active `TeamMembership` on that team. This is expected for
  container teams (no schedulable member pool) and is info, not a warning.

### Warnings (transitional drift / setup gaps — not fatal)

* active management `TeamMembership` (`role` in {`lead`, `coordinator`}) with a
  linked user but **no** equivalent active `MinistryTeamRoleAssignment` on the
  same team;
* active management `MinistryTeamRoleAssignment` (role code in {`lead`,
  `coordinator`}) on an **`is_assignable=True`** team whose user has **no**
  active linked `TeamMembership` on that team (for `is_assignable=False`
  container teams this is not a warning — it is the allowed info counter
  `container_management_role_assignment_without_membership`);
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

## 6.1 One-way backfill command (`1B`)

`backfill_ministry_role_assignments_from_memberships` (logic in
`ministry/role_source_backfill.py`) creates missing `MinistryTeamRoleAssignment`
rows from existing legacy management memberships. Options: `--apply`,
`--verbose`, `--limit N` (caps verbose examples only; does not narrow scope),
`--team-id ID`, `--role lead|coordinator`.

**Dry-run by default.** Rows are written only under explicit `--apply`, and
`--apply` is not run without explicit user approval. It creates only
`MinistryTeamRoleAssignment` rows; it never creates `TeamMembership` rows, never
deletes/deactivates/overwrites any row, and never mutates `TeamMembership.role` /
`TeamMembership.can_lead`. Running it changes no permission and switches no
source of truth; after the `1C` read switch, runtime already reads
`MinistryTeamRoleAssignment` for team management, so this backfill only ensures
the role-assignment rows exist. There is no bidirectional sync — this is a
one-way membership-role → role-assignment backfill.

Scan: active `TeamMembership` rows where `is_active=True`, `team.is_active=True`,
`user` is not null, and `role` in {`lead`, `coordinator`}. Mapping is minimal:
`lead` → role code `lead`, `coordinator` → role code `coordinator`. It never
backfills from `can_lead=True` (reported only as an `ignored_can_lead_true`
transparency count) and infers no scheduler / technical / admin / member-care
roles.

Per-candidate outcomes:

* **`skipped_missing_role_type`** — the mapped `MinistryTeamRoleType` is missing
  or inactive (config gap). The command creates no role type and no assignment;
  seed via `seed_ministry_structure_roles` first.
* **`skipped_existing`** — an exact active assignment already exists for the same
  (team, user, role type). No duplicate is created.
* **`conflict_existing_different_user`** — the same (team, role type) already has
  an active assignment held by a *different* user. Although the model allows
  multiple active Leads, this backfill is conservative: it reports the conflict,
  creates nothing, and overwrites/deactivates nothing, leaving it for manual
  decision. This is how the known team #1 disagreement is handled — it is
  **skipped as a conflict, never auto-resolved**.
* **`would_create` / `created`** — otherwise a new active
  `MinistryTeamRoleAssignment` is planned (dry-run) or written (`--apply`) with
  `start_date = timezone.localdate()` and the note "Backfilled from
  TeamMembership.role by MINISTRY-ROLE-SOURCE.1B.", after `full_clean()`.
* **`skipped_display_name_only`** — a management membership with no linked user
  cannot become a user-linked role assignment; reported and skipped.

`data_mutated` is `true` only when at least one row was actually created under
`--apply`; a dry-run always reports `false`, and an `--apply` run that creates
nothing (only conflicts/skips) also reports `false`.

`1B` does **not** create `TeamMembership` rows and does **not** resolve the
assignable-team "management role assignment without membership" warning surfaced
by the alignment audit (that gap needs a membership, which this command never
creates); it only backfills the reverse direction (membership role → role
assignment).

## 6.2 Deprecated `can_lead` cleanup command (`1E-A`)

`cleanup_team_membership_can_lead_flags` (logic in
`ministry/can_lead_cleanup.py`) clears the deprecated/reserved
`TeamMembership.can_lead=True` flag, which after the `1C` read switch grants no
permission (runtime team-management authority reads active lead/coordinator
`MinistryTeamRoleAssignment` rows for the exact team). Leaving `can_lead=True`
rows around is only stale legacy data that the alignment audit reports as the
`active_team_memberships_can_lead_true` warning.

It is dry-run by default and mutates nothing unless `--apply` is passed. Even
under `--apply` it only sets `can_lead` `True` → `False`. It never touches
`TeamMembership.role`, never creates/deletes/(de)activates a `TeamMembership` or
`MinistryTeamRoleAssignment` row, infers no role from `can_lead`, and changes no
permission. Both active and inactive memberships are in scope by default so the
deprecated flag is cleared completely; `--team-id` narrows the scope to one team,
and `--limit` caps verbose example rows only (it does not narrow scan/apply
scope).

Output reports `mode` (DRY RUN / APPLY), `candidates_checked`, `would_clear`,
`cleared`, and `data_mutated`. `data_mutated` is `true` only when at least one
row was actually cleared under `--apply`; a dry-run always reports `false`, and
an `--apply` run with no `can_lead=True` rows in scope also reports `false`. The
`--apply` mode is not run without explicit user approval.

This command does not remove the `can_lead` model field; field
deprecation/removal remains a later, separately approved audit + migration slice.

## 7. Boundaries reminder

`ChurchStructureMembership` is church belonging and is unrelated to ministry
serving or ministry role. `TeamMembership` is ministry candidate-pool belonging.
`MinistryTeamRoleAssignment` is long-term ministry responsibility (and, after
`1C`, the runtime team-management permission source). `TeamAssignmentMember` is
event serving. None of these implies another; this plan does not change that.
