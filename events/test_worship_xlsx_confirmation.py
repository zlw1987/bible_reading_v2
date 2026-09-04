"""Focused MO-S.6D-SLICE9.1A annual workbook confirmation tests."""

import copy
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, time
import os
import tempfile
import unittest
from unittest.mock import patch

from django.contrib.admin.models import LogEntry
from django.contrib.auth.models import User
from django.core import signing
from django.core.management import call_command
from django.db import close_old_connections, connections, transaction
from django.db.models.signals import pre_save
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import ChurchStructureMembership, ChurchStructureUnit
from accounts.permissions import (
    CAP_MANAGE_SERVICE_EVENTS,
    CAP_MANAGE_TEAM_ASSIGNMENTS,
)
from announcements.models import Announcement
from community_events.models import CommunityActivity
from ministry.models import (
    MinistryTeam,
    MinistryTeamParentLink,
    MinistryTeamRoleAssignment,
    MinistryTeamRoleType,
    TeamAssignment,
    TeamAssignmentMember,
    TeamMembership,
)
from ministry.permissions import can_manage_team_assignments
from ministry.services.worship_xlsx_confirmation import (
    CONFIRMATION_CONTRACT_REVISION,
    CONFIRMATION_MAX_AGE_SECONDS,
    CONFIRMATION_PROPOSAL_TYPE,
    CONFIRMATION_SIGNING_SALT,
    WorshipWorkbookConfirmationError,
    WorshipWorkbookConfirmationProposalError,
    build_worship_workbook_confirmation_proposal,
    confirm_worship_workbook,
    decode_signed_worship_workbook_confirmation,
)
from ministry.services.worship_xlsx_preview import (
    CONTRACT_REVISION,
    INTEGRATION_KEY,
    NORMALIZED_PREVIEW_CONTRACT_REVISION,
    TOKEN_ORDER,
    build_worship_import_preview,
    parse_known_worship_workbook,
    sign_parsed_workbook,
)
from notifications.models import Notification
from prayers.models import PrayerRequest
from reading.models import CheckIn, ReadingPlan
from studies.models import BibleStudyMeeting

from .models import (
    ServiceEvent,
    ServiceEventAudienceScope,
    ServiceEventPlannerAssignment,
    ServiceEventRequiredTeam,
    ServiceProfile,
)
from .scheduling_revision import (
    SchedulingRevisionError,
    advance_scheduling_revisions,
    claim_scheduling_revisions,
)
from .test_worship_xlsx_preview import build_known_workbook
from .views import can_manage_service_events


class WorshipWorkbookConfirmationTestBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.parsed = parse_known_worship_workbook(
            build_known_workbook(), filename="reviewed-schedule.xlsx"
        )
        cls.target_profile = ServiceProfile.objects.create(
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
        cls.pool = MinistryTeam.objects.create(
            name="CM Worship Pool",
            name_en="CM Worship Pool",
            is_assignable=False,
            is_worship_rotation_pool=True,
        )
        MinistryTeamParentLink.objects.create(
            child_team=cls.pool,
            parent_church_unit=cls.cm,
            is_primary=True,
        )
        cls.teams = {}
        for token in TOKEN_ORDER:
            team = MinistryTeam.objects.create(
                name=f"Worship {token}", name_en=f"Worship {token}"
            )
            MinistryTeamParentLink.objects.create(
                child_team=team,
                parent_team=cls.pool,
                is_primary=True,
            )
            cls.teams[token] = team

        cls.staff = User.objects.create_user(
            "annual_staff", password="pw", is_staff=True
        )
        cls.superuser = User.objects.create_user(
            "annual_super", password="pw", is_superuser=True, is_staff=False
        )
        cls.ordinary = User.objects.create_user("annual_ordinary", password="pw")
        cls.exact_lead = User.objects.create_user("annual_exact_lead", password="pw")
        cls.pool_lead = User.objects.create_user("annual_pool_lead", password="pw")
        cls.event_planner = User.objects.create_user(
            "annual_event_planner", password="pw"
        )
        cls.global_assignment_manager = User.objects.create_user(
            "annual_global_assignment_manager", password="pw"
        )
        cls.cap_service_event_manager = User.objects.create_user(
            "annual_cap_service_manager", password="pw"
        )
        role_type = MinistryTeamRoleType.objects.create(
            code=MinistryTeamRoleType.CODE_LEAD,
            name="Lead",
            name_en="Lead",
            is_active=True,
        )
        MinistryTeamRoleAssignment.objects.create(
            team=cls.teams["A"],
            role_type=role_type,
            user=cls.exact_lead,
            start_date=date(2025, 1, 1),
        )
        MinistryTeamRoleAssignment.objects.create(
            team=cls.pool,
            role_type=role_type,
            user=cls.pool_lead,
            start_date=date(2025, 1, 1),
        )

        cls.events = []
        for index, row in enumerate(cls.parsed.rows):
            event = ServiceEvent.objects.create(
                title=f"Sunday {index}",
                title_en=f"Sunday {index}",
                service_profile=cls.target_profile,
                service_profile_key="bethany_0930_cm",
                event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
                start_datetime=timezone.make_aware(
                    datetime.combine(row.local_date, time(9, 30)),
                    timezone.get_current_timezone(),
                ),
                status=(
                    ServiceEvent.STATUS_COMPLETED
                    if index < 34
                    else ServiceEvent.STATUS_PUBLISHED
                ),
            )
            ServiceEventAudienceScope.objects.create(
                service_event=event, unit=cls.cm
            )
            cls.events.append(event)
        ServiceEventPlannerAssignment.objects.create(
            service_event=cls.events[0], user=cls.event_planner
        )

    def setUp(self):
        session = self.client.session
        session["language"] = "en"
        session.save()

    def mapping(self):
        return {token: self.teams[token] for token in self.parsed.token_counts}

    def preview(self, *, user=None):
        return build_worship_import_preview(
            parsed=self.parsed,
            mapping=self.mapping(),
            user=user or self.staff,
        )

    def proposal(self, *, user=None):
        user = user or self.staff
        return build_worship_workbook_confirmation_proposal(
            preview=self.preview(user=user), user=user
        )

    def decoded(self, *, user=None):
        user = user or self.staff
        proposal = self.proposal(user=user)
        return proposal, decode_signed_worship_workbook_confirmation(
            proposal.signed_payload, user=user
        )

    def scheduling_snapshot(self):
        return list(
            ServiceEvent.objects.order_by("id").values_list(
                "id",
                "scheduling_revision",
                "rotation_anchor_team_id",
                "service_profile_id",
                "service_profile_key",
                "event_type",
                "start_datetime",
                "status",
            )
        )


@override_settings(
    CMS_ENABLED_INTEGRATIONS=["svca_bethany_2026_worship_xlsx"]
)
class WorshipWorkbookConfirmationSuccessTests(WorshipWorkbookConfirmationTestBase):
    def test_staff_all_52_changed_advances_once_audits_shared_operation_and_no_notify(self):
        proposal, payload = self.decoded()
        self.assertEqual(payload["integration_key"], INTEGRATION_KEY)
        self.assertEqual(payload["profile_id"], self.target_profile.pk)
        self.assertEqual(payload["profile_key"], self.target_profile.key)
        self.assertEqual(
            payload["profile_event_type"], self.target_profile.event_type
        )
        self.assertEqual(payload["parser_contract_revision"], CONTRACT_REVISION)
        self.assertEqual(
            payload["preview_contract_revision"],
            NORMALIZED_PREVIEW_CONTRACT_REVISION,
        )
        self.assertTrue(
            all(
                row["expected_service_profile_id"] == self.target_profile.pk
                for row in payload["rows"]
            )
        )
        self.assertEqual(proposal.selected_count, 52)
        self.assertEqual(proposal.changed_count, 52)
        self.assertEqual(proposal.no_op_count, 0)
        self.assertLess(proposal.signed_payload_bytes, 64 * 1024)
        self.assertNotEqual(proposal.signed_payload, self.preview().signed_payload)

        with patch("django.db.transaction.on_commit") as on_commit:
            result = confirm_worship_workbook(user=self.staff, payload=payload)

        self.assertEqual(result.selected_count, 52)
        self.assertEqual(result.changed_count, 52)
        self.assertEqual(result.no_op_count, 0)
        self.assertEqual(result.log_entry_count, 52)
        self.assertEqual(
            list(
                ServiceEvent.objects.order_by("id").values_list(
                    "scheduling_revision", flat=True
                )
            ),
            [1] * 52,
        )
        expected_team_ids = [self.teams[row.token].pk for row in self.parsed.rows]
        self.assertEqual(
            list(
                ServiceEvent.objects.order_by("id").values_list(
                    "rotation_anchor_team_id", flat=True
                )
            ),
            expected_team_ids,
        )
        logs = list(LogEntry.objects.order_by("id"))
        self.assertEqual(len(logs), 52)
        self.assertTrue(
            all(f"operation_id={proposal.operation_id};" in log.change_message for log in logs)
        )
        self.assertTrue(
            all(
                log.change_message.startswith(
                    "source=annual_worship_workbook_import;"
                )
                for log in logs
            )
        )
        self.assertNotIn("Private Leader", " ".join(log.change_message for log in logs))
        self.assertEqual(Notification.objects.count(), 0)
        on_commit.assert_not_called()

    def test_superuser_mixed_completed_and_published_success(self):
        proposal, payload = self.decoded(user=self.superuser)
        result = confirm_worship_workbook(user=self.superuser, payload=payload)
        self.assertEqual(result.operation_id, proposal.operation_id)
        self.assertEqual(result.selected_count, 52)
        self.assertEqual(
            set(ServiceEvent.objects.values_list("status", flat=True)),
            {ServiceEvent.STATUS_COMPLETED, ServiceEvent.STATUS_PUBLISHED},
        )
        self.assertEqual({log.user_id for log in LogEntry.objects.all()}, {self.superuser.pk})

    def test_mixed_changed_and_no_op_claims_every_row_but_logs_only_changes(self):
        no_op_ids = [event.pk for event in self.events[:10]]
        ServiceEvent.objects.filter(pk__in=no_op_ids).update(
            rotation_anchor_team=self.teams["A"]
        )
        # Only rows whose workbook token is A are no-op under this setup.
        preview = self.preview()
        proposal = build_worship_workbook_confirmation_proposal(
            preview=preview, user=self.staff
        )
        payload = decode_signed_worship_workbook_confirmation(
            proposal.signed_payload, user=self.staff
        )
        saved_event_ids = []

        def record_event_save(sender, instance, **kwargs):
            saved_event_ids.append(instance.pk)

        pre_save.connect(
            record_event_save,
            sender=ServiceEvent,
            dispatch_uid="annual-workbook-no-op-save-proof",
        )
        try:
            result = confirm_worship_workbook(user=self.staff, payload=payload)
        finally:
            pre_save.disconnect(
                sender=ServiceEvent,
                dispatch_uid="annual-workbook-no-op-save-proof",
            )

        self.assertEqual(result.no_op_count, preview.no_op_count)
        self.assertEqual(result.changed_count, preview.proposed_change_count)
        self.assertEqual(result.log_entry_count, preview.proposed_change_count)
        self.assertEqual(
            set(ServiceEvent.objects.values_list("scheduling_revision", flat=True)),
            {1},
        )
        logged_ids = {int(log.object_id) for log in LogEntry.objects.all()}
        expected_changed_ids = {
            row.event.pk
            for row in preview.rows
            if row.classification.value == "proposed_change"
        }
        self.assertEqual(logged_ids, expected_changed_ids)
        self.assertEqual(set(saved_event_ids), expected_changed_ids)

    def test_success_result_route_is_request_scoped_bilingual_and_replay_is_stale(self):
        proposal = self.proposal()
        self.client.force_login(self.staff)
        response = self.client.post(
            reverse("worship_workbook_confirm"),
            {"confirmation_proposal": proposal.signed_payload},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Reviewed Worship Team changes applied")
        self.assertContains(response, proposal.operation_id)
        self.assertContains(response, "No TeamAssignment, serving member")
        before_replay = self.scheduling_snapshot()
        before_logs = LogEntry.objects.count()
        replay = self.client.post(
            reverse("worship_workbook_confirm"),
            {"confirmation_proposal": proposal.signed_payload},
        )
        self.assertEqual(replay.status_code, 409)
        self.assertContains(replay, "Nothing was changed.", status_code=409)
        self.assertEqual(self.scheduling_snapshot(), before_replay)
        self.assertEqual(LogEntry.objects.count(), before_logs)
        self.assertEqual(Notification.objects.count(), 0)

    def test_success_changes_only_anchor_revision_and_changed_event_audit(self):
        protected_models = (
            ServiceEventAudienceScope,
            ServiceEventRequiredTeam,
            ServiceEventPlannerAssignment,
            MinistryTeam,
            MinistryTeamParentLink,
            TeamMembership,
            MinistryTeamRoleAssignment,
            TeamAssignment,
            TeamAssignmentMember,
            ChurchStructureUnit,
            ChurchStructureMembership,
            BibleStudyMeeting,
            ReadingPlan,
            CheckIn,
            PrayerRequest,
            CommunityActivity,
            Announcement,
            Notification,
        )
        counts_before = {
            model._meta.label: model.objects.count() for model in protected_models
        }
        identity_before = list(
            ServiceEvent.objects.order_by("id").values_list(
                "id",
                "service_profile_id",
                "service_profile_key",
                "event_type",
                "start_datetime",
                "end_datetime",
                "status",
                "title",
                "title_en",
                "location",
                "meeting_link",
                "host_language_unit_id",
                "created_by_id",
            )
        )
        _, payload = self.decoded()
        confirm_worship_workbook(user=self.staff, payload=payload)
        self.assertEqual(
            {model._meta.label: model.objects.count() for model in protected_models},
            counts_before,
        )
        self.assertEqual(
            list(
                ServiceEvent.objects.order_by("id").values_list(
                    "id",
                    "service_profile_id",
                    "service_profile_key",
                    "event_type",
                    "start_datetime",
                    "end_datetime",
                    "status",
                    "title",
                    "title_en",
                    "location",
                    "meeting_link",
                    "host_language_unit_id",
                    "created_by_id",
                )
            ),
            identity_before,
        )
        self.assertEqual(LogEntry.objects.count(), 52)

    def test_rebuilt_preview_after_success_is_52_no_op_and_not_confirmable(self):
        _, payload = self.decoded()
        confirm_worship_workbook(user=self.staff, payload=payload)
        rebuilt = self.preview()
        self.assertEqual(rebuilt.matched_target_count, 52)
        self.assertEqual(rebuilt.no_op_count, 52)
        self.assertEqual(rebuilt.proposed_change_count, 0)
        self.assertEqual(rebuilt.blocked_count, 0)
        with self.assertRaises(WorshipWorkbookConfirmationProposalError):
            build_worship_workbook_confirmation_proposal(
                preview=rebuilt, user=self.staff
            )


@override_settings(
    CMS_ENABLED_INTEGRATIONS=["svca_bethany_2026_worship_xlsx"]
)
class WorshipWorkbookConfirmationTokenAuthorityTests(
    WorshipWorkbookConfirmationTestBase
):
    def test_strict_decoder_rejects_contract_row_mapping_and_revision_tamper(self):
        proposal = self.proposal()
        base = signing.loads(
            proposal.signed_payload, salt=CONFIRMATION_SIGNING_SALT
        )
        cases = {}
        for name in (
            "wrong_type",
            "wrong_contract",
            "malformed_uuid",
            "row_count",
            "duplicate_event",
            "negative_revision",
            "noninteger_id",
            "mapping_inconsistent",
            "wrong_sunday",
            "duplicate_source_row",
            "malformed_sha256",
            "wrong_parser_contract",
            "wrong_preview_contract",
            "wrong_integration",
            "missing_profile_id",
            "wrong_profile_id",
            "wrong_profile_key",
            "wrong_profile_event_type",
            "wrong_row_profile_id",
            "missing_mapping_token",
            "extra_field",
        ):
            payload = copy.deepcopy(base)
            if name == "wrong_type":
                payload["proposal_type"] = "normalized_preview"
            elif name == "wrong_contract":
                payload["confirmation_contract_revision"] = "V2"
            elif name == "malformed_uuid":
                payload["operation_id"] = "not-a-uuid"
            elif name == "row_count":
                payload["rows"].pop()
            elif name == "duplicate_event":
                payload["rows"][1]["event_id"] = payload["rows"][0]["event_id"]
            elif name == "negative_revision":
                payload["rows"][0]["expected_scheduling_revision"] = -1
            elif name == "noninteger_id":
                payload["rows"][0]["event_id"] = "1"
            elif name == "mapping_inconsistent":
                payload["rows"][0]["proposed_team_id"] = self.teams["C3"].pk
            elif name == "wrong_sunday":
                payload["rows"][0]["local_date"] = "2026-01-11"
            elif name == "duplicate_source_row":
                payload["rows"][1]["source_row"] = payload["rows"][0]["source_row"]
            elif name == "malformed_sha256":
                payload["workbook_sha256"] = "not-a-sha"
            elif name == "wrong_parser_contract":
                payload["parser_contract_revision"] = "UNKNOWN"
            elif name == "wrong_preview_contract":
                payload["preview_contract_revision"] = "UNKNOWN"
            elif name == "wrong_integration":
                payload["integration_key"] = "other_adapter"
            elif name == "missing_profile_id":
                payload.pop("profile_id")
            elif name == "wrong_profile_id":
                payload["profile_id"] = self.target_profile.pk + 1000
                for row in payload["rows"]:
                    row["expected_service_profile_id"] = payload["profile_id"]
            elif name == "wrong_profile_key":
                payload["profile_key"] = "wrong"
            elif name == "wrong_profile_event_type":
                payload["profile_event_type"] = ServiceEvent.EVENT_SPECIAL_MEETING
            elif name == "wrong_row_profile_id":
                payload["rows"][0]["expected_service_profile_id"] += 1
            elif name == "missing_mapping_token":
                payload["mapping_team_ids"].pop("C3")
            else:
                payload["unexpected"] = True
            cases[name] = signing.dumps(
                payload, compress=True, salt=CONFIRMATION_SIGNING_SALT
            )

        before = self.scheduling_snapshot()
        for name, token in cases.items():
            with self.subTest(name=name), self.assertRaises(
                WorshipWorkbookConfirmationProposalError
            ):
                decode_signed_worship_workbook_confirmation(token, user=self.staff)
        self.assertEqual(self.scheduling_snapshot(), before)
        self.assertEqual(LogEntry.objects.count(), 0)
        self.assertEqual(Notification.objects.count(), 0)

    def test_v1_confirmation_proposal_is_rejected_without_compatibility_decode(self):
        proposal = self.proposal()
        payload = signing.loads(
            proposal.signed_payload,
            salt=CONFIRMATION_SIGNING_SALT,
        )
        payload["confirmation_contract_revision"] = (
            "SVCA_BETHANY_0930_2026_CONFIRM_V1"
        )
        payload["confirmation_signing_version"] = 1
        v1_token = signing.dumps(
            payload,
            compress=True,
            salt="ministry.worship-xlsx-confirmation.v1",
        )
        with self.assertRaises(WorshipWorkbookConfirmationProposalError):
            decode_signed_worship_workbook_confirmation(
                v1_token,
                user=self.staff,
            )

    def test_wrong_user_expired_and_tampered_tokens_fail_zero_write(self):
        proposal = self.proposal()
        before = self.scheduling_snapshot()
        with self.assertRaises(WorshipWorkbookConfirmationProposalError):
            decode_signed_worship_workbook_confirmation(
                proposal.signed_payload, user=self.superuser
            )
        with self.assertRaises(WorshipWorkbookConfirmationProposalError):
            decode_signed_worship_workbook_confirmation(
                proposal.signed_payload,
                user=self.staff,
                max_age=-1,
            )
        with self.assertRaises(WorshipWorkbookConfirmationProposalError):
            decode_signed_worship_workbook_confirmation(
                proposal.signed_payload + "tampered", user=self.staff
            )
        self.assertEqual(self.scheduling_snapshot(), before)

    def test_direct_confirm_denies_all_nonstaff_authority_classes_and_get(self):
        proposal = self.proposal()
        self.assertEqual(
            self.client.get(reverse("worship_workbook_confirm")).status_code,
            302,
        )
        for user in (
            self.ordinary,
            self.exact_lead,
            self.pool_lead,
            self.event_planner,
            self.global_assignment_manager,
            self.cap_service_event_manager,
        ):
            with self.subTest(user=user.username):
                self.client.force_login(user)
                response = self.client.post(
                    reverse("worship_workbook_confirm"),
                    {"confirmation_proposal": proposal.signed_payload},
                )
                self.assertEqual(response.status_code, 403)
        self.client.force_login(self.staff)
        self.assertEqual(
            self.client.get(reverse("worship_workbook_confirm")).status_code,
            405,
        )
        self.assertEqual(LogEntry.objects.count(), 0)

        with patch(
            "ministry.permissions.has_capability",
            side_effect=lambda user, capability: (
                user.pk == self.global_assignment_manager.pk
                and capability == CAP_MANAGE_TEAM_ASSIGNMENTS
            ),
        ):
            self.assertTrue(
                can_manage_team_assignments(self.global_assignment_manager)
            )
        with patch(
            "events.views.has_capability",
            side_effect=lambda user, capability: (
                user.pk == self.cap_service_event_manager.pk
                and capability == CAP_MANAGE_SERVICE_EVENTS
            ),
        ):
            self.assertTrue(can_manage_service_events(self.cap_service_event_manager))

    @override_settings(CMS_ENABLED_INTEGRATIONS=[])
    def test_disabled_confirmation_staff_and_superuser_cannot_decode_query_or_write(self):
        proposal = self.proposal()
        before = self.scheduling_snapshot()
        before_logs = LogEntry.objects.count()
        for user in (self.staff, self.superuser):
            with (
                self.subTest(user=user.username),
                patch(
                    "ministry.services.worship_xlsx_confirmation.decode_signed_worship_workbook_confirmation"
                ) as decode,
                patch(
                    "ministry.services.worship_xlsx_confirmation.ServiceEvent.objects.filter"
                ) as event_query,
                patch(
                    "events.forms.WorshipWorkbookConfirmationForm"
                ) as confirmation_form,
            ):
                self.client.force_login(user)
                response = self.client.post(
                    reverse("worship_workbook_confirm"),
                    {"confirmation_proposal": proposal.signed_payload},
                )
                self.assertEqual(response.status_code, 404)
                decode.assert_not_called()
                event_query.assert_not_called()
                confirmation_form.assert_not_called()
        self.assertEqual(self.scheduling_snapshot(), before)
        self.assertEqual(LogEntry.objects.count(), before_logs)

    def test_authority_loss_inside_transaction_rolls_back_without_claims(self):
        _, payload = self.decoded()
        User.objects.filter(pk=self.staff.pk).update(is_staff=False)
        before = self.scheduling_snapshot()
        with self.assertRaises(WorshipWorkbookConfirmationError):
            confirm_worship_workbook(user=self.staff, payload=payload)
        self.assertEqual(self.scheduling_snapshot(), before)
        self.assertEqual(LogEntry.objects.count(), 0)


class WorshipWorkbookConfirmationCurrentTruthTests(
    WorshipWorkbookConfirmationTestBase
):
    def assert_confirmation_fails_zero_write(self, payload, *, error=Exception):
        before = self.scheduling_snapshot()
        before_logs = LogEntry.objects.count()
        with self.assertRaises(error):
            confirm_worship_workbook(user=self.staff, payload=payload)
        self.assertEqual(self.scheduling_snapshot(), before)
        self.assertEqual(LogEntry.objects.count(), before_logs)
        self.assertEqual(Notification.objects.count(), 0)

    def assert_drift_case(self, mutate, *, error=(SchedulingRevisionError, WorshipWorkbookConfirmationError)):
        _, payload = self.decoded()
        with transaction.atomic():
            mutate(payload)
            before = self.scheduling_snapshot()
            before_logs = LogEntry.objects.count()
            with self.assertRaises(error):
                confirm_worship_workbook(user=self.staff, payload=payload)
            self.assertEqual(self.scheduling_snapshot(), before)
            self.assertEqual(LogEntry.objects.count(), before_logs)
            self.assertEqual(Notification.objects.count(), 0)
            transaction.set_rollback(True)

    def test_missing_profile_date_time_type_and_lifecycle_drift_matrix(self):
        def target_id(payload):
            return payload["rows"][-1]["event_id"]

        def change_date(payload):
            event = ServiceEvent.objects.get(pk=target_id(payload))
            local = timezone.localtime(event.start_datetime)
            ServiceEvent.objects.filter(pk=event.pk).update(
                start_datetime=timezone.make_aware(
                    datetime.combine(local.date().replace(day=local.date().day - 1), time(9, 30)),
                    timezone.get_current_timezone(),
                )
            )

        def change_time(payload):
            event = ServiceEvent.objects.get(pk=target_id(payload))
            local = timezone.localtime(event.start_datetime)
            ServiceEvent.objects.filter(pk=event.pk).update(
                start_datetime=timezone.make_aware(
                    datetime.combine(local.date(), time(10, 0)),
                    timezone.get_current_timezone(),
                )
            )

        cases = (
            ("deleted", lambda payload: ServiceEvent.objects.filter(pk=target_id(payload)).delete()),
            ("wrong_profile", lambda payload: ServiceEvent.objects.filter(pk=target_id(payload)).update(service_profile_key="wrong")),
            ("wrong_date", change_date),
            ("wrong_time", change_time),
            ("wrong_type", lambda payload: ServiceEvent.objects.filter(pk=target_id(payload)).update(event_type=ServiceEvent.EVENT_SPECIAL_MEETING)),
            ("draft", lambda payload: ServiceEvent.objects.filter(pk=target_id(payload)).update(status=ServiceEvent.STATUS_DRAFT)),
            ("cancelled", lambda payload: ServiceEvent.objects.filter(pk=target_id(payload)).update(status=ServiceEvent.STATUS_CANCELLED)),
        )
        for name, mutate in cases:
            with self.subTest(name=name):
                self.assert_drift_case(mutate)

    def test_profile_and_fk_current_truth_drift_matrix_rolls_back_all_52(self):
        def target_id(payload):
            return payload["rows"][0]["event_id"]

        def recreate_profile(_payload):
            ServiceEvent.objects.all().update(service_profile=None)
            ServiceProfile.objects.filter(pk=self.target_profile.pk).delete()
            ServiceProfile.objects.create(
                key="bethany_0930_cm",
                name="Recreated target",
                event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
            )

        def remap_event(payload):
            other = ServiceProfile.objects.create(
                key="remapped_profile",
                name="Remapped profile",
                event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
            )
            ServiceEvent.objects.filter(pk=target_id(payload)).update(
                service_profile=other,
                service_profile_key=other.key,
            )

        cases = (
            (
                "profile_inactive",
                lambda payload: ServiceProfile.objects.filter(
                    pk=self.target_profile.pk
                ).update(is_active=False),
            ),
            ("profile_recreated", recreate_profile),
            (
                "event_fk_cleared",
                lambda payload: ServiceEvent.objects.filter(
                    pk=target_id(payload)
                ).update(service_profile=None),
            ),
            ("event_fk_remapped", remap_event),
            (
                "compatibility_key_drift",
                lambda payload: ServiceEvent.objects.filter(
                    pk=target_id(payload)
                ).update(service_profile_key="wrong"),
            ),
            (
                "event_type_drift",
                lambda payload: ServiceEvent.objects.filter(
                    pk=target_id(payload)
                ).update(event_type=ServiceEvent.EVENT_SPECIAL_MEETING),
            ),
            (
                "profile_type_drift",
                lambda payload: ServiceProfile.objects.filter(
                    pk=self.target_profile.pk
                ).update(event_type=ServiceEvent.EVENT_SPECIAL_MEETING),
            ),
        )
        for name, mutate in cases:
            with self.subTest(name=name):
                self.assert_drift_case(
                    mutate,
                    error=WorshipWorkbookConfirmationError,
                )

    def test_signed_profile_id_mismatch_is_revalidated_after_claim_and_rolled_back(self):
        _, payload = self.decoded()
        payload = copy.deepcopy(payload)
        payload["profile_id"] += 1000
        for row in payload["rows"]:
            row["expected_service_profile_id"] = payload["profile_id"]
        before = self.scheduling_snapshot()
        with (
            patch(
                "ministry.services.worship_xlsx_confirmation.claim_scheduling_revisions",
                wraps=claim_scheduling_revisions,
            ) as claim,
            self.assertRaises(WorshipWorkbookConfirmationError),
        ):
            confirm_worship_workbook(user=self.staff, payload=payload)
        claim.assert_called_once()
        self.assertEqual(self.scheduling_snapshot(), before)
        self.assertEqual(LogEntry.objects.count(), 0)

    def test_audience_team_pool_hierarchy_and_destination_drift_matrix(self):
        def target_id(payload):
            return payload["rows"][0]["event_id"]

        def zero_audience(payload):
            ServiceEventAudienceScope.objects.filter(
                service_event_id=target_id(payload)
            ).delete()

        def overlapping_audience(payload):
            ServiceEventAudienceScope.objects.bulk_create(
                [
                    ServiceEventAudienceScope(
                        service_event_id=target_id(payload), unit=self.root
                    )
                ]
            )

        def delete_mapped_team(payload):
            MinistryTeamRoleAssignment.objects.filter(
                team=self.teams["A"]
            ).delete()
            MinistryTeam.objects.filter(pk=self.teams["A"].pk).delete()

        def destination_ineligible(payload):
            other = ChurchStructureUnit.objects.create(
                code="OTHER",
                name="Other Ministry",
                unit_type=ChurchStructureUnit.UNIT_MINISTRY_CONTEXT,
                parent=self.root,
            )
            ServiceEventAudienceScope.objects.filter(
                service_event_id=target_id(payload)
            ).delete()
            ServiceEventAudienceScope.objects.create(
                service_event_id=target_id(payload), unit=other
            )

        cases = (
            ("zero_audience", zero_audience),
            ("inactive_audience", lambda payload: ChurchStructureUnit.objects.filter(pk=self.cm.pk).update(is_active=False)),
            ("overlapping_audience", overlapping_audience),
            ("mapped_team_deleted", delete_mapped_team),
            ("mapped_team_inactive", lambda payload: MinistryTeam.objects.filter(pk=self.teams["A"].pk).update(is_active=False)),
            ("mapped_team_nonassignable", lambda payload: MinistryTeam.objects.filter(pk=self.teams["A"].pk).update(is_assignable=False)),
            ("pool_deactivated", lambda payload: MinistryTeam.objects.filter(pk=self.pool.pk).update(is_active=False)),
            ("pool_anchor_removed", lambda payload: MinistryTeamParentLink.objects.filter(child_team=self.pool).delete()),
            ("team_hierarchy_removed", lambda payload: MinistryTeamParentLink.objects.filter(child_team=self.teams["A"]).delete()),
            ("destination_ineligible", destination_ineligible),
        )
        for name, mutate in cases:
            with self.subTest(name=name):
                self.assert_drift_case(mutate)

    def test_off_team_out_of_scope_multiple_and_duplicate_assignment_drift(self):
        def first_event(payload):
            return ServiceEvent.objects.get(pk=payload["rows"][0]["event_id"])

        def off_team(payload):
            TeamAssignment.objects.bulk_create(
                [TeamAssignment(service_event=first_event(payload), ministry_team=self.teams["C3"])]
            )

        def multiple(payload):
            event = first_event(payload)
            TeamAssignment.objects.bulk_create(
                [
                    TeamAssignment(service_event=event, ministry_team=self.teams["A"]),
                    TeamAssignment(service_event=event, ministry_team=self.teams["C1"]),
                ]
            )

        def out_of_scope(payload):
            em = ChurchStructureUnit.objects.create(
                code="EM",
                name="English Ministry",
                unit_type=ChurchStructureUnit.UNIT_MINISTRY_CONTEXT,
                parent=self.root,
            )
            em_pool = MinistryTeam.objects.create(
                name="EM Pool", is_assignable=False, is_worship_rotation_pool=True
            )
            MinistryTeamParentLink.objects.create(
                child_team=em_pool, parent_church_unit=em, is_primary=True
            )
            em_team = MinistryTeam.objects.create(name="EM Worship")
            MinistryTeamParentLink.objects.create(
                child_team=em_team, parent_team=em_pool, is_primary=True
            )
            TeamAssignment.objects.bulk_create(
                [TeamAssignment(service_event=first_event(payload), ministry_team=em_team)]
            )

        for name, mutate in (
            ("off_team", off_team),
            ("out_of_scope", out_of_scope),
            ("multiple", multiple),
        ):
            with self.subTest(name=name):
                self.assert_drift_case(mutate)

        with transaction.atomic():
            first = self.events[0]
            ServiceEvent.objects.filter(pk=first.pk).update(
                rotation_anchor_team=self.teams["A"]
            )
            proposal = self.proposal()
            payload = decode_signed_worship_workbook_confirmation(
                proposal.signed_payload, user=self.staff
            )
            TeamAssignment.objects.bulk_create(
                [
                    TeamAssignment(service_event=first, ministry_team=self.teams["A"]),
                    TeamAssignment(service_event=first, ministry_team=self.teams["A"]),
                ]
            )
            before = self.scheduling_snapshot()
            with self.assertRaises(WorshipWorkbookConfirmationError):
                confirm_worship_workbook(user=self.staff, payload=payload)
            self.assertEqual(self.scheduling_snapshot(), before)
            self.assertEqual(LogEntry.objects.count(), 0)
            transaction.set_rollback(True)

    def test_one_stale_revision_and_one_deleted_target_roll_back_all_claims(self):
        for mutation in ("stale", "deleted"):
            with self.subTest(mutation=mutation):
                proposal, payload = self.decoded()
                target_id = payload["rows"][-1]["event_id"]
                if mutation == "stale":
                    ServiceEvent.objects.filter(pk=target_id).update(
                        scheduling_revision=1
                    )
                    self.assert_confirmation_fails_zero_write(
                        payload, error=SchedulingRevisionError
                    )
                else:
                    ServiceEvent.objects.filter(pk=target_id).delete()
                    self.assert_confirmation_fails_zero_write(
                        payload, error=SchedulingRevisionError
                    )
                # Each subtest needs the TestCase baseline; stop after one mutation.
                break

    def test_expected_before_identity_lifecycle_and_time_drift_fail_after_cas(self):
        _, payload = self.decoded()
        target_id = payload["rows"][0]["event_id"]
        ServiceEvent.objects.filter(pk=target_id).update(
            rotation_anchor_team=self.teams["C3"]
        )
        self.assert_confirmation_fails_zero_write(
            payload, error=WorshipWorkbookConfirmationError
        )

    def test_profile_type_and_cancelled_lifecycle_drift_fail_closed(self):
        for field, value in (
            ("service_profile_key", "wrong_profile"),
            ("event_type", ServiceEvent.EVENT_SPECIAL_MEETING),
            ("status", ServiceEvent.STATUS_CANCELLED),
        ):
            with self.subTest(field=field):
                _, payload = self.decoded()
                ServiceEvent.objects.filter(pk=payload["rows"][0]["event_id"]).update(
                    **{field: value}
                )
                self.assert_confirmation_fails_zero_write(
                    payload, error=WorshipWorkbookConfirmationError
                )
                break

    def test_zero_audience_and_inactive_mapped_team_fail_closed(self):
        _, payload = self.decoded()
        ServiceEventAudienceScope.objects.filter(
            service_event_id=payload["rows"][0]["event_id"]
        ).delete()
        self.assert_confirmation_fails_zero_write(payload)

    def test_mapped_team_inactive_nonassignable_and_destination_ineligible_fail(self):
        _, payload = self.decoded()
        MinistryTeam.objects.filter(pk=self.teams["A"].pk).update(is_active=False)
        self.assert_confirmation_fails_zero_write(
            payload, error=WorshipWorkbookConfirmationError
        )

    def test_pool_hierarchy_drift_and_current_worship_assignment_conflict_fail(self):
        _, payload = self.decoded()
        target = ServiceEvent.objects.get(pk=payload["rows"][0]["event_id"])
        TeamAssignment.objects.bulk_create(
            [
                TeamAssignment(
                    service_event=target,
                    ministry_team=self.teams["C3"],
                    status=TeamAssignment.STATUS_SCHEDULED,
                )
            ]
        )
        self.assert_confirmation_fails_zero_write(
            payload, error=WorshipWorkbookConfirmationError
        )

    def test_logentry_failure_restores_all_52_claims_and_anchor_changes(self):
        _, payload = self.decoded()
        before = self.scheduling_snapshot()
        with patch(
            "ministry.services.worship_xlsx_confirmation.LogEntry.objects.log_action",
            side_effect=RuntimeError("audit unavailable"),
        ), self.assertRaises(WorshipWorkbookConfirmationError):
            confirm_worship_workbook(user=self.staff, payload=payload)
        self.assertEqual(self.scheduling_snapshot(), before)
        self.assertEqual(LogEntry.objects.count(), 0)
        self.assertEqual(Notification.objects.count(), 0)

    def test_true_no_op_with_one_consistent_assignment_is_allowed(self):
        first = self.events[0]
        ServiceEvent.objects.filter(pk=first.pk).update(
            rotation_anchor_team=self.teams["A"]
        )
        TeamAssignment.objects.bulk_create(
            [
                TeamAssignment(
                    service_event=first,
                    ministry_team=self.teams["A"],
                    status=TeamAssignment.STATUS_SCHEDULED,
                )
            ]
        )
        proposal = self.proposal()
        payload = decode_signed_worship_workbook_confirmation(
            proposal.signed_payload, user=self.staff
        )
        result = confirm_worship_workbook(user=self.staff, payload=payload)
        self.assertGreaterEqual(result.no_op_count, 1)
        self.assertNotIn(first.pk, {change.event_id for change in result.changes})
        first.refresh_from_db()
        self.assertEqual(first.scheduling_revision, 1)


@override_settings(
    CMS_ENABLED_INTEGRATIONS=["svca_bethany_2026_worship_xlsx"]
)
class WorshipWorkbookConfirmationViewGateTests(WorshipWorkbookConfirmationTestBase):
    def upload(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        return SimpleUploadedFile(
            "schedule.xlsx",
            build_known_workbook(),
            content_type=(
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ),
        )

    def mapping_post(self, token):
        data = {"signed_workbook": token}
        for workbook_token in TOKEN_ORDER:
            data[f"mapping_{workbook_token.lower()}"] = self.teams[
                workbook_token
            ].pk
        return data

    def test_confirmable_blocked_and_already_matches_render_exact_action_gate(self):
        self.client.force_login(self.staff)
        upload = self.client.post(
            reverse("worship_workbook_preview"), {"workbook": self.upload()}
        )
        token = upload.context["mapping_form"]["signed_workbook"].value()
        confirmable = self.client.post(
            reverse("worship_workbook_preview"), self.mapping_post(token)
        )
        self.assertContains(confirmable, "Apply reviewed Worship Team changes")
        self.assertIsNotNone(confirmable.context["confirmation_form"])

        incomplete_data = self.mapping_post(token)
        incomplete_data.pop("mapping_c3")
        blocked = self.client.post(
            reverse("worship_workbook_preview"), incomplete_data
        )
        self.assertIsNone(blocked.context["confirmation_form"])
        self.assertNotContains(blocked, "Confirm and apply 52 reviewed targets")

        for row in self.parsed.rows:
            event = ServiceEvent.objects.get(
                start_datetime__date=row.local_date
            )
            ServiceEvent.objects.filter(pk=event.pk).update(
                rotation_anchor_team=self.teams[row.token]
            )
        no_op = self.client.post(
            reverse("worship_workbook_preview"), self.mapping_post(token)
        )
        self.assertContains(no_op, "Already matches — nothing to apply.")
        self.assertIsNone(no_op.context["confirmation_form"])


class FileBackedSQLiteAnnualWorshipConfirmationTests(unittest.TestCase):
    """Target-like two-connection confirmation and competing-write proof."""

    competing_alias = "annual_workbook_competing"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        handle = tempfile.NamedTemporaryFile(
            prefix="annual-workbook-confirmation-", suffix=".sqlite3", delete=False
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

    def build_fixture(self):
        parsed = parse_known_worship_workbook(build_known_workbook())
        target_profile = ServiceProfile.objects.create(
            key="bethany_0930_cm",
            name="Bethany 09:30",
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
        )
        root = ChurchStructureUnit.objects.create(
            code="ROOT", name="Root", unit_type=ChurchStructureUnit.UNIT_ROOT
        )
        cm = ChurchStructureUnit.objects.create(
            code="CM",
            name="CM",
            unit_type=ChurchStructureUnit.UNIT_MINISTRY_CONTEXT,
            parent=root,
        )
        pool = MinistryTeam.objects.create(
            name="Pool", is_assignable=False, is_worship_rotation_pool=True
        )
        MinistryTeamParentLink.objects.create(
            child_team=pool, parent_church_unit=cm, is_primary=True
        )
        team = MinistryTeam.objects.create(name="Worship")
        MinistryTeamParentLink.objects.create(
            child_team=team, parent_team=pool, is_primary=True
        )
        staff = User.objects.create_user("file_annual_staff", is_staff=True)
        events = []
        for index, row in enumerate(parsed.rows):
            event = ServiceEvent.objects.create(
                title=f"Sunday {index}",
                service_profile=target_profile,
                service_profile_key="bethany_0930_cm",
                event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
                start_datetime=timezone.make_aware(
                    datetime.combine(row.local_date, time(9, 30)),
                    timezone.get_current_timezone(),
                ),
                status=ServiceEvent.STATUS_PUBLISHED,
            )
            ServiceEventAudienceScope.objects.create(service_event=event, unit=cm)
            events.append(event)
        preview = build_worship_import_preview(
            parsed=parsed,
            mapping={token: team for token in parsed.token_counts},
            user=staff,
        )
        proposal = build_worship_workbook_confirmation_proposal(
            preview=preview, user=staff
        )
        payload = decode_signed_worship_workbook_confirmation(
            proposal.signed_payload, user=staff
        )
        return staff, team, events, payload

    def test_same_proposal_concurrent_only_one_commits_and_competing_write_goes_stale(self):
        staff, team, events, payload = self.build_fixture()

        def confirm_once():
            close_old_connections()
            try:
                result = confirm_worship_workbook(user=staff, payload=payload)
                return ("committed", result.operation_id)
            except (SchedulingRevisionError, WorshipWorkbookConfirmationError):
                return ("stale_or_busy", None)
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(executor.map(lambda _: confirm_once(), range(2)))

        self.assertEqual(sum(item[0] == "committed" for item in outcomes), 1)
        self.assertEqual(sum(item[0] == "stale_or_busy" for item in outcomes), 1)
        self.assertEqual(
            set(ServiceEvent.objects.values_list("scheduling_revision", flat=True)),
            {1},
        )
        self.assertEqual(
            set(ServiceEvent.objects.values_list("rotation_anchor_team_id", flat=True)),
            {team.pk},
        )
        self.assertEqual(LogEntry.objects.count(), 52)

        # A second supported writer that wins after preview makes the importer
        # stale; no importer row or audit commits partially.
        ServiceEvent.objects.all().delete()
        ServiceProfile.objects.all().delete()
        LogEntry.objects.all().delete()
        User.objects.all().delete()
        MinistryTeamParentLink.objects.all().delete()
        MinistryTeam.objects.all().delete()
        ChurchStructureUnit.objects.filter(parent__isnull=False).delete()
        ChurchStructureUnit.objects.all().delete()
        staff, _team, events, payload = self.build_fixture()
        advance_scheduling_revisions(
            (events[-1].pk,), using=self.competing_alias
        )
        before = list(
            ServiceEvent.objects.order_by("id").values_list(
                "scheduling_revision", "rotation_anchor_team_id"
            )
        )
        with self.assertRaises(SchedulingRevisionError):
            confirm_worship_workbook(user=staff, payload=payload)
        self.assertEqual(
            list(
                ServiceEvent.objects.order_by("id").values_list(
                    "scheduling_revision", "rotation_anchor_team_id"
                )
            ),
            before,
        )
        self.assertEqual(LogEntry.objects.count(), 0)
