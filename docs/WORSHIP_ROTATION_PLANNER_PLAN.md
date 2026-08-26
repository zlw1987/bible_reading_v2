# Worship Rotation Planner V1 Contract

Status: `MO-S.6D-1D-D-0A` docs-only architecture gate,
`MO-S.6D-1D-D-1A` read-only proposal/preview runtime,
`MO-S.6D-1D-D-1A-FU1` cycle-closed tail refinement, and the docs-only
`MO-S.6D-1D-D-1B-A0` SQLite optimistic scheduling-concurrency decision are
complete. `MO-S.6D-1D-D-1B-A1` Scheduling Revision Foundation and
`MO-S.6D-1D-D-1B-B` optimistic batch confirmation/shared audit are also
implemented. Docs-only `NOTIFY.1G-0A` closes the notification contract and
implemented `NOTIFY.1G` consumes the shared batch identity only after all
changed-event audits succeed. The contextual planner route builds an explicit exact-event
chain, projects the deterministic shift and privacy-limited downstream impact,
and produces a 30-minute user-bound signed normalized proposal without writing
state; an explicit confirm action may then apply that exact proposal atomically.
The attempted `MO-S.6D-1D-D-1B-A` row-lock closure correctly stopped without
changes because both local and GoDaddy deployment settings use SQLite and
`connection.features.has_select_for_update` is false. Runtime scheduling-
revision foundation supplies the target SQLite concurrency boundary and `1B-B`
consumes it. No planner model, notification, session proposal, temp file, or
BatchRun schema was added. Preview remains zero-write; confirmation changes only
selected-event Worship anchors and scheduling revisions plus shared-operation
per-changed-event audit rows.

This document owns the batch-planner contract. The broader Worship invariants
remain canonical in
[`WORSHIP_ROTATION_GOVERNANCE_PLAN.md`](WORSHIP_ROTATION_GOVERNANCE_PLAN.md).

## 1. Product boundary and repository decision

The implemented exact-event workflow already provides:

- `can_change_worship_team(user, event)` for narrow per-event authority;
- `/events/worship-planning/` for contextual upcoming-event reachability;
- `/events/<id>/worship-team/` for an atomic, stale-checked, exact-event
  selector;
- canonical applicable-pool, eligible-candidate, and ownership-consistency
  facts from `ministry.services.worship_governance`; and
- one same-transaction Django `LogEntry` for an actual selected-team change.

V1 must not duplicate that mature mutation path merely to make the planner look
symmetrical. The canonical separation is:

1. **Change one Sunday only:** use the existing exact-event selector.
2. **Insert / Shift Later Worship Teams:** use the implemented Worship Rotation
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
- At preview and again after the implemented confirmation CAS write barrier, every
  event whose selected team would actually change must pass
  `can_change_worship_team` for the current user.
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
- expected `scheduling_revision` from implemented `1B-A1`;
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

## 12. SQLite optimistic scheduling-concurrency contract

### Why the former row-lock contract stopped

`MO-S.6D-1D-D-1B-A` re-inventoried the supported downstream and required-team
write paths, then stopped without code or documentation changes when repository
truth proved that both `config.settings` and `config.settings_godaddy` use
SQLite. Django reports `has_select_for_update=False`; the existing
`select_for_update()` calls therefore provide no actual target-side
`ServiceEvent` row lock.

The implemented `MO-S.6D-1D-B/FU1` model/domain validation, Worship assignment
identity immutability, atomic boundaries, deterministic ordering code, and
member-confirmation revalidation remain useful. On SQLite, however, they must
not be described as a strict ServiceEvent row-lock serialization guarantee.
Prior SQLite tests proved code paths and rollback decisions, not parallel row
locking. This is a concurrency-contract correction, not evidence of corrupt
stored scheduling data.

### One event-owned revision is sufficient

`MO-S.6D-1D-D-1B-A0` selected one additive field, implemented by `1B-A1`:

```text
ServiceEvent.scheduling_revision
    PositiveBigIntegerField(default=0, editable=False)
```

Migration `events/0010_serviceevent_scheduling_revision.py` adds only this
field, with no data operation. It is a monotonic internal concurrency token
for operational scheduling truth, not user-visible state, audit history,
`updated_at` replacement, or a general CMS lost-update version. Existing rows
may safely start at zero through one normal schema migration with no data
operation. A separate index is unnecessary because CAS addresses rows by
primary key. No BatchRun, assignment version, required-team version, lock
table, or EventScheduleState model is needed.

Every planner-fingerprinted supported mutation belongs to one exact event or,
for ordinary downstream retargeting, the union of the old and new events.
Deleting the `ServiceEvent` itself needs no tombstone or revision advance:
future CAS cannot find that event and fails stale. This makes one event-owned
revision sufficient for the supported V1 boundary.

### Writes that advance the revision

Implemented `1B-A1` advances the affected event revision in the same atomic
transaction before final validation and mutation for:

- a governed Worship Team selection change;
- an existing ServiceEvent edit affecting the event fingerprint, including
  status/lifecycle changes;
- supported audience replacement and required-team add/remove/replacement;
- creation of a current `TeamAssignment` (`scheduled`, `prepared`, or
  `confirmed`), and deletion of a current assignment;
- any current assignment tuple change in event, team, or current status;
- transitions between current and cancelled/completed history in either
  direction, including cancellation, completion, and reactivation;
- the parent status change to `confirmed` caused by final member confirmation;
- the retained Lighting pilot when it creates or changes fingerprinted
  assignment truth; and
- supported Admin create/edit/status/retarget/object-delete/bulk-delete and
  MinistryTeam deletion cascades affecting current assignments.

A current ordinary downstream retarget from Event A to Event B advances both
surviving events once, in ascending event-ID order, in the same transaction.
The existing Worship event/team identity immutability remains unchanged.
Creating a brand-new event may retain its initial revision zero because its
initial audience/required-team/assignment setup precedes any possible preview;
later scheduling changes advance it normally.

Pure member-roster edits, assignment notes, `TeamAssignmentMember.confirmed_at`,
and confirmation-note detail do not advance the revision solely for planner
staleness. If the same operation changes the parent assignment's fingerprinted
status, that parent transition does advance it. A1 uses narrowly
scoped saves/reloads for these non-revision writes so a stale full-row save
cannot overwrite fingerprinted current truth. A conservative bump may remain
for a supported direct full `TeamAssignment.save()` whose intent cannot be
proved safely, but the normal forms/services and the Lighting notes-only update
should avoid needless proposal staleness.

### Required-team, Admin, delete, and cascade coverage

Current single-event create/edit and recurring creation already save/create
the owning event before `required_teams.set()` inside one atomic workflow.
ServiceEvent Admin saves the parent before its required-team and audience
inline formsets inside Admin's atomic change transaction. A1 makes the
event-owned revision advance the first scheduling write for existing-event
replacement, including an inline-only change; new-event related rows remain
part of initial creation.

There is no normal application TeamAssignment delete route. A1 covers
supported direct model delete, TeamAssignment Admin object delete, and Admin
bulk delete explicitly. The default Admin bulk action calls
`QuerySet.delete()` and therefore needs a bounded `delete_queryset()` path that
collects distinct current-assignment event IDs, advances them deterministically,
then deletes in the same transaction. MinistryTeam Admin/model deletion must
likewise collect and advance surviving event IDs before its assignment cascade;
required-team links already use `PROTECT` and are not silently cascaded by a
team deletion. ServiceEvent deletion needs no advance because the CAS target
itself disappears. Arbitrary shell/queryset deletion, bulk ORM writes, and raw
SQL remain outside the supported-write claim.

### Ordinary supported mutation barrier

The implemented reusable A1 helper/service contract is:

1. enter `transaction.atomic()`;
2. establish the affected old/proposed event IDs from the persisted baseline
   and requested mutation;
3. use database `F()` updates, never Python read-plus-one, to advance affected
   revisions in ascending ID order; the first actual update establishes the
   SQLite writer boundary;
4. reload current events and assignment rows, and fail stale/roll back if their
   identity no longer matches the pre-barrier baseline;
5. reauthorize and validate current domain truth, including the stronger
   Worship guard; and
6. apply the mutation and commit once.

If validation or any later write fails, revision increments and the mutation
roll back together. For an ordinary downstream retarget, a stale persisted
event discovered after the first barrier must fail/roll back and retry from a
fresh baseline rather than acquiring another affected event in reverse order.
Normal form, Team Schedule, Admin, cancellation/completion/reactivation,
member-confirmation parent status, and Lighting paths must converge on this
contract without changing their authority, notifications, or lifecycle rules.

### Implemented `1B-B` confirmation CAS

Preview includes each event's expected `scheduling_revision` in the signed
semantic payload. Implemented confirmation is:

1. decode and shape-check the signed payload before mutation logic;
2. enter `transaction.atomic()` with no scheduling/governance reads before the
   CAS claims;
3. in ascending event-ID order execute an atomic conditional update equivalent
   to:

   ```sql
   UPDATE events_serviceevent
      SET scheduling_revision = scheduling_revision + 1
    WHERE id = :event_id
      AND scheduling_revision = :expected_revision;
   ```

4. require exactly one affected row for every selected event; zero means
   missing/stale and rolls back the whole batch;
5. after the first successful CAS has established the SQLite write boundary,
   reload all events and recompute the exact chain, authority, governance,
   current-Worship ownership, and downstream/required-team fingerprints;
6. reject and roll back on any mismatch or conflict;
7. save only changed Worship Team selections without a second revision bump;
8. write one existing-style `LogEntry` per changed event, all sharing
   the operation ID; and
9. commit once.

Every selected context event, including a no-op row, receives the successful
CAS revision advance. Its Worship Team remains unchanged and it writes no
change `LogEntry`, but it participated in the confirmed concurrency boundary.
This also makes replay of the old signed proposal stale. A later failed CAS,
revalidation, anchor save, or audit write rolls back all earlier CAS advances.

### SQLite guarantee, limits, and test gate

The configured backend uses SQLite rollback-journal `delete` mode, Django's
default deferred `BEGIN`, no explicit transaction mode, and the default
5-second busy timeout. A disposable two-connection file-backed experiment for
A0 proved that the first successful revision CAS establishes SQLite's single-
writer boundary: a second connection could not update even a different event,
rollback restored the claimed revision, an old expected revision updated zero
rows, and a later failed batch claim rolled back the earlier successful claim.

The bounded target guarantee is therefore optimistic revision plus SQLite
write-transaction serialization plus current-truth recomputation for supported
application writes. It is database-wide writer exclusion, not a row-level
lock. Readers may continue. A competing writer may wait or receive
`database is locked`; A1 and B keep transactions short and render retry/error
without false success. Configuration/authority changes committed before the
first CAS are caught by recomputation; after that CAS, SQLite prevents another
database writer from committing through the confirmation window.

A1 includes a real two-connection, file-backed
SQLite concurrency test—not an in-memory database or ordinary `TestCase`—that
proves stale CAS, cross-event writer exclusion after the barrier, rollback of
revision claims, no partial batch commit, and safe retry/error behavior under
the configured journal/timeout behavior. Target-environment parity must be
checked separately. This does not certify general SQLite scalability.

The revision remains useful after a future PostgreSQL/MySQL migration as the
signed stale-proposal token. A row-locking backend may combine revision CAS
with `select_for_update()`, but must re-audit concurrent global governance/path/
role mutations because it will not inherit SQLite's database-wide writer
exclusion. No backend migration is authorized here.

## 13. Implemented `1B-B` audit and schema decision

V1 does not need a durable batch model.

Every actual event change in `1B-B` uses the established `LogEntry`
shape and adds:

```text
operation_id=<same UUID for every changed row>
old_team_id=<id or None>; old_team=<display>
new_team_id=<id or None>; new_team=<display>
```

`LogEntry.user_id`, object identity, timestamp, and shared operation ID are
sufficient for limited-trial diagnosis of who shifted which exact events and
for the docs-complete `NOTIFY.1G-0A` contract to select one stable committed-
batch dedupe identity, `ministry:worship_rotation:<operation_id>`. The future
recipient-specific summary contains only qualifying changed events for that
recipient. Those actual writes and logs remain in the same transaction.

This does not provide one-click rollback, durable preview retention, workflow
recovery, a unique/query-optimized batch history table, or a batch-history UI.
If any of those becomes mandatory, reevaluate a `BatchRun`-style schema rather
than overstating `LogEntry`.

## 14. User workflow and bilingual copy

The existing contextual Worship Planning page receives a contextual
`Rotation Planner / 敬拜轮值规划` link. V1 adds no primary/global navigation
item.

The full contract workflow is implemented below. Steps 1 through 5 are the
read-only preview; step 6 is the explicit `1B-B` confirmation:

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
  normalized proposal/fingerprint/signing service reused by `1B-B`.
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

### `MO-S.6D-1D-D-1B-A0` — SQLite optimistic contract — DOCS COMPLETE

- Records that attempted row-lock closure `1B-A` stopped without changes
  because target SQLite has no `select_for_update()` row-lock semantics.
- Selects one event-owned scheduling revision, the exact supported-write bump
  boundary, SQLite first-write barrier, future CAS algorithm, deletion/cascade
  treatment, and required file-backed concurrency-test gate.
- Adds no field, migration, helper, confirmation action, audit, notification,
  or data change.

### `MO-S.6D-1D-D-1B-A1` — Scheduling Revision Foundation — IMPLEMENTED

- Adds `ServiceEvent.scheduling_revision` and additive migration `events/0010`.
- Adds typed atomic increment/CAS helpers and retrofits supported ServiceEvent,
  TeamAssignment, required-team/audience, Admin/delete/cascade, confirmation-
  parent-status, and Lighting paths.
- Corrects the runtime SQLite concurrency boundary while preserving authority,
  notifications, lifecycle, and Worship identity rules.
- Adds real two-connection file-backed SQLite coverage for stale CAS, writer
  exclusion, rollback restoration, busy retry, and atomic multi-event failure.
- Planner proposal contract version 3 fingerprints each event revision and
  rejects missing/old tokens. `1B-B` consumes this boundary; A1 remains the
  scheduling-revision foundation rather than owning confirmation behavior.

### `MO-S.6D-1D-D-1B-B` — Optimistic batch confirmation and audit — IMPLEMENTED

- Reuses the exact `1A` proposal/revalidation service; the view does not
  reimplement shift logic.
- Adds a dedicated POST-only signed confirmation route, pure payload extraction
  before the transaction, ascending expected-revision CAS as the first
  scheduling/governance database access, full current-truth recomputation,
  all-or-nothing normal anchor saves, and one `LogEntry` per changed event with
  the shared signed operation ID.
- Every selected event advances revision exactly once on success; true no-op
  events write no anchor or audit row. Replay, stale/busy state, malformed or
  expired tokens, lost authority, governance/assignment conflicts, displaced
  tails, save failures, and audit failures fail closed without partial success.
- Focused tests cover CAS order and first-access discipline, target-like
  file-backed two-connection behavior, rollback/replay, tail protection, audit
  semantics, privacy, and zero assignment/audience/roster/notification writes.
- Rendered English desktop and Chinese mobile QA covers confirmable, blocked,
  success, replay-safe, responsive, and narrow-authority/privacy states.

`NOTIFY.1G-0A` is docs complete and `NOTIFY.1G` is implemented as the separate
ministry-owned producer integration after successful `1B-B` changed-event
audits. It does not alter `1A`, `1B-A1`, or `1B-B` CAS/revalidation semantics.

## 17. Decisions and remaining gates

This gate plus implemented `1A-FU1`, docs-only `1B-A0`, implemented `1B-A1`,
and implemented `1B-B` close the V1 planner confirmation path:
exact explicit weekly published-future Sunday
events, maximum 53, no interior blank, terminal blank or exact-ID cycle-closed
tail preservation, no arbitrary tail loss, per-destination canonical
eligibility, per-event existing authority, changed-row Worship-assignment
blocker, narrow roster-free downstream impact, 30-minute user-bound signed
proposal, one event-owned scheduling revision, SQLite optimistic CAS/write-
barrier semantics, and no BatchRun schema.

The A1 prerequisite and B confirmation slice are closed: the migration,
inventoried supported paths, required file-backed SQLite concurrency tests,
optimistic confirmation, and shared audit are implemented. Any newly discovered
supported bulk/cascade path outside the one-event revision contract remains a
stop condition; the downstream stale guarantee must not be weakened silently.
