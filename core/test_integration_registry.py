import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, override_settings

from .integration_registry import (
    CmsIntegration,
    IntegrationDisabled,
    get_enabled_integration_keys,
    get_enabled_integrations,
    get_integration,
    get_registered_integration_keys,
    get_registered_integrations,
    is_integration_enabled,
    require_integration_enabled,
    validate_enabled_integrations,
)


WORSHIP_XLSX = "svca_bethany_2026_worship_xlsx"
ALL_INTEGRATIONS = (WORSHIP_XLSX,)


class GodaddyIntegrationSettingsTests(SimpleTestCase):
    @staticmethod
    def _read_enabled_integrations(value=None, *, unset=False):
        env = os.environ.copy()
        env["DJANGO_SECRET_KEY"] = "settings-test-secret"
        if unset:
            env.pop("CMS_ENABLED_INTEGRATIONS", None)
        else:
            env["CMS_ENABLED_INTEGRATIONS"] = value

        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "import json; "
                "from config.settings_godaddy import CMS_ENABLED_INTEGRATIONS; "
                "print(json.dumps(CMS_ENABLED_INTEGRATIONS))",
            ],
            cwd=Path(settings.BASE_DIR),
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if result.returncode != 0:
            raise AssertionError(result.stdout + result.stderr)
        return json.loads(result.stdout)

    def test_missing_or_blank_environment_enables_nothing(self):
        cases = ((None, True), ("", False), ("   ", False), (", ,", False))
        for value, unset in cases:
            with self.subTest(value=value, unset=unset):
                self.assertEqual(
                    self._read_enabled_integrations(value, unset=unset),
                    [],
                )

    def test_single_integration_environment_value(self):
        self.assertEqual(
            self._read_enabled_integrations(WORSHIP_XLSX),
            [WORSHIP_XLSX],
        )

    def test_comma_separated_values_are_trimmed_and_empty_entries_ignored(self):
        self.assertEqual(
            self._read_enabled_integrations(" first, ,second,, "),
            ["first", "second"],
        )


class IntegrationRegistryTests(SimpleTestCase):
    def test_registered_metadata_is_static_and_stable(self):
        self.assertEqual(get_registered_integration_keys(), ALL_INTEGRATIONS)
        self.assertEqual(
            get_registered_integrations(),
            (
                CmsIntegration(WORSHIP_XLSX, ("events", "ministry")),
            ),
        )
        for integration in get_registered_integrations():
            self.assertTrue(
                all(isinstance(item, str) for item in integration.required_modules)
            )

    @override_settings()
    def test_absent_setting_enables_nothing(self):
        if hasattr(settings, "CMS_ENABLED_INTEGRATIONS"):
            del settings.CMS_ENABLED_INTEGRATIONS
        self.assertEqual(get_enabled_integration_keys(), frozenset())
        self.assertEqual(get_enabled_integrations(), ())

    @override_settings(CMS_ENABLED_INTEGRATIONS=None)
    def test_none_setting_enables_nothing(self):
        self.assertEqual(get_enabled_integration_keys(), frozenset())

    @override_settings(CMS_ENABLED_INTEGRATIONS=[])
    def test_empty_setting_enables_nothing(self):
        self.assertEqual(get_enabled_integration_keys(), frozenset())

    @override_settings(CMS_ENABLED_INTEGRATIONS=[WORSHIP_XLSX])
    def test_one_known_key_is_enabled(self):
        self.assertEqual(get_enabled_integration_keys(), frozenset({WORSHIP_XLSX}))
        self.assertTrue(is_integration_enabled(WORSHIP_XLSX))
        self.assertEqual(
            require_integration_enabled(WORSHIP_XLSX),
            get_integration(WORSHIP_XLSX),
        )

    @override_settings(CMS_ENABLED_INTEGRATIONS=ALL_INTEGRATIONS)
    def test_known_keys_are_enabled_in_registration_order(self):
        self.assertEqual(get_enabled_integration_keys(), frozenset(ALL_INTEGRATIONS))
        self.assertEqual(
            tuple(item.key for item in get_enabled_integrations()),
            ALL_INTEGRATIONS,
        )

    @override_settings(CMS_ENABLED_INTEGRATIONS=["unknown_adapter"])
    def test_unknown_enabled_key_raises(self):
        with self.assertRaisesMessage(ImproperlyConfigured, "unknown_adapter"):
            get_enabled_integration_keys()

    @override_settings(
        CMS_ENABLED_INTEGRATIONS=[WORSHIP_XLSX],
        CMS_ENABLED_MODULES=["events"],
    )
    def test_enabled_integration_with_disabled_required_module_raises(self):
        with self.assertRaises(ImproperlyConfigured) as ctx:
            get_enabled_integration_keys()
        self.assertIn(WORSHIP_XLSX, str(ctx.exception))
        self.assertIn("ministry", str(ctx.exception))

    @override_settings(CMS_ENABLED_INTEGRATIONS=[])
    def test_require_disabled_integration_fails_closed(self):
        with self.assertRaises(IntegrationDisabled):
            require_integration_enabled(WORSHIP_XLSX)

    def test_override_settings_results_are_not_cached(self):
        with override_settings(CMS_ENABLED_INTEGRATIONS=[]):
            self.assertEqual(get_enabled_integration_keys(), frozenset())
        with override_settings(CMS_ENABLED_INTEGRATIONS=[WORSHIP_XLSX]):
            self.assertEqual(
                get_enabled_integration_keys(),
                frozenset({WORSHIP_XLSX}),
            )
        with override_settings(CMS_ENABLED_INTEGRATIONS=None):
            self.assertEqual(get_enabled_integration_keys(), frozenset())

    def test_validate_none_is_empty_not_module_default_enable(self):
        self.assertEqual(validate_enabled_integrations(None), frozenset())


class DisabledIntegrationImportIsolationTests(SimpleTestCase):
    def test_registry_and_generic_imports_do_not_load_deployment_adapters(self):
        script = textwrap.dedent(
            """
            import importlib
            import os
            import sys

            os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

            import django
            django.setup()

            from django.conf import settings
            settings.CMS_ENABLED_INTEGRATIONS = []

            forbidden = {
                "ministry.services.worship_xlsx_preview",
                "ministry.services.worship_xlsx_confirmation",
            }
            if forbidden.intersection(sys.modules):
                raise AssertionError("Django setup eagerly loaded an adapter module")
            if any(
                name == "openpyxl" or name.startswith("openpyxl.")
                for name in sys.modules
            ):
                raise AssertionError("Django setup eagerly loaded openpyxl")

            importlib.import_module("core.integration_registry")
            if forbidden.intersection(sys.modules):
                raise AssertionError("registry metadata loaded an adapter module")

            for module_name in (
                "events.forms",
                "events.views",
                "events.urls",
                "ministry.views",
            ):
                importlib.import_module(module_name)

            from types import SimpleNamespace

            from django.db import connection
            from django.http import Http404
            from django.test import RequestFactory
            from django.test.utils import CaptureQueriesContext

            from events.views import (
                worship_workbook_confirm,
                worship_workbook_preview,
            )

            user = SimpleNamespace(
                is_authenticated=True,
                is_active=True,
                is_staff=True,
                is_superuser=True,
            )
            request_factory = RequestFactory()
            with CaptureQueriesContext(connection) as queries:
                for view in (
                    worship_workbook_preview,
                    worship_workbook_confirm,
                ):
                    request = request_factory.post("/disabled-integration/")
                    request.user = user
                    try:
                        view(request)
                    except Http404:
                        pass
                    else:
                        raise AssertionError(f"disabled route did not 404: {view}")
            if queries:
                raise AssertionError(f"disabled routes ran DB queries: {queries}")

            loaded_forbidden = sorted(forbidden.intersection(sys.modules))
            loaded_openpyxl = sorted(
                name
                for name in sys.modules
                if name == "openpyxl" or name.startswith("openpyxl.")
            )
            if loaded_forbidden or loaded_openpyxl:
                raise AssertionError(
                    f"generic imports loaded adapters={loaded_forbidden} "
                    f"openpyxl={loaded_openpyxl[:5]}"
                )
            print("GENERIC_INTEGRATION_IMPORT_ISOLATION_OK")
            """
        )
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=Path(settings.BASE_DIR),
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("GENERIC_INTEGRATION_IMPORT_ISOLATION_OK", result.stdout)
