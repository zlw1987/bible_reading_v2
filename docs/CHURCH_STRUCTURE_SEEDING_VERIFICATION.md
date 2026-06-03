# Church Structure Seeding Verification

## 1. Purpose

This document records the GoDaddy production/staging execution result for CS-H.3C.

The goal was to safely seed and map existing `MinistryContext`, `District`, and `SmallGroup` data into `ChurchStructureUnit` using the explicit `seed_church_structure_units` management command.

The command is a dry-run/apply operational step. It is not an automatic migration, does not run during app startup, and does not switch runtime behavior to `ChurchStructureUnit`.

Current runtime behavior remains unchanged.

## 2. Baseline

Baseline before production/staging seeding:
- Pilot baseline: `v0.9-pilot-rc1` passed validation.
- CS-H.3B nullable legacy mapping fields existed before seeding.
- CS-H.3C `seed_church_structure_units` command was available.
- The GoDaddy deployed app already had real `MinistryContext`, `District`, and `SmallGroup` data.

## 3. Apply Result

Production/staging command:

```text
python manage.py seed_church_structure_units --apply
```

Result:
- Return code: 0.
- Created root `CHURCH`.
- Created CM and EM `MinistryContext` units.
- Created 11 district units:
  - `一区` through `九区` under Chinese Ministry.
  - `English Adult` under English Ministry.
  - `English Youth Groups` under English Ministry.
- Created 20 small-group units.
- Created 35 total `ChurchStructureUnit` rows.
- Linked 2 `MinistryContext` records.
- Linked 11 `District` records.
- Linked 20 `SmallGroup` records.
- Linked 33 total legacy records.
- Warnings: 0.

Apply summary:

```text
created: 35
updated: 0
linked: 33
skipped: 0
warnings: 0
```

Created hierarchy summary:

```text
Whole Church
-> Chinese Ministry
   -> 一区 through 九区
      -> related small groups
-> English Ministry
   -> English Adult
      -> related small groups
   -> English Youth Groups
      -> related small groups
-> Unassigned Groups
   -> Santa Clara 3
```

## 4. Idempotency Verification

Post-apply verification command:

```text
python manage.py seed_church_structure_units --dry-run
```

Result:
- Return code: 0.

Dry-run summary:

```text
would created: 0
would updated: 0
would linked: 0
skipped: 68
warnings: 0
```

Idempotency passed.

No further seed changes are pending. This confirms the command can be safely re-run without duplicate creation when the legacy structure data has not changed.

## 5. Data QA Note

`Santa Clara 3` is currently under `UNASSIGNED-GROUPS`.

Reason: the legacy `SmallGroup` record currently has no `district`.

Business decision needed:
- If `Santa Clara 3` belongs to `一区`, update the legacy `SmallGroup.district` first, then rerun `seed_church_structure_units --apply` and `seed_church_structure_units --dry-run`.
- If `Santa Clara 3` is intentionally unassigned, leave it as-is.

Do not fix this by manually moving only the `ChurchStructureUnit`, because the legacy `SmallGroup` model is still the current runtime source of truth.

## 6. Runtime Behavior Confirmation

CS-H.3D does not change:
- `Profile.small_group` behavior.
- `/studies/` visibility.
- `BibleStudySeries` scope behavior.
- `ServiceEvent` scope behavior.
- My Serving / `TeamAssignment` behavior.
- signup/onboarding.
- audience selection.
- permissions.

`ChurchStructureUnit` remains a mirror/mapped structure only.

## 7. Admin QA Checklist

- [ ] Django admin shows the `CHURCH` root.
- [ ] CM and EM appear under `CHURCH`.
- [ ] CM districts `一区` through `九区` appear under Chinese Ministry.
- [ ] `English Adult` and `English Youth Groups` appear under English Ministry.
- [ ] `SmallGroup` mapping fields are populated.
- [ ] `Santa Clara 3` appears under Unassigned Groups unless the legacy district is corrected.
- [ ] Legacy `SmallGroup` records still exist.
- [ ] `Profile.small_group` values remain unchanged.

## 8. Browser QA Checklist

- [ ] Login works.
- [ ] `/studies/` works for a user with a small group.
- [ ] `/studies/` safe empty state works for a user without a small group.
- [ ] Reading group progress still works.
- [ ] `ServiceEvent` list/detail behavior is unchanged.
- [ ] My Serving behavior is unchanged.
- [ ] Staff pages still load.

## 9. Go / No-Go

- Seeding command result: Go.
- Idempotency result: Go.
- Runtime source-of-truth switch: No-Go / not authorized.
- Membership implementation: not authorized yet.
- Audience/filtering implementation: not authorized yet.

## 10. Next Steps

Recommended next steps:
- Resolve the `Santa Clara 3` business data question if needed.
- Optionally perform CS-H.3E admin/browser sanity QA after data review.
- Then plan CS-H.4 ChurchStructureMembership Design Doc.
- Do not implement membership or signup changes until CS-H.4 design is accepted.

## 11. Deferred Items

Deferred:
- `ChurchStructureMembership` model.
- signup requested-unit flow.
- admin approval workflow.
- audience selection.
- `ServiceEvent` filtering.
- Community Activities.
- Staff Admin UI.
- Checklist.
- automatic scheduling/reminders/swaps/attendance.
