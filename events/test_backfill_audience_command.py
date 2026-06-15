"""SE-AS.6B/6C targeted tests for the audience-scope backfill command.

These tests cover the `backfill_service_event_audience_scopes` command: its
category counts, its **current-runtime** parity rule (legacy zero-row
`Profile.small_group` visibility vs membership-core post-row visibility,
CS-CORE.2B-A), the read-only dry-run invariants, and the `--apply` behavior.
`--apply` runs only inside the Django test database; no real database is
touched.
"""

from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from accounts.models import (
    ChurchStructureMembership,
    ChurchStructureUnit,
    District,
    SmallGroup,
)

from events.management.commands.backfill_service_event_audience_scopes import (
    run_audit,
)
from events.models import ServiceEvent, ServiceEventAudienceScope

User = get_user_model()


class _BackfillTestMixin:
    """Shared fixtures for the dry-run audit and the apply tests."""

    def setUp(self):
        self.start = timezone.now() + timezone.timedelta(days=3)
        self.end = self.start + timezone.timedelta(hours=2)

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

    def make_membership(self, user, unit, **overrides):
        """Create an active primary membership unless overridden."""
        data = {
            "user": user,
            "unit": unit,
            "status": ChurchStructureMembership.STATUS_ACTIVE,
            "is_primary": True,
            "start_date": timezone.localdate() - timezone.timedelta(days=1),
        }
        data.update(overrides)
        return ChurchStructureMembership.objects.create(**data)

    def make_user(self, username, small_group=None, membership_unit=None):
        """Create an ordinary user with optional legacy group and membership.

        ``small_group`` sets the legacy ``Profile.small_group``;
        ``membership_unit`` adds an active primary ``ChurchStructureMembership``.
        The two are independent so tests can model in-sync and drifted users.
        """
        user = User.objects.create_user(username=username, password="pw123456")
        if small_group is not None:
            user.profile.small_group = small_group
            user.profile.save()
        if membership_unit is not None:
            self.make_membership(user, membership_unit)
        return user


class BackfillServiceEventAudienceAuditTests(_BackfillTestMixin, TestCase):
    def audit(self):
        stats, _lines = run_audit()
        return stats

    # -- command output contract ---------------------------------------

    def test_default_summary_output_keeps_existing_categories(self):
        self.make_root()
        self.make_event(scope_type=ServiceEvent.SCOPE_GLOBAL)

        out = StringIO()
        call_command("backfill_service_event_audience_scopes", stdout=out)

        output = out.getvalue()
        self.assertIn("skipped (already has audience rows)", output)
        self.assertIn("global:", output)
        self.assertIn("district:", output)
        self.assertIn("small group:", output)
        self.assertIn("parity-mismatch skipped", output)
        self.assertIn("events by status:", output)
        self.assertIn("would-create audience rows", output)
        self.assertIn("legacy-fields-mutated (must be 0)", output)
        self.assertNotIn("per-event decisions:", output)

    def test_verbose_events_include_event_context_category_and_reason(self):
        root = self.make_root()
        event = self.make_event(
            title="Youth Worship",
            scope_type=ServiceEvent.SCOPE_GLOBAL,
            status=ServiceEvent.STATUS_PUBLISHED,
        )
        expected_start = timezone.localtime(event.start_datetime).strftime(
            "%Y-%m-%d %H:%M"
        )

        out = StringIO()
        call_command(
            "backfill_service_event_audience_scopes",
            "--verbose-events",
            stdout=out,
        )

        output = out.getvalue()
        self.assertIn("per-event decisions:", output)
        self.assertIn(f"event #{event.id}", output)
        self.assertIn("title: Youth Worship", output)
        self.assertIn(f"starts: {expected_start}", output)
        self.assertIn("legacy: global/published", output)
        self.assertIn("category: would-create", output)
        self.assertIn(f"proposed unit: 全教会 ({root.code})", output)
        self.assertIn("reason: global -> active root unit", output)

    def test_verbose_events_include_skipped_category_and_reason(self):
        event = self.make_event(scope_type=ServiceEvent.SCOPE_GLOBAL)

        out = StringIO()
        call_command(
            "backfill_service_event_audience_scopes",
            "--verbose-events",
            stdout=out,
        )

        output = out.getvalue()
        self.assertIn(f"event #{event.id}", output)
        self.assertIn("category: skipped-root-missing-or-ambiguous", output)
        self.assertIn("reason: global root missing or ambiguous", output)

    def test_default_command_is_dry_run_and_creates_no_rows(self):
        self.make_root()
        self.make_event(scope_type=ServiceEvent.SCOPE_GLOBAL)

        out = StringIO()
        call_command("backfill_service_event_audience_scopes", stdout=out)

        output = out.getvalue()
        self.assertEqual(ServiceEventAudienceScope.objects.count(), 0)
        self.assertIn("dry-run only", output)
        self.assertIn(
            "no ServiceEventAudienceScope rows created and no fields mutated",
            output,
        )
        self.assertNotIn("APPLY mode", output)
        self.assertNotIn("created audience rows", output)

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

    # -- 8. parity mismatch (current-runtime / membership-core) --------

    def test_parity_mismatch_when_legacy_user_lacks_active_membership(self):
        # Under the current runtime a backfilled district event matches via
        # active primary membership, but this user only has the legacy
        # Profile.small_group (no membership). Legacy would show the event;
        # membership-core would not, so the audience sets differ and the event
        # must be skipped as parity-mismatch rather than backfilled.
        d_unit = self.make_unit("D1", ChurchStructureUnit.UNIT_DISTRICT)
        g_unit = self.make_unit(
            "G1U", ChurchStructureUnit.UNIT_SMALL_GROUP, parent=d_unit
        )
        district = District.objects.create(name="North", church_structure_unit=d_unit)
        group = SmallGroup.objects.create(
            name="G1", district=district, church_structure_unit=g_unit
        )
        # Legacy group only, no membership -> drifted user.
        self.make_user("legacy_only", small_group=group)
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


class BackfillServiceEventAudienceApplyTests(_BackfillTestMixin, TestCase):
    """SE-AS.6C apply-mode tests.

    These exercise ``--apply`` only inside the Django test database; they never
    touch a real database. Apply must reuse the same parity-safe decision path
    as the dry-run, create rows only for ``would-create`` events, skip events
    that already have rows, leave legacy fields untouched, and be idempotent.
    """

    def audit(self):
        stats, _lines = run_audit()
        return stats

    def apply(self, *args):
        out = StringIO()
        call_command(
            "backfill_service_event_audience_scopes",
            "--apply",
            *args,
            stdout=out,
        )
        return out.getvalue()

    # -- 1. global apply creates exactly one root row ------------------

    def test_apply_creates_one_row_for_global_with_single_active_root(self):
        root = self.make_root()
        event = self.make_event(scope_type=ServiceEvent.SCOPE_GLOBAL)

        self.apply()

        rows = ServiceEventAudienceScope.objects.filter(service_event=event)
        self.assertEqual(rows.count(), 1)
        self.assertEqual(rows.first().unit_id, root.id)

    # -- 2. apply creates rows only for parity-safe events ------------

    def test_apply_creates_rows_only_for_parity_safe_events(self):
        # District event with an active mapped unit -> parity-safe.
        d_unit = self.make_unit("D1", ChurchStructureUnit.UNIT_DISTRICT)
        safe_district = District.objects.create(
            name="North", church_structure_unit=d_unit
        )
        SmallGroup.objects.create(name="G1", district=safe_district)
        safe_event = self.make_event(
            scope_type=ServiceEvent.SCOPE_DISTRICT, district=safe_district
        )

        # District event with no unit mapping -> unsafe, must be skipped.
        unmapped_district = District.objects.create(name="South")
        SmallGroup.objects.create(name="G2", district=unmapped_district)
        unmapped_event = self.make_event(
            scope_type=ServiceEvent.SCOPE_DISTRICT, district=unmapped_district
        )

        self.apply()

        self.assertEqual(
            ServiceEventAudienceScope.objects.filter(
                service_event=safe_event
            ).count(),
            1,
        )
        self.assertEqual(
            ServiceEventAudienceScope.objects.filter(
                service_event=unmapped_event
            ).count(),
            0,
        )

    # -- 3. existing-row events are skipped, not duplicated -----------

    def test_apply_skips_events_that_already_have_rows(self):
        self.make_root()
        unit = self.make_unit("CUSTOM", ChurchStructureUnit.UNIT_CUSTOM)
        event = self.make_event(scope_type=ServiceEvent.SCOPE_GLOBAL)
        existing = ServiceEventAudienceScope.objects.create(
            service_event=event, unit=unit
        )

        self.apply()

        rows = ServiceEventAudienceScope.objects.filter(service_event=event)
        self.assertEqual(rows.count(), 1)
        # The pre-existing row is untouched; no root row is added.
        self.assertEqual(rows.first().id, existing.id)

    # -- 4. parity-mismatch event is skipped under --apply ------------

    def test_apply_skips_parity_mismatch_event(self):
        # Current-runtime mismatch: legacy district visibility includes a user
        # whose Profile.small_group is in the district but who has no active
        # primary membership, so membership-core would drop them. Apply must
        # skip the event and create no rows.
        d_unit = self.make_unit("D1", ChurchStructureUnit.UNIT_DISTRICT)
        g_unit = self.make_unit(
            "G1U", ChurchStructureUnit.UNIT_SMALL_GROUP, parent=d_unit
        )
        district = District.objects.create(name="North", church_structure_unit=d_unit)
        group = SmallGroup.objects.create(
            name="G1", district=district, church_structure_unit=g_unit
        )
        self.make_user("profile_only_skip", small_group=group)  # no membership
        event = self.make_event(
            scope_type=ServiceEvent.SCOPE_DISTRICT, district=district
        )

        self.apply()

        self.assertEqual(
            ServiceEventAudienceScope.objects.filter(
                service_event=event
            ).count(),
            0,
        )

    # -- 5. apply is idempotent ---------------------------------------

    def test_second_apply_creates_no_additional_rows(self):
        self.make_root()
        self.make_event(scope_type=ServiceEvent.SCOPE_GLOBAL)
        self.make_unit("D1", ChurchStructureUnit.UNIT_DISTRICT)
        d_unit = ChurchStructureUnit.objects.get(code="D1")
        district = District.objects.create(
            name="North", church_structure_unit=d_unit
        )
        SmallGroup.objects.create(name="G1", district=district)
        self.make_event(
            scope_type=ServiceEvent.SCOPE_DISTRICT, district=district
        )

        first_output = self.apply()
        count_after_first = ServiceEventAudienceScope.objects.count()
        self.assertEqual(count_after_first, 2)
        self.assertIn("created audience rows                         : 2", first_output)

        second_output = self.apply()
        self.assertEqual(ServiceEventAudienceScope.objects.count(), 2)
        self.assertIn("created audience rows                         : 0", second_output)

    # -- 6. legacy fields are unchanged after --apply -----------------

    def test_apply_does_not_mutate_legacy_fields(self):
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

        self.apply()

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
        # Both events were part of the realistic setup.
        self.assertNotEqual(global_event.id, district_event.id)

    # -- 7. apply-mode output wording and created count ---------------

    def test_apply_output_includes_apply_wording_and_created_count(self):
        self.make_root()
        self.make_event(scope_type=ServiceEvent.SCOPE_GLOBAL)

        output = self.apply()

        self.assertIn("APPLY mode", output)
        self.assertIn("created audience rows                         : 1", output)
        self.assertIn(
            "Apply mode: created 1 ServiceEventAudienceScope row(s)",
            output,
        )
        self.assertIn("legacy-fields-mutated (must be 0)             : 0", output)
        self.assertNotIn("dry-run only", output)

    # -- 8. apply still supports --verbose-events ---------------------

    def test_apply_supports_verbose_events(self):
        root = self.make_root()
        event = self.make_event(scope_type=ServiceEvent.SCOPE_GLOBAL)

        output = self.apply("--verbose-events")

        self.assertIn("per-event decisions:", output)
        self.assertIn(f"event #{event.id}", output)
        self.assertIn("category: would-create", output)
        self.assertIn(f"proposed unit: 全教会 ({root.code})", output)
        self.assertEqual(
            ServiceEventAudienceScope.objects.filter(
                service_event=event
            ).count(),
            1,
        )

    # -- 9. current-runtime parity regressions (CS-CORE.2B-A) ----------

    def _mapped_district(self, district_code="D1", group_code="G1"):
        """Build a district + small group both mapped to active units."""
        d_unit = self.make_unit(district_code, ChurchStructureUnit.UNIT_DISTRICT)
        g_unit = self.make_unit(
            f"{group_code}U",
            ChurchStructureUnit.UNIT_SMALL_GROUP,
            parent=d_unit,
        )
        district = District.objects.create(
            name=district_code, church_structure_unit=d_unit
        )
        group = SmallGroup.objects.create(
            name=group_code, district=district, church_structure_unit=g_unit
        )
        return district, group, d_unit, g_unit

    def test_legacy_user_without_membership_blocks_backfill(self):
        # Regression: a user whose legacy Profile.small_group matches the event
        # but who has no active primary membership is visible pre-backfill and
        # invisible post-backfill. The dry-run must not mark would-create and
        # apply must create 0 rows for the affected district/small-group events.
        district, group, _d_unit, _g_unit = self._mapped_district()
        self.make_user("profile_only", small_group=group)  # no membership

        self.make_event(scope_type=ServiceEvent.SCOPE_DISTRICT, district=district)
        self.make_event(
            scope_type=ServiceEvent.SCOPE_SMALL_GROUP, small_group=group
        )

        stats = self.audit()
        self.assertEqual(stats["would_create_rows"], 0)
        self.assertEqual(stats["parity_mismatch_skipped"], 2)

        self.apply()
        self.assertEqual(ServiceEventAudienceScope.objects.count(), 0)

    def test_membership_pointing_elsewhere_is_parity_mismatch(self):
        # Regression: legacy group is the event's group, but the user's active
        # primary membership points at a different unit. Legacy shows the event,
        # membership-core does not, so the command must report parity mismatch
        # and skip.
        district, group, _d_unit, _g_unit = self._mapped_district()
        other_unit = self.make_unit("OTHER", ChurchStructureUnit.UNIT_SMALL_GROUP)
        self.make_user(
            "drifted", small_group=group, membership_unit=other_unit
        )

        self.make_event(
            scope_type=ServiceEvent.SCOPE_SMALL_GROUP, small_group=group
        )

        stats = self.audit()
        self.assertEqual(stats["parity_mismatch_skipped"], 1)
        self.assertEqual(stats["would_create_rows"], 0)

        self.apply()
        self.assertEqual(ServiceEventAudienceScope.objects.count(), 0)

    def test_aligned_profile_and_membership_is_parity_safe(self):
        # Positive: legacy Profile.small_group and active primary membership are
        # aligned, so legacy and membership-core audiences match. The event is
        # would-create and apply creates exactly one row at the mapped unit.
        district, group, _d_unit, g_unit = self._mapped_district()
        self.make_user("in_sync", small_group=group, membership_unit=g_unit)

        event = self.make_event(
            scope_type=ServiceEvent.SCOPE_SMALL_GROUP, small_group=group
        )

        stats = self.audit()
        self.assertEqual(stats["small_group_mapped_parity_safe"], 1)
        self.assertEqual(stats["would_create_rows"], 1)

        self.apply()
        rows = ServiceEventAudienceScope.objects.filter(service_event=event)
        self.assertEqual(rows.count(), 1)
        self.assertEqual(rows.first().unit_id, g_unit.id)

    def test_district_aligned_child_membership_is_parity_safe(self):
        # Positive district parity: the user's legacy Profile.small_group is a
        # group in the event's district, and the user's active primary
        # membership is at the child small-group unit, which is a descendant of
        # the district unit. Under user_matches_structure_audience a district
        # row matches descendants, so the legacy district audience and the
        # membership-core district audience agree. The district event must be
        # would-create, and apply must create exactly one row pointing at the
        # district unit (not the child group unit).
        district, group, d_unit, g_unit = self._mapped_district()
        self.make_user(
            "district_in_sync", small_group=group, membership_unit=g_unit
        )

        event = self.make_event(
            scope_type=ServiceEvent.SCOPE_DISTRICT, district=district
        )

        stats = self.audit()
        self.assertEqual(stats["district_mapped_parity_safe"], 1)
        self.assertEqual(stats["parity_mismatch_skipped"], 0)
        self.assertEqual(stats["would_create_rows"], 1)

        self.apply()
        rows = ServiceEventAudienceScope.objects.filter(service_event=event)
        self.assertEqual(rows.count(), 1)
        self.assertEqual(rows.first().unit_id, d_unit.id)
