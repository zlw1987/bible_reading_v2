"""Stage-2 physical-column retirement regression."""

from django.core.exceptions import FieldDoesNotExist
from django.test import SimpleTestCase

from events.models import ServiceEvent


class ServiceProfileCompatibilityColumnTests(SimpleTestCase):
    def test_physical_column_is_absent_after_stage_two(self):
        with self.assertRaises(FieldDoesNotExist):
            ServiceEvent._meta.get_field("service_profile_key")
