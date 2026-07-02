from django.contrib.auth import get_user_model
from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from .module_registry import (
    CAPABILITY_NAV,
    CAPABILITY_SETUP_CHECKS,
    CAPABILITY_TODAY,
    get_enabled_module_keys,
    get_enabled_modules,
    get_module,
    get_registered_module_keys,
    get_registered_modules,
    is_module_enabled,
    module_has_capability,
    validate_enabled_modules,
)

User = get_user_model()

ALL_MODULE_KEYS = ("reading", "prayers", "studies", "events", "ministry")


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
            get_module("community_events")
        with self.assertRaises(KeyError):
            is_module_enabled("community_events")

    def test_module_capabilities_metadata(self):
        for key in ALL_MODULE_KEYS:
            self.assertTrue(module_has_capability(key, CAPABILITY_NAV), key)
        self.assertTrue(module_has_capability("reading", CAPABILITY_TODAY))
        self.assertFalse(module_has_capability("prayers", CAPABILITY_TODAY))
        for key in ("studies", "events", "ministry"):
            self.assertTrue(module_has_capability(key, CAPABILITY_SETUP_CHECKS), key)
        self.assertFalse(module_has_capability("reading", CAPABILITY_SETUP_CHECKS))
        with self.assertRaises(KeyError):
            module_has_capability("reading", "not_a_capability")

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

    @override_settings(CMS_ENABLED_MODULES=enabled_without("prayers"))
    def test_disabled_module_direct_url_stays_reachable(self):
        # MODULAR-CORE.1A gates surfaces only; existing routes are not
        # deleted or blocked by module enablement in this slice.
        response = self.client.get(reverse("prayer_list"))
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

    @override_settings(CMS_ENABLED_MODULES=[])
    def test_home_renders_with_all_modules_disabled(self):
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
