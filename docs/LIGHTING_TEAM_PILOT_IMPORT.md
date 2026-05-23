# Lighting Team Pilot Import

## Purpose

This import supports limited Lighting Team pilot data using the existing generic Ministry Operations models:

- ServiceEvent
- MinistryTeam
- TeamMembership
- TeamAssignment
- TeamAssignmentMember

It is intended to validate the workflow:

ServiceEvent -> MinistryTeam -> TeamAssignment -> My Serving confirmation.

## Boundary

This is a generic MinistryTeam pilot only.

Do not add:
- LightingTeam model
- Lighting Team-specific routes
- Automatic scheduling
- Availability matrix
- Swap requests
- Reminder automation
- Checklist engine
- Service review notes
- Full historical import
- Phone numbers or sensitive contact import
- Private notes, prayer notes, Zoom passwords, or counseling information
- Google Doc content copied into the database

Use links for playbooks and training documents instead of importing their content.

## CSV Columns

Required:
- `event_date`
- `event_type`
- `event_title`
- `assigned_member`

Optional:
- `event_title_en`
- `start_time`
- `end_time`
- `service_detail`
- `special_event_note`
- `worship_team`
- `member_email`
- `playbook_link`

Forbidden sensitive columns:
- `phone_number`
- `private_notes`
- `prayer_notes`
- `zoom_password`

If any forbidden column appears, the command rejects the file.

Accepted `event_type` values:
- `sunday_service`
- `bible_study`
- `special_meeting`
- `conference`
- `gospel_music`
- `baptism`
- `other`

Dates use `YYYY-MM-DD`. Times use `HH:MM`. Use `event_title` for the Chinese/local title and optional `event_title_en` for the English title.

## Example CSV

See `docs/examples/lighting_team_pilot_template.csv`.

```csv
event_date,event_type,event_title,event_title_en,start_time,end_time,service_detail,special_event_note,worship_team,assigned_member,member_email,playbook_link
2026-07-05,sunday_service,主日崇拜,Sunday Service,10:00,11:30,Main sanctuary service,,Worship Team A,Example Helper,helper@example.com,https://example.com/lighting-playbook
```

## Dry Run

Run this first:

```powershell
python manage.py import_lighting_pilot --csv docs/examples/lighting_team_pilot_template.csv --dry-run
```

Dry-run validates the CSV, prints what would be created or reused, and does not save database changes.

## Import

After reviewing dry-run output:

```powershell
python manage.py import_lighting_pilot --csv path/to/lighting_pilot.csv
```

Rows older than today are rejected by default to protect against accidental full historical imports. Use `--allow-past` only for deliberate testing or repair work.

## Rollback Note

Back up the database before importing real pilot data.

For the SQLite development database, copy `db.sqlite3` before import.

## Manual QA After Import

- Check the Lighting Team Ministry Team detail.
- Check the generated TeamAssignment detail.
- Check My Serving for an assigned user with a linked account.
- Confirm the assignment from My Serving.
- Verify an unrelated user cannot see the assignment on My Serving.
- Verify no sensitive contact fields or private notes were imported.
