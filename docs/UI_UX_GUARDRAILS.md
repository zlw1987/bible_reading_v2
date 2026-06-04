# UI/UX Guardrails

## 1. Purpose

This document defines compact UI/UX guardrails for normal-user and staff/admin surfaces. It is guidance only. It does not redesign the product, change runtime behavior, introduce new models, migrate consumers, add audience filtering, or start Community Activities.

## 2. Normal-User UI Rules

Normal-user pages should feel pastoral, clear, and task-oriented. Users should not need to understand the database or implementation history to sign up, update a profile, read, pray, study, or serve.

Rules:
- Do not expose internal model names, IDs, codes, enum values, field names, or implementation terms in normal-user copy.
- Labels must describe user intent, not database objects. Prefer "Your small group" over "Profile.small_group" and "Which group do you attend?" over "Select ChurchStructureUnit."
- Chinese wording must use natural church/user language, not literal technical translation. Prefer phrases like "我参加的小组", "所属团契/小组", "不确定/新朋友", and "请同工协助确认" when they fit the workflow.
- Dropdown choices must use clean display names. Do not show raw codes, slugs, primary keys, enum values, or legacy/foundation labels.
- Help text should explain what the user is choosing and why it matters, without naming implementation details.
- Empty states and validation messages should be kind, specific, and actionable.
- Mobile-first layout is required: primary actions visible without horizontal scrolling, readable labels, accessible tap targets, stacked form controls, and no table-only workflows for ordinary users.

## 3. Staff/Admin UI Rules

Staff/admin surfaces may expose more operational and technical context when it helps staff make safe decisions, audit data, or understand transition state.

Rules:
- Technical context should still be purposeful. Do not expose raw implementation detail when a clear operational label is enough.
- Clearly distinguish current legacy runtime models from future foundation models whenever both appear in the same staff/admin surface or documentation.
- Current runtime structure includes `MinistryContext`, `District`, `SmallGroup`, and `Profile.small_group`.
- Future foundation structure includes `ChurchStructureUnit` and `ChurchStructureMembership`.
- Staff labels should make transition state explicit, for example "Current runtime small group" versus "Future foundation membership."
- Do not imply that future foundation models are already runtime sources of truth until consumers have intentionally migrated.

## 4. Bilingual Copy Rules

English and Chinese labels must be reviewed together. The Chinese copy should match the same user intent, tone, and workflow meaning as the English copy.

Rules:
- Avoid literal technical translation. Translate the user's task and church context, not the database name.
- Review EN/ZH dropdown labels as a pair so choices remain equivalent and naturally understandable.
- Keep both languages short enough for mobile forms and buttons.
- Avoid mixing internal English terms into Chinese copy unless the term is already familiar to the church community.

## 5. Mobile QA Checklist

Before shipping normal-user or staff/admin UI changes, verify on mobile width:
- Signup: labels, dropdown choices, help text, validation, and submit flow are readable and user-facing.
- Profile: group/church affiliation wording is natural, non-technical, and does not expose internal model names.
- Staff list/detail pages: tables, filters, badges, and detail fields fit mobile screens or degrade into usable stacked layouts.
- Forms and dropdowns: choices use clean display names, tap targets are comfortable, selected values wrap cleanly, and errors remain visible near the relevant field.

## 6. Reusable Codex Prompt Snippet

Use this snippet in future Codex tasks that touch normal-user pages:

```text
Apply the CMS UI/UX guardrails for normal-user pages. Do not expose internal model names, IDs, codes, enum values, or implementation terms. Labels must describe user intent, not database objects. EN/ZH copy must be reviewed together, with natural church/user Chinese wording rather than literal technical translation. Dropdown choices must use clean display names. Keep the layout mobile-first with readable labels, accessible tap targets, stacked controls, and no horizontal scrolling.
```

## 7. Non-Goals

This document does not authorize:
- Redesigning the product.
- Migrating to a new CSS framework.
- Implementing features.
- Starting church structure implementation.
- Migrating runtime consumers.
- Adding audience filtering.
- Starting Community Activities.
