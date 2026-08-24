from datetime import datetime

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import ChurchRoleAssignment, ChurchStructureUnit
from core.notification_delivery import notification_sink_override_for_tests
from events.models import ServiceEvent, ServiceEventAudienceScope

from .models import (
    MinistryTeam,
    MinistryTeamParentLink,
    MinistryTeamRoleAssignment,
    MinistryTeamRoleType,
    TeamAssignment,
    TeamAssignmentMember,
    TeamMembership,
)


User = get_user_model()


class SundayScheduleBoardTests(TestCase):
    password = "testpass123"

    def setUp(self):
        self.lead = User.objects.create_user(
            username="board_lead",
            password=self.password,
        )
        self.coordinator = User.objects.create_user(
            username="board_coordinator",
            password=self.password,
        )
        self.ordinary = User.objects.create_user(
            username="board_ordinary",
            password=self.password,
        )
        self.membership_role_only = User.objects.create_user(
            username="board_membership_role_only",
            password=self.password,
        )
        self.can_lead_only = User.objects.create_user(
            username="board_can_lead_only",
            password=self.password,
        )
        self.staff = User.objects.create_user(
            username="board_staff",
            password=self.password,
            is_staff=True,
        )
        self.superuser = User.objects.create_superuser(
            username="board_superuser",
            password=self.password,
        )
        self.global_manager = User.objects.create_user(
            username="board_global_manager",
            password=self.password,
        )
        ChurchRoleAssignment.objects.create(
            user=self.global_manager,
            role=ChurchRoleAssignment.ROLE_PASTOR,
            scope_type=ChurchRoleAssignment.SCOPE_GLOBAL,
        )

        self.alpha_team = MinistryTeam.objects.create(
            name="Alpha Team",
            name_en="Alpha Team",
        )
        self.beta_team = MinistryTeam.objects.create(
            name="Beta Team",
            name_en="Beta Team",
            email_alias="beta-private@example.com",
        )
        self.delta_team = MinistryTeam.objects.create(
            name="Delta Team",
            name_en="Delta Team",
        )
        self.empty_team = MinistryTeam.objects.create(
            name="Empty Team",
            name_en="Empty Team",
        )
        self.gamma_team = MinistryTeam.objects.create(
            name="Gamma Team",
            name_en="Gamma Team",
        )
        self.cm = ChurchStructureUnit.objects.create(
            code="CM",
            name="Chinese Ministry",
            name_en="Chinese Ministry",
            unit_type=ChurchStructureUnit.UNIT_MINISTRY_CONTEXT,
        )
        self.worship_pool = MinistryTeam.objects.create(
            name="Chinese Worship Pool",
            name_en="Chinese Worship Pool",
            is_assignable=False,
            is_worship_rotation_pool=True,
        )
        MinistryTeamParentLink.objects.create(
            child_team=self.worship_pool,
            parent_church_unit=self.cm,
            is_primary=True,
        )
        self.anchor_team = MinistryTeam.objects.create(
            name="Anchor Team",
            name_en="Anchor Team",
        )
        MinistryTeamParentLink.objects.create(
            child_team=self.anchor_team,
            parent_team=self.worship_pool,
            is_primary=True,
        )
        self.anchor_lead = User.objects.create_user(
            username="board_anchor_lead",
            password=self.password,
        )

        lead_type = MinistryTeamRoleType.objects.create(
            code=MinistryTeamRoleType.CODE_LEAD,
            name="Lead",
            name_en="Lead",
        )
        coordinator_type = MinistryTeamRoleType.objects.create(
            code=MinistryTeamRoleType.CODE_COORDINATOR,
            name="Coordinator",
            name_en="Coordinator",
        )
        MinistryTeamRoleAssignment.objects.create(
            team=self.alpha_team,
            user=self.lead,
            role_type=lead_type,
            start_date=timezone.localdate(),
        )
        MinistryTeamRoleAssignment.objects.create(
            team=self.alpha_team,
            user=self.coordinator,
            role_type=coordinator_type,
            start_date=timezone.localdate(),
        )
        MinistryTeamRoleAssignment.objects.create(
            team=self.anchor_team,
            user=self.anchor_lead,
            role_type=lead_type,
            start_date=timezone.localdate(),
        )
        TeamMembership.objects.create(
            team=self.alpha_team,
            user=self.membership_role_only,
            role=TeamMembership.ROLE_LEAD,
        )
        TeamMembership.objects.create(
            team=self.alpha_team,
            user=self.can_lead_only,
            can_lead=True,
        )

        self.beta_membership = TeamMembership.objects.create(
            team=self.beta_team,
            display_name="Beta Scheduled Person",
            email="beta-person-private@example.com",
        )
        self.delta_membership = TeamMembership.objects.create(
            team=self.delta_team,
            display_name="Delta Additional Person",
        )
        self.gamma_membership = TeamMembership.objects.create(
            team=self.gamma_team,
            display_name="Gamma Unrelated Person",
        )

        days_until_sunday = (6 - timezone.localdate().weekday()) % 7
        self.event = self.create_event(
            "Arbitrary Sunday Gathering",
            days_from_today=days_until_sunday,
            rotation_anchor_team=self.anchor_team,
        )
        self.event.required_teams.add(
            self.alpha_team,
            self.beta_team,
            self.empty_team,
        )
        self.beta_assignment = self.create_assignment(
            self.event,
            self.beta_team,
            membership=self.beta_membership,
            notes="Cross-team private note must never render.",
        )
        self.beta_assignment.assignment_members.update(confirmed_at=timezone.now())
        self.empty_assignment = self.create_assignment(self.event, self.empty_team)
        self.delta_assignment = self.create_assignment(
            self.event,
            self.delta_team,
            membership=self.delta_membership,
        )

        self.unrelated_event = self.create_event(
            "Unrelated Team Sunday",
            days_from_today=days_until_sunday + 7,
        )
        self.unrelated_event.required_teams.add(self.gamma_team)
        self.unrelated_assignment = self.create_assignment(
            self.unrelated_event,
            self.gamma_team,
            membership=self.gamma_membership,
        )

        self.no_participants_event = self.create_event(
            "No Scheduling Data Sunday",
            days_from_today=days_until_sunday + 14,
        )
        self.own_assignment_event = self.create_event(
            "Own Team Additional Sunday",
            days_from_today=days_until_sunday + 14,
        )
        self.create_assignment(self.own_assignment_event, self.alpha_team)
        bible_event = self.create_event(
            "Not a Sunday Service Type",
            days_from_today=days_until_sunday + 21,
            event_type=ServiceEvent.EVENT_BIBLE_STUDY,
        )
        bible_event.required_teams.add(self.alpha_team)
        draft_event = self.create_event(
            "Draft Sunday",
            days_from_today=days_until_sunday + 28,
            status=ServiceEvent.STATUS_DRAFT,
        )
        draft_event.required_teams.add(self.alpha_team)
        cancelled_event = self.create_event(
            "Cancelled Sunday",
            days_from_today=days_until_sunday + 35,
            status=ServiceEvent.STATUS_CANCELLED,
        )
        cancelled_event.required_teams.add(self.alpha_team)
        outside_window = self.create_event(
            "Outside Board Window",
            days_from_today=70,
        )
        outside_window.required_teams.add(self.alpha_team)

    def local_datetime(self, days_from_today):
        local_date = timezone.localdate() + timezone.timedelta(days=days_from_today)
        return timezone.make_aware(
            datetime.combine(local_date, datetime.min.time()).replace(hour=10),
            timezone.get_current_timezone(),
        )

    def create_event(
        self,
        title,
        *,
        days_from_today,
        event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
        status=ServiceEvent.STATUS_PUBLISHED,
        rotation_anchor_team=None,
    ):
        event = ServiceEvent.objects.create(
            title=title,
            title_en=title,
            event_type=event_type,
            start_datetime=self.local_datetime(days_from_today),
            status=status,
            rotation_anchor_team=rotation_anchor_team,
        )
        ServiceEventAudienceScope.objects.create(service_event=event, unit=self.cm)
        return event

    def create_assignment(self, event, team, *, membership=None, notes=""):
        assignment = TeamAssignment.objects.create(
            service_event=event,
            ministry_team=team,
            status=TeamAssignment.STATUS_SCHEDULED,
            notes=notes,
            created_by=self.global_manager,
        )
        if membership is not None:
            TeamAssignmentMember.objects.create(
                assignment=assignment,
                membership=membership,
            )
        return assignment

    def create_stored_assignment(self, event, team):
        assignment = TeamAssignment(
            service_event=event,
            ministry_team=team,
            status=TeamAssignment.STATUS_SCHEDULED,
            created_by=self.global_manager,
        )
        TeamAssignment.objects.bulk_create([assignment])
        return assignment

    def set_language(self, language):
        session = self.client.session
        session["language"] = language
        session.save()

    def login(self, user):
        self.client.force_login(user)
        self.set_language("en")

    def board_cells(self, response):
        board = response.context["board"]
        event_row = next(
            row for row in board["rows"] if row["event"].id == self.event.id
        )
        return {cell["team"].id: cell for cell in event_row["cells"]}

    def test_staff_global_manager_lead_and_coordinator_can_access(self):
        for user in [
            self.staff,
            self.superuser,
            self.global_manager,
            self.lead,
            self.coordinator,
        ]:
            with self.subTest(user=user.username):
                self.login(user)
                response = self.client.get(reverse("sunday_schedule_board"))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "Sunday Schedule Board")

    def test_ordinary_and_legacy_membership_flags_do_not_grant_board(self):
        for user in [self.ordinary, self.membership_role_only, self.can_lead_only]:
            with self.subTest(user=user.username):
                self.login(user)
                response = self.client.get(reverse("sunday_schedule_board"))
                self.assertRedirects(response, reverse("my_serving"))

    def test_exact_team_scheduler_rows_are_anchored_to_own_manageable_team(self):
        self.login(self.lead)

        response = self.client.get(reverse("sunday_schedule_board"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.event.title_en)
        self.assertContains(response, self.own_assignment_event.title_en)
        self.assertNotContains(response, self.unrelated_event.title_en)
        self.assertNotContains(response, "Gamma Unrelated Person")
        self.assertFalse(self.event.can_be_seen_by(self.lead))
        self.assertNotContains(
            response,
            reverse("service_event_detail", args=[self.event.id]),
        )

    def test_global_operational_set_requires_sunday_row_scheduling_data(self):
        self.login(self.global_manager)

        response = self.client.get(reverse("sunday_schedule_board"))

        self.assertContains(response, self.event.title_en)
        self.assertContains(response, self.unrelated_event.title_en)
        self.assertContains(response, self.own_assignment_event.title_en)
        self.assertNotContains(response, self.no_participants_event.title_en)
        self.assertNotContains(response, "Not a Sunday Service Type")
        self.assertNotContains(response, "Draft Sunday")
        self.assertNotContains(response, "Cancelled Sunday")
        self.assertNotContains(response, "Outside Board Window")

    def test_cross_team_projection_is_narrow_and_detail_permission_is_unchanged(self):
        self.login(self.lead)

        response = self.client.get(reverse("sunday_schedule_board"))

        self.assertContains(response, "Beta Team")
        self.assertContains(response, "Beta Scheduled Person")
        self.assertNotContains(response, "Cross-team private note must never render.")
        self.assertNotContains(response, "beta-private@example.com")
        self.assertNotContains(response, "beta-person-private@example.com")
        self.assertNotContains(response, "Confirmed")
        self.assertNotContains(response, "Awaiting confirmation")

        detail_response = self.client.get(
            reverse("team_assignment_detail", args=[self.beta_assignment.id])
        )
        self.assertRedirects(detail_response, reverse("team_assignment_list"))

    def test_downstream_lead_sees_narrow_current_worship_roster(self):
        worship_membership = TeamMembership.objects.create(
            team=self.anchor_team,
            display_name="Worship Scheduled Person",
            email="worship-private@example.com",
        )
        worship_assignment = self.create_assignment(
            self.event,
            self.anchor_team,
            membership=worship_membership,
            notes="Worship private note must not render.",
        )
        worship_assignment.assignment_members.update(
            confirmed_at=timezone.now(),
            confirmation_note="Private confirmation detail",
        )
        self.login(self.lead)

        response = self.client.get(reverse("sunday_schedule_board"))

        self.assertContains(response, "Worship serving")
        self.assertContains(response, "Worship Scheduled Person", count=1)
        self.assertNotIn(
            self.anchor_team.id,
            [team.id for team in response.context["board"]["teams"]],
        )
        context = next(
            row["worship_context"]
            for row in response.context["board"]["rows"]
            if row["event"].id == self.event.id
        )
        self.assertFalse(context["can_edit"])
        self.assertEqual(context["action_url"], "")
        self.assertNotContains(response, "Worship private note must not render.")
        self.assertNotContains(response, "worship-private@example.com")
        self.assertNotContains(response, "Private confirmation detail")
        self.assertNotContains(
            response,
            reverse("team_assignment_detail", args=[worship_assignment.id]),
        )
        detail_response = self.client.get(
            reverse("team_assignment_detail", args=[worship_assignment.id])
        )
        self.assertRedirects(detail_response, reverse("team_assignment_list"))

    def test_board_worship_context_distinguishes_no_anchor_empty_and_duplicates(self):
        self.event.rotation_anchor_team = None
        self.event.save()
        self.login(self.lead)
        response = self.client.get(reverse("sunday_schedule_board"))
        self.assertContains(response, "Worship Team not selected")

        self.event.rotation_anchor_team = self.anchor_team
        self.event.save()
        empty_assignment = self.create_assignment(self.event, self.anchor_team)
        response = self.client.get(reverse("sunday_schedule_board"))
        self.assertContains(response, "Worship scheduled · no active members")

        self.create_stored_assignment(self.event, self.anchor_team)
        response = self.client.get(reverse("sunday_schedule_board"))
        self.assertContains(
            response,
            "Multiple current Worship assignments · review required",
        )
        self.assertNotContains(response, "Worship serving")
        self.assertTrue(TeamAssignment.objects.filter(id=empty_assignment.id).exists())

    def test_board_worship_context_copy_is_bilingual(self):
        self.login(self.lead)
        self.set_language("zh")

        response = self.client.get(reverse("sunday_schedule_board"))

        self.assertContains(response, "已选择，尚未排班")

    def test_board_states_columns_anchor_and_edit_authority(self):
        self.login(self.lead)

        response = self.client.get(reverse("sunday_schedule_board"))
        board = response.context["board"]
        cells = self.board_cells(response)

        self.assertEqual(
            [team.name for team in board["teams"]],
            ["Alpha Team", "Beta Team", "Delta Team", "Empty Team"],
        )
        self.assertEqual(cells[self.alpha_team.id]["state"], "missing")
        self.assertTrue(cells[self.alpha_team.id]["can_edit"])
        self.assertIn(f"event={self.event.id}", cells[self.alpha_team.id]["action_url"])
        self.assertEqual(cells[self.beta_team.id]["state"], "scheduled")
        self.assertEqual(
            cells[self.beta_team.id]["member_names"], ["Beta Scheduled Person"]
        )
        self.assertFalse(cells[self.beta_team.id]["can_edit"])
        self.assertEqual(cells[self.empty_team.id]["state"], "empty")
        self.assertEqual(cells[self.delta_team.id]["state"], "scheduled")
        self.assertTrue(cells[self.delta_team.id]["is_additional"])
        self.assertContains(response, "Anchor Team")
        self.assertNotContains(response, "Projection")
        self.assertNotContains(response, "Lighting")

    def test_exact_anchor_lead_keeps_row_scope_and_gets_existing_schedule_action(self):
        worship_assignment = self.create_assignment(self.event, self.anchor_team)
        self.login(self.anchor_lead)

        response = self.client.get(reverse("sunday_schedule_board"))
        row = next(
            row
            for row in response.context["board"]["rows"]
            if row["event"].id == self.event.id
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotIn(
            self.anchor_team.id,
            [team.id for team in response.context["board"]["teams"]],
        )
        self.assertTrue(row["worship_context"]["can_edit"])
        self.assertEqual(row["worship_context"]["action_kind"], "edit")
        self.assertIn(
            f"assignment={worship_assignment.id}",
            row["worship_context"]["action_url"],
        )
        self.assertContains(response, "Edit Worship")

    def test_exact_anchor_lead_can_schedule_unscheduled_required_anchor(self):
        anchor_only_event = self.create_event(
            "Anchor Only Sunday",
            days_from_today=(6 - timezone.localdate().weekday()) % 7 + 7,
            rotation_anchor_team=self.anchor_team,
        )
        anchor_only_event.required_teams.add(self.anchor_team)
        self.login(self.anchor_lead)

        response = self.client.get(reverse("sunday_schedule_board"))
        row = next(
            row
            for row in response.context["board"]["rows"]
            if row["event"].id == anchor_only_event.id
        )

        self.assertFalse(any(cell["participates"] for cell in row["cells"]))
        self.assertTrue(row["worship_context"]["can_edit"])
        self.assertEqual(row["worship_context"]["action_kind"], "schedule")
        self.assertIn(
            f"event={anchor_only_event.id}",
            row["worship_context"]["action_url"],
        )
        self.assertContains(response, "Schedule Worship")

    def test_anchor_team_remains_a_generic_cell_when_non_anchor_elsewhere(self):
        self.create_stored_assignment(self.event, self.anchor_team)
        mixed_event = self.create_event(
            "Anchor Team In Ordinary Role",
            days_from_today=(6 - timezone.localdate().weekday()) % 7 + 7,
        )
        mixed_event.required_teams.add(self.anchor_team)
        self.login(self.global_manager)

        response = self.client.get(reverse("sunday_schedule_board"))
        board = response.context["board"]
        self.assertIn(self.anchor_team.id, [team.id for team in board["teams"]])
        anchor_row = next(row for row in board["rows"] if row["event"].id == self.event.id)
        ordinary_row = next(
            row for row in board["rows"] if row["event"].id == mixed_event.id
        )
        anchor_cell = next(
            cell for cell in anchor_row["cells"] if cell["team"].id == self.anchor_team.id
        )
        ordinary_cell = next(
            cell for cell in ordinary_row["cells"] if cell["team"].id == self.anchor_team.id
        )

        self.assertFalse(anchor_cell["participates"])
        self.assertTrue(ordinary_cell["participates"])
        self.assertEqual(ordinary_cell["state"], "missing")

    def test_duplicate_and_unavailable_anchor_contexts_have_no_action(self):
        self.create_assignment(self.event, self.anchor_team)
        self.create_stored_assignment(self.event, self.anchor_team)
        self.login(self.anchor_lead)

        duplicate_response = self.client.get(reverse("sunday_schedule_board"))
        duplicate_context = next(
            row["worship_context"]
            for row in duplicate_response.context["board"]["rows"]
            if row["event"].id == self.event.id
        )
        self.assertFalse(duplicate_context["can_edit"])
        self.assertEqual(duplicate_context["action_url"], "")
        self.assertNotContains(duplicate_response, "Edit Worship")

        self.anchor_team.is_assignable = False
        self.anchor_team.save(update_fields=["is_assignable"])
        unavailable_response = self.client.get(reverse("sunday_schedule_board"))
        unavailable_context = next(
            row["worship_context"]
            for row in unavailable_response.context["board"]["rows"]
            if row["event"].id == self.event.id
        )
        self.assertFalse(unavailable_context["can_edit"])
        self.assertEqual(unavailable_context["action_url"], "")

    def test_forged_anchor_schedule_post_is_rejected_for_downstream_lead(self):
        worship_assignment = self.create_assignment(self.event, self.anchor_team)
        self.login(self.lead)

        response = self.client.post(
            reverse("team_schedule", args=[self.anchor_team.id]),
            {
                "assignment_id": worship_assignment.id,
                "status": TeamAssignment.STATUS_SCHEDULED,
                "notes": "Forged Worship note",
            },
        )

        self.assertRedirects(response, reverse("ministry_team_list"))
        worship_assignment.refresh_from_db()
        self.assertEqual(worship_assignment.notes, "")

    def test_duplicate_assignment_cell_fails_closed_to_read_only(self):
        self.create_assignment(self.event, self.alpha_team)
        self.create_assignment(self.event, self.alpha_team)
        self.login(self.lead)

        response = self.client.get(reverse("sunday_schedule_board"))
        cell = self.board_cells(response)[self.alpha_team.id]

        self.assertTrue(cell["has_duplicate_assignments"])
        self.assertFalse(cell["can_edit"])
        self.assertEqual(cell["action_url"], "")
        self.assertContains(response, "Multiple assignments found")

    def test_board_get_and_rejected_posts_have_no_side_effects_or_notifications(self):
        self.login(self.lead)
        before_assignments = TeamAssignment.objects.count()
        before_members = TeamAssignmentMember.objects.count()
        payloads = []

        with notification_sink_override_for_tests(payloads.append):
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.get(reverse("sunday_schedule_board"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(TeamAssignment.objects.count(), before_assignments)
        self.assertEqual(TeamAssignmentMember.objects.count(), before_members)
        self.assertEqual(payloads, [])

        board_post = self.client.post(reverse("sunday_schedule_board"), {})
        self.assertEqual(board_post.status_code, 405)

        forged_post = self.client.post(
            reverse("team_schedule", args=[self.beta_team.id]),
            {
                "assigned_members": [self.beta_membership.id],
                "status": TeamAssignment.STATUS_SCHEDULED,
                "notes": "Forged replacement note",
            },
        )
        self.assertRedirects(forged_post, reverse("ministry_team_list"))
        self.beta_assignment.refresh_from_db()
        self.assertEqual(
            self.beta_assignment.notes,
            "Cross-team private note must never render.",
        )
        self.assertEqual(TeamAssignment.objects.count(), before_assignments)
        self.assertEqual(TeamAssignmentMember.objects.count(), before_members)

    def test_my_serving_entry_point_is_scheduler_only_and_bilingual(self):
        self.login(self.lead)
        response = self.client.get(reverse("my_serving"))
        self.assertContains(response, reverse("sunday_schedule_board"))
        self.assertContains(response, "Sunday Schedule Board")

        self.set_language("zh")
        chinese_response = self.client.get(reverse("sunday_schedule_board"))
        self.assertContains(chinese_response, "主日服事排班总览")
        self.assertContains(chinese_response, "缺少排班")

        self.client.force_login(self.ordinary)
        self.set_language("en")
        ordinary_response = self.client.get(reverse("my_serving"))
        self.assertNotContains(ordinary_response, reverse("sunday_schedule_board"))
