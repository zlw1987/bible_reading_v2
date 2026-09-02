from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("ministry", "0005_teamassignment_reviewed_worship_context_fingerprint"),
    ]

    operations = [
        migrations.AddField(
            model_name="ministryteam",
            name="team_key",
            field=models.CharField(
                blank=True,
                help_text=(
                    "Stable local technical identity for reviewed deployment setup "
                    "and integrations. Grants no permission or serving behavior."
                ),
                max_length=64,
                null=True,
                unique=True,
            ),
        ),
    ]
