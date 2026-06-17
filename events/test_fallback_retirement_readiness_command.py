"""SE-RETIRE.1A targeted tests for the read-only ServiceEvent zero-row
fallback retirement-readiness audit command.

These exercise `audit_service_event_fallback_retirement_readiness`: its
counters, its backfillable classification (delegated to the
`backfill_service_event_audience_scopes` decision path), the blocker policy
for visible/active vs harmless cancelled/past zero-row events, the
`--fail-on-blockers` gate, and the read-only invariant. Everything runs inside
the Django test database; no real database is touched.
"""

from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.utils import timezone

from accounts.models import (
    ChurchStructureMembership,
    ChurchStructureUnit,
    District,
    SmallGroup,
)

from events.management.commands.audit_service_event_fallback_retirement_readiness import (
    run_audit,
)
from events.models import ServiceEvent, ServiceEventAudienceScope

User = get_user_model()


class _ReadinessTestMixin:
    """Shared fixtures mirroring the backfill command's test factory style."""

    def setUp(self):
        self.future = timezone.now() + timezone.timedelta(days=3)
        self.past = timezone.now() - timezone.timedelta(days=3)
        self.end = self.future + timezone.timedelta(hours=2)

    def make_event(self, **overrides):
        data = {
            "title": "聚会",
            "title_en": "Gathering",
            "event_type": ServiceEvent.EVENT_SUNDAY_SERVICE,
            "start_datetime": self.future,
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
        user = User.objects.create_user(username=username, password="pw123456")
        if small_group is not None:
            user.profile.small_group = small_group
            user.profile.save()
        if membership_unit is not None:
            self.make_membership(user, membership_unit)
        return user

    def make_mapped_small_group(self, code="R4"):
        """An active small group mapped to an active small-group unit, with an
        in-sync member so a small-group backfill is parity-safe."""
        unit = self.make_unit(code, ChurchStructureUnit.UNIT_SMALL_GROUP)
        district = District.objects.create(name=f"D-{code}")
        group = SmallGroup.objects.create(
            name=code, district=district, church_structure_unit=unit
        )
        self.make_user(f"member_{code}", small_group=group, membership_unit=unit)
        return group, unit


class ServiceEventFallbackReadinessAuditTests(_ReadinessTestMixin, TestCase):
    def audit(self, event_id=None):
        stats, _lines = run_audit(event_id=event_id)
        return stats

    # 1. event with audience rows is clean -----------------------------

    def test_event_with_audience_rows_is_clean(self):
        root = self.make_root()
        event = self.make_event(scope_type=ServiceEvent.SCOPE_GLOBAL)
        ServiceEventAudienceScope.objects.create(service_event=event, unit=root)

        stats = self.audit()

        self.assertEqual(stats["events_checked"], 1)
        self.assertEqual(stats["events_with_audience_rows"], 1)
        self.assertEqual(stats["events_without_audience_rows"], 0)
        self.assertEqual(stats["blockers_total"], 0)
        self.assertEqual(stats["legacy_fields_mutated"], 0)

    # 2. published/upcoming zero-row event is a blocker ----------------

    def test_published_upcoming_zero_row_event_is_blocker(self):
        self.make_root()
        self.make_event(
            scope_type=ServiceEvent.SCOPE_GLOBAL,
            status=ServiceEvent.STATUS_PUBLISHED,
            start_datetime=self.future,
        )

        stats = self.audit()

        self.assertEqual(stats["events_without_audience_rows"], 1)
        self.assertEqual(stats["published_without_audience_rows"], 1)
        self.assertEqual(stats["future_or_upcoming_without_audience_rows"], 1)
        self.assertEqual(stats["active_visible_without_audience_rows"], 1)
        self.assertEqual(stats["blocker_visible_zero_row_events"], 1)
        self.assertGreaterEqual(stats["blockers_total"], 1)

    # 3. zero-row global fallback is classified ------------------------

    def test_zero_row_global_fallback_classified(self):
        self.make_root()
        self.make_event(scope_type=ServiceEvent.SCOPE_GLOBAL)

        stats = self.audit()

        self.assertEqual(stats["zero_row_global_fallback"], 1)
        self.assertEqual(stats["zero_row_district_fallback"], 0)
        self.assertEqual(stats["zero_row_small_group_fallback"], 0)
        # Global with a single active root is backfillable into a root row.
        self.assertEqual(stats["zero_row_backfillable"], 1)
        self.assertEqual(stats["zero_row_not_backfillable"], 0)

    # 4. district / small-group fallback classified & backfillable -----

    def test_zero_row_district_fallback_backfillable_when_mapped(self):
        unit = self.make_unit("D1", ChurchStructureUnit.UNIT_DISTRICT)
        district = District.objects.create(name="North", church_structure_unit=unit)
        SmallGroup.objects.create(name="G1", district=district)
        self.make_event(scope_type=ServiceEvent.SCOPE_DISTRICT, district=district)

        stats = self.audit()

        self.assertEqual(stats["zero_row_district_fallback"], 1)
        self.assertEqual(stats["zero_row_backfillable"], 1)
        self.assertEqual(stats["zero_row_not_backfillable"], 0)
        # Still a blocker until the rows are actually backfilled.
        self.assertEqual(stats["blocker_visible_zero_row_events"], 1)
        self.assertEqual(stats["blocker_not_backfillable_zero_row_events"], 0)

    def test_zero_row_small_group_fallback_backfillable_when_mapped(self):
        group, _unit = self.make_mapped_small_group("R4")
        self.make_event(
            scope_type=ServiceEvent.SCOPE_SMALL_GROUP, small_group=group
        )

        stats = self.audit()

        self.assertEqual(stats["zero_row_small_group_fallback"], 1)
        self.assertEqual(stats["zero_row_backfillable"], 1)
        self.assertEqual(stats["blocker_not_backfillable_zero_row_events"], 0)

    # 5. unmapped/invalid fallback is blocker / not-backfillable -------

    def test_unmapped_district_fallback_is_not_backfillable_blocker(self):
        district = District.objects.create(name="Unmapped")  # no church_structure_unit
        SmallGroup.objects.create(name="G1", district=district)
        self.make_event(scope_type=ServiceEvent.SCOPE_DISTRICT, district=district)

        stats = self.audit()

        self.assertEqual(stats["zero_row_district_fallback"], 1)
        self.assertEqual(stats["zero_row_not_backfillable"], 1)
        self.assertEqual(stats["zero_row_backfillable"], 0)
        self.assertEqual(stats["blocker_visible_zero_row_events"], 1)
        self.assertEqual(stats["blocker_not_backfillable_zero_row_events"], 1)
        self.assertGreaterEqual(stats["blockers_total"], 1)

    def test_global_without_active_root_is_not_backfillable(self):
        # No active root -> global event cannot be converted to a root row.
        self.make_event(scope_type=ServiceEvent.SCOPE_GLOBAL)

        stats = self.audit()

        self.assertEqual(stats["zero_row_global_fallback"], 1)
        self.assertEqual(stats["zero_row_not_backfillable"], 1)
        self.assertEqual(stats["blocker_not_backfillable_zero_row_events"], 1)

    # 6. cancelled / draft / past behavior matches policy --------------

    def test_cancelled_zero_row_event_is_harmless(self):
        self.make_root()
        self.make_event(
            scope_type=ServiceEvent.SCOPE_GLOBAL,
            status=ServiceEvent.STATUS_CANCELLED,
        )

        stats = self.audit()

        self.assertEqual(stats["events_without_audience_rows"], 1)
        self.assertEqual(stats["active_visible_without_audience_rows"], 0)
        self.assertEqual(stats["blocker_visible_zero_row_events"], 0)
        self.assertEqual(stats["blockers_total"], 0)

    def test_draft_zero_row_event_is_harmless(self):
        self.make_root()
        self.make_event(
            scope_type=ServiceEvent.SCOPE_GLOBAL,
            status=ServiceEvent.STATUS_DRAFT,
        )

        stats = self.audit()

        self.assertEqual(stats["active_visible_without_audience_rows"], 0)
        self.assertEqual(stats["blockers_total"], 0)

    def test_past_completed_zero_row_event_is_harmless_archive(self):
        self.make_root()
        # Completed and past-dated -> visible historically but harmless archive.
        self.make_event(
            scope_type=ServiceEvent.SCOPE_GLOBAL,
            status=ServiceEvent.STATUS_COMPLETED,
            start_datetime=self.past,
        )

        stats = self.audit()

        # It is counted as visible-without-rows but not upcoming, and not a blocker.
        self.assertEqual(stats["active_visible_without_audience_rows"], 1)
        self.assertEqual(stats["future_or_upcoming_without_audience_rows"], 0)
        self.assertEqual(stats["published_without_audience_rows"], 0)
        self.assertEqual(stats["blocker_visible_zero_row_events"], 0)
        self.assertEqual(stats["blockers_total"], 0)

    def test_clean_when_only_harmless_zero_row_events_remain(self):
        self.make_root()
        self.make_event(status=ServiceEvent.STATUS_CANCELLED)
        self.make_event(status=ServiceEvent.STATUS_DRAFT)
        self.make_event(
            status=ServiceEvent.STATUS_COMPLETED, start_datetime=self.past
        )

        stats = self.audit()

        self.assertEqual(stats["events_without_audience_rows"], 3)
        self.assertEqual(stats["blockers_total"], 0)

    # 7. --fail-on-blockers raises when blockers exist -----------------

    def test_fail_on_blockers_raises_when_blockers_exist(self):
        self.make_root()
        self.make_event(
            scope_type=ServiceEvent.SCOPE_GLOBAL,
            status=ServiceEvent.STATUS_PUBLISHED,
        )

        out = StringIO()
        with self.assertRaises(CommandError):
            call_command(
                "audit_service_event_fallback_retirement_readiness",
                "--fail-on-blockers",
                stdout=out,
            )

    def test_fail_on_blockers_does_not_raise_when_clean(self):
        root = self.make_root()
        event = self.make_event(scope_type=ServiceEvent.SCOPE_GLOBAL)
        ServiceEventAudienceScope.objects.create(service_event=event, unit=root)

        out = StringIO()
        # Should not raise.
        call_command(
            "audit_service_event_fallback_retirement_readiness",
            "--fail-on-blockers",
            stdout=out,
        )
        self.assertIn("CLEAN", out.getvalue())

    # 8. command is read-only ------------------------------------------

    def test_command_is_read_only(self):
        self.make_root()
        unit = self.make_unit("D1", ChurchStructureUnit.UNIT_DISTRICT)
        district = District.objects.create(name="North", church_structure_unit=unit)
        SmallGroup.objects.create(name="G1", district=district)
        self.make_event(scope_type=ServiceEvent.SCOPE_GLOBAL)
        self.make_event(scope_type=ServiceEvent.SCOPE_DISTRICT, district=district)

        before_events = {
            e.id: (e.scope_type, e.district_id, e.small_group_id, e.status)
            for e in ServiceEvent.objects.all()
        }
        rows_before = ServiceEventAudienceScope.objects.count()

        out = StringIO()
        call_command(
            "audit_service_event_fallback_retirement_readiness", stdout=out
        )

        self.assertEqual(ServiceEventAudienceScope.objects.count(), rows_before)
        for event in ServiceEvent.objects.all():
            self.assertEqual(
                before_events[event.id],
                (event.scope_type, event.district_id, event.small_group_id, event.status),
            )
        output = out.getvalue()
        self.assertIn("legacy-fields-mutated (must be 0)", output)
        self.assertIn("runtime-switched (must be false)", output)
        self.assertIn(": false", output)

    # -- output / option behavior --------------------------------------

    def test_verbose_lists_non_sensitive_event_context_only(self):
        self.make_root()
        event = self.make_event(
            title="Members Only Notes",
            description="SECRET BODY TEXT should never be printed",
            scope_type=ServiceEvent.SCOPE_GLOBAL,
        )

        out = StringIO()
        call_command(
            "audit_service_event_fallback_retirement_readiness",
            "--verbose",
            stdout=out,
        )

        output = out.getvalue()
        self.assertIn("per-event decisions:", output)
        self.assertIn(f"event #{event.id}", output)
        self.assertIn("title: Members Only Notes", output)
        self.assertIn("scope: global/published", output)
        self.assertNotIn("SECRET BODY TEXT", output)

    def test_limit_caps_verbose_lines(self):
        self.make_root()
        for _ in range(4):
            self.make_event(scope_type=ServiceEvent.SCOPE_GLOBAL)

        out = StringIO()
        call_command(
            "audit_service_event_fallback_retirement_readiness",
            "--verbose",
            "--limit",
            "2",
            stdout=out,
        )

        output = out.getvalue()
        self.assertIn("more (raise --limit to see)", output)

    def test_event_id_scopes_audit_to_single_event(self):
        self.make_root()
        target = self.make_event(scope_type=ServiceEvent.SCOPE_GLOBAL)
        self.make_event(scope_type=ServiceEvent.SCOPE_GLOBAL)

        stats = self.audit(event_id=target.id)

        self.assertEqual(stats["events_checked"], 1)
