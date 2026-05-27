# Bible Study V2 Implementation Strategy

## 1. Purpose

This document records a concrete Bible Study V2 implementation and migration strategy based on the current `studies` app.

Do not implement these changes as part of this document. This is a planning artifact only.

The project remains a lightweight church spiritual life and ministry workflow system, not a full church ERP.

Church structure/domain alignment now lives in `docs/CHURCH_STRUCTURE_DOMAIN_PLAN.md`. That plan clarifies that fellowship `SmallGroup` is not `MinistryTeam`, `BibleStudyMeetingRole` is not `TeamAssignment`, and Bible Study meeting responsibilities should stay separate from church-level ministry operations.

## 2. Current Implementation Inventory

### App Files

Current Bible Study implementation lives in:
- `studies/models.py`
- `studies/forms.py`
- `studies/views.py`
- `studies/urls.py`
- `studies/admin.py`
- `studies/tests.py`
- `studies/templatetags/study_extras.py`
- `templates/studies/study_session_list.html`
- `templates/studies/study_session_detail.html`
- `templates/studies/study_session_form.html`
- `templates/studies/manage_worship_songs.html`
- `templates/studies/worship_song_form.html`

### Existing Models

`BibleStudySeries`
- Fields: `title`, `title_en`, `description`, `description_en`, `is_active`, timestamps.
- Ordering: `title`.
- Bilingual helpers: `get_title(language)`, `get_description(language)`.
- Current use: series container for `BibleStudySession`.

`BibleStudySession`
- Fields: `series`, `title`, `title_en`, `scripture_reference`, `prestudy_datetime`, `study_datetime`, `location`, `meeting_link`, `scope_type`, `district`, `small_group`, `status`, `published_at`, `created_by`, timestamps.
- Scope values: `global`, `district`, `small_group`.
- Status values: `draft`, `published`, `completed`, `cancelled`.
- Relationships: FK to `BibleStudySeries`, optional FK to `District`, optional FK to `SmallGroup`, optional FK to user via `created_by`.
- Current assumptions:
  - One model represents both church-wide Bible Study material and scoped group/district/global sessions.
  - `study_datetime` is the Friday Bible Study time.
  - `prestudy_datetime` is the Thursday pre-study time.
  - Scope controls visibility directly.
- Validation:
  - Global sessions cannot have district or small group.
  - District sessions require district and cannot have small group.
  - Small-group sessions require small group and cannot have district.
  - Status must be one of the known status values.
- Publishing behavior: `save()` sets `published_at` when status becomes `published`.
- Visibility: `can_be_seen_by(user)` allows staff/superuser/management capabilities to see all; normal users only see published/completed non-cancelled sessions in their scope.

`BibleStudyGuide`
- One-to-one with `BibleStudySession`.
- Fields: `guide_body`, `guide_body_en`, `discussion_questions`, `discussion_questions_en`, `prestudy_notes`, `prestudy_notes_en`, timestamps.
- Current assumption: one guide per session.
- Bilingual helpers return English fallback to Chinese/base fields.

`BibleStudyWorshipSong`
- FK to `BibleStudySession`.
- Fields: `sort_order`, `title`, `title_en`, `song_key`, `youtube_url`, `chord_url`, `lyrics_url`, `note`, `note_en`, timestamps.
- Ordering: `session`, `sort_order`, `id`.
- Constraint: unique `(session, sort_order)`.
- Current assumption: worship songs belong to the Bible Study session.
- Bilingual helpers: `get_title(language)`, `get_note(language)`.

### Current Forms

`BibleStudySeriesForm`
- Manages series metadata.

`BibleStudySessionForm`
- Manages session scheduling/scope/status fields.
- Uses `datetime-local` widgets for `prestudy_datetime` and `study_datetime`.
- Localizes field labels and choices through `FORM_TEXT`.

`BibleStudyGuideForm`
- Manages the one-to-one guide fields on the same create/edit page as the session.

`BibleStudyWorshipSongForm`
- Manages session-level worship song fields and localized labels/placeholders.

### Current URLs

`studies/urls.py` defines:
- `/studies/` -> `study_session_list`
- `/studies/new/` -> `create_study_session`
- `/studies/<int:session_id>/` -> `study_session_detail`
- `/studies/<int:session_id>/edit/` -> `edit_study_session`
- `/studies/<int:session_id>/delete/` -> `delete_study_session`
- `/studies/<int:session_id>/worship/` -> `manage_worship_songs`
- `/studies/worship-songs/<int:song_id>/edit/` -> `edit_worship_song`
- `/studies/worship-songs/<int:song_id>/delete/` -> `delete_worship_song`

The normal user top nav currently links Bible Study to `study_session_list`.

### Current Views

`can_manage_bible_studies(user)`
- Allows staff, superuser, `CAP_MANAGE_BIBLE_STUDIES`, or `CAP_PUBLISH_BIBLE_STUDY_GUIDES`.

`get_visible_study_sessions(user)`
- Returns all sessions for managers.
- For normal users, filters by `BibleStudySession.can_be_seen_by(user)`.

`study_session_list`
- Login required.
- Supports tabs: `upcoming`, `past`, and manager-only `drafts`.
- Filters current V1 sessions by date/status.

`study_session_detail`
- Login required.
- Checks `session.can_be_seen_by(user)`.
- Displays session, guide, worship songs, and management controls for managers.

`create_study_session` / `edit_study_session`
- Login required.
- Manager-only.
- Save `BibleStudySession` and `BibleStudyGuide` together.

`delete_study_session`
- Manager-only soft cancellation by setting status to `cancelled`.

`manage_worship_songs`, `edit_worship_song`, `delete_worship_song`
- Manager-only session-level worship song management.

### Current Templates and UI

Current user-facing pages:
- List page shows upcoming/past/draft tabs, session cards, scripture, Thursday pre-study, and Friday Bible Study.
- Detail page shows session status/scope, scripture, pre-study, study time, location/link, worship songs, study guide, discussion questions, and pre-study notes.
- Create/edit page combines session fields and guide fields.
- Worship management page adds/edits/deletes session-level worship songs.

### Current Permission / Capability Usage

Bible Study currently uses:
- `CAP_MANAGE_BIBLE_STUDIES`
- `CAP_PUBLISH_BIBLE_STUDY_GUIDES`
- staff/superuser checks
- `ChurchRoleAssignment.ROLE_PASTOR` indirectly through capability mapping in `accounts.permissions`

There is no separate group-level Bible Study editor permission yet.

### Current Bilingual Behavior

Existing bilingual pattern:
- Models store Chinese/base fields plus English fields.
- Template filters in `studies/templatetags/study_extras.py` select localized titles, guide text, questions, notes, worship song title/note, status labels, and scope labels.
- Form labels and placeholders are localized through dictionaries in `studies/forms.py`.

Some existing source/template strings may display encoding artifacts in raw files, but the intended UI behavior is bilingual.

### Current Worship Song Implementation

Worship songs are implemented as `BibleStudyWorshipSong` attached directly to `BibleStudySession`.

This works for a single global/session-level worship set, but it does not model group-specific worship arrangements, keys, pianist/support notes, or worship lead ownership.

### Relationship to ServiceEvent

There is no current direct relationship between `studies` models and `events.ServiceEvent`.

Bible Study V1 uses its own `prestudy_datetime`, `study_datetime`, `location`, and `meeting_link` fields.

## 3. V1 Limitations

The V1 model is useful as existing functionality, but it is too simple for the real church workflow.

Current limitations:
- `BibleStudySession` mixes church-wide material and scoped meeting concepts.
- `BibleStudyGuide` is one-to-one with the session, so there is no clear separation between pastor/church-wide guide and small-group-specific direction/questions.
- `BibleStudyWorshipSong` is session-level, so it implies one worship set for all groups.
- There is no `BibleStudyMeeting` concept for each small group's Friday meeting.
- There are no group-level preparation roles such as discussion leader, worship lead, pianist, support, or host.
- Scope fields on `BibleStudySession` can hide/show sessions, but they do not represent the two-layer workflow: one church-wide lesson plus many group meetings.

Real workflow:
- Pastor/church-wide pre-study guide is for the whole church.
- Each small group has its own Friday Bible Study meeting.
- Each group may have its own discussion direction, questions, worship arrangement, and leaders/support roles.
- Worship lead/support coworkers need the actual group-level arrangement, not only global session data.

## 4. V2 Target Model

### BibleStudySeries

Keep and adapt the existing model if possible.

Recommended direction:
- Continue using `BibleStudySeries` as the church-wide series container.
- Existing records can remain valid.
- Later fields should be additive only if needed.

### BibleStudyLesson

Represents church-wide lesson/material.

Suggested fields:
- `series`
- `title`
- `title_en`
- `scripture_reference`
- `lesson_date` or `study_week`
- `prestudy_datetime`
- `pastor_guide_body`
- `pastor_guide_body_en`
- `global_discussion_questions`
- `global_discussion_questions_en`
- `prestudy_notes`
- `prestudy_notes_en`
- `status`: `draft`, `published`, `completed`, `cancelled`
- `published_at`
- `created_by`
- timestamps

Purpose:
- Source of truth for church-wide Bible Study content and spiritual preparation.
- Replaces the church-wide content responsibilities currently split across `BibleStudySession` and `BibleStudyGuide`.

### BibleStudyMeeting

Represents a small-group-level meeting for a specific lesson.

Suggested fields:
- `lesson`
- `small_group`
- `meeting_datetime`
- `location`
- `meeting_link`
- `discussion_leader_user` optional
- `discussion_leader_name` fallback
- `group_direction`
- `group_direction_en`
- `group_questions`
- `group_questions_en`
- `status`: `draft`, `published`, `completed`, `cancelled`
- `service_event` optional, nullable
- `created_by`
- timestamps

Recommended constraint:
- Unique `(lesson, small_group)` unless the church later needs multiple meetings for the same group and lesson.

Purpose:
- Source of truth for each small group's Friday Bible Study preparation and meeting-specific content.

### BibleStudyMeetingWorshipSong

Represents the actual group-level worship set.

Suggested fields:
- `meeting`
- `sort_order`
- `title`
- `title_en`
- `song_key`
- `youtube_url`
- `chord_url`
- `lyrics_url`
- `arrangement_notes`
- `arrangement_notes_en`
- `worship_lead_user` optional
- `worship_lead_name` fallback
- `support_notes`
- `support_notes_en`
- timestamps

Recommended constraint:
- Unique `(meeting, sort_order)`.

Purpose:
- Move the real worship set and arrangement workflow from global session-level to small-group meeting-level.

### BibleStudyMeetingRole

Represents simple preparation roles for a meeting.

Suggested role values:
- `discussion_leader`
- `worship_lead`
- `pianist`
- `support`
- `host`

Suggested fields:
- `meeting`
- `role`
- `user` optional
- `display_name` fallback
- `notes`
- `notes_en`
- timestamps

Purpose:
- Display simple preparation ownership without creating a scheduling engine.

### Existing V1 Model Reuse / Legacy Direction

Recommended:
- Keep `BibleStudySeries`.
- Add V2 models alongside existing V1 models.
- Do not destructively rename `BibleStudySession` in the first implementation step.
- Treat `BibleStudySession`, `BibleStudyGuide`, and `BibleStudyWorshipSong` as V1/legacy compatibility models until V2 is stable.

## 5. Migration Strategy

Use an additive migration strategy.

Do not destructively rename V1 models in the first step. Preserve existing `BibleStudySession` data and keep `/studies/` working during migration.

### BibleStudySeries

Recommended handling:
- Reuse existing `BibleStudySeries`.
- Existing series records can be referenced by new `BibleStudyLesson`.
- No initial data migration needed.

### BibleStudySession

Recommended handling:
- Keep as legacy V1.
- Do not map every existing session automatically in the first V2 migration.
- Later, optional data migration can create `BibleStudyLesson` records from global or broadly scoped V1 sessions.

Mapping considerations:
- A global V1 `BibleStudySession` with a guide maps most naturally to `BibleStudyLesson`.
- A small-group-scoped V1 `BibleStudySession` maps more naturally to `BibleStudyMeeting`, but may also need a parent `BibleStudyLesson`.
- A district-scoped V1 `BibleStudySession` does not map perfectly to either one lesson or one group meeting; preserve as legacy unless a clear manual mapping is defined.

### BibleStudyGuide

Recommended handling:
- Preserve as legacy guide for V1 sessions.
- If migrating a V1 session to a `BibleStudyLesson`, copy:
  - `guide_body` -> `pastor_guide_body`
  - `guide_body_en` -> `pastor_guide_body_en`
  - `discussion_questions` -> `global_discussion_questions`
  - `discussion_questions_en` -> `global_discussion_questions_en`
  - `prestudy_notes` -> `prestudy_notes`
  - `prestudy_notes_en` -> `prestudy_notes_en`

### BibleStudyWorshipSong

Recommended handling:
- Preserve as V1 session-level worship songs.
- Do not automatically migrate to group-level worship songs in the first step.
- If a V1 session is later manually converted into one or more `BibleStudyMeeting` records, existing songs may be copied as starter songs into each meeting only if staff confirms that is appropriate.

Reason:
- V2 target says the actual worship set belongs to the small-group meeting, not the global session.
- Automatic copying risks implying that every group uses the same arrangement.

### V1 Scope Fields

`scope_type`, `district`, and `small_group` on `BibleStudySession` should remain as legacy visibility controls.

Do not carry this exact pattern into V2 church-wide content:
- `BibleStudyLesson` is church-wide lesson/material.
- `BibleStudyMeeting` is scoped by `small_group`.
- District-level behavior, if needed, should be explicit in views/permissions rather than turning `BibleStudyLesson` into another scoped event model.

### Status Preservation

V2 should keep the familiar status lifecycle:
- `draft`
- `published`
- `completed`
- `cancelled`

Preserve `published_at` behavior for publish transitions.

### Compatibility

Initial V2 implementation should:
- Add models and admin without changing existing V1 pages.
- Keep `/studies/` stable.
- Add V2 display behind the same entry point only after model tests pass.
- Provide a V1 legacy fallback section if V2 content does not exist yet.

## 6. URL and UI Strategy

Do not break the current user-facing Bible Study link.

### Phase UI Direction

1. Keep `/studies/` stable.
2. Initially show V2 lessons/meetings while preserving V1 legacy fallback.
3. Add church-wide lesson detail.
4. Add small-group meeting detail.
5. Add group-level guide/questions management.
6. Add simple meeting role display/editing.
7. Add group-level worship set management.
8. Add role-aware editing permissions only after meeting roles are validated.

### Possible Future URLs

Keep existing V1 URLs until replacement is proven:
- `/studies/` remains Bible Study entry.

Potential V2 URLs:
- `/studies/lessons/` for staff/pastor lesson management, or folded into `/studies/` for normal users.
- `/studies/lessons/<id>/` for church-wide lesson detail.
- `/studies/meetings/<id>/` for group meeting detail.
- `/studies/meetings/<id>/edit/` for group-level meeting preparation.
- `/studies/meetings/<id>/worship/` for group-level worship set management.
- `/studies/meetings/<id>/roles/` for simple role display/editing if needed.

### Normal User Flow

Normal logged-in user:
- Opens Bible Study from top nav.
- Sees current/upcoming published church-wide lesson.
- Sees their own small-group meeting if one exists.
- Can view pastor guide/global questions and their group's direction/questions/worship set.
- Should not see other groups' meeting preparation unless explicitly allowed later.

### Small Group Leader Flow

Small group leader:
- Opens Bible Study.
- Sees their group's meeting.
- Can edit group direction/questions and possibly roles/worship set depending on policy.
- Does not manage church-wide lesson content unless separately authorized.

### Staff/Pastor Flow

Staff/pastor:
- Can create/edit church-wide lessons.
- Can publish/cancel/complete lessons.
- Can see all group meetings.
- Can create or regenerate group meetings for lessons.
- Can assist with group-level content if needed.

### Bilingual UI Expectations

Follow current bilingual patterns:
- Chinese UI should show Chinese labels/data when available.
- English UI should prefer English fields when available.
- Add `*_en` fields for user-facing content.
- Add template filters or model helpers mirroring current `study_extras.py`.

## 7. Permission Strategy

Use existing capability and church-role patterns where possible.

Recommended direction:
- Staff/superuser: manage all Bible Study V2 content.
- `CAP_MANAGE_BIBLE_STUDIES`: manage church-wide lessons and all meetings.
- `CAP_PUBLISH_BIBLE_STUDY_GUIDES`: publish church-wide lessons/guides if this remains the intended capability.
- Pastor/global leader roles: manage church-wide lessons through existing capability mapping.
- Small group leader/coordinator: manage meeting-level content for their own small group.
- Normal users: view published lesson and published meeting content in their own scope.

Who can manage church-wide lessons:
- staff/superuser
- users with `CAP_MANAGE_BIBLE_STUDIES`
- users with pastor/global Bible Study management capability mapping

Who can manage small-group meeting content initially:
- staff/superuser
- users with `CAP_MANAGE_BIBLE_STUDIES`
- users with `CAP_PUBLISH_BIBLE_STUDY_GUIDES` if the app continues treating them as Bible Study managers

Small-group leader/coordinator editing should wait until a reliable small-group coworker role model or helper exists. Do not overload generic group-progress permissions as Bible Study preparation permissions.

Who can edit group worship set:
- manager-only initially, or a meeting role with `worship_lead` / `support` once `BibleStudyMeetingRole` exists and role-aware permissions are explicitly planned.
- Avoid creating a complex new permission system in V2.1-V2.3.

Who can view published content:
- logged-in users can view published church-wide lesson content.
- logged-in users can view their own group's published meeting content.
- staff/managers can view all.

## 8. Relationship to ServiceEvent

Bible Study owns content and spiritual preparation.

ServiceEvent remains an optional operations/calendar anchor.

Recommended:
- Add optional nullable `service_event` on `BibleStudyMeeting`, not on `BibleStudyLesson`.
- Use `ServiceEvent` only for generic date/time/location/operations/team assignment anchoring when needed.
- Do not make ServiceEvent the source of truth for Bible Study content.
- Do not require a ServiceEvent link in V2. It should remain optional unless a later pilot proves it necessary.

## 9. Relationship to Community Activities

Community Activities is separate and future/deferred.

Bible Study V2 should not use `CommunityActivity`.

CommunityActivity is for signup-oriented fellowship/community activities where the main question is "who wants to attend/signup?"

BibleStudyMeeting is for small-group Bible Study preparation and content where the main question is "what is our group's Bible Study preparation, worship arrangement, and meeting direction?"

Do not merge these concepts in V2.

## 10. Non-Goals

Bible Study V2 does not include:
- Checklist V1
- automatic scheduling
- availability matrix
- swap requests
- reminders
- attendance tracking
- full worship ministry system
- full song library
- Google Docs full-content migration
- Community Activities implementation
- ServiceEvent replacement
- full ERP functionality

## 11. Proposed Implementation Phases

### Phase BS-V2.0 - Strategy / Preparation

- Create this implementation strategy.
- Inspect current `studies` app.
- No code changes.

### Phase BS-V2.1 - Add V2 Models

- Add additive models only:
  - `BibleStudyLesson`
  - `BibleStudyMeeting`
  - `BibleStudyMeetingWorshipSong`
  - `BibleStudyMeetingRole`
- Add migrations.
- Register models in admin.
- Add model helper methods for bilingual display.
- Add model tests for validation, status behavior, visibility primitives, and ordering.
- Do not change `/studies/` behavior yet.

### Phase BS-V2.2 - Staff Church-Wide Lesson Management

- Add create/edit/list/detail views for `BibleStudyLesson`.
- Preserve existing V1 pages.
- Add permission tests for staff/pastor/capability users.
- Add bilingual labels and template filters.

### Phase BS-V2.3 - Small-Group Meeting Creation and Visibility

- Add `BibleStudyMeeting` list/detail for the current user's group.
- Decide whether staff manually creates meetings or whether a controlled management action creates one per active small group.
- Ensure normal users see only their own group meeting.
- Staff/managers can see all meetings.

### Phase BS-V2.4 - Group-Level Guide / Questions

- Allow authorized managers to edit group direction/questions for a small group meeting.
- Defer small-group leader/coordinator editing until reliable small-group coworker role helpers exist.
- Normal users can view published group content.
- Keep pastor/church-wide guide on `BibleStudyLesson`.

### Phase BS-V2.5A - Simple Meeting Roles

- Add simple display/editing for `BibleStudyMeetingRole`.
- Supported roles: discussion leader, worship lead, pianist, support, host.
- Manual assignment first.
- No scheduling engine.
- No availability workflow.
- `BibleStudyMeetingRole` is not `TeamAssignment`.

### Phase BS-V2.5B - Group-Level Worship Set

- Add management for `BibleStudyMeetingWorshipSong`.
- Managers can manage songs initially.
- Group worship lead/support editing can be considered later after meeting roles are implemented.
- Support users can view group-level arrangement, key, and links.
- Do not create a full song library.

### Phase BS-V2.5C - Role-Aware Editing Permissions

- Decide whether meeting role holders can edit preparation/worship fields for their assigned meeting.
- Keep this narrow and explicit.
- Do not add automatic scheduling, availability, swaps, or reminders.

### Phase BS-V2.6 - V1 Compatibility / Migration Cleanup

- Preserve old sessions.
- Optionally show legacy V1 sessions in a fallback section.
- Decide later whether to migrate, archive, or leave V1 session model as legacy.
- Only consider data migration after staff validates the V2 workflow with real examples.

## 12. Test Strategy

Use targeted tests only.

Baseline checks for each implementation phase:
- `python manage.py check`
- `python manage.py test studies accounts -v 2`

Include additional app tests only if touched:
- `python manage.py test ministry -v 2` if ServiceEvent/ministry integration or assignment surfaces are touched.
- `python manage.py test reading -v 2` if Today dashboard Bible Study summary behavior changes.

Full suite remains user-run unless explicitly requested.

Suggested phase coverage:

BS-V2.1:
- model creation and validation
- status transitions / `published_at`
- unique `(lesson, small_group)` meeting behavior
- worship song ordering and unique order per meeting
- role validation

BS-V2.2:
- staff/pastor can create/edit/publish lessons
- regular user cannot manage lessons
- bilingual lesson display
- `/studies/` remains available

BS-V2.3:
- normal user sees own group meeting
- normal user does not see other group meeting details
- staff sees all meetings
- meeting visibility follows lesson/meeting status

BS-V2.4:
- group leader can edit own group direction/questions
- group leader cannot edit another group
- normal users view published group questions

BS-V2.5A:
- role UI stays manager-only or explicitly authorized
- role display renders correctly
- no scheduling/reminder routes are introduced

BS-V2.5B:
- authorized user can add/edit/delete meeting worship songs
- regular user can view own group worship set
- session-level V1 worship songs remain visible in legacy fallback

BS-V2.5C:
- role-aware edit permissions, if added, stay scoped to the parent meeting
- normal members do not gain edit access accidentally

BS-V2.6:
- existing V1 session pages still work
- legacy fallback does not leak hidden/cancelled sessions
- optional migration command, if later added, is idempotent and preserves data

## 13. Risks and Open Questions

Open decisions:
- Should every lesson auto-create meetings for all active small groups, or should staff create meetings manually?
- Who exactly can edit group-level worship set: small group leader, assigned worship lead, staff, or all meeting role holders?
- Should `BibleStudyMeeting` require a `ServiceEvent` link or keep it optional?
- Should V1 sessions be migrated automatically or preserved as legacy?
- Should normal users see only their own group meeting, or also the church-wide lesson directly on the list?
- Should district leaders have special Bible Study meeting management rights for groups in their district?
- Should group-level content have its own draft/published state separate from lesson status?
- Should church-wide lessons optionally include suggested songs later, separate from actual group worship sets?

Risks:
- Automatic migration could incorrectly treat district/session-level V1 records as either lessons or meetings.
- Copying session-level worship songs to group meetings could imply all groups use the same arrangement.
- Adding too many permissions early could slow the pilot and create unclear ownership.
- Reusing `/studies/` too aggressively could break current V1 pages if not phased carefully.

## 14. Recommended Next Step

For future Bible Study implementation, proceed with the smallest next accepted phase.

Recommended next phase after church structure alignment:
- BS-V2.5A - Simple `BibleStudyMeetingRole` UI

Keep the next phase narrow:
- no destructive renames
- no V1 data deletion
- no `/studies/` route breakage
- no `ServiceEvent` requirement
- no Checklist V1
- no automatic scheduling, availability, swaps, or reminders
