# Notification V0 Plan

Status: current through `NOTIFY.1D`. The app/model/admin/Core delivery-port
foundation, recipient-scoped Notification Center/bell UI, the ministry-owned
explicit ServiceEvent serving-assignment producer, and the studies-owned
explicit Bible Study meeting-role producer are implemented.

This document is the implementation boundary for Notification V0. The completed
`NOTIFY.1A` through `NOTIFY.1D` scopes are recorded below; later producers,
background jobs, external delivery, and permission changes still require
separate approval.

## 1. Status

`NOTIFY.0A` created the docs-only plan. `NOTIFY.0B` resolved the cross-module
delivery dependency direction. `NOTIFY.1A` implements the authorized
foundation only:

- a registered, default-enabled `notifications` app/module with no source-module
  dependencies or shared-surface capabilities;
- the `Notification` model, initial migration, and operational Django admin;
- a Core-owned immutable directed payload, one-sink registration contract,
  notifications-module gate, and `transaction.on_commit()` dispatch;
- a notifications-owned persistence sink with database-backed uniqueness for
  recipient plus producer-owned `dedupe_key`, preserving the first stored
  snapshot on duplicate delivery;
- normal post-commit failure logging/containment and an explicit strict
  development/test delivery seam.

`NOTIFY.1B` adds an authenticated recipient-scoped center at `/notifications/`,
newest-first bounded snapshot rendering, visible read/unread state, explicit
POST-only mark-one and mark-all read actions, and a bilingual shared-shell
notification utility bell/link with a recipient-scoped unread count. The bell is
not a `PrimaryNavEntry`; when Notifications is disabled, it is absent and its
notifications-owned context data does not query Notification rows. Direct URLs
retain the existing module surface-gate semantics and their own authentication
and recipient checks.

`NOTIFY.1C` adds the first source producer, owned by `ministry`, for current
explicit linked-user `TeamAssignmentMember` serving. It emits only through the
Core port. A newly added eligible member receives one assigned snapshot; a
retained eligible member receives at most one updated snapshot when the
assignment moves to a different ServiceEvent and/or transitions from cancelled
to active. Display-name-only members, audience members, belonging rows,
managers, and staff are never inferred as recipients. Ordinary notes/same-event
non-cancelled status edits, confirmation, removal, cancellation, ServiceEvent
cancellation, previews, admin/import/direct ORM writes, and failed forms emit
nothing. The target is the existing exact My Serving member-row anchor.

`NOTIFY.1D` adds the second source producer, owned by `studies`, and calls it
only after successful interactive `BibleStudyMeetingRole` create/edit saves.
The only recipient is the role's active linked `user`; display-name-only roles
and audience, belonging, coworker-role, manager, or staff users are never
inferred. A new linked role, newly linked user, or reassigned user receives
`bible_study_role.assigned`; the same linked user receives
`bible_study_role.updated` only when the role type changes. Notes, display-name,
confirmation, deletion/removal, lifecycle, admin, direct ORM, generation, and
failed writes remain non-notifying. The target is the existing member-facing
Bible Study meeting detail.

`NOTIFY.1B` adds no Today/Calendar/My Serving/Staff
Overview integration, announcement fanout, external channel, scheduler,
background job, queue, retry framework, outbox, preference, deletion, archive,
or search behavior, and `NOTIFY.1C`/`NOTIFY.1D` change none of those surfaces. A
notification target remains permission-neutral: the
stored internal target path is rendered without source-model lookup, and that
owning target still enforces its own access rules.

### NOTIFY.1B Manual QA Closure

Product-owner manual rendered QA passed for the deployed `NOTIFY.1B` UI. The
confirmed scope covers desktop ordinary authenticated and staff users, mobile
navigation/drawer, English and Chinese UI, zero and multiple unread states, the
bell and unread count, Notification Center, mark-one and mark-all read actions,
target links, and Staff, Account, Grow, and Community navigation.

The current recipient UI is acceptable for the present limited-trial/product
stage. This manual QA result is not a broad production-readiness,
accessibility-certification, security-certification, or hosting-certification
claim, and it does not represent browser automation.

### NOTIFY.1C Deployed Smoke QA

The product owner completed the previously defined deployed producer smoke QA
and confirmed that the implemented explicit ServiceEvent serving-assignment
notification workflow worked as expected. This is a narrow workflow result,
not browser automation or a production, security, accessibility, or hosting
certification.

## 2. Purpose

Notifications are per-user directed records for important changes or actions
that source modules explicitly emit.

Notifications are not a replacement for Calendar, Today, My Serving, Official
Announcements, Community Activities, staff dashboards, or source-module detail
pages. They should point a user toward a relevant owning surface while preserving
that surface's existing permission checks and product role.

## 3. Non-goals

V0 explicitly excludes:

- email;
- SMS;
- WeChat;
- push notifications;
- external delivery;
- digest emails;
- an automatic reminder engine;
- a recurring or background reminder scheduler;
- notification preferences UI;
- a global broadcast feed;
- an announcement feed replacement;
- a Calendar replacement;
- a Today replacement;
- a My Serving replacement;
- permission granting;
- serving inference;
- attendance or check-in;
- external calendar sync.

## 4. Core Boundary Rules

- Notifications never grant permission.
- Notification existence must not leak private object information.
- Source modules choose recipients; the notifications app must not independently
  infer audience, serving, staff authority, or manager authority.
- Audience visibility does not imply serving.
- Serving assignment does not imply audience membership.
- Staff or manager permission is not implied by a notification.
- Notification target URLs must still enforce their own permissions.
- Producers must use the same visibility and permission rules that the source
  module already owns.
- A notification may help a user find an allowed action or detail page, but it
  must not become the authorization layer for that action or page.

### Architecture Decision (`NOTIFY.0B`)

Notifications is a registered, gateable CMS module, not an always-on Core
product. The `notifications` app owns Notification persistence, its model and
admin, and idempotent storage; it will own future read/unread state, retention
decisions, notification-specific rendering, the notification center, and the
bell/unread count.

Core owns only a deliberately small directed-notification delivery port and
sink-registration contract. A future source module may import that Core port
(implemented as `core.notification_delivery.emit_notification`) and pass an
already-resolved recipient plus notification payload. The `notifications` app
imports the Core registration contract and registers its persistence sink. The
dependency direction is fixed:

```text
source module -> Core notification port
notifications module -> Core sink-registration contract
```

The following directions are forbidden:

```text
source module -> notifications module
Core -> source module
notifications module -> source module
```

Core does not own Notification records or notification UX. It transports one
directed request to the registered sink and applies enablement/failure policy;
it is not a generic event bus, producer registry, recipient resolver, or
broadcast system.

### Recipient And Authority Ownership

The source module selects the recipient before calling Core. For the current
candidate producers, that means `ministry` resolves the linked serving user,
`studies` resolves `BibleStudyMeetingRole.user`, and `community_events`
resolves the primary activity creator. Neither Core nor the notifications app
may inspect a source object, Church Structure membership, audience rows,
serving rows, target URLs, staff roles, or manager capabilities to discover or
expand recipients.

The notifications module may depend on Core. Source modules may import only the
small Core delivery port for this integration; they must not import
`notifications`. The notifications app must not import source modules.

### Registry And Disablement

The registry key is `notifications`. It declares no dependency on
`events`, `studies`, `ministry`, `community_events`, or another source module.
Source modules must not declare `depends_on=("notifications",)` merely to emit
an optional notification.

Existing `CMS_ENABLED_MODULES` semantics remain the only feature gate:

- absent/`None` means every registered module, including `notifications`, is
  enabled;
- an explicit list enables `notifications` only when it contains the
  `notifications` key;
- no second notification feature-flag system exists.

In the foundation slice, `notifications` contributes no ordinary primary-nav
entry, Today provider, setup/readiness provider, or Staff Overview content.
The later bell/center is notification-owned UI, not a Today, Calendar, My
Serving, or ordinary primary-nav contribution.

When `notifications` is disabled, the Core emit call is a safe no-op: it writes
no Notification row, does not call the persistence sink, and lets the source
transaction continue normally. Disablement is optional-product behavior only;
it never grants or revokes source permissions, changes source lifecycle rules,
or becomes an authorization check.

### Commit And Failure Policy

The V0 foundation registers delivery with `transaction.on_commit()` so
a source rollback creates no notification and persistence runs only after the
source-domain transaction succeeds. The source module must resolve the
recipient and build the bounded payload before scheduling the callback; the
callback must not reopen the source object to discover recipients or authority.

An ordinary notification persistence failure after commit must be logged with
enough context to diagnose the source module/type and dedupe key, but must not
normally turn a successfully committed source-domain save into a source-domain
failure. Development and tests must have a deterministic strict execution seam
that surfaces sink/registration/persistence failures rather than silently
hiding them. `NOTIFY.1A` tests both the production containment policy and the
strict failure path. This does not add a queue, retry worker, scheduler,
outbox, or background job.

If the module is enabled but no sink is registered, that is a configuration or
programming failure, not disabled-module behavior. It follows the same
visible/logged failure policy and must fail loudly in foundation tests and
development.

### Idempotency Ownership

The source module owns the stable logical `dedupe_key` for the event it emits.
Core transports that key unchanged and performs no dedupe. The notifications
module owns idempotent persistence, backed by a database-level uniqueness rule
per recipient plus dedupe key and a sink/service that safely returns the
existing row for repeated delivery.

### Alternatives Considered

| Architecture | Dependency and disablement | Authority, testability, coupling, and fit |
|---|---|---|
| Source modules directly import `notifications.services` | Creates new source-to-notifications dependencies; every producer must understand module disablement. | Easy initially, but couples producers to persistence details, spreads gate/failure behavior, and weakens isolated source-module tests. Rejected. |
| Make notifications Core / always on | Avoids a cross-module import only by moving persistence and UX into always-on Core; cannot express optional module disablement cleanly. | Central and testable, but gives Core product/data ownership it does not need and conflicts with modular adoption. Rejected. |
| Registered notifications module plus Core delivery port and registered sink | Source modules depend only on Core; the notifications module registers a sink and Core applies one enablement/failure policy. | Keeps recipient authority in each source, persistence in notifications, and provides a narrow injectable seam for focused tests. Lowest coupling consistent with the registry. Chosen. |
| Notifications imports source modules and discovers producers/recipients | Reverses ownership, requires source knowledge in notifications, and makes disablement/import order fragile. | Centralizes coupling, duplicates permission/serving logic, and risks recipient expansion. Rejected. |

This comparison does not authorize a generic domain event bus, app
auto-discovery, model reflection, signals for recipient discovery, broadcast
subscriptions, webhooks, event sourcing, Kafka, Celery, Redis, an outbox, or a
retry framework. V0 needs one narrow seam for directed in-app records only.

### Decision Record Before `NOTIFY.1A`

1. Notifications is a registered, gateable module, not Core.
2. The notifications module owns Notification persistence.
3. Each source module selects its recipient under source-domain rules.
4. Core owns only the directed emit/sink-registration seam plus its enablement
   and failure policy.
5. Source modules may import the Core notification port; they may not import
   the notifications app.
6. The notifications app may import Core; it may not import source modules.
7. Disabled Notifications makes an emit a safe no-op with no row and no source
   behavior change.
8. Ordinary post-commit persistence failure is logged and normally contained;
   strict development/test execution surfaces it.
9. The source owns the logical dedupe key; notifications owns database-backed
   idempotent persistence; Core owns neither.
10. `NOTIFY.1A` includes no producer.
11. `NOTIFY.1A` includes no center, bell, route, template, or member UI.
12. A notification never grants permission; its target enforces its own access.

## 5. Recommended V0 Scope

The complete smallest useful V0 (across separately approved slices) should
include:

- in-app notifications only;
- a notification center page;
- unread/read state;
- a notification bell with unread count;
- source module and source object reference;
- target URL;
- an idempotent notifications-owned persistence sink behind the Core delivery
  port;
- simple severity or category;
- no background scheduler;
- no external delivery.

V0 should favor low volume, explicit producer calls, and clear permission
boundaries over broad automated reminders.

## 6. Proposed Data Model

Planning-level likely fields:

- `recipient`: user receiving the notification;
- `source_module`: stable source module key such as `events`, `studies`,
  `community_events`, or `announcements`;
- `source_model_label`: optional label such as `events.ServiceEvent`;
- `source_object_id`: optional string/integer object id snapshot;
- `notification_type`: stable producer-owned type key;
- `title`: short user-facing title;
- `body` or `summary`: short user-facing supporting text;
- `target_url`: URL to the owning member/staff surface;
- `actor`: optional user who caused the change;
- `created_at`;
- `read_at`;
- `dedupe_key`: idempotency key;
- `severity` or `category`;
- `metadata`: optional JSON, used sparingly.

### Source References

Two reasonable approaches exist:

- Generic foreign key: convenient for navigation and admin inspection, but can
  encourage cross-module coupling and may expose object identity too easily.
- Explicit source fields: `source_module`, `source_model_label`, and
  `source_object_id` keep the notification record simple and decoupled, at the
  cost of no automatic ORM relation.

V0 should prefer explicit source fields unless implementation discovers a
strong reason for a generic foreign key. Target URL permission checks remain
mandatory either way.

### Indexing And Dedupe

Indexes should support the notification center and bell count:

- `recipient`, `read_at`, `created_at`;
- `recipient`, `dedupe_key`;
- possibly `source_module`, `source_model_label`, `source_object_id` for admin
  cleanup or debugging.

`dedupe_key` should be unique per recipient. A producer should be able to safely
call the helper multiple times without creating duplicates for the same logical
event.

### Retention And Cleanup

V0 can start with retained records and a documented future cleanup review.
Retention should later consider old read notifications, deleted source objects,
and privacy-sensitive text snapshots.

Cleanup must not delete or mutate source-module data.

### Privacy

Notifications can outlive source-object visibility. They therefore must be
careful with stored text.

A short text snapshot can be useful because titles may change or objects may be
cancelled, archived, or removed. The snapshot must avoid sensitive details and
should not store draft-only, staff-only, or private body content unless the
recipient is explicitly allowed to receive it under the source module's current
producer rule.

`metadata` should not store personal contact information, hidden staff notes,
private scope internals, or data that would be unsafe if the notification record
remains after the source object changes.

## 7. Producer Contract

Future source modules should call the Core-owned port, conceptually:

```python
emit_notification(
    *,
    recipient,
    source_module,
    notification_type,
    title,
    body,
    target_url,
    dedupe_key,
    source_model_label=None,
    source_object_id=None,
    actor=None,
    severity="info",
    metadata=None,
)
```

Producer contract:

- `dedupe_key` is required and idempotent for a recipient.
- The source module owns recipient resolution.
- The source module owns visibility, serving, and permission checks before
  calling the helper.
- The source module imports the Core port, never `notifications.services` or
  another notifications-app implementation module.
- The source module should call the port within its successful domain write
  path; Core arranges post-commit delivery.
- Core applies the disabled-module no-op and delivery failure policy described
  above.
- The notifications-owned sink persists idempotently and must not infer extra
  recipients from Church Structure, audience rows, serving rows, staff roles,
  source models, or target URLs.

## 8. Candidate V0 Producers

### A. Explicit ServiceEvent Serving Assignment

Implemented in `NOTIFY.1C`.

Recipient rule: notify the linked user on
`TeamAssignmentMember.membership.user`.

Emit once when an eligible linked user is newly assigned. For a retained
eligible member, emit at most once when the assignment changes ServiceEvent
and/or is reactivated from cancelled to active. Notes-only and same-event
non-cancelled status edits do not notify; removal and cancellation notifications
remain deferred. Do not notify display-name-only members. Do not notify all
event audience members. Do not make the assigned user an event audience member.

The target is `/my-serving/?tab=all#serving-assignment-<member-id>`, built from
the named My Serving route plus the stable `TeamAssignmentMember` anchor. It
never targets a staff edit or scheduling page.

### B. Explicit Bible Study Meeting Serving Role

Implemented in `NOTIFY.1D`.

Recipient rule: notify `BibleStudyMeetingRole.user`.

Emit `bible_study_role.assigned` when an eligible active linked user is newly
assigned, when a display-only role becomes linked, or when the role is
reassigned to a different linked user. Emit `bible_study_role.updated` only
when the same linked user remains and the serving role type changes. Recipient
reassignment has priority and produces only the assigned payload to the new
user. Notes, display-name, confirmation, deletion/removal, and lifecycle
changes do not notify. Display-name-only roles receive nothing. Meeting
audience, Church Structure belonging/coworker roles, managers, and staff never
expand recipients.

The target is the existing member-facing meeting detail. An explicit linked
role remains a serving fact even outside the ordinary meeting audience; it
creates no audience or membership row and uses the existing exact-meeting
read-only serving gate without granting management permission.

### C. Community Activity Review Outcome

V0 candidate, narrow only.

Recipient rule: notify the primary creator only.

Candidate outcomes: `changes_requested`, `published`, and
`rejected_cancelled`. Co-organizer notifications are later, not V0, unless a
separate approved slice says otherwise.

Do not notify selected-scope ordinary users for pending-review,
changes-requested, or other review states.

### D. Official Announcements

Later, not V0 by default.

Avoid turning notifications into an announcement feed. If announcement
notifications are ever added, they should be only for important, published,
active announcements and only through explicit product approval.

The existing Today one-item important-announcement reminder remains separate.

### E. ServiceEvent Audience-visible Event Updates

Later, not V0.

Do not notify everyone who can merely see an event. If this is ever added, it
must define explicit event update rules, cancellation rules, dedupe/noise
controls, and recipient visibility checks.

### F. Bible Study Ordinary Meeting Updates

Later, not V0.

Do not notify everyone in the meeting audience by default. If added later, the
producer must define which updates matter, how duplicates are avoided, and how
visibility is rechecked before notifying.

### G. System/Admin/Setup Notifications

Later, not V0 unless the product owner approves a specific setup workflow.

Do not use Notification V0 as a general staff dashboard, setup-readiness feed,
or admin warning system.

## 9. UI/UX Plan

Future V0 UI should be simple:

- bell in the authenticated navbar;
- unread count;
- `/notifications/` center;
- list items with title, short body, created time, source label, and read/unread
  state;
- mark one read;
- mark all read;
- empty state;
- mobile-friendly layout;
- no complex filters in V0;
- no notification preferences in V0.

The center should be quiet and scannable. It should not compete with Today as a
dashboard, Calendar as date discovery, My Serving as the serving workspace, or
Announcements as official staff-authored communication.

## 10. Permission And Privacy Failure Modes

Likely failures and guardrails:

- leaking draft, private, cancelled, archived, or staff-only objects;
- notifying audience members as if they are servers;
- notifying servers as if they are audience members;
- notifying normal users about staff-only objects;
- leaving a stale target URL after object cancellation or removal;
- duplicate notifications from repeated saves;
- notification spam from noisy edit flows;
- display-name-only people receiving impossible notifications;
- source object permission changes after notification creation;
- storing too much object text in the notification snapshot;
- turning a notification click into a permission bypass.

Guardrails:

- producer-owned recipient selection;
- mandatory idempotency keys;
- target URL permission checks;
- conservative stored text;
- focused producer tests for each source module;
- no background fanout until noise and permission rules are designed.

## 11. Rollout Slices

### NOTIFY.0A Docs-only Plan

Goal: create this boundary document and link it from the docs index.

Likely files: `docs/NOTIFICATIONS_V0_PLAN.md`, `docs/README.md`.

Risk: low; stale or too-broad planning language is the main risk.

Suggested agent: Codex.

Targeted tests/checks: `git diff --check`, targeted docs grep for the title and
index link.

### NOTIFY.0B Cross-module Delivery Architecture Alignment

Goal: resolve dependency direction before runtime by keeping Notifications a
registered module, Notification persistence module-owned, recipient selection
source-owned, and the directed delivery port/sink-registration contract in
Core.

Files: this plan plus narrow canonical module-boundary, roadmap, and docs-index
alignment.

Risk: low; documentation ambiguity is the only changed surface.

Targeted checks: required architecture term searches, `git diff --check`, and
diff/status review. No Django tests.

### NOTIFY.1A App/model/admin/Core Port Foundation

Status: implemented. The slice adds only the minimal `notifications` app,
Notification model/migration, registry entry, minimal admin, Core delivery port
and sink-registration contract, notifications-owned persistence sink/service,
database-backed idempotency, disabled-module no-op, post-commit delivery/failure
policy, and focused foundation tests. It includes no source producer and no
member-facing UI.

Likely files: `notifications/models.py`, `notifications/admin.py`, a small
notifications-owned persistence service/sink, `notifications/apps.py`, a small
Core delivery-port module, settings/module registry, migration, and focused
foundation tests. The notifications app may import Core; source modules are not
touched.

Risk: medium; model privacy, dedupe uniqueness, registration/import order,
disabled-module behavior, and failure containment set the foundation.

Targeted tests/checks: model/admin/port/sink tests, including repeated delivery,
disabled no-op, source rollback, post-commit success, production failure
logging/containment, and strict development/test failure surfacing;
`makemigrations --check --dry-run` after migrations are generated,
`manage.py check`, `git diff --check`.

### NOTIFY.1B Notification Center And Bell UI

Status: implemented. The slice adds the authenticated `/notifications/` center,
recipient-scoped newest-first list, safe bounded snapshot rendering, localized
source label from registry metadata (with a historical-key fallback), textually
visible read/unread state, POST-only/idempotent mark-one and mark-all actions,
and the notifications-owned bilingual utility bell/link with unread count. The
bell remains outside ordinary primary navigation; it is absent and performs no
Notification ORM query for anonymous requests or when the module is disabled.

The target path stays an ordinary permission-neutral link. It does not grant
access, auto-mark a row read, or load a source object. Stored title/body/source
text remains normally template-escaped. No model or migration change was needed.

Likely files: notification views/urls/templates, base navbar template, focused
tests.

Risk: medium; UI must stay member-safe, mobile-friendly, and permission-neutral.

Suggested agent: Codex.

Targeted tests/checks: focused notification view tests, navbar context/count
tests, `manage.py check`, `git diff --check`, browser QA if rendered UI changes.

### NOTIFY.1C Explicit ServiceEvent Serving Assignment Producer

Status: implemented. The first source producer is the ministry-owned
`ministry/services/assignment_notifications.py` helper. Approved interactive
assignment create/edit and team-schedule writes call it only after the
assignment and final member set save successfully; explicit copy-forward POST
therefore uses the same semantics, while suggestion GET remains read-only.

Recipients come only from active `TeamAssignmentMember.membership.user` rows on
an active team, non-cancelled assignment, and non-draft/non-cancelled
ServiceEvent. New linked member rows emit `team_assignment.assigned`; retained
rows emit at most one `team_assignment.updated` for ServiceEvent change and/or
cancelled-to-active reactivation. New-member semantics take priority when both
conditions occur. Display-name-only members receive nothing, and no recipient
is inferred from audience, Church Structure belonging, ministry role,
management authority, or staff status.

Snapshots use the recipient's persisted English/Chinese preference (English
fallback), contain only localized event title plus ministry-team name, exclude
notes/contact/audience internals, and target the exact existing My Serving
member-row anchor. The stable initial dedupe key uses the durable member-row id;
updates add the successful assignment `updated_at` mutation token, so repeated
execution of one save is idempotent while later genuine changes remain distinct.
No signal, schema/migration, notification ORM dependency, UI change, permission
change, or source serving/audience behavior change was added.

Likely files: `ministry` assignment save flow/forms/services, notification
producer helper tests.

Risk: high; must avoid notifying event audience, display-name-only members, or
granting serving/audience/management permissions.

Suggested agent: Codex for a narrow implementation; Claude/Opus if recipient or
permission interactions grow complex.

Targeted tests/checks: ministry assignment producer tests, duplicate-save
dedupe tests, display-name-only exclusion tests, permission non-regression tests,
`manage.py check`, `git diff --check`.

### NOTIFY.1D Explicit Bible Study Serving Role Producer

Status: implemented. The studies-owned
`studies/meeting_role_notifications.py` helper captures pre-save row identity,
linked user, role type, and meeting before ModelForm binding, then emits only
after approved interactive create/edit saves succeed. New linked roles,
display-only-to-linked changes, and user reassignment emit one assigned payload
to the current linked active user; same-user role-type changes emit one updated
payload. Recipient changes take priority over role-type changes.

Eligibility mirrors existing explicit Bible Study serving/read lifecycle:
published/completed meeting and lesson, active published/completed series, and
active linked user, without an audience-membership requirement. Snapshots use
the recipient's persisted language (English fallback), contain localized lesson
title plus role label, use empty metadata, and target the member-facing meeting
detail. The dedupe key combines durable role-row identity, notification kind,
and the successful save's `updated_at` mutation token, so repeated execution of
one mutation is stable while later updates and A -> B -> A reassignment remain
distinct.

No signal, schema/migration, Notification ORM dependency, UI, permission,
visibility, My Serving, Calendar, Today, audience, belonging, confirmation, or
role-picker behavior changed. Delete, confirmation, lifecycle, admin, direct
ORM, generation, setup/import, and failed-form paths remain non-producers.

Likely files: `studies` role form/save flow/services, notification producer
helper tests.

Risk: high; must not infer from display names, audience rows, or church
structure roles.

Suggested agent: Codex for a narrow implementation; Claude/Opus if recipient or
visibility complexity grows.

Targeted tests/checks: studies role producer tests, display-name-only exclusion
tests, outside-audience linked-role tests, duplicate-save dedupe tests,
`manage.py check`, `git diff --check`.

### NOTIFY.1E Community Activity Review Outcome Producer

Goal: add one producer by emitting through the Core port to the primary creator
for narrow review outcomes.

Likely files: `community_events` review action flow/services, notification
producer tests.

Risk: medium; co-organizers and selected-scope ordinary users must stay out of
V0 unless separately approved.

Suggested agent: Codex.

Targeted tests/checks: review outcome producer tests, creator-only tests,
co-organizer exclusion tests, selected-scope exclusion tests, `manage.py check`,
`git diff --check`.

### NOTIFY.1F Read/unread Polish And Cleanup/retention Review

Goal: improve read/unread ergonomics and decide the first retention policy after
real V0 usage.

Likely files: notification views/templates/services/tests, optional cleanup
management command if separately approved.

Risk: medium; cleanup must not mutate source data and must preserve audit/useful
records until retention rules are explicit.

Suggested agent: Codex.

Targeted tests/checks: read/unread tests, retention or cleanup dry-run tests if a
command is added, `manage.py check`, `git diff --check`, browser QA if rendered
UI changes.

Fable 5 should be reserved for hard architecture/planning questions. It is not
needed for routine docs, model, simple UI, or focused producer slices.

## 12. Current Implementation Recommendation

Keep `NOTIFY.1A` as the completed delivery foundation, `NOTIFY.1B` as the
completed notification-owned recipient UI boundary, `NOTIFY.1C` as the first
narrow ministry-owned producer, and `NOTIFY.1D` as the second narrow
studies-owned producer. None changes target permission, audience, belonging, or
source serving semantics.

Additional producers may be added one at a time only in separately approved
`NOTIFY.1E+` slices. Each producer must prove
recipient selection, idempotency, disabled-module behavior, and permission
neutrality in its own focused tests before another producer is added.
