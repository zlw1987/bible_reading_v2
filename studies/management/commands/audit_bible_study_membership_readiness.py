"""Read-only Bible Study membership-core readiness/shadow audit.

CS-CORE.2C-A diagnostic command. For every active user and every in-scope
Bible Study meeting it compares the current runtime visibility source
(``Profile.small_group`` via ``BibleStudyMeeting.can_be_seen_by``) against the
future membership-core candidate source (active primary
``ChurchStructureMembership`` against the meeting small group's mapped
``ChurchStructureUnit``). It also reports per-meeting and per-user readiness
problems that would make a future runtime switch unsafe.

It is shadow/readiness only: it writes nothing, has no ``--apply``, and does
not change Bible Study, ServiceEvent, or any other runtime visibility.
"""

from collections import OrderedDict

from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from studies.models import BibleStudyLesson, BibleStudyMeeting, BibleStudySeries
from studies.structure_readiness import (
    CLASSIFICATION_WOULD_GAIN,
    CLASSIFICATION_WOULD_LOSE,
    compare_bible_study_meeting_visibility,
    get_user_active_primary_memberships,
)


PAIR_CATEGORY_KEYS = (
    "same_visible",
    "same_hidden",
    "would_gain",
    "would_lose",
)

MEETING_CATEGORY_KEYS = ("meeting_unmapped_small_group",)

USER_CATEGORY_KEYS = (
    "user_group_without_active_primary_membership",
    "user_active_primary_without_profile_group",
    "user_profile_membership_mismatch",
    "user_profile_group_unmapped",
    "multiple_active_primary_memberships",
)

# Categories that make a future Bible Study visibility switch unsafe.
#
# - would_gain / would_lose: the two sources disagree for a real user/meeting
#   pair, so flipping the source would change what someone sees today.
# - meeting_unmapped_small_group: the meeting's group cannot be matched by
#   membership-core at all; after a switch only staff/managers would see it.
# - user_group_without_active_primary_membership: the user is visible via
#   legacy today and would lose visibility on the next meeting of their group
#   after a switch, even if no such meeting is currently in scope.
# - user_profile_membership_mismatch: the two sources point at different
#   units, so the switch silently moves the user's Bible Study visibility.
# - multiple_active_primary_memberships: ambiguous belonging fails closed in
#   membership-core matching, hiding meetings the user can currently see.
#
# Deliberately not failing:
# - user_active_primary_without_profile_group: legacy grants nothing today, so
#   a switch can only add visibility; any actual in-scope effect already shows
#   up (and fails) as would_gain.
# - user_profile_group_unmapped: any in-scope Bible Study effect already shows
#   up as meeting_unmapped_small_group / would_lose; without an in-scope
#   meeting it is general belonging drift owned by audit_structure_belonging.
DRIFT_FAIL_KEYS = (
    "would_gain",
    "would_lose",
    "meeting_unmapped_small_group",
    "user_group_without_active_primary_membership",
    "user_profile_membership_mismatch",
    "multiple_active_primary_memberships",
)

# Verbose mode prints detail rows only for these categories; same_visible and
# same_hidden pairs are summary-only to keep output operational.
VERBOSE_DETAIL_KEYS = (
    "would_gain",
    "would_lose",
    "meeting_unmapped_small_group",
    "user_group_without_active_primary_membership",
    "user_active_primary_without_profile_group",
    "user_profile_membership_mismatch",
    "user_profile_group_unmapped",
    "multiple_active_primary_memberships",
)

ALL_CATEGORY_KEYS = PAIR_CATEGORY_KEYS + MEETING_CATEGORY_KEYS + USER_CATEGORY_KEYS


def _new_stats():
    return OrderedDict((key, 0) for key in ALL_CATEGORY_KEYS)


def _audited_meetings(include_past):
    """Return the meetings in audit scope.

    Default scope mirrors what ordinary members can currently reach: upcoming
    meetings whose meeting, lesson, and series are member-visible (published
    or completed status, active series). Draft and cancelled rows are excluded
    because no ordinary member can see them under either source.
    ``include_past`` widens the window to past meetings (detail pages still
    serve them) without relaxing the publish gates.
    """
    meetings = (
        BibleStudyMeeting.objects.filter(
            status__in=[
                BibleStudyMeeting.STATUS_PUBLISHED,
                BibleStudyMeeting.STATUS_COMPLETED,
            ],
            lesson__status__in=[
                BibleStudyLesson.STATUS_PUBLISHED,
                BibleStudyLesson.STATUS_COMPLETED,
            ],
            lesson__series__is_active=True,
            lesson__series__status__in=[
                BibleStudySeries.STATUS_PUBLISHED,
                BibleStudySeries.STATUS_COMPLETED,
            ],
        )
        .select_related(
            "lesson",
            "lesson__series",
            "small_group",
            "small_group__church_structure_unit",
        )
        .order_by("meeting_datetime", "id")
    )
    if not include_past:
        meetings = meetings.filter(meeting_datetime__gte=timezone.now())
    return meetings


def _group_label(group):
    if group is None:
        return ""
    return f"#{group.id} {group.name}"


def _unit_label(unit):
    if unit is None:
        return ""
    return f"#{unit.id} {unit.code}"


def _meeting_label(meeting):
    return (
        f"meeting_id={meeting.id}"
        f" | small_group={_group_label(meeting.small_group)}"
        f" | meeting_datetime={meeting.meeting_datetime.isoformat()}"
    )


def _classify_user(user, memberships):
    """Return the readiness categories that apply to one user.

    Unlike audit_structure_belonging's single classification, these are
    independent readiness flags and one user can hit more than one.
    """
    try:
        profile = user.profile
    except ObjectDoesNotExist:
        profile = None

    group = profile.small_group if profile else None
    group_unit = group.church_structure_unit if group else None
    categories = []

    if len(memberships) > 1:
        categories.append("multiple_active_primary_memberships")
    if group is not None and not memberships:
        categories.append("user_group_without_active_primary_membership")
    if memberships and group is None:
        categories.append("user_active_primary_without_profile_group")
    if group is not None and group_unit is None:
        categories.append("user_profile_group_unmapped")
    if (
        group_unit is not None
        and len(memberships) == 1
        and memberships[0].unit_id != group_unit.id
    ):
        categories.append("user_profile_membership_mismatch")

    return categories, group, group_unit


def _format_user_line(user, group, group_unit, memberships, category):
    membership = memberships[0] if len(memberships) == 1 else None
    parts = [
        f"user_id={user.id}",
        f"username={user.get_username()}",
        f"profile_small_group={_group_label(group)}",
        f"profile_group_unit={_unit_label(group_unit)}",
        f"active_primary_membership_unit={_unit_label(membership.unit) if membership else ''}",
        f"category={category}",
    ]
    if len(memberships) > 1:
        parts.append(
            "active_primary_membership_ids="
            + ",".join(str(item.id) for item in memberships)
        )
    return "  " + " | ".join(parts)


def _format_pair_line(user, meeting, result):
    parts = [
        f"user_id={user.id}",
        f"username={user.get_username()}",
        _meeting_label(meeting),
        f"legacy_visible={result['legacy_visible']}",
        f"membership_visible={result['membership_visible']}",
        f"classification={result['classification']}",
        "reasons=" + ",".join(result["reason_codes"]),
    ]
    return "  " + " | ".join(parts)


def run_audit(include_past=False, target_date=None):
    """Return read-only readiness audit data.

    The returned dict contains summary stats, per-category detail rows, and
    scope counts. It never creates, edits, or deletes any row.
    """
    target_date = target_date or timezone.localdate()
    stats = _new_stats()
    details = OrderedDict((key, []) for key in VERBOSE_DETAIL_KEYS)

    meetings = list(_audited_meetings(include_past))
    for meeting in meetings:
        if meeting.small_group.church_structure_unit_id is None:
            stats["meeting_unmapped_small_group"] += 1
            details["meeting_unmapped_small_group"].append(
                "  " + _meeting_label(meeting) + " | category=meeting_unmapped_small_group"
            )

    User = get_user_model()
    users = list(
        User.objects.filter(is_active=True)
        .select_related("profile__small_group__church_structure_unit")
        .order_by("username", "id")
    )

    for user in users:
        memberships = get_user_active_primary_memberships(
            user, target_date=target_date
        )
        categories, group, group_unit = _classify_user(user, memberships)
        for category in categories:
            stats[category] += 1
            details[category].append(
                _format_user_line(user, group, group_unit, memberships, category)
            )

        for meeting in meetings:
            result = compare_bible_study_meeting_visibility(
                user, meeting, target_date=target_date
            )
            classification = result["classification"]
            stats[classification] += 1
            if classification in (
                CLASSIFICATION_WOULD_GAIN,
                CLASSIFICATION_WOULD_LOSE,
            ):
                details[classification].append(
                    _format_pair_line(user, meeting, result)
                )

    return {
        "stats": stats,
        "details": details,
        "target_date": target_date,
        "meetings_audited": len(meetings),
        "users_audited": len(users),
        "include_past": include_past,
    }


class Command(BaseCommand):
    help = (
        "Audit Bible Study membership-core readiness (CS-CORE.2C-A). "
        "Read-only shadow comparison of current Profile.small_group meeting "
        "visibility vs the future active primary ChurchStructureMembership "
        "source. Default scope: upcoming member-visible meetings (published/"
        "completed meeting, lesson, and active series); --include-past widens "
        "to past meetings. Writes nothing and changes no runtime visibility."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--verbose",
            action="store_true",
            help=(
                "Print limited detail rows for drift and readiness "
                "categories (would_gain/would_lose pairs, unmapped meetings, "
                "per-user readiness flags). Never prints membership notes."
            ),
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Maximum number of verbose detail rows to print.",
        )
        parser.add_argument(
            "--include-past",
            action="store_true",
            help=(
                "Also audit past meetings (detail pages still serve them). "
                "Default scope is upcoming meetings only."
            ),
        )
        parser.add_argument(
            "--fail-on-drift",
            action="store_true",
            help=(
                "Exit with an error when any switch-unsafe category is "
                "nonzero: would_gain, would_lose, "
                "meeting_unmapped_small_group, "
                "user_group_without_active_primary_membership, "
                "user_profile_membership_mismatch, "
                "multiple_active_primary_memberships. Still read-only; "
                "nothing is changed or reconciled."
            ),
        )

    def handle(self, *args, **options):
        if options["limit"] is not None and options["limit"] < 0:
            raise CommandError("--limit must be zero or greater.")

        audit = run_audit(include_past=options["include_past"])
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
                    "Bible Study membership readiness drift detected "
                    "(--fail-on-drift): " + ", ".join(drifted)
                )

    def _print_report(self, audit, *, verbose, limit):
        write = self.stdout.write
        stats = audit["stats"]

        write(
            "Bible Study membership-core readiness audit "
            "(CS-CORE.2C-A, read-only shadow)"
        )
        write("=" * 68)
        write(f"target_date: {audit['target_date'].isoformat()}")
        write(
            "meeting scope: "
            + (
                "member-visible meetings (including past)"
                if audit["include_past"]
                else "upcoming member-visible meetings"
            )
        )
        write(f"meetings_audited: {audit['meetings_audited']}")
        write(f"users_audited: {audit['users_audited']}")
        write("summary:")
        write("  user/meeting visibility comparison:")
        for key in PAIR_CATEGORY_KEYS:
            write(f"    {key}: {stats[key]}")
        write("  meeting readiness:")
        for key in MEETING_CATEGORY_KEYS:
            write(f"    {key}: {stats[key]}")
        write("  user readiness:")
        for key in USER_CATEGORY_KEYS:
            write(f"    {key}: {stats[key]}")
        write("")
        write(
            "Audit only: Bible Study runtime visibility is unchanged; no "
            "meeting, session, membership, profile, group, unit, mapping, or "
            "audience row was changed."
        )

        if not verbose:
            return

        write("")
        write("details (drift and readiness categories only):")
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
