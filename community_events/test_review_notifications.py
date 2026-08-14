"""Focused NOTIFY.1E Community Activity review-outcome producer tests.

Producer coverage uses the Core test sink and intentionally imports no
notifications-app model or service. Notification persistence and database
idempotency remain owned by the notification foundation tests.
"""

from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import transaction
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import ChurchStructureMembership, ChurchStructureUnit
from core.notification_delivery import notification_sink_override_for_tests
from events.models import ServiceEvent
from ministry.models import TeamAssignment, TeamAssignmentMember
from studies.models import BibleStudyMeetingRole

from .models import (
    ActivitySignup,
    CommunityActivity,
    CommunityActivityAudienceScope,
    CommunityActivityCoOrganizer,
    CommunityActivitySubmissionBlock,
)
from .review_notifications import emit_review_outcome_notification
from .views import _apply_locked_review_transition


User = get_user_model()
_DEFAULT_CREATOR = object()


class CommunityActivityReviewNotificationTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(
            "activity_review_staff",
            password="testpass123",
            is_staff=True,
        )
        self.creator_en = User.objects.create_user(
            "activity_creator_en",
            password="testpass123",
        )
        self.creator_zh = User.objects.create_user(
            "activity_creator_zh",
            password="testpass123",
        )
        self.co_organizer = User.objects.create_user(
            "activity_co_organizer",
            password="testpass123",
        )
        self.audience_user = User.objects.create_user(
            "activity_audience_user",
            password="testpass123",
        )
        self.signup_user = User.objects.create_user(
            "activity_signup_user",
            password="testpass123",
        )
        self.hidden_user = User.objects.create_user(
            "activity_hidden_user",
            password="testpass123",
        )
        self.creator_en.profile.preferred_language = "en"
        self.creator_en.profile.save(update_fields=["preferred_language"])
        self.creator_zh.profile.preferred_language = "zh"
        self.creator_zh.profile.save(update_fields=["preferred_language"])

        self.root = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_ROOT,
            code="NOTIFY-COMMUNITY-ROOT",
            name="全教会",
            name_en="Whole Church",
        )
        self.group = ChurchStructureUnit.objects.create(
            parent=self.root,
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="NOTIFY-COMMUNITY-GROUP",
            name="彩虹小组",
            name_en="Rainbow Group",
        )
        for user in (self.audience_user, self.signup_user):
            ChurchStructureMembership.objects.create(
                user=user,
                unit=self.group,
                status=ChurchStructureMembership.STATUS_ACTIVE,
                is_primary=True,
                start_date=timezone.localdate() - timedelta(days=1),
            )

    def _activity(
        self,
        *,
        status=CommunityActivity.STATUS_PENDING_REVIEW,
        created_by=_DEFAULT_CREATOR,
        with_related=True,
        **overrides,
    ):
        data = {
            "title": "社区野餐",
            "title_en": "Community Picnic",
            "description": "活动详情",
            "description_en": "Activity details",
            "organizer": "DISPLAY ORGANIZER ONLY",
            "requested_audience_note": "PRIVATE AUDIENCE NOTE",
            "start_datetime": timezone.now() + timedelta(days=7),
            "location": "PRIVATE LOCATION",
            "status": status,
            "created_by": (
                self.creator_en if created_by is _DEFAULT_CREATOR else created_by
            ),
        }
        data.update(overrides)
        activity = CommunityActivity.objects.create(**data)
        if with_related:
            CommunityActivityAudienceScope.objects.create(
                activity=activity,
                structure_unit=self.group,
            )
            CommunityActivityCoOrganizer.objects.create(
                activity=activity,
                user=self.co_organizer,
                added_by=activity.created_by or self.staff,
            )
            ActivitySignup.objects.create(
                activity=activity,
                user=self.signup_user,
            )
        return activity

    def _review_url(self, activity, action):
        return reverse(
            f"community_activity_review_{action}",
            args=[activity.id],
        )

    def _post_review(self, activity, action, data=None, *, language="en"):
        self.client.force_login(self.staff)
        session = self.client.session
        session["language"] = language
        session.save()
        payloads = []
        with notification_sink_override_for_tests(payloads.append):
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.post(
                    self._review_url(activity, action),
                    data or {},
                )
        return response, payloads

    def _emit_direct(self, activity):
        payloads = []
        with notification_sink_override_for_tests(payloads.append):
            with self.captureOnCommitCallbacks(execute=True):
                emit_review_outcome_notification(activity, actor=self.staff)
        return payloads

    def _edit_data(self, activity, **overrides):
        data = {
            "title": activity.title,
            "title_en": activity.title_en,
            "description": activity.description,
            "description_en": activity.description_en,
            "organizer": activity.organizer,
            "co_organizer_users": [self.co_organizer.id],
            "start_datetime": timezone.localtime(
                activity.start_datetime
            ).strftime("%Y-%m-%dT%H:%M"),
            "end_datetime": "",
            "location": activity.location,
            "location_en": activity.location_en,
            "capacity_limit": "",
            "audience_units": [self.group.id],
            "requested_audience_note": activity.requested_audience_note,
            "expected_status": activity.status,
        }
        data.update(overrides)
        return data

    def _post_edit(self, activity, user, **overrides):
        self.client.force_login(user)
        payloads = []
        with notification_sink_override_for_tests(payloads.append):
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.post(
                    reverse("community_activity_edit", args=[activity.id]),
                    self._edit_data(activity, **overrides),
                )
        return response, payloads

    def _assert_common_payload(self, payload, activity, notification_type):
        self.assertEqual(payload.recipient, activity.created_by)
        self.assertEqual(payload.source_module, "community_events")
        self.assertEqual(payload.notification_type, notification_type)
        self.assertEqual(
            payload.source_model_label,
            "community_events.CommunityActivity",
        )
        self.assertEqual(payload.source_object_id, str(activity.id))
        self.assertEqual(payload.actor, self.staff)
        self.assertEqual(
            payload.target_url,
            reverse("community_activity_detail", args=[activity.id]),
        )
        self.assertEqual(dict(payload.metadata), {})
        snapshot = " ".join(
            [payload.title, payload.body, payload.target_url, str(dict(payload.metadata))]
        )
        for private_value in (
            "PRIVATE REVIEW NOTE",
            "PRIVATE AUDIENCE NOTE",
            "PRIVATE LOCATION",
            "DISPLAY ORGANIZER ONLY",
            self.co_organizer.username,
            self.signup_user.username,
            self.group.code,
        ):
            self.assertNotIn(private_value, snapshot)

    def _assert_creator_target_and_hidden_user(self, activity):
        self.client.force_login(activity.created_by)
        self.assertEqual(
            self.client.get(
                reverse("community_activity_detail", args=[activity.id])
            ).status_code,
            200,
        )
        self.client.force_login(self.hidden_user)
        self.assertEqual(
            self.client.get(
                reverse("community_activity_detail", args=[activity.id])
            ).status_code,
            404,
        )

    def test_request_changes_emits_one_private_safe_english_creator_payload(self):
        activity = self._activity()
        CommunityActivitySubmissionBlock.objects.create(
            user=self.creator_en,
            reason="Future submissions are blocked",
            is_active=True,
            created_by=self.staff,
        )
        membership_count = ChurchStructureMembership.objects.count()
        audience_count = CommunityActivityAudienceScope.objects.count()
        signup_count = ActivitySignup.objects.count()

        response, payloads = self._post_review(
            activity,
            "request_changes",
            {"review_note": "PRIVATE REVIEW NOTE"},
            language="zh",
        )

        activity.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(activity.status, CommunityActivity.STATUS_CHANGES_REQUESTED)
        self.assertEqual(activity.review_note, "PRIVATE REVIEW NOTE")
        self.assertEqual(activity.reviewed_by, self.staff)
        self.assertIsNotNone(activity.reviewed_at)
        self.assertEqual(len(payloads), 1)
        payload = payloads[0]
        self._assert_common_payload(
            payload,
            activity,
            "community_activity.review_changes_requested",
        )
        self.assertEqual(payload.title, "Changes requested for your activity")
        self.assertEqual(payload.body, "Community Picnic")
        self.assertTrue(
            payload.dedupe_key.startswith(
                f"community:activity:{activity.id}:review:changes_requested:"
            )
        )
        self.assertNotIn(
            payload.recipient,
            (self.co_organizer, self.audience_user, self.signup_user, self.staff),
        )
        self.assertFalse(
            ChurchStructureMembership.objects.filter(user=self.creator_en).exists()
        )
        self.assertEqual(ChurchStructureMembership.objects.count(), membership_count)
        self.assertEqual(CommunityActivityAudienceScope.objects.count(), audience_count)
        self.assertEqual(ActivitySignup.objects.count(), signup_count)
        self.assertEqual(TeamAssignment.objects.count(), 0)
        self.assertEqual(TeamAssignmentMember.objects.count(), 0)
        self.assertEqual(BibleStudyMeetingRole.objects.count(), 0)
        self.assertEqual(ServiceEvent.objects.count(), 0)
        self._assert_creator_target_and_hidden_user(activity)

    def test_chinese_creator_language_ignores_english_reviewer_session(self):
        activity = self._activity(created_by=self.creator_zh)

        _response, payloads = self._post_review(
            activity,
            "request_changes",
            {"review_note": "PRIVATE REVIEW NOTE"},
            language="en",
        )

        activity.refresh_from_db()
        self.assertEqual(len(payloads), 1)
        payload = payloads[0]
        self.assertEqual(payload.title, "你的活动需要修改")
        self.assertEqual(payload.body, "社区野餐")
        self.assertNotIn("PRIVATE REVIEW NOTE", payload.body)

    def test_invalid_creator_language_falls_back_to_english(self):
        type(self.creator_en.profile).objects.filter(
            pk=self.creator_en.profile.pk
        ).update(preferred_language="invalid")
        activity = self._activity()

        _response, payloads = self._post_review(activity, "publish", language="zh")

        self.assertEqual(len(payloads), 1)
        self.assertEqual(payloads[0].title, "Your activity was published")
        self.assertEqual(payloads[0].body, "Community Picnic")

    def test_publish_from_each_current_review_state_notifies_only_creator(self):
        for status in (
            CommunityActivity.STATUS_PENDING_REVIEW,
            CommunityActivity.STATUS_CHANGES_REQUESTED,
        ):
            with self.subTest(status=status):
                activity = self._activity(status=status)
                _response, payloads = self._post_review(activity, "publish")

                activity.refresh_from_db()
                self.assertEqual(activity.status, CommunityActivity.STATUS_PUBLISHED)
                self.assertEqual(len(payloads), 1)
                payload = payloads[0]
                self._assert_common_payload(
                    payload,
                    activity,
                    "community_activity.review_published",
                )
                self.assertEqual(payload.title, "Your activity was published")
                self.assertEqual(payload.body, "Community Picnic")
                self.assertEqual(payload.recipient, self.creator_en)
                self._assert_creator_target_and_hidden_user(activity)

    def test_cancel_from_each_current_review_state_notifies_only_creator(self):
        for status in (
            CommunityActivity.STATUS_PENDING_REVIEW,
            CommunityActivity.STATUS_CHANGES_REQUESTED,
        ):
            with self.subTest(status=status):
                activity = self._activity(status=status)
                _response, payloads = self._post_review(
                    activity,
                    "cancel",
                    {"review_note": "PRIVATE REVIEW NOTE"},
                )

                activity.refresh_from_db()
                self.assertEqual(activity.status, CommunityActivity.STATUS_CANCELLED)
                self.assertEqual(activity.review_note, "PRIVATE REVIEW NOTE")
                self.assertEqual(len(payloads), 1)
                payload = payloads[0]
                self._assert_common_payload(
                    payload,
                    activity,
                    "community_activity.review_cancelled",
                )
                self.assertEqual(payload.title, "Your activity was not approved")
                self.assertEqual(payload.body, "Community Picnic")
                self.assertEqual(payload.recipient, self.creator_en)
                self._assert_creator_target_and_hidden_user(activity)

    def test_missing_or_inactive_creator_skips_payload_without_blocking_review(self):
        inactive_creator = User.objects.create_user(
            "inactive_activity_creator",
            password="testpass123",
            is_active=False,
        )
        for created_by in (None, inactive_creator):
            with self.subTest(created_by=created_by):
                activity = self._activity(
                    created_by=created_by,
                    with_related=False,
                )
                _response, payloads = self._post_review(activity, "publish")

                activity.refresh_from_db()
                self.assertEqual(activity.status, CommunityActivity.STATUS_PUBLISHED)
                self.assertEqual(activity.reviewed_by, self.staff)
                self.assertIsNotNone(activity.reviewed_at)
                self.assertEqual(payloads, [])

    def test_blank_note_stale_action_and_repeated_terminal_action_emit_nothing(self):
        blank_activity = self._activity()
        _response, payloads = self._post_review(
            blank_activity,
            "request_changes",
            {"review_note": "   "},
        )
        blank_activity.refresh_from_db()
        self.assertEqual(blank_activity.status, CommunityActivity.STATUS_PENDING_REVIEW)
        self.assertIsNone(blank_activity.reviewed_at)
        self.assertEqual(payloads, [])

        activity = self._activity()
        winning_time = timezone.now()
        with patch("community_events.views.timezone.now", return_value=winning_time):
            _response, winning_payloads = self._post_review(activity, "publish")
        self.assertEqual(len(winning_payloads), 1)
        activity.refresh_from_db()
        winning_reviewer = activity.reviewed_by

        _response, stale_payloads = self._post_review(
            activity,
            "request_changes",
            {"review_note": "LOSING PRIVATE NOTE"},
        )
        activity.refresh_from_db()
        self.assertEqual(activity.status, CommunityActivity.STATUS_PUBLISHED)
        self.assertEqual(activity.reviewed_at, winning_time)
        self.assertEqual(activity.reviewed_by, winning_reviewer)
        self.assertEqual(activity.review_note, "")
        self.assertEqual(stale_payloads, [])

        _response, repeated_payloads = self._post_review(activity, "publish")
        self.assertEqual(repeated_payloads, [])

    def test_creator_resubmit_is_nonproducer_and_later_cycle_has_new_dedupe_key(self):
        first_time = timezone.now()
        second_time = first_time + timedelta(seconds=1)
        activity = self._activity()
        with patch("community_events.views.timezone.now", return_value=first_time):
            _response, first_payloads = self._post_review(
                activity,
                "request_changes",
                {"review_note": "First private note"},
            )
        activity.refresh_from_db()
        repeated_payloads = self._emit_direct(activity)
        self.assertEqual(
            first_payloads[0].dedupe_key,
            repeated_payloads[0].dedupe_key,
        )

        _response, resubmit_payloads = self._post_edit(
            activity,
            self.creator_en,
            description="Creator revision",
        )
        activity.refresh_from_db()
        self.assertEqual(activity.status, CommunityActivity.STATUS_PENDING_REVIEW)
        self.assertEqual(activity.reviewed_at, first_time)
        self.assertEqual(resubmit_payloads, [])

        with patch("community_events.views.timezone.now", return_value=second_time):
            _response, second_payloads = self._post_review(
                activity,
                "request_changes",
                {"review_note": "Second private note"},
            )
        self.assertEqual(len(second_payloads), 1)
        self.assertNotEqual(
            first_payloads[0].dedupe_key,
            second_payloads[0].dedupe_key,
        )

    def test_coorganizer_resubmit_and_creator_draft_pending_edits_are_nonproducers(self):
        coorganizer_activity = self._activity(
            status=CommunityActivity.STATUS_CHANGES_REQUESTED,
            review_note="Private source note",
        )
        _response, payloads = self._post_edit(
            coorganizer_activity,
            self.co_organizer,
            description="Co-organizer revision",
        )
        coorganizer_activity.refresh_from_db()
        self.assertEqual(
            coorganizer_activity.status,
            CommunityActivity.STATUS_PENDING_REVIEW,
        )
        self.assertEqual(payloads, [])

        draft = self._activity(
            status=CommunityActivity.STATUS_DRAFT,
            created_by=self.audience_user,
        )
        _response, submit_payloads = self._post_edit(
            draft,
            self.audience_user,
            workflow_action="submit",
        )
        draft.refresh_from_db()
        self.assertEqual(draft.status, CommunityActivity.STATUS_PENDING_REVIEW)
        self.assertEqual(submit_payloads, [])

        _response, edit_payloads = self._post_edit(
            draft,
            self.audience_user,
            description="Ordinary pending edit",
        )
        draft.refresh_from_db()
        self.assertEqual(draft.status, CommunityActivity.STATUS_PENDING_REVIEW)
        self.assertEqual(edit_payloads, [])

    @override_settings(CMS_ENABLED_MODULES=["community_events"])
    def test_disabled_notifications_keeps_review_write_and_skips_sink(self):
        activity = self._activity()

        _response, payloads = self._post_review(activity, "publish")

        activity.refresh_from_db()
        self.assertEqual(activity.status, CommunityActivity.STATUS_PUBLISHED)
        self.assertEqual(activity.reviewed_by, self.staff)
        self.assertIsNotNone(activity.reviewed_at)
        self.assertEqual(payloads, [])

    def test_direct_orm_review_metadata_write_has_no_signal_or_payload(self):
        activity = self._activity()
        payloads = []
        with notification_sink_override_for_tests(payloads.append):
            with self.captureOnCommitCallbacks(execute=True):
                activity.status = CommunityActivity.STATUS_PUBLISHED
                activity.reviewed_by = self.staff
                activity.reviewed_at = timezone.now()
                activity.save()
        self.assertEqual(payloads, [])

    def test_source_rollback_discards_transition_and_scheduled_payload(self):
        activity = self._activity()
        payloads = []
        with notification_sink_override_for_tests(payloads.append):
            with self.captureOnCommitCallbacks(execute=True):
                with self.assertRaises(RuntimeError):
                    with transaction.atomic():
                        _apply_locked_review_transition(
                            activity.id,
                            self.staff,
                            allowed_statuses=(
                                CommunityActivity.STATUS_PENDING_REVIEW,
                            ),
                            target_status=CommunityActivity.STATUS_PUBLISHED,
                        )
                        raise RuntimeError("force source rollback")

        activity.refresh_from_db()
        self.assertEqual(activity.status, CommunityActivity.STATUS_PENDING_REVIEW)
        self.assertIsNone(activity.reviewed_by)
        self.assertIsNone(activity.reviewed_at)
        self.assertEqual(payloads, [])
