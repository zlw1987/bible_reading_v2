"""Read-only inventory for legacy structure object row retirement.

ROW-RETIRE.1A focuses on the remaining ``SmallGroup``, ``District``, and
``MinistryContext`` rows after runtime consumers have moved away from legacy
ordinary-member authority. The command inventories those rows and the live code
surfaces that still justify keeping the old models as a bridge.

It is deliberately read-only. It has no ``--apply`` option, writes no rows,
changes no runtime behavior, and does not recommend deleting rows blindly.
"""

from collections import Counter, OrderedDict

from django.core.management.base import BaseCommand, CommandError

from accounts.models import ChurchStructureUnit, District, MinistryContext, SmallGroup


CATEGORY_RUNTIME_AUTHORITY = "runtime authority"
CATEGORY_FINAL_TABLE_RETIREMENT = "final table-retirement blocker"
CATEGORY_DISPLAY_ONLY = "display-only"
CATEGORY_ADMIN_MAINTENANCE = "admin/emergency maintenance"
CATEGORY_DIAGNOSTIC_SUPPORT = "diagnostic/audit/backfill/cleanup support"
CATEGORY_SETUP_BRIDGE = "setup/seed/mapping bridge"
CATEGORY_TEST_FIXTURE = "historical migration/test fixture only"
CATEGORY_DEAD_STALE = "dead/stale"

CONSUMER_INVENTORY = (
    (
        "SmallGroup / District / MinistryContext model rows",
        "accounts.models",
        CATEGORY_FINAL_TABLE_RETIREMENT,
        "remaining rows block final legacy table retirement, not ordinary visibility",
    ),
    (
        "V1 BibleStudySession.small_group FK",
        "studies.models.BibleStudySession.small_group",
        CATEGORY_FINAL_TABLE_RETIREMENT,
        "schema FK blocks final SmallGroup table retirement until guarded V1 purge "
        "and a later V1 schema migration remove it",
    ),
    (
        "V1 BibleStudySession.district FK",
        "studies.models.BibleStudySession.district",
        CATEGORY_FINAL_TABLE_RETIREMENT,
        "schema FK blocks final District table retirement until guarded V1 purge "
        "and a later V1 schema migration remove it",
    ),
    (
        "SmallGroup.church_structure_unit",
        "accounts.models.SmallGroup.church_structure_unit",
        CATEGORY_SETUP_BRIDGE,
        "maps old small-group rows to canonical structure units",
    ),
    (
        "District.church_structure_unit",
        "accounts.models.District.church_structure_unit",
        CATEGORY_SETUP_BRIDGE,
        "maps old district rows to canonical structure units",
    ),
    (
        "MinistryContext.church_structure_unit",
        "accounts.models.MinistryContext.church_structure_unit",
        CATEGORY_SETUP_BRIDGE,
        "maps old ministry-context rows to canonical structure units",
    ),
    (
        "resolve_units_to_small_groups",
        "accounts.structure_selectors.resolve_units_to_small_groups",
        CATEGORY_SETUP_BRIDGE,
        "diagnostic/setup-only resolver retained while bridge rows still exist",
    ),
    # PROFILE-SG-FIELD-RETIRE.1A removed Profile.small_group together with the
    # legacy-profile selector helpers (get_user_legacy_small_group,
    # get_user_legacy_structure_unit), so they are no longer listed here.
    (
        "seed_church_structure_units",
        "accounts.management.commands.seed_church_structure_units",
        CATEGORY_SETUP_BRIDGE,
        "seed/setup bridge for initial legacy-to-structure mapping",
    ),
    (
        "Django admin legacy structure surfaces",
        "accounts.admin",
        CATEGORY_ADMIN_MAINTENANCE,
        "maintenance surface while legacy fields and models still exist",
    ),
    (
        "Staff structure mapping templates",
        "templates/accounts/staff/structure_mapping_*",
        CATEGORY_ADMIN_MAINTENANCE,
        "staff review/edit maintenance surface for bridge mappings",
    ),
    (
        "Staff/user legacy display snippets",
        "templates/accounts/staff/*, templates/reading/*, templates/studies/*",
        CATEGORY_DISPLAY_ONLY,
        "legacy names may still display as context or fallback labels",
    ),
    (
        "ServiceEvent Host / Language display fallback",
        "events.ministry_context_display",
        CATEGORY_DISPLAY_ONLY,
        "structure-native display via ServiceEvent.host_language_unit plus an "
        "audience-derived ChurchStructureUnit fallback; the legacy "
        "ServiceEvent.ministry_context FK was removed in "
        "SERVICE-EVENT-CONTEXT.1C",
    ),
    (
        "Group progress compatibility group list",
        "accounts.permissions, reading.group_progress_shadow",
        CATEGORY_DISPLAY_ONLY,
        "progress UI still names legacy SmallGroup rows after membership-core gating",
    ),
    (
        "Bible Study V2 structure-native generation diagnostics",
        "studies management commands/docs",
        CATEGORY_DIAGNOSTIC_SUPPORT,
        "normal V2 generation is structure-native and not a SmallGroup/District "
        "table-retirement blocker; remaining references are audit context",
    ),
    (
        "Legacy retirement/readiness commands",
        "accounts/events/reading/studies management commands",
        CATEGORY_DIAGNOSTIC_SUPPORT,
        "read-only audits and dry-run-first cleanup/backfill support",
    ),
    (
        "Historical migrations and focused fixtures",
        "*/migrations, *_test*.py",
        CATEGORY_TEST_FIXTURE,
        "migration history and controlled tests retain model references",
    ),
)

STATS_KEYS = (
    "small_groups_checked",
    "districts_checked",
    "ministry_contexts_checked",
    "small_groups_with_mapping_unit",
    "districts_with_mapping_unit",
    "ministry_contexts_with_mapping_unit",
    "wrong_type_mapping_units",
    "inactive_mapping_units",
    "unmapped_rows",
    "live_runtime_consumers_found",
    "display_consumers_found",
    "admin_consumers_found",
    "diagnostic_tooling_consumers_found",
    "setup_seed_consumers_found",
    "test_fixture_consumers_found",
    "historical_migration_consumers_found",
    "dead_stale_consumers_found",
    "candidate_rows_for_future_archive",
    "candidate_rows_for_future_delete",
    "final_table_retirement_blocker_rows",
    "rows_requiring_mapping_bridge_decision",
    "rows_requiring_special_handling",
)

EXPECTED_UNIT_TYPES = {
    "SmallGroup": ChurchStructureUnit.UNIT_SMALL_GROUP,
    "District": ChurchStructureUnit.UNIT_DISTRICT,
    "MinistryContext": ChurchStructureUnit.UNIT_MINISTRY_CONTEXT,
}


def _new_stats():
    return OrderedDict((key, 0) for key in STATS_KEYS)


def _unit_label(unit):
    if unit is None:
        return "unit=(none)"
    return "unit_id={id} unit_code={code} unit_type={unit_type} unit_active={active}".format(
        id=unit.id,
        code=unit.code,
        unit_type=unit.unit_type,
        active=str(unit.is_active).lower(),
    )


def _object_label(object_type, obj):
    if object_type == "SmallGroup":
        return f"object_type=SmallGroup object_id={obj.id} object_name={obj.name}"
    if object_type == "District":
        return f"object_type=District object_id={obj.id} object_name={obj.name}"
    return (
        "object_type=MinistryContext "
        f"object_id={obj.id} object_code={obj.code} object_name={obj.name}"
    )


def _mapping_state(object_type, unit):
    if unit is None:
        return "unmapped"
    if not unit.is_active:
        return "inactive"
    if unit.unit_type != EXPECTED_UNIT_TYPES[object_type]:
        return "wrong_type"
    return "active_expected_type"


def _is_special_unassigned_mapping(object_type, obj, unit):
    if object_type != "District" or unit is None:
        return False
    name = (obj.name or "").lower()
    code = (unit.code or "").upper()
    return (
        code == "UNASSIGNED-GROUPS"
        or "unassigned" in name
        or "unassigned" in code.lower()
    ) and unit.unit_type == ChurchStructureUnit.UNIT_CUSTOM


def _recommendation_for(state, *, is_special):
    if is_special:
        return (
            "special-handling: treat as a placeholder or holding bucket; decide "
            "whether to archive/delete the legacy row or replace the bridge, and "
            "do not convert the mapped unit to a real district blindly"
        )
    if state == "active_expected_type":
        return (
            "future-archive-candidate: keep temporarily as bridge/admin/"
            "diagnostic context until a final row/table retirement slice is approved"
        )
    if state == "unmapped":
        return (
            "mapping-decision-required: row cannot prove a canonical structure "
            "identity; review before archive/delete"
        )
    if state == "inactive":
        return (
            "special-handling: mapped unit is inactive; review whether bridge, "
            "archive, or deletion is appropriate"
        )
    return (
        "special-handling: mapped unit type does not match the legacy object; "
        "review before archive/delete"
    )


def _reason_for(state, *, is_special):
    if is_special:
        return "legacy unassigned/custom holding-bucket mapping"
    if state == "active_expected_type":
        return "mapped to an active canonical structure unit of the expected type"
    if state == "unmapped":
        return "no church_structure_unit mapping"
    if state == "inactive":
        return "mapped church_structure_unit is inactive"
    return "mapped church_structure_unit has an unexpected unit_type"


def _scan_row(stats, details, object_type, obj, unit):
    state = _mapping_state(object_type, unit)
    is_special = _is_special_unassigned_mapping(object_type, obj, unit)
    stats["final_table_retirement_blocker_rows"] += 1

    if state == "unmapped":
        stats["unmapped_rows"] += 1
    else:
        stats["rows_requiring_mapping_bridge_decision"] += 1
        if object_type == "SmallGroup":
            stats["small_groups_with_mapping_unit"] += 1
        elif object_type == "District":
            stats["districts_with_mapping_unit"] += 1
        else:
            stats["ministry_contexts_with_mapping_unit"] += 1

    if state == "inactive":
        stats["inactive_mapping_units"] += 1
    if state == "wrong_type":
        stats["wrong_type_mapping_units"] += 1

    if is_special or state in {"inactive", "wrong_type"}:
        stats["rows_requiring_special_handling"] += 1
    elif state == "active_expected_type":
        stats["candidate_rows_for_future_archive"] += 1

    line = (
        "{object_label} {unit_label} category={category} "
        "diagnostic_state={diagnostic_state} reason={reason} "
        "final_retirement_recommendation={recommendation}".format(
            object_label=_object_label(object_type, obj),
            unit_label=_unit_label(unit),
            category=CATEGORY_FINAL_TABLE_RETIREMENT,
            diagnostic_state=state,
            reason=_reason_for(state, is_special=is_special),
            recommendation=_recommendation_for(state, is_special=is_special),
        )
    )
    if is_special or state in {"inactive", "wrong_type", "unmapped"}:
        details.insert(0, line)
    else:
        details.append(line)


def _scan_rows(stats, details):
    small_groups = (
        SmallGroup.objects.select_related("church_structure_unit")
        .all()
        .order_by("id")
    )
    for group in small_groups:
        stats["small_groups_checked"] += 1
        _scan_row(stats, details, "SmallGroup", group, group.church_structure_unit)

    districts = (
        District.objects.select_related("church_structure_unit").all().order_by("id")
    )
    for district in districts:
        stats["districts_checked"] += 1
        _scan_row(
            stats,
            details,
            "District",
            district,
            district.church_structure_unit,
        )

    contexts = (
        MinistryContext.objects.select_related("church_structure_unit")
        .all()
        .order_by("id")
    )
    for context in contexts:
        stats["ministry_contexts_checked"] += 1
        _scan_row(
            stats,
            details,
            "MinistryContext",
            context,
            context.church_structure_unit,
        )


def _scan_consumers(stats):
    counts = Counter(category for _name, _path, category, _reason in CONSUMER_INVENTORY)
    stats["live_runtime_consumers_found"] = counts[CATEGORY_RUNTIME_AUTHORITY]
    stats["display_consumers_found"] = counts[CATEGORY_DISPLAY_ONLY]
    stats["admin_consumers_found"] = counts[CATEGORY_ADMIN_MAINTENANCE]
    stats["diagnostic_tooling_consumers_found"] = counts[CATEGORY_DIAGNOSTIC_SUPPORT]
    stats["setup_seed_consumers_found"] = counts[CATEGORY_SETUP_BRIDGE]
    stats["test_fixture_consumers_found"] = counts[CATEGORY_TEST_FIXTURE]
    stats["historical_migration_consumers_found"] = counts[CATEGORY_TEST_FIXTURE]
    stats["dead_stale_consumers_found"] = counts[CATEGORY_DEAD_STALE]


def run_audit():
    """Run one read-only legacy object-row retirement inventory."""
    stats = _new_stats()
    details = []
    _scan_consumers(stats)
    _scan_rows(stats, details)
    return {
        "stats": stats,
        "details": details,
        "consumer_inventory": CONSUMER_INVENTORY,
        "runtime_mutated": False,
        "data_mutated": False,
        "schema_mutated": False,
    }


def _blocking_items(stats):
    blockers = []
    if stats["live_runtime_consumers_found"]:
        blockers.append(
            ("live_runtime_consumers_found", stats["live_runtime_consumers_found"])
        )
    if stats["final_table_retirement_blocker_rows"]:
        blockers.append(
            (
                "final_table_retirement_blocker_rows",
                stats["final_table_retirement_blocker_rows"],
            )
        )
    if stats["rows_requiring_special_handling"]:
        blockers.append(
            ("rows_requiring_special_handling", stats["rows_requiring_special_handling"])
        )
    return blockers


class Command(BaseCommand):
    help = (
        "ROW-RETIRE.1A read-only inventory for remaining legacy SmallGroup, "
        "District, and MinistryContext object rows. Writes nothing and has no "
        "--apply option."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--verbose",
            action="store_true",
            help="Print capped row examples and the live consumer inventory.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Maximum number of verbose row examples to print.",
        )
        parser.add_argument(
            "--fail-on-blockers",
            action="store_true",
            help=(
                "Exit nonzero when ordinary runtime consumers, remaining final "
                "table-retirement rows, or row special-handling blockers are "
                "found. Still read-only."
            ),
        )

    def handle(self, *args, **options):
        if options["limit"] is not None and options["limit"] < 0:
            raise CommandError("--limit must be zero or greater.")

        audit = run_audit()
        self._print_report(audit, verbose=options["verbose"], limit=options["limit"])

        blockers = _blocking_items(audit["stats"])
        if options["fail_on_blockers"] and blockers:
            raise CommandError(
                "Legacy object row retirement blockers present "
                "(--fail-on-blockers): "
                + ", ".join(f"{key}={value}" for key, value in blockers)
            )

    def _print_report(self, audit, *, verbose, limit):
        write = self.stdout.write
        stats = audit["stats"]

        write(
            "Legacy structure object row retirement inventory "
            "(ROW-RETIRE.1A, read-only)"
        )
        write("=" * 78)
        write("runtime_mutated: false")
        write("data_mutated: false")
        write("schema_mutated: false")
        write("apply_option_present: false")
        write("")
        write("summary counters:")
        for key in STATS_KEYS:
            write(f"  {key}: {stats[key]}")

        write("")
        write("ordinary_member_runtime_dependency: none_found")
        write(
            "legacy_object_rows_are: final table-retirement blockers, not "
            "ordinary-member runtime blockers"
        )
        write(
            "canonical_structure_tree: ChurchStructureUnit; "
            "canonical_belonging: ChurchStructureMembership"
        )
        write(
            "legacy_rows_status: compatibility/mapping/admin/diagnostic bridge "
            "until a later approved row/table retirement slice"
        )
        write(
            "legacy_bible_study_v1_schema_status: BibleStudySession.small_group "
            "blocks SmallGroup table retirement and BibleStudySession.district "
            "blocks District table retirement until future approved V1 purge and "
            "schema removal; there is no V1 MinistryContext FK."
        )

        blockers = _blocking_items(stats)
        write("")
        write("blockers:")
        if blockers:
            for key, value in blockers:
                write(f"  {key}: {value}")
            write("retirement_readiness: BLOCKED")
        else:
            write("  (none)")
            write("retirement_readiness: READY_FOR_ROW_DECISION")

        if not verbose:
            return

        write("")
        write("consumer inventory:")
        for name, path, category, reason in audit["consumer_inventory"]:
            write(
                f"  consumer={name} path={path} category={category} reason={reason}"
            )

        write("")
        write("row examples:")
        rows = audit["details"]
        shown = rows if limit is None else rows[:limit]
        for row in shown:
            write(f"  {row}")
        if not shown:
            write("  (none)")
        if limit is not None and len(rows) > len(shown):
            write(f"  (stopped at --limit {limit}; {len(rows) - len(shown)} more)")
