from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import ChurchStructureMembership, ChurchStructureUnit
from ministry.models import TeamAssignment, TeamAssignmentMember
from studies.models import BibleStudyMeetingRole

from .models import (
    ActivitySignup,
    CommunityActivity,
    CommunityActivityAudienceScope,
)
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


# Enabled-module set with community_events removed. It has no dependents and no
# module dependencies, so dropping it alone stays dependency-valid.
_WITHOUT_COMMUNITY_EVENTS = [
    "reading",
    "prayers",
    "studies",
    "events",
    "ministry",
]


class CommunityActivityWebTestBase(TestCase):
    """Shared structure/members/activity fixtures for the 1B browse entrance."""

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
        self.member = self.create_member("browse_member", self.parent)
        self.other_member = self.create_member("browse_other", self.sibling)
        self.no_membership = User.objects.create_user(
            username="browse_no_membership",
            password="testpass123",
        )
        self.staff = User.objects.create_user(
            username="browse_staff",
            password="testpass123",
            is_staff=True,
        )
        self.start_datetime = timezone.now() + timezone.timedelta(days=7)

    def create_member(self, username, unit, **membership_overrides):
        user = User.objects.create_user(username=username, password="testpass123")
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
            "title_en": "Fellowship Picnic",
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

    def login(self, user, language="en"):
        self.client.force_login(user)
        session = self.client.session
        session["language"] = language
        session.save()


class CommunityActivityBrowseTests(CommunityActivityWebTestBase):
    @property
    def list_url(self):
        return reverse("community_activity_list")

    def detail_url(self, activity):
        return reverse("community_activity_detail", args=[activity.id])

    def test_list_requires_authenticated_user(self):
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)

    def test_list_loads_for_authenticated_user(self):
        self.login(self.member)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, 200)

    def test_list_shows_matching_visible_published_activity(self):
        activity = self.create_activity()
        self.add_audience(activity, self.parent)
        self.login(self.member)

        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Fellowship Picnic")
        self.assertContains(response, self.detail_url(activity))

    def test_list_hides_nonmatching_activity(self):
        activity = self.create_activity()
        self.add_audience(activity, self.parent)
        self.login(self.other_member)

        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Fellowship Picnic")

    def test_list_hides_zero_audience_activity_from_ordinary_user(self):
        self.create_activity()
        self.login(self.member)

        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Fellowship Picnic")

    def test_list_hides_draft_cancelled_completed_from_ordinary_user(self):
        for status in (
            CommunityActivity.STATUS_DRAFT,
            CommunityActivity.STATUS_CANCELLED,
            CommunityActivity.STATUS_COMPLETED,
        ):
            activity = self.create_activity(
                title_en=f"Hidden {status}",
                status=status,
            )
            self.add_audience(activity, self.parent)
        self.login(self.member)

        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, 200)
        for status in ("draft", "cancelled", "completed"):
            self.assertNotContains(response, f"Hidden {status}")

    def test_list_hides_past_activity(self):
        activity = self.create_activity(
            title_en="Past Picnic",
            start_datetime=timezone.now() - timezone.timedelta(days=1),
        )
        self.add_audience(activity, self.parent)
        self.login(self.member)

        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Past Picnic")

    def test_list_contributes_no_today_or_my_serving_surface(self):
        self.login(self.member)
        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, 200)
        # The browse entrance is independent: it must not pull in Today or
        # My Serving context keys.
        for leaked_key in (
            "today_items",
            "today_gatherings",
            "serving_summary",
            "leader_summary",
        ):
            self.assertNotIn(leaked_key, response.context)

    def test_list_shows_no_signup_affordance(self):
        activity = self.create_activity()
        self.add_audience(activity, self.parent)
        self.login(self.member)

        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        for signup_word in ("RSVP", "Join now", "Sign up for", "Register for"):
            self.assertNotIn(signup_word, content)

    def test_detail_shows_matching_visible_activity(self):
        activity = self.create_activity()
        self.add_audience(activity, self.parent)
        self.login(self.member)

        response = self.client.get(self.detail_url(activity))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Fellowship Picnic")
        self.assertContains(response, "Sign up")

    def test_detail_denies_nonmatching_activity_with_404(self):
        activity = self.create_activity()
        self.add_audience(activity, self.parent)
        self.login(self.other_member)

        response = self.client.get(self.detail_url(activity))

        self.assertEqual(response.status_code, 404)

    def test_detail_denies_zero_audience_activity_with_404(self):
        activity = self.create_activity()
        self.login(self.member)

        response = self.client.get(self.detail_url(activity))

        self.assertEqual(response.status_code, 404)

    def test_staff_can_browse_and_open_draft_activity(self):
        activity = self.create_activity(
            title_en="Draft Retreat",
            status=CommunityActivity.STATUS_DRAFT,
        )
        self.login(self.staff)

        list_response = self.client.get(self.list_url)
        detail_response = self.client.get(self.detail_url(activity))

        self.assertEqual(list_response.status_code, 200)
        self.assertContains(list_response, "Draft Retreat")
        self.assertEqual(detail_response.status_code, 200)

    @override_settings(CMS_ENABLED_MODULES=_WITHOUT_COMMUNITY_EVENTS)
    def test_direct_list_route_is_not_route_hard_off_when_module_disabled(self):
        # MODULAR-CORE gating hides surfaces only. The list route stays
        # reachable under its own login/visibility rules even when the module
        # is disabled; an ordinary user simply sees the calm empty state.
        activity = self.create_activity()
        self.add_audience(activity, self.parent)
        self.login(self.member)

        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Fellowship Picnic")


class CommunityActivityNavTests(CommunityActivityWebTestBase):
    def nav_href(self, url_name):
        return 'href="%s"' % reverse(url_name)

    def test_activities_nav_link_appears_when_module_enabled(self):
        self.login(self.member, language="en")
        response = self.client.get(reverse("profile"))

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn(self.nav_href("community_activity_list"), content)
        self.assertIn("Activities", content)

    def test_activities_nav_link_renders_chinese_label(self):
        self.login(self.member, language="zh")
        response = self.client.get(reverse("profile"))

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn(self.nav_href("community_activity_list"), content)
        self.assertIn("活动", content)

    @override_settings(CMS_ENABLED_MODULES=_WITHOUT_COMMUNITY_EVENTS)
    def test_activities_nav_link_hidden_when_module_disabled(self):
        self.login(self.member, language="en")
        response = self.client.get(reverse("profile"))

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertNotIn(self.nav_href("community_activity_list"), content)
        # Unrelated primary nav (home) still renders.
        self.assertIn(self.nav_href("home"), content)

    def test_list_page_marks_community_events_nav_active(self):
        self.login(self.member, language="en")
        response = self.client.get(reverse("community_activity_list"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["active_nav"], "community_events")

    @override_settings(CMS_ENABLED_MODULES=_WITHOUT_COMMUNITY_EVENTS)
    def test_disabling_community_events_does_not_crash_home_or_profile(self):
        self.login(self.member, language="en")
        for url_name in ("home", "profile"):
            with self.subTest(url_name=url_name):
                response = self.client.get(reverse(url_name))
                self.assertEqual(response.status_code, 200)


class ActivitySignupTests(CommunityActivityWebTestBase):
    def signup_url(self, activity):
        return reverse("community_activity_signup", args=[activity.id])

    def cancel_url(self, activity):
        return reverse("community_activity_cancel_signup", args=[activity.id])

    def detail_url(self, activity):
        return reverse("community_activity_detail", args=[activity.id])

    def test_signup_requires_authenticated_user(self):
        activity = self.create_activity()
        self.add_audience(activity, self.parent)

        response = self.client.post(self.signup_url(activity))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)
        self.assertEqual(ActivitySignup.objects.count(), 0)

    def test_visible_member_can_sign_up_once(self):
        activity = self.create_activity()
        self.add_audience(activity, self.parent)
        self.login(self.member)

        first_response = self.client.post(self.signup_url(activity))
        second_response = self.client.post(self.signup_url(activity))

        self.assertRedirects(first_response, self.detail_url(activity))
        self.assertRedirects(second_response, self.detail_url(activity))
        signup = ActivitySignup.objects.get(
            activity=activity,
            user=self.member,
        )
        self.assertEqual(signup.status, ActivitySignup.STATUS_SIGNED_UP)
        self.assertEqual(ActivitySignup.objects.count(), 1)
        self.assertTrue(signup.is_active)
        self.assertEqual(activity.active_signup_count(), 1)

    def test_signed_up_member_can_cancel_and_reactivate_same_row(self):
        activity = self.create_activity()
        self.add_audience(activity, self.parent)
        signup = ActivitySignup.objects.create(
            activity=activity,
            user=self.member,
        )
        original_id = signup.id
        self.login(self.member)

        cancel_response = self.client.post(self.cancel_url(activity))
        signup.refresh_from_db()

        self.assertRedirects(cancel_response, self.detail_url(activity))
        self.assertEqual(signup.status, ActivitySignup.STATUS_CANCELLED)
        self.assertEqual(activity.active_signup_count(), 0)

        signup_response = self.client.post(self.signup_url(activity))
        signup.refresh_from_db()

        self.assertRedirects(signup_response, self.detail_url(activity))
        self.assertEqual(signup.id, original_id)
        self.assertEqual(signup.status, ActivitySignup.STATUS_SIGNED_UP)
        self.assertEqual(ActivitySignup.objects.count(), 1)

    def test_signup_denies_nonmatching_and_zero_audience_activities(self):
        nonmatching = self.create_activity(title_en="Other group activity")
        self.add_audience(nonmatching, self.sibling)
        zero_audience = self.create_activity(title_en="No audience activity")
        self.login(self.member)

        for activity in (nonmatching, zero_audience):
            with self.subTest(activity=activity.title_en):
                response = self.client.post(self.signup_url(activity))
                self.assertEqual(response.status_code, 404)

        self.assertEqual(ActivitySignup.objects.count(), 0)

    def test_signup_denies_nonpublished_activities_even_for_staff(self):
        self.login(self.staff)

        for status in (
            CommunityActivity.STATUS_DRAFT,
            CommunityActivity.STATUS_CANCELLED,
            CommunityActivity.STATUS_COMPLETED,
        ):
            with self.subTest(status=status):
                activity = self.create_activity(status=status)
                response = self.client.post(self.signup_url(activity))
                self.assertEqual(response.status_code, 404)

        self.assertEqual(ActivitySignup.objects.count(), 0)

    def test_signup_denies_past_activity(self):
        activity = self.create_activity(
            start_datetime=timezone.now() - timezone.timedelta(minutes=1),
        )
        self.add_audience(activity, self.parent)
        self.login(self.member)

        response = self.client.post(self.signup_url(activity))

        self.assertEqual(response.status_code, 404)
        self.assertEqual(ActivitySignup.objects.count(), 0)

    def test_detail_shows_signup_and_signed_up_states(self):
        activity = self.create_activity()
        self.add_audience(activity, self.parent)
        self.login(self.member)

        available_response = self.client.get(self.detail_url(activity))

        self.assertContains(available_response, "Sign up")
        self.assertContains(available_response, self.signup_url(activity))
        self.assertNotContains(available_response, "Cancel signup")

        ActivitySignup.objects.create(
            activity=activity,
            user=self.member,
        )
        signed_up_response = self.client.get(self.detail_url(activity))

        self.assertContains(signed_up_response, "You’re signed up")
        self.assertContains(signed_up_response, "Cancel signup")
        self.assertContains(signed_up_response, self.cancel_url(activity))

    def test_list_marks_signed_up_activity(self):
        activity = self.create_activity()
        self.add_audience(activity, self.parent)
        ActivitySignup.objects.create(
            activity=activity,
            user=self.member,
        )
        self.login(self.member)

        response = self.client.get(reverse("community_activity_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Signed up")

    def test_signup_lifecycle_does_not_create_serving_or_shared_surface_state(self):
        activity = self.create_activity()
        self.add_audience(activity, self.parent)
        self.login(self.member)

        self.client.post(self.signup_url(activity))
        detail_response = self.client.get(self.detail_url(activity))
        self.client.post(self.cancel_url(activity))

        self.assertEqual(TeamAssignment.objects.count(), 0)
        self.assertEqual(TeamAssignmentMember.objects.count(), 0)
        self.assertEqual(BibleStudyMeetingRole.objects.count(), 0)
        for leaked_key in (
            "today_items",
            "today_gatherings",
            "serving_summary",
            "leader_summary",
        ):
            self.assertNotIn(leaked_key, detail_response.context)
        self.assertNotIn(
            "service_event",
            {field.name for field in ActivitySignup._meta.get_fields()},
        )
