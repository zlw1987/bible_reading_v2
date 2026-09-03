# Generic Deployment Configuration Architecture

Status: **canonical architecture and schema freeze**. `GENERIC-DEPLOYMENT-CONFIG.0A`
completed the repository audit and froze the domain boundaries and proposed
schemas in this document. The runtime and migrations described here are
**unimplemented** unless a later status note explicitly says otherwise. Any
incompatible schema or domain change requires a separately approved architecture
revision; implementation tasks must not silently drift from this contract.

Implementation status: **`GENERIC-DEPLOYMENT-CONFIG.1A` — MinistryTeam stable
technical identity foundation — IMPLEMENTED / LOCAL VERIFIED;
`GENERIC-DEPLOYMENT-CONFIG.2A` — reviewed Ministry Team key configuration
tooling — IMPLEMENTED / LOCAL VERIFIED; and
`GENERIC-DEPLOYMENT-CONFIG.3A` — ServiceProfile + nullable ServiceEvent FK
expansion — IMPLEMENTED / LOCAL VERIFIED; and
`GENERIC-DEPLOYMENT-CONFIG.4A` — Service Profile identity audit + reviewed
mapping/backfill tooling — IMPLEMENTED / LOCAL VERIFIED.** The additive nullable unique
`MinistryTeam.team_key`, canonical normalization/validation, write-once ordinary
staff setup and Admin presentation, read-only identity inventory, and generic
dry-run-first reviewed configuration command are implemented. 2A itself applied
no normal-local or production configuration. The product-owner-reported current
SVCA production deployment later completed reviewed key configuration for all 11
current Ministry Team rows: 0 unconfigured and 0 identity integrity problems.
That remains deployment data; no runtime behavior depends on key text.

At the 3A milestone, the exact frozen `events.ServiceProfile` table and nullable protected
`ServiceEvent.service_profile` FK through `events/0012`, with key
normalization/validation, referenced identity immutability, transition
consistency validation, existing scheduling-revision integration, and bounded
technical Admin support. Existing events remain FK `NULL` and
`service_profile_key` remains authoritative. No profile row was created or
inferred, no FK was backfilled, and no readiness/setup/workbook consumer was
switched in 3A. Profile defaults/materialization, integration gating,
MO-S.REQUIRED runtime, and external identity mapping remain unimplemented and
separately gated.

4A adds the generic read-only `audit_service_profile_identity` inventory and
the dry-run-first `configure_service_profile_mapping` command. The inventory
reports every exact legacy key/event-type group, blank-key events, every
ServiceProfile row, dual-identity consistency, drift, and multi-type-key
blockers without deployment-specific defaults or data writes. The mapping
command creates one operator-supplied reviewed profile and backfills the
complete exact legacy-key target set only after a versioned, deterministic,
current-state-bound confirmation token is reviewed. Apply uses the existing
ascending scheduling-revision CAS as SQLite's first-write serialization
boundary, rechecks complete current truth, advances every target revision
exactly once, and rolls back the profile plus every event change on any stale,
busy, validation, or write failure. 4A applied no normal-local or production
profile mapping. Current readiness, setup/reset, workbook, signing/fingerprint,
and operational lookup consumers still use `service_profile_key`; the Slice 5
consumer switch remains pending.

## 1. Product Deployment Model

The product is one generic CMS codebase installed independently by different
churches. Each installation owns its own database, Church Structure, Ministry
Teams, Service Profiles, enabled modules, and optional integrations.

This is **not** a SaaS multi-tenant architecture. No `Church`, `Tenant`, tenant
foreign key, tenant-bound uniqueness rule, or cross-church data partition is
introduced. Deployment-global below means global inside one installation and
database, not across every church.

A deployment may omit a ministry team, combine several functions into one
team, name teams differently, use another Worship hierarchy, or connect the CMS
to another system. Generic CMS behavior must continue to work in all cases.

## 2. Genericity Rule

Keep three layers distinct:

1. **Generic CMS domain** owns reusable models and invariants such as
   `ServiceEvent`, `ServiceProfile`, `MinistryTeam`, explicit required teams,
   Worship governance, and scheduling revision.
2. **Deployment configuration** is local database data such as profile keys,
   team keys, profile default requirements, Church Structure rows, and enabled
   integration keys.
3. **Deployment adapters** are explicitly named, optional code paths for a real
   external file or system contract. They translate into local canonical CMS
   models and never redefine those models.

SVCA, Bethany, 09:30, Lighting, Sound, Camera, Projection, Digital Ministry,
A, C1, C2, C3, Chinese Worship, Main Campus, and Tri-Valley are not universal
CMS concepts. They may appear in one deployment's data, a clearly named
adapter, bounded historical/setup tooling, or tests. They must not become
behavior gates in generic business logic.

## 3. Identity Model

| Identity | Meaning | Portability |
|---|---|---|
| Database primary key | Internal relational identity in one database. Foreign keys and transactional writes use it. | Not portable and never hard-coded as deployment configuration. |
| Local stable machine key | Human-reviewed deployment-local identity such as `MinistryTeam.team_key` or `ServiceProfile.key`. | Portable within that deployment's configuration; not an external-system ID. |
| External identity | An ID, GUID, or code owned by one external system. | Interpreted only by a future adapter/mapping layer; never silently a local PK or key. |

Names and bilingual labels are mutable presentation, never identity.
Resemblance by name, time, title, location, audience, hierarchy, or Worship Team
is human-review evidence only.

### 3.1 Ministry Team identity verdict

`MinistryTeam` needs a stable local machine identity. The exact field name is
**`team_key`**.

Current `MinistryTeam` identity is only its database PK plus mutable display
fields. `team_kind`, `is_assignable`, `is_worship_rotation_pool`, and role
profiles are explicit taxonomy/behavior/configuration fields; none is a stable
portable identity and none should be overloaded as one.

`team_key` is preferred over `code` because ministry role types/profiles already
use `code` for taxonomy and Church Structure uses parent-scoped `code`; over
`slug` because this is not a URL/presentation slug; and over `external_key`
because this is local CMS identity, not an external identifier.

Canonical invariants:

```text
team_key != team type
team_key != behavior
team_key != permission
team_key != serving
team_key != Worship classification
team_key != audience
team_key != default-required status
team_key != hierarchy
team_key != external-system identity
```

Generic code must not branch on key text. Equality, suffix, prefix, substring,
and pattern inference such as `team_key == "lighting"`,
`team_key.endswith("_worship")`, or checking for `"camera"` are forbidden.
Behavior remains on explicit fields and relationships such as `is_assignable`,
`is_worship_rotation_pool`, roles, audience, profile requirements, and
assignments.

## 4. Exact Frozen Proposed Schemas

These are target schemas, not current models at the time of this docs-only
freeze.

### 4.1 `ministry.MinistryTeam.team_key`

| Property | Frozen contract |
|---|---|
| Field | `team_key` |
| Type | `models.CharField(max_length=64, null=True, blank=True, unique=True)` |
| Grammar | `^[a-z0-9_.-]+$` when non-null |
| Normalization | trim whitespace, lowercase, convert empty to `None`, then validate |
| Scope | unique across all non-null Ministry Teams in one deployment/database |
| Indexing | the unique constraint/index is sufficient; no redundant `db_index=True` |
| Initial population | existing rows become `NULL`; no name-, PK-, hierarchy-, or role-based automatic backfill |

Multiple unconfigured teams are supported through `NULL`. Empty string is not
the canonical blank because a portable globally unique field cannot allow many
`""` rows. Database uniqueness supplements model/form normalization.

The key is write-once through normal setup surfaces: an existing `NULL` may be
set after explicit review, but a non-null key is not casually editable. A typo
or exceptional rename requires a reviewed maintenance workflow that audits
adapters, configuration, signed contracts, and external mappings. Human names
remain mutable.

The implementation surface is Django Admin plus the existing staff/superuser
Ministry Structure setup boundary. Ordinary team/member/scheduling forms do not
edit it. Copy must state that it grants no behavior, permission, membership,
serving, or hierarchy.

`GENERIC-DEPLOYMENT-CONFIG.2A` adds the generic operator command
`configure_ministry_team_keys`. It accepts only invocation-supplied exact
`MinistryTeam` PK -> reviewed canonical `team_key` mappings; source code contains
no deployment-specific mapping. Dry-run is the default and prints deterministic
review evidence plus a `TEAM_KEY_CONFIG_PLAN_V1` SHA-256 confirmation token over
canonical JSON binding the exact target IDs, current/proposed keys, reviewed
team metadata, and exact safe primary-path evidence. Apply requires both
`--apply` and that exact current token, rebuilds and rechecks current truth,
then performs ordered atomic conditional `team_key IS NULL` CAS updates. It
cannot overwrite or rename a configured key. The command advances the target
row's normal `updated_at` timestamp and changes no other domain state. 2A adds
no runtime consumer and applied no normal-local or production key data.

### 4.2 `events.ServiceProfile`

`ServiceProfile` is a first-class event/gathering concept already implicit in
repeated `ServiceEvent.service_profile_key`, readiness/setup, and annual
workbook matching. The `events` app owns it.

Current repository truth after `GENERIC-DEPLOYMENT-CONFIG.3A` includes the
first-class profile table below plus a nullable protected
`ServiceEvent.service_profile` FK. The optional non-unique
`ServiceEvent.service_profile_key` string (`max_length=64`, blank/default empty)
remains authoritative during this expansion phase. Its consumers remain profile
readiness and reset/setup services and commands, Admin, the strict workbook
preview and confirmation services, proposal/reset fingerprints and signing
contracts, and their focused tests. No consumer switched in 3A; every one must
move together during the later switch phase.

| Field | Exact type and policy |
|---|---|
| `key` | `CharField(max_length=64, unique=True)`; required; grammar `^[a-z0-9_.-]+$`; trim/lowercase before validation |
| `name` | `CharField(max_length=160)`; required local/default-language staff label |
| `name_en` | `CharField(max_length=160, blank=True, default="")` |
| `description` | `TextField(blank=True, default="")` |
| `description_en` | `TextField(blank=True, default="")` |
| `event_type` | `CharField(max_length=40, choices=ServiceEvent.EVENT_TYPE_CHOICES)`; required |
| `is_active` | `BooleanField(default=True)` |
| `created_at` | `DateTimeField(auto_now_add=True)` |
| `updated_at` | `DateTimeField(auto_now=True)` |

`description_en` follows the repository's bilingual staff-facing configuration
convention; it adds no runtime behavior. No sort order is needed. No recurrence,
default time/location/audience/planner/Worship field, or arbitrary JSON belongs
on V1 `ServiceProfile`.

`event_type` belongs because current profile contracts bind key and event type,
and a profile must not span incompatible event categories. The key is
deployment-global unique. Key and event type become immutable in normal setup
after a ServiceEvent or profile-ministry requirement references the profile.
Names, descriptions, and active state remain editable.

An inactive profile may remain on historical events. It cannot be newly
selected or materialized. Referenced profiles are protected from deletion.

### 4.3 `events.ServiceEvent.service_profile`

```python
service_profile = models.ForeignKey(
    "events.ServiceProfile",
    null=True,
    blank=True,
    on_delete=models.PROTECT,
    related_name="service_events",
)
```

One event has zero or one profile. A referenced profile's `event_type` must
equal the event's `event_type`; portable model/forms/services validation and
auditing enforce this cross-row invariant.

Changing an existing event's profile uses the existing
`ServiceEvent.save()` `scheduling_revision` boundary. Ordinary member event
forms do not expose technical identity. Admin/setup and future profile-aware
creation may expose active-only profile choices with clear copy.

### 4.4 `ministry.ServiceProfileMinistryRequirement`

The exact relationship name/owner is
**`ministry.ServiceProfileMinistryRequirement`**. The relationship belongs to
ministry because it applies Ministry Team configuration and the module registry
already declares `ministry -> events`.

| Field | Exact type and policy |
|---|---|
| `service_profile` | FK to `events.ServiceProfile`, `on_delete=CASCADE`, `related_name="ministry_requirements"` |
| `ministry_team` | FK to `ministry.MinistryTeam`, `on_delete=PROTECT`, `related_name="service_profile_requirement_links"` |
| `is_active` | `BooleanField(default=True)` |
| `sort_order` | `PositiveIntegerField(default=0)` |
| `created_at` | `DateTimeField(auto_now_add=True)` |
| `updated_at` | `DateTimeField(auto_now=True)` |

Add one unconditional unique constraint on `(service_profile, ministry_team)`.
A row is deactivated/reactivated rather than duplicated. `sort_order` is
presentation only.

An active requirement must reference an active profile and active assignable
team. Non-assignable containers and Worship pools cannot be defaults. An
assignable team resolving through a configured Worship rotation pool also
cannot be a static profile default. Other arbitrary active assignable teams are
valid; there is no universal Lighting/Sound/Camera/etc. taxonomy.

Inactive rows may retain history when configuration is retired. Readiness
reports active requirements made invalid by later profile/team changes.
Deleting an unreferenced profile cascades only owned configuration rows;
ServiceEvent `PROTECT` retains history. Referenced teams are protected.

The initial surface is Admin/staff setup, not an ordinary member or scheduler
form. It uses keys for identity and human names for confirmation.

## 5. ServiceEvent/Profile Transition

The current optional, repeated, non-unique `service_profile_key` is not
permanently retained. The target is one FK; permanent dual identity would
create drift. Removal is a later contract phase, never initial expansion.

Use expand/migrate/switch/contract:

1. **IMPLEMENTED / LOCAL VERIFIED in 3A:** add `ServiceProfile` without changing
   existing event identity data.
2. **IMPLEMENTED / LOCAL VERIFIED in 3A:** add nullable
   `ServiceEvent.service_profile`; leave rows unchanged with FK `NULL`.
3. **IMPLEMENTED / LOCAL VERIFIED in 4A:** read-only generic audit of distinct
   nonblank legacy keys and every event/type/key/FK use, plus blank-key and
   ServiceProfile-table evidence.
4. **IMPLEMENTED / LOCAL VERIFIED as reviewed tooling in 4A:** product-owner
   review may create one profile per accepted exact key/type. One key used
   across conflicting event types is a blocker; 4A itself applied no
   normal-local or production mapping.
5. **IMPLEMENTED / LOCAL VERIFIED as reviewed tooling in 4A:** dry-run then
   separately approved apply maps one exact key to one newly created exact
   profile. Unmapped, malformed, ambiguous, existing-profile, already-mapped,
   or type-conflicting data fails closed; never infer from resemblance.
6. While both fields exist, supported identity writes preserve
   `service_profile.key == service_profile_key`; retain a drift audit.
7. Switch readiness/setup, workbook preview/confirmation, Admin, tests,
   reset-surface fingerprints, signed contracts, and every discovered consumer
   to FK/profile key.
8. Prove zero runtime legacy-string dependency and exact target-data
   consistency by repository search, focused tests, and target audit.
9. Separately approve removal of `service_profile_key`; historical migrations
   and clearly historical docs may retain the name.

The documented 52 canonical 2026 `bethany_0930_cm` events map by exact
persisted key and are preserved; they are not recreated merely to adopt the FK.

## 6. Profile Ministry Defaults

Defaults answer: when an event is intentionally initialized from this profile,
which static Ministry Teams should be proposed/materialized as event
requirements? They do not answer which teams are required at query time and do
not grant authority, audience, membership, serving, assignment, Worship
eligibility, or recurrence.

Defaults are deployment data. One church may configure
production/livestream/ushers/parking; another may configure a different set or
none. Generic code never creates a named default team.

## 7. Materialization Semantics

```text
ServiceProfile Ministry defaults (configuration/template)
    -> explicit reviewed materialization
ServiceEventRequiredTeam rows (individual event operational truth)
    -> coverage and scheduling consumers
```

There is no live inheritance. Editing defaults never silently changes an
existing event.

### 7.1 New events

Automatic initialization is allowed only at one explicit creation boundary:

- the caller intentionally chooses an active profile;
- the profile/defaults are displayed and reviewable in that workflow;
- the new event and explicit RequiredTeam rows are created in one transaction
  through a central initialization service.

This may support future profile-aware single/recurring creation or an enabled
adapter only when the caller explicitly invokes that service. It is never a
signal, implicit `ServiceEvent.save()` side effect, startup task, or background
sweep. No profile means no defaults. Changing an existing event's profile does
not initialize/delete requirements.

A new event has no pre-existing scheduling reader, so atomic initial creation
uses the normal creation revision. The transaction rolls back on failure.

### 7.2 Existing events

Existing/future already-created events use a separate preview/apply workflow:

1. explicitly select profile and bounded event/date scope;
2. show current rows, active defaults, missing additions, manual extras,
   invalid/inactive rows, and expected `scheduling_revision` values;
3. bind the proposal to exact event IDs, revisions, profile/default identity,
   and current rows;
4. on POST, claim changed events in ascending ID order via existing CAS;
5. reload, reauthorize, and recompute inside one transaction;
6. add only approved missing rows and audit changed events;
7. roll back on stale, busy, authorization, configuration, validation, save,
   or audit failure.

Unique `(service_event, ministry_team)` plus recomputation makes addition
idempotent. Replays fail stale; a fresh no-op preview has no apply action.

Manual/extra RequiredTeam rows are preserved. Removing/deactivating a default
does **not** delete an event row. Any future removal workflow needs separate
explicit row review. Materialization emits no current notification. Audit uses
one operation ID and changed-event detail without private roster data.

## 8. Worship Is a Separate Dynamic Axis

```text
effective required teams
    = explicit ServiceEventRequiredTeam rows
      UNION exact valid selected Worship Team
```

The selected Worship Team comes only from governed event state
(`rotation_anchor_team`) when canonical governance reports
`selected_team_is_eligible`. It is de-duplicated by exact database identity and
is not persisted as a RequiredTeam row merely for coverage.

No/invalid selection fails closed for the derived member. Ownership conflict
or ambiguity remains separate and is not clean coverage. Pool membership,
leadership, rotation tokens, and profile defaults do not imply each other.

A/C1/C2/C3 or another deployment's rotating children are not static defaults.
`rotation_anchor_team` is not a profile default. Profiles may materialize
static downstream teams; selected Worship remains event-specific.

## 9. Module Ownership and Migration Dependency

- `MinistryTeam.team_key`: `ministry`.
- `ServiceProfile` and `ServiceEvent.service_profile`: `events`.
- `ServiceProfileMinistryRequirement`: `ministry`.
- integration registry/settings: Core configuration; adapter code stays in an
  explicitly deployment-specific namespace owned by its functional modules.

This follows registered `ministry depends_on events` and avoids moving existing
models for theoretical purity.

At the `GENERIC-DEPLOYMENT-CONFIG.1A` milestone,
`ministry/0006_ministryteam_team_key` implements the additive nullable unique
`MinistryTeam.team_key` foundation. At the
`GENERIC-DEPLOYMENT-CONFIG.3A` milestone,
`events/0012_serviceprofile_serviceevent_service_profile` implements the exact
frozen ServiceProfile table plus nullable protected event FK. It contains no
`RunPython`, row creation, inference, or backfill.

The remaining planned migration direction is:

```text
ministry/0006 = implemented MinistryTeam.team_key foundation

events/0012 = implemented ServiceProfile + nullable ServiceEvent.service_profile

GENERIC-DEPLOYMENT-CONFIG.4A = implemented audit/configuration tooling only;
no migration and no automatic data operation

ministry/0006 + events/0012
    -> future create ministry.ServiceProfileMinistryRequirement
```

The events profile migration does not depend on the new ministry relationship.
The ministry relationship may depend on both foundations. Existing historical
cross-app edges (`ministry/0002 -> events/0001` and
`events/0003 -> ministry/0002`) remain a valid DAG; no new reverse edge creates
a cycle.

## 10. Deployment-Specific Adapter Boundary

The existing 2026 SVCA/Bethany Worship XLSX code is a valid specialized
adapter, not a generic importer. Its unqualified staff exposure and
unconditional imports are not the target boundary.

Freeze a small explicit registry, not a plugin framework:

- setting: **`CMS_ENABLED_INTEGRATIONS`**;
- absent, `None`, or empty means no deployment integrations;
- registered keys initially include
  **`svca_bethany_2026_worship_xlsx`** and, while retained,
  **`svca_lighting_pilot_csv`**;
- each entry declares required modules; workbook requires `events` + `ministry`;
- unknown keys or unmet module dependencies raise `ImproperlyConfigured` when
  configuration is evaluated;
- disabled means no entry point, no adapter query, and direct-route fail-closed
  regardless of staff status.

Unlike `CMS_ENABLED_MODULES`, absence never means enable all. Adapters are
opt-in so another church cannot accidentally see SVCA UI.

Current URL names may remain, but views must gate them and imports must be
lazy/isolated so disabled deployments do not load adapter code. Later move the
adapter under an explicit namespace such as
`ministry/integrations/svca_bethany_2026_worship_xlsx/`. Generic Worship
Planning provides selector/planner plus enabled adapter links. Future adapters
are explicitly registered: no auto-discovery, hook bus, or plugin SDK.

The Lighting pilot has the same boundary problem plus name-based team identity.
If retained, gate it and migrate to `team_key` mapping or retire it.

## 11. Future External-System Integration Boundary

```text
external system -> adapter/sync -> mapping layer
    -> local canonical CMS models -> CMS modules
```

Modules do not query an external database as canonical runtime truth. Adapters
validate/map into approved local models; local permissions, audience, serving,
and integrity still apply.

No `ExternalObjectMapping` schema is frozen because no real API, vocabulary,
uniqueness scope, deletion policy, or sync ownership exists. A later task must
derive it from an actual system. It may map external IDs to local PKs and use
local keys for reviewed configuration, but cannot overload identity layers.

## 12. Repository Genericity Audit

| Finding | Class | Verdict |
|---|---|---|
| ServiceEvent/audience/required-team models; MinistryTeam taxonomy/assignability; roles; Worship pools/governance | A. Acceptable generic domain | Explicit fields/relationships drive behavior. |
| Parent-scoped Church Structure codes and generic role/profile codes | A. Acceptable generic domain | Local configuration/taxonomy precedent; not deployment-global team identity. |
| Strict SVCA/Bethany 2026 XLSX contract | B. Acceptable explicit deployment adapter | Strict constants are correct inside a named adapter; exposure/placement still need work. |
| Bethany rebuild, CHURCH -> campus -> CM resolver, readiness defaults | C. Acceptable one-time historical setup | Bounded operator/history tooling, not generic runtime; future tooling should be profile-data-driven. |
| Legacy SVCA reading import and SVCA readiness-policy seed | C. Acceptable deployment/historical setup | Explicit command only; keep named and never auto-run. |
| Workbook card/URLs shown to all staff when modules enabled | D. Should be configuration-gated | New opt-in setting must hide and fail-close routes. |
| Lighting pilot CSV route/UI | D. Should be configuration-gated | Another deployment must not see/invoke it merely because ministry is enabled. |
| Unconditional XLSX imports in generic events forms/views and Lighting imports in ministry views | E. Genericity violation / future refactor | Isolate/lazy-load under explicit integration ownership. |
| Lighting pilot name matching/normalization | E. Genericity violation / future refactor | Mutable names are treated as identity and one taxonomy is encoded; use reviewed key mapping or retire. |
| Generic team-form placeholder "Lighting Team" | E. Minor genericity debt | Replace with neutral example copy; no current domain behavior effect. |
| Tests using Bethany/named teams/A-C tokens | F. Deferred, no current impact | Representative fixtures are acceptable when not asserted as universal taxonomy. |
| Generic `CHURCH` root seed | A. Acceptable generic domain | One local root concept; Bethany/CM assumptions remain bounded setup. |

Historical docs may record exact SVCA production facts. Current/future generic
instructions must label them as one deployment's configuration.

## 13. Production Compatibility and Risk

This audit did not inspect or mutate production. Assessment uses repository and
documented production contracts.

| Area | Risk | Protection |
|---|---|---|
| Nullable team key | LOW | Additive; existing rows stay valid `NULL`; no runtime switch. |
| ServiceProfile table | LOW | Additive/unreferenced. |
| Nullable event profile FK | LOW-MEDIUM | Additive; preserve Admin/model/revision behavior. |
| Reviewed profile creation/FK backfill | MEDIUM | Touches identity including 52 canonical rows; exact key/type + dry-run. |
| Dual consistency/consumer switch | MEDIUM-HIGH | Readiness, setup fingerprints, workbook signing/confirmation, tests, Admin change together. |
| Profile-ministry table | LOW-MEDIUM | Additive; reject inactive/non-assignable/Worship-rotation teams. |
| Production default-team configuration | MEDIUM | Keys require human review; no names/PK inference; existing rows untouched. |
| Existing-event materialization | MEDIUM-HIGH | Creates operational truth; bounded preview, CAS, atomicity, idempotency, audit. |
| Integration gating/refactor | MEDIUM | No data write, but missing setting could hide current workflow; configure before cutover. |
| MO-S.REQUIRED runtime | MEDIUM | Changes coverage/gaps while preserving dedicated Worship and explicit-only notification semantics. |
| Legacy string removal | HIGH | Destructive; zero references/consistency/rollback/separate approval required. |

Existing anchors, explicit requirements, assignments, LogEntry/Notification
history, and dedupe history are not rewritten. Revisions change only for
supported existing-event profile/materialization writes. Workbook contract
versions change when identity payloads change; old proposals fail closed.

## 14. Recommended Implementation Slices

Each slice requires separate approval.

| Slice | Purpose/impact | Gate and review |
|---|---|---|
| 1. Team identity foundation | Add nullable unique key, validation/immutability, setup/Admin, tests, read-only inventory; no backfill. LOW. | Additive migration; product owner reviews field/copy. |
| 2. Team key configuration | **IMPLEMENTED / LOCAL VERIFIED (`GENERIC-DEPLOYMENT-CONFIG.2A`)** as `configure_ministry_team_keys`: generic exact-PK reviewed plan, versioned state-bound token, atomic NULL-only CAS apply, and independent post-audit direction. 2A itself applied no configuration; the product owner later reported SVCA production at 11 configured current teams, 0 unconfigured, and 0 identity integrity problems. MEDIUM operationally. | Stop on duplicate/malformed/noncanonical/unreviewed or stale state; owner reviews every apply. |
| 3. Service Profile/FK expand | **IMPLEMENTED / LOCAL VERIFIED (`GENERIC-DEPLOYMENT-CONFIG.3A`)**: exact frozen profile model, nullable protected FK, validation/immutability/revision/Admin foundations, additive migration, and disposable migration proof; legacy string remains authoritative and no rows/FKs were created or backfilled. LOW-MEDIUM. | Profile rows reviewed before creation; Slice 4 remains the mapping/backfill gate. |
| 4. Profile mapping/backfill | **IMPLEMENTED / LOCAL VERIFIED (`GENERIC-DEPLOYMENT-CONFIG.4A`)**: generic read-only key/type/FK inventory plus one-key-at-a-time reviewed profile creation and complete exact-target FK backfill; `SERVICE_PROFILE_MAPPING_PLAN_V1` binds full metadata and current event state, existing scheduling CAS supplies SQLite serialization and exactly-once revision advance, and independent post-audit proves dual consistency. 4A applied no normal-local or production mapping. MEDIUM operationally. | Stop on conflict/unmapped/noncanonical/ambiguity/existing profile/non-null FK/stale/busy state; owner reviews every target apply. |
| 5. Integration boundary + consumer switch | Registry/gates, isolate SVCA adapters, configure deployment, switch readiness/setup/workbook/Admin/signing to FK with drift audit. MEDIUM-HIGH. | Focused adapter/workbook regressions and deployment setting review; old payloads fail closed. |
| 6. Profile ministry defaults | Add relation, validation/readiness, Admin/setup; no event materialization. LOW-MEDIUM. | Stop on invalid/inactive/non-assignable/Worship mapping; owner reviews configuration. |
| 7. Materialization/drift | Central new-event initialization and existing-event preview/CAS/apply/audit; additions only. MEDIUM-HIGH. | Exact dry-run, stale/busy/rollback/idempotency tests; owner reviews every production apply. |
| 8. MO-S.REQUIRED runtime | Effective resolver and bounded coverage/gap/Event-detail consumers; notifications/persisted audits explicit-only. MEDIUM. | Validate Team Schedule, Board, Today/leader attention, Staff Overview, event detail; review 52-event projection. |
| 9. Production configuration/QA | Enable approved integrations, verify identity/default data, preview/materialize approved scope, focused QA. MEDIUM-HIGH operationally. | Backup/rollback and reviewed dry-run before apply; owner required. |
| 10. Legacy contract retirement | Prove zero string consumers/drift, remove old field/tools in separate migration/docs slice. HIGH. | Last only; explicit destructive-schema approval. |

This avoids both micro-slice churn and an unsafe mega-task. Expansion, reviewed
data, runtime switching, and contract cleanup stay independently governed.

## 15. Deferred Items

- multi-tenancy or Church/Tenant model;
- generic plugin framework, auto-discovery, event bus, or hook SDK;
- `ExternalObjectMapping` without a real external contract;
- recurrence/default time/location/audience/planner/Worship profile fields;
- arbitrary profile JSON;
- live inheritance or automatic deletion of event requirements;
- automatic team creation from adapters;
- full event-template engine;
- broader assignment/member import or notification producers;
- generic external-database runtime reads.

## 16. Future Testing and Verification

Future slices require focused:

- key/profile validator, uniqueness, immutability, type-consistency, active,
  assignable, Worship-separation, and delete-protection tests;
- additive migration/dependency inspection;
- deterministic zero-write audits and guarded dry-run/apply command tests;
- materialization exact-scope, extras-preserved, no-delete, idempotency, CAS,
  stale/busy, rollback, and audit-failure tests;
- effective-required coverage/Team Schedule/Board/Today/Staff Overview/Event
  detail tests;
- disabled-adapter no-UI/direct-route/no-query tests plus unknown/unmet-key
  configuration validation;
- strict XLSX parser/signing/preview/confirmation/52-target, governance
  fingerprint, scheduling revision, and NOTIFY.1G regressions;
- searches for no key-behavior inference, name/PK mapping, and eventually no
  legacy string runtime dependency;
- `makemigrations --check --dry-run`, `manage.py check`, focused Django tests,
  `git diff --check`, and exact dirty-set review;
- target dry-run and product-owner review before data apply.

Browser QA is needed only for rendered setup/adapter/materialization changes and
must not be claimed unless actually performed.

## 17. Forbidden Shortcuts

Do not hard-code production PKs; match mutable names as identity; infer behavior
from keys; define universal named-team taxonomy; live-inherit profile defaults;
delete event rows because defaults changed; persist rotating Worship children as
static defaults; collapse audience/belonging/authority/serving/hierarchy; query
an external DB as module canonical truth; overload external IDs; expose SVCA
adapters through generic module enablement; or retain permanent dual profile
identity without an audited retirement plan.

## 18. Architecture Change Policy

Every future task touching team identity, Service Profiles, defaults,
materialization, effective required teams, integration gating, or external
mapping must read this file first.

Compatible details may be resolved in an approved slice. Any incompatible field
name/type, identity scope, ownership, delete rule, materialization semantic,
Worship boundary, integration default, or external authority requires an
explicit architecture revision and product-owner review. Silent drift is not
allowed.
