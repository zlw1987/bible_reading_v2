"""Read-only Reading / Reflection / Progress structure-runtime readiness audit.

READING-STRUCT.1A diagnostic helpers. This is an *inventory + blocker* audit
that measures, in absolute terms, how *resolvable* the structure data is to
active ``ChurchStructureUnit`` rows for the reading runtime. (The reflection
half of the former CS-CORE.4B comparator ``audit_reading_privacy_membership_readiness``
was retired in REFLECTION-MIRROR.1H together with the removed
``ReflectionComment.small_group_at_post`` mirror. The legacy ``Profile.small_group``
counters this audit once carried were dropped in PROFILE-SG-FIELD-RETIRE.1A when
that field was removed; belonging is membership-core.)

Current runtime state this audit is written against:

- Group-shared ``ReflectionComment`` visibility (read + write) is structure-native
  (CS-CORE.4G.2): it keys off ``structure_unit_at_post`` plus the viewer's single
  active primary ``ChurchStructureMembership``.
- Group-progress roster is membership-core (CS-CORE.4F.1) and the no-``?group=``
  default is a permission-fenced membership-core candidate (CS-CORE.4F.2).
  ``Profile.small_group`` no longer exists; belonging is membership-core.

So the readiness questions this audit answers are:

- Do the now-live structure snapshots on group reflections actually resolve to
  active small-group units, or are some group-visible posts effectively invisible
  (legacy-only, missing/invalid snapshot)?
- Do active legacy progress groups all map to an active small-group unit?
- Do users carry an unambiguous single active primary membership (no ambiguous
  multiple active primary memberships)?

It writes nothing: no reflection, profile, membership, group, unit, progress,
role, permission, or reading row is created, edited, or deleted. It has no
``--apply`` mode and is not imported by runtime code.
"""

from collections import OrderedDict, defaultdict

from django.contrib.auth import get_user_model
from django.db.models import Q
from django.utils import timezone

from accounts.models import ChurchStructureMembership, ChurchStructureUnit, SmallGroup
from comments.models import ReflectionComment


# --- Resolvability reason codes (shared by reflections and progress groups) ---
RESOLVABLE = "resolvable"
REASON_MISSING_MAPPING = "missing_mapping"
REASON_INACTIVE_UNIT = "inactive_unit"
REASON_WRONG_UNIT_TYPE = "wrong_unit_type"

REFLECTION_COUNTER_KEYS = (
    "group_visible_reflections",
    "reflections_with_structure_snapshot",
    "reflections_snapshot_resolvable",
    "reflections_snapshot_missing",
    "reflections_snapshot_inactive_unit",
    "reflections_snapshot_wrong_unit_type",
    "reflections_group_visible_no_valid_snapshot",
)

PROGRESS_COUNTER_KEYS = (
    "progress_groups_total",
    "progress_groups_resolvable",
    "progress_groups_missing_mapping",
    "progress_groups_inactive_unit",
    "progress_groups_wrong_unit_type",
)

MEMBERSHIP_COUNTER_KEYS = (
    "users_total",
    "users_with_single_active_primary_membership",
    "users_with_multiple_active_primary_membership",
    "users_with_no_active_primary_membership",
)

# Nonzero values for any of these mean a switch / legacy-retirement is not yet
# clean. They are surfaced together by the command's ``--fail-on-blockers`` flag.
BLOCKER_KEYS = (
    "reflections_group_visible_no_valid_snapshot",
    "progress_groups_missing_mapping",
    "progress_groups_inactive_unit",
    "progress_groups_wrong_unit_type",
    "users_with_multiple_active_primary_membership",
)

VERBOSE_DETAIL_KEYS = (
    "reflections_snapshot_missing",
    "reflections_snapshot_inactive_unit",
    "reflections_snapshot_wrong_unit_type",
    "reflections_group_visible_no_valid_snapshot",
    "progress_groups_missing_mapping",
    "progress_groups_inactive_unit",
    "progress_groups_wrong_unit_type",
    "users_with_multiple_active_primary_membership",
)


def _unit_resolution_reason(unit):
    """Classify a structure unit for small-group runtime use.

    Mirrors ``comments.reflection_visibility.snapshot_unit_is_valid_for_group_visibility``
    and ``accounts`` small-group-unit checks, but returns a reason code so the
    inventory can break ``not resolvable`` down into missing / inactive /
    wrong-type. ``RESOLVABLE`` is exactly the case those boolean helpers accept.
    """
    if unit is None:
        return REASON_MISSING_MAPPING
    if not unit.is_active:
        return REASON_INACTIVE_UNIT
    if unit.unit_type != ChurchStructureUnit.UNIT_SMALL_GROUP:
        return REASON_WRONG_UNIT_TYPE
    return RESOLVABLE


def _active_primary_membership_counts_by_user(target_date):
    counts = defaultdict(int)
    rows = (
        ChurchStructureMembership.objects.filter(
            status=ChurchStructureMembership.STATUS_ACTIVE,
            is_primary=True,
            start_date__lte=target_date,
        )
        .filter(Q(end_date__isnull=True) | Q(end_date__gte=target_date))
        .values_list("user_id", flat=True)
    )
    for user_id in rows:
        counts[user_id] += 1
    return counts


def _group_label(group):
    if group is None:
        return ""
    return f"#{group.id} {group.name}"


def _unit_label(unit):
    if unit is None:
        return ""
    return f"#{unit.id} {unit.code} ({unit.unit_type})"


def run_audit(target_date=None):
    """Return the read-only Reading structure-runtime readiness inventory.

    The returned dict carries summary counters, capped verbose detail rows, scope
    counts, and the list of nonzero blocker categories. It never writes a row.
    """
    target_date = target_date or timezone.localdate()
    stats = OrderedDict(
        (key, 0)
        for key in (
            REFLECTION_COUNTER_KEYS
            + PROGRESS_COUNTER_KEYS
            + MEMBERSHIP_COUNTER_KEYS
        )
    )
    details = OrderedDict((key, []) for key in VERBOSE_DETAIL_KEYS)

    # --- Group reflection structure-snapshot inventory ---------------------------
    reflections = (
        ReflectionComment.objects.filter(
            visibility=ReflectionComment.VISIBILITY_GROUP,
            is_hidden=False,
            is_deleted=False,
        )
        .select_related("structure_unit_at_post")
        .order_by("id")
    )
    for comment in reflections.iterator():
        stats["group_visible_reflections"] += 1

        snapshot_unit = comment.structure_unit_at_post
        if comment.structure_unit_at_post_id is not None:
            stats["reflections_with_structure_snapshot"] += 1

        reason = _unit_resolution_reason(snapshot_unit)
        if reason == RESOLVABLE:
            stats["reflections_snapshot_resolvable"] += 1
        elif reason == REASON_MISSING_MAPPING:
            stats["reflections_snapshot_missing"] += 1
            details["reflections_snapshot_missing"].append(
                f"  comment_id={comment.id} | snapshot_unit=(none)"
            )
        elif reason == REASON_INACTIVE_UNIT:
            stats["reflections_snapshot_inactive_unit"] += 1
            details["reflections_snapshot_inactive_unit"].append(
                f"  comment_id={comment.id} | snapshot_unit={_unit_label(snapshot_unit)}"
            )
        else:  # REASON_WRONG_UNIT_TYPE
            stats["reflections_snapshot_wrong_unit_type"] += 1
            details["reflections_snapshot_wrong_unit_type"].append(
                f"  comment_id={comment.id} | snapshot_unit={_unit_label(snapshot_unit)}"
            )

        # A group-shared post with no *valid* structure snapshot is invisible to
        # ordinary viewers under the live CS-CORE.4G.2 gate (it keys off the
        # snapshot). That is the headline reflection blocker. (The legacy
        # small_group_at_post mirror was removed in REFLECTION-MIRROR.1H.)
        if reason != RESOLVABLE:
            stats["reflections_group_visible_no_valid_snapshot"] += 1
            details["reflections_group_visible_no_valid_snapshot"].append(
                f"  comment_id={comment.id} | snapshot_reason={reason}"
            )

    # --- Active legacy progress-group resolvability inventory --------------------
    groups = (
        SmallGroup.objects.filter(is_active=True)
        .select_related("church_structure_unit")
        .order_by("name", "id")
    )
    for group in groups:
        stats["progress_groups_total"] += 1
        reason = _unit_resolution_reason(group.church_structure_unit)
        if reason == RESOLVABLE:
            stats["progress_groups_resolvable"] += 1
        elif reason == REASON_MISSING_MAPPING:
            stats["progress_groups_missing_mapping"] += 1
            details["progress_groups_missing_mapping"].append(
                f"  small_group={_group_label(group)}"
            )
        elif reason == REASON_INACTIVE_UNIT:
            stats["progress_groups_inactive_unit"] += 1
            details["progress_groups_inactive_unit"].append(
                f"  small_group={_group_label(group)} | "
                f"unit={_unit_label(group.church_structure_unit)}"
            )
        else:  # REASON_WRONG_UNIT_TYPE
            stats["progress_groups_wrong_unit_type"] += 1
            details["progress_groups_wrong_unit_type"].append(
                f"  small_group={_group_label(group)} | "
                f"unit={_unit_label(group.church_structure_unit)}"
            )

    # --- User membership inventory ----------------------------------------------
    membership_counts = _active_primary_membership_counts_by_user(target_date)
    User = get_user_model()
    users = User.objects.order_by("username", "id")
    for user in users.iterator():
        stats["users_total"] += 1
        active_primary_count = membership_counts.get(user.id, 0)

        if active_primary_count == 1:
            stats["users_with_single_active_primary_membership"] += 1
        elif active_primary_count > 1:
            stats["users_with_multiple_active_primary_membership"] += 1
            details["users_with_multiple_active_primary_membership"].append(
                f"  user_id={user.id} | username={user.get_username()} | "
                f"active_primary_memberships={active_primary_count}"
            )
        else:
            stats["users_with_no_active_primary_membership"] += 1

    blockers = [key for key in BLOCKER_KEYS if stats[key]]

    return {
        "stats": stats,
        "details": details,
        "blockers": blockers,
        "target_date": target_date,
    }
