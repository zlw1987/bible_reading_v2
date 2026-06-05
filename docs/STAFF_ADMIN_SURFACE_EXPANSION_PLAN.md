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

Gaps:
- Staff may need a simple event operations overview for upcoming events, draft events, missing setup fields, and related ministry assignments.
- Current ServiceEvent scope remains legacy-field based. It must not be silently replaced with `ChurchStructureMembership` or audience filtering.
- ServiceEvent should not become Community Activities, full event management, or scheduling automation without separate planning.

### MinistryTeam / TeamAssignment / My Serving Support

Current state:
- Ministry Operations includes `MinistryTeam`, `TeamMembership`, `TeamAssignment`, `TeamAssignmentMember`, manual ServiceEvent-based assignments, per-member confirmation, Playbook link, non-sensitive assignment notes, and My Serving Page V1.
- Lighting Team pilot data/setup support exists on the generic ministry operations foundation.

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

Candidate queues:
- Reported prayer requests/comments.
- Reported reading reflections/replies.
- Hidden or recently moderated items.
- Recent unanswered moderation actions.

Boundaries:
- Moderation queues are not pastoral case management.
- Do not add care workflows, announcements, notifications, attendance, private contact imports, or sensitive notes.
- Keep normal-user copy kind and non-technical; staff copy may show moderation state and audit context.

### PP-SA.5 Ministry Ops Admin Improvements

Goal:
- Improve staff oversight for ServiceEvent, MinistryTeam, TeamAssignment, and My Serving operations.

Candidate work:
- Upcoming ServiceEvent and assignment overview.
- Team setup health: missing members, display-name-only members, inactive teams, missing playbook links.
- Assignment confirmation review.
- Generic pilot setup support for additional ministry teams.

Boundaries:
- Keep models generic; do not add LightingTeam-specific models.
- Do not add availability, swap requests, reminders, attendance, checklist, or scheduling automation in this phase unless separately planned.
- Do not infer ministry team assignment or serving permissions from church structure membership.

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

Recommended next safe slice:
- PP-SA.4 Moderation / Admin Queues.
- Keep the next slice narrow and continue linking to existing workflows unless a separately planned workflow change is approved.
- Do not add schema changes, notifications, consumer migration, audience filtering, Community Activities, attendance, announcements, care workflows, file center, or permission matrix expansion from the PP-SA.3 completion alone.
