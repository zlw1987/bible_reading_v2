# Community Activities V1 Plan

Status: current plan updated through `COMMUNITY-EVENTS.1C` (July 2026).
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

Approval workflow, creation/management UI, capacity/waitlist, Today, My
Serving, any `ServiceEvent` relationship, Staff Overview, and a setup/readiness
provider remain deferred.

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
- status:
  - draft
  - published
  - cancelled
  - completed
- created_by
- created_at
- updated_at

Capacity, signup deadlines, approval fields, and approval workflow are not
part of `COMMUNITY-EVENTS.1A`.

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
signup reactivates it. Waitlist, notes, capacity enforcement, approval, and
attendance/check-in are not part of `COMMUNITY-EVENTS.1C`.

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

The UI and queries should avoid exposing private membership data. An activity
list should answer "can this user see this activity?" rather than showing
internal membership lists. See `docs/CHURCH_STRUCTURE_FOUNDATION_PLAN.md` for
the canonical hierarchy and belonging foundation.

## 6. Permission Direction

Keep permissions simple.

Regular member:
- can view published activities within scope
- can sign up or cancel their own signup
- may create an activity only if future policy allows, likely pending approval

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

Broader-scope activities should require approval.

Possible V1 policy:
- activity for one narrowly authorized structure unit may publish directly
- regular member-created activity goes pending approval
- multi-unit, broad-subtree, or whole-church/root-row activities require staff
  or explicitly authorized leader approval

## 8. UI Direction

Implemented in `COMMUNITY-EVENTS.1B` and `COMMUNITY-EVENTS.1C`:
- `/activities/` - browse activities visible to the current user (upcoming
  published rows; staff/superuser keep the helper's management bypass), with a
  small signed-up indicator for the current user
- `/activities/<id>/` - detail page with stateful signup/cancel controls
- `/activities/<id>/signup/` - POST-only signup/reactivation action
- `/activities/<id>/cancel-signup/` - POST-only cancellation action

Possible future pages:
- `/activities/new/` - create activity
- `/activities/manage/` - staff/leader management view

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

An approved later Today integration may contribute visible Community Activity
items as ordinary agenda. It must not place signups or visible activities in
the Today serving action center, create My Serving items, or infer serving.

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

Later work still requires separately approved, bounded slices for:

- activity creation/approval workflow and staff management UI;
- any staff-dropdown, Staff Overview, setup/readiness, or Today contribution;
- capacity, waitlist, reminders, payments, or calendar behavior.

No later slice may infer serving from activity visibility, signup, or
membership, and no link to `ServiceEvent` is implied by this foundation.

Checklist V1 remains deferred and should not be revived because of Community Activities.
