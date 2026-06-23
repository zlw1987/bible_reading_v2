"""Guarded dry-run-first purge gate for legacy structure object rows.

LEGACY-OBJECT-ROW-PURGE-GATE.1A prepares the final preflight path for removing
remaining ``SmallGroup``, ``District``, and ``MinistryContext`` rows. It does
not remove their tables or mapping FKs.
"""

from collections import OrderedDict

from django.apps import apps
from django.core.management.base import BaseCommand, CommandError
from django.db import DEFAULT_DB_ALIAS, transaction
from django.db.models.deletion import Collector, ProtectedError, RestrictedError

from accounts.models import ChurchStructureUnit, District, MinistryContext, SmallGroup


CONFIRM_FLAG = "--confirm-legacy-structure-object-row-retirement"
CONFIRM_OPTION = "confirm_legacy_structure_object_row_retirement"

LEGACY_MODELS = (SmallGroup, District, MinistryContext)
LEGACY_MODEL_LABELS = {model._meta.label for model in LEGACY_MODELS}

EXPECTED_UNIT_TYPES = {
    SmallGroup: ChurchStructureUnit.UNIT_SMALL_GROUP,
    District: ChurchStructureUnit.UNIT_DISTRICT,
    MinistryContext: ChurchStructureUnit.UNIT_MINISTRY_CONTEXT,
}

PROTECTED_MODEL_LABELS = OrderedDict(
    [
        ("church_structure_units", "accounts.ChurchStructureUnit"),
        ("users", "auth.User"),
        ("memberships", "accounts.ChurchStructureMembership"),
        ("roles", "accounts.ChurchRoleAssignment"),
        ("service_events", "events.ServiceEvent"),
        ("service_event_audience_scopes", "events.ServiceEventAudienceScope"),
        ("bible_study_series", "studies.BibleStudySeries"),
        ("bible_study_lessons", "studies.BibleStudyLesson"),
        ("bible_study_v2_meetings", "studies.BibleStudyMeeting"),
        ("bible_study_v2_audience_scopes", "studies.BibleStudyMeetingAudienceScope"),
        ("prayers", "prayers.PrayerRequest"),
        ("reflections", "comments.ReflectionComment"),
        ("team_assignments", "ministry.TeamAssignment"),
    ]
)


def _new_stats():
    stats = OrderedDict(
        [
            ("small_groups_matched", 0),
            ("districts_matched", 0),
            ("ministry_contexts_matched", 0),
            ("small_groups_mapped", 0),
            ("districts_mapped", 0),
            ("ministry_contexts_mapped", 0),
            ("small_groups_unmapped", 0),
            ("districts_unmapped", 0),
            ("ministry_contexts_unmapped", 0),
            ("small_groups_wrong_type_mapping_rows", 0),
            ("districts_wrong_type_mapping_rows", 0),
            ("ministry_contexts_wrong_type_mapping_rows", 0),
            ("small_groups_inactive_mapping_rows", 0),
            ("districts_inactive_mapping_rows", 0),
            ("ministry_contexts_inactive_mapping_rows", 0),
            ("wrong_type_mapping_rows", 0),
            ("inactive_mapping_rows", 0),
            ("special_unassigned_groups_rows", 0),
            ("unexpected_inbound_dependency_rows", 0),
            ("collector_field_update_rows", 0),
            ("collector_fast_delete_rows", 0),
            ("collector_protected_rows", 0),
            ("collector_restricted_rows", 0),
            ("legacy_rows_to_delete", 0),
            ("legacy_small_groups_to_delete", 0),
            ("legacy_districts_to_delete", 0),
            ("legacy_ministry_contexts_to_delete", 0),
            ("legacy_rows_deleted", 0),
            ("legacy_small_groups_deleted", 0),
            ("legacy_districts_deleted", 0),
            ("legacy_ministry_contexts_deleted", 0),
            ("runtime_rows_deleted", 0),
            ("data_mutated", False),
        ]
    )
    for key in PROTECTED_MODEL_LABELS:
        stats[f"protected_{key}_to_delete"] = 0
        stats[f"protected_{key}_deleted"] = 0
    return stats


def _object_label(obj):
    if isinstance(obj, SmallGroup):
        return f"object_type=SmallGroup object_id={obj.id} object_name={obj.name}"
    if isinstance(obj, District):
        return f"object_type=District object_id={obj.id} object_name={obj.name}"
    return (
        "object_type=MinistryContext "
        f"object_id={obj.id} object_code={obj.code} object_name={obj.name}"
    )


def _unit_label(unit):
    if unit is None:
        return "unit=(none)"
    return "unit_id={id} unit_code={code} unit_type={unit_type} unit_active={active}".format(
        id=unit.id,
        code=unit.code,
        unit_type=unit.unit_type,
        active=str(unit.is_active).lower(),
    )


def _model_prefix(model):
    if model is SmallGroup:
        return "small_groups"
    if model is District:
        return "districts"
    return "ministry_contexts"


def _mapping_state(model, unit):
    if unit is None:
        return "unmapped"
    if not unit.is_active:
        return "inactive"
    if unit.unit_type != EXPECTED_UNIT_TYPES[model]:
        return "wrong_type"
    return "active_expected_type"


def _is_special_unassigned_groups_row(obj):
    if not isinstance(obj, District) or obj.church_structure_unit is None:
        return False
    unit = obj.church_structure_unit
    name = (obj.name or "").lower()
    code = (unit.code or "").upper()
    return (
        code == "UNASSIGNED-GROUPS"
        or "unassigned" in name
        or "unassigned" in code.lower()
    ) and unit.unit_type == ChurchStructureUnit.UNIT_CUSTOM


def _increment_row_stats(stats, details, model, obj):
    prefix = _model_prefix(model)
    unit = obj.church_structure_unit
    state = _mapping_state(model, unit)
    special = _is_special_unassigned_groups_row(obj)

    stats[f"{prefix}_matched"] += 1
    stats["legacy_rows_to_delete"] += 1
    stats[f"legacy_{prefix}_to_delete"] += 1

    if state == "unmapped":
        stats[f"{prefix}_unmapped"] += 1
    else:
        stats[f"{prefix}_mapped"] += 1

    if state == "wrong_type":
        stats[f"{prefix}_wrong_type_mapping_rows"] += 1
        stats["wrong_type_mapping_rows"] += 1
    if state == "inactive":
        stats[f"{prefix}_inactive_mapping_rows"] += 1
        stats["inactive_mapping_rows"] += 1
    if special:
        stats["special_unassigned_groups_rows"] += 1
        details["special_unassigned_groups"].append(
            "{object_label} {unit_label} decision=special_final_retirement_row".format(
                object_label=_object_label(obj),
                unit_label=_unit_label(unit),
            )
        )


def _collect_candidates(stats, details):
    candidates_by_model = OrderedDict((model, []) for model in LEGACY_MODELS)
    for model in LEGACY_MODELS:
        rows = (
            model.objects.select_related("church_structure_unit")
            .all()
            .order_by("id")
        )
        for obj in rows:
            candidates_by_model[model].append(obj)
            _increment_row_stats(stats, details, model, obj)
    return candidates_by_model


def _label_for_model(model):
    return model._meta.label


def _queryset_count(queryset):
    try:
        return queryset.count()
    except TypeError:
        return len(queryset)


def _collector_field_update_count(collector):
    total = 0
    for updates in collector.field_updates.values():
        for objs in updates:
            total += _queryset_count(objs)
    return total


def _collector_fast_delete_count(collector):
    return sum(_queryset_count(queryset) for queryset in collector.fast_deletes)


def _protected_objects_from(error):
    return list(getattr(error, "protected_objects", []) or [])


def _restricted_objects_from(error):
    return list(getattr(error, "restricted_objects", []) or [])


def _build_collector(candidates, details):
    collector = Collector(using=DEFAULT_DB_ALIAS)
    try:
        collector.collect(candidates)
    except ProtectedError as error:
        protected = _protected_objects_from(error)
        for obj in protected:
            details["unexpected_dependencies"].append(
                f"protected_dependency model={_label_for_model(obj.__class__)} object_id={obj.pk}"
            )
        return collector, protected, []
    except RestrictedError as error:
        restricted = _restricted_objects_from(error)
        for obj in restricted:
            details["unexpected_dependencies"].append(
                f"restricted_dependency model={_label_for_model(obj.__class__)} object_id={obj.pk}"
            )
        return collector, [], restricted
    return collector, [], []


def _build_collectors(candidates_by_model, details):
    collectors = []
    all_protected = []
    all_restricted = []
    for candidates in candidates_by_model.values():
        if not candidates:
            continue
        collector, protected, restricted = _build_collector(candidates, details)
        collectors.append(collector)
        all_protected.extend(protected)
        all_restricted.extend(restricted)
    return collectors, all_protected, all_restricted


def _mark_collector_safety(stats, details, collectors, protected, restricted):
    collected_counts = OrderedDict()
    for collector in collectors:
        for model, objects in collector.data.items():
            label = _label_for_model(model)
            collected_counts[label] = collected_counts.get(label, 0) + len(objects)

        field_update_rows = _collector_field_update_count(collector)
        fast_delete_rows = _collector_fast_delete_count(collector)
        if field_update_rows:
            stats["collector_field_update_rows"] += field_update_rows
        if fast_delete_rows:
            stats["collector_fast_delete_rows"] += fast_delete_rows

    for label, count in sorted(collected_counts.items()):
        if label not in LEGACY_MODEL_LABELS:
            stats["unexpected_inbound_dependency_rows"] += count
            details["unexpected_dependencies"].append(
                f"unexpected_collected_model model={label} rows={count}"
            )

    if stats["collector_field_update_rows"]:
        details["unexpected_dependencies"].append(
            f"collector_field_updates rows={stats['collector_field_update_rows']}"
        )
    if stats["collector_fast_delete_rows"]:
        details["unexpected_dependencies"].append(
            f"collector_fast_deletes rows={stats['collector_fast_delete_rows']}"
        )

    stats["collector_protected_rows"] = len(protected)
    stats["collector_restricted_rows"] = len(restricted)
    stats["unexpected_inbound_dependency_rows"] += len(protected) + len(restricted)

    for counter_key, label in PROTECTED_MODEL_LABELS.items():
        stats[f"protected_{counter_key}_to_delete"] = collected_counts.get(label, 0)

    return not (
        stats["unexpected_inbound_dependency_rows"]
        or stats["collector_field_update_rows"]
        or stats["collector_fast_delete_rows"]
    )


def collect_plan():
    stats = _new_stats()
    details = {
        "special_unassigned_groups": [],
        "unexpected_dependencies": [],
    }
    candidates_by_model = _collect_candidates(stats, details)
    collectors, protected, restricted = _build_collectors(candidates_by_model, details)
    safe_to_apply = _mark_collector_safety(
        stats, details, collectors, protected, restricted
    )
    return {
        "stats": stats,
        "details": details,
        "collectors": collectors,
        "safe_to_apply": safe_to_apply,
    }


def _deleted_count_for_label(deleted_by_label, label):
    return deleted_by_label.get(label, 0)


def _record_delete_results(plan, deleted_by_label):
    stats = plan["stats"]
    stats["legacy_small_groups_deleted"] = _deleted_count_for_label(
        deleted_by_label, SmallGroup._meta.label
    )
    stats["legacy_districts_deleted"] = _deleted_count_for_label(
        deleted_by_label, District._meta.label
    )
    stats["legacy_ministry_contexts_deleted"] = _deleted_count_for_label(
        deleted_by_label, MinistryContext._meta.label
    )
    stats["legacy_rows_deleted"] = (
        stats["legacy_small_groups_deleted"]
        + stats["legacy_districts_deleted"]
        + stats["legacy_ministry_contexts_deleted"]
    )
    for counter_key, label in PROTECTED_MODEL_LABELS.items():
        stats[f"protected_{counter_key}_deleted"] = deleted_by_label.get(label, 0)
        stats["runtime_rows_deleted"] += deleted_by_label.get(label, 0)
    stats["data_mutated"] = bool(stats["legacy_rows_deleted"])


def apply_plan(plan):
    with transaction.atomic():
        deleted_total = 0
        deleted_by_label = {}
        for collector in plan["collectors"]:
            collector_deleted_total, collector_deleted_by_label = collector.delete()
            deleted_total += collector_deleted_total
            for label, count in collector_deleted_by_label.items():
                deleted_by_label[label] = deleted_by_label.get(label, 0) + count
    _record_delete_results(plan, deleted_by_label)
    return deleted_total


def _model_label_exists(label):
    app_label, model_name = label.split(".", 1)
    return apps.get_model(app_label, model_name, require_ready=False) is not None


class Command(BaseCommand):
    help = (
        "Dry-run-first purge/preflight for remaining legacy SmallGroup, District, "
        "and MinistryContext object rows. Apply requires an explicit confirmation "
        "flag and never deletes ChurchStructureUnit or runtime rows."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help=(
                "Delete the three legacy object row types. Requires "
                f"{CONFIRM_FLAG} and aborts if collector safety is not clean."
            ),
        )
        parser.add_argument(
            CONFIRM_FLAG,
            action="store_true",
            dest=CONFIRM_OPTION,
            help="Required together with --apply for destructive row retirement.",
        )
        parser.add_argument(
            "--verbose",
            action="store_true",
            help="Print capped special-row and unsafe-dependency examples.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Maximum number of verbose examples to print.",
        )

    def handle(self, *args, **options):
        if options["limit"] is not None and options["limit"] < 0:
            raise CommandError("--limit must be zero or greater.")

        apply_requested = options["apply"]
        confirmation_present = options[CONFIRM_OPTION]
        plan = collect_plan()

        if apply_requested and not confirmation_present:
            self._print_report(
                plan,
                apply_requested=apply_requested,
                confirmation_present=confirmation_present,
                verbose=options["verbose"],
                limit=options["limit"],
            )
            raise CommandError(f"--apply requires {CONFIRM_FLAG}.")

        if apply_requested and not plan["safe_to_apply"]:
            self._print_report(
                plan,
                apply_requested=apply_requested,
                confirmation_present=confirmation_present,
                verbose=options["verbose"],
                limit=options["limit"],
            )
            raise CommandError(
                "Unsafe legacy structure object row purge plan: unexpected "
                "collector dependencies are present."
            )

        if apply_requested:
            apply_plan(plan)

        self._print_report(
            plan,
            apply_requested=apply_requested,
            confirmation_present=confirmation_present,
            verbose=options["verbose"],
            limit=options["limit"],
        )

    def _print_report(
        self,
        plan,
        *,
        apply_requested,
        confirmation_present,
        verbose,
        limit,
    ):
        write = self.stdout.write
        stats = plan["stats"]

        write(
            "Legacy structure object row purge gate "
            "(LEGACY-OBJECT-ROW-PURGE-GATE.1A)"
        )
        write("=" * 78)
        write("dry_run: {}".format(str(not apply_requested).lower()))
        write("apply_option_present: true")
        write(f"apply_requested: {str(apply_requested).lower()}")
        write(f"confirmation_present: {str(confirmation_present).lower()}")
        write(f"safe_to_apply: {str(plan['safe_to_apply']).lower()}")
        write(f"data_mutated: {str(stats['data_mutated']).lower()}")
        write("schema_mutated: false")
        write("runtime_semantics_changed: false")
        write("prints_private_free_text: false")
        write("")
        write("summary counters:")
        for key, value in stats.items():
            rendered = str(value).lower() if isinstance(value, bool) else value
            write(f"  {key}: {rendered}")

        write("")
        write("protected deletion counters:")
        for counter_key, label in PROTECTED_MODEL_LABELS.items():
            if not _model_label_exists(label):
                continue
            write(
                "  {label}: to_delete={to_delete} deleted={deleted}".format(
                    label=label,
                    to_delete=stats[f"protected_{counter_key}_to_delete"],
                    deleted=stats[f"protected_{counter_key}_deleted"],
                )
            )

        write("")
        write(
            "delete_scope: SmallGroup, District, and MinistryContext rows only; "
            "ChurchStructureUnit rows and runtime product rows are protected."
        )
        write(
            "row_purge_boundary: separate from later model/table and "
            "church_structure_unit mapping-FK schema removal."
        )
        write(
            "unassigned_groups_boundary: UNASSIGNED-GROUPS District mappings are "
            "reported as special final-retirement decision rows."
        )
        if apply_requested:
            write("apply_result: completed")
        else:
            write(
                f"apply_result: not_run; rerun with --apply {CONFIRM_FLAG} only "
                "after reviewing this exact dry-run plan."
            )

        if not verbose:
            return

        self._print_examples(
            "special UNASSIGNED-GROUPS rows",
            plan["details"]["special_unassigned_groups"],
            limit,
        )
        self._print_examples(
            "unexpected dependencies",
            plan["details"]["unexpected_dependencies"],
            limit,
        )

    def _print_examples(self, heading, rows, limit):
        write = self.stdout.write
        write("")
        write(f"{heading}:")
        shown = rows if limit is None else rows[:limit]
        if not shown:
            write("  (none)")
            return
        for row in shown:
            write(f"  {row}")
        if limit is not None and len(rows) > len(shown):
            write(f"  (stopped at --limit {limit}; {len(rows) - len(shown)} more)")
