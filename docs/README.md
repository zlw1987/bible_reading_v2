# Documentation Index

Status: canonical documentation entry point, current through
`MODULAR-CORE.6A` and `RELEASE-HYGIENE.0A` (July 2026).

Use this page to distinguish current architecture and operating guidance from
historical design, migration, and execution records. Historical documents are
kept for decisions, rollout evidence, and rollback context; they are not current
schema or runtime instructions unless their opening status note says otherwise.

## Canonical Current-State Documents

| Area | Canonical document | What it owns |
|---|---|---|
| Product architecture and roadmap | [`PRODUCT_ARCHITECTURE_AND_ROADMAP.md`](PRODUCT_ARCHITECTURE_AND_ROADMAP.md) | Current product shape, implemented foundations, and deliberately deferred work. |
| Module boundaries | [`MODULE_BOUNDARIES.md`](MODULE_BOUNDARIES.md) | Core versus modules, registry keys, `CMS_ENABLED_MODULES`, dependencies, and present surface-gate limits. |
| Church Structure architecture | [`CHURCH_STRUCTURE_FOUNDATION_PLAN.md`](CHURCH_STRUCTURE_FOUNDATION_PLAN.md) | Current canonical structure/belonging models and the boundary between Church Structure and product-specific consumers. |
| Today versus My Serving | [`TODAY_AND_MY_SERVING_PRODUCT_BOUNDARIES.md`](TODAY_AND_MY_SERVING_PRODUCT_BOUNDARIES.md) | Agenda, personal serving, manager attention, and belonging-versus-serving rules. |
| Deployment security and release hygiene | [`DEPLOYMENT_SECURITY.md`](DEPLOYMENT_SECURITY.md) | Secure administrator bootstrap, repository hygiene completed in `RELEASE-HYGIENE.0A`, and the still-future external archive boundary. |
| Trial setup operations | [`TRIAL_SETUP_READINESS_RUNBOOK.md`](TRIAL_SETUP_READINESS_RUNBOOK.md) | Current read-only setup audit and operator review flow. |

When these documents conflict with an older plan, use the canonical document
and current code/migrations. `AGENTS.md` remains the standing agent workflow and
migration-safety instruction source.

## Current Architecture Snapshot

- `ChurchStructureUnit` is the canonical local hierarchy.
  `ChurchStructureMembership` is the canonical belonging source for approved
  migrated consumers. Belonging does not imply serving, staff authority, or
  role grants.
- Legacy `SmallGroup`, `District`, and `MinistryContext` models/tables are
  removed. `Profile.small_group` is removed. Historical migrations and
  explicitly historical documents may still name them.
- Bible Study V2 (`BibleStudySeries` + `BibleStudyLesson` +
  `BibleStudyMeeting`) is active. V1 `BibleStudySession`, `BibleStudyGuide`, and
  the V1-only `BibleStudyWorshipSong` schema are retired and removed.
- ServiceEvent ordinary visibility uses `ServiceEventAudienceScope` rows
  matched through active primary membership. Zero-row events fail closed for
  ordinary users.
- The module registry contains `reading`, `prayers`, `studies`, `events`, and
  `ministry`. `CMS_ENABLED_MODULES` defaults to all registered modules.
  Unknown keys and unmet dependencies raise `ImproperlyConfigured`;
  `ministry` requires `events`.
- Disabled modules are surface-gated: primary navigation, module-owned staff
  dropdown links, their Today aggregation/cards/actions, and the profile My
  Serving card where applicable are hidden. Today context is aggregated
  through per-module providers
  (`core/today_providers.py`, `MODULAR-CORE.3A`): enabled modules' registered
  providers are called and disabled modules keep safe default context. The
  provider bodies live in each module's `today_provider` module
  (`MODULAR-CORE.3B`), registered explicitly from `reading.views`. Setup/
  readiness checks follow the same pattern (`MODULAR-CORE.5A`,
  `core/setup_readiness.py`): the `audit_trial_setup_readiness` sections come
  from registered providers — ministry and studies own their sections, Church
  Structure / permission-admin and the always-run audience-visibility section
  stay Core — aggregated for enabled modules only, registered explicitly from
  `accounts.trial_setup_readiness`. This is not app unloading or route-level
  hard-off; direct URLs, staff overview, setup routes/checks, and admin routes
  keep their existing behavior.
- `RELEASE-HYGIENE.0A` secured the deployment admin bootstrap, expanded
  ignore rules for local secrets/databases/backups/logs/audit output, and
  removed committed local audit artifacts. It did not build an external release
  archive; that remains a separate future allowlist-based task.

## Historical Design and Execution Records

The following groups remain useful, but should be read as chronology rather
than pending work:

- Church Structure migration and retirement:
  [`CHURCH_STRUCTURE_CORE_MIGRATION_PLAN.md`](CHURCH_STRUCTURE_CORE_MIGRATION_PLAN.md),
  [`CHURCH_STRUCTURE_MAPPING_AND_MEMBERSHIP_STRATEGY.md`](CHURCH_STRUCTURE_MAPPING_AND_MEMBERSHIP_STRATEGY.md),
  [`LEGACY_STRUCTURE_RETIREMENT_EXECUTION_PLAN.md`](LEGACY_STRUCTURE_RETIREMENT_EXECUTION_PLAN.md),
  and the signup/profile/membership transition plans.
- Bible Study evolution:
  [`BIBLE_STUDY_V2_IMPLEMENTATION_STRATEGY.md`](BIBLE_STUDY_V2_IMPLEMENTATION_STRATEGY.md),
  [`BIBLE_STUDY_V2_GROUP_MEETING_MODEL_PLAN.md`](BIBLE_STUDY_V2_GROUP_MEETING_MODEL_PLAN.md),
  [`BIBLE_STUDY_STRUCTURE_NATIVE_MIGRATION_PLAN.md`](BIBLE_STUDY_STRUCTURE_NATIVE_MIGRATION_PLAN.md),
  and [`LEGACY_BIBLE_STUDY_SESSION_RETIREMENT_DECISION.md`](LEGACY_BIBLE_STUDY_SESSION_RETIREMENT_DECISION.md).
- ServiceEvent audience migration:
  [`SERVICE_EVENT_AUDIENCE_SCOPE_REDESIGN_PLAN.md`](SERVICE_EVENT_AUDIENCE_SCOPE_REDESIGN_PLAN.md)
  and [`SERVICE_EVENT_AUDIENCE_RUNTIME_MIGRATION_PLAN.md`](SERVICE_EVENT_AUDIENCE_RUNTIME_MIGRATION_PLAN.md).
- Reading/reflection migration:
  [`READING_PROGRESS_REFLECTION_PRIVACY_MIGRATION_PLAN.md`](READING_PROGRESS_REFLECTION_PRIVACY_MIGRATION_PLAN.md)
  and [`READING_STRUCTURE_RUNTIME_MIGRATION_PLAN.md`](READING_STRUCTURE_RUNTIME_MIGRATION_PLAN.md).
- Roadmap ledgers and pilot-era plans:
  [`ROADMAP_REVISED_PRE_PILOT.md`](ROADMAP_REVISED_PRE_PILOT.md) and
  [`POST_PILOT_BACKLOG_TRIAGE.md`](POST_PILOT_BACKLOG_TRIAGE.md).

QA checklists tied to retired schema, especially
[`BIBLE_STUDY_V1_QA_CHECKLIST.md`](BIBLE_STUDY_V1_QA_CHECKLIST.md), are
historical evidence rather than current test instructions.

## Deferred Product Plans

Community Events/Activities and Checklist remain deferred. References in
planning documents do not mean either product has been built or approved for
implementation. Do not use this documentation as authorization to create
them, gate staff/setup routes, or extract apps into packages. (Provider-based
Today aggregation, previously listed here, was delivered as an explicitly
approved slice in `MODULAR-CORE.3A`.)
