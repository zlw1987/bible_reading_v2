"""Focused GENERIC-DEPLOYMENT-CONFIG.7A read-only preview tests."""

from datetime import date, datetime, time
from io import StringIO

from django.core.management import CommandError, call_command
from django.test import TestCase
from django.utils import timezone

from events.models import ServiceEvent, ServiceEventRequiredTeam, ServiceProfile

from .models import (
    MinistryTeam,
    MinistryTeamParentLink,
    ServiceProfileMinistryRequirement,
)
from .service_profile_required_team_materialization import (
    MaterializationInputError,
    RequiredTeamClassification,
    inspect_service_profile_required_team_materialization,
)


class RequiredTeamMaterializationPreviewTests(TestCase):
    def setUp(self):
        self.profile = ServiceProfile.objects.create(
            key="profile.primary", name="Primary", name_en="Primary",
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
        )
        self.other_profile = ServiceProfile.objects.create(
            key="profile.other", name="Other", name_en="Other",
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
        )
        self.static = self.team("static.one")

    def team(self, key, **overrides):
        values = {"name": key, "name_en": key, "team_key": key,
                  "is_active": True, "is_assignable": True}
        values.update(overrides)
        return MinistryTeam.objects.create(**values)

    def event(self, day, *, profile=None, status=ServiceEvent.STATUS_PUBLISHED, key=None):
        profile = self.profile if profile is None else profile
        return ServiceEvent.objects.create(
            title="Neutral event", event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
            service_profile=profile, service_profile_key=key or profile.key,
            start_datetime=timezone.make_aware(datetime.combine(day, time(9))),
            status=status,
        )

    def requirement(self, team=None, active=True):
        return ServiceProfileMinistryRequirement.objects.create(
            service_profile=self.profile, ministry_team=team or self.static,
            is_active=active,
        )

    def preview(self):
        return inspect_service_profile_required_team_materialization(
            profile_key=self.profile.key, start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31),
        )

    def test_exact_fk_and_local_date_scope_with_no_legacy_fallback(self):
        included = self.event(date(2026, 1, 2))
        self.event(date(2026, 1, 3), profile=self.other_profile)
        legacy = ServiceEvent.objects.create(
            title="Legacy", event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
            service_profile_key=self.profile.key,
            start_datetime=timezone.make_aware(datetime(2026, 1, 4, 9)),
        )
        self.event(date(2026, 2, 1))
        result = self.preview()
        self.assertEqual([item["event_pk"] for item in result["events"]], [included.pk])
        self.assertNotIn(legacy.pk, [item["event_pk"] for item in result["events"]])

    def test_zero_defaults_is_valid_no_op_and_anchor_alone_is_not_row(self):
        event = self.event(date(2026, 1, 2))
        event.rotation_anchor_team = self.static
        event.save()
        result = self.preview()
        self.assertEqual(result["summary"]["missing_default_pairs"], 0)
        self.assertEqual(result["events"][0]["required_team_rows"], [])

    def test_missing_and_already_default_and_deterministic_missing_pairs(self):
        second = self.team("static.two")
        self.requirement()
        self.requirement(second)
        first_event = self.event(date(2026, 1, 3))
        second_event = self.event(date(2026, 1, 2))
        ServiceEventRequiredTeam.objects.create(service_event=first_event, ministry_team=self.static)
        result = self.preview()
        self.assertEqual([event["event_pk"] for event in result["events"]], [second_event.pk, first_event.pk])
        self.assertEqual(result["events"][0]["missing_default_teams"], [[self.static.pk, self.static.team_key], [second.pk, second.team_key]])
        self.assertEqual(result["events"][1]["missing_default_teams"], [[second.pk, second.team_key]])
        self.assertEqual(result["events"][1]["required_team_rows"][0]["classifications"], [RequiredTeamClassification.ALREADY_DEFAULT])

    def test_manual_extra_worship_and_invalid_rows_are_explicit_review_evidence(self):
        event = self.event(date(2026, 1, 2))
        extra = self.team("extra")
        pool = self.team("pool", is_assignable=False, is_worship_rotation_pool=True)
        child = self.team("child")
        MinistryTeamParentLink.objects.create(child_team=child, parent_team=pool, is_active=True, is_primary=True)
        event.rotation_anchor_team = child
        event.save()
        invalid = self.team("invalid")
        MinistryTeam.objects.filter(pk=invalid.pk).update(is_active=False)
        invalid.refresh_from_db()
        for team in (extra, pool, child, invalid):
            ServiceEventRequiredTeam.objects.create(service_event=event, ministry_team=team)
        rows = {row["team_pk"]: row for row in self.preview()["events"][0]["required_team_rows"]}
        self.assertEqual(rows[extra.pk]["classifications"], [RequiredTeamClassification.MANUAL_EXTRA])
        self.assertIn(RequiredTeamClassification.EXPLICIT_WORSHIP, rows[pool.pk]["classifications"])
        self.assertIn(RequiredTeamClassification.EXPLICIT_WORSHIP, rows[child.pk]["classifications"])
        self.assertIn(RequiredTeamClassification.INVALID_EXPLICIT, rows[invalid.pk]["classifications"])

    def test_inactive_history_never_materializes_and_lifecycle_remains_visible(self):
        history = self.requirement(active=False)
        completed = self.event(date(2026, 1, 2), status=ServiceEvent.STATUS_COMPLETED)
        draft = self.event(date(2026, 1, 3), status=ServiceEvent.STATUS_DRAFT)
        cancelled = self.event(date(2026, 1, 4), status=ServiceEvent.STATUS_CANCELLED)
        ServiceEventRequiredTeam.objects.create(service_event=completed, ministry_team=self.static)
        result = self.preview()
        self.assertEqual(result["summary"]["missing_default_pairs"], 0)
        self.assertEqual([item["lifecycle_status"] for item in result["events"]], ["completed", "draft", "cancelled"])
        self.assertEqual(
            result["events"][0]["required_team_rows"][0]["classifications"],
            [RequiredTeamClassification.INACTIVE_DEFAULT_HISTORY],
        )
        self.assertEqual(result["inactive_requirement_history"][0]["requirement_pk"], history.pk)
        self.assertEqual(result["summary"]["inactive_default_history_rows"], 1)
        self.assertEqual(result["summary"]["manual_extra_rows"], 0)

    def test_identity_drift_and_invalid_active_requirement_block(self):
        event = self.event(date(2026, 1, 2))
        ServiceEvent.objects.filter(pk=event.pk).update(service_profile_key="wrong.key")
        self.requirement()
        MinistryTeam.objects.filter(pk=self.static.pk).update(is_active=False)
        result = self.preview()
        self.assertGreater(result["summary"]["blockers"], 0)
        self.assertEqual(result["events"][0]["identity_state"], "fk_key_mismatch")

    def test_non_assignable_explicit_row_is_invalid_evidence(self):
        event = self.event(date(2026, 1, 2))
        team = self.team("non.assignable", is_assignable=False)
        ServiceEventRequiredTeam.objects.create(service_event=event, ministry_team=team)
        row = self.preview()["events"][0]["required_team_rows"][0]
        self.assertIn(RequiredTeamClassification.INVALID_EXPLICIT, row["classifications"])

    def test_fingerprint_binds_revision_rows_defaults_and_team_validity(self):
        event = self.event(date(2026, 1, 2))
        self.requirement()
        first = self.preview()["state_fingerprint"]
        ServiceEvent.objects.filter(pk=event.pk).update(scheduling_revision=7)
        second = self.preview()["state_fingerprint"]
        ServiceEventRequiredTeam.objects.create(service_event=event, ministry_team=self.static)
        third = self.preview()["state_fingerprint"]
        ServiceProfileMinistryRequirement.objects.filter(service_profile=self.profile).update(sort_order=8)
        fourth = self.preview()["state_fingerprint"]
        MinistryTeam.objects.filter(pk=self.static.pk).update(is_assignable=False)
        fifth = self.preview()["state_fingerprint"]
        self.assertEqual(len({first, second, third, fourth, fifth}), 5)

    def test_command_is_zero_write_and_deterministic(self):
        event = self.event(date(2026, 1, 2))
        self.requirement()
        before = (ServiceEventRequiredTeam.objects.count(), event.updated_at, event.scheduling_revision)
        output_one, output_two = StringIO(), StringIO()
        args = ("audit_service_profile_required_team_materialization", "--profile-key", self.profile.key, "--start-date", "2026-01-01", "--end-date", "2026-01-31")
        call_command(*args, stdout=output_one)
        call_command(*args, stdout=output_two)
        event.refresh_from_db()
        self.assertEqual(output_one.getvalue(), output_two.getvalue())
        self.assertEqual((ServiceEventRequiredTeam.objects.count(), event.updated_at, event.scheduling_revision), before)
        with self.assertRaises(CommandError):
            call_command(*args[:-1], "2025-01-01")
        with self.assertRaises(CommandError):
            call_command(*args[:-1], "not-a-date")

    def test_reversed_dates_fail_cleanly(self):
        with self.assertRaises(MaterializationInputError):
            inspect_service_profile_required_team_materialization(
                profile_key=self.profile.key, start_date=date(2026, 2, 1), end_date=date(2026, 1, 1)
            )

    def test_command_rejects_nonexistent_exact_profile_key(self):
        with self.assertRaises(CommandError):
            call_command(
                "audit_service_profile_required_team_materialization",
                "--profile-key", "profile.absent",
                "--start-date", "2026-01-01",
                "--end-date", "2026-01-31",
            )
