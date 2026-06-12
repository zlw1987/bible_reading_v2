# Church Structure Core Migration Plan (CS-CORE)

## 1. Purpose and Status

CS-CORE.0A is the docs-only architecture decision record (ADR) and staged migration plan for promoting Church Structure from a transitional foundation to the core model of the CMS.

Status: CS-CORE.0A is complete with this document. CS-CORE.0B.1, CS-CORE.1A, CS-CORE.1B, and CS-CORE.1C are also complete as narrow, separately approved slices. CS-CORE.1C closes the Bible Study resolver re-home/parity milestone: Bible Study compatibility imports now delegate to the shared selector layer, meeting generation remains unchanged, and ordinary member visibility still uses `Profile.small_group`. Later CS-CORE milestones still require their own separate approval.

This document is the primary CS-CORE plan. It builds on, and where noted supersedes, the transitional-era statements in:

- `docs/CHURCH_STRUCTURE_MAPPING_AND_MEMBERSHIP_STRATEGY.md` (CS-H.3/CS-H.4/CS-H.5 era)
- `docs/FLEXIBLE_CHURCH_STRUCTURE_AND_AUDIENCE_SCOPE_DESIGN.md` (CS-H.1)
- `docs/SERVICE_EVENT_AUDIENCE_RUNTIME_MIGRATION_PLAN.md` (SE-AS.3 through SE-AS.6B)
- `docs/CHURCH_STRUCTURE_MAP_AND_SETUP_READINESS_PLAN.md` (CS-MAP / CS-SETUP)

Where older docs say mapping fields or `ChurchStructureUnit` have "no runtime behavior," that statement is historical: it was true when written, and it stopped being true when BS-AS.1 and SE-AS.4 shipped. Section 3 records current behavior.

## 2. Executive Summary

- Church leadership treats church structure as a core foundation module. The project is therefore moving Church Structure from a transitional dual-model state to the canonical core model, deliberately and in small slices.
- `ChurchStructureUnit` gradually becomes the canonical church structure tree. `ChurchStructureMembership` gradually becomes the canonical user belonging source.
- Legacy `MinistryContext`, `District`, `SmallGroup`, and `Profile.small_group` become a compatibility layer during migration and are retired gradually, table by table, at the end.
- This is **gradual retirement, not a big-bang drop**. No legacy table is dropped, no legacy field is deleted, and no runtime source of truth switches in this milestone or as a side effect of any other milestone. Each switch is its own approved, tested slice with a per-consumer rollback path.
- The hardest remaining work is not audience scope (both structure-scope consumers already run on `ChurchStructureUnit` rows with legacy fallback). It is the **belonging migration**: every ordinary-user matching decision still terminates in `Profile.small_group`, and `ChurchStructureMembership` is consulted by zero runtime consumers.

## 3. Current State (verified against code at CS-CORE.0A time)

### 3.1 Already structure-driven

- ServiceEvent ordinary-user visibility (SE-AS.4/SE-AS.5): events with `ServiceEventAudienceScope` rows use those rows; events with zero rows fall back to legacy `scope_type` / `district` / `small_group` (`events/models.py`, `ServiceEvent.can_be_seen_by`).
- Bible Study Schedule eligibility and meeting generation (BS-AS.1/BS-AS.2, CS-CORE.1C): schedules with `BibleStudySeriesAudienceScope` rows resolve selected units to eligible active legacy `SmallGroup` rows through the shared selector-layer resolver (`accounts/structure_selectors.py`, with the `studies.models.resolve_units_to_small_groups` compatibility wrapper); schedules with zero rows use legacy scope fields.
- ServiceEvent and Bible Study now share the selector-layer unit-to-legacy-group resolver. Their staff audience selectors reuse the shared hierarchical picker pattern.
- Signup/Profile capture `ChurchStructureMembership(status=requested)` rows; staff approval activates membership and conditionally syncs `Profile.small_group` (CS-H.6 through CS-H.9).
- Read-only diagnostics exist: `/staff/structure/` map with drift indicators, `/staff/structure/mappings/` review/edit with conflict overlays and impact acknowledgement, plus `seed_church_structure_units`, `backfill_church_structure_memberships`, and the audit-only `backfill_service_event_audience_scopes` commands.

### 3.2 Still legacy-driven

- Ordinary runtime belonging is `Profile.small_group`, everywhere: ServiceEvent non-root audience matching, `BibleStudyMeeting.can_be_seen_by`, the `/studies/` member landing, legacy `BibleStudySession` visibility, reflection-wall group privacy (`small_group_at_post`), and reading group progress.
- `ChurchStructureMembership` is **not** a runtime visibility source. It exists for signup/request/approval, diagnostics, and backfill only.
- Permissions (`ChurchRoleAssignment`) scope only by legacy `District` / `SmallGroup` / global; no unit-scoped role exists.
- `BibleStudyMeeting.small_group` and `ReflectionComment.small_group_at_post` bind meeting history and comment privacy snapshots to legacy `SmallGroup` rows.

### 3.3 The mapping bridge is no longer inert

The nullable `church_structure_unit` mapping FKs on `MinistryContext`, `District`, and `SmallGroup` were added as a passive bridge (CS-H.3B). Since BS-AS.1 and SE-AS.4, structure-based audience scopes resolve through these fields at request time. Therefore:

- Editing a legacy-to-unit mapping can change which current groups/members match an existing structure-based ServiceEvent audience or Bible Study Schedule, and which groups Bible Study meeting generation targets.
- The `/staff/structure/mappings/` edit flow already requires an explicit impact acknowledgement for this reason (CS-SETUP.1D.4).
- Older doc statements that the mapping fields "do not drive runtime behavior" are superseded. (The `help_text` on those model fields says the same stale thing; it must be corrected only in a later code-touching milestone, because changing field options can create migrations. It is recorded here so it is not forgotten.)

## 4. Target Architecture

- **Canonical structure tree:** `ChurchStructureUnit` (single active whole-church root; typed, ordered, cycle-validated hierarchy).
- **Canonical belonging:** `ChurchStructureMembership` — eventually. Active, dated, approved membership rows (one active primary per user) become the runtime answer to "which units does this user belong to."
- **Compatibility layer during migration:** `MinistryContext`, `District`, `SmallGroup`, their `church_structure_unit` mapping FKs, and `Profile.small_group`. During migration they remain runtime-load-bearing; at the end state `Profile.small_group` becomes a derived/sync-only mirror, then read-only, and legacy tables are retired per Section 12 only after nothing reads them.
- **Audience selection stays per-module:** app-specific join models (`ServiceEventAudienceScope`, `BibleStudySeriesAudienceScope`, and future modules' own join models) selecting `ChurchStructureUnit` rows. No shared generic audience table, and no new legacy-only multi-select scope fields.
- **Final runtime matching target:** ordinary-user audience matching eventually compares the user's **active structure memberships** (plus unit ancestors/descendants as the rule requires) **directly against selected structure units, with no legacy small-group hop**. The unit-to-`SmallGroup` resolver then remains only where legacy rows are still the work target (e.g. meeting generation) until those consumers are migrated or retired.
- **Permissions and serving stay separate:** `ChurchRoleAssignment` + capabilities, and `TeamAssignment` / My Serving, are not migrated by CS-CORE. A structure-aware role scope is an optional, separate decision (CS-CORE.2D).

## 5. Concept Separation Rules (binding)

These six concerns must remain separate concepts, separate surfaces, and separate milestones. No single UI and no single milestone may mix them:

1. **Structure setup** — creating, renaming, moving, deactivating `ChurchStructureUnit` rows. Write surface today: Django Admin (plus the narrow CS-SETUP.1B rename slice). Future primary surface: CS-CORE.2A staff setup UI.
2. **Membership roster / user belonging** — who belongs to which unit; requests, approvals, transfers, end dates. Surfaces: signup/Profile request capture, staff approval queue, Django Admin; future roster UI is CS-CORE.2C, never embedded in structure setup.
3. **Audience selection** — per-event / per-schedule unit picks through module-specific join models and the shared picker. Belongs to each module's create/edit flow, never to structure setup.
4. **Legacy mapping diagnostics** — `/staff/structure/mappings/` review/edit. Migration diagnostics and advanced maintenance only. It is not, and must not become, the main staff setup UI; it is retired together with the mapping bridge.
5. **Permissions / role scopes** — `ChurchRoleAssignment` and the capability map. Membership never implies capability; structure setup never edits roles.
6. **Serving assignments** — `TeamAssignment` / `TeamAssignmentMember` / My Serving. Independent of audience and belonging; membership never infers serving.

The existing binding rule that Audience Scope, Host / Language Label, Required Ministry Teams, Rotation Anchor Team, and TeamAssignment are distinct concepts remains in force unchanged.

## 6. Runtime Contract During Transition (binding until explicitly superseded per consumer)

1. `Profile.small_group` remains the ordinary-member runtime belonging source for all current consumers.
2. `ChurchStructureMembership` must not grant or deny any visibility, audience match, eligibility, or access until the explicit CS-CORE.2B migration for that specific consumer, with targeted tests.
3. Requested memberships never grant anything, in any milestone, ever.
4. Active memberships are diagnostic/shadow-comparison data only until the explicit per-consumer switch.
5. Root unit behavior: a selected root (whole-church) unit means whole-church audience for current structure-scope consumers — all authenticated ordinary users for ServiceEvent matching (including users with no small group), all active small groups for Bible Study resolution.
6. Unmapped units (no legacy mapping at or beneath the unit) resolve to no ordinary users and no generated legacy groups, unless the selection includes a root unit. This is not an error; staff-facing warnings remain the mitigation.
7. Stored audience rows whose unit later becomes inactive keep matching (SE-AS.4 Section 7 parity decision). Changing this is a deliberate future product decision, not a side effect of any CS-CORE slice.
8. Mapping edits can change structure-based ServiceEvent visibility and Bible Study resolution at request time (Section 3.3). The acknowledgement requirement on mapping edits stays until the mapping bridge itself is retired.

## 7. Milestone Map

Each milestone is separately approved, intentionally narrow, and never bundled with another.

- **CS-CORE.0A — Docs-only ADR / architecture plan.** This document. Complete.
- **CS-CORE.0B — Read-only dependency audit.** Performed as an AI architecture review of the current worktree (consumers, call sites, drift paths, retirement blockers); its findings are folded into Sections 3 and 12. No standing artifact beyond this plan is required unless a later milestone wants one.
- **CS-CORE.0B.1 — Read-only belonging drift audit command.** Complete. `audit_structure_belonging` (see Section 9). Reports, writes nothing.
- **CS-CORE.1A — Selector/service layer, no behavior change.** Complete. `accounts/structure_selectors.py` centralizes: get user's legacy small group, get user's legacy-derived structure unit(s) with ancestors, resolve units to legacy small groups, match user against a structure audience. Legacy-parity only; semantics frozen by tests. `ChurchStructureMembership` is not consulted by any runtime path in this slice.
- **CS-CORE.1B — ServiceEvent matching through the selector layer, parity only.** Complete. Mechanical refactor of ServiceEvent structure-audience matching onto the shared selector. SE-AS.4 already did the semantic migration; this slice changed no behavior.
- **CS-CORE.1C — Bible Study resolver re-home / parity migration.** Complete. `resolve_units_to_small_groups` lives in the selector layer with a compatibility wrapper from `studies.models`; Bible Study eligibility and meeting generation read through it. No behavior change.
- **CS-CORE.2A — Staff structure setup UI as the primary setup surface.** Unit lifecycle (create/rename/move/deactivate) with per-action impact preview of referencing audience rows, mappings, and memberships. Mapping review stays a separate diagnostics page. Single-active-root enforcement lands here at the latest.
- **CS-CORE.2B — Belonging migration, shadow-first and consumer-by-consumer.** Sub-slices: (2B.1) shadow mode — selectors compute legacy and membership answers, report divergence, runtime stays legacy; (2B.2) sync/drift hardening until the 0B.1 audit shows sustained near-zero drift; (2B.3) per-consumer source switch, one consumer per release, each with targeted tests and instant rollback (flip the source back).
- **CS-CORE.2C — Membership roster UI.** Per-unit member listing, transfers, end dates. Separate from structure setup by Section 5.
- **CS-CORE.2D — Optional structure-aware role/permission model.** Unit-scoped role scopes for leaders/progress access. Separate decision; not assumed by any other CS-CORE milestone.
- **CS-CORE.3 — Legacy retirement, last only.** Per-table, per-field plan (Section 12). Only after no runtime consumer reads the legacy source and history-bearing FKs are re-pointed or deliberately archived.

## 8. Pilot-Safe Scope

Safe before pilot:

- This docs-only plan (CS-CORE.0A).
- CS-CORE.0B.1 read-only drift audit command — it actively de-risks the pilot by finding members whose approved membership cannot reach a runtime group before they hit empty pages.
- CS-CORE.1A selector layer, only if its parity test suite is strong and fully green; it is behavior-inert but touches visibility-adjacent files, so it is the last thing allowed in before pilot.

Not safe before pilot (explicitly wait):

- Switching any visibility or matching to `ChurchStructureMembership` (any part of CS-CORE.2B.3).
- Changing reading/reflection/comment privacy semantics.
- Changing the Bible Study meeting ownership model (`BibleStudyMeeting.small_group`).
- Dropping or deprecating legacy fields/tables, or making `Profile.small_group` read-only.
- Structure setup UI and roster UI (staff-workflow risk during pilot).

Never, in any phase: a big-bang migration that switches multiple consumers, or bundles a source-of-truth switch with UI work, in one release.

## 9. First Implementation Slice After This Document

Completed first slice: **CS-CORE.0B.1 — `audit_structure_belonging` management command** (`accounts/management/commands/`, modeled on the audit-only `backfill_service_event_audience_scopes`).

- Read-only. It writes nothing — no membership, profile, group, unit, mapping, or audience row. Any future reconcile/apply behavior is a separate command and a separate approval with dry-run/apply discipline.
- Per-user classification, with summary counts and an optional verbose per-user mode:
  - in sync — active primary membership unit and `Profile.small_group.church_structure_unit` agree;
  - membership without group — active primary membership, but no `Profile.small_group`;
  - group without membership — `Profile.small_group` set, but no active primary membership;
  - mismatch — both present, units disagree;
  - unmapped group — `Profile.small_group` has no `church_structure_unit` mapping;
  - parent/fellowship-only membership — active primary membership whose unit maps to zero (or more than one) active legacy small groups, i.e. the approval-sync rule could not or did not sync.
- Acceptance: categories reconcile with the `/staff/structure/` indicator counts; fixtures cover every category; zero-write assertion.
- These numbers are the standing gate evidence for CS-CORE.2B: 2B.3 may not start while drift is non-trivial.

## 10. No-Go Rules

1. Do not drop or truncate legacy tables (`MinistryContext`, `District`, `SmallGroup`).
2. Do not delete `Profile.small_group`, stop writing it, or make it read-only in this phase.
3. Do not switch any visibility, matching, or eligibility to `ChurchStructureMembership` outside an approved CS-CORE.2B consumer slice with targeted tests.
4. Do not treat requested memberships as access grants, in any milestone.
5. Do not make mapping review/edit the main staff setup UI; it stays migration diagnostics.
6. Do not mix structure setup with membership roster management in one UI or milestone.
7. Do not pull Community Activities (or notifications, attendance, audience-filter expansion) into CS-CORE.
8. Do not change ServiceEvent or Bible Study visibility/eligibility semantics without targeted tests; in parity milestones (1A–1C), any behavior difference is a bug.
9. Do not change reading/reflection/comment privacy in selector/refactor milestones; that area moves only in its own later CS-CORE.2B slice.
10. Do not infer serving assignments, ministry roles, staff capabilities, or permissions from membership — ever.
11. Do not let structure setup, mapping, or roster actions cascade writes into audience rows, `TeamAssignment`, `ChurchRoleAssignment`, or other modules' data.
12. Do not auto-reconcile belonging drift inside request cycles; reconciliation is an explicit, separately approved command or staff action.

## 11. Test / Acceptance Gate Summary

Detailed test matrices belong to each implementation milestone; the binding categories are:

- **ServiceEvent visibility:** root row matches all authenticated users including no-group users; ministry-context/district/small-group rows match exactly their resolved groups with no sibling leakage; multi-unit and cross-branch unions; unmapped unit matches no ordinary user; stored inactive unit keeps matching; legacy-fallback events unchanged; draft/cancelled hidden; manager override intact; requested and active `ChurchStructureMembership` grant nothing (explicit non-granting tests); list and detail agree.
- **Bible Study:** CS-CORE.1C parity is closed by selector-layer and Bible Study tests: resolver group sets remain identical after the re-home (audience-row, legacy-scope, root, ministry-context, district, small-group, unmapped, inactive-mapped, duplicate/multi-unit cases); meeting generation targets the same groups; active/requested `ChurchStructureMembership` rows do not grant schedule eligibility or member meeting visibility; member visibility stays `Profile.small_group`-anchored until its own 2B slice; cancelled meetings still count as existing for generation.
- **Membership approval sync:** approval syncs `Profile.small_group` only when the approved active primary unit maps to exactly one active legacy `SmallGroup`; all other cases warn and leave the profile unchanged; reject/requested never sync.
- **Drift audit:** every Section 9 category produced by fixtures; zero writes.
- **Belonging switch (2B.3, per consumer):** mismatch fixtures (membership unit ≠ profile group) asserting which source wins before and after; full membership lifecycle matrix (requested/active/ended/rejected/cancelled, future start, past end) with only currently-active granting; no-membership users keep safe empty states.
- **Reading/comment privacy:** tested only in its own later milestone, with leak tests in both directions.

## 12. Retirement Preconditions (for CS-CORE.3, recorded now)

Retirement is per-table and per-field, and blocked until each precondition clears:

- `Profile.small_group`: all consumers switched in 2B.3; field becomes sync-target only, then read-only, then removable.
- `SmallGroup`: blocked by `BibleStudyMeeting.small_group` (CASCADE — deleting a group would delete meeting history), `ReflectionComment.small_group_at_post` (privacy snapshot), `ChurchRoleAssignment.small_group`, and `BibleStudySession`. Each needs a re-point or explicit archive decision first.
- `District` / `MinistryContext`: blocked by `ChurchRoleAssignment.district`, legacy scope fields on events/series/sessions, and the resolver's mapping paths.
- Legacy scope fields on `ServiceEvent` / `BibleStudySeries` / `BibleStudySession`: deprecation planning only after audience rows have proven stable in production (per SE-AS.6 planning).
- The mapping FKs and `/staff/structure/mappings/` retire together, last of all, when nothing resolves through them.

No dates are scheduled for CS-CORE.3 by this document.

## 13. Open Decisions (to resolve in later milestones, not blockers for 0B.1)

- Whether signup-requestable units must have an active legacy mapping until 2B completes, or whether approving an unmapped/fellowship unit gets explicit staff messaging about runtime consequences (most pilot-relevant decision; the 0B.1 audit quantifies it).
- When to enforce a single active root in the database (CS-CORE.2A at the latest).
- Whether `ProfileAdmin` direct `small_group` edits stay open once 2B.2 sync hardening lands.
- Union-of-active-memberships vs. primary-only matching at 2B.3 switch time (recommendation: union for audience matching, primary for "my group" display).
- Whether CS-CORE.2D (unit-scoped roles) joins the CS-CORE charter or stays a separate track.
- Whether stored-inactive-unit matching parity is reaffirmed permanently or revisited after 2B.

## 14. Non-Goals

CS-CORE.0A does not include or authorize:

- any code, template, form, view, model, migration, admin, static, or test change;
- the selector layer, audit command, setup UI, roster UI, or any 2B work;
- Community Activities, notifications, attendance, announcements, checklist, availability, swaps, or scheduling engine work;
- changes to My Serving, TeamAssignment, Required Ministry Teams, Rotation Anchor Team, or Host / Language Label semantics;
- correcting the stale mapping-field `help_text` in `accounts/models.py` (deferred to a code-touching milestone to avoid migration churn).
