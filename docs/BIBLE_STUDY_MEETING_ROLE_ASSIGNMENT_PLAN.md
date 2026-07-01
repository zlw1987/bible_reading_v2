# Bible Study Meeting Role Assignment Plan

Status: BS-ROLE.1A docs-only planning complete; BS-ROLE.1B management form/UI polish complete; TODAY-HOME.1D linked Bible Study role chips on Today complete; Bible Study role confirmation in My Serving and MY-SERVING-BS.1B pending-role integration into the Today action center complete. UNIT-COWORKER-BS-CANDIDATE.1E makes discussion-leader and worship-lead user pickers prefer active Edify/Worship coworkers from the meeting `anchor_unit`, falling back to all active anchor-unit coworkers and then to the existing audience-membership picker when setup is missing.

Scope: make small-group `BibleStudyMeetingRole` assignment reliable enough for Today-page surfacing, My Serving confirmation, and clearer Friday Bible Study preparation UX. BS-ROLE.1B, TODAY-HOME.1D, and My Serving Bible Study role confirmation are now complete; this plan still does not approve any further code, schema, migration, permission, notification, or workflow expansion.

## 1. Current-State Audit

### Models and Fields

`BibleStudyMeeting`

- Anchors one small-group Friday meeting to a `BibleStudyLesson`, `anchor_unit`, `generation_key`, and meeting audience rows.
- Key fields: `lesson`, `anchor_unit`, `generation_key`, `meeting_kind`, `meeting_datetime`, `location`, `location_en`, `meeting_link`, `group_direction`, `group_direction_en`, `group_questions`, `group_questions_en`, `status`, optional `service_event`, and audit fields.
- Still has older discussion-leader fields: `discussion_leader_user` and `discussion_leader_name`.
- Current visibility is `BibleStudyMeeting.can_be_seen_by(user)`: staff/superuser/Bible Study managers can see all; ordinary users can see published meetings when the parent lesson and schedule are published and their single active primary `ChurchStructureMembership` matches a `BibleStudyMeetingAudienceScope` row (the selected unit or a descendant). Since BS-STRUCT.2A, zero-row V2 meetings fail closed for ordinary users. `BibleStudyMeeting.small_group` was removed in BS-MEETING-MIRROR.1A, and `Profile.small_group` alone no longer grants v2 `BibleStudyMeeting` visibility.

`BibleStudyMeetingRole`

- Represents one per-meeting responsibility.
- Role choices: `discussion_leader`, `worship_lead`, `pianist`, `support`, `host`.
- Key fields: `meeting`, `role`, nullable `user`, free-text `display_name`, `notes`, `notes_en`, `confirmed_at`, `confirmation_note`, timestamps.
- `get_display_name()` prefers `display_name`, then falls back to the linked user's full name or username, then blank.
- `confirm(note="")` records `confirmed_at` and an optional `confirmation_note`; there is no separate accepted/declined state.
- There is no model-level requirement that either `user` or `display_name` be present; BS-ROLE.1B enforces the nonblank assignee requirement at the form layer.

`BibleStudyMeetingWorshipSong`

- Represents one worship-set item for a meeting.
- Key fields: `meeting`, `sort_order`, `title`, `title_en`, `song_key`, links, arrangement notes, nullable `worship_lead_user`, free-text `worship_lead_name`, support notes, timestamps.
- This model has a similar identity pattern for worship lead, but Today role chips should use `BibleStudyMeetingRole`, not infer from song lead names.

### Where Roles Are Created or Edited

- `BibleStudyMeetingRoleForm` exposes `role`, `user`, `display_name`, `notes`, and `notes_en`.
- BS-ROLE.1B originally limited the `user` queryset to active users whose `profile.small_group` matched the meeting's small group, plus the already-selected user when editing.
- Since CS-CORE.3B and BS-STRUCT.2A, `BibleStudyMeetingWorshipSongForm` user pickers use membership-core matching against the meeting's `BibleStudyMeetingAudienceScope` rows, while preserving the currently saved user on edit. Zero-row meetings return no ordinary candidates.
- Since UNIT-COWORKER-BS-CANDIDATE.1E, `BibleStudyMeetingRoleForm` keeps that audience-membership picker as the fallback, but discussion-leader candidates first use active `edify` coworkers on the meeting `anchor_unit`, worship-lead candidates first use active `worship` coworkers on the `anchor_unit`, and role-specific setup gaps fall back to all active coworkers on that anchor unit. Display-name-only roles remain display fallback only and are not candidate assignments.
- The placeholder/help text frames `display_name` as a fallback when no user is selected, and BS-ROLE.1B form validation requires either a linked `user` or non-empty `display_name`.
- Staff/authorized users create roles through `manage_bible_study_meeting_roles`.
- Staff/authorized users edit roles through `edit_bible_study_meeting_role`.
- Staff/authorized users delete roles through `delete_bible_study_meeting_role`.
- Meeting creation/editing uses `BibleStudyMeetingForm`, while group preparation uses `BibleStudyMeetingPreparationForm`; neither currently manages role rows inline.

### Where Roles and Worship Songs Are Displayed

- Meeting detail (`bible_study_meeting_detail.html`) displays all meeting roles visible with the meeting, including role label, display name, and notes.
- Role management (`manage_bible_study_meeting_roles.html`) displays existing roles and the add-role form.
- Worship management (`manage_bible_study_meeting_worship_songs.html`) shows meeting context, existing worship songs, and current meeting roles for reference.
- Template filters localize role labels and use `role.get_display_name()` for the visible person name.
- Meeting detail can continue to show free-text fallback names because it is a meeting-preparation surface, not a personalized "my role" identity surface.
- My Serving lists linked-user Bible Study meeting roles and owns their confirmation action.

### Current Permission Boundary

- Bible Study meeting management is controlled by `can_manage_bible_studies(user)`.
- Current managers are staff, superusers, users with `CAP_MANAGE_BIBLE_STUDIES`, or users with `CAP_PUBLISH_BIBLE_STUDY_GUIDES`.
- Ordinary users can view their own published small-group meeting according to existing meeting visibility, but cannot manage roles or worship songs.
- `can_edit_bible_study_meeting_preparation()` currently delegates to full Bible Study management.

### Current Limitations for "My Role" Detection

- A role row with `user == request.user` is reliable.
- A role row with only `display_name` is not reliable for identity; multiple people can share names, names can be entered inconsistently, and display names are not account identities.
- A role row with both `user` and `display_name` is identity-reliable through `user`, but display may currently prefer the manual `display_name`.
- Blank `user` plus blank `display_name` is still possible only below the form layer; BS-ROLE.1B rejects it in the management form and it is not useful for Today surfacing.
- The older `BibleStudyMeeting.discussion_leader_user/name` fields duplicate part of the role concept and should not be used for new Today role-chip identity logic.

### Current Test Coverage Observed

Existing tests cover:

- Role form filtering to the meeting audience rows; after BS-STRUCT.2A this means membership-core matching for `BibleStudyMeetingAudienceScope` rows, not the legacy `small_group` mirror and not `Profile.small_group` alone.
- Staff access to role management.
- Ordinary-user denial for role management/edit/delete.
- Staff add/edit/delete for roles.
- Meeting detail role display for a visible own-group user.
- Meeting detail hiding roles when the parent meeting is not visible.
- Manager-only role controls on meeting detail.
- Chinese role labels.
- Worship-management context and worship-song form user filtering.
- Model validation for allowed/invalid role choices.

Pre-TODAY-HOME.1D coverage gaps now addressed by Claude's reported tests:

- Today role-chip tests now cover linked-user-only surfacing.
- Today role-chip tests now distinguish linked-user roles from display-name-only roles.
- No test asserts blank-assignee role rows are prevented or ignored.
- TODAY-HOME.1D covered personalized Today identity behavior for linked-user roles; broader display behavior remains owned by meeting-detail/form tests.

## 2. Product Goal

Make Friday small-group Bible Study responsibilities clear to the right people while keeping the workflow lightweight for small groups.

The desired direction is:

- Staff or authorized Bible Study managers can record who is responsible for discussion leading, worship leading, piano, support, or hosting.
- Ordinary users can see meeting preparation details according to the current small-group visibility rules.
- Today can show "your Bible Study role this week" only when the role row is reliably linked to the signed-in user.
- My Serving can show and confirm linked-user Bible Study meeting roles.
- Small groups can still record guest or one-off names when no account exists.

## 3. Recommended Design Direction

- Prefer linking roles to real `User` records whenever the responsible person has an active membership-core match for the meeting's audience rows.
- Keep `display_name` only as a fallback for people without accounts, guest names, or one-off cases.
- Do not infer identity by matching `display_name` to a user's full name, username, preferred name, profile field, or translated display text.
- For Today role chips, use only `BibleStudyMeetingRole.objects.filter(user=request.user, ...)` after applying the existing meeting visibility/date/status rules.
- If both `user` and `display_name` are present, treat `user` as the identity contract. Display can remain a separate UX decision, but Today identity must not depend on the manual name.
- Keep `BibleStudyMeetingRole` separate from `TeamAssignment`; Friday Bible Study meeting responsibilities are not Ministry Operations serving assignments.
- Keep ordinary-user visibility based on `BibleStudyMeeting.can_be_seen_by()`; since BS-STRUCT.2A, current v2 meeting visibility uses `BibleStudyMeetingAudienceScope` rows plus active primary `ChurchStructureMembership`, zero-row meetings fail closed for ordinary users, and neither `Profile.small_group` nor the legacy `BibleStudyMeeting.small_group` mirror grants ordinary access.
- Role work targets the v2 stack only. Per CS-CORE.3C and later BS-V1-SCHEMA-RETIRE.1A (`docs/LEGACY_BIBLE_STUDY_SESSION_RETIREMENT_DECISION.md`), Bible Study V2 is the active product path and legacy V1 `BibleStudySession` schema is removed; do not extend role assignment to V1 sessions.

## 4. Confirmation Decision

Current decision: Bible Study role confirmation is implemented in My Serving.

Implemented behavior:

- Managers record the role on the V2 meeting.
- The linked user can see the responsibility on meeting detail, on Today as
  read-only agenda context and a pending action-center item when unconfirmed,
  and in My Serving as serving work.
- My Serving confirms linked-user `BibleStudyMeetingRole` rows by setting `confirmed_at` and optional `confirmation_note`.
- There is no separate declined state, swap request, reminder, availability, automation, or conversion into `TeamAssignment`.

Boundary:

- Today remains a general dashboard and does not render the confirmation form.
- My Serving is the serving workspace for the confirm action.
- Bible Study meeting audience visibility or `ChurchStructureMembership` belonging does not imply a Bible Study serving role; only explicit `BibleStudyMeetingRole.user` rows drive My Serving Bible Study role confirmation.

## 5. Implementation Milestone Split

### BS-ROLE.1B - Management UI Polish

Status: complete.

Goal: encourage reliable user linking where possible while preserving a fallback path.

Completed scope:

- Clarify `BibleStudyMeetingRoleForm` help text so managers choose a user when the person has an account.
- Require at least one assignee signal: linked `user` or `display_name`.
- Warn/help managers that a display-name-only role can show on meeting detail but cannot appear as "my role" on Today.
- BS-ROLE.1B kept the `user` queryset limited to active users in the meeting small group, with the existing selected-user exception on edit; CS-CORE.3B and BS-STRUCT.2A later changed the role and worship user pickers to use membership-core matching for the meeting audience rows, preserving that saved-user exception.
- Keep role management restricted to current Bible Study managers.

Likely affected files later:

- `studies/forms.py`
- `templates/studies/manage_bible_study_meeting_roles.html`
- `templates/studies/bible_study_meeting_role_form.html`
- `studies/tests.py`

Schema result: BS-ROLE.1B itself added no schema change. Later migration `studies/0013_biblestudymeetingrole_confirmation_note_and_more` added `confirmed_at` and `confirmation_note` for My Serving confirmation. A future schema change would be necessary only if product requires database-level nonblank assignee enforcement, declined/swap status, richer audit history, or broader role assignment metadata.

### BS-ROLE.1C - Meeting Detail Display Cleanup

Goal: make role display clear without changing visibility.

Likely work:

- Preserve current meeting detail visibility rules.
- Display linked-user roles and display-name fallback roles naturally.
- Avoid exposing internal identity/source-of-truth language to ordinary users.
- Optionally de-emphasize or remove use of older meeting-level discussion-leader fields from visible preparation surfaces if they conflict with `BibleStudyMeetingRole`.

Likely affected files later:

- `templates/studies/bible_study_meeting_detail.html`
- `studies/templatetags/study_extras.py`
- `studies/tests.py`

### TODAY-HOME.1D - Today Role Chips

Status: complete.

Goal: show Today-page Bible Study role chips only when role identity is reliable.

Completed scope:

- Use the already-visible `primary_meeting` from the existing v2 Bible Study meeting context.
- Query role rows where `role.user == request.user`.
- Ignore display-name-only roles for personalized chips.
- Keep Today lightweight: show a concise chip/list and link to meeting detail, not a role management workflow.

Likely affected files later:

Completed boundaries:

- No identity inference from `display_name`, username/full-name matching, old discussion-leader names, worship-song lead names, `TeamAssignment`, `TeamMembership`, or `ServiceEvent`.
- No role confirmation form on Today, and no accept/decline/reminder/notification workflow.
- No schema/migration/URL/runtime-visibility change from the role-chip slice itself.
- No additional visibility source beyond the already-visible `BibleStudyMeeting.can_be_seen_by()` result.

### Historical Confirmation Milestone

Superseded: basic Bible Study role confirmation is now implemented in My Serving through `confirmed_at` and `confirmation_note`. Future work should be framed as enhancements beyond basic confirmation, not as first-time confirmation.

Potential scope:

- Decline/swap status.
- Who can decline, swap, or override.
- How declined roles are reassigned.
- Whether notifications/reminders are needed.
- Audit/history expectations.

These enhancements should remain separate from BS-ROLE.1B/1C, Today role-chip surfacing, and the completed My Serving confirmation workflow.

## 6. Data and Visibility Contract

- Ordinary users see only their own visible small-group Bible Study meeting according to current meeting visibility rules.
- Today role chips show only roles linked to the signed-in user through `BibleStudyMeetingRole.user`.
- Today must not show another person's role for the user's group unless the product explicitly designs a group-wide preparation summary.
- Meeting detail can continue showing the existing role list according to the current meeting visibility rules.
- Display-name-only roles may appear on meeting detail but must not be treated as "my role."
- Staff/admin users keep current management access; no new staff/admin leakage is introduced.
- Bible Study roles and Today role chips must not add a separate visibility rule; they use the already-visible meeting selected by `BibleStudyMeeting.can_be_seen_by()`.
- Do not infer Bible Study role ownership from `TeamAssignment`, `TeamMembership`, `ServiceEvent`, `MinistryTeam`, old `discussion_leader_name`, worship song free-text names, or display-name matching.

## 7. Non-Goals

- No broad Bible Study rewrite.
- No attendance.
- No notification/reminder system.
- No Community Activities.
- No automatic role assignment.
- No Today-owned role confirmation workflow.
- No swap requests, availability, checklist engine, or automation.
- No role-slice migration or expansion of Bible Study meeting visibility beyond the separately completed CS-CORE.2C-B source switch.
- No conversion of `BibleStudyMeetingRole` into `TeamAssignment`.
- No ServiceEvent or My Serving behavior changes.

## 8. Recommended First Implementation Slice

Recommended first slice: BS-ROLE.1B. Completed without schema changes.

Make the existing role management workflow safer and clearer:

- Add form-level validation requiring either `user` or `display_name`.
- Add manager-facing help text explaining that linked users are required for Today "my role" surfacing, while display names are fallback-only.
- Preserve the group-limited user picker. Historical note: BS-ROLE.1B used profile-based meeting-small-group filtering; since CS-CORE.3B / BS-STRUCT.2A the role and worship pickers use membership-core matching for the meeting audience rows.
- Preserve current meeting detail display and permissions.
- Historical note: BS-ROLE.1B did not add confirmation/status fields; later My Serving role-confirmation work added `confirmed_at` and `confirmation_note`.
- BS-ROLE.1B itself did not change Today.

This gave TODAY-HOME.1D a cleaner data contract without changing runtime visibility or creating a heavier workflow. BS-ROLE.1B did not change Today/Home files; TODAY-HOME.1D later completed the read-only Today surfacing separately.

## 9. Regression Coverage and Future Tests

Completed BS-ROLE.1B coverage:

- Linked-user role saves and displays.
- Display-name fallback role saves and displays.
- Blank `user` plus blank `display_name` is rejected by the form.
- User picker remains limited to the meeting audience, while preserving the currently selected user on edit; since CS-CORE.3B / BS-STRUCT.2A, role and worship user pickers enforce this through membership-core matching.
- Ordinary users still cannot manage roles.

Completed TODAY-HOME.1D coverage:

- Today shows role chips only for roles with `role.user == request.user`.
- Today ignores display-name-only roles even when the name matches the signed-in user.
- Today hides other users' and other groups' roles.
- Today hides roles when the meeting is not visible.
- Chinese role label rendering is covered.
- Today does not expose role-management controls.
- Today does not render a role confirmation form; My Serving owns confirmation.

Completed MY-SERVING-BS.1B coverage:

- Today counts a pending linked-user Bible Study meeting as one serving item,
  including when that user holds multiple roles on the meeting.
- The pending item is labelled as Bible Study serving and links to My Serving
  for confirmation.
- Audience-visible meetings without a linked role and display-name-only roles
  do not become personal serving items.
- The visible meeting remains an agenda row independently of whether the user
  has a serving role.

Future-only coverage for BS-ROLE.1C, if approved:

- Meeting detail shows linked-user roles and display-name fallback roles.
- Meeting detail does not expose management controls to ordinary users.
- Other-group users cannot see another group's meeting roles.
- Chinese and English labels remain natural.

Current confirmation coverage should stay focused on My Serving:

- Linked-user Bible Study roles appear in the appropriate My Serving confirmation context.
- Confirming a role records `confirmed_at` and optional `confirmation_note`.
- Display-name-only roles and audience-visible meetings without an explicit linked role do not become My Serving assignments.
- Today may show a pending linked-user role in the action center but remains
  read-only and does not expose confirmation controls.

Future-only coverage, only if separately approved:

- Decline/swap permissions, reassignment/override behavior, notification/reminder behavior, and richer audit expectations.
