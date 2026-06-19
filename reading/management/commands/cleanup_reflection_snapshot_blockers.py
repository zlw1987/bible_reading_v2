"""Guarded cleanup for remaining reflection structure-snapshot blockers.

REFLECTION-SNAPSHOT.1C cleanup tooling. The legacy retirement audit
(``audit_legacy_structure_retirement_readiness``) counts group-visible
``ReflectionComment`` rows that carry no valid ``structure_unit_at_post`` snapshot
as ``reflection_small_group_at_post_removal_blockers``. The
``backfill_reflection_structure_snapshots`` command already resolves rows whose
legacy ``small_group_at_post`` maps to an active small-group unit, but two
remaining blocker shapes are not covered by that backfill:

Category A -- backfillable snapshot rows
    Group-visible rows with a null ``structure_unit_at_post`` whose
    ``small_group_at_post`` resolves to an active ``UNIT_SMALL_GROUP``
    ``ChurchStructureUnit``. Hidden / deleted rows are included because the audit
    counts stored-snapshot blockers regardless of hidden / deleted status.
    Apply sets ``structure_unit_at_post`` to the mapped unit. (This overlaps with
    the existing backfill command but is included here so this one command can
    drive the snapshot blocker count to zero.)

Category B -- orphan group reflections with no recoverable group identity
    Group-visible rows with a null ``structure_unit_at_post`` *and* a null
    ``small_group_at_post`` -- no group identity exists to backfill. Apply demotes
    only **top-level** (``parent`` is null) orphan rows **with no child replies**
    from ``group`` to ``private``; ``small_group_at_post`` /
    ``structure_unit_at_post`` are left null. Replies and parents with replies are
    skipped and reported as blocked. The live CS-CORE.4G.2 group read gate already
    fails closed for missing snapshots, so demoting to private does not expand
    visibility -- it only clarifies data semantics and removes invalid
    group-snapshot blockers.

Contract (mirrors the ServiceEvent / Bible Study guarded cleanup pattern):

- **Dry-run is the default.** It writes nothing unless apply is requested.
- Apply requires **both** ``--apply`` and
  ``--confirm-reflection-snapshot-cleanup``.
- It performs no schema / model migration and no runtime source-of-truth switch.
- It mutates only ``ReflectionComment.structure_unit_at_post`` (Category A) and
  ``ReflectionComment.visibility`` (Category B). It never touches
  ``small_group_at_post`` / ``Profile.small_group``, Bible Study, ServiceEvent,
  ChurchStructureMembership / Unit, SmallGroup, District, MinistryContext, role,
  ministry / serving / team-assignment, audience, permission, or reading-progress
  data.
- It never prints reflection body text.
- It is idempotent: a second dry-run after apply reports zero would-change rows.
"""

from dataclasses import dataclass

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Count

from comments.models import ReflectionComment
from reading.structure_runtime_readiness import (
    REASON_INACTIVE_UNIT,
    REASON_MISSING_MAPPING,
    REASON_WRONG_UNIT_TYPE,
    RESOLVABLE,
    _unit_resolution_reason,
)


# Counter keys, in display order.
_STAT_KEYS = (
    "reflections_checked",
    "already_clean",
    "snapshot_backfill_candidates",
    "would_backfill_snapshot",
    "backfilled_snapshot",
    "orphan_group_candidates",
    "would_demote_orphan_to_private",
    "demoted_orphan_to_private",
    "skipped_reply_orphan",
    "skipped_orphan_with_replies",
    "skipped_missing_mapping",
    "skipped_inactive_unit",
    "skipped_wrong_unit_type",
    "remaining_blockers_after_operation",
)

# Plan actions.
_ACTION_BACKFILL = "backfill_snapshot"
_ACTION_DEMOTE = "demote_orphan_to_private"


@dataclass(frozen=True)
class CleanupPlan:
    comment_id: int
    action: str
    target_unit_id: int  # only meaningful for _ACTION_BACKFILL


@dataclass(frozen=True)
class DecisionLine:
    comment_id: int
    username: str
    visibility: str
    parent_id: object
    child_reply_count: int
    small_group: str
    mapped_unit: str
    structure_unit: str
    is_hidden: bool
    is_deleted: bool
    scripture_ref_key: str
    category: str
    reason: str


def _new_stats():
    return {key: 0 for key in _STAT_KEYS}


def _group_label(group):
    if group is None:
        return "(none)"
    return f"#{group.id} {group.name}"


def _unit_label(unit):
    if unit is None:
        return "(none)"
    return f"#{unit.id} {unit.code} ({unit.unit_type})"


def _decision_line(comment, *, child_reply_count, mapped_unit, category, reason):
    return DecisionLine(
        comment_id=comment.id,
        username=comment.user.get_username() if comment.user_id else "(none)",
        visibility=comment.visibility,
        parent_id=comment.parent_id,
        child_reply_count=child_reply_count,
        small_group=_group_label(comment.small_group_at_post),
        mapped_unit=_unit_label(mapped_unit),
        structure_unit=_unit_label(comment.structure_unit_at_post),
        is_hidden=comment.is_hidden,
        is_deleted=comment.is_deleted,
        scripture_ref_key=comment.scripture_ref_key,
        category=category,
        reason=reason,
    )


def _format_decision_line(line):
    return (
        f"  comment #{line.comment_id} | user: {line.username} "
        f"| visibility: {line.visibility} | parent_id: {line.parent_id} "
        f"| child_replies: {line.child_reply_count} "
        f"| small_group_at_post: {line.small_group} "
        f"| mapped_unit: {line.mapped_unit} "
        f"| structure_unit_at_post: {line.structure_unit} "
        f"| is_hidden: {line.is_hidden} | is_deleted: {line.is_deleted} "
        f"| scripture_ref_key: {line.scripture_ref_key!r} "
        f"| decision: {line.category} | reason: {line.reason}"
    )


def _comment_queryset(*, lock=False):
    rows = (
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
    if lock:
        rows = rows.select_for_update()
    return rows


def _reply_counts():
    """Map parent_id -> number of child replies (all replies, any state)."""
    return dict(
        ReflectionComment.objects.filter(parent_id__isnull=False)
        .values("parent_id")
        .annotate(child_count=Count("id"))
        .values_list("parent_id", "child_count")
    )


def _classify_category_a(comment, stats, *, child_reply_count, apply_mode):
    """Group row with a null snapshot but a non-null legacy small group."""
    legacy_group = comment.small_group_at_post
    mapped_unit = legacy_group.church_structure_unit
    reason = _unit_resolution_reason(mapped_unit)

    if reason == REASON_MISSING_MAPPING:
        stats["skipped_missing_mapping"] += 1
        return (
            _decision_line(
                comment,
                child_reply_count=child_reply_count,
                mapped_unit=mapped_unit,
                category="blocked",
                reason="legacy small_group_at_post has no church_structure_unit mapping",
            ),
            None,
        )
    if reason == REASON_INACTIVE_UNIT:
        stats["skipped_inactive_unit"] += 1
        return (
            _decision_line(
                comment,
                child_reply_count=child_reply_count,
                mapped_unit=mapped_unit,
                category="blocked",
                reason="mapped church_structure_unit is inactive",
            ),
            None,
        )
    if reason == REASON_WRONG_UNIT_TYPE:
        stats["skipped_wrong_unit_type"] += 1
        return (
            _decision_line(
                comment,
                child_reply_count=child_reply_count,
                mapped_unit=mapped_unit,
                category="blocked",
                reason="mapped church_structure_unit is not a small_group unit",
            ),
            None,
        )

    # RESOLVABLE: a safely backfillable snapshot row.
    assert reason == RESOLVABLE
    stats["snapshot_backfill_candidates"] += 1
    if apply_mode:
        category = "backfill_snapshot"
        reason_text = "safe snapshot backfill applied"
    else:
        stats["would_backfill_snapshot"] += 1
        category = "would_backfill_snapshot"
        reason_text = "safe snapshot backfill candidate"
    return (
        _decision_line(
            comment,
            child_reply_count=child_reply_count,
            mapped_unit=mapped_unit,
            category=category,
            reason=reason_text,
        ),
        CleanupPlan(
            comment_id=comment.id,
            action=_ACTION_BACKFILL,
            target_unit_id=mapped_unit.id,
        ),
    )


def _classify_category_b(comment, stats, *, child_reply_count, apply_mode):
    """Group row with both snapshot and legacy small group null (orphan)."""
    stats["orphan_group_candidates"] += 1

    if comment.parent_id is not None:
        stats["skipped_reply_orphan"] += 1
        return (
            _decision_line(
                comment,
                child_reply_count=child_reply_count,
                mapped_unit=None,
                category="blocked",
                reason="orphan group reply; only top-level orphans are demoted",
            ),
            None,
        )

    if child_reply_count > 0:
        stats["skipped_orphan_with_replies"] += 1
        return (
            _decision_line(
                comment,
                child_reply_count=child_reply_count,
                mapped_unit=None,
                category="blocked",
                reason="top-level orphan has child replies; skipped for safety",
            ),
            None,
        )

    # Top-level orphan with no replies: safe to demote to private.
    if apply_mode:
        category = "demote_orphan_to_private"
        reason_text = "safe orphan-group demotion to private applied"
    else:
        stats["would_demote_orphan_to_private"] += 1
        category = "would_demote_orphan_to_private"
        reason_text = "safe orphan-group demotion to private candidate"
    return (
        _decision_line(
            comment,
            child_reply_count=child_reply_count,
            mapped_unit=None,
            category=category,
            reason=reason_text,
        ),
        CleanupPlan(
            comment_id=comment.id,
            action=_ACTION_DEMOTE,
            target_unit_id=0,
        ),
    )


def _classify_comment(comment, stats, *, child_reply_count, apply_mode):
    if comment.structure_unit_at_post_id is not None:
        stats["already_clean"] += 1
        return (
            _decision_line(
                comment,
                child_reply_count=child_reply_count,
                mapped_unit=None,
                category="already_clean",
                reason="group comment already carries a structure snapshot",
            ),
            None,
        )

    if comment.small_group_at_post_id is not None:
        return _classify_category_a(
            comment, stats, child_reply_count=child_reply_count, apply_mode=apply_mode
        )
    return _classify_category_b(
        comment, stats, child_reply_count=child_reply_count, apply_mode=apply_mode
    )


def _scan(*, lock=False, apply_mode=False):
    stats = _new_stats()
    lines = []
    plans = []
    reply_counts = _reply_counts()

    for comment in _comment_queryset(lock=lock):
        stats["reflections_checked"] += 1
        line, plan = _classify_comment(
            comment,
            stats,
            child_reply_count=reply_counts.get(comment.id, 0),
            apply_mode=apply_mode,
        )
        lines.append(line)
        if plan is not None:
            plans.append(plan)

    return stats, lines, plans


def _missing_snapshot_total(stats):
    return (
        stats["snapshot_backfill_candidates"]
        + stats["skipped_missing_mapping"]
        + stats["skipped_inactive_unit"]
        + stats["skipped_wrong_unit_type"]
        + stats["orphan_group_candidates"]
    )


def _set_remaining_blockers(stats, *, apply_mode):
    remaining = _missing_snapshot_total(stats)
    if apply_mode:
        remaining -= stats["backfilled_snapshot"] + stats["demoted_orphan_to_private"]
    stats["remaining_blockers_after_operation"] = remaining


def run_cleanup():
    stats, lines, _plans = _scan()
    _set_remaining_blockers(stats, apply_mode=False)
    return stats, lines


def apply_cleanup():
    with transaction.atomic():
        stats, lines, plans = _scan(lock=True, apply_mode=True)
        for plan in plans:
            if plan.action == _ACTION_BACKFILL:
                updated = ReflectionComment.objects.filter(
                    id=plan.comment_id,
                    structure_unit_at_post__isnull=True,
                ).update(structure_unit_at_post_id=plan.target_unit_id)
                if updated:
                    stats["backfilled_snapshot"] += 1
            elif plan.action == _ACTION_DEMOTE:
                updated = ReflectionComment.objects.filter(
                    id=plan.comment_id,
                    visibility=ReflectionComment.VISIBILITY_GROUP,
                ).update(visibility=ReflectionComment.VISIBILITY_PRIVATE)
                if updated:
                    stats["demoted_orphan_to_private"] += 1
        _set_remaining_blockers(stats, apply_mode=True)
    return stats, lines


class Command(BaseCommand):
    help = (
        "Dry-run-first guarded cleanup for remaining reflection structure-snapshot "
        "blockers (REFLECTION-SNAPSHOT.1C). Apply mode (requires --apply and "
        "--confirm-reflection-snapshot-cleanup) backfills structure_unit_at_post "
        "for group reflections whose legacy small_group_at_post maps to an active "
        "small-group unit, and demotes top-level orphan group reflections (no "
        "recoverable group identity, no child replies) from group to private. It "
        "performs no schema migration, no runtime source switch, never prints "
        "reflection body text, and touches no other module's data."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help=(
                "Actually mutate safe rows. Requires "
                "--confirm-reflection-snapshot-cleanup."
            ),
        )
        parser.add_argument(
            "--confirm-reflection-snapshot-cleanup",
            action="store_true",
            help="Required with --apply to confirm this reflection snapshot cleanup.",
        )
        parser.add_argument(
            "--verbose",
            action="store_true",
            help="Print per-reflection cleanup decisions (no body text).",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help=(
                "Limit verbose printed decisions to N rows. Does not limit "
                "scan/apply scope."
            ),
        )

    def handle(self, *args, **options):
        if options["limit"] is not None and options["limit"] < 0:
            raise CommandError("--limit must be zero or greater.")

        apply_mode = options["apply"]
        confirmed = options["confirm_reflection_snapshot_cleanup"]
        if apply_mode and not confirmed:
            raise CommandError(
                "--apply requires --confirm-reflection-snapshot-cleanup; "
                "no reflection rows were changed."
            )

        if apply_mode:
            stats, lines = apply_cleanup()
        else:
            stats, lines = run_cleanup()

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
            stats["backfilled_snapshot"] or stats["demoted_orphan_to_private"]
        )

        if apply_mode:
            write(
                "Reflection snapshot blocker cleanup "
                "(REFLECTION-SNAPSHOT.1C, APPLY mode)"
            )
        else:
            write(
                "Reflection snapshot blocker cleanup "
                "(REFLECTION-SNAPSHOT.1C, dry-run only)"
            )
        write("=" * 76)
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
                "Apply mode: set ReflectionComment.structure_unit_at_post for safe "
                "mapped group rows and demoted safe top-level orphan group rows to "
                "private. small_group_at_post, Profile.small_group, Bible Study, "
                "ServiceEvent, membership, structure, role, serving, audience, "
                "permission, and reading-progress data were not changed. No runtime "
                "source was switched and no schema migration was run. Reflection "
                "body text is never printed."
            )
        else:
            write(
                "Dry-run only: no reflection, legacy, membership, structure, Bible "
                "Study, ServiceEvent, role, serving, audience, permission, "
                "reading-progress, runtime, or schema data changed. Re-run with "
                "--apply --confirm-reflection-snapshot-cleanup to write. Reflection "
                "body text is never printed."
            )

        if not verbose:
            return

        write("")
        write("per-reflection decisions:")
        if not lines:
            write("  (no group reflections scanned)")
            return
        shown_lines = lines if verbose_limit is None else lines[:verbose_limit]
        for line in shown_lines:
            write(_format_decision_line(line))
        if verbose_limit is not None and len(lines) > len(shown_lines):
            remaining = len(lines) - len(shown_lines)
            write(
                f"  (stopped at --limit {verbose_limit}; "
                f"{remaining} more reflection decision(s) not printed)"
            )
