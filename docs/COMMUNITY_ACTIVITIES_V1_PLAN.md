# Community Activities V1 Plan

Status: current plan and stabilization checkpoint updated through
`COMMUNITY-EVENTS-STABILIZATION.1A` (July 2026).
The independent `community_events` app foundation is implemented and
registered. `CommunityActivity`, `CommunityActivityAudienceScope`, migration
`community_events/0001_initial`, structure-native visibility, and Django admin
exist.

`COMMUNITY-EVENTS.1B` adds an independent member-facing browse/detail entrance
(`/activities/` and `/activities/<id>/`, route names `community_activity_list`
and `community_activity_detail`) and an ordinary primary-nav entry (English
"Activities" / Chinese "活动", `active_nav="community_events"`, ordered after
Church Gatherings and before My Serving). The list shows visible upcoming
published activities through the existing structure-native visibility helper;
the detail view denies with 404 when `can_be_seen_by` is false. Nav visibility
is gated by module enablement; the routes themselves have no route-level
hard-off and stay governed by their login/visibility rules.

`COMMUNITY-EVENTS.1C` adds `ActivitySignup` in migration
`community_events/0002_activitysignup`, plus minimal member-facing POST actions
to sign up and cancel. Each activity/user pair keeps one lifecycle row:
cancellation sets `cancelled`, and signing up again reactivates it to
`signed_up`. Signup is allowed only for authenticated users who can see a
published upcoming activity. It is attendance intent, never serving.

`COMMUNITY-EVENTS.1D-A` adds the bounded member submission + admin publish
gate. An ordinary authenticated user with an active primary
`ChurchStructureMembership` may submit at `/activities/new/` unless an active
`CommunityActivitySubmissionBlock` exists for that user. The submitted
activity starts `pending_review` and records the submitter in `created_by`.

`COMMUNITY-EVENTS.1D-A-FU1` replaces the note-only scope request with a
required `ChurchStructureUnit` Activity Scope picker. Members may select active
units, including the root/whole-church unit, language-ministry units, district
units, small-group units, or multiple non-overlapping units. Creation
atomically saves those selections as `CommunityActivityAudienceScope` rows.
The optional `requested_audience_note` remains review context and does not
control visibility. Creators can see their own pending submissions; other
ordinary users cannot, including users inside the selected scope.
Staff/superusers use Django admin to adjust audience rows and publish.

`COMMUNITY-EVENTS.1D-B` adds a lightweight staff review inbox and a minimal
request-changes loop. It adds a `changes_requested` status and the review
metadata fields `review_note`, `reviewed_by`, and `reviewed_at`
(migration `community_events/0004`). A staff/superuser-only inbox at
`/activities/review/` lists pending-review and changes-requested submissions
newest first, and `/activities/<id>/review/` offers POST-only publish, request
changes (requires a non-empty note), and cancel/reject actions that record the
reviewer and time without deleting the activity or its audience rows. When
staff request changes, the creator may edit and resubmit their own
`changes_requested` activity at `/activities/<id>/edit/`, which transactionally
replaces the audience rows with the newly selected valid scope units and moves
the activity back to `pending_review`; the prior review note is preserved for
context. Ordinary selected-scope users still cannot see pending-review or
changes-requested activities, and signup stays limited to published upcoming
activities. A staff-dropdown "Activity Review" / "活动审核" link appears only when
the `community_events` module is enabled.

A full approval dashboard beyond this inbox, waitlist, My Serving, any
`ServiceEvent` relationship, Staff Overview, setup/readiness provider, and
notifications remain deferred.

`COMMUNITY-EVENTS.1E-A` adds the minimal module-owned Today contribution.
Today shows only published visible activities happening today for which the
current user has an active `signed_up` attendance-intent row. A separate
creator reminder shows only the current user's own `changes_requested`
submissions with an edit/resubmit link. Later-this-week signups and
`pending_review` submissions stay on the owning Activities surfaces rather
than Today. Visible activities without an active signup do not appear.
Published creator activities do not appear merely because the user created
them. The provider is skipped, with empty context defaults, when the module is
disabled.

This Today card is ordinary activity agenda/review status, never serving. My
Serving, the serving action center, Staff Overview, setup/readiness,
waitlist, notifications, and any `ServiceEvent` relationship remain
deferred.

`COMMUNITY-EVENTS.1F-A` allows the primary creator to edit their own
`pending_review` activity without taking it out of review. Saving keeps the
activity `pending_review`; ordinary selected-scope users still cannot see it.
This changes no staff review authority, audience visibility, signup, serving,
My Serving, Today serving action, or `ServiceEvent` relationship.

`COMMUNITY-EVENTS.1G-A` adds optional user-linked co-organizers without
changing primary ownership. `CommunityActivity.created_by` remains the
accountable creator, while `CommunityActivity.organizer` remains public display
copy only and grants no permission. The primary creator may select active users
through an authenticated search picker and update that list. Linked
co-organizers initially gained view/edit access while an activity is
`pending_review` or `changes_requested`; `COMMUNITY-EVENTS.1H-A` extends that
bounded access to drafts. They cannot change the co-organizer list, publish,
request changes, cancel/reject, or enter the staff review inbox. This
permission creates no serving assignment, My Serving item, Bible Study role,
Today serving action, or `ServiceEvent` relationship.

`COMMUNITY-EVENTS.1F-B` adds optional signup capacity. A null
`CommunityActivity.capacity_limit` means no limit; a positive integer is the
maximum number of active `signed_up` rows. Cancelled rows do not count.
Signup checks serialize on the activity row, reactivation preserves the
existing lifecycle row, and a full activity fails closed for a new or
cancelled signup. An already-active signup stays idempotent. This is
attendance-intent management only, not serving. Waitlist, attendee list,
notifications, check-in, and signup deadlines remain deferred.

`COMMUNITY-EVENTS.1H-A` adds the member-facing draft workflow. Eligible
members may save the complete, validated create form as `draft` or submit it
directly as `pending_review`. Drafts still require Activity Scope and all
existing required fields; audience rows, capacity, and co-organizer links save
in the same transaction. Only the primary creator, linked co-organizers, and
staff/superusers may see a draft. The creator manages co-organizers and may
submit the draft for review; linked co-organizers may edit details and Activity
Scope but cannot change the co-organizer list or submit the draft. Drafts stay
outside the staff review inbox, selected-scope visibility, signup, Today, My
Serving, and every serving or `ServiceEvent` workflow.

## 1. Purpose

Community Activities is an independent module foundation for future
member/community/fellowship activity signup.

The project remains a lightweight church spiritual life and ministry workflow system. Community Activities should not turn the project into a full church ERP.

Example activities:
- small group meal
- hiking activity
- district fellowship
- whole-church picnic
- special community gathering

## 2. Product Boundary

Community Activities owns signup-oriented community activities.

It is not:
- Daily Reading
- Bible Study content or preparation
- Prayer
- Ministry Team Operations
- TeamAssignment
- ServiceEvent scheduling
- Checklist V1
- a full church ERP

Rule of thumb:
- If the main question is "which ministry team is serving?", use ServiceEvent + TeamAssignment.
- If the main question is "who wants to attend/signup?", use CommunityActivity + ActivitySignup.
- "Special event" is not one model by itself. Choose ServiceEvent, CommunityActivity, or both later based on the main product question.

Community Events/Activities does not create `TeamAssignment`,
`TeamAssignmentMember`, `BibleStudyMeetingRole`, or My Serving items. Signup,
audience visibility, and `ChurchStructureMembership` express attendance intent
or belonging, never serving. Serving exists only through an explicit
`TeamAssignmentMember` or linked-user `BibleStudyMeetingRole.user`.

## 3. Relationship to ServiceEvent

ServiceEvent remains the official church gathering, operations, and ministry assignment anchor.

CommunityActivity is for signup-oriented community and fellowship activities. Do not merge CommunityActivity into ServiceEvent in V1.

An optional future relationship to ServiceEvent may be considered later for large official events, but that link is not part of Community Activities V1.

Do not create a separate SpecialEvent model in V1.

## 4. Models

`COMMUNITY-EVENTS.1A` implements the first two models below.
`COMMUNITY-EVENTS.1C` implements `ActivitySignup`.
`COMMUNITY-EVENTS.1D-A` extends `CommunityActivity` and adds the submission
block model.
`COMMUNITY-EVENTS.1F-B` adds optional signup capacity to `CommunityActivity`.

### CommunityActivity

Implemented fields:
- title
- title_en
- description
- description_en
- organizer
- start_datetime
- end_datetime
- location
- location_en
- capacity_limit (optional; null means unlimited, a positive integer is the
  maximum number of active signups)
- status:
  - draft
  - pending_review
  - changes_requested
  - published
  - cancelled
  - completed
- requested_audience_note (optional; staff review context only, never runtime
  visibility)
- review_note (optional; staff explanation attached when requesting changes or
  cancelling, shown to the creator on their own `changes_requested` activity)
- reviewed_by (staff/superuser who last took a review action; `SET_NULL`)
- reviewed_at (timestamp of the last review action)
- created_by
- created_at
- updated_at

The `organizer` field is public display copy only. It does not identify a user,
grant permission, or replace `created_by` as the primary owner/accountable
submitter.

Signup deadlines and a full approval workflow/dashboard beyond the
`COMMUNITY-EVENTS.1D-B` inbox remain outside the current model.

### CommunityActivityAudienceScope

This is an app-specific audience join model following the current
structure-native pattern rather than any legacy `scope_type`,
`MinistryContext`, `District`, or `SmallGroup` fields.

Implemented fields:

- `activity`: FK to `CommunityActivity`;
- `structure_unit`: FK to `ChurchStructureUnit`;
- normal audit/timestamp fields only if the approved implementation needs
  them.

Each row selects one `ChurchStructureUnit`. Multiple rows express a union of
selected structure subtrees. The implementation must not recreate legacy
audience-segment tables or depend on retired legacy structure models.

ServiceEvent and Bible Study V2 already use app-specific structure audience
rows. Community Activities reuses the architectural pattern while owning its
own model and visibility query. See
`docs/FLEXIBLE_CHURCH_STRUCTURE_AND_AUDIENCE_SCOPE_DESIGN.md`.

### ActivitySignup

Implemented fields:
- activity
- user
- status:
  - signed_up
  - cancelled
- created_at
- updated_at

There is one row per activity/user. Cancelling preserves that row, and a later
signup reactivates it. `COMMUNITY-EVENTS.1F-B` later adds capacity enforcement
using only active `signed_up` rows. Waitlist, notes, approval, and
attendance/check-in are not part of the current lifecycle.

### CommunityActivitySubmissionBlock

Implemented in `COMMUNITY-EVENTS.1D-A`:

- user
- is_active
- reason
- created_by
- created_at
- updated_at

There is at most one block row per user. Only an active row prevents member
submission; staff manage these rows in Django admin.

### CommunityActivityCoOrganizer

Implemented in `COMMUNITY-EVENTS.1G-A`:

- activity
- user (active user selected through the co-organizer picker)
- added_by
- created_at

Each `(activity, user)` pair is unique. The primary creator cannot also be a
co-organizer. These links grant only the bounded pre-publication edit
permission described below; they are not attendance, belonging, staff
capability, or serving records.

## 5. Scope and Visibility Rules

Ordinary-user visibility is structure-native:

- resolve the user's active primary `ChurchStructureMembership`;
- an activity matches when that membership's `structure_unit` is the selected
  `ChurchStructureUnit` or one of its descendants;
- any matching `CommunityActivityAudienceScope` row is sufficient;
- zero audience rows fail closed for ordinary users.

There is no implicit `whole_church` audience type. If a future product slice
needs whole-church visibility, it must explicitly approve and test a policy
such as selecting the canonical root unit. It must not make zero rows mean
whole church.

Examples use canonical structure units, not legacy model types:

- select one language-ministry unit to include memberships on that unit and
  all descendant units;
- select several group units to include only those selected subtrees;
- select units from different branches to form a mixed audience;
- select the canonical root unit only under an explicitly approved
  whole-church/root-row policy.

Users outside every selected structure subtree must not see the activity or
sign up for it. `COMMUNITY-EVENTS.1A` gives authenticated staff and superusers
the minimal management/visibility bypass. It does not invent a leader or
structure-role permission.

`COMMUNITY-EVENTS.1C` permits signup only when the activity is published and
its start time is in the future, including for staff/superusers. Hidden,
nonmatching, and zero-audience activities fail closed for ordinary users.
Cancellation updates an existing visible user's lifecycle row; it never
deletes the row.

`COMMUNITY-EVENTS.1D-A` does not change the published audience helper:
pending-review activities remain absent from ordinary public results.
The creator gets a narrow object-level exception to view their own submission
and status. Staff/superusers retain the existing management bypass.
`COMMUNITY-EVENTS.1D-A-FU1` validates the submitted Activity Scope and creates
all selected audience rows in the same transaction as the activity, so the
normal create path cannot leave a zero-row submitted activity. The rows affect
ordinary visibility only after staff publish.

`COMMUNITY-EVENTS.1H-A` adds the creator-owned draft exception. Drafts are
visible only to their primary creator, linked co-organizers, and the existing
staff/superuser management bypass. Selected-scope ordinary users receive no
draft visibility, and audience rows still have no ordinary visibility effect
until publication. Drafts cannot be signed up for.

The UI and queries should avoid exposing private membership data. An activity
list should answer "can this user see this activity?" rather than showing
internal membership lists. See `docs/CHURCH_STRUCTURE_FOUNDATION_PLAN.md` for
the canonical hierarchy and belonging foundation.

## 6. Permission Direction

Keep permissions simple.

Regular member:
- can view published activities within scope
- can sign up or cancel their own signup
- with an active primary membership and no active submission block, can submit
  an activity for review or save it as a draft
- must select one or more valid active, non-overlapping Activity Scope units
- can view and continue editing their own drafts
- can view their own pending/changes-requested/cancelled/published submissions
- can submit their own draft for staff review
- when staff request changes, can edit and resubmit their own
  `changes_requested` activity, which returns it to `pending_review`
- cannot publish

Linked co-organizer:
- can view and edit the linked activity only while it is `draft`,
  `pending_review`, or `changes_requested`
- can edit activity details and Activity Scope; saving a
  `changes_requested` activity returns it to `pending_review`
- can save a linked draft as draft, but cannot submit it for review
- cannot change the co-organizer list (primary creator only)
- cannot edit published, cancelled, or completed activities
- cannot publish, request changes, cancel/reject, or access the staff review
  inbox
- gains no staff capability, serving assignment, My Serving item, or role

Authorized structure-unit leader:
- may create or manage activity for an authorized unit only if a future
  implementation explicitly maps existing capability/role rules to that
  action

Staff:
- can create and manage all activities
- can approve, publish, and cancel activities
- can create churchwide activities
- uses the same published-upcoming rule for personal signup actions

Avoid a complex role hierarchy in V1.

## 7. Approval Direction

The implemented `COMMUNITY-EVENTS.1D-A` plus `1D-A-FU1` policy is deliberately
small:

- every member-created activity is explicitly saved as `draft` or submitted
  as `pending_review`;
- the member must select at least one valid active Activity Scope unit;
- root plus another unit and ancestor/descendant overlaps are rejected;
- selected units are saved as app-owned audience rows in the activity creation
  transaction;
- `requested_audience_note` may explain the selection or request an adjustment,
  but has no runtime visibility effect;
- ordinary users cannot publish, and selected-scope members cannot see or sign
  up for the activity before publication.

`COMMUNITY-EVENTS.1H-A` keeps drafts outside review:

- Save draft keeps the activity in `draft`;
- only the primary creator may submit a draft, moving it to `pending_review`;
- draft rows never appear in the review inbox;
- editing `pending_review` keeps it pending, while saving
  `changes_requested` returns it to pending review as before.

`COMMUNITY-EVENTS.1D-B` adds a lightweight staff-facing review loop on top of
that policy:

- a staff/superuser-only inbox at `/activities/review/` lists pending-review
  and changes-requested submissions newest first with creator, start time,
  status, selected scope labels, and any scope/review note;
- the staff review detail at `/activities/<id>/review/` offers POST-only
  publish, request changes, and cancel/reject actions;
- publish is allowed from `pending_review` or `changes_requested`; request
  changes is allowed from `pending_review` and requires a non-empty
  `review_note`; cancel/reject is allowed from either review status with an
  optional note;
- every action records `reviewed_by` and `reviewed_at` and never deletes the
  activity or its audience rows;
- when staff request changes, the creator may edit and resubmit their own
  `changes_requested` activity, transactionally replacing the audience rows and
  returning it to `pending_review`;
- staff may still adjust audience rows in Django admin.

A larger review dashboard, leader approval workflow, and notifications remain
deferred.

## 8. UI Direction

Implemented through `COMMUNITY-EVENTS.1D-A-FU1`:
- `/activities/` - browse activities visible to the current user (upcoming
  published rows; staff/superuser keep the helper's management bypass), with a
  small signed-up indicator for the current user
- `/activities/<id>/` - detail page with stateful signup/cancel controls
- `/activities/<id>/signup/` - POST-only signup/reactivation action
- `/activities/<id>/cancel-signup/` - POST-only cancellation action
- `/activities/new/` - active-primary members submit an activity for staff
  review or save it as a draft, with a required Activity Scope picker and
  optional scope note
- `/activities/` also links to submission and shows the current creator's own
  draft/submitted activity statuses; drafts use "Draft" / "草稿" and
  "Continue editing" / "继续编辑"

Implemented through `COMMUNITY-EVENTS.1D-B`:
- `/activities/review/` - staff/superuser-only review inbox of pending-review
  and changes-requested submissions
- `/activities/<id>/review/` - staff/superuser-only review detail with
  POST-only publish / request-changes / cancel-reject actions
- `/activities/<id>/edit/` - primary creator or linked co-organizer edit for
  `draft` / `pending_review` / `changes_requested`; only the primary creator
  may change co-organizer links or submit a draft for review
- a staff-dropdown "Activity Review" / "活动审核" link gated by module enablement

Implemented through `COMMUNITY-EVENTS.1G-A`:
- the create/edit form includes an optional authenticated active-user search
  picker for co-organizers
- search requires at least two characters, returns at most 20 users, and
  exposes only user id, display name, username, and active primary membership
  path (or a no-active-group label); it exposes no email, phone, address, or
  sensitive profile fields
- selected users render as removable chips and submit as user ids; server-side
  validation remains authoritative
- activity detail may display linked co-organizer names separately from the
  unchanged organizer display text

Possible future pages:
- `/activities/manage/` - broader staff/leader management view

`COMMUNITY-EVENTS.1B` adds the ordinary "Activities" / "活动" primary-nav entry
(placed after Church Gatherings, before My Serving), gated by module
enablement. The wording, empty state, and detail copy stay low-noise: these are
unofficial community/fellowship activities, not Church Gatherings, and
visibility never implies attendance, signup, or serving.

Future possible user navigation:

English:
- Today
- Reading
- Bible Study
- Prayer
- Activities
- My Serving
- Profile

Chinese:
- 今日
- 读经
- 查经
- 代祷
- 活动
- 我的服事
- 个人资料

This is a future navigation consideration only.

`COMMUNITY-EVENTS.1E-A` contributes only active-signup published visible
activities happening today and creator-owned `changes_requested` reminders to
Today. It does not show later-this-week signups or `pending_review` status,
turn Today into an activity browse page, place signups or visible activities
in the Today serving action center, create My Serving items, or infer serving.

## 9. Non-Goals for V1

No:
- payments
- ticketing
- external public registration
- complex waitlist unless later needed
- reminders
- Google Calendar integration
- transportation coordination
- food signup sheet
- child-care management
- photo sharing
- full event ERP
- automatic scheduling
- ministry assignment checklist
- ServiceEvent replacement
- TeamAssignment or My Serving integration
- serving inferred from signup, audience visibility, or membership
- SpecialEvent model
- fake Combined Ministry record
- forcing CommunityActivity into ServiceEvent
- co-organizer-derived serving or staff authority

## 10. Roadmap Position

`COMMUNITY-EVENTS.1A` completed the independently registered model/admin
foundation and its structure-native visibility rule, with no member-facing
surface.

`COMMUNITY-EVENTS.1B` completes the independent member-facing browse/detail
entrance (`community_activity_list` / `community_activity_detail`) and the
ordinary "Activities" / "活动" primary-nav entry gated by module enablement. It
adds no approval, Today, My Serving, `ServiceEvent` relationship, Staff
Overview, or setup/readiness provider.

`COMMUNITY-EVENTS.1C` completes the minimal `ActivitySignup` lifecycle and
member-facing signup/cancel actions. It keeps one row per activity/user,
reactivates cancelled rows, restricts new signup to visible published upcoming
activities, and adds no serving or shared-surface integration.

`COMMUNITY-EVENTS.1D-A` completes the bounded member submission + admin publish
gate. It adds pending review, a requested-audience note, a one-row-per-user
submission block control, and creator-only pending visibility.

`COMMUNITY-EVENTS.1D-A-FU1` completes member-selected Activity Scope for that
submission flow. It requires at least one active, non-overlapping structure
unit and transactionally creates the selected audience rows. Staff review,
audience adjustment, and publishing remain in Django admin; selected audience
rows do not expose pending activities.

`COMMUNITY-EVENTS.1D-B` completes the lightweight staff review inbox and
request-changes loop. It adds the `changes_requested` status and review
metadata fields, a staff-only inbox and review detail with POST-only
publish/request-changes/cancel actions, the initial creator edit + resubmit
path for `changes_requested` activities, and a module-gated staff-dropdown
review link. `COMMUNITY-EVENTS.1G-A` later extends that edit path to linked
co-organizers without granting review authority.
It adds no Staff Overview counts, Today, My Serving, setup/readiness,
notifications, or `ServiceEvent` link.

`COMMUNITY-EVENTS.1F-A` completes primary-creator editing while an activity is
`pending_review`. A successful save keeps the activity in review and does not
make it visible to selected-scope ordinary users.

`COMMUNITY-EVENTS.1E-A` completes the minimal Today integration. Its
module-owned provider renders active-signup published visible activities
happening today and creator-owned `changes_requested` reminders. The retained
This Week context key stays an empty compatibility default; later-this-week
signups and `pending_review` submissions are not rendered. The module gate
skips the provider and its activity/signup queries when disabled. No serving
context, record, or relationship is added.

`COMMUNITY-EVENTS.1G-A` completes the bounded linked co-organizer edit
permission and active-user search picker. `created_by` remains primary owner;
`organizer` remains display-only. Only the primary creator manages links, and
linked users may edit only pending-review or changes-requested activities. The
slice itself added no draft workflow, capacity/waitlist, staff review
authority, My Serving or serving action-center contribution, notification, or
`ServiceEvent` relationship; `COMMUNITY-EVENTS.1H-A` later extends the same
bounded edit permission to drafts.

`COMMUNITY-EVENTS.1F-B` completes the optional participant limit. Blank/null
means unlimited; a positive integer caps active `signed_up` rows. Creators and
co-organizers edit it only through the existing `pending_review` /
`changes_requested` member edit path, while staff may inspect or edit it in
Django admin. Full activities reject new/reactivated signups without creating
or changing signup state; already-active signup posts remain idempotent.
Capacity affects attendance intent only and creates no serving or
`ServiceEvent` state.

`COMMUNITY-EVENTS.1H-A` completes the bounded member-facing draft workflow.
Eligible creators may save a complete validated draft, keep editing it,
manage its co-organizers, and submit it for review. Linked co-organizers may
view and edit a draft but cannot manage links or submit it. Drafts remain
private to those collaborators and staff/superusers, require Activity Scope,
and create no review-inbox item, signup, Today item, My Serving item, serving
record, or `ServiceEvent` relationship.

Later work still requires separately approved, bounded slices for:

- a larger approval dashboard or leader approval;
- any Staff Overview or setup/readiness contribution;
- any broader Today browse/discovery surface;
- waitlist, attendee list, check-in, reminders, payments, notifications,
  signup deadlines, or calendar behavior.

No later slice may infer serving from activity visibility, signup, or
membership, and no link to `ServiceEvent` is implied by this foundation.

Checklist V1 remains deferred and should not be revived because of Community Activities.

## 11. V1 Manual QA Checklist

Run this checkpoint before inviting a limited trial. Use separate accounts for
the primary creator, a linked co-organizer, an ordinary in-scope member, an
ordinary out-of-scope member, and staff. This checklist documents the required
manual QA; it does not claim that QA has already passed.

### Draft and collaboration

- [ ] As the primary creator, create and save a complete valid `draft`, then
  return later and continue editing it.
- [ ] Add and remove active user-linked co-organizers through the search
  picker; confirm only the primary creator can manage that list.
- [ ] As a linked co-organizer, open and edit the draft details and Activity
  Scope, but confirm there is no way to submit it for review or manage
  co-organizers.
- [ ] As the selected-scope ordinary user, confirm the draft is not visible.

### Review lifecycle

- [ ] As the primary creator, submit the draft for review and confirm it moves
  to `pending_review`.
- [ ] While it is `pending_review`, edit it as the primary creator and confirm
  it remains `pending_review`.
- [ ] As the selected-scope ordinary user, confirm `pending_review` and
  `changes_requested` activities are not visible.
- [ ] As staff, confirm the review inbox shows `pending_review` and
  `changes_requested` activities, but not drafts.
- [ ] Request changes as staff; confirm a non-empty review note is required.
- [ ] As the creator, confirm the `changes_requested` activity and review note
  are visible, edit it, and resubmit it to `pending_review`.
- [ ] Publish as staff.

### Published visibility, signup, and capacity

- [ ] As an in-scope member, confirm the published activity is visible. As an
  out-of-scope member, confirm it is not visible.
- [ ] Sign up, cancel, and sign up again; confirm cancellation retains the row
  and the later signup reactivates it.
- [ ] For an unlimited activity, confirm multiple eligible members can sign up
  without a capacity block.
- [ ] For a limited-capacity activity, fill the final slot and confirm a new
  signup is blocked when full.
- [ ] Cancel an existing signup, confirm that slot becomes available, and
  confirm the cancelled row can be reactivated while capacity is available.
- [ ] Post signup again for an already-active signup and confirm it is
  idempotent: no duplicate row and no erroneous full-capacity failure.

### Shared-surface and product boundaries

- [ ] On Today, confirm Community Activities shows only an active signup for a
  published visible activity happening today and the creator's own
  `changes_requested` reminder. Confirm later activities, cancelled signups,
  unsigned visible activities, drafts, and `pending_review` activities do not
  appear.
- [ ] Confirm My Serving shows no Community Activities item.
- [ ] Confirm the lifecycle creates no `TeamAssignment`,
  `TeamAssignmentMember`, `BibleStudyMeetingRole`, or `ServiceEvent`
  relationship. Activity signup remains attendance intent, not serving.

## 12. V1 Stabilization Boundary

Community Activities V1 is feature-complete enough for a limited trial after
the manual QA checklist above passes. Until trial feedback produces a
separately approved slice, stabilize the implemented lifecycle rather than
adding features.

Do not add a waitlist, attendee list, check-in, notifications, comments,
payments, calendar integration, broader Today browse/discovery, Staff Overview
cards, a setup/readiness provider, a `ServiceEvent` relationship, or My Serving
integration without separate approval.

Community Activities remains a secondary independent module. It is not
official Church Gatherings, not My Serving, not `ServiceEvent`, and not a
serving workflow.
