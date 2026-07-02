# Reading / Reflection / Progress Structure-Runtime Migration Plan (READING-STRUCT.1)

> **Historical completion record:** this migration is no longer pending.
> Current Reading group progress and Reflection group read/write paths use
> structure snapshots and active primary `ChurchStructureMembership`.
> `Profile.small_group`, `ReflectionComment.small_group_at_post`, and the legacy
> `SmallGroup` table are removed, along with their retired backfill/shadow
> tooling. Statements below about remaining legacy reads, mirrors, commands, or
> production apply work describe the rollout stage at which they were written.

## 0. Purpose and status

This is a **focused historical** companion to the broader
`docs/READING_PROGRESS_REFLECTION_PRIVACY_MIGRATION_PLAN.md` (the CS-CORE.4A
design plan) and the cross-module
`docs/CHURCH_STRUCTURE_CORE_MIGRATION_PLAN.md`. Those remain historical
design / invariants / rollback records. This doc tracked the **then-remaining
runtime legacy small-group dependencies** in Reading / Reflection / Progress and
the audit that measured readiness to retire them.

Status: **READING-STRUCT.1A (audit) + 1B (snapshot backfill) + 1C (reflection
visibility row-first, verified) + 1D (group progress membership-core default) +
1E (legacy small-group helper cleanup) + 1F (local real-data backfill apply
recorded) implemented.** 1A–1C are code/tests/docs only with no runtime change;
1D made a small runtime change (removed the last legacy `Profile.small_group`
read in the group-progress default-group path); 1E removed the now-dead
`reading.views.get_user_small_group` helper and corrected stale wording; 1F is
docs-only and records the successful local real-data `--apply` run of the 1B
backfill (see Section 5.8). **Local real-data Reading reflection blockers are
now clear** (`reflections_legacy_only_no_valid_snapshot: 0`); two no-source
reflections remain intentionally unresolved / fail-closed. **Production apply
status is not claimed and should only be claimed if separately confirmed.** The reflection read/write visibility path and the group-progress
roster/default path are now fully membership-core (see below); **no Reading
runtime path reads `Profile.small_group`.** What remains is retiring the legacy
mirror data and the `SmallGroup` storage bridge once real-data evidence is clean.

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
   `reading.views.my_group_progress` read `Profile.small_group` as the
   *last-resort* default selected group. **Removed in READING-STRUCT.1D** — the
   default is now membership-core candidate → first accessible group → no-group
   state. No `Profile.small_group` read remains in the group-progress runtime.
2. ~~**`reading.views.get_user_small_group(user)`** — thin `profile.small_group`
   reader.~~ **Removed in READING-STRUCT.1E** as dead code (its last callers were
   dropped by CS-CORE.4G.2 and READING-STRUCT.1D).
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
  (CS-CORE.4F.2 + READING-STRUCT.1D).** The legacy `Profile.small_group`
  last-resort default fallback was **removed** in 1D; the default is now the
  membership-core candidate, then the first accessible group, then the safe
  no-group state. `Profile.small_group` is no longer a group-progress runtime
  source.
- **Group-progress accessible list / own group — membership-core / role-scope
  structure-aware (CS-CORE.2D-B)** in `accounts.permissions.get_accessible_progress_groups`;
  ordinary membership grants only the single mapped own group.

## 3. What remains before legacy retirement

- ~~Replace the `my_group_progress` last-resort `Profile.small_group` default~~ —
  **done in READING-STRUCT.1D** (see Section 5.6).
- ~~Backfill `structure_unit_at_post` for legacy group reflections that predate
  CS-CORE.4D/4G.2 so historical group posts are not silently invisible under the
  live structure-native gate.~~ — **done on local real data in READING-STRUCT.1F**
  (6 rows backfilled; `reflections_legacy_only_no_valid_snapshot` now 0 locally;
  see Section 5.8). Two no-source reflections (no legacy small group) remain
  intentionally unresolved / fail-closed. **Production apply not claimed.**
- Eventually drop the `small_group_at_post` mirror writes once no consumer
  remains (coordinate with the cross-module `Profile.small_group` retirement in
  CHURCH_STRUCTURE_CORE Section 12). (`get_user_small_group` was already removed
  in READING-STRUCT.1E.)

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

## 5.6 Group progress default is membership-core (READING-STRUCT.1D — implemented)

**Outcome: small runtime change.** `reading.views.my_group_progress` previously
had three default-group sources when no explicit `?group=` was passed:
(1) the permission-fenced membership-core candidate (CS-CORE.4F.2), then
(2) a legacy `Profile.small_group` last-resort fallback, then
(3) the first accessible group. READING-STRUCT.1D **removed source (2)**.

New rule (no explicit `?group=`):

1. permission-fenced membership-core candidate — the user's exactly-one active
   primary `ChurchStructureMembership`, mapped through its unit to a single active
   legacy `SmallGroup` **bridge**, and only if already in the legacy
   `get_accessible_progress_groups()` set;
2. else the first accessible group (role/permission driven — e.g. a district
   leader's first scoped group);
3. else the safe no-group state ("You are not assigned to a small group yet.").

`Profile.small_group` is **no longer read** anywhere in the group-progress
runtime. The membership candidate fails closed on no / multiple active primary
memberships and on a unit that does not map to exactly one active small-group; in
those cases an ordinary user (whose only accessible group is the membership-core
own group) gets the no-group state rather than the legacy profile group. The
date/status validity rules (active, primary, `start_date`/`end_date` window) are
the shared `accounts.structure_selectors` / `group_progress_shadow` ones, so
requested / future / ended memberships do not count.

The rest of the page was already membership-core and is unchanged: the accessible
group list / own group (`get_accessible_progress_groups` →
`get_user_membership_progress_own_group`, CS-CORE.2D-B), the visible roster
(`get_membership_core_progress_roster_users`, CS-CORE.4F.1), and the legacy
permission gate. No new helper was added — the existing
`get_membership_core_default_progress_group` already encodes the
exactly-one-active-primary → single-active-`SmallGroup`-bridge rule.

**Legacy SmallGroup remains only as the storage/query bridge** (the progress
model and `accessible_groups` set still key on `SmallGroup`); no model or field
was removed or renamed, and no migration was added.

**Reflection runtime is unchanged** (still snapshot-only per Section 5.5). **No
production command or `--apply` was run** (only the read-only audit). Existing
tests that had asserted the legacy profile default as runtime truth
(`GroupProgressDefaultSourceSwitchTests`) were updated to assert the new
membership-core / first-accessible / no-group behavior, plus new cases:
profile-group-without-membership → no group; profile≠membership → membership
group wins; ended membership → no group.

## 5.7 Legacy small-group helper cleanup (READING-STRUCT.1E — implemented)

**Outcome: dead-code/wording cleanup; no behavior change.** After 1C/1D no
Reading runtime path reads `Profile.small_group`. This slice removed the now-dead
helper and corrected stale wording so nothing implies a `Profile.small_group`
runtime fallback still exists.

**Removed (genuinely unused dead code):**

- `reading.views.get_user_small_group(user)` — returned `Profile.small_group`.
  It had **zero callers** (code, templates, or tests): CS-CORE.4G.2 dropped its
  reflection-read uses and READING-STRUCT.1D dropped the group-progress default
  use. A short comment in its place records the removal so it is not reintroduced.

**Kept intentionally (audit / diagnostic / storage — not runtime source):**

- `reading.group_progress_shadow` legacy-roster/default helpers (`_profile_small_group`,
  `_legacy_roster_user_ids`) — the **comparison baseline** for the read-only
  shadow audit; explicitly diagnostic, never the live source.
- `reading.structure_runtime_readiness` and the three audit/backfill commands
  read `Profile.small_group` / `small_group_at_post` to **inventory readiness**
  and to **source the snapshot backfill**, never to drive runtime.
- `ReflectionComment.small_group_at_post` — legacy snapshot/storage + write-path
  mirror; it is **not** a visibility source. When `structure_unit_at_post` is
  missing, ordinary group visibility stays **fail-closed** (Section 5.5), not a
  legacy-group fallback.
- `accounts.structure_selectors.get_user_legacy_small_group` — accounts-level
  legacy comparator, out of Reading scope; unchanged.

**Wording corrected:** the `reading.structure_runtime_readiness` module docstring
and the `users_profile_group_without_single_membership` comment no longer call
`Profile.small_group` a "last-resort fallback"; the
`audit_reading_structure_runtime_readiness` help no longer says the runtime still
"reads" `Profile.small_group`.

**No model/field retirement is claimed.** `Profile.small_group`, `SmallGroup`, and
`small_group_at_post` all remain (storage / bridge / audit). Reflection runtime is
unchanged; no migration, and no production command / `--apply` was run (only the
read-only audit).

## 5.8 Local real-data snapshot backfill apply (READING-STRUCT.1F — recorded)

**Outcome: docs-only record of a successful local real-data `--apply` run of the
1B backfill. No code/test/migration/template/runtime change in this slice, and no
production command was run.** The user ran the READING-STRUCT.1B backfill on the
local real-data DB after CS-RETIRE.1A. This section records the evidence.

**Pre-apply audit (`audit_reading_structure_runtime_readiness`):**

- `group_visible_reflections: 8`
- `reflections_with_legacy_small_group: 6`
- `reflections_with_structure_snapshot: 0`
- `reflections_snapshot_missing: 8`
- `reflections_legacy_only_no_valid_snapshot: 6`
- `progress_groups_total: 21`, `progress_groups_resolvable: 21`
- `users_with_single_active_primary_membership: 19`
- `users_with_multiple_active_primary_membership: 0`
- `users_profile_group_without_single_membership: 0`
- blockers present: `reflections_legacy_only_no_valid_snapshot`

**Backfill dry-run:** `reflections_checked: 8`, `skipped_existing_snapshot: 0`,
`would_backfill: 6`, `backfilled: 0`, `missing_legacy_group: 2`,
`missing_mapping: 0`, `inactive_unit: 0`, `wrong_unit_type: 0`,
`validation_error: 0`, `legacy_fields_mutated: 0`, `runtime_switched: false`.

**Apply result (`--apply`):** `reflections_checked: 8`,
`skipped_existing_snapshot: 0`, `would_backfill: 0`, `backfilled: 6`,
`missing_legacy_group: 2`, `missing_mapping: 0`, `inactive_unit: 0`,
`wrong_unit_type: 0`, `validation_error: 0`, `legacy_fields_mutated: 0`,
`runtime_switched: false`.

Rows backfilled:

- `comment_id=4` → unit #15 SMALLGROUP-1
- `comment_id=5` → unit #15 SMALLGROUP-1
- `comment_id=6` → unit #15 SMALLGROUP-1
- `comment_id=7` → unit #15 SMALLGROUP-1
- `comment_id=9` → unit #16 SMALLGROUP-2
- `comment_id=10` → unit #15 SMALLGROUP-1

**Post-apply dry-run:** `reflections_checked: 8`, `skipped_existing_snapshot: 6`,
`would_backfill: 0`, `backfilled: 0`, `missing_legacy_group: 2`, all other
mapping/type/validation buckets 0, `legacy_fields_mutated: 0`,
`runtime_switched: false` (idempotent — the 6 rows are now snapshot-backed).

**Post-apply audit:** `group_visible_reflections: 8`,
`reflections_with_legacy_small_group: 6`,
`reflections_with_structure_snapshot: 6`, `reflections_snapshot_resolvable: 6`,
`reflections_snapshot_missing: 2`,
`reflections_legacy_only_no_valid_snapshot: 0`, `progress_groups_total: 21`,
`progress_groups_resolvable: 21` (all progress unresolved buckets 0),
`users_with_multiple_active_primary_membership: 0`,
`users_profile_group_without_single_membership: 0`, **blockers present: none**.

**Interpretation:**

- `comment_id=1` and `comment_id=2` still have no snapshot because they also have
  **no legacy small-group source** (`missing_legacy_group: 2`). They are **not
  auto-backfillable** and, under the snapshot-only reflection privacy gate
  (Section 5.5), they **remain fail-closed for ordinary users**. This is
  **expected** and is **not a blocker** for Reading runtime retirement.
- **No legacy fields were mutated** (`legacy_fields_mutated: 0`); only the
  additive `structure_unit_at_post` snapshot was set.
- **No runtime source was switched** by the command (`runtime_switched: false`).
- **Local real-data Reading reflection blockers are clear**
  (`reflections_legacy_only_no_valid_snapshot: 0`).
- **Production apply status is not claimed here and should only be claimed if
  separately confirmed** on the production DB.

## 6. Next proposed slice

**READING-STRUCT.1F (done locally — see Section 5.8):** the 1B backfill `--apply`
was run on the **local real-data** DB, driving
`reflections_legacy_only_no_valid_snapshot` to zero locally (two no-source
reflections remain intentionally unresolved / fail-closed). **The same apply has
not been claimed on production** and should only be claimed if separately
confirmed.

**Next (proposed):** a fallback-removal / legacy-field-retirement slice for the
`small_group_at_post` mirror and the `SmallGroup` progress storage bridge — each
gated on a clean `audit_reading_structure_runtime_readiness --fail-on-blockers`
and `audit_group_progress_shadow --fail-on-drift` over the target (eventually
production) data, coordinated with the cross-module `Profile.small_group`
retirement (CHURCH_STRUCTURE_CORE Section 12).

The 1A audit, 1B backfill, 1C verification, and 1E cleanup slices perform **no**
runtime switch; 1D makes the single group-progress default-source change
described above; 1F is docs-only (records the local apply) and switches no
runtime source.
