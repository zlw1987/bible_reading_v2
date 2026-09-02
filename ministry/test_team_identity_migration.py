from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class MinistryTeamKeyMigrationTests(TransactionTestCase):
    migrate_from = (
        "ministry",
        "0005_teamassignment_reviewed_worship_context_fingerprint",
    )
    migrate_to = ("ministry", "0006_ministryteam_team_key")

    def test_existing_team_survives_with_null_key(self):
        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_from])
        old_apps = executor.loader.project_state([self.migrate_from]).apps
        OldMinistryTeam = old_apps.get_model("ministry", "MinistryTeam")
        team = OldMinistryTeam.objects.create(name="Pre-existing team")

        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_to])
        new_apps = executor.loader.project_state([self.migrate_to]).apps
        NewMinistryTeam = new_apps.get_model("ministry", "MinistryTeam")
        migrated = NewMinistryTeam.objects.get(pk=team.pk)

        self.assertIsNone(migrated.team_key)
        self.assertEqual(migrated.name, "Pre-existing team")

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()
