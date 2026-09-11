from datetime import datetime, time

from django.test import TestCase
from django.utils import timezone

from events.models import ServiceEvent, ServiceEventAudienceScope, ServiceProfile
from events.service_profile_readiness import (
    SERVICE_PROFILE_READINESS_CONTRACT_VERSION,
    build_audit,
)
from accounts.models import ChurchStructureUnit


class ServiceProfileReadinessTests(TestCase):
    def setUp(self):
        self.profile = ServiceProfile.objects.create(
            key="bethany_0930_cm", name="Sunday", event_type=ServiceEvent.EVENT_SUNDAY_SERVICE
        )
        self.unit = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_ROOT, code="CHURCH", name="Church"
        )

    def test_readiness_is_versioned_and_selects_only_by_fk(self):
        start = timezone.make_aware(datetime(2026, 1, 4, 9, 30))
        event = ServiceEvent.objects.create(
            title="Sunday", event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
            start_datetime=start, status=ServiceEvent.STATUS_PUBLISHED,
            service_profile=self.profile,
        )
        ServiceEventAudienceScope.objects.create(service_event=event, unit=self.unit)
        ServiceEvent.objects.filter(pk=event.pk).update(service_profile_key="wrong.key")
        audit = build_audit(
            profile_key=self.profile.key, year=2026, target_time=time(9, 30),
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
        )
        self.assertEqual(audit["contract_version"], SERVICE_PROFILE_READINESS_CONTRACT_VERSION)
        self.assertEqual(audit["canonical_tagged_rows"][0]["service_profile_id"], self.profile.pk)
        self.assertNotIn("legacy_only_rows", audit)
        self.assertNotIn("compatibility_key", audit["canonical_tagged_rows"][0])

    def test_missing_profile_is_a_permanent_readiness_blocker(self):
        audit = build_audit(
            profile_key="missing.profile", year=2026, target_time=time(9, 30),
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
        )
        self.assertIn("requested_service_profile_missing", audit["profile_resolution"]["issues"])
