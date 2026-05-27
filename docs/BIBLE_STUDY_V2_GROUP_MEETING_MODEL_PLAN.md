# Bible Study V2 Group Meeting Model Plan

## 1. Purpose

This document records the recommended Bible Study V2 architecture before implementation.

Do not implement these changes as part of this planning document. This is a reference plan for future development.

See also `docs/CHURCH_STRUCTURE_DOMAIN_PLAN.md` for broader church structure boundaries:
- fellowship `SmallGroup` is not `MinistryTeam`
- small-group coworker roles are not `TeamAssignment`
- `BibleStudyMeetingRole` represents one-meeting Bible Study preparation responsibility
- `ServiceEvent` remains an optional operations anchor, not the Bible Study content source of truth

## 2. Current Problem

The current Bible Study V1 model appears too simple for the real church workflow. It risks mixing:
- church-wide study material
- small-group Friday Bible Study meetings
- pre-study guide
- group-level discussion direction
- group-level questions
- worship set
- leaders/support roles

The real workflow is two-layer:
- Pastor/church-wide guide is for the whole church.
- Each small group has its own Friday Bible Study meeting.
- Each group may have its own discussion direction, questions, worship arrangement, and leaders/support roles.

## 3. Recommended Model Direction

Keep or adapt:
- BibleStudySeries

### BibleStudyLesson

Represents the church-wide lesson/material.

Suggested fields:
- series
- title
- title_en
- scripture_reference
- lesson_date or study_week
- prestudy_datetime
- pastor_guide_body
- pastor_guide_body_en
- global_discussion_questions
- global_discussion_questions_en
- prestudy_notes
- prestudy_notes_en
- status: draft / published / completed / cancelled
- published_at
- created_by

### BibleStudyMeeting

Represents a small-group-level Bible Study gathering for a specific lesson.

Suggested fields:
- lesson
- small_group
- meeting_datetime
- location
- meeting_link
- discussion_leader_user nullable
- discussion_leader_name fallback
- group_direction
- group_direction_en
- group_questions
- group_questions_en
- status: draft / published / completed / cancelled
- service_event nullable
- created_by

Recommended constraint:
- unique(lesson, small_group), unless the church truly needs multiple meetings per group for the same lesson.

### BibleStudyMeetingWorshipSong

Represents the actual worship set for a specific small-group Bible Study meeting.

Suggested fields:
- meeting
- sort_order
- title
- title_en
- song_key
- youtube_url
- chord_url
- lyrics_url
- arrangement_notes
- arrangement_notes_en
- worship_lead_user nullable
- support_notes

### BibleStudyMeetingRole

Represents simple preparation roles for that Bible Study meeting.

Suggested roles:
- discussion_leader
- worship_lead
- pianist
- support
- host

Suggested fields:
- meeting
- user nullable
- display_name fallback
- role
- notes

Purpose:
- Capture per-meeting responsibility, not long-term small-group coworker identity.
- Example: this week one Rainbow 4 E coworker leads discussion.
- Example: this week one Rainbow 4 W coworker leads worship.
- Manual assignment first.

Not:
- `TeamAssignment`
- automatic scheduling
- availability matrix
- swap requests
- reminders

Long-term small-group coworker roles such as C/E/O/W/F should be planned separately as small-group coworker assignments, not as `MinistryTeam`.

## 4. Fellowship Small Group Boundary

Friday Bible Study happens at the fellowship small group level.

Examples:
- Rainbow 1
- Rainbow 4

`BibleStudyMeeting` should remain anchored to `SmallGroup`.

Do not model a fellowship small group as `MinistryTeam`.
Do not use `TeamAssignment` for Friday Bible Study discussion/worship/pianist/host rotation.
Use `BibleStudyMeetingRole` for those per-meeting responsibilities.

## 5. Bible Study and ServiceEvent Relationship

Principle:
- Bible Study owns content and spiritual preparation.
- ServiceEvent owns generic event/calendar/operations anchoring.
- ServiceEvent should not become the Bible Study content model.

Recommended relationship:
- BibleStudyMeeting may optionally link to ServiceEvent.
- ServiceEvent can be used for date/time/location/operations/team assignment anchoring.
- BibleStudyLesson and BibleStudyMeeting should remain the source of truth for Bible Study content.

## 6. Worship Songs Placement

Recommendation:
- Actual worship songs should belong to small-group BibleStudyMeeting, not only to a global BibleStudySession/Lesson.
- A church-wide lesson may optionally have suggested songs later, but the real worship set and arrangement should be group-level.

Reason:
- Worship lead, arrangement, key, support notes, pianist/support roles are usually group-specific.
- Support coworkers need the actual group-level arrangement, not just a global generic song list.
- Meeting roles should be added before role-aware worship editing permissions because worship ownership depends on knowing who the worship lead/support/pianist are.

## 7. Permission Direction

Keep simple:
- Normal users can view published study material relevant to them.
- Staff can manage church-wide lessons.
- Staff/managers can manage group meetings initially.
- Small-group leader/coordinator editing should wait until a reliable small-group coworker role model or helper exists.
- Avoid complex permission systems in V2 unless necessary.

## 8. Non-Goals for Bible Study V2

- No full worship ministry system.
- No full song library unless later justified.
- No attendance tracking.
- No automatic scheduling.
- No reminders.
- No availability matrix.
- No swap request.
- No Google Docs full-content migration.
- No complex response/submission workflow yet.
- No forcing Bible Study meeting roles into TeamAssignment.
- No forcing small-group coworkers into MinistryTeam.

## 9. Suggested Implementation Phases

Future reference only:

### Phase BS-V2.1

- Add planning-compatible models or migration strategy.

### Phase BS-V2.2

- Add church-wide lesson list/detail.

### Phase BS-V2.3

- Add small-group meeting list/detail.

### Phase BS-V2.4

- Add group-level direction/questions.

### Phase BS-V2.5A

- Add simple `BibleStudyMeetingRole` UI.
- Manager/staff manual assignment first.
- No automatic rotation/scheduling.

### Phase BS-V2.5B

- Add group-level worship set UI.
- Keep management simple and manager-controlled until role-aware editing permissions are explicitly planned.

### Phase BS-V2.5C

- Add role-aware editing permissions only if needed later.

### Phase BS-V2.6

- Add backward compatibility or migration notes for existing BibleStudySession data.
