"""Read-only operational group-progress shadow audit (CS-CORE.4E.1).

Focused diagnostic for the group-progress migration gate. For each active legacy
``SmallGroup`` it compares the legacy ``Profile.small_group`` roster with a
membership-core candidate roster (reusing
``reading.group_progress_shadow.compute_group_progress_roster_shadow``), and it
separately compares each relevant user's legacy default group with the
membership-core candidate default group.

Hard contract:

- This command is **read-only**. It has no ``--apply`` and writes nothing.
- Runtime group progress remains legacy-driven; nothing here switches the source,
  changes a roster/default, or grants/denies any progress permission. Ordinary
  ``ChurchStructureMembership`` confers no progress access (privacy invariant 5).
- The membership-core candidate fails closed on ambiguity (no active primary
  membership, multiple active primary memberships, an unmapped selected group, or a
  membership unit that is not a mapped small-group unit).

It does not call or influence ``reading.views.my_group_progress()``. Use it as
real-data gate evidence before any future group-progress source switch.
"""

from collections import OrderedDict, defaultdict
from datetime import datetime

from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q
from django.utils import timezone

from accounts.models import ChurchStructureMembership, ChurchStructureUnit, SmallGroup
from reading.group_progress_shadow import (
    REASON_SELECTED_GROUP_UNMAPPED,
    compute_group_progress_roster_shadow,
)


# Counters reported in the summary. Order is the display order.
SUMMARY_KEYS = (
    "groups_checked",
    "groups_same_roster",
    "groups_with_roster_gain",
    "groups_with_roster_loss",
    "progress_would_gain",
    "progress_would_lose",
    "selected_group_unmapped",
    "users_checked_for_default",
    "default_same",
    "default_would_change",
    "profile_membership_mismatch",
    "membership_no_active_primary",
    "membership_multiple_active_primary",
    "membership_unit_unmapped",
)

# Nonzero values for any of these are risky drift that would block a switch.
# ``membership_no_active_primary`` is intentionally *not* here: a user simply
# lacking a membership is not drift on its own. When that user also has a legacy
# default group it already surfaces through ``default_would_change``.
DRIFT_FAIL_KEYS = (
    "progress_would_gain",
    "progress_would_lose",
    "groups_with_roster_gain",
    "groups_with_roster_loss",
    "default_would_change",
    "profile_membership_mismatch",
    "membership_multiple_active_primary",
    "selected_group_unmapped",
    "membership_unit_unmapped",
)


def _profile_small_group(user):
    try:
        return user.profile.small_group
    except ObjectDoesNotExist:
        return None


def _group_label(group):
    if group is None:
        return ""
    return f"#{group.id} {group.name}"


def _active_primary_memberships_by_user(target_date):
    memberships_by_user = defaultdict(list)
    memberships = (
        ChurchStructureMembership.objects.filter(
            status=ChurchStructureMembership.STATUS_ACTIVE,
            is_primary=True,
            start_date__lte=target_date,
        )
        .filter(Q(end_date__isnull=True) | Q(end_date__gte=target_date))
        .select_related("unit")
        .order_by("user_id", "id")
    )
    for membership in memberships:
        memberships_by_user[membership.user_id].append(membership)
    return memberships_by_user


def _candidate_group_by_unit():
    """Map each unit id to its single active legacy small-group, fail-closed.

    Mirrors ``group_progress_shadow._candidate_group_for_unit``: a unit only maps
    when it is a small-group-type unit linked to exactly one active ``SmallGroup``.
    """
    groups_by_unit = defaultdict(list)
    groups = SmallGroup.objects.filter(is_active=True).select_related(
        "church_structure_unit"
    )
    for group in groups:
        unit = group.church_structure_unit
        if unit is not None and unit.unit_type == ChurchStructureUnit.UNIT_SMALL_GROUP:
            groups_by_unit[unit.id].append(group)
    return {
        unit_id: mapped[0]
        for unit_id, mapped in groups_by_unit.items()
        if len(mapped) == 1
    }


def run_audit(*, target_date=None, group_ids=None):
    """Return read-only group-progress shadow audit data.

    ``group_ids`` (optional iterable) limits both the roster scan and the user
    default scan to those legacy groups. The returned dict carries summary counters,
    capped-detail source rows, and scope metadata. It never writes.
    """
    target_date = target_date or timezone.localdate()
    group_id_filter = set(group_ids) if group_ids else None

    stats = OrderedDict((key, 0) for key in SUMMARY_KEYS)
    roster_details = []
    default_details = []

    # --- Roster comparison per active legacy group -------------------------------
    groups_qs = SmallGroup.objects.filter(is_active=True).select_related(
        "church_structure_unit"
    )
    if group_id_filter is not None:
        groups_qs = groups_qs.filter(id__in=group_id_filter)
    groups = list(groups_qs.order_by("name", "id"))

    user_ids_needed = set()
    for group in groups:
        roster = compute_group_progress_roster_shadow(group, target_date=target_date)
        stats["groups_checked"] += 1
        if REASON_SELECTED_GROUP_UNMAPPED in roster.reason_codes:
            stats["selected_group_unmapped"] += 1
        if roster.same_roster:
            stats["groups_same_roster"] += 1
        if roster.would_gain_user_ids:
            stats["groups_with_roster_gain"] += 1
        if roster.would_lose_user_ids:
            stats["groups_with_roster_loss"] += 1
        stats["progress_would_gain"] += len(roster.would_gain_user_ids)
        stats["progress_would_lose"] += len(roster.would_lose_user_ids)

        if roster.would_gain_user_ids or roster.would_lose_user_ids or (
            REASON_SELECTED_GROUP_UNMAPPED in roster.reason_codes
        ):
            user_ids_needed.update(roster.would_gain_user_ids)
            user_ids_needed.update(roster.would_lose_user_ids)
            roster_details.append(
                {
                    "group": group,
                    "would_gain": sorted(roster.would_gain_user_ids),
                    "would_lose": sorted(roster.would_lose_user_ids),
                    "reason_codes": roster.reason_codes,
                }
            )

    # --- User default comparison -------------------------------------------------
    memberships_by_user = _active_primary_memberships_by_user(target_date)
    candidate_group_by_unit = _candidate_group_by_unit()

    User = get_user_model()
    users = list(
        User.objects.select_related("profile__small_group").order_by("username", "id")
    )

    default_records = []
    for user in users:
        legacy_group = _profile_small_group(user)
        memberships = memberships_by_user.get(user.id, [])
        # Out of scope when the user has neither a legacy default nor any active
        # primary membership: there is no default in either world to compare.
        if legacy_group is None and not memberships:
            continue

        candidate_group = None
        reason = None
        if not memberships:
            reason = "membership_no_active_primary"
        elif len(memberships) > 1:
            reason = "membership_multiple_active_primary"
        else:
            unit_id = memberships[0].unit_id
            candidate_group = candidate_group_by_unit.get(unit_id)
            if candidate_group is None:
                reason = "membership_unit_unmapped"

        legacy_id = legacy_group.id if legacy_group is not None else None
        candidate_id = candidate_group.id if candidate_group is not None else None
        same_default = legacy_id == candidate_id
        mismatch = (
            legacy_group is not None
            and candidate_group is not None
            and legacy_id != candidate_id
        )

        default_records.append(
            {
                "user": user,
                "legacy_group": legacy_group,
                "candidate_group": candidate_group,
                "same_default": same_default,
                "mismatch": mismatch,
                "reason": reason,
            }
        )

    if group_id_filter is not None:
        default_records = [
            record
            for record in default_records
            if (
                (record["legacy_group"] is not None
                 and record["legacy_group"].id in group_id_filter)
                or (record["candidate_group"] is not None
                    and record["candidate_group"].id in group_id_filter)
            )
        ]

    for record in default_records:
        stats["users_checked_for_default"] += 1
        if record["same_default"]:
            stats["default_same"] += 1
        else:
            stats["default_would_change"] += 1
        if record["mismatch"]:
            stats["profile_membership_mismatch"] += 1
        if record["reason"] == "membership_no_active_primary":
            stats["membership_no_active_primary"] += 1
        elif record["reason"] == "membership_multiple_active_primary":
            stats["membership_multiple_active_primary"] += 1
        elif record["reason"] == "membership_unit_unmapped":
            stats["membership_unit_unmapped"] += 1

        if not record["same_default"] or record["mismatch"]:
            default_details.append(record)

    return {
        "stats": stats,
        "roster_details": roster_details,
        "default_details": default_details,
        "target_date": target_date,
        "group_id_filter": sorted(group_id_filter) if group_id_filter else None,
        "user_labels": {
            user.id: user.get_username()
            for user in users
            if user.id in user_ids_needed
            or any(record["user"].id == user.id for record in default_details)
        },
    }


class Command(BaseCommand):
    help = (
        "Read-only CS-CORE.4E.1 operational audit comparing legacy "
        "Profile.small_group group-progress rosters and defaults against a "
        "membership-core candidate. Writes nothing and has no apply mode."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--group-id",
            type=int,
            action="append",
            dest="group_ids",
            default=None,
            help="Limit the report to this legacy SmallGroup id. Repeatable.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=20,
            help="Cap the number of detailed example rows printed (default 20).",
        )
        parser.add_argument(
            "--verbose",
            action="store_true",
            help="Print capped per-group and per-user detail rows.",
        )
        parser.add_argument(
            "--fail-on-drift",
            action="store_true",
            help=(
                "Exit with an error when risky roster/default drift or membership "
                "ambiguity is present. Still read-only."
            ),
        )
        parser.add_argument(
            "--date",
            dest="date",
            default=None,
            help="Audit as-of date (YYYY-MM-DD). Defaults to today.",
        )

    def handle(self, *args, **options):
        if options["limit"] < 0:
            raise CommandError("--limit must be zero or greater.")

        target_date = None
        if options["date"]:
            try:
                target_date = datetime.strptime(options["date"], "%Y-%m-%d").date()
            except ValueError:
                raise CommandError("--date must be in YYYY-MM-DD format.")

        audit = run_audit(target_date=target_date, group_ids=options["group_ids"])
        self._print_report(
            audit,
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
                    "Group-progress shadow drift detected (--fail-on-drift): "
                    + ", ".join(drifted)
                )

    def _print_report(self, audit, *, verbose, limit):
        write = self.stdout.write
        stats = audit["stats"]

        write("Group-progress shadow audit (CS-CORE.4E.1, read-only)")
        write("=" * 76)
        write(f"target_date: {audit['target_date'].isoformat()}")
        if audit["group_id_filter"]:
            write(
                "group_id_filter: "
                + ", ".join(str(item) for item in audit["group_id_filter"])
            )
        write("summary:")
        for key in SUMMARY_KEYS:
            write(f"  {key}: {stats[key]}")
        write("")
        write("READ-ONLY: no data was changed.")
        write("Runtime remains legacy-driven.")
        write(
            "No membership-core source switch or permission change happened; "
            "ordinary membership grants no progress access."
        )

        if not verbose:
            return

        user_labels = audit["user_labels"]

        def label(user_id):
            return f"{user_labels.get(user_id, '?')}({user_id})"

        write("")
        write("details (capped):")
        printed = 0

        write("roster drift by group:")
        if not audit["roster_details"]:
            write("  (none)")
        for detail in audit["roster_details"]:
            if printed >= limit:
                write(f"  (detail output stopped at --limit {limit})")
                break
            group = detail["group"]
            write(
                "  "
                + f"group={_group_label(group)}"
                + " | would_gain="
                + ",".join(label(uid) for uid in detail["would_gain"])
                + " | would_lose="
                + ",".join(label(uid) for uid in detail["would_lose"])
                + " | reason_codes="
                + ",".join(detail["reason_codes"])
            )
            printed += 1

        write("default drift by user:")
        if not audit["default_details"]:
            write("  (none)")
        for record in audit["default_details"]:
            if printed >= limit:
                write(f"  (detail output stopped at --limit {limit})")
                break
            user = record["user"]
            write(
                "  "
                + f"user_id={user.id} | username={user.get_username()}"
                + f" | legacy_default={_group_label(record['legacy_group'])}"
                + f" | candidate_default={_group_label(record['candidate_group'])}"
                + f" | same_default={record['same_default']}"
                + f" | mismatch={record['mismatch']}"
                + f" | reason={record['reason'] or ''}"
            )
            printed += 1
