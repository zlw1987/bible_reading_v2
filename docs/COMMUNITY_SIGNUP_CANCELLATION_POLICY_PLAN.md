# Community Signup Cancellation Policy Plan

Status: docs-only repository audit and implementation recommendation for
`COMMUNITY-SIGNUP-CANCELLATION-POLICY.0A`. This document does not implement a
runtime change. It records the current Community Activities signup/cancellation
behavior from the repository and recommends the narrow V1 policy to preserve.

## 1. Executive Recommendation

Community Activities should keep the existing persistent signup-row model and
formalize it as the V1 cancellation policy:

- A signed-up member may cancel their own signup immediately, without organizer
  or staff approval.
- Cancellation must retain the `ActivitySignup` row by setting
  `status=cancelled`; it must not hard-delete the row.
- Cancelled rows do not consume capacity, do not appear on Today, and may be
  reactivated by the same member if the activity remains published, visible,
  upcoming, and not full.
- Only one effective active signup may exist per activity/user, enforced by the
  existing `(activity, user)` unique constraint.
- Activity signup/cancellation remains attendance intent only. It must not
  create, mutate, or imply Church Gatherings, `ServiceEvent`, My Serving,
  `TeamAssignment`, `ChurchStructureMembership`, roles, permissions, or
  notifications.

The current code already implements the core of this recommendation in
`ActivitySignup.status`, `community_activity_signup`, and
`community_activity_cancel_signup`. The first implementation slice should be a
hardening slice, not a redesign: make cancellation state eligibility explicit,
wrap cancellation in the same service/transaction discipline as signup, add
focused concurrency/state tests, and update the existing Community Activities
docs to remove ambiguity.

## 2. Current Implementation Map

Primary domain files:

- `community_events/models.py`
  - `CommunityActivity` owns activity details, status, review metadata, creator,
    capacity, timestamps, validation, visibility helpers, signup-open helpers,
    and active signup counts.
  - `CommunityActivityAudienceScope` owns member visibility scope through
    `ChurchStructureUnit` rows.
  - `CommunityActivityCoOrganizer` owns explicit user-linked co-organizer edit
    permission for pre-publication states.
  - `ActivitySignup` owns one signup lifecycle row per activity/user with
    `signed_up` and `cancelled` states.
  - `CommunityActivitySubmissionBlock` blocks member submissions, not signups.
- `community_events/views.py`
  - `community_activity_list` lists visible upcoming activities and annotates
    active signup state/count.
  - `community_activity_detail` displays signup state, capacity, and action
    affordances.
  - `community_activity_signup` creates or reactivates a signup inside
    `transaction.atomic()` and locks the activity row.
  - `community_activity_cancel_signup` bulk-updates the current user's active
    signup to `cancelled`.
  - Review routes publish/request changes/cancel pending submissions only.
- `community_events/urls.py`
  - Registers POST-only signup and cancel-signup member routes.
- `community_events/forms.py`
  - `CommunityActivitySubmissionForm` includes `capacity_limit` for
    create/edit while activities are still pre-publication.
- `community_events/admin.py`
  - Registers Community Activity models; `ActivitySignupAdmin` is read-only and
    denies add/delete.
- `community_events/visibility.py`
  - Defines staff/superuser management override and ordinary member visibility
    through published audience rows plus active primary membership.
- `community_events/today_provider.py`
  - Today includes only visible, published, upcoming activities where the user
    has an active `signed_up` row.
- `community_events/calendar_provider.py`
  - Calendar reads member-visible published activities only. It does not change
    signup or create an activity-owned calendar workflow.
- `core/module_registry.py`
  - Documents Community Activities as independent and non-serving.
- `accounts/context_processors.py`, `templates/base.html`
  - Provide nav highlighting and the staff review link only.
- `templates/community_events/community_activity_list.html`
  - Shows active signup badges and active signup counts.
- `templates/community_events/community_activity_detail.html`
  - Shows signup/cancel/full/unavailable states on published activities.

Focused tests inspected:

- `community_events/tests.py`
  - Foundation, browse/detail, submission, review, creator/co-organizer edit,
    Today, and `ActivitySignupTests`.
- `church_calendar/test_source_providers.py`, `church_calendar/test_ui.py`
  - Calendar provider and UI separation for Community Activity items.
- `core/tests.py`
  - Module registry/nav/Today defaults.
- `announcements/tests.py`
  - Cross-module regression checks that announcement flows do not mutate
    Community Activity rows.

Canonical docs inspected:

- `docs/README.md`
- `docs/COMMUNITY_ACTIVITIES_V1_PLAN.md`
- `docs/MODULE_BOUNDARIES.md`
- `docs/PRODUCT_ARCHITECTURE_AND_ROADMAP.md`
- `docs/TODAY_AND_MY_SERVING_PRODUCT_BOUNDARIES.md`
- `docs/CHURCH_CALENDAR_V1_PLAN.md`
- `docs/NOTIFICATIONS_V0_PLAN.md`
- `docs/STAFF_SETUP_GUIDE.en.md`

## 3. Current Domain Model

`CommunityActivity` fields representing the activity:

- Content/display: `title`, `title_en`, `description`, `description_en`,
  `organizer`, `location`, `location_en`.
- Timing: `start_datetime`, `end_datetime`.
- Capacity: nullable positive `capacity_limit`; `None` means unlimited.
- Lifecycle: `status` with `draft`, `pending_review`, `changes_requested`,
  `published`, `cancelled`, `completed`.
- Review: `requested_audience_note`, `review_note`, `reviewed_by`,
  `reviewed_at`.
- Ownership/audit: nullable `created_by`, `created_at`, `updated_at`.
- Validation: `end_datetime` may not be before `start_datetime`; capacity uses
  `PositiveIntegerField` plus `MinValueValidator(1)`.
- Indexes: `status`, `start_datetime`.

Organizer and co-organizer relationships:

- Public organizer copy is `CommunityActivity.organizer`; it grants no
  permission.
- Accountable creator is `CommunityActivity.created_by`.
- Bounded edit collaborators are `CommunityActivityCoOrganizer` rows with
  `activity`, `user`, `added_by`, `created_at`.
- Co-organizer uniqueness is `(activity, user)`.
- Co-organizer validation rejects inactive users and the primary creator.

Audience/visibility:

- `CommunityActivityAudienceScope.activity` cascades on activity delete.
- `CommunityActivityAudienceScope.structure_unit` is protected.
- `(activity, structure_unit)` is unique.
- Indexes exist on `activity` and `structure_unit`.
- Validation rejects inactive units and ancestor/descendant overlap.

Signup/registration:

- `ActivitySignup.activity` cascades on activity delete.
- `ActivitySignup.user` cascades on user delete.
- `ActivitySignup.status` is `signed_up` or `cancelled`.
- `created_at` and `updated_at` are the only audit timestamps.
- `(activity, user)` is unique, so one lifecycle row exists per activity/user.
- Indexes exist on `(activity, status)` and `(user, status)`.
- There is no cancellation timestamp, cancellation reason, waitlist,
  organizer approval record, attendance/check-in field, or notification field.

Submission review:

- `CommunityActivitySubmissionBlock` can block activity creation by user. It is
  unrelated to signup/cancellation.

Authoritative records:

- Whether a user is signed up: the user's `ActivitySignup` row is active only
  when `status=signed_up`.
- Current participant count: `CommunityActivity.active_signup_count()`, which
  counts only `signed_up` rows.
- Remaining capacity: `capacity_limit - active_signup_count`, clamped to zero;
  unlimited activities return `None`.
- Whether a user can sign up again: signup route reactivates the same cancelled
  row only if the activity is visible, published, upcoming, and not full.
- Organizer-visible participant state: current member-facing organizer surfaces
  show aggregate active counts only. Participant identity/status is available
  to staff through read-only Django admin, not through an organizer participant
  page.

## 4. Current Behavior Matrix

| Scenario | Current behavior |
|---|---|
| View activity list | Authenticated users see upcoming activities returned by `visible_community_activities_for`; staff/superusers see all statuses because of the manager override, then list filtering applies `start_datetime__gte=now`. |
| View activity detail | `CommunityActivity.can_be_seen_by` gates access. Creator and staff/superuser can see more states; ordinary members see only published audience-matching activities. |
| Sign up | POST to `community_activity_signup`; requires visible, published, upcoming activity. Creates `ActivitySignup` or reactivates a cancelled row. |
| Duplicate signup | Existing active row redirects idempotently. The database unique constraint also prevents duplicate activity/user rows. |
| Sign up when full | Full activity returns 404 and creates/reactivates no row. |
| View own signup state | List/detail annotate or fetch the user's active row. Detail shows "You're signed up" and a cancel button. |
| Cancel/withdraw | POST to `community_activity_cancel_signup`; visible active row is updated to `cancelled`. The row is not deleted. |
| Rejoin after cancellation | POST signup reuses the same row and sets `status=signed_up` if capacity is available. |
| Activity cancellation by organizer | No published-activity organizer cancellation route exists. Staff review can cancel/reject only pending-review or changes-requested submissions; admin can edit status directly. |
| Activity edits reducing capacity | Creator/co-organizer edit is pre-publication only, before signups exist. Django admin can set capacity below active count; model validation does not block that. New/reactivated signups are then denied because the activity is full. |
| Waitlist | None. |
| Cancellation request/review | None. Member cancellation is immediate. |
| Organizer participant list | None on member-facing pages; only counts are shown. |

## 5. Authorization Matrix

| Actor | View states | Sign up | See participant identities | Cancel own signup | Cancel another signup | Edit capacity | Cancel activity | Restore activity | Management pages |
|---|---|---|---|---|---|---|---|---|---|
| Ordinary member | Published audience-matching activities only | Yes, if visible/published/upcoming/not full | No | Yes, if detail is visible and row active | No | No | No | No | No |
| Creator | Own activity in any status through `created_by`; published audience matching also applies | Same signup rules as any user | No member-facing participant list | Yes, for own active signup | No | Draft/pending/changes only | No published cancellation route | No | Own create/edit surfaces only |
| Co-organizer | Linked draft/pending/changes activities; published only through ordinary visibility unless staff | Same signup rules as any user | No member-facing participant list | Yes, for own active signup | No | Draft/pending/changes, but cannot change co-organizer list | No | No | No review inbox |
| Staff | `visible_community_activities_for` returns all activities; staff review pages show pending/changes | Only published/upcoming activities; tests cover nonpublished denial even for staff | Django admin can read signup rows; member detail does not list identities | Yes, for own active signup | No app route; admin signup rows are read-only/no delete | Django admin; review UI does not expose capacity editing | Review cancel/reject for pending/changes; admin direct status edit | Admin direct status edit only | Staff review inbox and Django admin |
| Superuser | Same or broader than staff depending admin permissions | Same route rules as staff | Admin | Same as staff | Same as staff | Admin | Admin/review | Admin | Admin/review |

No path found where audience visibility grants organizer authority. Signup does
not grant management rights. Staff visibility bypasses ordinary audience
visibility, but signup itself still requires `published` and upcoming. Community
Activities do not create official-event or serving records in the inspected
runtime paths or tests.

Status-specific visibility:

- `draft`: creator, linked co-organizers, staff/superuser.
- `pending_review`: creator, linked co-organizers, staff/superuser.
- `changes_requested`: creator, linked co-organizers, staff/superuser.
- `published`: ordinary audience-matching members, creator, staff/superuser.
- `cancelled`: creator and staff/superuser; ordinary members do not see it.
- `completed`: creator and staff/superuser; ordinary members do not see it.
- `archived`: no such status currently exists.

## 6. Data Integrity and Concurrency Findings

What is currently strong:

- Duplicate signup is prevented at the application layer by selecting the
  existing row and at the database layer by `unique_activity_signup_user`.
- Signup/reactivation runs inside `transaction.atomic()`.
- Signup locks the `CommunityActivity` row with `select_for_update()` before
  checking capacity, so concurrent final-slot signups serialize on databases
  that support row locks.
- Active count and capacity use only `status=signed_up`; cancelled rows do not
  consume capacity.
- Hard-deleting signup rows would destroy lifecycle history currently preserved
  by `created_at`, `updated_at`, and `status`.
- Activity cancellation/rejection does not mutate signup rows.

Integrity gaps or limits:

- `community_activity_cancel_signup` is not wrapped in `transaction.atomic()`
  and does not lock the activity or signup row. The operation is idempotent, but
  a simultaneous signup/cancel for the same user can be last-write-wins.
- Cancellation currently does not explicitly check `published` or
  `start_datetime > now`. Because detail can show a published past activity,
  an active signup can be cancelled after the start time if the activity remains
  visible.
- There is no explicit participant-history organizer view, so the retained row
  helps audit/storage but is not yet visible outside admin.
- Django admin can reduce `capacity_limit` below active signup count. That does
  not overbook, but it can produce a count greater than the limit and deny new
  signups.
- User deletion cascades signup and co-organizer rows. This avoids orphans but
  loses signup history for deleted users. Inactive users can remain on existing
  signup rows because no model validation rejects them.
- SQLite does not enforce row-level `select_for_update()` the way production
  databases do; no focused concurrent signup test exists.

Race conditions, separate from normal validation:

- Concurrent final-slot signup by different users should serialize through the
  activity row lock on supporting databases; tests do not prove it.
- Concurrent cancellation and another member's signup cannot overbook, but can
  deny a signup that would have fit if cancellation committed first.
- Concurrent cancellation and reactivation by the same user can end in either
  status because cancellation does not lock the same row.

## 7. Existing Tests Summary

Covered:

- Unique signup and duplicate attempts:
  `ActivitySignupTests.test_visible_member_can_sign_up_once` proves repeated
  signup keeps one active row.
- Cancellation and reactivation:
  `test_signed_up_member_can_cancel_and_reactivate_same_row` proves
  cancellation sets `cancelled`, active count drops to zero, and signup
  reuses the same row.
- Capacity:
  `test_signup_is_allowed_below_capacity`,
  `test_signup_is_denied_at_capacity`,
  `test_cancelled_signup_does_not_count_toward_capacity`,
  `test_cancelled_signup_is_not_reactivated_at_capacity`, and detail/list count
  tests cover active-count semantics and UI.
- Approval and visibility:
  Foundation, browse, submission, review, and creator-edit tests cover ordinary
  visibility, zero-audience fail-closed, staff/superuser visibility, pending and
  changes-requested hiding, and staff review decisions.
- Organizer/co-organizer permissions:
  Creator/co-organizer edit tests prove bounded pre-publication edit and no
  review-action access for co-organizers.
- Activity cancellation:
  Review tests cover staff cancel/reject for pending/changes and hidden
  cancelled activities.
- Today integration:
  Today tests prove only active-signup published visible activities render and
  cancelled signups are excluded.
- My Serving and official-event separation:
  Multiple tests assert signup/review/edit flows do not create
  `TeamAssignment`, `TeamAssignmentMember`, `BibleStudyMeetingRole`, or
  `ServiceEvent` rows and do not leak serving context.
- Calendar separation:
  Calendar provider tests prove member-safe visibility and no co-organizer
  bypass in the calendar adapter.

Missing or thin:

- No true concurrent final-slot signup test.
- No concurrent signup/cancel same-user test.
- No explicit test that member cancellation is denied after start time, if that
  becomes the formal policy.
- No organizer/staff participant-history UI tests because no such UI exists.
- No test for admin capacity below active count because admin is currently the
  only published-capacity edit surface.
- No test for inactive-user signup-row retention behavior.

## 8. Documentation Consistency

Consistent current-state claims:

- `docs/COMMUNITY_ACTIVITIES_V1_PLAN.md` correctly records one retained
  activity/user row, `signed_up`/`cancelled`, reactivation, active-only capacity,
  Today active-signup behavior, and non-serving boundaries.
- `docs/MODULE_BOUNDARIES.md` and
  `docs/PRODUCT_ARCHITECTURE_AND_ROADMAP.md` correctly say cancelled rows do not
  count and no waitlist, attendee list, notifications, serving, or
  `ServiceEvent` state is added.
- `docs/TODAY_AND_MY_SERVING_PRODUCT_BOUNDARIES.md`,
  `docs/CHURCH_CALENDAR_V1_PLAN.md`, and `docs/STAFF_SETUP_GUIDE.en.md`
  support the boundaries that Community Activities are independent,
  member-facing attendance intent, not official Church Gatherings or serving.
- `docs/NOTIFICATIONS_V0_PLAN.md` says no notifications runtime is implemented.

Ambiguities/stale wording to clean in a later docs slice:

- `docs/README.md` line items for earlier milestones still say capacity and
  Today were deferred in the `1C` bullet. The later `1E`/`1F` bullets correct
  this, but the paragraph can be read as stale unless the milestone framing is
  clear.
- `docs/README.md` says "calendar integration" remains deferred while the
  Church Calendar adapter already reads Community Activities. The intended
  distinction appears to be "no Community Activity-owned calendar workflow";
  that wording should be clarified.
- Older architecture docs may still refer to `CommunityActivity` as future in
  historical sections. That is acceptable only where the section is clearly
  historical or superseded.

No documentation was edited by this audit except adding this plan to the
canonical docs index.

## 9. Options A-D

### Option A: Hard Delete

Deleting the signup row is simple and makes capacity calculation count all
remaining rows, but it is the wrong fit for the current model:

- Loses audit/history and the original signup timestamp.
- Removes organizer/staff ability to distinguish never-signed-up from
  cancelled.
- Allows re-signup naturally, but only by creating a new row.
- Weakens duplicate protection history because the unique row disappears.
- Is incompatible with the existing docs, tests, admin read-only setup, Today
  active-status filtering, and reactivation behavior.

Do not choose this for V1.

### Option B: Persistent Signup With Status

This is the current implementation and recommended V1 policy:

- Retains audit history through one row per activity/user.
- Active count is explicit: count only `status=signed_up`.
- Re-signup reactivates the same row.
- Existing unique constraint supports one lifecycle row and one effective active
  signup per activity/user.
- UI can remain simple for ordinary members while organizer/admin surfaces can
  later distinguish active and cancelled rows.
- Migration impact is already paid: `ActivitySignup.status` exists.
- Concurrency is manageable with row/activity locks and focused tests.

Choose this for V1.

### Option C: Cancellation Timestamp Only

A nullable timestamp would retain history and keep active-count logic possible,
but it is weaker than the current status lifecycle:

- It duplicates the already implemented `status=cancelled` concept.
- It makes future states like waitlisted/no-show harder or inconsistent.
- It does not materially improve capacity or re-signup semantics.
- It would require an extra migration and code churn for little V1 value.

Do not add this for V1. A future `cancelled_at` may be useful only if exact
cancellation-time audit becomes a separately approved need.

### Option D: Cancellation Request/Review Lifecycle

Organizer or staff approval for cancellation is too heavy for Community
Activities V1:

- It creates staff workflow for unofficial member-organized activities.
- It delays capacity release and makes full-activity behavior noisier.
- It implies an operational seriousness closer to official events or serving.
- No current model, route, or notification runtime supports this lifecycle.

Do not choose this for ordinary V1 member cancellation.

## 10. Recommended V1 Policy

Who may cancel:

- The signed-up member may cancel their own active signup.
- Organizer/co-organizer may cancel only their own signup, not another member's,
  in V1.
- Staff should not receive a new member-facing cancel-another-signup route in
  the first slice. Django admin remains read-only for `ActivitySignup`.
- Activity-level cancellation should set the activity status only; it should not
  rewrite or delete signup rows.

Eligible states:

- Signup row must exist for the current user and be `signed_up`.
- Activity should be `published`.
- Recommended hardening: self-cancellation should be allowed only before
  `start_datetime`. After the start time, retain the row as historical
  attendance intent unless a later approved attendance/check-in policy changes
  this.
- Cancelled, completed, draft, pending-review, and changes-requested activities
  should not accept member signup changes.

Immediate or reviewed:

- Immediate self-service update. No organizer/staff approval.

History:

- Retain the signup row.
- Keep `created_at` as original signup creation and `updated_at` as latest
  status transition timestamp.
- Do not add cancellation reason in V1.

Re-signup:

- A member may re-sign up after cancellation if the activity is still eligible
  and has remaining capacity.
- Reactivation updates the existing row back to `signed_up`.

Uniqueness:

- Keep `(activity, user)` unique.
- Do not switch to partial unique constraints for active rows in V1 because one
  lifecycle row is simpler and already implemented.

Capacity:

- Count only active `signed_up` rows.
- Cancelled rows do not consume capacity.
- Signup/reactivation must check capacity in the same transaction that changes
  the row.

Concurrency:

- Keep signup serialized on the activity row.
- Move cancellation into the same explicit transactional service boundary and
  lock the signup row when it exists.
- Add focused tests for idempotent cancellation, reactivation at capacity, and
  concurrent final-slot behavior where the test backend can support it.

Organizer view:

- Current V1 may keep showing aggregate active counts only.
- If a participant view is added, authorized organizer/staff views should
  distinguish active and cancelled rows. Ordinary members should not see
  cancellation history.

Ordinary member view:

- Active signup: show "You're signed up" and cancel action while cancellation
  is eligible.
- Cancelled/no signup: show signup action only if activity is published,
  visible, upcoming, and not full.
- Full: show full message and no signup action, unless the viewer is already
  actively signed up.
- Past/cancelled activity: show no signup-changing action.

Notifications:

- Produce no notifications in the first implementation slice.
- Do not add email, SMS, push, scheduler, broadcast delivery, or a notification
  producer. The current Notifications V0 plan is planning-only.

## 11. State-Transition Rules

Signup row transitions:

| From | Trigger | To | Notes |
|---|---|---|---|
| None | Eligible member signs up | `signed_up` | Create row if activity visible, published, upcoming, and not full. |
| `signed_up` | Same user signs up again | `signed_up` | Idempotent redirect; no duplicate row. |
| `signed_up` | Eligible self-cancellation | `cancelled` | Immediate, retained row, no approval. |
| `cancelled` | Eligible member signs up again | `signed_up` | Reactivate same row if capacity remains. |
| `cancelled` | Same user cancels again | `cancelled` | Idempotent no-op if route remains reachable. |

Activity state effects:

- `draft`, `pending_review`, `changes_requested`: no signup or cancellation
  changes for ordinary members.
- `published`: signup/cancellation lifecycle applies while upcoming and visible.
- `cancelled`: no signup/cancellation changes; existing signup rows retained.
- `completed`: no signup/cancellation changes; existing signup rows retained.
- `archived`: no current status.

## 12. Capacity and Uniqueness Rules

- Unlimited activity: `capacity_limit=None`; signup allowed unless blocked by
  status/time/visibility.
- Limited activity: `capacity_limit > 0`.
- Active count: count `ActivitySignup` rows with `status=signed_up`.
- Remaining capacity: `max(capacity_limit - active_count, 0)`.
- Full activity: deny new or cancelled-row reactivation; keep existing active
  signup idempotent.
- Admin capacity below current active count: treat as over-capacity closed state;
  deny new/reactivated signups. A future management UI should prevent or warn
  on this, but the member cancellation slice need not add that UI.
- Unique signup: preserve the existing unique activity/user lifecycle row.

## 13. UI Behavior

Current member-facing UI:

- List: shows visible upcoming activities, active signup badge, and active
  signed-up counts.
- Detail: shows active count, full state, signup action, cancel action for
  active signup, or unavailable message.
- No attendee list or cancellation history is exposed to ordinary members.
- Co-organizer names are displayed as collaborators, not participant state.

Recommended first-slice UI hardening:

- Hide or disable the cancel button after start time if the formal policy
  freezes past signup state.
- Keep ordinary copy operational and non-sensitive.
- Do not expose model names, IDs, source-of-truth wording, or cancellation
  history to ordinary users.

## 14. Cross-Module Boundaries

Cancellation should have no effect on:

- Today, except cancelled signups no longer qualify for Community Activity
  Today cards because Today filters active `signed_up` rows.
- Calendar, except the member can still see published visible activities through
  the read-only adapter. The calendar never changes signup.
- Official Church Gatherings and `ServiceEvent`.
- My Serving.
- `TeamAssignment` or `TeamAssignmentMember`.
- `ChurchStructureMembership`.
- Bible Study roles.
- Staff permissions, co-organizer permission, or member authority.
- Notifications, because no notification runtime or producer should be added.

Repository evidence supports the no-effect boundary through `today_provider`,
`calendar_provider`, `core/module_registry.py`, `MODULE_BOUNDARIES.md`, and the
focused no-serving/no-ServiceEvent tests.

## 15. Failure Modes and Privacy

- Duplicate signup: handled by app logic and database uniqueness.
- Full activity: deny new/reactivated signup; preserve existing active signup.
- Already cancelled signup: cancellation is a no-op; signup may reactivate only
  if eligible.
- Activity already cancelled: no ordinary signup/cancellation changes; retained
  signup rows become history.
- Start time passed: recommended policy should freeze self-service signup state
  to avoid post-event history rewrites.
- Inactive user: existing rows can remain; new login-based actions are naturally
  unavailable to users who cannot authenticate. User deletion currently cascades
  rows and loses history.
- Concurrent signup/cancel: formal service should lock consistently and tests
  should document accepted outcomes.
- Privacy: ordinary member pages should show only their own signup state and
  aggregate active counts. Cancelled-history visibility belongs only on future
  authorized management/admin surfaces.

## 16. Focused Test Plan

Model/query tests:

- Active count ignores `cancelled` rows.
- Remaining capacity and full state use active rows only.
- Unique activity/user row remains enforced.

View/service tests:

- Member can cancel own active signup and row is retained.
- Cancelled member can rejoin if published/upcoming/visible/not full.
- Cancelled member cannot rejoin when full.
- Duplicate signup remains idempotent.
- Cancellation is idempotent for already-cancelled rows.
- Cancellation denied or unavailable for draft, pending-review,
  changes-requested, cancelled, completed, and past activities if the policy
  freezes after start time.
- Signup and cancellation create no `ServiceEvent`, `TeamAssignment`,
  `TeamAssignmentMember`, `BibleStudyMeetingRole`, Today serving action, My
  Serving item, or notification row.

Concurrency tests:

- Final-slot concurrent signups do not overbook on the supported database.
- Concurrent cancel/reactivate for the same user has documented lock ordering
  and deterministic final behavior, or an explicitly accepted last-write-wins
  rule.

UI tests:

- Detail shows cancel action only for active eligible signup.
- Full activity hides signup for non-signed-up users but preserves active signed
  up state for existing participants.
- Ordinary member does not see cancellation history or participant identities.

Docs/tests:

- Update Community Activities docs to say cancellation status is the policy, not
  just an implementation detail.
- Update README wording around calendar adapter versus activity-owned calendar
  workflow.

## 17. Risk-Ordered Implementation Slices

### Slice 1: Policy hardening for existing signup lifecycle

Goal: formalize and harden the already implemented persistent-status policy.

Likely files:

- `community_events/views.py` or a new narrow `community_events/services.py`
- `community_events/tests.py`
- `templates/community_events/community_activity_detail.html`
- `docs/COMMUNITY_ACTIVITIES_V1_PLAN.md`
- `docs/README.md`

Work:

- Centralize signup/cancellation state checks.
- Make cancellation transactional and row-locking.
- Decide and enforce pre-start-only self-cancellation.
- Preserve current status-row reactivation behavior.
- Add focused tests listed above.
- Update docs only for the implemented policy.

No migration should be needed unless a separately approved audit timestamp is
added later.

### Slice 2: Organizer/staff participant-state presentation

Goal: if organizers need operational visibility, add a bounded authorized view
that distinguishes active and cancelled rows without exposing history to
ordinary members.

Defer until there is a concrete organizer workflow. This is not needed to make
member self-cancellation safe.

### Slice 3: Optional audit timestamp

Goal: add `cancelled_at` only if exact cancellation-time audit is required.

This would require a migration and backfill/default semantics. It should not be
part of the first slice.

## 18. Explicit Deferred Features

- Waitlists.
- Cancellation reasons.
- Organizer approval of cancellation.
- Organizer messaging.
- Notification producers.
- Email, SMS, push, scheduler, or broadcast delivery.
- Reminders.
- Attendance/check-in.
- Refunds or payments.
- Recurring activities.
- Analytics.
- Bulk organizer actions.
- Automated archival.
- Official Church Gathering or `ServiceEvent` linkage.
- My Serving or `TeamAssignment` integration.
- `ChurchStructureMembership` mutation.

## 19. Open Questions

- Should self-service cancellation be frozen exactly at `start_datetime`, or
  should there be a configurable cutoff? Repository evidence supports freezing
  after start for audit clarity, but no current product doc explicitly states
  the cutoff.
- Should deleted users preserve anonymized signup history instead of cascading
  deletion? Current model cascades; changing that is a separate retention policy
  decision, not required for V1 member cancellation.
