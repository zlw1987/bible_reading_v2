"""SE-AS.6B targeted tests for the audience-scope backfill dry-run audit.

These tests cover the read-only `backfill_service_event_audience_scopes`
command: its category counts, its parity rule, and the hard invariant that it
creates no `ServiceEventAudienceScope` rows and mutates no legacy fields.
"""

from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from accounts.models import ChurchStructureUnit, District, SmallGroup

from events.management.commands.backfill_service_event_audience_scopes import (
    run_audit,
)
from events.models import ServiceEvent, ServiceEventAudienceScope


class BackfillServiceEventAudienceAuditTests(TestCase):
    def setUp(self):
        self.start = timezone.now() + timezone.timedelta(days=3)
        self.end = self.start + timezone.timedelta(hours=2)

    # -- helpers --------------------------------------------------------

    def make_event(self, **overrides):
        data = {
            "title": "聚会",
            "title_en": "Gathering",
            "event_type": ServiceEvent.EVENT_SUNDAY_SERVICE,
            "start_datetime": self.start,
            "end_datetime": self.end,
            "location": "Sanctuary",
            "scope_type": ServiceEvent.SCOPE_GLOBAL,
            "status": ServiceEvent.STATUS_PUBLISHED,
        }
        data.update(overrides)
        return ServiceEvent.objects.create(**data)

    def make_root(self, code="CHURCH", is_active=True):
        return ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_ROOT,
            code=code,
            name="全教会",
            name_en="Whole Church",
            is_active=is_active,
        )

    def make_unit(self, code, unit_type, parent=None, is_active=True):
        return ChurchStructureUnit.objects.create(
            parent=parent,
            unit_type=unit_type,
            code=code,
            name=code,
            is_active=is_active,
        )

    def audit(self):
        stats, _lines = run_audit()
        return stats

    # -- 1. global mappable --------------------------------------------

    def test_global_event_with_single_active_root_would_create_one(self):
        self.make_root()
        self.make_event(scope_type=ServiceEvent.SCOPE_GLOBAL)

        stats = self.audit()

        self.assertEqual(stats["global_mappable"], 1)
        self.assertEqual(stats["global_skipped_root"], 0)
        self.assertEqual(stats["would_create_rows"], 1)

    # -- 2. global skipped (no root / ambiguous) -----------------------

    def test_global_event_with_no_active_root_skipped_ambiguous(self):
        self.make_event(scope_type=ServiceEvent.SCOPE_GLOBAL)

        stats = self.audit()

        self.assertEqual(stats["global_mappable"], 0)
        self.assertEqual(stats["global_skipped_root"], 1)
        self.assertEqual(stats["would_create_rows"], 0)

    def test_global_event_with_multiple_active_roots_skipped_ambiguous(self):
        self.make_root(code="CHURCH_A")
        self.make_root(code="CHURCH_B")
        self.make_event(scope_type=ServiceEvent.SCOPE_GLOBAL)

        stats = self.audit()

        self.assertEqual(stats["global_mappable"], 0)
        self.assertEqual(stats["global_skipped_root"], 1)

    # -- 3. district mapped and parity-safe ----------------------------

    def test_district_event_mapped_and_parity_safe(self):
        unit = self.make_unit("D1", ChurchStructureUnit.UNIT_DISTRICT)
        district = District.objects.create(name="North", church_structure_unit=unit)
        SmallGroup.objects.create(name="G1", district=district)
        SmallGroup.objects.create(name="G2", district=district)
        self.make_event(scope_type=ServiceEvent.SCOPE_DISTRICT, district=district)

        stats = self.audit()

        self.assertEqual(stats["district_mapped_parity_safe"], 1)
        self.assertEqual(stats["district_skipped_unsafe"], 0)
        self.assertEqual(stats["parity_mismatch_skipped"], 0)
        self.assertEqual(stats["would_create_rows"], 1)

    # -- 4. district unmapped / inactive skipped -----------------------

    def test_district_event_without_mapping_skipped_unsafe(self):
        district = District.objects.create(name="North")
        SmallGroup.objects.create(name="G1", district=district)
        self.make_event(scope_type=ServiceEvent.SCOPE_DISTRICT, district=district)

        stats = self.audit()

        self.assertEqual(stats["district_mapped_parity_safe"], 0)
        self.assertEqual(stats["district_skipped_unsafe"], 1)
        self.assertEqual(stats["would_create_rows"], 0)

    def test_district_event_with_inactive_unit_skipped_unsafe(self):
        unit = self.make_unit(
            "D1", ChurchStructureUnit.UNIT_DISTRICT, is_active=False
        )
        district = District.objects.create(name="North", church_structure_unit=unit)
        SmallGroup.objects.create(name="G1", district=district)
        self.make_event(scope_type=ServiceEvent.SCOPE_DISTRICT, district=district)

        stats = self.audit()

        self.assertEqual(stats["district_skipped_unsafe"], 1)
        self.assertEqual(stats["would_create_rows"], 0)

    # -- 5. small group mapped and parity-safe -------------------------

    def test_small_group_event_mapped_and_parity_safe(self):
        unit = self.make_unit("R4", ChurchStructureUnit.UNIT_SMALL_GROUP)
        district = District.objects.create(name="North")
        group = SmallGroup.objects.create(
            name="Rainbow 4", district=district, church_structure_unit=unit
        )
        self.make_event(
            scope_type=ServiceEvent.SCOPE_SMALL_GROUP, small_group=group
        )

        stats = self.audit()

        self.assertEqual(stats["small_group_mapped_parity_safe"], 1)
        self.assertEqual(stats["small_group_skipped_unsafe"], 0)
        self.assertEqual(stats["parity_mismatch_skipped"], 0)
        self.assertEqual(stats["would_create_rows"], 1)

    # -- 6. small group unmapped / inactive skipped --------------------

    def test_small_group_event_without_mapping_skipped_unsafe(self):
        district = District.objects.create(name="North")
        group = SmallGroup.objects.create(name="Rainbow 4", district=district)
        self.make_event(
            scope_type=ServiceEvent.SCOPE_SMALL_GROUP, small_group=group
        )

        stats = self.audit()

        self.assertEqual(stats["small_group_mapped_parity_safe"], 0)
        self.assertEqual(stats["small_group_skipped_unsafe"], 1)
        self.assertEqual(stats["would_create_rows"], 0)

    def test_small_group_event_with_inactive_unit_skipped_unsafe(self):
        unit = self.make_unit(
            "R4", ChurchStructureUnit.UNIT_SMALL_GROUP, is_active=False
        )
        district = District.objects.create(name="North")
        group = SmallGroup.objects.create(
            name="Rainbow 4", district=district, church_structure_unit=unit
        )
        self.make_event(
            scope_type=ServiceEvent.SCOPE_SMALL_GROUP, small_group=group
        )

        stats = self.audit()

        self.assertEqual(stats["small_group_skipped_unsafe"], 1)
        self.assertEqual(stats["would_create_rows"], 0)

    # -- 7. existing audience rows skipped -----------------------------

    def test_event_with_existing_audience_rows_skipped(self):
        self.make_root()
        unit = self.make_unit("CUSTOM", ChurchStructureUnit.UNIT_CUSTOM)
        event = self.make_event(scope_type=ServiceEvent.SCOPE_GLOBAL)
        ServiceEventAudienceScope.objects.create(service_event=event, unit=unit)

        stats = self.audit()

        self.assertEqual(stats["skipped_existing_rows"], 1)
        # The existing-row event is not re-classified as global-mappable.
        self.assertEqual(stats["global_mappable"], 0)
        self.assertEqual(stats["would_create_rows"], 0)

    # -- 8. parity mismatch --------------------------------------------

    def test_parity_mismatch_counted_when_inactive_group_in_district(self):
        # Legacy district visibility includes the inactive small group (legacy
        # matching ignores is_active); the resolver excludes it, so the audience
        # sets differ and the event must be skipped as parity-mismatch.
        unit = self.make_unit("D1", ChurchStructureUnit.UNIT_DISTRICT)
        district = District.objects.create(name="North", church_structure_unit=unit)
        SmallGroup.objects.create(name="Active", district=district)
        SmallGroup.objects.create(
            name="Inactive", district=district, is_active=False
        )
        self.make_event(scope_type=ServiceEvent.SCOPE_DISTRICT, district=district)

        stats = self.audit()

        self.assertEqual(stats["district_mapped_parity_safe"], 0)
        self.assertEqual(stats["parity_mismatch_skipped"], 1)
        self.assertEqual(stats["would_create_rows"], 0)

    # -- 9 & 10. audit creates nothing and mutates nothing -------------

    def test_command_creates_no_rows_and_mutates_no_legacy_fields(self):
        self.make_root()
        unit = self.make_unit("D1", ChurchStructureUnit.UNIT_DISTRICT)
        district = District.objects.create(name="North", church_structure_unit=unit)
        SmallGroup.objects.create(name="G1", district=district)
        global_event = self.make_event(scope_type=ServiceEvent.SCOPE_GLOBAL)
        district_event = self.make_event(
            scope_type=ServiceEvent.SCOPE_DISTRICT, district=district
        )

        before = {
            e.id: (e.scope_type, e.district_id, e.small_group_id, e.status)
            for e in ServiceEvent.objects.all()
        }
        rows_before = ServiceEventAudienceScope.objects.count()

        out = StringIO()
        call_command("backfill_service_event_audience_scopes", stdout=out)

        self.assertEqual(ServiceEventAudienceScope.objects.count(), rows_before)
        for event in ServiceEvent.objects.all():
            self.assertEqual(
                before[event.id],
                (
                    event.scope_type,
                    event.district_id,
                    event.small_group_id,
                    event.status,
                ),
            )

        output = out.getvalue()
        self.assertIn("legacy-fields-mutated (must be 0)             : 0", output)
        self.assertIn("would-create audience rows                    : 2", output)
        self.assertIn(
            "no ServiceEventAudienceScope rows created and no fields mutated",
            output,
        )
        # Reference both created events so the linter keeps the realistic setup.
        self.assertNotEqual(global_event.id, district_event.id)

    def test_legacy_fields_mutated_count_is_zero(self):
        self.make_root()
        self.make_event(scope_type=ServiceEvent.SCOPE_GLOBAL)

        stats = self.audit()

        self.assertEqual(stats["legacy_fields_mutated"], 0)
