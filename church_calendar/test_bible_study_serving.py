"""Focused tests for the CHURCH-CALENDAR.2B Bible Study serving overlay.

Covers the ``studies``-owned ``bible_study_serving`` calendar items and their FU4
occurrence grouping: explicit linked-user ``BibleStudyMeetingRole`` serving only,
one item per role, grouping with the base ``bible_study_meeting`` occurrence,
isolation from other users and from management authority, the serving-vs-belonging
boundary (membership / audience visibility alone never creates serving), unlinked
roles creating nothing, the ``studies`` source-module enablement gate (disabled
``studies`` runs no Bible Study calendar query and grants no serving-based detail
read), and the studies-owned meeting-detail read gate mirroring
SERVING-EVENT-VISIBILITY.1A.

Serving is EXPLICIT. It is never inferred from ``ChurchStructureMembership``,
audience scopes, Bible Study meeting visibility, or staff/superuser/manager
authority, and only the viewer's own serving is ever shown. Unlike the ordinary
meeting provider, the serving overlay is NOT gated on audience visibility: an
explicit role holder outside the audience still sees their own occurrence and can
open exactly that one meeting's detail, without widening ordinary meeting list /
calendar visibility.
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
from accounts.permissions import CAP_MANAGE_BIBLE_STUDIES, has_capability
from core.module_registry import get_registered_module_keys
from studies.calendar_provider import (
    provide_bible_study_meeting_items,
    provide_bible_study_serving_items,
    provide_studies_calendar_items,
)
from studies.models import (
    BibleStudyLesson,
    BibleStudyMeeting,
    BibleStudyMeetingAudienceScope,
    BibleStudyMeetingRole,
    BibleStudySeries,
)
from studies.permissions import (
    user_has_explicit_bible_study_serving_role_for_meeting,
)

from .providers import (
    ITEM_TYPE_BIBLE_STUDY_MEETING,
    ITEM_TYPE_BIBLE_STUDY_SERVING,
    CalendarRangeProvider,
    collect_calendar_items,
)

User = get_user_model()

# Dependency-valid enabled set that drops studies (nothing depends on studies)
# while keeping events / church_calendar and every other source enabled.
ENABLED_WITHOUT_STUDIES = [
    key for key in get_registered_module_keys() if key != "studies"
]


class BibleStudyServingBase(TestCase):
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
        self.other_unit = ChurchStructureUnit.objects.create(
            parent=self.root,
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="SOUTH-1",
            name="南区一组",
            name_en="South 1",
        )

        # server + other belong to the district (so a district meeting is
        # audience-visible to them). Only server holds a serving role.
        self.server = self._member("server", self.district)
        self.other = self._member("other", self.district)
        # outsider belongs to a sibling unit outside the district audience.
        self.outsider = self._member("outsider", self.other_unit)

    # -- factories ------------------------------------------------------------
    def _member(self, username, unit, **user_overrides):
        user = User.objects.create_user(
            username=username,
            password="pw12345!",
            **user_overrides,
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

    def _series(self, status=BibleStudySeries.STATUS_PUBLISHED, is_active=True):
        return BibleStudySeries.objects.create(
            title="查经系列",
            status=status,
            is_active=is_active,
        )

    def _meeting(
        self,
        unit="district",
        series=None,
        start=None,
        meeting_status=BibleStudyMeeting.STATUS_PUBLISHED,
        lesson_status=BibleStudyLesson.STATUS_PUBLISHED,
    ):
        series = series or self._series()
        lesson = BibleStudyLesson.objects.create(
            series=series,
            title="约翰十五章",
            title_en="John 15",
            lesson_date=timezone.localdate() + timedelta(days=1),
            status=lesson_status,
        )
        meeting = BibleStudyMeeting.objects.create(
            lesson=lesson,
            meeting_datetime=start or (self.now + timedelta(days=1)),
            location="小组家",
            status=meeting_status,
        )
        unit = self.district if unit == "district" else unit
        if unit is not None:
            BibleStudyMeetingAudienceScope.objects.create(meeting=meeting, unit=unit)
        return meeting

    def _role(
        self,
        user,
        meeting=None,
        role=BibleStudyMeetingRole.ROLE_DISCUSSION_LEADER,
    ):
        """Create an explicit linked-user Bible Study serving role."""
        if meeting is None:
            meeting = self._meeting()
        return BibleStudyMeetingRole.objects.create(
            meeting=meeting,
            role=role,
            user=user,
        )

    # -- helpers --------------------------------------------------------------
    def _items(self, user, range_start=None, range_end=None):
        return provide_bible_study_serving_items(
            user,
            range_start or self.range_start,
            range_end or self.range_end,
        )

    def _ids(self, items):
        return {item.source_id for item in items}


class BibleStudyServingProviderTests(BibleStudyServingBase):
    def test_explicit_linked_role_creates_own_serving_item(self):
        role = self._role(self.server)
        items = self._items(self.server)
        # One item PER ROLE, keyed on the role id (collision-safe).
        self.assertEqual(self._ids(items), {role.id})
        item = items[0]
        self.assertEqual(item.item_type, ITEM_TYPE_BIBLE_STUDY_SERVING)
        self.assertIn("约翰十五章", item.title)
        self.assertIn("查经带领", item.title)
        self.assertIsNone(item.end)
        self.assertEqual(item.start, role.meeting.meeting_datetime)
        # FU4 grouping metadata: shares the meeting occurrence key with the base
        # meeting item, carries the per-role label and the meeting detail link.
        self.assertEqual(
            item.occurrence_key, f"bible_study_meeting:{role.meeting_id}"
        )
        self.assertEqual(item.occurrence_role, "查经带领")
        expected_url = reverse("bible_study_meeting_detail", args=[role.meeting_id])
        self.assertEqual(item.detail_url, expected_url)
        self.assertEqual(item.occurrence_detail_url, expected_url)

    def test_other_user_does_not_see_the_role(self):
        self._role(self.server)
        self.assertEqual(self._items(self.other), [])

    def test_management_authority_does_not_show_others_serving(self):
        self._role(self.server)
        staff = self._member("staff", self.other_unit, is_staff=True)
        superuser = self._member("root_user", self.other_unit, is_superuser=True)
        manager = self._member("mgr", self.other_unit)
        ChurchRoleAssignment.objects.create(
            user=manager,
            role=ChurchRoleAssignment.ROLE_PASTOR,
            scope_type=ChurchRoleAssignment.SCOPE_GLOBAL,
        )
        self.assertTrue(has_capability(manager, CAP_MANAGE_BIBLE_STUDIES))
        for account in (staff, superuser, manager):
            self.assertEqual(self._items(account), [], account.username)

    def test_membership_and_audience_visibility_alone_create_no_serving_item(self):
        meeting = self._meeting()
        self.assertTrue(meeting.can_be_seen_by(self.other))
        self.assertEqual(self._items(self.other), [])

    def test_unlinked_role_creates_no_personal_item(self):
        meeting = self._meeting()
        BibleStudyMeetingRole.objects.create(
            meeting=meeting,
            role=BibleStudyMeetingRole.ROLE_HOST,
            user=None,
            display_name="访客弟兄",
        )
        self.assertEqual(self._items(self.server), [])
        self.assertEqual(self._items(self.other), [])

    def test_role_holder_outside_audience_still_gets_serving_item(self):
        # NEW (FU4-adapted): explicit serving is NOT gated on audience. An
        # outsider role holder receives their own serving occurrence even though
        # the ordinary meeting provider would not show the meeting to them.
        meeting = self._meeting()  # district audience excludes the outsider
        role = self._role(self.outsider, meeting=meeting)
        self.assertFalse(meeting.can_be_seen_by(self.outsider))
        self.assertEqual(self._ids(self._items(self.outsider)), {role.id})
        # ...and the ordinary meeting provider stays audience-only for them.
        meeting_items = provide_bible_study_meeting_items(
            self.outsider, self.range_start, self.range_end
        )
        self.assertEqual(meeting_items, [])

    def test_draft_and_cancelled_meeting_excluded(self):
        self._role(
            self.server,
            meeting=self._meeting(meeting_status=BibleStudyMeeting.STATUS_DRAFT),
        )
        self._role(
            self.server,
            meeting=self._meeting(meeting_status=BibleStudyMeeting.STATUS_CANCELLED),
        )
        self.assertEqual(self._items(self.server), [])

    def test_inactive_or_draft_series_and_draft_lesson_excluded(self):
        self._role(
            self.server,
            meeting=self._meeting(series=self._series(is_active=False)),
        )
        self._role(
            self.server,
            meeting=self._meeting(series=self._series(status=BibleStudySeries.STATUS_DRAFT)),
        )
        self._role(
            self.server,
            meeting=self._meeting(lesson_status=BibleStudyLesson.STATUS_DRAFT),
        )
        self.assertEqual(self._items(self.server), [])

    def test_completed_meeting_in_range_still_shown_as_history(self):
        role = self._role(
            self.server,
            meeting=self._meeting(
                meeting_status=BibleStudyMeeting.STATUS_COMPLETED,
                lesson_status=BibleStudyLesson.STATUS_COMPLETED,
                series=self._series(status=BibleStudySeries.STATUS_COMPLETED),
            ),
        )
        self.assertEqual(self._ids(self._items(self.server)), {role.id})

    def test_multiple_roles_same_meeting_yield_one_item_per_role(self):
        meeting = self._meeting()
        first = self._role(
            self.server, meeting=meeting, role=BibleStudyMeetingRole.ROLE_WORSHIP_LEAD
        )
        second = self._role(
            self.server, meeting=meeting, role=BibleStudyMeetingRole.ROLE_PIANIST
        )
        items = self._items(self.server)
        # One item per role, distinct ids, but the SAME occurrence key so FU4
        # collapses them into one occurrence.
        self.assertEqual(self._ids(items), {first.id, second.id})
        self.assertEqual(
            {i.occurrence_key for i in items},
            {f"bible_study_meeting:{meeting.id}"},
        )
        self.assertEqual(
            {i.occurrence_role for i in items}, {"敬拜带领", "伴奏"}
        )

    def test_out_of_range_meeting_excluded(self):
        self._role(
            self.server,
            meeting=self._meeting(start=self.now + timedelta(days=40)),
        )
        self.assertEqual(self._items(self.server), [])

    def test_point_in_time_membership_matches_only_meeting_day(self):
        meeting = self._meeting(start=self.now + timedelta(days=5))
        role = self._role(self.server, meeting=meeting)
        inside = self._items(
            self.server,
            range_start=self.now + timedelta(days=5),
            range_end=self.now + timedelta(days=6),
        )
        self.assertEqual(self._ids(inside), {role.id})
        after = self._items(
            self.server,
            range_start=self.now + timedelta(days=6),
            range_end=self.now + timedelta(days=7),
        )
        self.assertEqual(after, [])

    def test_detail_url_is_not_an_edit_manage_or_action_url(self):
        self._role(self.server)
        url = self._items(self.server)[0].detail_url
        for banned in (
            "/edit/",
            "/review/",
            "/manage/",
            "/delete/",
            "/cancel/",
            "/confirm/",
            "/attendance",
            "/check-in",
            "/roles/",
        ):
            self.assertNotIn(banned, url)

    def test_serving_and_meeting_items_coexist_without_identity_collision(self):
        role = self._role(self.server)
        combined = provide_studies_calendar_items(
            self.server, self.range_start, self.range_end
        )
        meeting_ids = {
            i.source_id for i in combined if i.item_type == ITEM_TYPE_BIBLE_STUDY_MEETING
        }
        serving_ids = {
            i.source_id for i in combined if i.item_type == ITEM_TYPE_BIBLE_STUDY_SERVING
        }
        self.assertIn(role.meeting_id, meeting_ids)
        self.assertIn(role.id, serving_ids)
        # collect_calendar_items validates per-provider identity uniqueness; the
        # meeting item and the serving item carry distinct identities.
        collected = collect_calendar_items(
            self.server, self.range_start, self.range_end
        )
        serving = [i for i in collected if i.item_type == ITEM_TYPE_BIBLE_STUDY_SERVING]
        self.assertEqual({i.source_id for i in serving}, {role.id})

    def test_no_data_mutation_when_collecting(self):
        self._role(self.server)
        before = (
            BibleStudyMeeting.objects.count(),
            BibleStudyMeetingRole.objects.count(),
            BibleStudyMeetingAudienceScope.objects.count(),
        )
        self._items(self.server)
        provide_studies_calendar_items(self.server, self.range_start, self.range_end)
        after = (
            BibleStudyMeeting.objects.count(),
            BibleStudyMeetingRole.objects.count(),
            BibleStudyMeetingAudienceScope.objects.count(),
        )
        self.assertEqual(before, after)


class BibleStudyServingDetailVisibilityTests(BibleStudyServingBase):
    """The studies-owned meeting-detail read gate (mirror of SEV.1A)."""

    def test_helper_true_for_own_linked_role_even_outside_audience(self):
        meeting = self._meeting()  # district audience excludes the outsider
        self._role(self.outsider, meeting=meeting)
        self.assertFalse(meeting.can_be_seen_by(self.outsider))
        self.assertTrue(
            user_has_explicit_bible_study_serving_role_for_meeting(
                self.outsider, meeting
            )
        )

    def test_helper_false_without_role_and_for_unlinked_and_draft(self):
        meeting = self._meeting()
        # audience member without a role
        self.assertFalse(
            user_has_explicit_bible_study_serving_role_for_meeting(self.other, meeting)
        )
        # unlinked role
        BibleStudyMeetingRole.objects.create(
            meeting=meeting, role=BibleStudyMeetingRole.ROLE_HOST, user=None,
            display_name="访客",
        )
        self.assertFalse(
            user_has_explicit_bible_study_serving_role_for_meeting(self.outsider, meeting)
        )
        # draft meeting never granted through serving
        draft = self._meeting(meeting_status=BibleStudyMeeting.STATUS_DRAFT)
        self._role(self.outsider, meeting=draft)
        self.assertFalse(
            user_has_explicit_bible_study_serving_role_for_meeting(self.outsider, draft)
        )

    def test_helper_scoped_to_exact_meeting_only(self):
        served = self._meeting()
        other_meeting = self._meeting()  # same district audience, no role for outsider
        self._role(self.outsider, meeting=served)
        self.assertTrue(
            user_has_explicit_bible_study_serving_role_for_meeting(self.outsider, served)
        )
        self.assertFalse(
            user_has_explicit_bible_study_serving_role_for_meeting(
                self.outsider, other_meeting
            )
        )

    @override_settings(CMS_ENABLED_MODULES=ENABLED_WITHOUT_STUDIES)
    def test_helper_false_when_studies_disabled(self):
        meeting = self._meeting()
        self._role(self.outsider, meeting=meeting)
        self.assertFalse(
            user_has_explicit_bible_study_serving_role_for_meeting(self.outsider, meeting)
        )

    def test_detail_view_grants_outside_audience_role_holder(self):
        meeting = self._meeting()
        self._role(self.outsider, meeting=meeting)
        self.client.force_login(self.outsider)
        response = self.client.get(
            reverse("bible_study_meeting_detail", args=[meeting.id])
        )
        self.assertEqual(response.status_code, 200)

    def test_detail_view_denies_other_meeting_without_role_or_audience(self):
        served = self._meeting()
        other_meeting = self._meeting()  # outsider has no role and no audience
        self._role(self.outsider, meeting=served)
        self.client.force_login(self.outsider)
        response = self.client.get(
            reverse("bible_study_meeting_detail", args=[other_meeting.id])
        )
        # Denied → redirect to the study list (not a 200 render).
        self.assertEqual(response.status_code, 302)


class BibleStudyServingEnablementTests(BibleStudyServingBase):
    def test_disabled_studies_skips_provider_and_runs_no_query(self):
        calls = []

        def spy(user, start, end, _calls=calls):
            _calls.append(user)
            return []

        provider = CalendarRangeProvider(module_key="studies", provide=spy)
        with override_settings(CMS_ENABLED_MODULES=ENABLED_WITHOUT_STUDIES):
            with self.assertNumQueries(0):
                result = collect_calendar_items(
                    self.server,
                    self.range_start,
                    self.range_end,
                    providers=[provider],
                )
        self.assertEqual(result, [])
        self.assertEqual(calls, [])

    def test_disabled_studies_contributes_no_items_via_real_registry(self):
        self._role(self.server)
        with override_settings(CMS_ENABLED_MODULES=ENABLED_WITHOUT_STUDIES):
            items = collect_calendar_items(
                self.server, self.range_start, self.range_end
            )
        types = {item.item_type for item in items}
        self.assertNotIn(ITEM_TYPE_BIBLE_STUDY_SERVING, types)
        self.assertNotIn(ITEM_TYPE_BIBLE_STUDY_MEETING, types)

    def test_enabled_studies_contributes_serving_item_via_real_registry(self):
        role = self._role(self.server)
        items = collect_calendar_items(self.server, self.range_start, self.range_end)
        serving = [i for i in items if i.item_type == ITEM_TYPE_BIBLE_STUDY_SERVING]
        self.assertEqual({i.source_id for i in serving}, {role.id})


class BibleStudyServingUITests(BibleStudyServingBase):
    """Month/day rendering of the grouped Bible Study serving occurrence."""

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

    def test_month_groups_meeting_and_serving_into_one_occurrence(self):
        meeting = self._meeting(start=self._at(12, 19))
        self._role(self.server, meeting=meeting, role=BibleStudyMeetingRole.ROLE_WORSHIP_LEAD)
        self._role(self.server, meeting=meeting, role=BibleStudyMeetingRole.ROLE_PIANIST)
        cell = self._cell(self._month(), 12)
        # One grouped occurrence, typed by the base meeting.
        occ = [i for i in cell["items"] if i.source_id == meeting.id]
        self.assertEqual(len(occ), 1)
        self.assertEqual(occ[0].item_type, ITEM_TYPE_BIBLE_STUDY_MEETING)
        self.assertEqual(occ[0].serving_count, 2)
        self.assertEqual(cell["total_count"], 1)  # not three rows
        # No standalone bible_study_serving row.
        self.assertNotIn(
            ITEM_TYPE_BIBLE_STUDY_SERVING, {i.item_type for i in cell["items"]}
        )
        self.assertContains(self._month(lang="en"), "Serving ×2")
        self.assertContains(self._month(lang="zh"), "服事 2项")

    def test_day_renders_one_meeting_card_with_serving_subitems(self):
        meeting = self._meeting(start=self._at(12, 19))
        self._role(self.server, meeting=meeting, role=BibleStudyMeetingRole.ROLE_WORSHIP_LEAD)
        self._role(self.server, meeting=meeting, role=BibleStudyMeetingRole.ROLE_PIANIST)
        response = self._day(12)
        occ = [i for i in response.context["timed_items"] if i.source_id == meeting.id]
        self.assertEqual(len(occ), 1)
        self.assertEqual(occ[0].item_type, ITEM_TYPE_BIBLE_STUDY_MEETING)
        self.assertEqual({s.role for s in occ[0].serving}, {"敬拜带领", "伴奏"})
        self.assertContains(
            response, reverse("bible_study_meeting_detail", args=[meeting.id])
        )
        self.assertContains(response, "19:00")

    def test_single_role_month_summary_shows_role_label(self):
        meeting = self._meeting(start=self._at(12, 19))
        self._role(self.server, meeting=meeting)
        cell = self._cell(self._month(), 12)
        occ = next(i for i in cell["items"] if i.source_id == meeting.id)
        self.assertEqual(occ.serving_count, 1)
        self.assertEqual(occ.serving[0].role, "查经带领")
        self.assertContains(self._month(), "查经带领")

    def test_outside_audience_role_holder_sees_serving_only_occurrence(self):
        meeting = self._meeting(start=self._at(12, 19))
        role = self._role(self.outsider, meeting=meeting)
        self.client.force_login(self.outsider)
        cell = self._cell(self._month(), 12)
        # Base meeting is not audience-visible; occurrence is serving-only.
        self.assertEqual(len(cell["items"]), 1)
        occ = cell["items"][0]
        self.assertEqual(occ.item_type, ITEM_TYPE_BIBLE_STUDY_MEETING)
        self.assertEqual(occ.source_id, role.id)
        self.assertEqual(occ.serving_count, 1)
        self.assertEqual(
            occ.detail_url, reverse("bible_study_meeting_detail", args=[meeting.id])
        )

    def test_audience_user_without_role_sees_meeting_but_no_serving(self):
        meeting = self._meeting(start=self._at(12, 19))
        self._role(self.server, meeting=meeting)
        self.client.force_login(self.other)
        cell = self._cell(self._month(), 12)
        occ = [i for i in cell["items"] if i.source_id == meeting.id]
        self.assertEqual(len(occ), 1)
        self.assertEqual(occ[0].serving_count, 0)
        self.assertNotContains(self._day(12), "查经带领")

    def test_no_serving_action_or_management_urls_render(self):
        self._role(self.server, meeting=self._meeting(start=self._at(12, 9)))
        for response in (self._month(), self._day(12), self._month(lang="en")):
            body = response.content.decode()
            for banned in (
                "/edit/",
                "/review/",
                "/manage/",
                "/delete/",
                "/cancel/",
                "/attendance",
                "/check-in",
            ):
                self.assertNotIn(banned, body)

    def test_render_mutates_no_serving_data(self):
        self._role(self.server, meeting=self._meeting(start=self._at(12, 9)))
        before = (
            BibleStudyMeeting.objects.count(),
            BibleStudyMeetingRole.objects.count(),
        )
        self._month()
        self._day(12)
        after = (
            BibleStudyMeeting.objects.count(),
            BibleStudyMeetingRole.objects.count(),
        )
        self.assertEqual(before, after)
