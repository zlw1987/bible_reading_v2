"""Privacy-bounded Ministry Team identity inventory and path evidence."""

from collections import defaultdict

from django.core.exceptions import ValidationError

from .models import MinistryTeam, validate_ministry_team_key


UNRESOLVED_MULTIPLE_PRIMARY_LINKS = "UNRESOLVED_MULTIPLE_PRIMARY_LINKS"
UNRESOLVED_PRIMARY_PATH_CYCLE = "UNRESOLVED_PRIMARY_PATH_CYCLE"
UNRESOLVED_CHURCH_PATH_CYCLE = "UNRESOLVED_CHURCH_PATH_CYCLE"


def _team_evidence(team):
    return {
        "pk": team.pk,
        "name": team.name,
        "name_en": team.name_en,
        "is_active": team.is_active,
    }


def _link_evidence(link):
    return {
        "pk": link.pk,
        "child_team_pk": link.child_team_id,
        "parent_team_pk": link.parent_team_id,
        "parent_church_unit_pk": link.parent_church_unit_id,
        "is_active": link.is_active,
        "is_primary": link.is_primary,
        "sort_order": link.sort_order,
    }


def _church_path_evidence(anchor):
    units = []
    seen = set()
    current = anchor
    status = "OK"
    while current is not None:
        if current.pk in seen:
            status = UNRESOLVED_CHURCH_PATH_CYCLE
            break
        seen.add(current.pk)
        units.append(
            {
                "pk": current.pk,
                "parent_pk": current.parent_id,
                "unit_type": current.unit_type,
                "code": current.code,
                "name": current.name,
                "name_en": current.name_en,
                "is_active": current.is_active,
                "sort_order": current.sort_order,
            }
        )
        current = current.parent
    return status, list(reversed(units))


def build_primary_path_evidence(team):
    """Return deterministic display plus exact safe primary-path evidence.

    The evidence contains no membership, roster, role, or contact data. It
    records exact link/team/unit identities and reviewed display metadata so a
    material path change can invalidate a later configuration apply.
    """

    ministry_teams = [_team_evidence(team)]
    links_evidence = []
    seen = {team.pk}
    current = team
    status = "OK"
    church_units = []

    while True:
        links = list(
            current.parent_links.filter(is_active=True, is_primary=True)
            .select_related("parent_team", "parent_church_unit")
            .order_by("sort_order", "id")[:2]
        )
        links_evidence.extend(_link_evidence(link) for link in links)
        if len(links) > 1:
            status = UNRESOLVED_MULTIPLE_PRIMARY_LINKS
            break
        if not links:
            break

        link = links[0]
        if link.parent_church_unit_id is not None:
            church_status, church_units = _church_path_evidence(
                link.parent_church_unit
            )
            if church_status != "OK":
                status = church_status
            break

        parent = link.parent_team
        if parent is None or parent.pk in seen:
            status = UNRESOLVED_PRIMARY_PATH_CYCLE
            break
        seen.add(parent.pk)
        ministry_teams.append(_team_evidence(parent))
        current = parent

    if status == "OK":
        display_parts = [unit["name"] for unit in church_units]
        display_parts.extend(
            item["name"] for item in reversed(ministry_teams)
        )
        display = " > ".join(display_parts)
    else:
        display = status

    return {
        "status": status,
        "display": display,
        "ministry_teams_leaf_to_root": ministry_teams,
        "primary_links_leaf_to_root": links_evidence,
        "church_units_root_to_anchor": church_units,
    }


def build_identity_inventory(*, using="default"):
    """Return deterministic, privacy-bounded identity evidence for all teams."""

    teams = list(MinistryTeam.objects.using(using).all().order_by("id"))
    rows = []
    canonical_key_owners = defaultdict(list)

    for team in teams:
        raw_key = team.team_key
        integrity_problems = []
        if raw_key is not None:
            try:
                canonical_key = validate_ministry_team_key(raw_key)
            except ValidationError:
                canonical_key = None
                integrity_problems.append("MALFORMED_TEAM_KEY")
            else:
                if canonical_key != raw_key:
                    integrity_problems.append("NONCANONICAL_TEAM_KEY")
                if canonical_key is not None:
                    canonical_key_owners[canonical_key].append(team.id)

        path_evidence = build_primary_path_evidence(team)
        rows.append(
            {
                "pk": team.pk,
                "team_key": raw_key,
                "name": team.name,
                "name_en": team.name_en,
                "is_active": team.is_active,
                "is_assignable": team.is_assignable,
                "is_worship_rotation_pool": team.is_worship_rotation_pool,
                "primary_path": path_evidence["display"],
                "primary_path_evidence": path_evidence,
                "integrity_problems": integrity_problems,
            }
        )

    duplicate_ids = {
        team_id
        for owner_ids in canonical_key_owners.values()
        if len(owner_ids) > 1
        for team_id in owner_ids
    }
    for row in rows:
        if row["pk"] in duplicate_ids:
            row["integrity_problems"].append("DUPLICATE_CANONICAL_TEAM_KEY")

    configured = sum(row["team_key"] is not None for row in rows)
    return {
        "rows": rows,
        "summary": {
            "total_teams": len(rows),
            "active_teams": sum(row["is_active"] for row in rows),
            "configured_team_keys": configured,
            "unconfigured_team_keys": len(rows) - configured,
            "integrity_problem_teams": sum(
                bool(row["integrity_problems"]) for row in rows
            ),
        },
    }
