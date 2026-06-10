# Data migration: BS-AS.1
#
# Copy each existing Bible Study Schedule's legacy single-scope value into the
# new BibleStudySeriesAudienceScope join model when a ChurchStructureUnit
# mapping already exists. Missing or ambiguous mappings are skipped so that the
# schedule keeps relying on its legacy scope fallback. This migration never
# creates ChurchStructureUnit rows and never alters legacy scope fields.

from django.db import migrations


def backfill_audience_scope(apps, schema_editor):
    BibleStudySeries = apps.get_model("studies", "BibleStudySeries")
    BibleStudySeriesAudienceScope = apps.get_model(
        "studies", "BibleStudySeriesAudienceScope"
    )
    ChurchStructureUnit = apps.get_model("accounts", "ChurchStructureUnit")

    active_roots = list(
        ChurchStructureUnit.objects.filter(unit_type="root", is_active=True)[:2]
    )
    single_active_root = active_roots[0] if len(active_roots) == 1 else None

    for series in BibleStudySeries.objects.all():
        # Idempotent: never touch a schedule that already has audience rows.
        if series.audience_scope_links.exists():
            continue

        unit = None
        scope_type = series.scope_type

        if scope_type == "global":
            unit = single_active_root
        elif scope_type == "ministry_context" and series.ministry_context_id:
            unit_id = series.ministry_context.church_structure_unit_id
            if unit_id:
                unit = ChurchStructureUnit.objects.filter(
                    id=unit_id, is_active=True
                ).first()
        elif scope_type == "district" and series.district_id:
            unit_id = series.district.church_structure_unit_id
            if unit_id:
                unit = ChurchStructureUnit.objects.filter(
                    id=unit_id, is_active=True
                ).first()
        elif scope_type == "small_group" and series.small_group_id:
            unit_id = series.small_group.church_structure_unit_id
            if unit_id:
                unit = ChurchStructureUnit.objects.filter(
                    id=unit_id, is_active=True
                ).first()

        if unit is not None:
            BibleStudySeriesAudienceScope.objects.create(series=series, unit=unit)


class Migration(migrations.Migration):

    dependencies = [
        ("studies", "0007_bible_study_series_audience_scope"),
    ]

    operations = [
        migrations.RunPython(
            backfill_audience_scope,
            migrations.RunPython.noop,
        ),
    ]
