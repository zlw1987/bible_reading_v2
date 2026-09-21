"""Focused MO-S.6F.GENERAL.1D ZERO-WRITE person-mapping tests."""

from datetime import datetime
import json
from unittest.mock import patch

from django.contrib.admin.models import LogEntry
from django.contrib.auth.models import User
from django.core import signing
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from events.models import ServiceEvent, ServiceEventAudienceScope
from events.test_worship_xlsx_preview import (
    WorshipWorkbookDomainTestBase,
    build_known_workbook,
)
from notifications.models import Notification
from core.integration_registry import IntegrationDisabled

from .models import (
    MinistryTeam,
    TeamAssignment,
    TeamAssignmentMember,
    TeamMembership,
)
from .services.team_roster_column_mapping import (
    REVIEWED_SIGNING_SALT,
    TeamRosterColumnMappingStateError,
    decode_reviewed_team_roster_column_mapping,
    finalize_team_roster_column_mapping,
    prepare_team_roster_column_mapping_review,
)
from .services.team_roster_person_mapping import (
    MAX_PERSON_MAPPING_STATE_BYTES,
    PERSON_INPUT_SIGNING_SALT,
    PERSON_REVIEWED_SIGNING_SALT,
    TEAM_ROSTER_PERSON_MAPPING_REVIEW_V1,
    TeamRosterPersonMappingStateError,
    TeamRosterPersonMappingValidationError,
    TeamRosterWorkbookMismatch,
    decode_reviewed_team_roster_person_mapping,
    decode_team_roster_person_mapping_input,
    finalize_team_roster_person_mapping,
    prepare_team_roster_person_mapping,
)
from .services.team_roster_workbook import TeamRosterCellState
from .services.worship_xlsx_preview import INTEGRATION_KEY


@override_settings(CMS_ENABLED_INTEGRATIONS=[INTEGRATION_KEY])
class TeamRosterPersonMappingTests(WorshipWorkbookDomainTestBase):
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
            ServiceEventAudienceScope.objects.create(service_event=event, unit=cls.cm)
            cls.events.append(event)

        cls.sound = MinistryTeam.objects.create(
            name="音控团队",
            name_en="Sound Team",
            team_key="main.cm.digital.sound",
        )
        cls.projection = MinistryTeam.objects.create(
            name="投影团队",
            name_en="Projection Team",
            team_key="main.cm.digital.projection",
        )
        cls.video = MinistryTeam.objects.create(
            name="视频团队",
            name_en="Video Team",
            team_key="main.cm.digital.video",
        )

        cls.nelson_user = User.objects.create_user(
            "nelson.user", password="pw", first_name="Nelson"
        )
        cls.nelson = TeamMembership.objects.create(
            team=cls.sound,
            user=cls.nelson_user,
            display_name="Nelson",
            email="private-nelson@example.test",
            notes="private membership note",
        )
        cls.bob = TeamMembership.objects.create(
            team=cls.sound, display_name="Bob"
        )
        cls.lower_aaron = TeamMembership.objects.create(
            team=cls.sound, display_name="aaron"
        )
        cls.inactive_user = User.objects.create_user(
            "dormant.user", password="pw", is_active=False
        )
        cls.dormant = TeamMembership.objects.create(
            team=cls.sound,
            user=cls.inactive_user,
            display_name="Dormant",
        )
        cls.inactive_membership = TeamMembership.objects.create(
            team=cls.sound, display_name="Inactive Membership", is_active=False
        )
        cls.projection_nelson = TeamMembership.objects.create(
            team=cls.projection, display_name="Nelson"
        )
        cls.superuser = User.objects.create_user(
            "person-super", password="pw", is_superuser=True, is_staff=False
        )

    def set_language(self, language):
        session = self.client.session
        session["language"] = language
        session.save()

    def workbook(self, **kwargs):
        return build_known_workbook(
            header_overrides={"H": "Video"},
            **kwargs,
        )

    def reviewed_columns(self, content, **mapped):
        review = prepare_team_roster_column_mapping_review(
            content=content,
            filename="review.xlsx",
            user=self.staff,
            language="en",
        )
        selections = {column: None for column in "CDEFGHI"}
        selections.update({column: team.pk for column, team in mapped.items()})
        return finalize_team_roster_column_mapping(
            review=review,
            selected_team_ids=selections,
            user=self.staff,
            language="en",
        )

    def person_review(self, content, **mapped):
        reviewed = self.reviewed_columns(content, **mapped)
        person = prepare_team_roster_person_mapping(
            content=content,
            filename="second-name-does-not-matter.xlsx",
            reviewed_column_state=reviewed.signed_reviewed_state,
            user=self.staff,
            language="en",
        )
        return reviewed, person

    def group(self, person, team):
        return next(group for group in person.groups if group.team_id == team.pk)

    def domain_snapshot(self):
        return {
            "events": list(
                ServiceEvent.objects.order_by("id").values_list(
                    "id", "scheduling_revision", "status"
                )
            ),
            "teams": list(
                MinistryTeam.objects.order_by("id").values_list(
                    "id", "team_key", "is_active", "is_assignable"
                )
            ),
            "memberships": list(
                TeamMembership.objects.order_by("id").values_list(
                    "id", "team_id", "user_id", "is_active", "updated_at"
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
            "logs": LogEntry.objects.count(),
            "notifications": Notification.objects.count(),
        }

    def test_same_workbook_reupload_is_required_and_filename_is_not_authority(self):
        content = self.workbook(sound_overrides={4: "Nelson"})
        reviewed = self.reviewed_columns(content, F=self.sound)
        accepted = prepare_team_roster_person_mapping(
            content=content,
            filename="renamed.xlsx",
            reviewed_column_state=reviewed.signed_reviewed_state,
            user=self.staff,
        )
        self.assertEqual(accepted.workbook_sha256, reviewed.workbook_sha256)
        with self.assertRaises(TeamRosterWorkbookMismatch):
            prepare_team_roster_person_mapping(
                content=self.workbook(sound_overrides={4: "Bob"}),
                filename="review.xlsx",
                reviewed_column_state=reviewed.signed_reviewed_state,
                user=self.staff,
            )

    def test_only_mapped_columns_are_parsed_and_only_their_teams_are_queried(self):
        content = self.workbook(
            projection_overrides={4: "Ignored / Ignored"},
            sound_overrides={4: "Nelson"},
        )
        reviewed = self.reviewed_columns(content, F=self.sound)
        from .services import team_roster_person_mapping as service

        with (
            patch.object(
                service,
                "parse_team_roster_cell",
                wraps=service.parse_team_roster_cell,
            ) as parser,
            patch.object(
                service,
                "_current_candidates_by_team",
                wraps=service._current_candidates_by_team,
            ) as candidates,
        ):
            person = prepare_team_roster_person_mapping(
                content=content,
                filename="review.xlsx",
                reviewed_column_state=reviewed.signed_reviewed_state,
                user=self.staff,
            )
        self.assertEqual(parser.call_count, 52)
        self.assertEqual(candidates.call_args.args[0], (self.sound.pk,))
        self.assertTrue(all(cell.column == "F" for cell in person.cells))
        self.assertTrue(
            all(cell.source_cell[0] not in "ABEJ KLMNO".replace(" ", "") for cell in person.cells)
        )
        self.assertNotIn("Ignored", {token for cell in person.cells for token in cell.normalized_tokens})

    def test_generic_parser_covers_blank_one_to_many_and_resource_guard(self):
        sixteen = " / ".join(f"Person {index}" for index in range(16))
        seventeen = " / ".join(f"Person {index}" for index in range(17))
        cases = {
            None: TeamRosterCellState.NO_SOURCE_PROPOSAL,
            "One": TeamRosterCellState.SUPPORTED_LITERAL,
            "One / Two": TeamRosterCellState.SUPPORTED_LITERAL,
            "One / Two / Three": TeamRosterCellState.SUPPORTED_LITERAL,
            "One / Two / Three / Four": TeamRosterCellState.SUPPORTED_LITERAL,
            sixteen: TeamRosterCellState.SUPPORTED_LITERAL,
            seventeen: TeamRosterCellState.TOO_MANY_MEMBERS,
            "One / One": TeamRosterCellState.DUPLICATE_TOKEN,
            "One / / Two": TeamRosterCellState.EMPTY_SEGMENT,
            "One, Two": TeamRosterCellState.UNSUPPORTED_SYNTAX,
            "=1+1": TeamRosterCellState.FORMULA_BLOCKED,
        }
        for value, expected in cases.items():
            with self.subTest(value=value):
                overrides = {} if value is None else {4: value}
                _reviewed, person = self.person_review(
                    self.workbook(sound_overrides=overrides), F=self.sound
                )
                cell = next(item for item in person.cells if item.source_cell == "F4")
                self.assertEqual(cell.parsed_state, expected)

    def test_exact_prefill_manual_ambiguity_inactive_user_and_display_only_policy(self):
        TeamMembership.objects.create(team=self.sound, display_name="Twin")
        TeamMembership.objects.create(team=self.sound, display_name="Twin")
        content = self.workbook(
            sound_overrides={4: "Nelson / Bob / Aaron / Dormant / Twin / Missing"}
        )
        _reviewed, person = self.person_review(content, F=self.sound)
        group = self.group(person, self.sound)
        by_token = {item.token: item for item in group.token_reviews}
        self.assertEqual(by_token["Nelson"].prefill_membership_id, self.nelson.pk)
        self.assertEqual(by_token["Bob"].prefill_membership_id, self.bob.pk)
        self.assertIsNone(by_token["Aaron"].prefill_membership_id)
        self.assertIsNone(by_token["Dormant"].prefill_membership_id)
        self.assertIsNone(by_token["Missing"].prefill_membership_id)
        self.assertEqual(
            by_token["Twin"].review_state, "ambiguous_manual_review_required"
        )
        candidate_ids = {item.membership_id for item in group.candidates}
        self.assertIn(self.bob.pk, candidate_ids)
        self.assertNotIn(self.dormant.pk, candidate_ids)
        self.assertEqual(group.diagnostic_inactive_user_count, 1)

    def test_same_token_is_scoped_separately_per_destination_team(self):
        content = self.workbook(
            projection_overrides={4: "Nelson"},
            sound_overrides={4: "Nelson"},
        )
        _reviewed, person = self.person_review(
            content, E=self.projection, F=self.sound
        )
        projection_review = self.group(person, self.projection).token_reviews[0]
        sound_review = self.group(person, self.sound).token_reviews[0]
        self.assertEqual(
            projection_review.prefill_membership_id, self.projection_nelson.pk
        )
        self.assertEqual(sound_review.prefill_membership_id, self.nelson.pk)

    def test_explicit_selection_rejects_cross_team_inactive_user_and_duplicate_roster_id(self):
        content = self.workbook(sound_overrides={4: "Nelson / Bob"})
        reviewed, person = self.person_review(content, F=self.sound)
        common = {
            "input_state": person.signed_input_state,
            "reviewed_column_state": reviewed.signed_reviewed_state,
            "user": self.staff,
        }
        with self.assertRaises(TeamRosterPersonMappingValidationError):
            finalize_team_roster_person_mapping(
                **common,
                selected_membership_ids={
                    (self.sound.pk, "Nelson"): self.nelson.pk,
                    (self.sound.pk, "Bob"): self.nelson.pk,
                },
            )
        with self.assertRaises(TeamRosterPersonMappingValidationError):
            finalize_team_roster_person_mapping(
                **common,
                selected_membership_ids={
                    (self.sound.pk, "Nelson"): self.projection_nelson.pk,
                    (self.sound.pk, "Bob"): self.bob.pk,
                },
            )
        with self.assertRaises(TeamRosterPersonMappingValidationError):
            finalize_team_roster_person_mapping(
                **common,
                selected_membership_ids={
                    (self.sound.pk, "Nelson"): self.inactive_membership.pk,
                    (self.sound.pk, "Bob"): self.bob.pk,
                },
            )
        with self.assertRaises(TeamRosterPersonMappingValidationError):
            finalize_team_roster_person_mapping(
                **common,
                selected_membership_ids={
                    (self.sound.pk, "Nelson"): self.dormant.pk,
                    (self.sound.pk, "Bob"): self.bob.pk,
                },
            )

    def test_final_review_is_signed_bounded_private_and_revalidates_current_truth(self):
        content = self.workbook(sound_overrides={4: "Nelson / Bob"})
        reviewed, person = self.person_review(content, F=self.sound)
        result = finalize_team_roster_person_mapping(
            input_state=person.signed_input_state,
            reviewed_column_state=reviewed.signed_reviewed_state,
            selected_membership_ids={
                (self.sound.pk, "Nelson"): self.nelson.pk,
                (self.sound.pk, "Bob"): self.bob.pk,
            },
            user=self.staff,
        )
        self.assertLessEqual(result.signed_state_bytes, MAX_PERSON_MAPPING_STATE_BYTES)
        payload = signing.loads(
            result.signed_reviewed_state, salt=PERSON_REVIEWED_SIGNING_SALT
        )
        serialized = json.dumps(payload, ensure_ascii=False)
        self.assertEqual(
            payload["contract_version"], TEAM_ROSTER_PERSON_MAPPING_REVIEW_V1
        )
        self.assertIn("Nelson", serialized)
        for private in (
            "private-nelson@example.test",
            "private membership note",
            "phone",
            "confirmation_note",
            "assignment_note",
        ):
            self.assertNotIn(private, serialized)
        decoded = decode_reviewed_team_roster_person_mapping(
            result.signed_reviewed_state, user=self.staff
        )
        self.assertEqual(len(decoded["reviewed_selections"]), 2)
        for token, user, max_age in (
            (result.signed_reviewed_state[:-2] + "xx", self.staff, None),
            (result.signed_reviewed_state, self.superuser, None),
            (result.signed_reviewed_state, self.staff, -1),
        ):
            with self.subTest(user=user.username, max_age=max_age), self.assertRaises(
                TeamRosterPersonMappingStateError
            ):
                kwargs = {"token": token, "user": user}
                if max_age is not None:
                    kwargs["max_age"] = max_age
                decode_reviewed_team_roster_person_mapping(**kwargs)
        TeamMembership.objects.filter(pk=self.nelson.pk).update(display_name="Changed")
        with self.assertRaises(TeamRosterPersonMappingStateError):
            decode_reviewed_team_roster_person_mapping(
                result.signed_reviewed_state, user=self.staff
            )

    def test_full_52_row_seven_team_evidence_stays_within_existing_bound(self):
        extra = [
            MinistryTeam.objects.create(
                name=f"Extra {index}",
                team_key=f"main.cm.extra.{index}",
            )
            for index in range(4)
        ]
        content = self.workbook(
            projection_overrides={4: "Nelson"},
            sound_overrides={4: "Nelson"},
        )
        mapped = {
            "C": extra[0],
            "D": extra[1],
            "E": self.projection,
            "F": self.sound,
            "G": extra[2],
            "H": self.video,
            "I": extra[3],
        }
        reviewed, person = self.person_review(content, **mapped)
        self.assertEqual(len(person.cells), 52 * 7)
        self.assertLessEqual(person.signed_state_bytes, MAX_PERSON_MAPPING_STATE_BYTES)
        result = finalize_team_roster_person_mapping(
            input_state=person.signed_input_state,
            reviewed_column_state=reviewed.signed_reviewed_state,
            selected_membership_ids={
                (self.projection.pk, "Nelson"): self.projection_nelson.pk,
                (self.sound.pk, "Nelson"): self.nelson.pk,
            },
            user=self.staff,
        )
        self.assertLessEqual(result.signed_state_bytes, MAX_PERSON_MAPPING_STATE_BYTES)

    def test_tamper_wrong_user_expiry_team_membership_and_event_drift_fail_closed(self):
        content = self.workbook(sound_overrides={4: "Nelson"})
        reviewed, person = self.person_review(content, F=self.sound)
        cases = (
            (person.signed_input_state[:-2] + "xx", self.staff, None),
            (person.signed_input_state, self.superuser, None),
            (person.signed_input_state, self.staff, -1),
        )
        for token, user, max_age in cases:
            with self.subTest(user=user.username, max_age=max_age), self.assertRaises(
                TeamRosterPersonMappingStateError
            ):
                kwargs = {
                    "token": token,
                    "reviewed_column_state": reviewed.signed_reviewed_state,
                    "user": user,
                }
                if max_age is not None:
                    kwargs["max_age"] = max_age
                decode_team_roster_person_mapping_input(**kwargs)

        MinistryTeam.objects.filter(pk=self.sound.pk).update(is_active=False)
        with self.assertRaises((TeamRosterPersonMappingStateError, TeamRosterColumnMappingStateError)):
            decode_team_roster_person_mapping_input(
                person.signed_input_state,
                reviewed_column_state=reviewed.signed_reviewed_state,
                user=self.staff,
            )
        MinistryTeam.objects.filter(pk=self.sound.pk).update(is_active=True)
        original_updated_at = self.nelson.updated_at
        TeamMembership.objects.filter(pk=self.nelson.pk).update(
            updated_at=timezone.now()
        )
        with self.assertRaises(TeamRosterPersonMappingStateError):
            decode_team_roster_person_mapping_input(
                person.signed_input_state,
                reviewed_column_state=reviewed.signed_reviewed_state,
                user=self.staff,
            )
        TeamMembership.objects.filter(pk=self.nelson.pk).update(
            updated_at=original_updated_at
        )
        TeamMembership.objects.filter(pk=self.nelson.pk).update(is_active=False)
        with self.assertRaises(TeamRosterPersonMappingStateError):
            decode_team_roster_person_mapping_input(
                person.signed_input_state,
                reviewed_column_state=reviewed.signed_reviewed_state,
                user=self.staff,
            )
        TeamMembership.objects.filter(pk=self.nelson.pk).update(is_active=True)
        ServiceEvent.objects.filter(pk=self.events[0].pk).update(
            scheduling_revision=99
        )
        with self.assertRaises((TeamRosterPersonMappingStateError, TeamRosterColumnMappingStateError)):
            decode_team_roster_person_mapping_input(
                person.signed_input_state,
                reviewed_column_state=reviewed.signed_reviewed_state,
                user=self.staff,
            )

    def test_reviewed_column_decoder_rejects_extra_keys_and_duplicate_team_mapping(self):
        content = self.workbook(sound_overrides={4: "Nelson"})
        reviewed = self.reviewed_columns(content, F=self.sound)
        payload = signing.loads(
            reviewed.signed_reviewed_state, salt=REVIEWED_SIGNING_SALT
        )
        payload["extra"] = True
        with self.assertRaises(TeamRosterColumnMappingStateError):
            decode_reviewed_team_roster_column_mapping(
                signing.dumps(payload, salt=REVIEWED_SIGNING_SALT, compress=True),
                user=self.staff,
            )
        payload.pop("extra")
        payload["reviewed_mappings"][0]["destination_team_id"] = self.sound.pk
        payload["reviewed_mappings"][0]["destination_team_key"] = self.sound.team_key
        with self.assertRaises(TeamRosterColumnMappingStateError):
            decode_reviewed_team_roster_column_mapping(
                signing.dumps(payload, salt=REVIEWED_SIGNING_SALT, compress=True),
                user=self.staff,
            )

    def test_person_mapping_queries_no_assignment_tables_and_writes_nothing(self):
        before = self.domain_snapshot()
        content = self.workbook(sound_overrides={4: "Nelson / Bob"})
        reviewed = self.reviewed_columns(content, F=self.sound)
        with CaptureQueriesContext(connection) as queries:
            person = prepare_team_roster_person_mapping(
                content=content,
                filename="review.xlsx",
                reviewed_column_state=reviewed.signed_reviewed_state,
                user=self.staff,
            )
            result = finalize_team_roster_person_mapping(
                input_state=person.signed_input_state,
                reviewed_column_state=reviewed.signed_reviewed_state,
                selected_membership_ids={
                    (self.sound.pk, "Nelson"): self.nelson.pk,
                    (self.sound.pk, "Bob"): self.bob.pk,
                },
                user=self.staff,
            )
        self.assertIsNotNone(result.signed_reviewed_state)
        sql = "\n".join(query["sql"].lower() for query in queries)
        self.assertNotIn("ministry_teamassignment\"", sql)
        self.assertNotIn("ministry_teamassignmentmember", sql)
        self.assertEqual(self.domain_snapshot(), before)

    @override_settings(CMS_ENABLED_INTEGRATIONS=[])
    def test_disabled_integration_blocks_before_person_parser_or_query(self):
        content = self.workbook(sound_overrides={4: "Nelson"})
        with (
            patch(
                "ministry.services.team_roster_person_mapping.decode_reviewed_team_roster_column_mapping"
            ) as decoder,
            patch(
                "ministry.services.team_roster_person_mapping.read_reviewed_team_roster_cells"
            ) as reader,
            self.assertNumQueries(0),
            self.assertRaises(IntegrationDisabled),
        ):
            prepare_team_roster_person_mapping(
                content=content,
                filename="review.xlsx",
                reviewed_column_state="unused",
                user=self.staff,
            )
        decoder.assert_not_called()
        reader.assert_not_called()

    def test_staff_and_superuser_allowed_nonstaff_denied(self):
        content = self.workbook(sound_overrides={4: "Nelson"})
        staff_reviewed = self.reviewed_columns(content, F=self.sound)
        prepare_team_roster_person_mapping(
            content=content,
            filename="review.xlsx",
            reviewed_column_state=staff_reviewed.signed_reviewed_state,
            user=self.staff,
        )
        super_review = prepare_team_roster_column_mapping_review(
            content=content, filename="review.xlsx", user=self.superuser
        )
        super_reviewed = finalize_team_roster_column_mapping(
            review=super_review,
            selected_team_ids={
                **{column: None for column in "CDEFGHI"},
                "F": self.sound.pk,
            },
            user=self.superuser,
        )
        prepare_team_roster_person_mapping(
            content=content,
            filename="review.xlsx",
            reviewed_column_state=super_reviewed.signed_reviewed_state,
            user=self.superuser,
        )
        with self.assertRaises(TeamRosterPersonMappingValidationError):
            prepare_team_roster_person_mapping(
                content=content,
                filename="review.xlsx",
                reviewed_column_state=staff_reviewed.signed_reviewed_state,
                user=self.other,
            )

    def test_english_desktop_and_chinese_mobile_workflow_copy(self):
        content = self.workbook(sound_overrides={4: "Nelson / Bob"})
        self.client.force_login(self.staff)
        self.set_language("en")
        upload = SimpleUploadedFile(
            "review.xlsx",
            content,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response = self.client.post(
            reverse("team_roster_column_mapping_review"), {"workbook": upload}
        )
        column_review = response.context["mapping_review"]
        data = {
            "signed_column_inventory_state": column_review.signed_inventory_state,
            **{f"mapping_{column}": "" for column in "CDEFGHI"},
            "mapping_F": str(self.sound.pk),
        }
        response = self.client.post(reverse("team_roster_column_mapping_review"), data)
        reviewed_state = response.context["reviewed_column_state"]
        self.assertContains(response, "Re-upload the same workbook to continue")
        response = self.client.post(
            reverse("team_roster_column_mapping_review"),
            {
                "signed_reviewed_column_state": reviewed_state,
                "workbook": SimpleUploadedFile("again.xlsx", content),
            },
        )
        self.assertContains(response, "Review Person / Team Membership Mapping")
        self.assertContains(response, 'class="sound-preview-table"', html=False)
        self.assertContains(response, "data-label=", html=False)
        form = response.context["person_form"]
        post = {
            "signed_reviewed_column_state": reviewed_state,
            "signed_person_mapping_input_state": response.context[
                "person_review"
            ].signed_input_state,
        }
        for field_name, (_team_id, token) in form._field_pairs.items():
            post[field_name] = str(self.nelson.pk if token == "Nelson" else self.bob.pk)
        response = self.client.post(reverse("team_roster_column_mapping_review"), post)
        self.assertContains(
            response,
            "Person mapping reviewed. A read-only Assignment Preview was generated.",
        )
        self.assertContains(response, "NOT YET APPLIED")
        self.assertContains(response, "There is no Confirm button")
        self.assertNotContains(response, "Confirm and Apply Team Roster Changes")
        self.set_language("zh")
        response = self.client.get(reverse("team_roster_column_mapping_review"))
        self.assertContains(response, "人员/团队成员映射复核")
