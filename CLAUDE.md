# CLAUDE.md — Bible Reading V2 / CMS

`AGENTS.md` is the canonical instruction file. If this file conflicts with `AGENTS.md`, follow `AGENTS.md`.

This file only adds Claude-specific reminders.

## Project priority

The current top priority is finishing the new Church Structure migration and retiring the legacy structure compatibility layer.

Do not drift into unrelated UI/UX, new product features, or broad cleanup unless explicitly requested.

## Current structure migration cautions

Do not reintroduce `Profile.small_group` as runtime authority for already-migrated consumers.

Current state:

* ServiceEvent audience rows use active primary `ChurchStructureMembership`.
* ServiceEvent zero-row ordinary-user fallback is retired; zero-row events fail closed.
* Prayer group visibility uses `PrayerRequest.structure_unit_at_post` plus active primary membership.
* Bible Study V2 uses `BibleStudyMeetingAudienceScope` rows plus active primary membership for ordinary visibility, Today/landing, and role/worship pickers.
* Bible Study V2 zero-row meetings fail closed.
* V1 `BibleStudySession` app runtime is retired.
* Guarded V1 purge tooling exists; do not run destructive purge/apply unless explicitly approved.
* V2 `BibleStudyMeeting` is the active Bible Study path.
* V2 generation-key backfill tooling exists; do not run apply commands unless explicitly approved.
* Role scoped validation uses explicit `ChurchRoleAssignment.structure_unit`.
* Group progress and reflection migrated paths no longer rely on `Profile.small_group` for ordinary access.
* Guarded V1 purge tooling exists; do not run destructive purge/apply unless explicitly approved.
* V2 generation-key backfill tooling exists; do not run apply commands unless explicitly approved.

Legacy fields still exist:

* `Profile.small_group`
* `SmallGroup`
* `District`
* `MinistryContext`
* ServiceEvent legacy scope fields
* Bible Study legacy/mirror fields
* reflection/prayer legacy mirror fields

Removed role legacy fields (do not reintroduce): `ChurchRoleAssignment.district` and `ChurchRoleAssignment.small_group` were removed in `ROLE-FIELD-RETIRE.1A` (migration `accounts/0011`); scoped-role runtime uses `ChurchRoleAssignment.structure_unit` only.

Do not delete legacy fields/models/tables without a separately approved field/table retirement slice.

## Membership is not serving

`ChurchStructureMembership` is belonging, not serving.

Do not infer TeamAssignment, My Serving, staff capability, role grants, or ministry serving schedule from membership.

Serving and role assignment remain separate concepts.

## Workflow

Work only on the explicit task.

Start with:

* `git status --short`
* `git fetch origin`
* `git merge --ff-only origin/master`
* `git status --short`

If the tree is dirty before the task, stop and report.

Do not stage, commit, or push unless the user explicitly asks.

Never commit DB files, backups, logs, or unrelated generated files.

## Testing

Do not run the full test suite unless explicitly approved.

Prefer targeted tests:

* `E:\bible-reading\bible_reading_v2\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run`
* `E:\bible-reading\bible_reading_v2\.venv\Scripts\python.exe manage.py check`
* focused Django test classes/modules
* dry-run management commands when relevant
* `git diff --check`

Do not claim browser/manual QA unless actually performed.

## Data safety

Dry-run first.

Do not run `--apply` unless explicitly approved.

Destructive commands must require explicit confirmation.

Do not mutate local or GoDaddy data silently.

Report any data mutation separately from code changes.

## Skills / plugins

Do not use plugins by default.

Do not connect third-party plugins unless the user explicitly approves.

Use Browser / Frontend Testing Debugging only for rendered UI/browser QA tasks.

Use OpenAI Docs only for OpenAI/Codex official behavior questions.

Most Django backend/data/docs tasks require no special skill.

## Final response

Report:

* files changed
* behavior changed
* targeted tests/checks run
* migrations generated or not
* data mutation status
* unresolved blockers
* discovery log
* confirmation of no stage/commit/push unless explicitly approved

If a task request conflicts with current Church Structure migration priority or risks reverting completed migration work, stop and say so.
