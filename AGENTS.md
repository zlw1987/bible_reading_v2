# AGENTS.md

Project: bible_reading_v2 / CMS.

Work compactly. Keep changes scoped to the user's request. Optimize for token and runtime efficiency without reducing required work.

Do not commit, push, or stage files unless explicitly instructed.

## Start-of-Task Discipline

At the start of each task:

- Run `git status --short`.
- Report any pre-existing dirty files before changing anything.
- Do not modify or stage unrelated dirty files.
- Keep docs-only tasks docs-only.
- Keep code tasks out of broad roadmap rewrites unless explicitly requested.

## Python / Django Command Discipline

On Windows/local work, prefer the project interpreter:

- `.venv\Scripts\python.exe`

Use it for Django commands unless there is a clear reason not to.

Examples:

- `.venv\Scripts\python.exe manage.py makemigrations --check`
- `.venv\Scripts\python.exe manage.py check`
- `.venv\Scripts\python.exe manage.py test accounts -v 2`

If using `python` instead of `.venv\Scripts\python.exe`, report which interpreter is being used or why `.venv` was not used.

## Verification

Prefer targeted tests during development.

Do not run the full project test suite unless explicitly requested.

For code, model, form, view, URL, template, or CSS changes where applicable, always run:

- `.venv\Scripts\python.exe manage.py makemigrations --check`
- `.venv\Scripts\python.exe manage.py check`

For accounts changes:

- `accounts` tests may exceed 10 minutes.
- If running `accounts` app tests, start with timeout >= 900 seconds / 15 minutes.
- Do not run accounts tests with a 2-minute timeout first.
- Do not rerun only because the first timeout was too short.
- If a long-timeout app test still exceeds 15 minutes, stop and report partial output.

For UI or browser behavior changes:

- Perform explicit browser and mobile QA before commit.
- If browser automation is unavailable, report the limitation clearly and say whether manual QA is still required.

## Windows Browser QA / Playwright Fallback

Keep the Django/Python app environment separate from the Node/Playwright browser QA runtime.

- Use the project Python interpreter: `E:\bible-reading\bible_reading_v2\.venv\Scripts\python.exe`
- Start Django with `--noreload`: `.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000 --noreload`
- Prefer the official Codex browser control workflow first when browser QA is required.
- If the in-app browser fails because of the Windows sandbox/browser startup issue, use the headless Chromium fallback.
- Do not install Node dependencies in this Django repo for browser QA.
- Do not create `package.json`, `package-lock.json`, or `node_modules` in this repo only for Playwright/browser QA.
- Use the external browser QA runtime: `C:\dev\codex-browser-qa`
- When running Node/Playwright scripts from this repo, set `$env:NODE_PATH = "C:\dev\codex-browser-qa\node_modules"`.
- If using Codex's bundled Node executable, still set the same `NODE_PATH`.
- Do not rely on Codex cached runtime paths or partial bundled Playwright shims.
- Temporary browser QA helper scripts may be created only when necessary.
- Temporary browser QA helper scripts must be narrow in purpose and removed before the final report.
- Browser QA must not create QA users or seed ministry/business data unless explicitly authorized.
- Creating an authenticated session row for an existing staff account is allowed only for QA login/session purposes, and must be reported clearly.

Reason:

- The Django/Python environment is the source of truth for app checks.
- Browser QA dependencies are intentionally externalized to avoid polluting this Django repo with Node artifacts.
- The Windows Codex browser sandbox can fail, so fallback QA should be deterministic instead of repeatedly searching cached runtime/plugin paths.

## QA Data Seeding

- Do not use long inline PowerShell commands to run `manage.py shell -c` for QA data seeding.
- Do not create QA users, set passwords, or insert dev DB records through long PowerShell one-liners.
- Endpoint security may flag PowerShell plus long inline scripts plus user creation, password setting, or database writes as malicious-looking behavior.
- Prefer Django tests, factories, fixtures, existing test setup, or the app UI for QA data.
- For browser/manual QA that needs seeded data, use existing safe dev data if available.
- If seeded data is unavoidable, create a short reviewed Django management command or fixture only when explicitly authorized.
- If a one-off shell command is unavoidable, keep it short and transparent, and ask or report before running it.
- Never bypass endpoint security.
- Never suggest disabling Netgear Armor, antivirus, or endpoint protection.

## Planning Discipline

For schema/model/migration changes, permission changes, source-of-truth changes, cross-app workflow changes, or new staff workflows:

- Do a docs/design plan first unless the prompt explicitly authorizes implementation.
- Do not jump directly into implementation from vague product feedback.
- Record real pilot feedback in backlog/planning docs before implementation when it changes model, workflow, permissions, or module boundaries.

For docs-only planning tasks:

- Do not create a separate meta-plan unless asked.
- Directly inspect the relevant docs and update the requested planning documents.
- Keep the update compact and scoped.

## UI / UX Wording Guardrails

Normal-user UI:

- Do not expose internal model names, IDs, codes, enum values, field names, source-of-truth language, runtime/foundation/legacy architecture terms, or implementation language.
- Use pastoral/user-intent wording.
- Keep EN/ZH copy paired and natural.
- Do not translate user data, enum values, or identifiers unless the UI already has explicit localized labels.

Staff/admin UI:

- Staff UI may show operational transition context when it helps safe decisions.
- Use staff workflow language, not architecture-doc language.
- Avoid labels like “future foundation,” “runtime source of truth,” or “legacy sync target” in visible UI unless the user explicitly asks for technical wording.
- Clearly distinguish current active group data from approval/membership records when both appear together.
- Notes and admin copy must avoid sensitive pastoral, medical, financial, or counseling details unless explicitly authorized.

## Project Constraints

Do not migrate these consumers from `Profile.small_group` to `ChurchStructureMembership` unless explicitly authorized:

- `/studies/`
- Reading progress
- `ServiceEvent`
- My Serving
- Other existing consumers that currently use legacy models or `Profile.small_group`

Do not add the following unless explicitly authorized:

- Audience filtering
- Community Activities implementation
- Notifications
- Attendance
- Announcements
- Care workflows
- File center
- Permission matrix expansion
- Availability
- Swap requests
- Reminder automation
- Checklist engine
- Automatic scheduling engine
- LightingTeam-specific model
- ChurchStructureMembership-based serving role inference

Keep ServiceEvent, MinistryTeam, TeamAssignment, and My Serving workflows generic unless a separate plan authorizes a narrower workflow.

Real pilot feedback has priority over speculative roadmap work, but pilot feedback must not bypass the explicit non-goals above without a separate planning decision.

## Final Report Format

Keep reports compact. Include:

- Files changed
- Behavior changed or preserved
- Verification commands and results
- Browser/mobile QA status when UI changed
- Any pre-existing dirty files left untouched
- Whether runtime behavior changed

Do not claim browser/mobile QA passed if it was blocked or only partially completed.