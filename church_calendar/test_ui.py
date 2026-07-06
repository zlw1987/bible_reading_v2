"""Focused month/day presentation tests for CHURCH-CALENDAR.1C.

These exercise the member-facing month grid and day detail rendered on top of
the 1B source providers: local-day bucketing, half-open boundary behavior,
timed/announcement separation, deterministic sorting, compacting with an
explicit "more" link, bilingual labels, accessibility, and the read-only
boundary. Presentation only — no provider visibility, source model, migration,
Today, My Serving, or data-write behavior is touched.

Timed items (events / meetings / activities) are visible independent of the
request "now", so they are anchored to fixed in-month days (10-20, always valid).
Announcements are gated by their active window at request time, so they use a
publish window that is unambiguously active now and open across the month.
"""

from datetime import datetime, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import ChurchStructureMembership, ChurchStructureUnit
from announcements.models import Announcement, AnnouncementAudienceScope
from community_events.models import CommunityActivity, CommunityActivityAudienceScope
from core.module_registry import get_registered_module_keys
from events.models import ServiceEvent, ServiceEventAudienceScope
from studies.models import (
    BibleStudyLesson,
    BibleStudyMeeting,
    BibleStudyMeetingAudienceScope,
    BibleStudySeries,
)

User = get_user_model()

# Dependency-valid enabled set that drops events (and ministry, which depends on
# events) while keeping core/church_calendar and the other sources enabled.
ENABLED_WITHOUT_EVENTS = [
    key for key in get_registered_module_keys() if key not in ("events", "ministry")
]
MODULES_WITHOUT_CALENDAR = tuple(
    key for key in get_registered_module_keys() if key != "church_calendar"
)


class CalendarUIBase(TestCase):
    def setUp(self):
        self.now = timezone.now()
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
        self.member = User.objects.create_user("member_ui", password="pw12345!")
        ChurchStructureMembership.objects.create(
            user=self.member,
            unit=self.district,
            status=ChurchStructureMembership.STATUS_ACTIVE,
            is_primary=True,
            start_date=self.today - timedelta(days=1),
        )
        self.client.force_login(self.member)

    # -- local aware datetime anchored in the current month -------------------
    def _at(self, day, hour=9, minute=0):
        return timezone.make_aware(
            datetime(self.year, self.month, day, hour, minute),
            timezone.get_current_timezone(),
        )

    # -- source factories (all district-audience, member-visible) -------------
    def _event(self, start, end=None, title="主日聚会", title_en="Sunday Service"):
        event = ServiceEvent.objects.create(
            title=title,
            title_en=title_en,
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
            start_datetime=start,
            end_datetime=end,
            status=ServiceEvent.STATUS_PUBLISHED,
            location="主堂",
        )
        ServiceEventAudienceScope.objects.create(
            service_event=event, unit=self.district
        )
        return event

    def _meeting(self, start, title="约翰十五章", title_en="John 15"):
        series = BibleStudySeries.objects.create(
            title="查经系列", status=BibleStudySeries.STATUS_PUBLISHED
        )
        lesson = BibleStudyLesson.objects.create(
            series=series,
            title=title,
            title_en=title_en,
            lesson_date=timezone.localtime(start).date(),
            status=BibleStudyLesson.STATUS_PUBLISHED,
        )
        meeting = BibleStudyMeeting.objects.create(
            lesson=lesson,
            meeting_datetime=start,
            location="小组家",
            status=BibleStudyMeeting.STATUS_PUBLISHED,
        )
        BibleStudyMeetingAudienceScope.objects.create(
            meeting=meeting, unit=self.district
        )
        return meeting

    def _activity(self, start, end=None, title="社区活动", title_en="Community Activity"):
        activity = CommunityActivity.objects.create(
            title=title,
            title_en=title_en,
            start_datetime=start,
            end_datetime=end,
            status=CommunityActivity.STATUS_PUBLISHED,
            location="教会广场",
        )
        CommunityActivityAudienceScope.objects.create(
            activity=activity, structure_unit=self.district
        )
        return activity

    def _announcement(
        self,
        publish_start=None,
        publish_end=None,
        title="本周通知",
        title_en="This Week",
    ):
        announcement = Announcement.objects.create(
            title=title,
            title_en=title_en,
            body="通知内容",
            status=Announcement.STATUS_PUBLISHED,
            priority=Announcement.PRIORITY_NORMAL,
            publish_start=publish_start or (self.now - timedelta(days=40)),
            publish_end=publish_end,
        )
        AnnouncementAudienceScope.objects.create(
            announcement=announcement, structure_unit=self.district
        )
        return announcement

    # -- month-context helpers ------------------------------------------------
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

    def _cell_ids(self, response, day):
        cell = self._cell(response, day)
        return {item.source_id for item in cell["items"]}


class MonthUITests(CalendarUIBase):
    def test_multi_day_event_on_every_overlapping_day_not_boundary(self):
        event = self._event(start=self._at(10, 9), end=self._at(13, 0))
        response = self._month()
        for day in (10, 11, 12):
            self.assertIn(event.id, self._cell_ids(response, day), day)
        # Ends exactly at day-13 local midnight: half-open, so not on the 13th.
        self.assertNotIn(event.id, self._cell_ids(response, 13))

    def test_ranged_activity_on_every_overlapping_day_not_boundary(self):
        activity = self._activity(start=self._at(10, 9), end=self._at(13, 0))
        response = self._month()
        for day in (10, 11, 12):
            self.assertIn(activity.id, self._cell_ids(response, day), day)
        self.assertNotIn(activity.id, self._cell_ids(response, 13))

    def test_bible_study_meeting_only_on_meeting_date(self):
        meeting = self._meeting(start=self._at(15, 19))
        response = self._month()
        self.assertIn(meeting.id, self._cell_ids(response, 15))
        self.assertNotIn(meeting.id, self._cell_ids(response, 14))
        self.assertNotIn(meeting.id, self._cell_ids(response, 16))

    def test_announcement_is_active_communication_on_overlapping_days(self):
        announcement = self._announcement()  # open-ended, active all month
        response = self._month()
        for day in (10, 20):
            cell = self._cell(response, day)
            ids = {item.source_id for item in cell["items"]}
            self.assertIn(announcement.id, ids, day)
            presented = next(
                item for item in cell["items"] if item.source_id == announcement.id
            )
            self.assertTrue(presented.is_announcement)

    def test_cell_compacts_with_more_link_and_drops_nothing(self):
        events = [
            self._event(start=self._at(12, 8 + i), title_en=f"Event {i}")
            for i in range(4)
        ]
        response = self._month(lang="en")
        cell = self._cell(response, 12)
        self.assertEqual(cell["total_count"], 4)
        self.assertEqual(len(cell["items"]), 3)  # compacted
        self.assertEqual(cell["more_count"], 1)
        self.assertContains(response, "+1 more")
        # Every hidden item stays reachable on the day detail.
        day = self._day(12)
        day_ids = {item.source_id for item in day.context["timed_items"]}
        self.assertEqual(day_ids, {e.id for e in events})

    def test_out_of_month_cell_links_to_day_detail(self):
        response = self._month()
        out_cell = None
        for week in response.context["calendar_weeks"]:
            for cell in week:
                if not cell["in_month"]:
                    out_cell = cell
                    break
            if out_cell:
                break
        self.assertIsNotNone(out_cell)
        url = reverse(
            "church_calendar_day",
            args=[out_cell["date"].year, out_cell["date"].month, out_cell["date"].day],
        )
        self.assertContains(response, url)

    def test_today_and_month_navigation_present(self):
        next_param = self._month().context["next_month_param"]
        response = self._month(month=next_param, lang="en")
        self.assertFalse(response.context["is_current_month"])
        self.assertContains(response, "Previous")
        self.assertContains(response, "Next")
        # The "current month" shortcut only shows when viewing another month.
        self.assertContains(response, "Current month")
        self.assertContains(response, "?month=" + response.context["previous_month_param"])
        self.assertContains(response, "?month=" + response.context["next_month_param"])

    def test_no_reading_active_plan_markers(self):
        self._event(start=self._at(10, 9))
        body = self._month().content.decode()
        self.assertNotIn("active_plan", body)
        self.assertNotIn("progress_percent", body)
        self.assertNotIn("Rest day", body)


class DayUITests(CalendarUIBase):
    def test_all_timed_items_uncapped_and_sorted_by_start(self):
        early = self._event(start=self._at(12, 8), title_en="Early")
        meeting = self._meeting(start=self._at(12, 9))
        mid = self._event(start=self._at(12, 11), title_en="Mid")
        late = self._activity(start=self._at(12, 15))
        response = self._day(12)
        order = [item.source_id for item in response.context["timed_items"]]
        self.assertEqual(order, [early.id, meeting.id, mid.id, late.id])
        self.assertEqual(len(response.context["timed_items"]), 4)  # uncapped

    def test_same_start_time_breaks_ties_by_type_order(self):
        # service_event sorts before bible_study_meeting at an identical start.
        # (source ids collide across models, so compare by item_type.)
        self._event(start=self._at(12, 10))
        self._meeting(start=self._at(12, 10))
        response = self._day(12)
        types = [item.item_type for item in response.context["timed_items"]]
        self.assertEqual(types, ["service_event", "bible_study_meeting"])

    def test_announcements_render_in_separate_deterministic_section(self):
        first = self._announcement(
            publish_start=self.now - timedelta(days=40), title_en="First"
        )
        second = self._announcement(
            publish_start=self.now - timedelta(days=39), title_en="Second"
        )
        self._event(start=self._at(12, 9))  # a timed item in the other section
        response = self._day(12)
        announce_ids = [i.source_id for i in response.context["announcement_items"]]
        self.assertEqual(announce_ids, [first.id, second.id])
        # The two sections are disjoint by display kind (source ids collide
        # across models, so assert on the kind, not the raw id).
        self.assertEqual(len(response.context["announcement_items"]), 2)
        for item in response.context["announcement_items"]:
            self.assertTrue(item.is_announcement)
        for item in response.context["timed_items"]:
            self.assertFalse(item.is_announcement)

    def test_open_ended_announcement_has_no_invented_end(self):
        self._announcement(publish_start=self.now - timedelta(days=40))
        response = self._day(12, lang="en")
        item = response.context["announcement_items"][0]
        self.assertIsNone(item.end)
        self.assertContains(response, "(ongoing)")

    def test_bible_study_meeting_shows_no_fabricated_duration(self):
        self._meeting(start=self._at(12, 19))
        response = self._day(12)
        item = response.context["timed_items"][0]
        self.assertTrue(item.is_point_in_time)
        self.assertIsNone(item.end)
        self.assertContains(response, "19:00")

    def test_detail_links_are_member_facing_owning_urls(self):
        event = self._event(start=self._at(12, 9))
        meeting = self._meeting(start=self._at(12, 10))
        activity = self._activity(start=self._at(12, 11))
        announcement = self._announcement()
        response = self._day(12)
        items = (
            list(response.context["timed_items"])
            + list(response.context["announcement_items"])
        )
        for item in items:
            for banned in ("/edit/", "/review/", "/manage/", "/delete/"):
                self.assertNotIn(banned, item.detail_url)
        self.assertContains(response, reverse("service_event_detail", args=[event.id]))
        self.assertContains(
            response, reverse("bible_study_meeting_detail", args=[meeting.id])
        )
        self.assertContains(
            response, reverse("community_activity_detail", args=[activity.id])
        )
        self.assertContains(
            response, reverse("announcement_detail", args=[announcement.id])
        )

    def test_empty_state_renders_when_no_items(self):
        response = self._day(12)
        self.assertFalse(response.context["has_items"])
        self.assertEqual(list(response.context["timed_items"]), [])
        self.assertEqual(list(response.context["announcement_items"]), [])
        self.assertContains(response, "这一天暂时没有与你相关的日程")


class BilingualAccessibilityTests(CalendarUIBase):
    def test_month_labels_render_per_session_language(self):
        self._event(start=self._at(10, 9))
        en = self._month(lang="en")
        self.assertContains(en, "Church Gathering")  # legend type label
        self.assertContains(en, "Previous")
        self.assertContains(en, "Next")
        zh = self._month(lang="zh")
        self.assertContains(zh, "教会聚会")
        self.assertContains(zh, "上个月")
        self.assertContains(zh, "下个月")

    def test_more_link_is_bilingual(self):
        for _ in range(4):
            self._event(start=self._at(12, 8))
        self.assertContains(self._month(lang="en"), "+1 more")
        self.assertContains(self._month(lang="zh"), "+1 更多")

    def test_day_section_headings_are_bilingual(self):
        self._event(start=self._at(12, 9))
        self._announcement()
        en = self._day(12, lang="en")
        self.assertContains(en, "Timed items")
        self.assertContains(en, "Announcements")
        zh = self._day(12, lang="zh")
        self.assertContains(zh, "日程")
        self.assertContains(zh, "公告")

    def test_type_label_is_accessible_text_not_color_only(self):
        self._event(start=self._at(10, 9))
        # Legend carries the visible label, and each cell item carries an
        # accessible (screen-reader) type prefix — type is never color alone.
        body = self._month(lang="zh").content.decode()
        self.assertIn("cc-sr-only", body)
        self.assertIn("教会聚会", body)


class ReadOnlyBoundaryTests(CalendarUIBase):
    def _seed_one_of_each(self, day=12):
        self._event(start=self._at(day, 9))
        self._meeting(start=self._at(day, 10))
        self._activity(start=self._at(day, 11))
        self._announcement()

    def test_no_write_or_management_action_urls_render(self):
        self._seed_one_of_each()
        for response in (self._month(), self._day(12), self._month(lang="en")):
            body = response.content.decode()
            for banned in (
                "/edit/",
                "/review/",
                "/manage/",
                "/delete/",
                "/attendance",
                "/check-in",
                "/serving",
            ):
                self.assertNotIn(banned, body)

    def test_render_mutates_no_source_data(self):
        self._seed_one_of_each()
        before = (
            ServiceEvent.objects.count(),
            BibleStudyMeeting.objects.count(),
            CommunityActivity.objects.count(),
            Announcement.objects.count(),
            ChurchStructureMembership.objects.count(),
        )
        self._month()
        self._day(12)
        after = (
            ServiceEvent.objects.count(),
            BibleStudyMeeting.objects.count(),
            CommunityActivity.objects.count(),
            Announcement.objects.count(),
            ChurchStructureMembership.objects.count(),
        )
        self.assertEqual(before, after)

    def test_disabled_source_contributes_no_rendered_items(self):
        event = self._event(start=self._at(12, 9))
        with override_settings(CMS_ENABLED_MODULES=ENABLED_WITHOUT_EVENTS):
            response = self._month()
            all_ids = set()
            for week in response.context["calendar_weeks"]:
                for cell in week:
                    all_ids.update(item.source_id for item in cell["items"])
            self.assertNotIn(event.id, all_ids)

    @override_settings(CMS_ENABLED_MODULES=MODULES_WITHOUT_CALENDAR)
    def test_disabling_calendar_hides_nav_entry(self):
        response = self.client.get(reverse("home"))
        self.assertNotContains(response, reverse("church_calendar_month"))
