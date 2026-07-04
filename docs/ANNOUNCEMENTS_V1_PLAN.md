# Official Announcements V1 Plan

Status: canonical product and implementation plan (July 2026).
`ANNOUNCEMENTS.1A` through `ANNOUNCEMENTS.1D-SLIM` are implemented.
`ANNOUNCEMENTS.1E` is a docs/QA closure slice only.
`ANNOUNCEMENTS-QA-PASS.1A` records that the product owner manually ran the
bounded checklist and confirmed it passed.

## 1. Purpose and product boundary

Official Announcements is a bounded pastor/staff communication module for
publishing official church information to selected structure audiences. It is
an independent `announcements` Django app with module registry key
`announcements`.

Official Announcements is:

- official staff-authored church communication;
- member-facing read-only content after publication;
- audience-scoped through app-owned rows linked to `ChurchStructureUnit`; and
- bilingual, time-bounded, and deliberately low-noise.

It is not Community Activities, `ServiceEvent`, My Serving, serving, or a
notifications platform. It does not add Community Activities behavior or reuse
activity signup/review concepts.

## 2. V1 data contract

### `Announcement`

The planned V1 record contains:

- `title` and `title_en`;
- `body` and `body_en`;
- `status`: `draft`, `published`, or `archived`;
- `priority`: `normal` or `important`;
- `publish_start` and optional `publish_end`;
- `created_by`;
- `published_by` and `published_at`;
- normal `created_at` and `updated_at` timestamps.

The bilingual fallback follows existing project patterns: Chinese/default
content is canonical; an English field falls back to the default field when it
is blank.

`publish_end`, when present, must be later than `publish_start`. Publishing
records the acting staff user and actual transition time in `published_by` and
`published_at`. A future `publish_start` schedules visibility without changing
the record to another status. Passing `publish_end` ends ordinary visibility
without automatically rewriting the status. Archiving is an explicit staff
action and does not delete the record or its audience rows.

### `AnnouncementAudienceScope`

Each audience row links one `Announcement` to one active
`ChurchStructureUnit`. Duplicate announcement/unit pairs are forbidden.
Overlapping rows may be rejected by the staff form for clarity, but visibility
must remain correct if historical or administrative data contains them.

Audience rows are visibility data only. They do not create membership, staff
authority, serving assignments, ministry roles, or management permission.

## 3. Visibility and permission rules

An announcement is ordinarily visible only when all of these are true:

1. the viewer is authenticated;
2. the status is `published`;
3. `publish_start` is at or before the current time;
4. `publish_end` is blank or after the current time; and
5. at least one audience row targets the viewer's active primary
   `ChurchStructureMembership` unit or one of that unit's ancestors.

The app should own one reusable queryset helper, such as
`visible_announcements_for(user, queryset=None, at=None)`, and member list,
detail, and Today reads must use it. Zero audience rows fail closed for
ordinary users. Missing, inactive, non-primary, or nonmatching membership also
fails closed.

Permission boundaries:

- staff and superusers may create, edit, publish, and archive announcements;
- ordinary users may only view visible, published, currently active
  announcements;
- member-facing list/detail routes use the published visibility helper and do
  not expose drafts or archived records;
- staff management routes may show every lifecycle state;
- `ChurchStructureMembership` is belonging and audience visibility only; and
- neither membership nor audience scope grants staff capability, serving,
  My Serving state, or any other role.

Publishing through the normal staff workflow should require at least one valid
audience row. Runtime visibility must still fail closed if a published
zero-audience row is created through historical data or another administrative
path.

## 4. Member, staff, navigation, and Today surfaces

V1 member surfaces are a module-gated Announcements / 公告 primary-navigation
entry, a concise list of visible active announcements, and a detail page.
Important items may be visually distinguished, but priority never changes
visibility or permission.

Staff/superusers receive a bounded management list plus create/edit and
POST-only publish/archive transitions. V1 does not add an approval workflow:
the authorized staff publisher is the publisher.

Today remains a low-noise agenda/dashboard, not an announcement feed.
`ANNOUNCEMENTS.1D-SLIM` adds only a compact reminder containing at most one
visible, active, `important` announcement, selected by newest `publish_start`
with deterministic creation/id tie-breakers. It shows the localized title as
a link to the owning detail page, not full bodies, excerpts, history,
normal-priority items, or an infinite/latest-announcements feed.
Disabled-module aggregation returns a safe `None` default, does not call the
provider, and does not query announcements.

Announcements never contribute to My Serving, the serving action center,
Leader Needs Attention, or Staff Overview.

## 5. Explicit V1 non-goals

V1 does not include:

- comments;
- reactions;
- read receipts;
- attachments or a file center;
- a rich text editor;
- email, SMS, WeChat, push, or app notifications;
- recurring announcements;
- per-user dismiss or snooze state;
- analytics;
- an approval or request-changes workflow;
- announcement templates;
- Staff Overview cards, counts, or alerts;
- announcement-to-`ServiceEvent` linking;
- signup, attendance, capacity, waitlist, or check-in;
- `TeamAssignment` or `TeamAssignmentMember`;
- `BibleStudyMeetingRole`;
- My Serving or any serving state; or
- Community Activities models, routes, permissions, review, signup, or Today
  behavior.

Any later addition requires its own explicit product and implementation slice.

## 6. Implementation slices

Each slice requires separate approval before code changes. Do not silently pull
a later slice into an earlier one.

### ANNOUNCEMENTS.1A — Model, admin, and visibility foundation

Status: implemented (July 2026).

Add the independent app, `Announcement`, `AnnouncementAudienceScope`, the
initial migration, Django admin, model validation, bilingual accessors, and the
structure-native visibility helper. Do not add member routes, module registry
metadata, navigation, staff workflow pages, or Today integration yet.

Targeted expectations:

- model tests cover statuses, priorities, bilingual fallback, and publish
  window validation;
- audience tests cover exact-unit and descendant membership matches;
- visibility tests cover unpublished, not-yet-started, expired, archived,
  inactive/non-primary/nonmatching membership, and zero-row fail-closed cases;
- permission tests prove membership/audience grants no staff or serving
  authority;
- run focused `announcements` tests, `manage.py check`,
  `makemigrations --check --dry-run`, and `git diff --check`.

### ANNOUNCEMENTS.1B — Registry, navigation, member list/detail

Status: implemented (July 2026).

Register module key `announcements` with navigation, Today, and structure-core
capability metadata; add the module-gated ordinary primary-nav entry and
member-facing list/detail routes. Both member pages use the 1A visibility
helper. Do not add staff workflow pages or Today output yet.

The implemented member routes use a separate public/member visibility helper,
so staff and superusers do not carry the 1A management-inspection bypass into
the ordinary list or detail page. The routes therefore require published
status, an active publish window, and a matching active primary structure
membership for every viewer. Module disablement hides the ordinary nav entry
but does not hard-disable direct URLs. The registry reserves
`contributes_today` capability metadata for 1D; 1B registers no Today provider
and produces no Today output.

Targeted expectations:

- registry tests cover the key, labels, capabilities, default enablement, and
  unknown/dependency validation;
- navigation tests cover enabled/disabled module states and bilingual labels;
- list/detail tests cover ordering, language fallback, active-window filtering,
  audience isolation, zero-row fail-closed behavior, and hidden-detail 404;
- disabled-module surface tests confirm the nav is hidden;
- run focused `announcements` and relevant registry/nav tests plus the standard
  Django and diff checks.

### ANNOUNCEMENTS.1C — Staff create/edit/publish/archive

Implemented in July 2026. Staff/superuser-only management pages and forms show
all lifecycle states and provide module-gated staff navigation. Create/edit
saves announcement fields and audience rows atomically. Publish and archive
are POST-only explicit transitions; publish validates the time window and at
least one active audience unit and records `published_by` / `published_at`.
Create always starts as draft, edit does not implicitly publish, overlapping
audience units are rejected, duplicate selections are normalized, archived
announcements cannot be republished, and archive preserves the announcement
and its audience rows. Member-facing 1B visibility remains unchanged, and 1C
adds no Today, Staff Overview, notification, event/activity, signup,
attendance, approval, request-changes, My Serving, or serving state.

Targeted expectations:

- access tests deny anonymous and ordinary users even when they have matching
  membership;
- form tests cover bilingual fields, priority, time windows, audience
  replacement, duplicate/invalid selections, and atomic failure;
- lifecycle tests cover draft creation, edit, publish attribution, scheduled
  start, archive, and rejected invalid transitions;
- tests prove management changes create no serving, role, event, signup, or
  Community Activities state;
- run focused staff workflow tests plus the standard Django, migration, and
  diff checks.

### ANNOUNCEMENTS.1D-SLIM — Today low-noise provider

Status: implemented (July 2026).

The module-owned Today provider and compact card stay exactly within Section 4:
important only, visible and active only through the member/public visibility
helper, maximum one, localized title/detail link only, and no serving or
action-center semantics. Registration uses the existing explicit Today
provider site. Disabled-module aggregation keeps the safe empty default and
skips the provider query.

Targeted expectations:

- provider tests cover audience and publish-window visibility;
- tests prove normal-priority, draft, archived, expired, future, zero-audience,
  and nonmatching announcements are absent;
- ordering/cap tests prove important-first semantics are unnecessary because
  normal items are excluded, newest `publish_start` wins, and no more than one
  row is returned;
- disabled-module tests prove safe empty defaults and no provider query;
- Today boundary tests prove no My Serving, serving action-center, Leader Needs
  Attention, or Community Activities behavior changes;
- run focused provider/Today/registry tests plus the standard checks.

### ANNOUNCEMENTS.1E — QA and docs closure

Status: docs/QA closure implemented (July 2026); manual QA passed by user
confirmation in `ANNOUNCEMENTS-QA-PASS.1A`.

This slice aligns canonical docs with the implemented 1A through 1D-SLIM
runtime and prepares the bounded bilingual staff/member lifecycle checklist.
It adds no runtime feature. The later user-confirmed pass makes Announcements
V1 acceptable for limited trial use under the existing trial boundary; it is
not a production-readiness claim.

Targeted expectations:

- manual QA covers staff create/edit/publish/archive; ordinary matching and
  nonmatching users; scheduled/expired visibility; bilingual list/detail; nav
  enablement; and the one-item important-only Today reminder;
- rerun focused announcement, registry, navigation, and Today tests;
- run `manage.py check`, `makemigrations --check --dry-run`, and
  `git diff --check`;
- record applied migration and deployment/setup evidence separately for each
  target environment.

## 7. ANNOUNCEMENTS.1E Manual QA

QA closure (`ANNOUNCEMENTS-QA-PASS.1A`): Manual QA passed by product-owner
confirmation. The pass covered every item below with suitable staff,
matching-member, and nonmatching-member accounts. This is evidence for limited
trial use under the existing trial boundary, not a production-readiness claim.

### Staff setup and lifecycle

- [x] With the `announcements` module enabled, staff can open Announcement
  Admin from the Staff dropdown.
- [x] Staff can create, save, and later edit a draft announcement.
- [x] Staff can select Audience Scope with the existing
  `ChurchStructureUnit` picker.
- [x] Staff can save a normal announcement.
- [x] Staff can save an Important announcement.
- [x] The Important checkbox help text is visible and makes clear that the
  item may appear on Today but never bypasses audience visibility.
- [x] Staff can publish a valid draft.
- [x] Publishing records the acting staff user in `published_by` and the
  transition time in `published_at`.
- [x] A future `publish_start` remains hidden from ordinary member visibility
  until the active window begins.
- [x] Passing `publish_end` hides the announcement from ordinary member
  visibility.
- [x] Staff can archive a published announcement.
- [x] Archiving hides the announcement from member list/detail, makes hidden
  member detail return 404, and preserves its audience rows.

### Member visibility and bilingual display

- [x] An ordinary matching member can see a published, active,
  audience-visible announcement in list and detail.
- [x] An ordinary nonmatching member cannot see that announcement.
- [x] Direct access to any announcement hidden from the viewer returns 404.
- [x] Bilingual list/detail display and fallback work in the supported
  language modes.

### Today and module surface gates

- [x] Today shows at most one Important, active, audience-visible announcement.
- [x] The Today card shows the localized title/detail link only, with no body
  or excerpt.
- [x] A normal-priority announcement does not appear on Today.
- [x] Important priority never bypasses audience visibility.
- [x] With the `announcements` module disabled, the ordinary nav entry, Staff
  dropdown link, and Today card are hidden through the existing surface gates;
  this check does not assert route hard-off behavior.

### Product-boundary regression check

- [x] The exercised lifecycle creates no My Serving or serving action-center
  item, Leader Needs Attention item, Staff Overview card/count/link,
  `ServiceEvent` relationship, Community Activities behavior, signup,
  attendance, notification, or approval/request-changes workflow.

The product owner confirmed that every applicable item was exercised and
passed. Announcements V1 is acceptable for limited trial use under the existing
trial boundary. This remains a limited-trial statement, not a
production-readiness claim.

## 8. Future bilingual staff setup guide

Do not create `STAFF_SETUP_GUIDE.md` in `ANNOUNCEMENTS-QA-PASS.1A`. Because the
manual QA pass is now recorded, a later separate docs slice may create the
bilingual staff setup guide from shipped behavior. It should include:

- the limited-trial prerequisite and the existing 0-blocker / 19-warning
  setup-readiness result, clearly labeled as not a production deployment claim;
- enabling the `announcements` module and confirming the member nav surface;
- confirming staff/superuser authority without deriving it from membership;
- creating bilingual title/body content;
- selecting active structure audience units and explaining descendant
  visibility;
- setting priority and the publication window;
- draft, publish, edit, archive, and scheduled/expired behavior;
- checking a matching and nonmatching ordinary member;
- checking the capped important-only Today reminder; and
- the explicit separation from Community Activities, `ServiceEvent`,
  notifications, and all serving/My Serving workflows.

The setup guide must describe shipped behavior only. Its creation is a later
docs slice, not authorization to implement or broaden Announcements V1.

## 9. Approval boundary

This document originally approved planning only. `ANNOUNCEMENTS.1A` later
received explicit approval and added the independent app, models, initial
migration, Django admin, model validation, bilingual accessors, focused tests,
and structure-native visibility helper. `ANNOUNCEMENTS.1B` later received
explicit approval and added only registry/default enablement, the bilingual
module-gated ordinary nav entry, and authenticated member list/detail routes
using public/member visibility. It created no migration or data change and
added no staff workflow, Today provider/output, Staff Overview, notification,
Community Activities, `ServiceEvent`, My Serving, or serving behavior.
`ANNOUNCEMENTS.1C` later received explicit approval and added the bounded
staff/superuser management list, create/edit forms, and POST-only
publish/archive workflow described above, without a migration or cross-module
state. `ANNOUNCEMENTS.1D-SLIM` later received separate approval and added only
the module-owned, module-gated Today provider and one-item localized
title/detail-link card described above, without a model change, migration,
feed, Staff Overview integration, or serving/cross-module state.
`ANNOUNCEMENTS.1E` later received approval as docs/QA closure only. It added the
unchecked manual-QA checklist and aligned canonical status wording without
changing runtime behavior, models, migrations, Today behavior, or cross-module
state. `ANNOUNCEMENTS-QA-PASS.1A` later recorded the product owner's
confirmation that the checklist passed, without adding runtime expectations or
changing code. Announcements V1 is therefore acceptable for limited trial use
under the existing trial boundary, not certified as production-ready.
