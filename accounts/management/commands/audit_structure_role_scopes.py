"""Read-only structure-aware role-scope readiness audit (CS-CORE.2D-A).

This diagnostic answers a single question: can existing ``ChurchRoleAssignment``
rows be represented by the canonical ``structure_unit`` scope so a later slice
(CS-CORE.2D-B) can switch ``get_accessible_progress_groups()`` /
``can_view_group_progress_for()`` away from legacy District / SmallGroup scopes?

It is strictly read-only. It writes nothing, has no ``--apply``, makes no
permission decision, and never consults ordinary ``ChurchStructureMembership``
(belonging does not decide role scope). Legacy ``district`` / ``small_group``
role fields remain compatibility scope fields after this slice.
"""

from collections import OrderedDict

from django.core.management.base import BaseCommand, CommandError

from accounts.models import ChurchRoleAssignment, ChurchStructureUnit
# Diagnostic-only resolution: explicit structure_unit first, then the legacy
# district / small_group mapped unit. The runtime legacy fallback was retired in
# ROLE-RETIRE.1B, so this audit deliberately uses the diagnostic helper (not the
# runtime get_role_assignment_structure_unit) to keep inspecting what a legacy
# scope would map to for migration / backfill / rollback readiness.
from accounts.permissions import (
    resolve_role_assignment_structure_unit_for_diagnostics,
)


COUNTER_KEYS = (
    "assignments_checked",
    "global_assignments",
    "assignments_with_structure_unit",
    "assignments_missing_structure_unit",
    "legacy_small_group_scope_mapped",
    "legacy_small_group_scope_unmapped",
    "legacy_district_scope_mapped",
    "legacy_district_scope_unmapped",
    "legacy_scope_mismatch_structure_unit",
    "structure_unit_inactive",
    "structure_unit_wrong_type_for_scope",
    "assignments_ready_for_structure_scope",
    "assignments_not_ready_for_structure_scope",
)

# Verbose example categories: the "problem" rows worth showing for admin review.
EXAMPLE_KEYS = (
    "legacy_small_group_scope_unmapped",
    "legacy_district_scope_unmapped",
    "legacy_scope_mismatch_structure_unit",
    "structure_unit_inactive",
    "structure_unit_wrong_type_for_scope",
    "assignments_not_ready_for_structure_scope",
)


def _new_stats():
    return OrderedDict((key, 0) for key in COUNTER_KEYS)


def _unit_label(unit):
    if unit is None:
        return ""
    return f"#{unit.id} {unit.code}"


def _group_label(group):
    if group is None:
        return ""
    return f"#{group.id} {group.name}"


def _district_label(district):
    if district is None:
        return ""
    return f"#{district.id} {district.name}"


def _legacy_scope_unit(assignment):
    """Structure unit implied by the assignment's legacy scope fields, if any."""
    if (
        assignment.scope_type == ChurchRoleAssignment.SCOPE_SMALL_GROUP
        and assignment.small_group is not None
    ):
        return assignment.small_group.church_structure_unit
    if (
        assignment.scope_type == ChurchRoleAssignment.SCOPE_DISTRICT
        and assignment.district is not None
    ):
        return assignment.district.church_structure_unit
    return None


def _is_wrong_type_for_scope(unit, scope_type):
    if unit is None:
        return False
    if scope_type == ChurchRoleAssignment.SCOPE_SMALL_GROUP:
        return unit.unit_type != ChurchStructureUnit.UNIT_SMALL_GROUP
    if scope_type == ChurchRoleAssignment.SCOPE_DISTRICT:
        # A small-group unit is too narrow to act as a district-like scope.
        return unit.unit_type == ChurchStructureUnit.UNIT_SMALL_GROUP
    return False


def _format_assignment_line(assignment, resolved_unit, reason):
    parts = [
        f"assignment_id={assignment.id}",
        f"user_id={assignment.user_id}",
        f"username={assignment.user.get_username()}",
        f"role={assignment.role}",
        f"scope_type={assignment.scope_type}",
        f"legacy_district={_district_label(assignment.district)}",
        f"legacy_small_group={_group_label(assignment.small_group)}",
        f"structure_unit={_unit_label(assignment.structure_unit)}",
        f"resolved_scope_unit={_unit_label(resolved_unit)}",
        f"reason={reason}",
    ]
    return "  " + " | ".join(parts)


def run_audit():
    """Return read-only role-scope readiness counters and example rows.

    Never creates, edits, or deletes a row, and never makes a permission
    decision.
    """
    stats = _new_stats()
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

    for assignment in assignments:
        stats["assignments_checked"] += 1

        is_global = assignment.scope_type == ChurchRoleAssignment.SCOPE_GLOBAL
        if is_global:
            stats["global_assignments"] += 1

        if assignment.structure_unit_id:
            stats["assignments_with_structure_unit"] += 1
        else:
            stats["assignments_missing_structure_unit"] += 1

        legacy_unit = _legacy_scope_unit(assignment)
        if assignment.scope_type == ChurchRoleAssignment.SCOPE_SMALL_GROUP:
            if legacy_unit is not None:
                stats["legacy_small_group_scope_mapped"] += 1
            else:
                stats["legacy_small_group_scope_unmapped"] += 1
                details["legacy_small_group_scope_unmapped"].append(
                    _format_assignment_line(
                        assignment, None, "legacy_small_group_scope_unmapped"
                    )
                )
        elif assignment.scope_type == ChurchRoleAssignment.SCOPE_DISTRICT:
            if legacy_unit is not None:
                stats["legacy_district_scope_mapped"] += 1
            else:
                stats["legacy_district_scope_unmapped"] += 1
                details["legacy_district_scope_unmapped"].append(
                    _format_assignment_line(
                        assignment, None, "legacy_district_scope_unmapped"
                    )
                )

        # Candidate scope unit for migration readiness (explicit-first, then legacy
        # fallback). Diagnostic only — runtime no longer honors the legacy fallback.
        resolved_unit = resolve_role_assignment_structure_unit_for_diagnostics(
            assignment
        )

        mismatch = bool(
            assignment.structure_unit_id
            and legacy_unit is not None
            and assignment.structure_unit_id != legacy_unit.id
        )
        if mismatch:
            stats["legacy_scope_mismatch_structure_unit"] += 1
            details["legacy_scope_mismatch_structure_unit"].append(
                _format_assignment_line(
                    assignment, resolved_unit, "legacy_scope_mismatch_structure_unit"
                )
            )

        inactive = bool(resolved_unit is not None and not resolved_unit.is_active)
        if inactive:
            stats["structure_unit_inactive"] += 1
            details["structure_unit_inactive"].append(
                _format_assignment_line(
                    assignment, resolved_unit, "structure_unit_inactive"
                )
            )

        wrong_type = _is_wrong_type_for_scope(resolved_unit, assignment.scope_type)
        if wrong_type:
            stats["structure_unit_wrong_type_for_scope"] += 1
            details["structure_unit_wrong_type_for_scope"].append(
                _format_assignment_line(
                    assignment, resolved_unit, "structure_unit_wrong_type_for_scope"
                )
            )

        if is_global:
            ready = True
        else:
            ready = bool(
                resolved_unit is not None
                and resolved_unit.is_active
                and not wrong_type
                and not mismatch
            )

        if ready:
            stats["assignments_ready_for_structure_scope"] += 1
        else:
            stats["assignments_not_ready_for_structure_scope"] += 1
            details["assignments_not_ready_for_structure_scope"].append(
                _format_assignment_line(
                    assignment,
                    resolved_unit,
                    "assignments_not_ready_for_structure_scope",
                )
            )

    return {"stats": stats, "details": details}


class Command(BaseCommand):
    help = (
        "Read-only CS-CORE.2D-A audit of whether legacy ChurchRoleAssignment "
        "scopes can be represented by structure_unit. Writes nothing, has no "
        "apply mode, and makes no permission decision."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--verbose",
            action="store_true",
            help="Print capped example rows for not-ready / drift categories.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Maximum number of verbose example rows to print per category.",
        )

    def handle(self, *args, **options):
        if options["limit"] is not None and options["limit"] < 0:
            raise CommandError("--limit must be zero or greater.")

        audit = run_audit()
        self._print_report(
            audit,
            verbose=options["verbose"],
            limit=options["limit"],
        )

    def _print_report(self, audit, *, verbose, limit):
        write = self.stdout.write
        stats = audit["stats"]

        write("Structure-aware role-scope readiness audit (CS-CORE.2D-A, read-only)")
        write("=" * 76)
        write("summary:")
        for key in COUNTER_KEYS:
            write(f"  {key}: {stats[key]}")
        write("")
        write(
            "Audit only: no role assignment, structure unit, district, small "
            "group, profile, membership, or permission rows were changed. This "
            "command makes no progress-permission decision and ordinary "
            "ChurchStructureMembership is never used as a role-scope source."
        )

        if not verbose:
            return

        write("")
        write("examples (not-ready / drift categories only):")
        for category in EXAMPLE_KEYS:
            rows = audit["details"][category]
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
