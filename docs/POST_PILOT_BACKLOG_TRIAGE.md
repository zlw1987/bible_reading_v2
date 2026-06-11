# Post-Pilot Backlog Triage

## 1. Current Baseline

- Current validated baseline: `v0.9-pilot-rc1`.
- Pilot validation passed.
- No P0/P1 pilot blockers are known.
- Current phase: Post-Pilot Backlog Planning.
- CS-H.1 Flexible Church Structure and Audience Scope Design Doc is complete.
- CS-H.2 ChurchStructureUnit model-only foundation is complete.
- CS-H.2A ChurchStructureUnit model hardening is complete.
- CS-H.3 Current Structure Mapping and Membership Strategy Design is complete.
- CS-H.3B nullable legacy-to-ChurchStructureUnit mapping fields are complete.
- CS-H.3C idempotent ChurchStructureUnit seeding/mapping command is complete.
- CS-H.3D production/staging seeding verification passed.
- CS-H.3E seeded structure data QA closure is complete.
- CS-H.4 ChurchStructureMembership Design Doc is complete.
- CS-H.5A ChurchStructureMembership model-only foundation is complete.
- CS-H.5B ChurchStructureMembership helper/validation hardening is complete.
- CS-H.5C ChurchStructureMembership backfill command is complete.
- CS-H.5D ChurchStructureMembership production/staging backfill verification is complete by user-attested GoDaddy run.
- CS-H.5E Admin clarity for legacy structure vs future structure/membership foundation is complete.
- CS-H.6 Signup Requested-Unit Flow Design Doc is complete.
- CS-H.7 Admin Approval Workflow Design Doc is complete.
- CS-H.7A Membership Approval Workflow Implementation Plan is complete.
- CS-H.7B/C Membership Approval Capability + Pending Request List is complete.
- CS-H.7D Membership Request Detail + Approve/Reject Actions is complete.
- CS-H.7E `Profile.small_group` sync implementation is complete.
- CS-H.8 Integration Checkpoint is complete.
- CS-H.9 Membership Request UX Hardening is complete.
- CS-H.10 CMS Hardening Checkpoint is complete.
- PP-SA.2 Read-Only Staff Dashboard Overview is complete at `/staff/`.
- PP-SA.3 Membership / Admin Workflow Polish is complete.
- PP-SA.4 Moderation / Admin Queues is complete at `/staff/moderation/`.
- PP-SA.5 Ministry Ops Admin Improvements is complete on `/staff/`.
- MO-S.1 Ministry Scheduling Requirements Plan is complete as docs-only planning in `docs/MINISTRY_SCHEDULING_REQUIREMENTS_PLAN.md`.
- MO-S.2 Event Required-Team implementation is complete.
- MO-S.3 Assignment Coverage Display is complete as read-only coverage display.
- MO-S.4 Team-Leader Scheduling Workspace is complete as a team-scoped manual scheduling workspace.
- MO-S.4A Scheduling Semantic Cleanup is complete after manual QA.
- Mobile nav polish is deferred and the current mobile header behavior is accepted for now.
- Root `AGENTS.md` verification policy has been added.

The pilot closure decision is Go. No `v0.9-pilot-rc2` is required unless new pilot issues are discovered.

## 2. Triage Principles

- Fix real pilot feedback before adding speculative features.
- P0/P1 is reserved for blockers, data leaks, permission leaks, crashes, or broken core workflows.
- P2 is for near-term usability improvements that matter during real use but do not block the pilot baseline.
- P3 is for backlog, nice-to-have, exploratory, or deferred work.
- Large structural changes require architecture design before implementation.
- Deferred items remain deferred unless pilot feedback proves a concrete need.
- Do not use post-pilot planning to immediately start new modules.

## 3. Backlog Categories

### A. P0/P1 Hotfixes

No P0/P1 items are known after pilot validation.

Add items here only when a real pilot issue blocks use, leaks data, leaks permissions, crashes a core route, or breaks a core workflow.

Initial state:

| Item | Severity | Evidence | Status |
| --- | --- | --- | --- |
| None known | - | Pilot validation passed with no P0/P1 blockers | Open for future triage only |

### B. P2 Near-Term Usability Improvements

Likely candidates if confirmed by real pilot use:

- Staff Admin Surface Expansion planning.
- More polished staff dashboard/home.
- Ministry scheduling required-team workflow improvements from real pilot feedback.
- Additional Chinese/English copy cleanup discovered during real use.
- Mobile usability follow-up if real users report issues.
- Better setup guidance for non-technical staff.

These should remain narrow and should not introduce broad new module scope.

### C. P3 Backlog

Likely candidates:

- Additional dashboard summaries.
- Minor UI polish.
- More guide/help pages.
- Additional exports or reports if requested.

These are not pilot blockers and should be scheduled only after higher-priority feedback is handled.

### D. Architecture / Design Docs

Likely candidates:

- CS-H.1 Flexible Church Structure and Audience Scope Design Doc.
- CS-H.2 ChurchStructureUnit model-only foundation.
- CS-H.2A ChurchStructureUnit model hardening.
- CS-H.3 Current Structure Mapping and Membership Strategy Design.
- CS-H.3B Legacy Structure Mapping Fields, Model-Only.
- CS-H.3C Idempotent ChurchStructureUnit Seeding Command.
- CS-H.3D Production/Staging Seeding Verification Closure.
- CS-H.3E Seeded Structure Data QA Closure.
- CS-H.4 ChurchStructureMembership Design Doc.
- CS-H.5A ChurchStructureMembership Model-Only Foundation.
- CS-H.5B ChurchStructureMembership Model Hardening.
- CS-H.5C ChurchStructureMembership Backfill Command. Completed.
- CS-H.5D ChurchStructureMembership Production Backfill Verification. Completed by user-attested GoDaddy run; exact output counts were not recorded.
- CS-H.5E Admin Clarity for Legacy SmallGroup vs Future Church Structure. Completed.
- CS-H.6 Signup Requested-Unit Flow Design Doc. Completed.
- CS-H.7 Admin Approval Workflow Design Doc. Completed.
- CS-H.7A Membership Approval Workflow Implementation Plan. Completed.
- CS-H.7B/C Membership Approval Capability + Pending Request List. Completed.
- CS-H.7D Membership Request Detail + Approve/Reject Actions. Completed.
- CS-H.7E `Profile.small_group` Sync Implementation. Completed.
- CS-H.8 Integration Checkpoint. Completed.
- CS-H.9 Membership Request UX Hardening. Completed.
- CS-H.10 CMS Hardening Checkpoint. Completed.
- SE-AS.1 ServiceEvent Audience Scope Redesign Plan. Completed as docs-only planning in `docs/SERVICE_EVENT_AUDIENCE_SCOPE_REDESIGN_PLAN.md`.
- SE-AS.2 ServiceEventAudienceScope Model-Only Foundation. Completed as a model-only data foundation. Runtime visibility is handled by SE-AS.4; staff UI selector/display is handled by SE-AS.5; SE-AS.6A backfill/compatibility planning and SE-AS.6B dry-run audit command (no `--apply`) are complete; SE-AS.6C apply and consumer migration remain deferred until separately approved.
- SE-AS.3 ServiceEvent Audience Runtime Migration Plan. Completed as docs-only planning in `docs/SERVICE_EVENT_AUDIENCE_RUNTIME_MIGRATION_PLAN.md`. Renumbers later milestones: SE-AS.4 runtime visibility rule with legacy fallback, SE-AS.5 staff audience selector UI/display, SE-AS.6 backfill/compatibility/cleanup planning.
- SE-AS.4 ServiceEvent Audience Runtime Visibility Rule. Completed as runtime visibility with legacy fallback: events with `ServiceEventAudienceScope` rows use audience rows for ordinary-user visibility; events with zero rows keep legacy `scope_type` / `district` / `small_group` plus `Profile.small_group` behavior. `ChurchStructureMembership` still does not grant ServiceEvent visibility. Legacy fields remain preserved as fallback. No SE-AS.5 selector UI, form/template audience picker, Community Activities, CS-MAP.3, or CS-SETUP.1 was added.
- SE-AS.5A ServiceEvent Audience Selector Interaction Plan. Completed as docs-only planning in `docs/SERVICE_EVENT_AUDIENCE_SELECTOR_INTERACTION_PLAN.md`. Records where the future picker appears, how it interacts with legacy fallback fields, staff/ordinary display wording, empty/unmapped selection handling, recurring/batch behavior, and explicit non-goals. No code, template, form, view, model, test, migration, static, backfill, or runtime behavior change was added.
- SE-AS.5 ServiceEvent Staff Audience Selector UI and Display. Completed. Single create/edit and recurring create expose the optional `ChurchStructureUnit` picker; selected units save/replace `ServiceEventAudienceScope` rows; clearing the picker restores legacy fallback; recurring preview writes no rows; recurring create applies one selected audience set only to newly created events; skipped duplicates are not backfilled; staff detail shows Structure audience vs Legacy fallback audience plus readable labels and unmapped-selection warning; ordinary detail avoids architecture terms and unit IDs/codes. No SE-AS.6C apply/backfill, later legacy cleanup, CS-MAP.3, CS-SETUP.1, schema/migration, `ChurchStructureMembership` visibility migration, legacy-field removal/deprecation, or Required Ministry Teams / Rotation Anchor / TeamAssignment / My Serving behavior change was added.
- SE-AS.5B Post-Commit UI Wording and Structure-Map Clarity Cleanup. Completed. ServiceEvent single create/edit and recurring create audience pickers are collapsed by default with selected-count summaries; fallback audience wording now says legacy fields are used only when no structure audience is selected; `/staff/structure/` now uses clearer structure/setup wording, descendant-inclusive covered-member counts, current data mapping labels for active legacy rows, and a setup warning for direct active primary memberships on parent units. No runtime visibility, schema, migration, backfill, setup/edit UI, member roster, or membership-source migration was added.
- DOCS-AS.1 ChurchStructureUnit Audience-Scope Alignment. Completed as docs-only planning. Records the shared `ChurchStructureUnit` audience-scope direction: app modules should select `ChurchStructureUnit` rows through app-specific join models rather than adding more legacy-only multi-select scope fields. Bible Study Schedule is the first narrow runtime consumer (now implemented via BS-AS.1); ServiceEvent / Church Gatherings and future Community Activities reuse the same foundation later. `ChurchStructureMembership` runtime visibility migration remains deferred.
- BS-AS.1 Bible Study Schedule Audience Scope Using ChurchStructureUnit. Completed. `BibleStudySeriesAudienceScope` joins `BibleStudySeries / 查经安排` to `ChurchStructureUnit`; selected units resolve to eligible legacy `SmallGroup` rows for meeting generation; generated `BibleStudyMeeting` rows still point to legacy `SmallGroup`; ordinary member visibility still uses `Profile.small_group`; legacy scope fields remain compatibility/fallback.
- BS-AS.2 Audience Picker UX / Compact Scope Display / Active-List Cancelled Cleanup. Completed. Reusable server-rendered audience picker partial (searchable, chips, tree order, no-JS fallback, vanilla-JS convenience clearing, backend validation authoritative); compact list/card labels and wrapped/chip detail labels with the root prefix omitted; active management lists and related detail lists hide cancelled schedules/guides/meetings; generation still treats cancelled meetings as existing/skipped.
- BS-AS.2A Audience Picker Accessibility Polish. Completed. Bilingual search-input `aria-label`; chip remove buttons include the selected unit label in their `aria-label`; no behavior/schema/visibility changes.
- PP-SA.1 Staff Admin Surface Expansion Plan. Completed as docs-only planning in `docs/STAFF_ADMIN_SURFACE_EXPANSION_PLAN.md`.
- PP-SA.2 Read-Only Staff Dashboard Overview. Completed as a permission-protected read-only staff overview at `/staff/`, with counts and links only for existing workflows.
- PP-SA.3 Membership / Admin Workflow Polish. Completed as staff membership request workflow polish with clearer queue summary, empty states, detail sections, approval-state/context labels, and overview context.
- PP-SA.4 Moderation / Admin Queues. Completed as a permission-protected read-only staff moderation queue at `/staff/moderation/`, summarizing existing report/hidden states only.
- PP-SA.5 Ministry Ops Admin Improvements. Completed as focused read-only ministry ops health indicators on `/staff/`.
- MO-S.1 Ministry Scheduling Requirements Plan. Completed as docs-only planning in `docs/MINISTRY_SCHEDULING_REQUIREMENTS_PLAN.md`.
- MO-S.2 Event Required-Team Implementation. Completed as the generic `ServiceEvent` required-team relationship.
- MO-S.3 Assignment Coverage Display. Completed.
- MO-S.4 Team-Leader Scheduling Workspace. Completed.
- MO-S.4A Scheduling Semantic Cleanup. Completed.
- MO-S.5A Rotation Anchor Foundation. Completed.
- MO-S.5B Copy-Forward Suggestion Helper. Completed.
- CS-MAP.1 Church Structure Map / Setup Readiness Plan. Completed as docs-only planning in `docs/CHURCH_STRUCTURE_MAP_AND_SETUP_READINESS_PLAN.md`, recording the June 2026 demo feedback and proposing CS-MAP.2 (read-only staff structure map + mapping health) as the next safe slice.
- CS-MAP.2 Read-Only Staff Structure Map + Mapping Health. Completed at `/staff/structure/` as a permission-protected read-only staff page: active `ChurchStructureUnit` hierarchy, descendant-inclusive covered-member counts, current data mapping context from active legacy rows, setup-readiness indicators including direct active primary memberships on parent units, no member rosters, no write actions, no schema/migration/runtime visibility changes, no setup/edit UI. CS-MAP.3 remains optional/unapproved; CS-SETUP.1 setup/edit UI is explicitly not approved.
- Deployment/operations hardening plan.

These are planning deliverables. They should precede implementation when the proposed work changes schema, permissions, audience scope, or module boundaries.

### E. Future Modules

Likely candidates:

- Community Activities V1.
- Checklist V1.
- Reminder/notification strategy.
- Availability/swap request planning.
- Bible Study / small group attendance planning.
- Prayer Wall refinement.
- Pastor/staff announcements.
- Group leader dashboard.
- Children/family/couples/newcomer care workflows.
- Activities signup, check-in, and capacity management.
- Resources/materials/file center.
- Finer permission matrix for ministry role, small group leader, district leader, and staff capabilities.

These are future CMS product directions, not immediate implementation authorization. "Not V1" or "not now" means deferred until separately planned, not outside the final product.

These remain future modules. Do not start implementation until post-pilot evidence justifies priority and the relevant design work is complete.

### F. Explicit Not Now

- Full church ERP.
- Automatic scheduling engine.
- Historical import.
- Sensitive/private data import.
- Phone/private contact import.
- Finance/HR/CRM expansion.
- LightingTeam-specific model.
- Child security check-in unless separately authorized.

Children/family care workflow belongs to future CMS scope; child security check-in is a separate safety-sensitive feature and is not automatically authorized.

### G. June 2026 Demo Feedback Record

1. IM team lead: it is unrealistic for this app to replace every existing church app at once; the system should be modular, adopted module by module, and able to coexist/integrate with existing tools (for example 微读圣经 for small-group reading/study content). Classification: product principle / architecture direction, not a defect. Response: recorded as the Modular Adoption and Coexistence principle in `docs/PRODUCT_ARCHITECTURE_AND_ROADMAP.md` and `docs/CHURCH_STRUCTURE_MAP_AND_SETUP_READINESS_PLAN.md`. Integration initially means link/reference/mapping; no external-system integration implementation is authorized by this record.
2. Pastor/elder/deacon: leadership wants a clear church structure architecture, setup support, and a visible structure map / hierarchy map; structure setup currently happens mainly through Django Admin, which is not convenient; church structure is seen as a foundation for many future modules. Classification: P2 staff visibility/usability planning; no P0/P1. Response: CS-MAP.1 docs-only plan completed (`docs/CHURCH_STRUCTURE_MAP_AND_SETUP_READINESS_PLAN.md`); CS-MAP.2 read-only Staff Structure Map + Mapping Health is now completed at `/staff/structure/`; setup/edit UI (CS-SETUP.1) is not approved and remains gated on read-only evidence plus a separate design doc. Django Admin remains the structure write surface for now.

## 4. Recommended Next Sequence

1. Collect real pilot feedback for a fixed period.
2. Record feedback into this backlog.
3. CS-H.1 flexible hierarchy/audience design doc completed.
4. CS-H.2 `ChurchStructureUnit` model-only foundation completed.
5. CS-H.2A `ChurchStructureUnit` model hardening completed.
6. CS-H.3 current structure mapping and membership strategy completed.
7. CS-H.3B nullable legacy-to-`ChurchStructureUnit` mapping fields completed.
8. CS-H.3C idempotent structure seeding/mapping command completed.
9. CS-H.3D production/staging seeding verification completed.
10. CS-H.3E seeded structure data QA closure completed.
11. CS-H.4 ChurchStructureMembership Design Doc completed.
12. CS-H.5A ChurchStructureMembership model-only foundation completed.
13. CS-H.5B membership helper/validation hardening completed.
14. CS-H.5C backfill command with dry-run/apply from `Profile.small_group` completed.
15. CS-H.5D production/staging backfill verification completed by user-attested GoDaddy run.
16. CS-H.5E Admin clarity for legacy structure vs future structure/membership foundation completed.
17. CS-H.6 Signup Requested-Unit Flow Design Doc completed.
18. CS-H.7 Admin Approval Workflow Design Doc completed.
19. CS-H.7A Membership Approval Workflow Implementation Plan completed.
20. CS-H.7B/C Membership Approval Capability + Pending Request List completed.
21. CS-H.7D Membership Request Detail + Approve/Reject Actions completed.
22. CS-H.7E `Profile.small_group` sync implementation completed.
23. CS-H.8 integrated request-flow checkpoint completed.
24. CS-H.9 membership request UX hardening completed.
25. CS-H.10 CMS hardening checkpoint completed.
26. Staff Admin Surface Expansion planning completed.
27. PP-SA.2 read-only staff overview completed.
28. PP-SA.3 membership/admin workflow polish completed.
29. PP-SA.4 moderation/admin queues completed.
30. PP-SA.5 ministry ops admin improvements completed.
31. MO-S.1 ministry scheduling requirements planning completed from real pilot feedback.
32. MO-S.2 event required-team model/design implementation completed.
33. MO-S.3 assignment coverage display for required teams completed.
34. MO-S.4 team-leader scheduling workspace for same-type events completed.
35. MO-S.4A scheduling semantic cleanup completed after manual QA.
36. MO-S.5A rotation anchor foundation completed.
37. MO-S.5B limited copy-forward suggestion helper completed.
38. SE-AS.1 ServiceEvent audience-scope redesign planning completed; SE-AS.2 completed as a model-only ServiceEvent audience-scope data foundation, and SE-AS.4 completed the runtime visibility rule with legacy fallback: audience rows govern ordinary-user visibility when present, while events with no audience rows still use legacy scope fields and `Profile.small_group`.
39. DOCS-AS.1 records the shared `ChurchStructureUnit` audience-scope direction across Bible Study Schedule, ServiceEvent / Church Gatherings, and future Community Activities.
40. BS-AS.1 Bible Study Schedule audience scope using `ChurchStructureUnit` is complete, as the first narrow runtime consumer. It resolves selected `ChurchStructureUnit` rows to eligible legacy `SmallGroup` rows for meeting generation; generated `BibleStudyMeeting` rows still point to legacy `SmallGroup`, ordinary member visibility stays on `Profile.small_group`, and `ChurchStructureMembership` runtime visibility migration remains deferred.
41. BS-AS.2 (audience picker UX, compact scope display, active-list cancelled cleanup) and BS-AS.2A (audience picker accessibility polish) are complete.
42. BS-AS QA follow-up completed; BS-AS.2B fixed the audience picker mobile CSS no-go. CS-MAP.2 read-only Staff Structure Map + Mapping Health is completed at `/staff/structure/`; SE-AS.4 is completed as the ServiceEvent runtime audience rule only, and CS-MAP work must not be bundled with SE-AS.5 or Community Activities; CS-MAP.3 remains optional/unapproved and CS-SETUP.1 setup/edit UI remains unapproved.
43. SE-AS.5A ServiceEvent audience selector interaction planning completed. The future selector appears on single create/edit and recurring create; legacy `scope_type` / `district` / `small_group` remain editable as fallback audience settings; selected audience rows govern visibility without legacy fields acting as an extra filter; empty picker means legacy fallback; one selected audience set applies to all events created by a recurring batch; no backfill, migration, deprecation, Community Activities, CS-MAP.3, CS-SETUP.1, membership visibility migration, or ministry scheduling behavior change is authorized.
44. SE-AS.5 ServiceEvent staff audience selector UI/display completed using the SE-AS.5A contract. SE-AS.5C / CS-MAP.2B corrected the interaction model: the ServiceEvent picker section remains visible while hierarchy tree nodes expand/collapse by level, and `/staff/structure/` uses the same root-visible tree mental model. The selector and staff effective display are implemented; SE-AS.6C apply/backfill and later legacy cleanup, CS-MAP.3, CS-SETUP.1, membership visibility migration, and ministry scheduling behavior changes remain unapproved.
45. Later SE-AS.6C apply/backfill, later legacy cleanup, and future Community Activities should reuse the same `ChurchStructureUnit` audience-scope foundation where applicable; none of them is authorized by SE-AS.5 completion.
46. Revisit Community Activities only after a separate Community Activities audience/operations plan is explicitly approved; that plan should use the shared `ChurchStructureUnit` audience-scope foundation through its own app-specific join model rather than a separate legacy-only audience segment system. Community Activities is not implemented now.
47. Revisit Checklist V1 only if ministry pilot feedback proves checklist need separately from required-team coverage.

CS-H.6 and CS-H.7 are original design docs, and CS-H.7A is implementation planning. Signup requested-unit capture, Profile request capture, staff request review, approve/reject actions, and CS-H.7E approval sync now exist. CS-H.7E syncs `Profile.small_group` only for approved active primary memberships whose unit maps to exactly one active legacy `SmallGroup`. CS-H.5E improves Django Admin clarity only. Exact CS-H.5D command-output counts were not recorded. PP-SA.2 adds a permission-protected read-only staff overview at `/staff/` with counts and links only for existing workflows. PP-SA.3 polishes the existing staff membership request workflow with clearer queue summary, empty states, detail sections, approval-state/context labels, and overview context. PP-SA.4 adds a permission-protected read-only staff moderation queue at `/staff/moderation/` that summarizes existing report and hidden states only. PP-SA.4 includes reported/hidden prayer request categories plus reported/hidden reflection post and reply categories; prayer comment report/hidden categories are shown as not separately tracked by existing data. PP-SA.4 links to existing moderation workflows and adds no moderation actions or states. PP-SA.5 adds focused read-only ministry ops health indicators on `/staff/`: upcoming ServiceEvents, upcoming TeamAssignments, unconfirmed assignments, inactive teams, active teams missing playbook links, display-name-only active members, active teams with no active members, upcoming assignments without active members, upcoming assignments using inactive teams, and upcoming required-team gaps. The PP-SA.5 aggregate is a sum of warning indicator buckets, not a unique problematic-record count; the same object may contribute to multiple indicators. PP-SA.5 links only to existing ServiceEvent, MinistryTeam, and TeamAssignment workflows. MO-S.1 records real pilot feedback that staff need required MinistryTeam selection when creating or batch-creating ServiceEvents, TeamAssignment pages need required-team coverage with assigned coworkers and confirmation status rather than only counts, missing required teams should show as unassigned, and team leaders need an efficient same-type event scheduling entry point for their own team. MO-S.2 implements required teams as event-level expectations: `ServiceEvent` now uses an explicit `ServiceEventRequiredTeam` through model to required `MinistryTeam` records, with `ministry_team` protected from deletion so referenced teams should be deactivated instead. Single create/edit and recurring batch-create can select required teams; batch-created events share the selected teams; existing events may have none; already-selected inactive teams remain visible/removable on edit. MO-S.3 is complete as read-only assignment coverage display: coverage compares `ServiceEvent` required teams against `TeamAssignment` and `TeamAssignmentMember` data, the `TeamAssignment` list is the primary operational coverage surface, assignment detail shows compact event coverage, ServiceEvent detail shows coverage only to staff/service-event or team-assignment managers, ordinary event viewers do not see coworker coverage, `/staff/` adds upcoming required-team gap counts, multiple coworkers display with confirmation status, and user-completed manual QA accepted the UI after browser automation was blocked. MO-S.4 is complete as a team-scoped manual scheduling workspace at `/teams/<team_id>/schedule/`, and MO-S.4A scheduling semantic cleanup is complete after manual QA: `TeamMembership.can_lead` is deprecated/reserved for now and does not grant scheduling, member-management, or admin permissions; Team detail shows the contextual Schedule Team / 安排团队服事 link only for users who can manage that team's assignments; staff, superusers, and global assignment managers can schedule any team; Lead and Coordinator roles can schedule their own team assignments; ordinary members, `can_lead`-only members, and unrelated users cannot schedule; My Serving provides the non-staff team leader entry point through Teams I manage / 我负责的团队; the default view uses All event types / 全部类型 over the upcoming 8-week window while still showing only events where the selected team is required or already assigned; specific event type filtering still works; it supports one active in-page schedule/edit form via event or assignment query selection; `service_event` and `ministry_team` are server-locked; existing event/team assignments are updated instead of duplicated; loading the page creates no assignments; ServiceEvent MinistryContext wording is Host / Language Label / 主办/语言标签（可选） and is label-only, so it does not control visibility, serving assignment, or permissions and does not replace future ChurchStructureUnit-based audience/coverage scope. Browser automation for MO-S.4A was blocked by the Windows browser sandbox issue; user manually QA'd and accepted the cleanup. MO-S.4/MO-S.4A did not add automatic rotation, copy-forward, availability, swaps, reminders, notifications, checklist, attendance, Community Activities, audience filtering, consumer migration, ChurchStructureMembership serving inference, or a LightingTeam-specific model. Current runtime behavior still uses the legacy models and `Profile.small_group`; `/studies/`, reading progress, `ServiceEvent`, My Serving, and other consumers have not migrated to `ChurchStructureMembership`. Hierarchical multi-select audience scope, ServiceEvent filtering migration, Community Activities, and broad Staff Admin expansion remain future phased work.

MO-S.5A adds optional `ServiceEvent.rotation_anchor_team` as a scheduling hint only. MO-S.5B adds limited copy-forward suggestions in the team schedule workspace: anchor-based and team-history modes prefill the editable form, copy active members only, do not copy confirmations, and write only on explicit save. MO-S.5B does not add an automatic scheduling engine, availability, swaps, reminders, notifications, checklist, attendance, Community Activities, audience filtering, consumer migration, ChurchStructureMembership serving inference, or a LightingTeam-specific model.

SE-AS.1 is complete as the docs-only ServiceEvent audience-scope redesign plan. SE-AS.2 is complete as a model-only ServiceEvent audience-scope data foundation: `ServiceEventAudienceScope` links `ServiceEvent` to `ChurchStructureUnit`, `ServiceEvent` delete cascades scope rows, `ChurchStructureUnit` delete is protected while referenced, a unique event+unit constraint exists, validation requires an active unit and rejects redundant ancestor/descendant selection while allowing siblings, and an event with no scope rows stays valid. SE-AS.3 is complete as the docs-only ServiceEvent Audience Runtime Migration Plan (`docs/SERVICE_EVENT_AUDIENCE_RUNTIME_MIGRATION_PLAN.md`). SE-AS.4 is complete as the runtime visibility rule with legacy fallback: events with `ServiceEventAudienceScope` rows use those rows for ordinary-user visibility, events with no rows keep legacy `scope_type` / `district` / `small_group` plus `Profile.small_group` behavior, requested or active `ChurchStructureMembership` still does not grant event visibility, and legacy scope fields remain preserved as fallback. SE-AS.5A is complete as the docs-only staff audience selector interaction plan (`docs/SERVICE_EVENT_AUDIENCE_SELECTOR_INTERACTION_PLAN.md`). SE-AS.5 is complete as the staff audience selector UI/display implementation: single create/edit and recurring create use the optional picker; legacy fields stay editable as fallback settings; empty picker means legacy fallback; selected structure rows govern visibility without legacy fields acting as an extra filter; recurring create applies one selected audience set to newly created events; preview writes no rows; skipped duplicates are not backfilled; staff effective display distinguishes Structure audience from Legacy fallback audience; ordinary detail avoids architecture details and unit codes/IDs. SE-AS.5 added no SE-AS.6C apply/backfill, later legacy cleanup, Community Activities, CS-MAP.3, CS-SETUP.1, schema/migration, deprecation/removal of legacy fields, `ChurchStructureMembership` visibility migration, or consumer migration. SE-AS.6C apply/backfill and later legacy cleanup remain future and require separate approval; SE-AS.6A planning and SE-AS.6B dry-run audit are complete. Required Ministry Teams, Rotation Anchor Team, TeamAssignment, My Serving, and MinistryContext/Host Label remain separate concepts and are not conflated with audience scope.

## 5. Decision Framework

For every proposed task, answer:

- Which pilot user felt the pain?
- Is it blocking, frequent, or merely aesthetic?
- Is it normal-user or staff-user?
- Is it workflow, UI, permission, data, or architecture?
- Can it be fixed without schema change?
- Does it belong in existing modules or a new module?
- Is this a pilot issue or a future vision?

Severity assignment:

| Severity | Use When |
| --- | --- |
| P0 | The pilot cannot continue, data leaks, permission leaks, or a common core route crashes. |
| P1 | A core workflow is broken or unusable for pilot users. |
| P2 | Real usability friction exists, but the validated baseline remains usable. |
| P3 | Nice-to-have, future vision, polish, or deferred module work. |

## 6. Candidate Next Task Options

Include these as planning options only. Do not start them from this triage document.

- CS-H.1 Flexible Church Structure and Audience Scope Design Doc. Completed.
- CS-H.2 ChurchStructureUnit model-only foundation. Completed.
- CS-H.2A ChurchStructureUnit model hardening. Completed.
- CS-H.3 Current Structure Mapping and Membership Strategy Design. Completed.
- CS-H.3B Legacy Structure Mapping Fields, Model-Only. Completed.
- CS-H.3C Idempotent ChurchStructureUnit Seeding Command. Completed.
- CS-H.3D Production/Staging Seeding Verification Closure. Completed.
- CS-H.3E Seeded Structure Data QA Closure. Completed.
- CS-H.4 ChurchStructureMembership Design Doc. Completed.
- CS-H.5A ChurchStructureMembership Model-Only Foundation. Completed.
- CS-H.5B ChurchStructureMembership Model Hardening. Completed.
- CS-H.5C ChurchStructureMembership Backfill Command. Completed.
- CS-H.5D ChurchStructureMembership Production Backfill Verification. Completed by user-attested GoDaddy run; exact output counts were not recorded.
- CS-H.5E Admin Clarity for Legacy SmallGroup vs Future Church Structure. Completed.
- CS-H.6 Signup Requested-Unit Flow Design Doc. Completed.
- CS-H.7 Admin Approval Workflow Design Doc. Completed.
- CS-H.7A Membership Approval Workflow Implementation Plan. Completed.
- CS-H.7B/C Membership Approval Capability + Pending Request List. Completed.
- CS-H.7D Membership Request Detail + Approve/Reject Actions. Completed.
- CS-H.7E `Profile.small_group` Sync Implementation. Completed.
- CS-H.8 Integration Checkpoint. Completed.
- CS-H.9 Membership Request UX Hardening. Completed.
- CS-H.10 CMS Hardening Checkpoint. Completed.
- PP-SA.1 Staff Admin Surface Expansion Plan. Completed as docs-only planning in `docs/STAFF_ADMIN_SURFACE_EXPANSION_PLAN.md`.
- PP-SA.2 Read-Only Staff Dashboard Overview. Completed at `/staff/` as a permission-protected read-only page with counts and links only for existing workflows.
- PP-SA.3 Membership / Admin Workflow Polish. Completed as staff membership request workflow polish without schema changes or consumer migration.
- PP-SA.4 Moderation / Admin Queues. Completed at `/staff/moderation/` as a read-only queue over existing report/hidden data.
- PP-SA.5 Ministry Ops Admin Improvements. Completed on `/staff/` as read-only ministry ops health indicators.
- MO-S.1 Ministry Scheduling Requirements Plan. Completed as docs-only planning from real pilot feedback.
- MO-S.2 Event Required-Team Model / Design Implementation. Completed.
- MO-S.3 Assignment Coverage Display for Required Teams. Completed.
- MO-S.4 Team-Leader Scheduling Workspace for Same-Type Events. Completed.
- MO-S.4A Scheduling Semantic Cleanup. Completed after manual QA.
- MO-S.5A Rotation Anchor Foundation. Completed.
- MO-S.5B Limited Copy-Forward Suggestion Helper. Completed.
- SE-AS.1 ServiceEvent Audience Scope Redesign Plan. Completed as docs-only planning.
- SE-AS.2 ServiceEventAudienceScope Model-Only Foundation. Completed as model-only data foundation; no staff UI selector, filtering, visibility migration, or consumer migration is approved by this status.
- SE-AS.3 ServiceEvent Audience Runtime Migration Plan. Completed as docs-only planning.
- SE-AS.4 ServiceEvent Audience Runtime Visibility Rule. Completed with legacy fallback; no selector UI, Community Activities, CS-MAP.3, or CS-SETUP.1.
- SE-AS.5A ServiceEvent Audience Selector Interaction Plan. Completed as docs-only planning; no implementation authorized.
- SE-AS.5 ServiceEvent Staff Audience Selector UI and Display. Completed.
- SE-AS.5B Post-Commit UI Wording and Structure-Map Clarity Cleanup. Completed.
- DOCS-AS.1 ChurchStructureUnit Audience-Scope Alignment. Completed as docs-only planning.
- BS-AS.1 Bible Study Schedule Audience Scope Using ChurchStructureUnit. Completed as the first narrow runtime audience-scope consumer.
- BS-AS.2 Audience Picker UX / Compact Scope Display / Active-List Cancelled Cleanup. Completed.
- BS-AS.2A Audience Picker Accessibility Polish. Completed.
- CS-MAP.1 Church Structure Map / Setup Readiness Plan. Completed as docs-only planning.
- CS-MAP.2 Read-Only Staff Structure Map + Mapping Health. Completed at `/staff/structure/` as a read-only staff page with descendant-inclusive covered-member counts, current data mapping context, setup-readiness indicators, and CS-MAP.2B hierarchical node-level expand/collapse.
- CS-SETUP.1A Structure Setup/Edit UI Risk Design. Completed as docs-only risk/design in `docs/CHURCH_STRUCTURE_MAP_AND_SETUP_READINESS_PLAN.md` Section 13: explains why a setup/edit UI is unsafe today (stored audience-row impact, legacy matching bridge, membership-vs-visibility confusion), defines the required safety contract, and splits CS-SETUP.1 into separately approvable CS-SETUP.1B–1E sub-milestones. No implementation, schema, or runtime change; none of 1B–1E approved.
- SE-AS.6 ServiceEvent Audience Backfill / Compatibility Cleanup. SE-AS.6A planning and SE-AS.6B dry-run audit command (no `--apply`) are complete; SE-AS.6C apply remains a future, separately approved milestone; do not bundle with CS-MAP work or Community Activities.
- TODAY-HOME.1A Today Page Action Center Plan. Completed as docs-only planning in `docs/TODAY_PAGE_ACTION_CENTER_PLAN.md`, refined by TODAY-HOME.1A.1: three-zone personal Today IA (Needs your attention / Today / This week); the week strip shows visible upcoming Church Gatherings (no `event_type` guessing, draft/cancelled excluded); Bible-study role chips deferred until role user-linking is reliable, and role confirmation not planned; no implementation, schema, or runtime visibility change authorized.
- CA-V1.1 Community Activities Planning Refinement.
- CL-V1.1 Checklist V1 Re-evaluation.
- OPS-H.1 Deployment and Operations Hardening.

## 7. Docs Consistency Notes

Roadmap documents should remain aligned on these points:

- Pilot validation passed on `v0.9-pilot-rc1`.
- The current next phase is Post-Pilot Backlog Triage / Post-Pilot Backlog Planning.
- Large deferred items remain deferred pending real pilot feedback. MO-S.4 manual team-leader scheduling, MO-S.4A semantic cleanup, MO-S.5A rotation anchor metadata, MO-S.5B limited copy-forward suggestions, SE-AS.1 ServiceEvent audience-scope planning, the SE-AS.2 ServiceEventAudienceScope model-only foundation, SE-AS.4 runtime visibility with legacy fallback, SE-AS.5A staff selector interaction planning, and SE-AS.5 staff selector UI/display now exist, but automatic scheduling, availability, swaps, reminders, checklist, notifications, attendance, Community Activities, SE-AS.6C apply/backfill and later legacy cleanup, ServiceEvent consumer migration, and membership-driven visibility remain deferred unless separately planned and approved.
- `ChurchStructureUnit` model-only foundation exists and has hardened cycle validation. CS-H.3 records the mapping/membership strategy, CS-H.3B adds nullable legacy mapping fields, CS-H.3C adds explicit command-based seeding/mapping, CS-H.3D verifies GoDaddy production/staging seeding with a clean second dry-run, CS-H.3E closes seeded structure data QA, CS-H.4 records the membership design, CS-H.5A adds the membership model-only foundation, CS-H.5B hardens helpers/validation, CS-H.5C adds explicit command-based membership backfill, CS-H.5D records user-attested GoDaddy production/staging backfill verification, CS-H.5E improves Django Admin clarity, CS-H.6 records signup requested-unit flow design, CS-H.6A/CS-H.6B add signup request capture planning and implementation, CS-H.6D adds Profile request capture, CS-H.7 records admin approval workflow design, CS-H.7A records approval implementation planning, CS-H.7B/C adds the membership-management capability plus pending request list, CS-H.7D adds request detail plus minimal approve/reject actions, CS-H.7E syncs `Profile.small_group` only for exactly one active legacy small-group mapping, CS-H.8 records the integration checkpoint, CS-H.9 records membership request UX hardening, CS-H.10 records the CMS hardening checkpoint, PP-SA.2 records the read-only staff overview completion, PP-SA.3 records the staff membership request workflow polish completion, PP-SA.4 records the read-only staff moderation queue completion, and PP-SA.5 records the read-only ministry ops health indicator completion. Runtime still uses legacy models and `Profile.small_group`; `/studies/`, reading progress, My Serving, and other consumers are not yet membership-driven, and ServiceEvent only uses `ServiceEventAudienceScope` rows for ordinary-user visibility when those rows exist. Bible Study Schedule audience selection is implemented (BS-AS.1 / BS-AS.2 / BS-AS.2A): selected `ChurchStructureUnit` rows resolve to legacy `SmallGroup` for meeting generation while ordinary member visibility stays on `Profile.small_group` and `ChurchStructureMembership` runtime visibility migration remains deferred. ServiceEvent audience selector UI/editing/display workflow is implemented in SE-AS.5, while SE-AS.6C apply/backfill and later legacy cleanup, ServiceEvent consumer migration, Community Activities, Checklist V1, reminders, scheduling, swaps, availability, attendance, notifications, announcements, care workflows, activities operations, file center, and finer permission matrix work should not start without a separate planning decision.
