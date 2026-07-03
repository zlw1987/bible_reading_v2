# Module Boundaries — Modular CMS Foundation

Status: canonical current-state module boundary, updated through
`MODULAR-CORE.6B` (July 2026).

This project is becoming a lightweight modular church management system.
Churches should eventually be able to enable only the modules they need, and
individual modules should be able to integrate with existing church systems.
This document defines what is Core, what is a Module, and the boundary rules
future work must follow so new modules do not make the monolith more tightly
coupled.

`MODULAR-CORE.1A` introduced the central module registry and feature gates
described here. It deliberately did **not** rename apps, extract packages,
add a plugin framework, change the database, or remove any URL.

## Core vs Modules

### Core (always on, never gated)

Core is the foundation every module may depend on:

* Identity / auth: Django auth, `accounts.Profile`, login/signup/password
  flows, language preference, bilingual UI text.
* Church structure: `ChurchStructureUnit` (canonical hierarchy via
  `.parent`) and `ChurchStructureMembership` (canonical belonging for
  migrated runtime paths).
* Permissions and audience primitives: `ChurchRoleAssignment` with explicit
  `structure_unit`, capability checks, and the audience-scope pattern
  (per-module audience rows matched against active primary membership,
  zero rows fail closed).
* The module registry itself (`core/module_registry.py`) and its template
  context support.

App mapping today: `core` (registry/foundation code) and `accounts`
(identity + structure core) are Core apps. `comments` (reflections) is a
support app of the reading module's surfaces, not an independently gated
module.

### Modules (registered, gateable)

Registered in `core/module_registry.py`, enabled via
`settings.CMS_ENABLED_MODULES`:

| Key        | App        | Surface                                | Notes |
|------------|------------|----------------------------------------|-------|
| `reading`  | `reading`  | Daily Reading / 每日读经                | Group progress + reflections read structure snapshots and membership. |
| `prayers`  | `prayers`  | Prayer / 代祷                           | Visibility via `structure_unit_at_post` + membership. |
| `studies`  | `studies`  | Bible Study / 查经 (V2)                 | Audience rows + membership; zero rows fail closed. |
| `events`   | `events`   | Church Gatherings / 教会聚会            | Audience rows + membership; zero rows fail closed. |
| `ministry` | `ministry` | Ministry teams, serving, My Serving / 我的服事 | Depends on `events` (assignments schedule against ServiceEvents). Membership is belonging, never serving. |

## Registry and feature gates (through MODULAR-CORE.6B)

* `settings.CMS_ENABLED_MODULES` is the single enablement source. Default
  ships with all current modules enabled, preserving current behavior.
  Unregistered keys in the setting raise `ImproperlyConfigured`.
* Dependency metadata is enforced (`MODULAR-CORE.2A`). A module's declared
  `depends_on` modules must also be enabled; otherwise reading the enabled
  set raises `ImproperlyConfigured`. Example: `ministry` depends on
  `events`, so `CMS_ENABLED_MODULES=["ministry"]` is rejected. Validation
  runs whenever the enabled set is read (`get_enabled_module_keys()` /
  `validate_enabled_modules()`), so it also fires under test
  `override_settings`. Enforcement is still a surface gate only: it does
  not unload apps, models, or URLs, and it is not route-level hard-off.
  Absent/None setting stays "all enabled" and empty `[]` stays valid (no
  enabled module can violate a dependency).
* API (`core.module_registry`): `get_registered_modules()`,
  `get_registered_module_keys()`, `get_module(key)`,
  `get_enabled_modules()`, `get_enabled_module_keys()`,
  `is_module_enabled(key)`, `module_has_capability(key, capability)`.
  `is_module_enabled` raises on unregistered keys to catch typos.
* Capabilities are descriptive metadata for now: `contributes_nav`,
  `contributes_today`, `contributes_setup_checks`,
  `requires_structure_core`.
* Templates get `enabled_modules` (a frozenset of keys) from
  `core.context_processors.module_context`, used as
  `{% if "prayers" in enabled_modules %}`. The same context processor exposes
  `enabled_primary_nav_entries`: enabled modules' ordered route, bilingual
  label, and active-state metadata from the registry (`MODULAR-CORE.4A`).
* `MODULAR-CORE.2B` strengthens content-level regression coverage for disabled
  module surfaces. Tests cover the primary nav, Today reading/prayer/study/event
  and ministry surfaces, the profile My Serving card, the valid
  events-plus-ministry dependency shutdown, and the all-disabled home state.
* `MODULAR-CORE.3A` adds the provider-based Today aggregation foundation
  (`core/today_providers.py`). Each module with Today context registers one
  provider against its module key (`register_today_provider`) together with
  the safe default values for the context keys it owns; the home view calls
  `build_today_context(request)`, which calls providers for enabled modules
  only and keeps the registered defaults for disabled ones. Context keys are
  exclusive per provider, provider output is validated against its declared
  keys, and reading the enabled set keeps `MODULAR-CORE.2A` dependency
  validation in force. Registration is explicit (no app auto-discovery).
  Prayer contributes only the static Today action card (template-gated), so
  it has no provider.
* `MODULAR-CORE.3B` moves the Today provider bodies into their owning
  modules: `reading/today_provider.py`, `events/today_provider.py`,
  `studies/today_provider.py`, and `ministry/today_provider.py`, with the
  shared Today/This Week date-window helper in `core/today_windows.py`.
  Each module file owns its provider body, helpers, and declared safe
  defaults, and exposes a `register()` function; `reading.views` (the home
  route's module) remains the single explicit registration site, calling the
  four `register()` functions in a fixed order at import time — before any
  `home()` request. The per-gathering serving note stays ministry-owned
  (`ministry.today_provider.get_week_serving_notes`) and is read by the
  events provider, returning an empty mapping when ministry is disabled.
  No context key, template, visibility, or serving semantics changed.
* `MODULAR-CORE.4A` makes the ordinary authenticated-user module links in
  `templates/base.html` registry-driven. Each nav-contributing module supplies
  its route, bilingual labels, active-state key, and display order through
  module metadata. Today remains an always-available Core link. At the `4A`
  milestone, the account dropdown and hard-coded staff dropdown were
  unchanged; `MODULAR-CORE.6A` later gated the staff dropdown's module-owned
  links while leaving its Core/staff links available.
* `MODULAR-CORE.5A` adds the module-owned setup/readiness check foundation
  (`core/setup_readiness.py`). Each readiness contribution registers a provider
  under a unique name against `core.setup_readiness`; Core providers
  (`module_key=None`) always run and module providers run only when their
  module is enabled. `accounts.trial_setup_readiness` is the single explicit
  registration site (no app auto-discovery) and wires providers in a fixed
  order so the operator-facing section order (1..6) and existing output are
  preserved. The ministry-structure / TeamAssignment serving sections are now
  owned by `ministry/setup_readiness_provider.py`, and the Bible Study
  meeting-serving section by `studies/setup_readiness_provider.py`. Church
  Structure / membership readiness and the permission/admin section stay Core
  providers. The `audit_trial_setup_readiness` command, its options, its
  read-only guarantee, and the `COUNTER_LABELS` rendering are unchanged. With
  the default all-modules-enabled configuration the report is identical to
  before. Reading the enabled set keeps `MODULAR-CORE.2A` dependency validation
  in force, so an invalid `CMS_ENABLED_MODULES` raises `ImproperlyConfigured`
  here too.
  * Still centralized (documented limitation): the ServiceEvent / Bible Study
    **audience-visibility** section (section 5) stays a Core, always-run
    provider. It merges events and studies audience rows into one operator
    section, and its zero-audience fail-closed checks are the most important
    trial blockers, so they are intentionally not gated behind
    `events` / `studies` enablement. Events therefore has no dedicated
    readiness provider yet; its trial-blocker checks live in this shared Core
    section. A future slice may split it into events- and studies-owned
    providers if module-gated audience readiness is ever wanted.
* `MODULAR-CORE.6A` applies module surface gates to the hard-coded staff
  dropdown in `templates/base.html`. Reading Plan Admin follows `reading`;
  the three Bible Study management links follow `studies`; Church Gatherings
  follows `events`; Ministry Teams and Team Assignments follow `ministry`; and
  Prayer Reports follows `prayers`. Reflection Reports remains visible because
  `comments` is a reading support app rather than an independently registered
  module. Staff Overview, Church Structure Setup & Review, Ministry Structure,
  user/review links, and Django Admin remain always visible to staff. This
  changes staff-dropdown discoverability only; setup routes/checks, direct
  URLs, admin routes, and permissions are unchanged. At the `6A` milestone,
  Staff Overview content was unchanged; `MODULAR-CORE.6B` later gated its
  module-owned cards/counts/links while preserving the route and Core/staff
  content.
* `MODULAR-CORE.6B` applies module surface gates to the Staff Overview
  (`/staff/`) content — its module-owned cards, counts, and workflow links —
  in `accounts.views.staff_overview` and
  `templates/accounts/staff/overview.html`. The Bible Study card follows
  `studies`; the prayer moderation counts and the Prayer Reports link follow
  `prayers`; the Ministry Operations card follows `events` or `ministry` (the
  service-events count/link follow `events`; the team-assignment counts,
  ministry ops health flags, and the Ministry Teams / Ministry Structure /
  Team Assignments links follow `ministry`). The view now computes each
  module's (sometimes expensive) counts only when that module is enabled and
  keeps safe zero defaults otherwise, so a disabled module contributes no query
  and no empty card. The Staff Overview route itself stays Core and always
  reachable for staff; the Membership Requests card, the reflection moderation
  counts, the Moderation Queue and Reflection Reports links, and the Users and
  Admin card (User Admin, Church Structure Setup & Review, Django Admin) stay
  Core/staff and always render. Two ambiguous surfaces were resolved to mirror
  `MODULAR-CORE.6A`: Reflection Reports / reflection moderation counts stay
  Core/support (visible regardless of `reading`) because `comments` is a
  reading support app, not a registered module, and the Moderation Queue stays
  Core/support and always visible. The Staff Overview has no reading-plan
  management card (Reading Plan Admin lives only in the staff dropdown), so
  disabling `reading` removes no overview card. Direct module URLs, setup/admin
  routes, permissions, and route-level access are unchanged.

### What disabling a module does today

* Omits its registry-contributed primary nav link from `templates/base.html`.
* Omits its module-owned staff dropdown links from `templates/base.html`
  (`MODULAR-CORE.6A`) while leaving the staff dropdown itself and its Core
  links available.
* Hides its module-owned Staff Overview cards, counts, and workflow links
  (`MODULAR-CORE.6B`) and skips computing their counts, while the Staff
  Overview route stays reachable and its Core/staff cards (Membership
  Requests, reflection moderation, Moderation Queue, Users and Admin) stay
  visible.
* Skips its Today provider (`core.today_providers.build_today_context` does
  not call disabled modules' providers and keeps their registered safe
  defaults) so no card, query, or crash comes from the disabled module, and
  hides its "Where to go next" card. Ministry gating also hides the Today
  action-center serving summary, the Leader Needs Attention card,
  per-gathering serving notes, and the profile page's My Serving card.
* Skips its owned setup/readiness provider sections in the
  `audit_trial_setup_readiness` report (`MODULAR-CORE.5A`): disabling `ministry`
  drops the ministry-structure and TeamAssignment serving sections; disabling
  `studies` drops the Bible Study meeting-serving section. Core sections
  (Church Structure, permission/admin) and the always-run audience-visibility
  section are unaffected, so fail-closed zero-audience blockers keep surfacing.
* Requires a dependency-valid configuration. Disabling `events` also requires
  disabling `ministry`; keeping `ministry` enabled without `events` is rejected
  rather than silently producing a partial serving surface.

### What disabling a module does NOT do (known limitations)

* It does not unload the app, its models, admin registrations, or URLs.
  Direct URLs of a disabled module remain reachable and are protected only
  by their existing per-view permission/visibility rules.
* It does not gate the staff overview (`/staff/`) *route* or the
  setup/readiness *route*. `MODULAR-CORE.6B` gates only the overview's
  module-owned *content* (cards/counts/links); the `/staff/` route itself
  stays reachable with its Core/staff dashboard. Likewise the
  `audit_trial_setup_readiness` command and any setup route stay reachable;
  `MODULAR-CORE.5A` only makes that command's module-specific *check sections*
  run per module enablement, and Core / audience checks always run.
* It does not perform Python import isolation: `reading.views` still
  imports the events/studies/ministry `today_provider` modules (which in
  turn import their apps' views helpers) at module load; gates are
  behavioral checks at request time.

## Boundary rules for future work

1. **Modules depend on Core, not on each other.** Avoid new direct
   cross-module imports. Today provider bodies live in module-owned provider
   files, while `reading.views` is only their explicit registration site.
   Existing cross-module reads (including ministry reading `events` / studies
   serving roles) are declared in the registry's `depends_on` / dependency
   notes and should not grow silently.
2. **Today is provider/registry-driven (`MODULAR-CORE.3A` + `3B`).**
   Per-module Today providers are registered against their module key in
   `core/today_providers.py`, and the home view aggregates enabled
   providers through `build_today_context`. The provider bodies live in
   each module's `today_provider` module (`MODULAR-CORE.3B`); the remaining
   coupling is deliberate and small: `reading.views` stays the explicit
   registration site, and the events provider reads the ministry-owned
   serving-note helper (module-gated inside ministry).
3. **Primary module nav is registry-driven (`MODULAR-CORE.4A`).** Enabled
   ordinary-user module links come from each module's registry metadata.
   Today stays Core; the account and staff dropdowns remain separately
   hard-coded. The staff dropdown's module-owned links are individually
   guarded by the enabled-module set (`MODULAR-CORE.6A`).
4. **Setup/readiness checks are provider/registry-driven (`MODULAR-CORE.5A`).**
   Module-specific checks register readiness providers against
   `core.setup_readiness` and are aggregated by `build_readiness_sections` for
   enabled modules only; `accounts.trial_setup_readiness` is the single
   explicit registration site. Ministry and studies checks are module-owned;
   Church Structure / permission-admin checks stay Core. The shared
   audience-visibility section remains a Core, always-run provider (see the
   `MODULAR-CORE.5A` note above) — events has no dedicated provider yet, so do
   not assume every capability-declared `contributes_setup_checks` module owns
   its own provider file today.
5. **Structure core stays general.** Do not hard-code one church's exact
   organization into Core; audience scoping stays per-module rows matched
   against membership.
6. **Membership is not serving.** `ChurchStructureMembership` is belonging.
   Serving remains explicit (`TeamAssignmentMember`, linked-user
   `BibleStudyMeetingRole`).
7. **New modules require explicit approval.** The modular foundation is now in
   place through `MODULAR-CORE.6B`, so Community Events/Activities may be
   considered next, but `COMMUNITY-EVENTS-READINESS.0A` is docs-only and does
   not approve or implement it. Checklist remains deferred. A new module must
   receive a separately approved implementation slice and register here as
   part of that work, with explicit model/migration scope.

## Follow-ups (not yet done)

* Optional: split the shared audience-visibility readiness section into
  events-owned and studies-owned providers, if module-gated audience readiness
  is ever wanted. Today it stays a Core, always-run provider so fail-closed
  zero-audience blockers surface regardless of module enablement
  (`MODULAR-CORE.5A`).
* Optional: middleware/route-level gating for disabled module URLs, if a
  church-facing deployment ever needs hard-off modules.
