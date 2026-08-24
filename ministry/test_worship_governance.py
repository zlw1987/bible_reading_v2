"""Focused MO-S.6D-1D-A read-only Worship governance domain tests."""

from django.contrib.admin.models import LogEntry
from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from accounts.models import ChurchStructureMembership, ChurchStructureUnit
from events.models import (
    ServiceEvent,
    ServiceEventAudienceScope,
    ServiceEventPlannerAssignment,
    ServiceEventRequiredTeam,
)
from notifications.models import Notification

from .models import (
    MinistryTeam,
    MinistryTeamParentLink,
    MinistryTeamRoleAssignment,
    MinistryTeamRoleType,
    TeamAssignment,
    TeamAssignmentMember,
)
from .permissions import (
    can_manage_ministry_team,
    can_manage_team_assignment_for_team,
)
from .services.worship_governance import (
    WorshipOwnershipConsistencyState,
    applicable_worship_rotation_pools,
    eligible_worship_team_candidates,
    inspect_worship_ownership_consistency,
)


class WorshipGovernanceDomainTestBase(TestCase):
    def setUp(self):
        self.root = self.create_unit(
            "ROOT", "Whole Church", ChurchStructureUnit.UNIT_ROOT
        )
        self.main = self.create_unit(
            "MAIN", "Main Campus", ChurchStructureUnit.UNIT_CAMPUS, self.root
        )
        self.cm = self.create_unit(
            "CM",
            "Chinese Ministry",
            ChurchStructureUnit.UNIT_MINISTRY_CONTEXT,
            self.main,
        )
        self.em = self.create_unit(
            "EM",
            "English Ministry",
            ChurchStructureUnit.UNIT_MINISTRY_CONTEXT,
            self.main,
        )
        self.tri = self.create_unit(
            "TRI", "Tri-Valley Campus", ChurchStructureUnit.UNIT_CAMPUS, self.root
        )
        self.tri_ministry = self.create_unit(
            "TRI-M",
            "Tri-Valley Ministry",
            ChurchStructureUnit.UNIT_MINISTRY_CONTEXT,
            self.tri,
        )

        self.chinese_pool = self.create_pool("Chinese Worship Pool", self.cm)
        self.english_pool = self.create_pool("English Worship Pool", self.em)
        self.tri_pool = self.create_pool(
            "Tri-Valley Worship Pool", self.tri_ministry
        )
        self.c1 = self.create_team("Chinese Worship C1", self.chinese_pool)
        self.c2 = self.create_team("Chinese Worship C2", self.chinese_pool)
        self.e1 = self.create_team("English Worship E1", self.english_pool)
        self.tri1 = self.create_team("Tri-Valley Worship T1", self.tri_pool)

        self.av_container = MinistryTeam.objects.create(
            name="AVL Ministry", is_assignable=False
        )
        MinistryTeamParentLink.objects.create(
            child_team=self.av_container,
            parent_church_unit=self.cm,
            is_primary=True,
        )
        self.av_team = self.create_team("Projection", self.av_container)

        self.event = ServiceEvent.objects.create(
            title="Sunday Worship",
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
            start_datetime=timezone.now() + timezone.timedelta(days=7),
            status=ServiceEvent.STATUS_PUBLISHED,
            rotation_anchor_team=self.c1,
        )
        self.add_audience(self.event, self.cm)

    def create_unit(self, code, name, unit_type, parent=None):
        return ChurchStructureUnit.objects.create(
            code=code,
            name=name,
            name_en=name,
            unit_type=unit_type,
            parent=parent,
        )

    def create_pool(self, name, anchor):
        pool = MinistryTeam.objects.create(
            name=name,
            name_en=name,
            is_assignable=False,
            is_worship_rotation_pool=True,
        )
        MinistryTeamParentLink.objects.create(
            child_team=pool,
            parent_church_unit=anchor,
            is_primary=True,
        )
        return pool

    def create_team(self, name, parent, *, primary=True, assignable=True):
        team = MinistryTeam.objects.create(
            name=name,
            name_en=name,
            is_assignable=assignable,
        )
        MinistryTeamParentLink.objects.create(
            child_team=team,
            parent_team=parent,
            is_primary=primary,
        )
        return team

    def add_audience(self, event, unit):
        return ServiceEventAudienceScope.objects.create(
            service_event=event, unit=unit
        )

    def pool_ids(self, event=None):
        return [
            item.pool.pk
            for item in applicable_worship_rotation_pools(event or self.event)
        ]

    def candidate_ids(self, event=None):
        return [
            item.team.pk
            for item in eligible_worship_team_candidates(event or self.event)
        ]

    def create_assignment(self, team, status=TeamAssignment.STATUS_SCHEDULED):
        # 1D-A must continue to diagnose pre-existing conflict rows after 1D-B
        # closes normal model writes.  bulk_create is intentional test-fixture
        # construction of stored legacy/conflict state, not a supported runtime
        # write path.
        assignment = TeamAssignment(
            service_event=self.event,
            ministry_team=team,
            status=status,
        )
        TeamAssignment.objects.bulk_create([assignment])
        return assignment


class WorshipPoolApplicabilityTests(WorshipGovernanceDomainTestBase):
    def event_for(self, audience_unit=None, **kwargs):
        values = {
            "title": "Applicability",
            "event_type": ServiceEvent.EVENT_SUNDAY_SERVICE,
            "start_datetime": timezone.now() + timezone.timedelta(days=14),
            "status": ServiceEvent.STATUS_PUBLISHED,
        }
        values.update(kwargs)
        event = ServiceEvent.objects.create(**values)
        if audience_unit is not None:
            self.add_audience(event, audience_unit)
        return event

    def test_exact_anchor_match_applies(self):
        self.assertEqual(self.pool_ids(), [self.chinese_pool.pk])

    def test_descendant_anchor_under_selected_audience_applies(self):
        event = self.event_for(self.main)
        self.assertEqual(
            set(self.pool_ids(event)),
            {self.chinese_pool.pk, self.english_pool.pk},
        )

    def test_whole_church_activates_multiple_descendant_pools(self):
        event = self.event_for(self.root)
        self.assertEqual(
            set(self.pool_ids(event)),
            {self.chinese_pool.pk, self.english_pool.pk, self.tri_pool.pk},
        )

    def test_main_campus_excludes_tri_valley_pool(self):
        event = self.event_for(self.main)
        self.assertNotIn(self.tri_pool.pk, self.pool_ids(event))

    def test_chinese_ministry_excludes_english_pool(self):
        self.assertNotIn(self.english_pool.pk, self.pool_ids())

    def test_multiple_audience_rows_form_union(self):
        event = self.event_for(self.cm)
        self.add_audience(event, self.em)
        self.assertEqual(
            set(self.pool_ids(event)),
            {self.chinese_pool.pk, self.english_pool.pk},
        )

    def test_zero_audience_fails_closed(self):
        self.assertEqual(self.pool_ids(self.event_for()), [])

    def test_inactive_audience_branch_fails_closed(self):
        event = self.event_for(self.main)
        self.main.is_active = False
        self.main.save(update_fields=["is_active", "updated_at"])
        self.assertEqual(self.pool_ids(event), [])

    def test_inactive_malformed_and_unanchored_pools_fail_closed(self):
        inactive = self.create_pool("Inactive Pool", self.cm)
        inactive.is_active = False
        inactive.save(update_fields=["is_active", "updated_at"])

        malformed = self.create_pool("Malformed Pool", self.cm)
        MinistryTeam.objects.filter(pk=malformed.pk).update(is_assignable=True)

        unanchored = MinistryTeam.objects.create(
            name="Unanchored Pool",
            is_assignable=False,
            is_worship_rotation_pool=True,
        )
        result_ids = self.pool_ids()
        self.assertNotIn(inactive.pk, result_ids)
        self.assertNotIn(malformed.pk, result_ids)
        self.assertNotIn(unanchored.pk, result_ids)

    def test_host_language_unit_does_not_create_applicability(self):
        event = self.event_for(self.cm, host_language_unit=self.em)
        self.assertEqual(self.pool_ids(event), [self.chinese_pool.pk])


class WorshipTeamCandidateTests(WorshipGovernanceDomainTestBase):
    def test_active_assignable_descendants_are_included_but_pool_is_not(self):
        result_ids = self.candidate_ids()
        self.assertIn(self.c1.pk, result_ids)
        self.assertIn(self.c2.pk, result_ids)
        self.assertNotIn(self.chinese_pool.pk, result_ids)

    def test_nested_descendant_through_intermediate_container_is_included(self):
        container = self.create_team(
            "Chinese Worship Container",
            self.chinese_pool,
            assignable=False,
        )
        nested = self.create_team("Nested Worship Team", container)
        candidates = eligible_worship_team_candidates(self.event)
        by_id = {candidate.team.pk: candidate for candidate in candidates}
        self.assertEqual(by_id[nested.pk].owning_pool, self.chinese_pool)

    def test_inactive_and_nonassignable_descendants_are_excluded(self):
        inactive = self.create_team("Inactive Worship Team", self.chinese_pool)
        inactive.is_active = False
        inactive.save(update_fields=["is_active", "updated_at"])
        container = self.create_team(
            "Nonassignable Worship Container",
            self.chinese_pool,
            assignable=False,
        )
        result_ids = self.candidate_ids()
        self.assertNotIn(inactive.pk, result_ids)
        self.assertNotIn(container.pk, result_ids)

    def test_secondary_only_pool_link_does_not_establish_eligibility(self):
        secondary_only = MinistryTeam.objects.create(name="Shared Team")
        MinistryTeamParentLink.objects.create(
            child_team=secondary_only,
            parent_team=self.av_container,
            is_primary=True,
        )
        MinistryTeamParentLink.objects.create(
            child_team=secondary_only,
            parent_team=self.chinese_pool,
            is_primary=False,
        )
        self.assertNotIn(secondary_only.pk, self.candidate_ids())

    def test_missing_ambiguous_cyclic_and_inactive_primary_paths_fail_closed(self):
        missing = MinistryTeam.objects.create(name="Missing Primary")

        ambiguous = self.create_team("Ambiguous Primary", self.chinese_pool)
        MinistryTeamParentLink.objects.bulk_create(
            [
                MinistryTeamParentLink(
                    child_team=ambiguous,
                    parent_team=self.av_container,
                    is_primary=True,
                )
            ]
        )

        cycle_a = MinistryTeam.objects.create(name="Cycle A")
        cycle_b = MinistryTeam.objects.create(name="Cycle B")
        MinistryTeamParentLink.objects.bulk_create(
            [
                MinistryTeamParentLink(
                    child_team=cycle_a, parent_team=cycle_b, is_primary=True
                ),
                MinistryTeamParentLink(
                    child_team=cycle_b, parent_team=cycle_a, is_primary=True
                ),
            ]
        )

        inactive_container = self.create_team(
            "Inactive Primary Container",
            self.chinese_pool,
            assignable=False,
        )
        inactive_path_team = self.create_team(
            "Inactive Path Team", inactive_container
        )
        inactive_container.is_active = False
        inactive_container.save(update_fields=["is_active", "updated_at"])

        result_ids = self.candidate_ids()
        for team in (missing, ambiguous, cycle_a, cycle_b, inactive_path_team):
            self.assertNotIn(team.pk, result_ids)

    def test_candidates_are_deterministically_ordered(self):
        self.create_team("Alpha Worship", self.chinese_pool)
        self.create_team("Zulu Worship", self.chinese_pool)
        names = [
            candidate.team.name
            for candidate in eligible_worship_team_candidates(self.event)
        ]
        self.assertEqual(names, sorted(names))

    def test_candidate_under_inapplicable_pool_is_excluded(self):
        self.assertNotIn(self.e1.pk, self.candidate_ids())


class WorshipOwnershipConsistencyTests(WorshipGovernanceDomainTestBase):
    def inspect(self):
        return inspect_worship_ownership_consistency(self.event)

    def test_no_selection(self):
        self.event.rotation_anchor_team = None
        self.event.save(update_fields=["rotation_anchor_team", "updated_at"])
        self.assertEqual(
            self.inspect().state, WorshipOwnershipConsistencyState.NO_SELECTION
        )

    def test_invalid_selected_team(self):
        self.event.rotation_anchor_team = self.av_team
        self.event.save(update_fields=["rotation_anchor_team", "updated_at"])
        result = self.inspect()
        self.assertEqual(
            result.state, WorshipOwnershipConsistencyState.INVALID_SELECTION
        )
        self.assertFalse(result.selected_team_is_eligible)

    def test_valid_selected_team_can_be_unscheduled(self):
        self.assertEqual(
            self.inspect().state,
            WorshipOwnershipConsistencyState.SELECTED_UNSCHEDULED,
        )

    def test_one_matching_current_assignment_is_consistent(self):
        assignment = self.create_assignment(self.c1)
        result = self.inspect()
        self.assertEqual(
            result.state, WorshipOwnershipConsistencyState.CONSISTENT
        )
        self.assertEqual(result.matching_assignment_ids, (assignment.pk,))
        self.assertEqual(result.conflicting_assignment_ids, ())

    def test_off_team_current_worship_assignment_is_conflict(self):
        assignment = self.create_assignment(self.c2)
        result = self.inspect()
        self.assertEqual(
            result.state, WorshipOwnershipConsistencyState.OFF_TEAM_CONFLICT
        )
        self.assertEqual(result.conflicting_assignment_ids, (assignment.pk,))

    def test_assignment_under_inapplicable_pool_is_conflict(self):
        assignment = self.create_assignment(self.e1)
        result = self.inspect()
        self.assertEqual(
            result.state,
            WorshipOwnershipConsistencyState.OUT_OF_SCOPE_WORSHIP_CONFLICT,
        )
        self.assertEqual(result.conflicting_assignment_ids, (assignment.pk,))

    def test_assignment_under_malformed_configured_pool_remains_conflict(self):
        malformed_pool = self.create_pool("Malformed Current Pool", self.cm)
        malformed_team = self.create_team(
            "Malformed Pool Worship Team", malformed_pool
        )
        MinistryTeam.objects.filter(pk=malformed_pool.pk).update(
            is_assignable=True
        )
        assignment = self.create_assignment(malformed_team)
        result = self.inspect()
        self.assertEqual(
            result.state,
            WorshipOwnershipConsistencyState.OUT_OF_SCOPE_WORSHIP_CONFLICT,
        )
        self.assertEqual(result.conflicting_assignment_ids, (assignment.pk,))

    def test_multiple_current_worship_assignments_are_ambiguous(self):
        self.create_assignment(self.c1)
        self.create_assignment(self.c2)
        self.assertEqual(
            self.inspect().state,
            WorshipOwnershipConsistencyState.MULTIPLE_CURRENT_WORSHIP_ASSIGNMENTS,
        )

    def test_duplicate_selected_team_assignment_is_distinct(self):
        self.create_assignment(self.c1)
        self.create_assignment(self.c1, TeamAssignment.STATUS_PREPARED)
        self.assertEqual(
            self.inspect().state,
            WorshipOwnershipConsistencyState.DUPLICATE_SELECTED_TEAM_ASSIGNMENT,
        )

    def test_completed_and_cancelled_history_do_not_count_as_current(self):
        self.create_assignment(self.c1, TeamAssignment.STATUS_COMPLETED)
        self.create_assignment(self.c2, TeamAssignment.STATUS_CANCELLED)
        self.assertEqual(
            self.inspect().state,
            WorshipOwnershipConsistencyState.SELECTED_UNSCHEDULED,
        )

    def test_downstream_non_worship_assignment_is_not_misclassified(self):
        self.create_assignment(self.av_team)
        result = self.inspect()
        self.assertEqual(
            result.state,
            WorshipOwnershipConsistencyState.SELECTED_UNSCHEDULED,
        )
        self.assertEqual(result.current_worship_assignments, ())


class WorshipGovernanceReadOnlyAndBoundaryTests(WorshipGovernanceDomainTestBase):
    def test_all_services_are_side_effect_free(self):
        assignment = self.create_assignment(self.c1)
        models = (
            ServiceEvent,
            ServiceEventAudienceScope,
            ServiceEventRequiredTeam,
            TeamAssignment,
            TeamAssignmentMember,
            MinistryTeam,
            MinistryTeamParentLink,
            ServiceEventPlannerAssignment,
            Notification,
            LogEntry,
        )
        before_counts = {model: model.objects.count() for model in models}
        before_event = ServiceEvent.objects.values(
            "rotation_anchor_team_id", "status", "updated_at"
        ).get(pk=self.event.pk)
        before_assignment = TeamAssignment.objects.values(
            "service_event_id", "ministry_team_id", "status", "updated_at"
        ).get(pk=assignment.pk)

        applicable_worship_rotation_pools(self.event)
        eligible_worship_team_candidates(self.event)
        inspect_worship_ownership_consistency(self.event)

        self.assertEqual(
            before_counts, {model: model.objects.count() for model in models}
        )
        self.assertEqual(
            before_event,
            ServiceEvent.objects.values(
                "rotation_anchor_team_id", "status", "updated_at"
            ).get(pk=self.event.pk),
        )
        self.assertEqual(
            before_assignment,
            TeamAssignment.objects.values(
                "service_event_id", "ministry_team_id", "status", "updated_at"
            ).get(pk=assignment.pk),
        )

    def test_planner_responsibility_alone_grants_no_authority(self):
        planner = User.objects.create_user(username="event_planner")
        ServiceEventPlannerAssignment.objects.create(
            service_event=self.event, user=planner
        )
        inspect_worship_ownership_consistency(self.event)
        self.assertFalse(self.event.can_be_managed_by(planner))
        self.assertFalse(can_manage_ministry_team(planner, self.chinese_pool))
        self.assertFalse(
            can_manage_team_assignment_for_team(planner, self.c1)
        )

    def test_pool_lead_gets_no_new_service_event_or_child_roster_action(self):
        lead_user = User.objects.create_user(username="pool_lead")
        lead_type = MinistryTeamRoleType.objects.create(
            code=MinistryTeamRoleType.CODE_LEAD,
            name="Lead",
            name_en="Lead",
        )
        MinistryTeamRoleAssignment.objects.create(
            team=self.chinese_pool,
            role_type=lead_type,
            user=lead_user,
            start_date=timezone.localdate(),
        )
        applicable_worship_rotation_pools(self.event)
        self.assertTrue(can_manage_ministry_team(lead_user, self.chinese_pool))
        self.assertFalse(self.event.can_be_managed_by(lead_user))
        self.assertFalse(
            can_manage_team_assignment_for_team(lead_user, self.c1)
        )

    def test_ordinary_service_event_visibility_is_unchanged(self):
        member = User.objects.create_user(username="ordinary_member")
        ChurchStructureMembership.objects.create(
            user=member,
            unit=self.cm,
            status=ChurchStructureMembership.STATUS_ACTIVE,
            is_primary=True,
            start_date=timezone.localdate(),
        )
        before = self.event.can_be_seen_by(member)
        applicable_worship_rotation_pools(self.event)
        eligible_worship_team_candidates(self.event)
        inspect_worship_ownership_consistency(self.event)
        self.event.refresh_from_db()
        self.assertTrue(before)
        self.assertEqual(self.event.can_be_seen_by(member), before)
