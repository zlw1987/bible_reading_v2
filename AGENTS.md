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
* ServiceEvent legacy `scope_type`, `district`, and `small_group` fields were removed in `SE-FIELD-RETIRE.1A` (migration `events/0007`) after `SE-RETIRE.1B` retired the zero-row runtime fallback and local/dev audit confirmed zero populated legacy scope fields. ServiceEvent visibility remains `ServiceEventAudienceScope` rows plus active primary `ChurchStructureMembership`; zero-row events stay fail-closed for ordinary users. The legacy-scope tooling (`cleanup_service_event_legacy_scope_fields`, `backfill_service_event_audience_scopes`, `audit_service_event_fallback_retirement_readiness`) was retired with the fields. This did not affect `ServiceEvent.ministry_context`, `host_language_unit`, `ServiceEventAudienceScope`, or the `SmallGroup` / `District` tables. Only immutable historical migrations still name these fields.
* The legacy ServiceEvent Host / Language display FK `ServiceEvent.ministry_context` was removed in `SERVICE-EVENT-CONTEXT.1C` (migration `events/0008`) after prior SERVICE-EVENT-CONTEXT slices stopped normal app writes, added `host_language_unit`, and local/dev audit confirmed zero populated `ministry_context` rows. Host / Language display now uses `ServiceEvent.host_language_unit` and, when blank, an audience-derived structure fallback (walking `ServiceEventAudienceScope` units up to the nearest ministry-context unit). The display-only cleanup/backfill tooling (`backfill_service_event_host_language_units`, `cleanup_service_event_ministry_context_labels`) was retired with the field, and its references were removed from the umbrella/schema retirement audits and from `cleanup_legacy_structure_parent_links`. This did not remove the `MinistryContext` table, `MinistryContext.church_structure_unit`, `ServiceEvent.host_language_unit`, or `ServiceEventAudienceScope`; ServiceEvent visibility and zero-row fail-closed behavior are unchanged. Only immutable historical migrations still name the field.
* Prayer group visibility uses `PrayerRequest.structure_unit_at_post` plus active primary membership.
* `PrayerRequest.small_group_at_post` was removed in `PRAYER-MIRROR.1D` (migration `prayers/0004`); its cleanup command (`cleanup_prayer_small_group_mirrors`) and the `resolve_legacy_small_group_mirror` helper were retired with it. Prayer group visibility is fully structure-native; `Profile.small_group` and legacy `SmallGroup` no longer participate in prayer visibility, writes, display, admin, cleanup, or schema. This was a prayer-only field removal and does not remove the `SmallGroup` table.
* Bible Study V2 `BibleStudyMeeting` visibility, `/studies/` / Today pre-filtering, and role/worship pickers use audience rows plus active primary membership.
* Bible Study V2 zero-row meetings fail closed for ordinary users.
* Bible Study schedule audience/eligibility uses `BibleStudySeriesAudienceScope` rows; normal generation is structure-unit-native and fails closed on zero audience rows. The legacy `BibleStudySeries.scope_type`, `ministry_context`, `district`, and `small_group` fields were removed in `BS-SERIES-FIELD-RETIRE.1A` (migration `studies/0010`) after `BS-SERIES-SCOPE.1A/1B` stopped writes and cleared values; `BibleStudySeries.get_eligible_small_groups()` resolves audience rows only, and the `cleanup_bible_study_series_legacy_scope_fields` command was retired with the fields. This did not remove `BibleStudyMeeting.anchor_unit`, `generation_key`, `BibleStudySeriesAudienceScope`, `BibleStudyMeetingAudienceScope`, V1 `BibleStudySession`, or the `SmallGroup` / `District` / `MinistryContext` tables. Only immutable historical migrations still name these fields.
* The legacy `BibleStudyMeeting.small_group` mirror FK was removed in `BS-MEETING-MIRROR.1A` (migration `studies/0011`) after preflight audits confirmed zero populated values and no live runtime/visibility/display/admin/generation dependency. V2 meeting visibility remains `BibleStudyMeetingAudienceScope` rows plus active primary `ChurchStructureMembership`; normal generation stays structure-unit-native via `generation_key` and `anchor_unit`; display/grouping uses `anchor_unit` and audience rows. The guarded mirror cleanup command (`cleanup_bible_study_v2_small_group_mirrors`), the one-time mirror→audience backfill (`backfill_bible_study_meeting_audience_scopes`), and the legacy-vs-membership shadow audit (`audit_bible_study_membership_readiness`) were retired with the field, along with the meeting-mirror counters in the generation-bridge / schema / umbrella retirement audits. This did not remove V1 `BibleStudySession` or the `SmallGroup` / `District` / `MinistryContext` tables, and did not change `BibleStudyMeetingAudienceScope`, `anchor_unit`, or `generation_key`. Only immutable historical migrations still name the field.
* V1 `BibleStudySession` app-level runtime is retired.
* V2 `BibleStudyMeeting` is the active Bible Study path.
* V1 `BibleStudySession` is not being migrated to membership-core.
* V1 purge tooling exists as guarded, dry-run-first cleanup.
* V2 generation-key backfill tooling exists for structure-native `generation_key` / safe `anchor_unit`; local/dev V2 meetings have already been backfilled, and target DBs should be verified with dry-run/audit before any apply; local/dev V2 meetings have already been backfilled, and target DBs should be verified with dry-run/audit before any apply.
* Role scoped validation is structure-unit-native through `ChurchRoleAssignment.structure_unit`, the sole scoped-role runtime source.
* `ChurchRoleAssignment.district` and `ChurchRoleAssignment.small_group` were removed in `ROLE-FIELD-RETIRE.1A` (migration `accounts/0011`). The `backfill_structure_role_scopes` command and the `resolve_role_assignment_structure_unit_for_diagnostics` helper were retired with them; `audit_structure_role_scopes` now validates explicit `structure_unit` readiness only. Only immutable historical migrations still name these fields.
* Group progress consumers are membership-core; the legacy `Profile.small_group` field was removed in `PROFILE-SG-FIELD-RETIRE.1A` (migration `accounts/0012`). `ChurchStructureMembership` is the canonical user belonging source for migrated runtime paths. Normal app-level membership approval/profile flows do not write any legacy profile group field. The guarded profile cleanup command (`cleanup_profile_small_group`), the profile-vs-membership belonging drift audit (`audit_structure_belonging`), the membership backfill that sourced from the field (`backfill_church_structure_memberships`), and the group-progress legacy shadow diagnostic (`audit_group_progress_shadow`) were retired with the field. This did not remove the `SmallGroup`, `District`, or `MinistryContext` tables and did not affect ServiceEvent, Prayer, Reflection, Role, Bible Study, TeamAssignment, or V1 schema. Only immutable historical migrations still name the field.
* Reflection group read/write paths use structure snapshots and active primary membership.
* `ReflectionComment.small_group_at_post` was removed in `REFLECTION-MIRROR.1H` (migration `comments/0007`); its mirror cleanup commands (`cleanup_reflection_small_group_mirrors`, `cleanup_reflection_nongroup_display_mirrors`) and the legacy-mirror backfill/recovery/shadow tooling (`backfill_reflection_structure_snapshots`, `cleanup_reflection_snapshot_blockers`, `audit_reading_privacy_membership_readiness`, `reflection_privacy_shadow`) were retired with it after stored mirror data was cleared and display/admin surfaces removed. Reflection group visibility uses `ReflectionComment.structure_unit_at_post` plus active primary `ChurchStructureMembership`; `Profile.small_group` and legacy `SmallGroup` no longer participate in reflection visibility, writes, display, admin, cleanup, or schema. This was a reflection-only field removal and does not remove the `SmallGroup` table or affect Prayer, Role, ServiceEvent, Bible Study, Profile, District, or MinistryContext schema.
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

* Audience rows (`BibleStudyMeetingAudienceScope`) plus active primary `ChurchStructureMembership` are the runtime source for ordinary visibility.
* `BibleStudyMeeting.small_group` was removed in `BS-MEETING-MIRROR.1A` (migration `studies/0011`); the legacy meeting mirror no longer exists. Display/grouping uses `anchor_unit` and audience rows; normal generation stays structure-unit-native via `generation_key` and `anchor_unit`. Do not reintroduce the field.
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
