"""Backfill missing Reflection structure snapshots (READING-STRUCT.1B).

Group-shared ``ReflectionComment`` visibility is structure-native since
CS-CORE.4G.2: it keys off ``structure_unit_at_post`` plus the viewer's active
primary ``ChurchStructureMembership``. Group reflections written before that
snapshot existed carry only the legacy ``small_group_at_post`` mirror and no
``structure_unit_at_post`` — so they are currently invisible to everyone under
the live gate (READING-STRUCT.1A audit surfaced these as
``reflections_legacy_only_no_valid_snapshot``).

This command backfills ``structure_unit_at_post`` for those rows, **only** when
the legacy ``small_group_at_post`` resolves to an active ``UNIT_SMALL_GROUP``
``ChurchStructureUnit`` — the same validity rule the runtime read gate uses.

Contract (mirrors the ServiceEvent / Bible Study backfill pattern):

- **Dry-run by default.** It writes nothing unless ``--apply`` is passed.
- It only ever sets ``structure_unit_at_post`` on rows where it is currently
  null. It never overwrites an existing snapshot, never mutates
  ``small_group_at_post`` / ``Profile.small_group`` or any other legacy field,
  and never changes ``visibility`` / ``is_hidden`` / ``is_deleted`` or any
  runtime privacy behavior.
- It is idempotent: a second run finds the just-backfilled rows already
  snapshot-backed and reports ``skipped_existing_snapshot`` for them, with zero
  further writes.

It performs **no runtime source switch**; it only prepares data for the later
structure-native runtime switch. See
``docs/READING_STRUCTURE_RUNTIME_MIGRATION_PLAN.md``.
"""

from collections import OrderedDict

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from comments.models import ReflectionComment
from reading.structure_runtime_readiness import (
    REASON_INACTIVE_UNIT,
    REASON_MISSING_MAPPING,
    REASON_WRONG_UNIT_TYPE,
    RESOLVABLE,
    _unit_resolution_reason,
)


# Counter keys, in display order.
COUNTER_KEYS = (
    "reflections_checked",
    "skipped_existing_snapshot",
    "would_backfill",
    "backfilled",
    "missing_legacy_group",
    "missing_mapping",
    "inactive_unit",
    "wrong_unit_type",
    "validation_error",
    "legacy_fields_mutated",
)

# Unresolved buckets: a nonzero value means a row could not be safely backfilled
# and needs manual data repair. ``would_backfill`` is intentionally *not* a
# problem (it is safely backfillable, and becomes ``backfilled`` under --apply).
ISSUE_KEYS = (
    "missing_legacy_group",
    "missing_mapping",
    "inactive_unit",
    "wrong_unit_type",
    "validation_error",
)

# Detail buckets printed under --verbose.
DETAIL_KEYS = (
    "would_backfill",
    "backfilled",
    "missing_legacy_group",
    "missing_mapping",
    "inactive_unit",
    "wrong_unit_type",
    "validation_error",
)


def _group_label(group):
    if group is None:
        return ""
    return f"#{group.id} {group.name}"


def _unit_label(unit):
    if unit is None:
        return ""
    return f"#{unit.id} {unit.code} ({unit.unit_type})"


def run_backfill(*, apply=False, limit=None, reflection_id=None):
    """Resolve and (optionally) backfill missing reflection structure snapshots.

    Returns a dict with counters, per-bucket detail rows, and the list of
    nonzero issue buckets. Writes only when ``apply`` is true, and only ever sets
    a currently-null ``structure_unit_at_post``.
    """
    stats = OrderedDict((key, 0) for key in COUNTER_KEYS)
    details = OrderedDict((key, []) for key in DETAIL_KEYS)

    # Scan group-visible, non-hidden, non-deleted reflections — the same
    # population the READING-STRUCT.1A audit reports — so the backfill clears the
    # exact ``reflections_legacy_only_no_valid_snapshot`` blocker it measures.
    comments = (
        ReflectionComment.objects.filter(
            visibility=ReflectionComment.VISIBILITY_GROUP,
            is_hidden=False,
            is_deleted=False,
        )
        .select_related("small_group_at_post__church_structure_unit", "structure_unit_at_post")
        .order_by("id")
    )
    if reflection_id is not None:
        comments = comments.filter(id=reflection_id)

    processed = 0
    for comment in comments.iterator():
        if limit is not None and processed >= limit:
            break
        processed += 1
        stats["reflections_checked"] += 1

        # Never overwrite an existing snapshot.
        if comment.structure_unit_at_post_id is not None:
            stats["skipped_existing_snapshot"] += 1
            continue

        legacy_group = comment.small_group_at_post
        if legacy_group is None:
            stats["missing_legacy_group"] += 1
            details["missing_legacy_group"].append(
                f"  comment_id={comment.id} | legacy_small_group="
            )
            continue

        unit = legacy_group.church_structure_unit
        reason = _unit_resolution_reason(unit)
        if reason == REASON_MISSING_MAPPING:
            stats["missing_mapping"] += 1
            details["missing_mapping"].append(
                f"  comment_id={comment.id} | legacy_small_group={_group_label(legacy_group)}"
            )
            continue
        if reason == REASON_INACTIVE_UNIT:
            stats["inactive_unit"] += 1
            details["inactive_unit"].append(
                f"  comment_id={comment.id} | legacy_small_group={_group_label(legacy_group)}"
                f" | unit={_unit_label(unit)}"
            )
            continue
        if reason == REASON_WRONG_UNIT_TYPE:
            stats["wrong_unit_type"] += 1
            details["wrong_unit_type"].append(
                f"  comment_id={comment.id} | legacy_small_group={_group_label(legacy_group)}"
                f" | unit={_unit_label(unit)}"
            )
            continue

        # reason == RESOLVABLE: the row is safely backfillable.
        assert reason == RESOLVABLE
        if not apply:
            stats["would_backfill"] += 1
            details["would_backfill"].append(
                f"  comment_id={comment.id} | legacy_small_group={_group_label(legacy_group)}"
                f" | -> unit={_unit_label(unit)}"
            )
            continue

        try:
            with transaction.atomic():
                comment.structure_unit_at_post = unit
                # Only the snapshot column is written; legacy fields and privacy
                # columns are never touched.
                comment.save(update_fields=["structure_unit_at_post"])
        except Exception as exc:  # pragma: no cover - defensive guard
            stats["validation_error"] += 1
            details["validation_error"].append(
                f"  comment_id={comment.id} | error={exc}"
            )
            continue

        stats["backfilled"] += 1
        details["backfilled"].append(
            f"  comment_id={comment.id} | legacy_small_group={_group_label(legacy_group)}"
            f" | -> unit={_unit_label(unit)}"
        )

    issues = [key for key in ISSUE_KEYS if stats[key]]
    return {
        "stats": stats,
        "details": details,
        "issues": issues,
        "applied": apply,
    }


class Command(BaseCommand):
    help = (
        "Backfill missing ReflectionComment.structure_unit_at_post snapshots for "
        "group-visible reflections whose legacy small_group_at_post resolves to an "
        "active small-group ChurchStructureUnit. Dry-run by default; pass --apply "
        "to write. Never overwrites an existing snapshot, never mutates legacy "
        "fields, and never changes runtime visibility."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Write the resolved snapshots. Without it the command is read-only.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Process at most N group-visible reflections.",
        )
        parser.add_argument(
            "--reflection-id",
            type=int,
            default=None,
            help="Restrict to a single ReflectionComment id.",
        )
        parser.add_argument(
            "--verbose",
            action="store_true",
            help="Print capped per-row detail for each non-skipped bucket.",
        )
        parser.add_argument(
            "--detail-limit",
            type=int,
            default=20,
            help="Cap the number of verbose detail rows printed (default 20).",
        )
        parser.add_argument(
            "--fail-on-issues",
            action="store_true",
            help=(
                "Exit with an error when any unresolved issue bucket is nonzero "
                "(missing legacy group / mapping, inactive unit, wrong unit type, "
                "validation error). Still respects dry-run / --apply for writes."
            ),
        )

    def handle(self, *args, **options):
        if options["limit"] is not None and options["limit"] < 0:
            raise CommandError("--limit must be zero or greater.")
        if options["detail_limit"] < 0:
            raise CommandError("--detail-limit must be zero or greater.")

        result = run_backfill(
            apply=options["apply"],
            limit=options["limit"],
            reflection_id=options["reflection_id"],
        )
        self._print_report(
            result,
            verbose=options["verbose"],
            detail_limit=options["detail_limit"],
        )

        if options["fail_on_issues"] and result["issues"]:
            blocking = [f"{key}={result['stats'][key]}" for key in result["issues"]]
            raise CommandError(
                "Reflection structure-snapshot backfill issues detected "
                "(--fail-on-issues): " + ", ".join(blocking)
            )

    def _print_report(self, result, *, verbose, detail_limit):
        write = self.stdout.write
        stats = result["stats"]
        mode = "APPLY (writes)" if result["applied"] else "DRY-RUN (read-only)"

        write("Reflection structure-snapshot backfill (READING-STRUCT.1B)")
        write("=" * 76)
        write(f"mode: {mode}")
        write("counters:")
        for key in COUNTER_KEYS:
            write(f"  {key}: {stats[key]}")
        write("  runtime_switched: false")
        write(
            "  => issues present: "
            + (", ".join(result["issues"]) if result["issues"] else "none")
        )
        write("")
        if result["applied"]:
            write(
                "APPLY: only ReflectionComment.structure_unit_at_post was set on "
                "rows where it was null. No legacy small_group / profile field, and "
                "no visibility / hidden / deleted column, was changed. No runtime "
                "source was switched. Reflection body text is never printed."
            )
        else:
            write(
                "DRY-RUN: no row was changed. Re-run with --apply to write the "
                "resolved snapshots. Reflection body text is never printed."
            )

        if not verbose:
            return

        write("")
        write("details (capped):")
        printed = 0
        stopped = False
        for bucket in DETAIL_KEYS:
            rows = result["details"][bucket]
            write(f"{bucket}:")
            if not rows:
                write("  (none)")
                continue
            for row in rows:
                if printed >= detail_limit:
                    stopped = True
                    break
                write(row)
                printed += 1
            if stopped:
                break
        if stopped:
            write(f"  (verbose output stopped at --detail-limit {detail_limit})")
