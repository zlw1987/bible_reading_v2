"""Read-only belonging drift audit for the church structure migration.

CS-CORE.0B.1 diagnostic command. It compares the future belonging foundation
(``ChurchStructureMembership``) with the current runtime belonging source
(``Profile.small_group``) and writes nothing.
"""

from collections import OrderedDict, defaultdict

from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Count, Q
from django.utils import timezone

from accounts.models import ChurchStructureMembership, SmallGroup


CATEGORY_KEYS = (
    "in_sync",
    "membership_without_group",
    "group_without_membership",
    "mismatch",
    "unmapped_group",
    "parent_or_fellowship_only_membership",
    "no_group_no_membership",
)

WARNING_KEYS = ("multiple_active_primary_memberships",)


def _new_stats():
    stats = OrderedDict((key, 0) for key in CATEGORY_KEYS)
    for key in WARNING_KEYS:
        stats[key] = 0
    return stats


def _active_primary_memberships(target_date):
    return (
        ChurchStructureMembership.objects.filter(
            status=ChurchStructureMembership.STATUS_ACTIVE,
            is_primary=True,
            start_date__lte=target_date,
        )
        .filter(Q(end_date__isnull=True) | Q(end_date__gte=target_date))
        .select_related("unit")
        .order_by("user_id", "id")
    )


def _active_legacy_group_counts_by_unit():
    return dict(
        SmallGroup.objects.filter(
            is_active=True,
            church_structure_unit__isnull=False,
        )
        .values("church_structure_unit_id")
        .annotate(group_count=Count("id"))
        .values_list("church_structure_unit_id", "group_count")
    )


def _unit_label(unit):
    if unit is None:
        return ""
    return f"#{unit.id} {unit.code} {unit.display_name('en')}".strip()


def _group_label(group):
    if group is None:
        return ""
    return f"#{group.id} {group.name}"


def _user_display_name(user):
    display_name = user.get_full_name().strip()
    return display_name


def _classify_user(user, memberships, syncable_group_counts):
    try:
        profile = user.profile
    except ObjectDoesNotExist:
        profile = None

    group = profile.small_group if profile else None
    group_unit = group.church_structure_unit if group else None
    membership = memberships[0] if memberships else None
    multiple_primary_ids = [item.id for item in memberships]

    if group is not None and group_unit is None:
        return {
            "category": "unmapped_group",
            "reason": "Profile.small_group has no ChurchStructureUnit mapping.",
            "group": group,
            "group_unit": None,
            "membership": membership,
            "multiple_primary_ids": multiple_primary_ids,
        }

    if membership is not None:
        syncable_group_count = syncable_group_counts.get(membership.unit_id, 0)

        if syncable_group_count != 1 and (
            group is None or group_unit and group_unit.id == membership.unit_id
        ):
            return {
                "category": "parent_or_fellowship_only_membership",
                "reason": (
                    "Active primary membership unit maps to "
                    f"{syncable_group_count} active legacy small groups; "
                    "approval sync requires exactly one."
                ),
                "group": group,
                "group_unit": group_unit,
                "membership": membership,
                "multiple_primary_ids": multiple_primary_ids,
            }

        if group is None:
            return {
                "category": "membership_without_group",
                "reason": (
                    "User has an active primary membership but no "
                    "Profile.small_group."
                ),
                "group": None,
                "group_unit": None,
                "membership": membership,
                "multiple_primary_ids": multiple_primary_ids,
            }

        if group_unit.id == membership.unit_id:
            return {
                "category": "in_sync",
                "reason": (
                    "Profile.small_group mapping matches the active primary "
                    "membership unit."
                ),
                "group": group,
                "group_unit": group_unit,
                "membership": membership,
                "multiple_primary_ids": multiple_primary_ids,
            }

        return {
            "category": "mismatch",
            "reason": (
                "Profile.small_group mapped unit differs from the active "
                "primary membership unit."
            ),
            "group": group,
            "group_unit": group_unit,
            "membership": membership,
            "multiple_primary_ids": multiple_primary_ids,
        }

    if group is not None:
        return {
            "category": "group_without_membership",
            "reason": "User has Profile.small_group but no active primary membership.",
            "group": group,
            "group_unit": group_unit,
            "membership": None,
            "multiple_primary_ids": multiple_primary_ids,
        }

    return {
        "category": "no_group_no_membership",
        "reason": "User has neither Profile.small_group nor active primary membership.",
        "group": None,
        "group_unit": None,
        "membership": None,
        "multiple_primary_ids": multiple_primary_ids,
    }


def _format_user_line(user, row):
    membership = row["membership"]
    membership_unit = membership.unit if membership else None
    multiple_primary = row["multiple_primary_ids"]
    parts = [
        f"user_id={user.id}",
        f"username={user.get_username()}",
        f"display_name={_user_display_name(user)}",
        f"profile_small_group={_group_label(row['group'])}",
        f"profile_group_unit={_unit_label(row['group_unit'])}",
        f"active_primary_membership_id={membership.id if membership else ''}",
        f"membership_unit={_unit_label(membership_unit)}",
        f"classification={row['category']}",
        f"reason={row['reason']}",
    ]
    if len(multiple_primary) > 1:
        parts.append(
            "multiple_active_primary_membership_ids="
            + ",".join(str(pk) for pk in multiple_primary)
        )
    return "  " + " | ".join(parts)


def run_audit(target_date=None):
    """Return read-only audit data for all users.

    The returned dict contains summary stats and per-category detail rows.
    It does not create, edit, or delete any row.
    """
    target_date = target_date or timezone.localdate()
    stats = _new_stats()
    details = OrderedDict((key, []) for key in CATEGORY_KEYS)
    warnings = []

    memberships_by_user = defaultdict(list)
    for membership in _active_primary_memberships(target_date):
        memberships_by_user[membership.user_id].append(membership)

    syncable_group_counts = _active_legacy_group_counts_by_unit()
    User = get_user_model()
    users = User.objects.select_related(
        "profile__small_group__church_structure_unit"
    ).order_by("username", "id")

    for user in users:
        memberships = memberships_by_user.get(user.id, [])
        row = _classify_user(user, memberships, syncable_group_counts)
        stats[row["category"]] += 1
        details[row["category"]].append((user, row))

        if len(memberships) > 1:
            stats["multiple_active_primary_memberships"] += 1
            warnings.append(
                "User "
                f"{user.get_username()} has multiple active primary memberships: "
                + ", ".join(str(item.id) for item in memberships)
                + ". Classified using the first membership in command ordering."
            )

    return {
        "stats": stats,
        "details": details,
        "warnings": warnings,
        "target_date": target_date,
    }


class Command(BaseCommand):
    help = (
        "Audit drift between ChurchStructureMembership and Profile.small_group. "
        "Read-only CS-CORE.0B.1 diagnostic; creates, edits, and deletes nothing."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--verbose",
            action="store_true",
            help="Print per-user audit details grouped by classification.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Maximum number of verbose user detail rows to print.",
        )

    def handle(self, *args, **options):
        if options["limit"] is not None and options["limit"] < 0:
            raise CommandError("--limit must be zero or greater.")

        audit = run_audit()
        self._print_report(
            audit,
            verbose=options["verbose"],
            limit=options["limit"],
        )

    def _print_report(self, audit, *, verbose, limit):
        write = self.stdout.write
        stats = audit["stats"]

        write("Church structure belonging drift audit (CS-CORE.0B.1, read-only)")
        write("=" * 68)
        write(f"target_date: {audit['target_date'].isoformat()}")
        write("summary:")
        for key in CATEGORY_KEYS:
            write(f"  {key}: {stats[key]}")
        write(
            "  multiple_active_primary_memberships: "
            f"{stats['multiple_active_primary_memberships']}"
        )
        write("")
        write(
            "Audit only: no Profile.small_group, ChurchStructureMembership, "
            "ChurchStructureUnit, SmallGroup, District, MinistryContext, "
            "audience, role, or assignment rows were changed."
        )

        if audit["warnings"]:
            write("")
            write("warnings:")
            for warning in audit["warnings"]:
                write(f"  WARNING: {warning}")

        if not verbose:
            return

        write("")
        write("per-user details:")
        printed = 0
        stopped_by_limit = False
        for category, rows in audit["details"].items():
            write(f"{category}:")
            if not rows:
                write("  (none)")
                continue

            for user, row in rows:
                if limit is not None and printed >= limit:
                    stopped_by_limit = True
                    break
                write(_format_user_line(user, row))
                printed += 1

            if stopped_by_limit:
                break

        if stopped_by_limit:
            write(f"  (verbose output stopped at --limit {limit})")
