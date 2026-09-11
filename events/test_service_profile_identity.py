from datetime import timedelta

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from events.models import ServiceEvent, ServiceProfile
from events.service_profile_identity import (
    IDENTITY_AUDIT_VERSION,
    PRE_DROP_LEGACY_KEY_AUDIT_VERSION,
    build_pre_drop_legacy_key_inventory,
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

    def test_pre_drop_safe_states_are_ready_and_zero_write(self):
        ServiceEvent.objects.create(**event_values(title="profileless"))
        ServiceEvent.objects.create(
            **event_values(title="fk only", service_profile=self.profile)
        )
        residue = ServiceEvent.objects.create(
            **event_values(title="residue", service_profile=self.profile)
        )
        ServiceEvent.objects.filter(pk=residue.pk).update(
            service_profile_key=self.profile.key
        )
        before = list(ServiceEvent.objects.values_list("pk", "service_profile_key"))
        audit = build_pre_drop_legacy_key_inventory()
        self.assertEqual(audit["version"], PRE_DROP_LEGACY_KEY_AUDIT_VERSION)
        self.assertEqual(audit["summary"]["profileless_blank"], 1)
        self.assertEqual(audit["summary"]["fk_only_blank_legacy"], 1)
        self.assertEqual(audit["summary"]["exact_legacy_residue"], 1)
        self.assertEqual(audit["summary"]["blocker_rows"], 0)
        self.assertTrue(audit["summary"]["ready_for_column_removal"])
        self.assertEqual(before, list(ServiceEvent.objects.values_list("pk", "service_profile_key")))

    def test_pre_drop_reports_each_blocker_without_repair_or_inference(self):
        null_fk = ServiceEvent.objects.create(**event_values(title="null fk"))
        blank_fk = ServiceEvent.objects.create(**event_values(title="blank fk", service_profile=self.profile))
        mismatch = ServiceEvent.objects.create(**event_values(title="mismatch", service_profile=self.profile))
        malformed = ServiceEvent.objects.create(**event_values(title="malformed"))
        type_drift = ServiceEvent.objects.create(**event_values(title="type", service_profile=self.profile))
        ServiceEvent.objects.filter(pk=null_fk.pk).update(service_profile_key="legacy.key")
        ServiceEvent.objects.filter(pk=mismatch.pk).update(service_profile_key="other.key")
        ServiceEvent.objects.filter(pk=malformed.pk).update(service_profile_key="bad key")
        ServiceEvent.objects.filter(pk=type_drift.pk).update(
            event_type=ServiceEvent.EVENT_BIBLE_STUDY
        )
        before = list(ServiceEvent.objects.order_by("pk").values_list("pk", "service_profile_id", "service_profile_key", "event_type"))
        audit = build_pre_drop_legacy_key_inventory()
        summary = audit["summary"]
        self.assertEqual(summary["legacy_only_blockers"], 2)
        self.assertEqual(summary["fk_only_blank_legacy"], 2)
        self.assertEqual(summary["legacy_mismatch_blockers"], 1)
        self.assertEqual(summary["malformed_legacy_blockers"], 1)
        self.assertEqual(summary["event_type_blockers"], 1)
        self.assertFalse(summary["ready_for_column_removal"])
        self.assertEqual(before, list(ServiceEvent.objects.order_by("pk").values_list("pk", "service_profile_id", "service_profile_key", "event_type")))

    def test_pre_drop_command_is_explicit_read_only_mode(self):
        from io import StringIO

        output = StringIO()
        call_command("audit_service_profile_identity", "--pre-drop-legacy-key", stdout=output)
        rendered = output.getvalue()
        self.assertIn("PRE-DROP LEGACY COLUMN AUDIT", rendered)
        self.assertIn("READ-ONLY", rendered)
        self.assertIn("NO DATA CHANGED", rendered)
        self.assertIn("READINESS: READY FOR COLUMN REMOVAL", rendered)
