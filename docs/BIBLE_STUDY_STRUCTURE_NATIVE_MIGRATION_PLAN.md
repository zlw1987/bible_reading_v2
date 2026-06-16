# Bible Study Structure-Native Migration Plan (BS-STRUCT.1A)

## 0. Purpose and Status

This is the BS-STRUCT.1A design/audit document. It defines how the Bible Study
module should migrate to the new Church Structure core (`ChurchStructureUnit` +
`ChurchStructureMembership`) while preserving the current module's useful
behavior and supporting the real church Bible Study workflow.

Status: **docs-only design/audit**. This slice changes no models, migrations,
forms, views, templates, tests, or runtime behavior. It does not create schema
migrations and does not stage/commit/push anything.

It deliberately follows the proven ServiceEvent runtime-migration pattern
(`docs/SERVICE_EVENT_AUDIENCE_RUNTIME_MIGRATION_PLAN.md`) as a *pattern* only.
Bible Study has its own domain model and must not be blindly copied — in
particular, ServiceEvent has a single optional `ServiceEventAudienceScope` set
per event, whereas a Bible Study **meeting** is currently hard-bound to exactly
one legacy `SmallGroup`, which is the central thing this migration must change.

Related docs:

- `docs/BIBLE_STUDY_V2_GROUP_MEETING_MODEL_PLAN.md` — V2 two-layer model rationale.
- `docs/BIBLE_STUDY_V2_SCHEDULE_SCOPE_REPLAN.md` — schedule/guide/meeting hierarchy, BS-AS.1/2 audience scope at the **series** level.
- `docs/LEGACY_BIBLE_STUDY_SESSION_RETIREMENT_DECISION.md` — V1 `BibleStudySession` retirement boundary (CS-CORE.3C–3F).
- `docs/CHURCH_STRUCTURE_CORE_MIGRATION_PLAN.md` — CS-CORE plan; Section 12 legacy retirement preconditions; CS-CORE.2C-B (BS meeting visibility → membership-core), CS-CORE.3B (BS pickers → membership-core), CS-CORE.1C (resolver re-home).
- `docs/SERVICE_EVENT_AUDIENCE_RUNTIME_MIGRATION_PLAN.md` — pattern reference only.
- `docs/FLEXIBLE_CHURCH_STRUCTURE_AND_AUDIENCE_SCOPE_DESIGN.md` — shared `ChurchStructureUnit` audience-scope direction.

---

## 1. Current State Audit

Verified against the worktree (`studies/` + `accounts/structure_selectors.py` +
`studies/visibility.py`) on 2026-06-15.

### 1.1 Series / Plan / Lesson / Meeting concepts present today

The active V2 stack (`studies/models.py`):

- **`BibleStudySeries`** — internal model used user-facing as *Bible Study
  Schedule / 查经安排*. Period-level container with `start_date` / `end_date` /
  `status` / `published_at`. Carries **two** scope mechanisms:
  - legacy scope fields: `scope_type` (`global` / `ministry_context` /
    `district` / `small_group`), `ministry_context`, `district`, `small_group`;
  - structure audience rows via **`BibleStudySeriesAudienceScope(series, unit)`**
    (BS-AS.1), a many-to-`ChurchStructureUnit` join.
- **`BibleStudySeriesAudienceScope`** — series-level audience join to
  `ChurchStructureUnit`. Validates: active unit, no whole-church-root combined
  with other units, no ancestor+descendant for the same series. This is the
  current `ChurchStructureUnit` audience-scope foundation for Bible Study, but
  it lives at the **series** level only.
- **`BibleStudyLesson`** — the weekly church-wide guide. Fields:
  `scripture_reference`, `lesson_date`, `prestudy_datetime`,
  `pastor_guide_body[_en]`, `global_discussion_questions[_en]`,
  `prestudy_notes[_en]`, `status`, `published_at`. Belongs to a series; it has
  **no independent audience/scope** — it inherits the series scope.
- **`BibleStudyMeeting`** — the concrete small-group meeting for one lesson.
  **Hard-bound to exactly one legacy `SmallGroup`** via a non-null
  `small_group = FK(SmallGroup, on_delete=CASCADE)`. Carries
  `meeting_datetime`, `location[_en]`, `meeting_link`, group-local
  `group_direction[_en]` / `group_questions[_en]`, `status`, optional
  `service_event` FK, and de-emphasized `discussion_leader_user` /
  `discussion_leader_name` compatibility fields.
  **Unique constraint: `(lesson, small_group)`.** There is **no meeting-level
  audience model and no `anchor_unit`.**
- **`BibleStudyMeetingRole`** — per-meeting responsibilities (discussion leader,
  worship lead, pianist, support, host); user FK (nullable) + display-name
  fallback.
- **`BibleStudyMeetingWorshipSong`** — per-meeting worship set (order, title,
  key, links, arrangement/support notes, worship-lead user/name fallback).

Legacy V1 stack, frozen as archive (`docs/LEGACY_BIBLE_STUDY_SESSION_RETIREMENT_DECISION.md`):

- **`BibleStudySession`** (+ `BibleStudyGuide` one-to-one, +
  `BibleStudyWorshipSong`). Visibility still legacy-driven through
  `Profile.small_group` / `scope_type` / `district` / `small_group`. App-level
  create/edit/delete/worship routes are frozen and redirect with archive
  messaging (CS-CORE.3D/3F). **Decision: do not migrate V1 to membership-core or
  to structure audience; it is a retirement target, not part of this migration.**

### 1.2 How weekly guides / questions are represented

- Church-wide weekly content lives on `BibleStudyLesson`
  (`pastor_guide_body`, `global_discussion_questions`, `prestudy_notes`,
  `scripture_reference`).
- Group-local overrides live on `BibleStudyMeeting`
  (`group_direction`, `group_questions`) and are editable via
  `BibleStudyMeetingPreparationForm` (`edit_bible_study_meeting_preparation`).
  The meeting **references** the lesson and displays parent content
  dynamically; guide content is not copied into the meeting. This already
  matches workflow steps 2–3 (pastoral guide as default, group-local
  customization).

### 1.3 How meetings are generated

`get_bible_study_meeting_generation_preview()` + `generate_bible_study_meetings()`
(`studies/views.py`):

1. `lesson.series.get_eligible_small_groups()` resolves the eligible legacy
   `SmallGroup` set. If the series has audience rows, this is
   `resolve_units_to_small_groups(units)` (selector layer, CS-CORE.1C); else it
   falls back to legacy `scope_type` semantics.
2. The preview diffs eligible groups against already-existing meetings for the
   lesson and lists `missing_groups`.
3. On POST, one `BibleStudyMeeting` is `get_or_create`d **per missing small
   group**, with a default Friday 19:30 datetime and `status=draft`.

Generation is idempotent (skips existing, including cancelled), one meeting per
`(lesson, small_group)`. **It always produces one meeting per leaf small group;
there is no concept of a single higher-level or multi-unit joint meeting.**

### 1.4 Where each structure concept is used

| Concept | Where used in `studies/` |
| --- | --- |
| `SmallGroup` | `BibleStudyMeeting.small_group` (non-null, CASCADE), `BibleStudySeries.small_group` (legacy scope), `BibleStudySession.small_group` (V1), generation target, manage-list filters, V2 landing. **The hard runtime dependency.** |
| `District` | `BibleStudySeries.district` / `BibleStudySession.district` legacy scope fields only. |
| `Profile.small_group` | **No longer read by V2 meeting visibility or pickers.** Still read by V1 `BibleStudySession.can_be_seen_by()` and by the read-only audit comparator in `structure_readiness.py` (`get_user_legacy_small_group`). |
| `ChurchStructureUnit` | `BibleStudySeriesAudienceScope.unit` (series audience); the mapping target for `SmallGroup.church_structure_unit` used in resolution and visibility. |
| `ChurchStructureMembership` | **Already the V2 runtime belonging source** for meeting visibility (`studies/visibility.py`, CS-CORE.2C-B) and for role/worship user pickers (CS-CORE.3B). Single active primary membership only; multiple/none fails closed. |

### 1.5 Current visibility behavior

`BibleStudyMeeting.can_be_seen_by()` → `studies/visibility.py`:

1. Manager override (staff / superuser / `CAP_MANAGE_BIBLE_STUDIES` /
   `CAP_PUBLISH_BIBLE_STUDY_GUIDES`) → always visible.
2. `meeting_is_member_visible()` — meeting published + lesson published + series
   active & published.
3. Row-first audience match (BS-STRUCT.1E): when the meeting has one or more
   `BibleStudyMeetingAudienceScope` rows,
   `user_matches_meeting_audience_scopes(user, meeting)` is the source of truth —
   the user's single active primary membership unit must be one of the audience
   units **or a descendant** (any unit level; no `UNIT_SMALL_GROUP` gate). When
   the meeting has **zero** audience rows it falls back to
   `user_matches_meeting_small_group_membership(user, meeting.small_group)` — the
   single `small_group` mapped to a **small-group-type** `ChurchStructureUnit`,
   matched by the user's single active primary membership unit or a descendant.
   `Profile.small_group` grants nothing on either path.

**Current state:** visibility is membership-core and **row-first**. A meeting
with audience rows can express any audience level (single group, district,
CM/EM, custom, or multi-unit joint), and the legacy single-`small_group` path
survives only as the zero-row fallback for meetings that have no audience rows.

### 1.6 Current Today / landing behavior

`get_v2_landing_context()` (`studies/views.py`, reused by `reading/views.py` for
Today, per CS-CORE.3C audit) is **row-first** (BS-STRUCT.1E):

- It resolves the user's active primary membership ancestor-or-self unit ids
  (`get_membership_audience_candidate_unit_ids`) and selects upcoming published
  meetings matching **either** an audience row on one of those units **or** the
  legacy `small_group` zero-row fallback, confirming each through
  `can_be_seen_by` (so audience-row precedence still applies).
- The empty/no-group state is only shown when the user has **neither** a
  resolvable legacy group **nor** any active primary membership (e.g. a
  profile-only user), so a membership user with a null `small_group` still sees
  their audience-row meeting and a descendant-unit member sees a higher-level /
  district audience-row meeting.
- Today additionally surfaces the user's linked `BibleStudyMeetingRole` chips.

So joint / higher-level audience-row meetings now appear here; only the zero-row
fallback remains single-group-centric. `Profile.small_group` is not consulted.

### 1.7 Current worship / song / leader / role picker behavior

- `BibleStudyMeetingRoleForm` and `BibleStudyMeetingWorshipSongForm` filter the
  user dropdown through `filter_users_for_meeting_audience(users, meeting)`
  (BS-STRUCT.1F): when the meeting has audience rows the candidates are
  active-primary members of any audience unit (or descendants); a zero-row
  meeting falls back to `filter_users_for_meeting_small_group_membership(users,
  meeting.small_group)` — active primary members of the meeting's single
  small-group unit (or descendants). Both paths are single-active-primary only
  (CS-CORE.3B) and never consult `Profile.small_group`.
- Worship set / roles are per-meeting; manager-controlled. No role-aware editing
  permissions yet (BS-V2.7 deferred). No automatic assignment, rotation,
  availability, swap, or reminders.

### 1.8 Current V1 archived / frozen paths

V1 `BibleStudySession` create/edit/delete/worship app routes redirect with
archive messaging (CS-CORE.3D/3F); direct detail stays readable when legacy
visibility allows; Django Admin is the emergency archival path. **Out of scope
for this migration** — see Section 7 open question on V1 handling.

### 1.9 Remaining legacy consumers (the migration surface)

Runtime **reads** for meeting visibility, V2 landing / Today, and role/worship
pickers are now **row-first** with a zero-row `small_group` fallback
(BS-STRUCT.1E/1F), so the remaining legacy surface is concentrated in the
**write** and **resolution** paths plus the fallback itself:

1. **Generation** writes meetings keyed on legacy `SmallGroup` and the
   conditional `(lesson, small_group)` unique constraint, resolving eligible
   targets through `get_eligible_small_groups()` /
   `resolve_units_to_small_groups()` (series audience → legacy `SmallGroup`).
2. **Manual create/edit meeting form** still writes `small_group` and does
   **not** write `BibleStudyMeetingAudienceScope` rows, so manually created
   meetings rely on the zero-row fallback.
3. **Zero-row `small_group` fallback** — visibility, landing/Today, and pickers
   all retain the legacy single-`small_group` path for meetings with no audience
   rows.
4. **Manage-list filters** still expose / filter by legacy `small_group`.
5. **Series legacy scope fields** (`scope_type` / `ministry_context` /
   `district` / `small_group`) + `apply_audience_legacy_fallback()` — still a
   coexistence fallback.
6. **V1 `BibleStudySession`** — legacy-only, retirement target (excluded).

Note: the runtime reads are **already** membership-core in their *user*
resolution and now structure-native in *how the meeting's audience is read*
(audience rows when present); `Profile.small_group` is not used by V2 visibility,
landing/Today, or pickers. The remaining blocker is the audience **write** path
(generation + manual form) and retiring the zero-row fallback once every meeting
carries rows.

---

## 2. Target Concept Model

Preserve the existing two-layer content model; add a structure-native meeting
audience layer. Do **not** collapse `SmallGroup` into a single `structure_unit`
FK — that cannot express multi-unit joint meetings.

### 2.1 Bible Study Series / Plan (`BibleStudySeries`)

- Period-level arrangement (quarter / month / multi-month range): "the church /
  CM / EM will study this book or section during this period."
- Scope may be church / CM / EM / department / fellowship level, expressed by the
  existing `BibleStudySeriesAudienceScope` units (already structure-native).
- Defines book/section/theme baseline (title, description, date range).
- **No new model needed.** Keep series-level audience rows as the default
  generation scope.

### 2.2 Weekly Guide / Lesson (`BibleStudyLesson`)

- Pastoral weekly source of truth: focus / theme / direction / discussion
  questions, scripture, pre-study datetime.
- Default inherited by group meetings (already implemented — meetings reference
  the lesson and display its content dynamically; no copy).
- **No independent lesson-level audience now.** A future lesson-level scope
  override is deferred (Section 3, post-migration), consistent with BS-AS.1.

### 2.3 BibleStudyMeeting

- Concrete Friday meeting instance referencing a weekly guide/lesson.
- date / time / location / status (unchanged).
- Must support **group-level, district-level, CM/EM-level, and multi-unit joint
  meetings** — i.e. the meeting's audience is no longer "exactly one
  `SmallGroup`."
- **`small_group` becomes a temporary compatibility mirror** (nullable), not the
  source of truth (Section 4). Keep it filled only when a meeting maps
  one-to-one to a legacy group, for legacy reads during the transition.

### 2.4 BibleStudyMeetingAudienceScope (new)

- Many rows from meeting to `ChurchStructureUnit`:
  `BibleStudyMeetingAudienceScope(meeting, unit)`.
- Controls who can see / participate in the meeting.
- Supports single group, district, CM/EM, and multi-unit joint meetings (e.g.
  Singles + Campus) via multiple rows.
- Validation mirrors `BibleStudySeriesAudienceScope`: active unit; no
  whole-church-root combined with other units; no ancestor+descendant for the
  same meeting; siblings / cross-branch allowed.

### 2.5 anchor_unit (new, optional)

- `BibleStudyMeeting.anchor_unit = FK(ChurchStructureUnit, null=True)`.
- Optional **primary organizational unit** for display / grouping / ownership.
- **Not the same as visibility** and does **not** replace audience rows. A
  district joint meeting may anchor to the district unit; a Singles+Campus joint
  meeting may anchor to either a chosen primary unit or be null.

### 2.6 Meeting-local prep / override

- Group leader / local team may use the pastoral guide as default but optionally
  customize focus / theme / questions / notes.
- **Already exists** as `group_direction` / `group_questions` +
  `BibleStudyMeetingPreparationForm`. No model change required for migration.
- Broader leader-editing permissions (role-aware editing, BS-V2.7) remain a
  **future feature**.

### 2.7 Worship plan

- Meeting-local worship draft → confirm → finalize workflow (workflow step 4:
  worship leaders draft ~Wednesday, finalize after Thursday pre-study).
- **Partially exists** as `BibleStudyMeetingWorshipSong` (per-meeting set,
  manager-controlled). A draft/confirm/finalize **status workflow** and
  role-aware worship editing are **future features**, not migration blockers.

### 2.8 Serving rotation

- Rotation slots should **not be hard-bound only to dates**: a joint / cancelled
  replacement week should usually **not consume** a group's rotation slot
  (workflow step 7 — the schedule shifts forward one week).
- The full rotation editor / UI / auto-shift is a **future feature**.
- **Migration requirement (data-model-must-not-prevent):** the meeting/audience
  model must let us tell, for a given unit and week, whether a *normal* group
  meeting occurred or was *replaced/suppressed* by a joint/higher-level/cancelled
  meeting — so a later rotation engine can decide whether to consume a slot. A
  "this week was a replacement/suppressed week for these units" signal must be
  representable (e.g. a meeting `kind` / replacement flag, or derivable from
  audience rows + a suppression marker). The migration must not bake in
  "one meeting per group per week ⇒ always consume a slot."

---

## 3. Migration Blockers vs Post-Migration Product Features

### 3.1 Migration blockers (required to retire the legacy Bible Study `SmallGroup` dependency)

1. **Meeting audience can no longer be representable only by legacy
   `SmallGroup`.** Add `BibleStudyMeetingAudienceScope(meeting, unit)`.
2. **Meeting generation must write structure audience rows** (not only a
   `small_group` FK), and must support the higher-level / joint cases.
3. **Visibility must read meeting audience rows + active primary
   `ChurchStructureMembership`.** Today visibility is already membership-core but
   keyed off the single `small_group` unit; it must switch to "user's active
   primary membership unit is in (a descendant of) any meeting audience unit,"
   with the single-`small_group` path kept only as zero-row fallback.
4. **Role / worship candidate filtering must not depend on a single
   `small_group` unit.** It is already membership-core (not `Profile.small_group`),
   but it must read the meeting's audience rows (union of units) instead of the
   one `small_group`.
5. **Existing meetings must be backfilled or safely bridged** — every existing
   meeting needs an audience row equivalent to its current `small_group` unit
   (audit + parity, ServiceEvent SE-AS.6 pattern).
6. **Normal write paths must stop creating legacy-only meeting audience** — once
   backfilled, generation/create/edit must not produce a meeting whose audience
   exists only as a `small_group` FK with zero audience rows (SE-AS.7A pattern).
7. **Audit must prove no normal runtime / write path still depends on legacy
   `SmallGroup`** for Bible Study meeting audience/visibility/pickers (landing &
   Today included).

### 3.2 Post-migration product features (explicitly NOT blockers)

- Full worship workflow UI (draft / confirm / finalize, role-aware worship
  editing).
- Full Thursday pre-study collaboration UI.
- Full serving-rotation editor.
- Automatic schedule-shift UI for replacement/joint/cancelled weeks.
- Notifications / reminders.
- Advanced reports.
- Lesson-level audience override (beyond series scope).
- V1 `BibleStudySession` data migration/retirement (separate retirement policy).

---

## 4. Recommended Data Model Direction

Proposed (not implemented; safest direction):

1. **Add `BibleStudyMeetingAudienceScope(meeting, unit)`** — many-to-`ChurchStructureUnit`
   join, CASCADE on meeting delete, PROTECT on unit delete, unique `(meeting,
   unit)`, validation mirroring `BibleStudySeriesAudienceScope`.
2. **Add optional `BibleStudyMeeting.anchor_unit = FK(ChurchStructureUnit,
   null=True, blank=True, on_delete=SET_NULL)`** — display/grouping/ownership
   only; never visibility.
3. **Keep `BibleStudyMeeting.small_group` temporarily as a compatibility
   mirror.** Make it **nullable** so higher-level/joint meetings (which map to no
   single leaf group) are representable. Fill it only when a meeting maps
   one-to-one to a legacy small group.
4. **Do NOT replace `small_group` with a single `structure_unit` FK only** — that
   fails multi-unit joint meetings (Singles + Campus). The audience must be a
   set of units.
5. **Revisit the `(lesson, small_group)` unique constraint.** With nullable
   `small_group` and joint meetings, this constraint cannot be the identity key.
   A later slice must define meeting identity (e.g. `(lesson, anchor_unit)` plus
   an audience-set signature, or a generation key) so generation stays
   idempotent without blocking multiple/joint meetings per lesson.
   **Resolved in BS-STRUCT.1B (see Section 6).** The existing
   `unique_bible_study_meeting_lesson_group` constraint was made **conditional
   on a non-null `small_group`**, so normal group-level duplicates are still
   rejected while multiple null-`small_group` (higher-level/joint) meetings per
   lesson are allowed. A nullable `generation_key` CharField was added with a
   **conditional** `unique_bible_study_meeting_lesson_generation_key` constraint
   on `(lesson, generation_key)` enforced only when `generation_key` is set;
   multiple null keys per lesson are allowed. No runtime depends on
   `generation_key` yet. **BS-STRUCT.1B-FU1:** `BibleStudyMeeting.clean()`
   normalizes a blank/whitespace-only `generation_key` to `None` (and strips
   non-empty keys) before constraint validation in `full_clean()`, so an empty
   string never collides as a set value under the conditional constraint.
   Model/test-only — no schema change, no new migration.
6. **Future models (not immediate blockers):**
   `BibleStudyMeetingPrep` (if group-local prep outgrows the inline fields),
   `BibleStudyWorshipPlan` (draft/confirm/finalize status), and rotation-slot
   models. Only build when current code requires them — today the inline prep
   fields and `BibleStudyMeetingWorshipSong` suffice.
7. **Rotation-readiness (data-model-must-not-prevent):** add a meeting `kind` /
   replacement marker (e.g. normal / higher-level / joint / cancelled-replacement)
   *or* ensure replacement/suppression is derivable, so a future rotation engine
   can decide slot consumption. Recommended to introduce the marker with the
   audience model so generation can set it, even if no rotation engine reads it
   yet.

This mirrors the ServiceEvent shape (`ServiceEventAudienceScope` + zero-row
legacy fallback) but adapts it: ServiceEvent kept one scalar `small_group`
fallback per event; Bible Study must make `small_group` **nullable** and add
`anchor_unit`, because a Bible Study meeting's audience is a *set* of units and
can be higher-level.

---

## 5. Generation Design (post-migration)

### 5.1 Default (normal group-level week)

- The series / weekly-guide scope generates meetings for the **active leaf Bible
  Study units** under that scope (see Section 7 open question on "leaf unit").
- Each generated meeting gets **one audience row = the leaf unit**.
- `anchor_unit` = the leaf unit.
- The legacy `small_group` mirror is filled **only** when the leaf unit maps
  one-to-one to an active legacy small group; otherwise it stays null and the
  audience row governs.

### 5.2 Higher-level meeting (district / CM / EM)

- Staff selects a district / CM / EM unit → generate **one** meeting.
- Audience rows = the selected higher-level unit.
- `anchor_unit` = the selected higher-level unit.
- Affected lower-level group meetings for that week are **skipped / suppressed**
  (marked as a replacement week for those units), not generated.

### 5.3 Multi-unit joint meeting (e.g. Singles + Campus)

- Staff selects multiple units → generate **one** meeting.
- Audience rows = **all** selected units.
- `anchor_unit` may be null or a chosen primary unit.
- **Do not create fake structure units** for one-off joint meetings.

### 5.4 Cancellation / skip week

- No normal group meetings generated for affected units.
- Rotation slots are **not consumed** by default (record the week as a
  replacement/cancelled week for those units so a later rotation engine shifts
  forward).

Generation stays idempotent, preview-before-create, and never auto-creates
roles, worship songs, `TeamAssignment`, or `ServiceEvent` (unchanged from
BS-V2.6.5 rules).

---

## 6. Proposed Slice Plan

Names/order are provisional and should be adjusted after BS-STRUCT.1B confirms
the meeting-identity decision (Section 4.5).

- **BS-STRUCT.1A** — docs-only design/audit (this document). ✅ complete.
- **BS-STRUCT.1B** — model foundation. ✅ **implemented** (inert foundation
  only; migration `studies/migrations/0009_biblestudymeetingaudiencescope_and_more.py`).
  Exactly what landed:
  - Added `BibleStudyMeetingAudienceScope(meeting, unit)` — CASCADE on meeting,
    PROTECT on unit, unique `(meeting, unit)`, indexes on `meeting` and `unit`,
    and `clean()` validation mirroring `BibleStudySeriesAudienceScope` (active
    unit; whole-church root not combinable; no ancestor+descendant for the same
    meeting; siblings/cross-branch allowed).
  - Added `BibleStudyMeeting.get_audience_scope_units()` convenience method.
  - Added `BibleStudyMeeting.anchor_unit` (FK `ChurchStructureUnit`,
    null/blank, `on_delete=SET_NULL`) — display/grouping/ownership only; no
    visibility read.
  - Converted `BibleStudyMeeting.small_group` to nullable/blank and changed
    `on_delete` from CASCADE to SET_NULL (compatibility mirror).
  - Added nullable `generation_key` CharField + meeting-identity constraints
    (Section 4.5).
  - Added `meeting_kind` CharField (`normal` default / `higher_level` / `joint`
    / `cancelled_replacement`) as an inert rotation/replacement readiness
    marker; no rotation logic reads it.
  - **No runtime read change**: audience rows, `anchor_unit`, `generation_key`,
    and `meeting_kind` are not read by visibility, generation, landing/Today, or
    role/worship pickers in this slice (like `ServiceEventAudienceScope` at
    SE-AS.2). No data backfill.
- **BS-STRUCT.1C** — backfill/audit command (dry-run first, SE-AS.6B pattern).
  ✅ **implemented.** Management command
  `backfill_bible_study_meeting_audience_scopes`
  (`studies/management/commands/backfill_bible_study_meeting_audience_scopes.py`).
  - **Dry-run by default**, `--apply` to write. A single shared classification
    pass (`_scan_meetings`) feeds both modes, so apply never creates a row the
    dry-run would not have reported as `would_create`.
  - For each meeting it proposes one audience row = the `small_group`'s mapped
    unit, valid only when that unit **exists, is active, and is
    `UNIT_SMALL_GROUP`**. Classification buckets: `skipped_existing_audience`,
    `would_create`, `missing_small_group` (null group), `unmapped_small_group`
    (no `church_structure_unit`), `inactive_structure_unit`, `wrong_unit_type`,
    `validation_error`.
  - **Additive only.** With `--apply` it creates the missing
    `BibleStudyMeetingAudienceScope` row and backfills `anchor_unit` **only when
    it is currently null** (never overwrites a set anchor). It **never mutates
    `small_group`** (reported `legacy_small_group_mutated = 0`) and **never
    changes runtime visibility / generation / Today-landing / role-worship
    picker behavior** (reported `runtime_switched = false`). Idempotent: a second
    run skips existing-audience meetings and creates `0` rows.
  - **Parity (conservative, structural).** Because the current runtime
    small-group path already keys off `small_group.church_structure_unit` gated
    on `UNIT_SMALL_GROUP` (`studies.visibility`), the proposed unit is
    structurally identical to the unit the runtime already matches; the command
    confirms this per `would_create` meeting (`parity_structural_match`). A full
    per-user parity matrix is intentionally **not** rebuilt here — that already
    has a dedicated command, `audit_bible_study_membership_readiness` — so 1C
    keeps its classification strict instead.
  - Options: `--apply`, `--limit N`, `--meeting-id ID`,
    `--verbose`/`--verbose-events` (per-meeting decisions), `--fail-on-issues`.
  - Tests: `studies/test_backfill_meeting_audience_command.py`.
  - **Runtime still does not read audience rows** after this slice.
- **BS-STRUCT.1D** — normal generation writes audience rows + `anchor_unit`.
  ✅ **implemented.** `generate_bible_study_meetings` (`studies/views.py`) now,
  for every **newly created** normal group-level `BibleStudyMeeting`, calls the
  new `write_normal_meeting_audience_scope(meeting)` helper:
  - It resolves `meeting.small_group.church_structure_unit`. **Only when that
    unit exists, is active, and is `UNIT_SMALL_GROUP`** does it create one
    `BibleStudyMeetingAudienceScope(meeting, unit)` row (via `get_or_create`) and
    set `meeting.anchor_unit = unit` **when that anchor is currently null**
    (`save(update_fields=["anchor_unit", "updated_at"])`, so the `small_group`
    column is never rewritten). `small_group` stays set as the compatibility
    mirror and `meeting_kind` stays `normal`.
  - **Invalid mapping is fail-closed.** If the group has no valid active
    `UNIT_SMALL_GROUP` mapping (unmapped, inactive unit, or wrong unit type), the
    legacy meeting is **still created** exactly as before (unchanged generation
    count/behavior) but gets **no audience row and no `anchor_unit`** — i.e. it
    stays a pre-1D legacy-only zero-row meeting — and the affected group names are
    surfaced to the manager in a `messages.warning`. This was chosen over
    "skip with warning" because it preserves existing generation behavior and
    never falsely presents a meeting as structure-native; existing-row backfill
    is BS-STRUCT.1C's job.
  - **Existing meetings are never mutated.** Rows are written only for meetings
    this run creates; meetings already present are skipped by the existing
    `get_or_create` missing-group logic and left untouched (no row, no anchor).
  - **`generation_key` left inert** in this slice (the `(lesson, small_group)`
    unique constraint already gives normal-meeting idempotency; a second
    identity key is deferred to the higher-level/joint slices per Section 4.5).
  - Idempotent: a second generation run creates no duplicate meetings and no
    duplicate audience rows.
  - Tests: new BS-STRUCT.1D methods in `studies/tests.py`
    (`BibleStudyModuleTests`).
  - **Runtime did not read audience rows as of this slice** (superseded by
    BS-STRUCT.1E). At 1D, visibility, Today/landing, and role/worship pickers
    all still keyed off `small_group`; this slice only stopped newly generated
    normal meetings from being zero-row legacy-only meetings. Since 1E,
    visibility and Today/landing read audience rows when present; role/worship
    pickers remain on `small_group` until BS-STRUCT.1F.
- **BS-STRUCT.1E** — visibility switches to **meeting audience rows + active
  primary membership**, with the single-`small_group` path kept only as zero-row
  fallback. Includes V2 landing / Today switch to audience-row matching.
  ✅ **implemented.**
  - **Row-first visibility with zero-row `small_group` fallback.**
    `BibleStudyMeeting.can_be_seen_by` keeps the unchanged manager override and
    the unchanged published / status / parent-lesson / parent-series member
    gates (`meeting_is_member_visible`). For ordinary users it now branches on
    `meeting_has_audience_scope_rows(self)`:
    - **When the meeting has one or more `BibleStudyMeetingAudienceScope` rows**
      those rows are the source of truth (`user_matches_meeting_audience_scopes`).
      The user matches when their **single active primary**
      `ChurchStructureMembership.unit` is one of the meeting's audience units
      **or a descendant** of one of them. Unlike the legacy small-group path
      there is **no `UNIT_SMALL_GROUP` gate**, so an audience row on a district /
      CM / EM unit is matched by a member of that unit or any descendant unit.
    - **When the meeting has zero audience rows** it falls back to the existing
      legacy `user_matches_meeting_small_group_membership(self.small_group)`
      path (mapped `UNIT_SMALL_GROUP` unit + active-primary membership), exactly
      as before this slice.
    - Fail-closed is preserved on both paths: anonymous, no active primary
      membership, requested / ended / future membership, **multiple** active
      primary memberships, unpublished / cancelled / draft meeting, and
      unpublished / inactive parent lesson or series all return `False`.
      `Profile.small_group` is **never** consulted on either path.
    - **Audience rows take precedence over the `small_group` fallback.** A
      meeting whose legacy `small_group` still points at the user's group but
      whose audience row targets a different branch is **not** visible to the
      original-group member and **is** visible to the audience-unit member.
  - **V2 landing / Today now uses meeting audience rows when present.**
    `get_v2_landing_context(user)` (also reused by Today via
    `reading/views.py`) no longer requires a resolved legacy small group when
    audience-row meetings exist. It resolves the user's active-primary
    membership ancestor-or-self unit ids
    (`get_membership_audience_candidate_unit_ids`) and selects upcoming
    published V2 meetings matching **either** an audience row on one of those
    units **or** the legacy `small_group` zero-row fallback, then confirms each
    candidate through `can_be_seen_by` (the per-meeting authority, so audience
    precedence still applies). The empty/no-group state is only shown when the
    user has **neither** a resolvable legacy group **nor** any active primary
    membership (e.g. a profile-only user), so a membership user with a null
    `small_group` still sees their audience-row meeting, and a member of a
    descendant unit sees a higher-level / district audience-row meeting.
    `user_small_group` is still returned for existing templates but no longer
    gates audience-row visibility; the template/context shape is otherwise
    unchanged.
  - **Generation is unchanged in this slice.** No generation, anchor, or
    `meeting_kind` write path was touched; this slice is read-only switching.
  - **Role / worship pickers still key off `small_group`** (single mapped unit)
    and are intentionally **not** changed here — that is BS-STRUCT.1F.
  - **`small_group` is not removed and the zero-row fallback remains.**
  - Tests: new BS-STRUCT.1E methods in `studies/tests.py`
    (`BibleStudyModuleTests`) covering detail visibility (null-`small_group`
    membership match, descendant match, district match, wrong-branch miss,
    profile-only miss, multiple-active-primary fail-closed, manager override,
    zero-row fallback, and audience-row precedence) and the landing/Today read
    path (membership with null group, descendant of district audience, wrong
    branch, zero-row fallback, precedence hide, profile-only empty state, and
    staff links).
- **BS-STRUCT.1F** — role / worship pickers read meeting audience rows (union of
  units) instead of the single `small_group` unit. ✅ **implemented.**
  - **Row-first picker candidates with zero-row `small_group` fallback.**
    `BibleStudyMeetingRoleForm` and `BibleStudyMeetingWorshipSongForm` now build
    their user dropdown through `filter_users_for_meeting_audience(users,
    meeting)`:
    - **When the meeting has one or more `BibleStudyMeetingAudienceScope` rows**
      those rows are the candidate source. Candidates are users with a **single
      active primary** `ChurchStructureMembership` whose unit is one of the
      meeting's audience units **or a descendant** of one of them. Unlike the
      legacy small-group path there is **no `UNIT_SMALL_GROUP` gate**, so audience
      rows on a district / CM / EM / custom unit offer that unit's members and any
      descendant unit's members. `Profile.small_group` is **never** consulted.
    - **When the meeting has zero audience rows** it falls back to the existing
      `filter_users_for_meeting_small_group_membership(users,
      meeting.small_group)` membership-core path, exactly as before this slice.
    - Fail-closed is preserved on the audience path: no active primary
      membership, requested / ended / future membership, **multiple** active
      primary memberships, and wrong-branch membership all exclude the user.
    - **Audience rows take precedence over the `small_group` mirror.** A meeting
      whose legacy `small_group` still points at one group but whose audience row
      targets a different unit offers the **audience** unit's members, not the
      `small_group` members.
  - **Edit forms keep the currently selected user available** even when that user
    no longer matches the meeting audience (unchanged edit behavior), and the
    blank-user + display-name fallback flow is unchanged.
  - **Visibility / detail access, V2 landing / Today, and generation are
    unchanged in this slice** — the read switch for those happened in
    BS-STRUCT.1E / 1D; this slice only changes role/worship candidate filtering.
  - **`small_group` is not removed and the zero-row fallback remains.** No
    models / schema / migrations changed.
  - Tests: new BS-STRUCT.1F methods in `studies/tests.py`
    (`BibleStudyModuleTests`) for both the role form and the worship-song form
    (audience-row match with null `small_group`, district/ancestor descendant
    match, wrong-branch miss, profile-only miss, multiple-active-primary
    fail-closed, zero-row `small_group` fallback, audience-row precedence over
    `small_group`, and selected user/lead retained on edit when outside the
    audience).
- **BS-STRUCT.1G** — support higher-level / joint generation cases (5.2–5.4),
  including replacement/suppression marking.
- **BS-STRUCT.1H** — stop normal write paths from creating legacy-only meeting
  audience (zero-row guard, SE-AS.7A pattern).
- **BS-STRUCT.1I** — production backfill/apply + post-apply audit.
- **BS-STRUCT.2+** — retire the legacy `SmallGroup` Bible Study bridge and the
  zero-row fallback once all consumers are proven migrated (coordinate with
  CS-CORE Section 12 legacy retirement).

The user-side resolver migration that ServiceEvent/Bible Study needed for
*visibility* is **already done** for Bible Study (CS-CORE.2C-B / 3B), so this
plan's hard work is concentrated in the meeting-audience representation
(1B–1D) and the read-switch (1E–1G), not in re-deriving "who the user is."

---

## 7. Risks / Open Questions (need user / planner decision)

1. **Definition of "leaf Bible Study unit."** Is it strictly
   `UNIT_SMALL_GROUP`, or any unit with no active Bible-Study-relevant children?
   Generation default and visibility both depend on this.
2. **Campus / Singles modeling.** Are they small-group-level units, or
   fellowship/department/custom units? This determines whether their meetings are
   "leaf" meetings and whether the current `UNIT_SMALL_GROUP` visibility check
   would have failed them today.
3. **Who can create district/CM-level or joint meetings?** A new staff
   capability, or existing `CAP_MANAGE_BIBLE_STUDIES`? Higher-level meetings
   suppress group meetings, so the authority matters.
4. **Today-page display of joint / higher-level meetings.** How should a user
   whose group's week was replaced by a district joint meeting see it — as their
   meeting, or as a clearly-labeled joint meeting? Landing logic is currently
   single-group-centric.
5. **Whether joint meetings consume any group rotation slot.** Default proposed:
   no (shift forward). Confirm, and confirm whether some joint meetings *should*
   consume a slot.
6. **Meeting identity / idempotency key (Section 4.5). ✅ Resolved in
   BS-STRUCT.1B.** The existing `(lesson, small_group)` unique constraint was
   made **conditional on a non-null `small_group`** (normal group meetings still
   cannot duplicate), and a nullable `generation_key` was added with a
   **conditional** `(lesson, generation_key)` unique constraint enforced only
   when the key is set — so multiple null-`small_group` / null-key
   higher-level/joint meetings per lesson are allowed. BS-STRUCT.1B-FU1
   normalizes blank/whitespace `generation_key` values to `None` so an empty
   string never collides as a set value. No runtime depends on `generation_key`
   yet; the future generation slices (1D/1G) will choose how to populate it.
7. **`small_group` nullability impact. ✅ Audited and implemented in
   BS-STRUCT.1B.** `small_group` is now nullable/blank with
   `on_delete=SET_NULL`; `__str__`, manage-list filters, and landing continue to
   work because normal group-level meetings still set it, and the existing
   tests/suite pass. Higher-level/joint meetings can now leave it null. The
   field remains a compatibility mirror; later slices (1E/1F) move
   visibility/pickers off it onto audience rows before it is eventually retired.
8. **Legacy V1 `BibleStudySession`.** Confirmed out of scope (retirement target);
   this migration must not touch its visibility. Re-confirm no slice accidentally
   couples V1 into the new audience model.
9. **Group-specific guide customization.** Already exists (`group_direction` /
   `group_questions`); confirm whether the real workflow needs anything beyond
   these two fields before treating prep as "done for migration."
10. **Series-vs-meeting audience relationship.** Should a meeting's audience be
    constrained to a subset of its series' audience, or independent? Affects
    generation and validation.

---

## 8. Verification (docs-only)

```powershell
cd E:\bible-reading\bible_reading_v2-claude
git diff --check
git status --short
```

No code, template, test, model, or migration changes; no makemigrations/check
runs are required for a docs-only slice. (See final report for results.)
