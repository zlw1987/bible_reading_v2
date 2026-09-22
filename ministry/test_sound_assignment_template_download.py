"""Focused generic Team Roster verified-workbook download tests."""

from datetime import timedelta
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth.models import User
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from accounts.permissions import CAP_MANAGE_TEAM_ASSIGNMENTS
from events.models import ServiceEvent, ServiceEventPlannerAssignment

from .models import MinistryTeam, MinistryTeamRoleAssignment, MinistryTeamRoleType
from .permissions import can_manage_team_assignments
from .services.sound_assignment_xlsx_preview import INTEGRATION_KEY
from .services.sound_assignment_template import (
    DOWNLOAD_CONTENT_TYPE,
    DOWNLOAD_FILENAME,
)


@override_settings(CMS_ENABLED_INTEGRATIONS=[INTEGRATION_KEY])
class SoundAssignmentTemplateDownloadTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.temp_parent = Path(settings.BASE_DIR) / "temp"
        cls.temp_parent.mkdir(exist_ok=True)
        cls.staff = User.objects.create_user(
            "template_staff", password="pw", is_staff=True
        )
        cls.inactive_staff = User.objects.create_user(
            "template_inactive_staff", password="pw", is_staff=True, is_active=False
        )
        cls.superuser = User.objects.create_superuser(
            "template_super", "template-super@example.test", "pw"
        )
        cls.ordinary = User.objects.create_user("template_member", password="pw")
        cls.assignment_manager = User.objects.create_user(
            "template_assignment_manager", password="pw"
        )
        cls.sound_lead = User.objects.create_user("template_sound_lead", password="pw")
        cls.planner = User.objects.create_user("template_planner", password="pw")

        sound_team = MinistryTeam.objects.create(
            name="Sound Team",
            team_key="main.cm.digital.sound",
            is_active=True,
            is_assignable=True,
        )
        lead_role = MinistryTeamRoleType.objects.create(
            code=MinistryTeamRoleType.CODE_LEAD,
            name="Lead",
            name_en="Lead",
        )
        MinistryTeamRoleAssignment.objects.create(
            team=sound_team,
            role_type=lead_role,
            user=cls.sound_lead,
            start_date=timezone.localdate(),
        )
        event = ServiceEvent.objects.create(
            title="Planner-only event",
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
            start_datetime=timezone.now() + timedelta(days=7),
        )
        ServiceEventPlannerAssignment.objects.create(
            service_event=event, user=cls.planner
        )

    def _force_login(self, user, *, language="en"):
        self.client.force_login(user)
        session = self.client.session
        session["language"] = language
        session.save()

    def _valid_download(self, user, content=b"exact private workbook bytes"):
        source_path = self.temp_parent / (
            f"{self._testMethodName}-{user.pk}-private-template.xlsx"
        )
        source_path.write_bytes(content)
        self.addCleanup(source_path.unlink, missing_ok=True)
        expected_hash = sha256(content).hexdigest().upper()
        with override_settings(
            SOUND_ASSIGNMENT_IMPORT_TEMPLATE_PATH=str(source_path)
        ), patch(
            "ministry.services.sound_assignment_template."
            "EXPECTED_REAL_WORKBOOK_SHA256",
            expected_hash,
        ):
            self._force_login(user)
            response = self.client.get(
                reverse("download_team_roster_workbook_template")
            )
            downloaded = b"".join(response.streaming_content)
            response.close()
            source_after = source_path.read_bytes()
        return response, downloaded, source_after

    def test_staff_and_superuser_can_download(self):
        for user in (self.staff, self.superuser):
            with self.subTest(user=user.username):
                response, downloaded, source_after = self._valid_download(user)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(downloaded, source_after)

    def test_authentication_is_required(self):
        response = self.client.get(
            reverse("download_team_roster_workbook_template")
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response["Location"])

    def test_ordinary_manager_lead_and_planner_are_denied(self):
        with patch(
            "ministry.permissions.has_capability",
            side_effect=lambda user, capability: (
                user.pk == self.assignment_manager.pk
                and capability == CAP_MANAGE_TEAM_ASSIGNMENTS
            ),
        ):
            self.assertTrue(can_manage_team_assignments(self.assignment_manager))
            for user in (
                self.ordinary,
                self.assignment_manager,
                self.sound_lead,
                self.planner,
            ):
                with self.subTest(user=user.username):
                    self._force_login(user)
                    response = self.client.get(
                        reverse("download_team_roster_workbook_template")
                    )
                    self.assertEqual(response.status_code, 403)

    def test_inactive_staff_is_denied_by_generic_authority(self):
        self._force_login(self.inactive_staff)
        response = self.client.get(reverse("download_team_roster_workbook_template"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response["Location"])

    @override_settings(CMS_ENABLED_INTEGRATIONS=[])
    def test_disabled_integration_fails_closed_before_template_open(self):
        self._force_login(self.staff)
        with patch(
            "ministry.services.sound_assignment_template."
            "open_verified_sound_assignment_template"
        ) as opener:
            response = self.client.get(
                reverse("download_team_roster_workbook_template")
            )
        self.assertEqual(response.status_code, 404)
        opener.assert_not_called()

    def test_unconfigured_and_missing_template_fail_closed_without_path_disclosure(
        self,
    ):
        self._force_login(self.staff)
        missing_path = str(self.temp_parent / "private-name.xlsx")
        for configured_path in ("", missing_path):
            with self.subTest(configured_path=bool(configured_path)), override_settings(
                SOUND_ASSIGNMENT_IMPORT_TEMPLATE_PATH=configured_path
            ):
                response = self.client.get(
                    reverse("download_team_roster_workbook_template")
                )
                self.assertEqual(response.status_code, 404)
                self.assertContains(
                    response,
                    "The verified annual workbook is currently unavailable.",
                    status_code=404,
                )
                self.assertNotContains(
                    response,
                    "private-name.xlsx",
                    status_code=404,
                )

    def test_non_regular_file_and_sha_mismatch_fail_closed(self):
        self._force_login(self.staff)
        mismatched_file = self.temp_parent / "mismatched-template.xlsx"
        mismatched_file.write_bytes(b"not the supported workbook")
        self.addCleanup(mismatched_file.unlink, missing_ok=True)
        for configured_path in (self.temp_parent, mismatched_file):
            with self.subTest(path_type=configured_path.name), override_settings(
                SOUND_ASSIGNMENT_IMPORT_TEMPLATE_PATH=str(configured_path)
            ):
                response = self.client.get(
                    reverse("download_team_roster_workbook_template")
                )
                self.assertEqual(response.status_code, 404)
                self.assertNotContains(
                    response,
                    str(configured_path),
                    status_code=404,
                )

    def test_valid_response_has_exact_headers_bytes_no_rewrite_and_no_database_write(self):
        content = b"source bytes stay byte-for-byte unchanged\x00\xff"
        source_path = self.temp_parent / "exact-byte-source.xlsx"
        source_path.write_bytes(content)
        self.addCleanup(source_path.unlink, missing_ok=True)
        expected_hash = sha256(content).hexdigest().upper()
        self._force_login(self.staff)
        with override_settings(
            SOUND_ASSIGNMENT_IMPORT_TEMPLATE_PATH=str(source_path)
        ), patch(
            "ministry.services.sound_assignment_template."
            "EXPECTED_REAL_WORKBOOK_SHA256",
            expected_hash,
        ), patch("openpyxl.load_workbook") as load_workbook, CaptureQueriesContext(
            connection
        ) as queries:
            response = self.client.get(
                reverse("download_team_roster_workbook_template")
            )
            downloaded = b"".join(response.streaming_content)
            response.close()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], DOWNLOAD_CONTENT_TYPE)
        self.assertEqual(
            response["Content-Disposition"],
            f'attachment; filename="{DOWNLOAD_FILENAME}"',
        )
        self.assertEqual(downloaded, content)
        self.assertEqual(source_path.read_bytes(), content)
        load_workbook.assert_not_called()
        mutating_queries = [
            query["sql"]
            for query in queries
            if query["sql"].lstrip().upper().startswith(
                ("INSERT", "UPDATE", "DELETE", "REPLACE")
            )
        ]
        self.assertEqual(mutating_queries, [])

    def test_route_is_get_only(self):
        self._force_login(self.staff)
        response = self.client.post(
            reverse("download_team_roster_workbook_template")
        )
        self.assertEqual(response.status_code, 405)

    def test_generic_page_links_verified_workbook_with_non_authority_copy(self):
        self._force_login(self.staff)
        for language, expected in (
            ("en", "Download Verified Annual Workbook"),
            ("zh", "下载已验证的年度工作簿"),
        ):
            with self.subTest(language=language):
                session = self.client.session
                session["language"] = language
                session.save()
                response = self.client.get(
                    reverse("team_roster_column_mapping_review")
                )
                self.assertContains(response, expected)
                self.assertContains(
                    response,
                    reverse("download_team_roster_workbook_template"),
                )
                if language == "en":
                    for instruction in (
                        "exact deployment workbook supported by this import adapter",
                        "does not map columns or authorize any write",
                        "uploaded roster columns still require explicit review",
                    ):
                        self.assertContains(response, instruction)
                    self.assertNotContains(response, "Sound template")
                    self.assertNotContains(response, "edit Column F only")

    def test_old_template_route_is_get_only_redirect(self):
        self._force_login(self.staff)
        response = self.client.get(
            reverse("download_sound_assignment_workbook_template")
        )
        self.assertRedirects(
            response,
            reverse("download_team_roster_workbook_template"),
            fetch_redirect_response=False,
        )
        response = self.client.post(
            reverse("download_sound_assignment_workbook_template"),
            {"signed_confirmation": "legacy-state-must-not-forward"},
        )
        self.assertEqual(response.status_code, 405)
        self.assertNotIn("Location", response)
