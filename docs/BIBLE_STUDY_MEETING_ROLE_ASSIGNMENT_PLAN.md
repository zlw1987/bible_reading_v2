# Bible Study Meeting Role Assignment Plan

Status: BS-ROLE.1A docs-only planning complete; BS-ROLE.1B management form/UI polish complete; TODAY-HOME.1D linked Bible Study role chips on Today complete.

Scope: make small-group `BibleStudyMeetingRole` assignment reliable enough for Today-page surfacing and clearer Friday Bible Study preparation UX. BS-ROLE.1B and TODAY-HOME.1D are now complete; this plan still does not approve any further code, schema, migration, permission, notification, or confirmation-workflow changes.

## 1. Current-State Audit

### Models and Fields

`BibleStudyMeeting`

- Anchors one small-group Friday meeting to a `BibleStudyLesson` and legacy `SmallGroup`.
- Key fields: `lesson`, `small_group`, `meeting_datetime`, `location`, `location_en`, `meeting_link`, `group_direction`, `group_direction_en`, `group_questions`, `group_questions_en`, `status`, optional `service_event`, and audit fields.
- Still has older discussion-leader fields: `discussion_leader_user` and `discussion_leader_name`.
- Current visibility is `BibleStudyMeeting.can_be_seen_by(user)`: staff/superuser/Bible Study managers can see all; ordinary users can see published meetings for their current `Profile.small_group` when the parent lesson and schedule are published.

`BibleStudyMeetingRole`

- Represents one per-meeting responsibility.
- Role choices: `discussion_leader`, `worship_lead`, `pianist`, `support`, `host`.
- Key fields: `meeting`, `role`, nullable `user`, free-text `display_name`, `notes`, `notes_en`, timestamps.
- `get_display_name()` prefers `display_name`, then falls back to the linked user's full name or username, then blank.
- There is no confirmation/status/accepted/declined field.
- There is no model-level requirement that either `user` or `display_name` be present; BS-ROLE.1B enforces the nonblank assignee requirement at the form layer.

`BibleStudyMeetingWorshipSong`

- Represents one worship-set item for a meeting.
- Key fields: `meeting`, `sort_order`, `title`, `title_en`, `song_key`, links, arrangement notes, nullable `worship_lead_user`, free-text `worship_lead_name`, support notes, timestamps.
- This model has a similar identity pattern for worship lead, but Today role chips should use `BibleStudyMeetingRole`, not infer from song lead names.

### Where Roles Are Created or Edited

- `BibleStudyMeetingRoleForm` exposes `role`, `user`, `display_name`, `notes`, and `notes_en`.
- When the form receives a meeting, the `user` queryset is limited to active users whose `profile.small_group` matches the meeting's small group, plus the already-selected user when editing.
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

- Role form filtering to the meeting small group.
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
- Small groups can still record guest or one-off names when no account exists.

## 3. Recommended Design Direction

- Prefer linking roles to real `User` records whenever the responsible person has an active account in the meeting's small group.
- Keep `display_name` only as a fallback for people without accounts, guest names, or one-off cases.
- Do not infer identity by matching `display_name` to a user's full name, username, preferred name, profile field, or translated display text.
- For Today role chips, use only `BibleStudyMeetingRole.objects.filter(user=request.user, ...)` after applying the existing meeting visibility/date/status rules.
- If both `user` and `display_name` are present, treat `user` as the identity contract. Display can remain a separate UX decision, but Today identity must not depend on the manual name.
- Keep `BibleStudyMeetingRole` separate from `TeamAssignment`; Friday Bible Study meeting responsibilities are not Ministry Operations serving assignments.
- Keep ordinary-user visibility based on `BibleStudyMeeting.can_be_seen_by()` and legacy `Profile.small_group`; do not use `ChurchStructureMembership` as runtime visibility.

## 4. Confirmation Decision

Recommendation: no confirmation workflow for now.

Use display-only responsibility surfacing first:

- Managers record the role.
- The linked user can see the responsibility on meeting detail and now on Today for linked-user roles.
- No accept/decline state is added in this slice.

Why this fits now:

- Bible Study roles appear to be lightweight small-group preparation responsibilities, not formal ministry scheduling assignments.
- Existing product boundaries already keep Bible Study roles separate from `TeamAssignment`, confirmation status, swap requests, reminders, availability, and automation.
- Adding confirmation would require product decisions around who can accept, decline, reassign, remind, override, and audit. That is a separate workflow design, not a polish prerequisite.

Tradeoffs:

- No confirmation keeps the workflow simple and avoids schema/workflow expansion.
- It does not prove the person has accepted the responsibility.
- If real users later need acceptance/decline, plan a separate confirmation milestone with explicit UX, permissions, status fields, notifications/reminders if needed, and tests.

## 5. Implementation Milestone Split

### BS-ROLE.1B - Management UI Polish

Status: complete.

Goal: encourage reliable user linking where possible while preserving a fallback path.

Completed scope:

- Clarify `BibleStudyMeetingRoleForm` help text so managers choose a user when the person has an account.
- Require at least one assignee signal: linked `user` or `display_name`.
- Warn/help managers that a display-name-only role can show on meeting detail but cannot appear as "my role" on Today.
- Keep the `user` queryset limited to active users in the meeting small group, with the existing selected-user exception on edit.
- Keep role management restricted to current Bible Study managers.

Likely affected files later:

- `studies/forms.py`
- `templates/studies/manage_bible_study_meeting_roles.html`
- `templates/studies/bible_study_meeting_role_form.html`
- `studies/tests.py`

Schema result: no schema change was added. A schema change would become necessary only if product requires database-level nonblank assignee enforcement, confirmation status, audit history, or richer role assignment metadata.

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
- No role confirmation/status/accept/decline/reminder/notification workflow.
- No schema/migration/URL/runtime-visibility change.
- No `ChurchStructureMembership` runtime visibility.

### Optional Future Confirmation Milestone

Only plan this if real use shows that Bible Study responsibilities need accept/decline tracking.

Potential scope:

- Confirmation status.
- Who can confirm.
- Who can override.
- How declined roles are reassigned.
- Whether notifications/reminders are needed.
- Audit/history expectations.

This should remain separate from BS-ROLE.1B/1C and Today role-chip surfacing.

## 6. Data and Visibility Contract

- Ordinary users see only their own visible small-group Bible Study meeting according to current meeting visibility rules.
- Today role chips show only roles linked to the signed-in user through `BibleStudyMeetingRole.user`.
- Today must not show another person's role for the user's group unless the product explicitly designs a group-wide preparation summary.
- Meeting detail can continue showing the existing role list according to the current meeting visibility rules.
- Display-name-only roles may appear on meeting detail but must not be treated as "my role."
- Staff/admin users keep current management access; no new staff/admin leakage is introduced.
- Do not use `ChurchStructureMembership` as runtime visibility for Bible Study roles or Today role chips.
- Do not infer Bible Study role ownership from `TeamAssignment`, `TeamMembership`, `ServiceEvent`, `MinistryTeam`, old `discussion_leader_name`, worship song free-text names, or display-name matching.

## 7. Non-Goals

- No broad Bible Study rewrite.
- No attendance.
- No notification/reminder system.
- No Community Activities.
- No automatic role assignment.
- No role confirmation unless separately approved.
- No swap requests, availability, checklist engine, or automation.
- No migration from `Profile.small_group` to `ChurchStructureMembership` runtime visibility.
- No conversion of `BibleStudyMeetingRole` into `TeamAssignment`.
- No ServiceEvent or My Serving behavior changes.

## 8. Recommended First Implementation Slice

Recommended first slice: BS-ROLE.1B. Completed without schema changes.

Make the existing role management workflow safer and clearer:

- Add form-level validation requiring either `user` or `display_name`.
- Add manager-facing help text explaining that linked users are required for Today "my role" surfacing, while display names are fallback-only.
- Preserve the current group-limited user picker.
- Preserve current meeting detail display and permissions.
- Do not add confirmation/status fields.
- BS-ROLE.1B itself did not change Today.

This gave TODAY-HOME.1D a cleaner data contract without changing runtime visibility or creating a heavier workflow. BS-ROLE.1B did not change Today/Home files; TODAY-HOME.1D later completed the read-only Today surfacing separately.

## 9. Regression Coverage and Future Tests

Completed BS-ROLE.1B coverage:

- Linked-user role saves and displays.
- Display-name fallback role saves and displays.
- Blank `user` plus blank `display_name` is rejected by the form.
- User picker remains limited to the meeting small group, while preserving the currently selected user on edit.
- Ordinary users still cannot manage roles.

Completed TODAY-HOME.1D coverage:

- Today shows role chips only for roles with `role.user == request.user`.
- Today ignores display-name-only roles even when the name matches the signed-in user.
- Today hides other users' and other groups' roles.
- Today hides roles when the meeting is not visible.
- Chinese role label rendering is covered.
- Today does not expose role-management controls.
- Today does not render a role confirmation form.

Future-only coverage for BS-ROLE.1C, if approved:

- Meeting detail shows linked-user roles and display-name fallback roles.
- Meeting detail does not expose management controls to ordinary users.
- Other-group users cannot see another group's meeting roles.
- Chinese and English labels remain natural.

Future-only coverage for optional confirmation, only if real use later justifies it:

- Confirmation status, accept/decline permissions, reassignment/override behavior, notification/reminder behavior if approved, and audit expectations.
