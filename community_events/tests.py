from datetime import datetime
from unittest.mock import patch

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
    CommunityActivitySubmissionBlock,
)
from .today_provider import TODAY_DEFAULTS as COMMUNITY_ACTIVITY_TODAY_DEFAULTS
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
            CommunityActivity.STATUS_PENDING_REVIEW,
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
        self.assertTrue(admin.site.is_registered(ActivitySignup))
        self.assertTrue(admin.site.is_registered(CommunityActivitySubmissionBlock))


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

    def test_creator_published_activity_appears_once_in_visible_list_only(self):
        activity = self.create_activity(created_by=self.member)
        self.add_audience(activity, self.parent)
        self.login(self.member)

        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Fellowship Picnic", count=1)
        self.assertIn(activity, response.context["activities"])
        self.assertNotIn(activity, response.context["submitted_activities"])
        self.assertNotContains(response, "Your activity submissions")

    def test_creator_pending_activity_appears_in_submissions_not_visible_list(self):
        activity = self.create_activity(
            title_en="Pending Creator Picnic",
            status=CommunityActivity.STATUS_PENDING_REVIEW,
            created_by=self.member,
        )
        self.add_audience(activity, self.parent)
        self.login(self.member)

        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Your activity submissions")
        self.assertContains(response, "Pending Creator Picnic", count=1)
        self.assertIn(activity, response.context["submitted_activities"])
        self.assertNotIn(activity, response.context["activities"])

    def test_submissions_only_include_workflow_attention_statuses(self):
        activities_by_status = {
            status: self.create_activity(
                title_en=f"Creator {status}",
                status=status,
                created_by=self.member,
            )
            for status in (
                CommunityActivity.STATUS_DRAFT,
                CommunityActivity.STATUS_PENDING_REVIEW,
                CommunityActivity.STATUS_CHANGES_REQUESTED,
                CommunityActivity.STATUS_PUBLISHED,
                CommunityActivity.STATUS_CANCELLED,
                CommunityActivity.STATUS_COMPLETED,
            )
        }
        self.login(self.member)

        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            set(response.context["submitted_activities"]),
            {
                activities_by_status[CommunityActivity.STATUS_PENDING_REVIEW],
                activities_by_status[CommunityActivity.STATUS_CHANGES_REQUESTED],
                activities_by_status[CommunityActivity.STATUS_CANCELLED],
            },
        )

    def test_published_activity_remains_visible_to_in_scope_member(self):
        activity = self.create_activity(title_en="Visible Published Picnic")
        self.add_audience(activity, self.parent)
        self.login(self.member)

        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Visible Published Picnic", count=1)
        self.assertIn(activity, response.context["activities"])

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
            CommunityActivity.STATUS_PENDING_REVIEW,
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
        for status in ("draft", "pending_review", "cancelled", "completed"):
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


class CommunityActivitySubmissionTests(CommunityActivityWebTestBase):
    @property
    def create_url(self):
        return reverse("community_activity_create")

    def detail_url(self, activity):
        return reverse("community_activity_detail", args=[activity.id])

    def submission_data(self, **overrides):
        data = {
            "title": "成员野餐",
            "title_en": "Member Picnic",
            "description": "一起吃饭",
            "description_en": "Share a meal together",
            "organizer": "Community Member",
            "start_datetime": timezone.localtime(self.start_datetime).strftime(
                "%Y-%m-%dT%H:%M"
            ),
            "end_datetime": "",
            "location": "公园",
            "location_en": "Park",
            "audience_units": [self.parent.id],
            "requested_audience_note": "I hope this can include North District.",
        }
        data.update(overrides)
        return data

    def test_create_page_shows_activity_scope_and_note_labels(self):
        for language, scope_label, note_label in (
            ("en", "Activity scope", "Activity scope note (optional)"),
            ("zh", "活动范围", "活动范围说明（可选）"),
        ):
            with self.subTest(language=language):
                self.login(self.member, language=language)

                response = self.client.get(self.create_url)

                self.assertEqual(response.status_code, 200)
                self.assertContains(response, scope_label)
                self.assertContains(response, note_label)
                self.assertNotContains(response, "期望参加范围")
                self.assertContains(response, 'name="audience_units"')
                self.assertContains(response, 'name="requested_audience_note"')
                for excluded_field in ("status", "created_by"):
                    self.assertNotContains(response, f'name="{excluded_field}"')

    def test_unauthenticated_user_is_redirected_to_login(self):
        response = self.client.get(self.create_url)

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)

    def test_user_without_active_primary_membership_cannot_submit(self):
        self.login(self.no_membership)

        get_response = self.client.get(self.create_url)
        post_response = self.client.post(
            self.create_url,
            self.submission_data(),
        )

        self.assertEqual(get_response.status_code, 403)
        self.assertEqual(post_response.status_code, 403)
        self.assertEqual(CommunityActivity.objects.count(), 0)

    def test_active_blocked_user_cannot_submit(self):
        CommunityActivitySubmissionBlock.objects.create(
            user=self.member,
            reason="Staff review required before future submissions.",
            created_by=self.staff,
        )
        self.login(self.member)

        get_response = self.client.get(self.create_url)
        post_response = self.client.post(
            self.create_url,
            self.submission_data(),
        )

        self.assertEqual(get_response.status_code, 403)
        self.assertEqual(post_response.status_code, 403)
        self.assertEqual(CommunityActivity.objects.count(), 0)

    def test_valid_submission_is_pending_creator_owned_and_saves_selected_scope(self):
        self.login(self.member)

        response = self.client.post(
            self.create_url,
            self.submission_data(audience_units=[self.child.id]),
        )

        activity = CommunityActivity.objects.get(title_en="Member Picnic")
        self.assertRedirects(response, self.detail_url(activity))
        self.assertEqual(
            activity.status,
            CommunityActivity.STATUS_PENDING_REVIEW,
        )
        self.assertEqual(activity.created_by, self.member)
        self.assertEqual(
            activity.requested_audience_note,
            "I hope this can include North District.",
        )
        self.assertEqual(activity.audience_scope_links.count(), 1)
        self.assertEqual(
            activity.audience_scope_links.get().structure_unit,
            self.child,
        )
        self.assertEqual(TeamAssignment.objects.count(), 0)
        self.assertEqual(TeamAssignmentMember.objects.count(), 0)
        self.assertEqual(BibleStudyMeetingRole.objects.count(), 0)

    def test_valid_submission_can_select_whole_church_root(self):
        self.login(self.member)

        response = self.client.post(
            self.create_url,
            self.submission_data(
                title_en="Whole Church Picnic",
                audience_units=[self.root.id],
            ),
        )

        activity = CommunityActivity.objects.get(title_en="Whole Church Picnic")
        self.assertRedirects(response, self.detail_url(activity))
        self.assertEqual(
            list(
                activity.audience_scope_links.values_list(
                    "structure_unit_id",
                    flat=True,
                )
            ),
            [self.root.id],
        )

    def test_valid_submission_saves_multiple_nonoverlapping_scope_rows(self):
        self.login(self.member)

        response = self.client.post(
            self.create_url,
            self.submission_data(
                title_en="Two Branch Picnic",
                audience_units=[self.parent.id, self.sibling.id],
            ),
        )

        activity = CommunityActivity.objects.get(title_en="Two Branch Picnic")
        self.assertRedirects(response, self.detail_url(activity))
        self.assertEqual(
            set(
                activity.audience_scope_links.values_list(
                    "structure_unit_id",
                    flat=True,
                )
            ),
            {self.parent.id, self.sibling.id},
        )

    def test_submission_requires_at_least_one_audience_unit(self):
        self.login(self.member)

        response = self.client.post(
            self.create_url,
            self.submission_data(audience_units=[]),
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("audience_units", response.context["form"].errors)
        self.assertEqual(CommunityActivity.objects.count(), 0)
        self.assertEqual(CommunityActivityAudienceScope.objects.count(), 0)

    def test_submission_rejects_inactive_audience_unit(self):
        inactive = ChurchStructureUnit.objects.create(
            parent=self.root,
            unit_type=ChurchStructureUnit.UNIT_CUSTOM,
            code="INACTIVE-ACTIVITY",
            name="Inactive Activity Unit",
            is_active=False,
        )
        self.login(self.member)

        response = self.client.post(
            self.create_url,
            self.submission_data(audience_units=[inactive.id]),
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("audience_units", response.context["form"].errors)
        self.assertEqual(CommunityActivity.objects.count(), 0)

    def test_submission_rejects_unknown_audience_unit_id(self):
        self.login(self.member)
        unknown_id = ChurchStructureUnit.objects.order_by("-id").first().id + 1000

        response = self.client.post(
            self.create_url,
            self.submission_data(audience_units=[unknown_id]),
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("audience_units", response.context["form"].errors)
        self.assertEqual(CommunityActivity.objects.count(), 0)

    def test_submission_rejects_ancestor_descendant_overlap(self):
        self.login(self.member)

        response = self.client.post(
            self.create_url,
            self.submission_data(audience_units=[self.parent.id, self.child.id]),
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("audience_units", response.context["form"].errors)
        self.assertEqual(CommunityActivity.objects.count(), 0)
        self.assertEqual(CommunityActivityAudienceScope.objects.count(), 0)

    def test_creator_can_see_pending_detail_and_submission_status(self):
        activity = self.create_activity(
            title_en="Pending Picnic",
            status=CommunityActivity.STATUS_PENDING_REVIEW,
            created_by=self.member,
        )
        self.add_audience(activity, self.parent)
        self.login(self.member)

        detail_response = self.client.get(self.detail_url(activity))
        list_response = self.client.get(reverse("community_activity_list"))

        self.assertEqual(detail_response.status_code, 200)
        self.assertContains(detail_response, "Pending review")
        self.assertContains(detail_response, "awaiting staff review")
        self.assertContains(list_response, "Your activity submissions")
        self.assertContains(list_response, "Pending Picnic")

    def test_other_member_inside_selected_scope_cannot_see_pending_activity(self):
        in_scope_member = self.create_member("pending_in_scope", self.child)
        activity = self.create_activity(
            title_en="Private Pending Picnic",
            status=CommunityActivity.STATUS_PENDING_REVIEW,
            created_by=self.member,
        )
        self.add_audience(activity, self.parent)
        self.login(in_scope_member)

        detail_response = self.client.get(self.detail_url(activity))
        list_response = self.client.get(reverse("community_activity_list"))

        self.assertEqual(detail_response.status_code, 404)
        self.assertNotContains(list_response, "Private Pending Picnic")
        self.assertFalse(
            visible_community_activities_for(in_scope_member)
            .filter(id=activity.id)
            .exists()
        )

    def test_staff_and_superuser_can_see_pending_activity(self):
        activity = self.create_activity(
            title_en="Staff Review Picnic",
            status=CommunityActivity.STATUS_PENDING_REVIEW,
            created_by=self.member,
        )
        self.add_audience(activity, self.parent)
        superuser = User.objects.create_superuser(
            username="activity_submission_superuser",
            password="testpass123",
            email="activity-superuser@example.com",
        )

        for user in (self.staff, superuser):
            with self.subTest(username=user.username):
                self.login(user)
                detail_response = self.client.get(self.detail_url(activity))
                list_response = self.client.get(reverse("community_activity_list"))

                self.assertEqual(detail_response.status_code, 200)
                self.assertContains(list_response, "Staff Review Picnic")

    def test_pending_activity_has_no_signup_action_and_signup_post_is_denied(self):
        activity = self.create_activity(
            title_en="Pending Signup Picnic",
            status=CommunityActivity.STATUS_PENDING_REVIEW,
            created_by=self.member,
        )
        self.add_audience(activity, self.parent)
        self.login(self.member)

        detail_response = self.client.get(self.detail_url(activity))
        signup_response = self.client.post(
            reverse("community_activity_signup", args=[activity.id])
        )

        self.assertEqual(detail_response.status_code, 200)
        self.assertNotContains(
            detail_response,
            reverse("community_activity_signup", args=[activity.id]),
        )
        self.assertEqual(signup_response.status_code, 404)
        self.assertEqual(ActivitySignup.objects.count(), 0)


class CommunityActivityReviewInboxTests(CommunityActivityWebTestBase):
    @property
    def review_list_url(self):
        return reverse("community_activity_review_list")

    def review_detail_url(self, activity):
        return reverse("community_activity_review_detail", args=[activity.id])

    def publish_url(self, activity):
        return reverse("community_activity_review_publish", args=[activity.id])

    def request_changes_url(self, activity):
        return reverse(
            "community_activity_review_request_changes",
            args=[activity.id],
        )

    def cancel_url(self, activity):
        return reverse("community_activity_review_cancel", args=[activity.id])

    def detail_url(self, activity):
        return reverse("community_activity_detail", args=[activity.id])

    def pending_activity(self, **overrides):
        data = {
            "title_en": "Pending Review Picnic",
            "status": CommunityActivity.STATUS_PENDING_REVIEW,
            "created_by": self.member,
        }
        data.update(overrides)
        activity = self.create_activity(**data)
        self.add_audience(activity, self.parent)
        return activity

    def test_staff_can_open_review_inbox(self):
        self.login(self.staff)
        response = self.client.get(self.review_list_url)
        self.assertEqual(response.status_code, 200)

    def test_superuser_can_open_review_inbox(self):
        superuser = User.objects.create_superuser(
            username="review_superuser",
            password="testpass123",
            email="review-superuser@example.com",
        )
        self.login(superuser)
        response = self.client.get(self.review_list_url)
        self.assertEqual(response.status_code, 200)

    def test_ordinary_user_cannot_open_review_inbox(self):
        self.login(self.member)
        response = self.client.get(self.review_list_url)
        self.assertNotEqual(response.status_code, 200)

    def test_review_inbox_shows_pending_and_changes_requested(self):
        pending = self.pending_activity(title_en="Inbox Pending")
        changes = self.pending_activity(
            title_en="Inbox Changes",
            status=CommunityActivity.STATUS_CHANGES_REQUESTED,
            review_note="Please adjust the time.",
        )
        self.login(self.staff)

        response = self.client.get(self.review_list_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Inbox Pending")
        self.assertContains(response, "Inbox Changes")
        self.assertContains(response, self.review_detail_url(pending))
        self.assertContains(response, self.review_detail_url(changes))

    def test_review_inbox_excludes_published_and_draft(self):
        self.create_activity(
            title_en="Published Hidden From Inbox",
            status=CommunityActivity.STATUS_PUBLISHED,
        )
        self.create_activity(
            title_en="Draft Hidden From Inbox",
            status=CommunityActivity.STATUS_DRAFT,
        )
        self.login(self.staff)

        response = self.client.get(self.review_list_url)

        self.assertNotContains(response, "Published Hidden From Inbox")
        self.assertNotContains(response, "Draft Hidden From Inbox")

    def test_review_detail_shows_actions_for_pending_review(self):
        activity = self.pending_activity()
        self.login(self.staff)

        response = self.client.get(self.review_detail_url(activity))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Review actions")
        self.assertContains(response, self.publish_url(activity))
        self.assertContains(response, self.request_changes_url(activity))
        self.assertContains(response, self.cancel_url(activity))
        self.assertNotContains(response, "no longer awaiting review")
        self.assertNotContains(response, "Changes have already been requested")

    def test_review_detail_shows_actions_for_changes_requested(self):
        activity = self.pending_activity(
            status=CommunityActivity.STATUS_CHANGES_REQUESTED,
            review_note="Please adjust.",
        )
        self.login(self.staff)

        response = self.client.get(self.review_detail_url(activity))

        self.assertEqual(response.status_code, 200)
        # Publish and Cancel stay available for changes_requested; the
        # request-changes form is hidden because changes were already asked
        # for and the activity is waiting for the creator to resubmit.
        self.assertContains(response, "Review actions")
        self.assertContains(response, self.publish_url(activity))
        self.assertContains(response, self.cancel_url(activity))
        self.assertNotContains(response, self.request_changes_url(activity))
        self.assertContains(response, "Changes have already been requested")

    def test_review_detail_hides_actions_after_publish(self):
        activity = self.pending_activity()
        self.login(self.staff)
        self.client.post(self.publish_url(activity))

        response = self.client.get(self.review_detail_url(activity))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Review actions")
        self.assertNotContains(response, self.publish_url(activity))
        self.assertNotContains(response, self.request_changes_url(activity))
        self.assertNotContains(response, self.cancel_url(activity))
        self.assertContains(response, "no longer awaiting review")

    def test_review_detail_hides_actions_after_cancel(self):
        activity = self.pending_activity()
        self.login(self.staff)
        self.client.post(self.cancel_url(activity))

        response = self.client.get(self.review_detail_url(activity))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Review actions")
        self.assertNotContains(response, self.publish_url(activity))
        self.assertNotContains(response, self.request_changes_url(activity))
        self.assertNotContains(response, self.cancel_url(activity))
        self.assertContains(response, "no longer awaiting review")

    def test_staff_can_publish_pending_activity(self):
        activity = self.pending_activity()
        self.login(self.staff)

        response = self.client.post(self.publish_url(activity))

        activity.refresh_from_db()
        self.assertRedirects(response, self.review_detail_url(activity))
        self.assertEqual(activity.status, CommunityActivity.STATUS_PUBLISHED)
        self.assertEqual(activity.reviewed_by, self.staff)
        self.assertIsNotNone(activity.reviewed_at)

    def test_published_activity_visible_to_selected_scope_member(self):
        activity = self.pending_activity()
        self.login(self.staff)
        self.client.post(self.publish_url(activity))

        self.login(self.member)
        response = self.client.get(self.detail_url(activity))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            visible_community_activities_for(self.member)
            .filter(id=activity.id)
            .exists()
        )

    def test_staff_can_request_changes_with_review_note(self):
        activity = self.pending_activity()
        self.login(self.staff)

        response = self.client.post(
            self.request_changes_url(activity),
            {"review_note": "Please shorten the description."},
        )

        activity.refresh_from_db()
        self.assertRedirects(response, self.review_detail_url(activity))
        self.assertEqual(
            activity.status,
            CommunityActivity.STATUS_CHANGES_REQUESTED,
        )
        self.assertEqual(
            activity.review_note,
            "Please shorten the description.",
        )
        self.assertEqual(activity.reviewed_by, self.staff)
        self.assertIsNotNone(activity.reviewed_at)

    def test_request_changes_without_note_fails_and_keeps_status(self):
        activity = self.pending_activity()
        self.login(self.staff)

        response = self.client.post(
            self.request_changes_url(activity),
            {"review_note": "   "},
        )

        activity.refresh_from_db()
        self.assertEqual(response.status_code, 302)
        self.assertIn("error=note", response.url)
        self.assertEqual(
            activity.status,
            CommunityActivity.STATUS_PENDING_REVIEW,
        )
        self.assertEqual(activity.review_note, "")

    def test_staff_can_cancel_pending_or_changes_requested(self):
        for status in (
            CommunityActivity.STATUS_PENDING_REVIEW,
            CommunityActivity.STATUS_CHANGES_REQUESTED,
        ):
            with self.subTest(status=status):
                activity = self.pending_activity(status=status)
                self.login(self.staff)

                response = self.client.post(self.cancel_url(activity))

                activity.refresh_from_db()
                self.assertRedirects(response, self.review_detail_url(activity))
                self.assertEqual(
                    activity.status,
                    CommunityActivity.STATUS_CANCELLED,
                )
                self.assertEqual(activity.reviewed_by, self.staff)

    def test_cancelled_activity_hidden_and_not_signup_able(self):
        # A non-creator member in the selected parent scope must not see or
        # sign up for the activity once it is cancelled.
        viewer = self.create_member("cancel_scope_viewer", self.child)
        activity = self.pending_activity(created_by=self.member)
        self.login(self.staff)
        self.client.post(self.cancel_url(activity))

        self.login(viewer)
        detail_response = self.client.get(self.detail_url(activity))
        signup_response = self.client.post(
            reverse("community_activity_signup", args=[activity.id])
        )

        self.assertEqual(detail_response.status_code, 404)
        self.assertEqual(signup_response.status_code, 404)
        self.assertEqual(ActivitySignup.objects.count(), 0)

    def test_review_actions_reject_get_and_ordinary_user(self):
        activity = self.pending_activity()

        self.login(self.staff)
        get_response = self.client.get(self.publish_url(activity))
        self.assertEqual(get_response.status_code, 405)

        self.login(self.member)
        post_response = self.client.post(self.publish_url(activity))
        activity.refresh_from_db()
        self.assertNotEqual(post_response.status_code, 200)
        self.assertEqual(
            activity.status,
            CommunityActivity.STATUS_PENDING_REVIEW,
        )

    def test_review_lifecycle_creates_no_serving_state(self):
        activity = self.pending_activity()
        self.login(self.staff)

        self.client.post(
            self.request_changes_url(activity),
            {"review_note": "tweak"},
        )
        self.client.post(self.publish_url(activity))

        self.assertEqual(TeamAssignment.objects.count(), 0)
        self.assertEqual(TeamAssignmentMember.objects.count(), 0)
        self.assertEqual(BibleStudyMeetingRole.objects.count(), 0)


class CommunityActivityCreatorEditTests(CommunityActivityWebTestBase):
    def edit_url(self, activity):
        return reverse("community_activity_edit", args=[activity.id])

    def detail_url(self, activity):
        return reverse("community_activity_detail", args=[activity.id])

    def changes_requested_activity(self, **overrides):
        data = {
            "title_en": "Changes Requested Picnic",
            "status": CommunityActivity.STATUS_CHANGES_REQUESTED,
            "created_by": self.member,
            "review_note": "Please pick a different scope.",
        }
        data.update(overrides)
        activity = self.create_activity(**data)
        self.add_audience(activity, self.parent)
        return activity

    def resubmit_data(self, activity, **overrides):
        data = {
            "title": activity.title,
            "title_en": activity.title_en,
            "description": activity.description or "Updated details",
            "description_en": activity.description_en,
            "organizer": activity.organizer,
            "start_datetime": timezone.localtime(
                activity.start_datetime
            ).strftime("%Y-%m-%dT%H:%M"),
            "end_datetime": "",
            "location": activity.location,
            "location_en": activity.location_en,
            "audience_units": [self.parent.id],
            "requested_audience_note": activity.requested_audience_note,
        }
        data.update(overrides)
        return data

    def test_creator_can_see_changes_requested_detail_and_note(self):
        activity = self.changes_requested_activity()
        self.login(self.member)

        response = self.client.get(self.detail_url(activity))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Changes requested")
        self.assertContains(response, "Please pick a different scope.")
        self.assertContains(response, self.edit_url(activity))

    def test_changes_requested_appears_in_submissions_with_resubmit_link(self):
        activity = self.changes_requested_activity()
        self.login(self.member)

        response = self.client.get(reverse("community_activity_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Your activity submissions")
        self.assertContains(response, "Changes Requested Picnic", count=1)
        self.assertContains(response, self.edit_url(activity))
        self.assertIn(activity, response.context["submitted_activities"])
        self.assertNotIn(activity, response.context["activities"])

    def test_other_scope_member_cannot_see_changes_requested_activity(self):
        in_scope_member = self.create_member("edit_in_scope", self.child)
        activity = self.changes_requested_activity(
            title_en="Hidden Changes Requested",
        )
        self.login(in_scope_member)

        detail_response = self.client.get(self.detail_url(activity))
        list_response = self.client.get(reverse("community_activity_list"))

        self.assertEqual(detail_response.status_code, 404)
        self.assertNotContains(list_response, "Hidden Changes Requested")
        self.assertFalse(
            visible_community_activities_for(in_scope_member)
            .filter(id=activity.id)
            .exists()
        )

    def test_creator_can_open_edit_form_for_own_changes_requested(self):
        activity = self.changes_requested_activity()
        self.login(self.member)

        response = self.client.get(self.edit_url(activity))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Resubmit for review")

    def test_creator_cannot_edit_pending_published_cancelled(self):
        self.login(self.member)
        for status in (
            CommunityActivity.STATUS_PENDING_REVIEW,
            CommunityActivity.STATUS_PUBLISHED,
            CommunityActivity.STATUS_CANCELLED,
        ):
            with self.subTest(status=status):
                activity = self.create_activity(
                    status=status,
                    created_by=self.member,
                )
                response = self.client.get(self.edit_url(activity))
                self.assertEqual(response.status_code, 404)

    def test_creator_cannot_edit_other_users_activity(self):
        activity = self.changes_requested_activity(created_by=self.other_member)
        self.login(self.member)

        response = self.client.get(self.edit_url(activity))

        self.assertEqual(response.status_code, 404)

    def test_resubmit_sets_status_back_to_pending_review(self):
        activity = self.changes_requested_activity()
        self.login(self.member)

        response = self.client.post(
            self.edit_url(activity),
            self.resubmit_data(activity, description="Rewritten description"),
        )

        activity.refresh_from_db()
        self.assertRedirects(response, self.detail_url(activity))
        self.assertEqual(
            activity.status,
            CommunityActivity.STATUS_PENDING_REVIEW,
        )
        self.assertEqual(activity.description, "Rewritten description")

    def test_resubmit_replaces_audience_rows_transactionally(self):
        activity = self.changes_requested_activity()
        self.login(self.member)

        self.client.post(
            self.edit_url(activity),
            self.resubmit_data(activity, audience_units=[self.sibling.id]),
        )

        activity.refresh_from_db()
        self.assertEqual(
            list(
                activity.audience_scope_links.values_list(
                    "structure_unit_id",
                    flat=True,
                )
            ),
            [self.sibling.id],
        )

    def test_resubmit_with_invalid_scope_keeps_changes_requested(self):
        activity = self.changes_requested_activity()
        self.login(self.member)

        response = self.client.post(
            self.edit_url(activity),
            self.resubmit_data(
                activity,
                audience_units=[self.parent.id, self.child.id],
            ),
        )

        activity.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertIn("audience_units", response.context["form"].errors)
        self.assertEqual(
            activity.status,
            CommunityActivity.STATUS_CHANGES_REQUESTED,
        )
        self.assertEqual(
            list(
                activity.audience_scope_links.values_list(
                    "structure_unit_id",
                    flat=True,
                )
            ),
            [self.parent.id],
        )

    def test_changes_requested_has_no_signup_and_denies_signup_post(self):
        activity = self.changes_requested_activity()
        self.login(self.member)

        detail_response = self.client.get(self.detail_url(activity))
        signup_response = self.client.post(
            reverse("community_activity_signup", args=[activity.id])
        )

        self.assertEqual(detail_response.status_code, 200)
        self.assertNotContains(
            detail_response,
            reverse("community_activity_signup", args=[activity.id]),
        )
        self.assertEqual(signup_response.status_code, 404)
        self.assertEqual(ActivitySignup.objects.count(), 0)

    def test_resubmit_creates_no_serving_state(self):
        activity = self.changes_requested_activity()
        self.login(self.member)

        self.client.post(self.edit_url(activity), self.resubmit_data(activity))

        self.assertEqual(TeamAssignment.objects.count(), 0)
        self.assertEqual(TeamAssignmentMember.objects.count(), 0)
        self.assertEqual(BibleStudyMeetingRole.objects.count(), 0)


class CommunityActivityReviewNavTests(CommunityActivityWebTestBase):
    def review_nav_href(self):
        return 'href="%s"' % reverse("community_activity_review_list")

    def test_staff_dropdown_shows_review_link_when_module_enabled(self):
        self.login(self.staff, language="en")
        response = self.client.get(reverse("profile"))

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn(self.review_nav_href(), content)
        self.assertIn("Activity Review", content)

    @override_settings(CMS_ENABLED_MODULES=_WITHOUT_COMMUNITY_EVENTS)
    def test_staff_dropdown_hides_review_link_when_module_disabled(self):
        self.login(self.staff, language="en")
        response = self.client.get(reverse("profile"))

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertNotIn(self.review_nav_href(), content)

    def test_ordinary_user_has_no_review_link(self):
        self.login(self.member, language="en")
        response = self.client.get(reverse("profile"))

        self.assertEqual(response.status_code, 200)
        self.assertNotIn(self.review_nav_href(), response.content.decode())


class CommunityActivityTodayTests(CommunityActivityWebTestBase):
    """COMMUNITY-EVENTS.1E-A personally relevant Today integration."""

    def setUp(self):
        super().setUp()
        self.today = timezone.make_aware(datetime(2030, 1, 7, 10, 0))

    def get_home(self, user=None, language="en"):
        self.login(user or self.member, language=language)
        with (
            patch(
                "community_events.today_provider.current_time",
                return_value=self.today,
            ),
            patch(
                "core.today_windows.timezone.localdate",
                return_value=self.today.date(),
            ),
        ):
            return self.client.get(reverse("home"))

    def signed_up_activity(self, *, starts_at, user=None, **overrides):
        activity = self.create_activity(
            start_datetime=starts_at,
            **overrides,
        )
        self.add_audience(activity, self.parent)
        ActivitySignup.objects.create(
            activity=activity,
            user=user or self.member,
            status=ActivitySignup.STATUS_SIGNED_UP,
        )
        return activity

    def test_today_shows_signed_up_published_activity_happening_today(self):
        activity = self.signed_up_activity(
            starts_at=self.today + timezone.timedelta(hours=2),
            title_en="Today Signed Activity",
        )

        response = self.get_home()

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Activities")
        self.assertContains(response, "Today Signed Activity")
        self.assertContains(response, "You’re signed up")
        self.assertIn(
            activity,
            response.context["community_activity_today_items"],
        )
        self.assertNotIn(
            activity,
            response.context["community_activity_this_week_items"],
        )

    def test_later_signed_up_activity_appears_only_in_this_week(self):
        activity = self.signed_up_activity(
            starts_at=self.today + timezone.timedelta(days=2),
            title_en="Later This Week Activity",
        )

        response = self.get_home()

        self.assertContains(response, "This Week")
        self.assertContains(response, "Later This Week Activity")
        self.assertNotIn(
            activity,
            response.context["community_activity_today_items"],
        )
        self.assertIn(
            activity,
            response.context["community_activity_this_week_items"],
        )

    def test_visible_published_activity_without_signup_is_not_on_today(self):
        activity = self.create_activity(
            title_en="Visible But Not Signed Up",
            start_datetime=self.today + timezone.timedelta(hours=2),
        )
        self.add_audience(activity, self.parent)

        response = self.get_home()

        self.assertNotContains(response, "Visible But Not Signed Up")
        self.assertEqual(response.context["community_activity_today_items"], [])

    def test_cancelled_signup_hidden_and_nonmatching_or_nonpublished_hidden(self):
        cancelled_signup = self.signed_up_activity(
            starts_at=self.today + timezone.timedelta(hours=1),
            title_en="Cancelled Signup Hidden",
        )
        cancelled_signup.signups.update(status=ActivitySignup.STATUS_CANCELLED)

        nonmatching = self.create_activity(
            title_en="Other Scope Signed Hidden",
            start_datetime=self.today + timezone.timedelta(hours=2),
        )
        self.add_audience(nonmatching, self.sibling)
        ActivitySignup.objects.create(activity=nonmatching, user=self.member)

        pending = self.create_activity(
            title_en="Pending Signed Hidden",
            status=CommunityActivity.STATUS_PENDING_REVIEW,
            start_datetime=self.today + timezone.timedelta(hours=3),
        )
        self.add_audience(pending, self.parent)
        ActivitySignup.objects.create(activity=pending, user=self.member)

        response = self.get_home()

        for title in (
            "Cancelled Signup Hidden",
            "Other Scope Signed Hidden",
            "Pending Signed Hidden",
        ):
            self.assertNotContains(response, title)
        self.assertEqual(response.context["community_activity_today_items"], [])

    def test_selected_scope_user_does_not_see_other_creators_review_rows(self):
        for status, title in (
            (
                CommunityActivity.STATUS_PENDING_REVIEW,
                "Other Creator Pending Hidden",
            ),
            (
                CommunityActivity.STATUS_CHANGES_REQUESTED,
                "Other Creator Changes Hidden",
            ),
        ):
            activity = self.create_activity(
                title_en=title,
                status=status,
                created_by=self.other_member,
            )
            self.add_audience(activity, self.parent)

        response = self.get_home()

        self.assertNotContains(response, "Other Creator Pending Hidden")
        self.assertNotContains(response, "Other Creator Changes Hidden")
        self.assertEqual(
            response.context["community_activity_creator_attention_items"],
            [],
        )

    def test_creator_changes_requested_shows_attention_and_edit_link(self):
        activity = self.create_activity(
            title_en="Creator Changes Activity",
            status=CommunityActivity.STATUS_CHANGES_REQUESTED,
            created_by=self.member,
        )

        response = self.get_home()

        self.assertContains(response, "Creator Changes Activity")
        self.assertContains(response, "Changes requested")
        self.assertContains(
            response,
            reverse("community_activity_edit", args=[activity.id]),
        )
        self.assertIn(
            activity,
            response.context["community_activity_creator_attention_items"],
        )

    def test_creator_pending_review_is_a_status_only_reminder(self):
        activity = self.create_activity(
            title_en="Creator Pending Activity",
            status=CommunityActivity.STATUS_PENDING_REVIEW,
            created_by=self.member,
        )

        response = self.get_home()

        self.assertContains(response, "Creator Pending Activity")
        self.assertContains(response, "Pending review")
        self.assertNotContains(
            response,
            reverse("community_activity_edit", args=[activity.id]),
        )

    def test_today_activity_copy_renders_in_chinese(self):
        self.signed_up_activity(
            starts_at=self.today + timezone.timedelta(hours=2),
            title="今日已报名活动",
        )
        self.create_activity(
            title="需要修改的活动",
            status=CommunityActivity.STATUS_CHANGES_REQUESTED,
            created_by=self.member,
        )

        response = self.get_home(language="zh")

        self.assertContains(response, "活动")
        self.assertContains(response, "你已报名")
        self.assertContains(response, "需要修改")

    def test_published_creator_activity_requires_active_signup(self):
        unsigned = self.create_activity(
            title_en="Creator Published Unsigned",
            status=CommunityActivity.STATUS_PUBLISHED,
            created_by=self.member,
            start_datetime=self.today + timezone.timedelta(hours=1),
        )
        self.add_audience(unsigned, self.parent)
        signed = self.signed_up_activity(
            starts_at=self.today + timezone.timedelta(hours=2),
            title_en="Creator Published Signed",
            created_by=self.member,
        )

        response = self.get_home()

        self.assertNotContains(response, "Creator Published Unsigned")
        self.assertContains(response, "Creator Published Signed")
        self.assertNotIn(
            unsigned,
            response.context["community_activity_creator_attention_items"],
        )
        self.assertIn(
            signed,
            response.context["community_activity_today_items"],
        )

    @override_settings(CMS_ENABLED_MODULES=_WITHOUT_COMMUNITY_EVENTS)
    def test_disabled_module_keeps_empty_defaults_and_skips_provider_queries(self):
        with patch(
            "community_events.today_provider.visible_community_activities_for",
        ) as visible_activities:
            response = self.get_home()

        visible_activities.assert_not_called()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["community_activity_today_items"], [])
        self.assertEqual(
            response.context["community_activity_this_week_items"],
            [],
        )
        self.assertEqual(
            response.context["community_activity_creator_attention_items"],
            [],
        )
        self.assertNotContains(response, "Activities")

    def test_today_integration_creates_no_serving_or_service_event_state(self):
        self.signed_up_activity(
            starts_at=self.today + timezone.timedelta(hours=2),
        )

        response = self.get_home()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(TeamAssignment.objects.count(), 0)
        self.assertEqual(TeamAssignmentMember.objects.count(), 0)
        self.assertEqual(BibleStudyMeetingRole.objects.count(), 0)
        self.assertNotIn(
            "service_event",
            {field.name for field in CommunityActivity._meta.get_fields()},
        )
        self.assertTrue(
            set(COMMUNITY_ACTIVITY_TODAY_DEFAULTS).isdisjoint(
                {
                    "serving_summary",
                    "leader_summary",
                    "my_serving_items",
                    "serving_action_items",
                }
            )
        )


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
            CommunityActivity.STATUS_PENDING_REVIEW,
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
