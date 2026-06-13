# Church Structure Core Migration Plan (CS-CORE)

## 1. Purpose and Status

CS-CORE.0A is the docs-only architecture decision record (ADR) and staged migration plan for promoting Church Structure from a transitional foundation to the core model of the CMS.

Status: CS-CORE.0A is complete with this document. CS-CORE.0B.1, CS-CORE.1A, CS-CORE.1B, CS-CORE.1C, CS-CORE.2B-A, CS-CORE.2C-A, and CS-CORE.2C-B are complete as narrow, separately approved slices. CS-CORE.2B-A is the first consumer source switch: ServiceEvent structure-audience matching (events with `ServiceEventAudienceScope` rows) now uses the active primary `ChurchStructureMembership` as its runtime belonging source; ServiceEvents with zero audience rows still use legacy fallback and `Profile.small_group`. CS-CORE.2C-B is the second consumer source switch: Bible Study v2 `BibleStudyMeeting` ordinary-member visibility and the `/studies/` / Today meeting pre-filter now use the user's single active primary `ChurchStructureMembership`, matched to the meeting legacy `SmallGroup`'s mapped small-group `ChurchStructureUnit` or a descendant. `Profile.small_group` alone no longer grants v2 `BibleStudyMeeting` visibility, and root/ministry-context/district/fellowship/custom mappings on a meeting's legacy small group fail closed for ordinary users rather than becoming whole-church audiences. This is still not full legacy retirement: Bible Study meeting generation and schedule audience resolution continue to target legacy `SmallGroup` rows through existing mappings; legacy `BibleStudySession`, reading progress, reflection/comment privacy, group progress permissions, TeamAssignment / My Serving, roles, ServiceEvent behavior, and legacy `Profile.small_group`, `SmallGroup`, `District`, and `MinistryContext` remain unchanged. The `audit_bible_study_membership_readiness` command remains read-only and now compares old legacy Bible Study meeting visibility against current membership-core v2 meeting visibility. Later CS-CORE milestones still require their own separate approval.

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
- The hardest remaining work is not audience scope (both structure-scope consumers already run on `ChurchStructureUnit` rows with legacy fallback). It is the **belonging migration**. Two consumer switches are done: ServiceEvent structure-audience matching consults the active primary `ChurchStructureMembership` (CS-CORE.2B-A), and Bible Study v2 `BibleStudyMeeting` ordinary-member visibility consults the active primary `ChurchStructureMembership` (CS-CORE.2C-B). Other ordinary-user matching decisions still terminate in `Profile.small_group`.

## 3. Current State (verified against code at CS-CORE.0A time)

### 3.1 Already structure-driven

- ServiceEvent ordinary-user visibility (SE-AS.4/SE-AS.5, CS-CORE.2B-A): events with `ServiceEventAudienceScope` rows use those rows, matched against the user's active primary `ChurchStructureMembership` (root rows match all authenticated users; `Profile.small_group` alone grants nothing here); events with zero rows fall back to legacy `scope_type` / `district` / `small_group` driven by `Profile.small_group` (`events/models.py`, `ServiceEvent.can_be_seen_by`).
- Bible Study Schedule eligibility and meeting generation (BS-AS.1/BS-AS.2, CS-CORE.1C): schedules with `BibleStudySeriesAudienceScope` rows resolve selected units to eligible active legacy `SmallGroup` rows through the shared selector-layer resolver (`accounts/structure_selectors.py`, with the `studies.models.resolve_units_to_small_groups` compatibility wrapper); schedules with zero rows use legacy scope fields. CS-CORE.2C-B does not change this generation/resolution layer.
- Bible Study v2 meeting visibility (CS-CORE.2C-B): `BibleStudyMeeting.can_be_seen_by` and the `/studies/` / Today v2 meeting pre-filter use the user's single active primary `ChurchStructureMembership`. The meeting's legacy `SmallGroup` must map to a `ChurchStructureUnit` of type `small_group`; the membership unit must be that unit or a descendant. `Profile.small_group` alone grants nothing, requested/rejected/cancelled/ended/future/expired memberships grant nothing, multiple active primary memberships fail closed, and wrong-type mappings fail closed rather than whole-church matching.
- ServiceEvent and Bible Study now share the selector-layer unit-to-legacy-group resolver. Their staff audience selectors reuse the shared hierarchical picker pattern.
- Signup/Profile capture `ChurchStructureMembership(status=requested)` rows; staff approval activates membership and conditionally syncs `Profile.small_group` (CS-H.6 through CS-H.9).
- Read-only diagnostics exist: `/staff/structure/` map with drift indicators, `/staff/structure/mappings/` review/edit with conflict overlays and impact acknowledgement, plus `seed_church_structure_units`, `backfill_church_structure_memberships`, and the audit-only `backfill_service_event_audience_scopes` commands.

### 3.2 Still legacy-driven

- Ordinary runtime belonging is `Profile.small_group` everywhere except ServiceEvent structure-audience rows (switched in CS-CORE.2B-A) and Bible Study v2 `BibleStudyMeeting` ordinary-member visibility (switched in CS-CORE.2C-B): legacy-fallback ServiceEvents, legacy `BibleStudySession` visibility, reflection-wall group privacy (`small_group_at_post`), and reading group progress still read `Profile.small_group`.
- `ChurchStructureMembership` is a runtime visibility source for exactly two consumers: ServiceEvent structure-audience matching (CS-CORE.2B-A) and Bible Study v2 `BibleStudyMeeting` ordinary-member visibility (CS-CORE.2C-B). For everything else it remains signup/request/approval, diagnostics, and backfill data only.
- Permissions (`ChurchRoleAssignment`) scope only by legacy `District` / `SmallGroup` / global; no unit-scoped role exists.
- `BibleStudyMeeting.small_group` and `ReflectionComment.small_group_at_post` bind meeting history and comment privacy snapshots to legacy `SmallGroup` rows.

### 3.3 The mapping bridge is no longer inert

The nullable `church_structure_unit` mapping FKs on `MinistryContext`, `District`, and `SmallGroup` were added as a passive bridge (CS-H.3B). Since BS-AS.1 and SE-AS.4, structure-based audience scopes resolve through these fields at request time. Therefore:

- Editing a legacy-to-unit mapping can change which current groups match an existing structure-based Bible Study Schedule and which groups Bible Study meeting generation targets. (Since CS-CORE.2B-A, ServiceEvent structure-audience matching follows the membership, not the mapping, so mapping edits no longer change ServiceEvent audience results; legacy-fallback ServiceEvents never used the mapping.)
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

1. `Profile.small_group` remains the ordinary-member runtime belonging source for current consumers except ServiceEvent structure-audience matching (switched by CS-CORE.2B-A) and Bible Study v2 `BibleStudyMeeting` ordinary-member visibility (switched by CS-CORE.2C-B).
2. `ChurchStructureMembership` must not grant or deny any visibility, audience match, eligibility, or access until the explicit CS-CORE.2B migration for that specific consumer, with targeted tests. The switched consumers so far are ServiceEvent structure-audience matching (CS-CORE.2B-A) and Bible Study v2 meeting visibility (CS-CORE.2C-B); both match only via the single active primary membership, and multiple active primary memberships fail closed.
3. Requested memberships never grant anything, in any milestone, ever.
4. Active memberships are diagnostic/shadow-comparison data only until the explicit per-consumer switch (done for ServiceEvent structure-audience rows; pending everywhere else).
5. Root unit behavior: a selected root (whole-church) unit means whole-church audience for current structure-scope consumers — all authenticated ordinary users for ServiceEvent matching (including users with no small group), all active small groups for Bible Study resolution.
6. Unmapped non-root units (no legacy mapping at or beneath the unit) still resolve to no legacy `SmallGroup` rows for legacy-resolver consumers such as Bible Study meeting generation, unless the selection includes a root unit. For CS-CORE.2B-A ServiceEvent structure-audience matching, selected unmapped, custom, or fellowship units can match ordinary users by active primary `ChurchStructureMembership` when the membership unit is the selected unit or a descendant. This is not an error; staff-facing warnings remain the mitigation for consumers still depending on legacy group resolution.
7. Stored audience rows whose unit later becomes inactive keep matching (SE-AS.4 Section 7 parity decision). Changing this is a deliberate future product decision, not a side effect of any CS-CORE slice.
8. Mapping edits can change structure-based Bible Study resolution at request time (Section 3.3; since CS-CORE.2B-A they no longer change ServiceEvent audience matching). The acknowledgement requirement on mapping edits stays until the mapping bridge itself is retired.

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
- **CS-CORE.2B-A — Membership-core runtime source for ServiceEvent structure audience.** Complete. An accelerated but bounded 2B bundle, unlocked by a real-data audit run (2026-06-12) showing zero risky drift: membership-core selector helpers (`get_user_primary_membership_unit`, `get_user_membership_structure_units`, `user_matches_membership_structure_audience`) plus a preserved `user_matches_legacy_structure_audience` comparison helper; `user_matches_structure_audience` became the canonical membership-core matcher; the only consumer switched is ServiceEvent structure-audience rows (`ServiceEvent._audience_scope_allows`). Events with zero audience rows keep legacy fallback via `Profile.small_group`. `audit_structure_belonging` gained a read-only `--fail-on-drift` guard. Rollback: point `user_matches_structure_audience` back at the legacy helper.
- **CS-CORE.2C-A — Bible Study membership-core readiness / shadow audit.** Complete. This was the read-only shadow layer before the source switch. `studies/structure_readiness.py` added `get_small_group_structure_unit`, old-vs-membership-core comparison helpers, `same_visible` / `same_hidden` / `would_gain` / `would_lose` classifications, and reason codes. The `audit_bible_study_membership_readiness` command (no `--apply`, writes nothing) reports those pair classifications over upcoming member-visible meetings (`--include-past` widens the window) plus readiness categories (`meeting_unmapped_small_group`, `user_group_without_active_primary_membership`, `user_active_primary_without_profile_group`, `user_profile_membership_mismatch`, `user_profile_group_unmapped`, `multiple_active_primary_memberships`) with `--verbose`/`--limit` detail and a read-only `--fail-on-drift` guard. After CS-CORE.2C-B, the audit remains read-only but now compares the preserved old `Profile.small_group` rule against current membership-core v2 meeting visibility.
- **CS-CORE.2C-B — Bible Study v2 meeting visibility source switch.** Complete. `BibleStudyMeeting.can_be_seen_by` and `get_v2_landing_context` now use `studies/visibility.py`: staff/manager overrides and existing publish/active gates stay the same, then ordinary-member matching uses the user's single active primary `ChurchStructureMembership` against the meeting legacy `SmallGroup`'s mapped `ChurchStructureUnit`. The mapped unit must be type `small_group`; unmapped groups and root/ministry-context/district/fellowship/custom mappings fail closed for ordinary members. Membership on a descendant of the mapped small-group unit can see the meeting. `Profile.small_group` alone no longer grants v2 meeting visibility. The readiness audit is still read-only, but its legacy comparator is now a standalone old-rule comparator rather than delegating to current runtime. Bible Study meeting generation, schedule audience resolution, legacy `BibleStudySession`, ServiceEvent behavior, reading/progress/privacy, permissions, My Serving, mapping edits, legacy fields/tables, schema, and CSS are unchanged.
- **CS-CORE.2C — Membership roster UI.** Per-unit member listing, transfers, end dates. Separate from structure setup by Section 5.
- **CS-CORE.2D — Optional structure-aware role/permission model.** Unit-scoped role scopes for leaders/progress access. Separate decision; not assumed by any other CS-CORE milestone.
- **CS-CORE.3 — Legacy retirement, last only.** Per-table, per-field plan (Section 12). Only after no runtime consumer reads the legacy source and history-bearing FKs are re-pointed or deliberately archived. Legacy small group retirement is consumer-by-consumer.
- **CS-CORE.3C — Bible Study V1/V2 boundary decision.** Complete as a docs-only decision record (`docs/LEGACY_BIBLE_STUDY_SESSION_RETIREMENT_DECISION.md`): Bible Study V2 is the active product path; legacy V1 `BibleStudySession` is a retirement/archive candidate; do not migrate V1 `BibleStudySession` visibility to membership-core; V2 still has a legacy `SmallGroup` generation bridge. V1 data is not deleted, V1 direct routes/admin are unchanged, and hiding/redirect/gating of V1 entry points requires a separately approved runtime slice.
- **CS-CORE.3D — Freeze legacy BibleStudySession app creation route.** Complete. `GET` and `POST` to `/studies/new/` now redirect to `/studies/` with retirement messaging and do not render/process the V1 creation form or create `BibleStudySession` / `BibleStudyGuide` rows. Existing V1 direct detail/edit/delete/worship/admin paths, `BibleStudySessionForm`, `BibleStudySessionAdmin`, and `BibleStudySession.can_be_seen_by()` remain unchanged.
- **CS-CORE.3E — Legacy BibleStudySession archive mutation policy audit.** Complete as docs-only. The audit records that direct V1 edit/delete/worship app routes still mutate existing V1 records or V1 worship rows, that promoted normal/staff UI surfaces do not link to those mutation routes, and that the V1 detail page still exposes management controls to Bible Study managers. Recommended future runtime slice: keep direct readable V1 detail and Django Admin emergency maintenance, but freeze app-level V1 edit/delete/worship mutations with archive messaging and no V1 data deletion.
- **CS-CORE.3F — Freeze legacy BibleStudySession app mutation routes.** Complete. V1 edit/delete/worship app routes now redirect with archive messaging and no longer mutate `BibleStudySession`, `BibleStudyGuide`, or V1 worship rows; direct V1 detail remains readable when legacy visibility allows it, existing V1 worship rows still display, and Django Admin remains the emergency archival maintenance path.
- **CS-CORE.4A — Reading, Group Progress, and Reflection Privacy Migration Plan.** Complete as docs-only. Plan-only, privacy-first migration plan for the remaining high-risk `Profile.small_group` / `SmallGroup` / `ReflectionComment.small_group_at_post` consumers: reading group progress (roster, default group, and the role-scope-coupled `get_accessible_progress_groups` permission) and reflection/comment privacy (the "My Group" tab, `ReflectionComment.can_be_seen_by`, `get_visible_reflection_filter`, `passage_wall`, create/edit group binding, and reply inheritance). It records the current code audit, privacy invariants, target options (A–E, with full migration explicitly not first), a staged path (4B read-only diagnostics → 4C privacy tests → optional 4D additive structure snapshot → 4E group-progress shadow → 4F+ one switch at a time), a future test matrix, a rollback strategy, and binding no-go rules. It changed no runtime/code/template/form/view/model/migration/admin/URL/static/test behavior, did not remove or hide `Profile.small_group`, did not change `small_group_at_post` semantics, and did not change reflection visibility or group-progress permissions. After CS-CORE.4A these consumers remain legacy-driven. See `docs/READING_PROGRESS_REFLECTION_PRIVACY_MIGRATION_PLAN.md`.

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
- These numbers are the standing gate evidence for CS-CORE.2B: 2B.3 may not start while drift is non-trivial. A real-data run on 2026-06-12 (in_sync 19, all risky categories 0, no_group_no_membership 4) gated CS-CORE.2B-A.
- CS-CORE.2B-A added an optional read-only `--fail-on-drift` flag: the command exits with an error when any risky category (`membership_without_group`, `group_without_membership`, `mismatch`, `unmapped_group`, `parent_or_fellowship_only_membership`, `multiple_active_primary_memberships`) is nonzero; `no_group_no_membership` alone never fails. Default behavior is unchanged, and the command still writes nothing.

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

- **ServiceEvent visibility (membership-core since CS-CORE.2B-A):** root row matches all authenticated users including no-membership/no-group users; ministry-context/district/small-group rows match by active primary membership unit (own unit or descendant) with no sibling leakage; multi-unit and cross-branch unions; selected unmapped/custom/fellowship units can match by active primary membership even when they resolve to no legacy `SmallGroup` rows; stored inactive unit keeps matching; `Profile.small_group` alone grants no audience-row visibility; requested/future/expired/ended/rejected/cancelled memberships grant nothing; multiple active primary memberships fail closed; legacy-fallback events unchanged and still `Profile.small_group`-driven; draft/cancelled hidden; manager override intact; list and detail agree.
- **Bible Study:** CS-CORE.1C parity is closed by selector-layer and Bible Study tests: resolver group sets remain identical after the re-home (audience-row, legacy-scope, root, ministry-context, district, small-group, unmapped, inactive-mapped, duplicate/multi-unit cases); meeting generation targets the same legacy `SmallGroup` rows; cancelled meetings still count as existing for generation. Since CS-CORE.2C-B, v2 `BibleStudyMeeting` ordinary-member visibility uses active primary `ChurchStructureMembership`; `Profile.small_group` alone no longer grants v2 meeting visibility. Legacy `BibleStudySession` remains unchanged and legacy-driven.
- **Membership approval sync:** approval syncs `Profile.small_group` only when the approved active primary unit maps to exactly one active legacy `SmallGroup`; all other cases warn and leave the profile unchanged; reject/requested never sync.
- **Drift audit:** every Section 9 category produced by fixtures; zero writes.
- **Belonging switch (2B.3, per consumer):** mismatch fixtures (membership unit ≠ profile group) asserting which source wins before and after; full membership lifecycle matrix (requested/active/ended/rejected/cancelled, future start, past end) with only currently-active granting; no-membership users keep safe empty states.
- **Reading/comment privacy:** tested only in its own later milestone, with leak tests in both directions.

## 12. Retirement Preconditions (for CS-CORE.3, recorded now)

Retirement is per-table and per-field, and blocked until each precondition clears:

- `Profile.small_group`: all consumers switched in 2B.3; field becomes sync-target only, then read-only, then removable.
- `SmallGroup`: blocked by `BibleStudyMeeting.small_group` (CASCADE — deleting a group would delete meeting history), `ReflectionComment.small_group_at_post` (privacy snapshot), `ChurchRoleAssignment.small_group`, and `BibleStudySession`. Each needs a re-point or explicit archive decision first. For `BibleStudySession`, CS-CORE.3C records the decision: legacy V1 `BibleStudySession` is a retirement/archive candidate, and its visibility is not migrated to membership-core (`docs/LEGACY_BIBLE_STUDY_SESSION_RETIREMENT_DECISION.md`).
- `District` / `MinistryContext`: blocked by `ChurchRoleAssignment.district`, legacy scope fields on events/series/sessions, and the resolver's mapping paths.
- Legacy scope fields on `ServiceEvent` / `BibleStudySeries` / `BibleStudySession`: deprecation planning only after audience rows have proven stable in production (per SE-AS.6 planning).
- The mapping FKs and `/staff/structure/mappings/` retire together, last of all, when nothing resolves through them.

No dates are scheduled for CS-CORE.3 by this document.

## 13. Open Decisions (to resolve in later milestones, not blockers for 0B.1)

- Whether signup-requestable units must have an active legacy mapping until 2B completes, or whether approving an unmapped/fellowship unit gets explicit staff messaging about runtime consequences (most pilot-relevant decision; the 0B.1 audit quantifies it).
- When to enforce a single active root in the database (CS-CORE.2A at the latest).
- Whether `ProfileAdmin` direct `small_group` edits stay open once 2B.2 sync hardening lands.
- Union-of-active-memberships vs. primary-only matching at 2B.3 switch time (recommendation was union for audience matching, primary for "my group" display; CS-CORE.2B-A shipped ServiceEvent matching as primary-only with fail-closed ambiguity — revisiting union matching is a separate future decision).
- Whether CS-CORE.2D (unit-scoped roles) joins the CS-CORE charter or stays a separate track.
- Whether stored-inactive-unit matching parity is reaffirmed permanently or revisited after 2B.

## 14. Non-Goals

CS-CORE.0A does not include or authorize:

- any code, template, form, view, model, migration, admin, static, or test change;
- the selector layer, audit command, setup UI, roster UI, or any 2B work;
- Community Activities, notifications, attendance, announcements, checklist, availability, swaps, or scheduling engine work;
- changes to My Serving, TeamAssignment, Required Ministry Teams, Rotation Anchor Team, or Host / Language Label semantics;
- correcting the stale mapping-field `help_text` in `accounts/models.py` (deferred to a code-touching milestone to avoid migration churn).
