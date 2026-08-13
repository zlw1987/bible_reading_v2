# Repository Audit Gap Completion Plan

Status: canonical repository-wide audit and gap roadmap for
`REPOSITORY-AUDIT-GAP-COMPLETION.1A`, with docs-only precision follow-up
`REPOSITORY-AUDIT-GAP-COMPLETION.1A-FU1`.

Date: 2026-08-11.

Scope: repository-only static and test-inventory audit. No runtime model,
migration, data, deployment, production, GoDaddy, staging, commit, push, or
module behavior change was made by this slice or FU1.

Conclusion: no repository-proven `BLOCKER` or `HIGH` issue was found. The
current codebase is suitable to continue the existing limited-trial path under
the already documented product and operational boundaries, with the open items
below handled as hardening or deliberately deferred product work. This is not a
broad production-readiness certification and does not replace live hosting
verification.

## Starting State And Sync

Original 1A starting state:

- Working directory: `C:\dev\bible_reading_v2`.
- Starting branch: `master`.
- Starting tracked state observed by `git branch -vv`: `master` at
  `e45b33ca3838bf7b840183589660c0157f63e804`, tracking `origin/master`.
- Starting `git status --short`: no file changes reported.
- `git fetch origin` could not update `.git/FETCH_HEAD` because the sandbox
  denied write access to `.git`.
- `git merge --ff-only origin/master` could not update `ORIG_HEAD` because the
  sandbox denied write access to `.git`.
- Per the task boundary, no `.git` workarounds were attempted. The 1A audit
  continued from the clean cached tracking state visible locally.

FU1 starting state:

- The dirty tree was expected and preserved:
  - `docs/README.md` modified by 1A.
  - `docs/REPOSITORY_AUDIT_GAP_COMPLETION_PLAN.md` untracked from 1A.
- FU1 intentionally did not fetch, merge, stage, commit, push, deploy, or
  disturb the 1A baseline.

## Canonical Documents Read

The 1A audit treated these as the current-state source set and checked them
against code where practical:

- `docs/README.md`
- `docs/PRODUCT_ARCHITECTURE_AND_ROADMAP.md`
- `docs/MODULE_BOUNDARIES.md`
- `docs/TODAY_AND_MY_SERVING_PRODUCT_BOUNDARIES.md`
- `docs/CHURCH_STRUCTURE_FOUNDATION_PLAN.md`
- `docs/TRIAL_SETUP_READINESS_RUNBOOK.md`
- `docs/COMMUNITY_ACTIVITIES_V1_PLAN.md`
- `docs/COMMUNITY_SIGNUP_CANCELLATION_POLICY_PLAN.md`
- `docs/ANNOUNCEMENTS_V1_PLAN.md`
- `docs/CHURCH_CALENDAR_V1_PLAN.md`
- `docs/NOTIFICATIONS_V0_PLAN.md`
- `docs/PORTAL_UX_AND_HELP_CENTER_PLAN.md`
- `docs/STAFF_SETUP_GUIDE.md`
- `docs/DEPLOYMENT_SECURITY.md`
- `docs/GODADDY_PRODUCTION_SECURITY_AUDIT.md`

FU1 did not reopen the full repository audit. It used targeted reads of the
membership model/selectors/write paths and canonical QA/status docs only where
needed to make this ledger precise.

## Runtime Areas Inspected

The audit inspected representative runtime, permission, visibility, form,
admin, and test files for these areas:

- Module registry and feature gates:
  `core/module_registry.py`, `core/today_providers.py`,
  `core/setup_readiness.py`, `config/urls.py`.
- Church Structure and belonging:
  `accounts/models.py`, `accounts/structure_selectors.py`,
  `accounts/views.py`, `accounts/tests.py`.
- Staff navigation, Help Center, and staff guide surfaces:
  `accounts/staff_navigation.py`, relevant `accounts/views.py` Help Center and
  staff routes, staff templates by inventory.
- Reading and reflections:
  `reading/views.py`, `comments` tests and visibility references by inventory.
- Prayer:
  `prayers` tests and current visibility references by inventory.
- Service Events:
  `events/models.py`, `events/views.py`, `events/visibility.py`,
  `events/admin.py`, `events/tests.py`,
  `events/test_serving_event_visibility.py`.
- Bible Study V2:
  `studies/models.py`, `studies/views.py`, `studies/visibility.py`,
  `studies/permissions.py`, `studies/admin.py`, `studies/tests.py`.
- Ministry serving:
  `ministry/permissions.py`, `ministry/views.py`, ministry tests by inventory.
- Community Activities:
  `community_events/models.py`, `community_events/views.py`,
  `community_events/visibility.py`, `community_events/admin.py`,
  `community_events/tests.py`.
- Announcements:
  `announcements/models.py`, `announcements/views.py`,
  `announcements/forms.py`, `announcements/visibility.py`,
  `announcements/admin.py`, `announcements/tests.py`.
- Church Calendar:
  `church_calendar/providers.py`, `church_calendar/registration.py`,
  calendar provider/UI/serving tests by inventory.
- Deployment and trial operations:
  deployment/security docs and the read-only trial readiness runbook.

## Module Inventory

| Key or area | Owner | Current status | Member nav | Today | Staff dropdown or overview | Setup readiness | Calendar |
|---|---|---|---|---|---|---|---|
| `accounts` / core | Core | Active core identity, structure, membership, staff shell, Help Center | Account/profile surfaces | Home and Today container | Staff Overview, User Admin, Membership Requests, Church Structure Setup & Review, Staff User Guide | Core readiness providers always run | None as source |
| `reading` | Reading app | Active | Grow / Reading | Reading provider | Reading Plan Admin | No module-specific provider observed | No source |
| `comments` | Support app under Reading | Active support surface, not independently module-gated | Reflection/comment support | Reflections attach to reading experience | Moderation Queue and Reflection Reports | No module-specific provider observed | No source |
| `prayers` | Prayers app | Active | Grow / Prayer | No registered Today provider | Prayer Reports and staff moderation/reporting | No module-specific provider observed | No source |
| `studies` | Bible Study V2 | Active V2 path | Grow / Bible Study | Bible Study provider | Bible Study Schedules, Weekly Bible Study Guides, Small Group Meetings | Module provider registered | `bible_study_meeting` plus personal `bible_study_serving` overlay |
| `events` | Service Events | Active church gatherings | Community / Church Gatherings | ServiceEvent provider | Manage Church Gatherings; Ministry Operations card uses event/serving data | Capability flag set; shared audience/core checks apply | `service_event` |
| `community_events` | Community Activities | Active V1 bounded activity path | Community / Activities | Low-noise activity reminders | Activity Review | No module-specific provider observed | `community_activity` |
| `announcements` | Official Announcements | Active V1 bounded communication path | Community / Announcements | One important announcement | Announcement Admin | No module-specific provider observed | `announcement` |
| `church_calendar` | Church Calendar | Active read-only aggregator | Community / Calendar | No Today provider | No staff management surface | No module-specific provider observed | Owns aggregation only |
| `ministry` | Ministry serving | Active serving assignment path, depends on `events` | My Serving | My Serving action/leader provider | Ministry Structure, Ministry Teams, Team Assignments, Ministry Operations card | Module provider registered | Personal `my_serving` overlay |
| Notifications | Future product area | Planning only | None | None | None | None | None |

Registry evidence: `core/module_registry.py` registers `reading`, `prayers`,
`studies`, `events`, `community_events`, `announcements`, `church_calendar`,
and `ministry`; unknown module keys and unmet dependencies raise
`ImproperlyConfigured`, and `ministry` depends on `events`.

## Module Lifecycle Completeness Matrix

Legend: every lifecycle cell uses one of `IMPLEMENTED`, `PARTIAL`,
`INTENTIONALLY NOT APPLICABLE`, `DEFERRED`, or `GAP`.

| MODULE | FOUNDATION | CREATE | EDIT | PUBLISH / ACTIVATE | VIEW | USER ACTION | CANCEL / ARCHIVE / END | STAFF REVIEW | TODAY | CALENDAR | MY SERVING | HELP / DOCS | QA | NOTES |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Reading | IMPLEMENTED | IMPLEMENTED | IMPLEMENTED | IMPLEMENTED | IMPLEMENTED | IMPLEMENTED | IMPLEMENTED | IMPLEMENTED | IMPLEMENTED | INTENTIONALLY NOT APPLICABLE | INTENTIONALLY NOT APPLICABLE | PARTIAL | PARTIAL | Reading is an active devotional surface; Calendar and My Serving are intentionally separate. |
| Prayer | IMPLEMENTED | IMPLEMENTED | IMPLEMENTED | IMPLEMENTED | IMPLEMENTED | IMPLEMENTED | IMPLEMENTED | IMPLEMENTED | INTENTIONALLY NOT APPLICABLE | INTENTIONALLY NOT APPLICABLE | INTENTIONALLY NOT APPLICABLE | PARTIAL | PARTIAL | Prayer is not an agenda, calendar, or serving module. |
| Bible Study | IMPLEMENTED | IMPLEMENTED | IMPLEMENTED | IMPLEMENTED | IMPLEMENTED | IMPLEMENTED | IMPLEMENTED | IMPLEMENTED | IMPLEMENTED | IMPLEMENTED | IMPLEMENTED | PARTIAL | IMPLEMENTED | V2 is active; V1 schema is retired. My Serving uses explicit linked-user meeting roles only. |
| Church Gatherings / ServiceEvent | IMPLEMENTED | IMPLEMENTED | IMPLEMENTED | IMPLEMENTED | IMPLEMENTED | PARTIAL | IMPLEMENTED | IMPLEMENTED | IMPLEMENTED | IMPLEMENTED | IMPLEMENTED | PARTIAL | IMPLEMENTED | Serving visibility is explicit assignment-based; ordinary visibility remains audience-based. |
| Ministry / My Serving | IMPLEMENTED | IMPLEMENTED | IMPLEMENTED | IMPLEMENTED | IMPLEMENTED | IMPLEMENTED | IMPLEMENTED | IMPLEMENTED | IMPLEMENTED | IMPLEMENTED | IMPLEMENTED | PARTIAL | IMPLEMENTED | Serving is explicit only through serving assignment rows or linked Bible Study roles. |
| Community Activities | IMPLEMENTED | IMPLEMENTED | IMPLEMENTED | IMPLEMENTED | IMPLEMENTED | IMPLEMENTED | IMPLEMENTED | IMPLEMENTED | IMPLEMENTED | IMPLEMENTED | INTENTIONALLY NOT APPLICABLE | IMPLEMENTED | IMPLEMENTED | V1 signup is attendance intent, not serving. Waitlists, check-in, payments, and My Serving integration are deferred product scope. |
| Announcements | IMPLEMENTED | IMPLEMENTED | IMPLEMENTED | IMPLEMENTED | IMPLEMENTED | INTENTIONALLY NOT APPLICABLE | IMPLEMENTED | INTENTIONALLY NOT APPLICABLE | IMPLEMENTED | IMPLEMENTED | INTENTIONALLY NOT APPLICABLE | IMPLEMENTED | IMPLEMENTED | Official communication only; no serving, signup, or review workflow. |
| Church Calendar | IMPLEMENTED | INTENTIONALLY NOT APPLICABLE | INTENTIONALLY NOT APPLICABLE | INTENTIONALLY NOT APPLICABLE | IMPLEMENTED | IMPLEMENTED | INTENTIONALLY NOT APPLICABLE | INTENTIONALLY NOT APPLICABLE | INTENTIONALLY NOT APPLICABLE | IMPLEMENTED | IMPLEMENTED | IMPLEMENTED | IMPLEMENTED | Calendar is intentionally read-only and aggregates source-owned items. Writable/external calendar sync is deferred product scope. |
| Church Structure | IMPLEMENTED | IMPLEMENTED | PARTIAL | IMPLEMENTED | IMPLEMENTED | IMPLEMENTED | IMPLEMENTED | IMPLEMENTED | INTENTIONALLY NOT APPLICABLE | INTENTIONALLY NOT APPLICABLE | INTENTIONALLY NOT APPLICABLE | IMPLEMENTED | IMPLEMENTED | Core belonging and delegated My Units are active. Broad create/move/deactivate UI remains deferred to avoid unsafe structure mutations. |

## Healthy Areas

### Belonging And Visibility

- Approved migrated visibility paths use `ChurchStructureMembership` plus
  audience rows, not legacy `Profile.small_group`, `SmallGroup`, `District`, or
  `MinistryContext`.
- `accounts/structure_selectors.py` fails closed when an authenticated user has
  zero or multiple current active primary memberships.
- ServiceEvent, Bible Study V2, Prayer, Reflection, Community Activity,
  Announcement, and Church Calendar member-safe paths do not reintroduce legacy
  belonging authority.
- Zero-audience member visibility generally fails closed for ordinary users.
  Management surfaces keep their separate staff or manager gates.

### Serving Boundaries

- Membership does not imply serving.
- Audience visibility does not imply serving.
- `ministry/permissions.py` uses explicit `TeamAssignmentMember`,
  `TeamMembership`, and role-assignment relationships for serving and ministry
  management.
- `events/test_serving_event_visibility.py` and `studies/permissions.py`
  preserve the narrow rule that explicit serving grants read-only detail access
  to exactly the served event or Bible Study meeting, not list/calendar/audience
  membership.
- Calendar serving overlays are personal, read-only, and source-owned:
  `ministry` emits `my_serving`; `studies` emits `bible_study_serving`.
- Community signup is attendance intent, never serving.

### Calendar

- `church_calendar/providers.py` is model-free and read-only.
- Providers are source-module owned, validate item type ownership, skip disabled
  modules, and fail closed for anonymous users.
- The registered source modules are deterministic through
  `church_calendar/registration.py`.
- Calendar does not create writable calendar events, mutate source modules,
  send notifications, or infer serving from belonging.

### Staff, Navigation, And Mutation Boundaries

- Representative mutation routes are guarded by `@login_required`,
  `@staff_member_required`, `@user_passes_test`, `@require_POST`, or explicit
  non-POST redirects before mutation.
- ServiceEvent, Bible Study meeting, Community Activity create/edit, Community
  signup/cancel, and Announcement create/edit/publish/archive paths use
  transactions for multi-row or lifecycle-sensitive writes.
- Community signup/cancel locks `CommunityActivity` first and then the signup
  row, preserving the documented lock order.
- No `csrf_exempt` usage was found in the inspected application code.
- Navigation visibility is not route permission.
- Help Center recommendation is not permission.

### Tests

- The repository has substantial focused coverage for structure visibility,
  audience rows, module gates, Today providers, setup readiness providers,
  ServiceEvent/Bible Study admin audience inlines, Community Activity lifecycle,
  signup/cancel, co-organizers, Announcements, Calendar provider/UI behavior,
  explicit serving visibility, My Serving, Staff Overview, Help Center, and
  delegated structure management.
- This audit did not run the full suite because the task explicitly preferred
  targeted static/regression checks and the full suite is outside the standing
  workflow unless approved.

## Manual QA Coverage Matrix

| AREA | AUTOMATED COVERAGE | RECORDED MANUAL QA | CURRENT STATUS | EVIDENCE | RECOMMENDED ACTION |
|---|---|---|---|---|---|
| Today | Focused Today/provider tests exist across reading, events, studies, Community Activities, Announcements, ministry, and registry behavior. | `DOCS-QA-CHECKPOINT.1A` prepared a checklist but says that round was not already run; Announcements Today manual QA passed. | Automated coverage plus partial historical manual QA. | `docs/TODAY_AND_MY_SERVING_PRODUCT_BOUNDARIES.md`; `docs/ANNOUNCEMENTS_V1_PLAN.md`. | Do not reopen Today for this slice. Run the existing Today/My Serving checklist when a future UI or demo-data milestone needs it. |
| My Serving | Focused ministry and Bible Study serving tests cover explicit assignment/role behavior. | My Units/belonging QA passed separately; ministry scheduling and My Serving flows have historical manual QA in serving docs; Calendar 2B QA confirmed My Serving unchanged. | Adequate for current slice; not reopened by FU1. | `docs/TRIAL_SETUP_READINESS_RUNBOOK.md`; `docs/CHURCH_CALENDAR_V1_PLAN.md`; serving docs referenced by roadmap. | No additional manual QA required for this docs-only FU1. Re-run if My Serving UI changes. |
| Church Calendar | Provider, UI, route, enablement, date, and serving overlay tests exist. | Product-owner manual QA passed for baseline Calendar V1 and again for Bible Study serving overlay. | Passed and recorded for current limited-trial Calendar scope. | `docs/CHURCH_CALENDAR_V1_PLAN.md`; `docs/CHURCH_CALENDAR_V1_QA_CHECKLIST.md`. | Do not reopen Calendar QA solely because reusable future-regression boxes exist. |
| Community Activities | Focused tests cover lifecycle, visibility, signup/cancel/capacity, co-organizers, Today, Calendar separation, and non-serving boundaries. | Manual QA passed by user confirmation under `COMMUNITY-EVENTS-STABILIZATION.1B`. | Passed and recorded for bounded V1; concurrency proof remains a separate low hardening item. | `docs/COMMUNITY_ACTIVITIES_V1_PLAN.md`; `docs/TRIAL_SETUP_READINESS_RUNBOOK.md`. | Keep V1 pass as historical evidence; run backend-specific concurrency proof separately if required. |
| Announcements | Focused tests cover staff lifecycle, member visibility, Today, module gates, and no cross-module mutation. | Product-owner manual QA passed under `ANNOUNCEMENTS-QA-PASS.1A`. | Passed and recorded for bounded V1. | `docs/ANNOUNCEMENTS_V1_PLAN.md`. | No additional manual QA required for this docs-only FU1. |
| Church Structure / My Units | Focused tests cover membership requests, delegated My Units, visibility selectors, and readiness checks. | `GROUP-MEMBERSHIP-MANAGE.1A` and `GROUP-MEMBERSHIP-REQUEST.1B` are recorded as QA-passed. | Passed for delegated belonging workflows; active/current primary integrity hardening remains open. | `docs/TRIAL_SETUP_READINESS_RUNBOOK.md`; `docs/CHURCH_STRUCTURE_MAPPING_AND_MEMBERSHIP_STRATEGY.md`; `docs/CHURCH_STRUCTURE_MEMBERSHIP_APPROVAL_IMPLEMENTATION_PLAN.md`. | Do not expand My Units. Address `AUDIT-DATA-001` through design-first integrity hardening. |
| Staff navigation | Focused Staff navigation grouping and Help Center access/recommendation tests exist. | Product-owner deployed manual QA passed after the mobile accordion follow-up, including Staff desktop grouped navigation, Staff mobile navigation, and final one-open-at-a-time mobile dropdown behavior. | Manual QA closed for the bounded Portal / Help Center slice. | `docs/PORTAL_UX_AND_HELP_CENTER_PLAN.md`. | No additional action for `AUDIT-QA-001`; re-run manual QA only for future Portal/Staff navigation changes. |
| Help Center | Focused authenticated access, guide detail, recommendation, and permission-boundary tests exist. | Product-owner deployed manual QA passed for Help Center, ordinary member desktop/mobile, explicit-serving recommendations, delegated My Units leader recommendations, and Staff Help Center access. | Manual QA closed for the bounded Portal / Help Center slice. | `docs/PORTAL_UX_AND_HELP_CENTER_PLAN.md`. | No additional action for `AUDIT-QA-001`; re-run manual QA only for future Help Center changes. |

## Findings Summary

Finding counts classify rows by finding type/severity, including closed rows.
Status changes from completed follow-ups are reflected in the findings table.

| Classification | Count |
|---|---:|
| `BLOCKER` | 0 |
| `HIGH` | 0 |
| `MEDIUM` | 1 |
| `LOW` | 4 |
| `NICE-TO-HAVE` | 0 |
| `DEFERRED-BY-DESIGN` | 2 |
| `MANUAL-QA` | 1 |
| `DOCS-DRIFT` | 2 |
| `NO-ISSUE` | 3 |

## Findings

| ID | AREA | SEVERITY | STATUS | EVIDENCE | USER / PRODUCT IMPACT | RECOMMENDED ACTION | PROPOSED SLICE |
|---|---|---|---|---|---|---|---|
| `AUDIT-DATA-001` | Active/current primary membership integrity and concurrency hardening | `MEDIUM` | Partially hardened / residual defense-in-depth gap | `STRUCTURE-MEMBERSHIP-PRIMARY-INTEGRITY-HARDENING.1A` established the canonical invariant in `docs/STRUCTURE_MEMBERSHIP_PRIMARY_INTEGRITY_PLAN.md`: read-time current primary is date-window aware, while today's normal write policy permits at most one `status=active, is_primary=True` row per user regardless of date window. 1A added shared active-primary conflict helpers, per-user membership mutation-scope locking for normal product writes, in-transaction rechecks, and focused tests for future-active-primary conflicts. `STRUCTURE-MEMBERSHIP-PRIMARY-INTEGRITY-HARDENING.1A-FU1` kept visibility/no-current readiness date-window-aware while adding broader active-primary write-invariant blocker detection for current+future and future+future drift; it also finished the post-lock target refetch/recheck pattern for rejection and end paths so stale reject objects cannot overwrite approved requests. `accounts/structure_selectors.get_user_primary_membership_unit()` still fails closed when multiple current active primary rows exist. `audit_trial_setup_readiness` remains the read-only drift detector and now covers both current-primary ambiguity and stricter active-primary write-policy drift. | Normal staff/delegated membership add, approve, reject, end, and set-primary paths are more consistent and fail closed cleanly, including future-dated active-primary conflicts and serialized stale approve/reject sequencing. Bulk operations, manual SQL, direct shell/import drift, and the absence of a database constraint can still create ambiguous current-primary belonging; affected users may lose scoped content until repaired because selectors intentionally fail closed. SQLite does not prove PostgreSQL-style row-lock concurrency behavior. | Keep 1A/FU1 as application/readiness hardening, but do not claim complete closure. Evaluate a separately approved `STRUCTURE-MEMBERSHIP-PRIMARY-DB-CONSTRAINT.1B` before adding schema enforcement. A simple partial unique constraint on active primary rows may match today's write policy, but it must be explicitly approved because it encodes the no current+future active-primary coexistence rule and requires a migration. | `STRUCTURE-MEMBERSHIP-PRIMARY-INTEGRITY-HARDENING.1A`; `STRUCTURE-MEMBERSHIP-PRIMARY-INTEGRITY-HARDENING.1A-FU1`; possible future `STRUCTURE-MEMBERSHIP-PRIMARY-DB-CONSTRAINT.1B` |
| `AUDIT-ADMIN-001` | Django Admin audience repair UX | `LOW` | Closed | `ADMIN-INACTIVE-AUDIENCE-REPAIR-UX.1A` keeps existing audience unit fields disabled/immutable while allowing the current inactive unit to render in the existing inline row. The inline now shows a concise inactive-unit repair warning; inactive units remain unavailable for new audience rows, and delete-and-replace remains the repair path. Focused Admin GET/POST tests cover ServiceEvent, BibleStudySeries, and BibleStudyMeeting inactive-existing display, immutable existing units, inactive-new rejection, delete-only rejection, and delete-plus-active-replacement success. | Staff/admin users can now see which inactive unit an existing audience row points to and repair it by deleting the obsolete row and adding an active replacement, without broadening audience semantics. | Closed; preserve the current audience visibility-only contract and do not treat audience as serving, belonging, leadership, or staff authority. | `ADMIN-INACTIVE-AUDIENCE-REPAIR-UX.1A` |
| `AUDIT-DOC-001` | Today/My Serving documentation | `DOCS-DRIFT` | Closed | `DOCS-CALENDAR-BOUNDARY-DRIFT.1A` updates `docs/TODAY_AND_MY_SERVING_PRODUCT_BOUNDARIES.md` so current-state wording describes Church Calendar V1 as an implemented read-only aggregation surface that remains separate from Today and My Serving. | Readers no longer need to reconcile stale `CHURCH-CALENDAR.0A` planned/no-runtime wording with the implemented Calendar V1 docs. | Closed; preserve the serving-vs-belonging boundary and do not expand Today, My Serving, or Calendar behavior without a separate approved slice. | `DOCS-CALENDAR-BOUNDARY-DRIFT.1A` |
| `AUDIT-DOC-002` | Module boundary wording | `DOCS-DRIFT` | Closed | `DOCS-CALENDAR-BOUNDARY-DRIFT.1A` updates `docs/MODULE_BOUNDARIES.md` to distinguish the implemented read-only Church Calendar adapter for Community Activities from still-deferred Community Activity-owned writable calendar workflow, external / Google Calendar sync, Calendar-driven signup/cancellation, `ServiceEvent` linkage, and My Serving integration. | Readers no longer need to infer whether "calendar integration" means the implemented read-only adapter or deferred writable/external calendar scope. | Closed; keep Community Activities independent from Calendar ownership, `ServiceEvent`, serving, and My Serving. | `DOCS-CALENDAR-BOUNDARY-DRIFT.1A` |
| `AUDIT-QA-001` | Portal UX and Help Center | `MANUAL-QA` | Closed | `docs/PORTAL_UX_AND_HELP_CENTER_PLAN.md` records that product-owner deployed manual QA passed after the mobile accordion follow-up. Coverage included ordinary member desktop, explicit-serving user recommendations, delegated My Units leader recommendations, Staff desktop grouped navigation, Help Center, ordinary member mobile, Staff mobile, and final one-open-at-a-time mobile top-level dropdown behavior. | The bounded Portal / Help Center manual-QA gap is closed without making a broad production-readiness claim. | Closed; re-run manual QA only for future Portal, Staff navigation, Help Center, or mobile navigation changes. | `PORTAL-HELP-MANUAL-QA.1A`; `PORTAL-HELP-MANUAL-QA.1A-FU1` |
| `AUDIT-TEST-001` | Community signup/cancel concurrency proof | `LOW` | Open | `community_events/views.py` locks the activity first and then the signup row inside `transaction.atomic()` for signup/cancel; `docs/COMMUNITY_SIGNUP_CANCELLATION_POLICY_PLAN.md` records the SQLite caveat. | SQLite-backed tests cannot prove production row-lock behavior for final-slot races on a database with real row-level locks. Code order is correct, so this is proof coverage rather than a current bug. | Run a backend-appropriate concurrency harness or add targeted tests when a production-like DB is available. | `COMMUNITY-SIGNUP-CONCURRENCY-PROOF.1A` |
| `AUDIT-DATA-002` | Community staff review and collaborator edit lifecycle transitions | `LOW` | Closed | `COMMUNITY-REVIEW-TRANSITION-LOCK.1A` routes staff review publish/request-changes/cancel through a shared transition helper that re-reads the `CommunityActivity` inside `transaction.atomic()` using `select_for_update()`, then rechecks the current mutable status before writing the status, reviewer, timestamp, and any accepted review note. `COMMUNITY-REVIEW-TRANSITION-LOCK.1A-FU1` makes normal creator/co-organizer POST edits use the same `CommunityActivity` row serialization point: the edit path locks and rechecks the current row before binding the form, derives draft/edit state from that locked row, and saves the activity plus audience/co-organizer replacements in the same transaction. `COMMUNITY-REVIEW-TRANSITION-LOCK.1A-FU2` adds a browser stale-state guard: existing activity edit forms submit a non-model expected lifecycle status, and POST rejects the form after locking if that status no longer matches the current row. Focused serialized stale-state tests cover staff publish/request-changes/cancel behavior, collaborator edit attempts after staff publish/cancel/request-changes, and old pending-review browser forms after staff request-changes. SQLite does not prove PostgreSQL-style row-lock concurrency behavior. | Stale losing staff actions no longer silently overwrite an already completed transition, stale collaborator edits no longer restore editable lifecycle state over published/cancelled staff decisions or clobber winning review metadata, and old browser forms cannot be silently reinterpreted as a different lifecycle action after staff changes the status. Request-changes notes are not saved unless the current locked row still accepts that staff transition, and fresh edit-side resubmission preserves existing review metadata under the accepted current lifecycle. | Closed for the normal product transition gap. Preserve the existing V1 lifecycle and keep backend-specific row-lock proof caveats separate from this runtime defect closure; this is not generic optimistic concurrency. | `COMMUNITY-REVIEW-TRANSITION-LOCK.1A`; `COMMUNITY-REVIEW-TRANSITION-LOCK.1A-FU1`; `COMMUNITY-REVIEW-TRANSITION-LOCK.1A-FU2` |
| `AUDIT-MAINT-001` | Accounts app size | `LOW` | Open | `accounts/views.py` is 3,448 lines and `accounts/tests.py` is 14,169 lines, covering staff shell, Help Center, structure, membership, My Units, user admin, readiness, and profile flows. | Large files increase review cost and make unrelated future changes easier to tangle. File size alone is not a runtime defect. | Opportunistically extract helpers/tests by surface only when related work is already being touched. Do not perform a broad refactor solely because files are large. | `ACCOUNTS-SURFACE-HELPER-EXTRACTION.1A` |
| `AUDIT-DEFER-001` | Notifications | `DEFERRED-BY-DESIGN` | Open by design | `docs/NOTIFICATIONS_V0_PLAN.md` is planning-only; no runtime notification app or delivery path is present. | Users will not receive in-app or external notifications until separately approved and implemented. | Future `NOTIFICATIONS` slices only after explicit approval. Do not backfill notifications into Calendar, Today, Announcements, or Community Activities ad hoc. | Future approved notifications slice |
| `AUDIT-DEFER-002` | Community expansion | `DEFERRED-BY-DESIGN` | Open by design | Community Activities V1 docs intentionally defer waitlists, attendee management/check-in, payments, recurring activities, external calendar sync, notification delivery, and serving integration. | Product expectations can exceed the intentionally bounded V1 implementation if not communicated. | Future separately approved Community V2 slices. Preserve Community Activities as separate from serving and official events. | Future approved Community V2 slice |
| `AUDIT-NOISSUE-001` | Serving inference | `NO-ISSUE` | Closed | `ministry/permissions.py`, `studies/permissions.py`, Calendar serving providers, and serving visibility tests keep serving explicit and separate from membership. | No repository issue found. | Keep this as a regression boundary for future changes. | None |
| `AUDIT-NOISSUE-002` | Church Calendar mutability | `NO-ISSUE` | Closed | `church_calendar/providers.py` validates provider ownership, skips disabled source modules, and only aggregates source items. | No repository issue found. | Keep Calendar read-only unless a separate writable-calendar slice is approved. | None |
| `AUDIT-NOISSUE-003` | GoDaddy static security audit status | `NO-ISSUE` | Closed | `docs/GODADDY_PRODUCTION_SECURITY_AUDIT.md` remains repository-only and does not claim live cPanel/proxy/environment facts. Prior static audit found no repository-proven `BLOCKER` or `HIGH`; live unknowns remain manual verification. | No new repository-proven GoDaddy issue was found in this audit. | Manual live verification remains outside repository-only work and requires explicit authorization. | None |

## Top Open Risks And Watch Items

1. Active/current primary membership integrity remains the only `MEDIUM`
   hardening item because it is central to scoped visibility and must preserve
   date-window semantics.
2. Community signup/cancel logic is coded with a safe lock order, but true
   row-lock proof needs a production-like database.
3. Accounts app maintainability debt remains opportunistic cleanup only; do
   not turn it into a broad standalone refactor.

## Remediation Roadmap

| SLICE | GOAL | LIKELY FILES / AREAS | MODEL / MIGRATION EXPECTED? | RISK | DEPENDENCIES | VERIFICATION | SOURCE FINDING IDS |
|---|---|---|---|---|---|---|---|
| `STRUCTURE-MEMBERSHIP-PRIMARY-INTEGRITY-HARDENING.1A` | Completed application/readiness hardening for the active/current primary belonging invariant through 1A/FU1/FU2 while preserving date-window-aware reads. | `accounts/models.py`, `accounts/structure_selectors.py`, `accounts/views.py`, `accounts/forms.py`, `accounts/tests.py`, trial readiness/audit command areas. | No additional model/migration is authorized by 1A/FU1/FU2. A possible `STRUCTURE-MEMBERSHIP-PRIMARY-DB-CONSTRAINT.1B` remains optional, unapproved, and separate because it would encode write-policy enforcement in schema. | Medium: belonging integrity affects scoped visibility; residual risk is direct/bulk/manual drift without a database constraint. | Completed application/readiness slices; any DB constraint slice requires separate approval and migration design. | Existing focused application/readiness tests and drift checks cover the completed hardening. A future 1B would need its own migration and backend-specific verification. | `AUDIT-DATA-001` |
| `PORTAL-HELP-MANUAL-QA.1A` | Completed product-owner visual/manual QA for Portal UX, grouped Staff dropdown, and Help Center after the mobile accordion follow-up. | `docs/PORTAL_UX_AND_HELP_CENTER_PLAN.md`, intended deployed/test environment, navigation and Help Center routes. | No. | Closed: visual/manual QA evidence recorded for the bounded Portal / Help Center slice. | Completed product-owner deployed manual QA. | Recorded pass for ordinary member desktop/mobile, explicit serving user recommendations, My Units leader recommendations, Staff desktop/mobile navigation, Help Center, and final one-open-at-a-time mobile dropdown behavior. | `AUDIT-QA-001` |
| `ADMIN-INACTIVE-AUDIENCE-REPAIR-UX.1A` | Completed Django Admin inactive-existing audience repair UX while preserving existing validation. | `events/admin.py`, `studies/admin.py`, focused admin tests in `events/tests.py` and `studies/tests.py`. | No model/migration expected. | Closed: staff/admin UX hardening only. | Current admin inline validation contract. | Actual Django Admin GET/POST tests cover inactive existing row display, delete-only rejection, delete-plus-active-replacement success, inactive-new rejection, and immutable existing rows. | `AUDIT-ADMIN-001` |
| `COMMUNITY-SIGNUP-CONCURRENCY-PROOF.1A` | Prove final-slot signup/cancel behavior on a backend with real row-level locks. | `community_events/views.py`, `community_events/tests.py`, backend-specific test harness or manual verification notes. | No model/migration expected. | Low: proof gap, code lock order already matches policy. | Production-like database or explicit backend test strategy. | Concurrency harness or documented DB-specific verification for simultaneous signup/reactivation/cancel cases. | `AUDIT-TEST-001` |
| `COMMUNITY-REVIEW-TRANSITION-LOCK.1A` | Completed staff review and collaborator edit lifecycle transition hardening against stale writers and stale browser forms. | `community_events/views.py`, `templates/community_events/community_activity_form.html`, `community_events/tests.py`, `docs/COMMUNITY_ACTIVITIES_V1_PLAN.md`. | No model/migration. | Closed: staff/collaborator last-write-wins and stale-form hardening. | Existing Community Activities V1 lifecycle. | Focused tests for staff publish/request-changes/cancel stale-state behavior, creator/co-organizer stale edit behavior, and stale expected-status browser forms; `manage.py check`; migration dry-run; `git diff --check`. SQLite remains a backend caveat, not database-level concurrency proof. | `AUDIT-DATA-002` |
| `DOCS-CALENDAR-BOUNDARY-DRIFT.1A` | Completed current-state Calendar wording correction in Today/My Serving and Module Boundaries docs. | `docs/TODAY_AND_MY_SERVING_PRODUCT_BOUNDARIES.md`, `docs/MODULE_BOUNDARIES.md`, `docs/REPOSITORY_AUDIT_GAP_COMPLETION_PLAN.md`. | No. | Closed: docs-only clarity. | Current Calendar V1 docs and implemented read-only provider behavior. | `git diff --check`; targeted doc search verified no stale current-state "no calendar runtime" wording remains in the canonical docs touched by this slice. | `AUDIT-DOC-001`, `AUDIT-DOC-002` |
| `ACCOUNTS-SURFACE-HELPER-EXTRACTION.1A` | Reduce future review cost by extracting helpers/tests only when related work is already being touched. | Candidate accounts views/tests by surface: Help Center, Staff shell, membership requests, My Units, readiness, profile. | No model/migration expected unless a future functional slice separately requires one. | Low if opportunistic; higher if attempted as broad refactor. | A related feature/fix that already touches the area. | Existing focused tests for the touched surface; no broad refactor solely because files are large. | `AUDIT-MAINT-001` |

## Manual QA Gaps

- Portal UX and Help Center post-deployment product-owner checklist is closed
  by product-owner deployed manual QA after the mobile accordion follow-up; it
  is not a current limited-trial manual-QA requirement.
- Existing Calendar V1 and Bible Study serving Calendar QA are recorded in the
  Calendar docs as passed and were not reopened by this repository audit.
- Existing Community Activities and Announcements manual QA passes are recorded
  in their canonical docs and were not reopened by this repository audit.
- GoDaddy/live hosting facts remain `MANUAL VERIFICATION REQUIRED`; no live
  cPanel, proxy, database, or production environment access was used.

## Deferred Product Boundaries

Do not treat these as required for the current limited-trial path:

- notifications runtime;
- Community waitlist;
- attendee management;
- Community check-in;
- payments;
- writable Calendar;
- Google or external calendar sync;
- Community Activities in My Serving;
- generalized RBAC rewrite;
- hard-off module routes;
- sidebar desktop navigation;
- PostgreSQL migration;
- microservices.

## Limited-Trial Assessment

A. No repository-proven `BLOCKER` or `HIGH` issue; suitable to continue the
current limited trial under the documented product and operational boundaries.

This assessment is based on the absence of `BLOCKER` and `HIGH` findings in the
repository-only audit, the preserved healthy boundaries above, and the current
manual-QA evidence recorded in canonical docs. It is not a production,
enterprise, security, hosting, or GoDaddy live-environment certification.
Deferred-by-design work is not required for the existing limited-trial scope
unless a future approved slice explicitly changes the scope.

## Verification Plan For This Docs-Only FU1

Run the following non-mutating checks after updating this document:

- `git diff --check`
- `git diff --stat`
- `git status --short`

No data-changing command, Django test suite, migration command, migration
generation, stage, commit, push, deploy, or production access belongs to FU1.
