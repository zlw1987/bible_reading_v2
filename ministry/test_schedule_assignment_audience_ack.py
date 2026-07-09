"""Focused tests for the SERVING-EVENT-VISIBILITY.1B scheduler acknowledgement.

``TeamScheduleAssignmentForm`` (the team-schedule page path) can create/update a
``TeamAssignment`` and sync its assigned members, so it grants the same
serving-context visibility as ``TeamAssignmentForm``. This slice mirrors the 1A
outside-audience warning/acknowledgement on that path: assigning a linked-user
member outside the event's defined audience scope warns and requires an explicit,
non-persistent acknowledgement before saving. It never adds the member to the
audience and creates no model field.

The ServiceEvent is fixed by the instance on this form (not an editable field),
so there is no "event changed" case; re-checks happen on create or reactivation.
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import ChurchStructureMembership, ChurchStructureUnit
from events.models import (
    ServiceEvent,
    ServiceEventAudienceScope,
    ServiceEventRequiredTeam,
)
from ministry.forms import TeamScheduleAssignmentForm
from ministry.models import (
    MinistryTeam,
    TeamAssignment,
    TeamAssignmentMember,
    TeamMembership,
)

User = get_user_model()


class ScheduleAssignmentAudienceAckBase(TestCase):
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

    def _new_instance(self, event=None):
        return TeamAssignment(
            service_event=event or self.event,
            ministry_team=self.team,
            status=TeamAssignment.STATUS_SCHEDULED,
        )

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

    def _form(
        self,
        instance,
        memberships,
        status=TeamAssignment.STATUS_SCHEDULED,
        notes="",
        ack=False,
    ):
        data = {
            "assigned_members": [m.id for m in memberships],
            "status": status,
            "notes": notes,
        }
        if ack:
            data["audience_override_ack"] = "on"
        return TeamScheduleAssignmentForm(
            data,
            instance=instance,
            language="en",
            team=self.team,
        )


class ScheduleAssignmentAudienceAckFormTests(ScheduleAssignmentAudienceAckBase):
    def test_new_outside_member_blocks_without_ack(self):
        form = self._form(self._new_instance(), [self.outside_membership])
        self.assertFalse(form.is_valid())
        self.assertIn("audience_override_ack", form.errors)
        self.assertIn(
            "audience scope", " ".join(form.errors["audience_override_ack"])
        )

    def test_new_outside_member_saves_with_ack(self):
        form = self._form(
            self._new_instance(), [self.outside_membership], ack=True
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_inside_member_needs_no_ack(self):
        form = self._form(self._new_instance(), [self.inside_membership])
        self.assertTrue(form.is_valid(), form.errors)

    def test_display_name_only_member_needs_no_ack(self):
        form = self._form(self._new_instance(), [self.display_only_membership])
        self.assertTrue(form.is_valid(), form.errors)

    def test_zero_audience_event_needs_no_ack(self):
        event = self._event(audience_unit=None)
        form = self._form(self._new_instance(event), [self.outside_membership])
        self.assertTrue(form.is_valid(), form.errors)

    def test_cancelled_submission_does_not_require_ack(self):
        form = self._form(
            self._new_instance(),
            [self.outside_membership],
            status=TeamAssignment.STATUS_CANCELLED,
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_ack_field_is_not_persisted_on_model(self):
        self.assertNotIn(
            "audience_override_ack",
            [f.name for f in TeamAssignment._meta.get_fields()],
        )

    def test_same_event_edit_does_not_renag_existing_member(self):
        # Member already assigned to an event whose audience excludes them; a
        # notes-only edit that changes neither the event nor reactivates must
        # not re-nag.
        event = self._event(self.other_unit)  # inside_user (district) is outside
        assignment = self._orm_assignment(event, [self.inside_membership])
        form = self._form(assignment, [self.inside_membership], notes="new notes")
        self.assertTrue(form.is_valid(), form.errors)

    def test_editing_to_cancelled_does_not_require_ack(self):
        event = self._event(self.other_unit)  # inside_user is outside
        assignment = self._orm_assignment(event, [self.inside_membership])
        form = self._form(
            assignment,
            [self.inside_membership],
            status=TeamAssignment.STATUS_CANCELLED,
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_reactivating_cancelled_rechecks_all_members(self):
        # A cancelled assignment holding an outside member; reactivating it
        # re-enables serving visibility, so it must require acknowledgement.
        event = self._event(self.other_unit)  # inside_user is outside
        assignment = self._orm_assignment(
            event,
            [self.inside_membership],
            status=TeamAssignment.STATUS_CANCELLED,
        )
        blocked = self._form(
            assignment,
            [self.inside_membership],
            status=TeamAssignment.STATUS_SCHEDULED,
        )
        self.assertFalse(blocked.is_valid())
        self.assertIn("audience_override_ack", blocked.errors)

        acked = self._form(
            assignment,
            [self.inside_membership],
            status=TeamAssignment.STATUS_SCHEDULED,
            ack=True,
        )
        self.assertTrue(acked.is_valid(), acked.errors)

    def test_adding_new_outside_member_to_existing_assignment_requires_ack(self):
        # An existing same-event edit that newly adds an outside member must nag
        # for that newly added member only.
        assignment = self._orm_assignment(self.event, [self.inside_membership])
        form = self._form(
            assignment, [self.inside_membership, self.outside_membership]
        )
        self.assertFalse(form.is_valid())
        self.assertIn("audience_override_ack", form.errors)


class ScheduleAssignmentAudienceAckViewTests(ScheduleAssignmentAudienceAckBase):
    """Exercise the acknowledgement through the team_schedule POST path."""

    def setUp(self):
        super().setUp()
        # Make the event display on the schedule grid so it is schedulable.
        ServiceEventRequiredTeam.objects.create(
            service_event=self.event, ministry_team=self.team
        )
        self.url = (
            reverse("team_schedule", args=[self.team.id])
            + f"?event={self.event.id}"
        )

    def _post(self, memberships, ack=False):
        self.client.force_login(self.scheduler)
        data = {
            "assigned_members": [m.id for m in memberships],
            "status": TeamAssignment.STATUS_SCHEDULED,
            "notes": "",
        }
        if ack:
            data["audience_override_ack"] = "on"
        return self.client.post(self.url, data)

    def test_post_without_ack_does_not_create_assignment(self):
        response = self._post([self.outside_membership])
        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "audience_override_ack", response.context["active_form"].errors
        )
        self.assertEqual(TeamAssignment.objects.count(), 0)
        self.assertEqual(TeamAssignmentMember.objects.count(), 0)

    def test_post_with_ack_creates_assignment(self):
        response = self._post([self.outside_membership], ack=True)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(TeamAssignment.objects.count(), 1)
        member = TeamAssignmentMember.objects.get()
        self.assertEqual(member.membership_id, self.outside_membership.id)

    def test_inside_member_saves_without_ack_via_view(self):
        response = self._post([self.inside_membership])
        self.assertEqual(response.status_code, 302)
        self.assertEqual(TeamAssignment.objects.count(), 1)
