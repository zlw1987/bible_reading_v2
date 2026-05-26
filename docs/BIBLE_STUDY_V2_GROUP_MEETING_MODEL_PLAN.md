# Bible Study V2 Group Meeting Model Plan

## 1. Purpose

This document records the recommended Bible Study V2 architecture before implementation.

Do not implement these changes as part of this planning document. This is a reference plan for future development.

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

## 4. Bible Study and ServiceEvent Relationship

Principle:
- Bible Study owns content and spiritual preparation.
- ServiceEvent owns generic event/calendar/operations anchoring.
- ServiceEvent should not become the Bible Study content model.

Recommended relationship:
- BibleStudyMeeting may optionally link to ServiceEvent.
- ServiceEvent can be used for date/time/location/operations/team assignment anchoring.
- BibleStudyLesson and BibleStudyMeeting should remain the source of truth for Bible Study content.

## 5. Worship Songs Placement

Recommendation:
- Actual worship songs should belong to small-group BibleStudyMeeting, not only to a global BibleStudySession/Lesson.
- A church-wide lesson may optionally have suggested songs later, but the real worship set and arrangement should be group-level.

Reason:
- Worship lead, arrangement, key, support notes, pianist/support roles are usually group-specific.
- Support coworkers need the actual group-level arrangement, not just a global generic song list.

## 6. Permission Direction

Keep simple:
- Normal users can view published study material relevant to them.
- Small-group leaders/coordinators can edit their own group meeting guide/questions/worship set.
- Staff can manage church-wide lessons.
- Avoid complex permission systems in V2 unless necessary.

## 7. Non-Goals for Bible Study V2

- No full worship ministry system.
- No full song library unless later justified.
- No attendance tracking.
- No automatic scheduling.
- No reminders.
- No availability matrix.
- No swap request.
- No Google Docs full-content migration.
- No complex response/submission workflow yet.

## 8. Suggested Implementation Phases

Future reference only:

### Phase BS-V2.1

- Add planning-compatible models or migration strategy.

### Phase BS-V2.2

- Add church-wide lesson list/detail.

### Phase BS-V2.3

- Add small-group meeting list/detail.

### Phase BS-V2.4

- Move or duplicate worship set concept to meeting-level.

### Phase BS-V2.5

- Add group-level direction/questions.

### Phase BS-V2.6

- Add simple leader/support role display.

### Phase BS-V2.7

- Add backward compatibility or migration notes for existing BibleStudySession data.

