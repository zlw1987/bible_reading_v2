"""Focused MO-S.6F.2A Projection zero-write preview tests."""

from datetime import date, datetime, time
import os
from pathlib import Path
from unittest import skipUnless
from unittest.mock import patch

from django.contrib.admin.models import LogEntry
from django.contrib.auth.models import User
from django.core import signing
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import ChurchStructureMembership, ChurchStructureUnit
from accounts.permissions import CAP_MANAGE_TEAM_ASSIGNMENTS
from events.models import (
    ServiceEvent,
    ServiceEventAudienceScope,
    ServiceEventPlannerAssignment,
    ServiceEventRequiredTeam,
    ServiceProfile,
)
from events.test_worship_xlsx_preview import build_known_workbook
from notifications.models import Notification

from .models import (
    MinistryTeam,
    MinistryTeamRoleAssignment,
    MinistryTeamRoleType,
    TeamAssignment,
    TeamAssignmentMember,
    TeamMembership,
)
from .permissions import can_manage_team_assignments
from .services.projection_assignment_xlsx_preview import (
    INTEGRATION_KEY,
    MAPPING_SIGNING_SALT,
    PREVIEW_SIGNING_SALT,
    SOURCE_COLUMN,
    SOURCE_CONTRACT_REVISION,
    SVCA_PROJECTION_TEAM_KEY,
    ProjectionDestinationTeamError,
    ProjectionDestinationTeamErrorCode,
    ProjectionIdentityState,
    ProjectionMappingStateError,
    ProjectionMappingValidationError,
    ProjectionSourceState,
    ProjectionTargetState,
    SignedProjectionPreviewError,
    build_projection_assignment_preview,
    decode_projection_assignment_mapping,
    decode_signed_projection_assignment_preview,
    normalize_projection_identity,
    parse_known_projection_assignment_workbook,
    prepare_projection_assignment_mapping,
    resolve_projection_destination_team,
    user_can_preview_projection_assignments,
)


@override_settings(CMS_ENABLED_INTEGRATIONS=[INTEGRATION_KEY])
class ProjectionPreviewTestBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.profile = ServiceProfile.objects.create(
            key="bethany_0930_cm",
            name="Bethany 09:30",
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
        )
        cls.root = ChurchStructureUnit.objects.create(
            code="ROOT",
            name="Whole Church",
            name_en="Whole Church",
            unit_type=ChurchStructureUnit.UNIT_ROOT,
        )
        cls.cm = ChurchStructureUnit.objects.create(
            code="CM",
            name="Chinese Ministry",
            name_en="Chinese Ministry",
            unit_type=ChurchStructureUnit.UNIT_MINISTRY_CONTEXT,
            parent=cls.root,
        )
        cls.other_unit = ChurchStructureUnit.objects.create(
            code="OTHER",
            name="Other",
            name_en="Other",
            unit_type=ChurchStructureUnit.UNIT_MINISTRY_CONTEXT,
            parent=cls.root,
        )
        cls.projection = MinistryTeam.objects.create(
            name="投影团队",
            name_en="Projection Team",
            team_key=SVCA_PROJECTION_TEAM_KEY,
            is_active=True,
            is_assignable=True,
        )
        cls.other_team = MinistryTeam.objects.create(
            name="Sound Team", name_en="Sound Team", team_key="main.cm.digital.sound"
        )
        cls.staff = User.objects.create_user("projection_staff", password="pw", is_staff=True)
        cls.superuser = User.objects.create_superuser("projection_super", "super@example.test", "pw")
        cls.alice = User.objects.create_user("alice_projection", password="pw", first_name="Alice")
        cls.zhang = User.objects.create_user("zhang_projection", password="pw", first_name="张三")
        for user in (cls.alice, cls.zhang):
            ChurchStructureMembership.objects.create(
                user=user,
                unit=cls.cm,
                status=ChurchStructureMembership.STATUS_ACTIVE,
                is_primary=True,
                start_date=date(2020, 1, 1),
            )
        cls.alice_membership = TeamMembership.objects.create(
            team=cls.projection,
            user=cls.alice,
            display_name="Alice",
            email="private-alice@example.test",
            notes="private Alice note",
        )
        cls.zhang_membership = TeamMembership.objects.create(
            team=cls.projection,
            user=cls.zhang,
            display_name="张三",
            email="private-zhang@example.test",
            notes="private Zhang note",
        )
        cls.display_only = TeamMembership.objects.create(
            team=cls.projection,
            display_name="José Mixed姓名",
            email="private-display@example.test",
            notes="private display-only note",
        )

    def workbook(self, projection_overrides=None, **kwargs):
        return build_known_workbook(
            projection_overrides=projection_overrides or {}, **kwargs
        )

    def upload(self, projection_overrides=None):
        return SimpleUploadedFile(
            "annual.xlsx",
            self.workbook(projection_overrides),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    def event_for_row(self, row_index=0, **overrides):
        row_number = [4, *range(6, 57)][row_index]
        local_date = datetime(2026, 1, 4) + timezone.timedelta(weeks=row_index)
        values = {
            "title": f"Sunday {row_number}",
            "title_en": f"Sunday {row_number}",
            "service_profile": self.profile,
            "event_type": ServiceEvent.EVENT_SUNDAY_SERVICE,
            "start_datetime": timezone.make_aware(
                datetime.combine(local_date.date(), time(9, 30)),
                timezone.get_current_timezone(),
            ),
            "status": ServiceEvent.STATUS_PUBLISHED,
        }
        values.update(overrides)
        event = ServiceEvent.objects.create(**values)
        ServiceEventAudienceScope.objects.create(service_event=event, unit=self.cm)
        return event

    def preview_now(self):
        return timezone.make_aware(datetime(2026, 1, 4, 8), timezone.get_current_timezone())

    def mapping_review(self, literal="Alice"):
        return prepare_projection_assignment_mapping(
            content=self.workbook({4: literal}), filename="annual.xlsx", user=self.staff
        )

    def preview(self, literal="Alice", mapping=None, now=None):
        review = self.mapping_review(literal)
        if mapping is None:
            mapping = {"Alice": self.alice_membership.pk}
        return build_projection_assignment_preview(
            mapping_review=review,
            selected_mapping=mapping,
            user=self.staff,
            now=now or self.preview_now(),
        )

    def assignment(self, event, members=(), **overrides):
        values = {
            "service_event": event,
            "ministry_team": self.projection,
            "status": TeamAssignment.STATUS_SCHEDULED,
            "notes": "private assignment note",
        }
        values.update(overrides)
        assignment = TeamAssignment.objects.create(**values)
        for membership in members:
            TeamAssignmentMember.objects.create(
                assignment=assignment,
                membership=membership,
                confirmation_note="private confirmation note",
            )
        return assignment


class ProjectionSourceGrammarTests(ProjectionPreviewTestBase):
    def test_one_and_two_person_literals_outer_trim_and_nfc(self):
        parsed = parse_known_projection_assignment_workbook(
            self.workbook({4: "  Jose\u0301  ", 6: "  Alice / 张三  "})
        )
        self.assertEqual(parsed.rows[0].source_cell, "E4")
        self.assertEqual(parsed.rows[0].normalized_tokens, ("José",))
        self.assertEqual(parsed.rows[1].normalized_tokens, ("Alice", "张三"))
        self.assertEqual(normalize_projection_identity("  A  B  "), "A  B")

    def test_chinese_and_mixed_script_tokens_are_literal_identity_text(self):
        parsed = parse_known_projection_assignment_workbook(
            self.workbook({4: "张三", 6: "José Mixed姓名"})
        )
        self.assertEqual(parsed.rows[0].source_state, ProjectionSourceState.SUPPORTED_LITERAL)
        self.assertEqual(parsed.rows[1].source_state, ProjectionSourceState.SUPPORTED_LITERAL)

    def test_blank_is_no_source_proposal(self):
        parsed = parse_known_projection_assignment_workbook(self.workbook({4: "   "}))
        self.assertEqual(parsed.rows[0].source_state, ProjectionSourceState.NO_SOURCE_PROPOSAL)

    def test_empty_segments_three_segments_and_duplicate_tokens_block(self):
        parsed = parse_known_projection_assignment_workbook(
            self.workbook({4: "/ Alice", 6: "Alice /", 7: "A/B/C", 8: "Alice / Alice"})
        )
        for row in parsed.rows[:4]:
            self.assertEqual(row.source_state, ProjectionSourceState.UNSUPPORTED_TOKEN)

    def test_formula_error_multiline_and_unsupported_punctuation_block(self):
        values = (
            "=B4", "#N/A", "Alice\nBob", "Alice\tBob", "Alice, Bob",
            "Alice; Bob", "张三、李四", "Alice，Bob",
        )
        parsed = parse_known_projection_assignment_workbook(
            self.workbook({row: value for row, value in zip([4, *range(6, 13)], values)})
        )
        self.assertEqual(parsed.rows[0].source_state, ProjectionSourceState.FORMULA_BLOCKED)
        self.assertEqual(parsed.rows[1].source_state, ProjectionSourceState.ERROR_BLOCKED)
        for row in parsed.rows[2:]:
            if row.source_row <= 12:
                self.assertEqual(row.source_state, ProjectionSourceState.UNSUPPORTED_TOKEN)

    def test_annotations_placeholders_substitutions_arrows_and_length_block(self):
        values = (
            "Alice (sub)", "Alice [backup]", "TBD", "TBA", "Alice replacement",
            "Alice -> Bob", "Alice 替补", "A" * 121,
        )
        parsed = parse_known_projection_assignment_workbook(
            self.workbook({row: value for row, value in zip([4, *range(6, 13)], values)})
        )
        for row in parsed.rows[:8]:
            self.assertEqual(row.source_state, ProjectionSourceState.UNSUPPORTED_TOKEN)

    def test_header_and_column_contract_are_exact(self):
        with self.assertRaises(Exception) as raised:
            parse_known_projection_assignment_workbook(self.workbook(e3="Projector"))
        self.assertEqual(raised.exception.code.value, "header_mismatch")
        self.assertEqual(SOURCE_COLUMN, "E")

    def test_source_blocker_survives_signed_mapping_round_trip(self):
        review = self.mapping_review("Alice / Alice")
        decoded = decode_projection_assignment_mapping(
            review.signed_state, user=self.staff
        )
        self.assertEqual(
            decoded.parsed.rows[0].source_state,
            ProjectionSourceState.UNSUPPORTED_TOKEN,
        )
        preview = build_projection_assignment_preview(
            mapping_review=decoded,
            selected_mapping={},
            user=self.staff,
            now=self.preview_now(),
        )
        self.assertEqual(
            preview.rows[0].target_state, ProjectionTargetState.SOURCE_BLOCKER
        )

    @skipUnless(
        os.environ.get("SVCA_WORSHIP_WORKBOOK_PATH")
        and Path(os.environ.get("SVCA_WORSHIP_WORKBOOK_PATH", "")).is_file(),
        "real workbook not supplied",
    )
    def test_real_workbook_column_e_reviewed_shape(self):
        path = Path(os.environ["SVCA_WORSHIP_WORKBOOK_PATH"])
        parsed = parse_known_projection_assignment_workbook(
            path.read_bytes(), filename=path.name
        )
        supported = [
            row
            for row in parsed.rows
            if row.source_state == ProjectionSourceState.SUPPORTED_LITERAL
        ]
        self.assertEqual(len(supported), 52)
        self.assertEqual(sum(len(row.normalized_tokens) == 2 for row in supported), 19)
        self.assertEqual(len({row.original_literal for row in supported}), 17)


class ProjectionIdentityAndTeamTests(ProjectionPreviewTestBase):
    def test_exact_team_key_is_authority_not_name_or_pk(self):
        self.assertEqual(resolve_projection_destination_team(), self.projection)
        original_pk = self.projection.pk
        self.projection.name = "Renamed Display"
        self.projection.save(update_fields=["name", "updated_at"])
        self.assertEqual(resolve_projection_destination_team().pk, original_pk)

    def test_missing_inactive_nonassignable_and_duplicate_team_fail_closed(self):
        with self.assertRaises(ProjectionDestinationTeamError) as missing:
            resolve_projection_destination_team("missing.projection")
        self.assertEqual(missing.exception.code, ProjectionDestinationTeamErrorCode.MISSING)
        for field, code in (
            ("is_active", ProjectionDestinationTeamErrorCode.INACTIVE),
            ("is_assignable", ProjectionDestinationTeamErrorCode.NON_ASSIGNABLE),
        ):
            with self.subTest(field=field):
                MinistryTeam.objects.filter(pk=self.projection.pk).update(**{field: False})
                with self.assertRaises(ProjectionDestinationTeamError) as raised:
                    resolve_projection_destination_team()
                self.assertEqual(raised.exception.code, code)
                MinistryTeam.objects.filter(pk=self.projection.pk).update(**{field: True})
        with patch.object(MinistryTeam.objects, "get", side_effect=MinistryTeam.MultipleObjectsReturned):
            with self.assertRaises(ProjectionDestinationTeamError) as duplicate:
                resolve_projection_destination_team()
        self.assertEqual(duplicate.exception.code, ProjectionDestinationTeamErrorCode.DUPLICATE)

    def test_unique_exact_prefill_zero_match_and_duplicate_visible_identity(self):
        exact = self.mapping_review("Alice").token_reviews[0]
        self.assertEqual(exact.identity_state, ProjectionIdentityState.EXACT_PREFILL_AVAILABLE)
        self.assertEqual(exact.prefill_membership_id, self.alice_membership.pk)
        self.assertEqual(
            self.mapping_review("alice").token_reviews[0].identity_state,
            ProjectionIdentityState.MAPPING_REQUIRED,
        )
        TeamMembership.objects.create(team=self.projection, display_name="Alice")
        self.assertEqual(
            self.mapping_review("Alice").token_reviews[0].identity_state,
            ProjectionIdentityState.AMBIGUOUS,
        )

    def test_wrong_team_inactive_missing_and_malformed_membership_rejected(self):
        wrong = TeamMembership.objects.create(team=self.other_team, display_name="Alice")
        review = self.mapping_review()
        for value in (wrong.pk, 999999, "bad"):
            with self.subTest(value=value), self.assertRaises(ProjectionMappingValidationError):
                build_projection_assignment_preview(
                    mapping_review=review,
                    selected_mapping={"Alice": value},
                    user=self.staff,
                )
        self.alice_membership.is_active = False
        self.alice_membership.save(update_fields=["is_active", "updated_at"])
        with self.assertRaises(ProjectionMappingValidationError):
            build_projection_assignment_preview(
                mapping_review=review,
                selected_mapping={"Alice": self.alice_membership.pk},
                user=self.staff,
            )

    def test_two_tokens_cannot_select_same_membership(self):
        self.event_for_row()
        preview = self.preview(
            "Alice / 张三",
            {"Alice": self.alice_membership.pk, "张三": self.alice_membership.pk},
        )
        self.assertEqual(preview.rows[0].target_state, ProjectionTargetState.IDENTITY_BLOCKER)
        self.assertEqual(preview.hard_blocker_count, 1)

    def test_mapping_creates_no_user_or_membership(self):
        before = (User.objects.count(), TeamMembership.objects.count())
        self.mapping_review("Alice / 张三")
        self.assertEqual((User.objects.count(), TeamMembership.objects.count()), before)


class ProjectionClassificationTests(ProjectionPreviewTestBase):
    def test_no_assignment_create_candidate_and_blank_no_proposal(self):
        self.event_for_row()
        preview = self.preview()
        self.assertEqual(preview.rows[0].target_state, ProjectionTargetState.CREATE_CANDIDATE)
        self.assertEqual(preview.rows[1].target_state, ProjectionTargetState.NO_SOURCE_PROPOSAL)

    def test_exact_one_person_roster_is_noop(self):
        event = self.event_for_row()
        self.assignment(event, (self.alice_membership,))
        self.assertEqual(self.preview().rows[0].target_state, ProjectionTargetState.EXACT_NOOP)

    def test_exact_two_person_roster_is_noop_regardless_member_row_order(self):
        event = self.event_for_row()
        self.assignment(event, (self.zhang_membership, self.alice_membership))
        preview = self.preview(
            "Alice / 张三",
            {"Alice": self.alice_membership.pk, "张三": self.zhang_membership.pk},
        )
        self.assertEqual(preview.rows[0].target_state, ProjectionTargetState.EXACT_NOOP)

    def test_empty_different_and_extra_rosters_block(self):
        cases = (
            (),
            (self.zhang_membership,),
            (self.alice_membership, self.zhang_membership),
        )
        for members in cases:
            with self.subTest(member_ids=[item.pk for item in members]):
                event = self.event_for_row()
                self.assignment(event, members)
                self.assertEqual(
                    self.preview().rows[0].target_state,
                    ProjectionTargetState.EXISTING_ROSTER_BLOCKER,
                )
                TeamAssignment.objects.all().delete()
                ServiceEvent.objects.all().delete()

    def test_inactive_current_member_blocks(self):
        event = self.event_for_row()
        self.assignment(event, (self.alice_membership,))
        TeamMembership.objects.filter(pk=self.alice_membership.pk).update(is_active=False)
        review = self.mapping_review("张三")
        preview = build_projection_assignment_preview(
            mapping_review=review,
            selected_mapping={"张三": self.zhang_membership.pk},
            user=self.staff,
            now=self.preview_now(),
        )
        self.assertEqual(preview.rows[0].target_state, ProjectionTargetState.EXISTING_ROSTER_BLOCKER)

    def test_duplicate_historical_and_unknown_assignments_block(self):
        event = self.event_for_row()
        self.assignment(event)
        self.assignment(event)
        self.assertEqual(self.preview().rows[0].target_state, ProjectionTargetState.DUPLICATE_ASSIGNMENT_BLOCKER)
        TeamAssignment.objects.all().delete()
        self.assignment(event, status=TeamAssignment.STATUS_COMPLETED)
        self.assertEqual(self.preview().rows[0].target_state, ProjectionTargetState.HISTORICAL_ASSIGNMENT_BLOCKER)
        TeamAssignment.objects.all().delete()
        assignment = self.assignment(event)
        TeamAssignment.objects.filter(pk=assignment.pk).update(status="mystery")
        self.assertEqual(self.preview().rows[0].target_state, ProjectionTargetState.UNKNOWN_ASSIGNMENT_BLOCKER)

    def test_historical_event_is_safe_skip(self):
        self.event_for_row(status=ServiceEvent.STATUS_COMPLETED)
        preview = self.preview()
        self.assertEqual(preview.rows[0].target_state, ProjectionTargetState.HISTORICAL_EVENT_BLOCKER)
        self.assertEqual(preview.hard_blocker_count, 0)

    def test_missing_exact_event_is_invalid_target_blocker(self):
        preview = self.preview()
        self.assertEqual(
            preview.rows[0].target_state,
            ProjectionTargetState.INVALID_TARGET_BLOCKER,
        )

    def test_worship_fingerprint_none_and_lowercase_are_valid_but_noncanonical_blocks(self):
        event = self.event_for_row()
        assignment = self.assignment(event, (self.alice_membership,))
        for value, expected in (
            (None, ProjectionTargetState.EXACT_NOOP),
            ("a" * 64, ProjectionTargetState.EXACT_NOOP),
            ("A" * 64, ProjectionTargetState.INVALID_ASSIGNMENT_BLOCKER),
            ("aA" * 32, ProjectionTargetState.INVALID_ASSIGNMENT_BLOCKER),
            ("malformed", ProjectionTargetState.INVALID_ASSIGNMENT_BLOCKER),
        ):
            with self.subTest(value=value):
                TeamAssignment.objects.filter(pk=assignment.pk).update(
                    reviewed_worship_context_fingerprint=value
                )
                self.assertEqual(self.preview().rows[0].target_state, expected)

    def test_audience_mismatch_blocks(self):
        event = self.event_for_row()
        ChurchStructureMembership.objects.filter(user=self.alice).update(
            unit=self.other_unit
        )
        self.assertEqual(
            self.preview().rows[0].target_state,
            ProjectionTargetState.AUDIENCE_SAFETY_BLOCKER,
        )


class ProjectionSigningAndZeroWriteTests(ProjectionPreviewTestBase):
    def snapshot(self):
        return {
            "events": list(ServiceEvent.objects.order_by("id").values()),
            "audience": list(ServiceEventAudienceScope.objects.order_by("id").values()),
            "required": list(ServiceEventRequiredTeam.objects.order_by("id").values()),
            "assignments": list(TeamAssignment.objects.order_by("id").values()),
            "members": list(TeamAssignmentMember.objects.order_by("id").values()),
            "memberships": list(TeamMembership.objects.order_by("id").values()),
            "users": list(User.objects.order_by("id").values()),
            "notifications": list(Notification.objects.order_by("id").values()),
            "logs": list(LogEntry.objects.order_by("id").values()),
        }

    def test_upload_mapping_and_preview_are_exhaustively_zero_write(self):
        event = self.event_for_row()
        self.assignment(
            event,
            (self.zhang_membership, self.alice_membership),
            reviewed_worship_context_fingerprint="a" * 64,
        )
        before = self.snapshot()
        review = self.mapping_review("Alice / 张三")
        preview = build_projection_assignment_preview(
            mapping_review=review,
            selected_mapping={"Alice": self.alice_membership.pk, "张三": self.zhang_membership.pk},
            user=self.staff,
            now=self.preview_now(),
        )
        decode_signed_projection_assignment_preview(
            preview.signed_payload, user=self.staff, now=self.preview_now()
        )
        self.assertEqual(
            preview.rows[0].target_state, ProjectionTargetState.EXACT_NOOP
        )
        self.assertEqual(self.snapshot(), before)

    def test_wrong_user_expiry_and_tamper_rejected(self):
        self.event_for_row()
        preview = self.preview()
        with self.assertRaises(SignedProjectionPreviewError):
            decode_signed_projection_assignment_preview(preview.signed_payload, user=self.superuser)
        with self.assertRaises(SignedProjectionPreviewError):
            decode_signed_projection_assignment_preview(preview.signed_payload, user=self.staff, max_age=-1)
        with self.assertRaises(SignedProjectionPreviewError):
            decode_signed_projection_assignment_preview(preview.signed_payload + "x", user=self.staff)

    def test_event_membership_assignment_member_and_team_drift_rejected(self):
        drift_cases = ("event", "membership", "assignment", "member", "team")
        for drift in drift_cases:
            with self.subTest(drift=drift):
                event = self.event_for_row()
                assignment = self.assignment(event, (self.alice_membership,))
                preview = self.preview()
                if drift == "event":
                    ServiceEvent.objects.filter(pk=event.pk).update(scheduling_revision=99)
                elif drift == "membership":
                    TeamMembership.objects.filter(pk=self.alice_membership.pk).update(display_name="Changed")
                elif drift == "assignment":
                    TeamAssignment.objects.filter(pk=assignment.pk).update(status=TeamAssignment.STATUS_CONFIRMED)
                elif drift == "member":
                    TeamAssignmentMember.objects.filter(assignment=assignment).update(confirmed_at=timezone.now())
                else:
                    MinistryTeam.objects.filter(pk=self.projection.pk).update(
                        name="Changed team", updated_at=timezone.now()
                    )
                with self.assertRaises(SignedProjectionPreviewError):
                    decode_signed_projection_assignment_preview(
                        preview.signed_payload, user=self.staff, now=self.preview_now()
                    )
                TeamAssignment.objects.all().delete()
                ServiceEvent.objects.all().delete()
                TeamMembership.objects.filter(pk=self.alice_membership.pk).update(display_name="Alice", is_active=True)
                MinistryTeam.objects.filter(pk=self.projection.pk).update(name="投影团队")

    def test_source_contract_version_tamper_rejected(self):
        self.event_for_row()
        preview = self.preview()
        payload = signing.loads(preview.signed_payload, salt=PREVIEW_SIGNING_SALT)
        payload["source_contract_revision"] = SOURCE_CONTRACT_REVISION + "_DRIFT"
        forged = signing.dumps(payload, compress=True, salt=PREVIEW_SIGNING_SALT)
        with self.assertRaises(SignedProjectionPreviewError):
            decode_signed_projection_assignment_preview(forged, user=self.staff)

        payload = signing.loads(preview.signed_payload, salt=PREVIEW_SIGNING_SALT)
        payload["rows"][0]["source"]["token_digests"][0] = "F" * 64
        forged = signing.dumps(payload, compress=True, salt=PREVIEW_SIGNING_SALT)
        with self.assertRaises(SignedProjectionPreviewError):
            decode_signed_projection_assignment_preview(forged, user=self.staff)

    def test_mapping_signature_wrong_user_and_membership_drift_rejected(self):
        review = self.mapping_review()
        with self.assertRaises(ProjectionMappingStateError):
            decode_projection_assignment_mapping(review.signed_state, user=self.superuser)
        self.alice_membership.display_name = "Changed"
        self.alice_membership.save(update_fields=["display_name", "updated_at"])
        with self.assertRaises(ProjectionMappingStateError):
            decode_projection_assignment_mapping(review.signed_state, user=self.staff)
        payload = signing.loads(review.signed_state, salt=MAPPING_SIGNING_SALT)
        payload["source_contract_revision"] += "_DRIFT"
        forged = signing.dumps(payload, compress=True, salt=MAPPING_SIGNING_SALT)
        with self.assertRaises(ProjectionMappingStateError):
            decode_projection_assignment_mapping(forged, user=self.staff)


class ProjectionPermissionAndRenderedTests(ProjectionPreviewTestBase):
    def test_staff_superuser_allowed_ordinary_and_inactive_staff_denied(self):
        self.assertTrue(user_can_preview_projection_assignments(self.staff))
        self.assertTrue(user_can_preview_projection_assignments(self.superuser))
        self.assertFalse(user_can_preview_projection_assignments(self.alice))
        self.staff.is_active = False
        self.assertFalse(user_can_preview_projection_assignments(self.staff))

    def test_integration_gate_and_ordinary_user_route_denial(self):
        self.client.force_login(self.alice)
        self.assertEqual(self.client.get(reverse("projection_assignment_workbook_preview")).status_code, 403)
        self.client.force_login(self.staff)
        with override_settings(CMS_ENABLED_INTEGRATIONS=[]):
            self.assertEqual(self.client.get(reverse("projection_assignment_workbook_preview")).status_code, 404)

    def test_global_manager_team_lead_event_planner_and_audience_member_are_denied(self):
        lead = User.objects.create_user("projection_lead", password="pw")
        coordinator = User.objects.create_user(
            "projection_coordinator", password="pw"
        )
        role_type = MinistryTeamRoleType.objects.create(
            code=MinistryTeamRoleType.CODE_LEAD, name="Lead", name_en="Lead"
        )
        coordinator_type = MinistryTeamRoleType.objects.create(
            code=MinistryTeamRoleType.CODE_COORDINATOR,
            name="Coordinator",
            name_en="Coordinator",
        )
        MinistryTeamRoleAssignment.objects.create(
            team=self.projection,
            role_type=role_type,
            user=lead,
            start_date=timezone.localdate(),
        )
        MinistryTeamRoleAssignment.objects.create(
            team=self.projection,
            role_type=coordinator_type,
            user=coordinator,
            start_date=timezone.localdate(),
        )
        planner = User.objects.create_user("projection_planner", password="pw")
        event = self.event_for_row()
        ServiceEventPlannerAssignment.objects.create(service_event=event, user=planner)
        manager = User.objects.create_user("projection_manager", password="pw")
        with patch(
            "ministry.permissions.has_capability",
            side_effect=lambda user, capability: (
                user.pk == manager.pk and capability == CAP_MANAGE_TEAM_ASSIGNMENTS
            ),
        ):
            self.assertTrue(can_manage_team_assignments(manager))
        for user in (lead, coordinator, planner, manager, self.alice):
            with self.subTest(user=user.username):
                self.client.force_login(user)
                self.assertEqual(
                    self.client.get(
                        reverse("projection_assignment_workbook_preview")
                    ).status_code,
                    403,
                )

    def _render_preview(self, language="en"):
        self.event_for_row()
        self.client.force_login(self.staff)
        session = self.client.session
        session["language"] = language
        session.save()
        upload_response = self.client.post(
            reverse("projection_assignment_workbook_preview"),
            {"workbook": self.upload({4: "Alice / 张三"})},
        )
        review = upload_response.context["mapping_review"]
        data = {"signed_mapping_state": review.signed_state}
        for token_review in review.token_reviews:
            data[f"mapping_{token_review.index}"] = {
                "Alice": self.alice_membership.pk,
                "张三": self.zhang_membership.pk,
            }[token_review.token]
        with patch(
            "ministry.services.projection_assignment_xlsx_preview.timezone.now",
            return_value=self.preview_now(),
        ):
            return self.client.post(reverse("projection_assignment_workbook_preview"), data)

    def test_english_desktop_two_person_review_has_no_private_data_or_writer(self):
        response = self._render_preview("en")
        self.assertContains(response, "ZERO WRITE")
        self.assertContains(response, "Two-person proposed roster — both included")
        self.assertContains(response, "Alice")
        self.assertContains(response, "张三")
        self.assertContains(response, "CREATE_CANDIDATE")
        body = response.content.decode()
        self.assertNotIn("private-alice@example.test", body)
        self.assertNotIn("private Alice note", body)
        self.assertNotIn("private confirmation note", body)
        self.assertNotIn("signed_confirmation", body)
        self.assertNotIn("Confirm and Create", body)

    def test_chinese_mobile_copy_and_responsive_labels_render(self):
        response = self._render_preview("zh")
        self.assertContains(response, "投影排班零写入预览")
        self.assertContains(response, "两人建议名单（两人都包括）")
        self.assertContains(response, 'data-label="来源"')
        self.assertContains(response, "本阶段不会建立或更改任何排班")

    def test_english_one_person_review_renders_one_selected_membership(self):
        self.event_for_row()
        self.client.force_login(self.staff)
        session = self.client.session
        session["language"] = "en"
        session.save()
        upload_response = self.client.post(
            reverse("projection_assignment_workbook_preview"),
            {"workbook": self.upload({4: "Alice"})},
        )
        review = upload_response.context["mapping_review"]
        with patch(
            "ministry.services.projection_assignment_xlsx_preview.timezone.now",
            return_value=self.preview_now(),
        ):
            response = self.client.post(
                reverse("projection_assignment_workbook_preview"),
                {
                    "signed_mapping_state": review.signed_state,
                    "mapping_0": self.alice_membership.pk,
                },
            )
        self.assertContains(response, "Alice · #membership")
        self.assertNotContains(response, "Two-person proposed roster")
        self.assertContains(response, "CREATE_CANDIDATE")
