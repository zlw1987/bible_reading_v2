"""Guarded cleanup for existing legacy ``ReflectionComment.small_group_at_post`` mirrors.

REFLECTION-MIRROR.1E cleanup tooling. REFLECTION-MIRROR.1D already stopped normal
app-level writes to the legacy ``small_group_at_post`` mirror: new top-level posts,
replies, and edit-into-group paths leave it null, and group->group Policy C edits
preserve any existing stored value without re-stamping. Group reflection visibility
keys off ``structure_unit_at_post`` plus the viewer's active primary
``ChurchStructureMembership`` (CS-CORE.4G.2). The passage-wall group label prefers
``structure_unit_at_post`` and only falls back to ``small_group_at_post`` for old rows.

This command clears the *existing* stored ``small_group_at_post`` legacy mirror values
only when doing so is provably safe -- i.e. it cannot change reflection visibility,
display, or any runtime behavior. The audit
(``audit_legacy_structure_retirement_readiness``) counts every row with a non-null
``small_group_at_post`` as a ``reflection_small_group_at_post_references`` /
``small_group_retirement_blocker_references`` blocker, regardless of hidden / deleted
status, because the stored FK keeps the legacy ``SmallGroup`` table pinned. So hidden
and deleted rows are in scope here when the same safety checks pass.

Eligibility categories:

Category A -- group-visibility rows
    Candidate: ``small_group_at_post`` is not null and ``visibility == group``.
    Eligible only if ``structure_unit_at_post`` is not null, is active, is a
    ``UNIT_SMALL_GROUP`` unit, the legacy ``small_group_at_post`` maps to a
    ``ChurchStructureUnit``, and that mapped unit *is* the same
    ``structure_unit_at_post``. Group visibility already runs entirely off the
    structure snapshot, so clearing the matching legacy mirror cannot change it.
    Replies are eligible only on their *own* valid structure snapshot; a reply with
    no valid snapshot of its own is skipped (parent context is never inferred here).

Category B -- non-group-visibility rows
    Candidate: ``small_group_at_post`` is not null and ``visibility != group``.
    Eligible only if ``structure_unit_at_post`` is not null. The only user-facing
    place a non-group row's legacy mirror can still show is the passage-wall label,
    which prefers ``structure_unit_at_post`` and only falls back to
    ``small_group_at_post`` when no structure snapshot exists. With a structure
    snapshot present the legacy mirror is never displayed, so clearing it is safe.
    Without one, clearing would remove the only remaining display context, so the
    row is skipped as uncertain (conservative default).

Contract (mirrors the ServiceEvent / Bible Study / reflection-snapshot guarded
cleanup pattern):

- **Dry-run is the default.** It writes nothing unless apply is requested.
- Apply requires **both** ``--apply`` and
  ``--confirm-reflection-small-group-mirror-cleanup``.
- It performs no schema / model migration and no runtime source-of-truth switch.
- The only field it ever mutates is ``ReflectionComment.small_group_at_post`` (set to
  ``None``). It never touches ``body``, ``visibility``, ``structure_unit_at_post``,
  ``parent``, Profile, ChurchStructureMembership / Unit, SmallGroup, District,
  MinistryContext, ServiceEvent, Bible Study, Prayer, role, ministry / serving /
  team-assignment, audience, permission, or reading-progress data.
- It never prints reflection body text.
- It is idempotent: a second dry-run after apply reports zero would-clear rows.
"""

from dataclasses import dataclass

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounts.models import ChurchStructureUnit
from comments.models import ReflectionComment


# Counter keys, in display order.
_STAT_KEYS = (
    "reflections_checked",
    "mirrors_present",
    "already_clear",
    "group_candidates",
    "group_eligible_to_clear",
    "nongroup_candidates",
    "nongroup_eligible_to_clear",
    "would_clear_count",
    "cleared_count",
    "skipped_missing_structure_snapshot",
    "skipped_inactive_structure_unit",
    "skipped_wrong_structure_unit_type",
    "skipped_legacy_group_unmapped",
    "skipped_legacy_structure_mismatch",
    "skipped_nongroup_uncertain_display_context",
    "skipped_reply_without_own_structure_snapshot",
    "remaining_mirror_references_after_operation",
)


@dataclass(frozen=True)
class CleanupPlan:
    comment_id: int


@dataclass(frozen=True)
class DecisionLine:
    comment_id: int
    username: str
    visibility: str
    parent_id: object
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


def _decision_line(comment, *, mapped_unit, category, reason):
    return DecisionLine(
        comment_id=comment.id,
        username=comment.user.get_username() if comment.user_id else "(none)",
        visibility=comment.visibility,
        parent_id=comment.parent_id,
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
        f"| small_group_at_post: {line.small_group} "
        f"| mapped_unit: {line.mapped_unit} "
        f"| structure_unit_at_post: {line.structure_unit} "
        f"| is_hidden: {line.is_hidden} | is_deleted: {line.is_deleted} "
        f"| scripture_ref_key: {line.scripture_ref_key!r} "
        f"| decision: {line.category} | reason: {line.reason}"
    )


def _mirror_queryset(*, lock=False):
    rows = (
        ReflectionComment.objects.filter(small_group_at_post__isnull=False)
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


def _classify_group(comment, stats):
    """Group-visibility mirror row (Category A)."""
    stats["group_candidates"] += 1
    snapshot = comment.structure_unit_at_post

    if snapshot is None:
        if comment.parent_id is not None:
            stats["skipped_reply_without_own_structure_snapshot"] += 1
            return (
                _decision_line(
                    comment,
                    mapped_unit=None,
                    category="blocked",
                    reason=(
                        "group reply has no structure_unit_at_post of its own; "
                        "parent context is not inferred"
                    ),
                ),
                None,
            )
        stats["skipped_missing_structure_snapshot"] += 1
        return (
            _decision_line(
                comment,
                mapped_unit=None,
                category="blocked",
                reason="group row has no structure_unit_at_post snapshot",
            ),
            None,
        )

    if not snapshot.is_active:
        stats["skipped_inactive_structure_unit"] += 1
        return (
            _decision_line(
                comment,
                mapped_unit=None,
                category="blocked",
                reason="structure_unit_at_post is inactive",
            ),
            None,
        )
    if snapshot.unit_type != ChurchStructureUnit.UNIT_SMALL_GROUP:
        stats["skipped_wrong_structure_unit_type"] += 1
        return (
            _decision_line(
                comment,
                mapped_unit=None,
                category="blocked",
                reason="structure_unit_at_post is not a small_group unit",
            ),
            None,
        )

    mapped_unit = comment.small_group_at_post.church_structure_unit
    if mapped_unit is None:
        stats["skipped_legacy_group_unmapped"] += 1
        return (
            _decision_line(
                comment,
                mapped_unit=None,
                category="blocked",
                reason="legacy small_group_at_post has no church_structure_unit mapping",
            ),
            None,
        )
    if mapped_unit.id != snapshot.id:
        stats["skipped_legacy_structure_mismatch"] += 1
        return (
            _decision_line(
                comment,
                mapped_unit=mapped_unit,
                category="blocked",
                reason=(
                    "legacy small_group_at_post maps to a unit other than "
                    "structure_unit_at_post"
                ),
            ),
            None,
        )

    # Group visibility already runs off this matching active small-group snapshot;
    # clearing the legacy mirror cannot change it.
    stats["group_eligible_to_clear"] += 1
    return (
        _decision_line(
            comment,
            mapped_unit=mapped_unit,
            category="eligible_to_clear",
            reason="group mirror matches valid structure snapshot; safe to clear",
        ),
        CleanupPlan(comment_id=comment.id),
    )


def _classify_nongroup(comment, stats):
    """Non-group-visibility mirror row (Category B)."""
    stats["nongroup_candidates"] += 1
    mapped_unit = comment.small_group_at_post.church_structure_unit

    if comment.structure_unit_at_post_id is None:
        # The legacy mirror is the only remaining display context (passage-wall
        # label fallback); clearing it could remove a user-facing label. Skip.
        stats["skipped_nongroup_uncertain_display_context"] += 1
        return (
            _decision_line(
                comment,
                mapped_unit=mapped_unit,
                category="blocked",
                reason=(
                    "non-group row has no structure_unit_at_post; legacy mirror is "
                    "the only display context, skipped conservatively"
                ),
            ),
            None,
        )

    # A structure snapshot is present, so the legacy mirror is never displayed
    # (the passage-wall label prefers structure_unit_at_post). Safe to clear.
    stats["nongroup_eligible_to_clear"] += 1
    return (
        _decision_line(
            comment,
            mapped_unit=mapped_unit,
            category="eligible_to_clear",
            reason=(
                "non-group row carries a structure_unit_at_post; legacy mirror is "
                "not displayed, safe to clear"
            ),
        ),
        CleanupPlan(comment_id=comment.id),
    )


def _classify_comment(comment, stats):
    if comment.visibility == ReflectionComment.VISIBILITY_GROUP:
        return _classify_group(comment, stats)
    return _classify_nongroup(comment, stats)


def _scan(*, lock=False):
    stats = _new_stats()
    lines = []
    plans = []

    stats["reflections_checked"] = ReflectionComment.objects.count()

    for comment in _mirror_queryset(lock=lock):
        stats["mirrors_present"] += 1
        line, plan = _classify_comment(comment, stats)
        lines.append(line)
        if plan is not None:
            plans.append(plan)

    stats["already_clear"] = stats["reflections_checked"] - stats["mirrors_present"]
    stats["would_clear_count"] = (
        stats["group_eligible_to_clear"] + stats["nongroup_eligible_to_clear"]
    )
    return stats, lines, plans


def _set_remaining(stats):
    stats["remaining_mirror_references_after_operation"] = (
        stats["mirrors_present"] - stats["cleared_count"]
    )


def run_cleanup():
    stats, lines, _plans = _scan()
    _set_remaining(stats)
    return stats, lines


def apply_cleanup():
    with transaction.atomic():
        stats, lines, plans = _scan(lock=True)
        for plan in plans:
            updated = ReflectionComment.objects.filter(
                id=plan.comment_id,
                small_group_at_post__isnull=False,
            ).update(small_group_at_post=None)
            if updated:
                stats["cleared_count"] += 1
        _set_remaining(stats)
    return stats, lines


class Command(BaseCommand):
    help = (
        "Dry-run-first guarded cleanup for existing legacy "
        "ReflectionComment.small_group_at_post mirrors (REFLECTION-MIRROR.1E). "
        "Apply mode (requires --apply and "
        "--confirm-reflection-small-group-mirror-cleanup) sets small_group_at_post "
        "to null only for rows where clearing it cannot change visibility or "
        "display: group rows whose matching active small-group structure snapshot "
        "already drives visibility, and non-group rows that carry a "
        "structure_unit_at_post. It performs no schema migration, no runtime source "
        "switch, never prints reflection body text, and touches no other field or "
        "module's data."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help=(
                "Actually clear safe small_group_at_post mirrors. Requires "
                "--confirm-reflection-small-group-mirror-cleanup."
            ),
        )
        parser.add_argument(
            "--confirm-reflection-small-group-mirror-cleanup",
            action="store_true",
            help=(
                "Required with --apply to confirm this legacy small-group mirror "
                "cleanup."
            ),
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
        confirmed = options["confirm_reflection_small_group_mirror_cleanup"]
        if apply_mode and not confirmed:
            raise CommandError(
                "--apply requires --confirm-reflection-small-group-mirror-cleanup; "
                "no ReflectionComment.small_group_at_post mirrors were cleared."
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
        data_mutated = bool(stats["cleared_count"])

        if apply_mode:
            write(
                "Reflection legacy small-group mirror cleanup "
                "(REFLECTION-MIRROR.1E, APPLY mode)"
            )
        else:
            write(
                "Reflection legacy small-group mirror cleanup "
                "(REFLECTION-MIRROR.1E, dry-run only)"
            )
        write("=" * 78)
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
                "Apply mode: cleared only safe ReflectionComment.small_group_at_post "
                "legacy mirrors. visibility, structure_unit_at_post, parent, body, "
                "Profile, membership, structure, SmallGroup, ServiceEvent, Bible "
                "Study, Prayer, role, serving, audience, permission, and "
                "reading-progress data were not changed. No runtime source was "
                "switched and no schema migration was run. Reflection body text is "
                "never printed."
            )
        else:
            write(
                "Dry-run only: no reflection, legacy mirror, structure, membership, "
                "SmallGroup, ServiceEvent, Bible Study, Prayer, role, serving, "
                "audience, permission, reading-progress, runtime, or schema data "
                "changed. Re-run with --apply "
                "--confirm-reflection-small-group-mirror-cleanup to write. "
                "Reflection body text is never printed."
            )

        if not verbose:
            return

        write("")
        write("per-reflection decisions:")
        if not lines:
            write("  (no legacy small-group mirrors scanned)")
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
