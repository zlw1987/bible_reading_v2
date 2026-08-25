# Worship Rotation Planner V1 Contract

Status: `MO-S.6D-1D-D-0A` docs-only architecture gate and
`MO-S.6D-1D-D-1A` read-only proposal/preview runtime and
`MO-S.6D-1D-D-1A-FU1` cycle-closed tail refinement are complete. The
contextual planner route now builds an explicit exact-event chain, projects
the deterministic shift and privacy-limited downstream impact, and produces a
30-minute user-bound signed normalized proposal without writing state.
`MO-S.6D-1D-D-1B` locked confirmation/audit remains unimplemented and blocked
on the downstream event-first serialization closure below. No planner model,
migration, dependency, confirmation write, audit write, notification, session
proposal, temp file, or data change is implemented by `1A`.

This document owns the batch-planner contract. The broader Worship invariants
remain canonical in
[`WORSHIP_ROTATION_GOVERNANCE_PLAN.md`](WORSHIP_ROTATION_GOVERNANCE_PLAN.md).

## 1. Product boundary and repository decision

The implemented exact-event workflow already provides:

- `can_change_worship_team(user, event)` for narrow per-event authority;
- `/events/worship-planning/` for contextual upcoming-event reachability;
- `/events/<id>/worship-team/` for a locked, stale-checked, exact-event
  selector;
- canonical applicable-pool, eligible-candidate, and ownership-consistency
  facts from `ministry.services.worship_governance`; and
- one same-transaction Django `LogEntry` for an actual selected-team change.

V1 must not duplicate that mature mutation path merely to make the planner look
symmetrical. The canonical separation is:

1. **Change one Sunday only:** use the existing exact-event selector.
2. **Insert / Shift Later Worship Teams:** use the future Worship Rotation
   Planner over an explicitly reviewed bounded event chain.

The planner edits explicit `ServiceEvent.rotation_anchor_team` values. It does
not store, infer, or perpetuate a C1/C2/C3/A rule and is not an automatic
scheduler, recurrence generator, spreadsheet rules engine, or second schedule
database.

## 2. Exact event-chain contract

V1 operates on an ordered list of exact existing `ServiceEvent` IDs. Start and
end controls are UI conveniences; the normalized proposal contains the exact
ordered IDs and the preview must show every selected event.

A chain is eligible only when all of these are true:

- it contains 2 through 53 distinct events, inclusive;
- every event has `event_type=sunday_service`;
- every event is `published` (draft, completed, and cancelled rows are
  excluded);
- every event starts in the future at preview and confirmation time;
- events are in strict `(start_datetime, id)` order;
- there is exactly one selected event on each represented local Sunday;
- represented local Sundays are seven days apart, so a missing interior Sunday
  is a blocking gap rather than an invented event; and
- every event was explicitly reviewed as part of the chain.

The repository has no canonical ServiceEvent series/profile key. V1 therefore
must not infer one from title, location, Host / Language, audience, database ID,
or a Worship Team name. Parallel services are handled by explicit event choice.
The preview shows date/time, title, location, and Host / Language as review
context, but those display fields do not create a hidden profile rule. Their
normal `ServiceEvent.updated_at` change still stales a proposal.

If an operator needs to cross an absent Sunday, select different bounds after
the missing event is created through the authorized ServiceEvent workflow. The
planner never creates an event and never silently skips a calendar gap.

## 3. Deterministic insert-and-shift operation

For ordered events:

```text
E0, E1, E2, ... En
```

with stored before selections:

```text
T0, T1, T2, ... Tn
```

and the operator-selected inserted team `S`:

```text
proposed(E0) = S
proposed(E1) = T0
proposed(E2) = T1
...
proposed(En) = T(n-1)
displaced tail = Tn
```

The algorithm uses stored identities only. It performs no fuzzy/name matching,
rotation inference, or candidate substitution. A row where proposed and before
team IDs are equal is a no-op: it is shown for chain context, saved nowhere,
and receives no change audit entry.

The inserted team must be a non-null current eligible Worship candidate for
`E0`. Every non-terminal before value must be a non-null valid eligible
selection for its source event. An invalid or inactive stored selection blocks
the proposal.

### Blank and gap handling

An interior blank in `E0` through `E(n-1)` blocks the proposal. V1 never jumps
over a blank to find a later team.

A blank is allowed only on the final event as an explicit landing slot. In
that case `Tn` is blank, `T(n-1)` moves into `En`, and there is no displaced
selected-team value.

## 4. Tail-preservation decision

The docs-only `0A` contract conservatively allowed only a terminal blank. The
implemented `1A` preview then demonstrated a second deterministic no-loss
case before any `1B` confirmation writes existed: the non-null displaced tail
can be the exact same `MinistryTeam` identity as the explicitly inserted team.
`1A-FU1` therefore defines three typed tail outcomes:

1. `terminal_blank`: the displaced tail is null. This is a safe landing slot.
2. `cycle_closed`: the displaced tail is non-null and its primary key exactly
   equals the inserted team's primary key. The selected-range team multiset is
   preserved, so this tail adds no blocker.
3. `displaced`: the displaced tail is non-null and its primary key differs from
   the inserted team's primary key. `DISPLACED_TAIL` remains a blocker.

Terminal-blank and cycle-closed proposals may be confirmable when every other
rule passes. A true displaced tail remains reviewable but not confirmable.

The preview always shows:

```text
Displaced after selected range: Tn
范围结束后被顺延出的团队：Tn
```

For a true displaced tail, the operator must extend the chain to an existing
later Sunday and regenerate until the final event is a blank landing slot or
the exact inserted team closes the selected-range cycle. No event is created
to make such a slot.

Cycle closure uses only exact `MinistryTeam` identity. Team names, display
labels, A/C1/C2/C3 conventions, pool position, inferred order, fuzzy matching,
and historical frequency are irrelevant. This does not store or infer a
recurring rotation rule, and it does not approve arbitrary tail drop.

An explicit "accept ending the shift here" / tail-drop option is deferred. It
would be a destructive semantic and requires a separate product decision,
copy, audit, and test slice. Merely displaying a non-null tail does not make
its loss acceptable in V1.

## 5. Per-event governance and destination eligibility

Preview and confirmation recompute the canonical governance facts independently
for every event.

For each destination:

```text
proposed team
    must be in eligible_worship_team_candidates(destination event)
```

This includes `S` for `E0` and each shifted `T(i-1)` for `Ei`. Eligibility at
the source does not imply eligibility at the destination. A CM team shifted
into an EM-only event, an inactive team, a malformed primary path, an
inapplicable pool, or a changed candidate union blocks the whole proposal.

Multiple applicable pools remain an intentional candidate union. Ambiguous,
inactive, broken, or cyclic pool/path configuration continues to fail closed
through the existing governance service. No team is resolved from a name,
code, previous rotation position, or database-ID convention.

## 6. Audience and combined-service boundary

The planner changes only selected Worship Teams. It never changes:

- ServiceEvent audience, status, type, title, time, location, or Host /
  Language;
- required teams or event-planner assignments;
- `TeamAssignment`, `TeamAssignmentMember`, rosters, notes, confirmation, or
  assignment lifecycle; or
- Church Structure, Ministry Structure, membership, roles, or serving.

When a Sunday becomes a Whole-Church combined service, an authorized full
ServiceEvent manager must first update its audience through the existing event
workflow. Only the resulting stored active audience rows determine applicable
pools and destination candidates. Selecting Team A never implies or writes a
Whole-Church audience.

## 7. Authorization contract

The batch invents no authority. It reuses
`can_change_worship_team(user, event)` exactly.

- The preview selection surface remains bounded to events reachable through
  the existing Worship Planning authority predicate; this avoids inventing a
  separate batch-read permission.
- At preview and again under lock at confirmation, every event whose selected
  team would actually change must pass `can_change_worship_team` for the
  current user.
- If one changed row is unauthorized, the whole proposal/confirmation is
  blocked. No row is silently omitted.
- A no-op row has no mutation and no change audit requirement. It still must
  have valid source/target governance truth and, in V1, comes from the same
  existing authorized planning surface.
- Full-event managers, exact-event planners, and active date-valid Leads or
  Coordinators of applicable pools keep their existing exact per-event
  semantics. Authority on the first event never flows to later events.

The signed proposal is bound to the previewing active user ID. Confirmation by
another user is rejected even if that user would independently be authorized;
that user must generate their own current proposal.

## 8. Current Worship-assignment blocker

For every row whose selected team would change, any current Worship assignment
returned by canonical governance blocks that row and therefore the entire
batch. Current means `scheduled`, `confirmed`, or `prepared`, including an
empty assignment row with status or notes but no members.

The planner never moves, retags, clones, cancels, completes, deletes, or edits
an assignment or member. It never treats an assignment on the proposed team as
permission to repair the event silently.

A true no-op row may remain informational with one current assignment only
when the canonical ownership state is exactly `CONSISTENT`. Because the row is
not mutated, that consistent assignment does not block. Invalid, off-team,
out-of-scope, multiple, or duplicate ownership blocks the chain even on a
no-op row because its source truth is not safe to propagate.

## 9. Downstream operational-impact projection

Non-Worship assignments do not block the shift and are never rewritten, but
their operational existence is review impact.

The preview may expose to a full event manager, exact-event planner, or
applicable-pool Lead/Coordinator only this planner-specific projection for each
downstream team:

- localized team display name;
- required or additional participation;
- no current assignment, one current assignment, or duplicate current
  assignments; and
- the coarse current assignment status (`scheduled`, `confirmed`, or
  `prepared`).

It must not expose member names or counts, notes, contacts, confirmation
details, audience internals, profile fields, or links/controls that imply
general assignment-detail permission.

The Sunday Board and assignment-coverage services establish the relevant
required/current-team concepts, but their existing projections include member
display names and Board-specific access/actions. V1 should therefore implement
a smaller planner-specific read-only projection while reusing the canonical
status constants and required/additional definitions. This preview contract
does not widen the Sunday Board, Team Schedule, or TeamAssignment detail
permissions.

## 10. Signed no-schema proposal

There is no existing repository-wide signed proposal or safe batch
preview/confirm framework. The recurring-event preview reuses one POST without
an expiring artifact, and Bible Study generation recomputes and creates rows
individually. Neither is the planner's all-or-nothing confirmation pattern.

V1 uses Django's built-in signing without a new dependency or schema:

```text
side-effect-free normalized proposal
-> django.core.signing.dumps(..., compress=True, dedicated salt)
-> explicit confirmation
-> django.core.signing.loads(..., max_age=1800)
```

The 30-minute maximum age is enforced at confirmation. The proposal is signed,
not encrypted. It contains no display names, roster/contact data, notes, or
other private content.

The normalized payload contains:

- contract version and operation type `insert_shift_later`;
- one random UUID `operation_id`, generated at preview and preserved through
  confirmation;
- generation timestamp and previewing user ID;
- ordered event IDs;
- inserted team ID;
- before and proposed team IDs per event;
- displaced-tail team ID or null;
- normalized tail resolution (`terminal_blank`, `cycle_closed`, or
  `displaced`), validated against the inserted and displaced-tail IDs;
- exact event, governance, current-Worship, and downstream-impact fingerprints
  defined below; and
- a dedicated signing salt/version.

Session storage adds tab/expiry/cleanup coupling, a temporary file adds hosting
and cleanup state, and a durable `BatchRun` adds schema/retention/privacy work.
None is needed for the bounded limited-trial contract. A durable run model is
deferred unless product later requires retained preview history, workflow
recovery, query-optimized batch history, or rollback state.

## 11. Exact stale/fingerprint contract

Fingerprints are sorted normalized semantic facts, hashed before inclusion
where useful. Confirmation recomputes them from current database truth; it does
not trust display values from the browser.

### Event fingerprint

For every selected event:

- event ID;
- `updated_at`;
- status and event type;
- start and end datetimes;
- stored before selected-team ID.

The broad `updated_at` intentionally makes title, time, location, Host /
Language, status, and other normal event edits require a fresh preview.

### Governance fingerprint

- sorted active audience unit IDs;
- sorted applicable `(pool_id, anchor_unit_id)` pairs;
- sorted eligible `(team_id, owning_pool_id)` pairs;
- selected-team eligibility; and
- canonical ownership-consistency state.

This fingerprints the normalized effect of active primary pool paths. A name or
other non-semantic display edit need not stale the proposal when the normalized
governance result is unchanged. Authority roles are not trusted from the
payload; current authority is always recomputed directly.

### Current Worship-assignment fingerprint

Sorted tuples of:

- assignment ID;
- team ID;
- owning pool ID;
- current status; and
- usable/applicable/eligible flags from canonical governance.

No member, note, contact, or confirmation data participates.

### Downstream-impact fingerprint

- sorted required downstream team IDs; and
- sorted current downstream `(assignment_id, team_id, status)` tuples.

Because preview promises this operational impact, adding, removing,
retargeting, duplicating, or changing the current status of a downstream
assignment stales the whole proposal. Member-roster changes and notes do not
stale it because the preview neither displays nor depends on them.

Any fingerprint difference rejects the entire confirmation and requires a new
preview. No individual stale row is skipped.

## 12. Confirmation transaction and lock order

The `1B` algorithm is:

1. Decode the signed payload with the dedicated salt and 30-minute `max_age`;
   verify version, operation, UUID, user binding, uniqueness, bounds, and
   normalized shape before entering mutation logic.
2. Enter `transaction.atomic()`.
3. Lock every selected `ServiceEvent`, including no-op context rows, in
   ascending primary-key order. Semantic shift order remains
   `(start_datetime, id)` and is checked separately.
4. Lock the current assignment rows for those events in deterministic
   `(service_event_id, id)` order after the event locks.
5. Reload and revalidate the exact chain/range contract.
6. Recompute the proposal from current before values, reauthorize every changed
   event with `can_change_worship_team`, and compare all fingerprints.
7. Recompute canonical per-destination candidate eligibility and all current
   Worship-assignment blockers/no-op consistency rules.
8. If any fact differs or conflicts, raise/reject and roll back the entire
   transaction.
9. Save only actually changed `rotation_anchor_team` values through normal
   per-event `ServiceEvent.save(update_fields=["rotation_anchor_team",
   "updated_at"])`; do not use `bulk_update` or `QuerySet.update`.
10. Write one existing-style `LogEntry` for every changed event with the same
    operation ID and explicit old/new team IDs and names. An audit failure
    rolls back the selected-team writes. No-op rows write no entry.
11. Commit once. No assignment, audience, required-team, planner, roster,
    notification, or other row is created or changed.

### Required downstream serialization closure for `1B`

Current Worship assignment saves already serialize on the governing
ServiceEvent row, and member confirmation follows
`ServiceEvent -> TeamAssignment -> TeamAssignmentMember`. Pure downstream
assignment create/edit/cancel/admin/direct-save paths deliberately do not
currently acquire that event lock.

Therefore locking events and existing assignment rows only inside the planner
is not enough to promise that a concurrent downstream insert/status change
cannot pass between validation and commit. Before `1B` may claim the
downstream-impact stale guarantee, the same slice must make all supported
current downstream `TeamAssignment` create/edit/status/delete paths that affect
the fingerprint serialize event-first on their ServiceEvent, or stop and adopt
an explicitly approved version/schema alternative. The no-schema V1 decision
is to extend event-first supported-write serialization in `1B`; it is not part
of read-only `1A`.

Raw SQL and future arbitrary bulk updates remain outside the application-level
claim and must not be introduced as supported assignment paths. SQLite tests
can prove lock ordering and atomic decisions, not production-backend parallel
row-lock behavior; target-backend concurrency verification remains required.

## 13. Audit and schema decision

V1 does not need a durable batch model.

Every actual event change uses the established `LogEntry` shape and adds:

```text
operation_id=<same UUID for every changed row>
old_team_id=<id or None>; old_team=<display>
new_team_id=<id or None>; new_team=<display>
```

`LogEntry.user_id`, object identity, timestamp, and shared operation ID are
sufficient for limited-trial diagnosis of who shifted which exact events and
for a later summarized-notification producer to use one stable committed-batch
identity. Actual writes and logs remain in the same transaction.

This does not provide one-click rollback, durable preview retention, workflow
recovery, a unique/query-optimized batch history table, or a batch-history UI.
If any of those becomes mandatory, reevaluate a `BatchRun`-style schema rather
than overstating `LogEntry`.

## 14. User workflow and bilingual copy

The existing contextual Worship Planning page receives a contextual
`Rotation Planner / 敬拜轮值规划` link. V1 adds no primary/global navigation
item.

The workflow is:

1. choose the starting Sunday;
2. choose the inserted/special Worship Team;
3. choose the bounded shift end and review the exact weekly event chain;
4. Generate Preview;
5. review before/after teams, blockers, downstream impact, no-op rows, and the
   displaced tail; and
6. Confirm Shift only when the preview is confirmable.

Scheduler-facing terms are:

| English | Chinese |
| --- | --- |
| Worship Team | 敬拜团队 |
| Shift later Worship Teams | 顺延后续敬拜团队 |
| Review required | 需要检查 |
| Displaced after range | 范围结束后被顺延出的团队 |
| Generate Preview | 生成预览 |
| Confirm Shift | 确认顺延 |

A cycle-closed preview is positive informational state, not a blocker: “Rotation
cycle closes within the selected range. No Worship Team is lost from this
shift.” / “本次顺延在所选范围内完成轮值闭合，没有敬拜团队被遗漏。” The displaced
tail identity remains visible for transparent review.

Do not call the operation Auto Rotate, Generate Rotation, or Smart Schedule.
Do not expose `rotation_anchor_team`, pool/path, fingerprint, or other
engineering terms to schedulers.

## 15. Example matrix

| Scenario | Preview result | Confirmation |
| --- | --- | --- |
| `C1, C2, C3, A`; insert `A` | `A, C1, C2, C3`; displaced tail `A` is visible and cycle-closed | Allowed if every other rule passes; exact team identities are preserved |
| Final landing event is blank | Prior last team moves into that exact existing event; displaced tail is blank | Allowed if every other rule passes |
| `C1, C2, C3`; insert `A` | `A, C1, C2`; displaced tail `C3` is visible | Blocked; this is a true displaced tail, not an accepted tail drop |
| Combined service | Audience was already changed to Whole Church; `A` is eligible for that event | Allowed only if every shifted team is eligible for its own destination |
| Audience mismatch | Shifted `C1` is not eligible for an EM-only destination | Whole proposal blocked |
| `C1, blank, C2` | Interior blank is visible; no jumping over it | Whole proposal blocked; choose a shorter/different chain |
| Changed row has a current `C2` Worship assignment | Empty or populated assignment is a current ownership row | Whole proposal blocked; no roster mutation |
| True no-op row has one consistent Worship assignment | Informational consistent state | Does not block by itself; writes/logs nothing |
| Required/additional AVL assignments exist | Team, required/additional role, assignment existence/duplicate, and coarse status shown | Review impact only; rows are not rewritten |
| Unauthorized middle changed event | Exact row identified as unauthorized without exposing private data | Whole proposal blocked at preview and confirmation |
| Event/audience/candidate/assignment truth changes after preview | Fingerprint differs | Whole confirmation rejected; regenerate |
| One LogEntry write fails | Transaction error | All event changes and audit rows roll back |

## 16. Runtime implementation split

### `MO-S.6D-1D-D-1A` — read-only proposal and preview — IMPLEMENTED

- `ministry.services.worship_rotation_planner` implements the side-effect-free
  normalized proposal/fingerprint/signing service reusable by `1B`.
- `/events/worship-planning/rotation/` provides the contextual exact-event and
  inserted-team form plus bilingual preview; parallel same-Sunday services
  remain separate explicit choices and are never auto-selected.
- The preview generates the signed, user-bound, expiring payload and projects
  the narrow downstream impact plus every blocker/tail state.
- GET and preview POST write nothing: no event, assignment, audit,
  notification, session, temp-file, or model row.
- Focused tests cover exact range/gaps, deterministic shift, source/destination eligibility,
  authorization, ownership/no-op rules, privacy, signing/expiry/tamper handling,
  and zero writes.

### `MO-S.6D-1D-D-1A-FU1` — cycle-closed tail refinement — IMPLEMENTED

- Keeps the preview read-only and changes only displaced-tail semantics.
- Adds the immutable typed `terminal_blank` / `cycle_closed` / `displaced`
  result and includes it in proposal contract version 2.
- Accepts a non-null tail only when its exact team ID equals the explicitly
  inserted team ID; decode validates the semantic against both IDs.
- Adds no rotation sequence, arbitrary tail drop, confirmation action, model,
  migration, permission, audit, notification, session, or file state.

### `MO-S.6D-1D-D-1B` — locked confirmation and audit

- Reuse the exact `1A` proposal/revalidation service; do not reimplement shift
  logic in the view.
- Complete the required supported downstream event-first serialization
  closure.
- Add signed confirmation, deterministic locks, full revalidation,
  all-or-nothing normal saves, and per-event `LogEntry` rows with the shared
  operation ID.
- Test stale/tampered/expired/unauthorized/conflicting rollback, lock order,
  tail protection, no-op audit behavior, audit failure rollback, idempotent
  replay rejection/no-op behavior, and zero assignment/audience/roster writes.

Notifications remain a later separately approved slice. They must not be added
to either `1A` or `1B`.

## 17. Decisions and remaining gates

This gate plus the implemented `1A-FU1` refinement closes the V1 product
decisions needed before `1B`: exact explicit weekly published-future Sunday
events, maximum 53, no interior blank, terminal blank or exact-ID cycle-closed
tail preservation, no arbitrary tail loss, per-destination canonical
eligibility, per-event existing authority, changed-row Worship-assignment
blocker, narrow roster-free downstream impact, 30-minute user-bound signed
proposal, and no BatchRun schema.

No remaining product decision blocks approval of `1A`. `1B` must still verify
the downstream supported-write serialization inventory and target-database lock
behavior during its repository-truth gate. If that closure cannot be made
safely within `1B`, stop before confirmation runtime and present either a
version/audit schema or a narrower impact-staleness promise for explicit product
decision.
