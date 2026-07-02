# Module Boundaries — Modular CMS Foundation

Status: current as of `MODULAR-CORE.1A` (July 2026).

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

## Registry and feature gates (MODULAR-CORE.1A)

* `settings.CMS_ENABLED_MODULES` is the single enablement source. Default
  ships with all current modules enabled, preserving current behavior.
  Unregistered keys in the setting raise `ImproperlyConfigured`.
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
  `{% if "prayers" in enabled_modules %}`.

### What disabling a module does today

* Hides its primary nav link in `templates/base.html`.
* Skips its aggregation on Today (`reading.views.home`) so no card, query,
  or crash comes from the disabled module, and hides its "Where to go next"
  card. Ministry gating also hides the Today action-center serving summary,
  the Leader Needs Attention card, per-gathering serving notes, and the
  profile page's My Serving card.

### What disabling a module does NOT do (known limitations)

* It does not unload the app, its models, admin registrations, or URLs.
  Direct URLs of a disabled module remain reachable and are protected only
  by their existing per-view permission/visibility rules.
* It does not gate the staff dropdown menu entries, the staff overview
  (`/staff/`) sections, or setup/readiness checks.
* It does not perform Python import isolation: `reading.views` still
  imports events/studies/ministry helpers at module load; gates are
  behavioral checks at request time.

## Boundary rules for future work

1. **Modules depend on Core, not on each other.** Avoid new direct
   cross-module imports. Existing cross-module reads (Today aggregation in
   `reading.views.home`; ministry reading `events` / studies serving roles)
   are declared in the registry's `depends_on` / dependency notes and
   should not grow silently.
2. **Today should become provider/registry-driven.** Today currently lives
   in the reading app and imports other modules directly. The target shape
   is per-module Today providers registered against the module key, with
   the home view aggregating enabled providers. `MODULAR-CORE.1A` only
   added safe per-module guards.
3. **Nav should become registry-driven.** `base.html` currently hard-codes
   links behind `enabled_modules` checks; the target is nav entries
   contributed by module metadata.
4. **Setup/readiness checks should become module-owned and aggregated.**
   `accounts.trial_setup_readiness` currently imports events / ministry /
   studies directly; the target is per-module checks aggregated by a core
   runner for enabled modules only.
5. **Structure core stays general.** Do not hard-code one church's exact
   organization into Core; audience scoping stays per-module rows matched
   against membership.
6. **Membership is not serving.** `ChurchStructureMembership` is belonging.
   Serving remains explicit (`TeamAssignmentMember`, linked-user
   `BibleStudyMeetingRole`).
7. **Deferred modules stay deferred.** Community Events and Checklist are
   not to be built until this foundation is in place and their slices are
   explicitly approved. New modules must register here first, with an
   explicit migration slice.

## Follow-ups (not in MODULAR-CORE.1A)

* Provider-based Today aggregation (rule 2).
* Registry-driven nav construction (rule 3).
* Module-owned setup/readiness checks (rule 4).
* Optional: gating staff menu sections and staff overview cards by module.
* Optional: middleware/route-level gating for disabled module URLs, if a
  church-facing deployment ever needs hard-off modules.
