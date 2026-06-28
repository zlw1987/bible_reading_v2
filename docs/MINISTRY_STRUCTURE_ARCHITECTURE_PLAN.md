# Ministry Structure Architecture Plan

Status: `MINISTRY-STRUCTURE.1A` created the full ministry-structure architecture
plan (target design, alternatives, models/fields, boundaries, phases).
`MINISTRY-STRUCTURE.1A-D` is a docs-only decision-lock slice that locked the key
architecture decisions previously listed as open (see Section 14, now
"Architecture Decisions Locked for 1B"): upgrade `MinistryTeam` in place, keep
both `team_kind` and `is_assignable`, use a dedicated `MinistryTeamParentLink`
with explicit nullable parent FKs, give `MinistryTeamRoleAssignment` an
`is_active` + date-window history with multiple active Leads allowed, treat
missing required roles as warnings only, follow the shared-vs-separate team
guideline, introduce a new `CAP_MANAGE_MINISTRY_STRUCTURE` capability, and keep
`TeamMembership.role` / `can_lead` as the permission source while the new role
model stays additive in the foundation phase.

`MINISTRY-STRUCTURE.1B` implemented the additive model/admin/test foundation
(migration `ministry/0003`): new `MinistryTeam.team_kind` / `is_assignable` /
`role_profile` fields (existing rows default to `team_kind=team`,
`is_assignable=True`), the dedicated `MinistryTeamParentLink` (explicit nullable
`parent_team` / `parent_church_unit`, exactly-one-target check constraint,
cycle/duplicate/primary `clean` validation), and the ministry role system
(`MinistryTeamRoleType` / `MinistryTeamRoleProfile` /
`MinistryTeamRoleRequirement` / `MinistryTeamRoleAssignment`) plus admin
registration and read-only `MinistryTeam` structure helpers
(`active_parent_links`, `primary_parent_link`, `get_ministry_ancestors`,
`primary_church_anchor`, `display_path_label`, `missing_required_role_types`).
This is additive only: it changes no runtime behavior, does not touch
`can_manage_ministry_team` / `manageable_assignment_teams` (TeamMembership.role /
can_lead remains the permission source), does not enforce `is_assignable` on
`TeamAssignment`, does not change My Serving / Today / ServiceEvent / Bible Study
visibility, seeds no defaults, and backfills no hierarchy or roles. The
`CAP_MANAGE_MINISTRY_STRUCTURE` capability was intentionally **not** added to
`accounts/permissions.py` in this slice (see Section 13 / Section 10): it would
be an unused cross-app capability-registry change, so it stays documented-only
until the later delegated-management slice.

`MINISTRY-STRUCTURE.1C` implemented a read-only staff **Ministry Structure**
map (`ministry_structure_map`, `/ministry/structure/`) plus a small read-only
helper module (`ministry/structure_map.py`). The page is staff/superuser-only
(`request.user.is_staff or request.user.is_superuser`); access is **not** granted
by `TeamMembership.role` / `can_lead`, `MinistryTeamRoleAssignment`,
`ChurchStructureUnitRoleAssignment`, or `ChurchStructureMembership`, and a church
anchor never grants access. It shows ministry teams grouped under their church
display anchors (with the church ancestor path), the ministry parent/child tree,
shared/multi-parent teams (primary occurrence expanded, additional occurrences as
compact "also linked here" references), unanchored teams, container vs assignable
status, active lead names, and missing-required-role readiness. It is GET-only and
read-only: it creates/updates/deletes nothing, drives no permission, does not read
membership as serving, and changes no My Serving / Today / `TeamAssignment` /
`can_manage_ministry_team` / visibility behavior. The `CAP_MANAGE_MINISTRY_STRUCTURE`
capability was again **not** added in this slice.

Runtime behavior changes — `is_assignable` enforcement, permission migration to
`MinistryTeamRoleAssignment`, delegated ministry management + the new
capability — remain deferred to later, separately approved slices.

Related existing docs:

- `docs/MINISTRY_TEAM_OPERATIONS_V1_PLAN.md` — current Ministry Team Operations
  V1 product boundary (teams, memberships, ServiceEvent-based assignments, My
  Serving).
- `docs/MINISTRY_SCHEDULING_REQUIREMENTS_PLAN.md` — scheduling/coverage
  requirements built on `TeamAssignment`.
- `docs/STRUCTURE_UNIT_COWORKER_ROLE_ARCHITECTURE_PLAN.md` — the
  `ChurchStructureUnit` coworker role-type / role-profile / requirement /
  assignment system. **This is the closest existing precedent and the pattern
  this plan deliberately mirrors in the ministry namespace.**
- `docs/MEMBER_RECORD_AND_SERVING_READINESS_PLAN.md` — delegated unit management
  (`/my-units/`), `can_manage_unit_coworkers` ancestor-or-self `lead` model.
- `docs/CHURCH_STRUCTURE_DOMAIN_PLAN.md` — church-structure vs ministry-team
  domain boundaries.
- `docs/TODAY_AND_MY_SERVING_PRODUCT_BOUNDARIES.md` — Today / My Serving
  surface boundaries.

---

## 0. Executive Summary and Direction Decision

The user's preferred direction is to **upgrade the existing `MinistryTeam` model
into the ministry-structure unit**, rather than create a separate parallel
`MinistryStructureUnit` table.

**This plan accepts that direction.** After reading the ministry app and the
church-structure code, upgrading `MinistryTeam` in place is the cleaner and
lower-risk choice:

- `TeamMembership`, `TeamAssignment`, and `TeamAssignmentMember` already point at
  `MinistryTeam` (`ministry/models.py`), several with `on_delete=CASCADE`. A
  separate `MinistryStructureUnit` table would force either dual-pointing FKs on
  every serving object or a mass migration of every assignment/membership target.
  Neither is justified when existing rows already *are* the real ministry units.
- The `ChurchStructureUnit` coworker role system (role type → profile →
  requirement → assignment, plus `missing_required_role_types`,
  `path_label`, `get_ancestors`, ancestor-or-self `lead` management) is a proven,
  directly transferable pattern. We replicate it in the ministry namespace
  instead of inventing a new shape.

Three refinements/findings were surfaced for an explicit decision and are now
**locked** by `MINISTRY-STRUCTURE.1A-D` (see Section 14; details in the sections
noted):

1. **A dedicated `MinistryTeamParentLink` model is justified** (Section 5),
   unlike `ChurchStructureUnit` which uses a single self-referential `parent` FK.
   The ministry requirement is *multi-parent* and *dual-target* (a parent may be
   another `MinistryTeam` **or** a `ChurchStructureUnit` anchor), which a single
   self-FK cannot express. Recommended shape: two nullable FKs + a check
   constraint, not a `GenericForeignKey` (matches this codebase's explicit-FK
   style).

2. **The biggest existing-system tension is the meaning of "Lead."** Today
   `ministry/permissions.py::can_manage_ministry_team` infers lead/coordinator
   authority from `TeamMembership.role` (`member` / `lead` / `coordinator`) and
   `TeamMembership.can_lead`. The proposed `MinistryTeamRoleAssignment(lead)`
   introduces a *second* source of "Lead." These must not silently diverge.
   Recommended path (Section 8): the new role-assignment model is **additive and
   does not drive permissions** in the foundation phase; migrating
   `can_manage_ministry_team` from `TeamMembership.role` to
   `MinistryTeamRoleAssignment` is a **separately approved later slice**.

3. **Both `team_kind` and `is_assignable` are worth keeping, but they are not
   redundant** (Section 6). `is_assignable` is the authoritative behavioral gate
   for `TeamAssignment`; `team_kind` is descriptive taxonomy used for the
   structure-map display and for *suggesting* an initial `is_assignable` default.

No part of this plan changes ServiceEvent visibility, Bible Study visibility,
`ChurchStructureMembership`, My Units, member/care records, My Serving, or
Today.

---

## 1. Problem Statement

`MinistryTeam` today is a **flat** model: a name, bilingual labels, description,
email alias, playbook link, and an `is_active` flag (`ministry/models.py`). It
has no parent, no kind, no structure, and no long-term role record. Leadership is
encoded only as `TeamMembership.role` (`member` / `lead` / `coordinator`) plus a
`can_lead` boolean.

Real ministry operation needs more than a flat list:

- Ministry units form a **hierarchy**: a `Digital Ministry` area contains
  `Projection Team`, `Video Team`, `Audio Team`, etc.
- Some ministry units are **assignable** to a weekly `ServiceEvent`
  (`Projection Team`); others are higher-level **containers/areas**
  (`Digital Ministry`) that should not be selected as a weekly assignment target.
- Ministry units belong, organizationally, under a church context
  (`CM` / `EM`), and some are **shared** between CM and EM.
- Ministry units need **explicit long-term roles** beyond "Lead": coordinator,
  scheduler, trainer, technical lead, equipment manager, member care, etc., and
  must support **multiple active Leads**.
- Staff need a **structure map** and a **readiness signal** (e.g. "this active
  ministry unit has no active Lead").

The product problem is *ministry organization and long-term ministry
responsibility*. It is explicitly **not** church belonging, audience visibility,
or weekly serving assignment — those remain owned by other models.

---

## 2. Current-System Impact Analysis

What exists today (read from `ministry/`):

| Object | Role today | Change under this plan |
| --- | --- | --- |
| `MinistryTeam` | Flat ministry team; assignment + membership target | **Upgraded** to also be the ministry-structure unit (adds parent links, kind, assignable flag, role profile). Existing rows preserved. |
| `TeamMembership` | Member/candidate pool for a team; `role` member/lead/coordinator; `can_lead` | **Unchanged in scope.** Remains the ordinary member/candidate pool. Its `role` field stays the permission source until a later approved slice migrates permissions (Section 8). |
| `TeamAssignment` | A `ServiceEvent` needs a specific team | **Unchanged.** Later gains an `is_assignable` validation guard (Section 6). |
| `TeamAssignmentMember` | Specific people assigned to that event/team | **Unchanged.** |
| `ministry/permissions.py` | `can_manage_ministry_team` infers lead from `TeamMembership.role` | **Unchanged in foundation phase.** Permission migration to role assignments is a separate later slice. |
| `ministry/views.py` `my_serving` etc. | Weekly serving + ongoing structure roles | **Unchanged in foundation phase.** Path-label polish is a later display-only slice. |

Surfaces that reference ministry teams today and must keep working:

- Staff Overview (`templates/accounts/staff/overview.html`) — "Ministry Teams"
  (`ministry_team_list`) and "Team Assignments" (`team_assignment_list`) buttons.
- Team list/detail, manage members, team schedule, assignment list/detail,
  My Serving (`templates/ministry/*`).
- Lighting pilot import (`ministry/services/lighting_pilot_import.py`).

**Compatibility requirement:** every existing `MinistryTeam` row keeps working
as an assignable team with its current membership pool. New structure fields must
be nullable/defaulted so no existing row is invalidated.

---

## 3. Domain Boundary: Ministry Structure ≠ Church Structure

Two separate structures coexist. They may *display* nested, but they are
**different authorities**.

`ChurchStructureUnit` / `ChurchStructureMembership` remain authoritative for:

- church belonging and membership
- ServiceEvent audience visibility
- Bible Study audience visibility
- My Units delegated church-structure coworker management
- unit member / care records

`MinistryTeam` / ministry structure is for:

- ministry organization and ministry teams
- ministry parent/child relationships
- ministry long-term leadership / role assignments
- ministry membership pools (`TeamMembership`)
- weekly / occasion-specific serving assignment targets (`TeamAssignment`)

A ministry team may name a `ChurchStructureUnit` as a **display/organization
anchor**. That anchor is **display only**. It must never imply
`ChurchStructureMembership`, audience visibility, serving assignment, My Serving,
church-structure delegated management, member/care-record access, Bible Study
candidacy, or ServiceEvent visibility.

---

## 4. Recommended Architecture (Target Design)

Upgrade `MinistryTeam` into the ministry-structure unit by adding, around it:

1. **Structure fields on `MinistryTeam`:** `team_kind`, `is_assignable`,
   optional `role_profile` (Section 6).
2. **`MinistryTeamParentLink`** — multi-parent, dual-target (ministry team or
   church anchor), with one primary per child for breadcrumb (Section 5).
3. **Ministry role system** mirroring the church coworker role system
   (Section 7): `MinistryTeamRoleType`, `MinistryTeamRoleProfile`,
   `MinistryTeamRoleRequirement`, `MinistryTeamRoleAssignment`.

All additions are **additive**. Existing `MinistryTeam`, `TeamMembership`,
`TeamAssignment`, and `TeamAssignmentMember` semantics are preserved.

---

## 5. Ministry Team Parent Links

### 5.1 Why a dedicated link model (and not a self-FK)

`ChurchStructureUnit` uses a single self-referential `parent` FK. That is enough
there because each church unit has exactly one parent. **Ministry structure has
two requirements a single self-FK cannot express:**

- **Multiple parents** — a shared ministry unit may sit under several anchors
  (e.g. `Internet Mission` under both `CM` and `EM`).
- **Dual target type** — a parent may be another `MinistryTeam` (ministry
  hierarchy) **or** a `ChurchStructureUnit` (church display anchor).

A dedicated `MinistryTeamParentLink` model is therefore the right shape.

### 5.2 Recommended field design

Avoid `GenericForeignKey` (the codebase consistently uses explicit FKs). Use two
nullable FKs plus a check constraint:

```
MinistryTeamParentLink
  child_team        FK -> MinistryTeam (CASCADE)          # required
  parent_team       FK -> MinistryTeam (PROTECT, null)    # exactly one of
  parent_unit       FK -> ChurchStructureUnit (PROTECT, null)  #   these two set
  is_primary        Boolean (default False)
  is_active         Boolean (default True)
  sort_order        PositiveInteger
  created_at / updated_at
```

Validation (`clean()` / constraints):

- Exactly one of `parent_team` / `parent_unit` is set (DB check constraint +
  `clean`).
- A `parent_team` link must not create a cycle in the ministry hierarchy — walk
  the parent-team chain and reject self/ancestor cycles (mirror
  `ChurchStructureUnit.clean`'s cycle guard).
- A child may not link the same parent twice while active (uniqueness on
  `child_team` + parent target among active rows).
- A `child_team` may have **at most one active `is_primary=True` link**.
- Active links should reference active parents (warn or block per setup policy).

### 5.3 Primary display parent

- Many active parent links are allowed.
- At most one active primary parent link per child team.
- The primary parent drives the **default breadcrumb / path**.
- Other active links render as "also linked under …".
- Primary parent is **display-only**. It grants no permission, membership,
  visibility, or serving.

### 5.4 Display path resolution

When building a breadcrumb for a ministry team:

1. Walk primary `parent_team` links upward through the ministry hierarchy.
2. If a primary link reaches a `ChurchStructureUnit` anchor, continue upward
   using the normal `ChurchStructureUnit.get_ancestors()` /
   `path_label()` chain.

Example display path:

```
Whole Church > CM > Digital Ministry > Projection Team
                └ church anchor ┘ └─── ministry hierarchy ───┘
```

This is **display/organization only** (see Section 3 and Section 9 boundaries).

---

## 6. Team Kind and Assignable / Container Distinction

Because existing `MinistryTeam` rows become structure units, some rows will be
real assignable teams and some will be container/area units.

### 6.1 `team_kind` (descriptive taxonomy)

`team_kind` choices (suggested): `ministry_area`, `department`, `team`,
`subteam`, `project_group`, `custom`. Used for the structure-map display, for
grouping, and for *suggesting* an initial `is_assignable` default.

### 6.2 `is_assignable` (behavioral gate)

`is_assignable` (Boolean) is the **authoritative** behavioral gate:

- `True` → may be selected for `TeamAssignment`.
- `False` → structure/container only; cannot be a `TeamAssignment` target.

### 6.3 Both are kept (LOCKED)

**Locked decision: keep both. They are not redundant.** `is_assignable` is the
single behavioral truth (it decides what `TeamAssignment` may target);
`team_kind` is descriptive and feeds display + default suggestion. A
`team_kind=ministry_area` would default `is_assignable=False`, a
`team_kind=team` would default `is_assignable=True`, but staff may override
(e.g. an assignable `department`). Collapsing them would either lose the
display taxonomy or overload one field with two meanings, so both ship in the
foundation phase (Section 14, decision 2).

### 6.4 Assignment-time guard (later behavior slice, not foundation)

`TeamAssignment` has no DB or app guard today preventing a container from being
assigned. When `is_assignable` lands, a later slice should add an app-level
validation in `TeamAssignmentForm` / `TeamScheduleAssignmentForm` (and the model
`clean`) rejecting assignment to a non-assignable team. Existing assignment
queries that list teams (`manageable_assignment_teams`, the assignment forms)
would filter to `is_assignable=True`. This is a **behavior change** and must be
its own approved slice, not part of the additive foundation.

### 6.5 Backfill defaults

Existing rows default to `team_kind=team`, `is_assignable=True` (they are
already assignment targets). New container units (`Digital Ministry`) are created
with `team_kind=ministry_area`, `is_assignable=False`.

---

## 7. Ministry-Specific Role System

Mirror the `ChurchStructureUnit` coworker role system
(`docs/STRUCTURE_UNIT_COWORKER_ROLE_ARCHITECTURE_PLAN.md`,
`accounts/models.py`) in the ministry namespace. Same shape, separate models,
separate semantics.

### 7.1 `MinistryTeamRoleType`

- Stable `code`: `lead`, `assistant_lead`, `coordinator`, `scheduler`,
  `trainer`, `technical_lead`, `equipment_manager`, `admin`, `member_care`,
  `custom`.
- Bilingual labels, `is_active`, `sort_order`, optional description.
- `is_system_default` marker so app defaults are distinguishable from
  church-customized roles.
- Globally scoped with globally unique codes (matches the resolved V1 decision
  for `ChurchStructureUnitRoleType`).

### 7.2 `MinistryTeamRoleProfile`

- Stable `code`: `default_ministry_unit`, `technical_team`,
  `worship_related_team`, `project_team`, `custom`.
- Bilingual label/description, `is_active`, `sort_order`.
- Explicitly selected on each team via `MinistryTeam.role_profile` (nullable);
  `team_kind` may *suggest* an initial profile but must not recompute it.

### 7.3 `MinistryTeamRoleRequirement`

- Links a role profile to role types, each marked required/optional.
- Drives a `missing_required_role_types(target_date)` helper on `MinistryTeam`
  (mirror `ChurchStructureUnit.missing_required_role_types`).
- At minimum: an active ministry unit with a profile that requires `lead` should
  **warn** when it has no active `lead` assignment. A required Lead means a
  **setup warning, not a hard block**.

### 7.4 `MinistryTeamRoleAssignment`

```
MinistryTeamRoleAssignment
  team        FK -> MinistryTeam (PROTECT)
  role_type   FK -> MinistryTeamRoleType (PROTECT)
  user        FK -> AUTH_USER_MODEL
  is_active   Boolean (default True)
  start_date  Date (default today)
  end_date    Date (null)
  notes       Text (operational/non-sensitive only)
  created_at / updated_at
```

Rules:

- **Multiple active Leads are allowed.** No uniqueness on (team, role_type);
  uniqueness only prevents the *same user* holding an overlapping active window
  for the same (team, role_type), mirroring
  `ChurchStructureUnitRoleAssignment.clean`.
- Role assignments are **explicit**. They are **never inferred from
  `TeamMembership`**.
- Assigning a role creates **only** a `MinistryTeamRoleAssignment` row. It does
  not create `TeamMembership`, `TeamAssignment`, `TeamAssignmentMember`,
  `ChurchStructureMembership`, `ChurchRoleAssignment`, `ChurchStructureUnitRoleAssignment`,
  or `BibleStudyMeetingRole`, and grants no capability.

### 7.5 Default presets (suggested, configurable)

Default role types: `lead`, `assistant_lead`, `coordinator`, `scheduler`,
`trainer`, `technical_lead`, `equipment_manager`, `member_care`.

- Every ministry profile requires `lead`.
- `technical_team` may additionally recommend `technical_lead` and
  `equipment_manager` (optional, not required, to avoid blocking small teams).
- Custom role types are allowed so a team can add a local role without changing
  global choices.

Presets must be seedable via an explicit dry-run/apply command or data migration
**only after data policy is approved** (matches the coworker-role precedent).

---

## 8. Relationship to Existing Serving Objects (Critical Distinction)

Preserve current meanings; do **not** collapse concepts:

- `MinistryTeam` — now also the ministry-structure unit.
- `TeamMembership` — who belongs to a ministry team / is a member or candidate.
- `TeamAssignment` — a specific `ServiceEvent` needs a specific ministry team.
- `TeamAssignmentMember` — specific people assigned to that event/team.
- `MinistryTeamRoleAssignment` — **new** long-term leadership/coordination
  responsibility.

Required distinctions:

- Being a `TeamMembership` member is **not** being a Lead.
- Being a Lead is **not** being assigned this week.
- A parent/child ministry relationship is **not** a serving assignment.
- A `ChurchStructureUnit` anchor is **not** a permission source.
- My Serving continues to show **explicit** assignments/roles only.

### 8.1 The "two sources of Lead" tension (key decision)

Today, `ministry/permissions.py::can_manage_ministry_team` treats a user as a
team manager if they hold an active `TeamMembership` with
`role in {lead, coordinator}`. The new `MinistryTeamRoleAssignment(role_type=lead)`
introduces a second, more explicit "Lead" concept.

If both existed and both drove permissions, they could silently disagree
(someone is `TeamMembership.role=lead` but has no role assignment, or vice
versa). To avoid that:

- **Foundation phase:** `MinistryTeamRoleAssignment` is **additive only** and
  does **not** drive any permission. `can_manage_ministry_team` keeps reading
  `TeamMembership.role` exactly as today. No behavior change.
- **Later, separately approved slice:** migrate `can_manage_ministry_team`
  (and `manageable_assignment_teams`) from `TeamMembership.role` to
  `MinistryTeamRoleAssignment`, with a defined transition (backfill role
  assignments from existing leads, dry-run audit, then switch the read). This
  mirrors how church-structure migrations retired inferred authority in favor of
  explicit assignment rows.

This decision is **locked** (Section 14, decision 8): the foundation phase keeps
`TeamMembership.role` / `can_lead` as the permission source and adds
`MinistryTeamRoleAssignment` as additive-only rows. Whether
`TeamMembership.role`'s lead/coordinator values are eventually deprecated is
settled inside the later, separately approved permission-migration slice, not in
the foundation phase.

---

## 9. Boundaries / Non-Goals

Ministry Structure does **not**:

- change `ChurchStructureUnit` hierarchy
- change `ChurchStructureMembership`
- change ServiceEvent audience visibility
- change Bible Study audience visibility
- change My Units church-structure delegated management
- change unit member / care record access
- infer serving from parent links
- infer membership from parent links
- infer permissions from church anchors
- auto-create `TeamMembership`
- auto-create `TeamAssignment`
- auto-create `TeamAssignmentMember`
- auto-create `MinistryTeamRoleAssignment` from `TeamMembership`
- change My Serving immediately
- change Today immediately
- reintroduce legacy `SmallGroup` / `District` / `MinistryContext` dependency

A ministry team being anchored under a `ChurchStructureUnit` does **not** make
that unit's church-structure leads automatic managers of the ministry team
(Section 10).

---

## 10. Permission Model Direction (Document, Do Not Implement)

Future model (for discussion; not implemented in any phase here):

- **Global capability** `CAP_MANAGE_MINISTRY_STRUCTURE` (new) — staff/superuser
  and holders manage the whole ministry structure. (Today there is
  `CAP_MANAGE_MINISTRY_TEAMS` and `CAP_MANAGE_TEAM_ASSIGNMENTS` in
  `accounts/permissions.py`; the structure-management capability would be a new,
  separate grant.)
- **Delegated ministry management** — derived from an active
  `MinistryTeamRoleAssignment(role_type=lead)` on the team itself **or an
  ancestor ministry team** (ancestor-or-self), mirroring
  `accounts.unit_management.can_manage_unit_coworkers` for church units. Walk the
  ministry `parent_team` chain only.
- **Hard boundary:** church-structure leads do **not** automatically manage a
  ministry team just because it is anchored under their `ChurchStructureUnit`.
  Example: `Digital Ministry` anchored under `CM` does **not** let CM
  church-structure leads manage `Digital Ministry`. If product later wants that
  bridge, it must be a **separately approved capability**, never automatic.

The ancestor walk for ministry management must follow **ministry parent_team
links only**, never church anchors, so a church anchor can never leak management.

---

## 11. Shared CM/EM Ministries

The design supports CM-only, EM-only, and shared ministries.

**Rule to apply:**

- Same people / same leadership / same responsibility / same assignment pool →
  **one shared `MinistryTeam`** with multiple parent anchor links (e.g.
  `Internet Mission` linked under both `CM` and `EM`).
- Separate members / separate leads / separate assignments / separate
  responsibilities → **separate `MinistryTeam` rows** (e.g. `CM Projection Team`
  and `EM Projection Team`).

This rule keeps multi-parent links for genuine sharing and avoids duplicating a
team that truly has one pool, while still allowing two distinct teams when the
operational reality is distinct.

### 11.1 Worked examples

CM-only structure:

```
CM (church anchor)
└─ Digital Ministry        (team_kind=ministry_area, is_assignable=False)
   ├─ Projection Team      (team_kind=team, is_assignable=True)
   ├─ Video Team           (team_kind=team, is_assignable=True)
   └─ Audio Team           (team_kind=team, is_assignable=True)
```

Shared structure (one team, two anchors):

```
Internet Mission   primary anchor = CM, also linked under EM
                   (one shared MinistryTeam, one membership pool)
```

Partially shared structure:

```
Digital Ministry (shared)
├─ CM Projection Team   (separate team — separate members/leads)
├─ EM Projection Team   (separate team — separate members/leads)
├─ Website Team         (shared — one pool, multiple anchors)
└─ Equipment Support    (shared — one pool, multiple anchors)
```

---

## 12. Data / Backfill Strategy

- **No destructive migration.** Existing `MinistryTeam` rows remain.
- New fields are nullable/defaulted; new models are additive tables.
- Existing teams default to `team_kind=team`, `is_assignable=True`.
- New container units (`Digital Ministry`) are created with
  `team_kind=ministry_area`, `is_assignable=False`.
- Parent links and role assignments are added gradually by staff; nothing is
  auto-guessed at migration time.
- Any seed/backfill command is **dry-run first**, `--apply` only with explicit
  approval, reports `data_mutated`, and does not guess parent links aggressively
  (it may seed default role types/profiles/requirements, but should not invent
  hierarchy).
- If permissions are later migrated to role assignments (Section 8.1), the
  lead-backfill (from existing `TeamMembership.role=lead/coordinator`) is its own
  dry-run-first command in that later slice, audited before any switch.

---

## 13. Implementation Phases

Engineering-safety slices only. The **target design above is not downscoped** —
phasing controls rollout risk, not product ambition.

- **`MINISTRY-STRUCTURE.1A` (this doc):** docs-only full architecture plan. No
  code.
- **`MINISTRY-STRUCTURE.1B` — model/admin foundation (IMPLEMENTED, migration
  `ministry/0003`):**
  - Added `MinistryTeamParentLink` (explicit nullable `parent_team` /
    `parent_church_unit`, exactly-one-target check constraint, cycle / duplicate
    / single-active-primary `clean` validation enforced in Python for SQLite +
    PostgreSQL portability).
  - Added `MinistryTeam.team_kind`, `MinistryTeam.is_assignable`, and
    `MinistryTeam.role_profile` (all locked per Section 14, decisions 2 and 5);
    existing rows default to `team_kind=team`, `is_assignable=True`.
  - Added `MinistryTeamRoleType` / `MinistryTeamRoleProfile` /
    `MinistryTeamRoleRequirement` / `MinistryTeamRoleAssignment`, plus read-only
    `MinistryTeam` structure helpers (`active_parent_links`,
    `primary_parent_link`, `get_ministry_ancestors`, `primary_church_anchor`,
    `display_path_label`, `missing_required_role_types`).
  - Admin registration for all new models; focused model/validation tests.
  - **No runtime behavior change**: role assignments are additive only and do
    not drive permissions or assignment filtering. `can_manage_ministry_team` /
    `manageable_assignment_teams` are untouched, `is_assignable` is not enforced,
    and no defaults are seeded / no hierarchy is backfilled.
  - The `CAP_MANAGE_MINISTRY_STRUCTURE` capability constant was **not** added in
    this slice. Adding it to `accounts/permissions.py` (`ALL_CAPABILITIES`) would
    be an unused cross-app capability-registry change with no consumer in the
    foundation phase, so it stays documented-only (Section 10) until the later
    delegated-management slice introduces a real check.
- **`MINISTRY-STRUCTURE.1C` — read-only structure map (IMPLEMENTED):** a staff
  read-only ministry structure map (`ministry_structure_map`,
  `/ministry/structure/`, template `ministry/structure_map.html` + node partials,
  helper `ministry/structure_map.py`). Top-down anchored tree/cards using the
  existing `structure-map` CSS with simple depth-indent connector styling (no
  heavy JS diagram/canvas). Shows team kind, assignable vs container status,
  church anchors with ancestor path, ministry parent/child nesting, shared
  (multi-parent) teams with a primary occurrence plus compact "also linked here"
  references, an explicit Unanchored section, active lead names, and
  missing-required-role warnings; optional read-only filters (search, kind,
  assignable/container, missing-required, unanchored-only, include-inactive).
  Staff/superuser-only access (not granted by `TeamMembership`,
  `MinistryTeamRoleAssignment`, `ChurchStructureUnitRoleAssignment`,
  `ChurchStructureMembership`, or church anchors). GET-only and read-only: no
  edits, no created/updated/deleted rows, no permission change, and no My Serving
  / Today / `TeamAssignment` / `can_manage_ministry_team` / visibility change.
  `CAP_MANAGE_MINISTRY_STRUCTURE` was not added.
- **`MINISTRY-STRUCTURE.1D` — staff setup/edit UI:** create/edit teams, manage
  parent links + primary, select role profile, manage role assignments, surface
  missing-required-role warnings.
- **`MINISTRY-STRUCTURE.1E` — seed defaults / dry-run backfill:** seed default
  role types/profiles/requirements; dry-run-first; `--apply` on explicit
  approval only.
- **Later (separate approvals):**
  - `is_assignable` enforcement on `TeamAssignment` (behavior change, Section
    6.4).
  - Permission migration from `TeamMembership.role` to
    `MinistryTeamRoleAssignment` (Section 8.1).
  - Delegated ministry management + `CAP_MANAGE_MINISTRY_STRUCTURE` (Section 10).
  - My Serving / Today ministry path-label polish (display only).

---

## 14. Architecture Decisions Locked for 1B

The product owner reviewed `MINISTRY-STRUCTURE.1A` and accepted the recommended
architecture. The decisions below are **locked** for `MINISTRY-STRUCTURE.1B` and
later slices. They are no longer open.

1. **Upgrade `MinistryTeam` in place — LOCKED.** Existing `MinistryTeam` is
   upgraded into the ministry-structure unit. **Do not** create a separate
   parallel `MinistryStructureUnit` table. Existing `MinistryTeam` rows remain
   the canonical ministry unit rows. *Rationale:* the serving objects already FK
   `MinistryTeam`, so a parallel table would force dual-pointing or a mass
   re-target for no benefit (Sections 0, 2, 4).
2. **Keep both `team_kind` and `is_assignable` — LOCKED.** `team_kind` is
   descriptive taxonomy for structure display and default suggestions;
   `is_assignable` is the authoritative behavior gate for whether a team may be
   selected for `TeamAssignment`. Existing teams default to `team_kind=team`,
   `is_assignable=True`; new container/area units may use
   `team_kind=ministry_area`, `is_assignable=False` (Section 6).
3. **Parent link shape — LOCKED.** Use a dedicated `MinistryTeamParentLink` with
   explicit nullable FKs `parent_team` (→ `MinistryTeam`) and `parent_church_unit`
   (→ `ChurchStructureUnit`), enforcing exactly one parent target via check
   constraint. **Do not** use `GenericForeignKey`. Support multiple parents and
   at most one active primary display parent per child (Section 5).
4. **Role-assignment history — LOCKED.** `MinistryTeamRoleAssignment` uses
   `is_active` plus `start_date` / `end_date`, mirroring
   `ChurchStructureUnitRoleAssignment`. Multiple active Leads are allowed; only
   invalid overlapping duplicate assignments for the same user/team/role are
   prevented (Section 7.4).
5. **Default required-role direction — LOCKED.** Every active ministry role
   profile can require at least one active `lead`. Missing required roles are
   setup warnings / readiness signals only; they must **not** hard block team
   creation, parent-link creation, assignment creation, or scheduling (Section
   7). Whether technical roles are required vs optional for `technical_team` is a
   preset-content choice deferred to the seed slice (`MINISTRY-STRUCTURE.1E`) and
   does not affect the foundation model.
6. **Shared-vs-separate guideline — LOCKED.** Same people / same leadership /
   same responsibility / same assignment pool → one shared `MinistryTeam` with
   multiple parent anchors. Separate members / separate leads / separate
   assignments / separate responsibilities → separate `MinistryTeam` rows
   (Section 11).
7. **Capability direction — LOCKED.** Future ministry-structure management uses a
   new `CAP_MANAGE_MINISTRY_STRUCTURE`. **Do not** reuse
   `CAP_MANAGE_MINISTRY_TEAMS` or `CAP_MANAGE_TEAM_ASSIGNMENTS` for
   structure-level authority. Staff/superuser remain global managers by default
   (Section 10).
8. **Permission-source transition — LOCKED.** In the `MINISTRY-STRUCTURE.1B`
   foundation phase, **do not** change existing `can_manage_ministry_team`.
   Existing `TeamMembership.role` / `can_lead` remains the current permission
   source. New `MinistryTeamRoleAssignment` rows are **additive only** in the
   foundation phase and do not drive permissions. Migrating ministry permissions
   from `TeamMembership.role` to `MinistryTeamRoleAssignment` is a later,
   separately approved slice with audit/backfill (Section 8.1).

---

## 15. Stop Conditions for Implementation

Stop and re-confirm with the user before coding if any of these arise:

- A foundation-phase change would alter ServiceEvent visibility, Bible Study
  visibility, `ChurchStructureMembership`, My Units, member/care records, My
  Serving, or Today behavior.
- A change would make `MinistryTeamRoleAssignment` drive permissions or
  `is_assignable` drive assignment filtering inside the foundation phase. Per the
  locked decisions (Sections 8.1 and 6.4), those runtime changes belong to later,
  separately approved slices, not to `MINISTRY-STRUCTURE.1B`.
- A change would let a church anchor (Section 10) grant ministry management.
- A change would require a destructive migration, dual-pointing every serving
  object, or a mass re-target of `TeamMembership` / `TeamAssignment`.
- A change would auto-create any `TeamMembership`, `TeamAssignment`,
  `TeamAssignmentMember`, or `MinistryTeamRoleAssignment` from inferred data.
- A change would reintroduce legacy `SmallGroup` / `District` /
  `MinistryContext` dependency.

---

## 16. Non-Goals for `MINISTRY-STRUCTURE.1A`

- No model, migration, fixture, data mutation, view, form, template, URL, admin,
  or test change.
- No runtime behavior change of any kind.
- No staging, commit, or push.
