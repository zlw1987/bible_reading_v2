"""Stage-1 physical-column regression; semantic audit coverage is separate."""

from django.test import SimpleTestCase

from events.models import ServiceEvent


class ServiceProfileCompatibilityColumnTests(SimpleTestCase):
    def test_physical_column_remains_until_separately_approved_stage_two(self):
        field = ServiceEvent._meta.get_field("service_profile_key")
        self.assertEqual(field.max_length, 64)
        self.assertEqual(field.default, "")
        self.assertTrue(field.blank)
