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
* ServiceEvent legacy `scope_type`, `district`, and `small_group` fields were removed in `SE-FIELD-RETIRE.1A` (migration `events/0007`); their cleanup/backfill/fallback-audit tooling was retired with them. This did not touch `host_language_unit`, `ServiceEventAudienceScope`, or the `SmallGroup`/`District` tables.
* The legacy ServiceEvent Host / Language display FK `ServiceEvent.ministry_context` was removed in `SERVICE-EVENT-CONTEXT.1C` (migration `events/0008`); Host / Language display now uses `ServiceEvent.host_language_unit` plus the audience-derived structure fallback. Its display-only cleanup/backfill tooling (`backfill_service_event_host_language_units`, `cleanup_service_event_ministry_context_labels`) was retired with the field. This did not remove the `MinistryContext` table, `MinistryContext.church_structure_unit`, `host_language_unit`, or `ServiceEventAudienceScope`.
* Prayer group visibility uses `PrayerRequest.structure_unit_at_post` plus active primary membership.
* Bible Study V2 uses `BibleStudyMeetingAudienceScope` rows plus active primary membership for ordinary visibility, Today/landing, and role/worship pickers.
* Bible Study V2 zero-row meetings fail closed.
* Bible Study schedule audience/eligibility uses `BibleStudySeriesAudienceScope` rows; normal generation is structure-unit-native and fails closed on zero rows. The legacy `BibleStudySeries.scope_type`, `ministry_context`, `district`, and `small_group` fields were removed in `BS-SERIES-FIELD-RETIRE.1A` (migration `studies/0010`); `get_eligible_small_groups()` resolves audience rows only, and the `cleanup_bible_study_series_legacy_scope_fields` command was retired with the fields. This did not remove V1 `BibleStudySession`, or the `SmallGroup`/`District`/`MinistryContext` tables.
* The legacy `BibleStudyMeeting.small_group` mirror FK was removed in `BS-MEETING-MIRROR.1A` (migration `studies/0011`) after preflight audits confirmed zero populated values and no live runtime/visibility/display/admin/generation dependency. V2 meeting visibility remains `BibleStudyMeetingAudienceScope` rows plus active primary `ChurchStructureMembership`; normal generation stays structure-unit-native via `generation_key` and `anchor_unit`. The mirror cleanup command (`cleanup_bible_study_v2_small_group_mirrors`), the one-time mirror→audience backfill (`backfill_bible_study_meeting_audience_scopes`), and the legacy-vs-membership shadow audit (`audit_bible_study_membership_readiness`) were retired with it. This did not remove `BibleStudyMeetingAudienceScope`, `anchor_unit`, `generation_key`, V1 `BibleStudySession`, or the `SmallGroup`/`District`/`MinistryContext` tables.
* V1 `BibleStudySession` app runtime is retired.
* The active V1 Django Admin surface was retired in `BS-V1-ADMIN-RETIRE.1A`: `BibleStudySessionAdmin` and the V1-only `BibleStudyGuideAdmin` / `BibleStudyWorshipSongAdmin` were unregistered in `studies/admin.py`. This was admin-only — no V1 data deleted, no V1 model/table/field removed, purge not applied. The schema-retirement audit now classifies V1 `BibleStudySession` as `blocked_by_diagnostic_tooling` rather than `blocked_by_display_or_admin`. V1 model/table/schema removal remains a later separate slice; do not re-register these admins, and the V2 `BibleStudyMeeting` admin is unaffected.
* Guarded V1 purge tooling exists; do not run destructive purge/apply unless explicitly approved.
* V2 `BibleStudyMeeting` is the active Bible Study path.
* V2 generation-key backfill tooling exists; do not run apply commands unless explicitly approved.
* Role scoped validation uses explicit `ChurchRoleAssignment.structure_unit`.
* Group progress and reflection migrated paths no longer rely on `Profile.small_group` for ordinary access.
* `Profile.small_group` was removed in `PROFILE-SG-FIELD-RETIRE.1A` (migration `accounts/0012`) after preflight audits confirmed zero populated values and no live runtime/app-write/display dependency. `ChurchStructureMembership` is the canonical user belonging source for migrated runtime paths; normal app-level membership approval/profile flows do not write any legacy profile group field. The profile cleanup command (`cleanup_profile_small_group`), the belonging drift audit (`audit_structure_belonging`), the membership backfill (`backfill_church_structure_memberships`), and the group-progress shadow diagnostic (`audit_group_progress_shadow`) were retired with the field. This did not remove the `SmallGroup`, `District`, or `MinistryContext` tables, and did not affect ServiceEvent, Prayer, Reflection, Role, Bible Study, TeamAssignment, or V1 schema.
* Guarded V1 purge tooling exists; do not run destructive purge/apply unless explicitly approved.
* V2 generation-key backfill tooling exists; do not run apply commands unless explicitly approved.

Legacy objects still exist:

* `SmallGroup`
* `District`
* `MinistryContext`
* V1 `BibleStudySession` legacy scope fields (`scope_type`/`district`/`small_group`); the V2 `BibleStudyMeeting.small_group` mirror was removed in `BS-MEETING-MIRROR.1A`

Removed legacy fields (do not reintroduce):

* `ChurchRoleAssignment.district` / `ChurchRoleAssignment.small_group` removed in `ROLE-FIELD-RETIRE.1A` (migration `accounts/0011`); scoped-role runtime uses `ChurchRoleAssignment.structure_unit` only.
* `Profile.small_group` removed in `PROFILE-SG-FIELD-RETIRE.1A` (migration `accounts/0012`); belonging is `ChurchStructureMembership`.

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
