"""Focused NOTIFY.1C producer tests.

These tests capture the supported Core sink payload. They intentionally import
no notifications-app model or service: producer coverage proves ministry source
mutations map to directed Core payloads, while notification persistence and DB
idempotency remain covered by the notifications foundation tests.
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import ChurchStructureMembership, ChurchStructureUnit
from core.notification_delivery import notification_sink_override_for_tests
from events.models import ServiceEvent, ServiceEventAudienceScope
from ministry.models import (
    MinistryTeam,
    TeamAssignment,
    TeamAssignmentMember,
    TeamMembership,
)
from ministry.services.assignment_notifications import (
    capture_assignment_notification_state,
    emit_assignment_notifications,
)


User = get_user_model()


class AssignmentNotificationProducerTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(
            "notify_manager",
            password="pw12345!",
            is_staff=True,
            is_superuser=True,
        )
        self.user_en = User.objects.create_user(
            "notify_en",
            email="linked-private@example.com",
            password="pw12345!",
        )
        self.user_zh = User.objects.create_user(
            "notify_zh",
            password="pw12345!",
        )
        self.user_two = User.objects.create_user(
            "notify_two",
            password="pw12345!",
        )
        self.audience_only_user = User.objects.create_user(
            "audience_only",
            password="pw12345!",
        )
        self.manager.profile.preferred_language = "en"
        self.manager.profile.save(update_fields=["preferred_language"])
        self.user_en.profile.preferred_language = "en"
        self.user_en.profile.save(update_fields=["preferred_language"])
        self.user_zh.profile.preferred_language = "zh"
        self.user_zh.profile.save(update_fields=["preferred_language"])
        self.user_two.profile.preferred_language = "en"
        self.user_two.profile.save(update_fields=["preferred_language"])

        self.team = MinistryTeam.objects.create(
            name="音响团队",
            name_en="Audio Team",
        )
        self.member_en = TeamMembership.objects.create(
            team=self.team,
            user=self.user_en,
            email="linked-private@example.com",
            notes="PRIVATE MEMBERSHIP NOTE",
        )
        self.member_zh = TeamMembership.objects.create(
            team=self.team,
            user=self.user_zh,
        )
        self.member_two = TeamMembership.objects.create(
            team=self.team,
            user=self.user_two,
        )
        self.display_only = TeamMembership.objects.create(
            team=self.team,
            display_name="Display Only Helper",
        )

        self.event = self._event(
            "主日聚会",
            "Sunday Gathering",
            days=2,
        )
        self.event.required_teams.add(self.team)
        self.event_two = self._event(
            "特别聚会",
            "Special Gathering",
            days=3,
        )
        self.event_two.required_teams.add(self.team)
        self.client.force_login(self.manager)
        session = self.client.session
        session["language"] = "en"
        session.save()

    def _event(self, title, title_en, *, days, status=ServiceEvent.STATUS_PUBLISHED):
        return ServiceEvent.objects.create(
            title=title,
            title_en=title_en,
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
            start_datetime=timezone.now() + timedelta(days=days),
            status=status,
        )

    def _assignment(self, *, event=None, members=None, status=None, notes="source note"):
        assignment = TeamAssignment.objects.create(
            service_event=event or self.event,
            ministry_team=self.team,
            status=status or TeamAssignment.STATUS_SCHEDULED,
            notes=notes,
            created_by=self.manager,
        )
        rows = []
        for membership in members or [self.member_en]:
            rows.append(
                TeamAssignmentMember.objects.create(
                    assignment=assignment,
                    membership=membership,
                )
            )
        return assignment, rows

    def _create_data(self, members, **overrides):
        data = {
            "service_event": self.event.id,
            "ministry_team": self.team.id,
            "assigned_members": [member.id for member in members],
            "status": TeamAssignment.STATUS_SCHEDULED,
            "notes": "PRIVATE ASSIGNMENT NOTE",
        }
        data.update(overrides)
        return data

    def _edit_data(self, assignment, members, **overrides):
        data = {
            "service_event": assignment.service_event_id,
            "ministry_team": assignment.ministry_team_id,
            "assigned_members": [member.id for member in members],
            "status": assignment.status,
            "notes": assignment.notes,
        }
        data.update(overrides)
        return data

    def _post_with_payloads(self, url, data):
        payloads = []
        with notification_sink_override_for_tests(payloads.append):
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.post(url, data)
        return response, payloads

    def _get_with_payloads(self, url):
        payloads = []
        with notification_sink_override_for_tests(payloads.append):
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.get(url)
        return response, payloads

    def _emit_direct(self, assignment, previous_state):
        payloads = []
        with notification_sink_override_for_tests(payloads.append):
            with self.captureOnCommitCallbacks(execute=True):
                emit_assignment_notifications(
                    assignment,
                    previous_state=previous_state,
                    actor=self.manager,
                )
        return payloads

    def test_create_linked_member_emits_exact_private_safe_payload(self):
        response, payloads = self._post_with_payloads(
            reverse("create_team_assignment"),
            self._create_data([self.member_en]),
        )

        self.assertEqual(response.status_code, 302)
        assignment = TeamAssignment.objects.get()
        member = assignment.assignment_members.get()
        self.assertEqual(len(payloads), 1)
        payload = payloads[0]
        self.assertEqual(payload.recipient, self.user_en)
        self.assertEqual(payload.source_module, "ministry")
        self.assertEqual(payload.notification_type, "team_assignment.assigned")
        self.assertEqual(payload.title, "New serving assignment")
        self.assertEqual(payload.body, "Sunday Gathering · Audio Team")
        self.assertEqual(
            payload.target_url,
            f"{reverse('my_serving')}?tab=all#serving-assignment-{member.id}",
        )
        self.assertEqual(payload.source_model_label, "ministry.TeamAssignmentMember")
        self.assertEqual(payload.source_object_id, str(member.id))
        self.assertEqual(payload.actor, self.manager)
        self.assertEqual(payload.dedupe_key, f"ministry:tam:{member.id}:assigned")
        self.assertEqual(dict(payload.metadata), {})
        snapshot = " ".join(
            [payload.title, payload.body, payload.target_url, str(dict(payload.metadata))]
        )
        self.assertNotIn("PRIVATE ASSIGNMENT NOTE", snapshot)
        self.assertNotIn("PRIVATE MEMBERSHIP NOTE", snapshot)
        self.assertNotIn("linked-private@example.com", snapshot)
        self.assertNotIn("audience", snapshot.lower())

    def test_create_two_linked_members_is_directed_once_each_not_audience_fanout(self):
        root = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_ROOT,
            code="NOTIFY-ROOT",
            name="全教会",
            name_en="Whole Church",
        )
        ServiceEventAudienceScope.objects.create(service_event=self.event, unit=root)
        ChurchStructureMembership.objects.create(
            user=self.audience_only_user,
            unit=root,
            status=ChurchStructureMembership.STATUS_ACTIVE,
            is_primary=True,
            start_date=timezone.localdate() - timedelta(days=1),
        )

        response, payloads = self._post_with_payloads(
            reverse("create_team_assignment"),
            self._create_data(
                [self.member_en, self.member_two],
                audience_override_ack="on",
            ),
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(payloads), 2)
        self.assertEqual(
            {payload.recipient for payload in payloads},
            {self.user_en, self.user_two},
        )
        self.assertNotIn(self.audience_only_user, [p.recipient for p in payloads])

    def test_display_name_only_emits_none_and_mixed_emits_only_linked_user(self):
        response, payloads = self._post_with_payloads(
            reverse("create_team_assignment"),
            self._create_data([self.display_only]),
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(payloads, [])
        TeamAssignment.objects.all().delete()

        response, payloads = self._post_with_payloads(
            reverse("create_team_assignment"),
            self._create_data([self.member_en, self.display_only]),
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual([payload.recipient for payload in payloads], [self.user_en])

    def test_outside_audience_ack_notifies_without_creating_audience_or_belonging(self):
        root = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_ROOT,
            code="ACK-ROOT",
            name="北区",
            name_en="North",
        )
        ServiceEventAudienceScope.objects.create(service_event=self.event, unit=root)
        audience_rows_before = self.event.audience_scope_links.count()

        response, payloads = self._post_with_payloads(
            reverse("create_team_assignment"),
            self._create_data([self.member_en], audience_override_ack="on"),
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual([payload.recipient for payload in payloads], [self.user_en])
        self.assertEqual(self.event.audience_scope_links.count(), audience_rows_before)
        self.assertFalse(
            ChurchStructureMembership.objects.filter(user=self.user_en).exists()
        )

    def test_recipient_chinese_preference_overrides_manager_session_language(self):
        response, payloads = self._post_with_payloads(
            reverse("create_team_assignment"),
            self._create_data([self.member_zh]),
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(payloads), 1)
        self.assertEqual(payloads[0].title, "新的服事安排")
        self.assertEqual(payloads[0].body, "主日聚会 · 音响团队")

    def test_invalid_acknowledgement_write_emits_nothing(self):
        root = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_ROOT,
            code="INVALID-ROOT",
            name="全教会",
            name_en="Whole Church",
        )
        district = ChurchStructureUnit.objects.create(
            parent=root,
            unit_type=ChurchStructureUnit.UNIT_DISTRICT,
            code="INVALID-DISTRICT",
            name="北区",
            name_en="North District",
        )
        ServiceEventAudienceScope.objects.create(
            service_event=self.event,
            unit=district,
        )

        response, payloads = self._post_with_payloads(
            reverse("create_team_assignment"),
            self._create_data([self.member_en]),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payloads, [])
        self.assertFalse(TeamAssignment.objects.exists())

    @override_settings(CMS_ENABLED_MODULES=["events", "ministry"])
    def test_disabled_notifications_keeps_source_write_and_skips_sink(self):
        response, payloads = self._post_with_payloads(
            reverse("create_team_assignment"),
            self._create_data([self.member_en]),
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(TeamAssignmentMember.objects.exists())
        self.assertEqual(payloads, [])

    def test_ordinary_edits_removal_cancellation_and_confirmation_emit_none(self):
        assignment, rows = self._assignment(members=[self.member_en, self.member_two])
        retained = rows[0]
        retained.confirm("keep this confirmation")
        retained.refresh_from_db()
        retained_id = retained.id
        retained_confirmed_at = retained.confirmed_at

        ordinary_saves = [
            {"notes": "notes only"},
            {"status": TeamAssignment.STATUS_PREPARED},
            {"status": TeamAssignment.STATUS_CONFIRMED},
            {"status": TeamAssignment.STATUS_COMPLETED},
            {},
        ]
        for overrides in ordinary_saves:
            assignment.refresh_from_db()
            response, payloads = self._post_with_payloads(
                reverse("edit_team_assignment", args=[assignment.id]),
                self._edit_data(
                    assignment,
                    [self.member_en, self.member_two],
                    **overrides,
                ),
            )
            self.assertEqual(response.status_code, 302)
            self.assertEqual(payloads, [])

        assignment.refresh_from_db()
        response, payloads = self._post_with_payloads(
            reverse("edit_team_assignment", args=[assignment.id]),
            self._edit_data(assignment, [self.member_en]),
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(payloads, [])

        assignment.refresh_from_db()
        response, payloads = self._post_with_payloads(
            reverse("edit_team_assignment", args=[assignment.id]),
            self._edit_data(
                assignment,
                [self.member_en],
                status=TeamAssignment.STATUS_CANCELLED,
            ),
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(payloads, [])

        retained.refresh_from_db()
        self.assertEqual(retained.id, retained_id)
        self.assertEqual(retained.confirmed_at, retained_confirmed_at)
        self.assertEqual(retained.confirmation_note, "keep this confirmation")

        # Confirmation has its own explicit POST path and is deliberately not a
        # NOTIFY.1C producer.
        assignment.status = TeamAssignment.STATUS_SCHEDULED
        assignment.save()
        retained.confirmed_at = None
        retained.confirmation_note = ""
        retained.save()
        self.client.force_login(self.user_en)
        response, payloads = self._post_with_payloads(
            reverse("confirm_team_assignment", args=[assignment.id]),
            {"confirmation_note": "confirmed by member"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(payloads, [])

    def test_assignment_and_service_event_cancellation_actions_emit_none(self):
        assignment, _rows = self._assignment(members=[self.member_en])

        response, payloads = self._post_with_payloads(
            reverse("cancel_team_assignment", args=[assignment.id]),
            {},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(payloads, [])
        assignment.refresh_from_db()
        self.assertEqual(assignment.status, TeamAssignment.STATUS_CANCELLED)

        event_assignment, _rows = self._assignment(
            event=self.event_two,
            members=[self.member_two],
        )
        response, payloads = self._post_with_payloads(
            reverse("cancel_service_event", args=[self.event_two.id]),
            {},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(payloads, [])
        event_assignment.refresh_from_db()
        self.event_two.refresh_from_db()
        self.assertEqual(
            event_assignment.status,
            TeamAssignment.STATUS_CANCELLED,
        )
        self.assertEqual(self.event_two.status, ServiceEvent.STATUS_CANCELLED)

    def test_add_member_notifies_only_new_row_and_repeat_save_is_quiet(self):
        assignment, rows = self._assignment(members=[self.member_en])
        retained = rows[0]
        retained.confirm("preserved")
        original_confirmed_at = retained.confirmed_at

        response, payloads = self._post_with_payloads(
            reverse("edit_team_assignment", args=[assignment.id]),
            self._edit_data(assignment, [self.member_en, self.member_two]),
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(payloads), 1)
        self.assertEqual(payloads[0].recipient, self.user_two)
        self.assertEqual(payloads[0].notification_type, "team_assignment.assigned")
        new_row = assignment.assignment_members.get(membership=self.member_two)
        self.assertEqual(payloads[0].source_object_id, str(new_row.id))
        retained.refresh_from_db()
        self.assertEqual(retained.confirmed_at, original_confirmed_at)
        self.assertEqual(retained.confirmation_note, "preserved")

        assignment.refresh_from_db()
        response, repeat_payloads = self._post_with_payloads(
            reverse("edit_team_assignment", args=[assignment.id]),
            self._edit_data(assignment, [self.member_en, self.member_two]),
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(repeat_payloads, [])

    def test_event_change_updates_retained_and_assigns_new_without_duplicates(self):
        assignment, rows = self._assignment(members=[self.member_en])
        retained = rows[0]

        response, payloads = self._post_with_payloads(
            reverse("edit_team_assignment", args=[assignment.id]),
            self._edit_data(
                assignment,
                [self.member_en, self.member_two],
                service_event=self.event_two.id,
            ),
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(payloads), 2)
        by_recipient = {payload.recipient: payload for payload in payloads}
        self.assertEqual(
            by_recipient[self.user_en].notification_type,
            "team_assignment.updated",
        )
        self.assertEqual(
            by_recipient[self.user_two].notification_type,
            "team_assignment.assigned",
        )
        self.assertEqual(by_recipient[self.user_en].source_object_id, str(retained.id))
        self.assertEqual(
            by_recipient[self.user_en].body,
            "Special Gathering · Audio Team",
        )
        self.assertEqual(len({p.recipient.pk for p in payloads}), 2)

    def test_reactivation_and_event_change_emit_one_update_per_retained_member(self):
        assignment, rows = self._assignment(
            members=[self.member_en, self.member_two],
            status=TeamAssignment.STATUS_CANCELLED,
        )

        response, payloads = self._post_with_payloads(
            reverse("edit_team_assignment", args=[assignment.id]),
            self._edit_data(
                assignment,
                [self.member_en, self.member_two],
                service_event=self.event_two.id,
                status=TeamAssignment.STATUS_SCHEDULED,
            ),
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(payloads), 2)
        self.assertEqual(
            {payload.notification_type for payload in payloads},
            {"team_assignment.updated"},
        )
        self.assertEqual(
            {payload.source_object_id for payload in payloads},
            {str(row.id) for row in rows},
        )

        assignment.refresh_from_db()
        response, repeat_payloads = self._post_with_payloads(
            reverse("edit_team_assignment", args=[assignment.id]),
            self._edit_data(assignment, [self.member_en, self.member_two]),
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(repeat_payloads, [])

    def test_update_dedupe_is_stable_for_same_save_and_new_for_future_change(self):
        assignment, _rows = self._assignment(members=[self.member_en])
        before = capture_assignment_notification_state(assignment)
        assignment.service_event = self.event_two
        assignment.save()
        first = self._emit_direct(assignment, before)
        repeated = self._emit_direct(assignment, before)
        self.assertEqual(first[0].dedupe_key, repeated[0].dedupe_key)

        next_before = capture_assignment_notification_state(assignment)
        assignment.service_event = self.event
        assignment.save()
        later = self._emit_direct(assignment, next_before)
        self.assertNotEqual(first[0].dedupe_key, later[0].dedupe_key)

    def test_ineligible_current_source_rows_emit_none(self):
        assignment, _rows = self._assignment(members=[self.member_en])
        empty_state = capture_assignment_notification_state(None)

        self.team.is_active = False
        self.team.save(update_fields=["is_active", "updated_at"])
        self.assertEqual(self._emit_direct(assignment, empty_state), [])
        self.team.is_active = True
        self.team.save(update_fields=["is_active", "updated_at"])

        self.member_en.is_active = False
        self.member_en.save(update_fields=["is_active", "updated_at"])
        self.assertEqual(self._emit_direct(assignment, empty_state), [])
        self.member_en.is_active = True
        self.member_en.save(update_fields=["is_active", "updated_at"])

        self.event.status = ServiceEvent.STATUS_DRAFT
        self.event.save(update_fields=["status", "updated_at"])
        self.assertEqual(self._emit_direct(assignment, empty_state), [])
        self.event.status = ServiceEvent.STATUS_CANCELLED
        self.event.save(update_fields=["status", "updated_at"])
        self.assertEqual(self._emit_direct(assignment, empty_state), [])

    def test_team_schedule_uses_same_create_add_notes_and_display_rules(self):
        create_url = (
            reverse("team_schedule", args=[self.team.id])
            + f"?event={self.event.id}"
        )
        response, payloads = self._post_with_payloads(
            create_url,
            {
                "assigned_members": [self.member_en.id],
                "status": TeamAssignment.STATUS_SCHEDULED,
                "notes": "scheduled",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual([p.notification_type for p in payloads], ["team_assignment.assigned"])
        assignment = TeamAssignment.objects.get()
        self.assertEqual(assignment.service_event, self.event)

        edit_url = (
            reverse("team_schedule", args=[self.team.id])
            + f"?assignment={assignment.id}"
        )
        response, payloads = self._post_with_payloads(
            edit_url,
            {
                "assigned_members": [self.member_en.id, self.member_two.id],
                "status": TeamAssignment.STATUS_SCHEDULED,
                "notes": "scheduled",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual([p.recipient for p in payloads], [self.user_two])

        response, payloads = self._post_with_payloads(
            edit_url,
            {
                "assigned_members": [self.member_en.id, self.member_two.id],
                "status": TeamAssignment.STATUS_SCHEDULED,
                "notes": "notes only",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(payloads, [])

        display_event = self._event("探访", "Visit", days=4)
        display_event.required_teams.add(self.team)
        response, payloads = self._post_with_payloads(
            reverse("team_schedule", args=[self.team.id])
            + f"?event={display_event.id}",
            {
                "assigned_members": [self.display_only.id],
                "status": TeamAssignment.STATUS_SCHEDULED,
                "notes": "display only",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(payloads, [])

    def test_copy_forward_get_is_read_only_and_post_notifies_without_confirmation_copy(self):
        source_event = self._event("上周聚会", "Prior Gathering", days=1)
        source_assignment, source_rows = self._assignment(
            event=source_event,
            members=[self.member_two],
        )
        source_rows[0].confirm("source confirmation")
        target_url = (
            reverse("team_schedule", args=[self.team.id])
            + f"?event={self.event.id}&suggest=team"
        )
        before_assignments = TeamAssignment.objects.count()
        before_members = TeamAssignmentMember.objects.count()

        response, payloads = self._get_with_payloads(target_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payloads, [])
        self.assertEqual(TeamAssignment.objects.count(), before_assignments)
        self.assertEqual(TeamAssignmentMember.objects.count(), before_members)

        response, payloads = self._post_with_payloads(
            target_url,
            {
                "assigned_members": [self.member_two.id],
                "status": TeamAssignment.STATUS_SCHEDULED,
                "notes": "explicit copy-forward save",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(payloads), 1)
        self.assertEqual(payloads[0].recipient, self.user_two)
        target_assignment = TeamAssignment.objects.exclude(id=source_assignment.id).get()
        target_member = target_assignment.assignment_members.get()
        self.assertIsNone(target_member.confirmed_at)
        self.assertEqual(target_member.confirmation_note, "")

    def test_direct_orm_member_creation_has_no_signal_or_payload(self):
        payloads = []
        with notification_sink_override_for_tests(payloads.append):
            with self.captureOnCommitCallbacks(execute=True):
                assignment = TeamAssignment.objects.create(
                    service_event=self.event,
                    ministry_team=self.team,
                    status=TeamAssignment.STATUS_SCHEDULED,
                )
                TeamAssignmentMember.objects.create(
                    assignment=assignment,
                    membership=self.member_en,
                )
        self.assertEqual(payloads, [])
