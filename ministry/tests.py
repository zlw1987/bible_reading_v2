from io import StringIO
from datetime import datetime, timezone as datetime_timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from django.apps import apps
from django.contrib.auth.models import User
from django.contrib.messages import get_messages
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command, CommandError
from django.test import TestCase
from django.urls import NoReverseMatch, reverse
from django.utils import timezone

from accounts.models import (
    ChurchMemberRecord,
    ChurchRoleAssignment,
    ChurchStructureMembership,
    ChurchStructureUnit,
    ChurchStructureUnitRoleAssignment,
    ChurchStructureUnitRoleType,
    ServingReadinessPolicy,
)
from events.models import ServiceEvent
from reading.templatetags.datetime_extras import member_datetime
from studies.models import (
    BibleStudyLesson,
    BibleStudyMeeting,
    BibleStudyMeetingAudienceScope,
    BibleStudyMeetingRole,
    BibleStudySeries,
)

from .models import (
    MinistryTeam,
    MinistryTeamParentLink,
    MinistryTeamRoleAssignment,
    MinistryTeamRoleProfile,
    MinistryTeamRoleRequirement,
    MinistryTeamRoleType,
    TeamAssignment,
    TeamAssignmentMember,
    TeamMembership,
)
from .permissions import can_manage_ministry_team
from .structure_map import build_ministry_structure_map
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
from .structure_readiness import run_audit


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

    def test_team_detail_orders_members_by_visible_display_name(self):
        zed_user = User.objects.create_user(
            username="aaa_team_member",
            email="aaa-team-member@example.com",
            password="testpass123",
            first_name="Zed",
            last_name="Member",
        )
        amy_user = User.objects.create_user(
            username="zzz_team_member",
            email="zzz-team-member@example.com",
            password="testpass123",
            first_name="Amy",
            last_name="Member",
        )
        zed = self.create_membership(user=zed_user)
        amy = self.create_membership(user=amy_user)
        self.client.login(username="pastor_ministry", password="testpass123")

        response = self.client.get(reverse("ministry_team_detail", args=[self.team.id]))

        member_ids = [membership.id for membership in response.context["memberships"]]
        self.assertLess(member_ids.index(amy.id), member_ids.index(zed.id))

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

    def ensure_structure_membership(self, user=None, unit=None):
        return ChurchStructureMembership.objects.get_or_create(
            user=user or self.user,
            unit=unit or self.cm_unit,
            defaults={
                "status": ChurchStructureMembership.STATUS_ACTIVE,
                "is_primary": True,
                "start_date": timezone.localdate() - timezone.timedelta(days=1),
            },
        )[0]

    def create_bible_study_meeting(self, *, title_en, days_from_today=0, hour=19, unit=None):
        unit = unit or self.cm_unit
        series = BibleStudySeries.objects.create(
            title=title_en,
            title_en=title_en,
            status=BibleStudySeries.STATUS_PUBLISHED,
            is_active=True,
        )
        lesson = BibleStudyLesson.objects.create(
            series=series,
            title=title_en,
            title_en=title_en,
            lesson_date=timezone.localdate() + timezone.timedelta(days=days_from_today),
            status=BibleStudyLesson.STATUS_PUBLISHED,
        )
        meeting = BibleStudyMeeting.objects.create(
            lesson=lesson,
            anchor_unit=unit,
            meeting_datetime=self.local_datetime(days_from_today, hour=hour),
            status=BibleStudyMeeting.STATUS_PUBLISHED,
        )
        BibleStudyMeetingAudienceScope.objects.create(meeting=meeting, unit=unit)
        return meeting

    def create_bible_study_role(self, meeting, role, *, user=None, display_name=""):
        return BibleStudyMeetingRole.objects.create(
            meeting=meeting,
            role=role,
            user=user,
            display_name=display_name,
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

    def test_assignment_member_selector_orders_by_visible_display_name(self):
        zed_user = User.objects.create_user(
            username="aaa_assignment_member",
            email="aaa-assignment-member@example.com",
            password="testpass123",
            first_name="Zed",
            last_name="Assignment",
        )
        amy_user = User.objects.create_user(
            username="zzz_assignment_member",
            email="zzz-assignment-member@example.com",
            password="testpass123",
            first_name="Amy",
            last_name="Assignment",
        )
        zed = TeamMembership.objects.create(team=self.team, user=zed_user)
        amy = TeamMembership.objects.create(team=self.team, user=amy_user)

        form = TeamAssignmentForm(
            language="en",
            manageable_teams=MinistryTeam.objects.all(),
            selected_team_id=self.team.id,
        )

        member_ids = [
            membership.id for membership in form.fields["assigned_members"].queryset
        ]
        self.assertLess(member_ids.index(amy.id), member_ids.index(zed.id))

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
        self.assertContains(response, "Fri, Jun 12, 12:30 PM")
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

    def test_my_serving_orders_personal_rows_by_event_start_datetime(self):
        self.set_language("en")
        later_event = ServiceEvent.objects.create(
            title="Later Personal Service",
            title_en="Later Personal Service",
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
            start_datetime=timezone.now() + timezone.timedelta(days=4),
            status=ServiceEvent.STATUS_PUBLISHED,
        )
        earlier_event = ServiceEvent.objects.create(
            title="Earlier Personal Service",
            title_en="Earlier Personal Service",
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
            start_datetime=timezone.now() + timezone.timedelta(days=2),
            status=ServiceEvent.STATUS_PUBLISHED,
        )
        self.create_assignment(service_event=later_event)
        self.create_assignment(service_event=earlier_event)
        self.client.login(username="regular_assign", password="testpass123")

        response = self.client.get(reverse("my_serving"))
        content = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertLess(
            content.index("Earlier Personal Service"),
            content.index("Later Personal Service"),
        )

    def test_my_serving_past_excludes_same_day_event_one_minute_in_future(self):
        self.set_language("en")
        soon_event = ServiceEvent.objects.create(
            title="Soon Today Service",
            title_en="Soon Today Service",
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
            start_datetime=timezone.now() + timezone.timedelta(minutes=1),
            status=ServiceEvent.STATUS_PUBLISHED,
        )
        assignment = self.create_assignment(service_event=soon_event)
        member = assignment.assignment_members.get(membership=self.membership)
        member.confirm()
        assignment.status = TeamAssignment.STATUS_CONFIRMED
        assignment.save()
        self.client.login(username="regular_assign", password="testpass123")

        upcoming_response = self.client.get(reverse("my_serving"))
        past_response = self.client.get(f"{reverse('my_serving')}?tab=past")

        self.assertContains(upcoming_response, "Soon Today Service")
        self.assertNotContains(past_response, "Soon Today Service")

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

    def test_my_serving_completed_current_assignment_is_not_past_before_effective_end(self):
        self.set_language("en")
        completed_event = ServiceEvent.objects.create(
            title="Completed Current Service",
            title_en="Completed Current Service",
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
            start_datetime=self.local_datetime(0, hour=0),
            status=ServiceEvent.STATUS_COMPLETED,
        )
        self.create_assignment(
            service_event=completed_event,
            status=TeamAssignment.STATUS_COMPLETED,
        )
        self.client.login(username="regular_assign", password="testpass123")

        upcoming_response = self.client.get(reverse("my_serving"))
        past_response = self.client.get(f"{reverse('my_serving')}?tab=past")

        self.assertContains(upcoming_response, "Today Serving")
        self.assertContains(upcoming_response, "Completed Current Service")
        self.assertNotContains(past_response, "Completed Current Service")

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

    def test_my_serving_shows_visible_bible_study_role_for_viewer(self):
        self.set_language("en")
        self.ensure_structure_membership()
        meeting = self.create_bible_study_meeting(title_en="Viewer Role Lesson")
        self.create_bible_study_role(
            meeting,
            BibleStudyMeetingRole.ROLE_DISCUSSION_LEADER,
            user=self.user,
        )
        self.client.login(username="regular_assign", password="testpass123")

        response = self.client.get(reverse("my_serving"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Needs Attention")
        self.assertContains(response, "Needs confirmation")
        self.assertContains(response, "Confirm Bible Study Serving")
        self.assertContains(response, "Viewer Role Lesson")
        self.assertContains(response, "Your role")
        self.assertContains(response, "Discussion Leader")
        self.assertContains(response, "View Bible Study")
        self.assertNotContains(response, "Confirm Assignment")

    def test_my_serving_team_assignment_and_ongoing_role_are_separate(self):
        # A team weekly serving assignment and an ongoing structure coworker
        # role must both render, in separate sections, with the ongoing role not
        # duplicated as a serving item.
        self.set_language("en")
        upcoming = (timezone.now() + timezone.timedelta(days=5)).replace(
            hour=19, minute=30, second=0, microsecond=0
        )
        self.event.start_datetime = upcoming
        self.event.save()
        self.create_assignment()
        edify_role = ChurchStructureUnitRoleType.objects.create(
            code=ChurchStructureUnitRoleType.CODE_EDIFY,
            name="带查经同工",
            name_en="Edify Coworker",
        )
        ChurchStructureUnitRoleAssignment.objects.create(
            unit=self.cm_unit,
            role_type=edify_role,
            user=self.user,
        )
        self.client.login(username="regular_assign", password="testpass123")

        response = self.client.get(reverse("my_serving"))

        self.assertEqual(response.status_code, 200)
        # Weekly serving still renders as before.
        self.assertContains(response, "Sunday Service")
        self.assertContains(response, "Lighting Team")
        # Ongoing role renders once in its own section.
        self.assertContains(response, "Ongoing Structure Roles", count=1)
        self.assertContains(response, "Edify Coworker", count=1)

    def test_my_serving_bible_study_role_and_ongoing_role_are_separate(self):
        # A weekly Bible Study meeting role and an ongoing structure coworker
        # role both render; the ongoing role is not duplicated as a meeting role.
        self.set_language("en")
        self.ensure_structure_membership()
        meeting = self.create_bible_study_meeting(title_en="Both Sections Lesson")
        self.create_bible_study_role(
            meeting,
            BibleStudyMeetingRole.ROLE_DISCUSSION_LEADER,
            user=self.user,
        )
        edify_role = ChurchStructureUnitRoleType.objects.create(
            code=ChurchStructureUnitRoleType.CODE_EDIFY,
            name="带查经同工",
            name_en="Edify Coworker",
        )
        ChurchStructureUnitRoleAssignment.objects.create(
            unit=self.cm_unit,
            role_type=edify_role,
            user=self.user,
        )
        self.client.login(username="regular_assign", password="testpass123")

        response = self.client.get(reverse("my_serving"))

        self.assertEqual(response.status_code, 200)
        # Weekly Bible Study role still renders as before.
        self.assertContains(response, "Both Sections Lesson")
        self.assertContains(response, "Discussion Leader")
        # Ongoing role renders once in its own section.
        self.assertContains(response, "Ongoing Structure Roles", count=1)
        self.assertContains(response, "Edify Coworker", count=1)

    def test_chinese_my_serving_bible_study_role_labels_render(self):
        self.set_language("zh")
        self.ensure_structure_membership()
        meeting = self.create_bible_study_meeting(title_en="Chinese Role Lesson")
        self.create_bible_study_role(
            meeting,
            BibleStudyMeetingRole.ROLE_DISCUSSION_LEADER,
            user=self.user,
        )
        self.client.login(username="regular_assign", password="testpass123")

        response = self.client.get(reverse("my_serving"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "查经服事")
        self.assertContains(response, "需要确认")
        self.assertContains(response, "确认查经服事")
        self.assertContains(response, "你的角色")
        self.assertContains(response, "查经带领")

    def test_my_serving_visible_bible_study_without_role_is_not_serving(self):
        self.set_language("en")
        self.ensure_structure_membership()
        self.create_bible_study_meeting(title_en="Visible No Role Lesson")
        self.client.login(username="regular_assign", password="testpass123")

        response = self.client.get(reverse("my_serving"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Visible No Role Lesson")
        self.assertNotContains(response, "Confirm Bible Study Serving")

    def test_my_serving_display_name_only_bible_study_role_is_not_serving(self):
        self.set_language("en")
        self.ensure_structure_membership()
        self.user.first_name = "Grace"
        self.user.last_name = "Lee"
        self.user.save()
        meeting = self.create_bible_study_meeting(title_en="Display Name Role Lesson")
        self.create_bible_study_role(
            meeting,
            BibleStudyMeetingRole.ROLE_DISCUSSION_LEADER,
            display_name="Grace Lee",
        )
        self.client.login(username="regular_assign", password="testpass123")

        response = self.client.get(reverse("my_serving"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Display Name Role Lesson")
        self.assertNotContains(response, "Discussion Leader")
        self.assertNotContains(response, "Confirm Bible Study Serving")

    def test_my_serving_other_users_bible_study_role_is_not_serving(self):
        self.set_language("en")
        self.ensure_structure_membership()
        meeting = self.create_bible_study_meeting(title_en="Other User Role Lesson")
        self.create_bible_study_role(
            meeting,
            BibleStudyMeetingRole.ROLE_DISCUSSION_LEADER,
            user=self.other_user,
        )
        self.client.login(username="regular_assign", password="testpass123")

        response = self.client.get(reverse("my_serving"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Other User Role Lesson")
        self.assertNotContains(response, "Discussion Leader")

    def test_my_serving_bible_study_role_requires_visible_meeting(self):
        self.set_language("en")
        meeting = self.create_bible_study_meeting(title_en="Hidden Role Lesson")
        self.create_bible_study_role(
            meeting,
            BibleStudyMeetingRole.ROLE_DISCUSSION_LEADER,
            user=self.user,
        )
        self.client.login(username="regular_assign", password="testpass123")

        response = self.client.get(reverse("my_serving"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Hidden Role Lesson")
        self.assertNotContains(response, "Discussion Leader")

    def test_my_serving_multiple_bible_study_roles_render_compactly(self):
        self.set_language("en")
        self.ensure_structure_membership()
        meeting = self.create_bible_study_meeting(title_en="Multi Role Lesson")
        self.create_bible_study_role(
            meeting,
            BibleStudyMeetingRole.ROLE_DISCUSSION_LEADER,
            user=self.user,
        )
        self.create_bible_study_role(
            meeting,
            BibleStudyMeetingRole.ROLE_WORSHIP_LEAD,
            user=self.user,
        )
        self.client.login(username="regular_assign", password="testpass123")

        response = self.client.get(reverse("my_serving"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Confirm Bible Study Serving", count=1)
        self.assertContains(response, "Multi Role Lesson")
        self.assertContains(response, "Discussion Leader")
        self.assertContains(response, "Worship Lead")

    def test_my_serving_bible_study_roles_bucket_today_this_week_and_later(self):
        self.set_language("en")
        self.ensure_structure_membership()
        today = self.create_bible_study_meeting(title_en="Today Study Serving", days_from_today=0)
        tomorrow = self.create_bible_study_meeting(title_en="Tomorrow Study Serving", days_from_today=1)
        later = self.create_bible_study_meeting(title_en="Later Study Serving", days_from_today=9)
        for meeting in [today, tomorrow, later]:
            role = self.create_bible_study_role(
                meeting,
                BibleStudyMeetingRole.ROLE_DISCUSSION_LEADER,
                user=self.user,
            )
            role.confirm()
        self.client.login(username="regular_assign", password="testpass123")

        response = self.client.get(reverse("my_serving"))
        content = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Today Serving")
        self.assertContains(response, "Today Study Serving")
        self.assertContains(response, "This Week Serving")
        self.assertContains(response, "Tomorrow Study Serving")
        self.assertContains(response, "Later")
        self.assertContains(response, "Later Study Serving")
        self.assertLess(content.index("Today Serving"), content.index("Today Study Serving"))
        self.assertLess(content.index("This Week Serving"), content.index("Tomorrow Study Serving"))
        self.assertLess(content.index("Later"), content.index("Later Study Serving"))

    def test_my_serving_bible_study_role_past_tab_uses_effective_end(self):
        self.set_language("en")
        self.ensure_structure_membership()
        ended = self.create_bible_study_meeting(
            title_en="Ended Study Serving",
            days_from_today=-1,
        )
        upcoming = self.create_bible_study_meeting(
            title_en="Upcoming Study Serving",
            days_from_today=1,
        )
        for meeting in [ended, upcoming]:
            self.create_bible_study_role(
                meeting,
                BibleStudyMeetingRole.ROLE_DISCUSSION_LEADER,
                user=self.user,
            )
        self.client.login(username="regular_assign", password="testpass123")

        upcoming_response = self.client.get(reverse("my_serving"))
        past_response = self.client.get(f"{reverse('my_serving')}?tab=past")
        all_response = self.client.get(f"{reverse('my_serving')}?tab=all")

        self.assertNotContains(upcoming_response, "Ended Study Serving")
        self.assertContains(upcoming_response, "Upcoming Study Serving")
        self.assertContains(past_response, "Ended Study Serving")
        self.assertNotContains(past_response, "Upcoming Study Serving")
        self.assertContains(all_response, "Ended Study Serving")
        self.assertContains(all_response, "Upcoming Study Serving")
        self.assertNotContains(past_response, "Confirm Bible Study Serving")

    def test_my_serving_bible_study_audience_visibility_alone_is_not_serving(self):
        self.set_language("en")
        self.ensure_structure_membership()
        self.create_bible_study_meeting(title_en="Audience Only Study")
        self.client.login(username="regular_assign", password="testpass123")

        response = self.client.get(reverse("my_serving"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Audience Only Study")
        self.assertNotContains(response, "Confirm Bible Study Serving")

    def test_confirmed_bible_study_role_shows_confirmed_state_on_my_serving(self):
        self.set_language("en")
        self.ensure_structure_membership()
        meeting = self.create_bible_study_meeting(title_en="Confirmed Role Lesson")
        role = self.create_bible_study_role(
            meeting,
            BibleStudyMeetingRole.ROLE_DISCUSSION_LEADER,
            user=self.user,
        )
        role.confirmed_at = datetime(
            2026,
            6,
            12,
            23,
            0,
            tzinfo=datetime_timezone.utc,
        )
        role.confirmation_note = "Ready."
        role.save()
        self.client.login(username="regular_assign", password="testpass123")

        response = self.client.get(reverse("my_serving"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Needs Attention")
        self.assertContains(response, "Confirmed")
        self.assertContains(response, "Confirmed At")
        confirmed_at_display = member_datetime(role.confirmed_at, "en")
        content = response.content.decode()
        confirmed_at_chunk = content[content.index("Confirmed At") : content.index("Confirmed At") + 250]
        self.assertIn(confirmed_at_display, confirmed_at_chunk)
        self.assertIn("Fri, Jun 12, 4:00 PM", confirmed_at_chunk)
        self.assertNotIn("11:00 PM", confirmed_at_chunk)
        self.assertNotContains(response, "Confirm Bible Study Serving")

    def test_user_can_confirm_own_bible_study_roles_from_my_serving(self):
        self.set_language("en")
        self.ensure_structure_membership()
        meeting = self.create_bible_study_meeting(title_en="Confirm Role Lesson")
        discussion_role = self.create_bible_study_role(
            meeting,
            BibleStudyMeetingRole.ROLE_DISCUSSION_LEADER,
            user=self.user,
        )
        worship_role = self.create_bible_study_role(
            meeting,
            BibleStudyMeetingRole.ROLE_WORSHIP_LEAD,
            user=self.user,
        )
        self.client.login(username="regular_assign", password="testpass123")

        response = self.client.post(
            reverse("confirm_bible_study_role_serving", args=[meeting.id]),
            {
                "confirmation_note": "Confirmed from My Serving.",
                "next": reverse("my_serving"),
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("my_serving"))
        discussion_role.refresh_from_db()
        worship_role.refresh_from_db()
        self.assertIsNotNone(discussion_role.confirmed_at)
        self.assertIsNotNone(worship_role.confirmed_at)
        self.assertEqual(discussion_role.confirmation_note, "Confirmed from My Serving.")
        self.assertEqual(worship_role.confirmation_note, "Confirmed from My Serving.")

        response = self.client.get(reverse("my_serving"))
        self.assertContains(response, "Confirm Role Lesson")
        self.assertContains(response, "Confirmed")
        self.assertNotContains(response, "Confirm Bible Study Serving")

    def test_user_cannot_confirm_another_users_bible_study_role(self):
        self.set_language("en")
        self.ensure_structure_membership()
        meeting = self.create_bible_study_meeting(title_en="Other User Confirm Lesson")
        role = self.create_bible_study_role(
            meeting,
            BibleStudyMeetingRole.ROLE_DISCUSSION_LEADER,
            user=self.other_user,
        )
        self.client.login(username="regular_assign", password="testpass123")

        response = self.client.post(
            reverse("confirm_bible_study_role_serving", args=[meeting.id])
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("my_serving"))
        role.refresh_from_db()
        self.assertIsNone(role.confirmed_at)

    def test_display_name_only_bible_study_role_cannot_be_confirmed(self):
        self.set_language("en")
        self.ensure_structure_membership()
        self.user.first_name = "Grace"
        self.user.last_name = "Lee"
        self.user.save()
        meeting = self.create_bible_study_meeting(title_en="Display Confirm Lesson")
        role = self.create_bible_study_role(
            meeting,
            BibleStudyMeetingRole.ROLE_DISCUSSION_LEADER,
            display_name="Grace Lee",
        )
        self.client.login(username="regular_assign", password="testpass123")

        response = self.client.post(
            reverse("confirm_bible_study_role_serving", args=[meeting.id])
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("my_serving"))
        role.refresh_from_db()
        self.assertIsNone(role.confirmed_at)

    def test_hidden_bible_study_role_cannot_be_confirmed(self):
        self.set_language("en")
        meeting = self.create_bible_study_meeting(title_en="Hidden Confirm Lesson")
        role = self.create_bible_study_role(
            meeting,
            BibleStudyMeetingRole.ROLE_DISCUSSION_LEADER,
            user=self.user,
        )
        self.client.login(username="regular_assign", password="testpass123")

        response = self.client.post(
            reverse("confirm_bible_study_role_serving", args=[meeting.id])
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("my_serving"))
        role.refresh_from_db()
        self.assertIsNone(role.confirmed_at)

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
        assignment_member.confirmed_at = datetime(
            2026,
            6,
            12,
            23,
            0,
            tzinfo=datetime_timezone.utc,
        )
        assignment_member.confirmation_note = "Ready."
        assignment_member.save()
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
        self.assertIn("Fri, Jun 12, 4:00 PM", confirmed_at_chunk)
        self.assertNotIn("11:00 PM", confirmed_at_chunk)
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

    def test_ordinary_member_does_not_see_leader_needs_attention(self):
        self.set_language("en")
        self.event.required_teams.add(self.team)
        self.client.login(username="regular_assign", password="testpass123")

        response = self.client.get(reverse("my_serving"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Leader Needs Attention")
        self.assertNotContains(response, "Review coverage")

    def test_personal_serving_without_management_does_not_show_leader_needs_attention(self):
        self.set_language("en")
        self.event.required_teams.add(self.other_team)
        self.create_assignment()
        self.client.login(username="regular_assign", password="testpass123")

        response = self.client.get(reverse("my_serving"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sunday Service")
        self.assertContains(response, "Needs confirmation")
        self.assertNotContains(response, "Leader Needs Attention")
        self.assertNotContains(response, "Sound Team")

    def test_team_lead_sees_only_own_team_leader_needs_attention(self):
        self.set_language("en")
        self.event.required_teams.add(self.team, self.other_team)
        self.client.login(username="assignment_lead", password="testpass123")

        response = self.client.get(reverse("my_serving"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Leader Needs Attention")
        self.assertContains(response, "Lighting Team")
        self.assertContains(response, "Unassigned")
        self.assertNotContains(response, "Sound Team")

    def test_team_coordinator_sees_only_own_team_leader_needs_attention(self):
        self.set_language("en")
        self.event.required_teams.add(self.team, self.other_team)
        self.client.login(username="assignment_coordinator", password="testpass123")

        response = self.client.get(reverse("my_serving"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Leader Needs Attention")
        self.assertContains(response, "Lighting Team")
        self.assertContains(response, "Unassigned")
        self.assertNotContains(response, "Sound Team")

    def test_global_assignment_manager_sees_all_leader_needs_attention(self):
        self.set_language("en")
        self.event.required_teams.add(self.team, self.other_team)
        self.client.login(username="assignment_pastor", password="testpass123")

        response = self.client.get(reverse("my_serving"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Leader Needs Attention")
        self.assertContains(response, "Lighting Team")
        self.assertContains(response, "Sound Team")
        self.assertContains(response, "Unassigned", count=2)

    def test_required_team_without_assignment_appears_in_leader_needs_attention(self):
        self.set_language("en")
        self.event.required_teams.add(self.team)
        self.client.login(username="assignment_pastor", password="testpass123")

        response = self.client.get(reverse("my_serving"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Leader Needs Attention")
        self.assertContains(response, "Sunday Service")
        self.assertContains(response, "Lighting Team")
        self.assertContains(response, "Unassigned")

    def test_empty_assignment_appears_in_leader_needs_attention(self):
        self.set_language("en")
        self.event.required_teams.add(self.team)
        TeamAssignment.objects.create(
            service_event=self.event,
            ministry_team=self.team,
            status=TeamAssignment.STATUS_SCHEDULED,
        )
        self.client.login(username="assignment_pastor", password="testpass123")

        response = self.client.get(reverse("my_serving"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Leader Needs Attention")
        self.assertContains(response, "Assignment exists, no people assigned")

    def test_unconfirmed_assignment_member_appears_in_leader_needs_attention(self):
        self.set_language("en")
        self.event.required_teams.add(self.team)
        self.create_assignment()
        self.client.login(username="assignment_pastor", password="testpass123")

        response = self.client.get(reverse("my_serving"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Leader Needs Attention")
        self.assertContains(response, "Awaiting confirmation")
        self.assertContains(response, "1 awaiting confirmation")

    def test_fully_confirmed_coverage_does_not_appear_in_leader_needs_attention(self):
        self.set_language("en")
        self.event.required_teams.add(self.team)
        assignment = self.create_assignment()
        assignment.assignment_members.get(membership=self.membership).confirm()
        assignment.status = TeamAssignment.STATUS_CONFIRMED
        assignment.save()
        self.client.login(username="assignment_pastor", password="testpass123")

        response = self.client.get(reverse("my_serving"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Leader Needs Attention")
        self.assertNotContains(response, "Review coverage")

    def test_draft_and_cancelled_events_do_not_appear_in_leader_needs_attention(self):
        self.set_language("en")
        draft_event = self.create_schedule_event(
            title_en="Draft Required Service",
            days_from_now=2,
            status=ServiceEvent.STATUS_DRAFT,
        )
        draft_event.required_teams.add(self.team)
        cancelled_event = self.create_schedule_event(
            title_en="Cancelled Required Service",
            days_from_now=3,
            status=ServiceEvent.STATUS_CANCELLED,
        )
        cancelled_event.required_teams.add(self.team)
        self.client.login(username="assignment_pastor", password="testpass123")

        response = self.client.get(reverse("my_serving"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Leader Needs Attention")
        self.assertNotContains(response, "Draft Required Service")
        self.assertNotContains(response, "Cancelled Required Service")

    def test_events_outside_near_term_window_do_not_appear_in_leader_needs_attention(self):
        self.set_language("en")
        future_event = self.create_schedule_event(
            title_en="Future Required Service",
            days_from_now=9,
        )
        future_event.required_teams.add(self.team)
        self.client.login(username="assignment_pastor", password="testpass123")

        response = self.client.get(reverse("my_serving"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Leader Needs Attention")
        self.assertNotContains(response, "Future Required Service")

    def test_leader_needs_attention_hidden_on_past_tab(self):
        self.set_language("en")
        self.event.required_teams.add(self.team)
        self.client.login(username="assignment_pastor", password="testpass123")

        response = self.client.get(f"{reverse('my_serving')}?tab=past")

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Leader Needs Attention")
        self.assertNotContains(response, "Review coverage")

    def test_leader_needs_attention_action_links_to_team_schedule(self):
        self.set_language("en")
        self.event.required_teams.add(self.team)
        self.client.login(username="assignment_lead", password="testpass123")

        response = self.client.get(reverse("my_serving"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("team_schedule", args=[self.team.id]))
        self.assertContains(response, f"event={self.event.id}")

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

    def test_ongoing_assignment_appears_in_upcoming_not_past_assignment_tab(self):
        self.set_language("en")
        current_event = ServiceEvent.objects.create(
            title="Ongoing Assignment Service",
            title_en="Ongoing Assignment Service",
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
            start_datetime=self.local_datetime(0, hour=0),
            status=ServiceEvent.STATUS_PUBLISHED,
        )
        self.create_assignment(service_event=current_event)
        self.client.login(username="assignment_pastor", password="testpass123")

        upcoming = self.client.get(reverse("team_assignment_list"), {"tab": "upcoming"})
        past = self.client.get(reverse("team_assignment_list"), {"tab": "past"})

        self.assertContains(upcoming, "Ongoing Assignment Service")
        self.assertNotContains(past, "Ongoing Assignment Service")

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

    def test_import_does_not_create_assignment_for_non_assignable_existing_team(self):
        # MINISTRY-STRUCTURE.1F: a reused lighting team that was set to
        # non-assignable must not receive a new serving assignment. The row
        # fails closed and its per-row work rolls back; no assignment is created.
        MinistryTeam.objects.create(
            name="灯光组",
            name_en="Lighting Team",
            is_assignable=False,
        )
        csv_path = self.write_csv(self.csv_content())

        output = self.run_import(csv_path)

        self.assertIn("assignments_created=0", output)
        self.assertIn("rows_errors=1", output)
        self.assertEqual(TeamAssignment.objects.count(), 0)
        self.assertEqual(TeamAssignmentMember.objects.count(), 0)
        # The container team itself is preserved; nothing was assigned to it.
        self.assertTrue(
            MinistryTeam.objects.filter(name="灯光组", is_assignable=False).exists()
        )

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


class MyServingOngoingStructureRoleTests(TestCase):
    """MYSERVING-STRUCTROLE.1A: read-only "Ongoing Structure Roles" section.

    These cover the new My Serving section that surfaces a user's OWN active
    long-term ``ChurchStructureUnitRoleAssignment`` rows (ongoing structure
    coworker roles). The section is conceptually separate from this-week serving
    (``TeamAssignmentMember`` / ``BibleStudyMeetingRole``) and from belonging
    (``ChurchStructureMembership``); none of those imply an ongoing role here.
    """

    def setUp(self):
        self.today = timezone.localdate()
        self.user = User.objects.create_user(
            username="ongoing_viewer",
            email="ongoing-viewer@example.com",
            password="testpass123",
        )
        self.other = User.objects.create_user(
            username="ongoing_other",
            email="ongoing-other@example.com",
            password="testpass123",
        )

        self.lead_role = ChurchStructureUnitRoleType.objects.create(
            code=ChurchStructureUnitRoleType.CODE_LEAD,
            name="负责人",
            name_en="Lead",
        )
        self.edify_role = ChurchStructureUnitRoleType.objects.create(
            code=ChurchStructureUnitRoleType.CODE_EDIFY,
            name="带查经同工",
            name_en="Edify",
        )
        self.worship_role = ChurchStructureUnitRoleType.objects.create(
            code=ChurchStructureUnitRoleType.CODE_WORSHIP,
            name="敬拜同工",
            name_en="Worship",
        )

        self.district = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_DISTRICT,
            code="OSR-DISTRICT",
            name="负责区",
            name_en="Lead District",
        )
        self.group = ChurchStructureUnit.objects.create(
            parent=self.district,
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="OSR-GROUP",
            name="小组A",
            name_en="Group A",
        )

    def set_language(self, language="en"):
        session = self.client.session
        session["language"] = language
        session.save()

    def _assign(self, user, unit, role_type, **kwargs):
        return ChurchStructureUnitRoleAssignment.objects.create(
            unit=unit,
            role_type=role_type,
            user=user,
            **kwargs,
        )

    def _login_viewer(self):
        self.client.login(username="ongoing_viewer", password="testpass123")

    # --- visibility of own active roles ---------------------------------------

    def test_active_lead_role_shows_section(self):
        self.set_language("en")
        self._assign(self.user, self.group, self.lead_role)
        self._login_viewer()

        response = self.client.get(reverse("my_serving"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ongoing Structure Roles")
        self.assertContains(
            response,
            "This is an ongoing structure role, not a weekly serving assignment.",
        )

    def test_active_edify_role_shows_role(self):
        self.set_language("en")
        self._assign(self.user, self.group, self.edify_role)
        self._login_viewer()

        response = self.client.get(reverse("my_serving"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ongoing Structure Roles")
        self.assertContains(response, "Edify")

    def test_english_role_and_unit_path_render(self):
        self.set_language("en")
        self._assign(self.user, self.group, self.worship_role)
        self._login_viewer()

        response = self.client.get(reverse("my_serving"))

        self.assertContains(response, "Worship")
        self.assertContains(response, "Lead District &gt; Group A")

    def test_chinese_role_and_unit_path_render(self):
        self.set_language("zh")
        self._assign(self.user, self.group, self.worship_role)
        self._login_viewer()

        response = self.client.get(reverse("my_serving"))

        self.assertContains(response, "长期同工角色")
        self.assertContains(response, "敬拜同工")
        self.assertContains(response, "负责区 &gt; 小组A")

    # --- inactive / expired / future / scope exclusions -----------------------

    def test_inactive_assignment_not_shown(self):
        self.set_language("en")
        self._assign(self.user, self.group, self.lead_role, is_active=False)
        self._login_viewer()

        response = self.client.get(reverse("my_serving"))

        self.assertNotContains(response, "Ongoing Structure Roles")

    def test_expired_assignment_not_shown(self):
        self.set_language("en")
        self._assign(
            self.user,
            self.group,
            self.lead_role,
            start_date=self.today - timezone.timedelta(days=30),
            end_date=self.today - timezone.timedelta(days=1),
        )
        self._login_viewer()

        response = self.client.get(reverse("my_serving"))

        self.assertNotContains(response, "Ongoing Structure Roles")

    def test_future_assignment_not_shown(self):
        self.set_language("en")
        self._assign(
            self.user,
            self.group,
            self.lead_role,
            start_date=self.today + timezone.timedelta(days=5),
        )
        self._login_viewer()

        response = self.client.get(reverse("my_serving"))

        self.assertNotContains(response, "Ongoing Structure Roles")

    def test_assignment_on_inactive_unit_not_shown(self):
        self.set_language("en")
        self._assign(self.user, self.group, self.lead_role)
        # Deactivate the unit after the (valid, active) assignment exists.
        self.group.is_active = False
        self.group.save()
        self._login_viewer()

        response = self.client.get(reverse("my_serving"))

        self.assertNotContains(response, "Ongoing Structure Roles")

    def test_inactive_role_type_assignment_not_shown(self):
        self.set_language("en")
        self._assign(self.user, self.group, self.edify_role)
        # Deactivate the role type after the (valid, active) assignment exists.
        self.edify_role.is_active = False
        self.edify_role.save()
        self._login_viewer()

        response = self.client.get(reverse("my_serving"))

        self.assertNotContains(response, "Ongoing Structure Roles")

    def test_other_users_assignment_not_shown(self):
        self.set_language("en")
        self._assign(self.other, self.group, self.lead_role)
        self._login_viewer()

        response = self.client.get(reverse("my_serving"))

        self.assertNotContains(response, "Ongoing Structure Roles")

    # --- belonging / capability are not ongoing roles -------------------------

    def test_membership_alone_does_not_create_ongoing_role(self):
        self.set_language("en")
        ChurchStructureMembership.objects.create(
            user=self.user,
            unit=self.group,
            status=ChurchStructureMembership.STATUS_ACTIVE,
            is_primary=True,
            start_date=self.today,
        )
        self._login_viewer()

        response = self.client.get(reverse("my_serving"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Ongoing Structure Roles")

    def test_church_role_assignment_alone_does_not_create_ongoing_role(self):
        self.set_language("en")
        ChurchRoleAssignment.objects.create(
            user=self.user,
            role=ChurchRoleAssignment.ROLE_GROUP_LEADER,
            scope_type=ChurchRoleAssignment.SCOPE_GLOBAL,
        )
        self._login_viewer()

        response = self.client.get(reverse("my_serving"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Ongoing Structure Roles")

    # --- management link gating ----------------------------------------------

    def test_lead_role_exposes_manage_unit_link(self):
        self.set_language("en")
        self._assign(self.user, self.group, self.lead_role)
        self._login_viewer()

        response = self.client.get(reverse("my_serving"))

        self.assertContains(response, "Manage unit coworkers")
        self.assertContains(response, reverse("my_unit_detail", args=[self.group.id]))

    def test_non_lead_coworker_role_has_no_manage_link(self):
        self.set_language("en")
        self._assign(self.user, self.group, self.edify_role)
        self._login_viewer()

        response = self.client.get(reverse("my_serving"))

        self.assertContains(response, "Ongoing Structure Roles")
        self.assertNotContains(response, "Manage unit coworkers")

    def test_section_exposes_no_staff_structure_links(self):
        self.set_language("en")
        self._assign(self.user, self.group, self.edify_role)
        self._login_viewer()

        response = self.client.get(reverse("my_serving"))

        self.assertNotContains(response, "/staff/structure/")

    # --- empty access ---------------------------------------------------------

    def test_user_without_ongoing_roles_still_accesses_my_serving(self):
        self.set_language("en")
        self._login_viewer()

        response = self.client.get(reverse("my_serving"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Ongoing Structure Roles")


class ServingReadinessMinistryWarningTests(TestCase):
    """SERVING-READINESS.1C warning integration on ministry serving surfaces.

    Covers ministry ``TeamMembership`` (manage/edit) and weekly
    ``TeamAssignmentMember`` (create/edit) surfaces. Warnings are advisory and
    warning-only: linked-user saves still succeed, display-name-only rows are not
    evaluated, no policy preserves prior behavior, and ordinary My Serving never
    shows readiness warnings.
    """

    def setUp(self):
        self.manager = User.objects.create_user(
            username="readiness_pastor",
            email="readiness-pastor@example.com",
            password="pw",
        )
        ChurchRoleAssignment.objects.create(
            user=self.manager,
            role=ChurchRoleAssignment.ROLE_PASTOR,
            scope_type=ChurchRoleAssignment.SCOPE_GLOBAL,
        )
        self.member = User.objects.create_user(
            username="readiness_member", email="rm@example.com", password="pw"
        )
        self.team = MinistryTeam.objects.create(name="灯光", name_en="Lighting")
        self.event = ServiceEvent.objects.create(
            title="主日崇拜",
            title_en="Sunday Service",
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
            start_datetime=timezone.now() + timezone.timedelta(days=2),
            status=ServiceEvent.STATUS_PUBLISHED,
        )

    # --- helpers ---------------------------------------------------------------

    def set_language(self, language="en"):
        session = self.client.session
        session["language"] = language
        session.save()

    def _seed_policy(self):
        call_command(
            "seed_serving_readiness_policies", "--apply", stdout=StringIO()
        )

    def _make_record(self, user, **kwargs):
        return ChurchMemberRecord.objects.create(user=user, **kwargs)

    def _readiness_messages(self, response):
        return [
            message.message
            for message in get_messages(response.wsgi_request)
            if "Serving readiness warning" in message.message
            or "服事预备提醒" in message.message
        ]

    def _login_manager(self):
        self.set_language("en")
        self.client.login(username="readiness_pastor", password="pw")

    def _membership_post(self, **overrides):
        data = {
            "user": self.member.id,
            "display_name": "",
            "email": "",
            "role": TeamMembership.ROLE_MEMBER,
            "skill_level": "",
            "notes": "",
            "is_active": "on",
        }
        data.update(overrides)
        return self.client.post(
            reverse("manage_team_members", args=[self.team.id]), data
        )

    # --- C. TeamMembership -----------------------------------------------------

    def test_membership_linked_user_unready_warns_and_saves(self):
        self._seed_policy()
        self._login_manager()
        response = self._membership_post()
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            TeamMembership.objects.filter(team=self.team, user=self.member).exists()
        )
        self.assertTrue(self._readiness_messages(response))

    def test_membership_linked_user_ready_does_not_warn(self):
        self._seed_policy()
        self._make_record(
            self.member,
            faith_statement_status=ChurchMemberRecord.FAITH_STATEMENT_SIGNED,
            baptism_status=ChurchMemberRecord.BAPTISM_BAPTIZED,
        )
        self._login_manager()
        response = self._membership_post()
        self.assertTrue(
            TeamMembership.objects.filter(team=self.team, user=self.member).exists()
        )
        self.assertEqual(self._readiness_messages(response), [])

    def test_display_name_only_membership_does_not_warn(self):
        self._seed_policy()
        self._login_manager()
        response = self._membership_post(
            user="", display_name="Guest Helper", email="guest@example.com"
        )
        self.assertTrue(
            TeamMembership.objects.filter(
                team=self.team, display_name="Guest Helper"
            ).exists()
        )
        self.assertEqual(self._readiness_messages(response), [])

    def test_membership_no_policy_preserves_previous_behavior(self):
        self._login_manager()
        response = self._membership_post()
        self.assertTrue(
            TeamMembership.objects.filter(team=self.team, user=self.member).exists()
        )
        self.assertEqual(self._readiness_messages(response), [])

    def test_membership_save_not_blocked_by_unready(self):
        self._seed_policy()
        self._make_record(
            self.member,
            faith_statement_status=ChurchMemberRecord.FAITH_STATEMENT_DECLINED,
            baptism_status=ChurchMemberRecord.BAPTISM_NOT_BAPTIZED,
        )
        self._login_manager()
        response = self._membership_post()
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            TeamMembership.objects.filter(team=self.team, user=self.member).exists()
        )

    def test_membership_warning_does_not_create_member_record(self):
        self._seed_policy()
        self._login_manager()
        before = ChurchMemberRecord.objects.count()
        self._membership_post()
        self.assertEqual(ChurchMemberRecord.objects.count(), before)

    # --- D. TeamAssignmentMember -----------------------------------------------

    def _assignment_post(self, membership, **overrides):
        data = {
            "service_event": self.event.id,
            "ministry_team": self.team.id,
            "assigned_members": [membership.id],
            "status": TeamAssignment.STATUS_SCHEDULED,
            "notes": "Operational note.",
        }
        data.update(overrides)
        return self.client.post(reverse("create_team_assignment"), data)

    def test_assignment_member_linked_unready_warns_and_saves(self):
        self._seed_policy()
        membership = TeamMembership.objects.create(
            team=self.team, user=self.member, role=TeamMembership.ROLE_MEMBER
        )
        self._login_manager()
        response = self._assignment_post(membership)
        self.assertEqual(response.status_code, 302)
        assignment = TeamAssignment.objects.get(ministry_team=self.team)
        self.assertEqual(assignment.assigned_members.count(), 1)
        self.assertTrue(self._readiness_messages(response))

    def test_assignment_member_linked_ready_does_not_warn(self):
        self._seed_policy()
        self._make_record(
            self.member,
            faith_statement_status=ChurchMemberRecord.FAITH_STATEMENT_SIGNED,
            baptism_status=ChurchMemberRecord.BAPTISM_BAPTIZED,
        )
        membership = TeamMembership.objects.create(
            team=self.team, user=self.member, role=TeamMembership.ROLE_MEMBER
        )
        self._login_manager()
        response = self._assignment_post(membership)
        self.assertEqual(TeamAssignmentMember.objects.count(), 1)
        self.assertEqual(self._readiness_messages(response), [])

    def test_assignment_display_name_only_member_does_not_warn(self):
        self._seed_policy()
        membership = TeamMembership.objects.create(
            team=self.team,
            display_name="Guest Helper",
            role=TeamMembership.ROLE_MEMBER,
        )
        self._login_manager()
        response = self._assignment_post(membership)
        self.assertEqual(TeamAssignmentMember.objects.count(), 1)
        self.assertEqual(self._readiness_messages(response), [])

    def test_assignment_confirmation_behavior_unchanged(self):
        # The warning path must not alter that members are synced onto the
        # assignment row (no extra/missing TeamAssignmentMember rows).
        self._seed_policy()
        membership = TeamMembership.objects.create(
            team=self.team, user=self.member, role=TeamMembership.ROLE_MEMBER
        )
        self._login_manager()
        self._assignment_post(membership)
        assignment = TeamAssignment.objects.get(ministry_team=self.team)
        self.assertEqual(
            list(
                assignment.assignment_members.values_list("membership_id", flat=True)
            ),
            [membership.id],
        )
        self.assertIsNone(assignment.assignment_members.first().confirmed_at)

    def test_ordinary_my_serving_does_not_show_readiness_warnings(self):
        self._seed_policy()
        membership = TeamMembership.objects.create(
            team=self.team, user=self.member, role=TeamMembership.ROLE_MEMBER
        )
        assignment = TeamAssignment.objects.create(
            service_event=self.event,
            ministry_team=self.team,
            status=TeamAssignment.STATUS_SCHEDULED,
            created_by=self.manager,
        )
        TeamAssignmentMember.objects.create(
            assignment=assignment, membership=membership
        )
        self.set_language("en")
        self.client.login(username="readiness_member", password="pw")
        response = self.client.get(reverse("my_serving"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Serving readiness warning")
        self.assertNotContains(response, "服事预备提醒")


class MinistryStructureFoundationTests(TestCase):
    """MINISTRY-STRUCTURE.1B model foundation tests (additive, no runtime change)."""

    def setUp(self):
        self.user = User.objects.create_user(username="ms_user", password="pw")
        self.other_user = User.objects.create_user(username="ms_other", password="pw")
        self.area = MinistryTeam.objects.create(
            name="数字事工",
            name_en="Digital Ministry",
            team_kind=MinistryTeam.KIND_MINISTRY_AREA,
            is_assignable=False,
        )
        self.team = MinistryTeam.objects.create(
            name="投影团队", name_en="Projection Team"
        )
        self.church_unit = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_MINISTRY_CONTEXT,
            code="CM",
            name="华语",
            name_en="CM",
        )

    # --- MinistryTeam field/default tests ---

    def test_existing_team_defaults_to_team_kind_and_assignable(self):
        team = MinistryTeam.objects.create(name="新团队", name_en="New Team")
        team.refresh_from_db()
        self.assertEqual(team.team_kind, MinistryTeam.KIND_TEAM)
        self.assertTrue(team.is_assignable)
        self.assertIsNone(team.role_profile)

    def test_role_profile_may_be_null_and_set(self):
        profile = MinistryTeamRoleProfile.objects.create(
            code="default_ministry_unit", name="默认", name_en="Default"
        )
        self.team.role_profile = profile
        self.team.save()
        self.team.refresh_from_db()
        self.assertEqual(self.team.role_profile_id, profile.id)

    def test_is_assignable_false_does_not_change_team_assignment_behavior(self):
        # Foundation slice: a non-assignable team can still be used to create a
        # TeamAssignment at the model level (enforcement is a later slice).
        event = ServiceEvent.objects.create(
            title="Service",
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
            start_datetime=timezone.now() + timezone.timedelta(days=1),
            status=ServiceEvent.STATUS_PUBLISHED,
        )
        assignment = TeamAssignment.objects.create(
            service_event=event,
            ministry_team=self.area,  # is_assignable=False
            status=TeamAssignment.STATUS_SCHEDULED,
        )
        self.assertEqual(assignment.ministry_team_id, self.area.id)

    # --- Parent link tests ---

    def test_parent_link_accepts_single_team_target(self):
        link = MinistryTeamParentLink.objects.create(
            child_team=self.team, parent_team=self.area, is_primary=True
        )
        self.assertEqual(link.parent_team_id, self.area.id)
        self.assertIsNone(link.parent_church_unit_id)

    def test_parent_link_accepts_single_church_anchor_target(self):
        link = MinistryTeamParentLink.objects.create(
            child_team=self.area, parent_church_unit=self.church_unit, is_primary=True
        )
        self.assertEqual(link.parent_church_unit_id, self.church_unit.id)

    def test_parent_link_rejects_no_target(self):
        with self.assertRaises(ValidationError):
            MinistryTeamParentLink(child_team=self.team).save()

    def test_parent_link_rejects_both_targets(self):
        with self.assertRaises(ValidationError):
            MinistryTeamParentLink(
                child_team=self.team,
                parent_team=self.area,
                parent_church_unit=self.church_unit,
            ).save()

    def test_parent_link_rejects_self_parent(self):
        with self.assertRaises(ValidationError):
            MinistryTeamParentLink(
                child_team=self.team, parent_team=self.team
            ).save()

    def test_parent_link_rejects_cycle(self):
        # area <- team (team's parent is area)
        MinistryTeamParentLink.objects.create(
            child_team=self.team, parent_team=self.area
        )
        # area's parent = team would close a cycle
        with self.assertRaises(ValidationError):
            MinistryTeamParentLink(
                child_team=self.area, parent_team=self.team
            ).save()

    def test_parent_link_rejects_duplicate_active_team_link(self):
        MinistryTeamParentLink.objects.create(
            child_team=self.team, parent_team=self.area
        )
        with self.assertRaises(ValidationError):
            MinistryTeamParentLink(
                child_team=self.team, parent_team=self.area
            ).save()

    def test_parent_link_rejects_duplicate_active_church_anchor(self):
        MinistryTeamParentLink.objects.create(
            child_team=self.team, parent_church_unit=self.church_unit
        )
        with self.assertRaises(ValidationError):
            MinistryTeamParentLink(
                child_team=self.team, parent_church_unit=self.church_unit
            ).save()

    def test_parent_link_rejects_two_active_primary_links(self):
        MinistryTeamParentLink.objects.create(
            child_team=self.team, parent_team=self.area, is_primary=True
        )
        with self.assertRaises(ValidationError):
            MinistryTeamParentLink(
                child_team=self.team,
                parent_church_unit=self.church_unit,
                is_primary=True,
            ).save()

    def test_parent_link_allows_multiple_active_non_primary(self):
        second_area = MinistryTeam.objects.create(
            name="网络宣教", name_en="Internet Mission"
        )
        MinistryTeamParentLink.objects.create(
            child_team=self.team, parent_team=self.area, is_primary=True
        )
        link2 = MinistryTeamParentLink.objects.create(
            child_team=self.team, parent_team=second_area, is_primary=False
        )
        self.assertEqual(self.team.active_parent_links().count(), 2)
        self.assertEqual(self.team.primary_parent_link().parent_team_id, self.area.id)
        self.assertFalse(link2.is_primary)

    def test_display_path_includes_church_anchor(self):
        # CM (church) <- Digital Ministry (area) <- Projection Team (team)
        MinistryTeamParentLink.objects.create(
            child_team=self.area, parent_church_unit=self.church_unit, is_primary=True
        )
        MinistryTeamParentLink.objects.create(
            child_team=self.team, parent_team=self.area, is_primary=True
        )
        path = self.team.display_path_label("en")
        self.assertEqual(path, "CM > Digital Ministry > Projection Team")
        self.assertEqual(self.team.primary_church_anchor().id, self.church_unit.id)
        self.assertEqual(
            [a.id for a in self.team.get_ministry_ancestors()], [self.area.id]
        )

    def test_parent_link_creates_no_membership_or_serving_objects(self):
        MinistryTeamParentLink.objects.create(
            child_team=self.team, parent_church_unit=self.church_unit
        )
        self.assertEqual(TeamMembership.objects.count(), 0)
        self.assertEqual(TeamAssignment.objects.count(), 0)
        self.assertEqual(TeamAssignmentMember.objects.count(), 0)
        self.assertEqual(ChurchStructureMembership.objects.count(), 0)
        self.assertEqual(ChurchStructureUnitRoleAssignment.objects.count(), 0)

    # --- Role type / profile / requirement tests ---

    def test_role_type_code_is_normalized_and_unique(self):
        rt = MinistryTeamRoleType.objects.create(
            code="  LEAD  ", name="负责人", name_en="Lead"
        )
        self.assertEqual(rt.code, "lead")
        with self.assertRaises(ValidationError):
            MinistryTeamRoleType(code="lead", name="dup", name_en="Dup").save()

    def test_role_profile_code_is_normalized_and_unique(self):
        profile = MinistryTeamRoleProfile.objects.create(
            code="  Technical_Team ", name="技术", name_en="Technical"
        )
        self.assertEqual(profile.code, "technical_team")
        with self.assertRaises(ValidationError):
            MinistryTeamRoleProfile(code="technical_team", name="d", name_en="D").save()

    def _seed_lead_profile(self):
        profile = MinistryTeamRoleProfile.objects.create(
            code="default_ministry_unit", name="默认", name_en="Default"
        )
        lead = MinistryTeamRoleType.objects.create(
            code="lead", name="负责人", name_en="Lead"
        )
        MinistryTeamRoleRequirement.objects.create(
            profile=profile, role_type=lead, is_required=True
        )
        return profile, lead

    def test_missing_required_role_types_reports_missing_lead(self):
        profile, lead = self._seed_lead_profile()
        self.team.role_profile = profile
        self.team.save()
        missing = self.team.missing_required_role_types()
        self.assertEqual([rt.id for rt in missing], [lead.id])

    def test_missing_required_role_types_empty_when_lead_assigned(self):
        profile, lead = self._seed_lead_profile()
        self.team.role_profile = profile
        self.team.save()
        MinistryTeamRoleAssignment.objects.create(
            team=self.team, role_type=lead, user=self.user
        )
        self.assertEqual(self.team.missing_required_role_types(), [])

    def test_missing_required_role_is_readiness_only_and_does_not_block_save(self):
        profile, _lead = self._seed_lead_profile()
        self.team.role_profile = profile
        # Saving a team with a missing required role must not raise.
        self.team.save()
        self.team.refresh_from_db()
        self.assertTrue(self.team.missing_required_role_types())

    # --- Role assignment tests ---

    def test_multiple_active_leads_allowed_for_different_users(self):
        lead = MinistryTeamRoleType.objects.create(
            code="lead", name="负责人", name_en="Lead"
        )
        a1 = MinistryTeamRoleAssignment.objects.create(
            team=self.team, role_type=lead, user=self.user
        )
        a2 = MinistryTeamRoleAssignment.objects.create(
            team=self.team, role_type=lead, user=self.other_user
        )
        self.assertTrue(a1.is_active and a2.is_active)
        self.assertEqual(
            MinistryTeamRoleAssignment.objects.filter(
                team=self.team, role_type=lead, is_active=True
            ).count(),
            2,
        )

    def test_overlapping_duplicate_assignment_rejected(self):
        lead = MinistryTeamRoleType.objects.create(
            code="lead", name="负责人", name_en="Lead"
        )
        MinistryTeamRoleAssignment.objects.create(
            team=self.team, role_type=lead, user=self.user
        )
        with self.assertRaises(ValidationError):
            MinistryTeamRoleAssignment(
                team=self.team, role_type=lead, user=self.user
            ).save()

    def test_non_overlapping_historical_assignment_allowed(self):
        lead = MinistryTeamRoleType.objects.create(
            code="lead", name="负责人", name_en="Lead"
        )
        today = timezone.localdate()
        MinistryTeamRoleAssignment.objects.create(
            team=self.team,
            role_type=lead,
            user=self.user,
            start_date=today - timezone.timedelta(days=30),
            end_date=today - timezone.timedelta(days=10),
        )
        # A new active window starting after the closed one is allowed.
        new_assignment = MinistryTeamRoleAssignment.objects.create(
            team=self.team,
            role_type=lead,
            user=self.user,
            start_date=today,
        )
        self.assertTrue(new_assignment.pk)

    def test_inactive_assignment_does_not_satisfy_missing_required_role(self):
        profile, lead = self._seed_lead_profile()
        self.team.role_profile = profile
        self.team.save()
        MinistryTeamRoleAssignment.objects.create(
            team=self.team, role_type=lead, user=self.user, is_active=False
        )
        self.assertEqual(
            [rt.id for rt in self.team.missing_required_role_types()], [lead.id]
        )

    def test_active_assignment_requires_active_team_role_user(self):
        lead = MinistryTeamRoleType.objects.create(
            code="lead", name="负责人", name_en="Lead"
        )
        inactive_team = MinistryTeam.objects.create(
            name="停用", name_en="Inactive", is_active=False
        )
        with self.assertRaises(ValidationError):
            MinistryTeamRoleAssignment(
                team=inactive_team, role_type=lead, user=self.user
            ).save()

    def test_end_date_before_start_date_rejected(self):
        lead = MinistryTeamRoleType.objects.create(
            code="lead", name="负责人", name_en="Lead"
        )
        today = timezone.localdate()
        with self.assertRaises(ValidationError):
            MinistryTeamRoleAssignment(
                team=self.team,
                role_type=lead,
                user=self.user,
                start_date=today,
                end_date=today - timezone.timedelta(days=1),
            ).save()

    def test_role_assignment_creates_no_team_membership(self):
        lead = MinistryTeamRoleType.objects.create(
            code="lead", name="负责人", name_en="Lead"
        )
        MinistryTeamRoleAssignment.objects.create(
            team=self.team, role_type=lead, user=self.user
        )
        self.assertEqual(TeamMembership.objects.count(), 0)

    def test_role_assignment_does_not_drive_can_manage_ministry_team(self):
        # A lead role assignment must NOT grant management; permission still
        # comes from TeamMembership.role (none here), so the user cannot manage.
        lead = MinistryTeamRoleType.objects.create(
            code="lead", name="负责人", name_en="Lead"
        )
        MinistryTeamRoleAssignment.objects.create(
            team=self.team, role_type=lead, user=self.user
        )
        self.assertFalse(can_manage_ministry_team(self.user, self.team))

    def test_team_membership_lead_still_grants_management(self):
        # Existing permission source unchanged: a TeamMembership lead can manage.
        TeamMembership.objects.create(
            team=self.team, user=self.user, role=TeamMembership.ROLE_LEAD
        )
        self.assertTrue(can_manage_ministry_team(self.user, self.team))


class MinistryStructureRoleSeedTests(TestCase):
    """MINISTRY-STRUCTURE.1E seed_ministry_structure_roles command tests.

    The command seeds configuration records only (role types / profiles /
    requirements). It must not assign users to ministry roles, must not create
    or update ministry teams / parent links / memberships / serving
    assignments, and must not assign a profile to any existing team.
    """

    EXPECTED_ROLE_TYPES = 10
    EXPECTED_PROFILES = 5
    EXPECTED_REQUIREMENTS = 14

    def call_seed_command(self, *args):
        output = StringIO()
        call_command("seed_ministry_structure_roles", *args, stdout=output)
        return output.getvalue()

    def test_dry_run_writes_nothing(self):
        output = self.call_seed_command()

        self.assertIn("Ministry structure role seed mode: DRY RUN", output)
        self.assertIn("Would create role type lead", output)
        self.assertEqual(MinistryTeamRoleType.objects.count(), 0)
        self.assertEqual(MinistryTeamRoleProfile.objects.count(), 0)
        self.assertEqual(MinistryTeamRoleRequirement.objects.count(), 0)

    def test_apply_creates_expected_role_types(self):
        output = self.call_seed_command("--apply")

        self.assertIn("Ministry structure role seed mode: APPLY", output)
        self.assertEqual(
            MinistryTeamRoleType.objects.count(), self.EXPECTED_ROLE_TYPES
        )
        expected_codes = {
            MinistryTeamRoleType.CODE_LEAD,
            MinistryTeamRoleType.CODE_ASSISTANT_LEAD,
            MinistryTeamRoleType.CODE_COORDINATOR,
            MinistryTeamRoleType.CODE_SCHEDULER,
            MinistryTeamRoleType.CODE_TRAINER,
            MinistryTeamRoleType.CODE_TECHNICAL_LEAD,
            MinistryTeamRoleType.CODE_EQUIPMENT_MANAGER,
            MinistryTeamRoleType.CODE_MEMBER_CARE,
            MinistryTeamRoleType.CODE_ADMIN,
            "custom",
        }
        self.assertEqual(
            set(MinistryTeamRoleType.objects.values_list("code", flat=True)),
            expected_codes,
        )
        lead = MinistryTeamRoleType.objects.get(
            code=MinistryTeamRoleType.CODE_LEAD
        )
        self.assertTrue(lead.is_system_default)
        self.assertTrue(lead.is_active)

    def test_apply_creates_expected_profiles(self):
        self.call_seed_command("--apply")

        self.assertEqual(
            MinistryTeamRoleProfile.objects.count(), self.EXPECTED_PROFILES
        )
        expected_codes = {
            MinistryTeamRoleProfile.CODE_DEFAULT_MINISTRY_UNIT,
            MinistryTeamRoleProfile.CODE_TECHNICAL_TEAM,
            MinistryTeamRoleProfile.CODE_WORSHIP_RELATED_TEAM,
            MinistryTeamRoleProfile.CODE_PROJECT_TEAM,
            MinistryTeamRoleProfile.CODE_CUSTOM,
        }
        self.assertEqual(
            set(MinistryTeamRoleProfile.objects.values_list("code", flat=True)),
            expected_codes,
        )
        for profile in MinistryTeamRoleProfile.objects.all():
            self.assertTrue(profile.is_system_default)
            self.assertTrue(profile.is_active)

    def test_apply_seeds_lead_requirement_for_every_profile(self):
        self.call_seed_command("--apply")

        lead = MinistryTeamRoleType.objects.get(
            code=MinistryTeamRoleType.CODE_LEAD
        )
        for profile in MinistryTeamRoleProfile.objects.all():
            self.assertTrue(
                MinistryTeamRoleRequirement.objects.filter(
                    profile=profile,
                    role_type=lead,
                    is_required=True,
                    is_active=True,
                ).exists(),
                msg=f"{profile.code} must require Lead",
            )

    def test_only_lead_is_required_by_default(self):
        self.call_seed_command("--apply")

        required_codes = set(
            MinistryTeamRoleRequirement.objects.filter(
                is_required=True, is_active=True
            ).values_list("role_type__code", flat=True)
        )
        self.assertEqual(required_codes, {MinistryTeamRoleType.CODE_LEAD})

        # Recommended optional requirements exist but are not required.
        technical = MinistryTeamRoleProfile.objects.get(
            code=MinistryTeamRoleProfile.CODE_TECHNICAL_TEAM
        )
        optional_codes = set(
            MinistryTeamRoleRequirement.objects.filter(
                profile=technical, is_required=False, is_active=True
            ).values_list("role_type__code", flat=True)
        )
        self.assertEqual(
            optional_codes,
            {
                MinistryTeamRoleType.CODE_TECHNICAL_LEAD,
                MinistryTeamRoleType.CODE_EQUIPMENT_MANAGER,
                MinistryTeamRoleType.CODE_TRAINER,
            },
        )

    def test_apply_is_idempotent(self):
        self.call_seed_command("--apply")
        second_dry_run = self.call_seed_command()
        second_apply = self.call_seed_command("--apply")

        self.assertIn(
            f"role types skipped: {self.EXPECTED_ROLE_TYPES}", second_dry_run
        )
        self.assertIn(
            f"profiles skipped: {self.EXPECTED_PROFILES}", second_dry_run
        )
        self.assertIn(
            f"requirements skipped: {self.EXPECTED_REQUIREMENTS}", second_dry_run
        )
        self.assertIn(
            f"role types skipped: {self.EXPECTED_ROLE_TYPES}", second_apply
        )
        self.assertEqual(
            MinistryTeamRoleType.objects.count(), self.EXPECTED_ROLE_TYPES
        )
        self.assertEqual(
            MinistryTeamRoleProfile.objects.count(), self.EXPECTED_PROFILES
        )
        self.assertEqual(
            MinistryTeamRoleRequirement.objects.count(),
            self.EXPECTED_REQUIREMENTS,
        )

    def test_apply_updates_stale_system_default_labels(self):
        self.call_seed_command("--apply")
        lead = MinistryTeamRoleType.objects.get(
            code=MinistryTeamRoleType.CODE_LEAD
        )
        lead.name_en = "Stale Label"
        lead.sort_order = 999
        # Bypass the seed path to simulate drift on a system-default record.
        MinistryTeamRoleType.objects.filter(pk=lead.pk).update(
            name_en="Stale Label", sort_order=999
        )

        output = self.call_seed_command("--apply")

        self.assertIn("Updated role type lead", output)
        lead.refresh_from_db()
        self.assertEqual(lead.name_en, "Lead")
        self.assertEqual(lead.sort_order, 10)

    def test_apply_does_not_delete_custom_records(self):
        custom_type = MinistryTeamRoleType.objects.create(
            code="my_custom_role", name="自定义", name_en="My Custom"
        )
        custom_profile = MinistryTeamRoleProfile.objects.create(
            code="my_custom_profile", name="自定义模板", name_en="My Custom Profile"
        )
        custom_requirement = MinistryTeamRoleRequirement.objects.create(
            profile=custom_profile, role_type=custom_type, is_required=False
        )

        self.call_seed_command("--apply")

        self.assertTrue(
            MinistryTeamRoleType.objects.filter(pk=custom_type.pk).exists()
        )
        self.assertTrue(
            MinistryTeamRoleProfile.objects.filter(pk=custom_profile.pk).exists()
        )
        self.assertTrue(
            MinistryTeamRoleRequirement.objects.filter(
                pk=custom_requirement.pk
            ).exists()
        )

    def test_apply_creates_no_assignments_or_team_changes(self):
        team = MinistryTeam.objects.create(name="种子团队", name_en="Seed Team")

        self.call_seed_command("--apply")

        team.refresh_from_db()
        self.assertIsNone(team.role_profile)
        self.assertEqual(MinistryTeamRoleAssignment.objects.count(), 0)
        self.assertEqual(MinistryTeamParentLink.objects.count(), 0)
        self.assertEqual(TeamMembership.objects.count(), 0)
        self.assertEqual(TeamAssignment.objects.count(), 0)
        self.assertEqual(TeamAssignmentMember.objects.count(), 0)
        self.assertEqual(ChurchStructureMembership.objects.count(), 0)
        self.assertEqual(ChurchStructureUnitRoleAssignment.objects.count(), 0)

    def test_seeded_default_profile_reports_missing_lead_then_satisfied(self):
        self.call_seed_command("--apply")
        profile = MinistryTeamRoleProfile.objects.get(
            code=MinistryTeamRoleProfile.CODE_DEFAULT_MINISTRY_UNIT
        )
        lead = MinistryTeamRoleType.objects.get(
            code=MinistryTeamRoleType.CODE_LEAD
        )
        team = MinistryTeam.objects.create(name="读经团队", name_en="Reading Team")
        team.role_profile = profile
        team.save()

        missing = team.missing_required_role_types()
        self.assertEqual([rt.id for rt in missing], [lead.id])

        user = User.objects.create_user(username="seed_lead", password="pw")
        MinistryTeamRoleAssignment.objects.create(
            team=team, role_type=lead, user=user
        )
        self.assertEqual(team.missing_required_role_types(), [])


class MinistryStructureMapTests(TestCase):
    """MINISTRY-STRUCTURE.1C read-only staff Ministry Structure map tests.

    Access is staff/superuser only and never granted by TeamMembership.role,
    MinistryTeamRoleAssignment, ChurchStructureUnitRoleAssignment, or
    ChurchStructureMembership. The page is GET-only and read-only.
    """

    def setUp(self):
        self.regular = User.objects.create_user(username="ms_reg", password="pw")
        self.staff = User.objects.create_user(
            username="ms_staff", password="pw", is_staff=True
        )
        self.superuser = User.objects.create_superuser(
            username="ms_super", password="pw", email="super@example.com"
        )
        self.lead_user = User.objects.create_user(username="ms_lead", password="pw")

        # Church anchors: Whole Church > CM
        self.whole = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_ROOT,
            code="WC",
            name="全教会",
            name_en="Whole Church",
        )
        self.cm = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_MINISTRY_CONTEXT,
            code="CM",
            name="华语",
            name_en="CM",
            parent=self.whole,
        )

        # Teams
        self.digital = MinistryTeam.objects.create(
            name="数字事工",
            name_en="Digital Ministry",
            team_kind=MinistryTeam.KIND_MINISTRY_AREA,
            is_assignable=False,
        )
        self.projection = MinistryTeam.objects.create(
            name="投影团队", name_en="Projection Team", is_assignable=True
        )
        self.video = MinistryTeam.objects.create(
            name="录影团队", name_en="Video Team", is_assignable=True
        )
        self.drama = MinistryTeam.objects.create(
            name="戏剧团队", name_en="Drama Team", is_assignable=True
        )
        self.website = MinistryTeam.objects.create(
            name="网站团队", name_en="Website Team", is_assignable=True
        )

        # Links: CM <- Digital <- Projection / Video. Website shared (CM primary
        # + Digital secondary). Drama unanchored (no links).
        MinistryTeamParentLink.objects.create(
            child_team=self.digital, parent_church_unit=self.cm, is_primary=True
        )
        MinistryTeamParentLink.objects.create(
            child_team=self.projection, parent_team=self.digital, is_primary=True
        )
        MinistryTeamParentLink.objects.create(
            child_team=self.video, parent_team=self.digital, is_primary=True
        )
        MinistryTeamParentLink.objects.create(
            child_team=self.website, parent_church_unit=self.cm, is_primary=True
        )
        MinistryTeamParentLink.objects.create(
            child_team=self.website, parent_team=self.digital, is_primary=False
        )

        # Role profile requiring a lead. Projection has a lead, Video does not.
        self.profile = MinistryTeamRoleProfile.objects.create(
            code="default_ministry_unit", name="默认", name_en="Default"
        )
        self.lead_type = MinistryTeamRoleType.objects.create(
            code="lead", name="负责人", name_en="Lead"
        )
        MinistryTeamRoleRequirement.objects.create(
            profile=self.profile, role_type=self.lead_type, is_required=True
        )
        for team in (self.projection, self.video):
            team.role_profile = self.profile
            team.save()
        MinistryTeamRoleAssignment.objects.create(
            team=self.projection, role_type=self.lead_type, user=self.lead_user
        )

    def set_language(self, language="en"):
        session = self.client.session
        session["language"] = language
        session.save()

    def _snapshot_counts(self):
        return {
            MinistryTeam: MinistryTeam.objects.count(),
            MinistryTeamParentLink: MinistryTeamParentLink.objects.count(),
            MinistryTeamRoleType: MinistryTeamRoleType.objects.count(),
            MinistryTeamRoleProfile: MinistryTeamRoleProfile.objects.count(),
            MinistryTeamRoleRequirement: MinistryTeamRoleRequirement.objects.count(),
            MinistryTeamRoleAssignment: MinistryTeamRoleAssignment.objects.count(),
            TeamMembership: TeamMembership.objects.count(),
            TeamAssignment: TeamAssignment.objects.count(),
            TeamAssignmentMember: TeamAssignmentMember.objects.count(),
            ChurchStructureMembership: ChurchStructureMembership.objects.count(),
            ChurchStructureUnitRoleAssignment: (
                ChurchStructureUnitRoleAssignment.objects.count()
            ),
        }

    # --- Access tests ---

    def test_requires_login(self):
        response = self.client.get(reverse("ministry_structure_map"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_staff_can_view(self):
        self.set_language("en")
        self.client.login(username="ms_staff", password="pw")
        response = self.client.get(reverse("ministry_structure_map"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ministry Structure")

    def test_superuser_can_view(self):
        self.client.login(username="ms_super", password="pw")
        response = self.client.get(reverse("ministry_structure_map"))
        self.assertEqual(response.status_code, 200)

    def test_regular_user_redirected(self):
        self.client.login(username="ms_reg", password="pw")
        response = self.client.get(reverse("ministry_structure_map"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("ministry_team_list"))

    def test_team_membership_lead_does_not_grant_access(self):
        TeamMembership.objects.create(
            team=self.projection,
            user=self.regular,
            role=TeamMembership.ROLE_LEAD,
            can_lead=True,
        )
        self.client.login(username="ms_reg", password="pw")
        response = self.client.get(reverse("ministry_structure_map"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("ministry_team_list"))

    def test_ministry_role_lead_does_not_grant_access(self):
        MinistryTeamRoleAssignment.objects.create(
            team=self.projection, role_type=self.lead_type, user=self.regular
        )
        self.client.login(username="ms_reg", password="pw")
        response = self.client.get(reverse("ministry_structure_map"))
        self.assertEqual(response.status_code, 302)

    def test_church_structure_role_and_membership_do_not_grant_access(self):
        church_lead = ChurchStructureUnitRoleType.objects.create(
            code=ChurchStructureUnitRoleType.CODE_LEAD,
            name="组长",
            name_en="Lead",
        )
        ChurchStructureUnitRoleAssignment.objects.create(
            unit=self.cm, role_type=church_lead, user=self.regular
        )
        ChurchStructureMembership.objects.create(
            user=self.regular,
            unit=self.cm,
            status=ChurchStructureMembership.STATUS_ACTIVE,
            is_primary=True,
            start_date=timezone.localdate(),
        )
        self.client.login(username="ms_reg", password="pw")
        response = self.client.get(reverse("ministry_structure_map"))
        self.assertEqual(response.status_code, 302)

    # --- Page rendering tests ---

    def test_anchored_team_shows_church_ancestor_path(self):
        self.set_language("en")
        self.client.login(username="ms_staff", password="pw")
        response = self.client.get(reverse("ministry_structure_map"))
        self.assertContains(response, "Digital Ministry")
        self.assertContains(response, "Whole Church &gt; CM")

    def test_parent_team_child_appears(self):
        self.set_language("en")
        self.client.login(username="ms_staff", password="pw")
        response = self.client.get(reverse("ministry_structure_map"))
        self.assertContains(response, "Projection Team")
        self.assertContains(response, "Video Team")

    def test_unanchored_team_in_section(self):
        self.set_language("en")
        self.client.login(username="ms_staff", password="pw")
        response = self.client.get(reverse("ministry_structure_map"))
        self.assertContains(response, "Unanchored Ministry Units")
        self.assertContains(response, "Drama Team")

    def test_shared_team_shows_shared_indicator(self):
        self.set_language("en")
        self.client.login(username="ms_staff", password="pw")
        response = self.client.get(reverse("ministry_structure_map"))
        self.assertContains(response, "Website Team")
        self.assertContains(response, "Shared")
        self.assertContains(response, "Also linked here")

    def test_assignable_and_container_badges(self):
        self.set_language("en")
        self.client.login(username="ms_staff", password="pw")
        response = self.client.get(reverse("ministry_structure_map"))
        self.assertContains(response, "Assignable")
        self.assertContains(response, "Container / not assignable")

    def test_missing_required_role_warning_shown(self):
        self.set_language("en")
        self.client.login(username="ms_staff", password="pw")
        response = self.client.get(reverse("ministry_structure_map"))
        self.assertContains(response, "Missing required")

    def test_team_detail_link_present_for_staff(self):
        self.set_language("en")
        self.client.login(username="ms_staff", password="pw")
        response = self.client.get(reverse("ministry_structure_map"))
        self.assertContains(
            response, reverse("ministry_team_detail", args=[self.projection.id])
        )

    # --- Boundary tests ---

    def test_get_creates_no_rows(self):
        before = self._snapshot_counts()
        self.client.login(username="ms_staff", password="pw")
        response = self.client.get(reverse("ministry_structure_map"))
        self.assertEqual(response.status_code, 200)
        after = self._snapshot_counts()
        self.assertEqual(before, after)

    def test_can_manage_ministry_team_unchanged_by_get(self):
        # Permission source stays TeamMembership.role; a role-assignment-only user
        # is not a manager, and a lead membership still is - before and after GET.
        MinistryTeamRoleAssignment.objects.create(
            team=self.video, role_type=self.lead_type, user=self.regular
        )
        TeamMembership.objects.create(
            team=self.video, user=self.lead_user, role=TeamMembership.ROLE_LEAD
        )
        self.assertFalse(can_manage_ministry_team(self.regular, self.video))
        self.assertTrue(can_manage_ministry_team(self.lead_user, self.video))
        self.client.login(username="ms_staff", password="pw")
        self.client.get(reverse("ministry_structure_map"))
        self.assertFalse(can_manage_ministry_team(self.regular, self.video))
        self.assertTrue(can_manage_ministry_team(self.lead_user, self.video))

    def test_get_does_not_change_team_assignments(self):
        event = ServiceEvent.objects.create(
            title="Service",
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
            start_datetime=timezone.now() + timezone.timedelta(days=1),
            status=ServiceEvent.STATUS_PUBLISHED,
        )
        assignment = TeamAssignment.objects.create(
            service_event=event,
            ministry_team=self.digital,  # container, is_assignable=False
            status=TeamAssignment.STATUS_SCHEDULED,
        )
        self.client.login(username="ms_staff", password="pw")
        self.client.get(reverse("ministry_structure_map"))
        assignment.refresh_from_db()
        self.assertEqual(assignment.ministry_team_id, self.digital.id)
        self.assertEqual(TeamAssignment.objects.count(), 1)

    # --- Helper tests ---

    def test_helper_unanchored_team_with_no_links(self):
        structure = build_ministry_structure_map(language="en")
        unanchored_ids = {
            node.card.team_id for node in structure.unanchored_nodes
        }
        self.assertIn(self.drama.id, unanchored_ids)

    def test_helper_shared_team_multiple_parents(self):
        structure = build_ministry_structure_map(language="en")
        # Website is anchored (primary under CM) and referenced (under Digital).
        primary_ids = []
        reference_ids = []
        for group in structure.anchor_groups:
            for node in group.nodes:
                if node.is_primary_occurrence:
                    primary_ids.append(node.card.team_id)
                else:
                    reference_ids.append(node.card.team_id)
        self.assertIn(self.website.id, primary_ids)
        self.assertIn(self.website.id, reference_ids)
        website_card = next(
            node.card
            for group in structure.anchor_groups
            for node in group.nodes
            if node.card.team_id == self.website.id
        )
        self.assertTrue(website_card.is_shared)
        self.assertEqual(website_card.active_parent_link_count, 2)

    def test_helper_missing_vs_present_lead(self):
        structure = build_ministry_structure_map(language="en")
        cards = {}
        for group in structure.anchor_groups:
            for node in group.nodes:
                cards[node.card.team_id] = node.card
        self.assertEqual(cards[self.projection.id].missing_required_role_count, 0)
        self.assertEqual(cards[self.projection.id].active_lead_count, 1)
        self.assertGreater(cards[self.video.id].missing_required_role_count, 0)

    def test_helper_defends_against_cyclic_data(self):
        # Bypass model validation via bulk_create to inject a primary-link cycle.
        a = MinistryTeam.objects.create(name="甲", name_en="Alpha")
        b = MinistryTeam.objects.create(name="乙", name_en="Beta")
        MinistryTeamParentLink.objects.bulk_create(
            [
                MinistryTeamParentLink(
                    child_team=a, parent_team=b, is_primary=True, is_active=True
                ),
                MinistryTeamParentLink(
                    child_team=b, parent_team=a, is_primary=True, is_active=True
                ),
            ]
        )
        structure = build_ministry_structure_map(language="en")
        surfaced = {
            node.card.team_id
            for node in structure.unanchored_nodes
        }
        self.assertIn(a.id, surfaced)
        self.assertIn(b.id, surfaced)

    def test_helper_church_anchor_is_not_permission_source(self):
        structure = build_ministry_structure_map(
            user=self.regular, language="en"
        )
        for group in structure.anchor_groups:
            for node in group.nodes:
                self.assertFalse(node.card.can_view_detail)

    def test_helper_filtered_mode_returns_flat_cards(self):
        structure = build_ministry_structure_map(
            language="en", filters={"q": "Drama"}
        )
        self.assertTrue(structure.is_filtered)
        names = {card.name for card in structure.filtered_cards}
        self.assertEqual(names, {"Drama Team"})
        self.assertTrue(structure.filtered_cards[0].path_label)


class MinistryTeamStructureSetupTests(TestCase):
    """MINISTRY-STRUCTURE.1D-A staff-only structure setup UI tests.

    The setup page edits ministry-structure metadata + parent links only.
    Access is staff/superuser only and is never granted by TeamMembership.role,
    MinistryTeamRoleAssignment, ChurchStructureUnitRoleAssignment, or
    ChurchStructureMembership. Editing structure never creates membership,
    serving, assignment, or role rows and never infers hierarchy.
    """

    def setUp(self):
        self.regular = User.objects.create_user(username="st_reg", password="pw")
        self.staff = User.objects.create_user(
            username="st_staff", password="pw", is_staff=True
        )
        self.superuser = User.objects.create_superuser(
            username="st_super", password="pw", email="st_super@example.com"
        )
        self.lead_user = User.objects.create_user(username="st_lead", password="pw")

        self.whole = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_ROOT,
            code="WC",
            name="全教会",
            name_en="Whole Church",
        )
        self.cm = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_MINISTRY_CONTEXT,
            code="CM",
            name="华语",
            name_en="CM",
            parent=self.whole,
        )

        self.area = MinistryTeam.objects.create(
            name="数字事工",
            name_en="Digital Ministry",
            team_kind=MinistryTeam.KIND_MINISTRY_AREA,
            is_assignable=False,
        )
        self.projection = MinistryTeam.objects.create(
            name="投影团队", name_en="Projection Team", is_assignable=True
        )
        self.video = MinistryTeam.objects.create(
            name="录影团队", name_en="Video Team", is_assignable=True
        )
        self.dept = MinistryTeam.objects.create(
            name="部门", name_en="Department", is_assignable=False
        )

        self.profile = MinistryTeamRoleProfile.objects.create(
            code="default_ministry_unit", name="默认", name_en="Default"
        )
        self.lead_type = MinistryTeamRoleType.objects.create(
            code="lead", name="负责人", name_en="Lead"
        )

    def _structure_url(self, team):
        return reverse("manage_ministry_team_structure", args=[team.id])

    def _login(self, username):
        self.client.login(username=username, password="pw")

    def _snapshot_counts(self):
        return {
            TeamMembership: TeamMembership.objects.count(),
            TeamAssignment: TeamAssignment.objects.count(),
            TeamAssignmentMember: TeamAssignmentMember.objects.count(),
            ChurchStructureMembership: ChurchStructureMembership.objects.count(),
            ChurchStructureUnitRoleAssignment: (
                ChurchStructureUnitRoleAssignment.objects.count()
            ),
            BibleStudyMeetingRole: BibleStudyMeetingRole.objects.count(),
            MinistryTeamRoleAssignment: MinistryTeamRoleAssignment.objects.count(),
        }

    # --- Access tests ---

    def test_requires_login(self):
        response = self.client.get(self._structure_url(self.projection))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_staff_can_access(self):
        self._login("st_staff")
        response = self.client.get(self._structure_url(self.projection))
        self.assertEqual(response.status_code, 200)

    def test_superuser_can_access(self):
        self._login("st_super")
        response = self.client.get(self._structure_url(self.projection))
        self.assertEqual(response.status_code, 200)

    def test_regular_user_redirected(self):
        self._login("st_reg")
        response = self.client.get(self._structure_url(self.projection))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("ministry_team_list"))

    def test_team_membership_lead_does_not_grant_access(self):
        TeamMembership.objects.create(
            team=self.projection,
            user=self.regular,
            role=TeamMembership.ROLE_LEAD,
            can_lead=True,
        )
        self._login("st_reg")
        response = self.client.get(self._structure_url(self.projection))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("ministry_team_list"))

    def test_ministry_role_lead_does_not_grant_access(self):
        MinistryTeamRoleAssignment.objects.create(
            team=self.projection, role_type=self.lead_type, user=self.regular
        )
        self._login("st_reg")
        response = self.client.get(self._structure_url(self.projection))
        self.assertEqual(response.status_code, 302)

    def test_church_structure_lead_and_membership_do_not_grant_access(self):
        church_lead = ChurchStructureUnitRoleType.objects.create(
            code=ChurchStructureUnitRoleType.CODE_LEAD, name="组长", name_en="Lead"
        )
        ChurchStructureUnitRoleAssignment.objects.create(
            unit=self.cm, role_type=church_lead, user=self.regular
        )
        ChurchStructureMembership.objects.create(
            user=self.regular,
            unit=self.cm,
            status=ChurchStructureMembership.STATUS_ACTIVE,
            is_primary=True,
            start_date=timezone.localdate(),
        )
        self._login("st_reg")
        response = self.client.get(self._structure_url(self.projection))
        self.assertEqual(response.status_code, 302)

    # --- Metadata tests ---

    def test_staff_can_update_team_kind_and_assignable(self):
        self._login("st_staff")
        response = self.client.post(
            self._structure_url(self.projection),
            {
                "action": "metadata",
                "team_kind": MinistryTeam.KIND_SUBTEAM,
                # is_assignable checkbox omitted => False
                "is_active": "on",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.projection.refresh_from_db()
        self.assertEqual(self.projection.team_kind, MinistryTeam.KIND_SUBTEAM)
        self.assertFalse(self.projection.is_assignable)
        self.assertTrue(self.projection.is_active)

    def test_role_profile_can_be_set_and_cleared(self):
        self._login("st_staff")
        self.client.post(
            self._structure_url(self.projection),
            {
                "action": "metadata",
                "team_kind": MinistryTeam.KIND_TEAM,
                "is_assignable": "on",
                "is_active": "on",
                "role_profile": str(self.profile.id),
            },
        )
        self.projection.refresh_from_db()
        self.assertEqual(self.projection.role_profile_id, self.profile.id)

        self.client.post(
            self._structure_url(self.projection),
            {
                "action": "metadata",
                "team_kind": MinistryTeam.KIND_TEAM,
                "is_assignable": "on",
                "is_active": "on",
                # role_profile omitted => null
            },
        )
        self.projection.refresh_from_db()
        self.assertIsNone(self.projection.role_profile_id)

    def test_metadata_update_does_not_touch_serving_rows(self):
        TeamMembership.objects.create(
            team=self.projection, user=self.lead_user, role=TeamMembership.ROLE_LEAD
        )
        before = self._snapshot_counts()
        self._login("st_staff")
        self.client.post(
            self._structure_url(self.projection),
            {
                "action": "metadata",
                "team_kind": MinistryTeam.KIND_SUBTEAM,
                "is_active": "on",
            },
        )
        self.assertEqual(before, self._snapshot_counts())

    # --- Parent link tests ---

    def test_add_parent_team_link_becomes_primary(self):
        self._login("st_staff")
        response = self.client.post(
            self._structure_url(self.projection),
            {"action": "add_parent_team", "parent_team": str(self.area.id)},
        )
        self.assertEqual(response.status_code, 302)
        link = MinistryTeamParentLink.objects.get(
            child_team=self.projection, parent_team=self.area
        )
        self.assertTrue(link.is_active)
        self.assertTrue(link.is_primary)

    def test_add_church_anchor_link(self):
        self._login("st_staff")
        self.client.post(
            self._structure_url(self.projection),
            {"action": "add_church_anchor", "parent_church_unit": str(self.cm.id)},
        )
        link = MinistryTeamParentLink.objects.get(
            child_team=self.projection, parent_church_unit=self.cm
        )
        self.assertTrue(link.is_active)
        self.assertTrue(link.is_primary)

    def test_add_link_with_neither_parent_rejected(self):
        self._login("st_staff")
        before = MinistryTeamParentLink.objects.count()
        response = self.client.post(
            self._structure_url(self.projection),
            {"action": "add_parent_team"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(MinistryTeamParentLink.objects.count(), before)

    def test_self_parent_rejected(self):
        self._login("st_staff")
        before = MinistryTeamParentLink.objects.count()
        response = self.client.post(
            self._structure_url(self.projection),
            {"action": "add_parent_team", "parent_team": str(self.projection.id)},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(MinistryTeamParentLink.objects.count(), before)

    def test_cycle_rejected_gracefully(self):
        # video <- projection (projection is parent of video)
        MinistryTeamParentLink.objects.create(
            child_team=self.video, parent_team=self.projection, is_primary=True
        )
        self._login("st_staff")
        # Try to make video a parent of projection => cycle.
        before = MinistryTeamParentLink.objects.filter(
            child_team=self.projection
        ).count()
        response = self.client.post(
            self._structure_url(self.projection),
            {"action": "add_parent_team", "parent_team": str(self.video.id)},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            MinistryTeamParentLink.objects.filter(child_team=self.projection).count(),
            before,
        )

    def test_duplicate_active_parent_link_rejected(self):
        MinistryTeamParentLink.objects.create(
            child_team=self.projection, parent_team=self.area, is_primary=True
        )
        self._login("st_staff")
        response = self.client.post(
            self._structure_url(self.projection),
            {"action": "add_parent_team", "parent_team": str(self.area.id)},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            MinistryTeamParentLink.objects.filter(
                child_team=self.projection, parent_team=self.area, is_active=True
            ).count(),
            1,
        )

    def test_multiple_active_parents_allowed(self):
        self._login("st_staff")
        self.client.post(
            self._structure_url(self.projection),
            {"action": "add_parent_team", "parent_team": str(self.area.id)},
        )
        self.client.post(
            self._structure_url(self.projection),
            {"action": "add_parent_team", "parent_team": str(self.dept.id)},
        )
        active = MinistryTeamParentLink.objects.filter(
            child_team=self.projection, is_active=True
        )
        self.assertEqual(active.count(), 2)
        # Only the first remains primary.
        self.assertEqual(active.filter(is_primary=True).count(), 1)
        self.assertEqual(
            active.get(is_primary=True).parent_team_id, self.area.id
        )

    def test_set_primary_clears_previous_primary(self):
        first = MinistryTeamParentLink.objects.create(
            child_team=self.projection, parent_team=self.area, is_primary=True
        )
        second = MinistryTeamParentLink.objects.create(
            child_team=self.projection, parent_team=self.dept, is_primary=False
        )
        self._login("st_staff")
        self.client.post(
            self._structure_url(self.projection),
            {"action": "set_primary", "link_id": str(second.id)},
        )
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertFalse(first.is_primary)
        self.assertTrue(second.is_primary)
        self.assertEqual(
            MinistryTeamParentLink.objects.filter(
                child_team=self.projection, is_active=True, is_primary=True
            ).count(),
            1,
        )

    def test_deactivate_non_primary_link_keeps_others(self):
        primary = MinistryTeamParentLink.objects.create(
            child_team=self.projection, parent_team=self.area, is_primary=True
        )
        secondary = MinistryTeamParentLink.objects.create(
            child_team=self.projection, parent_team=self.dept, is_primary=False
        )
        self._login("st_staff")
        self.client.post(
            self._structure_url(self.projection),
            {"action": "deactivate_link", "link_id": str(secondary.id)},
        )
        secondary.refresh_from_db()
        primary.refresh_from_db()
        self.assertFalse(secondary.is_active)
        self.assertTrue(primary.is_active)
        self.assertTrue(primary.is_primary)

    def test_deactivate_primary_promotes_sole_remaining_link(self):
        primary = MinistryTeamParentLink.objects.create(
            child_team=self.projection, parent_team=self.area, is_primary=True
        )
        other = MinistryTeamParentLink.objects.create(
            child_team=self.projection, parent_team=self.dept, is_primary=False
        )
        self._login("st_staff")
        self.client.post(
            self._structure_url(self.projection),
            {"action": "deactivate_link", "link_id": str(primary.id)},
        )
        primary.refresh_from_db()
        other.refresh_from_db()
        self.assertFalse(primary.is_active)
        self.assertTrue(other.is_active)
        self.assertTrue(other.is_primary)

    def test_map_reflects_added_parent_link(self):
        self._login("st_staff")
        self.client.post(
            self._structure_url(self.projection),
            {"action": "add_church_anchor", "parent_church_unit": str(self.cm.id)},
        )
        structure = build_ministry_structure_map(language="en")
        anchored_ids = {
            node.card.team_id
            for group in structure.anchor_groups
            for node in group.nodes
        }
        self.assertIn(self.projection.id, anchored_ids)

    # --- Boundary tests ---

    def test_add_link_creates_no_serving_or_role_rows(self):
        before = self._snapshot_counts()
        self._login("st_staff")
        self.client.post(
            self._structure_url(self.projection),
            {"action": "add_parent_team", "parent_team": str(self.area.id)},
        )
        self.client.post(
            self._structure_url(self.projection),
            {"action": "add_church_anchor", "parent_church_unit": str(self.cm.id)},
        )
        self.assertEqual(before, self._snapshot_counts())

    def test_can_manage_ministry_team_unchanged_by_structure_edit(self):
        TeamMembership.objects.create(
            team=self.projection, user=self.lead_user, role=TeamMembership.ROLE_LEAD
        )
        self.assertFalse(can_manage_ministry_team(self.regular, self.projection))
        self.assertTrue(can_manage_ministry_team(self.lead_user, self.projection))
        self._login("st_staff")
        self.client.post(
            self._structure_url(self.projection),
            {"action": "add_parent_team", "parent_team": str(self.area.id)},
        )
        self.assertFalse(can_manage_ministry_team(self.regular, self.projection))
        self.assertTrue(can_manage_ministry_team(self.lead_user, self.projection))

    def test_structure_edit_does_not_change_team_assignments(self):
        event = ServiceEvent.objects.create(
            title="Service",
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
            start_datetime=timezone.now() + timezone.timedelta(days=1),
            status=ServiceEvent.STATUS_PUBLISHED,
        )
        assignment = TeamAssignment.objects.create(
            service_event=event,
            ministry_team=self.area,
            status=TeamAssignment.STATUS_SCHEDULED,
        )
        self._login("st_staff")
        self.client.post(
            self._structure_url(self.projection),
            {"action": "add_parent_team", "parent_team": str(self.area.id)},
        )
        assignment.refresh_from_db()
        self.assertEqual(assignment.ministry_team_id, self.area.id)
        self.assertEqual(TeamAssignment.objects.count(), 1)


class MinistryTeamRoleAssignmentUITests(TestCase):
    """MINISTRY-STRUCTURE.1D-B staff-only ministry role assignment UI tests.

    The role assignment section lives on the staff-only structure setup page. It
    creates/deactivates only ``MinistryTeamRoleAssignment`` rows. Access is
    staff/superuser only and is never granted by TeamMembership.role,
    MinistryTeamRoleAssignment, ChurchStructureUnitRoleAssignment, or
    ChurchStructureMembership. Role assignments are additive: they drive no
    permission, do not appear in My Serving, and create no membership/serving
    rows.
    """

    def setUp(self):
        self.regular = User.objects.create_user(username="ra_reg", password="pw")
        self.staff = User.objects.create_user(
            username="ra_staff", password="pw", is_staff=True
        )
        self.superuser = User.objects.create_superuser(
            username="ra_super", password="pw", email="ra_super@example.com"
        )
        self.alice = User.objects.create_user(username="ra_alice", password="pw")
        self.bob = User.objects.create_user(username="ra_bob", password="pw")

        self.whole = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_ROOT,
            code="WC",
            name="全教会",
            name_en="Whole Church",
        )
        self.cm = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_MINISTRY_CONTEXT,
            code="CM",
            name="华语",
            name_en="CM",
            parent=self.whole,
        )

        self.profile = MinistryTeamRoleProfile.objects.create(
            code="default_ministry_unit", name="默认", name_en="Default"
        )
        self.lead_type = MinistryTeamRoleType.objects.create(
            code="lead", name="负责人", name_en="Lead", sort_order=10
        )
        self.coordinator_type = MinistryTeamRoleType.objects.create(
            code="coordinator", name="协调同工", name_en="Coordinator", sort_order=30
        )
        self.lead_requirement = MinistryTeamRoleRequirement.objects.create(
            profile=self.profile,
            role_type=self.lead_type,
            is_required=True,
            is_active=True,
        )

        self.projection = MinistryTeam.objects.create(
            name="投影团队",
            name_en="Projection Team",
            is_assignable=True,
            role_profile=self.profile,
        )

    def _structure_url(self, team):
        return reverse("manage_ministry_team_structure", args=[team.id])

    def _login(self, username, language="en"):
        # login() resets the session, so set the display language afterwards.
        self.client.login(username=username, password="pw")
        session = self.client.session
        session["language"] = language
        session.save()

    def _snapshot_counts(self):
        return {
            TeamMembership: TeamMembership.objects.count(),
            TeamAssignment: TeamAssignment.objects.count(),
            TeamAssignmentMember: TeamAssignmentMember.objects.count(),
            ChurchStructureMembership: ChurchStructureMembership.objects.count(),
            ChurchStructureUnitRoleAssignment: (
                ChurchStructureUnitRoleAssignment.objects.count()
            ),
            BibleStudyMeetingRole: BibleStudyMeetingRole.objects.count(),
        }

    def _add_role_post(self, team, role_type, user, **extra):
        data = {
            "action": "add_role_assignment",
            "role_type": str(role_type.id),
            "user": str(user.id),
            "start_date": timezone.localdate().isoformat(),
            "is_active": "on",
        }
        data.update(extra)
        return self.client.post(self._structure_url(team), data)

    # --- Access tests ---

    def test_staff_can_view_role_assignment_ui(self):
        self._login("ra_staff")
        response = self.client.get(self._structure_url(self.projection))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Long-term Ministry Roles")

    def test_superuser_can_view_role_assignment_ui(self):
        self._login("ra_super")
        response = self.client.get(self._structure_url(self.projection))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Long-term Ministry Roles")

    def test_regular_user_cannot_view(self):
        self._login("ra_reg")
        response = self.client.get(self._structure_url(self.projection))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("ministry_team_list"))

    def test_team_membership_lead_cannot_view(self):
        TeamMembership.objects.create(
            team=self.projection,
            user=self.regular,
            role=TeamMembership.ROLE_LEAD,
            can_lead=True,
        )
        self._login("ra_reg")
        response = self.client.get(self._structure_url(self.projection))
        self.assertEqual(response.status_code, 302)

    def test_ministry_role_lead_cannot_view(self):
        MinistryTeamRoleAssignment.objects.create(
            team=self.projection, role_type=self.lead_type, user=self.regular
        )
        self._login("ra_reg")
        response = self.client.get(self._structure_url(self.projection))
        self.assertEqual(response.status_code, 302)

    def test_church_structure_lead_cannot_view(self):
        church_lead = ChurchStructureUnitRoleType.objects.create(
            code=ChurchStructureUnitRoleType.CODE_LEAD, name="组长", name_en="Lead"
        )
        ChurchStructureUnitRoleAssignment.objects.create(
            unit=self.cm, role_type=church_lead, user=self.regular
        )
        self._login("ra_reg")
        response = self.client.get(self._structure_url(self.projection))
        self.assertEqual(response.status_code, 302)

    def test_church_membership_does_not_grant_access(self):
        ChurchStructureMembership.objects.create(
            user=self.regular,
            unit=self.cm,
            status=ChurchStructureMembership.STATUS_ACTIVE,
            is_primary=True,
            start_date=timezone.localdate(),
        )
        self._login("ra_reg")
        response = self.client.get(self._structure_url(self.projection))
        self.assertEqual(response.status_code, 302)

    # --- Display tests ---

    def test_no_role_types_shows_graceful_help(self):
        # Deactivate all role types so none are available; the protected
        # requirement row keeps the FK alive, so deactivate rather than delete.
        self.lead_type.is_active = False
        self.lead_type.save()
        self.coordinator_type.is_active = False
        self.coordinator_type.save()
        self._login("ra_staff")
        response = self.client.get(self._structure_url(self.projection))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["has_role_types"])
        self.assertContains(response, "No ministry role types exist yet")

    def test_active_assignment_renders_role_user_and_start_date(self):
        MinistryTeamRoleAssignment.objects.create(
            team=self.projection,
            role_type=self.lead_type,
            user=self.alice,
            start_date=timezone.localdate(),
        )
        self._login("ra_staff")
        response = self.client.get(self._structure_url(self.projection))
        self.assertContains(response, "Lead")
        self.assertContains(response, self.alice.username)
        self.assertContains(response, timezone.localdate().isoformat())

    def test_inactive_assignment_renders_in_historical_section(self):
        MinistryTeamRoleAssignment.objects.create(
            team=self.projection,
            role_type=self.lead_type,
            user=self.alice,
            is_active=False,
            start_date=timezone.localdate() - timezone.timedelta(days=30),
            end_date=timezone.localdate() - timezone.timedelta(days=1),
        )
        self._login("ra_staff")
        response = self.client.get(self._structure_url(self.projection))
        self.assertContains(response, "Historical ministry roles")
        self.assertEqual(len(response.context["inactive_role_assignments"]), 1)
        self.assertEqual(len(response.context["active_role_assignments"]), 0)

    def test_missing_required_lead_warning_appears_without_active_lead(self):
        self._login("ra_staff")
        response = self.client.get(self._structure_url(self.projection))
        self.assertContains(response, "Missing required roles")
        self.assertIn("Lead", response.context["missing_required_roles"])

    def test_missing_required_lead_warning_clears_after_active_lead(self):
        MinistryTeamRoleAssignment.objects.create(
            team=self.projection,
            role_type=self.lead_type,
            user=self.alice,
            start_date=timezone.localdate(),
        )
        self._login("ra_staff")
        response = self.client.get(self._structure_url(self.projection))
        self.assertEqual(response.context["missing_required_roles"], [])
        self.assertNotContains(response, "Missing required roles")

    def test_no_role_profile_shows_muted_note(self):
        self.projection.role_profile = None
        self.projection.save()
        self._login("ra_staff")
        response = self.client.get(self._structure_url(self.projection))
        self.assertContains(response, "no role profile selected")
        self.assertEqual(response.context["missing_required_roles"], [])

    # --- Create / deactivate tests ---

    def test_staff_can_create_lead_assignment(self):
        self._login("ra_staff")
        response = self._add_role_post(self.projection, self.lead_type, self.alice)
        self.assertEqual(response.status_code, 302)
        assignment = MinistryTeamRoleAssignment.objects.get(
            team=self.projection, role_type=self.lead_type, user=self.alice
        )
        self.assertTrue(assignment.is_active)
        self.assertEqual(assignment.start_date, timezone.localdate())

    def test_staff_can_create_coordinator_assignment(self):
        self._login("ra_staff")
        self._add_role_post(self.projection, self.coordinator_type, self.alice)
        self.assertTrue(
            MinistryTeamRoleAssignment.objects.filter(
                team=self.projection,
                role_type=self.coordinator_type,
                user=self.alice,
                is_active=True,
            ).exists()
        )

    def test_multiple_active_leads_for_different_users_allowed(self):
        self._login("ra_staff")
        self._add_role_post(self.projection, self.lead_type, self.alice)
        self._add_role_post(self.projection, self.lead_type, self.bob)
        active_leads = MinistryTeamRoleAssignment.objects.filter(
            team=self.projection, role_type=self.lead_type, is_active=True
        )
        self.assertEqual(active_leads.count(), 2)

    def test_duplicate_overlapping_assignment_rejected_gracefully(self):
        MinistryTeamRoleAssignment.objects.create(
            team=self.projection,
            role_type=self.lead_type,
            user=self.alice,
            start_date=timezone.localdate(),
        )
        self._login("ra_staff")
        response = self._add_role_post(self.projection, self.lead_type, self.alice)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            MinistryTeamRoleAssignment.objects.filter(
                team=self.projection,
                role_type=self.lead_type,
                user=self.alice,
                is_active=True,
            ).count(),
            1,
        )

    def test_inactive_historical_assignment_does_not_block_new(self):
        MinistryTeamRoleAssignment.objects.create(
            team=self.projection,
            role_type=self.lead_type,
            user=self.alice,
            is_active=False,
            start_date=timezone.localdate() - timezone.timedelta(days=30),
            end_date=timezone.localdate() - timezone.timedelta(days=1),
        )
        self._login("ra_staff")
        response = self._add_role_post(self.projection, self.lead_type, self.alice)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            MinistryTeamRoleAssignment.objects.filter(
                team=self.projection,
                role_type=self.lead_type,
                user=self.alice,
                is_active=True,
            ).count(),
            1,
        )

    def test_staff_can_deactivate_assignment_without_deleting(self):
        assignment = MinistryTeamRoleAssignment.objects.create(
            team=self.projection,
            role_type=self.lead_type,
            user=self.alice,
            start_date=timezone.localdate(),
        )
        self._login("ra_staff")
        response = self.client.post(
            self._structure_url(self.projection),
            {
                "action": "deactivate_role_assignment",
                "role_assignment_id": str(assignment.id),
            },
        )
        self.assertEqual(response.status_code, 302)
        assignment.refresh_from_db()
        self.assertFalse(assignment.is_active)
        self.assertEqual(assignment.end_date, timezone.localdate())
        self.assertTrue(
            MinistryTeamRoleAssignment.objects.filter(pk=assignment.pk).exists()
        )

    def test_deactivated_lead_no_longer_satisfies_required_lead(self):
        assignment = MinistryTeamRoleAssignment.objects.create(
            team=self.projection,
            role_type=self.lead_type,
            user=self.alice,
            start_date=timezone.localdate(),
        )
        self.assertEqual(self.projection.missing_required_role_types(), [])
        self._login("ra_staff")
        self.client.post(
            self._structure_url(self.projection),
            {
                "action": "deactivate_role_assignment",
                "role_assignment_id": str(assignment.id),
            },
        )
        missing = self.projection.missing_required_role_types()
        self.assertIn(self.lead_type, missing)

    # --- Boundary tests ---

    def test_add_role_creates_no_membership_or_serving_rows(self):
        before = self._snapshot_counts()
        self._login("ra_staff")
        self._add_role_post(self.projection, self.lead_type, self.alice)
        self.assertEqual(before, self._snapshot_counts())
        self.assertEqual(MinistryTeamRoleAssignment.objects.count(), 1)

    def test_deactivate_role_creates_no_membership_or_serving_rows(self):
        assignment = MinistryTeamRoleAssignment.objects.create(
            team=self.projection,
            role_type=self.lead_type,
            user=self.alice,
            start_date=timezone.localdate(),
        )
        before = self._snapshot_counts()
        self._login("ra_staff")
        self.client.post(
            self._structure_url(self.projection),
            {
                "action": "deactivate_role_assignment",
                "role_assignment_id": str(assignment.id),
            },
        )
        self.assertEqual(before, self._snapshot_counts())

    def test_can_manage_ministry_team_unchanged_by_role_assignment(self):
        TeamMembership.objects.create(
            team=self.projection, user=self.bob, role=TeamMembership.ROLE_LEAD
        )
        self.assertFalse(can_manage_ministry_team(self.alice, self.projection))
        self.assertTrue(can_manage_ministry_team(self.bob, self.projection))
        self._login("ra_staff")
        self._add_role_post(self.projection, self.lead_type, self.alice)
        self.assertFalse(can_manage_ministry_team(self.alice, self.projection))
        self.assertTrue(can_manage_ministry_team(self.bob, self.projection))

    def test_ministry_role_lead_cannot_access_team_edit_route(self):
        MinistryTeamRoleAssignment.objects.create(
            team=self.projection, role_type=self.lead_type, user=self.regular
        )
        self._login("ra_reg")
        response = self.client.get(
            reverse("edit_ministry_team", args=[self.projection.id])
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("ministry_team_list"))

    def test_ministry_role_lead_cannot_access_structure_setup(self):
        MinistryTeamRoleAssignment.objects.create(
            team=self.projection, role_type=self.lead_type, user=self.regular
        )
        self._login("ra_reg")
        response = self.client.get(self._structure_url(self.projection))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("ministry_team_list"))

    def test_ministry_role_assignment_not_shown_in_my_serving(self):
        MinistryTeamRoleAssignment.objects.create(
            team=self.projection,
            role_type=self.lead_type,
            user=self.alice,
            start_date=timezone.localdate(),
        )
        self._login("ra_alice")
        response = self.client.get(reverse("my_serving"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context["serving_items"]), [])
        self.assertEqual(list(response.context["ongoing_structure_roles"]), [])

    def test_regular_user_cannot_create_role_assignment(self):
        self._login("ra_reg")
        response = self._add_role_post(self.projection, self.lead_type, self.alice)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(MinistryTeamRoleAssignment.objects.count(), 0)


class MinistryTeamIsAssignableEnforcementTests(TestCase):
    """MINISTRY-STRUCTURE.1F — enforce ``is_assignable`` for TeamAssignment.

    New active assignments require an assignable ministry unit; existing /
    historical / cancelled assignments are preserved and stay editable so staff
    can view, cancel, or repair them. No permission, My Serving, or Today change.
    """

    def setUp(self):
        self.staff = User.objects.create_user(
            username="assignable_staff",
            email="assignable-staff@example.com",
            password="testpass123",
            is_staff=True,
        )
        self.lead_user = User.objects.create_user(
            username="assignable_lead",
            email="assignable-lead@example.com",
            password="testpass123",
        )
        self.member_user = User.objects.create_user(
            username="assignable_member",
            email="assignable-member@example.com",
            password="testpass123",
        )
        self.assignable_team = MinistryTeam.objects.create(
            name="灯光团队",
            name_en="Lighting Team",
            is_assignable=True,
        )
        self.container_team = MinistryTeam.objects.create(
            name="数字事工",
            name_en="Digital Ministry",
            team_kind=MinistryTeam.KIND_MINISTRY_AREA,
            is_assignable=False,
        )
        self.assignable_membership = TeamMembership.objects.create(
            team=self.assignable_team,
            user=self.member_user,
            role=TeamMembership.ROLE_MEMBER,
        )
        self.container_lead_membership = TeamMembership.objects.create(
            team=self.container_team,
            user=self.lead_user,
            role=TeamMembership.ROLE_LEAD,
        )
        self.event = ServiceEvent.objects.create(
            title="主日崇拜",
            title_en="Sunday Service",
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
            start_datetime=timezone.now() + timezone.timedelta(days=3),
            status=ServiceEvent.STATUS_PUBLISHED,
        )

    def set_language(self, language="en"):
        session = self.client.session
        session["language"] = language
        session.save()

    # ----- model.clean() backstop -------------------------------------------

    def test_model_rejects_new_active_assignment_for_non_assignable_team(self):
        with self.assertRaises(ValidationError) as ctx:
            TeamAssignment.objects.create(
                service_event=self.event,
                ministry_team=self.container_team,
                status=TeamAssignment.STATUS_SCHEDULED,
            )
        self.assertIn("ministry_team", ctx.exception.message_dict)
        self.assertIn(
            TeamAssignment.NOT_ASSIGNABLE_ERROR,
            ctx.exception.message_dict["ministry_team"],
        )
        self.assertEqual(TeamAssignment.objects.count(), 0)

    def test_model_allows_cancelled_assignment_for_non_assignable_team(self):
        assignment = TeamAssignment.objects.create(
            service_event=self.event,
            ministry_team=self.container_team,
            status=TeamAssignment.STATUS_CANCELLED,
        )
        self.assertEqual(assignment.status, TeamAssignment.STATUS_CANCELLED)
        self.assertTrue(
            TeamAssignment.objects.filter(pk=assignment.pk).exists()
        )

    def test_model_allows_new_active_assignment_for_assignable_team(self):
        assignment = TeamAssignment.objects.create(
            service_event=self.event,
            ministry_team=self.assignable_team,
            status=TeamAssignment.STATUS_SCHEDULED,
        )
        self.assertTrue(
            TeamAssignment.objects.filter(pk=assignment.pk).exists()
        )

    def test_model_allows_editing_existing_assignment_after_team_becomes_container(self):
        assignment = TeamAssignment.objects.create(
            service_event=self.event,
            ministry_team=self.assignable_team,
            status=TeamAssignment.STATUS_SCHEDULED,
        )
        self.assignable_team.is_assignable = False
        self.assignable_team.save(update_fields=["is_assignable", "updated_at"])

        assignment.refresh_from_db()
        assignment.notes = "Repair note for a now-container team."
        # Should not raise even though the team is now non-assignable.
        assignment.save()

        assignment.refresh_from_db()
        self.assertEqual(assignment.notes, "Repair note for a now-container team.")

    # ----- TeamAssignmentForm ------------------------------------------------

    def test_form_create_choices_exclude_non_assignable_team(self):
        form = TeamAssignmentForm(
            language="en",
            manageable_teams=MinistryTeam.objects.all(),
        )
        team_ids = set(
            form.fields["ministry_team"].queryset.values_list("id", flat=True)
        )
        self.assertIn(self.assignable_team.id, team_ids)
        self.assertNotIn(self.container_team.id, team_ids)

    def test_form_edit_keeps_current_team_when_it_became_non_assignable(self):
        assignment = TeamAssignment.objects.create(
            service_event=self.event,
            ministry_team=self.assignable_team,
            status=TeamAssignment.STATUS_SCHEDULED,
        )
        self.assignable_team.is_assignable = False
        self.assignable_team.save(update_fields=["is_assignable", "updated_at"])

        form = TeamAssignmentForm(
            instance=assignment,
            language="en",
            manageable_teams=MinistryTeam.objects.all(),
        )
        team_ids = set(
            form.fields["ministry_team"].queryset.values_list("id", flat=True)
        )
        self.assertIn(self.assignable_team.id, team_ids)

    def test_form_create_rejects_non_assignable_team_gracefully(self):
        form = TeamAssignmentForm(
            data={
                "service_event": self.event.id,
                "ministry_team": self.container_team.id,
                "status": TeamAssignment.STATUS_SCHEDULED,
                "notes": "",
            },
            language="en",
            manageable_teams=MinistryTeam.objects.all(),
        )
        self.assertFalse(form.is_valid())
        self.assertIn("ministry_team", form.errors)
        self.assertEqual(TeamAssignment.objects.count(), 0)

    def test_form_edit_rejects_moving_to_different_non_assignable_team(self):
        assignment = TeamAssignment.objects.create(
            service_event=self.event,
            ministry_team=self.assignable_team,
            status=TeamAssignment.STATUS_SCHEDULED,
        )
        form = TeamAssignmentForm(
            data={
                "service_event": self.event.id,
                "ministry_team": self.container_team.id,
                "status": TeamAssignment.STATUS_SCHEDULED,
                "notes": "",
            },
            instance=assignment,
            language="en",
            manageable_teams=MinistryTeam.objects.all(),
        )
        self.assertFalse(form.is_valid())
        self.assertIn("ministry_team", form.errors)
        assignment.refresh_from_db()
        self.assertEqual(assignment.ministry_team_id, self.assignable_team.id)

    def test_form_rejects_reactivating_cancelled_assignment_on_non_assignable_team(self):
        assignment = TeamAssignment.objects.create(
            service_event=self.event,
            ministry_team=self.assignable_team,
            status=TeamAssignment.STATUS_CANCELLED,
        )
        self.assignable_team.is_assignable = False
        self.assignable_team.save(update_fields=["is_assignable", "updated_at"])

        form = TeamAssignmentForm(
            data={
                "service_event": self.event.id,
                "ministry_team": self.assignable_team.id,
                "status": TeamAssignment.STATUS_SCHEDULED,
                "notes": "",
            },
            instance=assignment,
            language="en",
            manageable_teams=MinistryTeam.objects.all(),
        )
        self.assertFalse(form.is_valid())
        self.assertIn("ministry_team", form.errors)
        self.assertIn(
            TeamAssignment.NOT_ASSIGNABLE_ERROR,
            form.errors["ministry_team"],
        )
        # Exactly one message — model backstop and form do not double up.
        self.assertEqual(len(form.errors["ministry_team"]), 1)

    def test_form_allows_editing_unchanged_active_assignment_on_non_assignable_team(self):
        assignment = TeamAssignment.objects.create(
            service_event=self.event,
            ministry_team=self.assignable_team,
            status=TeamAssignment.STATUS_SCHEDULED,
        )
        self.assignable_team.is_assignable = False
        self.assignable_team.save(update_fields=["is_assignable", "updated_at"])

        form = TeamAssignmentForm(
            data={
                "service_event": self.event.id,
                "ministry_team": self.assignable_team.id,
                "status": TeamAssignment.STATUS_SCHEDULED,
                "notes": "Still editable for repair/cancel.",
                "assigned_members": [self.assignable_membership.id],
            },
            instance=assignment,
            language="en",
            manageable_teams=MinistryTeam.objects.all(),
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_form_assignable_team_still_valid(self):
        form = TeamAssignmentForm(
            data={
                "service_event": self.event.id,
                "ministry_team": self.assignable_team.id,
                "status": TeamAssignment.STATUS_SCHEDULED,
                "notes": "",
                "assigned_members": [self.assignable_membership.id],
            },
            language="en",
            manageable_teams=MinistryTeam.objects.all(),
        )
        self.assertTrue(form.is_valid(), form.errors)

    # ----- team schedule page -----------------------------------------------

    def test_schedule_get_for_non_assignable_team_shows_notice(self):
        self.set_language("en")
        self.client.login(username="assignable_staff", password="testpass123")
        response = self.client.get(
            reverse("team_schedule", args=[self.container_team.id])
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["team_not_assignable"])
        self.assertContains(
            response,
            "This ministry unit is not assignable for serving assignments.",
        )

    def test_schedule_post_for_non_assignable_team_does_not_create_assignment(self):
        self.set_language("en")
        self.client.login(username="assignable_staff", password="testpass123")
        response = self.client.post(
            reverse("team_schedule", args=[self.container_team.id]),
            {
                "event": self.event.id,
                "status": TeamAssignment.STATUS_SCHEDULED,
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            TeamAssignment.objects.filter(ministry_team=self.container_team).count(),
            0,
        )

    def test_team_lead_cannot_create_assignment_for_non_assignable_team_via_schedule(self):
        self.client.login(username="assignable_lead", password="testpass123")
        response = self.client.post(
            reverse("team_schedule", args=[self.container_team.id]),
            {
                "event": self.event.id,
                "status": TeamAssignment.STATUS_SCHEDULED,
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            TeamAssignment.objects.filter(ministry_team=self.container_team).count(),
            0,
        )

    # ----- permissions / boundaries -----------------------------------------

    def test_can_manage_ministry_team_unchanged_for_non_assignable_team(self):
        # is_assignable does not affect TeamMembership-derived management.
        self.assertTrue(
            can_manage_ministry_team(self.lead_user, self.container_team)
        )
        self.assertFalse(
            can_manage_ministry_team(self.member_user, self.container_team)
        )

    def test_role_assignment_does_not_grant_management_on_non_assignable_team(self):
        role_type = MinistryTeamRoleType.objects.create(
            code=MinistryTeamRoleType.CODE_LEAD,
            name="负责人",
            name_en="Lead",
        )
        MinistryTeamRoleAssignment.objects.create(
            team=self.container_team,
            role_type=role_type,
            user=self.member_user,
            start_date=timezone.localdate(),
        )
        # A long-term ministry role still does not drive management permission.
        self.assertFalse(
            can_manage_ministry_team(self.member_user, self.container_team)
        )

    def test_my_serving_renders_existing_assignment_on_non_assignable_team(self):
        assignment = TeamAssignment.objects.create(
            service_event=self.event,
            ministry_team=self.assignable_team,
            status=TeamAssignment.STATUS_SCHEDULED,
        )
        TeamAssignmentMember.objects.create(
            assignment=assignment,
            membership=self.assignable_membership,
        )
        # Team becomes a container after the assignment already exists.
        self.assignable_team.is_assignable = False
        self.assignable_team.save(update_fields=["is_assignable", "updated_at"])

        self.set_language("en")
        self.client.login(username="assignable_member", password="testpass123")
        response = self.client.get(reverse("my_serving"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sunday Service")


class MinistryStructureReadinessAuditTests(TestCase):
    """MINISTRY-STRUCTURE.1G read-only readiness audit command tests.

    The ``audit_ministry_structure_readiness`` command must be strictly
    read-only: it has no ``--apply``, mutates nothing, and only reports
    blockers / warnings / info.
    """

    COMMAND = "audit_ministry_structure_readiness"

    def setUp(self):
        # Role config (not teams): a profile that requires an active Lead.
        self.lead_type = MinistryTeamRoleType.objects.create(
            code=MinistryTeamRoleType.CODE_LEAD,
            name="负责人",
            name_en="Lead",
        )
        self.profile = MinistryTeamRoleProfile.objects.create(
            code=MinistryTeamRoleProfile.CODE_DEFAULT_MINISTRY_UNIT,
            name="默认事工单位",
            name_en="Default Ministry Unit",
        )
        self.lead_requirement = MinistryTeamRoleRequirement.objects.create(
            profile=self.profile,
            role_type=self.lead_type,
            is_required=True,
        )
        self.user = User.objects.create_user(
            username="audit_user",
            email="audit-user@example.com",
            password="testpass123",
        )
        self.event = ServiceEvent.objects.create(
            title="主日崇拜",
            title_en="Sunday Service",
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
            start_datetime=timezone.now() + timezone.timedelta(days=3),
            status=ServiceEvent.STATUS_PUBLISHED,
        )

    # ----- helpers ----------------------------------------------------------

    def run_command(self, *args):
        out = StringIO()
        call_command(self.COMMAND, *args, stdout=out)
        return out.getvalue()

    def make_team(self, name, **overrides):
        data = {"name": name, "name_en": name, "is_assignable": True}
        data.update(overrides)
        return MinistryTeam.objects.create(**data)

    def make_non_assignable_assignment(self, team, status):
        """Create an assignment in ``status`` on a now-non-assignable ``team``.

        For active states this mirrors the real-world path (assignment created
        while assignable, then the team flips to container), since 1F blocks a
        new active assignment on a non-assignable team.
        """
        was_assignable = team.is_assignable
        if not was_assignable:
            team.is_assignable = True
            team.save(update_fields=["is_assignable", "updated_at"])
        assignment = TeamAssignment.objects.create(
            service_event=self.event,
            ministry_team=team,
            status=status,
        )
        team.is_assignable = False
        team.save(update_fields=["is_assignable", "updated_at"])
        return assignment

    # ----- existence / read-only -------------------------------------------

    def test_command_runs_with_no_teams(self):
        output = self.run_command()
        self.assertIn(
            "Ministry Structure readiness audit (MINISTRY-STRUCTURE.1G, read-only)",
            output,
        )
        self.assertIn("total_teams: 0", output)
        self.assertIn("blockers present: none", output)

    def test_no_apply_option_exists(self):
        from ministry.management.commands.audit_ministry_structure_readiness import (
            Command,
        )

        parser = Command().create_parser("manage.py", self.COMMAND)
        dests = {action.dest for action in parser._actions}
        self.assertNotIn("apply", dests)
        self.assertIn("fail_on_blockers", dests)
        self.assertIn("verbose", dests)
        self.assertIn("limit", dests)

    def test_command_is_read_only_snapshot_counts(self):
        from accounts.models import (
            ChurchStructureMembership,
            ChurchStructureUnit,
            ChurchStructureUnitRoleAssignment,
        )
        from studies.models import BibleStudyMeetingRole

        team = self.make_team("Lighting", role_profile=self.profile)
        anchor = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_MINISTRY_CONTEXT,
            code="CM",
            name="中文事工",
            name_en="Chinese Ministry",
        )
        MinistryTeamParentLink.objects.create(
            child_team=team, parent_church_unit=anchor, is_primary=True
        )
        MinistryTeamRoleAssignment.objects.create(
            team=team,
            role_type=self.lead_type,
            user=self.user,
            start_date=timezone.localdate(),
        )
        membership = TeamMembership.objects.create(
            team=team, user=self.user, role=TeamMembership.ROLE_LEAD
        )
        assignment = TeamAssignment.objects.create(
            service_event=self.event, ministry_team=team
        )
        TeamAssignmentMember.objects.create(
            assignment=assignment, membership=membership
        )

        models = [
            MinistryTeam,
            MinistryTeamParentLink,
            MinistryTeamRoleType,
            MinistryTeamRoleProfile,
            MinistryTeamRoleRequirement,
            MinistryTeamRoleAssignment,
            TeamMembership,
            TeamAssignment,
            TeamAssignmentMember,
            ChurchStructureMembership,
            ChurchStructureUnitRoleAssignment,
            BibleStudyMeetingRole,
        ]
        before = {model.__name__: model.objects.count() for model in models}
        self.run_command("--verbose")
        after = {model.__name__: model.objects.count() for model in models}
        self.assertEqual(before, after)

    # ----- fail-on-blockers -------------------------------------------------

    def test_fail_on_blockers_exits_zero_when_no_blockers(self):
        self.make_team("Lighting")  # warnings only, no blockers
        # Should not raise.
        self.run_command("--fail-on-blockers")

    def test_fail_on_blockers_nonzero_with_active_assignment_on_container(self):
        team = self.make_team("Lighting")
        self.make_non_assignable_assignment(team, TeamAssignment.STATUS_SCHEDULED)

        audit = run_audit()
        self.assertEqual(audit["stats"]["active_assignments_on_non_assignable_team"], 1)
        self.assertIn("active_assignments_on_non_assignable_team", audit["blockers"])

        with self.assertRaises(CommandError):
            self.run_command("--fail-on-blockers")

    def test_cancelled_assignment_on_container_is_info_not_blocker(self):
        team = self.make_team("Lighting", is_assignable=False)
        TeamAssignment.objects.create(
            service_event=self.event,
            ministry_team=team,
            status=TeamAssignment.STATUS_CANCELLED,
        )
        audit = run_audit()
        self.assertEqual(
            audit["stats"]["cancelled_assignments_on_non_assignable_team"], 1
        )
        self.assertEqual(audit["blocker_count"], 0)
        # --fail-on-blockers must not raise for an info-only finding.
        self.run_command("--fail-on-blockers")

    # ----- parent-link readiness -------------------------------------------

    def test_active_team_no_parent_link_is_warning(self):
        self.make_team("Lighting")
        audit = run_audit()
        self.assertEqual(audit["stats"]["teams_no_active_parent_link"], 1)
        self.assertIn("teams_no_active_parent_link", audit["warnings"])
        self.assertEqual(audit["blocker_count"], 0)

    def test_no_primary_parent_is_warning(self):
        team = self.make_team("Lighting")
        anchor = self._make_anchor("CM")
        MinistryTeamParentLink.objects.create(
            child_team=team, parent_church_unit=anchor, is_primary=False
        )
        audit = run_audit()
        self.assertEqual(audit["stats"]["teams_no_primary_parent_link"], 1)
        self.assertIn("teams_no_primary_parent_link", audit["warnings"])

    def test_shared_team_multiple_parent_links_is_info(self):
        team = self.make_team("Internet Mission")
        cm = self._make_anchor("CM")
        em = self._make_anchor("EM")
        MinistryTeamParentLink.objects.create(
            child_team=team, parent_church_unit=cm, is_primary=True
        )
        MinistryTeamParentLink.objects.create(
            child_team=team, parent_church_unit=em, is_primary=False
        )
        audit = run_audit()
        self.assertEqual(audit["stats"]["shared_teams_multi_active_parent_link"], 1)
        self.assertIn("shared_teams_multi_active_parent_link", audit["info"])
        self.assertEqual(audit["blocker_count"], 0)

    def test_active_link_to_inactive_parent_team_is_warning(self):
        parent = self.make_team("Digital Ministry", is_assignable=False)
        child = self.make_team("Projection")
        MinistryTeamParentLink.objects.create(
            child_team=child, parent_team=parent, is_primary=True
        )
        # Deactivate the parent after the (valid) link exists.
        parent.is_active = False
        parent.save(update_fields=["is_active", "updated_at"])

        audit = run_audit()
        self.assertEqual(audit["stats"]["teams_link_to_inactive_parent_team"], 1)
        self.assertIn("teams_link_to_inactive_parent_team", audit["warnings"])

    # ----- role-profile readiness ------------------------------------------

    def test_assignable_team_no_role_profile_is_warning(self):
        self.make_team("Lighting")  # assignable, no role_profile
        audit = run_audit()
        self.assertEqual(audit["stats"]["assignable_teams_no_role_profile"], 1)
        self.assertIn("assignable_teams_no_role_profile", audit["warnings"])

    def test_missing_required_lead_is_warning(self):
        self.make_team("Lighting", role_profile=self.profile)
        audit = run_audit()
        self.assertEqual(audit["stats"]["teams_missing_required_lead"], 1)
        self.assertIn("teams_missing_required_lead", audit["warnings"])

    def test_active_lead_assignment_clears_missing_required_lead(self):
        team = self.make_team("Lighting", role_profile=self.profile)
        MinistryTeamRoleAssignment.objects.create(
            team=team,
            role_type=self.lead_type,
            user=self.user,
            start_date=timezone.localdate(),
        )
        audit = run_audit()
        self.assertEqual(audit["stats"]["teams_missing_required_lead"], 0)
        self.assertEqual(audit["stats"]["teams_missing_required_roles"], 0)

    # ----- verbose / limit / filters ---------------------------------------

    def test_verbose_output_respects_limit(self):
        for i in range(5):
            self.make_team(f"Team {i}")  # each: no parent link warning
        output = self.run_command("--verbose", "--limit", "2")
        self.assertIn("teams_no_active_parent_link:", output)
        self.assertIn("(stopped at --limit 2)", output)

    def test_team_id_filter_scopes_to_single_team(self):
        keep = self.make_team("Keep")
        self.make_team("Other")
        output = self.run_command("--team-id", str(keep.id))
        self.assertIn("total_teams: 1", output)

    def test_invalid_team_id_raises(self):
        with self.assertRaises(CommandError):
            self.run_command("--team-id", "999999")

    def _make_anchor(self, code):
        from accounts.models import ChurchStructureUnit

        return ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_MINISTRY_CONTEXT,
            code=code,
            name=code,
            name_en=code,
        )
