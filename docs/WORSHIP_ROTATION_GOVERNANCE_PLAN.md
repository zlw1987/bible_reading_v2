# Multi-Campus Worship Rotation Governance Plan

Status: canonical governance decisions through `MO-S.6D-0A-FU2`, plus
implemented `MO-S.6D-1A` Campus / Site type foundation and `MO-S.6D-1B`
Worship rotation-pool configuration foundation, and implemented `MO-S.6D-1C`
ServiceEvent planner/coordinator responsibility foundation, plus implemented
`MO-S.6D-1D-A` read-only event applicability, candidate, and ownership-
consistency domain foundation, plus implemented `MO-S.6D-1D-B` governed
authorization, mutation enforcement, and narrow Worship Planning UI, with
`MO-S.6D-1D-B-FU1` identity and structural-ordering closure, plus
implemented `MO-S.6D-1D-C` Worship Team operational reachability with FU1/FU2
projection-consistency closure, plus the docs-only `MO-S.6D-1D-D-0A`
Worship Rotation Planner batch contract and implemented read-only proposal/
preview `MO-S.6D-1D-D-1A`, plus implemented `MO-S.6D-1D-D-1A-FU1`
cycle-closed tail refinement, plus the docs-only `MO-S.6D-1D-D-1B-A0`
SQLite optimistic scheduling-concurrency decision, plus implemented
`MO-S.6D-1D-D-1B-A1` Scheduling Revision Foundation, plus implemented
`MO-S.6D-1D-D-1B-B` optimistic batch confirmation/shared audit, plus the
docs-only `NOTIFY.1G-0A` Direct Worship Team Change Notification Contract, plus
implemented `NOTIFY.1G` runtime, plus implemented
`MO-S.6D-PROFILE.1A` stable ServiceEvent profile identity foundation.
The separate `MO-S.6D-PROFILE-SETUP.0A` read-only readiness audit is committed
in current HEAD and its production run has been reviewed. Production schema was
ready through `events/0011`, but the audit was not setup-ready: zero canonical
rows/ready matches across 52 expected Sundays, seven single candidates, 45
missing 09:30 candidates, and no multiple/other-profile ambiguity. The seven
candidates were IDs 38-44 from `2026-08-16` through `2026-09-27`; product-owner
review confirmed their Bethany 09:30 Chinese Worship resemblance and declared
the current scheduling dataset disposable TEST DATA for reset rather than
in-place tagging.
`MO-S.6D-PROFILE-SETUP.1A` is **PRODUCTION APPLY COMPLETE / VERIFIED**. The
product-owner-reviewed reset created exactly 52 canonical 2026 Bethany 09:30
`bethany_0930_cm` ServiceEvents with exact CM audience, and the post-reset
production audit returned `PROFILE SETUP READY`. `MO-S.6D-SLICE8.1A/FU1/UX1` now
implements the strict dependency/parser, bounded OOXML ZIP preflight, and
staff/superuser-only zero-write preview with blocked partial mappings and a
wider operational matrix. Its production read-only smoke passed on GoDaddy
Python 3.11.15 with openpyxl 3.1.5. Docs/read-only
`MO-S.6D-SLICE9.0A` now freezes the separate Excel confirmation-write contract
and repository audit. `MO-S.6D-SLICE9.1A` is **PRODUCTION APPLY COMPLETE / VERIFIED**
with a distinct signed proposal, exact 52-target CAS/revalidation boundary,
changed-anchor-only writes, and changed-only shared audit. The product-owner-
reviewed production confirmation is complete. A fresh re-upload of the same
workbook produced 52 no-op rows, 0 proposed changes, 0 blocked rows, and no
confirmation action.
Governance FU2 finalizes the required
event-planner
prerequisite and Worship-specific pool semantics. The Campus, pool-
configuration, event-responsibility, read-only governance, governed single-
event mutation, operational-reachability, planner-confirmation, annual-workbook
confirmation, and the bounded direct-change notification runtime are
implemented; assignment import and any broader later notification expansion
below require separate explicit approval.

[`GENERIC_DEPLOYMENT_CONFIGURATION_ARCHITECTURE.md`](GENERIC_DEPLOYMENT_CONFIGURATION_ARCHITECTURE.md)
freezes the adjacent generic boundary. Service-profile defaults may name only
explicit static assignable teams; the governed selected Worship Team remains
dynamic event state and is never persisted as a static default. Named workbook
adapters must be explicitly enabled per deployment. These proposals remain
runtime unimplemented.

## 1. Problem and decisions owned here

Sunday Worship has two separate decisions:

1. **Event-level rotation selection:** an authorized planner or the active
   Lead/Coordinator of an applicable larger Worship ministry selects the exact
   assignable team that owns this event. `ServiceEvent.rotation_anchor_team`
   represents this decision.
2. **Exact-team roster scheduling:** the selected team's own Lead/Coordinator
   selects that team's serving members through `TeamAssignment` and
   `TeamAssignmentMember`.

These responsibilities must not collapse. A larger ministry-container Lead
does not inherit roster authority over descendants. A child-team Lead does not
gain authority over peer rotation selection. Audience, structure, membership,
serving, and management remain separate axes.

This plan closes the architecture decisions needed before the narrow
rotation-edit path or the MO-S.6D Excel importer can be approved. It now
records the implemented semantic Campus/Site, Worship pool-configuration,
exact-event planner/coordinator responsibility, and read-only event
applicability/candidate/consistency foundations. The separately implemented
`MO-S.6D-1D-B` slice adds the narrow rotation-selection permission,
selector/mutation UI, and supported-write enforcement described below.
`MO-S.6D-1D-C` separately adds selected-team operational reachability without
an Excel dependency or importer.

## 2. Current repository truth

The current code provides:

- a flexible `ChurchStructureUnit.parent` tree with a 32-character choice
  field for semantic unit type;
- `ChurchStructureUnit.UNIT_CAMPUS = "campus"` as the semantic-only Campus /
  Site organizational type implemented by `MO-S.6D-1A`;
- app-specific audience rows, including `ServiceEventAudienceScope`;
- ordinary ServiceEvent audience matching through one active primary
  `ChurchStructureMembership`, with zero-row events failing closed;
- `ServiceEvent.host_language_unit` as display-only context;
- `MinistryTeam` hierarchy through `MinistryTeamParentLink`, including multiple
  active parents and at most one active primary display path;
- `MinistryTeam.team_kind` as descriptive taxonomy only;
- `MinistryTeam.is_assignable` as the behavioral gate for new active
  `TeamAssignment` targets;
- `MinistryTeam.is_worship_rotation_pool` as explicit configuration metadata
  for a non-assignable Worship ministry container, exposed on the existing
  bilingual staff Ministry Structure setup page;
- a read-only `inspect_worship_rotation_pool()` resolver that follows only the
  active primary Ministry Structure path, fails closed on inactive/missing/
  ambiguous/cyclic/broken configuration, and reports canonical exact-team
  Lead/Coordinator readiness without authorizing a user or inspecting an event;
- Ministry Structure readiness integration: unusable active pool structure is
  a blocker, missing active date-valid Lead/Coordinator is a warning, and an
  inactive configured pool is retained informational state;
- exact-team Lead/Coordinator management authority through active, date-valid
  `MinistryTeamRoleAssignment` rows;
- nullable `ServiceEvent.rotation_anchor_team`, now presented as the selected
  Worship Team and editable only through the governed exact-event selector;
- Team Schedule and Sunday Board event reachability through required-team,
  current operational-assignment, or exact valid eligible selected-Worship-Team
  participation; the third predicate remains reachability only; and
- `ServiceEvent.created_by` plus `created_at` / `updated_at`, and the explicit
  `ServiceEventPlannerAssignment` responsibility foundation implemented by
  `MO-S.6D-1C`; each event/user pair has one lifecycle row with `is_active`,
  non-sensitive notes, and timestamps, while `created_by` remains attribution;
- a side-effect-free `current_service_event_planner_assignments(event)` lookup
  that returns only active rows linked to active users for that exact event;
  planner rows are managed only by existing full ServiceEvent managers on the
  existing bilingual event-edit surface; the `MO-S.6D-1C` responsibility
  foundation grants nothing by itself, while `MO-S.6D-1D-B` now consumes a
  current row only for the narrow applicable event's Worship Team action;
- a side-effect-free `ministry.services.worship_governance` domain service that
  resolves valid applicable pools from active event audience rows, active
  assignable candidates from deterministic active primary Ministry paths, and
  current Worship ownership consistency across scheduled / confirmed /
  prepared assignments; it accepts no user, exposes no roster/private fields,
  writes nothing, and grants no authority; and
- no `updated_by` field.

The current code declares `openpyxl==3.1.5` and provides the bounded Slice 8
annual-workbook parser/upload/preview. Counts are derived from present allowed
tokens, incomplete mappings and business blockers remain previewable, and an
OOXML ZIP preflight rejects encrypted or excessive archives before openpyxl.
The annual workbook flow now includes the Slice 9 staff/superuser confirmation
endpoint and selected-team write runtime, and that confirmation is production-
applied and verified. It still provides no durable `ImportRun` schema and no
`TeamAssignment`/`TeamAssignmentMember` import.

`created_by` is creation attribution, not durable planner responsibility or
runtime authority. `MinistryTeamParentLink.parent_church_unit` is a display/
organization anchor and an input to implemented `MO-S.6D-1D-A` Worship event/
pool applicability; the link alone still grants no authority.

## 3. Church Structure type semantics

`unit_type` is semantic classification layered over one generic tree. Most
hierarchy and audience behavior follows `parent`, not a fixed type matrix.

| Type | Intended purpose | Current stronger behavior | Generic behavior and boundaries |
| --- | --- | --- | --- |
| `root` | Whole Church / the top organizational audience | A root cannot have a parent; child creation excludes `root`; setup prevents enabling a second active root; a selected root audience matches every authenticated user and is exclusive of lower audience selections | It creates no membership, role, serving row, or permission. |
| `campus` | A semantic Campus / Site organizational node | No Campus-specific permission, membership, audience row, serving, role profile, MinistryTeam, or Host / Language grant is implemented; signup/profile and small-group-only consumers keep their existing type-specific exclusions | It participates in the generic parent tree and may participate in generic audience ancestry. A Campus Bible Study scope resolves only active descendant `small_group` leaves through existing generic ancestry, never the Campus itself. |
| `ministry_context` | Congregation, language, or ministry context such as CM/EM | The ServiceEvent Host / Language admin picker accepts only this type; display fallback walks audience ancestry to the nearest such unit | It remains display context when used by `host_language_unit`; as an audience row it uses the same subtree matching as other non-root units. |
| `district` | A district-like organizational branch | `ChurchRoleAssignment` district-scoped validation rejects a `small_group` unit but otherwise permits a broader non-small-group structure scope; group-progress access then filters to descendant small-group units | The type alone grants nothing. Audience and Bible Study schedule selection use generic ancestry. |
| `small_group` | The canonical group-level belonging and normal Bible Study generation leaf | Small-group member management, ordinary own-group progress, prayer/reflection group snapshots, and normal Bible Study generation explicitly require this type | A selected ancestor of small groups can still be an audience or Bible Study schedule scope; choosing this type does not auto-create membership or a meeting. |
| `fellowship` | A fellowship-level or locally named group/branch | Signup/Profile request selection currently offers active `fellowship` and `small_group` units; the delegated My Units member-maintenance workflow remains small-group-only | A fellowship audience uses generic subtree matching. A fellowship selected for Bible Study generation yields only active descendant `small_group` targets, not the fellowship row itself. |
| `department` | A church organizational department | No department-specific audience, membership, permission, or serving rule is implemented | It is mostly semantic metadata. It can participate in generic ancestry, audience, explicit role assignment, and an explicitly selected role profile. |
| `custom` | A flexible local classification when the predefined labels do not fit | No custom-specific runtime rule is implemented | It is mostly semantic metadata and participates in the generic tree and consumer-specific audience/role rules. |

Additional current rules:

- Any active unit may be selected by the generic ServiceEvent audience picker;
  audience matching covers that unit's subtree. Unit type does not grant
  audience membership.
- `ChurchStructureMembership` can technically point to an active unit without
  a model-level type gate, while the ordinary signup and small-group-management
  flows apply their narrower type policies.
- `ChurchStructureUnitRoleProfile` is explicitly selected and drives readiness
  warnings only. It is not inferred from unit type and grants nothing.
- `ChurchStructureUnitRoleAssignment` and `ChurchRoleAssignment` are explicit
  responsibility/permission rows. A unit type by itself is never a role.
- Bible Study audience visibility accepts any structure level. Normal meeting
  generation separately resolves only active descendant/self `small_group`
  units.
- Creating or editing a structure unit changes only structure metadata. The
  current add-child and rename paths do not create or rewrite memberships,
  ServiceEvent or Bible Study audience rows, role assignments, serving rows, or
  management authority. Moving/reparenting remains outside the narrow setup UI.

The binding boundaries are:

```text
ChurchStructureUnit != ChurchStructureMembership
ChurchStructureUnit != audience row
ChurchStructureUnit != permission or role assignment
ChurchStructureUnit != serving
ChurchStructureUnit != MinistryTeam
```

## 4. Campus / Site decision

The first-class choice is implemented:

```text
UNIT_CAMPUS = "campus"
Campus / Site
堂点
```

This is safer and clearer than misclassifying Main Campus / 母堂 as a
`ministry_context`. The stored value fits the existing `max_length=32`; the
generic parent tree, path helpers, audience selectors, and descendant matching
do not assume the current choices are exhaustive.

The implemented Campus slice is semantic only:

- no rigid parent-child type matrix;
- no required CM/EM children;
- no special permission, role, membership, audience, or serving grant;
- no automatic role profile;
- no automatic Host / Language meaning; and
- no automatic MinistryTeam anchor or pool configuration.

Implemented effects of the choice:

- Django model state requires an `AlterField` migration because choices change,
  although no data rewrite or database column expansion is expected.
- Django Admin and the staff add-child form derive Campus from
  `UNIT_TYPE_CHOICES`; the staff add-child control presents `Campus / Site` in
  English and `堂点` in Chinese, while root exclusion remains intact.
- A Campus audience includes memberships in descendant branches through the
  existing generic ancestry rule.
- A Bible Study schedule scoped to Campus resolves any active descendant
  `small_group` leaves without new generation logic.
- Campus remains excluded from the Host / Language picker, signup request
  picker, small-group member-management path, and small-group-only
  prayer/reflection/progress logic.
- An explicit role assignment may deliberately use a Campus as its structure
  scope under existing rules; that authority comes from the role assignment,
  never from the Campus type. The Campus slice must not widen or redesign
  `ChurchRoleAssignment.scope_type`.

Targeted tests should cover model/form/admin choice availability, flexible
parents and children, audience ancestry, Bible Study descendant-small-group
resolution, Host / Language exclusion, no automatic role profile, and no
creation of membership/audience/role/serving rows.

## 5. Flexible multi-campus contract

The canonical contract is a flexible tree, not a universal depth:

```text
Whole Church [root]
├── Main Campus [campus]
│   ├── Chinese Ministry [ministry_context]
│   └── English Ministry [ministry_context]
└── Tri-Valley Campus [campus]
    └── Tri-Valley Ministry [ministry_context today]
```

That example is data, not schema. A Campus may have zero, one, or many ministry
contexts. A church may omit Campus entirely, use additional intermediate
`department` / `fellowship` / `custom` units, or have unequal branch depth.
Adding a later Tri-Valley CM/EM subdivision must be a data/setup change, not a
code change. No behavior may depend on SVCA names, codes, or database IDs.

## 6. Church Structure versus Ministry Structure

Church Structure owns campus/congregation/group topology, belonging, and
organizational audience. Ministry Structure owns operational ministries,
assignable teams, long-term ministry roles, and serving assignments.

A safe Worship shape is:

```text
Church Structure                         Ministry Structure
Main Campus                              Chinese Worship Ministry [container]
└── Chinese Ministry  <--- anchor -------├── Worship Team 1 [assignable]
                                         ├── Worship Team 2 [assignable]
                                         └── ...
```

The ministry hierarchy remains `MinistryTeamParentLink.parent_team`. The Church
Structure link remains an organization anchor. Under the implemented Worship
governance consumer, the anchor helps answer whether an explicitly configured
Worship pool applies to an event, but it still grants no permission. Authority requires
an explicit active Lead/Coordinator role on the configured Worship pool
**and** event applicability.

## 7. Worship rotation-pool representation

No existing field safely identifies a Worship rotation pool:

- name/code matching and database IDs are church-specific and unsafe;
- `team_kind` is explicitly descriptive only;
- `is_assignable=False` identifies many containers, not rotation ownership;
- `role_profile=worship_related_team` is readiness metadata, can be used on
  assignable teams, and is explicitly not a behavior gate;
- hierarchy identifies organization, not scheduling purpose; and
- a Church Structure anchor identifies display placement, not purpose or
  authority.

`MO-S.6D-1B` implements the V1 decision as one explicit Worship-specific
Boolean on `MinistryTeam`, named `is_worship_rotation_pool`:

```text
is_worship_rotation_pool = True
    this active non-assignable MinistryTeam container owns an eligible
    Worship Team selection pool for ServiceEvent Worship governance
```

The stored semantic remains Worship-specific. It does not mean "generic
rotation pool" or make preaching,
ushering, or another future rotation domain eligible for the ServiceEvent
Worship Team slot. If materially different rotation domains emerge from real
use, reevaluate a typed `rotation_pool_kind`, responsibility-slot model, or
other abstraction then; do not pre-abstract a generic rotation engine now.

Implemented configuration/readiness rules:

- an operational pool team is active and `is_assignable=False`; a previously
  configured inactive pool may retain the flag but is non-usable and reported
  as informational state;
- its active primary MinistryTeam parent path resolves to exactly one active
  Church Structure anchor;
- the hierarchy/path is cycle-safe and unambiguous;
- unusable active pool structure is a readiness blocker, while missing active,
  date-valid Lead/Coordinator remains a setup warning, not an implicit grant;
- the flag is configuration only and grants no authority by itself;
- the flag creates no assignment, membership, audience row, required-team row,
  serving row, or role assignment; and
- it becomes an applicability/candidate input only through the separately
  governed Worship-rotation helpers.

The implemented governance consumer uses only the active **primary** ministry
parent path and its primary Church Structure anchor. Secondary parent links
remain display-only for this purpose. This deterministic rule avoids making one
shared child silently eligible in several pools. A genuinely multi-anchor
Worship rotation pool is deferred; first represent combined services as
multiple separately configured applicable pools. Missing primary path,
multiple-primary corruption, a cycle, an inactive anchor, or an unanchored
active pool fails closed and is a setup/readiness blocker. An inactive
configured pool is non-operational informational state, not a noisy active
blocker.

Rejected alternatives are recorded in Section 16.

## 8. Audience applicability, never authority

For an event with selected audience units `A` and a configured Worship pool
with primary Church Structure anchor `W`:

```text
pool_is_applicable(event, pool) =
    event has at least one audience row
    AND pool and W are active and valid
    AND W is equal to or a descendant of at least one unit in A
```

The rule uses `ChurchStructureUnit.parent` ancestry. It does not inspect unit
names, codes, fixed depth, membership rows, `host_language_unit`, event
location, or the current anchor team.

Examples:

- Whole Church audience -> all valid descendant Campus/congregation pools may
  apply.
- Main Campus audience -> valid pools anchored in Main Campus descendants may
  apply; Tri-Valley pools do not.
- Main Chinese Ministry audience -> Chinese pool applies; Main English pool
  does not.
- Main Chinese + Main English audience -> union of both applicable pools.
- Tri-Valley Ministry audience -> its current pool applies; later subdivisions
  follow changed ancestry/configuration without code changes.

Fail-closed behavior:

- zero audience rows -> no applicable pools;
- inactive selected audience unit or inactive pool anchor -> that branch grants
  no applicability;
- inactive or non-pool MinistryTeam -> not applicable;
- unanchored pool -> not applicable;
- missing/ambiguous/cyclic primary hierarchy -> not applicable;
- multiple audience rows -> union of valid branches;
- multiple applicable pools -> intentional union, not an ambiguity; and
- `host_language_unit` and audience-derived Host / Language display fallback ->
  excluded from applicability and authority.

Audience answers where a pool is operationally relevant. It never answers who
may change the event.

## 9. Eligible rotation-anchor teams

For all applicable configured Worship pools, the selector candidate set is the
union of teams that are:

- active;
- `is_assignable=True`; and
- descendants of an applicable pool through active **primary**
  `MinistryTeamParentLink.parent_team` edges.

Use all descendants, not direct children only, so an intermediate container
does not require a schema change. Use the primary parent path only so each
candidate has one deterministic pool owner in V1. The pool container itself is
never a candidate because it must be non-assignable. A team linked to a pool
only through a secondary parent is not eligible in V1. A candidate with a
missing, inactive, ambiguous, or cyclic primary path is excluded.

No candidate may be derived from names, fuzzy matching, `team_kind`,
`role_profile`, database IDs, or existing `TeamAssignment` rows. The governed
selector uses this candidate contract; normal and recurring event forms no
longer expose the field.

### Worship ownership and assignment consistency

For the governed workflow, `rotation_anchor_team` is the event-level Worship
team selected to **own Worship for that occurrence**. "Anchor" remains a useful
internal field name, but "optional scheduling hint" is no longer the canonical
product meaning once governance is implemented.

The stronger meaning preserves the existing separations:

```text
rotation_anchor_team = event-level Worship team ownership selection
rotation_anchor_team != TeamAssignment
rotation_anchor_team != serving
rotation_anchor_team != required coverage
rotation_anchor_team != audience
rotation_anchor_team != permission
```

An audience-ready future event may have a valid selected Worship team but no
Worship `TeamAssignment` yet; that is the normal **selected but unscheduled**
state. Once a current Worship assignment exists, however, it must be for the
exact selected team:

```text
rotation_anchor_team = C1
current Worship TeamAssignment team = C1        valid

rotation_anchor_team = C1
current Worship TeamAssignment team = C2        invalid / fail closed
```

For this invariant, a "current Worship assignment" is a non-cancelled
operational assignment for the event whose team resolves through the governed
primary path to any configured Worship rotation pool. A valid current row must
also be inside this event's Section 9 eligible candidate union and equal the
selected team. This catches an assignment under an inapplicable pool as a
conflict rather than allowing it to disappear from validation.
Completed/historical and cancelled rows remain history and must not be
retagged. More than one current assignment for the selected team remains
ambiguous under the existing duplicate fail-closed rule. A current assignment
for another Worship team is a cross-team ownership conflict, even when the
selected team has no assignment.

`MO-S.6D-1D-A` now implements the shared pool-aware domain inspection in
`ministry.services.worship_governance`. It reports no selection, invalid
selection, selected-but-unscheduled, consistent, off-team, out-of-scope,
multiple-current, and duplicate-selected-team states. Assignments under a
configured but inapplicable/invalid pool remain conflicts rather than
disappearing; downstream teams whose primary path reaches no configured
Worship pool are not misclassified. Results contain only safe team/pool and
assignment identifiers, never rosters, notes, contacts, or confirmations.

`build_worship_contexts()` now consumes that same inspection for Board/Team
Schedule presentation. Selected-unscheduled remains the ordinary unscheduled
state; consistent ownership projects only the exact selected-team roster;
off-team/out-of-scope ownership becomes review-required conflict; multiple or
duplicate current ownership remains ambiguous; and invalid selection remains
unavailable. No conflict assignment object, roster, note, contact, or
confirmation detail is exposed through the Worship context. `MO-S.6D-1D-B`
consumes the same domain inspection for the governed selector and
TeamAssignment write backstop rather than inventing a second ownership
definition. This remains a cross-row/hierarchy rule and must not be represented
as a misleading simple database constraint.

### Implemented write-path closure for `MO-S.6D-1D-B`

The read-only `1D-A` audit found these existing paths. `1D-B` now governs them
without widening their present authority:

- `ServiceEventForm` through normal create/edit writes
  `rotation_anchor_team`; `RecurringServiceEventForm` plus
  `create_recurring_events()` writes the same field for every generated event;
- Django Admin exposes `ServiceEvent.rotation_anchor_team` directly;
- generic `TeamAssignmentForm` create/edit and the team-scoped
  `TeamScheduleAssignmentForm` create/edit path can create, retarget,
  reactivate, complete, or cancel an assignment;
- Django Admin exposes `TeamAssignment` and `TeamAssignmentMember` directly;
- the retained Lighting pilot import service/management command can create a
  scheduled `TeamAssignment` (currently for the Lighting team) and membership
  row; and
- dedicated assignment cancellation and member confirmation can move rows out
  of or within the current status set, while ServiceEvent cancellation cancels
  non-final assignments.

No other current management command writes `rotation_anchor_team`; no current
management command other than the retained Lighting pilot importer creates
`TeamAssignment`. `1D-B` removes the anchor from normal and recurring event
forms, makes it read-only in ServiceEvent Admin, and adds the model-level
Worship ownership guard used by generic forms, Team Schedule, Admin, direct
`save()` / known `get_or_create()` callers, and member confirmation. Safe
ServiceEvent bulk cancellation remains an intentional queryset transition out
of the current set; arbitrary raw SQL or future `QuerySet.update()` callers are
not claimed as protected and must not be introduced as Worship write paths.

### `MO-S.6D-1D-B-FU1` identity and structural-ordering closure

The supported-write backstop now treats Worship assignment identity as
immutable. If either the persisted or proposed current/historical assignment
resolves through a configured Worship pool, an existing row cannot change its
`service_event` or `team`. This applies even when the persisted row is currently
valid and consistent, and it closes both directions of the boundary: a Worship
row cannot be retargeted to another Worship or downstream team/event, and a
downstream row cannot be retargeted into Worship. Supported pure-downstream
retargeting remains unchanged. Cancellation and completion remain explicit
in-place lifecycle transitions and never rewrite assignment identity.

Supported current Worship assignment writes enter atomic code that requests
the governing `ServiceEvent` rows in deterministic ID order, then re-runs model
validation before saving. The narrow selector requests the same event first,
and member confirmation follows the structural order
`ServiceEvent -> TeamAssignment -> TeamAssignmentMember` before revalidating
the parent. This covers the supported form, Team Schedule, Django Admin,
direct `save()`, known `get_or_create()`, and confirmation paths without
changing their domain rules.

`MO-S.6D-1D-D-1B-A` later proved that this must not be described as an actual
target-side row-lock guarantee: local and GoDaddy deployment settings both use
SQLite, and Django reports `has_select_for_update=False`. The model/domain
guard, identity immutability, atomic rollback, validation, and ordering code
remain implemented and future-backend compatible, but SQLite ignores the
requested row lock. Prior tests verified code paths, not parallel row locking;
this correction does not imply corrupt stored data.

Docs-only `MO-S.6D-1D-D-1B-A0` selected the monotonic
`ServiceEvent.scheduling_revision`; implemented `1B-A1` now supplies SQLite
first-write serialization, current-truth recomputation, supported-write
coverage, and file-backed concurrency proof. Optimistic batch confirmation
`1B-B` is implemented on that foundation. Arbitrary raw SQL and future bulk ORM
writes remain outside the claim.

Creating or editing a Worship assignment for a team other than the selected
team must fail closed. Changing the selected team while any current Worship
assignment exists for the old or another Worship team must also fail closed in
the ordinary anchor action. It must never move, rewrite, clone, retag, cancel,
or delete that assignment or its members. A later explicit resolution workflow
may show the conflicting assignment and require an authorized human to choose a
separate, auditable action; until then the safe choices are to keep the current
selection or resolve/cancel the old assignment through its existing owning-team
workflow before retrying. An existing assignment on the proposed new team is a
repair case, not permission for an ordinary silent anchor change.

If a service genuinely needs several simultaneous Worship owner teams, the
single selected-team model cannot express that truth. Configure one explicit
assignable combined-service Worship team for the first workflow or approve a
later multi-owner schema; do not encode co-ownership as mismatched parallel
assignments.

## 10. Rotation-selection authority

The implemented server-side `can_change_worship_team(user, event)` contract
allows exactly these classes:

1. staff, superuser, or an existing full `CAP_MANAGE_SERVICE_EVENTS` holder;
2. an active event-specific planner/coordinator assignment described in
   Section 11; or
3. a user holding an active, date-valid `lead` or `coordinator`
   `MinistryTeamRoleAssignment` on at least one applicable configured Worship
   rotation pool.

For class 3, both halves are mandatory:

```text
active Lead/Coordinator role on pool
AND
pool applicable to current reloaded event audience
```

A role on an inapplicable pool grants nothing. An applicable pool with no role
grants nothing. A role on a descendant candidate team grants exact-team roster
management only and does not grant peer rotation selection.

The narrow mutation endpoint/form changes only `rotation_anchor_team`, must
offer only the Section 9 candidate union, and must reject cancelled events. It
must not edit title, type, time, location, status, audience, Host / Language,
required teams, assignments, or rosters. Full event managers may keep their
existing broader event-edit path; the narrow endpoint must not turn a pool Lead
or planner into a full event manager.

For a combined event with several applicable pools, every qualifying pool
Lead/Coordinator may edit the event and the allowed selector is the same union
of candidates from all applicable pools. This is intentional shared
coordination, not descendant roster authority.

`/events/worship-planning/` provides bounded upcoming initial-selection
discoverability without adding a primary navigation item or ordinary event
visibility. `/events/<id>/worship-team/` enters an atomic transaction, requests
and reloads current event state, rechecks authority, audience/pool applicability,
candidates, and ownership consistency, then compares the submitted expected
`updated_at` and old team before saving. Actual changes write one Django
`LogEntry` in the same transaction; GET, denied, stale, invalid, conflict,
no-op, and rolled-back attempts write no audit row. No Worship Team change
notification is emitted in this slice.

## 11. Event-specific planner/coordinator responsibility

`MO-S.6D-1C` implements durable event-level responsibility without reusing
`created_by`: creation attribution still has no responsibility lifecycle and
does not grant management.

The approved workflow includes a person responsible for one exact Sunday
Service who may legitimately select/change that event's Worship Team without
being staff, a superuser, a full `CAP_MANAGE_SERVICE_EVENTS` holder, or a
Lead/Coordinator of an applicable Worship rotation pool. Explicit event-level
planner/coordinator responsibility is therefore a **required prerequisite** for
the narrow Worship Team selection workflow, not an optional later enhancement.
Do not satisfy this use case by granting full `CAP_MANAGE_SERVICE_EVENTS`.

The implemented bounded concept is one event-owned responsibility row named
`ServiceEventPlannerAssignment`:

```text
service_event
user
is_active
notes (operational and non-sensitive only)
created_at
updated_at
```

Implemented foundation semantics:

- one unique row per exact event/user, with explicit add, end, and restore;
  ended rows are retained for history;
- normal active assignment or restore requires an active linked Django user;
  a later-deactivated user makes the stored row non-current without rewriting
  it;
- draft, published, completed, and cancelled event lifecycle changes do not
  automatically delete or rewrite responsibility rows;
- multiple different active planners/coordinators are allowed;
- duplicate rows for the same event/user are rejected rather than silently
  reactivated;
- only existing full ServiceEvent managers may manage the rows in this
  foundation slice;
- the current-planner lookup is responsibility-only and grants no general read
  or event-management access; `MO-S.6D-1D-B` consumes it only for the narrow
  applicable event's Worship Team action;
- not audience membership and does not expose other events;
- not full ServiceEvent management;
- no required-team, TeamAssignment, roster, MinistryTeam, or Church Structure
  management authority;
- not serving and does not appear in My Serving; and
- creates no notification unless a later producer slice is approved.

The `MO-S.6D-1C` foundation remains non-authorizing by itself.
`MO-S.6D-1D-B` now explicitly consumes it so a current planner receives only
the minimum Worship planning context and anchor-change authority for that exact
event. General ServiceEvent visibility and full-event permission remain
unchanged.

## 12. Exact child-team roster boundary

`TeamAssignment` management remains exact-team:

- staff/superuser/global assignment authority may manage any team;
- otherwise an active Lead/Coordinator role on the exact assignable team may
  manage that team's assignment;
- a role on a pool or other ancestor must not flow to descendant teams; and
- a planner, audience row, Campus, Church Structure anchor, or rotation anchor
  must not grant roster management.

The existing `can_manage_team_assignment_for_team` exact-team contract is the
correct foundation and remains unchanged. The governed rotation endpoint
selects which team owns the event; the existing Team Schedule endpoint selects
who serves for that exact team.

## 13. Worship Team operational reachability — implemented (`MO-S.6D-1D-C`,
`MO-S.6D-1D-C-FU1/FU2` projection corrections)

The clean solution to the MO-S.6D-0A dead end is to make the exact current
rotation anchor a third operational event-relevance predicate:

```text
required team
OR existing non-cancelled assignment
OR exact selected rotation_anchor_team that remains an eligible candidate
```

This is reachability only. It does not make the anchor required coverage, does
not create a `ServiceEventRequiredTeam`, does not create a `TeamAssignment`, and
does not grant edit authority.

Implemented Team Schedule behavior:

- add exact valid eligible `rotation_anchor_team=selected_team` to the existing
  event set by reusing `inspect_worship_ownership_consistency(event)`;
- keep draft/cancelled exclusion and existing date/type filters;
- preserve exact-team POST authorization and `is_assignable` validation; and
- keep a selected-team-only event with legitimately empty coverage rows and a
  separate Selected Worship Team / selected-not-yet-scheduled marker and normal
  exact-team Schedule action, without fabricating coverage or an assignment;
- relabel the exact selected team's later non-required assignment only in this
  presentation layer so it does not imply required coverage; and
- use Worship Team / 敬拜团队 scheduler-facing terminology.

Implemented Sunday Board behavior:

- treat a valid current selected Worship Team as row-level operational
  participation for the bounded Sunday window;
- let an exact selected-team manager see that row and the narrow Worship context;
- let a global assignment manager see a selected-team-only operational row;
- keep only the canonically valid eligible selected team outside generic
  required/additional coverage columns and render it through the Worship
  context projection;
- keep an invalid or stale raw selection review-required in the Worship column
  without suppressing independent required-team or current-assignment generic
  participation, including its approved narrow roster/status projection;
- map canonical off-team/out-of-scope ownership to review-required conflict and
  multiple/duplicate ownership to ambiguous, with no Worship roster projection
  or Schedule/Edit Worship action for those states;
- require canonical selected-team eligibility in addition to exact-team
  assignment authority before showing the Worship Schedule/Edit action; and
- keep general ServiceEvent detail and unrelated assignment-detail access
  unchanged.

When the anchor changes, the prior team immediately loses anchor-only
reachability. It retains the event only if it is still required or has an
existing assignment. The new exact team gains anchor relevance. An inactive or
non-assignable anchor does not grant a team scheduling surface; existing global
event-management/repair surfaces remain responsible for invalid configuration.

The implementation is a queryset/projection-only slice with no schema change,
new permission, reachability persistence, coverage mutation, or notification
producer. Focused tests and rendered QA prove privacy redaction, exact-team
authority, planner/pool-Lead non-roster boundaries, old/new/cleared selection
behavior, global-manager rows, lifecycle/date/type exclusions, invalid-selection
fail-closed behavior, zero automatic writes, and contained bilingual mobile UI.

### Effective required-team semantic — docs contract complete, runtime unimplemented

`MO-S.REQUIRED.0A` supersedes only the earlier statement that a valid selected
Worship Team is never required coverage. It does not alter the historical
`MO-S.6D-1D-C` implementation result or persist a required row. The current
approved semantic is:

```text
effective required teams
    = explicit ServiceEventRequiredTeam rows
      UNION the exact selected Worship Team when selected_team_is_eligible
```

The derived selected team is not a `ServiceEventRequiredTeam`, assignment,
serving fact, audience, responsibility, or permission. Provenance remains
available so NOTIFY.1G and stored-row audits continue to consume explicit rows
only, and Board/Team Schedule keep the selected team in their dedicated Worship
presentation rather than duplicate it in generic columns.

`inspect_worship_ownership_consistency()` already provides the exact gate:
`selected_team_is_eligible`. No selection or an invalid/ineligible raw selection
derives nothing. A valid selected-unscheduled team is a missing Worship coverage
expectation; one exact current assignment is empty or scheduled according to
active members. If the selected identity remains eligible during off-team,
out-of-scope, multiple, or duplicate ownership, it remains the intended
effective requirement while the independent ownership result stays
conflict/ambiguous and is not clean coverage. Invalid selected identity never
becomes required merely because an assignment exists.

Operational reachability remains the existing three-predicate behavior and may
share the same selected-team resolver without changing scope. Exact-team roster
authority remains separate. Anchor selection never creates/deletes a stored
required row, and unselected Worship siblings and Worship containers are never
effective-required.

The Event-page entry contract also remains narrow: the canonical V1 entry is a
read-only/current Worship Team section on ServiceEvent detail, with a Change
action only when `can_change_worship_team(user, event)` is true. The action links
to the existing governed exact-event selector and grants neither general event
edit nor child roster authority. The ordinary ServiceEvent form must continue
to exclude raw `rotation_anchor_team`.

## 14. Concurrent authorized editors

Several pool Leads or planners may legitimately edit a combined event. The
implemented narrow POST therefore:

1. enter `transaction.atomic`, request current `ServiceEvent` state, and reload
   it;
2. reauthorize against the reloaded current event, audience, active pool roles,
   pool configuration, and candidate union;
3. compare a browser-rendered expected `updated_at` and expected current anchor
   against the reloaded row;
4. reject a stale event or a selected team that is no longer eligible;
5. save only the anchor; and
6. record actor plus old/new anchor through the repository's established
   `LogEntry` audit pattern inside the transaction.

The event-level `updated_at` and expected-old-anchor comparisons remain useful,
conservatively broad request-level stale guards: an unrelated event edit may
force the user to refresh, and stale-form/domain checks still reject detected
changes. On target SQLite, however, `select_for_update()` supplies no actual
`ServiceEvent` row lock, so those checks plus the atomic endpoint do not provide
a strict parallel scheduling-write or lost-update guarantee. That supported-
write concurrency closure is now implemented by `1B-A1` through the approved
`ServiceEvent.scheduling_revision` contract. This preserves the
chronology: `1D-B` implemented the existing timestamp/old-team checks, not an
optimistic revision. Prior SQLite tests prove request-level stale-form and
atomic rollback semantics, not parallel row locking.

### Worship Rotation Planner contract, preview, and optimistic confirmation

`MO-S.6D-1D-D-0A` closes the docs-only batch contract in
[`WORSHIP_ROTATION_PLANNER_PLAN.md`](WORSHIP_ROTATION_PLANNER_PLAN.md).
`MO-S.6D-1D-D-1A` implements the contextual exact-event selection and
side-effect-free signed proposal/preview. It writes no event, audience,
required-team, planner, assignment/member, structure/ministry membership,
audit, notification, session, temp-file, or other durable proposal state.

The existing exact-event selector remains the sole way to change one Sunday
only. Planner V1 owns only **Insert / Shift Later Worship Teams** over 2 through
53 exact, explicitly reviewed, published future Sunday Service events. It
shifts stored identities deterministically, validates every proposed team
against the destination event's canonical eligible-candidate set, blocks any
changed row with a current Worship assignment, shows roster-free downstream
assignment impact, and never changes audience, assignments, rosters, required
teams, or planner responsibility.

V1 permits no silent tail loss: an interior blank blocks, while a final blank
existing event may serve as the landing slot. Preview evidence from `1A`
refined the earlier conservative `0A` rule before confirmation existed:
`1A-FU1` also accepts a non-null tail when its exact `MinistryTeam` ID equals
the explicitly inserted team ID, because that closes the selected-range cycle
without losing a team identity. Any other non-null tail remains shown and
blocked. This is exact identity preservation, not a stored/inferred rotation
sequence, name/order convention, fuzzy match, or arbitrary tail-drop approval.
Preview uses a 30-minute user-bound timestamped Django-signed normalized
proposal. Implemented `1B-B` confirms only a currently matching proposal and
writes one per-changed-event `LogEntry` whose shared operation UUID identifies
the batch; preview itself still writes no audit rows. No durable BatchRun schema
is required for the limited-trial contract.

The attempted downstream row-lock closure `1B-A` correctly stopped without
changes because target SQLite cannot provide the proposed ServiceEvent
`select_for_update()` lock. Docs-only `1B-A0` closes the replacement
architecture decision; implemented `1B-A1` adds one monotonic event-owned
scheduling revision and retrofits supported ServiceEvent, current-assignment, required-
team/audience, Admin/delete/cascade, member-confirmation parent-status, and
Lighting writes. Implemented `1B-B` claims every selected event revision with an
atomic expected-value CAS before full governance/authority/fingerprint
recomputation. SQLite's first successful CAS supplies a database-wide writer
boundary, not a row lock. Read-only preview `1A` remains unaffected.

### Direct Worship Team change notifications — IMPLEMENTED

`NOTIFY.1G-0A` closes the docs-only contract and `NOTIFY.1G` implements it. A
successfully committed selected-team change is a known domain event with an
exact old/new value. The ministry-owned producer notifies a bounded, deduplicated
recipient set:

- active, date-valid Leads/Coordinators of the old selected Worship team;
- active, date-valid Leads/Coordinators of the new selected Worship team;
- active, date-valid Leads/Coordinators of active required downstream service
  teams for the event; and
- active, date-valid Leads/Coordinators of active additional downstream teams
  that already have a current operational assignment (`scheduled`,
  `confirmed`, or `prepared`) for the event.

The last class resolves the earlier loose phrase "non-cancelled assignment"
to canonical Sunday Board/planner participation. A completed assignment is
non-cancelled but historical and does not qualify; cancelled also does not
qualify. Sunday Board already treats a current
assignment without a required-team row as real operational participation. It
does not justify notifying assignment members, all team members, audience
members, Church Structure members, generic staff, or unrelated pool leaders.
Exclude any team whose canonical primary path resolves to a configured Worship
pool from the downstream classes, even when the pool is currently unusable;
an unresolved malformed path must not be guessed from names, team kinds,
labels, or secondary paths, and independent readiness/governance blockers stay
authoritative. Deduplicate a user
who qualifies through several teams, use recipient-persisted language, and keep
the snapshot free of rosters, notes, contact data, audience internals, and
private profile data.

The producer must live in `ministry`, resolve its own recipients and dedupe
identity before Core post-commit registration, and emit only through the Core
notification port. It must not import Notification persistence or use Django
signals. A
single-event change produces at most one notification per recipient. A batch
shift produces one summarized notification per recipient for the committed
batch, not one per Sunday. The exact-event dedupe identity is
`ministry:worship_team_change:log:<logentry_id>` using the saved audit row; the
batch identity is `ministry:worship_rotation:<operation_id>`. Batch summaries
contain only events for which that recipient qualifies. The safe common target
is `reverse("my_serving")`: its role-driven Teams I manage entrance remains
available to an old-team leader after anchor-only Board reachability is lost and
does not depend on event audience. Snapshots use recipient language, date plus
old/new localized team only, and batch previews at most three recipient-relevant
changes plus `+ N more`. Disabled Notifications remains a safe no-op.

This direct producer is separate from MO-S.6E. A committed selected-team change
has explicit before/after facts and can notify immediately. Detecting a later
roster membership/status change across every mutation path, deciding which
downstream schedules became stale, and avoiding noisy repeats remains the
harder MO-S.6E problem. Docs/read-only `MO-S.6E.0A` now rejects timestamp-only
and `scheduling_revision` reuse and freezes a nullable downstream-reviewed
canonical-fingerprint contract with unknown/current/different states and
explicit review acknowledgement. Docs-only `MO-S.6E.0A-FU1` closes unlinked
display-identity fingerprinting and binds acknowledgement to the protected
rendered context rather than silently accepting newer truth. `MO-S.6E.1A` now
implements the additive nullable schema, shared canonical signature, bounded
Team Schedule/Board UI, POST-only acknowledgement, and real SQLite first-write/
current-truth hard gate. Existing member-facing assignment notifications do not
solve that cross-team warning, and MO-S.6E V1 adds no notification producer.

Scheduler-facing copy should say **Worship Team** / **敬拜团队**, for example
"Current Worship Team" and "Change Worship Team." Reserve
`rotation_anchor_team`, "rotation anchor," pool, and path terminology for code,
staff setup, audit, or architecture documentation.

## 15. Consequences for MO-S.6D Excel import

The strict MO-S.6D-0A workbook decisions remain:

- known code-owned `.xlsx` contract; only `All 930` A:B for the Bethany 9:30
  profile in the first importer;
- exact `ServiceEvent.service_profile_key` matching, with the first approved
  workbook setup value `bethany_0930_cm`;
- exact local date/time/type/profile identity;
- no fuzzy event or team matching, no hard-coded PKs, and no user/team creation;
- no formula evaluation; cached date results only under the recorded structural
  and weekly-sequence validation;
- implemented read-only preview with expiring signed normalized state, partial
  mapping blockers, target-before-mapping-before-governance blocker precedence,
  and visible classification of special/unsupported rows; and
- no assignment/member import in the first importer.

Docs/read-only `MO-S.6D-SLICE9.0A` now owns the frozen confirmation-time
reauthorization/revalidation, atomic fail-closed selected-team write,
audit/result, rollback, replay, and idempotency contract. `SLICE9.1A` now implements that separate runtime and is
**PRODUCTION APPLY COMPLETE / VERIFIED**; none of its write-path claims changes
the still-zero-write Slice 8 preview contract.

Revised first lifecycle:

- match/update one exact existing, non-draft, non-cancelled,
  audience-ready ServiceEvent;
- resolve each present allowed workbook token by explicit preview mapping to a
  current eligible candidate from that event's applicable configured Worship-
  pool union; retain unresolved/ineligible rows as blocked preview evidence;
- classify any current Worship assignment for a different team, or any ordinary
  anchor change while a current Worship assignment exists, as a blocking
  conflict rather than moving or retagging a roster;
- surface existing downstream assignments as review impact without changing
  them;
- in the production-applied and product-owner-verified Slice 9 runtime, update
  `rotation_anchor_team` only; and
- never infer audience, Campus, Ministry Context, required teams, assignments,
  or serving from the workbook.

The frozen V1 confirmation boundary is staff/superuser-only at preview and
confirmation; exactly 52 reviewed existing published/completed canonical
targets; a distinct 30-minute user-bound signed confirmation proposal with
workbook hash, explicit token mapping, exact event/expected-revision/expected-
before/proposed-team identities, and one operation UUID; no workbook re-upload
or durable `ImportRun`; ascending expected-`scheduling_revision` CAS as the
first scheduling/governance access; reload plus current-truth recomputation of
profile/date/time/type, lifecycle, audience, mapped-team activity/
assignability, governance/applicability/eligibility, expected-before anchor,
ownership/current assignments, and bulk authority; changed-anchor-only saves
without a second revision bump; and one shared-operation `LogEntry` per changed
event. Every selected no-op row participates in the successful revision claim
but receives no anchor save or audit. Any stale, missing, busy, invalid,
conflicting, save, or audit failure rolls back the whole 52-row batch.

The importer deliberately does not invoke `NOTIFY.1G` in V1. A first annual
52-Sunday null-to-team import could create an unreviewed notification burst;
any annual-import summary is a separate later producer decision. Exact selector
and Rotation Planner notifications are unchanged.

The prior recommendation to create `ServiceEventRequiredTeam` for the anchor
solely to bootstrap discoverability is **superseded**. Anchor-based operational
reachability is the cleaner domain rule. The importer must not claim required
coverage merely because a team owns the rotation.

Single-event authority and bulk import authority remain separate. A Worship-pool
Lead or event planner may be allowed to change one applicable event; that does
not authorize an annual workbook. Implemented Slice 8 upload/preview is staff/
superuser only and rechecked at preview. The separately authorized Slice 9
confirmation now uses the same first-workflow boundary and rechecks authority at
confirmation. A later dedicated bulk-import capability may be considered after
trial evidence; do not reuse pool role, exact-team assignment authority, or
audience as bulk authority.

## 16. Rejected alternatives

- **Model Campus as `ministry_context`:** rejected because Campus and
  congregation/language context are different and the Host / Language consumer
  gives `ministry_context` a real display meaning.
- **Enforce Root -> Campus -> CM/EM -> District -> Small Group:** rejected
  because current and future churches need uneven, optional, and custom depth.
- **Use names, A/C1/C2/C3 codes, stable PKs, or fuzzy matching:** rejected as
  church-specific and unsafe.
- **Use `team_kind`, non-assignable status, or Worship role profile alone to
  identify pools:** rejected because each is intentionally broader or
  non-behavioral metadata.
- **Use a generic `is_rotation_pool` Boolean in V1:** rejected because the only
  governed slot is ServiceEvent Worship Team ownership; a generic flag could
  make unrelated preaching, ushering, or future rotation systems appear to be
  valid Worship candidates. Generalize only after a materially different domain
  proves the need for a typed or slot-based abstraction.
- **Treat every MinistryTeam Church Structure anchor as a pool:** rejected
  because anchors are generic organization/display links and would silently
  create authority/applicability.
- **Grant a pool Lead full `CAP_MANAGE_SERVICE_EVENTS`:** rejected because it
  exposes unrelated event fields and events.
- **Flow pool/ancestor management to descendant rosters:** rejected because it
  violates exact-team ownership and existing permission semantics.
- **Use `created_by` as planner:** rejected because it is attribution without a
  responsibility lifecycle.
- **Use audience as authority:** rejected; applicability and authority are two
  mandatory independent predicates.
- **Use Host / Language as applicability:** rejected because it is display-only
  and may be blank or derived.
- **Create a required-team row for discoverability:** rejected as a false
  coverage assertion; anchor reachability solves the workflow without changing
  required-team meaning.
- **Direct-child candidates only:** rejected because harmless intermediate
  containers would require data/schema churn.
- **All active parent links for candidate ownership:** rejected in V1 because a
  secondary/display link would make a shared team eligible in multiple pools;
  the primary path is deterministic.
- **Automatically create a published event from the workbook:** rejected because
  the workbook cannot supply safe audience or canonical profile data.

## 17. Future implementation slices

Each slice is separately approvable and must verify repository truth again.

| Order | Candidate slice | Runtime/schema and permission impact | Targeted verification | Manual QA |
| --- | --- | --- | --- | --- |
| 1 | **Campus/Site type foundation — IMPLEMENTED (`MO-S.6D-1A`)** | Choice-only model state plus `AlterField` migration; semantic behavior only; no new permission | model/form/admin choices, flexible topology, generic audience/Bible Study ancestry, type-specific exclusions, no side effects | Staff setup label/choice QA after deployment |
| 2 | **Worship rotation-pool configuration foundation — IMPLEMENTED (`MO-S.6D-1B`)** | Worship-specific `MinistryTeam.is_worship_rotation_pool` field, default-safe migration, model/form validation, read-only configuration resolver, existing setup UI, and readiness integration; configuration grants no authority | active non-assignable pool, primary anchor/path, inactive/ambiguous/cycle fail-closed, canonical role warning, no created rows/permissions | Narrow staff setup copy/error-state/rendered QA in the implementation slice; deployment QA remains separate |
| 3 | **ServiceEvent planner/coordinator responsibility foundation — IMPLEMENTED (`MO-S.6D-1C`)** | `ServiceEventPlannerAssignment` exact-event/user lifecycle model and migration, current-only read helper, existing full-manager bilingual edit-page setup controls, and admin exposure; the foundation grants nothing by itself, while 4B consumes it only for the exact-event Worship Team action | lifecycle/end/restore, unique event/user, multiple planners, inactive-user fail-closed lookup, draft/cancelled/completed persistence, full-manager-only setup, no audience/serving/full-event/structure/assignment authority | Narrow existing ServiceEvent edit-page rendered QA in the implementation slice; deployment QA remains separate |
| 4A | **Read-only Worship applicability, candidate, and ownership-consistency foundation — IMPLEMENTED (`MO-S.6D-1D-A`)** | Side-effect-free domain helper only; reuses pool inspection and current scheduling statuses; no permission, selector, endpoint, enforcement, model, or migration | audience union/fail-closed applicability, active-primary descendant candidates, off-team/out-of-scope/multiple/duplicate consistency, privacy/read-only and authority boundaries | No rendered QA; no user-visible behavior changed |
| 4B | **Narrow Worship Team authorization, write enforcement, and UI — IMPLEMENTED (`MO-S.6D-1D-B`, identity/ordering closure in `MO-S.6D-1D-B-FU1`)** | Consumes 4A from narrow GET/POST plus existing anchor/Worship-assignment write paths; pool Leads/planners receive only this action; current Worship identity is immutable; atomic validation and ServiceEvent-first ordering remain implemented, but target SQLite provides no actual `select_for_update()` row lock | actual denial/allow rules, current-truth reauthorization, stale form, combined union, legacy-form/admin/assignment bypass closure, cross-path identity retarget rejection, structural event-first path, LogEntry attribution, no roster move or unrelated writes | Rendered Worship Team selector, bilingual copy, conflict UX, hidden blocked controls, and narrow-context privacy verified in the implementation slices |
| 5 | **Worship Team operational reachability — IMPLEMENTED (`MO-S.6D-1D-C`; projection corrections `MO-S.6D-1D-C-FU1/FU2`)** | Team Schedule/Board queryset and projection change only; exact-team assignment permission unchanged; canonical eligibility fails closed; invalid raw selection never suppresses independent generic required/assignment participation; canonical ownership conflicts/ambiguity are review-only and non-actionable; no migration | selected-team-only rows, empty-coverage presentation, valid-selection de-dup, invalid required/assignment projection, off-team/out-of-scope conflict, multiple/duplicate ambiguity, global/exact-team behavior, planner/pool-Lead boundary, change/removal, privacy, no coverage/assignment/required-team writes | Rendered English desktop and Chinese mobile Team Schedule/Board QA completed in the implementation slice; FU1/FU2 are focused projection-only and test-verified |
| 6 | **Worship Rotation Planner — IMPLEMENTED THROUGH `1B-B`** | Existing selector retains one-Sunday changes; `1A/FU1` remain side-effect-free; `1B-A1` owns the event revision/barriers/fingerprint-v3 foundation; `1B-B` adds POST-only signed confirmation and shared audit; no rule engine, roster mutation, notification, or BatchRun schema | expected-revision CAS first, full recomputation, stale/all-or-nothing rollback, all-selected revision advance, changed-only shared-operation LogEntry audit, replay/tail/privacy/zero-cross-domain-write coverage, and target-like file-backed SQLite proof | Rendered English desktop and Chinese mobile confirmable/blocked/success/replay/narrow-authority QA completed; deployment QA remains separate |
| 7 | **Direct Worship Team change notification producer — IMPLEMENTED (`NOTIFY.1G`)** | Ministry-owned post-commit producer through Core port; no notification permission/schema inference; recipient-specific summarized batch delivery | exact role/date recipients, current-operational required/additional downstream bounds, Worship exclusion, dedupe, subset privacy, language/snapshot safety, disabled-module no-op, rollback/no-emission | Focused source/persistence tests complete; deployment QA remains separate |
| 7A | **Stable ServiceEvent profile identity — IMPLEMENTED (`MO-S.6D-PROFILE.1A`)** | One optional, non-unique, validated `service_profile_key`; Admin-only technical setup; existing rows default empty; grants no audience/permission/serving/recurrence meaning | lexical validation, duplicate profile reuse, ordinary-form exclusion, scheduling-revision advance/rollback, zero cross-domain side effects | No browser QA; no non-Admin surface changed |
| 7B | **Profile target-event readiness audit — IMPLEMENTED, COMMITTED, AND RUN ON PRODUCTION (`MO-S.6D-PROFILE-SETUP.0A`, READ-ONLY)** | Independent 52-Sunday local-date contract; persisted-key-only canonical identity; requested-event-type candidate discovery; migration/schema gate; tagged-row, audience, untagged candidate, other-profile exact-time, and different-time parallel-service evidence; deterministic text/JSON stdout | exact/invalid/duplicate/out-of-contract tagged rows, untagged none/single/multiple review cases, other-profile non-candidate separation, different-time service isolation, profile-key length bound, schema-not-ready stop, privacy, full zero-write model/callback proof | Local DB remains schema-not-ready; final production post-reset audit is setup-ready: 52 expected, 52 canonical, 52 ready exact matches, and zero missing/duplicate/invalid/ambiguous target rows |
| 7C | **Canonical Bethany 09:30 TEST-data rebuild — PRODUCTION APPLY COMPLETE / VERIFIED (`MO-S.6D-PROFILE-SETUP.1A/FU1`)** | Dry-run default; three-part destructive gate including reviewed-state token; all-ServiceEvent/event-owned reset only; exact active `CHURCH -> campus -> CM`; atomic 52-Sunday setup; audit postcondition; no importer or Worship selection | deletion/cascade/preservation inventory, deterministic token, missing/malformed/wrong/stale rejection, exact local/DST contract, lifecycle-date/path binding, rollback, no-op repeat, post-reset `PROFILE SETUP READY` | Product-owner-reviewed production reset created 52 canonical events plus 52 exact CM audience rows; final audit returned 52/52 ready and `PROFILE SETUP READY` |
| 8 | **Excel dependency/parser + preview — IMPLEMENTED / PRODUCTION READ-ONLY SMOKE PASSED (`MO-S.6D-SLICE8.1A/FU1/UX1`)** | `openpyxl==3.1.5`; strict known-workbook parser; fixed A/C1/C2/C3 vocabulary with counts and mapping controls derived from present tokens; blocked partial-mapping preview; exact persisted-profile target classification; signed user-bound normalized state; pre-openpyxl 5 MiB upload, 128-member, 20 MiB total-uncompressed, and 8 MiB single-member OOXML limits plus encrypted-member rejection; staff/superuser-only read-only upload/preview; wider compact operational matrix with sticky review context; no confirm route, data write, or migration | contract/header/geometry/date/formula/cache/token/profile/identity classification, altered/absent-token distributions, archive member/count/resource/encryption boundaries, signed semantic tamper, target-before-mapping precedence, incomplete/no-candidate/per-destination mapping blockers, lifecycle/audience/parallel evidence, roster/downstream impact, privacy/expiry, permission, zero-write tests, and desktop/mobile rendered QA | Real workbook SHA-256 `186735DC723979AA49D209C92D4155BE533D6AFE9253CDB5D8B809A77C8B07AA` accepted on local Python 3.14.7: 257,609 bytes, 46 members, 2,291,811 declared uncompressed bytes, 631,391-byte largest member, and observed A/C1/C2/C3 counts 12/13/13/14 (evidence, not an invariant). Production smoke on GoDaddy Python 3.11.15 imported openpyxl 3.1.5 and produced 52 supported Sundays, 52 exact targets, 0 no-op, 52 proposed changes, 0 blocked, and Complete mapping; preview stayed read-only. This is not Slice 9 readiness proof. |
| 9 | **Excel exact match/update confirmation — PRODUCTION APPLY COMPLETE / VERIFIED (`MO-S.6D-SLICE9.1A`; contract `SLICE9.0A`)** | Staff/superuser-only distinct 30-minute signed reviewed proposal; exact 52 existing events; scheduling-revision CAS plus current-truth recomputation; changed anchors plus all-selected revision claims; per-changed-event shared-operation LogEntry; no ImportRun, assignment/member/audience/RequiredTeam/event/team/structure write, or notification | strict proposal shape/user/expiry, 52-row completed+published atomic success, changed/no-op, identity/governance/ownership failures, stale/busy/replay/audit rollback, zero cross-domain/notification effects, and two-scenario target-like file-backed SQLite concurrency | Local English desktop / Chinese mobile QA passed; product-owner-reviewed production confirmation completed, followed by 52 no-op / 0 proposed / 0 blocked re-upload verification. |
| 10 | **Later assignment import** | Deferred; would write TeamAssignment/member data and needs exact-team plus bulk authority and identity proof | unresolved/ambiguous people, explicit aliases, team ownership, no user creation, rollback/idempotency | Required; only after operational evidence |

Dependencies: slices 1, 2, 3, 4A, 4B, 5, and slice 6 through confirmation
`1B-B` are implemented; docs-only `1B-A0` is complete. Slice 1 remains
independent but should precede real multi-campus setup. Slices 2 and 3 both
precede 4B: pool configuration is required for pool-based authority/
applicability, and the implemented exact-event planner responsibility is
required for the approved event-planner workflow. Slice 4A defines the
read-only ownership facts; 4B enforces them for supported writes. Implemented
slice 5 now ensures an imported Worship Team can be operationally reachable
without false required coverage before slice 9. Implemented slice 6 precedes
using annual import as a batch rotation tool. Slice 7 follows a proven change
path. PROFILE.1A supplies Slice 8's stable field, PROFILE-SETUP.0A supplies the
committed zero-write evidence tool, and PROFILE-SETUP.1A supplies the separately
gated canonical TEST-data setup command. Production migrations/schema through
`events/0011` are ready. The product-owner-reviewed production reset and post-
apply audit are complete: 52/52 canonical targets are ready and the result is
`PROFILE SETUP READY`. The target-event setup prerequisite is therefore closed.
Slice 8/FU1/UX1 dependency, parser, bounded archive preflight, partial zero-
write preview, and wider operational review surface are implemented. The exact
production Python 3.11.15/openpyxl 3.1.5 read-only smoke passed with 52/52 exact
targets and zero blocked rows. This closes Slice 8 production preview smoke
only. `MO-S.6D-SLICE9.0A` closes the separate docs/read-only confirmation
contract and repository audit; `MO-S.6D-SLICE9.1A` is PRODUCTION APPLY COMPLETE / VERIFIED. The
product-owner-reviewed production confirmation is complete, and a fresh
re-upload produced 52 no-op rows, 0 proposed changes, 0 blocked rows, and no
confirmation action. Slice 10 remains later.

## 18. Permission, privacy, and data invariants

- Audience is not permission.
- Structure is not belonging; belonging is not serving.
- Church Structure anchors are not authority by themselves.
- Pool roles and event planner roles are not TeamAssignment roster authority.
- Rotation anchor is not required coverage, assignment, serving, audience, or
  permission grant.
- A current Worship assignment must match the selected Worship Team; conflict
  handling never silently retags or moves its roster.
- Exact-team roster authority remains exact-team.
- Narrow coordination views must not expose private notes, contact/profile data,
  confirmation detail, or unrelated event/assignment detail.
- All mutation paths reauthorize on POST and fail closed on stale or changed
  configuration.
- No name-based, fuzzy, or PK-configured production mapping.
- No future slice may create memberships, audience rows, serving rows, or roles
  as an undocumented side effect.

## 19. Remaining bounded product decisions

Architecture is closed enough for the proposed slices. Slice 8 selected
`openpyxl==3.1.5`, implemented strict exact-profile parsing/matching and the
staff/superuser-only zero-write preview, and retained signed request-scoped
normalized proposals without `ImportRun` schema. Its exact production Python
3.11.15/openpyxl 3.1.5 read-only smoke is complete. `MO-S.6D-SLICE9.0A` froze
the no-schema signed-proposal, current-truth reauthorization, stale/replay
handling, atomic 52-row selected-team write, shared audit, no-notification,
result, failure, and concurrency-test contract; `MO-S.6D-SLICE9.1A` is now PRODUCTION APPLY COMPLETE / VERIFIED. The
product-owner-reviewed production confirmation is complete, and the fresh
same-workbook re-upload verified 52 no-op rows, 0 proposed changes, 0 blocked
rows, and no confirmation action.

Multi-anchor pool semantics, a dedicated bulk-import capability, dedicated
anchor version/audit schema, explicit roster-conflict resolution, and assignment
import remain evidence-gated later decisions rather than hidden V1 assumptions.

## 20. Evidence references

This decision is grounded in:

- `accounts/models.py`, `accounts/forms.py`, `accounts/permissions.py`,
  `accounts/structure_selectors.py`, `accounts/unit_management.py`, and the
  current staff Church Structure setup views/tests;
- `events/models.py`, `events/forms.py`, `events/views.py`, and
  `events/ministry_context_display.py`;
- `ministry/models.py`, `ministry/permissions.py`, `ministry/views.py`,
  `ministry/services/sunday_schedule_board.py`,
  `ministry/services/worship_context.py`, and
  `ministry/services/copy_forward_suggestions.py` plus the existing
  `ministry/services/assignment_notifications.py` producer and Core notification
  delivery boundary;
- focused Team Schedule, Sunday Board, Ministry hierarchy, and Church Structure
  setup tests; and
- `CHURCH_STRUCTURE_FOUNDATION_PLAN.md`,
  `CHURCH_STRUCTURE_MAP_AND_SETUP_READINESS_PLAN.md`,
  `FLEXIBLE_CHURCH_STRUCTURE_AND_AUDIENCE_SCOPE_DESIGN.md`,
  `MINISTRY_STRUCTURE_ARCHITECTURE_PLAN.md`,
  `MINISTRY_ROLE_SOURCE_OF_TRUTH_PLAN.md`,
  `WORSHIP_ROTATION_PLANNER_PLAN.md`, and
  `SUNDAY_MINISTRY_SCHEDULING_PLAN.md`.
