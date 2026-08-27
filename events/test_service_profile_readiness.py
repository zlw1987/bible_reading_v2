"""Focused MO-S.6D-PROFILE-SETUP.0A read-only audit tests."""

import json
from datetime import datetime, time
from io import StringIO
from unittest.mock import patch

from django.contrib.admin.models import LogEntry
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.utils import timezone

from accounts.models import ChurchStructureMembership, ChurchStructureUnit
from ministry.models import (
    MinistryTeam,
    MinistryTeamRoleAssignment,
    TeamAssignment,
    TeamAssignmentMember,
    TeamMembership,
)
from notifications.models import Notification

from .models import (
    ServiceEvent,
    ServiceEventAudienceScope,
    ServiceEventPlannerAssignment,
    ServiceEventRequiredTeam,
)
from .service_profile_readiness import (
    build_audit,
    build_expected_sundays,
    get_schema_readiness,
)


User = get_user_model()


class ServiceProfileReadinessAuditTests(TestCase):
    PROFILE_KEY = "bethany_0930_cm"

    def setUp(self):
        self.root = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_ROOT,
            code="CHURCH",
            name="Whole Church",
            name_en="Whole Church",
        )

    def local_datetime(self, year, month, day, hour=9, minute=30):
        return timezone.make_aware(
            datetime(year, month, day, hour, minute),
            timezone.get_current_timezone(),
        )

    def make_event(self, **overrides):
        values = {
            "title": "Sunday Service",
            "event_type": ServiceEvent.EVENT_SUNDAY_SERVICE,
            "start_datetime": self.local_datetime(2026, 1, 4),
            "status": ServiceEvent.STATUS_PUBLISHED,
            "service_profile_key": self.PROFILE_KEY,
        }
        values.update(overrides)
        return ServiceEvent.objects.create(**values)

    def add_audience(self, event, unit=None):
        return ServiceEventAudienceScope.objects.create(
            service_event=event,
            unit=unit or self.root,
        )

    def audit(self, *, event_type=ServiceEvent.EVENT_SUNDAY_SERVICE):
        return build_audit(
            profile_key=self.PROFILE_KEY,
            year=2026,
            target_time=time(9, 30),
            event_type=event_type,
        )

    def day(self, audit, date_value="2026-01-04"):
        return next(row for row in audit["sundays"] if row["date"] == date_value)

    def run_command(self, *args):
        out = StringIO()
        call_command("audit_service_profile_readiness", *args, stdout=out)
        return out.getvalue()

    def test_schema_ready_database_reports_0009_0010_0011(self):
        schema = get_schema_readiness()

        self.assertTrue(schema["ready"])
        self.assertEqual(
            [check["migration"] for check in schema["checks"]],
            [
                "events.0009_serviceeventplannerassignment",
                "events.0010_serviceevent_scheduling_revision",
                "events.0011_serviceevent_service_profile_key",
            ],
        )
        self.assertTrue(all(check["applied"] for check in schema["checks"]))
        self.assertTrue(all(check["schema_present"] for check in schema["checks"]))

    def test_expected_2026_contract_constructs_all_52_sundays(self):
        sundays = build_expected_sundays(2026)

        self.assertEqual(len(sundays), 52)
        self.assertEqual(sundays[0].isoformat(), "2026-01-04")
        self.assertEqual(sundays[-1].isoformat(), "2026-12-27")
        self.assertTrue(all(value.weekday() == 6 for value in sundays))
        self.assertTrue(
            all((right - left).days == 7 for left, right in zip(sundays, sundays[1:]))
        )

    def test_one_correctly_tagged_exact_event_is_ready_but_year_is_incomplete(self):
        event = self.make_event()
        self.add_audience(event)

        audit = self.audit()
        fact = audit["canonical_tagged_rows"][0]

        self.assertEqual(fact["classification"], "EXACT READY MATCH")
        self.assertTrue(fact["row_ready"])
        self.assertEqual(audit["summary"]["ready_exact_matches"], 1)
        self.assertEqual(
            audit["summary"]["missing_canonical_profile_sundays"], 51
        )
        self.assertEqual(
            audit["recommendation"], "NOT READY FOR SLICE 8 REAL-DATA MATCHING"
        )

    def test_all_52_exact_audience_ready_rows_are_profile_setup_ready(self):
        for sunday in build_expected_sundays(2026):
            event = self.make_event(
                title=f"Sunday {sunday.isoformat()}",
                start_datetime=timezone.make_aware(
                    datetime.combine(sunday, time(9, 30)),
                    timezone.get_current_timezone(),
                ),
            )
            self.add_audience(event)

        audit = self.audit()

        self.assertEqual(audit["summary"]["canonical_tagged_rows"], 52)
        self.assertEqual(audit["summary"]["ready_exact_matches"], 52)
        self.assertEqual(audit["summary"]["missing_canonical_profile_sundays"], 0)
        self.assertEqual(audit["recommendation"], "PROFILE SETUP READY")

    def test_missing_profile_event_with_no_candidate_is_reported(self):
        audit = self.audit()
        row = self.day(audit)

        self.assertEqual(row["classification"], "NO 09:30 CANDIDATE")
        self.assertEqual(row["canonical_tagged_profile_matches"], 0)
        self.assertEqual(row["untagged_exact_time_candidates"], 0)

    def test_one_untagged_exact_time_candidate_requires_human_review(self):
        candidate = self.make_event(service_profile_key="")
        self.add_audience(candidate)

        row = self.day(self.audit())

        self.assertEqual(
            row["classification"], "UNTAGGED CANDIDATE / HUMAN REVIEW REQUIRED"
        )
        self.assertEqual(row["untagged_exact_time_candidates"], 1)
        self.assertEqual(
            row["candidates"][0]["classification"],
            "UNTAGGED CANDIDATE / HUMAN REVIEW REQUIRED",
        )
        self.assertEqual(row["canonical_exact_identity_matches"], 0)

    def test_multiple_untagged_candidates_require_human_selection(self):
        first = self.make_event(service_profile_key="", title="First")
        second = self.make_event(service_profile_key="", title="Second")
        self.add_audience(first)
        self.add_audience(second)

        row = self.day(self.audit())

        self.assertEqual(
            row["classification"],
            "MULTIPLE UNTAGGED CANDIDATES — HUMAN SELECTION REQUIRED",
        )
        self.assertEqual(row["untagged_exact_time_candidates"], 2)
        self.assertEqual([item["id"] for item in row["candidates"]], [first.pk, second.pk])

    def test_explicit_nondefault_event_type_controls_cli_candidate_discovery(self):
        sunday_service = self.make_event(
            service_profile_key="",
            title="Sunday candidate",
        )
        special_meeting = self.make_event(
            service_profile_key="",
            title="Special candidate",
            event_type=ServiceEvent.EVENT_SPECIAL_MEETING,
        )
        self.add_audience(sunday_service)
        self.add_audience(special_meeting)

        payload = json.loads(
            self.run_command(
                "--event-type",
                ServiceEvent.EVENT_SPECIAL_MEETING,
                "--json",
            )
        )
        row = self.day(payload)

        self.assertEqual(payload["profile"]["event_type"], "special_meeting")
        self.assertEqual(row["untagged_exact_time_candidates"], 1)
        self.assertEqual([item["id"] for item in row["candidates"]], [special_meeting.pk])
        self.assertNotIn(sunday_service.pk, [item["id"] for item in row["candidates"]])

    def test_default_event_type_still_discovers_only_sunday_service_candidates(self):
        sunday_service = self.make_event(
            service_profile_key="",
            title="Sunday candidate",
        )
        special_meeting = self.make_event(
            service_profile_key="",
            title="Special candidate",
            event_type=ServiceEvent.EVENT_SPECIAL_MEETING,
        )
        self.add_audience(sunday_service)
        self.add_audience(special_meeting)

        row = self.day(self.audit())

        self.assertEqual(row["untagged_exact_time_candidates"], 1)
        self.assertEqual([item["id"] for item in row["candidates"]], [sunday_service.pk])
        self.assertNotIn(special_meeting.pk, [item["id"] for item in row["candidates"]])

    def test_other_profile_exact_time_event_is_visible_but_never_a_candidate(self):
        other_profile = self.make_event(
            service_profile_key="bethany_0930_em",
            title="Parallel English Service",
            location="Bethany Hall",
        )
        self.add_audience(other_profile)

        audit = self.audit()
        row = self.day(audit)

        self.assertEqual(row["canonical_tagged_profile_matches"], 0)
        self.assertEqual(row["canonical_exact_identity_matches"], 0)
        self.assertEqual(row["untagged_exact_time_candidates"], 0)
        self.assertEqual(row["other_profile_exact_time_count"], 1)
        self.assertEqual(
            row["other_profile_exact_time_events"][0]["id"], other_profile.pk
        )
        self.assertEqual(
            row["other_profile_exact_time_events"][0]["classification"],
            "EXACT-TIME EVENT OWNED BY ANOTHER PROFILE — NOT A CANDIDATE",
        )
        self.assertEqual(row["classification"], "NO 09:30 CANDIDATE")
        self.assertEqual(
            audit["recommendation"], "NOT READY FOR SLICE 8 REAL-DATA MATCHING"
        )
        self.assertIn(
            "EXACT-TIME EVENT OWNED BY ANOTHER PROFILE — NOT A CANDIDATE",
            self.run_command(),
        )

    def test_candidate_and_other_profile_exact_time_counts_remain_separate(self):
        candidate = self.make_event(service_profile_key="", title="Candidate")
        other_profile = self.make_event(
            service_profile_key="bethany_0930_em",
            title="Other profile",
        )
        self.add_audience(candidate)
        self.add_audience(other_profile)

        row = self.day(self.audit())

        self.assertEqual(row["untagged_exact_time_candidates"], 1)
        self.assertEqual(row["other_profile_exact_time_count"], 1)
        self.assertEqual([item["id"] for item in row["candidates"]], [candidate.pk])
        self.assertEqual(
            [item["id"] for item in row["other_profile_exact_time_events"]],
            [other_profile.pk],
        )

    def test_multiple_other_profile_exact_time_events_are_deterministic(self):
        first = self.make_event(
            service_profile_key="bethany_0930_em",
            title="English Ministry",
        )
        second = self.make_event(
            service_profile_key="trivalley_0930_cm",
            title="Tri-Valley",
        )
        self.add_audience(first)
        self.add_audience(second)

        audit = self.audit()
        row = self.day(audit)

        self.assertEqual(row["untagged_exact_time_candidates"], 0)
        self.assertEqual(row["other_profile_exact_time_count"], 2)
        self.assertEqual(
            [item["id"] for item in row["other_profile_exact_time_events"]],
            [first.pk, second.pk],
        )
        self.assertTrue(
            all(
                item["classification"].endswith("NOT A CANDIDATE")
                for item in row["other_profile_exact_time_events"]
            )
        )
        self.assertEqual(audit["summary"]["other_profile_exact_time_events"], 2)

    def test_same_day_1130_service_is_informational_never_target(self):
        other = self.make_event(
            service_profile_key="",
            start_datetime=self.local_datetime(2026, 1, 4, 11, 30),
        )
        self.add_audience(other)

        row = self.day(self.audit())

        self.assertEqual(row["untagged_exact_time_candidates"], 0)
        self.assertEqual(row["other_requested_type_different_time_count"], 1)
        self.assertEqual(
            row["other_requested_type_different_time_events"][0]["id"], other.pk
        )
        self.assertEqual(row["classification"], "NO 09:30 CANDIDATE")

    def test_wrong_event_type_tagged_profile_is_invalid(self):
        event = self.make_event(event_type=ServiceEvent.EVENT_SPECIAL_MEETING)
        self.add_audience(event)

        fact = self.audit()["canonical_tagged_rows"][0]

        self.assertIn("wrong_event_type", fact["identity_issues"])
        self.assertFalse(fact["row_ready"])

    def test_wrong_local_time_tagged_profile_is_invalid(self):
        event = self.make_event(start_datetime=self.local_datetime(2026, 1, 4, 11, 30))
        self.add_audience(event)

        audit = self.audit()

        self.assertIn(
            "wrong_local_time", audit["canonical_tagged_rows"][0]["identity_issues"]
        )
        self.assertEqual(
            audit["summary"]["missing_canonical_profile_sundays"], 52
        )

    def test_draft_tagged_target_is_not_ready(self):
        event = self.make_event(status=ServiceEvent.STATUS_DRAFT)
        self.add_audience(event)

        fact = self.audit()["canonical_tagged_rows"][0]

        self.assertIn("draft", fact["readiness_issues"])
        self.assertFalse(fact["row_ready"])

    def test_cancelled_tagged_target_is_not_ready(self):
        event = self.make_event(status=ServiceEvent.STATUS_CANCELLED)
        self.add_audience(event)

        fact = self.audit()["canonical_tagged_rows"][0]

        self.assertIn("cancelled", fact["readiness_issues"])
        self.assertFalse(fact["row_ready"])

    def test_completed_historical_tagged_target_is_accepted_and_reported(self):
        event = self.make_event(status=ServiceEvent.STATUS_COMPLETED)
        self.add_audience(event)

        audit = self.audit()

        self.assertTrue(audit["canonical_tagged_rows"][0]["row_ready"])
        self.assertEqual(
            audit["summary"]["completed_historical_canonical_rows"], 1
        )

    def test_zero_audience_tagged_target_fails_closed_and_is_not_ready(self):
        self.make_event()

        fact = self.audit()["canonical_tagged_rows"][0]

        self.assertEqual(fact["audience"]["row_count"], 0)
        self.assertTrue(fact["audience"]["ordinary_user_fail_closed"])
        self.assertIn("zero_audience_rows", fact["readiness_issues"])
        self.assertFalse(fact["row_ready"])

    def test_inactive_audience_unit_is_detected_without_repair(self):
        unit = ChurchStructureUnit.objects.create(
            parent=self.root,
            unit_type=ChurchStructureUnit.UNIT_MINISTRY_CONTEXT,
            code="CM",
            name="Chinese Ministry",
            name_en="Chinese Ministry",
        )
        event = self.make_event()
        self.add_audience(event, unit)
        ChurchStructureUnit.objects.filter(pk=unit.pk).update(is_active=False)

        fact = self.audit()["canonical_tagged_rows"][0]

        self.assertIn("inactive_audience_units", fact["readiness_issues"])
        self.assertFalse(fact["audience"]["ready"])

    def test_duplicate_tagged_rows_on_one_sunday_block_readiness(self):
        first = self.make_event(title="First tagged")
        second = self.make_event(title="Second tagged")
        self.add_audience(first)
        self.add_audience(second)

        audit = self.audit()
        row = self.day(audit)

        self.assertEqual(row["classification"], "DUPLICATE CANONICAL PROFILE ROWS")
        self.assertEqual(row["canonical_tagged_profile_matches"], 2)
        self.assertEqual(audit["summary"]["duplicate_canonical_sundays"], 1)
        self.assertEqual(audit["summary"]["ready_exact_matches"], 0)

    def test_unexpected_out_of_contract_tagged_row_is_reported(self):
        event = self.make_event(start_datetime=self.local_datetime(2027, 1, 3))
        self.add_audience(event)

        audit = self.audit()

        self.assertIn(
            "wrong_year_or_date", audit["canonical_tagged_rows"][0]["identity_issues"]
        )
        self.assertEqual(audit["summary"]["unexpected_profile_tagged_rows"], 1)

    def test_resemblance_facts_never_auto_select_or_establish_profile_identity(self):
        host = ChurchStructureUnit.objects.create(
            parent=self.root,
            unit_type=ChurchStructureUnit.UNIT_MINISTRY_CONTEXT,
            code="CM",
            name="Chinese Ministry",
            name_en="Chinese Ministry",
        )
        selected_team = MinistryTeam.objects.create(name="Worship A")
        candidate = self.make_event(
            service_profile_key="",
            title="Bethany Chinese Sunday Service",
            location="Bethany Main Campus",
            host_language_unit=host,
            rotation_anchor_team=selected_team,
        )
        self.add_audience(candidate, host)

        audit = self.audit()
        row = self.day(audit)

        self.assertEqual(row["canonical_tagged_profile_matches"], 0)
        self.assertEqual(row["canonical_exact_identity_matches"], 0)
        self.assertEqual(
            row["classification"], "UNTAGGED CANDIDATE / HUMAN REVIEW REQUIRED"
        )
        self.assertEqual(row["candidates"][0]["service_profile_key"], "")
        self.assertEqual(row["candidates"][0]["host_language_unit"]["code"], "CM")
        self.assertEqual(
            row["candidates"][0]["selected_worship_team"]["id"], selected_team.pk
        )

    def test_schema_not_ready_stops_before_serviceevent_query_and_reports_cleanly(self):
        schema = {
            "ready": False,
            "checks": [
                {
                    "migration": "events.0009_serviceeventplannerassignment",
                    "applied": False,
                    "schema_present": False,
                },
                {
                    "migration": "events.0010_serviceevent_scheduling_revision",
                    "applied": False,
                    "schema_present": False,
                },
                {
                    "migration": "events.0011_serviceevent_service_profile_key",
                    "applied": False,
                    "schema_present": False,
                },
            ],
            "error": "",
        }
        with patch(
            "events.service_profile_readiness.get_schema_readiness",
            return_value=schema,
        ), patch("events.service_profile_readiness.ServiceEvent.objects") as objects:
            output = self.run_command()

        objects.filter.assert_not_called()
        self.assertIn("schema: NOT READY", output)
        self.assertIn("ServiceEvent data audit: NOT EVALUATED", output)
        self.assertNotIn("no such column", output)

    def test_command_has_no_apply_option(self):
        from events.management.commands.audit_service_profile_readiness import Command

        parser = Command().create_parser(
            "manage.py", "audit_service_profile_readiness"
        )
        dests = {action.dest for action in parser._actions}
        self.assertNotIn("apply", dests)
        self.assertIn("json", dests)

    def test_profile_key_longer_than_model_max_length_is_rejected(self):
        max_length = ServiceEvent._meta.get_field("service_profile_key").max_length

        with self.assertRaisesMessage(
            CommandError,
            f"--profile-key must be at most {max_length} characters.",
        ):
            self.run_command("--profile-key", "a" * (max_length + 1))

    def test_json_other_profile_evidence_excludes_private_event_data(self):
        private_user = User.objects.create_user(username="PRIVATE_OTHER_PROFILE_USER")
        other_profile = self.make_event(
            service_profile_key="bethany_0930_em",
            title="Parallel Service",
            created_by=private_user,
            description="PRIVATE_OTHER_PROFILE_DESCRIPTION",
            meeting_link="https://private-other-profile.example.test/secret",
        )
        self.add_audience(other_profile)
        ServiceEventPlannerAssignment.objects.create(
            service_event=other_profile,
            user=private_user,
            notes="PRIVATE_OTHER_PROFILE_PLANNER_NOTE",
        )

        output = self.run_command("--json")
        payload = json.loads(output)
        row = self.day(payload)

        self.assertEqual(row["other_profile_exact_time_count"], 1)
        self.assertEqual(
            row["other_profile_exact_time_events"][0]["service_profile_key"],
            "bethany_0930_em",
        )
        for private_value in (
            "PRIVATE_OTHER_PROFILE_USER",
            "PRIVATE_OTHER_PROFILE_DESCRIPTION",
            "PRIVATE_OTHER_PROFILE_PLANNER_NOTE",
            "private-other-profile.example.test",
        ):
            self.assertNotIn(private_value, output)

    def test_json_is_deterministic_and_excludes_roster_user_and_private_text(self):
        private_user = User.objects.create_user(username="PRIVATE_USER_NAME")
        selected_team = MinistryTeam.objects.create(name="Worship Review Team")
        event = self.make_event(
            service_profile_key="",
            rotation_anchor_team=selected_team,
            created_by=private_user,
            description="PRIVATE_EVENT_NOTE",
            meeting_link="https://private.example.test/secret",
        )
        self.add_audience(event)
        ServiceEventPlannerAssignment.objects.create(
            service_event=event,
            user=private_user,
            notes="PRIVATE_PLANNER_NOTE",
        )
        membership = TeamMembership.objects.create(
            team=selected_team,
            user=private_user,
            display_name="PRIVATE_ROSTER_NAME",
            email="private-roster@example.test",
            notes="PRIVATE_MEMBERSHIP_NOTE",
        )
        assignment = TeamAssignment.objects.create(
            service_event=event,
            ministry_team=selected_team,
        )
        TeamAssignmentMember.objects.create(
            assignment=assignment,
            membership=membership,
            confirmation_note="PRIVATE_CONFIRMATION_NOTE",
        )

        first = self.run_command("--json")
        second = self.run_command("--json")
        payload = json.loads(first)

        self.assertEqual(first, second)
        self.assertEqual(payload["mode"], "read-only")
        for secret in (
            "PRIVATE_USER_NAME",
            "PRIVATE_EVENT_NOTE",
            "PRIVATE_PLANNER_NOTE",
            "PRIVATE_ROSTER_NAME",
            "private-roster@example.test",
            "PRIVATE_MEMBERSHIP_NOTE",
            "PRIVATE_CONFIRMATION_NOTE",
            "private.example.test",
        ):
            self.assertNotIn(secret, first)

    def test_command_is_zero_write_across_required_models_and_callbacks(self):
        team = MinistryTeam.objects.create(name="Audit Team")
        event = self.make_event(service_profile_key="", rotation_anchor_team=team)
        self.add_audience(event)
        tracked_models = (
            ServiceEvent,
            ServiceEventAudienceScope,
            ServiceEventRequiredTeam,
            ServiceEventPlannerAssignment,
            MinistryTeam,
            TeamAssignment,
            TeamAssignmentMember,
            TeamMembership,
            MinistryTeamRoleAssignment,
            ChurchStructureMembership,
            LogEntry,
            Notification,
        )

        def snapshot():
            return {
                model._meta.label: list(model.objects.order_by("pk").values())
                for model in tracked_models
            }

        before = snapshot()
        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            self.run_command()
        after = snapshot()

        self.assertEqual(callbacks, [])
        self.assertEqual(after, before)
        event.refresh_from_db()
        self.assertEqual(event.service_profile_key, "")
        self.assertEqual(event.scheduling_revision, 0)
