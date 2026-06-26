# Church Structure Mapping and Membership Strategy

> **Status note (CS-CORE.0A / current superseded-state):** this document is the
> CS-H-era strategy record and is preserved as historical background. Statements
> below that legacy mapping fields "do not drive runtime behavior," that
> `Profile.small_group` is current runtime source, or that Bible Study schedule
> generation continues to resolve selected audience units to legacy `SmallGroup`
> rows are superseded. Current normal Bible Study V2 generation is
> structure-native through audience rows, `generation_key`, and `anchor_unit`;
> ServiceEvent audience rows match active primary `ChurchStructureMembership`;
> `Profile.small_group`, the legacy structure object tables, and multiple
> legacy scope/mirror fields have been removed. Current architecture direction
> and the staged migration plan live in
> `docs/CHURCH_STRUCTURE_CORE_MIGRATION_PLAN.md` and
> `docs/LEGACY_STRUCTURE_RETIREMENT_EXECUTION_PLAN.md`.

## 1. Purpose

CS-H.2 added `ChurchStructureUnit` as a model-only flexible tree foundation. CS-H.2A hardened that tree with indirect cycle validation and safe ancestor/path helpers. CS-H.3B adds nullable mapping fields from legacy structure models to `ChurchStructureUnit`. CS-H.3C adds an idempotent management command for seeding and mapping current structure data into that tree. CS-H.3D records that GoDaddy production/staging seeding completed successfully and the second dry-run was clean. CS-H.3E records that the remaining `Santa Clara 3` data QA item was resolved/closed. CS-H.4 records the `ChurchStructureMembership` design. CS-H.5A adds the model-only `ChurchStructureMembership` foundation. CS-H.5B hardens membership helpers and validation. CS-H.5C adds an explicit dry-run/apply backfill command from `Profile.small_group`. CS-H.5D records user-attested GoDaddy production/staging backfill verification. CS-H.5E improves Django Admin clarity for legacy structure models versus future foundation models. CS-H.6 records the signup requested-unit flow design. CS-H.7 records the admin approval workflow design. CS-H.8 records the integrated request-flow checkpoint across signup, Profile, staff approval, and transition `Profile.small_group` sync. CS-H.9 records membership request UX hardening as complete. CS-H.10 records the CMS hardening checkpoint.

Before seeding root, CM/EM, districts, or small groups into the tree, the project needs an explicit mapping and membership strategy. The purpose of this document is to avoid duplicate source-of-truth drift, protect permission and visibility behavior, and preserve the validated pilot baseline.

This began as the CS-H.3 planning document. CS-H.3B implements only nullable legacy-to-`ChurchStructureUnit` mapping fields and admin visibility for those fields. CS-H.3C implements only the explicit `seed_church_structure_units` management command with dry-run and apply modes. CS-H.3D and CS-H.3E are production/staging verification and data QA closure documentation only. CS-H.4 is membership design only. CS-H.5A adds the model/admin/test foundation only. CS-H.5B adds helper/validation hardening only. CS-H.5C adds only an explicit backfill command and tests. CS-H.5D is verification documentation only. CS-H.5E is Django Admin clarity only. CS-H.6 starts requested-unit flow design; CS-H.6B and CS-H.6D add signup/Profile request capture. CS-H.7 starts admin approval workflow design; CS-H.7B/C/D/E add staff request review, approve/reject actions, and narrow `Profile.small_group` approval sync. CS-H.8 is an integration checkpoint only. CS-H.9 is membership request UX hardening only. CS-H.10 is a docs/checkpoint-only hardening checkpoint. These steps do not auto-run, add audience selection, add filtering, switch runtime source of truth, or add broad staff admin expansion.

## 2. Source-of-Truth Decision

Long-term target:
- `ChurchStructureUnit` is the canonical church structure source.
- `ChurchStructureMembership` is the canonical user belonging / membership source.

Historical short-term transition:
- At the CS-H.3 planning point, `MinistryContext`, `District`, `SmallGroup`, and `Profile.small_group` remained the source of truth for then-current runtime behavior.
- `ChurchStructureUnit` was initially a mirror or mapped structure.
- CS-H.3B added nullable mapping fields on the legacy structure models, but those fields did not drive runtime behavior at that time.
- CS-H.3C could populate `ChurchStructureUnit` rows and fill those mapping fields through an explicit management command, but the mappings still did not drive runtime behavior then.
- No behavior was to switch to `ChurchStructureUnit` until a specific consumer was planned, implemented, and tested. That consumer-by-consumer migration has since proceeded; current state is summarized in the status note above.

Current behavior must remain explicit by consumer:
- Bible Study v2 `BibleStudyMeeting` ordinary-member visibility uses `BibleStudyMeetingAudienceScope` rows plus active primary `ChurchStructureMembership`; zero-row V2 meetings fail closed for ordinary users, and `Profile.small_group` / `BibleStudyMeeting.small_group` no longer exist.
- Bible Study schedule scope and normal meeting generation use `BibleStudySeriesAudienceScope` rows and structure-unit-native targets (`generation_key`, `anchor_unit`, and meeting audience rows), not legacy `SmallGroup` resolution.
- V1 `BibleStudySession` schema is removed; historical V1 references in this strategy are planning context only.
- ServiceEvent visibility uses `ServiceEventAudienceScope` rows plus active primary `ChurchStructureMembership`; zero-row ServiceEvents fail closed for ordinary users, and legacy `scope_type` / `district` / `small_group` fields are removed.
- Host / Language display uses `ServiceEvent.host_language_unit` plus the audience-derived structure fallback; `ServiceEvent.ministry_context` is removed.
- TeamAssignment / My Serving remain explicit serving concepts and are not inferred from membership.

## 3. Historical SmallGroup Absorption Strategy

Historical/superseded: this section records the CS-H.3-era bridge plan before
legacy structure row/table retirement. The current canonical local structure is
`ChurchStructureUnit`; legacy `SmallGroup`, `District`, and `MinistryContext`
models/tables are removed from current code.

Likely future mapping:
- `SmallGroup` -> `ChurchStructureUnit` with `unit_type=small_group`, or
- `SmallGroup` -> `ChurchStructureUnit` with `unit_type=fellowship`, depending on final naming.

Historical rules at that bridge point:
- Do not delete `SmallGroup` early.
- Do not replace `Profile.small_group` early.
- Do not replace `BibleStudyMeeting.small_group` early.
- During coexistence, `Profile.small_group` and `BibleStudyMeeting.small_group` continue to work.
- A future migration should map each then-current `SmallGroup` to exactly one `ChurchStructureUnit`.
- Avoid dual-edit drift by deciding which side is editable during the transition.

Current resolution: those bridge concerns were resolved by the later consumer
switches, field removals, guarded legacy object-row purge, and final legacy
structure table retirement. Do not use this section as current implementation
guidance.

Historical recommended transition stance:
- Legacy models remained editable source-of-truth until mapping was seeded and verified.
- `ChurchStructureUnit` mirrored them at first.
- Only after admin QA should any staff workflow edit structure through `ChurchStructureUnit`.
- CS-H.3B prepared this by adding nullable mapping fields only; CS-H.3C owned idempotent seeding/mapping through the `seed_church_structure_units` command.

Current resolution: `ChurchStructureUnit` is the canonical local structure model,
and the legacy structure object tables / mapping FKs are removed.

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

Historical/superseded: this membership model was intended to eventually replace
`Profile.small_group` as the canonical belonging source. That replacement has
since happened for migrated consumers, and `Profile.small_group` was removed.

CS-H.4 design recommendation:
- Use `ChurchStructureMembership` as the eventual canonical belonging source.
- Prefer a single membership lifecycle model with `status=requested` for V1 unless implementation discovers stronger audit needs for a separate request model.
- Treat only approved active membership as eligible for future visibility.
- Historical/superseded at the CS-H.4 point: keep `Profile.small_group` as the runtime source for that stage. Current migrated consumers use active primary membership, and `Profile.small_group` is removed.
- See `docs/CHURCH_STRUCTURE_MEMBERSHIP_DESIGN.md`.

CS-H.5A implementation status (historical/superseded):
- `ChurchStructureMembership` exists as a model-only foundation.
- Signup and Profile can write requested memberships for staff review.
- Staff request review, approve/reject actions, and narrow `Profile.small_group` approval sync exist.
- At that time, no runtime consumer used membership as source of truth yet; current migrated consumers now use active primary membership where explicitly approved.
- CS-H.5C adds an explicit backfill command from `Profile.small_group`.
- CS-H.5D records user-attested production/staging backfill verification. Exact command-output counts were not recorded.
- CS-H.5E improves Django Admin clarity but does not change source of truth.
- Historical/superseded: no runtime consumer read membership yet at CS-H.5A/5E time.

CS-H.5B hardening status:
- `ChurchStructureMembership` has active/date-window query helpers.
- Requested, rejected, cancelled, and ended memberships do not count as active.
- Historical/superseded: runtime still used `Profile.small_group` at this CS-H.5 stage. Current approved migrated consumers use active primary `ChurchStructureMembership`, and `Profile.small_group` was removed in PROFILE-SG-FIELD-RETIRE.1A.

CS-H.5C backfill command status:
- `backfill_church_structure_memberships` defaults to dry-run and supports `--apply`.
- It creates active primary memberships only where `Profile.small_group.church_structure_unit` is mapped.
- It does not update `Profile.small_group`, create requested memberships, infer permissions, or change current visibility.

CS-H.5D verification status:
- GoDaddy production/staging backfill verification is complete by user-attested run.
- Exact command-output counts were not recorded.
- No unresolved warning, error, or data QA item was reported.
- Historical/superseded: runtime still used `Profile.small_group` at this CS-H.5D verification point. Current approved migrated consumers use active primary `ChurchStructureMembership`, and `Profile.small_group` was removed in PROFILE-SG-FIELD-RETIRE.1A.

CS-H.5E admin clarity status:
- Historical/superseded: Django Admin distinguished legacy current-runtime models from future foundation models at the CS-H.5E point.
- Historical/superseded: `MinistryContext`, `District`, `SmallGroup`, and `Profile.small_group` were not to be deleted in that slice.
- Admin mapping status was visible for legacy models during the bridge period.
- The active legacy mapping/admin surfaces were later retired with the row/table retirement slices.

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

Historical behavior mapping:
- At this CS-H.3/CS-H.5 planning point, pilot behavior could use `Profile.small_group`.
- A user without `Profile.small_group` received then-current safe empty/limited states where implemented.
- Membership could drive visibility only after explicit consumer migration.
- During transition, approved primary small-group membership could synchronize `Profile.small_group`.

Current behavior: migrated consumers use active primary `ChurchStructureMembership`
only where explicitly switched, with app-specific audience/snapshot rows as
applicable. `Profile.small_group` is removed.

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

Historical/resolved decisions:
- CS-H.6 chose active leaf small-group/fellowship-style units for ordinary requests.
- Broader ministry-context/district request routing remains a future product choice, not current legacy-model behavior.
- The request flow includes a "Not sure / New visitor" path.

Recommendation:
- Offer known small-group/fellowship leaf units when available.
- Also offer "Not sure / New visitor".
- Allow an optional note field to help admin assign correctly.
- Do not let requested unit become active membership without approval.
- See `docs/CHURCH_STRUCTURE_SIGNUP_REQUEST_FLOW_DESIGN.md` for the CS-H.6 signup request design.

## 10. Admin Approval Workflow

Historical staff workflow plan:
- Staff sees pending requested assignments.
- Staff can approve into official membership.
- Staff can change requested unit before approval.
- Staff can reject or mark needs clarification.
- Staff can assign no group / visitor state.
- Approval creates or activates membership.
- Historical/superseded: during transition, approval updated `Profile.small_group` when the approved primary unit mapped to a `SmallGroup`.

This workflow was later implemented and then the legacy sync portion was retired.

The workflow should be simple enough for non-technical staff: review request, choose official group/unit, approve, or mark for clarification.

See `docs/CHURCH_STRUCTURE_MEMBERSHIP_APPROVAL_WORKFLOW_DESIGN.md` for the CS-H.7 approval workflow design.

## 11. Impact on Current Modules

### Bible Study

Current `/studies/` v2 meeting visibility uses active primary `ChurchStructureMembership` after CS-CORE.2C-B. `Profile.small_group` alone no longer grants v2 `BibleStudyMeeting` visibility.

Historical note: this CS-H-era section originally said `/studies/` visibility used `Profile.small_group`; that was true before CS-CORE.2C-B. Legacy `BibleStudySession` visibility remains unchanged.

### Reading Group Progress

Current group progress uses membership-core own-group resolution plus
structure-aware role scopes where applicable. Historical/superseded: this
section originally said group progress used `Profile.small_group` / `SmallGroup`
and should not switch in this slice.

### ServiceEvent

Current ServiceEvent visibility uses `ServiceEventAudienceScope` rows plus
active primary membership, with zero-row events failing closed for ordinary
users. Host / Language display uses `ServiceEvent.host_language_unit` plus
audience-derived fallback. Historical/superseded: this section originally said
`ServiceEvent.ministry_context` remained label-only and audience filtering was
future work.

### Community Activities

Future Community Activities should use `ChurchStructureUnit` audience/membership from the start if the structure and membership layers are ready.

Do not implement Community Activities now.

### My Serving / TeamAssignment

Serving assignment remains `TeamAssignment`-based.

Membership does not automatically assign serving roles.

## 12. CS-H.8 Integration Checkpoint

CS-H.8 verified the integrated request flow across signup, normal-user Profile, staff membership request list/detail, approve/reject actions, and CS-H.7E transition sync behavior.

Checkpoint result:
- signup and Profile create pending `ChurchStructureMembership(status=requested)` rows without updating `Profile.small_group`
- Profile updates an existing pending request and normal users cannot self-edit `Profile.small_group`
- staff list/detail surfaces signup-created and Profile-created pending requests
- historical/superseded: approving a mapped request activated membership and synced `Profile.small_group` only when the approved active primary unit mapped to exactly one active legacy `SmallGroup`
- historical/superseded: reject and requested/pending states did not sync `Profile.small_group`
- requested memberships do not grant access, permissions, serving assignments, audience eligibility, or runtime visibility before approval
- Later slices superseded the remaining legacy-belonging claims: Bible Study V2 meeting visibility, group progress, reflection, Prayer, and ServiceEvent use their approved membership/audience/snapshot paths; ServiceEvent and Bible Study zero-row fallbacks fail closed; V1 `BibleStudySession` and `Profile.small_group` are removed. My Serving remains explicit assignment-based.

No signup/profile feature expansion, consumer migration, audience filtering, or Community Activities work was added in CS-H.8.

## 13. CS-H.10 CMS Hardening Checkpoint

CS-H.10 records the current CMS hardening baseline after the membership request flow work.

Checkpoint result:
- Historical/superseded CS-H.7E approval sync rule completed at that time: approved active primary memberships synced `Profile.small_group` only when the approved unit mapped to exactly one active legacy `SmallGroup`. That sync was later retired and `Profile.small_group` was removed.
- CS-H.8 integration checkpoint is complete
- CS-H.9 membership request UX hardening is complete
- mobile nav polish remains deferred and the current mobile header behavior is accepted for now
- root `AGENTS.md` verification policy has been added for scoped checks, accounts test timeout handling, and browser/mobile QA expectations

CS-H.10 did not change runtime behavior, migrate consumers, add audience filtering, start Community Activities, or reopen mobile nav polish.

## 14. Source-of-Truth Transition Phases

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
- CS-H.8: integrated membership request flow checkpoint. Completed.
- CS-H.9: membership request UX hardening. Completed.
- CS-H.10: CMS hardening checkpoint. Completed.
- Historical/superseded later step: migrate selected consumers from `Profile.small_group` to membership. The approved consumer migrations and field removals have since completed for the current migrated surfaces.

Historical rule: no hard cutover should happen early. Current state reflects the later approved cutover/removal slices, not an early unapproved cutover.

## 15. Historical Risks

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

Mitigation direction at the CS-H.3 planning point:
- keep legacy behavior during coexistence
- use explicit mapping rather than name matching
- make seeding idempotent
- require admin approval before active membership
- separate membership from permissions and serving
- add one consumer at a time only after tests

Current note: the coexistence risks were addressed consumer-by-consumer; legacy
fields/tables named above are no longer current runtime authorities.

## 16. Historical Non-Goals

CS-H.3/CS-H.3B/CS-H.3C did not include:
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

These are historical non-goals for the early mapping slices; later approved
slices replaced or removed those fields/models where current docs say they are
retired.

## 17. Historical / Resolved Decisions

Historical/resolved decisions:
- mapping FK vs mapping table was resolved for the bridge period, then superseded by legacy table retirement.
- exact `unit_type` naming was resolved in the implemented `ChurchStructureUnit` model.
- request routing prefers active leaf small-group/fellowship units plus "Not sure / New visitor" unless a later product slice says otherwise.
- requested-unit capture and approval use `ChurchStructureMembership` rows rather than making `Profile.small_group` the current source.
- approval capability and staff/superuser override rules were implemented in the membership request workflow.
- approved membership no longer syncs `Profile.small_group`; the sync was retired and the field removed.
- `/studies/` migration was answered by the Bible Study V2 membership/audience-row migration.
- transfers and orphan/seed issues are historical setup concerns unless reopened by a new migration slice.
- active-root enforcement belongs to the current `ChurchStructureUnit` setup policy, not to legacy table coexistence.

Historical recommendation:
- long-term source of truth: `ChurchStructureUnit` + `ChurchStructureMembership`
- short-term runtime source of truth at CS-H.3 time: current legacy models
- mapping: explicit nullable FK fields, added in CS-H.3B
- seeding: explicit dry-run/apply management command, added in CS-H.3C
- data QA: production/staging seeded structure QA closed in CS-H.3E
- signup: requested unit plus admin approval, never direct final self-assignment
