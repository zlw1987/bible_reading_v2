"""Focused NOTIFY.1D producer tests.

Producer coverage captures the supported Core payload seam and intentionally
imports no notifications-app model or service. Notification persistence and
database idempotency remain covered by the notification foundation tests.
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import ChurchStructureMembership, ChurchStructureUnit
from core.notification_delivery import notification_sink_override_for_tests
from studies.meeting_role_notifications import (
    capture_meeting_role_notification_state,
    emit_meeting_role_notification,
)
from studies.models import (
    BibleStudyLesson,
    BibleStudyMeeting,
    BibleStudyMeetingAudienceScope,
    BibleStudyMeetingRole,
    BibleStudySeries,
)


User = get_user_model()


class MeetingRoleNotificationProducerTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(
            "study_notify_manager",
            password="pw12345!",
            is_staff=True,
        )
        self.user_en = User.objects.create_user(
            "study_notify_en",
            email="private-linked@example.com",
            password="pw12345!",
        )
        self.user_zh = User.objects.create_user(
            "study_notify_zh",
            password="pw12345!",
        )
        self.audience_only = User.objects.create_user(
            "study_audience_only",
            password="pw12345!",
        )
        self.outsider = User.objects.create_user(
            "study_outside_role",
            password="pw12345!",
        )
        self.user_en.profile.preferred_language = "en"
        self.user_en.profile.save(update_fields=["preferred_language"])
        self.user_zh.profile.preferred_language = "zh"
        self.user_zh.profile.save(update_fields=["preferred_language"])

        self.root = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_ROOT,
            code="NOTIFY-STUDIES-ROOT",
            name="全教会",
            name_en="Whole Church",
        )
        self.group = ChurchStructureUnit.objects.create(
            parent=self.root,
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="NOTIFY-STUDIES-GROUP",
            name="彩虹小组",
            name_en="Rainbow Group",
        )
        for user in (self.user_en, self.user_zh, self.audience_only):
            ChurchStructureMembership.objects.create(
                user=user,
                unit=self.group,
                status=ChurchStructureMembership.STATUS_ACTIVE,
                is_primary=True,
                start_date=timezone.localdate() - timedelta(days=1),
            )

        self.series = self._series()
        self.meeting = self._meeting(series=self.series)
        BibleStudyMeetingAudienceScope.objects.create(
            meeting=self.meeting,
            unit=self.group,
        )
        self.client.force_login(self.manager)
        session = self.client.session
        session["language"] = "en"
        session.save()

    def _series(
        self,
        *,
        status=BibleStudySeries.STATUS_PUBLISHED,
        is_active=True,
    ):
        return BibleStudySeries.objects.create(
            title="查经系列",
            title_en="Bible Study Series",
            status=status,
            is_active=is_active,
        )

    def _meeting(
        self,
        *,
        series=None,
        meeting_status=BibleStudyMeeting.STATUS_PUBLISHED,
        lesson_status=BibleStudyLesson.STATUS_PUBLISHED,
    ):
        lesson = BibleStudyLesson.objects.create(
            series=series or self._series(),
            title="约翰十五章",
            title_en="John 15",
            lesson_date=timezone.localdate() + timedelta(days=2),
            status=lesson_status,
        )
        return BibleStudyMeeting.objects.create(
            lesson=lesson,
            anchor_unit=self.group,
            meeting_datetime=timezone.now() + timedelta(days=2),
            location="PRIVATE MEETING LOCATION",
            status=meeting_status,
            created_by=self.manager,
        )

    def _role(
        self,
        *,
        meeting=None,
        user=None,
        role=BibleStudyMeetingRole.ROLE_DISCUSSION_LEADER,
        display_name="",
        notes="PRIVATE ROLE NOTE",
        notes_en="PRIVATE ENGLISH ROLE NOTE",
    ):
        return BibleStudyMeetingRole.objects.create(
            meeting=meeting or self.meeting,
            role=role,
            user=user,
            display_name=display_name,
            notes=notes,
            notes_en=notes_en,
        )

    def _post_data(self, *, user=None, **overrides):
        data = {
            "role": BibleStudyMeetingRole.ROLE_DISCUSSION_LEADER,
            "user": "" if user is None else user.id,
            "display_name": "",
            "notes": "PRIVATE ROLE NOTE",
            "notes_en": "PRIVATE ENGLISH ROLE NOTE",
        }
        data.update(overrides)
        return data

    def _post_with_payloads(self, url, data=None):
        payloads = []
        with notification_sink_override_for_tests(payloads.append):
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.post(url, data or {})
        return response, payloads

    def _emit_direct(self, meeting_role, previous_state):
        payloads = []
        with notification_sink_override_for_tests(payloads.append):
            with self.captureOnCommitCallbacks(execute=True):
                emit_meeting_role_notification(
                    meeting_role,
                    previous_state=previous_state,
                    actor=self.manager,
                )
        return payloads

    def test_create_linked_user_emits_exact_private_safe_assigned_payload(self):
        response, payloads = self._post_with_payloads(
            reverse("manage_bible_study_meeting_roles", args=[self.meeting.id]),
            self._post_data(user=self.user_en),
        )

        self.assertEqual(response.status_code, 302)
        role = BibleStudyMeetingRole.objects.get(meeting=self.meeting)
        self.assertEqual(len(payloads), 1)
        payload = payloads[0]
        self.assertEqual(payload.recipient, self.user_en)
        self.assertEqual(payload.source_module, "studies")
        self.assertEqual(payload.notification_type, "bible_study_role.assigned")
        self.assertEqual(payload.title, "New Bible Study serving role")
        self.assertEqual(payload.body, "John 15 · Discussion Leader")
        self.assertEqual(
            payload.target_url,
            reverse("bible_study_meeting_detail", args=[self.meeting.id]),
        )
        self.assertEqual(
            payload.source_model_label,
            "studies.BibleStudyMeetingRole",
        )
        self.assertEqual(payload.source_object_id, str(role.id))
        self.assertEqual(payload.actor, self.manager)
        self.assertTrue(
            payload.dedupe_key.startswith(f"studies:bsmr:{role.id}:assigned:")
        )
        self.assertEqual(dict(payload.metadata), {})
        self.assertNotEqual(payload.recipient, self.audience_only)
        snapshot = " ".join(
            [payload.title, payload.body, payload.target_url, str(dict(payload.metadata))]
        )
        for private_value in (
            "PRIVATE ROLE NOTE",
            "PRIVATE ENGLISH ROLE NOTE",
            "PRIVATE MEETING LOCATION",
            "private-linked@example.com",
            "NOTIFY-STUDIES-GROUP",
        ):
            self.assertNotIn(private_value, snapshot)

    def test_display_name_only_create_saves_without_payload(self):
        response, payloads = self._post_with_payloads(
            reverse("manage_bible_study_meeting_roles", args=[self.meeting.id]),
            self._post_data(user=None, display_name="Guest Host"),
        )

        self.assertEqual(response.status_code, 302)
        role = BibleStudyMeetingRole.objects.get(meeting=self.meeting)
        self.assertIsNone(role.user)
        self.assertEqual(role.display_name, "Guest Host")
        self.assertEqual(payloads, [])

    def test_recipient_chinese_preference_overrides_manager_session_language(self):
        response, payloads = self._post_with_payloads(
            reverse("manage_bible_study_meeting_roles", args=[self.meeting.id]),
            self._post_data(
                user=self.user_zh,
                role=BibleStudyMeetingRole.ROLE_HOST,
            ),
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(payloads), 1)
        self.assertEqual(payloads[0].title, "新的查经服事安排")
        self.assertEqual(payloads[0].body, "约翰十五章 · 接待")

    def test_same_user_role_type_change_emits_updated_and_preserves_source_state(self):
        role = self._role(user=self.user_en)
        role.confirm("Keep confirmation")
        role.refresh_from_db()
        original_id = role.id
        original_confirmed_at = role.confirmed_at

        response, payloads = self._post_with_payloads(
            reverse("edit_bible_study_meeting_role", args=[role.id]),
            self._post_data(
                user=self.user_en,
                role=BibleStudyMeetingRole.ROLE_HOST,
            ),
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(payloads), 1)
        self.assertEqual(payloads[0].recipient, self.user_en)
        self.assertEqual(payloads[0].notification_type, "bible_study_role.updated")
        self.assertEqual(payloads[0].body, "John 15 · Host")
        role.refresh_from_db()
        self.assertEqual(role.id, original_id)
        self.assertEqual(role.confirmed_at, original_confirmed_at)
        self.assertEqual(role.confirmation_note, "Keep confirmation")

    def test_user_reassignment_assigns_only_new_user_with_priority_over_role_change(self):
        role = self._role(user=self.user_en)

        response, payloads = self._post_with_payloads(
            reverse("edit_bible_study_meeting_role", args=[role.id]),
            self._post_data(
                user=self.user_zh,
                role=BibleStudyMeetingRole.ROLE_HOST,
            ),
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(payloads), 1)
        self.assertEqual(payloads[0].recipient, self.user_zh)
        self.assertEqual(payloads[0].notification_type, "bible_study_role.assigned")
        self.assertNotEqual(payloads[0].recipient, self.user_en)

    def test_display_only_to_linked_assigns_and_linked_to_display_only_is_quiet(self):
        display_role = self._role(user=None, display_name="Guest")
        response, payloads = self._post_with_payloads(
            reverse("edit_bible_study_meeting_role", args=[display_role.id]),
            self._post_data(user=self.user_en),
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual([payload.recipient for payload in payloads], [self.user_en])
        self.assertEqual(payloads[0].notification_type, "bible_study_role.assigned")

        display_role.refresh_from_db()
        response, payloads = self._post_with_payloads(
            reverse("edit_bible_study_meeting_role", args=[display_role.id]),
            self._post_data(user=None, display_name="Guest Again"),
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(payloads, [])

    def test_notes_display_name_and_unchanged_edits_emit_nothing(self):
        role = self._role(user=self.user_en)
        edits = [
            {"notes": "notes changed"},
            {"notes_en": "English notes changed"},
            {"display_name": "Text label only changed"},
            {},
        ]
        for overrides in edits:
            role.refresh_from_db()
            data = self._post_data(
                user=self.user_en,
                role=role.role,
                display_name=role.display_name,
                notes=role.notes,
                notes_en=role.notes_en,
            )
            data.update(overrides)
            with self.subTest(overrides=overrides):
                response, payloads = self._post_with_payloads(
                    reverse("edit_bible_study_meeting_role", args=[role.id]),
                    data,
                )
                self.assertEqual(response.status_code, 302)
                self.assertEqual(payloads, [])

    def test_outside_audience_explicit_role_update_notifies_without_widening_access(self):
        role = self._role(user=self.outsider)
        audience_rows_before = BibleStudyMeetingAudienceScope.objects.count()
        memberships_before = ChurchStructureMembership.objects.count()

        response, payloads = self._post_with_payloads(
            reverse("edit_bible_study_meeting_role", args=[role.id]),
            self._post_data(
                user=self.outsider,
                role=BibleStudyMeetingRole.ROLE_HOST,
            ),
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual([payload.recipient for payload in payloads], [self.outsider])
        self.assertEqual(payloads[0].notification_type, "bible_study_role.updated")
        self.assertEqual(
            payloads[0].target_url,
            reverse("bible_study_meeting_detail", args=[self.meeting.id]),
        )
        self.assertEqual(
            BibleStudyMeetingAudienceScope.objects.count(),
            audience_rows_before,
        )
        self.assertEqual(ChurchStructureMembership.objects.count(), memberships_before)
        self.assertFalse(
            ChurchStructureMembership.objects.filter(user=self.outsider).exists()
        )
        self.assertNotIn(self.audience_only, [payload.recipient for payload in payloads])

        self.client.force_login(self.outsider)
        detail_url = reverse("bible_study_meeting_detail", args=[self.meeting.id])
        detail_response = self.client.get(detail_url)
        self.assertEqual(detail_response.status_code, 200)
        self.assertNotContains(
            detail_response,
            reverse("edit_bible_study_meeting_role", args=[role.id]),
        )
        manage_response = self.client.get(
            reverse("manage_bible_study_meeting_roles", args=[self.meeting.id])
        )
        self.assertEqual(manage_response.status_code, 302)
        self.assertEqual(manage_response.url, detail_url)

    def test_ineligible_hierarchy_and_inactive_user_emit_nothing(self):
        scenarios = [
            {
                "name": "draft meeting",
                "meeting": self._meeting(
                    meeting_status=BibleStudyMeeting.STATUS_DRAFT
                ),
                "user": self.user_en,
            },
            {
                "name": "cancelled meeting",
                "meeting": self._meeting(
                    meeting_status=BibleStudyMeeting.STATUS_CANCELLED
                ),
                "user": self.user_en,
            },
            {
                "name": "draft lesson",
                "meeting": self._meeting(
                    lesson_status=BibleStudyLesson.STATUS_DRAFT
                ),
                "user": self.user_en,
            },
            {
                "name": "cancelled lesson",
                "meeting": self._meeting(
                    lesson_status=BibleStudyLesson.STATUS_CANCELLED
                ),
                "user": self.user_en,
            },
            {
                "name": "inactive series",
                "meeting": self._meeting(series=self._series(is_active=False)),
                "user": self.user_en,
            },
            {
                "name": "cancelled series",
                "meeting": self._meeting(
                    series=self._series(status=BibleStudySeries.STATUS_CANCELLED)
                ),
                "user": self.user_en,
            },
        ]
        inactive_user = User.objects.create_user(
            "inactive_study_server",
            password="pw12345!",
            is_active=False,
        )
        scenarios.append(
            {
                "name": "inactive linked user",
                "meeting": self.meeting,
                "user": inactive_user,
            }
        )

        for scenario in scenarios:
            with self.subTest(scenario=scenario["name"]):
                role = self._role(
                    meeting=scenario["meeting"],
                    user=scenario["user"],
                )
                self.assertEqual(
                    self._emit_direct(
                        role,
                        capture_meeting_role_notification_state(None),
                    ),
                    [],
                )

    @override_settings(CMS_ENABLED_MODULES=["studies"])
    def test_disabled_notifications_keeps_source_write_and_skips_sink(self):
        response, payloads = self._post_with_payloads(
            reverse("manage_bible_study_meeting_roles", args=[self.meeting.id]),
            self._post_data(user=self.user_en),
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            BibleStudyMeetingRole.objects.filter(
                meeting=self.meeting,
                user=self.user_en,
            ).exists()
        )
        self.assertEqual(payloads, [])

    def test_invalid_form_does_not_save_or_emit(self):
        count_before = BibleStudyMeetingRole.objects.count()
        response, payloads = self._post_with_payloads(
            reverse("manage_bible_study_meeting_roles", args=[self.meeting.id]),
            self._post_data(user=None, display_name=""),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(BibleStudyMeetingRole.objects.count(), count_before)
        self.assertEqual(payloads, [])

    def test_delete_and_confirmation_posts_emit_nothing(self):
        delete_role = self._role(user=self.user_en)
        response, payloads = self._post_with_payloads(
            reverse("delete_bible_study_meeting_role", args=[delete_role.id]),
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(payloads, [])
        self.assertFalse(BibleStudyMeetingRole.objects.filter(id=delete_role.id).exists())

        confirm_role = self._role(user=self.user_en)
        self.client.force_login(self.user_en)
        confirm_url = reverse(
            "confirm_bible_study_role_serving",
            args=[self.meeting.id],
        )
        response, payloads = self._post_with_payloads(
            confirm_url,
            {"confirmation_note": "First confirmation"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(payloads, [])
        confirm_role.refresh_from_db()
        self.assertIsNotNone(confirm_role.confirmed_at)
        self.assertEqual(confirm_role.confirmation_note, "First confirmation")

        response, payloads = self._post_with_payloads(
            confirm_url,
            {"confirmation_note": "Changed confirmation note"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(payloads, [])
        confirm_role.refresh_from_db()
        self.assertEqual(confirm_role.confirmation_note, "Changed confirmation note")

    def test_meeting_and_lesson_cancellation_actions_emit_nothing(self):
        self._role(user=self.user_en)
        response, payloads = self._post_with_payloads(
            reverse("cancel_bible_study_meeting", args=[self.meeting.id]),
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(payloads, [])

        another_meeting = self._meeting()
        self._role(meeting=another_meeting, user=self.user_en)
        response, payloads = self._post_with_payloads(
            reverse("cancel_bible_study_lesson", args=[another_meeting.lesson_id]),
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(payloads, [])

    def test_direct_orm_create_and_edit_have_no_signal_or_payload(self):
        payloads = []
        with notification_sink_override_for_tests(payloads.append):
            with self.captureOnCommitCallbacks(execute=True):
                role = self._role(user=self.user_en)
                role.role = BibleStudyMeetingRole.ROLE_HOST
                role.save()
        self.assertEqual(payloads, [])

    def test_dedupe_is_stable_per_save_and_new_for_later_genuine_mutations(self):
        role = self._role(user=self.user_en)
        original_assignment_state = capture_meeting_role_notification_state(None)
        original = self._emit_direct(role, original_assignment_state)
        self.assertEqual(len(original), 1)

        before_update = capture_meeting_role_notification_state(role)
        role.role = BibleStudyMeetingRole.ROLE_HOST
        role.save()
        first_update = self._emit_direct(role, before_update)
        repeated_update = self._emit_direct(role, before_update)
        self.assertEqual(first_update[0].dedupe_key, repeated_update[0].dedupe_key)

        next_before = capture_meeting_role_notification_state(role)
        role.role = BibleStudyMeetingRole.ROLE_SUPPORT
        role.save()
        later_update = self._emit_direct(role, next_before)
        self.assertNotEqual(
            first_update[0].dedupe_key,
            later_update[0].dedupe_key,
        )

        before_b = capture_meeting_role_notification_state(role)
        role.user = self.user_zh
        role.save()
        assigned_b = self._emit_direct(role, before_b)
        before_a_again = capture_meeting_role_notification_state(role)
        role.user = self.user_en
        role.save()
        assigned_a_again = self._emit_direct(role, before_a_again)
        self.assertEqual(assigned_b[0].notification_type, "bible_study_role.assigned")
        self.assertEqual(
            assigned_a_again[0].notification_type,
            "bible_study_role.assigned",
        )
        self.assertNotEqual(original[0].dedupe_key, assigned_a_again[0].dedupe_key)
        self.assertNotEqual(assigned_b[0].dedupe_key, assigned_a_again[0].dedupe_key)
