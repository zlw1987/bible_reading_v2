from io import StringIO

from django.contrib import admin
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import RequestFactory, TestCase
from django.urls import reverse

from .admin import MinistryTeamAdmin
from .forms import (
    MinistryTeamForm,
    MinistryTeamStructureForm,
    TeamAssignmentForm,
    TeamMembershipForm,
    TeamScheduleAssignmentForm,
)
from .management.commands.audit_ministry_team_identity import (
    build_identity_inventory,
)
from .models import (
    MinistryTeam,
    MinistryTeamRoleAssignment,
    MinistryTeamRoleType,
    TeamMembership,
)


class MinistryTeamKeyModelTests(TestCase):
    def test_default_is_none_and_multiple_nulls_are_allowed(self):
        first = MinistryTeam.objects.create(name="Alpha")
        second = MinistryTeam.objects.create(name="Beta")

        self.assertIsNone(first.team_key)
        self.assertIsNone(second.team_key)

    def test_valid_key_normalizes_and_valid_punctuation_is_accepted(self):
        examples = {
            " Main_CM_Lighting ": "main_cm_lighting",
            "worship.c1": "worship.c1",
            "av-team": "av-team",
        }
        for index, (submitted, expected) in enumerate(examples.items()):
            with self.subTest(submitted=submitted):
                team = MinistryTeam(name=f"Team {index}", team_key=submitted)
                team.full_clean()
                team.save()
                self.assertEqual(team.team_key, expected)
                self.assertEqual(
                    MinistryTeam.objects.get(pk=team.pk).team_key,
                    expected,
                )

    def test_whitespace_only_normalizes_to_none(self):
        team = MinistryTeam(name="Blank", team_key="   ")
        team.full_clean()
        team.save()

        self.assertIsNone(team.team_key)
        self.assertIsNone(MinistryTeam.objects.get(pk=team.pk).team_key)

    def test_surrounding_whitespace_is_removed_before_length_validation(self):
        key = "a" * 64
        team = MinistryTeam(name="Long", team_key=f"  {key}  ")

        team.full_clean()
        team.save()

        self.assertEqual(team.team_key, key)

    def test_invalid_nonblank_keys_are_rejected(self):
        for invalid in (
            "Main CM Lighting",
            "灯光团队",
            "team/key",
            "team@main",
        ):
            with self.subTest(invalid=invalid):
                team = MinistryTeam(name="Invalid", team_key=invalid)
                with self.assertRaises(ValidationError) as raised:
                    team.full_clean()
                self.assertIn("team_key", raised.exception.message_dict)

    def test_normalized_duplicate_fails_model_validation(self):
        MinistryTeam.objects.create(name="First", team_key="shared.key")
        duplicate = MinistryTeam(name="Second", team_key=" SHARED.KEY ")

        with self.assertRaises(ValidationError) as raised:
            duplicate.full_clean()

        self.assertIn("team_key", raised.exception.message_dict)

    def test_name_rename_does_not_change_key(self):
        team = MinistryTeam.objects.create(name="Original", team_key="stable.key")
        team.name = "Renamed"
        team.name_en = "Renamed English"
        team.save(update_fields=["name", "name_en", "updated_at"])
        team.refresh_from_db()

        self.assertEqual(team.team_key, "stable.key")

    def test_taxonomy_assignability_and_worship_pool_do_not_define_key(self):
        ordinary = MinistryTeam(
            name="Ordinary",
            team_key="ordinary.identity",
            team_kind=MinistryTeam.KIND_CUSTOM,
            is_assignable=True,
        )
        pool = MinistryTeam(
            name="Pool",
            team_key="pool.identity",
            team_kind=MinistryTeam.KIND_DEPARTMENT,
            is_assignable=False,
            is_worship_rotation_pool=True,
        )

        ordinary.full_clean()
        pool.full_clean()
        self.assertEqual(ordinary.team_key, "ordinary.identity")
        self.assertEqual(pool.team_key, "pool.identity")


class MinistryTeamKeyStructureSurfaceTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(
            username="identity_staff", password="pw", is_staff=True
        )
        self.regular = User.objects.create_user(
            username="identity_regular", password="pw"
        )
        self.team = MinistryTeam.objects.create(name="Setup Team", name_en="Setup Team")

    def structure_url(self, team=None):
        return reverse(
            "manage_ministry_team_structure", args=[(team or self.team).pk]
        )

    def metadata_post(self, **overrides):
        data = {
            "action": "metadata",
            "team_key": " Main_Setup.Team ",
            "team_kind": MinistryTeam.KIND_TEAM,
            "is_assignable": "on",
            "is_active": "on",
        }
        data.update(overrides)
        return data

    def test_authorized_staff_can_set_null_key_and_normalized_value_is_stored(self):
        self.client.login(username="identity_staff", password="pw")
        response = self.client.post(self.structure_url(), self.metadata_post())

        self.assertRedirects(response, self.structure_url())
        self.team.refresh_from_db()
        self.assertEqual(self.team.team_key, "main_setup.team")

    def test_unconfigured_setup_state_is_explicit(self):
        session = self.client.session
        session["language"] = "en"
        session.save()
        self.client.login(username="identity_staff", password="pw")

        response = self.client.get(self.structure_url())

        self.assertContains(response, "No technical key is configured.")

    def test_non_staff_cannot_set_key(self):
        self.client.login(username="identity_regular", password="pw")
        response = self.client.post(self.structure_url(), self.metadata_post())

        self.assertRedirects(response, reverse("ministry_team_list"))
        self.team.refresh_from_db()
        self.assertIsNone(self.team.team_key)

    def test_configured_key_is_read_only_and_malicious_replacement_is_ignored(self):
        self.team.team_key = "stable.key"
        self.team.save()
        session = self.client.session
        session["language"] = "en"
        session.save()
        self.client.login(username="identity_staff", password="pw")

        get_response = self.client.get(self.structure_url())
        self.assertContains(get_response, "Stable team key")
        self.assertContains(get_response, "stable.key")
        self.assertTrue(get_response.context["metadata_form"].fields["team_key"].disabled)

        response = self.client.post(
            self.structure_url(),
            self.metadata_post(team_key="replacement.key", team_kind=MinistryTeam.KIND_SUBTEAM),
        )
        self.assertRedirects(response, self.structure_url())
        self.team.refresh_from_db()
        self.assertEqual(self.team.team_key, "stable.key")
        self.assertEqual(self.team.team_kind, MinistryTeam.KIND_SUBTEAM)

    def test_duplicate_key_is_a_clean_form_error_not_an_integrity_error(self):
        MinistryTeam.objects.create(name="Existing", team_key="duplicate.key")
        self.client.login(username="identity_staff", password="pw")

        response = self.client.post(
            self.structure_url(),
            self.metadata_post(team_key=" DUPLICATE.KEY "),
        )

        self.assertEqual(response.status_code, 200)
        self.assertFormError(
            response.context["metadata_form"],
            "team_key",
            "Ministry team with this Team key already exists.",
        )
        self.team.refresh_from_db()
        self.assertIsNone(self.team.team_key)

    def test_ordinary_team_edit_preserves_key_and_does_not_expose_field(self):
        self.team.team_key = "stable.key"
        self.team.save()
        form = MinistryTeamForm(
            {
                "name": "Renamed Team",
                "name_en": "Renamed Team",
                "description": "",
                "description_en": "",
                "email_alias": "",
                "playbook_link": "",
                "is_active": "on",
                "team_key": "attempted.replacement",
            },
            instance=self.team,
        )

        self.assertNotIn("team_key", form.fields)
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        self.team.refresh_from_db()
        self.assertEqual(self.team.name, "Renamed Team")
        self.assertEqual(self.team.team_key, "stable.key")

    def test_ordinary_member_and_scheduling_forms_do_not_expose_team_key(self):
        self.assertNotIn("team_key", MinistryTeamForm.base_fields)
        self.assertNotIn("team_key", TeamMembershipForm.base_fields)
        self.assertNotIn("team_key", TeamAssignmentForm.base_fields)
        self.assertNotIn("team_key", TeamScheduleAssignmentForm.base_fields)

    def test_chinese_setup_copy_is_present_for_unconfigured_key(self):
        session = self.client.session
        session["language"] = "zh"
        session.save()
        self.client.login(username="identity_staff", password="pw")

        response = self.client.get(self.structure_url())

        self.assertContains(response, "稳定团队标识")
        self.assertContains(response, "不授予任何权限，也不代表服事安排")


class MinistryTeamKeyAdminTests(TestCase):
    def setUp(self):
        self.superuser = User.objects.create_superuser(
            username="identity_admin", password="pw", email="admin@example.com"
        )
        self.request = RequestFactory().get("/admin/ministry/ministryteam/")
        self.request.user = self.superuser
        self.model_admin = MinistryTeamAdmin(MinistryTeam, admin.site)

    def form_data(self, team, **overrides):
        data = {
            "name": team.name,
            "name_en": team.name_en,
            "team_key": team.team_key or "",
            "description": team.description,
            "description_en": team.description_en,
            "email_alias": team.email_alias,
            "playbook_link": team.playbook_link,
            "team_kind": team.team_kind,
            "is_assignable": "on" if team.is_assignable else "",
            "is_worship_rotation_pool": "on" if team.is_worship_rotation_pool else "",
            "role_profile": team.role_profile_id or "",
            "is_active": "on" if team.is_active else "",
        }
        data.update(overrides)
        return data

    def test_admin_can_set_unconfigured_key_and_it_normalizes(self):
        team = MinistryTeam.objects.create(name="Admin New")
        form_class = self.model_admin.get_form(self.request, team)
        form = form_class(self.form_data(team, team_key=" Admin.Key "), instance=team)

        self.assertTrue(form.is_valid(), form.errors)
        saved = form.save()
        self.assertEqual(saved.team_key, "admin.key")

    def test_configured_key_is_read_only_while_human_name_remains_editable(self):
        team = MinistryTeam.objects.create(name="Admin Existing", team_key="stable.key")
        self.assertIn(
            "team_key", self.model_admin.get_readonly_fields(self.request, team)
        )
        form_class = self.model_admin.get_form(self.request, team)
        form = form_class(
            self.form_data(
                team,
                name="Admin Renamed",
                team_key="replacement.key",
            ),
            instance=team,
        )

        self.assertNotIn("team_key", form.fields)
        self.assertTrue(form.is_valid(), form.errors)
        saved = form.save()
        self.assertEqual(saved.name, "Admin Renamed")
        self.assertEqual(saved.team_key, "stable.key")

    def test_duplicate_normalized_admin_target_is_a_form_error(self):
        MinistryTeam.objects.create(name="Admin Existing", team_key="duplicate.key")
        target = MinistryTeam.objects.create(name="Admin Target")
        form_class = self.model_admin.get_form(self.request, target)
        form = form_class(
            self.form_data(target, team_key=" DUPLICATE.KEY "), instance=target
        )

        self.assertFalse(form.is_valid())
        self.assertIn("team_key", form.errors)


class MinistryTeamIdentityInventoryTests(TestCase):
    def setUp(self):
        self.configured = MinistryTeam.objects.create(
            name="已配置团队",
            name_en="Configured Team",
            team_key="configured.team",
            is_active=True,
            is_assignable=True,
        )
        self.unconfigured = MinistryTeam.objects.create(
            name="未配置团队",
            name_en="Unconfigured Team",
            is_active=False,
            is_assignable=False,
        )

        private_user = User.objects.create_user(
            username="private_user",
            email="private-contact@example.test",
        )
        TeamMembership.objects.create(
            team=self.configured,
            user=private_user,
            display_name="Private Roster Name",
            email="roster-secret@example.test",
            notes="Private membership notes",
        )
        role_type = MinistryTeamRoleType.objects.create(
            code="identity_test_role", name="私密角色", name_en="Private Role"
        )
        MinistryTeamRoleAssignment.objects.create(
            team=self.configured,
            role_type=role_type,
            user=private_user,
            notes="Private role notes",
        )

    def model_counts(self):
        return {
            MinistryTeam: MinistryTeam.objects.count(),
            TeamMembership: TeamMembership.objects.count(),
            MinistryTeamRoleAssignment: MinistryTeamRoleAssignment.objects.count(),
        }

    def test_inventory_is_deterministic_read_only_and_privacy_bounded(self):
        before = self.model_counts()
        first = StringIO()
        second = StringIO()
        call_command("audit_ministry_team_identity", stdout=first)
        call_command("audit_ministry_team_identity", stdout=second)
        output = first.getvalue()

        self.assertEqual(first.getvalue(), second.getvalue())
        self.assertEqual(before, self.model_counts())
        self.assertIn(f"pk={self.configured.pk}", output)
        self.assertIn("team_key=\"configured.team\"", output)
        self.assertIn(f"pk={self.unconfigured.pk}", output)
        self.assertIn("team_key=UNCONFIGURED", output)
        self.assertIn("configured_team_keys: 1", output)
        self.assertIn("unconfigured_team_keys: 1", output)
        self.assertIn("not a trial-readiness blocker", output)
        for private_value in (
            "private_user",
            "private-contact@example.test",
            "Private Roster Name",
            "roster-secret@example.test",
            "Private membership notes",
            "Private role notes",
        ):
            self.assertNotIn(private_value, output)

    def test_all_null_inventory_is_informational_not_blocking(self):
        MinistryTeam.objects.filter(pk=self.configured.pk).update(team_key=None)
        output = StringIO()

        call_command("audit_ministry_team_identity", stdout=output)

        self.assertIn("configured_team_keys: 0", output.getvalue())
        self.assertIn("unconfigured_team_keys: 2", output.getvalue())
        self.assertIn("not a trial-readiness blocker", output.getvalue())

    def test_unsupported_malformed_storage_is_reported_without_mutation(self):
        MinistryTeam.objects.filter(pk=self.configured.pk).update(team_key="Bad Key")
        before = self.model_counts()

        inventory = build_identity_inventory()

        row = next(
            row for row in inventory["rows"] if row["pk"] == self.configured.pk
        )
        self.assertIn("MALFORMED_TEAM_KEY", row["integrity_problems"])
        self.assertEqual(inventory["summary"]["integrity_problem_teams"], 1)
        self.assertEqual(before, self.model_counts())
        self.configured.refresh_from_db()
        self.assertEqual(self.configured.team_key, "Bad Key")

    def test_unsupported_normalized_duplicate_is_reported_fail_closed(self):
        MinistryTeam.objects.filter(pk=self.configured.pk).update(team_key="raw.key")
        MinistryTeam.objects.filter(pk=self.unconfigured.pk).update(team_key="RAW.KEY")

        inventory = build_identity_inventory()

        rows = {row["pk"]: row for row in inventory["rows"]}
        self.assertIn(
            "DUPLICATE_CANONICAL_TEAM_KEY",
            rows[self.configured.pk]["integrity_problems"],
        )
        self.assertIn(
            "DUPLICATE_CANONICAL_TEAM_KEY",
            rows[self.unconfigured.pk]["integrity_problems"],
        )
        self.assertIn(
            "NONCANONICAL_TEAM_KEY",
            rows[self.unconfigured.pk]["integrity_problems"],
        )
        self.assertEqual(inventory["summary"]["integrity_problem_teams"], 2)
