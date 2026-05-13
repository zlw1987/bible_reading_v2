# Legacy PHP/MySQL Reading Plan Migration Report

Source dump: `zlw1987_bible_app.sql`

## What I extracted

- `plan` table: 4 reading plans
- `s_plan` table: 636 reading-day rows
- `ongoingplan` table: legacy start dates retained in metadata
- `smallgroup` table: exported separately for reference

I did **not** migrate old users, passwords, comments, or check-ins. Those include private and/or spiritually sensitive data and should not be bulk-imported without an explicit policy decision.

## Generated files

- `data/import/legacy_svca_plans/plan_1_2022-SVCA-plan_D.csv` — 2022-SVCA讀經計劃D / 2022-SVCA-plan D; rows: 156; day range: 1-181; missing days: 25
- `data/import/legacy_svca_plans/plan_2_2022-SVCA-plan_A.csv` — 2022-SVCA讀經計劃A / 2022-SVCA-plan A; rows: 90; day range: 1-90; missing days: 0
- `data/import/legacy_svca_plans/plan_3_2022-SVCA-plan_B.csv` — 2022-SVCA讀經計劃B / 2022-SVCA-plan B; rows: 79; day range: 1-79; missing days: 0
- `data/import/legacy_svca_plans/plan_4_2022-SVCA-plan_C.csv` — 2022-SVCA讀經計劃C / 2022-SVCA-plan C; rows: 311; day range: 2-364; missing days: 52
- `data/import/legacy_svca_plans/legacy_plan_metadata.json` — full names, descriptions, CSV paths, missing days
- `data/import/legacy_svca_plans/legacy_plan_metadata.csv` — compact metadata summary
- `data/import/legacy_svca_plans/legacy_smallgroups.csv` — reference export of old small groups
- `import_all_legacy_plans.bat` — simple Windows import commands using your existing `import_reading_plan` command
- `reading/management/commands/import_legacy_svca_plans.py` — optional command to import all plans while preserving descriptions

## Recommended import method

Copy this bundle into the root of your Django project:

```cmd
c:\dev\bible_reading_v2
```

Then run:

```cmd
python manage.py import_legacy_svca_plans --replace
```

If you want to create ActivePlan rows too, run:

```cmd
python manage.py import_legacy_svca_plans --replace --create-active-plans --start-date 2026-05-18
```

Using `--start-date 2026-05-18` avoids reusing the old 2022 run date and starts all four plans on the next Monday. Change it to your real launch date.

## If you do not want the optional command

Run the existing CSV importer with the generated batch file:

```cmd
import_all_legacy_plans.bat
```

That method imports the plan days but does not preserve the long legacy descriptions automatically.

## Data notes

- `2022-SVCA讀經計劃D` has intentional missing day numbers, mostly weekly rest/review days. First missing days: 7, 14, 21, 28, 35, 42, 49, 56, 63, 70, 77, 84, 91, 98, 105, 112, 119, 126, 133, 140, 147, 154, 161, 168, 175. Do not auto-fill these unless you want blank reading days.
- `2022-SVCA讀經計劃A` has no missing day numbers in its imported day range.
- `2022-SVCA讀經計劃B` has no missing day numbers in its imported day range.
- `2022-SVCA讀經計劃C` has intentional missing day numbers, mostly weekly rest/review days. First missing days: 8, 15, 22, 29, 36, 43, 50, 57, 64, 71, 78, 85, 92, 99, 106, 113, 120, 127, 134, 141, 148, 155, 162, 169, 176, 183, 190, 197, 204, 211. Do not auto-fill these unless you want blank reading days.

## Verification checklist

1. Run `python manage.py check`.
2. Run `python manage.py test reading -v 2`.
3. Open Django admin and confirm four `ReadingPlan` records and their `ReadingPlanDay` rows.
4. Create or verify `ActivePlan` rows with your real launch date.
5. Join one plan from the frontend and check Today, Plan Detail, and Group Progress.