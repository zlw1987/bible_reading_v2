import copy
import os
import tempfile
import unittest

from django.contrib import admin
from django.core.exceptions import ValidationError
from django.db import connections, transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase
from django.utils import timezone

from ministry.models import MinistryTeam, TeamAssignment
from ministry.admin import MinistryTeamAdmin, TeamAssignmentAdmin

from .models import ServiceEvent
from .scheduling_revision import (
    RevisionClaimState,
    SchedulingRevisionBatchClaimError,
    SchedulingRevisionBusyError,
    advance_scheduling_revisions,
    claim_scheduling_revision,
    claim_scheduling_revisions,
)


def event_values(**overrides):
    values = {
        "title": "Scheduling revision test",
        "event_type": ServiceEvent.EVENT_SUNDAY_SERVICE,
        "start_datetime": timezone.now() + timezone.timedelta(days=7),
        "status": ServiceEvent.STATUS_PUBLISHED,
    }
    values.update(overrides)
    return values


class SchedulingRevisionServiceTests(TestCase):
    def setUp(self):
        self.event = ServiceEvent.objects.create(**event_values())

    def test_field_contract_and_unconditional_advance(self):
        field = ServiceEvent._meta.get_field("scheduling_revision")
        self.assertEqual(self.event.scheduling_revision, 0)
        self.assertEqual(field.default, 0)
        self.assertFalse(field.editable)

        result = advance_scheduling_revisions((self.event.pk,))[0]

        self.assertEqual(result.state, RevisionClaimState.CLAIMED)
        self.assertEqual(result.revision, 1)
        self.event.refresh_from_db()
        self.assertEqual(self.event.scheduling_revision, 1)

    def test_expected_revision_claim_distinguishes_claimed_stale_and_missing(self):
        claimed = claim_scheduling_revision(self.event.pk, 0)
        stale = claim_scheduling_revision(self.event.pk, 0)
        missing = claim_scheduling_revision(999999, 0)

        self.assertTrue(claimed.claimed)
        self.assertEqual(claimed.revision, 1)
        self.assertEqual(stale.state, RevisionClaimState.STALE)
        self.assertEqual(stale.revision, 1)
        self.assertEqual(missing.state, RevisionClaimState.MISSING)
        self.assertIsNone(missing.revision)

    def test_outer_transaction_rollback_restores_advance(self):
        with transaction.atomic():
            advance_scheduling_revisions((self.event.pk,))
            transaction.set_rollback(True)

        self.event.refresh_from_db()
        self.assertEqual(self.event.scheduling_revision, 0)

    def test_team_assignment_fingerprinted_writes_and_delete_advance_revision(self):
        other_event = ServiceEvent.objects.create(
            **event_values(
                title="Retarget destination",
                start_datetime=timezone.now() + timezone.timedelta(days=14),
            )
        )
        team = MinistryTeam.objects.create(name="Downstream team")
        assignment = TeamAssignment.objects.create(
            service_event=self.event,
            ministry_team=team,
            status=TeamAssignment.STATUS_SCHEDULED,
        )
        self.event.refresh_from_db()
        self.assertEqual(self.event.scheduling_revision, 1)

        assignment.notes = "notes only"
        assignment.save(update_fields=["notes", "updated_at"])
        self.event.refresh_from_db()
        self.assertEqual(self.event.scheduling_revision, 1)

        assignment.service_event = other_event
        assignment.save()
        self.event.refresh_from_db()
        other_event.refresh_from_db()
        self.assertEqual(self.event.scheduling_revision, 2)
        self.assertEqual(other_event.scheduling_revision, 1)

        assignment.status = TeamAssignment.STATUS_COMPLETED
        assignment.save(update_fields=["status", "updated_at"])
        other_event.refresh_from_db()
        self.assertEqual(other_event.scheduling_revision, 2)

        assignment.status = TeamAssignment.STATUS_SCHEDULED
        assignment.save(update_fields=["status", "updated_at"])
        other_event.refresh_from_db()
        self.assertEqual(other_event.scheduling_revision, 3)

        assignment.delete()
        other_event.refresh_from_db()
        self.assertEqual(other_event.scheduling_revision, 4)

    def test_new_event_starts_at_zero_and_existing_event_save_advances(self):
        self.event.title = "Edited"
        self.event.save(update_fields=["title", "updated_at"])
        self.event.refresh_from_db()
        self.assertEqual(self.event.scheduling_revision, 1)

    def test_failed_current_assignment_create_rolls_back_revision(self):
        team = MinistryTeam.objects.create(
            name="Non-assignable",
            is_assignable=False,
        )
        with self.assertRaises(ValidationError):
            TeamAssignment.objects.create(
                service_event=self.event,
                ministry_team=team,
                status=TeamAssignment.STATUS_SCHEDULED,
            )
        self.event.refresh_from_db()
        self.assertEqual(self.event.scheduling_revision, 0)

    def test_assignment_admin_bulk_delete_advances_distinct_event_once(self):
        team = MinistryTeam.objects.create(name="Admin delete team")
        TeamAssignment.objects.create(
            service_event=self.event,
            ministry_team=team,
            status=TeamAssignment.STATUS_SCHEDULED,
        )
        TeamAssignment.objects.create(
            service_event=self.event,
            ministry_team=team,
            status=TeamAssignment.STATUS_PREPARED,
        )
        self.event.refresh_from_db()
        before = self.event.scheduling_revision

        TeamAssignmentAdmin(TeamAssignment, admin.site).delete_queryset(
            None,
            TeamAssignment.objects.filter(service_event=self.event),
        )

        self.event.refresh_from_db()
        self.assertEqual(self.event.scheduling_revision, before + 1)
        self.assertFalse(TeamAssignment.objects.exists())

    def test_ministry_team_object_and_admin_bulk_cascades_advance_events(self):
        object_team = MinistryTeam.objects.create(name="Object cascade")
        TeamAssignment.objects.create(
            service_event=self.event,
            ministry_team=object_team,
            status=TeamAssignment.STATUS_SCHEDULED,
        )
        self.event.refresh_from_db()
        before_object = self.event.scheduling_revision
        object_team.delete()
        self.event.refresh_from_db()
        self.assertEqual(self.event.scheduling_revision, before_object + 1)

        admin_team = MinistryTeam.objects.create(name="Admin cascade")
        TeamAssignment.objects.create(
            service_event=self.event,
            ministry_team=admin_team,
            status=TeamAssignment.STATUS_SCHEDULED,
        )
        self.event.refresh_from_db()
        before_admin = self.event.scheduling_revision
        MinistryTeamAdmin(MinistryTeam, admin.site).delete_queryset(
            None,
            MinistryTeam.objects.filter(pk=admin_team.pk),
        )
        self.event.refresh_from_db()
        self.assertEqual(self.event.scheduling_revision, before_admin + 1)

    def test_protected_team_delete_rolls_back_revision(self):
        team = MinistryTeam.objects.create(name="Protected required team")
        self.event.required_teams.add(team)
        TeamAssignment.objects.create(
            service_event=self.event,
            ministry_team=team,
            status=TeamAssignment.STATUS_SCHEDULED,
        )
        self.event.refresh_from_db()
        before = self.event.scheduling_revision

        with self.assertRaises(ProtectedError):
            team.delete()

        self.event.refresh_from_db()
        self.assertEqual(self.event.scheduling_revision, before)
        self.assertTrue(MinistryTeam.objects.filter(pk=team.pk).exists())


class FileBackedSQLiteSchedulingRevisionTests(unittest.TestCase):
    """Target-like two-connection proof; this does not certify SQLite scale."""

    alias_a = "scheduling_revision_file_a"
    alias_b = "scheduling_revision_file_b"

    def setUp(self):
        handle = tempfile.NamedTemporaryFile(
            prefix="scheduling-revision-", suffix=".sqlite3", delete=False
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
            schema_editor.create_model(ServiceEvent)
        with self.connection_a.cursor() as cursor:
            cursor.execute("PRAGMA foreign_keys=OFF")
        with self.connection_b.cursor() as cursor:
            cursor.execute("PRAGMA foreign_keys=OFF")

        self.event_a = ServiceEvent.objects.using(self.alias_a).create(
            **event_values(title="File A")
        )
        self.event_b = ServiceEvent.objects.using(self.alias_a).create(
            **event_values(
                title="File B",
                start_datetime=timezone.now() + timezone.timedelta(days=14),
            )
        )

    def tearDown(self):
        for alias in (self.alias_a, self.alias_b):
            wrapper = connections[alias]
            wrapper.close()
            connections.databases.pop(alias, None)
            if hasattr(connections._connections, alias):
                delattr(connections._connections, alias)
        if os.path.exists(self.database_path):
            os.remove(self.database_path)

    def revision(self, event_id, *, alias=None):
        return (
            ServiceEvent.objects.using(alias or self.alias_a)
            .filter(pk=event_id)
            .values_list("scheduling_revision", flat=True)
            .get()
        )

    def test_two_connection_stale_writer_exclusion_rollback_and_atomic_batch(self):
        # A. A committed advance makes the old expected revision stale.
        advance_scheduling_revisions((self.event_a.pk,), using=self.alias_a)
        stale = claim_scheduling_revision(
            self.event_a.pk, 0, using=self.alias_b
        )
        self.assertEqual(stale.state, RevisionClaimState.STALE)

        # B/E. A's uncommitted first revision write excludes B, even on another
        # event; B reports busy and commits neither a false success nor a write.
        before_b = self.revision(self.event_b.pk)
        with transaction.atomic(using=self.alias_a):
            advance_scheduling_revisions(
                (self.event_a.pk,), using=self.alias_a
            )
            with self.assertRaises(SchedulingRevisionBusyError):
                advance_scheduling_revisions(
                    (self.event_b.pk,), using=self.alias_b
                )
        self.assertEqual(self.revision(self.event_b.pk), before_b)

        # C. Rollback restores an already advanced revision.
        before_a = self.revision(self.event_a.pk)
        with transaction.atomic(using=self.alias_a):
            advance_scheduling_revisions(
                (self.event_a.pk,), using=self.alias_a
            )
            transaction.set_rollback(True, using=self.alias_a)
        self.assertEqual(self.revision(self.event_a.pk), before_a)

        # D. A later stale claim rolls back an earlier successful event claim.
        expected_a = self.revision(self.event_a.pk)
        expected_b = self.revision(self.event_b.pk)
        with self.assertRaises(SchedulingRevisionBatchClaimError) as raised:
            claim_scheduling_revisions(
                {
                    self.event_a.pk: expected_a,
                    self.event_b.pk: expected_b + 1,
                },
                using=self.alias_a,
            )
        self.assertEqual(
            [result.event_id for result in raised.exception.results],
            [self.event_a.pk, self.event_b.pk],
        )
        self.assertEqual(self.revision(self.event_a.pk), expected_a)
        self.assertEqual(self.revision(self.event_b.pk), expected_b)
