"""Focused NOTIFY.1G Worship Team change producer tests."""

from datetime import datetime

from unittest.mock import patch

from django.contrib.auth.models import User
from django.db import transaction
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import ChurchStructureUnit
from core.notification_delivery import notification_sink_override_for_tests
from events.models import ServiceEvent, ServiceEventRequiredTeam
from notifications.models import Notification
from notifications.services import persist_notification

from .models import (
    MinistryTeam,
    MinistryTeamParentLink,
    MinistryTeamRoleAssignment,
    MinistryTeamRoleType,
    TeamAssignment,
    TeamMembership,
)
from .services.worship_change_notifications import (
    WorshipTeamChangeFact,
    emit_worship_rotation_change_notifications,
    emit_worship_team_change_notifications,
)


class WorshipChangeNotificationProducerTests(TestCase):
    def setUp(self):
        self.today = timezone.localdate()
        self.root = ChurchStructureUnit.objects.create(
            code="ROOT-N1G",
            name="全教会",
            name_en="Whole Church",
            unit_type=ChurchStructureUnit.UNIT_ROOT,
        )
        self.pool = self.team(
            "敬拜团队组",
            "Worship Pool",
            is_assignable=False,
            is_worship_rotation_pool=True,
        )
        MinistryTeamParentLink.objects.create(
            child_team=self.pool,
            parent_church_unit=self.root,
            is_primary=True,
        )
        self.old = self.team("旧敬拜队", "Old Worship Team", parent=self.pool)
        self.new = self.team("新敬拜队", "New Worship Team", parent=self.pool)
        self.required = self.team("投影团队", "Projection Team")
        self.additional = self.team("音响团队", "Sound Team")
        self.similar = self.team("敬拜后勤", "Worship Support")
        self.downstream_worship = self.team(
            "敬拜第三队", "Worship Team C3", parent=self.pool
        )
        self.lead_type = MinistryTeamRoleType.objects.create(
            code=MinistryTeamRoleType.CODE_LEAD,
            name="负责人",
            name_en="Lead",
        )
        self.coordinator_type = MinistryTeamRoleType.objects.create(
            code=MinistryTeamRoleType.CODE_COORDINATOR,
            name="协调员",
            name_en="Coordinator",
        )
        self.other_type = MinistryTeamRoleType.objects.create(
            code=MinistryTeamRoleType.CODE_SCHEDULER,
            name="排班员",
            name_en="Scheduler",
        )
        self.actor = self.user("actor", staff=True)
        self.event = self.event_at(14, self.old)

    def team(self, name, name_en, *, parent=None, **overrides):
        values = {"name": name, "name_en": name_en}
        values.update(overrides)
        team = MinistryTeam.objects.create(**values)
        if parent is not None:
            MinistryTeamParentLink.objects.create(
                child_team=team, parent_team=parent, is_primary=True
            )
        return team

    def user(self, username, *, language="en", staff=False):
        user = User.objects.create_user(username=username, is_staff=staff)
        user.profile.preferred_language = language
        user.profile.save(update_fields=["preferred_language"])
        return user

    def role(self, user, team, role_type=None, **overrides):
        values = {
            "team": team,
            "role_type": role_type or self.lead_type,
            "user": user,
            "start_date": self.today,
        }
        values.update(overrides)
        return MinistryTeamRoleAssignment.objects.create(**values)

    def event_at(self, days, team):
        return ServiceEvent.objects.create(
            title="不得显示的主日标题",
            title_en="PRIVATE EVENT TITLE",
            location="PRIVATE LOCATION",
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
            start_datetime=timezone.now() + timezone.timedelta(days=days),
            status=ServiceEvent.STATUS_PUBLISHED,
            rotation_anchor_team=team,
        )

    def fact(self, event=None, old=None, new=None):
        event = event or self.event
        return WorshipTeamChangeFact(
            event_id=event.pk,
            event_start_datetime=event.start_datetime,
            old_team_id=(self.old if old is None else old).pk if old is not False else None,
            new_team_id=(self.new if new is None else new).pk if new is not False else None,
        )

    def deliver_single(self, fact=None, *, logentry_id=41, sink=None):
        payloads = []
        with notification_sink_override_for_tests(sink or payloads.append):
            with self.captureOnCommitCallbacks(execute=True):
                emit_worship_team_change_notifications(
                    fact or self.fact(),
                    logentry_id=logentry_id,
                    actor=self.actor,
                )
        return payloads

    def deliver_batch(self, facts, *, operation_id="12345678-1234-5678-1234-567812345678", sink=None):
        payloads = []
        with notification_sink_override_for_tests(sink or payloads.append):
            with self.captureOnCommitCallbacks(execute=True):
                emit_worship_rotation_change_notifications(
                    facts, operation_id=operation_id, actor=self.actor
                )
        return payloads

    def test_exact_old_new_required_and_current_additional_roles_qualify(self):
        old_lead = self.user("old_lead")
        new_coordinator = self.user("new_coordinator")
        required_lead = self.user("required_lead")
        scheduled = self.user("scheduled")
        prepared = self.user("prepared")
        confirmed = self.user("confirmed")
        self.role(old_lead, self.old)
        self.role(new_coordinator, self.new, self.coordinator_type)
        self.role(required_lead, self.required)
        ServiceEventRequiredTeam.objects.create(
            service_event=self.event, ministry_team=self.required
        )
        for user, status in (
            (scheduled, TeamAssignment.STATUS_SCHEDULED),
            (prepared, TeamAssignment.STATUS_PREPARED),
            (confirmed, TeamAssignment.STATUS_CONFIRMED),
        ):
            team = self.team(f"{user.username}队", f"{user.username} team")
            self.role(user, team)
            TeamAssignment.objects.create(
                service_event=self.event, ministry_team=team, status=status
            )

        payloads = self.deliver_single()

        self.assertEqual(
            {payload.recipient_id if hasattr(payload, "recipient_id") else payload.recipient.pk for payload in payloads},
            {old_lead.pk, new_coordinator.pk, required_lead.pk, scheduled.pk, prepared.pk, confirmed.pk},
        )

    def test_historical_membership_authority_and_non_management_roles_do_not_qualify(self):
        completed = self.user("completed")
        cancelled = self.user("cancelled")
        member_only = self.user("member_only")
        scheduler = self.user("scheduler")
        pool_lead = self.user("pool_lead")
        for user, team, status in (
            (completed, self.required, TeamAssignment.STATUS_COMPLETED),
            (cancelled, self.additional, TeamAssignment.STATUS_CANCELLED),
        ):
            self.role(user, team)
            TeamAssignment.objects.create(
                service_event=self.event, ministry_team=team, status=status
            )
        TeamMembership.objects.create(
            team=self.old, user=member_only, role=TeamMembership.ROLE_LEAD
        )
        self.role(scheduler, self.old, self.other_type)
        self.role(pool_lead, self.pool)

        self.assertEqual(self.deliver_single(), [])

    def test_inactive_future_expired_team_and_user_are_excluded_with_boundary_dates_included(self):
        start_boundary = self.user("start_boundary")
        end_boundary = self.user("end_boundary")
        future = self.user("future")
        expired = self.user("expired")
        inactive_role = self.user("inactive_role")
        inactive_user = self.user("inactive_user")
        inactive_team_user = self.user("inactive_team")
        self.role(start_boundary, self.old, start_date=self.today)
        self.role(end_boundary, self.new, end_date=self.today)
        self.role(future, self.old, start_date=self.today + timezone.timedelta(days=1))
        self.role(expired, self.old, start_date=self.today - timezone.timedelta(days=2), end_date=self.today - timezone.timedelta(days=1))
        self.role(inactive_role, self.old, is_active=False)
        self.role(inactive_user, self.old)
        inactive_user.is_active = False
        inactive_user.save(update_fields=["is_active"])
        inactive_team = self.team("停用团队", "Inactive Team")
        self.role(inactive_team_user, inactive_team)
        MinistryTeam.objects.filter(pk=inactive_team.pk).update(is_active=False)
        ServiceEventRequiredTeam.objects.create(service_event=self.event, ministry_team=inactive_team)

        payloads = self.deliver_single()

        self.assertEqual(
            {payload.recipient.pk for payload in payloads},
            {start_boundary.pk, end_boundary.pk},
        )

    def test_downstream_worship_is_excluded_but_similar_name_is_not(self):
        worship_lead = self.user("worship_downstream")
        similar_lead = self.user("similar_name")
        self.role(worship_lead, self.downstream_worship)
        self.role(similar_lead, self.similar)
        TeamAssignment.objects.bulk_create(
            [
                TeamAssignment(service_event=self.event, ministry_team=team)
                for team in (self.downstream_worship, self.similar)
            ]
        )

        payloads = self.deliver_single()

        self.assertEqual([payload.recipient for payload in payloads], [similar_lead])

    def test_one_user_qualifying_through_every_class_receives_one_exact_single_payload(self):
        recipient = self.user("deduped")
        for team in (self.old, self.new, self.required, self.additional):
            self.role(recipient, team)
        ServiceEventRequiredTeam.objects.create(service_event=self.event, ministry_team=self.required)
        TeamAssignment.objects.create(service_event=self.event, ministry_team=self.additional)

        payloads = self.deliver_single(logentry_id=987)

        self.assertEqual(len(payloads), 1)
        payload = payloads[0]
        self.assertEqual(payload.notification_type, "worship_team.changed")
        self.assertEqual(payload.dedupe_key, "ministry:worship_team_change:log:987")
        self.assertEqual(payload.source_model_label, "events.ServiceEvent")
        self.assertEqual(payload.source_object_id, str(self.event.pk))
        self.assertEqual(payload.target_url, reverse("my_serving"))
        self.assertEqual(dict(payload.metadata), {})
        self.assertEqual(payload.actor, self.actor)
        self.assertEqual(payload.title, "Worship Team changed")
        self.assertIn("Old Worship Team → New Worship Team", payload.body)
        self.assertNotIn("PRIVATE", payload.body)

    def test_recipient_language_controls_copy_and_missing_english_name_falls_back(self):
        english = self.user("english")
        chinese = self.user("chinese", language="zh")
        self.new.name_en = ""
        self.new.save(update_fields=["name_en"])
        self.role(english, self.old)
        self.role(chinese, self.old)

        payloads = {payload.recipient.pk: payload for payload in self.deliver_single()}

        self.assertEqual(payloads[english.pk].title, "Worship Team changed")
        self.assertIn("Old Worship Team → 新敬拜队", payloads[english.pk].body)
        self.assertEqual(payloads[chinese.pk].title, "敬拜团队已调整")
        self.assertIn("旧敬拜队 → 新敬拜队", payloads[chinese.pk].body)

    def test_null_old_and_new_have_localized_fallback(self):
        english = self.user("null_en")
        chinese = self.user("null_zh", language="zh")
        self.role(english, self.new)
        self.role(chinese, self.new)
        payloads = {
            payload.recipient.pk: payload
            for payload in self.deliver_single(self.fact(old=False))
        }
        self.assertIn("Not selected → New Worship Team", payloads[english.pk].body)
        self.assertIn("未选择 → 新敬拜队", payloads[chinese.pk].body)

    def test_batch_is_one_payload_per_user_with_recipient_private_sorted_subsets(self):
        subset_user = self.user("subset")
        all_user = self.user("all_rows")
        other = self.team("其他团队", "Other Team")
        events = [self.event_at(days, self.old if index != 1 else other) for index, days in enumerate((28, 21, 35))]
        facts = [
            self.fact(event=event, old=(self.old if index != 1 else other))
            for index, event in enumerate(events)
        ]
        self.role(subset_user, self.old)
        self.role(all_user, self.required)
        for event in events:
            ServiceEventRequiredTeam.objects.create(service_event=event, ministry_team=self.required)

        payloads = {payload.recipient.pk: payload for payload in self.deliver_batch(reversed(facts))}

        self.assertEqual(set(payloads), {subset_user.pk, all_user.pk})
        subset = payloads[subset_user.pk]
        self.assertEqual(subset.metadata["recipient_relevant_event_count"], 2)
        self.assertNotIn("Other Team", subset.body)
        self.assertEqual(payloads[all_user.pk].metadata["recipient_relevant_event_count"], 3)
        self.assertEqual(subset.dedupe_key, payloads[all_user.pk].dedupe_key)
        self.assertEqual(subset.source_model_label, "")
        self.assertEqual(subset.source_object_id, "")
        self.assertEqual(
            set(subset.metadata), {"operation_id", "recipient_relevant_event_count"}
        )
        body_lines = subset.body.splitlines()
        rendered_dates = [
            datetime.strptime(
                line.split(" Old Worship Team", 1)[0],
                "%b %d, %Y",
            )
            for line in body_lines[1:3]
        ]
        self.assertLess(rendered_dates[0], rendered_dates[1])

    def test_batch_more_than_three_is_bounded_localized_and_snapshot_private(self):
        recipient = self.user("batch_zh", language="zh")
        self.role(recipient, self.required)
        facts = []
        for days in (49, 21, 42, 28, 35):
            event = self.event_at(days, self.old)
            ServiceEventRequiredTeam.objects.create(service_event=event, ministry_team=self.required)
            facts.append(self.fact(event=event))

        payload = self.deliver_batch(facts)[0]

        self.assertEqual(payload.title, "敬拜轮值已更新")
        self.assertIn("与您团队相关的 5 个主日已更新：", payload.body)
        self.assertIn("另有 2 个主日", payload.body)
        self.assertEqual(len(payload.body.splitlines()), 5)
        self.assertLess(len(payload.body), 1200)
        self.assertNotIn("PRIVATE", payload.body)
        self.assertNotIn(payload.metadata["operation_id"], payload.body)

    def test_empty_batch_and_rolled_back_registration_deliver_nothing(self):
        recipient = self.user("rollback")
        self.role(recipient, self.old)
        payloads = []
        with notification_sink_override_for_tests(payloads.append):
            with self.captureOnCommitCallbacks(execute=True) as callbacks:
                emit_worship_rotation_change_notifications([], operation_id="empty")
                try:
                    with transaction.atomic():
                        emit_worship_rotation_change_notifications(
                            [self.fact()], operation_id="rolled-back"
                        )
                        raise RuntimeError("force rollback")
                except RuntimeError:
                    pass
        self.assertEqual(payloads, [])
        self.assertEqual(callbacks, [])

    def test_persistence_is_idempotent_for_single_and_batch_dedupe(self):
        recipient = self.user("idempotent")
        self.role(recipient, self.old)
        for _ in range(2):
            self.deliver_single(logentry_id=77, sink=persist_notification)
            self.deliver_batch([self.fact()], operation_id="same-op", sink=persist_notification)
        self.assertEqual(Notification.objects.filter(recipient=recipient).count(), 2)

    @override_settings(CMS_ENABLED_MODULES=[])
    def test_disabled_notifications_register_no_callback_and_change_no_domain_rows(self):
        recipient = self.user("disabled")
        self.role(recipient, self.old)
        counts = {
            model: model.objects.count()
            for model in (ServiceEventRequiredTeam, TeamAssignment, TeamMembership, MinistryTeamRoleAssignment)
        }
        payloads = []
        with notification_sink_override_for_tests(payloads.append):
            with self.captureOnCommitCallbacks(execute=True) as callbacks:
                emit_worship_team_change_notifications(self.fact(), logentry_id=1, actor=self.actor)
        self.assertEqual(payloads, [])
        self.assertEqual(callbacks, [])
        self.assertEqual(Notification.objects.count(), 0)
        self.assertEqual(
            counts,
            {model: model.objects.count() for model in counts},
        )

    def test_emit_call_count_equals_unique_recipients(self):
        one = self.user("call_one")
        two = self.user("call_two")
        self.role(one, self.old)
        self.role(one, self.new)
        self.role(two, self.new)
        with patch(
            "ministry.services.worship_change_notifications.emit_notification",
            return_value=True,
        ) as emit:
            count = emit_worship_team_change_notifications(
                self.fact(), logentry_id=5, actor=self.actor
            )
        self.assertEqual(count, 2)
        self.assertEqual(emit.call_count, 2)

        with patch(
            "ministry.services.worship_change_notifications.emit_notification",
            return_value=True,
        ) as emit:
            count = emit_worship_rotation_change_notifications(
                [self.fact()], operation_id="call-count", actor=self.actor
            )
        self.assertEqual(count, 2)
        self.assertEqual(emit.call_count, 2)
