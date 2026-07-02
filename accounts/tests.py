import re
from datetime import timedelta
from io import StringIO
from pathlib import Path

from django.contrib.auth.models import AnonymousUser, User
from django.contrib.messages import get_messages
from django.core.exceptions import FieldDoesNotExist, ValidationError
from django.core.management import call_command, CommandError
from django.db import connection, IntegrityError, transaction
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from accounts.forms import (
    StructureUnitCoworkerAssignmentForm,
    coworker_assignment_local_user_queryset,
    create_or_update_signup_membership_request,
)
from accounts.models import (
    ChurchMemberRecord,
    ChurchRoleAssignment,
    ChurchStructureMembership,
    ChurchStructureUnit,
    ChurchStructureUnitMemberRecord,
    ChurchStructureUnitRoleAssignment,
    ChurchStructureUnitRoleProfile,
    ChurchStructureUnitRoleRequirement,
    ChurchStructureUnitRoleType,
    Profile,
    ServingReadinessPolicy,
    ServingReadinessRequirement,
)
from accounts.serving_readiness import (
    STATUS_INACTIVE_USER,
    STATUS_NO_POLICY,
    STATUS_NO_RECORD,
    STATUS_PENDING,
    STATUS_READY,
    evaluate_serving_readiness,
    get_serving_readiness,
    get_serving_readiness_warning_messages,
)
from accounts.permissions import (
    CAP_MANAGE_CHURCH_MEMBERSHIPS,
    CAP_MANAGE_BIBLE_STUDIES,
    CAP_PUBLISH_READING_GUIDES,
    CAP_VIEW_ALL_GROUP_PROGRESS,
    CAP_VIEW_DISTRICT_PROGRESS,
    CAP_VIEW_GROUP_PROGRESS,
    assignment_scope_includes_unit,
    can_view_group_progress_for,
    get_accessible_progress_groups,
    get_role_assignment_structure_unit,
    get_user_membership_progress_own_group,
    has_capability,
)
from accounts.unit_management import (
    can_manage_unit_coworkers,
    get_manageable_structure_units,
    get_user_active_lead_units,
    should_show_my_units_nav,
)
from accounts.unit_member_record_access import (
    UNIT_MEMBER_RECORD_ACCESS_ADMIN_FULL,
    UNIT_MEMBER_RECORD_ACCESS_NONE,
    UNIT_MEMBER_RECORD_ACCESS_SELF_BASIC,
    UNIT_MEMBER_RECORD_ACCESS_UNIT_LEAD_OPERATIONAL,
    build_unit_member_record_safe_snapshot,
    can_view_unit_member_record_basic,
    can_view_unit_member_record_care_notes,
    can_view_unit_member_record_group_notes,
    can_write_unit_member_records,
    get_unit_member_record_access_tier,
)
from comments.models import ReflectionComment, ReflectionReport
from events.models import ServiceEvent, ServiceEventAudienceScope
from events.views import get_visible_service_events
from ministry.models import (
    MinistryTeam,
    TeamAssignment,
    TeamAssignmentMember,
    TeamMembership,
)
from ministry.today_provider import get_today_serving_summary
from ministry.views import my_serving_assignments
from prayers.models import PrayerReport, PrayerRequest
from reading.models import ReadingPlan, ReadingPlanDay
from studies.models import (
    BibleStudyLesson,
    BibleStudyMeeting,
    BibleStudyMeetingAudienceScope,
    BibleStudyMeetingRole,
    BibleStudySeries,
    BibleStudySeriesAudienceScope,
)
from studies.visibility import get_membership_audience_candidate_unit_ids


def create_role_assignment_without_validation(**kwargs):
    """Insert historical role-scope fixtures that new validation would reject."""
    assignment = ChurchRoleAssignment(**kwargs)
    assignment.save_base(force_insert=True)
    return assignment


class AccountProfileTests(TestCase):
    def setUp(self):
        self.unit = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="PROFILE4",
            name="Profile Rainbow 4",
            name_en="Profile Rainbow 4",
        )
        self.other_unit = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="SMALLGROUP-6",
            name="Profile Rainbow 5",
            name_en="Profile Rainbow 5",
        )
        self.fellowship_unit = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_FELLOWSHIP,
            code="PROFILEF",
            name="Profile Fellowship",
            name_en="Profile Fellowship",
        )

        self.user = User.objects.create_user(
            username="levin",
            email="",
            password="OldPass123!",
        )

        self.user.profile.preferred_language = "zh"
        self.user.profile.save()

        self.staff = User.objects.create_user(
            username="staff",
            email="staff@example.com",
            password="StaffPass123!",
            is_staff=True,
        )

    def set_language(self, language="en"):
        session = self.client.session
        session["language"] = language
        session.save()

    def assert_active_nav_href(self, response, url_name):
        content = response.content.decode()
        expected_href = reverse(url_name)

        self.assertEqual(content.count('class="nav-link active"'), 1)
        self.assertRegex(
            content,
            r'class="nav-link active"\s+href="%s"' % re.escape(expected_href),
        )

    def test_profile_requires_login(self):
        response = self.client.get(reverse("profile"))

        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_profile_page_shows_user_info(self):
        # CS-RETIRE.1A: the "current confirmed group" display uses the active
        # primary ChurchStructureMembership unit, not legacy Profile.small_group.
        ChurchStructureMembership.objects.create(
            user=self.user,
            unit=self.unit,
            status=ChurchStructureMembership.STATUS_ACTIVE,
            is_primary=True,
            start_date=timezone.localdate(),
        )
        self.client.login(username="levin", password="OldPass123!")

        response = self.client.get(reverse("profile"))
        content = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "levin")
        # The membership unit path (not the legacy small group) is the group shown.
        self.assertContains(response, "Profile Rainbow 4")
        self.assertContains(response, "我参加的小组")
        self.assertContains(response, "Profile Rainbow 5")
        self.assertNotContains(response, "SMALLGROUP-6 - Profile Rainbow 5")
        self.assertNotIn('name="small_group"', content)

    def test_profile_page_no_membership_shows_no_group_not_legacy_profile(self):
        # CS-RETIRE.1A: with a legacy Profile.small_group but no active primary
        # membership, the page shows the no-group state, not the legacy group.
        self.assertFalse(
            ChurchStructureMembership.objects.filter(user=self.user).exists()
        )
        self.set_language("en")
        self.client.login(username="levin", password="OldPass123!")

        response = self.client.get(reverse("profile"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Not sure / new here")
        # The legacy group name is not presented as the confirmed group.
        self.assertNotContains(response, "Current confirmed group: Rainbow 4")

    def test_user_can_update_profile_without_email(self):
        self.client.login(username="levin", password="OldPass123!")

        response = self.client.post(
            reverse("profile"),
            {
                "email": "",
                "requested_unit": "",
                "preferred_language": "en",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("profile"))

        self.user.refresh_from_db()
        self.user.profile.refresh_from_db()

        self.assertEqual(self.user.email, "")
        self.assertEqual(self.user.profile.preferred_language, "en")
        self.assertEqual(self.client.session["language"], "en")
        self.assertFalse(
            ChurchStructureMembership.objects.filter(user=self.user).exists(),
        )

    def test_user_can_update_email(self):
        self.client.login(username="levin", password="OldPass123!")

        response = self.client.post(
            reverse("profile"),
            {
                "email": "levin@example.com",
                "requested_unit": "",
                "preferred_language": "zh",
            },
        )

        self.assertEqual(response.status_code, 302)

        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "levin@example.com")

    def test_profile_requested_small_group_unit_creates_pending_membership_request(self):
        self.client.login(username="levin", password="OldPass123!")

        response = self.client.post(
            reverse("profile"),
            {
                "email": "levin@example.com",
                "requested_unit": self.other_unit.id,
                "preferred_language": "en",
            },
        )

        self.assertEqual(response.status_code, 302)

        self.user.refresh_from_db()
        self.user.profile.refresh_from_db()
        membership = ChurchStructureMembership.objects.get(user=self.user)

        self.assertEqual(self.user.email, "levin@example.com")
        self.assertEqual(self.user.profile.preferred_language, "en")
        self.assertEqual(membership.unit, self.other_unit)
        self.assertEqual(membership.status, ChurchStructureMembership.STATUS_REQUESTED)
        self.assertEqual(
            membership.membership_type,
            ChurchStructureMembership.TYPE_SMALL_GROUP_MEMBER,
        )
        self.assertFalse(membership.is_primary)
        self.assertEqual(membership.requested_by, self.user)
        self.assertIsNone(membership.approved_by)
        self.assertIsNone(membership.approved_at)
        self.assertIsNone(membership.start_date)

    def test_profile_requested_fellowship_unit_creates_pending_membership_request(self):
        self.client.login(username="levin", password="OldPass123!")

        response = self.client.post(
            reverse("profile"),
            {
                "email": "",
                "requested_unit": self.fellowship_unit.id,
                "preferred_language": "zh",
            },
        )

        self.assertEqual(response.status_code, 302)

        membership = ChurchStructureMembership.objects.get(user=self.user)
        self.user.profile.refresh_from_db()

        self.assertEqual(membership.unit, self.fellowship_unit)
        self.assertEqual(membership.status, ChurchStructureMembership.STATUS_REQUESTED)

    def test_profile_rejects_inactive_requested_unit(self):
        inactive_unit = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="PROFILEINACTIVE",
            name="Profile Inactive",
            is_active=False,
        )
        self.client.login(username="levin", password="OldPass123!")

        response = self.client.post(
            reverse("profile"),
            {
                "email": "changed@example.com",
                "requested_unit": inactive_unit.id,
                "preferred_language": "en",
            },
        )

        self.assertEqual(response.status_code, 200)

        self.user.refresh_from_db()
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.email, "")
        self.assertEqual(self.user.profile.preferred_language, "zh")
        self.assertFalse(
            ChurchStructureMembership.objects.filter(user=self.user).exists(),
        )

    def test_profile_rejects_non_requestable_requested_unit(self):
        root_unit = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_ROOT,
            code="PROFILEROOT",
            name="Profile Root",
        )
        self.client.login(username="levin", password="OldPass123!")

        response = self.client.post(
            reverse("profile"),
            {
                "email": "changed@example.com",
                "requested_unit": root_unit.id,
                "preferred_language": "en",
            },
        )

        self.assertEqual(response.status_code, 200)

        self.user.refresh_from_db()
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.email, "")
        self.assertEqual(self.user.profile.preferred_language, "zh")
        self.assertFalse(
            ChurchStructureMembership.objects.filter(user=self.user).exists(),
        )

    def test_profile_duplicate_pending_request_updates_existing_row(self):
        existing = ChurchStructureMembership.objects.create(
            user=self.user,
            unit=self.unit,
            status=ChurchStructureMembership.STATUS_REQUESTED,
            is_primary=True,
            start_date=timezone.localdate(),
            approved_by=self.staff,
            approved_at=timezone.now(),
        )
        self.client.login(username="levin", password="OldPass123!")

        response = self.client.post(
            reverse("profile"),
            {
                "email": "",
                "requested_unit": self.other_unit.id,
                "preferred_language": "zh",
            },
        )

        self.assertEqual(response.status_code, 302)

        membership = ChurchStructureMembership.objects.get(user=self.user)
        self.assertEqual(membership.id, existing.id)
        self.assertEqual(membership.unit, self.other_unit)
        self.assertEqual(membership.status, ChurchStructureMembership.STATUS_REQUESTED)
        self.assertFalse(membership.is_primary)
        self.assertEqual(membership.requested_by, self.user)
        self.assertIsNone(membership.approved_by)
        self.assertIsNone(membership.approved_at)
        self.assertIsNone(membership.start_date)

    def test_profile_request_leaves_active_primary_membership_unchanged(self):
        active_primary = ChurchStructureMembership.objects.create(
            user=self.user,
            unit=self.unit,
            status=ChurchStructureMembership.STATUS_ACTIVE,
            is_primary=True,
            start_date=timezone.localdate(),
            approved_by=self.staff,
            approved_at=timezone.now(),
        )
        self.client.login(username="levin", password="OldPass123!")

        response = self.client.post(
            reverse("profile"),
            {
                "email": "",
                "requested_unit": self.other_unit.id,
                "preferred_language": "zh",
            },
        )

        self.assertEqual(response.status_code, 302)

        active_primary.refresh_from_db()
        pending = ChurchStructureMembership.objects.get(
            user=self.user,
            status=ChurchStructureMembership.STATUS_REQUESTED,
        )

        self.assertEqual(active_primary.status, ChurchStructureMembership.STATUS_ACTIVE)
        self.assertTrue(active_primary.is_primary)
        self.assertEqual(active_primary.unit, self.unit)
        self.assertEqual(pending.unit, self.other_unit)
        self.assertFalse(pending.is_primary)
        self.user.profile.refresh_from_db()

    def test_profile_request_does_not_grant_runtime_access_or_permissions(self):
        event = ServiceEvent.objects.create(
            title="Profile District Service",
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
            start_datetime=timezone.now(),
            status=ServiceEvent.STATUS_PUBLISHED,
        )
        self.client.login(username="levin", password="OldPass123!")

        response = self.client.post(
            reverse("profile"),
            {
                "email": "",
                "requested_unit": self.other_unit.id,
                "preferred_language": "zh",
            },
        )

        self.assertEqual(response.status_code, 302)

        self.user.profile.refresh_from_db()
        self.assertFalse(event.can_be_seen_by(self.user))
        self.assertFalse(has_capability(self.user, CAP_MANAGE_CHURCH_MEMBERSHIPS))
        self.assertEqual(TeamMembership.objects.count(), 0)
        self.assertEqual(TeamAssignment.objects.count(), 0)
        self.assertEqual(TeamAssignmentMember.objects.count(), 0)

        serving_response = self.client.get(reverse("my_serving"))

        self.assertEqual(serving_response.status_code, 200)
        self.assertContains(serving_response, "你目前还没有即将到来的服事安排。")

    def test_staff_request_pages_show_profile_created_request(self):
        self.client.login(username="levin", password="OldPass123!")
        response = self.client.post(
            reverse("profile"),
            {
                "email": "",
                "requested_unit": self.other_unit.id,
                "preferred_language": "zh",
            },
        )
        self.assertEqual(response.status_code, 302)
        membership = ChurchStructureMembership.objects.get(user=self.user)
        self.client.logout()
        self.client.login(username="staff", password="StaffPass123!")

        list_response = self.client.get(reverse("staff_membership_request_list"))
        detail_response = self.client.get(
            reverse("staff_membership_request_detail", args=[membership.id]),
        )

        self.assertEqual(list_response.status_code, 200)
        self.assertContains(list_response, "levin")
        self.assertContains(list_response, "Profile Rainbow 5")
        # PROFILE-SG-FIELD-RETIRE.1A removed the legacy current-group column, so the
        # legacy Profile.small_group name ("Rainbow 4") is no longer displayed.
        self.assertEqual(detail_response.status_code, 200)
        self.assertContains(detail_response, "levin")
        self.assertContains(detail_response, "Profile Rainbow 5")

    def test_password_change_page_requires_login(self):
        response = self.client.get(reverse("password_change"))

        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_user_can_change_password(self):
        self.client.login(username="levin", password="OldPass123!")

        response = self.client.post(
            reverse("password_change"),
            {
                "old_password": "OldPass123!",
                "new_password1": "NewStrongPass123!",
                "new_password2": "NewStrongPass123!",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("password_change_done"))

        self.client.logout()

        login_success = self.client.login(
            username="levin",
            password="NewStrongPass123!",
        )

        self.assertTrue(login_success)

    def test_password_change_page_chinese_labels(self):
        self.set_language("zh")
        self.client.login(username="levin", password="OldPass123!")

        response = self.client.get(reverse("password_change"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "旧密码")
        self.assertContains(response, "新密码")
        self.assertContains(response, "确认新密码")
        self.assertContains(response, "密码至少 8 个字符")
        # Default English Django strings must not leak into the Chinese page.
        self.assertNotContains(response, "Old password")
        self.assertNotContains(response, "Enter the same password as before")

    def test_password_change_page_english_labels(self):
        self.set_language("en")
        self.client.login(username="levin", password="OldPass123!")

        response = self.client.get(reverse("password_change"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Old password")
        self.assertContains(response, "New password")

    def test_password_change_behavior_unchanged_in_chinese(self):
        # Localization must not alter the actual change behavior.
        self.set_language("zh")
        self.client.login(username="levin", password="OldPass123!")

        response = self.client.post(
            reverse("password_change"),
            {
                "old_password": "OldPass123!",
                "new_password1": "NewStrongPass123!",
                "new_password2": "NewStrongPass123!",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("password_change_done"))
        self.client.logout()
        self.assertTrue(
            self.client.login(username="levin", password="NewStrongPass123!")
        )

    def test_password_change_chinese_weak_password_error_localized(self):
        self.set_language("zh")
        self.client.login(username="levin", password="OldPass123!")

        response = self.client.post(
            reverse("password_change"),
            {
                "old_password": "OldPass123!",
                "new_password1": "Ab1!",
                "new_password2": "Ab1!",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "密码太短")
        self.assertNotContains(response, "This password is too short")
        # Password must not change on validation failure.
        self.client.logout()
        self.assertTrue(self.client.login(username="levin", password="OldPass123!"))

    def test_password_change_english_weak_password_shows_english_error(self):
        self.set_language("en")
        self.client.login(username="levin", password="OldPass123!")

        response = self.client.post(
            reverse("password_change"),
            {
                "old_password": "OldPass123!",
                "new_password1": "Ab1!",
                "new_password2": "Ab1!",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "too short")

    def test_normal_english_user_sees_simple_primary_nav(self):
        self.set_language("en")
        self.client.login(username="levin", password="OldPass123!")

        response = self.client.get(reverse("profile"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Today")
        self.assertContains(response, "Reading")
        self.assertContains(response, "Bible Study")
        self.assertContains(response, "Prayer")
        self.assertContains(response, "My Serving")
        self.assertContains(response, "Profile")
        self.assertNotContains(response, "Reading Plan Admin")
        self.assertNotContains(response, "Bible Study Admin")
        self.assertNotContains(response, "Bible Study Schedules")
        self.assertNotContains(response, "Legacy Bible Study Sessions")
        self.assertNotContains(response, "Weekly Bible Study Guides")
        self.assertNotContains(response, "Small Group Meetings")
        self.assertNotContains(response, "User Admin")
        self.assertNotContains(response, "Reflection Reports")
        self.assertNotContains(response, "Prayer Reports")
        self.assertNotContains(response, "Ministry Teams")
        self.assertNotContains(response, "Team Assignments")
        self.assertNotContains(response, "Django Admin")
        self.assertNotContains(response, "Staff")

    def test_normal_english_user_nav_excludes_global_clutter(self):
        self.set_language("en")
        self.client.login(username="levin", password="OldPass123!")

        response = self.client.get(reverse("profile"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Calendar")
        self.assertNotContains(response, "Reflection Wall")
        self.assertNotContains(response, "Prayer Wall")
        self.assertNotContains(response, "Group Progress")

    def test_staff_english_user_sees_staff_menu_links(self):
        self.set_language("en")
        self.client.login(username="staff", password="StaffPass123!")

        response = self.client.get(reverse("profile"))
        content = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Staff")
        self.assertIn(
            '<details class="nav-staff-menu nav-dropdown" data-dropdown-var-prefix="staff-menu">',
            content,
        )
        self.assertIn('<div class="nav-staff-menu-panel nav-dropdown-panel">', content)
        self.assertIn('document.querySelectorAll(".nav-dropdown")', content)
        self.assertIn('(hover: hover) and (pointer: fine)', content)
        self.assertIn('menu.addEventListener("mouseenter"', content)
        self.assertIn("menu.contains(event.relatedTarget)", content)
        self.assertIn("nav-menu-open", content)
        self.assertIn("lockBodyScroll", content)
        self.assertIn("unlockBodyScroll", content)
        self.assertIn("site-header--hidden", content)
        self.assertIn("var mobileHeader = window.matchMedia", content)
        self.assertIn("function headerHasActiveInteraction()", content)
        self.assertIn("function updateHeaderVisibility()", content)
        self.assertIn("function requestHeaderVisibilityUpdate()", content)
        self.assertIn('window.addEventListener("scroll"', content)
        self.assertIn("showSiteHeader();", content)
        self.assertIn("hideSiteHeader", content)
        self.assertIn("headerHidden", content)
        self.assertIn("visibilityCooldownMs = 125", content)
        self.assertIn("headerTouchActive", content)
        self.assertIn("headerPointerActive", content)
        self.assertNotIn("headerFocusActive", content)
        self.assertIn("clearTransientHeaderInteraction", content)
        self.assertIn("getClampedScrollY", content)
        self.assertIn("accumulatedScrollDelta", content)
        self.assertIn("hideScrollThreshold = 56", content)
        self.assertIn("showScrollThreshold = 96", content)
        self.assertIn("tinyScrollDelta = 4", content)
        self.assertIn("bottomBounceZone = 48", content)
        self.assertIn("hasOpenDropdown()", content)
        self.assertIn("setDropdownPosition(menu)", content)
        self.assertIn("var summaryRect = summary.getBoundingClientRect();", content)
        self.assertIn("var desiredTop = summaryRect.bottom + 8;", content)
        self.assertIn("var desiredLeft = summaryRect.left;", content)
        self.assertIn("viewportHeight * 0.55", content)
        self.assertIn("Math.min(420, Math.max(280", content)
        self.assertIn("var maxAllowedTop = viewportHeight - minPanelHeight - margin;", content)
        self.assertIn("Math.min(desiredTop, Math.max(margin, maxAllowedTop))", content)
        self.assertIn("top = Math.max(margin, top);", content)
        self.assertIn("var panelWidth = Math.min(availableWidth, 520);", content)
        self.assertIn("Math.max(desiredLeft, margin)", content)
        self.assertIn('menu.getAttribute("data-dropdown-var-prefix")', content)
        self.assertIn('"--" + varPrefix + "-top"', content)
        self.assertIn('"--" + varPrefix + "-left"', content)
        self.assertIn('"--" + varPrefix + "-width"', content)
        self.assertIn("--nav-dropdown-top", content)
        self.assertIn("closeMenuFromOutside", content)
        self.assertIn('document.addEventListener("click"', content)
        self.assertIn("lockedMenu.contains(event.target)", content)
        self.assertContains(response, "Content Management")
        self.assertContains(response, "Reading Plan Admin")
        self.assertContains(response, "Bible Study Schedules")
        self.assertContains(response, "Weekly Bible Study Guides")
        self.assertContains(response, "Small Group Meetings")
        self.assertNotContains(response, "Bible Study Admin")
        self.assertNotContains(response, "Legacy Bible Study Sessions")
        self.assertLess(
            content.index("Bible Study Schedules"),
            content.index("Weekly Bible Study Guides"),
        )
        self.assertLess(
            content.index("Weekly Bible Study Guides"),
            content.index("Small Group Meetings"),
        )
        self.assertContains(response, "Ministry Operations")
        self.assertContains(response, "Church Gatherings")
        self.assertContains(response, "Ministry Teams")
        self.assertContains(response, "Team Assignments")
        # The Lighting Pilot Import is retired from the discoverable staff
        # menu; its route remains available but is not linked here.
        self.assertNotContains(response, "Lighting Pilot Import")
        self.assertContains(response, "Church Structure")
        self.assertContains(response, "Church Structure Setup & Review")
        self.assertContains(response, reverse("staff_structure_map"))
        self.assertContains(response, "Users and Review")
        self.assertContains(response, "User Admin")
        self.assertContains(response, "Reflection Reports")
        self.assertContains(response, "Prayer Reports")
        self.assertContains(response, "Django Admin")
        # Staff Overview is a dashboard entry point, not Content Management;
        # it renders ahead of the first group heading.
        self.assertLess(
            content.index("Staff Overview"),
            content.index("Content Management"),
        )

    @override_settings(
        CMS_ENABLED_MODULES=["prayers", "studies", "events", "ministry"]
    )
    def test_staff_menu_hides_reading_link_when_reading_disabled(self):
        self.set_language("en")
        self.client.login(username="staff", password="StaffPass123!")

        response = self.client.get(reverse("profile"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Reading Plan Admin")
        self.assertContains(response, "Bible Study Schedules")
        self.assertContains(response, "Staff Overview")

    @override_settings(
        CMS_ENABLED_MODULES=["reading", "prayers", "events", "ministry"]
    )
    def test_staff_menu_hides_study_links_when_studies_disabled(self):
        self.set_language("en")
        self.client.login(username="staff", password="StaffPass123!")

        response = self.client.get(reverse("profile"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Bible Study Schedules")
        self.assertNotContains(response, "Weekly Bible Study Guides")
        self.assertNotContains(response, "Small Group Meetings")
        self.assertContains(response, "Reading Plan Admin")
        self.assertContains(response, "Church Gatherings")
        self.assertContains(response, "Ministry Teams")
        self.assertContains(response, "Prayer Reports")
        self.assertContains(response, "Staff Overview")

    @override_settings(CMS_ENABLED_MODULES=["reading", "prayers", "studies"])
    def test_staff_menu_hides_events_and_ministry_links_when_events_disabled(self):
        self.set_language("en")
        self.client.login(username="staff", password="StaffPass123!")

        response = self.client.get(reverse("profile"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Church Gatherings")
        self.assertNotContains(response, "Ministry Teams")
        self.assertNotContains(response, "Team Assignments")
        self.assertContains(response, "Reading Plan Admin")
        self.assertContains(response, "Bible Study Schedules")
        self.assertContains(response, "Staff Overview")

    @override_settings(
        CMS_ENABLED_MODULES=["reading", "prayers", "studies", "events"]
    )
    def test_staff_menu_hides_ministry_links_but_keeps_events_link(self):
        self.set_language("en")
        self.client.login(username="staff", password="StaffPass123!")

        response = self.client.get(reverse("profile"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Church Gatherings")
        self.assertNotContains(response, "Ministry Teams")
        self.assertNotContains(response, "Team Assignments")
        self.assertContains(response, "Staff Overview")

    @override_settings(
        CMS_ENABLED_MODULES=["reading", "studies", "events", "ministry"]
    )
    def test_staff_menu_hides_prayer_reports_when_prayers_disabled(self):
        self.set_language("en")
        self.client.login(username="staff", password="StaffPass123!")

        response = self.client.get(reverse("profile"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Prayer Reports")
        self.assertContains(response, "Reflection Reports")
        self.assertContains(response, "Staff Overview")

    @override_settings(CMS_ENABLED_MODULES=[])
    def test_disabled_module_staff_urls_remain_reachable(self):
        self.client.login(username="staff", password="StaffPass123!")

        for url_name in (
            "staff_reading_plan_list",
            "bible_study_schedule_manage_list",
            "bible_study_lesson_manage_list",
            "bible_study_meeting_manage_list",
            "service_event_list",
            "ministry_team_list",
            "team_assignment_list",
            "staff_prayer_reports",
        ):
            with self.subTest(url_name=url_name):
                response = self.client.get(reverse(url_name))
                self.assertEqual(response.status_code, 200)

    def test_mobile_staff_menu_css_uses_viewport_overlay_height(self):
        css_path = Path(__file__).resolve().parent.parent / "static" / "css" / "app.css"
        css = css_path.read_text(encoding="utf-8")

        self.assertIn("top: var(--staff-menu-top, var(--nav-dropdown-top, 88px));", css)
        self.assertIn("left: var(--staff-menu-left, var(--nav-dropdown-left, 12px));", css)
        self.assertIn(
            "width: var(--staff-menu-width, var(--nav-dropdown-width, calc(100vw - 24px)));",
            css,
        )
        self.assertIn("bottom: max(12px, env(safe-area-inset-bottom));", css)
        self.assertIn("min-width: 0;", css)
        self.assertIn("max-width: calc(100vw - 24px);", css)
        self.assertIn("max-height: none;", css)
        self.assertIn("overflow-y: auto;", css)
        self.assertIn("z-index: 100;", css)
        self.assertIn(".site-header.site-header--hidden", css)
        self.assertIn("transform: translateY(calc(-100% - 1px));", css)
        self.assertIn("body.nav-menu-open .site-header", css)
        self.assertIn("transition: none;", css)
        self.assertIn("@media (max-width: 760px) and (prefers-reduced-motion: reduce)", css)
        self.assertNotIn("will-change: transform", css)
        self.assertNotIn("transform: translateY(0);", css)
        self.assertNotIn("min-width: min(300px", css)

    def test_english_header_has_mobile_nav_toggle_button(self):
        self.set_language("en")
        self.client.login(username="levin", password="OldPass123!")

        response = self.client.get(reverse("profile"))
        content = response.content.decode()

        self.assertEqual(response.status_code, 200)
        # Hamburger button with accessible state + an id'd nav it controls.
        self.assertIn('class="nav-toggle"', content)
        self.assertIn('aria-controls="primary-nav"', content)
        self.assertIn('aria-expanded="false"', content)
        self.assertIn('aria-label="Open menu"', content)
        self.assertIn('id="primary-nav"', content)
        # The primary nav is marked collapsible for the mobile drawer.
        self.assertIn("nav-collapsible", content)

    def test_chinese_header_has_mobile_nav_toggle_button(self):
        self.set_language("zh")
        self.client.login(username="levin", password="OldPass123!")

        response = self.client.get(reverse("profile"))
        content = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertIn('class="nav-toggle"', content)
        self.assertIn('aria-controls="primary-nav"', content)
        self.assertIn('aria-label="打开菜单"', content)

    def test_anonymous_header_has_no_mobile_nav_toggle(self):
        # The drawer is scoped to authenticated users; the login page keeps its
        # compact controls visible without a hamburger.
        self.set_language("en")

        response = self.client.get(reverse("login"))
        content = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertNotIn('class="nav-toggle"', content)
        self.assertNotIn("nav-collapsible", content)

    def test_mobile_nav_drawer_js_controls_present(self):
        self.set_language("en")
        self.client.login(username="levin", password="OldPass123!")

        response = self.client.get(reverse("profile"))
        content = response.content.decode()

        # Open/close/toggle controller + state, reusing the existing helpers.
        self.assertIn("function openPrimaryNav()", content)
        self.assertIn("function closePrimaryNav()", content)
        self.assertIn("function togglePrimaryNav()", content)
        self.assertIn("primary-nav-open", content)
        self.assertIn("var primaryNavOpen = false;", content)
        self.assertIn('navToggle.setAttribute("aria-expanded"', content)
        # Outside-click + Escape close.
        self.assertIn("onPrimaryNavOutsideClick", content)
        self.assertIn('event.key === "Escape"', content)
        # Menu-open keeps the header from auto-hiding.
        self.assertIn("primaryNavOpen ||", content)
        # Staff overlay must not engage while the drawer is open.
        self.assertIn("&& !primaryNavOpen", content)

    def test_mobile_nav_drawer_css_present(self):
        css_path = Path(__file__).resolve().parent.parent / "static" / "css" / "app.css"
        css = css_path.read_text(encoding="utf-8")

        # Hamburger styling + collapsed-by-default + drawer-when-open.
        self.assertIn(".nav-toggle {", css)
        self.assertIn(".nav-collapsible {", css)
        self.assertIn("body.primary-nav-open .nav-collapsible {", css)
        # Header auto-hide is suppressed while the drawer is open.
        self.assertIn("body.primary-nav-open .site-header", css)
        # Body scroll is locked while the drawer is open.
        self.assertIn("body.primary-nav-open {", css)
        # Staff menu expands inline inside the drawer (not the fixed overlay).
        self.assertIn(
            "body.primary-nav-open .nav-staff-menu[open] .nav-staff-menu-panel {",
            css,
        )
        # Hamburger hidden by default (desktop) and shown at mobile width.
        self.assertIn(".nav-toggle {\n    display: none;", css)
        self.assertIn(".nav-toggle {\n        display: inline-flex;", css)

    def test_normal_chinese_user_sees_simple_primary_nav(self):
        self.set_language("zh")
        self.client.login(username="levin", password="OldPass123!")

        response = self.client.get(reverse("profile"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "今日")
        self.assertContains(response, "读经")
        self.assertContains(response, "查经")
        self.assertContains(response, "代祷")
        self.assertContains(response, "我的服事")
        self.assertContains(response, "个人资料")

    def test_staff_chinese_user_sees_staff_menu_links(self):
        self.set_language("zh")
        self.client.login(username="staff", password="StaffPass123!")

        response = self.client.get(reverse("profile"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "同工管理")
        self.assertContains(response, "内容管理")
        self.assertContains(response, "读经计划管理")
        self.assertContains(response, "查经安排")
        self.assertContains(response, "每周查经指引")
        self.assertContains(response, "小组查经聚会")
        self.assertNotContains(response, "旧版查经安排")
        self.assertNotContains(response, "查经管理")
        content = response.content.decode()
        self.assertLess(content.index("查经安排"), content.index("每周查经指引"))
        self.assertLess(content.index("每周查经指引"), content.index("小组查经聚会"))
        self.assertContains(response, "事工运作")
        self.assertContains(response, "教会聚会")
        self.assertContains(response, "事工团队")
        self.assertContains(response, "服事排班")
        # 灯光试点导入已从可发现的同工菜单中退役；路由仍在，但不再链接。
        self.assertNotContains(response, "灯光试点导入")
        self.assertContains(response, "教会结构")
        self.assertContains(response, "教会结构设置与检查")
        self.assertContains(response, reverse("staff_structure_map"))
        self.assertContains(response, "用户与审核")
        self.assertContains(response, "用户管理")
        self.assertContains(response, "默想举报")
        self.assertContains(response, "代祷举报")
        # 同工总览 is a dashboard entry, rendered ahead of 内容管理.
        self.assertLess(content.index("同工总览"), content.index("内容管理"))

    def test_core_logged_in_pages_still_render(self):
        self.set_language("en")
        self.client.login(username="levin", password="OldPass123!")

        for url_name in [
            "home",
            "my_plans",
            "study_session_list",
            "prayer_list",
            "my_serving",
            "profile",
        ]:
            response = self.client.get(reverse(url_name))
            self.assertEqual(response.status_code, 200)

    def test_today_page_marks_today_nav_active(self):
        self.set_language("en")
        self.client.login(username="levin", password="OldPass123!")

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assert_active_nav_href(response, "home")

    def test_reading_page_marks_reading_nav_active(self):
        self.set_language("en")
        self.client.login(username="levin", password="OldPass123!")

        response = self.client.get(reverse("my_plans"))

        self.assertEqual(response.status_code, 200)
        self.assert_active_nav_href(response, "my_plans")

    def test_bible_study_page_marks_bible_study_nav_active(self):
        self.set_language("en")
        self.client.login(username="levin", password="OldPass123!")

        response = self.client.get(reverse("study_session_list"))

        self.assertEqual(response.status_code, 200)
        self.assert_active_nav_href(response, "study_session_list")

    def test_prayer_page_marks_prayer_nav_active(self):
        self.set_language("en")
        self.client.login(username="levin", password="OldPass123!")

        response = self.client.get(reverse("prayer_list"))

        self.assertEqual(response.status_code, 200)
        self.assert_active_nav_href(response, "prayer_list")

    def test_my_serving_page_marks_my_serving_nav_active(self):
        self.set_language("en")
        self.client.login(username="levin", password="OldPass123!")

        response = self.client.get(reverse("my_serving"))

        self.assertEqual(response.status_code, 200)
        self.assert_active_nav_href(response, "my_serving")

    def test_profile_page_marks_profile_nav_active(self):
        self.set_language("en")
        self.client.login(username="levin", password="OldPass123!")

        response = self.client.get(reverse("profile"))
        content = response.content.decode()

        self.assertEqual(response.status_code, 200)
        # Profile now lives in the account dropdown, so the dropdown summary
        # carries the active state instead of a standalone nav link.
        self.assertEqual(content.count('class="nav-link active"'), 1)
        self.assertIn('<summary class="nav-link active">', content)
        self.assertIn('href="%s"' % reverse("profile"), content)

    def test_staff_management_page_marks_staff_nav_active(self):
        self.set_language("en")
        self.client.login(username="staff", password="StaffPass123!")

        response = self.client.get(reverse("staff_user_list"))
        content = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(content.count('class="nav-link active"'), 1)
        self.assertIn('<summary class="nav-link active">', content)


    def test_normal_chinese_user_sees_my_serving_in_top_nav(self):
        self.set_language("zh")
        self.client.login(username="levin", password="OldPass123!")

        response = self.client.get(reverse("profile"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "我的服事")

class ChurchStructureUnitFoundationTests(TestCase):
    def test_church_structure_unit_can_be_created_as_root(self):
        root = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_ROOT,
            code="church",
            name="全教会",
            name_en="Whole Church",
        )

        self.assertEqual(root.code, "CHURCH")
        self.assertIsNone(root.parent)
        self.assertEqual(str(root), "CHURCH - 全教会")
        self.assertEqual(root.display_name("zh"), "全教会")
        self.assertEqual(root.display_name("en"), "Whole Church")

    def test_child_unit_can_be_created_under_parent(self):
        root = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_ROOT,
            code="CHURCH",
            name="全教会",
            name_en="Whole Church",
        )
        child = ChurchStructureUnit.objects.create(
            parent=root,
            unit_type=ChurchStructureUnit.UNIT_MINISTRY_CONTEXT,
            code="cm",
            name="中文事工",
            name_en="Chinese Ministry",
            sort_order=10,
        )

        self.assertEqual(child.code, "CM")
        self.assertEqual(child.parent, root)
        self.assertIn(child, root.children.all())

    def test_same_code_is_allowed_under_different_parents(self):
        root = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_ROOT,
            code="CHURCH",
            name="全教会",
        )
        cm = ChurchStructureUnit.objects.create(
            parent=root,
            unit_type=ChurchStructureUnit.UNIT_MINISTRY_CONTEXT,
            code="CM",
            name="中文事工",
        )
        em = ChurchStructureUnit.objects.create(
            parent=root,
            unit_type=ChurchStructureUnit.UNIT_MINISTRY_CONTEXT,
            code="EM",
            name="英文事工",
        )

        ChurchStructureUnit.objects.create(
            parent=cm,
            unit_type=ChurchStructureUnit.UNIT_DISTRICT,
            code="D1",
            name="第一区",
        )
        ChurchStructureUnit.objects.create(
            parent=em,
            unit_type=ChurchStructureUnit.UNIT_DISTRICT,
            code="D1",
            name="District 1",
        )

        self.assertEqual(ChurchStructureUnit.objects.filter(code="D1").count(), 2)

    def test_self_parent_validation_rejects_direct_self_parent(self):
        unit = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_CUSTOM,
            code="CUSTOM",
            name="Custom Unit",
        )
        unit.parent = unit

        with self.assertRaises(ValidationError):
            unit.full_clean()

    def test_indirect_cycle_validation_rejects_self_as_ancestor(self):
        top = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_CUSTOM,
            code="TOP",
            name="Top",
        )
        branch = ChurchStructureUnit.objects.create(
            parent=top,
            unit_type=ChurchStructureUnit.UNIT_CUSTOM,
            code="BRANCH",
            name="Branch",
        )
        leaf = ChurchStructureUnit.objects.create(
            parent=branch,
            unit_type=ChurchStructureUnit.UNIT_CUSTOM,
            code="LEAF",
            name="Leaf",
        )

        ChurchStructureUnit.objects.filter(pk=top.pk).update(parent=leaf)
        top.refresh_from_db()

        with self.assertRaises(ValidationError):
            top.full_clean()

    def test_get_ancestors_stops_on_corrupted_cycle(self):
        top = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_CUSTOM,
            code="TOP",
            name="Top",
            name_en="Top",
        )
        branch = ChurchStructureUnit.objects.create(
            parent=top,
            unit_type=ChurchStructureUnit.UNIT_CUSTOM,
            code="BRANCH",
            name="Branch",
            name_en="Branch",
        )
        leaf = ChurchStructureUnit.objects.create(
            parent=branch,
            unit_type=ChurchStructureUnit.UNIT_CUSTOM,
            code="LEAF",
            name="Leaf",
            name_en="Leaf",
        )

        ChurchStructureUnit.objects.filter(pk=top.pk).update(parent=leaf)
        top.refresh_from_db()

        self.assertEqual(top.get_ancestors(), [branch, leaf])
        self.assertEqual(top.path_label("en"), "Branch > Leaf > Top")

    def test_root_with_parent_is_invalid(self):
        root = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_ROOT,
            code="CHURCH",
            name="全教会",
        )
        child_root = ChurchStructureUnit(
            parent=root,
            unit_type=ChurchStructureUnit.UNIT_ROOT,
            code="ROOT2",
            name="Second Root",
        )

        with self.assertRaises(ValidationError):
            child_root.full_clean()

    def test_ancestor_and_path_label_helpers(self):
        root = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_ROOT,
            code="CHURCH",
            name="全教会",
            name_en="Whole Church",
        )
        context = ChurchStructureUnit.objects.create(
            parent=root,
            unit_type=ChurchStructureUnit.UNIT_MINISTRY_CONTEXT,
            code="CM",
            name="中文事工",
            name_en="Chinese Ministry",
        )
        district = ChurchStructureUnit.objects.create(
            parent=context,
            unit_type=ChurchStructureUnit.UNIT_DISTRICT,
            code="D1",
            name="第一区",
            name_en="District 1",
        )

        self.assertEqual(district.get_ancestors(), [root, context])
        self.assertEqual(
            district.path_label("en"),
            "Whole Church > Chinese Ministry > District 1",
        )


class ChurchStructureUnitCoworkerRoleFoundationTests(TestCase):
    def call_seed_command(self, *args):
        output = StringIO()
        call_command("seed_structure_unit_coworker_roles", *args, stdout=output)
        return output.getvalue()

    def test_seed_command_dry_run_does_not_write_defaults(self):
        output = self.call_seed_command()

        self.assertIn("Structure unit coworker role seed mode: DRY RUN", output)
        self.assertIn("Would create role type lead", output)
        self.assertEqual(ChurchStructureUnitRoleType.objects.count(), 0)
        self.assertEqual(ChurchStructureUnitRoleProfile.objects.count(), 0)
        self.assertEqual(ChurchStructureUnitRoleRequirement.objects.count(), 0)

    def test_seed_command_apply_creates_default_presets(self):
        output = self.call_seed_command("--apply")

        self.assertIn("Structure unit coworker role seed mode: APPLY", output)
        self.assertEqual(ChurchStructureUnitRoleType.objects.count(), 6)
        self.assertEqual(ChurchStructureUnitRoleProfile.objects.count(), 5)
        self.assertEqual(ChurchStructureUnitRoleRequirement.objects.count(), 10)

        lead = ChurchStructureUnitRoleType.objects.get(
            code=ChurchStructureUnitRoleType.CODE_LEAD
        )
        self.assertTrue(lead.is_system_default)
        self.assertTrue(lead.is_active)

        for profile in ChurchStructureUnitRoleProfile.objects.all():
            self.assertTrue(
                ChurchStructureUnitRoleRequirement.objects.filter(
                    profile=profile,
                    role_type=lead,
                    is_required=True,
                    is_active=True,
                ).exists(),
                msg=f"{profile.code} must require Lead",
            )

        small_group_profile = ChurchStructureUnitRoleProfile.objects.get(
            code=ChurchStructureUnitRoleProfile.CODE_SMALL_GROUP_UNIT
        )
        required_codes = set(
            ChurchStructureUnitRoleRequirement.objects.filter(
                profile=small_group_profile,
                is_required=True,
                is_active=True,
            ).values_list("role_type__code", flat=True)
        )
        self.assertEqual(
            required_codes,
            {
                ChurchStructureUnitRoleType.CODE_LEAD,
                ChurchStructureUnitRoleType.CODE_ASSISTANT_LEAD,
                ChurchStructureUnitRoleType.CODE_CARING,
                ChurchStructureUnitRoleType.CODE_EDIFY,
                ChurchStructureUnitRoleType.CODE_OUTREACH,
            },
        )
        worship_requirement = ChurchStructureUnitRoleRequirement.objects.get(
            profile=small_group_profile,
            role_type__code=ChurchStructureUnitRoleType.CODE_WORSHIP,
        )
        self.assertFalse(worship_requirement.is_required)

    def test_seed_command_is_idempotent_after_apply(self):
        self.call_seed_command("--apply")
        second_dry_run = self.call_seed_command()
        second_apply = self.call_seed_command("--apply")

        self.assertIn("role types skipped: 6", second_dry_run)
        self.assertIn("profiles skipped: 5", second_dry_run)
        self.assertIn("requirements skipped: 10", second_dry_run)
        self.assertIn("role types skipped: 6", second_apply)
        self.assertEqual(ChurchStructureUnitRoleType.objects.count(), 6)
        self.assertEqual(ChurchStructureUnitRoleProfile.objects.count(), 5)
        self.assertEqual(ChurchStructureUnitRoleRequirement.objects.count(), 10)

    def test_seed_command_apply_does_not_mutate_units_or_assign_coworkers(self):
        unit = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="COWORKER-SEED-SG",
            name="Seed Group",
        )

        self.call_seed_command("--apply")

        unit.refresh_from_db()
        self.assertIsNone(unit.role_profile)
        self.assertEqual(ChurchStructureUnitRoleAssignment.objects.count(), 0)

    def test_multiple_users_can_hold_same_role_on_same_unit(self):
        role_type = ChurchStructureUnitRoleType.objects.create(
            code=ChurchStructureUnitRoleType.CODE_LEAD,
            name="负责人",
            name_en="Lead",
        )
        unit = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="COWORKER-SG",
            name="Coworker Group",
        )
        first_user = User.objects.create_user(username="coworker_lead_one")
        second_user = User.objects.create_user(username="coworker_lead_two")

        ChurchStructureUnitRoleAssignment.objects.create(
            unit=unit,
            role_type=role_type,
            user=first_user,
        )
        ChurchStructureUnitRoleAssignment.objects.create(
            unit=unit,
            role_type=role_type,
            user=second_user,
        )

        self.assertEqual(
            ChurchStructureUnitRoleAssignment.objects.filter(
                unit=unit,
                role_type=role_type,
                is_active=True,
            ).count(),
            2,
        )

    def test_same_user_cannot_hold_overlapping_active_duplicate_assignment(self):
        today = timezone.localdate()
        role_type = ChurchStructureUnitRoleType.objects.create(
            code=ChurchStructureUnitRoleType.CODE_LEAD,
            name="负责人",
            name_en="Lead",
        )
        unit = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="COWORKER-DUP",
            name="Duplicate Group",
        )
        user = User.objects.create_user(username="coworker_dup_user")
        ChurchStructureUnitRoleAssignment.objects.create(
            unit=unit,
            role_type=role_type,
            user=user,
            start_date=today,
        )

        duplicate = ChurchStructureUnitRoleAssignment(
            unit=unit,
            role_type=role_type,
            user=user,
            start_date=today + timedelta(days=7),
        )

        with self.assertRaises(ValidationError) as context:
            duplicate.full_clean()

        self.assertIn("user", context.exception.message_dict)

    def test_same_user_can_have_non_overlapping_historical_and_current_assignment(self):
        today = timezone.localdate()
        role_type = ChurchStructureUnitRoleType.objects.create(
            code=ChurchStructureUnitRoleType.CODE_LEAD,
            name="负责人",
            name_en="Lead",
        )
        unit = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="COWORKER-HISTORY",
            name="History Group",
        )
        user = User.objects.create_user(username="coworker_history_user")
        ChurchStructureUnitRoleAssignment.objects.create(
            unit=unit,
            role_type=role_type,
            user=user,
            start_date=today - timedelta(days=30),
            end_date=today - timedelta(days=1),
        )

        current = ChurchStructureUnitRoleAssignment.objects.create(
            unit=unit,
            role_type=role_type,
            user=user,
            start_date=today,
        )

        self.assertTrue(current.active_for_date(today))

    def test_inactive_duplicate_assignment_does_not_block_active_assignment(self):
        today = timezone.localdate()
        role_type = ChurchStructureUnitRoleType.objects.create(
            code=ChurchStructureUnitRoleType.CODE_LEAD,
            name="负责人",
            name_en="Lead",
        )
        unit = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="COWORKER-INACTIVE-DUP",
            name="Inactive Duplicate Group",
        )
        user = User.objects.create_user(username="coworker_inactive_dup_user")
        ChurchStructureUnitRoleAssignment.objects.create(
            unit=unit,
            role_type=role_type,
            user=user,
            is_active=False,
            start_date=today,
        )

        active = ChurchStructureUnitRoleAssignment.objects.create(
            unit=unit,
            role_type=role_type,
            user=user,
            start_date=today,
        )

        self.assertTrue(active.is_active)

    def test_role_assignment_does_not_create_other_runtime_assignments(self):
        role_type = ChurchStructureUnitRoleType.objects.create(
            code=ChurchStructureUnitRoleType.CODE_EDIFY,
            name="带查经同工",
            name_en="Edify",
        )
        unit = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="COWORKER-B",
            name="Coworker Boundary",
        )
        user = User.objects.create_user(username="coworker_boundary")

        ChurchStructureUnitRoleAssignment.objects.create(
            unit=unit,
            role_type=role_type,
            user=user,
        )

        self.assertFalse(ChurchStructureMembership.objects.filter(user=user).exists())
        self.assertFalse(ChurchRoleAssignment.objects.filter(user=user).exists())
        self.assertEqual(TeamAssignment.objects.count(), 0)
        self.assertEqual(TeamAssignmentMember.objects.count(), 0)
        self.assertEqual(BibleStudyMeetingRole.objects.count(), 0)

    def test_unit_with_children_can_use_small_group_role_profile(self):
        profile = ChurchStructureUnitRoleProfile.objects.create(
            code=ChurchStructureUnitRoleProfile.CODE_SMALL_GROUP_UNIT,
            name="小组型单元",
            name_en="Small-Group Unit",
        )
        parent_unit = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="COWORKER-PARENT",
            name="Parent Group",
            role_profile=profile,
        )
        child_unit = ChurchStructureUnit.objects.create(
            parent=parent_unit,
            unit_type=ChurchStructureUnit.UNIT_CUSTOM,
            code="COWORKER-CHILD",
            name="Child Unit",
        )

        self.assertEqual(parent_unit.role_profile, profile)
        self.assertIn(child_unit, parent_unit.children.all())

    def test_childless_unit_is_not_treated_as_small_group_without_role_profile(self):
        role_type = ChurchStructureUnitRoleType.objects.create(
            code=ChurchStructureUnitRoleType.CODE_LEAD,
            name="负责人",
            name_en="Lead",
        )
        profile = ChurchStructureUnitRoleProfile.objects.create(
            code=ChurchStructureUnitRoleProfile.CODE_SMALL_GROUP_UNIT,
            name="小组型单元",
            name_en="Small-Group Unit",
        )
        ChurchStructureUnitRoleRequirement.objects.create(
            profile=profile,
            role_type=role_type,
            is_required=True,
        )
        childless_unit = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_DEPARTMENT,
            code="COWORKER-DEPT",
            name="Childless Department",
        )

        self.assertEqual(list(childless_unit.children.all()), [])
        self.assertIsNone(childless_unit.role_profile)
        self.assertEqual(childless_unit.missing_required_role_types(), [])

    def test_missing_required_roles_are_reported_without_auto_assignment(self):
        lead = ChurchStructureUnitRoleType.objects.create(
            code=ChurchStructureUnitRoleType.CODE_LEAD,
            name="负责人",
            name_en="Lead",
        )
        profile = ChurchStructureUnitRoleProfile.objects.create(
            code=ChurchStructureUnitRoleProfile.CODE_SMALL_GROUP_UNIT,
            name="小组型单元",
            name_en="Small-Group Unit",
        )
        ChurchStructureUnitRoleRequirement.objects.create(
            profile=profile,
            role_type=lead,
            is_required=True,
        )
        unit = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="COWORKER-MISSING",
            name="Missing Lead Group",
            role_profile=profile,
        )
        user = User.objects.create_user(username="missing_lead_user")

        self.assertEqual(unit.missing_required_role_types(), [lead])
        self.assertEqual(ChurchStructureUnitRoleAssignment.objects.count(), 0)

        ChurchStructureUnitRoleAssignment.objects.create(
            unit=unit,
            role_type=lead,
            user=user,
        )

        self.assertEqual(unit.missing_required_role_types(), [])

    def test_active_assignment_rejects_inactive_role_type(self):
        inactive_role = ChurchStructureUnitRoleType.objects.create(
            code="inactive_role",
            name="Inactive Role",
            is_active=False,
        )
        unit = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="COWORKER-INACTIVE",
            name="Inactive Role Group",
        )
        user = User.objects.create_user(username="inactive_role_user")
        assignment = ChurchStructureUnitRoleAssignment(
            unit=unit,
            role_type=inactive_role,
            user=user,
        )

        with self.assertRaises(ValidationError) as context:
            assignment.full_clean()

        self.assertIn("role_type", context.exception.message_dict)


class ChurchStructureSelectorLayerTests(TestCase):
    def setUp(self):
        self.root_unit = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_ROOT,
            code="CHURCH",
            name="Whole Church",
        )
        self.cm_unit = ChurchStructureUnit.objects.create(
            parent=self.root_unit,
            unit_type=ChurchStructureUnit.UNIT_MINISTRY_CONTEXT,
            code="CM",
            name="Chinese Ministry",
        )
        self.em_unit = ChurchStructureUnit.objects.create(
            parent=self.root_unit,
            unit_type=ChurchStructureUnit.UNIT_MINISTRY_CONTEXT,
            code="EM",
            name="English Ministry",
        )
        self.north_unit = ChurchStructureUnit.objects.create(
            parent=self.cm_unit,
            unit_type=ChurchStructureUnit.UNIT_DISTRICT,
            code="NORTH",
            name="North",
        )
        self.south_unit = ChurchStructureUnit.objects.create(
            parent=self.cm_unit,
            unit_type=ChurchStructureUnit.UNIT_DISTRICT,
            code="SOUTH",
            name="South",
        )
        self.group_unit = ChurchStructureUnit.objects.create(
            parent=self.north_unit,
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="R4",
            name="Rainbow 4",
        )
        self.sibling_group_unit = ChurchStructureUnit.objects.create(
            parent=self.north_unit,
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="R4B",
            name="Rainbow 4B",
        )
        self.other_group_unit = ChurchStructureUnit.objects.create(
            parent=self.south_unit,
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="R5",
            name="Rainbow 5",
        )
        self.unmapped_unit = ChurchStructureUnit.objects.create(
            parent=self.cm_unit,
            unit_type=ChurchStructureUnit.UNIT_CUSTOM,
            code="UNMAPPED",
            name="Unmapped Unit",
        )

        self.group_user = self.create_user("selector_group")
        self.sibling_user = self.create_user("selector_sibling")
        self.no_group_user = self.create_user("selector_no_group")
        self.unmapped_group_user = self.create_user("selector_unmapped_group")

    def create_user(self, username):
        user = User.objects.create_user(username=username, password="testpass123")
        return user

    def create_membership(self, user, unit, **overrides):
        data = {
            "user": user,
            "unit": unit,
            "status": ChurchStructureMembership.STATUS_ACTIVE,
            "is_primary": True,
            "start_date": timezone.localdate() - timedelta(days=1),
        }
        data.update(overrides)
        return ChurchStructureMembership.objects.create(**data)

    def test_get_user_primary_membership_unit_returns_single_active_primary(self):
        from accounts.structure_selectors import get_user_primary_membership_unit

        self.create_membership(self.no_group_user, self.group_unit)

        self.assertEqual(
            get_user_primary_membership_unit(self.no_group_user),
            self.group_unit,
        )
        # Profile.small_group alone is not a membership-core source.
        self.assertIsNone(get_user_primary_membership_unit(self.group_user))
        self.assertIsNone(get_user_primary_membership_unit(AnonymousUser()))
        self.assertIsNone(get_user_primary_membership_unit(object()))
        self.assertIsNone(
            get_user_primary_membership_unit(User(username="selector_unsaved"))
        )

    def test_get_user_primary_membership_unit_ignores_inactive_lifecycle_states(self):
        from accounts.structure_selectors import get_user_primary_membership_unit

        today = timezone.localdate()
        users = [
            User.objects.create_user(username=f"selector_lifecycle_{index}")
            for index in range(7)
        ]
        requested, rejected, cancelled, ended, future, expired, non_primary = users

        self.create_membership(
            requested,
            self.group_unit,
            status=ChurchStructureMembership.STATUS_REQUESTED,
            is_primary=False,
            start_date=None,
        )
        self.create_membership(
            ended,
            self.group_unit,
            status=ChurchStructureMembership.STATUS_ENDED,
            start_date=today - timedelta(days=10),
            end_date=today - timedelta(days=1),
        )
        self.create_membership(
            future,
            self.group_unit,
            start_date=today + timedelta(days=1),
        )
        self.create_membership(non_primary, self.group_unit, is_primary=False)
        # Rejected/cancelled primary and active-expired rows fail model
        # validation by design, so insert them directly like drifted data.
        ChurchStructureMembership.objects.bulk_create(
            [
                ChurchStructureMembership(
                    user=rejected,
                    unit=self.group_unit,
                    status=ChurchStructureMembership.STATUS_REJECTED,
                    is_primary=True,
                    start_date=today - timedelta(days=10),
                ),
                ChurchStructureMembership(
                    user=cancelled,
                    unit=self.group_unit,
                    status=ChurchStructureMembership.STATUS_CANCELLED,
                    is_primary=True,
                    start_date=today - timedelta(days=10),
                ),
                ChurchStructureMembership(
                    user=expired,
                    unit=self.group_unit,
                    status=ChurchStructureMembership.STATUS_ACTIVE,
                    is_primary=True,
                    start_date=today - timedelta(days=10),
                    end_date=today - timedelta(days=1),
                ),
            ]
        )

        for user in users:
            self.assertIsNone(
                get_user_primary_membership_unit(user),
                msg=f"{user.username} must not have a membership-core unit",
            )

    def test_get_user_primary_membership_unit_fails_closed_on_multiple(self):
        from accounts.structure_selectors import get_user_primary_membership_unit

        user = User.objects.create_user(username="selector_multi_primary")
        today = timezone.localdate()
        ChurchStructureMembership.objects.bulk_create(
            [
                ChurchStructureMembership(
                    user=user,
                    unit=self.group_unit,
                    status=ChurchStructureMembership.STATUS_ACTIVE,
                    is_primary=True,
                    start_date=today,
                ),
                ChurchStructureMembership(
                    user=user,
                    unit=self.sibling_group_unit,
                    status=ChurchStructureMembership.STATUS_ACTIVE,
                    is_primary=True,
                    start_date=today,
                ),
            ]
        )

        self.assertIsNone(get_user_primary_membership_unit(user))

    def test_get_user_membership_structure_units_derives_from_membership_only(self):
        from accounts.structure_selectors import get_user_membership_structure_units

        self.create_membership(self.no_group_user, self.group_unit)

        self.assertEqual(
            get_user_membership_structure_units(self.no_group_user),
            [self.group_unit],
        )
        self.assertEqual(
            get_user_membership_structure_units(
                self.no_group_user,
                include_ancestors=True,
            ),
            [self.root_unit, self.cm_unit, self.north_unit, self.group_unit],
        )
        # Profile.small_group alone yields nothing from membership-core.
        self.assertEqual(
            get_user_membership_structure_units(
                self.group_user,
                include_ancestors=True,
            ),
            [],
        )

    def test_membership_audience_matches_own_unit_and_ancestor_units(self):
        from accounts.structure_selectors import (
            user_matches_membership_structure_audience,
        )

        member = User.objects.create_user(username="selector_member_match")
        self.create_membership(member, self.group_unit)

        self.assertTrue(
            user_matches_membership_structure_audience(member, [self.group_unit])
        )
        self.assertTrue(
            user_matches_membership_structure_audience(member, [self.north_unit])
        )
        self.assertTrue(
            user_matches_membership_structure_audience(member, [self.cm_unit])
        )
        self.assertTrue(
            user_matches_membership_structure_audience(member, [self.root_unit])
        )

    def test_membership_audience_root_matches_user_without_membership(self):
        from accounts.structure_selectors import (
            user_matches_membership_structure_audience,
        )

        self.assertTrue(
            user_matches_membership_structure_audience(
                self.no_group_user, [self.root_unit]
            )
        )
        self.assertFalse(
            user_matches_membership_structure_audience(
                AnonymousUser(), [self.root_unit]
            )
        )

    def test_membership_audience_sibling_branch_does_not_match(self):
        from accounts.structure_selectors import (
            user_matches_membership_structure_audience,
        )

        member = User.objects.create_user(username="selector_sibling_branch")
        self.create_membership(member, self.group_unit)

        self.assertFalse(
            user_matches_membership_structure_audience(
                member, [self.sibling_group_unit]
            )
        )
        self.assertFalse(
            user_matches_membership_structure_audience(member, [self.south_unit])
        )
        self.assertFalse(
            user_matches_membership_structure_audience(member, [self.em_unit])
        )
        self.assertFalse(
            user_matches_membership_structure_audience(member, [self.unmapped_unit])
        )

    def test_membership_audience_unmapped_or_fellowship_unit_matches_by_membership(
        self,
    ):
        from accounts.structure_selectors import (
            user_matches_membership_structure_audience,
            user_matches_structure_audience,
        )

        member = User.objects.create_user(username="selector_unmapped_member")
        self.create_membership(member, self.unmapped_unit)

        self.assertTrue(
            user_matches_membership_structure_audience(member, [self.unmapped_unit])
        )
        self.assertTrue(user_matches_structure_audience(member, [self.unmapped_unit]))

    def test_membership_audience_requested_membership_does_not_match(self):
        from accounts.structure_selectors import (
            user_matches_membership_structure_audience,
        )

        self.create_membership(
            self.no_group_user,
            self.group_unit,
            status=ChurchStructureMembership.STATUS_REQUESTED,
            is_primary=False,
            start_date=None,
        )

        self.assertFalse(
            user_matches_membership_structure_audience(
                self.no_group_user, [self.group_unit]
            )
        )

    def test_membership_audience_inactive_lifecycle_states_do_not_match(self):
        from accounts.structure_selectors import (
            user_matches_membership_structure_audience,
        )

        today = timezone.localdate()
        ended = User.objects.create_user(username="selector_audience_ended")
        future = User.objects.create_user(username="selector_audience_future")
        self.create_membership(
            ended,
            self.group_unit,
            status=ChurchStructureMembership.STATUS_ENDED,
            start_date=today - timedelta(days=10),
            end_date=today - timedelta(days=1),
        )
        self.create_membership(
            future,
            self.group_unit,
            start_date=today + timedelta(days=1),
        )
        rejected = User.objects.create_user(username="selector_audience_rejected")
        cancelled = User.objects.create_user(username="selector_audience_cancelled")
        expired = User.objects.create_user(username="selector_audience_expired")
        ChurchStructureMembership.objects.bulk_create(
            [
                ChurchStructureMembership(
                    user=rejected,
                    unit=self.group_unit,
                    status=ChurchStructureMembership.STATUS_REJECTED,
                    is_primary=True,
                    start_date=today - timedelta(days=10),
                ),
                ChurchStructureMembership(
                    user=cancelled,
                    unit=self.group_unit,
                    status=ChurchStructureMembership.STATUS_CANCELLED,
                    is_primary=True,
                    start_date=today - timedelta(days=10),
                ),
                ChurchStructureMembership(
                    user=expired,
                    unit=self.group_unit,
                    status=ChurchStructureMembership.STATUS_ACTIVE,
                    is_primary=True,
                    start_date=today - timedelta(days=10),
                    end_date=today - timedelta(days=1),
                ),
            ]
        )

        for user in (ended, future, rejected, cancelled, expired):
            self.assertFalse(
                user_matches_membership_structure_audience(user, [self.group_unit]),
                msg=f"{user.username} must not match the structure audience",
            )

    def test_membership_audience_profile_small_group_alone_does_not_match(self):
        from accounts.structure_selectors import (
            user_matches_membership_structure_audience,
        )

        self.assertFalse(
            user_matches_membership_structure_audience(
                self.group_user, [self.group_unit]
            )
        )
        self.assertFalse(
            user_matches_membership_structure_audience(
                self.group_user, [self.north_unit]
            )
        )

    def test_membership_audience_multiple_active_primaries_fail_closed(self):
        from accounts.structure_selectors import (
            user_matches_membership_structure_audience,
        )

        user = User.objects.create_user(username="selector_audience_multi")
        today = timezone.localdate()
        ChurchStructureMembership.objects.bulk_create(
            [
                ChurchStructureMembership(
                    user=user,
                    unit=self.group_unit,
                    status=ChurchStructureMembership.STATUS_ACTIVE,
                    is_primary=True,
                    start_date=today,
                ),
                ChurchStructureMembership(
                    user=user,
                    unit=self.sibling_group_unit,
                    status=ChurchStructureMembership.STATUS_ACTIVE,
                    is_primary=True,
                    start_date=today,
                ),
            ]
        )

        # Both units sit under north, so either row alone would match; the
        # ambiguous pair must still fail closed for non-root audiences.
        self.assertFalse(
            user_matches_membership_structure_audience(user, [self.north_unit])
        )
        self.assertTrue(
            user_matches_membership_structure_audience(user, [self.root_unit])
        )

    def test_user_matches_structure_audience_is_membership_core(self):
        from accounts.structure_selectors import user_matches_structure_audience

        self.create_membership(self.no_group_user, self.group_unit)

        self.assertFalse(
            user_matches_structure_audience(AnonymousUser(), [self.root_unit])
        )
        self.assertTrue(
            user_matches_structure_audience(self.no_group_user, [self.root_unit])
        )
        # The canonical matcher is membership-core as of CS-CORE.2B-A:
        # active primary membership matches, Profile.small_group alone does not.
        self.assertTrue(
            user_matches_structure_audience(self.no_group_user, [self.group_unit])
        )
        self.assertTrue(
            user_matches_structure_audience(self.no_group_user, [self.north_unit])
        )
        self.assertFalse(
            user_matches_structure_audience(self.group_user, [self.group_unit])
        )
        self.assertFalse(
            user_matches_structure_audience(self.no_group_user, [self.unmapped_unit])
        )

class ChurchStructureUnitSeedingCommandTests(TestCase):
    def run_seed_command(self, *args):
        output = StringIO()
        call_command("seed_church_structure_units", *args, stdout=output)
        return output.getvalue()

    def test_dry_run_previews_root_without_reading_legacy_rows(self):
        output = self.run_seed_command("--dry-run")

        self.assertIn("Church structure unit seeding mode: DRY RUN", output)
        self.assertIn("Would create root CHURCH", output)
        self.assertIn("legacy row source: retired", output)
        self.assertEqual(ChurchStructureUnit.objects.count(), 0)

    def test_apply_seeds_only_canonical_root(self):
        output = self.run_seed_command("--apply")

        self.assertIn("Church structure unit seeding mode: APPLY", output)
        self.assertIn("legacy row source: retired", output)

        root = ChurchStructureUnit.objects.get(
            parent__isnull=True,
            code="CHURCH",
        )
        self.assertEqual(root.unit_type, ChurchStructureUnit.UNIT_ROOT)
        self.assertEqual(root.name, "全教会")
        self.assertEqual(root.name_en, "Whole Church")

    def test_apply_reports_legacy_rows_retired(self):
        output = self.run_seed_command("--apply")

        self.assertIn("legacy row source: retired", output)
        self.assertIn("legacy rows linked: 0", output)

    def test_apply_updates_existing_root_but_not_existing_child_units(self):
        root = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_CUSTOM,
            code="CHURCH",
            name="Old Root",
            name_en="Old Root",
            is_active=False,
            sort_order=99,
        )
        mapped_unit = ChurchStructureUnit.objects.create(
            parent=root,
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="R4",
            name="Old Rainbow",
        )

        self.run_seed_command("--apply")

        root.refresh_from_db()
        mapped_unit.refresh_from_db()

        self.assertEqual(root.unit_type, ChurchStructureUnit.UNIT_ROOT)
        self.assertEqual(root.name, "全教会")
        self.assertEqual(root.name_en, "Whole Church")
        self.assertTrue(root.is_active)
        self.assertEqual(root.sort_order, 0)
        self.assertEqual(mapped_unit.name, "Old Rainbow")

    def test_apply_is_idempotent(self):
        self.run_seed_command("--apply")
        first_unit_count = ChurchStructureUnit.objects.count()

        second_output = self.run_seed_command("--apply")
        dry_run_output = self.run_seed_command("--dry-run")

        self.assertEqual(ChurchStructureUnit.objects.count(), first_unit_count)
        self.assertIn("created: 0", second_output)
        self.assertIn("would created: 0", dry_run_output)
        self.assertIn("legacy rows linked: 0", dry_run_output)

    def test_apply_preserves_existing_runtime_behavior(self):
        user = User.objects.create_user(
            username="seeded_member",
            password="TestPass123!",
        )
        other_user = User.objects.create_user(
            username="seeded_other_member",
            password="TestPass123!",
        )

        event = ServiceEvent.objects.create(
            title="District Service",
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
            start_datetime=timezone.now(),
            status=ServiceEvent.STATUS_PUBLISHED,
        )

        self.run_seed_command("--apply")

        # SE-RETIRE.1B: the seed command still does not create ServiceEvent
        # audience rows, so this zero-row event fails closed for ordinary users
        # (the zero-row legacy fallback via Profile.small_group is retired).
        self.assertFalse(event.can_be_seen_by(user))
        self.assertFalse(event.can_be_seen_by(other_user))


class ChurchStructureMembershipFoundationTests(TestCase):
    def create_unit(self, code="RAINBOW4", name="Rainbow 4", is_active=True):
        return ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code=code,
            name=name,
            is_active=is_active,
        )

    def test_can_create_requested_membership(self):
        user = User.objects.create_user(username="requested_member")
        unit = self.create_unit()

        membership = ChurchStructureMembership.objects.create(
            user=user,
            unit=unit,
            membership_type=ChurchStructureMembership.TYPE_SMALL_GROUP_MEMBER,
            status=ChurchStructureMembership.STATUS_REQUESTED,
            requested_by=user,
            notes="New attendee asked for this group.",
        )

        self.assertTrue(membership.is_requested)
        self.assertFalse(membership.is_active_membership)
        self.assertIn(membership, user.church_structure_memberships.all())
        self.assertIn(membership, unit.memberships.all())

    def test_requested_membership_does_not_count_as_active_for_date(self):
        user = User.objects.create_user(username="requested_not_active")
        unit = self.create_unit()
        membership = ChurchStructureMembership.objects.create(
            user=user,
            unit=unit,
            status=ChurchStructureMembership.STATUS_REQUESTED,
            start_date=timezone.localdate(),
            is_primary=True,
        )

        self.assertFalse(membership.active_for_date(timezone.localdate()))

    def test_inactive_statuses_do_not_count_as_active(self):
        user = User.objects.create_user(username="inactive_statuses")
        today = timezone.localdate()

        for status in [
            ChurchStructureMembership.STATUS_REJECTED,
            ChurchStructureMembership.STATUS_CANCELLED,
            ChurchStructureMembership.STATUS_ENDED,
        ]:
            unit = self.create_unit(f"UNIT-{status}", f"Unit {status}")
            membership = ChurchStructureMembership.objects.create(
                user=user,
                unit=unit,
                status=status,
                start_date=today - timedelta(days=10),
                end_date=today - timedelta(days=1),
            )

            self.assertFalse(membership.is_active_membership)
            self.assertFalse(membership.active_for_date(today))

    def test_active_membership_with_future_start_date_is_not_active_today(self):
        user = User.objects.create_user(username="future_start")
        unit = self.create_unit()
        membership = ChurchStructureMembership.objects.create(
            user=user,
            unit=unit,
            status=ChurchStructureMembership.STATUS_ACTIVE,
            start_date=timezone.localdate() + timedelta(days=1),
        )

        self.assertFalse(membership.is_active_membership)
        self.assertFalse(
            ChurchStructureMembership.active_for_user(user).filter(pk=membership.pk).exists()
        )

    def test_active_membership_with_current_date_window_is_active(self):
        user = User.objects.create_user(username="current_window")
        unit = self.create_unit()
        membership = ChurchStructureMembership.objects.create(
            user=user,
            unit=unit,
            status=ChurchStructureMembership.STATUS_ACTIVE,
            start_date=timezone.localdate() - timedelta(days=1),
            end_date=timezone.localdate() + timedelta(days=1),
        )

        self.assertTrue(membership.is_active_membership)
        self.assertIn(membership, ChurchStructureMembership.active_for_user(user))

    def test_can_create_active_primary_membership(self):
        user = User.objects.create_user(username="active_primary")
        unit = self.create_unit()

        membership = ChurchStructureMembership.objects.create(
            user=user,
            unit=unit,
            status=ChurchStructureMembership.STATUS_ACTIVE,
            is_primary=True,
            start_date=timezone.localdate(),
            approved_by=user,
            approved_at=timezone.now(),
        )

        self.assertTrue(membership.is_active_membership)
        self.assertTrue(membership.is_current_primary)

    def test_current_primary_for_user_returns_active_primary_membership(self):
        user = User.objects.create_user(username="current_primary")
        primary = ChurchStructureMembership.objects.create(
            user=user,
            unit=self.create_unit("PRIMARY", "Primary"),
            status=ChurchStructureMembership.STATUS_ACTIVE,
            is_primary=True,
            start_date=timezone.localdate(),
        )
        ChurchStructureMembership.objects.create(
            user=user,
            unit=self.create_unit("NONPRIMARY", "Non-primary"),
            status=ChurchStructureMembership.STATUS_ACTIVE,
            is_primary=False,
            start_date=timezone.localdate(),
        )

        self.assertEqual(
            ChurchStructureMembership.current_primary_for_user(user),
            primary,
        )

    def test_current_primary_for_user_ignores_requested_primary_membership(self):
        user = User.objects.create_user(username="requested_primary")
        ChurchStructureMembership.objects.create(
            user=user,
            unit=self.create_unit(),
            status=ChurchStructureMembership.STATUS_REQUESTED,
            is_primary=True,
            start_date=timezone.localdate(),
        )

        self.assertIsNone(ChurchStructureMembership.current_primary_for_user(user))

    def test_duplicate_active_primary_membership_for_same_user_is_rejected(self):
        user = User.objects.create_user(username="duplicate_primary")
        first_unit = self.create_unit("RAINBOW4", "Rainbow 4")
        second_unit = self.create_unit("RAINBOW5", "Rainbow 5")
        ChurchStructureMembership.objects.create(
            user=user,
            unit=first_unit,
            status=ChurchStructureMembership.STATUS_ACTIVE,
            is_primary=True,
            start_date=timezone.localdate(),
        )

        duplicate = ChurchStructureMembership(
            user=user,
            unit=second_unit,
            status=ChurchStructureMembership.STATUS_ACTIVE,
            is_primary=True,
            start_date=timezone.localdate(),
        )

        with self.assertRaises(ValidationError):
            duplicate.full_clean()

    def test_active_non_primary_membership_can_coexist(self):
        user = User.objects.create_user(username="non_primary_member")
        primary_unit = self.create_unit("RAINBOW4", "Rainbow 4")
        other_unit = self.create_unit("CHOIR", "Choir")
        ChurchStructureMembership.objects.create(
            user=user,
            unit=primary_unit,
            status=ChurchStructureMembership.STATUS_ACTIVE,
            is_primary=True,
            start_date=timezone.localdate(),
        )

        other = ChurchStructureMembership.objects.create(
            user=user,
            unit=other_unit,
            status=ChurchStructureMembership.STATUS_ACTIVE,
            is_primary=False,
            start_date=timezone.localdate(),
        )

        self.assertTrue(other.is_active_membership)

    def test_ended_historical_membership_can_coexist(self):
        user = User.objects.create_user(username="ended_member")
        old_unit = self.create_unit("OLDGROUP", "Old Group")
        new_unit = self.create_unit("NEWGROUP", "New Group")
        yesterday = timezone.localdate() - timedelta(days=1)
        ChurchStructureMembership.objects.create(
            user=user,
            unit=old_unit,
            status=ChurchStructureMembership.STATUS_ENDED,
            is_primary=True,
            start_date=yesterday - timedelta(days=30),
            end_date=yesterday,
        )

        active = ChurchStructureMembership.objects.create(
            user=user,
            unit=new_unit,
            status=ChurchStructureMembership.STATUS_ACTIVE,
            is_primary=True,
            start_date=timezone.localdate(),
        )

        self.assertTrue(active.is_active_membership)
        self.assertEqual(user.church_structure_memberships.count(), 2)

    def test_end_date_before_start_date_is_rejected(self):
        user = User.objects.create_user(username="bad_dates")
        unit = self.create_unit()
        today = timezone.localdate()
        membership = ChurchStructureMembership(
            user=user,
            unit=unit,
            status=ChurchStructureMembership.STATUS_ENDED,
            start_date=today,
            end_date=today - timedelta(days=1),
        )

        with self.assertRaises(ValidationError):
            membership.full_clean()

    def test_rejected_or_cancelled_primary_membership_is_rejected(self):
        user = User.objects.create_user(username="rejected_primary")
        unit = self.create_unit()

        for status in [
            ChurchStructureMembership.STATUS_REJECTED,
            ChurchStructureMembership.STATUS_CANCELLED,
        ]:
            membership = ChurchStructureMembership(
                user=user,
                unit=unit,
                status=status,
                is_primary=True,
            )
            with self.assertRaises(ValidationError):
                membership.full_clean()

    def test_active_membership_requires_start_date(self):
        user = User.objects.create_user(username="active_no_start")
        unit = self.create_unit()
        membership = ChurchStructureMembership(
            user=user,
            unit=unit,
            status=ChurchStructureMembership.STATUS_ACTIVE,
        )

        with self.assertRaises(ValidationError):
            membership.full_clean()

    def test_notes_help_text_warns_against_sensitive_information(self):
        help_text = ChurchStructureMembership._meta.get_field("notes").help_text

        self.assertIn("Operational/non-sensitive", help_text)
        self.assertIn("pastoral", help_text)
        self.assertIn("medical", help_text)
        self.assertIn("financial", help_text)

    def test_membership_does_not_change_service_event_visibility(self):
        unit = self.create_unit()
        user = User.objects.create_user(username="event_membership")
        ChurchStructureMembership.objects.create(
            user=user,
            unit=unit,
            status=ChurchStructureMembership.STATUS_ACTIVE,
            is_primary=True,
            start_date=timezone.localdate(),
        )
        event = ServiceEvent.objects.create(
            title="District Service",
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
            start_datetime=timezone.now(),
            status=ServiceEvent.STATUS_PUBLISHED,
        )

        self.assertFalse(event.can_be_seen_by(user))


        # SE-RETIRE.1B: with the zero-row legacy fallback retired, neither the
        # membership nor Profile.small_group grants visibility for a zero-row
        # event; it fails closed until it carries audience rows.
        self.assertFalse(event.can_be_seen_by(user))


class ChurchStructureAdminClarityTests(TestCase):
    def setUp(self):
        self.admin_user = User.objects.create_superuser(
            username="structure_admin",
            email="structure_admin@example.com",
            password="AdminPass123!",
        )
        self.client.login(username="structure_admin", password="AdminPass123!")

    def test_legacy_small_group_admin_is_retired(self):
        with self.assertRaises(Exception):
            reverse("admin:accounts_smallgroup_change", args=[1])

    def test_legacy_district_and_ministry_context_admins_are_retired(self):
        with self.assertRaises(Exception):
            reverse("admin:accounts_ministrycontext_change", args=[1])
        with self.assertRaises(Exception):
            reverse("admin:accounts_district_change", args=[1])

    def test_church_structure_unit_admin_explains_structure_foundation_status(self):
        unit = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="RAINBOW4",
            name="Rainbow 4",
        )

        response = self.client.get(
            reverse("admin:accounts_churchstructureunit_change", args=[unit.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Church Structure Units")
        self.assertContains(response, "教会结构单元")
        self.assertContains(response, "结构基础")
        self.assertContains(response, "flexible structure foundation")
        self.assertContains(response, "ChurchStructureUnit.parent hierarchy is authoritative")
        self.assertContains(response, "ServiceEvent audience rows use selected units")
        self.assertContains(response, "V2 Bible Study meeting visibility")
        self.assertContains(
            response,
            "Membership/belonging is separate from serving",
        )
        self.assertContains(response, "object rows and schema surfaces have been retired/removed")
        self.assertContains(response, "Path label")

    def test_church_structure_membership_admin_explains_belonging_status(self):
        user = User.objects.create_user(username="membership_admin_member")
        unit = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="RAINBOW4",
            name="Rainbow 4",
        )
        membership = ChurchStructureMembership.objects.create(
            user=user,
            unit=unit,
            status=ChurchStructureMembership.STATUS_ACTIVE,
            is_primary=True,
            start_date=timezone.localdate(),
        )

        response = self.client.get(
            reverse(
                "admin:accounts_churchstructuremembership_change",
                args=[membership.pk],
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Church Structure Memberships")
        self.assertContains(response, "教会结构归属")
        self.assertContains(response, "归属基础")
        self.assertContains(
            response,
            "active primary membership is the canonical belonging source",
        )
        self.assertContains(
            response,
            "runtime source for several ordinary-member visibility/access paths",
        )
        self.assertContains(
            response,
            "Bible Study v2 audience rows and role/worship pickers",
        )
        self.assertContains(
            response,
            "legacy Profile.small_group field was removed in",
        )
        self.assertContains(response, "V1 Bible Study models/tables are removed")
        self.assertContains(response, "Zero-row ServiceEvents fail closed")
        self.assertContains(
            response,
            "Membership does not grant staff capabilities, role assignments, or "
            "TeamAssignment/My Serving",
        )
        self.assertContains(response, "Notes must stay operational and non-sensitive")


class ChurchRolePermissionTests(TestCase):
    def setUp(self):
        # CS-CORE.2D-B / ROLE-SCHEMA.1A: progress permission/access and scoped
        # role validation are structure-unit-native.
        self.district_unit = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_DISTRICT,
            code="PERM-DIST-N",
            name="North Unit",
        )
        self.other_district_unit = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_DISTRICT,
            code="PERM-DIST-S",
            name="South Unit",
        )
        self.group_unit = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="PERM-SG-4",
            name="Rainbow 4 Unit",
            parent=self.district_unit,
        )
        self.other_group_unit = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="PERM-SG-5",
            name="Rainbow 5 Unit",
            parent=self.other_district_unit,
        )
        self.user = User.objects.create_user(
            username="member",
            password="TestPass123!",
        )
        self.staff = User.objects.create_user(
            username="staff_roles",
            password="TestPass123!",
            is_staff=True,
        )

    def create_membership(self, user, unit):
        return ChurchStructureMembership.objects.create(
            user=user,
            unit=unit,
            status=ChurchStructureMembership.STATUS_ACTIVE,
            is_primary=True,
            start_date=timezone.localdate(),
        )

    def test_small_group_structure_unit_sits_under_district_structure_unit(self):
        # LEGACY-PARENT-FK-FIELD-RETIRE.1A removed the legacy SmallGroup.district
        # parent FK; the small-group/district relationship is now the canonical
        # ChurchStructureUnit.parent chain.
        self.assertEqual(self.group_unit.parent, self.district_unit)

    def test_global_scope_rejects_structure_unit(self):
        # ROLE-FIELD-RETIRE.1A: only structure_unit remains scoped; global roles
        # must leave it blank.
        assignment = ChurchRoleAssignment(
            user=self.user,
            role=ChurchRoleAssignment.ROLE_PASTOR,
            scope_type=ChurchRoleAssignment.SCOPE_GLOBAL,
            structure_unit=self.group_unit,
        )

        with self.assertRaises(ValidationError) as context:
            assignment.full_clean()

        self.assertIn("structure_unit", context.exception.message_dict)

    def test_district_scope_requires_structure_unit(self):
        assignment = ChurchRoleAssignment(
            user=self.user,
            role=ChurchRoleAssignment.ROLE_DISTRICT_LEADER,
            scope_type=ChurchRoleAssignment.SCOPE_DISTRICT,
        )

        with self.assertRaises(ValidationError) as context:
            assignment.full_clean()

        self.assertIn("structure_unit", context.exception.message_dict)

    def test_small_group_scope_requires_structure_unit(self):
        assignment = ChurchRoleAssignment(
            user=self.user,
            role=ChurchRoleAssignment.ROLE_GROUP_LEADER,
            scope_type=ChurchRoleAssignment.SCOPE_SMALL_GROUP,
        )

        with self.assertRaises(ValidationError) as context:
            assignment.full_clean()

        self.assertIn("structure_unit", context.exception.message_dict)

    def test_staff_has_all_capabilities(self):
        self.assertTrue(has_capability(self.staff, CAP_PUBLISH_READING_GUIDES))
        self.assertTrue(has_capability(self.staff, CAP_VIEW_ALL_GROUP_PROGRESS))
        self.assertTrue(has_capability(self.staff, CAP_VIEW_DISTRICT_PROGRESS))
        self.assertTrue(has_capability(self.staff, CAP_VIEW_GROUP_PROGRESS))
        self.assertTrue(has_capability(self.staff, CAP_MANAGE_CHURCH_MEMBERSHIPS))

    def test_superuser_has_membership_management_capability(self):
        superuser = User.objects.create_superuser(
            username="super_roles",
            password="TestPass123!",
        )

        self.assertTrue(has_capability(superuser, CAP_MANAGE_CHURCH_MEMBERSHIPS))

    def test_regular_user_without_role_has_no_capabilities(self):
        self.assertFalse(has_capability(self.user, CAP_PUBLISH_READING_GUIDES))
        self.assertFalse(has_capability(self.user, CAP_VIEW_ALL_GROUP_PROGRESS))
        self.assertFalse(has_capability(self.user, CAP_MANAGE_CHURCH_MEMBERSHIPS))

    def test_pastor_assignment_grants_expected_capabilities(self):
        ChurchRoleAssignment.objects.create(
            user=self.user,
            role=ChurchRoleAssignment.ROLE_PASTOR,
            scope_type=ChurchRoleAssignment.SCOPE_GLOBAL,
        )

        self.assertTrue(has_capability(self.user, CAP_PUBLISH_READING_GUIDES))
        self.assertTrue(has_capability(self.user, CAP_VIEW_ALL_GROUP_PROGRESS))
        self.assertTrue(has_capability(self.user, CAP_MANAGE_CHURCH_MEMBERSHIPS))

    def test_membership_alone_does_not_grant_membership_management_capability(self):
        unit = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="RAINBOW4",
            name="Rainbow 4",
        )
        ChurchStructureMembership.objects.create(
            user=self.user,
            unit=unit,
            status=ChurchStructureMembership.STATUS_ACTIVE,
            is_primary=True,
            start_date=timezone.localdate(),
        )

        self.assertFalse(has_capability(self.user, CAP_MANAGE_CHURCH_MEMBERSHIPS))

    def test_district_leader_gets_only_assigned_district_groups(self):
        ChurchRoleAssignment.objects.create(
            user=self.user,
            role=ChurchRoleAssignment.ROLE_DISTRICT_LEADER,
            scope_type=ChurchRoleAssignment.SCOPE_DISTRICT,
            structure_unit=self.district_unit,
        )

        groups = list(get_accessible_progress_groups(self.user))

        self.assertIn(self.group_unit, groups)
        self.assertNotIn(self.other_group_unit, groups)

    def test_group_leader_gets_only_assigned_small_group(self):
        ChurchRoleAssignment.objects.create(
            user=self.user,
            role=ChurchRoleAssignment.ROLE_GROUP_LEADER,
            scope_type=ChurchRoleAssignment.SCOPE_SMALL_GROUP,
            structure_unit=self.group_unit,
        )

        groups = list(get_accessible_progress_groups(self.user))

        self.assertEqual(groups, [self.group_unit])

    def test_regular_user_gets_own_membership_group(self):
        # CS-CORE.2D-B: own-group progress access now comes from the active primary
        # ChurchStructureMembership small-group unit, not Profile.small_group.
        self.create_membership(self.user, self.group_unit)

        groups = list(get_accessible_progress_groups(self.user))

        self.assertEqual(groups, [self.group_unit])

    def test_profile_only_user_no_longer_gets_progress_access(self):
        # CS-CORE.2D-B: Profile.small_group alone no longer grants progress access.

        self.assertEqual(list(get_accessible_progress_groups(self.user)), [])


class StaffMembershipRequestListTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="request_user",
            password="TestPass123!",
        )
        self.requester = User.objects.create_user(
            username="requester",
            password="TestPass123!",
        )
        self.staff = User.objects.create_user(
            username="membership_staff",
            password="TestPass123!",
            is_staff=True,
        )
        self.normal_user = User.objects.create_user(
            username="normal_user",
            password="TestPass123!",
        )
        self.unit = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="RAINBOW4",
            name="Rainbow 4",
            name_en="Rainbow 4",
        )
        self.other_unit = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="RAINBOW5",
            name="Rainbow 5",
            name_en="Rainbow 5",
        )

    def create_membership(self, **overrides):
        defaults = {
            "user": self.user,
            "unit": self.unit,
            "requested_by": self.requester,
            "status": ChurchStructureMembership.STATUS_REQUESTED,
            "notes": "I attend Rainbow 4.",
        }
        defaults.update(overrides)
        return ChurchStructureMembership.objects.create(**defaults)

    def test_pending_list_requires_login(self):
        response = self.client.get(reverse("staff_membership_request_list"))

        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_normal_user_without_permission_cannot_access_pending_list(self):
        self.client.login(username="normal_user", password="TestPass123!")

        response = self.client.get(reverse("staff_membership_request_list"))

        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_staff_can_view_pending_requested_memberships(self):
        membership = self.create_membership()
        session = self.client.session
        session["language"] = "en"
        session.save()
        self.client.login(username="membership_staff", password="TestPass123!")

        response = self.client.get(reverse("staff_membership_request_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Group Requests")
        self.assertContains(response, "request_user")
        self.assertContains(response, "Rainbow 4")
        self.assertContains(response, "requester")
        self.assertContains(response, "I attend Rainbow 4.")
        self.assertContains(response, "Pending review queue")
        self.assertContains(response, "This list only shows requests")
        self.assertContains(response, "Pending review")
        self.assertEqual(response.context["status_summary"]["requested"], 1)
        self.assertContains(
            response,
            reverse("staff_membership_request_detail", args=[membership.id]),
        )
        self.assertNotContains(response, "Approve")
        self.assertNotContains(response, "Reject")

    def test_chinese_pending_list_uses_chinese_labels(self):
        self.create_membership()
        session = self.client.session
        session["language"] = "zh"
        session.save()
        self.client.login(username="membership_staff", password="TestPass123!")

        response = self.client.get(reverse("staff_membership_request_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "小组申请审核")
        self.assertContains(response, "申请加入的小组/团契")
        self.assertContains(response, "等待审核队列")
        self.assertContains(response, "备注必须只包含非敏感")

    def test_pending_list_has_clear_empty_state(self):
        session = self.client.session
        session["language"] = "en"
        session.save()
        self.client.login(username="membership_staff", password="TestPass123!")

        response = self.client.get(reverse("staff_membership_request_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No requests are waiting for review")
        self.assertContains(response, "An empty queue does not change")
        self.assertEqual(response.context["status_summary"]["requested"], 0)

    def test_pending_list_excludes_active_memberships(self):
        self.create_membership()
        active_user = User.objects.create_user(username="active_member")
        ChurchStructureMembership.objects.create(
            user=active_user,
            unit=self.other_unit,
            status=ChurchStructureMembership.STATUS_ACTIVE,
            is_primary=True,
            start_date=timezone.localdate(),
            notes="Already active.",
        )
        self.client.login(username="membership_staff", password="TestPass123!")

        response = self.client.get(reverse("staff_membership_request_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "request_user")
        self.assertNotContains(response, "active_member")
        self.assertNotContains(response, "Already active.")

    def test_user_with_capability_can_view_pending_list(self):
        ChurchRoleAssignment.objects.create(
            user=self.normal_user,
            role=ChurchRoleAssignment.ROLE_PASTOR,
            scope_type=ChurchRoleAssignment.SCOPE_GLOBAL,
        )
        self.create_membership()
        self.client.login(username="normal_user", password="TestPass123!")

        response = self.client.get(reverse("staff_membership_request_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "request_user")

    def test_detail_requires_permission(self):
        membership = self.create_membership()
        self.client.login(username="normal_user", password="TestPass123!")

        response = self.client.get(
            reverse("staff_membership_request_detail", args=[membership.id]),
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_authorized_user_sees_request_detail(self):
        membership = self.create_membership()
        session = self.client.session
        session["language"] = "en"
        session.save()
        self.client.login(username="membership_staff", password="TestPass123!")

        response = self.client.get(
            reverse("staff_membership_request_detail", args=[membership.id]),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Group Request Detail")
        self.assertContains(response, "request_user")
        self.assertContains(response, "Rainbow 4")
        self.assertContains(response, "requester")
        self.assertContains(response, "I attend Rainbow 4.")
        self.assertContains(response, "Request Source")
        # PROFILE-SG-FIELD-RETIRE.1A: the legacy small-group reference rows are gone.
        self.assertNotContains(response, "Legacy small group data (reference only)")
        self.assertNotContains(response, "Legacy small group (reference)")
        self.assertContains(response, "Group membership after approval")
        self.assertContains(response, "Approval state")
        self.assertContains(
            response,
            "Approval creates the primary church-structure membership record",
        )
        self.assertContains(response, "No existing confirmed membership")
        # CS-RETIRE.1A: the legacy sync-target row and sync-on-approval wording
        # are gone (approval no longer writes Profile.small_group).
        self.assertNotContains(response, "Current group update target")
        self.assertNotContains(response, "No single active current small group")
        self.assertNotContains(response, "Confirm and Sync by Rule")
        self.assertContains(response, "Approve Request")
        self.assertContains(response, "Decline Request")

    def test_chinese_authorized_user_sees_request_detail_staff_wording(self):
        membership = self.create_membership()
        session = self.client.session
        session["language"] = "zh"
        session.save()
        self.client.login(username="membership_staff", password="TestPass123!")

        response = self.client.get(
            reverse("staff_membership_request_detail", args=[membership.id]),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "小组申请详情")
        self.assertContains(response, "申请加入的小组/团契")
        # PROFILE-SG-FIELD-RETIRE.1A: the legacy small-group reference rows are gone.
        self.assertNotContains(response, "旧版小组资料（仅供参考）")
        self.assertNotContains(response, "旧版小组（仅供参考）")
        self.assertContains(response, "确认后的归属记录")
        self.assertContains(response, "现有已确认归属")
        self.assertContains(
            response,
            "确认后会建立主要归属记录（教会架构归属）；归属记录才是依据。",
        )
        # CS-RETIRE.1A: the legacy sync-target row is gone.
        self.assertNotContains(response, "确认后会更新到的小组")
        self.assertNotContains(response, "未来教会架构基础")
        self.assertNotContains(response, "当前运行资料")

    def test_detail_has_no_profile_sync_warning_after_retire_1a(self):
        # CS-RETIRE.1A: approval no longer writes Profile.small_group, so the
        # detail page no longer shows a "will update the current active group"
        # sync warning even when the requested unit maps to a different active
        # legacy group than the user's current Profile.small_group.
        membership = self.create_membership()
        session = self.client.session
        session["language"] = "en"
        session.save()
        self.client.login(username="membership_staff", password="TestPass123!")

        response = self.client.get(
            reverse("staff_membership_request_detail", args=[membership.id]),
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(
            response,
            "confirming this request will update the current active group data",
        )

    def test_detail_only_allows_requested_memberships(self):
        active_user = User.objects.create_user(username="active_detail")
        membership = ChurchStructureMembership.objects.create(
            user=active_user,
            unit=self.unit,
            status=ChurchStructureMembership.STATUS_ACTIVE,
            is_primary=True,
            start_date=timezone.localdate(),
        )
        self.client.login(username="membership_staff", password="TestPass123!")

        response = self.client.get(
            reverse("staff_membership_request_detail", args=[membership.id]),
        )

        self.assertEqual(response.status_code, 404)

    def test_approve_is_post_only(self):
        membership = self.create_membership()
        self.client.login(username="membership_staff", password="TestPass123!")

        response = self.client.get(
            reverse("staff_membership_request_approve", args=[membership.id]),
        )

        self.assertEqual(response.status_code, 302)
        membership.refresh_from_db()
        self.user.profile.refresh_from_db()
        self.assertEqual(membership.status, ChurchStructureMembership.STATUS_REQUESTED)

    def test_reject_is_post_only(self):
        membership = self.create_membership()
        self.client.login(username="membership_staff", password="TestPass123!")

        response = self.client.get(
            reverse("staff_membership_request_reject", args=[membership.id]),
        )

        self.assertEqual(response.status_code, 302)
        membership.refresh_from_db()
        self.assertEqual(membership.status, ChurchStructureMembership.STATUS_REQUESTED)

    def test_approve_requires_permission(self):
        membership = self.create_membership()
        self.client.login(username="normal_user", password="TestPass123!")

        response = self.client.post(
            reverse("staff_membership_request_approve", args=[membership.id]),
        )

        self.assertEqual(response.status_code, 302)
        membership.refresh_from_db()
        self.assertEqual(membership.status, ChurchStructureMembership.STATUS_REQUESTED)

    def test_approve_changes_requested_to_active(self):
        membership = self.create_membership()
        requested_by = membership.requested_by
        self.client.login(username="membership_staff", password="TestPass123!")

        response = self.client.post(
            reverse("staff_membership_request_approve", args=[membership.id]),
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("staff_membership_request_list"))
        membership.refresh_from_db()
        self.user.profile.refresh_from_db()
        self.assertEqual(membership.status, ChurchStructureMembership.STATUS_ACTIVE)
        self.assertTrue(membership.is_primary)
        self.assertEqual(
            membership.membership_type,
            ChurchStructureMembership.TYPE_SMALL_GROUP_MEMBER,
        )
        self.assertEqual(membership.start_date, timezone.localdate())
        self.assertEqual(membership.approved_by, self.staff)
        self.assertIsNotNone(membership.approved_at)
        self.assertEqual(membership.requested_by, requested_by)

    def test_approve_mapped_unit_does_not_update_profile_small_group(self):
        # CS-RETIRE.1A: approval no longer mirrors into Profile.small_group, even
        # when the requested unit maps to exactly one active legacy group. The
        # ChurchStructureMembership is the source of truth; the legacy field is
        # left untouched.
        membership = self.create_membership()
        self.client.login(username="membership_staff", password="TestPass123!")

        response = self.client.post(
            reverse("staff_membership_request_approve", args=[membership.id]),
        )

        self.assertEqual(response.status_code, 302)
        membership.refresh_from_db()
        self.user.profile.refresh_from_db()
        self.assertEqual(membership.status, ChurchStructureMembership.STATUS_ACTIVE)
        self.assertTrue(membership.is_primary)

    def test_approve_inactive_mapped_small_group_does_not_update_profile_small_group(self):
        membership = self.create_membership()
        self.client.login(username="membership_staff", password="TestPass123!")

        response = self.client.post(
            reverse("staff_membership_request_approve", args=[membership.id]),
        )

        self.assertEqual(response.status_code, 302)
        membership.refresh_from_db()
        self.user.profile.refresh_from_db()
        self.assertEqual(membership.status, ChurchStructureMembership.STATUS_ACTIVE)

    def test_approve_multi_mapped_unit_does_not_update_profile_small_group(self):
        membership = self.create_membership()
        self.client.login(username="membership_staff", password="TestPass123!")

        response = self.client.post(
            reverse("staff_membership_request_approve", args=[membership.id]),
        )

        self.assertEqual(response.status_code, 302)
        membership.refresh_from_db()
        self.user.profile.refresh_from_db()
        self.assertEqual(membership.status, ChurchStructureMembership.STATUS_ACTIVE)

    def test_approve_blocks_existing_active_primary_membership(self):
        membership = self.create_membership()
        ChurchStructureMembership.objects.create(
            user=self.user,
            unit=self.other_unit,
            status=ChurchStructureMembership.STATUS_ACTIVE,
            is_primary=True,
            start_date=timezone.localdate(),
        )
        self.client.login(username="membership_staff", password="TestPass123!")

        response = self.client.post(
            reverse("staff_membership_request_approve", args=[membership.id]),
        )

        self.assertEqual(response.status_code, 302)
        membership.refresh_from_db()
        self.assertEqual(membership.status, ChurchStructureMembership.STATUS_REQUESTED)
        self.assertFalse(membership.is_primary)
        self.assertIsNone(membership.approved_by)
        self.assertIsNone(membership.approved_at)
        self.user.profile.refresh_from_db()

    def test_reject_changes_requested_to_rejected_and_not_primary(self):
        membership = self.create_membership(is_primary=True)
        requested_by = membership.requested_by
        self.client.login(username="membership_staff", password="TestPass123!")

        response = self.client.post(
            reverse("staff_membership_request_reject", args=[membership.id]),
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("staff_membership_request_list"))
        membership.refresh_from_db()
        self.user.profile.refresh_from_db()
        self.assertEqual(membership.status, ChurchStructureMembership.STATUS_REJECTED)
        self.assertFalse(membership.is_primary)
        self.assertEqual(membership.requested_by, requested_by)
        self.assertIsNone(membership.approved_by)
        self.assertIsNone(membership.approved_at)

    def test_reject_mapped_unit_does_not_update_profile_small_group(self):
        membership = self.create_membership(is_primary=True)
        self.client.login(username="membership_staff", password="TestPass123!")

        response = self.client.post(
            reverse("staff_membership_request_reject", args=[membership.id]),
        )

        self.assertEqual(response.status_code, 302)
        membership.refresh_from_db()
        self.user.profile.refresh_from_db()
        self.assertEqual(membership.status, ChurchStructureMembership.STATUS_REJECTED)

    def test_approve_and_reject_only_allow_requested_status(self):
        membership = self.create_membership()
        membership.status = ChurchStructureMembership.STATUS_REJECTED
        membership.save()
        self.client.login(username="membership_staff", password="TestPass123!")

        approve_response = self.client.post(
            reverse("staff_membership_request_approve", args=[membership.id]),
        )
        reject_response = self.client.post(
            reverse("staff_membership_request_reject", args=[membership.id]),
        )

        self.assertEqual(approve_response.status_code, 404)
        self.assertEqual(reject_response.status_code, 404)

    def test_membership_alone_does_not_allow_pending_list_access(self):
        ChurchStructureMembership.objects.create(
            user=self.normal_user,
            unit=self.unit,
            status=ChurchStructureMembership.STATUS_ACTIVE,
            is_primary=True,
            start_date=timezone.localdate(),
        )
        self.client.login(username="normal_user", password="TestPass123!")

        response = self.client.get(reverse("staff_membership_request_list"))

        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_requested_membership_does_not_change_service_event_visibility(self):
        self.create_membership(user=self.normal_user)
        event = ServiceEvent.objects.create(
            title="District Service",
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
            start_datetime=timezone.now(),
            status=ServiceEvent.STATUS_PUBLISHED,
        )

        self.assertFalse(event.can_be_seen_by(self.normal_user))


        # SE-RETIRE.1B: the requested membership grants nothing, and the
        # retired zero-row fallback means even Profile.small_group no longer
        # makes a zero-row event visible.
        self.assertFalse(event.can_be_seen_by(self.normal_user))

    def test_unmapped_approved_membership_does_not_change_service_event_visibility(self):
        membership = self.create_membership(user=self.normal_user)
        event = ServiceEvent.objects.create(
            title="District Service",
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
            start_datetime=timezone.now(),
            status=ServiceEvent.STATUS_PUBLISHED,
        )
        self.client.login(username="membership_staff", password="TestPass123!")

        self.client.post(
            reverse("staff_membership_request_approve", args=[membership.id]),
        )

        self.assertFalse(event.can_be_seen_by(self.normal_user))


        # SE-RETIRE.1B: the approved (unmapped) membership grants nothing, and
        # the retired zero-row fallback means Profile.small_group no longer
        # makes a zero-row event visible either.
        self.assertFalse(event.can_be_seen_by(self.normal_user))

    def test_mapped_approval_does_not_write_profile_or_change_event_visibility(self):
        # CS-RETIRE.1A: approval no longer mirrors into Profile.small_group, so it
        # no longer flips a legacy zero-row-fallback ServiceEvent's visibility via
        # the profile group. The membership is the source of truth; the legacy
        # field (and the legacy event fallback that reads it) is left untouched.
        membership = self.create_membership(user=self.normal_user)
        event = ServiceEvent.objects.create(
            title="Mapped District Service",
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
            start_datetime=timezone.now(),
            status=ServiceEvent.STATUS_PUBLISHED,
        )

        self.assertFalse(event.can_be_seen_by(self.normal_user))

        self.client.login(username="membership_staff", password="TestPass123!")
        self.client.post(
            reverse("staff_membership_request_approve", args=[membership.id]),
        )
        self.normal_user.profile.refresh_from_db()

        # Profile.small_group is not written, and the legacy event visibility is
        # unchanged by approval.
        self.assertFalse(event.can_be_seen_by(self.normal_user))

    def test_rejected_membership_does_not_change_service_event_visibility(self):
        membership = self.create_membership(user=self.normal_user)
        event = ServiceEvent.objects.create(
            title="District Service",
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
            start_datetime=timezone.now(),
            status=ServiceEvent.STATUS_PUBLISHED,
        )
        self.client.login(username="membership_staff", password="TestPass123!")

        self.client.post(
            reverse("staff_membership_request_reject", args=[membership.id]),
        )

        self.assertFalse(event.can_be_seen_by(self.normal_user))


        # SE-RETIRE.1B: the rejected membership grants nothing, and the retired
        # zero-row fallback means Profile.small_group no longer makes a
        # zero-row event visible either.
        self.assertFalse(event.can_be_seen_by(self.normal_user))

    def test_mapped_approval_does_not_write_removed_profile_small_group(self):
        # PROFILE-SG-FIELD-RETIRE.1A removed Profile.small_group entirely; approval
        # creates/activates membership without restoring a legacy profile mirror.
        membership = self.create_membership(user=self.normal_user)

        self.client.login(username="membership_staff", password="TestPass123!")
        self.client.post(
            reverse("staff_membership_request_approve", args=[membership.id]),
        )
        self.normal_user.profile.refresh_from_db()

        self.assertFalse(hasattr(self.normal_user.profile, "small_group"))


class StaffOverviewTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(
            username="overview_staff",
            password="StaffPass123!",
            is_staff=True,
        )
        self.normal_user = User.objects.create_user(
            username="overview_user",
            password="UserPass123!",
        )
        self.reporter = User.objects.create_user(
            username="overview_reporter",
            password="ReporterPass123!",
        )
        self.unit = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="OVERVIEWGROUP",
            name="Overview Group",
        )

    def set_language(self, language="en"):
        session = self.client.session
        session["language"] = language
        session.save()

    def create_dashboard_data(self):
        now = timezone.now()
        today = timezone.localdate()

        ChurchStructureMembership.objects.create(
            user=self.normal_user,
            unit=self.unit,
            status=ChurchStructureMembership.STATUS_REQUESTED,
        )

        BibleStudySeries.objects.create(
            title="Draft Schedule",
            status=BibleStudySeries.STATUS_DRAFT,
        )
        upcoming_series = BibleStudySeries.objects.create(
            title="Upcoming Schedule",
            start_date=today + timedelta(days=7),
            status=BibleStudySeries.STATUS_PUBLISHED,
        )
        BibleStudyLesson.objects.create(
            series=upcoming_series,
            title="Draft Guide",
            lesson_date=today + timedelta(days=1),
            status=BibleStudyLesson.STATUS_DRAFT,
        )
        upcoming_lesson = BibleStudyLesson.objects.create(
            series=upcoming_series,
            title="Upcoming Guide",
            lesson_date=today + timedelta(days=8),
            status=BibleStudyLesson.STATUS_PUBLISHED,
        )
        # BS-MEETING-MIRROR.1A removed the legacy BibleStudyMeeting.small_group FK;
        # V2 meetings anchor on a structure unit. The overview only counts meetings.
        BibleStudyMeeting.objects.create(
            lesson=upcoming_lesson,
            anchor_unit=self.unit,
            meeting_datetime=now + timedelta(days=2),
            status=BibleStudyMeeting.STATUS_DRAFT,
        )
        BibleStudyMeeting.objects.create(
            lesson=upcoming_lesson,
            anchor_unit=None,
            meeting_datetime=now + timedelta(days=9),
            status=BibleStudyMeeting.STATUS_PUBLISHED,
        )

        hidden_prayer = PrayerRequest.objects.create(
            user=self.normal_user,
            title="Hidden prayer",
            body="Please pray",
            is_hidden=True,
        )
        PrayerReport.objects.create(
            prayer_request=hidden_prayer,
            reporter=self.reporter,
            status=PrayerReport.STATUS_OPEN,
        )

        plan = ReadingPlan.objects.create(name="Overview Plan")
        day = ReadingPlanDay.objects.create(
            plan=plan,
            day_number=1,
            reading_text="John 1",
        )
        hidden_reflection = ReflectionComment.objects.create(
            plan_day=day,
            user=self.normal_user,
            body="Hidden reflection",
            is_hidden=True,
        )
        ReflectionReport.objects.create(
            comment=hidden_reflection,
            reporter=self.reporter,
            status=ReflectionReport.STATUS_OPEN,
        )

        event = ServiceEvent.objects.create(
            title="Upcoming Service",
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
            start_datetime=now + timedelta(days=3),
            status=ServiceEvent.STATUS_PUBLISHED,
        )
        team = MinistryTeam.objects.create(name="Overview Team")
        membership = TeamMembership.objects.create(
            team=team,
            user=self.normal_user,
        )
        TeamMembership.objects.create(
            team=team,
            display_name="Display Only Helper",
        )
        assignment = TeamAssignment.objects.create(
            service_event=event,
            ministry_team=team,
            status=TeamAssignment.STATUS_SCHEDULED,
        )
        TeamAssignmentMember.objects.create(
            assignment=assignment,
            membership=membership,
        )
        empty_team = MinistryTeam.objects.create(
            name="Overview Empty Team",
            playbook_link="https://example.com/empty-team",
        )
        TeamAssignment.objects.create(
            service_event=event,
            ministry_team=empty_team,
            status=TeamAssignment.STATUS_SCHEDULED,
        )
        inactive_team = MinistryTeam.objects.create(
            name="Overview Inactive Team",
            playbook_link="https://example.com/inactive-team",
            is_active=False,
        )
        TeamAssignment.objects.create(
            service_event=event,
            ministry_team=inactive_team,
            status=TeamAssignment.STATUS_SCHEDULED,
        )

    def test_staff_overview_requires_staff_access(self):
        self.client.login(username="overview_user", password="UserPass123!")

        response = self.client.get(reverse("staff_overview"))

        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response.url)

    def test_staff_overview_anonymous_user_redirects_to_login(self):
        response = self.client.get(reverse("staff_overview"))

        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response.url)

    def test_staff_overview_renders_counts_and_existing_workflow_links(self):
        self.create_dashboard_data()
        self.set_language("en")
        self.client.login(username="overview_staff", password="StaffPass123!")

        response = self.client.get(reverse("staff_overview"))
        content = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Staff Overview")
        self.assertContains(response, "Read-only summary")
        self.assertContains(response, "How visibility works today")
        self.assertNotContains(response, "Current Runtime Boundary")
        self.assertContains(response, "ordinary care/belonging")
        self.assertContains(response, "not serving or leadership")
        self.assertContains(response, reverse("staff_membership_request_list"))
        self.assertContains(response, reverse("bible_study_schedule_manage_list"))
        self.assertContains(response, reverse("bible_study_lesson_manage_list"))
        self.assertContains(response, reverse("bible_study_meeting_manage_list"))
        self.assertContains(response, reverse("staff_moderation_queue"))
        self.assertContains(response, reverse("staff_prayer_reports"))
        self.assertContains(response, reverse("staff_reflection_reports"))
        self.assertContains(response, reverse("service_event_list"))
        self.assertContains(response, reverse("ministry_team_list"))
        self.assertContains(response, reverse("team_assignment_list"))
        self.assertContains(response, reverse("staff_user_list"))
        self.assertContains(response, reverse("staff_structure_map"))
        self.assertNotContains(response, "/structure/setup/")
        self.assertContains(response, "Ministry ops health flags")
        self.assertContains(response, "Teams missing playbook links")
        self.assertContains(response, "Display-name-only members")
        self.assertContains(response, "Teams with no active members")
        self.assertContains(response, "Upcoming assignments without active members")
        self.assertContains(response, "Upcoming assignments using inactive teams")
        self.assertContains(response, "Unassigned required teams")
        self.assertEqual(response.context["pending_membership_requests"], 1)
        self.assertEqual(response.context["draft_schedules"], 1)
        self.assertEqual(response.context["upcoming_schedules"], 1)
        self.assertEqual(response.context["draft_guides"], 1)
        self.assertEqual(response.context["upcoming_guides"], 2)
        self.assertEqual(response.context["draft_meetings"], 1)
        self.assertEqual(response.context["upcoming_meetings"], 2)
        self.assertEqual(response.context["open_prayer_reports"], 1)
        self.assertEqual(response.context["hidden_prayers"], 1)
        self.assertEqual(response.context["open_reflection_reports"], 1)
        self.assertEqual(response.context["hidden_reflections"], 1)
        self.assertEqual(response.context["upcoming_service_events"], 1)
        self.assertEqual(response.context["upcoming_assignments"], 3)
        self.assertEqual(response.context["unconfirmed_assignments"], 1)
        self.assertEqual(response.context["inactive_ministry_teams"], 1)
        self.assertEqual(response.context["teams_missing_playbook"], 1)
        self.assertEqual(response.context["display_name_only_members"], 1)
        self.assertEqual(response.context["teams_without_active_members"], 1)
        self.assertEqual(response.context["upcoming_assignments_without_active_members"], 2)
        self.assertEqual(response.context["upcoming_assignments_with_inactive_team"], 1)
        self.assertEqual(response.context["upcoming_required_team_gaps"], 0)
        self.assertEqual(response.context["ministry_ops_warning_indicator_count"], 7)

    def test_staff_overview_shows_upcoming_required_team_gap_count(self):
        now = timezone.now()
        required_team = MinistryTeam.objects.create(
            name="Required Overview Team",
            playbook_link="https://example.com/required",
        )
        event = ServiceEvent.objects.create(
            title="Required Team Service",
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
            start_datetime=now + timedelta(days=3),
            status=ServiceEvent.STATUS_PUBLISHED,
        )
        event.required_teams.add(required_team)
        self.set_language("en")
        self.client.login(username="overview_staff", password="StaffPass123!")

        response = self.client.get(reverse("staff_overview"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Unassigned required teams")
        self.assertEqual(response.context["upcoming_required_team_gaps"], 1)
        self.assertContains(response, "Team Assignments")
        self.assertFalse(TeamAssignment.objects.exists())
        self.assertFalse(TeamAssignmentMember.objects.exists())

    def test_staff_menu_includes_overview_but_normal_nav_stays_uncluttered(self):
        self.set_language("en")
        self.client.login(username="overview_staff", password="StaffPass123!")

        staff_response = self.client.get(reverse("profile"))

        self.assertEqual(staff_response.status_code, 200)
        self.assertContains(staff_response, "Staff Overview")
        self.assertContains(staff_response, reverse("staff_overview"))

        self.client.logout()
        self.client.login(username="overview_user", password="UserPass123!")

        normal_response = self.client.get(reverse("profile"))

        self.assertEqual(normal_response.status_code, 200)
        self.assertNotContains(normal_response, "Staff Overview")
        self.assertNotContains(normal_response, reverse("staff_overview"))

    def test_staff_overview_renders_chinese_labels(self):
        self.set_language("zh")
        self.client.login(username="overview_staff", password="StaffPass123!")

        response = self.client.get(reverse("staff_overview"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "同工总览")
        self.assertContains(response, "只读摘要")
        self.assertContains(response, "目前的运作方式")
        self.assertNotContains(response, "当前运行边界")
        self.assertContains(response, "事工运作提醒指标")
        self.assertContains(response, "目前没有可由现有资料看出的事工设置提醒指标")
        self.assertEqual(response.context["ministry_ops_warning_indicator_count"], 0)

    # MODULAR-CORE.6B: Staff Overview module surface gates. The overview route
    # itself stays Core and always reachable for staff; only module-owned
    # cards/counts/links are gated by CMS_ENABLED_MODULES. Reflection moderation
    # and the Moderation Queue stay Core/support (mirroring MODULAR-CORE.6A,
    # since `comments` is a reading support app, not a registered module).

    @override_settings(
        CMS_ENABLED_MODULES=["reading", "prayers", "events", "ministry"]
    )
    def test_staff_overview_hides_bible_study_card_when_studies_disabled(self):
        self.create_dashboard_data()
        self.set_language("en")
        self.client.login(username="overview_staff", password="StaffPass123!")

        response = self.client.get(reverse("staff_overview"))

        self.assertEqual(response.status_code, 200)
        # Bible Study card/counts/links hidden.
        self.assertNotContains(response, "Draft schedules")
        self.assertNotContains(response, "Upcoming meetings")
        self.assertNotContains(response, reverse("bible_study_schedule_manage_list"))
        self.assertNotContains(response, reverse("bible_study_lesson_manage_list"))
        self.assertNotContains(response, reverse("bible_study_meeting_manage_list"))
        # Studies counts not computed while disabled.
        self.assertEqual(response.context["draft_schedules"], 0)
        self.assertEqual(response.context["upcoming_meetings"], 0)
        # Core/staff and other-module surfaces remain.
        self.assertContains(response, reverse("staff_membership_request_list"))
        self.assertContains(response, reverse("staff_user_list"))
        self.assertContains(response, reverse("staff_structure_map"))
        self.assertContains(response, reverse("staff_moderation_queue"))
        self.assertContains(response, "Upcoming service events")
        self.assertContains(response, reverse("service_event_list"))
        self.assertContains(response, reverse("staff_prayer_reports"))

    @override_settings(CMS_ENABLED_MODULES=["reading", "prayers", "studies"])
    def test_staff_overview_hides_events_and_ministry_when_events_disabled(self):
        self.create_dashboard_data()
        self.set_language("en")
        self.client.login(username="overview_staff", password="StaffPass123!")

        response = self.client.get(reverse("staff_overview"))

        self.assertEqual(response.status_code, 200)
        # Whole Ministry Operations card (events + ministry) hidden.
        self.assertNotContains(response, "Ministry Operations")
        self.assertNotContains(response, "Upcoming service events")
        self.assertNotContains(response, "Upcoming team assignments")
        self.assertNotContains(response, "Ministry ops health flags")
        self.assertNotContains(response, reverse("service_event_list"))
        self.assertNotContains(response, reverse("ministry_team_list"))
        self.assertNotContains(response, reverse("team_assignment_list"))
        # Module counts not computed while disabled.
        self.assertEqual(response.context["upcoming_service_events"], 0)
        self.assertEqual(response.context["upcoming_assignments"], 0)
        self.assertEqual(response.context["ministry_ops_warning_indicator_count"], 0)
        # Core/staff and still-enabled module surfaces remain.
        self.assertContains(response, reverse("staff_membership_request_list"))
        self.assertContains(response, reverse("staff_user_list"))
        self.assertContains(response, reverse("staff_structure_map"))
        self.assertContains(response, reverse("bible_study_schedule_manage_list"))

    @override_settings(
        CMS_ENABLED_MODULES=["reading", "prayers", "studies", "events"]
    )
    def test_staff_overview_hides_ministry_but_keeps_events_when_ministry_disabled(self):
        self.create_dashboard_data()
        self.set_language("en")
        self.client.login(username="overview_staff", password="StaffPass123!")

        response = self.client.get(reverse("staff_overview"))

        self.assertEqual(response.status_code, 200)
        # Ministry surfaces hidden.
        self.assertNotContains(response, "Upcoming team assignments")
        self.assertNotContains(response, "Unconfirmed assignments")
        self.assertNotContains(response, "Ministry ops health flags")
        self.assertNotContains(response, reverse("ministry_team_list"))
        self.assertNotContains(response, reverse("team_assignment_list"))
        self.assertEqual(response.context["upcoming_assignments"], 0)
        self.assertEqual(response.context["ministry_ops_warning_indicator_count"], 0)
        # Church Gatherings (events) surfaces remain in the same card.
        self.assertContains(response, "Ministry Operations")
        self.assertContains(response, "Upcoming service events")
        self.assertContains(response, reverse("service_event_list"))
        self.assertEqual(response.context["upcoming_service_events"], 1)

    @override_settings(
        CMS_ENABLED_MODULES=["reading", "studies", "events", "ministry"]
    )
    def test_staff_overview_hides_prayer_surfaces_when_prayers_disabled(self):
        self.create_dashboard_data()
        self.set_language("en")
        self.client.login(username="overview_staff", password="StaffPass123!")

        response = self.client.get(reverse("staff_overview"))

        self.assertEqual(response.status_code, 200)
        # Prayer report / hidden prayer surfaces hidden.
        self.assertNotContains(response, "Open prayer reports")
        self.assertNotContains(response, "Hidden prayers")
        self.assertNotContains(response, reverse("staff_prayer_reports"))
        self.assertEqual(response.context["open_prayer_reports"], 0)
        self.assertEqual(response.context["hidden_prayers"], 0)
        # Reflection moderation stays Core/support and visible.
        self.assertContains(response, "Open reflection reports")
        self.assertContains(response, "Reflection Reports")
        self.assertContains(response, reverse("staff_reflection_reports"))
        self.assertContains(response, reverse("staff_moderation_queue"))
        # Reflection counts still computed as Core/support.
        self.assertEqual(response.context["open_reflection_reports"], 1)
        self.assertEqual(response.context["hidden_reflections"], 1)

    @override_settings(
        CMS_ENABLED_MODULES=["prayers", "studies", "events", "ministry"]
    )
    def test_staff_overview_reflection_reports_stay_core_when_reading_disabled(self):
        # The Staff Overview has no reading-plan management card (Reading Plan
        # Admin lives only in the staff dropdown, gated in MODULAR-CORE.6A), so
        # disabling `reading` removes no overview card. Reflection Reports stay
        # Core/support and visible, matching the MODULAR-CORE.6A decision.
        self.create_dashboard_data()
        self.set_language("en")
        self.client.login(username="overview_staff", password="StaffPass123!")

        response = self.client.get(reverse("staff_overview"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Reflection Reports")
        self.assertContains(response, reverse("staff_reflection_reports"))
        self.assertContains(response, "Open reflection reports")
        # Reading disablement removes the nav Reading Plan Admin link only.
        self.assertNotContains(response, "Reading Plan Admin")
        # Other module cards remain.
        self.assertContains(response, reverse("bible_study_schedule_manage_list"))
        self.assertContains(response, "Upcoming service events")

    @override_settings(CMS_ENABLED_MODULES=[])
    def test_staff_overview_all_modules_disabled_keeps_core_dashboard(self):
        self.create_dashboard_data()
        self.set_language("en")
        self.client.login(username="overview_staff", password="StaffPass123!")

        response = self.client.get(reverse("staff_overview"))

        self.assertEqual(response.status_code, 200)
        # Core/staff/structure/user-management surfaces remain.
        self.assertContains(response, "Staff Overview")
        self.assertContains(response, "Membership Requests")
        self.assertContains(response, reverse("staff_membership_request_list"))
        self.assertContains(response, "User Admin")
        self.assertContains(response, reverse("staff_user_list"))
        self.assertContains(response, "Church Structure Setup & Review")
        self.assertContains(response, reverse("staff_structure_map"))
        self.assertContains(response, reverse("staff_moderation_queue"))
        self.assertContains(response, "Reflection Reports")
        self.assertContains(response, reverse("staff_reflection_reports"))
        self.assertContains(response, reverse("admin:index"))
        # All module-owned overview surfaces absent.
        self.assertNotContains(response, "Draft schedules")
        self.assertNotContains(response, reverse("bible_study_schedule_manage_list"))
        self.assertNotContains(response, "Ministry Operations")
        self.assertNotContains(response, "Upcoming service events")
        self.assertNotContains(response, reverse("service_event_list"))
        self.assertNotContains(response, reverse("ministry_team_list"))
        self.assertNotContains(response, "Open prayer reports")
        self.assertNotContains(response, reverse("staff_prayer_reports"))
        # Guarded module counts stay at safe defaults.
        self.assertEqual(response.context["draft_schedules"], 0)
        self.assertEqual(response.context["upcoming_service_events"], 0)
        self.assertEqual(response.context["upcoming_assignments"], 0)
        self.assertEqual(response.context["open_prayer_reports"], 0)
        self.assertEqual(response.context["ministry_ops_warning_indicator_count"], 0)

    @override_settings(CMS_ENABLED_MODULES=[])
    def test_staff_overview_module_urls_remain_reachable_when_disabled(self):
        # Surface gating is discoverability only: existing module routes stay
        # reachable under their own permissions even with every module disabled.
        self.client.login(username="overview_staff", password="StaffPass123!")

        for url_name in (
            "bible_study_schedule_manage_list",
            "service_event_list",
            "ministry_team_list",
            "team_assignment_list",
            "staff_prayer_reports",
        ):
            with self.subTest(url_name=url_name):
                response = self.client.get(reverse(url_name))
                self.assertEqual(response.status_code, 200)


class StaffStructureMapTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(
            username="structure_staff",
            password="StaffPass123!",
            is_staff=True,
        )
        self.normal_user = User.objects.create_user(
            username="structure_user",
            password="UserPass123!",
        )
        self.url = reverse("staff_structure_map")

    def set_language(self, language="en"):
        session = self.client.session
        session["language"] = language
        session.save()

    def login_staff(self):
        self.client.login(username="structure_staff", password="StaffPass123!")

    def build_tree(self):
        self.root = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_ROOT,
            code="CHURCH",
            name="全教会",
            name_en="Whole Church",
        )
        self.cm_unit = ChurchStructureUnit.objects.create(
            parent=self.root,
            unit_type=ChurchStructureUnit.UNIT_MINISTRY_CONTEXT,
            code="CM",
            name="中文部",
            name_en="Chinese Ministry",
        )
        self.district_unit = ChurchStructureUnit.objects.create(
            parent=self.cm_unit,
            unit_type=ChurchStructureUnit.UNIT_DISTRICT,
            code="D2",
            name="二区",
            name_en="District 2",
        )
        self.group_unit = ChurchStructureUnit.objects.create(
            parent=self.district_unit,
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="R4",
            name="Rainbow 4",
        )

    def create_active_primary_membership(self, user, unit):
        return ChurchStructureMembership.objects.create(
            user=user,
            unit=unit,
            status=ChurchStructureMembership.STATUS_ACTIVE,
            is_primary=True,
            start_date=timezone.localdate() - timedelta(days=1),
        )

    def test_structure_map_requires_staff_access(self):
        self.client.login(username="structure_user", password="UserPass123!")

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response.url)

    def test_structure_map_anonymous_user_redirects_to_login(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response.url)

    def test_structure_map_rejects_post(self):
        self.login_staff()

        response = self.client.post(self.url)

        self.assertEqual(response.status_code, 405)

    def test_structure_map_renders_tree_in_hierarchy_order(self):
        self.build_tree()
        self.set_language("en")
        self.login_staff()

        response = self.client.get(self.url)
        content = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Church Structure Setup & Review")
        self.assertContains(
            response,
            "View and manage the church structure, member belonging, and structure data reminders.",
        )
        self.assertContains(response, "Belonging, Roles, and Serving")
        self.assertContains(
            response,
            "Member belonging shows where a person is ordinarily cared for and managed",
        )
        self.assertContains(
            response,
            "Role scopes, serving schedules, and team membership are separate concepts.",
        )
        self.assertNotContains(response, "Current Runtime Boundary")
        root_index = content.index("Whole Church")
        cm_index = content.index("Chinese Ministry")
        district_index = content.index("District 2")
        group_index = content.index("Rainbow 4")
        self.assertLess(root_index, cm_index)
        self.assertLess(cm_index, district_index)
        self.assertLess(district_index, group_index)
        self.assertContains(response, "Rainbow 4")
        self.assertContains(
            response,
            reverse("admin:accounts_churchstructureunit_changelist"),
        )
        self.assertContains(response, reverse("staff_membership_request_list"))

    def test_structure_map_siblings_sort_by_sort_order_name_code_and_preserve_tree(self):
        self.root = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_ROOT,
            code="CHURCH",
            name="全教会",
            name_en="Whole Church",
        )
        beta = ChurchStructureUnit.objects.create(
            parent=self.root,
            unit_type=ChurchStructureUnit.UNIT_DISTRICT,
            code="BETA",
            name="Beta Sibling",
            sort_order=1,
        )
        zulu = ChurchStructureUnit.objects.create(
            parent=self.root,
            unit_type=ChurchStructureUnit.UNIT_DISTRICT,
            code="ZULU",
            name="Zulu Parent",
            sort_order=2,
        )
        alpha_child = ChurchStructureUnit.objects.create(
            parent=zulu,
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="ALPHA-CHILD",
            name="Alpha Child",
            sort_order=0,
        )
        alpha_name = ChurchStructureUnit.objects.create(
            parent=self.root,
            unit_type=ChurchStructureUnit.UNIT_DISTRICT,
            code="Z-CODE",
            name="Alpha Same Sort",
            sort_order=3,
        )
        beta_name = ChurchStructureUnit.objects.create(
            parent=self.root,
            unit_type=ChurchStructureUnit.UNIT_DISTRICT,
            code="A-CODE",
            name="Beta Same Sort",
            sort_order=3,
        )
        self.set_language("en")
        self.login_staff()

        response = self.client.get(self.url)

        units = [row["unit"] for row in response.context["structure_rows"]]
        self.assertLess(units.index(beta), units.index(zulu))
        self.assertLess(units.index(zulu), units.index(alpha_child))
        self.assertLess(units.index(alpha_child), units.index(alpha_name))
        self.assertLess(units.index(alpha_name), units.index(beta_name))

    def test_structure_map_renders_collapsible_tree_controls(self):
        self.build_tree()
        self.set_language("en")
        self.login_staff()

        response = self.client.get(self.url)
        content = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "data-structure-tree")
        self.assertContains(response, "Whole Church")
        self.assertContains(response, "data-structure-toggle")
        self.assertContains(response, 'aria-expanded="false"')
        self.assertContains(response, 'data-depth="1"')
        self.assertIn(f'data-parent-id="{self.root.id}"', content)
        self.assertContains(response, "function updateVisibility()")

    def test_structure_map_hides_inactive_units(self):
        self.build_tree()
        ChurchStructureUnit.objects.create(
            parent=self.cm_unit,
            unit_type=ChurchStructureUnit.UNIT_DISTRICT,
            code="OLD-D",
            name="Old District Unit",
            is_active=False,
        )
        self.set_language("en")
        self.login_staff()

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Old District Unit")

    def test_structure_map_renders_chinese_labels(self):
        self.build_tree()
        self.set_language("zh")
        self.login_staff()

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "教会结构设置与检查")
        self.assertContains(response, "查看和管理教会的组织结构、成员所属")
        self.assertContains(response, "归属、职分与服事")
        self.assertContains(response, "成员所属表示一个人平时在哪个小组、区或单位中被关怀和管理")
        self.assertContains(response, "职分范围、服事排班和团队成员关系是另外的概念")
        self.assertNotContains(response, "当前运行边界")
        self.assertContains(response, "教会结构树")
        self.assertContains(response, "成员数")
        self.assertContains(response, "结构资料检查")
        self.assertContains(response, "需要处理")
        self.assertContains(response, "仅供参考")
        self.assertNotContains(response, "覆盖成员")
        self.assertNotContains(response, "设置就绪指标")
        self.assertNotContains(response, "当前资料对应")
        self.assertNotContains(response, "现有记录")
        self.assertContains(response, "全教会")
        self.assertContains(response, "中文部")

    def test_structure_map_renders_english_layout_and_new_indicator_copy(self):
        self.build_tree()
        self.set_language("en")
        self.login_staff()

        response = self.client.get(self.url)
        content = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Church Structure Setup & Review")
        self.assertContains(
            response,
            "View and manage the church structure, member belonging, and structure data reminders.",
        )
        self.assertContains(
            response,
            "Member belonging shows where a person is ordinarily cared for and managed",
        )
        self.assertContains(response, "Members")
        self.assertContains(response, "Structure Data Check")
        self.assertContains(response, "Needs attention")
        self.assertContains(response, "Informational")
        self.assertNotContains(response, "Covered members")
        self.assertNotContains(response, "Setup Readiness Indicators")
        self.assertLess(
            content.index("Church Structure Tree"),
            content.index("Structure Data Check"),
        )
        self.assertContains(response, "Active units with no direct members")
        self.assertContains(response, "Users with more than one primary belonging")
        self.assertContains(response, "Inactive units still in use")

    def test_legacy_row_indicators_are_retired(self):
        self.build_tree()
        self.login_staff()

        response = self.client.get(self.url)
        indicators = response.context["indicators"]

        self.assertNotIn("unmapped_ministry_contexts", indicators)
        self.assertNotIn("unmapped_districts", indicators)
        self.assertNotIn("unmapped_small_groups", indicators)

    def test_units_without_linked_records_indicator_is_retired(self):
        self.build_tree()
        ChurchStructureUnit.objects.create(
            parent=self.root,
            unit_type=ChurchStructureUnit.UNIT_CUSTOM,
            code="NEWMIN",
            name="New Ministry Unit",
        )
        self.login_staff()

        response = self.client.get(self.url)
        indicators = response.context["indicators"]

        self.assertNotIn("units_without_linked_records", indicators)
        self.assertTrue(
            all(
                "without_linked_records" not in row
                for row in response.context["structure_rows"]
            )
        )

    def test_units_under_holding_indicator_is_retired(self):
        self.build_tree()
        holding = ChurchStructureUnit.objects.create(
            parent=self.root,
            unit_type=ChurchStructureUnit.UNIT_CUSTOM,
            code="UNASSIGNED-GROUPS",
            name="Unassigned Groups",
        )
        ChurchStructureUnit.objects.create(
            parent=holding,
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="LOST-GROUP",
            name="Lost Group Unit",
        )
        self.login_staff()

        response = self.client.get(self.url)
        indicators = response.context["indicators"]

        self.assertNotIn("units_under_holding", indicators)

    def _build_tree_with_holding_child(self):
        self.build_tree()
        holding = ChurchStructureUnit.objects.create(
            parent=self.root,
            unit_type=ChurchStructureUnit.UNIT_CUSTOM,
            code="UNASSIGNED-GROUPS",
            name="Unassigned Groups",
        )
        ChurchStructureUnit.objects.create(
            parent=holding,
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="LOST-GROUP",
            name="Lost Group Unit",
        )

    def test_structure_map_omits_retired_awaiting_placement_panel_en(self):
        self._build_tree_with_holding_child()
        self.set_language("en")
        self.login_staff()

        response = self.client.get(self.url)
        content = response.content.decode()

        self.assertIn("Unassigned Groups", content)
        self.assertIn("Lost Group Unit", content)
        self.assertNotIn("Units in awaiting-placement area", content)
        self.assertNotIn("Awaiting placement", content)
        self.assertNotIn("Unassigned holding", content)
        self.assertNotIn("unassigned holding nodes", content)
        self.assertNotIn("holding/unassigned", content)

    def test_structure_map_omits_retired_awaiting_placement_panel_zh(self):
        self._build_tree_with_holding_child()
        self.set_language("zh")
        self.login_staff()

        response = self.client.get(self.url)
        content = response.content.decode()

        self.assertIn("Unassigned Groups", content)
        self.assertIn("Lost Group Unit", content)
        self.assertNotIn("待安排", content)
        self.assertNotIn("待安排区域", content)
        self.assertNotIn("未分配暂存", content)
        self.assertNotIn("未分配暂存节点", content)

    def test_structure_map_shows_counts_without_member_names(self):
        self.build_tree()
        counted_member = User.objects.create_user(
            username="counted_member_name",
            password="MemberPass123!",
        )
        self.create_active_primary_membership(counted_member, self.group_unit)
        self.set_language("en")
        self.login_staff()

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        group_row = next(
            row
            for row in response.context["structure_rows"]
            if row["unit"].id == self.group_unit.id
        )
        self.assertEqual(group_row["membership_count"], 1)
        self.assertNotContains(response, "counted_member_name")

    def test_structure_map_parent_count_includes_descendant_primary_members(self):
        self.build_tree()
        first_member = User.objects.create_user(
            username="covered_child_one",
            password="MemberPass123!",
        )
        second_member = User.objects.create_user(
            username="covered_child_two",
            password="MemberPass123!",
        )
        self.create_active_primary_membership(first_member, self.group_unit)
        self.create_active_primary_membership(second_member, self.group_unit)
        self.set_language("en")
        self.login_staff()

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        rows_by_code = {
            row["unit"].code: row for row in response.context["structure_rows"]
        }
        self.assertEqual(rows_by_code["R4"]["membership_count"], 2)
        self.assertEqual(rows_by_code["D2"]["membership_count"], 2)
        self.assertEqual(rows_by_code["CM"]["membership_count"], 2)
        self.assertContains(response, "Members: 2")

    def test_structure_map_omits_retired_current_data_mapping_label(self):
        self.build_tree()
        self.set_language("en")
        self.login_staff()

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Current data mapping")
        self.assertContains(response, "Rainbow 4")

    def test_structure_map_flags_direct_primary_memberships_on_parent_units(self):
        self.build_tree()
        parent_member = User.objects.create_user(
            username="parent_level_member",
            password="MemberPass123!",
        )
        self.create_active_primary_membership(parent_member, self.cm_unit)
        self.set_language("en")
        self.login_staff()

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["indicators"]["direct_parent_memberships"], 1)
        cm_row = next(
            row
            for row in response.context["structure_rows"]
            if row["unit"].id == self.cm_unit.id
        )
        self.assertEqual(cm_row["membership_count"], 1)
        self.assertEqual(cm_row["direct_parent_membership_count"], 1)
        self.assertContains(response, "Members directly assigned to parent units")
        self.assertNotContains(response, "parent_level_member")

    def test_active_root_unit_count_flags_zero_and_multiple_roots(self):
        self.build_tree()
        self.login_staff()

        response = self.client.get(self.url)
        self.assertEqual(response.context["indicators"]["active_root_units"], 1)

        ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_ROOT,
            code="CHURCH2",
            name="Second Root",
        )
        response = self.client.get(self.url)
        self.assertEqual(response.context["indicators"]["active_root_units"], 2)

        ChurchStructureUnit.objects.filter(
            unit_type=ChurchStructureUnit.UNIT_ROOT,
        ).update(is_active=False)
        response = self.client.get(self.url)
        self.assertEqual(response.context["indicators"]["active_root_units"], 0)

    def test_inactive_legacy_mapping_references_are_retired(self):
        self.build_tree()
        inactive_unit = ChurchStructureUnit.objects.create(
            parent=self.cm_unit,
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="RETIRED",
            name="Retired Unit",
            is_active=False,
        )
        ChurchStructureMembership.objects.bulk_create(
            [
                ChurchStructureMembership(
                    user=self.normal_user,
                    unit=inactive_unit,
                    status=ChurchStructureMembership.STATUS_ACTIVE,
                    is_primary=True,
                    start_date=timezone.localdate(),
                )
            ]
        )
        self.login_staff()

        response = self.client.get(self.url)
        indicators = response.context["indicators"]

        self.assertEqual(indicators["inactive_units_still_referenced"], 0)

    def test_staff_overview_links_to_structure_map(self):
        self.set_language("en")
        self.login_staff()

        response = self.client.get(reverse("staff_overview"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.url)
        self.assertContains(response, "Church Structure Setup & Review")


class ChurchStructureSetupDetailTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(
            username="setup_staff",
            password="StaffPass123!",
            is_staff=True,
        )
        self.structure_admin = User.objects.create_user(
            username="setup_structure_admin",
            password="AdminPass123!",
            is_staff=True,
            is_superuser=True,
        )
        self.pastor = User.objects.create_user(
            username="setup_pastor",
            password="PastorPass123!",
        )
        ChurchRoleAssignment.objects.create(
            user=self.pastor,
            role=ChurchRoleAssignment.ROLE_PASTOR,
            scope_type=ChurchRoleAssignment.SCOPE_GLOBAL,
        )
        self.ordinary = User.objects.create_user(
            username="setup_ordinary",
            password="UserPass123!",
        )
        self.member_only = User.objects.create_user(
            username="setup_member_only",
            password="UserPass123!",
        )
        self.team_only = User.objects.create_user(
            username="setup_team_only",
            password="UserPass123!",
        )
        self.bible_study_role_only = User.objects.create_user(
            username="setup_bible_study_role_only",
            password="UserPass123!",
        )
        self.target_user = User.objects.create_user(
            username="setup_target",
            password="UserPass123!",
            email="target@example.com",
        )
        self.other_user = User.objects.create_user(
            username="setup_other_target",
            password="UserPass123!",
        )
        self.root = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_ROOT,
            code="CHURCH",
            name="全教会",
            name_en="Whole Church",
        )
        self.group = ChurchStructureUnit.objects.create(
            parent=self.root,
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="SETUP-R4",
            name="彩虹四组",
            name_en="Rainbow 4",
        )
        self.child = ChurchStructureUnit.objects.create(
            parent=self.group,
            unit_type=ChurchStructureUnit.UNIT_FELLOWSHIP,
            code="SETUP-FEL",
            name="团契小组",
            name_en="Fellowship Unit",
        )
        self.inactive_unit = ChurchStructureUnit.objects.create(
            parent=self.root,
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="SETUP-OLD",
            name="停用小组",
            name_en="Inactive Unit",
            is_active=False,
        )
        self.setup_url = reverse("staff_structure_map")
        self.old_setup_path = "/structure/setup/"
        self.detail_url = reverse("church_structure_unit_detail", args=[self.group.id])

    def set_language(self, language="en"):
        session = self.client.session
        session["language"] = language
        session.save()

    def login_staff(self):
        self.client.login(username="setup_staff", password="StaffPass123!")

    def login_structure_admin(self):
        self.client.login(
            username="setup_structure_admin",
            password="AdminPass123!",
        )

    def create_membership(self, user, unit=None, **overrides):
        defaults = {
            "user": user,
            "unit": unit or self.group,
            "membership_type": ChurchStructureMembership.TYPE_MEMBER,
            "status": ChurchStructureMembership.STATUS_ACTIVE,
            "start_date": timezone.localdate(),
            "is_primary": False,
        }
        defaults.update(overrides)
        return ChurchStructureMembership.objects.create(**defaults)

    def create_role_profile(self, *, code="small_group_unit", name="Small Group Unit"):
        return ChurchStructureUnitRoleProfile.objects.create(
            code=code,
            name=name,
            name_en=name,
        )

    def create_role_type(self, *, code="lead", name="Lead"):
        return ChurchStructureUnitRoleType.objects.create(
            code=code,
            name=name,
            name_en=name,
        )

    def create_role_requirement(self, profile, role_type, **overrides):
        defaults = {
            "profile": profile,
            "role_type": role_type,
            "is_required": True,
            "is_active": True,
        }
        defaults.update(overrides)
        return ChurchStructureUnitRoleRequirement.objects.create(**defaults)

    def create_team_assignment_for(self, user):
        event = ServiceEvent.objects.create(
            title="Setup Service",
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
            start_datetime=timezone.now() + timedelta(days=1),
            status=ServiceEvent.STATUS_PUBLISHED,
        )
        team = MinistryTeam.objects.create(name="Setup Team")
        team_membership = TeamMembership.objects.create(team=team, user=user)
        assignment = TeamAssignment.objects.create(
            service_event=event,
            ministry_team=team,
            status=TeamAssignment.STATUS_SCHEDULED,
        )
        TeamAssignmentMember.objects.create(
            assignment=assignment,
            membership=team_membership,
        )

    def create_bible_study_role_for(self, user):
        series = BibleStudySeries.objects.create(
            title="Setup Series",
            start_date=timezone.localdate(),
        )
        lesson = BibleStudyLesson.objects.create(
            series=series,
            title="Setup Lesson",
            lesson_date=timezone.localdate(),
        )
        meeting = BibleStudyMeeting.objects.create(
            lesson=lesson,
            anchor_unit=self.group,
            meeting_datetime=timezone.now() + timedelta(days=1),
            status=BibleStudyMeeting.STATUS_PUBLISHED,
        )
        BibleStudyMeetingRole.objects.create(
            meeting=meeting,
            role=BibleStudyMeetingRole.ROLE_DISCUSSION_LEADER,
            user=user,
        )

    def test_anonymous_user_is_redirected_to_login(self):
        response = self.client.get(self.setup_url)

        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_ordinary_user_cannot_access_structure_map(self):
        self.client.login(username="setup_ordinary", password="UserPass123!")

        response = self.client.get(self.setup_url)

        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_membership_only_user_cannot_access_unit_detail(self):
        self.create_membership(self.member_only, is_primary=True)
        self.client.login(username="setup_member_only", password="UserPass123!")

        response = self.client.get(self.detail_url)

        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_team_assignment_only_user_cannot_access_unit_detail(self):
        self.create_team_assignment_for(self.team_only)
        self.client.login(username="setup_team_only", password="UserPass123!")

        response = self.client.get(self.detail_url)

        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_bible_study_role_only_user_cannot_access_unit_detail(self):
        self.create_bible_study_role_for(self.bible_study_role_only)
        self.client.login(
            username="setup_bible_study_role_only",
            password="UserPass123!",
        )

        response = self.client.get(self.detail_url)

        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_staff_can_access_map_and_pastor_can_access_unit_detail(self):
        self.set_language("en")

        self.login_staff()
        map_response = self.client.get(self.setup_url)
        self.assertEqual(map_response.status_code, 200)
        self.assertContains(map_response, "Church Structure Setup & Review")
        self.assertNotContains(map_response, self.old_setup_path)

        self.client.logout()
        self.client.login(username="setup_pastor", password="PastorPass123!")
        detail_response = self.client.get(self.detail_url)
        self.assertEqual(detail_response.status_code, 200)
        self.assertContains(detail_response, "Rainbow 4")

    def test_structure_map_lists_units_counts_and_detail_links(self):
        self.create_membership(self.target_user, is_primary=True)
        self.set_language("en")
        self.login_staff()

        response = self.client.get(self.setup_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Rainbow 4")
        self.assertContains(response, "Members: 1")
        self.assertNotContains(response, self.old_setup_path)

    def test_structure_map_shows_setup_warning_counts(self):
        no_primary_user = User.objects.create_user(username="setup_no_primary")
        multiple_primary_user = User.objects.create_user(username="setup_multi_primary")
        self.create_membership(self.target_user, is_primary=True)
        self.create_membership(no_primary_user, is_primary=False)
        ChurchStructureMembership.objects.bulk_create(
            [
                ChurchStructureMembership(
                    user=multiple_primary_user,
                    unit=self.group,
                    status=ChurchStructureMembership.STATUS_ACTIVE,
                    start_date=timezone.localdate(),
                    is_primary=True,
                ),
                ChurchStructureMembership(
                    user=multiple_primary_user,
                    unit=self.child,
                    status=ChurchStructureMembership.STATUS_ACTIVE,
                    start_date=timezone.localdate(),
                    is_primary=True,
                ),
                ChurchStructureMembership(
                    user=self.other_user,
                    unit=self.inactive_unit,
                    status=ChurchStructureMembership.STATUS_ACTIVE,
                    start_date=timezone.localdate(),
                    is_primary=False,
                ),
            ]
        )
        self.set_language("en")
        self.login_staff()

        response = self.client.get(self.setup_url)
        indicators = response.context["indicators"]

        self.assertEqual(response.status_code, 200)
        self.assertEqual(indicators["users_with_multiple_primary"], 1)
        self.assertEqual(
            indicators["users_with_active_memberships_without_primary"],
            2,
        )
        self.assertEqual(
            indicators["inactive_units_with_active_memberships"],
            1,
        )
        self.assertGreaterEqual(indicators["active_units_without_primary"], 1)
        self.assertContains(response, "Users with more than one primary belonging")
        self.assertContains(response, "Users with memberships but no primary belonging")
        self.assertContains(response, "Inactive units with active members")
        self.assertContains(response, "Active units with no direct members")
        self.assertNotContains(response, "setup_multi_primary")
        self.assertNotContains(response, "setup_no_primary")

    def test_structure_map_shows_coworker_role_readiness_counts_only(self):
        profile = self.create_role_profile()
        lead = self.create_role_type()
        self.create_role_requirement(profile, lead)
        self.group.role_profile = profile
        self.group.save(update_fields=["role_profile"])
        self.set_language("en")
        self.login_staff()

        response = self.client.get(self.setup_url)
        indicators = response.context["indicators"]

        self.assertEqual(response.status_code, 200)
        self.assertEqual(indicators["active_units_without_role_profile"], 2)
        self.assertEqual(
            indicators["active_units_with_missing_required_coworker_roles"],
            1,
        )
        self.assertContains(response, "Active units without a coworker role profile")
        self.assertContains(
            response,
            "Active units with selected profiles and missing required coworkers",
        )
        self.assertContains(response, "childless units are not treated")
        self.assertNotContains(response, "setup_target")

    def test_unit_detail_shows_metadata_children_and_active_memberships(self):
        membership = self.create_membership(self.target_user, is_primary=True)
        self.set_language("en")
        self.login_staff()

        response = self.client.get(self.detail_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Structure Unit Detail")
        self.assertContains(response, "Rainbow 4")
        self.assertContains(response, "SETUP-R4")
        self.assertContains(response, "Small Group")
        self.assertContains(response, "Whole Church &gt; Rainbow 4")
        self.assertContains(response, "Fellowship Unit")
        self.assertContains(response, "setup_target")
        self.assertContains(response, "target@example.com")
        self.assertContains(response, reverse("end_structure_membership", args=[membership.id]))
        self.assertContains(response, reverse("admin:accounts_churchstructureunit_change", args=[self.group.id]))

    def test_unit_detail_shows_role_profile_missing_roles_and_coworkers(self):
        profile = self.create_role_profile()
        lead = self.create_role_type()
        assistant = self.create_role_type(
            code="assistant_lead",
            name="Assistant Lead",
        )
        self.create_role_requirement(profile, lead)
        self.create_role_requirement(profile, assistant)
        self.group.role_profile = profile
        self.group.save(update_fields=["role_profile"])
        active_assignment = ChurchStructureUnitRoleAssignment.objects.create(
            unit=self.group,
            role_type=lead,
            user=self.target_user,
            start_date=timezone.localdate(),
            notes="Current operational note.",
        )
        historical_assignment = ChurchStructureUnitRoleAssignment.objects.create(
            unit=self.group,
            role_type=assistant,
            user=self.other_user,
            is_active=False,
            start_date=timezone.localdate() - timedelta(days=30),
            end_date=timezone.localdate() - timedelta(days=1),
        )
        self.set_language("en")
        self.login_staff()

        response = self.client.get(self.detail_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Coworker Roles")
        self.assertContains(response, "Role Profile")
        self.assertContains(response, "Small Group Unit")
        self.assertContains(response, "Missing Required Roles")
        self.assertContains(response, "Assistant Lead")
        self.assertContains(response, "Active Coworkers")
        self.assertContains(response, "setup_target")
        self.assertContains(response, "Current operational note.")
        self.assertContains(response, "Historical Coworkers")
        self.assertContains(response, "setup_other_target")
        self.assertContains(
            response,
            "do not grant membership, permissions, or weekly serving assignments",
        )
        self.assertIn(
            assistant,
            response.context["missing_required_coworker_roles"],
        )
        self.assertIn(
            active_assignment,
            list(response.context["active_coworker_assignments"]),
        )
        self.assertIn(
            historical_assignment,
            list(response.context["historical_coworker_assignments"]),
        )

    def test_unit_detail_shows_seed_note_when_coworker_defaults_missing(self):
        self.set_language("en")
        self.login_staff()

        response = self.client.get(self.detail_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Coworker role defaults are not seeded yet")
        self.assertContains(
            response,
            "python manage.py seed_structure_unit_coworker_roles --apply",
        )

    def test_default_coworker_candidates_are_direct_unit_and_parent_primary_members(self):
        unit_member = User.objects.create_user(username="candidate_unit")
        parent_member = User.objects.create_user(username="candidate_parent")
        sibling_member = User.objects.create_user(username="candidate_sibling")
        child_member = User.objects.create_user(username="candidate_child")
        non_primary_user = User.objects.create_user(username="candidate_non_primary")
        inactive_user = User.objects.create_user(
            username="candidate_inactive",
            is_active=False,
        )
        requested_user = User.objects.create_user(username="candidate_requested")
        ended_user = User.objects.create_user(username="candidate_ended")
        rejected_user = User.objects.create_user(username="candidate_rejected")
        cancelled_user = User.objects.create_user(username="candidate_cancelled")
        sibling = ChurchStructureUnit.objects.create(
            parent=self.root,
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="SETUP-SIB",
            name="Sibling Group",
        )
        self.create_membership(unit_member, is_primary=True)
        self.create_membership(parent_member, unit=self.root, is_primary=True)
        self.create_membership(sibling_member, unit=sibling, is_primary=True)
        self.create_membership(child_member, unit=self.child, is_primary=True)
        self.create_membership(non_primary_user, is_primary=False)
        self.create_membership(inactive_user, is_primary=True)
        self.create_membership(
            requested_user,
            status=ChurchStructureMembership.STATUS_REQUESTED,
            start_date=None,
            is_primary=False,
        )
        self.create_membership(
            ended_user,
            status=ChurchStructureMembership.STATUS_ENDED,
            start_date=timezone.localdate() - timedelta(days=10),
            end_date=timezone.localdate() - timedelta(days=1),
            is_primary=False,
        )
        self.create_membership(
            rejected_user,
            status=ChurchStructureMembership.STATUS_REJECTED,
            start_date=None,
            is_primary=False,
        )
        self.create_membership(
            cancelled_user,
            status=ChurchStructureMembership.STATUS_CANCELLED,
            start_date=None,
            is_primary=False,
        )

        candidate_ids = set(
            coworker_assignment_local_user_queryset(self.group).values_list(
                "id",
                flat=True,
            )
        )

        self.assertIn(unit_member.id, candidate_ids)
        self.assertIn(parent_member.id, candidate_ids)
        self.assertNotIn(sibling_member.id, candidate_ids)
        self.assertNotIn(child_member.id, candidate_ids)
        self.assertNotIn(non_primary_user.id, candidate_ids)
        self.assertNotIn(inactive_user.id, candidate_ids)
        self.assertNotIn(requested_user.id, candidate_ids)
        self.assertNotIn(ended_user.id, candidate_ids)
        self.assertNotIn(rejected_user.id, candidate_ids)
        self.assertNotIn(cancelled_user.id, candidate_ids)

        form = StructureUnitCoworkerAssignmentForm(unit=self.group, language="en")
        form_candidate_ids = set(form.fields["user"].queryset.values_list("id", flat=True))
        self.assertEqual(form_candidate_ids, candidate_ids)

    def test_coworker_candidates_for_root_use_direct_root_members_only(self):
        root_member = User.objects.create_user(username="candidate_root")
        child_member = User.objects.create_user(username="candidate_root_child")
        self.create_membership(root_member, unit=self.root, is_primary=True)
        self.create_membership(child_member, unit=self.group, is_primary=True)

        candidate_ids = set(
            coworker_assignment_local_user_queryset(self.root).values_list(
                "id",
                flat=True,
            )
        )

        self.assertIn(root_member.id, candidate_ids)
        self.assertNotIn(child_member.id, candidate_ids)

    def test_default_coworker_candidates_do_not_use_leaf_node_status(self):
        self.assertFalse(self.child.children.exists())

        candidate_ids = set(
            coworker_assignment_local_user_queryset(self.child).values_list(
                "id",
                flat=True,
            )
        )

        self.assertNotIn(self.target_user.id, candidate_ids)
        self.assertNotIn(self.other_user.id, candidate_ids)

    def test_unit_detail_displays_local_candidate_note_and_all_user_link(self):
        self.create_membership(self.target_user, is_primary=True)
        self.set_language("en")
        self.login_structure_admin()

        response = self.client.get(self.detail_url)
        form = response.context["coworker_assignment_form"]

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context["coworker_user_scope"],
            StructureUnitCoworkerAssignmentForm.USER_SCOPE_LOCAL,
        )
        self.assertIn(self.target_user, list(form.fields["user"].queryset))
        self.assertContains(
            response,
            "Showing members directly assigned to this unit or its parent.",
        )
        self.assertContains(response, "Show all active users")
        self.assertContains(response, "?coworker_user_scope=all")

    def test_unit_detail_all_user_mode_displays_warning_and_all_active_users(self):
        inactive_user = User.objects.create_user(
            username="all_scope_inactive",
            is_active=False,
        )
        self.set_language("en")
        self.login_structure_admin()

        response = self.client.get(
            self.detail_url,
            {"coworker_user_scope": "all"},
        )
        form = response.context["coworker_assignment_form"]
        user_ids = set(form.fields["user"].queryset.values_list("id", flat=True))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context["coworker_user_scope"],
            StructureUnitCoworkerAssignmentForm.USER_SCOPE_ALL,
        )
        self.assertIn(self.target_user.id, user_ids)
        self.assertIn(self.other_user.id, user_ids)
        self.assertNotIn(inactive_user.id, user_ids)
        self.assertContains(
            response,
            "Showing all active users. Use this only for special cross-unit cases.",
        )
        self.assertContains(response, "Back to local candidates")
        self.assertContains(
            response,
            'action="/staff/structure/units/'
            f'{self.group.id}/coworker-roles/add/?coworker_user_scope=all"',
        )

    def test_unit_detail_empty_local_candidates_shows_help_and_fallback(self):
        self.set_language("en")
        self.login_structure_admin()

        response = self.client.get(self.detail_url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["coworker_assignment_local_user_count"], 0)
        self.assertContains(response, "No local candidates are available")
        self.assertContains(response, "Show all active users")

    def test_role_profile_update_is_post_only_and_requires_structure_permission(self):
        profile = self.create_role_profile()
        url = reverse("update_structure_unit_role_profile", args=[self.group.id])

        self.login_structure_admin()
        get_response = self.client.get(url)
        self.assertEqual(get_response.status_code, 405)

        self.client.logout()
        self.client.login(username="setup_ordinary", password="UserPass123!")
        ordinary_response = self.client.post(url, {"role_profile": profile.id})
        self.assertEqual(ordinary_response.status_code, 302)
        self.group.refresh_from_db()
        self.assertIsNone(self.group.role_profile)

    def test_structure_admin_can_update_and_clear_unit_role_profile(self):
        profile = self.create_role_profile()
        url = reverse("update_structure_unit_role_profile", args=[self.group.id])
        self.login_structure_admin()

        response = self.client.post(url, {"role_profile": profile.id})

        self.assertRedirects(response, self.detail_url)
        self.group.refresh_from_db()
        self.assertEqual(self.group.role_profile, profile)
        self.assertEqual(
            ChurchStructureUnitRoleAssignment.objects.filter(unit=self.group).count(),
            0,
        )

        clear_response = self.client.post(url, {"role_profile": ""})
        self.assertRedirects(clear_response, self.detail_url)
        self.group.refresh_from_db()
        self.assertIsNone(self.group.role_profile)

    def test_role_profile_update_rejects_inactive_profile(self):
        inactive_profile = self.create_role_profile(name="Inactive Profile")
        inactive_profile.is_active = False
        inactive_profile.save(update_fields=["is_active"])
        self.set_language("en")
        self.login_structure_admin()

        response = self.client.post(
            reverse("update_structure_unit_role_profile", args=[self.group.id]),
            {"role_profile": inactive_profile.id},
            follow=True,
        )

        self.group.refresh_from_db()
        self.assertIsNone(self.group.role_profile)
        self.assertContains(response, "Coworker role profile was not updated")

    def test_structure_admin_can_add_coworker_assignment_without_side_effects(self):
        role_type = self.create_role_type()
        baseline_memberships = ChurchStructureMembership.objects.count()
        baseline_role_assignments = ChurchRoleAssignment.objects.count()
        baseline_team_assignments = TeamAssignment.objects.count()
        baseline_team_assignment_members = TeamAssignmentMember.objects.count()
        baseline_bible_study_roles = BibleStudyMeetingRole.objects.count()
        self.login_structure_admin()

        response = self.client.post(
            reverse("add_structure_unit_coworker_assignment", args=[self.group.id])
            + "?coworker_user_scope=all",
            {
                "role_type": role_type.id,
                "user": self.target_user.id,
                "start_date": timezone.localdate().isoformat(),
                "notes": "Operational coworker note.",
            },
        )

        self.assertRedirects(response, self.detail_url)
        assignment = ChurchStructureUnitRoleAssignment.objects.get(
            unit=self.group,
            role_type=role_type,
            user=self.target_user,
        )
        self.assertTrue(assignment.is_active)
        self.assertEqual(assignment.start_date, timezone.localdate())
        self.assertEqual(assignment.notes, "Operational coworker note.")
        self.assertEqual(
            ChurchStructureMembership.objects.count(),
            baseline_memberships,
        )
        self.assertEqual(
            ChurchRoleAssignment.objects.count(),
            baseline_role_assignments,
        )
        self.assertEqual(TeamAssignment.objects.count(), baseline_team_assignments)
        self.assertEqual(
            TeamAssignmentMember.objects.count(),
            baseline_team_assignment_members,
        )
        self.assertEqual(
            BibleStudyMeetingRole.objects.count(),
            baseline_bible_study_roles,
        )
        self.assertFalse(
            has_capability(self.target_user, CAP_MANAGE_BIBLE_STUDIES)
        )

    def test_add_coworker_assignment_is_post_only_and_rejects_ordinary_user(self):
        role_type = self.create_role_type()
        url = reverse("add_structure_unit_coworker_assignment", args=[self.group.id])

        self.login_structure_admin()
        get_response = self.client.get(url)
        self.assertEqual(get_response.status_code, 405)

        self.client.logout()
        self.client.login(username="setup_ordinary", password="UserPass123!")
        ordinary_response = self.client.post(
            url,
            {
                "role_type": role_type.id,
                "user": self.target_user.id,
                "start_date": timezone.localdate().isoformat(),
            },
        )

        self.assertEqual(ordinary_response.status_code, 302)
        self.assertEqual(ChurchStructureUnitRoleAssignment.objects.count(), 0)

    def test_add_coworker_assignment_rejects_inactive_unit_and_duplicates(self):
        role_type = self.create_role_type()
        self.create_membership(self.target_user, is_primary=True)
        self.create_membership(self.other_user, unit=self.root, is_primary=True)
        ChurchStructureUnitRoleAssignment.objects.create(
            unit=self.group,
            role_type=role_type,
            user=self.target_user,
            start_date=timezone.localdate(),
        )
        self.set_language("en")
        self.login_structure_admin()

        duplicate_response = self.client.post(
            reverse("add_structure_unit_coworker_assignment", args=[self.group.id]),
            {
                "role_type": role_type.id,
                "user": self.target_user.id,
                "start_date": timezone.localdate().isoformat(),
            },
            follow=True,
        )
        inactive_response = self.client.post(
            reverse(
                "add_structure_unit_coworker_assignment",
                args=[self.inactive_unit.id],
            ),
            {
                "role_type": role_type.id,
                "user": self.other_user.id,
                "start_date": timezone.localdate().isoformat(),
            },
            follow=True,
        )

        self.assertEqual(
            ChurchStructureUnitRoleAssignment.objects.filter(
                unit=self.group,
                role_type=role_type,
                user=self.target_user,
            ).count(),
            1,
        )
        self.assertFalse(
            ChurchStructureUnitRoleAssignment.objects.filter(
                unit=self.inactive_unit,
            ).exists()
        )
        self.assertContains(duplicate_response, "Coworker role was not added")
        self.assertContains(inactive_response, "Coworker role was not added")

    def test_structure_admin_can_end_coworker_assignment_without_deleting_row(self):
        role_type = self.create_role_type()
        assignment = ChurchStructureUnitRoleAssignment.objects.create(
            unit=self.group,
            role_type=role_type,
            user=self.target_user,
            start_date=timezone.localdate() - timedelta(days=5),
        )
        self.login_structure_admin()

        response = self.client.post(
            reverse("end_structure_unit_coworker_assignment", args=[assignment.id]),
        )

        self.assertRedirects(response, self.detail_url)
        assignment.refresh_from_db()
        self.assertFalse(assignment.is_active)
        self.assertEqual(assignment.end_date, timezone.localdate())
        self.assertTrue(
            ChurchStructureUnitRoleAssignment.objects.filter(
                id=assignment.id,
            ).exists()
        )

    def test_end_coworker_assignment_is_post_only(self):
        role_type = self.create_role_type()
        assignment = ChurchStructureUnitRoleAssignment.objects.create(
            unit=self.group,
            role_type=role_type,
            user=self.target_user,
            start_date=timezone.localdate(),
        )
        self.login_structure_admin()

        response = self.client.get(
            reverse("end_structure_unit_coworker_assignment", args=[assignment.id]),
        )

        self.assertEqual(response.status_code, 405)
        assignment.refresh_from_db()
        self.assertTrue(assignment.is_active)

    def test_role_profile_is_explicit_not_leaf_inferred(self):
        profile = self.create_role_profile()
        lead = self.create_role_type()
        self.create_role_requirement(profile, lead)
        self.set_language("en")
        self.login_structure_admin()

        self.client.post(
            reverse("update_structure_unit_role_profile", args=[self.group.id]),
            {"role_profile": profile.id},
        )
        self.group.refresh_from_db()
        self.assertEqual(self.group.role_profile, profile)

        child_detail = self.client.get(
            reverse("church_structure_unit_detail", args=[self.child.id]),
        )

        self.assertEqual(child_detail.status_code, 200)
        self.assertIsNone(child_detail.context["unit"].role_profile)
        self.assertEqual(child_detail.context["missing_required_coworker_roles"], [])
        self.assertContains(child_detail, "Not set")

    def test_unit_detail_children_order_by_sibling_key(self):
        beta = ChurchStructureUnit.objects.create(
            parent=self.group,
            unit_type=ChurchStructureUnit.UNIT_FELLOWSHIP,
            code="BETA-CODE",
            name="Beta Child",
            sort_order=1,
        )
        alpha = ChurchStructureUnit.objects.create(
            parent=self.group,
            unit_type=ChurchStructureUnit.UNIT_FELLOWSHIP,
            code="ALPHA-CODE",
            name="Alpha Child",
            sort_order=1,
        )
        self.set_language("en")
        self.login_staff()

        response = self.client.get(self.detail_url)

        child_ids = [child.id for child in response.context["children"]]
        self.assertLess(child_ids.index(alpha.id), child_ids.index(beta.id))

    def test_unit_detail_memberships_order_by_visible_user_identity(self):
        zed = User.objects.create_user(
            username="aaa_username",
            password="UserPass123!",
            first_name="Zed",
            last_name="Member",
        )
        amy = User.objects.create_user(
            username="zzz_username",
            password="UserPass123!",
            first_name="Amy",
            last_name="Member",
        )
        ended_ben = User.objects.create_user(
            username="ended_z",
            password="UserPass123!",
            first_name="Ben",
            last_name="Ended",
        )
        ended_ada = User.objects.create_user(
            username="ended_a",
            password="UserPass123!",
            first_name="Ada",
            last_name="Ended",
        )
        self.create_membership(zed, is_primary=True)
        self.create_membership(amy)
        self.create_membership(
            ended_ben,
            status=ChurchStructureMembership.STATUS_ENDED,
            start_date=timezone.localdate() - timedelta(days=10),
            end_date=timezone.localdate() - timedelta(days=1),
        )
        self.create_membership(
            ended_ada,
            status=ChurchStructureMembership.STATUS_ENDED,
            start_date=timezone.localdate() - timedelta(days=10),
            end_date=timezone.localdate() - timedelta(days=1),
        )
        self.set_language("en")
        self.login_staff()

        response = self.client.get(self.detail_url)

        active_names = [
            membership.user.get_full_name()
            for membership in response.context["active_memberships"]
        ]
        inactive_names = [
            membership.user.get_full_name()
            for membership in response.context["inactive_memberships"]
        ]
        self.assertEqual(active_names[:2], ["Amy Member", "Zed Member"])
        self.assertEqual(inactive_names[:2], ["Ada Ended", "Ben Ended"])

    def test_unit_detail_shows_read_only_move_impact_preview_counts(self):
        direct_member = self.create_membership(self.target_user, is_primary=True)
        descendant_member = self.create_membership(
            self.other_user,
            unit=self.child,
        )
        ChurchRoleAssignment.objects.create(
            user=self.target_user,
            role=ChurchRoleAssignment.ROLE_GROUP_LEADER,
            scope_type=ChurchRoleAssignment.SCOPE_SMALL_GROUP,
            structure_unit=self.group,
        )
        service_event = ServiceEvent.objects.create(
            title="Preview Service",
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
            start_datetime=timezone.now() + timedelta(days=1),
            status=ServiceEvent.STATUS_PUBLISHED,
            host_language_unit=self.group,
        )
        ServiceEventAudienceScope.objects.create(
            service_event=service_event,
            unit=self.child,
        )
        series = BibleStudySeries.objects.create(
            title="Preview Schedule",
            start_date=timezone.localdate(),
            status=BibleStudySeries.STATUS_PUBLISHED,
        )
        BibleStudySeriesAudienceScope.objects.create(series=series, unit=self.child)
        lesson = BibleStudyLesson.objects.create(
            series=series,
            title="Preview Lesson",
            lesson_date=timezone.localdate(),
            status=BibleStudyLesson.STATUS_PUBLISHED,
        )
        meeting = BibleStudyMeeting.objects.create(
            lesson=lesson,
            anchor_unit=self.child,
            meeting_datetime=timezone.now() + timedelta(days=2),
            status=BibleStudyMeeting.STATUS_PUBLISHED,
        )
        BibleStudyMeetingAudienceScope.objects.create(meeting=meeting, unit=self.group)
        PrayerRequest.objects.create(
            user=self.target_user,
            title="Preview prayer",
            body="Please pray.",
            structure_unit_at_post=self.child,
        )
        plan = ReadingPlan.objects.create(name="Preview Plan")
        day = ReadingPlanDay.objects.create(
            plan=plan,
            day_number=1,
            reading_text="John 1",
        )
        ReflectionComment.objects.create(
            plan_day=day,
            user=self.other_user,
            body="Preview reflection",
            structure_unit_at_post=self.group,
        )
        self.set_language("en")
        self.login_staff()

        response = self.client.get(self.detail_url)
        preview = response.context["move_impact_preview"]["counts"]

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Move / Reparent Impact Preview")
        self.assertContains(response, "Moving a unit is not implemented yet")
        self.assertContains(response, "Membership does not grant serving or leadership")
        self.assertContains(response, "Active descendant units")
        self.assertEqual(preview["active_descendant_units"], 1)
        self.assertEqual(preview["inactive_descendant_units"], 0)
        self.assertEqual(preview["active_memberships_direct"], 1)
        self.assertEqual(preview["active_memberships_descendants"], 1)
        self.assertEqual(preview["active_role_scopes"], 1)
        self.assertEqual(preview["service_event_audience_scopes"], 1)
        self.assertEqual(preview["service_event_host_language_refs"], 1)
        self.assertEqual(preview["bible_study_schedule_audience_scopes"], 1)
        self.assertEqual(preview["bible_study_meeting_audience_scopes"], 1)
        self.assertEqual(preview["bible_study_meeting_anchors"], 1)
        self.assertEqual(preview["prayer_snapshots"], 1)
        self.assertEqual(preview["reflection_snapshots"], 1)
        self.assertEqual(direct_member.unit, self.group)
        self.assertEqual(descendant_member.unit, self.child)

    def test_unit_detail_exposes_no_move_form_or_route(self):
        self.set_language("en")
        self.login_staff()

        response = self.client.get(self.detail_url)

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "/move/")
        self.assertNotContains(response, 'name="new_parent"')
        self.assertNotContains(response, "Move this unit")
        self.assertNotContains(response, "Reparent this unit")

    def test_inactive_unit_detail_shows_banner_and_hides_add_membership_form(self):
        self.set_language("en")
        self.client.login(username="setup_pastor", password="PastorPass123!")
        inactive_detail_url = reverse(
            "church_structure_unit_detail",
            args=[self.inactive_unit.id],
        )

        response = self.client.get(inactive_detail_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "This unit is inactive")
        self.assertContains(response, "Active memberships cannot be added to inactive units.")
        self.assertContains(response, "Active memberships cannot be added to inactive units")
        self.assertNotContains(
            response,
            reverse("add_structure_membership", args=[self.inactive_unit.id]),
        )

    def test_ordinary_user_cannot_access_unit_detail(self):
        self.client.login(username="setup_ordinary", password="UserPass123!")

        response = self.client.get(self.detail_url)

        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_staff_can_add_active_membership_to_unit(self):
        self.login_staff()

        response = self.client.post(
            reverse("add_structure_membership", args=[self.group.id]),
            {
                "user": self.target_user.id,
                "membership_type": ChurchStructureMembership.TYPE_MEMBER,
                "start_date": timezone.localdate().isoformat(),
                "is_primary": "",
                "notes": "Operational note.",
            },
        )

        self.assertRedirects(response, self.detail_url)
        membership = ChurchStructureMembership.objects.get(user=self.target_user)
        self.assertEqual(membership.unit, self.group)
        self.assertEqual(membership.status, ChurchStructureMembership.STATUS_ACTIVE)
        self.assertFalse(membership.is_primary)
        self.assertEqual(membership.start_date, timezone.localdate())
        self.assertEqual(membership.approved_by, self.staff)

    def test_adding_primary_membership_unsets_other_active_primary(self):
        existing = self.create_membership(
            self.target_user,
            unit=self.child,
            is_primary=True,
        )
        self.login_staff()

        self.client.post(
            reverse("add_structure_membership", args=[self.group.id]),
            {
                "user": self.target_user.id,
                "membership_type": ChurchStructureMembership.TYPE_MEMBER,
                "start_date": timezone.localdate().isoformat(),
                "is_primary": "on",
            },
        )

        existing.refresh_from_db()
        new_membership = ChurchStructureMembership.objects.get(
            user=self.target_user,
            unit=self.group,
        )
        self.assertFalse(existing.is_primary)
        self.assertTrue(new_membership.is_primary)

    def test_adding_non_primary_membership_preserves_existing_primary(self):
        existing = self.create_membership(
            self.target_user,
            unit=self.child,
            is_primary=True,
        )
        self.login_staff()

        self.client.post(
            reverse("add_structure_membership", args=[self.group.id]),
            {
                "user": self.target_user.id,
                "membership_type": ChurchStructureMembership.TYPE_MEMBER,
                "start_date": timezone.localdate().isoformat(),
            },
        )

        existing.refresh_from_db()
        new_membership = ChurchStructureMembership.objects.get(
            user=self.target_user,
            unit=self.group,
        )
        self.assertTrue(existing.is_primary)
        self.assertFalse(new_membership.is_primary)

    def test_duplicate_active_membership_is_blocked(self):
        self.create_membership(self.target_user, is_primary=False)
        self.login_staff()

        response = self.client.post(
            reverse("add_structure_membership", args=[self.group.id]),
            {
                "user": self.target_user.id,
                "membership_type": ChurchStructureMembership.TYPE_MEMBER,
                "start_date": timezone.localdate().isoformat(),
            },
            follow=True,
        )

        self.assertEqual(
            ChurchStructureMembership.objects.filter(
                user=self.target_user,
                unit=self.group,
            ).count(),
            1,
        )
        self.assertContains(response, "Membership was not added")

    def test_end_membership_does_not_delete_and_removes_from_active_list(self):
        membership = self.create_membership(self.target_user, is_primary=True)
        self.login_staff()

        response = self.client.post(
            reverse("end_structure_membership", args=[membership.id]),
        )

        self.assertRedirects(response, self.detail_url)
        membership.refresh_from_db()
        self.assertEqual(membership.status, ChurchStructureMembership.STATUS_ENDED)
        self.assertFalse(membership.is_primary)
        self.assertEqual(membership.end_date, timezone.localdate())
        self.assertTrue(
            ChurchStructureMembership.objects.filter(id=membership.id).exists()
        )
        detail = self.client.get(self.detail_url)
        self.assertNotIn(membership, list(detail.context["active_memberships"]))

    def test_set_primary_action_unsets_other_active_primaries(self):
        existing = self.create_membership(
            self.target_user,
            unit=self.child,
            is_primary=True,
        )
        target = self.create_membership(self.target_user, is_primary=False)
        self.login_staff()

        response = self.client.post(
            reverse("set_primary_structure_membership", args=[target.id]),
        )

        self.assertRedirects(response, self.detail_url)
        existing.refresh_from_db()
        target.refresh_from_db()
        self.assertFalse(existing.is_primary)
        self.assertTrue(target.is_primary)

    def test_set_primary_rejects_inactive_membership(self):
        membership = self.create_membership(
            self.target_user,
            status=ChurchStructureMembership.STATUS_ENDED,
            end_date=timezone.localdate(),
            is_primary=False,
        )
        self.login_staff()

        self.client.post(reverse("set_primary_structure_membership", args=[membership.id]))

        membership.refresh_from_db()
        self.assertFalse(membership.is_primary)

    def test_post_actions_reject_ordinary_users(self):
        membership = self.create_membership(self.target_user, is_primary=False)
        self.client.login(username="setup_ordinary", password="UserPass123!")

        add_response = self.client.post(
            reverse("add_structure_membership", args=[self.child.id]),
            {
                "user": self.other_user.id,
                "membership_type": ChurchStructureMembership.TYPE_MEMBER,
                "start_date": timezone.localdate().isoformat(),
            },
        )
        primary_response = self.client.post(
            reverse("set_primary_structure_membership", args=[membership.id]),
        )
        end_response = self.client.post(
            reverse("end_structure_membership", args=[membership.id]),
        )

        self.assertEqual(add_response.status_code, 302)
        self.assertEqual(primary_response.status_code, 302)
        self.assertEqual(end_response.status_code, 302)
        self.assertEqual(ChurchStructureMembership.objects.count(), 1)
        membership.refresh_from_db()
        self.assertEqual(membership.status, ChurchStructureMembership.STATUS_ACTIVE)
        self.assertFalse(membership.is_primary)

    def test_membership_actions_do_not_create_serving_or_bible_study_roles(self):
        self.login_staff()

        self.client.post(
            reverse("add_structure_membership", args=[self.group.id]),
            {
                "user": self.target_user.id,
                "membership_type": ChurchStructureMembership.TYPE_MEMBER,
                "start_date": timezone.localdate().isoformat(),
                "is_primary": "on",
            },
        )

        self.assertEqual(TeamAssignment.objects.count(), 0)
        self.assertEqual(TeamAssignmentMember.objects.count(), 0)
        self.assertEqual(BibleStudyMeetingRole.objects.count(), 0)

    def test_staff_overview_and_staff_menu_link_to_setup_only_for_staff_nav(self):
        self.set_language("en")
        self.login_staff()

        overview_response = self.client.get(reverse("staff_overview"))
        profile_response = self.client.get(reverse("profile"))

        self.assertContains(overview_response, self.setup_url)
        self.assertContains(overview_response, "Church Structure Setup & Review")
        self.assertNotContains(overview_response, self.old_setup_path)
        self.assertContains(profile_response, self.setup_url)
        self.assertNotContains(profile_response, self.old_setup_path)
        self.assertContains(profile_response, "Church Structure Setup & Review")

        self.client.logout()
        self.client.login(username="setup_ordinary", password="UserPass123!")
        normal_profile = self.client.get(reverse("profile"))

        self.assertNotContains(normal_profile, self.setup_url)
        self.assertNotContains(normal_profile, self.old_setup_path)
        self.assertNotContains(normal_profile, "Church Structure Setup & Review")


class StaffStructureMapEditModeTests(TestCase):
    """CS-SETUP.1B: edit mode + rename/detail only on /staff/structure/."""

    def setUp(self):
        # Superuser has the change_churchstructureunit permission implicitly.
        self.admin = User.objects.create_user(
            username="structure_admin",
            password="AdminPass123!",
            is_staff=True,
            is_superuser=True,
        )
        # Staff who can view the page but cannot change structure units.
        self.viewer = User.objects.create_user(
            username="structure_viewer",
            password="ViewerPass123!",
            is_staff=True,
        )
        self.normal_user = User.objects.create_user(
            username="structure_plain",
            password="PlainPass123!",
        )
        self.url = reverse("staff_structure_map")

        self.root = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_ROOT,
            code="CHURCH",
            name="全教会",
            name_en="Whole Church",
        )
        self.child = ChurchStructureUnit.objects.create(
            parent=self.root,
            unit_type=ChurchStructureUnit.UNIT_DISTRICT,
            code="D2",
            name="二区",
            name_en="District 2",
            sort_order=3,
        )
        self.inactive_child = ChurchStructureUnit.objects.create(
            parent=self.root,
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="OLD1",
            name="停用一组",
            name_en="Inactive Group 1",
            is_active=False,
            sort_order=9,
        )
        self.rename_root_url = reverse(
            "staff_structure_unit_rename", args=[self.root.id]
        )
        self.rename_child_url = reverse(
            "staff_structure_unit_rename", args=[self.child.id]
        )
        self.add_child_url = reverse(
            "staff_structure_unit_add_child", args=[self.child.id]
        )
        self.sort_order_root_url = reverse(
            "staff_structure_unit_update_sort_order", args=[self.root.id]
        )
        self.sort_order_child_url = reverse(
            "staff_structure_unit_update_sort_order", args=[self.child.id]
        )
        self.order_siblings_url = reverse(
            "staff_structure_units_order_siblings"
        )
        self.disable_root_url = reverse(
            "staff_structure_unit_disable", args=[self.root.id]
        )
        self.disable_child_url = reverse(
            "staff_structure_unit_disable", args=[self.child.id]
        )
        self.enable_child_url = reverse(
            "staff_structure_unit_enable", args=[self.inactive_child.id]
        )

    def set_language(self, language="en"):
        session = self.client.session
        session["language"] = language
        session.save()

    def login_admin(self):
        self.client.login(username="structure_admin", password="AdminPass123!")

    def login_viewer(self):
        self.client.login(
            username="structure_viewer", password="ViewerPass123!"
        )

    def child_payload(self, **overrides):
        payload = {
            "name": "青年小组",
            "name_en": "Youth Group",
            "code": "youth",
            "unit_type": ChurchStructureUnit.UNIT_SMALL_GROUP,
            "sort_order": "7",
        }
        payload.update(overrides)
        return payload

    def post_sibling_order(self, parent_id, unit_ids, **kwargs):
        payload = {
            "parent_id": "root" if parent_id is None else str(parent_id),
            "unit_ids": [str(unit_id) for unit_id in unit_ids],
        }
        return self.client.post(self.order_siblings_url, payload, **kwargs)

    # --- view / edit mode ---------------------------------------------------

    def test_default_view_has_no_action_menus(self):
        self.set_language("en")
        self.login_admin()

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["edit_mode"])
        self.assertEqual(response.context["inactive_unit_count"], 1)
        self.assertContains(response, "Inactive units")
        self.assertNotContains(response, "structure-row-icon-actions")
        self.assertNotContains(response, "Review inactive units")
        self.assertNotContains(response, "Edit mode:")
        # The entry point into edit mode is offered to admin users.
        self.assertContains(response, "Edit structure")

    def test_edit_mode_shows_banner_and_inline_icon_actions(self):
        self.set_language("en")
        self.login_admin()

        response = self.client.get(self.url, {"edit": "1"})
        content = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["edit_mode"])
        self.assertContains(response, "Edit mode lets authorized users")
        self.assertContains(response, "structure-row-icon-actions")
        self.assertContains(response, 'aria-label="Rename unit"')
        self.assertContains(response, 'aria-label="Order"')
        self.assertContains(response, 'aria-label="Add child unit"')
        self.assertContains(response, 'aria-label="Disable unit"')
        self.assertContains(response, 'aria-label="View details"')
        self.assertNotIn("structure-row-actions-summary", content)
        self.assertNotIn(">Actions<", content)
        self.assertContains(response, "Exit edit mode")
        self.assertContains(response, "rename display labels")
        self.assertContains(response, "adjust same-level order")
        self.assertContains(response, "add child units")
        self.assertContains(response, "safely disable eligible units")
        self.assertContains(response, "detail/admin links")
        self.assertContains(response, "does not hard-delete units")
        self.assertContains(response, "move/reparent units")
        self.assertContains(response, "cascade-disable children")
        self.assertContains(response, "automatically end memberships")
        self.assertContains(response, "rewrite audience or role scopes")
        self.assertContains(
            response,
            "change serving assignments or visibility rules",
        )
        self.assertContains(
            response,
            "Use the up/down arrows to reorder units under the same parent; this does not move units or change memberships, permissions, or serving assignments.",
        )
        self.assertNotContains(response, "only change display names")

    def test_edit_mode_shows_inactive_unit_review_section(self):
        self.set_language("en")
        self.login_admin()

        response = self.client.get(self.url, {"edit": "1"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Review inactive units")
        self.assertContains(response, "Inactive Group 1")
        self.assertContains(response, "OLD1")
        self.assertContains(response, "Small Group")
        self.assertContains(response, "Whole Church")
        self.assertContains(response, "Active memberships")
        self.assertContains(response, "Reference warnings")
        self.assertContains(response, "Re-enable this unit")

    def test_edit_mode_inactive_unit_rows_order_by_path_then_sibling_key(self):
        alpha_parent = ChurchStructureUnit.objects.create(
            parent=self.root,
            unit_type=ChurchStructureUnit.UNIT_DISTRICT,
            code="ALPHA-PARENT",
            name="Alpha Parent",
            sort_order=2,
        )
        alpha_child = ChurchStructureUnit.objects.create(
            parent=alpha_parent,
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="ALPHA-INACTIVE",
            name="Alpha Inactive",
            is_active=False,
            sort_order=5,
        )
        root_inactive = ChurchStructureUnit.objects.create(
            parent=self.root,
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="ROOT-INACTIVE",
            name="Root Inactive",
            is_active=False,
            sort_order=1,
        )
        self.set_language("en")
        self.login_admin()

        response = self.client.get(self.url, {"edit": "1"})

        row_ids = [row["unit"].id for row in response.context["inactive_unit_rows"]]
        self.assertLess(row_ids.index(alpha_child.id), row_ids.index(self.inactive_child.id))
        self.assertLess(row_ids.index(self.inactive_child.id), row_ids.index(root_inactive.id))

    def test_inactive_units_are_labeled_and_excluded_from_active_tree(self):
        self.set_language("en")
        self.login_admin()

        response = self.client.get(self.url, {"edit": "1"})
        active_tree_unit_ids = {
            row["unit"].id for row in response.context["structure_rows"]
        }

        self.assertNotIn(self.inactive_child.id, active_tree_unit_ids)
        self.assertContains(response, "Inactive Group 1")
        self.assertContains(response, "Inactive")

    def test_edit_mode_chinese_copy_describes_current_actions(self):
        self.set_language("zh")
        self.login_admin()

        response = self.client.get(self.url, {"edit": "1"})

        self.assertContains(response, "可以重命名显示名称")
        self.assertContains(response, "调整同层排序")
        self.assertContains(response, "新增下级单元")
        self.assertContains(response, "安全停用可停用的单元")
        self.assertContains(response, "进入详细资料或后台管理")
        self.assertContains(response, "不会硬删除")
        self.assertContains(response, "移动或改上级")
        self.assertContains(response, "递归停用下级")
        self.assertContains(response, "自动结束归属")
        self.assertContains(response, "改写适用范围或职分范围")
        self.assertContains(response, "不会改变服事安排或可见性规则")
        self.assertContains(response, "可用上下箭头调整同一上级下的显示顺序")
        self.assertNotContains(response, "这里只能修改显示名称")

    def test_edit_mode_root_has_no_rename_but_child_does(self):
        self.set_language("en")
        self.login_admin()

        response = self.client.get(self.url, {"edit": "1"})
        content = response.content.decode()

        # Root cannot be renamed; its rename endpoint must not be in the page.
        self.assertNotIn(f'action="{self.rename_root_url}"', content)
        # Non-root unit exposes a rename form in edit mode.
        self.assertIn(f'action="{self.rename_child_url}"', content)

    def test_view_only_staff_sees_no_edit_controls(self):
        self.set_language("en")
        self.login_viewer()

        plain = self.client.get(self.url)
        self.assertEqual(plain.status_code, 200)
        self.assertFalse(plain.context["can_admin_units"])
        self.assertNotContains(plain, "Edit structure")

        # Even forcing ?edit=1 must not enable edit mode for view-only staff.
        forced = self.client.get(self.url, {"edit": "1"})
        self.assertFalse(forced.context["edit_mode"])
        self.assertNotContains(forced, "Edit mode:")
        self.assertNotContains(forced, "structure-row-icon-actions")

    def test_edit_mode_renders_sort_order_controls_for_active_units(self):
        self.set_language("en")
        self.login_admin()

        response = self.client.get(self.url, {"edit": "1"})
        content = response.content.decode()

        self.assertContains(response, self.sort_order_root_url)
        self.assertContains(response, self.sort_order_child_url)
        self.assertContains(response, 'name="sort_order"')
        self.assertContains(response, "Save order")
        self.assertContains(
            response,
            "Only same-level display order changes; this does not move/reparent the unit or change memberships or permissions.",
        )
        self.assertIn(f'action="{self.sort_order_root_url}"', content)
        self.assertIn(f'action="{self.sort_order_child_url}"', content)

    def test_edit_mode_renders_sibling_reorder_controls_for_active_siblings_en(self):
        ChurchStructureUnit.objects.create(
            parent=self.root,
            unit_type=ChurchStructureUnit.UNIT_DISTRICT,
            code="D1",
            name="一区",
            name_en="District 1",
            sort_order=1,
        )
        self.set_language("en")
        self.login_admin()

        response = self.client.get(self.url, {"edit": "1"})
        content = response.content.decode()

        self.assertContains(response, self.order_siblings_url)
        self.assertContains(response, "This level order has changed")
        self.assertContains(response, "Save this level order")
        self.assertContains(response, 'data-sibling-order-control')
        self.assertContains(response, 'data-direction="up"')
        self.assertContains(response, 'data-direction="down"')
        self.assertContains(response, 'data-sibling-save-bar')
        self.assertContains(response, 'hidden')
        self.assertContains(response, 'data-parent-id="1"')
        self.assertContains(response, 'data-depth="1"')
        self.assertContains(response, 'data-ancestors="1"')
        self.assertContains(response, "function getSubtreeBlock(row)")
        self.assertContains(response, "moveSiblingRow(row, direction)")
        self.assertNotContains(response, "structure-sibling-order-list")
        self.assertNotContains(response, "<strong>Same-level order</strong>", html=True)
        self.assertLess(
            content.index('data-sibling-order-controls'),
            content.index("District 1"),
        )

    def test_edit_mode_renders_sibling_reorder_controls_for_active_siblings_zh(self):
        ChurchStructureUnit.objects.create(
            parent=self.root,
            unit_type=ChurchStructureUnit.UNIT_DISTRICT,
            code="D1",
            name="一区",
            name_en="District 1",
            sort_order=1,
        )
        self.set_language("zh")
        self.login_admin()

        response = self.client.get(self.url, {"edit": "1"})

        self.assertContains(response, "保存此层排序")
        self.assertContains(response, "此层顺序已调整")
        self.assertContains(response, "可用上下箭头调整同一上级下的显示顺序")
        self.assertNotContains(response, "<strong>同层排序</strong>", html=True)

    def test_non_edit_mode_does_not_render_sort_order_control(self):
        self.set_language("en")
        self.login_admin()

        response = self.client.get(self.url)

        self.assertNotContains(response, self.sort_order_child_url)
        self.assertNotContains(response, "Save order")
        self.assertNotContains(response, 'aria-label="Order"')
        self.assertNotContains(response, self.order_siblings_url)
        self.assertNotContains(response, "Save this level order")
        self.assertNotContains(response, "structure-row-order-controls")
        self.assertNotContains(response, 'aria-label="Same-level ordering tools"')

    def test_edit_mode_action_menu_links_to_detail_and_admin(self):
        self.set_language("en")
        detail_url = reverse("church_structure_unit_detail", args=[self.child.id])
        admin_change_url = reverse(
            "admin:accounts_churchstructureunit_change", args=[self.child.id]
        )

        self.login_admin()
        admin_resp = self.client.get(self.url, {"edit": "1"})
        self.assertContains(admin_resp, detail_url)
        self.assertContains(admin_resp, admin_change_url)

        self.client.logout()
        self.login_viewer()
        viewer_resp = self.client.get(self.url, {"edit": "1"})
        self.assertNotContains(viewer_resp, detail_url)
        self.assertNotContains(viewer_resp, admin_change_url)

    def test_icon_panels_expose_rename_add_child_and_disable_forms(self):
        self.set_language("en")
        self.login_admin()

        response = self.client.get(self.url, {"edit": "1"})

        self.assertContains(response, self.rename_child_url)
        self.assertContains(response, self.add_child_url)
        self.assertContains(response, self.sort_order_child_url)
        self.assertContains(response, self.disable_child_url)
        self.assertContains(response, self.enable_child_url)
        self.assertContains(response, 'name="confirm_disable"')
        self.assertContains(response, "Disable this unit")
        self.assertContains(response, "This only marks the unit inactive")

    # --- sort_order POST ----------------------------------------------------

    def test_admin_can_update_sort_order_for_one_unit_only(self):
        sibling = ChurchStructureUnit.objects.create(
            parent=self.root,
            unit_type=ChurchStructureUnit.UNIT_DISTRICT,
            code="D1",
            name="一区",
            name_en="District 1",
            sort_order=1,
        )
        self.login_admin()

        response = self.client.post(
            self.sort_order_child_url,
            {"sort_order": "20"},
        )

        self.assertRedirects(response, f"{self.url}?edit=1")
        self.child.refresh_from_db()
        sibling.refresh_from_db()
        self.assertEqual(self.child.sort_order, 20)
        self.assertEqual(sibling.sort_order, 1)

    def test_sort_order_update_preserves_structure_and_related_rows(self):
        from events.models import ServiceEventAudienceScope
        from studies.models import BibleStudySeriesAudienceScope

        grandchild = ChurchStructureUnit.objects.create(
            parent=self.child,
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="D2A",
            name="二区 A 组",
            name_en="District 2A",
            sort_order=4,
        )
        membership = ChurchStructureMembership.objects.create(
            user=self.normal_user,
            unit=self.child,
            status=ChurchStructureMembership.STATUS_ACTIVE,
            is_primary=True,
            start_date=timezone.localdate(),
        )
        ChurchRoleAssignment.objects.create(
            user=self.normal_user,
            role=ChurchRoleAssignment.ROLE_GROUP_LEADER,
            scope_type=ChurchRoleAssignment.SCOPE_SMALL_GROUP,
            structure_unit=grandchild,
        )
        event = ServiceEvent.objects.create(
            title="Sort Order Safety Service",
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
            start_datetime=timezone.now() + timedelta(days=1),
            status=ServiceEvent.STATUS_PUBLISHED,
        )
        ServiceEventAudienceScope.objects.create(
            service_event=event,
            unit=self.child,
        )
        team = MinistryTeam.objects.create(name="Sort Order Safety Team")
        assignment = TeamAssignment.objects.create(
            service_event=event,
            ministry_team=team,
            status=TeamAssignment.STATUS_SCHEDULED,
        )
        team_membership = TeamMembership.objects.create(
            team=team,
            user=self.normal_user,
        )
        TeamAssignmentMember.objects.create(
            assignment=assignment,
            membership=team_membership,
        )
        series = BibleStudySeries.objects.create(
            title="Sort Order Safety Series",
            start_date=timezone.localdate(),
        )
        BibleStudySeriesAudienceScope.objects.create(
            series=series,
            unit=self.child,
        )
        before = {
            "parent_id": self.child.parent_id,
            "name": self.child.name,
            "name_en": self.child.name_en,
            "code": self.child.code,
            "unit_type": self.child.unit_type,
            "is_active": self.child.is_active,
            "grandchild_parent_id": grandchild.parent_id,
            "memberships": ChurchStructureMembership.objects.count(),
            "service_scopes": ServiceEventAudienceScope.objects.count(),
            "series_scopes": BibleStudySeriesAudienceScope.objects.count(),
            "role_assignments": ChurchRoleAssignment.objects.count(),
            "team_assignments": TeamAssignment.objects.count(),
            "team_assignment_members": TeamAssignmentMember.objects.count(),
        }
        self.login_admin()

        self.client.post(self.sort_order_child_url, {"sort_order": "30"})

        self.child.refresh_from_db()
        grandchild.refresh_from_db()
        membership.refresh_from_db()
        after = {
            "parent_id": self.child.parent_id,
            "name": self.child.name,
            "name_en": self.child.name_en,
            "code": self.child.code,
            "unit_type": self.child.unit_type,
            "is_active": self.child.is_active,
            "grandchild_parent_id": grandchild.parent_id,
            "memberships": ChurchStructureMembership.objects.count(),
            "service_scopes": ServiceEventAudienceScope.objects.count(),
            "series_scopes": BibleStudySeriesAudienceScope.objects.count(),
            "role_assignments": ChurchRoleAssignment.objects.count(),
            "team_assignments": TeamAssignment.objects.count(),
            "team_assignment_members": TeamAssignmentMember.objects.count(),
        }
        self.assertEqual(before, after)
        self.assertEqual(self.child.sort_order, 30)
        self.assertEqual(membership.unit_id, self.child.id)

    def test_sort_order_update_rejects_invalid_value(self):
        self.set_language("en")
        self.login_admin()

        response = self.client.post(
            self.sort_order_child_url,
            {"sort_order": "second"},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sort order must be an integer.")
        self.child.refresh_from_db()
        self.assertEqual(self.child.sort_order, 3)

    def test_unauthorized_users_cannot_update_sort_order(self):
        self.login_viewer()

        viewer_response = self.client.post(
            self.sort_order_child_url,
            {"sort_order": "40"},
        )

        self.assertEqual(viewer_response.status_code, 302)
        self.child.refresh_from_db()
        self.assertEqual(self.child.sort_order, 3)

        self.client.logout()
        self.client.login(username="structure_plain", password="PlainPass123!")
        normal_response = self.client.post(
            self.sort_order_child_url,
            {"sort_order": "40"},
        )

        self.assertEqual(normal_response.status_code, 302)
        self.child.refresh_from_db()
        self.assertEqual(self.child.sort_order, 3)

    def test_sort_order_update_changes_sibling_display_order_and_preserves_hierarchy(self):
        first = ChurchStructureUnit.objects.create(
            parent=self.root,
            unit_type=ChurchStructureUnit.UNIT_DISTRICT,
            code="D1",
            name="一区",
            name_en="District 1",
            sort_order=10,
        )
        grandchild = ChurchStructureUnit.objects.create(
            parent=self.child,
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="D2A",
            name="二区 A 组",
            name_en="District 2A",
            sort_order=1,
        )
        self.login_admin()

        self.client.post(self.sort_order_child_url, {"sort_order": "5"})
        response = self.client.get(self.url)

        units = [row["unit"] for row in response.context["structure_rows"]]
        self.assertLess(units.index(self.child), units.index(first))
        self.assertLess(units.index(self.child), units.index(grandchild))
        self.assertEqual(grandchild.parent_id, self.child.id)

    def test_sort_order_update_writes_logentry_audit(self):
        from django.contrib.admin.models import LogEntry
        from django.contrib.contenttypes.models import ContentType

        self.login_admin()

        self.client.post(self.sort_order_child_url, {"sort_order": "44"})

        ct = ContentType.objects.get_for_model(ChurchStructureUnit)
        entry = LogEntry.objects.filter(
            content_type=ct,
            object_id=str(self.child.id),
            user=self.admin,
        ).first()
        self.assertIsNotNone(entry)
        self.assertIn("Updated structure unit sort_order", entry.change_message)
        self.assertIn("sort_order: 3 -> 44", entry.change_message)

    # --- sibling order POST -------------------------------------------------

    def test_admin_can_save_valid_sibling_order(self):
        first = ChurchStructureUnit.objects.create(
            parent=self.root,
            unit_type=ChurchStructureUnit.UNIT_DISTRICT,
            code="D1",
            name="一区",
            name_en="District 1",
            sort_order=1,
        )
        third = ChurchStructureUnit.objects.create(
            parent=self.root,
            unit_type=ChurchStructureUnit.UNIT_DISTRICT,
            code="D3",
            name="三区",
            name_en="District 3",
            sort_order=30,
        )
        self.login_admin()

        response = self.post_sibling_order(
            self.root.id,
            [third.id, self.child.id, first.id],
        )

        self.assertRedirects(response, f"{self.url}?edit=1")
        first.refresh_from_db()
        self.child.refresh_from_db()
        third.refresh_from_db()
        self.assertEqual(third.sort_order, 10)
        self.assertEqual(self.child.sort_order, 20)
        self.assertEqual(first.sort_order, 30)

    def test_sibling_order_update_preserves_structure_and_related_rows(self):
        from events.models import ServiceEventAudienceScope
        from studies.models import BibleStudySeriesAudienceScope

        sibling = ChurchStructureUnit.objects.create(
            parent=self.root,
            unit_type=ChurchStructureUnit.UNIT_DISTRICT,
            code="D1",
            name="一区",
            name_en="District 1",
            sort_order=1,
        )
        grandchild = ChurchStructureUnit.objects.create(
            parent=self.child,
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="D2A",
            name="二区 A 组",
            name_en="District 2A",
            sort_order=4,
        )
        membership = ChurchStructureMembership.objects.create(
            user=self.normal_user,
            unit=self.child,
            status=ChurchStructureMembership.STATUS_ACTIVE,
            is_primary=True,
            start_date=timezone.localdate(),
        )
        ChurchRoleAssignment.objects.create(
            user=self.normal_user,
            role=ChurchRoleAssignment.ROLE_GROUP_LEADER,
            scope_type=ChurchRoleAssignment.SCOPE_SMALL_GROUP,
            structure_unit=grandchild,
        )
        event = ServiceEvent.objects.create(
            title="Sibling Order Safety Service",
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
            start_datetime=timezone.now() + timedelta(days=1),
            status=ServiceEvent.STATUS_PUBLISHED,
        )
        ServiceEventAudienceScope.objects.create(
            service_event=event,
            unit=self.child,
        )
        team = MinistryTeam.objects.create(name="Sibling Order Safety Team")
        assignment = TeamAssignment.objects.create(
            service_event=event,
            ministry_team=team,
            status=TeamAssignment.STATUS_SCHEDULED,
        )
        team_membership = TeamMembership.objects.create(
            team=team,
            user=self.normal_user,
        )
        TeamAssignmentMember.objects.create(
            assignment=assignment,
            membership=team_membership,
        )
        series = BibleStudySeries.objects.create(
            title="Sibling Order Safety Series",
            start_date=timezone.localdate(),
        )
        BibleStudySeriesAudienceScope.objects.create(
            series=series,
            unit=self.child,
        )
        before = {
            "child_parent_id": self.child.parent_id,
            "child_name": self.child.name,
            "child_name_en": self.child.name_en,
            "child_code": self.child.code,
            "child_unit_type": self.child.unit_type,
            "child_is_active": self.child.is_active,
            "sibling_parent_id": sibling.parent_id,
            "grandchild_parent_id": grandchild.parent_id,
            "memberships": ChurchStructureMembership.objects.count(),
            "service_scopes": ServiceEventAudienceScope.objects.count(),
            "series_scopes": BibleStudySeriesAudienceScope.objects.count(),
            "role_assignments": ChurchRoleAssignment.objects.count(),
            "team_assignments": TeamAssignment.objects.count(),
            "team_assignment_members": TeamAssignmentMember.objects.count(),
        }
        self.login_admin()

        self.post_sibling_order(self.root.id, [self.child.id, sibling.id])

        self.child.refresh_from_db()
        sibling.refresh_from_db()
        grandchild.refresh_from_db()
        membership.refresh_from_db()
        after = {
            "child_parent_id": self.child.parent_id,
            "child_name": self.child.name,
            "child_name_en": self.child.name_en,
            "child_code": self.child.code,
            "child_unit_type": self.child.unit_type,
            "child_is_active": self.child.is_active,
            "sibling_parent_id": sibling.parent_id,
            "grandchild_parent_id": grandchild.parent_id,
            "memberships": ChurchStructureMembership.objects.count(),
            "service_scopes": ServiceEventAudienceScope.objects.count(),
            "series_scopes": BibleStudySeriesAudienceScope.objects.count(),
            "role_assignments": ChurchRoleAssignment.objects.count(),
            "team_assignments": TeamAssignment.objects.count(),
            "team_assignment_members": TeamAssignmentMember.objects.count(),
        }
        self.assertEqual(before, after)
        self.assertEqual(self.child.sort_order, 10)
        self.assertEqual(sibling.sort_order, 20)
        self.assertEqual(membership.unit_id, self.child.id)

    def test_sibling_order_update_preserves_parent_child_hierarchy_in_display(self):
        first = ChurchStructureUnit.objects.create(
            parent=self.root,
            unit_type=ChurchStructureUnit.UNIT_DISTRICT,
            code="D1",
            name="一区",
            name_en="District 1",
            sort_order=1,
        )
        grandchild = ChurchStructureUnit.objects.create(
            parent=self.child,
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="D2A",
            name="二区 A 组",
            name_en="District 2A",
            sort_order=1,
        )
        self.login_admin()

        self.post_sibling_order(self.root.id, [self.child.id, first.id])
        response = self.client.get(self.url)

        units = [row["unit"] for row in response.context["structure_rows"]]
        self.assertLess(units.index(self.child), units.index(grandchild))
        self.assertLess(units.index(grandchild), units.index(first))
        grandchild.refresh_from_db()
        self.assertEqual(grandchild.parent_id, self.child.id)

    def test_sibling_order_rejects_mixed_parent_unit_ids(self):
        sibling = ChurchStructureUnit.objects.create(
            parent=self.root,
            unit_type=ChurchStructureUnit.UNIT_DISTRICT,
            code="D1",
            name="一区",
            sort_order=1,
        )
        grandchild = ChurchStructureUnit.objects.create(
            parent=self.child,
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="D2A",
            name="二区 A 组",
            sort_order=5,
        )
        self.set_language("en")
        self.login_admin()

        response = self.post_sibling_order(
            self.root.id,
            [self.child.id, sibling.id, grandchild.id],
            follow=True,
        )

        self.assertContains(response, "Order was not saved")
        self.child.refresh_from_db()
        sibling.refresh_from_db()
        grandchild.refresh_from_db()
        self.assertEqual(self.child.sort_order, 3)
        self.assertEqual(sibling.sort_order, 1)
        self.assertEqual(grandchild.parent_id, self.child.id)

    def test_sibling_order_rejects_omitted_active_sibling(self):
        sibling = ChurchStructureUnit.objects.create(
            parent=self.root,
            unit_type=ChurchStructureUnit.UNIT_DISTRICT,
            code="D1",
            name="一区",
            sort_order=1,
        )
        self.set_language("en")
        self.login_admin()

        response = self.post_sibling_order(
            self.root.id,
            [self.child.id],
            follow=True,
        )

        self.assertContains(response, "Order was not saved")
        sibling.refresh_from_db()
        self.child.refresh_from_db()
        self.assertEqual(sibling.sort_order, 1)
        self.assertEqual(self.child.sort_order, 3)

    def test_sibling_order_rejects_duplicate_ids(self):
        sibling = ChurchStructureUnit.objects.create(
            parent=self.root,
            unit_type=ChurchStructureUnit.UNIT_DISTRICT,
            code="D1",
            name="一区",
            sort_order=1,
        )
        self.set_language("en")
        self.login_admin()

        response = self.post_sibling_order(
            self.root.id,
            [self.child.id, sibling.id, self.child.id],
            follow=True,
        )

        self.assertContains(response, "Order was not saved")
        self.child.refresh_from_db()
        sibling.refresh_from_db()
        self.assertEqual(self.child.sort_order, 3)
        self.assertEqual(sibling.sort_order, 1)

    def test_sibling_order_rejects_inactive_unit(self):
        self.set_language("en")
        self.login_admin()

        response = self.post_sibling_order(
            self.root.id,
            [self.child.id, self.inactive_child.id],
            follow=True,
        )

        self.assertContains(response, "Order was not saved")
        self.child.refresh_from_db()
        self.inactive_child.refresh_from_db()
        self.assertEqual(self.child.sort_order, 3)
        self.assertEqual(self.inactive_child.sort_order, 9)
        self.assertFalse(self.inactive_child.is_active)

    def test_sibling_order_rejects_invalid_parent_id(self):
        self.set_language("en")
        self.login_admin()

        response = self.post_sibling_order(
            999999,
            [self.child.id],
            follow=True,
        )

        self.assertContains(response, "Order was not saved")
        self.child.refresh_from_db()
        self.assertEqual(self.child.sort_order, 3)

    def test_unauthorized_users_cannot_save_sibling_order(self):
        sibling = ChurchStructureUnit.objects.create(
            parent=self.root,
            unit_type=ChurchStructureUnit.UNIT_DISTRICT,
            code="D1",
            name="一区",
            sort_order=1,
        )
        self.login_viewer()

        viewer_response = self.post_sibling_order(
            self.root.id,
            [sibling.id, self.child.id],
        )

        self.assertEqual(viewer_response.status_code, 302)
        sibling.refresh_from_db()
        self.child.refresh_from_db()
        self.assertEqual(sibling.sort_order, 1)
        self.assertEqual(self.child.sort_order, 3)

        self.client.logout()
        self.client.login(username="structure_plain", password="PlainPass123!")
        normal_response = self.post_sibling_order(
            self.root.id,
            [sibling.id, self.child.id],
        )

        self.assertEqual(normal_response.status_code, 302)
        sibling.refresh_from_db()
        self.child.refresh_from_db()
        self.assertEqual(sibling.sort_order, 1)
        self.assertEqual(self.child.sort_order, 3)

    def test_sibling_order_update_writes_logentry_audit(self):
        from django.contrib.admin.models import LogEntry
        from django.contrib.contenttypes.models import ContentType

        sibling = ChurchStructureUnit.objects.create(
            parent=self.root,
            unit_type=ChurchStructureUnit.UNIT_DISTRICT,
            code="D1",
            name="一区",
            sort_order=1,
        )
        self.login_admin()

        self.post_sibling_order(self.root.id, [self.child.id, sibling.id])

        ct = ContentType.objects.get_for_model(ChurchStructureUnit)
        entry = LogEntry.objects.filter(
            content_type=ct,
            object_id=str(self.root.id),
            user=self.admin,
        ).first()
        self.assertIsNotNone(entry)
        self.assertIn("Reordered same-parent structure unit siblings", entry.change_message)
        self.assertIn(f"parent_id={self.root.id!r}", entry.change_message)
        self.assertIn(f"ordered_unit_ids={[self.child.id, sibling.id]!r}", entry.change_message)

    # --- add child POST -----------------------------------------------------

    def test_admin_can_create_child_unit_under_active_parent(self):
        self.login_admin()

        response = self.client.post(self.add_child_url, self.child_payload())

        self.assertRedirects(response, f"{self.url}?edit=1")
        created = ChurchStructureUnit.objects.get(code="YOUTH")
        self.assertEqual(created.parent, self.child)
        self.assertEqual(created.name, "青年小组")
        self.assertEqual(created.name_en, "Youth Group")
        self.assertEqual(created.unit_type, ChurchStructureUnit.UNIT_SMALL_GROUP)
        self.assertEqual(created.sort_order, 7)
        self.assertTrue(created.is_active)

    def test_normal_user_cannot_create_child_unit(self):
        self.client.login(username="structure_plain", password="PlainPass123!")

        response = self.client.post(self.add_child_url, self.child_payload())

        self.assertEqual(response.status_code, 302)
        self.assertFalse(ChurchStructureUnit.objects.filter(code="YOUTH").exists())

    def test_invalid_child_unit_data_is_rejected(self):
        self.set_language("en")
        self.login_admin()
        before_units = ChurchStructureUnit.objects.count()

        response = self.client.post(
            self.add_child_url,
            self.child_payload(name="", unit_type=ChurchStructureUnit.UNIT_ROOT),
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(ChurchStructureUnit.objects.count(), before_units)
        self.assertContains(response, "Child unit was not added")

    def test_add_child_does_not_create_membership_audience_role_or_serving_rows(self):
        from events.models import ServiceEventAudienceScope
        from studies.models import BibleStudySeriesAudienceScope

        self.login_admin()
        before = (
            ChurchStructureMembership.objects.count(),
            ServiceEventAudienceScope.objects.count(),
            BibleStudySeriesAudienceScope.objects.count(),
            ChurchRoleAssignment.objects.count(),
            TeamAssignment.objects.count(),
            BibleStudyMeetingRole.objects.count(),
        )

        self.client.post(self.add_child_url, self.child_payload(code="NOSIDE"))

        after = (
            ChurchStructureMembership.objects.count(),
            ServiceEventAudienceScope.objects.count(),
            BibleStudySeriesAudienceScope.objects.count(),
            ChurchRoleAssignment.objects.count(),
            TeamAssignment.objects.count(),
            BibleStudyMeetingRole.objects.count(),
        )
        self.assertEqual(before, after)

    # --- disable POST -------------------------------------------------------

    def test_admin_can_soft_disable_safe_non_root_unit(self):
        self.login_admin()

        response = self.client.post(
            self.disable_child_url,
            {"confirm_disable": "on"},
        )

        self.assertRedirects(response, f"{self.url}?edit=1")
        self.child.refresh_from_db()
        self.assertFalse(self.child.is_active)
        self.assertTrue(ChurchStructureUnit.objects.filter(id=self.child.id).exists())

    def test_disable_root_unit_is_blocked(self):
        self.login_admin()

        self.client.post(self.disable_root_url, {"confirm_disable": "on"})

        self.root.refresh_from_db()
        self.assertTrue(self.root.is_active)

    def test_disable_unit_with_active_child_units_is_blocked(self):
        ChurchStructureUnit.objects.create(
            parent=self.child,
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="D2A",
            name="二区 A 组",
            name_en="District 2A",
        )
        self.login_admin()

        self.client.post(self.disable_child_url, {"confirm_disable": "on"})

        self.child.refresh_from_db()
        self.assertTrue(self.child.is_active)

    def test_disable_unit_with_active_memberships_is_blocked(self):
        ChurchStructureMembership.objects.create(
            user=self.normal_user,
            unit=self.child,
            status=ChurchStructureMembership.STATUS_ACTIVE,
            is_primary=True,
            start_date=timezone.localdate(),
        )
        self.login_admin()

        self.client.post(self.disable_child_url, {"confirm_disable": "on"})

        self.child.refresh_from_db()
        self.assertTrue(self.child.is_active)

    def test_disable_blocker_message_is_localized_in_chinese(self):
        ChurchStructureMembership.objects.create(
            user=self.normal_user,
            unit=self.child,
            status=ChurchStructureMembership.STATUS_ACTIVE,
            is_primary=True,
            start_date=timezone.localdate(),
        )
        self.set_language("zh")
        self.login_admin()

        response = self.client.post(
            self.disable_child_url,
            {"confirm_disable": "on"},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "无法停用此单元")
        self.assertContains(response, "启用中的归属记录")
        self.assertNotContains(response, "active memberships")
        self.child.refresh_from_db()
        self.assertTrue(self.child.is_active)

    def test_normal_user_cannot_disable_unit(self):
        self.client.login(username="structure_plain", password="PlainPass123!")

        response = self.client.post(
            self.disable_child_url,
            {"confirm_disable": "on"},
        )

        self.assertEqual(response.status_code, 302)
        self.child.refresh_from_db()
        self.assertTrue(self.child.is_active)

    def test_disable_does_not_delete_or_rewrite_related_rows(self):
        ended_membership = ChurchStructureMembership.objects.create(
            user=self.normal_user,
            unit=self.child,
            status=ChurchStructureMembership.STATUS_ENDED,
            is_primary=False,
            start_date=timezone.localdate(),
            end_date=timezone.localdate(),
        )
        before = (
            ChurchStructureMembership.objects.count(),
            TeamAssignment.objects.count(),
            BibleStudyMeetingRole.objects.count(),
            ChurchRoleAssignment.objects.count(),
        )
        self.login_admin()

        self.client.post(self.disable_child_url, {"confirm_disable": "on"})

        after = (
            ChurchStructureMembership.objects.count(),
            TeamAssignment.objects.count(),
            BibleStudyMeetingRole.objects.count(),
            ChurchRoleAssignment.objects.count(),
        )
        self.assertEqual(before, after)
        ended_membership.refresh_from_db()
        self.assertEqual(ended_membership.status, ChurchStructureMembership.STATUS_ENDED)
        self.assertFalse(ended_membership.is_primary)

    # --- enable POST --------------------------------------------------------

    def test_admin_can_re_enable_safe_inactive_unit(self):
        self.login_admin()

        response = self.client.post(self.enable_child_url)

        self.assertRedirects(response, f"{self.url}?edit=1")
        self.inactive_child.refresh_from_db()
        self.assertTrue(self.inactive_child.is_active)

    def test_re_enable_preserves_unrelated_structure_and_runtime_rows(self):
        from events.models import ServiceEventAudienceScope
        from studies.models import (
            BibleStudyMeetingAudienceScope,
            BibleStudySeriesAudienceScope,
        )

        ended_membership = ChurchStructureMembership.objects.create(
            user=self.normal_user,
            unit=self.inactive_child,
            status=ChurchStructureMembership.STATUS_ENDED,
            is_primary=False,
            start_date=timezone.localdate(),
            end_date=timezone.localdate(),
        )
        active_scope_unit = ChurchStructureUnit.objects.create(
            parent=self.root,
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="LIVE1",
            name="启用一组",
            name_en="Active Group 1",
        )
        ChurchRoleAssignment.objects.create(
            user=self.normal_user,
            role=ChurchRoleAssignment.ROLE_GROUP_LEADER,
            scope_type=ChurchRoleAssignment.SCOPE_SMALL_GROUP,
            structure_unit=active_scope_unit,
        )
        event = ServiceEvent.objects.create(
            title="Enable Safety Service",
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
            start_datetime=timezone.now() + timedelta(days=1),
            status=ServiceEvent.STATUS_PUBLISHED,
        )
        ServiceEventAudienceScope.objects.create(
            service_event=event,
            unit=active_scope_unit,
        )
        team = MinistryTeam.objects.create(name="Enable Safety Team")
        assignment = TeamAssignment.objects.create(
            service_event=event,
            ministry_team=team,
            status=TeamAssignment.STATUS_SCHEDULED,
        )
        team_membership = TeamMembership.objects.create(
            team=team,
            user=self.normal_user,
        )
        TeamAssignmentMember.objects.create(
            assignment=assignment,
            membership=team_membership,
        )
        series = BibleStudySeries.objects.create(
            title="Enable Safety Series",
            start_date=timezone.localdate(),
        )
        BibleStudySeriesAudienceScope.objects.create(
            series=series,
            unit=active_scope_unit,
        )
        lesson = BibleStudyLesson.objects.create(
            series=series,
            title="Enable Safety Lesson",
            lesson_date=timezone.localdate(),
        )
        meeting = BibleStudyMeeting.objects.create(
            lesson=lesson,
            anchor_unit=active_scope_unit,
            meeting_datetime=timezone.now() + timedelta(days=1),
            status=BibleStudyMeeting.STATUS_PUBLISHED,
        )
        BibleStudyMeetingAudienceScope.objects.create(
            meeting=meeting,
            unit=active_scope_unit,
        )
        BibleStudyMeetingRole.objects.create(
            meeting=meeting,
            role=BibleStudyMeetingRole.ROLE_DISCUSSION_LEADER,
            user=self.normal_user,
        )
        before = {
            "parent_id": self.inactive_child.parent_id,
            "code": self.inactive_child.code,
            "unit_type": self.inactive_child.unit_type,
            "memberships": ChurchStructureMembership.objects.count(),
            "service_scopes": ServiceEventAudienceScope.objects.count(),
            "series_scopes": BibleStudySeriesAudienceScope.objects.count(),
            "meeting_scopes": BibleStudyMeetingAudienceScope.objects.count(),
            "role_assignments": ChurchRoleAssignment.objects.count(),
            "team_assignments": TeamAssignment.objects.count(),
            "team_assignment_members": TeamAssignmentMember.objects.count(),
            "bible_study_roles": BibleStudyMeetingRole.objects.count(),
        }
        self.login_admin()

        self.client.post(self.enable_child_url)

        self.inactive_child.refresh_from_db()
        after = {
            "parent_id": self.inactive_child.parent_id,
            "code": self.inactive_child.code,
            "unit_type": self.inactive_child.unit_type,
            "memberships": ChurchStructureMembership.objects.count(),
            "service_scopes": ServiceEventAudienceScope.objects.count(),
            "series_scopes": BibleStudySeriesAudienceScope.objects.count(),
            "meeting_scopes": BibleStudyMeetingAudienceScope.objects.count(),
            "role_assignments": ChurchRoleAssignment.objects.count(),
            "team_assignments": TeamAssignment.objects.count(),
            "team_assignment_members": TeamAssignmentMember.objects.count(),
            "bible_study_roles": BibleStudyMeetingRole.objects.count(),
        }
        self.assertEqual(before, after)
        self.assertTrue(self.inactive_child.is_active)
        ended_membership.refresh_from_db()
        self.assertEqual(ended_membership.status, ChurchStructureMembership.STATUS_ENDED)
        self.assertFalse(ended_membership.is_primary)

    def test_re_enable_does_not_cascade_to_inactive_children(self):
        inactive_grandchild = ChurchStructureUnit.objects.create(
            parent=self.inactive_child,
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="OLD1A",
            name="停用一组 A",
            name_en="Inactive Group 1A",
            is_active=False,
        )
        self.login_admin()

        self.client.post(self.enable_child_url)

        self.inactive_child.refresh_from_db()
        inactive_grandchild.refresh_from_db()
        self.assertTrue(self.inactive_child.is_active)
        self.assertFalse(inactive_grandchild.is_active)

    def test_re_enable_is_blocked_when_parent_is_inactive(self):
        inactive_parent = ChurchStructureUnit.objects.create(
            parent=self.root,
            unit_type=ChurchStructureUnit.UNIT_DISTRICT,
            code="OLDP",
            name="停用父级",
            name_en="Inactive Parent",
            is_active=False,
        )
        inactive_child = ChurchStructureUnit.objects.create(
            parent=inactive_parent,
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="OLDP1",
            name="停用子级",
            name_en="Inactive Child",
            is_active=False,
        )
        self.set_language("en")
        self.login_admin()

        response = self.client.post(
            reverse("staff_structure_unit_enable", args=[inactive_child.id]),
            follow=True,
        )

        inactive_child.refresh_from_db()
        self.assertFalse(inactive_child.is_active)
        self.assertContains(response, "parent unit is inactive")

    def test_re_enable_already_active_unit_warns_without_related_changes(self):
        before = (
            ChurchStructureMembership.objects.count(),
            ChurchRoleAssignment.objects.count(),
            TeamAssignment.objects.count(),
            BibleStudyMeetingRole.objects.count(),
        )
        self.set_language("en")
        self.login_admin()

        response = self.client.post(
            reverse("staff_structure_unit_enable", args=[self.child.id]),
            follow=True,
        )

        after = (
            ChurchStructureMembership.objects.count(),
            ChurchRoleAssignment.objects.count(),
            TeamAssignment.objects.count(),
            BibleStudyMeetingRole.objects.count(),
        )
        self.child.refresh_from_db()
        self.assertTrue(self.child.is_active)
        self.assertEqual(before, after)
        self.assertContains(response, "This unit is already active.")

    def test_normal_user_cannot_re_enable_unit(self):
        self.client.login(username="structure_plain", password="PlainPass123!")

        response = self.client.post(self.enable_child_url)

        self.assertEqual(response.status_code, 302)
        self.inactive_child.refresh_from_db()
        self.assertFalse(self.inactive_child.is_active)

    def test_re_enable_writes_logentry_audit(self):
        from django.contrib.admin.models import LogEntry
        from django.contrib.contenttypes.models import ContentType

        self.login_admin()

        self.client.post(self.enable_child_url)

        ct = ContentType.objects.get_for_model(ChurchStructureUnit)
        entry = LogEntry.objects.filter(
            content_type=ct,
            object_id=str(self.inactive_child.id),
            user=self.admin,
        ).first()
        self.assertIsNotNone(entry)
        self.assertIn("Re-enabled structure unit", entry.change_message)
        self.assertIn("No child units, memberships", entry.change_message)

    def test_inactive_unit_detail_shows_re_enable_action_for_structure_admin(self):
        self.set_language("en")
        self.login_admin()

        response = self.client.get(
            reverse("church_structure_unit_detail", args=[self.inactive_child.id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "This unit is inactive")
        self.assertContains(response, "Re-enable this unit")
        self.assertContains(
            response,
            "It does not re-enable children, create memberships, rewrite audience scopes, role scopes, or serving assignments.",
        )

    def test_unit_detail_displays_sort_order_metadata(self):
        self.set_language("en")
        self.login_admin()

        response = self.client.get(
            reverse("church_structure_unit_detail", args=[self.child.id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sort order")
        self.assertContains(response, "<dd>3</dd>", html=True)

    # --- rename POST --------------------------------------------------------

    def test_rename_updates_only_name_and_name_en(self):
        self.login_admin()
        before_units = ChurchStructureUnit.objects.count()

        response = self.client.post(
            self.rename_child_url,
            {"name": "第二区", "name_en": "Second District"},
        )

        self.assertRedirects(response, f"{self.url}?edit=1")

        self.child.refresh_from_db()
        self.assertEqual(self.child.name, "第二区")
        self.assertEqual(self.child.name_en, "Second District")
        # Nothing structural changed.
        self.assertEqual(self.child.parent_id, self.root.id)
        self.assertEqual(
            self.child.unit_type, ChurchStructureUnit.UNIT_DISTRICT
        )
        self.assertEqual(self.child.code, "D2")
        self.assertTrue(self.child.is_active)
        self.assertEqual(self.child.sort_order, 3)
        self.assertEqual(ChurchStructureUnit.objects.count(), before_units)

    def test_rename_shows_success_message(self):
        self.set_language("en")
        self.login_admin()

        response = self.client.post(
            self.rename_child_url,
            {"name": "二区", "name_en": "District Two"},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Display name updated.")

    def test_rename_does_not_create_audience_or_membership_rows(self):
        from events.models import ServiceEventAudienceScope
        from studies.models import BibleStudySeriesAudienceScope

        self.login_admin()
        before = (
            ServiceEventAudienceScope.objects.count(),
            BibleStudySeriesAudienceScope.objects.count(),
            ChurchStructureMembership.objects.count(),
        )

        self.client.post(
            self.rename_child_url,
            {"name": "二区改", "name_en": "District 2b"},
        )

        after = (
            ServiceEventAudienceScope.objects.count(),
            BibleStudySeriesAudienceScope.objects.count(),
            ChurchStructureMembership.objects.count(),
        )
        self.assertEqual(before, after)

    def test_rename_writes_logentry_audit(self):
        from django.contrib.admin.models import LogEntry
        from django.contrib.contenttypes.models import ContentType

        self.login_admin()
        # Rename to new values so old != new for both fields.
        self.client.post(
            self.rename_child_url,
            {"name": "第二区", "name_en": "Second District"},
        )

        ct = ContentType.objects.get_for_model(ChurchStructureUnit)
        entry = LogEntry.objects.filter(
            content_type=ct,
            object_id=str(self.child.id),
            user=self.admin,
        ).first()
        self.assertIsNotNone(entry)
        # The audit message records old and new values for both fields.
        # Use repr() (quoted) forms so the old value "二区" is not matched as a
        # substring of the new value "第二区".
        self.assertIn(repr("二区"), entry.change_message)
        self.assertIn(repr("第二区"), entry.change_message)
        self.assertIn(repr("District 2"), entry.change_message)
        self.assertIn(repr("Second District"), entry.change_message)

    def test_rename_root_is_forbidden(self):
        self.login_admin()

        response = self.client.post(
            self.rename_root_url,
            {"name": "改名", "name_en": "Renamed Root"},
        )

        self.assertEqual(response.status_code, 403)
        self.root.refresh_from_db()
        self.assertEqual(self.root.name, "全教会")
        self.assertEqual(self.root.name_en, "Whole Church")

    def test_rename_blank_name_does_not_change_data(self):
        self.set_language("en")
        self.login_admin()

        response = self.client.post(
            self.rename_child_url,
            {"name": "   ", "name_en": "District 2"},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Please enter a display name.")
        self.child.refresh_from_db()
        self.assertEqual(self.child.name, "二区")
        self.assertEqual(self.child.name_en, "District 2")

    def test_view_only_staff_cannot_rename(self):
        self.login_viewer()

        response = self.client.post(
            self.rename_child_url,
            {"name": "Hacked", "name_en": "Hacked"},
        )

        self.assertEqual(response.status_code, 403)
        self.child.refresh_from_db()
        self.assertEqual(self.child.name, "二区")
        self.assertEqual(self.child.name_en, "District 2")

    def test_normal_user_cannot_rename(self):
        self.client.login(
            username="structure_plain", password="PlainPass123!"
        )

        response = self.client.post(
            self.rename_child_url,
            {"name": "Hacked", "name_en": "Hacked"},
        )

        # staff_member_required redirects non-staff to the admin login.
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response.url)
        self.child.refresh_from_db()
        self.assertEqual(self.child.name, "二区")

    def test_rename_rejects_get(self):
        self.login_admin()

        response = self.client.get(self.rename_child_url)

        self.assertEqual(response.status_code, 405)


class StaffStructureMappingReviewTests(TestCase):
    """LEGACY-STRUCTURE-SURFACE-RETIRE.1A retires mapping review URLs."""

    def setUp(self):
        self.staff = User.objects.create_user(
            username="mapping_retired_staff",
            password="StaffPass123!",
            is_staff=True,
        )

    def test_mapping_review_url_name_is_retired(self):
        with self.assertRaises(Exception):
            reverse("staff_structure_mapping_review")

    def test_mapping_review_path_is_not_routable(self):
        self.client.login(username="mapping_retired_staff", password="StaffPass123!")

        response = self.client.get("/staff/structure/mappings/")

        self.assertEqual(response.status_code, 404)

    def test_structure_map_no_longer_links_to_mapping_review(self):
        self.client.login(username="mapping_retired_staff", password="StaffPass123!")

        response = self.client.get(reverse("staff_structure_map"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "/staff/structure/mappings/")
        self.assertNotContains(response, "Review Data Mappings")



class StaffStructureMappingEditTests(TestCase):
    """LEGACY-STRUCTURE-SURFACE-RETIRE.1A retires mapping edit URLs."""

    def setUp(self):
        self.staff = User.objects.create_user(
            username="mapping_edit_retired_staff",
            password="StaffPass123!",
            is_staff=True,
        )

    def test_mapping_edit_url_name_is_retired(self):
        with self.assertRaises(Exception):
            reverse("staff_structure_mapping_edit", args=["small-group", 1])

    def test_mapping_edit_path_is_not_routable(self):
        self.client.login(
            username="mapping_edit_retired_staff",
            password="StaffPass123!",
        )

        response = self.client.get("/staff/structure/mappings/small-group/1/edit/")

        self.assertEqual(response.status_code, 404)



class StaffModerationQueueTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(
            username="moderation_staff",
            password="StaffPass123!",
            is_staff=True,
        )
        self.normal_user = User.objects.create_user(
            username="moderation_user",
            password="UserPass123!",
        )
        self.reporter = User.objects.create_user(
            username="moderation_reporter",
            password="ReporterPass123!",
        )
        self.plan = ReadingPlan.objects.create(name="Moderation Plan")
        self.day = ReadingPlanDay.objects.create(
            plan=self.plan,
            day_number=1,
            reading_text="John 1",
        )

    def set_language(self, language="en"):
        session = self.client.session
        session["language"] = language
        session.save()

    def create_queue_data(self):
        reported_prayer = PrayerRequest.objects.create(
            user=self.normal_user,
            title="Reported prayer queue",
            body="Please review this prayer.",
        )
        PrayerReport.objects.create(
            prayer_request=reported_prayer,
            reporter=self.reporter,
            status=PrayerReport.STATUS_OPEN,
        )
        PrayerRequest.objects.create(
            user=self.normal_user,
            title="Hidden prayer queue",
            body="Hidden prayer body.",
            is_hidden=True,
            hidden_at=timezone.now(),
            hidden_by=self.staff,
        )

        reported_reflection = ReflectionComment.objects.create(
            plan_day=self.day,
            user=self.normal_user,
            body="Reported reflection post.",
            scripture_ref_key="John 1:1",
        )
        ReflectionReport.objects.create(
            comment=reported_reflection,
            reporter=self.reporter,
            status=ReflectionReport.STATUS_OPEN,
        )
        reply_parent = ReflectionComment.objects.create(
            plan_day=self.day,
            user=self.normal_user,
            body="Parent reflection.",
            scripture_ref_key="John 1:2",
        )
        reported_reply = ReflectionComment.objects.create(
            plan_day=self.day,
            user=self.normal_user,
            parent=reply_parent,
            body="Reported reflection reply.",
            scripture_ref_key="John 1:2",
        )
        ReflectionReport.objects.create(
            comment=reported_reply,
            reporter=self.reporter,
            status=ReflectionReport.STATUS_OPEN,
        )
        ReflectionComment.objects.create(
            plan_day=self.day,
            user=self.normal_user,
            body="Hidden reflection post.",
            scripture_ref_key="Psalm 1:1",
            is_hidden=True,
            hidden_at=timezone.now(),
            hidden_by=self.staff,
        )
        ReflectionComment.objects.create(
            plan_day=self.day,
            user=self.normal_user,
            parent=reply_parent,
            body="Hidden reflection reply.",
            scripture_ref_key="Psalm 1:2",
            is_hidden=True,
            hidden_at=timezone.now(),
            hidden_by=self.staff,
        )

    def test_staff_moderation_queue_requires_staff_access(self):
        self.client.login(username="moderation_user", password="UserPass123!")

        response = self.client.get(reverse("staff_moderation_queue"))

        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response.url)

    def test_staff_moderation_queue_anonymous_redirects_to_login(self):
        response = self.client.get(reverse("staff_moderation_queue"))

        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response.url)

    def test_staff_moderation_queue_shows_counts_and_existing_workflow_links(self):
        self.create_queue_data()
        self.set_language("en")
        self.client.login(username="moderation_staff", password="StaffPass123!")

        response = self.client.get(reverse("staff_moderation_queue"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Moderation Queue")
        self.assertContains(response, "This page summarizes existing report and hidden states only")
        self.assertContains(response, "Reported prayer requests")
        self.assertContains(response, "Reported prayer comments")
        self.assertContains(response, "Hidden prayer requests")
        self.assertContains(response, "Hidden prayer comments")
        self.assertContains(response, "Reported reflections")
        self.assertContains(response, "Reported reflection replies")
        self.assertContains(response, "Hidden reflections")
        self.assertContains(response, "Hidden reflection replies")
        self.assertContains(response, "Reported prayer queue")
        self.assertContains(response, "Hidden prayer queue")
        self.assertContains(response, "John 1:1")
        self.assertContains(response, "John 1:2")
        self.assertContains(response, "Psalm 1:1")
        self.assertContains(response, "Psalm 1:2")
        self.assertContains(response, reverse("staff_prayer_reports"))
        self.assertContains(response, reverse("staff_reflection_reports"))
        self.assertContains(response, "Existing data does not track separate report or hidden state")
        self.assertNotContains(response, "Hide Prayer Request")
        self.assertEqual(response.context["moderation_counts"]["reported_prayer_requests"], 1)
        self.assertEqual(response.context["moderation_counts"]["reported_prayer_comments"], 0)
        self.assertEqual(response.context["moderation_counts"]["hidden_prayer_requests"], 1)
        self.assertEqual(response.context["moderation_counts"]["hidden_prayer_comments"], 0)
        self.assertEqual(response.context["moderation_counts"]["reported_reflection_posts"], 1)
        self.assertEqual(response.context["moderation_counts"]["reported_reflection_replies"], 1)
        self.assertEqual(response.context["moderation_counts"]["hidden_reflection_posts"], 1)
        self.assertEqual(response.context["moderation_counts"]["hidden_reflection_replies"], 1)

    def test_staff_moderation_queue_empty_state_is_bilingual(self):
        self.set_language("zh")
        self.client.login(username="moderation_staff", password="StaffPass123!")

        response = self.client.get(reverse("staff_moderation_queue"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "内容审核队列")
        self.assertContains(response, "此队列目前没有项目")
        self.assertContains(response, "现有资料没有单独记录")
        self.assertEqual(response.context["moderation_counts"]["reported_prayer_requests"], 0)
        self.assertEqual(response.context["moderation_counts"]["hidden_reflection_replies"], 0)


class StaffPasswordResetTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(
            username="staff",
            email="staff@example.com",
            password="StaffPass123!",
            is_staff=True,
        )

        self.user = User.objects.create_user(
            username="elder",
            email="",
            password="OldPass123!",
        )


    def test_staff_user_list_requires_staff(self):
        self.client.login(username="elder", password="OldPass123!")

        response = self.client.get(reverse("staff_user_list"))

        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response.url)

    def test_staff_can_access_user_list(self):
        session = self.client.session
        session["language"] = "en"
        session.save()
        self.client.login(username="staff", password="StaffPass123!")

        response = self.client.get(reverse("staff_user_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "User Admin")
        self.assertContains(response, "elder")

    def test_chinese_staff_user_list_uses_chinese_labels(self):
        session = self.client.session
        session["language"] = "zh"
        session.save()
        self.client.login(username="staff", password="StaffPass123!")

        response = self.client.get(reverse("staff_user_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "用户管理")
        self.assertContains(response, "搜索用户，并为无法使用邮件找回密码的成员重置密码")
        self.assertContains(response, "搜索")
        self.assertContains(response, "用户名")
        self.assertContains(response, "邮箱")
        self.assertContains(response, "语言")
        self.assertContains(response, "密码状态")
        self.assertContains(response, "操作")
        self.assertContains(response, "重置密码")
        self.assertContains(response, "正常")
        self.assertNotContains(response, "User Admin")
        self.assertNotContains(response, "Reset Password")

    def test_staff_can_search_user_list(self):
        self.client.login(username="staff", password="StaffPass123!")

        # PROFILE-SG-FIELD-RETIRE.1A removed group-name search; search by username.
        response = self.client.get(reverse("staff_user_list"), {"q": "eld"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "elder")

    def test_staff_can_reset_user_password(self):
        self.client.login(username="staff", password="StaffPass123!")

        response = self.client.post(
            reverse("staff_user_password_reset", args=[self.user.id]),
            {
                "new_password1": "TempPass123!",
                "new_password2": "TempPass123!",
                "require_password_change": "on",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("staff_user_list"))

        self.user.refresh_from_db()
        self.user.profile.refresh_from_db()

        self.assertTrue(self.user.check_password("TempPass123!"))
        self.assertTrue(self.user.profile.must_change_password)

    def test_user_with_must_change_password_is_redirected(self):
        self.user.profile.must_change_password = True
        self.user.profile.save()

        self.client.login(username="elder", password="OldPass123!")

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("password_change"))

    def test_password_change_clears_must_change_password_flag(self):
        self.user.set_password("TempPass123!")
        self.user.save()

        self.user.profile.must_change_password = True
        self.user.profile.save()

        self.client.login(username="elder", password="TempPass123!")

        response = self.client.post(
            reverse("password_change"),
            {
                "old_password": "TempPass123!",
                "new_password1": "NewStrongPass123!",
                "new_password2": "NewStrongPass123!",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("password_change_done"))

        self.user.profile.refresh_from_db()

        self.assertFalse(self.user.profile.must_change_password)

        self.client.logout()

        login_success = self.client.login(
            username="elder",
            password="NewStrongPass123!",
        )

        self.assertTrue(login_success)

    def _set_language(self, language):
        session = self.client.session
        session["language"] = language
        session.save()

    def test_chinese_staff_reset_page_labels_localized(self):
        self._set_language("zh")
        self.client.login(username="staff", password="StaffPass123!")

        response = self.client.get(
            reverse("staff_user_password_reset", args=[self.user.id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "重置密码")
        self.assertContains(response, "返回用户管理")
        self.assertContains(response, "为该用户设置一个新的临时密码")
        self.assertContains(response, "新密码")
        self.assertContains(response, "确认新密码")
        self.assertContains(response, "要求用户下次登录时修改密码")
        self.assertContains(response, "请私下把临时密码交给该用户")
        # English reset UI strings must be gone in Chinese mode.
        self.assertNotContains(response, "Reset Password")
        self.assertNotContains(response, "Back to User Admin")
        self.assertNotContains(response, "Set a new temporary password")
        self.assertNotContains(response, "New password confirmation")
        self.assertNotContains(response, "Require user to change password")

    def test_english_staff_reset_page_labels(self):
        self._set_language("en")
        self.client.login(username="staff", password="StaffPass123!")

        response = self.client.get(
            reverse("staff_user_password_reset", args=[self.user.id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Reset Password")
        self.assertContains(response, "New password")
        self.assertContains(response, "Require user to change password on next login")

    def test_chinese_staff_reset_weak_password_error_localized(self):
        self._set_language("zh")
        self.client.login(username="staff", password="StaffPass123!")

        response = self.client.post(
            reverse("staff_user_password_reset", args=[self.user.id]),
            {
                "new_password1": "Ab1!",
                "new_password2": "Ab1!",
                "require_password_change": "on",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "密码太短")
        self.assertNotContains(response, "This password is too short")
        # Password must NOT change on validation failure.
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("OldPass123!"))

    def test_chinese_staff_reset_success_message_localized(self):
        self._set_language("zh")
        self.client.login(username="staff", password="StaffPass123!")

        response = self.client.post(
            reverse("staff_user_password_reset", args=[self.user.id]),
            {
                "new_password1": "TempPass123!",
                "new_password2": "TempPass123!",
                "require_password_change": "on",
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "已重置 elder 的密码")
        self.assertNotContains(response, "Password reset for elder")
        # Behavior still works: password changed and flag set.
        self.user.refresh_from_db()
        self.user.profile.refresh_from_db()
        self.assertTrue(self.user.check_password("TempPass123!"))
        self.assertTrue(self.user.profile.must_change_password)


class AccountSignupLanguageTests(TestCase):
    def setUp(self):
        self.unit = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="SMALLGROUP-1",
            name="Rainbow 4",
            name_en="Rainbow 4",
        )
        self.fellowship_unit = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_FELLOWSHIP,
            code="FELLOWSHIP",
            name="Fellowship",
            name_en="Fellowship",
        )

    def test_signup_does_not_require_email_or_requested_unit(self):
        response = self.client.post(
            reverse("signup"),
            {
                "username": "elder_user",
                "email": "",
                "requested_unit": "",
                "password1": "StrongPass123!",
                "password2": "StrongPass123!",
            },
        )

        self.assertEqual(response.status_code, 302)

        user = User.objects.get(username="elder_user")
        self.assertEqual(user.email, "")
        self.assertFalse(
            ChurchStructureMembership.objects.filter(user=user).exists(),
        )

    def test_signup_with_requested_unit_creates_pending_membership_request(self):
        response = self.client.post(
            reverse("signup"),
            {
                "username": "requested_user",
                "email": "",
                "requested_unit": self.unit.id,
                "password1": "StrongPass123!",
                "password2": "StrongPass123!",
            },
        )

        self.assertEqual(response.status_code, 302)

        user = User.objects.get(username="requested_user")
        user.profile.refresh_from_db()
        membership = ChurchStructureMembership.objects.get(user=user)

        self.assertEqual(membership.unit, self.unit)
        self.assertEqual(
            membership.membership_type,
            ChurchStructureMembership.TYPE_SMALL_GROUP_MEMBER,
        )
        self.assertEqual(membership.status, ChurchStructureMembership.STATUS_REQUESTED)
        self.assertFalse(membership.is_primary)
        self.assertEqual(membership.requested_by, user)
        self.assertIsNone(membership.approved_by)
        self.assertIsNone(membership.approved_at)
        self.assertIsNone(membership.start_date)

    def test_signup_allows_active_fellowship_request(self):
        response = self.client.post(
            reverse("signup"),
            {
                "username": "fellowship_user",
                "email": "",
                "requested_unit": self.fellowship_unit.id,
                "password1": "StrongPass123!",
                "password2": "StrongPass123!",
            },
        )

        self.assertEqual(response.status_code, 302)

        user = User.objects.get(username="fellowship_user")
        membership = ChurchStructureMembership.objects.get(user=user)

        self.assertEqual(membership.unit, self.fellowship_unit)
        self.assertEqual(membership.status, ChurchStructureMembership.STATUS_REQUESTED)

    def test_signup_rejects_inactive_requested_unit(self):
        inactive_unit = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="INACTIVE",
            name="Inactive",
            is_active=False,
        )

        response = self.client.post(
            reverse("signup"),
            {
                "username": "inactive_request_user",
                "email": "",
                "requested_unit": inactive_unit.id,
                "password1": "StrongPass123!",
                "password2": "StrongPass123!",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username="inactive_request_user").exists())
        self.assertEqual(ChurchStructureMembership.objects.count(), 0)

    def test_signup_rejects_non_requestable_unit_type(self):
        root_unit = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_ROOT,
            code="ROOT",
            name="Root",
        )

        response = self.client.post(
            reverse("signup"),
            {
                "username": "root_request_user",
                "email": "",
                "requested_unit": root_unit.id,
                "password1": "StrongPass123!",
                "password2": "StrongPass123!",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username="root_request_user").exists())
        self.assertEqual(ChurchStructureMembership.objects.count(), 0)

    def test_duplicate_pending_signup_request_helper_updates_existing_request(self):
        user = User.objects.create_user(username="duplicate_pending")
        original = ChurchStructureMembership.objects.create(
            user=user,
            unit=self.unit,
            status=ChurchStructureMembership.STATUS_REQUESTED,
            is_primary=True,
            start_date=timezone.localdate(),
            approved_by=user,
            approved_at=timezone.now(),
        )

        membership = create_or_update_signup_membership_request(
            user,
            self.fellowship_unit,
        )

        self.assertEqual(membership.id, original.id)
        self.assertEqual(ChurchStructureMembership.objects.filter(user=user).count(), 1)
        membership.refresh_from_db()
        self.assertEqual(membership.unit, self.fellowship_unit)
        self.assertEqual(membership.status, ChurchStructureMembership.STATUS_REQUESTED)
        self.assertEqual(
            membership.membership_type,
            ChurchStructureMembership.TYPE_SMALL_GROUP_MEMBER,
        )
        self.assertFalse(membership.is_primary)
        self.assertEqual(membership.requested_by, user)
        self.assertIsNone(membership.approved_by)
        self.assertIsNone(membership.approved_at)
        self.assertIsNone(membership.start_date)

    def test_requested_signup_membership_does_not_grant_service_event_visibility(self):
        event = ServiceEvent.objects.create(
            title="District Service",
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
            start_datetime=timezone.now(),
            status=ServiceEvent.STATUS_PUBLISHED,
        )

        response = self.client.post(
            reverse("signup"),
            {
                "username": "visibility_request_user",
                "email": "",
                "requested_unit": self.unit.id,
                "password1": "StrongPass123!",
                "password2": "StrongPass123!",
            },
        )

        self.assertEqual(response.status_code, 302)

        user = User.objects.get(username="visibility_request_user")
        user.profile.refresh_from_db()
        self.assertFalse(event.can_be_seen_by(user))


        # SE-RETIRE.1B: the signup request grants nothing, and the retired
        # zero-row fallback means Profile.small_group no longer makes a
        # zero-row event visible either.
        self.assertFalse(event.can_be_seen_by(user))

    def test_signup_request_appears_in_staff_membership_request_flow(self):
        staff = User.objects.create_user(
            username="signup_staff",
            password="StaffPass123!",
            is_staff=True,
        )

        response = self.client.post(
            reverse("signup"),
            {
                "username": "staff_handoff_user",
                "email": "",
                "requested_unit": self.unit.id,
                "password1": "StrongPass123!",
                "password2": "StrongPass123!",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.client.logout()
        self.client.login(username=staff.username, password="StaffPass123!")

        response = self.client.get(reverse("staff_membership_request_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "staff_handoff_user")
        self.assertContains(response, "Rainbow 4")
        self.assertContains(response, "等待审核")

    def test_language_switch_updates_session(self):
        response = self.client.post(
            reverse("change_language"),
            {
                "language": "en",
                "next": reverse("login"),
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("login"))
        self.assertEqual(self.client.session["language"], "en")

    def test_signup_page_can_render_chinese_labels(self):
        self.client.post(
            reverse("change_language"),
            {
                "language": "zh",
                "next": reverse("signup"),
            },
        )

        response = self.client.get(reverse("signup"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Email（可选）")
        self.assertContains(response, "我参加的小组")
        self.assertContains(response, "Rainbow 4")
        self.assertNotContains(response, "SMALLGROUP-1 - Rainbow 4")

    def test_signup_page_can_render_english_labels(self):
        self.client.post(
            reverse("change_language"),
            {
                "language": "en",
                "next": reverse("signup"),
            },
        )

        response = self.client.get(reverse("signup"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Email (optional)")
        self.assertContains(response, "Your small group")
        self.assertContains(response, "Rainbow 4")
        self.assertNotContains(response, "SMALLGROUP-1 - Rainbow 4")

    def _set_language(self, language):
        self.client.post(
            reverse("change_language"),
            {"language": language, "next": reverse("signup")},
        )

    def test_signup_chinese_help_text_is_localized(self):
        self._set_language("zh")

        response = self.client.get(reverse("signup"))

        self.assertEqual(response.status_code, 200)
        # Localized Chinese help text is present.
        self.assertContains(response, "150 个字符以内")
        self.assertContains(response, "密码至少 8 个字符")
        self.assertContains(response, "请再次输入相同的密码")
        # Default English Django help text must not leak into the Chinese page.
        self.assertNotContains(response, "Required. 150 characters or fewer")
        self.assertNotContains(response, "Your password can")  # "can't be too similar"
        self.assertNotContains(response, "Enter the same password as before")

    def test_signup_english_help_text_is_present(self):
        self._set_language("en")

        response = self.client.get(reverse("signup"))

        self.assertEqual(response.status_code, 200)
        # English keeps reasonable helper text and the confirmation label.
        self.assertContains(response, "150 characters or fewer")
        self.assertContains(response, "Password confirmation")

    def test_signup_chinese_password_mismatch_shows_localized_error(self):
        self._set_language("zh")

        response = self.client.post(
            reverse("signup"),
            {
                "username": "mismatch_user",
                "email": "",
                "requested_unit": "",
                "password1": "StrongPass123!",
                "password2": "DifferentPass123!",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "两次输入的密码不一致")
        self.assertNotContains(response, "The two password fields")
        self.assertFalse(User.objects.filter(username="mismatch_user").exists())

    def test_login_page_chinese_labels(self):
        self._set_language("zh")

        response = self.client.get(reverse("login"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "用户名")
        self.assertContains(response, "密码")
        # The localized login form label should replace the English field label.
        self.assertNotContains(response, ">Username:<")

    def test_login_page_english_labels(self):
        self._set_language("en")

        response = self.client.get(reverse("login"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Username")
        self.assertContains(response, "Password")

    def test_signup_chinese_too_short_password_error_localized(self):
        self._set_language("zh")

        response = self.client.post(
            reverse("signup"),
            {
                "username": "shortpw_user",
                "email": "",
                "requested_unit": "",
                "password1": "Ab1!",
                "password2": "Ab1!",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "密码太短")
        self.assertNotContains(response, "This password is too short")
        self.assertFalse(User.objects.filter(username="shortpw_user").exists())

    def test_signup_chinese_common_password_error_localized(self):
        self._set_language("zh")

        response = self.client.post(
            reverse("signup"),
            {
                "username": "commonpw_user",
                "email": "",
                "requested_unit": "",
                "password1": "password",
                "password2": "password",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "这个密码太常见")
        self.assertNotContains(response, "This password is too common")
        self.assertFalse(User.objects.filter(username="commonpw_user").exists())

    def test_signup_chinese_numeric_password_error_localized(self):
        self._set_language("zh")

        response = self.client.post(
            reverse("signup"),
            {
                "username": "numericpw_user",
                "email": "",
                "requested_unit": "",
                "password1": "29384756102",
                "password2": "29384756102",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "密码不能全部是数字")
        self.assertNotContains(response, "This password is entirely numeric")
        self.assertFalse(User.objects.filter(username="numericpw_user").exists())

    def test_signup_english_weak_password_shows_english_error(self):
        self._set_language("en")

        response = self.client.post(
            reverse("signup"),
            {
                "username": "weakpw_user",
                "email": "",
                "requested_unit": "",
                "password1": "Ab1!",
                "password2": "Ab1!",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "too short")
        self.assertFalse(User.objects.filter(username="weakpw_user").exists())

    def test_signup_chinese_duplicate_username_error_localized(self):
        User.objects.create_user(username="taken_user", password="StrongPass123!")
        self._set_language("zh")

        response = self.client.post(
            reverse("signup"),
            {
                "username": "taken_user",
                "email": "",
                "requested_unit": "",
                "password1": "StrongPass123!",
                "password2": "StrongPass123!",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "这个用户名已被使用")
        self.assertNotContains(response, "already exists")

    def test_signup_case_insensitive_duplicate_username_rejected(self):
        # Behavior preservation: Django's inherited UserCreationForm.clean_username
        # rejected usernames differing only in case (username__iexact). UI-H.6 must
        # keep that semantics, only localizing the message.
        User.objects.create_user(username="Mixed_Case", password="StrongPass123!")
        self._set_language("zh")

        response = self.client.post(
            reverse("signup"),
            {
                "username": "mixed_case",
                "email": "",
                "requested_unit": "",
                "password1": "StrongPass123!",
                "password2": "StrongPass123!",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "这个用户名已被使用")
        self.assertEqual(User.objects.filter(username="mixed_case").count(), 0)

    def test_signup_english_case_insensitive_duplicate_username_rejected(self):
        User.objects.create_user(username="Casey", password="StrongPass123!")
        self._set_language("en")

        response = self.client.post(
            reverse("signup"),
            {
                "username": "casey",
                "email": "",
                "requested_unit": "",
                "password1": "StrongPass123!",
                "password2": "StrongPass123!",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "already taken")
        self.assertEqual(User.objects.filter(username="casey").count(), 0)


class StructureRoleScopeFoundationTests(TestCase):
    """CS-CORE.2D-A: ChurchRoleAssignment.structure_unit field + scope helpers.

    Foundation only. Adding the field and the resolution helpers does not change
    any progress-permission runtime behavior, and ordinary
    ChurchStructureMembership is never used as a role-scope source here.
    """

    def setUp(self):
        self.user = User.objects.create_user(username="role_scope_user")
        self.district_unit = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_DISTRICT,
            code="DIST-A",
            name="District A",
        )
        self.group_unit = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="SG-A",
            name="Small Group A",
            parent=self.district_unit,
        )
        self.sibling_group_unit = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="SG-B",
            name="Small Group B",
            parent=self.district_unit,
        )
        self.unrelated_unit = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="SG-Z",
            name="Small Group Z",
        )

    def test_scoped_assignment_with_structure_unit(self):
        assignment = ChurchRoleAssignment.objects.create(
            user=self.user,
            role=ChurchRoleAssignment.ROLE_GROUP_LEADER,
            scope_type=ChurchRoleAssignment.SCOPE_SMALL_GROUP,
            structure_unit=self.group_unit,
        )

        assignment.refresh_from_db()
        self.assertEqual(assignment.structure_unit_id, self.group_unit.id)

    def test_scoped_duplicate_identity_uses_structure_unit(self):
        ChurchRoleAssignment.objects.create(
            user=self.user,
            role=ChurchRoleAssignment.ROLE_GROUP_LEADER,
            scope_type=ChurchRoleAssignment.SCOPE_SMALL_GROUP,
            structure_unit=self.group_unit,
        )
        duplicate = ChurchRoleAssignment(
            user=self.user,
            role=ChurchRoleAssignment.ROLE_GROUP_LEADER,
            scope_type=ChurchRoleAssignment.SCOPE_SMALL_GROUP,
            structure_unit=self.group_unit,
        )

        with self.assertRaises(ValidationError) as context:
            duplicate.full_clean()

        self.assertIn("role", context.exception.message_dict)

    def test_global_duplicate_identity_remains_global(self):
        ChurchRoleAssignment.objects.create(
            user=self.user,
            role=ChurchRoleAssignment.ROLE_PASTOR,
            scope_type=ChurchRoleAssignment.SCOPE_GLOBAL,
        )
        duplicate = ChurchRoleAssignment(
            user=self.user,
            role=ChurchRoleAssignment.ROLE_PASTOR,
            scope_type=ChurchRoleAssignment.SCOPE_GLOBAL,
        )

        with self.assertRaises(ValidationError) as context:
            duplicate.full_clean()

        self.assertIn("role", context.exception.message_dict)

    def test_assignment_can_be_created_with_structure_unit(self):
        assignment = ChurchRoleAssignment.objects.create(
            user=self.user,
            role=ChurchRoleAssignment.ROLE_GROUP_LEADER,
            scope_type=ChurchRoleAssignment.SCOPE_SMALL_GROUP,
            structure_unit=self.group_unit,
        )

        assignment.refresh_from_db()
        self.assertEqual(assignment.structure_unit_id, self.group_unit.id)

    def test_resolver_returns_explicit_structure_unit(self):
        assignment = ChurchRoleAssignment.objects.create(
            user=self.user,
            role=ChurchRoleAssignment.ROLE_GROUP_LEADER,
            scope_type=ChurchRoleAssignment.SCOPE_SMALL_GROUP,
            structure_unit=self.group_unit,
        )

        self.assertEqual(
            get_role_assignment_structure_unit(assignment), self.group_unit
        )

    def test_resolver_returns_none_for_scoped_row_missing_structure_unit(self):
        # ROLE-FIELD-RETIRE.1A: scoped runtime access is explicit-structure_unit
        # only. A scoped row with no structure_unit (which normal validation would
        # reject) fails closed at resolution time.
        assignment = create_role_assignment_without_validation(
            user=self.user,
            role=ChurchRoleAssignment.ROLE_GROUP_LEADER,
            scope_type=ChurchRoleAssignment.SCOPE_SMALL_GROUP,
        )

        self.assertIsNone(get_role_assignment_structure_unit(assignment))

    def test_resolver_returns_none_for_global_scope(self):
        assignment = ChurchRoleAssignment.objects.create(
            user=self.user,
            role=ChurchRoleAssignment.ROLE_PASTOR,
            scope_type=ChurchRoleAssignment.SCOPE_GLOBAL,
        )

        self.assertIsNone(get_role_assignment_structure_unit(assignment))

    def test_scope_includes_same_unit(self):
        assignment = ChurchRoleAssignment.objects.create(
            user=self.user,
            role=ChurchRoleAssignment.ROLE_GROUP_LEADER,
            scope_type=ChurchRoleAssignment.SCOPE_SMALL_GROUP,
            structure_unit=self.group_unit,
        )

        self.assertTrue(
            assignment_scope_includes_unit(assignment, self.group_unit)
        )

    def test_scope_includes_descendant_small_group_under_district_unit(self):
        assignment = ChurchRoleAssignment.objects.create(
            user=self.user,
            role=ChurchRoleAssignment.ROLE_DISTRICT_LEADER,
            scope_type=ChurchRoleAssignment.SCOPE_DISTRICT,
            structure_unit=self.district_unit,
        )

        # group_unit is a child of district_unit, so a district-like scope covers it.
        self.assertTrue(
            assignment_scope_includes_unit(assignment, self.group_unit)
        )

    def test_scope_fails_closed_for_scoped_district_missing_structure_unit(self):
        # ROLE-FIELD-RETIRE.1A: a scoped district row with no structure_unit no
        # longer covers its descendant units at runtime.
        assignment = create_role_assignment_without_validation(
            user=self.user,
            role=ChurchRoleAssignment.ROLE_DISTRICT_LEADER,
            scope_type=ChurchRoleAssignment.SCOPE_DISTRICT,
        )

        self.assertIsNone(get_role_assignment_structure_unit(assignment))
        self.assertFalse(
            assignment_scope_includes_unit(assignment, self.group_unit)
        )
        self.assertFalse(
            assignment_scope_includes_unit(assignment, self.district_unit)
        )

    def test_scope_excludes_sibling_and_unrelated_units(self):
        assignment = ChurchRoleAssignment.objects.create(
            user=self.user,
            role=ChurchRoleAssignment.ROLE_GROUP_LEADER,
            scope_type=ChurchRoleAssignment.SCOPE_SMALL_GROUP,
            structure_unit=self.group_unit,
        )

        # A small-group-unit scope does not cover a sibling or unrelated unit,
        # and never reaches up to its own parent district.
        self.assertFalse(
            assignment_scope_includes_unit(assignment, self.sibling_group_unit)
        )
        self.assertFalse(
            assignment_scope_includes_unit(assignment, self.unrelated_unit)
        )
        self.assertFalse(
            assignment_scope_includes_unit(assignment, self.district_unit)
        )

    def test_scope_fails_closed_on_missing_unit_or_unresolved_scope(self):
        unresolved = create_role_assignment_without_validation(
            user=self.user,
            role=ChurchRoleAssignment.ROLE_GROUP_LEADER,
            scope_type=ChurchRoleAssignment.SCOPE_SMALL_GROUP,
        )

        # Missing target unit fails closed.
        self.assertFalse(
            assignment_scope_includes_unit(unresolved, None)
        )
        # Unresolved assignment scope (no explicit structure_unit) fails closed.
        self.assertFalse(
            assignment_scope_includes_unit(unresolved, self.group_unit)
        )

    def test_helpers_do_not_use_membership_for_scope(self):
        # An ordinary active primary membership under group_unit must not make a
        # global-scope (or any) assignment resolve to that unit.
        ChurchStructureMembership.objects.create(
            user=self.user,
            unit=self.group_unit,
            status=ChurchStructureMembership.STATUS_ACTIVE,
            is_primary=True,
            start_date=timezone.localdate(),
        )
        global_assignment = ChurchRoleAssignment.objects.create(
            user=self.user,
            role=ChurchRoleAssignment.ROLE_PASTOR,
            scope_type=ChurchRoleAssignment.SCOPE_GLOBAL,
        )

        self.assertIsNone(get_role_assignment_structure_unit(global_assignment))
        self.assertFalse(
            assignment_scope_includes_unit(global_assignment, self.group_unit)
        )

    def test_progress_permission_uses_structure_aware_role_scope(self):
        # ROLE-FIELD-RETIRE.1A: progress access requires an explicit
        # structure_unit. A scoped role with structure_unit set grants access to
        # the canonical small-group unit; a scoped role with no structure_unit
        # fails closed.

        explicit_user = User.objects.create_user(username="explicit_perm_user")
        ChurchRoleAssignment.objects.create(
            user=explicit_user,
            role=ChurchRoleAssignment.ROLE_GROUP_LEADER,
            scope_type=ChurchRoleAssignment.SCOPE_SMALL_GROUP,
            structure_unit=self.group_unit,
        )
        self.assertEqual(
            list(get_accessible_progress_groups(explicit_user)), [self.group_unit]
        )

        missing_unit_user = User.objects.create_user(username="missing_unit_perm_user")
        create_role_assignment_without_validation(
            user=missing_unit_user,
            role=ChurchRoleAssignment.ROLE_GROUP_LEADER,
            scope_type=ChurchRoleAssignment.SCOPE_SMALL_GROUP,
        )
        self.assertEqual(
            list(get_accessible_progress_groups(missing_unit_user)), []
        )


class StructureRoleScopeAuditCommandTests(TestCase):
    """CS-CORE.2D-A read-only role-scope readiness audit command tests."""

    def setUp(self):
        self.user = User.objects.create_user(username="audit_role_user")

    def run_command(self, *args):
        output = StringIO()
        call_command("audit_structure_role_scopes", *args, stdout=output)
        return output.getvalue()

    def create_unit(self, code, *, unit_type=None, is_active=True, parent=None):
        return ChurchStructureUnit.objects.create(
            unit_type=unit_type or ChurchStructureUnit.UNIT_SMALL_GROUP,
            code=code,
            name=code,
            is_active=is_active,
            parent=parent,
        )

    def assert_summary_count(self, output, key, count):
        self.assertIn(f"{key}: {count}", output)

    def create_assignment(self, **kwargs):
        kwargs.setdefault("user", self.user)
        return create_role_assignment_without_validation(**kwargs)

    def test_command_is_read_only(self):
        unit = self.create_unit("AUDIT-RO")
        self.create_assignment(
            role=ChurchRoleAssignment.ROLE_GROUP_LEADER,
            scope_type=ChurchRoleAssignment.SCOPE_SMALL_GROUP,
            structure_unit=unit,
        )
        before = {
            "assignments": ChurchRoleAssignment.objects.count(),
            "units": ChurchStructureUnit.objects.count(),
        }

        with CaptureQueriesContext(connection) as queries:
            output = self.run_command("--verbose")

        write_sql = [
            query["sql"]
            for query in queries
            if query["sql"].lstrip().upper().startswith(
                ("INSERT", "UPDATE", "DELETE")
            )
        ]
        self.assertEqual(write_sql, [])
        self.assertIn("Audit only:", output)
        self.assertEqual(
            before,
            {
                "assignments": ChurchRoleAssignment.objects.count(),
                "units": ChurchStructureUnit.objects.count(),
            },
        )

    def test_explicit_structure_unit_scope_is_ready(self):
        unit = self.create_unit("AUDIT-MAP-SG")
        self.create_assignment(
            role=ChurchRoleAssignment.ROLE_GROUP_LEADER,
            scope_type=ChurchRoleAssignment.SCOPE_SMALL_GROUP,
            structure_unit=unit,
        )

        output = self.run_command()

        self.assert_summary_count(output, "assignments_checked", 1)
        self.assert_summary_count(output, "assignments_with_structure_unit", 1)
        self.assert_summary_count(output, "assignments_missing_structure_unit", 0)
        self.assert_summary_count(output, "assignments_ready_for_structure_scope", 1)
        self.assert_summary_count(
            output, "assignments_not_ready_for_structure_scope", 0
        )

    def test_scoped_assignment_missing_structure_unit_is_not_ready(self):
        # A scoped row with no structure_unit (which normal validation rejects)
        # fails closed in the audit.
        self.create_assignment(
            role=ChurchRoleAssignment.ROLE_GROUP_LEADER,
            scope_type=ChurchRoleAssignment.SCOPE_SMALL_GROUP,
        )

        output = self.run_command("--verbose")

        self.assert_summary_count(output, "assignments_missing_structure_unit", 1)
        self.assert_summary_count(
            output, "assignments_not_ready_for_structure_scope", 1
        )
        self.assertIn(
            "reason=assignments_not_ready_for_structure_scope", output
        )

    def test_global_assignment_counted_and_ready(self):
        ChurchRoleAssignment.objects.create(
            user=self.user,
            role=ChurchRoleAssignment.ROLE_PASTOR,
            scope_type=ChurchRoleAssignment.SCOPE_GLOBAL,
        )

        output = self.run_command()

        self.assert_summary_count(output, "global_assignments", 1)
        self.assert_summary_count(output, "assignments_missing_structure_unit", 1)
        self.assert_summary_count(output, "assignments_ready_for_structure_scope", 1)

    def test_inactive_structure_unit_counted_and_not_ready(self):
        inactive_unit = self.create_unit("AUDIT-INACT", is_active=False)
        self.create_assignment(
            role=ChurchRoleAssignment.ROLE_GROUP_LEADER,
            scope_type=ChurchRoleAssignment.SCOPE_SMALL_GROUP,
            structure_unit=inactive_unit,
        )

        output = self.run_command("--verbose")

        self.assert_summary_count(output, "structure_unit_inactive", 1)
        self.assert_summary_count(
            output, "assignments_not_ready_for_structure_scope", 1
        )
        self.assertIn("reason=structure_unit_inactive", output)

    def test_wrong_type_structure_unit_for_small_group_scope(self):
        fellowship_unit = self.create_unit(
            "AUDIT-WT-FEL", unit_type=ChurchStructureUnit.UNIT_FELLOWSHIP
        )
        self.create_assignment(
            role=ChurchRoleAssignment.ROLE_GROUP_LEADER,
            scope_type=ChurchRoleAssignment.SCOPE_SMALL_GROUP,
            structure_unit=fellowship_unit,
        )

        output = self.run_command("--verbose")

        self.assert_summary_count(output, "structure_unit_wrong_type_for_scope", 1)
        self.assert_summary_count(
            output, "assignments_not_ready_for_structure_scope", 1
        )
        self.assertIn("reason=structure_unit_wrong_type_for_scope", output)

    def test_limit_caps_verbose_rows(self):
        for index in range(3):
            user = User.objects.create_user(username=f"audit_limit_user_{index}")
            self.create_assignment(
                user=user,
                role=ChurchRoleAssignment.ROLE_GROUP_LEADER,
                scope_type=ChurchRoleAssignment.SCOPE_SMALL_GROUP,
            )

        output = self.run_command("--verbose", "--limit", "1")

        self.assert_summary_count(
            output, "assignments_not_ready_for_structure_scope", 3
        )
        self.assertIn("(stopped at --limit 1)", output)


class GroupProgressPermissionSourceSwitchTests(TestCase):
    """CS-CORE.2D-B: group-progress permission/access list is structure-aware.

    ``get_accessible_progress_groups`` / ``can_view_group_progress_for`` resolve
    scoped role access through ``ChurchRoleAssignment.structure_unit`` only (the
    legacy district/small_group runtime fallback was retired in ROLE-RETIRE.1B) plus
    its descendants, and the ordinary own-group rule comes from the single active
    primary ``ChurchStructureMembership`` small-group unit. ``Profile.small_group``
    no longer grants any progress access, and ordinary membership grants only its
    own canonical small-group unit (never a broad grant).
    """

    def setUp(self):
        # district_unit
        #   |- group_unit
        #   |- sibling_unit
        # other_district_unit
        #   |- other_group_unit
        self.district_unit = self.create_unit(
            "PERM2DB-DIST", unit_type=ChurchStructureUnit.UNIT_DISTRICT
        )
        self.other_district_unit = self.create_unit(
            "PERM2DB-OTHER-DIST", unit_type=ChurchStructureUnit.UNIT_DISTRICT
        )
        self.group_unit = self.create_unit("PERM2DB-SG", parent=self.district_unit)
        self.sibling_unit = self.create_unit(
            "PERM2DB-SIB", parent=self.district_unit
        )
        self.other_group_unit = self.create_unit(
            "PERM2DB-OTHER-SG", parent=self.other_district_unit
        )

    def create_unit(self, code, *, unit_type=None, parent=None):
        return ChurchStructureUnit.objects.create(
            unit_type=unit_type or ChurchStructureUnit.UNIT_SMALL_GROUP,
            code=code,
            name=code,
            parent=parent,
        )

    def create_user(self, username, *, group=None):
        user = User.objects.create_user(username=username, password="TestPass123!")
        return user

    def create_membership(self, user, unit):
        return ChurchStructureMembership.objects.create(
            user=user,
            unit=unit,
            status=ChurchStructureMembership.STATUS_ACTIVE,
            is_primary=True,
            start_date=timezone.localdate(),
        )

    def accessible_ids(self, user):
        return set(get_accessible_progress_groups(user).values_list("id", flat=True))

    # --- ordinary own-group via membership-core ---------------------------------

    def test_membership_only_user_gets_own_group_even_without_profile(self):
        user = self.create_user("perm2db_membership_only")
        self.create_membership(user, self.group_unit)

        self.assertEqual(
            get_user_membership_progress_own_group(user), self.group_unit
        )
        self.assertEqual(self.accessible_ids(user), {self.group_unit.id})
        self.assertTrue(can_view_group_progress_for(user, self.group_unit))

    def test_profile_only_user_gets_no_own_group_access(self):
        user = self.create_user("perm2db_profile_only")

        self.assertIsNone(get_user_membership_progress_own_group(user))
        self.assertEqual(self.accessible_ids(user), set())
        self.assertFalse(can_view_group_progress_for(user, self.group_unit))

    def test_multiple_active_primary_memberships_fail_closed(self):
        user = self.create_user("perm2db_multi")
        today = timezone.localdate()
        ChurchStructureMembership.objects.bulk_create(
            [
                ChurchStructureMembership(
                    user=user,
                    unit=self.group_unit,
                    status=ChurchStructureMembership.STATUS_ACTIVE,
                    is_primary=True,
                    start_date=today,
                ),
                ChurchStructureMembership(
                    user=user,
                    unit=self.other_group_unit,
                    status=ChurchStructureMembership.STATUS_ACTIVE,
                    is_primary=True,
                    start_date=today,
                ),
            ]
        )

        self.assertIsNone(get_user_membership_progress_own_group(user))
        self.assertEqual(self.accessible_ids(user), set())

    def test_unmapped_or_wrong_type_membership_unit_fails_closed(self):
        # A canonical small-group unit no longer needs a legacy SmallGroup row.
        unmapped_user = self.create_user("perm2db_unmapped")
        unmapped_unit = self.create_unit("PERM2DB-UNMAPPED")
        self.create_membership(unmapped_user, unmapped_unit)
        self.assertEqual(
            get_user_membership_progress_own_group(unmapped_user), unmapped_unit
        )
        self.assertEqual(self.accessible_ids(unmapped_user), {unmapped_unit.id})

        # Wrong-type unit (fellowship, not small_group).
        wrong_type_user = self.create_user("perm2db_wrong_type")
        fellowship_unit = self.create_unit(
            "PERM2DB-FEL", unit_type=ChurchStructureUnit.UNIT_FELLOWSHIP
        )
        self.create_membership(wrong_type_user, fellowship_unit)
        self.assertIsNone(get_user_membership_progress_own_group(wrong_type_user))
        self.assertEqual(self.accessible_ids(wrong_type_user), set())

    def test_membership_unit_without_legacy_mapping_still_grants_own_group(self):
        user = self.create_user("perm2db_ambiguous_map")
        shared_unit = self.create_unit("PERM2DB-SHARED", parent=self.district_unit)
        self.create_membership(user, shared_unit)

        self.assertEqual(get_user_membership_progress_own_group(user), shared_unit)
        self.assertEqual(self.accessible_ids(user), {shared_unit.id})

    def test_ordinary_membership_grants_only_own_group_not_siblings(self):
        user = self.create_user("perm2db_own_only")
        self.create_membership(user, self.group_unit)

        self.assertEqual(self.accessible_ids(user), {self.group_unit.id})
        self.assertTrue(can_view_group_progress_for(user, self.group_unit))
        self.assertFalse(can_view_group_progress_for(user, self.sibling_unit))
        self.assertFalse(can_view_group_progress_for(user, self.other_group_unit))

    # --- structure-aware role scopes --------------------------------------------

    def test_group_leader_structure_unit_scope_grants_that_group(self):
        leader = self.create_user("perm2db_group_leader")
        ChurchRoleAssignment.objects.create(
            user=leader,
            role=ChurchRoleAssignment.ROLE_GROUP_LEADER,
            scope_type=ChurchRoleAssignment.SCOPE_SMALL_GROUP,
            structure_unit=self.group_unit,
        )

        self.assertEqual(self.accessible_ids(leader), {self.group_unit.id})
        self.assertFalse(can_view_group_progress_for(leader, self.sibling_unit))

    def test_district_leader_scope_includes_descendant_groups_only(self):
        leader = self.create_user("perm2db_district_leader")
        ChurchRoleAssignment.objects.create(
            user=leader,
            role=ChurchRoleAssignment.ROLE_DISTRICT_LEADER,
            scope_type=ChurchRoleAssignment.SCOPE_DISTRICT,
            structure_unit=self.district_unit,
        )

        # district_unit covers its descendant small-group units (group + sibling),
        # but not a group under another district.
        self.assertEqual(
            self.accessible_ids(leader),
            {self.group_unit.id, self.sibling_unit.id},
        )
        self.assertTrue(can_view_group_progress_for(leader, self.group_unit))
        self.assertTrue(can_view_group_progress_for(leader, self.sibling_unit))
        self.assertFalse(can_view_group_progress_for(leader, self.other_group_unit))

    def test_scoped_group_role_missing_structure_unit_fails_closed(self):
        # ROLE-FIELD-RETIRE.1A: a scoped group-leader role with no structure_unit
        # (which normal validation rejects) no longer grants progress access.
        leader = self.create_user("perm2db_missing_unit_group_leader")
        create_role_assignment_without_validation(
            user=leader,
            role=ChurchRoleAssignment.ROLE_GROUP_LEADER,
            scope_type=ChurchRoleAssignment.SCOPE_SMALL_GROUP,
        )

        self.assertEqual(self.accessible_ids(leader), set())
        self.assertFalse(can_view_group_progress_for(leader, self.group_unit))

    def test_scoped_district_role_missing_structure_unit_fails_closed(self):
        # ROLE-FIELD-RETIRE.1A: a scoped district-leader role with no
        # structure_unit no longer grants progress access to descendant groups.
        leader = self.create_user("perm2db_missing_unit_district_leader")
        create_role_assignment_without_validation(
            user=leader,
            role=ChurchRoleAssignment.ROLE_DISTRICT_LEADER,
            scope_type=ChurchRoleAssignment.SCOPE_DISTRICT,
        )

        self.assertEqual(self.accessible_ids(leader), set())
        self.assertFalse(can_view_group_progress_for(leader, self.group_unit))
        self.assertFalse(can_view_group_progress_for(leader, self.sibling_unit))

    def test_permission_checks_do_not_mutate_role_assignments(self):
        # Read-only invariant: evaluating progress permissions never writes
        # structure_unit or any other role-assignment field.
        leader = self.create_user("perm2db_readonly_leader")
        assignment = create_role_assignment_without_validation(
            user=leader,
            role=ChurchRoleAssignment.ROLE_GROUP_LEADER,
            scope_type=ChurchRoleAssignment.SCOPE_SMALL_GROUP,
        )

        with CaptureQueriesContext(connection) as queries:
            self.accessible_ids(leader)
            can_view_group_progress_for(leader, self.group_unit)

        write_sql = [
            query["sql"]
            for query in queries
            if query["sql"].lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE"))
        ]
        self.assertEqual(write_sql, [])
        assignment.refresh_from_db()
        self.assertIsNone(assignment.structure_unit_id)

    # --- staff / global + agreement ---------------------------------------------

    def test_staff_superuser_and_global_capability_see_all_active_groups(self):
        staff = User.objects.create_user(
            username="perm2db_staff", password="TestPass123!", is_staff=True
        )
        superuser = User.objects.create_superuser(
            username="perm2db_super", password="TestPass123!"
        )
        pastor = self.create_user("perm2db_pastor")
        ChurchRoleAssignment.objects.create(
            user=pastor,
            role=ChurchRoleAssignment.ROLE_PASTOR,
            scope_type=ChurchRoleAssignment.SCOPE_GLOBAL,
        )

        all_active = {
            self.group_unit.id,
            self.sibling_unit.id,
            self.other_group_unit.id,
        }
        for viewer in (staff, superuser, pastor):
            self.assertEqual(self.accessible_ids(viewer), all_active)
            self.assertTrue(can_view_group_progress_for(viewer, self.other_group_unit))

    def test_can_view_agrees_with_accessible_list_for_allowed_and_denied(self):
        leader = self.create_user("perm2db_agree")
        ChurchRoleAssignment.objects.create(
            user=leader,
            role=ChurchRoleAssignment.ROLE_GROUP_LEADER,
            scope_type=ChurchRoleAssignment.SCOPE_SMALL_GROUP,
            structure_unit=self.group_unit,
        )

        accessible = self.accessible_ids(leader)
        for candidate in (self.group_unit, self.sibling_unit, self.other_group_unit):
            self.assertEqual(
                can_view_group_progress_for(leader, candidate),
                candidate.id in accessible,
            )



class MyUnitsReadOnlyTests(TestCase):
    """UNIT-LEAD-MANAGE.1B read-only My Units entry.

    Management is granted only by staff/superuser or an active `lead` coworker
    assignment on the unit or an ancestor. Membership/belonging, audience
    visibility, and non-lead coworker roles never grant management. This surface
    is read-only and exposes no add/end coworker actions.
    """

    def setUp(self):
        self.today = timezone.localdate()
        self.url = reverse("my_units")

        self.lead_role = ChurchStructureUnitRoleType.objects.create(
            code=ChurchStructureUnitRoleType.CODE_LEAD,
            name="负责人",
            name_en="Lead",
        )
        self.edify_role = ChurchStructureUnitRoleType.objects.create(
            code=ChurchStructureUnitRoleType.CODE_EDIFY,
            name="带查经同工",
            name_en="Edify",
        )

        # A district subtree (district -> group -> nested), plus a sibling branch.
        self.district = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_DISTRICT,
            code="MU-DISTRICT",
            name="负责区",
            name_en="Lead District",
        )
        self.group = ChurchStructureUnit.objects.create(
            parent=self.district,
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="MU-GROUP",
            name="小组A",
            name_en="Group A",
        )
        self.nested = ChurchStructureUnit.objects.create(
            parent=self.group,
            unit_type=ChurchStructureUnit.UNIT_CUSTOM,
            code="MU-NESTED",
            name="子单元",
            name_en="Nested",
        )
        self.sibling = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="MU-SIBLING",
            name="无关组",
            name_en="Unrelated Group",
        )

    def _lead(self, user, unit, **kwargs):
        return ChurchStructureUnitRoleAssignment.objects.create(
            unit=unit,
            role_type=self.lead_role,
            user=user,
            **kwargs,
        )

    # --- helper: get_manageable_structure_units --------------------------------

    def test_staff_sees_all_active_units(self):
        staff = User.objects.create_user(username="mu_staff", is_staff=True)
        units = get_manageable_structure_units(staff)
        self.assertEqual(
            {u.id for u in units},
            {self.district.id, self.group.id, self.nested.id, self.sibling.id},
        )

    def test_superuser_sees_all_active_units(self):
        superuser = User.objects.create_superuser(
            username="mu_super", email="mu_super@example.com", password="x"
        )
        units = get_manageable_structure_units(superuser)
        self.assertIn(self.sibling.id, {u.id for u in units})

    def test_staff_does_not_see_inactive_units(self):
        staff = User.objects.create_user(username="mu_staff_inactive", is_staff=True)
        self.sibling.is_active = False
        self.sibling.save()
        units = get_manageable_structure_units(staff)
        self.assertNotIn(self.sibling.id, {u.id for u in units})

    def test_lead_on_unit_sees_that_unit(self):
        user = User.objects.create_user(username="mu_group_lead")
        self._lead(user, self.group)
        ids = {u.id for u in get_manageable_structure_units(user)}
        self.assertIn(self.group.id, ids)

    def test_lead_on_parent_sees_descendant_units(self):
        user = User.objects.create_user(username="mu_district_lead")
        self._lead(user, self.district)
        ids = {u.id for u in get_manageable_structure_units(user)}
        self.assertEqual(ids, {self.district.id, self.group.id, self.nested.id})

    def test_lead_on_one_branch_does_not_see_sibling_branch(self):
        user = User.objects.create_user(username="mu_branch_lead")
        self._lead(user, self.group)
        ids = {u.id for u in get_manageable_structure_units(user)}
        self.assertNotIn(self.sibling.id, ids)
        self.assertNotIn(self.district.id, ids)

    def test_inactive_lead_assignment_does_not_grant_visibility(self):
        user = User.objects.create_user(username="mu_inactive_lead")
        self._lead(user, self.group, is_active=False)
        self.assertEqual(get_manageable_structure_units(user), [])
        self.assertFalse(can_manage_unit_coworkers(user, self.group))

    def test_expired_lead_assignment_does_not_grant_visibility(self):
        user = User.objects.create_user(username="mu_expired_lead")
        self._lead(
            user,
            self.group,
            start_date=self.today - timedelta(days=30),
            end_date=self.today - timedelta(days=1),
        )
        self.assertEqual(get_manageable_structure_units(user), [])
        self.assertFalse(can_manage_unit_coworkers(user, self.group))

    def test_not_yet_started_lead_assignment_does_not_grant_visibility(self):
        user = User.objects.create_user(username="mu_future_lead")
        self._lead(user, self.group, start_date=self.today + timedelta(days=7))
        self.assertEqual(get_manageable_structure_units(user), [])
        self.assertFalse(can_manage_unit_coworkers(user, self.group))

    def test_non_lead_coworker_assignment_does_not_grant_visibility(self):
        user = User.objects.create_user(username="mu_edify")
        ChurchStructureUnitRoleAssignment.objects.create(
            unit=self.group,
            role_type=self.edify_role,
            user=user,
        )
        self.assertEqual(get_manageable_structure_units(user), [])
        self.assertFalse(can_manage_unit_coworkers(user, self.group))

    def test_membership_alone_does_not_grant_visibility(self):
        user = User.objects.create_user(username="mu_member")
        ChurchStructureMembership.objects.create(
            user=user,
            unit=self.group,
            status=ChurchStructureMembership.STATUS_ACTIVE,
            is_primary=True,
            start_date=self.today,
        )
        self.assertEqual(get_manageable_structure_units(user), [])
        self.assertFalse(can_manage_unit_coworkers(user, self.group))

    def test_lead_on_inactive_unit_is_not_listed(self):
        user = User.objects.create_user(username="mu_inactive_unit_lead")
        self._lead(user, self.group)
        self.group.is_active = False
        self.group.save()
        ids = {u.id for u in get_manageable_structure_units(user)}
        self.assertNotIn(self.group.id, ids)

    def test_active_lead_on_inactive_unit_does_not_show_nav(self):
        user = User.objects.create_user(username="mu_inactive_unit_nav")
        self._lead(user, self.group)
        self.group.is_active = False
        self.group.save()
        # The only active lead assignment is on an inactive unit, so there is
        # nothing manageable and the nav link must stay hidden.
        self.assertEqual(get_user_active_lead_units(user), [])
        self.assertFalse(should_show_my_units_nav(user))

    def test_active_lead_on_inactive_unit_cannot_manage_it(self):
        user = User.objects.create_user(username="mu_inactive_unit_manage")
        self._lead(user, self.group)
        self.group.is_active = False
        self.group.save()
        self.assertFalse(can_manage_unit_coworkers(user, self.group))

    def test_staff_listing_only_lists_active_units(self):
        staff = User.objects.create_user(
            username="mu_staff_active_only", is_staff=True
        )
        self.sibling.is_active = False
        self.sibling.save()
        ids = {u.id for u in get_manageable_structure_units(staff)}
        self.assertEqual(ids, {self.district.id, self.group.id, self.nested.id})
        self.assertNotIn(self.sibling.id, ids)

    # --- helper: can_manage_unit_coworkers -------------------------------------

    def test_can_manage_ancestor_or_self_but_not_sibling(self):
        user = User.objects.create_user(username="mu_can_manage")
        self._lead(user, self.district)
        self.assertTrue(can_manage_unit_coworkers(user, self.district))
        self.assertTrue(can_manage_unit_coworkers(user, self.group))
        self.assertTrue(can_manage_unit_coworkers(user, self.nested))
        self.assertFalse(can_manage_unit_coworkers(user, self.sibling))

    def test_anonymous_cannot_manage(self):
        self.assertFalse(can_manage_unit_coworkers(AnonymousUser(), self.group))
        self.assertEqual(get_manageable_structure_units(AnonymousUser()), [])

    # --- nav guard -------------------------------------------------------------

    def test_nav_flag_true_for_lead_and_staff_false_for_member(self):
        lead = User.objects.create_user(username="mu_nav_lead")
        self._lead(lead, self.group)
        staff = User.objects.create_user(username="mu_nav_staff", is_staff=True)
        member = User.objects.create_user(username="mu_nav_member")
        ChurchStructureMembership.objects.create(
            user=member,
            unit=self.group,
            status=ChurchStructureMembership.STATUS_ACTIVE,
            is_primary=True,
            start_date=self.today,
        )
        self.assertTrue(should_show_my_units_nav(lead))
        self.assertTrue(should_show_my_units_nav(staff))
        self.assertFalse(should_show_my_units_nav(member))

    # --- view ------------------------------------------------------------------

    def test_view_requires_login(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response["Location"])

    def test_staff_view_lists_active_units(self):
        User.objects.create_user(
            username="mu_view_staff", password="pw", is_staff=True
        )
        self.client.login(username="mu_view_staff", password="pw")
        response = self.client.get(self.url + "?lang=en")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Lead District")
        self.assertContains(response, "Unrelated Group")

    def test_lead_view_shows_led_unit_and_not_sibling(self):
        user = User.objects.create_user(username="mu_view_lead", password="pw")
        self._lead(user, self.group)
        self.client.login(username="mu_view_lead", password="pw")
        response = self.client.get(self.url + "?lang=en")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Group A")
        self.assertNotContains(response, "Unrelated Group")

    def test_empty_state_for_user_with_no_manageable_units(self):
        User.objects.create_user(username="mu_view_empty", password="pw")
        self.client.login(username="mu_view_empty", password="pw")
        response = self.client.get(self.url + "?lang=en")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "You do not currently lead any units.")

    def test_view_shows_missing_required_role_readiness(self):
        profile = ChurchStructureUnitRoleProfile.objects.create(
            code=ChurchStructureUnitRoleProfile.CODE_SMALL_GROUP_UNIT,
            name="小组型单元",
            name_en="Small-Group Unit",
        )
        ChurchStructureUnitRoleRequirement.objects.create(
            profile=profile,
            role_type=self.edify_role,
            is_required=True,
        )
        self.group.role_profile = profile
        self.group.save()
        user = User.objects.create_user(username="mu_view_missing", password="pw")
        self._lead(user, self.group)
        self.client.login(username="mu_view_missing", password="pw")
        response = self.client.get(self.url + "?lang=en")
        self.assertEqual(response.status_code, 200)
        # MYUNITS-UX.1A: the list page now shows compact signals (a missing
        # required count + a "Needs attention" badge), not the full per-role
        # roster. The detail page is where individual role labels are reviewed.
        self.assertContains(response, "Missing required")
        self.assertContains(response, "Needs attention")
        self.assertNotContains(response, "Edify")

    def test_view_shows_no_role_profile_note(self):
        user = User.objects.create_user(username="mu_view_noprofile", password="pw")
        self._lead(user, self.group)
        self.client.login(username="mu_view_noprofile", password="pw")
        response = self.client.get(self.url + "?lang=en")
        # MYUNITS-UX.1A: compact "No role profile" signal on the list page.
        self.assertContains(response, "No role profile")

    def test_view_is_read_only_no_post_actions(self):
        user = User.objects.create_user(username="mu_view_readonly", password="pw")
        self._lead(user, self.group)
        # An active coworker to confirm the roster renders without an end action.
        other = User.objects.create_user(username="mu_view_roster_member")
        ChurchStructureUnitRoleAssignment.objects.create(
            unit=self.group,
            role_type=self.edify_role,
            user=other,
        )
        self.client.login(username="mu_view_readonly", password="pw")
        get_response = self.client.get(self.url + "?lang=en")
        self.assertEqual(get_response.status_code, 200)
        # No add/end coworker form actions are exposed on this surface.
        self.assertNotContains(get_response, "end_structure_unit_coworker_assignment")
        self.assertNotContains(get_response, "add_structure_unit_coworker_assignment")
        # No coworker management form is rendered in the page content area.
        self.assertNotContains(get_response, "structure-membership-form")


class MyUnitDelegatedCoworkerEditTests(TestCase):
    """UNIT-LEAD-MANAGE.1C delegated coworker add/end on the My Units surface.

    Editing is gated only by ``can_manage_unit_coworkers`` (active ``lead``
    ancestor-or-self, or staff/superuser). Edits create/end only
    ``ChurchStructureUnitRoleAssignment`` rows; never membership, capabilities,
    serving, or meeting roles. Non-staff leads are pinned to local candidates and
    cannot widen the picker to all active users.
    """

    def setUp(self):
        self.today = timezone.localdate()

        self.lead_role = ChurchStructureUnitRoleType.objects.create(
            code=ChurchStructureUnitRoleType.CODE_LEAD,
            name="负责人",
            name_en="Lead",
        )
        self.edify_role = ChurchStructureUnitRoleType.objects.create(
            code=ChurchStructureUnitRoleType.CODE_EDIFY,
            name="带查经同工",
            name_en="Edify",
        )

        self.district = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_DISTRICT,
            code="MUD-DISTRICT",
            name="负责区",
            name_en="Lead District",
        )
        self.group = ChurchStructureUnit.objects.create(
            parent=self.district,
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="MUD-GROUP",
            name="小组A",
            name_en="Group A",
        )
        self.nested = ChurchStructureUnit.objects.create(
            parent=self.group,
            unit_type=ChurchStructureUnit.UNIT_CUSTOM,
            code="MUD-NESTED",
            name="子单元",
            name_en="Nested",
        )
        self.sibling = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="MUD-SIBLING",
            name="无关组",
            name_en="Unrelated Group",
        )

        # A local candidate: active primary membership directly on the group.
        self.candidate = User.objects.create_user(username="mud_candidate")
        ChurchStructureMembership.objects.create(
            user=self.candidate,
            unit=self.group,
            status=ChurchStructureMembership.STATUS_ACTIVE,
            is_primary=True,
            start_date=self.today,
        )

    # --- fixture helpers -------------------------------------------------------

    def _lead(self, user, unit, **kwargs):
        return ChurchStructureUnitRoleAssignment.objects.create(
            unit=unit,
            role_type=self.lead_role,
            user=user,
            **kwargs,
        )

    def _make_lead_login(self, username, unit):
        user = User.objects.create_user(username=username, password="pw")
        self._lead(user, unit)
        self.client.login(username=username, password="pw")
        return user

    def _detail_url(self, unit):
        return reverse("my_unit_detail", args=[unit.id])

    def _add_url(self, unit, scope=None):
        url = reverse("add_my_unit_coworker_assignment", args=[unit.id])
        if scope:
            url += f"?coworker_user_scope={scope}"
        return url

    def _end_url(self, assignment):
        return reverse("end_my_unit_coworker_assignment", args=[assignment.id])

    # --- detail access ---------------------------------------------------------

    def test_anonymous_redirected_from_detail(self):
        response = self.client.get(self._detail_url(self.group))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response["Location"])

    def test_ordinary_user_without_lead_cannot_access_detail(self):
        User.objects.create_user(username="mud_plain", password="pw")
        self.client.login(username="mud_plain", password="pw")
        response = self.client.get(self._detail_url(self.group))
        self.assertEqual(response.status_code, 404)

    def test_active_lead_can_access_own_unit_detail(self):
        self._make_lead_login("mud_group_lead", self.group)
        response = self.client.get(self._detail_url(self.group) + "?lang=en")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Group &amp; Coworker Management")

    def test_lead_on_parent_can_access_descendant_detail(self):
        self._make_lead_login("mud_district_lead", self.district)
        response = self.client.get(self._detail_url(self.nested))
        self.assertEqual(response.status_code, 200)

    def test_lead_on_one_branch_cannot_access_sibling_detail(self):
        self._make_lead_login("mud_branch_lead", self.group)
        response = self.client.get(self._detail_url(self.sibling))
        self.assertEqual(response.status_code, 404)

    def test_inactive_unit_cannot_be_managed(self):
        self._make_lead_login("mud_inactive_unit", self.group)
        self.group.is_active = False
        self.group.save()
        response = self.client.get(self._detail_url(self.group))
        self.assertEqual(response.status_code, 404)

    def test_expired_lead_cannot_access_detail(self):
        user = User.objects.create_user(username="mud_expired", password="pw")
        self._lead(
            user,
            self.group,
            start_date=self.today - timedelta(days=30),
            end_date=self.today - timedelta(days=1),
        )
        self.client.login(username="mud_expired", password="pw")
        response = self.client.get(self._detail_url(self.group))
        self.assertEqual(response.status_code, 404)

    def test_future_lead_cannot_access_detail(self):
        user = User.objects.create_user(username="mud_future", password="pw")
        self._lead(user, self.group, start_date=self.today + timedelta(days=7))
        self.client.login(username="mud_future", password="pw")
        response = self.client.get(self._detail_url(self.group))
        self.assertEqual(response.status_code, 404)

    def test_inactive_lead_assignment_cannot_access_detail(self):
        user = User.objects.create_user(username="mud_inactive_lead", password="pw")
        self._lead(user, self.group, is_active=False)
        self.client.login(username="mud_inactive_lead", password="pw")
        response = self.client.get(self._detail_url(self.group))
        self.assertEqual(response.status_code, 404)

    def test_non_lead_coworker_cannot_access_detail(self):
        user = User.objects.create_user(username="mud_edify", password="pw")
        ChurchStructureUnitRoleAssignment.objects.create(
            unit=self.group,
            role_type=self.edify_role,
            user=user,
        )
        self.client.login(username="mud_edify", password="pw")
        response = self.client.get(self._detail_url(self.group))
        self.assertEqual(response.status_code, 404)

    def test_membership_alone_cannot_access_detail(self):
        self.client.force_login(self.candidate)
        response = self.client.get(self._detail_url(self.group))
        self.assertEqual(response.status_code, 404)

    def test_staff_can_access_active_unit_detail(self):
        User.objects.create_user(username="mud_staff", password="pw", is_staff=True)
        self.client.login(username="mud_staff", password="pw")
        response = self.client.get(self._detail_url(self.group))
        self.assertEqual(response.status_code, 200)

    def test_superuser_can_access_active_unit_detail(self):
        User.objects.create_superuser(
            username="mud_super", email="mud_super@example.com", password="pw"
        )
        self.client.login(username="mud_super", password="pw")
        response = self.client.get(self._detail_url(self.group))
        self.assertEqual(response.status_code, 200)

    # --- add assignment --------------------------------------------------------

    def test_delegated_lead_can_add_assignment(self):
        self._make_lead_login("mud_add_lead", self.group)
        response = self.client.post(
            self._add_url(self.group),
            {
                "role_type": self.edify_role.id,
                "user": self.candidate.id,
                "start_date": self.today.isoformat(),
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            ChurchStructureUnitRoleAssignment.objects.filter(
                unit=self.group,
                role_type=self.edify_role,
                user=self.candidate,
                is_active=True,
            ).exists()
        )

    def test_delegated_lead_cannot_add_to_unmanageable_unit(self):
        self._make_lead_login("mud_add_branch", self.group)
        response = self.client.post(
            self._add_url(self.sibling),
            {
                "role_type": self.edify_role.id,
                "user": self.candidate.id,
                "start_date": self.today.isoformat(),
            },
        )
        self.assertEqual(response.status_code, 404)
        self.assertFalse(
            ChurchStructureUnitRoleAssignment.objects.filter(unit=self.sibling).exists()
        )

    def test_non_staff_lead_cannot_use_all_users_fallback(self):
        # An unrelated user with no local membership is not a local candidate.
        outsider = User.objects.create_user(username="mud_outsider")
        self._make_lead_login("mud_no_all", self.group)
        response = self.client.post(
            self._add_url(self.group, scope="all"),
            {
                "role_type": self.edify_role.id,
                "user": outsider.id,
                "start_date": self.today.isoformat(),
            },
        )
        self.assertEqual(response.status_code, 302)
        # Scope stayed local, so the non-local user was rejected: nothing created.
        self.assertFalse(
            ChurchStructureUnitRoleAssignment.objects.filter(user=outsider).exists()
        )

    def test_non_staff_lead_detail_hides_all_users_fallback(self):
        self._make_lead_login("mud_hide_all", self.group)
        response = self.client.get(self._detail_url(self.group) + "?lang=en")
        self.assertNotContains(response, "Show all active users")
        self.assertNotContains(response, "coworker_user_scope=all")

    def test_staff_can_use_all_users_fallback(self):
        outsider = User.objects.create_user(username="mud_staff_outsider")
        User.objects.create_user(
            username="mud_staff_all", password="pw", is_staff=True
        )
        self.client.login(username="mud_staff_all", password="pw")
        response = self.client.post(
            self._add_url(self.group, scope="all"),
            {
                "role_type": self.edify_role.id,
                "user": outsider.id,
                "start_date": self.today.isoformat(),
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            ChurchStructureUnitRoleAssignment.objects.filter(
                unit=self.group, user=outsider, is_active=True
            ).exists()
        )

    def test_local_picker_includes_unit_and_parent_members(self):
        parent_member = User.objects.create_user(username="mud_parent_member")
        ChurchStructureMembership.objects.create(
            user=parent_member,
            unit=self.district,
            status=ChurchStructureMembership.STATUS_ACTIVE,
            is_primary=True,
            start_date=self.today,
        )
        form = StructureUnitCoworkerAssignmentForm(
            unit=self.group,
            language="en",
            user_scope=StructureUnitCoworkerAssignmentForm.USER_SCOPE_LOCAL,
        )
        picker_ids = set(form.fields["user"].queryset.values_list("id", flat=True))
        self.assertIn(self.candidate.id, picker_ids)
        self.assertIn(parent_member.id, picker_ids)

    def test_local_picker_excludes_sibling_and_child_members(self):
        sibling_member = User.objects.create_user(username="mud_sibling_member")
        ChurchStructureMembership.objects.create(
            user=sibling_member,
            unit=self.sibling,
            status=ChurchStructureMembership.STATUS_ACTIVE,
            is_primary=True,
            start_date=self.today,
        )
        child_member = User.objects.create_user(username="mud_child_member")
        ChurchStructureMembership.objects.create(
            user=child_member,
            unit=self.nested,
            status=ChurchStructureMembership.STATUS_ACTIVE,
            is_primary=True,
            start_date=self.today,
        )
        form = StructureUnitCoworkerAssignmentForm(
            unit=self.group,
            language="en",
            user_scope=StructureUnitCoworkerAssignmentForm.USER_SCOPE_LOCAL,
        )
        picker_ids = set(form.fields["user"].queryset.values_list("id", flat=True))
        self.assertNotIn(sibling_member.id, picker_ids)
        self.assertNotIn(child_member.id, picker_ids)

    def test_duplicate_assignment_validation_blocks_second_add(self):
        self._make_lead_login("mud_dup_lead", self.group)
        ChurchStructureUnitRoleAssignment.objects.create(
            unit=self.group,
            role_type=self.edify_role,
            user=self.candidate,
            start_date=self.today,
        )
        response = self.client.post(
            self._add_url(self.group),
            {
                "role_type": self.edify_role.id,
                "user": self.candidate.id,
                "start_date": self.today.isoformat(),
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            ChurchStructureUnitRoleAssignment.objects.filter(
                unit=self.group,
                role_type=self.edify_role,
                user=self.candidate,
            ).count(),
            1,
        )

    # --- end assignment --------------------------------------------------------

    def _make_active_assignment(self, unit):
        return ChurchStructureUnitRoleAssignment.objects.create(
            unit=unit,
            role_type=self.edify_role,
            user=self.candidate,
            start_date=self.today,
        )

    def test_delegated_lead_can_end_assignment(self):
        self._make_lead_login("mud_end_lead", self.group)
        assignment = self._make_active_assignment(self.group)
        response = self.client.post(self._end_url(assignment))
        self.assertEqual(response.status_code, 302)
        assignment.refresh_from_db()
        self.assertFalse(assignment.is_active)
        self.assertEqual(assignment.end_date, self.today)

    def test_delegated_lead_cannot_end_in_unmanageable_unit(self):
        assignment = self._make_active_assignment(self.sibling)
        self._make_lead_login("mud_end_branch", self.group)
        response = self.client.post(self._end_url(assignment))
        self.assertEqual(response.status_code, 404)
        assignment.refresh_from_db()
        self.assertTrue(assignment.is_active)

    def test_get_to_end_route_does_not_mutate(self):
        self._make_lead_login("mud_end_get", self.group)
        assignment = self._make_active_assignment(self.group)
        response = self.client.get(self._end_url(assignment))
        self.assertEqual(response.status_code, 405)
        assignment.refresh_from_db()
        self.assertTrue(assignment.is_active)

    def test_ending_does_not_delete_row(self):
        self._make_lead_login("mud_end_keep", self.group)
        assignment = self._make_active_assignment(self.group)
        self.client.post(self._end_url(assignment))
        self.assertTrue(
            ChurchStructureUnitRoleAssignment.objects.filter(id=assignment.id).exists()
        )

    def test_ended_assignment_not_shown_as_active(self):
        self._make_lead_login("mud_end_hidden", self.group)
        assignment = self._make_active_assignment(self.group)
        self.client.post(self._end_url(assignment))
        response = self.client.get(self._detail_url(self.group) + "?lang=en")
        self.assertNotContains(response, self._end_url(assignment))

    # --- boundary --------------------------------------------------------------

    def test_add_and_end_do_not_create_other_rows(self):
        membership_before = ChurchStructureMembership.objects.count()
        self._make_lead_login("mud_boundary", self.group)
        self.client.post(
            self._add_url(self.group),
            {
                "role_type": self.edify_role.id,
                "user": self.candidate.id,
                "start_date": self.today.isoformat(),
            },
        )
        assignment = ChurchStructureUnitRoleAssignment.objects.get(
            unit=self.group, user=self.candidate, role_type=self.edify_role
        )
        self.client.post(self._end_url(assignment))

        self.assertEqual(
            ChurchStructureMembership.objects.count(), membership_before
        )
        self.assertEqual(ChurchRoleAssignment.objects.count(), 0)
        self.assertEqual(TeamAssignment.objects.count(), 0)
        self.assertEqual(TeamAssignmentMember.objects.count(), 0)
        self.assertEqual(BibleStudyMeetingRole.objects.count(), 0)
        # No staff capability or My Serving was granted to the assignee.
        self.candidate.refresh_from_db()
        self.assertFalse(self.candidate.is_staff)

    def test_detail_does_not_expose_staff_structure_links(self):
        self._make_lead_login("mud_no_staff_links", self.group)
        response = self.client.get(self._detail_url(self.group) + "?lang=en")
        self.assertNotContains(response, "/staff/structure/")
        self.assertNotContains(response, "church_structure_unit_detail")

    # --- nav / readiness copy --------------------------------------------------

    def test_list_links_to_detail_page(self):
        self._make_lead_login("mud_list_link", self.group)
        response = self.client.get(reverse("my_units") + "?lang=en")
        self.assertContains(response, self._detail_url(self.group))

    def test_detail_marks_my_units_nav_active(self):
        self._make_lead_login("mud_nav_active", self.group)
        response = self.client.get(self._detail_url(self.group))
        self.assertEqual(response.context["active_nav"], "my_units")

    def test_no_role_profile_copy_renders_english(self):
        self._make_lead_login("mud_noprofile_en", self.group)
        response = self.client.get(self._detail_url(self.group) + "?lang=en")
        self.assertContains(response, "No coworker role profile selected yet.")

    def test_no_role_profile_copy_renders_chinese(self):
        self._make_lead_login("mud_noprofile_zh", self.group)
        response = self.client.get(self._detail_url(self.group) + "?lang=zh")
        self.assertContains(response, "尚未选择同工角色配置。")

    def test_boundary_copy_renders(self):
        self._make_lead_login("mud_boundary_copy", self.group)
        response_en = self.client.get(self._detail_url(self.group) + "?lang=en")
        self.assertContains(
            response_en,
            "The coworker section changes only long-term structure coworker roles.",
        )
        response_zh = self.client.get(self._detail_url(self.group) + "?lang=zh")
        self.assertContains(response_zh, "同工区块只更改长期结构同工角色")

    def test_missing_required_role_readiness_renders(self):
        profile = ChurchStructureUnitRoleProfile.objects.create(
            code=ChurchStructureUnitRoleProfile.CODE_SMALL_GROUP_UNIT,
            name="小组型单元",
            name_en="Small-Group Unit",
        )
        ChurchStructureUnitRoleRequirement.objects.create(
            profile=profile,
            role_type=self.edify_role,
            is_required=True,
        )
        self.group.role_profile = profile
        self.group.save()
        self._make_lead_login("mud_readiness", self.group)
        response = self.client.get(self._detail_url(self.group) + "?lang=en")
        self.assertContains(response, "Missing Required Roles")
        self.assertContains(response, "Edify")


class MyUnitSmallGroupMemberManageTests(TestCase):
    """GROUP-MEMBERSHIP-MANAGE.1A small-group member management on My Units.

    Assign/end belonging (``ChurchStructureMembership``) for small-group units
    only, gated by ``can_manage_unit_members`` (staff/superuser or active
    ``lead`` ancestor-or-self via ``can_manage_unit_coworkers``). Belonging is
    never inferred from or granted to serving; membership alone never grants
    management. "Unassigned" is a user state (no current/future active
    membership and no pending request) — never a fake structure unit. Pending
    signup/profile group requests stay in the staff membership-request
    workflow and are shown read-only here.
    """

    def setUp(self):
        self.today = timezone.localdate()

        self.lead_role = ChurchStructureUnitRoleType.objects.create(
            code=ChurchStructureUnitRoleType.CODE_LEAD,
            name="负责人",
            name_en="Lead",
        )

        self.district = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_DISTRICT,
            code="GMM-DISTRICT",
            name="成员区",
            name_en="Member District",
        )
        self.group = ChurchStructureUnit.objects.create(
            parent=self.district,
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="GMM-GROUP",
            name="成员小组",
            name_en="Member Group",
        )
        self.sibling = ChurchStructureUnit.objects.create(
            parent=self.district,
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="GMM-SIBLING",
            name="邻组",
            name_en="Sibling Group",
        )

        # An existing active primary member of the managed group.
        self.member = User.objects.create_user(username="gmm_member")
        self.member_membership = ChurchStructureMembership.objects.create(
            user=self.member,
            unit=self.group,
            status=ChurchStructureMembership.STATUS_ACTIVE,
            is_primary=True,
            start_date=self.today,
        )
        # A user with no membership rows at all: the assignable candidate.
        self.unassigned = User.objects.create_user(username="gmm_unassigned")

    # --- fixture helpers -------------------------------------------------------

    def _make_lead_login(self, username, unit):
        user = User.objects.create_user(username=username, password="pw")
        ChurchStructureUnitRoleAssignment.objects.create(
            unit=unit,
            role_type=self.lead_role,
            user=user,
        )
        self.client.login(username=username, password="pw")
        return user

    def _make_staff_login(self, username):
        user = User.objects.create_user(
            username=username, password="pw", is_staff=True
        )
        self.client.login(username=username, password="pw")
        return user

    def _detail_url(self, unit):
        return reverse("my_unit_detail", args=[unit.id])

    def _add_url(self, unit):
        return reverse("add_my_unit_member", args=[unit.id])

    def _end_url(self, membership):
        return reverse("end_my_unit_member", args=[membership.id])

    def _candidate_ids(self, response):
        form = response.context["member_add_form"]
        return set(form.fields["user"].queryset.values_list("id", flat=True))

    # --- access ----------------------------------------------------------------

    def test_staff_sees_member_section_on_small_group(self):
        self._make_staff_login("gmm_staff")
        response = self.client.get(self._detail_url(self.group) + "?lang=en")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Group Members")
        self.assertTrue(response.context["member_manage_enabled"])

    def test_superuser_sees_member_section(self):
        User.objects.create_superuser(
            username="gmm_super", email="gmm_super@example.com", password="pw"
        )
        self.client.login(username="gmm_super", password="pw")
        response = self.client.get(self._detail_url(self.group))
        self.assertTrue(response.context["member_manage_enabled"])

    def test_group_lead_sees_member_section(self):
        self._make_lead_login("gmm_group_lead", self.group)
        response = self.client.get(self._detail_url(self.group) + "?lang=en")
        self.assertContains(response, "Group Members")

    def test_district_lead_sees_member_section_on_descendant_group(self):
        self._make_lead_login("gmm_district_lead", self.district)
        response = self.client.get(self._detail_url(self.group))
        self.assertTrue(response.context["member_manage_enabled"])

    def test_ordinary_user_cannot_access_or_post(self):
        User.objects.create_user(username="gmm_plain", password="pw")
        self.client.login(username="gmm_plain", password="pw")
        self.assertEqual(
            self.client.get(self._detail_url(self.group)).status_code, 404
        )
        response = self.client.post(
            self._add_url(self.group), {"user": self.unassigned.id}
        )
        self.assertEqual(response.status_code, 404)
        self.assertFalse(
            ChurchStructureMembership.objects.filter(user=self.unassigned).exists()
        )

    def test_membership_alone_does_not_grant_member_management(self):
        self.client.force_login(self.member)
        self.assertEqual(
            self.client.get(self._detail_url(self.group)).status_code, 404
        )
        response = self.client.post(
            self._add_url(self.group), {"user": self.unassigned.id}
        )
        self.assertEqual(response.status_code, 404)

    def test_sibling_group_lead_cannot_add_to_unmanaged_group(self):
        self._make_lead_login("gmm_sibling_lead", self.sibling)
        response = self.client.post(
            self._add_url(self.group), {"user": self.unassigned.id}
        )
        self.assertEqual(response.status_code, 404)
        self.assertFalse(
            ChurchStructureMembership.objects.filter(user=self.unassigned).exists()
        )

    # --- small-group-only guard --------------------------------------------------

    def test_district_page_has_no_member_section_and_add_is_blocked(self):
        self._make_staff_login("gmm_staff_district")
        response = self.client.get(self._detail_url(self.district) + "?lang=en")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["member_manage_enabled"])
        self.assertNotContains(response, "Group Members")
        post_response = self.client.post(
            self._add_url(self.district), {"user": self.unassigned.id}
        )
        self.assertEqual(post_response.status_code, 404)
        self.assertFalse(
            ChurchStructureMembership.objects.filter(unit=self.district).exists()
        )

    # --- listing ----------------------------------------------------------------

    def test_page_lists_active_members(self):
        self._make_lead_login("gmm_list_lead", self.group)
        response = self.client.get(self._detail_url(self.group) + "?lang=en")
        self.assertContains(response, "gmm_member")
        member_ids = [
            membership.id for membership in response.context["active_members"]
        ]
        self.assertEqual(member_ids, [self.member_membership.id])

    def test_candidates_exclude_assigned_users(self):
        self._make_lead_login("gmm_candidates_lead", self.group)
        response = self.client.get(self._detail_url(self.group))
        candidate_ids = self._candidate_ids(response)
        self.assertIn(self.unassigned.id, candidate_ids)
        self.assertNotIn(self.member.id, candidate_ids)

    def test_candidates_exclude_pending_request_users(self):
        requester = User.objects.create_user(username="gmm_requester")
        pending = ChurchStructureMembership.objects.create(
            user=requester,
            unit=self.sibling,
            status=ChurchStructureMembership.STATUS_REQUESTED,
            is_primary=False,
            requested_by=requester,
        )
        self._make_lead_login("gmm_pending_lead", self.group)
        response = self.client.get(self._detail_url(self.group))
        self.assertNotIn(requester.id, self._candidate_ids(response))
        pending.refresh_from_db()
        self.assertEqual(
            pending.status, ChurchStructureMembership.STATUS_REQUESTED
        )

    def test_pending_request_for_this_unit_is_listed_with_badge(self):
        # GROUP-MEMBERSHIP-REQUEST.1B added approve/reject controls to these
        # rows; the delegated review flow itself is covered by
        # MyUnitMemberRequestReviewTests. This test keeps asserting the row
        # renders with the pending badge.
        requester = User.objects.create_user(username="gmm_unit_requester")
        ChurchStructureMembership.objects.create(
            user=requester,
            unit=self.group,
            status=ChurchStructureMembership.STATUS_REQUESTED,
            is_primary=False,
            requested_by=requester,
        )
        self._make_lead_login("gmm_pending_view", self.group)
        response = self.client.get(self._detail_url(self.group) + "?lang=en")
        self.assertContains(response, "Pending request")
        self.assertContains(response, "gmm_unit_requester")

    # --- add member ---------------------------------------------------------------

    def test_add_unassigned_user_creates_active_primary_membership(self):
        self._make_lead_login("gmm_add_lead", self.group)
        response = self.client.post(
            self._add_url(self.group), {"user": self.unassigned.id}
        )
        self.assertEqual(response.status_code, 302)
        membership = ChurchStructureMembership.objects.get(user=self.unassigned)
        self.assertEqual(membership.unit, self.group)
        self.assertEqual(
            membership.status, ChurchStructureMembership.STATUS_ACTIVE
        )
        self.assertTrue(membership.is_primary)
        self.assertEqual(membership.start_date, self.today)
        self.assertEqual(
            membership.membership_type,
            ChurchStructureMembership.TYPE_SMALL_GROUP_MEMBER,
        )
        self.assertTrue(membership.is_current_primary)

    def test_add_already_assigned_user_is_blocked(self):
        self._make_lead_login("gmm_block_lead", self.group)
        response = self.client.post(
            self._add_url(self.group), {"user": self.member.id}
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            ChurchStructureMembership.objects.filter(
                user=self.member,
                status=ChurchStructureMembership.STATUS_ACTIVE,
            ).count(),
            1,
        )
        self.assertEqual(
            ChurchStructureMembership.objects.filter(
                user=self.member,
                status=ChurchStructureMembership.STATUS_ACTIVE,
                is_primary=True,
            ).count(),
            1,
        )

    def test_add_user_with_pending_request_is_blocked_and_request_kept(self):
        requester = User.objects.create_user(username="gmm_req_block")
        pending = ChurchStructureMembership.objects.create(
            user=requester,
            unit=self.sibling,
            status=ChurchStructureMembership.STATUS_REQUESTED,
            is_primary=False,
            requested_by=requester,
        )
        self._make_lead_login("gmm_req_block_lead", self.group)
        response = self.client.post(
            self._add_url(self.group), {"user": requester.id}
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            ChurchStructureMembership.objects.filter(user=requester).count(), 1
        )
        pending.refresh_from_db()
        self.assertEqual(
            pending.status, ChurchStructureMembership.STATUS_REQUESTED
        )
        self.assertEqual(pending.unit, self.sibling)

    def test_add_does_not_create_serving_or_coworker_rows(self):
        from ministry.models import TeamAssignmentMember, TeamMembership

        self._make_lead_login("gmm_boundary_lead", self.group)
        self.client.post(self._add_url(self.group), {"user": self.unassigned.id})
        self.assertTrue(
            ChurchStructureMembership.objects.filter(
                user=self.unassigned,
                status=ChurchStructureMembership.STATUS_ACTIVE,
            ).exists()
        )
        self.assertFalse(
            TeamMembership.objects.filter(user=self.unassigned).exists()
        )
        self.assertFalse(
            TeamAssignmentMember.objects.filter(
                membership__user=self.unassigned
            ).exists()
        )
        self.assertFalse(
            ChurchStructureUnitRoleAssignment.objects.filter(
                user=self.unassigned
            ).exists()
        )

    # --- end member ---------------------------------------------------------------

    def test_end_membership_marks_ended_and_keeps_user(self):
        self._make_lead_login("gmm_end_lead", self.group)
        response = self.client.post(self._end_url(self.member_membership))
        self.assertEqual(response.status_code, 302)
        self.member_membership.refresh_from_db()
        self.assertEqual(
            self.member_membership.status,
            ChurchStructureMembership.STATUS_ENDED,
        )
        self.assertFalse(self.member_membership.is_primary)
        self.assertEqual(self.member_membership.end_date, self.today)
        self.member.refresh_from_db()
        self.assertTrue(self.member.is_active)

    def test_sibling_group_lead_cannot_end_membership_outside_unit(self):
        self._make_lead_login("gmm_end_sibling_lead", self.sibling)
        response = self.client.post(self._end_url(self.member_membership))
        self.assertEqual(response.status_code, 404)
        self.member_membership.refresh_from_db()
        self.assertEqual(
            self.member_membership.status,
            ChurchStructureMembership.STATUS_ACTIVE,
        )

    def test_end_requires_currently_active_membership(self):
        ended = ChurchStructureMembership.objects.create(
            user=self.unassigned,
            unit=self.group,
            status=ChurchStructureMembership.STATUS_ENDED,
            is_primary=False,
            start_date=self.today - timedelta(days=30),
            end_date=self.today - timedelta(days=1),
        )
        self._make_lead_login("gmm_end_inactive_lead", self.group)
        response = self.client.post(self._end_url(ended))
        self.assertEqual(response.status_code, 302)
        ended.refresh_from_db()
        self.assertEqual(ended.status, ChurchStructureMembership.STATUS_ENDED)
        self.assertEqual(ended.end_date, self.today - timedelta(days=1))

    # --- bilingual copy -------------------------------------------------------------

    def test_member_section_bilingual_copy_renders(self):
        self._make_lead_login("gmm_lang_lead", self.group)
        response_en = self.client.get(self._detail_url(self.group) + "?lang=en")
        self.assertContains(response_en, "Group Members")
        self.assertContains(response_en, "Add Unassigned User")
        self.assertContains(response_en, "End membership")
        response_zh = self.client.get(self._detail_url(self.group) + "?lang=zh")
        self.assertContains(response_zh, "组员管理")
        self.assertContains(response_zh, "添加未分配用户")
        self.assertContains(response_zh, "结束归属")


class MyUnitMemberRequestReviewTests(TestCase):
    """GROUP-MEMBERSHIP-REQUEST.1B delegated request review on My Units.

    Approve/reject pending ``ChurchStructureMembership`` requests for
    small-group units, gated by ``can_manage_unit_members`` (staff/superuser or
    active ``lead`` ancestor-or-self). Approval reuses the shared staff
    semantics (``approve_membership_request``) including the active-primary
    fail-closed block. Belonging only: serving/team/Bible Study rows never
    grant review rights and are never created by approval. Non-small-group
    requests fail closed on this surface and stay staff-queue-only.
    """

    def setUp(self):
        self.today = timezone.localdate()

        self.lead_role = ChurchStructureUnitRoleType.objects.create(
            code=ChurchStructureUnitRoleType.CODE_LEAD,
            name="负责人",
            name_en="Lead",
        )

        self.district = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_DISTRICT,
            code="GMR-DISTRICT",
            name="申请区",
            name_en="Request District",
        )
        self.group = ChurchStructureUnit.objects.create(
            parent=self.district,
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="GMR-GROUP",
            name="申请小组",
            name_en="Request Group",
        )
        self.sibling = ChurchStructureUnit.objects.create(
            parent=self.district,
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="GMR-SIBLING",
            name="邻组",
            name_en="Sibling Group",
        )

        # A pending signup/profile-style group request for the managed group.
        self.requester = User.objects.create_user(username="gmr_requester")
        self.request_row = self._make_request(self.requester, self.group)

        # An existing active primary member (membership alone grants nothing).
        self.member = User.objects.create_user(username="gmr_member")
        ChurchStructureMembership.objects.create(
            user=self.member,
            unit=self.group,
            status=ChurchStructureMembership.STATUS_ACTIVE,
            is_primary=True,
            start_date=self.today,
        )

    # --- fixture helpers -------------------------------------------------------

    def _make_request(self, user, unit):
        # Mirrors create_or_update_signup_membership_request row shape.
        return ChurchStructureMembership.objects.create(
            user=user,
            unit=unit,
            membership_type=ChurchStructureMembership.TYPE_SMALL_GROUP_MEMBER,
            status=ChurchStructureMembership.STATUS_REQUESTED,
            is_primary=False,
            requested_by=user,
        )

    def _make_lead_login(self, username, unit):
        user = User.objects.create_user(username=username, password="pw")
        ChurchStructureUnitRoleAssignment.objects.create(
            unit=unit,
            role_type=self.lead_role,
            user=user,
        )
        self.client.login(username=username, password="pw")
        return user

    def _detail_url(self, unit):
        return reverse("my_unit_detail", args=[unit.id])

    def _approve_url(self, membership):
        return reverse("approve_my_unit_member_request", args=[membership.id])

    def _reject_url(self, membership):
        return reverse("reject_my_unit_member_request", args=[membership.id])

    def _assert_still_requested(self):
        self.request_row.refresh_from_db()
        self.assertEqual(
            self.request_row.status,
            ChurchStructureMembership.STATUS_REQUESTED,
        )
        self.assertFalse(self.request_row.is_primary)
        self.assertIsNone(self.request_row.approved_by)
        self.assertIsNone(self.request_row.approved_at)

    # --- page rendering ----------------------------------------------------------

    def test_pending_request_rows_render_on_small_group_page(self):
        self._make_lead_login("gmr_render_lead", self.group)
        response = self.client.get(self._detail_url(self.group) + "?lang=en")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "gmr_requester")
        self.assertContains(response, "Pending request")

    def test_group_lead_sees_approve_reject_controls(self):
        self._make_lead_login("gmr_controls_lead", self.group)
        response = self.client.get(self._detail_url(self.group) + "?lang=en")
        self.assertContains(response, self._approve_url(self.request_row))
        self.assertContains(response, self._reject_url(self.request_row))
        self.assertContains(response, "Approve")
        self.assertContains(response, "Reject")

    def test_ancestor_lead_sees_controls_for_descendant_group_request(self):
        self._make_lead_login("gmr_district_lead", self.district)
        response = self.client.get(self._detail_url(self.group))
        self.assertContains(response, self._approve_url(self.request_row))
        self.assertContains(response, self._reject_url(self.request_row))

    def test_bilingual_review_copy_renders(self):
        self._make_lead_login("gmr_lang_lead", self.group)
        response_en = self.client.get(self._detail_url(self.group) + "?lang=en")
        self.assertContains(response_en, "Approve")
        self.assertContains(response_en, "Reject")
        self.assertContains(
            response_en,
            "Approving changes group belonging only",
        )
        response_zh = self.client.get(self._detail_url(self.group) + "?lang=zh")
        self.assertContains(response_zh, "批准")
        self.assertContains(response_zh, "拒绝")
        self.assertContains(response_zh, "批准只更改小组归属")

    # --- authorization -------------------------------------------------------------

    def test_ordinary_user_cannot_approve_or_reject(self):
        User.objects.create_user(username="gmr_plain", password="pw")
        self.client.login(username="gmr_plain", password="pw")
        self.assertEqual(
            self.client.post(self._approve_url(self.request_row)).status_code, 404
        )
        self.assertEqual(
            self.client.post(self._reject_url(self.request_row)).status_code, 404
        )
        self._assert_still_requested()

    def test_membership_only_user_cannot_approve_or_reject(self):
        self.client.force_login(self.member)
        self.assertEqual(
            self.client.post(self._approve_url(self.request_row)).status_code, 404
        )
        self.assertEqual(
            self.client.post(self._reject_url(self.request_row)).status_code, 404
        )
        self._assert_still_requested()

    def test_sibling_group_lead_cannot_approve_or_reject(self):
        self._make_lead_login("gmr_sibling_lead", self.sibling)
        self.assertEqual(
            self.client.post(self._approve_url(self.request_row)).status_code, 404
        )
        self.assertEqual(
            self.client.post(self._reject_url(self.request_row)).status_code, 404
        )
        self._assert_still_requested()

    def test_group_lead_cannot_review_request_for_other_unit(self):
        other_requester = User.objects.create_user(username="gmr_other_requester")
        other_request = self._make_request(other_requester, self.sibling)
        self._make_lead_login("gmr_wrong_route_lead", self.group)
        self.assertEqual(
            self.client.post(self._approve_url(other_request)).status_code, 404
        )
        self.assertEqual(
            self.client.post(self._reject_url(other_request)).status_code, 404
        )
        other_request.refresh_from_db()
        self.assertEqual(
            other_request.status, ChurchStructureMembership.STATUS_REQUESTED
        )

    def test_serving_rows_do_not_grant_review_rights(self):
        from ministry.models import MinistryTeam, TeamMembership
        from studies.models import (
            BibleStudyLesson,
            BibleStudyMeeting,
            BibleStudyMeetingRole,
            BibleStudySeries,
        )

        server = User.objects.create_user(username="gmr_server", password="pw")
        team = MinistryTeam.objects.create(name="敬拜队", name_en="Worship Team")
        TeamMembership.objects.create(
            team=team,
            user=server,
            role=TeamMembership.ROLE_LEAD,
            can_lead=True,
        )
        series = BibleStudySeries.objects.create(title="查经系列")
        lesson = BibleStudyLesson.objects.create(
            series=series,
            title="第一课",
            lesson_date=self.today,
        )
        meeting = BibleStudyMeeting.objects.create(
            lesson=lesson,
            meeting_datetime=timezone.now(),
            anchor_unit=self.group,
        )
        BibleStudyMeetingRole.objects.create(
            meeting=meeting,
            role=BibleStudyMeetingRole.ROLE_DISCUSSION_LEADER,
            user=server,
        )
        self.client.login(username="gmr_server", password="pw")
        self.assertEqual(
            self.client.post(self._approve_url(self.request_row)).status_code, 404
        )
        self.assertEqual(
            self.client.post(self._reject_url(self.request_row)).status_code, 404
        )
        self._assert_still_requested()

    def test_staff_can_approve_via_my_units(self):
        staff = User.objects.create_user(
            username="gmr_staff", password="pw", is_staff=True
        )
        self.client.login(username="gmr_staff", password="pw")
        response = self.client.post(self._approve_url(self.request_row))
        self.assertEqual(response.status_code, 302)
        self.request_row.refresh_from_db()
        self.assertEqual(
            self.request_row.status, ChurchStructureMembership.STATUS_ACTIVE
        )
        self.assertEqual(self.request_row.approved_by, staff)

    # --- approve ---------------------------------------------------------------------

    def test_approve_activates_requested_membership(self):
        lead = self._make_lead_login("gmr_approve_lead", self.group)
        response = self.client.post(self._approve_url(self.request_row))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, self._detail_url(self.group))
        self.request_row.refresh_from_db()
        self.assertEqual(
            self.request_row.status, ChurchStructureMembership.STATUS_ACTIVE
        )
        self.assertTrue(self.request_row.is_primary)
        self.assertEqual(
            self.request_row.membership_type,
            ChurchStructureMembership.TYPE_SMALL_GROUP_MEMBER,
        )
        self.assertEqual(self.request_row.start_date, self.today)
        self.assertEqual(self.request_row.approved_by, lead)
        self.assertIsNotNone(self.request_row.approved_at)
        self.assertEqual(self.request_row.requested_by, self.requester)
        self.assertTrue(self.request_row.is_current_primary)

    def test_approve_creates_no_serving_role_or_legacy_rows(self):
        from ministry.models import TeamAssignmentMember, TeamMembership
        from studies.models import BibleStudyMeetingRole

        self._make_lead_login("gmr_boundary_lead", self.group)
        self.client.post(self._approve_url(self.request_row))
        self.request_row.refresh_from_db()
        self.assertEqual(
            self.request_row.status, ChurchStructureMembership.STATUS_ACTIVE
        )
        self.assertFalse(
            TeamMembership.objects.filter(user=self.requester).exists()
        )
        self.assertFalse(
            TeamAssignmentMember.objects.filter(
                membership__user=self.requester
            ).exists()
        )
        self.assertFalse(
            BibleStudyMeetingRole.objects.filter(user=self.requester).exists()
        )
        self.assertFalse(
            ChurchStructureUnitRoleAssignment.objects.filter(
                user=self.requester
            ).exists()
        )
        self.assertFalse(
            ChurchRoleAssignment.objects.filter(user=self.requester).exists()
        )
        # PROFILE-SG-FIELD-RETIRE.1A: the legacy profile group field no longer
        # exists, so approval cannot write it.
        with self.assertRaises(FieldDoesNotExist):
            Profile._meta.get_field("small_group")

    def test_approve_blocked_when_requester_has_active_primary(self):
        ChurchStructureMembership.objects.create(
            user=self.requester,
            unit=self.sibling,
            status=ChurchStructureMembership.STATUS_ACTIVE,
            is_primary=True,
            start_date=self.today,
        )
        self._make_lead_login("gmr_blocked_lead", self.group)
        response = self.client.post(self._approve_url(self.request_row))
        self.assertEqual(response.status_code, 302)
        self._assert_still_requested()
        # The existing active primary belonging is untouched.
        self.assertEqual(
            ChurchStructureMembership.objects.filter(
                user=self.requester,
                status=ChurchStructureMembership.STATUS_ACTIVE,
                is_primary=True,
            ).count(),
            1,
        )

    # --- reject ---------------------------------------------------------------------

    def test_reject_marks_rejected_and_not_primary(self):
        self._make_lead_login("gmr_reject_lead", self.group)
        response = self.client.post(self._reject_url(self.request_row))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, self._detail_url(self.group))
        self.request_row.refresh_from_db()
        self.assertEqual(
            self.request_row.status, ChurchStructureMembership.STATUS_REJECTED
        )
        self.assertFalse(self.request_row.is_primary)

    def test_reject_keeps_user_and_membership_row(self):
        self._make_lead_login("gmr_keep_lead", self.group)
        self.client.post(self._reject_url(self.request_row))
        self.assertTrue(User.objects.filter(pk=self.requester.pk).exists())
        self.assertTrue(
            ChurchStructureMembership.objects.filter(
                pk=self.request_row.pk
            ).exists()
        )

    # --- method / state guards --------------------------------------------------------

    def test_approve_and_reject_are_post_only(self):
        self._make_lead_login("gmr_get_lead", self.group)
        self.assertEqual(
            self.client.get(self._approve_url(self.request_row)).status_code, 405
        )
        self.assertEqual(
            self.client.get(self._reject_url(self.request_row)).status_code, 405
        )
        self._assert_still_requested()

    def test_processed_request_cannot_be_reviewed_again(self):
        self._make_lead_login("gmr_repeat_lead", self.group)
        self.client.post(self._reject_url(self.request_row))
        self.assertEqual(
            self.client.post(self._approve_url(self.request_row)).status_code, 404
        )
        self.request_row.refresh_from_db()
        self.assertEqual(
            self.request_row.status, ChurchStructureMembership.STATUS_REJECTED
        )

    def test_non_small_group_request_fails_closed_even_for_staff(self):
        district_requester = User.objects.create_user(
            username="gmr_district_requester"
        )
        district_request = self._make_request(district_requester, self.district)
        User.objects.create_user(
            username="gmr_staff_district", password="pw", is_staff=True
        )
        self.client.login(username="gmr_staff_district", password="pw")
        self.assertEqual(
            self.client.post(self._approve_url(district_request)).status_code, 404
        )
        self.assertEqual(
            self.client.post(self._reject_url(district_request)).status_code, 404
        )
        district_request.refresh_from_db()
        self.assertEqual(
            district_request.status, ChurchStructureMembership.STATUS_REQUESTED
        )


class MyUnitsListUxTests(TestCase):
    """MYUNITS-UX.1A compact hierarchy/filter/search on the /my-units/ list page.

    This is a presentation/data-shaping slice only. It must not change the
    permission model, must not mutate any assignment/membership/serving row, and
    must keep the page a read-only operational surface separate from the admin
    structure tree at ``/staff/structure/``.
    """

    def setUp(self):
        self.today = timezone.localdate()
        self.url = reverse("my_units")

        self.lead_role = ChurchStructureUnitRoleType.objects.create(
            code=ChurchStructureUnitRoleType.CODE_LEAD,
            name="负责人",
            name_en="Lead",
        )
        self.edify_role = ChurchStructureUnitRoleType.objects.create(
            code=ChurchStructureUnitRoleType.CODE_EDIFY,
            name="带查经同工",
            name_en="Edify",
        )

        # district -> group -> nested, plus an unrelated sibling branch.
        self.district = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_DISTRICT,
            code="UX-DISTRICT",
            name="负责区",
            name_en="Lead District",
        )
        self.group = ChurchStructureUnit.objects.create(
            parent=self.district,
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="UX-GROUP",
            name="阿尔法小组",
            name_en="Alpha Group",
        )
        self.nested = ChurchStructureUnit.objects.create(
            parent=self.group,
            unit_type=ChurchStructureUnit.UNIT_CUSTOM,
            code="UX-NESTED",
            name="子单元",
            name_en="Nested Unit",
        )
        self.sibling = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="UX-SIBLING",
            name="无关组",
            name_en="Unrelated Group",
        )

    def _lead(self, user, unit, **kwargs):
        return ChurchStructureUnitRoleAssignment.objects.create(
            unit=unit,
            role_type=self.lead_role,
            user=user,
            **kwargs,
        )

    def _staff_login(self, username="ux_staff"):
        User.objects.create_user(username=username, password="pw", is_staff=True)
        self.client.login(username=username, password="pw")

    # --- A. Staff / superuser compact view -----------------------------------

    def test_staff_view_uses_compact_table_not_full_roster(self):
        coworker = User.objects.create_user(username="ux_roster_member")
        ChurchStructureUnitRoleAssignment.objects.create(
            unit=self.group,
            role_type=self.edify_role,
            user=coworker,
        )
        self._staff_login()
        response = self.client.get(self.url + "?lang=en")
        self.assertEqual(response.status_code, 200)
        # Compact table layout, not repeated full roster cards.
        self.assertContains(response, "my-units-table")
        # Active units appear.
        self.assertContains(response, "Lead District")
        self.assertContains(response, "Alpha Group")
        # The list page shows an active-coworker COUNT, not the roster names.
        self.assertNotContains(response, "ux_roster_member")

    def test_staff_view_excludes_inactive_units(self):
        self.sibling.is_active = False
        self.sibling.save()
        self._staff_login("ux_staff_inactive")
        response = self.client.get(self.url + "?lang=en")
        self.assertContains(response, "Lead District")
        self.assertNotContains(response, "Unrelated Group")

    def test_child_unit_renders_after_parent_in_hierarchy_order(self):
        self._staff_login("ux_staff_order")
        response = self.client.get(self.url + "?lang=en")
        body = response.content.decode()
        district_at = body.index("Lead District")
        group_at = body.index("Alpha Group")
        nested_at = body.index("Nested Unit")
        self.assertLess(district_at, group_at)
        self.assertLess(group_at, nested_at)

    def test_detail_links_point_to_my_unit_detail(self):
        self._staff_login("ux_staff_links")
        response = self.client.get(self.url + "?lang=en")
        self.assertContains(
            response, reverse("my_unit_detail", args=[self.group.id])
        )

    # --- B. Delegated lead view ----------------------------------------------

    def test_lead_sees_subtree_not_unrelated_branch(self):
        user = User.objects.create_user(username="ux_lead", password="pw")
        self._lead(user, self.group)
        self.client.login(username="ux_lead", password="pw")
        response = self.client.get(self.url + "?lang=en")
        # Manageable subtree (group + nested) renders; the unrelated sibling and
        # the un-led ancestor district do not get their own manageable rows.
        # (District's name can still appear inside a descendant's path label, so
        # assert on the per-row detail link rather than the plain-text name.)
        self.assertContains(response, reverse("my_unit_detail", args=[self.group.id]))
        self.assertContains(response, reverse("my_unit_detail", args=[self.nested.id]))
        self.assertNotContains(
            response, reverse("my_unit_detail", args=[self.sibling.id])
        )
        self.assertNotContains(
            response, reverse("my_unit_detail", args=[self.district.id])
        )

    def test_membership_alone_shows_empty_state_not_units(self):
        user = User.objects.create_user(username="ux_member", password="pw")
        ChurchStructureMembership.objects.create(
            user=user,
            unit=self.group,
            status=ChurchStructureMembership.STATUS_ACTIVE,
            is_primary=True,
            start_date=self.today,
        )
        self.client.login(username="ux_member", password="pw")
        response = self.client.get(self.url + "?lang=en")
        self.assertContains(response, "You do not currently lead any units.")
        self.assertNotContains(response, "my-units-table")

    def test_non_lead_coworker_shows_empty_state(self):
        user = User.objects.create_user(username="ux_noncoworker", password="pw")
        ChurchStructureUnitRoleAssignment.objects.create(
            unit=self.group,
            role_type=self.edify_role,
            user=user,
        )
        self.client.login(username="ux_noncoworker", password="pw")
        response = self.client.get(self.url + "?lang=en")
        self.assertContains(response, "You do not currently lead any units.")

    def test_no_staff_structure_link_for_non_staff_lead(self):
        user = User.objects.create_user(username="ux_lead_nostaff", password="pw")
        self._lead(user, self.group)
        self.client.login(username="ux_lead_nostaff", password="pw")
        response = self.client.get(self.url + "?lang=en")
        self.assertNotContains(response, "/staff/structure")

    # --- C. Filters / search --------------------------------------------------

    def test_q_filters_by_code(self):
        self._staff_login("ux_q_code")
        response = self.client.get(self.url + "?lang=en&q=UX-SIBLING")
        self.assertContains(response, "Unrelated Group")
        self.assertNotContains(response, "Alpha Group")

    def test_q_filters_by_chinese_name(self):
        self._staff_login("ux_q_zh")
        response = self.client.get(self.url + "?lang=en&q=阿尔法")
        self.assertContains(response, "Alpha Group")
        self.assertNotContains(response, "Unrelated Group")

    def test_q_filters_by_english_name(self):
        self._staff_login("ux_q_en")
        response = self.client.get(self.url + "?lang=en&q=Nested")
        self.assertContains(response, "Nested Unit")
        self.assertNotContains(response, "Unrelated Group")

    def _profile_with_required_edify(self):
        profile = ChurchStructureUnitRoleProfile.objects.create(
            code=ChurchStructureUnitRoleProfile.CODE_SMALL_GROUP_UNIT,
            name="小组型单元",
            name_en="Small-Group Unit",
        )
        ChurchStructureUnitRoleRequirement.objects.create(
            profile=profile,
            role_type=self.edify_role,
            is_required=True,
        )
        return profile

    def _detail_link(self, unit):
        return reverse("my_unit_detail", args=[unit.id])

    def test_attention_filter_shows_missing_or_no_profile(self):
        # Each shown unit links to its detail page; path labels are plain text,
        # so the detail link is the reliable "this row is present" signal (an
        # ancestor's name can appear inside a descendant's path label).
        # group: has a profile but is missing the required edify role.
        self.group.role_profile = self._profile_with_required_edify()
        self.group.save()
        # district + nested: give a complete profile so they are NOT attention.
        complete_profile = ChurchStructureUnitRoleProfile.objects.create(
            code="ux_complete",
            name="完整",
            name_en="Complete",
        )
        for unit in (self.district, self.nested):
            unit.role_profile = complete_profile
            unit.save()
        # sibling: keep no role profile (also "attention").
        self._staff_login("ux_attention")
        response = self.client.get(self.url + "?lang=en&attention=1")
        self.assertContains(response, self._detail_link(self.group))  # missing
        self.assertContains(response, self._detail_link(self.sibling))  # no prof
        self.assertNotContains(response, self._detail_link(self.district))
        self.assertNotContains(response, self._detail_link(self.nested))

    def test_missing_required_filter(self):
        self.group.role_profile = self._profile_with_required_edify()
        self.group.save()
        self._staff_login("ux_missing")
        response = self.client.get(self.url + "?lang=en&missing_required=1")
        # group has a profile with an unmet required role.
        self.assertContains(response, self._detail_link(self.group))
        # sibling/district/nested have no profile => no *missing required* count.
        self.assertNotContains(response, self._detail_link(self.sibling))
        self.assertNotContains(response, self._detail_link(self.district))
        self.assertNotContains(response, self._detail_link(self.nested))

    def test_no_role_profile_filter(self):
        self.group.role_profile = self._profile_with_required_edify()
        self.group.save()
        self._staff_login("ux_noprofile")
        response = self.client.get(self.url + "?lang=en&no_role_profile=1")
        # sibling/district/nested have no profile; group has one.
        self.assertContains(response, self._detail_link(self.sibling))
        self.assertContains(response, self._detail_link(self.district))
        self.assertContains(response, self._detail_link(self.nested))
        self.assertNotContains(response, self._detail_link(self.group))

    def test_filters_combine_without_expanding_permissions(self):
        # Non-staff lead limited to the group subtree; a search term that also
        # matches the unrelated branch must NOT surface it.
        user = User.objects.create_user(username="ux_combine", password="pw")
        self._lead(user, self.group)
        self.client.login(username="ux_combine", password="pw")
        response = self.client.get(self.url + "?lang=en&q=Group&no_role_profile=1")
        self.assertContains(response, "Alpha Group")
        self.assertNotContains(response, "Unrelated Group")

    def test_empty_filter_result_shows_empty_state(self):
        self._staff_login("ux_empty")
        response = self.client.get(self.url + "?lang=en&q=zzz-no-match")
        self.assertContains(response, "No manageable units match these filters.")
        self.assertNotContains(response, "my-units-table")

    def test_clear_filters_link_rendered_when_filters_active(self):
        self._staff_login("ux_clear")
        active = self.client.get(self.url + "?lang=en&q=Alpha")
        self.assertContains(active, "Clear filters")
        inactive = self.client.get(self.url + "?lang=en")
        self.assertNotContains(inactive, "Clear filters")

    # --- D. Boundary: list UX never mutates rows -----------------------------

    def test_list_view_does_not_mutate_any_rows(self):
        coworker = User.objects.create_user(username="ux_boundary_member")
        ChurchStructureUnitRoleAssignment.objects.create(
            unit=self.group,
            role_type=self.edify_role,
            user=coworker,
        )
        ChurchStructureMembership.objects.create(
            user=coworker,
            unit=self.group,
            status=ChurchStructureMembership.STATUS_ACTIVE,
            is_primary=True,
            start_date=self.today,
        )
        counts_before = {
            "role_assignment": ChurchStructureUnitRoleAssignment.objects.count(),
            "membership": ChurchStructureMembership.objects.count(),
            "church_role": ChurchRoleAssignment.objects.count(),
            "team_assignment": TeamAssignment.objects.count(),
            "team_member": TeamAssignmentMember.objects.count(),
            "meeting_role": BibleStudyMeetingRole.objects.count(),
        }
        self._staff_login("ux_boundary")
        response = self.client.get(
            self.url + "?lang=en&q=Alpha&attention=1&missing_required=1"
        )
        self.assertEqual(response.status_code, 200)
        counts_after = {
            "role_assignment": ChurchStructureUnitRoleAssignment.objects.count(),
            "membership": ChurchStructureMembership.objects.count(),
            "church_role": ChurchRoleAssignment.objects.count(),
            "team_assignment": TeamAssignment.objects.count(),
            "team_member": TeamAssignmentMember.objects.count(),
            "meeting_role": BibleStudyMeetingRole.objects.count(),
        }
        self.assertEqual(counts_before, counts_after)


class ServingReadinessCoworkerWarningIntegrationTests(TestCase):
    """SERVING-READINESS.1C readiness warnings on coworker-add surfaces.

    Covers the delegated My Units add (``add_my_unit_coworker_assignment``) and the
    staff Church Structure add (``add_structure_unit_coworker_assignment``).
    Warnings are advisory and warning-only: the assignment row is always created,
    no readiness state hard-blocks the save, and ordinary users never see them.
    """

    def setUp(self):
        self.today = timezone.localdate()
        self.lead_role = ChurchStructureUnitRoleType.objects.create(
            code=ChurchStructureUnitRoleType.CODE_LEAD,
            name="负责人",
            name_en="Lead",
        )
        self.edify_role = ChurchStructureUnitRoleType.objects.create(
            code=ChurchStructureUnitRoleType.CODE_EDIFY,
            name="带查经同工",
            name_en="Edify",
        )
        self.group = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="SRW-GROUP",
            name="小组",
            name_en="Group",
        )
        self.candidate = User.objects.create_user(username="srw_candidate")
        ChurchStructureMembership.objects.create(
            user=self.candidate,
            unit=self.group,
            status=ChurchStructureMembership.STATUS_ACTIVE,
            is_primary=True,
            start_date=self.today,
        )

    # --- helpers ---------------------------------------------------------------

    def _seed_policy(self):
        call_command(
            "seed_serving_readiness_policies", "--apply", stdout=StringIO()
        )

    def _make_record(self, user, **kwargs):
        return ChurchMemberRecord.objects.create(user=user, **kwargs)

    def _readiness_messages(self, response):
        return [
            message.message
            for message in get_messages(response.wsgi_request)
            if "Serving readiness warning" in message.message
            or "服事预备提醒" in message.message
        ]

    def _login_group_lead(self, username="srw_lead"):
        user = User.objects.create_user(username=username, password="pw")
        ChurchStructureUnitRoleAssignment.objects.create(
            unit=self.group,
            role_type=self.lead_role,
            user=user,
            start_date=self.today,
        )
        self.client.login(username=username, password="pw")
        return user

    def _login_superuser(self, username="srw_staff"):
        User.objects.create_superuser(
            username=username, email=f"{username}@example.com", password="pw"
        )
        self.client.login(username=username, password="pw")

    def _my_units_add(self):
        return self.client.post(
            reverse("add_my_unit_coworker_assignment", args=[self.group.id])
            + "?lang=en",
            {
                "role_type": self.edify_role.id,
                "user": self.candidate.id,
                "start_date": self.today.isoformat(),
            },
        )

    def _staff_add(self):
        return self.client.post(
            reverse("add_structure_unit_coworker_assignment", args=[self.group.id])
            + "?lang=en",
            {
                "role_type": self.edify_role.id,
                "user": self.candidate.id,
                "start_date": self.today.isoformat(),
            },
        )

    def _assignment_exists(self):
        return ChurchStructureUnitRoleAssignment.objects.filter(
            unit=self.group,
            role_type=self.edify_role,
            user=self.candidate,
            is_active=True,
        ).exists()

    # --- My Units delegated add ------------------------------------------------

    def test_my_units_ready_user_saves_without_readiness_warning(self):
        self._seed_policy()
        self._make_record(
            self.candidate,
            faith_statement_status=ChurchMemberRecord.FAITH_STATEMENT_SIGNED,
            baptism_status=ChurchMemberRecord.BAPTISM_BAPTIZED,
        )
        self._login_group_lead()
        response = self._my_units_add()
        self.assertEqual(response.status_code, 302)
        self.assertTrue(self._assignment_exists())
        self.assertEqual(self._readiness_messages(response), [])

    def test_my_units_no_member_record_saves_with_warning(self):
        self._seed_policy()
        self._login_group_lead()
        response = self._my_units_add()
        self.assertTrue(self._assignment_exists())
        messages = self._readiness_messages(response)
        self.assertTrue(messages)
        self.assertIn("No church member record is on file", " ".join(messages))

    def test_my_units_declined_faith_statement_saves_with_warning(self):
        self._seed_policy()
        self._make_record(
            self.candidate,
            faith_statement_status=ChurchMemberRecord.FAITH_STATEMENT_DECLINED,
            baptism_status=ChurchMemberRecord.BAPTISM_BAPTIZED,
        )
        self._login_group_lead()
        response = self._my_units_add()
        self.assertTrue(self._assignment_exists())
        self.assertIn(
            "Faith Statement is not signed or confirmed.",
            " ".join(self._readiness_messages(response)),
        )

    def test_my_units_not_baptized_saves_with_warning(self):
        self._seed_policy()
        self._make_record(
            self.candidate,
            faith_statement_status=ChurchMemberRecord.FAITH_STATEMENT_SIGNED,
            baptism_status=ChurchMemberRecord.BAPTISM_NOT_BAPTIZED,
        )
        self._login_group_lead()
        response = self._my_units_add()
        self.assertTrue(self._assignment_exists())
        self.assertIn(
            "No baptism or recognized baptism record.",
            " ".join(self._readiness_messages(response)),
        )

    def test_my_units_non_staff_lead_sees_warning_after_authorized_add(self):
        self._seed_policy()
        lead = self._login_group_lead()
        self.assertFalse(lead.is_staff)
        response = self._my_units_add()
        self.assertTrue(self._assignment_exists())
        self.assertTrue(self._readiness_messages(response))

    def test_my_units_warning_does_not_expose_admin_or_record_links(self):
        self._seed_policy()
        self._login_group_lead()
        response = self._my_units_add()
        joined = " ".join(self._readiness_messages(response))
        self.assertTrue(joined)
        self.assertNotIn("/admin/", joined)
        self.assertNotIn("churchmemberrecord", joined.lower())

    def test_my_units_no_policy_saves_without_warning(self):
        self._login_group_lead()
        response = self._my_units_add()
        self.assertTrue(self._assignment_exists())
        self.assertEqual(self._readiness_messages(response), [])

    def test_my_units_warning_does_not_create_member_record(self):
        self._seed_policy()
        self._login_group_lead()
        before = ChurchMemberRecord.objects.count()
        self._my_units_add()
        self.assertEqual(ChurchMemberRecord.objects.count(), before)

    # --- Staff Church Structure add --------------------------------------------

    def test_staff_add_saves_with_warning_for_unready_user(self):
        self._seed_policy()
        self._login_superuser()
        response = self._staff_add()
        self.assertEqual(response.status_code, 302)
        self.assertTrue(self._assignment_exists())
        self.assertTrue(self._readiness_messages(response))

    def test_staff_add_saves_without_warning_for_ready_user(self):
        self._seed_policy()
        self._make_record(
            self.candidate,
            faith_statement_status=ChurchMemberRecord.FAITH_STATEMENT_SIGNED,
            baptism_status=ChurchMemberRecord.BAPTISM_BAPTIZED,
        )
        self._login_superuser()
        response = self._staff_add()
        self.assertTrue(self._assignment_exists())
        self.assertEqual(self._readiness_messages(response), [])

    def test_staff_add_no_policy_preserves_previous_behavior(self):
        self._login_superuser()
        response = self._staff_add()
        self.assertTrue(self._assignment_exists())
        self.assertEqual(self._readiness_messages(response), [])


class ChurchMemberRecordModelTests(TestCase):
    """MEMBER-RECORD.1B global member fact record model foundation."""

    def setUp(self):
        self.user = User.objects.create_user(username="member_record_user")

    def test_can_create_with_default_statuses(self):
        record = ChurchMemberRecord.objects.create(user=self.user)
        self.assertEqual(
            record.faith_statement_status,
            ChurchMemberRecord.FAITH_STATEMENT_UNKNOWN,
        )
        self.assertEqual(record.baptism_status, ChurchMemberRecord.BAPTISM_UNKNOWN)
        self.assertEqual(record.faith_statement_status, "unknown")
        self.assertEqual(record.baptism_status, "unknown")

    def test_one_to_one_uniqueness_prevents_duplicate_records(self):
        ChurchMemberRecord.objects.create(user=self.user)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ChurchMemberRecord.objects.create(user=self.user)

    def test_faith_statement_status_choices_cover_required_values(self):
        codes = {code for code, _ in ChurchMemberRecord.FAITH_STATEMENT_STATUS_CHOICES}
        self.assertEqual(
            codes,
            {
                "unknown",
                "not_started",
                "sent_pending_signature",
                "signed",
                "waived",
                "declined",
                "not_required",
            },
        )
        # Course/class progress must not be encoded into the Faith Statement field.
        self.assertNotIn("class_completed_pending_signature", codes)

    def test_baptism_status_choices_cover_required_values(self):
        codes = {code for code, _ in ChurchMemberRecord.BAPTISM_STATUS_CHOICES}
        self.assertEqual(
            codes,
            {
                "unknown",
                "not_baptized",
                "baptized",
                "recognized",
                "waived",
                "not_required",
            },
        )

    def test_faith_statement_status_field_present_and_faith_status_absent(self):
        self.assertIsNotNone(
            ChurchMemberRecord._meta.get_field("faith_statement_status")
        )
        with self.assertRaises(FieldDoesNotExist):
            ChurchMemberRecord._meta.get_field("faith_status")

    def test_course_training_status_fields_absent(self):
        for field_name in ("membership_class_status", "c201_status", "course_status"):
            with self.assertRaises(FieldDoesNotExist):
                ChurchMemberRecord._meta.get_field(field_name)

    def test_nullable_dates_can_be_blank(self):
        record = ChurchMemberRecord.objects.create(user=self.user)
        self.assertIsNone(record.faith_statement_signed_date)
        self.assertIsNone(record.baptism_date)

    def test_notes_help_text_warns_against_sensitive_information(self):
        help_text = ChurchMemberRecord._meta.get_field("notes").help_text
        self.assertIn("Operational membership notes only", help_text)
        self.assertIn("counseling", help_text)
        self.assertIn("medical", help_text)
        self.assertIn("financial", help_text)
        self.assertIn("immigration", help_text)

    def test_status_label_helpers_are_bilingual(self):
        record = ChurchMemberRecord.objects.create(
            user=self.user,
            faith_statement_status=ChurchMemberRecord.FAITH_STATEMENT_SIGNED,
            baptism_status=ChurchMemberRecord.BAPTISM_BAPTIZED,
        )
        self.assertEqual(record.faith_statement_status_label("en"), "Signed")
        self.assertEqual(record.faith_statement_status_label("zh"), "已签署")
        self.assertEqual(record.baptism_status_label("en"), "Baptized")
        self.assertEqual(record.baptism_status_label("zh"), "已受浸")

    def test_creating_record_does_not_create_belonging_serving_or_role_rows(self):
        before = {
            "membership": ChurchStructureMembership.objects.count(),
            "unit_role": ChurchStructureUnitRoleAssignment.objects.count(),
            "church_role": ChurchRoleAssignment.objects.count(),
            "team_assignment": TeamAssignment.objects.count(),
            "team_assignment_member": TeamAssignmentMember.objects.count(),
            "bs_meeting_role": BibleStudyMeetingRole.objects.count(),
        }
        ChurchMemberRecord.objects.create(
            user=self.user,
            faith_statement_status=ChurchMemberRecord.FAITH_STATEMENT_SIGNED,
            baptism_status=ChurchMemberRecord.BAPTISM_BAPTIZED,
        )
        self.assertEqual(
            ChurchStructureMembership.objects.count(), before["membership"]
        )
        self.assertEqual(
            ChurchStructureUnitRoleAssignment.objects.count(), before["unit_role"]
        )
        self.assertEqual(ChurchRoleAssignment.objects.count(), before["church_role"])
        self.assertEqual(TeamAssignment.objects.count(), before["team_assignment"])
        self.assertEqual(
            TeamAssignmentMember.objects.count(), before["team_assignment_member"]
        )
        self.assertEqual(
            BibleStudyMeetingRole.objects.count(), before["bs_meeting_role"]
        )

    def test_creating_record_does_not_grant_permissions(self):
        ChurchMemberRecord.objects.create(
            user=self.user,
            faith_statement_status=ChurchMemberRecord.FAITH_STATEMENT_SIGNED,
            baptism_status=ChurchMemberRecord.BAPTISM_BAPTIZED,
        )
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_staff)
        self.assertFalse(self.user.is_superuser)

    def test_no_stored_serving_readiness_field_or_property(self):
        record = ChurchMemberRecord.objects.create(user=self.user)
        for name in ("eligible_for_formal_serving", "is_ready_to_serve"):
            with self.assertRaises(FieldDoesNotExist):
                ChurchMemberRecord._meta.get_field(name)
            self.assertFalse(hasattr(record, name))


class ChurchMemberRecordAdminTests(TestCase):
    """MEMBER-RECORD.1B admin registration and clarity wording."""

    def setUp(self):
        self.admin_user = User.objects.create_superuser(
            username="member_record_admin",
            email="member_record_admin@example.com",
            password="AdminPass123!",
        )
        self.client.login(username="member_record_admin", password="AdminPass123!")

    def test_change_page_renders_member_record(self):
        member = User.objects.create_user(username="rendered_member")
        record = ChurchMemberRecord.objects.create(user=member)
        response = self.client.get(
            reverse("admin:accounts_churchmemberrecord_change", args=[record.pk])
        )
        self.assertEqual(response.status_code, 200)

    def test_changelist_renders(self):
        response = self.client.get(
            reverse("admin:accounts_churchmemberrecord_changelist")
        )
        self.assertEqual(response.status_code, 200)

    def test_admin_note_distinguishes_facts_courses_belonging_serving_readiness(self):
        member = User.objects.create_user(username="noted_member")
        record = ChurchMemberRecord.objects.create(user=member)
        response = self.client.get(
            reverse("admin:accounts_churchmemberrecord_change", args=[record.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Church Member Record")
        self.assertContains(response, "教会成员记录")
        # member facts only in V1
        self.assertContains(response, "Faith Statement")
        self.assertContains(response, "baptism facts only")
        # course/training progress deferred to a future module
        self.assertContains(response, "future course/training")
        self.assertContains(response, "认识我们的教会")
        # belonging vs serving distinction
        self.assertContains(response, "Belonging remains ChurchStructureMembership")
        self.assertContains(response, "TeamAssignmentMember / BibleStudyMeetingRole")
        # future configurable readiness, never a stored boolean
        self.assertContains(response, "warning-only policy")
        self.assertContains(response, "never a stored boolean")


class ChurchStructureUnitMemberRecordModelTests(TestCase):
    """MEMBER-RECORD.1C unit-specific operational/care record model foundation.

    The record is admin-only operational/care data. It is NOT belonging
    (ChurchStructureMembership), NOT a global member fact (ChurchMemberRecord),
    NOT serving (TeamAssignmentMember / BibleStudyMeetingRole), and never grants
    membership, serving, audience visibility, permissions, or management rights.
    """

    def setUp(self):
        self.user = User.objects.create_user(username="unit_record_user")
        self.unit = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="UMR-GROUP",
            name="单元记录组",
            name_en="Unit Record Group",
        )

    def test_can_create_unit_member_record(self):
        record = ChurchStructureUnitMemberRecord.objects.create(
            unit=self.unit, user=self.user
        )
        self.assertEqual(record.unit, self.unit)
        self.assertEqual(record.user, self.user)
        self.assertIsNone(record.joined_unit_date)
        self.assertEqual(record.group_notes, "")
        self.assertEqual(record.care_followup_notes, "")

    def test_default_attendance_state_is_unknown(self):
        record = ChurchStructureUnitMemberRecord.objects.create(
            unit=self.unit, user=self.user
        )
        self.assertEqual(
            record.attendance_state,
            ChurchStructureUnitMemberRecord.ATTENDANCE_UNKNOWN,
        )
        self.assertEqual(record.attendance_state, "unknown")

    def test_attendance_state_choices_cover_required_values(self):
        codes = {
            code
            for code, _ in ChurchStructureUnitMemberRecord.ATTENDANCE_STATE_CHOICES
        }
        self.assertEqual(
            codes,
            {
                "unknown",
                "active",
                "unstable_attendee",
                "inactive",
                "no_longer_comes",
                "graduated",
                "moved",
                "visitor",
                "other",
            },
        )

    def test_unique_unit_user_prevents_duplicate_records(self):
        ChurchStructureUnitMemberRecord.objects.create(
            unit=self.unit, user=self.user
        )
        with self.assertRaises(ValidationError):
            ChurchStructureUnitMemberRecord.objects.create(
                unit=self.unit, user=self.user
            )

    def test_same_user_can_have_records_in_different_units(self):
        other_unit = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="UMR-GROUP-2",
            name="另一组",
            name_en="Other Group",
        )
        ChurchStructureUnitMemberRecord.objects.create(
            unit=self.unit, user=self.user
        )
        record = ChurchStructureUnitMemberRecord.objects.create(
            unit=other_unit, user=self.user
        )
        self.assertEqual(record.unit, other_unit)

    def test_inactive_unit_is_rejected(self):
        self.unit.is_active = False
        self.unit.save()
        with self.assertRaises(ValidationError):
            ChurchStructureUnitMemberRecord.objects.create(
                unit=self.unit, user=self.user
            )

    def test_inactive_user_is_rejected(self):
        self.user.is_active = False
        self.user.save()
        with self.assertRaises(ValidationError):
            ChurchStructureUnitMemberRecord.objects.create(
                unit=self.unit, user=self.user
            )

    def test_joined_unit_date_can_be_blank(self):
        record = ChurchStructureUnitMemberRecord.objects.create(
            unit=self.unit, user=self.user
        )
        self.assertIsNone(record.joined_unit_date)

    def test_group_notes_help_text_warns_about_sensitive_data(self):
        help_text = ChurchStructureUnitMemberRecord._meta.get_field(
            "group_notes"
        ).help_text
        self.assertIn("Unit-local operational notes only", help_text)
        self.assertIn("counseling", help_text)
        self.assertIn("medical", help_text)
        self.assertIn("financial", help_text)
        self.assertIn("immigration", help_text)

    def test_care_followup_notes_help_text_warns_about_sensitive_data(self):
        help_text = ChurchStructureUnitMemberRecord._meta.get_field(
            "care_followup_notes"
        ).help_text
        self.assertIn("Restricted care/follow-up notes", help_text)
        self.assertIn("sensitive", help_text)
        self.assertIn("delegated leads", help_text)

    def test_display_helpers_are_bilingual(self):
        record = ChurchStructureUnitMemberRecord.objects.create(
            unit=self.unit,
            user=self.user,
            attendance_state=ChurchStructureUnitMemberRecord.ATTENDANCE_ACTIVE,
        )
        self.assertEqual(record.display_attendance_state("en"), "Active")
        self.assertEqual(record.display_attendance_state("zh"), "稳定参加")
        self.assertEqual(record.unit_path_label("en"), "Unit Record Group")
        self.assertEqual(record.unit_path_label("zh"), "单元记录组")

    def test_no_membership_or_management_inference_helpers(self):
        record = ChurchStructureUnitMemberRecord.objects.create(
            unit=self.unit, user=self.user
        )
        for name in (
            "can_manage",
            "is_member",
            "is_serving",
            "is_ready_to_serve",
        ):
            self.assertFalse(hasattr(record, name))

    def test_creating_record_does_not_create_belonging_serving_or_facts(self):
        before = {
            "membership": ChurchStructureMembership.objects.count(),
            "unit_role": ChurchStructureUnitRoleAssignment.objects.count(),
            "church_role": ChurchRoleAssignment.objects.count(),
            "team_assignment": TeamAssignment.objects.count(),
            "team_assignment_member": TeamAssignmentMember.objects.count(),
            "bs_meeting_role": BibleStudyMeetingRole.objects.count(),
            "member_record": ChurchMemberRecord.objects.count(),
        }
        ChurchStructureUnitMemberRecord.objects.create(
            unit=self.unit,
            user=self.user,
            attendance_state=ChurchStructureUnitMemberRecord.ATTENDANCE_ACTIVE,
        )
        self.assertEqual(
            ChurchStructureMembership.objects.count(), before["membership"]
        )
        self.assertEqual(
            ChurchStructureUnitRoleAssignment.objects.count(), before["unit_role"]
        )
        self.assertEqual(ChurchRoleAssignment.objects.count(), before["church_role"])
        self.assertEqual(TeamAssignment.objects.count(), before["team_assignment"])
        self.assertEqual(
            TeamAssignmentMember.objects.count(), before["team_assignment_member"]
        )
        self.assertEqual(
            BibleStudyMeetingRole.objects.count(), before["bs_meeting_role"]
        )
        self.assertEqual(
            ChurchMemberRecord.objects.count(), before["member_record"]
        )

    def test_creating_record_does_not_grant_permissions(self):
        ChurchStructureUnitMemberRecord.objects.create(
            unit=self.unit, user=self.user
        )
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_staff)
        self.assertFalse(self.user.is_superuser)
        self.assertFalse(has_capability(self.user, CAP_MANAGE_CHURCH_MEMBERSHIPS))


class ChurchStructureUnitMemberRecordBoundaryTests(TestCase):
    """MEMBER-RECORD.1C: a unit member record never grants belonging-derived
    visibility or serving. It must not make zero-row ServiceEvents visible, must
    not appear in My Serving, must not affect Today, and must not affect Bible
    Study meeting visibility candidacy."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="umr_boundary_user", password="pw"
        )
        self.unit = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="UMR-BND",
            name="边界组",
            name_en="Boundary Group",
        )
        # The record alone must not behave like membership/serving anywhere.
        self.record = ChurchStructureUnitMemberRecord.objects.create(
            unit=self.unit,
            user=self.user,
            attendance_state=ChurchStructureUnitMemberRecord.ATTENDANCE_ACTIVE,
        )

    def test_record_does_not_make_zero_row_service_event_visible(self):
        event = ServiceEvent.objects.create(
            title="Zero-row Service",
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
            start_datetime=timezone.now() + timezone.timedelta(days=3),
            status=ServiceEvent.STATUS_PUBLISHED,
        )
        # No audience scope rows: ordinary users fail closed.
        self.assertEqual(event.audience_scope_links.count(), 0)
        self.assertFalse(event.can_be_seen_by(self.user))
        visible_ids = set(
            get_visible_service_events(self.user).values_list("id", flat=True)
        )
        self.assertNotIn(event.id, visible_ids)

    def test_record_does_not_appear_in_my_serving(self):
        self.assertEqual(my_serving_assignments(self.user, tab="upcoming"), [])
        self.assertEqual(my_serving_assignments(self.user, tab="past"), [])

    def test_record_does_not_affect_today_serving_summary(self):
        self.assertIsNone(get_today_serving_summary(self.user))

    def test_record_does_not_grant_bible_study_audience_candidacy(self):
        # Without a single active primary membership, the record gives no Bible
        # Study audience candidacy (the Today/landing pre-filter feeder).
        self.assertEqual(
            get_membership_audience_candidate_unit_ids(self.user), []
        )


class ChurchStructureUnitMemberRecordAdminTests(TestCase):
    """MEMBER-RECORD.1C admin registration and clarity wording (admin-only)."""

    def setUp(self):
        self.admin_user = User.objects.create_superuser(
            username="unit_record_admin",
            email="unit_record_admin@example.com",
            password="AdminPass123!",
        )
        self.client.login(username="unit_record_admin", password="AdminPass123!")
        self.user = User.objects.create_user(username="unit_record_member")
        self.unit = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="UMR-ADMIN",
            name="管理组",
            name_en="Admin Group",
        )
        self.record = ChurchStructureUnitMemberRecord.objects.create(
            unit=self.unit, user=self.user
        )

    def test_changelist_renders(self):
        response = self.client.get(
            reverse("admin:accounts_churchstructureunitmemberrecord_changelist")
        )
        self.assertEqual(response.status_code, 200)

    def test_change_page_renders(self):
        response = self.client.get(
            reverse(
                "admin:accounts_churchstructureunitmemberrecord_change",
                args=[self.record.pk],
            )
        )
        self.assertEqual(response.status_code, 200)

    def test_admin_note_distinguishes_record_belonging_facts_serving_privacy(self):
        response = self.client.get(
            reverse(
                "admin:accounts_churchstructureunitmemberrecord_change",
                args=[self.record.pk],
            )
        )
        self.assertEqual(response.status_code, 200)
        # unit member/care record
        self.assertContains(response, "Unit Member Record")
        self.assertContains(response, "单元成员记录")
        # canonical belonging
        self.assertContains(response, "ChurchStructureMembership")
        # global member facts
        self.assertContains(response, "ChurchMemberRecord")
        # serving assignments
        self.assertContains(response, "TeamAssignmentMember / BibleStudyMeetingRole")
        # privacy boundary
        self.assertContains(response, "care_followup_notes")
        self.assertContains(response, "admin-only for now")
        self.assertContains(response, "delegated unit")


class ChurchStructureUnitMemberRecordUiBoundaryTests(TestCase):
    """MEMBER-RECORD.1C: no non-admin UI exposes unit member/care records.

    This slice adds no ordinary-user / My Units / My Serving / Today UI. A
    delegated lead and an ordinary member must not see member-record fields or
    care notes on their existing surfaces.
    """

    # Field-name / care markers that must never leak onto non-admin surfaces.
    LEAK_MARKERS = (
        "care_followup_notes",
        "attendance_state",
        "joined_unit_date",
        "structure_unit_member_records",
    )

    def setUp(self):
        self.lead_role = ChurchStructureUnitRoleType.objects.create(
            code=ChurchStructureUnitRoleType.CODE_LEAD,
            name="负责人",
            name_en="Lead",
        )
        self.unit = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="UMR-UI",
            name="界面组",
            name_en="UI Group",
        )
        self.member = User.objects.create_user(
            username="umr_ui_member", password="pw"
        )
        # A care record exists, with sensitive notes, for the member.
        self.record = ChurchStructureUnitMemberRecord.objects.create(
            unit=self.unit,
            user=self.member,
            attendance_state=ChurchStructureUnitMemberRecord.ATTENDANCE_ACTIVE,
            group_notes="SENSITIVE-GROUP-NOTE",
            care_followup_notes="SENSITIVE-CARE-NOTE",
        )

    def _assert_no_leak(self, response):
        self.assertNotContains(response, "SENSITIVE-GROUP-NOTE")
        self.assertNotContains(response, "SENSITIVE-CARE-NOTE")
        for marker in self.LEAK_MARKERS:
            self.assertNotContains(response, marker)

    def test_delegated_lead_my_units_list_has_no_member_record_ui(self):
        lead = User.objects.create_user(username="umr_ui_lead", password="pw")
        ChurchStructureUnitRoleAssignment.objects.create(
            unit=self.unit, role_type=self.lead_role, user=lead
        )
        self.client.login(username="umr_ui_lead", password="pw")
        # The compact My Units LIST page never exposes member/care records.
        list_response = self.client.get(reverse("my_units") + "?lang=en")
        self.assertEqual(list_response.status_code, 200)
        self._assert_no_leak(list_response)
        # MEMBER-RECORD.1E: the DETAIL page now shows a read-only member/care
        # section to delegated leads at the operational tier (group notes yes,
        # restricted care notes no). Internal field-name markers still never leak.
        detail_response = self.client.get(
            reverse("my_unit_detail", args=[self.unit.id]) + "?lang=en"
        )
        self.assertEqual(detail_response.status_code, 200)
        self.assertContains(detail_response, "Unit Member / Care Records")
        self.assertContains(detail_response, "SENSITIVE-GROUP-NOTE")
        self.assertNotContains(detail_response, "SENSITIVE-CARE-NOTE")
        self.assertNotContains(detail_response, "care_followup_notes")
        self.assertNotContains(detail_response, "structure_unit_member_records")

    def test_ordinary_profile_page_has_no_member_record_fields(self):
        self.client.login(username="umr_ui_member", password="pw")
        response = self.client.get(reverse("profile") + "?lang=en")
        self.assertEqual(response.status_code, 200)
        self._assert_no_leak(response)


class UnitMemberRecordAccessHelperTests(TestCase):
    """MEMBER-RECORD.1D privacy/access helper foundation (read-only).

    Defines who may read which field tier of a ``ChurchStructureUnitMemberRecord``:
    NONE / SELF_BASIC / UNIT_LEAD_OPERATIONAL / ADMIN_FULL. The helper is a
    privacy contract only — it adds no non-admin UI, grants no permission, and
    never infers belonging or serving. Lead (operational) access comes ONLY from
    an explicit active ``lead`` ancestor-or-self coworker role; membership,
    non-lead coworker roles, and serving never grant access.
    """

    def setUp(self):
        self.today = timezone.localdate()
        self.lead_role = ChurchStructureUnitRoleType.objects.create(
            code=ChurchStructureUnitRoleType.CODE_LEAD, name="负责人", name_en="Lead"
        )
        self.edify_role = ChurchStructureUnitRoleType.objects.create(
            code=ChurchStructureUnitRoleType.CODE_EDIFY,
            name="带查经同工",
            name_en="Edify",
        )
        self.worship_role = ChurchStructureUnitRoleType.objects.create(
            code=ChurchStructureUnitRoleType.CODE_WORSHIP,
            name="敬拜同工",
            name_en="Worship",
        )
        self.caring_role = ChurchStructureUnitRoleType.objects.create(
            code=ChurchStructureUnitRoleType.CODE_CARING,
            name="关怀同工",
            name_en="Caring",
        )

        # district -> group(record unit) -> nested, plus an unrelated branch.
        self.district = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_DISTRICT,
            code="UMRA-DISTRICT",
            name="访问区",
            name_en="Access District",
        )
        self.group = ChurchStructureUnit.objects.create(
            parent=self.district,
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="UMRA-GROUP",
            name="访问组",
            name_en="Access Group",
        )
        self.nested = ChurchStructureUnit.objects.create(
            parent=self.group,
            unit_type=ChurchStructureUnit.UNIT_CUSTOM,
            code="UMRA-NESTED",
            name="访问子单元",
            name_en="Access Nested",
        )
        self.other_branch = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="UMRA-OTHER",
            name="无关组",
            name_en="Unrelated Group",
        )

        self.member = User.objects.create_user(
            username="umra_member", first_name="Mem", last_name="Ber"
        )
        self.record = ChurchStructureUnitMemberRecord.objects.create(
            unit=self.group,
            user=self.member,
            attendance_state=ChurchStructureUnitMemberRecord.ATTENDANCE_ACTIVE,
            joined_unit_date=self.today - timedelta(days=10),
            group_notes="GROUP-NOTE-XYZ",
            care_followup_notes="CARE-NOTE-XYZ",
        )

    def _lead(self, user, unit, **kwargs):
        return ChurchStructureUnitRoleAssignment.objects.create(
            unit=unit, role_type=self.lead_role, user=user, **kwargs
        )

    def _coworker(self, user, unit, role_type, **kwargs):
        return ChurchStructureUnitRoleAssignment.objects.create(
            unit=unit, role_type=role_type, user=user, **kwargs
        )

    def _active_primary_membership(self, user, unit):
        return ChurchStructureMembership.objects.create(
            user=user,
            unit=unit,
            status=ChurchStructureMembership.STATUS_ACTIVE,
            is_primary=True,
            start_date=self.today,
        )

    # --- access tier ---------------------------------------------------------

    def test_anonymous_user_gets_none(self):
        self.assertEqual(
            get_unit_member_record_access_tier(AnonymousUser(), self.record),
            UNIT_MEMBER_RECORD_ACCESS_NONE,
        )

    def test_none_record_gets_none(self):
        user = User.objects.create_user(username="umra_norecord")
        self.assertEqual(
            get_unit_member_record_access_tier(user, None),
            UNIT_MEMBER_RECORD_ACCESS_NONE,
        )

    def test_unrelated_regular_user_gets_none(self):
        user = User.objects.create_user(username="umra_unrelated")
        self.assertEqual(
            get_unit_member_record_access_tier(user, self.record),
            UNIT_MEMBER_RECORD_ACCESS_NONE,
        )

    def test_membership_only_user_gets_none(self):
        user = User.objects.create_user(username="umra_membership_only")
        self._active_primary_membership(user, self.group)
        self.assertEqual(
            get_unit_member_record_access_tier(user, self.record),
            UNIT_MEMBER_RECORD_ACCESS_NONE,
        )

    def test_requested_membership_user_gets_none(self):
        user = User.objects.create_user(username="umra_requested")
        ChurchStructureMembership.objects.create(
            user=user,
            unit=self.group,
            status=ChurchStructureMembership.STATUS_REQUESTED,
            is_primary=True,
            start_date=self.today,
        )
        self.assertEqual(
            get_unit_member_record_access_tier(user, self.record),
            UNIT_MEMBER_RECORD_ACCESS_NONE,
        )

    def test_non_lead_coworker_on_same_unit_gets_none(self):
        # edify / worship / caring coworkers on the record's unit get nothing.
        for role_type, username in (
            (self.edify_role, "umra_edify"),
            (self.worship_role, "umra_worship"),
            (self.caring_role, "umra_caring"),
        ):
            user = User.objects.create_user(username=username)
            self._coworker(user, self.group, role_type)
            self.assertEqual(
                get_unit_member_record_access_tier(user, self.record),
                UNIT_MEMBER_RECORD_ACCESS_NONE,
                f"{username} must not gain access",
            )

    def test_team_membership_user_gets_none(self):
        user = User.objects.create_user(username="umra_team_member")
        team = MinistryTeam.objects.create(name="UMRA Team")
        TeamMembership.objects.create(team=team, user=user)
        self.assertEqual(
            get_unit_member_record_access_tier(user, self.record),
            UNIT_MEMBER_RECORD_ACCESS_NONE,
        )

    def test_team_assignment_member_user_gets_none(self):
        user = User.objects.create_user(username="umra_team_assignment")
        team = MinistryTeam.objects.create(name="UMRA Assign Team")
        membership = TeamMembership.objects.create(team=team, user=user)
        event = ServiceEvent.objects.create(
            title="UMRA Event",
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
            start_datetime=timezone.now() + timedelta(days=2),
            status=ServiceEvent.STATUS_PUBLISHED,
        )
        assignment = TeamAssignment.objects.create(
            service_event=event,
            ministry_team=team,
            status=TeamAssignment.STATUS_SCHEDULED,
        )
        TeamAssignmentMember.objects.create(
            assignment=assignment, membership=membership
        )
        self.assertEqual(
            get_unit_member_record_access_tier(user, self.record),
            UNIT_MEMBER_RECORD_ACCESS_NONE,
        )

    def test_bible_study_meeting_role_user_gets_none(self):
        user = User.objects.create_user(username="umra_bs_role")
        series = BibleStudySeries.objects.create(
            title="UMRA 查经", title_en="UMRA Study"
        )
        lesson = BibleStudyLesson.objects.create(
            series=series, title="UMRA 课", lesson_date=self.today
        )
        meeting = BibleStudyMeeting.objects.create(
            lesson=lesson,
            anchor_unit=self.group,
            meeting_datetime=timezone.now() + timedelta(days=2),
            status=BibleStudyMeeting.STATUS_PUBLISHED,
        )
        BibleStudyMeetingRole.objects.create(
            meeting=meeting,
            role=BibleStudyMeetingRole.ROLE_DISCUSSION_LEADER,
            user=user,
        )
        self.assertEqual(
            get_unit_member_record_access_tier(user, self.record),
            UNIT_MEMBER_RECORD_ACCESS_NONE,
        )

    def test_record_own_user_gets_self_basic(self):
        self.assertEqual(
            get_unit_member_record_access_tier(self.member, self.record),
            UNIT_MEMBER_RECORD_ACCESS_SELF_BASIC,
        )

    def test_active_lead_on_same_unit_gets_unit_lead_operational(self):
        user = User.objects.create_user(username="umra_group_lead")
        self._lead(user, self.group)
        self.assertEqual(
            get_unit_member_record_access_tier(user, self.record),
            UNIT_MEMBER_RECORD_ACCESS_UNIT_LEAD_OPERATIONAL,
        )

    def test_active_lead_on_ancestor_unit_gets_unit_lead_operational(self):
        user = User.objects.create_user(username="umra_district_lead")
        self._lead(user, self.district)
        self.assertEqual(
            get_unit_member_record_access_tier(user, self.record),
            UNIT_MEMBER_RECORD_ACCESS_UNIT_LEAD_OPERATIONAL,
        )

    def test_lead_on_unrelated_branch_gets_none(self):
        user = User.objects.create_user(username="umra_other_lead")
        self._lead(user, self.other_branch)
        self.assertEqual(
            get_unit_member_record_access_tier(user, self.record),
            UNIT_MEMBER_RECORD_ACCESS_NONE,
        )

    def test_lead_on_descendant_unit_gets_none(self):
        # A lead of the nested child does not lead the parent group's record.
        user = User.objects.create_user(username="umra_nested_lead")
        self._lead(user, self.nested)
        self.assertEqual(
            get_unit_member_record_access_tier(user, self.record),
            UNIT_MEMBER_RECORD_ACCESS_NONE,
        )

    def test_inactive_lead_assignment_gets_none(self):
        user = User.objects.create_user(username="umra_inactive_lead")
        self._lead(user, self.group, is_active=False)
        self.assertEqual(
            get_unit_member_record_access_tier(user, self.record),
            UNIT_MEMBER_RECORD_ACCESS_NONE,
        )

    def test_ended_lead_assignment_gets_none(self):
        user = User.objects.create_user(username="umra_ended_lead")
        self._lead(
            user,
            self.group,
            start_date=self.today - timedelta(days=30),
            end_date=self.today - timedelta(days=1),
        )
        self.assertEqual(
            get_unit_member_record_access_tier(user, self.record),
            UNIT_MEMBER_RECORD_ACCESS_NONE,
        )

    def test_future_start_lead_assignment_gets_none(self):
        user = User.objects.create_user(username="umra_future_lead")
        self._lead(user, self.group, start_date=self.today + timedelta(days=5))
        self.assertEqual(
            get_unit_member_record_access_tier(user, self.record),
            UNIT_MEMBER_RECORD_ACCESS_NONE,
        )

    def test_staff_gets_admin_full(self):
        staff = User.objects.create_user(username="umra_staff", is_staff=True)
        self.assertEqual(
            get_unit_member_record_access_tier(staff, self.record),
            UNIT_MEMBER_RECORD_ACCESS_ADMIN_FULL,
        )

    def test_superuser_gets_admin_full(self):
        superuser = User.objects.create_superuser(
            username="umra_super", email="umra_super@example.com", password="x"
        )
        self.assertEqual(
            get_unit_member_record_access_tier(superuser, self.record),
            UNIT_MEMBER_RECORD_ACCESS_ADMIN_FULL,
        )

    def test_staff_who_owns_record_still_gets_admin_full(self):
        # Staff/superuser is distinguished before self, so the fuller tier wins.
        staff_owner = User.objects.create_user(
            username="umra_staff_owner", is_staff=True
        )
        record = ChurchStructureUnitMemberRecord.objects.create(
            unit=self.other_branch, user=staff_owner
        )
        self.assertEqual(
            get_unit_member_record_access_tier(staff_owner, record),
            UNIT_MEMBER_RECORD_ACCESS_ADMIN_FULL,
        )

    # --- boolean convenience helpers track the tier --------------------------

    def test_boolean_helpers_match_tier_grants(self):
        unrelated = User.objects.create_user(username="umra_bool_none")
        lead = User.objects.create_user(username="umra_bool_lead")
        self._lead(lead, self.group)
        staff = User.objects.create_user(username="umra_bool_staff", is_staff=True)

        # NONE
        self.assertFalse(can_view_unit_member_record_basic(unrelated, self.record))
        self.assertFalse(
            can_view_unit_member_record_group_notes(unrelated, self.record)
        )
        self.assertFalse(
            can_view_unit_member_record_care_notes(unrelated, self.record)
        )
        # SELF_BASIC
        self.assertTrue(can_view_unit_member_record_basic(self.member, self.record))
        self.assertFalse(
            can_view_unit_member_record_group_notes(self.member, self.record)
        )
        self.assertFalse(
            can_view_unit_member_record_care_notes(self.member, self.record)
        )
        # UNIT_LEAD_OPERATIONAL
        self.assertTrue(can_view_unit_member_record_basic(lead, self.record))
        self.assertTrue(can_view_unit_member_record_group_notes(lead, self.record))
        self.assertFalse(can_view_unit_member_record_care_notes(lead, self.record))
        # ADMIN_FULL
        self.assertTrue(can_view_unit_member_record_basic(staff, self.record))
        self.assertTrue(can_view_unit_member_record_group_notes(staff, self.record))
        self.assertTrue(can_view_unit_member_record_care_notes(staff, self.record))

    # --- snapshot field visibility -------------------------------------------

    def test_none_snapshot_excludes_all_person_unit_and_care_detail(self):
        unrelated = User.objects.create_user(username="umra_snap_none")
        snapshot = build_unit_member_record_safe_snapshot(
            unrelated, self.record, language="en"
        )
        self.assertEqual(snapshot["access_tier"], UNIT_MEMBER_RECORD_ACCESS_NONE)
        self.assertFalse(snapshot["can_view_basic"])
        self.assertFalse(snapshot["can_view_group_notes"])
        self.assertFalse(snapshot["can_view_care_notes"])
        for key in (
            "user_display",
            "unit_path",
            "attendance_state_display",
            "joined_unit_date",
            "group_notes",
            "care_followup_notes",
        ):
            self.assertNotIn(key, snapshot)

    def test_self_basic_snapshot_has_basic_only(self):
        snapshot = build_unit_member_record_safe_snapshot(
            self.member, self.record, language="en"
        )
        self.assertEqual(
            snapshot["access_tier"], UNIT_MEMBER_RECORD_ACCESS_SELF_BASIC
        )
        self.assertTrue(snapshot["can_view_basic"])
        self.assertEqual(snapshot["user_display"], "Mem Ber")
        self.assertEqual(snapshot["unit_path"], "Access District > Access Group")
        self.assertEqual(snapshot["attendance_state_display"], "Active")
        self.assertEqual(
            snapshot["joined_unit_date"], self.today - timedelta(days=10)
        )
        self.assertNotIn("group_notes", snapshot)
        self.assertNotIn("care_followup_notes", snapshot)

    def test_unit_lead_snapshot_has_basic_and_group_notes_only(self):
        lead = User.objects.create_user(username="umra_snap_lead")
        self._lead(lead, self.group)
        snapshot = build_unit_member_record_safe_snapshot(
            lead, self.record, language="en"
        )
        self.assertEqual(
            snapshot["access_tier"],
            UNIT_MEMBER_RECORD_ACCESS_UNIT_LEAD_OPERATIONAL,
        )
        self.assertTrue(snapshot["can_view_basic"])
        self.assertTrue(snapshot["can_view_group_notes"])
        self.assertEqual(snapshot["user_display"], "Mem Ber")
        self.assertEqual(snapshot["group_notes"], "GROUP-NOTE-XYZ")
        self.assertNotIn("care_followup_notes", snapshot)

    def test_admin_full_snapshot_has_basic_group_and_care_notes(self):
        staff = User.objects.create_user(username="umra_snap_staff", is_staff=True)
        snapshot = build_unit_member_record_safe_snapshot(
            staff, self.record, language="en"
        )
        self.assertEqual(
            snapshot["access_tier"], UNIT_MEMBER_RECORD_ACCESS_ADMIN_FULL
        )
        self.assertTrue(snapshot["can_view_care_notes"])
        self.assertEqual(snapshot["group_notes"], "GROUP-NOTE-XYZ")
        self.assertEqual(snapshot["care_followup_notes"], "CARE-NOTE-XYZ")

    def test_snapshot_localizes_basic_labels(self):
        snapshot = build_unit_member_record_safe_snapshot(
            self.member, self.record, language="zh"
        )
        self.assertEqual(snapshot["attendance_state_display"], "稳定参加")
        self.assertEqual(snapshot["unit_path"], "访问区 > 访问组")

    def test_snapshot_excludes_internal_ids_and_admin_urls(self):
        staff = User.objects.create_user(username="umra_snap_ids", is_staff=True)
        snapshot = build_unit_member_record_safe_snapshot(
            staff, self.record, language="en"
        )
        # No id-bearing keys.
        for key in snapshot:
            self.assertNotIn("_id", key)
            self.assertNotEqual(key, "id")
            self.assertNotIn("url", key.lower())
        # No raw pk values and no admin URL fragments leak into values. Skip
        # bools (in Python ``True == 1`` would spuriously match a pk of 1).
        raw_ids = {self.record.id, self.member.id, self.group.id}
        for value in snapshot.values():
            if not isinstance(value, bool):
                self.assertNotIn(value, raw_ids)
            self.assertNotIn("/admin/", str(value))

    # --- boundary: no mutation, no belonging/serving inference ----------------

    def _call_all_helpers(self, user):
        get_unit_member_record_access_tier(user, self.record)
        can_view_unit_member_record_basic(user, self.record)
        can_view_unit_member_record_group_notes(user, self.record)
        can_view_unit_member_record_care_notes(user, self.record)
        build_unit_member_record_safe_snapshot(user, self.record)

    def test_helpers_do_not_mutate_belonging_serving_or_role_rows(self):
        staff = User.objects.create_user(username="umra_nomutate", is_staff=True)
        before = {
            "membership": ChurchStructureMembership.objects.count(),
            "unit_role": ChurchStructureUnitRoleAssignment.objects.count(),
            "church_role": ChurchRoleAssignment.objects.count(),
            "team_assignment": TeamAssignment.objects.count(),
            "team_assignment_member": TeamAssignmentMember.objects.count(),
            "bs_meeting_role": BibleStudyMeetingRole.objects.count(),
            "unit_member_record": ChurchStructureUnitMemberRecord.objects.count(),
        }
        self._call_all_helpers(staff)
        self.assertEqual(
            ChurchStructureMembership.objects.count(), before["membership"]
        )
        self.assertEqual(
            ChurchStructureUnitRoleAssignment.objects.count(), before["unit_role"]
        )
        self.assertEqual(
            ChurchRoleAssignment.objects.count(), before["church_role"]
        )
        self.assertEqual(
            TeamAssignment.objects.count(), before["team_assignment"]
        )
        self.assertEqual(
            TeamAssignmentMember.objects.count(),
            before["team_assignment_member"],
        )
        self.assertEqual(
            BibleStudyMeetingRole.objects.count(), before["bs_meeting_role"]
        )
        self.assertEqual(
            ChurchStructureUnitMemberRecord.objects.count(),
            before["unit_member_record"],
        )

    def test_helpers_do_not_make_zero_row_service_event_visible(self):
        staff = User.objects.create_user(username="umra_bnd_event", is_staff=True)
        self._call_all_helpers(staff)
        event = ServiceEvent.objects.create(
            title="UMRA Zero-row",
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
            start_datetime=timezone.now() + timedelta(days=3),
            status=ServiceEvent.STATUS_PUBLISHED,
        )
        # An ordinary member of the record's unit still fails closed.
        self._active_primary_membership(self.member, self.group)
        self.assertEqual(event.audience_scope_links.count(), 0)
        self.assertFalse(event.can_be_seen_by(self.member))
        visible_ids = set(
            get_visible_service_events(self.member).values_list("id", flat=True)
        )
        self.assertNotIn(event.id, visible_ids)

    def test_helpers_do_not_affect_today_my_serving_or_bs_candidacy(self):
        # The record's own user, with the helpers exercised, gains no serving.
        self._call_all_helpers(self.member)
        self.assertIsNone(get_today_serving_summary(self.member))
        self.assertEqual(my_serving_assignments(self.member, tab="upcoming"), [])
        self.assertEqual(my_serving_assignments(self.member, tab="past"), [])
        self.assertEqual(
            get_membership_audience_candidate_unit_ids(self.member), []
        )


class UnitMemberRecordAccessUiNonExposureTests(TestCase):
    """MEMBER-RECORD.1D: the access helper adds no non-admin UI.

    Even with a unit member/care record on file and the access contract defined,
    `/my-units/`, `/my-units/<id>/`, and the ordinary profile page must still
    expose no member-record fields or care notes.
    """

    LEAK_MARKERS = (
        "GROUP-NOTE-1D",
        "CARE-NOTE-1D",
        "care_followup_notes",
        "attendance_state",
        "joined_unit_date",
        "structure_unit_member_records",
    )

    def setUp(self):
        self.lead_role = ChurchStructureUnitRoleType.objects.create(
            code=ChurchStructureUnitRoleType.CODE_LEAD, name="负责人", name_en="Lead"
        )
        self.unit = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="UMRA-UI",
            name="界面访问组",
            name_en="Access UI Group",
        )
        self.member = User.objects.create_user(
            username="umra_ui_member", password="pw"
        )
        self.record = ChurchStructureUnitMemberRecord.objects.create(
            unit=self.unit,
            user=self.member,
            attendance_state=ChurchStructureUnitMemberRecord.ATTENDANCE_ACTIVE,
            group_notes="GROUP-NOTE-1D",
            care_followup_notes="CARE-NOTE-1D",
        )

    def _assert_no_leak(self, response):
        for marker in self.LEAK_MARKERS:
            self.assertNotContains(response, marker)

    def test_my_units_list_shows_no_member_record(self):
        lead = User.objects.create_user(username="umra_ui_lead", password="pw")
        ChurchStructureUnitRoleAssignment.objects.create(
            unit=self.unit, role_type=self.lead_role, user=lead
        )
        self.client.login(username="umra_ui_lead", password="pw")
        # The compact My Units LIST page never exposes member/care records.
        list_response = self.client.get(reverse("my_units") + "?lang=en")
        self.assertEqual(list_response.status_code, 200)
        self._assert_no_leak(list_response)
        # MEMBER-RECORD.1E: the DETAIL page now surfaces a read-only member/care
        # section to delegated leads at the operational tier (group notes yes,
        # restricted care notes no); internal field-name markers still never leak.
        detail_response = self.client.get(
            reverse("my_unit_detail", args=[self.unit.id]) + "?lang=en"
        )
        self.assertEqual(detail_response.status_code, 200)
        self.assertContains(detail_response, "GROUP-NOTE-1D")
        self.assertNotContains(detail_response, "CARE-NOTE-1D")
        self.assertNotContains(detail_response, "care_followup_notes")
        self.assertNotContains(detail_response, "structure_unit_member_records")

    def test_ordinary_profile_page_shows_no_member_record(self):
        self.client.login(username="umra_ui_member", password="pw")
        response = self.client.get(reverse("profile") + "?lang=en")
        self.assertEqual(response.status_code, 200)
        self._assert_no_leak(response)


class MyUnitMemberCareRecordReadOnlyTests(TestCase):
    """MEMBER-RECORD.1E: read-only, privacy-scoped member/care section on the My
    Units detail page (``/my-units/<id>/``).

    The first non-admin UI exposure for unit member/care records. It renders only
    the current unit's records, every field gated through the MEMBER-RECORD.1D
    access helper: staff/superuser see basic + group notes + restricted care
    notes; delegated leads see basic + group notes only. It adds no
    create/edit/delete UI, grants no permission, infers no belonging or serving,
    and never exposes records on the My Units list, profile, My Serving, or Today.
    """

    GROUP_NOTE = "GROUP-NOTE-1E"
    CARE_NOTE = "CARE-NOTE-1E"
    ANCESTOR_NOTE = "ANCESTOR-NOTE-1E"
    DESCENDANT_NOTE = "DESCENDANT-NOTE-1E"
    SIBLING_NOTE = "SIBLING-NOTE-1E"

    def setUp(self):
        self.today = timezone.localdate()
        self.lead_role = ChurchStructureUnitRoleType.objects.create(
            code=ChurchStructureUnitRoleType.CODE_LEAD, name="负责人", name_en="Lead"
        )
        self.edify_role = ChurchStructureUnitRoleType.objects.create(
            code=ChurchStructureUnitRoleType.CODE_EDIFY,
            name="带查经同工",
            name_en="Edify",
        )

        # district -> group(record unit) -> nested, plus an unrelated branch.
        self.district = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_DISTRICT,
            code="MR1E-DISTRICT",
            name="记录区",
            name_en="Record District",
        )
        self.group = ChurchStructureUnit.objects.create(
            parent=self.district,
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="MR1E-GROUP",
            name="记录组",
            name_en="Record Group",
        )
        self.nested = ChurchStructureUnit.objects.create(
            parent=self.group,
            unit_type=ChurchStructureUnit.UNIT_CUSTOM,
            code="MR1E-NESTED",
            name="记录子单元",
            name_en="Record Nested",
        )
        self.sibling = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="MR1E-SIBLING",
            name="无关组",
            name_en="Unrelated Group",
        )

        self.member = User.objects.create_user(
            username="mr1e_member", first_name="Mem", last_name="Ber"
        )
        self.record = ChurchStructureUnitMemberRecord.objects.create(
            unit=self.group,
            user=self.member,
            attendance_state=ChurchStructureUnitMemberRecord.ATTENDANCE_ACTIVE,
            joined_unit_date=self.today - timedelta(days=10),
            group_notes=self.GROUP_NOTE,
            care_followup_notes=self.CARE_NOTE,
        )

    # --- fixture helpers -----------------------------------------------------

    def _lead(self, user, unit, **kwargs):
        return ChurchStructureUnitRoleAssignment.objects.create(
            unit=unit, role_type=self.lead_role, user=user, **kwargs
        )

    def _detail_url(self, unit=None):
        return reverse("my_unit_detail", args=[(unit or self.group).id]) + "?lang=en"

    def _login_staff(self):
        User.objects.create_user(
            username="mr1e_staff", password="pw", is_staff=True
        )
        self.client.login(username="mr1e_staff", password="pw")

    def _login_group_lead(self):
        user = User.objects.create_user(username="mr1e_lead", password="pw")
        self._lead(user, self.group)
        self.client.login(username="mr1e_lead", password="pw")
        return user

    # --- tier-scoped field visibility ----------------------------------------

    def test_staff_sees_section_with_basic_group_and_care_fields(self):
        self._login_staff()
        response = self.client.get(self._detail_url())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Unit Member / Care Records")
        # basic
        self.assertContains(response, "Mem Ber")
        self.assertContains(response, "Active")
        # operational + restricted care
        self.assertContains(response, self.GROUP_NOTE)
        self.assertContains(response, self.CARE_NOTE)
        self.assertContains(response, "Restricted care notes")

    def test_non_staff_lead_sees_basic_and_group_notes(self):
        self._login_group_lead()
        response = self.client.get(self._detail_url())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Unit Member / Care Records")
        self.assertContains(response, "Mem Ber")
        self.assertContains(response, self.GROUP_NOTE)

    def test_non_staff_lead_does_not_see_care_notes(self):
        self._login_group_lead()
        response = self.client.get(self._detail_url())
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, self.CARE_NOTE)
        # The page tells the lead the restricted notes are withheld.
        self.assertContains(
            response, "Restricted care notes are not shown on this page."
        )

    def test_ancestor_lead_sees_current_unit_records_operational(self):
        user = User.objects.create_user(username="mr1e_district_lead", password="pw")
        self._lead(user, self.district)
        self.client.login(username="mr1e_district_lead", password="pw")
        response = self.client.get(self._detail_url(self.group))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.GROUP_NOTE)
        self.assertNotContains(response, self.CARE_NOTE)

    # --- access gating (no records visible to the unauthorized) --------------

    def test_lead_on_unrelated_branch_cannot_access(self):
        user = User.objects.create_user(username="mr1e_other_lead", password="pw")
        self._lead(user, self.sibling)
        self.client.login(username="mr1e_other_lead", password="pw")
        response = self.client.get(self._detail_url(self.group))
        self.assertEqual(response.status_code, 404)

    def test_membership_only_user_cannot_access(self):
        user = User.objects.create_user(username="mr1e_membership", password="pw")
        ChurchStructureMembership.objects.create(
            user=user,
            unit=self.group,
            status=ChurchStructureMembership.STATUS_ACTIVE,
            is_primary=True,
            start_date=self.today,
        )
        self.client.login(username="mr1e_membership", password="pw")
        response = self.client.get(self._detail_url(self.group))
        self.assertEqual(response.status_code, 404)

    def test_non_lead_coworker_cannot_access(self):
        user = User.objects.create_user(username="mr1e_edify", password="pw")
        ChurchStructureUnitRoleAssignment.objects.create(
            unit=self.group, role_type=self.edify_role, user=user
        )
        self.client.login(username="mr1e_edify", password="pw")
        response = self.client.get(self._detail_url(self.group))
        self.assertEqual(response.status_code, 404)

    def test_team_assignment_member_only_user_cannot_access(self):
        user = User.objects.create_user(username="mr1e_team", password="pw")
        team = MinistryTeam.objects.create(name="MR1E Team")
        membership = TeamMembership.objects.create(team=team, user=user)
        event = ServiceEvent.objects.create(
            title="MR1E Event",
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
            start_datetime=timezone.now() + timedelta(days=2),
            status=ServiceEvent.STATUS_PUBLISHED,
        )
        assignment = TeamAssignment.objects.create(
            service_event=event,
            ministry_team=team,
            status=TeamAssignment.STATUS_SCHEDULED,
        )
        TeamAssignmentMember.objects.create(
            assignment=assignment, membership=membership
        )
        self.client.login(username="mr1e_team", password="pw")
        response = self.client.get(self._detail_url(self.group))
        self.assertEqual(response.status_code, 404)

    def test_bible_study_meeting_role_only_user_cannot_access(self):
        user = User.objects.create_user(username="mr1e_bs", password="pw")
        series = BibleStudySeries.objects.create(
            title="MR1E 查经", title_en="MR1E Study"
        )
        lesson = BibleStudyLesson.objects.create(
            series=series, title="MR1E 课", lesson_date=self.today
        )
        meeting = BibleStudyMeeting.objects.create(
            lesson=lesson,
            anchor_unit=self.group,
            meeting_datetime=timezone.now() + timedelta(days=2),
            status=BibleStudyMeeting.STATUS_PUBLISHED,
        )
        BibleStudyMeetingRole.objects.create(
            meeting=meeting,
            role=BibleStudyMeetingRole.ROLE_DISCUSSION_LEADER,
            user=user,
        )
        self.client.login(username="mr1e_bs", password="pw")
        response = self.client.get(self._detail_url(self.group))
        self.assertEqual(response.status_code, 404)

    # --- current-unit-only scope --------------------------------------------

    def test_only_current_unit_records_shown(self):
        ancestor_member = User.objects.create_user(username="mr1e_anc")
        descendant_member = User.objects.create_user(username="mr1e_desc")
        sibling_member = User.objects.create_user(username="mr1e_sib")
        ChurchStructureUnitMemberRecord.objects.create(
            unit=self.district, user=ancestor_member, group_notes=self.ANCESTOR_NOTE
        )
        ChurchStructureUnitMemberRecord.objects.create(
            unit=self.nested, user=descendant_member, group_notes=self.DESCENDANT_NOTE
        )
        ChurchStructureUnitMemberRecord.objects.create(
            unit=self.sibling, user=sibling_member, group_notes=self.SIBLING_NOTE
        )
        self._login_staff()
        response = self.client.get(self._detail_url(self.group))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.GROUP_NOTE)
        self.assertNotContains(response, self.ANCESTOR_NOTE)
        self.assertNotContains(response, self.DESCENDANT_NOTE)
        self.assertNotContains(response, self.SIBLING_NOTE)

    def test_empty_state_when_unit_has_no_records(self):
        self.record.delete()
        self._login_staff()
        response = self.client.get(self._detail_url(self.group))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Unit Member / Care Records")
        self.assertContains(
            response,
            "No unit member/care records are on file for this unit yet.",
        )

    # --- non-exposure on other surfaces -------------------------------------

    def test_my_units_list_page_does_not_expose_records(self):
        self._login_group_lead()
        response = self.client.get(reverse("my_units") + "?lang=en")
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, self.GROUP_NOTE)
        self.assertNotContains(response, self.CARE_NOTE)
        self.assertNotContains(response, "Unit Member / Care Records")

    def test_profile_page_does_not_expose_records(self):
        self.client.force_login(self.member)
        response = self.client.get(reverse("profile") + "?lang=en")
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, self.GROUP_NOTE)
        self.assertNotContains(response, self.CARE_NOTE)
        self.assertNotContains(response, "Unit Member / Care Records")

    def test_my_serving_does_not_expose_records(self):
        self.client.force_login(self.member)
        response = self.client.get(reverse("my_serving") + "?lang=en")
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, self.GROUP_NOTE)
        self.assertNotContains(response, self.CARE_NOTE)
        self.assertNotContains(response, "Unit Member / Care Records")

    def test_today_does_not_expose_records(self):
        self.client.force_login(self.member)
        response = self.client.get(reverse("home") + "?lang=en")
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, self.GROUP_NOTE)
        self.assertNotContains(response, self.CARE_NOTE)
        self.assertNotContains(response, "Unit Member / Care Records")

    # --- privacy / snapshot rendering ---------------------------------------

    def test_lead_page_renders_no_internal_ids_or_admin_urls(self):
        self._login_group_lead()
        response = self.client.get(self._detail_url())
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "care_followup_notes")
        self.assertNotContains(response, "structure_unit_member_records")
        self.assertNotContains(response, "/admin/")

    def test_lead_page_omits_care_value_even_when_present(self):
        # The record DOES have a care note; the lead's tier must still hide it.
        self.assertTrue(self.record.care_followup_notes)
        self._login_group_lead()
        response = self.client.get(self._detail_url())
        self.assertNotContains(response, self.CARE_NOTE)

    def test_staff_page_includes_care_value(self):
        self._login_staff()
        response = self.client.get(self._detail_url())
        self.assertContains(response, self.CARE_NOTE)

    # --- boundary: GET is read-only and infers nothing ----------------------

    def test_get_does_not_mutate_records_or_belonging_serving_rows(self):
        self._login_staff()
        before = {
            "unit_member_record": ChurchStructureUnitMemberRecord.objects.count(),
            "membership": ChurchStructureMembership.objects.count(),
            "unit_role": ChurchStructureUnitRoleAssignment.objects.count(),
            "church_role": ChurchRoleAssignment.objects.count(),
            "team_assignment": TeamAssignment.objects.count(),
            "team_assignment_member": TeamAssignmentMember.objects.count(),
            "bs_meeting_role": BibleStudyMeetingRole.objects.count(),
            "church_member_record": ChurchMemberRecord.objects.count(),
        }
        response = self.client.get(self._detail_url(self.group))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            ChurchStructureUnitMemberRecord.objects.count(),
            before["unit_member_record"],
        )
        self.assertEqual(
            ChurchStructureMembership.objects.count(), before["membership"]
        )
        self.assertEqual(
            ChurchStructureUnitRoleAssignment.objects.count(), before["unit_role"]
        )
        self.assertEqual(
            ChurchRoleAssignment.objects.count(), before["church_role"]
        )
        self.assertEqual(
            TeamAssignment.objects.count(), before["team_assignment"]
        )
        self.assertEqual(
            TeamAssignmentMember.objects.count(),
            before["team_assignment_member"],
        )
        self.assertEqual(
            BibleStudyMeetingRole.objects.count(), before["bs_meeting_role"]
        )
        self.assertEqual(
            ChurchMemberRecord.objects.count(), before["church_member_record"]
        )

    def test_get_does_not_grant_visibility_serving_or_bs_candidacy(self):
        # Viewing a member's care record does not make a zero-row ServiceEvent
        # visible to that member, nor add serving / Bible Study candidacy.
        self._login_staff()
        self.client.get(self._detail_url(self.group))
        event = ServiceEvent.objects.create(
            title="MR1E Zero-row",
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
            start_datetime=timezone.now() + timedelta(days=3),
            status=ServiceEvent.STATUS_PUBLISHED,
        )
        self.assertEqual(event.audience_scope_links.count(), 0)
        self.assertFalse(event.can_be_seen_by(self.member))
        self.assertIsNone(get_today_serving_summary(self.member))
        self.assertEqual(my_serving_assignments(self.member, tab="upcoming"), [])
        self.assertEqual(
            get_membership_audience_candidate_unit_ids(self.member), []
        )


class MyUnitMemberRecordWriteSurfaceTests(TestCase):
    """MEMBER-RECORD.1F: staff/admin-only create/edit surface for unit
    member/care records, reachable from the My Units detail page.

    Write access is staff/superuser only; delegated (non-staff) leads stay
    read-only at the operational tier from MEMBER-RECORD.1E. The unit is fixed by
    the route, records are never moved across units, and creating/editing a
    record never creates membership, role, serving, meeting-role, or global
    member-record rows and never infers belonging or serving.
    """

    NEW_GROUP_NOTE = "NEW-GROUP-NOTE-1F"
    NEW_CARE_NOTE = "NEW-CARE-NOTE-1F"
    EDIT_GROUP_NOTE = "EDIT-GROUP-NOTE-1F"
    EDIT_CARE_NOTE = "EDIT-CARE-NOTE-1F"

    def setUp(self):
        self.today = timezone.localdate()
        self.lead_role = ChurchStructureUnitRoleType.objects.create(
            code=ChurchStructureUnitRoleType.CODE_LEAD, name="负责人", name_en="Lead"
        )
        self.edify_role = ChurchStructureUnitRoleType.objects.create(
            code=ChurchStructureUnitRoleType.CODE_EDIFY,
            name="带查经同工",
            name_en="Edify",
        )

        self.district = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_DISTRICT,
            code="MR1F-DISTRICT",
            name="记录区",
            name_en="Record District",
        )
        self.group = ChurchStructureUnit.objects.create(
            parent=self.district,
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="MR1F-GROUP",
            name="记录组",
            name_en="Record Group",
        )
        self.other_group = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="MR1F-OTHER",
            name="另一组",
            name_en="Other Group",
        )
        self.inactive_unit = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="MR1F-INACTIVE",
            name="停用组",
            name_en="Inactive Group",
            is_active=False,
        )

        self.member = User.objects.create_user(
            username="mr1f_member", first_name="Mem", last_name="Ber"
        )
        self.member2 = User.objects.create_user(
            username="mr1f_member2", first_name="Sec", last_name="Ond"
        )
        self.inactive_member = User.objects.create_user(
            username="mr1f_inactive", first_name="In", last_name="Active",
            is_active=False,
        )

        self.existing = ChurchStructureUnitMemberRecord.objects.create(
            unit=self.group,
            user=self.member,
            attendance_state=ChurchStructureUnitMemberRecord.ATTENDANCE_ACTIVE,
            joined_unit_date=self.today - timedelta(days=5),
            group_notes="ORIGINAL-GROUP-1F",
            care_followup_notes="ORIGINAL-CARE-1F",
        )

    # --- fixture helpers -----------------------------------------------------

    def _lead(self, user, unit, **kwargs):
        return ChurchStructureUnitRoleAssignment.objects.create(
            unit=unit, role_type=self.lead_role, user=user, **kwargs
        )

    def _add_url(self, unit=None):
        return reverse(
            "add_my_unit_member_record", args=[(unit or self.group).id]
        ) + "?lang=en"

    def _edit_url(self, record=None, unit=None):
        record = record or self.existing
        return reverse(
            "edit_my_unit_member_record",
            args=[(unit or self.group).id, record.id],
        ) + "?lang=en"

    def _detail_url(self, unit=None):
        return reverse("my_unit_detail", args=[(unit or self.group).id]) + "?lang=en"

    def _login_staff(self):
        self.staff = User.objects.create_user(
            username="mr1f_staff", password="pw", is_staff=True
        )
        self.client.login(username="mr1f_staff", password="pw")
        return self.staff

    def _login_group_lead(self):
        user = User.objects.create_user(username="mr1f_lead", password="pw")
        self._lead(user, self.group)
        self.client.login(username="mr1f_lead", password="pw")
        return user

    def _add_payload(self, user=None, **overrides):
        data = {
            "user": (user or self.member2).id,
            "attendance_state": (
                ChurchStructureUnitMemberRecord.ATTENDANCE_ACTIVE
            ),
            "joined_unit_date": "",
            "group_notes": self.NEW_GROUP_NOTE,
            "care_followup_notes": self.NEW_CARE_NOTE,
        }
        data.update(overrides)
        return data

    def _other_object_counts(self):
        return {
            "membership": ChurchStructureMembership.objects.count(),
            "unit_role": ChurchStructureUnitRoleAssignment.objects.count(),
            "church_role": ChurchRoleAssignment.objects.count(),
            "team_assignment": TeamAssignment.objects.count(),
            "team_assignment_member": TeamAssignmentMember.objects.count(),
            "bs_meeting_role": BibleStudyMeetingRole.objects.count(),
            "church_member_record": ChurchMemberRecord.objects.count(),
        }

    # --- write-permission helper --------------------------------------------

    def test_can_write_helper_staff_only(self):
        staff = User.objects.create_user(username="mr1f_h_staff", is_staff=True)
        superuser = User.objects.create_superuser(
            username="mr1f_h_super", email="s@e.com", password="pw"
        )
        lead = User.objects.create_user(username="mr1f_h_lead")
        self._lead(lead, self.group)
        ordinary = User.objects.create_user(username="mr1f_h_ord")
        self.assertTrue(can_write_unit_member_records(staff))
        self.assertTrue(can_write_unit_member_records(superuser))
        self.assertFalse(can_write_unit_member_records(lead))
        self.assertFalse(can_write_unit_member_records(ordinary))
        self.assertFalse(can_write_unit_member_records(AnonymousUser()))

    # --- entry points on the detail page ------------------------------------

    def test_staff_sees_add_and_edit_links(self):
        self._login_staff()
        response = self.client.get(self._detail_url())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Add member/care record")
        self.assertContains(
            response,
            reverse(
                "add_my_unit_member_record", args=[self.group.id]
            ),
        )
        self.assertContains(
            response,
            reverse(
                "edit_my_unit_member_record",
                args=[self.group.id, self.existing.id],
            ),
        )

    def test_delegated_lead_does_not_see_add_or_edit_links(self):
        self._login_group_lead()
        response = self.client.get(self._detail_url())
        self.assertEqual(response.status_code, 200)
        # The read-only section is still shown (group note visible)...
        self.assertContains(response, "ORIGINAL-GROUP-1F")
        # ...but no add/edit affordances appear.
        self.assertNotContains(response, "Add member/care record")
        self.assertNotContains(
            response,
            reverse("add_my_unit_member_record", args=[self.group.id]),
        )
        self.assertNotContains(
            response,
            reverse(
                "edit_my_unit_member_record",
                args=[self.group.id, self.existing.id],
            ),
        )

    # --- access gating: only staff may reach the routes ----------------------

    def _assert_blocked(self, username):
        self.client.login(username=username, password="pw")
        self.assertEqual(self.client.get(self._add_url()).status_code, 404)
        self.assertEqual(
            self.client.post(self._add_url(), self._add_payload()).status_code,
            404,
        )
        self.assertEqual(self.client.get(self._edit_url()).status_code, 404)
        self.assertEqual(
            self.client.post(
                self._edit_url(), self._add_payload(user=self.member)
            ).status_code,
            404,
        )

    def test_delegated_lead_cannot_access_routes(self):
        before = ChurchStructureUnitMemberRecord.objects.count()
        User.objects.create_user(username="mr1f_g_lead", password="pw")
        self._lead(
            User.objects.get(username="mr1f_g_lead"), self.group
        )
        self._assert_blocked("mr1f_g_lead")
        self.assertEqual(
            ChurchStructureUnitMemberRecord.objects.count(), before
        )

    def test_ordinary_user_cannot_access_routes(self):
        User.objects.create_user(username="mr1f_ord", password="pw")
        self._assert_blocked("mr1f_ord")

    def test_membership_only_user_cannot_access_routes(self):
        user = User.objects.create_user(username="mr1f_mem_only", password="pw")
        ChurchStructureMembership.objects.create(
            user=user,
            unit=self.group,
            status=ChurchStructureMembership.STATUS_ACTIVE,
            is_primary=True,
            start_date=self.today,
        )
        self._assert_blocked("mr1f_mem_only")

    def test_non_lead_coworker_cannot_access_routes(self):
        user = User.objects.create_user(username="mr1f_edify", password="pw")
        ChurchStructureUnitRoleAssignment.objects.create(
            unit=self.group, role_type=self.edify_role, user=user
        )
        self._assert_blocked("mr1f_edify")

    def test_team_assignment_member_only_user_cannot_access_routes(self):
        user = User.objects.create_user(username="mr1f_team", password="pw")
        team = MinistryTeam.objects.create(name="MR1F Team")
        membership = TeamMembership.objects.create(team=team, user=user)
        event = ServiceEvent.objects.create(
            title="MR1F Event",
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
            start_datetime=timezone.now() + timedelta(days=2),
            status=ServiceEvent.STATUS_PUBLISHED,
        )
        assignment = TeamAssignment.objects.create(
            service_event=event,
            ministry_team=team,
            status=TeamAssignment.STATUS_SCHEDULED,
        )
        TeamAssignmentMember.objects.create(
            assignment=assignment, membership=membership
        )
        self._assert_blocked("mr1f_team")

    def test_bible_study_meeting_role_only_user_cannot_access_routes(self):
        user = User.objects.create_user(username="mr1f_bs", password="pw")
        series = BibleStudySeries.objects.create(
            title="MR1F 查经", title_en="MR1F Study"
        )
        lesson = BibleStudyLesson.objects.create(
            series=series, title="MR1F 课", lesson_date=self.today
        )
        meeting = BibleStudyMeeting.objects.create(
            lesson=lesson,
            anchor_unit=self.group,
            meeting_datetime=timezone.now() + timedelta(days=2),
            status=BibleStudyMeeting.STATUS_PUBLISHED,
        )
        BibleStudyMeetingRole.objects.create(
            meeting=meeting,
            role=BibleStudyMeetingRole.ROLE_DISCUSSION_LEADER,
            user=user,
        )
        self._assert_blocked("mr1f_bs")

    # --- add behavior --------------------------------------------------------

    def test_staff_can_create_record(self):
        staff = self._login_staff()
        before_other = self._other_object_counts()
        response = self.client.post(self._add_url(), self._add_payload())
        self.assertRedirects(response, reverse("my_unit_detail", args=[self.group.id]))
        record = ChurchStructureUnitMemberRecord.objects.get(
            unit=self.group, user=self.member2
        )
        self.assertEqual(record.group_notes, self.NEW_GROUP_NOTE)
        self.assertEqual(record.care_followup_notes, self.NEW_CARE_NOTE)
        # updated_by is the acting staff user.
        self.assertEqual(record.updated_by, staff)
        # No unrelated belonging/serving/global rows were created.
        self.assertEqual(self._other_object_counts(), before_other)

    def test_add_fixes_unit_from_route_not_post(self):
        self._login_staff()
        # A malicious "unit" field in POST is ignored; the route unit wins.
        self.client.post(
            self._add_url(self.group),
            self._add_payload(unit=self.other_group.id),
        )
        record = ChurchStructureUnitMemberRecord.objects.get(user=self.member2)
        self.assertEqual(record.unit, self.group)

    def test_add_rejects_inactive_unit_with_404(self):
        self._login_staff()
        self.assertEqual(
            self.client.get(self._add_url(self.inactive_unit)).status_code, 404
        )
        self.assertEqual(
            self.client.post(
                self._add_url(self.inactive_unit), self._add_payload()
            ).status_code,
            404,
        )

    def test_add_rejects_inactive_user(self):
        self._login_staff()
        before = ChurchStructureUnitMemberRecord.objects.count()
        response = self.client.post(
            self._add_url(), self._add_payload(user=self.inactive_member)
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            ChurchStructureUnitMemberRecord.objects.count(), before
        )
        self.assertFalse(
            ChurchStructureUnitMemberRecord.objects.filter(
                user=self.inactive_member
            ).exists()
        )

    def test_duplicate_add_shows_error_and_creates_no_duplicate(self):
        self._login_staff()
        before = ChurchStructureUnitMemberRecord.objects.filter(
            unit=self.group, user=self.member
        ).count()
        response = self.client.post(
            self._add_url(), self._add_payload(user=self.member)
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "already has a member/care record")
        self.assertEqual(
            ChurchStructureUnitMemberRecord.objects.filter(
                unit=self.group, user=self.member
            ).count(),
            before,
        )

    def test_add_does_not_require_membership_or_global_member_record(self):
        self._login_staff()
        self.assertFalse(
            ChurchStructureMembership.objects.filter(user=self.member2).exists()
        )
        self.assertFalse(
            ChurchMemberRecord.objects.filter(user=self.member2).exists()
        )
        response = self.client.post(self._add_url(), self._add_payload())
        self.assertRedirects(response, reverse("my_unit_detail", args=[self.group.id]))
        self.assertTrue(
            ChurchStructureUnitMemberRecord.objects.filter(
                unit=self.group, user=self.member2
            ).exists()
        )
        # Still no membership / global member record was auto-created.
        self.assertFalse(
            ChurchStructureMembership.objects.filter(user=self.member2).exists()
        )
        self.assertFalse(
            ChurchMemberRecord.objects.filter(user=self.member2).exists()
        )

    # --- edit behavior -------------------------------------------------------

    def test_staff_can_edit_all_editable_fields(self):
        staff = self._login_staff()
        new_date = self.today - timedelta(days=2)
        response = self.client.post(
            self._edit_url(),
            {
                "user": self.member.id,
                "attendance_state": (
                    ChurchStructureUnitMemberRecord.ATTENDANCE_VISITOR
                ),
                "joined_unit_date": new_date.isoformat(),
                "group_notes": self.EDIT_GROUP_NOTE,
                "care_followup_notes": self.EDIT_CARE_NOTE,
            },
        )
        self.assertRedirects(response, reverse("my_unit_detail", args=[self.group.id]))
        self.existing.refresh_from_db()
        self.assertEqual(
            self.existing.attendance_state,
            ChurchStructureUnitMemberRecord.ATTENDANCE_VISITOR,
        )
        self.assertEqual(self.existing.joined_unit_date, new_date)
        self.assertEqual(self.existing.group_notes, self.EDIT_GROUP_NOTE)
        self.assertEqual(self.existing.care_followup_notes, self.EDIT_CARE_NOTE)
        self.assertEqual(self.existing.updated_by, staff)

    def test_edit_cannot_move_record_to_another_unit_via_post(self):
        self._login_staff()
        self.client.post(
            self._edit_url(),
            {
                "user": self.member.id,
                "attendance_state": (
                    ChurchStructureUnitMemberRecord.ATTENDANCE_ACTIVE
                ),
                "joined_unit_date": "",
                "group_notes": "X",
                "care_followup_notes": "Y",
                "unit": self.other_group.id,
            },
        )
        self.existing.refresh_from_db()
        self.assertEqual(self.existing.unit, self.group)

    def test_edit_rejects_record_not_belonging_to_route_unit(self):
        self._login_staff()
        # Edit URL points at other_group but record belongs to group → 404.
        url = reverse(
            "edit_my_unit_member_record",
            args=[self.other_group.id, self.existing.id],
        )
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(
            self.client.post(url, self._add_payload(user=self.member)).status_code,
            404,
        )

    def test_edit_allows_resaving_same_user_on_same_record(self):
        self._login_staff()
        response = self.client.post(
            self._edit_url(),
            {
                "user": self.member.id,
                "attendance_state": (
                    ChurchStructureUnitMemberRecord.ATTENDANCE_ACTIVE
                ),
                "joined_unit_date": "",
                "group_notes": self.EDIT_GROUP_NOTE,
                "care_followup_notes": self.EDIT_CARE_NOTE,
            },
        )
        self.assertRedirects(response, reverse("my_unit_detail", args=[self.group.id]))
        self.existing.refresh_from_db()
        self.assertEqual(self.existing.group_notes, self.EDIT_GROUP_NOTE)

    def test_edit_rejects_change_to_inactive_user(self):
        self._login_staff()
        response = self.client.post(
            self._edit_url(),
            {
                "user": self.inactive_member.id,
                "attendance_state": (
                    ChurchStructureUnitMemberRecord.ATTENDANCE_ACTIVE
                ),
                "joined_unit_date": "",
                "group_notes": "X",
                "care_followup_notes": "Y",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.existing.refresh_from_db()
        self.assertEqual(self.existing.user, self.member)

    def test_edit_does_not_create_or_delete_unrelated_objects(self):
        self._login_staff()
        before_other = self._other_object_counts()
        before_records = ChurchStructureUnitMemberRecord.objects.count()
        self.client.post(
            self._edit_url(),
            {
                "user": self.member.id,
                "attendance_state": (
                    ChurchStructureUnitMemberRecord.ATTENDANCE_ACTIVE
                ),
                "joined_unit_date": "",
                "group_notes": self.EDIT_GROUP_NOTE,
                "care_followup_notes": self.EDIT_CARE_NOTE,
            },
        )
        self.assertEqual(self._other_object_counts(), before_other)
        self.assertEqual(
            ChurchStructureUnitMemberRecord.objects.count(), before_records
        )

    # --- display after save --------------------------------------------------

    def test_created_record_shows_on_detail_for_staff_with_care(self):
        self._login_staff()
        self.client.post(self._add_url(), self._add_payload())
        response = self.client.get(self._detail_url())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sec Ond")
        self.assertContains(response, self.NEW_GROUP_NOTE)
        self.assertContains(response, self.NEW_CARE_NOTE)

    def test_created_record_visible_to_lead_without_care(self):
        # Staff creates a record...
        self._login_staff()
        self.client.post(self._add_url(), self._add_payload())
        self.client.logout()
        # ...a delegated lead sees the group note but not the care note.
        self._login_group_lead()
        response = self.client.get(self._detail_url())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.NEW_GROUP_NOTE)
        self.assertNotContains(response, self.NEW_CARE_NOTE)

    def test_my_units_list_still_hides_records(self):
        self._login_staff()
        self.client.post(self._add_url(), self._add_payload())
        response = self.client.get(reverse("my_units") + "?lang=en")
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, self.NEW_GROUP_NOTE)
        self.assertNotContains(response, self.NEW_CARE_NOTE)
        self.assertNotContains(response, "Unit Member / Care Records")

    def test_other_surfaces_still_hide_records_after_save(self):
        self._login_staff()
        self.client.post(self._add_url(), self._add_payload())
        self.client.logout()
        self.client.force_login(self.member2)
        for name in ("profile", "my_serving", "home"):
            response = self.client.get(reverse(name) + "?lang=en")
            self.assertEqual(response.status_code, 200)
            self.assertNotContains(response, self.NEW_GROUP_NOTE)
            self.assertNotContains(response, self.NEW_CARE_NOTE)
            self.assertNotContains(response, "Unit Member / Care Records")

    # --- boundary: no readiness / visibility / serving / candidacy change ----

    def test_create_does_not_grant_visibility_serving_or_bs_candidacy(self):
        self._login_staff()
        self.client.post(self._add_url(), self._add_payload())
        event = ServiceEvent.objects.create(
            title="MR1F Zero-row",
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
            start_datetime=timezone.now() + timedelta(days=3),
            status=ServiceEvent.STATUS_PUBLISHED,
        )
        self.assertEqual(event.audience_scope_links.count(), 0)
        self.assertFalse(event.can_be_seen_by(self.member2))
        self.assertIsNone(get_today_serving_summary(self.member2))
        self.assertEqual(
            my_serving_assignments(self.member2, tab="upcoming"), []
        )
        self.assertEqual(
            get_membership_audience_candidate_unit_ids(self.member2), []
        )


class ServingReadinessPolicyModelTests(TestCase):
    """SERVING-READINESS.1A policy model foundation."""

    def test_can_create_policy(self):
        policy = ServingReadinessPolicy.objects.create(
            code="church_a_policy",
            name="政策甲",
            name_en="Policy A",
        )
        self.assertEqual(policy.code, "church_a_policy")
        self.assertTrue(policy.is_active)
        self.assertFalse(policy.is_default)

    def test_code_normalizes_lower_case(self):
        policy = ServingReadinessPolicy.objects.create(
            code="  Church_B_Policy  ",
            name="政策乙",
        )
        policy.refresh_from_db()
        self.assertEqual(policy.code, "church_b_policy")

    def test_at_most_one_active_default_policy(self):
        ServingReadinessPolicy.objects.create(
            code="default_one",
            name="默认一",
            is_default=True,
            is_active=True,
        )
        with self.assertRaises(ValidationError):
            ServingReadinessPolicy.objects.create(
                code="default_two",
                name="默认二",
                is_default=True,
                is_active=True,
            )

    def test_inactive_default_does_not_block_active_default(self):
        ServingReadinessPolicy.objects.create(
            code="retired_default",
            name="停用默认",
            is_default=True,
            is_active=False,
        )
        # An inactive default must not count against the single-active-default rule.
        policy = ServingReadinessPolicy.objects.create(
            code="live_default",
            name="启用默认",
            is_default=True,
            is_active=True,
        )
        self.assertTrue(policy.is_default)

    def test_display_name_helper_is_bilingual(self):
        policy = ServingReadinessPolicy.objects.create(
            code="bilingual_policy",
            name="中文名称",
            name_en="English Name",
        )
        self.assertEqual(policy.display_name("en"), "English Name")
        self.assertEqual(policy.display_name("zh"), "中文名称")

    def test_no_stored_readiness_result_field(self):
        policy = ServingReadinessPolicy.objects.create(
            code="no_result_policy",
            name="无结果政策",
        )
        for name in ("eligible_for_formal_serving", "is_ready_to_serve"):
            with self.assertRaises(FieldDoesNotExist):
                ServingReadinessPolicy._meta.get_field(name)
            self.assertFalse(hasattr(policy, name))


class ServingReadinessRequirementModelTests(TestCase):
    """SERVING-READINESS.1A requirement model foundation."""

    def setUp(self):
        self.policy = ServingReadinessPolicy.objects.create(
            code="req_test_policy",
            name="要求测试政策",
        )

    def test_can_create_requirement(self):
        requirement = ServingReadinessRequirement.objects.create(
            policy=self.policy,
            requirement_type=ServingReadinessRequirement.REQUIREMENT_FAITH_STATEMENT,
            accepted_statuses="signed,waived",
            severity=ServingReadinessRequirement.SEVERITY_REQUIRED,
            label="信仰宣言",
            label_en="Faith Statement",
        )
        self.assertEqual(
            requirement.accepted_status_set(), {"signed", "waived"}
        )

    def test_accepted_statuses_normalize_and_dedupe(self):
        requirement = ServingReadinessRequirement.objects.create(
            policy=self.policy,
            requirement_type=ServingReadinessRequirement.REQUIREMENT_BAPTISM,
            accepted_statuses="  Baptized , recognized ,baptized,",
            label="受洗",
        )
        requirement.refresh_from_db()
        self.assertEqual(requirement.accepted_statuses, "baptized,recognized")
        self.assertEqual(
            requirement.accepted_status_set(), {"baptized", "recognized"}
        )

    def test_invalid_faith_statement_status_rejected(self):
        with self.assertRaises(ValidationError):
            ServingReadinessRequirement.objects.create(
                policy=self.policy,
                requirement_type=(
                    ServingReadinessRequirement.REQUIREMENT_FAITH_STATEMENT
                ),
                accepted_statuses="signed,baptized",
                label="信仰宣言",
            )

    def test_invalid_baptism_status_rejected(self):
        with self.assertRaises(ValidationError):
            ServingReadinessRequirement.objects.create(
                policy=self.policy,
                requirement_type=ServingReadinessRequirement.REQUIREMENT_BAPTISM,
                accepted_statuses="baptized,signed",
                label="受洗",
            )

    def test_unsupported_requirement_type_rejected(self):
        with self.assertRaises(ValidationError):
            ServingReadinessRequirement.objects.create(
                policy=self.policy,
                requirement_type="membership_class",
                accepted_statuses="completed",
                label="会员课程",
            )

    def test_empty_accepted_statuses_rejected(self):
        with self.assertRaises(ValidationError):
            ServingReadinessRequirement.objects.create(
                policy=self.policy,
                requirement_type=(
                    ServingReadinessRequirement.REQUIREMENT_FAITH_STATEMENT
                ),
                accepted_statuses="  , ,",
                label="信仰宣言",
            )

    def test_duplicate_active_requirement_type_rejected(self):
        ServingReadinessRequirement.objects.create(
            policy=self.policy,
            requirement_type=(
                ServingReadinessRequirement.REQUIREMENT_FAITH_STATEMENT
            ),
            accepted_statuses="signed",
            label="信仰宣言",
        )
        with self.assertRaises(ValidationError):
            ServingReadinessRequirement.objects.create(
                policy=self.policy,
                requirement_type=(
                    ServingReadinessRequirement.REQUIREMENT_FAITH_STATEMENT
                ),
                accepted_statuses="waived",
                label="信仰宣言二",
            )

    def test_duplicate_inactive_requirement_type_allowed(self):
        ServingReadinessRequirement.objects.create(
            policy=self.policy,
            requirement_type=(
                ServingReadinessRequirement.REQUIREMENT_FAITH_STATEMENT
            ),
            accepted_statuses="signed",
            label="信仰宣言",
        )
        # An inactive duplicate (historical/disabled) must not be blocked.
        second = ServingReadinessRequirement.objects.create(
            policy=self.policy,
            requirement_type=(
                ServingReadinessRequirement.REQUIREMENT_FAITH_STATEMENT
            ),
            accepted_statuses="waived",
            label="信仰宣言二",
            is_active=False,
        )
        self.assertFalse(second.is_active)

    def test_active_requirement_on_inactive_policy_rejected(self):
        inactive_policy = ServingReadinessPolicy.objects.create(
            code="inactive_policy",
            name="停用政策",
            is_active=False,
        )
        with self.assertRaises(ValidationError):
            ServingReadinessRequirement.objects.create(
                policy=inactive_policy,
                requirement_type=ServingReadinessRequirement.REQUIREMENT_BAPTISM,
                accepted_statuses="baptized",
                label="受洗",
            )

    def test_creating_requirement_does_not_create_records_or_assignments(self):
        before = {
            "records": ChurchMemberRecord.objects.count(),
            "membership": ChurchStructureMembership.objects.count(),
            "unit_role": ChurchStructureUnitRoleAssignment.objects.count(),
            "church_role": ChurchRoleAssignment.objects.count(),
            "team_assignment": TeamAssignment.objects.count(),
            "team_assignment_member": TeamAssignmentMember.objects.count(),
            "bs_meeting_role": BibleStudyMeetingRole.objects.count(),
        }
        ServingReadinessRequirement.objects.create(
            policy=self.policy,
            requirement_type=ServingReadinessRequirement.REQUIREMENT_BAPTISM,
            accepted_statuses="baptized,recognized",
            label="受洗",
        )
        self.assertEqual(ChurchMemberRecord.objects.count(), before["records"])
        self.assertEqual(
            ChurchStructureMembership.objects.count(), before["membership"]
        )
        self.assertEqual(
            ChurchStructureUnitRoleAssignment.objects.count(), before["unit_role"]
        )
        self.assertEqual(
            ChurchRoleAssignment.objects.count(), before["church_role"]
        )
        self.assertEqual(
            TeamAssignment.objects.count(), before["team_assignment"]
        )
        self.assertEqual(
            TeamAssignmentMember.objects.count(),
            before["team_assignment_member"],
        )
        self.assertEqual(
            BibleStudyMeetingRole.objects.count(), before["bs_meeting_role"]
        )

    def test_display_helpers_are_bilingual(self):
        requirement = ServingReadinessRequirement.objects.create(
            policy=self.policy,
            requirement_type=(
                ServingReadinessRequirement.REQUIREMENT_FAITH_STATEMENT
            ),
            accepted_statuses="signed",
            label="信仰宣言",
            label_en="Faith Statement",
            message="信仰宣言尚未签署。",
            message_en="Faith Statement is not signed.",
        )
        self.assertEqual(requirement.display_label("en"), "Faith Statement")
        self.assertEqual(requirement.display_label("zh"), "信仰宣言")
        self.assertEqual(
            requirement.display_message("en"), "Faith Statement is not signed."
        )
        self.assertEqual(requirement.display_message("zh"), "信仰宣言尚未签署。")


class ServingReadinessSeedCommandTests(TestCase):
    """SERVING-READINESS.1A default SVCA policy seed command."""

    POLICY_CODE = "svca_default_formal_serving"

    def _call(self, *args):
        out = StringIO()
        call_command("seed_serving_readiness_policies", *args, stdout=out)
        return out.getvalue()

    def test_dry_run_creates_nothing(self):
        output = self._call("--dry-run")
        self.assertEqual(ServingReadinessPolicy.objects.count(), 0)
        self.assertEqual(ServingReadinessRequirement.objects.count(), 0)
        self.assertIn("DRY RUN", output)

    def test_default_invocation_is_dry_run(self):
        self._call()
        self.assertEqual(ServingReadinessPolicy.objects.count(), 0)
        self.assertEqual(ServingReadinessRequirement.objects.count(), 0)

    def test_dry_run_reports_would_create(self):
        output = self._call("--dry-run")
        self.assertIn(f"Would create policy {self.POLICY_CODE}", output)
        self.assertIn("Would create requirement", output)
        self.assertIn("faith_statement", output)
        self.assertIn("baptism", output)

    def test_apply_creates_policy_and_requirements(self):
        self._call("--apply")
        policy = ServingReadinessPolicy.objects.get(code=self.POLICY_CODE)
        self.assertTrue(policy.is_default)
        self.assertTrue(policy.is_active)
        self.assertEqual(policy.requirements.count(), 2)

    def test_apply_is_idempotent(self):
        self._call("--apply")
        output = self._call("--apply")
        self.assertEqual(
            ServingReadinessPolicy.objects.filter(code=self.POLICY_CODE).count(),
            1,
        )
        self.assertEqual(ServingReadinessRequirement.objects.count(), 2)
        self.assertIn("policies skipped: 1", output)
        self.assertIn("requirements skipped: 2", output)

    def test_created_requirements_have_expected_accepted_statuses(self):
        self._call("--apply")
        policy = ServingReadinessPolicy.objects.get(code=self.POLICY_CODE)
        faith = policy.requirements.get(
            requirement_type=ServingReadinessRequirement.REQUIREMENT_FAITH_STATEMENT
        )
        baptism = policy.requirements.get(
            requirement_type=ServingReadinessRequirement.REQUIREMENT_BAPTISM
        )
        self.assertEqual(
            faith.accepted_status_set(), {"signed", "waived", "not_required"}
        )
        self.assertEqual(
            baptism.accepted_status_set(),
            {"baptized", "recognized", "waived", "not_required"},
        )
        self.assertEqual(
            faith.severity, ServingReadinessRequirement.SEVERITY_REQUIRED
        )
        self.assertEqual(
            baptism.severity, ServingReadinessRequirement.SEVERITY_REQUIRED
        )

    def test_apply_does_not_create_member_records(self):
        before = ChurchMemberRecord.objects.count()
        self._call("--apply")
        self.assertEqual(ChurchMemberRecord.objects.count(), before)

    def test_apply_does_not_create_assignments(self):
        before = {
            "membership": ChurchStructureMembership.objects.count(),
            "unit_role": ChurchStructureUnitRoleAssignment.objects.count(),
            "church_role": ChurchRoleAssignment.objects.count(),
            "team_assignment": TeamAssignment.objects.count(),
            "team_assignment_member": TeamAssignmentMember.objects.count(),
            "bs_meeting_role": BibleStudyMeetingRole.objects.count(),
        }
        self._call("--apply")
        self.assertEqual(
            ChurchStructureMembership.objects.count(), before["membership"]
        )
        self.assertEqual(
            ChurchStructureUnitRoleAssignment.objects.count(), before["unit_role"]
        )
        self.assertEqual(
            ChurchRoleAssignment.objects.count(), before["church_role"]
        )
        self.assertEqual(
            TeamAssignment.objects.count(), before["team_assignment"]
        )
        self.assertEqual(
            TeamAssignmentMember.objects.count(),
            before["team_assignment_member"],
        )
        self.assertEqual(
            BibleStudyMeetingRole.objects.count(), before["bs_meeting_role"]
        )

    def test_dry_run_and_apply_together_rejected(self):
        with self.assertRaises(CommandError):
            self._call("--dry-run", "--apply")


class ServingReadinessEvaluatorTests(TestCase):
    """SERVING-READINESS.1B read-only evaluator."""

    def setUp(self):
        self.user = User.objects.create_user(username="readiness_user")

    def _seed_default_policy(self):
        call_command(
            "seed_serving_readiness_policies", "--apply", stdout=StringIO()
        )
        return ServingReadinessPolicy.objects.get(
            code="svca_default_formal_serving"
        )

    def _make_record(self, **kwargs):
        return ChurchMemberRecord.objects.create(user=self.user, **kwargs)

    def test_no_policy_returns_neutral_ready_result(self):
        result = get_serving_readiness(self.user, language="en")
        self.assertEqual(result.status, STATUS_NO_POLICY)
        self.assertTrue(result.is_ready)
        self.assertEqual(result.warnings, [])
        self.assertIsNone(result.policy_used)

    def test_no_record_with_required_policy_is_not_ready(self):
        self._seed_default_policy()
        result = get_serving_readiness(self.user, language="en")
        self.assertEqual(result.status, STATUS_NO_RECORD)
        self.assertFalse(result.is_ready)
        self.assertTrue(result.warnings)
        self.assertIsNone(result.record)

    def test_signed_and_baptized_passes(self):
        self._seed_default_policy()
        self._make_record(
            faith_statement_status=ChurchMemberRecord.FAITH_STATEMENT_SIGNED,
            baptism_status=ChurchMemberRecord.BAPTISM_BAPTIZED,
        )
        result = get_serving_readiness(self.user, language="en")
        self.assertEqual(result.status, STATUS_READY)
        self.assertTrue(result.is_ready)
        self.assertEqual(result.warnings, [])
        self.assertEqual(len(result.passed_requirements), 2)
        self.assertEqual(result.missing_requirements, [])

    def test_signed_and_recognized_passes(self):
        self._seed_default_policy()
        self._make_record(
            faith_statement_status=ChurchMemberRecord.FAITH_STATEMENT_SIGNED,
            baptism_status=ChurchMemberRecord.BAPTISM_RECOGNIZED,
        )
        result = get_serving_readiness(self.user)
        self.assertEqual(result.status, STATUS_READY)
        self.assertTrue(result.is_ready)

    def test_waived_and_not_required_statuses_pass(self):
        self._seed_default_policy()
        self._make_record(
            faith_statement_status=ChurchMemberRecord.FAITH_STATEMENT_WAIVED,
            baptism_status=ChurchMemberRecord.BAPTISM_NOT_REQUIRED,
        )
        result = get_serving_readiness(self.user)
        self.assertTrue(result.is_ready)
        self.assertEqual(result.status, STATUS_READY)

    def test_declined_faith_statement_fails(self):
        self._seed_default_policy()
        self._make_record(
            faith_statement_status=ChurchMemberRecord.FAITH_STATEMENT_DECLINED,
            baptism_status=ChurchMemberRecord.BAPTISM_BAPTIZED,
        )
        result = get_serving_readiness(self.user)
        self.assertEqual(result.status, STATUS_PENDING)
        self.assertFalse(result.is_ready)
        self.assertEqual(len(result.missing_requirements), 1)
        self.assertEqual(
            result.missing_requirements[0].requirement_type,
            ServingReadinessRequirement.REQUIREMENT_FAITH_STATEMENT,
        )

    def test_not_baptized_fails(self):
        self._seed_default_policy()
        self._make_record(
            faith_statement_status=ChurchMemberRecord.FAITH_STATEMENT_SIGNED,
            baptism_status=ChurchMemberRecord.BAPTISM_NOT_BAPTIZED,
        )
        result = get_serving_readiness(self.user)
        self.assertEqual(result.status, STATUS_PENDING)
        self.assertFalse(result.is_ready)

    def test_unknown_statuses_fail(self):
        self._seed_default_policy()
        self._make_record(
            faith_statement_status=ChurchMemberRecord.FAITH_STATEMENT_UNKNOWN,
            baptism_status=ChurchMemberRecord.BAPTISM_UNKNOWN,
        )
        result = get_serving_readiness(self.user)
        self.assertEqual(result.status, STATUS_PENDING)
        self.assertFalse(result.is_ready)
        self.assertEqual(len(result.missing_requirements), 2)

    def test_recommended_unmet_warns_but_stays_ready(self):
        policy = ServingReadinessPolicy.objects.create(
            code="recommended_policy",
            name="建议政策",
            is_default=True,
            is_active=True,
        )
        ServingReadinessRequirement.objects.create(
            policy=policy,
            requirement_type=(
                ServingReadinessRequirement.REQUIREMENT_FAITH_STATEMENT
            ),
            accepted_statuses="signed",
            severity=ServingReadinessRequirement.SEVERITY_REQUIRED,
            label="信仰宣言",
        )
        ServingReadinessRequirement.objects.create(
            policy=policy,
            requirement_type=ServingReadinessRequirement.REQUIREMENT_BAPTISM,
            accepted_statuses="baptized",
            severity=ServingReadinessRequirement.SEVERITY_RECOMMENDED,
            label="受洗",
            message="建议有受洗记录。",
            message_en="A baptism record is recommended.",
        )
        self._make_record(
            faith_statement_status=ChurchMemberRecord.FAITH_STATEMENT_SIGNED,
            baptism_status=ChurchMemberRecord.BAPTISM_NOT_BAPTIZED,
        )
        result = get_serving_readiness(self.user, language="en")
        self.assertTrue(result.is_ready)
        self.assertEqual(result.status, STATUS_READY)
        self.assertIn("A baptism record is recommended.", result.warnings)

    def test_inactive_user_returns_inactive_user_status(self):
        policy = self._seed_default_policy()
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        result = evaluate_serving_readiness(self.user, policy, language="en")
        self.assertEqual(result.status, STATUS_INACTIVE_USER)
        self.assertFalse(result.is_ready)
        self.assertTrue(result.warnings)

    def test_evaluator_messages_render_in_english_and_chinese(self):
        self._seed_default_policy()
        self._make_record(
            faith_statement_status=ChurchMemberRecord.FAITH_STATEMENT_DECLINED,
            baptism_status=ChurchMemberRecord.BAPTISM_BAPTIZED,
        )
        en_result = get_serving_readiness(self.user, language="en")
        zh_result = get_serving_readiness(self.user, language="zh")
        self.assertIn(
            "Faith Statement is not signed or confirmed.", en_result.warnings
        )
        self.assertIn("信仰宣言尚未签署或确认。", zh_result.warnings)

    def test_explicit_inactive_policy_is_honored_when_passed(self):
        policy = ServingReadinessPolicy.objects.create(
            code="explicit_inactive",
            name="显式停用政策",
            is_active=False,
        )
        ServingReadinessRequirement.objects.create(
            policy=policy,
            requirement_type=(
                ServingReadinessRequirement.REQUIREMENT_FAITH_STATEMENT
            ),
            accepted_statuses="signed",
            is_active=False,
            label="信仰宣言",
        )
        self._make_record(
            faith_statement_status=ChurchMemberRecord.FAITH_STATEMENT_DECLINED,
        )
        # No active requirements -> ready, but the explicit policy is used.
        result = get_serving_readiness(self.user, policy=policy)
        self.assertEqual(result.policy_used, policy)
        self.assertTrue(result.is_ready)

    def test_evaluator_does_not_create_or_change_records_or_assignments(self):
        self._seed_default_policy()
        before = {
            "records": ChurchMemberRecord.objects.count(),
            "membership": ChurchStructureMembership.objects.count(),
            "unit_role": ChurchStructureUnitRoleAssignment.objects.count(),
            "church_role": ChurchRoleAssignment.objects.count(),
            "team_assignment": TeamAssignment.objects.count(),
            "team_assignment_member": TeamAssignmentMember.objects.count(),
            "bs_meeting_role": BibleStudyMeetingRole.objects.count(),
        }
        get_serving_readiness(self.user)
        self.assertEqual(ChurchMemberRecord.objects.count(), before["records"])
        self.assertEqual(
            ChurchStructureMembership.objects.count(), before["membership"]
        )
        self.assertEqual(
            ChurchStructureUnitRoleAssignment.objects.count(), before["unit_role"]
        )
        self.assertEqual(
            ChurchRoleAssignment.objects.count(), before["church_role"]
        )
        self.assertEqual(
            TeamAssignment.objects.count(), before["team_assignment"]
        )
        self.assertEqual(
            TeamAssignmentMember.objects.count(),
            before["team_assignment_member"],
        )
        self.assertEqual(
            BibleStudyMeetingRole.objects.count(), before["bs_meeting_role"]
        )

    def test_evaluator_does_not_infer_facts_from_membership(self):
        # A user with active belonging but no member record must still be
        # treated as no_record: belonging never substitutes for facts.
        unit = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="RSG1",
            name="Readiness Group",
        )
        ChurchStructureMembership.objects.create(
            user=self.user,
            unit=unit,
            status=ChurchStructureMembership.STATUS_ACTIVE,
            is_primary=True,
            start_date=timezone.localdate() - timedelta(days=1),
        )
        self._seed_default_policy()
        result = get_serving_readiness(self.user)
        self.assertEqual(result.status, STATUS_NO_RECORD)
        self.assertFalse(result.is_ready)
        self.assertIsNone(result.record)


class ServingReadinessWarningHelperTests(TestCase):
    """SERVING-READINESS.1C warning-message helper (advisory, warning-only)."""

    def setUp(self):
        self.user = User.objects.create_user(username="warning_user")

    def _seed_default_policy(self):
        call_command(
            "seed_serving_readiness_policies", "--apply", stdout=StringIO()
        )

    def _make_record(self, **kwargs):
        return ChurchMemberRecord.objects.create(user=self.user, **kwargs)

    def test_no_policy_returns_no_messages(self):
        self.assertEqual(
            get_serving_readiness_warning_messages(self.user, language="en"), []
        )

    def test_ready_user_returns_no_messages(self):
        self._seed_default_policy()
        self._make_record(
            faith_statement_status=ChurchMemberRecord.FAITH_STATEMENT_SIGNED,
            baptism_status=ChurchMemberRecord.BAPTISM_BAPTIZED,
        )
        self.assertEqual(
            get_serving_readiness_warning_messages(self.user, language="en"), []
        )

    def test_none_user_returns_no_messages(self):
        self._seed_default_policy()
        self.assertEqual(get_serving_readiness_warning_messages(None), [])

    def test_no_record_returns_concise_warning(self):
        self._seed_default_policy()
        messages = get_serving_readiness_warning_messages(self.user, language="en")
        self.assertTrue(messages)
        joined = " ".join(messages)
        self.assertIn("Serving readiness warning:", joined)
        self.assertIn("No church member record is on file", joined)
        # No internal IDs / model names leak into the staff-facing message.
        self.assertNotIn("ChurchMemberRecord", joined)
        self.assertNotIn(str(self.user.pk), joined)

    def test_pending_faith_statement_returns_warning(self):
        self._seed_default_policy()
        self._make_record(
            faith_statement_status=ChurchMemberRecord.FAITH_STATEMENT_DECLINED,
            baptism_status=ChurchMemberRecord.BAPTISM_BAPTIZED,
        )
        messages = get_serving_readiness_warning_messages(self.user, language="en")
        joined = " ".join(messages)
        self.assertIn("Faith Statement is not signed or confirmed.", joined)

    def test_pending_baptism_returns_warning(self):
        self._seed_default_policy()
        self._make_record(
            faith_statement_status=ChurchMemberRecord.FAITH_STATEMENT_SIGNED,
            baptism_status=ChurchMemberRecord.BAPTISM_NOT_BAPTIZED,
        )
        messages = get_serving_readiness_warning_messages(self.user, language="en")
        joined = " ".join(messages)
        self.assertIn("No baptism or recognized baptism record.", joined)

    def test_chinese_messages_use_chinese_prefix(self):
        self._seed_default_policy()
        self._make_record(
            faith_statement_status=ChurchMemberRecord.FAITH_STATEMENT_DECLINED,
            baptism_status=ChurchMemberRecord.BAPTISM_BAPTIZED,
        )
        messages = get_serving_readiness_warning_messages(self.user, language="zh")
        joined = " ".join(messages)
        self.assertIn("服事预备提醒：", joined)
        self.assertIn("信仰宣言尚未签署或确认。", joined)

    def test_recommended_unmet_warns_but_user_stays_ready(self):
        policy = ServingReadinessPolicy.objects.create(
            code="helper_recommended_policy",
            name="建议政策",
            is_default=True,
            is_active=True,
        )
        ServingReadinessRequirement.objects.create(
            policy=policy,
            requirement_type=(
                ServingReadinessRequirement.REQUIREMENT_FAITH_STATEMENT
            ),
            accepted_statuses="signed",
            severity=ServingReadinessRequirement.SEVERITY_REQUIRED,
            label="信仰宣言",
        )
        ServingReadinessRequirement.objects.create(
            policy=policy,
            requirement_type=ServingReadinessRequirement.REQUIREMENT_BAPTISM,
            accepted_statuses="baptized",
            severity=ServingReadinessRequirement.SEVERITY_RECOMMENDED,
            label="受洗",
            message="建议有受洗记录。",
            message_en="A baptism record is recommended.",
        )
        self._make_record(
            faith_statement_status=ChurchMemberRecord.FAITH_STATEMENT_SIGNED,
            baptism_status=ChurchMemberRecord.BAPTISM_NOT_BAPTIZED,
        )
        # Ready (only required requirement met) but the recommended one still warns.
        self.assertTrue(get_serving_readiness(self.user).is_ready)
        messages = get_serving_readiness_warning_messages(self.user, language="en")
        self.assertTrue(messages)
        self.assertIn("A baptism record is recommended.", " ".join(messages))

    def test_helper_creates_no_member_record(self):
        self._seed_default_policy()
        before = ChurchMemberRecord.objects.count()
        get_serving_readiness_warning_messages(self.user, language="en")
        self.assertEqual(ChurchMemberRecord.objects.count(), before)


class ServingReadinessAdminTests(TestCase):
    """SERVING-READINESS.1A admin registration and clarity wording."""

    def setUp(self):
        self.admin_user = User.objects.create_superuser(
            username="readiness_admin",
            email="readiness_admin@example.com",
            password="AdminPass123!",
        )
        self.client.login(username="readiness_admin", password="AdminPass123!")
        self.policy = ServingReadinessPolicy.objects.create(
            code="admin_policy",
            name="管理政策",
            name_en="Admin Policy",
        )
        self.requirement = ServingReadinessRequirement.objects.create(
            policy=self.policy,
            requirement_type=(
                ServingReadinessRequirement.REQUIREMENT_FAITH_STATEMENT
            ),
            accepted_statuses="signed",
            label="信仰宣言",
        )

    def test_policy_changelist_renders(self):
        response = self.client.get(
            reverse("admin:accounts_servingreadinesspolicy_changelist")
        )
        self.assertEqual(response.status_code, 200)

    def test_policy_change_page_renders_with_clarity_note(self):
        response = self.client.get(
            reverse(
                "admin:accounts_servingreadinesspolicy_change",
                args=[self.policy.pk],
            )
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Serving Readiness Policy")
        self.assertContains(response, "服事预备政策")
        self.assertContains(response, "does NOT grant any permission")
        self.assertContains(response, "does NOT block any assignment")
        self.assertContains(response, "never a stored boolean")
        self.assertContains(response, "Belonging remains ChurchStructureMembership")

    def test_requirement_changelist_renders(self):
        response = self.client.get(
            reverse("admin:accounts_servingreadinessrequirement_changelist")
        )
        self.assertEqual(response.status_code, 200)

    def test_requirement_change_page_renders_with_clarity_note(self):
        response = self.client.get(
            reverse(
                "admin:accounts_servingreadinessrequirement_change",
                args=[self.requirement.pk],
            )
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Faith Statement and baptism facts")
        self.assertContains(response, "computed on demand")
