# Bible Study Structure-Native Migration Plan (BS-STRUCT.1A)

## 0. Purpose and Status

This document **began** as the BS-STRUCT.1A design/audit slice (docs-only): it
defined how the Bible Study module should migrate to the new Church Structure
core (`ChurchStructureUnit` + `ChurchStructureMembership`) while preserving the
current module's useful behavior and supporting the real church Bible Study
workflow. That original BS-STRUCT.1A slice changed no models, migrations, forms,
views, templates, tests, or runtime behavior.

Status: **partially migrated through BS-STRUCT.2A.** The design slices that
followed BS-STRUCT.1A are now implemented:

- the meeting-audience model foundation exists (`BibleStudyMeetingAudienceScope`,
  `anchor_unit`, nullable `small_group` mirror, `generation_key`, `meeting_kind`
  — BS-STRUCT.1B);
- backfill/audit and normal-generation/manual-form writers populate meeting
  audience rows (BS-STRUCT.1C / 1D / 1H);
- visibility, V2 landing / Today, and role/worship pickers now treat
  `BibleStudyMeetingAudienceScope` rows as the V2 runtime source of truth.
  Zero-row V2 meetings fail closed for ordinary users, and
  `BibleStudyMeeting.small_group` no longer grants ordinary runtime access
  (BS-STRUCT.1E / 1F / 2A);
- a read-only retirement-readiness audit command exists (BS-STRUCT.1J);
- normal generation is **structure-unit-native**: it targets `ChurchStructureUnit`
  leaf small-group units, keys idempotency on a per-unit `generation_key`, and
  keeps `small_group` only as a compatibility mirror (BS-STRUCT.1L);
- normal generation now **requires** series structure audience rows: a schedule
  with zero `BibleStudySeriesAudienceScope` rows **fails closed** (no meetings,
  manager warning) instead of falling back to legacy `scope_type` / `district` /
  `small_group` (BS-STRUCT.1M);
- the staff meeting manage-list filter is **structure-audience aware**: it
  filters by `ChurchStructureUnit` (GET `unit`) over meeting audience rows
  (unit-or-descendant), matches audience rows only, and no longer exposes a
  legacy `small_group` select; old `?small_group=<id>` URLs are still tolerated
  only as an in-view mapping to `unit` (BS-STRUCT.1N / 2A);
- the manual normal meeting create/edit form is **structure-unit-native**: it
  chooses an active `UNIT_SMALL_GROUP` `ChurchStructureUnit` (`audience_unit`)
  as the audience source of truth, writes the audience row + `anchor_unit` +
  per-unit `generation_key`, keeps `small_group` only as a mirror when exactly
  one active legacy group maps, and no longer exposes a legacy `small_group`
  select (BS-STRUCT.1O);
- obsolete small-group-keyed write/generation helpers were removed
  (`write_normal_meeting_audience_scope`, the compatibility-only
  `sync_normal_meeting_audience_scope`, and the never-produced
  `GENERATION_WARNING_UNMAPPED_GROUP` constant + its unreachable view warning
  branch), so no dead code can lure future work back onto a legacy
  `small_group` write path (BS-STRUCT.1P);
- BS-STRUCT.2A retired the V2 zero-row ordinary-user runtime fallback after a
  clean readiness gate: 29 meetings checked, 29 with audience rows, zero
  zero-row blockers, `db_data_blockers_clear = true`,
  `legacy_small_group_fallback_still_present = false`, and
  `runtime_zero_row_fallback_removed = true`. No schema/model deletion and no
  migration were created.

So the document as a whole is **no longer "docs-only / changes no runtime
behavior."** The runtime now reads meeting audience rows, and zero-row V2
meetings fail closed for ordinary users. What remains is the legacy generation /
idempotency / display bridge and V1 archive retirement, not an ordinary-user
zero-row runtime access path.
This document does not stage/commit/push anything.

It deliberately follows the proven ServiceEvent runtime-migration pattern
(`docs/SERVICE_EVENT_AUDIENCE_RUNTIME_MIGRATION_PLAN.md`) as a *pattern* only.
Bible Study has its own domain model and must not be blindly copied — in
particular, ServiceEvent has a single optional `ServiceEventAudienceScope` set
per event, whereas a Bible Study **meeting** was originally hard-bound to exactly
one legacy `SmallGroup` — the central thing this migration set out to change, and
which the row-first audience model (BS-STRUCT.1B onward) now does.

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
- **`BibleStudyMeeting`** — the concrete meeting for one lesson. Carries
  `meeting_datetime`, `location[_en]`, `meeting_link`, group-local
  `group_direction[_en]` / `group_questions[_en]`, `status`, optional
  `service_event` FK, and de-emphasized `discussion_leader_user` /
  `discussion_leader_name` compatibility fields. Structure-native fields added
  through BS-STRUCT.1B onward:
  - `small_group = FK(SmallGroup, null=True, blank=True, on_delete=SET_NULL)`
    is now **nullable/blank** and a **compatibility mirror**, not the source of
    truth. Normal group-level meetings still set it one-to-one with a leaf group;
    higher-level / joint meetings may leave it null.
  - **`BibleStudyMeetingAudienceScope(meeting, unit)` rows exist** and are the
    **row-first meeting audience source** when one or more rows are present
    (visibility, V2 landing/Today, and role/worship pickers read them — see 1.5).
  - `anchor_unit = FK(ChurchStructureUnit, null=True, blank=True,
    on_delete=SET_NULL)` exists for **display / grouping / ownership only**, not
    visibility.
  - `generation_key` (nullable CharField) exists with a conditional
    `(lesson, generation_key)` unique constraint, but **no runtime reads it yet**.
  - `meeting_kind` (CharField: `normal` default / `higher_level` / `joint` /
    `cancelled_replacement`) exists as a rotation/replacement-readiness marker.
  - The legacy **`(lesson, small_group)` unique constraint is now conditional on
    a non-null `small_group`** (BS-STRUCT.1B), so normal group-level duplicates
    are still rejected while multiple null-`small_group` higher-level/joint
    meetings per lesson are allowed.
- **`BibleStudyMeetingRole`** — per-meeting responsibilities (discussion leader,
  worship lead, pianist, support, host); user FK (nullable) + display-name
  fallback.
- **`BibleStudyMeetingWorshipSong`** — per-meeting worship set (order, title,
  key, links, arrangement/support notes, worship-lead user/name fallback).

Legacy V1 stack, retired from app runtime (`docs/LEGACY_BIBLE_STUDY_SESSION_RETIREMENT_DECISION.md`):

- **`BibleStudySession`** (+ `BibleStudyGuide` one-to-one, +
  `BibleStudyWorshipSong`). BS-V1-RETIRE.1A retires app-level V1 visibility for
  ordinary users and managers; `Profile.small_group` / `scope_type` / `district`
  / `small_group` no longer grant V1 app access. App-level create/detail/edit/
  delete/worship routes redirect with retirement messaging. **Decision: do not
  migrate V1 to membership-core or to structure audience; it is pilot/archive
  data pending explicit purge, not part of this migration.**

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

Since BS-STRUCT.1L, normal generation is **structure-unit-native**: the
generated target is a `ChurchStructureUnit` leaf small-group unit, not
fundamentally a legacy `SmallGroup`. `resolve_normal_generation_targets(series)`
(`studies/services.py`) returns a deduplicated, deterministically ordered list of
`GenerationTarget(unit, small_group)` where `unit` is an active
`UNIT_SMALL_GROUP` unit and `small_group` is an optional legacy mirror attached
only when exactly one active legacy group maps to that unit.

`get_bible_study_meeting_generation_preview()` + `generate_bible_study_meetings()`
(`studies/views.py`):

1. **Targets.** When the series has `BibleStudySeriesAudienceScope` rows, each
   selected unit expands to its active descendant-or-self `UNIT_SMALL_GROUP`
   units (one target each — this path can target structure-native units that
   have no legacy `SmallGroup`). **Since BS-STRUCT.1M, when the series has zero
   audience rows generation fails closed**: `resolve_normal_generation_targets()`
   returns no targets and a single `GENERATION_WARNING_MISSING_SERIES_AUDIENCE`
   warning. It **no longer** consults legacy `get_eligible_small_groups()` /
   `scope_type` / `district` / `small_group`, so no legacy-only or zero-row
   meeting is generated from legacy series scope.
2. **Preview.** Targets are diffed against existing meetings. A target counts as
   existing when any meeting matches it by `generation_key`
   (`normal-unit:{unit_id}`), by the legacy `small_group` mirror, or by a single
   audience row equal to the target unit — so pre-1L meetings (mirror + row, no
   key) are recognized and never duplicated. The preview lists `missing_targets`
   and (BS-STRUCT.1M) a `missing_series_audience` flag so the GET page and the
   POST handler can surface a bilingual "configure the schedule audience scope
   first" warning when the series has no structure audience rows.
3. **On POST**, one `BibleStudyMeeting` is created **per missing target** with
   `small_group = target.small_group` (or `None`), `anchor_unit = target.unit`,
   `meeting_kind = normal`, the stable per-unit `generation_key`, one
   `BibleStudyMeetingAudienceScope` row for the target unit, a default Friday
   19:30 datetime, and `status=draft`.

Generation is idempotent (skips existing, including cancelled) and creates no
duplicate meeting or audience row. **It still produces one normal meeting per
leaf small-group unit; higher-level / multi-unit joint generation remains a later
slice (BS-STRUCT.1G).** A unit with several active legacy groups is ambiguous, so
its meeting carries no `small_group` mirror (structure-native, warned).

### 1.4 Where each structure concept is used

| Concept | Where used in `studies/` |
| --- | --- |
| `SmallGroup` | **No longer the V2 visibility / picker source, the manage-list filter, or the manual-form source field.** Now only a **compatibility mirror** on `BibleStudyMeeting.small_group` (nullable, `SET_NULL`), written by generation (BS-STRUCT.1L) and the manual form (BS-STRUCT.1O) when exactly one active legacy group maps to the target unit; the secondary `(lesson, small_group)` idempotency constraint; plus `BibleStudySeries.small_group` (legacy scope) and `BibleStudySession.small_group` (V1). |
| `District` | `BibleStudySeries.district` / `BibleStudySession.district` legacy scope fields only. |
| `Profile.small_group` | **No longer read by V2 meeting visibility or pickers, and no longer grants V1 app access after BS-V1-RETIRE.1A.** Still read by the read-only audit comparator in `structure_readiness.py` (`get_user_legacy_small_group`). |
| `ChurchStructureUnit` | `BibleStudySeriesAudienceScope.unit` (series audience), **`BibleStudyMeetingAudienceScope.unit` (meeting audience, V2 runtime source of truth)**, and **`BibleStudyMeeting.anchor_unit` (display/grouping/ownership)**; also the mapping target for `SmallGroup.church_structure_unit` used in generation/resolution and legacy mirror compatibility. |
| `ChurchStructureMembership` | **The V2 runtime user-belonging source** for meeting visibility (`studies/visibility.py`, CS-CORE.2C-B) and for role/worship user pickers (CS-CORE.3B). Single active primary membership only; multiple/none fails closed. |

### 1.5 Current visibility behavior

`BibleStudyMeeting.can_be_seen_by()` → `studies/visibility.py`:

1. Manager override (staff / superuser / `CAP_MANAGE_BIBLE_STUDIES` /
   `CAP_PUBLISH_BIBLE_STUDY_GUIDES`) → always visible.
2. `meeting_is_member_visible()` — meeting published + lesson published + series
   active & published.
3. Audience-row match (BS-STRUCT.1E / 2A):
   `user_matches_meeting_audience_scopes(user, meeting)` is the ordinary-member
   source of truth — the user's single active primary membership unit must be
   one of the audience units **or a descendant** (any unit level; no
   `UNIT_SMALL_GROUP` gate). When the meeting has **zero** audience rows, it
   fails closed for ordinary users. `BibleStudyMeeting.small_group` and
   `Profile.small_group` grant no ordinary V2 meeting visibility.

**Current state:** visibility is membership-core and audience-row authoritative.
A meeting with audience rows can express any audience level (single group,
district, CM/EM, custom, or multi-unit joint). A zero-row meeting is an
invalid/safety state for ordinary users, not a legacy access path.

### 1.6 Current Today / landing behavior

`get_v2_landing_context()` (`studies/views.py`, reused by `reading/views.py` for
Today, per CS-CORE.3C audit) is **audience-row based** (BS-STRUCT.1E / 2A):

- It resolves the user's active primary membership ancestor-or-self unit ids
  (`get_membership_audience_candidate_unit_ids`) and selects upcoming published
  meetings matching an audience row on one of those units, confirming each
  through `can_be_seen_by`.
- The empty/no-group state is shown when the user has no active primary
  membership candidate ids. `Profile.small_group` / legacy visible small groups
  no longer admit zero-row meetings. A membership user with a null
  `small_group` still sees their audience-row meeting, and a descendant-unit
  member sees a higher-level / district audience-row meeting.
- Today additionally surfaces the user's linked `BibleStudyMeetingRole` chips.

So joint / higher-level audience-row meetings appear here. Zero-row V2 meetings
do not appear for ordinary users. `Profile.small_group` is not consulted.

### 1.7 Current worship / song / leader / role picker behavior

- `BibleStudyMeetingRoleForm` and `BibleStudyMeetingWorshipSongForm` filter the
  user dropdown through `filter_users_for_meeting_audience(users, meeting)`
  (BS-STRUCT.1F / 2A): candidates are active-primary members of any audience
  unit (or descendants). A zero-row meeting returns no ordinary candidates.
  Candidate filtering is single-active-primary only (CS-CORE.3B) and never
  consults `Profile.small_group`.
- Worship set / roles are per-meeting; manager-controlled. No role-aware editing
  permissions yet (BS-V2.7 deferred). No automatic assignment, rotation,
  availability, swap, or reminders.

### 1.8 Current V1 retired app paths

V1 `BibleStudySession` create/detail/edit/delete/worship app routes redirect
with retirement messaging after BS-V1-RETIRE.1A. Direct detail is no longer an
app archive surface for ordinary users or managers. Django Admin remains the
emergency maintenance path until a later explicit V1 pilot-data purge slice.
**Out of scope for this migration** — see Section 7 open question on V1 data
cleanup.

### 1.9 Remaining legacy consumers (the migration surface)

Runtime **reads** for meeting visibility, V2 landing / Today, and role/worship
pickers are now audience-row authoritative with zero-row meetings failing closed
for ordinary users (BS-STRUCT.1E/1F/2A), so the remaining legacy surface is
concentrated in the **write**, **resolution**, mirror/display, and V1 archive
paths:

1. **Generation** is structure-unit-native since BS-STRUCT.1L and
   **structure-audience-required** since BS-STRUCT.1M: it resolves
   `ChurchStructureUnit` leaf `UNIT_SMALL_GROUP` targets via
   `resolve_normal_generation_targets()`, keys idempotency on the per-unit
   `generation_key` (`normal-unit:{unit_id}`), and writes one audience row +
   `anchor_unit` per target. `small_group` is attached only as a compatibility
   mirror (and may be `None` for a structure-native unit). **The series legacy
   `scope_type` / `district` / `small_group` fields are no longer a generation
   source**: a series with zero `BibleStudySeriesAudienceScope` rows now **fails
   closed** — `resolve_normal_generation_targets()` returns no targets and a
   `GENERATION_WARNING_MISSING_SERIES_AUDIENCE` warning, and the view tells the
   manager to configure the schedule audience scope first. (`get_eligible_small_groups()`
   survives only as a model-level legacy helper / display aid, not as a
   generation fallback.) The conditional `(lesson, small_group)` unique
   constraint remains as secondary protection alongside the
   `(lesson, generation_key)` constraint.
2. **Manual create/edit meeting form** — since BS-STRUCT.1O the normal manual
   `BibleStudyMeetingForm` is **structure-unit-native**. The visible source field
   is `audience_unit`, a single active `UNIT_SMALL_GROUP` `ChurchStructureUnit`
   (path-labelled); the legacy `small_group` select is gone. Create/edit go
   through `sync_normal_meeting_audience_scope_for_unit(meeting, unit)`, which
   writes one `BibleStudyMeetingAudienceScope` row for the selected unit, sets
   `anchor_unit`, sets `meeting_kind = normal`, sets the per-unit
   `generation_key` (`normal-unit:{unit_id}`, shared with generation), and sets
   `small_group` only as a mirror when **exactly one** active legacy group maps
   to the unit (`None` for a structure-native unit with no legacy group or an
   ambiguous many-to-one mapping). Duplicate prevention rejects a second meeting
   for the same `(lesson, unit)` (by matching `generation_key` or an existing
   single-unit audience row) before save. On edit, the initial unit resolves in
   priority order: a single `UNIT_SMALL_GROUP` audience row → an active
   `UNIT_SMALL_GROUP` `anchor_unit` → the unit mapped from the existing
   `small_group` → blank. The form still refuses to edit a higher-level / joint /
   multi-unit meeting (it rejects a meeting whose `meeting_kind != normal` or
   whose audience rows are not a single small-group row, leaving those rows
   untouched); that higher-level write UI is deferred. The legacy
   small-group-keyed `sync_normal_meeting_audience_scope(meeting)` /
   `write_normal_meeting_audience_scope(meeting)` helpers that earlier slices kept
   around were **removed in BS-STRUCT.1P** as obsolete; only
   `resolve_normal_small_group_unit(small_group)` survives, and only to pre-fill
   the edit `audience_unit` from an existing legacy `small_group` (it is not a
   write path).
3. **Zero-row meetings** — retired as an ordinary-user runtime path in
   BS-STRUCT.2A. Manual writes no longer create legacy-only zero-row meetings,
   readiness reported 29/29 meetings with audience rows and zero blockers, and
   runtime now fails closed for ordinary users when a meeting has no
   `BibleStudyMeetingAudienceScope` rows. The read-only
   `audit_bible_study_structure_retirement_readiness` command remains a standing
   diagnostic for zero-row safety, mirror drift, and rollback/backfill context.
4. **Manage-list filter** — **since BS-STRUCT.1N the staff meeting manage-list no
   longer exposes / filters by legacy `small_group`.** It now filters by
   `ChurchStructureUnit` (GET `unit`): a meeting matches when it has a
   `BibleStudyMeetingAudienceScope` row on the selected unit or a descendant
   (mirroring runtime visibility). A legacy `?small_group=<id>` query (with no
   `unit`) is tolerated
   and **mapped internally** to that group's structure unit within the same
   request — it is handled in-view, not an HTTP redirect — so old bookmarks keep
   working, but the UI field is gone. After BS-STRUCT.2A, that mapped unit still
   matches audience rows only; `small_group` remains a compatibility mirror /
   display / history / backfill / idempotency field, not a manage-list fallback
   source.
5. **Series legacy scope fields** (`scope_type` / `ministry_context` /
   `district` / `small_group`) + `apply_audience_legacy_fallback()` — still
   exist for compatibility / display / coexistence, but **since BS-STRUCT.1M they
   are no longer a generation source** (generation requires audience rows). The
   fields remain (no schema change) and `apply_audience_legacy_fallback()` still
   mirrors selected units into them for any code that still reads legacy scope.
6. **V1 `BibleStudySession`** — legacy-only, retirement target (excluded).

Note: the runtime reads are **already** membership-core in their *user*
resolution and now structure-native in *how the meeting's audience is read*
(audience rows); `Profile.small_group` and `BibleStudyMeeting.small_group` are
not ordinary-user V2 visibility, landing/Today, or picker access sources. The
remaining blockers are the legacy generation / mirror / idempotency bridge,
field-level cleanup, and V1 archive/retirement execution.

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

### 3.1 Migration blockers cleared by BS-STRUCT.2A

The former V2 meeting-runtime blockers have been cleared:

1. `BibleStudyMeetingAudienceScope(meeting, unit)` exists and is the V2 runtime
   source of truth for ordinary-member visibility.
2. Meeting generation and manual write paths write structure audience rows rather
   than legacy-only `small_group` audience.
3. Visibility, `/studies/` / Today, and role/worship pickers read meeting
   audience rows plus active primary `ChurchStructureMembership`; zero-row V2
   meetings fail closed for ordinary users.
4. Existing production V2 meetings were audited/backfilled: 29 checked, 29 with
   audience rows, zero zero-row blockers.
5. `BibleStudyMeeting.small_group` remains only mirror/display/backfill/history/
   idempotency compatibility. It is not an ordinary-member V2 visibility,
   landing/Today, or role/worship picker fallback.

Remaining migration work is now field-level cleanup, the generation/idempotency
bridge, and V1 `BibleStudySession` archive/retirement.

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
- **BS-STRUCT.1H** — stop the **normal manual** `BibleStudyMeetingForm`
  create/edit path from creating or preserving legacy-only zero-row meetings
  (zero-row guard, SE-AS.7A pattern). ✅ **implemented.**
  - **Reusable normal-meeting audience logic moved to `studies/services.py`.**
    `write_normal_meeting_audience_scope` (the BS-STRUCT.1D generation-side
    create-only writer) was moved from `studies/views.py` to
    `studies/services.py` unchanged in behavior (`views.py` now imports it), and
    a shared `resolve_normal_small_group_unit(small_group)` helper centralizes
    the "active `UNIT_SMALL_GROUP` mapping" validation both writers use. A new
    `sync_normal_meeting_audience_scope(meeting)` handles the manual-form
    create/repair/realign case. No circular imports: `forms` → `services` →
    `models` / `visibility`.
  - **Manual create now writes audience rows.** `BibleStudyMeetingForm` makes
    `small_group` required, and `clean()` rejects (form invalid, nothing saved) a
    selected group whose `church_structure_unit` is missing, inactive, or not
    `UNIT_SMALL_GROUP`. On a valid save the create/edit views call
    `sync_normal_meeting_audience_scope` inside a `transaction.atomic()`, which
    creates exactly one `BibleStudyMeetingAudienceScope(meeting, mapped unit)`
    row and sets `anchor_unit` when null. `small_group` stays set as the
    compatibility mirror and `meeting_kind` stays `normal`. So a normal manual
    meeting is never left as a legacy-only zero-row meeting, and an invalid
    mapping fails validation instead of creating one.
  - **Manual edit repairs or realigns the normal audience row.** Editing a
    zero-row meeting with a valid group creates the missing row and sets the
    anchor when null. Changing the selected group updates the single normal
    small-group row to the newly mapped unit and **drops the stale old row** so
    the row-first runtime and the `small_group` mirror stay aligned; the anchor
    follows the change **only** when it still mirrors the old group's unit
    (an unrelated, manually set anchor is preserved).
  - **Higher-level / joint / multi-unit meetings are protected.** This
    small-group-only form fails safely (validation error, rows untouched) when
    the existing meeting has `meeting_kind != normal`, multiple audience rows, or
    a single non-small-group (district / CM / EM / custom) audience row, so a
    district/joint meeting is never silently converted into a fake single-group
    meeting. Building an audience-scope picker UI for higher-level/joint meetings
    remains deferred (BS-STRUCT.1G and later).
  - **Zero-row fallback still remains** for old data in visibility, landing/Today,
    and role/worship pickers until production backfill/apply (BS-STRUCT.1I) and
    fallback retirement (BS-STRUCT.2+). `small_group` is not removed.
  - **Unchanged in this slice:** generation behavior (the moved helper is
    behavior-identical), visibility/detail access, landing/Today, role/worship
    picker behavior, and models/schema/migrations.
  - Tests: new BS-STRUCT.1H methods in `studies/tests.py`
    (`BibleStudyModuleTests`) — manual create writes one row + anchor and keeps
    the mirror/`normal` kind; unmapped / inactive-unit / wrong-type create is
    invalid and creates no meeting; edit of a zero-row meeting creates the row;
    edit changing the group replaces the row and drops the stale one (anchor
    follows); edit does not clobber a multi-unit or higher-level audience
    meeting.
- **BS-STRUCT.1I** — production backfill/apply + post-apply audit.
  ⚠️ **partially completed (local real-data only).** Local real-data sqlite apply
  completed on 2026-06-15. Production apply remains a deployment/runbook step
  unless separately confirmed.
  - **Local real-data apply result (2026-06-15).** Run against the local
    real-data sqlite DB only (`bible_reading_v2/db.sqlite3`); no production DB was
    touched. With `--apply`: 29 meetings checked, 29
    `BibleStudyMeetingAudienceScope` rows created, 29 `anchor_unit` values
    backfilled. `legacy_small_group_mutated = 0` and `runtime_switched = false`
    (additive only; no runtime/generation/Today-landing/picker behavior changed).
    Post-state: `BibleStudyMeeting.objects.count() = 29` and
    `BibleStudyMeetingAudienceScope.objects.count() = 29`.
  - **Post-apply dry-run (idempotency + clean audit).** 29 meetings checked,
    `skipped_existing_audience = 29`, `would_create = 0`, `created = 0`, and all
    issue buckets = 0. `--fail-on-issues` exited `0`.
  - **Production rollout boundary.** Production rollout is a separate runbook
    step and was **not** run here. On production: (1) run database migrations
    first; (2) run the backfill command as a **dry-run** and review; (3) only if
    the dry-run is clean, run it with `--apply`; (4) re-run the dry-run post-apply
    with `--fail-on-issues` and confirm it exits `0`. **Do not remove the zero-row
    fallback** until production has been applied and verified clean.
- **BS-STRUCT.1J** — Bible Study legacy-retirement **readiness audit**
  (read-only). ✅ **implemented.** Management command
  `audit_bible_study_structure_retirement_readiness`
  (`studies/management/commands/audit_bible_study_structure_retirement_readiness.py`).
  - **Strictly read-only.** It scans **every** `BibleStudyMeeting` row
    (all statuses, since every meeting must carry audience rows before the
    fallback can go) and reports human-readable counters. It has **no
    `--apply`**, creates/edits/deletes **nothing** (no `BibleStudyMeeting`,
    `BibleStudyMeetingAudienceScope`, `SmallGroup`, `ChurchStructureUnit`,
    `ChurchStructureMembership`, or `Profile` writes), and changes **no** runtime
    behavior (visibility, landing/Today, role/worship pickers, generation, and
    forms are untouched). It audits whichever DB Django is configured to use, so
    it needs no production access of its own.
  - **What it proves.** It quantifies exactly what remains before the zero-row
    `small_group` fallback can be removed: how many meetings still have **zero**
    audience rows (the meetings still served only by the fallback), how many have
    single-group / higher-level / multi-unit / joint audience, the health of each
    meeting's legacy `small_group` mirror mapping (unmapped / inactive / wrong
    unit type), `anchor_unit` presence/mismatch, and any disagreement between a
    single small-group audience row and its `small_group` mirror unit.
  - **Counters:** `meetings_checked`, `meetings_with_audience_rows`,
    `meetings_without_audience_rows`, `normal_meetings_without_audience_rows`,
    `meetings_with_null_small_group`,
    `meetings_with_existing_audience_and_null_small_group`,
    `meetings_with_single_small_group_audience`,
    `meetings_with_multi_unit_audience`, `meetings_with_higher_level_audience`,
    `meetings_with_anchor_unit`, `meetings_missing_anchor_unit`,
    `meetings_anchor_mismatch_small_group_unit`, `meetings_small_group_unmapped`,
    `meetings_small_group_inactive_unit`, `meetings_small_group_wrong_unit_type`,
    `meetings_audience_mismatch_small_group_mirror`, plus fixed-truth flags
    `legacy_small_group_fallback_still_present = true`,
    `db_data_blockers_clear` (machine-checkable: no hard blockers in the DB), and
    `runtime_zero_row_fallback_removable = false`.
  - **Hard blockers vs warnings.** Only two counters are **hard blockers** (and
    only they trip a nonzero exit under `--fail-on-blockers`):
    `meetings_without_audience_rows` (rule 1 — any zero-row meeting still depends
    on the fallback; this subsumes `normal_meetings_without_audience_rows` and
    the null-`small_group`-with-zero-rows case, rule 6) and
    `meetings_audience_mismatch_small_group_mirror` (rule 2 — a single
    small-group audience row whose unit disagrees with its active-`UNIT_SMALL_GROUP`
    `small_group` mirror; classified **explicitly as a blocker** because the
    row-first runtime and the legacy mirror point at different units). Everything
    else is a **warning**: broken mirror mappings
    (`meetings_small_group_unmapped` / `_inactive_unit` / `_wrong_unit_type`) are
    data hygiene (already a hard blocker via `meetings_without_audience_rows`
    when the meeting is also zero-row; otherwise the row-first runtime no longer
    depends on the mirror), and `anchor_unit` issues
    (`meetings_missing_anchor_unit` / `meetings_anchor_mismatch_small_group_unit`)
    are warnings because `anchor_unit` is display/grouping/ownership only and
    never a visibility source (rule 7). A single higher-level audience row,
    multi-unit/joint audience, and null `small_group` **with** audience rows are
    acceptable, not blockers (rules 3–5). `Profile.small_group` is never consulted
    (rule 8); V1 `BibleStudySession` is excluded as a separate retirement target
    (rule 9).
  - **This audit does not remove the fallback.** It is purely diagnostic. Even
    when `db_data_blockers_clear` is `true`, `runtime_zero_row_fallback_removable`
    stays `false` by construction, because removal also requires a **separately
    verified production rollout** (BS-STRUCT.1I) that this command cannot confirm.
    The local configured `-claude` worktree DB currently has **0 meetings**
    (clean audit, all counters `0`); the 29 real meetings backfilled at
    BS-STRUCT.1I live in the sibling `bible_reading_v2/db.sqlite3`, which is where
    this audit should be run before any fallback-removal decision.
  - **Local real-data audit result (2026-06-16, `bible_reading_v2/db.sqlite3`).**
    `audit_bible_study_structure_retirement_readiness --verbose`: 29 meetings
    checked, **29 with audience rows**, `meetings_without_audience_rows = 0`,
    `normal_meetings_without_audience_rows = 0`, all 29 with a single small-group
    audience row and an anchor unit, and **zero hard blockers** (every issue
    counter `0`). `db_data_blockers_clear = true` and `--fail-on-blockers` exited
    cleanly. BS-STRUCT.2A later reported the same safety condition for the
    configured data (29 checked, 29 with rows, 0 blockers) and retired the
    ordinary-user zero-row runtime fallback in code.
  - Options: `--verbose` (lists meeting id / lesson title / `small_group` for
    each blocker and warning category), `--fail-on-blockers` (nonzero exit only
    when a hard blocker is present; still read-only).
  - Tests: `studies/test_retirement_readiness_command.py`.
  - **Remaining legacy surfaces after 1J** (none removed by that slice; updated
    after BS-STRUCT.2A):
    - zero-row meetings are now a fail-closed safety state for ordinary users,
      not a `small_group` fallback path;
    - **generation** is now structure-unit-native after BS-STRUCT.1L/1M: normal
      generation targets active `UNIT_SMALL_GROUP` leaves, writes audience rows,
      and keys primary idempotency on `generation_key`; `small_group` remains an
      optional mirror and secondary compatibility/idempotency guard only;
    - **manage-list filters** now filter by audience rows only while tolerating
      old `?small_group=` URLs as a mapping to `unit`;
    - **series zero-row legacy generation fallback is retired**: schedules with
      zero `BibleStudySeriesAudienceScope` rows fail closed for normal generation
      with a warning rather than falling back to legacy scope fields;
    - **V1 `BibleStudySession`** remains excluded / a retirement target;
    - field-level legacy cleanup and V1 archive/retirement remain separate.
- **BS-STRUCT.1L** — normal generation becomes **structure-unit-native**.
  ✅ **implemented.** Code/tests/docs only; no model/schema/migration change (the
  `anchor_unit`, `generation_key`, and `meeting_kind` fields already existed).
  - **New resolver.** `resolve_normal_generation_targets(series)`
    (`studies/services.py`) returns `(targets, warnings)` where each
    `GenerationTarget(unit, small_group)` is one active `UNIT_SMALL_GROUP`
    `ChurchStructureUnit` leaf. With series audience rows, each selected unit
    expands to its active descendant-or-self small-group units (one target each,
    including structure-native units with no legacy mirror). With zero audience
    rows it falls back to `get_eligible_small_groups()` and converts each
    eligible group to its mapped active small-group unit. Targets are
    deduplicated by unit id and deterministically ordered by unit
    `sort_order` / `code` / `name` / `id`. The legacy `small_group` mirror is
    attached only when **exactly one** active legacy group maps to the unit;
    ambiguous (many-to-one) units get no mirror (warned), and duplicate eligible
    groups collapse to one target with no mirror.
  - **Generation key.** `normal_generation_key_for_unit(unit)` →
    `normal-unit:{unit_id}`. Keyed on the structure unit (not `small_group`)
    because the target is now a unit; this makes generation idempotent even for a
    structure-native unit with no legacy mirror, enforced by the existing
    `(lesson, generation_key)` conditional unique constraint.
  - **Existing-meeting detection.** `build_existing_normal_meeting_index()` +
    `find_existing_meeting_for_target()` match a target against existing meetings
    by `generation_key`, by legacy `small_group` mirror, **or** by a single
    audience row equal to the target unit — so pre-1L meetings (mirror + one row,
    no key) are recognized and never duplicated; cancelled meetings still count
    as existing.
  - **Creation.** `create_normal_meeting_for_target()` writes one meeting per
    missing target with `small_group = target.small_group` (or `None`),
    `anchor_unit = target.unit`, `meeting_kind = normal`, the per-unit
    `generation_key`, and one audience row for the target unit. Default Friday
    19:30 datetime and `status=draft` behavior is preserved.
  - **Fail-closed mappings.** Legacy-fallback groups whose mapping is
    missing / inactive / wrong-type are **skipped with a manager warning**
    instead of creating a legacy-only zero-row meeting (a behavior change from
    BS-STRUCT.1D, which created the legacy meeting). `write_normal_meeting_audience_scope()`
    is retained in `studies/services.py` for the manual-form path lineage but is
    no longer called by generation.
  - **Boundary (unchanged by this slice):** higher-level / joint generation UI
    remains BS-STRUCT.1G; manage-list filters still expose `small_group`; the
    series legacy scope fallback still exists; the **zero-row fallback is not
    removed** (still required until production rollout and the final
    fallback-removal slice); `small_group` remains a compatibility mirror, not
    retired; V1 `BibleStudySession` is unchanged.
  - Tests: new BS-STRUCT.1L methods in `studies/tests.py`
    (`BibleStudyModuleTests`); three BS-STRUCT.1D "creates legacy meeting"
    tests were updated to assert skip-with-warning.
- **BS-STRUCT.1M** — normal generation **requires series structure audience
  rows** (fail closed). ✅ **implemented.** Code/tests/docs only; no
  model/schema/migration change.
  - **Resolver change.** `resolve_normal_generation_targets(series)`
    (`studies/services.py`) no longer falls back to legacy
    `get_eligible_small_groups()` / `scope_type` / `district` / `small_group`
    when the series has zero `BibleStudySeriesAudienceScope` rows. It now returns
    `([], [GenerationWarning(GENERATION_WARNING_MISSING_SERIES_AUDIENCE)])` — no
    targets, no legacy-only meeting, no zero-row meeting, no hidden fallback. The
    structure-audience path (descendant-or-self active `UNIT_SMALL_GROUP`
    expansion, dedup by unit id, single-active-group mirror, ambiguous-mirror
    warning, per-unit `generation_key` + `anchor_unit` + one audience row) is
    unchanged from BS-STRUCT.1L.
  - **New warning kind.** `GENERATION_WARNING_MISSING_SERIES_AUDIENCE`
    (`"missing_series_audience"`). The existing unmapped/ambiguous warning
    display in `generate_bible_study_meetings()` is retained; a new bilingual
    "this schedule has no structure audience scope — no meetings generated;
    configure the schedule audience scope first" warning is added on POST, and
    `get_bible_study_meeting_generation_preview()` exposes a
    `missing_series_audience` flag so the GET preview surfaces the same notice
    (`templates/studies/bible_study_meeting_generation.html`).
  - **Tests.** Pre-existing legacy-scope generation tests
    (`global` / `district` / `ministry_context` / `small_group` scope,
    idempotency, audience-row writers, runtime-visibility) were rewritten to
    drive generation via `BibleStudySeriesAudienceScope` rows
    (root / district / ministry-context / small-group units) instead of legacy
    scope fields. The three BS-STRUCT.1L legacy-fallback skip-with-warning tests
    (unmapped / inactive-unit / wrong-type legacy group) were **removed** as
    unreachable from generation. New tests assert a zero-audience-row series
    creates 0 meetings and shows the missing-series-audience warning (EN + ZH),
    and that an inactive audience unit yields 0 meetings without the
    missing-audience warning. The model-level `get_eligible_small_groups_*` tests
    remain as legacy model-method coverage.
  - **Boundary (as of this slice):** the zero-row meeting fallback was still
    present in BS-STRUCT.1M, but BS-STRUCT.2A later retired it for ordinary
    users; zero-row V2 meetings now fail closed.
    `small_group` is not removed or renamed; `BibleStudySeries` legacy fields are
    not removed (compatibility / display / coexistence only); manage-list filters
    still expose `small_group`; higher-level / joint generation UI remains
    BS-STRUCT.1G; V1 `BibleStudySession` is unchanged. Full legacy retirement is
    **not** claimed.
- **BS-STRUCT.1N** — staff meeting manage-list filter becomes
  **structure-audience aware**. ✅ **implemented.** Code/tests/docs only; no
  model/schema/migration change.
  - **Filter change.** `bible_study_meeting_manage_list()` (`studies/views.py`)
    reads GET `unit` (a `ChurchStructureUnit` id) instead of `small_group`.
    It filters meetings whose audience rows target the selected unit or a
    descendant (`_collect_descendant_or_self_unit_ids`), de-duplicated with
    `.distinct()`. Since BS-STRUCT.2A, zero-row meetings no longer match through
    `small_group`. An invalid / unknown / non-numeric `unit` fails safe (no
    filter, select shows "All").
  - **Legacy URL tolerance.** A legacy `?small_group=<id>` query with no `unit`
    is mapped internally (in-view, not an HTTP redirect) to that group's
    `church_structure_unit` (`get_small_group_structure_unit`) within the same
    request so old bookmarks keep working; the UI no longer renders a legacy
    small-group `<select>`.
  - **Options / template.** The view passes `unit_options` (active non-root
    units) and the template renders a bilingual "Audience Unit / 适用单位" select
    using a new `study_unit_path` filter (`ChurchStructureUnit.path_label`).
    Status and lesson filters are unchanged.
  - **Tests.** New `BibleStudyModuleTests` cases: filter by small-group unit;
    district unit includes descendant; wrong-branch unit excludes; legacy
    `small_group` param maps to unit; invalid unit fails safe; template uses
    `unit` not `small_group`; status + unit filters combine. BS-STRUCT.2A later
    flipped the zero-row manage-list assertions so zero-row meetings no longer
    match through `small_group`.
  - **Boundary:** `small_group` is not removed or renamed; no V1
    `BibleStudySession` change; no schema / migration change.
- **BS-STRUCT.1O** — manual Bible Study meeting create/edit form becomes
  **structure-unit-native**. ✅ **implemented.** Code/tests/docs only; no
  model/schema/migration change.
  - **Form change.** `BibleStudyMeetingForm` (`studies/forms.py`) drops the
    visible legacy `small_group` field and adds `audience_unit`, a single-select
    `ChurchStructureUnitChoiceField` whose queryset is active `UNIT_SMALL_GROUP`
    units, path-labelled (`Audience Unit` / `适用单位`). Because the picker only
    offers valid active small-group units, the old unmapped / inactive /
    wrong-type validation is unnecessary. On edit the initial unit resolves:
    single `UNIT_SMALL_GROUP` audience row → active `UNIT_SMALL_GROUP`
    `anchor_unit` → unit mapped from existing `small_group` → blank.
  - **Service change.** New `sync_normal_meeting_audience_scope_for_unit(meeting,
    unit)` (`studies/services.py`) creates/gets the single audience row for the
    selected unit, deletes stale rows (caller-validated normal single-unit), sets
    `anchor_unit`, sets `meeting_kind = normal`, sets the per-unit
    `generation_key` (`normal-unit:{unit_id}`, shared with generation), and sets
    the legacy `small_group` mirror only when exactly one active legacy group maps
    to the unit (`None` for a no-mirror or ambiguous mapping). The view path
    (`create_bible_study_meeting` / `edit_bible_study_meeting`) now calls this
    helper with `form.cleaned_data["audience_unit"]`.
  - **Duplicate prevention.** `clean()` rejects a second meeting for the same
    `(lesson, unit)` before save, matching either an existing `generation_key` or
    a meeting whose audience rows are exactly that single unit — so the
    structure-native identity never raises an `IntegrityError`. **BS-STRUCT.1O-FU1:**
    duplicate prevention also treats an existing legacy **zero-row** mirror meeting
    for the selected unit as a duplicate — when exactly one active legacy group
    maps to the unit (`resolve_unit_small_group_mirror`), any other meeting for the
    lesson with that `small_group` is caught, so an old zero-row meeting no longer
    slips through to the `(lesson, small_group)` constraint. This guard stays until
    the zero-row fallback is retired.
  - **Fail-safe (carried over).** The form still refuses to edit a higher-level /
    joint / multi-unit meeting (`meeting_kind != normal`, or audience rows that
    are not a single small-group row), leaving those rows untouched.
  - **Template.** `templates/studies/bible_study_meeting_form.html` is
    field-agnostic (iterates `form`), so removing `small_group` and adding
    `audience_unit` flows through with no template edit; the staff UI no longer
    renders a legacy small-group select.
  - **Tests.** Updated/added `BibleStudyModuleTests` cases: form exposes
    `audience_unit` not `small_group` and the picker only offers small-group
    units; bilingual label; the create page renders no `name="small_group"`;
    manual create writes row + anchor + normal kind; mirror set when one active
    legacy group maps; `small_group=None` for a no-mirror unit; create/edit
    duplicate `(lesson, unit)` rejected; edit changes unit and replaces the stale
    row + anchor + mirror; multi-unit and higher-level edits rejected with rows
    untouched. The three obsolete BS-STRUCT.1H unmapped / inactive-unit /
    wrong-type legacy-group validation tests were **removed** as unreachable —
    the `audience_unit` picker can no longer select such a unit.
  - **Boundary (as of this slice):** the zero-row fallback was still present in
    BS-STRUCT.1O, but BS-STRUCT.2A later retired it for ordinary users;
    `small_group` is not removed or renamed (kept as a mirror written
    by this form); the small-group-keyed
    `sync_normal_meeting_audience_scope(meeting)` helper is retained for
    compatibility (later removed in BS-STRUCT.1P); no higher-level / joint write
    UI is added; no V1 `BibleStudySession` change; no schema / migration change.
- **BS-STRUCT.1P** — remove obsolete small-group-keyed Bible Study
  write/generation helpers. ✅ **implemented.** Code/tests/docs only; no
  model/schema/migration change.
  - **Removed `write_normal_meeting_audience_scope(meeting)`** (`studies/services.py`)
    — the BS-STRUCT.1D generation-side small-group-keyed writer. Generation is
    structure-unit-native since BS-STRUCT.1L (`create_normal_meeting_for_target`
    writes the row/anchor/key directly), so this had no caller in code, tests, or
    management commands.
  - **Removed `sync_normal_meeting_audience_scope(meeting)`** (`studies/services.py`)
    — the BS-STRUCT.1H manual-form small-group-keyed writer, already superseded by
    `sync_normal_meeting_audience_scope_for_unit(meeting, unit)` in BS-STRUCT.1O
    and kept only "for compatibility" with no remaining caller. Removing it stops
    future work from re-entering a legacy `small_group` write path.
  - **Removed `GENERATION_WARNING_UNMAPPED_GROUP`** (`studies/services.py`) and its
    **unreachable view warning branch** (`studies/views.py`). Since BS-STRUCT.1L/1M
    generation no longer resolves legacy `SmallGroup` rows, `resolve_normal_generation_targets`
    can only emit `GENERATION_WARNING_AMBIGUOUS_MIRROR` /
    `GENERATION_WARNING_MISSING_SERIES_AUDIENCE`, so the unmapped-group warning was
    dead code. The `GENERATION_WARNING_UNMAPPED_GROUP` import was dropped from the
    view.
  - **Kept `resolve_normal_small_group_unit(small_group)`** (`studies/services.py`),
    reason: still used by `BibleStudyMeetingForm._initial_audience_unit_id` (edit
    initial resolution priority 3 — map an existing legacy `small_group` to its
    unit). Docstring updated to record it is the sole caller and not a write path.
    The `studies/forms.py` import is unchanged.
  - **No test changes.** No test imported or asserted the removed helpers /
    constant; the targeted generation / manual-form / zero-row-fallback tests
    (including `test_meeting_role_form_zero_row_meeting_falls_back_to_small_group`)
    pass unchanged.
  - **Boundary (as of this slice):** the zero-row runtime fallback was still
    present in BS-STRUCT.1P, but BS-STRUCT.2A later retired it for ordinary
    users. `BibleStudyMeeting.small_group` is **not** removed or renamed and
    remains a compatibility mirror / display / history / backfill /
    idempotency field;
    `get_small_group_structure_unit` and the membership-core fallback helpers are
    untouched; no V1 `BibleStudySession` change; no schema / migration change; no
    production command run.
- **BS-STRUCT.2A** — retire the V2 zero-row `small_group` runtime fallback for
  ordinary users. ✅ **implemented.** V2 meetings with audience rows remain
  visible through membership-core audience-row matching; V2 meetings with zero
  `BibleStudyMeetingAudienceScope` rows fail closed for ordinary users; manager /
  staff override is unchanged. Landing/Today no longer includes zero-row meetings
  through legacy `small_group`; role/worship candidate filtering returns no
  ordinary candidates for zero-row meetings; the manage-list unit filter matches
  audience rows only while still tolerating legacy `?small_group=<id>` URLs as a
  mapping to `unit`. `BibleStudyMeeting.small_group` remains mirror/display/
  backfill/history/idempotency compatibility only. V1 `BibleStudySession` app
  runtime was later retired in BS-V1-RETIRE.1A and remains a data cleanup target.
  No schema field/model was deleted and no migration was created. Readiness reported 29
  meetings checked, 29 with audience rows, zero zero-row blockers,
  `db_data_blockers_clear = true`, `legacy_small_group_fallback_still_present =
  false`, and `runtime_zero_row_fallback_removed = true`.
- **BS-STRUCT.2+ future work** — field-level cleanup / retirement of the legacy
  Bible Study `SmallGroup` bridge only after remaining compatibility consumers
  are resolved (coordinate with CS-CORE Section 12 legacy retirement). This does
  **not** mean V1 `BibleStudySession` should be migrated to membership-core; V1
  remains retired app runtime and a later pilot-data purge target.

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
8. **Legacy V1 `BibleStudySession`.** Retired from app-level runtime by
   BS-V1-RETIRE.1A. V1 is still not migrated into the new audience model and
   should not be coupled to `BibleStudyMeetingAudienceScope` or membership-core.
   Remaining V1 rows are pilot/archive data pending an explicit guarded purge.
   Future work is purge/data cleanup, not V1 visibility migration.
9. **Group-specific guide customization.** Already exists (`group_direction` /
   `group_questions`); confirm whether the real workflow needs anything beyond
   these two fields before treating prep as "done for migration."
10. **Series-vs-meeting audience relationship.** Should a meeting's audience be
    constrained to a subset of its series' audience, or independent? Affects
    generation and validation.

---

## 8. Verification (historical BS-STRUCT.1A docs-only slice)

```powershell
cd E:\bible-reading\bible_reading_v2-claude
git diff --check
git status --short
```

For the original BS-STRUCT.1A docs-only design/audit slice, there were no code,
template, test, model, or migration changes, so no makemigrations/check runs
were required at that time. This section is historical verification for that
slice only; this living plan now records later implemented runtime slices such
as BS-STRUCT.1B/1E/1G/2A and BS-V1-RETIRE.1A.
