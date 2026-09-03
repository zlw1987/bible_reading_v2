import copy
import os
import tempfile
import unittest
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connections, transaction
from django.test import TestCase
from django.utils import timezone

from ministry.models import TeamAssignment, TeamAssignmentMember
from notifications.models import Notification

from . import service_profile_mapping
from .models import ServiceEvent, ServiceEventRequiredTeam, ServiceProfile
from .service_profile_mapping import (
    PLAN_VERSION,
    ServiceProfileMappingNotReady,
    ServiceProfileMappingBusy,
    ServiceProfileMappingStale,
    apply_service_profile_mapping,
    build_service_profile_mapping_plan,
    normalize_mapping_inputs,
)


def event_values(**overrides):
    values = {
        "title": "Generic gathering",
        "title_en": "Generic gathering",
        "description": "PRIVATE EVENT NOTE",
        "event_type": ServiceEvent.EVENT_SUNDAY_SERVICE,
        "start_datetime": timezone.now() + timezone.timedelta(days=7),
        "status": ServiceEvent.STATUS_PUBLISHED,
        "service_profile_key": "local.sunday",
    }
    values.update(overrides)
    return values


def reviewed_input(**overrides):
    values = {
        "legacy_key": "local.sunday",
        "event_type": ServiceEvent.EVENT_SUNDAY_SERVICE,
        "name": "Local Sunday Service",
        "name_en": "Sunday Service",
        "description": "Reviewed local description",
        "description_en": "Reviewed English description",
    }
    values.update(overrides)
    return normalize_mapping_inputs(**values)


class ServiceProfileMappingDryRunTests(TestCase):
    def test_cli_normalizes_input_matches_exact_group_and_writes_zero_rows(self):
        event = ServiceEvent.objects.create(**event_values())
        before = ServiceEvent.objects.values().get(pk=event.pk)
        output = StringIO()

        call_command(
            "configure_service_profile_mapping",
            "--legacy-key",
            " Local.Sunday ",
            "--event-type",
            ServiceEvent.EVENT_SUNDAY_SERVICE,
            "--name",
            "Local Sunday Service",
            "--name-en",
            "Sunday Service",
            stdout=output,
        )

        event.refresh_from_db()
        self.assertEqual(ServiceEvent.objects.values().get(pk=event.pk), before)
        self.assertEqual(event.service_profile_key, "local.sunday")
        self.assertEqual(ServiceProfile.objects.count(), 0)
        value = output.getvalue()
        self.assertIn(f"plan_version: {PLAN_VERSION}", value)
        self.assertIn("proposed_key: local.sunday", value)
        self.assertIn(f"target_event_ids: [{event.pk}]", value)
        self.assertIn(f"pk={event.pk}", value)
        self.assertIn("scheduling_revision=0", value)
        self.assertRegex(value, r"confirmation_token: [0-9a-f]{64}")
        self.assertNotIn(event.description, value)

    def test_missing_apply_token_and_invalid_token_are_rejected(self):
        ServiceEvent.objects.create(**event_values())
        common = (
            "configure_service_profile_mapping",
            "--legacy-key",
            "local.sunday",
            "--event-type",
            ServiceEvent.EVENT_SUNDAY_SERVICE,
            "--name",
            "Local Sunday",
            "--apply",
        )
        with self.assertRaises(CommandError):
            call_command(*common)
        with self.assertRaises(CommandError):
            call_command(*common, "--confirmation-token", "not-a-token")
        self.assertEqual(ServiceProfile.objects.count(), 0)

    def test_no_targets_mixed_types_existing_profile_and_nonnull_fk_block(self):
        no_target = build_service_profile_mapping_plan(reviewed_input())
        self.assertFalse(no_target["ready"])
        self.assertTrue(any("NO_TARGET_EVENTS" in b for b in no_target["blockers"]))

        first = ServiceEvent.objects.create(**event_values())
        ServiceEvent.objects.create(
            **event_values(
                event_type=ServiceEvent.EVENT_OTHER,
                start_datetime=timezone.now() + timezone.timedelta(days=14),
            )
        )
        mixed = build_service_profile_mapping_plan(reviewed_input())
        self.assertTrue(any("MULTI_TYPE_LEGACY_KEY" in b for b in mixed["blockers"]))

        ServiceEvent.objects.all().delete()
        first = ServiceEvent.objects.create(**event_values())
        profile = ServiceProfile.objects.create(
            key="local.sunday",
            name="Existing",
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
        )
        existing = build_service_profile_mapping_plan(reviewed_input())
        self.assertTrue(
            any("SERVICE_PROFILE_KEY_ALREADY_EXISTS" in b for b in existing["blockers"])
        )
        ServiceEvent.objects.filter(pk=first.pk).update(service_profile_id=profile.pk)
        nonnull = build_service_profile_mapping_plan(reviewed_input())
        self.assertTrue(
            any("TARGET_FK_ALREADY_NON_NULL" in b for b in nonnull["blockers"])
        )

    def test_malformed_or_noncanonical_persisted_identity_blocks_without_repair(self):
        event = ServiceEvent.objects.create(**event_values(service_profile_key="placeholder"))
        ServiceEvent.objects.filter(pk=event.pk).update(
            service_profile_key=" Local.Sunday "
        )

        plan = build_service_profile_mapping_plan(reviewed_input())

        self.assertFalse(plan["ready"])
        self.assertTrue(
            any("NONCANONICAL_PERSISTED_LEGACY_KEY" in b for b in plan["blockers"])
        )
        event.refresh_from_db()
        self.assertEqual(event.service_profile_key, " Local.Sunday ")

    def test_token_and_order_are_deterministic_and_bind_full_metadata(self):
        later = ServiceEvent.objects.create(
            **event_values(start_datetime=timezone.now() + timezone.timedelta(days=14))
        )
        earlier_id = ServiceEvent.objects.create(
            **event_values(start_datetime=timezone.now() + timezone.timedelta(days=7))
        )
        profile_input = reviewed_input()

        first = build_service_profile_mapping_plan(profile_input)
        second = build_service_profile_mapping_plan(dict(reversed(list(profile_input.items()))))

        self.assertEqual(first["confirmation_token"], second["confirmation_token"])
        self.assertEqual(
            [row["pk"] for row in first["target_events"]],
            sorted([later.pk, earlier_id.pk]),
        )
        changed = build_service_profile_mapping_plan(
            reviewed_input(name="Changed reviewed name")
        )
        self.assertNotEqual(first["confirmation_token"], changed["confirmation_token"])


class ServiceProfileMappingStaleTests(TestCase):
    def setUp(self):
        self.event = ServiceEvent.objects.create(**event_values())
        self.profile_input = reviewed_input()

    def token(self):
        return build_service_profile_mapping_plan(self.profile_input)[
            "confirmation_token"
        ]

    def assert_zero_mapping_writes(self):
        self.assertEqual(ServiceProfile.objects.count(), 0)
        self.event.refresh_from_db()
        self.assertIsNone(self.event.service_profile_id)

    def assert_stale_after(self, mutation, *, apply_input=None):
        token = self.token()
        mutation()
        with self.assertRaises(ServiceProfileMappingStale):
            apply_service_profile_mapping(apply_input or self.profile_input, token)
        self.assert_zero_mapping_writes()

    def test_stale_when_target_added_or_removed(self):
        self.assert_stale_after(
            lambda: ServiceEvent.objects.create(
                **event_values(start_datetime=timezone.now() + timezone.timedelta(days=14))
            )
        )

        # Use a fresh state because the helper intentionally preserves the added row.
        ServiceEvent.objects.exclude(pk=self.event.pk).delete()
        self.assert_stale_after(
            lambda: ServiceEvent.objects.filter(pk=self.event.pk).update(
                service_profile_key="other.key"
            )
        )

    def test_stale_when_key_type_status_revision_or_updated_at_changes(self):
        mutations = (
            lambda: ServiceEvent.objects.filter(pk=self.event.pk).update(
                service_profile_key="other.key"
            ),
            lambda: ServiceEvent.objects.filter(pk=self.event.pk).update(
                event_type=ServiceEvent.EVENT_OTHER
            ),
            lambda: ServiceEvent.objects.filter(pk=self.event.pk).update(
                status=ServiceEvent.STATUS_CANCELLED
            ),
            lambda: ServiceEvent.objects.filter(pk=self.event.pk).update(
                scheduling_revision=99
            ),
            lambda: ServiceEvent.objects.filter(pk=self.event.pk).update(
                updated_at=timezone.now() + timezone.timedelta(seconds=1)
            ),
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                original = ServiceEvent.objects.values().get(pk=self.event.pk)
                token = self.token()
                mutation()
                with self.assertRaises(ServiceProfileMappingStale):
                    apply_service_profile_mapping(self.profile_input, token)
                self.assertEqual(ServiceProfile.objects.count(), 0)
                ServiceEvent.objects.filter(pk=self.event.pk).update(**original)
                self.event.refresh_from_db()

    def test_stale_when_target_gains_fk_or_profile_key_appears(self):
        token = self.token()
        other = ServiceProfile.objects.create(
            key="other.profile",
            name="Other",
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
        )
        ServiceEvent.objects.filter(pk=self.event.pk).update(service_profile_id=other.pk)
        with self.assertRaises(ServiceProfileMappingStale):
            apply_service_profile_mapping(self.profile_input, token)
        self.assertEqual(ServiceProfile.objects.count(), 1)
        self.event.refresh_from_db()
        self.assertEqual(self.event.service_profile_id, other.pk)

        ServiceEvent.objects.filter(pk=self.event.pk).update(service_profile_id=None)
        token = self.token()
        ServiceProfile.objects.create(
            key="local.sunday",
            name="Conflicting",
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
        )
        with self.assertRaises(ServiceProfileMappingStale):
            apply_service_profile_mapping(self.profile_input, token)
        self.event.refresh_from_db()
        self.assertIsNone(self.event.service_profile_id)

    def test_stale_when_reviewed_profile_metadata_changes(self):
        token = self.token()
        changed = reviewed_input(description="Changed after review")

        with self.assertRaises(ServiceProfileMappingStale):
            apply_service_profile_mapping(changed, token)

        self.assert_zero_mapping_writes()


class ServiceProfileMappingApplyTests(TestCase):
    def setUp(self):
        self.first = ServiceEvent.objects.create(**event_values())
        self.second = ServiceEvent.objects.create(
            **event_values(
                start_datetime=timezone.now() + timezone.timedelta(days=14),
                status=ServiceEvent.STATUS_COMPLETED,
            )
        )
        self.unrelated = ServiceEvent.objects.create(
            **event_values(
                service_profile_key="other.profile",
                start_datetime=timezone.now() + timezone.timedelta(days=21),
            )
        )
        self.profile_input = reviewed_input()

    def token(self):
        return build_service_profile_mapping_plan(self.profile_input)[
            "confirmation_token"
        ]

    def test_success_creates_exact_profile_maps_all_and_advances_once(self):
        before = {
            event.pk: {
                "revision": event.scheduling_revision,
                "key": event.service_profile_key,
                "type": event.event_type,
                "updated_at": event.updated_at,
            }
            for event in (self.first, self.second, self.unrelated)
        }
        counts = {
            "required": ServiceEventRequiredTeam.objects.count(),
            "assignments": TeamAssignment.objects.count(),
            "members": TeamAssignmentMember.objects.count(),
            "notifications": Notification.objects.count(),
        }

        result = apply_service_profile_mapping(self.profile_input, self.token())

        profile = ServiceProfile.objects.get()
        self.assertEqual(result["service_profile_id"], profile.pk)
        for field, value in self.profile_input.items():
            self.assertEqual(getattr(profile, field), value)
        for event in (self.first, self.second):
            event.refresh_from_db()
            self.assertEqual(event.service_profile_id, profile.pk)
            self.assertEqual(event.service_profile_key, before[event.pk]["key"])
            self.assertEqual(event.event_type, before[event.pk]["type"])
            self.assertEqual(event.scheduling_revision, before[event.pk]["revision"] + 1)
            self.assertGreater(event.updated_at, before[event.pk]["updated_at"])
        self.unrelated.refresh_from_db()
        self.assertIsNone(self.unrelated.service_profile_id)
        self.assertEqual(self.unrelated.scheduling_revision, before[self.unrelated.pk]["revision"])
        self.assertEqual(self.unrelated.updated_at, before[self.unrelated.pk]["updated_at"])
        self.assertEqual(
            counts,
            {
                "required": ServiceEventRequiredTeam.objects.count(),
                "assignments": TeamAssignment.objects.count(),
                "members": TeamAssignmentMember.objects.count(),
                "notifications": Notification.objects.count(),
            },
        )

    def test_failure_mid_batch_rolls_back_profile_fks_revisions_and_timestamps(self):
        token = self.token()
        before = {
            event.pk: (event.service_profile_id, event.scheduling_revision, event.updated_at)
            for event in (self.first, self.second)
        }
        original = service_profile_mapping._assign_profile_to_event
        calls = 0

        def fail_second(event_id, profile, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError("simulated mid-batch failure")
            return original(event_id, profile, **kwargs)

        with patch(
            "events.service_profile_mapping._assign_profile_to_event",
            side_effect=fail_second,
        ):
            with self.assertRaisesRegex(RuntimeError, "simulated"):
                apply_service_profile_mapping(self.profile_input, token)

        self.assertEqual(ServiceProfile.objects.count(), 0)
        for event in (self.first, self.second):
            event.refresh_from_db()
            self.assertEqual(
                (event.service_profile_id, event.scheduling_revision, event.updated_at),
                before[event.pk],
            )

    def test_second_apply_and_remap_or_rename_are_blocked(self):
        token = self.token()
        apply_service_profile_mapping(self.profile_input, token)

        with self.assertRaises((ServiceProfileMappingStale, ServiceProfileMappingNotReady)):
            apply_service_profile_mapping(self.profile_input, token)
        remap = build_service_profile_mapping_plan(self.profile_input)
        self.assertFalse(remap["ready"])
        self.assertTrue(any("ALREADY_EXISTS" in b for b in remap["blockers"]))
        self.assertTrue(any("FK_ALREADY_NON_NULL" in b for b in remap["blockers"]))
        self.assertEqual(ServiceProfile.objects.count(), 1)

    def test_command_apply_reports_post_audit_and_no_runtime_switch(self):
        output = StringIO()
        token = self.token()

        call_command(
            "configure_service_profile_mapping",
            "--legacy-key",
            "local.sunday",
            "--event-type",
            ServiceEvent.EVENT_SUNDAY_SERVICE,
            "--name",
            "Local Sunday Service",
            "--name-en",
            "Sunday Service",
            "--description",
            "Reviewed local description",
            "--description-en",
            "Reviewed English description",
            "--apply",
            "--confirmation-token",
            token,
            stdout=output,
        )

        value = output.getvalue()
        self.assertIn("APPLY COMPLETE", value)
        self.assertIn("service_profiles_created: 1", value)
        self.assertIn("service_events_mapped: 2", value)
        self.assertIn("runtime_consumer_switched: false", value)
        self.assertIn("manage.py audit_service_profile_identity", value)

    def test_independent_post_audit_proves_complete_consistency(self):
        apply_service_profile_mapping(self.profile_input, self.token())
        output = StringIO()

        call_command("audit_service_profile_identity", stdout=output)

        value = output.getvalue()
        self.assertIn("events=2 | fk_null=0 | fk_nonnull=2 | exact_fk=2", value)
        self.assertIn("fk_mismatch=0", value)
        self.assertIn("exact_dual_consistent_events: 2", value)
        self.assertIn("drifted_fk_events: 0", value)


class FileBackedSQLiteServiceProfileMappingTests(unittest.TestCase):
    """Target-like writer exclusion proof; this does not certify SQLite scale."""

    alias_a = "service_profile_mapping_file_a"
    alias_b = "service_profile_mapping_file_b"

    def setUp(self):
        handle = tempfile.NamedTemporaryFile(
            prefix="service-profile-mapping-", suffix=".sqlite3", delete=False
        )
        self.database_path = handle.name
        handle.close()
        for alias in (self.alias_a, self.alias_b):
            config = copy.deepcopy(connections.databases["default"])
            config["NAME"] = self.database_path
            config["OPTIONS"] = {**config.get("OPTIONS", {}), "timeout": 0.1}
            config["TEST"] = {"NAME": None}
            connections.databases[alias] = config

        self.connection_a = connections[self.alias_a]
        self.connection_b = connections[self.alias_b]
        with self.connection_a.cursor() as cursor:
            mode = cursor.execute("PRAGMA journal_mode=delete").fetchone()[0]
            cursor.execute("PRAGMA busy_timeout=100")
        with self.connection_b.cursor() as cursor:
            cursor.execute("PRAGMA busy_timeout=100")
        self.assertEqual(mode.lower(), "delete")
        with self.connection_a.schema_editor() as schema_editor:
            schema_editor.create_model(ServiceProfile)
            schema_editor.create_model(ServiceEvent)
        with self.connection_a.cursor() as cursor:
            cursor.execute("PRAGMA foreign_keys=OFF")
        with self.connection_b.cursor() as cursor:
            cursor.execute("PRAGMA foreign_keys=OFF")

        self.event = ServiceEvent.objects.using(self.alias_a).create(**event_values())
        self.profile_input = reviewed_input()

    def tearDown(self):
        for alias in (self.alias_a, self.alias_b):
            wrapper = connections[alias]
            wrapper.close()
            connections.databases.pop(alias, None)
            if hasattr(connections._connections, alias):
                delattr(connections._connections, alias)
        if os.path.exists(self.database_path):
            os.remove(self.database_path)

    def test_uncommitted_first_revision_write_excludes_mapping_writer(self):
        token = build_service_profile_mapping_plan(
            self.profile_input, using=self.alias_b
        )["confirmation_token"]

        with transaction.atomic(using=self.alias_a):
            ServiceEvent.objects.using(self.alias_a).filter(pk=self.event.pk).update(
                scheduling_revision=1
            )
            with self.assertRaises(ServiceProfileMappingBusy):
                apply_service_profile_mapping(
                    self.profile_input, token, using=self.alias_b
                )
            transaction.set_rollback(True, using=self.alias_a)

        current = ServiceEvent.objects.using(self.alias_b).get(pk=self.event.pk)
        self.assertEqual(current.scheduling_revision, 0)
        self.assertIsNone(current.service_profile_id)
        self.assertFalse(ServiceProfile.objects.using(self.alias_b).exists())
