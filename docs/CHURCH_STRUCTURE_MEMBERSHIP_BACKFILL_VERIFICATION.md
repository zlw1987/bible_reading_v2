# Church Structure Membership Backfill Verification

## 1. Purpose

This document records production/staging verification of `backfill_church_structure_memberships`.

Verification is based on the user's attested GoDaddy execution. Exact command-output counts were not provided, so this document does not invent them.

Historical note: at the time of this CS-H.5D backfill verification, runtime behavior remained unchanged and `Profile.small_group` was still the current runtime source for Bible Study visibility, reading group progress, and current group-scoped behavior. Current state supersedes that: approved migrated consumers use active primary `ChurchStructureMembership`, `Profile.small_group` was removed, V1 `BibleStudySession` app runtime is retired, and remaining legacy rows/tables are bridge/admin/diagnostic/setup/table-retirement context.

Current state: membership is a runtime source only for explicitly switched consumers: ServiceEvent structure-audience row matching since CS-CORE.2B-A, and Bible Study v2 `BibleStudyMeeting` ordinary-member visibility plus the `/studies/` / Today v2 meeting pre-filter since CS-CORE.2C-B. Requested/rejected/cancelled/ended/future/expired memberships still grant nothing.

Because exact output counts were not provided, this closure records the verification status as user-attested rather than command-output-transcribed.

## 2. Baseline

Baseline before CS-H.5D:
- CS-H.3C/CS-H.3D/CS-H.3E structure seeding and mapping already passed.
- `ChurchStructureUnit` exists and is seeded/mapped from current structure data.
- CS-H.5A `ChurchStructureMembership` model exists.
- CS-H.5B membership helpers and validation exist.
- CS-H.5C `backfill_church_structure_memberships` command exists.
- The GoDaddy app had real user, profile, and small-group data.

## 3. Commands Verified By User

The user confirmed the expected production/staging verification flow was run:

```bash
python manage.py migrate
python manage.py backfill_church_structure_memberships --dry-run
python manage.py backfill_church_structure_memberships --apply
python manage.py backfill_church_structure_memberships --dry-run
```

User confirmed the run completed without issue.

No unresolved warnings, errors, or data QA items were reported.

No exact numeric summary is recorded because exact command output was not provided.

## 4. Verification Result

Status: Passed by user confirmation.

Idempotency: Passed by user confirmation.

No unresolved production data QA item was reported.

No runtime behavior switch occurred.

CS-H.5E follow-up:
- Django Admin clarity was improved so legacy current-runtime structure models and future structure/membership foundation models are easier to distinguish.
- Legacy `MinistryContext`, `District`, `SmallGroup`, and `Profile.small_group` must not be deleted during this transition.
- Custom staff admin UI remains future work.

## 5. Runtime Behavior Confirmation

CS-H.5D did not change:
- `Profile.small_group`
- `/studies/` visibility at the time of CS-H.5D; historical note: `/studies/` v2 meeting visibility now uses active primary `ChurchStructureMembership` after CS-CORE.2C-B, while legacy `BibleStudySession` remains unchanged
- Reading group progress, which still uses `Profile.small_group` / `SmallGroup`
- `BibleStudySeries` scope behavior
- `ServiceEvent` scope behavior at the time of CS-H.5D; historical note: ServiceEvent structure-audience rows now match by active primary `ChurchStructureMembership` after CS-CORE.2B-A, while zero-row events still use legacy fallback
- My Serving / `TeamAssignment` behavior
- signup/onboarding
- admin approval workflow
- audience selection
- filtering
- permissions

At the time of CS-H.5D, membership was not yet a runtime source. Current state: membership is now the runtime source only for explicitly switched consumers: ServiceEvent structure-audience rows, Bible Study v2 audience rows / `/studies/` / Today / role-worship pickers, Prayer group requests, group-progress roster/default/ordinary own-group access, and reflection read/write paths. Legacy `BibleStudySession`, TeamAssignment / My Serving, staff capabilities, role assignments, and legacy fields/tables remain separate. ServiceEvent zero-row events fail closed for ordinary users after SE-RETIRE.1B; legacy ServiceEvent scope fields remain stored/admin/display/audit data until field-level retirement.

Requested membership still does not grant visibility.

Backfilled membership does not grant permissions or serving assignments.

CS-H.5E also does not change runtime behavior. It only clarifies Django Admin labels/help text/list displays for staff clarity.

## 6. Go / No-Go

CS-H.5D production/staging backfill verification: Go, based on user confirmation.

Runtime source-of-truth switch at CS-H.5D time: No-Go / not authorized. Current note: later CS-CORE slices explicitly switched only ServiceEvent structure-audience rows and Bible Study v2 `BibleStudyMeeting` visibility.

Signup approval workflow: not started.

Consumer migration at CS-H.5D time: not started. Current note: ServiceEvent structure-audience row matching and Bible Study v2 meeting visibility have since switched; additional consumers still require separate approval.

Audience selection/filtering: not started.

## 7. Data QA Notes

No unresolved unmapped-group or warning item was reported.

If future issues are discovered, fix source legacy mapping/profile data first, then rerun dry-run/apply as needed.

Do not manually force runtime consumers to membership because of backfill.

## 8. Next Step

Recommended next design step:
- CS-H.6 Signup Requested-Unit Flow Design Doc, or
- CS-H.7 Admin Approval Workflow Design Doc,

Choose based on current product priority.

Historical note: `/studies/` v2 meeting visibility has since migrated in CS-CORE.2C-B. Do not migrate additional consumers such as reading progress without a separately approved plan.

Historical note: this CS-H.5D recommendation predated the later signup/request/admin approval slices and the CS-CORE consumer switches. Further migration from `Profile.small_group` should still wait for a separately approved consumer plan and explicit fallback or fail-closed behavior.

## 9. Deferred Items

Deferred:
- signup requested-unit flow
- admin approval workflow
- membership-driven visibility beyond the explicitly switched ServiceEvent structure-audience and Bible Study v2 meeting-visibility consumers
- audience selection
- `ServiceEvent` filtering
- Community Activities
- Staff Admin UI
- Checklist
- scheduling/reminders/swaps/attendance
