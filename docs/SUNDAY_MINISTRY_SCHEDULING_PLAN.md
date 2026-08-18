# Sunday Ministry Scheduling Workflow & Import Plan

Status: current through implemented MO-S.6C Worship Context & Pairing
Suggestions and the docs-only MO-S.6D-0A workbook/readiness investigation plus
MO-S.6D-0A-FU1/FU2 multi-campus Worship rotation governance closure. MO-S.6D
and all other future runtime slices remain separately scoped and require
explicit approval.

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
- `rotation_anchor_team` can already store a Worship team such as Worship A,
  C1, C2, or C3 when configured as an ordinary assignable `MinistryTeam`. The
  current runtime treats it only as an optional hint and does not enforce the
  stronger governed invariant. Canonically, the future governed workflow uses
  it as the event-level selection of the team that owns Worship for that
  occurrence. It is still not an assignment, required team, audience,
  visibility, permission, serving, or coverage source.
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

MO-S.6B provides the bounded cross-team Sunday matrix and exact-team cell
editability. MO-S.6C now adds the narrow current Worship roster/state context
and transparent, review-first pairing suggestions to that Board/Team Schedule
workflow. The current system still does not provide the downstream review
warning when Worship changes or a controlled
`.xlsx` upload/parse/preview/confirm workflow. MO-S.6D-0A-FU1/FU2 now define how
a future explicitly configured Worship rotation pool, event audience, and
primary Ministry Structure path determine eligible teams without treating a
name such as C2 as semantic proof. They also require explicit exact-event
planner/coordinator responsibility for the approved planner workflow. This is
documentation architecture only; the required Campus type, Worship-pool
metadata, event responsibility, authorization, reachability, and import runtime
do not yet exist.

## 3. Real-world Sunday workflow

The intended operating sequence is:

1. Staff or an authorized Worship scheduler establishes the Sunday
   `ServiceEvent` and selects its Worship Team, if known.
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
2. Under the governed workflow, `rotation_anchor_team` is the event-level
   selection of the Worship Team that owns that occurrence. It is not an
   assignment, required-team declaration, serving row, permission grant,
   audience scope, or proof that Worship has been scheduled.
3. If a current Worship `TeamAssignment` exists, its team must equal the
   selected Worship Team. Off-team or duplicate assignments fail closed, and a
   selection change never silently moves, retags, clones, cancels, or rewrites
   an existing roster. Current runtime does not yet enforce this FU1 invariant.
4. Required teams remain coverage expectations, not placeholder assignments.
5. Belonging, serving, management authority, and audience visibility remain
   separate axes. `ChurchStructureMembership` must not imply serving,
   `TeamAssignment`, My Serving, or scheduling permission; audience scope must
   not imply permission.
6. Calendar remains read-only aggregation, Today remains agenda/action, My
   Serving remains personal explicit serving, and Notifications remain directed
   per-user records. None becomes the scheduling source of truth.
7. Existing fail-closed ordinary-user visibility and invalid/zero-audience
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
derived from required teams plus current operational assignments. The
dedicated Worship / Rotation Context column owns each event's exact rotation
anchor, so that same event/anchor pair is omitted from its generic team cells.
An anchor team still appears as an ordinary generic cell on another event when
it participates there in a non-anchor role. Cancelled and completed
assignments are excluded consistently with the existing Team Schedule
workspace.

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
The Worship context uses the same navigation rule when the viewer can
canonically manage that exact active, assignable anchor and the current anchor
assignment is unambiguous. Downstream team owners remain read-only.

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
CMS logic. The no-schema V1 derives row eligibility from the full union of
`ServiceEventRequiredTeam` teams and existing `TeamAssignment` teams. Generic
display columns use that same per-event union after subtracting only the
event's exact `rotation_anchor_team`; their cross-event union is ordered by
canonical team name and ID. This preserves exact-anchor scheduler row scope,
avoids duplicate Worship cells for the anchor event, and still shows the team
normally when it participates as a non-anchor on another event. The table
labels inactive teams and shows a non-participating dash where a column appears
only for another event. The anchor remains an ordinary configured
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

The first importer should target one named, code-versioned church Sunday
workbook contract. It should reject unsupported headers, missing required
sheets, ambiguous date columns, required formulas or cached values outside the
explicit MO-S.6D-0A policy, forbidden sensitive columns, and template-contract
drift. The real workbook has no durable workbook-supplied version marker, so a
future implementation must not fabricate one or attempt to understand an
arbitrary spreadsheet.

### First import scope

Before MO-S.6D-0A, the proposed first scope was:

1. Sunday dates and the matching/creation of `ServiceEvent` rows;
2. Worship rotation anchor assignment to an existing configured
   `MinistryTeam`.

Special-service rows, annotations, downstream team columns, and person names
should be reported as unsupported or informational in this first slice, not
silently converted into assignments. Worship member assignments and AVL
assignment import are later slices. MO-S.6D-0A found that event plus anchor
alone cannot start the implemented scheduling workflow and that the workbook
cannot supply a safe event audience. MO-S.6D-0A-FU1/FU2 close the architecture
by requiring a match/update-only first lifecycle, explicit Worship-specific
rotation-pool configuration, required exact-event planner/coordinator
responsibility, audience applicability, eligible token mappings, and
anchor-only operational reachability. Those prerequisite runtime slices and
the remaining importer-owned decisions still require separate approval.

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

- Status: implemented. MO-S.6D and later remain unapproved.
- Goal: let a downstream scheduler understand current Worship context and
  review a safe suggestion.
- Scope delivered: a shared read-only presenter identifies the configured
  anchor and an exact-event/exact-anchor scheduled/confirmed/prepared
  `TeamAssignment`; it distinguishes no anchor, not scheduled, empty roster,
  scheduled roster, unavailable anchor, and duplicate/ambiguous assignments.
  The Board and Sunday Team Schedule show only anchor name, coarse state, and
  active member display names.
- Suggestions: the existing anchor and team-history copy-forward modes remain
  separate. An active preview labels the source mode, source event/date, and
  proposed members, and says explicitly that Save Assignment is required.
  Current assignment match/difference compares canonical `TeamMembership`
  identities; duplicate targets suppress unreliable comparison/proposal review.
- Out of scope: automatic writes, hard-coded pairing rules, dependency graph,
  Worship-specific model, optimizer, changed-context warning, and suggestion
  provenance.
- Components: `ministry/services/worship_context.py`, the existing
  `copy_forward_suggestions.py`, existing Team Schedule mutation/notification
  path, Board/Team Schedule templates, and focused tests.
- Schema impact: none; no model, migration, provenance, or context-version field.
- Security: a qualifying Sunday scheduler may receive the approved narrow
  cross-team scheduling projection, including the current Worship roster
  context needed for coordination, even when they cannot manage Worship. This
  projection is not general `TeamAssignment`-detail visibility and must not
  expose private Worship notes or confirmation/contact details. Board
  de-duplication is presentation-only and does not reduce row authorization or
  operational participation. An exact anchor manager may navigate from the
  context cell to the existing exact-event/assignment Team Schedule flow;
  downstream managers remain read-only under the canonical management
  predicate. Duplicate and unavailable anchors expose no action.
- Tests verified: current status mapping; no anchor/no assignment/empty/current
  roster/unavailable anchor/duplicate states; downstream lead, staff/global and
  ordinary-user boundaries; private-note/contact/confirmation redaction;
  same-anchor and team-history sources; future/draft/cancelled filtering;
  completed-history behavior; inactive-member filtering; no-write/no-notify GET;
  explicit-save notification behavior; confirmation not copied; identity-based
  match/difference; duplicate target fail-closed behavior; and forged cross-team
  rejection.
- Acceptance verified: suggestion is visibly a proposal and never creates or
  overwrites until explicit save; only derivable current-row comparison is
  reported, with no provenance or automatic-pairing claim.
- Rendered QA: an isolated throwaway SQLite database and local Chrome
  Playwright fallback verified exact-team lead, staff, and ordinary-user
  boundaries; current/no-roster/no-anchor Worship states; English desktop
  suggestion review/prefill; and Chinese mobile contained matrix scrolling.
  The in-app Browser runtime failed twice during initialization with
  `Cannot redefine property: process`; bundled Playwright had no Chromium
  binary, so the existing local Chrome executable was used without installing
  anything. The only console error was the pre-existing missing `/favicon.ico`
  request. This is automated rendered QA, not product-owner manual QA.
- Dependency: MO-S.6B or a shared board context helper.

### MO-S.6D-0A-FU1/FU2 — Multi-Campus Worship Rotation Governance

- Status: canonical docs-only architecture closure complete through FU2. FU2
  makes exact-event planner/coordinator responsibility a required prerequisite
  and fixes the pool semantic as Worship-specific. No Campus type, Worship-pool
  field, event responsibility model, permission, queryset, importer, migration,
  or data change is implemented or approved here.
- Canonical decision: see
  [`WORSHIP_ROTATION_GOVERNANCE_PLAN.md`](WORSHIP_ROTATION_GOVERNANCE_PLAN.md).
- Church Structure: add a future semantic-only Campus / Site type while
  preserving a flexible tree and the separation between structure, belonging,
  audience, permission, and serving.
- Pool applicability: a future active, non-assignable MinistryTeam explicitly
  marked with the `is_worship_rotation_pool`-equivalent semantic applies only
  when its valid primary Church Structure anchor is equal to or below a selected
  active event audience unit. The configuration is Worship-specific and grants
  nothing by itself. Audience establishes applicability, never authority.
- Candidate anchors: the union of active assignable descendants of all
  applicable pools through active primary MinistryTeam parent paths. Names,
  fuzzy matching, database IDs, `team_kind`, and role profiles are excluded.
- Ownership invariant: the selected team owns Worship for that occurrence. A
  missing Worship assignment is an unscheduled state; any current Worship
  assignment that exists must be for that exact team. An off-team or duplicate
  roster is invalid/ambiguous and fails closed. Selection changes never move,
  retag, clone, cancel, or rewrite an existing roster.
- Authority: full ServiceEvent managers, an explicit event planner/coordinator,
  or an active date-valid Lead/Coordinator on an applicable pool may use a
  future narrow anchor-only action. Exact child-team roster authority remains
  unchanged and never flows from a pool role.
- Event responsibility: the approved workflow requires a lifecycle-managed
  user + exact-ServiceEvent planner/coordinator foundation before the narrow
  selector ships. It grants only minimum event/Worship context and this action;
  it is not replaced by `created_by` or full `CAP_MANAGE_SERVICE_EVENTS`.
- Reachability: the exact current valid rotation anchor should become a third
  operational relevance predicate beside required-team and existing-assignment
  participation. It must not create or imply a required team, assignment,
  coverage, audience, serving row, or permission grant.
- Import consequence: the former RequiredTeam bootstrap recommendation is
  superseded. The first importer remains exact existing-event match/update,
  maps tokens only to eligible candidates, blocks on current Worship-roster
  conflicts, changes only the selected Worship Team, and is staff/superuser-only
  for bulk upload/preview/confirm.
- Later operations: a Worship Rotation Planner may preview/confirm one-Sunday
  changes or a bounded one-Sunday shift of later explicit selections, without a
  rotation rule engine or any roster movement. A separate ministry-owned
  post-commit producer may send direct old/new/downstream leadership notices,
  summarized once per recipient for a batch. This is distinct from MO-S.6E
  roster-change staleness detection.
- Copy: scheduler-facing UI should use Worship Team / 敬拜团队 rather than the
  engineering term rotation anchor.
- Dependency: every runtime/schema slice in the canonical governance plan still
  requires separate task approval and focused verification.

### MO-S.6D-0A — Workbook Contract & Imported-Sunday Readiness

- Status: docs-only investigation complete. MO-S.6D implementation remains
  blocked on the FU1 prerequisite runtime slices and importer-owned decisions
  below. No importer, runtime surface, schema, dependency, or data change is
  approved by this section.
- Evidence: the external workbook
  `2026 SVCA Sunday Service and Special Events Schedule (Master總表) .xlsx`
  was inspected without modification and was not added to the repository. Its
  inspected SHA-256 was
  `186735DC723979AA49D209C92D4155BE533D6AFE9253CDB5D8B809A77C8B07AA`.

#### Workbook contract and supported service profile

The workbook contains these exact sheet names; whitespace shown inside quotes
is part of the sheet name:

1. `All 930`
2. `2026 Special Events `
3. `Bethany Hall 其他服事（總務，關懷，福音）`
4. `工作表22`
5. `三谷主日（擘餅、worship, 总务，饭食，接待，主日學）`
6. `Kephir`
7. ` Sunday Groups `
8. `Children (Auto Renew) `

The only supported operational input for the proposed first slice is the
`All 930` sheet. Its populated data are `A1:O58`; formatting extends through
`AD948` and must not create input rows. Row 2 contains the 2026 master title,
row 3 contains the operational headers, and only `N2:O2` is merged. Row 1
still says 2025, so the first title row cannot be a version marker. Required
contract evidence is the exact sheet name, the 2026 title in `B2`, the header
positions `A3`/`B3`, and `B3 = Worship/AV @Bethany`. Column A is the date and
column B is the Worship/rotation input. Columns C:O are informational and must
not produce assignments or event identity in MO-S.6D.

`All 930` is a parallel multi-service/location master row, not proof that a
date identifies one church event: Bethany columns are B:I, English Ministry
J:K, children/Kephir L:M, and Tri-Valley N:O. The sheet name plus the Bethany
header supports only the Bethany 9:30 service profile for columns A:B; the
workbook has no explicit start-time cell. MO-S.6D must not import the parallel
English, children, or Tri-Valley columns under the Bethany profile.

The proposed code-owned contract revision must require the expected sheet,
titles, headers, positions, supported year, allowed input columns, date rules,
and rotation-token rules. The workbook has no durable supplied version field,
so implementation must use a CMS-owned contract revision/structural signature
and must not fabricate a workbook version. Formatting, comments, titles, and
unselected sheets are not business rules.

#### Date and formula contract

The 2026 Sunday input comprises exactly 52 rows: row 4 and rows 6:56. `A4` is
a literal Excel date (`1/4/26`). `A5` is the literal text `1/9/26(Fri)` and is
a special Friday row. The other 51 supported Sunday dates are formula-backed
weekly increments with stored Excel-date results. Rows 57:58 continue into
2027 and are outside the supported year; the final anchor is also blank.
Column B rotation values are literal strings, not formula results. Other
columns contain formulas and must be ignored by this slice.

A future parser must not evaluate Excel formulas. For a date formula in the
exact supported date cells, it may consume the workbook's stored cached value
only when all of these checks pass:

- a cached result is present and is a valid Excel date;
- the result is a Sunday in the configured 2026 contract year;
- the date equals the strictly expected weekly sequence for its contract row;
- the formula is confined to the allowed date-column pattern; and
- preview identifies the value as formula-backed and retains its source row.

Missing, stale-looking, inconsistent, non-date, wrong-year, or unexpected
formula/cache combinations are invalid and block confirmation. A formula in
the anchor cell is outside this observed contract and is invalid. Cached data
are supplied source evidence, not CMS-evaluated truth. No server-side Excel or
LibreOffice installation is required or permitted as a formula engine.

#### Rotation tokens and team resolution

The 52 supported Sunday rows use literal prefixes `A` (12), `C1` (13), `C2`
(13), and `C3` (14), followed by leader names and sometimes annotations. The
Friday special row uses `C`. These prefixes are template tokens, not universal
CMS concepts. The current local configuration has active, assignable teams
whose displayed names correspond to A/C1/C2/C3, but `MinistryTeam` has no
unique stable external/import-key field; names are mutable and not unique.

MO-S.6D must not fuzzy-match, use substring matching, auto-create a team, or
hard-code a database primary key. The smallest no-schema mechanism is an
explicit preview mapping from each observed token to one existing active,
assignable team. An exact unique expected-name match may prefill a choice, but
the user must see and confirm it. The signed proposal may retain the selected
database identity for confirmation-time revalidation. A code/config exact-name
mapping is more brittle; a future explicit import key is justified only if
repeated imports demonstrate that need.

#### Deterministic event identity and matching

Date alone and date plus `event_type` are unsafe because the workbook contains
parallel same-day services. The candidate identity is:

`contract/service profile + local service date + exact local 09:30 start +`
`sunday_service event type + configured persisted profile discriminator`.

The profile discriminator must be an explicitly selected canonical location
and/or `host_language_unit` resolved by a stable structure code, never a
database primary key. The workbook does not supply the exact CMS location or
host/language value, so product must approve the Bethany 9:30 profile-to-CMS
mapping before creation is safe. Title is validation/mutable display metadata,
not identity. End time and annotations are also not identity. Location or
host/language may be identity evidence only after that explicit mapping;
`host_language_unit` remains display-only and never supplies audience.

Matching must use the configured local timezone and require exactly one
non-cancelled candidate with the exact minute, event type, and profile
discriminator. An audience-invalid candidate is not import-ready. Multiple
candidates, a cancelled candidate, or a same-date row whose time, type, or
profile disagrees is a conflict with no write; the importer must not select a
closest match or silently create a second event around a conflict.

#### Mandatory event-plus-anchor reachability gate

For an imported `ServiceEvent` with `rotation_anchor_team = Worship C2`, no
`ServiceEventRequiredTeam` for C2, and no `TeamAssignment`:

A. The C2 Lead cannot reach that event through Team Schedule, whose event set
   requires the selected team to be required or already assigned.
B. The C2 Lead cannot reach it through Sunday Schedule Board because exact-team
   scope also requires the manageable team to participate through a required
   team or current assignment.
C. A global assignment manager cannot see the row on the Board because the
   global row set still requires required-team or assignment scheduling data.
D. The intended workflow “Worship schedules itself first” cannot start through
   either implemented scheduling surface.

This is a workflow dead end, not a permission grant that should be inferred
from `rotation_anchor_team`. The current Board deliberately does not treat an
anchor as a required team, assignment, coverage source, or participation row.
Changing that row-scope semantic is a separate product decision.

#### Required-team bootstrap recommendation (superseded by FU1)

New events currently receive required teams only through explicit per-event
selection in the single-event or recurring-event forms. The repository has no
event template, canonical Sunday required-team preset, reusable setup
configuration, or required-team copy-forward source for an importer.

- Option A, event plus anchor followed by manual setup, is representable but
  does not make an anchor-only event reachable in current scheduling surfaces.
- Option B cannot be used because no canonical reusable required-team
  configuration exists.
- Option C makes the exact current valid anchor a narrow operational-relevance
  predicate without changing coverage meaning.
- Option D would create an explicit `ServiceEventRequiredTeam` solely for
  discoverability, falsely asserting expected coverage.

MO-S.6D-0A-FU1 approves Option C as the future architecture and supersedes the
former Option D recommendation. Team Schedule and Sunday Board should treat the
exact active/assignable current anchor as operationally reachable while keeping
it outside required/additional coverage. No `ServiceEventRequiredTeam` or
`TeamAssignment` is created. This remains an unimplemented, separately approved
runtime slice; current behavior is unchanged.

#### New-event audience and lifecycle gate

A published zero-audience event is invisible to ordinary users and is reported
as an upcoming readiness blocker by the current audit. Normal event and
recurring-event creation require audience selection, while the model alone can
still store a published zero-audience row. The workbook has no Church Structure
audience data, and audience must not be inferred from a Worship token, team,
person name, location label, or `host_language_unit`. No existing event
template supplies a canonical audience.

Creating a draft is safer for ordinary visibility, but draft events are
excluded from both Team Schedule and the Board, so it does not solve the
scheduling workflow. The safest first implementation is therefore match/update
only: operate on one exact existing, non-draft, non-cancelled, audience-ready
CMS event. If product later requires new-event creation, preview must require
an authorized staff user to select and confirm valid audience and profile
metadata, then confirmation must atomically create the event, audience rows,
and anchor. It must never silently create a
published zero-audience event.

#### Special and exceptional row policy

The master and special-event sheets include Friday/Saturday/Sunday entries,
multi-day ranges, special meetings, conference/holiday/baptism annotations,
TBD values, wrong-year text, combined or replacement Worship labels, blanks,
and 2027 spillover rows. The special-events sheet is informational for 6D and
must not create ordinary Sundays.

- **Supported Sunday row:** exact 2026 `All 930` date/anchor contract, exact
  audience-ready target event, and resolved allowed token.
- **Supported no-op:** exact target already has the proposed anchor.
- **Informational:** notes or person/service annotations ignored by the first
  slice and visibly reported in preview.
- **Unsupported special row:** Friday, non-2026, special-sheet, multi-day,
  combined/replacement, or otherwise out-of-profile input.
- **Conflict:** same-date CMS candidates disagree on identity, multiple targets,
  cancelled/draft/zero-audience target, or changed target since preview.
- **Invalid row:** missing/malformed date or anchor, disallowed token, or
  missing/inconsistent formula cache.

Only a strict match-first contract prevents an annotated or combined row from
silently becoming a new normal Sunday event. Future support for special or
combined services requires a separate explicit classification and identity
contract, not keyword inference.

#### Preview state and confirmation invariants

There is no repository-wide signed preview/import-run pattern. The recurring
event form previews and writes within one POST, while the lighting pilot CSV
import can directly create data and is not a safe pattern for this audience-
and-identity-sensitive flow.

For an annual workbook of this size (about 258 KB and 52 supported rows), the
smallest no-schema option is a timestamped, signed normalized proposal, with
compression if needed. It should contain only the supported normalized fields,
source row/cell, literal-versus-cached status, upload hash, code contract
revision, chosen team mappings, target identifiers, and target fingerprints.
It is tamper-resistant but not confidential, so ignored person names and
unneeded workbook content must not be retained.

Session state is server-side but creates multi-tab, expiry, cleanup, and size
concerns. A temporary uploaded file adds storage/cleanup and hosting concerns.
Re-upload-on-confirm is stateless but adds friction and still requires hash
comparison and reparsing. A durable `ImportRun` gives the best audit/recovery
surface but adds schema, retention, privacy, and cleanup work; it is warranted
only if durable multi-user audit or recovery becomes a stated requirement.

Confirmation must:

- reauthorize the user and enforce an expiry on the signed proposal;
- reparse/revalidate source integrity as required and revalidate contract,
  selected active/assignable teams, current targets, status, audience, and
  target fingerprints;
- lock/reload affected target rows inside `transaction.atomic` and abort the
  entire write set on any stale value or conflict;
- report no success after rollback and make repeated upload/confirmation an
  idempotent no-op;
- make every anchor change explicit in preview;
- create no `TeamAssignment`, `TeamAssignmentMember`, `User`, or
  `MinistryTeam`, and send no notification unless separately approved.

For any later approved new event, current `ServiceEvent.created_by` can record
the confirming user. There is no `updated_by` or anchor-change actor field. A
signed proposal alone cannot provide durable change attribution after the
request; if durable import/anchor-change audit retention is mandatory, product
must approve an `ImportRun` or other audit schema rather than claiming that
attribution already exists.

#### Permission and dependency readiness

Single-event Worship Team selection and annual bulk import are different
authority surfaces. MO-S.6D-0A-FU1/FU2 allow a future narrow one-event action
for full ServiceEvent managers, an explicit lifecycle-managed exact-event
planner/coordinator, or an active date-valid Lead/Coordinator on an applicable
configured Worship rotation pool. The event-responsibility foundation is a
required prerequisite for the approved planner use case and must not be
replaced by full `CAP_MANAGE_SERVICE_EVENTS`. The action changes only the
selected Worship Team and does not grant general event management. The first
annual upload/preview/confirm workflow should be staff/superuser-only at both
preview and confirmation. Exact-team assignment authority, audience, and pool
leadership do not confer bulk import or event-creation authority. A future slice
that writes assignments would additionally require corresponding exact-team and
bulk authority, but assignments are outside MO-S.6D.

No xlsx reader is declared in `requirements.txt` or installed in the repository
virtual environment. The current local environment is Python 3.14/Django 5.2,
while the deployment tooling targets Python 3.11. A future 6D slice therefore
requires a separately reviewed xlsx dependency and verification against both
supported environments and cPanel deployment. A suitable parser can read xlsx
server-side without Excel/LibreOffice, but no package/version was selected or
verified in this investigation.

#### Decisions and prerequisites before MO-S.6D authorization

MO-S.6D-0A-FU1/FU2 close the lifecycle, Worship-pool/candidate,
event-responsibility, operational-reachability, and initial bulk-authority
architecture: first lifecycle is exact existing-event match/update; mapping is
limited to eligible teams from applicable configured Worship pools; the
selected Worship Team is operationally reachable without a RequiredTeam
bootstrap; the event-planner responsibility foundation is required; and first
bulk import is staff/superuser-only. These are documentation decisions, not
implemented prerequisites.

MO-S.6D remains unapproved until its owning slices:

1. implement and verify the Worship-specific rotation-pool configuration,
   applicability, eligible-team resolution, required exact-event
   planner/coordinator foundation, Worship ownership consistency, and
   selected-team operational reachability; Campus remains an independent
   foundation that should precede real multi-campus setup;
2. define the Bethany 9:30 profile's exact local time and persisted CMS
   discriminator, including its stable structure/location mapping;
3. choose timestamped signed proposal retention, or state a durable audit need
   that justifies an `ImportRun` design;
4. decide whether `LogEntry` plus request/result logging is enough or durable
   selected-team/batch attribution requires additional schema; and
5. approve and verify an `.xlsx` dependency in a separate implementation
   slice.

Authorization must also preserve the strict sheet/header/date/formula/special-
row contract, match conflicts, atomic stale revalidation, the first-slice
staff/superuser bulk boundary, no assignment/person/team creation, no
notifications unless a separate FU1 producer slice is approved, and no
published zero-audience creation.

### MO-S.6D — Excel Event + Worship Team Import

- Status: not implemented or authorized; blocked on the prerequisite slices and
  remaining importer-owned decisions above.
- Goal: controlled annual Bethany 9:30 workbook input under the approved
  contract and lifecycle, not date-and-anchor import in isolation.
- Candidate scope after approval: code-versioned template contract,
  parse/validate/preview/confirm, exact existing-event matching, explicit
  eligible token mapping, before/after Worship Team proposals, current Worship
  roster conflict detection, downstream-assignment impact display, audit/result
  classification, and idempotent atomic selected-team-only write. New-event
  creation remains excluded unless product separately approves the
  audience/profile flow.
- Out of scope: assignment/member import, arbitrary workbooks, formulas as
  rules, bidirectional sync, automatic user/team creation.
- Likely components: importer service, upload/preview/confirm views/templates,
  event/team lookup helpers; reuse generic models.
- Schema impact: target none; any import-run persistence requires a later
  explicit decision.
- Security: staff/superuser only for the first bulk workflow; no production
  mutation on upload or preview; reauthorize at confirmation.
- Tests: malformed/versioned workbook, date/event conflict, no-op/re-upload,
  selected-team change, off-team/duplicate/current roster conflict, downstream
  impact, audience-invalid or draft/cancelled event, unsupported/special row,
  stale target, atomic rollback, explicit confirmation, permission denial,
  formula/cache boundary, and eligible token mapping.
- Acceptance: identical re-upload is a no-op; every write is previewed,
  confirmed, authorized, and attributable to the extent explicitly approved;
  no assignment is created and no published zero-audience event is produced.
- Dependency: MO-S.6B event/team context, the MO-S.6D-0A/FU1 governance
  prerequisites, stable service-profile mapping, and a separately reviewed
  `.xlsx` dependency.

### MO-S.6E — Worship Change / Downstream Review Warning

- Goal: make possible downstream staleness visible without automation.
- Scope: conservative derived warning first; later version field only if needed.
- Out of scope: downstream rewrite, automatic rescheduling, and notification
  fanout. A known committed before/after Worship Team selection may receive a
  separate direct FU1 notification producer; it does not solve this harder
  later-roster-change staleness problem.
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

- When should the separately approved Worship Rotation Planner add bounded
  one-Sunday shifts, and does durable batch audit require schema beyond the
  existing per-change `LogEntry` pattern?
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
- `docs/WORSHIP_ROTATION_GOVERNANCE_PLAN.md`;
- `docs/MODULE_BOUNDARIES.md` and `docs/CHURCH_STRUCTURE_FOUNDATION_PLAN.md`;
- `events/models.py`, `ministry/models.py`, `ministry/permissions.py`,
  `ministry/services/assignment_coverage.py`,
  `ministry/services/worship_context.py`,
  `ministry/services/copy_forward_suggestions.py`, and
  `ministry/services/assignment_notifications.py`.
