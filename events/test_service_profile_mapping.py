from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase


class ServiceProfileMappingRetirementTests(SimpleTestCase):
    def test_retired_mapping_command_is_unknown(self):
        with self.assertRaises(CommandError) as raised:
            call_command("configure_service_profile_mapping", stdout=StringIO())
        self.assertIn("Unknown command", str(raised.exception))
