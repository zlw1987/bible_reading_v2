"""Focused MO-S.6D-1D-B Worship TeamAssignment write enforcement tests."""

from unittest.mock import patch

from django.contrib import admin
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import ChurchStructureUnit
from events.models import (
    ServiceEvent,
    ServiceEventAudienceScope,
    ServiceEventRequiredTeam,
)
from events.views import cancel_non_final_assignments_for_event

from .forms import TeamAssignmentForm, TeamScheduleAssignmentForm
from .models import (
    MinistryTeam,
    MinistryTeamParentLink,
    TeamAssignment,
    TeamAssignmentMember,
    TeamMembership,
)
from .services.worship_assignment_guard import (
    lock_service_events_for_worship_assignment_write,
    worship_assignment_serialization_event_ids,
)


class WorshipAssignmentEnforcementTests(TestCase):
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
        self.cm_pool = self.pool("Chinese Worship Pool", self.cm)
        self.em_pool = self.pool("English Worship Pool", self.em)
        self.c1 = self.team("Chinese Worship C1", self.cm_pool)
        self.c2 = self.team("Chinese Worship C2", self.cm_pool)
        self.e1 = self.team("English Worship E1", self.em_pool)
        self.av = MinistryTeam.objects.create(
            name="Projection", name_en="Projection"
        )
        self.event = ServiceEvent.objects.create(
            title="Sunday Worship",
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
            start_datetime=timezone.now() + timezone.timedelta(days=7),
            status=ServiceEvent.STATUS_PUBLISHED,
            rotation_anchor_team=self.c1,
        )
        ServiceEventAudienceScope.objects.create(
            service_event=self.event, unit=self.cm
        )
        self.staff = User.objects.create_user(
            username="assignment_staff", password="pw", is_staff=True
        )
        self.member_user = User.objects.create_user(
            username="worship_member", password="pw"
        )
        self.c1_membership = TeamMembership.objects.create(
            team=self.c1, user=self.member_user
        )
        self.c2_membership = TeamMembership.objects.create(
            team=self.c2, display_name="C2 Member"
        )
        self.av_membership = TeamMembership.objects.create(
            team=self.av, user=self.member_user
        )

    def pool(self, name, anchor):
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

    def team(self, name, parent):
        team = MinistryTeam.objects.create(name=name, name_en=name)
        MinistryTeamParentLink.objects.create(
            child_team=team,
            parent_team=parent,
            is_primary=True,
        )
        return team

    def stored_assignment(self, team, status=TeamAssignment.STATUS_SCHEDULED):
        assignment = TeamAssignment(
            service_event=self.event,
            ministry_team=team,
            status=status,
        )
        TeamAssignment.objects.bulk_create([assignment])
        return assignment

    def assert_rejected(self, assignment):
        with self.assertRaises(ValidationError):
            assignment.save()

    def assert_identity_rejected_unchanged(
        self,
        assignment,
        *,
        service_event=None,
        ministry_team=None,
    ):
        original = TeamAssignment.objects.values(
            "service_event_id", "ministry_team_id", "status"
        ).get(pk=assignment.pk)
        if service_event is not None:
            assignment.service_event = service_event
        if ministry_team is not None:
            assignment.ministry_team = ministry_team
        try:
            assignment.save()
        except ValidationError:
            pass
        else:
            # Keep subtests isolated even when reproducing the pre-fix loophole.
            TeamAssignment.objects.filter(pk=assignment.pk).update(**original)
            self.fail("Worship-boundary identity retarget was not rejected.")
        self.assertEqual(
            TeamAssignment.objects.values(
                "service_event_id", "ministry_team_id", "status"
            ).get(pk=assignment.pk),
            original,
        )

    def test_selected_team_current_assignment_is_allowed(self):
        assignment = TeamAssignment.objects.create(
            service_event=self.event,
            ministry_team=self.c1,
            status=TeamAssignment.STATUS_SCHEDULED,
        )
        self.assertIsNotNone(assignment.pk)

    def test_current_worship_save_uses_exact_serviceevent_lock_boundary(self):
        with patch(
            "ministry.services.worship_assignment_guard."
            "lock_service_events_for_worship_assignment_write",
            wraps=lock_service_events_for_worship_assignment_write,
        ) as lock_boundary:
            assignment = TeamAssignment.objects.create(
                service_event=self.event,
                ministry_team=self.c1,
                status=TeamAssignment.STATUS_SCHEDULED,
            )

        lock_boundary.assert_called_once()
        locked_proposal = lock_boundary.call_args.args[0]
        self.assertEqual(
            worship_assignment_serialization_event_ids(locked_proposal),
            (self.event.id,),
        )
        self.assertEqual(
            lock_boundary.call_args.kwargs["using"], "default"
        )

    def test_safe_transition_out_needs_no_worship_serialization_event(self):
        assignment = TeamAssignment.objects.create(
            service_event=self.event,
            ministry_team=self.c1,
            status=TeamAssignment.STATUS_SCHEDULED,
        )
        assignment.status = TeamAssignment.STATUS_CANCELLED
        self.assertEqual(
            worship_assignment_serialization_event_ids(assignment), ()
        )
        assignment.save()
        assignment.refresh_from_db()
        self.assertEqual(assignment.status, TeamAssignment.STATUS_CANCELLED)

    def test_off_team_no_selection_and_invalid_selection_are_rejected(self):
        self.assert_rejected(
            TeamAssignment(
                service_event=self.event,
                ministry_team=self.c2,
                status=TeamAssignment.STATUS_SCHEDULED,
            )
        )
        self.event.rotation_anchor_team = None
        self.event.save(update_fields=["rotation_anchor_team", "updated_at"])
        self.assert_rejected(
            TeamAssignment(
                service_event=self.event,
                ministry_team=self.c1,
                status=TeamAssignment.STATUS_PREPARED,
            )
        )
        self.event.rotation_anchor_team = self.av
        self.event.save(update_fields=["rotation_anchor_team", "updated_at"])
        self.assert_rejected(
            TeamAssignment(
                service_event=self.event,
                ministry_team=self.c1,
                status=TeamAssignment.STATUS_CONFIRMED,
            )
        )

    def test_inapplicable_pool_assignment_is_rejected(self):
        self.assert_rejected(
            TeamAssignment(
                service_event=self.event,
                ministry_team=self.e1,
                status=TeamAssignment.STATUS_SCHEDULED,
            )
        )

    def test_duplicate_current_selected_assignment_is_rejected(self):
        TeamAssignment.objects.create(
            service_event=self.event,
            ministry_team=self.c1,
            status=TeamAssignment.STATUS_SCHEDULED,
        )
        self.assert_rejected(
            TeamAssignment(
                service_event=self.event,
                ministry_team=self.c1,
                status=TeamAssignment.STATUS_PREPARED,
            )
        )

    def test_cancelled_and_completed_history_do_not_count_as_current(self):
        TeamAssignment.objects.create(
            service_event=self.event,
            ministry_team=self.c2,
            status=TeamAssignment.STATUS_CANCELLED,
        )
        TeamAssignment.objects.create(
            service_event=self.event,
            ministry_team=self.e1,
            status=TeamAssignment.STATUS_COMPLETED,
        )
        current = TeamAssignment.objects.create(
            service_event=self.event,
            ministry_team=self.c1,
            status=TeamAssignment.STATUS_SCHEDULED,
        )
        self.assertIsNotNone(current.pk)

    def test_conflicting_current_row_can_cancel_or_complete_in_place(self):
        for target_status in (
            TeamAssignment.STATUS_CANCELLED,
            TeamAssignment.STATUS_COMPLETED,
        ):
            with self.subTest(target_status=target_status):
                assignment = self.stored_assignment(self.c2)
                assignment.status = target_status
                assignment.save()
                assignment.refresh_from_db()
                self.assertEqual(assignment.status, target_status)
                assignment.delete()

    def test_historical_worship_row_cannot_be_retargeted(self):
        assignment = TeamAssignment.objects.create(
            service_event=self.event,
            ministry_team=self.c1,
            status=TeamAssignment.STATUS_COMPLETED,
        )
        assignment.ministry_team = self.c2
        self.assert_rejected(assignment)

    def test_consistent_current_worship_identity_cannot_cross_team_boundary(self):
        for status in (
            TeamAssignment.STATUS_SCHEDULED,
            TeamAssignment.STATUS_PREPARED,
            TeamAssignment.STATUS_CONFIRMED,
        ):
            with self.subTest(status=status, target="downstream"):
                assignment = TeamAssignment.objects.create(
                    service_event=self.event,
                    ministry_team=self.c1,
                    status=status,
                )
                self.assert_identity_rejected_unchanged(
                    assignment, ministry_team=self.av
                )
                assignment.delete()
            with self.subTest(status=status, target="worship"):
                assignment = TeamAssignment.objects.create(
                    service_event=self.event,
                    ministry_team=self.c1,
                    status=status,
                )
                self.assert_identity_rejected_unchanged(
                    assignment, ministry_team=self.c2
                )
                assignment.delete()

    def test_consistent_current_worship_identity_cannot_move_event(self):
        other_event = ServiceEvent.objects.create(
            title="Other Sunday Worship",
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
            start_datetime=timezone.now() + timezone.timedelta(days=14),
            status=ServiceEvent.STATUS_PUBLISHED,
            rotation_anchor_team=self.c1,
        )
        ServiceEventAudienceScope.objects.create(
            service_event=other_event, unit=self.cm
        )
        for status in (
            TeamAssignment.STATUS_SCHEDULED,
            TeamAssignment.STATUS_PREPARED,
            TeamAssignment.STATUS_CONFIRMED,
        ):
            with self.subTest(status=status):
                assignment = TeamAssignment.objects.create(
                    service_event=self.event,
                    ministry_team=self.c1,
                    status=status,
                )
                self.assert_identity_rejected_unchanged(
                    assignment, service_event=other_event
                )
                assignment.delete()

    def test_downstream_assignment_cannot_retarget_into_worship_identity(self):
        assignment = TeamAssignment.objects.create(
            service_event=self.event,
            ministry_team=self.av,
            status=TeamAssignment.STATUS_SCHEDULED,
        )
        self.assert_identity_rejected_unchanged(
            assignment, ministry_team=self.c1
        )

    def test_downstream_identity_retarget_remains_unchanged(self):
        downstream_b = MinistryTeam.objects.create(
            name="Audio", name_en="Audio"
        )
        other_event = ServiceEvent.objects.create(
            title="Other Gathering",
            event_type=ServiceEvent.EVENT_OTHER,
            start_datetime=timezone.now() + timezone.timedelta(days=14),
            status=ServiceEvent.STATUS_PUBLISHED,
        )
        assignment = TeamAssignment.objects.create(
            service_event=self.event,
            ministry_team=self.av,
            status=TeamAssignment.STATUS_SCHEDULED,
        )
        assignment.service_event = other_event
        assignment.ministry_team = downstream_b
        assignment.save()
        assignment.refresh_from_db()
        self.assertEqual(assignment.service_event, other_event)
        self.assertEqual(assignment.ministry_team, downstream_b)

    def test_invalid_current_row_cannot_be_retargeted_as_repair(self):
        assignment = self.stored_assignment(self.c2)
        assignment.ministry_team = self.c1
        self.assert_rejected(assignment)

    def test_cancelled_row_reactivation_into_invalid_state_is_rejected(self):
        assignment = TeamAssignment.objects.create(
            service_event=self.event,
            ministry_team=self.c2,
            status=TeamAssignment.STATUS_CANCELLED,
        )
        assignment.status = TeamAssignment.STATUS_SCHEDULED
        self.assert_rejected(assignment)

    def test_downstream_assignment_behavior_is_unchanged(self):
        assignment = TeamAssignment.objects.create(
            service_event=self.event,
            ministry_team=self.av,
            status=TeamAssignment.STATUS_SCHEDULED,
        )
        assignment.status = TeamAssignment.STATUS_CONFIRMED
        assignment.save()
        self.assertEqual(assignment.status, TeamAssignment.STATUS_CONFIRMED)

    def test_generic_form_enforces_with_bilingual_error(self):
        form = TeamAssignmentForm(
            data={
                "service_event": self.event.id,
                "ministry_team": self.c2.id,
                "assigned_members": [],
                "status": TeamAssignment.STATUS_SCHEDULED,
                "notes": "",
            },
            language="zh",
            manageable_teams=MinistryTeam.objects.all(),
        )
        self.assertFalse(form.is_valid())
        self.assertIn("敬拜排班", form.non_field_errors().as_text())

    def test_generic_form_and_view_reject_current_worship_retarget(self):
        assignment = TeamAssignment.objects.create(
            service_event=self.event,
            ministry_team=self.c1,
            status=TeamAssignment.STATUS_SCHEDULED,
        )
        data = {
            "service_event": self.event.id,
            "ministry_team": self.av.id,
            "assigned_members": [],
            "status": TeamAssignment.STATUS_SCHEDULED,
            "notes": "",
        }
        form = TeamAssignmentForm(
            data=data,
            instance=assignment,
            language="en",
            manageable_teams=MinistryTeam.objects.all(),
        )
        self.assertFalse(form.is_valid())
        self.assertIn("cannot be moved", form.non_field_errors().as_text())

        self.client.force_login(self.staff)
        response = self.client.post(
            reverse("edit_team_assignment", args=[assignment.id]), data
        )
        self.assertEqual(response.status_code, 200)
        assignment.refresh_from_db()
        self.assertEqual(assignment.service_event, self.event)
        self.assertEqual(assignment.ministry_team, self.c1)

    def test_team_schedule_form_enforces_with_bilingual_error(self):
        instance = TeamAssignment(
            service_event=self.event,
            ministry_team=self.c2,
        )
        form = TeamScheduleAssignmentForm(
            data={
                "assigned_members": [],
                "status": TeamAssignment.STATUS_SCHEDULED,
                "notes": "",
            },
            instance=instance,
            language="zh",
            team=self.c2,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("敬拜排班", form.non_field_errors().as_text())

    def test_generic_and_team_schedule_views_reject_off_team_writes(self):
        self.client.force_login(self.staff)
        generic = self.client.post(
            reverse("create_team_assignment"),
            {
                "service_event": self.event.id,
                "ministry_team": self.c2.id,
                "assigned_members": [],
                "status": TeamAssignment.STATUS_SCHEDULED,
                "notes": "",
            },
        )
        self.assertEqual(generic.status_code, 200)
        self.assertFalse(TeamAssignment.objects.exists())

        ServiceEventRequiredTeam.objects.create(
            service_event=self.event, ministry_team=self.c2
        )
        schedule = self.client.post(
            f"{reverse('team_schedule', args=[self.c2.id])}?event={self.event.id}",
            {
                "assigned_members": [],
                "status": TeamAssignment.STATUS_SCHEDULED,
                "notes": "",
            },
        )
        self.assertEqual(schedule.status_code, 200)
        self.assertFalse(TeamAssignment.objects.exists())

    def test_team_assignment_admin_uses_normal_validation(self):
        model_admin = admin.site._registry[TeamAssignment]
        request = RequestFactory().post("/admin/ministry/teamassignment/add/")
        request.user = self.staff
        form_class = model_admin.get_form(request)
        form = form_class(
            data={
                "service_event": self.event.id,
                "ministry_team": self.c2.id,
                "status": TeamAssignment.STATUS_SCHEDULED,
                "notes": "",
                "created_by": "",
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("Worship assignment", form.non_field_errors().as_text())

    def test_team_assignment_admin_rejects_valid_current_worship_retarget(self):
        assignment = TeamAssignment.objects.create(
            service_event=self.event,
            ministry_team=self.c1,
            status=TeamAssignment.STATUS_SCHEDULED,
        )
        model_admin = admin.site._registry[TeamAssignment]
        request = RequestFactory().post(
            f"/admin/ministry/teamassignment/{assignment.id}/change/"
        )
        request.user = self.staff
        form_class = model_admin.get_form(request, assignment)
        form = form_class(
            data={
                "service_event": self.event.id,
                "ministry_team": self.av.id,
                "status": TeamAssignment.STATUS_SCHEDULED,
                "notes": "",
                "created_by": "",
            },
            instance=assignment,
        )
        self.assertFalse(form.is_valid())
        self.assertIn(
            "cannot be moved", form.non_field_errors().as_text()
        )
        assignment.refresh_from_db()
        self.assertEqual(assignment.service_event, self.event)
        self.assertEqual(assignment.ministry_team, self.c1)

    def test_valid_worship_confirmation_updates_member_and_parent(self):
        assignment = TeamAssignment.objects.create(
            service_event=self.event,
            ministry_team=self.c1,
            status=TeamAssignment.STATUS_SCHEDULED,
        )
        member = TeamAssignmentMember.objects.create(
            assignment=assignment, membership=self.c1_membership
        )
        self.client.force_login(self.member_user)
        response = self.client.post(
            reverse("confirm_team_assignment", args=[assignment.id]),
            {"confirmation_note": "Ready"},
        )
        self.assertEqual(response.status_code, 302)
        member.refresh_from_db()
        assignment.refresh_from_db()
        self.assertIsNotNone(member.confirmed_at)
        self.assertEqual(assignment.status, TeamAssignment.STATUS_CONFIRMED)

    def test_invalid_worship_confirmation_has_no_partial_mutation(self):
        assignment = self.stored_assignment(self.c2)
        member_user = User.objects.create_user(
            username="off_team_member", password="pw"
        )
        membership = TeamMembership.objects.create(
            team=self.c2, user=member_user
        )
        member = TeamAssignmentMember.objects.create(
            assignment=assignment, membership=membership
        )
        self.client.force_login(member_user)
        response = self.client.post(
            reverse("confirm_team_assignment", args=[assignment.id]),
            {"confirmation_note": "Ready"},
        )
        self.assertEqual(response.status_code, 302)
        member.refresh_from_db()
        assignment.refresh_from_db()
        self.assertIsNone(member.confirmed_at)
        self.assertEqual(assignment.status, TeamAssignment.STATUS_SCHEDULED)

    def test_downstream_confirmation_still_works(self):
        assignment = TeamAssignment.objects.create(
            service_event=self.event,
            ministry_team=self.av,
            status=TeamAssignment.STATUS_SCHEDULED,
        )
        member = TeamAssignmentMember.objects.create(
            assignment=assignment, membership=self.av_membership
        )
        self.client.force_login(self.member_user)
        self.client.post(
            reverse("confirm_team_assignment", args=[assignment.id]), {}
        )
        member.refresh_from_db()
        self.assertIsNotNone(member.confirmed_at)

    def test_assignment_cancel_view_remains_safe_repair(self):
        assignment = self.stored_assignment(self.c2)
        self.client.force_login(self.staff)
        response = self.client.post(
            reverse("cancel_team_assignment", args=[assignment.id])
        )
        self.assertEqual(response.status_code, 302)
        assignment.refresh_from_db()
        self.assertEqual(assignment.status, TeamAssignment.STATUS_CANCELLED)

    def test_service_event_bulk_cancellation_remains_safe(self):
        assignment = self.stored_assignment(self.c2)
        updated = cancel_non_final_assignments_for_event(self.event)
        self.assertEqual(updated, 1)
        assignment.refresh_from_db()
        self.event.refresh_from_db()
        self.assertEqual(assignment.status, TeamAssignment.STATUS_CANCELLED)
        self.assertEqual(self.event.rotation_anchor_team, self.c1)

    def test_member_admin_cannot_change_parent_ownership_fields(self):
        model_admin = admin.site._registry[TeamAssignmentMember]
        request = RequestFactory().get(
            "/admin/ministry/teamassignmentmember/add/"
        )
        request.user = self.staff
        form_class = model_admin.get_form(request)
        self.assertNotIn("service_event", form_class.base_fields)
        self.assertNotIn("ministry_team", form_class.base_fields)
        self.assertNotIn("status", form_class.base_fields)
