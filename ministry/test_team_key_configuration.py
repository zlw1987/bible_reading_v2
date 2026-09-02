from io import StringIO
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.management import CommandError, call_command
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from accounts.models import ChurchStructureUnit
from events.models import ServiceEvent
from ministry import team_key_configuration
from ministry.models import (
    MinistryTeam,
    MinistryTeamParentLink,
    MinistryTeamRoleAssignment,
    MinistryTeamRoleType,
    TeamAssignment,
    TeamMembership,
)
from ministry.team_key_configuration import (
    TeamKeyConfigurationNotReady,
    TeamKeyConfigurationStale,
    TeamKeyMappingError,
    apply_team_key_configuration,
    build_team_key_configuration_plan,
    parse_mapping_values,
)


class MinistryTeamKeyMappingParserTests(SimpleTestCase):
    def test_one_valid_mapping(self):
        self.assertEqual(parse_mapping_values(["12=main.audio"]), ((12, "main.audio"),))

    def test_multiple_mappings_are_canonical_pk_order(self):
        self.assertEqual(
            parse_mapping_values(["18=sunday.production", "12=main.audio"]),
            ((12, "main.audio"), (18, "sunday.production")),
        )

    def test_uppercase_and_whitespace_normalize(self):
        self.assertEqual(parse_mapping_values(["12= Main.Audio "]), ((12, "main.audio"),))

    def test_invalid_mapping_shapes_are_rejected(self):
        cases = (
            (["12main.audio"], "expected"),
            (["=main.audio"], "TEAM_PK is empty"),
            (["abc=main.audio"], "must be an integer"),
            (["0=main.audio"], "greater than zero"),
            (["-1=main.audio"], "greater than zero"),
            (["12=   "], "empty after normalization"),
            (["12=main/audio"], "lowercase letters"),
            ([f"12={'a' * 65}"], "exceeds 64"),
        )
        for values, message in cases:
            with self.subTest(values=values):
                with self.assertRaisesRegex(TeamKeyMappingError, message):
                    parse_mapping_values(values)

    def test_duplicate_pk_is_rejected(self):
        with self.assertRaisesRegex(TeamKeyMappingError, "Duplicate TEAM_PK"):
            parse_mapping_values(["12=main.alpha", "12=main.beta"])

    def test_duplicate_normalized_key_is_rejected(self):
        with self.assertRaisesRegex(TeamKeyMappingError, "Duplicate normalized"):
            parse_mapping_values(["12=Main.Audio", "18= main.audio "])


class MinistryTeamKeyConfigurationPlanTests(TestCase):
    def setUp(self):
        self.root = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_ROOT,
            code="ROOT",
            name="本地教会",
            name_en="Local Church",
        )
        self.target = MinistryTeam.objects.create(
            name="音频团队",
            name_en="Audio Team",
            is_active=True,
            is_assignable=True,
        )
        self.other = MinistryTeam.objects.create(
            name="儿童团队",
            name_en="Children Team",
            is_active=False,
            is_assignable=False,
        )
        self.parent_link = MinistryTeamParentLink.objects.create(
            child_team=self.target,
            parent_church_unit=self.root,
            is_primary=True,
        )

    def mappings(self, *values):
        return parse_mapping_values(values or (f"{self.target.pk}=local.audio",))

    def command_output(self, values):
        output = StringIO()
        call_command("configure_ministry_team_keys", mapping=values, stdout=output)
        return output.getvalue()

    def test_dry_run_is_zero_write_and_contains_review_evidence(self):
        before_updated_at = self.target.updated_at
        output = self.command_output([f"{self.target.pk}= Local.Audio "])

        self.target.refresh_from_db()
        self.assertIsNone(self.target.team_key)
        self.assertEqual(self.target.updated_at, before_updated_at)
        self.assertIn("mode: DRY RUN", output)
        self.assertIn(f"pk={self.target.pk}", output)
        self.assertIn("current_team_key: UNCONFIGURED", output)
        self.assertIn("proposed_team_key: local.audio", output)
        self.assertIn('name: "音频团队"', output)
        self.assertIn('name_en: "Audio Team"', output)
        self.assertIn("active: true", output)
        self.assertIn("assignable: true", output)
        self.assertIn("worship_rotation_pool: false", output)
        self.assertIn("本地教会 > 音频团队", output)
        self.assertIn("readiness: READY TO APPLY", output)
        self.assertRegex(output, r"confirmation_token: [0-9a-f]{64}")

    def test_all_null_deployment_and_unrelated_null_team_are_ready(self):
        plan = build_team_key_configuration_plan(self.mappings())

        self.assertTrue(plan["ready"])
        self.assertEqual(plan["summary"]["currently_unconfigured"], 1)
        self.assertEqual(plan["summary"]["integrity_problems"], 0)

    def test_inactive_nonassignable_worship_container_is_eligible_identity_target(self):
        MinistryTeam.objects.filter(pk=self.other.pk).update(
            is_active=False,
            is_assignable=False,
            is_worship_rotation_pool=True,
            team_kind=MinistryTeam.KIND_DEPARTMENT,
        )
        plan = build_team_key_configuration_plan(
            self.mappings(f"{self.other.pk}=local.worship.container")
        )

        self.assertTrue(plan["ready"])
        self.assertFalse(plan["rows"][0]["is_active"])
        self.assertFalse(plan["rows"][0]["is_assignable"])
        self.assertTrue(plan["rows"][0]["is_worship_rotation_pool"])

    def test_cli_order_does_not_change_output_plan_order_or_token(self):
        mappings_a = self.mappings(
            f"{self.other.pk}=local.children",
            f"{self.target.pk}=local.audio",
        )
        mappings_b = self.mappings(
            f"{self.target.pk}=local.audio",
            f"{self.other.pk}=local.children",
        )
        plan_a = build_team_key_configuration_plan(mappings_a)
        plan_b = build_team_key_configuration_plan(mappings_b)

        self.assertEqual(plan_a["rows"], plan_b["rows"])
        self.assertEqual(plan_a["confirmation_token"], plan_b["confirmation_token"])
        self.assertEqual([row["pk"] for row in plan_a["rows"]], sorted([self.target.pk, self.other.pk]))

    def test_output_and_token_are_deterministic(self):
        first = self.command_output([f"{self.target.pk}=local.audio"])
        second = self.command_output([f"{self.target.pk}=local.audio"])

        self.assertEqual(first, second)

    def test_changed_proposed_key_changes_token(self):
        first = build_team_key_configuration_plan(self.mappings(f"{self.target.pk}=local.audio"))
        second = build_team_key_configuration_plan(self.mappings(f"{self.target.pk}=local.gamma"))
        self.assertNotEqual(first["confirmation_token"], second["confirmation_token"])

    def test_changed_reviewed_metadata_changes_token(self):
        baseline = build_team_key_configuration_plan(self.mappings())["confirmation_token"]
        changes = (
            {"name": "重命名团队"},
            {"is_active": False},
            {"is_assignable": False},
            {"is_assignable": False, "is_worship_rotation_pool": True},
        )
        for change in changes:
            with self.subTest(change=change):
                MinistryTeam.objects.filter(pk=self.target.pk).update(
                    name="音频团队",
                    is_active=True,
                    is_assignable=True,
                    is_worship_rotation_pool=False,
                )
                MinistryTeam.objects.filter(pk=self.target.pk).update(**change)
                changed = build_team_key_configuration_plan(self.mappings())
                self.assertNotEqual(baseline, changed["confirmation_token"])

    def test_changed_primary_path_evidence_changes_token(self):
        baseline = build_team_key_configuration_plan(self.mappings())["confirmation_token"]
        ChurchStructureUnit.objects.filter(pk=self.root.pk).update(name="另一个本地教会")
        changed = build_team_key_configuration_plan(self.mappings())

        self.assertNotEqual(baseline, changed["confirmation_token"])

    def test_missing_exact_target_blocks_without_apply_recommendation(self):
        output = self.command_output(["999999=local.missing"])

        self.assertIn("TEAM_NOT_FOUND", output)
        self.assertIn("readiness: NOT READY", output)
        self.assertNotIn("confirmation_token:", output)
        self.assertIn("No actionable apply recommendation", output)

    def test_already_configured_target_blocks_even_if_same_key(self):
        MinistryTeam.objects.filter(pk=self.target.pk).update(team_key="local.audio")
        plan = build_team_key_configuration_plan(self.mappings())

        self.assertFalse(plan["ready"])
        self.assertTrue(any("TARGET_ALREADY_CONFIGURED" in item for item in plan["blockers"]))

    def test_proposed_key_owned_by_other_team_blocks(self):
        MinistryTeam.objects.filter(pk=self.other.pk).update(team_key="local.audio")
        plan = build_team_key_configuration_plan(self.mappings())

        self.assertFalse(plan["ready"])
        self.assertTrue(any("PROPOSED_KEY_ALREADY_OWNED" in item for item in plan["blockers"]))

    def test_malformed_or_noncanonical_existing_key_blocks(self):
        for bad_key, problem in (("Bad Key", "MALFORMED"), ("UPPER.KEY", "NONCANONICAL")):
            with self.subTest(bad_key=bad_key):
                MinistryTeam.objects.filter(pk=self.other.pk).update(team_key=bad_key)
                plan = build_team_key_configuration_plan(self.mappings())
                self.assertFalse(plan["ready"])
                self.assertTrue(any(problem in item for item in plan["integrity_problems"]))
                MinistryTeam.objects.filter(pk=self.other.pk).update(team_key=None)

    def test_unsupported_duplicate_canonical_storage_blocks(self):
        third = MinistryTeam.objects.create(name="Third")
        MinistryTeam.objects.filter(pk=self.other.pk).update(team_key="shared.key")
        MinistryTeam.objects.filter(pk=third.pk).update(team_key="SHARED.KEY")
        plan = build_team_key_configuration_plan(self.mappings())

        self.assertFalse(plan["ready"])
        self.assertEqual(
            sum("DUPLICATE_CANONICAL_TEAM_KEY" in item for item in plan["integrity_problems"]),
            2,
        )

    def test_private_roster_role_and_contact_data_are_absent(self):
        private_user = User.objects.create_user(
            username="private_operator_target",
            email="private-contact@example.test",
        )
        TeamMembership.objects.create(
            team=self.target,
            user=private_user,
            display_name="Private Roster Name",
            email="roster-secret@example.test",
            notes="Private membership notes",
        )
        role_type = MinistryTeamRoleType.objects.create(
            code="private_role", name="私密角色", name_en="Private Role"
        )
        MinistryTeamRoleAssignment.objects.create(
            team=self.target,
            role_type=role_type,
            user=private_user,
            notes="Private role notes",
        )
        output = self.command_output([f"{self.target.pk}=local.audio"])

        for private_value in (
            "private_operator_target",
            "private-contact@example.test",
            "Private Roster Name",
            "roster-secret@example.test",
            "Private membership notes",
            "Private role notes",
        ):
            self.assertNotIn(private_value, output)


class MinistryTeamKeyConfigurationApplyTests(TestCase):
    def setUp(self):
        self.first = MinistryTeam.objects.create(name="Audio", name_en="Audio")
        self.second = MinistryTeam.objects.create(name="Beta Team", name_en="Beta Team")
        self.other = MinistryTeam.objects.create(name="Hospitality", name_en="Hospitality")
        self.mappings = parse_mapping_values(
            [f"{self.first.pk}= Local.Audio ", f"{self.second.pk}=local.beta"]
        )

    def token(self):
        return build_team_key_configuration_plan(self.mappings)["confirmation_token"]

    def assert_all_unconfigured(self):
        self.first.refresh_from_db()
        self.second.refresh_from_db()
        self.assertIsNone(self.first.team_key)
        self.assertIsNone(self.second.team_key)

    def test_apply_without_token_rejects_with_zero_writes(self):
        with self.assertRaisesRegex(CommandError, "requires --confirmation-token"):
            call_command(
                "configure_ministry_team_keys",
                mapping=[f"{self.first.pk}=local.audio"],
                apply=True,
            )
        self.assert_all_unconfigured()

    def test_token_without_apply_remains_dry_run(self):
        output = StringIO()
        call_command(
            "configure_ministry_team_keys",
            mapping=[f"{self.first.pk}=local.audio"],
            confirmation_token=self.token(),
            stdout=output,
        )
        self.assertIn("DRY RUN only", output.getvalue())
        self.assert_all_unconfigured()

    def test_wrong_token_rejects_with_zero_writes(self):
        with self.assertRaises(TeamKeyConfigurationStale):
            apply_team_key_configuration(self.mappings, "0" * 64)
        self.assert_all_unconfigured()

    def test_stale_token_after_name_or_path_change_rejects(self):
        root = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_ROOT,
            code="ROOT",
            name="Local Church",
        )
        MinistryTeamParentLink.objects.create(
            child_team=self.first,
            parent_church_unit=root,
            is_primary=True,
        )
        name_token = self.token()
        MinistryTeam.objects.filter(pk=self.first.pk).update(name="Audio Renamed")
        with self.assertRaises(TeamKeyConfigurationStale):
            apply_team_key_configuration(self.mappings, name_token)
        self.assert_all_unconfigured()

        current_token = self.token()
        ChurchStructureUnit.objects.filter(pk=root.pk).update(name="New Root")
        with self.assertRaises(TeamKeyConfigurationStale):
            apply_team_key_configuration(self.mappings, current_token)
        self.assert_all_unconfigured()

    def test_stale_token_after_target_key_change_never_overwrites(self):
        token = self.token()
        MinistryTeam.objects.filter(pk=self.first.pk).update(team_key="already.configured")

        with self.assertRaises(TeamKeyConfigurationNotReady):
            apply_team_key_configuration(self.mappings, token)
        self.first.refresh_from_db()
        self.second.refresh_from_db()
        self.assertEqual(self.first.team_key, "already.configured")
        self.assertIsNone(self.second.team_key)

    def test_valid_token_applies_all_normalized_values_and_advances_updated_at(self):
        token = self.token()
        before_first = self.first.updated_at
        before_second = self.second.updated_at

        result = apply_team_key_configuration(self.mappings, token)

        self.first.refresh_from_db()
        self.second.refresh_from_db()
        self.other.refresh_from_db()
        self.assertEqual(result, {"mappings_requested": 2, "rows_configured": 2})
        self.assertEqual(self.first.team_key, "local.audio")
        self.assertEqual(self.second.team_key, "local.beta")
        self.assertGreater(self.first.updated_at, before_first)
        self.assertGreater(self.second.updated_at, before_second)
        self.assertIsNone(self.other.team_key)

    def test_cas_loss_on_second_target_rolls_back_every_target(self):
        token = self.token()
        original = team_key_configuration._cas_configure_row
        calls = 0

        def lose_second(row, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                return 0
            return original(row, **kwargs)

        with patch(
            "ministry.team_key_configuration._cas_configure_row",
            side_effect=lose_second,
        ):
            with self.assertRaises(TeamKeyConfigurationStale):
                apply_team_key_configuration(self.mappings, token)

        self.assert_all_unconfigured()

    def test_second_apply_with_old_token_cannot_rename_or_reconfigure(self):
        token = self.token()
        apply_team_key_configuration(self.mappings, token)

        with self.assertRaises(TeamKeyConfigurationNotReady):
            apply_team_key_configuration(self.mappings, token)
        self.first.refresh_from_db()
        self.second.refresh_from_db()
        self.assertEqual(self.first.team_key, "local.audio")
        self.assertEqual(self.second.team_key, "local.beta")

    def test_zero_side_effect_apply_preserves_related_domain_state(self):
        root = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_ROOT,
            code="ROOT",
            name="Local Church",
        )
        parent_link = MinistryTeamParentLink.objects.create(
            child_team=self.first,
            parent_church_unit=root,
            is_primary=True,
        )
        user = User.objects.create_user(username="related_user")
        membership = TeamMembership.objects.create(
            team=self.first,
            user=user,
            display_name="Related User",
            email="related@example.test",
            notes="Keep this private note",
        )
        role_type = MinistryTeamRoleType.objects.create(
            code="related_role", name="Related Role"
        )
        role = MinistryTeamRoleAssignment.objects.create(
            team=self.first,
            role_type=role_type,
            user=user,
            notes="Keep role note",
        )
        event = ServiceEvent.objects.create(
            title="Generic Sunday",
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
            start_datetime=timezone.now() + timezone.timedelta(days=7),
            status=ServiceEvent.STATUS_PUBLISHED,
        )
        assignment = TeamAssignment.objects.create(
            service_event=event,
            ministry_team=self.first,
            status=TeamAssignment.STATUS_SCHEDULED,
            notes="Keep assignment note",
        )
        event.refresh_from_db()
        snapshot = {
            "parent": (parent_link.parent_church_unit_id, parent_link.updated_at),
            "membership": (membership.role, membership.notes, membership.updated_at),
            "role": (role.is_active, role.notes, role.updated_at),
            "assignment": (assignment.status, assignment.notes, assignment.updated_at),
            "event": (event.scheduling_revision, event.updated_at),
            "counts": (
                MinistryTeamParentLink.objects.count(),
                TeamMembership.objects.count(),
                MinistryTeamRoleAssignment.objects.count(),
                TeamAssignment.objects.count(),
                ServiceEvent.objects.count(),
            ),
        }

        apply_team_key_configuration(self.mappings, self.token())

        parent_link.refresh_from_db()
        membership.refresh_from_db()
        role.refresh_from_db()
        assignment.refresh_from_db()
        event.refresh_from_db()
        self.assertEqual(snapshot["parent"], (parent_link.parent_church_unit_id, parent_link.updated_at))
        self.assertEqual(snapshot["membership"], (membership.role, membership.notes, membership.updated_at))
        self.assertEqual(snapshot["role"], (role.is_active, role.notes, role.updated_at))
        self.assertEqual(snapshot["assignment"], (assignment.status, assignment.notes, assignment.updated_at))
        self.assertEqual(snapshot["event"], (event.scheduling_revision, event.updated_at))
        self.assertEqual(
            snapshot["counts"],
            (
                MinistryTeamParentLink.objects.count(),
                TeamMembership.objects.count(),
                MinistryTeamRoleAssignment.objects.count(),
                TeamAssignment.objects.count(),
                ServiceEvent.objects.count(),
            ),
        )

    def test_command_reports_apply_complete_and_post_audit(self):
        token = self.token()
        output = StringIO()

        call_command(
            "configure_ministry_team_keys",
            "--mapping",
            f"{self.first.pk}=local.audio",
            "--mapping",
            f"{self.second.pk}=local.beta",
            "--apply",
            "--confirmation-token",
            token,
            stdout=output,
        )

        value = output.getvalue()
        self.assertIn("APPLY COMPLETE", value)
        self.assertIn("mappings_requested: 2", value)
        self.assertIn("rows_configured: 2", value)
        self.assertIn("failed_rows: 0", value)
        self.assertIn("manage.py audit_ministry_team_identity", value)
