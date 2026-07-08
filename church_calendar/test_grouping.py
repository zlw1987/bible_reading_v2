"""Focused tests for CHURCH-CALENDAR.2A-FU4 occurrence grouping.

The same real ServiceEvent must render as ONE grouped occurrence when the base
(audience-visible) ServiceEvent row and the viewer's own ``my_serving`` rows
refer to the same ServiceEvent, instead of one base row plus one row per serving
assignment. Grouping is presentation-only and keyed on the underlying object
identity (``occurrence_key``), never on title/time/location strings.

These tests assert the product boundaries too: grouping never widens visibility
(serving stays explicit; the base provider stays audience-only), other users and
management authority never see the viewer's serving subitems, an assigned server
outside the ordinary audience still sees the occurrence (SERVING-EVENT-
VISIBILITY.1A), a non-assigned non-audience user still cannot, unrelated events
sharing a title/time are never merged, and the calendar stays read-only.
"""

from datetime import datetime, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import (
    ChurchRoleAssignment,
    ChurchStructureMembership,
    ChurchStructureUnit,
)
from events.models import ServiceEvent, ServiceEventAudienceScope
from ministry.models import (
    MinistryTeam,
    TeamAssignment,
    TeamAssignmentMember,
    TeamMembership,
)

from .providers import ITEM_TYPE_MY_SERVING, ITEM_TYPE_SERVICE_EVENT

User = get_user_model()


class GroupingBase(TestCase):
    def setUp(self):
        self.today = timezone.localdate()
        self.year = self.today.year
        self.month = self.today.month

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

        self.server = User.objects.create_user("server", password="pw12345!")
        self.other = User.objects.create_user("other", password="pw12345!")

        self.camera = MinistryTeam.objects.create(name="摄像团队", name_en="Camera Team")
        self.lighting = MinistryTeam.objects.create(name="灯光组", name_en="Lighting Team")

    # -- local aware datetime anchored in the current month -------------------
    def _at(self, day, hour=9, minute=0):
        return timezone.make_aware(
            datetime(self.year, self.month, day, hour, minute),
            timezone.get_current_timezone(),
        )

    def _in_audience(self, user, unit=None):
        """Give ``user`` an active primary membership so audience matches."""
        ChurchStructureMembership.objects.create(
            user=user,
            unit=unit or self.district,
            status=ChurchStructureMembership.STATUS_ACTIVE,
            is_primary=True,
            start_date=self.today - timedelta(days=1),
        )

    def _event(self, start=None, title="主日崇拜", title_en="Sunday Worship", audience=True):
        event = ServiceEvent.objects.create(
            title=title,
            title_en=title_en,
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
            start_datetime=start or self._at(12, 9),
            status=ServiceEvent.STATUS_PUBLISHED,
            location="主堂",
        )
        if audience:
            ServiceEventAudienceScope.objects.create(
                service_event=event, unit=self.district
            )
        return event

    def _serving(self, user, event, team):
        membership = TeamMembership.objects.filter(
            team=team, user=user, is_active=True
        ).first() or TeamMembership.objects.create(team=team, user=user, is_active=True)
        assignment = TeamAssignment.objects.create(
            service_event=event,
            ministry_team=team,
            status=TeamAssignment.STATUS_SCHEDULED,
        )
        return TeamAssignmentMember.objects.create(
            assignment=assignment, membership=membership
        )

    # -- request helpers ------------------------------------------------------
    def _month(self, user=None, **params):
        self.client.force_login(user or self.server)
        return self.client.get(reverse("church_calendar_month"), params)

    def _day(self, day, user=None, **params):
        self.client.force_login(user or self.server)
        return self.client.get(
            reverse("church_calendar_day", args=[self.year, self.month, day]),
            params,
        )

    def _cell(self, response, day):
        for week in response.context["calendar_weeks"]:
            for cell in week:
                if cell["in_month"] and cell["date"].day == day:
                    return cell
        return None


class MonthGroupingTests(GroupingBase):
    def test_visible_base_plus_two_serving_render_one_grouped_row(self):
        # Test 1: audience-visible base ServiceEvent + two own serving rows.
        self._in_audience(self.server)
        event = self._event(start=self._at(12, 9))
        self._serving(self.server, event, self.camera)
        self._serving(self.server, event, self.lighting)

        cell = self._cell(self._month(), 12)
        # Exactly one occurrence row for the event, not three.
        self.assertEqual(cell["total_count"], 1)
        self.assertEqual(len(cell["items"]), 1)
        self.assertEqual(cell["more_count"], 0)
        occ = cell["items"][0]
        # Grouped under the base ServiceEvent identity and type.
        self.assertEqual(occ.item_type, ITEM_TYPE_SERVICE_EVENT)
        self.assertEqual(occ.source_id, event.id)
        self.assertEqual(occ.serving_count, 2)
        self.assertEqual(
            {s.role for s in occ.serving}, {"摄像团队", "灯光组"}
        )
        # No stray my_serving-typed row is emitted.
        self.assertNotIn(
            ITEM_TYPE_MY_SERVING, {i.item_type for i in cell["items"]}
        )

    def test_two_serving_summary_is_bilingual(self):
        self._in_audience(self.server)
        event = self._event(start=self._at(12, 9))
        self._serving(self.server, event, self.camera)
        self._serving(self.server, event, self.lighting)
        self.assertContains(self._month(lang="en"), "Serving ×2")
        self.assertContains(self._month(lang="zh"), "服事 2项")

    def test_grouped_row_does_not_consume_extra_month_cell_rows(self):
        # Test 3: one grouped occurrence + one unrelated event = two rows, well
        # under the compaction cap, even though the group holds three raw items.
        self._in_audience(self.server)
        event = self._event(start=self._at(12, 9))
        self._serving(self.server, event, self.camera)
        self._serving(self.server, event, self.lighting)
        other_event = self._event(start=self._at(12, 15), title_en="Prayer")

        cell = self._cell(self._month(), 12)
        self.assertEqual(cell["total_count"], 2)
        self.assertEqual(cell["more_count"], 0)
        self.assertEqual(len(cell["items"]), 2)
        ids = {i.source_id for i in cell["items"]}
        self.assertEqual(ids, {event.id, other_event.id})

    def test_unrelated_events_with_same_title_time_are_not_grouped(self):
        # Test 8: identical title/time, different ServiceEvents -> two rows.
        self._in_audience(self.server)
        first = self._event(start=self._at(12, 9), title="主日崇拜", title_en="Sunday Worship")
        second = self._event(start=self._at(12, 9), title="主日崇拜", title_en="Sunday Worship")
        cell = self._cell(self._month(), 12)
        self.assertEqual(cell["total_count"], 2)
        self.assertEqual({i.source_id for i in cell["items"]}, {first.id, second.id})

    def test_assigned_server_outside_audience_still_sees_occurrence(self):
        # Test 6: no membership/audience -> base provider emits nothing, but the
        # explicit serving still surfaces the occurrence, linking to event detail.
        event = self._event(start=self._at(12, 9), audience=False)
        member = self._serving(self.server, event, self.camera)
        cell = self._cell(self._month(), 12)
        self.assertEqual(len(cell["items"]), 1)
        occ = cell["items"][0]
        self.assertEqual(occ.item_type, ITEM_TYPE_SERVICE_EVENT)
        self.assertEqual(occ.serving_count, 1)
        self.assertEqual(occ.source_id, member.id)
        # The grouped row links to the member-facing event detail (read-only
        # visibility granted by SERVING-EVENT-VISIBILITY.1A).
        self.assertEqual(
            occ.detail_url, reverse("service_event_detail", args=[event.id])
        )
        self.assertContains(
            self._month(), reverse("service_event_detail", args=[event.id])
        )

    def test_non_assigned_non_audience_user_sees_no_occurrence(self):
        # Test 7: neither audience nor serving -> nothing on the calendar.
        event = self._event(start=self._at(12, 9), audience=False)
        self._serving(self.server, event, self.camera)
        cell = self._cell(self._month(self.other), 12)
        self.assertEqual(cell["items"], [])

    def test_other_user_does_not_see_the_viewers_serving(self):
        # Test 4: other user is in audience (sees the base event) but must not
        # inherit the viewer's serving subitems.
        self._in_audience(self.other)
        event = self._event(start=self._at(12, 9))
        self._serving(self.server, event, self.camera)
        cell = self._cell(self._month(self.other), 12)
        self.assertEqual(len(cell["items"]), 1)
        occ = cell["items"][0]
        self.assertEqual(occ.source_id, event.id)
        self.assertEqual(occ.serving_count, 0)

    def test_management_authority_does_not_see_others_serving(self):
        # Test 5: staff / superuser / manager, each in audience, see the base
        # event but never the viewer's serving subitems.
        event = self._event(start=self._at(12, 9))
        self._serving(self.server, event, self.camera)

        staff = User.objects.create_user("staff", password="pw12345!", is_staff=True)
        superuser = User.objects.create_user(
            "root_user", password="pw12345!", is_superuser=True
        )
        manager = User.objects.create_user("mgr", password="pw12345!")
        ChurchRoleAssignment.objects.create(
            user=manager,
            role=ChurchRoleAssignment.ROLE_PASTOR,
            scope_type=ChurchRoleAssignment.SCOPE_GLOBAL,
        )
        for account in (staff, superuser, manager):
            self._in_audience(account)
            cell = self._cell(self._month(account), 12)
            occ = next(
                (i for i in cell["items"] if i.source_id == event.id), None
            )
            self.assertIsNotNone(occ, account.username)
            self.assertEqual(occ.serving_count, 0, account.username)


class DayGroupingTests(GroupingBase):
    def test_day_shows_one_occurrence_with_two_serving_subitems(self):
        # Test 2: day detail groups into one card listing both serving teams.
        self._in_audience(self.server)
        event = self._event(start=self._at(12, 19))
        camera = self._serving(self.server, event, self.camera)
        lighting = self._serving(self.server, event, self.lighting)

        response = self._day(12)
        timed = response.context["timed_items"]
        occurrences = [i for i in timed if i.source_id == event.id]
        self.assertEqual(len(occurrences), 1)
        occ = occurrences[0]
        self.assertEqual(occ.item_type, ITEM_TYPE_SERVICE_EVENT)
        self.assertEqual(occ.serving_count, 2)
        self.assertEqual({s.role for s in occ.serving}, {"摄像团队", "灯光组"})
        # Header links to the member-facing event detail.
        self.assertContains(
            response, reverse("service_event_detail", args=[event.id])
        )
        # Each serving subitem deep-links to its own My Serving anchor.
        for member in (camera, lighting):
            self.assertContains(
                response,
                f'{reverse("my_serving")}?tab=all#serving-assignment-{member.id}',
            )

    def test_day_read_only_no_action_controls(self):
        # Test 9: no confirm/edit/manage/attendance/check-in controls render.
        self._in_audience(self.server)
        event = self._event(start=self._at(12, 19))
        self._serving(self.server, event, self.camera)
        response = self._day(12)
        body = response.content.decode()
        for banned in (
            "/edit/",
            "/review/",
            "/manage/",
            "/delete/",
            "/cancel/",
            "/confirm/",
            "/attendance",
            "/check-in",
        ):
            self.assertNotIn(banned, body)

    def test_other_user_day_has_no_serving_anchor(self):
        # Test 4 (day): other user in audience sees the event but no serving.
        self._in_audience(self.other)
        event = self._event(start=self._at(12, 19))
        member = self._serving(self.server, event, self.camera)
        response = self._day(12, self.other)
        occurrences = [
            i for i in response.context["timed_items"] if i.source_id == event.id
        ]
        self.assertEqual(len(occurrences), 1)
        self.assertEqual(occurrences[0].serving_count, 0)
        self.assertNotContains(response, f"serving-assignment-{member.id}")
