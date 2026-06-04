# Church Structure Profile.small_group Sync Plan

## 1. Purpose

CS-H.7E plans transition behavior for syncing `Profile.small_group` when staff approve a mapped small-group `ChurchStructureMembership`.

Sync is needed during the transition because current runtime consumers still read the legacy `Profile.small_group` field. `/studies/`, reading progress, `ServiceEvent`, and related behavior do not yet use `ChurchStructureMembership`, so approving membership alone does not change what the user can see or do in those flows.

This is planning-only. It does not change code, models, migrations, views, forms, templates, URLs, signup behavior, consumer queries, or runtime visibility.

## 2. Current Behavior

CS-H.7D approval updates the requested `ChurchStructureMembership` record to an active membership.

Current approval:
- sets the membership active
- sets the membership primary
- records approval metadata
- blocks approval when the user already has a current active primary membership
- does not change `Profile.small_group`

Therefore, approved membership by itself does not affect current `/studies/`, reading progress, `ServiceEvent`, or related visibility. Those consumers continue to depend on `Profile.small_group`.

## 3. Proposed CS-H.7E Behavior

On approve, future CS-H.7E implementation should sync `user.profile.small_group` only when all of these are true:
- the approved membership is moving through the normal `requested` to `active` approval flow
- the approved membership is active
- the approved membership is primary
- the approved `ChurchStructureUnit` maps to exactly one active legacy `SmallGroup`

When those conditions are met, set `user.profile.small_group` to the mapped legacy `SmallGroup`.

This preserves existing runtime behavior because `/studies/`, reading progress, `ServiceEvent`, and related consumers already read `Profile.small_group`. CS-H.7E should not switch those consumers to membership.

## 4. No Sync Cases

Do not sync `Profile.small_group` when:
- the approved unit has no legacy `SmallGroup` mapping
- the approved unit maps to multiple legacy small groups
- the mapped legacy `SmallGroup` is inactive
- the membership user already has an active primary membership conflict
- the membership is not primary
- the action is not the normal `requested` to `active` approval flow

Reject, blocked approval, cancellation, needs-clarification, manual edits, backfill, signup capture, and consumer migration should not update `Profile.small_group` as part of CS-H.7E.

## 5. Conflict and Transfer Rule

V1 rule: if the user already has `Profile.small_group` set to a different small group than the mapped group, approval may update it only when staff explicitly approve the request.

Because CS-H.7D approval already requires staff action, this may be acceptable for V1. The implementation should still make the consequence visible: approving this mapped request may change the user's current legacy small group and therefore affect current runtime visibility.

Future implementation should include a warning message and tests for this transfer case. The warning should be shown before or during approval when the mapped group differs from the user's current `Profile.small_group`.

## 6. Tests Required Later

Future CS-H.7E implementation tests should cover:
- mapped unit approval updates `Profile.small_group`
- unmapped unit approval does not update `Profile.small_group`
- inactive legacy group does not sync
- active approved membership visibility changes through `Profile.small_group` only
- `/studies/` behavior is affected only because `Profile.small_group` changed
- `ServiceEvent` behavior is affected only because `Profile.small_group` changed
- reject does not sync
- blocked approval does not sync
- requested membership grants no visibility before approval
- different existing `Profile.small_group` requires staff-visible warning coverage

Do not run tests as part of this planning-only task.

## 7. Risks

Primary risks:
- accidental visibility grant
- wrong legacy mapping
- data drift between `ChurchStructureMembership` and `Profile.small_group`
- staff misunderstanding of approval consequences
- rollback difficulty after a legacy small-group transfer

Mitigations should include exact mapping checks, an active legacy group requirement, visible staff warning copy for transfers, and focused tests around no-sync cases.

## 8. Recommendation

Implement CS-H.7E only after confirming this product behavior is desired:

Approval to a mapped small-group unit should immediately make the user belong to that legacy small group in the current runtime.

Until that decision is confirmed, CS-H.7D's current behavior should remain unchanged: approval updates `ChurchStructureMembership` only, and `Profile.small_group` remains the runtime source for `/studies/`, reading progress, `ServiceEvent`, and related behavior.
