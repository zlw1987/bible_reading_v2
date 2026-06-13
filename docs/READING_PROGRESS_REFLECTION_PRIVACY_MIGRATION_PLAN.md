# CS-CORE.4A Reading, Group Progress, and Reflection Privacy Migration Plan

## 1. Purpose and Status

This is a **docs-only, plan-only** migration plan (CS-CORE.4A) for the remaining
privacy-sensitive consumers of legacy `Profile.small_group`, `accounts.SmallGroup`,
and the reflection historical snapshot field `ReflectionComment.small_group_at_post`:

- reading **group progress** (rosters, defaults, and progress-permission scoping), and
- **reflection / comment privacy** (the "My Group" reflection tab, group-shared
  reflection visibility, create/edit group binding, and reply inheritance).

CS-CORE.4A does **not** authorize or implement any runtime, code, template, form,
view, model, migration, admin, URL, static, or test-behavior change. It does not
remove or hide `Profile.small_group`, it does not change `small_group_at_post`
semantics, and it does not change reflection visibility or group-progress permissions.
After CS-CORE.4A, every consumer named here is still legacy-driven exactly as before.

CS-CORE.4B is complete as a read-only diagnostic slice. It adds
`audit_reading_privacy_membership_readiness`, a management command that compares
legacy `Profile.small_group` behavior with a membership-core candidate answer for
group-shared reflection visibility and group-progress roster membership. The command
writes nothing, has no `--apply` mode, and is not used by request/runtime code. After
CS-CORE.4B, reading progress, group progress, reflection/comment privacy,
`Profile.small_group`, and `ReflectionComment.small_group_at_post` remain
legacy-driven exactly as before; no switch happened.

CS-CORE.4C is complete as a test-only privacy invariant slice. It adds targeted
tests for the canonical reflection gate, list/detail/group-tab agreement, reply
inheritance, transfer snapshot behavior, the current top-level edit re-bind behavior,
no-group safety, group-progress roster membership, progress permissions, staff/all
progress override behavior, and the existing CS-CORE.4B read-only audit command. It
changes no runtime, view, form, model, template, URL, admin, static, migration, source
of truth, or management-command behavior. After CS-CORE.4C, these consumers remain
legacy-driven exactly as before.

CS-CORE.4C.1 is complete as a docs-only policy decision slice. It records the
deliberate decision for the top-level group-shared reflection **edit re-bind** that
CS-CORE.4A flagged and CS-CORE.4C locked in a test: see
`docs/REFLECTION_EDIT_REBIND_POLICY_DECISION.md`. The decision recommends **Policy C**
— preserve the original `small_group_at_post` snapshot when editing an existing
group-shared post (so an edit after a group transfer no longer re-homes the post),
while still stamping the editor's current group when a private/church post is newly
changed to group visibility, and never re-homing replies independently. CS-CORE.4C.1
itself changed no runtime, view, form, model, template, URL, admin, static, migration,
source of truth, management-command, or test behavior. At that point, the current
edit re-bind behavior and its CS-CORE.4C lock test were intentionally unchanged;
CS-CORE.4C.2 below is the later runtime slice that intentionally updates both.

CS-CORE.4C.2 is complete as the narrow runtime slice that implements Policy C. Editing
an existing top-level group-shared reflection that remains group-shared now preserves
the existing `small_group_at_post` snapshot; changing a private/church reflection to
group visibility stamps the editor's current `Profile.small_group`; replies continue
to inherit the parent snapshot and never independently re-home. Existing already
re-bound posts were not mass-rewritten. Reading/progress/reflection runtime otherwise
remains legacy-driven: no membership-core switch, no `structure_unit_at_post`, no
group-progress change, and no model/migration/form/template/admin/URL/CSS change.

CS-CORE.4D is complete as an additive structure snapshot slice. `ReflectionComment`
now has nullable `structure_unit_at_post`, written only as a companion snapshot for
new/edited future records that already write or preserve `small_group_at_post`.
Visibility still uses `small_group_at_post` and current `Profile.small_group`; no read
path consults `structure_unit_at_post`. Old posts were not backfilled, no membership-core
switch happened, and no group-progress, ServiceEvent, Bible Study, template, admin,
URL, CSS, or data-migration behavior changed.

CS-CORE.4E is complete as a group-progress shadow-mode comparison slice. The new
`reading/group_progress_shadow.py` helper computes a membership-core candidate default
group and roster for the selected legacy `SmallGroup` alongside the legacy answer, and
`reading.views.my_group_progress()` now stores that comparison in context under the
internal `group_progress_shadow` key (not rendered). This is comparison-only: the
actual page still uses legacy `Profile.small_group`, legacy `SmallGroup`,
`accounts.permissions.get_accessible_progress_groups()`, and
`accounts.permissions.can_view_group_progress_for()`, so the selected group, the
visible roster, the redirects, and the permission set are all unchanged. The candidate
fails closed on ambiguity (no active primary membership, multiple active primary
memberships, an unmapped selected group, or a membership unit that is not a mapped
small-group unit) and never grants progress access — ordinary `ChurchStructureMembership`
still confers nothing here (invariant 5). No membership-core runtime switch happened, no
role-scope decision was made, and no model, migration, template, CSS, admin, or URL
change was needed. The existing read-only `audit_reading_privacy_membership_readiness`
command already exposes equivalent progress roster `would_gain` / `would_lose` and
risk categories, so it was reused unchanged and pinned by a new test asserting the
helper and the command agree.

This plan follows the established CS-CORE direction (`docs/CHURCH_STRUCTURE_CORE_MIGRATION_PLAN.md`):
legacy retire / new model as core, `ChurchStructureUnit` is the canonical structure tree,
`ChurchStructureMembership` is becoming the canonical ordinary-user belonging model, and
legacy small-group retirement is consumer-by-consumer. These consumers are explicitly
called out as **high privacy risk** in `docs/LEGACY_PROFILE_SMALL_GROUP_CONSUMER_INVENTORY.md`
and in that inventory's "Non-Consumers / Do Not Migrate Casually" list; they require their
own privacy-first plan before any runtime switch. This document is that plan.

Related docs:

- `docs/CHURCH_STRUCTURE_CORE_MIGRATION_PLAN.md` (CS-CORE plan; runtime contract; no-go rules)
- `docs/LEGACY_PROFILE_SMALL_GROUP_CONSUMER_INVENTORY.md` (CS-CORE.3A consumer inventory)
- `docs/REFLECTION_EDIT_REBIND_POLICY_DECISION.md` (CS-CORE.4C.1 edit re-bind policy decision)
- `docs/LEGACY_BIBLE_STUDY_SESSION_RETIREMENT_DECISION.md` (precedent for legacy-vs-migrate decisions)

## 2. Scope

In scope (CS-CORE.4A audit plus later approved CS-CORE.4D additive snapshot context):

- `reading.views.get_user_small_group()`
- `reading.views.get_visible_reflection_filter()`
- `reading.views.passage_wall()`
- `reading.views.my_group_progress()`
- `accounts.permissions.get_accessible_progress_groups()` and `can_view_group_progress_for()`
- `comments.models.ReflectionComment.can_be_seen_by()`, `ReflectionComment.small_group_at_post`,
  and additive write-only `ReflectionComment.structure_unit_at_post`
- `comments.forms.ReflectionCommentForm`, `comments.forms.ReflectionCommentEditForm`
- `comments.views.add_comment()`, `comments.views.add_reply()`, `comments.views.edit_comment()`
- templates `templates/reading/group_progress.html`, `templates/reading/passage_wall.html`
- supporting transition context only: `accounts.models.Profile.small_group`,
  `ChurchStructureMembership`, staff approval sync, `audit_structure_belonging`

Out of scope (see Section 9 no-go rules and Section 11 non-goals): any visibility read-path
source switch, `ChurchRoleAssignment` scope migration, ServiceEvent changes, Bible Study V1/V2
changes, `Profile.small_group` removal, and `small_group_at_post` semantic change. CS-CORE.4D
is the approved additive exception for adding/writing `structure_unit_at_post`; it does not
authorize any of those switches or removals.

## 3. Current Code Audit (verified against the worktree on 2026-06-12)

### 3.1 Reading "current group" helper

- `reading.views.get_user_small_group(user)` returns `user.profile.small_group` (a legacy
  `SmallGroup` or `None`). It is a **read-only display/context helper** used by the reflection
  filter and `passage_wall`. It does not by itself grant or deny anything; it is the seam every
  reflection-side group decision currently flows through.

### 3.2 Group progress (`reading.views.my_group_progress`)

Two distinct legacy dependencies:

1. **Which groups the user may select** — `accounts.permissions.get_accessible_progress_groups(user)`.
   This is **access-granting**:
   - staff / superuser / `CAP_VIEW_ALL_GROUP_PROGRESS` → all active `SmallGroup` rows;
   - otherwise the accessible set is the union of:
     - `ChurchRoleAssignment` **district-leader** scopes (`assignment.district_id`),
     - `ChurchRoleAssignment` **group-leader** scopes (`assignment.small_group_id`),
     - the user's own `Profile.small_group` (if active).
   - `can_view_group_progress_for()` gates a single group through the same set.
   This mixes **two different authority sources**: legacy role scopes (`ChurchRoleAssignment`)
   and ordinary belonging (`Profile.small_group`). That coupling is the crux of why this consumer
   is high-risk: it cannot be migrated as "just belonging."
2. **Default selected group and roster** — inside `my_group_progress`:
   - default `selected_group` falls back to `user_profile.small_group` (filtered through the
     accessible set);
   - the **roster** is `User.objects.filter(profile__small_group=selected_group)`.
   The roster is a **privacy-visible list of people plus their reading check-ins and progress
   percentages**, so it is both a display surface and a data-exposure surface. Roster membership
   is driven entirely by `Profile.small_group`, independent of any membership row.

`templates/reading/group_progress.html` only renders `selected_group`, the `groups` selector
options, and `member_rows` from the view; it holds no independent legacy logic.

### 3.3 Reflection / comment privacy (read paths)

- `comments.models.ReflectionComment.can_be_seen_by(user)` is the **canonical access gate**. For
  `VISIBILITY_GROUP` posts it returns true only when
  `user.profile.small_group` is set **and** `small_group_at_post_id == user.profile.small_group_id`.
  Staff, the author, and `VISIBILITY_CHURCH` posts bypass the group check. Deleted/hidden posts are
  author/staff only.
- `reading.views.get_visible_reflection_filter(user)` builds the ORM `Q()` used for list queries.
  For non-staff it admits own posts, church-visible posts, and — only when `user_group` is set —
  `VISIBILITY_GROUP` posts with `small_group_at_post=user_group`. Staff get `Q()` (all). This is the
  **query-level mirror** of `can_be_seen_by` and must stay in lockstep with it.
- `reading.views.passage_wall(request)` "group" tab: staff see all `VISIBILITY_GROUP` posts; a user
  with a group sees own posts plus non-hidden `VISIBILITY_GROUP` posts where
  `small_group_at_post=user_group`; a user with no group sees only their own. This is **access-granting
  read filtering**, and it is a third place that encodes the same group-visibility rule.

Invariant to preserve: `can_be_seen_by`, `get_visible_reflection_filter`, and the `passage_wall`
"group" tab are three encodings of one rule. Any migration must move them together or they will
diverge (a list/detail leak).

### 3.4 Reflection / comment privacy (write paths and historical snapshot)

- `ReflectionComment.small_group_at_post` is a **historical snapshot FK** to `accounts.SmallGroup`
  (`on_delete=SET_NULL`). It records the group the post was shared to **at post time**, and it is the
  privacy key for group visibility forever after.
- `comments.views.add_comment()` writes `comment.small_group_at_post = request.user.profile.small_group`
  on every new comment (snapshot **write**). For a non-group post this is incidental; for a
  `VISIBILITY_GROUP` post it is the binding that controls who can ever see it. After
  CS-CORE.4D, the same create path also writes `structure_unit_at_post` from the current
  legacy group's mapped `ChurchStructureUnit` when one exists; this structure snapshot is
  additive/write-only and is not a visibility key.
- `comments.views.add_reply()` makes a reply **inherit** the parent's `visibility` and
  `small_group_at_post`. After CS-CORE.4D replies also inherit the parent's
  `structure_unit_at_post`. Replies never compute their own group or structure unit; they
  ride the parent snapshot.
- `comments.views.edit_comment()`:
  - replies re-inherit the parent's `visibility` / `small_group_at_post` /
    `structure_unit_at_post` on save;
  - for a top-level post, CS-CORE.4C.2 implements Policy C: if a post was already
    `VISIBILITY_GROUP` and remains group-shared, the existing `small_group_at_post`
    snapshot is preserved; if a private/church post is newly changed to
    `VISIBILITY_GROUP`, `small_group_at_post` is stamped from the editor's current
    `Profile.small_group`. CS-CORE.4D mirrors those same Policy C snapshot rules into
    `structure_unit_at_post`, preserving it for already-group posts that stay group and
    stamping the current mapped unit only when private/church becomes group. Before
    CS-CORE.4C.2, editing an old group post after a transfer re-bound it to the editor's
    current group; that historical behavior is preserved in
    `docs/REFLECTION_EDIT_REBIND_POLICY_DECISION.md` but is no longer the active edit policy.
- `comments.forms.ReflectionCommentForm` / `ReflectionCommentEditForm`: presence of
  `user.profile.small_group` decides whether the **"My Group" visibility choice is offered**, sets the
  default visibility (group when a group exists, else private), and `clean()` rejects a group post when
  the user has no group. This is **option-gating + validation**, not a stored grant, but it is what
  routes users into the group-snapshot write path above.

### 3.5 Supporting transition context (not migrated here)

- `accounts.models.Profile.small_group` remains the legacy belonging field every path above reads.
  Per the runtime contract it must remain until all consumers are migrated or retired.
- `ChurchStructureMembership` already has membership-core selector helpers in
  `accounts/structure_selectors.py` (`get_user_primary_membership_unit`,
  `get_user_membership_structure_units`, `resolve_units_to_small_groups`,
  `user_matches_membership_structure_audience`, plus the preserved
  `user_matches_legacy_structure_audience` comparator). None of these are consulted by any
  reading/progress/reflection path today.
- Staff approval sync (`accounts.views.staff_membership_request_approve`,
  `_get_single_active_legacy_small_group_for_unit`) keeps `Profile.small_group` in step with an
  approved active primary membership **only when the unit maps to exactly one active legacy
  `SmallGroup`**; otherwise it warns and leaves the profile unchanged. So `Profile.small_group` is
  not guaranteed to equal the membership unit's group — drift is possible and is exactly what
  `audit_structure_belonging` reports.

### 3.6 Behavior classification summary

| Path | Legacy source | Read-only display/context | Grants/denies access | Writes historical snapshot | Depends on legacy role scopes |
| --- | --- | --- | --- | --- | --- |
| `get_user_small_group()` | `Profile.small_group` | Yes | No (feeds others) | No | No |
| `get_visible_reflection_filter()` | `Profile.small_group` + `small_group_at_post` | No | **Yes (read filter)** | No | No |
| `passage_wall()` group tab | `Profile.small_group` + `small_group_at_post` | No | **Yes (read filter)** | No | No |
| `ReflectionComment.can_be_seen_by()` | `Profile.small_group` + `small_group_at_post` | No | **Yes (canonical gate)** | No | No |
| `my_group_progress()` default + roster | `Profile.small_group` | Partly (roster display) | **Yes (roster membership)** | No | No |
| `get_accessible_progress_groups()` | `ChurchRoleAssignment` + `Profile.small_group` | No | **Yes (permission)** | No | **Yes** |
| `ReflectionCommentForm` / `EditForm` | `Profile.small_group` | Option display | Option-gating + validation | No | No |
| `add_comment()` | `Profile.small_group`; mapped `SmallGroup.church_structure_unit` only for additive write-only snapshot | No | No | **Yes (`small_group_at_post`; `structure_unit_at_post` after CS-CORE.4D)** | No |
| `add_reply()` | parent snapshot | No | No | **Yes (inherits parent `small_group_at_post` and `structure_unit_at_post`)** | No |
| `edit_comment()` | Existing snapshot for already-group posts; `Profile.small_group` and mapped unit only when newly changing private/church → group; parent for replies | No | No | **Yes (Policy C edit binding, mirrored into `structure_unit_at_post` after CS-CORE.4D)** | No |

## 4. Privacy Invariants (binding for any future runtime slice)

These are the privacy properties a correct migration must preserve. They are the acceptance bar
for CS-CORE.4C tests and any later switch.

1. **No broadening of group-shared reflection visibility.** A `VISIBILITY_GROUP` post must never
   become visible to a user it is not visible to today. In particular, a user must not gain
   visibility to another group's posts via root/parent/fellowship/ancestor units.
2. **No accidental re-homing of historical posts.** `small_group_at_post` is a snapshot. A user
   transferring groups must not cause old group-shared posts to silently appear in their new group,
   and must not cause their old posts to leave the original group's view, unless an explicit,
   approved archive rule says so.
3. **List == detail.** `get_visible_reflection_filter()`, the `passage_wall` "group" tab, and
   `ReflectionComment.can_be_seen_by()` must always agree. No post may be listed-but-not-openable or
   openable-but-not-listed for the same viewer.
4. **Replies never exceed their parent.** A reply's visibility is its parent's visibility and group;
   a reply must never be visible to anyone who cannot see the parent.
5. **Group progress is a permission, not a belonging inference.** Access to a group's roster and
   reading data is currently granted by role scopes plus own-group membership. Migration must not let
   ordinary `ChurchStructureMembership` alone confer the ability to view other members' progress.
6. **Roster correctness.** The progress roster must list exactly the people who belong to the
   selected group under the chosen source, with no cross-group leakage and no silent inclusion of
   transferred/ended members beyond what the rule states.
7. **No-group users stay safe.** Users with no group (legacy or membership) must keep safe empty
   states: no group tab content beyond their own posts, no group-progress access they did not have.
8. **Staff override unchanged.** Staff/superuser review access to group reflections and all group
   progress must be preserved exactly.
9. **Drift cannot silently flip a decision.** Because `Profile.small_group` and the active primary
   membership unit can disagree (Section 3.5), any switch must define which source wins and must be
   gated on `audit_structure_belonging` showing sustained near-zero risky drift first.

### 4.1 Historical group-shared reflections on transfer — the central policy question

When a user transfers groups, what happens to a previously group-shared reflection? Options:

- **(a) Stay visible to the group at post time** (current `small_group_at_post` semantics). Old posts
  remain owned by the original group; the author's new group does not see them. This is the current,
  privacy-conservative behavior and the recommended default to preserve.
- **(b) Follow the author's current group.** Old posts move to the new group's view. This **leaks
  the author's past group-private reflections to a group that was never the intended audience** and
  removes them from the original group. Rejected as a default; it also matches the surprising
  `edit_comment` re-bind behavior, which this plan flags as something to make deliberate, not extend.
- **(c) Both.** Visible to old and new group. Maximizes exposure; rejected unless a product owner
  explicitly wants cross-group reflection sharing.
- **(d) Explicit archive rule.** e.g. old posts become read-only to the original group and invisible
  to the new group, or are hidden after transfer. Requires explicit product decision.

**Recommendation:** preserve option (a) — `small_group_at_post` keeps posts tied to the group at post
time. The separate `edit_comment` re-bind decision is recorded in CS-CORE.4C.1
(`docs/REFLECTION_EDIT_REBIND_POLICY_DECISION.md`), and CS-CORE.4C.2 now implements Policy C: preserve
the original snapshot when editing an existing group post, stamp the current group only when newly
changing private/church → group, and leave replies inherited from the parent.

**Replies under old group-shared posts:** replies inherit the parent snapshot (Section 3.4) and must
continue to. Under option (a), replies stay with the parent's original group regardless of either
participant's current group. No reply should ever be re-homed independently of its parent.

## 5. Target Design Options

Comparison of candidate end states. "Membership-core" means active primary
`ChurchStructureMembership` resolved through the structure tree, as already used by ServiceEvent
audience rows (CS-CORE.2B-A) and Bible Study v2 meeting visibility (CS-CORE.2C-B).

- **Option A — Keep everything legacy; document risk + add audits only.**
  No runtime change. Add read-only diagnostics that compare legacy vs membership-core answers for
  reflection visibility and progress rosters. Lowest risk; preserves all invariants trivially. Does
  not advance retirement, but de-risks every later option. **This is CS-CORE.4A itself plus the
  proposed 4B.**

- **Option B — Switch "current group" display/defaults to membership-core; keep historical
  reflection `small_group_at_post` legacy.**
  `get_user_small_group()`-style "what is my current group" for *defaults and option-gating* would
  resolve from the active primary membership's mapped small-group unit, while stored reflection
  snapshots and the group-visibility comparison stay on legacy `SmallGroup`. Risk: the comparison key
  (`small_group_at_post` vs "current group") would then straddle two notions of group unless the
  comparison is also migrated, so this must be scoped to **display/default only**, never the
  visibility comparison, or it breaks invariant 3. Moderate value, must be carefully bounded.

- **Option C — Add a structure-native historical snapshot field for new reflections only
  (e.g. `structure_unit_at_post`), preserving `small_group_at_post`.**
  New posts additionally record the structure unit at post time; old posts keep only the legacy
  snapshot; visibility still reads the legacy snapshot until a later switch. This is additive and
  reversible, and it is the cleanest path to eventually compare membership against a unit snapshot
  without a legacy hop. Cost: a model/migration (deferred, additive, new rows only) and a write-path
  change — so it is its own narrow slice (proposed 4D), never bundled.

- **Option D — Migrate group-progress roster/permission logic to structure membership, but only
  after role-scope decisions.**
  Roster could come from membership rows for the selected unit; permission scoping
  (`get_accessible_progress_groups`) still depends on `ChurchRoleAssignment` and must not be inferred
  from ordinary membership (invariant 5). Because progress couples belonging and role scope, this
  option is blocked on a separate role-scope decision (CS-CORE.2D territory) and must not proceed
  inside this plan.

- **Option E — Full migration of reflection privacy and group progress to structure units.**
  All read filters, the canonical gate, snapshot semantics, roster, and progress permission move to
  membership/units in one effort. **This must not be first.** It would simultaneously change the
  canonical access gate, a historical privacy snapshot, three encodings of the visibility rule, and a
  permission surface that mixes role scopes — i.e. it violates the CS-CORE rule against bundling a
  source-of-truth switch with multiple consumers, and it maximizes the blast radius of any leak. Full
  migration is the *destination*, reached only after diagnostics, locked privacy tests, additive
  snapshot fields, and per-consumer shadow+switch slices have de-risked each piece.

## 6. Recommended Staged Migration Path

Each step is a separate, separately-approved slice. Names align with the CS-CORE.4 series; adjust if
a better scheme emerges, but keep the sequence and the gates.

- **CS-CORE.4A — This plan-only audit (current slice).** Docs only. No runtime change. Records the
  audit, invariants, options, staged path, test matrix, rollback strategy, and no-go rules.
- **CS-CORE.4B — Read-only diagnostics/audit command.** Complete.
  `audit_reading_privacy_membership_readiness` compares the current legacy answer
  against a membership-core candidate answer for group-shared reflection visibility
  and progress roster membership. It classifies reflection pairs as `same_visible` /
  `same_hidden` / `would_gain` / `would_lose`, progress roster pairs as
  `same_in_roster` / `same_out_of_roster` / `would_gain` / `would_lose`, and reports
  risky readiness categories such as unmapped reflection/progress groups, multiple
  active primary memberships, and profile/membership mismatch. It is read-only,
  writes nothing, has no `--apply`, and changes no runtime behavior. Its output is
  the standing gate evidence for any later switch.
- **CS-CORE.4C — Lock privacy invariants in tests/fixtures.** Complete. Added tests
  (no runtime change) that pin every invariant in Section 4 in both directions (leak
  and over-hide), including list==detail/group-tab agreement, reply inheritance,
  transfer scenarios, no-group users, group-progress roster and permission behavior,
  staff/all-progress override behavior, and the 4B audit command's read-only contract.
  These tests must stay green before any source switch.
- **CS-CORE.4C.2 — Implement reflection edit re-bind Policy C.** Complete. The
  top-level edit path now preserves the existing group snapshot when an already-group
  reflection stays group-visible, stamps the current legacy profile group only when a
  private/church reflection is newly changed to group visibility, and leaves reply
  inheritance unchanged. This is forward-only; no existing comments were mass-rewritten.
- **CS-CORE.4D — Additive structure snapshot for new reflections only.** Complete. Added
  nullable `ReflectionComment.structure_unit_at_post` (Option C) and writes it only as a
  companion to the existing legacy snapshot behavior for new/edited future records:
  top-level creates stamp the current mapped unit when present, replies inherit the
  parent unit snapshot, and Policy C edits preserve/stamp the structure snapshot in the
  same cases as `small_group_at_post`. No read-path or visibility change; old posts
  unaffected and not backfilled. Additive migration, instant rollback by ignoring the new field.
- **CS-CORE.4E — Shadow mode for group-progress roster/defaults.** Complete. The
  `reading/group_progress_shadow.py` helper computes the membership-core candidate
  default group and roster for the selected legacy group alongside the legacy ones and
  reports divergence (`same_default`, `same_roster`, `would_gain_user_ids`,
  `would_lose_user_ids`, plus boring `reason_codes`). `my_group_progress()` stores it
  under the internal, unrendered `group_progress_shadow` context key. Runtime stays
  legacy: selected group, visible roster, redirects, and permissions are unchanged, the
  candidate fails closed on ambiguity, and ordinary membership grants nothing. No source
  switch, and the role-scope decision is still explicitly *not* made here.
- **CS-CORE.4F+ — One runtime switch at a time.** Switch a single consumer per release (e.g. the
  reflection "group" read filter, then the canonical gate, then progress roster), each only after
  4C tests are green, 4B diagnostics show sustained near-zero risky drift, and a documented rollback
  exists. Progress *permission scoping* and any `ChurchRoleAssignment` semantics are explicitly **not**
  in this series and need their own decision.

## 7. Future Test Matrix (for CS-CORE.4C and each switch)

Reflection visibility (each in both legacy and post-switch worlds, asserting equality at switch time):

- group post visible to a same-group member; invisible to a different-group member; invisible to a
  no-group user; visible to author and to staff;
- list (`get_visible_reflection_filter`, `passage_wall` group tab) agrees with detail
  (`can_be_seen_by`) for every viewer class;
- hidden/deleted group posts visible only to author/staff;
- church and private visibility unaffected by any group migration.

Transfer scenarios:

- author transfers group, then an old group post: still owned by the group at post time (option (a));
  not shown to the new group; not removed from the original group;
- `edit_comment` on an old group post after transfer: assert the chosen, explicit behavior (current
  code re-binds to current group — the test must encode whatever the approved decision is, not the
  accidental behavior);
- reply under an old group post stays tied to the parent's snapshot regardless of either user's
  current group.

Create/edit group binding:

- group option offered iff the user has a group (legacy now; membership-core after a switch);
- creating a group post stamps the correct snapshot;
- validation rejects a group post for a no-group user.

Group progress:

- roster contains exactly the selected group's members, no cross-group leakage;
- default selected group matches the user's own group;
- permission set equals role scopes ∪ own group; ordinary membership alone never grants other-group
  progress access (invariant 5);
- staff / `CAP_VIEW_ALL_GROUP_PROGRESS` see all; no-group non-leader sees safe empty state.

Drift:

- fixtures where `Profile.small_group` ≠ active primary membership unit, asserting which source wins
  before/after each switch, and that the 4B diagnostic classifies them correctly.

## 8. Rollback Strategy

- **4A/4B/4C/4E (docs, read-only command, tests, shadow):** nothing to roll back; they change no
  runtime behavior. Reverting the commit removes the artifact.
- **4D (additive snapshot field):** the new field is write-only and unread; rollback is to stop
  writing it / ignore it. The column may stay (nullable, additive) until a formal retirement slice;
  no data loss.
- **4F+ (per-consumer switch):** each switch is a single source flip behind one helper (mirroring how
  `user_matches_structure_audience` can be pointed back at the legacy comparator for ServiceEvent).
  Rollback = point the one consumer's source helper back at `Profile.small_group` /
  `small_group_at_post`. Because only one consumer flips per release and 4C tests pin both worlds,
  rollback is mechanical and does not touch stored data. `small_group_at_post` is never rewritten by a
  switch, so historical snapshots survive any rollback intact.

## 9. No-Go Rules (binding for future implementers)

1. Do not migrate reflection privacy casually or as a side effect of a refactor.
2. Do not change `small_group_at_post` semantics (snapshot meaning, what is written, when it is
   re-bound) without explicit, separate approval. The `edit_comment` re-bind behavior in particular is
   not to be extended or "fixed" silently.
3. Do not make old group-shared posts visible to a user's new group by accident; preserve invariant 2.
4. Do not broaden visibility based on root / parent / fellowship / ancestor units without an explicit,
   approved rule (membership-core consumers elsewhere fail closed on non-small-group mappings; reflect
   that conservatism here).
5. Do not infer group-progress permission from ordinary `ChurchStructureMembership`; progress access
   stays role-scope-driven (invariant 5).
6. Do not migrate `ChurchRoleAssignment` district/small-group scope semantics inside this plan or any
   4-series slice.
7. Do not remove, hide, or stop writing `Profile.small_group` in any 4-series slice.
8. Do not change reading/progress/reflection runtime behavior in any selector/refactor slice; in a
   parity slice, any behavior difference is a bug.
9. Do not bundle a source-of-truth switch with another consumer's switch or with UI work in one
   release.
10. Do not switch any consumer before CS-CORE.4C privacy tests are green and CS-CORE.4B diagnostics
    show sustained near-zero risky drift.

## 10. Verification

```powershell
git diff --check
git diff --stat
```

No Django tests were required for CS-CORE.4A. CS-CORE.4C added targeted Django tests
for reading/progress/reflection privacy invariants and the existing 4B audit command
regression. No browser/mobile QA was required or claimed because 4C changed tests and
docs only.

## 11. Non-Goals

Beyond the completed CS-CORE.4D additive model/migration/write-path/test/doc slice and the
CS-CORE.4E comparison-only group-progress shadow helper/context/test slice, CS-CORE.4A
through CS-CORE.4E do not include or authorize:

- any visibility read-path, template, form, admin, URL, static, deployment, source-of-truth,
  or permission change;
- removal, hiding, or sync-only conversion of `Profile.small_group`;
- any change to `small_group_at_post` semantics or to reflection visibility;
- any use of `structure_unit_at_post` for visibility, filtering, permissions, or group progress;
- any change to group-progress permissions or rosters;
- any `ChurchRoleAssignment` scope migration;
- any ServiceEvent or Bible Study V1/V2 change;
- any data migration;
- staging, committing, or pushing.
