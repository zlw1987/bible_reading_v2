from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import NoReverseMatch, reverse

from accounts.models import ChurchRoleAssignment

from .models import MinistryTeam, TeamMembership


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

    def test_no_team_assignment_routes_exist_in_this_task(self):
        with self.assertRaises(NoReverseMatch):
            reverse("team_assignment_list")
