# Lighting Team Pilot QA Checklist

## 1. Purpose

This checklist is retained as a future QA reference for limited Lighting Team Pilot data through the generic Ministry Operations workflow:

ServiceEvent -> MinistryTeam -> TeamAssignment -> TeamAssignmentMember -> My Serving confirmation.

Do not proceed to this checklist yet. Per `docs/LIGHTING_PILOT_PREFLIGHT_REQUIREMENTS.md`, Checklist V1 remains deferred until IA, Bible Study V2 direction, import/setup behavior, bilingual data display, and member/coordinator guides are validated.

When it is reactivated, use it to verify the import command and browser workflow with future 2-3 months of data only.

This checklist does not validate automatic scheduling, availability, swap requests, reminders, or a checklist engine.

## 2. Data Boundary

- [ ] Use only future 2-3 months of schedule data.
- [ ] Do not import 2021-2026 full history.
- [ ] Do not import phone numbers.
- [ ] Do not import private notes.
- [ ] Do not import prayer notes.
- [ ] Do not import Zoom passwords.
- [ ] Do not import ShowXpress training content.
- [ ] Do not import Google Doc body content.
- [ ] Only store playbook link.
- [ ] Confirm the CSV has no forbidden sensitive columns.

## 2a. Preconditions Before This Checklist Is Used

- [ ] IA is clear: Today, Reading, Bible Study, Prayer, My Serving, and Profile are distinct user surfaces.
- [ ] My Serving is the independent serving entry point.
- [ ] Today, if used, shows only a lightweight serving summary card that links to My Serving.
- [ ] Daily Reading does not own or manage serving operations.
- [ ] Bible Study V2 direction is documented and no longer conflicts with Lighting Pilot assumptions.
- [ ] Lighting import/setup dry-run and re-run behavior is validated.
- [ ] Bilingual ServiceEvent and MinistryTeam display is validated.
- [ ] Member-facing My Serving guide is available.
- [ ] Coordinator-facing ministry assignment guide is available.
- [ ] Pilot users can complete the serving flow without checklist support.

## 3. CSV Columns

Required columns:
- `event_date`
- `event_type`
- `event_title`
- `assigned_member`

Optional columns:
- `start_time`
- `end_time`
- `service_detail`
- `special_event_note`
- `worship_team`
- `member_email`
- `playbook_link`

Forbidden columns:
- `phone_number`
- `private_notes`
- `prayer_notes`
- `zoom_password`

## 4. Pre-Import Setup

- [ ] Backup `db.sqlite3` if using local SQLite.
- [ ] Confirm users exist for members who should be linked by email.
- [ ] Confirm future event dates are correct.
- [ ] Confirm `event_type` values match accepted choices.
- [ ] Confirm `playbook_link` points to Google Doc, not copied content.
- [ ] Run `python manage.py check`.
- [ ] Do not run full suite for this docs-only checklist task.

## 5. Dry Run

- [ ] Run dry-run command.
- [ ] Confirm dry-run creates no database records.
- [ ] Review `teams_created`.
- [ ] Review `memberships_created`.
- [ ] Review `service_events_created`.
- [ ] Review `assignments_created`.
- [ ] Review `assignment_members_created`.
- [ ] Review `rows_skipped`.
- [ ] Review `rows_errors`.
- [ ] Confirm row errors are understandable.
- [ ] Confirm past rows are rejected or skipped by default.
- [ ] Confirm forbidden columns are rejected.

Command:

```bash
python manage.py import_lighting_pilot --csv path/to/file.csv --dry-run
```

## 6. Import

- [ ] Run import only after dry-run is clean.
- [ ] Confirm Lighting Team is created or reused as a generic MinistryTeam.
- [ ] Confirm `playbook_link` is set.
- [ ] Confirm TeamMembership records are created or reused.
- [ ] Confirm existing users are linked by `member_email`.
- [ ] Confirm display-name-only memberships are created only when no user exists.
- [ ] Confirm ServiceEvent records are created or reused.
- [ ] Confirm TeamAssignment records are created or reused.
- [ ] Confirm TeamAssignmentMember records are created or reused.
- [ ] Re-run import and confirm no duplicates.

Command:

```bash
python manage.py import_lighting_pilot --csv path/to/file.csv
```

## 7. Browser QA: Staff / Coordinator

- [ ] Staff can open Ministry Teams.
- [ ] Staff can open Lighting Team detail.
- [ ] Lighting Team shows playbook link.
- [ ] Lighting Team members appear.
- [ ] Staff can open Team Assignments.
- [ ] Imported assignments appear.
- [ ] Assignment detail shows ServiceEvent.
- [ ] Assignment detail shows MinistryTeam.
- [ ] Assignment detail shows assigned member.
- [ ] Assignment detail shows status.
- [ ] Assignment detail shows notes.
- [ ] Assignment detail shows confirmation state.
- [ ] No LightingTeam-specific page exists.
- [ ] No automatic scheduling UI exists.
- [ ] No availability/swap/reminder/checklist UI exists.

## 8. Browser QA: Assigned Member

- [ ] Linked user logs in.
- [ ] User can find serving details through My Serving.
- [ ] If Today shows serving at all, it is only a lightweight summary card linking to My Serving.
- [ ] User opens My Serving.
- [ ] User sees imported assignment.
- [ ] User sees event date/time.
- [ ] User sees Lighting Team.
- [ ] User sees playbook link.
- [ ] User sees non-sensitive assignment notes.
- [ ] User can confirm assignment.
- [ ] Confirmed state appears after confirmation.
- [ ] Re-confirming does not create duplicate confirmation.

## 9. Browser QA: Unrelated User

- [ ] Unrelated regular user logs in.
- [ ] User does not see Lighting Team assignments.
- [ ] User does not see another member's assignment in My Serving.
- [ ] User cannot confirm another member's assignment.
- [ ] Normal top nav has no Ministry Teams / Team Assignments / Lighting Team clutter.

## 10. Bilingual Review

- [ ] Chinese My Serving page is readable.
- [ ] Chinese assignment detail page is readable.
- [ ] English My Serving page is readable.
- [ ] English assignment detail page is readable.
- [ ] Chinese UI/data shows `主日崇拜` and `灯光组` where bilingual fields exist.
- [ ] English UI/data shows `Sunday Service` and `Lighting Team` where bilingual fields exist.
- [ ] Chinese-facing flows do not require English-only event/team labels when bilingual fields exist.
- [ ] No obvious hardcoded English leaks into Chinese pages for My Serving.
- [ ] No obvious hardcoded English leaks into Chinese pages for Team Assignment.
- [ ] No obvious hardcoded English leaks into Chinese pages for Ministry Team.
- [ ] No obvious hardcoded English leaks into Chinese pages for Confirm Assignment.
- [ ] No obvious hardcoded English leaks into Chinese pages for Playbook.
- [ ] No obvious hardcoded English leaks into Chinese pages for Assignment Notes.

## 11. Pilot Acceptance Criteria

- [ ] Dry-run clean.
- [ ] Import clean.
- [ ] No duplicate records on re-run.
- [ ] Staff/coordinator can inspect assignments.
- [ ] Assigned member can see and confirm.
- [ ] Unrelated users cannot see assignments.
- [ ] No sensitive data imported.
- [ ] No historical bulk import.
- [ ] No LightingTeam-specific model or UI.
- [ ] No scheduling algorithm.
- [ ] No checklist engine.

## 12. Decision After Pilot

If pilot passes:
- Reconsider whether Checklist V1 is still needed.

If pilot fails:
- Fix import, assignment visibility, My Serving, or confirmation flow first.
- Do not build Checklist V1 until IA, Bible Study V2 direction, import/setup, bilingual data display, member/coordinator guides, and the pilot flow are stable.

## 13. Explicit Non-Goals

- No automatic scheduling.
- No availability matrix.
- No swap request.
- No reminders.
- No checklist engine yet.
- No service review notes yet.
- No full historical import.
- No sensitive contact import.
- No Google Doc content migration.
- No LightingTeam-specific model.
