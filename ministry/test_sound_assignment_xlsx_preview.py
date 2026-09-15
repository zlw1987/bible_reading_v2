"""Focused MO-S.6F.1A Sound assignment zero-write preview tests."""

from copy import deepcopy
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
from .services.sound_assignment_xlsx_preview import (
    INTEGRATION_KEY,
    MAPPING_SIGNING_SALT,
    PREVIEW_CONTRACT_REVISION,
    PREVIEW_SIGNING_SALT,
    SOURCE_COLUMN,
    SOURCE_CONTRACT_REVISION,
    SVCA_SOUND_TEAM_KEY,
    SignedSoundPreviewError,
    SoundDestinationTeamError,
    SoundDestinationTeamErrorCode,
    SoundIdentityState,
    SoundMappingStateError,
    SoundMappingValidationError,
    SoundSourceState,
    SoundTargetState,
    build_sound_assignment_preview,
    decode_signed_sound_assignment_preview,
    decode_sound_assignment_mapping,
    normalize_sound_identity,
    parse_known_sound_assignment_workbook,
    prepare_sound_assignment_mapping,
    resolve_destination_team,
    user_can_preview_sound_assignments,
)


@override_settings(CMS_ENABLED_INTEGRATIONS=[INTEGRATION_KEY])
class SoundAssignmentPreviewTestBase(TestCase):
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
        cls.sound = MinistryTeam.objects.create(
            name="音控团队",
            name_en="Sound Team",
            team_key=SVCA_SOUND_TEAM_KEY,
            is_active=True,
            is_assignable=True,
        )
        cls.other_team = MinistryTeam.objects.create(
            name="Projection Team",
            name_en="Projection Team",
            team_key="main.cm.digital.projection",
        )
        cls.staff = User.objects.create_user(
            "sound_staff", password="pw", is_staff=True
        )
        cls.superuser = User.objects.create_superuser(
            "sound_super", "super@example.test", "pw"
        )
        cls.alice = User.objects.create_user(
            "alice", password="pw", first_name="Alice"
        )
        ChurchStructureMembership.objects.create(
            user=cls.alice,
            unit=cls.cm,
            status=ChurchStructureMembership.STATUS_ACTIVE,
            is_primary=True,
            start_date=date(2020, 1, 1),
        )
        cls.alice_membership = TeamMembership.objects.create(
            team=cls.sound,
            user=cls.alice,
            display_name="Alice",
            email="private-alice@example.test",
            notes="private member note",
        )
        cls.display_only = TeamMembership.objects.create(
            team=cls.sound,
            display_name="O'Neil-Smith",
            email="private-display@example.test",
            notes="private display-only note",
        )

    def workbook(self, sound_overrides=None):
        return build_known_workbook(sound_overrides=sound_overrides or {})

    def upload(self, sound_overrides=None):
        return SimpleUploadedFile(
            "annual.xlsx",
            self.workbook(sound_overrides),
            content_type=(
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ),
        )

    def event_for_row(self, row_index=0, **overrides):
        row_number = [4, *range(6, 57)][row_index]
        local_date = timezone.datetime(2026, 1, 4) + timezone.timedelta(
            weeks=row_index
        )
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

    def mapping_review(self, token="Alice"):
        return prepare_sound_assignment_mapping(
            content=self.workbook({4: token}),
            filename="annual.xlsx",
            user=self.staff,
        )

    def preview_now(self):
        return timezone.make_aware(
            datetime(2026, 1, 4, 8, 0), timezone.get_current_timezone()
        )

    def preview(self, *, token="Alice", membership=None):
        review = self.mapping_review(token)
        return build_sound_assignment_preview(
            mapping_review=review,
            selected_mapping={
                token: (membership or self.alice_membership).pk,
            },
            user=self.staff,
            now=self.preview_now(),
        )


class SoundSourceParserTests(SoundAssignmentPreviewTestBase):
    def test_column_f_literal_blank_and_normalization_contract(self):
        parsed = parse_known_sound_assignment_workbook(
            self.workbook({4: "  Jose\u0301  ", 6: ""})
        )
        self.assertEqual(parsed.rows[0].source_cell, "F4")
        self.assertEqual(parsed.rows[0].source_state, SoundSourceState.SUPPORTED_LITERAL)
        self.assertEqual(parsed.rows[0].normalized_token, "José")
        self.assertEqual(parsed.rows[1].source_state, SoundSourceState.NO_SOURCE_PROPOSAL)
        self.assertIsNone(parsed.rows[1].normalized_token)
        self.assertEqual(normalize_sound_identity("  A  B  "), "A  B")

    def test_formula_error_separator_annotation_placeholder_and_free_text_block(self):
        cases = (
            "=B4",
            "#N/A",
            "Alice/Bob",
            "Alice & Bob",
            "Alice, Bob",
            "张三、李四",
            "Alice；Bob",
            "Alice\nBob",
            "Alice (sub)",
            "TBD",
            "Alice -> Bob",
        )
        parsed = parse_known_sound_assignment_workbook(
            self.workbook({row: value for row, value in zip([4, *range(6, 16)], cases)})
        )
        self.assertEqual(parsed.rows[0].source_state, SoundSourceState.FORMULA_BLOCKED)
        self.assertEqual(parsed.rows[1].source_state, SoundSourceState.ERROR_BLOCKED)
        for row in parsed.rows[2:11]:
            self.assertEqual(row.source_state, SoundSourceState.UNSUPPORTED_TOKEN)

    def test_apostrophe_and_hyphen_are_not_rejected(self):
        parsed = parse_known_sound_assignment_workbook(
            self.workbook({4: "O'Neil-Smith"})
        )
        self.assertEqual(parsed.rows[0].source_state, SoundSourceState.SUPPORTED_LITERAL)

    @skipUnless(
        os.environ.get("SVCA_WORSHIP_WORKBOOK_PATH")
        and Path(os.environ.get("SVCA_WORSHIP_WORKBOOK_PATH", "")).is_file(),
        "real workbook not supplied",
    )
    def test_real_workbook_column_f_acceptance(self):
        path = Path(os.environ["SVCA_WORSHIP_WORKBOOK_PATH"])
        parsed = parse_known_sound_assignment_workbook(
            path.read_bytes(), filename=path.name
        )
        supported = [
            row
            for row in parsed.rows
            if row.source_state == SoundSourceState.SUPPORTED_LITERAL
        ]
        self.assertEqual(len(supported), 26)
        self.assertEqual(len({row.normalized_token for row in supported}), 4)
        self.assertEqual(
            sum(
                row.source_state == SoundSourceState.NO_SOURCE_PROPOSAL
                for row in parsed.rows
            ),
            26,
        )

    def test_sound_header_is_exact_and_no_other_assignment_column_is_parsed(self):
        with self.assertRaises(Exception) as raised:
            parse_known_sound_assignment_workbook(build_known_workbook(f3="Audio"))
        self.assertEqual(raised.exception.code.value, "header_mismatch")
        parsed = parse_known_sound_assignment_workbook(self.workbook({4: "Alice"}))
        self.assertEqual(SOURCE_COLUMN, "F")
        self.assertFalse(any(hasattr(row, "projection_token") for row in parsed.rows))


class SoundTeamAndIdentityTests(SoundAssignmentPreviewTestBase):
    def test_exact_team_key_resolves_without_pk_or_mutable_name_assumption(self):
        self.assertEqual(resolve_destination_team(SVCA_SOUND_TEAM_KEY), self.sound)
        original_pk = self.sound.pk
        self.sound.name = "Renamed Audio Team"
        self.sound.save(update_fields=["name", "updated_at"])
        self.assertEqual(resolve_destination_team(SVCA_SOUND_TEAM_KEY).pk, original_pk)

    def test_missing_inactive_and_nonassignable_team_block(self):
        with self.assertRaises(SoundDestinationTeamError) as missing:
            resolve_destination_team("missing.sound")
        self.assertEqual(missing.exception.code, SoundDestinationTeamErrorCode.MISSING)
        for field, code in (
            ("is_active", SoundDestinationTeamErrorCode.INACTIVE),
            ("is_assignable", SoundDestinationTeamErrorCode.NON_ASSIGNABLE),
        ):
            with self.subTest(field=field):
                MinistryTeam.objects.filter(pk=self.sound.pk).update(**{field: False})
                with self.assertRaises(SoundDestinationTeamError) as raised:
                    resolve_destination_team(SVCA_SOUND_TEAM_KEY)
                self.assertEqual(raised.exception.code, code)
                MinistryTeam.objects.filter(pk=self.sound.pk).update(**{field: True})

    def test_exact_prefill_zero_match_multiple_match_and_display_only_identity(self):
        alice_review = self.mapping_review("Alice")
        self.assertEqual(
            alice_review.token_reviews[0].identity_state,
            SoundIdentityState.EXACT_PREFILL_AVAILABLE,
        )
        self.assertEqual(
            alice_review.token_reviews[0].prefill_membership_id,
            self.alice_membership.pk,
        )
        alias_review = self.mapping_review("Workbook Alias")
        self.assertEqual(
            alias_review.token_reviews[0].identity_state,
            SoundIdentityState.MAPPING_REQUIRED,
        )
        case_changed = self.mapping_review("alice")
        self.assertEqual(
            case_changed.token_reviews[0].identity_state,
            SoundIdentityState.MAPPING_REQUIRED,
        )
        TeamMembership.objects.create(team=self.sound, display_name="Alice")
        ambiguous = self.mapping_review("Alice")
        self.assertEqual(
            ambiguous.token_reviews[0].identity_state, SoundIdentityState.AMBIGUOUS
        )
        display_review = self.mapping_review("O'Neil-Smith")
        self.assertEqual(
            display_review.token_reviews[0].prefill_membership_id,
            self.display_only.pk,
        )

    def test_forged_wrong_team_inactive_missing_and_malformed_mapping_rejected(self):
        wrong_team_member = TeamMembership.objects.create(
            team=self.other_team, display_name="Alice"
        )
        review = self.mapping_review("Alice")
        for forged in (wrong_team_member.pk, 999999, "not-an-id"):
            with self.subTest(forged=forged), self.assertRaises(
                SoundMappingValidationError
            ):
                build_sound_assignment_preview(
                    mapping_review=review,
                    selected_mapping={"Alice": forged},
                    user=self.staff,
                )
        self.alice_membership.is_active = False
        self.alice_membership.save(update_fields=["is_active", "updated_at"])
        with self.assertRaises(SoundMappingValidationError):
            build_sound_assignment_preview(
                mapping_review=review,
                selected_mapping={"Alice": self.alice_membership.pk},
                user=self.staff,
            )

    def test_mapping_state_rejects_changed_membership_identity(self):
        review = self.mapping_review("Alice")
        self.alice_membership.display_name = "Alice Changed"
        self.alice_membership.save(update_fields=["display_name", "updated_at"])
        with self.assertRaises(SoundMappingStateError):
            decode_sound_assignment_mapping(review.signed_state, user=self.staff)

    def test_mapping_preparation_creates_neither_user_nor_membership(self):
        before = (User.objects.count(), TeamMembership.objects.count())
        self.mapping_review("Alice")
        self.assertEqual((User.objects.count(), TeamMembership.objects.count()), before)


class SoundAssignmentClassificationTests(SoundAssignmentPreviewTestBase):
    def test_no_assignment_is_create_candidate_and_blank_is_no_proposal(self):
        self.event_for_row()
        preview = self.preview()
        self.assertEqual(preview.rows[0].target_state, SoundTargetState.CREATE_CANDIDATE)
        self.assertEqual(
            preview.rows[1].target_state, SoundTargetState.NO_SOURCE_PROPOSAL
        )
        self.assertEqual(preview.create_candidate_count, 1)
        self.assertEqual(preview.no_source_count, 51)

    def test_completed_event_without_assignment_is_historical_event_blocker(self):
        self.event_for_row(status=ServiceEvent.STATUS_COMPLETED)
        preview = self.preview()
        self.assertEqual(
            preview.rows[0].target_state,
            SoundTargetState.HISTORICAL_EVENT_BLOCKER,
        )
        self.assertEqual(preview.create_candidate_count, 0)

    def test_canonically_past_published_event_is_historical_event_blocker(self):
        self.event_for_row()
        past_now = timezone.make_aware(
            datetime(2026, 1, 6, 0, 0), timezone.get_current_timezone()
        )
        review = self.mapping_review()
        preview = build_sound_assignment_preview(
            mapping_review=review,
            selected_mapping={"Alice": self.alice_membership.pk},
            user=self.staff,
            now=past_now,
        )
        self.assertEqual(
            preview.rows[0].target_state,
            SoundTargetState.HISTORICAL_EVENT_BLOCKER,
        )
        self.assertEqual(preview.create_candidate_count, 0)

    def test_blank_historical_event_remains_no_source_and_not_blocked(self):
        self.event_for_row(status=ServiceEvent.STATUS_COMPLETED)
        review = prepare_sound_assignment_mapping(
            content=self.workbook(), filename="annual.xlsx", user=self.staff
        )
        preview = build_sound_assignment_preview(
            mapping_review=review,
            selected_mapping={},
            user=self.staff,
            now=self.preview_now(),
        )
        self.assertEqual(
            preview.rows[0].target_state, SoundTargetState.NO_SOURCE_PROPOSAL
        )
        self.assertEqual(preview.blocked_count, 0)

    def test_historical_event_precedes_exact_current_roster_noop(self):
        event = self.event_for_row(status=ServiceEvent.STATUS_COMPLETED)
        assignment = TeamAssignment.objects.create(
            service_event=event,
            ministry_team=self.sound,
            status=TeamAssignment.STATUS_SCHEDULED,
        )
        TeamAssignmentMember.objects.create(
            assignment=assignment, membership=self.alice_membership
        )
        self.assertEqual(
            self.preview().rows[0].target_state,
            SoundTargetState.HISTORICAL_EVENT_BLOCKER,
        )

    def test_blank_remains_no_proposal_when_cms_assignment_exists(self):
        event = self.event_for_row()
        TeamAssignment.objects.create(
            service_event=event,
            ministry_team=self.sound,
            status=TeamAssignment.STATUS_SCHEDULED,
        )
        review = prepare_sound_assignment_mapping(
            content=self.workbook(), filename="annual.xlsx", user=self.staff
        )
        preview = build_sound_assignment_preview(
            mapping_review=review, selected_mapping={}, user=self.staff
        )
        self.assertEqual(
            preview.rows[0].target_state, SoundTargetState.NO_SOURCE_PROPOSAL
        )
        self.assertEqual(preview.blocked_count, 0)

    def _assignment(self, *, status=TeamAssignment.STATUS_SCHEDULED, member=None):
        event = self.event_for_row()
        assignment = TeamAssignment.objects.create(
            service_event=event,
            ministry_team=self.sound,
            status=status,
            notes="preserve private assignment note",
            reviewed_worship_context_fingerprint="A" * 64,
        )
        if member is not None:
            TeamAssignmentMember.objects.create(
                assignment=assignment,
                membership=member,
                confirmation_note="preserve private confirmation note",
            )
        return assignment

    def test_exact_one_member_roster_is_noop_and_preserves_everything(self):
        assignment = self._assignment(member=self.alice_membership)
        before = (
            assignment.status,
            assignment.notes,
            assignment.reviewed_worship_context_fingerprint,
            assignment.updated_at,
        )
        preview = self.preview()
        self.assertEqual(preview.rows[0].target_state, SoundTargetState.EXACT_NOOP)
        assignment.refresh_from_db()
        self.assertEqual(
            (
                assignment.status,
                assignment.notes,
                assignment.reviewed_worship_context_fingerprint,
                assignment.updated_at,
            ),
            before,
        )

    def test_empty_and_different_current_rosters_block(self):
        self._assignment()
        self.assertEqual(
            self.preview().rows[0].target_state,
            SoundTargetState.EXISTING_ROSTER_BLOCKER,
        )
        TeamAssignment.objects.all().delete()
        ServiceEvent.objects.all().delete()
        self._assignment(member=self.display_only)
        self.assertEqual(
            self.preview().rows[0].target_state,
            SoundTargetState.EXISTING_ROSTER_BLOCKER,
        )

    def test_duplicate_current_assignments_block(self):
        event = self.event_for_row()
        for _ in range(2):
            TeamAssignment.objects.create(
                service_event=event,
                ministry_team=self.sound,
                status=TeamAssignment.STATUS_SCHEDULED,
            )
        self.assertEqual(
            self.preview().rows[0].target_state,
            SoundTargetState.DUPLICATE_ASSIGNMENT_BLOCKER,
        )

    def test_completed_and_cancelled_history_block_new_current_row(self):
        for status in (
            TeamAssignment.STATUS_COMPLETED,
            TeamAssignment.STATUS_CANCELLED,
        ):
            with self.subTest(status=status):
                TeamAssignment.objects.all().delete()
                ServiceEvent.objects.all().delete()
                self._assignment(status=status, member=self.alice_membership)
                self.assertEqual(
                    self.preview().rows[0].target_state,
                    SoundTargetState.HISTORICAL_ASSIGNMENT_BLOCKER,
                )

    def test_history_alongside_exact_current_and_inactive_extra_member_still_block(self):
        event = self.event_for_row()
        current = TeamAssignment.objects.create(
            service_event=event,
            ministry_team=self.sound,
            status=TeamAssignment.STATUS_SCHEDULED,
        )
        TeamAssignmentMember.objects.create(
            assignment=current, membership=self.alice_membership
        )
        TeamAssignment.objects.create(
            service_event=event,
            ministry_team=self.sound,
            status=TeamAssignment.STATUS_COMPLETED,
        )
        self.assertEqual(
            self.preview().rows[0].target_state,
            SoundTargetState.HISTORICAL_ASSIGNMENT_BLOCKER,
        )

        TeamAssignment.objects.filter(status=TeamAssignment.STATUS_COMPLETED).delete()
        inactive = TeamMembership.objects.create(
            team=self.sound,
            display_name="Inactive history",
            is_active=True,
        )
        TeamAssignmentMember.objects.create(
            assignment=current, membership=inactive
        )
        TeamMembership.objects.filter(pk=inactive.pk).update(is_active=False)
        self.assertEqual(
            self.preview().rows[0].target_state,
            SoundTargetState.EXISTING_ROSTER_BLOCKER,
        )

    def test_invalid_target_and_unsupported_source_block_without_retarget(self):
        event = self.event_for_row(status=ServiceEvent.STATUS_DRAFT)
        preview = self.preview()
        self.assertEqual(
            preview.rows[0].target_state, SoundTargetState.INVALID_TARGET_BLOCKER
        )
        original_event_id = event.pk
        blocked_review = prepare_sound_assignment_mapping(
            content=self.workbook({4: "Alice/Bob"}),
            filename="annual.xlsx",
            user=self.staff,
        )
        blocked = build_sound_assignment_preview(
            mapping_review=blocked_review,
            selected_mapping={},
            user=self.staff,
        )
        self.assertEqual(blocked.rows[0].target_state, SoundTargetState.SOURCE_BLOCKER)
        self.assertEqual(ServiceEvent.objects.get(pk=original_event_id).pk, original_event_id)


class SoundSigningTests(SoundAssignmentPreviewTestBase):
    def test_real_shape_signed_preview_stays_within_existing_64k_pattern(self):
        source_rows = [4, *range(6, 31)]
        for row_index in range(len(source_rows)):
            self.event_for_row(row_index)
        review = prepare_sound_assignment_mapping(
            content=self.workbook({row: "Alice" for row in source_rows}),
            filename="annual.xlsx",
            user=self.staff,
        )
        preview = build_sound_assignment_preview(
            mapping_review=review,
            selected_mapping={"Alice": self.alice_membership.pk},
            user=self.staff,
            now=self.preview_now(),
        )
        self.assertEqual(preview.create_candidate_count, 26)
        self.assertLess(preview.signed_payload_bytes, 64 * 1024)

    def test_mapping_state_is_user_bound_expiring_tamper_evident_and_hash_bound(self):
        review = self.mapping_review("Alice")
        decoded = signing.loads(review.signed_state, salt=MAPPING_SIGNING_SALT)
        self.assertEqual(decoded["sha256"], review.parsed.sha256)
        self.assertEqual(decoded["source_contract_revision"], SOURCE_CONTRACT_REVISION)
        with self.assertRaises(SoundMappingStateError):
            decode_sound_assignment_mapping(review.signed_state, user=self.alice)
        with self.assertRaises(SoundMappingStateError):
            decode_sound_assignment_mapping(
                review.signed_state + "tamper", user=self.staff
            )
        with self.assertRaises(SoundMappingStateError):
            decode_sound_assignment_mapping(
                review.signed_state, user=self.staff, max_age=-1
            )

    def test_preview_contract_binds_canonical_source_event_team_member_and_baseline(self):
        event = self.event_for_row()
        preview = self.preview()
        payload = decode_signed_sound_assignment_preview(
            preview.signed_payload, user=self.staff, now=self.preview_now()
        )
        self.assertEqual(payload["contract_revision"], PREVIEW_CONTRACT_REVISION)
        self.assertEqual(payload["sha256"], preview.mapping_review.parsed.sha256)
        row = payload["rows"][0]
        self.assertEqual(row["source"]["cell"], "F4")
        self.assertEqual(row["event"]["id"], event.pk)
        self.assertEqual(row["team"], {
            "id": self.sound.pk,
            "key": SVCA_SOUND_TEAM_KEY,
            "active": True,
            "assignable": True,
        })
        self.assertEqual(row["membership"]["id"], self.alice_membership.pk)
        self.assertEqual(row["assignment_baseline"], [])
        self.assertNotIn("Alice", str(row["source"]))

    def test_signed_historical_state_cannot_be_reinterpreted_as_create_authority(self):
        self.event_for_row()
        historical_now = timezone.make_aware(
            datetime(2026, 1, 6, 0, 0), timezone.get_current_timezone()
        )
        review = self.mapping_review()
        preview = build_sound_assignment_preview(
            mapping_review=review,
            selected_mapping={"Alice": self.alice_membership.pk},
            user=self.staff,
            now=historical_now,
        )
        payload = decode_signed_sound_assignment_preview(
            preview.signed_payload, user=self.staff, now=historical_now
        )
        self.assertEqual(
            payload["rows"][0]["target_state"],
            SoundTargetState.HISTORICAL_EVENT_BLOCKER.value,
        )
        forged = deepcopy(preview.normalized_payload)
        forged["rows"][0]["target_state"] = SoundTargetState.CREATE_CANDIDATE.value
        forged_token = signing.dumps(
            forged, compress=True, salt=PREVIEW_SIGNING_SALT
        )
        with self.assertRaises(SignedSoundPreviewError):
            decode_signed_sound_assignment_preview(
                forged_token, user=self.staff, now=historical_now
            )

    def test_create_candidate_becoming_historical_is_stale_at_decode(self):
        self.event_for_row()
        preview = self.preview()
        historical_now = timezone.make_aware(
            datetime(2026, 1, 6, 0, 0), timezone.get_current_timezone()
        )
        with self.assertRaises(SignedSoundPreviewError):
            decode_signed_sound_assignment_preview(
                preview.signed_payload, user=self.staff, now=historical_now
            )

    def test_preview_decoder_rejects_other_user_expiry_version_and_resigned_forgery(self):
        self.event_for_row()
        preview = self.preview()
        with self.assertRaises(SignedSoundPreviewError):
            decode_signed_sound_assignment_preview(preview.signed_payload, user=self.alice)
        with self.assertRaises(SignedSoundPreviewError):
            decode_signed_sound_assignment_preview(
                preview.signed_payload, user=self.staff, max_age=-1
            )
        payload = deepcopy(preview.normalized_payload)
        payload["contract_revision"] = "forged"
        forged = signing.dumps(payload, compress=True, salt=PREVIEW_SIGNING_SALT)
        with self.assertRaises(SignedSoundPreviewError):
            decode_signed_sound_assignment_preview(forged, user=self.staff)
        payload = deepcopy(preview.normalized_payload)
        payload["team"]["id"] = self.other_team.pk
        forged_team = signing.dumps(
            payload, compress=True, salt=PREVIEW_SIGNING_SALT
        )
        with self.assertRaises(SignedSoundPreviewError):
            decode_signed_sound_assignment_preview(forged_team, user=self.staff)

    def test_preview_decoder_rejects_stale_event_membership_and_assignment_baselines(self):
        event = self.event_for_row()
        preview = self.preview()
        event.scheduling_revision += 1
        event.save(update_fields=["scheduling_revision"])
        with self.assertRaises(SignedSoundPreviewError):
            decode_signed_sound_assignment_preview(
                preview.signed_payload, user=self.staff, now=self.preview_now()
            )

        event.scheduling_revision -= 1
        event.save(update_fields=["scheduling_revision"])
        preview = self.preview()
        self.alice_membership.display_name = "Alice Changed"
        self.alice_membership.save(update_fields=["display_name", "updated_at"])
        with self.assertRaises(SignedSoundPreviewError):
            decode_signed_sound_assignment_preview(
                preview.signed_payload, user=self.staff, now=self.preview_now()
            )

        self.alice_membership.display_name = "Alice"
        self.alice_membership.save(update_fields=["display_name", "updated_at"])
        preview = self.preview()
        TeamAssignment.objects.create(
            service_event=event,
            ministry_team=self.sound,
            status=TeamAssignment.STATUS_SCHEDULED,
        )
        with self.assertRaises(SignedSoundPreviewError):
            decode_signed_sound_assignment_preview(
                preview.signed_payload, user=self.staff, now=self.preview_now()
            )


@override_settings(CMS_ENABLED_INTEGRATIONS=[INTEGRATION_KEY])
class SoundPreviewPermissionPrivacyAndZeroWriteTests(SoundAssignmentPreviewTestBase):
    def test_only_active_staff_or_superuser_has_bulk_preview_authority(self):
        self.assertTrue(user_can_preview_sound_assignments(self.staff))
        self.assertTrue(user_can_preview_sound_assignments(self.superuser))
        self.assertFalse(user_can_preview_sound_assignments(self.alice))
        for user in (self.staff, self.superuser):
            self.client.force_login(user)
            self.assertEqual(
                self.client.get(reverse("sound_assignment_workbook_preview")).status_code,
                200,
            )

    def test_global_manager_team_lead_event_planner_and_member_are_denied(self):
        lead = User.objects.create_user("sound_lead", password="pw")
        role_type = MinistryTeamRoleType.objects.create(
            code=MinistryTeamRoleType.CODE_LEAD,
            name="Lead",
            name_en="Lead",
        )
        MinistryTeamRoleAssignment.objects.create(
            team=self.sound,
            role_type=role_type,
            user=lead,
            start_date=timezone.localdate(),
        )
        planner = User.objects.create_user("event_planner", password="pw")
        event = self.event_for_row()
        ServiceEventPlannerAssignment.objects.create(service_event=event, user=planner)
        global_manager = User.objects.create_user("global_manager", password="pw")
        with patch(
            "ministry.permissions.has_capability",
            side_effect=lambda user, capability: (
                user.pk == global_manager.pk
                and capability == CAP_MANAGE_TEAM_ASSIGNMENTS
            ),
        ):
            self.assertTrue(can_manage_team_assignments(global_manager))
        for user in (global_manager, lead, planner, self.alice):
            with self.subTest(user=user.username):
                self.client.force_login(user)
                self.assertEqual(
                    self.client.get(
                        reverse("sound_assignment_workbook_preview")
                    ).status_code,
                    403,
                )

    @override_settings(CMS_ENABLED_INTEGRATIONS=[])
    def test_disabled_integration_returns_404_for_staff_before_adapter_import(self):
        self.client.force_login(self.staff)
        with patch(
            "ministry.services.sound_assignment_xlsx_preview.parse_known_sound_assignment_workbook"
        ) as parser:
            response = self.client.get(reverse("sound_assignment_workbook_preview"))
        self.assertEqual(response.status_code, 404)
        parser.assert_not_called()

    def _domain_snapshot(self):
        return {
            "events": list(
                ServiceEvent.objects.order_by("id").values_list(
                    "id", "scheduling_revision", "rotation_anchor_team_id"
                )
            ),
            "audience_scopes": list(
                ServiceEventAudienceScope.objects.order_by("id").values_list(
                    "id", "service_event_id", "unit_id"
                )
            ),
            "required_teams": list(
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
                    "id", "team_id", "user_id", "display_name", "is_active", "updated_at"
                )
            ),
            "assignments": list(
                TeamAssignment.objects.order_by("id").values_list(
                    "id", "status", "reviewed_worship_context_fingerprint", "updated_at"
                )
            ),
            "assignment_members": list(
                TeamAssignmentMember.objects.order_by("id").values_list(
                    "id", "assignment_id", "membership_id", "confirmed_at"
                )
            ),
            "users": User.objects.count(),
            "notifications": Notification.objects.count(),
            "logs": LogEntry.objects.count(),
        }

    def test_upload_mapping_preview_and_confirmation_proposal_are_zero_write_and_privacy_bounded(self):
        self.event_for_row()
        unrelated = TeamMembership.objects.create(
            team=self.other_team,
            display_name="Unrelated Private Person",
            email="unrelated@example.test",
            notes="unrelated note",
        )
        self.client.force_login(self.staff)
        session = self.client.session
        session["language"] = "en"
        session.save()
        before = self._domain_snapshot()
        with patch(
            "ministry.services.sound_assignment_xlsx_preview.timezone.now",
            return_value=self.preview_now(),
        ), patch("django.db.transaction.on_commit") as on_commit:
            upload_response = self.client.post(
                reverse("sound_assignment_workbook_preview"),
                {"workbook": self.upload({4: "Alice"})},
            )
            review = upload_response.context["mapping_review"]
            preview_response = self.client.post(
                reverse("sound_assignment_workbook_preview"),
                {
                    "signed_mapping_state": review.signed_state,
                    "mapping_0": str(self.alice_membership.pk),
                },
            )
        self.assertEqual(preview_response.status_code, 200)
        self.assertEqual(
            preview_response.context["preview"].rows[0].target_state,
            SoundTargetState.CREATE_CANDIDATE,
        )
        rendered = preview_response.content.decode()
        for private_value in (
            self.alice_membership.email,
            self.alice_membership.notes,
            unrelated.display_name,
            unrelated.email,
            unrelated.notes,
        ):
            self.assertNotIn(private_value, rendered)
        self.assertContains(preview_response, "This preview will not change any assignments")
        self.assertIsNotNone(preview_response.context["confirmation_proposal"])
        self.assertContains(preview_response, "Confirm and Create")
        self.assertEqual(self._domain_snapshot(), before)
        on_commit.assert_not_called()

    def test_historical_event_preview_is_domain_zero_write(self):
        self.event_for_row(status=ServiceEvent.STATUS_COMPLETED)
        before = self._domain_snapshot()
        review = self.mapping_review()
        preview = build_sound_assignment_preview(
            mapping_review=review,
            selected_mapping={"Alice": self.alice_membership.pk},
            user=self.staff,
            now=self.preview_now(),
        )
        self.assertEqual(
            preview.rows[0].target_state,
            SoundTargetState.HISTORICAL_EVENT_BLOCKER,
        )
        self.assertEqual(self._domain_snapshot(), before)

    def test_historical_event_blocker_has_bilingual_preview_copy(self):
        self.event_for_row(status=ServiceEvent.STATUS_COMPLETED)
        self.client.force_login(self.staff)
        for language, expected in (
            ("en", "Historical event — backfill not supported"),
            ("zh", "历史聚会 — 当前版本不补建排班"),
        ):
            with self.subTest(language=language):
                session = self.client.session
                session["language"] = language
                session.save()
                upload_response = self.client.post(
                    reverse("sound_assignment_workbook_preview"),
                    {"workbook": self.upload({4: "Alice"})},
                )
                review = upload_response.context["mapping_review"]
                preview_response = self.client.post(
                    reverse("sound_assignment_workbook_preview"),
                    {
                        "signed_mapping_state": review.signed_state,
                        "mapping_0": str(self.alice_membership.pk),
                    },
                )
                self.assertContains(preview_response, expected)
