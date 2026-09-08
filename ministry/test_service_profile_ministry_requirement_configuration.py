"""Focused GENERIC-DEPLOYMENT-CONFIG.6B reviewed configuration tests."""

import re
from io import StringIO
from unittest.mock import patch

from django.core.management import CommandError, call_command
from django.test import TestCase
from django.utils import timezone

from events.models import ServiceEvent, ServiceEventRequiredTeam, ServiceProfile
from notifications.models import Notification

from .models import (
    MinistryTeam,
    MinistryTeamParentLink,
    ServiceProfileMinistryRequirement,
    TeamAssignment,
)
from .service_profile_ministry_requirement_configuration import (
    RequirementConfigurationStale,
    apply_requirement_configuration,
    build_requirement_configuration_plan,
    parse_team_values,
)
from .service_profile_ministry_requirements import (
    inspect_service_profile_ministry_requirements,
)


class RequirementConfigurationFixtureMixin:
    def setUp(self):
        super().setUp()
        self.profile = ServiceProfile.objects.create(
            key="generic.sunday",
            name="Generic Sunday",
            name_en="Generic Sunday",
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
        )
        self.team = self.create_team("static.alpha")

    def create_team(self, key, **overrides):
        values = {
            "name": f"Team {key}",
            "name_en": f"Team {key}",
            "team_key": key,
            "is_active": True,
            "is_assignable": True,
        }
        values.update(overrides)
        return MinistryTeam.objects.create(**values)

    def identities(self, *teams):
        teams = teams or (self.team,)
        return tuple((team.pk, team.team_key) for team in teams)

    def token(self, *teams):
        return build_requirement_configuration_plan(
            self.profile.key,
            self.identities(*teams),
        )["confirmation_token"]

    def preview_output(self, *teams):
        teams = teams or (self.team,)
        args = ["--profile-key", self.profile.key]
        for team in teams:
            args.extend(["--team", f"{team.pk}={team.team_key}"])
        output = StringIO()
        call_command(
            "configure_service_profile_ministry_requirements",
            *args,
            stdout=output,
        )
        return output.getvalue()

    def create_worship_pool_and_child(self):
        pool = self.create_team(
            "rotation.pool",
            is_assignable=False,
            is_worship_rotation_pool=True,
        )
        child = self.create_team("rotation.child")
        MinistryTeamParentLink.objects.create(
            child_team=child,
            parent_team=pool,
            is_primary=True,
            is_active=True,
        )
        return pool, child


class RequirementConfigurationPreviewTests(
    RequirementConfigurationFixtureMixin,
    TestCase,
):
    def test_dry_run_writes_zero_rows(self):
        profile_updated = self.profile.updated_at
        team_updated = self.team.updated_at
        before = {
            "profiles": ServiceProfile.objects.count(),
            "teams": MinistryTeam.objects.count(),
            "requirements": ServiceProfileMinistryRequirement.objects.count(),
            "events": ServiceEvent.objects.count(),
            "required": ServiceEventRequiredTeam.objects.count(),
            "assignments": TeamAssignment.objects.count(),
            "notifications": Notification.objects.count(),
        }

        output = self.preview_output()

        self.profile.refresh_from_db()
        self.team.refresh_from_db()
        self.assertEqual(profile_updated, self.profile.updated_at)
        self.assertEqual(team_updated, self.team.updated_at)
        self.assertEqual(
            before,
            {
                "profiles": ServiceProfile.objects.count(),
                "teams": MinistryTeam.objects.count(),
                "requirements": ServiceProfileMinistryRequirement.objects.count(),
                "events": ServiceEvent.objects.count(),
                "required": ServiceEventRequiredTeam.objects.count(),
                "assignments": TeamAssignment.objects.count(),
                "notifications": Notification.objects.count(),
            },
        )
        self.assertIn("mode: DRY RUN", output)
        self.assertIn("create_new: 1", output)
        self.assertIn("no ServiceEventRequiredTeam", output)

    def test_missing_and_inactive_profile_fail_closed(self):
        missing = build_requirement_configuration_plan(
            "generic.missing", self.identities()
        )
        self.assertFalse(missing["ready"])
        self.assertIn("PROFILE_NOT_FOUND", missing["blockers"][0])
        self.assertEqual(missing["classification_counts"]["invalid_target"], 1)
        self.assertEqual(missing["classification_counts"]["create_new"], 0)
        self.assertIsNone(missing["confirmation_token"])

        ServiceProfile.objects.filter(pk=self.profile.pk).update(is_active=False)
        inactive = build_requirement_configuration_plan(
            self.profile.key, self.identities()
        )
        self.assertFalse(inactive["ready"])
        self.assertTrue(
            any("PROFILE_INACTIVE" in item for item in inactive["blockers"])
        )
        self.assertIsNone(inactive["confirmation_token"])

    def test_missing_team_and_pk_key_mismatch_fail_closed(self):
        missing = build_requirement_configuration_plan(
            self.profile.key, ((999999, "missing.team"),)
        )
        self.assertFalse(missing["ready"])
        self.assertEqual(missing["classification_counts"]["invalid_target"], 1)
        self.assertIn("TEAM_NOT_FOUND", missing["blockers"][0])

        other = self.create_team("static.other")
        mismatch = build_requirement_configuration_plan(
            self.profile.key, ((self.team.pk, other.team_key),)
        )
        self.assertFalse(mismatch["ready"])
        self.assertEqual(
            mismatch["classification_counts"]["stale_conflicting"], 1
        )
        self.assertTrue(
            any("TEAM_PK_KEY_MISMATCH" in item for item in mismatch["blockers"])
        )

    def test_null_unconfigured_team_key_fails_closed(self):
        MinistryTeam.objects.filter(pk=self.team.pk).update(team_key=None)
        plan = build_requirement_configuration_plan(
            self.profile.key, ((self.team.pk, "static.alpha"),)
        )
        self.assertFalse(plan["ready"])
        self.assertTrue(
            any("TEAM_KEY_UNCONFIGURED" in item for item in plan["blockers"])
        )

    def test_each_6a_invalid_team_state_fails_closed(self):
        scenarios = (
            ({"is_active": False}, "team_inactive"),
            ({"is_assignable": False}, "team_non_assignable"),
            (
                {"is_assignable": False, "is_worship_rotation_pool": True},
                "team_worship_rotation_pool",
            ),
        )
        for mutation, reason in scenarios:
            with self.subTest(reason=reason):
                MinistryTeam.objects.filter(pk=self.team.pk).update(
                    is_active=True,
                    is_assignable=True,
                    is_worship_rotation_pool=False,
                )
                MinistryTeam.objects.filter(pk=self.team.pk).update(**mutation)
                plan = build_requirement_configuration_plan(
                    self.profile.key, self.identities()
                )
                self.assertFalse(plan["ready"])
                self.assertTrue(any(reason in item for item in plan["blockers"]), plan)

    def test_canonical_worship_child_fails_closed(self):
        _pool, child = self.create_worship_pool_and_child()
        plan = build_requirement_configuration_plan(
            self.profile.key, self.identities(child)
        )
        self.assertFalse(plan["ready"])
        self.assertTrue(plan["desired_teams"][0]["is_canonical_worship_child"])
        self.assertTrue(
            any("team_under_worship_rotation_pool" in item for item in plan["blockers"])
        )

    def test_unrelated_eligible_static_team_succeeds_in_preview(self):
        output = self.preview_output()
        self.assertIn(f"pk={self.team.pk}", output)
        self.assertIn('team_key="static.alpha"', output)
        self.assertIn("readiness: READY TO APPLY", output)
        self.assertRegex(output, r"confirmation_token: [0-9a-f]{64}")

    def test_complete_desired_set_classifications(self):
        active = self.team
        reactivate = self.create_team("static.reactivate")
        create = self.create_team("static.create")
        deactivate = self.create_team("static.deactivate")
        ServiceProfileMinistryRequirement.objects.create(
            service_profile=self.profile,
            ministry_team=active,
            is_active=True,
            sort_order=3,
        )
        ServiceProfileMinistryRequirement.objects.create(
            service_profile=self.profile,
            ministry_team=reactivate,
            is_active=False,
            sort_order=4,
        )
        ServiceProfileMinistryRequirement.objects.create(
            service_profile=self.profile,
            ministry_team=deactivate,
            is_active=True,
            sort_order=5,
        )

        plan = build_requirement_configuration_plan(
            self.profile.key,
            self.identities(active, reactivate, create),
        )

        self.assertTrue(plan["ready"])
        for classification in (
            "already_active",
            "create_new",
            "reactivate_existing",
            "deactivate_existing",
        ):
            self.assertEqual(plan["classification_counts"][classification], 1)
        self.assertEqual(plan["classification_counts"]["invalid_target"], 0)
        self.assertEqual(plan["classification_counts"]["stale_conflicting"], 0)

    def test_state_token_binds_complete_current_profile_requirement_surface(self):
        history = ServiceProfileMinistryRequirement.objects.create(
            service_profile=self.profile,
            ministry_team=self.create_team("static.history"),
            is_active=False,
            sort_order=7,
        )
        initial = build_requirement_configuration_plan(
            self.profile.key, self.identities()
        )["state_fingerprint"]

        ServiceProfileMinistryRequirement.objects.filter(pk=history.pk).update(
            sort_order=8
        )
        changed = build_requirement_configuration_plan(
            self.profile.key, self.identities()
        )["state_fingerprint"]

        self.assertNotEqual(initial, changed)

    def test_exact_input_parser_rejects_normalization_and_supports_reviewed_empty_set(self):
        self.assertEqual(
            parse_team_values([f"{self.team.pk}=static.alpha"]),
            ((self.team.pk, "static.alpha"),),
        )
        with self.assertRaisesRegex(Exception, "exact canonical"):
            parse_team_values([f"{self.team.pk}= Static.Alpha "])
        self.assertEqual(parse_team_values([], no_teams=True), ())


class RequirementConfigurationApplyTests(
    RequirementConfigurationFixtureMixin,
    TestCase,
):
    def assert_stale_after(self, mutate):
        token = self.token()
        mutate()
        with self.assertRaises(RequirementConfigurationStale):
            apply_requirement_configuration(
                self.profile.key,
                self.identities(),
                token,
            )
        self.assertEqual(ServiceProfileMinistryRequirement.objects.count(), 0)

    def test_profile_state_change_after_preview_is_stale(self):
        self.assert_stale_after(
            lambda: ServiceProfile.objects.filter(pk=self.profile.pk).update(
                is_active=False
            )
        )

    def test_team_state_change_after_preview_is_stale(self):
        self.assert_stale_after(
            lambda: MinistryTeam.objects.filter(pk=self.team.pk).update(
                is_assignable=False
            )
        )

    def test_team_key_raw_bypass_after_preview_is_stale(self):
        self.assert_stale_after(
            lambda: MinistryTeam.objects.filter(pk=self.team.pk).update(
                team_key="static.changed"
            )
        )

    def test_requirement_state_change_after_preview_is_stale(self):
        existing = ServiceProfileMinistryRequirement.objects.create(
            service_profile=self.profile,
            ministry_team=self.team,
            is_active=False,
            sort_order=2,
        )
        identities = self.identities()
        token = build_requirement_configuration_plan(
            self.profile.key, identities
        )["confirmation_token"]
        ServiceProfileMinistryRequirement.objects.filter(pk=existing.pk).update(
            sort_order=9
        )
        with self.assertRaises(RequirementConfigurationStale):
            apply_requirement_configuration(self.profile.key, identities, token)
        existing.refresh_from_db()
        self.assertFalse(existing.is_active)
        self.assertEqual(existing.sort_order, 9)

    def test_successful_apply_creates_reactivates_deactivates_without_deleting(self):
        reactivate = self.create_team("static.reactivate")
        deactivate = self.create_team("static.deactivate")
        inactive = ServiceProfileMinistryRequirement.objects.create(
            service_profile=self.profile,
            ministry_team=reactivate,
            is_active=False,
            sort_order=11,
        )
        retired = ServiceProfileMinistryRequirement.objects.create(
            service_profile=self.profile,
            ministry_team=deactivate,
            is_active=True,
            sort_order=12,
        )
        identities = self.identities(self.team, reactivate)
        plan = build_requirement_configuration_plan(self.profile.key, identities)

        result = apply_requirement_configuration(
            self.profile.key,
            identities,
            plan["confirmation_token"],
        )

        self.assertEqual(
            result,
            {"created": 1, "reactivated": 1, "deactivated": 1, "rows_mutated": 3},
        )
        inactive.refresh_from_db()
        retired.refresh_from_db()
        self.assertTrue(inactive.is_active)
        self.assertEqual(inactive.sort_order, 11)
        self.assertFalse(retired.is_active)
        self.assertEqual(retired.sort_order, 12)
        self.assertTrue(
            ServiceProfileMinistryRequirement.objects.filter(pk=retired.pk).exists()
        )
        created = ServiceProfileMinistryRequirement.objects.get(
            service_profile=self.profile,
            ministry_team=self.team,
        )
        self.assertTrue(created.is_active)
        self.assertEqual(created.sort_order, 0)

    def test_complete_desired_set_does_not_touch_another_profile(self):
        other_profile = ServiceProfile.objects.create(
            key="generic.other",
            name="Other",
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
        )
        other_team = self.create_team("static.other")
        other_row = ServiceProfileMinistryRequirement.objects.create(
            service_profile=other_profile,
            ministry_team=other_team,
            is_active=True,
            sort_order=41,
        )
        before = other_row.updated_at

        apply_requirement_configuration(
            self.profile.key,
            self.identities(),
            self.token(),
        )

        other_row.refresh_from_db()
        self.assertTrue(other_row.is_active)
        self.assertEqual(other_row.sort_order, 41)
        self.assertEqual(other_row.updated_at, before)

    def test_write_failure_rolls_back_all_requirement_changes(self):
        obsolete = self.create_team("static.obsolete")
        old = ServiceProfileMinistryRequirement.objects.create(
            service_profile=self.profile,
            ministry_team=obsolete,
            is_active=True,
        )
        identities = self.identities()
        token = build_requirement_configuration_plan(
            self.profile.key, identities
        )["confirmation_token"]

        with patch(
            "ministry.service_profile_ministry_requirement_configuration."
            "_cas_requirement_state",
            return_value=0,
        ):
            with self.assertRaises(RequirementConfigurationStale):
                apply_requirement_configuration(
                    self.profile.key,
                    identities,
                    token,
                )

        old.refresh_from_db()
        self.assertTrue(old.is_active)
        self.assertFalse(
            ServiceProfileMinistryRequirement.objects.filter(
                service_profile=self.profile,
                ministry_team=self.team,
            ).exists()
        )

    def test_successful_apply_then_fresh_preview_is_noop_without_apply_token(self):
        identities = self.identities()
        old_token = self.token()
        apply_requirement_configuration(self.profile.key, identities, old_token)

        fresh = build_requirement_configuration_plan(self.profile.key, identities)

        self.assertTrue(fresh["ready"])
        self.assertFalse(fresh["has_changes"])
        self.assertEqual(fresh["classification_counts"]["already_active"], 1)
        self.assertIsNone(fresh["confirmation_token"])
        row = ServiceProfileMinistryRequirement.objects.get()
        before = row.updated_at
        output = self.preview_output()
        row.refresh_from_db()
        self.assertEqual(row.updated_at, before)
        self.assertIn("readiness: READY / NO CHANGES", output)
        self.assertNotIn("confirmation_token:", output)

    def test_no_teams_command_deactivates_all_without_deleting(self):
        second_team = self.create_team("static.second")
        requirements = (
            ServiceProfileMinistryRequirement.objects.create(
                service_profile=self.profile,
                ministry_team=self.team,
                is_active=True,
                sort_order=17,
            ),
            ServiceProfileMinistryRequirement.objects.create(
                service_profile=self.profile,
                ministry_team=second_team,
                is_active=True,
                sort_order=29,
            ),
        )
        requirement_ids = {requirement.pk for requirement in requirements}
        original_timestamps = {
            requirement.pk: requirement.updated_at for requirement in requirements
        }
        boundary_counts = {
            "events": ServiceEvent.objects.count(),
            "required": ServiceEventRequiredTeam.objects.count(),
            "assignments": TeamAssignment.objects.count(),
            "notifications": Notification.objects.count(),
        }

        preview_output = StringIO()
        call_command(
            "configure_service_profile_ministry_requirements",
            "--profile-key",
            self.profile.key,
            "--no-teams",
            stdout=preview_output,
        )
        preview = preview_output.getvalue()

        self.assertEqual(preview.count("deactivate_existing: requirement_pk="), 2)
        self.assertIn("  deactivate_existing: 2", preview)
        token_match = re.search(
            r"^confirmation_token: ([0-9a-f]{64})$",
            preview,
            flags=re.MULTILINE,
        )
        self.assertIsNotNone(token_match)
        token = token_match.group(1)
        previewed_rows = list(
            ServiceProfileMinistryRequirement.objects.filter(
                service_profile=self.profile
            ).order_by("pk")
        )
        self.assertEqual({row.pk for row in previewed_rows}, requirement_ids)
        self.assertTrue(all(row.is_active for row in previewed_rows))
        self.assertEqual(
            {row.pk: row.sort_order for row in previewed_rows},
            {requirements[0].pk: 17, requirements[1].pk: 29},
        )
        self.assertEqual(
            {row.pk: row.updated_at for row in previewed_rows},
            original_timestamps,
        )

        apply_output = StringIO()
        call_command(
            "configure_service_profile_ministry_requirements",
            "--profile-key",
            self.profile.key,
            "--no-teams",
            "--apply",
            "--confirmation-token",
            token,
            stdout=apply_output,
        )

        self.assertIn("APPLY COMPLETE", apply_output.getvalue())
        applied_rows = list(
            ServiceProfileMinistryRequirement.objects.filter(
                service_profile=self.profile
            ).order_by("pk")
        )
        self.assertEqual({row.pk for row in applied_rows}, requirement_ids)
        self.assertTrue(all(not row.is_active for row in applied_rows))
        self.assertEqual(
            {row.pk: row.sort_order for row in applied_rows},
            {requirements[0].pk: 17, requirements[1].pk: 29},
        )
        post_apply_state = {
            row.pk: (row.is_active, row.sort_order, row.updated_at)
            for row in applied_rows
        }

        fresh_output = StringIO()
        call_command(
            "configure_service_profile_ministry_requirements",
            "--profile-key",
            self.profile.key,
            "--no-teams",
            stdout=fresh_output,
        )
        fresh = fresh_output.getvalue()
        self.assertIn("readiness: READY / NO CHANGES", fresh)
        self.assertNotIn("confirmation_token:", fresh)
        fresh_rows = list(
            ServiceProfileMinistryRequirement.objects.filter(
                service_profile=self.profile
            ).order_by("pk")
        )
        self.assertEqual(
            {
                row.pk: (row.is_active, row.sort_order, row.updated_at)
                for row in fresh_rows
            },
            post_apply_state,
        )
        self.assertEqual(
            boundary_counts,
            {
                "events": ServiceEvent.objects.count(),
                "required": ServiceEventRequiredTeam.objects.count(),
                "assignments": TeamAssignment.objects.count(),
                "notifications": Notification.objects.count(),
            },
        )

    def test_old_token_cannot_replay_state_changing_apply(self):
        identities = self.identities()
        old_token = self.token()
        apply_requirement_configuration(self.profile.key, identities, old_token)

        with self.assertRaises(RequirementConfigurationStale):
            apply_requirement_configuration(
                self.profile.key,
                identities,
                old_token,
            )
        self.assertEqual(ServiceProfileMinistryRequirement.objects.count(), 1)

    def test_dry_run_and_apply_materialize_nothing_and_change_no_event_state(self):
        event = ServiceEvent.objects.create(
            title="Existing service",
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
            service_profile=self.profile,
            service_profile_key=self.profile.key,
            start_datetime=timezone.now() + timezone.timedelta(days=7),
            status=ServiceEvent.STATUS_PUBLISHED,
        )
        event.refresh_from_db()
        before = {
            "events": ServiceEvent.objects.count(),
            "required": ServiceEventRequiredTeam.objects.count(),
            "assignments": TeamAssignment.objects.count(),
            "notifications": Notification.objects.count(),
            "revision": event.scheduling_revision,
            "anchor": event.rotation_anchor_team_id,
            "event_updated_at": event.updated_at,
        }

        self.preview_output()
        apply_requirement_configuration(
            self.profile.key,
            self.identities(),
            self.token(),
        )

        event.refresh_from_db()
        self.assertEqual(ServiceEvent.objects.count(), before["events"])
        self.assertEqual(ServiceEventRequiredTeam.objects.count(), before["required"])
        self.assertEqual(TeamAssignment.objects.count(), before["assignments"])
        self.assertEqual(Notification.objects.count(), before["notifications"])
        self.assertEqual(event.scheduling_revision, before["revision"])
        self.assertEqual(event.rotation_anchor_team_id, before["anchor"])
        self.assertEqual(event.updated_at, before["event_updated_at"])

    def test_resulting_configuration_passes_6a_audit(self):
        apply_requirement_configuration(
            self.profile.key,
            self.identities(),
            self.token(),
        )
        inspection = inspect_service_profile_ministry_requirements(
            profile_key=self.profile.key
        )
        self.assertEqual(inspection.valid_active_requirements, 1)
        self.assertEqual(inspection.integrity_blockers, 0)
        output = StringIO()
        call_command(
            "audit_service_profile_ministry_requirements",
            "--profile-key",
            self.profile.key,
            "--fail-on-blockers",
            stdout=output,
        )
        self.assertIn("READY / ACTIVE PROFILE MINISTRY DEFAULTS VALID", output.getvalue())

    def test_command_requires_token_for_apply(self):
        with self.assertRaisesRegex(CommandError, "requires --confirmation-token"):
            call_command(
                "configure_service_profile_ministry_requirements",
                "--profile-key",
                self.profile.key,
                "--team",
                f"{self.team.pk}={self.team.team_key}",
                "--apply",
                stdout=StringIO(),
            )
