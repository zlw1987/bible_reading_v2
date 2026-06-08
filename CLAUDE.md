# CLAUDE.md

Root `AGENTS.md` is the canonical AI/project instruction source. Read it first. This file does not override `AGENTS.md`; if anything here appears to conflict, `AGENTS.md` wins.

## Workflow

- ChatGPT acts as planner / reviewer / scope controller.
- Claude Code acts as implementer.
- Implement only the explicit task/prompt given.
- Report uncertainty instead of expanding scope.

## Verification discipline

- Prefer targeted tests over the full suite.
- For code/model/form/view changes, run `.venv\Scripts\python.exe manage.py makemigrations --check` and `.venv\Scripts\python.exe manage.py check`.
- Run `git diff --check`.
- Do not claim browser/manual QA unless it was actually performed.

## Forbidden files

- Do not modify `AGENTS.md` unless explicitly requested.
- Do not modify `db.sqlite3`.

## Project-specific caution

- Do not conflate Audience Scope, Host / Language Label, Required Ministry Teams, Rotation Anchor Team, and TeamAssignment — they are separate concepts.
- Do not treat `ServiceEventAudienceScope` as the runtime visibility source until a future approved migration. Runtime visibility still uses legacy scope fields and `Profile.small_group`.
