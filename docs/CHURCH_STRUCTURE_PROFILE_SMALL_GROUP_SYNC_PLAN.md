# Church Structure Profile.small_group Sync Plan

> **Status note (superseded):** this CS-H.7E transition plan predates
> PROFILE-SG-FIELD-RETIRE.1A. `Profile.small_group` was later removed, and the
> approval-sync behavior described here is historical only. Current approved
> migrated runtime paths use active primary `ChurchStructureMembership` or
> structure/audience rows as documented in
> `docs/LEGACY_PROFILE_SMALL_GROUP_CONSUMER_INVENTORY.md`.

## 1. Purpose

CS-H.7E implemented transition behavior for syncing `Profile.small_group` when staff approved a mapped small-group `ChurchStructureMembership`.

Historical/superseded: sync was needed during the transition because then-current runtime consumers still read the legacy `Profile.small_group` field. `/studies/`, reading progress, `ServiceEvent`, and related behavior did not yet use `ChurchStructureMembership`, so approving membership alone did not change what the user could see or do in those flows.

This implementation did not change models, migrations, signup behavior, consumer queries, or consumer source of truth at that time. Historical runtime visibility could change only because `Profile.small_group` changed.

## 2. Historical Behavior

CS-H.7D approval updates the requested `ChurchStructureMembership` record to an active membership.

Historical CS-H.7D approval:
- sets the membership active
- sets the membership primary
- records approval metadata
- blocks approval when the user already has a current active primary membership
- does not change `Profile.small_group`

Therefore, approved membership by itself did not affect then-current `/studies/`, reading progress, `ServiceEvent`, or related visibility. Those consumers depended on `Profile.small_group` at that historical point.

## 3. Historical Implemented CS-H.7E Behavior

On approve, CS-H.7E synced `user.profile.small_group` only when all of these were true:
- the approved membership is moving through the normal `requested` to `active` approval flow
- the approved membership is active
- the approved membership is primary
- the approved `ChurchStructureUnit` maps to exactly one active legacy `SmallGroup`

When those conditions were met, CS-H.7E set `user.profile.small_group` to the mapped legacy `SmallGroup`.

At that time, this preserved existing runtime behavior because `/studies/`, reading progress, `ServiceEvent`, and related consumers already read `Profile.small_group`. CS-H.7E did not switch those consumers to membership; later consumer and field-retirement slices retired that bridge separately.

## 4. No Sync Cases

Historical CS-H.7E did not sync `Profile.small_group` when:
- the approved unit has no legacy `SmallGroup` mapping
- the approved unit maps to multiple legacy small groups
- the mapped legacy `SmallGroup` is inactive
- the membership user already has an active primary membership conflict
- the membership is not primary
- the action is not the normal `requested` to `active` approval flow

Reject, blocked approval, cancellation, needs-clarification, manual edits, backfill, signup capture, and consumer migration did not update `Profile.small_group` as part of CS-H.7E.

## 5. Conflict and Transfer Rule

V1 rule: if the user already has `Profile.small_group` set to a different small group than the mapped group, approval may update it only when staff explicitly approve the request.

Because CS-H.7D approval already required staff action, this was acceptable for the transition. The implementation made the consequence visible: approving this mapped request could change the user's then-current legacy small group and therefore affect then-current runtime visibility.

Historical implementation guidance included a warning message and tests for this transfer case. The warning was shown before or during approval when the mapped group differed from the user's then-current `Profile.small_group`.

## 6. Tests Added

CS-H.7E transition-era implementation tests covered:
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

## 7. Risks

Primary risks:
- accidental visibility grant
- wrong legacy mapping
- data drift between `ChurchStructureMembership` and `Profile.small_group`
- staff misunderstanding of approval consequences
- rollback difficulty after a legacy small-group transfer

Mitigations should include exact mapping checks, an active legacy group requirement, visible staff warning copy for transfers, and focused tests around no-sync cases.

## 8. Completion

CS-H.7E was implemented for the confirmed transition behavior:

At that time, approval to a mapped small-group unit immediately made the user belong to that legacy small group in the then-current runtime.

Historical/superseded: consumers still read `Profile.small_group` during CS-H.7E. CS-H.7E did not add signup capture, audience filtering, or consumer migration, and the approval-sync bridge was later retired when `Profile.small_group` was removed.
