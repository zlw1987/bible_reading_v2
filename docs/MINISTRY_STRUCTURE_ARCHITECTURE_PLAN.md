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
`TeamMembership.role` as the runtime permission source (`can_lead` is
deprecated/reserved and grants no permission) while the new role model stays
additive in the foundation phase.

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
`can_manage_ministry_team` / `manageable_assignment_teams` (at the time of `1B`,
`TeamMembership.role` was still the runtime permission source — later switched to
`MinistryTeamRoleAssignment` in `MINISTRY-ROLE-SOURCE.1C`; `TeamMembership.can_lead`
is deprecated/reserved and grants no permission), does not enforce `is_assignable` on
`TeamAssignment`, does not change My Serving / Today / ServiceEvent / Bible Study
visibility, seeds no defaults, and backfills no hierarchy or roles. The
`CAP_MANAGE_MINISTRY_STRUCTURE` capability was intentionally **not** added to
`accounts/permissions.py` in this slice (see Section 13 / Section 10): it would
be an unused cross-app capability-registry change, so it stays documented-only
until the later delegated-management slice.

`MINISTRY-STRUCTURE.1C` implemented a read-only staff **Ministry Structure**
map (`ministry_structure_map`, `/structure/`) plus a small read-only
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

`MINISTRY-STRUCTURE.1D-A` implemented a staff-only **structure setup** UI for
team metadata and parent links (`manage_ministry_team_structure`,
`/teams/<id>/structure/`, template `ministry/manage_team_structure.html`).
It is the first edit slice and is split out from the broader `1D`. Staff/superuser
edit ministry-structure *display/organization* metadata on an existing
`MinistryTeam` (`team_kind`, `is_assignable`, `role_profile` — existing active
profiles only, none are seeded/created — and `is_active`) and manage
`MinistryTeamParentLink` rows: add a ministry-parent link, add a church-anchor
link, set the single active primary parent, and deactivate a link. Two explicit
add-link forms keep the parent target unambiguous; all link writes defer to
`MinistryTeamParentLink.full_clean()` (exactly-one-target, self-parent, cycle,
duplicate-active, single-active-primary) and surface validation errors on the
form. The first active parent link auto-becomes primary; setting a primary clears
the previous primary; deactivating the primary promotes the sole remaining active
link (or warns when none/several remain). Access is staff/superuser only and is
deliberately **not** granted by `TeamMembership.role`/`can_lead`,
`MinistryTeamRoleAssignment`, `ChurchStructureUnitRoleAssignment`, or
`ChurchStructureMembership`; a church anchor never grants access. The shared
`MinistryTeamForm` / `create_ministry_team` / `edit_ministry_team` flow is
unchanged (so structure-edit access never leaks to non-staff team managers).
Nothing here creates/updates `TeamMembership`, `TeamAssignment`,
`TeamAssignmentMember`, `ChurchStructureMembership`,
`ChurchStructureUnitRoleAssignment`, `BibleStudyMeetingRole`, or any
`MinistryTeamRoleAssignment`; `can_manage_ministry_team`, TeamAssignment
behavior, My Serving, and Today are unchanged; no hierarchy is inferred or
backfilled and no migration was generated.

`MINISTRY-STRUCTURE.1E` implemented a safe seed management command
(`seed_ministry_structure_roles`) that seeds/maintains the default ministry
**role types, role profiles, and role requirement rows** only. It is dry-run by
default and writes only when passed `--apply`; it is idempotent (create missing,
update drifted system-default labels/`sort_order`/flags, skip unchanged) and
never deletes extra custom role types/profiles/requirements. It seeds ten role
types (`lead`, `assistant_lead`, `coordinator`, `scheduler`, `trainer`,
`technical_lead`, `equipment_manager`, `member_care`, `admin`, `custom`), five
profiles (`default_ministry_unit`, `technical_team`, `worship_related_team`,
`project_team`, `custom`), and fourteen requirement rows. Only `lead` is
`is_required=True` (required for every seeded active profile); all other seeded
requirements are recommended `is_required=False` optional rows, so missing
required roles remain warnings/readiness signals only. This seeds configuration
records only: it assigns no people to roles (no `MinistryTeamRoleAssignment`),
assigns no profile to any existing team, and creates/updates no
`MinistryTeam` / `MinistryTeamParentLink` / `TeamMembership` / `TeamAssignment` /
`TeamAssignmentMember` / `ChurchStructureMembership` /
`ChurchStructureUnitRoleAssignment`. It changes no permission,
`can_manage_ministry_team`, `is_assignable` enforcement, My Serving, Today, or
visibility behavior, and generated no migration.

`MINISTRY-STRUCTURE.1D-B` implemented the staff-only **ministry role assignment**
UI as a new "Long-term Ministry Roles" section on the existing structure setup
page (`manage_ministry_team_structure`, template
`ministry/manage_team_structure.html`, form
`MinistryTeamRoleAssignmentForm`). Staff/superuser may view active and historical
`MinistryTeamRoleAssignment` rows for a team, add an assignment (role type, user,
start date, optional end date, `is_active`, non-sensitive notes), and soft
"end role" an active assignment (`is_active=False` plus an `end_date` mirroring
the church coworker deactivation convention; rows are never hard deleted). The
add form's `role_type` lists active role types only, its `user` list uses the
shared visible-identity ordering, and all writes defer to
`MinistryTeamRoleAssignment.full_clean()` so overlapping same-user/team/role
duplicates are rejected gracefully while multiple active Leads (different users)
are allowed. The page surfaces `team.missing_required_role_types()` as a warning
when the team has a role profile requiring a role with no active assignment
(clears once an active assignment covers it), shows a muted note when the team
has no role profile, and degrades to a help message (run
`seed_ministry_structure_roles` / configure role types) when no active role types
exist — it never seeds automatically. Access is staff/superuser only and is
deliberately **not** granted by `TeamMembership.role`/`can_lead`,
`MinistryTeamRoleAssignment`, `ChurchStructureUnitRoleAssignment`, or
`ChurchStructureMembership`. Role assignments stay additive/readiness only: they
drive no permission, do not change `can_manage_ministry_team`, never appear in My
Serving or Today, and create/update no `TeamMembership`, `TeamAssignment`,
`TeamAssignmentMember`, `ChurchStructureMembership`,
`ChurchStructureUnitRoleAssignment`, or `BibleStudyMeetingRole`. No migration was
generated and `seed_ministry_structure_roles --apply` was not run.

`MINISTRY-STRUCTURE.1F` implemented `is_assignable` enforcement for
`TeamAssignment` (no migration; enforcement only). A non-assignable
(container/area) ministry unit can no longer be the target of a **new active**
serving assignment: `TeamAssignment.clean()` rejects new non-cancelled
assignments on a non-assignable team (structural backstop covering forms, the
lighting import helper, and direct/programmatic saves), `TeamAssignmentForm`
drops non-assignable teams from its create choices while keeping an existing
assignment's current team selectable when editing, and the team schedule page
(`/teams/<id>/schedule/`) blocks scheduling writes for a non-assignable team
(POST rejected with a clear bilingual message; the schedule/edit/suggestion
action UI is hidden on GET while existing assignments stay read-only-visible).
Enforcement applies to **new/active** serving assignments only:
existing/historical assignments are preserved and stay editable (so staff can
view, cancel, or repair them), cancelled assignments are always allowed, and
`manageable_assignment_teams` / list / detail / My Serving are unchanged so
existing assignments on a now-non-assignable team never disappear. No permission
migration, My Serving role display, delegated ministry management,
`CAP_MANAGE_MINISTRY_STRUCTURE`, Today change, or production data cleanup was
done; `can_manage_ministry_team` and `MinistryTeamRoleAssignment`'s
non-permission status are unchanged.

`MINISTRY-STRUCTURE.1G` added a read-only **Ministry Structure readiness audit**
(`audit_ministry_structure_readiness`, logic in `ministry/structure_readiness.py`).
It inventories ministry teams (active/inactive, assignable/container, by kind)
and reports parent-link, role-profile, and `is_assignable` assignment readiness
as **blockers / warnings / info**, plus a static permission-boundary
confirmation. It is strictly read-only: it has **no `--apply`**, mutates nothing,
creates no defaults, assigns no roles, and repairs no rows. Options:
`--verbose`, `--limit N`, `--fail-on-blockers` (exits non-zero only when blocker
count > 0), `--team-id`, and `--include-inactive`. Blockers are an active
(non-cancelled, non-completed) `TeamAssignment` on a non-assignable team, more
than one active primary parent link for a team, and any active parent-link
cycle; cancelled/completed assignments on a non-assignable team are reported as
**info** (preserved by design, never blockers). It drives no permission, makes
no permission decision, never reads `ChurchStructureMembership` as serving, and
leaves My Serving and Today unchanged.

`MINISTRY-STRUCTURE.1H` added staff-facing **entry points and setup guidance**
for Ministry Structure (UI/discoverability only; no migration). The Ministry Team
detail page now shows a staff/superuser-only **Structure setup** summary card
(unit kind, assignable/container, role profile, display path, parent/primary-parent
status, and missing-required-role — including missing Lead — warnings) plus a
**Manage Structure** link to the existing staff-only `/teams/<id>/structure/`
page, and the Ministry Team list shows a staff-only per-team Manage Structure link
with compact badges (assignable/container, unanchored, no role profile, missing
Lead). The staff overview already links to the read-only `/structure/` map, and
the structure map/node rows already carry a staff-only Manage link to
`/teams/<id>/structure/`. A small read-only helper
(`build_team_structure_setup_summary` in `ministry/structure_map.py`) builds the
summary from existing model helpers. All of this is staff/superuser-gated and is
deliberately **not** granted by `TeamMembership.role`/`can_lead`,
`MinistryTeamRoleAssignment`, `ChurchStructureUnitRoleAssignment`, or
`ChurchStructureMembership`. It only improves discoverability/guidance: actual
structure editing stays on the staff-only `/teams/<id>/structure/` page, no
permission/`can_manage_ministry_team` behavior changed, structure fields were not
added to `MinistryTeamForm`, no delegated ministry management was added, and My
Serving / Today / TeamAssignment / ServiceEvent / Bible Study behavior is
unchanged. GET requests create/update/delete no rows.

Post-`1H` Ministry Teams / Ministry Structure UI polish and navbar IA cleanup are
complete. The Ministry Team list (`/teams/`) gained search / kind / assignable /
active filters plus readiness checkboxes (missing required role, missing role
profile, unanchored), the `/teams/` ↔ `/structure/` relationship was made
clearer, and the Lighting Pilot Import was retired from the normal discoverable
UI (its route/view/service/command remain available). The authenticated navbar
was reorganized so primary nav keeps the main user workflows while staff/admin
and account functions are grouped into caret dropdowns, and the staff menu has a
Structure Setup / 结构设置 section linking both Church Structure and Ministry
Structure. The Ministry Structure setup foundation is complete enough for the
current product stage.

Manual QA passed across desktop ordinary user, desktop staff user, the mobile
hamburger drawer, the Staff dropdown, the account dropdown, the Today / My
Serving / Bible Study serving core flows, and the Ministry Teams / Ministry
Structure core flows. This polish/IA work changed no product boundary: Today
stays a general dashboard, My Serving stays the serving workspace,
`ChurchStructureMembership` / audience scope still does not imply serving, only
explicit `TeamAssignmentMember` and linked-user `BibleStudyMeetingRole.user`
personalize serving, and `MinistryTeamRoleAssignment` is not weekly/event serving
and is not shown as personal serving; after `MINISTRY-ROLE-SOURCE.1C`, active
lead/coordinator role assignments are the runtime team-management permission
source.

Role-profile setup UI, missing-role bulk repair, delegated ancestor ministry
management, the `CAP_MANAGE_MINISTRY_STRUCTURE` capability, and My Serving
exposure of ministry role assignments remain deferred to later, separately
approved slices; the exact-team permission read switch to
`MinistryTeamRoleAssignment` is complete in `MINISTRY-ROLE-SOURCE.1C`.

Runtime behavior changes: the exact-team permission read switch to
`MinistryTeamRoleAssignment` is complete in `MINISTRY-ROLE-SOURCE.1C`; delegated
ancestor ministry management and the new `CAP_MANAGE_MINISTRY_STRUCTURE`
capability remain deferred to later, separately approved slices. `is_assignable`
enforcement landed in `MINISTRY-STRUCTURE.1F`.

`MINISTRY-ROLE-SOURCE.1A` (docs + read-only audit) locked the long-term
source-of-truth boundary between `TeamMembership` and `MinistryTeamRoleAssignment`
and added a read-only drift audit (`audit_ministry_role_source_alignment`, logic
in `ministry/role_source_alignment.py`). The locked direction:
`TeamMembership` stays the membership / candidate pool; `MinistryTeamRoleAssignment`
becomes the single source of truth for long-term ministry roles and the
team-management permission source; `TeamAssignmentMember` stays event-specific
serving; and `TeamMembership.role` / `can_lead` remain transitional/legacy fields.
`1A` itself changed no permission, mutated no data, switched no source of truth,
ran no backfill, and added no migration.

**`MINISTRY-ROLE-SOURCE.1B` and `1C` are implemented.** `1B` shipped the
dry-run-by-default backfill (`backfill_ministry_role_assignments_from_memberships`)
that creates missing `MinistryTeamRoleAssignment` rows from active user-linked
`TeamMembership.role` in {`lead`, `coordinator`}. `1C` switched the permission
read: `can_manage_ministry_team`, `manageable_assignment_teams`, and related
team-management / team-scheduling checks now read active
`MinistryTeamRoleAssignment` rows (role_type code in {`lead`, `coordinator`}) for
the exact team, not `TeamMembership.role`. After `1C`, `TeamMembership.role` is
legacy compatibility data only and grants no runtime team-management permission;
`TeamMembership.can_lead` remains deprecated/reserved and grants none. `1C` is
exact-team only (no ancestor ministry teams, church-structure anchors,
`ChurchStructureMembership`, or `ChurchStructureUnitRoleAssignment`; no
`CAP_MANAGE_MINISTRY_STRUCTURE` wiring; staff / superuser / global capability
behavior unchanged; no model or migration change). See
`docs/MINISTRY_ROLE_SOURCE_OF_TRUTH_PLAN.md` for the full plan (1A docs/audit,
1A-FU1 assignable/container clarification, 1B backfill, 1C permission read switch,
1D manage-members UI cleanup, later optional field retirement).

`MINISTRY-ROLE-SOURCE.1A-FU1` (docs + read-only audit) clarified that
**assignable** teams (`is_assignable=True`) expect management-role holders to
also be active `TeamMembership` rows (the team has a concrete schedulable member
pool), while **container** teams (`is_assignable=False`) do not — a
`MinistryTeamRoleAssignment` may name a long-term leader on a container team
without a membership row. `is_assignable=True` means the team is eligible as a
ServiceEvent required-team / `TeamAssignment` target for **any event type** (not
Sunday-only), which is why it needs a real candidate pool; `is_assignable=False`
is structure/container only and is not a direct `TeamAssignment` target. The
alignment audit reflects this: `management_role_assignment_without_membership` is
a warning only for assignable teams, and container teams use the allowed info
counter `container_management_role_assignment_without_membership`. No permission,
source-of-truth, or `is_assignable` enforcement behavior changed.

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

2. **The biggest existing-system tension is the meaning of "Lead."**
   Historically `ministry/permissions.py::can_manage_ministry_team` derived
   lead/coordinator authority from `TeamMembership.role` in {`lead`,
   `coordinator`}; `TeamMembership.can_lead` is deprecated/reserved and grants no
   permission. The `MinistryTeamRoleAssignment(lead)` model introduced a *second*
   source of "Lead," and these must not silently diverge. Resolved path
   (Section 8): the role-assignment model was additive and drove no permission in
   the foundation phase; **`MINISTRY-ROLE-SOURCE.1C` then migrated
   `can_manage_ministry_team` / `manageable_assignment_teams` to read active
   `MinistryTeamRoleAssignment` rows (role code in {`lead`, `coordinator`},
   exact team) instead of `TeamMembership.role`.**

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
| `TeamMembership` | Member/candidate pool for a team; `role` member/lead/coordinator; `can_lead` | **Unchanged in scope.** Remains the ordinary member/candidate pool. After `MINISTRY-ROLE-SOURCE.1C` its `role` field no longer grants runtime team-management permission (that reads `MinistryTeamRoleAssignment`); `role` / `can_lead` are legacy compatibility data (Section 8). |
| `TeamAssignment` | A `ServiceEvent` needs a specific team | **Unchanged.** Later gains an `is_assignable` validation guard (Section 6). |
| `TeamAssignmentMember` | Specific people assigned to that event/team | **Unchanged.** |
| `ministry/permissions.py` | `can_manage_ministry_team` historically inferred lead from `TeamMembership.role` | **Migrated in `MINISTRY-ROLE-SOURCE.1C`:** now reads active `MinistryTeamRoleAssignment` rows (role code in {`lead`, `coordinator`}, exact team). |
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

### 6.4 Assignment-time guard (IMPLEMENTED — `MINISTRY-STRUCTURE.1F`)

Implemented in `MINISTRY-STRUCTURE.1F`. `TeamAssignment.clean()` now rejects a
**new active** (non-cancelled) assignment whose `ministry_team.is_assignable` is
`False` (the structural backstop, guarded by `self._state.adding` so existing
rows stay editable). `TeamAssignmentForm` excludes non-assignable teams from its
create choices, keeps an existing assignment's current team selectable when
editing (so staff can view/cancel/repair it), and rejects moving onto a
different non-assignable team or reactivating a cancelled assignment onto a
non-assignable team. The team schedule page blocks scheduling writes for a
non-assignable team (POST rejected with a clear bilingual message; the
schedule/edit/suggestion UI hidden on GET) while leaving existing assignments
read-only-visible. The lighting import helper fails the row closed rather than
creating an assignment for a non-assignable reused team. To avoid hiding
history, `manageable_assignment_teams` itself is **not** filtered (it still backs
list/detail/My Serving visibility); only the create/schedule write paths are
gated. Enforcement applies to **new/active** assignments only; existing,
historical, and cancelled assignments are preserved. No DB constraint was added
and no migration was generated.

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

### 8.1 The "two sources of Lead" tension (key decision — resolved)

Historically, `ministry/permissions.py::can_manage_ministry_team` treated a user
as a team manager if they held an active `TeamMembership` with
`role in {lead, coordinator}`. The `MinistryTeamRoleAssignment(role_type=lead)`
model introduced a second, more explicit "Lead" concept.

If both drove permissions, they could silently disagree (someone is
`TeamMembership.role=lead` but has no role assignment, or vice versa). The
resolution:

- **Foundation phase:** `MinistryTeamRoleAssignment` was **additive only** and
  drove no permission; `can_manage_ministry_team` kept reading
  `TeamMembership.role`.
- **`MINISTRY-ROLE-SOURCE.1B` / `1C` (implemented):** `1B` backfilled role
  assignments from existing active `lead`/`coordinator` memberships (dry-run
  audit first), then `1C` switched the read — `can_manage_ministry_team` and
  `manageable_assignment_teams` now resolve team-management authority from active
  `MinistryTeamRoleAssignment` rows (role code in {`lead`, `coordinator`}, exact
  team). This mirrors how church-structure migrations retired inferred authority
  in favor of explicit assignment rows.

After `1C`, `MinistryTeamRoleAssignment` is the runtime team-management permission
source; `TeamMembership.role` / `can_lead` remain as legacy compatibility data and
grant no runtime team-management permission. Whether `TeamMembership.role`'s
lead/coordinator values are eventually removed is settled inside a later,
separately approved field-retirement slice, not here.

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
  `/structure/`, template `ministry/structure_map.html` + node partials,
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
  missing-required-role warnings. Split into sub-slices:
  - **`MINISTRY-STRUCTURE.1D-A` — team metadata + parent links (IMPLEMENTED):**
    staff/superuser-only setup page per team (`manage_ministry_team_structure`,
    `/teams/<id>/structure/`, template
    `ministry/manage_team_structure.html`). Edits structure metadata
    (`team_kind`, `is_assignable`, `role_profile` from existing active profiles
    only, `is_active`) via `MinistryTeamStructureForm`, and manages
    `MinistryTeamParentLink` rows (add ministry-parent / church-anchor link, set
    primary, deactivate) via two explicit add-link forms
    (`MinistryTeamParentTeamLinkForm` / `MinistryTeamChurchAnchorLinkForm`) that
    defer to `MinistryTeamParentLink.full_clean()`. First active link
    auto-primary; set-primary clears the prior primary; deactivating the primary
    promotes a sole remaining link or warns. Staff/superuser-only (not granted by
    `TeamMembership.role`, `MinistryTeamRoleAssignment`,
    `ChurchStructureUnitRoleAssignment`, `ChurchStructureMembership`, or church
    anchors). The shared create/edit ministry-team form is unchanged. No role
    assignments, role-type/profile/requirement seeds, role-profile setup UI,
    missing-role bulk repair, delegated management,
    `CAP_MANAGE_MINISTRY_STRUCTURE` / permission migration, or `is_assignable`
    enforcement; no membership/serving/assignment writes, no inferred hierarchy,
    no migration.
  - **`MINISTRY-STRUCTURE.1D-B` — staff ministry role assignment UI
    (IMPLEMENTED):** a "Long-term Ministry Roles" section on the staff-only
    structure setup page (`manage_ministry_team_structure`, template
    `ministry/manage_team_structure.html`, form
    `MinistryTeamRoleAssignmentForm`). Staff/superuser view active + historical
    `MinistryTeamRoleAssignment` rows, add an assignment (`role_type`, `user`,
    `start_date`, optional `end_date`, `is_active`, non-sensitive `notes`), and
    soft-deactivate ("end role") an active assignment (`is_active=False` + an
    `end_date`; never hard deleted). Add-form `role_type` lists active types
    only; writes defer to `MinistryTeamRoleAssignment.full_clean()` (overlapping
    same user/team/role rejected; multiple active Leads for different users
    allowed). Surfaces `missing_required_role_types()` as a warning (clears once
    covered), a muted note when no role profile is set, and a help message when
    no active role types exist (no auto-seed). Staff/superuser-only access (not
    granted by `TeamMembership.role`/`can_lead`, `MinistryTeamRoleAssignment`,
    `ChurchStructureUnitRoleAssignment`, or `ChurchStructureMembership`). Role
    assignments are explicit and staff-managed: no permission migration, no My
    Serving / Today exposure, no `can_manage_ministry_team` change, and no
    `TeamMembership` / `TeamAssignment` / `TeamAssignmentMember` /
    `ChurchStructureMembership` / `ChurchStructureUnitRoleAssignment` /
    `BibleStudyMeetingRole` side effects. No migration; no seed apply.
  - Role-profile setup UI, missing-role bulk repair, delegated ministry
    management, the `CAP_MANAGE_MINISTRY_STRUCTURE` capability, and
    `is_assignable` enforcement remain deferred to separately approved slices; the
    exact-team permission read switch to `MinistryTeamRoleAssignment` is complete
    in `MINISTRY-ROLE-SOURCE.1C`.
- **`MINISTRY-STRUCTURE.1E` — seed defaults (IMPLEMENTED):** the
  `seed_ministry_structure_roles` management command seeds/maintains the default
  ministry role types, role profiles, and requirement rows only. Dry-run by
  default; writes only on explicit `--apply`; idempotent (create / update
  drifted system-default labels, `sort_order`, and flags / skip unchanged) and
  non-destructive (never deletes extra custom role types/profiles/requirements).
  Seeds ten role types, five profiles, and fourteen requirement rows; only
  `lead` is `is_required=True` for every seeded profile, all other seeded
  requirements are recommended optional (`is_required=False`). Seeds
  configuration records only: it assigns no people to roles (no
  `MinistryTeamRoleAssignment`), does not assign a profile to any existing team,
  and creates/updates no `MinistryTeam` / `MinistryTeamParentLink` /
  `TeamMembership` / `TeamAssignment` / `TeamAssignmentMember` /
  `ChurchStructureMembership` / `ChurchStructureUnitRoleAssignment`. No
  permission, `can_manage_ministry_team`, `is_assignable` enforcement, My
  Serving, Today, or visibility change; no migration. Role assignment UI,
  role-profile setup UI, delegated ministry management, the
  `CAP_MANAGE_MINISTRY_STRUCTURE` capability, and `is_assignable` enforcement
  remain deferred; the exact-team permission read switch to
  `MinistryTeamRoleAssignment` is complete in `MINISTRY-ROLE-SOURCE.1C`.
- **`MINISTRY-STRUCTURE.1F` — `is_assignable` enforcement (IMPLEMENTED):** the
  first behavior slice after the additive foundation. `TeamAssignment.clean()`
  rejects new active (non-cancelled) assignments on a non-assignable team (model
  backstop, guarded by `self._state.adding`); `TeamAssignmentForm` excludes
  non-assignable teams from create choices, preserves an existing assignment's
  current team when editing, and rejects moving/reactivating onto a
  non-assignable team; the team schedule page blocks scheduling writes for a
  non-assignable team (bilingual message; read-only on GET); the lighting import
  helper fails such rows closed. Existing/historical/cancelled assignments are
  preserved and stay viewable in list/detail/My Serving (no
  `manageable_assignment_teams` narrowing). No permission, `can_manage_ministry_team`,
  My Serving role display, Today, or production-data change; no migration.
- **`MINISTRY-STRUCTURE.1G` — readiness audit (IMPLEMENTED):** a read-only
  `audit_ministry_structure_readiness` management command (logic in
  `ministry/structure_readiness.py`). It inventories ministry teams and reports
  parent-link, role-profile, and `is_assignable` assignment readiness as
  blockers / warnings / info, plus a static permission-boundary confirmation.
  Strictly read-only: **no `--apply`**, no data mutation, no defaults seeded, no
  roles assigned, no rows repaired. Options `--verbose`, `--limit N`,
  `--fail-on-blockers` (non-zero exit only when blocker count > 0), `--team-id`,
  `--include-inactive`. Blockers are an active (non-cancelled, non-completed)
  `TeamAssignment` on a non-assignable team, multiple active primary parent links
  for one team, and active parent-link cycles; cancelled/completed assignments on
  a non-assignable team are info (preserved by design). No permission, My
  Serving, or Today change; no migration. Role-profile setup UI, missing-role
  bulk repair, delegated ministry management, the `CAP_MANAGE_MINISTRY_STRUCTURE`
  capability, and My Serving exposure of ministry roles remain deferred; the
  exact-team permission read switch to `MinistryTeamRoleAssignment` is complete in
  `MINISTRY-ROLE-SOURCE.1C`.
- **`MINISTRY-STRUCTURE.1H` — staff structure entry points + setup guidance
  (IMPLEMENTED):** a UI/discoverability slice (no migration, no new behavior).
  The Ministry Team detail page gains a staff/superuser-only **Structure setup**
  summary card (unit kind, assignable/container, role profile, display path,
  parent/primary-parent status, missing-required-role / missing-Lead warnings)
  and a **Manage Structure** link; the Ministry Team list gains a staff-only
  per-team Manage Structure link with compact badges (assignable/container,
  unanchored, no role profile, missing Lead); the staff overview link to the
  read-only `/structure/` map and the structure map/node Manage links to
  `/teams/<id>/structure/` are confirmed present (no duplicates added). A small
  read-only `build_team_structure_setup_summary` helper
  (`ministry/structure_map.py`) builds the summary. Staff/superuser-gated and
  never granted by `TeamMembership.role`/`can_lead`,
  `MinistryTeamRoleAssignment`, `ChurchStructureUnitRoleAssignment`, or
  `ChurchStructureMembership`. Improves discoverability/guidance only: structure
  editing stays on staff-only `/teams/<id>/structure/`; no permission /
  `can_manage_ministry_team` change, no structure fields added to
  `MinistryTeamForm`, no delegated management, no `CAP_MANAGE_MINISTRY_STRUCTURE`
  wiring; My Serving / Today / TeamAssignment / ServiceEvent / Bible Study
  unchanged; GET creates no rows.
- **Done (separate approval):**
  - Permission migration from `TeamMembership.role` to
    `MinistryTeamRoleAssignment` — implemented in `MINISTRY-ROLE-SOURCE.1C`
    (Section 8.1).
- **Later (separate approvals):**
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
8. **Permission-source transition — LOCKED (now completed).** In the
   `MINISTRY-STRUCTURE.1B` foundation phase, `can_manage_ministry_team` was left
   unchanged and `MinistryTeamRoleAssignment` rows were additive only. The
   migration then happened in its own approved slices:
   `MINISTRY-ROLE-SOURCE.1B` backfilled role assignments from active
   `lead`/`coordinator` memberships, and **`MINISTRY-ROLE-SOURCE.1C` switched
   `can_manage_ministry_team` / `manageable_assignment_teams` to read active
   `MinistryTeamRoleAssignment` rows** (role code in {`lead`, `coordinator`},
   exact team). After `1C`, `TeamMembership.role` is legacy compatibility data and
   no longer the runtime team-management permission source;
   `TeamMembership.can_lead` remains deprecated/reserved and grants no permission
   (Section 8.1).

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
