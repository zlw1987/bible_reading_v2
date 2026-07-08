"""Focused tests for the CHURCH-CALENDAR.2A personal serving overlay.

Covers the ministry-owned ``my_serving`` range provider and its month/day UI:
explicit ``TeamAssignmentMember`` serving only, isolation from other users and
from management authority, the serving-vs-belonging boundary (membership /
audience visibility alone never creates a serving item), the source-module
enablement gate (disabled ``ministry`` runs no serving query), range/overlap
semantics, and the read-only member-facing UI.

Serving is EXPLICIT. It is never inferred from ``ChurchStructureMembership``,
audience scopes, event visibility, or staff/superuser/manager authority, and only
the viewer's own serving is ever shown.
"""

from datetime import datetime, timedelta

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
from events.models import ServiceEvent, ServiceEventAudienceScope
from ministry.calendar_provider import provide_my_serving_items
from ministry.models import (
    MinistryTeam,
    TeamAssignment,
    TeamAssignmentMember,
    TeamMembership,
)

from .providers import (
    ITEM_TYPE_MY_SERVING,
    ITEM_TYPE_SERVICE_EVENT,
    CalendarRangeProvider,
    collect_calendar_items,
)

User = get_user_model()

# Dependency-valid enabled set that drops ministry (nothing depends on ministry)
# while keeping events / church_calendar and every other source enabled.
ENABLED_WITHOUT_MINISTRY = [
    key for key in get_registered_module_keys() if key != "ministry"
]


class ServingProviderBase(TestCase):
    def setUp(self):
        self.now = timezone.now()
        self.range_start = self.now - timedelta(days=10)
        self.range_end = self.now + timedelta(days=20)

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

        self.team = MinistryTeam.objects.create(name="敬拜团", name_en="Worship")

    # -- factories ------------------------------------------------------------
    def _event(self, start=None, end=None, status=ServiceEvent.STATUS_PUBLISHED):
        return ServiceEvent.objects.create(
            title="主日聚会",
            title_en="Sunday Service",
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
            start_datetime=start or (self.now + timedelta(days=1)),
            end_datetime=end,
            status=status,
            location="主堂",
        )

    def _membership(self, user, team=None, is_active=True):
        team = team or self.team
        # A user may hold only one active membership per team, but that one
        # membership can back several assignments; reuse it so multi-assignment
        # tests do not trip the unique-active-membership constraint.
        if is_active:
            existing = TeamMembership.objects.filter(
                team=team, user=user, is_active=True
            ).first()
            if existing:
                return existing
        return TeamMembership.objects.create(
            team=team,
            user=user,
            is_active=is_active,
        )

    def _serving(
        self,
        user,
        event=None,
        team=None,
        assignment_status=TeamAssignment.STATUS_SCHEDULED,
        membership=None,
    ):
        """Create an explicit TeamAssignmentMember serving row for ``user``."""
        team = team or self.team
        event = event or self._event()
        membership = membership or self._membership(user, team=team)
        assignment = TeamAssignment.objects.create(
            service_event=event,
            ministry_team=team,
            status=assignment_status,
        )
        return TeamAssignmentMember.objects.create(
            assignment=assignment,
            membership=membership,
        )

    def _items(self, user, range_start=None, range_end=None):
        return provide_my_serving_items(
            user,
            range_start or self.range_start,
            range_end or self.range_end,
        )

    def _ids(self, items):
        return {item.source_id for item in items}


class ServingProviderTests(ServingProviderBase):
    def test_explicit_assignment_member_creates_own_serving_item(self):
        member = self._serving(self.server)
        items = self._items(self.server)
        self.assertEqual(self._ids(items), {member.id})
        item = items[0]
        self.assertEqual(item.item_type, ITEM_TYPE_MY_SERVING)
        self.assertIn("主日聚会", item.title)
        self.assertIn("敬拜团", item.title)
        # CHURCH-CALENDAR.2A-FU2: the item deep-links to the viewer's own
        # specific serving assignment card, not the generic My Serving page.
        self.assertNotEqual(item.detail_url, reverse("my_serving"))
        self.assertEqual(
            item.detail_url,
            f"{reverse('my_serving')}?tab=all#serving-assignment-{member.id}",
        )

    def test_other_user_does_not_see_the_assignment(self):
        self._serving(self.server)
        self.assertEqual(self._items(self.other), [])

    def test_management_authority_does_not_show_others_serving(self):
        self._serving(self.server)
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
            self.assertEqual(self._items(account), [], account.username)

    def test_membership_and_audience_visibility_alone_create_no_serving_item(self):
        # The user belongs to the district and can see an audience-matching
        # published event, but has NO TeamAssignmentMember row.
        ChurchStructureMembership.objects.create(
            user=self.other,
            unit=self.district,
            status=ChurchStructureMembership.STATUS_ACTIVE,
            is_primary=True,
            start_date=timezone.localdate() - timedelta(days=1),
        )
        event = self._event()
        ServiceEventAudienceScope.objects.create(
            service_event=event, unit=self.district
        )
        self.assertEqual(self._items(self.other), [])

    def test_cancelled_assignment_excluded(self):
        self._serving(
            self.server, assignment_status=TeamAssignment.STATUS_CANCELLED
        )
        self.assertEqual(self._items(self.server), [])

    def test_draft_and_cancelled_event_excluded(self):
        self._serving(self.server, event=self._event(status=ServiceEvent.STATUS_DRAFT))
        self._serving(
            self.server, event=self._event(status=ServiceEvent.STATUS_CANCELLED)
        )
        self.assertEqual(self._items(self.server), [])

    def test_inactive_membership_excluded(self):
        # An assignment member can only be created for an active membership, so
        # create it active, then deactivate the membership: My Serving semantics
        # (membership__is_active=True) then drop it from the serving overlay.
        member = self._serving(self.server)
        self.assertEqual(self._ids(self._items(self.server)), {member.id})
        membership = member.membership
        membership.is_active = False
        membership.save()
        self.assertEqual(self._items(self.server), [])

    def test_completed_assignment_still_shown_as_history(self):
        # Calendar is a range surface (tab="all"): a completed assignment on an
        # in-range event still appears, unlike the My Serving "upcoming" tab.
        member = self._serving(
            self.server, assignment_status=TeamAssignment.STATUS_COMPLETED
        )
        self.assertEqual(self._ids(self._items(self.server)), {member.id})

    def test_two_teams_same_event_yield_distinct_items(self):
        event = self._event()
        second_team = MinistryTeam.objects.create(name="音响组", name_en="Audio")
        first = self._serving(self.server, event=event, team=self.team)
        second = self._serving(self.server, event=event, team=second_team)
        items = self._items(self.server)
        self.assertEqual(self._ids(items), {first.id, second.id})

    def test_multi_day_event_overlaps_middle_range(self):
        event = self._event(
            start=self.now + timedelta(days=1),
            end=self.now + timedelta(days=3),
        )
        member = self._serving(self.server, event=event)
        mid = self._items(
            self.server,
            range_start=self.now + timedelta(days=2),
            range_end=self.now + timedelta(days=3),
        )
        self.assertEqual(self._ids(mid), {member.id})

    def test_out_of_range_event_excluded(self):
        self._serving(self.server, event=self._event(start=self.now + timedelta(days=40)))
        self.assertEqual(self._items(self.server), [])

    def test_detail_url_targets_the_specific_serving_anchor(self):
        member = self._serving(self.server)
        item = self._items(self.server)[0]
        self.assertEqual(
            item.detail_url,
            f"{reverse('my_serving')}?tab=all#serving-assignment-{member.id}",
        )

    def test_detail_url_is_not_an_edit_manage_or_action_url(self):
        member = self._serving(self.server)
        url = self._items(self.server)[0].detail_url
        # Anchor fallback: a read-only My Serving deep link, never a staff /
        # action route. Current Calendar behavior keeps the my_serving item on the
        # My Serving anchor (not the ServiceEvent detail); any change to link at
        # the event detail is deferred to CHURCH-CALENDAR.2A-FU4. (Since
        # SERVING-EVENT-VISIBILITY.1A an explicitly assigned server may view that
        # specific event detail, but this overlay's link is unchanged here.)
        for banned in (
            "/edit/",
            "/review/",
            "/manage/",
            "/delete/",
            "/cancel/",
            "/confirm/",
            "/attendance",
            "/check-in",
            "/schedule/",
            reverse("service_event_detail", args=[member.assignment.service_event_id]),
        ):
            self.assertNotIn(banned, url)

    def test_two_teams_same_event_yield_distinct_anchor_urls(self):
        event = self._event()
        second_team = MinistryTeam.objects.create(name="音响组", name_en="Audio")
        first = self._serving(self.server, event=event, team=self.team)
        second = self._serving(self.server, event=event, team=second_team)
        urls = {item.detail_url for item in self._items(self.server)}
        self.assertEqual(
            urls,
            {
                f"{reverse('my_serving')}?tab=all#serving-assignment-{first.id}",
                f"{reverse('my_serving')}?tab=all#serving-assignment-{second.id}",
            },
        )

    def test_no_data_mutation_when_collecting(self):
        self._serving(self.server)
        before = (
            TeamAssignment.objects.count(),
            TeamAssignmentMember.objects.count(),
            TeamMembership.objects.count(),
            ServiceEvent.objects.count(),
        )
        self._items(self.server)
        after = (
            TeamAssignment.objects.count(),
            TeamAssignmentMember.objects.count(),
            TeamMembership.objects.count(),
            ServiceEvent.objects.count(),
        )
        self.assertEqual(before, after)


class ServingEnablementTests(ServingProviderBase):
    def test_disabled_ministry_skips_provider_and_runs_no_query(self):
        calls = []

        def spy(user, start, end, _calls=calls):
            _calls.append(user)
            return []

        provider = CalendarRangeProvider(module_key="ministry", provide=spy)
        with override_settings(CMS_ENABLED_MODULES=ENABLED_WITHOUT_MINISTRY):
            with self.assertNumQueries(0):
                result = collect_calendar_items(
                    self.server,
                    self.range_start,
                    self.range_end,
                    providers=[provider],
                )
        self.assertEqual(result, [])
        self.assertEqual(calls, [])

    def test_disabled_ministry_contributes_no_serving_item_via_real_registry(self):
        self._serving(self.server)
        with override_settings(CMS_ENABLED_MODULES=ENABLED_WITHOUT_MINISTRY):
            items = collect_calendar_items(
                self.server, self.range_start, self.range_end
            )
        self.assertNotIn(ITEM_TYPE_MY_SERVING, {item.item_type for item in items})

    def test_enabled_ministry_contributes_serving_item_via_real_registry(self):
        member = self._serving(self.server)
        items = collect_calendar_items(self.server, self.range_start, self.range_end)
        serving = [i for i in items if i.item_type == ITEM_TYPE_MY_SERVING]
        self.assertEqual({i.source_id for i in serving}, {member.id})


class ServingUITests(ServingProviderBase):
    """Month/day rendering of the personal serving overlay."""

    def setUp(self):
        super().setUp()
        self.today = timezone.localdate()
        self.year = self.today.year
        self.month = self.today.month
        self.client.force_login(self.server)

    def _at(self, day, hour=9, minute=0):
        return timezone.make_aware(
            datetime(self.year, self.month, day, hour, minute),
            timezone.get_current_timezone(),
        )

    def _month(self, **params):
        return self.client.get(reverse("church_calendar_month"), params)

    def _day(self, day, **params):
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

    def test_month_cell_groups_serving_into_one_occurrence(self):
        # CHURCH-CALENDAR.2A-FU4: the serving row is grouped into the base
        # ServiceEvent occurrence rather than rendered as a separate my_serving
        # row. This server is outside the ordinary audience, so the base
        # ``service_event`` provider emits nothing; the occurrence is still shown
        # from the viewer's own serving (SERVING-EVENT-VISIBILITY.1A).
        member = self._serving(self.server, event=self._event(start=self._at(12, 9)))
        cell = self._cell(self._month(), 12)
        self.assertIn(member.id, {item.source_id for item in cell["items"]})
        presented = next(
            item for item in cell["items"] if item.source_id == member.id
        )
        # The occurrence is typed by its base ServiceEvent, not my_serving.
        self.assertEqual(presented.item_type, ITEM_TYPE_SERVICE_EVENT)
        self.assertFalse(presented.is_announcement)
        self.assertEqual(presented.serving_count, 1)
        self.assertEqual(presented.serving[0].role, "敬拜团")
        # A single-serving month row shows the team inline; the legend still
        # carries the bilingual My Serving label.
        self.assertContains(self._month(), "敬拜团")
        self.assertContains(self._month(lang="en"), "My Serving")
        self.assertContains(self._month(lang="zh"), "我的服事")

    def test_day_renders_grouped_occurrence_with_serving_subitem(self):
        member = self._serving(self.server, event=self._event(start=self._at(12, 19)))
        response = self._day(12)
        occurrences = [
            item
            for item in response.context["timed_items"]
            if member.id in {s.source_id for s in item.serving}
        ]
        self.assertEqual(len(occurrences), 1)
        occ = occurrences[0]
        # One grouped occurrence, typed by the base ServiceEvent.
        self.assertEqual(occ.item_type, ITEM_TYPE_SERVICE_EVENT)
        self.assertEqual(occ.serving_count, 1)
        expected_url = (
            f"{reverse('my_serving')}?tab=all#serving-assignment-{member.id}"
        )
        # The serving subitem deep-links to the viewer's own My Serving anchor.
        self.assertEqual(occ.serving[0].detail_url, expected_url)
        self.assertContains(response, f'href="{expected_url}"')
        self.assertContains(response, "19:00")

    def test_month_serving_subitem_carries_specific_anchor_target(self):
        member = self._serving(self.server, event=self._event(start=self._at(12, 9)))
        expected_url = (
            f"{reverse('my_serving')}?tab=all#serving-assignment-{member.id}"
        )
        cell = self._cell(self._month(), 12)
        presented = next(
            item for item in cell["items"] if item.source_id == member.id
        )
        # The grouped month row links to the member-facing event detail; the
        # exact My Serving anchor rides on the serving subitem (day detail).
        self.assertNotEqual(presented.detail_url, expected_url)
        self.assertEqual(presented.serving[0].detail_url, expected_url)

    def test_my_serving_page_renders_the_matching_anchor(self):
        # The deep-link target must actually exist on My Serving so the anchor
        # resolves. tab=all guarantees the card is present for past or upcoming.
        member = self._serving(self.server, event=self._event(start=self._at(12, 9)))
        response = self.client.get(reverse("my_serving"), {"tab": "all"})
        self.assertContains(response, f'id="serving-assignment-{member.id}"')

    def test_other_user_calendar_pages_have_no_serving_anchor(self):
        member = self._serving(self.server, event=self._event(start=self._at(12, 9)))
        anchor = f"serving-assignment-{member.id}"
        self.client.force_login(self.other)
        for response in (self._month(), self._day(12)):
            self.assertNotContains(response, anchor)

    def test_no_serving_action_or_management_urls_render(self):
        self._serving(self.server, event=self._event(start=self._at(12, 9)))
        for response in (self._month(), self._day(12), self._month(lang="en")):
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

    def test_other_user_sees_no_serving_item_on_calendar(self):
        self._serving(self.server, event=self._event(start=self._at(12, 9)))
        self.client.force_login(self.other)
        cell = self._cell(self._month(), 12)
        self.assertEqual(cell["items"], [])

    def test_render_mutates_no_serving_data(self):
        self._serving(self.server, event=self._event(start=self._at(12, 9)))
        before = (
            TeamAssignment.objects.count(),
            TeamAssignmentMember.objects.count(),
        )
        self._month()
        self._day(12)
        after = (
            TeamAssignment.objects.count(),
            TeamAssignmentMember.objects.count(),
        )
        self.assertEqual(before, after)
