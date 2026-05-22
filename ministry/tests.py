from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from django.apps import apps
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command, CommandError
from django.test import TestCase
from django.urls import NoReverseMatch, reverse
from django.utils import timezone

from accounts.models import ChurchRoleAssignment
from events.models import ServiceEvent

from .models import (
    MinistryTeam,
    TeamAssignment,
    TeamAssignmentMember,
    TeamMembership,
)


class MinistryTeamFoundationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="regular",
            email="regular@example.com",
            password="testpass123",
        )
        self.other_user = User.objects.create_user(
            username="other",
            email="other@example.com",
            password="testpass123",
        )
        self.staff = User.objects.create_user(
            username="ministry_staff",
            email="staff@example.com",
            password="testpass123",
            is_staff=True,
        )
        self.manager = User.objects.create_user(
            username="pastor_ministry",
            email="pastor@example.com",
            password="testpass123",
        )
        ChurchRoleAssignment.objects.create(
            user=self.manager,
            role=ChurchRoleAssignment.ROLE_PASTOR,
            scope_type=ChurchRoleAssignment.SCOPE_GLOBAL,
        )
        self.lead_user = User.objects.create_user(
            username="team_lead",
            email="lead@example.com",
            password="testpass123",
        )
        self.team = MinistryTeam.objects.create(
            name="灯光团队",
            name_en="Lighting Team",
            description="负责聚会灯光。",
            description_en="Handles service lighting.",
            email_alias="lighting@example.org",
            playbook_link="https://example.com/playbook",
        )
        self.other_team = MinistryTeam.objects.create(
            name="音响团队",
            name_en="Sound Team",
        )

    def set_language(self, language="en"):
        session = self.client.session
        session["language"] = language
        session.save()

    def team_post_data(self, **overrides):
        data = {
            "name": "招待团队",
            "name_en": "Usher Team",
            "description": "中文描述",
            "description_en": "English description",
            "email_alias": "ushers@example.org",
            "playbook_link": "https://example.com/ushers",
            "is_active": "on",
        }
        data.update(overrides)
        return data

    def membership_post_data(self, **overrides):
        data = {
            "user": self.user.id,
            "display_name": "",
            "email": "",
            "role": TeamMembership.ROLE_MEMBER,
            "skill_level": "Beginner",
            "can_lead": "",
            "notes": "Public workflow note only.",
            "is_active": "on",
        }
        data.update(overrides)
        return data

    def create_membership(self, **overrides):
        data = {
            "team": self.team,
            "user": self.user,
            "role": TeamMembership.ROLE_MEMBER,
            "is_active": True,
        }
        data.update(overrides)
        return TeamMembership.objects.create(**data)

    def test_ministry_team_list_requires_login(self):
        response = self.client.get(reverse("ministry_team_list"))

        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_staff_can_access_team_list_and_create_team(self):
        self.set_language("en")
        self.client.login(username="ministry_staff", password="testpass123")

        list_response = self.client.get(reverse("ministry_team_list"))
        create_response = self.client.get(reverse("create_ministry_team"))

        self.assertEqual(list_response.status_code, 200)
        self.assertContains(list_response, "Lighting Team")
        self.assertEqual(create_response.status_code, 200)
        self.assertContains(create_response, "New Ministry Team")

    def test_user_with_capability_can_access_create_team(self):
        self.set_language("en")
        self.client.login(username="pastor_ministry", password="testpass123")

        response = self.client.get(reverse("create_ministry_team"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "New Ministry Team")

    def test_regular_user_cannot_access_create_team(self):
        self.set_language("en")
        self.client.login(username="regular", password="testpass123")

        response = self.client.get(reverse("create_ministry_team"))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("ministry_team_list"))

    def test_manager_can_create_ministry_team(self):
        self.set_language("en")
        self.client.login(username="pastor_ministry", password="testpass123")

        response = self.client.post(reverse("create_ministry_team"), self.team_post_data())

        self.assertEqual(response.status_code, 302)
        team = MinistryTeam.objects.get(name="招待团队")
        self.assertEqual(team.name_en, "Usher Team")
        self.assertEqual(team.email_alias, "ushers@example.org")

    def test_manager_can_edit_ministry_team(self):
        self.set_language("en")
        self.client.login(username="pastor_ministry", password="testpass123")

        response = self.client.post(
            reverse("edit_ministry_team", args=[self.team.id]),
            self.team_post_data(name="更新团队", name_en="Updated Team"),
        )

        self.assertEqual(response.status_code, 302)
        self.team.refresh_from_db()
        self.assertEqual(self.team.name, "更新团队")
        self.assertEqual(self.team.name_en, "Updated Team")

    def test_team_member_can_view_own_active_team(self):
        self.set_language("en")
        self.create_membership()
        self.client.login(username="regular", password="testpass123")

        response = self.client.get(reverse("ministry_team_detail", args=[self.team.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Lighting Team")

    def test_unrelated_regular_user_cannot_view_team_detail(self):
        self.set_language("en")
        self.client.login(username="other", password="testpass123")

        response = self.client.get(reverse("ministry_team_detail", args=[self.team.id]))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("ministry_team_list"))

    def test_manager_can_add_user_linked_membership(self):
        self.set_language("en")
        self.client.login(username="pastor_ministry", password="testpass123")

        response = self.client.post(
            reverse("manage_team_members", args=[self.team.id]),
            self.membership_post_data(),
        )

        self.assertEqual(response.status_code, 302)
        membership = TeamMembership.objects.get(team=self.team, user=self.user)
        self.assertEqual(membership.skill_level, "Beginner")

    def test_manager_can_add_display_name_only_membership_without_user(self):
        self.set_language("en")
        self.client.login(username="pastor_ministry", password="testpass123")

        response = self.client.post(
            reverse("manage_team_members", args=[self.team.id]),
            self.membership_post_data(
                user="",
                display_name="Guest Helper",
                email="helper@example.org",
            ),
        )

        self.assertEqual(response.status_code, 302)
        membership = TeamMembership.objects.get(team=self.team, display_name="Guest Helper")
        self.assertEqual(membership.get_display_name(), "Guest Helper")

    def test_membership_without_user_requires_display_name(self):
        membership = TeamMembership(team=self.team, user=None, display_name="")

        with self.assertRaises(ValidationError):
            membership.full_clean()

    def test_duplicate_active_membership_for_same_user_team_is_rejected(self):
        self.create_membership()
        duplicate = TeamMembership(team=self.team, user=self.user)

        with self.assertRaises(ValidationError):
            duplicate.full_clean()

    def test_team_lead_can_manage_members_for_own_team(self):
        self.set_language("en")
        TeamMembership.objects.create(
            team=self.team,
            user=self.lead_user,
            role=TeamMembership.ROLE_LEAD,
        )
        self.client.login(username="team_lead", password="testpass123")

        response = self.client.get(reverse("manage_team_members", args=[self.team.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Manage Members")

    def test_team_lead_cannot_manage_another_team(self):
        self.set_language("en")
        TeamMembership.objects.create(
            team=self.team,
            user=self.lead_user,
            role=TeamMembership.ROLE_COORDINATOR,
        )
        self.client.login(username="team_lead", password="testpass123")

        response = self.client.get(
            reverse("manage_team_members", args=[self.other_team.id])
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("ministry_team_list"))

    def test_manager_can_deactivate_membership(self):
        self.set_language("en")
        membership = self.create_membership()
        self.client.login(username="pastor_ministry", password="testpass123")

        response = self.client.post(
            reverse("deactivate_team_membership", args=[membership.id])
        )

        self.assertEqual(response.status_code, 302)
        membership.refresh_from_db()
        self.assertFalse(membership.is_active)

    def test_deactivated_membership_no_longer_grants_team_view_access(self):
        self.set_language("en")
        self.create_membership(is_active=False)
        self.client.login(username="regular", password="testpass123")

        response = self.client.get(reverse("ministry_team_detail", args=[self.team.id]))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("ministry_team_list"))

    def test_chinese_team_pages_show_chinese_labels(self):
        self.set_language("zh")
        self.create_membership()
        self.client.login(username="pastor_ministry", password="testpass123")

        list_response = self.client.get(reverse("ministry_team_list"))
        detail_response = self.client.get(reverse("ministry_team_detail", args=[self.team.id]))
        form_response = self.client.get(reverse("manage_team_members", args=[self.team.id]))

        self.assertContains(list_response, "事工团队")
        self.assertContains(detail_response, "管理成员")
        self.assertContains(form_response, "非敏感备注")

    def test_english_team_pages_show_english_labels(self):
        self.set_language("en")
        self.create_membership()
        self.client.login(username="pastor_ministry", password="testpass123")

        list_response = self.client.get(reverse("ministry_team_list"))
        detail_response = self.client.get(reverse("ministry_team_detail", args=[self.team.id]))
        form_response = self.client.get(reverse("manage_team_members", args=[self.team.id]))

        self.assertContains(list_response, "Ministry Teams")
        self.assertContains(detail_response, "Manage Members")
        self.assertContains(form_response, "Non-sensitive notes")

    def test_normal_top_nav_does_not_show_ministry_teams(self):
        self.set_language("en")
        self.client.login(username="regular", password="testpass123")

        response = self.client.get(reverse("ministry_team_list"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, '<nav class="nav">Ministry Teams', html=False)
        self.assertNotContains(response, 'href="/teams/">Ministry Teams', html=False)

    def test_staff_menu_includes_ministry_teams(self):
        self.set_language("en")
        self.client.login(username="ministry_staff", password="testpass123")

        response = self.client.get(reverse("ministry_team_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ministry Teams")
        self.assertContains(response, 'href="/teams/"', html=False)

    def test_no_lighting_team_routes_exist_in_this_task(self):
        with self.assertRaises(NoReverseMatch):
            reverse("lighting_team_list")


class TeamAssignmentV1Tests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="regular_assign",
            email="regular-assign@example.com",
            password="testpass123",
        )
        self.other_user = User.objects.create_user(
            username="other_assign",
            email="other-assign@example.com",
            password="testpass123",
        )
        self.staff = User.objects.create_user(
            username="assignment_staff",
            email="assignment-staff@example.com",
            password="testpass123",
            is_staff=True,
        )
        self.manager = User.objects.create_user(
            username="assignment_pastor",
            email="assignment-pastor@example.com",
            password="testpass123",
        )
        ChurchRoleAssignment.objects.create(
            user=self.manager,
            role=ChurchRoleAssignment.ROLE_PASTOR,
            scope_type=ChurchRoleAssignment.SCOPE_GLOBAL,
        )
        self.lead_user = User.objects.create_user(
            username="assignment_lead",
            email="assignment-lead@example.com",
            password="testpass123",
        )

        self.team = MinistryTeam.objects.create(
            name="灯光团队",
            name_en="Lighting Team",
            playbook_link="https://example.com/playbook",
        )
        self.other_team = MinistryTeam.objects.create(
            name="音响团队",
            name_en="Sound Team",
        )
        self.membership = TeamMembership.objects.create(
            team=self.team,
            user=self.user,
            role=TeamMembership.ROLE_MEMBER,
        )
        self.second_membership = TeamMembership.objects.create(
            team=self.team,
            user=self.other_user,
            role=TeamMembership.ROLE_MEMBER,
        )
        self.lead_membership = TeamMembership.objects.create(
            team=self.team,
            user=self.lead_user,
            role=TeamMembership.ROLE_LEAD,
        )
        self.other_team_membership = TeamMembership.objects.create(
            team=self.other_team,
            display_name="Other Helper",
            role=TeamMembership.ROLE_MEMBER,
        )
        self.event = ServiceEvent.objects.create(
            title="主日崇拜",
            title_en="Sunday Service",
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
            start_datetime=timezone.now() + timezone.timedelta(days=2),
            scope_type=ServiceEvent.SCOPE_GLOBAL,
            status=ServiceEvent.STATUS_PUBLISHED,
        )

    def set_language(self, language="en"):
        session = self.client.session
        session["language"] = language
        session.save()

    def assignment_post_data(self, **overrides):
        data = {
            "service_event": self.event.id,
            "ministry_team": self.team.id,
            "assigned_members": [self.membership.id],
            "status": TeamAssignment.STATUS_SCHEDULED,
            "notes": "Bring the operational playbook.",
        }
        data.update(overrides)
        return data

    def create_assignment(self, members=None, **overrides):
        data = {
            "service_event": self.event,
            "ministry_team": self.team,
            "status": TeamAssignment.STATUS_SCHEDULED,
            "notes": "Operational note.",
            "created_by": self.manager,
        }
        data.update(overrides)
        assignment = TeamAssignment.objects.create(**data)
        for membership in members or [self.membership]:
            TeamAssignmentMember.objects.create(
                assignment=assignment,
                membership=membership,
            )
        return assignment

    def test_assignment_list_requires_login(self):
        response = self.client.get(reverse("team_assignment_list"))

        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_staff_global_manager_can_access_assignment_list(self):
        self.set_language("en")
        assignment = self.create_assignment()
        self.client.login(username="assignment_staff", password="testpass123")

        response = self.client.get(reverse("team_assignment_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Team Assignments")
        self.assertContains(response, assignment.service_event.title_en)

    def test_regular_unrelated_user_cannot_see_unrelated_assignments(self):
        self.set_language("en")
        self.create_assignment(members=[self.second_membership])
        self.client.login(username="regular_assign", password="testpass123")

        response = self.client.get(reverse("team_assignment_list"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Sunday Service")

    def test_team_lead_can_see_own_team_assignments(self):
        self.set_language("en")
        self.create_assignment()
        self.client.login(username="assignment_lead", password="testpass123")

        response = self.client.get(reverse("team_assignment_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sunday Service")

    def test_team_lead_cannot_manage_other_team_assignments(self):
        self.set_language("en")
        assignment = self.create_assignment(
            members=[self.other_team_membership],
            ministry_team=self.other_team,
        )
        self.client.login(username="assignment_lead", password="testpass123")

        response = self.client.get(reverse("edit_team_assignment", args=[assignment.id]))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("team_assignment_list"))

    def test_manager_can_create_assignment(self):
        self.set_language("en")
        self.client.login(username="assignment_pastor", password="testpass123")

        response = self.client.post(
            reverse("create_team_assignment"),
            self.assignment_post_data(),
        )

        self.assertEqual(response.status_code, 302)
        assignment = TeamAssignment.objects.get(notes="Bring the operational playbook.")
        self.assertEqual(assignment.created_by, self.manager)
        self.assertEqual(assignment.assigned_members.count(), 1)

    def test_team_lead_can_create_assignment_only_for_own_team(self):
        self.set_language("en")
        self.client.login(username="assignment_lead", password="testpass123")

        own_response = self.client.post(
            reverse("create_team_assignment"),
            self.assignment_post_data(assigned_members=[self.membership.id]),
        )
        other_response = self.client.post(
            reverse("create_team_assignment"),
            self.assignment_post_data(
                ministry_team=self.other_team.id,
                assigned_members=[self.other_team_membership.id],
                notes="Unauthorized assignment",
            ),
        )

        self.assertEqual(own_response.status_code, 302)
        self.assertEqual(other_response.status_code, 200)
        self.assertFalse(
            TeamAssignment.objects.filter(notes="Unauthorized assignment").exists()
        )

    def test_manager_can_edit_assignment(self):
        self.set_language("en")
        assignment = self.create_assignment()
        self.client.login(username="assignment_pastor", password="testpass123")

        response = self.client.post(
            reverse("edit_team_assignment", args=[assignment.id]),
            self.assignment_post_data(
                notes="Updated operational note.",
                assigned_members=[self.membership.id, self.second_membership.id],
            ),
        )

        self.assertEqual(response.status_code, 302)
        assignment.refresh_from_db()
        self.assertEqual(assignment.notes, "Updated operational note.")
        self.assertEqual(assignment.assigned_members.count(), 2)

    def test_manager_can_cancel_assignment(self):
        self.set_language("en")
        assignment = self.create_assignment()
        self.client.login(username="assignment_pastor", password="testpass123")

        response = self.client.post(reverse("cancel_team_assignment", args=[assignment.id]))

        self.assertEqual(response.status_code, 302)
        assignment.refresh_from_db()
        self.assertEqual(assignment.status, TeamAssignment.STATUS_CANCELLED)

    def test_assigned_member_can_view_assignment_detail(self):
        self.set_language("en")
        assignment = self.create_assignment()
        self.client.login(username="regular_assign", password="testpass123")

        response = self.client.get(reverse("team_assignment_detail", args=[assignment.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Team Assignment")

    def test_assigned_member_can_confirm_assignment(self):
        self.set_language("en")
        assignment = self.create_assignment()
        self.client.login(username="regular_assign", password="testpass123")

        response = self.client.post(
            reverse("confirm_team_assignment", args=[assignment.id]),
            {"confirmation_note": "Confirmed."},
        )

        self.assertEqual(response.status_code, 302)
        assignment_member = assignment.assignment_members.get(membership=self.membership)
        self.assertIsNotNone(assignment_member.confirmed_at)
        self.assertEqual(assignment_member.confirmation_note, "Confirmed.")

    def test_unassigned_user_cannot_confirm_assignment(self):
        self.set_language("en")
        assignment = self.create_assignment(members=[self.second_membership])
        self.client.login(username="regular_assign", password="testpass123")

        response = self.client.post(reverse("confirm_team_assignment", args=[assignment.id]))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("team_assignment_list"))
        self.assertFalse(
            assignment.assignment_members.filter(confirmed_at__isnull=False).exists()
        )

    def test_manager_cannot_confirm_for_an_unassigned_member(self):
        self.set_language("en")
        assignment = self.create_assignment()
        self.client.login(username="assignment_pastor", password="testpass123")

        response = self.client.post(reverse("confirm_team_assignment", args=[assignment.id]))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("team_assignment_list"))
        self.assertFalse(
            assignment.assignment_members.filter(confirmed_at__isnull=False).exists()
        )

    def test_duplicate_team_assignment_member_is_rejected(self):
        assignment = self.create_assignment()
        duplicate = TeamAssignmentMember(assignment=assignment, membership=self.membership)

        with self.assertRaises(ValidationError):
            duplicate.full_clean()

    def test_assignment_member_must_belong_to_assignment_team(self):
        assignment = self.create_assignment()
        invalid = TeamAssignmentMember(
            assignment=assignment,
            membership=self.other_team_membership,
        )

        with self.assertRaises(ValidationError):
            invalid.full_clean()

    def test_inactive_membership_cannot_be_assigned(self):
        inactive = TeamMembership.objects.create(
            team=self.team,
            display_name="Inactive Helper",
            is_active=False,
        )
        assignment = self.create_assignment()
        invalid = TeamAssignmentMember(assignment=assignment, membership=inactive)

        with self.assertRaises(ValidationError):
            invalid.full_clean()

    def test_all_members_confirmed_sets_assignment_confirmed(self):
        assignment = self.create_assignment(members=[self.membership, self.second_membership])

        for assignment_member in assignment.assignment_members.all():
            assignment_member.confirm()
        if assignment.all_members_confirmed():
            assignment.status = TeamAssignment.STATUS_CONFIRMED
            assignment.save()

        assignment.refresh_from_db()
        self.assertEqual(assignment.status, TeamAssignment.STATUS_CONFIRMED)

    def test_chinese_assignment_pages_show_chinese_labels(self):
        self.set_language("zh")
        assignment = self.create_assignment()
        self.client.login(username="assignment_pastor", password="testpass123")

        list_response = self.client.get(reverse("team_assignment_list"))
        form_response = self.client.get(reverse("create_team_assignment"))
        detail_response = self.client.get(reverse("team_assignment_detail", args=[assignment.id]))

        self.assertContains(list_response, "服事排班")
        self.assertContains(form_response, "新增排班")
        self.assertContains(detail_response, "非敏感排班备注")

    def test_english_assignment_pages_show_english_labels(self):
        self.set_language("en")
        assignment = self.create_assignment()
        self.client.login(username="assignment_pastor", password="testpass123")

        list_response = self.client.get(reverse("team_assignment_list"))
        form_response = self.client.get(reverse("create_team_assignment"))
        detail_response = self.client.get(reverse("team_assignment_detail", args=[assignment.id]))

        self.assertContains(list_response, "Team Assignments")
        self.assertContains(form_response, "New Assignment")
        self.assertContains(detail_response, "Non-sensitive assignment notes")

    def test_normal_top_nav_does_not_show_team_assignments(self):
        self.set_language("en")
        self.client.login(username="regular_assign", password="testpass123")

        response = self.client.get(reverse("team_assignment_list"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'href="/assignments/">Team Assignments', html=False)

    def test_staff_menu_includes_team_assignments(self):
        self.set_language("en")
        self.client.login(username="assignment_staff", password="testpass123")

        response = self.client.get(reverse("team_assignment_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'href="/assignments/"', html=False)

    def test_no_lighting_or_future_workflow_routes_exist(self):
        missing_routes = [
            "lighting_team_list",
            "availability_matrix",
            "swap_request_list",
            "team_reminder_list",
            "assignment_checklist",
            "team_import",
        ]
        for route_name in missing_routes:
            with self.assertRaises(NoReverseMatch):
                reverse(route_name)

    def test_my_serving_requires_login(self):
        response = self.client.get(reverse("my_serving"))

        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_assigned_user_sees_own_upcoming_assignment_on_my_serving(self):
        self.set_language("en")
        self.create_assignment()
        self.client.login(username="regular_assign", password="testpass123")

        response = self.client.get(reverse("my_serving"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "My Serving")
        self.assertContains(response, "Sunday Service")
        self.assertContains(response, "Lighting Team")
        self.assertContains(response, "Operational note.")
        self.assertContains(response, "https://example.com/playbook")

    def test_assigned_user_does_not_see_unrelated_assignment_on_my_serving(self):
        self.set_language("en")
        self.create_assignment(members=[self.second_membership])
        self.client.login(username="regular_assign", password="testpass123")

        response = self.client.get(reverse("my_serving"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Sunday Service")
        self.assertContains(response, "You do not have any serving assignments yet.")

    def test_inactive_membership_does_not_show_on_my_serving(self):
        self.set_language("en")
        self.create_assignment()
        self.membership.is_active = False
        self.membership.save()
        self.client.login(username="regular_assign", password="testpass123")

        response = self.client.get(reverse("my_serving"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Sunday Service")
        self.assertContains(response, "You do not have any serving assignments yet.")

    def test_cancelled_assignment_does_not_appear_in_my_serving_upcoming(self):
        self.set_language("en")
        self.create_assignment(status=TeamAssignment.STATUS_CANCELLED)
        self.client.login(username="regular_assign", password="testpass123")

        response = self.client.get(reverse("my_serving"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Sunday Service")

    def test_past_assignment_appears_in_past_and_all_my_serving_views(self):
        self.set_language("en")
        past_event = ServiceEvent.objects.create(
            title="过去聚会",
            title_en="Past Service",
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
            start_datetime=timezone.now() - timezone.timedelta(days=2),
            scope_type=ServiceEvent.SCOPE_GLOBAL,
            status=ServiceEvent.STATUS_COMPLETED,
        )
        self.create_assignment(service_event=past_event)
        self.client.login(username="regular_assign", password="testpass123")

        upcoming_response = self.client.get(reverse("my_serving"))
        past_response = self.client.get(f"{reverse('my_serving')}?tab=past")
        all_response = self.client.get(f"{reverse('my_serving')}?tab=all")

        self.assertNotContains(upcoming_response, "Past Service")
        self.assertContains(past_response, "Past Service")
        self.assertContains(all_response, "Past Service")

    def test_user_can_confirm_own_assignment_from_my_serving(self):
        self.set_language("en")
        assignment = self.create_assignment()
        self.client.login(username="regular_assign", password="testpass123")

        response = self.client.post(
            reverse("confirm_team_assignment", args=[assignment.id]),
            {
                "confirmation_note": "Confirmed from My Serving.",
                "next": reverse("my_serving"),
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("my_serving"))
        assignment_member = assignment.assignment_members.get(membership=self.membership)
        self.assertIsNotNone(assignment_member.confirmed_at)
        self.assertEqual(assignment_member.confirmation_note, "Confirmed from My Serving.")

    def test_confirmed_assignment_shows_confirmed_state_on_my_serving(self):
        self.set_language("en")
        assignment = self.create_assignment()
        assignment_member = assignment.assignment_members.get(membership=self.membership)
        assignment_member.confirm("Ready.")
        self.client.login(username="regular_assign", password="testpass123")

        response = self.client.get(reverse("my_serving"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Confirmed")
        self.assertContains(response, "Confirmed At")
        self.assertNotContains(response, "Not Confirmed")

    def test_duplicate_confirmation_does_not_create_duplicate_state(self):
        self.set_language("en")
        assignment = self.create_assignment()
        self.client.login(username="regular_assign", password="testpass123")

        for note in ["First confirmation.", "Second confirmation."]:
            self.client.post(
                reverse("confirm_team_assignment", args=[assignment.id]),
                {"confirmation_note": note, "next": reverse("my_serving")},
            )

        assignment_member = assignment.assignment_members.get(membership=self.membership)
        self.assertIsNotNone(assignment_member.confirmed_at)
        self.assertEqual(assignment.assignment_members.filter(membership=self.membership).count(), 1)

    def test_home_shows_upcoming_serving_when_user_has_assignment(self):
        self.set_language("en")
        self.create_assignment()
        self.client.login(username="regular_assign", password="testpass123")

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Upcoming Serving")
        self.assertContains(response, "My Serving")

    def test_home_does_not_show_upcoming_serving_without_assignment(self):
        self.set_language("en")
        self.client.login(username="regular_assign", password="testpass123")

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Upcoming Serving")

    def test_profile_links_to_my_serving(self):
        self.set_language("en")
        self.client.login(username="regular_assign", password="testpass123")

        response = self.client.get(reverse("profile"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'href="/my-serving/"', html=False)

    def test_chinese_my_serving_page_shows_chinese_labels(self):
        self.set_language("zh")
        self.create_assignment()
        self.client.login(username="regular_assign", password="testpass123")

        response = self.client.get(reverse("my_serving"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "我的服事")
        self.assertContains(response, "即将服事")
        self.assertContains(response, "确认服事")

    def test_english_my_serving_page_shows_english_labels(self):
        self.set_language("en")
        self.create_assignment()
        self.client.login(username="regular_assign", password="testpass123")

        response = self.client.get(reverse("my_serving"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "My Serving")
        self.assertContains(response, "Upcoming Serving")
        self.assertContains(response, "Confirm Assignment")

    def test_normal_top_nav_does_not_show_my_serving(self):
        self.set_language("en")
        self.client.login(username="regular_assign", password="testpass123")

        response = self.client.get(reverse("my_serving"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'href="/my-serving/">My Serving', html=False)

    def test_no_lighting_team_model_exists(self):
        with self.assertRaises(LookupError):
            apps.get_model("ministry", "LightingTeam")


class LightingPilotImportCommandTests(TestCase):
    def setUp(self):
        self.future_date = timezone.localdate() + timezone.timedelta(days=30)
        self.linked_user = User.objects.create_user(
            username="linked_lighting",
            email="linked-lighting@example.com",
            password="testpass123",
        )
        self.regular_user = User.objects.create_user(
            username="lighting_regular",
            email="lighting-regular@example.com",
            password="testpass123",
        )
        self.manager = User.objects.create_user(
            username="lighting_manager",
            email="lighting-manager@example.com",
            password="testpass123",
        )
        ChurchRoleAssignment.objects.create(
            user=self.manager,
            role=ChurchRoleAssignment.ROLE_PASTOR,
            scope_type=ChurchRoleAssignment.SCOPE_GLOBAL,
        )

    def set_language(self, language="en"):
        session = self.client.session
        session["language"] = language
        session.save()

    def write_csv(self, content):
        temp_dir = TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        path = Path(temp_dir.name) / "lighting_pilot.csv"
        path.write_text(content, encoding="utf-8")
        return str(path)

    def csv_content(self, **overrides):
        row = {
            "event_date": self.future_date.isoformat(),
            "event_type": ServiceEvent.EVENT_SUNDAY_SERVICE,
            "event_title": "Pilot Sunday Service",
            "start_time": "10:00",
            "end_time": "11:30",
            "service_detail": "Main sanctuary service.",
            "special_event_note": "Baptism Sunday.",
            "worship_team": "Worship Team A",
            "assigned_member": "Pilot Helper",
            "member_email": "",
            "playbook_link": "https://example.com/lighting-playbook",
        }
        row.update(overrides)
        headers = [
            "event_date",
            "event_type",
            "event_title",
            "start_time",
            "end_time",
            "service_detail",
            "special_event_note",
            "worship_team",
            "assigned_member",
            "member_email",
            "playbook_link",
        ]
        return ",".join(headers) + "\n" + ",".join(row[header] for header in headers) + "\n"

    def run_import(self, csv_path, *extra_args):
        output = StringIO()
        call_command(
            "import_lighting_pilot",
            "--csv",
            csv_path,
            *extra_args,
            stdout=output,
        )
        return output.getvalue()

    def uploaded_csv(self, content=None):
        return SimpleUploadedFile(
            "lighting_pilot.csv",
            (content or self.csv_content()).encode("utf-8"),
            content_type="text/csv",
        )

    def test_dry_run_does_not_create_records(self):
        csv_path = self.write_csv(self.csv_content())

        output = self.run_import(csv_path, "--dry-run")

        self.assertIn("Dry run complete", output)
        self.assertEqual(MinistryTeam.objects.count(), 0)
        self.assertEqual(TeamMembership.objects.count(), 0)
        self.assertEqual(ServiceEvent.objects.count(), 0)
        self.assertEqual(TeamAssignment.objects.count(), 0)
        self.assertEqual(TeamAssignmentMember.objects.count(), 0)

    def test_import_creates_lighting_team(self):
        csv_path = self.write_csv(self.csv_content())

        output = self.run_import(csv_path)

        team = MinistryTeam.objects.get(name="Lighting Team")
        self.assertEqual(team.name_en, "Lighting Team")
        self.assertEqual(team.playbook_link, "https://example.com/lighting-playbook")
        self.assertIn("teams_created=1", output)

    def test_import_creates_display_name_only_membership_when_no_matching_user(self):
        csv_path = self.write_csv(self.csv_content(assigned_member="Guest Helper"))

        self.run_import(csv_path)

        membership = TeamMembership.objects.get(display_name="Guest Helper")
        self.assertIsNone(membership.user)
        self.assertEqual(membership.team.name, "Lighting Team")

    def test_import_links_membership_to_existing_user_when_email_matches(self):
        csv_path = self.write_csv(
            self.csv_content(
                assigned_member="Linked Helper",
                member_email="linked-lighting@example.com",
            )
        )

        self.run_import(csv_path)

        membership = TeamMembership.objects.get(user=self.linked_user)
        self.assertEqual(membership.email, "linked-lighting@example.com")
        self.assertEqual(membership.team.name, "Lighting Team")

    def test_import_creates_service_event(self):
        csv_path = self.write_csv(self.csv_content())

        self.run_import(csv_path)

        event = ServiceEvent.objects.get(title="Pilot Sunday Service")
        self.assertEqual(event.event_type, ServiceEvent.EVENT_SUNDAY_SERVICE)
        self.assertEqual(event.scope_type, ServiceEvent.SCOPE_GLOBAL)
        self.assertEqual(event.status, ServiceEvent.STATUS_PUBLISHED)
        self.assertIn("Main sanctuary service.", event.description)

    def test_import_creates_team_assignment(self):
        csv_path = self.write_csv(self.csv_content())

        self.run_import(csv_path)

        assignment = TeamAssignment.objects.get()
        self.assertEqual(assignment.ministry_team.name, "Lighting Team")
        self.assertIn("Special event note: Baptism Sunday.", assignment.notes)
        self.assertIn("Worship team: Worship Team A", assignment.notes)

    def test_import_creates_team_assignment_member(self):
        csv_path = self.write_csv(self.csv_content())

        self.run_import(csv_path)

        assignment_member = TeamAssignmentMember.objects.get()
        self.assertEqual(assignment_member.assignment.ministry_team.name, "Lighting Team")
        self.assertEqual(assignment_member.membership.get_display_name(), "Pilot Helper")

    def test_rerunning_import_does_not_duplicate_assignments_or_memberships(self):
        csv_path = self.write_csv(self.csv_content())

        self.run_import(csv_path)
        second_output = self.run_import(csv_path)

        self.assertEqual(MinistryTeam.objects.count(), 1)
        self.assertEqual(TeamMembership.objects.count(), 1)
        self.assertEqual(ServiceEvent.objects.count(), 1)
        self.assertEqual(TeamAssignment.objects.count(), 1)
        self.assertEqual(TeamAssignmentMember.objects.count(), 1)
        self.assertIn("assignment_members_created=0", second_output)

    def test_forbidden_sensitive_columns_are_rejected(self):
        for forbidden_column in [
            "phone_number",
            "private_notes",
            "prayer_notes",
            "zoom_password",
        ]:
            csv_path = self.write_csv(
                "event_date,event_type,event_title,assigned_member,"
                f"{forbidden_column}\n"
                f"{self.future_date.isoformat()},sunday_service,Pilot Sunday Service,"
                "Pilot Helper,secret\n"
            )

            with self.assertRaises(CommandError):
                self.run_import(csv_path, "--dry-run")

    def test_past_rows_are_skipped_by_default(self):
        past_date = timezone.localdate() - timezone.timedelta(days=1)
        csv_path = self.write_csv(self.csv_content(event_date=past_date.isoformat()))

        output = self.run_import(csv_path)

        self.assertIn("rows_skipped=1", output)
        self.assertIn("rows_errors=1", output)
        self.assertEqual(ServiceEvent.objects.count(), 0)
        self.assertEqual(TeamAssignment.objects.count(), 0)

    def test_imported_assignment_appears_in_my_serving_for_linked_user(self):
        self.set_language("en")
        csv_path = self.write_csv(
            self.csv_content(
                assigned_member="Linked Helper",
                member_email="linked-lighting@example.com",
            )
        )
        self.run_import(csv_path)
        self.client.login(username="linked_lighting", password="testpass123")

        response = self.client.get(reverse("my_serving"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Pilot Sunday Service")
        self.assertContains(response, "Lighting Team")
        self.assertContains(response, "Confirm Assignment")

    def test_no_lighting_team_model_or_route_exists_after_import_support(self):
        with self.assertRaises(LookupError):
            apps.get_model("ministry", "LightingTeam")
        with self.assertRaises(NoReverseMatch):
            reverse("lighting_team_list")

    def test_no_future_workflow_routes_are_added_by_import_support(self):
        missing_routes = [
            "availability_matrix",
            "swap_request_list",
            "team_reminder_list",
            "assignment_checklist",
            "import_history",
        ]
        for route_name in missing_routes:
            with self.assertRaises(NoReverseMatch):
                reverse(route_name)

    def test_eligible_manager_can_open_lighting_pilot_import_page(self):
        self.set_language("en")
        self.client.login(username="lighting_manager", password="testpass123")

        response = self.client.get(reverse("lighting_pilot_import"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Lighting Pilot Import")

    def test_regular_user_cannot_open_lighting_pilot_import_page(self):
        self.set_language("en")
        self.client.login(username="lighting_regular", password="testpass123")

        response = self.client.get(reverse("lighting_pilot_import"))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("ministry_team_list"))

    def test_lighting_pilot_import_ui_dry_run_creates_no_records(self):
        self.set_language("en")
        self.client.login(username="lighting_manager", password="testpass123")

        response = self.client.post(
            reverse("lighting_pilot_import"),
            {"dry_run": "1", "csv_file": self.uploaded_csv()},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No database records were created during dry run.")
        self.assertEqual(MinistryTeam.objects.count(), 0)
        self.assertEqual(ServiceEvent.objects.count(), 0)
        self.assertEqual(TeamAssignment.objects.count(), 0)

    def test_lighting_pilot_import_ui_import_creates_records(self):
        self.set_language("en")
        self.client.login(username="lighting_manager", password="testpass123")

        response = self.client.post(
            reverse("lighting_pilot_import"),
            {"import": "1", "csv_file": self.uploaded_csv()},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Import Results")
        self.assertEqual(MinistryTeam.objects.get().name, "Lighting Team")
        self.assertEqual(ServiceEvent.objects.count(), 1)
        self.assertEqual(TeamAssignment.objects.count(), 1)
        self.assertEqual(TeamAssignmentMember.objects.count(), 1)

    def test_lighting_pilot_import_ui_rejects_forbidden_sensitive_columns(self):
        self.set_language("en")
        self.client.login(username="lighting_manager", password="testpass123")
        csv_content = (
            "event_date,event_type,event_title,assigned_member,phone_number\n"
            f"{self.future_date.isoformat()},sunday_service,Pilot Sunday Service,"
            "Pilot Helper,555-0100\n"
        )

        response = self.client.post(
            reverse("lighting_pilot_import"),
            {"dry_run": "1", "csv_file": self.uploaded_csv(csv_content)},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Forbidden column")
        self.assertContains(response, "phone_number")
        self.assertEqual(MinistryTeam.objects.count(), 0)

    def test_lighting_pilot_import_ui_displays_row_errors(self):
        self.set_language("en")
        self.client.login(username="lighting_manager", password="testpass123")
        past_date = timezone.localdate() - timezone.timedelta(days=1)

        response = self.client.post(
            reverse("lighting_pilot_import"),
            {
                "dry_run": "1",
                "csv_file": self.uploaded_csv(
                    self.csv_content(event_date=past_date.isoformat())
                ),
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Row Errors")
        self.assertContains(response, "event_date is older than today")

    def test_lighting_pilot_csv_template_uses_iso_dates(self):
        template_path = Path("docs/examples/lighting_team_pilot_template.csv")

        content = template_path.read_text(encoding="utf-8")

        self.assertIn("2026-07-05", content)
        self.assertNotIn("7/5/2026", content)

    def test_chinese_lighting_pilot_import_page_shows_chinese_labels(self):
        self.set_language("zh")
        self.client.login(username="lighting_manager", password="testpass123")

        response = self.client.get(reverse("lighting_pilot_import"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "灯光组试点导入")
        self.assertContains(response, "试运行")
        self.assertContains(response, "正式导入")

    def test_english_lighting_pilot_import_page_shows_english_labels(self):
        self.set_language("en")
        self.client.login(username="lighting_manager", password="testpass123")

        response = self.client.get(reverse("lighting_pilot_import"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Lighting Pilot Import")
        self.assertContains(response, "Dry Run")
        self.assertContains(response, "Import")
