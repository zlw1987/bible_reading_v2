"""Guarded migration of non-group reflection display context off the legacy mirror.

REFLECTION-MIRROR.1F cleanup tooling. By this point the legacy
``ReflectionComment.small_group_at_post`` mirror is no longer a group-visibility
source: CS-CORE.4G.2 keyed ordinary group reflection visibility off
``structure_unit_at_post`` plus the viewer's active primary
``ChurchStructureMembership``. REFLECTION-MIRROR.1D stopped normal app-level
writes to ``small_group_at_post``, and REFLECTION-MIRROR.1E cleared the safe
group mirror rows (and non-group rows that already carried a structure snapshot).

What remains is non-group display-context rows: rows whose ``visibility`` is not
``group`` and whose only remaining display context is the legacy
``small_group_at_post`` FK because they have no ``structure_unit_at_post`` yet.
The passage-wall label prefers ``structure_unit_at_post.name`` and only falls
back to ``small_group_at_post.name``. The 1E command conservatively *skipped*
these rows (``skipped_nongroup_uncertain_display_context``) so as not to drop the
only display context. This command finishes the job: it migrates the display
context forward onto ``structure_unit_at_post`` and then clears the legacy mirror,
so the passage-wall label is preserved while the legacy ``SmallGroup`` FK is
removed.

Candidate (Category B display-context) row:
    ``small_group_at_post`` is not null, ``visibility != group``, and
    ``structure_unit_at_post`` is null.

Eligible only if the legacy ``small_group_at_post`` maps to a
``ChurchStructureUnit`` that is active and is a ``UNIT_SMALL_GROUP`` unit. On
apply the command sets ``structure_unit_at_post`` to that mapped unit and clears
``small_group_at_post``.

Scope / non-goals:

- Group-visibility rows (``visibility == group``) are **not** processed here;
  ``cleanup_reflection_small_group_mirrors`` owns those.
- Non-group rows that already carry a ``structure_unit_at_post`` are **not**
  processed here; ``cleanup_reflection_small_group_mirrors`` clears those.
- Replies are handled only from their own ``small_group_at_post`` mapping; parent
  context is never inferred.
- Hidden / deleted rows are in scope when the same safety checks pass, because
  the audit counts every non-null ``small_group_at_post`` as a
  ``reflection_small_group_at_post_references`` /
  ``small_group_retirement_blocker_references`` blocker regardless of hidden /
  deleted status (the stored FK keeps the legacy ``SmallGroup`` table pinned).

Contract (mirrors the ServiceEvent / Bible Study / reflection-snapshot /
reflection-small-group-mirror guarded cleanup pattern):

- **Dry-run is the default.** It writes nothing unless apply is requested.
- Apply requires **both** ``--apply`` and
  ``--confirm-reflection-nongroup-display-mirror-cleanup``.
- It performs no schema / model migration and no runtime source-of-truth switch.
- The only fields it ever mutates are ``ReflectionComment.structure_unit_at_post``
  (set to the mapped unit) and ``ReflectionComment.small_group_at_post`` (set to
  ``None``). It never touches ``body``, ``visibility``, ``parent``, Profile,
  ChurchStructureMembership / Unit, SmallGroup, District, MinistryContext,
  ServiceEvent, Bible Study, Prayer, role, ministry / serving / team-assignment,
  audience, permission, or reading-progress data.
- It never prints reflection body text.
- It is idempotent: a second dry-run after apply reports zero would-change rows.
"""

from dataclasses import dataclass

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounts.models import ChurchStructureUnit
from comments.models import ReflectionComment


# Counter keys, in display order.
_STAT_KEYS = (
    "reflections_checked",
    "legacy_mirror_references_before",
    "candidates",
    "eligible_to_migrate_and_clear",
    "would_migrate_and_clear_count",
    "migrated_and_cleared_count",
    "skipped_group_visibility",
    "skipped_existing_structure_snapshot",
    "skipped_legacy_group_unmapped",
    "skipped_inactive_mapped_unit",
    "skipped_wrong_mapped_unit_type",
    "remaining_legacy_mirror_references_after_operation",
)


@dataclass(frozen=True)
class MigratePlan:
    comment_id: int
    target_unit_id: int


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


def _classify(comment, stats):
    """Classify one legacy-mirror row for non-group display-context migration."""
    # Group-visibility rows are owned by cleanup_reflection_small_group_mirrors.
    if comment.visibility == ReflectionComment.VISIBILITY_GROUP:
        stats["skipped_group_visibility"] += 1
        return (
            _decision_line(
                comment,
                mapped_unit=None,
                category="skipped",
                reason=(
                    "group-visibility row; handled by "
                    "cleanup_reflection_small_group_mirrors"
                ),
            ),
            None,
        )

    # Non-group rows that already carry a structure snapshot are owned by
    # cleanup_reflection_small_group_mirrors (nothing to migrate forward here).
    if comment.structure_unit_at_post_id is not None:
        stats["skipped_existing_structure_snapshot"] += 1
        return (
            _decision_line(
                comment,
                mapped_unit=comment.small_group_at_post.church_structure_unit,
                category="skipped",
                reason=(
                    "non-group row already has structure_unit_at_post; handled by "
                    "cleanup_reflection_small_group_mirrors"
                ),
            ),
            None,
        )

    # Candidate: non-group row whose only display context is the legacy mirror.
    stats["candidates"] += 1
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
    if not mapped_unit.is_active:
        stats["skipped_inactive_mapped_unit"] += 1
        return (
            _decision_line(
                comment,
                mapped_unit=mapped_unit,
                category="blocked",
                reason="legacy small_group_at_post maps to an inactive unit",
            ),
            None,
        )
    if mapped_unit.unit_type != ChurchStructureUnit.UNIT_SMALL_GROUP:
        stats["skipped_wrong_mapped_unit_type"] += 1
        return (
            _decision_line(
                comment,
                mapped_unit=mapped_unit,
                category="blocked",
                reason="legacy small_group_at_post maps to a non-small_group unit",
            ),
            None,
        )

    # Safe: carry the display context onto structure_unit_at_post, then drop the
    # legacy mirror. Non-group visibility does not use either snapshot for access
    # control, so this preserves the passage-wall label without runtime change.
    stats["eligible_to_migrate_and_clear"] += 1
    return (
        _decision_line(
            comment,
            mapped_unit=mapped_unit,
            category="eligible_to_migrate_and_clear",
            reason=(
                "non-group display row maps to a valid active small-group unit; "
                "migrate structure_unit_at_post then clear legacy mirror"
            ),
        ),
        MigratePlan(comment_id=comment.id, target_unit_id=mapped_unit.id),
    )


def _scan(*, lock=False):
    stats = _new_stats()
    lines = []
    plans = []

    stats["reflections_checked"] = ReflectionComment.objects.count()

    for comment in _mirror_queryset(lock=lock):
        stats["legacy_mirror_references_before"] += 1
        line, plan = _classify(comment, stats)
        lines.append(line)
        if plan is not None:
            plans.append(plan)

    stats["would_migrate_and_clear_count"] = stats["eligible_to_migrate_and_clear"]
    return stats, lines, plans


def _set_remaining(stats):
    stats["remaining_legacy_mirror_references_after_operation"] = (
        stats["legacy_mirror_references_before"] - stats["migrated_and_cleared_count"]
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
                structure_unit_at_post__isnull=True,
            ).update(
                structure_unit_at_post_id=plan.target_unit_id,
                small_group_at_post=None,
            )
            if updated:
                stats["migrated_and_cleared_count"] += 1
        _set_remaining(stats)
    return stats, lines


class Command(BaseCommand):
    help = (
        "Dry-run-first guarded migration of non-group reflection display context "
        "off the legacy ReflectionComment.small_group_at_post mirror "
        "(REFLECTION-MIRROR.1F). Apply mode (requires --apply and "
        "--confirm-reflection-nongroup-display-mirror-cleanup) takes non-group "
        "rows whose only display context is the legacy mirror and whose legacy "
        "small_group_at_post maps to a valid active small-group unit, sets "
        "structure_unit_at_post to that unit, and clears small_group_at_post. It "
        "skips group-visibility rows and non-group rows that already carry a "
        "structure snapshot (owned by cleanup_reflection_small_group_mirrors). It "
        "performs no schema migration, no runtime source switch, never changes "
        "visibility/parent/body, never prints reflection body text, and touches "
        "no other field or module's data."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help=(
                "Actually migrate display context and clear the legacy mirror for "
                "eligible non-group rows. Requires "
                "--confirm-reflection-nongroup-display-mirror-cleanup."
            ),
        )
        parser.add_argument(
            "--confirm-reflection-nongroup-display-mirror-cleanup",
            action="store_true",
            help=(
                "Required with --apply to confirm this non-group reflection "
                "display-mirror migration."
            ),
        )
        parser.add_argument(
            "--verbose",
            action="store_true",
            help="Print per-reflection migration decisions (no body text).",
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
        confirmed = options["confirm_reflection_nongroup_display_mirror_cleanup"]
        if apply_mode and not confirmed:
            raise CommandError(
                "--apply requires "
                "--confirm-reflection-nongroup-display-mirror-cleanup; no "
                "ReflectionComment display mirrors were migrated or cleared."
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
        data_mutated = bool(stats["migrated_and_cleared_count"])

        if apply_mode:
            write(
                "Reflection non-group display-mirror migration "
                "(REFLECTION-MIRROR.1F, APPLY mode)"
            )
        else:
            write(
                "Reflection non-group display-mirror migration "
                "(REFLECTION-MIRROR.1F, dry-run only)"
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
                "Apply mode: for eligible non-group rows, set "
                "structure_unit_at_post to the legacy mirror's mapped active "
                "small-group unit and cleared small_group_at_post. visibility, "
                "parent, body, Profile, membership, structure, SmallGroup, "
                "ServiceEvent, Bible Study, Prayer, role, serving, audience, "
                "permission, and reading-progress data were not changed. No "
                "runtime source was switched and no schema migration was run. "
                "Reflection body text is never printed."
            )
        else:
            write(
                "Dry-run only: no reflection, legacy mirror, structure snapshot, "
                "membership, SmallGroup, ServiceEvent, Bible Study, Prayer, role, "
                "serving, audience, permission, reading-progress, runtime, or "
                "schema data changed. Re-run with --apply "
                "--confirm-reflection-nongroup-display-mirror-cleanup to write. "
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
