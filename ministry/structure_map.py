"""Read-only ministry-structure map builder (MINISTRY-STRUCTURE.1C).

This module turns the additive ministry-structure foundation
(``MinistryTeam`` + ``MinistryTeamParentLink`` + the ministry role system,
added in MINISTRY-STRUCTURE.1B) into simple display structures for a staff
read-only Ministry Structure page.

It is **read-only**. Nothing here creates, updates, or deletes any row, drives
any permission, or changes runtime behavior:

- A ``ChurchStructureUnit`` parent is a *display anchor only*. It never implies
  ``ChurchStructureMembership``, audience visibility, serving/``TeamAssignment``,
  My Serving, church-structure delegated management, member/care-record access,
  or any permission.
- ``MinistryTeamRoleAssignment`` (including ``lead``) is read here purely to
  surface readiness signals. It is never treated as a permission source, and
  ``can_manage_ministry_team`` / ``TeamAssignment`` are not consulted or changed.
- Membership (``TeamMembership``) is *not* read as serving, leadership, or
  permission.

The builder defends against cyclic/bad data even though
``MinistryTeamParentLink.clean`` already prevents ministry cycles.
"""

from dataclasses import dataclass, field

from django.db.models import Q
from django.utils import timezone

from .models import (
    MinistryTeam,
    MinistryTeamParentLink,
    MinistryTeamRoleAssignment,
)


LEAD_ROLE_CODE = "lead"


TEAM_KIND_LABELS = {
    "zh": {
        MinistryTeam.KIND_MINISTRY_AREA: "事工范畴",
        MinistryTeam.KIND_DEPARTMENT: "部门",
        MinistryTeam.KIND_TEAM: "团队",
        MinistryTeam.KIND_SUBTEAM: "子团队",
        MinistryTeam.KIND_PROJECT_GROUP: "项目小组",
        MinistryTeam.KIND_CUSTOM: "自定义",
    },
    "en": {
        MinistryTeam.KIND_MINISTRY_AREA: "Ministry Area",
        MinistryTeam.KIND_DEPARTMENT: "Department",
        MinistryTeam.KIND_TEAM: "Team",
        MinistryTeam.KIND_SUBTEAM: "Subteam",
        MinistryTeam.KIND_PROJECT_GROUP: "Project Group",
        MinistryTeam.KIND_CUSTOM: "Custom",
    },
}


def team_kind_label(kind, language="zh"):
    table = TEAM_KIND_LABELS.get(language, TEAM_KIND_LABELS["en"])
    return table.get(kind, kind)


def team_kind_options(language="zh"):
    """Bilingual ``(value, label)`` options for an optional kind filter."""
    return [
        (value, team_kind_label(value, language))
        for value, _label in MinistryTeam.TEAM_KIND_CHOICES
    ]


@dataclass
class MinistryTeamStructureSetupSummary:
    """Read-only structure-setup signals for one ministry team (1H).

    A compact, cheap summary used by the staff-only structure entry points on the
    Ministry Team detail/list pages. Display/readiness only: every field is
    derived from existing read-only model helpers and nothing here grants
    membership, serving/``TeamAssignment``, ``can_manage_ministry_team``, or any
    permission. ``has_warnings`` is a convenience flag for "this unit needs
    structure setup attention", never a behavior gate.
    """

    team_id: int
    team_kind: str
    team_kind_label: str
    is_assignable: bool
    is_active: bool
    has_role_profile: bool
    role_profile_label: str
    display_path: str
    has_active_parent_link: bool
    has_primary_parent: bool
    is_unanchored: bool
    has_no_primary_parent: bool
    missing_required_role_labels: list = field(default_factory=list)
    missing_required_role_count: int = 0
    missing_lead: bool = False
    has_warnings: bool = False


def build_team_structure_setup_summary(
    team, language="zh", target_date=None, include_path=True
):
    """Build a read-only :class:`MinistryTeamStructureSetupSummary` for ``team``.

    Cheap and read-only: it reads only the team's active parent links, role
    profile, and missing-required-role helper (all existing read-only model
    helpers) and mutates nothing. ``include_path=False`` skips the breadcrumb walk
    for list views where the display path is not shown. This never reads
    ``ChurchStructureMembership`` as serving and drives no permission.
    """
    target_date = target_date or timezone.localdate()

    active_links = list(team.active_parent_links())
    has_active_parent_link = bool(active_links)
    has_primary_parent = any(link.is_primary for link in active_links)
    is_unanchored = not has_active_parent_link
    has_no_primary_parent = has_active_parent_link and not has_primary_parent

    missing = (
        team.missing_required_role_types(target_date) if team.is_active else []
    )
    missing_labels = [role_type.display_name(language) for role_type in missing]
    missing_lead = any(role_type.code == LEAD_ROLE_CODE for role_type in missing)

    has_role_profile = team.role_profile_id is not None
    role_profile_label = (
        team.role_profile.display_name(language) if has_role_profile else ""
    )

    has_warnings = bool(
        is_unanchored
        or has_no_primary_parent
        or not has_role_profile
        or missing_lead
        or missing_labels
    )

    return MinistryTeamStructureSetupSummary(
        team_id=team.id,
        team_kind=team.team_kind,
        team_kind_label=team_kind_label(team.team_kind, language),
        is_assignable=team.is_assignable,
        is_active=team.is_active,
        has_role_profile=has_role_profile,
        role_profile_label=role_profile_label,
        display_path=team.display_path_label(language) if include_path else "",
        has_active_parent_link=has_active_parent_link,
        has_primary_parent=has_primary_parent,
        is_unanchored=is_unanchored,
        has_no_primary_parent=has_no_primary_parent,
        missing_required_role_labels=missing_labels,
        missing_required_role_count=len(missing_labels),
        missing_lead=missing_lead,
        has_warnings=has_warnings,
    )


@dataclass
class MinistryStructureTeamCard:
    """Display signals for one ministry team node. No internal IDs are exposed
    in copy; ``team_id`` is used only for building detail links."""

    team_id: int
    name: str
    team_kind: str
    team_kind_label: str
    is_assignable: bool
    is_active: bool
    is_shared: bool
    active_parent_link_count: int
    lead_names: list = field(default_factory=list)
    active_lead_count: int = 0
    missing_required_role_labels: list = field(default_factory=list)
    missing_required_role_count: int = 0
    can_view_detail: bool = False
    path_label: str = ""


@dataclass
class MinistryStructureDisplayNode:
    """One placed occurrence of a team card inside the structure tree.

    ``is_primary_occurrence`` is ``True`` for the single expanded placement of a
    team (its primary parent link, or its first active link when no primary is
    flagged). Additional active parent links render as compact
    ``is_primary_occurrence=False`` reference nodes that are not expanded again.
    """

    card: MinistryStructureTeamCard
    depth: int
    is_primary_occurrence: bool = True


@dataclass
class MinistryStructureAnchorGroup:
    anchor_path: str
    anchor_id: int
    nodes: list = field(default_factory=list)


@dataclass
class MinistryStructureMap:
    anchor_groups: list = field(default_factory=list)
    unanchored_nodes: list = field(default_factory=list)
    inactive_nodes: list = field(default_factory=list)
    is_filtered: bool = False
    filtered_cards: list = field(default_factory=list)
    summary: dict = field(default_factory=dict)


def _normalize_filters(filters):
    filters = filters or {}
    kind = (filters.get("kind") or "").strip()
    if kind not in dict(MinistryTeam.TEAM_KIND_CHOICES):
        kind = ""
    assignable = (filters.get("assignable") or "").strip()
    if assignable not in {"assignable", "container"}:
        assignable = ""
    return {
        "q": (filters.get("q") or "").strip(),
        "kind": kind,
        "assignable": assignable,
        "missing_required": bool(filters.get("missing_required")),
        "unanchored": bool(filters.get("unanchored")),
    }


def _filters_active(normalized):
    return bool(
        normalized["q"]
        or normalized["kind"]
        or normalized["assignable"]
        or normalized["missing_required"]
        or normalized["unanchored"]
    )


def build_ministry_structure_map(
    user=None,
    language="zh",
    include_inactive=False,
    filters=None,
    target_date=None,
):
    """Build read-only ministry-structure display data.

    Returns a :class:`MinistryStructureMap`. When any filter is active the map is
    rendered as a flat ``filtered_cards`` list (with a display path for context)
    instead of the nested tree, which keeps filtered results readable without
    showing broken partial trees.
    """
    # Imported here to avoid a circular import at module load time.
    from .permissions import can_view_ministry_team

    target_date = target_date or timezone.localdate()
    normalized = _normalize_filters(filters)

    teams_qs = MinistryTeam.objects.all().select_related("role_profile")
    if not include_inactive:
        teams_qs = teams_qs.filter(is_active=True)
    teams = list(teams_qs)
    teams_by_id = {team.id: team for team in teams}
    team_ids = list(teams_by_id.keys())

    # Active links only participate in the tree. An active link already requires
    # an active child + active parent (model ``clean``), so inactive teams never
    # carry active parent links and always fall through to the inactive section.
    active_links = list(
        MinistryTeamParentLink.objects.filter(is_active=True)
        .select_related("parent_team", "parent_church_unit")
        .order_by("child_team_id", "sort_order", "id")
    )
    active_links_by_child = {}
    child_links_by_parent_team = {}
    for link in active_links:
        if link.child_team_id not in teams_by_id:
            continue
        if link.parent_team_id is not None and link.parent_team_id not in teams_by_id:
            # Parent team filtered out (e.g. include_inactive=False); skip edge.
            continue
        active_links_by_child.setdefault(link.child_team_id, []).append(link)
        if link.parent_team_id is not None:
            child_links_by_parent_team.setdefault(
                link.parent_team_id, []
            ).append(link)

    def primary_link_for(team_id):
        links = active_links_by_child.get(team_id)
        if not links:
            return None
        for link in links:
            if link.is_primary:
                return link
        return links[0]

    # --- Active lead names per team (readiness signal only) ----------------
    lead_names_by_team = {}
    lead_assignments = (
        MinistryTeamRoleAssignment.objects.filter(
            team_id__in=team_ids,
            is_active=True,
            role_type__code=LEAD_ROLE_CODE,
            start_date__lte=target_date,
        )
        .filter(Q(end_date__isnull=True) | Q(end_date__gte=target_date))
        .select_related("user")
    )
    for assignment in lead_assignments:
        user_obj = assignment.user
        name = ""
        if user_obj is not None:
            name = user_obj.get_full_name() or user_obj.username
        lead_names_by_team.setdefault(assignment.team_id, []).append(name)

    # --- Cards -------------------------------------------------------------
    card_by_id = {}

    def build_card(team, with_path=False):
        links = active_links_by_child.get(team.id, [])
        missing = team.missing_required_role_types(target_date) if team.is_active else []
        lead_names = lead_names_by_team.get(team.id, [])
        return MinistryStructureTeamCard(
            team_id=team.id,
            name=team.get_name(language),
            team_kind=team.team_kind,
            team_kind_label=team_kind_label(team.team_kind, language),
            is_assignable=team.is_assignable,
            is_active=team.is_active,
            is_shared=len(links) > 1,
            active_parent_link_count=len(links),
            lead_names=lead_names,
            active_lead_count=len(lead_names),
            missing_required_role_labels=[
                role_type.display_name(language) for role_type in missing
            ],
            missing_required_role_count=len(missing),
            can_view_detail=(
                can_view_ministry_team(user, team) if user is not None else False
            ),
            path_label=team.display_path_label(language) if with_path else "",
        )

    for team in teams:
        card_by_id[team.id] = build_card(team)

    summary = {
        "total_teams": len(teams),
        "active_teams": sum(1 for team in teams if team.is_active),
        "inactive_teams": sum(1 for team in teams if not team.is_active),
        "assignable_teams": sum(
            1 for team in teams if team.is_active and team.is_assignable
        ),
        "container_teams": sum(
            1 for team in teams if team.is_active and not team.is_assignable
        ),
        "shared_teams": sum(
            1
            for team_id, card in card_by_id.items()
            if card.is_active and card.is_shared
        ),
        "teams_missing_required_roles": sum(
            1
            for card in card_by_id.values()
            if card.is_active and card.missing_required_role_count
        ),
        "unanchored_teams": sum(
            1
            for team in teams
            if team.is_active and not active_links_by_child.get(team.id)
        ),
    }

    # --- Filtered (flat) mode ---------------------------------------------
    if _filters_active(normalized):
        q_value = normalized["q"].lower()
        flat = []
        for team in teams:
            if not team.is_active and not include_inactive:
                continue
            if normalized["kind"] and team.team_kind != normalized["kind"]:
                continue
            if normalized["assignable"] == "assignable" and not team.is_assignable:
                continue
            if normalized["assignable"] == "container" and team.is_assignable:
                continue
            links = active_links_by_child.get(team.id, [])
            if normalized["unanchored"] and links:
                continue
            card = card_by_id[team.id]
            if normalized["missing_required"] and not card.missing_required_role_count:
                continue
            if q_value:
                haystack = f"{team.name} {team.name_en}".lower()
                if q_value not in haystack:
                    continue
            flat.append(build_card(team, with_path=True))
        flat.sort(key=lambda card: card.name)
        return MinistryStructureMap(
            is_filtered=True,
            filtered_cards=flat,
            summary=summary,
        )

    # --- Tree mode ---------------------------------------------------------
    expanded = set()

    def flatten_subtree(team, depth, nodes):
        if team.id in expanded:
            # Already placed as a primary occurrence elsewhere (defensive: only
            # possible with cyclic bad data). Render a compact reference instead.
            nodes.append(
                MinistryStructureDisplayNode(
                    card=card_by_id[team.id],
                    depth=depth,
                    is_primary_occurrence=False,
                )
            )
            return
        expanded.add(team.id)
        nodes.append(
            MinistryStructureDisplayNode(
                card=card_by_id[team.id],
                depth=depth,
                is_primary_occurrence=True,
            )
        )
        for child_link in child_links_by_parent_team.get(team.id, []):
            child_id = child_link.child_team_id
            child_team = teams_by_id.get(child_id)
            if child_team is None:
                continue
            child_primary = primary_link_for(child_id)
            if child_primary is not None and child_primary.id == child_link.id:
                flatten_subtree(child_team, depth + 1, nodes)
            else:
                nodes.append(
                    MinistryStructureDisplayNode(
                        card=card_by_id[child_id],
                        depth=depth + 1,
                        is_primary_occurrence=False,
                    )
                )

    # Anchor groups keyed by church unit referenced by an active church link.
    anchor_units = {}
    anchor_team_links = {}
    for team in teams:
        for link in active_links_by_child.get(team.id, []):
            if link.parent_church_unit_id is not None:
                anchor_units.setdefault(
                    link.parent_church_unit_id, link.parent_church_unit
                )
                anchor_team_links.setdefault(link.parent_church_unit_id, []).append(
                    (team, link)
                )

    anchor_groups = []
    for anchor_id, anchor_unit in anchor_units.items():
        team_links = anchor_team_links.get(anchor_id, [])
        team_links.sort(key=lambda pair: card_by_id[pair[0].id].name)
        nodes = []
        for team, link in team_links:
            primary = primary_link_for(team.id)
            if primary is not None and primary.id == link.id:
                flatten_subtree(team, 0, nodes)
            else:
                nodes.append(
                    MinistryStructureDisplayNode(
                        card=card_by_id[team.id],
                        depth=0,
                        is_primary_occurrence=False,
                    )
                )
        anchor_groups.append(
            MinistryStructureAnchorGroup(
                anchor_path=anchor_unit.path_label(language),
                anchor_id=anchor_id,
                nodes=nodes,
            )
        )
    anchor_groups.sort(key=lambda group: group.anchor_path)

    # Unanchored active roots: active teams with no active parent links.
    unanchored_nodes = []
    unanchored_roots = [
        team
        for team in teams
        if team.is_active and not active_links_by_child.get(team.id)
    ]
    unanchored_roots.sort(key=lambda team: card_by_id[team.id].name)
    for team in unanchored_roots:
        flatten_subtree(team, 0, unanchored_nodes)

    # Defensive safety net: any active team not yet expanded (only reachable via
    # pathological cyclic data) is surfaced so nothing silently disappears.
    leftover = [
        team
        for team in teams
        if team.is_active and team.id not in expanded
    ]
    leftover.sort(key=lambda team: card_by_id[team.id].name)
    for team in leftover:
        flatten_subtree(team, 0, unanchored_nodes)

    # Inactive teams (only when requested) shown flat with an inactive badge.
    inactive_nodes = []
    if include_inactive:
        inactive_teams = [team for team in teams if not team.is_active]
        inactive_teams.sort(key=lambda team: card_by_id[team.id].name)
        inactive_nodes = [
            MinistryStructureDisplayNode(
                card=card_by_id[team.id],
                depth=0,
                is_primary_occurrence=True,
            )
            for team in inactive_teams
        ]

    return MinistryStructureMap(
        anchor_groups=anchor_groups,
        unanchored_nodes=unanchored_nodes,
        inactive_nodes=inactive_nodes,
        is_filtered=False,
        filtered_cards=[],
        summary=summary,
    )
