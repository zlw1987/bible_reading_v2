"""Focused MO-S.6D-1D-C Worship Team operational reachability tests."""

from datetime import datetime

from django.contrib.admin.models import LogEntry
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import (
    ChurchRoleAssignment,
    ChurchStructureMembership,
    ChurchStructureUnit,
)
from core.notification_delivery import notification_sink_override_for_tests
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
    TeamMembership,
)
from .services.worship_context import WORSHIP_CONTEXT_CONFLICT
from .services.worship_governance import (
    WorshipOwnershipConsistencyState,
    inspect_worship_ownership_consistency,
)


User = get_user_model()


class WorshipOperationalReachabilityTests(TestCase):
    password = "testpass123"

    def setUp(self):
        self.root = ChurchStructureUnit.objects.create(
            code="ROOT",
            name="Whole Church",
            name_en="Whole Church",
            unit_type=ChurchStructureUnit.UNIT_ROOT,
        )
        self.cm = ChurchStructureUnit.objects.create(
            code="CM",
            name="Chinese Ministry",
            name_en="Chinese Ministry",
            unit_type=ChurchStructureUnit.UNIT_MINISTRY_CONTEXT,
            parent=self.root,
        )
        self.em = ChurchStructureUnit.objects.create(
            code="EM",
            name="English Ministry",
            name_en="English Ministry",
            unit_type=ChurchStructureUnit.UNIT_MINISTRY_CONTEXT,
            parent=self.root,
        )
        self.pool = MinistryTeam.objects.create(
            name="Chinese Worship Pool",
            name_en="Chinese Worship Pool",
            is_assignable=False,
            is_worship_rotation_pool=True,
        )
        MinistryTeamParentLink.objects.create(
            child_team=self.pool,
            parent_church_unit=self.cm,
            is_primary=True,
        )
        self.c1 = self.create_worship_team("Worship C1")
        self.c2 = self.create_worship_team("Worship C2")

        self.lead_type = MinistryTeamRoleType.objects.create(
            code=MinistryTeamRoleType.CODE_LEAD,
            name="Lead",
            name_en="Lead",
        )
        self.coordinator_type = MinistryTeamRoleType.objects.create(
            code=MinistryTeamRoleType.CODE_COORDINATOR,
            name="Coordinator",
            name_en="Coordinator",
        )
        self.c1_lead = self.create_user("c1_lead")
        self.c1_coordinator = self.create_user("c1_coordinator")
        self.c2_lead = self.create_user("c2_lead")
        self.pool_lead = self.create_user("pool_lead")
        self.planner = self.create_user("event_planner")
        self.ordinary = self.create_user("audience_viewer")
        self.global_manager = self.create_user("global_assignment_manager")
        self.staff = self.create_user("staff_manager", is_staff=True)
        self.roster_user = self.create_user(
            "worship_roster_person", email="worship-roster@example.com"
        )

        self.assign_role(self.c1, self.c1_lead, self.lead_type)
        self.assign_role(self.c1, self.c1_coordinator, self.coordinator_type)
        self.assign_role(self.c2, self.c2_lead, self.lead_type)
        self.assign_role(self.pool, self.pool_lead, self.lead_type)
        ChurchRoleAssignment.objects.create(
            user=self.global_manager,
            role=ChurchRoleAssignment.ROLE_PASTOR,
            scope_type=ChurchRoleAssignment.SCOPE_GLOBAL,
        )
        ChurchStructureMembership.objects.create(
            user=self.ordinary,
            unit=self.cm,
            status=ChurchStructureMembership.STATUS_ACTIVE,
            is_primary=True,
            start_date=timezone.localdate(),
        )
        self.c1_membership = TeamMembership.objects.create(
            team=self.c1,
            user=self.roster_user,
        )

        self.event = self.create_event("Anchor-only Worship Sunday", team=self.c1)
        ServiceEventPlannerAssignment.objects.create(
            service_event=self.event,
            user=self.planner,
        )

    def create_user(self, username, **kwargs):
        return User.objects.create_user(
            username=username,
            password=self.password,
            **kwargs,
        )

    def create_worship_team(self, name):
        team = MinistryTeam.objects.create(name=name, name_en=name)
        MinistryTeamParentLink.objects.create(
            child_team=team,
            parent_team=self.pool,
            is_primary=True,
        )
        return team

    def assign_role(self, team, user, role_type):
        return MinistryTeamRoleAssignment.objects.create(
            team=team,
            user=user,
            role_type=role_type,
            start_date=timezone.localdate(),
        )

    def sunday_datetime(self, *, weeks=1):
        days_until_sunday = (6 - timezone.localdate().weekday()) % 7
        date = timezone.localdate() + timezone.timedelta(
            days=days_until_sunday + (7 * weeks)
        )
        naive = datetime.combine(date, datetime.min.time()).replace(hour=10)
        return timezone.make_aware(naive, timezone.get_current_timezone())

    def create_event(
        self,
        title,
        *,
        team,
        weeks=1,
        event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
        status=ServiceEvent.STATUS_PUBLISHED,
    ):
        event = ServiceEvent.objects.create(
            title=title,
            title_en=title,
            event_type=event_type,
            start_datetime=self.sunday_datetime(weeks=weeks),
            status=status,
            rotation_anchor_team=team,
        )
        ServiceEventAudienceScope.objects.create(service_event=event, unit=self.cm)
        return event

    def login(self, user, language="en"):
        self.client.force_login(user)
        session = self.client.session
        session["language"] = language
        session.save()

    def team_schedule(self, user, team=None, **params):
        self.login(user)
        return self.client.get(
            reverse("team_schedule", args=[(team or self.c1).id]),
            params,
        )

    def board(self, user, language="en"):
        self.login(user, language=language)
        return self.client.get(reverse("sunday_schedule_board"))

    def assert_event_on_board(self, response, event=None):
        target = event or self.event
        self.assertEqual(response.status_code, 200)
        return next(
            row
            for row in response.context["board"]["rows"]
            if row["event"].id == target.id
        )

    def reachability_counts(self):
        return {
            "required": ServiceEventRequiredTeam.objects.count(),
            "assignments": TeamAssignment.objects.count(),
            "assignment_members": TeamAssignmentMember.objects.count(),
            "team_memberships": TeamMembership.objects.count(),
            "audience": ServiceEventAudienceScope.objects.count(),
            "structure_memberships": ChurchStructureMembership.objects.count(),
            "planners": ServiceEventPlannerAssignment.objects.count(),
            "notifications": Notification.objects.count(),
            "log_entries": LogEntry.objects.count(),
        }

    def change_selected_team(self, team):
        self.login(self.planner)
        self.event.refresh_from_db()
        response = self.client.post(
            reverse("change_worship_team", args=[self.event.id]),
            {
                "worship_team": team.id if team else "",
                "expected_updated_at": self.event.updated_at.isoformat(),
                "expected_anchor_team": self.event.rotation_anchor_team_id or "",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.event.refresh_from_db()

    def test_valid_anchor_only_team_schedule_is_actionable_and_get_is_read_only(self):
        before = self.reachability_counts()
        payloads = []
        self.login(self.c1_lead)
        with notification_sink_override_for_tests(payloads.append):
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.get(
                    reverse("team_schedule", args=[self.c1.id])
                )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.event.title_en)
        self.assertContains(response, "Selected Worship Team")
        self.assertContains(response, "Selected, not yet scheduled")
        self.assertContains(response, f"event={self.event.id}")
        row = response.context["schedule_rows"][0]
        self.assertEqual(row["coverage_rows"], [])
        self.assertTrue(row["is_valid_selected_worship_team"])
        self.assertNotContains(response, "Unassigned")
        self.assertNotContains(response, "Additional assignment")
        self.assertEqual(self.reachability_counts(), before)
        self.assertEqual(payloads, [])

        form_response = self.client.get(
            reverse("team_schedule", args=[self.c1.id]),
            {"event": self.event.id},
        )
        self.assertEqual(form_response.status_code, 200)
        self.assertContains(form_response, "Schedule Assignment")
        self.assertEqual(self.reachability_counts(), before)

    def test_explicit_team_schedule_save_uses_normal_assignment_workflow(self):
        self.login(self.c1_lead)
        payloads = []
        with notification_sink_override_for_tests(payloads.append):
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.post(
                    f"{reverse('team_schedule', args=[self.c1.id])}"
                    f"?event={self.event.id}",
                    {
                        "assigned_members": [self.c1_membership.id],
                        "status": TeamAssignment.STATUS_SCHEDULED,
                        "notes": "Normal explicit Worship roster save.",
                        "audience_override_ack": "on",
                    },
                )

        self.assertEqual(response.status_code, 302)
        assignment = TeamAssignment.objects.get()
        self.assertEqual(assignment.service_event, self.event)
        self.assertEqual(assignment.ministry_team, self.c1)
        self.assertEqual(assignment.created_by, self.c1_lead)
        self.assertEqual(assignment.assignment_members.count(), 1)
        self.assertFalse(ServiceEventRequiredTeam.objects.exists())
        self.assertTrue(payloads)

        rendered = self.team_schedule(self.c1_lead)
        self.assertContains(rendered, "Selected Worship Team assignment")
        self.assertNotContains(rendered, "Additional assignment")

    def test_exact_team_authority_is_independent_from_selection_authority(self):
        for user in [self.c1_lead, self.c1_coordinator, self.staff, self.global_manager]:
            with self.subTest(allowed=user.username):
                response = self.team_schedule(user)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, self.event.title_en)

        unrelated = self.team_schedule(self.c2_lead, team=self.c2)
        self.assertNotContains(unrelated, self.event.title_en)
        for user in [self.pool_lead, self.planner]:
            with self.subTest(selection_only=user.username):
                denied = self.team_schedule(user)
                self.assertRedirects(denied, reverse("ministry_team_list"))

    def test_board_anchor_only_scope_actions_and_boundaries(self):
        for user in [self.c1_lead, self.c1_coordinator, self.global_manager]:
            with self.subTest(allowed=user.username):
                response = self.board(user)
                row = self.assert_event_on_board(response)
                self.assertEqual(row["cells"], [])
                self.assertTrue(row["worship_context"]["can_edit"])
                self.assertEqual(row["worship_context"]["action_kind"], "schedule")
                self.assertIn(
                    reverse("team_schedule", args=[self.c1.id]),
                    row["worship_context"]["action_url"],
                )
                self.assertIn(
                    f"event={self.event.id}", row["worship_context"]["action_url"]
                )

        unrelated = self.board(self.c2_lead)
        self.assertNotContains(unrelated, self.event.title_en)
        pool_lead = self.board(self.pool_lead)
        self.assertEqual(pool_lead.status_code, 200)
        self.assertNotContains(pool_lead, self.event.title_en)
        for user in [self.planner, self.ordinary]:
            with self.subTest(no_board_grant=user.username):
                response = self.board(user)
                self.assertRedirects(response, reverse("my_serving"))

        self.assertFalse(self.event.can_be_seen_by(self.c1_lead))
        self.login(self.c1_lead)
        detail = self.client.get(reverse("service_event_detail", args=[self.event.id]))
        self.assertNotEqual(detail.status_code, 200)

    def test_invalid_selection_gives_no_anchor_only_reachability_or_action(self):
        invalidators = [
            ("inactive", lambda: MinistryTeam.objects.filter(id=self.c1.id).update(is_active=False)),
            (
                "nonassignable",
                lambda: MinistryTeam.objects.filter(id=self.c1.id).update(
                    is_assignable=False
                ),
            ),
            (
                "audience_changed",
                lambda: ServiceEventAudienceScope.objects.filter(
                    service_event=self.event
                ).update(unit=self.em),
            ),
        ]
        for label, invalidate in invalidators:
            with self.subTest(label=label):
                invalidate()
                self.c1.refresh_from_db()
                schedule = self.team_schedule(self.global_manager)
                board = self.board(self.global_manager)
                MinistryTeam.objects.filter(id=self.c1.id).update(
                    is_active=True, is_assignable=True
                )
                ServiceEventAudienceScope.objects.filter(
                    service_event=self.event
                ).update(unit=self.cm)
                self.c1.refresh_from_db()
                self.assertNotContains(schedule, self.event.title_en)
                self.assertNotContains(board, self.event.title_en)

        self.event.required_teams.add(self.c1)
        ServiceEventAudienceScope.objects.filter(service_event=self.event).update(
            unit=self.em
        )
        visible = self.board(self.c1_lead)
        row = self.assert_event_on_board(visible)
        self.assertEqual(row["worship_context"]["state"], "anchor_unavailable")
        self.assertFalse(row["worship_context"]["can_edit"])
        self.assertEqual(row["worship_context"]["action_url"], "")
        self.assertEqual(len(row["cells"]), 1)
        cell = row["cells"][0]
        self.assertEqual(cell["team"], self.c1)
        self.assertTrue(cell["participates"])
        self.assertTrue(cell["is_required"])
        self.assertEqual(cell["state"], "missing")
        self.assertContains(visible, "Selected Worship Team needs review")
        self.assertNotContains(visible, "Schedule Worship")

    def test_invalid_selection_preserves_independent_assignment_projection(self):
        assignment = TeamAssignment.objects.create(
            service_event=self.event,
            ministry_team=self.c1,
            status=TeamAssignment.STATUS_SCHEDULED,
            notes="Private invalid-selection assignment note.",
            created_by=self.c1_lead,
        )
        assignment_member = TeamAssignmentMember.objects.create(
            assignment=assignment,
            membership=self.c1_membership,
            confirmation_note="Private invalid-selection confirmation.",
        )
        assignment_member.confirmed_at = timezone.now()
        assignment_member.save()
        ServiceEventAudienceScope.objects.filter(service_event=self.event).update(
            unit=self.em
        )
        before = self.reachability_counts()

        visible = self.board(self.c1_lead)

        self.assertEqual(self.reachability_counts(), before)
        row = self.assert_event_on_board(visible)
        self.assertEqual(row["worship_context"]["state"], WORSHIP_CONTEXT_CONFLICT)
        self.assertFalse(row["worship_context"]["can_edit"])
        self.assertEqual(row["worship_context"]["action_url"], "")
        self.assertEqual(len(row["cells"]), 1)
        cell = row["cells"][0]
        self.assertEqual(cell["team"], self.c1)
        self.assertTrue(cell["participates"])
        self.assertFalse(cell["is_required"])
        self.assertTrue(cell["is_additional"])
        self.assertEqual(cell["state"], "scheduled")
        self.assertEqual(cell["member_names"], [self.roster_user.username])
        self.assertContains(visible, self.roster_user.username, count=1)
        self.assertContains(visible, "Worship ownership conflict · review required")
        self.assertNotContains(visible, "Schedule Worship")
        self.assertNotContains(visible, "Edit Worship")
        self.assertNotContains(
            visible, "Private invalid-selection assignment note."
        )
        self.assertNotContains(visible, self.roster_user.email)
        self.assertNotContains(
            visible, "Private invalid-selection confirmation."
        )

    def test_off_team_conflict_is_review_required_on_board_and_team_schedule(self):
        c2_membership = TeamMembership.objects.create(
            team=self.c2,
            display_name="C2 Conflict Worship Person",
            email="c2-conflict-private@example.com",
        )
        assignment = TeamAssignment(
            service_event=self.event,
            ministry_team=self.c2,
            status=TeamAssignment.STATUS_SCHEDULED,
            notes="Private off-team conflict note.",
            created_by=self.c2_lead,
        )
        TeamAssignment.objects.bulk_create([assignment])
        TeamAssignmentMember.objects.bulk_create(
            [
                TeamAssignmentMember(
                    assignment=assignment,
                    membership=c2_membership,
                    confirmed_at=timezone.now(),
                    confirmation_note="Private off-team confirmation.",
                )
            ]
        )
        before = self.reachability_counts()

        inspection = inspect_worship_ownership_consistency(self.event)
        board = self.board(self.c1_lead)
        row = self.assert_event_on_board(board)
        schedule = self.team_schedule(self.c1_lead)

        self.assertEqual(
            inspection.state,
            WorshipOwnershipConsistencyState.OFF_TEAM_CONFLICT,
        )
        self.assertEqual(self.reachability_counts(), before)
        self.assertEqual(row["worship_context"]["state"], WORSHIP_CONTEXT_CONFLICT)
        self.assertFalse(row["worship_context"]["can_edit"])
        self.assertEqual(row["worship_context"]["action_url"], "")
        c2_cell = next(cell for cell in row["cells"] if cell["team"] == self.c2)
        self.assertTrue(c2_cell["participates"])
        self.assertEqual(c2_cell["state"], "scheduled")
        self.assertEqual(c2_cell["member_names"], ["C2 Conflict Worship Person"])
        self.assertContains(board, "Worship ownership conflict · review required")
        self.assertContains(board, "C2 Conflict Worship Person")
        self.assertNotContains(board, "Schedule Worship")
        self.assertNotContains(board, "Edit Worship")
        self.assertNotContains(board, "Private off-team conflict note.")
        self.assertNotContains(board, c2_membership.email)
        self.assertNotContains(board, "Private off-team confirmation.")

        schedule_row = schedule.context["schedule_rows"][0]
        self.assertEqual(
            schedule_row["worship_context"]["state"],
            WORSHIP_CONTEXT_CONFLICT,
        )
        self.assertContains(schedule, "Worship ownership conflict · review required")
        self.assertNotContains(schedule, "Selected, not yet scheduled")
        self.assertNotContains(schedule, "Private off-team conflict note.")
        self.assertNotContains(schedule, c2_membership.email)
        self.assertNotContains(schedule, "Private off-team confirmation.")

    def test_governed_change_and_clear_move_derived_reachability(self):
        self.assertContains(self.team_schedule(self.c1_lead), self.event.title_en)
        self.assertNotContains(
            self.team_schedule(self.c2_lead, team=self.c2), self.event.title_en
        )

        self.change_selected_team(self.c2)
        c1_after_change = self.team_schedule(self.c1_lead)
        self.assertNotContains(c1_after_change, self.event.title_en)
        self.assertContains(
            c1_after_change,
            "No events in this range require, already include, or select this team as the Worship Team.",
        )
        self.assertContains(
            self.team_schedule(self.c2_lead, team=self.c2), self.event.title_en
        )
        self.assertNotContains(self.board(self.c1_lead), self.event.title_en)
        self.assertContains(self.board(self.c2_lead), self.event.title_en)

        self.change_selected_team(None)
        self.assertNotContains(self.team_schedule(self.c1_lead), self.event.title_en)
        self.assertNotContains(
            self.team_schedule(self.c2_lead, team=self.c2), self.event.title_en
        )

        self.change_selected_team(self.c2)
        self.event.required_teams.add(self.c1)
        self.assertContains(self.team_schedule(self.c1_lead), self.event.title_en)
        self.change_selected_team(None)
        self.assertContains(self.team_schedule(self.c1_lead), self.event.title_en)
        self.assertNotContains(
            self.team_schedule(self.c2_lead, team=self.c2), self.event.title_en
        )

    def test_anchor_only_filters_and_bilingual_terminology_are_preserved(self):
        self.create_event(
            "Draft Anchor Sunday",
            team=self.c1,
            weeks=2,
            status=ServiceEvent.STATUS_DRAFT,
        )
        self.create_event(
            "Cancelled Anchor Sunday",
            team=self.c1,
            weeks=3,
            status=ServiceEvent.STATUS_CANCELLED,
        )
        self.create_event(
            "Non-Sunday Anchor Event",
            team=self.c1,
            weeks=4,
            event_type=ServiceEvent.EVENT_BIBLE_STUDY,
        )
        self.create_event(
            "Outside Anchor Window",
            team=self.c1,
            weeks=10,
        )
        schedule = self.team_schedule(
            self.c1_lead,
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
        )
        self.assertContains(schedule, self.event.title_en)
        self.assertNotContains(schedule, "Draft Anchor Sunday")
        self.assertNotContains(schedule, "Cancelled Anchor Sunday")
        self.assertNotContains(schedule, "Non-Sunday Anchor Event")
        self.assertNotContains(schedule, "Outside Anchor Window")

        board = self.board(self.c1_lead)
        self.assertContains(board, self.event.title_en)
        self.assertNotContains(board, "Draft Anchor Sunday")
        self.assertNotContains(board, "Cancelled Anchor Sunday")
        self.assertNotContains(board, "Non-Sunday Anchor Event")
        self.assertNotContains(board, "Outside Anchor Window")

        self.login(self.c1_lead, language="zh")
        chinese_schedule = self.client.get(
            reverse("team_schedule", args=[self.c1.id])
        )
        self.assertContains(chinese_schedule, "已选敬拜团队")
        self.assertContains(chinese_schedule, "已选择，尚未排班")
        chinese_board = self.board(self.c1_lead, language="zh")
        self.assertContains(chinese_board, "敬拜")
        self.assertContains(chinese_board, "已选择，尚未排班")
        for stale in ["配搭参考", "Rotation Anchor", "Rotation/Worship"]:
            self.assertNotContains(chinese_schedule, stale)
            self.assertNotContains(chinese_board, stale)
