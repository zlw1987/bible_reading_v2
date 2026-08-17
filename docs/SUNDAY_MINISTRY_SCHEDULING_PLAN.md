# Sunday Ministry Scheduling Workflow & Import Plan

Status: current through implemented MO-S.6B Sunday Schedule Board V1. Later
MO-S.6 slices remain separately scoped and require explicit approval.

## 1. Purpose

The current Ministry Operations workflow can schedule one ministry team for a
`ServiceEvent`, but Sunday operations are coordinated as a wider matrix. The
Worship arrangement is normally planned first; Projection, Sound, Recording,
Video, and Lighting then plan their own people with that context in mind. The
church also uses an annual/master Google Sheet or Excel workbook as a compact
planning overview.

This plan defines a controlled path from that team-centric workflow toward a
Worship-led, database-backed Sunday operating view. It intentionally extends
the generic scheduling architecture in small slices. It does not approve a
new Worship assignment model, a spreadsheet replacement by unrestricted CRUD,
or a production import in this planning slice.

## 2. Current-state findings

### Existing domain objects

- `ServiceEvent` is the generic gathering/date-time record. It already has an
  event type including `sunday_service`, lifecycle status, audience-scope
  rows, and the nullable `rotation_anchor_team` foreign key to
  `MinistryTeam`.
- `rotation_anchor_team` can already represent a Worship rotation team such as
  Worship A, C1, C2, or C3 when those are configured as ordinary assignable
  `MinistryTeam` records. It is a scheduling hint only: it is not an
  assignment, required team, audience, visibility, permission, or coverage
  source.
- `ServiceEventRequiredTeam` says which teams are expected for an event. It
  does not create a `TeamAssignment`.
- `MinistryTeam` is generic and has descriptive hierarchy/taxonomy plus an
  explicit `is_assignable` gate. Team structure links are display/setup
  metadata and do not grant serving or permissions.
- `TeamMembership` is a candidate pool. A membership row is not serving.
- `TeamAssignment` is the actual event/team schedule row. It stores status,
  notes, creator, and timestamps.
- `TeamAssignmentMember` is the actual person-level serving row and stores
  confirmation state. This is what powers personal serving views.

### Existing scheduling and permissions

- The Team Schedule workspace is scoped to one selected team and an upcoming
  event window. It shows events where that team is required or already
  assigned, uses a server-locked event/team form, and updates the existing
  event/team assignment rather than duplicating it.
- Staff, superusers, and the global team-assignment manager capability may
  manage any team assignment. A team lead/coordinator may manage assignments
  for the exact team through an active, date-valid
  `MinistryTeamRoleAssignment`. `TeamMembership.role` and `can_lead` are not
  runtime scheduling authority.
- A person may view an assignment as its assigned active member or through the
  applicable team-management permission. Existing member confirmation is
  limited to that person's explicit `TeamAssignmentMember` row.
- Long-term ministry role assignments are a management/responsibility axis;
  they are not weekly serving rows and do not create `TeamAssignmentMember`
  records. Church Structure membership is belonging, not serving or
  scheduling authority.

### Existing coverage, suggestions, and surfaces

- Coverage compares required teams with actual assignments and active assigned
  members. It distinguishes assigned, assignment-without-people, unassigned,
  and additional assignment states, and can show member confirmation status.
- MO-S.5B copy-forward suggestions already use generic assignments. The anchor
  mode finds the most recent prior non-draft/non-cancelled same-event-type
  assignment for the same team and same `rotation_anchor_team`; the team mode
  uses same-event-type/team history without the anchor. Active members are
  proposed, confirmations are not copied, and opening the suggestion writes
  nothing. Explicit save is required.
- My Serving is the personal serving workspace for explicit
  `TeamAssignmentMember` rows and confirmation. Today is a selective agenda
  and action surface with compact serving reminders and manager attention; it
  is not a scheduling workspace. Church Calendar is a model-free, read-only
  aggregation surface and does not create or edit schedules.
- Notifications are directed, recipient-scoped records delivered through the
  Core notification port. The implemented ministry producer covers successful
  interactive TeamAssignment create/edit scheduling writes; it does not make
  notifications a schedule database or authorize imports/admin/direct ORM
  writes. Future board/import notifications require a separate producer slice.
- A narrow Lighting pilot CSV importer exists, but it is not the proposed
  annual Excel importer. It demonstrates the need for strict columns,
  sensitive-column rejection, dry-run capability, and generic model reuse;
  its current direct import behavior must not be copied into a production
  upload flow without the preview/confirmation gate defined below.

### Material gaps

MO-S.6B now provides the bounded cross-team Sunday matrix, exact-team cell
editability, and visible event-level Worship rotation context. The current
system still does not provide the richer Worship assignment/suggestion context
planned for MO-S.6C, a downstream review warning when Worship changes, or a
controlled `.xlsx` upload/parse/preview/confirm workflow. It also does not
prove that a team named C2 is semantically a Worship rotation anchor; that
remains configuration/data responsibility, not a hard-coded rule.

## 3. Real-world Sunday workflow

The intended operating sequence is:

1. Staff or an authorized Worship scheduler establishes the Sunday
   `ServiceEvent` and its Worship rotation anchor, if known.
2. Worship schedules its own `TeamAssignment` and explicit members.
3. Each downstream team opens the same Sunday context, reviews the current
   Worship anchor/roster and any historical suggestion, and schedules its own
   team assignment.
4. Each team owns its own members, status, notes, and confirmation workflow.
5. A later Worship change does not rewrite downstream assignments. It marks
   affected downstream rows for human review when the system can establish
   that the upstream context changed after the downstream row was last saved.
6. The board provides a shared operational overview, while the owning team
   surfaces remain the places where detailed edits and confirmations occur.

The board should preserve the useful row-oriented mental model:

| Sunday Service | Worship | Projection | Sound | Recording | Video | Lighting |
| --- | --- | --- | --- | --- | --- | --- |
| event/date | assignment summary | assignment summary | assignment summary | assignment summary | assignment summary | assignment summary |

This is a coordination view over canonical event/team assignment records, not
an unrestricted spreadsheet and not a second schedule database.

## 4. Product goals and non-goals

### Goals

- Give staff and authorized team leaders one operational Sunday view.
- Keep Worship context visible to downstream schedulers without making Worship
  a special assignment type.
- Make missing, empty, pending-confirmation, confirmed, and changed-context
  states understandable without fabricating assignments.
- Preserve team ownership: a Lighting leader edits Lighting, a Sound leader
  edits Sound, and broader authority is available only through existing
  capability semantics.
- Make historical pairings useful as reviewable suggestions and keep unusual
  Sundays, substitutions, and assignment differences first-class.
- Make annual workbook import safe, explicit, repeatable, and auditable.

### Explicit non-goals

Defer an automatic scheduler/optimizer, hard-coded A/C1/C2/C3-to-person
rules, a generic team-dependency graph, a Worship-specific parallel model,
drag-and-drop scheduling, a full availability system, swap/replacement
workflow, reminders, arbitrary spreadsheet import, bidirectional Google Sheets
sync, and full assignment import in the first import slice.

## 5. Domain and invariant decisions

1. Reuse `ServiceEvent`, `MinistryTeam`, `ServiceEventRequiredTeam`,
   `TeamAssignment`, and `TeamAssignmentMember` unless implementation evidence
   later proves a narrow missing semantic. Do not create `WorshipAssignment`.
2. `rotation_anchor_team` remains an event-level hint. It is not an assignment,
   required-team declaration, permission grant, audience scope, or proof that
   Worship has been scheduled.
3. Required teams remain coverage expectations, not placeholder assignments.
4. Belonging, serving, management authority, and audience visibility remain
   separate axes. `ChurchStructureMembership` must not imply serving,
   `TeamAssignment`, My Serving, or scheduling permission; audience scope must
   not imply permission.
5. Calendar remains read-only aggregation, Today remains agenda/action, My
   Serving remains personal explicit serving, and Notifications remain directed
   per-user records. None becomes the scheduling source of truth.
6. Existing fail-closed ordinary-user visibility and invalid/zero-audience
   behavior remain unchanged. There is no ordinary-user or audience-based
   permission bypass, and the board must not bypass canonical mutation/manage
   authority. The approved narrow operational coordination projection is an
   intentional Board/scheduling-context read contract for already-authorized
   schedulers; it does not widen general assignment-detail access.

## 6. Sunday Schedule Board V1

### Implemented behavior

`/assignments/sunday-board/` is a GET-only operational matrix for the fixed
local-date window from today through eight weeks later, inclusive. It shows
non-draft/non-cancelled Sunday Service rows and participating team columns
derived from required teams plus current operational assignments. Cancelled
and completed assignments are excluded consistently with the existing Team
Schedule workspace.

Each participating cell exposes only the approved coordination projection:

- missing when the team is required but has no current assignment;
- empty when a current assignment exists with no active scheduled members;
- scheduled member display names and a coarse scheduled state;
- an Additional label when an assignment exists for a non-required team;
- the event's Worship rotation anchor as context, when configured.

V1 deliberately omits member confirmation detail, assignment notes, contact
and profile details, private staff metadata, prayer/care data, unrelated
history, and cross-team management controls. It does not implement the later
suggestion or changed-context warning semantics.

My Serving provides the scheduler-only Board entry. The Board presents each
event as plain operational text and does not link to `ServiceEvent` or
`TeamAssignment` detail routes. An editable exact-team cell deep-links the
existing Team Schedule workspace for the same date range, Sunday Service
filter, and exact event/assignment; unauthorized cells are read-only.

### Board access and permission design

Board access is an operational scheduler capability. Staff, superusers, and
users with the global TeamAssignment manager capability receive the bounded
Sunday operational set when a row has at least one required team or current
operational assignment. An exact-team Lead/Coordinator receives a row only
when at least one of that user's canonically manageable teams is required for
the event or has a current operational assignment for it. Participation by an
unrelated team cannot establish exact-team row scope.

Ordinary `ServiceEvent.can_be_seen_by()` audience visibility is intentionally
not an additional Board row requirement. Ordinary users do not gain the Board
from event audience visibility, ServiceEvent visibility, Calendar presence,
Church Structure membership, TeamMembership alone, `can_lead`, or an unrelated
serving assignment.

Within the board, a qualifying team leader/coordinator may have narrow,
read-only coordination visibility into other participating teams, including
team name, scheduled display names, assignment existence, coarse operational
state, and the Worship anchor/roster needed for Sunday coordination. This is
not general assignment-detail permission. It must exclude private/internal
notes, contact details, private staff data, prayer/care data, management
controls, and unrelated history. Confirmation details remain conservative
unless a later product decision and repository evidence justify them.

Once a row is legitimately in scope through the preceding rule, the viewer may
receive the approved narrow cross-team coordination projection for all
participating teams on that row. Derive editable team IDs from the existing
`can_manage_team_assignment_for_team` predicate (global assignment authority or
exact-team management authority). A user may edit only those exact teams;
cross-team read visibility never grants cross-team management. Board row scope
is independent of the ordinary ServiceEvent audience predicate, but existing
ServiceEvent and TeamAssignment detail permissions remain unchanged. Every
mutation continues to enforce canonical team-management authority server-side;
hiding an edit button is not authorization.

The board may show the approved narrow cross-team coordination details even
when the viewer cannot edit that team. It must not widen ordinary event or
assignment detail routes.

### Board boundaries

The board owns presentation and navigation. Detailed assignment forms,
member selection, status transitions, and confirmation remain owned by the
existing assignment flows. V1 has no Board POST or save action: Board loading
and navigation write no rows, and any edit occurs through the existing
permission-checked Team Schedule event/team operation.

The board is spreadsheet-like only as a presentation and interaction metaphor,
not as a multi-cell transaction model. MO-S.6B must not add a client-side
spreadsheet state engine, bulk “Save spreadsheet” action, drag/drop bulk
mutation, or silent autosave. Each cell mutation is independently authorized
and saved through existing domain semantics.

### Column derivation

MO-S.6B does not hard-code current church team names or A/C1/C2/C3 into generic
CMS logic. The no-schema V1 derives participating columns from the union of
`ServiceEventRequiredTeam` teams and existing `TeamAssignment` teams for the
selected Sunday rows, orders them by canonical team name and ID, labels
inactive teams, and shows a non-participating dash where a column appears only
for another event. The presentation separately labels the event's
`rotation_anchor_team` as the Worship context; that anchor remains an ordinary configured
`MinistryTeam`, not a global Worship taxonomy.

## 7. Worship-led coordination and suggestions

Downstream team scheduling should receive a compact context panel for the
selected Sunday:

- current `rotation_anchor_team`, if set;
- current Worship `TeamAssignment` summary and roster only when the viewer is
  authorized to see it;
- “Worship not yet scheduled” when the anchor exists but no active Worship
  assignment exists;
- the source and age of a historical/default pairing suggestion;
- whether the current assignment differs from or matches the currently shown
  suggestion, when that comparison is derivable from current rows.

The first implementation should reuse the existing copy-forward service and
team schedule flow. It should make the suggestion source explicit (same anchor
history versus team history), show copied member candidates before save, and
make the user review/edit the form. The invariant is:

**system suggestion -> human review -> explicit save**

Suggestions must never silently create, overwrite, cancel, or confirm a
downstream assignment. A manual save should preserve the current assignment
update/idempotency behavior. V1 must not claim that an assignment was a
“manual override” unless durable repository data proves that provenance; it may
only report a current assignment that differs from or matches the current
suggestion. A new durable provenance field is not approved in MO-S.6A.

## 8. Upstream-change awareness

Initially, evaluate a derived warning without schema changes only after an
implementation audit proves that every relevant Worship roster/member
mutation updates the timestamp being compared. Candidate evidence includes
the current Worship assignment/event `updated_at`, the downstream assignment
`updated_at`, and any already-existing request-flow state. The current model
has a separate `TeamAssignmentMember` row with `created_at` but no
`updated_at`, and its save/confirmation path does not itself update the parent
assignment; therefore timestamps cannot be assumed to prove roster change.

Before shipping a warning, the implementer must trace all supported create,
remove, replace, confirm, and direct/administrative paths that can change the
relevant roster. If those paths do not reliably update the compared timestamp,
stop before material divergence, report the evidence, and present the smallest
safe alternatives (for example, a deliberately weaker review prompt or a
future explicit context/version field) for product decision. Do not ship a
misleading freshness warning and do not add schema in this task.

The warning is advisory only:

> Worship scheduling changed after this team assignment was last updated.
> Review recommended.

Do not overwrite downstream members, status, notes, or confirmation. If later
product use shows that timestamps cannot distinguish context changes, evaluate
a narrow explicit scheduling-context/version field in a later slice. Do not
claim manual-override provenance or add that schema in this planning task.

## 9. Controlled Excel import

### Supported boundary

The first importer should target one named, versioned church Sunday workbook
template. It should reject unsupported headers, missing required sheets,
ambiguous date columns, formula-dependent required values, forbidden sensitive
columns, and template-version drift. It should not attempt to understand an
arbitrary spreadsheet.

### First import scope

MO-S.6D should import only:

1. Sunday dates and the matching/creation of `ServiceEvent` rows;
2. Worship rotation anchor assignment to an existing configured
   `MinistryTeam`.

Special-service rows, annotations, downstream team columns, and person names
should be reported as unsupported or informational in this first slice, not
silently converted into assignments. Worship member assignments and AVL
assignment import are later slices.

### Required transaction flow

`upload -> parse -> validate -> preview -> explicit confirmation -> write`

Parsing and preview must be side-effect free. Confirmation must revalidate the
preview against current rows, use an atomic write boundary, and fail clearly if
the source or target changed. The preview should classify each row as:

- create event;
- existing event matched;
- change rotation anchor;
- already matches / no-op;
- conflict;
- invalid row;
- unresolved person;
- ambiguous person;
- unsupported or special row.

The first scope normally has no person rows, but the preview vocabulary should
not force a later importer to hide identity problems.

### Matching and idempotency

Event matching must use a documented stable key derived from the actual
supported workbook/template service identity. It may involve local service
start date/time, supported event type, and template/service-profile identity;
MO-S.6D must inspect the real workbook before fixing the exact key. Date alone,
or date plus event type alone, must not silently merge distinct same-day
services. A collision with conflicting event type/time/title/service identity
must be a conflict requiring human resolution. Re-uploading the same workbook must
produce no duplicate event or anchor rows; a changed anchor must appear as an
explicit proposed change and never be silently applied. Cancelled or otherwise
non-matchable existing events must not be silently reused.

No import should create a `TeamAssignment` merely because the workbook has a
Projection, Sound, Recording, Video, or Lighting column.

## 10. Future identity resolution for assignment import

Assignment import is high risk because names may be abbreviated, bilingual,
punctuated differently, aliased, or combined in one cell. A later importer
must use exact/canonical mappings first. If repeated operations justify it, a
small explicit import-alias model or equivalent admin-managed mapping may be
evaluated; it is not approved or created here.

Unsafe fuzzy matching must never silently assign a real CMS user. Unresolved
and ambiguous names must remain visible in preview and block automatic import
of that assignment. Multiple names in one cell require explicit tokenization
and review. An unknown spreadsheet name must never auto-create a Django User.
The safe fallback is a blocked row or an explicitly unlinked, human-resolved
candidate only if a future product decision permits that state.

## 11. Spreadsheet formulas and Google Sheets boundary

Workbook formulas are input artifacts, not CMS business rules. The importer
may read a supported exported value where the template contract explicitly
allows it, but CMS semantics must not depend on evaluating arbitrary formulas.
Changes to a Google Sheet formula must not silently redefine rotation/pairing
rules in the CMS. Pairing suggestions remain governed by CMS-owned data and
explicit human review.

Near-term ownership is:

- Google Sheet / Excel: macro annual planning and controlled input source;
- CMS: operational execution source of truth after explicit import/save.

Bidirectional sync is out of scope. A future one-way Google Sheets import may
be reconsidered only if repeated manual `.xlsx` uploads create a demonstrated
operational burden and a separate conflict policy is approved.

## 12. Privacy, permissions, and failure modes

The board and importer must avoid exposing private notes, phone numbers,
passwords, prayer/care content, or unrelated team rosters. Staff/global views
may be broader only where current capability semantics allow. Ordinary members
should not receive an operational multi-team dashboard merely because they can
see a public event.

Important failure modes and required handling include:

- no/invalid event audience: preserve the existing fail-closed behavior;
- missing required team: show coverage gap, never create a fake assignment;
- anchor set but no Worship assignment: show “not yet scheduled”;
- Worship assignment changed: warn/review, never rewrite downstream rows;
- duplicate target assignment: block or route through existing duplicate-safe
  edit behavior;
- inactive/non-assignable team: reject new scheduling/import target while
  preserving appropriate historical visibility;
- stale board form or preview: re-check locked/current rows before write;
- ambiguous workbook event: classify as conflict and write nothing;
- unsupported template or formula-dependent field: reject clearly;
- unresolved/ambiguous person: block that assignment import;
- partial import failure: atomic confirmation or clearly reported per-row
  isolation with no false “completed” summary;
- repeat upload: no duplicate events or assignments.

## 13. Migration and backward compatibility

The plan assumes existing rows remain valid and current Team Schedule,
assignment detail, My Serving, Today, Calendar, and notification behavior keep
working throughout. A board is a new read/write surface over existing rows,
not a migration away from them.

No legacy Church Structure fields, retired models, or fallback bridges may be
reintroduced. No new serving inference is needed. Any later schema addition
must be justified by an observed gap, include a migration/backfill and
rollback/readiness plan, and preserve existing direct assignment workflows.

## 14. Recommended implementation slices

Each slice is independently reviewable and should ship only after its focused
tests and limited-trial review pass.

### MO-S.6A — this document

- Goal: establish current-state truth, boundaries, and order of work.
- Scope: documentation only.
- Out of scope: all runtime, schema, import, UI, and test changes.
- Likely components: `docs/` only.
- Schema/permission impact: none.
- Tests/acceptance: `git diff --check`; no runtime claims.
- Dependency: current MO-S.5A/B and existing module boundaries.

### MO-S.6B — Sunday Schedule Board V1

- Status: implemented and verified in the current repository.
- Goal: bounded event-by-team operational matrix with permission-safe editing.
- Scope delivered: fixed eight-week Sunday rows, participating team columns,
  coarse coverage/status summaries, narrow cross-team display-name projection,
  and explicit Team Schedule navigation for manageable team cells.
- Out of scope: suggestion semantics, Excel import, optimizer, drag/drop,
  availability, swaps, notifications, and a new permission system.
- Components: a focused side-effect-free Board projection service, ministry
  view/route/template, My Serving entry, responsive CSS, and focused tests;
  existing coverage and permission helpers are reused.
- Schema impact: no model or migration change.
- Security: Board entry requires valid scheduling-management authority for at
  least one participating team. Authorized schedulers receive the approved
  narrow cross-team read projection, while editability is limited to exact
  teams allowed by existing canonical management predicates. The projection
  does not broaden the ordinary TeamAssignment detail route.
- Failure behavior: duplicate assignment and inactive/non-assignable team cells
  fail closed as read-only. Audience-invisible but operationally in-scope events
  have no misleading detail link.
- Verified tests: board GET, qualifying scheduler entry, narrow cross-team projection,
  editable/read-only cells, staff/global manager, exact-team lead/coordinator,
  ordinary member denial/redaction, no-write GET, POST ownership checks,
  duplicate/stale handling, and unchanged general assignment-detail access.
- Acceptance verified: an authorized leader can see the approved narrow Sunday
  coordination projection, schedule only their exact manageable team from the
  board, and leave existing Team Schedule/My Serving and general assignment
  detail behavior unchanged.
- Repository-truth gate resolution: Team Schedule already selected
  required-or-assigned events independently of ordinary ServiceEvent audience
  visibility, while ordinary detail visibility fails closed on zero audience.
  Product approval selected operational parity for Board row scope, with no
  widening of either detail route and no cross-team mutation authority.
- Rendered QA: isolated local Playwright fallback verified lead, staff, and
  ordinary-user flows; authorized Team Schedule navigation; English desktop;
  Chinese mobile; and contained horizontal matrix scrolling. The in-app
  Browser tool failed to initialize, and the only browser console entry in the
  fallback was the pre-existing missing `/favicon.ico` request.
- Dependency: MO-S.5B current assignment/suggestion semantics.

### MO-S.6C — Worship Context & Pairing Suggestions

- Goal: let a downstream scheduler understand current Worship context and
  review a safe suggestion.
- Scope: anchor/roster/not-scheduled context, suggestion source and candidate
  members, explicit review/save, and current assignment-versus-suggestion
  comparison where derivable.
- Out of scope: automatic writes, hard-coded pairing rules, dependency graph,
  Worship-specific model, optimizer.
- Likely components: reusable copy-forward service, team schedule form/view,
  focused context presenter.
- Schema impact: target none; no provenance field unless a later evidence-based
  slice is separately approved.
- Security: a qualifying Sunday scheduler may receive the approved narrow
  cross-team scheduling projection, including the current Worship roster
  context needed for coordination, even when they cannot manage Worship. This
  projection is not general `TeamAssignment`-detail visibility and must not
  expose private Worship notes or controls. Edit remains limited to the
  downstream team owner under the canonical management predicate.
- Tests: same-anchor/team-history selection, approved narrow roster projection,
  no source/no anchor, no-write
  preview, explicit save, confirmation not copied, matching/differing current
  assignment comparison, and no unsupported provenance claim.
- Acceptance: suggestion is visibly a proposal and never creates or overwrites
  until explicit save; V1 reports only derivable current-row comparison.
- Dependency: MO-S.6B or a shared board context helper.

### MO-S.6D — Excel Event + Worship Anchor Import

- Goal: controlled annual workbook input for dates and anchor only.
- Scope: versioned template, parse/validate/preview/confirm, event matching,
  anchor proposals, audit/result classification, idempotent atomic write.
- Out of scope: assignment/member import, arbitrary workbooks, formulas as
  rules, bidirectional sync, automatic user/team creation.
- Likely components: importer service, upload/preview/confirm views/templates,
  event/team lookup helpers; reuse generic models.
- Schema impact: target none; any import-run persistence requires a later
  explicit decision.
- Security: authorized event/scheduling manager only; no production mutation
  on upload or preview; reauthorize at confirmation.
- Tests: malformed/versioned workbook, date/event conflict, no-op/re-upload,
  anchor change, cancelled event, unsupported/special row, atomic rollback,
  explicit confirmation, permission denial, formula/value boundary.
- Acceptance: identical re-upload is a no-op; every write is previewed,
  confirmed, authorized, and attributable; no assignment is created.
- Dependency: MO-S.6B event/team context and stable template contract.

### MO-S.6E — Worship Change / Downstream Review Warning

- Goal: make possible downstream staleness visible without automation.
- Scope: conservative derived warning first; later version field only if needed.
- Out of scope: downstream rewrite, automatic rescheduling, notification fanout.
- Likely components: event/team context helper and board/team schedule copy.
- Schema impact: none initially; explicit context/version field deferred.
- Security: warning reveals only authorized schedule context.
- Tests: upstream-before-downstream, upstream-after-downstream, no Worship
  assignment, roster mutation-path timestamp audit, unsupported timestamp
  evidence, and unknown/ambiguous freshness state.
- Acceptance: warning is advisory, shipped only where every relevant roster
  mutation is proven to update the compared timestamp, and never mutates
  assignments.
- Dependency: MO-S.6C and stable board context.

### MO-S.6F — Excel Assignment Import

- Goal: import selected Worship/AVL assignments only after identity safety is
  proven.
- Scope: exact/canonical or explicit alias mapping, preview-blocked unresolved
  and ambiguous identities, team-owned authorization, explicit confirmation.
- Out of scope: fuzzy auto-assignment, User creation, bulk permission bypass,
  full annual history, formula-driven behavior.
- Likely components: importer identity resolver, admin-managed mappings if
  approved, preview UI, generic assignment writes.
- Schema impact: possible future alias model only after an ADR/evidence review.
- Tests: bilingual names, aliases, punctuation, initials, multiple names,
  unresolved/ambiguous blocking, team ownership, idempotency, no User creation.
- Acceptance: no real user is assigned without a safe match and human-visible
  confirmation.
- Dependency: MO-S.6D, MO-S.6C, and proven permission/identity rules.

### MO-S.6G — Operational Board Polish

- Goal: improve day-to-day scanning after real use.
- Scope: filtering, coverage/missing/unconfirmed states, visual status, bounded
  responsive usability, and evidence-backed copy improvements.
- Out of scope: new workflow authority, optimizer, availability, swaps,
  arbitrary spreadsheet behavior.
- Likely components: board presentation only unless evidence identifies a
  narrow domain gap.
- Schema impact: none expected.
- Security: preserve all V1 row/cell boundaries.
- Tests: focused rendering, permission redaction, filters, status transitions,
  bilingual copy, responsive/manual QA where rendered behavior changes.
- Acceptance: real schedulers can identify missing/review-needed work quickly
  without losing ownership or privacy boundaries.
- Dependency: MO-S.6B through MO-S.6E trial evidence.

### Later candidates

Evaluate separately only after operational evidence: availability, swaps or
replacement workflow, reminders, and optional one-way Google Sheets import.

## 15. Test, rollout, and limited-trial strategy

The implementation slices should use focused Django tests for actual GET/POST
flows, permission boundaries, atomic side effects, duplicate/idempotency cases,
and stale/current-row checks. Import slices need fixture workbooks covering
valid, changed, conflicting, unsupported, bilingual, and unsafe identity cases.
Browser/manual QA is required for board and preview/confirmation UI because
rendered interaction is part of their risk; it must not be claimed until
actually performed.

Roll out to a small set of Sunday schedulers first: one Worship coordinator and
leaders for a few AVL teams. Keep the existing workbook as a reference during
the trial, but treat explicit CMS assignments as operational execution data.
Compare missing/changed-context cases and assignment-difference/exception
frequency. Do not
declare production readiness from a limited trial. Expand only after
permission, privacy, idempotency, and exception handling are observed to work.

## 16. Open product decisions

These are genuine future decisions, not hidden implementation assumptions:

- Which configured teams are authoritative Worship anchors, and who may set or
  change that event hint?
- Which teams participate in the default Sunday board, and how are combined or
  special services represented?
- Which additional cross-team details, if any, may be added beyond the
  approved narrow Sunday coordination view?
- Can existing `updated_at` values produce a trustworthy review warning after
  all roster mutation paths are audited, or is a context/version field needed?
- What exact annual workbook template/version and stable event key will the
  church support?
- Should import preview/results be retained durably for audit, or remain a
  request-scoped confirmation artifact?
- If assignment import is needed, is an explicit alias mapping model worth its
  operational cost and who maintains it?
- When should repeated uploads justify a one-way Google Sheets import, and what
  conflict policy would it use?

## 17. Current-state references

This plan is grounded in the current implementation and canonical boundaries in:

- `docs/MINISTRY_SCHEDULING_REQUIREMENTS_PLAN.md` (MO-S.2 through MO-S.5B);
- `docs/MINISTRY_TEAM_OPERATIONS_V1_PLAN.md`;
- `docs/TODAY_AND_MY_SERVING_PRODUCT_BOUNDARIES.md`;
- `docs/CHURCH_CALENDAR_V1_PLAN.md`;
- `docs/NOTIFICATIONS_V0_PLAN.md`;
- `docs/MODULE_BOUNDARIES.md` and `docs/CHURCH_STRUCTURE_FOUNDATION_PLAN.md`;
- `events/models.py`, `ministry/models.py`, `ministry/permissions.py`,
  `ministry/services/assignment_coverage.py`, and
  `ministry/services/copy_forward_suggestions.py`.
