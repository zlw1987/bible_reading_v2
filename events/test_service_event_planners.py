"""Focused tests for MO-S.6D-1C ServiceEvent planner responsibility."""

from datetime import timedelta

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import ChurchStructureMembership, ChurchStructureUnit
from events.calendar_provider import provide_service_event_items
from events.forms import ServiceEventPlannerAssignmentForm
from events.models import (
    ServiceEvent,
    ServiceEventAudienceScope,
    ServiceEventPlannerAssignment,
    ServiceEventRequiredTeam,
    current_service_event_planner_assignments,
)
from events.views import can_manage_service_events, get_visible_service_events
from events.visibility import member_visible_service_events_for
from events.today_provider import get_gathering_rows_for_window
from ministry.models import (
    MinistryTeam,
    TeamAssignment,
    TeamAssignmentMember,
    TeamMembership,
)
from ministry.permissions import (
    can_manage_ministry_team,
    can_manage_team_assignment_for_team,
    user_has_explicit_serving_assignment_for_event,
)
from notifications.models import Notification
from studies.models import BibleStudyMeetingRole


User = get_user_model()


class ServiceEventPlannerTestBase(TestCase):
    def setUp(self):
        self.root = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_ROOT,
            code="CHURCH",
            name="全教会",
            name_en="Whole Church",
        )
        self.audience_unit = ChurchStructureUnit.objects.create(
            parent=self.root,
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="AUD",
            name="适用小组",
            name_en="Audience Group",
        )
        self.outside_unit = ChurchStructureUnit.objects.create(
            parent=self.root,
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="OUT",
            name="其他小组",
            name_en="Outside Group",
        )
        self.staff = User.objects.create_user(
            username="event_staff",
            password="pw12345!",
            is_staff=True,
        )
        self.planner = User.objects.create_user(
            username="event_planner",
            password="pw12345!",
            first_name="Pat",
            last_name="Planner",
        )
        self.other_planner = User.objects.create_user(
            username="second_planner",
            password="pw12345!",
        )
        self.inactive_user = User.objects.create_user(
            username="inactive_planner",
            password="pw12345!",
            is_active=False,
        )
        ChurchStructureMembership.objects.create(
            user=self.planner,
            unit=self.outside_unit,
            status=ChurchStructureMembership.STATUS_ACTIVE,
            is_primary=True,
            start_date=timezone.localdate() - timedelta(days=1),
        )
        self.team = MinistryTeam.objects.create(
            name="敬拜一队",
            name_en="Worship One",
        )
        self.other_team = MinistryTeam.objects.create(
            name="敬拜二队",
            name_en="Worship Two",
        )
        self.event = ServiceEvent.objects.create(
            title="主日聚会",
            title_en="Sunday Service",
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
            start_datetime=timezone.now() + timedelta(days=3),
            status=ServiceEvent.STATUS_PUBLISHED,
            rotation_anchor_team=self.team,
        )
        ServiceEventAudienceScope.objects.create(
            service_event=self.event,
            unit=self.audience_unit,
        )
        ServiceEventRequiredTeam.objects.create(
            service_event=self.event,
            ministry_team=self.team,
        )

    def set_language(self, language):
        session = self.client.session
        session["language"] = language
        session.save()

    def assign(self, user=None, **overrides):
        data = {
            "service_event": self.event,
            "user": user or self.planner,
            "notes": "Coordinate the service order.",
        }
        data.update(overrides)
        return ServiceEventPlannerAssignment.objects.create(**data)


class ServiceEventPlannerModelTests(ServiceEventPlannerTestBase):
    def test_explicit_active_user_assignment_is_valid_and_current(self):
        assignment = self.assign()

        self.assertEqual(assignment.service_event, self.event)
        self.assertEqual(assignment.user, self.planner)
        self.assertTrue(assignment.is_active)
        self.assertEqual(
            list(current_service_event_planner_assignments(self.event)),
            [assignment],
        )

    def test_multiple_different_planners_are_allowed_for_one_event(self):
        first = self.assign()
        second = self.assign(self.other_planner)

        self.assertEqual(
            set(current_service_event_planner_assignments(self.event)),
            {first, second},
        )

    def test_duplicate_event_user_assignment_is_rejected(self):
        self.assign()

        with self.assertRaises(ValidationError):
            self.assign(notes="Duplicate")

        self.assertEqual(ServiceEventPlannerAssignment.objects.count(), 1)

    def test_responsibility_can_end_and_remains_historical(self):
        assignment = self.assign()
        assignment.is_active = False
        assignment.save(update_fields=["is_active", "updated_at"])

        self.assertTrue(
            ServiceEventPlannerAssignment.objects.filter(pk=assignment.pk).exists()
        )
        self.assertEqual(
            list(current_service_event_planner_assignments(self.event)),
            [],
        )

    def test_user_deactivated_after_creation_is_not_current_without_row_rewrite(self):
        assignment = self.assign()
        self.planner.is_active = False
        self.planner.save(update_fields=["is_active"])

        assignment.refresh_from_db()
        self.assertTrue(assignment.is_active)
        self.assertEqual(
            list(current_service_event_planner_assignments(self.event)),
            [],
        )

    def test_active_assignment_rejects_inactive_user(self):
        with self.assertRaises(ValidationError):
            self.assign(self.inactive_user)

    def test_draft_event_can_have_planner(self):
        self.event.status = ServiceEvent.STATUS_DRAFT
        self.event.save(update_fields=["status", "updated_at"])

        assignment = self.assign()

        self.assertTrue(assignment.is_active)

    def test_cancelled_or_completed_event_does_not_rewrite_assignment(self):
        assignment = self.assign()
        assignment_updated_at = assignment.updated_at

        for status in (
            ServiceEvent.STATUS_CANCELLED,
            ServiceEvent.STATUS_COMPLETED,
        ):
            self.event.status = status
            self.event.save(update_fields=["status", "updated_at"])
            assignment.refresh_from_db()
            self.assertTrue(assignment.is_active)
            self.assertEqual(assignment.updated_at, assignment_updated_at)

    def test_admin_registers_explicit_responsibility_model(self):
        self.assertTrue(admin.site.is_registered(ServiceEventPlannerAssignment))


class ServiceEventPlannerManagementTests(ServiceEventPlannerTestBase):
    def test_full_event_manager_can_add_end_and_restore_planner(self):
        self.client.force_login(self.staff)

        add_response = self.client.post(
            reverse("add_service_event_planner", args=[self.event.id]),
            {"user": self.planner.id, "notes": "Plan this service."},
        )
        assignment = ServiceEventPlannerAssignment.objects.get()
        self.assertRedirects(
            add_response,
            reverse("edit_service_event", args=[self.event.id]),
        )
        self.assertTrue(assignment.is_active)

        end_response = self.client.post(
            reverse(
                "end_service_event_planner",
                args=[self.event.id, assignment.id],
            )
        )
        self.assertRedirects(
            end_response,
            reverse("edit_service_event", args=[self.event.id]),
        )
        assignment.refresh_from_db()
        self.assertFalse(assignment.is_active)

        restore_response = self.client.post(
            reverse(
                "restore_service_event_planner",
                args=[self.event.id, assignment.id],
            )
        )
        self.assertRedirects(
            restore_response,
            reverse("edit_service_event", args=[self.event.id]),
        )
        assignment.refresh_from_db()
        self.assertTrue(assignment.is_active)

    def test_duplicate_add_is_rejected_without_reactivation_or_new_row(self):
        assignment = self.assign(is_active=False)
        self.set_language("en")
        self.client.force_login(self.staff)

        response = self.client.post(
            reverse("add_service_event_planner", args=[self.event.id]),
            {"user": self.planner.id, "notes": "Try duplicate"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "already has a planner responsibility record")
        assignment.refresh_from_db()
        self.assertFalse(assignment.is_active)
        self.assertEqual(ServiceEventPlannerAssignment.objects.count(), 1)

    def test_inactive_users_are_not_selectable_and_forged_post_is_rejected(self):
        form = ServiceEventPlannerAssignmentForm(
            service_event=self.event,
            language="en",
        )
        self.assertNotIn(self.inactive_user, form.fields["user"].queryset)

        self.client.force_login(self.staff)
        response = self.client.post(
            reverse("add_service_event_planner", args=[self.event.id]),
            {"user": self.inactive_user.id, "notes": "Forged"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertFormError(
            response.context["planner_form"],
            "user",
            "Select a valid choice. That choice is not one of the available choices.",
        )
        self.assertEqual(ServiceEventPlannerAssignment.objects.count(), 0)

    def test_planner_management_copy_and_labels_render_in_both_languages(self):
        self.client.force_login(self.staff)
        edit_url = reverse("edit_service_event", args=[self.event.id])

        self.set_language("en")
        english = self.client.get(edit_url)
        self.assertContains(english, "Service Planners / Coordinators")
        self.assertContains(english, "Add planner")
        self.assertContains(english, "does not by itself grant full event editing")
        self.assertContains(english, "team-assignment authority")

        self.set_language("zh")
        chinese = self.client.get(edit_url)
        self.assertContains(chinese, "聚会安排人 / 协调人")
        self.assertContains(chinese, "添加安排人")
        self.assertContains(chinese, "此责任本身不会授予完整的聚会编辑权限")
        self.assertContains(chinese, "团队排班权限")

    def test_non_manager_cannot_mutate_planner_rows(self):
        assignment = self.assign(self.other_planner)
        self.client.force_login(self.planner)

        add_response = self.client.post(
            reverse("add_service_event_planner", args=[self.event.id]),
            {"user": self.planner.id},
        )
        end_response = self.client.post(
            reverse(
                "end_service_event_planner",
                args=[self.event.id, assignment.id],
            )
        )

        self.assertRedirects(add_response, reverse("service_event_list"))
        self.assertRedirects(end_response, reverse("service_event_list"))
        assignment.refresh_from_db()
        self.assertTrue(assignment.is_active)
        self.assertEqual(ServiceEventPlannerAssignment.objects.count(), 1)

    def test_restore_fails_closed_when_linked_user_became_inactive(self):
        assignment = self.assign(is_active=False)
        self.planner.is_active = False
        self.planner.save(update_fields=["is_active"])
        self.client.force_login(self.staff)

        response = self.client.post(
            reverse(
                "restore_service_event_planner",
                args=[self.event.id, assignment.id],
            )
        )

        self.assertRedirects(
            response,
            reverse("edit_service_event", args=[self.event.id]),
        )
        assignment.refresh_from_db()
        self.assertFalse(assignment.is_active)


class ServiceEventPlannerBoundaryTests(ServiceEventPlannerTestBase):
    def test_planner_alone_gains_no_event_or_team_management_authority(self):
        self.assign()

        self.assertFalse(can_manage_service_events(self.planner))
        self.assertFalse(self.event.can_be_managed_by(self.planner))
        self.assertFalse(can_manage_ministry_team(self.planner, self.team))
        self.assertFalse(
            can_manage_team_assignment_for_team(self.planner, self.team)
        )

        original_audience_ids = list(
            self.event.audience_scope_links.values_list("unit_id", flat=True)
        )
        original_required_team_ids = list(
            self.event.required_team_links.values_list("ministry_team_id", flat=True)
        )
        self.client.force_login(self.planner)
        response = self.client.post(
            reverse("edit_service_event", args=[self.event.id]),
            {
                "title": "Forged title",
                "event_type": ServiceEvent.EVENT_OTHER,
                "start_datetime": "2030-01-01T10:00",
                "rotation_anchor_team": self.other_team.id,
                "audience_units": [self.outside_unit.id],
                "required_teams": [self.other_team.id],
                "status": ServiceEvent.STATUS_PUBLISHED,
            },
        )

        self.assertRedirects(response, reverse("service_event_list"))
        self.event.refresh_from_db()
        self.assertEqual(self.event.title, "主日聚会")
        self.assertEqual(self.event.rotation_anchor_team, self.team)
        self.assertEqual(
            list(self.event.audience_scope_links.values_list("unit_id", flat=True)),
            original_audience_ids,
        )
        self.assertEqual(
            list(
                self.event.required_team_links.values_list(
                    "ministry_team_id", flat=True
                )
            ),
            original_required_team_ids,
        )

    def test_planner_outside_audience_gets_no_visibility_or_membership(self):
        membership_count = ChurchStructureMembership.objects.count()
        audience_count = ServiceEventAudienceScope.objects.count()
        self.assign()

        self.assertEqual(ChurchStructureMembership.objects.count(), membership_count)
        self.assertEqual(ServiceEventAudienceScope.objects.count(), audience_count)
        self.assertFalse(self.event.can_be_seen_by(self.planner))
        self.assertNotIn(
            self.event.id,
            get_visible_service_events(self.planner).values_list("id", flat=True),
        )
        self.assertNotIn(
            self.event.id,
            member_visible_service_events_for(self.planner).values_list(
                "id", flat=True
            ),
        )
        calendar_items = provide_service_event_items(
            self.planner,
            timezone.now() - timedelta(days=1),
            timezone.now() + timedelta(days=10),
        )
        self.assertEqual(calendar_items, [])

        self.client.force_login(self.planner)
        detail_response = self.client.get(
            reverse("service_event_detail", args=[self.event.id])
        )
        self.assertRedirects(detail_response, reverse("service_event_list"))

    def test_planner_creation_has_no_serving_or_notification_side_effects(self):
        before = {
            "team_assignments": TeamAssignment.objects.count(),
            "assignment_members": TeamAssignmentMember.objects.count(),
            "team_memberships": TeamMembership.objects.count(),
            "required_teams": ServiceEventRequiredTeam.objects.count(),
            "audiences": ServiceEventAudienceScope.objects.count(),
            "structure_memberships": ChurchStructureMembership.objects.count(),
            "notifications": Notification.objects.count(),
            "bible_study_roles": BibleStudyMeetingRole.objects.count(),
        }

        self.assign()

        after = {
            "team_assignments": TeamAssignment.objects.count(),
            "assignment_members": TeamAssignmentMember.objects.count(),
            "team_memberships": TeamMembership.objects.count(),
            "required_teams": ServiceEventRequiredTeam.objects.count(),
            "audiences": ServiceEventAudienceScope.objects.count(),
            "structure_memberships": ChurchStructureMembership.objects.count(),
            "notifications": Notification.objects.count(),
            "bible_study_roles": BibleStudyMeetingRole.objects.count(),
        }
        self.assertEqual(after, before)
        self.assertFalse(
            user_has_explicit_serving_assignment_for_event(
                self.planner,
                self.event,
            )
        )
        today_rows, _show_all = get_gathering_rows_for_window(
            self.planner,
            timezone.now() - timedelta(days=1),
            timezone.now() + timedelta(days=8),
        )
        self.assertEqual(today_rows, [])

        self.client.force_login(self.planner)
        my_serving = self.client.get(reverse("my_serving"))
        self.assertEqual(my_serving.status_code, 200)
        self.assertNotContains(my_serving, "Sunday Service")
