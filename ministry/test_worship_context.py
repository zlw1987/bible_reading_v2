from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from accounts.models import ChurchStructureUnit
from events.models import ServiceEvent, ServiceEventAudienceScope

from .models import (
    MinistryTeam,
    MinistryTeamParentLink,
    TeamAssignment,
    TeamAssignmentMember,
    TeamMembership,
)
from .services.worship_context import (
    WORSHIP_CONTEXT_AMBIGUOUS,
    WORSHIP_CONTEXT_ANCHOR_UNAVAILABLE,
    WORSHIP_CONTEXT_CONFLICT,
    WORSHIP_CONTEXT_EMPTY,
    WORSHIP_CONTEXT_NO_ANCHOR,
    WORSHIP_CONTEXT_SCHEDULED,
    WORSHIP_CONTEXT_UNSCHEDULED,
    build_worship_contexts,
)
from .services.worship_governance import (
    WorshipOwnershipConsistencyState,
    inspect_worship_ownership_consistency,
)


User = get_user_model()


class WorshipContextProjectionTests(TestCase):
    def setUp(self):
        self.cm = ChurchStructureUnit.objects.create(
            code="CM",
            name="Chinese Ministry",
            name_en="Chinese Ministry",
            unit_type=ChurchStructureUnit.UNIT_MINISTRY_CONTEXT,
        )
        self.em = ChurchStructureUnit.objects.create(
            code="EM",
            name="English Ministry",
            name_en="English Ministry",
            unit_type=ChurchStructureUnit.UNIT_MINISTRY_CONTEXT,
        )
        self.pool = MinistryTeam.objects.create(
            name="Chinese Worship Pool",
            name_en="Chinese Worship Pool",
            is_assignable=False,
            is_worship_rotation_pool=True,
        )
        MinistryTeamParentLink.objects.create(
            child_team=self.pool,
            parent_church_unit=self.cm,
            is_primary=True,
        )
        self.anchor = MinistryTeam.objects.create(
            name="敬拜 C2",
            name_en="Worship C2",
        )
        MinistryTeamParentLink.objects.create(
            child_team=self.anchor,
            parent_team=self.pool,
            is_primary=True,
        )
        self.event = ServiceEvent.objects.create(
            title="主日崇拜",
            title_en="Sunday Service",
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
            start_datetime=timezone.now() + timezone.timedelta(days=3),
            status=ServiceEvent.STATUS_PUBLISHED,
            rotation_anchor_team=self.anchor,
        )
        ServiceEventAudienceScope.objects.create(
            service_event=self.event,
            unit=self.cm,
        )

    def create_assignment(self, *, status=TeamAssignment.STATUS_SCHEDULED):
        return TeamAssignment.objects.create(
            service_event=self.event,
            ministry_team=self.anchor,
            status=status,
            notes="Private Worship note",
        )

    def create_stored_assignment(self, *, status=TeamAssignment.STATUS_SCHEDULED):
        assignment = TeamAssignment(
            service_event=self.event,
            ministry_team=self.anchor,
            status=status,
            notes="Stored duplicate Worship note",
        )
        TeamAssignment.objects.bulk_create([assignment])
        return assignment

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
        second = self.create_stored_assignment(status=TeamAssignment.STATUS_PREPARED)
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

    def test_out_of_scope_assignment_projects_conflict_without_roster(self):
        membership = TeamMembership.objects.create(
            team=self.anchor,
            display_name="Private Out-of-Scope Worship Person",
        )
        assignment = self.create_assignment()
        TeamAssignmentMember.objects.create(
            assignment=assignment,
            membership=membership,
        )
        ServiceEventAudienceScope.objects.filter(service_event=self.event).update(
            unit=self.em
        )

        inspection = inspect_worship_ownership_consistency(self.event)
        context = self.context()

        self.assertEqual(
            inspection.state,
            WorshipOwnershipConsistencyState.OUT_OF_SCOPE_WORSHIP_CONFLICT,
        )
        self.assertEqual(context["state"], WORSHIP_CONTEXT_CONFLICT)
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
