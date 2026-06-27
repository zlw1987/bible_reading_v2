# Structure Unit Coworker Role Architecture Plan

Status: UNIT-COWORKER.1A docs-only design complete. UNIT-COWORKER.1B adds the
narrow model/admin foundation, nullable explicit unit role profile selection,
globally scoped role types with globally unique codes, and a dry-run/apply
preset seed command. UNIT-COWORKER.1C adds the narrow staff-facing setup UI on
the existing Church Structure setup/detail surface: explicit unit role-profile
update, missing-required-role display, active/historical coworker assignment
review, add-active-assignment, end/deactivate-assignment, count-only map
readiness, and a seed-command discoverability note when defaults are missing.
UNIT-COWORKER.1D narrows the add-coworker user picker to active users whose
active primary `ChurchStructureMembership` is directly on the current unit or
its immediate parent, with a staff-controlled `coworker_user_scope=all`
fallback for special cross-unit cases. UNIT-COWORKER-BS-CANDIDATE.1E adds
Bible Study V2 meeting-role candidate filtering for discussion and worship
roles: active `edify` / `worship` coworkers on the meeting `anchor_unit` are
preferred, all active anchor-unit coworkers are the setup fallback, and the
existing audience-membership picker remains the fallback when no anchor unit or
no coworkers exist. Today, My Serving long-term role display, long-term coworker role confirmation,
runtime visibility, and permission inference remain unimplemented and require
separate approval.

The next product direction built on this foundation — delegated unit management
("My Units") driven by `lead` coworker assignments, a global member record,
unit-specific care records, and a configurable warning-only serving-readiness
policy/evaluator — is designed (docs-only) in
[Member Record, Faith Statement, Delegated Unit Management, and Configurable Serving Readiness Plan](MEMBER_RECORD_AND_SERVING_READINESS_PLAN.md)
(`MEMBER-RECORD.1A`). The first read-only slice of that direction,
`UNIT-LEAD-MANAGE.1B`, is now implemented: a read-only `/my-units/` entry that
lists the units a user may manage (staff/superuser or active `lead`
ancestor-or-self) plus their coworker roster and missing-required-role
readiness, with no edit actions. See that plan's Section A.5 for status.

## 1. Purpose and Product Problem

`ChurchStructureUnit` is now the local canonical church structure model, but the
app does not yet have a structure-native way to record long-term coworker roles
inside a unit.

Real church operations need this distinction:

- A unit may have one or more Lead people, such as senior pastor / 主任牧师,
  district leader / 区长, or small-group leader / 小组长 depending on the unit.
- Small-group-like units often have long-term coworker roles such as
  assistant_lead / 副组长, caring / 关怀同工, edify / 带查经同工,
  outreach / 福音同工, and worship / 敬拜同工.
- Bible Study weekly roles are still assigned per meeting through
  `BibleStudyMeetingRole.user`; long-term coworker context should only help
  narrow candidate pickers unless a later approved slice changes that.

The product problem is not "who belongs to this unit" or "who is serving this
week." It is "which people hold ongoing coworker roles for this structure unit,
and which role types are expected for this kind of unit."

## 2. Terminology

Structure unit:
`ChurchStructureUnit`, the flexible local hierarchy row for church, ministry,
district, small-group-like, department, or custom units.

Role type:
A named coworker role definition such as `lead`, `assistant_lead`, `caring`,
`edify`, `outreach`, `worship`, or a church-defined custom role.

Role profile / template:
A configurable bundle of required and optional role types applied to a unit
based on explicit unit semantics, for example `general_unit`, `district_unit`,
`small_group_unit`, `department_unit`, or `custom`.

Role assignment:
A link between a `ChurchStructureUnit`, a role type, and one or more users who
hold that long-term role. Multiple people may hold the same role type on the
same unit.

Required vs optional roles:
Required means the role type is expected for setup readiness and missing active
assignees should surface warnings. It does not mean the system auto-assigns a
person. Optional means the role type is available and can be assigned, but its
absence should not be a setup blocker.

Long-term coworker role vs per-meeting Bible Study role:
A long-term coworker role says a person is an ongoing Edify or Worship coworker
for an anchor unit. A per-meeting Bible Study role says a specific user is
responsible for one `BibleStudyMeeting` through `BibleStudyMeetingRole.user`.

## 3. Proposed Model Concepts

These are design concepts only.

`ChurchStructureUnitRoleType`

- Stable `code`, such as `lead`, `assistant_lead`, `caring`, `edify`,
  `outreach`, or `worship`.
- Bilingual labels, such as Lead / 负责人 and Edify / 带查经同工.
- Active flag, sort order, and optional description.
- System/default preset marker so app defaults can be distinguished from
  church-customized setup.
- Optional scope for custom role types, either global to the church instance or
  limited to one unit/profile if later product review needs that.

`ChurchStructureUnitRoleProfile`

- Stable `code`, such as `general_unit`, `district_unit`,
  `small_group_unit`, `department_unit`, or `custom`.
- Bilingual label and description.
- Active flag and sort order.
- Configurable default selection per unit type or setup workflow.
- Explicitly selected on each unit, or derived once as an editable suggestion
  during setup; it should not be recomputed from tree position.

Role requirement / template rows

- Link a role profile to role types.
- Mark each role type as required or optional for that profile.
- Preserve sort order for staff setup UI.
- Allow future churches to change which role types are required for
  small-group-like units without hard-coding SVCA's exact coworker set forever.

`ChurchStructureUnitRoleAssignment`

- Link `unit`, `role_type`, and `user`.
- Include active/date-window fields if history is needed in the first
  implementation; otherwise keep an active flag and add history later only if
  product review requires it.
- Optional non-sensitive operational note.
- Validation should prevent assignment to inactive role types and should warn
  when assigning to inactive units/users.
- Assignment does not create `ChurchStructureMembership`,
  `ChurchRoleAssignment`, `TeamAssignment`, `TeamAssignmentMember`, or
  `BibleStudyMeetingRole`.

## 4. Default Presets

Default role types:

- `lead` / Lead / 负责人
- `assistant_lead` / Assistant Lead / 副组长
- `caring` / Caring / 关怀同工
- `edify` / Edify / 带查经同工
- `outreach` / Outreach / 福音同工
- `worship` / Worship / 敬拜同工

All unit profiles should include `lead` as required by default.

The default `small_group_unit` profile should include these required role types:

- `lead`
- `assistant_lead`
- `caring`
- `edify`
- `outreach`

The default `small_group_unit` profile should include `worship` as optional.

Custom role types should be allowed so one small group can add roles such as
finance, activity, pianist, host, or another local need without forcing those
roles onto every church instance.

## 5. Leaf-Node Problem and Recommended Solution

Do not define a small group by `children.count() == 0` or by any other structural
leaf-node detection.

That rule is fragile because setup may not know future children, a unit may gain
children later, and a small-group-like unit can still have child rows for classes,
subgroups, or local organization.

Recommended solution:

- Add explicit unit semantics for coworker-role purposes, such as
  `unit_role_profile`, `unit_category`, or a configurable role template.
- Staff/setup should explicitly mark a unit as `small_group_unit` when it should
  use small-group coworker requirements.
- Existing `unit_type` can suggest an initial profile, for example a
  `UNIT_SMALL_GROUP` type can default to `small_group_unit`.
- The stored explicit profile/category should be the source for role
  requirements and warnings after setup.
- A later setup UI can show "suggested from unit type" without hiding that staff
  are choosing the role profile intentionally.

## 6. Bible Study Candidate Selection Rules

For a `BibleStudyMeeting`, candidate filtering should use
`BibleStudyMeeting.anchor_unit` as the structure-unit context.

Discussion leader / 查经带领:

- If active `edify` coworkers exist on the anchor unit, candidates should be
  only those linked users.
- If no active `edify` coworkers exist but other active coworkers exist on the
  anchor unit, candidates should be all active coworkers configured on that unit.
- If no coworkers are configured at all, the recommended V1 fallback is to keep
  the current membership/audience-based user picker behavior and show a setup
  warning to staff. This avoids blocking weekly preparation while making missing
  setup visible. A stricter fail-closed picker is safer for data quality but may
  interrupt real Friday workflow before staff have completed coworker setup.

Worship lead / 敬拜带领:

- If active `worship` coworkers exist on the anchor unit, candidates should be
  only those linked users.
- If no active `worship` coworkers exist but other active coworkers exist on the
  anchor unit, candidates should be all active coworkers configured on that unit.
- If no coworkers are configured at all, use the same recommended fallback:
  keep the current membership/audience-based picker with a setup warning.

These rules only narrow candidates. Candidate eligibility does not create a
serving assignment, does not imply the user is assigned this week, and does not
grant a permission. The final weekly responsibility remains an explicit
`BibleStudyMeetingRole.user` row.

## 7. My Serving and Today Boundaries

Today should continue to show concrete weekly Bible Study role context only from
linked-user `BibleStudyMeetingRole` rows that are visible to the signed-in user.

My Serving can later show long-term structure coworker roles as a separate
"ongoing roles" section if that product slice is approved. That display should
be clearly separate from this-week serving assignments and Bible Study meeting
role confirmation.

Do not design automatic confirmation for long-term structure roles in this
slice. Role confirmation for Bible Study meeting roles remains tied to explicit
`BibleStudyMeetingRole.user` assignments.

## 8. Permission and Serving Boundaries

Structure coworker roles are not `TeamAssignment`.

Structure coworker roles are not `TeamAssignmentMember`.

Structure coworker roles are not `ChurchRoleAssignment` and do not automatically
grant capabilities.

Structure coworker roles are not membership/belonging. A user's
`ChurchStructureMembership` gives approved belonging/visibility for migrated
consumers, but membership does not imply Lead, Edify, Worship, serving, or
permissions.

Being an Edify or Worship coworker is long-term role context. It is not this
week's assignment unless a staff/manager explicitly creates or updates a
`BibleStudyMeetingRole.user` row.

If a future workflow wants a coworker role to grant limited editing capability,
that must be a separate role-aware permission slice with explicit
`ChurchRoleAssignment` or capability design, not an implicit side effect of this
model.

## 9. Implementation Phases

Phase 1 - docs-only design:

- Record the architecture and boundaries.
- No model, migration, UI, template, test, data, or runtime changes.

Phase 2 - model foundation:

- Add role type, role profile/template, requirement, and assignment models.
- Seed or create default preset rows through an explicit setup command or data
  migration only after data policy is approved.
- Add model/admin tests for required-vs-optional semantics and no implicit
  assignment behavior.

Phase 3 - setup/admin UI:

- Let staff configure role profiles and role requirements.
- Let staff select each unit's role profile explicitly.
- Let staff assign multiple active users to each role type on each unit.
- Surface missing required roles as setup/readiness warnings, not silent fills.

Phase 4 - Bible Study candidate filtering:

- Use `BibleStudyMeeting.anchor_unit`.
- Prefer Edify coworkers for discussion leader and Worship coworkers for worship
  lead.
- Fall back to all active coworkers on the unit when the role-specific pool is
  empty.
- Fall back to current membership/audience-based pickers with setup warning when
  no coworkers exist.
- Keep final assignment in `BibleStudyMeetingRole.user`.

Phase 5 - optional My Serving long-term role display:

- Show ongoing structure roles separately from this-week assignments only if
  product review approves it.
- Do not add long-term role confirmation in this phase unless separately
  designed.

## 10. Non-Goals

- No code implementation in UNIT-COWORKER.1A.
- No model, migration, fixture, data mutation, or template change.
- No automatic assignment of Lead or any coworker role.
- No automatic scheduling or rotation.
- No conversion of structure coworker roles into `TeamAssignment`.
- No conversion of structure coworker roles into `ChurchRoleAssignment`.
- No permission grants from coworker roles.
- No membership or audience visibility change.
- No role confirmation workflow for long-term structure roles.
- No leaf-node-based definition of small group.
- No hard-coded permanent SVCA-only coworker role set.

## 11. Open Decisions and Recommended Defaults

Recommended default: use an explicit `ChurchStructureUnitRoleProfile` selected
on each unit. Let `unit_type` suggest an initial profile, but do not make tree
depth or current child count authoritative.

Recommended default: make `lead` required for all unit profiles.

Recommended default: make `assistant_lead`, `caring`, `edify`, and `outreach`
required for `small_group_unit`.

Recommended default: make `worship` optional for `small_group_unit`, because
some groups may share worship support or handle worship ad hoc.

Recommended default: when Bible Study coworker setup is missing, keep current
candidate picker behavior with a staff-visible setup warning rather than
failing closed. This is more operationally forgiving for V1 while still making
readiness gaps visible.

Open decision: whether role assignments need full date-window history in the
first model slice or can start with active/inactive plus audit timestamps.

Resolved for V1: UNIT-COWORKER.1B implements global role types with globally
unique codes. Per-profile or per-unit scoped custom role types remain deferred
future work and would require a separately approved slice if needed.

Open decision: whether inactive users already assigned to a role should remain
visible for historical cleanup in setup UI.

Open decision: which staff capability should manage role profiles and role
assignments. Do not reuse membership visibility or ordinary belonging for this.

## 12. Targeted Tests for Later Implementation

Model foundation tests:

- Default role type and profile rows can be created idempotently.
- Every default profile requires `lead`.
- `small_group_unit` requires `assistant_lead`, `caring`, `edify`, and
  `outreach`, and treats `worship` as optional.
- Multiple users can hold the same role type on the same unit.
- Assigning a role does not create membership, `ChurchRoleAssignment`,
  `TeamAssignment`, `TeamAssignmentMember`, or `BibleStudyMeetingRole`.
- Missing required assignees produce readiness warnings, not auto-created users
  or assignments.

Setup/admin tests:

- Staff can explicitly select a unit role profile.
- A `UNIT_SMALL_GROUP` unit can suggest `small_group_unit`, but staff can review
  or override the profile according to product rules.
- A unit with children can still use the `small_group_unit` profile.
- A childless non-small-group unit is not treated as a small group only because
  it has no children.
- Custom role types can be added without changing global hard-coded choices.

Bible Study picker tests:

- Discussion leader candidates prefer active `edify` coworkers on the meeting
  `anchor_unit`.
- Worship lead candidates prefer active `worship` coworkers on the meeting
  `anchor_unit`.
- If the role-specific pool is empty, candidates fall back to all active
  coworkers on the anchor unit.
- If no coworkers are configured, candidates use the current
  membership/audience-based picker and staff see a setup warning.
- Candidate filtering never creates or confirms a `BibleStudyMeetingRole`.
- Display-name-only meeting roles remain fallback display data and are not
  treated as coworker assignments.

Boundary tests:

- Active `ChurchStructureMembership` alone does not make a user a coworker.
- Coworker assignment alone does not grant staff or Bible Study management
  capability.
- Coworker assignment alone does not create My Serving weekly assignments.
- Today continues to surface only explicit linked-user `BibleStudyMeetingRole`
  rows for weekly Bible Study responsibilities.
