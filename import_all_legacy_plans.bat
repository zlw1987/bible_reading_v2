@echo off
REM Run this file from your Django project root: c:\dev\bible_reading_v2
REM It imports the four legacy SVCA reading plans from normalized CSV files.

python manage.py import_reading_plan --name "2022-SVCA讀經計劃D" --file "data\import\legacy_svca_plans\plan_1_2022-SVCA-plan_D.csv" --replace
python manage.py import_reading_plan --name "2022-SVCA讀經計劃A" --file "data\import\legacy_svca_plans\plan_2_2022-SVCA-plan_A.csv" --replace
python manage.py import_reading_plan --name "2022-SVCA讀經計劃B" --file "data\import\legacy_svca_plans\plan_3_2022-SVCA-plan_B.csv" --replace
python manage.py import_reading_plan --name "2022-SVCA讀經計劃C" --file "data\import\legacy_svca_plans\plan_4_2022-SVCA-plan_C.csv" --replace
