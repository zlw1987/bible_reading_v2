"""Focused MO-S.6D-1D-B Worship authorization and selector tests."""

from unittest.mock import patch

from django.contrib import admin
from django.contrib.admin.models import LogEntry
from django.contrib.auth.models import User
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import ChurchStructureMembership, ChurchStructureUnit
from accounts.permissions import (
    CAP_MANAGE_MINISTRY_TEAMS,
    CAP_MANAGE_SERVICE_EVENTS,
    CAP_MANAGE_TEAM_ASSIGNMENTS,
)
from core.notification_delivery import notification_sink_override_for_tests
from events.scheduling_revision import (
    RevisionClaimState,
    SchedulingRevisionBusyError,
    SchedulingRevisionResult,
)
from ministry.models import (
    MinistryTeam,
    MinistryTeamParentLink,
    MinistryTeamRoleAssignment,
    MinistryTeamRoleType,
    TeamAssignment,
    TeamAssignmentMember,
    TeamMembership,
)
from ministry.permissions import can_change_worship_team
from notifications.models import Notification

from .forms import RecurringServiceEventForm, ServiceEventForm
from .models import (
    ServiceEvent,
    ServiceEventAudienceScope,
    ServiceEventPlannerAssignment,
    ServiceEventRequiredTeam,
)
from .views import get_visible_service_events


class WorshipTeamPlanningTestBase(TestCase):
    def setUp(self):
        self.root = self.unit("ROOT", "Whole Church", ChurchStructureUnit.UNIT_ROOT)
        self.cm = self.unit(
            "CM",
            "Chinese Ministry",
            ChurchStructureUnit.UNIT_MINISTRY_CONTEXT,
            self.root,
        )
        self.em = self.unit(
            "EM",
            "English Ministry",
            ChurchStructureUnit.UNIT_MINISTRY_CONTEXT,
            self.root,
        )
        self.cm_pool = self.pool("Chinese Worship Pool", self.cm)
        self.em_pool = self.pool("English Worship Pool", self.em)
        self.c1 = self.team("Chinese Worship C1", self.cm_pool)
        self.c2 = self.team("Chinese Worship C2", self.cm_pool)
        self.e1 = self.team("English Worship E1", self.em_pool)
        self.av = MinistryTeam.objects.create(
            name="Projection", name_en="Projection"
        )
        self.lead_type = MinistryTeamRoleType.objects.create(
            code=MinistryTeamRoleType.CODE_LEAD,
            name="Lead",
            name_en="Lead",
        )
        self.coordinator_type = MinistryTeamRoleType.objects.create(
            code=MinistryTeamRoleType.CODE_COORDINATOR,
            name="Coordinator",
            name_en="Coordinator",
        )
        self.staff = User.objects.create_user(
            username="worship_staff", password="pw", is_staff=True
        )
        self.planner = User.objects.create_user(
            username="worship_planner", password="pw"
        )
        self.pool_lead = User.objects.create_user(
            username="pool_lead", password="pw"
        )
        self.pool_coordinator = User.objects.create_user(
            username="pool_coordinator", password="pw"
        )
        self.ordinary = User.objects.create_user(
            username="ordinary_viewer", password="pw"
        )
        self.event = ServiceEvent.objects.create(
            title="主日崇拜",
            title_en="Sunday Worship",
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
            start_datetime=timezone.now() + timezone.timedelta(days=7),
            status=ServiceEvent.STATUS_PUBLISHED,
        )
        ServiceEventAudienceScope.objects.create(
            service_event=self.event, unit=self.cm
        )
        session = self.client.session
        session["language"] = "en"
        session.save()

    def unit(self, code, name, unit_type, parent=None):
        return ChurchStructureUnit.objects.create(
            code=code,
            name=name,
            name_en=name,
            unit_type=unit_type,
            parent=parent,
        )

    def pool(self, name, anchor):
        pool = MinistryTeam.objects.create(
            name=name,
            name_en=name,
            is_assignable=False,
            is_worship_rotation_pool=True,
        )
        MinistryTeamParentLink.objects.create(
            child_team=pool,
            parent_church_unit=anchor,
            is_primary=True,
        )
        return pool

    def team(self, name, parent):
        team = MinistryTeam.objects.create(name=name, name_en=name)
        MinistryTeamParentLink.objects.create(
            child_team=team,
            parent_team=parent,
            is_primary=True,
        )
        return team

    def role(self, user, team, role_type=None, **overrides):
        values = {
            "team": team,
            "role_type": role_type or self.lead_type,
            "user": user,
            "start_date": timezone.localdate(),
        }
        values.update(overrides)
        return MinistryTeamRoleAssignment.objects.create(**values)

    def planner_assignment(self, user=None, **overrides):
        values = {
            "service_event": self.event,
            "user": user or self.planner,
        }
        values.update(overrides)
        return ServiceEventPlannerAssignment.objects.create(**values)

    def selector_post_data(self, team=None):
        response = self.client.get(
            reverse("change_worship_team", args=[self.event.id])
        )
        form = response.context["form"]
        return {
            "worship_team": "" if team is None else str(team.id),
            "expected_updated_at": form.initial["expected_updated_at"],
            "expected_anchor_team": str(
                form.initial.get("expected_anchor_team") or ""
            ),
        }

    def stored_conflict(self, team, status=TeamAssignment.STATUS_SCHEDULED):
        assignment = TeamAssignment(
            service_event=self.event,
            ministry_team=team,
            status=status,
        )
        TeamAssignment.objects.bulk_create([assignment])
        return assignment


class WorshipTeamAuthorizationTests(WorshipTeamPlanningTestBase):
    def test_full_manager_and_exact_current_planner_are_allowed(self):
        self.planner_assignment()
        self.assertTrue(can_change_worship_team(self.staff, self.event))
        self.assertTrue(can_change_worship_team(self.planner, self.event))

    def test_ended_and_inactive_planners_are_denied(self):
        self.planner_assignment(is_active=False)
        self.assertFalse(can_change_worship_team(self.planner, self.event))
        inactive = User.objects.create_user(
            username="inactive_planner", is_active=False
        )
        self.planner_assignment(user=inactive, is_active=False)
        self.assertFalse(can_change_worship_team(inactive, self.event))

    def test_applicable_pool_lead_and_coordinator_are_allowed(self):
        self.role(self.pool_lead, self.cm_pool)
        self.role(
            self.pool_coordinator,
            self.cm_pool,
            role_type=self.coordinator_type,
        )
        self.assertTrue(can_change_worship_team(self.pool_lead, self.event))
        self.assertTrue(
            can_change_worship_team(self.pool_coordinator, self.event)
        )

    def test_future_expired_inactive_and_inapplicable_pool_roles_are_denied(self):
        today = timezone.localdate()
        future = User.objects.create_user(username="future_role")
        expired = User.objects.create_user(username="expired_role")
        inactive_role_user = User.objects.create_user(username="inactive_role")
        inapplicable = User.objects.create_user(username="inapplicable_role")
        self.role(future, self.cm_pool, start_date=today + timezone.timedelta(days=1))
        self.role(
            expired,
            self.cm_pool,
            start_date=today - timezone.timedelta(days=10),
            end_date=today - timezone.timedelta(days=1),
        )
        self.role(inactive_role_user, self.cm_pool, is_active=False)
        self.role(inapplicable, self.em_pool)
        for user in (future, expired, inactive_role_user, inapplicable):
            self.assertFalse(can_change_worship_team(user, self.event))

    def test_child_team_lead_and_membership_lead_flags_are_denied(self):
        child_lead = User.objects.create_user(username="child_lead")
        membership_lead = User.objects.create_user(username="membership_lead")
        self.role(child_lead, self.c1)
        TeamMembership.objects.create(
            team=self.cm_pool,
            user=membership_lead,
            role=TeamMembership.ROLE_LEAD,
            can_lead=True,
        )
        self.assertFalse(can_change_worship_team(child_lead, self.event))
        self.assertFalse(can_change_worship_team(membership_lead, self.event))

    def test_audience_member_and_ordinary_viewer_are_denied(self):
        ChurchStructureMembership.objects.create(
            user=self.ordinary,
            unit=self.cm,
            status=ChurchStructureMembership.STATUS_ACTIVE,
            is_primary=True,
            start_date=timezone.localdate(),
        )
        self.assertTrue(self.event.can_be_seen_by(self.ordinary))
        self.assertFalse(can_change_worship_team(self.ordinary, self.event))

    def test_unrelated_global_capabilities_alone_are_denied(self):
        for allowed_capability in (
            CAP_MANAGE_TEAM_ASSIGNMENTS,
            CAP_MANAGE_MINISTRY_TEAMS,
        ):
            with self.subTest(allowed_capability=allowed_capability), patch(
                "ministry.permissions.has_capability",
                side_effect=lambda user, capability: capability
                == allowed_capability,
            ):
                self.assertFalse(can_change_worship_team(self.ordinary, self.event))
        with patch(
            "ministry.permissions.has_capability",
            side_effect=lambda user, capability: capability
            == CAP_MANAGE_SERVICE_EVENTS,
        ):
            self.assertTrue(can_change_worship_team(self.ordinary, self.event))

    def test_combined_event_lead_sees_same_candidate_union(self):
        ServiceEventAudienceScope.objects.filter(service_event=self.event).delete()
        ServiceEventAudienceScope.objects.create(
            service_event=self.event, unit=self.root
        )
        self.role(self.pool_lead, self.cm_pool)
        english_lead = User.objects.create_user(username="english_pool_lead")
        self.role(english_lead, self.em_pool)
        expected = {self.c1.id, self.c2.id, self.e1.id}
        for user in (self.pool_lead, english_lead):
            self.client.force_login(user)
            response = self.client.get(
                reverse("change_worship_team", args=[self.event.id])
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(
                set(
                    response.context["form"]
                    .fields["worship_team"]
                    .queryset.values_list("id", flat=True)
                ),
                expected,
            )


class WorshipTeamSelectorTests(WorshipTeamPlanningTestBase):
    def setUp(self):
        super().setUp()
        self.planner_assignment()
        self.client.force_login(self.planner)

    def test_get_is_read_only_and_candidates_are_exact_domain_union(self):
        models = (
            ServiceEvent,
            ServiceEventAudienceScope,
            ServiceEventRequiredTeam,
            TeamAssignment,
            TeamAssignmentMember,
            ServiceEventPlannerAssignment,
            Notification,
            LogEntry,
        )
        before = {model: model.objects.count() for model in models}
        event_before = ServiceEvent.objects.values().get(pk=self.event.pk)
        response = self.client.get(
            reverse("change_worship_team", args=[self.event.id])
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            set(
                response.context["form"]
                .fields["worship_team"]
                .queryset.values_list("id", flat=True)
            ),
            {self.c1.id, self.c2.id},
        )
        self.assertEqual(before, {model: model.objects.count() for model in models})
        self.assertEqual(
            event_before, ServiceEvent.objects.values().get(pk=self.event.pk)
        )

    def test_planner_outside_audience_gets_narrow_planning_not_event_access(self):
        self.assertFalse(self.event.can_be_seen_by(self.planner))
        self.assertNotIn(
            self.event.id,
            get_visible_service_events(self.planner).values_list("id", flat=True),
        )
        planning = self.client.get(reverse("worship_planning"))
        detail = self.client.get(
            reverse("service_event_detail", args=[self.event.id])
        )
        edit = self.client.get(reverse("edit_service_event", args=[self.event.id]))
        self.assertContains(planning, "Sunday Worship")
        self.assertEqual(detail.status_code, 302)
        self.assertEqual(edit.status_code, 302)
        self.assertNotContains(planning, "Edit Service Event")

    def test_valid_initial_selection_changes_only_anchor_and_audits(self):
        before = ServiceEvent.objects.values(
            "title",
            "event_type",
            "start_datetime",
            "status",
            "rotation_anchor_team_id",
        ).get(pk=self.event.pk)
        counts = {
            model: model.objects.count()
            for model in (
                ServiceEventAudienceScope,
                ServiceEventRequiredTeam,
                TeamAssignment,
                TeamAssignmentMember,
                ServiceEventPlannerAssignment,
                Notification,
            )
        }
        response = self.client.post(
            reverse("change_worship_team", args=[self.event.id]),
            self.selector_post_data(self.c1),
        )
        self.assertEqual(response.status_code, 302)
        self.event.refresh_from_db()
        self.assertEqual(self.event.rotation_anchor_team, self.c1)
        self.assertEqual(self.event.scheduling_revision, 1)
        after = ServiceEvent.objects.values(
            "title",
            "event_type",
            "start_datetime",
            "status",
            "rotation_anchor_team_id",
        ).get(pk=self.event.pk)
        self.assertEqual(
            {key: value for key, value in before.items() if key != "rotation_anchor_team_id"},
            {key: value for key, value in after.items() if key != "rotation_anchor_team_id"},
        )
        self.assertEqual(
            counts, {model: model.objects.count() for model in counts}
        )
        entry = LogEntry.objects.get(object_id=str(self.event.id))
        self.assertEqual(entry.user_id, self.planner.id)
        self.assertIn(f"new_team_id={self.c1.id!r}", entry.change_message)

    def test_actual_change_emits_after_saved_log_with_exact_payload_identity(self):
        self.event.rotation_anchor_team = self.c1
        self.event.save(update_fields=["rotation_anchor_team", "updated_at"])
        recipient = User.objects.create_user(username="old_team_lead")
        self.role(recipient, self.c1)
        payloads = []
        data = self.selector_post_data(self.c2)

        with notification_sink_override_for_tests(payloads.append):
            with self.captureOnCommitCallbacks(execute=True) as callbacks:
                response = self.client.post(
                    reverse("change_worship_team", args=[self.event.pk]), data
                )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(callbacks), 1)
        self.assertEqual(len(payloads), 1)
        entry = LogEntry.objects.get(object_id=str(self.event.pk))
        payload = payloads[0]
        self.assertEqual(payload.recipient, recipient)
        self.assertEqual(
            payload.dedupe_key,
            f"ministry:worship_team_change:log:{entry.pk}",
        )
        self.assertEqual(payload.target_url, reverse("my_serving"))

    @override_settings(CMS_ENABLED_MODULES=[])
    def test_actual_change_still_succeeds_when_notifications_are_disabled(self):
        self.event.rotation_anchor_team = self.c1
        self.event.save(update_fields=["rotation_anchor_team", "updated_at"])
        recipient = User.objects.create_user(username="disabled_old_lead")
        self.role(recipient, self.c1)
        payloads = []

        with notification_sink_override_for_tests(payloads.append):
            with self.captureOnCommitCallbacks(execute=True) as callbacks:
                response = self.client.post(
                    reverse("change_worship_team", args=[self.event.pk]),
                    self.selector_post_data(self.c2),
                )

        self.event.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.event.rotation_anchor_team, self.c2)
        self.assertEqual(payloads, [])
        self.assertEqual(callbacks, [])

    def test_team_to_team_and_clear_work_without_assignment(self):
        self.event.rotation_anchor_team = self.c1
        self.event.save(update_fields=["rotation_anchor_team", "updated_at"])
        self.client.post(
            reverse("change_worship_team", args=[self.event.id]),
            self.selector_post_data(self.c2),
        )
        self.event.refresh_from_db()
        self.assertEqual(self.event.rotation_anchor_team, self.c2)
        self.client.post(
            reverse("change_worship_team", args=[self.event.id]),
            self.selector_post_data(None),
        )
        self.event.refresh_from_db()
        self.assertIsNone(self.event.rotation_anchor_team)
        self.assertEqual(LogEntry.objects.count(), 2)
        self.assertEqual(self.event.scheduling_revision, 3)

    def test_no_op_selection_does_not_advance_revision_or_audit(self):
        self.event.rotation_anchor_team = self.c1
        self.event.save(update_fields=["rotation_anchor_team", "updated_at"])
        self.event.refresh_from_db()
        before_revision = self.event.scheduling_revision

        response = self.client.post(
            reverse("change_worship_team", args=[self.event.id]),
            self.selector_post_data(self.c1),
        )

        self.assertEqual(response.status_code, 302)
        self.event.refresh_from_db()
        self.assertEqual(self.event.scheduling_revision, before_revision)
        self.assertEqual(LogEntry.objects.count(), 0)

    @patch("events.views.advance_scheduling_revisions")
    def test_busy_revision_barrier_renders_retry_without_false_success(
        self, advance_revisions
    ):
        advance_revisions.side_effect = SchedulingRevisionBusyError(
            "SQLite scheduling write is busy; retry from current state."
        )

        response = self.client.post(
            reverse("change_worship_team", args=[self.event.id]),
            self.selector_post_data(self.c1),
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Scheduling changed or is busy.")
        self.event.refresh_from_db()
        self.assertIsNone(self.event.rotation_anchor_team)
        self.assertEqual(self.event.scheduling_revision, 0)
        self.assertEqual(LogEntry.objects.count(), 0)

    @patch("events.views.advance_scheduling_revisions")
    def test_post_barrier_stale_redirects_after_rollback_without_template_error(
        self, advance_revisions
    ):
        advance_revisions.return_value = (
            SchedulingRevisionResult(
                event_id=self.event.pk,
                state=RevisionClaimState.CLAIMED,
                revision=2,
            ),
        )

        response = self.client.post(
            reverse("change_worship_team", args=[self.event.id]),
            self.selector_post_data(self.c1),
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "changed after you opened the form")
        self.event.refresh_from_db()
        self.assertIsNone(self.event.rotation_anchor_team)
        self.assertEqual(self.event.scheduling_revision, 0)
        self.assertEqual(LogEntry.objects.count(), 0)

    def test_forged_candidate_is_rejected_without_audit(self):
        data = self.selector_post_data(self.c1)
        data["worship_team"] = str(self.e1.id)
        response = self.client.post(
            reverse("change_worship_team", args=[self.event.id]), data
        )
        self.assertEqual(response.status_code, 200)
        self.event.refresh_from_db()
        self.assertIsNone(self.event.rotation_anchor_team)
        self.assertEqual(self.event.scheduling_revision, 0)
        self.assertEqual(LogEntry.objects.count(), 0)

    def test_stale_timestamp_and_stale_old_anchor_are_rejected(self):
        timestamp_data = self.selector_post_data(self.c1)
        self.event.title = "Updated elsewhere"
        self.event.save(update_fields=["title", "updated_at"])
        response = self.client.post(
            reverse("change_worship_team", args=[self.event.id]), timestamp_data
        )
        self.assertContains(response, "changed after you opened the form")
        anchor_data = self.selector_post_data(self.c1)
        anchor_data["expected_anchor_team"] = str(self.c2.id)
        response = self.client.post(
            reverse("change_worship_team", args=[self.event.id]), anchor_data
        )
        self.assertContains(response, "changed after you opened the form")
        self.event.refresh_from_db()
        self.assertIsNone(self.event.rotation_anchor_team)
        self.assertEqual(LogEntry.objects.count(), 0)

    def test_candidate_and_authority_are_revalidated_after_get(self):
        candidate_data = self.selector_post_data(self.c2)
        self.c2.is_active = False
        self.c2.save(update_fields=["is_active", "updated_at"])
        response = self.client.post(
            reverse("change_worship_team", args=[self.event.id]), candidate_data
        )
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(ServiceEvent.objects.get(pk=self.event.pk).rotation_anchor_team)

        self.client.logout()
        self.role(self.pool_lead, self.cm_pool)
        self.client.force_login(self.pool_lead)
        authority_data = self.selector_post_data(self.c1)
        MinistryTeamRoleAssignment.objects.filter(user=self.pool_lead).update(
            is_active=False
        )
        response = self.client.post(
            reverse("change_worship_team", args=[self.event.id]), authority_data
        )
        self.assertEqual(response.status_code, 302)
        self.assertIsNone(ServiceEvent.objects.get(pk=self.event.pk).rotation_anchor_team)

    def test_same_team_post_is_noop_without_audit(self):
        self.event.rotation_anchor_team = self.c1
        self.event.save(update_fields=["rotation_anchor_team", "updated_at"])
        before_updated = self.event.updated_at
        response = self.client.post(
            reverse("change_worship_team", args=[self.event.id]),
            self.selector_post_data(self.c1),
        )
        self.assertEqual(response.status_code, 302)
        self.event.refresh_from_db()
        self.assertEqual(self.event.updated_at, before_updated)
        self.assertEqual(LogEntry.objects.count(), 0)

    def test_any_current_worship_assignment_blocks_change_without_mutation(self):
        self.event.rotation_anchor_team = self.c1
        self.event.save(update_fields=["rotation_anchor_team", "updated_at"])
        assignment = self.stored_conflict(self.c1)
        before = TeamAssignment.objects.values().get(pk=assignment.pk)
        response = self.client.post(
            reverse("change_worship_team", args=[self.event.id]),
            self.selector_post_data(self.c2),
        )
        self.assertContains(response, "Resolve or cancel the existing Worship assignment")
        self.assertNotContains(response, 'name="worship_team"')
        self.assertNotContains(response, "Save Worship Team")
        self.event.refresh_from_db()
        self.assertEqual(self.event.rotation_anchor_team, self.c1)
        self.assertEqual(before, TeamAssignment.objects.values().get(pk=assignment.pk))
        self.assertEqual(LogEntry.objects.count(), 0)

    def test_blocked_selector_hides_edit_controls_in_both_languages(self):
        self.event.rotation_anchor_team = self.c1
        self.event.save(update_fields=["rotation_anchor_team", "updated_at"])
        self.stored_conflict(self.c1)

        for language, instruction in (
            ("en", "Existing schedule must be resolved first"),
            ("zh", "需要先处理现有排班"),
        ):
            with self.subTest(language=language):
                session = self.client.session
                session["language"] = language
                session.save()
                response = self.client.get(
                    reverse("change_worship_team", args=[self.event.id])
                )
                self.assertContains(response, instruction)
                self.assertNotContains(response, 'name="worship_team"')
                self.assertNotContains(response, "Save Worship Team")
                self.assertNotContains(response, "保存敬拜团队")

    def test_clear_does_not_cancel_or_remove_existing_assignment(self):
        self.event.rotation_anchor_team = self.c1
        self.event.save(update_fields=["rotation_anchor_team", "updated_at"])
        assignment = self.stored_conflict(self.c1)
        response = self.client.post(
            reverse("change_worship_team", args=[self.event.id]),
            self.selector_post_data(None),
        )
        self.assertEqual(response.status_code, 200)
        assignment.refresh_from_db()
        self.assertEqual(assignment.status, TeamAssignment.STATUS_SCHEDULED)
        self.assertEqual(assignment.assignment_members.count(), 0)
        self.assertEqual(
            ServiceEvent.objects.get(pk=self.event.pk).rotation_anchor_team,
            self.c1,
        )

    def test_all_current_worship_conflict_shapes_block_change(self):
        scenarios = {
            "selected team": [self.c1],
            "other eligible team": [self.c2],
            "inapplicable pool": [self.e1],
            "duplicate selected team": [self.c1, self.c1],
            "multiple worship teams": [self.c1, self.c2],
        }
        for label, teams in scenarios.items():
            with self.subTest(label=label):
                TeamAssignment.objects.all().delete()
                LogEntry.objects.all().delete()
                self.event.rotation_anchor_team = self.c1
                self.event.save(
                    update_fields=["rotation_anchor_team", "updated_at"]
                )
                assignments = [
                    TeamAssignment(
                        service_event=self.event,
                        ministry_team=team,
                        status=TeamAssignment.STATUS_SCHEDULED,
                    )
                    for team in teams
                ]
                TeamAssignment.objects.bulk_create(assignments)
                before = list(
                    TeamAssignment.objects.order_by("id").values(
                        "id",
                        "service_event_id",
                        "ministry_team_id",
                        "status",
                    )
                )
                response = self.client.post(
                    reverse("change_worship_team", args=[self.event.id]),
                    self.selector_post_data(self.c2),
                )
                self.assertEqual(response.status_code, 200)
                self.event.refresh_from_db()
                self.assertEqual(self.event.rotation_anchor_team, self.c1)
                self.assertEqual(
                    before,
                    list(
                        TeamAssignment.objects.order_by("id").values(
                            "id",
                            "service_event_id",
                            "ministry_team_id",
                            "status",
                        )
                    ),
                )
                self.assertEqual(LogEntry.objects.count(), 0)

    def test_invalid_stored_selection_can_be_repaired_or_cleared(self):
        for proposed_team in (self.c1, None):
            with self.subTest(proposed_team=proposed_team):
                self.event.rotation_anchor_team = self.av
                self.event.save(
                    update_fields=["rotation_anchor_team", "updated_at"]
                )
                response = self.client.post(
                    reverse("change_worship_team", args=[self.event.id]),
                    self.selector_post_data(proposed_team),
                )
                self.assertEqual(response.status_code, 302)
                self.event.refresh_from_db()
                self.assertEqual(self.event.rotation_anchor_team, proposed_team)

    def test_audience_change_between_get_and_post_revalidates_candidates(self):
        data = self.selector_post_data(self.c1)
        ServiceEventAudienceScope.objects.filter(service_event=self.event).delete()
        ServiceEventAudienceScope.objects.create(
            service_event=self.event, unit=self.em
        )
        response = self.client.post(
            reverse("change_worship_team", args=[self.event.id]), data
        )
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(
            ServiceEvent.objects.get(pk=self.event.pk).rotation_anchor_team
        )
        self.assertEqual(LogEntry.objects.count(), 0)

    def test_audit_failure_rolls_back_anchor_change(self):
        data = self.selector_post_data(self.c1)
        initial_revision = self.event.scheduling_revision
        payloads = []
        with notification_sink_override_for_tests(payloads.append):
            with self.captureOnCommitCallbacks(execute=True) as callbacks:
                with patch(
                    "events.views.LogEntry.objects.log_action",
                    side_effect=RuntimeError("audit unavailable"),
                ), self.assertRaises(RuntimeError):
                    self.client.post(
                        reverse("change_worship_team", args=[self.event.id]), data
                    )
        self.event.refresh_from_db()
        self.assertIsNone(self.event.rotation_anchor_team)
        self.assertEqual(self.event.scheduling_revision, initial_revision)
        self.assertEqual(LogEntry.objects.count(), 0)
        self.assertEqual(payloads, [])
        self.assertEqual(callbacks, [])

    def test_unauthorized_direct_url_and_cancelled_event_are_denied(self):
        self.client.force_login(self.ordinary)
        response = self.client.get(
            reverse("change_worship_team", args=[self.event.id])
        )
        self.assertEqual(response.status_code, 302)
        self.client.force_login(self.staff)
        self.event.status = ServiceEvent.STATUS_CANCELLED
        self.event.save(update_fields=["status", "updated_at"])
        response = self.client.get(
            reverse("change_worship_team", args=[self.event.id])
        )
        self.assertEqual(response.status_code, 302)


class WorshipLegacyAnchorClosureTests(WorshipTeamPlanningTestBase):
    def test_normal_and_recurring_forms_do_not_expose_anchor(self):
        self.assertNotIn("rotation_anchor_team", ServiceEventForm().fields)
        self.assertNotIn(
            "rotation_anchor_team", RecurringServiceEventForm().fields
        )

    def test_unrelated_edit_preserves_stored_anchor_and_ignores_forged_post(self):
        self.event.rotation_anchor_team = self.c1
        self.event.save(update_fields=["rotation_anchor_team", "updated_at"])
        self.client.force_login(self.staff)
        response = self.client.post(
            reverse("edit_service_event", args=[self.event.id]),
            {
                "title": "Updated title",
                "title_en": "Updated title",
                "description": "",
                "description_en": "",
                "event_type": self.event.event_type,
                "start_datetime": timezone.localtime(
                    self.event.start_datetime
                ).strftime("%Y-%m-%dT%H:%M"),
                "end_datetime": "",
                "location": "",
                "meeting_link": "",
                "required_teams": [],
                "status": self.event.status,
                "audience_units": [self.cm.id],
                "rotation_anchor_team": self.c2.id,
            },
        )
        self.assertEqual(response.status_code, 302)
        self.event.refresh_from_db()
        self.assertEqual(self.event.rotation_anchor_team, self.c1)

    def test_service_event_admin_has_readonly_worship_display_no_anchor_form(self):
        model_admin = admin.site._registry[ServiceEvent]
        request = RequestFactory().get("/admin/events/serviceevent/")
        request.user = self.staff
        form_class = model_admin.get_form(request, self.event)
        self.assertNotIn("rotation_anchor_team", form_class.base_fields)
        self.assertIn("worship_team", model_admin.readonly_fields)
        self.assertIn("rotation_anchor_team", model_admin.exclude)

    def test_contextual_discoverability_and_bilingual_copy(self):
        self.planner_assignment()
        self.client.force_login(self.planner)
        event_list = self.client.get(reverse("service_event_list"))
        planning = self.client.get(reverse("worship_planning"))
        selector = self.client.get(
            reverse("change_worship_team", args=[self.event.id])
        )
        self.assertContains(event_list, "Worship Planning")
        self.assertContains(planning, "Current Worship Team")
        self.assertContains(selector, "Select Worship Team")
        self.assertNotContains(planning, "Rotation Anchor")
        self.assertNotContains(selector, "rotation anchor")
        self.assertNotContains(selector, "pool")

        session = self.client.session
        session["language"] = "zh"
        session.save()
        planning = self.client.get(reverse("worship_planning"))
        selector = self.client.get(
            reverse("change_worship_team", args=[self.event.id])
        )
        self.assertContains(planning, "敬拜安排")
        self.assertContains(planning, "尚未选择敬拜团队")
        self.assertContains(selector, "选择敬拜团队")
        self.assertNotContains(selector, "配搭参考团队")

    def test_child_team_lead_has_no_contextual_entry_or_direct_access(self):
        child_lead = User.objects.create_user(
            username="denied_child_lead", password="pw"
        )
        MinistryTeamRoleAssignment.objects.create(
            team=self.c1,
            role_type=self.lead_type,
            user=child_lead,
            start_date=timezone.localdate(),
        )
        self.client.force_login(child_lead)
        event_list = self.client.get(reverse("service_event_list"))
        direct = self.client.get(
            reverse("change_worship_team", args=[self.event.id])
        )
        self.assertNotContains(event_list, "Worship Planning")
        self.assertEqual(direct.status_code, 302)
