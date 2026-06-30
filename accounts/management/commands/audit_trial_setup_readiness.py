"""Read-only pre-user-trial setup readiness audit command (SETUP-READINESS.1A).

Thin CLI wrapper over ``accounts.trial_setup_readiness.run_audit``. It prints a
setup/data readiness snapshot across the core modules so a co-worker can tell,
before inviting real users to a trial, whether the core surfaces (audience
visibility, ministry/serving, Bible Study) are set up well enough to work.

This command is **read-only**: it has no ``--apply``, writes nothing, repairs no
rows, creates no defaults, infers no serving from membership/visibility, and
changes no permission. It is not a production-deployment claim. See
``docs/TRIAL_SETUP_READINESS_RUNBOOK.md``.
"""

from django.core.management.base import BaseCommand, CommandError

from accounts.trial_setup_readiness import COUNTER_LABELS, run_audit


class Command(BaseCommand):
    help = (
        "Read-only SETUP-READINESS.1A audit: a pre-user-trial setup/data "
        "readiness snapshot across Church Structure, Ministry Teams, "
        "TeamAssignment / My Serving, Bible Study serving, audience visibility, "
        "and permission/admin signals, classified as blockers / warnings / info. "
        "Writes nothing, has no apply mode, and repairs no data."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--verbose",
            action="store_true",
            help="Print capped example rows for nonzero blocker / warning categories.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=20,
            help="Cap the number of verbose example rows printed per category (default 20).",
        )
        parser.add_argument(
            "--fail-on-blockers",
            action="store_true",
            help="Exit non-zero when any blocker count > 0. Still read-only.",
        )

    def handle(self, *args, **options):
        if options["limit"] < 0:
            raise CommandError("--limit must be zero or greater.")

        audit = run_audit()
        self._print_report(
            audit,
            verbose=options["verbose"],
            limit=options["limit"],
        )

        if options["fail_on_blockers"] and audit["blocker_count"] > 0:
            raise CommandError(
                "Trial setup readiness blockers detected (--fail-on-blockers): "
                f"blockers={audit['blocker_count']}"
            )

    def _label(self, key):
        return COUNTER_LABELS.get(key, key)

    def _print_report(self, audit, *, verbose, limit):
        write = self.stdout.write

        write("Pre-user-trial setup readiness audit (SETUP-READINESS.1A, read-only)")
        write("=" * 76)
        write("mode: read-only (no --apply exists; no data was changed)")
        write(
            "scope: this is a SETUP/DATA readiness snapshot, NOT a production-"
            "deployment claim"
        )
        write(f"target_date: {audit['target_date'].isoformat()}")
        write(f"as_of: {audit['now'].isoformat()}")
        write("")

        for section in audit["sections"]:
            self._print_section(section, verbose=verbose, limit=limit)

        write("permission / serving boundary confirmation (static, read-only):")
        for note in audit["permission_notes"]:
            write(f"  - {note}")
        write("")

        write(
            "READ-ONLY: no user, ChurchStructureUnit, ChurchStructureMembership, "
            "ChurchRoleAssignment, MinistryTeam, TeamAssignment, "
            "TeamAssignmentMember, ServiceEvent, ServiceEventAudienceScope, "
            "BibleStudyMeeting, BibleStudyMeetingAudienceScope, or "
            "BibleStudyMeetingRole row was created, updated, or deleted. No "
            "permission, membership, serving, audience, or visibility was "
            "changed. No --apply mode exists."
        )
        write("")

        write(f"blockers: {audit['blocker_count']}")
        write(f"warnings: {audit['warning_count']}")
        write(f"recommendation: {audit['recommendation']}")

    def _print_section(self, section, *, verbose, limit):
        write = self.stdout.write
        write(section.title)
        write("-" * len(section.title))

        if section.info:
            write("  info:")
            for key, count in section.info.items():
                write(f"    {self._label(key)}: {count}")

        if section.blockers:
            write("  blockers:")
            for key, count in section.blockers.items():
                write(f"    {self._label(key)}: {count}")

        if section.warnings:
            write("  warnings:")
            for key, count in section.warnings.items():
                write(f"    {self._label(key)}: {count}")

        if verbose:
            self._print_section_details(section, limit=limit)

        write("")

    def _print_section_details(self, section, *, limit):
        write = self.stdout.write
        # Only categories with a nonzero count carry detail rows; print them in
        # blocker-then-warning order for the categories that have examples.
        ordered_keys = list(section.blockers.keys()) + list(section.warnings.keys())
        for key in ordered_keys:
            rows = section.details.get(key)
            if not rows:
                continue
            write(f"  examples [{self._label(key)}]:")
            for index, row in enumerate(rows):
                if index >= limit:
                    write(f"    (stopped at --limit {limit}; {len(rows)} total)")
                    break
                write(f"    {row}")
