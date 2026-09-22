"""Focused MO-S.6F.1C Sound existing-roster update tests."""

from copy import deepcopy
import json
from unittest.mock import patch

from django.contrib.admin.models import CHANGE, LogEntry
from django.contrib.auth.models import User
from django.core import signing
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from events.models import ServiceEvent
from notifications.models import Notification

from .models import TeamAssignment, TeamAssignmentMember, TeamMembership
from .services.sound_assignment_xlsx_confirmation import (
    CONFIRMATION_SIGNING_SALT,
    SoundAssignmentConfirmationError,
    SoundAssignmentConfirmationProposalError,
    build_sound_assignment_confirmation_proposal,
    decode_signed_sound_assignment_confirmation,
)
from .services.sound_assignment_xlsx_preview import (
    INTEGRATION_KEY,
    SoundTargetState,
    build_sound_assignment_preview,
    prepare_sound_assignment_mapping,
)
from .services.sound_assignment_xlsx_roster_update import (
    ROSTER_UPDATE_CONTRACT_REVISION,
    ROSTER_UPDATE_SIGNING_SALT,
    build_sound_roster_update_proposal,
    confirm_sound_roster_update,
    decode_signed_sound_roster_update,
    _valid_hash,
)
from .test_sound_assignment_xlsx_preview import SoundAssignmentPreviewTestBase


@override_settings(CMS_ENABLED_INTEGRATIONS=[INTEGRATION_KEY])
class SoundRosterUpdateTests(SoundAssignmentPreviewTestBase):
    def setUp(self):
        self.bob = TeamMembership.objects.create(
            team=self.sound,
            display_name="Bob Visible",
            email="bob-private@example.test",
            notes="bob private notes",
        )

    def _assignment(
        self,
        event,
        *,
        status=TeamAssignment.STATUS_SCHEDULED,
        membership=None,
        confirmed_at=None,
        confirmation_note="",
        fingerprint="b" * 64,
    ):
        assignment = TeamAssignment.objects.create(
            service_event=event,
            ministry_team=self.sound,
            status=status,
            notes="preserve parent notes byte-for-byte",
            created_by=self.superuser,
            reviewed_worship_context_fingerprint=fingerprint,
        )
        member = None
        if membership is not None:
            member = TeamAssignmentMember.objects.create(
                assignment=assignment,
                membership=membership,
                confirmed_at=confirmed_at,
                confirmation_note=confirmation_note,
            )
        return assignment, member

    def _preview(self, overrides=None, mapping=None):
        review = prepare_sound_assignment_mapping(
            content=self.workbook(overrides or {4: "Alice"}),
            filename="annual.xlsx",
            user=self.staff,
        )
        return build_sound_assignment_preview(
            mapping_review=review,
            selected_mapping=mapping or {"Alice": self.alice_membership.pk},
            user=self.staff,
            now=self.preview_now(),
        )

    def _proposal(self, preview):
        with patch(
            "ministry.services.sound_assignment_xlsx_roster_update.timezone.now",
            return_value=self.preview_now(),
        ):
            proposal = build_sound_roster_update_proposal(
                preview=preview, user=self.staff
            )
        return proposal, decode_signed_sound_roster_update(
            proposal.signed_payload, user=self.staff
        )

    def _confirm(self, payload):
        with patch(
            "ministry.services.sound_assignment_xlsx_roster_update.timezone.now",
            return_value=self.preview_now(),
        ):
            return confirm_sound_roster_update(user=self.staff, payload=payload)

    def test_preview_fill_replace_noop_and_confirmation_blocker_matrix(self):
        event = self.event_for_row()
        assignment, _member = self._assignment(event)
        event.refresh_from_db()
        revision_before = event.scheduling_revision
        preview = self._preview()
        self.assertEqual(preview.rows[0].target_state, SoundTargetState.FILL_CANDIDATE)

        assignment.delete()
        assignment, old = self._assignment(event, membership=self.bob)
        preview = self._preview()
        self.assertEqual(
            preview.rows[0].target_state, SoundTargetState.REPLACE_CANDIDATE
        )
        self.assertEqual(preview.rows[0].current_membership.membership_id, self.bob.pk)

        old.delete()
        same = TeamAssignmentMember.objects.create(
            assignment=assignment,
            membership=self.alice_membership,
            confirmed_at=self.preview_now(),
            confirmation_note="preserve private confirmation text",
        )
        self.assertEqual(
            self._preview().rows[0].target_state, SoundTargetState.EXACT_NOOP
        )

        same.delete()
        TeamAssignmentMember.objects.create(
            assignment=assignment,
            membership=self.bob,
            confirmed_at=self.preview_now(),
        )
        self.assertEqual(
            self._preview().rows[0].target_state,
            SoundTargetState.EXISTING_ROSTER_BLOCKER,
        )
        TeamAssignmentMember.objects.filter(assignment=assignment).update(
            confirmed_at=None,
            confirmation_note="do not erase",
        )
        self.assertEqual(
            self._preview().rows[0].target_state,
            SoundTargetState.EXISTING_ROSTER_BLOCKER,
        )

    def test_canonical_lowercase_fingerprint_allows_fill_candidate(self):
        event = self.event_for_row()
        assignment, _member = self._assignment(event, fingerprint="b" * 64)

        preview = self._preview()

        self.assertEqual(preview.rows[0].target_state, SoundTargetState.FILL_CANDIDATE)
        assignment.refresh_from_db()
        self.assertEqual(
            assignment.reviewed_worship_context_fingerprint,
            "b" * 64,
        )

    def test_canonical_lowercase_fingerprint_allows_replace_candidate(self):
        event = self.event_for_row()
        assignment, _member = self._assignment(
            event,
            membership=self.bob,
            fingerprint="b" * 64,
        )

        preview = self._preview()

        self.assertEqual(
            preview.rows[0].target_state,
            SoundTargetState.REPLACE_CANDIDATE,
        )
        assignment.refresh_from_db()
        self.assertEqual(
            assignment.reviewed_worship_context_fingerprint,
            "b" * 64,
        )

    def test_canonical_lowercase_fingerprint_allows_exact_noop(self):
        event = self.event_for_row()
        assignment, _member = self._assignment(
            event,
            membership=self.alice_membership,
            fingerprint="b" * 64,
        )

        preview = self._preview()

        self.assertEqual(preview.rows[0].target_state, SoundTargetState.EXACT_NOOP)
        assignment.refresh_from_db()
        self.assertEqual(
            assignment.reviewed_worship_context_fingerprint,
            "b" * 64,
        )

    def test_confirmed_and_prepared_exact_noop_but_difference_blocks(self):
        for status in (
            TeamAssignment.STATUS_CONFIRMED,
            TeamAssignment.STATUS_PREPARED,
        ):
            with self.subTest(status=status):
                TeamAssignment.objects.all().delete()
                ServiceEvent.objects.all().delete()
                event = self.event_for_row()
                _assignment, member = self._assignment(
                    event, status=status, membership=self.alice_membership
                )
                self.assertEqual(
                    self._preview().rows[0].target_state,
                    SoundTargetState.EXACT_NOOP,
                )
                member.delete()
                TeamAssignmentMember.objects.create(
                    assignment=_assignment, membership=self.bob
                )
                self.assertEqual(
                    self._preview().rows[0].target_state,
                    SoundTargetState.EXISTING_ROSTER_BLOCKER,
                )

    def test_multiple_inactive_and_malformed_fingerprint_block(self):
        event = self.event_for_row()
        assignment, _old = self._assignment(event, membership=self.bob)
        TeamAssignmentMember.objects.create(
            assignment=assignment, membership=self.alice_membership
        )
        self.assertEqual(
            self._preview().rows[0].target_state,
            SoundTargetState.EXISTING_ROSTER_BLOCKER,
        )
        TeamAssignmentMember.objects.filter(
            assignment=assignment, membership=self.alice_membership
        ).delete()
        TeamMembership.objects.filter(pk=self.bob.pk).update(is_active=False)
        self.assertEqual(
            self._preview().rows[0].target_state,
            SoundTargetState.EXISTING_ROSTER_BLOCKER,
        )
        TeamMembership.objects.filter(pk=self.bob.pk).update(is_active=True)
        TeamAssignment.objects.filter(pk=assignment.pk).update(
            reviewed_worship_context_fingerprint="malformed"
        )
        self.assertEqual(
            self._preview().rows[0].target_state,
            SoundTargetState.INVALID_ASSIGNMENT_BLOCKER,
        )

    def test_noncanonical_worship_fingerprints_fail_closed_but_none_is_valid(self):
        event = self.event_for_row()
        assignment, _member = self._assignment(event, fingerprint=None)
        self.assertEqual(
            self._preview().rows[0].target_state,
            SoundTargetState.FILL_CANDIDATE,
        )

        for fingerprint in (
            "B" * 64,
            "b" * 63 + "B",
            "b" * 63,
            "b" * 65,
            "g" * 64,
            "malformed",
        ):
            with self.subTest(fingerprint=fingerprint):
                TeamAssignment.objects.filter(pk=assignment.pk).update(
                    reviewed_worship_context_fingerprint=fingerprint
                )
                self.assertEqual(
                    self._preview().rows[0].target_state,
                    SoundTargetState.INVALID_ASSIGNMENT_BLOCKER,
                )

    def test_proposal_accepts_lowercase_fingerprint_and_keeps_uppercase_hashes(self):
        event = self.event_for_row()
        self._assignment(event, fingerprint="0123456789abcdef" * 4)

        proposal, payload = self._proposal(self._preview())

        self.assertEqual(
            payload["rows"][0]["assignment_baseline"][0][
                "reviewed_worship_context_fingerprint"
            ],
            "0123456789abcdef" * 4,
        )
        self.assertEqual(
            decode_signed_sound_roster_update(
                proposal.signed_payload,
                user=self.staff,
            ),
            payload,
        )
        self.assertTrue(_valid_hash(payload["workbook_sha256"]))
        self.assertTrue(_valid_hash(payload["preview_digest"]))
        self.assertEqual(
            payload["workbook_sha256"], payload["workbook_sha256"].upper()
        )
        self.assertEqual(
            payload["preview_digest"], payload["preview_digest"].upper()
        )
        self.assertFalse(_valid_hash("a" * 64))

        uppercase_fingerprint = deepcopy(payload)
        uppercase_fingerprint["rows"][0]["assignment_baseline"][0][
            "reviewed_worship_context_fingerprint"
        ] = "B" * 64
        with self.assertRaises(SoundAssignmentConfirmationProposalError):
            decode_signed_sound_roster_update(
                signing.dumps(
                    uppercase_fingerprint,
                    salt=ROSTER_UPDATE_SIGNING_SALT,
                ),
                user=self.staff,
            )

    def test_fill_preserves_parent_revision_fingerprint_and_is_idempotent(self):
        event = self.event_for_row()
        fingerprint = "0123456789abcdef" * 4
        assignment, _member = self._assignment(event, fingerprint=fingerprint)
        event.refresh_from_db()
        revision_before = event.scheduling_revision
        parent_before = TeamAssignment.objects.values().get(pk=assignment.pk)
        proposal, payload = self._proposal(self._preview())
        self.assertEqual(
            payload["confirmation_contract_revision"],
            ROSTER_UPDATE_CONTRACT_REVISION,
        )
        self.assertNotIn("filename", payload)
        self.assertNotIn("Alice", str(payload))
        self.assertNotIn(assignment.notes, str(payload))

        result = self._confirm(payload)

        self.assertEqual(result.filled_assignment_ids, (assignment.pk,))
        self.assertEqual(result.replaced_assignment_ids, ())
        event.refresh_from_db()
        self.assertEqual(event.scheduling_revision, revision_before)
        parent_after = TeamAssignment.objects.values().get(pk=assignment.pk)
        self.assertEqual(parent_after, parent_before)
        self.assertEqual(
            parent_after["reviewed_worship_context_fingerprint"], fingerprint
        )
        member = TeamAssignmentMember.objects.get(assignment=assignment)
        self.assertEqual(member.membership_id, self.alice_membership.pk)
        self.assertIsNone(member.confirmed_at)
        self.assertEqual(member.confirmation_note, "")
        self.assertEqual(Notification.objects.count(), 0)
        log = LogEntry.objects.get()
        self.assertEqual(log.action_flag, CHANGE)
        audit = json.loads(log.change_message)
        self.assertEqual(audit["action"], "fill")
        self.assertIsNone(audit["removed_membership_id"])
        self.assertEqual(audit["added_membership_id"], self.alice_membership.pk)
        for private in (assignment.notes, "Alice", self.alice_membership.email):
            self.assertNotIn(private, log.change_message)

        fresh = self._preview()
        self.assertEqual(fresh.rows[0].target_state, SoundTargetState.EXACT_NOOP)
        self.assertFalse(fresh.is_confirmable)
        with self.assertRaises(SoundAssignmentConfirmationError):
            self._confirm(payload)
        self.assertEqual(LogEntry.objects.count(), 1)

    def test_replace_deletes_exact_old_row_and_adds_unconfirmed_member(self):
        event = self.event_for_row()
        fingerprint = "fedcba9876543210" * 4
        assignment, old = self._assignment(
            event,
            membership=self.bob,
            fingerprint=fingerprint,
        )
        event.refresh_from_db()
        revision_before = event.scheduling_revision
        parent_before = TeamAssignment.objects.values().get(pk=assignment.pk)
        _proposal, payload = self._proposal(self._preview())

        result = self._confirm(payload)

        self.assertEqual(result.replaced_assignment_ids, (assignment.pk,))
        self.assertEqual(result.removed_member_ids, (old.pk,))
        self.assertFalse(TeamAssignmentMember.objects.filter(pk=old.pk).exists())
        new = TeamAssignmentMember.objects.get(assignment=assignment)
        self.assertEqual(new.pk, result.added_member_ids[0])
        self.assertEqual(new.membership_id, self.alice_membership.pk)
        self.assertIsNone(new.confirmed_at)
        self.assertEqual(new.confirmation_note, "")
        self.assertEqual(
            TeamAssignment.objects.values().get(pk=assignment.pk), parent_before
        )
        self.assertEqual(
            TeamAssignment.objects.values_list(
                "reviewed_worship_context_fingerprint", flat=True
            ).get(pk=assignment.pk),
            fingerprint,
        )
        event.refresh_from_db()
        self.assertEqual(event.scheduling_revision, revision_before)
        audit = json.loads(LogEntry.objects.get().change_message)
        self.assertEqual(audit["removed_membership_id"], self.bob.pk)
        self.assertEqual(audit["added_membership_id"], self.alice_membership.pk)

    def test_mixed_create_replace_advances_only_create_event_once(self):
        replace_event = self.event_for_row(0)
        create_event = self.event_for_row(1)
        assignment, _old = self._assignment(replace_event, membership=self.bob)
        replace_event.refresh_from_db()
        replace_revision_before = replace_event.scheduling_revision
        preview = self._preview(
            {4: "Alice", 6: "Alice"},
            {"Alice": self.alice_membership.pk},
        )
        self.assertEqual(preview.replace_candidate_count, 1)
        self.assertEqual(preview.create_candidate_count, 1)
        _proposal, payload = self._proposal(preview)

        result = self._confirm(payload)

        replace_event.refresh_from_db()
        create_event.refresh_from_db()
        self.assertEqual(
            replace_event.scheduling_revision, replace_revision_before
        )
        self.assertEqual(create_event.scheduling_revision, 1)
        self.assertEqual(result.claimed_event_ids, (create_event.pk,))
        self.assertEqual(result.replaced_assignment_ids, (assignment.pk,))
        self.assertEqual(result.created_count, 1)
        self.assertEqual(LogEntry.objects.count(), 2)
        self.assertEqual(
            {json.loads(item.change_message)["operation_id"] for item in LogEntry.objects.all()},
            {result.operation_id},
        )

    def test_distinct_signatures_wrong_user_expiry_tamper_and_create_only_gate(self):
        event = self.event_for_row()
        self._assignment(event)
        proposal, _payload = self._proposal(self._preview())
        with self.assertRaises(SoundAssignmentConfirmationProposalError):
            decode_signed_sound_assignment_confirmation(
                proposal.signed_payload, user=self.staff
            )
        with self.assertRaises(SoundAssignmentConfirmationProposalError):
            decode_signed_sound_roster_update(
                signing.dumps({}, salt=CONFIRMATION_SIGNING_SALT), user=self.staff
            )
        with self.assertRaises(SoundAssignmentConfirmationProposalError):
            decode_signed_sound_roster_update(
                proposal.signed_payload, user=self.superuser
            )
        with self.assertRaises(SoundAssignmentConfirmationProposalError):
            decode_signed_sound_roster_update(
                proposal.signed_payload, user=self.staff, max_age=-1
            )
        with self.assertRaises(SoundAssignmentConfirmationProposalError):
            decode_signed_sound_roster_update(
                proposal.signed_payload + "tamper", user=self.staff
            )
        resigned = deepcopy(proposal.normalized_payload)
        resigned["rows"][0]["mutation"]["assignment_id"] += 1
        with self.assertRaises(SoundAssignmentConfirmationProposalError):
            decode_signed_sound_roster_update(
                signing.dumps(resigned, salt=ROSTER_UPDATE_SIGNING_SALT),
                user=self.staff,
            )

        TeamAssignment.objects.all().delete()
        create_only = self._preview()
        self.assertEqual(create_only.create_candidate_count, 1)
        with self.assertRaises(SoundAssignmentConfirmationProposalError):
            build_sound_roster_update_proposal(preview=create_only, user=self.staff)
        create_proposal = build_sound_assignment_confirmation_proposal(
            preview=create_only, user=self.staff
        )
        self.assertIsNotNone(create_proposal)
        with self.assertRaises(SoundAssignmentConfirmationProposalError):
            decode_signed_sound_roster_update(
                create_proposal.signed_payload, user=self.staff
            )

    def test_proposal_mint_fails_if_reviewed_destination_or_old_identity_drifted(self):
        event = self.event_for_row()
        _assignment, _old = self._assignment(event, membership=self.bob)
        preview = self._preview()
        self.alice_membership.display_name = "Alice changed after review"
        self.alice_membership.save(update_fields=["display_name", "updated_at"])
        with self.assertRaises(SoundAssignmentConfirmationProposalError):
            self._proposal(preview)

        self.alice_membership.display_name = "Alice"
        self.alice_membership.save(update_fields=["display_name", "updated_at"])
        preview = self._preview()
        self.bob.display_name = "Bob changed after review"
        self.bob.save(update_fields=["display_name", "updated_at"])
        with self.assertRaises(SoundAssignmentConfirmationProposalError):
            self._proposal(preview)

    def test_post_barrier_authority_and_integration_drift_roll_back(self):
        event = self.event_for_row()
        assignment, _old = self._assignment(event, membership=self.bob)
        _proposal, payload = self._proposal(self._preview())
        from .services import sound_assignment_xlsx_roster_update as service

        User.objects.filter(pk=self.staff.pk).update(is_staff=False)
        with self.assertRaises(SoundAssignmentConfirmationError):
            self._confirm(payload)
        User.objects.filter(pk=self.staff.pk).update(is_staff=True)
        self.staff.refresh_from_db()
        self.assertEqual(LogEntry.objects.count(), 0)

        from core.integration_registry import IntegrationDisabled

        with patch.object(
            service,
            "require_integration_enabled",
            side_effect=IntegrationDisabled("disabled"),
        ):
            with self.assertRaises(SoundAssignmentConfirmationError):
                self._confirm(payload)
        self.assertEqual(LogEntry.objects.count(), 0)

        original_barrier = service._conditional_assignment_barriers

        def remove_authority(rows):
            original_barrier(rows)
            User.objects.filter(pk=self.staff.pk).update(is_staff=False)

        with patch.object(
            service, "_conditional_assignment_barriers", side_effect=remove_authority
        ):
            with self.assertRaises(SoundAssignmentConfirmationError):
                self._confirm(payload)
        self.staff.refresh_from_db()
        self.assertTrue(self.staff.is_staff)
        self.assertEqual(
            TeamAssignmentMember.objects.get(assignment=assignment).membership_id,
            self.bob.pk,
        )
        self.assertEqual(LogEntry.objects.count(), 0)

        calls = []

        def integration_then_fail(_key):
            calls.append(True)
            if len(calls) == 2:
                raise IntegrationDisabled("disabled")

        with patch.object(
            service, "require_integration_enabled", side_effect=integration_then_fail
        ):
            with self.assertRaises(SoundAssignmentConfirmationError):
                self._confirm(payload)
        self.assertEqual(LogEntry.objects.count(), 0)

    def test_delete_or_audit_failure_rolls_back_entire_replacement(self):
        event = self.event_for_row()
        assignment, old = self._assignment(event, membership=self.bob)
        _proposal, payload = self._proposal(self._preview())
        with patch.object(
            LogEntry.objects,
            "log_action",
            side_effect=RuntimeError("audit unavailable"),
        ):
            with self.assertRaises(SoundAssignmentConfirmationError):
                self._confirm(payload)
        self.assertTrue(TeamAssignmentMember.objects.filter(pk=old.pk).exists())
        self.assertEqual(
            TeamAssignmentMember.objects.get(assignment=assignment).membership_id,
            self.bob.pk,
        )
        self.assertEqual(LogEntry.objects.count(), 0)

        original_save = TeamAssignmentMember.save

        def fail_new_member(instance, *args, **kwargs):
            if instance.membership_id == self.alice_membership.pk:
                raise RuntimeError("insert failed")
            return original_save(instance, *args, **kwargs)

        with patch.object(TeamAssignmentMember, "save", new=fail_new_member):
            with self.assertRaises(RuntimeError):
                self._confirm(payload)
        self.assertTrue(TeamAssignmentMember.objects.filter(pk=old.pk).exists())
        self.assertEqual(LogEntry.objects.count(), 0)

        with patch("django.db.models.query.QuerySet.delete", return_value=(0, {})):
            with self.assertRaises(SoundAssignmentConfirmationError):
                self._confirm(payload)
        self.assertTrue(TeamAssignmentMember.objects.filter(pk=old.pk).exists())

        from .services import sound_assignment_xlsx_roster_update as service

        with patch.object(
            service,
            "_assert_postconditions",
            side_effect=SoundAssignmentConfirmationError("postcondition failed"),
        ):
            with self.assertRaises(SoundAssignmentConfirmationError):
                self._confirm(payload)
        self.assertTrue(TeamAssignmentMember.objects.filter(pk=old.pk).exists())
        self.assertEqual(LogEntry.objects.count(), 0)
