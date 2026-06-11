# ServiceEvent Audience Selector Interaction Plan

## 1. Purpose and Status

SE-AS.5A is the docs-only interaction plan for the SE-AS.5 staff audience selector UI. SE-AS.5 is now implemented against this contract.

Status: SE-AS.5A planning is complete, SE-AS.5 implementation is complete, SE-AS.5B post-commit UI/wording cleanup is complete, and SE-AS.5C corrects the picker interaction model. ServiceEvent single create/edit and recurring create now expose the optional `ChurchStructureUnit` audience picker as a visible section; the tree nodes inside the picker expand/collapse by hierarchy level. Staff detail shows effective audience source and readable labels; empty selections keep legacy fallback behavior. No schema/model field change, migration, data backfill, Community Activities, CS-MAP.3, CS-SETUP.1, `ChurchStructureMembership` visibility migration, or ministry scheduling behavior change was added.

Current local baseline:

- SE-AS.4 is complete: if a `ServiceEvent` has one or more `ServiceEventAudienceScope` rows, those rows govern ordinary-user visibility.
- If a `ServiceEvent` has zero audience rows, ordinary-user visibility falls back to legacy `scope_type` / `district` / `small_group` plus `Profile.small_group`.
- `ChurchStructureMembership` does not grant ServiceEvent visibility.
- The SE-AS.5 staff selector UI/display now exists; SE-AS.6 backfill remains future.

## 2. Current Surfaces to Extend in SE-AS.5

Single ServiceEvent create:

- Add the `ChurchStructureUnit` audience picker to the staff create form.
- Place it in a new audience section before or near the existing legacy `scope_type` / `district` / `small_group` controls.
- The picker is optional. Empty selection means the event uses legacy fallback fields.

Single ServiceEvent edit:

- Add the same picker to the staff edit form.
- Preselect existing `ServiceEventAudienceScope` rows when present.
- If no audience rows exist, leave the picker empty so staff can see that the event is still governed by fallback settings.
- Do not auto-convert legacy fields into saved audience rows on edit. Staff must explicitly select units and save.

Recurring/batch ServiceEvent create:

- Add the same picker to the recurring create form.
- One selected audience set applies to every event created by that batch.
- If the picker is empty, every created event uses the legacy fallback fields selected in the same form.
- Preview should show the selected audience source in SE-AS.5 if practical, but no automatic backfill or per-event audience variation is part of the interaction.

Staff/admin detail display:

- Add a management-only effective audience display on the existing ServiceEvent detail management section.
- Show whether the event is governed by `Structure audience` or `Legacy fallback audience`.
- Show readable selected unit labels for structure-governed events.
- Show readable legacy fallback labels for fallback-governed events.
- Do not show database IDs, model names, unit codes, or architecture/source-of-truth language in staff-facing event pages unless a future admin-only diagnostics surface explicitly needs it.

Ordinary detail display:

- Ordinary users should not see architecture details such as `Structure audience`, `Legacy fallback audience`, `ServiceEventAudienceScope`, or fallback fields.
- If any ordinary-facing audience label is shown, it should be a simple readable label such as `For: Whole Church` / `适用：全教会` or a compact unit label with the root prefix omitted.
- Ordinary detail display is optional for SE-AS.5. Visibility itself already proves that the ordinary user is allowed to see the event.

## 3. Interaction With Legacy Fields

The new picker and legacy fields are not combined filters.

- If one or more structure audience units are selected and saved, `ServiceEventAudienceScope` rows control ordinary-user visibility.
- When audience rows exist, legacy `scope_type` / `district` / `small_group` remain stored fallback settings only. They do not further narrow or expand visibility.
- If the picker is empty and the event has zero audience rows, legacy `scope_type` / `district` / `small_group` control ordinary-user visibility exactly as they do after SE-AS.4.
- Clearing all selected units on an event that had audience rows should return that event to legacy fallback behavior, subject to explicit SE-AS.5 form validation and confirmation copy.
- Legacy validation still matters: the fallback fields must remain internally consistent because they become active whenever the picker is empty.

Recommended legacy-field decision for SE-AS.5:

- Keep `scope_type`, `district`, and `small_group` editable.
- Visually group and label them as `Used when no structure audience is selected` / `未选择上方范围时使用（旧版）`.
- Do not delete, deprecate, hide permanently, migrate away from, or make schema changes to these fields in SE-AS.5.
- Do not run data migration or automatic backfill as part of SE-AS.5.

## 4. Staff Wording

The staff UI should use direct operational wording:

- Picker label: `Audience Scope` / `适用范围`.
- Picker help text after SE-AS.5B: `Selected units control which ordinary users can see this gathering. Leave this empty to use the Whole Church / District / Small Group settings below.` / `选择的教会结构单元会决定普通用户能否看到这个聚会。留空则使用下方的全教会 / 区 / 小组设置。`
- Fallback group heading after SE-AS.5B: `Used when no structure audience is selected` / `未选择上方范围时使用（旧版）`.
- Fallback group help text after SE-AS.5B: `If no structure unit is selected above, the event uses these Whole Church / District / Small Group settings. Once structure units are selected, these fields are kept only as fallback records and are not an extra filter.` / `如果上方没有选择任何教会结构单元，系统会使用这里的全教会 / 区 / 小组设置。上方一旦有选择，这里只作为备用记录，不会再额外筛选。`
- Effective audience source, structure-governed: `Visibility source: Structure audience` / `可见范围来源：教会结构适用范围`.
- Effective audience source, fallback-governed: `Visibility source: Legacy fallback audience` / `可见范围来源：备用适用范围`.

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
- `ChurchStructureMembership` grants ServiceEvent visibility.

## 5. Effective Audience Display

Staff display:

- Always show the effective source when the viewer has management/coverage access.
- For structure-governed events, show selected unit labels in compact, readable form. Use the same root-stripped style as the Bible Study audience display where possible.
- For fallback-governed events, show a clear fallback label such as `Whole Church`, `District: North`, or `Small Group: Caleb Group`.
- If selected units resolve to no ordinary users because they are custom/unmapped, show a staff warning or preview in SE-AS.5 implementation.

Ordinary display:

- Keep copy simple and pastoral.
- Do not expose unit codes, IDs, model names, fallback/source-of-truth wording, or implementation terms.
- Prefer no ordinary audience display unless the product need is clear. If shown, use `For` / `适用` labels with readable unit names only.

## 6. Empty and Unmapped Selections

Empty selector:

- Empty on create means save zero audience rows and use legacy fallback.
- Empty on edit for an event that already has zero audience rows keeps legacy fallback.
- Clearing all units on edit for an event that previously had rows should delete those rows and return the event to legacy fallback, with clear staff copy in SE-AS.5.

Custom or unmapped unit selected:

- A selected active custom/unmapped `ChurchStructureUnit` is valid.
- It may match no ordinary users because SE-AS.4 still resolves selected units through legacy `SmallGroup` mapping and `Profile.small_group`.
- Staff should get a clear warning or preview in SE-AS.5 implementation, such as `This selection currently matches no ordinary users because it is not mapped to active legacy groups.` / `此选择目前没有匹配到普通用户，因为它尚未映射到启用的小组。`
- SE-AS.5 implements this as a staff detail warning when selected units currently resolve to no active legacy groups.

## 7. Recurring/Batch Create

Recurring create should behave as one shared event template:

- The staff-selected structure audience set applies to all created events in the batch.
- If the picker is empty, all created events use the batch's legacy fallback fields.
- The batch preview may summarize the audience source, but it must not create rows during preview.
- Creating the batch saves audience rows only for newly created events when staff selected units.
- Existing skipped duplicate events are not backfilled or modified.
- No automatic backfill from legacy fields into audience rows is included.

## 8. SE-AS.5 Implementation Notes

Implemented shape:

- Reuse `templates/shared/_church_structure_unit_audience_picker.html`.
- SE-AS.5C removes the collapsed outer picker shell from ServiceEvent create/edit and recurring create. The `Audience Scope` / `适用范围` label, help text, search input, selected chips, and root-level tree rows are visible immediately.
- The picker tree uses node-level hierarchy controls: root-level units show by default; child levels are revealed by expanding their parent; selected descendant paths expand on edit or validation re-render; search shows matching rows and their ancestor path. Without JavaScript, the server-rendered checkbox tree remains visible and usable.
- Add a ServiceEvent-specific optional `audience_units` field/helper pattern parallel to `BibleStudySeriesForm`; unlike Bible Study Schedule, ServiceEvent keeps empty-picker fallback behavior instead of requiring the picker.
- Save selected units through `ServiceEventAudienceScope` rows in the same transaction as the event save. Edit replaces rows atomically; clearing all units deletes rows and restores fallback.
- Prefetch `audience_scope_links__unit` for detail/list surfaces that display effective audience.
- Add template filters/helpers for compact structure audience labels and fallback labels; ordinary-facing detail still does not show audience architecture details.
- Add a staff detail warning when selected structure units currently resolve to no active legacy small groups.
- Add targeted tests for create, edit, clear-to-fallback, recurring create, effective display source, ordinary detail non-exposure, runtime visibility, and the boundary that ministry scheduling concepts are unchanged.

SE-AS.6 backfill remains future and separately approved.

## 9. Explicit Non-Goals

SE-AS.5A and the later SE-AS.5 selector implementation must not include:

- SE-AS.6 backfill command.
- Community Activities.
- CS-MAP.3.
- CS-SETUP.1.
- Migration to `ChurchStructureMembership`.
- Deprecation, deletion, hiding as obsolete, or schema removal of `scope_type`, `district`, or `small_group`.
- Data migration or automatic audience-row backfill.
- Changes to `ServiceEvent.ministry_context` beyond preserving Host / Language Label wording.
- Changes to Required Ministry Teams.
- Changes to Rotation Anchor Team.
- Changes to TeamAssignment.
- Changes to My Serving.
- New permission matrix work.
- New notifications, attendance, availability, swaps, reminders, checklist, or automatic scheduling.

## 10. SE-AS.5 Completion Decision

SE-AS.5 is complete using this interaction contract:

- Picker appears on single create, single edit, and recurring create.
- The picker section stays visible on those forms; hierarchy tree nodes collapse/expand by level, with root rows visible by default and selected ancestor paths expanded on edit.
- Staff detail shows effective audience source and readable labels.
- Ordinary detail either omits audience display or shows only simple readable labels.
- Legacy fields remain editable as fallback settings.
- Empty picker means legacy fallback.
- Selected structure units govern visibility and are not combined with legacy fields.
- Recurring create applies one selected audience set to all created events.
- No backfill, migration, deprecation, Community Activities, CS-MAP.3, CS-SETUP.1, membership visibility migration, or ministry scheduling behavior changes are included.
