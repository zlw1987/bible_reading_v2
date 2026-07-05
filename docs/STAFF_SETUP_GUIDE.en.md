# Staff Setup Guide

Status: STAFF-ONLY / INTERNAL-ONLY.

This limited-trial operations guide describes shipped behavior only. It is not
a production-readiness certification or an ordinary-member help page. Do not
expose it to ordinary members. The in-app page at `/staff/setup-guide/` uses
the same staff/superuser-only access boundary as other `/staff/` surfaces.

## 1. Purpose and operating boundary

Use this guide to prepare a small, supervised trial and verify the boundaries
between belonging, audience visibility, agenda items, and serving. Record the
target environment, operator, date, enabled modules, audit result, warnings
reviewed, and smoke-test accounts. A recorded local result does not replace a
fresh check against the exact trial environment.

Current context:

- Community Activities V1 manual QA passed by user confirmation.
- Official Announcements V1 manual QA passed by user confirmation in
  `ANNOUNCEMENTS-QA-PASS.1A`.
- The latest recorded setup-readiness audit reported 0 blockers and 19
  warnings. This supports limited-trial planning only. Review the warnings and
  rerun the audit against the target database before inviting real users.

## 2. Deployment, migrations, and module enablement

1. Confirm that the intended code revision and environment-specific settings
   are deployed to the trial environment.
2. Review migration state and planned operations. Apply migrations only
   through the separately approved deployment procedure; this guide does not
   authorize a data-changing command.
3. Run the Django system check and confirm that model changes have no missing
   migration.
4. Review `CMS_ENABLED_MODULES` in the deployed settings. The shipped
   registered keys are `reading`, `prayers`, `studies`, `events`,
   `community_events`, `announcements`, and `ministry`; the default enables all
   of them. Unknown keys fail configuration validation, and `ministry` requires
   `events`.
5. Confirm the intended navigation, Today contributions, staff links, and
   module-owned Staff Overview/readiness content with both enabled and
   deliberately disabled modules.

Suggested read-only or no-write verification commands:

```powershell
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py showmigrations
python manage.py migrate --plan
python manage.py audit_trial_setup_readiness --verbose --limit 20 --fail-on-blockers
```

`audit_trial_setup_readiness` is read-only and has no `--apply` mode. `--limit`
limits examples only, not the scan.

Important limitation:

Module disablement is surface-gated, not route hard-off. It hides registered
navigation and selected module-owned surfaces/providers, but does not unload
apps, models, admin registrations, or URLs. Direct routes retain their existing
view-level permissions and visibility rules.

## 3. Accounts, Church Structure, and audience verification

- Confirm at least one usable staff or superuser account for trial operations.
  Staff authority must come from the existing permission boundary, never from
  `ChurchStructureMembership`.
- Confirm the `ChurchStructureUnit` hierarchy reflects the intended active
  church structure. Units used for audiences or memberships must be active.
- Confirm each participating ordinary member has the intended active primary
  `ChurchStructureMembership`. Resolve ambiguous multiple active primary rows
  before the trial.
- Do not create a fake `Unassigned` unit. “Unassigned” means that a user has no
  blocking active primary membership and no pending membership request; it is
  a state, not a `ChurchStructureUnit`.
- Treat membership as belonging only. It may establish the member's structure
  context for approved visibility consumers, but it grants no serving,
  coworker role, staff capability, team assignment, or Bible Study role.
- Treat every module-owned audience row as visibility configuration only.
  Audience visibility is not assignment, attendance, approval, or serving.
- For each scoped item, test with a matching ordinary member and a nonmatching
  ordinary member. Selected ancestor units include qualifying descendant
  memberships under the shipped structure-native matching rule; zero audience
  rows fail closed for ordinary users.

## 4. Official Announcements setup

Official Announcements is official staff-authored communication. Its management
workflow is staff/superuser-only. It is not event management, signup, or
serving.

1. Confirm `announcements` is enabled and the intended staff management and
   authenticated-member navigation surfaces appear.
2. As staff/superuser, create a draft with English and Chinese title/body
   content. Check supported-language display and fallback.
3. Choose one or more existing active `ChurchStructureUnit` rows with the
   audience picker. Do not invent audience units for an announcement.
4. Choose normal or check Important. Important makes an eligible item a
   Today-reminder candidate; it never bypasses audience visibility.
5. Set the publication window (`publish_start` and optional `publish_end`) and
   save the draft. Verify that future and expired windows remain hidden from
   ordinary members.
6. Publish through the shipped staff action, then verify list and detail with a
   matching ordinary member. Verify the nonmatching member cannot see the item
   and receives 404 on direct hidden-detail access.
7. Archive the announcement and confirm member list/detail visibility ends.
   Archiving preserves its audience rows.
8. For an active Important item, confirm Today shows at most one newest visible
   Important reminder and only its localized title/detail link. Confirm a
   normal announcement does not appear there.

Announcements does not add Staff Overview content, My Serving items, serving
state, notifications, `ServiceEvent`, Community Activities, signup, attendance,
or approval/request-changes behavior.

## 5. Community Activities setup

Community Activities is an independent, secondary module for signup-oriented
community and fellowship activities. It is not `ServiceEvent`, official Church
Gatherings, My Serving, or a serving system.

1. Confirm `community_events` is enabled.
2. As an eligible member with active primary membership, create a complete
   draft or submit it for review. Activity Scope is required and saves
   `CommunityActivityAudienceScope` rows using active `ChurchStructureUnit`
   choices. The optional audience note is review context, not visibility.
3. Confirm drafts remain visible only to the primary creator, linked
   co-organizers, and staff/superusers. Only the primary creator manages
   co-organizers and submits a draft; co-organizers may edit within the shipped
   draft/pending-review/changes-requested boundary.
4. As staff/superuser, use the shipped review inbox to publish, request changes
   with a note, or cancel/reject. Verify creator edits/resubmission return a
   `changes_requested` item to `pending_review`.
5. After publication, verify Activity Scope visibility with matching and
   nonmatching members.
6. Test signup, cancel, and re-signup. For capped activities, verify the final
   available slot and full-capacity refusal; cancellation frees capacity.
   These rows express attendance intent only.
7. On Today, confirm an activity appears only when the user has an active
   signup for a published, visible activity happening today. Also confirm only
   the creator's own `changes_requested` item creates the review reminder.

Community Activities adds no My Serving item, `ServiceEvent`, Church Gathering,
serving record, check-in, waitlist, notification, or Staff Overview content.
Do not use it as the official church-gathering operations model.

## 6. Bible Study V2 setup

- Use the active `BibleStudySeries` + `BibleStudyMeeting` path. Do not revive
  retired V1 `BibleStudySession` workflows.
- Configure series and meeting audiences through module-owned audience rows
  that target `ChurchStructureUnit`. Confirm generated or manually prepared
  member-visible meetings have the intended audience rows; zero-row meetings
  fail closed for ordinary users.
- Verify a matching member can see the meeting and a nonmatching member cannot.
  A visible meeting is agenda, not serving.
- Create personal Bible Study serving only by linking
  `BibleStudyMeetingRole.user` to the actual user. That explicit user-linked
  role may appear in Today and My Serving and use the shipped confirmation
  workflow.
- A display-name-only meeting role is meeting-detail fallback only. It must not
  create Today serving action or My Serving state and must never be matched to
  a user by text.

## 7. Ministry and My Serving setup

- `MinistryTeam` defines the ministry team context.
- `TeamAssignment` schedules a team for a specific event, and
  `TeamAssignmentMember` explicitly assigns a person. Only that explicit member
  row creates team-serving state for the person.
- My Serving is the dedicated personal serving and confirmation workspace. Use
  it to verify pending, today, this-week, later, and management-linked serving
  surfaces as applicable. My Serving is explicit-serving-only.
- `ChurchStructureMembership` never creates a team assignment or My Serving
  item.
- Active, date-valid lead/coordinator `MinistryTeamRoleAssignment` rows grant
  the shipped exact-team management responsibility. They may expose management
  links or leader attention, but they are long-term responsibility—not personal
  event serving—and must not appear as a personal serving assignment by
  themselves.
- Keep Bible Study serving separate: its explicit personal source is the
  linked-user `BibleStudyMeetingRole.user`, not a `TeamAssignmentMember`.

## 8. Today boundary

Today is the general, low-noise agenda and lightweight action surface. Depending
on enabled modules and the current user's data, it may include:

- today's reading and check-in state;
- visible Church Gatherings today and this week;
- visible Bible Study V2 meetings today and this week;
- the narrow Community Activities reminders described above;
- at most one visible active Important Announcement reminder; and
- personal action items or compact serving notes backed only by an explicit
  `TeamAssignmentMember` or linked-user `BibleStudyMeetingRole.user`.

Today is not a feed, a staff dashboard, or the full serving workspace. Full
serving confirmation and management remain in My Serving or the owning module.

## 9. Limited-trial verification checklist

Use separate accounts and record evidence without copying sensitive personal
data into this document.

### Platform and setup

- [ ] `python manage.py check` passes.
- [ ] `python manage.py makemigrations --check --dry-run` reports no missing
  migrations.
- [ ] `showmigrations` and `migrate --plan` match the target deployment plan;
  any apply action is separately approved.
- [ ] `CMS_ENABLED_MODULES` contains the intended dependency-valid set and its
  surface gates were checked.
- [ ] A fresh `audit_trial_setup_readiness --verbose --limit 20
  --fail-on-blockers` result was reviewed.
- [ ] Every warning has an owner, disposition, or accepted trial limitation.

### Accounts and audience

- [ ] Sample staff/superuser can reach the required management surfaces.
- [ ] Sample matching member has the intended active primary membership and can
  see scoped published content.
- [ ] Sample nonmatching member cannot see that scoped content, including by
  direct hidden-detail URL.

### Product smoke tests

- [ ] Announcement: draft, bilingual content, audience, Important, publish
  window, publish/archive, matching/nonmatching visibility, and max-one Today
  reminder pass.
- [ ] Community Activity: draft/submission, review/request changes, published
  scope visibility, signup/cancel/capacity, and narrow Today reminders pass.
- [ ] Today/My Serving: visible gathering and meeting remain agenda only;
  membership/audience alone creates no serving; explicit team and linked Bible
  Study assignments appear in the correct serving surfaces; a
  display-name-only Bible Study role does not.

## 10. Known limitations and escalation

- Disabled modules are surface-gated, not route hard-off.
- Production readiness is not claimed. This guide does not certify deployment
  security, backups, monitoring, scale, accessibility, or operational support.
- Setup-readiness warnings must be reviewed before inviting real users, even
  when blocker count is zero.
- Target-environment migration and audit evidence must be recorded separately;
  local evidence is not target-environment proof.
- New integrations, broader shared surfaces, notifications, route hard-off,
  automatic assignments, or cross-module behavior require a separate approved
  slice.

## 11. Do Not Do

- Do not create serving from `ChurchStructureMembership`.
- Do not treat audience visibility as assignment or serving.
- Do not use Community Activities for official church-gathering operations.
- Do not use Announcements for event management, signup, or serving.
- Do not claim production readiness from this guide, a QA pass, or a
  zero-blocker audit.
- Do not expose this guide to ordinary members.
- Do not infer staff authority, management responsibility, or a personal Bible
  Study role from belonging, audience rows, or display text.
- Do not implement a future integration or product expansion while following
  this operations guide.
