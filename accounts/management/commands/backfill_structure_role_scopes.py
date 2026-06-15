"""Backfill ``ChurchRoleAssignment.structure_unit`` from legacy role scopes (CS-CORE.2D-C).

Data-migration tooling only. This command populates the canonical
``structure_unit`` scope on existing role assignments when it can be *safely*
derived from the legacy ``district`` / ``small_group`` scope fields (their mapped
``church_structure_unit``). It never changes runtime permission behavior, never
clears the legacy ``district`` / ``small_group`` fields, and never consults
ordinary ``ChurchStructureMembership`` (belonging does not decide role scope).

Default behavior is dry-run only: nothing is written unless ``--apply`` is
passed. Readiness agrees with the read-only ``audit_structure_role_scopes``
diagnostic (CS-CORE.2D-A): a scoped row is eligible only when its legacy scope
maps to an active structure unit of a compatible type. Ambiguous / inconsistent
rows fail closed and are skipped.

The command is idempotent: once an eligible row's ``structure_unit`` is set it
matches the derived legacy unit on a later run and is left unchanged.
"""

from collections import OrderedDict

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounts.models import ChurchRoleAssignment

# Reuse the audit's legacy-scope resolution + wrong-type rules so the backfill and
# the read-only audit agree on what is "ready" (no behavior drift).
from accounts.management.commands.audit_structure_role_scopes import (
    _format_assignment_line,
    _is_wrong_type_for_scope,
    _legacy_scope_unit,
)


COUNTER_KEYS = (
    "assignments_checked",
    "global_assignments",
    "already_set_matching",
    "already_set_no_legacy_mapping",
    "mismatch_existing_structure_unit",
    "legacy_small_group_scope_mapped",
    "legacy_small_group_scope_unmapped",
    "legacy_district_scope_mapped",
    "legacy_district_scope_unmapped",
    "legacy_scope_structure_unit_inactive",
    "legacy_scope_structure_unit_wrong_type",
    "missing_structure_unit_ready",
    "skipped_not_ready",
    "would_update",
    "updated",
    "dry_run",
)

# Verbose example categories worth showing for admin review.
EXAMPLE_KEYS = (
    "would_update",
    "updated",
    "mismatch_existing_structure_unit",
    "skipped_not_ready",
    "already_set_no_legacy_mapping",
    "global_assignment",
)


def _new_stats():
    return OrderedDict((key, 0) for key in COUNTER_KEYS)


def run_backfill(*, apply, user_id=None, role=None, assignment_id=None):
    """Resolve and (optionally) write structure-unit backfills.

    Returns ``{"stats": ..., "details": ...}``. When ``apply`` is false nothing
    is written. Never clears legacy scope fields and never reads membership.
    """
    stats = _new_stats()
    stats["dry_run"] = 0 if apply else 1
    details = OrderedDict((key, []) for key in EXAMPLE_KEYS)

    assignments = (
        ChurchRoleAssignment.objects.filter(is_active=True)
        .select_related(
            "user",
            "district",
            "district__church_structure_unit",
            "small_group",
            "small_group__church_structure_unit",
            "structure_unit",
        )
        .order_by("user__username", "role", "scope_type", "id")
    )
    if user_id is not None:
        assignments = assignments.filter(user_id=user_id)
    if role is not None:
        assignments = assignments.filter(role=role)
    if assignment_id is not None:
        assignments = assignments.filter(id=assignment_id)

    pending_updates = []  # (assignment, derived_unit) tuples, ready to write.

    for assignment in assignments:
        stats["assignments_checked"] += 1
        scope = assignment.scope_type
        legacy_unit = _legacy_scope_unit(assignment)

        # Descriptive mapped/unmapped tally for scoped rows (matches the audit).
        if scope == ChurchRoleAssignment.SCOPE_SMALL_GROUP:
            if legacy_unit is not None:
                stats["legacy_small_group_scope_mapped"] += 1
            else:
                stats["legacy_small_group_scope_unmapped"] += 1
        elif scope == ChurchRoleAssignment.SCOPE_DISTRICT:
            if legacy_unit is not None:
                stats["legacy_district_scope_mapped"] += 1
            else:
                stats["legacy_district_scope_unmapped"] += 1

        # Global roles keep structure_unit=None; never write.
        if scope == ChurchRoleAssignment.SCOPE_GLOBAL:
            stats["global_assignments"] += 1
            details["global_assignment"].append(
                _format_assignment_line(assignment, None, "global_assignment")
            )
            continue

        # Already has an explicit structure_unit: never overwrite.
        if assignment.structure_unit_id:
            if legacy_unit is None:
                stats["already_set_no_legacy_mapping"] += 1
                details["already_set_no_legacy_mapping"].append(
                    _format_assignment_line(
                        assignment, None, "already_set_no_legacy_mapping"
                    )
                )
            elif assignment.structure_unit_id == legacy_unit.id:
                stats["already_set_matching"] += 1
            else:
                stats["mismatch_existing_structure_unit"] += 1
                details["mismatch_existing_structure_unit"].append(
                    _format_assignment_line(
                        assignment, legacy_unit, "mismatch_existing_structure_unit"
                    )
                )
            continue

        # Missing structure_unit on a scoped row: evaluate readiness, fail closed.
        if legacy_unit is None:
            stats["skipped_not_ready"] += 1
            details["skipped_not_ready"].append(
                _format_assignment_line(assignment, None, "legacy_scope_unmapped")
            )
            continue
        if not legacy_unit.is_active:
            stats["legacy_scope_structure_unit_inactive"] += 1
            stats["skipped_not_ready"] += 1
            details["skipped_not_ready"].append(
                _format_assignment_line(
                    assignment, legacy_unit, "legacy_scope_structure_unit_inactive"
                )
            )
            continue
        if _is_wrong_type_for_scope(legacy_unit, scope):
            stats["legacy_scope_structure_unit_wrong_type"] += 1
            stats["skipped_not_ready"] += 1
            details["skipped_not_ready"].append(
                _format_assignment_line(
                    assignment, legacy_unit, "legacy_scope_structure_unit_wrong_type"
                )
            )
            continue

        # Ready: structure_unit can be safely derived from the legacy scope.
        stats["missing_structure_unit_ready"] += 1
        if apply:
            pending_updates.append((assignment, legacy_unit))
            stats["updated"] += 1
            details["updated"].append(
                _format_assignment_line(assignment, legacy_unit, "updated")
            )
        else:
            stats["would_update"] += 1
            details["would_update"].append(
                _format_assignment_line(assignment, legacy_unit, "would_update")
            )

    if apply and pending_updates:
        # Direct, validated-on-creation rows: write only structure_unit via a
        # queryset update so legacy district / small_group fields are untouched.
        with transaction.atomic():
            for assignment, derived_unit in pending_updates:
                ChurchRoleAssignment.objects.filter(pk=assignment.pk).update(
                    structure_unit=derived_unit
                )

    return {"stats": stats, "details": details}


class Command(BaseCommand):
    help = (
        "CS-CORE.2D-C: backfill ChurchRoleAssignment.structure_unit from mapped "
        "legacy district / small_group role scopes. Dry-run by default; pass "
        "--apply to write. Never changes runtime permission behavior, never clears "
        "legacy scope fields, and never reads ChurchStructureMembership."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Actually write derived structure_unit values. Without it, dry-run.",
        )
        parser.add_argument(
            "--verbose",
            action="store_true",
            help="Print capped example rows per outcome category.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Maximum number of verbose example rows to print per category.",
        )
        parser.add_argument(
            "--user-id",
            type=int,
            default=None,
            help="Only process active role assignments for this user id.",
        )
        parser.add_argument(
            "--role",
            choices=[choice for choice, _ in ChurchRoleAssignment.ROLE_CHOICES],
            default=None,
            help="Only process active role assignments with this role.",
        )
        parser.add_argument(
            "--assignment-id",
            type=int,
            default=None,
            help="Only process the active role assignment with this id.",
        )

    def handle(self, *args, **options):
        if options["limit"] is not None and options["limit"] < 0:
            raise CommandError("--limit must be zero or greater.")

        result = run_backfill(
            apply=options["apply"],
            user_id=options["user_id"],
            role=options["role"],
            assignment_id=options["assignment_id"],
        )
        self._print_report(
            result,
            apply=options["apply"],
            verbose=options["verbose"],
            limit=options["limit"],
        )

    def _print_report(self, result, *, apply, verbose, limit):
        write = self.stdout.write
        stats = result["stats"]
        mode = "apply" if apply else "dry-run"

        write("Structure-aware role-scope backfill (CS-CORE.2D-C)")
        write("=" * 76)
        write(f"MODE: {mode}")
        write("summary:")
        for key in COUNTER_KEYS:
            write(f"  {key}: {stats[key]}")
        write("")
        if apply:
            write(
                "apply mode: only structure_unit was written on ready rows; legacy "
                "district / small_group fields were not changed, no permission "
                "decision was made, and ChurchStructureMembership was never read."
            )
        else:
            write(
                "dry-run: nothing was written. Re-run with --apply to set "
                "structure_unit on the would_update rows. Legacy district / "
                "small_group fields are never changed and membership is never read."
            )

        if not verbose:
            return

        write("")
        write("examples (capped per category):")
        for category in EXAMPLE_KEYS:
            rows = result["details"][category]
            write(f"{category}:")
            if not rows:
                write("  (none)")
                continue

            printed = 0
            for row in rows:
                if limit is not None and printed >= limit:
                    write(f"  (stopped at --limit {limit})")
                    break
                write(row)
                printed += 1
