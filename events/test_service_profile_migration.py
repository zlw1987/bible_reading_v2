from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.utils import timezone


class ServiceProfileExpansionMigrationTests(TransactionTestCase):
    migrate_from = ("events", "0011_serviceevent_service_profile_key")
    migrate_to = ("events", "0012_serviceprofile_serviceevent_service_profile")

    def test_existing_events_survive_without_profile_inference(self):
        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_from])
        old_apps = executor.loader.project_state([self.migrate_from]).apps
        OldServiceEvent = old_apps.get_model("events", "ServiceEvent")
        start = timezone.now() + timezone.timedelta(days=7)
        end = start + timezone.timedelta(hours=2)
        tagged = OldServiceEvent.objects.create(
            title="Pre-expansion tagged event",
            event_type="sunday_service",
            service_profile_key="legacy.profile",
            start_datetime=start,
            end_datetime=end,
            location="Main Hall",
            status="published",
            scheduling_revision=7,
        )
        blank = OldServiceEvent.objects.create(
            title="Pre-expansion blank event",
            event_type="other",
            service_profile_key="",
            start_datetime=start + timezone.timedelta(days=1),
            status="draft",
            scheduling_revision=3,
        )

        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_to])
        new_apps = executor.loader.project_state([self.migrate_to]).apps
        NewServiceEvent = new_apps.get_model("events", "ServiceEvent")
        NewServiceProfile = new_apps.get_model("events", "ServiceProfile")
        migrated_tagged = NewServiceEvent.objects.get(pk=tagged.pk)
        migrated_blank = NewServiceEvent.objects.get(pk=blank.pk)

        self.assertEqual(migrated_tagged.service_profile_key, "legacy.profile")
        self.assertIsNone(migrated_tagged.service_profile_id)
        self.assertEqual(migrated_tagged.start_datetime, start)
        self.assertEqual(migrated_tagged.end_datetime, end)
        self.assertEqual(migrated_tagged.location, "Main Hall")
        self.assertEqual(migrated_tagged.scheduling_revision, 7)
        self.assertEqual(migrated_blank.service_profile_key, "")
        self.assertIsNone(migrated_blank.service_profile_id)
        self.assertEqual(migrated_blank.scheduling_revision, 3)
        self.assertEqual(NewServiceProfile.objects.count(), 0)

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()
