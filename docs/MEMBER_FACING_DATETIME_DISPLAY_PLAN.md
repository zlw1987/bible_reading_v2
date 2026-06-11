# DATETIME-UX.1A Member-Facing Datetime Display Consistency Plan

## Status

- DATETIME-UX.1A docs-only plan is complete.
- DATETIME-UX.1B is complete: the shared `member_datetime` filter is applied to Today, Church Gatherings, Bible Study member surfaces, and My Serving member surfaces.
- DATETIME-UX.1C docs-only staff/report/table formatting audit and plan is complete; implementation remains future and separately approvable.
- DATETIME-UX.1D user timezone preference remains far-future only.

## 1. Current-State Audit

### Member-facing raw datetime output

This audit describes the pre-DATETIME-UX.1B baseline, when member-facing surfaces often rendered Django datetime objects directly and produced raw or locale-agnostic output instead of ordinary EN/ZH reading copy.

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

DATETIME-UX.1B updated member-facing surfaces only:

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

## 7. DATETIME-UX.1C Staff / Report / Table Audit Plan

Status: docs-only audit and plan complete. This section does not authorize code, template, test, model, migration, timezone, query, sorting, filtering, or business-rule changes.

### Why this is separate from member-facing display

DATETIME-UX.1B intentionally optimized ordinary member reading copy. `member_datetime` is appropriate for pastoral, human-readable surfaces such as Today, Church Gatherings detail/list, Bible Study member pages, and My Serving.

Staff/admin/report/table surfaces have different needs:

- Dense tables often need compact, scan-friendly values such as `Y-m-d H:i`.
- Operational lists may need date-first ordering cues that align with existing filters and table sorting.
- Audit/moderation timestamps may be acceptable as compact internal timestamps, especially when staff compare records quickly.
- Some raw Django datetime output is acceptable only when it is truly internal/debug-like or Django Admin-owned. Raw datetime output in user-visible staff pages should be reviewed because it can be inconsistent and harder to scan.

Do not automatically apply `member_datetime` to staff tables. The future implementation should choose either an existing explicit compact format or a small staff-facing display helper only where that improves operational clarity without changing data behavior.

### Future audit targets

Target surfaces to review later:

- Staff membership request pages:
  - `templates/accounts/staff/membership_request_list.html`
  - `templates/accounts/staff/membership_request_detail.html`
  - Current compact `date:"Y-m-d H:i"` usage may already be acceptable.
- Staff moderation/report pages:
  - `templates/accounts/staff/moderation_queue.html`
  - `templates/prayers/staff/prayer_reports.html`
  - `templates/comments/staff/reflection_reports.html`
  - Prefer compact audit timestamps where the page is staff-only; do not introduce pastoral/member phrasing into operational moderation tables.
- Ministry operations staff/table pages:
  - `templates/ministry/assignment_list.html`
  - `templates/ministry/team_schedule.html`
  - `templates/ministry/assignment_detail.html` when viewed by staff/assignment managers
  - Existing `Y-m-d H:i` table formatting should be treated as an intentional baseline unless the future slice finds inconsistent raw output on the same surface.
- Bible Study staff/manage pages:
  - `templates/studies/bible_study_schedule_detail.html`
  - `templates/studies/bible_study_lesson_detail.html`
  - `templates/studies/bible_study_lesson_manage_list.html`
  - `templates/studies/bible_study_meeting_manage_list.html`
  - These include likely raw datetime candidates such as `published_at`, `prestudy_datetime`, and `meeting_datetime`.
- Staff overview/report-style surfaces:
  - `/staff/` overview templates under `templates/accounts/staff/`
  - any future report/export pages that surface event, meeting, confirmation, report, hidden, created, updated, or published timestamps.

Likely view areas to inspect during implementation, only to understand context and targeted tests:

- `accounts.views` staff overview, membership request, and moderation queue views.
- `ministry.views` assignment list, assignment detail, and team schedule views.
- `studies.views` Bible Study schedule/guide/meeting management views.
- `events.views` only if a staff-only event table/report surface is touched later.

### Explicit non-goals for 1C implementation

- No changes to datetime storage.
- No timezone setting changes.
- No user timezone preference.
- No query, ordering, filtering, or sorting behavior changes.
- No form widget, input format, or parsing changes.
- No event generation, recurrence, Bible Study meeting generation, or scheduling behavior changes.
- No permission, visibility, audience, or source-of-truth changes.
- No model or migration changes.
- No Community Activities work except a future/out-of-scope note if a later report page needs the same convention.
- No broad staff UI redesign.

### Recommended implementation strategy

1. Keep the future slice display-only and staff-surface-only.
2. Inventory raw staff-visible datetime outputs first, then group them by surface type:
   - operational schedule/table values;
   - audit/moderation/report timestamps;
   - detail-page labels;
   - Django Admin or internal-only values.
3. Preserve existing compact `date:"Y-m-d H:i"` table formats unless there is a clear inconsistency on the same surface.
4. For raw staff-visible values, prefer explicit compact formatting before introducing a new helper. Add a helper only if repeated staff/report formatting rules become duplicated across several templates.
5. Keep member-facing surfaces on `member_datetime`; do not replace them with staff/table formatting.
6. Keep sorting/filtering tied to stored datetimes and existing querysets. Formatting must not become a sorting or filtering mechanism.
7. Update only the templates and tests directly needed for the selected future slice.

### Recommended targeted tests for future implementation

Run only focused tests for surfaces changed in the future implementation:

- For membership request timestamps: targeted `accounts` tests covering staff request list/detail rendered timestamp text.
- For moderation/report timestamps: targeted `accounts`, `prayers`, or `comments` staff queue/report tests for the changed page.
- For ministry assignment/team schedule tables: targeted `ministry` tests for assignment list, assignment detail, or team schedule timestamp rendering.
- For Bible Study manage pages: targeted `studies` tests for schedule detail, lesson detail/manage list, or meeting manage list timestamp rendering.
- For any new staff helper, add helper-level tests for aware datetime, `None`, and expected compact output.

The future implementation should still run the standard short code-change checks:

- `E:\bible-reading\_venvs\bible-reading-codex-312\Scripts\python.exe manage.py makemigrations --check`
- `E:\bible-reading\_venvs\bible-reading-codex-312\Scripts\python.exe manage.py check`
- the exact targeted test methods/classes touched by the slice
- `git diff --check`

Browser/mobile QA should be narrow and only for pages whose visible formatting changes. Staff tables should be checked for wrapping/scanability on mobile only when the changed surface has a meaningful mobile staff path.

## 8. Implementation Milestones

- DATETIME-UX.1B: Complete; added the shared filter/helper and updated Today, Church Gatherings, Bible Study member surfaces, and My Serving member surfaces.
- DATETIME-UX.1C: Docs-only audit and plan complete; future implementation remains optional and separately approvable.
- DATETIME-UX.1D: Optional user timezone preference, far future only and only after a separate product/design decision.

## 9. Regression Coverage and Future Tests

DATETIME-UX.1B added focused regression coverage for:

- EN datetime output.
- ZH datetime output.
- None-safe helper behavior.
- Today Church Gathering datetime display.
- Today Bible Study datetime display.
- ServiceEvent detail/list datetime display.
- BibleStudyMeeting detail datetime display.
- My Serving card/detail datetime display.
- No sorting/filtering behavior change.

Future DATETIME-UX.1C implementation work should add targeted coverage for each staff/report/table surface it changes. Future DATETIME-UX.1D work should add targeted coverage for any user-timezone behavior it changes.

## 10. Verification Recommendation For Future Datetime Work

For future datetime work or regression checks, run the normal code-change checks for the affected slice:

- `E:\bible-reading\_venvs\bible-reading-codex-312\Scripts\python.exe manage.py makemigrations --check`
- `E:\bible-reading\_venvs\bible-reading-codex-312\Scripts\python.exe manage.py check`
- Targeted tests for the helper and changed datetime display surfaces.
- `git diff --check`

Browser/mobile QA should stay narrow: the changed datetime display surfaces in both EN and ZH where practical.
