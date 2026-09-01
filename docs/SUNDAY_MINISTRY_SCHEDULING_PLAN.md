# Sunday Ministry Scheduling Workflow & Import Plan

Status: current through implemented MO-S.6C Worship Context & Pairing
Suggestions, `MO-S.6D-1A` Campus / Site type foundation,
`MO-S.6D-1B` Worship rotation-pool configuration foundation,
`MO-S.6D-1C` ServiceEvent planner/coordinator responsibility foundation, and
`MO-S.6D-1D-A` read-only applicability/candidate/ownership-consistency domain
foundation, and `MO-S.6D-1D-B` governed Worship Team authorization, mutation,
legacy-write enforcement, and narrow planning UI, with
`MO-S.6D-1D-B-FU1` assignment identity and structural-ordering closure,
plus `MO-S.6D-1D-C` Worship Team operational reachability and its FU1/FU2
projection-consistency closures, plus the docs-only `MO-S.6D-1D-D-0A`
Worship Rotation Planner contract and implemented read-only proposal/preview
`MO-S.6D-1D-D-1A`, plus implemented cycle-closed tail refinement
`MO-S.6D-1D-D-1A-FU1`, plus the docs-only SQLite optimistic scheduling-
concurrency decision `MO-S.6D-1D-D-1B-A0`, plus
implemented Scheduling Revision Foundation `MO-S.6D-1D-D-1B-A1`, plus
the MO-S.6D-0A workbook/readiness investigation plus MO-S.6D-0A-FU1/FU2
multi-campus Worship rotation governance closure. Planner confirmation/audit is
implemented through runtime revision foundation `1B-A1` and optimistic batch
confirmation/shared audit `1B-B`. The docs-only `NOTIFY.1G-0A` Direct Worship
Team Change Notification Contract and bounded `NOTIFY.1G` runtime are
implemented; remaining MO-S.6D runtime slices remain
separately scoped and require explicit approval.
`MO-S.6D-PROFILE.1A` now implements the optional stable
`ServiceEvent.service_profile_key` identity foundation and is committed in the
current HEAD. `MO-S.6D-SLICE8.1A/FU1/UX1` separately implements the strict Excel
dependency/parser, bounded OOXML ZIP resource preflight, and staff/superuser-
only zero-write preview, including blocked partial-mapping preview and the
wider operational review surface. Its production read-only smoke passed on
GoDaddy Python 3.11.15 with openpyxl 3.1.5.
`MO-S.6D-PROFILE-SETUP.0A` is committed in current HEAD as the separate read-
only target-event readiness audit. Its production run was reviewed: migrations
and schema through `events/0011` were ready, but zero canonical rows meant the
result was `NOT READY FOR SLICE 8 REAL-DATA MATCHING`; it found seven single
untagged candidates and 45 Sundays with no 09:30 candidate.
`MO-S.6D-PROFILE-SETUP.1A` is **PRODUCTION APPLY COMPLETE / VERIFIED**. The
product-owner-reviewed reset created exactly 52 canonical 2026 Bethany 09:30
`bethany_0930_cm` ServiceEvents with exact CM audience, and the production
post-reset audit returned `PROFILE SETUP READY`. The Slice 8 target-event setup
prerequisite is closed; Slice 8 is implemented. Docs/read-only
`MO-S.6D-SLICE9.0A` now freezes the separately approved confirmation-write
contract and repository audit. `MO-S.6D-SLICE9.1A` is now **PRODUCTION APPLY COMPLETE / VERIFIED** as the
distinct signed 52-target atomic confirmation runtime. The product-owner-reviewed
production confirmation applied the reviewed annual Worship Team selection set.
A fresh re-upload of the same workbook then produced 52 no-op rows, 0 proposed
changes, 0 blocked rows, and no confirmation action, confirming that production
now matches the reviewed workbook.

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
  current governed runtime uses it as the event-level selection of the team
  that owns Worship for that
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
  event window. It shows events where that team is required, currently assigned,
  or the exact valid eligible selected Worship Team, uses a server-locked
  event/team form, and updates the existing event/team assignment rather than
  duplicating it.
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
warning when Worship changes. It now provides the controlled `.xlsx` upload/parse/preview flow and the
separately governed atomic confirmation/write runtime. The system still does not provide the MO-S.6E
roster-change staleness mechanism.
MO-S.6D-0A-FU1/FU2 define how
a future explicitly configured Worship rotation pool, event audience, and
primary Ministry Structure path determine eligible teams without treating a
name such as C2 as semantic proof. They also require explicit exact-event
planner/coordinator responsibility for the approved planner workflow.
`MO-S.6D-1A` has implemented the semantic Campus / Site type foundation, and
`MO-S.6D-1B` has implemented Worship-specific pool metadata, validation,
fail-closed primary-anchor configuration inspection, existing staff setup UI,
and Ministry Structure readiness integration. `MO-S.6D-1C` now provides the
explicit exact-ServiceEvent/user planner/coordinator responsibility lifecycle,
current-only active-user lookup, and full-manager bilingual setup UI.
`MO-S.6D-1D-A` now provides side-effect-free event applicability, deterministic
active-primary-path Worship Team candidates, and pool-aware current ownership
consistency. It reuses the existing pool inspection, treats scheduled /
confirmed / prepared as current, reports off-team, inapplicable-pool, multiple,
and duplicate conflicts, and exposes no roster/private data. These domain facts
accept no user and grant no permission by themselves. `MO-S.6D-1D-B` now
provides the narrow Worship Team authorization and selector/mutation UI and
enforces ownership on supported existing assignment writes. `MO-S.6D-1D-C`
now provides selected-team operational reachability on Team Schedule and the
Sunday Board without false coverage. `MO-S.6D-1D-D-1A` now provides the
read-only Worship Rotation Planner proposal/preview, and `1A-FU1`
distinguishes terminal blank, exact-ID cycle-closed, and true displaced tail
outcomes without adding preview writes. The system now provides optimistic
planner confirmation/shared audit, a closed docs-only direct-change
notification contract, and the bounded `NOTIFY.1G` producer. The controlled XLSX dependency/parser/upload/read-only-preview runtime is now
implemented and production-smoke-passed. 

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
   an existing roster. `MO-S.6D-1D-B-FU1` enforces this across supported write
   paths: any persisted or proposed Worship row has immutable event/team
   identity, including valid current rows and downstream-to-Worship retargets.
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
non-draft/non-cancelled Sunday Service rows when participation comes from a
required team, current operational assignment, or exact valid eligible selected
Worship Team. Generic participating team columns remain derived only from
required teams plus current operational assignments. The dedicated Worship
column exclusively owns the canonically valid eligible selected Worship Team,
so that same event/team pair is omitted from its generic team cells. An invalid
or stale raw selection remains review-required in the Worship column but never
suppresses independent required-team or current-assignment participation from
the generic cells.

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
The Worship context uses the same navigation rule only when the selected team
remains canonically eligible, the viewer can manage that exact active,
assignable team, and its current assignment is unambiguous. Downstream team
owners remain read-only.

### Board access and permission design

Board access is an operational scheduler capability. Staff, superusers, and
users with the global TeamAssignment manager capability receive the bounded
Sunday operational set when a row has at least one required team, current
operational assignment, or valid selected Worship Team. An exact-team
Lead/Coordinator receives a row only when at least one of that user's
canonically manageable teams is required, currently assigned, or the valid
selected Worship Team. Participation by an unrelated team, planner
responsibility, or pool-level role cannot establish exact-team row scope.

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
`ServiceEventRequiredTeam` teams, current `TeamAssignment` teams, and the exact
valid eligible selected Worship Team. Generic display columns intentionally use
only the required/current-assignment union after subtracting the
event's exact canonically valid eligible selected Worship Team; their
cross-event union is ordered by canonical team name and ID. An invalid or stale
raw `rotation_anchor_team` never suppresses independent required-team or
current-assignment participation. This preserves selected-team scheduler row
scope, avoids duplicate Worship cells for a valid selected-team event, and
still shows the team normally when it participates independently or on another
event. The table
labels inactive teams and shows a non-participating dash where a column appears
only for another event. The anchor remains an ordinary configured
`MinistryTeam`, not a global Worship taxonomy.

## 7. Worship-led coordination and suggestions

Downstream team scheduling should receive a compact context panel for the
selected Sunday:

- current `rotation_anchor_team`, if set;
- current Worship `TeamAssignment` summary and roster only for a canonically
  consistent exact selected-team assignment and when the viewer is authorized
  to see it;
- “Worship not yet scheduled” only for the canonical selected-unscheduled
  state; ownership conflicts are review-required instead;
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
by requiring a match/update-only first lifecycle, the now-implemented explicit
Worship-specific rotation-pool configuration foundation, required exact-event
planner/coordinator responsibility, audience applicability, eligible token
mappings, and the now-implemented selected-team-only operational reachability.
The remaining prerequisite runtime slices and importer-owned decisions still
require separate approval.

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
- valid selected Worship Team with no current Worship assignment: show “not yet
  scheduled”; canonical ownership conflict: show review-required and fail
  closed on the Worship action;
- Worship assignment changed: warn/review, never rewrite downstream rows;
- duplicate target assignment: block or route through existing duplicate-safe
  edit behavior;
- inactive/non-assignable team: reject new scheduling/import target while
  preserving appropriate historical visibility;
- stale board form or preview: reload and re-check current rows before write;
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

- Status: implemented; later MO-S.6D slices remain separately scoped and
  require explicit approval.
- Goal: let a downstream scheduler understand current Worship context and
  review a safe suggestion.
- Scope delivered: a shared read-only presenter consumes the canonical 1D-A
  ownership inspection. It distinguishes no selection, selected-unscheduled,
  consistent empty/scheduled roster, invalid selection, off-team/out-of-scope
  conflict, and multiple/duplicate ambiguity. Only a consistent exact selected-
  team assignment projects active member display names; conflict/ambiguous
  states remain roster-free in the Worship context. The Board and Sunday Team
  Schedule show only selected team name, coarse state, and permitted active
  member display names.
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
  de-duplication removes only the canonically valid eligible selected Worship
  Team from the event's generic cells; it is presentation-only and does not
  reduce row authorization or independent required/current-assignment
  participation. An exact selected-team manager may navigate from the context
  cell to the existing exact-event/assignment Team Schedule flow; downstream
  managers remain read-only under the canonical management predicate.
  Duplicate and unavailable selections expose no Worship action.
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

- Status: canonical architecture closure complete through FU2, with the
  separate `MO-S.6D-1A` Campus / Site and `MO-S.6D-1B` Worship rotation-pool
  configuration foundations and `MO-S.6D-1C` exact-event planner/coordinator
  responsibility foundation implemented. `MO-S.6D-1D-A` also implements the
  read-only applicability/candidate/ownership-consistency domain half of the
  canonical slice 4. `MO-S.6D-1D-B` implements its narrow authorization,
  selector/mutation UI, legacy write-path enforcement, and audit half, with
  FU1 closing assignment identity and ServiceEvent-first structural ordering.
  FU2 makes
  exact-event planner/coordinator responsibility a required prerequisite and
  fixes the pool semantic as Worship-specific. `MO-S.6D-1C` adds the explicit
  responsibility model, active/inactive lifecycle, current-only active-user
  lookup, existing full-manager setup controls, and admin exposure. The 1C
  source grants nothing by itself; 1D-B consumes it only for the exact-event
  Worship Team action. It does not add queryset visibility/reachability, an
  importer, or normal-data changes.
- Canonical decision: see
  [`WORSHIP_ROTATION_GOVERNANCE_PLAN.md`](WORSHIP_ROTATION_GOVERNANCE_PLAN.md).
- Church Structure: `MO-S.6D-1A` implemented the semantic-only Campus / Site
  type while preserving a flexible tree and the separation between structure,
  belonging, audience, permission, and serving.
- Pool applicability: an active, non-assignable MinistryTeam may now be
  explicitly marked with `is_worship_rotation_pool`, and its configuration can
  be inspected through the active primary path to one active Church Structure
  anchor. The implemented 1D-A/1D-B consumer considers it applicable only
  when that anchor is equal to or below a selected active event audience unit.
  The configuration is Worship-specific and grants nothing by itself. Audience
  establishes applicability, never authority.
- Candidate anchors: the union of active assignable descendants of all
  applicable pools through active primary MinistryTeam parent paths. Names,
  fuzzy matching, database IDs, `team_kind`, and role profiles are excluded.
- Ownership invariant: the selected team owns Worship for that occurrence. A
  missing Worship assignment is an unscheduled state; any current Worship
  assignment that exists must be for that exact team. An off-team or duplicate
  roster is invalid/ambiguous and fails closed. Selection changes never move,
  retag, clone, cancel, or rewrite an existing roster.
- Authority: full ServiceEvent managers, an explicit event planner/coordinator,
  or an active date-valid Lead/Coordinator on an applicable pool may use the
  implemented narrow Worship-Team-only action. Exact child-team roster authority remains
  unchanged and never flows from a pool role.
- Event responsibility: the approved workflow requires a lifecycle-managed
  user + exact-ServiceEvent planner/coordinator foundation before the narrow
  selector ships. `MO-S.6D-1C` implements that responsibility source as one
  unique event/user row with explicit add, end, and restore, but intentionally
  grants no general event visibility or full-event action. The implemented
  `1D-B` selector consumes it narrowly; it is not replaced by `created_by` or full
  `CAP_MANAGE_SERVICE_EVENTS`.
- Read-only governance: `ministry.services.worship_governance` now resolves
  active applicable pools from event audience, active assignable candidates
  through deterministic primary paths, and the stronger current Worship
  ownership state. `MO-S.6D-1D-B` consumes those facts from the atomic/stale-
  checked narrow selector and the canonical TeamAssignment write guard.
  `MO-S.6D-1D-C` now
  also consumes canonical selected-team eligibility for Board/Team Schedule
  reachability and the Board Worship action. Its shared presenter maps the
  canonical ownership state so off-team/out-of-scope conflicts are never
  downgraded to selected-unscheduled, and multiple/duplicate states remain
  ambiguous and non-actionable.
- Governed mutation: the contextual Worship Planning page lists only bounded
  upcoming exact events currently authorized for the user, including initial
  no-selection cases. The exact-event selector enters an atomic transaction,
  requests/reloads current event state, reauthorizes, compares expected
  `updated_at` and old team, recomputes 1D-A facts, changes only the selected
  Worship Team, and writes one same-transaction `LogEntry` for a real change.
  Normal/recurring ServiceEvent forms and ServiceEvent Admin
  no longer provide a direct anchor write. Supported current Worship
  TeamAssignment writes must match the valid eligible selected team; existing
  conflicts may still cancel/complete in place, but are never silently
  retargeted as repair. `MO-S.6D-1D-B-FU1` also makes event/team identity
  immutable for every supported persisted/proposed Worship boundary and
  requests ServiceEvent-first ordering before revalidation. Member confirmation
  follows ServiceEvent -> assignment -> member order and validates the parent
  before any member side effect. Target SQLite does not implement
  `select_for_update()` row locks, so FU1's model/domain validation, identity
  rule, atomic rollback, and ordering code remain implemented but do not supply
  a strict target row-lock guarantee. Implemented `1B-A1` now closes that gap
  with one event scheduling revision plus SQLite write serialization and
  current-truth recomputation. Raw SQL and future arbitrary bulk updates
  remain outside the application-level claim.
- Reachability: `MO-S.6D-1D-C` implements the exact current valid selected
  Worship Team as a third operational relevance predicate beside required-team
  and existing-assignment participation. Selected-team-only rows keep empty
  coverage and render through the dedicated Worship presentation/action. It
  creates or implies no required team, assignment, coverage, audience, serving
  row, permission grant, or notification.
- Import consequence: the former RequiredTeam bootstrap recommendation is
  superseded. The first importer remains exact existing-event match/update,
  maps tokens only to eligible candidates, blocks on current Worship-roster
  conflicts, changes only the selected Worship Team, and is staff/superuser-only
  for bulk upload/preview/confirm.
- Later operations: the existing exact-event selector remains the one-Sunday
  change path. The docs-only contract in
  [`WORSHIP_ROTATION_PLANNER_PLAN.md`](WORSHIP_ROTATION_PLANNER_PLAN.md) limits
  planner V1 to a bounded insert/shift of later explicit selections, with a
  terminal blank landing slot or exact-ID inserted-team cycle closure, no
  arbitrary tail loss, per-destination candidate
  validation, per-event authority, roster blockers, a 30-minute user-bound
  signed proposal, and implemented shared-operation per-changed-event `LogEntry`
  audit without a BatchRun schema. Read-only preview `1A` is implemented; the
  attempted row-lock closure `1B-A` stopped without changes because the target
  is SQLite. Docs-only `1B-A0` selects an event-owned scheduling revision,
  supported-write bump scope, and expected-revision CAS. Runtime `1B-A1` now
  implements and concurrency-tests that foundation; `1B-B` now consumes it and
  provides downstream-impact staleness for supported writes. A
  docs-only `NOTIFY.1G-0A` contract now defines the separate ministry-owned
  post-commit producer for direct old/new/downstream leadership notices,
  summarized once per recipient from that recipient's qualifying batch-event
  subset. `NOTIFY.1G` is implemented. This is distinct from MO-S.6E
  roster-change staleness detection.
- Copy: scheduler-facing UI should use Worship Team / 敬拜团队 rather than the
  engineering term rotation anchor.
- Dependency: the Campus, pool-configuration, event-responsibility, read-only
  governance, governed single-event mutation, operational reachability,
  read-only planner preview, docs-only SQLite optimistic contract, `1B-A1`
  scheduling revision foundation, and `1B-B` optimistic batch confirmation/
  shared audit are implemented. The direct notification architecture gate and
  bounded `NOTIFY.1G` runtime are implemented. Import and other genuinely future
  runtime slices remain separately scoped and require separate task approval
  and focused verification.

### MO-S.6D-1D-D-0A — Worship Rotation Planner contract and audit decision

- Status: docs-only contract complete; no runtime, schema, dependency,
  notification, or data change is implemented.
- Canonical decision: see
  [`WORSHIP_ROTATION_PLANNER_PLAN.md`](WORSHIP_ROTATION_PLANNER_PLAN.md).
- Product split: the existing selector owns one Sunday; planner V1 owns only
  Insert / Shift Later Worship Teams over 2 through 53 exact published future
  Sunday Service events.
- Historical `0A` safety decision: no interior blank, final blank landing slot,
  and no non-null displaced-tail confirmation. Implemented `1A` preview later
  supplied evidence for the narrow `1A-FU1` refinement below; this chronology
  is retained rather than rewriting `0A` as though it already contained it.
- Other safety: destination-specific canonical eligibility, per-event existing
  authority, and any current Worship assignment blocking an actual changed
  row.
- Proposal/audit: implemented preview uses a 30-minute user-bound Django-signed
  normalized proposal and writes no audit rows. Implemented `1B-B` uses normal
  per-event saves and one same-operation-ID `LogEntry` per actual change; no
  durable BatchRun model exists for V1.
- Runtime order: read-only proposal/preview `1A` is implemented. Attempted
  row-lock closure `1B-A` stopped without changes on target SQLite; docs-only
  `1B-A0` now closes the optimistic scheduling-revision architecture.
  Scheduling Revision Foundation `1B-A1` is implemented and passes real
  file-backed SQLite concurrency tests. Implemented optimistic confirmation/
  audit `1B-B` makes the bounded downstream-impact stale claim.

### MO-S.6D-1D-D-1A — Worship Rotation Planner read-only proposal/preview

- Status: implemented with no schema, dependency, data mutation, audit write,
  notification producer, session proposal, temp file, or confirmation action.
- Runtime: the contextual Worship Planning entry opens an explicit exact-event
  checkbox chain and inserted-team selector; parallel same-Sunday services are
  separate choices and selecting more than one for a Sunday is rejected.
- Domain: one reusable ministry service owns weekly-chain validation,
  deterministic insert/shift, blank/tail rules, destination eligibility,
  changed-row authority and assignment blockers, privacy-limited downstream
  projection, deterministic fingerprints, and 30-minute user-bound Django
  signing/decoding.
- UI: bilingual preview shows before/after/no-op, blockers, downstream impact,
  and displaced tail. Confirm Shift appears only for a confirmable proposal;
  preview remains side-effect free.
- Follow-on: `1B-B` owns confirmation/audit; notifications and importer work
  remain separately scoped.

### MO-S.6D-1D-D-1A-FU1 — Cycle-closed shift preview

- Status: implemented as a read-only product-contract refinement with no
  schema, dependency, permission, audit, notification, session/file state, or
  confirmation action.
- Evidence chronology: `0A` selected terminal-blank-only conservatively; real
  `1A` preview showed that a non-null tail exactly equal to the inserted team
  preserves the selected-range team multiset; FU1 refines the contract before
  any `1B` writes exist.
- Typed result: `terminal_blank` is safe; `cycle_closed` is safe when the exact
  displaced-tail team primary key equals the exact inserted-team primary key;
  every other non-null tail is `displaced` and keeps `DISPLACED_TAIL`.
- Signed boundary: proposal contract version 2 includes the non-sensitive tail
  semantic, and decode rejects missing, unknown, or ID-inconsistent values.
- Identity boundary: team name, A/C1/C2/C3 labels, pool position, inferred
  order, fuzzy matching, and history do not participate. This stores no
  rotation rule and approves no arbitrary tail drop.

### MO-S.6D-1D-D-1B-A0 — SQLite optimistic scheduling-concurrency contract

- Status: docs/read-only architecture decision complete; no runtime, field,
  migration, data, confirmation, audit, notification, or permission change.
- Repository truth: local and GoDaddy settings both use SQLite; the inspected
  local database uses rollback-journal mode, and Django reports
  `has_select_for_update=False`. The preceding `1B-A`
  attempt therefore stopped without changes instead of claiming a false event
  row lock.
- Corrected FU1 truth: Worship model/domain validation, immutable identity,
  atomic rollback, deterministic ordering code, and member-confirmation parent
  revalidation remain implemented; target SQLite supplies no actual
  ServiceEvent row-lock guarantee.
- Implemented A1 adds one internal monotonic
  `ServiceEvent.scheduling_revision` field. Supported event fingerprint,
  audience/required-team, current-assignment create/edit/status/retarget/delete,
  Admin/cascade, member-confirmation parent-status, and Lighting mutations
  advance affected event revisions atomically. A downstream Event A -> Event B
  retarget advances both in deterministic ID order.
- Exclusions: pure roster/member changes, notes, and confirmation detail do not
  advance solely for planner staleness unless the parent status also changes.
  ServiceEvent deletion needs no tombstone because future CAS cannot find it.
- SQLite barrier: ordinary mutations use an atomic database-expression
  increment before reload/revalidation. Implemented `1B-B` conditionally increments
  every selected event from its signed expected revision before any final
  governance/authority/fingerprint read; the first successful write establishes
  SQLite's database-wide writer boundary, not a row lock.
- Confirmation: every selected event, including a no-op context row, advances
  revision on success; only actually changed Worship Team rows receive
  shared-operation `LogEntry` audit. Any stale CAS, recomputation conflict, save,
  or audit failure rolls back every revision claim and change.
- Test gate: A1 proves stale CAS, writer
  exclusion, rollback restoration, and no partial batch commit with two real
  connections to a file-backed SQLite database under target-like journal/
  timeout behavior. Ordinary in-memory/TestCase coverage is insufficient.
- Runtime split: implemented `1B-A1` owns the field/migration, helpers,
  supported-write retrofit, and concurrency tests; implemented `1B-B` owns
  signed confirmation, CAS, recomputation, anchor writes, replay/stale handling,
  and shared audit.

### MO-S.6D-1D-D-1B-A1 — Scheduling Revision Foundation

- Status: implemented. Additive migration `events/0010` introduces the internal
  non-editable event revision with default zero and no data operation.
- Supported scheduling writes advance affected event revisions with database
  expressions inside their mutation transaction, then reload/revalidate current
  identity, authority where the caller owns it, and Worship governance.
- Current assignment retargeting advances old and new events in ascending ID
  order. Rollback covers revision increments, domain writes, audit, and existing
  on-commit notification behavior. Notes/member-only detail remains non-staling.
- Admin object/bulk deletion and MinistryTeam cascades are explicitly covered;
  arbitrary raw SQL, shell/queryset bulk mutation, and newly added write paths
  remain outside the supported-write guarantee until inventoried.
- Planner signed proposal contract version 3 includes every selected event's
  expected revision and rejects old/missing tokens, but remains read-only.
- Real file-backed, two-connection SQLite tests prove stale CAS, writer
  exclusion, rollback restoration, busy retry, and no partial multi-event claim.
  This is optimistic revision plus SQLite database-wide writer exclusion and
  current-truth recomputation—not a row-level lock or general scalability claim.
- Prerequisite status: A1 is closed and consumed by implemented `1B-B`.

### MO-S.6D-1D-D-1B-B — Optimistic Batch Confirmation & Shared Audit

- Status: implemented with no new schema, migration, dependency, notification,
  import, assignment, roster/member, required-team, audience, planner, or
  Church Structure mutation.
- Runtime: a dedicated POST-only route accepts only the signed proposal token,
  shape-checks it before transaction work, claims every selected event revision
  in ascending ID order as the first scheduling/governance database access,
  then reloads and recomputes exact chain, authority, governance, ownership,
  tail, and downstream facts before any anchor save.
- Atomicity/audit: selected revisions advance exactly once on success, changed
  anchors save in semantic order without a second revision bump, no-op rows do
  not save/log, and changed rows receive one `LogEntry` each with the same signed
  operation ID. Stale, busy, replay, validation, save, or audit failure rolls
  back the entire batch.
- UI/evidence: explicit bilingual Confirm Shift is shown only for confirmable
  previews; focused tests and rendered English desktop/Chinese mobile QA cover
  success, blockers, replay-safe retry, responsive layout, narrow authority,
  privacy, concurrency, and zero cross-domain writes/notifications.

### NOTIFY.1G-0A — Direct Worship Team Change Notification Contract

- Status: docs complete; `NOTIFY.1G` runtime is implemented.
- Trigger: actual committed selected-team changes through the exact selector or
  `1B-B` only; no-op, preview, stale/blocked/failed, replay, rollback, and
  unsupported write paths emit nothing.
- Recipients: active users with current active/date-valid exact Lead/Coordinator
  roles on the old team, new team, active required downstream teams, or active
  additional downstream teams with a `scheduled`/`confirmed`/`prepared`
  assignment. Completed/cancelled rows do not qualify, and primary-path Worship
  teams never re-enter through downstream classes.
- Aggregation/privacy: exact-user dedupe, at most one notification per recipient
  per single operation or batch, and a batch summary contains only that
  recipient's qualifying changed Sundays.
- Identity/target: single audit LogEntry identity, shared batch `operation_id`,
  stable `worship_team.changed` / `worship_rotation.changed` types, and common
  permission-neutral `reverse("my_serving")` target.
- Snapshot/timing: recipient-language date and localized old/new team only;
  batch preview capped at three entries plus a remainder count; source-owned
  resolution and Core registration remain inside the successful source
  transaction, with persistence after commit.
- Scope: no schema, permission, new route/UI, background job, external delivery,
  or relationship to later roster-context staleness in `MO-S.6E`.

### MO-S.6D-PROFILE.1A — Stable Service Profile Identity Foundation

- Status: **IMPLEMENTED AND COMMITTED IN CURRENT HEAD** as one additive,
  optional ServiceEvent field and migration.
- `ServiceEvent.service_profile_key` is a non-unique, machine-oriented stable
  integration/profile identity for the recurring service profile represented
  by one exact event. Existing rows safely default to an empty key.
- Non-empty keys accept only lowercase ASCII letters, digits, underscore,
  hyphen, and period. The field is deliberately absent from ordinary
  ServiceEvent and recurring-event forms; Django Admin is the narrow technical
  setup surface.
- The key grants no audience, visibility, permission, Campus, Host / Language,
  location, recurrence, serving, RequiredTeam, assignment, Calendar,
  notification, or future-event-creation meaning. It is not a scheduling source
  of truth.
- The first approved SVCA workbook setup value is `bethany_0930_cm`. This value
  is deployment/setup data, not a global CMS semantic. No existing event is
  inferred or tagged from title, location, Host / Language, time, audience, or
  selected Worship Team.
- Existing-event key changes use the existing ServiceEvent save barrier and
  advance `scheduling_revision`; validation failure rolls back that advance.
  This makes later profile-aware proposals stale when identity changes without
  introducing a second counter.
- Excel dependency/parser/read-only preview is **IMPLEMENTED
  (`MO-S.6D-SLICE8.1A/FU1`)**. It declares `openpyxl==3.1.5`, enforces the
  code-owned 2026 workbook contract, matches only exact persisted-profile
  targets, and exposes a staff/superuser-only zero-write preview. The allowed
  token grammar remains exactly A/C1/C2/C3, but mapping controls and signed
  mapping state contain only tokens actually present in the accepted workbook;
  an omitted or ineligible selection remains visible as a blocked row rather
  than preventing preview. The setup command remains separate from importer
  runtime. `MO-S.6D-SLICE9.0A` freezes the confirmation-write contract, and
  `MO-S.6D-SLICE9.1A` implements it with local verification only.

### MO-S.6D-PROFILE-SETUP.0A — Bethany 09:30 Target Event Readiness Audit

- Status: **READ-ONLY AUDIT TOOL IMPLEMENTED AND COMMITTED IN CURRENT HEAD**.
  The command is
  `audit_service_profile_readiness`; it has no `--apply`, no backfill, no
  automatic tagging, no Excel/parser dependency, and no mutation mode.
- The default, documented SVCA contract is profile key `bethany_0930_cm`, local
  year `2026`, exact configured-local-time `09:30`, and event type
  `sunday_service`. The expected set is independently constructed as every
  seven days from `2026-01-04` through `2026-12-27` (52 Sundays); UTC clock
  time is never used as service-profile identity.
- Only persisted `ServiceEvent.service_profile_key == "bethany_0930_cm"` is
  canonical profile identity. Untagged exact-09:30 events are printed only as
  `UNTAGGED CANDIDATE / HUMAN REVIEW REQUIRED`; multiple candidates require
  human selection, and title, location, Host / Language, audience, or selected
  Worship Team resemblance never selects or ranks a target.
- `--event-type` controls both canonical validation and candidate discovery;
  the default `sunday_service` contract is unchanged. A supplied profile key
  longer than the persisted field's 64-character maximum is rejected.
- Each expected Sunday reports four distinct requested-type categories:
  canonical requested-profile rows; untagged exact-time candidates; exact-time
  events already owned by another non-empty profile key; and same-day events at
  different times. Other-profile exact-time rows are informational parallel-
  service evidence only, labeled not a candidate, never counted or ranked as a
  target, and never make the requested profile ready.
- Canonical rows are classified for wrong type/time/date, lifecycle state,
  duplicates, out-of-contract rows, and audience readiness. Zero audience rows
  retain the canonical ordinary-user fail-closed meaning; inactive or
  ancestor/descendant-overlapping audience evidence blocks readiness but is
  never repaired.
- Before querying ServiceEvent data, the audit separately reports migration
  recorder plus physical-schema evidence for `events/0009`, `0010`, and `0011`.
  Missing schema stops cleanly before ORM event queries, avoiding a raw missing-
  column traceback. Optional `--json` prints the same deterministic,
  privacy-bounded facts to stdout only.
- `PROFILE SETUP READY` requires one and only one exact, published/completed,
  audience-ready canonical tagged row on each of all 52 expected Sundays, with
  no unexpected/duplicate profile rows. Any number of untagged lookalikes is
  insufficient.
- The normal local development DB probe reported all three migrations
  unapplied and their schema targets absent. Result: `Schema: NOT READY`,
  ServiceEvent data `NOT EVALUATED`, recommendation
  `NOT READY FOR SLICE 8 REAL-DATA MATCHING`. No migration was applied and no
  data was changed.
- The product owner subsequently ran and reviewed this audit on GoDaddy.
  Production reported migrations `events/0009`, `0010`, and `0011` applied and
  physically present (`Schema: READY`), 52 expected Sundays, zero canonical
  tagged rows/ready exact matches, 52 missing canonical-profile Sundays, seven
  single untagged exact-09:30 candidate Sundays, 45 Sundays with no 09:30
  candidate, zero multiple-candidate Sundays, and zero other-profile exact-time
  events. The recommendation was
  `NOT READY FOR SLICE 8 REAL-DATA MATCHING`.
- The seven candidates were event IDs 38-44, covering `2026-08-16` through
  `2026-09-27`. Product-owner review confirmed they were Bethany 09:30 Chinese
  Sunday Worship events, then explicitly declared the current ServiceEvent/
  scheduling dataset disposable TEST DATA and approved reset/rebuild rather
  than in-place tagging.
- The reviewed production command was run from the GoDaddy application
  directory:

  ```bash
  /home/rsnwvvl103hc/virtualenv/app_read/3.11/bin/python manage.py audit_service_profile_readiness
  ```

  This completed production audit still did not authorize profile assignment
  or reset APPLY; it established the reviewed pre-reset production truth only.
- This was the reviewed **pre-reset** audit result. The later product-owner-
  reviewed post-reset audit supersedes it for current readiness and returned
  `PROFILE SETUP READY` with 52/52 ready exact matches.

### MO-S.6D-PROFILE-SETUP.1A — Canonical Bethany 09:30 Test-Data Rebuild

- Status: **PRODUCTION APPLY COMPLETE / VERIFIED**.
  `rebuild_bethany_0930_service_events` is read-only by default; mutation
  requires `--apply`, `--confirm-test-data-reset`, and
  `--expected-reset-token <token>` and must run in a maintenance window. No
  APPLY was run during command implementation; the product owner later ran and
  reviewed the production workflow.
- The verified production reset deleted 44 ServiceEvents, 45 audience rows,
  102 required-team rows, zero planner assignments, 23 TeamAssignments, and 29
  assignment-member rows. Zero BibleStudyMeeting links were cleared by
  `SET_NULL`. It created 52 ServiceEvents and 52 audience rows, with
  `data_mutated: true` and postcondition `PROFILE SETUP READY`.
- The final production audit reported schema ready, 52 expected Sundays, 52
  canonical tagged rows, and 52 ready exact matches. Missing, duplicate,
  wrong-time/type/date, unexpected, draft, cancelled, zero-audience, and
  invalid-audience canonical counts were all zero. It recorded 34 completed
  historical canonical rows and no remaining untagged-candidate or other-
  profile exact-time ambiguity.
- The product owner explicitly declared the current ServiceEvent/scheduling
  rows disposable TEST DATA. The reset deletes all `ServiceEvent` rows and the
  event-owned audience, required-team, planner, TeamAssignment, and assignment-
  member rows reached by their existing cascade semantics. A linked
  `BibleStudyMeeting` survives with its nullable `service_event` link cleared.
  Generic Notification and `LogEntry` history is retained.
- The reset does not delete the database or unrelated users/admin accounts,
  Church Structure or belonging, Ministry Teams/memberships/hierarchy/roles,
  Worship pools, permissions, Bible Study rows, Reading, Prayer, Community
  Activities, Announcements, or unrelated notifications.
- The intended audience is resolved without PK/name guessing as exactly one
  active persisted `CHURCH -> campus -> CM` path. Missing, inactive, wrong-
  shape, or ambiguous structure blocks before deletion; no structure row is
  created.
- One atomic transaction rechecks schema/structure/current reset scope, deletes
  the approved test dataset, creates exactly the 52 Sundays from `2026-01-04`
  through `2026-12-27` at configured-local `09:30`, creates exactly one CM
  audience row per event, and verifies all postconditions through
  `audit_service_profile_readiness` before commit. Any failure rolls back the
  deletion and partial rebuild.
- Every new event is `sunday_service`, titled `主日崇拜` / `Sunday Service`, and
  has profile `bethany_0930_cm`, blank location/link/descriptions, CM Host /
  Language display, `rotation_anchor_team = NULL`, and creation-time
  `scheduling_revision = 0`. Sundays strictly before APPLY's local date are
  completed; all others are published. No assignment, roster, planner,
  required-team, notification, or synthetic audit history is created.
- An already exact dataset is a no-op for the same local-date lifecycle truth;
  it never appends a second 52-event series. The command emits a preflight
  fingerprint, exact deletion/dependent counts, all existing event rows, all 52
  proposed replacements, retained-history counts, and explicit preserved-
  domain boundaries.
- The dry-run emits a 16-character lowercase hexadecimal reset approval token,
  derived from a full canonical SHA-256 payload binding the reset-surface
  fingerprint, resolved persisted audience path (unit/ancestor PK, parent,
  code, and type), local `today`, timezone, profile key, year, local time, and
  event type. The token is stale-state/reviewed-state binding, not an
  authentication credential. APPLY recomputes it inside the transaction before
  deletion; any mismatch stops zero-write and requires a new reviewed dry-run.
- This is explicit setup data only. The Slice 8 workbook preview does not create
  ServiceEvents, infer audience, create RequiredTeam, create TeamAssignment or
  serving rows, or import assignment members. `MO-S.6D-SLICE8.1A/FU1` is
  implemented as a separate dependency/parser/read-only-preview slice and has
  no confirmation or apply path.

### MO-S.6D-0A — Workbook Contract & Imported-Sunday Readiness

- Status: historical docs-only investigation complete. This section by itself
  approved no importer, runtime surface, schema, dependency, or data change;
  the later separately approved `MO-S.6D-SLICE8.1A/FU1` now implements the
  dependency/parser/read-only-preview subset while retaining this contract.
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

`MO-S.6D-PROFILE.1A` supersedes the earlier location/Host candidate with the
explicit optional `ServiceEvent.service_profile_key`. The supported workbook
contract expects `bethany_0930_cm`; this church-specific expectation is not a
global CMS semantic. Title, location, `host_language_unit`, end time, audience,
annotations, and selected Worship Team are not profile identity and must not
infer or auto-tag the key. `host_language_unit` remains display-only and never
supplies audience.

Matching must use the configured local timezone and require exactly one
non-cancelled candidate with the exact minute, event type, and profile
discriminator. An audience-invalid candidate is not import-ready. Multiple
candidates, a cancelled candidate, or a same-date row whose time, type, or
profile disagrees is a conflict with no write; the importer must not select a
closest match or silently create a second event around a conflict.

#### Event-plus-selected-Worship-Team reachability gate — implemented

For an imported `ServiceEvent` with `rotation_anchor_team = Worship C2`, no
`ServiceEventRequiredTeam` for C2, and no `TeamAssignment`:

A. The exact C2 Lead/Coordinator can reach that valid selected-team-only event
   through Team Schedule and open the normal exact-event Schedule action.
B. The C2 Lead/Coordinator and a global assignment manager can see the bounded
   Sunday row on the Board.
C. The row has no fabricated generic coverage cell; C2 appears only in the
   dedicated Worship column as selected and not yet scheduled.
D. Planner/pool-Lead selection authority alone still grants neither roster
   workspace nor Board row scope for the selected child team.

`MO-S.6D-1D-C` closes the former workflow dead end as derived operational
reachability. It does not make `rotation_anchor_team` a required team,
assignment, coverage source, audience source, serving row, or permission grant.

#### Required-team bootstrap recommendation (superseded by FU1)

New events currently receive required teams only through explicit per-event
selection in the single-event or recurring-event forms. The repository has no
event template, canonical Sunday required-team preset, reusable setup
configuration, or required-team copy-forward source for an importer.

- Option A, event plus selected Worship Team followed by manual setup, is now
  operationally reachable through the implemented bounded scheduling surfaces.
- Option B cannot be used because no canonical reusable required-team
  configuration exists.
- Option C makes the exact current valid selected Worship Team a narrow operational-relevance
  predicate without changing coverage meaning.
- Option D would create an explicit `ServiceEventRequiredTeam` solely for
  discoverability, falsely asserting expected coverage.

MO-S.6D-0A-FU1 approved Option C and superseded the former Option D
recommendation. `MO-S.6D-1D-C` implements it: Team Schedule and Sunday Board
treat the exact canonically eligible selected Worship Team as operationally
reachable while keeping it outside required/additional coverage. No
`ServiceEventRequiredTeam` or `TeamAssignment` is created by reachability.

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
authority surfaces. `MO-S.6D-1D-B` implements the narrow one-event action
authorized by MO-S.6D-0A-FU1/FU2 for full ServiceEvent managers, an explicit
lifecycle-managed exact-event
planner/coordinator, or an active date-valid Lead/Coordinator on an applicable
configured Worship rotation pool. The event-responsibility foundation is a
consumed prerequisite for the planner use case and is not replaced by full
`CAP_MANAGE_SERVICE_EVENTS`. The action changes only the selected Worship Team
and does not grant general event management. The first
annual upload/preview/confirm workflow should be staff/superuser-only at both
preview and confirmation. Exact-team assignment authority, audience, and pool
leadership do not confer bulk import or event-creation authority. A future slice
that writes assignments would additionally require corresponding exact-team and
bulk authority, but assignments are outside MO-S.6D.

`requirements.txt` now declares `openpyxl==3.1.5`; its required
`et-xmlfile==2.0.0` dependency is installed in the repository virtual
environment. Local import and workbook parsing are verified on Python
3.14.7/Django 5.2. Direct
product-owner cPanel verification confirms that the GoDaddy Python App
`AMAXTW.COM/APP_READ` uses Python 3.11.15, retains the existing `3.11`
virtualenv, and has no Python 3.14 option in the observed selector. Therefore
the Python 3.11 path in `deploy_godaddy.sh` remains aligned with production;
`DEPLOY-PYTHON.1A` is closed with no script change required. Production smoke
subsequently confirmed that `openpyxl 3.1.5` imports successfully in the exact
GoDaddy Python 3.11.15 runtime and that the parser reads the real xlsx
server-side without Excel/LibreOffice.

#### MO-S.6D Slice 8 implementation result

MO-S.6D-0A-FU1/FU2 close the lifecycle, Worship-pool/candidate,
event-responsibility, operational-reachability, and initial bulk-authority
architecture: first lifecycle is exact existing-event match/update; mapping is
limited to eligible teams from applicable configured Worship pools; the
selected Worship Team is operationally reachable without a RequiredTeam
bootstrap; the event-planner responsibility foundation is required; and first
bulk import is staff/superuser-only. The Campus and pool-configuration
foundations, the event-planner responsibility foundation, the read-only
applicability/candidate/consistency foundation, governed `1D-B`
authorization/mutation enforcement, and `1D-C` operational reachability are now
implemented; all other prerequisites remain documentation decisions only.

`MO-S.6D-PROFILE.1A` supplies the stable field and approves
`bethany_0930_cm` as the first setup value. `PROFILE-SETUP.0A` is committed,
and `PROFILE-SETUP.1A` completed its product-owner-reviewed production apply and
post-reset audit. The canonical target-event setup prerequisite is closed with
52/52 ready exact matches and `PROFILE SETUP READY`.

`MO-S.6D-SLICE8.1A/FU1` implements the strict known-workbook parser and
staff/superuser-only read-only upload/preview with exact persisted-profile event
matching. The accepted token vocabulary is A/C1/C2/C3; only tokens actually
present in the parsed rows require explicit reviewed mapping to the current
union of canonical eligible Worship teams. A missing selection, no eligible
union, or per-destination ineligibility produces a readable blocked preview.
Target blockers take precedence over mapping blockers, which take precedence
over governance blockers. The normalized parsed and preview states are
timestamped, compressed, signed, user-bound, and contain no workbook binary,
ignored person names, notes, or roster-member detail.
Preview does not mutate a ServiceEvent, its Worship Team, audience,
RequiredTeam, TeamAssignment, serving rows, assignment members, notification,
or audit data. Slice 8 alone does not authorize confirmation; the separately
approved `MO-S.6D-SLICE9.1A` runtime owns that explicit POST boundary.

The production read-only smoke is **PASSED**: GoDaddy Python 3.11.15 imported
openpyxl 3.1.5, accepted the real workbook, and produced 52 supported Sundays,
52 exact matched targets, zero no-op rows, 52 proposed changes, zero blocked
rows, and `Complete` token mapping. Product-owner review confirmed that the
preview data looked correct. This verifies only the Slice 8 production preview
path; it is not Slice 9 readiness or write-path evidence.

The accepted production workbook observation was 12 A, 13 C1, 13 C2, and 14 C3
rows. Those counts are evidence, not a runtime invariant: the parser derives
counts from accepted rows while retaining the fixed vocabulary, 52-row total,
and exact date/formula/special-row contract. Its measured archive has 46 ZIP
members, 2,291,811 declared uncompressed bytes, and a 631,391-byte largest
member. Pre-openpyxl resource preflight therefore caps upload size at 5 MiB,
member count at 128, total declared uncompressed content at 20 MiB, and any one
member at 8 MiB; encrypted members are rejected and no archive content is
extracted.

Slice 8 preserves the strict sheet/header/date/formula/special-row contract,
match conflicts, the staff/superuser bulk boundary, no assignment/person/team
creation, zero writes, and no notifications. Under the docs-complete
`MO-S.6D-SLICE9.0A` contract, a separately authorized Slice 9 runtime owns
confirmation-time reauthorization and stale checks, atomic selected-team
writes/rollback, attribution, audit/result handling, and idempotency.

### MO-S.6D-SLICE9.0A — Excel Confirmation Write Contract / Repository Audit

Status: **CONFIRMATION WRITE CONTRACT / REPOSITORY AUDIT COMPLETE**.

This section records the completed docs/read-only architecture decision as it
stood before runtime implementation. At the `SLICE9.0A` gate, runtime was
**UNIMPLEMENTED** and this decision itself added no confirmation route, form,
template, service, test, dependency, schema, migration, data command,
notification, or application/data write. The later `SLICE9.1A` implementation
closure is recorded below.

#### Approved V1 authority and mutation boundary

Both the successful preview and implemented confirmation require an authenticated,
active staff user or superuser. Pool Lead/Coordinator, exact-event planner,
exact-team Lead/Coordinator, global assignment manager, audience membership,
Church Structure belonging, serving, and ordinary ServiceEvent management do
not grant annual-import authority. Confirmation must reload and recheck the
actor's active staff/superuser state inside the transaction before the
scheduling-revision CAS claim.

V1 operates on exactly the 52 supported existing events carried by one
reviewed proposal. Published and completed canonical events are accepted;
draft, cancelled, missing, duplicate, or otherwise no-longer-ready targets
block the whole batch. The only business-field write is:

```text
ServiceEvent.rotation_anchor_team
```

Every successful selected event also advances its existing internal
`scheduling_revision` exactly once as the concurrency claim. V1 creates,
deletes, or changes no ServiceEvent, audience row, RequiredTeam row, planner
row, TeamAssignment, TeamAssignmentMember, MinistryTeam, Church Structure,
membership, serving row, user, or assignment/member import record. It adds no
`ImportRun` schema and emits no notification.

#### Audited Slice 8 signed state and distinct confirmation proposal

Slice 8 currently signs two 30-minute, timestamped, user-bound states with its
dedicated salt/version:

1. `parsed_workbook` binds parser contract revision, generated time, user,
   sanitized filename, workbook SHA-256, supported sheet, exactly 52 normalized
   source rows (`source_row`, `source_cell`, local date, literal/cached date
   kind, workbook token), and derived present-token counts.
2. `normalized_preview` binds parser contract revision, generated time, user,
   filename/hash/sheet, explicit present-token-to-MinistryTeam IDs, and one row
   containing source row/cell/date/date-kind/token, target classification,
   exact ServiceEvent ID, expected current and proposed team IDs, preview
   classification/blocker, ownership state, parallel-event evidence count, and
   planner-style event/governance/current-Worship/downstream fingerprints.

The nested event fingerprint already includes the exact event ID, nonnegative
expected `scheduling_revision`, lifecycle/type/start/end/updated timestamps,
and expected current anchor. Governance fingerprints include active audience
IDs, applicable pool/anchor pairs, eligible team/owning-pool pairs, selected-
team eligibility, and ownership state. Current-Worship and bounded downstream
assignment fingerprints are also present. The exact persisted profile key is
not stored in that fingerprint; exact profile matching was represented by the
server-derived target classification and must be recomputed from current data.

The existing normalized-preview decoder validates the signature, expiry, user,
top-level state/version, row count, allowed row keys, token vocabulary/count,
mapping keys, and mapping-ID types. It does not provide the planner decoder's
full confirmation-grade validation of every row's canonical source semantics,
enum/value types, cross-field relationships, event/revision/team IDs, or
fingerprint shapes. Server-signed preview classifications and fingerprints are
review evidence, not current confirmation truth.

Slice 9 V1 therefore mints a **distinct, versioned confirmation proposal** only
from a successful, confirmable Slice 8 preview. It uses a dedicated confirmation
salt/type/version and retains the current 30-minute maximum age and exact user
binding. It does not re-upload, retain, or reparse the workbook at confirmation.
The minimal confirmation payload is privacy-bounded and contains:

- confirmation contract version/type and parser contract revision;
- one random operation UUID minted with the reviewed proposal;
- timestamp, previewing user ID, sanitized filename, and workbook SHA-256;
- the complete explicit present-token-to-team ID mapping; and
- exactly 52 canonical rows, each binding source row, local date, workbook
  token, exact event ID, expected pre-claim scheduling revision, expected-before
  anchor team ID, and proposed team ID.

The exact profile key `bethany_0930_cm`, exact local 09:30 time, event type,
supported dates/rows/token vocabulary, and 52-row total remain code-owned
parser/confirmation contract constants and are recomputed/shape-checked; they
need not be repeated as trusted DB classifications. Operation UUID and the
distinct confirmation contract/version are the only new semantic fields not
already bound by the current successful preview. The confirmation payload may
drop preview-only display classifications/fingerprints rather than treating
them as authorization or current truth.

The future preview exposes a functional confirmation action only when all of
these are true: structurally valid workbook; exactly 52 supported rows; exactly
52 exact canonical targets; complete explicit mapping for every present token;
zero blocked rows; at least one proposed change; and current staff/superuser
authority. Zero proposed changes renders `Already matches / nothing to apply`
and no write action. The future endpoint is POST-only and CSRF-protected.

#### Reusable 1B-A1 / 1B-B primitives and prohibited planner reuse

Slice 9 directly reuses `events.scheduling_revision.claim_scheduling_revisions`.
It already sorts exact `(event_id, expected_revision)` claims by event ID,
performs conditional database-expression updates, translates SQLite busy
errors, and rolls back earlier claims when any row is stale or missing. The
first successful update establishes the proven SQLite single-writer boundary;
this is not a row lock.

Changed anchors use the same supported post-claim save primitive as planner
`1B-B`:

```python
event.save(
    update_fields=["rotation_anchor_team", "updated_at"],
    _skip_scheduling_revision=True,
)
```

This preserves model validation while preventing an accidental second revision
advance. No-op rows are not saved. The future service also follows the proven
`transaction.atomic()`, reload-after-claim, changed-only `LogEntry`, shared
operation UUID, and exception-to-zero-write patterns.

Importer code must not call or copy planner-specific
`build_worship_rotation_proposal`, `confirm_worship_rotation_proposal`,
`extract_expected_scheduling_revisions`, tail/shift validation, future-only
published weekly-chain rules, per-event `can_change_worship_team` authority, or
planner notification emission. Its signing decoder needs its own strict shape
validator. Small positive/optional-ID, datetime, UUID, and exact-key validation
patterns may be mirrored or narrowly extracted only if that reduces duplication
without coupling the two product contracts. Canonical current-truth helpers
`service_event_audience_readiness` and
`inspect_worship_ownership_consistency` are reused directly.

#### Atomic confirmation order

The future write service follows this exact order:

1. Before a transaction, authenticate, require active staff/superuser, decode
   and fully shape-check the distinct signed proposal, enforce expiry/user
   binding, validate the UUID and exact canonical 52-row cross-field shape, and
   perform no scheduling mutation. Reject a payload that was not confirmable or
   has no proposed change.
2. Enter one `transaction.atomic()` block.
3. Reload the actor and require current active staff/superuser authority.
4. As the first scheduling/governance mutation, call
   `claim_scheduling_revisions` for all 52 unique exact event IDs and their
   signed expected revisions. Claims occur in ascending event-ID order. Every
   selected row, including a signed no-op row, participates.
5. On stale, missing, or busy claim, abort. Earlier claims roll back; no anchor
   or audit row is written.
6. Reload all exact ServiceEvents after the successful claim. Require the exact
   52 IDs once with no missing/extra/duplicate target.
7. For every row, recompute all confirmation facts from current database truth
   as specified below. Any failure aborts all 52 rows.
8. For rows whose current anchor differs from the proposed team, save only
   `rotation_anchor_team` and `updated_at` with the established skip-second-
   revision primitive. A row whose signed expected-before equals proposed is a
   no-op: it keeps the successful claim revision but receives no anchor save.
9. Create all changed-event `LogEntry` rows in the same transaction. Any audit
   exception aborts the batch.
10. Commit once and return the request-scoped result. There is no partial
   success and no notification registration.

#### Current-truth recomputation matrix

| Fact | Confirmation-time rule | Revision coverage and independent check |
| --- | --- | --- |
| Exact target identity | Event ID from the reviewed row; persisted profile exactly `bethany_0930_cm`; signed local date; configured-local exact 09:30; `sunday_service` | Normal ServiceEvent profile/time/type saves advance revision; confirmation independently reloads and recomputes every field |
| Lifecycle | Status is exactly published or completed; draft/cancelled/unknown blocks | Normal ServiceEvent lifecycle saves advance revision; status is independently recomputed |
| Audience | `service_event_audience_readiness(event)["ready"]` remains true, including nonzero rows, active units, and no ancestor/descendant overlap | Supported audience replacement advances revision; audience rows and Church Structure activity/ancestry are independently recomputed |
| Proposed mapping | Every signed mapping/row relation is exact; proposed MinistryTeam exists, active, and assignable | MinistryTeam configuration changes do not need new event revision coupling because existence/flags are independently recomputed after the CAS |
| Governance/applicability | Proposed team remains in the exact event's current eligible candidate union; all pool, anchor, active-primary-path, hierarchy, and applicability rules pass | Pool/team/path/Church Structure changes are independently recomputed after the CAS; no new revision coupling is required |
| Expected-before anchor | Current `rotation_anchor_team_id` equals the signed expected-before ID, including null | Supported anchor changes advance revision; exact equality is independently required. Equality with the proposed team alone never proves replay |
| Worship ownership | No invalid/off-team/out-of-scope/multiple/duplicate state; a changed row has no current Worship assignment; a true no-op may retain one exact consistent current assignment | Supported current assignment writes advance revision; assignment rows/status and canonical ownership are independently recomputed to catch unsupported/bulk drift |
| Bulk authority | Reloaded actor remains active staff or superuser | User/role state is independent of event revision and is rechecked inside the transaction before CAS |
| Claim state | Current post-claim revision is the signed expected revision plus one for every target | Enforced by the conditional claim and verified from reloaded rows |

This satisfies the SQLite stale-safety boundary without adding revision coupling
for pool configuration, team flags, Ministry hierarchy, Church Structure, or
authority facts that are safely recomputed after the first writer claim. Raw
SQL and arbitrary future bulk ORM mutation remain outside the supported-write
inventory, but relevant persisted truth is still fail-closed when the importer
recomputes it.

#### Audit, replay, and no-ImportRun decisions

V1 uses the existing Django `LogEntry` model. Each actually changed event gets
one row whose actor is `LogEntry.user`; all rows share the proposal operation
UUID. The planner's `LogEntry.objects.log_action(...)` and semicolon-delimited
key/value convention are reusable, but its exact message is not: the annual
import needs a distinct source and provenance contract and must not emit team
display names or workbook annotations.

Each annual-import audit message records only:

```text
source=annual_worship_workbook_import;
operation_id=<uuid>;
workbook_sha256=<sha256>;
parser_contract_revision=<revision>;
confirmation_contract_revision=<revision>;
event_id=<id>;
local_date=<YYYY-MM-DD>;
old_team_id=<id or None>;
new_team_id=<id>.
```

No ignored leader name, arbitrary workbook cell, roster/member data, note,
contact, or private source text is logged. No-op rows receive no audit. Audit
failure rolls back anchors, revisions, and all earlier audit rows.

The operation UUID embedded in free-form `LogEntry.change_message` has no
database uniqueness constraint and no existing trustworthy exact-replay lookup
contract. Slice 9 therefore does not pretend that a matching current team or
text search proves an earlier successful import. The reliable V1 replay rule is
the revision CAS: after one successful POST, all 52 signed expected revisions
are stale, so a double POST/replay performs no duplicate anchor save, revision
advance, or audit. A concurrent second POST waits/fails busy or later fails CAS.
The response is `stale / already changed — rebuild preview`. A rebuilt preview
after successful application produces 52 no-op rows and no confirm action.

No durable `ImportRun` is required because V1 needs no retained preview,
multi-user handoff, workflow recovery, unique query-optimized batch history,
one-click rollback, or import-history UI. The signed reviewed proposal supplies
the request contract; per-changed-event `LogEntry` plus shared operation UUID
supplies durable actor/correlation audit. If any deferred durable workflow need
becomes mandatory, reevaluate schema rather than overstating this design.

#### Notifications and request-scoped result UX

The annual importer deliberately does not call the implemented `NOTIFY.1G`
producer. A first production import may change all 52 anchors from null and the
ordinary direct-change fanout could create an unreviewed notification burst.
The exact selector and Rotation Planner notifications remain unchanged. After
trial evidence, a separately approved producer may consider one bounded,
recipient-specific annual-import summary.

On success, the POST response may show only the sanitized workbook filename and
hash, operation ID, selected/changed/no-op/audit counts, and changed Sunday/date
rows with old team to new team. It states explicitly that no roster, assignment,
audience, RequiredTeam, planner, event, membership, or serving data changed.
The result is request-scoped; `LogEntry` is the durable audit and no import-
history UI is added.

On stale, conflict, busy, validation, save, or audit failure, show one all-or-
nothing failure result: nothing changed; rebuild and review a new preview. Do
not show partial-success counts or expose private/governance internals.

#### Zero-write/all-or-nothing failure matrix

Every listed failure yields zero committed anchor changes, zero partial
revision claims, zero committed `LogEntry` rows, and zero notifications:

| Failure | Required behavior |
| --- | --- |
| Expired, tampered, malformed, wrong-contract token; user mismatch | Reject before transaction mutation and require a new preview |
| Ordinary/non-staff user or authority lost after preview | Reject before transaction or on the in-transaction pre-CAS actor reload; no claim commits |
| One event deleted | Missing CAS target aborts and rolls back earlier claims |
| One event revision changed | Stale CAS aborts and rolls back earlier claims |
| Profile, local date/time, type, or expected-before anchor changed | Current-truth mismatch aborts all rows |
| Event becomes draft/cancelled or unsupported lifecycle | Current lifecycle check aborts all rows |
| Audience becomes zero/inactive/overlapping/otherwise invalid | Current readiness check aborts all rows |
| Mapped/proposed team is missing, inactive, or nonassignable | Current mapping check aborts all rows |
| Pool, Ministry hierarchy, primary path, Church anchor, or applicability changes | Recomputed governance mismatch/ineligibility aborts all rows |
| Mapped team is no longer an eligible destination candidate | Current eligible-union check aborts all rows |
| Current Worship assignment appears after preview | A changed-row assignment or any invalid ownership state aborts all rows |
| Off-team, out-of-scope, multiple, or duplicate ownership appears | Canonical ownership check aborts all rows |
| `LogEntry` creation fails after one or more saves | Transaction rolls back every save, claim, and earlier audit |
| SQLite is busy/locked or a competing writer wins first | Return retry/new-preview failure; no partial commit |
| Replay/double POST | Old expected revisions fail; no duplicate write/audit and no claim of proven prior application |

#### Required implementation test architecture

Before runtime is approved, focused tests must cover:

- staff and superuser success; ordinary user, pool Lead, event planner,
  exact-team Lead, and global assignment manager denial;
- a production-shaped exact 52-row batch containing completed and published
  targets, plus mixed changed/no-op behavior;
- all-selected stale protection and one later stale/missing row rolling back
  earlier claims;
- every identity, lifecycle, audience, team activity/assignability, pool,
  hierarchy, Church anchor/applicability, destination eligibility, expected-old
  anchor, assignment, and ownership failure above;
- changed-only per-event `LogEntry`, one shared operation UUID, privacy-bounded
  audit fields, and audit-failure rollback;
- zero creation/change of ServiceEvent rows beyond anchor/revision, audience,
  RequiredTeam, planner, assignment/member, MinistryTeam, Church Structure,
  membership, serving, or user data;
- no notification payload, Core on-commit producer registration, or Notification
  row from the annual importer;
- token contract/tamper/user/expiry/shape validation and confirmability gates;
- double POST/replay and concurrent POST behavior with zero duplicate write;
- a real two-connection, file-backed SQLite confirmation service test modeled
  on A1/1B-B, proving the first CAS excludes a competing writer through commit,
  later failure restores all claims, and no partial 52-row commit occurs; and
- rendered bilingual English/Chinese desktop/mobile confirmable, blocked,
  already-matches, stale, failure, and success UI QA. Automated tests use only
  isolated test databases and never mutate production.

The implementation slice must retain POST-only/CSRF behavior, exact 52-row
shape, and the repository's no-row-lock wording. Any need for event creation,
RequiredTeam/assignment/member mutation, notification fanout, durable run state,
or a second concurrency protocol is a stop condition requiring a new decision.

### MO-S.6D-SLICE9.1A — Atomic Annual Workbook Confirmation — PRODUCTION APPLY COMPLETE / VERIFIED

`MO-S.6D-SLICE9.1A` implements the complete V1 confirmation runtime authorized
by `SLICE9.0A`:

- a fully accepted Slice 8 preview mints a distinct 30-minute, user-bound
  `SVCA_BETHANY_0930_2026_CONFIRM_V1` proposal with one operation UUID; the
  workbook is not re-uploaded and the measured 52-row signed token is 1,351
  UTF-8 bytes in the focused fixture;
- only active staff/superusers can preview or POST confirmation; exact-team or
  pool leadership, event planning, assignment management, service-event
  capability, audience, belonging, and serving grant no annual-import authority;
- one transaction reloads/rechecks the actor, claims all 52 signed
  `scheduling_revision` values through the existing ascending-ID CAS helper,
  reloads the exact events, and recomputes profile/date/time/type/lifecycle,
  canonical audience readiness, mapped-team activity/assignability,
  per-destination eligibility, expected-before anchor, and current ownership;
- every selected event advances revision exactly once; changed rows save only
  `rotation_anchor_team` with `_skip_scheduling_revision=True`, while true
  no-op rows receive no anchor save;
- each changed event receives one same-transaction deterministic `LogEntry`;
  changed rows share the proposal operation UUID and no-op rows receive none;
- replay/double-submit is stale-safe through the 52 expected revisions; no
  `ImportRun`, consumed-token table, notification producer/callback, assignment,
  member, audience, RequiredTeam, planner, event-identity, team, or structure
  write was added; and
- request-scoped bilingual confirmable/already-matches/success/stale result UX,
  strict token/current-truth failures, and two-scenario target-like file-backed
  SQLite concurrency are locally verified. English desktop and Chinese mobile
  rendered QA also verified blocked/no-op action gates and no global horizontal
  layout break.

Production confirmation is complete and product-owner verified. A fresh
re-upload of the same workbook produced 52 no-op rows, 0 proposed changes,
0 blocked rows, and no confirmation action. This closes the annual Worship Team
workbook confirmation path for the current V1 scope. Assignment/member import
remains separately deferred.

### MO-S.6D — Excel Event + Worship Team Import

- Status: **PREVIEW IMPLEMENTED / PRODUCTION READ-ONLY SMOKE PASSED
  (`MO-S.6D-SLICE8.1A/FU1/UX1`); CONFIRMATION PRODUCTION APPLY COMPLETE / VERIFIED
  (`MO-S.6D-SLICE9.1A`)**. The declared dependency, strict parser, derived
  present-token counts, bounded OOXML ZIP preflight, partial eligible-token
  mapping, exact existing-target classification, blocked-row business evidence,
  bounded downstream-impact display, and staff/superuser-only upload/preview
  are in place. The preview remains zero-write. The separate explicit Slice 9
  POST applies only the reviewed 52-target anchor/revision/audit contract and
 has been product-owner confirmed on production.
- Goal: controlled annual Bethany 9:30 workbook input under the approved
  contract and lifecycle, not date-and-anchor import in isolation.
- Implemented Slice 8 scope: code-versioned template contract,
  parse/validate/preview, exact existing-event matching, explicit
  eligible mapping for present tokens, incomplete-mapping and per-destination
  eligibility blockers, before/after Worship Team proposals, current Worship
  roster conflict detection, downstream-assignment impact display, and no-op/
  change/blocked classification. Docs/read-only `MO-S.6D-SLICE9.0A` froze the
  confirmation, reauthorization, audit/result, replay, and atomic selected-team-
  only write contract; `MO-S.6D-SLICE9.1A` is production-applied and product-owner verified.
  New-event
  creation remains excluded unless product separately approves the
  audience/profile flow.
- Out of scope: assignment/member import, arbitrary workbooks, formulas as
  rules, bidirectional sync, automatic user/team creation.
- Components: strict importer-preview service, upload/preview and dedicated
  POST-only confirmation views/templates, strict confirmation service, event/
  team lookup helpers, existing scheduling CAS, and reused generic models.
- Schema impact: none in Slice 8 or the approved Slice 9 V1 contract; a durable
  ImportRun remains deferred unless a later explicit workflow requirement
  proves it necessary.
- Security: staff/superuser only for upload/preview and confirmation; no
  mutation on upload or preview; both signed states are normalized, expiring,
  and user-bound; confirmation rechecks current authority inside its transaction.
- Tests: malformed/versioned workbook, ZIP member/count/resource/encryption
  boundaries, derived and absent-token distributions, signed semantic tamper,
  date/event conflict, no-op, selected-team change, incomplete/no-candidate/
  per-destination mapping blockers, target-blocker precedence, roster conflict,
  downstream impact, lifecycle/audience blockers, permission denial, formula/
  cache boundary, real-workbook acceptance, and zero-write proof.
- Acceptance: every accepted upload produces read-only evidence; incomplete
  mappings and business blockers remain visible; identical current selection is
  a no-op; no event/team/assignment/audience/audit/notification data is written,
  no assignment is created, and no published zero-audience event is produced.
Slice 9 confirmation is production-applied and product-owner verified. A fresh
re-upload of the same workbook produced 52 no-op rows, 0 proposed changes,
0 blocked rows, and no confirmation action.
- Dependency: MO-S.6B event/team context, the MO-S.6D-0A/FU1 governance
  prerequisites, stable service-profile mapping, and a separately reviewed
  `.xlsx` dependency.

### MO-S.6E — Worship Change / Downstream Review Warning

- Goal: make possible downstream staleness visible without automation.
- Scope: conservative derived warning first; later version field only if needed.
- Out of scope: downstream rewrite, automatic rescheduling, and notification
  fanout. A known committed before/after Worship Team selection may receive a
  separately implemented `NOTIFY.1G` producer under the docs-complete
  `NOTIFY.1G-0A` contract; it does not solve this harder
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

The direct Worship Team change notification is not an open architecture item:
`NOTIFY.1G-0A` closed its contract and `NOTIFY.1G` implements that bounded
runtime. MO-S.6E roster-change staleness remains a separate future problem.

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
- `docs/WORSHIP_ROTATION_PLANNER_PLAN.md`;
- `docs/MODULE_BOUNDARIES.md` and `docs/CHURCH_STRUCTURE_FOUNDATION_PLAN.md`;
- `events/models.py`, `ministry/models.py`, `ministry/permissions.py`,
  `ministry/services/assignment_coverage.py`,
  `ministry/services/worship_context.py`,
  `ministry/services/copy_forward_suggestions.py`, and
  `ministry/services/assignment_notifications.py`.
