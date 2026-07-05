"""Focused tests for the CHURCH-CALENDAR.1A read-only foundation.

Covers route auth, month/day rendering and fail-safe parameter handling, the
registry/nav surface gate, safe empty states, the absence of Reading
active-plan calendar content, and the model-free range-provider contract —
including the critical member-safe boundary that disabled sources are not
called and that unauthenticated viewers fail closed. Real source providers are
intentionally stubbed in this slice (CHURCH-CALENDAR.1B integrates them).
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core.module_registry import (
    CAPABILITY_NAV,
    CAPABILITY_REQUIRES_STRUCTURE_CORE,
    CAPABILITY_TODAY,
    get_module,
    get_registered_module_keys,
    module_has_capability,
)

from . import providers, ranges
from .providers import (
    CalendarItem,
    CalendarRangeProvider,
    collect_calendar_items,
    get_registered_range_provider_keys,
    register_range_provider,
)

User = get_user_model()

# A dependency-valid enabled set that excludes church_calendar. ministry
# depends on events, so both stay enabled together.
MODULES_WITHOUT_CALENDAR = tuple(
    key for key in get_registered_module_keys() if key != "church_calendar"
)


def _aware(offset_hours=0):
    return timezone.now() + timedelta(hours=offset_hours)


class ChurchCalendarRouteTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("member1", password="pw12345!")

    def test_month_requires_login(self):
        response = self.client.get(reverse("church_calendar_month"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_day_requires_login(self):
        response = self.client.get(
            reverse("church_calendar_day", args=[2026, 7, 5])
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_month_defaults_to_current_month(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("church_calendar_month"))
        self.assertEqual(response.status_code, 200)
        today = timezone.localdate()
        self.assertEqual(response.context["calendar_year"], today.year)
        self.assertEqual(response.context["calendar_month"], today.month)
        self.assertTrue(response.context["is_current_month"])

    def test_month_valid_param_renders_that_month(self):
        self.client.force_login(self.user)
        response = self.client.get(
            reverse("church_calendar_month"), {"month": "2025-01"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["calendar_year"], 2025)
        self.assertEqual(response.context["calendar_month"], 1)
        self.assertFalse(response.context["is_current_month"])

    def test_month_invalid_param_fails_safe_to_current_month(self):
        self.client.force_login(self.user)
        today = timezone.localdate()
        for bad in ("not-a-month", "2025-13", "2025-00", "20251", "abc-de", ""):
            response = self.client.get(
                reverse("church_calendar_month"), {"month": bad}
            )
            self.assertEqual(response.status_code, 200, bad)
            self.assertEqual(response.context["calendar_month"], today.month, bad)
            self.assertEqual(response.context["calendar_year"], today.year, bad)

    def test_day_valid_route_renders(self):
        self.client.force_login(self.user)
        response = self.client.get(
            reverse("church_calendar_day", args=[2026, 7, 5])
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["calendar_date"].isoformat(), "2026-07-05")

    def test_day_invalid_route_fails_safe_with_404(self):
        self.client.force_login(self.user)
        # Feb 30 never exists; the int route matches but the view 404s.
        response = self.client.get(
            reverse("church_calendar_day", args=[2025, 2, 30])
        )
        self.assertEqual(response.status_code, 404)

    def test_month_renders_safe_empty_state_with_no_providers(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("church_calendar_month"))
        self.assertFalse(response.context["has_items"])
        self.assertEqual(list(response.context["calendar_items"]), [])
        # Default language is zh; assert the bilingual empty state renders.
        self.assertContains(response, "本月暂时没有与你相关的日程")

    def test_day_renders_safe_empty_state_with_no_providers(self):
        self.client.force_login(self.user)
        response = self.client.get(
            reverse("church_calendar_day", args=[2026, 7, 5])
        )
        self.assertFalse(response.context["has_items"])
        self.assertEqual(list(response.context["calendar_items"]), [])
        self.assertContains(response, "这一天暂时没有与你相关的日程")

    def test_no_reading_active_plan_calendar_content(self):
        self.client.force_login(self.user)
        month = self.client.get(reverse("church_calendar_month"))
        day = self.client.get(
            reverse("church_calendar_day", args=[2026, 7, 5])
        )
        for response in (month, day):
            body = response.content.decode()
            # The reading active-plan calendar is a separate reading-owned
            # surface; none of its markers should leak into this calendar.
            self.assertNotIn("active_plan", body)
            self.assertNotIn("progress_percent", body)
            self.assertNotIn("Rest day", body)


class ChurchCalendarRegistryTests(TestCase):
    def test_registry_includes_church_calendar(self):
        self.assertIn("church_calendar", get_registered_module_keys())

    def test_module_metadata(self):
        module = get_module("church_calendar")
        self.assertEqual(module.label_en, "Calendar")
        self.assertEqual(module.label_zh, "日历")
        self.assertEqual(module.primary_nav.url_name, "church_calendar_month")
        self.assertEqual(module.depends_on, ())

    def test_declares_nav_and_structure_core_but_not_today(self):
        self.assertTrue(
            module_has_capability("church_calendar", CAPABILITY_NAV)
        )
        self.assertTrue(
            module_has_capability(
                "church_calendar", CAPABILITY_REQUIRES_STRUCTURE_CORE
            )
        )
        self.assertFalse(
            module_has_capability("church_calendar", CAPABILITY_TODAY)
        )


class ChurchCalendarNavTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("member2", password="pw12345!")
        self.client.force_login(self.user)

    def test_nav_shows_calendar_when_enabled(self):
        response = self.client.get(reverse("home"))
        self.assertContains(response, reverse("church_calendar_month"))

    @override_settings(CMS_ENABLED_MODULES=MODULES_WITHOUT_CALENDAR)
    def test_nav_hides_calendar_when_disabled(self):
        response = self.client.get(reverse("home"))
        self.assertNotContains(response, reverse("church_calendar_month"))


class ChurchCalendarProviderContractTests(TestCase):
    """The model-free range-provider contract and member-safe aggregator."""

    def setUp(self):
        self.user = User.objects.create_user("member3", password="pw12345!")
        self.start, self.end = ranges.month_bounds(2026, 7)

    def _service_event_item(self, source_id=1):
        return CalendarItem(
            item_type=providers.ITEM_TYPE_SERVICE_EVENT,
            source_id=source_id,
            title="Sunday Service",
            start=_aware(),
            detail_url="/events/1/",
        )

    def test_unauthenticated_viewer_fails_closed_without_calling_providers(self):
        calls = []

        def stub(user, range_start, range_end):
            calls.append(user)
            return []

        provider = CalendarRangeProvider(module_key="events", provide=stub)
        result = collect_calendar_items(
            AnonymousUser(), self.start, self.end, providers=[provider]
        )
        self.assertEqual(result, [])
        self.assertEqual(calls, [])

    @override_settings(CMS_ENABLED_MODULES=["studies", "announcements"])
    def test_disabled_source_module_provider_not_called(self):
        calls = []

        def stub(user, range_start, range_end):
            calls.append(user)
            return [self._service_event_item()]

        provider = CalendarRangeProvider(module_key="events", provide=stub)
        result = collect_calendar_items(
            self.user, self.start, self.end, providers=[provider]
        )
        self.assertEqual(result, [])
        self.assertEqual(calls, [])

    def test_enabled_provider_called_with_aware_half_open_range(self):
        captured = {}

        def stub(user, range_start, range_end):
            captured["user"] = user
            captured["start"] = range_start
            captured["end"] = range_end
            return []

        provider = CalendarRangeProvider(module_key="events", provide=stub)
        collect_calendar_items(
            self.user, self.start, self.end, providers=[provider]
        )
        self.assertIs(captured["user"], self.user)
        self.assertTrue(timezone.is_aware(captured["start"]))
        self.assertTrue(timezone.is_aware(captured["end"]))
        self.assertLess(captured["start"], captured["end"])

    def test_naive_range_bounds_rejected(self):
        naive_start = timezone.make_naive(self.start)
        naive_end = timezone.make_naive(self.end)
        with self.assertRaises(ValueError):
            collect_calendar_items(
                self.user, naive_start, naive_end, providers=[]
            )

    def test_empty_range_rejected(self):
        with self.assertRaises(ValueError):
            collect_calendar_items(
                self.user, self.end, self.start, providers=[]
            )

    def test_valid_owned_item_passes_through(self):
        provider = CalendarRangeProvider(
            module_key="events",
            provide=lambda u, s, e: [self._service_event_item()],
        )
        result = collect_calendar_items(
            self.user, self.start, self.end, providers=[provider]
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].item_type, providers.ITEM_TYPE_SERVICE_EVENT)

    def test_provider_ownership_enforced(self):
        # events must not emit an announcement item.
        bad_item = CalendarItem(
            item_type=providers.ITEM_TYPE_ANNOUNCEMENT,
            source_id=9,
            title="Wrong owner",
            start=_aware(),
            detail_url="/announcements/9/",
            display_mode=providers.DISPLAY_ACTIVE_WINDOW,
        )
        provider = CalendarRangeProvider(
            module_key="events", provide=lambda u, s, e: [bad_item]
        )
        with self.assertRaises(ValueError):
            collect_calendar_items(
                self.user, self.start, self.end, providers=[provider]
            )

    def test_naive_item_start_rejected(self):
        bad_item = CalendarItem(
            item_type=providers.ITEM_TYPE_SERVICE_EVENT,
            source_id=2,
            title="Naive",
            start=timezone.make_naive(_aware()),
            detail_url="/events/2/",
        )
        provider = CalendarRangeProvider(
            module_key="events", provide=lambda u, s, e: [bad_item]
        )
        with self.assertRaises(ValueError):
            collect_calendar_items(
                self.user, self.start, self.end, providers=[provider]
            )

    def test_missing_detail_url_rejected(self):
        bad_item = CalendarItem(
            item_type=providers.ITEM_TYPE_SERVICE_EVENT,
            source_id=3,
            title="No URL",
            start=_aware(),
            detail_url="",
        )
        provider = CalendarRangeProvider(
            module_key="events", provide=lambda u, s, e: [bad_item]
        )
        with self.assertRaises(ValueError):
            collect_calendar_items(
                self.user, self.start, self.end, providers=[provider]
            )

    def test_duplicate_identity_within_provider_rejected(self):
        provider = CalendarRangeProvider(
            module_key="events",
            provide=lambda u, s, e: [
                self._service_event_item(source_id=5),
                self._service_event_item(source_id=5),
            ],
        )
        with self.assertRaises(ValueError):
            collect_calendar_items(
                self.user, self.start, self.end, providers=[provider]
            )

    def test_registry_registration_and_keys(self):
        def stub(user, range_start, range_end):
            return []

        self.assertNotIn("events", get_registered_range_provider_keys())
        register_range_provider("events", stub)
        try:
            self.assertIn("events", get_registered_range_provider_keys())
            with self.assertRaises(ValueError):
                register_range_provider("events", stub)  # duplicate
        finally:
            providers._RANGE_PROVIDERS.pop("events", None)

    def test_register_rejects_non_source_module(self):
        with self.assertRaises(ValueError):
            register_range_provider("reading", lambda u, s, e: [])

    def test_register_rejects_unregistered_module(self):
        with self.assertRaises(KeyError):
            register_range_provider("not_a_module", lambda u, s, e: [])
