"""Focused tests for the CHURCH-CALENDAR.1B source providers.

Covers the four member-safe range providers (ServiceEvent, BibleStudyMeeting,
Announcement, CommunityActivity), the explicit registration + source-module
enablement gate, the manager-bypass regression boundary (staff / superuser /
capability accounts get no member-calendar widening), range/overlap semantics,
and cross-product non-goals.

Visibility means the signed-in viewer's *current* ordinary audience/belonging
visibility only. All four providers must fail closed for absent/ambiguous active
primary membership, zero audience rows, and nonmatching audience.
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from accounts.models import (
    ChurchRoleAssignment,
    ChurchStructureMembership,
    ChurchStructureUnit,
)
from announcements.calendar_provider import provide_announcement_items
from announcements.models import Announcement, AnnouncementAudienceScope
from community_events.calendar_provider import provide_community_activity_items
from community_events.models import (
    CommunityActivity,
    CommunityActivityAudienceScope,
    CommunityActivityCoOrganizer,
)
from events.calendar_provider import provide_service_event_items
from events.models import ServiceEvent, ServiceEventAudienceScope
from studies.calendar_provider import provide_bible_study_meeting_items
from studies.models import (
    BibleStudyLesson,
    BibleStudyMeeting,
    BibleStudyMeetingAudienceScope,
    BibleStudySeries,
)

from .providers import (
    DISPLAY_ACTIVE_WINDOW,
    ITEM_TYPE_ANNOUNCEMENT,
    ITEM_TYPE_BIBLE_STUDY_MEETING,
    ITEM_TYPE_COMMUNITY_ACTIVITY,
    ITEM_TYPE_SERVICE_EVENT,
    CalendarRangeProvider,
    collect_calendar_items,
)

User = get_user_model()


class CalendarSourceProviderBase(TestCase):
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
        self.group = ChurchStructureUnit.objects.create(
            parent=self.district,
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="NORTH-1",
            name="北区一组",
            name_en="North 1",
        )
        self.sibling = ChurchStructureUnit.objects.create(
            parent=self.root,
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="SOUTH-1",
            name="南区一组",
            name_en="South 1",
        )

        # District audience: the district member matches exactly, the group
        # member matches as a descendant, the sibling member never matches.
        self.member = self._member("district_member", self.district)
        self.descendant_member = self._member("group_member", self.group)
        self.nonmatching_member = self._member("sibling_member", self.sibling)

        # No / ambiguous membership fail-closed viewers.
        self.no_membership_user = User.objects.create_user(
            "no_membership",
            password="pw12345!",
        )
        self.ambiguous_user = self._member("ambiguous", self.district)
        # A second active primary membership makes the primary unit ambiguous.
        # bulk_create bypasses the model's single-active-primary validation so
        # we can construct the "ambiguous" fail-closed state directly.
        ChurchStructureMembership.objects.bulk_create(
            [
                ChurchStructureMembership(
                    user=self.ambiguous_user,
                    unit=self.sibling,
                    status=ChurchStructureMembership.STATUS_ACTIVE,
                    is_primary=True,
                    start_date=timezone.localdate() - timedelta(days=1),
                )
            ]
        )

        # Management-authority accounts, all with NONMATCHING membership: they
        # must never gain member-calendar visibility from management authority.
        self.staff_nonmatching = self._member(
            "staff_nonmatching",
            self.sibling,
            is_staff=True,
        )
        self.superuser_nonmatching = self._member(
            "superuser_nonmatching",
            self.sibling,
            is_superuser=True,
        )
        self.manager_nonmatching = self._member(
            "manager_nonmatching",
            self.sibling,
        )
        ChurchRoleAssignment.objects.create(
            user=self.manager_nonmatching,
            role=ChurchRoleAssignment.ROLE_PASTOR,
            scope_type=ChurchRoleAssignment.SCOPE_GLOBAL,
        )

    def _member(self, username, unit, **user_overrides):
        user = User.objects.create_user(
            username=username,
            password="pw12345!",
            **user_overrides,
        )
        ChurchStructureMembership.objects.create(
            user=user,
            unit=unit,
            status=ChurchStructureMembership.STATUS_ACTIVE,
            is_primary=True,
            start_date=timezone.localdate() - timedelta(days=1),
        )
        return user

    def _in_range(self, offset_days=1):
        return self.now + timedelta(days=offset_days)

    def _ids(self, items):
        return {item.source_id for item in items}


class ServiceEventProviderTests(CalendarSourceProviderBase):
    def _event(self, unit=None, status=ServiceEvent.STATUS_PUBLISHED, **overrides):
        data = {
            "title": "主日聚会",
            "title_en": "Sunday Service",
            "event_type": ServiceEvent.EVENT_SUNDAY_SERVICE,
            "start_datetime": self._in_range(1),
            "status": status,
            "location": "主堂",
        }
        data.update(overrides)
        event = ServiceEvent.objects.create(**data)
        if unit is not None:
            ServiceEventAudienceScope.objects.create(service_event=event, unit=unit)
        return event

    def _items(self, user):
        return provide_service_event_items(user, self.range_start, self.range_end)

    def test_matching_member_sees_published_and_completed(self):
        published = self._event(unit=self.district)
        completed = self._event(unit=self.district, status=ServiceEvent.STATUS_COMPLETED)
        items = self._items(self.member)
        self.assertEqual(self._ids(items), {published.id, completed.id})
        item = next(i for i in items if i.source_id == published.id)
        self.assertEqual(item.item_type, ITEM_TYPE_SERVICE_EVENT)
        self.assertEqual(item.title, "主日聚会")
        self.assertEqual(item.location, "主堂")
        self.assertEqual(item.detail_url, f"/events/{published.id}/")

    def test_descendant_member_matches_district_audience(self):
        event = self._event(unit=self.district)
        self.assertEqual(self._ids(self._items(self.descendant_member)), {event.id})

    def test_nonmatching_member_does_not_see(self):
        event = self._event(unit=self.district)  # audience excludes the sibling
        self.assertEqual(self._ids(self._items(self.member)), {event.id})
        self.assertEqual(self._items(self.nonmatching_member), [])

    def test_zero_audience_event_fails_closed(self):
        self._event(unit=None)  # no audience rows
        self.assertEqual(self._items(self.member), [])

    def test_draft_and_cancelled_excluded(self):
        self._event(unit=self.district, status=ServiceEvent.STATUS_DRAFT)
        self._event(unit=self.district, status=ServiceEvent.STATUS_CANCELLED)
        self.assertEqual(self._items(self.member), [])

    def test_absent_membership_fails_closed_even_for_root_audience(self):
        self._event(unit=self.root)
        self.assertEqual(self._items(self.no_membership_user), [])

    def test_ambiguous_membership_fails_closed(self):
        self._event(unit=self.district)
        self.assertEqual(self._items(self.ambiguous_user), [])

    def test_management_authority_gets_no_bypass(self):
        self._event(unit=self.district)  # audience excludes sibling
        for account in (
            self.staff_nonmatching,
            self.superuser_nonmatching,
            self.manager_nonmatching,
        ):
            self.assertEqual(self._items(account), [], account.username)

    def test_multi_day_event_appears_on_overlapping_middle_day(self):
        event = self._event(
            unit=self.district,
            start_datetime=self._in_range(1),
            end_datetime=self._in_range(3),
        )
        # A one-day window that the event spans but does not start on.
        mid_start = self._in_range(2)
        mid_end = self._in_range(3)
        items = provide_service_event_items(self.member, mid_start, mid_end)
        self.assertEqual(self._ids(items), {event.id})

    def test_out_of_range_event_excluded(self):
        self._event(unit=self.district, start_datetime=self._in_range(40))
        self.assertEqual(self._items(self.member), [])


class BibleStudyMeetingProviderTests(CalendarSourceProviderBase):
    def _series(self, **overrides):
        data = {
            "title": "查经系列",
            "status": BibleStudySeries.STATUS_PUBLISHED,
        }
        data.update(overrides)
        return BibleStudySeries.objects.create(**data)

    def _meeting(
        self,
        unit=None,
        series=None,
        meeting_status=BibleStudyMeeting.STATUS_PUBLISHED,
        lesson_status=BibleStudyLesson.STATUS_PUBLISHED,
        **overrides,
    ):
        series = series or self._series()
        lesson = BibleStudyLesson.objects.create(
            series=series,
            title="约翰十五章",
            title_en="John 15",
            lesson_date=timezone.localdate() + timedelta(days=1),
            status=lesson_status,
        )
        data = {
            "lesson": lesson,
            "meeting_datetime": self._in_range(1),
            "location": "小组家",
            "status": meeting_status,
        }
        data.update(overrides)
        meeting = BibleStudyMeeting.objects.create(**data)
        if unit is not None:
            BibleStudyMeetingAudienceScope.objects.create(meeting=meeting, unit=unit)
        return meeting

    def _items(self, user):
        return provide_bible_study_meeting_items(user, self.range_start, self.range_end)

    def test_matching_member_sees_visible_meeting(self):
        meeting = self._meeting(unit=self.district)
        items = self._items(self.member)
        self.assertEqual(self._ids(items), {meeting.id})
        item = items[0]
        self.assertEqual(item.item_type, ITEM_TYPE_BIBLE_STUDY_MEETING)
        self.assertEqual(item.title, "约翰十五章")
        self.assertEqual(item.detail_url, f"/studies/meetings/{meeting.id}/")

    def test_descendant_member_matches(self):
        meeting = self._meeting(unit=self.district)
        self.assertEqual(self._ids(self._items(self.descendant_member)), {meeting.id})

    def test_nonmatching_member_does_not_see(self):
        self._meeting(unit=self.district)
        self.assertEqual(self._items(self.nonmatching_member), [])

    def test_zero_audience_meeting_fails_closed(self):
        self._meeting(unit=None)
        self.assertEqual(self._items(self.member), [])

    def test_draft_and_lifecycle_hidden_excluded(self):
        self._meeting(unit=self.district, meeting_status=BibleStudyMeeting.STATUS_DRAFT)
        self._meeting(
            unit=self.district,
            meeting_status=BibleStudyMeeting.STATUS_CANCELLED,
        )
        self._meeting(unit=self.district, lesson_status=BibleStudyLesson.STATUS_DRAFT)
        self._meeting(unit=self.district, series=self._series(is_active=False))
        self._meeting(
            unit=self.district,
            series=self._series(status=BibleStudySeries.STATUS_DRAFT),
        )
        self.assertEqual(self._items(self.member), [])

    def test_absent_and_ambiguous_membership_fail_closed(self):
        self._meeting(unit=self.root)
        self.assertEqual(self._items(self.no_membership_user), [])
        self._meeting(unit=self.district)
        self.assertEqual(self._items(self.ambiguous_user), [])

    def test_management_authority_gets_no_bypass(self):
        self._meeting(unit=self.district)
        for account in (
            self.staff_nonmatching,
            self.superuser_nonmatching,
            self.manager_nonmatching,
        ):
            self.assertEqual(self._items(account), [], account.username)

    def test_meeting_is_point_in_time_without_invented_end(self):
        meeting = self._meeting(unit=self.district)
        item = self._items(self.member)[0]
        self.assertIsNone(item.end)
        self.assertEqual(item.start, meeting.meeting_datetime)

    def test_out_of_range_meeting_excluded(self):
        self._meeting(unit=self.district, meeting_datetime=self._in_range(40))
        self.assertEqual(self._items(self.member), [])


class AnnouncementProviderTests(CalendarSourceProviderBase):
    def _announcement(self, unit=None, **overrides):
        data = {
            "title": "本周通知",
            "title_en": "This Week",
            "body": "通知内容",
            "status": Announcement.STATUS_PUBLISHED,
            "priority": Announcement.PRIORITY_NORMAL,
            "publish_start": self.now - timedelta(hours=1),
        }
        data.update(overrides)
        announcement = Announcement.objects.create(**data)
        if unit is not None:
            AnnouncementAudienceScope.objects.create(
                announcement=announcement,
                structure_unit=unit,
            )
        return announcement

    def _items(self, user, range_start=None, range_end=None):
        return provide_announcement_items(
            user,
            range_start or self.range_start,
            range_end or self.range_end,
        )

    def test_matching_member_sees_normal_and_important_active(self):
        normal = self._announcement(unit=self.district)
        important = self._announcement(
            unit=self.district,
            priority=Announcement.PRIORITY_IMPORTANT,
        )
        items = self._items(self.member)
        self.assertEqual(self._ids(items), {normal.id, important.id})
        for item in items:
            self.assertEqual(item.item_type, ITEM_TYPE_ANNOUNCEMENT)
            self.assertEqual(item.display_mode, DISPLAY_ACTIVE_WINDOW)

    def test_future_expired_archived_zero_audience_and_nonmatching_hidden(self):
        self._announcement(
            unit=self.district,
            publish_start=self.now + timedelta(days=2),
        )  # future / not yet published
        self._announcement(
            unit=self.district,
            publish_start=self.now - timedelta(days=3),
            publish_end=self.now - timedelta(hours=1),
        )  # expired
        self._announcement(unit=self.district, status=Announcement.STATUS_ARCHIVED)
        self._announcement(unit=None)  # zero audience
        self._announcement(unit=self.sibling)  # nonmatching
        self.assertEqual(self._items(self.member), [])

    def test_management_authority_gets_no_bypass(self):
        self._announcement(unit=self.district)
        for account in (self.staff_nonmatching, self.superuser_nonmatching):
            self.assertEqual(self._items(account), [], account.username)

    def test_absent_membership_fails_closed(self):
        self._announcement(unit=self.root)
        self.assertEqual(self._items(self.no_membership_user), [])

    def test_open_ended_only_within_requested_range(self):
        announcement = self._announcement(unit=self.district, publish_end=None)
        # In-range: appears with open-ended (None) end.
        items = self._items(self.member)
        self.assertEqual(self._ids(items), {announcement.id})
        self.assertIsNone(items[0].end)
        self.assertEqual(items[0].start, announcement.publish_start)
        # A range entirely before the window start: does not appear.
        past = self._items(
            self.member,
            range_start=self.now - timedelta(days=40),
            range_end=self.now - timedelta(days=20),
        )
        self.assertEqual(past, [])


class CommunityActivityProviderTests(CalendarSourceProviderBase):
    def _activity(self, unit=None, status=CommunityActivity.STATUS_PUBLISHED, **overrides):
        data = {
            "title": "社区活动",
            "title_en": "Community Activity",
            "start_datetime": self._in_range(1),
            "status": status,
            "location": "教会广场",
        }
        data.update(overrides)
        activity = CommunityActivity.objects.create(**data)
        if unit is not None:
            CommunityActivityAudienceScope.objects.create(
                activity=activity,
                structure_unit=unit,
            )
        return activity

    def _items(self, user, range_start=None, range_end=None):
        return provide_community_activity_items(
            user,
            range_start or self.range_start,
            range_end or self.range_end,
        )

    def test_matching_member_sees_published(self):
        activity = self._activity(unit=self.district)
        items = self._items(self.member)
        self.assertEqual(self._ids(items), {activity.id})
        self.assertEqual(items[0].item_type, ITEM_TYPE_COMMUNITY_ACTIVITY)
        self.assertEqual(items[0].detail_url, f"/activities/{activity.id}/")

    def test_descendant_member_matches(self):
        activity = self._activity(unit=self.district)
        self.assertEqual(self._ids(self._items(self.descendant_member)), {activity.id})

    def test_nonmatching_member_does_not_see(self):
        self._activity(unit=self.district)
        self.assertEqual(self._items(self.nonmatching_member), [])

    def test_zero_audience_fails_closed(self):
        self._activity(unit=None)
        self.assertEqual(self._items(self.member), [])

    def test_non_published_states_excluded(self):
        for status in (
            CommunityActivity.STATUS_DRAFT,
            CommunityActivity.STATUS_PENDING_REVIEW,
            CommunityActivity.STATUS_CHANGES_REQUESTED,
            CommunityActivity.STATUS_CANCELLED,
            CommunityActivity.STATUS_COMPLETED,
        ):
            self._activity(unit=self.district, status=status)
        self.assertEqual(self._items(self.member), [])

    def test_creator_and_management_get_no_bypass(self):
        # Pre-publication activity created by the nonmatching account itself.
        activity = self._activity(
            unit=self.district,
            status=CommunityActivity.STATUS_PENDING_REVIEW,
            created_by=self.nonmatching_member,
        )
        self.assertEqual(self._items(self.nonmatching_member), [])
        # Published-but-nonmatching activity is still hidden from staff/superuser.
        self._activity(unit=self.district)
        for account in (self.staff_nonmatching, self.superuser_nonmatching):
            self.assertEqual(self._items(account), [], account.username)
        self.assertNotIn(activity.id, self._ids(self._items(self.member)))

    def test_co_organizer_gets_no_bypass(self):
        draft = self._activity(
            unit=self.district,
            status=CommunityActivity.STATUS_DRAFT,
            created_by=self.member,
        )
        CommunityActivityCoOrganizer.objects.create(
            activity=draft,
            user=self.nonmatching_member,
            added_by=self.member,
        )
        published = self._activity(
            unit=self.district,
            status=CommunityActivity.STATUS_PUBLISHED,
            created_by=self.member,
        )
        CommunityActivityCoOrganizer.objects.create(
            activity=published,
            user=self.nonmatching_member,
            added_by=self.member,
        )

        self.assertTrue(draft.is_co_organizer(self.nonmatching_member))
        self.assertTrue(published.is_co_organizer(self.nonmatching_member))
        self.assertEqual(self._items(self.nonmatching_member), [])

    def test_absent_and_ambiguous_membership_fail_closed(self):
        self._activity(unit=self.root)
        self.assertEqual(self._items(self.no_membership_user), [])
        self._activity(unit=self.district)
        self.assertEqual(self._items(self.ambiguous_user), [])

    def test_start_only_activity_belongs_to_its_start_day(self):
        activity = self._activity(unit=self.district, start_datetime=self._in_range(5))
        inside = self._items(
            self.member,
            range_start=self._in_range(5),
            range_end=self._in_range(6),
        )
        self.assertEqual(self._ids(inside), {activity.id})
        self.assertIsNone(inside[0].end)
        outside = self._items(
            self.member,
            range_start=self._in_range(6),
            range_end=self._in_range(7),
        )
        self.assertEqual(outside, [])

    def test_ranged_activity_overlaps_middle_day(self):
        activity = self._activity(
            unit=self.district,
            start_datetime=self._in_range(1),
            end_datetime=self._in_range(4),
        )
        mid = self._items(
            self.member,
            range_start=self._in_range(2),
            range_end=self._in_range(3),
        )
        self.assertEqual(self._ids(mid), {activity.id})
        self.assertEqual(mid[0].end, activity.end_datetime)

    def test_ranged_activity_ending_at_range_start_excluded(self):
        # Half-open [range_start, range_end): an activity ending exactly at the
        # range start (e.g. ending at a day's 00:00 boundary) must NOT appear on
        # that following range/day.
        boundary = self._in_range(6)
        activity = self._activity(
            unit=self.district,
            start_datetime=self._in_range(5),
            end_datetime=boundary,
        )
        after = self._items(
            self.member,
            range_start=boundary,
            range_end=self._in_range(7),
        )
        self.assertEqual(after, [])
        # The range the activity actually spans still includes it.
        during = self._items(
            self.member,
            range_start=self._in_range(5),
            range_end=boundary,
        )
        self.assertEqual(self._ids(during), {activity.id})


# Dependency-valid enabled sets that drop exactly one source module (and drop
# ministry when events is dropped, since ministry depends on events).
_ENABLED_WITHOUT = {
    "events": ["studies", "announcements", "community_events", "church_calendar"],
    "studies": ["events", "announcements", "community_events", "church_calendar"],
    "announcements": ["events", "studies", "community_events", "church_calendar"],
    "community_events": ["events", "studies", "announcements", "church_calendar"],
}


class CalendarEnablementTests(CalendarSourceProviderBase):
    """Registration + source-module enablement gate (real registry)."""

    def _seed_all_sources(self):
        # One matching, in-range item per source for self.member.
        event = ServiceEvent.objects.create(
            title="聚会",
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
            start_datetime=self._in_range(1),
            status=ServiceEvent.STATUS_PUBLISHED,
        )
        ServiceEventAudienceScope.objects.create(
            service_event=event,
            unit=self.district,
        )

        series = BibleStudySeries.objects.create(
            title="系列",
            status=BibleStudySeries.STATUS_PUBLISHED,
        )
        lesson = BibleStudyLesson.objects.create(
            series=series,
            title="课",
            lesson_date=timezone.localdate() + timedelta(days=1),
            status=BibleStudyLesson.STATUS_PUBLISHED,
        )
        meeting = BibleStudyMeeting.objects.create(
            lesson=lesson,
            meeting_datetime=self._in_range(1),
            status=BibleStudyMeeting.STATUS_PUBLISHED,
        )
        BibleStudyMeetingAudienceScope.objects.create(
            meeting=meeting,
            unit=self.district,
        )

        announcement = Announcement.objects.create(
            title="通知",
            body="内容",
            status=Announcement.STATUS_PUBLISHED,
            publish_start=self.now - timedelta(hours=1),
        )
        AnnouncementAudienceScope.objects.create(
            announcement=announcement,
            structure_unit=self.district,
        )

        activity = CommunityActivity.objects.create(
            title="活动",
            start_datetime=self._in_range(1),
            status=CommunityActivity.STATUS_PUBLISHED,
        )
        CommunityActivityAudienceScope.objects.create(
            activity=activity,
            structure_unit=self.district,
        )
        return {
            ITEM_TYPE_SERVICE_EVENT,
            ITEM_TYPE_BIBLE_STUDY_MEETING,
            ITEM_TYPE_ANNOUNCEMENT,
            ITEM_TYPE_COMMUNITY_ACTIVITY,
        }

    def _collected_types(self, user):
        items = collect_calendar_items(user, self.range_start, self.range_end)
        return {item.item_type for item in items}

    def test_all_four_types_present_when_all_enabled(self):
        expected = self._seed_all_sources()
        self.assertEqual(self._collected_types(self.member), expected)

    def test_each_disabled_source_contributes_nothing(self):
        all_types = self._seed_all_sources()
        type_by_module = {
            "events": ITEM_TYPE_SERVICE_EVENT,
            "studies": ITEM_TYPE_BIBLE_STUDY_MEETING,
            "announcements": ITEM_TYPE_ANNOUNCEMENT,
            "community_events": ITEM_TYPE_COMMUNITY_ACTIVITY,
        }
        for module_key, item_type in type_by_module.items():
            with override_settings(CMS_ENABLED_MODULES=_ENABLED_WITHOUT[module_key]):
                types = self._collected_types(self.member)
                self.assertNotIn(item_type, types, module_key)
                self.assertEqual(types, all_types - {item_type}, module_key)

    def test_disabled_source_provider_not_called_and_runs_no_query(self):
        # The aggregator must skip a disabled module's provider entirely.
        for module_key, enabled in _ENABLED_WITHOUT.items():
            calls = []

            def spy(user, start, end, _calls=calls):
                _calls.append(user)
                return []

            provider = CalendarRangeProvider(module_key=module_key, provide=spy)
            with override_settings(CMS_ENABLED_MODULES=enabled):
                with self.assertNumQueries(0):
                    result = collect_calendar_items(
                        self.member,
                        self.range_start,
                        self.range_end,
                        providers=[provider],
                    )
            self.assertEqual(result, [])
            self.assertEqual(calls, [], module_key)

    def test_staff_status_does_not_bypass_source_disablement(self):
        self._seed_all_sources()
        with override_settings(CMS_ENABLED_MODULES=_ENABLED_WITHOUT["events"]):
            self.assertNotIn(
                ITEM_TYPE_SERVICE_EVENT,
                self._collected_types(self.staff_nonmatching),
            )


class CalendarCrossProductRegressionTests(CalendarSourceProviderBase):
    """The calendar aggregator touches no Today / serving / reading state."""

    def test_no_data_mutation_when_collecting(self):
        before = {
            "events": ServiceEvent.objects.count(),
            "meetings": BibleStudyMeeting.objects.count(),
            "announcements": Announcement.objects.count(),
            "activities": CommunityActivity.objects.count(),
            "memberships": ChurchStructureMembership.objects.count(),
        }
        collect_calendar_items(self.member, self.range_start, self.range_end)
        self.assertEqual(
            before,
            {
                "events": ServiceEvent.objects.count(),
                "meetings": BibleStudyMeeting.objects.count(),
                "announcements": Announcement.objects.count(),
                "activities": CommunityActivity.objects.count(),
                "memberships": ChurchStructureMembership.objects.count(),
            },
        )

    def test_collected_items_carry_only_member_detail_urls(self):
        # No management / edit / review URL is ever emitted.
        event = ServiceEvent.objects.create(
            title="聚会",
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
            start_datetime=self._in_range(1),
            status=ServiceEvent.STATUS_PUBLISHED,
        )
        ServiceEventAudienceScope.objects.create(
            service_event=event,
            unit=self.district,
        )
        items = collect_calendar_items(self.member, self.range_start, self.range_end)
        for item in items:
            self.assertNotIn("/edit/", item.detail_url)
            self.assertNotIn("/review/", item.detail_url)
            self.assertNotIn("/manage/", item.detail_url)
