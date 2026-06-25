import re
from datetime import timedelta
from io import StringIO
from pathlib import Path

from django.contrib.auth.models import AnonymousUser, User
from django.core.exceptions import ValidationError
from django.core.management import call_command, CommandError
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from accounts.forms import create_or_update_signup_membership_request
from accounts.models import (
    ChurchRoleAssignment,
    ChurchStructureMembership,
    ChurchStructureUnit,
    Profile,
)
from accounts.permissions import (
    CAP_MANAGE_CHURCH_MEMBERSHIPS,
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
from comments.models import ReflectionComment, ReflectionReport
from events.models import ServiceEvent
from ministry.models import (
    MinistryTeam,
    TeamAssignment,
    TeamAssignmentMember,
    TeamMembership,
)
from prayers.models import PrayerReport, PrayerRequest
from reading.models import ReadingPlan, ReadingPlanDay
from studies.models import (
    BibleStudyLesson,
    BibleStudyMeeting,
    BibleStudyMeetingRole,
    BibleStudySeries,
)


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
        self.assertContains(response, "Lighting Pilot Import")
        self.assertContains(response, "Church Structure")
        self.assertContains(response, "Structure & Setup Check")
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
        self.assertContains(response, "灯光试点导入")
        self.assertContains(response, "教会结构")
        self.assertContains(response, "教会结构与设置检查")
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

        self.assertEqual(response.status_code, 200)
        self.assert_active_nav_href(response, "profile")

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
        self.assertContains(response, "object rows have been purged")
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
        self.assertContains(response, "Church Structure & Setup Check")
        self.assertContains(response, "How visibility works today")
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
        self.assertContains(response, "教会结构与设置检查")
        self.assertContains(response, "目前的运作方式")
        self.assertNotContains(response, "当前运行边界")
        self.assertContains(response, "设置就绪指标")
        self.assertContains(response, "教会结构树")
        self.assertContains(response, "覆盖成员")
        self.assertNotContains(response, "当前资料对应")
        self.assertNotContains(response, "现有记录")
        self.assertContains(response, "全教会")
        self.assertContains(response, "中文部")

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
        self.assertContains(response, "Covered members: 2")

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
        self.assertContains(response, "Direct member records on parent units")
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
        self.assertContains(response, "Structure & Setup Check")


class ChurchStructureSetupDetailTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(
            username="setup_staff",
            password="StaffPass123!",
            is_staff=True,
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
        self.assertContains(map_response, "Church Structure & Setup Check")
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
        self.assertContains(response, "Covered members: 1")
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
        self.assertContains(response, "Users with multiple active primary memberships")
        self.assertContains(response, "Users with active memberships but no primary")
        self.assertContains(response, "Inactive units with active memberships")
        self.assertNotContains(response, "setup_multi_primary")
        self.assertNotContains(response, "setup_no_primary")

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
        self.assertContains(overview_response, "Structure & Setup Check")
        self.assertNotContains(overview_response, self.old_setup_path)
        self.assertNotContains(overview_response, "Church Structure Setup")
        self.assertContains(profile_response, self.setup_url)
        self.assertNotContains(profile_response, self.old_setup_path)
        self.assertNotContains(profile_response, "Church Structure Setup")

        self.client.logout()
        self.client.login(username="setup_ordinary", password="UserPass123!")
        normal_profile = self.client.get(reverse("profile"))

        self.assertNotContains(normal_profile, self.setup_url)
        self.assertNotContains(normal_profile, self.old_setup_path)
        self.assertNotContains(normal_profile, "Church Structure Setup")


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
        self.rename_root_url = reverse(
            "staff_structure_unit_rename", args=[self.root.id]
        )
        self.rename_child_url = reverse(
            "staff_structure_unit_rename", args=[self.child.id]
        )
        self.add_child_url = reverse(
            "staff_structure_unit_add_child", args=[self.child.id]
        )
        self.disable_root_url = reverse(
            "staff_structure_unit_disable", args=[self.root.id]
        )
        self.disable_child_url = reverse(
            "staff_structure_unit_disable", args=[self.child.id]
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

    # --- view / edit mode ---------------------------------------------------

    def test_default_view_has_no_action_menus(self):
        self.set_language("en")
        self.login_admin()

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["edit_mode"])
        self.assertNotContains(response, "structure-row-icon-actions")
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
        self.assertContains(response, "Edit mode supports")
        self.assertContains(response, "structure-row-icon-actions")
        self.assertContains(response, 'aria-label="Rename unit"')
        self.assertContains(response, 'aria-label="Add child unit"')
        self.assertContains(response, 'aria-label="Disable unit"')
        self.assertContains(response, 'aria-label="View details"')
        self.assertNotIn("structure-row-actions-summary", content)
        self.assertNotIn(">Actions<", content)
        self.assertContains(response, "Exit edit mode")
        self.assertContains(response, "renaming display labels")
        self.assertContains(response, "adding child units")
        self.assertContains(response, "safe soft-disable")
        self.assertContains(response, "detail/admin links")
        self.assertContains(response, "does not hard-delete units")
        self.assertNotContains(response, "only change display names")

    def test_edit_mode_chinese_copy_describes_current_actions(self):
        self.set_language("zh")
        self.login_admin()

        response = self.client.get(self.url, {"edit": "1"})

        self.assertContains(response, "可重命名显示名称")
        self.assertContains(response, "新增下级单元")
        self.assertContains(response, "安全停用")
        self.assertContains(response, "查看详细资料或后台链接")
        self.assertContains(response, "不会硬删除")
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
        self.assertContains(response, self.disable_child_url)
        self.assertContains(response, 'name="confirm_disable"')
        self.assertContains(response, "Disable this unit")
        self.assertContains(response, "This only marks the unit inactive")

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

