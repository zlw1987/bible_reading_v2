# Reading / Reflection / Progress Structure-Runtime Migration Plan (READING-STRUCT.1)

## 0. Purpose and status

This is a **focused, current** companion to the broader
`docs/READING_PROGRESS_REFLECTION_PRIVACY_MIGRATION_PLAN.md` (the CS-CORE.4A
design plan) and the cross-module
`docs/CHURCH_STRUCTURE_CORE_MIGRATION_PLAN.md`. Those remain the authoritative
design / invariants / rollback documents. This doc tracks only the **remaining
runtime legacy small-group dependencies** in Reading / Reflection / Progress and
the audit that measures readiness to retire them.

Status: **READING-STRUCT.1A (audit) + 1B (snapshot backfill) + 1C (reflection
visibility row-first, verified) implemented.** Code/tests/docs only; no model,
schema, migration, or runtime-behavior change. The reflection read/write
visibility path and the group-progress roster/default path are already
membership-core (see below); what remains is retiring the last
`Profile.small_group` reads and the legacy mirror data once real-data evidence is
clean.

This document's code changes **no runtime behavior**. It adds a read-only audit
(`reading.structure_runtime_readiness` + the
`audit_reading_structure_runtime_readiness` command) and a dry-run/apply data
backfill (`backfill_reflection_structure_snapshots`) that only sets the additive
`structure_unit_at_post` snapshot column. No runtime source is switched and no
production command has been run.

> **READING-STRUCT.1C finding (2026-06-16).** Group-shared reflection visibility
> was already made structure-snapshot row-first — in fact snapshot-**only**, with
> the legacy `Profile.small_group` / `small_group_at_post` fallback **removed** —
> by CS-CORE.4G.2 (commit `238481f`), which predates this plan. So the 1C goal is
> already in effect and *stricter* than the original 1C draft (which had proposed
> keeping a legacy fallback for no-snapshot rows). Per an explicit decision this
> slice **does not re-add** that legacy fallback (doing so would reverse the
> 4G.2 privacy tightening); it only verifies and documents the current behavior.
> See Section 5.5.

## 1. Current legacy consumers in Reading / Reflection / Progress

Verified against the worktree on 2026-06-16:

1. **Group-progress default group fallback** —
   `reading.views.my_group_progress` still reads `Profile.small_group` as the
   *last-resort* default selected group (after a permission-fenced membership-core
   default candidate, CS-CORE.4F.2). It only picks a default among the already
   legacy-accessible groups; it never grants access. This is the main remaining
   ordinary-runtime `Profile.small_group` read.
2. **`reading.views.get_user_small_group(user)`** — thin
   `profile.small_group` reader retained for legacy/default/option-gating use.
3. **Legacy mirror writes** — group reflections still stamp
   `ReflectionComment.small_group_at_post` as an optional compatibility mirror
   (only when exactly one active legacy `SmallGroup` maps to the author's
   structure unit). It is no longer a visibility source.
4. **Legacy comparator / shadow code** — `reading.group_progress_shadow`,
   `reading.reflection_privacy_shadow`, and the two existing audit commands read
   `Profile.small_group` / `small_group_at_post` *deliberately*, to compare legacy
   vs membership-core answers. Diagnostic only.

District (`accounts.District`) has **no** reading/reflection/progress runtime
read; it appears only via `accounts.structure_selectors.resolve_units_to_small_groups`
(audience resolution shared with other modules) and progress role-scope
resolution in `accounts.permissions`, not in reading runtime.

## 2. What is already structure-ready

- **Group reflection visibility (read + write) — structure-native (CS-CORE.4G.2).**
  `comments.reflection_visibility` gates group-shared reflections on
  `structure_unit_at_post` plus the viewer's single active primary
  `ChurchStructureMembership` (snapshot unit or a descendant), via
  `ReflectionComment.can_be_seen_by`,
  `reading.views.get_visible_reflection_filter`, and the `passage_wall` group
  tab. `Profile.small_group` / `small_group_at_post` grant **no** ordinary group
  visibility. The write path stamps `structure_unit_at_post` from the author's
  membership-core write context.
- **Group-progress visible roster — membership-core (CS-CORE.4F.1).**
  `get_membership_core_progress_roster_users` drives `member_rows`.
- **Group-progress default selected group — permission-fenced membership-core
  (CS-CORE.4F.2)**, falling back to legacy `Profile.small_group` only as the last
  resort.
- **Group-progress accessible list / own group — membership-core / role-scope
  structure-aware (CS-CORE.2D-B)** in `accounts.permissions.get_accessible_progress_groups`;
  ordinary membership grants only the single mapped own group.

## 3. What remains before legacy retirement

- Replace the `my_group_progress` last-resort `Profile.small_group` default with
  a membership-core (or "no default") behavior, once the audit shows no users
  depend solely on the legacy default.
- Backfill `structure_unit_at_post` for legacy group reflections that predate
  CS-CORE.4D/4G.2 so historical group posts are not silently invisible under the
  live structure-native gate.
- Eventually drop the `small_group_at_post` mirror writes and `get_user_small_group`
  once no consumer remains (coordinate with the cross-module
  `Profile.small_group` retirement in CHURCH_STRUCTURE_CORE Section 12).

None of these are done in this slice.

## 4. What the audit measures (READING-STRUCT.1A)

`reading.structure_runtime_readiness.run_audit()` (wrapped by
`python manage.py audit_reading_structure_runtime_readiness`) is a read-only
**inventory + blocker verdict**, complementary to the two existing drift
comparators (it counts absolute resolvability rather than per-row legacy-vs-new
divergence). It reports:

**Group reflection structure-snapshot inventory** (group-visible, non-hidden,
non-deleted reflections):

- `group_visible_reflections`
- `reflections_with_legacy_small_group` (`small_group_at_post` set)
- `reflections_with_structure_snapshot` (`structure_unit_at_post` set)
- `reflections_snapshot_resolvable` (snapshot = active `UNIT_SMALL_GROUP`)
- `reflections_snapshot_missing` / `..._inactive_unit` / `..._wrong_unit_type`
- `reflections_legacy_only_no_valid_snapshot` — legacy group set but no valid
  snapshot, i.e. **already invisible** under the live 4G.2 gate (headline blocker)

**Active legacy progress-group resolvability inventory:**

- `progress_groups_total`
- `progress_groups_resolvable` (`church_structure_unit` = active `UNIT_SMALL_GROUP`)
- `progress_groups_missing_mapping` / `..._inactive_unit` / `..._wrong_unit_type`

**User membership inventory:**

- `users_total`, `users_with_profile_small_group`
- `users_with_single_active_primary_membership`
- `users_with_multiple_active_primary_membership`
- `users_with_no_active_primary_membership`
- `users_profile_group_without_single_membership` (still depend on the legacy
  default fallback)
- `users_single_membership_without_profile_group`

**Blockers** (nonzero blocks the next switch / legacy retirement; `--fail-on-blockers`
exits nonzero, still read-only): `reflections_legacy_only_no_valid_snapshot`,
the three `progress_groups_*` unresolved counters,
`users_with_multiple_active_primary_membership`, and
`users_profile_group_without_single_membership`.

The command writes nothing, has no `--apply`, never switches a runtime source,
and never prints reflection body text. `--verbose` prints capped representative
rows (ids / labels only) for the unresolved and blocker categories.

## 5. Snapshot backfill (READING-STRUCT.1B — implemented)

`python manage.py backfill_reflection_structure_snapshots` (logic in
`run_backfill`, in the command module) backfills the additive
`ReflectionComment.structure_unit_at_post` snapshot for group-visible,
non-hidden, non-deleted reflections that are missing it, driving the
`reflections_legacy_only_no_valid_snapshot` blocker toward zero.

**Classification (per reflection):**

- existing `structure_unit_at_post` set → `skipped_existing_snapshot` (never
  overwritten);
- legacy `small_group_at_post` is null → `missing_legacy_group` (issue);
- legacy group's `church_structure_unit` is null → `missing_mapping` (issue);
- mapped unit inactive → `inactive_unit` (issue);
- mapped unit not `UNIT_SMALL_GROUP` → `wrong_unit_type` (issue);
- otherwise (active small-group unit) → `would_backfill` (dry-run) /
  `backfilled` (`--apply`).

The resolvability check reuses `reading.structure_runtime_readiness`’s
`_unit_resolution_reason`, so it stays in lockstep with both the 1A audit and the
live `comments.reflection_visibility` read gate.

**Counters:** `reflections_checked`, `skipped_existing_snapshot`,
`would_backfill`, `backfilled`, `missing_legacy_group`, `missing_mapping`,
`inactive_unit`, `wrong_unit_type`, `validation_error`, `legacy_fields_mutated`
(always 0), plus a printed `runtime_switched: false`.

**Contract:**

- **Dry-run by default;** `--apply` is required to write. Without `--apply` the
  command is strictly read-only.
- It only ever sets a currently-null `structure_unit_at_post`. It never
  overwrites an existing snapshot, never mutates `small_group_at_post` /
  `Profile.small_group` or any other legacy field (`legacy_fields_mutated` stays
  0), and never changes `visibility` / `is_hidden` / `is_deleted` or any runtime
  privacy behavior.
- Idempotent: a second `--apply` finds the backfilled rows already
  snapshot-backed (`skipped_existing_snapshot`) and writes 0 rows.
- Flags: `--apply`, `--limit N`, `--reflection-id ID`, `--verbose`,
  `--detail-limit N`, `--fail-on-issues` (exits nonzero when any unresolved issue
  bucket — `missing_legacy_group` / `missing_mapping` / `inactive_unit` /
  `wrong_unit_type` / `validation_error` — is nonzero; `would_backfill` is **not**
  an issue). `--verbose` prints capped id/label-only rows and never prints
  reflection body text.
- **No production command has been run.** The dev-DB dry-run reports the same 6
  backfillable rows the 1A audit flagged (plus 2 `missing_legacy_group` rows that
  need manual repair, not backfill). The runtime read/write paths are unchanged;
  this only prepares data for the later structure-native runtime switch.

## 5.5 Reflection visibility row-first (READING-STRUCT.1C — verified, no change)

**Outcome: already implemented by CS-CORE.4G.2; this slice makes no runtime
change and deliberately does not re-add a legacy fallback.**

Group-shared `ReflectionComment` read visibility is **structure-snapshot
row-first** — in fact snapshot-**only**:

- When a group post has a valid `structure_unit_at_post` (active
  `UNIT_SMALL_GROUP`), that snapshot unit is the sole audience source: a viewer
  sees it only with exactly one active primary `ChurchStructureMembership` in
  that unit **or a descendant**. `Profile.small_group` / `small_group_at_post`
  are not consulted. Fail-closed on no active primary membership, multiple active
  primary memberships, or an inactive/wrong-type snapshot.
- When a group post has **no** valid snapshot, it currently fails closed (visible
  only to author/staff). CS-CORE.4G.2 **removed** the old legacy
  `Profile.small_group` fallback here; this slice **keeps it removed** by explicit
  decision (re-adding it would reverse the 4G.2 privacy tightening). The
  no-snapshot rows the 1A audit flags
  (`reflections_legacy_only_no_valid_snapshot`) become visible again only once the
  1B backfill is run with `--apply` on real data — not via a legacy fallback.
- Private / church / hidden / deleted / author / staff behavior is unchanged.

This applies uniformly to detail access (`ReflectionComment.can_be_seen_by`), the
list/feed filter (`reading.views.get_visible_reflection_filter`, used by the
passage reader), and the `passage_wall` group tab — all routed through
`comments.reflection_visibility` (`user_matches_group_reflection_snapshot`
per-row gate and `get_visible_group_reflection_snapshot_unit_ids` queryset
mirror, kept in lockstep). No new helper was added (the canonical per-row gate
already exists).

**Verification (no code change in this slice):** the row-first / no-fallback
behavior is locked by existing tests in `reading.tests.ReflectionPrivacyInvariantTests`,
including `test_structure_unit_snapshot_drives_group_visibility` (snapshot wins
over a mismatched legacy group; list + detail agree),
`test_matching_legacy_group_without_structure_snapshot_is_not_visible` (no-snapshot
fail-closed, **no** legacy fallback),
`test_profile_small_group_alone_does_not_grant_group_visibility`,
`test_membership_descendant_of_snapshot_unit_can_see_post`,
`test_no_active_primary_membership_fails_closed_for_group_visibility`,
`test_multiple_active_primary_memberships_fail_closed`, and
`test_filter_and_group_tab_agree_with_detail_for_group_privacy`; plus the
public/private/hidden regression cases in `ReflectionWallVisibilityRegressionTests`.

**Group progress runtime was not switched in this slice.**

## 6. Next proposed slice

**READING-STRUCT.1D (proposed):** switch the `my_group_progress` last-resort
default to membership-core (or no default) and remove the
`Profile.small_group` default read, gated on a clean
`audit_reading_structure_runtime_readiness --fail-on-blockers` (after the 1B
backfill `--apply` is run and verified on real data) and the existing
`audit_group_progress_shadow --fail-on-drift`.

Each is a separate, individually-gated slice; the 1A audit, 1B backfill, and 1C
verification slices perform **no** runtime switch.
