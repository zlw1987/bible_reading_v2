from django.db import connection
from django.core.exceptions import FieldDoesNotExist
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


class ServiceProfileKeyRemovalMigrationTests(TransactionTestCase):
    migrate_from = ("events", "0012_serviceprofile_serviceevent_service_profile")
    migrate_to = ("events", "0013_remove_serviceevent_service_profile_key")

    def test_0012_to_0013_preserves_fk_events_while_dropping_only_legacy_column(self):
        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_from])
        old_apps = executor.loader.project_state([self.migrate_from]).apps
        OldServiceEvent = old_apps.get_model("events", "ServiceEvent")
        OldServiceProfile = old_apps.get_model("events", "ServiceProfile")
        start = timezone.now() + timezone.timedelta(days=7)
        profile = OldServiceProfile.objects.create(
            key="sunday.main",
            name="Main Sunday",
            event_type="sunday_service",
        )
        exact_residue = OldServiceEvent.objects.create(
            title="Exact historical residue",
            event_type="sunday_service",
            service_profile_id=profile.pk,
            service_profile_key=profile.key,
            start_datetime=start,
            end_datetime=start + timezone.timedelta(hours=2),
            location="Main Hall",
            status="published",
            scheduling_revision=7,
        )
        fk_only = OldServiceEvent.objects.create(
            title="FK-only Stage 1 event",
            event_type="sunday_service",
            service_profile_id=profile.pk,
            service_profile_key="",
            start_datetime=start + timezone.timedelta(days=7),
            location="Chapel",
            status="completed",
            scheduling_revision=3,
        )
        profileless = OldServiceEvent.objects.create(
            title="Profileless event",
            event_type="other",
            service_profile_key="",
            start_datetime=start + timezone.timedelta(days=14),
            location="Community Room",
            status="draft",
            scheduling_revision=1,
        )

        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_to])
        new_apps = executor.loader.project_state([self.migrate_to]).apps
        NewServiceEvent = new_apps.get_model("events", "ServiceEvent")
        NewServiceProfile = new_apps.get_model("events", "ServiceProfile")
        exact_after = NewServiceEvent.objects.get(pk=exact_residue.pk)
        fk_only_after = NewServiceEvent.objects.get(pk=fk_only.pk)
        profileless_after = NewServiceEvent.objects.get(pk=profileless.pk)

        self.assertEqual(NewServiceEvent.objects.count(), 3)
        self.assertEqual(exact_after.service_profile_id, profile.pk)
        self.assertEqual(fk_only_after.service_profile_id, profile.pk)
        self.assertIsNone(profileless_after.service_profile_id)
        self.assertEqual(exact_after.event_type, "sunday_service")
        self.assertEqual(fk_only_after.event_type, "sunday_service")
        self.assertEqual(profileless_after.event_type, "other")
        self.assertEqual(exact_after.scheduling_revision, 7)
        self.assertEqual(fk_only_after.scheduling_revision, 3)
        self.assertEqual(profileless_after.scheduling_revision, 1)
        self.assertEqual(exact_after.location, "Main Hall")
        self.assertEqual(exact_after.end_datetime, start + timezone.timedelta(hours=2))
        self.assertEqual(fk_only_after.status, "completed")
        self.assertEqual(profileless_after.title, "Profileless event")
        self.assertEqual(NewServiceProfile.objects.get(pk=profile.pk).key, "sunday.main")
        with self.assertRaises(FieldDoesNotExist):
            NewServiceEvent._meta.get_field("service_profile_key")
        with connection.cursor() as cursor:
            columns = {
                column.name
                for column in connection.introspection.get_table_description(
                    cursor, NewServiceEvent._meta.db_table
                )
            }
        self.assertNotIn("service_profile_key", columns)

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()
