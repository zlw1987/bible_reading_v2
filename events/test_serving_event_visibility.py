"""Focused tests for SERVING-EVENT-VISIBILITY.1A.

An explicit ``TeamAssignmentMember`` serving assignment grants the assigned user
read-only serving-context visibility to *that specific* ServiceEvent detail, even
when the user is outside the event's ordinary audience scope. This is not audience
membership and never widens ordinary member-safe browse/calendar/list visibility,
which stays audience-only.
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import (
    ChurchRoleAssignment,
    ChurchStructureMembership,
    ChurchStructureUnit,
)
from core.module_registry import get_registered_module_keys
from events.calendar_provider import provide_service_event_items
from events.models import ServiceEvent, ServiceEventAudienceScope
from events.visibility import member_visible_service_events_for
from ministry.models import (
    MinistryTeam,
    TeamAssignment,
    TeamAssignmentMember,
    TeamMembership,
)
from ministry.permissions import user_has_explicit_serving_assignment_for_event

User = get_user_model()

ENABLED_WITHOUT_MINISTRY = [
    key for key in get_registered_module_keys() if key != "ministry"
]


class ServingEventVisibilityBase(TestCase):
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

        # The server belongs OUTSIDE the district audience but serves the event.
        self.server = self._member("server", self.other_unit)
        # An ordinary audience member (no serving assignment).
        self.audience_member = self._member("aud", self.district)

        self.team = MinistryTeam.objects.create(name="音响组", name_en="Audio")

    def _member(self, username, unit, **user_overrides):
        user = User.objects.create_user(
            username=username, password="pw12345!", **user_overrides
        )
        if unit is not None:
            ChurchStructureMembership.objects.create(
                user=user,
                unit=unit,
                status=ChurchStructureMembership.STATUS_ACTIVE,
                is_primary=True,
                start_date=timezone.localdate() - timedelta(days=1),
            )
        return user

    def _event(self, audience_unit="district", status=ServiceEvent.STATUS_PUBLISHED):
        event = ServiceEvent.objects.create(
            title="主日聚会",
            title_en="Sunday Service",
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
            start_datetime=self.now + timedelta(days=1),
            status=status,
            location="主堂",
        )
        unit = self.district if audience_unit == "district" else audience_unit
        if unit is not None:
            ServiceEventAudienceScope.objects.create(service_event=event, unit=unit)
        return event

    def _assign(self, user, event, team=None, status=TeamAssignment.STATUS_SCHEDULED):
        team = team or self.team
        # A user may hold only one active membership per team; reuse it so
        # multi-event assignments don't trip the unique-active-membership rule.
        membership = TeamMembership.objects.filter(
            team=team, user=user, is_active=True
        ).first() or TeamMembership.objects.create(
            team=team, user=user, is_active=True
        )
        assignment = TeamAssignment.objects.create(
            service_event=event,
            ministry_team=team,
            status=status,
        )
        return TeamAssignmentMember.objects.create(
            assignment=assignment, membership=membership
        )

    def _get_detail(self, user, event):
        self.client.force_login(user)
        return self.client.get(reverse("service_event_detail", args=[event.id]))


class ServingEventVisibilityHelperTests(ServingEventVisibilityBase):
    def test_assigned_outside_audience_user_matches_helper(self):
        event = self._event()
        self._assign(self.server, event)
        self.assertFalse(event.can_be_seen_by(self.server))
        self.assertTrue(
            user_has_explicit_serving_assignment_for_event(self.server, event)
        )

    def test_audience_member_without_assignment_does_not_match_helper(self):
        event = self._event()
        # Ordinary audience visibility, but no serving assignment => helper False.
        self.assertTrue(event.can_be_seen_by(self.audience_member))
        self.assertFalse(
            user_has_explicit_serving_assignment_for_event(
                self.audience_member, event
            )
        )

    def test_helper_scoped_to_the_specific_event(self):
        event = self._event()
        other_event = self._event()
        self._assign(self.server, event)
        self.assertTrue(
            user_has_explicit_serving_assignment_for_event(self.server, event)
        )
        self.assertFalse(
            user_has_explicit_serving_assignment_for_event(self.server, other_event)
        )

    def test_management_authority_not_matched_for_others_serving(self):
        event = self._event()
        self._assign(self.server, event)
        staff = self._member("staff", self.other_unit, is_staff=True)
        superuser = self._member("root_user", self.other_unit, is_superuser=True)
        manager = self._member("mgr", self.other_unit)
        ChurchRoleAssignment.objects.create(
            user=manager,
            role=ChurchRoleAssignment.ROLE_PASTOR,
            scope_type=ChurchRoleAssignment.SCOPE_GLOBAL,
        )
        for account in (staff, superuser, manager):
            self.assertFalse(
                user_has_explicit_serving_assignment_for_event(account, event),
                account.username,
            )

    def test_cancelled_assignment_does_not_match(self):
        event = self._event()
        self._assign(self.server, event, status=TeamAssignment.STATUS_CANCELLED)
        self.assertFalse(
            user_has_explicit_serving_assignment_for_event(self.server, event)
        )

    def test_inactive_membership_does_not_match(self):
        event = self._event()
        member = self._assign(self.server, event)
        membership = member.membership
        membership.is_active = False
        membership.save()
        self.assertFalse(
            user_has_explicit_serving_assignment_for_event(self.server, event)
        )

    def test_draft_and_cancelled_event_do_not_match(self):
        draft = self._event(status=ServiceEvent.STATUS_DRAFT)
        cancelled = self._event(status=ServiceEvent.STATUS_CANCELLED)
        self._assign(self.server, draft)
        self._assign(self.server, cancelled)
        self.assertFalse(
            user_has_explicit_serving_assignment_for_event(self.server, draft)
        )
        self.assertFalse(
            user_has_explicit_serving_assignment_for_event(self.server, cancelled)
        )

    def test_disabled_ministry_does_not_match_and_runs_no_query(self):
        event = self._event()
        self._assign(self.server, event)
        with override_settings(CMS_ENABLED_MODULES=ENABLED_WITHOUT_MINISTRY):
            with self.assertNumQueries(0):
                result = user_has_explicit_serving_assignment_for_event(
                    self.server, event
                )
        self.assertFalse(result)


class ServingEventDetailGateTests(ServingEventVisibilityBase):
    def test_assigned_outside_audience_user_can_open_detail_read_only(self):
        event = self._event()
        self._assign(self.server, event)
        response = self._get_detail(self.server, event)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["event"].id, event.id)
        # Read-only: no management / coverage surfaces for a serving-only viewer.
        self.assertFalse(response.context["can_manage"])
        self.assertFalse(response.context["can_view_coverage"])
        self.assertIsNone(response.context["event_coverage"])

    def test_assigned_user_cannot_open_different_event_in_that_audience(self):
        event = self._event()
        other_event = self._event()
        self._assign(self.server, event)
        response = self._get_detail(self.server, other_event)
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("service_event_list"), response.url)

    def test_audience_member_detail_is_ordinary_visibility(self):
        event = self._event()
        response = self._get_detail(self.audience_member, event)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["can_manage"])

    def test_cancelled_assignment_does_not_open_detail(self):
        event = self._event()
        self._assign(self.server, event, status=TeamAssignment.STATUS_CANCELLED)
        response = self._get_detail(self.server, event)
        self.assertEqual(response.status_code, 302)

    def test_draft_event_not_opened_through_serving(self):
        draft = self._event(status=ServiceEvent.STATUS_DRAFT)
        self._assign(self.server, draft)
        response = self._get_detail(self.server, draft)
        self.assertEqual(response.status_code, 302)

    def test_disabled_ministry_does_not_open_detail_through_serving(self):
        event = self._event()
        self._assign(self.server, event)
        with override_settings(CMS_ENABLED_MODULES=ENABLED_WITHOUT_MINISTRY):
            response = self._get_detail(self.server, event)
        self.assertEqual(response.status_code, 302)


class MemberSafeProviderUnchangedTests(ServingEventVisibilityBase):
    """Serving must not widen the ordinary member-safe calendar/list visibility."""

    def test_calendar_provider_stays_audience_only(self):
        event = self._event()
        self._assign(self.server, event)
        range_start = self.now - timedelta(days=10)
        range_end = self.now + timedelta(days=20)
        # Server is outside the audience; serving grants specific-event detail but
        # never a calendar item.
        server_items = provide_service_event_items(self.server, range_start, range_end)
        self.assertEqual(server_items, [])
        # The audience member still sees it on the calendar (unchanged behavior).
        audience_items = provide_service_event_items(
            self.audience_member, range_start, range_end
        )
        self.assertEqual({i.source_id for i in audience_items}, {event.id})

    def test_member_visible_queryset_stays_audience_only(self):
        event = self._event()
        self._assign(self.server, event)
        self.assertNotIn(
            event.id,
            member_visible_service_events_for(self.server).values_list(
                "id", flat=True
            ),
        )
        self.assertIn(
            event.id,
            member_visible_service_events_for(self.audience_member).values_list(
                "id", flat=True
            ),
        )
