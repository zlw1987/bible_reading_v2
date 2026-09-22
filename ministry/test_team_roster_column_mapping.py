"""Focused MO-S.6F.GENERAL.1C zero-write column-mapping tests."""

from datetime import date, datetime, timedelta
import json
from unittest.mock import patch

from django.contrib.admin.models import LogEntry
from django.contrib.auth.models import User
from django.core import signing
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.http import Http404
from django.test import RequestFactory, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from accounts.models import ChurchRoleAssignment, ChurchStructureMembership
from events.models import (
    ServiceEvent,
    ServiceEventAudienceScope,
    ServiceEventPlannerAssignment,
    ServiceEventRequiredTeam,
)
from events.test_worship_xlsx_preview import (
    WorshipWorkbookDomainTestBase,
    build_known_workbook,
)
from notifications.models import Notification

from .models import (
    MinistryTeam,
    MinistryTeamRoleAssignment,
    MinistryTeamRoleType,
    TeamAssignment,
    TeamAssignmentMember,
    TeamMembership,
)
from .services.team_roster_column_mapping import (
    INVENTORY_SIGNING_SALT,
    MAX_COLUMN_MAPPING_STATE_BYTES,
    REVIEWED_SIGNING_SALT,
    TEAM_ROSTER_COLUMN_MAPPING_REVIEW_V1,
    TEAM_ROSTER_REVIEWED_COLUMN_MAPPING_V1,
    TeamRosterColumnMappingStateError,
    TeamRosterColumnMappingValidationError,
    decode_team_roster_column_mapping_review,
    finalize_team_roster_column_mapping,
    prepare_team_roster_column_mapping_review,
)
from .services.worship_xlsx_preview import INTEGRATION_KEY
from .views import team_roster_column_mapping_review


@override_settings(CMS_ENABLED_INTEGRATIONS=[INTEGRATION_KEY])
class TeamRosterColumnMappingTests(WorshipWorkbookDomainTestBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.events = []
        for index, row in enumerate(cls.parsed.rows):
            event = ServiceEvent.objects.create(
                title=f"Bethany Sunday {index}",
                title_en=f"Bethany Sunday {index}",
                service_profile=cls.target_profile,
                event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
                start_datetime=timezone.make_aware(
                    datetime.combine(row.local_date, datetime.min.time()).replace(
                        hour=9, minute=30
                    ),
                    timezone.get_current_timezone(),
                ),
                status=ServiceEvent.STATUS_PUBLISHED,
            )
            ServiceEventAudienceScope.objects.create(
                service_event=event, unit=cls.cm
            )
            cls.events.append(event)

        cls.projection = MinistryTeam.objects.create(
            name="投影团队",
            name_en="Projection Team",
            team_key="main.cm.digital.projection",
        )
        cls.sound = MinistryTeam.objects.create(
            name="音控团队",
            name_en="Sound Team",
            team_key="main.cm.digital.sound",
        )
        cls.video = MinistryTeam.objects.create(
            name="视频团队",
            name_en="Video Team",
            team_key="main.cm.digital.video",
        )
        cls.other_team = MinistryTeam.objects.create(
            name="接待团队",
            name_en="Hospitality Team",
            team_key="main.cm.hospitality",
        )
        cls.inactive = MinistryTeam.objects.create(
            name="Inactive Team",
            team_key="main.cm.inactive",
            is_active=False,
        )
        cls.nonassignable = MinistryTeam.objects.create(
            name="Nonassignable Team",
            team_key="main.cm.container",
            is_assignable=False,
        )
        cls.unkeyed = MinistryTeam.objects.create(name="Unkeyed Team")
        cls.malformed = MinistryTeam.objects.create(
            name="Malformed Team", team_key="temporary.valid.key"
        )
        MinistryTeam.objects.filter(pk=cls.malformed.pk).update(team_key="Bad Key")

        cls.superuser = User.objects.create_user(
            "column_super", password="pw", is_superuser=True, is_staff=False
        )
        cls.exact_lead = User.objects.create_user("column_lead", password="pw")
        cls.global_manager = User.objects.create_user(
            "column_global", password="pw"
        )
        cls.event_planner = User.objects.create_user(
            "column_planner", password="pw"
        )
        cls.exact_coordinator = User.objects.create_user(
            "column_coordinator", password="pw"
        )
        cls.membership_only = User.objects.create_user(
            "column_membership", password="pw"
        )
        cls.audience_only = User.objects.create_user(
            "column_audience", password="pw"
        )
        cls.role_type = MinistryTeamRoleType.objects.create(
            code=MinistryTeamRoleType.CODE_LEAD,
            name="Lead",
            name_en="Lead",
            is_active=True,
        )
        MinistryTeamRoleAssignment.objects.create(
            team=cls.sound,
            role_type=cls.role_type,
            user=cls.exact_lead,
            start_date=date(2026, 1, 1),
            is_active=True,
        )
        coordinator_type = MinistryTeamRoleType.objects.create(
            code=MinistryTeamRoleType.CODE_COORDINATOR,
            name="Coordinator",
            name_en="Coordinator",
            is_active=True,
        )
        MinistryTeamRoleAssignment.objects.create(
            team=cls.sound,
            role_type=coordinator_type,
            user=cls.exact_coordinator,
            start_date=date(2026, 1, 1),
            is_active=True,
        )
        TeamMembership.objects.create(team=cls.sound, user=cls.membership_only)
        ChurchStructureMembership.objects.create(
            user=cls.audience_only,
            unit=cls.cm,
            status=ChurchStructureMembership.STATUS_ACTIVE,
            is_primary=True,
            start_date=timezone.localdate() - timedelta(days=1),
        )
        ChurchRoleAssignment.objects.create(
            user=cls.global_manager,
            role=ChurchRoleAssignment.ROLE_COWORKER,
            scope_type=ChurchRoleAssignment.SCOPE_GLOBAL,
        )
        ServiceEventPlannerAssignment.objects.create(
            service_event=cls.events[0], user=cls.event_planner
        )

    def set_language(self, language):
        session = self.client.session
        session["language"] = language
        session.save()

    def workbook_content(self, **kwargs):
        headers = {
            "C": "BB & Offering",
            "D": "Speaker @Bethany",
            "H": "Video",
            "J": "Other service",
        }
        headers.update(kwargs.pop("header_overrides", {}))
        return build_known_workbook(header_overrides=headers, **kwargs)

    def upload(self, **kwargs):
        return SimpleUploadedFile(
            "review.xlsx",
            self.workbook_content(**kwargs),
            content_type=(
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ),
        )

    def upload_review(self, *, user=None, **kwargs):
        self.client.force_login(user or self.staff)
        self.set_language("en")
        response = self.client.post(
            reverse("team_roster_column_mapping_review"),
            {"workbook": self.upload(**kwargs)},
        )
        self.assertEqual(response.status_code, 200)
        return response, response.context["mapping_review"]

    def mapping_post(self, review, **selected):
        data = {
            "signed_column_inventory_state": review.signed_inventory_state,
            **{f"mapping_{column}": "" for column in "CDEFGHI"},
        }
        data.update(
            {
                f"mapping_{column}": str(team_id) if team_id is not None else ""
                for column, team_id in selected.items()
            }
        )
        return data

    def domain_snapshot(self):
        return {
            "events": list(
                ServiceEvent.objects.order_by("id").values_list(
                    "id", "scheduling_revision", "rotation_anchor_team_id"
                )
            ),
            "audience": list(
                ServiceEventAudienceScope.objects.order_by("id").values_list(
                    "id", "service_event_id", "unit_id"
                )
            ),
            "required": list(
                ServiceEventRequiredTeam.objects.order_by("id").values_list(
                    "id", "service_event_id", "ministry_team_id"
                )
            ),
            "teams": list(
                MinistryTeam.objects.order_by("id").values_list(
                    "id", "team_key", "is_active", "is_assignable"
                )
            ),
            "memberships": list(
                TeamMembership.objects.order_by("id").values_list(
                    "id", "team_id", "is_active"
                )
            ),
            "assignments": list(
                TeamAssignment.objects.order_by("id").values_list(
                    "id", "service_event_id", "ministry_team_id", "status"
                )
            ),
            "assignment_members": list(
                TeamAssignmentMember.objects.order_by("id").values_list(
                    "id", "assignment_id", "membership_id"
                )
            ),
            "log_entries": LogEntry.objects.count(),
            "notifications": Notification.objects.count(),
        }

    def test_staff_and_superuser_allowed_but_nonstaff_authorities_denied(self):
        for user in (self.staff, self.superuser):
            with self.subTest(user=user.username):
                self.client.force_login(user)
                self.assertEqual(
                    self.client.get(
                        reverse("team_roster_column_mapping_review")
                    ).status_code,
                    200,
                )
        for user in (
            self.other,
            self.exact_lead,
            self.exact_coordinator,
            self.global_manager,
            self.event_planner,
            self.membership_only,
            self.audience_only,
        ):
            with self.subTest(user=user.username), patch(
                "ministry.permissions.has_capability", return_value=True
            ):
                self.client.force_login(user)
                self.assertEqual(
                    self.client.get(
                        reverse("team_roster_column_mapping_review")
                    ).status_code,
                    403,
                )
                self.assertEqual(
                    self.client.post(
                        reverse("team_roster_column_mapping_review"),
                        {
                            "team_roster_action": "confirm",
                            "signed_reviewed_person_state": "forged",
                            "signed_assignment_preview_state": "forged",
                            "signed_confirmation_state": "forged",
                        },
                    ).status_code,
                    403,
                )

    @override_settings(CMS_ENABLED_INTEGRATIONS=[])
    def test_disabled_integration_fails_before_parser_form_or_database_query(self):
        request = RequestFactory().post("/team-roster/")
        request.user = self.staff
        request._files = {"workbook": self.upload()}
        with (
            patch(
                "ministry.services.team_roster_column_mapping.inventory_team_roster_columns"
            ) as inventory,
            patch("ministry.views.TeamRosterWorkbookUploadForm") as upload_form,
            self.assertNumQueries(0),
            self.assertRaises(Http404),
        ):
            team_roster_column_mapping_review(request)
        inventory.assert_not_called()
        upload_form.assert_not_called()

    def test_inventory_scopes_render_locked_candidates_and_other_profile_columns(self):
        response, review = self.upload_review()
        by_column = {row.column: row for row in review.columns}
        self.assertEqual(tuple(by_column), tuple("ABCDEFGHIJKLMNO"))
        self.assertContains(response, "Owns date and target-event identity")
        self.assertContains(response, "Owned by the existing Worship rotation flow")
        self.assertContains(response, "Not mappable in this Bethany import", count=6)
        self.assertContains(response, "<strong>Locked</strong>", count=2, html=True)
        self.assertEqual(
            tuple(row.column for row in review.columns if row.is_candidate),
            tuple("CDEFGHI"),
        )

    def test_every_current_active_assignable_canonical_team_is_available_in_localized_order(self):
        _response, review = self.upload_review()
        option_ids = [option.team_id for option in review.destination_options]
        self.assertCountEqual(
            option_ids,
            [self.projection.pk, self.sound.pk, self.video.pk, self.other_team.pk],
        )
        self.assertNotIn(self.inactive.pk, option_ids)
        self.assertNotIn(self.nonassignable.pk, option_ids)
        self.assertNotIn(self.unkeyed.pk, option_ids)
        self.assertNotIn(self.malformed.pk, option_ids)
        labels = [option.display_name for option in review.destination_options]
        self.assertEqual(labels, sorted(labels, key=str.casefold))

    def test_exact_hints_prefill_but_case_spacing_and_fuzzy_headers_do_not(self):
        _response, review = self.upload_review()
        by_column = {row.column: row for row in review.columns}
        self.assertEqual(by_column["E"].prefill_team_id, self.projection.pk)
        self.assertEqual(by_column["F"].prefill_team_id, self.sound.pk)
        self.assertEqual(by_column["H"].prefill_team_id, self.video.pk)
        for header in ("sound", "Sound ", "sounder"):
            with self.subTest(header=repr(header)):
                _response, variant = self.upload_review(f3=header)
                row = {item.column: item for item in variant.columns}["F"]
                self.assertIsNone(row.prefill_team_id)
                self.assertIsNone(row.hint_team_key)

    def test_missing_or_inactive_hint_never_falls_back(self):
        MinistryTeam.objects.filter(pk=self.sound.pk).update(is_active=False)
        response, review = self.upload_review()
        sound_row = {row.column: row for row in review.columns}["F"]
        self.assertIsNone(sound_row.prefill_team_id)
        self.assertEqual(sound_row.hint_warning, "inactive")
        self.assertContains(response, "no fallback team was selected")
        self.assertNotEqual(
            response.context["mapping_form"]["mapping_F"].value(),
            str(self.other_team.pk),
        )

    def test_unknown_header_defaults_ignore_and_ignore_is_valid(self):
        response, review = self.upload_review(f3="sounder")
        self.assertEqual(response.context["mapping_form"]["mapping_F"].value(), None)
        complete = self.client.post(
            reverse("team_roster_column_mapping_review"),
            self.mapping_post(review),
        )
        result = complete.context["reviewed_mapping"]
        self.assertIsNotNone(result)
        self.assertEqual(result.mapped_count, 0)
        self.assertEqual(result.ignored_count, 7)
        self.assertContains(complete, "Column mapping reviewed")
        self.assertContains(complete, "Re-upload the same workbook to continue")

    def test_sounder_and_arbitrary_candidate_can_be_mapped_manually(self):
        _response, review = self.upload_review(f3="sounder")
        complete = self.client.post(
            reverse("team_roster_column_mapping_review"),
            self.mapping_post(
                review,
                F=self.sound.pk,
                C=self.other_team.pk,
            ),
        )
        result = complete.context["reviewed_mapping"]
        self.assertIsNotNone(result)
        by_column = {choice.column: choice for choice in result.choices}
        self.assertEqual(by_column["F"].destination_team_key, self.sound.team_key)
        self.assertEqual(
            by_column["C"].destination_team_key, self.other_team.team_key
        )

    def test_duplicate_destination_team_is_blocked_bilingually(self):
        _response, review = self.upload_review(f3="sounder")
        response = self.client.post(
            reverse("team_roster_column_mapping_review"),
            self.mapping_post(review, E=self.sound.pk, F=self.sound.pk),
        )
        self.assertIsNone(response.context["reviewed_mapping"])
        self.assertContains(response, "selected by only one workbook column")
        self.set_language("zh")
        response = self.client.post(
            reverse("team_roster_column_mapping_review"),
            self.mapping_post(review, E=self.sound.pk, F=self.sound.pk),
        )
        self.assertContains(response, "同一个目标团队最多只能由一个工作簿列选择")

    def test_forged_structural_other_profile_and_unknown_coordinates_are_blocked(self):
        for forged_field in ("mapping_A", "mapping_B", "mapping_J", "mapping_Z"):
            with self.subTest(field=forged_field):
                _response, review = self.upload_review()
                data = self.mapping_post(review)
                data[forged_field] = str(self.sound.pk)
                response = self.client.post(
                    reverse("team_roster_column_mapping_review"), data
                )
                self.assertIsNone(response.context["reviewed_mapping"])
                self.assertContains(
                    response,
                    "Locked, other-service, and unknown column coordinates cannot be mapped.",
                )

    def test_inactive_nonassignable_and_unoffered_team_ids_are_rejected(self):
        for team in (self.inactive, self.nonassignable, self.unkeyed, self.malformed):
            with self.subTest(team=team.name):
                _response, review = self.upload_review()
                response = self.client.post(
                    reverse("team_roster_column_mapping_review"),
                    self.mapping_post(review, C=team.pk),
                )
                self.assertIsNone(response.context["reviewed_mapping"])
                self.assertContains(response, "Select a valid choice")

    def test_changed_team_key_rejects_the_signed_id_key_identity(self):
        _response, review = self.upload_review(f3="sounder")
        MinistryTeam.objects.filter(pk=self.sound.pk).update(
            team_key="main.cm.digital.sound.changed"
        )
        with self.assertRaises(TeamRosterColumnMappingValidationError):
            finalize_team_roster_column_mapping(
                review=review,
                selected_team_ids={
                    **{column: None for column in "CDEFGHI"},
                    "F": self.sound.pk,
                },
                user=self.staff,
            )

    def test_changed_header_tamper_wrong_user_and_expiry_are_blocked(self):
        _response, review = self.upload_review()
        payload = signing.loads(
            review.signed_inventory_state, salt=INVENTORY_SIGNING_SALT
        )
        payload["columns"][5]["header"] = "changed"
        changed = signing.dumps(
            payload, salt=INVENTORY_SIGNING_SALT, compress=True
        )
        cases = (
            (changed, self.staff, None),
            (review.signed_inventory_state[:-2] + "xx", self.staff, None),
            (review.signed_inventory_state, self.other, None),
            (review.signed_inventory_state, self.staff, -1),
        )
        for token, user, max_age in cases:
            with self.subTest(user=user.username, max_age=max_age), self.assertRaises(
                TeamRosterColumnMappingStateError
            ):
                kwargs = {"token": token, "user": user}
                if max_age is not None:
                    kwargs["max_age"] = max_age
                decode_team_roster_column_mapping_review(**kwargs)

        response = self.client.post(
            reverse("team_roster_column_mapping_review"),
            {
                "signed_column_inventory_state": (
                    review.signed_inventory_state[:-2] + "xx"
                )
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "invalid, expired, or stale")
        self.assertContains(response, "Upload the workbook again")

    def test_stale_event_target_evidence_is_blocked(self):
        _response, review = self.upload_review()
        ServiceEvent.objects.filter(pk=self.events[0].pk).update(
            status=ServiceEvent.STATUS_DRAFT
        )
        with self.assertRaises(TeamRosterColumnMappingStateError):
            decode_team_roster_column_mapping_review(
                review.signed_inventory_state, user=self.staff
            )

    def test_blocked_target_inventory_renders_but_cannot_mint_reviewed_authority(self):
        ServiceEvent.objects.filter(pk=self.events[0].pk).delete()
        response, review = self.upload_review()
        self.assertFalse(review.target_gate_ready)
        self.assertContains(response, "visible for diagnosis")
        self.assertContains(response, "disabled aria-disabled=\"true\"", html=False)
        response = self.client.post(
            reverse("team_roster_column_mapping_review"),
            self.mapping_post(review),
        )
        self.assertIsNone(response.context["reviewed_mapping"])
        self.assertContains(response, "no next-stage authority was minted")

    def test_signed_states_are_bounded_private_and_distinct(self):
        content = self.workbook_content(sound_overrides={4: "Private Person Name"})
        review = prepare_team_roster_column_mapping_review(
            content=content,
            filename="private.xlsx",
            user=self.staff,
            language="en",
        )
        self.assertLessEqual(review.signed_state_bytes, MAX_COLUMN_MAPPING_STATE_BYTES)
        inventory_payload = signing.loads(
            review.signed_inventory_state, salt=INVENTORY_SIGNING_SALT
        )
        serialized = json.dumps(inventory_payload, ensure_ascii=False)
        self.assertEqual(
            inventory_payload["contract_version"],
            TEAM_ROSTER_COLUMN_MAPPING_REVIEW_V1,
        )
        self.assertNotIn("Private Person Name", serialized)
        self.assertNotIn("membership", serialized.lower())
        self.assertNotIn("email", serialized.lower())
        self.assertNotIn("phone", serialized.lower())
        self.assertNotIn("confirmation", serialized.lower())

        reviewed = finalize_team_roster_column_mapping(
            review=review,
            selected_team_ids={
                **{column: None for column in "CDEFGHI"},
                "F": self.sound.pk,
            },
            user=self.staff,
        )
        self.assertLessEqual(reviewed.signed_state_bytes, MAX_COLUMN_MAPPING_STATE_BYTES)
        reviewed_payload = signing.loads(
            reviewed.signed_reviewed_state, salt=REVIEWED_SIGNING_SALT
        )
        self.assertEqual(
            reviewed_payload["contract_version"],
            TEAM_ROSTER_REVIEWED_COLUMN_MAPPING_V1,
        )
        mapped = {
            item["column"]: item for item in reviewed_payload["reviewed_mappings"]
        }
        self.assertEqual(mapped["F"]["destination_team_id"], self.sound.pk)
        self.assertEqual(
            mapped["F"]["destination_team_key"], self.sound.team_key
        )
        self.assertIsNone(mapped["C"]["destination_team_id"])
        self.assertNotIn(
            "Private Person Name",
            json.dumps(reviewed_payload, ensure_ascii=False),
        )

    def test_upload_and_review_query_no_membership_or_assignment_table(self):
        self.client.force_login(self.staff)
        self.set_language("en")
        with CaptureQueriesContext(connection) as queries:
            response = self.client.post(
                reverse("team_roster_column_mapping_review"),
                {"workbook": self.upload()},
            )
            review = response.context["mapping_review"]
            mapped_response = self.client.post(
                reverse("team_roster_column_mapping_review"),
                self.mapping_post(review, F=self.sound.pk),
            )
        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(mapped_response.context["reviewed_mapping"])
        sql = "\n".join(query["sql"].lower() for query in queries)
        self.assertNotIn("ministry_teammembership", sql)
        self.assertNotIn("ministry_teamassignment", sql)
        self.assertNotIn("ministry_teamassignmentmember", sql)

    def test_upload_and_mapping_post_are_zero_write(self):
        before = self.domain_snapshot()
        _response, review = self.upload_review(f3="sounder")
        response = self.client.post(
            reverse("team_roster_column_mapping_review"),
            self.mapping_post(review, F=self.sound.pk),
        )
        self.assertIsNotNone(response.context["reviewed_mapping"])
        self.assertEqual(self.domain_snapshot(), before)

    def test_bilingual_copy_and_mobile_table_structure_render(self):
        self.client.force_login(self.staff)
        self.set_language("en")
        response = self.client.get(reverse("team_roster_column_mapping_review"))
        self.assertContains(response, "Team Roster Import")
        self.set_language("zh")
        response = self.client.post(
            reverse("team_roster_column_mapping_review"),
            {"workbook": self.upload(f3="sounder")},
        )
        self.assertContains(response, "团队名单导入")
        self.assertContains(response, "未知或未提示的表头默认忽略")
        self.assertContains(response, 'class="sound-preview-table"', html=False)
        self.assertContains(response, "data-label=", html=False)
