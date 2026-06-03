# Church Structure Mapping and Membership Strategy

## 1. Purpose

CS-H.2 added `ChurchStructureUnit` as a model-only flexible tree foundation. CS-H.2A hardened that tree with indirect cycle validation and safe ancestor/path helpers. CS-H.3B adds nullable mapping fields from legacy structure models to `ChurchStructureUnit`. CS-H.3C adds an idempotent management command for seeding and mapping current structure data into that tree. CS-H.3D records that GoDaddy production/staging seeding completed successfully and the second dry-run was clean. CS-H.3E records that the remaining `Santa Clara 3` data QA item was resolved/closed. CS-H.4 records the `ChurchStructureMembership` design. CS-H.5A adds the model-only `ChurchStructureMembership` foundation. CS-H.5B hardens membership helpers and validation. CS-H.5C adds an explicit dry-run/apply backfill command from `Profile.small_group`. CS-H.5D records user-attested GoDaddy production/staging backfill verification. CS-H.5E improves Django Admin clarity for legacy structure models versus future foundation models. CS-H.6 records the signup requested-unit flow design. CS-H.7 records the admin approval workflow design.

Before seeding root, CM/EM, districts, or small groups into the tree, the project needs an explicit mapping and membership strategy. The purpose of this document is to avoid duplicate source-of-truth drift, protect permission and visibility behavior, and preserve the validated pilot baseline.

This began as the CS-H.3 planning document. CS-H.3B implements only nullable legacy-to-`ChurchStructureUnit` mapping fields and admin visibility for those fields. CS-H.3C implements only the explicit `seed_church_structure_units` management command with dry-run and apply modes. CS-H.3D and CS-H.3E are production/staging verification and data QA closure documentation only. CS-H.4 is membership design only. CS-H.5A adds the model/admin/test foundation only. CS-H.5B adds helper/validation hardening only. CS-H.5C adds only an explicit backfill command and tests. CS-H.5D is verification documentation only. CS-H.5E is Django Admin clarity only. CS-H.6 is signup requested-unit flow design only. CS-H.7 is admin approval workflow design only. These steps do not auto-run, change signup, add audience selection, add filtering, switch runtime source of truth, or add custom staff UI.

## 2. Source-of-Truth Decision

Long-term target:
- `ChurchStructureUnit` is the canonical church structure source.
- `ChurchStructureMembership` is the canonical user belonging / membership source.

Short-term transition:
- `MinistryContext`, `District`, `SmallGroup`, and `Profile.small_group` remain the source of truth for current runtime behavior.
- `ChurchStructureUnit` is initially a mirror or mapped structure.
- CS-H.3B adds nullable mapping fields on the legacy structure models, but those fields do not drive runtime behavior.
- CS-H.3C can populate `ChurchStructureUnit` rows and fill those mapping fields through an explicit management command, but the mappings still do not drive runtime behavior.
- No existing behavior should switch to `ChurchStructureUnit` until a specific consumer is planned, implemented, and tested.

Current pilot behavior must remain stable:
- Bible Study visibility continues to use `Profile.small_group` and `SmallGroup`.
- Bible Study schedule scope continues to use `BibleStudySeries.scope_type`, `ministry_context`, `district`, and `small_group`.
- ServiceEvent audience behavior continues to use `scope_type`, `district`, and `small_group`.
- `ServiceEvent.ministry_context` remains label-only.

## 3. SmallGroup Absorption Strategy

`SmallGroup` should eventually be represented as `ChurchStructureUnit` rows.

Likely future mapping:
- `SmallGroup` -> `ChurchStructureUnit` with `unit_type=small_group`, or
- `SmallGroup` -> `ChurchStructureUnit` with `unit_type=fellowship`, depending on final naming.

Rules:
- Do not delete `SmallGroup` early.
- Do not replace `Profile.small_group` early.
- Do not replace `BibleStudyMeeting.small_group` early.
- During coexistence, `Profile.small_group` and `BibleStudyMeeting.small_group` continue to work.
- A future migration should map each current `SmallGroup` to exactly one `ChurchStructureUnit`.
- Avoid dual-edit drift by deciding which side is editable during the transition.

Recommended transition stance:
- Legacy models remain editable source-of-truth until mapping is seeded and verified.
- `ChurchStructureUnit` mirrors them at first.
- Only after admin QA should any staff workflow edit structure through `ChurchStructureUnit`.
- CS-H.3B prepares this by adding nullable mapping fields only; CS-H.3C owns idempotent seeding/mapping through the `seed_church_structure_units` command.

## 4. Membership Strategy

Future model concept:

`ChurchStructureMembership`
- `user`
- `unit`
- `membership_type` or `role`
- `start_date`
- `end_date`
- `is_primary`
- `status`
  - `requested`
  - `active`
  - `ended`
  - `rejected`
- `approved_by`
- `approved_at`
- `notes` optional, non-sensitive

Clarifications:
- Membership is for belonging, not staff permissions.
- `ChurchRoleAssignment` and the capability system remain separate for permissions.
- `TeamAssignment` remains separate for serving assignments.
- Membership does not automatically grant staff permissions.
- Membership does not automatically assign ministry serving roles.
- Notes must not store sensitive counseling, pastoral, medical, financial, or private information.

This membership model should eventually replace `Profile.small_group` as the canonical belonging source, but only after staged migration and visibility tests.

CS-H.4 design recommendation:
- Use `ChurchStructureMembership` as the eventual canonical belonging source.
- Prefer a single membership lifecycle model with `status=requested` for V1 unless implementation discovers stronger audit needs for a separate request model.
- Treat only approved active membership as eligible for future visibility.
- Keep `Profile.small_group` as the runtime source for now.
- See `docs/CHURCH_STRUCTURE_MEMBERSHIP_DESIGN.md`.

CS-H.5A implementation status:
- `ChurchStructureMembership` exists as a model-only foundation.
- No signup/onboarding flow writes requested memberships yet.
- No admin approval workflow exists yet.
- CS-H.5C adds an explicit backfill command from `Profile.small_group`.
- CS-H.5D records user-attested production/staging backfill verification. Exact command-output counts were not recorded.
- CS-H.5E improves Django Admin clarity but does not change source of truth.
- No runtime consumer reads membership yet.

CS-H.5B hardening status:
- `ChurchStructureMembership` has active/date-window query helpers.
- Requested, rejected, cancelled, and ended memberships do not count as active.
- Runtime still uses `Profile.small_group`.

CS-H.5C backfill command status:
- `backfill_church_structure_memberships` defaults to dry-run and supports `--apply`.
- It creates active primary memberships only where `Profile.small_group.church_structure_unit` is mapped.
- It does not update `Profile.small_group`, create requested memberships, infer permissions, or change current visibility.

CS-H.5D verification status:
- GoDaddy production/staging backfill verification is complete by user-attested run.
- Exact command-output counts were not recorded.
- No unresolved warning, error, or data QA item was reported.
- Runtime still uses `Profile.small_group`.

CS-H.5E admin clarity status:
- Django Admin distinguishes legacy current-runtime models from future foundation models.
- `MinistryContext`, `District`, `SmallGroup`, and `Profile.small_group` must not be deleted yet.
- Admin mapping status is visible for legacy models.
- Custom staff admin UI remains future.

## 5. Registration / Onboarding Strategy

Use the compromise approach.

Signup or onboarding may collect:
- username/password
- optional email
- language
- requested structure unit or requested small group
- optional note, such as "I attend Rainbow 1" or "I am new"

But:
- the requested unit is not final membership
- the user starts as pending assignment or limited/unassigned
- admin/staff reviews and approves membership
- after approval, official membership is created or activated
- during transition, approval may also set `Profile.small_group`

Why this approach:
- Users may choose the wrong group.
- New people may not know their group.
- Group membership affects Bible Study visibility.
- Future membership will affect audience scope.
- Church belonging should be confirmed pastorally and administratively.

Do not allow normal users to directly self-assign final membership during signup.

## 6. Transition States

Likely user states:
- `unassigned` / no group
- requested assignment pending
- active assigned membership
- rejected / needs clarification
- ended / transferred membership

Current behavior mapping:
- Today, current pilot behavior may use `Profile.small_group`.
- A user without `Profile.small_group` receives current safe empty/limited states where implemented.
- Future membership may drive visibility only after explicit consumer migration.
- During transition, approved primary small-group membership can synchronize `Profile.small_group`.

Important transition rule:
- Do not trust requested membership for visibility.
- Only approved active membership should influence future visibility.

## 7. Mapping Strategy Options

### Option A: Nullable Mapping FKs on Existing Models

Add fields such as:
- `MinistryContext.church_structure_unit`
- `District.church_structure_unit`
- `SmallGroup.church_structure_unit`

CS-H.3B status: selected and implemented as nullable, permissive mapping fields.

Pros:
- Clear and easy to inspect.
- Simple joins from current runtime models to the future tree.
- Good admin/debug visibility.
- Avoids generic source-model/source-id logic.

Cons:
- Requires migrations on legacy models.
- Adds future-tree awareness to old models.
- Needs careful handling if long-term deletion/deprecation is planned.

### Option B: Separate Mapping Table

Possible model:

`ChurchStructureLegacyMap`
- `unit`
- `source_model`
- `source_id`
- `source_label_snapshot`

Pros:
- Keeps legacy models untouched.
- Flexible for multiple legacy source types.
- Can preserve historical labels.

Cons:
- More indirection.
- Easier to create invalid source references.
- Needs custom validation and admin tooling.

### Option C: Derive By Code/Name Only

Pros:
- No migration.
- Simple initial script logic.

Cons:
- Fragile under renames.
- Ambiguous when names repeat.
- Poor auditability.
- High drift risk.

Recommendation:
- Prefer explicit nullable FK mapping fields on existing models if migration risk is acceptable. CS-H.3B follows this recommendation.
- Use a separate mapping table only if keeping legacy models completely untouched is more important.
- Do not rely on name/code matching only.

## 8. Seeded Tree Plan

Conceptual tree only:

```text
CHURCH / Whole Church / 全教会
-> MinistryContext units, such as CM and EM
   -> District units under their MinistryContext unit when available
      -> SmallGroup units under their District unit when available
```

Rules:
- No seeding in CS-H.3 or CS-H.3B.
- CS-H.3C handles idempotent seeding/mapping of existing `MinistryContext`, `District`, and `SmallGroup` records into `ChurchStructureUnit` through `python manage.py seed_church_structure_units`.
- The command defaults to dry-run; use `--apply` only after reviewing dry-run output.
- Seeding is idempotent and may be re-run after future structure edits.
- Do not delete legacy records.
- Do not drop orphan records.
- Orphan `District` rows without `MinistryContext` are placed under an `UNASSIGNED-DISTRICTS` holding unit.
- Orphan `SmallGroup` rows without `District` are placed under an `UNASSIGNED-GROUPS` holding unit.
- Seed labels should preserve bilingual names where available.

Root:
- One active Whole Church root is the intended system shape.
- CS-H.3C seeds a parentless `CHURCH` root when applying the command.
- Root uniqueness database enforcement remains deferred; the command warns about duplicate active roots or duplicate parentless `CHURCH` units without destructively fixing them.

Recommended deployment flow:
- Deploy code.
- Run migrations.
- Run `python manage.py seed_church_structure_units --dry-run`.
- Inspect output for unexpected creates, updates, links, or warnings.
- Run `python manage.py seed_church_structure_units --apply`.
- Run `python manage.py seed_church_structure_units --dry-run` again to confirm no remaining changes are expected.

CS-H.3D verification result:
- GoDaddy production/staging `--apply` completed with return code 0.
- The command created 35 `ChurchStructureUnit` rows and linked 33 legacy records.
- The second dry-run reported `would created: 0`, `would updated: 0`, `would linked: 0`, and `warnings: 0`.
- `Santa Clara 3` was under `UNASSIGNED-GROUPS` because the legacy `SmallGroup` had no district; this was a business/data QA item, not a command failure.

CS-H.3E data QA closure:
- The `Santa Clara 3` legacy data issue was corrected or otherwise handled first, rather than manually moving only the `ChurchStructureUnit`.
- The seed/apply flow was rerun as needed.
- This item should remain closed as long as the final dry-run reports zero create/update/link changes.
- See `docs/CHURCH_STRUCTURE_SEEDING_VERIFICATION.md`.

## 9. Requested Unit Rules

Future signup requested unit should probably point to:
- a selectable active `ChurchStructureUnit`
- likely only membership-eligible units, such as `small_group` or `fellowship`
- visitor/unassigned choices when the user is unsure
- not arbitrary operational units
- not `MinistryTeam`

Open decisions:
- Should users request only leaf/small-group units?
- Should users be allowed to request ministry context or district if unsure?
- Should there be a "Not sure / New visitor" option?

Recommendation:
- Offer known small-group/fellowship leaf units when available.
- Also offer "Not sure / New visitor".
- Allow an optional note field to help admin assign correctly.
- Do not let requested unit become active membership without approval.
- See `docs/CHURCH_STRUCTURE_SIGNUP_REQUEST_FLOW_DESIGN.md` for the CS-H.6 signup request design.

## 10. Admin Approval Workflow

Future staff workflow:
- Staff sees pending requested assignments.
- Staff can approve into official membership.
- Staff can change requested unit before approval.
- Staff can reject or mark needs clarification.
- Staff can assign no group / visitor state.
- Approval creates or activates future membership.
- During transition, approval updates `Profile.small_group` when the approved primary unit maps to a `SmallGroup`.

Do not implement this now.

The workflow should be simple enough for non-technical staff: review request, choose official group/unit, approve, or mark for clarification.

See `docs/CHURCH_STRUCTURE_MEMBERSHIP_APPROVAL_WORKFLOW_DESIGN.md` for the CS-H.7 approval workflow design.

## 11. Impact on Current Modules

### Bible Study

Current `/studies/` visibility uses `Profile.small_group`.

Future membership may replace this only after tests prove no cross-group visibility leaks. Do not switch now.

### Reading Group Progress

Current group progress uses `Profile.small_group` / `SmallGroup`.

Do not switch now.

### ServiceEvent

`ServiceEvent.ministry_context` remains label-only.

Audience/filtering remains future work.

### Community Activities

Future Community Activities should use `ChurchStructureUnit` audience/membership from the start if the structure and membership layers are ready.

Do not implement Community Activities now.

### My Serving / TeamAssignment

Serving assignment remains `TeamAssignment`-based.

Membership does not automatically assign serving roles.

## 12. Source-of-Truth Transition Phases

Recommended phases:
- CS-H.3: design mapping/membership strategy.
- CS-H.3B: choose and implement mapping fields/table model-only. Completed with nullable FKs on legacy structure models.
- CS-H.3C: seed root and current structure idempotently through a management command. Completed.
- CS-H.3D: production/staging seeding verification closure. Completed.
- CS-H.3E: seeded structure data QA closure. Completed.
- CS-H.4: design `ChurchStructureMembership` model, not implementation. Completed.
- CS-H.5A: implement membership model-only foundation. Completed.
- CS-H.5B: membership model hardening/tests. Completed.
- CS-H.5C: backfill command with dry-run/apply from `Profile.small_group`. Completed.
- CS-H.5D: production/staging backfill verification. Completed by user-attested GoDaddy run; exact output counts were not recorded.
- CS-H.5E: admin clarity for legacy structure vs future structure/membership foundation. Completed.
- CS-H.6: signup requested-unit flow. Completed.
- CS-H.7: admin approval workflow. Completed.
- Later: migrate selected consumers from `Profile.small_group` to membership.

No hard cutover should happen early.

## 13. Risks

Known risks:
- two sources of truth drift
- users self-select wrong group
- visibility leaks if membership is trusted too early
- admin workload
- orphan records
- renames and moves
- overbuilding HR/ERP
- confusing membership with permissions
- confusing membership with serving assignments
- approving requests without enough context

Mitigation direction:
- keep legacy behavior during coexistence
- use explicit mapping rather than name matching
- make seeding idempotent
- require admin approval before active membership
- separate membership from permissions and serving
- add one consumer at a time only after tests

## 14. Non-Goals

CS-H.3/CS-H.3B/CS-H.3C do not include:
- signup changes
- membership model
- audience selector
- ServiceEvent filtering
- Community Activities
- Staff Admin UI
- replacement of `Profile.small_group`
- replacement of `BibleStudySeries` scope
- deletion of `SmallGroup`
- deletion of `District`
- deletion of `MinistryContext`

## 15. Open Decisions

Open decisions:
- mapping FK vs mapping table
- exact `unit_type` name for `SmallGroup` / fellowship
- whether implementation should support broader district/ministry-context request routing, beyond the CS-H.6 recommendation to prefer active leaf small-group/fellowship units plus "Not sure / New visitor"
- whether to add requested unit to `Profile` or create a separate request model
- exact approval capability and staff/superuser override rules
- whether approved membership syncs `Profile.small_group` immediately
- when membership becomes source of truth for `/studies/`
- how to handle transfers
- how to handle orphan districts or groups during seed
- when to enforce one active Whole Church root in the database

Current recommendation:
- long-term source of truth: `ChurchStructureUnit` + `ChurchStructureMembership`
- short-term runtime source of truth: current legacy models
- mapping: explicit nullable FK fields, added in CS-H.3B
- seeding: explicit dry-run/apply management command, added in CS-H.3C
- data QA: production/staging seeded structure QA closed in CS-H.3E
- signup: requested unit plus admin approval, never direct final self-assignment
