# AGENTS.md

Project: bible_reading_v2 / CMS.

Work compactly and keep changes scoped to the user's request. Prefer targeted tests during development, and do not run the full project test suite unless explicitly requested.

## Verification

For code, model, or template-related changes where applicable, always run:

```powershell
python manage.py makemigrations --check
python manage.py check
```

For accounts changes:

- `python manage.py test accounts -v 2` may exceed 10 minutes.
- Start with a timeout of at least 900 seconds / 15 minutes.
- Do not run it with a 2-minute timeout first.
- Do not rerun only because the first timeout was too short.
- If it still exceeds 15 minutes, stop and report the partial output.

For UI or browser behavior changes, perform explicit browser and mobile QA before commit.

## QA Data Seeding

- Do not use long inline PowerShell commands to run `manage.py shell -c` for QA data seeding.
- Do not create QA users, set passwords, or insert dev DB records through long PowerShell one-liners.
- Reason: endpoint security may flag PowerShell plus long inline scripts plus user creation, password setting, or database writes as malicious-looking behavior.
- Prefer Django tests, factories, fixtures, existing test setup, or the app UI for QA data.
- For browser/manual QA that needs seeded data, use existing safe dev data if available, create a short reviewed Django management command or fixture only when explicitly authorized, or report that manual QA needs seed data.
- If a one-off shell command is unavoidable, keep it short and transparent, and ask or report before running it.
- Never bypass endpoint security or suggest disabling Netgear Armor/AV.

## Project Constraints

- Do not migrate `/studies/`, Reading progress, `ServiceEvent`, My Serving, or other consumers from `Profile.small_group` to `ChurchStructureMembership` unless explicitly authorized.
- Do not add audience filtering or Community Activities unless explicitly authorized.
- Do not rewrite broad roadmap docs unless necessary.
