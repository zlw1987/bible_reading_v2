# Notification V0 Plan

Status: planning only. No notification runtime is implemented by this plan.
Implementation requires separately approved slices.

This document is a practical implementation boundary for future notification
work. It does not authorize app creation, models, migrations, routes, templates,
producer hooks, background jobs, external delivery, or any permission changes.

## 1. Status

`NOTIFY.0A` is docs-only planning.

No notification runtime is implemented. There is no `notifications` app, no
notification model, no notification center, no bell UI, no producer helper, and
no source-module emission logic from this plan.

Future implementation must be approved one small slice at a time. Planning text
here is not authorization to add runtime behavior.

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

## 5. Recommended V0 Scope

The smallest useful V0 should include:

- in-app notifications only;
- a notification center page;
- unread/read state;
- a notification bell with unread count;
- source module and source object reference;
- target URL;
- an idempotent producer helper;
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

Future implementation should expose a conceptual helper such as:

```python
notify_user(
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
- The helper should log failures clearly.
- The helper should not break source save flows for ordinary transient failures.
- Persistent failures must not be silently hidden in tests or development.
- The helper must not infer extra recipients from church structure, audience
  rows, serving rows, staff roles, or target URLs.

## 8. Candidate V0 Producers

### A. Explicit ServiceEvent Serving Assignment

V0 candidate.

Recipient rule: notify the linked user on
`TeamAssignmentMember.membership.user`.

Emit when a linked user is newly assigned or a meaningful assignment detail
changes. Do not notify display-name-only members. Do not notify all event
audience members. Do not make the assigned user an event audience member.

The target can be My Serving or an assignment detail if one exists. It must not
target a staff edit page for ordinary users.

### B. Explicit Bible Study Meeting Serving Role

V0 candidate.

Recipient rule: notify `BibleStudyMeetingRole.user`.

Emit when a linked user is newly assigned or a meaningful role detail changes.
Do not notify display-name-only roles. Do not notify all meeting audience
members. Do not infer recipients from church structure role, active primary
membership, or audience scope.

The target can be My Serving or the meeting detail if existing permission allows
the linked user to open that meeting.

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

### NOTIFY.1A App/model/admin/service Helper Foundation

Goal: add the minimal `notifications` app, model, admin, and idempotent helper
without source producers.

Likely files: `notifications/models.py`, `notifications/admin.py`,
`notifications/services.py`, `notifications/apps.py`, settings/app registry,
migration, focused tests.

Risk: medium; model privacy, dedupe uniqueness, and app-boundary choices set the
foundation.

Suggested agent: Codex.

Targeted tests/checks: model/admin/service helper tests,
`makemigrations --check --dry-run` after migrations are generated,
`manage.py check`, `git diff --check`.

### NOTIFY.1B Notification Center And Bell UI

Goal: add authenticated notification center, unread count, bell link, mark-one
read, and mark-all-read.

Likely files: notification views/urls/templates, base navbar template, focused
tests.

Risk: medium; UI must stay member-safe, mobile-friendly, and permission-neutral.

Suggested agent: Codex.

Targeted tests/checks: focused notification view tests, navbar context/count
tests, `manage.py check`, `git diff --check`, browser QA if rendered UI changes.

### NOTIFY.1C Explicit ServiceEvent Serving Assignment Producer

Goal: emit notifications for linked-user `TeamAssignmentMember` serving
assignment creation or meaningful changes.

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

Goal: emit notifications for linked-user `BibleStudyMeetingRole` assignment
creation or meaningful changes.

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

Goal: notify the primary creator about narrow review outcomes.

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

## 12. First Implementation Recommendation

Do not implement notifications in this task.

When ready, start with model/helper foundation only. The first implementation
slice should not touch source producers yet.

Add producers one at a time after the foundation and UI exist. Each producer
must prove recipient selection, idempotency, and permission neutrality in its
own focused tests before another producer is added.
