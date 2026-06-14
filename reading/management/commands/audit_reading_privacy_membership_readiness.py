"""Read-only reading/reflection privacy membership-core readiness audit.

CS-CORE.4B diagnostic command. It compares current legacy
``Profile.small_group`` answers with a membership-core candidate answer for:

- group-shared reflection visibility, using ``small_group_at_post`` as the
  historical group snapshot; and
- group progress roster membership for each legacy ``SmallGroup``.

It writes nothing, has no ``--apply``, and is not used by runtime code.
"""

from collections import OrderedDict, defaultdict

from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q
from django.utils import timezone

from accounts.models import ChurchStructureMembership, ChurchStructureUnit, SmallGroup
from comments.models import ReflectionComment
from reading.reflection_privacy_shadow import (
    SNAPSHOT_COUNTER_KEYS,
    SNAPSHOT_EXAMPLE_KEYS,
    run_snapshot_readiness_audit,
)


REFLECTION_PAIR_KEYS = (
    "same_visible",
    "same_hidden",
    "would_gain",
    "would_lose",
)

PROGRESS_PAIR_KEYS = (
    "same_in_roster",
    "same_out_of_roster",
    "would_gain",
    "would_lose",
)

RISK_KEYS = (
    "reflection_group_unmapped",
    "progress_group_unmapped",
    "user_profile_without_active_primary_membership",
    "user_active_primary_without_profile_group",
    "user_profile_membership_mismatch",
    "multiple_active_primary_memberships",
)

DRIFT_FAIL_KEYS = (
    "reflection_would_gain",
    "reflection_would_lose",
    "progress_would_gain",
    "progress_would_lose",
    "reflection_group_unmapped",
    "progress_group_unmapped",
    "user_profile_membership_mismatch",
    "multiple_active_primary_memberships",
)

VERBOSE_DETAIL_KEYS = (
    "reflection_would_gain",
    "reflection_would_lose",
    "progress_would_gain",
    "progress_would_lose",
    "reflection_group_unmapped",
    "progress_group_unmapped",
    "user_profile_without_active_primary_membership",
    "user_active_primary_without_profile_group",
    "user_profile_membership_mismatch",
    "multiple_active_primary_memberships",
)


def _new_stats():
    stats = OrderedDict()
    for key in REFLECTION_PAIR_KEYS:
        stats[f"reflection_{key}"] = 0
    for key in PROGRESS_PAIR_KEYS:
        stats[f"progress_{key}"] = 0
    for key in RISK_KEYS:
        stats[key] = 0
    return stats


def _active_primary_memberships_by_user(target_date):
    memberships_by_user = defaultdict(list)
    memberships = (
        ChurchStructureMembership.objects.filter(
            status=ChurchStructureMembership.STATUS_ACTIVE,
            is_primary=True,
            start_date__lte=target_date,
        )
        .filter(Q(end_date__isnull=True) | Q(end_date__gte=target_date))
        .select_related("unit", "unit__parent")
        .order_by("user_id", "id")
    )
    for membership in memberships:
        memberships_by_user[membership.user_id].append(membership)
    return memberships_by_user


def _unit_label(unit):
    if unit is None:
        return ""
    return f"#{unit.id} {unit.code}"


def _group_label(group):
    if group is None:
        return ""
    return f"#{group.id} {group.name}"


def _comment_label(comment):
    return (
        f"comment_id={comment.id}"
        f" | parent_id={comment.parent_id or ''}"
        f" | small_group_at_post={_group_label(comment.small_group_at_post)}"
    )


def _profile_small_group(user):
    try:
        return user.profile.small_group
    except ObjectDoesNotExist:
        return None


def _is_same_or_descendant(unit, target_unit):
    current = unit
    seen_ids = set()
    while current is not None and current.id not in seen_ids:
        if current.id == target_unit.id:
            return True
        seen_ids.add(current.id)
        current = current.parent
    return False


def _membership_matches_group(memberships, group):
    unit = group.church_structure_unit if group else None
    if unit is None or unit.unit_type != ChurchStructureUnit.UNIT_SMALL_GROUP:
        return False
    if len(memberships) != 1:
        return False
    return _is_same_or_descendant(memberships[0].unit, unit)


def _is_group_unmapped_for_candidate(group):
    unit = group.church_structure_unit if group else None
    return unit is None or unit.unit_type != ChurchStructureUnit.UNIT_SMALL_GROUP


def _classify_reflection_pair(user, memberships, comment):
    profile_group = _profile_small_group(user)
    legacy_visible = bool(
        profile_group and profile_group.id == comment.small_group_at_post_id
    )
    candidate_visible = _membership_matches_group(
        memberships, comment.small_group_at_post
    )

    if legacy_visible and candidate_visible:
        classification = "same_visible"
    elif not legacy_visible and not candidate_visible:
        classification = "same_hidden"
    elif legacy_visible:
        classification = "would_lose"
    else:
        classification = "would_gain"

    return legacy_visible, candidate_visible, classification


def _classify_progress_pair(user, memberships, group):
    profile_group = _profile_small_group(user)
    legacy_in_roster = bool(profile_group and profile_group.id == group.id)
    candidate_in_roster = _membership_matches_group(memberships, group)

    if legacy_in_roster and candidate_in_roster:
        classification = "same_in_roster"
    elif not legacy_in_roster and not candidate_in_roster:
        classification = "same_out_of_roster"
    elif legacy_in_roster:
        classification = "would_lose"
    else:
        classification = "would_gain"

    return legacy_in_roster, candidate_in_roster, classification


def _user_risk_categories(user, memberships):
    profile_group = _profile_small_group(user)
    profile_unit = profile_group.church_structure_unit if profile_group else None
    categories = []

    if len(memberships) > 1:
        categories.append("multiple_active_primary_memberships")
    if profile_group is not None and not memberships:
        categories.append("user_profile_without_active_primary_membership")
    if memberships and profile_group is None:
        categories.append("user_active_primary_without_profile_group")
    if (
        profile_unit is not None
        and len(memberships) == 1
        and memberships[0].unit_id != profile_unit.id
    ):
        categories.append("user_profile_membership_mismatch")

    return categories, profile_group, profile_unit


def _format_user_line(user, memberships, profile_group, profile_unit, category):
    membership = memberships[0] if len(memberships) == 1 else None
    parts = [
        f"user_id={user.id}",
        f"username={user.get_username()}",
        f"profile_small_group={_group_label(profile_group)}",
        f"profile_group_unit={_unit_label(profile_unit)}",
        f"active_primary_membership_unit={_unit_label(membership.unit) if membership else ''}",
        f"category={category}",
    ]
    if len(memberships) > 1:
        parts.append(
            "active_primary_membership_ids="
            + ",".join(str(item.id) for item in memberships)
        )
    return "  " + " | ".join(parts)


def _format_reflection_pair_line(
    user, comment, legacy_visible, candidate_visible, classification
):
    return (
        "  "
        f"user_id={user.id} | username={user.get_username()} | "
        f"{_comment_label(comment)} | legacy_visible={legacy_visible} | "
        f"membership_visible={candidate_visible} | classification={classification}"
    )


def _format_progress_pair_line(
    user, group, legacy_in_roster, candidate_in_roster, classification
):
    return (
        "  "
        f"user_id={user.id} | username={user.get_username()} | "
        f"small_group={_group_label(group)} | legacy_in_roster={legacy_in_roster} | "
        f"membership_in_roster={candidate_in_roster} | classification={classification}"
    )


def run_audit(target_date=None):
    """Return read-only readiness audit data.

    The returned dict contains summary stats, per-category detail rows, and
    scope counts. It never creates, edits, or deletes any row.
    """
    target_date = target_date or timezone.localdate()
    stats = _new_stats()
    details = OrderedDict((key, []) for key in VERBOSE_DETAIL_KEYS)

    memberships_by_user = _active_primary_memberships_by_user(target_date)
    User = get_user_model()
    users = list(
        User.objects.select_related(
            "profile__small_group__church_structure_unit"
        ).order_by("username", "id")
    )
    reflections = list(
        ReflectionComment.objects.filter(
            visibility=ReflectionComment.VISIBILITY_GROUP,
            is_hidden=False,
            is_deleted=False,
        )
        .select_related(
            "small_group_at_post",
            "small_group_at_post__church_structure_unit",
            "parent",
        )
        .order_by("id")
    )
    progress_groups = list(
        SmallGroup.objects.select_related("church_structure_unit").order_by(
            "name", "id"
        )
    )

    for comment in reflections:
        if _is_group_unmapped_for_candidate(comment.small_group_at_post):
            stats["reflection_group_unmapped"] += 1
            details["reflection_group_unmapped"].append(
                "  "
                + _comment_label(comment)
                + " | category=reflection_group_unmapped"
            )

    for group in progress_groups:
        if _is_group_unmapped_for_candidate(group):
            stats["progress_group_unmapped"] += 1
            details["progress_group_unmapped"].append(
                "  "
                + f"small_group={_group_label(group)}"
                + " | category=progress_group_unmapped"
            )

    for user in users:
        memberships = memberships_by_user.get(user.id, [])
        categories, profile_group, profile_unit = _user_risk_categories(
            user, memberships
        )
        for category in categories:
            stats[category] += 1
            details[category].append(
                _format_user_line(
                    user, memberships, profile_group, profile_unit, category
                )
            )

        for comment in reflections:
            legacy_visible, candidate_visible, classification = (
                _classify_reflection_pair(user, memberships, comment)
            )
            stats[f"reflection_{classification}"] += 1
            if classification in {"would_gain", "would_lose"}:
                details[f"reflection_{classification}"].append(
                    _format_reflection_pair_line(
                        user,
                        comment,
                        legacy_visible,
                        candidate_visible,
                        classification,
                    )
                )

        for group in progress_groups:
            legacy_in_roster, candidate_in_roster, classification = (
                _classify_progress_pair(user, memberships, group)
            )
            stats[f"progress_{classification}"] += 1
            if classification in {"would_gain", "would_lose"}:
                details[f"progress_{classification}"].append(
                    _format_progress_pair_line(
                        user,
                        group,
                        legacy_in_roster,
                        candidate_in_roster,
                        classification,
                    )
                )

    return {
        "stats": stats,
        "details": details,
        "target_date": target_date,
        "users_audited": len(users),
        "reflections_audited": len(reflections),
        "progress_groups_audited": len(progress_groups),
    }


class Command(BaseCommand):
    help = (
        "Read-only CS-CORE.4B audit comparing legacy Profile.small_group "
        "reflection visibility and progress rosters against a membership-core "
        "candidate. Writes nothing and has no apply mode."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--verbose",
            action="store_true",
            help="Print limited representative rows for drift and risk categories.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Maximum number of verbose detail rows to print.",
        )
        parser.add_argument(
            "--fail-on-drift",
            action="store_true",
            help=(
                "Exit with an error when risky reflection/progress drift or "
                "membership ambiguity is present. Still read-only."
            ),
        )

    def handle(self, *args, **options):
        if options["limit"] is not None and options["limit"] < 0:
            raise CommandError("--limit must be zero or greater.")

        audit = run_audit()
        snapshot = run_snapshot_readiness_audit()
        self._print_report(
            audit,
            verbose=options["verbose"],
            limit=options["limit"],
        )
        self._print_snapshot_readiness(
            snapshot,
            verbose=options["verbose"],
            limit=options["limit"],
        )

        if options["fail_on_drift"]:
            drifted = [
                f"{key}={audit['stats'][key]}"
                for key in DRIFT_FAIL_KEYS
                if audit["stats"][key]
            ]
            if drifted:
                raise CommandError(
                    "Reading privacy membership readiness drift detected "
                    "(--fail-on-drift): " + ", ".join(drifted)
                )

    def _print_report(self, audit, *, verbose, limit):
        write = self.stdout.write
        stats = audit["stats"]

        write("Reading privacy membership-core readiness audit (CS-CORE.4B, read-only)")
        write("=" * 76)
        write(f"target_date: {audit['target_date'].isoformat()}")
        write(f"users_audited: {audit['users_audited']}")
        write(f"reflections_audited: {audit['reflections_audited']}")
        write(f"progress_groups_audited: {audit['progress_groups_audited']}")
        write("summary:")
        write("  reflection visibility comparison:")
        for key in REFLECTION_PAIR_KEYS:
            write(f"    {key}: {stats[f'reflection_{key}']}")
        write("  progress roster comparison:")
        for key in PROGRESS_PAIR_KEYS:
            write(f"    {key}: {stats[f'progress_{key}']}")
        write("  risk categories:")
        for key in RISK_KEYS:
            write(f"    {key}: {stats[key]}")
        write("")
        write(
            "Audit only: no reflection, profile, membership, group, unit, "
            "progress, role, permission, or reading rows were changed."
        )

        if not verbose:
            return

        write("")
        write("details (drift and risk categories only):")
        printed = 0
        stopped_by_limit = False
        for category in VERBOSE_DETAIL_KEYS:
            rows = audit["details"][category]
            write(f"{category}:")
            if not rows:
                write("  (none)")
                continue

            for row in rows:
                if limit is not None and printed >= limit:
                    stopped_by_limit = True
                    break
                write(row)
                printed += 1

            if stopped_by_limit:
                break

        if stopped_by_limit:
            write(f"  (verbose output stopped at --limit {limit})")

    def _print_snapshot_readiness(self, snapshot, *, verbose, limit):
        """Print the CS-CORE.4G.1 read-only structure-snapshot readiness section.

        This reports only whether group-shared reflection rows carry stable
        ``structure_unit_at_post`` data; it is not a runtime visibility switch
        and never prints reflection body text.
        """
        write = self.stdout.write
        stats = snapshot["stats"]

        write("")
        write(
            "Reflection privacy structure-snapshot readiness "
            "(CS-CORE.4G.1, read-only)"
        )
        write("=" * 76)
        write(
            "group-shared reflection structure snapshot coverage "
            "(visibility=group only):"
        )
        for key in SNAPSHOT_COUNTER_KEYS:
            write(f"  {key}: {stats[key]}")
        write("")
        write(
            "Snapshot readiness is diagnostic only: structure_unit_at_post is not "
            "a reflection visibility source. ReflectionComment.can_be_seen_by, "
            "get_visible_reflection_filter, and the passage_wall group tab still "
            "use small_group_at_post and the viewer's legacy Profile.small_group. "
            "Reflection body text is never printed."
        )

        if not verbose:
            return

        write("")
        write("structure-snapshot examples (diagnostic categories only):")
        for category in SNAPSHOT_EXAMPLE_KEYS:
            rows = snapshot["examples"][category]
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
