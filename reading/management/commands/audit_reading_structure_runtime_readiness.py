"""Read-only Reading structure-runtime readiness audit command (READING-STRUCT.1A).

Thin wrapper over ``reading.structure_runtime_readiness.run_audit``. It prints a
resolvability inventory for the remaining legacy small-group data behind the
reading / reflection / progress runtime and reports whether any blocker stands in
the way of retiring the legacy ``Profile.small_group`` data. (As of
READING-STRUCT.1D the Reading runtime no longer *reads* ``Profile.small_group``;
the legacy ``ReflectionComment.small_group_at_post`` mirror was removed in
REFLECTION-MIRROR.1H, so reflection readiness now keys solely off the
structure snapshot.)

This command is **read-only**: it has no ``--apply`` and writes nothing. It does
not switch any runtime source. Use it as real-data evidence before the next
reading-structure runtime slice. See
``docs/READING_STRUCTURE_RUNTIME_MIGRATION_PLAN.md``.
"""

from django.core.management.base import BaseCommand, CommandError

from reading.structure_runtime_readiness import (
    BLOCKER_KEYS,
    MEMBERSHIP_COUNTER_KEYS,
    PROGRESS_COUNTER_KEYS,
    REFLECTION_COUNTER_KEYS,
    VERBOSE_DETAIL_KEYS,
    run_audit,
)


class Command(BaseCommand):
    help = (
        "Read-only READING-STRUCT.1A audit: inventory of remaining Reading / "
        "Reflection / Progress legacy small-group dependencies and their "
        "resolvability to active ChurchStructureUnit rows. Writes nothing and "
        "has no apply mode."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--verbose",
            action="store_true",
            help="Print capped representative rows for unresolved / blocker categories.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=20,
            help="Cap the number of verbose detail rows printed (default 20).",
        )
        parser.add_argument(
            "--fail-on-blockers",
            action="store_true",
            help=(
                "Exit with an error when any blocker category is nonzero. Still "
                "read-only."
            ),
        )

    def handle(self, *args, **options):
        if options["limit"] < 0:
            raise CommandError("--limit must be zero or greater.")

        audit = run_audit()
        self._print_report(audit, verbose=options["verbose"], limit=options["limit"])

        if options["fail_on_blockers"] and audit["blockers"]:
            blocking = [
                f"{key}={audit['stats'][key]}" for key in audit["blockers"]
            ]
            raise CommandError(
                "Reading structure-runtime readiness blockers detected "
                "(--fail-on-blockers): " + ", ".join(blocking)
            )

    def _print_report(self, audit, *, verbose, limit):
        write = self.stdout.write
        stats = audit["stats"]

        write("Reading structure-runtime readiness audit (READING-STRUCT.1A, read-only)")
        write("=" * 76)
        write(f"target_date: {audit['target_date'].isoformat()}")
        write("group reflection structure-snapshot inventory:")
        for key in REFLECTION_COUNTER_KEYS:
            write(f"  {key}: {stats[key]}")
        write("active legacy progress-group resolvability inventory:")
        for key in PROGRESS_COUNTER_KEYS:
            write(f"  {key}: {stats[key]}")
        write("user membership inventory:")
        for key in MEMBERSHIP_COUNTER_KEYS:
            write(f"  {key}: {stats[key]}")
        write("blocker categories (nonzero blocks legacy retirement / next switch):")
        for key in BLOCKER_KEYS:
            write(f"  {key}: {stats[key]}")
        write(
            "  => blockers present: "
            + (", ".join(audit["blockers"]) if audit["blockers"] else "none")
        )
        write("")
        write(
            "READ-ONLY: no reflection, profile, membership, group, unit, progress, "
            "role, permission, or reading row was changed. No runtime source was "
            "switched. Reflection body text is never printed."
        )

        if not verbose:
            return

        write("")
        write("details (unresolved / blocker categories only, capped):")
        printed = 0
        stopped = False
        for category in VERBOSE_DETAIL_KEYS:
            rows = audit["details"][category]
            write(f"{category}:")
            if not rows:
                write("  (none)")
                continue
            for row in rows:
                if printed >= limit:
                    stopped = True
                    break
                write(row)
                printed += 1
            if stopped:
                break
        if stopped:
            write(f"  (verbose output stopped at --limit {limit})")
