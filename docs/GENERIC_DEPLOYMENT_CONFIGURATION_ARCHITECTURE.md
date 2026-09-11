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
mapping/backfill tooling — IMPLEMENTED / LOCAL VERIFIED / PRODUCTION APPLY
COMPLETE / PRODUCTION POST-AUDIT VERIFIED for the reviewed SVCA mapping; and
`GENERIC-DEPLOYMENT-CONFIG.5A` — repository-wide read-only Slice 5 audit and
docs-only implementation planning — COMPLETE, with no Slice 5 runtime behavior
implemented by 5A; and `GENERIC-DEPLOYMENT-CONFIG.5B` — explicit integration registry,
fail-closed gates, and lazy import isolation — IMPLEMENTED / LOCAL VERIFIED;
and `GENERIC-DEPLOYMENT-CONFIG.5C` — canonical ServiceProfile runtime identity
seam — IMPLEMENTED / LOCAL VERIFIED; and `GENERIC-DEPLOYMENT-CONFIG.5D` —
ServiceProfile readiness V2, bounded reset V2, and ServiceEvent Admin consumer
switch — IMPLEMENTED / LOCAL VERIFIED; and
`GENERIC-DEPLOYMENT-CONFIG.5E` — Worship XLSX FK matching, current-truth
confirmation, and V2 signed contracts — IMPLEMENTED / LOCAL VERIFIED; and
`GENERIC-DEPLOYMENT-CONFIG.5F` — transition-closure audit and local closure
proof — **PRODUCTION CLOSEOUT COMPLETE / VERIFIED.**
The additive nullable unique
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
switched in 3A. Integration gating is implemented by 5B. The non-workbook
readiness, bounded reset, and Admin consumers are switched by 5D; workbook
matching/signing is FK/Profile-authoritative after 5E. Profile-ministry default
schema, validation, Admin, audit, and reviewed configuration tooling are
implemented through 6A/6B. **`GENERIC-DEPLOYMENT-CONFIG.6B — PRODUCTION
CONFIGURATION APPLY COMPLETE / VERIFIED`**: the reviewed SVCA deployment has
four active valid static ministry defaults for `bethany_0930_cm`, and a fresh
same-set dry-run proves the configuration idempotent. Slice 7A production
read-only preview evidence is verified. **`GENERIC-DEPLOYMENT-CONFIG.7B —
PRODUCTION MATERIALIZATION APPLY COMPLETE / VERIFIED`**: the separately
reviewed `2026-09-08` through `2026-12-31` existing-event scope is closed with
64 explicit static-default pairs and zero missing/blockers. Historical backfill
remains deliberately deferred. **`GENERIC-DEPLOYMENT-CONFIG.7C-1A` —
IMPLEMENTED / LOCAL VERIFIED** implements the 7C-0A/FU1 contract for ordinary
single and recurring creation: optional reviewed profile-default suggestions,
an explicit final RequiredTeam set, and one atomic events-owned creation
boundary. Profileless creation remains supported. **`MO-S.REQUIRED.1A —
IMPLEMENTED / LOCAL VERIFIED / PRODUCTION RUNTIME VERIFIED`** adds the
separately gated effective-required read/runtime consumer slice; external identity mapping remains unimplemented
and separately gated. The
production consumer-switch closeout is complete and verified.

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
busy, validation, or write failure. The 4A implementation task itself applied
no normal-local or production mapping; the product owner later completed and
independently audited one reviewed production mapping on the SVCA deployment.
At the 4A milestone, readiness, setup/reset, workbook, signing/fingerprint, and
operational lookup consumers still used `service_profile_key`; the apply
reported `runtime_consumer_switched: false`. 5D later switched the three
non-workbook consumers, and 5E later switched the workbook consumer. Formal
local Slice 5 closure is proved by 5F; its production read-only closeout is
now verified.

`LIGHTING-PILOT-RETIRE.1A` — **IMPLEMENTED / LOCAL VERIFIED** — retires the
obsolete Lighting Pilot CSV integration from active code. It is no longer
registered, routable, callable through a management command, or supported as a
deployment adapter. The product owner selected retirement rather than
`MinistryTeam.team_key` modernization. Historical canonical rows once created
by the pilot remain ordinary model data and were not changed.

5B added the static Core `CMS_ENABLED_INTEGRATIONS` registry. Absent, `None`,
or empty configuration enables no integration. At that milestone the named
SVCA/Bethany 2026 Worship XLSX and Lighting Pilot CSV integrations each
required the enabled `events` and `ministry` modules; unknown keys and unmet
dependencies failed with `ImproperlyConfigured`. The workbook routes and the
then-retained Lighting route/command failed closed when disabled, and generic
events/ministry imports no longer loaded either adapter service or `openpyxl`.
`LIGHTING-PILOT-RETIRE.1A` later removed the Lighting surfaces and registration;
the retired key is now unknown. No adapter service file moved in 5B. 5E later
versioned the workbook contracts and made `service_profile_key` compatibility/
drift evidence rather than workbook identity authority. Overall
source/runtime consumer-switch closure is proved locally by 5F; deployment
configuration/data/rendered proof is verified by the completed production
closeout.

5C adds `events.service_profile_runtime`, the generic events-owned inspection,
strict resolution, and pair-write/clear boundary for future profile-aware
consumers. Inside this seam, the FK-linked `ServiceProfile` is authoritative;
the compatibility string is drift evidence only and is never used for profile
lookup or inference. The seam distinguishes profileless, legacy-only, exact,
FK/blank-key, FK/key-mismatch, and event-type-mismatch states. Inactive exact
profiles remain valid identity, while callers may separately require active
state. Explicit normal assignment/clear writes the exact pair through the
existing validated `ServiceEvent.save()` boundary, advances an existing
event's scheduling revision exactly once, and avoids writes/revisions for
exact no-ops. Drifted states are not silently repaired. 5C switched no
readiness, setup/reset, Admin, or workbook consumer; no workbook/reset signed
contract changed and `runtime_consumer_switched` remains false globally.

5D switches exactly three non-workbook consumers to that seam. Readiness V2
resolves the requested stable key to one actual active, type-compatible
`ServiceProfile`, requires schema through `events/0012`, selects canonical rows
by FK, and reports legacy-only, profileless, and drift states as blocker or
review evidence without fallback. The retained Bethany 2026 TEST reset resolves
the reviewed profile during preview and again inside apply before deletion,
binds profile plus event FK/key state in its V2 approval, and creates exact
dual-identity revision-0 rows. No reset was executed by 5D. ServiceEvent Admin
now selects the FK, shows the compatibility key read-only, preserves a current
inactive exact profile for historical review, and prepares exact pair changes
in memory before one normal `ServiceEvent.save()` and one existing-event
revision advance. Ordinary event forms remain unchanged. Workbook preview and
confirmation were deliberately untouched by 5D.

5E switches the explicit SVCA/Bethany 2026 Worship XLSX adapter. It resolves
the configured stable profile key to the actual active, Sunday-service
`ServiceProfile`, matches target events by FK, and uses the 5C seam to require
exact dual identity. Legacy-only, missing-FK, FK/key drift, event/profile type
drift, inactive/missing target profile, and other-profile ownership fail closed
without fallback. Parsed, normalized-preview, and confirmation signed artifacts
are strict V2 contracts binding the integration key and exact profile PK/key/
type; every V1 artifact is rejected. Confirmation re-resolves the configured
profile after scheduling-revision CAS and requires each reloaded event to remain
exact before any anchor save, so failure rolls back claims, anchors, and audit
rows atomically. No schema, migration, backfill, production command, or
production data change occurred. `service_profile_key` remains stored as drift
evidence and rollback compatibility. All known profile-aware runtime consumers
have now been switched.

5F reruns the repository-wide inventory after 5E and proves that no Class-A
runtime consumer uses the compatibility string as ServiceProfile identity
authority. The surviving active-code references are limited to transition/drift
evidence and guards, supported dual-storage writes, and bounded operator/setup/
mapping history. The existing generic read-only identity inventory is extended
only with separate legacy-only, FK/blank-key, FK/key, and event/profile-type
drift counts required for deployment closeout. No field, schema, signing,
readiness, Admin, mapper, or reset contract is retired or changed by this
closure proof. Production deployment/configuration/data and fresh-workbook
rendered proof are now verified, so `runtime_consumer_switched` is formally
true globally.

Current production closeouts: **`GENERIC-DEPLOYMENT-CONFIG.5F — PRODUCTION
CLOSEOUT COMPLETE / VERIFIED`** and **`GENERIC-DEPLOYMENT-CONFIG.6B —
PRODUCTION CONFIGURATION APPLY COMPLETE / VERIFIED`**.

`GENERIC-DEPLOYMENT-CONFIG.6A` — **IMPLEMENTED / LOCAL VERIFIED** — adds the
ministry-owned `ServiceProfileMinistryRequirement` configuration foundation,
its Admin surface, typed read-only audit, and a bounded invalid-active blocker
in the ministry setup-readiness provider. Active rows require an active
Service Profile and an active assignable static Ministry Team; a Worship
rotation pool and any assignable team resolving to one through the canonical
active-primary Ministry Structure path are forbidden. Inactive rows retain
history and must pass current validation before reactivation. Any requirement
reference, active or inactive, makes the profile key/event type immutable
through supported writes. Migration `ministry/0007` is schema-only and creates
no rows. No default has been materialized into a ServiceEvent:
`ServiceEventRequiredTeam` operational truth, scheduling revisions, event
creation, Worship runtime/XLSX contracts, and `runtime_consumer_switched=true`
are unchanged. Slice 7 materialization and MO-S.REQUIRED runtime remain
pending; the Lighting Pilot remains retired.

`GENERIC-DEPLOYMENT-CONFIG.6B` — **IMPLEMENTED / LOCAL VERIFIED; PRODUCTION
CONFIGURATION APPLY COMPLETE / VERIFIED** — adds the
generic dry-run-first `configure_service_profile_ministry_requirements`
reviewed configuration path. One invocation binds one exact
`ServiceProfile.key` and the complete desired active static-default set as
exact `MinistryTeam` PK + `team_key` pairs. A V1 SHA-256 approval contract
binds current profile identity/state, the complete current requirement surface,
the desired identities, and current 6A team-validity facts. Apply re-resolves
and revalidates inside one transaction, fails closed on stale state, creates
missing rows, reactivates retained history, and deactivates omitted active rows
without deletion or `sort_order` changes. Exact no-op previews expose no apply
token. At the 6B implementation milestone, the task ran no production command
and applied no production configuration. It creates no `ServiceEventRequiredTeam`, changes no
ServiceEvent or scheduling revision, creates no assignment or notification,
and changes no Worship selection or XLSX contract. Slice 7 materialization and
MO-S.REQUIRED remain pending.

`GENERIC-DEPLOYMENT-CONFIG.7A` — **PRODUCTION READ-ONLY PREVIEW VERIFIED** —
adds a ministry-owned bounded existing-event inspector and
`audit_service_profile_required_team_materialization` command. For one exact
active ServiceProfile FK and inclusive configured-local-date scope, it reports
valid active defaults, missing additions, persisted matching defaults, manual
extras, explicit canonical-Worship rows, invalid explicit rows, and inactive
default history. It records a deterministic V1 state fingerprint binding the
profile, complete default surface, selected event identity/lifecycle/revision,
persisted required-team surface, current team validity, and missing-pair
calculation. It writes nothing.

The production 7A full-year preview for `2026-01-01` through `2026-12-31`
reported 52 selected events, 4 active defaults, 208 expected pairs, 8 already
present pairs, 200 missing pairs, 50 events with missing defaults, and zero
manual extras, explicit Worship rows, invalid explicit rows, inactive-default
history rows, review-evidence events, or blockers. The product owner explicitly
deferred full-history backfill. The separately reviewed operational scope is
`2026-09-08` through `2026-12-31` inclusive: 16 selected events, 64 expected
pairs, 4 already present, 60 missing across 15 changed events, and again zero
review evidence or blockers. Its 7A state fingerprint was
`8aa89d8d42a0516a4a8712009a15ceab4d8153ee70d360aa5ca837aec4600d10`.
That fingerprint is historical read-only evidence, not a 7B confirmation token.
If the eventual fresh production dry-run differs, current truth requires new
review. Historical missing defaults remain deliberately untouched; after a
future reviewed operational-scope apply, the full-year preview is expected to
retain 140 historical missing pairs unless separately reviewed.

`GENERIC-DEPLOYMENT-CONFIG.7B` — **PRODUCTION MATERIALIZATION APPLY COMPLETE /
VERIFIED** — adds the generic dry-run-first
`materialize_service_profile_required_teams --profile-key KEY --start-date
YYYY-MM-DD --end-date YYYY-MM-DD --actor-user-id USER_PK` command and a
separate `SERVICE_PROFILE_REQUIRED_TEAM_MATERIALIZATION_PLAN_V1` contract.
Apply additionally requires `--apply --confirmation-token <64-lowercase-hex>`.
The token binds the exact active staff/superuser actor state and complete 7A
profile, configuration, event lifecycle/revision, RequiredTeam, team-validity,
review-evidence, blocker, and missing-pair truth. Inside one transaction, apply
rebuilds current truth, claims only changed events through the canonical
scheduling-revision CAS in ascending event-ID order, recomputes complete 7A
truth after the SQLite first write allowing only each claimed revision's exact
`+1`, creates only reviewed missing static-default pairs in event/team PK order,
then recomputes and verifies the exact scope before writing one shared-operation
`LogEntry` per changed event. Any stale, busy, duplicate, postcondition, or
audit failure rolls back all rows, claims, and audits.

Existing defaults, manual extras, explicit Worship rows, invalid historical
rows, and inactive-default history are never changed or removed. Complete
events receive no write, revision claim, or audit. The operation creates no
event, TeamAssignment, TeamAssignmentMember, Notification, Worship selection,
serving, or new-event initialization. The reviewed production apply is recorded
below and remains unchanged by the later MO-S.REQUIRED.1A read/runtime slice.

#### 7B production materialization closeout: reviewed existing-event scope

This is deployment-specific production evidence, not generic CMS behavior. The
reviewed active profile was PK `1`, key `bethany_0930_cm`, event type
`sunday_service`; the inclusive operational scope was `2026-09-08` through
`2026-12-31`. The pre-apply reviewed 7B dry-run selected 16 events: 15 changed
events and one complete no-op, with four active defaults, 64 expected pairs,
four already-default pairs, 60 missing pairs, and zero manual extras, explicit
Worship rows, invalid explicit rows, inactive-default history rows,
review-evidence events, or blockers. The exact active staff/superuser actor was
PK `1` / `levin-z`. The reviewed confirmation token
`1daf728268caf723f69c8225ec6d0ae8ab2cf2c098486260c159c06e0f892442` is
historical reviewed-state evidence only, never reusable authorization.

The product owner explicitly ran that reviewed production apply. Operation
`8f867561-d971-44f4-9842-cb021b285e4c` created only the 60 reviewed missing
static-default `ServiceEventRequiredTeam` rows, changed events `82` through
`96`, and created 15 audit rows. Event `81` was already complete and remained
unchanged; events `82` through `96` advanced scheduling revision `2 -> 3`
exactly once. It reported `data_mutated: true` and
`event_materialization: true`. It created no assignment/member, notification,
Worship selection, ServiceEvent, audience, or serving state.

An independent post-apply 7A audit selected the same 16 events and reported
four active defaults, 64 expected pairs, 64 already-default pairs, zero missing
pairs, zero manual/review/Worship/invalid/inactive-history evidence, and zero
blockers: `READY / NO MATERIALIZATION NEEDED`. Its post-apply fingerprint was
`46c7e2a88b4b0ce9140fd7fe641d77fad3742f6f1de1d6faf8fadb17257f28bb`; all
events `81` through `96` were at scheduling revision `3`.

A fresh production 7B dry-run for the exact same profile/date scope/actor then
reported 16 selected events, zero changed events, 16 complete no-ops, four
active defaults, 64 expected and already-default pairs, zero missing pairs,
zero review evidence/blockers, and `READY / NO MATERIALIZATION NEEDED`. It had
no confirmation token and reported `data_mutated: false` and
`event_materialization: false`. This is the production idempotency proof.

The earlier full-year preview remains historical review context: 52 events, 208
expected pairs, eight already present, and 200 missing before the approved
operational apply. The owner deliberately deferred historical backfill; the
reviewed scope added 60 pairs, so the full-year scope is expected to retain 140
historical missing pairs unless separately reviewed. That deliberate deployment
history/backfill deferral is neither a runtime invariant nor an error.

#### 6B production configuration closeout: reviewed SVCA deployment

This is deployment-specific production evidence, not generic CMS taxonomy or
runtime behavior. The active production `ServiceProfile` is PK `1`, key
`bethany_0930_cm`, event type `sunday_service`. The product owner reviewed the
exact Ministry Team identity inventory and approved only these static defaults:

| Team PK | `team_key` |
|---:|---|
| 1 | `main.cm.digital.lighting` |
| 2 | `main.cm.digital.projection` |
| 3 | `main.cm.digital.sound` |
| 4 | `main.cm.digital.video` |

The reviewed, explicitly non-selected identities are `main.cm.worship.c1`,
`main.cm.worship.c2`, `main.cm.worship.c3`, `main.cm.worship.a`,
`main.cm.digital`, `main.cm.worship`, and `main.em.worship`. No identity in
either list is a generic runtime default.

Before apply, the independent audit reported zero profiles with requirements,
zero active or inactive requirements, zero valid or invalid active
requirements, zero Worship-forbidden requirements, and zero integrity blockers
(`READY / NO PROFILE MINISTRY DEFAULTS CONFIGURED`). The reviewed dry-run
resolved the active PK `1` profile and classified the four approved teams as
active, assignable, non-Worship-pool, and non-canonical-Worship-child. It
reported `already_active: 0`, `create_new: 4`, `reactivate_existing: 0`,
`deactivate_existing: 0`, `invalid_target: 0`, `stale_conflicting: 0`, and
`inactive_history: 0`. Its reviewed state fingerprint was
`1e08695fbb58a9d4d876d37bb9300b8cbdfe0bef4e1533ab2d6c8f87032ca7a8`;
this is historical reviewed-state evidence, not a secret or reusable
authorization.

The product owner then explicitly ran the reviewed apply: `created: 4`,
`reactivated: 0`, `deactivated: 0`, `rows_mutated: 4`, `data_mutated: true`,
and `event_materialization: false`. Exactly four
`ServiceProfileMinistryRequirement` rows were created. The independent
read-only post-audit found requirement IDs `1` through `4` as valid active rows
for the same profile and, respectively, the four approved team PK/key pairs;
its summary was one profile with requirements, four active and four valid active
requirements, zero inactive or invalid active requirements, zero
Worship-forbidden requirements, and zero integrity blockers (`READY / ACTIVE
PROFILE MINISTRY DEFAULTS VALID`).

A fresh same-set post-apply dry-run reported `already_active: 4` and zero for
`create_new`, `reactivate_existing`, `deactivate_existing`, `invalid_target`,
`stale_conflicting`, and `inactive_history`: `READY / NO CHANGES`. It exposed
no apply action or confirmation token and reported `data_mutated: false`. This
is the production idempotency proof.

The configuration apply changed only `ServiceProfileMinistryRequirement`
configuration. It created no `ServiceEventRequiredTeam` rows; changed no
`ServiceEvent` or scheduling revision; created or changed no `TeamAssignment`
or notification; changed no Worship selection or Worship XLSX data/contracts;
and created no serving or membership state. The frozen boundary remains:
`ServiceProfileMinistryRequirement` is a deployment configuration/template and
`ServiceEventRequiredTeam` is explicit per-event operational truth. There is no
live inheritance, and the 6B configuration apply did not silently change
existing events or start Slice 7 materialization. The later reviewed 7B
existing-event materialization closeout is recorded above.

### Historical production mapping: reviewed SVCA mapping only

The following is deployment-specific production evidence, not generic CMS
taxonomy or behavior. The product owner verified it on the GoDaddy/cPanel
deployment using Python `3.11.15`, application directory `~/app_read`, virtual
environment `/home/rsnwvvl103hc/virtualenv/app_read/3.11/`, and the deployed
application SQLite `db.sqlite3`.

- Exactly one reviewed `ServiceProfile` exists: PK `1`, key
  `bethany_0930_cm`, event type `sunday_service`, name
  `母堂中文部 9:30 主日崇拜`, English name
  `Bethany 9:30 Chinese Sunday Service`, blank descriptions, and active state.
- Exactly 52 `ServiceEvent` rows, current IDs `45` through `96`, are mapped to
  that profile. They span `2026-01-04T17:30:00+00:00` through
  `2026-12-27T17:30:00+00:00`; status counts stayed `completed = 34` and
  `published = 18`.
- Post-apply identity is exact: FK `NULL = 0`, FK non-`NULL = 52`, exact
  dual-consistent links `= 52`, mismatches/drift `= 0`, and every mapped event
  references profile PK `1`. No unrelated event is known to have changed.
- Every target scheduling revision advanced `1 -> 2` exactly once. The guarded
  apply reported one profile created, 52 events mapped, 52 revisions advanced,
  `data_mutated: true`, and `runtime_consumer_switched: false`.
- The independent `audit_service_profile_identity` run reported 52 events, one
  profile, 52 exact dual-consistent events, zero drift, zero integrity blockers,
  and zero conflicting multi-type legacy keys. The profile reported 52 linked
  and exact links, zero mismatches, and
  `MATCHES_LEGACY_GROUP,EXACT_LINKED_EVENTS` legacy consistency.
- A later dry-run saw the existing profile, 52 already non-`NULL` exact FKs,
  zero drift, and all revisions at `2`. It correctly returned `NOT READY` with
  `TARGET_FK_ALREADY_NON_NULL` and `SERVICE_PROFILE_KEY_ALREADY_EXISTS`; this
  is fail-closed repeat-run evidence, not an error requiring repair.

The legacy string still exists as compatibility/drift evidence for 5D/5E-switched
consumers and is no longer workbook identity authority. This production
evidence does not infer recurrence, default time,
location, audience, Worship behavior, ministry defaults, or any other generic
semantics from the reviewed key, names, time, deployment, or 52-event pattern.
That production mapping did not implement profile ministry defaults,
materialization, `MO-S.REQUIRED`, the Slice 5 consumer switch, or legacy-key
retirement. The code-only 5B integration boundary was implemented and locally
verified later; no production configuration or command was run as part of 5B.

### Production read-only consumer closeout: verified

The product owner completed the closeout on the deployed GoDaddy/cPanel
application root `/home/rsnwvvl103hc/app_read` using Python `3.11.15` and its
deployed virtual environment. The read-only identity audit found one active
`bethany_0930_cm` / `sunday_service` profile (actual PK `1`), 52 linked events,
52 exact dual-consistent FK/key links, zero profileless or legacy-only events,
zero FK/blank-key, FK/key, or event/profile-type drift, zero conflicting
multi-type legacy keys, and zero integrity blockers.

Readiness V2 was ready through `events/0012`: 52 expected Sundays, 52 canonical
tagged rows, 52 ready exact matches, and zero missing, duplicate, wrong-time,
wrong-type, wrong-date, unexpected, zero-audience, invalid-audience,
other-profile, legacy-only, drifted, or transition-blocker rows. It reported
`PROFILE SETUP READY`.

`config.settings_godaddy` was verified with
`CMS_ENABLED_INTEGRATIONS = ['svca_bethany_2026_worship_xlsx']`; registry
verification returned `frozenset({'svca_bethany_2026_worship_xlsx'})`.
`svca_lighting_pilot_csv` was not enabled. A fresh post-V2 workbook preview
used parser contract `SVCA_BETHANY_0930_2026_V2` and returned 52 supported
Sunday rows, 52 exact matched targets, 52 no-op rows, zero proposed changes,
zero blocked rows, and Complete token mapping. The English and Chinese rendered
workflows were checked. No workbook confirmation or other workbook write was
performed. The current URL-encoded filename display is minor presentation debt
outside this closeout.

Class A runtime legacy-string authority is therefore zero, and all known
profile-aware runtime consumers resolve through
`ServiceEvent.service_profile -> ServiceProfile -> ServiceProfile.key`.
`service_profile_key` remains transitional compatibility, drift evidence,
supported pair-storage evidence, and bounded setup/history tooling only. Its
field retirement remains a later separately approved, potentially destructive
cleanup slice; direct ORM/raw database drift remains possible while both fields
exist, so the identity audit remains useful.

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

Current repository truth includes the
first-class profile table below plus a nullable protected
`ServiceEvent.service_profile` FK. The optional non-unique
`ServiceEvent.service_profile_key` string (`max_length=64`, blank/default empty)
remains stored for compatibility and drift evidence. 5D switches readiness,
the retained reset/setup service, and ServiceEvent Admin to FK/Profile
authority; 5E switches strict workbook preview/confirmation to the same
authority with V2 signed identity contracts. No consumer switched in 3A, and
the post-5F production read-only closeout formally verifies the global switch.

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

The exact relationship name/owner, implemented by
`GENERIC-DEPLOYMENT-CONFIG.6A`, is
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
   across conflicting event types is a blocker. The implementation task itself
   applied no normal-local or production mapping.
5. **PRODUCTION APPLY COMPLETE / POST-AUDIT VERIFIED for the reviewed SVCA
   mapping:** a separately approved guarded apply created one exact profile and
   mapped its complete 52-event exact-key target set. Independent audit proved
   52 exact dual-consistent links and zero drift; every scheduling revision
   advanced `1 -> 2` exactly once. A repeat dry-run failed closed on the
   existing profile and non-`NULL` FKs without advancing any revision to `3`.
   This evidence is deployment-specific and grants no generic semantics.
6. **IMPLEMENTED / LOCAL VERIFIED in 5C:** while both fields exist, the
   canonical runtime seam classifies all dual-identity states without legacy
   fallback, and supported explicit identity writes preserve
   `service_profile.key == service_profile_key` with one existing-event
   scheduling revision. Retain the separate read-only drift audit.
7. **IMPLEMENTED / LOCAL VERIFIED in 5D:** switch readiness, the bounded reset,
   and ServiceEvent Admin to FK/Profile authority; version readiness/reset
   evidence and preserve one-save revision behavior. Workbook signing remains
   unchanged for 5E.
8. **IMPLEMENTED / LOCAL VERIFIED in 5E:** switch workbook preview/confirmation
   and signed contracts to FK/Profile authority.
9. **PRODUCTION CLOSEOUT COMPLETE / VERIFIED in 5F:** repository proof and
   deployed read-only evidence establish zero runtime legacy-string authority,
   exact target data, explicit integration configuration, and the rendered
   workbook workflow.
10. Separately approve removal of `service_profile_key`; historical migrations
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

### 7.3 `GENERIC-DEPLOYMENT-CONFIG.7C-0A` / `7C-1A` — new-event initialization

Status: **7C-0A/FU1 CONTRACT COMPLETE; 7C-1A IMPLEMENTED / LOCAL VERIFIED**.
The implementation preserves the frozen SQLite first-write/current-truth
contract and does not change the historical 7B closeout. 7C itself does not
implement MO-S.REQUIRED runtime; the later 1A slice is read-only and does not
change this writer contract.

The current supported creation inventory is:

| Path | Cardinality | Current transaction and writes | Profile exposure |
|---|---:|---|---|
| Ordinary `/events/new/` | One | The shared events-owned creation service owns one outer transaction and explicitly creates the event, RequiredTeam rows, and audience rows | Optional active-profile selector plus server-rendered review; the compatibility key is never exposed |
| Ordinary `/events/recurring/new/` | Zero or many dates after duplicate filtering | The same service owns the complete deterministic batch; every created event receives the same explicit RequiredTeam and audience sets | Optional active-profile selector extends Preview with reviewed defaults; the compatibility key is never exposed |
| Django Admin ServiceEvent add | One | Django Admin's change-form transaction owns the parent event plus RequiredTeam and audience inlines | Active profiles are selectable through the FK; the compatibility key is read-only; RequiredTeam rows remain separate manual inlines |
| `rebuild_bethany_0930_service_events` explicit operator APPLY | Exactly the bounded 52-event replacement set | `apply_reset()` owns one destructive, token-gated outer transaction and `_create_canonical_event()` creates each exact profile-linked event plus its audience row | The exact profile is an operator prerequisite, not a user choice; this historical/deployment-specific reset deliberately creates no RequiredTeam rows |

Repository-wide non-test searches found no other supported `ServiceEvent`
creation writer. Direct ORM construction in tests and immutable historical
migrations is not a user-facing creation path. Worship workbook confirmation,
rotation planning, assignment flows, audits, 7A, and 7B operate on existing
events and create no ServiceEvent.

The ordinary Required Ministry Teams picker remains the explicit operational
review surface. New single and recurring forms now offer only active **and**
assignable teams. Single-event edit unions those normal choices with every
exact already-linked team, including inactive/non-assignable history, so an
unrelated edit does not silently drop evidence. Admin remains a manual repair
surface and gains no implicit profile-default materialization.

#### Chosen UX and stale-state contract

| Option | Repository fit | Decision |
|---|---|---|
| A. Extend existing single/recurring forms | Reuses both supported ordinary routes, the existing Required Ministry Teams picker, audience validation, and recurring Preview; needs one shared create service and focused form/template changes | **Recommend**: smallest complete reviewed consumer with no duplicate UI |
| B. Separate profile-aware creation workflow | Would duplicate event fields, audience selection, permission checks, recurrence rules, and transaction behavior while leaving users to choose between overlapping create routes | Reject for 7C-1A |
| C. Central initialization service only | Establishes a useful boundary but has no explicit user review/choice consumer, so it cannot by itself satisfy the frozen new-event contract | Reject as an incomplete shipping slice; build the service inside Option A |

Choose **Option A**: extend the existing ordinary single and recurring creation
forms. Do not add a duplicate profile-specific workflow (Option B), and do not
ship an unused central writer with no user-facing reviewed consumer (Option C).
Expose a bilingual, human-facing `ServiceProfile` choice only while creating;
never expose `service_profile_key`. Choices are active profiles, and the
submitted `event_type` must equal the selected profile's event type before a
review can be produced.

Review is server-rendered; dynamic JavaScript is not necessary. Single creation
gets a **Review profile defaults** action. Recurring creation reuses and extends
its existing **Preview** action. The review displays the selected profile and
its exact active static defaults in configured order, states clearly that they
are initial Required Ministry Teams rather than assignments or live
inheritance, and prechecks those defaults in the existing picker. A user may
then deliberately add or remove active assignable teams; the submitted picker
set is the exact operational set to create. No profile leaves the picker with
no profile-derived preselection. A valid active profile with zero defaults is
ready and visibly says that no profile defaults are configured.

The review carries a versioned signed, expiring, request-scoped snapshot. At
minimum it binds:

- contract version and, when required by the repository signing pattern, the
  exact requesting user/owner identity;
- submitted `event_type`;
- selected profile PK/key/type/current active state plus its current identity
  and update evidence;
- the complete relevant active **and inactive** requirement surface, including
  row identity, order, active state, and update evidence;
- every relevant MinistryTeam PK/key and current activity, assignability, and
  canonical Worship-path validity;
- the exact default set displayed to the user;
- the selected audience and its validation baseline where used by the current
  workflow; and
- an expiration bound.

Recurring review additionally binds every recurrence input, every exact
candidate local date, every date classified for creation, and every skipped
date plus the reason/current duplicate evidence used by the existing duplicate
semantics. Neither the 7A state fingerprint nor the 7B confirmation token is a
7C review artifact and neither may be reused.

The final user-selected RequiredTeam set may deliberately differ from the
profile defaults because those defaults are proposed/prechecked configuration,
not mandatory inheritance. Every deliberate ordinary picker addition must be
active and assignable; only profile-derived defaults use the canonical stricter
profile-default/Worship classification. Changing
the selected profile or `event_type` after review invalidates the review. A
crafted final POST selecting a profile without a valid current signed snapshot
for that exact profile/type state is rejected. No profile still means no
profile-derived defaults; zero active defaults remains a valid reviewed state.
Inactive requirement history is bound review evidence but is not a default or
blocker.

#### SQLite first-write and current-truth contract

One outer atomic transaction owns the complete single event or recurring
batch. Before writing, the create-only orchestration decodes and validates the
signed snapshot; re-resolves the exact ServiceProfile; recomputes complete
profile/default/team validity and every submitted explicit RequiredTeam's
validity; recomputes audience validity; and, for recurring creation, recomputes
the exact candidate/create/skip classification. It then establishes SQLite's
writer boundary through the first intended ServiceEvent creation write.
`select_for_update()` must not be described or relied on as a row lock on
SQLite.

After that first write, while the writer boundary is held, the orchestration
reloads and recomputes **all** review-sensitive current truth. Only the expected
transaction-local consequence of the first intended event insert may differ
from the reviewed/pre-write state. Any changed external fact, invalid state,
unexpected duplicate, or post-write mismatch rolls back that first insert and
the entire transaction. No partially created event, audience row, or
RequiredTeam row survives. If 7C-1A finds a safer existing repository-supported
first-write ordering, it may use that ordering only if it preserves the same
all-or-nothing, post-boundary current-truth guarantee.

For one event the required order is: validate reviewed state; enter the outer
transaction; insert the candidate ServiceEvent at `scheduling_revision = 0`;
use that insert as the writer boundary; re-resolve/recompute exact profile
identity, profile/type compatibility, the complete relevant default surface,
relevant team state/Worship validity, and audience validity; require equality
with the reviewed contract except for the inserted row; create the exact
reviewed explicit RequiredTeam rows and audience rows; verify postconditions;
and commit. A failed post-first-write check rolls back the candidate event.

For recurring creation the first candidate event insert establishes the writer
boundary. The orchestration then recomputes the **complete** batch
candidate/create/skip classification plus profile/default/team/audience truth.
It must equal the signed reviewed batch except for that one expected
transaction-local created row. Only then may it create the remaining events
and every event's exact RequiredTeam/audience rows. Final postconditions prove
the exact reviewed event set and revision zero for every new event. A concurrent
duplicate or any other create/skip change rolls back the whole batch; apply
never silently shrinks or expands the reviewed batch.

#### Central creation boundary and revisions

`events` should own one new central creation service because it owns the event
creation transaction and the two ordinary callers. The service should consume
one or more fully validated event specifications, the exact selected audience
units, the exact reviewed RequiredTeam set, the optional selected profile, and
the reviewed profile-default snapshot. It reuses:

- `events.service_profile_runtime.prepare_service_event_profile()` for the
  exact FK/compatibility pair and event-type/active validation;
- `ministry.service_profile_ministry_requirements` as the canonical
  read-only default/team-validity classifier; and
- the current audience-combination validation, while creating new audience
  rows rather than invoking an edit-oriented delete/recreate operation.

Inside one outer `transaction.atomic()`, the service follows the pre-write,
first-intended-insert, and post-boundary recomputation contract above; then it
creates every remaining event, every audience row, and the exact explicit
`ServiceEventRequiredTeam` rows. Recurring creation passes one exact reviewed
static/manual set to every event and is all-or-nothing. Every successfully
created event remains at the model's normal `scheduling_revision = 0`; initial
audience and RequiredTeam rows do not advance it. Busy, integrity, validation,
stale-current-truth, or postcondition failure rolls back the complete single
event or recurring batch.

The events-owned orchestration must not copy or reinterpret Ministry profile-
default validation. It calls the canonical ministry inspector/service through
the smallest existing cross-domain seam needed by this repository. This adds no
module-registry dependency metadata and no plugin/extension abstraction.
Existing edit paths must never call the create-only service. Django Admin and
the Bethany reset remain unchanged.

Do not reuse the 7B writer for this purpose. 7B is an existing-event,
changed-event-only CAS/audit workflow. The new creation service may reuse the
same read-only validity semantics, but it needs no existing-event revision
claim and must not manufacture a 7B audit/materialization operation.

Single and recurring creation should ship together in one `7C-1A` slice. Their
form layouts differ, but they share the same profile review contract, explicit
team picker, audience requirement, failure rules, and final atomic service.
Shipping only one would leave duplicated creation logic and inconsistent
ordinary behavior. Django Admin and the bounded reset stay outside that
consumer slice: their current manual/technical semantics remain explicit and
gain no hidden default behavior.

The exact proposed `GENERIC-DEPLOYMENT-CONFIG.7C-1A` scope is: create-only
profile selection for both ordinary forms; bilingual server-rendered
single-review and recurring-preview output; a versioned signed review snapshot;
strict active/assignable new-team choices with existing invalid-row
preservation on edit; one events-owned atomic single/batch creation service;
exact profile-pair preparation; all-or-nothing event/audience/explicit
RequiredTeam creation; revision-zero postconditions; and focused tests for no
profile, zero defaults, deliberate edits, invalid/stale configuration,
recurrence drift, rollback, and unchanged existing-event/Admin/reset behavior.
The matrix must include: a profile/default writer winning before the first
event write produces stale with zero created rows; 7C winning the SQLite
first-write boundary prevents a relevant concurrent configuration writer from
silently committing inside the reviewed transaction; recurring duplicate or
create/skip drift rolls back the whole batch; post-first-write recomputation
failure rolls back the first inserted event; changed profile/type rejects the
review; a crafted profile POST without a valid snapshot is rejected; successful
events remain revision zero; and deliberate removal of every proposed default
remains a valid explicit final selection. Use target-like file-backed,
two-connection SQLite tests where practical, following existing scheduling
concurrency patterns.

Explicit non-goals are schema/migrations; live inheritance; signals,
`post_save`, startup/background materialization, or `ServiceEvent.save()` side
effects; default-driven deletion; existing-event profile-change
materialization/removal; Admin/default-inline automation; changes to the
Bethany reset or 7A/7B; Worship A/C1/C2/C3 static rows; `rotation_anchor_team`;
assignments, members, serving, notifications, permissions, audience inference,
adapters, production data, historical backfill, and MO-S.REQUIRED coverage
runtime.

## 8. Worship Is a Separate Dynamic Axis

Status: **`MO-S.REQUIRED.1A — IMPLEMENTED / LOCAL VERIFIED / PRODUCTION RUNTIME
VERIFIED`**. One canonical
read-only ministry resolver implements the union below from event operational
truth, with exact-ID de-duplication and explicit/derived provenance. Generic
coverage, gap, readiness, and already-authorized attention consumers use it;
ownership conflict/review remains separate from missing coverage. Team Schedule
and Sunday Board retain dedicated Worship presentation, and Event detail has a
bounded readout plus the existing authorization-gated selector link. The slice
creates no row, changes no permission, and adds no schema or migration.
The product-owner-run canonical read-only production projection for the 16
future `bethany_0930_cm` events verified 64 persisted explicit pairs plus 16
eligible derived Worship requirements, for 80 effective pairs and zero
review-required events. It made no production write and persisted no derived
requirement. Every selected Worship state was `selected_unscheduled`: a valid
coverage/scheduling gap pending a matching Worship assignment, not configuration
drift or an invalid selection.

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

GENERIC-DEPLOYMENT-CONFIG.4A = implemented audit/configuration tooling;
no migration and no automatic data operation; separately reviewed SVCA
production apply and independent post-audit complete for one exact mapping

ministry/0006 + events/0012
    -> ministry/0007 = implemented ServiceProfileMinistryRequirement
```

The events profile migration does not depend on the new ministry relationship.
The ministry relationship may depend on both foundations. Existing historical
cross-app edges (`ministry/0002 -> events/0001` and
`events/0003 -> ministry/0002`) remain a valid DAG; no new reverse edge creates
a cycle.

## 10. Deployment-Specific Adapter Boundary

The existing 2026 SVCA/Bethany Worship XLSX code is a valid specialized
adapter, not a generic importer. `GENERIC-DEPLOYMENT-CONFIG.5B` implements the
following frozen boundary around the previously unqualified staff exposure and
unconditional generic imports.

Freeze a small explicit registry, not a plugin framework:

- setting: **`CMS_ENABLED_INTEGRATIONS`**;
- absent, `None`, or empty means no deployment integrations;
- the current registered key is **`svca_bethany_2026_worship_xlsx`**;
- 5B initially also registered **`svca_lighting_pilot_csv`**, but
  `LIGHTING-PILOT-RETIRE.1A` removed it without an alias, so configuring that
  retired key now fails unknown-key validation;
- each entry declares required modules; workbook requires `events` + `ministry`;
- unknown keys or unmet module dependencies raise `ImproperlyConfigured` when
  configuration is evaluated;
- disabled means no entry point, no adapter query, and direct-route fail-closed
  regardless of staff status.

Unlike `CMS_ENABLED_MODULES`, absence never means enable all. Adapters are
opt-in so another church cannot accidentally see SVCA UI.

Current URL names remain, while 5B view wrappers gate first and lazy-import the
adapter only after enablement and authority checks. Disabled generic imports do
not load the adapter services or `openpyxl`. A later focused task may move the
adapter under an explicit namespace such as
`ministry/integrations/svca_bethany_2026_worship_xlsx/`. Generic Worship
Planning provides selector/planner plus enabled adapter links. Future adapters
are explicitly registered: no auto-discovery, hook bus, or plugin SDK.

The Lighting pilot is retired from active code by
`LIGHTING-PILOT-RETIRE.1A`. Its registry entry, route/view, upload template,
management command, importer service, and active tests were removed. The
product owner chose retirement instead of converting its unsafe mutable-name
identity to `MinistryTeam.team_key`. No canonical model rows were deleted or
rewritten.

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
| Strict SVCA/Bethany 2026 XLSX contract | B. Acceptable explicit deployment adapter | Strict constants remain correct; 5B gates exposure, while physical namespace placement remains optional cleanup. |
| Bethany rebuild, CHURCH -> campus -> CM resolver, readiness defaults | C. Acceptable one-time historical setup | Bounded operator/history tooling, not generic runtime; future tooling should be profile-data-driven. |
| Legacy SVCA reading import and SVCA readiness-policy seed | C. Acceptable deployment/historical setup | Explicit command only; keep named and never auto-run. |
| Workbook card/URLs shown to all staff when modules enabled | D. Configuration-gating debt resolved in 5B | Card is opt-in; disabled direct routes return 404 before adapter form/service/parser/query work. |
| Lighting pilot CSV route/UI | D. Resolved by retirement in `LIGHTING-PILOT-RETIRE.1A` | No route, view, template, command, service, or registry entry remains. |
| Unconditional XLSX imports in generic events forms/views and former Lighting imports in ministry views | E. Generic import violation resolved | 5B isolated adapter imports; `LIGHTING-PILOT-RETIRE.1A` removed the Lighting importer entirely. Worship XLSX remains gate-first and lazy. |
| Historical Lighting pilot name matching/normalization | E. Genericity violation retired | The product owner chose complete retirement rather than reviewed `team_key` modernization. |
| Generic team-form placeholder "Lighting Team" | E. Minor genericity debt | Replace with neutral example copy; no current domain behavior effect. |
| Tests using Bethany/named teams/A-C tokens | F. Deferred, no current impact | Representative fixtures are acceptable when not asserted as universal taxonomy. |
| Generic `CHURCH` root seed | A. Acceptable generic domain | One local root concept; Bethany/CM assumptions remain bounded setup. |

Historical docs may record exact SVCA production facts. Current/future generic
instructions must label them as one deployment's configuration.

## 13. Production Compatibility and Risk

The original architecture audit did not inspect or mutate production. The
current closeout additionally records product-owner-verified production apply
and post-audit evidence for the reviewed SVCA mapping; it does not generalize
that deployment data into CMS behavior.

| Area | Risk | Protection |
|---|---|---|
| Nullable team key | LOW | Additive; existing rows stay valid `NULL`; no runtime switch. |
| ServiceProfile table | LOW | Additive; the reviewed SVCA production deployment has one profile referenced by the exact 52-event mapped set. This deployment data adds no generic behavior. |
| Nullable event profile FK | LOW-MEDIUM | Additive; the reviewed SVCA production mapped set has 52 non-`NULL` exact links and zero drift. 5D readiness/reset/Admin and 5E workbook preview/confirmation use FK authority; the legacy string is drift evidence. |
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
| 3. Service Profile/FK expand | **IMPLEMENTED / LOCAL VERIFIED (`GENERIC-DEPLOYMENT-CONFIG.3A`)**: exact frozen profile model, nullable protected FK, validation/immutability/revision/Admin foundations, additive migration, and disposable migration proof; legacy string remains authoritative and no rows/FKs were created or backfilled by 3A. LOW-MEDIUM. | Profile rows required review before creation; Slice 4 was the separately reviewed mapping/backfill gate. |
| 4. Profile mapping/backfill | **IMPLEMENTED / LOCAL VERIFIED / PRODUCTION APPLY COMPLETE / POST-AUDIT VERIFIED (`GENERIC-DEPLOYMENT-CONFIG.4A`) for the reviewed SVCA mapping**: generic read-only key/type/FK inventory plus one-key-at-a-time reviewed profile creation and complete exact-target FK backfill; `SERVICE_PROFILE_MAPPING_PLAN_V1` binds full metadata and current event state, existing scheduling CAS supplies SQLite serialization and exactly-once revision advance, and independent post-audit proves dual consistency. Production has one reviewed profile, 52 exact dual-consistent mapped events, zero drift, and revisions advanced `1 -> 2` exactly once. At the 4A milestone, `runtime_consumer_switched` remained false. MEDIUM operationally. | Stop on conflict/unmapped/noncanonical/ambiguity/existing profile/non-null FK/stale/busy state; owner reviews every target apply. Repeat initial mapping correctly fails closed after configuration. |
| 5. Integration boundary + consumer switch | **5A READ-ONLY AUDIT / DOCS-ONLY IMPLEMENTATION PLAN COMPLETE; 5B REGISTRY/GATES/IMPORT ISOLATION IMPLEMENTED / LOCAL VERIFIED; 5C CANONICAL RUNTIME IDENTITY SEAM IMPLEMENTED / LOCAL VERIFIED; 5D READINESS/RESET/ADMIN SWITCH IMPLEMENTED / LOCAL VERIFIED; 5E WORKBOOK FK MATCHING/CONFIRMATION/V2 SIGNING IMPLEMENTED / LOCAL VERIFIED; 5F PRODUCTION CLOSEOUT COMPLETE / VERIFIED**: [`GENERIC_DEPLOYMENT_CONFIGURATION_SLICE5_PLAN.md`](GENERIC_DEPLOYMENT_CONFIGURATION_SLICE5_PLAN.md) contains the classified inventory and verified production evidence. 5E makes workbook matching and post-CAS confirmation FK/Profile-authoritative and rejects V1 artifacts; 5F proves Class A legacy authority is zero in repository/runtime design and the deployed closeout verifies `runtime_consumer_switched` as true. MEDIUM-HIGH. | Verified: only the workbook key is enabled; identity audit and Readiness V2 are zero-drift/ready; a fresh V2 workbook preview is 52 exact no-ops with no confirmation; English/Chinese rendered surfaces were checked. |
| 6. Profile ministry defaults | **FOUNDATION + REVIEWED CONFIGURATION TOOLING IMPLEMENTED / LOCAL VERIFIED (`GENERIC-DEPLOYMENT-CONFIG.6A/6B`)**: ministry-owned relation, active/static-team validation through canonical Worship primary-path resolution, inactive history, profile identity immutability extension, Admin, typed read-only audit, bounded setup-readiness blocker, and exact profile-key + team-PK/key complete-desired-set dry-run/apply tooling; no event materialization. LOW-MEDIUM. | Active configuration with an inactive profile/team, non-assignable team, or Worship-path team fails closed; state-bound V1 review fails stale; inactive history is retained; zero defaults is ready; owner reviews every deployment apply. |
| 7. Materialization/drift | **7A PRODUCTION READ-ONLY PREVIEW VERIFIED; 7B PRODUCTION MATERIALIZATION APPLY COMPLETE / VERIFIED; 7C-1A IMPLEMENTED / LOCAL VERIFIED**: the historical reviewed existing-event materialization remains closed and unchanged. Ordinary single+recurring creation now uses optional server-reviewed profile suggestions and one atomic events-owned service; profileless creation remains supported and final RequiredTeam rows remain explicit truth. MEDIUM-HIGH. | Existing events keep the 7B CAS/apply contract. New events use a distinct expiring state-bound review for selected profiles, exact active/assignable explicit sets, SQLite first-insert/post-boundary recomputation, atomic event+audience+RequiredTeam creation, revision-zero postconditions, and stale/invalid rollback. Admin/reset/adapters remain unchanged. |
| 8. MO-S.REQUIRED runtime | **IMPLEMENTED / LOCAL VERIFIED / PRODUCTION RUNTIME VERIFIED (`MO-S.REQUIRED.1A`)**: read-only effective resolver, exact-ID provenance/de-duplication, bounded coverage/gap/attention/Event-detail adoption; notifications, persisted writers/audits, and profile-default materialization remain explicit-only. MEDIUM. | Production read-only projection verified 64 explicit + 16 eligible derived Worship = 80 effective pairs across 16 future reviewed events, with zero review-required events and no write; all selected-unscheduled cases are valid gaps pending assignments. |
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

## 19. `GENERIC-DEPLOYMENT-CONFIG.LEGACY-SERVICE-PROFILE-KEY-RETIRE.0A`

Status: **RETIREMENT-READINESS AUDIT COMPLETE; RETIREMENT NOT IMPLEMENTED**.

`ServiceEvent.service_profile_key` is transitional compatibility/drift storage.
It is not canonical identity and must not be confused with the permanent,
deployment-local `ServiceProfile.key`. Current runtime identity is the
`ServiceEvent.service_profile` FK and Class-A legacy-string runtime authority
remains zero after 6A/6B, 7A/7B/7C, and MO-S.REQUIRED.1A.

### Exhaustive active-reference inventory and disposition

The table classifies current executable references. Historical migrations and
clearly historical documentation remain valid evidence and are listed
separately. A name such as `service_profile_key` is not necessarily the event
compatibility field: ministry default DTOs and command output obtain that value
from canonical `ServiceProfile.key` and therefore survive unchanged.

| File / symbol | Class | Current purpose | Event-field retirement disposition |
|---|---|---|---|
| `events/models.py` — `ServiceEvent.service_profile_key`, `ServiceEvent.clean()` | B | Stores and validates exact/blank/mismatch compatibility evidence beside the authoritative FK | DELETE the field and dual-pair checks; retain permanent FK/profile event-type, active-selection, PROTECT, revision, and `ServiceProfile.key` rules |
| `events/service_profile_runtime.py` — `inspect_service_event_profile()`, `require_service_profile()` | B | Resolves from the FK and reports legacy-only, blank-key, mismatch, and event-type drift; never resolves a profile from the string | REWRITE to FK/profile semantics; retain profileless, event-type, and active-profile checks |
| `events/service_profile_runtime.py` — `prepare_…`, `set_…`, `clear_…`, `_save_identity_pair()` | C | Keeps both columns synchronized as a transition invariant | REPLACE WITH FK-only assignment/clear helpers and preserve existing revision/transaction behavior |
| `events/admin.py` — `ServiceEventAdminForm`, `ServiceEventAdmin` | B, C, F | Uses the inspector, pair helpers, active/current FK selector, compatibility error mapping, read-only key, and compatibility note | REWRITE to FK-only form semantics; remove compatibility presentation while retaining authorized Admin selection and permanent validation |
| `events/service_event_creation.py` — `_insert_event()`, `_verify_event()` | C | 7C writes the selected FK and matching string atomically, then verifies both | REPLACE WITH FK-only insert/postcondition; retain profileless creation and review/atomic/revision-zero contract |
| `events/service_profile_identity.py` and `audit_service_profile_identity` | D | Reports complete identity state, profileless events, type drift, legacy groups, legacy-only rows, blank keys, and mismatches | SIMPLIFY IN PLACE: preserve permanent FK/profile/profileless/type integrity; remove transition-only fields after the final pre-drop audit |
| `events/service_profile_readiness.py` and `audit_service_profile_readiness` | D | Selects canonical targets through the FK and separately reports compatibility blockers/evidence | VERSION and simplify in place; retain target/date/time/lifecycle/audience/duplicate/profileless/FK checks and remove transition-only schema/counters/evidence |
| `events/service_profile_mapping.py` and `configure_service_profile_mapping` | C, D, J | Explicit legacy-key group discovery and guarded mapping; command success text still says the string is authoritative | RETIRE before DROP after supported deployments are mapped; current obsolete authority wording must disappear with the command |
| `events/service_profile_setup.py`, `rebuild_bethany_0930_service_events` | C, E | Bounded reset resolves the canonical profile but snapshots, fingerprints, validates, creates, and reports the dual pair | REWRITE FK-only and bump the reset approval contract/fingerprint version |
| `ministry/services/worship_xlsx_preview.py` and confirmation recomputation | B, E | Matches by FK/Profile; normalized rows use canonical `ServiceProfile.key`, but signed profile evidence also includes the event compatibility value and drift states | Adapter identity does not block retirement; remove compatibility evidence and bump normalized preview/confirmation contracts because signed current truth changes |
| `ministry/service_profile_required_team_materialization.py` and 7B apply plan | B, E | Selects events by FK but includes inspector identity state in the signed 7A preview inherited by 7B | REWRITE the inspector dependency and bump 7A preview/7B plan contracts while preserving create-only materialization semantics |
| `ministry/admin.py`, `ministry/service_profile_ministry_requirements.py`, setup provider, and ministry audit command | NO EVENT-FIELD CLASS | Their similarly named DTO/output value comes from `requirement.service_profile.key` | NO CHANGE; this is permanent canonical Profile identity |
| `events/forms.py`, `events/views.py`, `events/scheduling_revision.py` | — | Forms/views select the FK and delegate creation; scheduling revision is identity-agnostic | NO CHANGE except consequences of the FK-only service boundary |
| templates, settings, configuration | — | No active event compatibility-field reference was found | NO CHANGE |

The exact repository-search ledger is:

- direct active event-field source: `events/models.py`, `events/admin.py`,
  `events/service_event_creation.py`, `events/service_profile_identity.py`,
  `events/service_profile_mapping.py`, `events/service_profile_readiness.py`,
  `events/service_profile_runtime.py`, `events/service_profile_setup.py`,
  `events/management/commands/audit_service_profile_readiness.py`,
  `events/management/commands/configure_service_profile_mapping.py`,
  `events/management/commands/rebuild_bethany_0930_service_events.py`, and
  `ministry/services/worship_xlsx_preview.py`;
- indirect active callers/contracts: `events/forms.py`, `events/views.py`,
  `events/scheduling_revision.py`,
  `ministry/service_profile_required_team_materialization.py`,
  `ministry/service_profile_required_team_materialization_apply.py`,
  `ministry/management/commands/audit_service_profile_required_team_materialization.py`,
  `ministry/management/commands/materialize_service_profile_required_teams.py`,
  and `ministry/services/worship_xlsx_confirmation.py`;
- permanent canonical-Profile references whose local DTO/output name happens to
  be `service_profile_key`: `ministry/admin.py`,
  `ministry/service_profile_ministry_requirements.py`,
  `ministry/setup_readiness_provider.py`, and
  `ministry/management/commands/audit_service_profile_ministry_requirements.py`;
- tests: `events/test_service_event_creation.py`,
  `events/test_service_profile.py`, `events/test_service_profile_identity.py`,
  `events/test_service_profile_key.py`, `events/test_service_profile_mapping.py`,
  `events/test_service_profile_migration.py`,
  `events/test_service_profile_readiness.py`,
  `events/test_service_profile_runtime.py`,
  `events/test_service_profile_setup.py`,
  `events/test_worship_xlsx_preview.py`,
  `events/test_worship_xlsx_confirmation.py`,
  `ministry/test_effective_required_teams.py`,
  `ministry/test_service_profile_ministry_requirements.py`,
  `ministry/test_service_profile_ministry_requirement_configuration.py`,
  `ministry/test_service_profile_required_team_materialization.py`, and
  `ministry/test_service_profile_required_team_materialization_apply.py`;
- immutable migrations: `events/0011` and `events/0012`; and
- documentation: this document,
  `GENERIC_DEPLOYMENT_CONFIGURATION_SLICE5_PLAN.md`, `MODULE_BOUNDARIES.md`,
  `PRODUCT_ARCHITECTURE_AND_ROADMAP.md`, `SUNDAY_MINISTRY_SCHEDULING_PLAN.md`,
  and `WORSHIP_ROTATION_GOVERNANCE_PLAN.md`. Current-state references must track
  the FK-authoritative transition; clearly labeled milestone chronology is
  preserved historically. No template, settings, or configuration occurrence
  survives.

No active lookup equivalent to
`ServiceProfile.objects.get(key=event.service_profile_key)` exists. The 4A
mapping workflow is guarded transition tooling, not runtime identity authority;
filtering by `ServiceProfile.key` through `ServiceEvent.service_profile` is
canonical and is not a blocker.

### Supported writers and validation contract

Current supported writers are:

- 7C single/recurring creation: create-only; canonical identity comes from the
  reviewed selected `ServiceProfile`; the central atomic creation service writes
  both columns at revision zero.
- ServiceEvent Admin: existing-event edit; canonical selection is the FK; the
  Admin form prepares an exact pair and the model save barrier advances
  `scheduling_revision` once.
- bounded Bethany reset: create-only replacement dataset; canonical profile is
  resolved from an explicitly approved key, and the reset owns the transaction,
  exact pair, fingerprint, and revision-zero creation.
- 4A mapping: existing-event transition only; the reviewed legacy-key group and
  current-state token choose the bounded set, then the command writes the FK
  while preserving the already matching string under its SQLite CAS transaction.
- the public pair set/clear helpers: shared transition primitives (with direct
  production use currently limited to the reset); they update both columns and
  preserve the caller's revision/transaction contract.

No supported writer fundamentally needs duplicate identity storage. Each writer
maintains only the transition invariant. Before `DROP COLUMN`, all must become
FK-only or be retired. Direct `ServiceEvent.save()` is a validation barrier, not
a supported identity-selection workflow.

Transition-only model/runtime rules that disappear are event-key grammar,
legacy-only state, FK-with-blank-key state, FK/key equality, mismatch state, and
pair preparation/save/clear postconditions. Permanent rules that remain are
`ServiceProfile.key` grammar, FK/profile event-type compatibility, rejection of
new inactive-profile selection while preserving historical references,
referenced-profile identity immutability, FK `PROTECT`, and existing
`scheduling_revision` behavior.

### Tooling, signed contracts, and tests

The identity and readiness audits remain useful after retirement and should be
simplified/versioned, not wholly deleted. Permanent checks include the FK,
profileless events, event/profile type agreement, expected target-event
identity, workflow-required active state, and referenced-profile integrity.
Legacy-only groups, FK/blank-key, FK/key mismatch, multi-type legacy grouping,
and migration-0011-as-current-schema checks are transition-only.

`configure_service_profile_mapping` should remain available only until every
supported deployment has passed the pre-contract audit. It should then be
retired in the pre-contract cleanup slice. New installations have no need for
the legacy group workflow because 7C creates FK/Profile-aware events directly;
historical migration and milestone tests/docs remain as history.

The bounded reset's current V2 approval snapshot includes the compatibility
string, so its FK-only rewrite requires an explicit V3 approval-contract and
token/fingerprint bump. The 7C V1 signed review payload already binds canonical
`ServiceProfile` ID/key/type/activity/timestamp and does not encode the event
compatibility column; V1 may remain while its unsigned insert/postcondition
becomes FK-only. The Worship parser itself also does not depend on the event
field. Its normalized preview and confirmation do: signed profile evidence
includes compatibility truth, so retirement requires a V3 normalized preview
and matching V3 confirmation contract. The 7A preview/7B plan should likewise
advance versions when transition identity state leaves their signed facts.

Future test disposition is:

- preserve permanent `ServiceProfile` key, FK, event-type, active-selection,
  immutability, PROTECT, permissions, revision, atomicity, concurrency,
  profileless, audience, and zero-write coverage;
- replace pair assertions in `test_service_profile.py`,
  `test_service_profile_runtime.py`, `test_service_profile_identity.py`,
  `test_service_profile_readiness.py`, `test_service_profile_setup.py`, and
  `test_service_event_creation.py` with FK/permanent-integrity assertions;
- retire transition schema/grammar/Admin drift coverage in
  `test_service_profile_key.py` and the active 4A mapping suite in
  `test_service_profile_mapping.py`, while preserving historical evidence;
- update `test_worship_xlsx_preview.py` and
  `test_worship_xlsx_confirmation.py` for V3 FK/Profile evidence without
  weakening matching, governance, CAS, audit, or all-or-nothing behavior;
- update the ServiceProfile RequiredTeam materialization preview/apply/config
  tests for their versioned FK-only facts while retaining create-only and
  rollback contracts; and
- preserve `test_service_profile_migration.py` as historical 0011-to-0012
  coverage and add future 0012-to-0013 removal coverage. The effective-required
  test that currently supplies a compatibility fixture should retain its
  no-inference assertion using canonical Profile/default state.

Historical migrations `events/0011_serviceevent_service_profile_key.py` and
`events/0012_serviceprofile_serviceevent_service_profile.py` remain immutable.
The current `events` migration tip is `0012`; the future contract migration is
conceptually `0013_remove_serviceevent_service_profile_key`, dependent on
`0012`. Historical documentation may retain the old name when its milestone
context is explicit.

### Fresh production precondition and SQLite contract

The prior 5F result is evidence, not a permanent substitute for a fresh
immediately-pre-migration audit. Reuse a simplified/versioned identity/readiness
audit and require zero:

- nonblank compatibility strings with a null FK;
- nonblank FK/key mismatches;
- FK profile/event `event_type` mismatches;
- dangling/impossible FK integrity states; and
- malformed/noncanonical nonblank event keys or any other unsupported
  transition state.

Profileless events with null FK and blank compatibility strings are allowed,
as are FK-linked events with blank compatibility strings (the canonical
FK-only Stage-1 shape) and exact historical FK/key residue. The former
transition-era condition requiring zero FK-plus-blank-key rows is superseded:
the destructive-removal condition is that no canonical ServiceProfile identity
exists only in the legacy column and no unexplained nonblank mismatch or
malformed residue remains.
Exact inactive profiles may remain valid historical references; active state is
required only where a current workflow permanently requires it. The audit must
be rerun read-only against the exact target database immediately before the
future migration.

Production uses SQLite. The field is not a PK, unique field, index, or FK, so a
Django/SQLite combination with native `DROP COLUMN` support may use it;
otherwise Django can rebuild the table. The deployed SQLite version and chosen
migration SQL must be verified on the target rather than inferred from local
code. Either path may take a schema/write lock and is not an online-migration
guarantee. Column deletion loses compatibility values: a reverse migration can
re-add an empty column but cannot reconstruct them.

The future production sequence is therefore: deploy the pre-contract code;
run the fresh read-only audit; stop event writers for a maintenance window;
take and validate a recoverable database backup; inspect the target migration
plan/SQL; migrate; run post-migration Django/schema/identity and bounded product
smoke checks; then reopen writes. Production execution remains a separately
approved task.

### Retirement sequence decision

- Option A (code and column together) is small in slice count but couples many
  signed-contract/tooling changes to an immediately destructive SQLite schema
  operation.
- **Option B is selected**: Stage 1 removes all active event-field
  reads/writes/guards/presentation and versions affected contracts while the
  physical column remains; it retains one explicit read-only pre-drop audit.
  After repository zero-reference and fresh production FK-integrity proof,
  Stage 2 adds the new removal migration and deletes the final preflight/model
  reference.
- Option C avoids immediate migration risk but preserves redundant identity and
  continuing drift indefinitely, so it is not the recommended steady state.

The exact next slice should be
`GENERIC-DEPLOYMENT-CONFIG.LEGACY-SERVICE-PROFILE-KEY-RETIRE.1A`: FK-only
runtime/Admin/writers; retirement of 4A mapping; simplified/versioned
identity/readiness audit with an explicit pre-drop mode; version bumps for the
reset, 7A/7B, and Worship normalized preview/confirmation contracts; and focused
test/doc updates. It leaves the column and migration history untouched. A later
separately approved `.1B` owns fresh production zero-state evidence, backup and
maintenance planning, `events/0013`, and final post-migration cleanup.

Deferred external identity mapping does not read or require
`ServiceEvent.service_profile_key`, does not block retirement, and must remain a
separate adapter/mapping concept. It must not overload permanent
`ServiceProfile.key` or resurrect the event compatibility string as speculative
external-ID storage.

## 20. `GENERIC-DEPLOYMENT-CONFIG.LEGACY-SERVICE-PROFILE-KEY-RETIRE.1A`

Status: **PRODUCTION VERIFIED**.

Stage 1 implements Option B without a schema migration. The physical
`ServiceEvent.service_profile_key` column and model declaration remain only as
temporary dead storage pending separately approved Stage 2. Current identity is
strictly `ServiceEvent.service_profile -> ServiceProfile.key`: ordinary model
validation, runtime resolution, Admin, 7C creation, the bounded reset, Worship
preview/confirmation, and RequiredTeam materialization neither read nor write
the compatibility column. Existing raw values are neither inferred, repaired,
blanked, nor synchronized by ordinary saves.

The only intentional column reader is the explicit read-only
`audit_service_profile_identity --pre-drop-legacy-key` preflight. It reports
all transition states needed to gate Stage 2 and states `PRE-DROP LEGACY COLUMN
AUDIT`, `READ-ONLY`, and `NO DATA CHANGED`. Normal identity and readiness
audits are FK/Profile-authoritative (`SERVICE_PROFILE_IDENTITY_V2` and
`SERVICE_PROFILE_READINESS_V3`). The 4A mapping command is retired.

The V2 pre-drop result distinguishes safe `profileless_blank`,
`fk_only_blank_legacy`, and `exact_legacy_residue` rows from blocking
legacy-only, nonblank mismatch, malformed/noncanonical, and event/type states.
It is ready for column removal when those blockers are zero; Stage 1 never
restores a dual writer merely to reduce the FK-only blank-key count.

Affected signed contracts are versioned: Bethany reset approval is V3, Worship
normalized preview/confirmation are V3, and RequiredTeam preview/plan are V2.
7C `SERVICE_EVENT_PROFILE_CREATION_REVIEW_V1` remains valid because its signed
review already bound canonical Profile facts, not the compatibility column.

Production Stage-1 verification recorded `SERVICE_PROFILE_IDENTITY_V2` with 52
events, 52 FK-linked rows, one active profile, and zero integrity blockers. Its
`SERVICE_PROFILE_LEGACY_KEY_PRE_DROP_V2` evidence recorded 52 exact historical
residue rows, zero legacy-only/mismatch/malformed/event-type blockers, and
`READINESS: READY FOR COLUMN REMOVAL`. Those retained exact strings are safe
historical residue; they require no cleanup write before removal.

## 21. `GENERIC-DEPLOYMENT-CONFIG.LEGACY-SERVICE-PROFILE-KEY-RETIRE.2A`

Status: **IMPLEMENTED / LOCAL VERIFIED; NOT PRODUCTION APPLIED**.

`events/0013_remove_serviceevent_service_profile_key` removes only the
physical `ServiceEvent.service_profile_key` column. Current model/runtime,
Admin, creation, reset, readiness, Worship, and RequiredTeam code have no
event compatibility field. The Stage-1 pre-drop mode is retired with the
column; the normal `SERVICE_PROFILE_IDENTITY_V2` audit remains supported and
`ServiceProfile.key` remains the permanent canonical identity.

The local SQLite migration and 0012-to-0013 preservation test prove that exact
historical residue, FK-only, and profileless rows retain their event IDs, FK,
event type, scheduling revision, and ordinary data while the removed column is
absent. A schema reverse may recreate an empty column but cannot reconstruct
dropped strings. Production rollback therefore requires the immediately
pre-migration SQLite backup together with pre-Stage-2 application code; running
`migrate events 0012` alone is not a complete rollback.

The separately approved production operation remains: while Stage-1 code is
still deployed, rerun the pre-drop audit and require `READY FOR COLUMN
REMOVAL`; create and verify a SQLite backup; deploy approved Stage-2 code; run
the migration in a maintenance window; restart/reload the application as the
hosting deployment requires; run post-migration FK identity/schema checks; and
retain the backup through production closeout. SQLite `RemoveField` may rebuild
the table or take a schema/write lock and is not an online migration.
