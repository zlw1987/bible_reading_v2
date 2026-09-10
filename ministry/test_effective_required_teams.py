from django.contrib.admin.models import LogEntry
from django.contrib.auth.models import User
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from accounts.models import ChurchStructureMembership
from events.models import ServiceEventRequiredTeam
from notifications.models import Notification

from .models import (
    MinistryTeamRoleAssignment,
    MinistryTeamRoleType,
    TeamAssignment,
    TeamAssignmentMember,
    TeamMembership,
)
from .services.assignment_coverage import (
    COVERAGE_ADDITIONAL,
    COVERAGE_ASSIGNED,
    COVERAGE_EMPTY_ASSIGNMENT,
    COVERAGE_UNASSIGNED,
    assignment_coverage_queryset,
    build_assignment_coverage,
    count_upcoming_required_team_gaps,
    events_with_coverage_queryset,
)
from .services.effective_required_teams import inspect_effective_required_teams
from .services.sunday_schedule_board import build_sunday_schedule_board
from .services.worship_governance import (
    inspect_worship_ownership_consistency,
    inspect_worship_ownership_consistency_for_events,
)
from .test_worship_governance import WorshipGovernanceDomainTestBase
from .views import leader_needs_attention_rows


class EffectiveRequiredTeamsTests(WorshipGovernanceDomainTestBase):
    def inspect(self):
        event = events_with_coverage_queryset().get(pk=self.event.pk)
        return inspect_effective_required_teams(event)

    def coverage(self, *, suppress_derived_worship_rows=False):
        event = events_with_coverage_queryset().get(pk=self.event.pk)
        assignments = list(
            assignment_coverage_queryset().filter(service_event_id=event.pk)
        )
        return build_assignment_coverage(
            [event],
            assignments,
            language="en",
            suppress_derived_worship_rows=suppress_derived_worship_rows,
        )[event.pk]

    def add_active_member(self, assignment, *, display_name="Team Member"):
        membership = TeamMembership.objects.create(
            team=assignment.ministry_team,
            display_name=display_name,
        )
        return TeamAssignmentMember.objects.create(
            assignment=assignment,
            membership=membership,
        )

    def test_explicit_rows_are_retained_without_revalidation(self):
        ServiceEventRequiredTeam.objects.create(
            service_event=self.event, ministry_team=self.av_team
        )
        self.av_team.is_active = False
        self.av_team.is_assignable = False
        self.av_team.save(update_fields=["is_active", "is_assignable", "updated_at"])

        inspection = self.inspect()

        fact = next(fact for fact in inspection.facts if fact.team.pk == self.av_team.pk)
        self.assertTrue(fact.is_explicit)
        self.assertFalse(fact.is_derived_worship)

    def test_no_selected_worship_adds_nothing(self):
        self.event.rotation_anchor_team = None
        self.event.save(update_fields=["rotation_anchor_team", "updated_at"])

        inspection = self.inspect()

        self.assertEqual(inspection.facts, ())
        self.assertIsNone(inspection.derived_worship_team)
        self.assertFalse(inspection.worship_review_required)

    def test_eligible_selected_worship_is_derived(self):
        inspection = self.inspect()

        self.assertEqual(inspection.teams, (self.c1,))
        self.assertFalse(inspection.facts[0].is_explicit)
        self.assertTrue(inspection.facts[0].is_derived_worship)

    def test_invalid_selection_is_excluded_and_requires_review(self):
        self.event.rotation_anchor_team = self.av_team
        self.event.save(update_fields=["rotation_anchor_team", "updated_at"])

        inspection = self.inspect()

        self.assertEqual(inspection.facts, ())
        self.assertFalse(inspection.selected_team_is_eligible)
        self.assertTrue(inspection.worship_review_required)

    def test_exact_explicit_and_derived_team_is_deduplicated_with_both_provenances(self):
        link = ServiceEventRequiredTeam.objects.create(
            service_event=self.event, ministry_team=self.c1
        )

        inspection = self.inspect()

        self.assertEqual(len(inspection.facts), 1)
        fact = inspection.facts[0]
        self.assertTrue(fact.is_explicit)
        self.assertTrue(fact.is_derived_worship)
        self.assertEqual(fact.explicit_required_team_link_id, link.pk)

    def test_eligible_selected_team_remains_required_during_off_team_conflict(self):
        self.create_assignment(self.c2)

        inspection = self.inspect()

        self.assertEqual(inspection.teams, (self.c1,))
        self.assertTrue(inspection.has_operational_conflict)

    def test_eligible_selected_team_remains_required_during_multiple_assignment_conflict(self):
        self.create_assignment(self.c1)
        self.create_assignment(self.c2)

        inspection = self.inspect()

        self.assertEqual(inspection.teams, (self.c1,))
        self.assertTrue(inspection.worship_review_required)

    def test_names_tokens_and_profile_configuration_do_not_infer_a_requirement(self):
        self.event.rotation_anchor_team = None
        self.event.title = "A C1 C2 C3 Worship"
        self.event.service_profile_key = "worship_named_profile"
        self.event.save(
            update_fields=[
                "rotation_anchor_team",
                "title",
                "service_profile_key",
                "updated_at",
            ]
        )

        with CaptureQueriesContext(connection) as queries:
            inspection = self.inspect()

        self.assertEqual(inspection.facts, ())
        sql = " ".join(query["sql"].lower() for query in queries.captured_queries)
        self.assertNotIn("serviceprofileministryrequirement", sql)

    def test_batch_worship_inspections_preserve_canonical_results(self):
        event = events_with_coverage_queryset().get(pk=self.event.pk)

        batched = inspect_worship_ownership_consistency_for_events([event])[event.pk]
        canonical = inspect_worship_ownership_consistency(event)

        self.assertEqual(batched, canonical)

    def test_derived_worship_coverage_states_and_provenance(self):
        coverage = self.coverage()
        self.assertEqual(coverage["rows"][0]["kind"], COVERAGE_UNASSIGNED)
        self.assertTrue(coverage["rows"][0]["is_derived_worship_requirement"])
        self.assertEqual(coverage["missing_count"], 1)

        assignment = self.create_assignment(self.c1)
        coverage = self.coverage()
        self.assertEqual(coverage["rows"][0]["kind"], COVERAGE_EMPTY_ASSIGNMENT)
        self.assertEqual(coverage["missing_count"], 0)

        self.add_active_member(assignment)
        coverage = self.coverage()
        self.assertEqual(coverage["rows"][0]["kind"], COVERAGE_ASSIGNED)
        self.assertEqual(coverage["missing_count"], 0)

    def test_upcoming_gap_count_includes_unscheduled_derived_worship(self):
        event = events_with_coverage_queryset().get(pk=self.event.pk)

        self.assertEqual(count_upcoming_required_team_gaps([event], []), 1)

    def test_matching_assignment_is_not_additional_and_off_team_assignment_is(self):
        self.create_assignment(self.c1)
        self.create_assignment(self.c2)

        coverage = self.coverage()
        rows = {row["team"].pk: row for row in coverage["rows"]}

        self.assertNotEqual(rows[self.c1.pk]["kind"], COVERAGE_ADDITIONAL)
        self.assertEqual(rows[self.c2.pk]["kind"], COVERAGE_ADDITIONAL)

    def test_explicit_and_derived_dedup_does_not_double_count(self):
        ServiceEventRequiredTeam.objects.create(
            service_event=self.event, ministry_team=self.c1
        )

        coverage = self.coverage()

        self.assertEqual(len(coverage["rows"]), 1)
        self.assertEqual(coverage["missing_count"], 1)

    def test_conflict_with_matching_assignment_has_zero_missing_but_is_not_clean(self):
        self.create_assignment(self.c1)
        self.create_assignment(self.c2)

        coverage = self.coverage()

        self.assertEqual(coverage["missing_count"], 0)
        self.assertTrue(coverage["worship_review_required"])
        self.assertTrue(coverage["has_operational_conflict"])
        self.assertFalse(coverage["is_operationally_clean"])

    def test_dedicated_worship_projection_can_suppress_generic_row_and_additional(self):
        self.create_assignment(self.c1)

        coverage = self.coverage(suppress_derived_worship_rows=True)

        self.assertEqual(coverage["rows"], [])

    def test_effective_reads_create_no_operational_rows(self):
        models = (
            ServiceEventRequiredTeam,
            TeamAssignment,
            TeamAssignmentMember,
            Notification,
            LogEntry,
        )
        before = {model: model.objects.count() for model in models}

        self.inspect()
        self.coverage()

        self.assertEqual(before, {model: model.objects.count() for model in models})


class EffectiveRequiredTeamConsumerTests(WorshipGovernanceDomainTestBase):
    def setUp(self):
        super().setUp()
        self.viewer = User.objects.create_user(username="effective_viewer", password="pw")
        ChurchStructureMembership.objects.create(
            user=self.viewer,
            unit=self.cm,
            status=ChurchStructureMembership.STATUS_ACTIVE,
            is_primary=True,
            start_date=timezone.localdate(),
        )
        self.staff = User.objects.create_user(
            username="effective_staff", password="pw", is_staff=True
        )
        self.lead = User.objects.create_user(username="effective_lead", password="pw")
        lead_type = MinistryTeamRoleType.objects.create(
            code=MinistryTeamRoleType.CODE_LEAD,
            name="Lead",
            name_en="Lead",
        )
        MinistryTeamRoleAssignment.objects.create(
            team=self.c1,
            role_type=lead_type,
            user=self.lead,
            start_date=timezone.localdate(),
        )

    def set_language(self, language="en"):
        session = self.client.session
        session["language"] = language
        session.save()

    def test_event_detail_bounded_worship_states_and_existing_selector_authority(self):
        self.set_language("en")
        self.client.login(username="effective_viewer", password="pw")
        response = self.client.get(reverse("service_event_detail", args=[self.event.pk]))
        self.assertContains(response, "Worship Team")
        self.assertContains(response, self.c1.name_en)
        self.assertContains(response, "Selected, not yet scheduled")
        self.assertNotContains(response, "Change Worship Team")

        self.client.logout()
        self.client.login(username="effective_staff", password="pw")
        self.set_language("en")
        response = self.client.get(reverse("service_event_detail", args=[self.event.pk]))
        self.assertTrue(response.context["can_change_worship_team"])
        self.assertContains(response, reverse("change_worship_team", args=[self.event.pk]))

    def test_event_detail_no_selection_readout(self):
        self.event.rotation_anchor_team = None
        self.event.save(update_fields=["rotation_anchor_team", "updated_at"])
        self.set_language("en")
        self.client.login(username="effective_viewer", password="pw")

        response = self.client.get(reverse("service_event_detail", args=[self.event.pk]))

        self.assertContains(response, "Worship Team not selected")
        self.assertNotContains(response, "Change Worship Team")

    def test_persisted_required_team_metadata_does_not_duplicate_derived_worship(self):
        ServiceEventRequiredTeam.objects.create(
            service_event=self.event,
            ministry_team=self.av_team,
        )
        self.set_language("en")
        self.client.login(username="effective_staff", password="pw")

        response = self.client.get(reverse("service_event_detail", args=[self.event.pk]))

        self.assertEqual(
            [team.pk for team in response.context["required_teams"]],
            [self.av_team.pk],
        )
        self.assertContains(response, self.c1.name_en)

    def test_event_detail_invalid_selection_hides_raw_team_and_shows_review(self):
        self.event.rotation_anchor_team = self.av_team
        self.event.save(update_fields=["rotation_anchor_team", "updated_at"])
        self.set_language("en")
        self.client.login(username="effective_viewer", password="pw")

        response = self.client.get(reverse("service_event_detail", args=[self.event.pk]))

        self.assertContains(response, "Worship Team review required")
        self.assertNotContains(response, self.av_team.name_en)

    def test_event_detail_does_not_leak_roster_to_ordinary_viewer(self):
        assignment = self.create_assignment(self.c1)
        membership = TeamMembership.objects.create(
            team=self.c1, display_name="Private Roster Name"
        )
        TeamAssignmentMember.objects.create(
            assignment=assignment, membership=membership
        )
        self.set_language("en")
        self.client.login(username="effective_viewer", password="pw")

        response = self.client.get(reverse("service_event_detail", args=[self.event.pk]))

        self.assertNotContains(response, "Private Roster Name")
        self.assertNotContains(response, "Assignment Coverage")

    def test_leader_attention_includes_effective_gap_and_excludes_unrelated_leader(self):
        rows = leader_needs_attention_rows(self.lead, language="en")
        self.assertEqual([(row["event"].pk, row["team"].pk) for row in rows], [(self.event.pk, self.c1.pk)])
        self.assertEqual(rows[0]["issue_label"], "Unassigned")

        unrelated = User.objects.create_user(username="unrelated_lead")
        MinistryTeamRoleAssignment.objects.create(
            team=self.c2,
            role_type=MinistryTeamRoleType.objects.get(code=MinistryTeamRoleType.CODE_LEAD),
            user=unrelated,
            start_date=timezone.localdate(),
        )
        self.assertEqual(leader_needs_attention_rows(unrelated), [])

    def test_staff_overview_counts_unscheduled_effective_worship_gap(self):
        self.set_language("en")
        self.client.login(username="effective_staff", password="pw")

        response = self.client.get(reverse("staff_overview"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["upcoming_required_team_gaps"], 1)

    def test_conflict_with_matching_assignment_is_leader_review_not_missing(self):
        selected_assignment = self.create_assignment(self.c1)
        membership = TeamMembership.objects.create(
            team=self.c1, display_name="Scheduled Member"
        )
        assignment_member = TeamAssignmentMember.objects.create(
            assignment=selected_assignment, membership=membership
        )
        assignment_member.confirmed_at = timezone.now()
        assignment_member.save(update_fields=["confirmed_at"])
        self.create_assignment(self.c2)

        rows = leader_needs_attention_rows(self.lead, language="en")

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["team"], self.c1)
        self.assertEqual(rows[0]["issue_label"], "Review required")

    def test_team_schedule_and_board_keep_worship_out_of_generic_projection(self):
        self.set_language("en")
        self.client.login(username="effective_lead", password="pw")
        response = self.client.get(reverse("team_schedule", args=[self.c1.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["schedule_rows"][0]["coverage_rows"], [])

        board = build_sunday_schedule_board(
            user=self.staff,
            manageable_team_ids=[],
            global_assignment_manager=True,
            language="en",
            today=timezone.localdate(),
        )
        self.assertNotIn(self.c1.pk, {team.pk for team in board["teams"]})
        row = next(row for row in board["rows"] if row["event"].pk == self.event.pk)
        self.assertEqual(row["worship_context"]["anchor_team"], self.c1)
