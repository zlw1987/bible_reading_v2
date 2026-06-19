"""Guarded cleanup for existing legacy Profile.small_group values.

Dry-run is the default. Apply mode requires both ``--apply`` and
``--confirm-profile-small-group-cleanup``. It clears only
``Profile.small_group`` rows whose current active primary
``ChurchStructureMembership`` safely represents the same active small-group
``ChurchStructureUnit`` mapped from the legacy ``SmallGroup``.
"""

from dataclasses import dataclass

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from accounts.models import (
    ChurchStructureMembership,
    ChurchStructureUnit,
    Profile,
)


_STAT_KEYS = (
    "profiles_checked",
    "profiles_without_small_group",
    "candidates_with_small_group",
    "eligible_to_clear",
    "would_clear_count",
    "cleared_count",
    "skipped_no_active_primary_membership",
    "skipped_multiple_active_primary_memberships",
    "skipped_unmapped_small_group",
    "skipped_inactive_unit",
    "skipped_wrong_unit_type",
    "skipped_membership_mismatch",
    "remaining_blockers_after_operation",
)


@dataclass(frozen=True)
class CleanupPlan:
    profile_id: int
    small_group_id: int


@dataclass(frozen=True)
class DecisionLine:
    user_id: int
    username: str
    profile_id: int
    small_group: str
    mapped_unit: str
    membership: str
    decision: str
    reason: str


def _new_stats():
    return {key: 0 for key in _STAT_KEYS}


def _bool(value):
    return str(bool(value)).lower()


def _group_label(group):
    if group is None:
        return "(none)"
    return f"#{group.id} {group.name}"


def _unit_label(unit):
    if unit is None:
        return "(none)"
    try:
        path = unit.path_label("en")
    except AttributeError:
        path = getattr(unit, "name_en", "") or getattr(unit, "name", "")
    path = path or getattr(unit, "code", "")
    return f"#{unit.id} {path}".strip()


def _membership_label(membership):
    if membership is None:
        return "(none)"
    return f"#{membership.id} {_unit_label(membership.unit)}"


def _active_primary_memberships(target_date):
    return (
        ChurchStructureMembership.objects.filter(
            status=ChurchStructureMembership.STATUS_ACTIVE,
            is_primary=True,
            start_date__lte=target_date,
        )
        .filter(Q(end_date__isnull=True) | Q(end_date__gte=target_date))
        .select_related("unit")
        .order_by("id")
    )


def _memberships_by_user(target_date):
    memberships_by_user = {}
    for membership in _active_primary_memberships(target_date):
        memberships_by_user.setdefault(membership.user_id, []).append(membership)
    return memberships_by_user


def _profile_queryset(*, lock=False):
    profiles = (
        Profile.objects.select_related(
            "user",
            "small_group",
            "small_group__church_structure_unit",
        )
        .all()
        .order_by("user__username", "id")
    )
    if lock:
        profiles = profiles.select_for_update()
    return profiles


def _decision_line(profile, *, membership=None, decision, reason):
    group = profile.small_group
    mapped_unit = group.church_structure_unit if group is not None else None
    return DecisionLine(
        user_id=profile.user_id,
        username=profile.user.get_username(),
        profile_id=profile.id,
        small_group=_group_label(group),
        mapped_unit=_unit_label(mapped_unit),
        membership=_membership_label(membership),
        decision=decision,
        reason=reason,
    )


def _format_decision_line(line):
    return (
        f"  user_id={line.user_id} | username={line.username} "
        f"| profile_id={line.profile_id} | legacy_small_group={line.small_group} "
        f"| mapped_structure_unit={line.mapped_unit} "
        f"| active_primary_membership={line.membership} "
        f"| decision={line.decision} | reason={line.reason}"
    )


def _blocked(stats, key, profile, reason, *, membership=None):
    stats[key] += 1
    return (
        _decision_line(
            profile,
            membership=membership,
            decision="blocked",
            reason=f"{key}: {reason}",
        ),
        None,
    )


def _classify_profile(profile, stats, *, memberships, apply_mode):
    stats["profiles_checked"] += 1

    if profile.small_group_id is None:
        stats["profiles_without_small_group"] += 1
        return (
            _decision_line(
                profile,
                decision="already_clear",
                reason="Profile.small_group is already null",
            ),
            None,
        )

    stats["candidates_with_small_group"] += 1

    if not memberships:
        return _blocked(
            stats,
            "skipped_no_active_primary_membership",
            profile,
            "user has no active primary ChurchStructureMembership for target date",
        )

    if len(memberships) > 1:
        return _blocked(
            stats,
            "skipped_multiple_active_primary_memberships",
            profile,
            "user has more than one active primary ChurchStructureMembership",
        )

    membership = memberships[0]
    mapped_unit = profile.small_group.church_structure_unit

    if mapped_unit is None:
        return _blocked(
            stats,
            "skipped_unmapped_small_group",
            profile,
            "legacy SmallGroup has no ChurchStructureUnit mapping",
            membership=membership,
        )

    if not mapped_unit.is_active:
        return _blocked(
            stats,
            "skipped_inactive_unit",
            profile,
            "mapped ChurchStructureUnit is inactive",
            membership=membership,
        )

    if mapped_unit.unit_type != ChurchStructureUnit.UNIT_SMALL_GROUP:
        return _blocked(
            stats,
            "skipped_wrong_unit_type",
            profile,
            (
                "mapped ChurchStructureUnit has unit_type "
                f"{mapped_unit.unit_type!r}, not "
                f"{ChurchStructureUnit.UNIT_SMALL_GROUP!r}"
            ),
            membership=membership,
        )

    if membership.unit_id != mapped_unit.id:
        return _blocked(
            stats,
            "skipped_membership_mismatch",
            profile,
            "active primary membership unit differs from legacy SmallGroup mapping",
            membership=membership,
        )

    stats["eligible_to_clear"] += 1
    if apply_mode:
        decision = "cleared"
        reason = "safe Profile.small_group cleanup applied"
    else:
        stats["would_clear_count"] += 1
        decision = "would_clear"
        reason = "safe Profile.small_group cleanup candidate"

    return (
        _decision_line(
            profile,
            membership=membership,
            decision=decision,
            reason=reason,
        ),
        CleanupPlan(
            profile_id=profile.id,
            small_group_id=profile.small_group_id,
        ),
    )


def _scan_profiles(*, target_date, lock=False, apply_mode=False):
    stats = _new_stats()
    lines = []
    plans = []
    memberships_by_user = _memberships_by_user(target_date)

    for profile in _profile_queryset(lock=lock):
        memberships = memberships_by_user.get(profile.user_id, [])
        line, plan = _classify_profile(
            profile,
            stats,
            memberships=memberships,
            apply_mode=apply_mode,
        )
        lines.append(line)
        if plan is not None:
            plans.append(plan)

    return stats, lines, plans


def _set_remaining_blockers(stats, *, apply_mode):
    if apply_mode:
        remaining = stats["candidates_with_small_group"] - stats["cleared_count"]
    else:
        remaining = stats["candidates_with_small_group"]
    stats["remaining_blockers_after_operation"] = remaining


def run_audit(*, target_date=None):
    target_date = target_date or timezone.localdate()
    stats, lines, _plans = _scan_profiles(target_date=target_date)
    _set_remaining_blockers(stats, apply_mode=False)
    return stats, lines


def apply_cleanup(*, target_date=None):
    target_date = target_date or timezone.localdate()
    with transaction.atomic():
        stats, lines, plans = _scan_profiles(
            target_date=target_date,
            lock=True,
            apply_mode=True,
        )
        for plan in plans:
            updated = Profile.objects.filter(
                id=plan.profile_id,
                small_group_id=plan.small_group_id,
            ).update(small_group=None)
            if updated:
                stats["cleared_count"] += 1
        _set_remaining_blockers(stats, apply_mode=True)
    return stats, lines


class Command(BaseCommand):
    help = (
        "Dry-run-first cleanup for legacy Profile.small_group values "
        "(PROFILE-SG.1B). Apply mode clears only Profile.small_group for "
        "profiles whose single active primary ChurchStructureMembership "
        "matches the mapped active small-group ChurchStructureUnit. It never "
        "changes memberships, structure rows, legacy SmallGroup/District/"
        "MinistryContext rows, runtime behavior, permissions, serving, or "
        "other app data."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help=(
                "Actually clear safe Profile.small_group values. Requires "
                "--confirm-profile-small-group-cleanup."
            ),
        )
        parser.add_argument(
            "--confirm-profile-small-group-cleanup",
            action="store_true",
            help="Required with --apply to confirm this Profile.small_group cleanup.",
        )
        parser.add_argument(
            "--verbose",
            action="store_true",
            help="Print per-profile cleanup decisions.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help=(
                "Limit verbose printed decisions to N profiles. Does not "
                "limit scan/apply scope."
            ),
        )

    def handle(self, *args, **options):
        if options["limit"] is not None and options["limit"] < 0:
            raise CommandError("--limit must be zero or greater.")

        apply_mode = options["apply"]
        confirmed = options["confirm_profile_small_group_cleanup"]
        if apply_mode and not confirmed:
            raise CommandError(
                "--apply requires --confirm-profile-small-group-cleanup; "
                "no Profile.small_group values were cleared."
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
        data_mutated = bool(stats["cleared_count"])

        if apply_mode:
            write("Profile.small_group cleanup (PROFILE-SG.1B, APPLY mode)")
        else:
            write("Profile.small_group cleanup (PROFILE-SG.1B, dry-run only)")
        write("=" * 72)
        write(f"mode: {'apply' if apply_mode else 'dry-run'}")
        write(f"apply_option_present: {_bool(apply_mode)}")
        write(f"confirmation_option_present: {_bool(confirmed)}")
        for key in _STAT_KEYS:
            if key == "cleared_count" and not apply_mode:
                continue
            write(f"{key}: {stats[key]}")
        write(f"data_mutated: {_bool(data_mutated)}")
        write("runtime_mutated: false")
        write("schema_mutated: false")
        write("")
        if apply_mode:
            write(
                "Apply mode: cleared only safe Profile.small_group values. "
                "ChurchStructureMembership, ChurchStructureUnit, SmallGroup, "
                "District, MinistryContext, ServiceEvent, Bible Study, Prayer, "
                "Reading, Reflection, Role, Ministry, TeamAssignment, "
                "permissions, serving data, runtime behavior, and schema were "
                "not changed."
            )
        else:
            write(
                "Dry-run only: no Profile.small_group, ChurchStructureMembership, "
                "ChurchStructureUnit, SmallGroup, District, MinistryContext, "
                "ServiceEvent, Bible Study, Prayer, Reading, Reflection, Role, "
                "Ministry, TeamAssignment, permission, serving, runtime, or "
                "schema data changed."
            )

        if not verbose:
            return

        write("")
        write("per-profile decisions:")
        if not lines:
            write("  (no profiles scanned)")
            return
        shown_lines = lines if verbose_limit is None else lines[:verbose_limit]
        for line in shown_lines:
            write(_format_decision_line(line))
        if verbose_limit is not None and len(lines) > len(shown_lines):
            remaining = len(lines) - len(shown_lines)
            write(
                f"  (stopped at --limit {verbose_limit}; "
                f"{remaining} more profile decision(s) not printed)"
            )
