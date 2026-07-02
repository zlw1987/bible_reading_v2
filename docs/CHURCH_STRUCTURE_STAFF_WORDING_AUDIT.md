# Church Structure Staff Wording Audit

Task: CS-UX.AUDIT.1

## 1. Purpose and Status

This is a docs-only wording audit for the completed Church Structure staff surfaces. It inventories remaining technical or awkward staff-facing wording and proposes small, separately approvable cleanup slices.

No code, template, CSS, test, schema, migration, data, permission, or runtime behavior change is made or authorized by this document. No implementation slice is marked complete here.

Audited context:

- `templates/base.html`
- `templates/accounts/staff/overview.html`
- `templates/accounts/staff/structure_map.html`
- `templates/accounts/staff/structure_mapping_review.html`
- `templates/accounts/staff/structure_mapping_edit.html`
- `accounts/views.py` context strings and comments for the staff structure surfaces
- `docs/CHURCH_STRUCTURE_MAP_AND_SETUP_READINESS_PLAN.md`
- `docs/POST_PILOT_BACKLOG_TRIAGE.md`
- `docs/UI_UX_GUARDRAILS.md`

## 2. Historical Product Boundary Summary

These were the boundaries when this wording audit was written. The active
runtime statements in this list are preserved as historical audit context;
current architecture belongs in the current-state docs named above.

- `ChurchStructureMembership` is not a runtime visibility source.
- Ordinary user visibility still mainly uses `Profile.small_group` and legacy mapping behavior.
- ServiceEvent audience rows govern ordinary-user visibility only when `ServiceEventAudienceScope` rows exist; ServiceEvents with zero audience rows still use legacy fallback fields.
- Bible Study Schedule selected structure units resolve to legacy `SmallGroup` rows for meeting generation; ordinary visibility still uses `Profile.small_group`.
- Broad structure unit lifecycle edit is not approved.
- Historical at this audit point: membership roster management was not approved.
  Current narrow state: GROUP-MEMBERSHIP-MANAGE.1A and
  GROUP-MEMBERSHIP-REQUEST.1B are complete and QA-passed for small-group My Units
  add/end and pending-request approve/reject. Broad transfer/bulk/history tooling
  remains deferred.
- Community Activities is not part of this audit.

## 3. Wording Inventory

| Current term | Where it appears or likely appears | Why it may confuse non-technical church staff | Safer EN wording | Safer ZH wording | Safe to change now? |
| --- | --- | --- | --- | --- | --- |
| Legacy | Mapping review/edit docs and staff copy, especially "legacy record" | Sounds obsolete or broken, and can make staff think the record should be deleted rather than treated as the current operational data. | Existing record / current ministry data | 现有记录 / 当前事工资料 | Yes, if limited to visible staff copy. Keep internal docs/code names unchanged. |
| legacy record | Mapping review table header and explanatory copy | Developer transition wording; staff may not know it means Ministry Context, District, or Small Group rows currently in use. | Current record | 现有记录 | Yes, for visible labels. |
| Current record | Mapping edit detail card | Better than "legacy record," but still generic unless paired with record type. | Current record | 现有记录 | Safe as-is; optional refinement to "Current ministry record" / "现有事工记录" where space allows. |
| structure unit | Structure map, mapping review/edit, setup checks | Reasonable staff shorthand, but abstract without "church" or hierarchy context. | Church structure unit / church structure item | 教会结构单元 | Yes, but keep labels compact. |
| ChurchStructureUnit | Docs, view comments, model/admin references | Raw model name is not staff-friendly and should not appear in ordinary UI. | Church structure unit | 教会结构单元 | Yes for visible UI; no broad model/code rename. |
| mapping | Mapping review/edit, setup readiness indicators | Can sound technical; staff may not know it means linking existing records to the structure tree. | Link / data link / setup link | 对应关系 / 资料对应 | Yes, but preserve "mapping" in technical docs where clarity requires it. |
| setup mapping | Mapping edit notice and review copy | Indicates safety boundary, but still technical. | Setup link / setup data link | 设置对应关系 | Safe follow-up; avoid implying it changes members or visibility. |
| current data mapping | `/staff/structure/` map row meta and indicators | Accurate, but a little database-like; may be read as all current church data. | Linked current data | 已关联的当前资料 | Yes, for visible staff wording. |
| associated structure unit | Possible staff/admin explanatory wording | Vague relationship; staff may not know whether association changes membership, visibility, or setup only. | Linked church structure unit | 已对应的教会结构单元 | Yes if found in visible copy. |
| Mapped structure unit | Mapping review/edit labels | Operationally accurate, but "mapped" is technical and can hide the staff task. | Linked structure unit | 对应结构单元 / 已对应单元 | Yes, if paired with safety note. |
| holding | Structure setup docs and holding-node concepts | Internal data-seeding concept; may sound like an action queue or member-holding state. | Awaiting placement | 待安排 | Yes for visible UI. Keep technical docs precise when referring to seeded holding nodes. |
| unassigned | Structure map and mapping review status/filter labels | Could mean members are personally unassigned, not that the structure unit is under a temporary setup branch. | Awaiting placement / not placed in final structure | 待安排 / 尚未放入正式结构 | Yes, but do not change data codes. |
| holding/unassigned node | Mapping review filters and status labels | Combines two technical words and makes the tree setup detail too prominent. | Awaiting placement area | 待安排区域 | Yes for staff UI. |
| mapped under holding/unassigned node | Mapping review summary, filters, and row status | Long and technical; staff may not know whether it is a warning, error, or temporary setup condition. | Linked to awaiting-placement area | 已对应到待安排区域 | Yes as a small wording slice. |
| type mismatch | Mapping review warnings and filters | Concise for admins, but staff may not know what "type" refers to. | Record and unit types do not match | 记录类型与单元类型不一致 | Yes; keep summary compact as "Type mismatch" only if explanatory text remains nearby. |
| duplicate active mapping | Mapping review warnings and filters | Technical database phrasing; staff may not know duplicate among which records. | More than one active record uses this unit | 多条启用记录对应同一单元 | Yes; update tests if they assert exact labels. |
| runtime | Staff overview and structure map boundary panels | Developer architecture term; staff need to know what currently decides matching/visibility, not "runtime." | How this works today / current operating data | 目前的运作方式 / 当前使用的资料 | Yes, but boundary must stay explicit. |
| runtime boundary | Staff overview and structure map panel title | Important concept, but too architecture-facing for staff page headings. | How this works today | 目前的运作方式 | Yes for UI; docs can retain "runtime boundary." |
| visibility | Structure map/edit notices and docs | Technical permission/audience word; useful to staff but clearer as "who can see content." | Who can see content | 谁可以看到内容 | Yes; already partly used in mapping review. |
| covered members | Structure map tree count and docs | Could imply care coverage or ministry responsibility rather than descendant-inclusive membership count. | Members in this unit and below | 本单元及下级成员 | Yes; keep a short explanatory note near counts. |
| 教会结构单位 | Mapping edit empty state | "单位" is understandable but less consistent with existing "单元"; can sound bureaucratic. | Church structure unit | 教会结构单元 | Yes; standardize to `教会结构单元`. |
| 教会结构单元 | Structure map/review/edit | Best current Chinese term for this concept; still benefits from nearby plain-language help. | Church structure unit | 教会结构单元 | Safe as the preferred term. |
| 当前运行边界 | Staff overview and structure map panels | Literal architecture wording; not natural for staff. | How this works today | 目前的运作方式 | Yes. |
| 目前的运作方式 | Proposed safer wording | Natural staff-facing replacement for runtime boundary. | How this works today | 目前的运作方式 | Safe preferred term. |
| 当前资料对应 | Structure map row meta | Understandable but compact; may not explain that it means existing ministry/district/group data. | Linked current data | 已关联的当前资料 | Yes. |
| 对应结构单元 | Mapping review/edit labels | Usable but abstract; staff may need a linked/current-data frame. | Linked structure unit | 对应结构单元 / 已对应单元 | Safe, with explanatory copy. |
| 未分配暂存节点 | Structure map/review labels | Very technical; "node" and "holding" are setup implementation terms. | Awaiting placement area | 待安排区域 | Yes, as CS-UX.1B. |
| 类型不匹配 | Mapping warnings | Clear to technical staff, but can be more actionable. | Record and unit types do not match | 记录类型与单元类型不一致 | Yes. |
| 重复的启用对应 | Mapping warnings | Accurate but stiff; could be made more explicit. | More than one active record uses this unit | 多条启用记录对应同一单元 | Yes. |
| 覆盖成员 | Structure map count | May imply pastoral coverage, responsibility, or care assignment. | Members in this unit and below | 本单元及下级成员 | Yes. |

## 4. Recommended Terminology Table

| Concept | Recommended EN | Recommended ZH | Notes |
| --- | --- | --- | --- |
| Current operational legacy row | Current record | 现有记录 | Prefer over "legacy record" in UI. |
| Church structure tree item | Church structure unit | 教会结构单元 | Do not expose `ChurchStructureUnit` in visible UI. |
| Link from current data to unit tree | Setup link / data link | 设置对应关系 / 资料对应 | Use "mapping" only where staff are already on the mapping page or docs need precision. |
| Runtime boundary panel | How this works today | 目前的运作方式 | Replace architecture heading while preserving boundary text. |
| Holding/unassigned area | Awaiting placement area | 待安排区域 | Avoid "holding/unassigned node" in visible copy. |
| Mapped active state | Linked to active unit | 已对应到启用单元 | Existing label is acceptable; "linked" may read warmer in EN. |
| Unmapped state | Not linked yet | 尚未对应 | More actionable than "unmapped." |
| Needs-review aggregate | Needs review | 需要检查 | Keep as status/filter wording. |
| Type mismatch | Record and unit types do not match | 记录类型与单元类型不一致 | Use full phrase in row status or help text; compact filter label may stay if space is tight. |
| Duplicate active mapping | More than one active record uses this unit | 多条启用记录对应同一单元 | Prefer explanatory wording in help/status; compact table heading may need shorter copy. |
| Warning group | Conflict / warning | 冲突／警告 | Current term is acceptable when explanatory text remains nearby. |
| Covered-member count | Members in this unit and below | 本单元及下级成员 | Avoid implying care/serving coverage. |
| Visibility | Who can see content | 谁可以看到内容 | Preferred in staff safety notes. |

## 5. Proposed Future Cleanup Slices

### CS-UX.1B - Holding/unassigned Wording Cleanup

Scope:

- Replace visible "holding/unassigned node" language on `/staff/structure/` and `/staff/structure/mappings/` with "awaiting placement area" wording.
- Standardize Chinese visible wording from `未分配暂存节点` / `未分配暂存` to `待安排区域` or another approved church-staff phrase.
- Keep seeded codes such as `UNASSIGNED-DISTRICTS` and `UNASSIGNED-GROUPS` unchanged.

Files likely affected:

- `templates/accounts/staff/structure_map.html`
- `templates/accounts/staff/structure_mapping_review.html`
- Focused tests that assert the visible labels, if present.

Risk level: Low.

Tests likely needed:

- Targeted staff structure map and mapping review tests that confirm the new EN/ZH labels render.
- `git diff --check`, `manage.py check`, and `makemigrations --check` if templates/tests are edited.

Explicit non-goals:

- No data-code rename.
- No seeding command change.
- No tree movement, unit lifecycle edit, mapping behavior change, membership change, or runtime visibility change.

### CS-UX.1C - Mapping Review/Edit Explanatory Copy Cleanup

Scope:

- Replace "legacy record" visible labels with "Current record" / `现有记录`.
- Tune "mapping" copy where staff need a simpler action frame, while preserving that edits only update the setup/data link.
- Make type mismatch and duplicate active mapping explanations more explicit.
- Standardize `教会结构单位` to `教会结构单元` where visible.

Files likely affected:

- `templates/accounts/staff/structure_mapping_review.html`
- `templates/accounts/staff/structure_mapping_edit.html`
- Targeted mapping review/edit tests.

Risk level: Low to medium, because exact-label tests may need updates.

Tests likely needed:

- Mapping review page renders the new headers, filters, warning copy, and row statuses.
- Mapping edit page renders the new empty/current mapped-unit copy in EN/ZH.
- Existing permission and POST validation tests should remain behavior-focused and unchanged unless they assert exact copy.

Explicit non-goals:

- No POST behavior change.
- No permission change.
- No duplicate/type validation change.
- No model/admin/code variable rename.
- No mapping source-of-truth change.

### CS-UX.1D - Structure Map Setup-Readiness Wording Cleanup

Scope:

- Retitle "Current Runtime Boundary" to a staff-facing phrase such as "How this works today" / `目前的运作方式`.
- Replace "covered members" with a clearer descendant-inclusive count label.
- Tune setup-readiness indicators so staff can tell which counts are setup checks, not direct action queues.
- Preserve the current warning that approved memberships do not decide ordinary visibility.

Files likely affected:

- `templates/accounts/staff/overview.html`
- `templates/accounts/staff/structure_map.html`
- Targeted staff overview and structure map tests, if they assert copy.

Risk level: Low.

Tests likely needed:

- Staff overview renders the new boundary heading and keeps the current-source explanation.
- Structure map renders setup indicators, tree rows, and count labels in EN/ZH.
- No behavior assertions should change.

Explicit non-goals:

- No count semantics change.
- No membership roster UI.
- No structure lifecycle UI.
- No audience, ServiceEvent, Bible Study, reading progress, My Serving, or `Profile.small_group` behavior change.

### CS-UX.1E - Staff Navigation IA Follow-up

Scope:

- Only if real users still find pages hard to discover after CS-UX.1A, review whether staff navigation labels and grouping make `/staff/structure/`, `/staff/structure/mappings/`, membership requests, and Django Admin links easy to find.
- Keep this as a navigation wording/information-architecture pass, not a workflow redesign.

Files likely affected:

- `templates/base.html`
- `templates/accounts/staff/overview.html`
- Possibly staff navigation tests if exact labels are asserted.

Risk level: Medium, because navigation affects multiple staff workflows and could conflict with parallel UI cleanup work.

Tests likely needed:

- Targeted staff navigation/overview rendering tests.
- Manual browser/mobile QA for staff navigation if templates/CSS are changed.

Explicit non-goals:

- No new staff workflow.
- No permission expansion.
- No dashboard redesign.
- No Community Activities link or implementation.
- No broad IA rewrite without fresh user evidence.

## 6. Do-Not-Change List

Future wording cleanup slices must not include:

- No model/schema/migration change.
- No runtime visibility change.
- No audience behavior change.
- No `Profile.small_group` change.
- No membership-driven visibility.
- No broad setup/edit UI.
- No structure unit create/move/deactivate UI.
- No member roster UI.
- No Community Activities.
- No model, database-field, or Python variable rename just to improve staff wording.
- No source-of-truth change for ServiceEvent, Bible Study, Reading Progress, My Serving, or existing legacy consumers.

## 7. Suggested Review Order

Recommended sequence:

1. CS-UX.1B, because holding/unassigned wording is the most awkward visible phrase and can be changed without touching behavior.
2. CS-UX.1C, because mapping review/edit copy carries the highest risk of staff misunderstanding what an edit does.
3. CS-UX.1D, because the structure map/overview boundary language should be friendlier but must preserve architectural clarity.
4. CS-UX.1E only after user feedback shows navigation discovery remains a real problem.

This document is an audit and slice proposal only. Each slice needs separate approval before implementation.
