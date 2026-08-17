from datetime import datetime

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import ChurchRoleAssignment
from core.notification_delivery import notification_sink_override_for_tests
from events.models import ServiceEvent

from .models import (
    MinistryTeam,
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
        self.anchor_team = MinistryTeam.objects.create(
            name="Anchor Team",
            name_en="Anchor Team",
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
        return ServiceEvent.objects.create(
            title=title,
            title_en=title,
            event_type=event_type,
            start_datetime=self.local_datetime(days_from_today),
            status=status,
            rotation_anchor_team=rotation_anchor_team,
        )

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
