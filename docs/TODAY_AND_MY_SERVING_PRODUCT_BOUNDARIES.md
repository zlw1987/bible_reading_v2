# Today and My Serving Product Boundaries

Status: TODAY-SERVING.1B / MYSERVING-LEADER.1A product-boundaries note.

This note records product and architecture boundaries for Today, My Serving, Bible Study meeting roles, and future people-status design. It does not approve new models, schema changes, migrations, or serving inference from Church Structure membership.

## Today

Today is the general agenda and lightweight action surface for all signed-in users. It answers: what should I pay attention to today and this week?

Today may show:

- today's reading and check-in state;
- completed reading as a small confirmation state;
- visible church gatherings today and this week;
- visible Bible Study V2 meetings today and this week;
- compact serving notes only when backed by explicit assignment rows.

Today must not become a full serving management workspace. It should link to the owning module for management actions instead of duplicating those workflows.

## My Serving

My Serving is the dedicated serving workspace for coworkers and leaders. It owns personal ministry-team serving assignments, confirmation status, and links into team scheduling or assignment management when the viewer already has the right permission.

The preferred section order is:

1. Needs Attention
2. Today Serving
3. This Week Serving
4. Leader-only Unassigned Ministry Work
5. Later
6. Past / History, collapsed by default in a future UI slice

MYSERVING-AGENDA.1A only approves reorganizing existing personal `TeamAssignmentMember` rows into clearer time sections. BS-SERVING-MYSERVING.1A adds explicit user-linked Bible Study V2 meeting roles to the same My Serving agenda, but only from `BibleStudyMeetingRole.user == request.user`; it does not infer serving from membership, audience visibility, or display names.

BS-SERVING-CONFIRM.1A adds minimal confirmation state to explicit user-linked Bible Study V2 meeting roles in My Serving. It adds confirmed-versus-unconfirmed workflow only; it does not add decline or unavailable workflow, does not infer role ownership from visibility, membership, audience scope, or display names, and does not convert Bible Study roles into `TeamAssignment` rows.

MYSERVING-LEADER.1A adds a leader-only, near-term, read-only Unassigned Ministry Work summary to My Serving. It uses explicit `ServiceEvent.required_teams`, `TeamAssignment`, and `TeamAssignmentMember` coverage data; it is gated by existing team-assignment management permission or teams returned by `manageable_assignment_teams(user)`. It does not create assignments automatically, does not infer serving or management from Church Structure membership, does not add models or migrations, and links back to the existing Team Schedule / Assignment workflows for full scheduling.

## Assignment Boundaries

Visibility is not serving assignment.

- Church event visibility is not a serving assignment.
- Bible Study meeting visibility is not a Bible Study serving role.
- Audience rows are not serving assignment.
- `ChurchStructureMembership` is ordinary care/belonging, not ministry serving.
- `TeamAssignment` / My Serving must not be inferred from `ChurchStructureMembership`.
- Ordinary members can see meetings and gatherings without serving in them.

Only explicit user assignment rows can show as "my serving."

For Bible Study V2 roles, Today may show a compact role note only from `BibleStudyMeetingRole.user == request.user`. Display-name-only rows remain meeting-detail fallback and must not be matched to users by text. Do not infer role ownership from `display_name`, username/full-name matching, membership, small-group belonging, audience visibility, old discussion-leader fields, worship-song lead names, `TeamAssignment`, `TeamMembership`, or `ServiceEvent`.

Bible Study roles are not `TeamAssignment` rows. Their minimal confirmation status is owned by the approved BS-SERVING-CONFIRM.1A workflow and remains separate from `TeamAssignmentMember` confirmation.

## Leader-Only Unassigned Work

Unassigned ministry work must not appear to ordinary members or ordinary coworkers without the correct management permission.

MYSERVING-LEADER.1A reuses the existing ServiceEvent required-team coverage concepts. It shows compact near-term issues for required teams with no assignment, assignments with no assigned people, and assignments with assigned members still awaiting confirmation. Full scheduling remains owned by Team Schedule / Assignment workflows; My Serving only links leaders to those workflows.

## Future People-Status Axes

Future design should keep three axes separate.

Ordinary care/belonging:

- represented today by `ChurchStructureMembership`;
- answers where a person ordinarily belongs for care, visibility, and group-level spiritual life;
- must not imply serving, team membership, staff authority, or leadership responsibility.

Leadership / responsibility scope:

- should be a separate axis from ordinary membership;
- may later need a model such as `ChurchStructureLeadershipAssignment`;
- possible fields: `user`, `structure_unit`, `role_type` such as pastor / lead / backup / district_leader / group_leader / coordinator, `status`, `start_date`, and `end_date`;
- requires a future ADR before implementation.

Church membership / spiritual-administrative status:

- should be a third axis separate from ordinary care/belonging and leadership responsibility;
- possible statuses include visitor, regular_attender, gospel_friend, baptized_believer_not_member, membership_class_completed, faith_statement_signed, official_member, and inactive_member;
- possible serving eligibility levels include none, limited, regular, and leader;
- should be admin-only or staff-visible by authorization scope, not user-editable, and not fully visible to ordinary coworkers;
- ministry team leaders may only need simplified eligibility such as Eligible, Not eligible, or Needs review;
- requires a future ADR before implementation.

No task in this milestone approves `ChurchStructureLeadershipAssignment`, a church membership/profile status model, a schema migration, or a Church Structure source-of-truth change.
