# AGENTS.md — Bible Reading V2 / CMS

This file contains standing instructions for AI coding agents working in this repo.

## Project priority

The current top priority is finishing the new Church Structure migration and retiring the old structure compatibility layer.

Primary goal:

* Move all approved runtime consumers to `ChurchStructureUnit` / `ChurchStructureMembership`.
* Retire legacy runtime authority from:

  * `Profile.small_group`
  * `SmallGroup`
  * `District`
  * `MinistryContext`
  * legacy scope fields
  * fallback bridges
* Do not shift to unrelated UI/UX, new product features, or polish work unless explicitly requested.

Do not delete legacy fields/models/tables just because they look unused. Field/table retirement requires audit, backfill/purge readiness, explicit approval, targeted tests, and a separate migration slice.

## Repo and workflow

Repo path:

`E:\bible-reading\bible_reading_v2`

Default current workflow:

* Work directly on `master` only when the user explicitly asks.
* Start every task with:

  * `git status --short`
  * `git fetch origin`
  * `git merge --ff-only origin/master`
  * `git status --short`
* If the tree is dirty before the task, stop and report the dirty files.
* Do not stage, commit, or push unless the user explicitly asks.
* Never commit local DB files, backups, logs, or generated artifacts not required by the task.
* End every task with:

  * files changed
  * tests/checks run
  * `git diff --stat`
  * `git status --short`
  * confirmation of no stage/commit/push

## Testing rules

Do not run the full test suite unless explicitly required.

Prefer targeted checks:

* `E:\bible-reading\bible_reading_v2\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run`
* `E:\bible-reading\bible_reading_v2\.venv\Scripts\python.exe manage.py check`
* focused Django test classes/modules for the changed app
* command dry-runs for management command work
* `git diff --check`

If a full suite seems necessary, explain why first and wait for approval.

## Data mutation rules

Dry-run first for every backfill, purge, audit, or data-changing command.

Do not run `--apply` unless the user explicitly approves the exact command.

Destructive commands must be guarded by:

* dry-run default
* explicit `--apply`
* an additional confirmation flag when deleting data

Never mutate GoDaddy/local data silently.

Report data mutation separately from code changes.

Never commit SQLite DB files or DB backups.

## Current Church Structure migration state

`ChurchStructureUnit` and `ChurchStructureMembership` are the new structure model.

`ChurchStructureMembership` is now the runtime belonging source for approved migrated consumers. Do not broadly say membership is “future only.”

Already migrated consumers must not be reverted to `Profile.small_group`.

New or unapproved consumers must not start using membership without an explicit migration slice.

Current migrated/runtime-retired state:

* ServiceEvent audience-row visibility uses active primary `ChurchStructureMembership`.
* ServiceEvent zero-row events fail closed for ordinary users after `SE-RETIRE.1B`.
* ServiceEvent legacy `scope_type`, `district`, and `small_group` fields remain stored/admin/display/backfill/audit/rollback context only.
* Prayer group visibility uses `PrayerRequest.structure_unit_at_post` plus active primary membership.
* `PrayerRequest.small_group_at_post` was removed in `PRAYER-MIRROR.1D` (migration `prayers/0004`); its cleanup command (`cleanup_prayer_small_group_mirrors`) and the `resolve_legacy_small_group_mirror` helper were retired with it. Prayer group visibility is fully structure-native; `Profile.small_group` and legacy `SmallGroup` no longer participate in prayer visibility, writes, display, admin, cleanup, or schema. This was a prayer-only field removal and does not remove the `SmallGroup` table.
* Bible Study V2 `BibleStudyMeeting` visibility, `/studies/` / Today pre-filtering, and role/worship pickers use audience rows plus active primary membership.
* Bible Study V2 zero-row meetings fail closed for ordinary users.
* V1 `BibleStudySession` app-level runtime is retired.
* V2 `BibleStudyMeeting` is the active Bible Study path.
* V1 `BibleStudySession` is not being migrated to membership-core.
* V1 purge tooling exists as guarded, dry-run-first cleanup.
* V2 generation-key backfill tooling exists for structure-native `generation_key` / safe `anchor_unit`; local/dev V2 meetings have already been backfilled, and target DBs should be verified with dry-run/audit before any apply; local/dev V2 meetings have already been backfilled, and target DBs should be verified with dry-run/audit before any apply.
* Role scoped validation is structure-unit-native through `ChurchRoleAssignment.structure_unit`, the sole scoped-role runtime source.
* `ChurchRoleAssignment.district` and `ChurchRoleAssignment.small_group` were removed in `ROLE-FIELD-RETIRE.1A` (migration `accounts/0011`). The `backfill_structure_role_scopes` command and the `resolve_role_assignment_structure_unit_for_diagnostics` helper were retired with them; `audit_structure_role_scopes` now validates explicit `structure_unit` readiness only. Only immutable historical migrations still name these fields.
* Group progress migrated consumers no longer receive ordinary access from `Profile.small_group`.
* Reflection group read/write paths use structure snapshots and active primary membership.
* `Profile.small_group`, `SmallGroup`, `District`, and `MinistryContext` still exist and must not be deleted until audits/backfills/purges and field-level retirement slices prove safe.

## Serving is separate from belonging

Membership/belonging must not imply:

* TeamAssignment
* My Serving
* staff capabilities
* role grants
* ministry serving assignments
* schedule ownership

Do not infer serving from `ChurchStructureMembership`.

TeamAssignment / My Serving remain separate serving concepts.

## Bible Study direction

V2 `BibleStudyMeeting` is the active Bible Study product path.

V1 `BibleStudySession` is retired from app runtime:

* Do not revive V1 app-level detail/edit/delete/worship routes.
* Do not migrate V1 to membership-core.
* Do not treat V1 as a long-term app archive surface.
* V1 pilot/archive rows may be purged only through explicit guarded cleanup; the purge command may exist before it has been applied to a given DB; the purge command may exist before it has been applied to a given DB.
* V1 model/table/schema removal remains a later migration slice.

For V2:

* Audience rows are the runtime source for ordinary visibility.
* `BibleStudyMeeting.small_group` is legacy mirror/display/history/secondary compatibility until retired by a separate slice.
* Do not delete or null `small_group` without explicit approval and audit readiness.
* Do not change V2 generation/runtime semantics while doing display/docs/audit cleanup.

## Management command rules

Read-only audit commands:

* must not mutate data
* must not offer `--apply`
* may offer `--fail-on-blockers`
* must clearly distinguish runtime blockers, data blockers, admin/display leftovers, and historical/diagnostic references
* Before any approved `--apply`, rerun the command in dry-run mode against the exact target DB and review blockers/output.

Backfill commands:

* dry-run by default
* no `--apply` unless explicitly approved
* should report `data_mutated`
* should report whether runtime behavior changed
* should preserve legacy mirrors unless the task explicitly retires them
* Before any approved `--apply`, rerun the command in dry-run mode against the exact target DB and review blockers/output.

Purge commands:

* dry-run by default
* must require `--apply`
* destructive cleanup should require an additional confirmation flag
* must prove V2/current-product data is protected

`--limit` should normally limit verbose examples only. It must not silently narrow scan/apply scope unless the option is explicitly documented as a scope filter. Use explicit filters such as `--id`, `--meeting-id`, `--lesson-id`, or similar for scope narrowing.

## Documentation rules

Update docs after completed migration milestones.

Do not leave stale current-state wording in docs.

Historical wording is allowed only when clearly labeled as historical or superseded.

Docs must distinguish:

* runtime source
* stored mirror
* admin display
* audit/backfill support
* rollback context
* data/table retirement blocker
* schema/model deletion blocker

## UI and copy rules

Keep staff-facing wording operational and non-sensitive.

Avoid exposing internal model names, database IDs, implementation terms, or source-of-truth language to ordinary users unless explicitly required.

For bilingual UI/copy, keep English and Chinese meaning aligned.

Do not redesign UI during backend migration tasks unless explicitly requested.

## Browser / UI QA rules

Do not claim browser/manual QA was performed unless it actually was.

Use browser validation only when the task changes rendered UI, JavaScript behavior, layout, form interaction, or user-visible route behavior that cannot be trusted from tests alone.

For backend/data/docs-only tasks, browser QA is usually not required.

## Skills and plugins policy

Default: do not use plugins.

Default Django backend/data/docs tasks do not require a special skill.

Use Browser / Frontend Testing Debugging only when the task explicitly includes rendered UI/browser QA.

Use OpenAI Docs only for OpenAI/Codex official behavior questions.

Do not use image/video/design plugins for CMS migration tasks unless explicitly requested.

Do not connect, install, or use third-party plugins without explicit user approval.

Do not add new skills/plugins as part of repo work unless explicitly requested.

## Task-fit and scope discipline

Before implementing, check whether the request matches the current project priority.

If the prompt would move away from Church Structure migration, point that out unless the user explicitly chooses the detour.

Keep changes narrow and reversible.

Do not silently fix unrelated issues. Put unrelated discoveries in the final report.

When uncertain, stop and ask or report a task-fit concern.

## Final report format

Every coding task final report should include:

* starting branch/path/status
* sync result
* files changed
* behavior changed
* tests/checks run and results
* commands run and whether they were dry-run or apply
* data mutation status
* migrations generated or not
* remaining blockers
* discovery log / proposed follow-ups
* confirmation of no stage/commit/push unless explicitly approved
