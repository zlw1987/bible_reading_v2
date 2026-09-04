from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from .models import ServiceEvent, ServiceProfile
from .service_profile_identity import build_service_profile_identity_inventory


def event_values(**overrides):
    values = {
        "title": "Private event title",
        "description": "PRIVATE EVENT DESCRIPTION",
        "event_type": ServiceEvent.EVENT_SUNDAY_SERVICE,
        "start_datetime": timezone.now() + timezone.timedelta(days=7),
        "status": ServiceEvent.STATUS_PUBLISHED,
        "service_profile_key": "local.sunday",
    }
    values.update(overrides)
    return values


def profile_values(**overrides):
    values = {
        "key": "local.sunday",
        "name": "Local Sunday",
        "name_en": "Sunday",
        "event_type": ServiceEvent.EVENT_SUNDAY_SERVICE,
    }
    values.update(overrides)
    return values


class ServiceProfileIdentityInventoryTests(TestCase):
    def test_empty_and_blank_only_deployments(self):
        empty = build_service_profile_identity_inventory()
        self.assertEqual(
            empty["summary"],
            {
                "service_events_total": 0,
                "blank_legacy_key_events": 0,
                "nonblank_legacy_key_events": 0,
                "distinct_nonblank_legacy_keys": 0,
                "distinct_legacy_key_type_groups": 0,
                "conflicting_multi_type_legacy_keys": 0,
                "service_profiles_total": 0,
                "events_fk_null": 0,
                "events_fk_nonnull": 0,
                "profileless_events": 0,
                "legacy_only_events": 0,
                "exact_dual_consistent_events": 0,
                "drifted_fk_events": 0,
                "fk_blank_key_events": 0,
                "fk_key_mismatch_events": 0,
                "event_profile_type_drift_events": 0,
                "integrity_blockers": 0,
            },
        )

        ServiceEvent.objects.create(**event_values(service_profile_key=""))
        blank_only = build_service_profile_identity_inventory()
        self.assertEqual(blank_only["legacy_groups"], [])
        self.assertEqual(blank_only["blank_legacy_key"]["total_event_count"], 1)
        self.assertEqual(blank_only["summary"]["blank_legacy_key_events"], 1)
        self.assertEqual(blank_only["summary"]["integrity_blockers"], 0)

    def test_clean_multiple_groups_have_deterministic_key_then_type_order(self):
        ServiceEvent.objects.create(
            **event_values(
                service_profile_key="zeta.study",
                event_type=ServiceEvent.EVENT_BIBLE_STUDY,
            )
        )
        ServiceEvent.objects.create(
            **event_values(service_profile_key="alpha.sunday")
        )
        ServiceEvent.objects.create(
            **event_values(
                service_profile_key="zeta.other",
                event_type=ServiceEvent.EVENT_OTHER,
            )
        )

        first = build_service_profile_identity_inventory()
        second = build_service_profile_identity_inventory()
        order = [
            (row["legacy_key"], row["event_type"])
            for row in first["legacy_groups"]
        ]
        self.assertEqual(
            order,
            [
                ("alpha.sunday", ServiceEvent.EVENT_SUNDAY_SERVICE),
                ("zeta.other", ServiceEvent.EVENT_OTHER),
                ("zeta.study", ServiceEvent.EVENT_BIBLE_STUDY),
            ],
        )
        self.assertEqual(first, second)
        self.assertEqual(first["summary"]["distinct_nonblank_legacy_keys"], 3)

    def test_same_key_across_event_types_is_one_automatic_mapping_blocker(self):
        ServiceEvent.objects.create(**event_values())
        ServiceEvent.objects.create(
            **event_values(event_type=ServiceEvent.EVENT_SPECIAL_MEETING)
        )

        inventory = build_service_profile_identity_inventory()

        self.assertEqual(
            inventory["conflicting_multi_type_legacy_keys"], ["local.sunday"]
        )
        self.assertEqual(
            inventory["summary"]["conflicting_multi_type_legacy_keys"], 1
        )
        self.assertEqual(
            sum("MULTI_TYPE_LEGACY_KEY" in value for value in inventory["integrity_blockers"]),
            1,
        )

    def test_profile_unlinked_and_legacy_group_without_profile_are_visible(self):
        ServiceEvent.objects.create(**event_values())
        profile = ServiceProfile.objects.create(
            **profile_values()
        )
        ServiceEvent.objects.create(
            **event_values(
                service_profile_key="without.profile",
                start_datetime=timezone.now() + timezone.timedelta(days=14),
            )
        )

        inventory = build_service_profile_identity_inventory()
        group = next(
            row
            for row in inventory["legacy_groups"]
            if row["legacy_key"] == "without.profile"
        )
        profile_row = inventory["service_profiles"][0]

        self.assertFalse(group["matching_profile_exists"])
        self.assertIsNone(group["matching_service_profile_id"])
        self.assertEqual(profile_row["pk"], profile.pk)
        self.assertIn("ZERO_LINKED_EVENTS", profile_row["legacy_consistency_status"])
        self.assertIn("MATCHES_LEGACY_GROUP", profile_row["legacy_consistency_status"])

    def test_exact_dual_state_and_mixed_null_state_are_counted(self):
        profile = ServiceProfile.objects.create(**profile_values())
        exact = ServiceEvent.objects.create(
            **event_values(service_profile=profile)
        )
        ServiceEvent.objects.create(
            **event_values(
                start_datetime=exact.start_datetime + timezone.timedelta(days=7)
            )
        )

        inventory = build_service_profile_identity_inventory()
        row = inventory["legacy_groups"][0]

        self.assertEqual(row["total_event_count"], 2)
        self.assertEqual(row["fk_null_count"], 1)
        self.assertEqual(row["fk_nonnull_count"], 1)
        self.assertEqual(row["exact_match_fk_count"], 1)
        self.assertEqual(row["fk_mismatch_count"], 0)
        self.assertEqual(row["fk_blank_key_count"], 0)
        self.assertEqual(row["fk_key_mismatch_count"], 0)
        self.assertEqual(row["event_profile_type_mismatch_count"], 0)
        self.assertEqual(row["referenced_service_profile_ids"], [profile.pk])
        self.assertEqual(inventory["summary"]["exact_dual_consistent_events"], 1)
        self.assertEqual(inventory["summary"]["legacy_only_events"], 1)

    def test_fk_profile_key_and_event_type_drift_are_reported(self):
        key_mismatch_profile = ServiceProfile.objects.create(
            **profile_values(key="other.profile", name="Other")
        )
        type_mismatch_profile = ServiceProfile.objects.create(
            **profile_values(key="typed.profile", name="Typed")
        )
        key_drift = ServiceEvent.objects.create(**event_values())
        type_drift = ServiceEvent.objects.create(
            **event_values(
                service_profile_key="typed.profile",
                start_datetime=timezone.now() + timezone.timedelta(days=14),
            )
        )
        ServiceEvent.objects.filter(pk=key_drift.pk).update(
            service_profile_id=key_mismatch_profile.pk
        )
        ServiceEvent.objects.filter(pk=type_drift.pk).update(
            service_profile_id=type_mismatch_profile.pk,
            event_type=ServiceEvent.EVENT_OTHER,
        )

        inventory = build_service_profile_identity_inventory()

        self.assertEqual(inventory["summary"]["events_fk_nonnull"], 2)
        self.assertEqual(inventory["summary"]["exact_dual_consistent_events"], 0)
        self.assertEqual(inventory["summary"]["drifted_fk_events"], 2)
        self.assertEqual(inventory["summary"]["fk_blank_key_events"], 0)
        self.assertEqual(inventory["summary"]["fk_key_mismatch_events"], 1)
        self.assertEqual(
            inventory["summary"]["event_profile_type_drift_events"], 1
        )
        self.assertTrue(
            any(
                "EVENT_FK_KEY_DRIFT" in value
                for value in inventory["integrity_blockers"]
            )
        )
        self.assertTrue(
            any(
                "EVENT_PROFILE_TYPE_DRIFT" in value
                for value in inventory["integrity_blockers"]
            )
        )
        self.assertTrue(
            any("PROFILE_LINK_DRIFT" in value for value in inventory["integrity_blockers"])
        )
        self.assertTrue(
            all(
                "MISMATCHED_LINKED_EVENTS" in row["legacy_consistency_status"]
                for row in inventory["service_profiles"]
            )
        )

    def test_fk_blank_key_drift_is_reported_separately(self):
        profile = ServiceProfile.objects.create(**profile_values())
        event = ServiceEvent.objects.create(
            **event_values(service_profile=profile)
        )
        ServiceEvent.objects.filter(pk=event.pk).update(service_profile_key="")

        inventory = build_service_profile_identity_inventory()

        self.assertEqual(inventory["summary"]["events_fk_nonnull"], 1)
        self.assertEqual(inventory["summary"]["exact_dual_consistent_events"], 0)
        self.assertEqual(inventory["summary"]["drifted_fk_events"], 1)
        self.assertEqual(inventory["summary"]["fk_blank_key_events"], 1)
        self.assertEqual(inventory["summary"]["fk_key_mismatch_events"], 0)
        self.assertEqual(
            inventory["summary"]["event_profile_type_drift_events"], 0
        )
        self.assertEqual(
            inventory["blank_legacy_key"]["fk_blank_key_count"], 1
        )
        self.assertTrue(
            any(
                "BLANK_LEGACY_KEY_WITH_FK" in value
                for value in inventory["integrity_blockers"]
            )
        )

    def test_command_output_is_private_and_writes_zero_rows(self):
        event = ServiceEvent.objects.create(**event_values())
        before = ServiceEvent.objects.values().get(pk=event.pk)
        output = StringIO()

        call_command("audit_service_profile_identity", stdout=output)

        after = ServiceEvent.objects.values().get(pk=event.pk)
        value = output.getvalue()
        self.assertEqual(before, after)
        self.assertEqual(ServiceProfile.objects.count(), 0)
        self.assertNotIn(event.title, value)
        self.assertNotIn(event.description, value)
        self.assertIn("mode: read-only", value)
        self.assertIn("service_profiles_total: 0", value)
        self.assertIn("events_fk_null: 1", value)
        self.assertIn("legacy_only_events: 1", value)
        self.assertIn("fk_blank_key_events: 0", value)
        self.assertIn("fk_key_mismatch_events: 0", value)
        self.assertIn("event_profile_type_drift_events: 0", value)
