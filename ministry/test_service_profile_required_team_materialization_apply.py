"""Focused GENERIC-DEPLOYMENT-CONFIG.7B plan/apply and concurrency tests."""

import copy
from contextlib import contextmanager
from datetime import date, datetime, time
from io import StringIO
import json
import os
import tempfile
import unittest
from unittest.mock import Mock, patch

from django.contrib.admin.models import LogEntry
from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command
from django.db import IntegrityError, OperationalError, connections
from django.test import TestCase
from django.utils import timezone

from events.models import ServiceEvent, ServiceEventRequiredTeam, ServiceProfile
from events.scheduling_revision import (
    SchedulingRevisionBatchClaimError,
    advance_scheduling_revisions,
)
from notifications.models import Notification

from .models import (
    MinistryTeam,
    MinistryTeamParentLink,
    ServiceProfileMinistryRequirement,
    TeamAssignment,
    TeamAssignmentMember,
)
from .service_profile_required_team_materialization_apply import (
    PLAN_VERSION,
    MaterializationActorError,
    MaterializationAuditError,
    MaterializationStale,
    apply_service_profile_required_team_materialization,
    build_service_profile_required_team_materialization_plan,
)


User = get_user_model()
START = date(2026, 1, 1)
END = date(2026, 1, 31)


class MaterializationApplyTestBase:
    def setUp(self):
        self.staff = User.objects.create_user("operator", is_staff=True)
        self.profile = ServiceProfile.objects.create(
            key="profile.primary",
            name="Primary",
            name_en="Primary",
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
        )
        self.other_profile = ServiceProfile.objects.create(
            key="profile.other",
            name="Other",
            name_en="Other",
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
        )
        self.first_team = self.team("static.one")

    def team(self, key, **overrides):
        values = {
            "name": key,
            "name_en": key,
            "team_key": key,
            "is_active": True,
            "is_assignable": True,
        }
        values.update(overrides)
        return MinistryTeam.objects.create(**values)

    def requirement(self, team=None, *, active=True, sort_order=0):
        return ServiceProfileMinistryRequirement.objects.create(
            service_profile=self.profile,
            ministry_team=team or self.first_team,
            is_active=active,
            sort_order=sort_order,
        )

    def event(
        self,
        day,
        *,
        profile=None,
        status=ServiceEvent.STATUS_PUBLISHED,
        title="Neutral event",
    ):
        profile = self.profile if profile is None else profile
        return ServiceEvent.objects.create(
            title=title,
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
            service_profile=profile,
            service_profile_key=profile.key,
            start_datetime=timezone.make_aware(datetime.combine(day, time(9))),
            status=status,
        )

    def plan(self, **overrides):
        values = {
            "profile_key": self.profile.key,
            "start_date": START,
            "end_date": END,
            "actor_user_id": self.staff.pk,
        }
        values.update(overrides)
        return build_service_profile_required_team_materialization_plan(**values)

    def apply(self, plan=None, **overrides):
        plan = plan or self.plan()
        values = {
            "profile_key": self.profile.key,
            "start_date": START,
            "end_date": END,
            "actor_user_id": self.staff.pk,
            "confirmation_token": plan["confirmation_token"],
        }
        values.update(overrides)
        return apply_service_profile_required_team_materialization(**values)

    def snapshot(self):
        return {
            "rows": list(
                ServiceEventRequiredTeam.objects.order_by("pk").values_list(
                    "pk", "service_event_id", "ministry_team_id", "created_at"
                )
            ),
            "events": list(
                ServiceEvent.objects.order_by("pk").values_list(
                    "pk",
                    "scheduling_revision",
                    "status",
                    "service_profile_id",
                    "rotation_anchor_team_id",
                )
            ),
            "assignments": TeamAssignment.objects.count(),
            "members": TeamAssignmentMember.objects.count(),
            "notifications": Notification.objects.count(),
            "requirements": list(
                ServiceProfileMinistryRequirement.objects.order_by("pk").values_list(
                    "pk", "service_profile_id", "ministry_team_id", "is_active", "sort_order"
                )
            ),
            "logs": LogEntry.objects.count(),
        }


class RequiredTeamMaterializationPlanApplyTests(MaterializationApplyTestBase, TestCase):
    def test_reviewed_scale_shape_derives_16_64_4_60_without_fixed_identity(self):
        teams = [self.first_team]
        teams.extend(self.team(f"static.{index}") for index in range(2, 5))
        for team in teams:
            self.requirement(team)
        events = [self.event(date(2026, 1, day)) for day in range(1, 17)]
        complete = events[0]
        for team in teams:
            ServiceEventRequiredTeam.objects.create(
                service_event=complete,
                ministry_team=team,
            )
        ServiceEvent.objects.filter(pk=complete.pk).update(scheduling_revision=3)
        ServiceEvent.objects.filter(pk__in=[event.pk for event in events[1:]]).update(
            scheduling_revision=2
        )

        plan = self.plan()

        summary = plan["source_preview"]["summary"]
        self.assertEqual(summary["selected_events"], 16)
        self.assertEqual(summary["active_defaults"], 4)
        self.assertEqual(summary["expected_default_pairs"], 64)
        self.assertEqual(summary["already_default_pairs"], 4)
        self.assertEqual(summary["missing_default_pairs"], 60)
        self.assertEqual(plan["changed_event_count"], 15)
        result = self.apply(plan)
        self.assertEqual(result["required_team_rows_created"], 60)
        self.assertEqual(result["audit_rows_created"], 15)
        self.assertEqual(
            list(
                ServiceEvent.objects.order_by("pk").values_list(
                    "scheduling_revision", flat=True
                )
            ),
            [3] * 16,
        )

    def test_dry_run_is_zero_write_and_proposes_exact_deterministic_pairs(self):
        second_team = self.team("static.two")
        self.requirement(second_team, sort_order=2)
        self.requirement(self.first_team, sort_order=1)
        later_pk = self.event(date(2026, 1, 3))
        earlier_pk = self.event(date(2026, 1, 2))
        before = self.snapshot()

        plan = self.plan()

        self.assertEqual(self.snapshot(), before)
        self.assertEqual(plan["materialization_plan_version"], PLAN_VERSION)
        self.assertEqual(plan["source_preview_version"], "SERVICE_PROFILE_REQUIRED_TEAM_MATERIALIZATION_PREVIEW_V1")
        self.assertEqual(plan["readiness"], "READY_TO_APPLY")
        self.assertRegex(plan["confirmation_token"], r"^[0-9a-f]{64}$")
        self.assertEqual(
            [row["event_pk"] for row in plan["changed_events"]],
            sorted([later_pk.pk, earlier_pk.pk]),
        )
        self.assertEqual(
            [row["team_pk"] for row in plan["changed_events"][0]["missing_teams"]],
            sorted([self.first_team.pk, second_team.pk]),
        )

    def test_mixed_apply_creates_only_missing_and_changes_only_changed_events(self):
        second_team = self.team("static.two")
        self.requirement(self.first_team)
        self.requirement(second_team)
        complete = self.event(date(2026, 1, 2), title="Complete")
        partial = self.event(date(2026, 1, 3), title="Partial")
        empty = self.event(date(2026, 1, 4), title="Empty")
        existing_complete = [
            ServiceEventRequiredTeam.objects.create(
                service_event=complete, ministry_team=team
            )
            for team in (self.first_team, second_team)
        ]
        existing_partial = ServiceEventRequiredTeam.objects.create(
            service_event=partial, ministry_team=self.first_team
        )
        existing_facts = {
            row.pk: (row.service_event_id, row.ministry_team_id, row.created_at)
            for row in (*existing_complete, existing_partial)
        }

        plan = self.plan()
        result = self.apply(plan)

        self.assertEqual(result["changed_event_ids"], (partial.pk, empty.pk))
        self.assertEqual(result["required_team_rows_created"], 3)
        self.assertEqual(result["audit_rows_created"], 2)
        self.assertTrue(result["data_mutated"])
        complete.refresh_from_db()
        partial.refresh_from_db()
        empty.refresh_from_db()
        self.assertEqual(complete.scheduling_revision, 0)
        self.assertEqual(partial.scheduling_revision, 1)
        self.assertEqual(empty.scheduling_revision, 1)
        self.assertEqual(
            set(
                ServiceEventRequiredTeam.objects.values_list(
                    "service_event_id", "ministry_team_id"
                )
            ),
            {
                (event.pk, team.pk)
                for event in (complete, partial, empty)
                for team in (self.first_team, second_team)
            },
        )
        for row in ServiceEventRequiredTeam.objects.filter(pk__in=existing_facts):
            self.assertEqual(
                (row.service_event_id, row.ministry_team_id, row.created_at),
                existing_facts[row.pk],
            )

    def test_preserves_manual_worship_invalid_and_inactive_history_rows(self):
        self.requirement()
        event = self.event(date(2026, 1, 2))
        manual = self.team("manual.extra")
        pool = self.team(
            "worship.pool", is_assignable=False, is_worship_rotation_pool=True
        )
        child = self.team("worship.child")
        MinistryTeamParentLink.objects.create(
            child_team=child,
            parent_team=pool,
            is_active=True,
            is_primary=True,
        )
        ServiceEvent.objects.filter(pk=event.pk).update(rotation_anchor_team=child)
        invalid = self.team("invalid.explicit")
        MinistryTeam.objects.filter(pk=invalid.pk).update(is_active=False)
        history = self.team("inactive.history")
        self.requirement(history, active=False)
        stored = [
            ServiceEventRequiredTeam.objects.create(
                service_event=event, ministry_team=team
            )
            for team in (manual, pool, child, invalid, history)
        ]
        stored_ids = [row.pk for row in stored]

        result = self.apply(self.plan())

        self.assertEqual(result["required_team_rows_created"], 1)
        event.refresh_from_db()
        self.assertEqual(event.rotation_anchor_team_id, child.pk)
        self.assertEqual(
            list(
                ServiceEventRequiredTeam.objects.filter(pk__in=stored_ids)
                .order_by("pk")
                .values_list("pk", flat=True)
            ),
            stored_ids,
        )
        self.assertFalse(
            ServiceProfileMinistryRequirement.objects.get(
                ministry_team=history
            ).is_active
        )

    def test_zero_defaults_anchor_only_and_inactive_history_are_noop_without_token(self):
        event = self.event(date(2026, 1, 2))
        event.rotation_anchor_team = self.first_team
        event.save()
        self.requirement(active=False)
        before = self.snapshot()

        plan = self.plan()

        self.assertEqual(plan["readiness"], "READY_NO_MATERIALIZATION_NEEDED")
        self.assertIsNone(plan["confirmation_token"])
        self.assertEqual(plan["changed_event_count"], 0)
        self.assertEqual(self.snapshot(), before)

    def test_invalid_active_default_and_inactive_profile_block_without_token(self):
        self.requirement()
        self.event(date(2026, 1, 2))
        MinistryTeam.objects.filter(pk=self.first_team.pk).update(is_assignable=False)
        blocked = self.plan()
        self.assertEqual(blocked["readiness"], "BLOCKED")
        self.assertIsNone(blocked["confirmation_token"])

        MinistryTeam.objects.filter(pk=self.first_team.pk).update(is_assignable=True)
        ServiceProfile.objects.filter(pk=self.profile.pk).update(is_active=False)
        blocked = self.plan()
        self.assertEqual(blocked["readiness"], "BLOCKED")
        self.assertIsNone(blocked["confirmation_token"])

    def test_actor_must_be_exact_active_staff_or_superuser(self):
        absent_pk = self.staff.pk + 999
        inactive = User.objects.create_user("inactive", is_staff=True, is_active=False)
        ordinary = User.objects.create_user("ordinary")
        superuser = User.objects.create_user("super", is_superuser=True, is_staff=False)
        for actor_pk in (absent_pk, inactive.pk, ordinary.pk):
            with self.subTest(actor_pk=actor_pk), self.assertRaises(MaterializationActorError):
                self.plan(actor_user_id=actor_pk)
        self.assertEqual(self.plan(actor_user_id=superuser.pk)["actor"]["pk"], superuser.pk)

    def test_actor_is_bound_to_token_and_exact_actor_writes_audit(self):
        other_staff = User.objects.create_user("other-operator", is_staff=True)
        self.requirement()
        self.event(date(2026, 1, 2))
        plan = self.plan()
        with self.assertRaises(MaterializationStale):
            self.apply(plan, actor_user_id=other_staff.pk)
        self.assertEqual(ServiceEventRequiredTeam.objects.count(), 0)
        self.apply(plan)
        self.assertEqual(set(LogEntry.objects.values_list("user_id", flat=True)), {self.staff.pk})

    def assert_old_plan_stale_after(self, mutation):
        self.requirement()
        event = self.event(date(2026, 1, 2))
        plan = self.plan()
        mutation(event)
        before = self.snapshot()
        with self.assertRaises(MaterializationStale):
            self.apply(plan)
        self.assertEqual(self.snapshot(), before)

    def test_profile_default_team_required_surface_revision_and_lifecycle_drift_reject(self):
        mutations = (
            lambda event: ServiceProfile.objects.filter(pk=self.profile.pk).update(
                updated_at=timezone.now()
            ),
            lambda event: ServiceProfileMinistryRequirement.objects.filter(
                service_profile=self.profile
            ).update(sort_order=7),
            lambda event: MinistryTeam.objects.filter(pk=self.first_team.pk).update(
                is_assignable=False
            ),
            lambda event: ServiceEventRequiredTeam.objects.create(
                service_event=event, ministry_team=self.first_team
            ),
            lambda event: ServiceEvent.objects.filter(pk=event.pk).update(
                scheduling_revision=4
            ),
            lambda event: ServiceEvent.objects.filter(pk=event.pk).update(
                status=ServiceEvent.STATUS_COMPLETED
            ),
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation), self.atomic_subtest_rollback():
                self.assert_old_plan_stale_after(mutation)

    @contextmanager
    def atomic_subtest_rollback(self):
        from django.db import transaction

        with transaction.atomic():
            try:
                yield
            finally:
                transaction.set_rollback(True)

    def test_changed_date_scope_and_profile_identity_reject_old_token(self):
        self.requirement()
        event = self.event(date(2026, 1, 2))
        plan = self.plan()
        with self.assertRaises(MaterializationStale):
            self.apply(plan, end_date=date(2026, 1, 2))
        ServiceEvent.objects.filter(pk=event.pk).update(service_profile_key="profile.other")
        with self.assertRaises(MaterializationStale):
            self.apply(plan)
        self.assertEqual(ServiceEventRequiredTeam.objects.count(), 0)

    def test_7a_fingerprint_is_not_a_7b_confirmation_token(self):
        self.requirement()
        self.event(date(2026, 1, 2))
        plan = self.plan()
        self.assertNotEqual(
            plan["source_preview_fingerprint"], plan["confirmation_token"]
        )
        with self.assertRaises(MaterializationStale):
            self.apply(
                plan,
                confirmation_token=plan["source_preview_fingerprint"],
            )
        self.assertEqual(ServiceEventRequiredTeam.objects.count(), 0)

    def test_another_profile_and_outside_date_are_untouched(self):
        self.requirement()
        included = self.event(date(2026, 1, 2))
        outside = self.event(date(2026, 2, 2))
        other = self.event(date(2026, 1, 2), profile=self.other_profile)
        self.apply(self.plan())
        self.assertEqual(
            set(ServiceEventRequiredTeam.objects.values_list("service_event_id", flat=True)),
            {included.pk},
        )
        outside.refresh_from_db()
        other.refresh_from_db()
        self.assertEqual((outside.scheduling_revision, other.scheduling_revision), (0, 0))

    def test_create_integrity_failure_rolls_back_all_rows_and_revisions(self):
        second = self.team("static.two")
        self.requirement()
        self.requirement(second)
        events = [self.event(date(2026, 1, day)) for day in (2, 3)]
        plan = self.plan()
        original = ServiceEventRequiredTeam.save
        calls = []

        def fail_second(instance, *args, **kwargs):
            calls.append(instance)
            if len(calls) == 2:
                raise IntegrityError("simulated duplicate")
            return original(instance, *args, **kwargs)

        with patch.object(ServiceEventRequiredTeam, "save", fail_second), self.assertRaises(MaterializationStale):
            self.apply(plan)
        self.assertEqual(ServiceEventRequiredTeam.objects.count(), 0)
        self.assertEqual(
            list(ServiceEvent.objects.filter(pk__in=[e.pk for e in events]).values_list("scheduling_revision", flat=True)),
            [0, 0],
        )
        self.assertEqual(LogEntry.objects.count(), 0)

    def test_cas_failure_rolls_back_all(self):
        self.requirement()
        events = [self.event(date(2026, 1, day)) for day in (2, 3)]
        plan = self.plan()
        with patch(
            "ministry.service_profile_required_team_materialization_apply.claim_scheduling_revisions",
            side_effect=SchedulingRevisionBatchClaimError(()),
        ), self.assertRaises(MaterializationStale):
            self.apply(plan)
        self.assertEqual(ServiceEventRequiredTeam.objects.count(), 0)
        self.assertEqual(
            list(ServiceEvent.objects.filter(pk__in=[e.pk for e in events]).values_list("scheduling_revision", flat=True)),
            [0, 0],
        )

    def test_post_claim_recomputation_drift_rolls_back_all(self):
        self.requirement()
        event = self.event(date(2026, 1, 2))
        plan = self.plan()
        from . import service_profile_required_team_materialization_apply as service

        original = service.inspect_service_profile_required_team_materialization
        calls = []

        def changed(*args, **kwargs):
            result = original(*args, **kwargs)
            calls.append(result)
            if len(calls) == 2:
                result = copy.deepcopy(result)
                result["profile"]["is_active"] = False
            return result

        with patch.object(
            service,
            "inspect_service_profile_required_team_materialization",
            side_effect=changed,
        ), self.assertRaises(MaterializationStale):
            self.apply(plan)
        event.refresh_from_db()
        self.assertEqual(event.scheduling_revision, 0)
        self.assertEqual(ServiceEventRequiredTeam.objects.count(), 0)
        self.assertEqual(LogEntry.objects.count(), 0)

    def test_audit_failure_rolls_back_all(self):
        self.requirement()
        event = self.event(date(2026, 1, 2))
        plan = self.plan()
        failing_manager = Mock()
        failing_manager.log_action.side_effect = RuntimeError("audit unavailable")
        with patch.object(
            LogEntry.objects,
            "db_manager",
            return_value=failing_manager,
        ), self.assertRaises(MaterializationAuditError):
            self.apply(plan)
        event.refresh_from_db()
        self.assertEqual(event.scheduling_revision, 0)
        self.assertEqual(ServiceEventRequiredTeam.objects.count(), 0)
        self.assertEqual(LogEntry.objects.count(), 0)

    def test_shared_operation_audit_is_one_per_changed_event_and_private_free(self):
        self.requirement()
        events = [self.event(date(2026, 1, day)) for day in (2, 3)]
        result = self.apply(self.plan())
        logs = list(LogEntry.objects.order_by("object_id"))
        self.assertEqual(len(logs), 2)
        payloads = [json.loads(log.change_message) for log in logs]
        self.assertEqual({item["operation_id"] for item in payloads}, {result["operation_id"]})
        self.assertEqual({int(log.object_id) for log in logs}, {event.pk for event in events})
        for payload in payloads:
            self.assertEqual(payload["operation_type"], "service_profile_required_team_materialization")
            self.assertEqual(payload["plan_version"], PLAN_VERSION)
            serialized = json.dumps(payload)
            for forbidden in ("email", "phone", "member", "roster", "prayer", "private"):
                self.assertNotIn(forbidden, serialized.lower())

    def test_success_recomputes_zero_missing_then_old_token_replay_is_stale(self):
        self.requirement()
        event = self.event(date(2026, 1, 2))
        plan = self.plan()
        self.apply(plan)
        fresh = self.plan()
        self.assertEqual(fresh["source_preview"]["summary"]["missing_default_pairs"], 0)
        self.assertEqual(
            fresh["source_preview"]["summary"]["already_default_pairs"],
            fresh["source_preview"]["summary"]["expected_default_pairs"],
        )
        self.assertEqual(fresh["changed_event_count"], 0)
        self.assertIsNone(fresh["confirmation_token"])
        before = self.snapshot()
        with self.assertRaises(MaterializationStale):
            self.apply(plan)
        self.assertEqual(self.snapshot(), before)
        event.refresh_from_db()
        self.assertEqual(event.scheduling_revision, 1)

    def test_command_dry_run_output_and_apply_gate(self):
        self.requirement()
        self.event(date(2026, 1, 2))
        output = StringIO()
        call_command(
            "materialize_service_profile_required_teams",
            "--profile-key",
            self.profile.key,
            "--start-date",
            START.isoformat(),
            "--end-date",
            END.isoformat(),
            "--actor-user-id",
            str(self.staff.pk),
            stdout=output,
        )
        rendered = output.getvalue()
        self.assertIn("mode: DRY RUN", rendered)
        self.assertIn("source_preview_fingerprint:", rendered)
        self.assertIn("materialization_plan_version:", rendered)
        self.assertIn("readiness: READY TO APPLY", rendered)
        self.assertIn("data_mutated: false", rendered)
        self.assertEqual(ServiceEventRequiredTeam.objects.count(), 0)
        with self.assertRaises(CommandError):
            call_command(
                "materialize_service_profile_required_teams",
                "--profile-key",
                self.profile.key,
                "--start-date",
                START.isoformat(),
                "--end-date",
                END.isoformat(),
                "--actor-user-id",
                str(self.staff.pk),
                "--apply",
            )

    def test_command_apply_reports_bounded_materialization_result(self):
        self.requirement()
        self.event(date(2026, 1, 2))
        plan = self.plan()
        output = StringIO()
        call_command(
            "materialize_service_profile_required_teams",
            "--profile-key",
            self.profile.key,
            "--start-date",
            START.isoformat(),
            "--end-date",
            END.isoformat(),
            "--actor-user-id",
            str(self.staff.pk),
            "--apply",
            "--confirmation-token",
            plan["confirmation_token"],
            stdout=output,
        )
        rendered = output.getvalue()
        self.assertIn("APPLY COMPLETE", rendered)
        self.assertIn("required_team_rows_created: 1", rendered)
        self.assertIn("audit_rows_created: 1", rendered)
        self.assertIn("data_mutated: true", rendered)
        self.assertIn(
            "event_materialization: true (RequiredTeam operational rows)", rendered
        )

    def test_apply_changes_no_cross_domain_state(self):
        self.requirement()
        event = self.event(date(2026, 1, 2))
        before = self.snapshot()
        self.apply(self.plan())
        after = self.snapshot()
        self.assertEqual(after["assignments"], before["assignments"])
        self.assertEqual(after["members"], before["members"])
        self.assertEqual(after["notifications"], before["notifications"])
        self.assertEqual(after["requirements"], before["requirements"])
        event.refresh_from_db()
        self.assertIsNone(event.rotation_anchor_team_id)
        self.assertEqual(event.status, ServiceEvent.STATUS_PUBLISHED)
        self.assertEqual(event.service_profile_id, self.profile.pk)


class FileBackedSQLiteMaterializationTests(MaterializationApplyTestBase, unittest.TestCase):
    """Target-like two-connection first-writer and stale-state proof."""

    competing_alias = "materialization_competing"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        handle = tempfile.NamedTemporaryFile(
            prefix="required-team-materialization-", suffix=".sqlite3", delete=False
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
        competing = copy.deepcopy(file_config)
        competing["TEST"] = {"NAME": None}
        connections.databases[cls.competing_alias] = competing
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
        call_command("flush", database="default", interactive=False, verbosity=0)
        super().setUp()
        self.requirement()
        self.selected = self.event(date(2026, 1, 2))

    def test_revision_writer_wins_first_old_plan_fails_without_partial_write(self):
        plan = self.plan()
        advance_scheduling_revisions((self.selected.pk,), using=self.competing_alias)
        with self.assertRaises(MaterializationStale):
            self.apply(plan)
        self.selected.refresh_from_db()
        self.assertEqual(self.selected.scheduling_revision, 1)
        self.assertEqual(ServiceEventRequiredTeam.objects.count(), 0)
        self.assertEqual(LogEntry.objects.count(), 0)

    def test_required_team_writer_changes_truth_before_boundary_and_plan_is_stale(self):
        plan = self.plan()
        ServiceEventRequiredTeam.objects.using(self.competing_alias).create(
            service_event_id=self.selected.pk,
            ministry_team_id=self.first_team.pk,
        )
        with self.assertRaises(MaterializationStale):
            self.apply(plan)
        self.selected.refresh_from_db()
        self.assertEqual(self.selected.scheduling_revision, 0)
        self.assertEqual(ServiceEventRequiredTeam.objects.count(), 1)
        self.assertEqual(LogEntry.objects.count(), 0)

    def test_materialization_first_write_blocks_competitor_and_old_state_is_stale(self):
        plan = self.plan()
        from . import service_profile_required_team_materialization_apply as service

        original = service.inspect_service_profile_required_team_materialization
        calls = []
        competing_busy = []

        def inspect_after_competing_write(*args, **kwargs):
            calls.append(True)
            if len(calls) == 2:
                try:
                    ServiceProfileMinistryRequirement.objects.using(
                        self.competing_alias
                    ).filter(service_profile_id=self.profile.pk).update(sort_order=9)
                except OperationalError:
                    competing_busy.append(True)
            return original(*args, **kwargs)

        with patch.object(
            service,
            "inspect_service_profile_required_team_materialization",
            side_effect=inspect_after_competing_write,
        ):
            result = self.apply(plan)

        self.assertEqual(competing_busy, [True])
        self.assertEqual(result["required_team_rows_created"], 1)
        self.selected.refresh_from_db()
        self.assertEqual(self.selected.scheduling_revision, 1)
        with self.assertRaises(MaterializationStale):
            self.apply(plan)
