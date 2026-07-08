"""Focused tests for the SERVING-EVENT-VISIBILITY.1A scheduler acknowledgement.

When a scheduler newly assigns a linked-user member who is outside the event's
audience scope, ``TeamAssignmentForm`` warns and requires an explicit,
non-persistent acknowledgement before saving. Assigning them grants read-only
serving-context visibility to that specific event; it never adds them to the
audience and creates no model field.
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import ChurchStructureMembership, ChurchStructureUnit
from events.models import ServiceEvent, ServiceEventAudienceScope
from ministry.forms import TeamAssignmentForm
from ministry.models import (
    MinistryTeam,
    TeamAssignment,
    TeamAssignmentMember,
    TeamMembership,
)

User = get_user_model()


class AssignmentAudienceAckBase(TestCase):
    def setUp(self):
        self.now = timezone.now()
        self.root = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_ROOT,
            code="CHURCH",
            name="全教会",
            name_en="Whole Church",
        )
        self.district = ChurchStructureUnit.objects.create(
            parent=self.root,
            unit_type=ChurchStructureUnit.UNIT_DISTRICT,
            code="NORTH",
            name="北区",
            name_en="North",
        )
        self.other_unit = ChurchStructureUnit.objects.create(
            parent=self.root,
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="SOUTH-1",
            name="南区一组",
            name_en="South 1",
        )

        self.team = MinistryTeam.objects.create(name="音响组", name_en="Audio")

        self.outside_user = self._member("outside", self.other_unit)
        self.inside_user = self._member("inside", self.district)
        self.outside_membership = TeamMembership.objects.create(
            team=self.team, user=self.outside_user, is_active=True
        )
        self.inside_membership = TeamMembership.objects.create(
            team=self.team, user=self.inside_user, is_active=True
        )
        # A display-name-only membership: no linked user to grant visibility to.
        self.display_only_membership = TeamMembership.objects.create(
            team=self.team, user=None, display_name="访客弟兄", is_active=True
        )

        self.event = self._event(self.district)
        self.scheduler = User.objects.create_user(
            "scheduler", password="pw12345!", is_superuser=True, is_staff=True
        )

    def _member(self, username, unit):
        user = User.objects.create_user(username, password="pw12345!")
        ChurchStructureMembership.objects.create(
            user=user,
            unit=unit,
            status=ChurchStructureMembership.STATUS_ACTIVE,
            is_primary=True,
            start_date=timezone.localdate() - timedelta(days=1),
        )
        return user

    def _event(self, audience_unit, status=ServiceEvent.STATUS_PUBLISHED):
        event = ServiceEvent.objects.create(
            title="主日聚会",
            title_en="Sunday Service",
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
            start_datetime=self.now + timedelta(days=1),
            status=status,
            location="主堂",
        )
        if audience_unit is not None:
            ServiceEventAudienceScope.objects.create(
                service_event=event, unit=audience_unit
            )
        return event

    def _form(self, memberships, ack=False):
        data = {
            "service_event": self.event.id,
            "ministry_team": self.team.id,
            "assigned_members": [m.id for m in memberships],
            "status": TeamAssignment.STATUS_SCHEDULED,
            "notes": "",
        }
        if ack:
            data["audience_override_ack"] = "on"
        return TeamAssignmentForm(
            data,
            language="en",
            manageable_teams=MinistryTeam.objects.all(),
        )


class AssignmentAudienceAckFormTests(AssignmentAudienceAckBase):
    def test_outside_member_blocks_without_ack(self):
        form = self._form([self.outside_membership])
        self.assertFalse(form.is_valid())
        self.assertIn("audience_override_ack", form.errors)
        self.assertIn("audience scope", " ".join(form.errors["audience_override_ack"]))

    def test_outside_member_saves_with_ack(self):
        form = self._form([self.outside_membership], ack=True)
        self.assertTrue(form.is_valid(), form.errors)

    def test_inside_member_needs_no_ack(self):
        form = self._form([self.inside_membership])
        self.assertTrue(form.is_valid(), form.errors)

    def test_display_name_only_member_needs_no_ack(self):
        # No linked user => no account to grant visibility to => no warning.
        form = self._form([self.display_only_membership])
        self.assertTrue(form.is_valid(), form.errors)

    def test_zero_audience_event_needs_no_ack(self):
        # An event with no defined audience scope has no audience to be "outside"
        # of, so the warning does not trigger (the serving read grant still
        # applies to whoever is assigned).
        self.event = self._event(audience_unit=None)
        form = self._form([self.outside_membership])
        self.assertTrue(form.is_valid(), form.errors)

    def test_ack_field_is_not_persisted_on_model(self):
        self.assertNotIn("audience_override_ack", [f.name for f in TeamAssignment._meta.get_fields()])


class AssignmentAudienceAckViewTests(AssignmentAudienceAckBase):
    def _post(self, memberships, ack=False):
        self.client.force_login(self.scheduler)
        data = {
            "service_event": self.event.id,
            "ministry_team": self.team.id,
            "assigned_members": [m.id for m in memberships],
            "status": TeamAssignment.STATUS_SCHEDULED,
            "notes": "",
        }
        if ack:
            data["audience_override_ack"] = "on"
        return self.client.post(reverse("create_team_assignment"), data)

    def test_post_without_ack_does_not_create_assignment(self):
        response = self._post([self.outside_membership])
        self.assertEqual(response.status_code, 200)
        self.assertIn("audience_override_ack", response.context["form"].errors)
        self.assertEqual(TeamAssignment.objects.count(), 0)
        self.assertEqual(TeamAssignmentMember.objects.count(), 0)

    def test_post_with_ack_creates_assignment_and_grants_specific_event_detail(self):
        response = self._post([self.outside_membership], ack=True)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(TeamAssignment.objects.count(), 1)
        member = TeamAssignmentMember.objects.get()
        self.assertEqual(member.membership_id, self.outside_membership.id)

        # The now-assigned outside user can open THIS event detail (read-only)...
        self.client.force_login(self.outside_user)
        ok = self.client.get(reverse("service_event_detail", args=[self.event.id]))
        self.assertEqual(ok.status_code, 200)
        self.assertFalse(ok.context["can_manage"])
        # ...but not a different event in that audience.
        other_event = self._event(self.district)
        denied = self.client.get(
            reverse("service_event_detail", args=[other_event.id])
        )
        self.assertEqual(denied.status_code, 302)

    def test_inside_member_saves_without_ack_via_view(self):
        response = self._post([self.inside_membership])
        self.assertEqual(response.status_code, 302)
        self.assertEqual(TeamAssignment.objects.count(), 1)


class AssignmentAudienceAckEditTests(AssignmentAudienceAckBase):
    """FU1: re-check members on edits that newly grant serving visibility."""

    def _orm_assignment(
        self, event, memberships, status=TeamAssignment.STATUS_SCHEDULED
    ):
        assignment = TeamAssignment.objects.create(
            service_event=event,
            ministry_team=self.team,
            status=status,
        )
        for membership in memberships:
            TeamAssignmentMember.objects.create(
                assignment=assignment, membership=membership
            )
        return assignment

    def _edit_form(
        self,
        assignment,
        service_event,
        memberships,
        status=TeamAssignment.STATUS_SCHEDULED,
        notes="edited",
        ack=False,
    ):
        data = {
            "service_event": service_event.id,
            "ministry_team": self.team.id,
            "assigned_members": [m.id for m in memberships],
            "status": status,
            "notes": notes,
        }
        if ack:
            data["audience_override_ack"] = "on"
        return TeamAssignmentForm(
            data,
            instance=assignment,
            language="en",
            manageable_teams=MinistryTeam.objects.all(),
        )

    def test_moving_to_event_excluding_existing_member_requires_ack(self):
        # inside_user is inside event A (district) but outside event B (other_unit).
        event_a = self.event  # district audience
        event_b = self._event(self.other_unit)
        assignment = self._orm_assignment(event_a, [self.inside_membership])

        form = self._edit_form(assignment, event_b, [self.inside_membership])
        self.assertFalse(form.is_valid())
        self.assertIn("audience_override_ack", form.errors)

    def test_moving_to_excluding_event_saves_with_ack(self):
        event_a = self.event
        event_b = self._event(self.other_unit)
        assignment = self._orm_assignment(event_a, [self.inside_membership])

        form = self._edit_form(
            assignment, event_b, [self.inside_membership], ack=True
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_editing_notes_same_event_does_not_renag_existing_member(self):
        # The member is already assigned to an event whose audience excludes them;
        # a notes-only edit that changes neither the event nor reactivates must not
        # re-nag.
        event = self._event(self.other_unit)  # inside_user (district) is outside
        assignment = self._orm_assignment(event, [self.inside_membership])

        form = self._edit_form(
            assignment, event, [self.inside_membership], notes="new notes"
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_editing_to_cancelled_does_not_require_ack(self):
        event = self._event(self.other_unit)  # inside_user is outside
        assignment = self._orm_assignment(event, [self.inside_membership])

        form = self._edit_form(
            assignment,
            event,
            [self.inside_membership],
            status=TeamAssignment.STATUS_CANCELLED,
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_creating_cancelled_assignment_does_not_require_ack(self):
        form = TeamAssignmentForm(
            {
                "service_event": self.event.id,
                "ministry_team": self.team.id,
                "assigned_members": [self.outside_membership.id],
                "status": TeamAssignment.STATUS_CANCELLED,
                "notes": "",
            },
            language="en",
            manageable_teams=MinistryTeam.objects.all(),
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_reactivating_cancelled_rechecks_all_members(self):
        # A cancelled assignment holding an outside member; reactivating it
        # re-enables serving visibility, so it must require acknowledgement.
        event = self._event(self.other_unit)  # inside_user is outside
        assignment = self._orm_assignment(
            event, [self.inside_membership], status=TeamAssignment.STATUS_CANCELLED
        )

        blocked = self._edit_form(
            assignment,
            event,
            [self.inside_membership],
            status=TeamAssignment.STATUS_SCHEDULED,
        )
        self.assertFalse(blocked.is_valid())
        self.assertIn("audience_override_ack", blocked.errors)

        acked = self._edit_form(
            assignment,
            event,
            [self.inside_membership],
            status=TeamAssignment.STATUS_SCHEDULED,
            ack=True,
        )
        self.assertTrue(acked.is_valid(), acked.errors)
