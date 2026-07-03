# Community Activities V1 Plan

Status: current planning/readiness document as of
`COMMUNITY-EVENTS-READINESS.0A` (July 2026). The Church Structure migration and
modular CMS foundation through `MODULAR-CORE.6B` are complete enough for
Community Events/Activities to be considered as a separately approved next
implementation. This docs-only checkpoint does not approve or implement the
module; names, routes, permissions, models, migrations, and delivery slices
still require explicit approval.

## 1. Purpose

Community Activities is a future module for member/community/fellowship activities with signup.

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

## 4. Possible V1 Models

This section documents a possible future model direction only. It is not
implementation approval.

### CommunityActivity

Suggested fields:
- title
- title_en
- description
- description_en
- organizer
- start_datetime
- end_datetime
- location
- location_en
- capacity optional
- signup_deadline optional
- status:
  - draft
  - pending_approval
  - published
  - cancelled
  - completed
- requires_approval
- created_by
- approved_by
- approved_at

### CommunityActivityAudienceScope

The final implementation direction is an app-specific audience join model,
following the current structure-native pattern rather than any legacy
`scope_type`, `MinistryContext`, `District`, or `SmallGroup` fields.

Suggested fields:

- `activity`: FK to `CommunityActivity`;
- `structure_unit`: FK to `ChurchStructureUnit`;
- normal audit/timestamp fields only if the approved implementation needs
  them.

Each row selects one `ChurchStructureUnit`. Multiple rows express a union of
selected structure subtrees. The implementation must not recreate legacy
audience-segment tables or depend on retired legacy structure models.

ServiceEvent and Bible Study V2 already use app-specific structure audience
rows. Community Activities should reuse the same architectural pattern while
owning its own model and visibility query; it is not implemented now. See
`docs/FLEXIBLE_CHURCH_STRUCTURE_AND_AUDIENCE_SCOPE_DESIGN.md`.

### ActivitySignup

Suggested fields:
- activity
- user
- status:
  - signed_up
  - cancelled
  - waitlisted optional/future
- note optional
- created_at
- updated_at

## 5. Scope and Visibility Rules

Ordinary-user visibility should be structure-native:

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
sign up for it. Staff/manager bypass behavior, if any, must be specified in the
approved implementation rather than inferred here.

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

Avoid a complex role hierarchy in V1.

## 7. Approval Direction

Broader-scope activities should require approval.

Possible V1 policy:
- activity for one narrowly authorized structure unit may publish directly
- regular member-created activity goes pending approval
- multi-unit, broad-subtree, or whole-church/root-row activities require staff
  or explicitly authorized leader approval

## 8. UI Direction

Possible future pages:
- `/activities/` - list activities visible to the current user
- `/activities/<id>/` - detail page with signup/cancel
- `/activities/new/` - create activity
- `/activities/manage/` - staff/leader management view

Do not add Activities to the top navigation yet.

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

The prerequisites named by the earlier plan are now satisfied: Bible Study V2
is the active path, Church Structure is canonical and structure-native, and
the modular CMS foundation is implemented through `MODULAR-CORE.6B`.
Community Events/Activities may therefore be proposed as a separate next
module.

Implementation still requires a separately approved, bounded slice covering at
least:

- the final product/module name and registry key;
- registry capabilities and any declared dependencies;
- models and migrations, including an app-specific
  `CommunityActivityAudienceScope` selecting `ChurchStructureUnit`;
- active-primary-membership descendant matching and zero-row fail-closed
  coverage;
- permissions, signup lifecycle, staff surfaces, and bilingual copy;
- any primary-nav, staff-dropdown, Staff Overview, setup/readiness, or Today
  provider contributions;
- explicit regression tests proving that visibility/signup/belonging do not
  create serving or My Serving items.

`COMMUNITY-EVENTS-READINESS.0A` changes documentation only. Community
Events/Activities is not implemented, registered, migrated, or enabled by this
checkpoint.

Checklist V1 remains deferred and should not be revived because of Community Activities.
