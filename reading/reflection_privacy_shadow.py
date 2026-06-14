"""Read-only reflection-privacy structure-snapshot readiness audit (CS-CORE.4G.1).

This diagnostic answers a single question: are group-shared ``ReflectionComment``
rows carrying enough stable structure-snapshot data
(``structure_unit_at_post``) to consider a future visibility shadow/switch off
``small_group_at_post``?

It is strictly read-only. It does NOT change any runtime reflection visibility
path:

- ``ReflectionComment.can_be_seen_by``
- ``reading.views.get_visible_reflection_filter``
- ``reading.views.passage_wall`` group-tab filtering
- reflection create/edit forms or views

It writes nothing, has no ``--apply``, never prints reflection body text, and is
not used by runtime code. ``structure_unit_at_post`` remains a write-only
companion snapshot; this module only reports on its coverage and drift.
"""

from collections import OrderedDict

from accounts.models import ChurchStructureUnit
from comments.models import ReflectionComment


SNAPSHOT_COUNTER_KEYS = (
    "group_reflections_checked",
    "group_reflections_with_legacy_group",
    "group_reflections_without_legacy_group",
    "group_reflections_with_structure_snapshot",
    "group_reflections_missing_structure_snapshot",
    "group_reflections_snapshot_matches_legacy_group_mapping",
    "group_reflections_snapshot_mismatch_legacy_group_mapping",
    "group_reflections_legacy_group_unmapped",
    "group_reflections_structure_snapshot_wrong_type",
    "group_reflections_structure_snapshot_inactive_or_missing",
)

# Verbose example categories. Each value doubles as the reason code printed on a
# detail row.
EXAMPLE_MISSING_SNAPSHOT = "missing_structure_snapshot"
EXAMPLE_SNAPSHOT_MISMATCH = "snapshot_mismatch_legacy_group_mapping"
EXAMPLE_LEGACY_GROUP_UNMAPPED = "legacy_group_unmapped"
EXAMPLE_SNAPSHOT_WRONG_TYPE = "structure_snapshot_wrong_type"

SNAPSHOT_EXAMPLE_KEYS = (
    EXAMPLE_MISSING_SNAPSHOT,
    EXAMPLE_SNAPSHOT_MISMATCH,
    EXAMPLE_LEGACY_GROUP_UNMAPPED,
    EXAMPLE_SNAPSHOT_WRONG_TYPE,
)


def _new_snapshot_stats():
    return OrderedDict((key, 0) for key in SNAPSHOT_COUNTER_KEYS)


def _unit_label(unit):
    if unit is None:
        return ""
    return f"#{unit.id} {unit.code}"


def _group_label(group):
    if group is None:
        return ""
    return f"#{group.id} {group.name}"


def _author_label(comment):
    user = comment.user
    if user is None:
        return f"#{comment.user_id}"
    return f"{user.get_username()} (#{user.id})"


def _example_row(comment, reason):
    legacy_group = comment.small_group_at_post
    legacy_unit = legacy_group.church_structure_unit if legacy_group else None
    snapshot_unit = comment.structure_unit_at_post
    # Reflection body text is private content and is intentionally never printed.
    return (
        "  "
        f"comment_id={comment.id}"
        f" | parent_id={comment.parent_id or ''}"
        f" | author={_author_label(comment)}"
        f" | legacy_small_group={_group_label(legacy_group)}"
        f" | legacy_mapped_unit={_unit_label(legacy_unit)}"
        f" | structure_snapshot_unit={_unit_label(snapshot_unit)}"
        f" | reason={reason}"
    )


def run_snapshot_readiness_audit():
    """Return read-only structure-snapshot readiness counters and examples.

    Only ``ReflectionComment`` rows with ``visibility=VISIBILITY_GROUP`` are
    counted. Nothing is mutated, created, or backfilled, and no runtime
    reflection visibility decision is made.
    """
    stats = _new_snapshot_stats()
    examples = OrderedDict((key, []) for key in SNAPSHOT_EXAMPLE_KEYS)

    comments = (
        ReflectionComment.objects.filter(
            visibility=ReflectionComment.VISIBILITY_GROUP,
        )
        .select_related(
            "user",
            "small_group_at_post",
            "small_group_at_post__church_structure_unit",
            "structure_unit_at_post",
        )
        .order_by("id")
    )

    for comment in comments:
        stats["group_reflections_checked"] += 1

        legacy_group = comment.small_group_at_post
        legacy_unit = legacy_group.church_structure_unit if legacy_group else None
        snapshot_unit = comment.structure_unit_at_post

        if legacy_group is not None:
            stats["group_reflections_with_legacy_group"] += 1
        else:
            stats["group_reflections_without_legacy_group"] += 1

        if snapshot_unit is not None:
            stats["group_reflections_with_structure_snapshot"] += 1
        else:
            stats["group_reflections_missing_structure_snapshot"] += 1
            examples[EXAMPLE_MISSING_SNAPSHOT].append(
                _example_row(comment, EXAMPLE_MISSING_SNAPSHOT)
            )

        # Snapshot-vs-legacy-mapping comparison. Only meaningful when there is a
        # legacy group to compare against.
        if legacy_group is not None and legacy_unit is None:
            stats["group_reflections_legacy_group_unmapped"] += 1
            examples[EXAMPLE_LEGACY_GROUP_UNMAPPED].append(
                _example_row(comment, EXAMPLE_LEGACY_GROUP_UNMAPPED)
            )
        elif legacy_unit is not None and snapshot_unit is not None:
            if snapshot_unit.id == legacy_unit.id:
                stats[
                    "group_reflections_snapshot_matches_legacy_group_mapping"
                ] += 1
            else:
                stats[
                    "group_reflections_snapshot_mismatch_legacy_group_mapping"
                ] += 1
                examples[EXAMPLE_SNAPSHOT_MISMATCH].append(
                    _example_row(comment, EXAMPLE_SNAPSHOT_MISMATCH)
                )

        # Snapshot self-diagnostics, independent of the legacy mapping.
        if snapshot_unit is not None:
            if snapshot_unit.unit_type != ChurchStructureUnit.UNIT_SMALL_GROUP:
                stats["group_reflections_structure_snapshot_wrong_type"] += 1
                examples[EXAMPLE_SNAPSHOT_WRONG_TYPE].append(
                    _example_row(comment, EXAMPLE_SNAPSHOT_WRONG_TYPE)
                )
            if not snapshot_unit.is_active:
                stats[
                    "group_reflections_structure_snapshot_inactive_or_missing"
                ] += 1

    return {
        "stats": stats,
        "examples": examples,
    }
