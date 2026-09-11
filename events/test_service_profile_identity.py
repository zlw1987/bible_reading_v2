from datetime import timedelta

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.utils import timezone

from events.models import ServiceEvent, ServiceProfile
from events.service_profile_identity import (
    IDENTITY_AUDIT_VERSION,
    build_service_profile_identity_inventory,
)


def event_values(**overrides):
    values = {
        "title": "Audit event", "event_type": ServiceEvent.EVENT_SUNDAY_SERVICE,
        "start_datetime": timezone.now() + timedelta(days=1),
    }
    values.update(overrides)
    return values


class ServiceProfileIdentityAuditTests(TestCase):
    def setUp(self):
        self.profile = ServiceProfile.objects.create(
            key="local.sunday", name="Local Sunday",
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
        )

    def test_normal_inventory_is_fk_authoritative(self):
        ServiceEvent.objects.create(**event_values(service_profile=self.profile))
        inventory = build_service_profile_identity_inventory()
        self.assertEqual(inventory["version"], IDENTITY_AUDIT_VERSION)
        self.assertEqual(inventory["summary"]["fk_linked_events"], 1)
        self.assertNotIn("legacy_groups", inventory)

    def test_pre_drop_option_is_retired_with_the_column(self):
        with self.assertRaises(CommandError) as raised:
            call_command("audit_service_profile_identity", "--pre-drop-legacy-key")
        self.assertIn("unrecognized arguments", str(raised.exception))
