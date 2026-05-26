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

## 3. Relationship to ServiceEvent

ServiceEvent remains the official church gathering, operations, and ministry assignment anchor.

CommunityActivity is for signup-oriented community and fellowship activities. Do not merge CommunityActivity into ServiceEvent in V1.

An optional future relationship to ServiceEvent may be considered later for large official events, but that link is not part of Community Activities V1.

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
- scope_type:
  - own_group
  - selected_groups
  - selected_districts
  - churchwide
- small_groups M2M
- districts M2M
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

Expected visibility:
- own_group: visible to the creator's own small group.
- selected_groups: visible to selected small groups.
- selected_districts: visible to members in selected districts.
- churchwide: visible to all logged-in church users.

Users outside the activity scope should not see the activity or sign up for it.

The UI and queries should avoid exposing private group membership unnecessarily. For example, an activity list should answer "can this user see this activity?" rather than showing internal membership lists.

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
- own_group activity by a small group leader can publish directly
- regular member-created activity goes pending approval
- selected_groups, selected_districts, and churchwide activities require staff or authorized leader approval

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

## 10. Roadmap Position

Community Activities V1 should be planned as a separate future module after:
- Bible Study V2 direction is resolved
- Lighting Pilot preflight validation is complete

It should not change the current pre-pilot priority order.

Checklist V1 remains deferred and should not be revived because of Community Activities.
