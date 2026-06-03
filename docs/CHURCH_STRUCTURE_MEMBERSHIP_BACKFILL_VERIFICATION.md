# Church Structure Membership Backfill Verification

## 1. Purpose

This document records production/staging verification of `backfill_church_structure_memberships`.

Verification is based on the user's attested GoDaddy execution. Exact command-output counts were not provided, so this document does not invent them.

Runtime behavior remains unchanged. `Profile.small_group` remains the current runtime source for Bible Study visibility, reading group progress, and current group-scoped behavior.

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

## 5. Runtime Behavior Confirmation

CS-H.5D does not change:
- `Profile.small_group`
- `/studies/` visibility, which still uses `Profile.small_group`
- Reading group progress, which still uses `Profile.small_group` / `SmallGroup`
- `BibleStudySeries` scope behavior
- `ServiceEvent` scope behavior, which still uses existing scope fields
- My Serving / `TeamAssignment` behavior
- signup/onboarding
- admin approval workflow
- audience selection
- filtering
- permissions

Membership is not yet the runtime source of truth.

Requested membership still does not grant visibility.

Backfilled membership does not grant permissions or serving assignments.

## 6. Go / No-Go

CS-H.5D production/staging backfill verification: Go, based on user confirmation.

Runtime source-of-truth switch: No-Go / not authorized.

Signup approval workflow: not started.

Consumer migration: not started.

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

Do not migrate `/studies/` or Reading progress to membership yet.

Consumer migration from `Profile.small_group` should wait until signup/request/admin approval design is accepted, or until there is a deliberate fallback plan.

## 9. Deferred Items

Deferred:
- signup requested-unit flow
- admin approval workflow
- membership-driven visibility
- audience selection
- `ServiceEvent` filtering
- Community Activities
- Staff Admin UI
- Checklist
- scheduling/reminders/swaps/attendance
