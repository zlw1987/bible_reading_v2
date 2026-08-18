"""Read-only Worship rotation-pool configuration inspection.

MO-S.6D-1B configuration metadata is not an authorization or applicability
decision. This module follows only the active primary Ministry Structure path
to validate one configured pool and intentionally accepts no ServiceEvent or
user. It creates, updates, and deletes nothing.
"""

from dataclasses import dataclass
from enum import StrEnum

from django.db.models import Q
from django.utils import timezone

from accounts.models import ChurchStructureUnit

from .models import MinistryTeam, MinistryTeamRoleAssignment, MinistryTeamRoleType


class WorshipRotationPoolStatus(StrEnum):
    NOT_POOL = "not_pool"
    INACTIVE_POOL = "inactive_pool"
    ASSIGNABLE_POOL = "assignable_pool"
    MISSING_PRIMARY_PATH = "missing_primary_path"
    AMBIGUOUS_PRIMARY_PATH = "ambiguous_primary_path"
    CYCLIC_PRIMARY_PATH = "cyclic_primary_path"
    BROKEN_PRIMARY_PATH = "broken_primary_path"
    INACTIVE_PRIMARY_TEAM = "inactive_primary_team"
    INACTIVE_CHURCH_ANCHOR = "inactive_church_anchor"
    VALID = "valid"


@dataclass(frozen=True)
class WorshipRotationPoolInspection:
    status: WorshipRotationPoolStatus
    anchor: ChurchStructureUnit | None = None
    has_active_leadership: bool = False

    @property
    def is_usable(self):
        return self.status == WorshipRotationPoolStatus.VALID


def _has_active_lead_or_coordinator(team, target_date):
    """Canonical exact-team role-source readiness; never a permission grant."""
    return (
        MinistryTeamRoleAssignment.objects.filter(
            team=team,
            team__is_active=True,
            is_active=True,
            role_type__is_active=True,
            role_type__code__in=(
                MinistryTeamRoleType.CODE_LEAD,
                MinistryTeamRoleType.CODE_COORDINATOR,
            ),
            user__is_active=True,
            start_date__lte=target_date,
        )
        .filter(Q(end_date__isnull=True) | Q(end_date__gte=target_date))
        .exists()
    )


def inspect_worship_rotation_pool(team, target_date=None):
    """Return a fail-closed, side-effect-free configuration inspection.

    Only active primary links establish the V1 path. Secondary links are
    ignored. Every step must have exactly one active primary link until the
    path reaches one active Church Structure anchor.
    """
    if team is None or not team.is_worship_rotation_pool:
        return WorshipRotationPoolInspection(WorshipRotationPoolStatus.NOT_POOL)

    if not team.is_active:
        return WorshipRotationPoolInspection(
            WorshipRotationPoolStatus.INACTIVE_POOL
        )

    if team.is_assignable:
        return WorshipRotationPoolInspection(
            WorshipRotationPoolStatus.ASSIGNABLE_POOL
        )

    seen_team_ids = set()
    current = team

    while True:
        if current.pk is None or current.pk in seen_team_ids:
            return WorshipRotationPoolInspection(
                WorshipRotationPoolStatus.CYCLIC_PRIMARY_PATH
            )
        seen_team_ids.add(current.pk)

        primary_links = list(
            current.parent_links.filter(is_active=True, is_primary=True)
            .select_related("parent_team", "parent_church_unit")
            .order_by("sort_order", "id")[:2]
        )
        if not primary_links:
            return WorshipRotationPoolInspection(
                WorshipRotationPoolStatus.MISSING_PRIMARY_PATH
            )
        if len(primary_links) != 1:
            return WorshipRotationPoolInspection(
                WorshipRotationPoolStatus.AMBIGUOUS_PRIMARY_PATH
            )

        link = primary_links[0]
        has_parent_team = link.parent_team_id is not None
        has_church_anchor = link.parent_church_unit_id is not None
        if has_parent_team == has_church_anchor:
            return WorshipRotationPoolInspection(
                WorshipRotationPoolStatus.BROKEN_PRIMARY_PATH
            )

        if has_church_anchor:
            anchor = link.parent_church_unit
            if anchor is None:
                return WorshipRotationPoolInspection(
                    WorshipRotationPoolStatus.BROKEN_PRIMARY_PATH
                )
            if not anchor.is_active:
                return WorshipRotationPoolInspection(
                    WorshipRotationPoolStatus.INACTIVE_CHURCH_ANCHOR,
                    anchor=anchor,
                )
            target_date = target_date or timezone.localdate()
            return WorshipRotationPoolInspection(
                WorshipRotationPoolStatus.VALID,
                anchor=anchor,
                has_active_leadership=_has_active_lead_or_coordinator(
                    team, target_date
                ),
            )

        parent_team = link.parent_team
        if parent_team is None:
            return WorshipRotationPoolInspection(
                WorshipRotationPoolStatus.BROKEN_PRIMARY_PATH
            )
        if not parent_team.is_active:
            return WorshipRotationPoolInspection(
                WorshipRotationPoolStatus.INACTIVE_PRIMARY_TEAM
            )
        current = parent_team
