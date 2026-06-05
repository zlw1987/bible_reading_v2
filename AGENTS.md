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

## Windows Browser QA / Playwright Fallback

For browser QA on Windows, keep the Django/Python app environment separate from the Node/Playwright browser QA runtime.

- Use the project Python interpreter: `E:\bible-reading\bible_reading_v2\.venv\Scripts\python.exe`
- For local browser QA, start Django with `--noreload`: `.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000 --noreload`
- Prefer the official Codex browser control workflow first when browser QA is required.
- If the in-app browser fails because of the Windows sandbox/browser startup issue, use the headless Chromium fallback.
- Do not install Node dependencies in this Django repo for browser QA.
- Do not create `package.json`, `package-lock.json`, or `node_modules` in this repo only for Playwright/browser QA.
- Use the external browser QA runtime: `C:\dev\codex-browser-qa`
- When running Node/Playwright scripts from this repo, set: `$env:NODE_PATH = "C:\dev\codex-browser-qa\node_modules"`
- If using Codex's bundled Node executable, still set the same `NODE_PATH`; do not rely on Codex cached runtime paths or partial bundled Playwright shims.
- Temporary browser QA helper scripts may be created only when necessary, must be narrow in purpose, and must be removed before the final report.
- Browser QA must not create QA users or seed ministry/business data unless explicitly authorized.
- Creating an authenticated session row for an existing staff account is allowed only for QA login/session purposes, and must be reported clearly.

Reason:

- The Django/Python environment is the source of truth for app checks.
- Browser QA dependencies are intentionally externalized to avoid polluting this Django repo with Node artifacts.
- The Windows Codex browser sandbox can fail, so fallback QA should be deterministic instead of repeatedly searching cached runtime/plugin paths.

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
