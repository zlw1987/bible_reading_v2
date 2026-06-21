"""Guarded cleanup for legacy structure parent/context FK links.

LEGACY-OBJECT-LINKS.1A. Dry-run is the default. Apply mode clears legacy
parent/context FK links that are already fully represented by the
``ChurchStructureUnit`` hierarchy:

* ``SmallGroup.district`` (small group -> district), and
* ``District.ministry_context`` (district -> ministry context).

A link is cleared only when both the child and parent legacy objects map to
active ``ChurchStructureUnit`` rows of the expected unit types and the child
unit's ``parent`` already equals the parent legacy object's mapped unit. In
that case the legacy FK is redundant with ``ChurchStructureUnit.parent`` and
clearing it does not change the migrated runtime (audience-row + hierarchy)
behaviour or any staff/member display label.

The legacy ``ServiceEvent.ministry_context`` display FK was removed in
SERVICE-EVENT-CONTEXT.1C, so this command no longer scans or reports
ServiceEvent rows. Host / Language display now uses
``ServiceEvent.host_language_unit`` plus the audience-derived structure
fallback.

This command never deletes ``SmallGroup`` / ``District`` / ``MinistryContext``
rows, never removes fields, runs no schema migration, and switches no runtime
source of truth. It only nulls eligible legacy FK fields.
"""

from dataclasses import dataclass

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounts.models import ChurchStructureUnit, District, SmallGroup


CONFIRM_FLAG = "confirm_legacy_structure_parent_link_cleanup"
CONFIRM_OPTION = "--confirm-legacy-structure-parent-link-cleanup"


_STAT_KEYS = (
    "small_groups_checked",
    "small_group_district_links_present",
    "small_group_district_links_eligible",
    "small_group_district_links_would_clear",
    "small_group_district_links_cleared",
    "districts_checked",
    "district_ministry_context_links_present",
    "district_ministry_context_links_eligible",
    "district_ministry_context_links_would_clear",
    "district_ministry_context_links_cleared",
    "skipped_not_nullable",
    "skipped_missing_mapping",
    "skipped_inactive_unit",
    "skipped_wrong_unit_type",
    "skipped_parent_mismatch",
    "remaining_small_group_district_links_after_operation",
    "remaining_district_ministry_context_links_after_operation",
)


@dataclass(frozen=True)
class ClearPlan:
    """A single eligible legacy FK link scheduled for clearing on apply."""

    model: str  # "small_group" or "district"
    object_id: int


@dataclass(frozen=True)
class DecisionLine:
    object_type: str
    object_id: int
    object_label: str
    legacy_fk: str
    mapped_child_unit: str
    mapped_parent_unit: str
    category: str
    reason: str


def _new_stats():
    return {key: 0 for key in _STAT_KEYS}


def field_is_nullable(model, field_name):
    """Return whether ``model.field_name`` is a nullable database column."""
    return bool(model._meta.get_field(field_name).null)


def _object_label(obj):
    if obj is None:
        return "(none)"
    name = getattr(obj, "name", None) or getattr(obj, "code", None) or ""
    return f"#{obj.id} {name}".strip()


def _legacy_label(obj):
    if obj is None:
        return "(none)"
    code = getattr(obj, "code", "")
    name = getattr(obj, "name", "")
    label = code or name
    if code and name and code != name:
        label = f"{code} {name}"
    return f"#{obj.id} {label}".strip()


def _unit_label(unit):
    if unit is None:
        return "(none)"
    unit_type = getattr(unit, "unit_type", "")
    return f"#{unit.id} {unit.code} [{unit_type}]".strip()


def _classify_link(child_unit, parent_unit, expected_child_type, expected_parent_type):
    """Return one of: missing_mapping, inactive_unit, wrong_unit_type,
    parent_mismatch, eligible.

    The priority order mirrors the dedicated ``skipped_*`` counters so each
    blocked link is attributed to exactly one reason.
    """
    if child_unit is None or parent_unit is None:
        return "missing_mapping"
    if not child_unit.is_active or not parent_unit.is_active:
        return "inactive_unit"
    if (
        child_unit.unit_type != expected_child_type
        or parent_unit.unit_type != expected_parent_type
    ):
        return "wrong_unit_type"
    if child_unit.parent_id != parent_unit.id:
        return "parent_mismatch"
    return "eligible"


_SKIP_COUNTER = {
    "missing_mapping": "skipped_missing_mapping",
    "inactive_unit": "skipped_inactive_unit",
    "wrong_unit_type": "skipped_wrong_unit_type",
    "parent_mismatch": "skipped_parent_mismatch",
}

_SKIP_REASON = {
    "missing_mapping": "child or parent legacy object has no ChurchStructureUnit mapping",
    "inactive_unit": "mapped child or parent ChurchStructureUnit is inactive",
    "wrong_unit_type": "mapped child or parent ChurchStructureUnit has the wrong unit_type",
    "parent_mismatch": (
        "child unit.parent does not equal the parent legacy object's mapped unit"
    ),
}


def _evaluate_link(
    *,
    stats,
    lines,
    plans,
    object_type,
    obj,
    legacy_obj,
    child_unit,
    parent_unit,
    expected_child_type,
    expected_parent_type,
    present_key,
    eligible_key,
    would_clear_key,
    plan_model,
    apply_mode,
):
    """Classify one present legacy FK link and record stats/lines/plans."""
    stats[present_key] += 1
    category = _classify_link(
        child_unit, parent_unit, expected_child_type, expected_parent_type
    )

    if category != "eligible":
        stats[_SKIP_COUNTER[category]] += 1
        lines.append(
            DecisionLine(
                object_type=object_type,
                object_id=obj.id,
                object_label=_object_label(obj),
                legacy_fk=_legacy_label(legacy_obj),
                mapped_child_unit=_unit_label(child_unit),
                mapped_parent_unit=_unit_label(parent_unit),
                category="skipped",
                reason=f"{category}: {_SKIP_REASON[category]}",
            )
        )
        return

    stats[eligible_key] += 1
    if apply_mode:
        decision_category = "cleared"
        reason = "eligible: legacy link cleared (redundant with ChurchStructureUnit.parent)"
    else:
        stats[would_clear_key] += 1
        decision_category = "would_clear"
        reason = "eligible: redundant with ChurchStructureUnit.parent"
    plans.append(ClearPlan(model=plan_model, object_id=obj.id))
    lines.append(
        DecisionLine(
            object_type=object_type,
            object_id=obj.id,
            object_label=_object_label(obj),
            legacy_fk=_legacy_label(legacy_obj),
            mapped_child_unit=_unit_label(child_unit),
            mapped_parent_unit=_unit_label(parent_unit),
            category=decision_category,
            reason=reason,
        )
    )


def _scan(*, apply_mode=False, lock=False):
    stats = _new_stats()
    lines = []
    plans = []

    small_group_nullable = field_is_nullable(SmallGroup, "district")
    district_nullable = field_is_nullable(District, "ministry_context")

    # --- A. SmallGroup.district ------------------------------------------
    groups = (
        SmallGroup.objects.select_related(
            "church_structure_unit",
            "district",
            "district__church_structure_unit",
        )
        .order_by("name", "id")
    )
    if lock:
        groups = groups.select_for_update()
    for group in groups:
        stats["small_groups_checked"] += 1
        if group.district_id is None:
            continue
        if not small_group_nullable:
            stats["small_group_district_links_present"] += 1
            stats["skipped_not_nullable"] += 1
            lines.append(
                DecisionLine(
                    object_type="SmallGroup.district",
                    object_id=group.id,
                    object_label=_object_label(group),
                    legacy_fk=_legacy_label(group.district),
                    mapped_child_unit=_unit_label(group.church_structure_unit),
                    mapped_parent_unit=_unit_label(
                        group.district.church_structure_unit
                    ),
                    category="skipped",
                    reason="not_nullable: SmallGroup.district cannot be cleared",
                )
            )
            continue
        _evaluate_link(
            stats=stats,
            lines=lines,
            plans=plans,
            object_type="SmallGroup.district",
            obj=group,
            legacy_obj=group.district,
            child_unit=group.church_structure_unit,
            parent_unit=group.district.church_structure_unit,
            expected_child_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            expected_parent_type=ChurchStructureUnit.UNIT_DISTRICT,
            present_key="small_group_district_links_present",
            eligible_key="small_group_district_links_eligible",
            would_clear_key="small_group_district_links_would_clear",
            plan_model="small_group",
            apply_mode=apply_mode,
        )

    # --- B. District.ministry_context ------------------------------------
    districts = (
        District.objects.select_related(
            "church_structure_unit",
            "ministry_context",
            "ministry_context__church_structure_unit",
        )
        .order_by("name", "id")
    )
    if lock:
        districts = districts.select_for_update()
    for district in districts:
        stats["districts_checked"] += 1
        if district.ministry_context_id is None:
            continue
        if not district_nullable:
            stats["district_ministry_context_links_present"] += 1
            stats["skipped_not_nullable"] += 1
            lines.append(
                DecisionLine(
                    object_type="District.ministry_context",
                    object_id=district.id,
                    object_label=_object_label(district),
                    legacy_fk=_legacy_label(district.ministry_context),
                    mapped_child_unit=_unit_label(district.church_structure_unit),
                    mapped_parent_unit=_unit_label(
                        district.ministry_context.church_structure_unit
                    ),
                    category="skipped",
                    reason="not_nullable: District.ministry_context cannot be cleared",
                )
            )
            continue
        _evaluate_link(
            stats=stats,
            lines=lines,
            plans=plans,
            object_type="District.ministry_context",
            obj=district,
            legacy_obj=district.ministry_context,
            child_unit=district.church_structure_unit,
            parent_unit=district.ministry_context.church_structure_unit,
            expected_child_type=ChurchStructureUnit.UNIT_DISTRICT,
            expected_parent_type=ChurchStructureUnit.UNIT_MINISTRY_CONTEXT,
            present_key="district_ministry_context_links_present",
            eligible_key="district_ministry_context_links_eligible",
            would_clear_key="district_ministry_context_links_would_clear",
            plan_model="district",
            apply_mode=apply_mode,
        )

    return stats, lines, plans


def _finalize_remaining(stats):
    stats["remaining_small_group_district_links_after_operation"] = (
        SmallGroup.objects.filter(district__isnull=False).count()
    )
    stats["remaining_district_ministry_context_links_after_operation"] = (
        District.objects.filter(ministry_context__isnull=False).count()
    )


def run_audit():
    """Run one read-only dry-run pass; mutates nothing."""
    stats, lines, _plans = _scan(apply_mode=False)
    _finalize_remaining(stats)
    return stats, lines


def apply_cleanup():
    """Clear eligible legacy parent/context FK links inside a transaction."""
    with transaction.atomic():
        stats, lines, plans = _scan(apply_mode=True, lock=True)
        for plan in plans:
            if plan.model == "small_group":
                group = SmallGroup.objects.select_for_update().get(id=plan.object_id)
                group.district = None
                group.save(update_fields=["district"])
                stats["small_group_district_links_cleared"] += 1
            elif plan.model == "district":
                district = District.objects.select_for_update().get(id=plan.object_id)
                district.ministry_context = None
                district.save(update_fields=["ministry_context"])
                stats["district_ministry_context_links_cleared"] += 1
        _finalize_remaining(stats)
    return stats, lines


def _format_decision_line(line):
    return (
        f"  {line.object_type} {line.object_label} | legacy_fk: {line.legacy_fk} "
        f"| child_unit: {line.mapped_child_unit} "
        f"| parent_unit: {line.mapped_parent_unit} "
        f"| {line.category}: {line.reason}"
    )


class Command(BaseCommand):
    help = (
        "Dry-run-first cleanup for legacy structure parent/context FK links "
        "(LEGACY-OBJECT-LINKS.1A). Apply mode clears only SmallGroup.district "
        "and District.ministry_context links that are already represented by "
        "ChurchStructureUnit.parent. It deletes no rows, removes no fields, runs "
        "no schema migration, and switches no runtime source of truth."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help=(
                "Actually clear eligible legacy parent/context FK links. "
                f"Requires {CONFIRM_OPTION}."
            ),
        )
        parser.add_argument(
            CONFIRM_OPTION,
            action="store_true",
            dest=CONFIRM_FLAG,
            help="Required with --apply to confirm this legacy link cleanup.",
        )
        parser.add_argument(
            "--verbose",
            action="store_true",
            help="Print per-link cleanup decisions.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help=(
                "Limit verbose printed decisions to N rows per object type. Does "
                "not limit scan or apply scope."
            ),
        )

    def handle(self, *args, **options):
        if options["limit"] is not None and options["limit"] < 0:
            raise CommandError("--limit must be zero or greater.")

        apply_mode = options["apply"]
        confirmed = options[CONFIRM_FLAG]
        if apply_mode and not confirmed:
            raise CommandError(
                f"--apply requires {CONFIRM_OPTION}; no legacy structure "
                "parent/context FK links were cleared."
            )

        if apply_mode:
            stats, lines = apply_cleanup()
        else:
            stats, lines = run_audit()

        self._print_report(
            stats,
            lines,
            verbose=options["verbose"],
            verbose_limit=options["limit"],
            apply_mode=apply_mode,
            confirmed=confirmed,
        )

    def _print_report(
        self,
        stats,
        lines,
        *,
        verbose,
        verbose_limit,
        apply_mode,
        confirmed,
    ):
        write = self.stdout.write
        data_mutated = bool(
            stats["small_group_district_links_cleared"]
            or stats["district_ministry_context_links_cleared"]
        )

        if apply_mode:
            header = "Legacy structure parent/context link cleanup (LEGACY-OBJECT-LINKS.1A, APPLY mode)"
        else:
            header = "Legacy structure parent/context link cleanup (LEGACY-OBJECT-LINKS.1A, dry-run only)"
        write(header)
        write("=" * 88)
        write(f"mode: {'apply' if apply_mode else 'dry-run'}")
        write(f"apply_option_present: {str(apply_mode).lower()}")
        write(f"confirmation_option_present: {str(confirmed).lower()}")
        for key in _STAT_KEYS:
            write(f"{key}: {stats[key]}")
        write(f"data_mutated: {str(data_mutated).lower()}")
        write("runtime_mutated: false")
        write("schema_mutated: false")
        write("")
        if apply_mode:
            write(
                "Apply mode: cleared only eligible SmallGroup.district and "
                "District.ministry_context links already represented by "
                "ChurchStructureUnit.parent. No rows were deleted, no fields were "
                "removed, no schema migration ran, and no runtime source of truth "
                "was switched."
            )
        else:
            write(
                "Dry-run only: no SmallGroup.district or District.ministry_context "
                "link was changed; no rows were deleted and no schema or runtime "
                "behaviour changed."
            )

        if not verbose:
            return

        write("")
        write("per-link decisions:")
        if not lines:
            write("  (no legacy links scanned)")
            return

        for object_type in (
            "SmallGroup.district",
            "District.ministry_context",
        ):
            group_lines = [line for line in lines if line.object_type == object_type]
            write(f"{object_type} ({len(group_lines)}):")
            if not group_lines:
                write("  (none)")
                continue
            shown = group_lines if verbose_limit is None else group_lines[:verbose_limit]
            for line in shown:
                write(_format_decision_line(line))
            if verbose_limit is not None and len(group_lines) > len(shown):
                remaining = len(group_lines) - len(shown)
                write(
                    f"  (stopped at --limit {verbose_limit}; "
                    f"{remaining} more decision(s) not printed)"
                )
