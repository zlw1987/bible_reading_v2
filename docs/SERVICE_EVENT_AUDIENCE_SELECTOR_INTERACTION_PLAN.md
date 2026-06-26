# ServiceEvent Audience Selector Interaction Plan

## 1. Purpose and Status

SE-AS.5A is the docs-only interaction plan for the SE-AS.5 staff audience selector UI. SE-AS.5 is now implemented against this contract.

Status: SE-AS.5A planning is complete, SE-AS.5 implementation is complete, SE-AS.5B post-commit UI/wording cleanup is complete, and SE-AS.5C corrects the picker interaction model. ServiceEvent single create/edit and recurring create now expose the optional `ChurchStructureUnit` audience picker as a visible section; the tree nodes inside the picker expand/collapse by hierarchy level. Staff detail shows effective audience source and readable labels. SE-AS.7A later superseded the SE-AS.5 empty-selection write behavior: normal writes now convert valid legacy fallback fields into structure audience rows or fail validation. SE-RETIRE.1B later retired the runtime zero-row fallback, so zero-row events fail closed for ordinary users. No schema/model field deletion, migration, Community Activities, CS-MAP.3, CS-SETUP.1, or ministry scheduling behavior change was added by the selector work.

Current-state supersession: SE-FIELD-RETIRE.1A later removed the legacy
`scope_type` / `district` / `small_group` fields, and
SERVICE-EVENT-CONTEXT.1C removed `ServiceEvent.ministry_context`. Body text below
that places the picker beside editable legacy fallback controls is historical
selector-era context; current ServiceEvent visibility is audience rows plus active
primary membership, and zero-row events fail closed for ordinary users.

Current local baseline:

- SE-AS.4 is complete: if a `ServiceEvent` has one or more `ServiceEventAudienceScope` rows, those rows govern ordinary-user visibility.
- CS-CORE.2B-A later switched audience-row matching to active primary `ChurchStructureMembership`.
- SE-AS.7A later stopped normal create/edit/recurring writes from saving new zero-row fallback events.
- SE-RETIRE.1B later retired the zero-row runtime fallback: if a `ServiceEvent` has zero audience rows, ordinary-user visibility fails closed.
- The SE-AS.5 staff selector UI/display exists; SE-AS.6C backfill/apply and SE-RETIRE.1B fallback retirement are complete.

## 2. Current Surfaces to Extend in SE-AS.5

Single ServiceEvent create:

- Add the `ChurchStructureUnit` audience picker to the staff create form.
- Place it in a new audience section before or near the existing legacy `scope_type` / `district` / `small_group` controls.
- The picker is optional in the UI. Since SE-AS.7A, an empty selection is converted from the legacy fields into a structure audience row when a valid mapping exists, or validation fails.

Single ServiceEvent edit:

- Add the same picker to the staff edit form.
- Preselect existing `ServiceEventAudienceScope` rows when present.
- If no audience rows exist, leave the picker empty so staff can see the invalid/safety state; ordinary users will fail closed after SE-RETIRE.1B.
- Since SE-AS.7A, saving with an empty picker converts valid legacy fields into saved audience rows or rejects the save when mapping is missing/inactive/ambiguous.

Recurring/batch ServiceEvent create:

- Add the same picker to the recurring create form.
- One selected audience set applies to every event created by that batch.
- Since SE-AS.7A, if the picker is empty, every newly created event converts the selected legacy fallback fields into structure audience rows when the mapping is valid, or the save is rejected.
- Preview should show the selected audience source in SE-AS.5 if practical, but no automatic backfill or per-event audience variation is part of the interaction.

Staff/admin detail display:

- Add a management-only effective audience display on the existing ServiceEvent detail management section.
- Show whether the event is governed by `Structure audience` or is in the zero-row fail-closed safety state.
- Show readable selected unit labels for structure-governed events.
- Show readable legacy stored-field labels only as staff context for zero-row/safety or field-retirement work.
- Do not show database IDs, model names, unit codes, or architecture/source-of-truth language in staff-facing event pages unless a future admin-only diagnostics surface explicitly needs it.

Ordinary detail display:

- Ordinary users should not see architecture details such as `Structure audience`, `Legacy fallback audience`, `ServiceEventAudienceScope`, or fallback fields.
- If any ordinary-facing audience label is shown, it should be a simple readable label such as `For: Whole Church` / `适用：全教会` or a compact unit label with the root prefix omitted.
- Ordinary detail display is optional for SE-AS.5. Visibility itself already proves that the ordinary user is allowed to see the event.

## 3. Interaction With Legacy Fields

The new picker and legacy fields are not combined filters.

- If one or more structure audience units are selected and saved, `ServiceEventAudienceScope` rows control ordinary-user visibility.
- When audience rows exist, legacy `scope_type` / `district` / `small_group` remain stored conversion/display/backfill/audit/rollback context only. They do not further narrow or expand visibility. 
- Since SE-AS.7A, if the picker is empty on save, legacy `scope_type` / `district` / `small_group` are converted into structure audience rows when the mapping is valid, or validation rejects the save. They no longer become an ordinary-user runtime fallback.
- Clearing all selected units on an event that had audience rows should convert the legacy fields into replacement audience rows or reject the save; it must not return the event to ordinary-user legacy fallback behavior.
- Legacy validation still matters because these fields are used as conversion/backfill/display context while they remain stored.

Recommended legacy-field decision for SE-AS.5:

- Keep `scope_type`, `district`, and `small_group` editable.
- Visually group and label them as `Used when no structure audience is selected` / `未选择上方范围时使用（旧版）`.
- Do not delete, deprecate, hide permanently, migrate away from, or make schema changes to these fields in SE-AS.5.
- Do not run data migration or automatic backfill as part of SE-AS.5.

## 4. Staff Wording

The staff UI should use direct operational wording:

- Picker label: `Audience Scope` / `适用范围`.
- Picker help text after SE-AS.7A: `Selected units control which ordinary users can see this gathering. If left empty, the Whole Church / District / Small Group settings below must map to a valid structure audience.` / `选择的教会结构单元会决定普通用户能否看到这个聚会。若留空，下方的全教会 / 区 / 小组设置必须能对应到有效的教会结构范围。`
- Fallback group heading after SE-AS.7A: `Used to fill an empty structure audience` / `未选择上方范围时用于转换`.
- Fallback group help text after SE-AS.7A: `If no structure unit is selected above, these Whole Church / District / Small Group settings are converted into structure audience rows when a valid mapping exists. Once structure units are selected, these fields are kept only as stored reference and are not an extra filter.` / `如果上方没有选择任何教会结构单元，系统会在对应关系有效时把这里的全教会 / 区 / 小组设置转换成教会结构适用范围。上方一旦有选择，这里只作为保留记录，不会再额外筛选。`
- Effective audience source, structure-governed: `Visibility source: Structure audience` / `可见范围来源：教会结构适用范围`.
- Effective audience source, zero-row safety state: `No structure audience saved` / `尚未保存教会结构适用范围`.

Concept separation wording:

- `Host / Language Label` / `主办/语言标签` remains display-only. It does not control visibility, serving assignment, or permissions.
- `Required Ministry Teams` / `需要的事工团队` are coverage expectations only. They are not audience.
- `Rotation Anchor Team` / `配搭参考团队` is a scheduling/copy-forward hint only. It is not audience.
- `TeamAssignment` / `服事安排` records actual serving assignments. It is not audience.
- `My Serving` / `我的服事` shows a user's serving assignments. It is not audience and should remain independent of ServiceEvent audience visibility.

Avoid staff wording that implies:

- legacy fields are an additional filter when structure rows exist;
- `ministry_context` is audience;
- required teams, rotation anchor, TeamAssignment, or My Serving affect who can see the event;
- `ChurchStructureMembership` is a universal visibility source beyond separately switched consumers.

## 5. Effective Audience Display

Staff display:

- Always show the effective source when the viewer has management/coverage access.
- For structure-governed events, show selected unit labels in compact, readable form. Use the same root-stripped style as the Bible Study audience display where possible.
- For zero-row/safety or field-retirement contexts, show legacy stored-field labels as staff context, not as an active ordinary-user visibility source.
- If selected units resolve to no ordinary users because they are custom/unmapped, show a staff warning or preview in SE-AS.5 implementation.

Ordinary display:

- Keep copy simple and pastoral.
- Do not expose unit codes, IDs, model names, fallback/source-of-truth wording, or implementation terms.
- Prefer no ordinary audience display unless the product need is clear. If shown, use `For` / `适用` labels with readable unit names only.

## 6. Empty and Unmapped Selections

Empty selector:

- Empty on create means convert legacy fields into audience rows when a valid mapping exists, or reject the save.
- Empty on edit for an event that already has zero audience rows remains a fail-closed safety state until staff save valid audience rows or valid convertible legacy fields.
- Clearing all units on edit for an event that previously had rows should convert legacy fields into replacement audience rows or reject the save, with clear staff copy.

Custom or unmapped unit selected:

- A selected active custom/unmapped `ChurchStructureUnit` is valid.
- It may match no ordinary users if no active primary `ChurchStructureMembership` falls under the selected unit.
- Staff should get a clear warning or preview when practical, such as `This selection currently matches no ordinary users.` / `此选择目前没有匹配到普通用户。`
- SE-AS.5 originally implemented a legacy-mapping warning; after CS-CORE.2B-A, the current matching source is active primary membership.

## 7. Recurring/Batch Create

Recurring create should behave as one shared event template:

- The staff-selected structure audience set applies to all created events in the batch.
- If the picker is empty, all created events convert the batch's legacy fallback fields into structure audience rows when valid, or the batch save is rejected.
- The batch preview may summarize the audience source, but it must not create rows during preview.
- Creating the batch saves audience rows for newly created events either from staff-selected units or from valid converted legacy fields.
- Existing skipped duplicate events are not backfilled or modified.
- No broad backfill is included by this interaction slice; SE-AS.6C later handled approved apply/backfill separately.

## 8. SE-AS.5 Implementation Notes

Implemented shape:

- Reuse `templates/shared/_church_structure_unit_audience_picker.html`.
- SE-AS.5C removes the collapsed outer picker shell from ServiceEvent create/edit and recurring create. The `Audience Scope` / `适用范围` label, help text, search input, selected chips, and root-level tree rows are visible immediately.
- The picker tree uses node-level hierarchy controls: root-level units show by default; child levels are revealed by expanding their parent; selected descendant paths expand on edit or validation re-render; search shows matching rows and their ancestor path. Without JavaScript, the server-rendered checkbox tree remains visible and usable.
- Add a ServiceEvent-specific optional `audience_units` field/helper pattern parallel to `BibleStudySeriesForm`; unlike Bible Study Schedule, ServiceEvent supports an optional picker UI, but since SE-AS.7A an empty save converts valid legacy fields into audience rows or fails validation.
- Save selected units through `ServiceEventAudienceScope` rows in the same transaction as the event save. Edit replaces rows atomically; clearing all units converts valid legacy fields into replacement audience rows or rejects the save.
- Prefetch `audience_scope_links__unit` for detail/list surfaces that display effective audience.
- Add template filters/helpers for compact structure audience labels and stored legacy-field context labels; ordinary-facing detail still does not show audience architecture details.
- Add a staff detail warning/preview when selected structure units currently match no ordinary users, where practical. After CS-CORE.2B-A, the matching source is active primary `ChurchStructureMembership`, not legacy small-group resolution.
- Add targeted tests for create, edit, empty/clear converts or rejects, recurring create, effective display source, ordinary detail non-exposure, runtime visibility, and the boundary that ministry scheduling concepts are unchanged.

SE-AS.6C apply/backfill is complete; further legacy-field retirement remains separate.

## 9. Explicit Non-Goals

SE-AS.5A and the later SE-AS.5 selector implementation must not include:

- SE-AS.6 backfill command as part of the original SE-AS.5 selector slice.
- Community Activities.
- CS-MAP.3.
- CS-SETUP.1.
- Migration to `ChurchStructureMembership`.
- Deprecation, deletion, hiding as obsolete, or schema removal of `scope_type`, `district`, or `small_group`.
- Data migration or automatic audience-row backfill as part of the original SE-AS.5 selector slice.
- Changes to `ServiceEvent.ministry_context` beyond preserving Host / Language Label wording.
- Changes to Required Ministry Teams.
- Changes to Rotation Anchor Team.
- Changes to TeamAssignment.
- Changes to My Serving.
- New permission matrix work.
- New notifications, attendance, availability, swaps, reminders, checklist, or automatic scheduling.

## 10. SE-AS.5 Completion Decision

SE-AS.5 is complete using this interaction contract, with later write-path and runtime behavior superseded by SE-AS.7A and SE-RETIRE.1B:

- Picker appears on single create, single edit, and recurring create.
- The picker section stays visible on those forms; hierarchy tree nodes collapse/expand by level, with root rows visible by default and selected ancestor paths expanded on edit.
- Staff detail shows effective audience source and readable labels.
- Ordinary detail either omits audience display or shows only simple readable labels.
- Legacy fields remain editable as stored conversion/display/backfill/audit/rollback context until field-level retirement. They are not an additional filter when structure audience rows exist.
- Since SE-AS.7A, an empty picker save converts valid legacy `scope_type` / `district` / `small_group` fields into `ServiceEventAudienceScope` rows or rejects the save when the mapping is missing, inactive, or ambiguous.
- Since SE-RETIRE.1B, zero-row ServiceEvents fail closed for ordinary users; empty picker behavior no longer restores an ordinary-user legacy runtime fallback.
- Selected structure units govern visibility and are not combined with legacy fields.
- Recurring create applies one selected or converted audience set to all newly created events; skipped duplicate events are not backfilled or modified by recurring create.
- SE-AS.5 itself did not include backfill, schema migration, legacy-field deprecation/removal, Community Activities, CS-MAP.3, CS-SETUP.1, membership visibility migration, or ministry scheduling behavior changes. Later, SE-AS.6C completed approved backfill/apply, SE-AS.7A added the write-path guard, and SE-RETIRE.1B retired the zero-row runtime fallback.
