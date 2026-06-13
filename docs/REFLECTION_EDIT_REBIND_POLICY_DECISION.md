# CS-CORE.4C.1/4C.2 Reflection Edit Re-bind Policy Decision and Implementation

## 1. Purpose and Status

This is a **docs-only policy decision record** (CS-CORE.4C.1) for one specific,
already-flagged behavior in reflection privacy:

> When an existing **top-level, group-shared** reflection (`VISIBILITY_GROUP`) is
> edited and **remains** group-shared, `comments.views.edit_comment()` re-binds
> `ReflectionComment.small_group_at_post` to the editor's **current**
> `Profile.small_group`. After the author transfers groups, an ordinary edit
> therefore silently **re-homes** the historical post from the old group to the
> author's new group.

CS-CORE.4A flagged this re-bind as "a behavior worth flagging … decide deliberately
rather than inherit it by accident" (`docs/READING_PROGRESS_REFLECTION_PRIVACY_MIGRATION_PLAN.md`
Sections 3.4, 4.1, and No-Go Rule 2). CS-CORE.4C **locked the then-current behavior
in a test** (`reading.tests.ReflectionPrivacyInvariantTests.test_top_level_group_edit_after_transfer_rebinds_to_current_profile_group`)
with an explicit comment that the test "documents the existing re-bind, not an
endorsement of future policy." CS-CORE.4C.1 recorded the deliberate decision that
CS-CORE.4A asked for, and CS-CORE.4C.2 implemented it.

**Status:** Policy C is active after CS-CORE.4C.2. The runtime change is limited to
`comments.views.edit_comment()`: an existing top-level group-shared reflection that
stays group-shared preserves its existing `small_group_at_post`; a private/church
reflection newly changed to group visibility stamps the editor's current
`Profile.small_group`; replies still inherit the parent snapshot. CS-CORE.4C.2 made no
model, migration, form, admin, URL, template, CSS, management-command,
membership-core, `structure_unit_at_post`, group-progress, ServiceEvent, Bible Study,
or data-migration change. Existing posts that were already re-bound under the old
behavior were not mass-rewritten. Reflection create/edit group binding remains
legacy-driven by `Profile.small_group`.

CS-CORE.4D later added nullable `ReflectionComment.structure_unit_at_post` as an
additive, write-only companion snapshot. It mirrors the Policy C write rules recorded
here: replies inherit the parent structure snapshot; an already-group top-level
reflection that stays group preserves its existing structure snapshot; and a
private/church reflection newly changed to group stamps the editor's current mapped
structure unit when one exists. This does not change Policy C's legacy runtime
behavior: visibility still reads `small_group_at_post` and current `Profile.small_group`,
not `structure_unit_at_post`.

Related docs:

- `docs/READING_PROGRESS_REFLECTION_PRIVACY_MIGRATION_PLAN.md` (CS-CORE.4A/4B/4C; privacy invariants; this is the parent plan)
- `docs/CHURCH_STRUCTURE_CORE_MIGRATION_PLAN.md` (CS-CORE plan; milestone map; no-go rules)
- `docs/LEGACY_PROFILE_SMALL_GROUP_CONSUMER_INVENTORY.md` (CS-CORE.3A consumer inventory; reflection create/edit group binding row)

## 2. Previous Behavior (verified against the worktree on 2026-06-12)

This section preserves the old Policy A behavior for historical context.

### 2.1 Creation of a group post

`comments.views.add_comment()` writes
`comment.small_group_at_post = request.user.profile.small_group` on every new comment
(`comments/views.py`). For a `VISIBILITY_GROUP` post this snapshot is the privacy key:
`ReflectionComment.can_be_seen_by()` returns true for a non-author, non-staff viewer
only when the viewer's current `Profile.small_group` equals `small_group_at_post`
(`comments/models.py`). The visibility option is offered only when the author has a
group (`comments.forms.ReflectionCommentForm`), and `clean()` rejects a group post for
a no-group user.

### 2.2 Editing an existing top-level group post while staying group-visible

`comments.views.edit_comment()`, for a top-level post whose edited visibility is
`VISIBILITY_GROUP`, **re-binds** `small_group_at_post` to the editor's current
`Profile.small_group` (`comments/views.py`, the `if edited_comment.visibility ==
ReflectionComment.VISIBILITY_GROUP:` branch). When the author has not transferred,
this is a no-op (current group == post-time group). When the author **has**
transferred, this moves the post to the new group. Editing body text or the anonymity
flag alone is enough to trigger it, because the re-bind runs whenever the saved
visibility is group.

### 2.3 Editing a private/church post into group-visible

The same branch stamps the editor's current group. Changing a `VISIBILITY_PRIVATE` or
`VISIBILITY_CHURCH` post to `VISIBILITY_GROUP` is, in substance, a **new group-share
action**, and stamping the current group is the correct snapshot for that action. The
form's `clean()` still rejects this for a no-group user (no-group safety preserved).

### 2.4 Editing replies

Replies never compute their own group. `add_reply()` makes a reply inherit the
parent's `visibility` and `small_group_at_post`, and `edit_comment()` re-inherits the
parent's `visibility` / `small_group_at_post` on every reply save (`comments/views.py`,
the `if is_reply:` branch). A reply is never independently re-homed; it always rides the
parent snapshot. `reading.tests.py` pins this
(`test_reply_inherits_parent_visibility_and_group_and_stays_inherited_on_edit`,
`test_reply_edit_does_not_change_parent_visibility`).

### 2.5 Author transfer from old group to new group

Transfer itself does **not** rewrite existing posts:
`test_group_post_keeps_historical_snapshot_after_author_transfer` proves an untouched
old post keeps `small_group_at_post == old_group`, stays visible to the old group, and
stays invisible to the new group. The re-bind only fires **on edit** (Section 2.2):
`test_top_level_group_edit_after_transfer_rebinds_to_current_profile_group` proves that
after transfer, editing the old post sets `small_group_at_post = new_group`, makes it
visible to the new group, and **removes** it from the old group's view.

### 2.6 Previous behavior summary table

| Action | Previous snapshot effect |
| --- | --- |
| Create group post | Stamp author's current group (correct) |
| Edit top-level group post, stay group (no transfer) | No-op (current == post-time) |
| Edit top-level group post, stay group (after transfer) | **Re-home old → new group** |
| Edit private/church post → group | Stamp editor's current group (new share) |
| Edit reply | Re-inherit parent snapshot (never independent) |
| Transfer alone (no edit) | No change to existing posts |

## 3. Privacy Risk

The re-bind in Section 2.2 creates a **two-directional** privacy change as a side
effect of an ordinary edit:

1. **Leak to the new group (broadening).** A reflection originally shared only to the
   old group becomes visible to the author's **new** group — a group that was never the
   intended audience. The author may not even realize this happened; they only meant to
   fix a typo or toggle anonymity.
2. **Loss for the original group (silent un-share).** The original group, which could
   previously see the post (and may have replied under it), **loses** visibility the
   moment the author edits. Their context disappears without any explicit un-share
   action.
3. **It is a side effect, not an explicit transfer/re-share action.** The user took no
   action that signals "move this to my new group." Body edits, anonymity toggles, and
   simply re-saving while staying group-visible all trigger it. This makes the privacy
   outcome surprising and hard to reason about.

This directly tensions with the parent plan's binding privacy invariants
(`docs/READING_PROGRESS_REFLECTION_PRIVACY_MIGRATION_PLAN.md` Section 4):

- Invariant 1 (**no broadening of group-shared reflection visibility**) — the leak in
  (1).
- Invariant 2 (**no accidental re-homing of historical posts**) — `small_group_at_post`
  is a snapshot, and (1)+(2) re-home it without an explicit approved archive rule.

Note the asymmetry already locked by tests: a **transfer alone** is invariant-safe
(Section 2.5); only the **edit-after-transfer** path re-homes. So the risk is narrow
and well-localized, which is what makes a conservative fix cheap.

## 4. Candidate Policies

### Policy A — Keep current behavior (re-bind on every group edit)

Editing a group post always re-stamps the editor's current group.

- **Pros:** zero change; the snapshot always equals the author's current group, which
  is simple to describe ("a group post belongs to your current group").
- **Cons:** violates invariants 1 and 2 on the edit-after-transfer path; re-homes
  historical posts as a side effect of unrelated edits; can both leak to the new group
  and un-share from the original group silently. Directly contradicts the parent plan's
  No-Go Rule 2 and the recommended option (a) in Section 4.1.

### Policy B — Preserve the original group snapshot when editing an existing group post

When editing a top-level post that **was already** group-shared and **stays**
group-shared, leave `small_group_at_post` untouched.

- **Pros:** fully honors snapshot semantics; an old group post stays with its original
  group regardless of edits or transfers; satisfies invariants 1 and 2.
- **Cons:** offers no sanctioned way to ever move a post to the author's new group; a
  user who genuinely wants to re-share to their new group has no path. Acceptable, but
  slightly less flexible than C.

### Policy C — Preserve original snapshot by default; allow an explicit re-share/re-home later (recommended)

Same default as B (an edit that keeps an existing group post group-shared preserves the
original snapshot), **but** the design leaves room for a future, **explicit** re-share
or re-home action (a deliberate "share to my current group" control) rather than
folding re-homing into ordinary edit. Until that explicit action is designed, behavior
equals B.

- **Pros:** privacy-conservative default (identical to B for invariants 1 and 2);
  preserves the legitimate "I want this in my new group now" need as an explicit,
  visible, opt-in action instead of a silent side effect; matches the parent plan's
  recommended option (a) plus its note that re-homing must be a deliberate decision.
- **Cons:** the explicit re-share action is additional future design surface — but it
  is **out of scope** here and need not exist for the default to be correct.

### Policy D — Archive/hide old group posts on transfer

On transfer, old group posts become read-only to the original group and/or hidden from
both groups, per an explicit archive rule.

- **Pros:** strongest separation between past and present group context.
- **Cons:** heaviest behavior change; requires a product decision and likely a data
  rule; affects posts that were never edited; changes transfer (currently invariant-safe
  and untouched) into a mutating event. Out of proportion to the narrow risk. The
  parent plan already lists archive as option (d): "Requires explicit product
  decision."

## 5. Decision / Implementation

**Adopt Policy C** (preserve the original group snapshot on edit by default; reserve
re-homing for a future explicit action). CS-CORE.4C.1 recorded this decision, and
CS-CORE.4C.2 implemented the default Policy C behavior.

Rationale:

- **More privacy-conservative than current behavior.** It removes both the leak to the
  new group and the silent un-share from the original group on the edit-after-transfer
  path (Section 3), bringing `edit_comment()` into line with invariants 1 and 2. The
  default outcome is identical to Policy B; C only additionally leaves room for a
  sanctioned explicit re-share later.
- **Compatible with historical snapshot semantics.** `small_group_at_post` is defined
  as the group the post was shared to **at post time** (`comments/models.py`,
  `docs/...PRIVACY_MIGRATION_PLAN.md` Section 3.4). Policy C makes edit behavior match
  that definition: an edit is not a re-post, so it should not re-stamp the snapshot.
  Creating a brand-new group share (private/church → group, Section 2.3) is genuinely a
  new share and continues to stamp the editor's current group, which is consistent — the
  snapshot records the moment the post *became* group-shared, not the moment of an
  unrelated body edit.
- **Why a separate runtime slice.** Changing this is itself a privacy change to a
  canonical write path, and the parent plan's No-Go Rule 2 forbids changing
  `small_group_at_post` re-bind behavior "without explicit, separate approval" and
  forbids migrating reflection privacy "as a side effect of a refactor." It also
  requires intentionally rewriting a test that CS-CORE.4C deliberately locked
  (Section 7). CS-CORE.4C.2 was that approved, tested runtime slice and was kept
  separate from membership-core migration or any other consumer switch.

This decision **supersedes nothing** in the parent plan; it **resolves** the open
sub-question the parent plan deferred ("separately decide whether the `edit_comment`
re-bind … should be changed," Section 4.1) by recording Policy C as the chosen
direction.

## 6. Runtime Slice CS-CORE.4C.2 (implemented)

CS-CORE.4C.2 implements Policy C as follows:

- **The only runtime change is in `comments.views.edit_comment()`.** For a
  top-level post, distinguish two cases instead of one:
  1. **Post was already `VISIBILITY_GROUP` and stays `VISIBILITY_GROUP`** → **do not**
     re-bind; preserve the existing `small_group_at_post`.
  2. **Post is changing into `VISIBILITY_GROUP` from private/church** → stamp the
     editor's current `Profile.small_group` (new group-share), subject to the existing
     no-group validation.

  The implementation captures the pre-edit visibility and `small_group_at_post` before
  `form.save(commit=False)`, then applies the two cases above.
- **Form validation stayed unchanged.** `ReflectionCommentEditForm` already gates the
  group option on having a current group and rejects a group post for a no-group user.
- **No data migration.** Policy C only affects **future** edits. Existing rows are not
  touched.
- **Do not mass-rewrite already re-bound posts.** Posts that were re-homed under the
  current behavior stay as they are unless a **separate** data-review slice decides
  otherwise. Policy C is forward-only.
- **Replies unchanged.** The reply inheritance branch stays exactly as is; replies
  continue to ride the parent snapshot and are never independently re-homed.
- **Keep it isolated.** This future slice must not be bundled with membership-core
  belonging switches, a `structure_unit_at_post` field, group-progress changes, role/
  scope changes, or any other consumer switch (parent plan No-Go Rules 2 and 9;
  CS-CORE plan No-Go Rule 9).

CS-CORE.4D was later approved as that separate `structure_unit_at_post` slice. It
mirrors the Policy C snapshot decisions into the additive field only; it does not read
the new field for visibility and does not change the legacy `small_group_at_post`
runtime policy above.

## 7. Test Changes in CS-CORE.4C.2

CS-CORE.4C.2 intentionally changed the test suite together with the runtime change:

- **Replaced the previously locked re-bind test.**
  `reading.tests.ReflectionPrivacyInvariantTests.test_top_level_group_edit_after_transfer_preserves_original_group_snapshot`
  now asserts that editing an existing group post after transfer preserves
  `small_group_at_post == old_group`, keeps the post visible to the old group, and
  keeps it invisible to the new group.
- **Added a private/church → group stamping test.** Editing a private or church post into
  `VISIBILITY_GROUP` stamps the editor's **current** group (new share), and is rejected
  for a no-group user.
- **Added an explicit "edit body/anonymity only, stay group" preservation test.** Editing only body
  or anonymity on an already-group post (with and without a prior transfer) preserves
  the original snapshot.
- **Reply inheritance tests remain unchanged.** They already assert the correct Policy C
  behavior (replies follow the parent).
- **No-group create/edit safety is covered.** The existing create/form safety test stays
  in place, and CS-CORE.4C.2 adds an edit-path assertion that a no-group user cannot
  force a private reflection into group visibility by POSTing the hidden value.
- **List == detail must stay in lockstep.** Any change must keep
  `get_visible_reflection_filter`, the `passage_wall` group tab, and `can_be_seen_by`
  agreeing for every viewer (parent plan invariant 3).

## 8. Rollback Strategy

- **The docs-only slice (CS-CORE.4C.1):** nothing to roll back; it changed no runtime
  behavior. Reverting that commit removes the document and the cross-references.
- **The runtime slice (CS-CORE.4C.2):** the change is a single local branch decision in
  `edit_comment()`. Rollback is to restore the unconditional re-bind (Policy A). Because
  Policy C is forward-only and writes no migration, rollback touches no stored data;
  `small_group_at_post` values written under either behavior remain valid snapshots.

## 9. No-Go Rules

1. **Do not change runtime behavior beyond the approved CS-CORE.4C.2 edit path.**
2. **Do not silently broaden** an old group post's visibility to the author's new group
   (the leak in Section 3); any move must be an explicit, approved action.
3. **Do not silently un-share** an old group post from its original group as a side
   effect of an edit.
4. **Do not mass-rewrite** existing already-re-bound posts; Policy C is forward-only,
   and any historical cleanup is a separate, separately-approved data-review slice.
5. **Do not make replies independently re-home;** replies always follow the parent
   snapshot.
6. **Do not bundle** the edit-path runtime change with membership-core migration, a
   `structure_unit_at_post` field, group-progress changes, role/scope changes, or any
   other consumer switch.
7. **Do not change `small_group_at_post` semantics** beyond the narrow edit-path
   decision recorded here without separate approval (parent plan No-Go Rule 2).

## 10. Verification

For CS-CORE.4C.2:

```powershell
git diff --check
E:\bible-reading\_venvs\bible-reading-codex-312\Scripts\python.exe manage.py check
E:\bible-reading\_venvs\bible-reading-codex-312\Scripts\python.exe manage.py makemigrations --check
E:\bible-reading\_venvs\bible-reading-codex-312\Scripts\python.exe manage.py test reading.tests.ReflectionPrivacyInvariantTests -v 2
```

No browser/mobile QA is required or claimed because CS-CORE.4C.2 changes a Django
view branch, focused tests, and docs only.
