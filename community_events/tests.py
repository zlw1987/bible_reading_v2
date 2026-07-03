from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from accounts.models import ChurchStructureMembership, ChurchStructureUnit
from ministry.models import TeamAssignment, TeamAssignmentMember
from studies.models import BibleStudyMeetingRole

from .models import CommunityActivity, CommunityActivityAudienceScope
from .visibility import visible_community_activities_for

User = get_user_model()


class CommunityActivityFoundationTests(TestCase):
    def setUp(self):
        self.root = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_ROOT,
            code="CHURCH",
            name="Whole Church",
        )
        self.parent = ChurchStructureUnit.objects.create(
            parent=self.root,
            unit_type=ChurchStructureUnit.UNIT_DISTRICT,
            code="NORTH",
            name="North",
        )
        self.child = ChurchStructureUnit.objects.create(
            parent=self.parent,
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="NORTH-1",
            name="North 1",
        )
        self.sibling = ChurchStructureUnit.objects.create(
            parent=self.root,
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="SOUTH-1",
            name="South 1",
        )
        self.direct_member = self.create_member("direct_member", self.parent)
        self.descendant_member = self.create_member("descendant_member", self.child)
        self.nonmatching_member = self.create_member(
            "nonmatching_member",
            self.sibling,
        )
        self.no_membership_user = User.objects.create_user(
            username="no_membership",
            password="testpass123",
        )
        self.staff = User.objects.create_user(
            username="activity_staff",
            password="testpass123",
            is_staff=True,
        )
        self.superuser = User.objects.create_superuser(
            username="activity_superuser",
            password="testpass123",
            email="superuser@example.com",
        )
        self.start_datetime = timezone.now() + timezone.timedelta(days=7)

    def create_member(self, username, unit, **membership_overrides):
        user = User.objects.create_user(
            username=username,
            password="testpass123",
        )
        membership_data = {
            "user": user,
            "unit": unit,
            "status": ChurchStructureMembership.STATUS_ACTIVE,
            "is_primary": True,
            "start_date": timezone.localdate() - timezone.timedelta(days=1),
        }
        membership_data.update(membership_overrides)
        ChurchStructureMembership.objects.create(**membership_data)
        return user

    def create_activity(self, **overrides):
        data = {
            "title": "社区活动",
            "title_en": "Community Activity",
            "description": "一起相聚",
            "description_en": "Gather together",
            "organizer": "Fellowship Team",
            "start_datetime": self.start_datetime,
            "location": "Fellowship Hall",
            "location_en": "Fellowship Hall",
            "status": CommunityActivity.STATUS_PUBLISHED,
        }
        data.update(overrides)
        return CommunityActivity.objects.create(**data)

    def add_audience(self, activity, unit):
        return CommunityActivityAudienceScope.objects.create(
            activity=activity,
            structure_unit=unit,
        )

    def test_matching_unit_and_descendant_memberships_are_visible(self):
        activity = self.create_activity()
        self.add_audience(activity, self.parent)

        self.assertTrue(activity.can_be_seen_by(self.direct_member))
        self.assertTrue(activity.can_be_seen_by(self.descendant_member))
        self.assertEqual(
            list(
                visible_community_activities_for(self.descendant_member).values_list(
                    "id",
                    flat=True,
                )
            ),
            [activity.id],
        )

    def test_nonmatching_audience_is_hidden(self):
        activity = self.create_activity()
        self.add_audience(activity, self.parent)

        self.assertFalse(activity.can_be_seen_by(self.nonmatching_member))

    def test_any_matching_audience_row_is_sufficient(self):
        activity = self.create_activity()
        self.add_audience(activity, self.sibling)
        self.add_audience(activity, self.parent)

        self.assertTrue(activity.can_be_seen_by(self.descendant_member))
        self.assertTrue(activity.can_be_seen_by(self.nonmatching_member))

    def test_zero_audience_rows_fail_closed_for_ordinary_users(self):
        activity = self.create_activity()

        self.assertFalse(activity.can_be_seen_by(self.direct_member))
        self.assertFalse(activity.can_be_seen_by(self.no_membership_user))

    def test_root_audience_still_requires_active_primary_membership(self):
        activity = self.create_activity()
        self.add_audience(activity, self.root)

        self.assertTrue(activity.can_be_seen_by(self.descendant_member))
        self.assertFalse(activity.can_be_seen_by(self.no_membership_user))

    def test_only_published_activities_are_visible_to_ordinary_users(self):
        for status in (
            CommunityActivity.STATUS_DRAFT,
            CommunityActivity.STATUS_CANCELLED,
            CommunityActivity.STATUS_COMPLETED,
        ):
            activity = self.create_activity(
                title=f"Activity {status}",
                status=status,
            )
            self.add_audience(activity, self.parent)
            self.assertFalse(
                activity.can_be_seen_by(self.direct_member),
                msg=f"{status} must be hidden from ordinary users",
            )

    def test_inactive_or_nonprimary_membership_does_not_grant_visibility(self):
        activity = self.create_activity()
        self.add_audience(activity, self.parent)
        inactive = self.create_member(
            "inactive_member",
            self.parent,
            status=ChurchStructureMembership.STATUS_ENDED,
            is_primary=False,
            end_date=timezone.localdate() - timezone.timedelta(days=1),
        )
        nonprimary = self.create_member(
            "nonprimary_member",
            self.parent,
            is_primary=False,
        )

        self.assertFalse(activity.can_be_seen_by(inactive))
        self.assertFalse(activity.can_be_seen_by(nonprimary))

    def test_staff_and_superuser_have_minimal_management_bypass(self):
        draft_without_audience = self.create_activity(
            status=CommunityActivity.STATUS_DRAFT,
        )

        self.assertTrue(draft_without_audience.can_be_seen_by(self.staff))
        self.assertTrue(draft_without_audience.can_be_seen_by(self.superuser))
        self.assertTrue(draft_without_audience.can_be_managed_by(self.staff))
        self.assertTrue(draft_without_audience.can_be_managed_by(self.superuser))
        self.assertFalse(draft_without_audience.can_be_managed_by(self.direct_member))

    def test_visibility_does_not_create_or_imply_serving_records(self):
        activity = self.create_activity()
        self.add_audience(activity, self.parent)

        self.assertTrue(activity.can_be_seen_by(self.descendant_member))
        self.assertEqual(TeamAssignment.objects.count(), 0)
        self.assertEqual(TeamAssignmentMember.objects.count(), 0)
        self.assertEqual(BibleStudyMeetingRole.objects.count(), 0)
        self.assertNotIn(
            "service_event",
            {field.name for field in CommunityActivity._meta.get_fields()},
        )

    def test_end_datetime_cannot_precede_start_datetime(self):
        with self.assertRaises(ValidationError):
            self.create_activity(
                end_datetime=self.start_datetime - timezone.timedelta(hours=1)
            )

    def test_audience_scope_requires_unique_active_nonoverlapping_units(self):
        activity = self.create_activity()
        self.add_audience(activity, self.parent)

        with self.assertRaises(ValidationError):
            self.add_audience(activity, self.parent)
        with self.assertRaises(ValidationError):
            self.add_audience(activity, self.child)

        inactive_unit = ChurchStructureUnit.objects.create(
            parent=self.root,
            unit_type=ChurchStructureUnit.UNIT_CUSTOM,
            code="INACTIVE",
            name="Inactive",
            is_active=False,
        )
        with self.assertRaises(ValidationError):
            self.add_audience(activity, inactive_unit)

    def test_admin_registers_activity_with_audience_inline(self):
        self.assertTrue(admin.site.is_registered(CommunityActivity))
