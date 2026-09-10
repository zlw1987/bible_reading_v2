"""Canonical read-only effective Required Ministry Team inspection.

Persisted ``ServiceEventRequiredTeam`` rows remain event operational evidence.
The one dynamic member is the exact selected Worship Team, and only while the
canonical Worship ownership inspection says that selection is eligible.
Nothing in this module accepts a user, grants authority, or writes data.
"""

from dataclasses import dataclass

from ..models import MinistryTeam
from .worship_governance import (
    WorshipOwnershipConsistencyInspection,
    WorshipOwnershipConsistencyState,
    inspect_worship_ownership_consistency,
)


_WORSHIP_REVIEW_STATES = frozenset(
    {
        WorshipOwnershipConsistencyState.INVALID_SELECTION,
        WorshipOwnershipConsistencyState.OFF_TEAM_CONFLICT,
        WorshipOwnershipConsistencyState.OUT_OF_SCOPE_WORSHIP_CONFLICT,
        WorshipOwnershipConsistencyState.MULTIPLE_CURRENT_WORSHIP_ASSIGNMENTS,
        WorshipOwnershipConsistencyState.DUPLICATE_SELECTED_TEAM_ASSIGNMENT,
    }
)

_WORSHIP_CONFLICT_STATES = frozenset(
    {
        WorshipOwnershipConsistencyState.OFF_TEAM_CONFLICT,
        WorshipOwnershipConsistencyState.OUT_OF_SCOPE_WORSHIP_CONFLICT,
        WorshipOwnershipConsistencyState.MULTIPLE_CURRENT_WORSHIP_ASSIGNMENTS,
        WorshipOwnershipConsistencyState.DUPLICATE_SELECTED_TEAM_ASSIGNMENT,
    }
)


@dataclass(frozen=True)
class EffectiveRequiredTeamFact:
    team: MinistryTeam
    is_explicit: bool
    is_derived_worship: bool
    explicit_required_team_link_id: int | None = None


@dataclass(frozen=True)
class EffectiveRequiredTeamsInspection:
    event: object
    facts: tuple[EffectiveRequiredTeamFact, ...]
    explicit_team_ids: frozenset[int]
    derived_worship_team: MinistryTeam | None
    worship_ownership: WorshipOwnershipConsistencyInspection

    @property
    def teams(self):
        return tuple(fact.team for fact in self.facts)

    @property
    def selected_team_is_eligible(self):
        return self.worship_ownership.selected_team_is_eligible

    @property
    def worship_review_required(self):
        return self.worship_ownership.state in _WORSHIP_REVIEW_STATES

    @property
    def has_operational_conflict(self):
        return self.worship_ownership.state in _WORSHIP_CONFLICT_STATES


def _fact_sort_key(fact):
    team = fact.team
    return (
        (team.name or "").casefold(),
        (team.name_en or "").casefold(),
        team.pk,
    )


def inspect_effective_required_teams(event, *, worship_ownership=None):
    """Return deterministic effective requirements with exact provenance.

    ``worship_ownership`` may be supplied only as a precomputed result from the
    canonical governance inspector. This lets batch/presentation consumers
    avoid inspecting the same event twice without duplicating eligibility
    rules or introducing cross-request state.
    """

    if worship_ownership is None:
        worship_ownership = inspect_worship_ownership_consistency(event)

    required_links = list(getattr(event, "required_team_links").all())
    facts_by_team_id = {}
    explicit_team_ids = set()
    for link in required_links:
        team = link.ministry_team
        explicit_team_ids.add(team.pk)
        facts_by_team_id[team.pk] = EffectiveRequiredTeamFact(
            team=team,
            is_explicit=True,
            is_derived_worship=False,
            explicit_required_team_link_id=link.pk,
        )

    derived_worship_team = None
    if worship_ownership.selected_team_is_eligible:
        derived_worship_team = worship_ownership.selected_team
        existing = facts_by_team_id.get(derived_worship_team.pk)
        facts_by_team_id[derived_worship_team.pk] = EffectiveRequiredTeamFact(
            team=derived_worship_team,
            is_explicit=existing is not None,
            is_derived_worship=True,
            explicit_required_team_link_id=(
                existing.explicit_required_team_link_id if existing else None
            ),
        )

    return EffectiveRequiredTeamsInspection(
        event=event,
        facts=tuple(sorted(facts_by_team_id.values(), key=_fact_sort_key)),
        explicit_team_ids=frozenset(explicit_team_ids),
        derived_worship_team=derived_worship_team,
        worship_ownership=worship_ownership,
    )
