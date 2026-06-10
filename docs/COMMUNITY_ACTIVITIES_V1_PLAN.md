# Community Activities V1 Plan

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

## 3. Relationship to ServiceEvent

ServiceEvent remains the official church gathering, operations, and ministry assignment anchor.

CommunityActivity is for signup-oriented community and fellowship activities. Do not merge CommunityActivity into ServiceEvent in V1.

An optional future relationship to ServiceEvent may be considered later for large official events, but that link is not part of Community Activities V1.

Do not create a separate SpecialEvent model in V1.

## 4. Possible V1 Models

This section documents a possible future model direction only. Do not implement as part of current pre-pilot work.

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

### CommunityActivityAudience (early concept, superseded)

This legacy-only audience segment model is an early concept and is superseded by the DOCS-AS.1 shared audience-scope direction. Future Community Activities should use a `ChurchStructureUnit`-based audience-scope design through an app-specific join model (for example `CommunityActivityAudienceScope` selecting `ChurchStructureUnit` rows) rather than inventing a separate legacy-only `CommunityActivityAudience` segment system. The fields below are retained only to document the original early concept.

Original early-concept fields (superseded):
- activity
- audience_type:
  - whole_church
  - ministry_context
  - district
  - small_group
- ministry_context nullable
- district nullable
- small_group nullable

Bible Study Schedule audience scope is the first narrow runtime consumer candidate for `ChurchStructureUnit`; ServiceEvent / Church Gatherings and Community Activities should reuse the same foundation later. See `docs/FLEXIBLE_CHURCH_STRUCTURE_AND_AUDIENCE_SCOPE_DESIGN.md`.

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

The simple single `scope_type` model is not enough for real scenarios.

Real scenarios:
- entire EM plus several CM small groups
- EM plus one CM district
- several CM small groups
- whole church
- selected districts
- selected groups across ministries

Expected visibility:
- whole_church: visible to all logged-in church users.
- ministry_context: visible to members in that ministry context, such as EM or CM.
- district: visible to members in that district.
- small_group: visible to members in that small group.

A user can see/signup if any audience segment matches the user:
- whole church
- user's ministry context
- user's district
- user's small group

Examples:

Entire EM + CM Rainbow 1 + CM Rainbow 4:
- audience segment: ministry_context = EM
- audience segment: small_group = Rainbow 1
- audience segment: small_group = Rainbow 4

EM + CM District 1:
- audience segment: ministry_context = EM
- audience segment: district = CM District 1

CM selected small groups:
- audience segment: small_group = Rainbow 1
- audience segment: small_group = Rainbow 4

Whole church:
- audience segment: whole_church

Users outside all matching audience segments should not see the activity or sign up for it.

The UI and queries should avoid exposing private group membership unnecessarily. For example, an activity list should answer "can this user see this activity?" rather than showing internal membership lists.

Future planning may need `MinistryContext` and `District.ministry_context`; see `docs/CHURCH_STRUCTURE_DOMAIN_PLAN.md`.

For longer-term flexible hierarchy and arbitrary audience units, see `docs/CHURCH_STRUCTURE_FOUNDATION_PLAN.md`. Community Activities V1 should not require the flexible tree immediately, but advanced mixed audience segments should wait for or align with that foundation.

## 6. Permission Direction

Keep permissions simple.

Regular member:
- can view published activities within scope
- can sign up or cancel their own signup
- may create an activity only if future policy allows, likely pending approval

Small group leader:
- can create and manage own small-group activity

District leader:
- can create and manage district activity

Staff:
- can create and manage all activities
- can approve, publish, and cancel activities
- can create churchwide activities

Avoid a complex role hierarchy in V1.

## 7. Approval Direction

Broader-scope activities should require approval.

Possible V1 policy:
- single-small-group activity by a small group leader can publish directly
- regular member-created activity goes pending approval
- selected groups, selected districts, ministry-context, and whole-church activities require staff or authorized leader approval

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
- SpecialEvent model
- fake Combined Ministry record
- forcing CommunityActivity into ServiceEvent

## 10. Roadmap Position

Community Activities V1 should be planned as a separate future module after:
- Bible Study V2 direction is resolved
- Lighting Pilot preflight validation is complete
- Church Structure Foundation is planned enough to support mixed CM/EM, district, small-group, and future arbitrary unit audiences

Per DOCS-AS.1, Community Activities audience scope should reuse the shared `ChurchStructureUnit` audience-scope foundation (an app-specific join model selecting `ChurchStructureUnit` rows), following Bible Study Schedule as the first narrow runtime consumer and alongside ServiceEvent / Church Gatherings. It should not introduce a separate legacy-only audience segment system as the final direction.

It should not change the current pre-pilot priority order.

Checklist V1 remains deferred and should not be revived because of Community Activities.
