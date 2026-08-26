"""Focused Worship Rotation Planner preview and confirmation tests."""

from datetime import datetime, time
import copy
import os
import tempfile
import time as stdlib_time
import unittest
from unittest.mock import patch

from django.contrib.admin.models import LogEntry
from django.contrib.auth.models import User
from django.core import signing
from django.core.management import call_command
from django.db import connection, connections
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from accounts.models import ChurchStructureMembership, ChurchStructureUnit
from core.notification_delivery import notification_sink_override_for_tests
from ministry.models import (
    MinistryTeam,
    MinistryTeamParentLink,
    MinistryTeamRoleAssignment,
    MinistryTeamRoleType,
    TeamAssignment,
    TeamAssignmentMember,
    TeamMembership,
)
from ministry.services.worship_rotation_planner import (
    PLANNER_CONTRACT_VERSION,
    PLANNER_SIGNING_SALT,
    PlannerBlocker,
    SignedProposalError,
    SignedProposalUserMismatch,
    TailResolution,
    build_worship_rotation_proposal,
    confirm_worship_rotation_proposal,
    decode_signed_worship_rotation_proposal,
)
from ministry.services import worship_rotation_planner as planner_service
from events.scheduling_revision import (
    SchedulingRevisionBusyError,
    advance_scheduling_revisions,
)
from notifications.models import Notification

from .models import (
    ServiceEvent,
    ServiceEventAudienceScope,
    ServiceEventPlannerAssignment,
    ServiceEventRequiredTeam,
)


class WorshipRotationPlannerTestBase(TestCase):
    def setUp(self):
        self.root = self.unit("ROOT", "Whole Church", ChurchStructureUnit.UNIT_ROOT)
        self.cm = self.unit(
            "CM", "Chinese Ministry", ChurchStructureUnit.UNIT_MINISTRY_CONTEXT, self.root
        )
        self.em = self.unit(
            "EM", "English Ministry", ChurchStructureUnit.UNIT_MINISTRY_CONTEXT, self.root
        )
        self.cm_pool = self.pool("Chinese Worship Pool", self.cm)
        self.em_pool = self.pool("English Worship Pool", self.em)
        self.c1 = self.team("Chinese Worship Team One", self.cm_pool)
        self.c2 = self.team("Chinese Worship Team Two", self.cm_pool)
        self.e1 = self.team("English Worship Team One", self.em_pool)
        self.av_container = MinistryTeam.objects.create(
            name="AVL Ministry", name_en="AVL Ministry", is_assignable=False
        )
        MinistryTeamParentLink.objects.create(
            child_team=self.av_container,
            parent_church_unit=self.cm,
            is_primary=True,
        )
        self.projection = self.team("Projection", self.av_container)
        self.sound = self.team("Sound", self.av_container)
        self.staff = User.objects.create_user(
            username="planner_staff", password="pw", is_staff=True
        )
        self.other = User.objects.create_user(username="other", password="pw")
        self.first_sunday = self.next_sunday()
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

    def next_sunday(self):
        today = timezone.localdate()
        days = (6 - today.weekday()) % 7
        if days == 0:
            days = 7
        local_value = datetime.combine(
            today + timezone.timedelta(days=days), time(10, 0)
        )
        return timezone.make_aware(local_value, timezone.get_current_timezone())

    def event(self, week, team, *, audience=None, title=None, **overrides):
        values = {
            "title": title or f"Sunday {week}",
            "title_en": title or f"Sunday {week}",
            "event_type": ServiceEvent.EVENT_SUNDAY_SERVICE,
            "start_datetime": self.first_sunday + timezone.timedelta(weeks=week),
            "status": ServiceEvent.STATUS_PUBLISHED,
            "rotation_anchor_team": team,
        }
        values.update(overrides)
        event = ServiceEvent.objects.create(**values)
        ServiceEventAudienceScope.objects.create(
            service_event=event, unit=audience or self.cm
        )
        return event

    def proposal(self, events, inserted=None, user=None, now=None):
        return build_worship_rotation_proposal(
            user=user or self.staff,
            event_ids=[event.pk for event in events],
            inserted_team=inserted or self.c2,
            now=now,
        )

    def stored_assignment(self, event, team, status=TeamAssignment.STATUS_SCHEDULED):
        row = TeamAssignment(service_event=event, ministry_team=team, status=status)
        TeamAssignment.objects.bulk_create([row])
        return row


class WorshipRotationProposalDomainTests(WorshipRotationPlannerTestBase):
    def test_happy_path_terminal_blank_and_exact_shift(self):
        events = [self.event(0, self.c1), self.event(1, self.c2), self.event(2, None)]
        proposal = self.proposal(events)

        self.assertTrue(proposal.confirmable)
        self.assertEqual(
            [row.proposed_team for row in proposal.rows],
            [self.c2, self.c1, self.c2],
        )
        self.assertIsNone(proposal.displaced_tail)
        self.assertEqual(proposal.tail_resolution, TailResolution.TERMINAL_BLANK)
        self.assertEqual(
            proposal.normalized_payload["tail_resolution"], "terminal_blank"
        )

    def test_two_row_cycle_closure_is_confirmable(self):
        events = [self.event(0, self.c1), self.event(1, self.c2)]
        proposal = self.proposal(events)
        self.assertEqual(proposal.displaced_tail, self.c2)
        self.assertEqual(proposal.tail_resolution, TailResolution.CYCLE_CLOSED)
        self.assertNotIn(PlannerBlocker.DISPLACED_TAIL, proposal.blockers)
        self.assertTrue(proposal.confirmable)

    def test_longer_cycle_closure_preserves_team_identity_multiset(self):
        c3 = self.team("Chinese Worship Team Three", self.cm_pool)
        team_a = self.team("Chinese Worship Team A", self.cm_pool)
        events = [
            self.event(0, self.c1),
            self.event(1, self.c2),
            self.event(2, c3),
            self.event(3, team_a),
        ]
        proposal = self.proposal(events, inserted=team_a)

        self.assertEqual(
            [row.proposed_team for row in proposal.rows],
            [team_a, self.c1, self.c2, c3],
        )
        self.assertEqual(proposal.tail_resolution, TailResolution.CYCLE_CLOSED)
        self.assertCountEqual(
            [row.before_team.pk for row in proposal.rows],
            [row.proposed_team.pk for row in proposal.rows],
        )
        self.assertTrue(proposal.confirmable)

    def test_true_non_null_tail_is_prominent_review_blocker(self):
        team_a = self.team("Chinese Worship Team A", self.cm_pool)
        events = [self.event(0, self.c1), self.event(1, self.c2)]
        proposal = self.proposal(events, inserted=team_a)
        self.assertEqual(proposal.displaced_tail, self.c2)
        self.assertEqual(proposal.tail_resolution, TailResolution.DISPLACED)
        self.assertIn(PlannerBlocker.DISPLACED_TAIL, proposal.blockers)
        self.assertFalse(proposal.confirmable)

    def test_same_team_noop_beginning_still_cycle_closes(self):
        events = [
            self.event(0, self.c1),
            self.event(1, self.c2),
            self.event(2, self.c1),
        ]
        proposal = self.proposal(events, inserted=self.c1)

        self.assertFalse(proposal.rows[0].changed)
        self.assertEqual(proposal.tail_resolution, TailResolution.CYCLE_CLOSED)
        self.assertNotIn(PlannerBlocker.DISPLACED_TAIL, proposal.blockers)
        self.assertTrue(proposal.confirmable)

    def test_tail_identity_uses_exact_primary_key_not_display_name(self):
        same_name_team = self.team(self.c2.name, self.cm_pool)
        events = [self.event(0, self.c1), self.event(1, same_name_team)]
        proposal = self.proposal(events, inserted=self.c2)

        self.assertEqual(proposal.displaced_tail.name, proposal.inserted_team.name)
        self.assertNotEqual(proposal.displaced_tail.pk, proposal.inserted_team.pk)
        self.assertEqual(proposal.tail_resolution, TailResolution.DISPLACED)
        self.assertIn(PlannerBlocker.DISPLACED_TAIL, proposal.blockers)

    def test_interior_blank_and_weekly_gap_block(self):
        blank = [self.event(0, self.c1), self.event(1, None), self.event(2, None)]
        self.assertIn(PlannerBlocker.INTERIOR_BLANK, self.proposal(blank).blockers)

        gap = [self.event(4, self.c1), self.event(6, None)]
        self.assertIn(PlannerBlocker.WEEKLY_GAP, self.proposal(gap).blockers)

    def test_chain_bounds_duplicates_missing_and_invalid_lifecycle(self):
        one = self.event(0, self.c1)
        self.assertIn(PlannerBlocker.CHAIN_LENGTH, self.proposal([one]).blockers)
        too_many = build_worship_rotation_proposal(
            user=self.staff,
            event_ids=[one.pk] * 54,
            inserted_team=self.c2,
        )
        self.assertIn(PlannerBlocker.CHAIN_LENGTH, too_many.blockers)
        self.assertIn(PlannerBlocker.DUPLICATE_EVENT, too_many.blockers)
        missing = build_worship_rotation_proposal(
            user=self.staff, event_ids=[one.pk, 999999], inserted_team=self.c2
        )
        self.assertIn(PlannerBlocker.EVENT_NOT_FOUND, missing.blockers)

        for index, values in enumerate(
            [
                {"status": ServiceEvent.STATUS_DRAFT},
                {"status": ServiceEvent.STATUS_COMPLETED},
                {"status": ServiceEvent.STATUS_CANCELLED},
                {"start_datetime": timezone.now() - timezone.timedelta(days=1)},
                {"event_type": ServiceEvent.EVENT_OTHER},
            ],
            start=10,
        ):
            with self.subTest(values=values):
                invalid = self.event(index, self.c1, **values)
                landing = self.event(index + 1, None)
                self.assertIn(
                    PlannerBlocker.INVALID_EVENT,
                    self.proposal([invalid, landing]).blockers,
                )

    def test_same_sunday_parallel_events_are_explicit_and_never_auto_selected(self):
        first = self.event(0, self.c1, title="CM Sunday")
        parallel = self.event(
            0,
            self.e1,
            audience=self.em,
            title="EM Sunday",
            start_datetime=self.first_sunday + timezone.timedelta(hours=2),
        )
        proposal = self.proposal([first, parallel])
        self.assertIn(PlannerBlocker.SAME_SUNDAY, proposal.blockers)
        self.client.force_login(self.staff)
        response = self.client.get(reverse("worship_rotation_planner"))
        self.assertContains(response, "CM Sunday")
        self.assertContains(response, "EM Sunday")
        response = self.client.post(
            reverse("worship_rotation_planner"),
            {"events": [first.pk, parallel.pk], "inserted_team": self.c2.pk},
        )
        self.assertFormError(
            response.context["form"],
            "events",
            "Select exactly one event for each represented Sunday.",
        )
        self.assertIsNone(response.context["proposal"])

    def test_inserted_and_shifted_destination_ineligibility(self):
        cm_first = self.event(0, self.c1)
        cm_landing = self.event(1, None)
        inserted = self.proposal([cm_first, cm_landing], inserted=self.e1)
        self.assertIn(PlannerBlocker.DESTINATION_INELIGIBLE, inserted.rows[0].blockers)

        em_landing = self.event(3, None, audience=self.em)
        shifted = self.proposal([self.event(2, self.c1), em_landing])
        self.assertIn(PlannerBlocker.DESTINATION_INELIGIBLE, shifted.rows[1].blockers)

    def test_whole_church_multiple_pool_union_is_valid(self):
        first = self.event(0, self.c1, audience=self.root)
        landing = self.event(1, None, audience=self.root)
        proposal = self.proposal([first, landing], inserted=self.e1)
        self.assertTrue(proposal.confirmable)
        eligible = proposal.rows[0].fingerprints["governance"]["eligible_candidates"]
        self.assertIn([self.c1.pk, self.cm_pool.pk], eligible)
        self.assertIn([self.e1.pk, self.em_pool.pk], eligible)

    def test_unauthorized_changed_middle_row_blocks_whole_proposal(self):
        events = [
            self.event(0, self.c1),
            self.event(1, self.c2),
            self.event(2, self.c2),
        ]
        ServiceEventPlannerAssignment.objects.create(service_event=events[0], user=self.other)
        ServiceEventPlannerAssignment.objects.create(service_event=events[2], user=self.other)
        proposal = self.proposal(events, user=self.other)
        self.assertEqual(proposal.tail_resolution, TailResolution.CYCLE_CLOSED)
        self.assertIn(PlannerBlocker.UNAUTHORIZED, proposal.rows[1].blockers)
        self.assertFalse(proposal.confirmable)

    def test_cycle_closure_does_not_override_other_blockers(self):
        destination_events = [
            self.event(6, self.c1),
            self.event(7, self.e1, audience=self.em),
        ]
        destination = self.proposal(destination_events, inserted=self.e1)
        self.assertEqual(destination.tail_resolution, TailResolution.CYCLE_CLOSED)
        self.assertIn(
            PlannerBlocker.DESTINATION_INELIGIBLE,
            destination.blockers,
        )
        self.assertFalse(destination.confirmable)

        assignment_events = [self.event(9, self.c1), self.event(10, self.c2)]
        self.stored_assignment(assignment_events[0], self.c1)
        assignment = self.proposal(assignment_events, inserted=self.c2)
        self.assertEqual(assignment.tail_resolution, TailResolution.CYCLE_CLOSED)
        self.assertIn(PlannerBlocker.WORSHIP_ASSIGNMENT, assignment.blockers)
        self.assertFalse(assignment.confirmable)

        conflict_events = [self.event(12, self.c1), self.event(13, self.c2)]
        self.stored_assignment(conflict_events[0], self.c2)
        conflict = self.proposal(conflict_events, inserted=self.c2)
        self.assertEqual(conflict.tail_resolution, TailResolution.CYCLE_CLOSED)
        self.assertIn(PlannerBlocker.OWNERSHIP_CONFLICT, conflict.blockers)
        self.assertFalse(conflict.confirmable)

    def test_changed_assignment_blocks_but_noop_consistent_is_informational(self):
        changed = self.event(0, self.c1)
        landing = self.event(1, None)
        self.stored_assignment(changed, self.c1)
        proposal = self.proposal([changed, landing], inserted=self.c2)
        self.assertIn(PlannerBlocker.WORSHIP_ASSIGNMENT, proposal.rows[0].blockers)

        noop = self.event(3, self.c1)
        next_landing = self.event(4, None)
        self.stored_assignment(noop, self.c1)
        proposal = self.proposal([noop, next_landing], inserted=self.c1)
        self.assertTrue(proposal.rows[0].worship_assignment_informational)
        self.assertNotIn(PlannerBlocker.WORSHIP_ASSIGNMENT, proposal.rows[0].blockers)

    def test_off_team_multiple_and_duplicate_ownership_fail_closed(self):
        for index, assignments in enumerate(
            [(self.c2,), (self.c1, self.c2), (self.c1, self.c1)], start=6
        ):
            with self.subTest(assignments=assignments):
                event = self.event(index * 2, self.c1)
                landing = self.event(index * 2 + 1, None)
                for team in assignments:
                    self.stored_assignment(event, team)
                proposal = self.proposal([event, landing], inserted=self.c1)
                self.assertIn(PlannerBlocker.OWNERSHIP_CONFLICT, proposal.rows[0].blockers)

        out_of_scope = self.event(30, self.c1, audience=self.em)
        out_landing = self.event(31, None, audience=self.em)
        self.stored_assignment(out_of_scope, self.c1)
        proposal = self.proposal([out_of_scope, out_landing], inserted=self.e1)
        self.assertIn(PlannerBlocker.OWNERSHIP_CONFLICT, proposal.rows[0].blockers)

    def test_downstream_projection_is_roster_free_and_fingerprinted(self):
        first = self.event(0, self.c1)
        landing = self.event(1, None)
        ServiceEventRequiredTeam.objects.create(
            service_event=first, ministry_team=self.projection
        )
        assignment = TeamAssignment.objects.create(
            service_event=first,
            ministry_team=self.sound,
            status=TeamAssignment.STATUS_CONFIRMED,
            notes="SECRET ASSIGNMENT NOTE",
        )
        membership = TeamMembership.objects.create(
            team=self.sound,
            display_name="PRIVATE MEMBER NAME",
            email="private@example.com",
            notes="SECRET MEMBER NOTE",
        )
        TeamAssignmentMember.objects.create(
            assignment=assignment,
            membership=membership,
            confirmation_note="SECRET CONFIRMATION",
        )
        proposal = self.proposal([first, landing])
        impacts = proposal.rows[0].downstream_impacts
        self.assertEqual(
            [(impact.team, impact.participation, impact.assignment_state) for impact in impacts],
            [(self.projection, "required", "none"), (self.sound, "additional", "one")],
        )
        serialized = str(proposal.normalized_payload)
        for private_value in [
            "PRIVATE MEMBER NAME",
            "private@example.com",
            "SECRET ASSIGNMENT NOTE",
            "SECRET MEMBER NOTE",
            "SECRET CONFIRMATION",
        ]:
            self.assertNotIn(private_value, serialized)

    def test_fingerprints_are_deterministic_and_operation_uuid_is_per_proposal(self):
        events = [self.event(0, self.c1), self.event(1, None)]
        fixed_now = timezone.now()
        first = self.proposal(events, now=fixed_now)
        second = self.proposal(list(reversed(events)), now=fixed_now)
        self.assertEqual(first.ordered_event_ids, second.ordered_event_ids)
        self.assertEqual(
            first.normalized_payload["fingerprints"],
            second.normalized_payload["fingerprints"],
        )
        self.assertEqual(first.operation_id, first.normalized_payload["operation_id"])
        self.assertNotEqual(first.operation_id, second.operation_id)


class WorshipRotationSigningTests(WorshipRotationPlannerTestBase):
    def setUp(self):
        super().setUp()
        self.events = [self.event(0, self.c1), self.event(1, None)]
        self.proposal_value = self.proposal(self.events)

    def test_signed_round_trip_and_user_binding(self):
        payload = decode_signed_worship_rotation_proposal(
            self.proposal_value.signed_payload, user=self.staff
        )
        self.assertEqual(payload, self.proposal_value.normalized_payload)
        self.assertEqual(payload["contract_version"], PLANNER_CONTRACT_VERSION)
        self.assertEqual(PLANNER_CONTRACT_VERSION, 3)
        self.assertEqual(
            payload["fingerprints"][0]["event"]["scheduling_revision"],
            self.events[0].scheduling_revision,
        )
        self.assertEqual(payload["tail_resolution"], "terminal_blank")
        with self.assertRaises(SignedProposalUserMismatch):
            decode_signed_worship_rotation_proposal(
                self.proposal_value.signed_payload, user=self.other
            )

    def test_tampered_expired_and_wrong_contract_payloads_are_rejected(self):
        token = self.proposal_value.signed_payload
        tampered = token[:-1] + ("a" if token[-1] != "a" else "b")
        with self.assertRaises(SignedProposalError):
            decode_signed_worship_rotation_proposal(tampered, user=self.staff)
        with self.assertRaises(SignedProposalError):
            decode_signed_worship_rotation_proposal(token, user=self.staff, max_age=-1)

        payload = dict(self.proposal_value.normalized_payload)
        payload["contract_version"] = 999
        wrong = signing.dumps(
            payload, compress=True, salt=PLANNER_SIGNING_SALT
        )
        with self.assertRaises(SignedProposalError):
            decode_signed_worship_rotation_proposal(wrong, user=self.staff)

        missing_revision = dict(self.proposal_value.normalized_payload)
        missing_revision["fingerprints"] = [
            {
                **fingerprint,
                "event": {
                    key: value
                    for key, value in fingerprint["event"].items()
                    if key != "scheduling_revision"
                },
            }
            for fingerprint in missing_revision["fingerprints"]
        ]
        missing_revision_token = signing.dumps(
            missing_revision, compress=True, salt=PLANNER_SIGNING_SALT
        )
        with self.assertRaises(SignedProposalError):
            decode_signed_worship_rotation_proposal(
                missing_revision_token, user=self.staff
            )

    def test_inconsistent_tail_resolution_is_rejected(self):
        payload = dict(self.proposal_value.normalized_payload)
        payload["tail_resolution"] = TailResolution.CYCLE_CLOSED.value
        inconsistent = signing.dumps(
            payload,
            compress=True,
            salt=PLANNER_SIGNING_SALT,
        )

        with self.assertRaisesMessage(
            SignedProposalError, "Inconsistent tail resolution."
        ):
            decode_signed_worship_rotation_proposal(
                inconsistent,
                user=self.staff,
            )

    def test_mismatched_fingerprint_event_id_and_shift_shape_are_rejected(self):
        for mutation in ("fingerprint_event", "proposed_shift"):
            with self.subTest(mutation=mutation):
                payload = signing.loads(
                    self.proposal_value.signed_payload,
                    salt=PLANNER_SIGNING_SALT,
                )
                if mutation == "fingerprint_event":
                    payload["fingerprints"][0]["event"]["event_id"] = 999999
                else:
                    payload["proposed_team_ids"][1] = self.c2.pk
                token = signing.dumps(
                    payload,
                    compress=True,
                    salt=PLANNER_SIGNING_SALT,
                )
                with self.assertRaisesMessage(
                    SignedProposalError,
                    "Invalid proposal shape.",
                ):
                    decode_signed_worship_rotation_proposal(
                        token,
                        user=self.staff,
                    )


class WorshipRotationPlannerViewTests(WorshipRotationPlannerTestBase):
    def setUp(self):
        super().setUp()
        self.events = [self.event(0, self.c1), self.event(1, None)]
        self.client.force_login(self.staff)

    def counts(self):
        return {
            "events": ServiceEvent.objects.count(),
            "audience": ServiceEventAudienceScope.objects.count(),
            "required": ServiceEventRequiredTeam.objects.count(),
            "planners": ServiceEventPlannerAssignment.objects.count(),
            "teams": MinistryTeam.objects.count(),
            "assignments": TeamAssignment.objects.count(),
            "assignment_members": TeamAssignmentMember.objects.count(),
            "team_memberships": TeamMembership.objects.count(),
            "structure_memberships": ChurchStructureMembership.objects.count(),
            "logs": LogEntry.objects.count(),
            "notifications": Notification.objects.count(),
            "scheduling_revisions": tuple(
                ServiceEvent.objects.order_by("pk").values_list(
                    "pk", "scheduling_revision"
                )
            ),
        }

    def test_contextual_entry_and_bilingual_copy(self):
        response = self.client.get(reverse("worship_planning"))
        self.assertContains(response, "Rotation Planner")
        response = self.client.get(reverse("worship_rotation_planner"))
        self.assertContains(response, "Shift later Worship Teams")
        self.assertContains(response, "Generate Preview")
        self.assertContains(response, "Generate and review the preview")

        session = self.client.session
        session["language"] = "zh"
        session.save()
        response = self.client.get(reverse("worship_rotation_planner"))
        for copy in ["敬拜轮值规划", "顺延后续敬拜团队", "生成预览"]:
            self.assertContains(response, copy)

    def test_valid_preview_renders_shift_tail_and_roster_free_impact(self):
        ServiceEventRequiredTeam.objects.create(
            service_event=self.events[0], ministry_team=self.projection
        )
        assignment = TeamAssignment.objects.create(
            service_event=self.events[0],
            ministry_team=self.sound,
            notes="PRIVATE ASSIGNMENT NOTE",
        )
        membership = TeamMembership.objects.create(
            team=self.sound,
            display_name="PRIVATE ROSTER NAME",
            email="private-roster@example.com",
        )
        TeamAssignmentMember.objects.create(
            assignment=assignment,
            membership=membership,
            confirmation_note="PRIVATE CONFIRMATION NOTE",
        )
        response = self.client.post(
            reverse("worship_rotation_planner"),
            {"events": [event.pk for event in self.events], "inserted_team": self.c2.pk},
        )
        self.assertContains(response, "Shift Preview")
        self.assertContains(response, "Before")
        self.assertContains(response, "After")
        self.assertContains(response, "Downstream teams to review")
        self.assertContains(response, "Displaced after selected range")
        self.assertNotContains(response, "Rotation cycle closes")
        self.assertContains(response, "Confirm Shift")
        self.assertNotContains(response, "PRIVATE ROSTER NAME")
        self.assertNotContains(response, "private-roster@example.com")
        self.assertNotContains(response, "PRIVATE ASSIGNMENT NOTE")
        self.assertNotContains(response, "PRIVATE CONFIRMATION NOTE")

    def test_cycle_closed_preview_is_positive_and_bilingual(self):
        events = [self.event(3, self.c1), self.event(4, self.c2)]
        response = self.client.post(
            reverse("worship_rotation_planner"),
            {"events": [event.pk for event in events], "inserted_team": self.c2.pk},
        )
        self.assertContains(response, "Confirmable")
        self.assertContains(
            response, "Rotation cycle closes within the selected range"
        )
        self.assertContains(response, "No Worship Team is lost from this shift")
        self.assertContains(response, "Cycle closed by the inserted Worship Team")
        self.assertNotContains(response, "Review required")
        self.assertContains(response, "Confirm Shift")

        session = self.client.session
        session["language"] = "zh"
        session.save()
        response = self.client.post(
            reverse("worship_rotation_planner"),
            {"events": [event.pk for event in events], "inserted_team": self.c2.pk},
        )
        self.assertContains(response, "可确认")
        self.assertContains(response, "本次顺延在所选范围内完成轮值闭合")
        self.assertContains(response, "没有敬拜团队被遗漏")
        self.assertNotContains(response, "需要检查")

    def test_true_displaced_tail_remains_review_required_and_bilingual(self):
        team_a = self.team("Chinese Worship Team A", self.cm_pool)
        events = [self.event(3, self.c1), self.event(4, self.c2)]
        response = self.client.post(
            reverse("worship_rotation_planner"),
            {"events": [event.pk for event in events], "inserted_team": team_a.pk},
        )
        self.assertContains(response, "Review required")
        self.assertContains(
            response, "A Worship Team would be displaced after the selected range."
        )
        self.assertNotContains(response, "Rotation cycle closes")
        self.assertNotContains(response, "Confirm Shift")

        session = self.client.session
        session["language"] = "zh"
        session.save()
        response = self.client.post(
            reverse("worship_rotation_planner"),
            {"events": [event.pk for event in events], "inserted_team": team_a.pk},
        )
        self.assertContains(response, "需要检查")
        self.assertContains(response, "范围结束后仍有一个敬拜团队被顺延出范围")
        self.assertNotContains(response, "完成轮值闭合")

    def test_get_and_preview_post_are_zero_write_no_session_or_notification(self):
        payloads = []
        before = self.counts()
        session_before = dict(self.client.session)
        with notification_sink_override_for_tests(payloads.append):
            with self.captureOnCommitCallbacks(execute=True) as callbacks:
                get_response = self.client.get(reverse("worship_rotation_planner"))
                with patch("tempfile.NamedTemporaryFile") as temp_file:
                    post_response = self.client.post(
                        reverse("worship_rotation_planner"),
                        {
                            "events": [event.pk for event in self.events],
                            "inserted_team": self.c2.pk,
                        },
                    )
                    temp_file.assert_not_called()
        self.assertEqual(get_response.status_code, 200)
        self.assertEqual(post_response.status_code, 200)
        self.assertEqual(self.counts(), before)
        self.assertEqual(dict(self.client.session), session_before)
        self.assertEqual(payloads, [])
        self.assertEqual(callbacks, [])


class WorshipRotationConfirmationTests(WorshipRotationPlannerTestBase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.staff)

    def preview(self, events, *, inserted=None):
        response = self.client.post(
            reverse("worship_rotation_planner"),
            {
                "events": [event.pk for event in events],
                "inserted_team": (inserted or self.c2).pk,
            },
        )
        self.assertEqual(response.status_code, 200)
        return response.context["proposal"]

    def confirm(self, proposal, *, follow=False):
        return self.client.post(
            reverse("worship_rotation_planner_confirm"),
            {"proposal": proposal.signed_payload},
            follow=follow,
        )

    def event_truth(self, events):
        return list(
            ServiceEvent.objects.filter(pk__in=[event.pk for event in events])
            .order_by("start_datetime", "id")
            .values_list("rotation_anchor_team_id", "scheduling_revision")
        )

    def cross_domain_counts(self):
        return {
            model: model.objects.count()
            for model in (
                ServiceEventAudienceScope,
                ServiceEventRequiredTeam,
                ServiceEventPlannerAssignment,
                MinistryTeam,
                TeamAssignment,
                TeamAssignmentMember,
                TeamMembership,
                ChurchStructureMembership,
                Notification,
            )
        }

    def test_terminal_blank_confirmation_advances_all_and_shared_audits_changes(self):
        events = [self.event(0, self.c1), self.event(1, self.c2), self.event(2, None)]
        proposal = self.preview(events)

        response = self.confirm(proposal, follow=True)

        self.assertContains(response, "Worship rotation updated.")
        self.assertEqual(
            self.event_truth(events),
            [(self.c2.pk, 1), (self.c1.pk, 1), (self.c2.pk, 1)],
        )
        logs = list(LogEntry.objects.order_by("object_id"))
        self.assertEqual(len(logs), 3)
        for entry in logs:
            self.assertEqual(entry.user_id, self.staff.pk)
            self.assertIn("Worship Rotation Planner batch confirmation", entry.change_message)
            self.assertIn(f"operation_id={proposal.operation_id}", entry.change_message)

    def test_cycle_closed_confirmation_preserves_tail_and_advances_all(self):
        events = [self.event(0, self.c1), self.event(1, self.c2)]
        proposal = self.preview(events)

        self.confirm(proposal)

        self.assertEqual(
            self.event_truth(events),
            [(self.c2.pk, 1), (self.c1.pk, 1)],
        )
        self.assertEqual(LogEntry.objects.count(), 2)

    def test_noop_context_row_is_claimed_but_not_saved_or_audited(self):
        events = [
            self.event(0, self.c1),
            self.event(1, self.c2),
            self.event(2, self.c1),
        ]
        proposal = self.preview(events, inserted=self.c1)
        first_updated_at = events[0].updated_at

        self.confirm(proposal)

        for event in events:
            event.refresh_from_db()
        self.assertEqual(events[0].rotation_anchor_team, self.c1)
        self.assertEqual(events[0].updated_at, first_updated_at)
        self.assertEqual([event.scheduling_revision for event in events], [1, 1, 1])
        self.assertEqual(
            set(LogEntry.objects.values_list("object_id", flat=True)),
            {str(events[1].pk), str(events[2].pk)},
        )

    def test_batch_emits_once_per_recipient_and_excludes_noop_context(self):
        events = [
            self.event(0, self.c1),
            self.event(1, self.c2),
            self.event(2, self.c1),
        ]
        proposal = self.preview(events, inserted=self.c1)
        recipient = User.objects.create_user(username="batch_c1_lead")
        lead_type = MinistryTeamRoleType.objects.create(
            code=MinistryTeamRoleType.CODE_LEAD,
            name="Lead",
            name_en="Lead",
        )
        MinistryTeamRoleAssignment.objects.create(
            team=self.c1,
            role_type=lead_type,
            user=recipient,
            start_date=timezone.localdate(),
        )
        payloads = []

        with notification_sink_override_for_tests(payloads.append):
            with self.captureOnCommitCallbacks(execute=True) as callbacks:
                response = self.confirm(proposal)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(callbacks), 1)
        self.assertEqual(len(payloads), 1)
        payload = payloads[0]
        self.assertEqual(payload.recipient, recipient)
        self.assertEqual(payload.notification_type, "worship_rotation.changed")
        self.assertEqual(
            payload.dedupe_key,
            f"ministry:worship_rotation:{proposal.operation_id}",
        )
        self.assertEqual(payload.metadata["recipient_relevant_event_count"], 2)
        self.assertNotIn("3 Sundays", payload.body)

    def test_notification_persistence_failure_does_not_reverse_batch_commit(self):
        events = [self.event(0, self.c1), self.event(1, None)]
        proposal = self.preview(events)
        recipient = User.objects.create_user(username="failing_sink_lead")
        lead_type = MinistryTeamRoleType.objects.create(
            code=MinistryTeamRoleType.CODE_LEAD,
            name="Lead",
            name_en="Lead",
        )
        MinistryTeamRoleAssignment.objects.create(
            team=self.c1,
            role_type=lead_type,
            user=recipient,
            start_date=timezone.localdate(),
        )

        def failing_sink(_payload):
            raise RuntimeError("notification persistence unavailable")

        with notification_sink_override_for_tests(failing_sink):
            with self.assertLogs("core.notification_delivery", level="ERROR"):
                with self.captureOnCommitCallbacks(execute=True):
                    response = self.confirm(proposal)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            self.event_truth(events),
            [(self.c2.pk, 1), (self.c1.pk, 1)],
        )
        self.assertEqual(LogEntry.objects.count(), 2)

    @override_settings(CMS_ENABLED_MODULES=[])
    def test_batch_still_succeeds_when_notifications_are_disabled(self):
        events = [self.event(0, self.c1), self.event(1, None)]
        proposal = self.preview(events)
        recipient = User.objects.create_user(username="disabled_batch_lead")
        lead_type = MinistryTeamRoleType.objects.create(
            code=MinistryTeamRoleType.CODE_LEAD,
            name="Lead",
            name_en="Lead",
        )
        MinistryTeamRoleAssignment.objects.create(
            team=self.c1,
            role_type=lead_type,
            user=recipient,
            start_date=timezone.localdate(),
        )
        payloads = []

        with notification_sink_override_for_tests(payloads.append):
            with self.captureOnCommitCallbacks(execute=True) as callbacks:
                response = self.confirm(proposal)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            self.event_truth(events),
            [(self.c2.pk, 1), (self.c1.pk, 1)],
        )
        self.assertEqual(payloads, [])
        self.assertEqual(callbacks, [])

    def test_displaced_and_interior_blank_signed_proposals_cannot_confirm(self):
        team_a = self.team("Chinese Worship Team A", self.cm_pool)
        scenarios = (
            ([self.event(0, self.c1), self.event(1, self.c2)], team_a),
            ([self.event(3, self.c1), self.event(4, None), self.event(5, None)], self.c2),
        )
        for events, inserted in scenarios:
            with self.subTest(inserted=inserted.pk):
                proposal = self.preview(events, inserted=inserted)
                self.assertFalse(proposal.confirmable)
                response = self.confirm(proposal, follow=True)
                self.assertContains(response, "Generate a new preview")
                self.assertEqual(
                    [revision for _team, revision in self.event_truth(events)],
                    [0] * len(events),
                )
        self.assertEqual(LogEntry.objects.count(), 0)

    def test_stale_first_revision_rejects_without_additional_write(self):
        events = [self.event(0, self.c1), self.event(1, None)]
        proposal = self.preview(events)
        advance_scheduling_revisions((events[0].pk,))

        response = self.confirm(proposal, follow=True)

        self.assertContains(response, "Scheduling changed or is busy")
        self.assertEqual(self.event_truth(events), [(self.c1.pk, 1), (None, 0)])
        self.assertEqual(LogEntry.objects.count(), 0)

    def test_missing_or_stale_later_event_rolls_back_earlier_claim(self):
        first = self.event(0, self.c1)
        later = self.event(1, None)
        missing_proposal = self.preview([first, later])
        later.delete()
        self.confirm(missing_proposal)
        first.refresh_from_db()
        self.assertEqual(first.scheduling_revision, 0)

        later = self.event(3, None)
        first.start_datetime = self.first_sunday + timezone.timedelta(weeks=2)
        ServiceEvent.objects.filter(pk=first.pk).update(
            start_datetime=first.start_datetime,
            updated_at=timezone.now(),
        )
        stale_proposal = self.preview([first, later])
        advance_scheduling_revisions((later.pk,))
        self.confirm(stale_proposal)
        first.refresh_from_db()
        later.refresh_from_db()
        self.assertEqual(first.scheduling_revision, 0)
        self.assertEqual(later.scheduling_revision, 1)
        self.assertEqual(LogEntry.objects.count(), 0)

    def test_supported_downstream_and_required_team_changes_stale_confirmation(self):
        for week, mutation in (
            (
                0,
                lambda event: TeamAssignment.objects.create(
                    service_event=event,
                    ministry_team=self.sound,
                ),
            ),
            (
                3,
                lambda event: ServiceEventRequiredTeam.objects.create(
                    service_event=event,
                    ministry_team=self.projection,
                ),
            ),
        ):
            with self.subTest(week=week):
                events = [self.event(week, self.c1), self.event(week + 1, None)]
                proposal = self.preview(events)
                mutation(events[0])
                before = self.event_truth(events)
                self.confirm(proposal)
                self.assertEqual(self.event_truth(events), before)
        self.assertEqual(LogEntry.objects.count(), 0)

    def test_nonrevision_event_and_downstream_fingerprint_changes_roll_back(self):
        events = [self.event(0, self.c1), self.event(1, None)]
        proposal = self.preview(events)
        ServiceEvent.objects.filter(pk=events[0].pk).update(
            title="Changed outside supported save",
            updated_at=timezone.now(),
        )
        self.confirm(proposal)
        self.assertEqual(self.event_truth(events), [(self.c1.pk, 0), (None, 0)])

        events = [self.event(3, self.c1), self.event(4, None)]
        proposal = self.preview(events)
        TeamAssignment.objects.bulk_create(
            [TeamAssignment(service_event=events[0], ministry_team=self.sound)]
        )
        self.confirm(proposal)
        self.assertEqual(self.event_truth(events), [(self.c1.pk, 0), (None, 0)])
        self.assertEqual(LogEntry.objects.count(), 0)

    def test_unsupported_audience_or_pool_change_is_caught_by_recomputation(self):
        events = [self.event(0, self.c1), self.event(1, None)]
        proposal = self.preview(events)
        ServiceEventAudienceScope.objects.filter(service_event=events[0]).update(
            unit=self.em
        )
        self.confirm(proposal)
        self.assertEqual(self.event_truth(events), [(self.c1.pk, 0), (None, 0)])

        events = [self.event(3, self.c1), self.event(4, None)]
        proposal = self.preview(events)
        MinistryTeam.objects.filter(pk=self.cm_pool.pk).update(is_active=False)
        self.confirm(proposal)
        self.assertEqual(self.event_truth(events), [(self.c1.pk, 0), (None, 0)])
        self.assertEqual(LogEntry.objects.count(), 0)

    def test_authority_loss_and_new_worship_assignment_block_and_rollback(self):
        events = [self.event(0, self.c1), self.event(1, None)]
        for event in events:
            ServiceEventPlannerAssignment.objects.create(
                service_event=event,
                user=self.other,
            )
        proposal = self.proposal(events, user=self.other)
        ServiceEventPlannerAssignment.objects.filter(
            service_event=events[1], user=self.other
        ).update(is_active=False)
        self.client.force_login(self.other)
        self.confirm(proposal)
        self.assertEqual(self.event_truth(events), [(self.c1.pk, 0), (None, 0)])

        self.client.force_login(self.staff)
        events = [self.event(3, self.c1), self.event(4, None)]
        proposal = self.preview(events)
        self.stored_assignment(events[0], self.c1)
        self.confirm(proposal)
        self.assertEqual(self.event_truth(events), [(self.c1.pk, 0), (None, 0)])
        self.assertEqual(LogEntry.objects.count(), 0)

    def test_consistent_assignment_on_noop_row_remains_informational(self):
        events = [
            self.event(0, self.c1),
            self.event(1, self.c2),
            self.event(2, self.c1),
        ]
        self.stored_assignment(events[0], self.c1)
        proposal = self.preview(events, inserted=self.c1)
        self.assertTrue(proposal.confirmable)

        self.confirm(proposal)

        self.assertEqual([revision for _team, revision in self.event_truth(events)], [1, 1, 1])
        self.assertNotIn(
            str(events[0].pk),
            set(LogEntry.objects.values_list("object_id", flat=True)),
        )

    def test_wrong_user_expired_tampered_and_v2_tokens_reject_before_mutation(self):
        events = [self.event(0, self.c1), self.event(1, None)]
        proposal = self.preview(events)
        tokens = []
        tampered = proposal.signed_payload[:-1] + (
            "a" if proposal.signed_payload[-1] != "a" else "b"
        )
        tokens.append(tampered)
        for old_version in (1, 2):
            old_payload = dict(proposal.normalized_payload)
            old_payload["contract_version"] = old_version
            tokens.append(
                signing.dumps(
                    old_payload,
                    salt=PLANNER_SIGNING_SALT,
                    compress=True,
                )
            )
        for token in tokens:
            with self.subTest(token=token[-12:]):
                self.client.post(
                    reverse("worship_rotation_planner_confirm"),
                    {"proposal": token},
                )

        self.client.force_login(self.other)
        self.confirm(proposal)
        self.client.force_login(self.staff)
        with patch(
            "django.core.signing.time.time",
            return_value=stdlib_time.time() + 1801,
        ):
            self.confirm(proposal)
        self.assertEqual(self.event_truth(events), [(self.c1.pk, 0), (None, 0)])
        self.assertEqual(LogEntry.objects.count(), 0)

    def test_replay_is_stale_without_duplicate_audit_or_revision(self):
        events = [self.event(0, self.c1), self.event(1, None)]
        proposal = self.preview(events)
        self.confirm(proposal)
        after_first = self.event_truth(events)
        log_count = LogEntry.objects.count()

        response = self.confirm(proposal, follow=True)

        self.assertContains(response, "Generate a new preview")
        self.assertEqual(self.event_truth(events), after_first)
        self.assertEqual(LogEntry.objects.count(), log_count)

    def test_audit_failure_rolls_back_all_claims_anchors_and_audits(self):
        events = [self.event(0, self.c1), self.event(1, None)]
        proposal = self.preview(events)
        with patch(
            "ministry.services.worship_rotation_planner.LogEntry.objects.log_action",
            side_effect=RuntimeError("audit unavailable"),
        ):
            response = self.confirm(proposal, follow=True)

        self.assertContains(response, "Generate a new preview")
        self.assertEqual(self.event_truth(events), [(self.c1.pk, 0), (None, 0)])
        self.assertEqual(LogEntry.objects.count(), 0)

    def test_busy_cas_exits_transaction_before_safe_retry_response(self):
        events = [self.event(0, self.c1), self.event(1, None)]
        proposal = self.preview(events)
        with patch(
            "ministry.services.worship_rotation_planner.claim_scheduling_revisions",
            side_effect=SchedulingRevisionBusyError("database is locked"),
        ):
            response = self.confirm(proposal, follow=True)

        self.assertContains(response, "Scheduling changed or is busy")
        self.assertNotContains(response, "Worship rotation updated")
        self.assertEqual(self.event_truth(events), [(self.c1.pk, 0), (None, 0)])

        self.staff.profile.preferred_language = "zh"
        self.staff.profile.save(update_fields=["preferred_language"])
        self.client.logout()
        self.client.force_login(self.staff)
        with patch(
            "ministry.services.worship_rotation_planner.claim_scheduling_revisions",
            side_effect=SchedulingRevisionBusyError("database is locked"),
        ):
            response = self.confirm(proposal, follow=True)
        self.assertContains(
            response,
            "排班资料已有变化或系统正忙。请重新生成预览后再试。",
        )
        self.assertNotContains(response, "敬拜轮值已更新。")
        self.assertEqual(self.event_truth(events), [(self.c1.pk, 0), (None, 0)])

    def test_confirmation_performs_no_select_before_cas_claim(self):
        events = [self.event(0, self.c1), self.event(1, None)]
        proposal = self.preview(events)
        payload = decode_signed_worship_rotation_proposal(
            proposal.signed_payload,
            user=self.staff,
        )
        with patch(
            "ministry.services.worship_rotation_planner.claim_scheduling_revisions",
            side_effect=SchedulingRevisionBusyError("stop at first CAS"),
        ) as claim:
            with CaptureQueriesContext(connection) as queries:
                with self.assertRaises(SchedulingRevisionBusyError):
                    confirm_worship_rotation_proposal(
                        user=self.staff,
                        payload=payload,
                    )

        claim.assert_called_once()
        self.assertFalse(
            any(query["sql"].lstrip().upper().startswith("SELECT") for query in queries)
        )

    def test_success_has_zero_cross_domain_or_notification_effect(self):
        events = [self.event(0, self.c1), self.event(1, None)]
        proposal = self.preview(events)
        before = self.cross_domain_counts()
        payloads = []
        with notification_sink_override_for_tests(payloads.append):
            with self.captureOnCommitCallbacks(execute=True) as callbacks:
                self.confirm(proposal)

        self.assertEqual(self.cross_domain_counts(), before)
        self.assertEqual(payloads, [])
        self.assertEqual(callbacks, [])

    def test_confirmation_route_is_post_only_and_response_is_roster_private(self):
        get_response = self.client.get(reverse("worship_rotation_planner_confirm"))
        self.assertEqual(get_response.status_code, 405)

        events = [self.event(0, self.c1), self.event(1, None)]
        proposal = self.preview(events)
        membership = TeamMembership.objects.create(
            team=self.sound,
            display_name="PRIVATE CONFIRM MEMBER",
            email="private-confirm@example.com",
        )
        assignment = TeamAssignment.objects.create(
            service_event=events[0], ministry_team=self.sound
        )
        TeamAssignmentMember.objects.create(assignment=assignment, membership=membership)
        response = self.confirm(proposal, follow=True)
        self.assertNotContains(response, "PRIVATE CONFIRM MEMBER")
        self.assertNotContains(response, "private-confirm@example.com")


class FileBackedSQLiteWorshipRotationConfirmationTests(unittest.TestCase):
    """One target-like proof at the actual confirmation service boundary."""

    competing_alias = "worship_confirmation_competing"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        handle = tempfile.NamedTemporaryFile(
            prefix="worship-confirmation-",
            suffix=".sqlite3",
            delete=False,
        )
        cls.database_path = handle.name
        handle.close()
        cls.original_default_config = copy.deepcopy(
            connections.databases["default"]
        )
        connections["default"].close()
        if hasattr(connections._connections, "default"):
            delattr(connections._connections, "default")

        file_config = copy.deepcopy(cls.original_default_config)
        file_config["NAME"] = cls.database_path
        file_config["OPTIONS"] = {
            **file_config.get("OPTIONS", {}),
            "timeout": 0.1,
        }
        file_config["TEST"] = {"NAME": None}
        connections.databases["default"] = file_config
        call_command(
            "migrate",
            database="default",
            interactive=False,
            verbosity=0,
        )
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

    def test_confirmation_first_cas_excludes_competing_writer_until_commit(self):
        root = ChurchStructureUnit.objects.create(
            code="ROOT",
            name="Whole Church",
            name_en="Whole Church",
            unit_type=ChurchStructureUnit.UNIT_ROOT,
        )
        cm = ChurchStructureUnit.objects.create(
            code="CM",
            name="Chinese Ministry",
            name_en="Chinese Ministry",
            unit_type=ChurchStructureUnit.UNIT_MINISTRY_CONTEXT,
            parent=root,
        )
        pool = MinistryTeam.objects.create(
            name="Chinese Worship Pool",
            name_en="Chinese Worship Pool",
            is_assignable=False,
            is_worship_rotation_pool=True,
        )
        MinistryTeamParentLink.objects.create(
            child_team=pool,
            parent_church_unit=cm,
            is_primary=True,
        )
        c1 = MinistryTeam.objects.create(name="Worship C1", name_en="Worship C1")
        c2 = MinistryTeam.objects.create(name="Worship C2", name_en="Worship C2")
        for team in (c1, c2):
            MinistryTeamParentLink.objects.create(
                child_team=team,
                parent_team=pool,
                is_primary=True,
            )
        staff = User.objects.create_user(
            username="file_confirmation_staff",
            password="pw",
            is_staff=True,
        )
        today = timezone.localdate()
        days = (6 - today.weekday()) % 7 or 7
        first_start = timezone.make_aware(
            datetime.combine(today + timezone.timedelta(days=days), time(10, 0)),
            timezone.get_current_timezone(),
        )
        selected = []
        for week, team in ((0, c1), (1, None)):
            event = ServiceEvent.objects.create(
                title=f"Selected {week}",
                event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
                start_datetime=first_start + timezone.timedelta(weeks=week),
                status=ServiceEvent.STATUS_PUBLISHED,
                rotation_anchor_team=team,
            )
            ServiceEventAudienceScope.objects.create(service_event=event, unit=cm)
            selected.append(event)
        unrelated = ServiceEvent.objects.create(
            title="Unrelated writer target",
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
            start_datetime=first_start + timezone.timedelta(weeks=5),
            status=ServiceEvent.STATUS_PUBLISHED,
        )
        ServiceEventAudienceScope.objects.create(service_event=unrelated, unit=cm)
        proposal = build_worship_rotation_proposal(
            user=staff,
            event_ids=[event.pk for event in selected],
            inserted_team=c2,
        )
        payload = decode_signed_worship_rotation_proposal(
            proposal.signed_payload,
            user=staff,
        )
        original_build = planner_service.build_worship_rotation_proposal
        competing_busy = []

        def build_after_competing_write(*args, **kwargs):
            try:
                advance_scheduling_revisions(
                    (unrelated.pk,),
                    using=self.competing_alias,
                )
            except SchedulingRevisionBusyError:
                competing_busy.append(True)
            return original_build(*args, **kwargs)

        with patch.object(
            planner_service,
            "build_worship_rotation_proposal",
            side_effect=build_after_competing_write,
        ):
            result = confirm_worship_rotation_proposal(
                user=staff,
                payload=payload,
            )

        self.assertEqual(competing_busy, [True])
        self.assertEqual(result.claimed_event_ids, tuple(sorted(event.pk for event in selected)))
        self.assertEqual(
            list(
                ServiceEvent.objects.filter(pk__in=[event.pk for event in selected])
                .order_by("start_datetime", "id")
                .values_list("rotation_anchor_team_id", "scheduling_revision")
            ),
            [(c2.pk, 1), (c1.pk, 1)],
        )
        unrelated.refresh_from_db()
        self.assertEqual(unrelated.scheduling_revision, 0)
