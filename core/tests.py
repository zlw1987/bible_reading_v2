import re
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from . import setup_readiness, today_providers
from .module_registry import (
    CAPABILITY_NAV,
    CAPABILITY_REQUIRES_STRUCTURE_CORE,
    CAPABILITY_SETUP_CHECKS,
    CAPABILITY_TODAY,
    get_enabled_module_keys,
    get_enabled_modules,
    get_enabled_primary_nav_entries,
    get_module,
    get_registered_module_keys,
    get_registered_modules,
    is_module_enabled,
    module_has_capability,
    validate_enabled_modules,
)
from .setup_readiness import (
    ReadinessContext,
    ReadinessSection,
    build_readiness_sections,
    register_readiness_provider,
)
from .today_providers import (
    build_today_context,
    get_registered_today_provider_keys,
    register_today_provider,
)

User = get_user_model()

ALL_MODULE_KEYS = (
    "reading",
    "prayers",
    "studies",
    "events",
    "community_events",
    "ministry",
)

# MODULAR-CORE.3A: the full default Today context shape contributed by the
# registered providers (reading / events / studies / ministry).
TODAY_CONTEXT_KEYS = (
    "today_items",
    "ended_plan_count",
    "today_gatherings",
    "show_all_today_gatherings_link",
    "week_gatherings",
    "show_all_gatherings_link",
    "study_meeting_context",
    "today_study_meetings",
    "week_study_meetings",
    "serving_summary",
    "leader_summary",
)


def enabled_without(*excluded):
    return [key for key in ALL_MODULE_KEYS if key not in excluded]


def _cascade_excluded(excluded):
    """Grow ``excluded`` to include every module that (transitively) depends on
    an excluded module, so the remaining set is dependency-valid."""
    dropped = set(excluded)
    changed = True
    while changed:
        changed = False
        for module in get_registered_modules():
            if module.key in dropped:
                continue
            if any(dep in dropped for dep in module.depends_on):
                dropped.add(module.key)
                changed = True
    return dropped


def enabled_without_cascade(*excluded):
    """``enabled_without`` that also drops dependents, yielding a valid enabled
    set under ``MODULAR-CORE.2A`` dependency validation. Disabling ``events``
    therefore also disables its dependent ``ministry``."""
    dropped = _cascade_excluded(excluded)
    return [key for key in ALL_MODULE_KEYS if key not in dropped]


class ModuleRegistryTests(SimpleTestCase):
    def test_registered_module_keys_are_stable(self):
        self.assertEqual(get_registered_module_keys(), ALL_MODULE_KEYS)

    def test_registered_modules_have_bilingual_labels(self):
        for module in get_registered_modules():
            self.assertTrue(module.label_en, module.key)
            self.assertTrue(module.label_zh, module.key)

    def test_primary_nav_metadata_preserves_current_links_and_order(self):
        self.assertEqual(
            tuple(
                (
                    entry.url_name,
                    entry.label_en,
                    entry.label_zh,
                    entry.active_nav,
                )
                for entry in get_enabled_primary_nav_entries()
            ),
            (
                ("my_plans", "Reading", "读经", "reading"),
                (
                    "study_session_list",
                    "Bible Study",
                    "查经",
                    "bible_study",
                ),
                ("prayer_list", "Prayer", "代祷", "prayer"),
                (
                    "service_event_list",
                    "Church Gatherings",
                    "教会聚会",
                    "events",
                ),
                ("my_serving", "My Serving", "我的服事", "my_serving"),
            ),
        )

    @override_settings(CMS_ENABLED_MODULES=["reading", "prayers"])
    def test_primary_nav_metadata_includes_enabled_modules_only(self):
        self.assertEqual(
            tuple(
                entry.url_name
                for entry in get_enabled_primary_nav_entries()
            ),
            ("my_plans", "prayer_list"),
        )

    def test_default_setting_enables_all_registered_modules(self):
        # config.settings ships CMS_ENABLED_MODULES with every module on.
        self.assertEqual(get_enabled_module_keys(), frozenset(ALL_MODULE_KEYS))
        self.assertEqual(get_enabled_modules(), get_registered_modules())

    @override_settings()
    def test_absent_setting_enables_all_registered_modules(self):
        from django.conf import settings

        del settings.CMS_ENABLED_MODULES
        self.assertEqual(get_enabled_module_keys(), frozenset(ALL_MODULE_KEYS))

    @override_settings(CMS_ENABLED_MODULES=["reading", "prayers"])
    def test_enabled_subset_respected_and_ordered(self):
        self.assertEqual(get_enabled_module_keys(), frozenset({"reading", "prayers"}))
        self.assertTrue(is_module_enabled("reading"))
        self.assertFalse(is_module_enabled("studies"))
        self.assertEqual(
            tuple(module.key for module in get_enabled_modules()),
            ("reading", "prayers"),
        )

    @override_settings(CMS_ENABLED_MODULES=["reading", "checklist"])
    def test_unregistered_key_in_setting_raises(self):
        with self.assertRaises(ImproperlyConfigured):
            get_enabled_module_keys()

    def test_unregistered_key_lookups_raise(self):
        with self.assertRaises(KeyError):
            get_module("checklist")
        with self.assertRaises(KeyError):
            is_module_enabled("checklist")

    def test_module_capabilities_metadata(self):
        for key in ("reading", "prayers", "studies", "events", "ministry"):
            self.assertTrue(module_has_capability(key, CAPABILITY_NAV), key)
        self.assertFalse(module_has_capability("community_events", CAPABILITY_NAV))
        self.assertTrue(module_has_capability("reading", CAPABILITY_TODAY))
        self.assertFalse(module_has_capability("prayers", CAPABILITY_TODAY))
        self.assertFalse(module_has_capability("community_events", CAPABILITY_TODAY))
        for key in ("studies", "events", "ministry"):
            self.assertTrue(module_has_capability(key, CAPABILITY_SETUP_CHECKS), key)
        self.assertFalse(module_has_capability("reading", CAPABILITY_SETUP_CHECKS))
        self.assertFalse(
            module_has_capability("community_events", CAPABILITY_SETUP_CHECKS)
        )
        self.assertTrue(
            module_has_capability(
                "community_events",
                CAPABILITY_REQUIRES_STRUCTURE_CORE,
            )
        )
        with self.assertRaises(KeyError):
            module_has_capability("reading", "not_a_capability")

    @override_settings(CMS_ENABLED_MODULES=["community_events"])
    def test_community_events_is_valid_without_module_dependencies(self):
        self.assertEqual(
            get_enabled_module_keys(),
            frozenset({"community_events"}),
        )
        module = get_module("community_events")
        self.assertEqual(module.label_en, "Community Activities")
        self.assertEqual(module.label_zh, "活动")
        self.assertEqual(module.depends_on, ())
        self.assertIsNone(module.primary_nav)

    @override_settings(
        CMS_ENABLED_MODULES=["reading", "prayers", "studies", "events", "ministry"]
    )
    def test_disabled_community_events_contributes_no_nav_or_today_surface(self):
        self.assertNotIn(
            "community_events",
            {
                entry.active_nav
                for entry in get_enabled_primary_nav_entries()
            },
        )
        self.assertNotIn(
            "community_events",
            get_registered_today_provider_keys(),
        )

    def test_ministry_declares_events_dependency(self):
        self.assertIn("events", get_module("ministry").depends_on)

    def test_default_setting_dependencies_satisfied(self):
        # config.settings ships every module enabled; ministry's events
        # dependency is satisfied, so the read stays valid.
        self.assertEqual(get_enabled_module_keys(), frozenset(ALL_MODULE_KEYS))

    @override_settings()
    def test_absent_setting_valid_and_returns_all_modules(self):
        from django.conf import settings

        del settings.CMS_ENABLED_MODULES
        self.assertEqual(get_enabled_module_keys(), frozenset(ALL_MODULE_KEYS))

    @override_settings(CMS_ENABLED_MODULES=[])
    def test_empty_list_valid_and_returns_empty_frozenset(self):
        # No module is enabled, so no depends_on rule can be violated.
        self.assertEqual(get_enabled_module_keys(), frozenset())

    @override_settings(CMS_ENABLED_MODULES=["reading", "prayers"])
    def test_subset_without_dependency_violation_valid(self):
        self.assertEqual(
            get_enabled_module_keys(), frozenset({"reading", "prayers"})
        )

    @override_settings(CMS_ENABLED_MODULES=["events", "ministry"])
    def test_subset_with_dependency_included_valid(self):
        self.assertEqual(
            get_enabled_module_keys(), frozenset({"events", "ministry"})
        )

    @override_settings(CMS_ENABLED_MODULES=["ministry"])
    def test_enabled_module_missing_dependency_raises(self):
        with self.assertRaises(ImproperlyConfigured) as ctx:
            get_enabled_module_keys()
        # The message must name both the dependent module and the missing
        # dependency clearly enough for an operator to act.
        message = str(ctx.exception)
        self.assertIn("ministry", message)
        self.assertIn("events", message)

    def test_validate_enabled_modules_none_returns_all(self):
        self.assertEqual(
            validate_enabled_modules(None), frozenset(ALL_MODULE_KEYS)
        )

    def test_validate_enabled_modules_missing_dependency_raises(self):
        with self.assertRaises(ImproperlyConfigured):
            validate_enabled_modules(["ministry"])

    def test_validate_enabled_modules_unknown_key_raises(self):
        with self.assertRaises(ImproperlyConfigured):
            validate_enabled_modules(["reading", "checklist"])


class TodayProviderRegistryTests(SimpleTestCase):
    """MODULAR-CORE.3A: the Today provider registry and aggregator."""

    def isolated_registry(self, initial=None):
        """Run a test against an empty (or seeded) provider registry so the
        real reading/events/studies/ministry registrations from
        ``reading.views`` are untouched."""
        return patch.dict(today_providers._TODAY_PROVIDERS, initial or {}, clear=True)

    def test_register_unregistered_module_key_raises(self):
        with self.isolated_registry():
            with self.assertRaises(KeyError):
                register_today_provider(
                    "checklist",
                    lambda request: {},
                    defaults={"checklist_items": []},
                )

    def test_non_callable_provider_raises(self):
        with self.isolated_registry():
            with self.assertRaises(ValueError) as ctx:
                register_today_provider(
                    "reading",
                    object(),  # not callable
                    defaults={"today_items": []},
                )
            self.assertIn("callable", str(ctx.exception))

    def test_duplicate_registration_raises(self):
        with self.isolated_registry():
            register_today_provider(
                "reading",
                lambda request: {},
                defaults={"today_items": []},
            )
            with self.assertRaises(ValueError):
                register_today_provider(
                    "reading",
                    lambda request: {},
                    defaults={"other_key": None},
                )

    def test_empty_defaults_raise(self):
        with self.isolated_registry():
            with self.assertRaises(ValueError):
                register_today_provider(
                    "reading",
                    lambda request: {},
                    defaults={},
                )

    def test_overlapping_context_keys_across_providers_raise(self):
        with self.isolated_registry():
            register_today_provider(
                "reading",
                lambda request: {},
                defaults={"today_items": []},
            )
            with self.assertRaises(ValueError) as ctx:
                register_today_provider(
                    "prayers",
                    lambda request: {},
                    defaults={"today_items": []},
                )
            self.assertIn("today_items", str(ctx.exception))

    @override_settings(CMS_ENABLED_MODULES=["prayers"])
    def test_disabled_module_provider_not_called_and_defaults_kept(self):
        calls = []

        def reading_provider(request):
            calls.append(request)
            return {"today_items": ["leaked"], "ended_plan_count": 9}

        with self.isolated_registry():
            register_today_provider(
                "reading",
                reading_provider,
                defaults={"today_items": [], "ended_plan_count": 0},
            )
            context = build_today_context(request=None)

        self.assertEqual(calls, [])
        self.assertEqual(
            context, {"today_items": [], "ended_plan_count": 0}
        )

    @override_settings(CMS_ENABLED_MODULES=["reading", "prayers"])
    def test_enabled_provider_output_merges_over_defaults(self):
        with self.isolated_registry():
            register_today_provider(
                "reading",
                lambda request: {"today_items": ["item"]},
                defaults={"today_items": [], "ended_plan_count": 0},
            )
            register_today_provider(
                "studies",
                lambda request: {"study_meeting_context": {"x": 1}},
                defaults={"study_meeting_context": {}},
            )
            context = build_today_context(request=None)

        # The enabled provider's values win; its undeclared-by-return keys
        # and the disabled provider's keys keep their safe defaults.
        self.assertEqual(
            context,
            {
                "today_items": ["item"],
                "ended_plan_count": 0,
                "study_meeting_context": {},
            },
        )

    @override_settings(CMS_ENABLED_MODULES=["reading"])
    def test_provider_returning_undeclared_key_raises(self):
        with self.isolated_registry():
            register_today_provider(
                "reading",
                lambda request: {"surprise_key": True},
                defaults={"today_items": []},
            )
            with self.assertRaises(ValueError) as ctx:
                build_today_context(request=None)
            self.assertIn("surprise_key", str(ctx.exception))

    @override_settings(CMS_ENABLED_MODULES=["prayers"])
    def test_default_values_are_copied_per_request(self):
        with self.isolated_registry():
            register_today_provider(
                "reading",
                lambda request: {},
                defaults={"today_items": [], "study_meeting_context": {}},
            )
            first = build_today_context(request=None)
            first["today_items"].append("mutated")
            first["study_meeting_context"]["mutated"] = True
            second = build_today_context(request=None)

        self.assertEqual(second["today_items"], [])
        self.assertEqual(second["study_meeting_context"], {})

    @override_settings(CMS_ENABLED_MODULES=["ministry"])
    def test_invalid_dependency_configuration_raises_through_aggregation(self):
        # ministry-without-events must fail the same way everywhere the
        # enabled set is read (MODULAR-CORE.2A); aggregation is no exception
        # and must not silently render a partial Today.
        with self.isolated_registry():
            with self.assertRaises(ImproperlyConfigured):
                build_today_context(request=None)

    def test_real_today_providers_cover_expected_modules_and_keys(self):
        # Importing reading.views registers the real providers (it is already
        # imported through the URLConf in normal runs; import explicitly so
        # this test does not depend on ordering).
        import reading.views  # noqa: F401

        self.assertEqual(
            get_registered_today_provider_keys(),
            ("reading", "events", "studies", "ministry"),
        )
        declared_keys = set()
        for provider in today_providers._TODAY_PROVIDERS.values():
            declared_keys.update(provider.defaults)
        self.assertEqual(declared_keys, set(TODAY_CONTEXT_KEYS))


class ReadinessProviderRegistryTests(SimpleTestCase):
    """MODULAR-CORE.5A: the setup/readiness provider registry and aggregator."""

    def isolated_registry(self, initial=None):
        """Run against an empty (or seeded) readiness registry so the real
        core/ministry/studies registrations are untouched."""
        return patch.dict(
            setup_readiness._READINESS_PROVIDERS, initial or {}, clear=True
        )

    def _section(self, key, title=None):
        return ReadinessSection(key, title or key)

    def _context(self):
        now = timezone.now()
        return ReadinessContext(now=now, target_date=now.date())

    def test_non_callable_provider_raises(self):
        with self.isolated_registry():
            with self.assertRaises(ValueError) as ctx:
                register_readiness_provider("core_check", object())
            self.assertIn("callable", str(ctx.exception))

    def test_duplicate_name_raises(self):
        with self.isolated_registry():
            register_readiness_provider("core_check", lambda ctx: [])
            with self.assertRaises(ValueError):
                register_readiness_provider("core_check", lambda ctx: [])

    def test_unregistered_module_key_raises(self):
        with self.isolated_registry():
            with self.assertRaises(KeyError):
                register_readiness_provider(
                    "checklist_check",
                    lambda ctx: [],
                    module_key="checklist",
                )

    @override_settings(CMS_ENABLED_MODULES=["reading", "prayers", "studies", "events"])
    def test_core_provider_always_runs_module_provider_gated(self):
        # ministry disabled (events still enabled -> dependency-valid): the
        # module provider is skipped, the core provider always contributes.
        calls = {"core": 0, "ministry": 0}

        def core_build(ctx):
            calls["core"] += 1
            return [self._section("church_structure")]

        def ministry_build(ctx):
            calls["ministry"] += 1
            return [self._section("ministry_structure")]

        with self.isolated_registry():
            register_readiness_provider("church_structure", core_build)
            register_readiness_provider(
                "ministry", ministry_build, module_key="ministry"
            )
            sections = build_readiness_sections(self._context())

        self.assertEqual(calls, {"core": 1, "ministry": 0})
        self.assertEqual([s.key for s in sections], ["church_structure"])

    @override_settings(CMS_ENABLED_MODULES=None)
    def test_enabled_module_provider_runs_and_order_follows_registration(self):
        with self.isolated_registry():
            register_readiness_provider(
                "church_structure", lambda ctx: [self._section("church_structure")]
            )
            register_readiness_provider(
                "ministry",
                lambda ctx: [
                    self._section("ministry_structure"),
                    self._section("team_serving"),
                ],
                module_key="ministry",
            )
            register_readiness_provider(
                "studies",
                lambda ctx: [self._section("bible_study_serving")],
                module_key="studies",
            )
            register_readiness_provider(
                "permission_admin",
                lambda ctx: [self._section("permission_admin")],
            )
            sections = build_readiness_sections(self._context())

        self.assertEqual(
            [s.key for s in sections],
            [
                "church_structure",
                "ministry_structure",
                "team_serving",
                "bible_study_serving",
                "permission_admin",
            ],
        )

    @override_settings(CMS_ENABLED_MODULES=[])
    def test_all_modules_disabled_keeps_only_core_providers(self):
        with self.isolated_registry():
            register_readiness_provider(
                "church_structure", lambda ctx: [self._section("church_structure")]
            )
            register_readiness_provider(
                "ministry",
                lambda ctx: [self._section("ministry_structure")],
                module_key="ministry",
            )
            register_readiness_provider(
                "studies",
                lambda ctx: [self._section("bible_study_serving")],
                module_key="studies",
            )
            sections = build_readiness_sections(self._context())

        self.assertEqual([s.key for s in sections], ["church_structure"])

    @override_settings(CMS_ENABLED_MODULES=["ministry"])
    def test_invalid_dependency_configuration_raises_through_aggregation(self):
        # ministry-without-events must fail the same way everywhere the enabled
        # set is read (MODULAR-CORE.2A); readiness aggregation is no exception.
        with self.isolated_registry():
            with self.assertRaises(ImproperlyConfigured):
                build_readiness_sections(self._context())

    def test_real_readiness_providers_cover_expected_names_and_modules(self):
        # Importing the audit runner module registers the real providers.
        import accounts.trial_setup_readiness  # noqa: F401

        providers = setup_readiness._READINESS_PROVIDERS
        self.assertEqual(
            tuple(providers),
            (
                "church_structure",
                "ministry",
                "studies",
                "audience_visibility",
                "permission_admin",
            ),
        )
        # Core providers (always run) vs module-gated providers.
        module_keys = {name: p.module_key for name, p in providers.items()}
        self.assertEqual(
            module_keys,
            {
                "church_structure": None,
                "ministry": "ministry",
                "studies": "studies",
                "audience_visibility": None,
                "permission_admin": None,
            },
        )


class ModuleGateTestBase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="member",
            email="",
            password="MemberPass123!",
        )
        self.client.login(username="member", password="MemberPass123!")
        session = self.client.session
        session["language"] = "en"
        session.save()

    def nav_href(self, url_name):
        return 'href="%s"' % reverse(url_name)


class ModuleGateNavTests(ModuleGateTestBase):
    MODULE_NAV_URL_NAMES = {
        "reading": "my_plans",
        "studies": "study_session_list",
        "prayers": "prayer_list",
        "events": "service_event_list",
        "ministry": "my_serving",
    }

    def test_all_modules_enabled_shows_all_primary_nav_links(self):
        response = self.client.get(reverse("profile"))

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn(self.nav_href("home"), content)
        for url_name in self.MODULE_NAV_URL_NAMES.values():
            self.assertIn(self.nav_href(url_name), content)

    def test_primary_nav_renders_bilingual_registry_labels(self):
        expected_labels = {
            "en": {
                "my_plans": "Reading",
                "study_session_list": "Bible Study",
                "prayer_list": "Prayer",
                "service_event_list": "Church Gatherings",
                "my_serving": "My Serving",
            },
            "zh": {
                "my_plans": "读经",
                "study_session_list": "查经",
                "prayer_list": "代祷",
                "service_event_list": "教会聚会",
                "my_serving": "我的服事",
            },
        }
        for language, labels in expected_labels.items():
            with self.subTest(language=language):
                session = self.client.session
                session["language"] = language
                session.save()
                response = self.client.get(reverse("profile"))

                self.assertEqual(response.status_code, 200)
                content = response.content.decode()
                for url_name, label in labels.items():
                    self.assertRegex(
                        content,
                        r'href="%s">\s*%s\s*</a>'
                        % (re.escape(reverse(url_name)), re.escape(label)),
                    )

    def test_disabling_a_module_hides_its_nav_link_and_dependents(self):
        # Disabling a module hides its own nav link. Under MODULAR-CORE.2A a
        # module cannot be disabled while a dependent stays enabled, so the
        # dependent (e.g. ministry when events is disabled) is cascaded off and
        # its link is hidden too; unrelated enabled modules stay visible.
        for module_key, url_name in self.MODULE_NAV_URL_NAMES.items():
            with self.subTest(module=module_key):
                enabled = enabled_without_cascade(module_key)
                with override_settings(CMS_ENABLED_MODULES=enabled):
                    response = self.client.get(reverse("profile"))

                self.assertEqual(response.status_code, 200)
                content = response.content.decode()
                self.assertNotIn(self.nav_href(url_name), content)
                self.assertIn(self.nav_href("home"), content)
                for other_key, other_url in self.MODULE_NAV_URL_NAMES.items():
                    if other_key == module_key:
                        continue
                    if other_key in enabled:
                        self.assertIn(self.nav_href(other_url), content)
                    else:
                        self.assertNotIn(self.nav_href(other_url), content)

    def test_disabled_module_direct_urls_stay_reachable(self):
        # MODULAR-CORE.1A gates surfaces only; existing routes are not
        # deleted or blocked by module enablement in this slice.
        for module_key, url_name in self.MODULE_NAV_URL_NAMES.items():
            with self.subTest(module=module_key):
                with override_settings(
                    CMS_ENABLED_MODULES=enabled_without_cascade(module_key)
                ):
                    response = self.client.get(reverse(url_name))
                self.assertEqual(response.status_code, 200)


class ModuleGateHomeTests(ModuleGateTestBase):
    def test_home_renders_with_all_modules_enabled(self):
        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        # Default all-enabled behavior: the Today's Reading section renders,
        # including the no-plan empty state and its reading-plans link.
        content = response.content.decode()
        self.assertIn("Today's Reading", content)
        self.assertIn("No reading plan in progress yet", content)
        self.assertIn(self.nav_href("my_plans"), content)

    @override_settings(CMS_ENABLED_MODULES=enabled_without("reading"))
    def test_home_with_reading_disabled_hides_reading_surfaces(self):
        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        # No Today's Reading section: heading, empty-state card, and
        # my_plans links (nav and body) must all be gone.
        self.assertNotIn("Today's Reading", content)
        self.assertNotIn("No reading plan in progress yet", content)
        self.assertNotIn(self.nav_href("my_plans"), content)
        # Other enabled modules still render their surfaces normally.
        self.assertIn(self.nav_href("study_session_list"), content)
        self.assertIn(self.nav_href("prayer_list"), content)
        self.assertIn(self.nav_href("service_event_list"), content)
        self.assertIn(self.nav_href("my_serving"), content)

    @override_settings(CMS_ENABLED_MODULES=enabled_without("reading"))
    def test_home_with_reading_disabled_hides_reading_surfaces_chinese(self):
        session = self.client.session
        session["language"] = "zh"
        session.save()

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertNotIn("今日读经", content)
        self.assertNotIn("还没有进行中的读经计划", content)
        self.assertNotIn(self.nav_href("my_plans"), content)

    @override_settings(CMS_ENABLED_MODULES=enabled_without("prayers"))
    def test_home_with_prayers_disabled_hides_prayer_surfaces(self):
        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        # The same stable URL covers both the primary nav and the Today action
        # card; neither surface should remain.
        self.assertNotIn(self.nav_href("prayer_list"), content)
        self.assertNotIn("Open Prayer Wall", content)
        # Unrelated action cards remain available.
        self.assertIn(self.nav_href("study_session_list"), content)
        self.assertIn(self.nav_href("my_serving"), content)

    @override_settings(CMS_ENABLED_MODULES=enabled_without("studies"))
    def test_home_with_studies_disabled_hides_bible_study_surfaces(self):
        series = SimpleNamespace(get_title=lambda language: "Leaked Study Series")
        lesson = SimpleNamespace(
            series=series,
            get_title=lambda language: "Leaked Study Lesson",
        )
        meeting = SimpleNamespace(
            id=202,
            lesson=lesson,
            meeting_datetime=timezone.now(),
        )
        meeting_rows = [{"meeting": meeting, "roles": []}]

        with (
            patch(
                "studies.today_provider.get_v2_landing_context",
                return_value={"show_no_small_group": False},
            ) as landing_context,
            patch(
                "studies.today_provider.get_study_meeting_rows_for_window",
                return_value=meeting_rows,
            ) as meeting_rows_for_window,
        ):
            response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        landing_context.assert_not_called()
        meeting_rows_for_window.assert_not_called()
        content = response.content.decode()
        self.assertNotIn(self.nav_href("study_session_list"), content)
        self.assertNotIn(
            'href="%s"' % reverse("bible_study_meeting_detail", args=[meeting.id]),
            content,
        )
        self.assertNotIn("Open Bible Study", content)
        self.assertNotIn("Today's Bible study", content)
        self.assertNotIn("Small group Bible study", content)
        self.assertNotIn("Leaked Study Lesson", content)

    @override_settings(CMS_ENABLED_MODULES=enabled_without_cascade("events"))
    def test_home_with_events_disabled_hides_events_and_ministry_surfaces(self):
        event = SimpleNamespace(
            id=101,
            start_datetime=timezone.now(),
            get_title=lambda language: "Leaked Church Gathering",
        )
        gathering_rows = [{"event": event, "serving_note": None}]

        with patch(
            "events.today_provider.get_gathering_rows_for_window",
            return_value=(gathering_rows, True),
        ) as gathering_rows_for_window:
            response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        gathering_rows_for_window.assert_not_called()
        content = response.content.decode()
        self.assertNotIn(self.nav_href("service_event_list"), content)
        self.assertNotIn(
            'href="%s"' % reverse("service_event_detail", args=[event.id]),
            content,
        )
        self.assertNotIn("Today's Church Gatherings", content)
        self.assertNotIn("Church Gatherings this week", content)
        self.assertNotIn("Leaked Church Gathering", content)
        # MODULAR-CORE.2A requires ministry to be disabled with events.
        self.assertNotIn(self.nav_href("my_serving"), content)
        self.assertNotIn("Open My Serving", content)

    @override_settings(CMS_ENABLED_MODULES=enabled_without("ministry"))
    def test_home_with_ministry_disabled_hides_serving_surfaces(self):
        with (
            patch(
                "ministry.today_provider.get_today_serving_summary",
                return_value={
                    "is_pending": True,
                    "pending_count": 1,
                    "items": [],
                },
            ) as serving_summary,
            patch(
                "ministry.today_provider.get_today_leader_summary",
                return_value={"count": 1, "items": []},
            ) as leader_summary,
        ):
            response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        serving_summary.assert_not_called()
        leader_summary.assert_not_called()
        content = response.content.decode()
        self.assertNotIn(self.nav_href("my_serving"), content)
        self.assertNotIn("Needs your attention", content)
        self.assertNotIn("Leader Needs Attention", content)
        self.assertNotIn("Open My Serving", content)

    @override_settings(CMS_ENABLED_MODULES=enabled_without("ministry"))
    def test_profile_with_ministry_disabled_hides_my_serving_card(self):
        response = self.client.get(reverse("profile"))

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertNotIn(self.nav_href("my_serving"), content)
        self.assertNotIn("Review your upcoming ministry serving assignments", content)

    def test_home_renders_with_each_module_disabled(self):
        # enabled_without_cascade keeps the disabled set dependency-valid
        # (disabling events also disables its dependent ministry).
        for module_key in ALL_MODULE_KEYS:
            with self.subTest(module=module_key):
                with override_settings(
                    CMS_ENABLED_MODULES=enabled_without_cascade(module_key)
                ):
                    response = self.client.get(reverse("home"))
                self.assertEqual(response.status_code, 200)

    def test_home_context_has_all_today_keys_when_all_enabled(self):
        # MODULAR-CORE.3A: provider aggregation must keep the full default
        # context shape home() used to build inline.
        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        for key in TODAY_CONTEXT_KEYS:
            self.assertIn(key, response.context, key)

    @override_settings(CMS_ENABLED_MODULES=[])
    def test_home_context_keeps_safe_defaults_with_all_modules_disabled(self):
        # Disabled providers contribute their registered safe defaults, so
        # the template never sees a missing key or a leaked query result.
        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["today_items"], [])
        self.assertEqual(response.context["ended_plan_count"], 0)
        self.assertEqual(response.context["today_gatherings"], [])
        self.assertFalse(response.context["show_all_today_gatherings_link"])
        self.assertEqual(response.context["week_gatherings"], [])
        self.assertFalse(response.context["show_all_gatherings_link"])
        self.assertEqual(response.context["study_meeting_context"], {})
        self.assertEqual(response.context["today_study_meetings"], [])
        self.assertEqual(response.context["week_study_meetings"], [])
        self.assertIsNone(response.context["serving_summary"])
        self.assertIsNone(response.context["leader_summary"])

    @override_settings(CMS_ENABLED_MODULES=[])
    def test_home_renders_with_all_modules_disabled(self):
        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertNotIn("dashboard-action-card", content)
        self.assertNotIn("Today's Reading", content)
        self.assertNotIn("Today's Church Gatherings", content)
        self.assertNotIn("Today's Bible study", content)
        self.assertNotIn("Leader Needs Attention", content)
        for url_name in (
            "my_plans",
            "prayer_list",
            "study_session_list",
            "service_event_list",
            "my_serving",
        ):
            self.assertNotIn(self.nav_href(url_name), content)
