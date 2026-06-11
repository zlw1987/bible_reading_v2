# DATETIME-UX.1A Member-Facing Datetime Display Consistency Plan

## 1. Current-State Audit

### Member-facing raw datetime output

The current member-facing surfaces often render Django datetime objects directly, which produces raw or locale-agnostic output instead of ordinary EN/ZH reading copy.

- Today / home (`templates/reading/home.html`)
  - Pending serving confirmation rows render `item.assignment.service_event.start_datetime` directly.
  - This Week Church Gatherings render `row.event.start_datetime` directly.
  - This Week Small Group Bible Study renders `meeting.meeting_datetime` directly.
- Church Gatherings (`templates/events/service_event_list.html`, `templates/events/service_event_detail.html`)
  - List cards render `event.start_datetime` directly.
  - Detail renders `event.start_datetime` and `event.end_datetime` directly.
- Bible Study v2 member surfaces (`templates/studies/study_session_list.html`, `templates/studies/bible_study_meeting_detail.html`)
  - The current Bible Study landing card renders `meeting.meeting_datetime` directly.
  - Meeting detail renders `meeting.meeting_datetime` directly.
- My Serving (`templates/ministry/my_serving.html`, `templates/ministry/_serving_card.html`, `templates/ministry/assignment_detail.html`)
  - Serving cards render `serving_item.assignment.service_event.start_datetime` directly.
  - Assignment detail renders `assignment.service_event.start_datetime` directly.
  - Confirmation timestamps render `confirmed_at` directly.

### Existing format filters and contrast surfaces

- No reusable humanized member-facing datetime filter was found in the existing app templatetags:
  - `events/templatetags/event_extras.py`
  - `studies/templatetags/study_extras.py`
  - `ministry/templatetags/ministry_extras.py`
  - `reading/templatetags/reading_extras.py`
- Some staff or staff-adjacent scheduling surfaces already use explicit Django `date` filters with machine-like formats:
  - `templates/ministry/assignment_list.html`: `group.event.start_datetime|date:"Y-m-d H:i"`
  - `templates/ministry/team_schedule.html`: event and suggestion datetimes use `date:"Y-m-d H:i"`.
  - Date input values use `date:'Y-m-d'`, which should remain form/input-oriented.
- Several staff/manage Bible Study tables still render raw datetimes, for example meeting management and guide detail tables. These are useful contrast points, but they should not drive the first member-facing slice unless the change is trivial after the shared helper exists.

### Language and timezone behavior

- The app language toggle is independent of Django's locale selection:
  - `accounts.language.get_user_language(request)` reads `?lang=`, session language, then `Profile.preferred_language`, with default `zh`.
  - Templates branch on the app-level `language` value instead of relying on Django locale activation.
- Django settings currently use `LANGUAGE_CODE = 'en-us'`, `TIME_ZONE = 'UTC'`, and `USE_TZ = True` in `config/settings.py`.
- Views use timezone-aware querying and creation patterns in relevant areas:
  - `timezone.now()` is used for upcoming/past filtering.
  - Some generated ServiceEvent and Bible Study datetimes are created with `timezone.make_aware(..., timezone.get_current_timezone())`.
- Display timezone handling is not currently explicit at the template display layer. Direct rendering and Django `date` filters therefore risk inconsistent assumptions if settings or active timezone behavior changes later.

## 2. Product Goal

Ordinary members should see dates and times that are easy to read, consistent, and pastoral in both EN and ZH.

The first consistency pass should align:

- Today page event and Bible Study times.
- Church Gathering list/detail times.
- Bible Study v2 landing/detail meeting times.
- My Serving card/detail times.

Target examples:

- EN: `Fri, Jun 14, 7:30 PM`
- ZH: `6月14日（周五）晚上7:30`

## 3. Recommended Design

Add one small reusable display helper for member-facing datetime output.

Recommended shape:

- Add a template filter, preferably in a new shared templatetag module such as `reading/templatetags/datetime_extras.py` or another locally appropriate shared app.
- Filter signature should accept a datetime value and the existing app-level `language`, for example `{{ value|member_datetime:language }}`.
- Input should be an aware datetime. If a naive datetime appears, the helper should either make the conversion explicit through Django's current timezone or return a safe fallback after tests cover the decision.
- Convert with Django timezone APIs before formatting, for example `timezone.localtime(value, timezone.get_current_timezone())`, so display behavior follows Django settings consistently.
- Keep the formatter server-side. Do not add JavaScript date formatting or a frontend date library.
- Keep labels separate from values. The helper should format only the datetime, not add field labels like `Start Time` or `Meeting Time`.

Suggested output rules:

- EN:
  - Abbreviated weekday.
  - Abbreviated month.
  - Numeric day.
  - 12-hour time with AM/PM.
  - Example: `Fri, Jun 14, 7:30 PM`.
- ZH:
  - Month/day.
  - Chinese weekday in parentheses.
  - Natural day period for AM/PM where practical.
  - Example: `6月14日（周五）晚上7:30`.

## 4. Scope Recommendation

DATETIME-UX.1B should update member-facing surfaces only:

- Today page:
  - pending serving confirmation rows;
  - This Week Church Gatherings;
  - This Week Small Group Bible Study.
- Church Gatherings:
  - list card start time;
  - detail start/end time.
- Bible Study:
  - v2 landing/current meeting card;
  - BibleStudyMeeting detail meeting time;
  - include the older `study_session_*` member path only if it is still user-reachable and quick to update with the same helper.
- My Serving:
  - serving cards;
  - assignment detail for ordinary serving users;
  - confirmation timestamps only if the copy choice is clear in the same slice.

Do not attempt broad staff report/table cleanup in the first slice unless it is a very low-risk one-line use of the same helper after the member paths are complete.

## 5. Non-Goals

- No model changes.
- No migrations.
- No timezone setting changes.
- No calendar recurrence changes.
- No event scheduling logic changes.
- No sorting, filtering, or query behavior changes.
- No form input format changes.
- No user-level timezone preference.
- No frontend library.
- No JavaScript date formatting.
- No Church Structure implementation changes.
- No ServiceEvent, Bible Study, My Serving, or TeamAssignment business-rule changes.

## 6. Risk Notes

- Keep the change display-only. Sorting and filtering must remain based on stored datetimes and existing query logic.
- Do not mutate stored datetimes or reinterpret historical values.
- Do not change form widgets, input parsing, or recurring event creation defaults.
- Avoid mixing this UX polish with scheduling logic, cancellation lifecycle, audience visibility, role assignment, or confirmation workflows.
- Be careful with staff/manage pages that intentionally use compact operational formats like `Y-m-d H:i`; changing those may be a separate workflow decision.
- Confirm timezone expectations before adding any future user-level timezone support. Current settings are app-wide, not per user.

## 7. Implementation Milestones

- DATETIME-UX.1B: Add the shared filter/helper and update Today, Church Gatherings, Bible Study member surfaces, and My Serving member surfaces.
- DATETIME-UX.1C: Optional staff/report/table formatting pass for operational surfaces after member-facing behavior is settled.
- DATETIME-UX.1D: Optional user timezone preference, far future only and only after a separate product/design decision.

## 8. Tests To Add Later

DATETIME-UX.1B should include focused tests for:

- EN datetime output.
- ZH datetime output.
- Timezone-aware input conversion.
- Today event datetime display.
- Today Bible Study datetime display.
- ServiceEvent list/detail datetime display.
- BibleStudyMeeting detail datetime display.
- My Serving card datetime display.
- Assignment detail datetime display if included.
- No sorting/filtering behavior change.

## 9. Verification Recommendation For DATETIME-UX.1B

Run the normal code-change checks for the implementation slice:

- `E:\bible-reading\_venvs\bible-reading-codex-312\Scripts\python.exe manage.py makemigrations --check`
- `E:\bible-reading\_venvs\bible-reading-codex-312\Scripts\python.exe manage.py check`
- Targeted tests for the new helper and changed member views/templates.
- `git diff --check`

Browser/mobile QA should be narrow: Today, Church Gathering detail, Bible Study meeting detail, and My Serving cards in both EN and ZH where practical.
