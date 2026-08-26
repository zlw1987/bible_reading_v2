"""Directed notifications for committed Worship Team selection changes.

The producer accepts immutable before/after facts from the two governed source
mutations. It resolves the bounded exact-team recipient snapshot inside the
source transaction and emits only fully built payloads through Core.
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime

from django.urls import reverse
from django.utils import timezone

from core.notification_delivery import emit_notification

from ..models import MinistryTeam, TeamAssignment
from ..permissions import current_ministry_management_role_assignments
from .worship_governance import resolve_worship_rotation_pool_for_team


CURRENT_DOWNSTREAM_ASSIGNMENT_STATUSES = (
    TeamAssignment.STATUS_SCHEDULED,
    TeamAssignment.STATUS_CONFIRMED,
    TeamAssignment.STATUS_PREPARED,
)


@dataclass(frozen=True)
class WorshipTeamChangeFact:
    """Exact source facts for one actual committed-intent anchor change."""

    event_id: int
    event_start_datetime: datetime
    old_team_id: int | None
    new_team_id: int | None


def _recipient_language(user):
    profile = getattr(user, "profile", None)
    return "zh" if getattr(profile, "preferred_language", None) == "zh" else "en"


def _localized_date(value, language):
    local_date = timezone.localtime(value).date()
    if language == "zh":
        return f"{local_date.year}年{local_date.month}月{local_date.day}日"
    return local_date.strftime("%b %d, %Y").replace(" 0", " ")


def _is_canonical_worship_team(team):
    # A resolved configured pool excludes a downstream team even when the pool
    # is currently unusable. Malformed/unresolved paths fail closed without
    # display-name, team-kind, or secondary-path guesses.
    return resolve_worship_rotation_pool_for_team(team).pool is not None


def _team_name(team_id, *, language, teams_by_id):
    if team_id is None:
        return "未选择" if language == "zh" else "Not selected"
    team = teams_by_id.get(team_id)
    if team is None:
        raise ValueError("A Worship change fact references a missing team.")
    return team.get_name(language)


def _change_text(fact, *, language, teams_by_id, separator=" · "):
    return (
        f"{_localized_date(fact.event_start_datetime, language)}{separator}"
        f"{_team_name(fact.old_team_id, language=language, teams_by_id=teams_by_id)}"
        " → "
        f"{_team_name(fact.new_team_id, language=language, teams_by_id=teams_by_id)}"
    )


def _recipient_change_subsets(changes):
    """Return users mapped only to changed events where they qualify."""

    changes = tuple(changes)
    event_ids = {change.event_id for change in changes}
    referenced_team_ids = {
        team_id
        for change in changes
        for team_id in (change.old_team_id, change.new_team_id)
        if team_id is not None
    }
    teams_by_id = MinistryTeam.objects.in_bulk(referenced_team_ids)
    missing_team_ids = referenced_team_ids - set(teams_by_id)
    if missing_team_ids:
        raise ValueError("A Worship change fact references a missing team.")

    qualifying_team_ids = {
        change.event_id: {
            team_id
            for team_id in (change.old_team_id, change.new_team_id)
            if team_id is not None
            and teams_by_id[team_id].is_active
        }
        for change in changes
    }

    required_teams = MinistryTeam.objects.filter(
        is_active=True,
        required_event_links__service_event_id__in=event_ids,
    ).distinct()
    for team in required_teams:
        teams_by_id[team.pk] = team
        if _is_canonical_worship_team(team):
            continue
        for event_id in team.required_event_links.filter(
            service_event_id__in=event_ids
        ).values_list("service_event_id", flat=True):
            qualifying_team_ids[event_id].add(team.pk)

    assignments = TeamAssignment.objects.filter(
        service_event_id__in=event_ids,
        status__in=CURRENT_DOWNSTREAM_ASSIGNMENT_STATUSES,
        ministry_team__is_active=True,
    ).select_related("ministry_team")
    for assignment in assignments:
        team = assignment.ministry_team
        teams_by_id[team.pk] = team
        if not _is_canonical_worship_team(team):
            qualifying_team_ids[assignment.service_event_id].add(team.pk)

    all_qualifying_team_ids = set().union(*qualifying_team_ids.values())
    users_by_team = defaultdict(dict)
    roles = (
        current_ministry_management_role_assignments(
            team_ids=all_qualifying_team_ids
        )
        .filter(user__is_active=True)
        .select_related("user__profile")
        .order_by("user_id", "id")
    )
    for role in roles:
        users_by_team[role.team_id][role.user_id] = role.user

    recipient_changes = defaultdict(list)
    recipients = {}
    for change in changes:
        event_users = {}
        for team_id in qualifying_team_ids[change.event_id]:
            event_users.update(users_by_team[team_id])
        for user_id, user in event_users.items():
            recipients[user_id] = user
            recipient_changes[user_id].append(change)

    for user_id in recipient_changes:
        recipient_changes[user_id].sort(
            key=lambda item: (item.event_start_datetime, item.event_id)
        )
    return recipients, recipient_changes, teams_by_id


def emit_worship_team_change_notifications(
    change, *, logentry_id, actor=None
):
    """Register one selector-change payload per unique qualifying user."""

    recipients, subsets, teams_by_id = _recipient_change_subsets((change,))
    emitted = 0
    for user_id in sorted(subsets):
        recipient = recipients[user_id]
        language = _recipient_language(recipient)
        emitted += int(
            emit_notification(
                recipient=recipient,
                source_module="ministry",
                notification_type="worship_team.changed",
                title=(
                    "敬拜团队已调整"
                    if language == "zh"
                    else "Worship Team changed"
                ),
                body=_change_text(
                    change, language=language, teams_by_id=teams_by_id
                ),
                target_url=reverse("my_serving"),
                dedupe_key=(
                    f"ministry:worship_team_change:log:{logentry_id}"
                ),
                source_model_label="events.ServiceEvent",
                source_object_id=str(change.event_id),
                actor=actor,
                metadata={},
            )
        )
    return emitted


def emit_worship_rotation_change_notifications(
    changes, *, operation_id, actor=None
):
    """Register one recipient-private summary per batch recipient."""

    changes = tuple(changes)
    if not changes:
        return 0
    recipients, subsets, teams_by_id = _recipient_change_subsets(changes)
    emitted = 0
    dedupe_key = f"ministry:worship_rotation:{operation_id}"
    for user_id in sorted(subsets):
        recipient = recipients[user_id]
        relevant = subsets[user_id]
        language = _recipient_language(recipient)
        count = len(relevant)
        if language == "zh":
            title = "敬拜轮值已更新"
            prefix = f"与您团队相关的 {count} 个主日已更新："
            remainder = f"另有 {count - 3} 个主日"
        else:
            title = "Worship rotation updated"
            prefix = (
                "1 Sunday affecting your team was updated:"
                if count == 1
                else f"{count} Sundays affecting your team were updated:"
            )
            remainder = f"+ {count - 3} more"
        lines = [prefix]
        lines.extend(
            _change_text(
                change,
                language=language,
                teams_by_id=teams_by_id,
                separator=" ",
            )
            for change in relevant[:3]
        )
        if count > 3:
            lines.append(remainder)
        emitted += int(
            emit_notification(
                recipient=recipient,
                source_module="ministry",
                notification_type="worship_rotation.changed",
                title=title,
                body="\n".join(lines),
                target_url=reverse("my_serving"),
                dedupe_key=dedupe_key,
                source_model_label="",
                source_object_id="",
                actor=actor,
                metadata={
                    "operation_id": str(operation_id),
                    "recipient_relevant_event_count": count,
                },
            )
        )
    return emitted
