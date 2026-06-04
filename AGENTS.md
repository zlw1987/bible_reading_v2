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

## Project Constraints

- Do not migrate `/studies/`, Reading progress, `ServiceEvent`, My Serving, or other consumers from `Profile.small_group` to `ChurchStructureMembership` unless explicitly authorized.
- Do not add audience filtering or Community Activities unless explicitly authorized.
- Do not rewrite broad roadmap docs unless necessary.
