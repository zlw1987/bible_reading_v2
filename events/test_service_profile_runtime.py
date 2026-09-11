from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from events.models import ServiceEvent, ServiceProfile
from events.service_profile_runtime import (
    ServiceProfileIdentityState,
    ServiceProfileMutationError,
    ServiceProfileResolutionError,
    clear_service_event_profile,
    inspect_service_profile_identity,
    require_service_profile,
    set_service_event_profile,
)


def event_values(**overrides):
    values = {
        "title": "Service",
        "event_type": ServiceEvent.EVENT_SUNDAY_SERVICE,
        "start_datetime": timezone.now() + timedelta(days=1),
    }
    values.update(overrides)
    return values


class ServiceProfileRuntimeTests(TestCase):
    def setUp(self):
        self.active = ServiceProfile.objects.create(
            key="local.sunday", name="Local Sunday",
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
        )
        self.other = ServiceProfile.objects.create(
            key="local.other", name="Local Other",
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
        )
        self.inactive = ServiceProfile.objects.create(
            key="local.inactive", name="Local Inactive",
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE, is_active=False,
        )

    def test_profileless_is_valid_and_required_read_fails_closed(self):
        event = ServiceEvent.objects.create(**event_values())
        identity = inspect_service_profile_identity(event)
        self.assertEqual(identity.state, ServiceProfileIdentityState.PROFILELESS)
        with self.assertRaises(ServiceProfileResolutionError):
            require_service_profile(event)

    def test_fk_identity_uses_the_exact_referenced_profile(self):
        event = ServiceEvent.objects.create(**event_values(service_profile=self.active))
        identity = inspect_service_profile_identity(event)
        self.assertEqual(identity.state, ServiceProfileIdentityState.EXACT)
        self.assertEqual(require_service_profile(event), self.active)

    def test_profile_type_mismatch_is_rejected_by_resolution(self):
        event = ServiceEvent.objects.create(**event_values(service_profile=self.active))
        ServiceEvent.objects.filter(pk=event.pk).update(
            event_type=ServiceEvent.EVENT_SPECIAL_MEETING
        )
        event.refresh_from_db()
        self.assertEqual(
            inspect_service_profile_identity(event).state,
            ServiceProfileIdentityState.EVENT_TYPE_MISMATCH,
        )
        with self.assertRaises(ServiceProfileResolutionError):
            require_service_profile(event)

    def test_fk_change_advances_once(self):
        event = ServiceEvent.objects.create(**event_values(service_profile=self.active))
        self.assertTrue(set_service_event_profile(event, self.other))
        event.refresh_from_db()
        self.assertEqual(event.service_profile_id, self.other.pk)
        self.assertEqual(event.scheduling_revision, 1)
        self.assertFalse(set_service_event_profile(event, self.other))
        event.refresh_from_db()
        self.assertEqual(event.scheduling_revision, 1)

    def test_clear_advances_once(self):
        event = ServiceEvent.objects.create(**event_values(service_profile=self.active))
        self.assertTrue(clear_service_event_profile(event))
        event.refresh_from_db()
        self.assertIsNone(event.service_profile_id)
        self.assertEqual(event.scheduling_revision, 1)

    def test_inactive_profile_cannot_be_newly_assigned_but_history_resolves(self):
        event = ServiceEvent.objects.create(**event_values())
        with self.assertRaises(ServiceProfileMutationError):
            set_service_event_profile(event, self.inactive)
        self.inactive.is_active = True
        self.inactive.save()
        historic = ServiceEvent.objects.create(**event_values(service_profile=self.inactive))
        self.inactive.is_active = False
        self.inactive.save()
        self.assertEqual(require_service_profile(historic), self.inactive)
        with self.assertRaises(ServiceProfileResolutionError):
            require_service_profile(historic, require_active=True)
