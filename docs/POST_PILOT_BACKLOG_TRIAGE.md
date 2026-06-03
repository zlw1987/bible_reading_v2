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
- ServiceEvent audience/filtering design doc.
- Staff Admin Surface Expansion plan.
- Deployment/operations hardening plan.

These are planning deliverables. They should precede implementation when the proposed work changes schema, permissions, audience scope, or module boundaries.

### E. Future Modules

Likely candidates:

- Community Activities V1.
- Checklist V1.
- Reminder/notification strategy.
- Availability/swap request planning.
- Attendance planning only if real need emerges.

These remain future modules. Do not start implementation until post-pilot evidence justifies priority and the relevant design work is complete.

### F. Explicit Not Now

- Full church ERP.
- Automatic scheduling engine.
- Historical import.
- Sensitive/private data import.
- Phone/private contact import.
- Finance/HR/CRM expansion.
- LightingTeam-specific model.

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
18. Plan CS-H.7 Admin Approval Workflow Design Doc.
19. Do Staff Admin Surface Expansion planning if setup/admin friction is real.
20. Revisit Community Activities only after the audience model is clarified.
21. Revisit Checklist V1 only if ministry pilot feedback proves need.

CS-H.6 is design-only. CS-H.5E improves Django Admin clarity only. Exact CS-H.5D command-output counts were not recorded. Current runtime behavior still uses the legacy models and `Profile.small_group`. Signup/onboarding assignment changes, hierarchical multi-select audience scope, ServiceEvent filtering, Community Activities, and custom Staff Admin implementation remain future phased work.

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
- PP-SA.1 Staff Admin Surface Expansion Plan.
- CA-V1.1 Community Activities Planning Refinement.
- CL-V1.1 Checklist V1 Re-evaluation.
- OPS-H.1 Deployment and Operations Hardening.

## 7. Docs Consistency Notes

Roadmap documents should remain aligned on these points:

- Pilot validation passed on `v0.9-pilot-rc1`.
- The current next phase is Post-Pilot Backlog Triage / Post-Pilot Backlog Planning.
- Large deferred items remain deferred pending real pilot feedback.
- `ChurchStructureUnit` model-only foundation exists and has hardened cycle validation. CS-H.3 records the mapping/membership strategy, CS-H.3B adds nullable legacy mapping fields, CS-H.3C adds explicit command-based seeding/mapping, CS-H.3D verifies GoDaddy production/staging seeding with a clean second dry-run, CS-H.3E closes seeded structure data QA, CS-H.4 records the membership design, CS-H.5A adds the membership model-only foundation, CS-H.5B hardens helpers/validation, CS-H.5C adds explicit command-based membership backfill, CS-H.5D records user-attested GoDaddy production/staging backfill verification, CS-H.5E improves Django Admin clarity, and CS-H.6 records signup requested-unit flow design. Runtime still uses legacy models and `Profile.small_group`. Signup/onboarding code changes, audience selection, Community Activities, Checklist V1, ServiceEvent filtering, reminders, scheduling, swaps, availability, and attendance should not start without a separate planning decision.
