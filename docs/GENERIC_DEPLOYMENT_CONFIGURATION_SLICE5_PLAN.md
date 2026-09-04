# Generic Deployment Configuration — Slice 5 Implementation Plan

Status: **`GENERIC-DEPLOYMENT-CONFIG.5A` repository-wide read-only audit and
docs-only implementation planning complete; `GENERIC-DEPLOYMENT-CONFIG.5B`
explicit integration registry, fail-closed gates, and lazy import isolation
IMPLEMENTED / LOCAL VERIFIED; and `GENERIC-DEPLOYMENT-CONFIG.5C` canonical
ServiceProfile runtime identity seam IMPLEMENTED / LOCAL VERIFIED; and
`GENERIC-DEPLOYMENT-CONFIG.5D` readiness/reset/Admin consumer switch
IMPLEMENTED / LOCAL VERIFIED; and `GENERIC-DEPLOYMENT-CONFIG.5E` Worship XLSX
FK matching, current-truth confirmation, and V2 signed contracts IMPLEMENTED /
LOCAL VERIFIED; and `GENERIC-DEPLOYMENT-CONFIG.5F` transition-closure audit and
local closure proof **LOCAL CLOSURE PROOF COMPLETE / PRODUCTION READ-ONLY
CLOSEOUT PENDING**. Class A legacy-string runtime authority is zero. The global
status stays conservative until the separately performed deployed read-only
closeout.**

Task IDs: `GENERIC-DEPLOYMENT-CONFIG.5A`,
`GENERIC-DEPLOYMENT-CONFIG.5B`,
`GENERIC-DEPLOYMENT-CONFIG.5C`,
`GENERIC-DEPLOYMENT-CONFIG.5D`,
`GENERIC-DEPLOYMENT-CONFIG.5E`,
`GENERIC-DEPLOYMENT-CONFIG.5F`

Audit baseline: `master` at `C:\dev\bible_reading_v2`, synchronized with
`origin/master` at `0` ahead / `0` behind and clean before this document was
created on 2026-09-03. The audit queried no production system and changed no
runtime, tests, schema, settings, package, templates, static assets, or data.

5B was implemented on the synchronized 5A baseline with no schema, migration,
normal-local data, or production operation. It adds an explicit default-off
registry for `svca_bethany_2026_worship_xlsx` and
`svca_lighting_pilot_csv`, gates their web/command surfaces, and converts
generic import leaks to gate-first lazy imports. No adapter service file was
moved, no workbook parser/matching/signing/confirmation semantic or contract
version changed, and no ServiceProfile runtime consumer switched.

5C was implemented on the synchronized 5B baseline with no schema, migration,
data, UI, route, integration, or signed-contract change. It adds the typed
events-owned FK-authoritative runtime inspection/strict-resolution seam and an
explicit exact pair-write/clear contract. At the 5C milestone no readiness,
setup/reset, Admin, or workbook consumer imported or used the seam, so
`runtime_consumer_switched` remained false globally.

5D was implemented on the synchronized 5C baseline with no model, migration,
normal-local data, production operation, or workbook change. Readiness now
resolves the stable key to an active type-compatible profile and selects FK-
owned canonical rows under a V2 evidence contract; legacy-only/profileless/
drift states are blocker or review evidence only. The retained bounded Bethany
TEST reset uses a V2 state-bound approval and exact FK/key replacement rows;
no reset was run. ServiceEvent Admin now selects the FK, renders the
compatibility key read-only, and prepares pair writes before one normal save.
At the 5D milestone, workbook preview/confirmation stayed legacy-authoritative
pending 5E, so `runtime_consumer_switched` remained false globally.

5E was implemented on the synchronized 5D baseline with no model, schema,
migration, backfill, normal-local data, or production operation. The adapter
resolves `bethany_0930_cm` to one active Sunday-service profile, matches by FK,
and requires the 5C seam's exact state. Parsed, normalized-preview, and
confirmation contracts are strict V2 artifacts binding
`svca_bethany_2026_worship_xlsx` and exact profile PK/key/type. Confirmation
re-resolves and revalidates the profile after CAS and before anchor writes.
Every V1 artifact fails closed. `service_profile_key` remains drift evidence
and rollback compatibility. All known profile-aware runtime consumers are now
switched.

5F reran the post-5E repository inventory and focused behavior suites. No
Class-A runtime authority remains. The existing read-only identity inventory
needed only a small generic extension that separates legacy-only, FK/blank-key,
FK/key, and event/profile-type drift counts; it remains zero-write and has no
deployment defaults. No schema, signing, readiness, reset, Admin, mapper, or
field-retirement behavior changed. Production deployment/config/data and fresh
workbook rendered proof were not performed, so `runtime_consumer_switched`
remains false globally.

This document turns the canonical architecture in
[`GENERIC_DEPLOYMENT_CONFIGURATION_ARCHITECTURE.md`](GENERIC_DEPLOYMENT_CONFIGURATION_ARCHITECTURE.md)
into an evidence-complete implementation boundary. It does not authorize any
implementation slice listed below.

## 1. Scope and canonical architecture

The permanent event profile identity is:

```text
ServiceEvent.service_profile FK
    -> ServiceProfile
    -> stable deployment-local ServiceProfile.key
```

`ServiceEvent.service_profile_key` is temporary compatibility data. It remains
stored through Slice 5, but after the consumer switch it must not answer a
profile-aware runtime identity question. While both fields exist, every
supported identity write must preserve:

```text
service_event.service_profile is not None
    => service_event.service_profile.key == service_event.service_profile_key
```

Generic events may legitimately have no Service Profile. A profile-specific
workflow is different: it requires a non-null valid FK and must fail closed on
a missing FK, mismatch, wrong profile event type, or any other transition
drift. No fallback from the legacy string is approved.

The existing 2026 SVCA/Bethany Worship XLSX contract is an explicit deployment
adapter. Its Bethany, 09:30, 2026, A/C1/C2/C3, sheet, header, and workbook hash
facts are correct inside that adapter and are not generic CMS taxonomy. The
approved integration boundary is an explicit opt-in registry, not a plugin
framework.

The reviewed production mapping is evidence only: one profile (current PK 1,
key `bethany_0930_cm`) and 52 exact dual-consistent events (current IDs 45–96),
zero drift, and revisions advanced from 1 to 2 exactly once. No implementation
may hard-code that PK or infer behavior from those deployment facts.

## 2. Executive repository findings

1. 5C now provides the central runtime ServiceProfile seam in
   `events.service_profile_runtime`. Its inspection result represents every
   approved dual-identity state, its strict resolver uses only the FK-linked
   profile, and its mutation helpers preserve the exact identity pair. The
   separate `events.service_profile_identity` module remains the read-only 4A
   inventory. 5D adopts the seam for readiness, bounded reset, and Admin; 5E
   adopts it for both workbook services.
2. All currently known profile-aware runtime consumers use FK/Profile
   authority. 5F proves the post-5E Class-A count is zero;
   `service_profile_key` remains compatibility/drift/storage/setup evidence.
3. `ServiceEvent.clean()` enforces FK/key equality and profile/event-type
   equality when the FK is non-null. `ServiceEvent.save()` always calls
   `full_clean()`. `ServiceProfile.save()` also calls `full_clean()` and makes a
   referenced key/event type immutable.
4. Direct `QuerySet.update()`, `bulk_create()`, raw SQL, and database writes
   outside model/service boundaries bypass model validation. The database has
   no cross-table constraint capable of enforcing FK key/type equality. The 4A
   identity audit therefore remains required during the dual phase.
5. The ServiceEvent Django Admin exposes the FK selector and renders the legacy
   key as read-only compatibility evidence. Ordinary and recurring
   ServiceEvent forms expose neither.
6. Existing-event `ServiceEvent.save()` calls advance `scheduling_revision`
   before validation unless `_skip_scheduling_revision=True` is explicitly
   used. Transaction rollback restores the bump after validation failure.
7. The 4A mapper intentionally claims each target revision first, then writes
   only the FK with `_skip_scheduling_revision=True`; the exact legacy key was
   a reviewed precondition, so the model equality check still runs and each
   event advances exactly once. Workbook confirmation uses the same claim-then-
   skip pattern for `rotation_anchor_team`.
8. 5A found that generic `events.forms`, `events.views`, and `events.urls`
   eagerly loaded both workbook services and `openpyxl`. 5B removes that leak:
   generic events imports do not load workbook adapter services or `openpyxl`.
9. 5B makes the workbook card conditional on explicit integration enablement
   and gates the stable preview/confirmation URLs before adapter form/service,
   parse, query, decode, CAS, or write work. Staff/superuser status does not
   bypass disablement.
10. The Lighting Pilot remains absent from navigation. 5B gates its direct
    route and command before importer/file/query/data work and removes the
    eager importer dependency from `ministry.views`; its mutable-name identity
    remains unchanged and unresolved.
11. The workbook's parsed, normalized-preview, and confirmation artifacts are
    strict V2 signed contracts binding integration plus exact ServiceProfile
    identity. The adapter-specific normalized rows bind canonical FK state;
    the generic shared Worship event fingerprint remains unchanged.
12. The bounded reset approval is a hashed state contract, not a Django-signed
    token. 5D V2 binds the resolved profile plus each event's FK and
    compatibility key; V1 tokens fail closed.
13. Trial setup readiness contains no ServiceProfile or workbook-integration
    provider. This is not a hidden consumer and need not change in Slice 5.

## 3. Current identity states and enforcement

| Persisted event state | Supported model save today | Current meaning | Post-switch profile-aware behavior |
|---|---|---|---|
| FK `NULL`, key blank | Valid | Generic event with no profile | Valid generally; fail closed only when the exact workflow requires a profile |
| FK `NULL`, key nonblank | Valid | Legacy-only transitional identity | Transition/audit state; never satisfy a profile-required consumer |
| FK non-null, exact key, matching event type | Valid | Exact dual-consistent identity | Canonical FK/Profile identity; legacy value is drift evidence only |
| FK non-null, key blank | Rejected by `clean()` / `save()` | Invalid drift if inserted by a bypass | Fail closed and audit blocker |
| FK non-null, mismatched key | Rejected by `clean()` / `save()` | Invalid drift if inserted by a bypass | Fail closed and audit blocker |
| FK non-null, exact key, wrong event type | Rejected by `clean()` / `save()` | Invalid type drift if inserted by a bypass | Fail closed and audit blocker |

Enforcement is layered rather than database-complete:

| Surface | Equality/type enforcement | Revision behavior |
|---|---|---|
| `ServiceEvent.clean()` / `save()` | Checks non-null FK against legacy key and event type; rejects a newly assigned inactive profile | Every existing save advances once unless explicitly skipped; failed saves roll back atomically |
| `ServiceProfile.clean()` / `save()` | Normalizes/validates key; referenced key and event type are immutable | Profile label/description/active edits do not advance linked events |
| ServiceEvent Admin | FK is the explicit selector; legacy key is read-only evidence; shared non-saving preparation rejects drift/inactive-new/type conflict | One normal existing-event save advances exactly once; new rows remain revision 0 |
| Ordinary/recurring event forms | Neither identity field is exposed | No profile identity write |
| 4A mapping service | Requires exact legacy targets and no existing FK, claims all revisions, creates profile, then writes FK | Intentional `_skip_scheduling_revision=True` after the batch claim |
| Bounded reset/setup | Resolves the exact active profile and creates exact FK/key events | New rows begin at revision 0; V2 preview/approval binds the profile and complete reset surface |
| Workbook confirmation | Does not change profile identity; after claiming all revisions it changes only Worship anchors | Intentional `_skip_scheduling_revision=True` after the batch claim |
| Direct ORM/raw writes | No model equality/type validation | `QuerySet.update()` does not perform the normal revision bump unless the caller explicitly does so |

## 4. Complete legacy identity consumer inventory

### 4.1 Counting method

The audit found **58 literal `service_profile_key` occurrences on 52
occurrence-bearing lines in active, non-test, non-migration Python across 10
files**. Every occurrence has exactly one primary A–D classification below. It
also found 112 occurrences in nine test modules (E), three immutable migration
occurrences, and 18 pre-plan documentation occurrences across five documents
(F). Thus the full classified pre-plan textual set is 191 occurrences:

| Class | Occurrences | Meaning |
|---|---:|---|
| A — runtime authoritative consumer | 20 | Readiness command/service and workbook preview/confirmation decisions |
| B — dual-consistency / transition guard | 14 | Model/profile guards and generic identity inventory |
| C — supported identity write contract | 8 | Model key normalization/field/write validation |
| D — bounded setup/operator tooling | 16 | 4A mapper plus Bethany test-data reset and their command output |
| E — tests / fixtures / assertions | 112 | Nine focused test modules |
| F — migrations / docs only | 21 | Three migration and 18 documentation occurrences |

Primary classification follows the enclosing symbol's role: for example, the
bounded 4A mapper is Class D even though it also checks drift. Symbol rows below
also include indirect consumers that do not spell the legacy field, such as
Admin's implicit model field and the identity-audit command. Those indirect
rows are not added to the literal occurrence totals.

### 4.2 Active-code inventory (A–D)

This table preserves the 5A pre-switch inventory and recommended routing.
Implemented 5D results in section 11.3 supersede the readiness/reset/Admin
“current” cells; implemented 5E results in section 11.4 supersede the workbook
rows. The inventory remains historical input for 5F rather than closure proof.

| Class | File / symbol | Current role | Current profile authority | Access / audience | Genericity | Signed or fingerprint impact | Recommended future action | Slice | Risk |
|---|---|---|---|---|---|---|---|---|---|
| C | `events/models.py` — key normalizers and `ServiceEvent.service_profile_key` field/write contract | Defines and validates the compatibility field used by supported writes | Legacy string remains accepted with or without FK | Read/write; all model-backed paths | Generic domain | Every supported existing-event identity save changes revision; no token owned here | Retain compatibility field through Slice 5; route explicit profile changes through one pair-writing service | 5C/5D | High |
| B | `events/models.py` — `ServiceEvent.clean/save`, `ServiceProfile.clean/save` transition guards | Enforces non-null FK/key/type equality, active assignment, and referenced profile key/type immutability | Compares both identities but does not resolve via fallback | Read/write guard; all model-backed paths | Generic domain | Failed validation rolls back the revision bump | Retain equality/type guard; do not add fallback, inference, or silent repair | 5C/5D | High |
| B | `events/service_profile_identity.py` — `build_service_profile_identity_inventory`, `_event_summary` | Complete 4A inventory of groups, missing FKs, exact links, drift, and profile rows | Deliberately compares both | Read-only operator/audit | Generic | No signed artifact | Retain and extend only as needed for post-switch closure; legacy reads remain justified drift evidence | 5F | Low |
| B | `events/management/commands/audit_service_profile_identity.py` — `Command.handle` (indirect) | Operator rendering of the generic identity inventory | Both identities as audit evidence | Read-only operator | Generic | None | Retain; its post-switch references are intentional, not runtime authority | 5F | Low |
| D | `events/service_profile_mapping.py` — V1 plan/build/apply and `_assign_profile_to_event` | One-time reviewed profile creation and exact legacy-key FK mapping | Legacy exact target set is setup authority; writes FK only after CAS | Read/write operator | Generic operator tooling | `SERVICE_PROFILE_MAPPING_PLAN_V1` binds raw key, FK IDs, event state and revisions | Do not redesign completed 4A. Keep as bounded mapping/history tooling while unmapped deployments exist; exclude it from “runtime authority” counts | 5F | Medium |
| D | `events/management/commands/configure_service_profile_mapping.py` | CLI for the 4A plan/apply | Delegates to V1 mapper; explicitly reports consumer not switched | Read/write operator | Generic operator tooling | Prints V1 confirmation token | Retain unchanged unless closure evidence proves it can be retired later; never treat output text as a runtime consumer | 5F/later contract retirement | Low |
| A | `events/service_profile_readiness.py` — `build_audit`, `_event_evidence`, `_other_profile_exact_time_evidence`, rendering | Selects canonical rows, untagged candidates, and other-profile rows | Raw input key and `ServiceEvent.service_profile_key` | Read-only operator runtime | Core service is parameterized; its annual contract semantics are setup-specific | JSON/report contract is serialized but unsigned; reset postcondition depends on it | Resolve the requested `ServiceProfile` first, query by FK, report dual drift separately, and make FK-null legacy rows blockers rather than fallback matches | 5D | High |
| A | `events/management/commands/audit_service_profile_readiness.py` — `Command.handle` | Validates key text/length and invokes readiness; defaults to Bethany 2026 09:30 | Legacy field metadata and raw key | Read-only operator | Bounded SVCA default around a parameterized service | Output contract changes when profile facts are added | Resolve by stable `ServiceProfile.key`; require schema through 0012; version/document JSON output change | 5D | Medium |
| D | `events/service_profile_setup.py` — snapshot, reset approval, `_dataset_is_canonical`, `_create_canonical_event`, postcondition | Destructive, guarded TEST-data reset for one Bethany 2026 dataset | Snapshot and replacement use legacy string; creates key-only rows | Read/write operator | Explicit bounded historical/setup tooling | Reset V1 fingerprint and approval bind raw key but not FK/profile | Keep bounded; if retained as callable, require the exact profile FK, fingerprint both identities, create both identities, and bump reset contract. If no longer operational, retire only in a separate approved cleanup | 5D | High |
| D | `events/management/commands/rebuild_bethany_0930_service_events.py` | Exposes the bounded destructive reset and renders raw key | Delegates to setup service | Read/write operator | Explicit Bethany test-data tooling | Prints reset fingerprint/token | Do not genericize or silently run. Follow the retained-versus-retired setup decision above | 5D or later retirement | High |
| A | `ministry/services/worship_xlsx_preview.py` — `match_exact_service_event_targets` | Matches each workbook Sunday to one event | Hard-coded adapter key compared to legacy string plus type/time | Read-only staff adapter runtime | Explicit SVCA adapter | Parsed and normalized preview tokens; shared row fingerprint omits profile identity | Match through resolved profile FK, use central resolver for drift, add explicit profile-conflict state, and version all affected signed payloads | 5E | High |
| A | `ministry/services/worship_xlsx_confirmation.py` — `confirm_worship_workbook` | Revalidates all 52 targets after revision claims | Hard-coded adapter key compared to legacy string | Read/write staff adapter runtime | Explicit SVCA adapter | Confirmation V1 payload does not bind profile; current truth checks raw key | Bind resolved profile PK/key/type in V2 proposal and require every reloaded event's exact FK plus dual consistency after CAS | 5E | Critical |
| C | `events/admin.py` — `ServiceEventAdmin`, `ServiceProfileAdmin` (indirect) | Event Admin edits legacy key and displays FK read-only; profile Admin protects referenced key/type | Legacy string is the only event identity control | Read/write staff Admin | Generic domain | Normal Admin save changes event revision | Make FK the explicit active-only selector, preserve an existing inactive choice for history, make compatibility key read-only, and synchronize both only from the explicit FK selection | 5D | High |

### 4.3 Test and fixture inventory (E)

| File | Current contract | Future disposition |
|---|---|---|
| `events/test_service_profile_key.py` | Legacy field schema, duplicate-key validity, Admin editability, revision, no permission semantics | Keep schema/permission regressions while field exists; rewrite Admin authority and identity-change tests around FK plus read-only compatibility key |
| `events/test_service_profile.py` | Profile model, dual-state validation, revision, Admin/forms | Retain equality/type/inactive/immutability/direct-drift tests; rewrite Admin selector and pair-write expectations |
| `events/test_service_profile_identity.py` | Exact/mixed/drift inventory and zero-write command | Retain and extend with post-switch classification/closure proof |
| `events/test_service_profile_mapping.py` | V1 dry-run/apply/CAS/rollback and “consumer not switched” | Retain 4A regression/history; update only the obsolete status assertion after closure, without weakening V1 mapping guarantees |
| `events/test_service_profile_readiness.py` | String-owned targets/candidates/other-profile/readiness output | Rewrite canonical cases to create profiles/FKs; retain legacy-only/mismatch rows as fail-closed transition cases |
| `events/test_service_profile_setup.py` | Reset V1 fingerprint and key-only replacement | If reset remains callable, rewrite for exact profile resolution, dual creation, V2 token invalidation, and missing/inactive/mismatched profile blockers |
| `events/test_worship_xlsx_preview.py` | Parser, legacy-string matching, signed parsed/normalized previews, view availability | Preserve strict workbook semantics; rewrite identity fixtures to exact FK and add disabled/no-import/no-query plus old-token rejection |
| `events/test_worship_xlsx_confirmation.py` | Confirmation V1 signing, raw-key drift, CAS, rollback, routes | Rewrite proposal/current-truth tests for profile PK/key/type binding; retain legacy mismatch and FK-null as rollback/fail-closed cases |
| `events/test_service_profile_migration.py` | Additive 0011→0012 migration preserves legacy-only/blank rows without inference | Keep unchanged as immutable expansion history |

Representative Bethany/team/token fixture names are harmless inside adapter
tests. They become a problem only if asserted as generic CMS behavior.

### 4.4 Historical migrations and docs (F)

The three migration occurrences are immutable history:

- `events/migrations/0011_serviceevent_service_profile_key.py` defines the
  transitional field (two occurrences).
- `events/migrations/0012_serviceprofile_serviceevent_service_profile.py`
  depends on 0011 (one occurrence).

The 18 documentation occurrences are in:

- `docs/GENERIC_DEPLOYMENT_CONFIGURATION_ARCHITECTURE.md`;
- `docs/MODULE_BOUNDARIES.md`;
- `docs/PRODUCT_ARCHITECTURE_AND_ROADMAP.md`;
- `docs/SUNDAY_MINISTRY_SCHEDULING_PLAN.md`;
- `docs/WORSHIP_ROTATION_GOVERNANCE_PLAN.md`.

They document current/transition/history and do not count against future zero
runtime dependency. Current wording must be updated at implementation
milestones; historical facts must not be rewritten as though they never
existed.

## 5. Complete adapter exposure and import inventory

### 5.1 Worship XLSX

| Surface | Current 5B behavior | Import boundary | Status |
|---|---|---|---|
| `requirements.txt` | Pins `openpyxl==3.1.5` | Package is a deployment dependency | Keep deployable for the enabled adapter; package optionalization is not required for Slice 5 |
| `events/forms.py` | Workbook constants are imported only inside workbook form methods | Generic form import loads no workbook service or `openpyxl` | Implemented in 5B; a later physical form move is optional cleanup |
| `events/views.py` | Imports no workbook service/form at module import | Generic view import loads no workbook adapter or `openpyxl` | Implemented in 5B with thin gate-first route wrappers and lazy service/form imports |
| `events/urls.py` | Stable preview and confirmation URLs still reference generic wrappers | Importing the route table loads no workbook adapter or `openpyxl` | Implemented in 5B; disabled wrappers return 404 before adapter-specific work |
| `events.views.worship_planning` + `templates/events/worship_planning.html` | Card requires enabled integration plus existing staff/superuser authority | Generic planner/event queries remain independent of the adapter | Implemented in 5B; disabled state hides only the workbook card |
| `events.views.worship_workbook_preview` | Gate runs before authority and lazy imports; enabled behavior is unchanged | Disabled GET/POST performs no adapter form/service/parser/query work | Implemented and locally verified in 5B |
| `events.views.worship_workbook_confirm` | Gate runs before authority and lazy imports, decode, CAS, query, or write | Disabled POST performs no confirmation adapter/data work | Implemented and locally verified in 5B |
| `ministry/services/worship_xlsx_preview.py` | Parser, archive preflight, target matching, preview/signing remain in the existing service file | Loaded only after the enabled route/form boundary or direct adapter-unit import | 5B leaves physical placement unchanged to avoid a broad relocation; later namespace cleanup remains optional debt |
| `ministry/services/worship_xlsx_confirmation.py` | Confirmation remains beside the preview service and imports its constants/types | Its internal eager preview import occurs only after the enabled outer boundary or direct adapter-unit import | 5B leaves physical placement and semantics unchanged |
| Preview/result templates | Explicit Bethany/09:30/52/A-C copy and route links | Rendered only through current staff route, not integration-gated | Keep semantics/copy inside adapter templates; parent generic card is enabled-integration driven |
| Focused tests | Adapter unit tests continue to import services directly; route/UI classes explicitly enable the key | Disabled cases and a fresh subprocess cover UI/route/no-work/import isolation | Implemented in 5B without globally enabling integrations |

The ServiceEvent list exposes generic Worship Planning when a user has a
current manageable/visible Worship event. That parent page and the rotation
planner are generic Worship features and must not be disabled with the XLSX
adapter. Only the annual workbook card/routes are integration-owned.

### 5.2 Lighting Pilot CSV

| Surface | Present behavior | Verdict |
|---|---|---|
| `ministry/urls.py` | Stable `teams/import/lighting-pilot/` route targets a gated wrapper | Disabled direct requests return 404 before importer/data work |
| `ministry/views.py` | No top-level importer import; integration gate precedes authority, and POST lazy-imports the service | Generic import leak resolved in 5B |
| `ministry/permissions.py` | Staff bypass or three-capability authority | Authority is not enablement; retain only after integration enablement succeeds |
| `templates/ministry/lighting_pilot_import.html` | Explicit pilot upload/apply UI | Adapter-specific and acceptable only when enabled |
| `ministry/management/commands/import_lighting_pilot.py` | Requires enabled integration before lazy service import or CSV read; existing `--dry-run` contract is unchanged | Gating implemented in 5B; broader command safety redesign remains out of scope |
| `ministry/services/lighting_pilot_import.py` | Creates/reuses a Lighting team by Chinese/English mutable names and may normalize names; matches events by mutable titles/time | Genericity violation inside retained legacy pilot code; do not copy this identity pattern |
| Staff navigation / assignment empty state | Tests explicitly assert no Lighting link | Non-discoverable and default-disabled; retain no-link state |
| `ministry/tests.py` | Retained route/permission/dry-run/apply tests explicitly enable the integration | Disabled cases prove 404/CommandError before importer, file, query, or mutation work |

No repository evidence proves continuing production use. The narrowest safe
Slice 5 treatment is therefore:

1. register `svca_lighting_pilot_csv` with required modules `events` and
   `ministry`;
2. leave it disabled unless a deployment explicitly opts in;
3. 5B gates the route and CLI and isolates imports;
4. do not rewrite name matching in that gating slice;
5. before any deployment enables it, obtain an owner decision: either retain
   and replace team-name identity with an explicitly reviewed `team_key`, or
   retire the pilot in a separate approved slice.

This avoids inventing requirements or expanding a retired pilot while ensuring
another church cannot invoke it accidentally.

## 6. Historical pre-5D/pre-5E signed and fingerprint contract inventory

This table preserves the 5A baseline used to plan the V2 cutover. It is not an
inventory of the current active workbook contracts; Sections 11.3 and 11.4
record the post-5E runtime state.

| Contract | 5A/pre-switch version | Exact identity then bound | Canonicalization impact | Planned action at 5A |
|---|---|---|---|---|
| 4A mapping plan/token | `SERVICE_PROFILE_MAPPING_PLAN_V1` | Reviewed profile metadata/key, complete exact legacy target set, each event's raw key, FK ID, type, revision and timestamp | Already binds both transition sides for initial mapping | Retain V1 as completed operator tooling; no Slice 5 compatibility parser or bump needed |
| Reset-surface fingerprint | No separate label; SHA-256 inside reset V1 | Event rows include raw legacy key, not FK/profile | Adding FK ID/profile key changes canonical JSON/digest | Include `service_profile_id` and resolved profile facts if reset remains callable |
| Reset approval | `MO-S.6D-PROFILE-SETUP.1A-FU1-v1`, 16 hex chars | Raw `PROFILE_KEY` plus type/year/time/audience path and reset-surface digest | Canonical payload changes | Bump to V2; recomputation makes every V1 token fail closed |
| Parsed workbook token | parser `SVCA_BETHANY_0930_2026_V1`, signing version 1, salt `ministry.worship-xlsx-preview.v1` | Workbook/file/user/rows/tokens only; profile is implicit in adapter revision | FK resolution is not presently serialized | Bump parser contract/signing version or salt as one V2 boundary so pre-cutover tokens fail closed |
| Normalized workbook preview token | same parser/signing V1 | Event IDs, team IDs and shared fingerprints; shared event fingerprint contains revision/status/type/time/anchor but no profile field | Adding canonical profile facts changes shape | Add resolved profile PK/key/type and per-row FK identity; bump V2. The token is currently decoded only in tests, but remains a real signed artifact |
| Workbook confirmation proposal | `SVCA_BETHANY_0930_2026_CONFIRM_V1`, signing version 1, salt `ministry.worship-xlsx-confirmation.v1` | Event IDs/revisions, before/proposed team IDs, workbook hash, parser version; no profile identity | Current confirmation rechecks raw key outside payload | V2 must bind integration key plus resolved profile PK/key/type and strictly require exact FK/dual consistency after CAS; old proposals fail decode |
| Generic Worship Rotation Planner proposal | contract version 3, signing version 1 | Generic event/governance/team/downstream facts; no profile field | Not a profile-aware consumer | No bump for Slice 5; supported profile changes already advance event revision |
| Worship-context review fingerprint/token | fingerprint `worship_context_v1`, review state version 1 | Selected team/assignment/roster semantics; no profile identity | Not profile-aware | No bump for Slice 5 |

Do not accept old shapes through optional fields or compatibility parsing.
Version/salt mismatch or strict-shape mismatch should reject them and direct the
operator to rebuild a fresh preview.

## 7. Admin, forms, views, and identity presentation

- Ordinary `ServiceEventForm` and `RecurringServiceEventForm` currently expose
  neither identity field. Preserve that product boundary.
- Django Admin currently exposes raw `service_profile_key` through the default
  model form and lists `service_profile` in `readonly_fields`. It can create a
  legacy-key-only event; it cannot explicitly assign the FK. On an exact mapped
  event, changing only the key is rejected by model validation.
- Future Admin should make `service_profile` the explicit selector and show
  `service_profile_key` as read-only compatibility/confirmation context. New
  selections should contain active profiles only; an already selected inactive
  profile remains visible for historical repair/review and cannot be newly
  assigned to another event.
- A custom Admin form/service should pair-write the FK and compatibility key
  from the explicit selection, or clear both from an explicit clear. Do not
  auto-heal arbitrary mismatches and do not infer a profile from the legacy
  string.
- ServiceProfile names and bilingual labels are display only. Admin choices may
  show name plus stable key and event type, but equality, filtering, signing,
  and writes use PK/key/type—not names.
- Member event detail currently does not expose technical identity. Preserve
  that behavior.
- The workbook card, preview, and result are staff-facing adapter surfaces.
  Their technical profile key may remain read-only confirmation context, but
  the UI must not imply the mutable profile name is identity.

## 8. Genericity findings

| Finding | Class | Slice 5 disposition |
|---|---|---|
| ServiceEvent/Profile models, audience, required teams, Worship governance, revisions | Acceptable generic domain | Preserve explicit fields and relationships |
| Strict Bethany 2026 workbook constants, sheet/header/hash/time/tokens | Explicit deployment adapter | Keep strict; isolate and opt-in gate |
| Bethany reset command and CHURCH→campus→CM resolver | Bounded historical/setup tooling | Do not genericize; make dual-safe if retained or retire separately |
| Readiness command Bethany defaults | Bounded setup default around parameterized audit | Resolve stable profile key to FK; do not infer from time/name |
| Workbook card and routes available on staff status alone | Configuration-gating debt | Gate through explicit registry; staff never bypasses disabled state |
| Workbook imports in generic events forms/views | Genericity violation | Remove generic import dependency; lazy load after gate |
| Lighting route/CLI and generic ministry view import | Configuration-gating debt/import violation | Gate and isolate immediately |
| Lighting mutable-name team lookup/normalization | Genericity violation in legacy pilot | Replace with reviewed `team_key` only if retention is approved; otherwise retire separately |
| `MinistryTeamForm` placeholder “Lighting Team” | Minor generic copy debt | Not part of identity cutover; may be neutralized only in a separately approved UI cleanup |
| SVCA readiness-policy seed and legacy reading importer | Explicit bounded deployment/history commands | Outside Slice 5; leave untouched |
| Bethany/team/token names in adapter tests and historical docs | Harmless fixture/history | Retain where accurately scoped |

No active generic business rule was found branching on a ServiceProfile name,
Bethany, 09:30, A/C1/C2/C3, Lighting/Sound/Camera/Projection/Digital Ministry,
or production profile PK. The violations are exposure/import placement and the
Lighting pilot's mutable-name identity, not the strict adapter's internal
contract constants.

## 9. Implemented 5C runtime identity semantics

5C creates the focused events-owned canonical runtime service
`events/service_profile_runtime.py`, separate from the 4A inventory. It exposes
typed, testable identity states/results, strict resolution failures, mutation
failure reasons, and no deployment-specific constants.

`inspect_service_profile_identity(event)` classifies `PROFILELESS`,
`LEGACY_ONLY`, `EXACT`, `FK_BLANK_KEY`, `FK_KEY_MISMATCH`, and
`EVENT_TYPE_MISMATCH`. `require_service_profile(event,
require_active=False)` returns only the actual FK-linked profile for exact
identity. It never looks up a profile through `service_profile_key`; the
active requirement is a separate caller choice, so an exact inactive profile
remains identity-correct.

`set_service_event_profile(event, profile)` and
`clear_service_event_profile(event)` are the supported pair-write boundary.
They write through normal validated model save behavior, advance an existing
event revision once, and return a no-op without saving for an already exact
same-profile assignment or already profileless clear. A legacy-only event may
be assigned only when the caller supplies the actual active, same-type profile
whose key exactly matches the compatibility key; the seam never infers that
profile. Clearing legacy-only state is rejected so transition evidence is not
silently erased. Invalid dual states are rejected rather than repaired.
Unsaved assignment is supported because it is the same explicit reviewed
operation and preserves normal creation semantics at revision 0.

Future profile-aware runtime consumers must adopt these semantics:

1. `ServiceEvent.service_profile` is canonical relational identity.
2. `event.service_profile.key` is the stable deployment-local machine key when
   a portable key is required.
3. `service_profile_key` is compatibility/drift evidence only.
4. A non-null FK with blank/mismatched compatibility key or mismatched event
   type fails closed and is an audit blocker.
5. A workflow that requires a profile fails closed when FK is null, including a
   legacy-only row. It never falls back to the string.
6. A generic workflow that does not require a profile accepts both fields blank
   and does not invent one.
7. During dual storage, an explicit supported profile assignment/clear writes
   both fields atomically and advances `scheduling_revision` exactly once for
   an existing event.
8. Inactive profiles remain valid on historical events. New assignment and
   explicitly current adapter/setup operations require an active profile unless
   a narrower audited historical-read rule says otherwise.
9. Querysets for profile-specific work should select/join the FK and use the
   central resolver; they must not independently reimplement fallback logic.
10. Direct ORM drift remains possible, so the read-only dual audit stays in
    service until the later destructive field-retirement slice.

## 10. Implemented integration registry API and ownership

5B owns the registry in `core/integration_registry.py`, alongside but separate
from `core.module_registry.py`:

```text
CmsIntegration(key, required_modules)
get_registered_integrations()
get_registered_integration_keys()
get_integration(key)
validate_enabled_integrations(enabled_keys=None)
get_enabled_integrations()
get_enabled_integration_keys()
is_integration_enabled(key)
require_integration_enabled(key)  # thin fail-closed route/command helper
```

Initial static registrations:

| Key | Required modules |
|---|---|
| `svca_bethany_2026_worship_xlsx` | `events`, `ministry` |
| `svca_lighting_pilot_csv` | `events`, `ministry` while retained |

Rules:

- `CMS_ENABLED_INTEGRATIONS` absent, `None`, or `[]` returns the empty enabled
  set. This intentionally differs from `CMS_ENABLED_MODULES`.
- Any unknown key raises `ImproperlyConfigured`.
- Every required module must be present in the already validated enabled module
  set or configuration raises `ImproperlyConfigured`.
- Registry metadata contains no adapter callable/module import. It validates
  names and module dependencies without loading `openpyxl` or either adapter.
- Views/commands gate first, then lazy-import the named adapter. Disabled direct
  web routes should return 404 to avoid advertising a deployment-only surface;
  disabled commands should raise `CommandError` before file read or DB query.
- Staff/superuser/capabilities are evaluated only after enablement and never
  override it.
- The generic Worship Planning view receives an enabled/authorized boolean for
  the workbook card. Lighting remains absent from navigation.
- Tests use `override_settings`; configuration access must not be cached in a
  way that defeats overrides.

This registry is a static tuple/dict and small accessor set. It must not add
entry-point discovery, auto-discovery, signals, hooks, an SDK, dynamic packages,
or third-party registration.

Adapter code should eventually live under explicit namespaces:

```text
ministry/integrations/svca_bethany_2026_worship_xlsx/
    forms.py
    preview.py        # parser, preflight, target matching, preview/signing
    confirmation.py

ministry/integrations/svca_lighting_pilot_csv/
    import_service.py
```

Current route names may remain stable. A generic events/ministry wrapper may
own the URL callable only if it performs the integration gate before lazy
adapter import.

## 11. Recommended implementation decomposition

### 11.1 `GENERIC-DEPLOYMENT-CONFIG.5B` — Integration registry, gates, and import isolation — IMPLEMENTED / LOCAL VERIFIED

Scope:

- add the explicit Core registry/API with the frozen setting semantics;
- register the two known keys and validate module dependencies;
- gate workbook card, preview route, confirmation route, Lighting route, and
  Lighting CLI;
- move or isolate adapter forms/services under explicit namespaces and remove
  unconditional imports from generic `events.forms`, `events.views`, and
  `ministry.views`;
- preserve workbook parser/matching/signing semantics and Lighting import
  semantics unchanged.

Implemented result: the exact static API above is present; both integrations
require `events` and `ministry`; absent/`None`/empty configuration enables
nothing; unknown keys and disabled required modules raise
`ImproperlyConfigured`; workbook UI/routes and Lighting web/CLI entry points
fail closed; and isolated imports prove generic modules load no adapter service
or `openpyxl`. Existing service files remain in place and are loaded lazily,
so no broad package relocation or compatibility shim was introduced.

Likely files: new `core/integration_registry.py` and focused tests;
`events/forms.py`, `events/views.py`, possibly `events/urls.py`;
`ministry/views.py`, `ministry/management/commands/import_lighting_pilot.py`;
the two adapter service namespaces; workbook/Lighting route tests; and the
Worship Planning card condition/template.

Impact: no model, migration, or data change. Behavioral change is opt-in
discoverability/direct-route/CLI failure. No signing version change. Production
must configure `CMS_ENABLED_INTEGRATIONS =
["svca_bethany_2026_worship_xlsx"]` before or atomically with deployment if the
current workbook UI must remain available. Do not enable Lighting without the
retention decision.

Rollback/fail-closed: removing the setting disables integrations; disabled
paths return 404/CommandError before adapter import/query. Rollback of code is
safe because no data changes.

Not included: ServiceProfile consumer switch, token shape change, Lighting
team-key modernization/retirement, arbitrary adapters, plugin framework.

### 11.2 `GENERIC-DEPLOYMENT-CONFIG.5C` — Canonical ServiceProfile runtime seam — IMPLEMENTED / LOCAL VERIFIED

Scope:

- add the events-owned canonical resolver/state contract;
- distinguish optional-none, exact, legacy-only missing-FK, blank-key-with-FK,
  mismatch, and type mismatch identity states, with inactive status evaluated
  separately;
- expose strict “profile required” behavior with no string fallback;
- define the explicit pair-write contract for later Admin/setup consumers;
- add exhaustive unit tests including direct-ORM drift construction.

Implemented result: `events.service_profile_runtime` owns the six-state frozen
identity result, strict FK-only resolver with optional active requirement, and
typed fail-closed pair-write/clear helpers. The helpers accept explicit
compatible legacy-only assignment, reject conflicting legacy evidence and all
invalid drift, preserve inactive exact historical identity, avoid no-op saves,
advance supported existing changes exactly once, and support unsaved creation
at revision 0. Focused tests prove zero-query/no-fallback legacy-only reads,
zero-write inspection/resolution, direct-ORM drift classification, validation
rollback, and revision/no-op behavior.

Implemented files: new `events/service_profile_runtime.py` and
`events/test_service_profile_runtime.py`. The separate 4A
`events/service_profile_identity.py` inventory remains unchanged.

Impact: no schema, migration, data, UI, route, or signing change; no existing
consumer switched. `runtime_consumer_switched` remains false globally.
Production prerequisite is still zero drift. Rollback is code-only.

Not included: workbook/readiness/Admin adoption, automatic backfill, model
fallback, legacy-field removal.

### 11.3 `GENERIC-DEPLOYMENT-CONFIG.5D` — Readiness, bounded setup, and Admin consumer switch — IMPLEMENTED / LOCAL VERIFIED

Scope:

- make readiness resolve a ServiceProfile by stable key, require schema through
  0012, select canonical rows by FK, and report drift/missing-FK separately;
- version the serialized readiness output;
- if the Bethany TEST reset remains callable, require the reviewed profile,
  fingerprint FK+key/type, write both identities, and bump reset approval to V2;
- switch ServiceEvent Admin to explicit FK selection with active-only new
  choices, existing inactive-history visibility, read-only compatibility key,
  exact pair-write/clear, and one revision bump;
- preserve ordinary forms and member presentation.

Implemented result: readiness uses `SERVICE_PROFILE_READINESS_V2`, requires
physical/recorded schema through `events/0012`, resolves the requested
`ServiceProfile.key`, and selects canonical events by the resolved FK. Its JSON
and text evidence include profile PK/key/type/active state plus each event's
FK, canonical key, compatibility key, and classified 5C identity state.
Legacy-only matching rows block readiness, profileless exact-time rows remain
human-review evidence, and exact rows owned by another strict profile are never
candidates.

The retained Bethany 2026 TEST reset now resolves the exact active correct-type
profile during preview and again inside apply before deletion. Its complete
surface fingerprint binds both event identity fields and its
`MO-S.6D-PROFILE-SETUP.1A-FU1-v2` approval binds the resolved profile's stable
operational state. V1 tokens have no compatibility path. Replacement events use
the 5C pair-write seam and remain creation revision 0; postconditions require
the exact reviewed FK/key/type pair. No reset apply was run.

ServiceEvent Admin now exposes active profiles plus the current inactive exact
profile, makes `service_profile_key` read-only compatibility evidence, and
rejects incompatible, inactive-new, or persisted drift states. The Admin form
uses the shared non-saving 5C preparation primitive, then Django Admin performs
one normal `ServiceEvent.save()`: existing changes advance one revision and new
events remain revision 0. Ordinary and recurring ServiceEvent forms remain
unchanged.

Likely files: `events/service_profile_readiness.py`,
`events/management/commands/audit_service_profile_readiness.py`,
`events/service_profile_setup.py`,
`events/management/commands/rebuild_bethany_0930_service_events.py`,
`events/admin.py`, the canonical runtime seam, and the corresponding four
focused test modules.

Impact: no schema/migration and no automatic data mutation. Admin/readiness
behavior changes. Reset V1 tokens fail closed; no reset apply was run. The
workbook files, parsed/normalized/confirmation versions, matching, and
current-truth validation remain unchanged for 5E. Therefore
`runtime_consumer_switched` remains false globally. No production or rendered
browser QA is claimed.

Rollback/fail-closed: legacy field remains populated, so code rollback remains
possible. New code fails closed on missing/mismatched FK. The setup command must
abort before deletion if exact profile resolution fails.

Not included: running reset/apply, recreating the 52 events, workbook switch,
defaults/materialization, profile retirement.

### 11.4 `GENERIC-DEPLOYMENT-CONFIG.5E` — Workbook FK matching, confirmation, and V2 signing — IMPLEMENTED / LOCAL VERIFIED

Prerequisites: 5B registry/isolation deployed/configured; 5C strict resolver;
zero-drift production audit.

Scope:

- resolve the adapter's stable profile key to one active ServiceProfile;
- match targets by FK and validate dual consistency through the central seam;
- add explicit missing-FK/drift target blockers rather than string fallback;
- bind integration key and exact profile PK/key/type to parsed/normalized/
  confirmation V2 contracts as appropriate;
- revalidate exact FK/profile/type/key after revision CAS and before any anchor
  save;
- reject every V1 parsed/preview/confirmation artifact;
- preserve strict XLSX parsing, 52-row scope, A/C token mapping, governance,
  audience, CAS, audit, no-notification, and all-or-nothing semantics.

Implemented result: `worship_xlsx_preview.py` resolves the configured target
profile without legacy fallback before matching. Canonical targets require the
resolved FK plus the 5C `EXACT` identity state; missing/inactive/wrong-type
target profiles are workbook-level blockers, while legacy-only, FK/key/type
drift, and other-profile ownership have explicit per-date blocker evidence.
The parsed contract is `SVCA_BETHANY_0930_2026_V2`, signing version `2`, salt
`ministry.worship-xlsx-preview.v2`. The normalized contract is
`SVCA_BETHANY_0930_2026_PREVIEW_V2`, signing version `2`, salt
`ministry.worship-xlsx-normalized-preview.v2`. Both bind the integration key,
target profile PK/key/type, workbook facts, user, and their existing state;
normalized canonical rows also bind the event FK and exact identity state.

Confirmation uses `SVCA_BETHANY_0930_2026_CONFIRM_V2`, signing version `2`,
and `ministry.worship-xlsx-confirmation.v2`. It binds integration, exact profile
PK/key/type, parser/preview contract revisions, workbook hash, target events,
expected profile FK/revisions, before/proposed teams, mapping, user, and
operation. After claiming all expected scheduling revisions it resolves the
configured profile once under current database truth, compares it with the
signed identity, reloads each event with its profile, and requires the 5C seam
to report exact ownership before any anchor save. Any discrepancy rolls back
all claims, anchors, and audit rows. Changed anchors still save with the
existing post-claim skip behavior; no-op behavior and all non-profile workbook
semantics are unchanged. V1 salts/shapes are not accepted.

Likely files: the named workbook adapter `preview.py`, `confirmation.py`, and
forms/views wrappers; `events/test_worship_xlsx_preview.py` and
`events/test_worship_xlsx_confirmation.py`; adapter templates only where
version/error context changes. Avoid changing the generic Worship Rotation
Planner fingerprint contract unless new repository evidence proves coupling.

Impact: no schema/migration/data backfill. Profile authority and signed shapes
changed. Production must have the integration enabled and exact current mapping.
Previously issued V1 proposals fail closed and operators must re-upload. Local
automated route/render tests passed; no rendered browser or production QA is
claimed by 5E.

Rollback/fail-closed: legacy field remains exact for rollback; a V2 code
rollback rejects V2 tokens under strict V1 decoding. Missing/inactive/drifted
profile state yields no confirmation action and no write.

Not included: arbitrary workbook support, assignment/member import, durable
import history, notifications, profile defaults, hard-coded profile PK.

### 11.5 `GENERIC-DEPLOYMENT-CONFIG.5F` — LOCAL CLOSURE PROOF COMPLETE / PRODUCTION READ-ONLY CLOSEOUT PENDING

5F used literal, case-sensitive `rg --count-matches -F` searches. Active Python
means `*.py` excluding basenames `test*.py`, every `tests/` directory, and every
`migrations/` directory. On the post-extension tree this finds **70 literal
`service_profile_key` occurrences across 11 files**. Each occurrence has one
primary classification: **A = 0, B = 39, C = 17, D = 14**. Tests contain 145
occurrences across 10 modules (E), and immutable migrations contain three
occurrences across two files (F). For a reproducible file-level documentation
bucket, “current docs” means the five canonical files named by 5F
(`GENERIC_DEPLOYMENT_CONFIGURATION_ARCHITECTURE`, this Slice 5 plan,
`MODULE_BOUNDARIES`, `PRODUCT_ARCHITECTURE_AND_ROADMAP`, and `README`): **32
occurrences across four occurrence-bearing files**. Every other `docs/*.md` is
the historical/milestone bucket: **5 occurrences across two files**. The total
is 37 across six documentation files; the surviving milestone wording was
reviewed and, where necessary, explicitly labeled historical/superseded.

Reproducible commands:

```text
rg --count-matches -F -g '*.py' -g '!test*.py' -g '!*/tests/*' -g '!*/migrations/*' service_profile_key .
rg --count-matches -F -g 'test*.py' service_profile_key .
rg --count-matches -F -g '*.py' service_profile_key events/migrations
rg --count-matches -F -g '*.md' service_profile_key docs
```

Current active-code classification:

| File / symbols | Literal occurrences | Class | Closure justification |
|---|---:|---|---|
| `events/models.py` — key validator/field and FK/key/type validation | 15 | B 4 / C 11 | Transitional storage and supported validation/write contract; comparisons reject drift and never resolve identity from the string. |
| `events/service_profile_runtime.py` — inspection and pair preparation | 4 | B 1 / C 3 | One evidence read classifies drift; remaining references write/clear the exact pair. No string lookup exists. |
| `events/service_profile_identity.py` — generic inventory | 15 | B | Read-only deployment evidence, including separately counted legacy-only, blank-key, key-mismatch, and type-drift states. |
| `events/service_profile_readiness.py` — V2 evidence/rendering | 14 | B | Canonical selection is by resolved FK; legacy-only query and payload fields are blocker/review evidence only. |
| `events/admin.py` — error remapping and read-only field | 3 | C | FK is the selector; compatibility field is read-only and pair preparation owns synchronization. |
| `ministry/services/worship_xlsx_preview.py` — normalized V2 evidence | 3 | B | Signed payload compatibility fields are evidence checked against the resolved current profile; matching authority is FK plus exact 5C state. |
| `events/service_profile_mapping.py` — 4A mapper | 9 | D | Bounded historical/onboarding mapper intentionally selects the complete exact legacy set before creating/writing the FK. It is not a runtime consumer. |
| `events/service_profile_setup.py` — reset V2 fingerprint | 2 | D | Bounded TEST reset evidence binds both identities and creates exact pairs through 5C. |
| `events/management/commands/configure_service_profile_mapping.py` | 2 | D | Renders retained 4A plan/history, including the historically accurate operation status. |
| `events/management/commands/rebuild_bethany_0930_service_events.py` | 1 | D | Renders the bounded reset V2 compatibility snapshot only. |
| `events/management/commands/audit_service_profile_readiness.py` | 2 | B | Uses the shared key validator for the requested actual `ServiceProfile.key`; no legacy event lookup or fallback. |

Former Class-A closure proof:

- Readiness resolves `ServiceProfile.key` to one active compatible profile,
  selects canonical rows by `service_profile=profile`, and treats the explicit
  FK-null/string query only as legacy-only blocker evidence.
- ServiceEvent Admin edits the FK, renders the compatibility field read-only,
  and delegates in-memory pair preparation to 5C before Django performs one
  normal save. Ordinary event forms expose neither technical field.
- Worship preview resolves the adapter key to the actual profile, requires the
  event FK to equal that profile PK and 5C state `EXACT`, and classifies
  legacy-only, drift, and other-profile exact events as non-target blockers.
  No compatibility-string equality grants target ownership.
- Worship confirmation binds and current-truth checks signed profile PK/key/
  type, re-resolves after revision CAS, reloads with the profile relation, and
  requires exact FK ownership before any anchor save. The legacy string grants
  no confirmation authority.

Only the active workbook contracts
`SVCA_BETHANY_0930_2026_V2`,
`SVCA_BETHANY_0930_2026_PREVIEW_V2`, and
`SVCA_BETHANY_0930_2026_CONFIRM_V2` remain in non-test Python. V1 names/salts
remain only in explicit rejection tests and clearly historical documentation;
there is no V2-then-V1 decoder fallback and no optional profile identity.

The existing identity inventory remains the deployment audit framework. Its
small 5F extension adds only distinct summary/report facts for profileless,
legacy-only, FK/blank-key, nonblank FK/key mismatch, and event/profile-type
drift. Counts for different drift dimensions may overlap when one bypassed row
has more than one defect; `drifted_fk_events` remains the union/non-exact count.
The command is still generic, read-only, and has no `--apply` or target default.

Impact: no field retirement, schema, migration, signing, readiness/reset,
Admin, mapping, or ordinary runtime behavior change; no normal-local or
production data operation. This is the local gate for the separately performed
production read-only closeout and a later separately approved destructive
contract-retirement plan.

### 11.6 Lighting follow-up decision

After 5B, but not as an automatic Slice 5 continuation:

- if retained, approve a focused task to resolve one reviewed
  `MinistryTeam.team_key`, reject missing/duplicate/inactive/non-assignable
  targets, stop creating/renaming teams by name, and update focused importer
  tests;
- if not retained, approve a separate route/command/service/template/docs
  retirement task.

No production deployment should enable `svca_lighting_pilot_csv` before one of
those paths is approved.

## 12. Future test and verification matrix

| Slice | Required focused tests | Static/check commands | Target/deployment evidence |
|---|---|---|---|
| 5B | absent/None/[] disabled; known enable; unknown key error; required-module error; staff cannot bypass; hidden workbook card; direct 404; disabled no parser/importer query; generic events/ministry import without adapter/openpyxl load; Lighting web/CLI disabled; enabled behavior regression | `manage.py check`, focused registry/events/ministry tests, import smoke, `git diff --check` | Configure exact approved workbook key before release; no data command |
| 5C | all six identity states; optional-none; required missing-FK; mismatch/type/inactive; select-related behavior; pair assignment/clear; exact one revision; direct ORM bypass detected | focused model/runtime tests, `manage.py check`, `makemigrations --check --dry-run`, `git diff --check` | Read-only identity audit remains zero drift |
| 5D | FK-owned readiness; no fallback; schema 0012 check; serialized version; Admin active/inactive choices; key read-only; pair write/clear; reset V2 determinism/staleness/missing profile/rollback/dual creation | focused profile/readiness/setup/Admin tests, checks above | No reset apply; read-only audit before/after; rendered Admin QA |
| 5E | exact FK target; legacy-only/mismatch/type/inactive blockers; V1 token rejection; V2 strict shape/tamper/user/expiry; profile drift after preview/CAS; full rollback; 52 success/no-op; disabled route still no query | focused XLSX preview/confirmation plus file-backed SQLite tests, checks above | GoDaddy Python 3.11.15/openpyxl 3.1.5 import; read-only preview first; rendered English/Chinese route QA; no hard-coded PK |
| 5F | **LOCAL CLOSURE PROOF COMPLETE:** audit exact/legacy-only/blank-key/key-drift/type-drift counts; command zero-write; current classified repository inventory; Class A = 0 | focused profile/audit/readiness/setup/Admin/workbook/integration suites, exact `rg` searches, `manage.py check`, `makemigrations --check --dry-run`, `git diff --check` | **PENDING:** post-deployment read-only identity + Readiness V2 audit, explicit workbook integration setting, fresh-workbook no-op preview, and English/Chinese rendered verification |

Do not run the full Django suite without separate approval. Browser/manual QA
is required only for slices that actually change rendered Admin/integration
surfaces and must not be claimed unless performed.

## 13. Deployment and cutover considerations

1. Before production 5E deployment, rerun `audit_service_profile_identity`
   against the exact target database and require zero drift and all required
   rows mapped.
2. Run Readiness V2 for `bethany_0930_cm` and require the exact 52-row FK-owned
   annual scope; also require the resolved profile to remain active with event
   type `sunday_service`.
3. Configure `CMS_ENABLED_INTEGRATIONS` to explicitly include
   `svca_bethany_2026_worship_xlsx`. Because absence means disabled, a missed
   setting intentionally hides/fail-closes the workbook workflow.
4. Do not enable the Lighting key until retention and team identity are
   explicitly decided.
5. Keep GoDaddy Python 3.11.15 and `openpyxl` 3.1.5 deployable. Import smoke is
   required for the enabled adapter, not evidence of workbook correctness by
   itself.
6. Treat every unsubmitted V1 parsed preview, normalized preview, and
   confirmation proposal as invalid. Operators must re-upload the workbook;
   do not preserve in-flight V1 state or add compatibility parsing.
7. Never configure or sign a database PK as deployment configuration. The
   adapter resolves the stable key to the current local PK and binds both in
   the short-lived proposal.
8. The consumer switch requires no automatic row rewrite because the reviewed
   target rows are already mapped. Any future unmapped deployment must complete
   the 4A audit/review/apply first.
9. Post-switch production evidence must prove the same 52 reviewed SVCA rows
   resolve through FK/Profile, with exact dual consistency and no unrelated
   change. This is read-only audit evidence, not generic cardinality.
10. Preserve the legacy field for rollback and drift evidence until a later
    destructive contract-retirement approval.
11. A rollback to pre-5E code can still read the populated compatibility key,
    but strict V1 code rejects V2 artifacts. This fail-closed rollback is
    intentional; do not add cross-version decoding.
12. 5E ran no production reset, mapper apply, migration, or other data command.
    Deployment work must separately report code release, settings, read-only
    audits, and any data mutation.
13. After 5F is committed and deployed, run exactly:
    `python manage.py audit_service_profile_identity` and
    `python manage.py audit_service_profile_readiness --profile-key
    bethany_0930_cm --year 2026 --time 09:30 --event-type sunday_service`.
    Require one active reviewed target profile (record its actual deployed PK),
    52 linked/FK-non-null/exact rows, zero legacy-only/key/blank/type drift,
    zero multi-type conflicts and integrity blockers, plus Readiness V2 at
    52 canonical, 52 ready, zero missing, `PROFILE SETUP READY`.
14. Confirm the deployed setting explicitly enables
    `svca_bethany_2026_worship_xlsx` and does not enable
    `svca_lighting_pilot_csv` for this closeout. Then use a fresh workbook
    upload. Expected deployment evidence is 52 matched canonical FK targets,
    zero blocked, 52 no-op, zero proposed, and no confirmation action. Stop on
    any difference. Verify English/Chinese success and error surfaces. These
    deployment/browser steps were not performed by 5F.

## 14. Explicit non-goals

- removing `ServiceEvent.service_profile_key`;
- changing or recreating the reviewed 52 production events;
- hard-coding profile PK 1 or assuming one profile/deployment;
- inferring a profile from name, time, title, venue, language, audience, date,
  recurrence, key resemblance, or Worship Team;
- adding ServiceProfile ministry defaults, materialization, MO-S.REQUIRED, or
  live inheritance;
- changing generic Worship rotation/governance semantics;
- expanding the XLSX contract, importing assignments/members, or adding import
  history/notifications;
- modernizing or retiring Lighting without separate approval;
- plugin SDK, Python entry points, auto-discovery, signals/hooks/event bus, or
  third-party package discovery;
- external-system identity mapping without a real contract;
- normal ServiceEvent UX redesign or technical identity exposure to members;
- production query/mutation or browser QA in 5A.

## 15. Blockers and open decisions

No architecture contradiction blocked 5E. Current repository truth matches the
frozen architecture: 3A is additive, 4A supplies exact dual mapping/audit, 5C
supplies the shared seam, 5D switches the approved non-workbook consumers, and
5E switches the final currently known Class-A workbook consumer.

Two bounded owner decisions remain, neither blocking registry implementation:

1. **Lighting retention:** confirm operational value before team-key work or
   retirement. Until then it stays registered but disabled and unreachable.
2. **Bethany TEST reset retention:** 5D retains it as FK/dual-safe V2 tooling.
   Retirement still requires a separately approved cleanup.

5B, 5C, 5D, and 5E are complete and locally verified. 5F now proves local
repository/runtime closure with Class A legacy authority at zero. Production
read-only closeout remains pending; `runtime_consumer_switched` therefore
remains false. After the committed 5F code is deployed, satisfy section 13,
including explicit `svca_bethany_2026_worship_xlsx` enablement, zero-drift
identity and 52-row Readiness V2 evidence, a fresh no-op workbook preview, and
English/Chinese rendered verification. Do not enable the Lighting key without
the separate retention/identity decision.
