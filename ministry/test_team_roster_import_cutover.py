"""Focused MO-S.6F.GENERAL.1G-1A authority and UX cutover regressions."""

import inspect

from django.contrib.auth.models import User
from django.core import signing
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import NoReverseMatch, reverse

from .services.sound_assignment_xlsx_confirmation import (
    CONFIRMATION_CONTRACT_REVISION,
    CONFIRMATION_SIGNING_SALT,
)
from .services.sound_assignment_xlsx_roster_update import (
    ROSTER_UPDATE_CONTRACT_REVISION,
    ROSTER_UPDATE_SIGNING_SALT,
)
from .services.team_roster_assignment_confirmation import (
    TeamRosterConfirmationProposalError,
    decode_team_roster_confirmation,
)
from .services.worship_xlsx_preview import INTEGRATION_KEY
from .views import (
    download_sound_assignment_workbook_template,
    download_team_roster_workbook_template,
    sound_assignment_workbook_preview,
    team_roster_column_mapping_review,
)


@override_settings(CMS_ENABLED_INTEGRATIONS=[INTEGRATION_KEY])
class TeamRosterImportCutoverTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = User.objects.create_user(
            "cutover_staff", password="pw", is_staff=True
        )
        cls.superuser = User.objects.create_superuser(
            "cutover_super", "cutover-super@example.test", "pw"
        )

    def set_language(self, language):
        session = self.client.session
        session["language"] = language
        session.save()

    def test_generic_route_reachable_for_staff_and_superuser(self):
        for user in (self.staff, self.superuser):
            with self.subTest(user=user.username):
                self.client.force_login(user)
                self.set_language("en")
                response = self.client.get(reverse("team_roster_column_mapping_review"))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "Team Roster Import")

    def test_removed_route_names_and_paths_are_unavailable(self):
        removed = {
            "confirm_sound_assignment_workbook": "/assignments/import/sound-confirm/",
            "confirm_sound_assignment_roster_update_workbook": (
                "/assignments/import/sound-roster-update-confirm/"
            ),
            "projection_assignment_workbook_preview": (
                "/assignments/import/projection-preview/"
            ),
        }
        self.client.force_login(self.staff)
        for route_name, path in removed.items():
            with self.subTest(route_name=route_name):
                with self.assertRaises(NoReverseMatch):
                    reverse(route_name)
                self.assertEqual(self.client.get(path).status_code, 404)
                self.assertEqual(self.client.post(path, {"token": "old"}).status_code, 404)

    def test_old_sound_preview_is_get_only_redirect_and_drops_post_state(self):
        self.client.force_login(self.staff)
        alias = reverse("sound_assignment_workbook_preview")
        response = self.client.get(alias, {"signed_mapping_state": "old-query-state"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("team_roster_column_mapping_review"))
        response = self.client.post(
            alias,
            {
                "signed_mapping_state": "old-post-state",
                "workbook": SimpleUploadedFile("old.xlsx", b"old bytes"),
            },
        )
        self.assertEqual(response.status_code, 405)
        self.assertNotIn("Location", response)

    def test_assignment_list_has_exactly_one_bilingual_annual_import_action(self):
        self.client.force_login(self.staff)
        expected_href = reverse("team_roster_column_mapping_review")
        for language, label in (("en", "Team Roster Import"), ("zh", "团队名单导入")):
            with self.subTest(language=language):
                self.set_language(language)
                response = self.client.get(reverse("team_assignment_list"))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, label, count=1)
                self.assertContains(response, f'href="{expected_href}"', count=1)
                for retired_copy in (
                    "Sound Workbook Preview",
                    "音控工作簿预览",
                    "Projection Workbook Preview",
                    "投影工作簿预览",
                ):
                    self.assertNotContains(response, retired_copy)
                self.assertNotContains(
                    response, reverse("sound_assignment_workbook_preview")
                )

    def test_legacy_sound_confirmation_tokens_are_not_generic_authority(self):
        for contract, salt in (
            (CONFIRMATION_CONTRACT_REVISION, CONFIRMATION_SIGNING_SALT),
            (ROSTER_UPDATE_CONTRACT_REVISION, ROSTER_UPDATE_SIGNING_SALT),
        ):
            with self.subTest(contract=contract):
                legacy_token = signing.dumps(
                    {"contract_revision": contract, "user_id": self.staff.pk},
                    salt=salt,
                    compress=True,
                )
                with self.assertRaises(TeamRosterConfirmationProposalError):
                    decode_team_roster_confirmation(
                        legacy_token,
                        reviewed_person_state="not-decoded",
                        assignment_preview_state="not-decoded",
                        user=self.staff,
                    )

    def test_active_cutover_views_do_not_import_legacy_preview_or_writer_services(self):
        active_source = "\n".join(
            inspect.getsource(view)
            for view in (
                team_roster_column_mapping_review,
                download_team_roster_workbook_template,
                sound_assignment_workbook_preview,
                download_sound_assignment_workbook_template,
            )
        )
        for legacy_module in (
            "sound_assignment_xlsx_preview",
            "sound_assignment_xlsx_confirmation",
            "sound_assignment_xlsx_roster_update",
            "projection_assignment_xlsx_preview",
        ):
            self.assertNotIn(legacy_module, active_source)
