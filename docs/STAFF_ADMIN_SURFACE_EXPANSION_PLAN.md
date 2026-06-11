# Staff Admin Surface Expansion Plan

## 1. Purpose

PP-SA.1 is a docs-only planning pass for expanding staff/admin surfaces after pilot validation. It inventories the current staff/admin entry points, names staff pain points and information-architecture gaps, and proposes phased work without changing runtime behavior.

This plan does not implement dashboard UI, queues, permissions, migrations, consumer source-of-truth changes, audience filtering, Community Activities, notifications, attendance, announcements, care workflows, file center, mobile nav polish, or broad roadmap rewrites.

## 2. Current Staff/Admin Surface Inventory

### Membership Requests

Current state:
- Signup and Profile can create pending `ChurchStructureMembership(status=requested)` records.
- Staff request review, request detail, approve/reject actions, and narrow `Profile.small_group` approval sync exist.
- Approval sync updates `Profile.small_group` only when the approved active primary unit maps to exactly one active legacy `SmallGroup`.
- Requested, rejected, cancelled, and ended memberships do not grant visibility, permissions, serving assignments, audience eligibility, or runtime access.

Gaps:
- Staff workflow remains narrow and task-specific.
- Needs-clarification handling, transfer history, richer filters, and operational status views remain future.
- Staff may need clearer side-by-side labels for "current runtime small group" and "future foundation membership."

### Reading Plans and Guides

Current state:
- Daily Reading includes reading plans, active plans, plan introduction, reading guide posts, structured passages, check-in, calendar, group progress, reflections, replies, reporting, hiding, and moderation.
- Staff reading plan editor exists.

Gaps:
- Staff lack a consolidated overview of active plans, guide publishing state, recent reflection moderation needs, and group progress health.
- Reading admin tasks can feel split between content setup, visibility/progress review, and moderation.

### Prayer and Reflection Moderation

Current state:
- Prayer V1 supports prayer requests, wall visibility, anonymous display, answered/closed status, comments, reporting, hiding, and moderation.
- Daily Reading supports reflection wall reporting/hiding/moderation.

Gaps:
- Staff do not have a unified moderation queue across prayer and reading reflections.
- Moderation state, reported items, hidden items, and recent activity may require module-by-module inspection.
- Sensitive or pastoral content must not be turned into broad case-management scope.

### Bible Study Schedules, Guides, and Meetings

Current state:
- Bible Study V1/V2 flow includes schedule/series, sessions/guides, Thursday pre-study, Friday study schedule, generated small-group meetings, scope fields, lifecycle fields, and permission-controlled editing.
- `BibleStudySeries` currently acts as the internal Bible Study Schedule model.
- Existing scope behavior still uses current runtime fields and models.

Gaps:
- Staff may need a clearer setup checklist or overview for schedules, guide publishing, generated meetings, and meeting-role coverage.
- Staff IA should separate content editing, schedule lifecycle, generated meeting review, and per-meeting responsibilities.
- Any future scope/audience change must be planned separately and tested before runtime behavior changes.

### ServiceEvent

Current state:
- ServiceEvent Foundation V1 supports generic church events, event type, date/time, location, meeting link, draft/published/completed/cancelled workflow, global/district/small_group scope, and permission-controlled editing.
- Optional `ministry_context` label exists; it is label-only.
- MO-S.2 is complete: staff can select required `MinistryTeam` records when creating, editing, or recurring batch-creating `ServiceEvent` records.
- Required teams are stored through explicit `ServiceEventRequiredTeam` rows; `ministry_team` uses `PROTECT`, so referenced teams should be deactivated rather than deleted.
- MO-S.3 is complete: staff/service-event or team-assignment managers can see read-only assignment coverage on ServiceEvent detail; ordinary event viewers do not see coworker coverage.
- MO-S.4/MO-S.4A is complete: authorized Lead and Coordinator role users can use a team-scoped manual scheduling workspace at `/teams/<team_id>/schedule/` for their own manageable team; staff, superusers, and global assignment managers can schedule any team; `TeamMembership.can_lead` is deprecated/reserved and does not grant scheduling, member-management, or admin permissions.
- MO-S.5A/MO-S.5B is complete: ServiceEvent has an optional rotation anchor scheduling hint, and the team schedule workspace offers limited anchor-based and team-history copy-forward suggestions that prefill the editable form and write only on explicit save.
- SE-AS.1 is complete as docs-only ServiceEvent audience-scope redesign planning.
- SE-AS.2 is complete as a model-only `ServiceEventAudienceScope` data foundation; runtime ServiceEvent visibility still uses legacy `scope_type` / `district` / `small_group` and `Profile.small_group`, `ServiceEventAudienceScope` is not the runtime source of truth, and there is no UI selector or audience filtering yet.

Gaps:
- Staff may need a simple event operations overview for upcoming events, draft events, missing setup fields, and related ministry assignments.
- Current ServiceEvent scope remains legacy-field based and is the runtime source of truth even though the SE-AS.2 `ServiceEventAudienceScope` model now exists. It must not be silently replaced with `ChurchStructureMembership`, the SE-AS.2 audience-scope model, the future SE-AS.5 staff UI selector, audience filtering, the SE-AS.4 ServiceEvent visibility migration, or consumer migration from `Profile.small_group` (numbering per `docs/SERVICE_EVENT_AUDIENCE_RUNTIME_MIGRATION_PLAN.md`).
- ServiceEvent should not become Community Activities, full event management, or scheduling automation without separate planning.

### MinistryTeam / TeamAssignment / My Serving Support

Current state:
- Ministry Operations includes `MinistryTeam`, `TeamMembership`, `TeamAssignment`, `TeamAssignmentMember`, manual ServiceEvent-based assignments, per-member confirmation, Playbook link, non-sensitive assignment notes, and My Serving Page V1.
- Lighting Team pilot data/setup support exists on the generic ministry operations foundation.
- MO-S.2 keeps `ServiceEvent` required teams as event-level expectations, `TeamAssignment` as actual scheduled assignments, and `TeamAssignmentMember` as assigned people plus confirmation.
- Batch-created events share the selected required teams; existing events remain valid with no required teams; already-selected inactive teams remain visible/removable on edit.
- No `TeamAssignment` or `TeamAssignmentMember` is auto-created.
- MO-S.3 adds read-only assignment coverage display. The `TeamAssignment` list is the primary operational coverage surface; assignment detail shows compact event coverage; `/staff/` adds upcoming required-team gap counts. Coverage states include assigned required teams with members, required teams with assignment but no active members, unassigned/missing required teams, and non-required additional assignments. Multiple assigned coworkers display with confirmation status.
- MO-S.4 adds the team-scoped manual scheduling workspace for same-type events. MO-S.4A completes the scheduling semantic cleanup after manual QA, adds the My Serving Teams I manage / 我负责的团队 entry point, defaults the workspace to All event types / 全部类型, and keeps specific event type filtering available. MO-S.5A adds optional rotation anchor metadata; MO-S.5B adds limited preview/edit-first copy-forward suggestions without automatic scheduling.

Gaps:
- Staff may need a compact operations overview for upcoming assignments, unconfirmed assignments, missing members, team setup health, and generic pilot setup status.
- Team membership and serving assignment should remain separate from church structure membership.
- Do not infer serving roles from `ChurchStructureMembership`.

### User / Profile / Group Admin

Current state:
- Accounts includes Profile, password reset support for users without email, staff user admin, `District`, `ChurchRoleAssignment`, capability helpers, and scoped group progress.
- Django Admin clarity distinguishes legacy current-runtime models from future foundation models.

Gaps:
- Staff may need safer non-technical user/profile/group tools that avoid raw Django Admin complexity for common tasks.
- Staff-facing technical labels are acceptable when operationally useful, but normal-user UI must not expose model names, IDs, codes, enum values, or implementation terms.
- Permission assignment, group belonging, and serving assignment need clear separation in staff IA.

## 3. Cross-Cutting Pain Points and IA Gaps

- Staff tasks are spread across module-specific pages and Django Admin.
- Setup health is hard to scan: staff need to know what is draft, pending, incomplete, reported, unconfirmed, or stale.
- Current runtime models and future foundation models coexist, which can confuse staff if labels blur the boundary.
- Membership, permissions, and serving assignments are related in ministry practice but separate in the system.
- Normal-user pages require pastoral, non-technical wording; staff pages may show operational context, but only when it helps staff make safe decisions.
- Mobile staff pages must degrade cleanly from tables into stacked layouts, but this plan does not start mobile nav polish.

## 4. Phased Staff Admin Expansion

### PP-SA.1 Docs Plan Only

Status: this document.

Deliverables:
- Inventory current staff/admin surfaces.
- Identify pain points and IA gaps.
- Define phase boundaries, permission boundaries, and non-goals.
- Record that no runtime behavior changes are authorized.

### PP-SA.2 Staff Dashboard / Read-Only Overview

Status: completed.

Goal:
- Add a read-only staff home that helps authorized staff scan operational health without creating new workflows.

Implemented overview cards or sections:
- Pending membership requests.
- Draft or upcoming Bible Study schedules/guides/meetings.
- Reported or hidden prayer/reflection moderation items.
- Upcoming ServiceEvents.
- Upcoming TeamAssignments and unconfirmed My Serving assignments.
- Basic user/profile/group admin links.

Completion notes:
- Implemented as a permission-protected read-only staff overview at `/staff/`.
- Includes counts and links only for existing workflows.
- Browser/mobile QA was completed via local Chrome Playwright because the in-app browser connector failed.

Boundaries:
- Read-only first.
- Link to existing staff/admin workflows rather than rebuilding them.
- No write actions.
- No schema changes.
- No new workflow states.
- No consumer migration, audience filtering, Community Activities, notifications, attendance, announcements, care workflows, file center, permission matrix expansion, or new dashboard automation.

### PP-SA.3 Membership / Admin Workflow Polish

Goal:
- Improve staff membership request handling and adjacent user/profile/group admin workflows.

Completion notes:
- Completed as staff membership request workflow polish.
- Added a clearer pending queue summary, stronger empty states, clearer detail sections, approval-state/context labels, and staff overview context.
- The detail flow now separates requested group/unit, current runtime small group, future foundation membership, request source/note, and approval state for staff review.
- Browser/mobile QA was completed via headless Chromium fallback because the in-app browser connector failed.

Boundaries:
- Preserved the existing requested-status workflow and existing approve/reject behavior.
- Preserved CS-H.7E exactly-one active mapped legacy `SmallGroup` sync for `Profile.small_group`.
- No schema changes.
- `ChurchStructureMembership` remains separate from permissions and serving assignment.
- `/studies/`, reading progress, `ServiceEvent`, My Serving, and other consumers continue to use legacy runtime behavior until separately authorized.
- Do not treat requested membership as access-granting.
- Did not add audience filtering, Community Activities, notifications, attendance, announcements, care workflows, file center, or permission matrix expansion.

### PP-SA.4 Moderation / Admin Queues

Goal:
- Create focused staff queues for content that already supports report/hide/moderation workflows.

Completion notes:
- Completed as a permission-protected read-only staff moderation queue at `/staff/moderation/`.
- The queue summarizes existing report and hidden states only, linking staff to existing moderation workflows for action.
- Included reported and hidden prayer request categories.
- Included reported and hidden reflection post and reply categories.
- Prayer comment report/hidden categories are shown as not separately tracked by existing data.
- No new moderation actions or states were added.
- Browser/mobile QA was completed via headless Chromium fallback because the in-app browser connector failed.

Boundaries:
- Moderation queues are not pastoral case management.
- No schema changes.
- No sensitive notes.
- Do not add care workflows, announcements, notifications, attendance, private contact imports, or sensitive notes.
- Keep normal-user copy kind and non-technical; staff copy may show moderation state and audit context.
- Did not add file center, Community Activities, audience filtering, consumer migration, or permission matrix expansion.

### PP-SA.5 Ministry Ops Admin Improvements

Status: complete.

Goal:
- Completed as focused read-only ministry ops health indicators on `/staff/`.

Completed scope:
- Shows upcoming ServiceEvents, upcoming TeamAssignments, and unconfirmed assignments.
- Shows read-only health indicators for inactive teams, active teams missing playbook links, display-name-only active members, active teams with no active members, upcoming assignments without active members, and upcoming assignments using inactive teams.
- The aggregate health value is a sum of warning indicator buckets, not a unique problematic-record count. The same object may contribute to multiple indicators.
- Links only to existing ServiceEvent, MinistryTeam, and TeamAssignment workflows.
- Browser/mobile QA: initial headless Chromium QA completed before wording clarification; final wording change should be manually checked if browser automation remains unavailable.

Boundaries:
- Keep models generic; do not add LightingTeam-specific models.
- No schema changes, write actions, new states, availability, swaps, reminders, attendance, checklist, scheduling automation, notifications, Community Activities, audience filtering, consumer migration, file center, care workflows, announcements, or permission expansion.
- Do not infer ministry team assignment or serving permissions from church structure membership.

### CS-MAP.2 Read-Only Church Structure Map / Mapping Health

Status: completed. See `docs/CHURCH_STRUCTURE_MAP_AND_SETUP_READINESS_PLAN.md`.

Completed scope:
- A permission-protected read-only staff page at `/staff/structure/`, linked from `/staff/`, rendering the active `ChurchStructureUnit` hierarchy with bilingual names, counts-only membership/mapping context, and mapping-health / setup-readiness indicators.

Boundaries:
- Follows the PP-SA.2/PP-SA.4/PP-SA.5 read-only staff surface pattern: zero write actions, no schema changes, no new states, links only to existing Django Admin and staff workflows.
- Counts only; no member rosters.
- No runtime visibility change; current visibility still uses legacy scope fields and `Profile.small_group`.
- No setup/edit UI; Django Admin remains the structure write surface during transition.

## 5. Permission and Capability Boundaries

- Staff dashboard access should require an explicit staff/admin capability or existing staff/superuser access, not ordinary membership.
- Membership approval requires a capability separate from being a group member.
- Reading plan/guide editing remains separate from prayer/reflection moderation.
- Bible Study schedule/guide/meeting editing remains permission-controlled and separate from membership approval.
- ServiceEvent editing remains permission-controlled and separate from TeamAssignment management.
- MinistryTeam and TeamAssignment management remain separate from `ChurchStructureMembership`.
- Normal users should not receive staff operational context, internal model names, IDs, codes, enum values, or implementation terms.
- Staff pages may show technical context only when it helps decision-making, audit, or transition safety.

## 6. UI/UX Guardrails Applied

Use `docs/UI_UX_GUARDRAILS.md` as the baseline.

Normal-user UI:
- Do not expose internal model names, IDs, codes, enum values, field names, or implementation terms.
- Use user-intent labels such as "Your small group" rather than `Profile.small_group`.
- Keep EN/ZH copy paired and natural, especially for church/user wording.

Staff/admin UI:
- Clearly distinguish current runtime structure from future foundation structure.
- Current runtime structure includes `MinistryContext`, `District`, `SmallGroup`, and `Profile.small_group`.
- Future foundation structure includes `ChurchStructureUnit` and `ChurchStructureMembership`.
- Use labels such as "Current runtime small group" and "Future foundation membership" when both appear together.
- Do not imply future foundation models are already runtime sources of truth.

## 7. Runtime Source-of-Truth Boundary

This plan does not migrate any consumer from `Profile.small_group` to `ChurchStructureMembership`.

The following remain current-runtime behavior unless separately authorized:
- `/studies/` visibility.
- Reading group progress.
- `ServiceEvent` scope/filter behavior.
- My Serving and `TeamAssignment` support.
- Other consumers that currently use legacy models or `Profile.small_group`.

`ChurchStructureMembership` remains the future foundation for belonging and current staff request workflow data. Requested membership must not grant visibility, permissions, serving assignment, audience eligibility, or runtime access.

## 8. Future Final CMS Scope, Not Started Here

Long-term CMS scope may include staff announcements, notifications, attendance, care workflows, activities operations, resources/file center, finer permission matrix work, dashboards, and additional ministry operations. These remain future product directions, not implementation authorization from PP-SA.1.

This plan specifically does not start:
- Community Activities.
- Audience filtering.
- Notifications.
- Attendance.
- Announcements.
- Care workflows.
- File center.
- Mobile nav polish.
- Dashboard implementation.

## 9. Recommended First Implementation Slice

PP-SA.2 is complete as a read-only staff dashboard overview.

PP-SA.3 is complete as membership/admin workflow polish for the existing staff membership request flow.

PP-SA.4 is complete as a read-only staff moderation queue at `/staff/moderation/`.

PP-SA.5 is complete as read-only ministry ops health indicators on `/staff/`.

MO-S.1 is complete as docs-only ministry scheduling requirements planning in `docs/MINISTRY_SCHEDULING_REQUIREMENTS_PLAN.md`.

MO-S.2 is complete as event required-team implementation.

MO-S.3 is complete as read-only assignment coverage display. Browser automation was blocked; user completed manual QA and accepted the MO-S.3 UI.

MO-S.4 is complete as a team-scoped manual scheduling workspace at `/teams/<team_id>/schedule/`, and MO-S.4A scheduling semantic cleanup is complete after manual QA. Team detail shows the contextual Schedule Team / 安排团队服事 link only for users who can manage that team's assignments. Staff, superusers, and global assignment managers can schedule any team; Lead and Coordinator role users can schedule their own team assignments; ordinary members, `can_lead`-only members, and unrelated users cannot schedule. `TeamMembership.can_lead` is deprecated/reserved for now and does not grant scheduling, member-management, or admin permissions. My Serving provides the non-staff team leader entry point through Teams I manage / 我负责的团队. The default view uses All event types / 全部类型 over the upcoming 8-week window while still showing only events where the selected team is required or already assigned; specific event type filtering still works. The workspace uses one active in-page schedule/edit form via event or assignment query selection, server-locks `service_event` and `ministry_team`, updates an existing event/team assignment instead of duplicating it, and creates no assignments on page load. ServiceEvent MinistryContext wording is Host / Language Label / 主办/语言标签（可选） and is label-only; it does not control visibility, serving assignment, or permissions and does not replace future ChurchStructureUnit-based audience/coverage scope. Browser automation was blocked by the Windows browser sandbox issue; user manually QA'd and accepted the MO-S.4A cleanup.

Root `AGENTS.md` now includes safe QA data seeding guidance: avoid long inline PowerShell `manage.py shell` commands, prefer tests/fixtures/app UI, keep one-off commands short and transparent, and never bypass endpoint security.

Recommended next safe slice:
- MO-S.5A rotation anchor foundation and MO-S.5B limited copy-forward suggestion helper are complete. The helper is preview/edit-first: it pre-fills the existing team schedule form from anchor-based or team-history prior assignments and writes only when the user explicitly saves.
- SE-AS.1 audience-scope redesign planning and SE-AS.2 model-only `ServiceEventAudienceScope` foundation are complete; the foundation is model-only and not the runtime source of truth, and `ServiceEvent.can_be_seen_by` is unchanged. SE-AS.3 is complete as the docs-only runtime migration plan (`docs/SERVICE_EVENT_AUDIENCE_RUNTIME_MIGRATION_PLAN.md`). Do not add the SE-AS.5 staff UI selector, the SE-AS.4 ServiceEvent visibility migration, consumer migration, or audience filtering without separate approval.
- Do not add automatic scheduling, availability, swaps, reminders, notifications, checklist, consumer migration, audience filtering, Community Activities, attendance, announcements, care workflows, file center, permission matrix expansion, ChurchStructureMembership serving inference, or a LightingTeam-specific model from MO-S.5 alone.
