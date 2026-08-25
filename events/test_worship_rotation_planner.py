"""Focused MO-S.6D-1D-D-1A read-only planner tests."""

from datetime import datetime, time
from unittest.mock import patch

from django.contrib.admin.models import LogEntry
from django.contrib.auth.models import User
from django.core import signing
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import ChurchStructureMembership, ChurchStructureUnit
from core.notification_delivery import notification_sink_override_for_tests
from ministry.models import (
    MinistryTeam,
    MinistryTeamParentLink,
    TeamAssignment,
    TeamAssignmentMember,
    TeamMembership,
)
from ministry.services.worship_rotation_planner import (
    PlannerBlocker,
    SignedProposalError,
    SignedProposalUserMismatch,
    build_worship_rotation_proposal,
    decode_signed_worship_rotation_proposal,
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

    def test_non_null_tail_is_prominent_review_blocker(self):
        events = [self.event(0, self.c1), self.event(1, self.c2)]
        proposal = self.proposal(events)
        self.assertEqual(proposal.displaced_tail, self.c2)
        self.assertIn(PlannerBlocker.DISPLACED_TAIL, proposal.blockers)
        self.assertFalse(proposal.confirmable)

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
        events = [self.event(0, self.c1), self.event(1, self.c2), self.event(2, None)]
        ServiceEventPlannerAssignment.objects.create(service_event=events[0], user=self.other)
        ServiceEventPlannerAssignment.objects.create(service_event=events[2], user=self.other)
        proposal = self.proposal(events, user=self.other)
        self.assertIn(PlannerBlocker.UNAUTHORIZED, proposal.rows[1].blockers)
        self.assertFalse(proposal.confirmable)

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
            payload, compress=True, salt="ministry.worship-rotation-planner.v1"
        )
        with self.assertRaises(SignedProposalError):
            decode_signed_worship_rotation_proposal(wrong, user=self.staff)


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
        }

    def test_contextual_entry_and_bilingual_copy(self):
        response = self.client.get(reverse("worship_planning"))
        self.assertContains(response, "Rotation Planner")
        response = self.client.get(reverse("worship_rotation_planner"))
        self.assertContains(response, "Shift later Worship Teams")
        self.assertContains(response, "Generate Preview")
        self.assertContains(response, "Preview only")

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
        self.assertNotContains(response, "Confirm Shift")
        self.assertNotContains(response, "PRIVATE ROSTER NAME")
        self.assertNotContains(response, "private-roster@example.com")
        self.assertNotContains(response, "PRIVATE ASSIGNMENT NOTE")
        self.assertNotContains(response, "PRIVATE CONFIRMATION NOTE")

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
