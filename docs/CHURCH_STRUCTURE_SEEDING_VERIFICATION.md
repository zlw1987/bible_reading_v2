# Church Structure Seeding Verification

> **Historical operational evidence:** this document records the CS-H.3C
> bridge-era seed/map run. The legacy source rows and mapping bridge were later
> retired; current structure is `ChurchStructureUnit`, current belonging for
> approved migrated consumers is active primary `ChurchStructureMembership`,
> and the legacy `SmallGroup` / `District` / `MinistryContext` tables and
> `Profile.small_group` are removed. Do not rerun this historical bridge command
> as current setup guidance.

## 1. Purpose

This document records the GoDaddy production/staging execution result for CS-H.3C.

The goal was to safely seed and map existing `MinistryContext`, `District`, and `SmallGroup` data into `ChurchStructureUnit` using the explicit `seed_church_structure_units` management command.

The command is a dry-run/apply operational step. It is not an automatic migration, does not run during app startup, and does not switch runtime behavior to `ChurchStructureUnit`.

At the time of this seeding run, runtime behavior remained unchanged. That
bridge-era statement is historical; the later consumer migrations and legacy
retirement are complete.

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
   -> originally contained Santa Clara 3 before data QA closure
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

## 5. Data QA Closure

CS-H.3D recorded one remaining data QA item: `Santa Clara 3` was under `UNASSIGNED-GROUPS`.

Reason: the legacy `SmallGroup` record had no `district` at the time of the first production/staging seed.

CS-H.3E closes this item. The legacy data was corrected or otherwise handled first, rather than manually moving only the `ChurchStructureUnit`.

After resolving the legacy data issue and rerunning the seed/apply flow, this item should remain closed as long as the final dry-run reports zero create/update/link changes.

Historical/superseded caution: at this seeding-verification milestone, manually moving only the `ChurchStructureUnit` could diverge from the legacy `SmallGroup` runtime source. Current normal V2 generation is structure-native, and remaining `SmallGroup` rows/mappings are setup/admin/diagnostic/table-retirement context.

## 6. Runtime Behavior Confirmation

CS-H.3D and CS-H.3E do not change:
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
- [ ] `Santa Clara 3` no longer appears as an unresolved Unassigned Groups QA item after the legacy data correction/handling and seed rerun.
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
- Treat CS-H.3 seeded structure data QA as closed, provided the final dry-run remains clean.
- Plan CS-H.4 ChurchStructureMembership Design Doc.
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
