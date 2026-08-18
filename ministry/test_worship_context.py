from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from events.models import ServiceEvent

from .models import (
    MinistryTeam,
    TeamAssignment,
    TeamAssignmentMember,
    TeamMembership,
)
from .services.worship_context import (
    WORSHIP_CONTEXT_AMBIGUOUS,
    WORSHIP_CONTEXT_ANCHOR_UNAVAILABLE,
    WORSHIP_CONTEXT_EMPTY,
    WORSHIP_CONTEXT_NO_ANCHOR,
    WORSHIP_CONTEXT_SCHEDULED,
    WORSHIP_CONTEXT_UNSCHEDULED,
    build_worship_contexts,
)


User = get_user_model()


class WorshipContextProjectionTests(TestCase):
    def setUp(self):
        self.anchor = MinistryTeam.objects.create(
            name="敬拜 C2",
            name_en="Worship C2",
        )
        self.event = ServiceEvent.objects.create(
            title="主日崇拜",
            title_en="Sunday Service",
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
            start_datetime=timezone.now() + timezone.timedelta(days=3),
            status=ServiceEvent.STATUS_PUBLISHED,
            rotation_anchor_team=self.anchor,
        )

    def create_assignment(self, *, status=TeamAssignment.STATUS_SCHEDULED):
        return TeamAssignment.objects.create(
            service_event=self.event,
            ministry_team=self.anchor,
            status=status,
            notes="Private Worship note",
        )

    def context(self):
        return build_worship_contexts([self.event])[self.event.id]

    def test_no_anchor_and_anchor_without_assignment_are_distinct(self):
        self.event.rotation_anchor_team = None
        self.event.save()
        self.assertEqual(self.context()["state"], WORSHIP_CONTEXT_NO_ANCHOR)

        self.event.rotation_anchor_team = self.anchor
        self.event.save()
        context = self.context()
        self.assertEqual(context["state"], WORSHIP_CONTEXT_UNSCHEDULED)
        self.assertEqual(context["anchor_team"], self.anchor)

    def test_one_current_assignment_projects_active_names_only(self):
        user = User.objects.create_user(
            username="worship_person",
            email="private-worship@example.com",
        )
        active_member = TeamMembership.objects.create(
            team=self.anchor,
            user=user,
        )
        inactive_member = TeamMembership.objects.create(
            team=self.anchor,
            display_name="Inactive Worship Person",
        )
        assignment = self.create_assignment()
        TeamAssignmentMember.objects.create(
            assignment=assignment,
            membership=active_member,
        )
        TeamAssignmentMember.objects.create(
            assignment=assignment,
            membership=inactive_member,
        )
        TeamMembership.objects.filter(id=inactive_member.id).update(is_active=False)

        context = self.context()

        self.assertEqual(context["state"], WORSHIP_CONTEXT_SCHEDULED)
        self.assertEqual(context["member_names"], ["worship_person"])
        self.assertNotIn("assignment", context)

    def test_empty_current_assignment_is_truthful(self):
        self.create_assignment()

        context = self.context()

        self.assertEqual(context["state"], WORSHIP_CONTEXT_EMPTY)
        self.assertEqual(context["member_names"], [])

    def test_cancelled_and_completed_assignments_are_not_current(self):
        self.create_assignment(status=TeamAssignment.STATUS_CANCELLED)
        self.create_assignment(status=TeamAssignment.STATUS_COMPLETED)

        self.assertEqual(self.context()["state"], WORSHIP_CONTEXT_UNSCHEDULED)

    def test_duplicate_current_assignments_fail_closed_without_roster(self):
        first_member = TeamMembership.objects.create(
            team=self.anchor,
            display_name="First Worship Person",
        )
        second_member = TeamMembership.objects.create(
            team=self.anchor,
            display_name="Second Worship Person",
        )
        first = self.create_assignment()
        second = self.create_assignment(status=TeamAssignment.STATUS_PREPARED)
        TeamAssignmentMember.objects.create(
            assignment=first,
            membership=first_member,
        )
        TeamAssignmentMember.objects.create(
            assignment=second,
            membership=second_member,
        )

        context = self.context()

        self.assertEqual(context["state"], WORSHIP_CONTEXT_AMBIGUOUS)
        self.assertEqual(context["member_names"], [])

    def test_inactive_or_nonassignable_anchor_fails_to_review_required(self):
        self.anchor.is_active = False
        self.anchor.save()
        self.assertEqual(
            self.context()["state"],
            WORSHIP_CONTEXT_ANCHOR_UNAVAILABLE,
        )

        self.anchor.is_active = True
        self.anchor.is_assignable = False
        self.anchor.save()
        self.assertEqual(
            self.context()["state"],
            WORSHIP_CONTEXT_ANCHOR_UNAVAILABLE,
        )
