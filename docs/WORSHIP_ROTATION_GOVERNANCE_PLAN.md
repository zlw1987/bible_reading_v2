# Multi-Campus Worship Rotation Governance Plan

Status: canonical governance decisions through `MO-S.6D-0A-FU2`, plus
implemented `MO-S.6D-1A` Campus / Site type foundation and `MO-S.6D-1B`
Worship rotation-pool configuration foundation, and implemented `MO-S.6D-1C`
ServiceEvent planner/coordinator responsibility foundation, plus implemented
`MO-S.6D-1D-A` read-only event applicability, candidate, and ownership-
consistency domain foundation, plus implemented `MO-S.6D-1D-B` governed
authorization, mutation enforcement, and narrow Worship Planning UI, with
`MO-S.6D-1D-B-FU1` identity and cross-path serialization closure, plus
implemented `MO-S.6D-1D-C` Worship Team operational reachability with FU1/FU2
projection-consistency closure, plus the docs-only `MO-S.6D-1D-D-0A`
Worship Rotation Planner batch contract and implemented read-only proposal/
preview `MO-S.6D-1D-D-1A`. Governance FU2 finalizes the required event-planner
prerequisite and Worship-specific pool semantics. The Campus, pool-
configuration, event-responsibility, read-only governance, and governed
single-event mutation and operational-reachability foundations are implemented;
locked planner confirmation/audit, notification, and import slices below
require separate explicit approval.

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

The current code does **not** provide:

- locked Worship Rotation Planner confirmation/audit;
- direct Worship Team change notifications; or
- a declared `.xlsx` dependency or annual-workbook importer.

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

### `MO-S.6D-1D-B-FU1` identity and serialization closure

The supported-write backstop now treats Worship assignment identity as
immutable. If either the persisted or proposed current/historical assignment
resolves through a configured Worship pool, an existing row cannot change its
`service_event` or `team`. This applies even when the persisted row is currently
valid and consistent, and it closes both directions of the boundary: a Worship
row cannot be retargeted to another Worship or downstream team/event, and a
downstream row cannot be retargeted into Worship. Supported pure-downstream
retargeting remains unchanged. Cancellation and completion remain explicit
in-place lifecycle transitions and never rewrite assignment identity.

Supported current Worship assignment writes serialize on the governing
`ServiceEvent` row. The model save boundary enters an atomic transaction, locks
the proposed and/or persisted Worship event rows in deterministic ID order,
then re-runs model validation before saving. The narrow selector already uses
the same event lock, and member confirmation follows the lock order
`ServiceEvent -> TeamAssignment -> TeamAssignmentMember` before revalidating
the parent. This covers the supported form, Team Schedule, Django Admin,
direct `save()`, known `get_or_create()`, and confirmation paths without adding
a schema or lock table. Pure downstream writes and safe lifecycle transitions
out of the current Worship set acquire no Worship event-row lock.

This is an application-supported-write guarantee, not a database constraint.
Arbitrary raw SQL and future bulk `QuerySet.update()` paths remain outside the
claim and must not be introduced for Worship mutations. SQLite tests verify
the guard decisions, transaction boundaries, and selected lock path, but do
not prove PostgreSQL-style parallel row-lock behavior; that behavior remains a
target-backend concurrency property.

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
pool applicable to current locked event audience
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
visibility. `/events/<id>/worship-team/` locks and reloads the event, rechecks
authority, audience/pool applicability, candidates, and ownership consistency,
then compares the submitted expected `updated_at` and old team before saving.
Actual changes write one Django `LogEntry` in the same transaction; GET, denied,
stale, invalid, conflict, no-op, and rolled-back attempts write no audit row.
No Worship Team change notification is emitted in this slice.

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

## 14. Concurrent authorized editors

Several pool Leads or planners may legitimately edit a combined event. The
implemented narrow POST therefore:

1. enter `transaction.atomic` and lock/reload the `ServiceEvent`;
2. reauthorize against the locked current event, audience, active pool roles,
   pool configuration, and candidate union;
3. compare a browser-rendered expected `updated_at` and expected current anchor
   against the locked row;
4. reject a stale event or a selected team that is no longer eligible;
5. save only the anchor; and
6. record actor plus old/new anchor through the repository's established
   `LogEntry` audit pattern inside the transaction.

Using the event-level `updated_at` is conservatively broad: an unrelated event
edit may force the user to refresh, but no silent lost update occurs and no new
version field is needed initially. If trials show unacceptable false conflicts,
a dedicated anchor version/audit model can be evaluated separately. SQLite
tests can prove stale-form and atomic semantics, not parallel PostgreSQL lock
behavior.

### Worship Rotation Planner contract and implemented read-only preview

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
existing event may serve as the landing slot. A non-null displaced tail is
shown and blocks confirmation until the range is extended and regenerated.
Preview uses a 30-minute user-bound timestamped Django-signed normalized
proposal. Confirmation is a separately approved locked atomic slice using
normal per-event saves and one existing-style `LogEntry` per actual change,
all sharing one operation UUID. No durable BatchRun schema is required for the
limited-trial contract.

The repository-truth audit also found that pure downstream assignment writes
do not currently serialize on their ServiceEvent. Before confirmation may
promise downstream-impact staleness, its owning `1B` slice must close the
supported event-first downstream write paths or stop and obtain an explicit
version/schema decision. Read-only preview `1A` is not blocked by that runtime
closure.

### Direct Worship Team change notifications

A successfully committed selected-team change is a known domain event with an
exact old/new value. A future ministry-owned producer should notify a bounded,
deduplicated recipient set:

- active, date-valid Leads/Coordinators of the old selected Worship team;
- active, date-valid Leads/Coordinators of the new selected Worship team;
- active, date-valid Leads/Coordinators of active required downstream service
  teams for the event; and
- active, date-valid Leads/Coordinators of active additional downstream teams
  that already have a non-cancelled assignment for the event.

The last class is repository-grounded: Sunday Board already treats a current
assignment without a required-team row as real operational participation. It
does not justify notifying assignment members, all team members, audience
members, Church Structure members, generic staff, or unrelated pool leaders.
Exclude Worship candidate teams from the downstream classes, deduplicate a user
who qualifies through several teams, use recipient-persisted language, and keep
the snapshot free of rosters, notes, contact data, audience internals, and
private profile data.

The producer must live in `ministry`, resolve its own recipients and dedupe
identity, and emit only through the Core notification port after a successful
commit. It must not import Notification persistence or use Django signals. A
single-event change produces at most one notification per recipient. A batch
shift produces one summarized notification per recipient for the committed
batch, not one per Sunday. The owning slice must define a stable operation
identity/dedupe key and a recipient-safe target; an old-team leader may lose
anchor-only Board reachability after the change, so a Board link must not be
assumed accessible. Disabled Notifications remains a safe no-op.

This direct producer is separate from MO-S.6E. A committed selected-team change
has explicit before/after facts and can notify immediately. Detecting a later
roster membership/status change across every mutation path, deciding which
downstream schedules became stale, and avoiding noisy repeats remains the
harder MO-S.6E context/version problem. Existing member-facing assignment
notifications do not solve that cross-team warning.

Scheduler-facing copy should say **Worship Team** / **敬拜团队**, for example
"Current Worship Team" and "Change Worship Team." Reserve
`rotation_anchor_team`, "rotation anchor," pool, and path terminology for code,
staff setup, audit, or architecture documentation.

## 15. Consequences for MO-S.6D Excel import

The strict MO-S.6D-0A workbook decisions remain:

- known code-owned `.xlsx` contract; only `All 930` A:B for the Bethany 9:30
  profile in the first importer;
- explicit code-owned service-profile mapping;
- exact local date/time/type/profile identity;
- no fuzzy event or team matching, no hard-coded PKs, and no user/team creation;
- no formula evaluation; cached date results only under the recorded structural
  and weekly-sequence validation;
- preview before confirmation, expiring signed normalized proposal,
  confirmation-time reauthorization/revalidation, atomic fail-closed writes,
  idempotent no-op behavior, and visible classification of special/unsupported
  rows; and
- no assignment/member import in the first importer.

Revised first lifecycle:

- match/update one exact existing, non-draft, non-cancelled,
  audience-ready ServiceEvent;
- resolve each workbook token by explicit preview mapping to a current eligible
  candidate from that event's applicable configured Worship-pool union;
- classify any current Worship assignment for a different team, or any ordinary
  anchor change while a current Worship assignment exists, as a blocking
  conflict rather than moving or retagging a roster;
- surface existing downstream assignments as review impact without changing
  them;
- update `rotation_anchor_team` only; and
- never infer audience, Campus, Ministry Context, required teams, assignments,
  or serving from the workbook.

The prior recommendation to create `ServiceEventRequiredTeam` for the anchor
solely to bootstrap discoverability is **superseded**. Anchor-based operational
reachability is the cleaner domain rule. The importer must not claim required
coverage merely because a team owns the rotation.

Single-event authority and bulk import authority remain separate. A Worship-pool
Lead or event planner may be allowed to change one applicable event; that does
not authorize an annual workbook. The safest first upload/preview/confirm
boundary is staff/superuser only, rechecked at both preview and confirmation. A
later dedicated bulk-import capability may be considered after trial evidence;
do not reuse pool role, exact-team assignment authority, or audience as bulk
authority.

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
| 4B | **Narrow Worship Team authorization, write enforcement, and UI — IMPLEMENTED (`MO-S.6D-1D-B`, identity/serialization closure in `MO-S.6D-1D-B-FU1`)** | Consumes 4A from narrow GET/POST plus existing anchor/Worship-assignment write paths; pool Leads/planners receive only this action; current Worship identity is immutable and supported writes serialize on ServiceEvent; no model migration | actual denial/allow rules, locked-current reauthorization, stale form, combined union, legacy-form/admin/assignment bypass closure, cross-path identity retarget rejection, event-first lock path, LogEntry attribution, no roster move or unrelated writes | Rendered Worship Team selector, bilingual copy, conflict UX, hidden blocked controls, and narrow-context privacy verified in the implementation slices |
| 5 | **Worship Team operational reachability — IMPLEMENTED (`MO-S.6D-1D-C`; projection corrections `MO-S.6D-1D-C-FU1/FU2`)** | Team Schedule/Board queryset and projection change only; exact-team assignment permission unchanged; canonical eligibility fails closed; invalid raw selection never suppresses independent generic required/assignment participation; canonical ownership conflicts/ambiguity are review-only and non-actionable; no migration | selected-team-only rows, empty-coverage presentation, valid-selection de-dup, invalid required/assignment projection, off-team/out-of-scope conflict, multiple/duplicate ambiguity, global/exact-team behavior, planner/pool-Lead boundary, change/removal, privacy, no coverage/assignment/required-team writes | Rendered English desktop and Chinese mobile Team Schedule/Board QA completed in the implementation slice; FU1/FU2 are focused projection-only and test-verified |
| 6 | **Worship Rotation Planner — DOCS CONTRACT COMPLETE (`MO-S.6D-1D-D-0A`); READ-ONLY PREVIEW IMPLEMENTED (`MO-S.6D-1D-D-1A`); `1B` UNIMPLEMENTED** | Existing selector retains one-Sunday changes; `1A` adds the side-effect-free signed proposal/preview with no durable state; locked atomic confirmation/audit remains `1B`; no rule engine, roster mutation, or BatchRun schema | `1A`: exact event-chain/range/tail rules, destination eligibility, per-event authority, roster blocker, roster-free downstream impact, signed expiry/tamper, privacy, and zero writes. `1B`: stale/all-or-nothing rollback, shared-operation LogEntry audit, and downstream serialization closure remain future | `1A` preview/conflict UX verified in its implementation slice; confirmation/result UX remains required for `1B` |
| 7 | **Direct Worship Team change notification producer** | Ministry-owned post-commit producer through Core port; no notification permission/schema inference; summarized batch delivery | exact role/date recipients, required/additional downstream bounds, dedupe, language/privacy, disabled-module no-op, rollback/no-emission | Required for recipient-safe copy/target QA |
| 8 | **Excel dependency/parser + preview** | Reviewed `.xlsx` dependency and read-only upload/preview; staff/superuser only; no data write or migration expected | contract/header/date/cache/token/profile/identity classification, roster/downstream impact, size/privacy/tamper/expiry tests | Required for upload and preview |
| 9 | **Excel exact match/update confirmation** | Atomic existing-event selected-team writes only; no new event/required team/assignment; no schema if signed proposal remains sufficient | reauthorization, target locking/fingerprint, roster conflict, stale rollback, idempotency, eligible mapping, unsupported rows, audit attribution | Required for confirmation/result UX |
| 10 | **Later assignment import** | Deferred; would write TeamAssignment/member data and needs exact-team plus bulk authority and identity proof | unresolved/ambiguous people, explicit aliases, team ownership, no user creation, rollback/idempotency | Required; only after operational evidence |

Dependencies: slices 1, 2, 3, 4A, 4B, 5, and slice 6 read-only preview `1A`
are implemented; slice 6 locked confirmation `1B` remains future. Slice 1 remains
independent but should precede real multi-campus setup. Slices 2 and 3 both
precede 4B: pool configuration is required for pool-based authority/
applicability, and the implemented exact-event planner responsibility is
required for the approved event-planner workflow. Slice 4A defines the
read-only ownership facts; 4B enforces them for supported writes. Implemented
slice 5 now ensures an imported Worship Team can be operationally reachable
without false required coverage before slice 9. Slice 6 confirmation `1B`
remains separately approved and should precede using annual import as a batch
rotation tool. Slice 7 follows a proven change
path. Slice 8 precedes 9. Slice 10 remains later.

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

Architecture is closed enough for the proposed slices. The following details
remain for their owning implementation approval:

1. the exact Bethany 9:30 persisted location/Host profile mapping;
2. whether signed request-scoped import proposals are sufficient or durable
   `ImportRun` retention is required; and
3. the reviewed `.xlsx` library/version compatible with local and deployment
   Python runtimes.

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
