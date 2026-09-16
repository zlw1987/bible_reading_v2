"""Focused MO-S.6F.1B Sound create-only confirmation tests."""

from copy import deepcopy
import copy
import os
from datetime import datetime, time, timedelta
import json
import tempfile
import unittest
from unittest.mock import patch

from django.contrib.admin.models import LogEntry
from django.contrib.auth.models import User
from django.core.management import call_command
from django.core import signing
from django.db import OperationalError, close_old_connections, connections
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import ChurchStructureMembership
from core.integration_registry import IntegrationDisabled
from events.models import ServiceEvent, ServiceEventRequiredTeam
from events.scheduling_revision import SchedulingRevisionError, advance_scheduling_revisions
from events.test_worship_xlsx_preview import build_known_workbook
from notifications.models import Notification

from .models import TeamAssignment, TeamAssignmentMember, TeamMembership
from .services.sound_assignment_xlsx_confirmation import (
    CONFIRMATION_CONTRACT_REVISION,
    CONFIRMATION_SIGNING_SALT,
    SoundAssignmentConfirmationAuditError,
    SoundAssignmentConfirmationError,
    SoundAssignmentConfirmationProposalError,
    build_sound_assignment_confirmation_proposal,
    confirm_sound_assignments,
    decode_signed_sound_assignment_confirmation,
)
from .services.sound_assignment_xlsx_preview import (
    INTEGRATION_KEY,
    SoundTargetState,
    build_sound_assignment_preview,
    prepare_sound_assignment_mapping,
)
from .services.sound_assignment_xlsx_roster_update import (
    build_sound_roster_update_proposal,
    confirm_sound_roster_update,
    decode_signed_sound_roster_update,
)
from .test_sound_assignment_xlsx_preview import SoundAssignmentPreviewTestBase


@override_settings(CMS_ENABLED_INTEGRATIONS=[INTEGRATION_KEY])
class SoundAssignmentConfirmationTests(SoundAssignmentPreviewTestBase):
    def _reviewed_preview(self, sound_overrides, mapping, *, now=None):
        review = prepare_sound_assignment_mapping(
            content=self.workbook(sound_overrides),
            filename="annual.xlsx",
            user=self.staff,
        )
        return build_sound_assignment_preview(
            mapping_review=review,
            selected_mapping=mapping,
            user=self.staff,
            now=now or self.preview_now(),
        )

    def _proposal(self, preview=None):
        preview = preview or self.preview()
        with patch(
            "ministry.services.sound_assignment_xlsx_confirmation.timezone.now",
            return_value=self.preview_now(),
        ):
            proposal = build_sound_assignment_confirmation_proposal(
                preview=preview,
                user=self.staff,
            )
        payload = decode_signed_sound_assignment_confirmation(
            proposal.signed_payload,
            user=self.staff,
        )
        return proposal, payload

    def _confirm(self, payload):
        with patch(
            "ministry.services.sound_assignment_xlsx_confirmation.timezone.now",
            return_value=self.preview_now(),
        ):
            return confirm_sound_assignments(user=self.staff, payload=payload)

    def test_separate_contract_binds_full_create_and_safe_nonwrite_set(self):
        create_event = self.event_for_row(0)
        noop_event = self.event_for_row(1)
        noop = TeamAssignment.objects.create(
            service_event=noop_event,
            ministry_team=self.sound,
            status=TeamAssignment.STATUS_SCHEDULED,
        )
        TeamAssignmentMember.objects.create(
            assignment=noop, membership=self.alice_membership
        )
        noop.refresh_from_db()
        noop_before = (
            noop.status,
            noop.notes,
            noop.reviewed_worship_context_fingerprint,
            noop.updated_at,
        )
        historical_event = self.event_for_row(
            2, status=ServiceEvent.STATUS_COMPLETED
        )
        preview = self._reviewed_preview(
            {4: "Alice", 6: "Alice", 7: "Alice"},
            {"Alice": self.alice_membership.pk},
        )
        self.assertTrue(preview.is_confirmable)
        self.assertEqual(preview.hard_blocker_count, 0)
        proposal, payload = self._proposal(preview)
        self.assertEqual(
            payload["confirmation_contract_revision"],
            CONFIRMATION_CONTRACT_REVISION,
        )
        self.assertEqual(
            payload["summary"],
            {
                "create_count": 1,
                "exact_noop_count": 1,
                "historical_event_count": 1,
                "no_source_count": 49,
                "hard_blocker_count": 0,
            },
        )
        self.assertNotEqual(proposal.signed_payload, preview.signed_payload)
        self.assertNotIn("Alice", str(payload))

        before_revisions = {
            event.pk: ServiceEvent.objects.get(pk=event.pk).scheduling_revision
            for event in (create_event, noop_event, historical_event)
        }
        result = self._confirm(payload)
        self.assertEqual(result.created_count, 1)
        self.assertEqual(result.claimed_event_ids, (create_event.pk,))
        for event in (create_event, noop_event, historical_event):
            event.refresh_from_db()
        self.assertEqual(
            create_event.scheduling_revision, before_revisions[create_event.pk] + 1
        )
        self.assertEqual(
            noop_event.scheduling_revision, before_revisions[noop_event.pk]
        )
        self.assertEqual(
            historical_event.scheduling_revision,
            before_revisions[historical_event.pk],
        )
        self.assertEqual(TeamAssignment.objects.count(), 2)
        noop.refresh_from_db()
        self.assertEqual(
            (
                noop.status,
                noop.notes,
                noop.reviewed_worship_context_fingerprint,
                noop.updated_at,
            ),
            noop_before,
        )

    def test_create_has_exact_parent_member_fingerprint_and_audit_semantics(self):
        event = self.event_for_row()
        before_users = User.objects.count()
        before_memberships = TeamMembership.objects.count()
        before_required = ServiceEventRequiredTeam.objects.count()
        before_anchor = event.rotation_anchor_team_id
        _proposal, payload = self._proposal()

        result = self._confirm(payload)

        event.refresh_from_db()
        self.assertEqual(event.scheduling_revision, 1)
        self.assertEqual(event.rotation_anchor_team_id, before_anchor)
        assignment = TeamAssignment.objects.get(pk=result.created_assignment_ids[0])
        member = TeamAssignmentMember.objects.get(pk=result.created_member_ids[0])
        self.assertEqual(assignment.service_event_id, event.pk)
        self.assertEqual(assignment.ministry_team_id, self.sound.pk)
        self.assertEqual(assignment.status, TeamAssignment.STATUS_SCHEDULED)
        self.assertEqual(assignment.notes, "")
        self.assertEqual(assignment.created_by_id, self.staff.pk)
        self.assertIsNone(assignment.reviewed_worship_context_fingerprint)
        self.assertEqual(member.assignment_id, assignment.pk)
        self.assertEqual(member.membership_id, self.alice_membership.pk)
        self.assertIsNone(member.confirmed_at)
        self.assertEqual(member.confirmation_note, "")
        self.assertEqual(User.objects.count(), before_users)
        self.assertEqual(TeamMembership.objects.count(), before_memberships)
        self.assertEqual(ServiceEventRequiredTeam.objects.count(), before_required)
        self.assertEqual(Notification.objects.count(), 0)

        log = LogEntry.objects.get()
        audit = json.loads(log.change_message)
        self.assertEqual(audit["operation_id"], result.operation_id)
        self.assertEqual(audit["created_team_assignment_id"], assignment.pk)
        self.assertEqual(
            audit["selected_team_membership_id"], self.alice_membership.pk
        )
        for private_value in (
            self.alice_membership.display_name,
            self.alice_membership.email,
            self.alice_membership.notes,
        ):
            self.assertNotIn(private_value, log.change_message)

    def test_multiple_create_events_each_advance_exactly_once(self):
        first = self.event_for_row(0)
        second = self.event_for_row(1)
        preview = self._reviewed_preview(
            {4: "Alice", 6: "Alice"},
            {"Alice": self.alice_membership.pk},
        )
        _proposal, payload = self._proposal(preview)
        result = self._confirm(payload)
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual((first.scheduling_revision, second.scheduling_revision), (1, 1))
        self.assertEqual(set(result.claimed_event_ids), {first.pk, second.pk})
        self.assertEqual(TeamAssignment.objects.count(), 2)
        self.assertEqual(TeamAssignmentMember.objects.count(), 2)
        self.assertEqual(LogEntry.objects.count(), 2)
        self.assertEqual(
            {json.loads(log.change_message)["operation_id"] for log in LogEntry.objects.all()},
            {result.operation_id},
        )

    def test_zero_create_and_any_hard_blocker_mint_no_confirmation(self):
        self.event_for_row()
        blank = self._reviewed_preview({}, {})
        self.assertFalse(blank.is_confirmable)
        with self.assertRaises(SoundAssignmentConfirmationProposalError):
            build_sound_assignment_confirmation_proposal(
                preview=blank, user=self.staff
            )

        assignment = TeamAssignment.objects.create(
            service_event=ServiceEvent.objects.get(),
            ministry_team=self.sound,
            status=TeamAssignment.STATUS_SCHEDULED,
        )
        TeamAssignmentMember.objects.create(
            assignment=assignment,
            membership=self.display_only,
            confirmation_note="preserve confirmation evidence",
        )
        blocked = self.preview()
        self.assertEqual(
            blocked.rows[0].target_state,
            SoundTargetState.EXISTING_ROSTER_BLOCKER,
        )
        self.assertEqual(blocked.hard_blocker_count, 1)
        with self.assertRaises(SoundAssignmentConfirmationProposalError):
            build_sound_assignment_confirmation_proposal(
                preview=blocked, user=self.staff
            )

    def test_audience_linked_outside_blocks_but_display_only_is_allowed(self):
        self.event_for_row()
        outsider = User.objects.create_user("outside", password="pw")
        outside_membership = TeamMembership.objects.create(
            team=self.sound, user=outsider, display_name="Outside"
        )
        outside = self._reviewed_preview(
            {4: "Outside"}, {"Outside": outside_membership.pk}
        )
        self.assertEqual(
            outside.rows[0].target_state,
            SoundTargetState.AUDIENCE_SAFETY_BLOCKER,
        )
        self.assertFalse(outside.is_confirmable)

        display_only = self._reviewed_preview(
            {4: "O'Neil-Smith"}, {"O'Neil-Smith": self.display_only.pk}
        )
        self.assertEqual(
            display_only.rows[0].target_state,
            SoundTargetState.CREATE_CANDIDATE,
        )
        self.assertTrue(display_only.is_confirmable)

    def test_assignment_appearing_without_revision_bump_rolls_back_claim(self):
        event = self.event_for_row()
        _proposal, payload = self._proposal()
        TeamAssignment(
            service_event=event,
            ministry_team=self.sound,
            status=TeamAssignment.STATUS_SCHEDULED,
        ).save(_skip_scheduling_revision=True)
        with self.assertRaises(SoundAssignmentConfirmationError):
            self._confirm(payload)
        event.refresh_from_db()
        self.assertEqual(event.scheduling_revision, 0)
        self.assertEqual(TeamAssignment.objects.count(), 1)


class FileBackedSQLiteSoundAssignmentConfirmationTests(unittest.TestCase):
    """Two real SQLite connections prove the CAS is the first-writer boundary."""

    competing_alias = "sound_assignment_competing"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        handle = tempfile.NamedTemporaryFile(
            prefix="sound-assignment-confirmation-", suffix=".sqlite3", delete=False
        )
        cls.database_path = handle.name
        handle.close()
        cls.original_default_config = copy.deepcopy(connections.databases["default"])
        connections["default"].close()
        if hasattr(connections._connections, "default"):
            delattr(connections._connections, "default")
        file_config = copy.deepcopy(cls.original_default_config)
        file_config["NAME"] = cls.database_path
        file_config["OPTIONS"] = {**file_config.get("OPTIONS", {}), "timeout": 0.1}
        file_config["TEST"] = {"NAME": None}
        connections.databases["default"] = file_config
        call_command("migrate", database="default", interactive=False, verbosity=0)
        competing_config = copy.deepcopy(file_config)
        competing_config["TEST"] = {"NAME": None}
        connections.databases[cls.competing_alias] = competing_config
        with connections["default"].cursor() as cursor:
            mode = cursor.execute("PRAGMA journal_mode=delete").fetchone()[0]
            cursor.execute("PRAGMA busy_timeout=100")
        with connections[cls.competing_alias].cursor() as cursor:
            cursor.execute("PRAGMA busy_timeout=100")
        if mode.lower() != "delete":
            raise AssertionError(f"Unexpected SQLite journal mode: {mode}")

    @classmethod
    def tearDownClass(cls):
        for alias in (cls.competing_alias, "default"):
            if alias in connections.databases:
                connections[alias].close()
            if hasattr(connections._connections, alias):
                delattr(connections._connections, alias)
        connections.databases.pop(cls.competing_alias, None)
        connections.databases["default"] = cls.original_default_config
        if os.path.exists(cls.database_path):
            os.remove(cls.database_path)
        super().tearDownClass()

    def setUp(self):
        self.integration_override = override_settings(
            CMS_ENABLED_INTEGRATIONS=[INTEGRATION_KEY]
        )
        self.integration_override.enable()
        call_command("flush", database="default", interactive=False, verbosity=0)
        from accounts.models import ChurchStructureUnit
        from events.models import ServiceEventAudienceScope, ServiceProfile
        from ministry.models import MinistryTeam

        self.now = timezone.make_aware(
            datetime(2026, 1, 4, 8, 0), timezone.get_current_timezone()
        )
        self.profile = ServiceProfile.objects.create(
            key="bethany_0930_cm",
            name="Bethany 09:30",
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
        )
        root = ChurchStructureUnit.objects.create(
            code="ROOT", name="Root", unit_type=ChurchStructureUnit.UNIT_ROOT
        )
        self.cm = ChurchStructureUnit.objects.create(
            code="CM",
            name="CM",
            unit_type=ChurchStructureUnit.UNIT_MINISTRY_CONTEXT,
            parent=root,
        )
        self.sound = MinistryTeam.objects.create(
            name="Sound",
            team_key="main.cm.digital.sound",
            is_active=True,
            is_assignable=True,
        )
        self.staff = User.objects.create_user("file_sound_staff", is_staff=True)
        self.alice = User.objects.create_user(
            "file_sound_alice", first_name="Alice"
        )
        ChurchStructureMembership.objects.create(
            user=self.alice,
            unit=self.cm,
            status=ChurchStructureMembership.STATUS_ACTIVE,
            is_primary=True,
            start_date=timezone.datetime(2020, 1, 1).date(),
        )
        self.membership = TeamMembership.objects.create(
            team=self.sound, user=self.alice, display_name="Alice"
        )
        self.ServiceEventAudienceScope = ServiceEventAudienceScope

    def tearDown(self):
        self.integration_override.disable()

    def event(self, row_index):
        local_day = timezone.datetime(2026, 1, 4).date() + timedelta(weeks=row_index)
        event = ServiceEvent.objects.create(
            title=f"Sunday {row_index}",
            service_profile=self.profile,
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
            start_datetime=timezone.make_aware(
                datetime.combine(local_day, time(9, 30)),
                timezone.get_current_timezone(),
            ),
            status=ServiceEvent.STATUS_PUBLISHED,
        )
        self.ServiceEventAudienceScope.objects.create(
            service_event=event, unit=self.cm
        )
        return event

    def payload(self, events):
        source_rows = [4, *range(6, 57)]
        overrides = {source_rows[index]: "Alice" for index in range(len(events))}
        review = prepare_sound_assignment_mapping(
            content=build_known_workbook(sound_overrides=overrides),
            filename="annual.xlsx",
            user=self.staff,
        )
        preview = build_sound_assignment_preview(
            mapping_review=review,
            selected_mapping={"Alice": self.membership.pk},
            user=self.staff,
            now=self.now,
        )
        with patch(
            "ministry.services.sound_assignment_xlsx_confirmation.timezone.now",
            return_value=self.now,
        ):
            proposal = build_sound_assignment_confirmation_proposal(
                preview=preview, user=self.staff
            )
        return decode_signed_sound_assignment_confirmation(
            proposal.signed_payload, user=self.staff
        )

    def confirm(self, payload):
        with patch(
            "ministry.services.sound_assignment_xlsx_confirmation.timezone.now",
            return_value=self.now,
        ):
            return confirm_sound_assignments(user=self.staff, payload=payload)

    def test_competing_supported_assignment_write_wins_first_and_claim_is_stale(self):
        event = self.event(0)
        payload = self.payload([event])
        other_event = ServiceEvent.objects.using(self.competing_alias).get(pk=event.pk)
        other_team = type(self.sound).objects.using(self.competing_alias).get(
            pk=self.sound.pk
        )
        TeamAssignment.objects.using(self.competing_alias).create(
            service_event=other_event,
            ministry_team=other_team,
            status=TeamAssignment.STATUS_SCHEDULED,
        )
        with self.assertRaises(SoundAssignmentConfirmationError):
            self.confirm(payload)
        event.refresh_from_db()
        self.assertEqual(event.scheduling_revision, 1)
        self.assertEqual(TeamAssignment.objects.count(), 1)
        self.assertEqual(TeamAssignmentMember.objects.count(), 0)
        self.assertEqual(LogEntry.objects.count(), 0)

    def test_import_claim_wins_and_blocks_competing_writer_during_transaction(self):
        event = self.event(0)
        payload = self.payload([event])
        from .services import sound_assignment_xlsx_confirmation as service

        original = service._revalidate_current_truth
        competing_busy = []
        calls = []

        def revalidate_after_competing_write(*args, **kwargs):
            calls.append(True)
            if len(calls) == 1:
                competitor = TeamAssignment(
                    service_event_id=event.pk,
                    ministry_team_id=self.sound.pk,
                    status=TeamAssignment.STATUS_SCHEDULED,
                )
                try:
                    competitor.save(using=self.competing_alias)
                except (SchedulingRevisionError, OperationalError):
                    competing_busy.append(True)
            return original(*args, **kwargs)

        with patch.object(
            service,
            "_revalidate_current_truth",
            side_effect=revalidate_after_competing_write,
        ):
            result = self.confirm(payload)

        self.assertEqual(competing_busy, [True])
        self.assertEqual(result.created_count, 1)
        event.refresh_from_db()
        self.assertEqual(event.scheduling_revision, 1)
        self.assertEqual(TeamAssignment.objects.count(), 1)
        fresh_review = prepare_sound_assignment_mapping(
            content=build_known_workbook(sound_overrides={4: "Alice"}),
            filename="annual.xlsx",
            user=self.staff,
        )
        fresh = build_sound_assignment_preview(
            mapping_review=fresh_review,
            selected_mapping={"Alice": self.membership.pk},
            user=self.staff,
            now=self.now,
        )
        self.assertEqual(fresh.rows[0].target_state, SoundTargetState.EXACT_NOOP)
        self.assertFalse(fresh.is_confirmable)

    def test_multirow_stale_claim_rolls_back_earlier_claim_and_creates_nothing(self):
        first = self.event(0)
        second = self.event(1)
        payload = self.payload([first, second])
        advance_scheduling_revisions((second.pk,), using=self.competing_alias)
        with self.assertRaises(SoundAssignmentConfirmationError):
            self.confirm(payload)
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual((first.scheduling_revision, second.scheduling_revision), (0, 1))
        self.assertEqual(TeamAssignment.objects.count(), 0)
        self.assertEqual(TeamAssignmentMember.objects.count(), 0)
        self.assertEqual(LogEntry.objects.count(), 0)

    def test_failure_after_claims_and_first_internal_create_rolls_back_all(self):
        first = self.event(0)
        second = self.event(1)
        payload = self.payload([first, second])
        original_save = TeamAssignmentMember.save
        calls = []

        def fail_second_member(instance, *args, **kwargs):
            calls.append(instance.assignment_id)
            if len(calls) == 2:
                raise RuntimeError("second member create failed")
            return original_save(instance, *args, **kwargs)

        with patch.object(TeamAssignmentMember, "save", new=fail_second_member):
            with self.assertRaises(RuntimeError):
                self.confirm(payload)
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual((first.scheduling_revision, second.scheduling_revision), (0, 0))
        self.assertEqual(TeamAssignment.objects.count(), 0)
        self.assertEqual(TeamAssignmentMember.objects.count(), 0)
        self.assertEqual(LogEntry.objects.count(), 0)
        self.assertEqual(LogEntry.objects.count(), 0)

    def roster_payload(self, event, *, include_create_event=None):
        old_membership = TeamMembership.objects.create(
            team=self.sound, display_name="Old Sound Member"
        )
        assignment = TeamAssignment.objects.create(
            service_event=event,
            ministry_team=self.sound,
            status=TeamAssignment.STATUS_SCHEDULED,
            notes="preserve metadata",
            reviewed_worship_context_fingerprint="c" * 64,
        )
        old_member = TeamAssignmentMember.objects.create(
            assignment=assignment, membership=old_membership
        )
        overrides = {4: "Alice"}
        if include_create_event is not None:
            overrides[6] = "Alice"
        review = prepare_sound_assignment_mapping(
            content=build_known_workbook(sound_overrides=overrides),
            filename="annual.xlsx",
            user=self.staff,
        )
        preview = build_sound_assignment_preview(
            mapping_review=review,
            selected_mapping={"Alice": self.membership.pk},
            user=self.staff,
            now=self.now,
        )
        with patch(
            "ministry.services.sound_assignment_xlsx_roster_update.timezone.now",
            return_value=self.now,
        ):
            proposal = build_sound_roster_update_proposal(
                preview=preview, user=self.staff
            )
        payload = decode_signed_sound_roster_update(
            proposal.signed_payload, user=self.staff
        )
        return payload, assignment, old_member

    def confirm_roster(self, payload):
        with patch(
            "ministry.services.sound_assignment_xlsx_roster_update.timezone.now",
            return_value=self.now,
        ):
            return confirm_sound_roster_update(user=self.staff, payload=payload)

    def test_member_only_writer_commits_first_and_roster_proposal_is_stale(self):
        event = self.event(0)
        payload, assignment, old_member = self.roster_payload(event)
        event.refresh_from_db()
        revision_before = event.scheduling_revision
        TeamAssignmentMember.objects.using(self.competing_alias).filter(
            pk=old_member.pk
        ).update(confirmation_note="competing evidence")

        with self.assertRaises(SoundAssignmentConfirmationError):
            self.confirm_roster(payload)

        event.refresh_from_db()
        self.assertEqual(event.scheduling_revision, revision_before)
        self.assertEqual(
            TeamAssignmentMember.objects.get(pk=old_member.pk).confirmation_note,
            "competing evidence",
        )
        self.assertEqual(LogEntry.objects.count(), 0)

    def test_roster_barrier_wins_and_member_writer_cannot_interleave(self):
        event = self.event(0)
        payload, assignment, old_member = self.roster_payload(event)
        from .services import sound_assignment_xlsx_roster_update as service

        original = service._load_current_truth
        competing_busy = []

        def load_after_competing_attempt(*args, **kwargs):
            try:
                TeamAssignmentMember.objects.using(self.competing_alias).filter(
                    pk=old_member.pk
                ).update(confirmation_note="race")
            except OperationalError:
                competing_busy.append(True)
            return original(*args, **kwargs)

        with patch.object(
            service, "_load_current_truth", side_effect=load_after_competing_attempt
        ):
            result = self.confirm_roster(payload)

        self.assertEqual(competing_busy, [True])
        self.assertEqual(result.replaced_assignment_ids, (assignment.pk,))
        self.assertFalse(TeamAssignmentMember.objects.filter(pk=old_member.pk).exists())
        current = TeamAssignmentMember.objects.get(assignment=assignment)
        self.assertEqual(current.membership_id, self.membership.pk)
        self.assertEqual(
            TeamAssignmentMember.objects.using(self.competing_alias)
            .get(pk=current.pk)
            .membership_id,
            self.membership.pk,
        )

    def test_parent_metadata_and_destination_identity_races_fail_closed(self):
        event = self.event(0)
        payload, assignment, old_member = self.roster_payload(event)
        TeamAssignment.objects.using(self.competing_alias).filter(
            pk=assignment.pk
        ).update(notes="competing metadata")
        with self.assertRaises(SoundAssignmentConfirmationError):
            self.confirm_roster(payload)
        self.assertTrue(TeamAssignmentMember.objects.filter(pk=old_member.pk).exists())
        self.assertEqual(LogEntry.objects.count(), 0)

        TeamAssignment.objects.filter(pk=assignment.pk).update(
            notes="preserve metadata"
        )
        TeamAssignment.objects.using(self.competing_alias).filter(
            pk=assignment.pk
        ).update(status=TeamAssignment.STATUS_CONFIRMED)
        with self.assertRaises(SoundAssignmentConfirmationError):
            self.confirm_roster(payload)
        TeamAssignment.objects.filter(pk=assignment.pk).update(
            status=TeamAssignment.STATUS_SCHEDULED
        )
        review = prepare_sound_assignment_mapping(
            content=build_known_workbook(sound_overrides={4: "Alice"}),
            filename="annual.xlsx",
            user=self.staff,
        )
        preview = build_sound_assignment_preview(
            mapping_review=review,
            selected_mapping={"Alice": self.membership.pk},
            user=self.staff,
            now=self.now,
        )
        with patch(
            "ministry.services.sound_assignment_xlsx_roster_update.timezone.now",
            return_value=self.now,
        ):
            proposal = build_sound_roster_update_proposal(
                preview=preview, user=self.staff
            )
        payload = decode_signed_sound_roster_update(
            proposal.signed_payload, user=self.staff
        )
        TeamMembership.objects.using(self.competing_alias).filter(
            pk=self.membership.pk
        ).update(is_active=False)
        with self.assertRaises(SoundAssignmentConfirmationError):
            self.confirm_roster(payload)
        TeamMembership.objects.filter(pk=self.membership.pk).update(is_active=True)

        relinked = User.objects.create_user("file_sound_relinked")
        TeamMembership.objects.using(self.competing_alias).filter(
            pk=self.membership.pk
        ).update(user_id=relinked.pk)
        with self.assertRaises(SoundAssignmentConfirmationError):
            self.confirm_roster(payload)
        TeamMembership.objects.filter(pk=self.membership.pk).update(
            user_id=self.alice.pk
        )

        TeamMembership.objects.using(self.competing_alias).filter(
            pk=self.membership.pk
        ).update(display_name="Alice relinked identity")
        with self.assertRaises(SoundAssignmentConfirmationError):
            self.confirm_roster(payload)
        self.assertTrue(TeamAssignmentMember.objects.filter(pk=old_member.pk).exists())
        self.assertEqual(LogEntry.objects.count(), 0)

    def test_mixed_create_replace_stale_member_rolls_back_revision_and_all_writes(self):
        replace_event = self.event(0)
        create_event = self.event(1)
        payload, assignment, old_member = self.roster_payload(
            replace_event, include_create_event=create_event
        )
        replace_event.refresh_from_db()
        replace_revision = replace_event.scheduling_revision
        TeamAssignmentMember.objects.using(self.competing_alias).filter(
            pk=old_member.pk
        ).update(confirmation_note="race wins")

        with self.assertRaises(SoundAssignmentConfirmationError):
            self.confirm_roster(payload)

        replace_event.refresh_from_db()
        create_event.refresh_from_db()
        self.assertEqual(replace_event.scheduling_revision, replace_revision)
        self.assertEqual(create_event.scheduling_revision, 0)
        self.assertEqual(TeamAssignment.objects.count(), 1)
        self.assertEqual(TeamAssignmentMember.objects.count(), 1)
        self.assertEqual(
            TeamAssignmentMember.objects.get(pk=old_member.pk).confirmation_note,
            "race wins",
        )
        self.assertEqual(LogEntry.objects.count(), 0)


@override_settings(CMS_ENABLED_INTEGRATIONS=[INTEGRATION_KEY])
class SoundAssignmentConfirmationAdditionalTests(SoundAssignmentPreviewTestBase):
    def _reviewed_preview(self, sound_overrides, mapping, *, now=None):
        review = prepare_sound_assignment_mapping(
            content=self.workbook(sound_overrides),
            filename="annual.xlsx",
            user=self.staff,
        )
        return build_sound_assignment_preview(
            mapping_review=review,
            selected_mapping=mapping,
            user=self.staff,
            now=now or self.preview_now(),
        )

    def _proposal(self, preview=None):
        preview = preview or self.preview()
        with patch(
            "ministry.services.sound_assignment_xlsx_confirmation.timezone.now",
            return_value=self.preview_now(),
        ):
            proposal = build_sound_assignment_confirmation_proposal(
                preview=preview,
                user=self.staff,
            )
        payload = decode_signed_sound_assignment_confirmation(
            proposal.signed_payload,
            user=self.staff,
        )
        return proposal, payload

    def _confirm(self, payload):
        with patch(
            "ministry.services.sound_assignment_xlsx_confirmation.timezone.now",
            return_value=self.preview_now(),
        ):
            return confirm_sound_assignments(user=self.staff, payload=payload)

    def test_stale_one_row_in_multirow_batch_rolls_back_all_claims(self):
        first = self.event_for_row(0)
        second = self.event_for_row(1)
        preview = self._reviewed_preview(
            {4: "Alice", 6: "Alice"}, {"Alice": self.alice_membership.pk}
        )
        _proposal, payload = self._proposal(preview)
        ServiceEvent.objects.filter(pk=second.pk).update(scheduling_revision=1)
        with self.assertRaises(SoundAssignmentConfirmationError):
            self._confirm(payload)
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual((first.scheduling_revision, second.scheduling_revision), (0, 1))
        self.assertEqual(TeamAssignment.objects.count(), 0)
        self.assertEqual(TeamAssignmentMember.objects.count(), 0)
        self.assertEqual(LogEntry.objects.count(), 0)

    def test_event_history_profile_and_audience_drift_each_roll_back_claim(self):
        from events.models import ServiceProfile

        def become_completed(event):
            ServiceEvent.objects.filter(pk=event.pk).update(
                status=ServiceEvent.STATUS_COMPLETED
            )

        def change_profile(event):
            other = ServiceProfile.objects.create(
                key="other_0930_cm",
                name="Other",
                event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
            )
            ServiceEvent.objects.filter(pk=event.pk).update(service_profile=other)

        def leave_audience(_event):
            ChurchStructureMembership.objects.filter(user=self.alice).delete()

        for mutate in (become_completed, change_profile, leave_audience):
            with self.subTest(mutate=mutate):
                event = self.event_for_row()
                _proposal, payload = self._proposal()
                mutate(event)
                with self.assertRaises(SoundAssignmentConfirmationError):
                    self._confirm(payload)
                event.refresh_from_db()
                self.assertEqual(event.scheduling_revision, 0)
                self.assertEqual(TeamAssignment.objects.count(), 0)
                ServiceEvent.objects.all().delete()
                ServiceProfile.objects.exclude(pk=self.profile.pk).delete()
                ChurchStructureMembership.objects.get_or_create(
                    user=self.alice,
                    defaults={
                        "unit": self.cm,
                        "status": ChurchStructureMembership.STATUS_ACTIVE,
                        "is_primary": True,
                        "start_date": timezone.datetime(2020, 1, 1).date(),
                    },
                )

    def test_event_becoming_canonically_elapsed_rolls_back_claim(self):
        event = self.event_for_row()
        _proposal, payload = self._proposal()
        after_event = timezone.make_aware(
            datetime(2026, 1, 6, 0, 0), timezone.get_current_timezone()
        )
        with patch(
            "ministry.services.sound_assignment_xlsx_confirmation.timezone.now",
            return_value=after_event,
        ):
            with self.assertRaises(SoundAssignmentConfirmationError):
                confirm_sound_assignments(user=self.staff, payload=payload)
        event.refresh_from_db()
        self.assertEqual(event.scheduling_revision, 0)
        self.assertEqual(TeamAssignment.objects.count(), 0)

    def test_assignment_history_or_duplicate_appearing_rolls_back_claim(self):
        def history(event):
            TeamAssignment(
                service_event=event,
                ministry_team=self.sound,
                status=TeamAssignment.STATUS_COMPLETED,
            ).save(_skip_scheduling_revision=True)

        def duplicate(event):
            for _ in range(2):
                TeamAssignment(
                    service_event=event,
                    ministry_team=self.sound,
                    status=TeamAssignment.STATUS_SCHEDULED,
                ).save(_skip_scheduling_revision=True)

        for mutate in (history, duplicate):
            with self.subTest(mutate=mutate):
                event = self.event_for_row()
                _proposal, payload = self._proposal()
                mutate(event)
                with self.assertRaises(SoundAssignmentConfirmationError):
                    self._confirm(payload)
                event.refresh_from_db()
                self.assertEqual(event.scheduling_revision, 0)
                self.assertEqual(LogEntry.objects.count(), 0)
                TeamAssignment.objects.all().delete()
                ServiceEvent.objects.all().delete()

    def test_member_only_noop_drift_rolls_back_unrelated_create_claim(self):
        create_event = self.event_for_row(0)
        noop_event = self.event_for_row(1)
        noop = TeamAssignment.objects.create(
            service_event=noop_event,
            ministry_team=self.sound,
            status=TeamAssignment.STATUS_SCHEDULED,
        )
        TeamAssignmentMember.objects.create(
            assignment=noop, membership=self.alice_membership
        )
        preview = self._reviewed_preview(
            {4: "Alice", 6: "Alice"}, {"Alice": self.alice_membership.pk}
        )
        _proposal, payload = self._proposal(preview)
        TeamAssignmentMember.objects.create(
            assignment=noop, membership=self.display_only
        )
        create_before = create_event.scheduling_revision
        noop_before = ServiceEvent.objects.get(pk=noop_event.pk).scheduling_revision
        with self.assertRaises(SoundAssignmentConfirmationError):
            self._confirm(payload)
        create_event.refresh_from_db()
        noop_event.refresh_from_db()
        self.assertEqual(create_event.scheduling_revision, create_before)
        self.assertEqual(noop_event.scheduling_revision, noop_before)
        self.assertEqual(TeamAssignment.objects.count(), 1)
        self.assertEqual(LogEntry.objects.count(), 0)

    def test_permission_integration_event_team_and_membership_drift_fail_closed(self):
        mutators = (
            lambda event: User.objects.filter(pk=self.staff.pk).update(is_staff=False),
            lambda event: ServiceEvent.objects.filter(pk=event.pk).update(
                start_datetime=timezone.make_aware(
                    datetime(2026, 1, 4, 10, 0),
                    timezone.get_current_timezone(),
                )
            ),
            lambda event: type(self.sound).objects.filter(pk=self.sound.pk).update(
                is_assignable=False
            ),
            lambda event: TeamMembership.objects.filter(
                pk=self.alice_membership.pk
            ).update(is_active=False),
        )
        for mutator in mutators:
            with self.subTest(mutator=mutator):
                event = self.event_for_row()
                _proposal, payload = self._proposal()
                mutator(event)
                with self.assertRaises(SoundAssignmentConfirmationError):
                    self._confirm(payload)
                event.refresh_from_db()
                self.assertEqual(event.scheduling_revision, 0)
                self.assertEqual(TeamAssignment.objects.count(), 0)
                TeamAssignmentMember.objects.all().delete()
                ServiceEvent.objects.all().delete()
                User.objects.filter(pk=self.staff.pk).update(is_staff=True)
                type(self.sound).objects.filter(pk=self.sound.pk).update(
                    is_assignable=True
                )
                TeamMembership.objects.filter(
                    pk=self.alice_membership.pk
                ).update(is_active=True)

        event = self.event_for_row()
        _proposal, payload = self._proposal()
        with override_settings(CMS_ENABLED_INTEGRATIONS=[]):
            with self.assertRaises(SoundAssignmentConfirmationError):
                self._confirm(payload)
        event.refresh_from_db()
        self.assertEqual(event.scheduling_revision, 0)

    def test_post_claim_actor_reauthorization_precedes_assignment_write(self):
        event = self.event_for_row()
        _proposal, payload = self._proposal()
        from .services import sound_assignment_xlsx_confirmation as service

        original_claim = service.claim_scheduling_revisions
        claimed_revisions = []

        def claim_then_revoke_authority(expected_revisions):
            result = original_claim(expected_revisions)
            claimed_revisions.append(
                ServiceEvent.objects.get(pk=event.pk).scheduling_revision
            )
            User.objects.filter(pk=self.staff.pk).update(is_staff=False)
            return result

        with patch.object(
            service,
            "claim_scheduling_revisions",
            side_effect=claim_then_revoke_authority,
        ), patch.object(
            TeamAssignment,
            "save",
            autospec=True,
            side_effect=AssertionError("assignment.save() must not be reached"),
        ) as assignment_save:
            with self.assertRaisesRegex(
                SoundAssignmentConfirmationError,
                "authority changed after the event revision claim",
            ):
                self._confirm(payload)

        self.assertEqual(claimed_revisions, [1])
        assignment_save.assert_not_called()
        event.refresh_from_db()
        self.staff.refresh_from_db()
        self.assertEqual(event.scheduling_revision, 0)
        self.assertTrue(self.staff.is_staff)
        self.assertEqual(TeamAssignment.objects.count(), 0)
        self.assertEqual(TeamAssignmentMember.objects.count(), 0)
        self.assertEqual(LogEntry.objects.count(), 0)

    def test_post_claim_integration_recheck_precedes_assignment_write(self):
        event = self.event_for_row()
        _proposal, payload = self._proposal()
        from .services import sound_assignment_xlsx_confirmation as service

        original_claim = service.claim_scheduling_revisions
        call_order = []
        integration_checks = 0

        def integration_becomes_unavailable(key):
            nonlocal integration_checks
            integration_checks += 1
            call_order.append("integration")
            if integration_checks == 2:
                raise IntegrationDisabled("disabled after claim")
            return object()

        def claim_and_record(expected_revisions):
            result = original_claim(expected_revisions)
            call_order.append("claim")
            self.assertEqual(
                ServiceEvent.objects.get(pk=event.pk).scheduling_revision,
                1,
            )
            return result

        with patch.object(
            service,
            "require_integration_enabled",
            side_effect=integration_becomes_unavailable,
        ), patch.object(
            service,
            "claim_scheduling_revisions",
            side_effect=claim_and_record,
        ), patch.object(
            TeamAssignment,
            "save",
            autospec=True,
            side_effect=AssertionError("assignment.save() must not be reached"),
        ) as assignment_save:
            with self.assertRaisesRegex(
                SoundAssignmentConfirmationError,
                "integration became unavailable after the event revision claim",
            ):
                self._confirm(payload)

        self.assertEqual(call_order, ["integration", "claim", "integration"])
        assignment_save.assert_not_called()
        event.refresh_from_db()
        self.assertEqual(event.scheduling_revision, 0)
        self.assertEqual(TeamAssignment.objects.count(), 0)
        self.assertEqual(TeamAssignmentMember.objects.count(), 0)
        self.assertEqual(LogEntry.objects.count(), 0)

    def test_member_audit_and_postcondition_failures_roll_back_everything(self):
        failure_points = (
            patch.object(
                TeamAssignmentMember,
                "save",
                side_effect=RuntimeError("member failed"),
            ),
            patch(
                "ministry.services.sound_assignment_xlsx_confirmation.LogEntry.objects.log_action",
                side_effect=RuntimeError("audit failed"),
            ),
            patch(
                "ministry.services.sound_assignment_xlsx_confirmation._assert_postconditions",
                side_effect=SoundAssignmentConfirmationError("postcondition failed"),
            ),
        )
        for failure in failure_points:
            with self.subTest(failure=failure):
                event = self.event_for_row()
                _proposal, payload = self._proposal()
                with failure:
                    with self.assertRaises(Exception):
                        self._confirm(payload)
                event.refresh_from_db()
                self.assertEqual(event.scheduling_revision, 0)
                self.assertEqual(TeamAssignment.objects.count(), 0)
                self.assertEqual(TeamAssignmentMember.objects.count(), 0)
                self.assertEqual(LogEntry.objects.count(), 0)
                ServiceEvent.objects.all().delete()

    def test_audit_failure_uses_bounded_error_and_rolls_back(self):
        event = self.event_for_row()
        _proposal, payload = self._proposal()
        with patch(
            "ministry.services.sound_assignment_xlsx_confirmation.LogEntry.objects.log_action",
            side_effect=RuntimeError("audit failed"),
        ):
            with self.assertRaises(SoundAssignmentConfirmationAuditError):
                self._confirm(payload)
        event.refresh_from_db()
        self.assertEqual(event.scheduling_revision, 0)

    def test_replay_and_fresh_preview_are_safe(self):
        event = self.event_for_row()
        _proposal, payload = self._proposal()
        self._confirm(payload)
        with self.assertRaises(SoundAssignmentConfirmationError):
            self._confirm(payload)
        event.refresh_from_db()
        self.assertEqual(event.scheduling_revision, 1)
        self.assertEqual(TeamAssignment.objects.count(), 1)
        fresh = self.preview()
        self.assertEqual(fresh.rows[0].target_state, SoundTargetState.EXACT_NOOP)
        self.assertFalse(fresh.is_confirmable)

    def test_tamper_expiry_user_mismatch_and_resigned_substitution_rejected(self):
        self.event_for_row()
        proposal, _payload = self._proposal()
        with self.assertRaises(SoundAssignmentConfirmationProposalError):
            decode_signed_sound_assignment_confirmation(
                proposal.signed_payload + "tamper", user=self.staff
            )
        with self.assertRaises(SoundAssignmentConfirmationProposalError):
            decode_signed_sound_assignment_confirmation(
                proposal.signed_payload, user=self.staff, max_age=-1
            )
        with self.assertRaises(SoundAssignmentConfirmationProposalError):
            decode_signed_sound_assignment_confirmation(
                proposal.signed_payload, user=self.superuser
            )
        forged = deepcopy(proposal.normalized_payload)
        forged["rows"][0]["event"]["id"] += 999
        token = signing.dumps(
            forged, compress=True, salt=CONFIRMATION_SIGNING_SALT
        )
        with self.assertRaises(SoundAssignmentConfirmationError):
            payload = decode_signed_sound_assignment_confirmation(
                token, user=self.staff
            )
            self._confirm(payload)

    def test_ui_exposes_post_only_confirmation_and_redirects_after_success(self):
        event = self.event_for_row()
        self.client.force_login(self.staff)
        session = self.client.session
        session["language"] = "en"
        session.save()
        upload = self.client.post(
            reverse("sound_assignment_workbook_preview"),
            {"workbook": self.upload({4: "Alice"})},
        )
        mapping_review = upload.context["mapping_review"]
        with patch(
            "ministry.services.sound_assignment_xlsx_preview.timezone.now",
            return_value=self.preview_now(),
        ), patch(
            "ministry.services.sound_assignment_xlsx_confirmation.timezone.now",
            return_value=self.preview_now(),
        ):
            preview_response = self.client.post(
                reverse("sound_assignment_workbook_preview"),
                {
                    "signed_mapping_state": mapping_review.signed_state,
                    "mapping_0": str(self.alice_membership.pk),
                },
            )
            proposal = preview_response.context["confirmation_proposal"]
            self.assertContains(preview_response, "Create 1 future Sound assignments")
            self.assertContains(preview_response, "Past rows are not backfilled")
            self.assertEqual(
                self.client.get(
                    reverse("confirm_sound_assignment_workbook")
                ).status_code,
                405,
            )
            response = self.client.post(
                reverse("confirm_sound_assignment_workbook"),
                {"signed_confirmation": proposal.signed_payload},
            )
        self.assertRedirects(response, reverse("team_assignment_list"))
        event.refresh_from_db()
        self.assertEqual(event.scheduling_revision, 1)
        self.assertEqual(TeamAssignment.objects.count(), 1)

    def test_confirmation_view_denies_member_and_disabled_integration(self):
        self.event_for_row()
        proposal, _payload = self._proposal()
        self.client.force_login(self.alice)
        denied = self.client.post(
            reverse("confirm_sound_assignment_workbook"),
            {"signed_confirmation": proposal.signed_payload},
        )
        self.assertEqual(denied.status_code, 403)
        self.client.force_login(self.staff)
        with override_settings(CMS_ENABLED_INTEGRATIONS=[]):
            disabled = self.client.post(
                reverse("confirm_sound_assignment_workbook"),
                {"signed_confirmation": proposal.signed_payload},
            )
        self.assertEqual(disabled.status_code, 404)
        self.assertEqual(TeamAssignment.objects.count(), 0)

    def test_active_superuser_can_confirm_and_is_recorded_as_creator(self):
        event = self.event_for_row()
        review = prepare_sound_assignment_mapping(
            content=self.workbook({4: "Alice"}),
            filename="annual.xlsx",
            user=self.superuser,
        )
        preview = build_sound_assignment_preview(
            mapping_review=review,
            selected_mapping={"Alice": self.alice_membership.pk},
            user=self.superuser,
            now=self.preview_now(),
        )
        with patch(
            "ministry.services.sound_assignment_xlsx_confirmation.timezone.now",
            return_value=self.preview_now(),
        ):
            proposal = build_sound_assignment_confirmation_proposal(
                preview=preview, user=self.superuser
            )
            payload = decode_signed_sound_assignment_confirmation(
                proposal.signed_payload, user=self.superuser
            )
            confirm_sound_assignments(user=self.superuser, payload=payload)
        assignment = TeamAssignment.objects.get()
        event.refresh_from_db()
        self.assertEqual(assignment.created_by_id, self.superuser.pk)
        self.assertEqual(event.scheduling_revision, 1)
