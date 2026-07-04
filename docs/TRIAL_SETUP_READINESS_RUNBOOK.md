# Pre-User-Trial Setup Readiness Runbook (SETUP-READINESS.1A)

This runbook describes `audit_trial_setup_readiness`, a single **read-only**
management command that summarizes setup/data readiness across the core modules
**before** inviting real users / co-workers to a trial.

It answers one practical question: *if I invite people now, will the core
surfaces (audience visibility, ministry/serving, Bible Study) actually work, or
are there setup gaps that would break the trial or quietly hide content?*

## What this is — and is not

- It is a **pre-user-trial setup/data readiness snapshot**, run on demand.
- It is **read-only**: no `--apply`, no data mutation, no migrations, no model
  changes, no repair/backfill/auto-fix, no permission changes.
- It does **not** infer serving from visibility or membership. Belonging
  (`ChurchStructureMembership`) and serving (`TeamAssignmentMember` /
  `BibleStudyMeetingRole`) stay separate, exactly as in runtime.
- It is **not** a production-deployment claim. A clean run means the target data
  has no high-confidence trial blockers at audit time; it does not certify
  deployment, security, scale, or correctness.

## Limited trial readiness closure (July 2026)

Community Activities V1 is QA-passed by user confirmation, and the latest
setup-readiness audit reports **0 blockers** and **19 warnings**. The project is
usable for a limited trial with the documented setup/data warnings below. This
is not a production deployment claim.

The recorded audit command was:

```powershell
python manage.py audit_trial_setup_readiness --verbose --limit 20 --fail-on-blockers
```

Recorded result:

- recommendation: `USABLE FOR A LIMITED TRIAL` — no blockers, but review the
  warnings because setup gaps may degrade the trial experience;
- 2 active non-staff users have no active primary membership;
- 6 assignable ministry teams have no role profile;
- 3 teams are missing a required active Lead;
- 4 assignable teams have no active members;
- 4 upcoming required-team coverage gaps remain.

The Community Activities QA pass covered draft/collaboration, review lifecycle,
visibility, signup/cancel/capacity, low-noise Today reminders, no My Serving
contamination, no serving records or `ServiceEvent` relationship, and the
limited-trial browser smoke path. `python manage.py check`,
`python manage.py makemigrations --check --dry-run`, and `git diff --check`
also passed. `community_events` migrations through `0006` are applied, and
`migrate --plan` reported no planned operations.

This closure authorizes no new Community Activities features or integrations.
The module remains independent from `ServiceEvent` and My Serving; membership
or audience visibility never implies serving.

## Delegated belonging readiness checkpoint

`GROUP-MEMBERSHIP-MANAGE.1A` and `GROUP-MEMBERSHIP-REQUEST.1B` are complete and
QA-passed. My Units now gives authorized small-group/ancestor leads and staff a
small-group belonging workflow: add a user only when there is no current/future
active primary membership and no pending request, end an active membership, and
approve/reject a pending requested row for a managed small group. The global
staff membership-request queue remains available.

"Unassigned" describes a user with no blocking active primary membership and no
pending request; it is not a `ChurchStructureUnit`, and setup must not create a
fake Unassigned group. Existing active-primary conflicts fail closed; a full
one-click transfer workflow remains deferred. Membership management changes
belonging/visibility context only and never grants serving, coworker roles,
permissions, TeamAssignment / My Serving, or Bible Study serving. This closes
the earlier limited-trial gap where small-group leaders had no easy way to
maintain group belonging. The audit below remains a read-only data snapshot; it
does not mutate membership rows or certify deployment.

## How to run

```powershell
E:\bible-reading\bible_reading_v2\.venv\Scripts\python.exe manage.py audit_trial_setup_readiness
```

Options:

- `--verbose` — print capped example rows for nonzero blocker / warning
  categories.
- `--limit N` — cap verbose example rows per category (default 20). Caps
  examples only; it never narrows the scan.
- `--fail-on-blockers` — exit non-zero **only** when blockers > 0. Warnings never
  cause a non-zero exit. Still strictly read-only.

The ministry-structure portion delegates to
`ministry.structure_readiness.run_audit`, so this audit reuses (and does not
contradict) the existing ministry readiness classification.

## What it checks

The report is grouped into seven labelled parts:

1. **Church Structure / membership readiness** — active users, staff/superuser
   accounts, active structure units, active primary memberships; ambiguous
   multiple active primary memberships (blocker); active non-staff users with no
   active primary membership (warning — they will not see scoped content).
2. **Ministry Teams / Ministry Structure readiness** — team inventory; multiple
   active primary parent links / parent-link cycles (blockers); unanchored
   teams, assignable teams with no role profile / no required Lead / no active
   members (warnings).
3. **TeamAssignment / My Serving readiness** — active serving assignments on a
   non-assignable unit (blocker); upcoming assignments (info); upcoming serving
   members who are display-name-only and cannot personalize My Serving
   (warning); upcoming required-team coverage gaps (warning).
4. **Bible Study meeting-serving readiness** — upcoming published meetings
   (info); upcoming meeting roles that are display-name-only and cannot
   personalize My Serving (warning).
5. **ServiceEvent / Bible Study audience visibility readiness** — upcoming
   published events / member-visible meetings (info); those with **zero audience
   rows** (blockers — ordinary users fail closed and see nothing).
6. **Permission / admin setup signals** — active staff / superusers, church role
   assignments (info); no active staff or superuser account at all (warning — no
   one can manage the trial).
7. **Final recommendation** — `blockers: N`, `warnings: N`, and a plain-language
   recommendation.

## Blockers vs warnings

- **Blocker** — a high-confidence issue that would break a core trial flow.
  Examples: a published, upcoming, member-visible event/meeting with zero
  audience rows (ordinary users fail closed); an active serving assignment on a
  non-assignable ministry unit; ambiguous multiple active primary memberships.
  `--fail-on-blockers` exits non-zero only when blockers > 0.
- **Warning** — a setup gap that may be acceptable for a trial but is worth
  fixing. Examples: an assignable team with no role profile / no required Lead;
  a serving slot filled by a display-name-only person who cannot personalize
  My Serving; upcoming required-team coverage gaps; active users with no active
  primary membership. Warnings never fail the command.
- **Info** — neutral counts for context only.

## Data safety

The command mutates nothing. It has no `--apply` mode, creates no defaults, and
performs no repair logic. It only reads existing rows and prints a report. It is
safe to run against local, staging, or production-target databases for a
read-only snapshot, but it makes **no** deployment or correctness guarantee.
