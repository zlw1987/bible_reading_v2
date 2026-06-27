# Member Record, Faith Statement, Delegated Unit Management, and Configurable Serving Readiness Plan

Status: `MEMBER-RECORD.1A` docs-only design. No models, migrations, forms,
views, templates, permissions, management commands, tests, or data changes are
made in this slice. This document records an approved next product direction so
it can be reviewed before any implementation slice is approved.

This plan sits downstream of
[Structure Unit Coworker Role Architecture Plan](STRUCTURE_UNIT_COWORKER_ROLE_ARCHITECTURE_PLAN.md)
(`UNIT-COWORKER.1A`–`1E`), which already shipped the coworker role-type /
profile / requirement / assignment foundation and Bible Study candidate
filtering. This plan adds four related but separable concerns:

- A. Delegated unit management ("My Units") so leads can maintain coworker
  structure without admin-only Church Structure setup.
- B. A global church member record separate from self-editable profile data.
- C. A unit-specific member/care record separate from the global record.
- D. A configurable serving-readiness policy and evaluator, plus
- E. shared use of that evaluator across coworker, ministry, weekly-serving, and
  Bible Study assignment surfaces.

## 0. Migration-Safety Preconditions (must stay true)

This plan must not weaken the completed Church Structure migration. Every later
slice derived from this document must keep all of the following true:

- Do not reintroduce `Profile.small_group`, `SmallGroup`, `District`,
  `MinistryContext`, legacy scope fields, or legacy bridge runtime authority.
- `ChurchStructureUnit` and `ChurchStructureMembership` stay the canonical
  structure and belonging models.
- Belonging is not serving. Membership/visibility must not imply
  `TeamAssignment`, `TeamAssignmentMember`, My Serving, staff capability, role
  grants, or ministry serving assignment.
- Delegated management permission, member-record edit permission, and serving
  readiness must never be inferred from `ChurchStructureMembership` or from
  audience visibility.
- Nothing here hard-blocks an existing assignment surface in V1. Readiness is
  warning-only.

## 1. Product Problem

Two operational gaps motivate this plan.

1. Coworker structure is currently editable only through admin-oriented Church
   Structure setup/detail (`/staff/structure/`). In real operation, small-group
   coworkers are maintained by group leaders and district leaders, not only by
   central admins. There is no delegated operational surface for a lead to
   maintain coworkers for the units they are responsible for.

2. Churches keep member/pastoral records (the SVCA Google Sheet is the concrete
   example) covering membership class, Faith Statement, baptism, contact info,
   group serving, church serving, and care notes. Today the app has no
   structured place for these, no privacy-scoped access, and no way to express
   "is this person ready to serve" without hard-coding one church's rule.

These are distinct from "who belongs to this unit" (`ChurchStructureMembership`)
and "who is serving this week" (`TeamAssignmentMember` / `BibleStudyMeetingRole`).

## 2. Terminology

- Profile: lightweight, self-editable user settings (`Profile`,
  currently `preferred_language` / `must_change_password`).
- Member record (global): church-wide person facts (membership class, Faith
  Statement, baptism). One row per linked user.
- Unit member record (local): unit-scoped operational/care data (attendance
  state, joined-group date, care notes) for one user in one unit.
- Coworker role assignment: `ChurchStructureUnitRoleAssignment`, an explicit
  long-term coworker role (`lead`, `assistant_lead`, `caring`, `edify`,
  `outreach`, `worship`, or custom) linking a unit, role type, and user.
- Lead: an active `ChurchStructureUnitRoleAssignment` whose `role_type.code`
  is `lead`. Used as the delegated-management permission source.
- Serving readiness: a computed, policy-driven evaluation of whether a person
  meets a church's configured conditions to serve. Warning-only in V1.
- Serving readiness policy: configurable church rule defining which member-record
  facts (and statuses) are required for readiness.

---

# A. Delegated Unit Management / "My Units"

## A.1 Goal

Add a business/operational entrance, e.g. `/my-units/` ("My Units" /
"我负责的单位"), separate from the admin/setup-oriented `/staff/structure/`. A
lead of a unit should be able to manage coworker structure for that unit and all
descendant units, at every level (church lead, ministry/context lead, district
lead, small-group lead, department lead, etc.).

`/staff/structure/` stays the admin surface for the structure tree itself
(create/rename/reorder/enable/disable units). `/my-units/` is the operational
surface for coworker-role maintenance and readiness review within units a person
already leads. It must not become a second tree editor.

## A.2 Permission Model (recommended)

Permission to manage a unit's coworkers comes from **explicit active lead role
assignment on an ancestor-or-self unit**, plus existing admin capability. It is
never inferred from membership, audience visibility, `TeamAssignment`,
`TeamAssignmentMember`, or Bible Study visibility.

Recommended helper:

```
can_manage_unit_coworkers(user, unit) -> bool
```

Returns `True` when any of:

1. `user.is_staff` or `user.is_superuser`.
2. The user holds an explicit structure-admin capability (recommended new
   capability `manage_structure_coworkers`, see A.3) — global manage of all
   units' coworker roles.
3. The user has an **active** `ChurchStructureUnitRoleAssignment` with
   `role_type.code == "lead"` on `unit` itself **or any ancestor** of `unit`
   (ancestor-or-self), where "active" means `is_active` and
   `active_for_date(today)` (start reached, not ended).

Membership alone never grants management. Coworker (non-lead) assignment alone
never grants management in V1.

Ancestor-or-self is resolved from the canonical hierarchy
`ChurchStructureUnit.parent`. The unit model already exposes `get_ancestors()`
(ancestors excluding self); "ancestor-or-self" = `get_ancestors() + [self]`. A
lead high in the tree (e.g. church or district lead) therefore manages all
descendant units; a small-group lead manages only their own group's subtree.

### Manageable-units query

For listing on `/my-units/`, the recommended resolution is:

- Collect units where the user has an active `lead` assignment (the "lead
  units").
- The manageable set is each lead unit plus all of its active descendants
  (descend via `children`).
- De-duplicate when lead assignments overlap subtrees.
- Staff / structure-coworker-admins effectively see all active units.

Open decision: compute descendants on demand (simple recursive walk; fine for
current tree sizes) versus maintaining a materialized closure table for scale.
Recommended V1: on-demand recursive walk, because the tree is small and this
avoids new denormalized state. Revisit only if performance requires it.

## A.3 Why a new capability, not reuse (architecture note)

Do **not** reuse `CAP_MANAGE_CHURCH_MEMBERSHIPS` or
`accounts.change_churchstructureunit` as the delegated-management gate.

- `change_churchstructureunit` is tree-structure editing (admin), broader than
  "manage coworkers for my subtree" and not delegable per-unit.
- `CAP_MANAGE_CHURCH_MEMBERSHIPS` is belonging approval, a different concept;
  conflating it would let membership approvers edit coworker roles and vice
  versa.

Recommended: add a narrow capability `CAP_MANAGE_STRUCTURE_COWORKERS`
("manage_structure_coworkers") for explicit central structure-coworker admins,
wired into the existing `has_capability` / `ROLE_CAPABILITIES` system. The
per-unit lead path (A.2 rule 3) is separate from and additional to this global
capability. This keeps the capability catalog honest: belonging, tree editing,
and coworker management are three different powers.

## A.4 Scope discipline for V1 delegated management

Default V1 delegated management is limited to **coworker-role management and
readiness review** for managed units. It must not become broad staff
permission. Specifically, leads using `/my-units/` must not, via this surface,
gain:

- membership approval / rejection,
- `ChurchRoleAssignment` (capability) granting,
- `TeamAssignment` / `TeamAssignmentMember` / My Serving editing,
- `BibleStudyMeetingRole` confirmation authority,
- structure tree create/rename/reorder/enable/disable,
- global member-record (Section B) editing, unless a later privacy/permission
  slice explicitly approves it.

Member-record management (Sections B/C) is intentionally gated behind a later,
separately approved privacy review — it is **not** unlocked by `lead` status in
the first delegated-management slices.

## A.5 Suggested phases

- `UNIT-LEAD-MANAGE.1A` — docs-only delegated-management design (this section).
- `UNIT-LEAD-MANAGE.1B` — **implemented (read-only).** The `/my-units/`
  ("My Units" / 我负责的单位) entry lists managed units + current coworker roster
  grouped by role type + missing-required-role readiness, with no edits. The
  helpers `can_manage_unit_coworkers` / `get_manageable_structure_units`
  (`accounts/unit_management.py`) derive management from staff/superuser status
  or an active `lead` ancestor-or-self assignment only; the central
  `CAP_MANAGE_STRUCTURE_COWORKERS` capability (A.3) is still deferred and was
  not added in this slice. A guarded global nav link (`should_show_my_units_nav`)
  shows only to staff and active leads. No models, migrations, forms, or data
  changes; no member-record/readiness models were introduced.
- `UNIT-LEAD-MANAGE.1C` — **implemented.** Delegated coworker management for
  authorized leads. A per-unit operational page (`my_unit_detail`,
  `GET /my-units/<id>/`) plus POST actions `add_my_unit_coworker_assignment`
  (`/my-units/<id>/coworkers/add/`) and `end_my_unit_coworker_assignment`
  (`/my-units/coworkers/<id>/end/`) let authorized users add / end coworker
  `ChurchStructureUnitRoleAssignment` rows within managed units. Every action is
  gated by `can_manage_unit_coworkers` (active `lead` ancestor-or-self, staff, or
  superuser); non-manageable or inactive units return 404. It reuses the
  `UNIT-COWORKER.1C/1D` `StructureUnitCoworkerAssignmentForm` and
  `coworker_assignment_local_user_queryset`; non-staff leads are pinned to local
  candidates (active primary membership on the unit or immediate parent) with no
  "all active users" fallback, while staff/superuser may still widen the picker
  via `?coworker_user_scope=all`. Ending sets `is_active=False` + `end_date`
  (rows are retained, never deleted). No membership, capability,
  `TeamAssignment`, `TeamAssignmentMember`, `ChurchRoleAssignment`, or
  `BibleStudyMeetingRole` rows are created; the delegated page exposes no
  `/staff/structure/` links. The central `CAP_MANAGE_STRUCTURE_COWORKERS`
  capability (A.3) remains deferred. No new models, migrations, or data changes.
- Later (separate approval) — unit member-record management, only after the
  privacy/permission review in Sections B–C.

## A.6 Boundaries

- No permission from membership, audience, `TeamAssignment`,
  `TeamAssignmentMember`, or Bible Study visibility.
- `/my-units/` does not edit the structure tree.
- Delegated coworker edits create only `ChurchStructureUnitRoleAssignment`
  rows; they never create membership, capabilities, serving, or meeting roles.

> If the reviewer prefers a different permission spine (e.g. a dedicated
> per-unit "manager" grant table instead of deriving management from the `lead`
> coworker role), that is a legitimate alternative — see Open Alternatives,
> Section H. Recommended design derives management from the existing `lead`
> coworker role to avoid a parallel permission model.

---

# B. Global Member Record vs Self-Editable Profile

## B.1 Split rationale

Keep `Profile` lightweight and self-editable. Do not pour pastoral/member-
management fields into `Profile`. Separate three concerns:

1. Self-editable profile/contact data (user-owned).
2. Global church member facts (admin/pastoral-owned, church-wide).
3. Unit-specific operational/care data (Section C, unit-scoped).

### Self-editable profile/contact fields (user-owned)

Candidate fields a user may edit about themselves:

- preferred name / English name
- phone / mobile
- birthday month + day (no year required)
- basic contact preferences

Open decision: whether these live as new fields on `Profile` or in a small
`MemberContactInfo` companion. Recommended: extend `Profile` for the few simple
self-editable fields (it is already the per-user settings row), and keep
pastoral facts out of it. Birthday is mildly sensitive; store month/day and gate
its visibility (see privacy, Section C.3).

## B.2 `ChurchMemberRecord` (global, recommended)

Recommended model: `ChurchMemberRecord`, **one-to-one with `User`** (mirroring
`Profile`'s `OneToOneField` to `AUTH_USER_MODEL`). It records church-wide facts,
not unit-specific status. It is admin/pastoral-owned, not self-edited by default.

> Naming note: `ChurchMemberRecord` is clear and consistent with existing
> `Church*` naming. Open alternatives: `MemberFaithRecord` (narrower, faith/
> membership only) or `ChurchMembershipFile`. Avoid `MemberProfile` (collides
> conceptually with `Profile`). Recommended: `ChurchMemberRecord`.

Proposed fields (concepts only):

- `user` — OneToOne to `AUTH_USER_MODEL`.
- `membership_class_status` — C201 / "认识我们的教会" progress (B.3).
- `faith_statement_status` — Faith Statement / 信仰宣言 status (B.4).
  **Not `faith_status`.** This field is specifically about the Faith Statement,
  not a generic spiritual-state label.
- `faith_statement_signed_date` — nullable date.
- `baptism_status` — baptism state (B.5).
- `baptism_date` — nullable date.
- `formal_member_status` — optional explicit membership status if needed beyond
  the derived combination (open decision, B.6).
- `notes` — membership/admin notes; non-counseling, non-medical, non-financial,
  privacy-scoped (mirror the cautionary `help_text` already used on
  `ChurchStructureUnitRoleAssignment.notes`).
- `recorded_by`, `updated_by` — FKs to the editing user (audit).
- `created_at`, `updated_at` — timestamps.

### Important correction captured

Do **not** name the field `faith_status`. Use `faith_statement_status`. It is
specifically the Faith Statement / 信仰宣言 acceptance-and-signature state, not a
generic faith status, and conflating the two would invite mislabeling someone's
spiritual standing.

## B.3 Membership class / C201 status (separate field)

Recommended values:

- `unknown`
- `not_started`
- `in_progress`
- `completed`
- `waived`

Kept separate from Faith Statement status: completing the class is a different
fact from signing the statement.

## B.4 Faith Statement status (not a boolean)

The SVCA process: a person attends "认识我们的教会" / C201 (or equivalent
membership class); if they accept the church's faith statement they sign a Faith
Statement / 信仰宣言; signing is what theoretically makes them a formal member;
if also baptized they are eligible to begin formal serving. Eligibility is a
warning, never a hard block in V1.

Recommended V1 values:

- `unknown`
- `not_started`
- `class_completed_pending_signature`
- `sent_pending_signature`
- `signed`
- `waived`
- `declined`
- `not_required`

Notes / open alternatives:

- `class_completed_pending_signature` and `sent_pending_signature` are two
  flavors of "pending." If staff find the distinction noisy, collapse to a
  single `pending_signature` and rely on `membership_class_status` for the
  class fact. Recommended: keep both initially (they map to real SVCA states),
  revisit after pilot use.
- `signed` is the readiness-satisfying value; `waived` / `not_required` also
  satisfy readiness for churches that configure it so (Section D).
- `declined` is a real, non-shaming operational state (chose not to sign).

## B.5 Baptism status (separate field)

Recommended values:

- `unknown`
- `not_baptized`
- `baptized`
- `recognized` (baptism elsewhere recognized by this church)
- `waived`
- `not_required`

## B.6 Formal member status (open decision)

Two options:

1. Derive formal-member from `faith_statement_status == signed` (the SVCA
   theory) and surface it as computed, not stored.
2. Store an explicit `formal_member_status` for churches whose membership roll
   is maintained independently of the signature event.

Recommended: derive by default and only add a stored `formal_member_status` if a
church needs an authoritative roll independent of the signature. Do not let
either become a serving hard-block (that is the readiness policy's job, D).

---

# C. Unit-Specific Member / Care Record

## C.1 `ChurchStructureUnitMemberRecord` (recommended)

A separate unit-scoped record attaches a user to a unit and stores unit-local
operational/care data. Recommended name `ChurchStructureUnitMemberRecord`
(consistent with `ChurchStructureUnit*` naming). Open alternative:
`UnitMemberCareRecord`.

Proposed fields (concepts only):

- `unit` — FK to `ChurchStructureUnit`.
- `user` — FK to `AUTH_USER_MODEL` (unique together with `unit`).
- `attendance_state` — e.g. `active`, `unstable_attendee`, `inactive`,
  `no_longer_comes`, `graduated`, `moved`, `visitor`.
- `joined_group_date` — nullable.
- `group_notes` — unit-local small-group notes (privacy-scoped).
- `care_followup_notes` — care / follow-up notes (stricter visibility).
- `local_display_order` / grouping hints — optional.
- `updated_by`, `updated_at` — audit.

This is deliberately separate from `ChurchMemberRecord` (B): global church facts
(baptism, Faith Statement) must not be duplicated per unit, and unit-local care
state must not leak as church-wide truth.

## C.2 Relationship to belonging

`ChurchStructureUnitMemberRecord` is operational/care data, not belonging
authority and not serving. It does **not** replace or imply
`ChurchStructureMembership`, and it must not be used to compute audience
visibility or any serving assignment. A unit member record may exist for people
whose belonging is recorded elsewhere; the canonical belonging source remains
`ChurchStructureMembership`.

## C.3 Privacy warning (must shape any later slice)

The SVCA Google Sheet contains sensitive data: birthday, mobile, email,
baptism/church history, Faith Statement / training status, group serving, church
serving, and comments/care notes. The future system **must not** expose all of
this to ordinary members by default. Any implementation slice must:

- define scoped access rules (who can read which field set: self vs unit lead vs
  district lead vs central admin),
- treat care/follow-up notes and comments as the most restricted tier,
- audit updates (`updated_by` / `updated_at`, and consider an append-only audit
  log for sensitive fields),
- avoid surfacing internal model names, DB IDs, or "source-of-truth" language to
  ordinary users (consistent with the repo UI/copy rules).

Member-record management is therefore explicitly **deferred** behind a dedicated
privacy/permission review and is not unlocked by the early delegated-management
slices (A.5).

---

# D. Configurable Serving Readiness / Eligibility Policy

## D.1 Architecture rule: separate facts, policy, and result

Do **not** hard-code SVCA's formal serving rule into the user/profile/member
model, and do **not** store a single `eligible_for_formal_serving` boolean.
Separate three layers:

1. **Member facts** — `ChurchMemberRecord` (B): the church-wide truth about a
   person (membership class, Faith Statement, baptism).
2. **Serving readiness policy** — configurable church rule: which facts (and
   which statuses) are required, and at what severity.
3. **Evaluated readiness result** — computed on demand by an evaluator; never a
   stored boolean.

SVCA's default policy: Faith Statement `signed`/`waived` **plus** baptism
`baptized`/`recognized` → ready. But other churches differ (baptism only,
membership class only, plus background check / training, etc.), so the rule must
be data-driven, not code-hard-coded.

## D.2 `ServingReadinessPolicy` (recommended)

> Naming note: the prompt proposed `ServingEligibilityPolicy` /
> `ServingEligibilityRequirement`. Recommended: align names with the evaluator
> verb and use `ServingReadinessPolicy` / `ServingReadinessRequirement` so the
> model, helper (`get_serving_readiness`), and result vocabulary all say
> "readiness." Open alternative: keep "Eligibility" naming if preferred for
> staff-facing wording. Either is acceptable; pick one and use it consistently.

`ServingReadinessPolicy` proposed fields:

- `code` — stable identifier (e.g. `svca_default`).
- `name_en` / `name_zh` — bilingual label.
- `description`.
- `is_default` — exactly one default policy when no context-specific policy
  applies.
- `is_active`.
- optional `applies_to` context — reserved for future per-ministry or
  per-unit-type policy selection; V1 may have only one default policy.

## D.3 `ServingReadinessRequirement` (recommended)

Proposed fields:

- `policy` — FK to `ServingReadinessPolicy`.
- `requirement_type` — what fact is checked (D.4).
- `accepted_statuses` — the member-record statuses that satisfy this
  requirement (e.g. for `faith_statement`: `signed`, `waived`, `not_required`).
  Stored as a structured list validated against the relevant member-record
  field's choices.
- `severity` — `required` (counts as missing/blocking-readiness when unmet) vs
  `recommended` (informational warning only). V1 keeps even `required` as
  warning-only at assignment surfaces (D.6).
- `label` — bilingual operational label for the warning.
- `sort_order`.
- `is_active`.

### D.4 Requirement types

V1:

- `membership_class` → checks `ChurchMemberRecord.membership_class_status`.
- `faith_statement` → checks `ChurchMemberRecord.faith_statement_status`.
- `baptism` → checks `ChurchMemberRecord.baptism_status`.

Future (do not build in V1):

- `background_check`, `training`, `child_safety_training`, `age`,
  `manual_review`, `custom`.

Each `requirement_type` maps to a member-record field (or a future fact source).
`accepted_statuses` is validated against that field's choice set. Future types
like `age` or `background_check` need their own fact source before they can be
evaluated.

## D.5 Evaluator (recommended helper)

Do not store readiness. Compute it:

```
get_serving_readiness(user, context=None) -> ServingReadinessResult
# or, when a specific policy is supplied:
evaluate_serving_readiness(user, policy, context=None) -> ServingReadinessResult
```

`get_serving_readiness` resolves the applicable policy (context-specific if
configured, else the default active policy) and delegates to
`evaluate_serving_readiness`. The result is a structured object, not a bool:

- `is_ready` — all `required` requirements satisfied.
- `status` — summary label (e.g. `ready`, `pending`, `unknown`,
  `no_policy`, `no_record`).
- `warnings` — operational, non-shaming messages.
- `missing_requirements` — unmet requirements (type + accepted statuses +
  current status).
- `passed_requirements` — satisfied requirements.
- `policy_used` — which policy produced the result.

Edge cases the evaluator must handle gracefully (all non-blocking):

- No `ChurchMemberRecord` for the user → `status = no_record`, treat unmet facts
  as warnings, never an error.
- No active policy / no default → `status = no_policy`, `is_ready = True` or a
  neutral non-blocking value (open decision; recommended: treat as "no policy
  configured, no warnings" so unconfigured churches are not spammed).
- Inactive user → may short-circuit to a neutral result.

The evaluator is **read-only**. It must never write member records, create
assignments, or read `ChurchStructureMembership` to infer facts.

## D.6 Warning-only in V1 (hard requirement)

The readiness result must be warning-only in V1. It must **not** hard-block:

- `ChurchStructureUnitRoleAssignment`
- ministry `TeamMembership`
- `TeamAssignmentMember`
- `BibleStudyMeetingRole`

Assignment surfaces show an operational warning ("readiness incomplete: Faith
Statement pending") and still allow the save. Hard-gating is a separately
approved future policy decision per church, not a V1 default.

---

# E. Shared Use Across Serving Surfaces

Formal serving readiness must be usable outside small-group coworker management.
The same evaluator (`get_serving_readiness`) should be callable from:

- structure unit coworker assignment (`ChurchStructureUnitRoleAssignment`),
- ministry team membership (`TeamMembership`),
- weekly team assignments / My Serving (`TeamAssignmentMember`),
- Bible Study meeting roles (`BibleStudyMeetingRole`).

V1 behavior is warning-only everywhere. Examples:

- Assigning a small-group `lead` / `edify` / `worship` coworker warns if
  readiness is missing.
- Adding someone to an Audio / Lighting / Usher / Website ministry team warns if
  readiness is missing.
- Adding someone to a weekly `TeamAssignmentMember` warns if readiness is
  missing.
- Adding someone to a `BibleStudyMeetingRole` warns if readiness is missing.

Warnings are operational and non-shaming, shown only to staff/leads performing
the assignment — never published to ordinary members.

Boundary: calling the readiness evaluator from these surfaces does not couple the
concepts. Readiness is an advisory read; it does not create belonging, does not
grant capability, and serving remains separate from belonging.

---

# F. Google Sheet Fields (product evidence only)

The existing SVCA Google Sheet contains fields like: Name, English Name, Gender,
birthday, mobile, 来SVCA时间 (date joined SVCA), 受洗时间 (baptism date), email,
小组内服事 (in-group serving), 教会服事 (church serving), Faith Statement, C301,
C201, 小组同工培训 (small-group coworker training), Comment, plus sections for
unstable attendees, no-longer-come, and graduated.

Used here only as design evidence. **No import functionality is designed or
built in this slice.**

Mapping guidance / boundaries for later slices:

- 小组内服事 (in-group serving) should eventually be derived from
  `ChurchStructureUnitRoleAssignment`, not maintained as free text.
- 教会服事 (church serving) should eventually connect to Ministry /
  `TeamMembership` / `TeamAssignment` concepts, not small-group coworker roles.
- Faith Statement → `ChurchMemberRecord.faith_statement_status` (+ signed date).
- C201 → `ChurchMemberRecord.membership_class_status`. C301 / 小组同工培训 are
  candidate future `training` requirement sources (not V1).
- 受洗时间 → `ChurchMemberRecord.baptism_status` + `baptism_date`.
- birthday / mobile / email → self-editable profile/contact (B.1), privacy-scoped.
- unstable / no-longer-come / graduated → unit `attendance_state` (C.1).
- Comment / care notes → most restricted tier; stricter visibility and edit
  permission than self-profile fields (C.3).

---

# G. Concept Separation Summary (one table to keep honest)

| Concept | Source of truth | Grants management? | Implies serving? |
| --- | --- | --- | --- |
| Belonging | `ChurchStructureMembership` | No | No |
| Coworker role | `ChurchStructureUnitRoleAssignment` | `lead` → manage subtree coworkers only | No (advisory candidate only) |
| Delegated management | active `lead` ancestor-or-self + `manage_structure_coworkers` cap | — | No |
| Global member facts | `ChurchMemberRecord` | No | No (feeds readiness) |
| Unit care record | `ChurchStructureUnitMemberRecord` | No | No |
| Serving readiness | `ServingReadinessPolicy` + evaluator | No | No (advisory warning) |
| Serving (this week) | `TeamAssignmentMember` / `BibleStudyMeetingRole` | No | Yes (explicit) |
| Capability/role | `ChurchRoleAssignment` / `has_capability` | Yes (explicit) | No |

Nothing in the left column may be inferred from another row except the documented
`lead` → manage path. Membership never implies any other row.

---

# H. Open Alternatives and Architecture Review Notes

These are deliberate decision points for review before implementation.

1. **Delegated permission spine.** Recommended: derive management from the
   existing `lead` coworker role (no new per-unit grant table). Alternative: a
   dedicated `UnitManagerGrant` table assigning explicit managers per unit,
   decoupled from the `lead` coworker role. Trade-off: the recommended approach
   reuses existing data and matches how churches think ("the leader runs the
   group"); the alternative allows a non-lead administrator without making them a
   `lead` coworker. Recommended unless review wants manager ≠ lead.

2. **Readiness naming.** Recommended `ServingReadinessPolicy` /
   `ServingReadinessRequirement` / `get_serving_readiness` for vocabulary
   alignment. Alternative: the prompt's `ServingEligibilityPolicy` /
   `ServingEligibilityRequirement`. Pick one and use consistently.

3. **Member-record host.** Recommended `ChurchMemberRecord` OneToOne to `User`
   (parallel to `Profile`). Alternative: attach to `Profile`. Recommended split
   keeps `Profile` lightweight and self-editable while member facts are
   admin/pastoral-owned with different permissions.

4. **Faith Statement pending granularity.** Recommended: keep
   `class_completed_pending_signature` and `sent_pending_signature`. Alternative:
   collapse to one `pending_signature` and lean on `membership_class_status`.

5. **Formal member status.** Recommended: derive from Faith Statement signature;
   add stored `formal_member_status` only if a church needs an independent roll.

6. **Descendant resolution.** Recommended: on-demand recursive walk for V1.
   Alternative: closure table if scale demands it.

7. **No-policy readiness default.** Recommended: unconfigured churches get no
   warnings (neutral result), so the feature is opt-in per church.

If, on review, any recommended model name, boundary, or policy shape is judged
wrong, change it here in docs before any code slice — do not silently diverge in
implementation.

---

# I. Implementation Phasing (all later, each separately approved)

- `MEMBER-RECORD.1A` — this docs-only design (current slice).
- `UNIT-LEAD-MANAGE.1A/1B/1C` — delegated management (A.5).
- `MEMBER-RECORD.1B` — `ChurchMemberRecord` model + admin + self-editable
  profile/contact split, behind privacy review.
- `MEMBER-RECORD.1C` — `ChurchStructureUnitMemberRecord` + scoped access +
  audit, behind privacy review.
- `SERVING-READINESS.1A` — `ServingReadinessPolicy` /
  `ServingReadinessRequirement` models + default SVCA policy seed (dry-run/apply).
- `SERVING-READINESS.1B` — `get_serving_readiness` evaluator + structured result.
- `SERVING-READINESS.1C` — warning-only integration across coworker, ministry,
  weekly-serving, and Bible Study assignment surfaces (E).

# J. Non-Goals (this slice)

- No models, migrations, fixtures, forms, views, templates, URLs, permissions,
  management commands, tests, or data changes.
- No import of the Google Sheet.
- No hard-blocking of any assignment surface.
- No new runtime authority for `Profile.small_group` / `SmallGroup` / `District`
  / `MinistryContext` / legacy scope fields / legacy bridges.
- No inference of management, member facts, or readiness from
  `ChurchStructureMembership` or audience visibility.
- No coupling of belonging to serving.
