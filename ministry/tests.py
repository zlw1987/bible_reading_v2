from io import StringIO
from datetime import datetime, timezone as datetime_timezone
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

from accounts.models import (
    ChurchRoleAssignment,
    ChurchStructureUnit,
)
from events.models import ServiceEvent
from reading.templatetags.datetime_extras import member_datetime
from studies.models import BibleStudyLesson, BibleStudyMeeting, BibleStudySeries

from .models import (
    MinistryTeam,
    TeamAssignment,
    TeamAssignmentMember,
    TeamMembership,
)
from .forms import TeamAssignmentForm
from .services.assignment_coverage import (
    assignment_coverage_queryset,
    build_assignment_coverage,
    events_with_coverage_queryset,
)
from .services.copy_forward_suggestions import (
    MODE_ANCHOR,
    MODE_TEAM,
    find_copy_forward_suggestion,
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
        self.assertContains(
            detail_response,
            '<a href="https://example.com/playbook" target="_blank" rel="noopener noreferrer">',
            html=False,
        )
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
        self.coordinator_user = User.objects.create_user(
            username="assignment_coordinator",
            email="assignment-coordinator@example.com",
            password="testpass123",
        )
        self.can_lead_user = User.objects.create_user(
            username="assignment_can_lead",
            email="assignment-can-lead@example.com",
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
        self.coordinator_membership = TeamMembership.objects.create(
            team=self.team,
            user=self.coordinator_user,
            role=TeamMembership.ROLE_COORDINATOR,
        )
        self.can_lead_membership = TeamMembership.objects.create(
            team=self.team,
            user=self.can_lead_user,
            role=TeamMembership.ROLE_MEMBER,
            can_lead=True,
        )
        self.other_team_membership = TeamMembership.objects.create(
            team=self.other_team,
            display_name="Other Helper",
            role=TeamMembership.ROLE_MEMBER,
        )
        self.cm_unit = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_MINISTRY_CONTEXT,
            code="CM",
            name="中文事工",
            name_en="Chinese Ministry",
        )
        self.event = ServiceEvent.objects.create(
            title="主日崇拜",
            title_en="Sunday Service",
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
            start_datetime=timezone.now() + timezone.timedelta(days=2),            status=ServiceEvent.STATUS_PUBLISHED,
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

    def create_schedule_event(self, *, title_en, days_from_now, anchor=None, status=None):
        return ServiceEvent.objects.create(
            title=title_en,
            title_en=title_en,
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
            start_datetime=timezone.now() + timezone.timedelta(days=days_from_now),            status=status or ServiceEvent.STATUS_PUBLISHED,
            rotation_anchor_team=anchor,
        )

    def local_datetime(self, days_from_today=0, *, hour=9, minute=0):
        local_date = timezone.localdate() + timezone.timedelta(days=days_from_today)
        naive_datetime = datetime.combine(local_date, datetime.min.time()).replace(
            hour=hour,
            minute=minute,
        )
        return timezone.make_aware(
            naive_datetime,
            timezone.get_current_timezone(),
        )

    def test_copy_forward_anchor_suggestion_finds_same_anchor_prior_assignment(self):
        anchor_team = MinistryTeam.objects.create(name="敬拜 C1", name_en="Worship C1")
        source_event = self.create_schedule_event(
            title_en="Prior Sunday",
            days_from_now=1,
            anchor=anchor_team,
        )
        self.event.rotation_anchor_team = anchor_team
        self.event.save()
        self.create_assignment(
            service_event=source_event,
            members=[self.membership, self.second_membership],
        )

        suggestion = find_copy_forward_suggestion(self.event, self.team, MODE_ANCHOR)

        self.assertIsNotNone(suggestion)
        self.assertEqual(suggestion.source_assignment.service_event, source_event)
        self.assertEqual(
            {member.id for member in suggestion.source_members},
            {self.membership.id, self.second_membership.id},
        )

    def test_copy_forward_anchor_suggestion_ignores_different_anchor(self):
        target_anchor = MinistryTeam.objects.create(name="敬拜 C1", name_en="Worship C1")
        other_anchor = MinistryTeam.objects.create(name="敬拜 C2", name_en="Worship C2")
        source_event = self.create_schedule_event(
            title_en="Prior Sunday",
            days_from_now=1,
            anchor=other_anchor,
        )
        self.event.rotation_anchor_team = target_anchor
        self.event.save()
        self.create_assignment(service_event=source_event)

        suggestion = find_copy_forward_suggestion(self.event, self.team, MODE_ANCHOR)

        self.assertIsNone(suggestion)

    def test_copy_forward_team_only_fallback_works_without_anchor(self):
        source_event = self.create_schedule_event(
            title_en="Prior Sunday",
            days_from_now=1,
        )
        self.create_assignment(service_event=source_event, members=[self.second_membership])

        suggestion = find_copy_forward_suggestion(self.event, self.team, MODE_TEAM)

        self.assertIsNotNone(suggestion)
        self.assertEqual(suggestion.source_assignment.service_event, source_event)
        self.assertEqual([member.id for member in suggestion.source_members], [self.second_membership.id])

    def test_copy_forward_suggestion_does_not_use_future_assignment(self):
        future_event = self.create_schedule_event(
            title_en="Future Sunday",
            days_from_now=4,
        )
        self.create_assignment(service_event=future_event)

        suggestion = find_copy_forward_suggestion(self.event, self.team, MODE_TEAM)

        self.assertIsNone(suggestion)

    def test_copy_forward_suggestion_ignores_cancelled_or_draft_sources(self):
        draft_event = self.create_schedule_event(
            title_en="Draft Sunday",
            days_from_now=1,
            status=ServiceEvent.STATUS_DRAFT,
        )
        cancelled_event = self.create_schedule_event(
            title_en="Cancelled Sunday",
            days_from_now=1,
            status=ServiceEvent.STATUS_CANCELLED,
        )
        valid_event = self.create_schedule_event(
            title_en="Valid Sunday",
            days_from_now=1,
        )
        self.create_assignment(service_event=draft_event, members=[self.second_membership])
        self.create_assignment(service_event=cancelled_event, members=[self.second_membership])
        self.create_assignment(
            service_event=valid_event,
            status=TeamAssignment.STATUS_CANCELLED,
            members=[self.second_membership],
        )

        suggestion = find_copy_forward_suggestion(self.event, self.team, MODE_TEAM)

        self.assertIsNone(suggestion)

    def test_copy_forward_suggestion_copies_active_members_only(self):
        source_event = self.create_schedule_event(
            title_en="Prior Sunday",
            days_from_now=1,
        )
        inactive_membership = TeamMembership.objects.create(
            team=self.team,
            display_name="Inactive Helper",
        )
        self.create_assignment(
            service_event=source_event,
            members=[self.membership, inactive_membership],
        )
        inactive_membership.is_active = False
        inactive_membership.save()

        suggestion = find_copy_forward_suggestion(self.event, self.team, MODE_TEAM)

        self.assertIsNotNone(suggestion)
        self.assertEqual([member.id for member in suggestion.source_members], [self.membership.id])

    def test_copy_forward_anchor_suggestion_skips_newer_empty_source(self):
        anchor_team = MinistryTeam.objects.create(name="敬拜 C1", name_en="Worship C1")
        older_event = self.create_schedule_event(
            title_en="Older Sunday",
            days_from_now=0,
            anchor=anchor_team,
        )
        newer_empty_event = self.create_schedule_event(
            title_en="Newer Empty Sunday",
            days_from_now=1,
            anchor=anchor_team,
        )
        self.event.rotation_anchor_team = anchor_team
        self.event.save()
        older_assignment = self.create_assignment(
            service_event=older_event,
            members=[self.second_membership],
        )
        TeamAssignment.objects.create(
            service_event=newer_empty_event,
            ministry_team=self.team,
            status=TeamAssignment.STATUS_SCHEDULED,
        )

        suggestion = find_copy_forward_suggestion(self.event, self.team, MODE_ANCHOR)

        self.assertIsNotNone(suggestion)
        self.assertEqual(suggestion.source_assignment, older_assignment)
        self.assertEqual([member.id for member in suggestion.source_members], [self.second_membership.id])

    def test_copy_forward_team_suggestion_skips_newer_empty_source(self):
        older_event = self.create_schedule_event(
            title_en="Older Sunday",
            days_from_now=0,
        )
        newer_empty_event = self.create_schedule_event(
            title_en="Newer Empty Sunday",
            days_from_now=1,
        )
        older_assignment = self.create_assignment(
            service_event=older_event,
            members=[self.second_membership],
        )
        TeamAssignment.objects.create(
            service_event=newer_empty_event,
            ministry_team=self.team,
            status=TeamAssignment.STATUS_SCHEDULED,
        )

        suggestion = find_copy_forward_suggestion(self.event, self.team, MODE_TEAM)

        self.assertIsNotNone(suggestion)
        self.assertEqual(suggestion.source_assignment, older_assignment)
        self.assertEqual([member.id for member in suggestion.source_members], [self.second_membership.id])

    def test_copy_forward_suggestion_returns_none_when_all_sources_empty(self):
        older_empty_event = self.create_schedule_event(
            title_en="Older Empty Sunday",
            days_from_now=0,
        )
        newer_empty_event = self.create_schedule_event(
            title_en="Newer Empty Sunday",
            days_from_now=1,
        )
        TeamAssignment.objects.create(
            service_event=older_empty_event,
            ministry_team=self.team,
            status=TeamAssignment.STATUS_SCHEDULED,
        )
        TeamAssignment.objects.create(
            service_event=newer_empty_event,
            ministry_team=self.team,
            status=TeamAssignment.STATUS_SCHEDULED,
        )

        suggestion = find_copy_forward_suggestion(self.event, self.team, MODE_TEAM)

        self.assertIsNone(suggestion)

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

    def test_assignment_list_shows_service_event_host_language_label_without_filtering(self):
        self.set_language("en")
        self.event.host_language_unit = self.cm_unit
        self.event.save()
        self.create_assignment(members=[self.second_membership])
        self.client.login(username="assignment_lead", password="testpass123")

        response = self.client.get(reverse("team_assignment_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "CM - Chinese Ministry")
        self.assertContains(response, "Lighting Team")

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

    def test_create_blocks_duplicate_scheduled_assignment_for_same_event_team(self):
        self.set_language("en")
        self.create_assignment(status=TeamAssignment.STATUS_SCHEDULED)
        self.client.login(username="assignment_pastor", password="testpass123")

        response = self.client.post(
            reverse("create_team_assignment"),
            self.assignment_post_data(notes="Attempted duplicate."),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "An active assignment already exists")
        self.assertEqual(
            TeamAssignment.objects.filter(
                service_event=self.event,
                ministry_team=self.team,
            ).count(),
            1,
        )

    def test_create_blocks_duplicate_non_cancelled_assignment_for_each_active_status(self):
        self.set_language("en")
        self.client.login(username="assignment_pastor", password="testpass123")
        for status in (
            TeamAssignment.STATUS_PREPARED,
            TeamAssignment.STATUS_CONFIRMED,
            TeamAssignment.STATUS_COMPLETED,
        ):
            with self.subTest(status=status):
                event = self.create_schedule_event(
                    title_en=f"Event {status}",
                    days_from_now=3,
                )
                self.create_assignment(service_event=event, status=status)

                response = self.client.post(
                    reverse("create_team_assignment"),
                    self.assignment_post_data(
                        service_event=event.id,
                        notes=f"Duplicate against {status}.",
                    ),
                )

                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "An active assignment already exists")
                self.assertEqual(
                    TeamAssignment.objects.filter(
                        service_event=event,
                        ministry_team=self.team,
                    ).count(),
                    1,
                )

    def test_create_allows_active_assignment_when_only_existing_is_cancelled(self):
        self.set_language("en")
        self.create_assignment(status=TeamAssignment.STATUS_CANCELLED)
        self.client.login(username="assignment_pastor", password="testpass123")

        response = self.client.post(
            reverse("create_team_assignment"),
            self.assignment_post_data(notes="New active alongside cancelled."),
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            TeamAssignment.objects.filter(
                service_event=self.event,
                ministry_team=self.team,
            ).count(),
            2,
        )
        self.assertEqual(
            TeamAssignment.objects.filter(
                service_event=self.event,
                ministry_team=self.team,
            )
            .exclude(status=TeamAssignment.STATUS_CANCELLED)
            .count(),
            1,
        )

    def test_edit_same_assignment_is_allowed(self):
        self.set_language("en")
        assignment = self.create_assignment()
        self.client.login(username="assignment_pastor", password="testpass123")

        response = self.client.post(
            reverse("edit_team_assignment", args=[assignment.id]),
            self.assignment_post_data(notes="Same assignment edited."),
        )

        self.assertEqual(response.status_code, 302)
        assignment.refresh_from_db()
        self.assertEqual(assignment.notes, "Same assignment edited.")
        self.assertEqual(
            TeamAssignment.objects.filter(
                service_event=self.event,
                ministry_team=self.team,
            ).count(),
            1,
        )

    def test_edit_to_existing_event_team_pair_is_blocked(self):
        self.set_language("en")
        other_event = self.create_schedule_event(
            title_en="Other Sunday",
            days_from_now=4,
        )
        self.create_assignment(service_event=other_event)
        assignment = self.create_assignment(notes="Editable assignment.")
        self.client.login(username="assignment_pastor", password="testpass123")

        response = self.client.post(
            reverse("edit_team_assignment", args=[assignment.id]),
            self.assignment_post_data(
                service_event=other_event.id,
                notes="Moved into a conflicting pair.",
            ),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "An active assignment already exists")
        assignment.refresh_from_db()
        self.assertEqual(assignment.service_event, self.event)
        self.assertEqual(assignment.notes, "Editable assignment.")

    def test_edit_changing_only_notes_status_members_still_works(self):
        self.set_language("en")
        assignment = self.create_assignment()
        self.client.login(username="assignment_pastor", password="testpass123")

        response = self.client.post(
            reverse("edit_team_assignment", args=[assignment.id]),
            self.assignment_post_data(
                status=TeamAssignment.STATUS_CONFIRMED,
                assigned_members=[self.second_membership.id],
                notes="Updated notes, status, and members.",
            ),
        )

        self.assertEqual(response.status_code, 302)
        assignment.refresh_from_db()
        self.assertEqual(assignment.status, TeamAssignment.STATUS_CONFIRMED)
        self.assertEqual(assignment.notes, "Updated notes, status, and members.")
        self.assertEqual(
            list(assignment.assigned_members.values_list("id", flat=True)),
            [self.second_membership.id],
        )

    def test_assignment_form_service_event_choices_include_date_time(self):
        self.set_language("en")
        later_event = ServiceEvent.objects.create(
            title="ä¸»æ—¥å´‡æ‹œ",
            title_en="Sunday Service",
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
            start_datetime=self.event.start_datetime + timezone.timedelta(days=7),            status=ServiceEvent.STATUS_PUBLISHED,
        )
        self.client.login(username="assignment_pastor", password="testpass123")

        response = self.client.get(reverse("create_team_assignment"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            f"Sunday Service - {timezone.localtime(self.event.start_datetime).strftime('%Y-%m-%d %H:%M')}",
        )
        self.assertContains(
            response,
            f"Sunday Service - {timezone.localtime(later_event.start_datetime).strftime('%Y-%m-%d %H:%M')}",
        )

    def test_assignment_form_filters_members_to_selected_team(self):
        self.set_language("en")
        self.client.login(username="assignment_pastor", password="testpass123")

        response = self.client.get(
            reverse("create_team_assignment"),
            {"ministry_team": self.team.id},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "regular_assign")
        self.assertContains(response, "other_assign")
        self.assertNotContains(response, "Other Helper")

    def test_assignment_create_form_preserves_safe_fields_when_team_filter_changes(self):
        self.set_language("en")
        self.client.login(username="assignment_pastor", password="testpass123")

        response = self.client.get(
            reverse("create_team_assignment"),
            {
                "ministry_team": self.other_team.id,
                "service_event": self.event.id,
                "status": TeamAssignment.STATUS_PREPARED,
                "notes": "Keep this service event selected.",
                "assigned_members": self.membership.id,
            },
        )

        form = response.context["form"]
        member_ids = set(form.fields["assigned_members"].queryset.values_list("id", flat=True))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(str(form["service_event"].value()), str(self.event.id))
        self.assertEqual(form["status"].value(), TeamAssignment.STATUS_PREPARED)
        self.assertEqual(form["notes"].value(), "Keep this service event selected.")
        self.assertIn(self.other_team_membership.id, member_ids)
        self.assertNotIn(self.membership.id, member_ids)
        self.assertNotEqual(form["assigned_members"].value(), [str(self.membership.id)])

    def test_assignment_form_hides_members_until_team_is_selected(self):
        self.set_language("en")
        self.client.login(username="assignment_pastor", password="testpass123")

        response = self.client.get(reverse("create_team_assignment"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "regular_assign")
        self.assertNotContains(response, "Other Helper")

    def test_assignment_edit_form_preserves_service_event_when_team_filter_changes(self):
        self.set_language("en")
        assignment = self.create_assignment()
        self.client.login(username="assignment_pastor", password="testpass123")

        response = self.client.get(
            reverse("edit_team_assignment", args=[assignment.id]),
            {
                "ministry_team": self.other_team.id,
                "service_event": assignment.service_event_id,
                "status": TeamAssignment.STATUS_CONFIRMED,
                "notes": "Edited note should stay visible.",
                "assigned_members": self.membership.id,
            },
        )

        form = response.context["form"]
        member_ids = set(form.fields["assigned_members"].queryset.values_list("id", flat=True))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(str(form["service_event"].value()), str(assignment.service_event_id))
        self.assertEqual(form["status"].value(), TeamAssignment.STATUS_CONFIRMED)
        self.assertEqual(form["notes"].value(), "Edited note should stay visible.")
        self.assertIn(self.other_team_membership.id, member_ids)
        self.assertNotIn(self.membership.id, member_ids)

    def test_assignment_form_rejects_member_from_different_team(self):
        form = TeamAssignmentForm(
            data=self.assignment_post_data(
                assigned_members=[self.other_team_membership.id],
            ),
            language="en",
            manageable_teams=MinistryTeam.objects.all(),
        )

        self.assertFalse(form.is_valid())
        self.assertIn("assigned_members", form.errors)
        self.assertIn(
            "Assigned members must be active members of the selected team.",
            form.errors["assigned_members"],
        )

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
        self.event.start_datetime = datetime(
            2026, 6, 12, 19, 30, tzinfo=datetime_timezone.utc
        )
        self.event.save()
        assignment = self.create_assignment()
        self.client.login(username="regular_assign", password="testpass123")

        response = self.client.get(reverse("team_assignment_detail", args=[assignment.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Team Assignment")
        self.assertContains(response, "Fri, Jun 12, 7:30 PM")
        self.assertNotContains(response, "June 12, 2026")

    def test_assignment_detail_shows_back_to_my_serving_for_member(self):
        self.set_language("en")
        assignment = self.create_assignment()
        self.client.login(username="regular_assign", password="testpass123")

        response = self.client.get(reverse("team_assignment_detail", args=[assignment.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Back to My Serving")
        self.assertContains(response, reverse("my_serving"))
        self.assertNotContains(response, "Back to Assignments")

    def test_assignment_detail_member_back_link_uses_chinese_label(self):
        self.set_language("zh")
        assignment = self.create_assignment()
        self.client.login(username="regular_assign", password="testpass123")

        response = self.client.get(reverse("team_assignment_detail", args=[assignment.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "返回我的服事")
        self.assertNotContains(response, "返回排班")

    def test_assignment_detail_shows_back_to_assignments_for_manager(self):
        self.set_language("en")
        assignment = self.create_assignment()
        self.client.login(username="assignment_pastor", password="testpass123")

        response = self.client.get(reverse("team_assignment_detail", args=[assignment.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Back to My Serving")
        self.assertContains(response, "Back to Assignments")
        self.assertContains(response, reverse("team_assignment_list"))

    def test_assignment_detail_playbook_link_opens_in_new_tab(self):
        self.set_language("en")
        assignment = self.create_assignment()
        self.client.login(username="regular_assign", password="testpass123")

        response = self.client.get(reverse("team_assignment_detail", args=[assignment.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            '<a href="https://example.com/playbook" target="_blank" rel="noopener noreferrer">',
        )

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

    def test_assigned_member_can_confirm_prepared_assignment(self):
        self.set_language("en")
        assignment = self.create_assignment(status=TeamAssignment.STATUS_PREPARED)
        self.client.login(username="regular_assign", password="testpass123")

        response = self.client.post(
            reverse("confirm_team_assignment", args=[assignment.id]),
            {"confirmation_note": "Prepared and ready."},
        )

        self.assertEqual(response.status_code, 302)
        assignment.refresh_from_db()
        assignment_member = assignment.assignment_members.get(membership=self.membership)
        self.assertIsNotNone(assignment_member.confirmed_at)
        self.assertEqual(assignment.status, TeamAssignment.STATUS_CONFIRMED)

    def test_assigned_member_cannot_confirm_cancelled_assignment(self):
        self.set_language("en")
        assignment = self.create_assignment(status=TeamAssignment.STATUS_CANCELLED)
        self.client.login(username="regular_assign", password="testpass123")

        response = self.client.post(reverse("confirm_team_assignment", args=[assignment.id]))

        self.assertEqual(response.status_code, 302)
        assignment.refresh_from_db()
        assignment_member = assignment.assignment_members.get(membership=self.membership)
        self.assertEqual(assignment.status, TeamAssignment.STATUS_CANCELLED)
        self.assertIsNone(assignment_member.confirmed_at)

    def test_assigned_member_cannot_confirm_completed_assignment(self):
        self.set_language("en")
        assignment = self.create_assignment(status=TeamAssignment.STATUS_COMPLETED)
        self.client.login(username="regular_assign", password="testpass123")

        response = self.client.post(reverse("confirm_team_assignment", args=[assignment.id]))

        self.assertEqual(response.status_code, 302)
        assignment.refresh_from_db()
        assignment_member = assignment.assignment_members.get(membership=self.membership)
        self.assertEqual(assignment.status, TeamAssignment.STATUS_COMPLETED)
        self.assertIsNone(assignment_member.confirmed_at)

    def test_cancelled_assignment_detail_does_not_show_confirmation_form(self):
        self.set_language("en")
        assignment = self.create_assignment(status=TeamAssignment.STATUS_CANCELLED)
        self.client.login(username="regular_assign", password="testpass123")

        response = self.client.get(reverse("team_assignment_detail", args=[assignment.id]))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Confirm Assignment")

    def test_completed_assignment_detail_does_not_show_confirmation_form(self):
        self.set_language("en")
        assignment = self.create_assignment(status=TeamAssignment.STATUS_COMPLETED)
        self.client.login(username="regular_assign", password="testpass123")

        response = self.client.get(reverse("team_assignment_detail", args=[assignment.id]))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Confirm Assignment")

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
        # Use an upcoming datetime relative to now so the My Serving "upcoming"
        # filter includes it (a hardcoded calendar date drifts into the past).
        # Assert the abbreviated, member-formatted rendering, which never shows
        # the year unlike Django's default verbose datetime format.
        upcoming = (timezone.now() + timezone.timedelta(days=5)).replace(
            hour=19, minute=30, second=0, microsecond=0
        )
        self.event.start_datetime = upcoming
        self.event.save()
        self.create_assignment()
        self.client.login(username="regular_assign", password="testpass123")

        response = self.client.get(reverse("my_serving"))

        local = timezone.localtime(upcoming)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "My Serving")
        self.assertContains(response, "Sunday Service")
        self.assertContains(response, member_datetime(upcoming, "en"))
        self.assertNotContains(response, f"{local:%B} {local.day}, {local.year}")
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
        self.assertContains(
            response,
            "You do not have any upcoming serving assignments right now.",
        )

    def test_inactive_membership_does_not_show_on_my_serving(self):
        self.set_language("en")
        self.create_assignment()
        self.membership.is_active = False
        self.membership.save()
        self.client.login(username="regular_assign", password="testpass123")

        response = self.client.get(reverse("my_serving"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Sunday Service")
        self.assertContains(
            response,
            "You do not have any upcoming serving assignments right now.",
        )

    def test_cancelled_assignment_does_not_appear_in_my_serving_upcoming(self):
        self.set_language("en")
        self.create_assignment(status=TeamAssignment.STATUS_CANCELLED)
        self.client.login(username="regular_assign", password="testpass123")

        response = self.client.get(reverse("my_serving"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Sunday Service")

    def test_cancelled_event_assignment_does_not_appear_in_my_serving_upcoming(self):
        self.set_language("en")
        cancelled_event = self.create_schedule_event(
            title_en="Cancelled Service",
            days_from_now=2,
            status=ServiceEvent.STATUS_CANCELLED,
        )
        self.create_assignment(service_event=cancelled_event)
        self.client.login(username="regular_assign", password="testpass123")

        response = self.client.get(reverse("my_serving"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Cancelled Service")

    def test_draft_event_assignment_does_not_appear_in_my_serving_upcoming(self):
        self.set_language("en")
        draft_event = self.create_schedule_event(
            title_en="Draft Service",
            days_from_now=2,
            status=ServiceEvent.STATUS_DRAFT,
        )
        self.create_assignment(service_event=draft_event)
        self.client.login(username="regular_assign", password="testpass123")

        response = self.client.get(reverse("my_serving"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Draft Service")

    def test_past_assignment_appears_in_past_and_all_my_serving_views(self):
        self.set_language("en")
        past_event = ServiceEvent.objects.create(
            title="过去聚会",
            title_en="Past Service",
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
            start_datetime=timezone.now() - timezone.timedelta(days=2),            status=ServiceEvent.STATUS_COMPLETED,
        )
        self.create_assignment(service_event=past_event)
        self.client.login(username="regular_assign", password="testpass123")

        upcoming_response = self.client.get(reverse("my_serving"))
        past_response = self.client.get(f"{reverse('my_serving')}?tab=past")
        all_response = self.client.get(f"{reverse('my_serving')}?tab=all")

        self.assertNotContains(upcoming_response, "Past Service")
        self.assertContains(past_response, "Past Service")
        self.assertContains(all_response, "Past Service")

    def test_my_serving_upcoming_includes_today_assignment_after_start(self):
        self.set_language("en")
        current_event = ServiceEvent.objects.create(
            title="Current Today Service",
            title_en="Current Today Service",
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
            start_datetime=self.local_datetime(0, hour=0),
            status=ServiceEvent.STATUS_PUBLISHED,
        )
        assignment = self.create_assignment(service_event=current_event)
        member = assignment.assignment_members.get(membership=self.membership)
        member.confirm()
        assignment.status = TeamAssignment.STATUS_CONFIRMED
        assignment.save()
        self.client.login(username="regular_assign", password="testpass123")

        upcoming_response = self.client.get(reverse("my_serving"))
        past_response = self.client.get(f"{reverse('my_serving')}?tab=past")

        self.assertEqual(upcoming_response.status_code, 200)
        self.assertContains(upcoming_response, "Today Serving")
        self.assertContains(upcoming_response, "Current Today Service")
        self.assertNotContains(upcoming_response, "Past / History")
        self.assertNotContains(past_response, "Current Today Service")

    def test_my_serving_past_includes_assignment_effectively_ended_yesterday(self):
        self.set_language("en")
        ended_event = ServiceEvent.objects.create(
            title="Ended Yesterday Service",
            title_en="Ended Yesterday Service",
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
            start_datetime=self.local_datetime(-1, hour=9),
            status=ServiceEvent.STATUS_PUBLISHED,
        )
        assignment = self.create_assignment(service_event=ended_event)
        member = assignment.assignment_members.get(membership=self.membership)
        member.confirm()
        assignment.status = TeamAssignment.STATUS_CONFIRMED
        assignment.save()
        self.client.login(username="regular_assign", password="testpass123")

        response = self.client.get(f"{reverse('my_serving')}?tab=past")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Past / History")
        self.assertContains(response, "Ended Yesterday Service")

    def test_my_serving_upcoming_uses_explicit_event_end_datetime(self):
        self.set_language("en")
        multi_day_event = ServiceEvent.objects.create(
            title="Multi-day Current Service",
            title_en="Multi-day Current Service",
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
            start_datetime=self.local_datetime(-1, hour=9),
            end_datetime=timezone.now() + timezone.timedelta(hours=1),
            status=ServiceEvent.STATUS_PUBLISHED,
        )
        assignment = self.create_assignment(service_event=multi_day_event)
        member = assignment.assignment_members.get(membership=self.membership)
        member.confirm()
        assignment.status = TeamAssignment.STATUS_CONFIRMED
        assignment.save()
        self.client.login(username="regular_assign", password="testpass123")

        upcoming_response = self.client.get(reverse("my_serving"))
        past_response = self.client.get(f"{reverse('my_serving')}?tab=past")

        self.assertContains(upcoming_response, "Today Serving")
        self.assertContains(upcoming_response, "Multi-day Current Service")
        self.assertNotContains(past_response, "Multi-day Current Service")

    def test_my_serving_sections_bucket_tomorrow_and_later_assignments(self):
        self.set_language("en")
        tomorrow_event = ServiceEvent.objects.create(
            title="Tomorrow Serving",
            title_en="Tomorrow Serving",
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
            start_datetime=self.local_datetime(1, hour=9),
            status=ServiceEvent.STATUS_PUBLISHED,
        )
        later_event = ServiceEvent.objects.create(
            title="Later Serving Window",
            title_en="Later Serving Window",
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
            start_datetime=self.local_datetime(9, hour=9),
            status=ServiceEvent.STATUS_PUBLISHED,
        )
        for event in [tomorrow_event, later_event]:
            assignment = self.create_assignment(service_event=event)
            member = assignment.assignment_members.get(membership=self.membership)
            member.confirm()
            assignment.status = TeamAssignment.STATUS_CONFIRMED
            assignment.save()
        self.client.login(username="regular_assign", password="testpass123")

        response = self.client.get(reverse("my_serving"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "This Week Serving")
        self.assertContains(response, "Tomorrow Serving")
        self.assertContains(response, "Later")
        self.assertContains(response, "Later Serving Window")

    def test_pending_current_assignment_stays_in_needs_attention(self):
        self.set_language("en")
        current_event = ServiceEvent.objects.create(
            title="Pending Current Service",
            title_en="Pending Current Service",
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
            start_datetime=self.local_datetime(0, hour=0),
            status=ServiceEvent.STATUS_PUBLISHED,
        )
        self.create_assignment(service_event=current_event)
        self.client.login(username="regular_assign", password="testpass123")

        response = self.client.get(reverse("my_serving"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Needs Attention")
        self.assertContains(response, "Pending Current Service")
        self.assertContains(response, "Confirm Assignment")

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
        self.assertIsNotNone(assignment_member.confirmed_at)
        confirmed_at_display = member_datetime(assignment_member.confirmed_at, "en")
        event_start_display = member_datetime(assignment.service_event.start_datetime, "en")
        content = response.content.decode()
        confirmed_at_chunk = content[content.index("Confirmed At") : content.index("Confirmed At") + 250]
        self.assertIn(confirmed_at_display, confirmed_at_chunk)
        self.assertNotIn(event_start_display, confirmed_at_chunk)
        self.assertNotContains(response, "Not Confirmed")

    def test_completed_assignment_does_not_show_confirmation_form_on_my_serving_all(self):
        self.set_language("en")
        self.create_assignment(status=TeamAssignment.STATUS_COMPLETED)
        self.client.login(username="regular_assign", password="testpass123")

        response = self.client.get(f"{reverse('my_serving')}?tab=all")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sunday Service")
        self.assertNotContains(response, "Confirm Assignment")

    def test_duplicate_confirmation_does_not_create_duplicate_state(self):
        self.set_language("en")
        assignment = self.create_assignment()
        self.client.login(username="regular_assign", password="testpass123")

        self.client.post(
            reverse("confirm_team_assignment", args=[assignment.id]),
            {"confirmation_note": "First confirmation.", "next": reverse("my_serving")},
        )
        assignment_member = assignment.assignment_members.get(membership=self.membership)
        first_confirmed_at = assignment_member.confirmed_at

        self.client.post(
            reverse("confirm_team_assignment", args=[assignment.id]),
            {"confirmation_note": "Second confirmation.", "next": reverse("my_serving")},
        )

        assignment_member = assignment.assignment_members.get(membership=self.membership)
        self.assertIsNotNone(assignment_member.confirmed_at)
        self.assertEqual(assignment_member.confirmed_at, first_confirmed_at)
        self.assertEqual(assignment.assignment_members.filter(membership=self.membership).count(), 1)

    def test_home_shows_pending_serving_summary_when_user_has_assignment(self):
        self.set_language("en")
        self.create_assignment()
        self.client.login(username="regular_assign", password="testpass123")

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "My Serving")
        self.assertContains(response, "You have 1 serving assignment waiting for confirmation.")
        self.assertContains(response, "Pending confirmation")
        self.assertContains(response, "Sunday Service")
        self.assertContains(response, "Lighting Team")
        self.assertContains(response, reverse("my_serving"))
        self.assertNotContains(response, "Edit Assignment")
        self.assertNotContains(response, "Cancel Assignment")
        self.assertNotContains(response, "Operational note.")

    def test_home_does_not_show_upcoming_serving_without_assignment(self):
        self.set_language("en")
        self.client.login(username="regular_assign", password="testpass123")

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "serving assignment waiting for confirmation")
        self.assertNotContains(response, "Upcoming Serving")

    def test_home_shows_pending_count_for_multiple_assignments(self):
        self.set_language("en")
        self.create_assignment()
        later_event = ServiceEvent.objects.create(
            title="Midweek Service",
            title_en="Midweek Service",
            event_type=ServiceEvent.EVENT_OTHER,
            start_datetime=timezone.now() + timezone.timedelta(days=9),            status=ServiceEvent.STATUS_PUBLISHED,
        )
        self.create_assignment(service_event=later_event)
        self.client.login(username="regular_assign", password="testpass123")

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "You have 2 serving assignments waiting for confirmation.")
        self.assertContains(response, "Sunday Service")
        self.assertNotContains(response, "Midweek Service")

    def test_home_does_not_show_unrelated_user_assignment(self):
        self.set_language("en")
        self.create_assignment(members=[self.second_membership])
        self.client.login(username="regular_assign", password="testpass123")

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "serving assignment waiting for confirmation")
        self.assertNotContains(response, "Sunday Service")

    def test_home_shows_near_term_confirmed_assignment_when_no_pending(self):
        self.set_language("en")
        assignment = self.create_assignment()
        assignment_member = assignment.assignment_members.get(membership=self.membership)
        assignment_member.confirm("Ready.")
        assignment.status = TeamAssignment.STATUS_CONFIRMED
        assignment.save()
        self.client.login(username="regular_assign", password="testpass123")

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "You have an upcoming serving assignment.")
        self.assertContains(response, "Confirmed")
        self.assertContains(response, "Sunday Service")
        self.assertContains(response, reverse("my_serving"))
        self.assertNotContains(response, "Ready.")

    def test_home_hides_confirmed_assignment_outside_near_term_window(self):
        self.set_language("en")
        far_event = ServiceEvent.objects.create(
            title="Future Service",
            title_en="Future Service",
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
            start_datetime=timezone.now() + timezone.timedelta(days=45),            status=ServiceEvent.STATUS_PUBLISHED,
        )
        assignment = self.create_assignment(service_event=far_event)
        assignment_member = assignment.assignment_members.get(membership=self.membership)
        assignment_member.confirm()
        assignment.status = TeamAssignment.STATUS_CONFIRMED
        assignment.save()
        self.client.login(username="regular_assign", password="testpass123")

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Future Service")
        self.assertNotContains(response, "You have an upcoming serving assignment.")

    def test_chinese_home_serving_summary_uses_chinese_labels(self):
        self.set_language("zh")
        self.create_assignment()
        self.client.login(username="regular_assign", password="testpass123")

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "我的服事")
        self.assertContains(response, "你有 1 个服事安排等待确认。")
        self.assertContains(response, "等待确认")
        self.assertContains(response, "主日崇拜")
        self.assertContains(response, "去确认")

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
        self.assertContains(response, "查看你的服事安排和确认状态。")
        self.assertContains(response, "需要你留意")
        self.assertContains(response, "确认服事")

    def test_english_my_serving_page_shows_english_labels(self):
        self.set_language("en")
        self.create_assignment()
        self.client.login(username="regular_assign", password="testpass123")

        response = self.client.get(reverse("my_serving"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "My Serving")
        self.assertContains(
            response,
            "Your upcoming serving assignments and confirmation status.",
        )
        self.assertContains(response, "Needs Attention")
        self.assertContains(response, "Confirm Assignment")

    def test_pending_assignment_shows_needs_confirmation_section_and_action(self):
        self.set_language("en")
        self.create_assignment()
        self.client.login(username="regular_assign", password="testpass123")

        response = self.client.get(reverse("my_serving"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Needs Attention")
        self.assertContains(response, "Needs confirmation")
        self.assertContains(response, "Confirm Assignment")
        self.assertContains(response, "View details")

    def test_confirmed_upcoming_assignment_shows_under_upcoming_not_pending(self):
        self.set_language("en")
        assignment = self.create_assignment()
        assignment_member = assignment.assignment_members.get(membership=self.membership)
        assignment_member.confirm("Ready.")
        assignment.status = TeamAssignment.STATUS_CONFIRMED
        assignment.save()
        self.client.login(username="regular_assign", password="testpass123")

        response = self.client.get(reverse("my_serving"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "This Week Serving")
        self.assertContains(response, "Confirmed")
        self.assertNotContains(response, "Needs Attention")
        self.assertNotContains(response, "Confirm Assignment")

    def test_my_serving_orders_agenda_sections(self):
        self.set_language("en")
        today_event = self.create_schedule_event(
            title_en="Today Serving",
            days_from_now=0,
        )
        week_event = self.create_schedule_event(
            title_en="This Week Serving",
            days_from_now=2,
        )
        later_event = self.create_schedule_event(
            title_en="Later Serving",
            days_from_now=9,
        )
        past_event = ServiceEvent.objects.create(
            title="Past Serving",
            title_en="Past Serving",
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
            start_datetime=timezone.now() - timezone.timedelta(days=2),
            status=ServiceEvent.STATUS_COMPLETED,
        )
        for event in [today_event, week_event, later_event, past_event]:
            assignment = self.create_assignment(service_event=event)
            member = assignment.assignment_members.get(membership=self.membership)
            member.confirm()
            assignment.status = TeamAssignment.STATUS_CONFIRMED
            assignment.save()

        self.client.login(username="regular_assign", password="testpass123")

        response = self.client.get(f"{reverse('my_serving')}?tab=all")
        content = response.content.decode()

        self.assertEqual(response.status_code, 200)
        for heading in [
            "Today Serving",
            "This Week Serving",
            "Later",
            "Past / History",
        ]:
            self.assertContains(response, heading)
        self.assertLess(content.index("Today Serving"), content.index("This Week Serving"))
        self.assertLess(content.index("This Week Serving"), content.index("Later"))
        self.assertLess(content.index("Later"), content.index("Past / History"))

    def test_empty_my_serving_shows_friendly_empty_state_en(self):
        self.set_language("en")
        self.client.login(username="regular_assign", password="testpass123")

        response = self.client.get(reverse("my_serving"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "You do not have any upcoming serving assignments right now.",
        )

    def test_empty_my_serving_shows_friendly_empty_state_zh(self):
        self.set_language("zh")
        self.client.login(username="regular_assign", password="testpass123")

        response = self.client.get(reverse("my_serving"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "你目前还没有即将到来的服事安排。")

    def test_normal_top_nav_shows_my_serving(self):
        self.set_language("en")
        self.client.login(username="regular_assign", password="testpass123")

        response = self.client.get(reverse("my_serving"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'href="/my-serving/">', html=False)
        self.assertContains(response, "My Serving")

    def test_my_serving_shows_manage_section_for_team_lead(self):
        self.set_language("en")
        self.client.login(username="assignment_lead", password="testpass123")

        response = self.client.get(reverse("my_serving"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Teams I manage")
        self.assertContains(response, "Lighting Team")
        self.assertContains(response, reverse("ministry_team_detail", args=[self.team.id]))
        self.assertContains(response, reverse("team_schedule", args=[self.team.id]))
        self.assertNotContains(response, "Sound Team")

    def test_my_serving_shows_manage_section_for_team_coordinator(self):
        self.set_language("en")
        self.client.login(username="assignment_coordinator", password="testpass123")

        response = self.client.get(reverse("my_serving"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Teams I manage")
        self.assertContains(response, "Lighting Team")
        self.assertContains(response, reverse("team_schedule", args=[self.team.id]))

    def test_my_serving_shows_manage_section_for_global_assignment_manager(self):
        self.set_language("en")
        self.client.login(username="assignment_pastor", password="testpass123")

        response = self.client.get(reverse("my_serving"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Teams I manage")
        self.assertContains(response, "Lighting Team")
        self.assertContains(response, "Sound Team")
        self.assertContains(response, reverse("team_schedule", args=[self.team.id]))
        self.assertContains(response, reverse("team_schedule", args=[self.other_team.id]))

    def test_my_serving_hides_manage_section_for_ordinary_member(self):
        self.set_language("en")
        self.client.login(username="regular_assign", password="testpass123")

        response = self.client.get(reverse("my_serving"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Teams I manage")
        self.assertNotContains(response, reverse("team_schedule", args=[self.team.id]))

    def test_my_serving_hides_manage_section_for_can_lead_only_member(self):
        self.set_language("en")
        self.client.login(username="assignment_can_lead", password="testpass123")

        response = self.client.get(reverse("my_serving"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Teams I manage")
        self.assertNotContains(response, reverse("team_schedule", args=[self.team.id]))

    def test_no_lighting_team_model_exists(self):
        with self.assertRaises(LookupError):
            apps.get_model("ministry", "LightingTeam")

    def test_assignment_list_shows_new_filter_tabs(self):
        self.set_language("en")
        self.client.login(username="assignment_pastor", password="testpass123")

        response = self.client.get(reverse("team_assignment_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Upcoming")
        self.assertContains(response, "Needs Confirmation")
        self.assertContains(response, "Past")
        self.assertContains(response, "Cancelled")
        self.assertNotContains(response, ">Active<", html=False)

    def test_chinese_assignment_list_shows_new_filter_tabs(self):
        self.set_language("zh")
        self.client.login(username="assignment_pastor", password="testpass123")

        response = self.client.get(reverse("team_assignment_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "即将开始")
        self.assertContains(response, "待确认")
        self.assertContains(response, "过去")
        self.assertContains(response, "已取消")
        self.assertNotContains(response, "进行中")

    def test_future_assignment_appears_in_upcoming_tab(self):
        self.set_language("en")
        self.create_assignment()
        self.client.login(username="assignment_pastor", password="testpass123")

        response = self.client.get(reverse("team_assignment_list"), {"tab": "upcoming"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sunday Service")

    def test_assignment_list_groups_assignments_by_service_event(self):
        self.set_language("en")
        self.create_assignment()
        self.create_assignment(
            members=[self.other_team_membership],
            ministry_team=self.other_team,
        )
        self.client.login(username="assignment_pastor", password="testpass123")

        response = self.client.get(reverse("team_assignment_list"))
        content = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Lighting Team")
        self.assertContains(response, "Sound Team")
        self.assertContains(response, "View/Edit", count=2)
        self.assertEqual(content.count("Sunday Service"), 1)

    def test_assignment_list_filters_by_status(self):
        self.set_language("en")
        self.create_assignment()
        confirmed_event = ServiceEvent.objects.create(
            title="ç‰¹åˆ«èšä¼š",
            title_en="Confirmed Service",
            event_type=ServiceEvent.EVENT_SPECIAL_MEETING,
            start_datetime=timezone.now() + timezone.timedelta(days=5),            status=ServiceEvent.STATUS_PUBLISHED,
        )
        self.create_assignment(
            service_event=confirmed_event,
            status=TeamAssignment.STATUS_CONFIRMED,
        )
        self.client.login(username="assignment_pastor", password="testpass123")

        response = self.client.get(
            reverse("team_assignment_list"),
            {"tab": "upcoming", "status": TeamAssignment.STATUS_CONFIRMED},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Confirmed Service")
        self.assertNotContains(response, "Sunday Service")

    def test_assignment_list_filters_by_ministry_team(self):
        self.set_language("en")
        self.create_assignment()
        self.create_assignment(
            members=[self.other_team_membership],
            ministry_team=self.other_team,
        )
        self.client.login(username="assignment_pastor", password="testpass123")

        response = self.client.get(
            reverse("team_assignment_list"),
            {"tab": "upcoming", "team": self.other_team.id},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sound Team")
        self.assertNotIn("<strong>Lighting Team</strong>", response.content.decode())

    def test_unconfirmed_assignment_appears_in_needs_confirmation_tab(self):
        self.set_language("en")
        self.create_assignment()
        self.client.login(username="assignment_pastor", password="testpass123")

        response = self.client.get(
            reverse("team_assignment_list"),
            {"tab": "needs_confirmation"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sunday Service")

    def test_confirmed_assignment_does_not_appear_in_needs_confirmation_tab(self):
        self.set_language("en")
        assignment = self.create_assignment()
        assignment_member = assignment.assignment_members.get(membership=self.membership)
        assignment_member.confirm()
        assignment.status = TeamAssignment.STATUS_CONFIRMED
        assignment.save()
        self.client.login(username="assignment_pastor", password="testpass123")

        response = self.client.get(
            reverse("team_assignment_list"),
            {"tab": "needs_confirmation"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Sunday Service")

    def test_completed_or_past_assignment_appears_in_past_tab(self):
        self.set_language("en")
        completed_assignment = self.create_assignment(status=TeamAssignment.STATUS_COMPLETED)
        past_event = ServiceEvent.objects.create(
            title="过去聚会",
            title_en="Past Service",
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
            start_datetime=timezone.now() - timezone.timedelta(days=3),            status=ServiceEvent.STATUS_COMPLETED,
        )
        self.create_assignment(service_event=past_event)
        self.client.login(username="assignment_pastor", password="testpass123")

        response = self.client.get(reverse("team_assignment_list"), {"tab": "past"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, completed_assignment.service_event.title_en)
        self.assertContains(response, "Past Service")

    def test_cancelled_assignment_appears_in_cancelled_tab(self):
        self.set_language("en")
        self.create_assignment(status=TeamAssignment.STATUS_CANCELLED)
        self.client.login(username="assignment_pastor", password="testpass123")

        response = self.client.get(reverse("team_assignment_list"), {"tab": "cancelled"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sunday Service")

    def test_old_active_tab_maps_safely_to_needs_confirmation(self):
        self.set_language("en")
        self.create_assignment()
        self.client.login(username="assignment_pastor", password="testpass123")

        response = self.client.get(reverse("team_assignment_list"), {"tab": "active"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Needs Confirmation")
        self.assertContains(response, "Sunday Service")
        self.assertNotContains(response, ">Active<", html=False)

    def test_manager_sees_new_assignment_when_zero_assignments(self):
        self.set_language("en")
        self.client.login(username="assignment_pastor", password="testpass123")

        response = self.client.get(reverse("team_assignment_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "New Assignment")
        self.assertContains(response, "No assignments found.")

    def test_new_assignment_is_not_part_of_filter_tabs(self):
        self.set_language("en")
        self.client.login(username="assignment_pastor", password="testpass123")

        response = self.client.get(reverse("team_assignment_list"))
        content = response.content.decode()

        self.assertIn("assignment-page-actions", content)
        self.assertIn("assignment-filter-tabs", content)
        self.assertLess(
            content.index("assignment-page-actions"),
            content.index("assignment-filter-tabs"),
        )

    def test_regular_unrelated_user_does_not_see_new_assignment(self):
        self.set_language("en")
        self.client.login(username="regular_assign", password="testpass123")

        response = self.client.get(reverse("team_assignment_list"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "New Assignment")
        self.assertNotContains(response, "Suggested setup steps")

    def test_manager_empty_state_shows_setup_ctas(self):
        self.set_language("en")
        self.client.login(username="assignment_pastor", password="testpass123")

        response = self.client.get(reverse("team_assignment_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Suggested setup steps")
        self.assertContains(response, "Create Recurring Events")
        self.assertContains(response, "Ministry Teams")
        self.assertContains(response, "Lighting Pilot Import")
        self.assertContains(response, "New Assignment")

    def test_coverage_helper_reports_required_assignment_states_without_creating_rows(self):
        self.event.required_teams.add(self.team, self.other_team)
        empty_assignment = TeamAssignment.objects.create(
            service_event=self.event,
            ministry_team=self.other_team,
            status=TeamAssignment.STATUS_SCHEDULED,
        )
        assignment = self.create_assignment(
            members=[self.membership, self.second_membership],
        )
        assignment_member = assignment.assignment_members.get(membership=self.membership)
        assignment_member.confirm("Ready.")
        additional_team = MinistryTeam.objects.create(
            name="投影团队",
            name_en="Projection Team",
        )
        additional_membership = TeamMembership.objects.create(
            team=additional_team,
            display_name="Projection Helper",
        )
        additional_assignment = TeamAssignment.objects.create(
            service_event=self.event,
            ministry_team=additional_team,
            status=TeamAssignment.STATUS_SCHEDULED,
        )
        TeamAssignmentMember.objects.create(
            assignment=additional_assignment,
            membership=additional_membership,
        )
        before_assignment_count = TeamAssignment.objects.count()
        before_member_count = TeamAssignmentMember.objects.count()

        event = events_with_coverage_queryset().get(id=self.event.id)
        coverage = build_assignment_coverage(
            [event],
            list(assignment_coverage_queryset().filter(service_event=event)),
            language="en",
        )[event.id]

        rows_by_team = {row["team"].name_en: row for row in coverage["rows"]}
        self.assertEqual(rows_by_team["Lighting Team"]["summary_label"], "Assigned 2 people")
        lighting_statuses = [
            member["status_label"] for member in rows_by_team["Lighting Team"]["members"]
        ]
        self.assertIn("Confirmed", lighting_statuses)
        self.assertIn("Awaiting confirmation", lighting_statuses)
        self.assertEqual(
            rows_by_team["Sound Team"]["summary_label"],
            "Assignment exists, no people assigned",
        )
        self.assertEqual(rows_by_team["Projection Team"]["summary_label"], "Additional assignment")
        self.assertEqual(coverage["missing_count"], 0)
        self.assertEqual(TeamAssignment.objects.count(), before_assignment_count)
        self.assertEqual(TeamAssignmentMember.objects.count(), before_member_count)
        self.assertEqual(empty_assignment.assignment_members.count(), 0)

    def test_coverage_helper_reports_missing_required_team_without_creating_assignment(self):
        self.event.required_teams.add(self.other_team)
        before_assignment_count = TeamAssignment.objects.count()
        before_member_count = TeamAssignmentMember.objects.count()

        event = events_with_coverage_queryset().get(id=self.event.id)
        coverage = build_assignment_coverage([event], [], language="en")[event.id]

        self.assertEqual(coverage["rows"][0]["summary_label"], "Unassigned")
        self.assertEqual(coverage["missing_count"], 1)
        self.assertEqual(TeamAssignment.objects.count(), before_assignment_count)
        self.assertEqual(TeamAssignmentMember.objects.count(), before_member_count)

    def test_assignment_list_shows_required_team_coverage_and_members(self):
        self.set_language("en")
        self.event.required_teams.add(self.team, self.other_team)
        assignment = self.create_assignment(
            members=[self.membership, self.second_membership],
        )
        assignment.assignment_members.get(membership=self.membership).confirm()
        self.client.login(username="assignment_pastor", password="testpass123")

        response = self.client.get(reverse("team_assignment_list"), {"tab": "upcoming"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Assignment Coverage")
        self.assertContains(response, "Lighting Team")
        self.assertContains(response, "Assigned 2 people")
        self.assertContains(response, "regular_assign（Confirmed）")
        self.assertContains(response, "other_assign（Awaiting confirmation）")
        self.assertContains(response, "Sound Team")
        self.assertContains(response, "Unassigned")

    def test_assignment_list_marks_non_required_assignment_as_additional(self):
        self.set_language("en")
        self.event.required_teams.add(self.team)
        self.create_assignment(
            members=[self.other_team_membership],
            ministry_team=self.other_team,
        )
        self.client.login(username="assignment_pastor", password="testpass123")

        response = self.client.get(reverse("team_assignment_list"), {"tab": "upcoming"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sound Team")
        self.assertContains(response, "Additional assignment")

    def test_team_lead_sees_only_manageable_team_missing_coverage(self):
        self.set_language("en")
        self.event.required_teams.add(self.team, self.other_team)
        self.client.login(username="assignment_lead", password="testpass123")

        response = self.client.get(reverse("team_assignment_list"), {"tab": "upcoming"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Lighting Team")
        self.assertContains(response, "Unassigned")
        self.assertNotContains(response, "Sound Team")

    def test_assignment_detail_shows_compact_event_coverage(self):
        self.set_language("en")
        self.event.required_teams.add(self.team, self.other_team)
        assignment = self.create_assignment()
        self.client.login(username="assignment_pastor", password="testpass123")

        response = self.client.get(reverse("team_assignment_detail", args=[assignment.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Event Assignment Coverage")
        self.assertContains(response, "Lighting Team")
        self.assertContains(response, "Assigned 1 person")
        self.assertContains(response, "Sound Team")
        self.assertContains(response, "Unassigned")

    def test_team_schedule_link_appears_for_team_lead_only(self):
        self.set_language("en")
        self.client.login(username="assignment_lead", password="testpass123")

        lead_response = self.client.get(reverse("ministry_team_detail", args=[self.team.id]))

        self.client.logout()
        self.client.login(username="regular_assign", password="testpass123")
        member_response = self.client.get(reverse("ministry_team_detail", args=[self.team.id]))

        self.assertEqual(lead_response.status_code, 200)
        self.assertContains(lead_response, "Schedule Team")
        self.assertContains(
            lead_response,
            reverse("team_schedule", args=[self.team.id]),
        )
        self.assertEqual(member_response.status_code, 200)
        self.assertNotContains(member_response, "Schedule Team")

    def test_team_schedule_link_appears_for_team_coordinator(self):
        self.set_language("en")
        self.client.login(username="assignment_coordinator", password="testpass123")

        response = self.client.get(reverse("ministry_team_detail", args=[self.team.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Schedule Team")
        self.assertContains(response, reverse("team_schedule", args=[self.team.id]))

    def test_can_lead_member_does_not_see_team_schedule_link(self):
        self.set_language("en")
        self.client.login(username="assignment_can_lead", password="testpass123")

        response = self.client.get(reverse("ministry_team_detail", args=[self.team.id]))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Schedule Team")
        self.assertNotContains(response, "Can Lead")
        self.assertNotContains(response, reverse("team_schedule", args=[self.team.id]))

    def test_team_lead_can_access_own_team_schedule(self):
        self.set_language("en")
        self.event.required_teams.add(self.team)
        self.client.login(username="assignment_lead", password="testpass123")

        response = self.client.get(reverse("team_schedule", args=[self.team.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Schedule Team")
        self.assertContains(response, "Lighting Team")
        self.assertContains(response, "Sunday Service")
        self.assertContains(response, "Unassigned")

    def test_team_coordinator_can_access_own_team_schedule(self):
        self.set_language("en")
        self.event.required_teams.add(self.team)
        self.client.login(username="assignment_coordinator", password="testpass123")

        response = self.client.get(reverse("team_schedule", args=[self.team.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Schedule Team")
        self.assertContains(response, "Lighting Team")
        self.assertContains(response, "Sunday Service")

    def test_can_lead_member_cannot_access_own_team_schedule(self):
        self.set_language("en")
        self.event.required_teams.add(self.team)
        self.client.login(username="assignment_can_lead", password="testpass123")

        response = self.client.get(reverse("team_schedule", args=[self.team.id]))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("ministry_team_list"))

    def test_team_lead_cannot_access_other_team_schedule(self):
        self.set_language("en")
        self.client.login(username="assignment_lead", password="testpass123")

        response = self.client.get(reverse("team_schedule", args=[self.other_team.id]))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("ministry_team_list"))

    def test_team_coordinator_cannot_access_other_team_schedule(self):
        self.set_language("en")
        self.client.login(username="assignment_coordinator", password="testpass123")

        response = self.client.get(reverse("team_schedule", args=[self.other_team.id]))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("ministry_team_list"))

    def test_can_lead_member_cannot_access_other_team_schedule(self):
        self.set_language("en")
        self.client.login(username="assignment_can_lead", password="testpass123")

        response = self.client.get(reverse("team_schedule", args=[self.other_team.id]))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("ministry_team_list"))

    def test_ordinary_member_cannot_access_team_schedule(self):
        self.set_language("en")
        self.client.login(username="regular_assign", password="testpass123")

        response = self.client.get(reverse("team_schedule", args=[self.team.id]))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("ministry_team_list"))

    def test_staff_can_access_any_team_schedule(self):
        self.set_language("en")
        self.event.required_teams.add(self.other_team)
        self.client.login(username="assignment_staff", password="testpass123")

        response = self.client.get(reverse("team_schedule", args=[self.other_team.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sound Team")
        self.assertContains(response, "Sunday Service")

    def test_team_schedule_default_shows_required_or_assigned_events_across_event_types(self):
        self.set_language("en")
        self.event.required_teams.add(self.team)
        unrelated_event = ServiceEvent.objects.create(
            title="Unrelated Sunday",
            title_en="Unrelated Sunday",
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
            start_datetime=self.event.start_datetime + timezone.timedelta(days=7),            status=ServiceEvent.STATUS_PUBLISHED,
        )
        unrelated_event.required_teams.add(self.other_team)
        bible_study_event = ServiceEvent.objects.create(
            title="查经",
            title_en="Bible Study Night",
            event_type=ServiceEvent.EVENT_BIBLE_STUDY,
            start_datetime=self.event.start_datetime + timezone.timedelta(days=14),            status=ServiceEvent.STATUS_PUBLISHED,
        )
        bible_study_event.required_teams.add(self.team)
        additional_event = ServiceEvent.objects.create(
            title="特别服事",
            title_en="Special Service Assignment",
            event_type=ServiceEvent.EVENT_SPECIAL_MEETING,
            start_datetime=self.event.start_datetime + timezone.timedelta(days=21),            status=ServiceEvent.STATUS_PUBLISHED,
        )
        self.create_assignment(service_event=additional_event)
        self.client.login(username="assignment_lead", password="testpass123")

        response = self.client.get(reverse("team_schedule", args=[self.team.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "All event types")
        self.assertContains(response, "Sunday Service")
        self.assertContains(response, "Bible Study Night")
        self.assertContains(response, "Special Service Assignment")
        self.assertNotContains(response, "Unrelated Sunday")

    def test_team_schedule_specific_sunday_filter_excludes_other_event_types(self):
        self.set_language("en")
        self.event.required_teams.add(self.team)
        bible_study_event = ServiceEvent.objects.create(
            title="查经",
            title_en="Bible Study Night",
            event_type=ServiceEvent.EVENT_BIBLE_STUDY,
            start_datetime=self.event.start_datetime + timezone.timedelta(days=14),            status=ServiceEvent.STATUS_PUBLISHED,
        )
        bible_study_event.required_teams.add(self.team)
        self.client.login(username="assignment_lead", password="testpass123")

        response = self.client.get(
            f"{reverse('team_schedule', args=[self.team.id])}"
            f"?event_type={ServiceEvent.EVENT_SUNDAY_SERVICE}"
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sunday Service")
        self.assertNotContains(response, "Bible Study Night")

    def test_cancelled_event_assignment_does_not_appear_in_upcoming_assignment_list(self):
        self.set_language("en")
        cancelled_event = self.create_schedule_event(
            title_en="Cancelled Service",
            days_from_now=2,
            status=ServiceEvent.STATUS_CANCELLED,
        )
        self.create_assignment(service_event=cancelled_event)
        self.client.login(username="assignment_pastor", password="testpass123")

        response = self.client.get(reverse("team_assignment_list"), {"tab": "upcoming"})

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Cancelled Service")

    def test_draft_event_assignment_does_not_appear_in_upcoming_assignment_list(self):
        self.set_language("en")
        draft_event = self.create_schedule_event(
            title_en="Draft Service",
            days_from_now=2,
            status=ServiceEvent.STATUS_DRAFT,
        )
        self.create_assignment(service_event=draft_event)
        self.client.login(username="assignment_pastor", password="testpass123")

        response = self.client.get(reverse("team_assignment_list"), {"tab": "upcoming"})

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Draft Service")

    def test_cancelled_event_assignment_does_not_appear_in_needs_confirmation_list(self):
        self.set_language("en")
        cancelled_event = self.create_schedule_event(
            title_en="Cancelled Needs Confirmation",
            days_from_now=2,
            status=ServiceEvent.STATUS_CANCELLED,
        )
        self.create_assignment(service_event=cancelled_event)
        self.client.login(username="assignment_pastor", password="testpass123")

        response = self.client.get(
            reverse("team_assignment_list"),
            {"tab": "needs_confirmation"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Cancelled Needs Confirmation")

    def test_draft_event_assignment_does_not_appear_in_needs_confirmation_list(self):
        self.set_language("en")
        draft_event = self.create_schedule_event(
            title_en="Draft Needs Confirmation",
            days_from_now=2,
            status=ServiceEvent.STATUS_DRAFT,
        )
        self.create_assignment(service_event=draft_event)
        self.client.login(username="assignment_pastor", password="testpass123")

        response = self.client.get(
            reverse("team_assignment_list"),
            {"tab": "needs_confirmation"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Draft Needs Confirmation")

    def test_team_schedule_includes_existing_additional_assignment(self):
        self.set_language("en")
        self.create_assignment()
        self.client.login(username="assignment_lead", password="testpass123")

        response = self.client.get(reverse("team_schedule", args=[self.team.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sunday Service")
        self.assertContains(response, "Additional assignment")
        self.assertContains(response, "regular_assign")

    def test_team_schedule_load_does_not_create_assignment(self):
        self.set_language("en")
        self.event.required_teams.add(self.team)
        self.client.login(username="assignment_lead", password="testpass123")

        response = self.client.get(reverse("team_schedule", args=[self.team.id]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(TeamAssignment.objects.count(), 0)
        self.assertEqual(TeamAssignmentMember.objects.count(), 0)

    def test_team_schedule_shows_rotation_anchor_without_creating_assignment(self):
        self.set_language("en")
        anchor_team = MinistryTeam.objects.create(
            name="敬拜 C1",
            name_en="Worship C1",
        )
        self.event.required_teams.add(self.team)
        self.event.rotation_anchor_team = anchor_team
        self.event.save()
        self.client.login(username="assignment_lead", password="testpass123")

        response = self.client.get(reverse("team_schedule", args=[self.team.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Rotation Anchor Team")
        self.assertContains(response, "Worship C1")
        self.assertEqual(TeamAssignment.objects.count(), 0)
        self.assertEqual(TeamAssignmentMember.objects.count(), 0)

    def test_team_schedule_anchor_suggestion_get_prefills_without_creating_assignment(self):
        self.set_language("en")
        anchor_team = MinistryTeam.objects.create(
            name="敬拜 C1",
            name_en="Worship C1",
        )
        source_event = self.create_schedule_event(
            title_en="Prior Sunday",
            days_from_now=1,
            anchor=anchor_team,
        )
        self.create_assignment(
            service_event=source_event,
            members=[self.second_membership],
        )
        self.event.required_teams.add(self.team)
        self.event.rotation_anchor_team = anchor_team
        self.event.save()
        before_count = TeamAssignment.objects.count()
        self.client.login(username="assignment_lead", password="testpass123")

        response = self.client.get(
            f"{reverse('team_schedule', args=[self.team.id])}"
            f"?event={self.event.id}&suggest=anchor"
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Suggestion Source")
        self.assertContains(response, "Prior Sunday")
        self.assertContains(response, "regular_assign")
        self.assertEqual(TeamAssignment.objects.count(), before_count)
        self.assertFalse(
            TeamAssignment.objects.filter(
                service_event=self.event,
                ministry_team=self.team,
            ).exists()
        )

    def test_team_schedule_suggested_form_creates_assignment_only_after_post(self):
        self.set_language("en")
        anchor_team = MinistryTeam.objects.create(
            name="敬拜 C1",
            name_en="Worship C1",
        )
        source_event = self.create_schedule_event(
            title_en="Prior Sunday",
            days_from_now=1,
            anchor=anchor_team,
        )
        source_assignment = self.create_assignment(
            service_event=source_event,
            members=[self.second_membership],
        )
        source_member = source_assignment.assignment_members.get(
            membership=self.second_membership,
        )
        source_member.confirm()
        self.event.required_teams.add(self.team)
        self.event.rotation_anchor_team = anchor_team
        self.event.save()
        self.client.login(username="assignment_lead", password="testpass123")

        response = self.client.post(
            f"{reverse('team_schedule', args=[self.team.id])}"
            f"?event={self.event.id}&suggest=anchor",
            {
                "assigned_members": [self.second_membership.id],
                "status": TeamAssignment.STATUS_SCHEDULED,
                "notes": "",
            },
        )

        self.assertEqual(response.status_code, 302)
        assignment = TeamAssignment.objects.get(
            service_event=self.event,
            ministry_team=self.team,
        )
        self.assertEqual(assignment.assigned_members.get(), self.second_membership)
        self.assertEqual(assignment.status, TeamAssignment.STATUS_SCHEDULED)
        self.assertEqual(assignment.notes, "")
        target_member = assignment.assignment_members.get(
            membership=self.second_membership,
        )
        self.assertIsNone(target_member.confirmed_at)

    def test_team_schedule_team_only_suggestion_updates_existing_assignment_without_duplicate(self):
        self.set_language("en")
        source_event = self.create_schedule_event(
            title_en="Prior Sunday",
            days_from_now=1,
        )
        self.create_assignment(
            service_event=source_event,
            members=[self.second_membership],
        )
        self.event.required_teams.add(self.team)
        existing_assignment = self.create_assignment(
            service_event=self.event,
            members=[self.membership],
        )
        self.client.login(username="assignment_lead", password="testpass123")

        response = self.client.post(
            f"{reverse('team_schedule', args=[self.team.id])}"
            f"?event={self.event.id}&suggest=team",
            {
                "assigned_members": [self.second_membership.id],
                "status": TeamAssignment.STATUS_SCHEDULED,
                "notes": "Edited before save.",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            TeamAssignment.objects.filter(
                service_event=self.event,
                ministry_team=self.team,
            ).count(),
            1,
        )
        existing_assignment.refresh_from_db()
        self.assertEqual(existing_assignment.notes, "Edited before save.")
        self.assertEqual(existing_assignment.assigned_members.get(), self.second_membership)

    def test_team_schedule_suggestion_get_preserves_existing_assignment_status(self):
        self.set_language("en")
        source_event = self.create_schedule_event(
            title_en="Prior Sunday",
            days_from_now=1,
        )
        self.create_assignment(
            service_event=source_event,
            members=[self.second_membership],
        )
        self.event.required_teams.add(self.team)
        self.create_assignment(
            service_event=self.event,
            members=[self.membership],
            status=TeamAssignment.STATUS_PREPARED,
        )
        self.client.login(username="assignment_lead", password="testpass123")

        response = self.client.get(
            f"{reverse('team_schedule', args=[self.team.id])}"
            f"?event={self.event.id}&suggest=team"
        )

        self.assertEqual(response.status_code, 200)
        form = response.context["active_form"]
        self.assertEqual(form["status"].value(), TeamAssignment.STATUS_PREPARED)
        self.assertEqual(
            [membership.id for membership in form.fields["assigned_members"].initial],
            [self.second_membership.id],
        )

    def test_team_schedule_duplicate_target_assignments_block_helper_save(self):
        self.set_language("en")
        source_event = self.create_schedule_event(
            title_en="Prior Sunday",
            days_from_now=1,
        )
        self.create_assignment(
            service_event=source_event,
            members=[self.second_membership],
        )
        self.event.required_teams.add(self.team)
        first_assignment = self.create_assignment(
            service_event=self.event,
            members=[self.membership],
            notes="First target.",
        )
        second_assignment = self.create_assignment(
            service_event=self.event,
            members=[self.second_membership],
            notes="Second target.",
        )
        self.client.login(username="assignment_lead", password="testpass123")

        response = self.client.post(
            f"{reverse('team_schedule', args=[self.team.id])}"
            f"?event={self.event.id}&suggest=team",
            {
                "assigned_members": [self.second_membership.id],
                "status": TeamAssignment.STATUS_SCHEDULED,
                "notes": "Should not save.",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "duplicate assignments for this team")
        self.assertEqual(
            TeamAssignment.objects.filter(
                service_event=self.event,
                ministry_team=self.team,
            ).count(),
            2,
        )
        first_assignment.refresh_from_db()
        second_assignment.refresh_from_db()
        self.assertEqual(first_assignment.notes, "First target.")
        self.assertEqual(second_assignment.notes, "Second target.")

    def test_team_schedule_creates_assignment_for_missing_required_event(self):
        self.set_language("en")
        self.event.required_teams.add(self.team)
        self.client.login(username="assignment_lead", password="testpass123")

        response = self.client.post(
            f"{reverse('team_schedule', args=[self.team.id])}?event={self.event.id}",
            {
                "assigned_members": [self.membership.id, self.second_membership.id],
                "status": TeamAssignment.STATUS_SCHEDULED,
                "notes": "Schedule from workspace.",
            },
        )

        self.assertEqual(response.status_code, 302)
        assignment = TeamAssignment.objects.get()
        self.assertEqual(assignment.service_event, self.event)
        self.assertEqual(assignment.ministry_team, self.team)
        self.assertEqual(assignment.created_by, self.lead_user)
        self.assertEqual(assignment.notes, "Schedule from workspace.")
        self.assertEqual(assignment.assigned_members.count(), 2)

    def test_team_schedule_updates_existing_assignment_from_event_action_without_duplicate(self):
        self.set_language("en")
        self.event.required_teams.add(self.team)
        assignment = self.create_assignment()
        self.client.login(username="assignment_lead", password="testpass123")

        response = self.client.post(
            f"{reverse('team_schedule', args=[self.team.id])}?event={self.event.id}",
            {
                "assigned_members": [self.second_membership.id],
                "status": TeamAssignment.STATUS_PREPARED,
                "notes": "Updated through event action.",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(TeamAssignment.objects.count(), 1)
        assignment.refresh_from_db()
        self.assertEqual(assignment.status, TeamAssignment.STATUS_PREPARED)
        self.assertEqual(assignment.notes, "Updated through event action.")
        self.assertEqual(
            list(assignment.assigned_members.values_list("id", flat=True)),
            [self.second_membership.id],
        )

    def test_team_schedule_updates_existing_assignment_from_assignment_action(self):
        self.set_language("en")
        assignment = self.create_assignment()
        self.client.login(username="assignment_lead", password="testpass123")

        response = self.client.post(
            f"{reverse('team_schedule', args=[self.team.id])}?assignment={assignment.id}",
            {
                "assigned_members": [self.membership.id, self.second_membership.id],
                "status": TeamAssignment.STATUS_CONFIRMED,
                "notes": "Edited from workspace.",
            },
        )

        self.assertEqual(response.status_code, 302)
        assignment.refresh_from_db()
        self.assertEqual(assignment.status, TeamAssignment.STATUS_CONFIRMED)
        self.assertEqual(assignment.notes, "Edited from workspace.")
        self.assertEqual(assignment.assigned_members.count(), 2)

    def test_team_schedule_rejects_cross_team_member_submission(self):
        self.set_language("en")
        self.event.required_teams.add(self.team)
        self.client.login(username="assignment_lead", password="testpass123")

        response = self.client.post(
            f"{reverse('team_schedule', args=[self.team.id])}?event={self.event.id}",
            {
                "assigned_members": [self.other_team_membership.id],
                "status": TeamAssignment.STATUS_SCHEDULED,
                "notes": "Invalid cross-team member.",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Select a valid choice", html=False)
        self.assertFalse(TeamAssignment.objects.exists())

    def test_no_future_workflow_routes_exist_after_team_schedule(self):
        missing_routes = [
            "availability_matrix",
            "swap_request_list",
            "team_reminder_list",
            "assignment_checklist",
            "team_rotation_helper",
            "copy_forward_assignments",
        ]
        for route_name in missing_routes:
            with self.assertRaises(NoReverseMatch):
                reverse(route_name)

    def assignment_form_event_ids(self, **kwargs):
        form = TeamAssignmentForm(
            language="en",
            manageable_teams=MinistryTeam.objects.all(),
            **kwargs,
        )
        return list(
            form.fields["service_event"].queryset.values_list("id", flat=True)
        )

    def make_bible_study_meeting(self, service_event):
        series = BibleStudySeries.objects.create(title="约翰福音查经")
        lesson = BibleStudyLesson.objects.create(
            series=series,
            title="约翰十五章",
            lesson_date=timezone.localdate() + timezone.timedelta(days=3),
        )
        # BS-MEETING-MIRROR.1A removed the legacy BibleStudyMeeting.small_group FK;
        # this fixture only needs the meeting's service_event linkage.
        return BibleStudyMeeting.objects.create(
            lesson=lesson,
            meeting_datetime=timezone.now() + timezone.timedelta(days=2),
            service_event=service_event,
        )

    def test_assignment_form_excludes_cancelled_events(self):
        cancelled = ServiceEvent.objects.create(
            title="取消聚会",
            title_en="Cancelled Event",
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
            start_datetime=timezone.now() + timezone.timedelta(days=3),            status=ServiceEvent.STATUS_CANCELLED,
        )

        event_ids = self.assignment_form_event_ids()

        self.assertNotIn(cancelled.id, event_ids)
        self.assertIn(self.event.id, event_ids)

    def test_assignment_form_excludes_draft_events(self):
        draft = ServiceEvent.objects.create(
            title="草稿聚会",
            title_en="Draft Event",
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
            start_datetime=timezone.now() + timezone.timedelta(days=3),            status=ServiceEvent.STATUS_DRAFT,
        )

        event_ids = self.assignment_form_event_ids()

        self.assertNotIn(draft.id, event_ids)
        self.assertIn(self.event.id, event_ids)

    def test_assignment_form_excludes_past_events(self):
        past = ServiceEvent.objects.create(
            title="过去聚会",
            title_en="Past Event",
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
            start_datetime=timezone.now() - timezone.timedelta(days=3),            status=ServiceEvent.STATUS_PUBLISHED,
        )

        event_ids = self.assignment_form_event_ids()

        self.assertNotIn(past.id, event_ids)
        self.assertIn(self.event.id, event_ids)

    def test_assignment_form_excludes_bible_study_meeting_events(self):
        study_event = ServiceEvent.objects.create(
            title="小组查经",
            title_en="Group Bible Study",
            event_type=ServiceEvent.EVENT_BIBLE_STUDY,
            start_datetime=timezone.now() + timezone.timedelta(days=3),            status=ServiceEvent.STATUS_PUBLISHED,
        )
        self.make_bible_study_meeting(study_event)

        event_ids = self.assignment_form_event_ids()

        self.assertNotIn(study_event.id, event_ids)
        self.assertIn(self.event.id, event_ids)

    def test_assignment_form_lists_future_published_operational_events(self):
        special = ServiceEvent.objects.create(
            title="特别聚会",
            title_en="Special Meeting",
            event_type=ServiceEvent.EVENT_SPECIAL_MEETING,
            start_datetime=timezone.now() + timezone.timedelta(days=5),            status=ServiceEvent.STATUS_PUBLISHED,
        )

        event_ids = self.assignment_form_event_ids()

        self.assertIn(self.event.id, event_ids)
        self.assertIn(special.id, event_ids)

    def test_assignment_edit_keeps_current_filtered_event_available(self):
        past = ServiceEvent.objects.create(
            title="过去聚会",
            title_en="Past Event",
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
            start_datetime=timezone.now() - timezone.timedelta(days=3),            status=ServiceEvent.STATUS_PUBLISHED,
        )
        assignment = self.create_assignment(service_event=past)

        new_event_ids = self.assignment_form_event_ids()
        edit_event_ids = self.assignment_form_event_ids(instance=assignment)

        self.assertNotIn(past.id, new_event_ids)
        self.assertIn(past.id, edit_event_ids)

    def test_assignment_edit_does_not_silently_change_event(self):
        self.set_language("en")
        past = ServiceEvent.objects.create(
            title="过去聚会",
            title_en="Past Event",
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
            start_datetime=timezone.now() - timezone.timedelta(days=3),            status=ServiceEvent.STATUS_PUBLISHED,
        )
        assignment = self.create_assignment(service_event=past)
        self.client.login(username="assignment_pastor", password="testpass123")

        response = self.client.post(
            reverse("edit_team_assignment", args=[assignment.id]),
            self.assignment_post_data(
                service_event=past.id,
                notes="Updated note only.",
            ),
        )

        self.assertEqual(response.status_code, 302)
        assignment.refresh_from_db()
        self.assertEqual(assignment.service_event_id, past.id)
        self.assertEqual(assignment.notes, "Updated note only.")


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
            "event_title": "主日崇拜",
            "event_title_en": "Sunday Service",
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
            "event_title_en",
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

        team = MinistryTeam.objects.get(name="灯光组")
        self.assertEqual(team.name_en, "Lighting Team")
        self.assertEqual(team.playbook_link, "https://example.com/lighting-playbook")
        self.assertIn("teams_created=1", output)

    def test_import_reuses_legacy_lighting_team_and_normalizes_on_real_import(self):
        MinistryTeam.objects.create(name="Lighting Team")
        csv_path = self.write_csv(self.csv_content())

        output = self.run_import(csv_path)

        self.assertEqual(MinistryTeam.objects.count(), 1)
        team = MinistryTeam.objects.get()
        self.assertEqual(team.name, "灯光组")
        self.assertEqual(team.name_en, "Lighting Team")
        self.assertIn("normalized Lighting Team", output)

    def test_dry_run_does_not_normalize_legacy_lighting_team(self):
        team = MinistryTeam.objects.create(name="Lighting Team")
        csv_path = self.write_csv(self.csv_content())

        output = self.run_import(csv_path, "--dry-run")

        team.refresh_from_db()
        self.assertEqual(team.name, "Lighting Team")
        self.assertEqual(team.name_en, "")
        self.assertIn("normalized Lighting Team", output)

    def test_import_creates_display_name_only_membership_when_no_matching_user(self):
        csv_path = self.write_csv(self.csv_content(assigned_member="Guest Helper"))

        self.run_import(csv_path)

        membership = TeamMembership.objects.get(display_name="Guest Helper")
        self.assertIsNone(membership.user)
        self.assertEqual(membership.team.name, "灯光组")

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
        self.assertEqual(membership.team.name, "灯光组")

    def test_import_creates_service_event(self):
        csv_path = self.write_csv(self.csv_content())

        self.run_import(csv_path)

        event = ServiceEvent.objects.get(title="主日崇拜")
        self.assertEqual(event.title_en, "Sunday Service")
        self.assertEqual(event.event_type, ServiceEvent.EVENT_SUNDAY_SERVICE)
        self.assertEqual(event.status, ServiceEvent.STATUS_PUBLISHED)
        self.assertIn("Main sanctuary service.", event.description)

    def test_import_creates_team_assignment(self):
        csv_path = self.write_csv(self.csv_content())

        self.run_import(csv_path)

        assignment = TeamAssignment.objects.get()
        self.assertEqual(assignment.ministry_team.name, "灯光组")
        self.assertIn("Special event note: Baptism Sunday.", assignment.notes)
        self.assertIn("Worship team: Worship Team A", assignment.notes)

    def test_import_creates_team_assignment_member(self):
        csv_path = self.write_csv(self.csv_content())

        self.run_import(csv_path)

        assignment_member = TeamAssignmentMember.objects.get()
        self.assertEqual(assignment_member.assignment.ministry_team.name, "灯光组")
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

    def test_rerunning_bilingual_import_does_not_duplicate_service_event(self):
        csv_path = self.write_csv(self.csv_content())

        self.run_import(csv_path)
        self.run_import(csv_path)

        self.assertEqual(ServiceEvent.objects.count(), 1)
        event = ServiceEvent.objects.get()
        self.assertEqual(event.title, "主日崇拜")
        self.assertEqual(event.title_en, "Sunday Service")

    def test_existing_english_only_sunday_service_event_is_reused_and_normalized(self):
        start_datetime = timezone.make_aware(
            timezone.datetime.combine(
                self.future_date,
                timezone.datetime.strptime("10:00", "%H:%M").time(),
            ),
            timezone.get_current_timezone(),
        )
        ServiceEvent.objects.create(
            title="Sunday Service",
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
            start_datetime=start_datetime,            status=ServiceEvent.STATUS_PUBLISHED,
        )
        csv_path = self.write_csv(self.csv_content())

        output = self.run_import(csv_path)

        self.assertEqual(ServiceEvent.objects.count(), 1)
        event = ServiceEvent.objects.get()
        self.assertEqual(event.title, "主日崇拜")
        self.assertEqual(event.title_en, "Sunday Service")
        self.assertIn("normalized ServiceEvent title", output)

    def test_import_does_not_reuse_cancelled_matching_service_event(self):
        start_datetime = timezone.make_aware(
            timezone.datetime.combine(
                self.future_date,
                timezone.datetime.strptime("10:00", "%H:%M").time(),
            ),
            timezone.get_current_timezone(),
        )
        cancelled_event = ServiceEvent.objects.create(
            title="主日崇拜",
            title_en="Sunday Service",
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
            start_datetime=start_datetime,            status=ServiceEvent.STATUS_CANCELLED,
        )
        csv_path = self.write_csv(self.csv_content())

        self.run_import(csv_path)

        self.assertEqual(ServiceEvent.objects.count(), 2)
        cancelled_event.refresh_from_db()
        self.assertEqual(cancelled_event.status, ServiceEvent.STATUS_CANCELLED)
        self.assertFalse(cancelled_event.team_assignments.exists())
        replacement_event = (
            ServiceEvent.objects.exclude(id=cancelled_event.id).get()
        )
        self.assertEqual(replacement_event.status, ServiceEvent.STATUS_PUBLISHED)
        assignment = TeamAssignment.objects.get()
        self.assertEqual(assignment.service_event, replacement_event)

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
        self.assertContains(response, "Sunday Service")
        self.assertContains(response, "Lighting Team")
        self.assertContains(response, "Confirm Assignment")

    def test_chinese_pages_display_bilingual_pilot_data(self):
        self.set_language("zh")
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
        self.assertContains(response, "主日崇拜")
        self.assertContains(response, "灯光组")
        self.assertNotContains(response, "Sunday Service")

    def test_english_pages_display_bilingual_pilot_data(self):
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
        self.assertContains(response, "Sunday Service")
        self.assertContains(response, "Lighting Team")

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
        self.assertEqual(MinistryTeam.objects.get().name, "灯光组")
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

        self.assertIn("event_title_en", content)
        self.assertIn("2026-07-05", content)
        self.assertIn("主日崇拜", content)
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
        self.assertContains(response, "Use event_title for the Chinese/local title.")
