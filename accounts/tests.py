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
    District,
    MinistryContext,
    Profile,
    SmallGroup,
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
    BibleStudySeries,
    BibleStudySession,
)

class AccountProfileTests(TestCase):
    def setUp(self):
        self.group = SmallGroup.objects.create(name="Rainbow 4")
        self.other_group = SmallGroup.objects.create(name="Rainbow 5")
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

        self.user.profile.small_group = self.group
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
        self.client.login(username="levin", password="OldPass123!")

        response = self.client.get(reverse("profile"))
        content = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "levin")
        self.assertContains(response, "Rainbow 4")
        self.assertContains(response, "我参加的小组")
        self.assertContains(response, "Profile Rainbow 5")
        self.assertNotContains(response, "SMALLGROUP-6 - Profile Rainbow 5")
        self.assertNotIn('name="small_group"', content)

    def test_user_can_update_profile_without_email(self):
        self.client.login(username="levin", password="OldPass123!")

        response = self.client.post(
            reverse("profile"),
            {
                "email": "",
                "small_group": self.other_group.id,
                "requested_unit": "",
                "preferred_language": "en",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("profile"))

        self.user.refresh_from_db()
        self.user.profile.refresh_from_db()

        self.assertEqual(self.user.email, "")
        self.assertEqual(self.user.profile.small_group, self.group)
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
                "small_group": self.group.id,
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
        self.assertEqual(self.user.profile.small_group, self.group)
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
        self.assertEqual(self.user.profile.small_group, self.group)

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
        self.assertEqual(self.user.profile.small_group, self.group)
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
        self.assertEqual(self.user.profile.small_group, self.group)
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
        self.assertEqual(self.user.profile.small_group, self.group)

    def test_profile_request_does_not_grant_runtime_access_or_permissions(self):
        district = District.objects.create(name="Profile District")
        district_group = SmallGroup.objects.create(
            name="Profile District Group",
            district=district,
        )
        event = ServiceEvent.objects.create(
            title="Profile District Service",
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
            start_datetime=timezone.now(),
            scope_type=ServiceEvent.SCOPE_DISTRICT,
            district=district,
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
        self.assertEqual(self.user.profile.small_group, self.group)
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
        self.assertContains(list_response, "Rainbow 4")
        self.assertEqual(detail_response.status_code, 200)
        self.assertContains(detail_response, "levin")
        self.assertContains(detail_response, "Profile Rainbow 5")
        self.assertContains(detail_response, "Rainbow 4")

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


class MinistryContextBridgeTests(TestCase):
    def test_ministry_context_can_be_created(self):
        context = MinistryContext.objects.create(
            code="CM",
            name="Chinese Ministry",
            name_en="Chinese Ministry",
            description="Chinese ministry context",
            description_en="Chinese ministry context",
            sort_order=10,
        )

        self.assertEqual(context.code, "CM")
        self.assertEqual(str(context), "CM - Chinese Ministry")
        self.assertTrue(context.is_active)
        self.assertIsNone(context.church_structure_unit)

    def test_ministry_context_code_is_normalized_to_uppercase(self):
        context = MinistryContext.objects.create(
            code="em",
            name="English Ministry",
        )

        self.assertEqual(context.code, "EM")

    def test_district_can_be_linked_to_ministry_context(self):
        context = MinistryContext.objects.create(code="CM", name="Chinese Ministry")
        district = District.objects.create(
            name="District 1",
            ministry_context=context,
        )

        self.assertEqual(district.ministry_context, context)
        self.assertIn(district, context.districts.all())

    def test_existing_district_without_ministry_context_remains_valid(self):
        district = District.objects.create(name="District without context")

        district.full_clean()
        self.assertIsNone(district.ministry_context)
        self.assertIsNone(district.church_structure_unit)

    def test_small_group_can_be_created_without_church_structure_unit(self):
        group = SmallGroup.objects.create(name="Rainbow without mapping")

        group.full_clean()
        self.assertIsNone(group.church_structure_unit)

    def test_small_group_still_belongs_to_district(self):
        district = District.objects.create(name="District 1")
        group = SmallGroup.objects.create(name="Rainbow 4", district=district)

        self.assertEqual(group.district, district)
        self.assertIn(group, district.small_groups.all())

    def test_ministry_context_can_link_to_church_structure_unit(self):
        unit = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_MINISTRY_CONTEXT,
            code="CM",
            name="中文事工",
        )
        context = MinistryContext.objects.create(
            code="CM",
            name="Chinese Ministry",
            church_structure_unit=unit,
        )

        self.assertEqual(context.church_structure_unit, unit)
        self.assertIn(context, unit.legacy_ministry_contexts.all())

    def test_district_can_link_to_church_structure_unit(self):
        unit = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_DISTRICT,
            code="D1",
            name="第一区",
        )
        district = District.objects.create(
            name="District 1",
            church_structure_unit=unit,
        )

        self.assertEqual(district.church_structure_unit, unit)
        self.assertIn(district, unit.legacy_districts.all())

    def test_small_group_can_link_to_church_structure_unit(self):
        unit = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="RAINBOW4",
            name="Rainbow 4",
        )
        group = SmallGroup.objects.create(
            name="Rainbow 4",
            church_structure_unit=unit,
        )

        self.assertEqual(group.church_structure_unit, unit)
        self.assertIn(group, unit.legacy_small_groups.all())

    def test_profile_small_group_behavior_is_unchanged(self):
        district = District.objects.create(name="District 1")
        group = SmallGroup.objects.create(name="Rainbow 4", district=district)
        user = User.objects.create_user(
            username="member_context",
            password="TestPass123!",
        )

        user.profile.small_group = group
        user.profile.save()

        user.profile.refresh_from_db()
        self.assertEqual(user.profile.small_group, group)
        self.assertIn(user.profile, group.members.all())

    def test_profile_small_group_still_drives_bible_study_scope(self):
        context = MinistryContext.objects.create(code="CM", name="Chinese Ministry")
        district = District.objects.create(
            name="District 1",
            ministry_context=context,
        )
        group = SmallGroup.objects.create(name="Rainbow 4", district=district)

        series = BibleStudySeries.objects.create(
            title="CM Bible Study",
            scope_type=BibleStudySeries.SCOPE_MINISTRY_CONTEXT,
            ministry_context=context,
        )

        self.assertEqual(list(series.get_eligible_small_groups()), [group])

    def test_profile_small_group_still_drives_service_event_scope(self):
        district = District.objects.create(name="District 1")
        group = SmallGroup.objects.create(name="Rainbow 4", district=district)
        other_group = SmallGroup.objects.create(name="Rainbow 5")
        user = User.objects.create_user(
            username="service_event_member",
            password="TestPass123!",
        )
        other_user = User.objects.create_user(
            username="other_service_event_member",
            password="TestPass123!",
        )

        user.profile.small_group = group
        user.profile.save()
        other_user.profile.small_group = other_group
        other_user.profile.save()

        event = ServiceEvent.objects.create(
            title="District Service",
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
            start_datetime=timezone.now(),
            scope_type=ServiceEvent.SCOPE_DISTRICT,
            district=district,
            status=ServiceEvent.STATUS_PUBLISHED,
        )

        self.assertTrue(event.can_be_seen_by(user))
        self.assertFalse(event.can_be_seen_by(other_user))


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

        self.cm = MinistryContext.objects.create(
            code="CM",
            name="Chinese Ministry",
            church_structure_unit=self.cm_unit,
        )
        self.em = MinistryContext.objects.create(
            code="EM",
            name="English Ministry",
            church_structure_unit=self.em_unit,
        )
        self.north = District.objects.create(
            name="North",
            ministry_context=self.cm,
            church_structure_unit=self.north_unit,
        )
        self.south = District.objects.create(
            name="South",
            ministry_context=self.cm,
            church_structure_unit=self.south_unit,
        )
        self.group = SmallGroup.objects.create(
            name="Rainbow 4",
            district=self.north,
            church_structure_unit=self.group_unit,
        )
        self.sibling_group = SmallGroup.objects.create(
            name="Rainbow 4B",
            district=self.north,
            church_structure_unit=self.sibling_group_unit,
        )
        self.other_group = SmallGroup.objects.create(
            name="Rainbow 5",
            district=self.south,
            church_structure_unit=self.other_group_unit,
        )
        self.unmapped_group = SmallGroup.objects.create(
            name="Unmapped Legacy Group",
            district=self.south,
        )

        self.group_user = self.create_user("selector_group", self.group)
        self.sibling_user = self.create_user("selector_sibling", self.sibling_group)
        self.no_group_user = self.create_user("selector_no_group", None)
        self.unmapped_group_user = self.create_user(
            "selector_unmapped_group",
            self.unmapped_group,
        )

    def create_user(self, username, small_group):
        user = User.objects.create_user(username=username, password="testpass123")
        user.profile.small_group = small_group
        user.profile.save(update_fields=["small_group"])
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

    def assert_resolved_groups(self, units, expected_groups):
        from accounts.structure_selectors import resolve_units_to_small_groups

        self.assertEqual(
            set(resolve_units_to_small_groups(units)),
            set(expected_groups),
        )

    def test_get_user_legacy_small_group_uses_profile_small_group_only(self):
        from accounts.structure_selectors import get_user_legacy_small_group

        missing_profile_user = User.objects.create_user(
            username="selector_missing_profile",
            password="testpass123",
        )
        missing_profile_user.profile.delete()

        self.assertEqual(get_user_legacy_small_group(self.group_user), self.group)
        self.assertIsNone(get_user_legacy_small_group(self.no_group_user))
        self.assertIsNone(get_user_legacy_small_group(missing_profile_user))
        self.assertIsNone(get_user_legacy_small_group(AnonymousUser()))
        self.assertIsNone(get_user_legacy_small_group(object()))

    def test_get_user_legacy_structure_unit_uses_mapped_profile_group_only(self):
        from accounts.structure_selectors import get_user_legacy_structure_unit

        yesterday = timezone.localdate() - timedelta(days=1)
        ChurchStructureMembership.objects.create(
            user=self.unmapped_group_user,
            unit=self.group_unit,
            status=ChurchStructureMembership.STATUS_ACTIVE,
            is_primary=True,
            start_date=yesterday,
        )

        self.assertEqual(
            get_user_legacy_structure_unit(self.group_user),
            self.group_unit,
        )
        self.assertIsNone(get_user_legacy_structure_unit(self.unmapped_group_user))
        self.assertIsNone(get_user_legacy_structure_unit(self.no_group_user))

    def test_get_user_legacy_structure_units_can_include_ancestors(self):
        from accounts.structure_selectors import get_user_legacy_structure_units

        yesterday = timezone.localdate() - timedelta(days=1)
        ChurchStructureMembership.objects.create(
            user=self.no_group_user,
            unit=self.group_unit,
            status=ChurchStructureMembership.STATUS_ACTIVE,
            is_primary=True,
            start_date=yesterday,
        )

        self.assertEqual(
            get_user_legacy_structure_units(self.group_user),
            [self.group_unit],
        )
        self.assertEqual(
            get_user_legacy_structure_units(
                self.group_user,
                include_ancestors=True,
            ),
            [self.root_unit, self.cm_unit, self.north_unit, self.group_unit],
        )
        self.assertEqual(
            get_user_legacy_structure_units(
                self.unmapped_group_user,
                include_ancestors=True,
            ),
            [],
        )
        self.assertEqual(
            get_user_legacy_structure_units(
                self.no_group_user,
                include_ancestors=True,
            ),
            [],
        )

    def test_resolve_units_to_small_groups_preserves_legacy_semantics(self):
        from accounts.structure_selectors import resolve_units_to_small_groups

        inactive_group = SmallGroup.objects.create(
            name="Inactive Group",
            district=self.north,
            is_active=False,
        )

        self.assert_resolved_groups(
            [self.root_unit],
            [self.group, self.sibling_group, self.other_group, self.unmapped_group],
        )
        self.assert_resolved_groups([self.group_unit], [self.group])
        self.assert_resolved_groups(
            [self.north_unit],
            [self.group, self.sibling_group],
        )
        self.assert_resolved_groups(
            [self.cm_unit],
            [self.group, self.sibling_group, self.other_group, self.unmapped_group],
        )
        self.assert_resolved_groups([self.unmapped_unit], [])

        self.group_unit.is_active = False
        self.group_unit.save(update_fields=["is_active"])
        self.assert_resolved_groups([self.group_unit], [self.group])
        root_groups = list(resolve_units_to_small_groups([self.root_unit]))
        self.assertIn(self.group, root_groups)
        self.assertNotIn(inactive_group, root_groups)

    def test_resolve_units_to_small_groups_does_not_duplicate_groups(self):
        from accounts.structure_selectors import resolve_units_to_small_groups

        groups = list(resolve_units_to_small_groups([self.cm_unit, self.north_unit]))

        self.assertEqual(len(groups), len({group.id for group in groups}))
        self.assertEqual(
            set(groups),
            {self.group, self.sibling_group, self.other_group, self.unmapped_group},
        )

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
            resolve_units_to_small_groups,
            user_matches_legacy_structure_audience,
            user_matches_membership_structure_audience,
            user_matches_structure_audience,
        )

        member = User.objects.create_user(username="selector_unmapped_member")
        self.create_membership(member, self.unmapped_unit)

        self.assertTrue(
            user_matches_membership_structure_audience(member, [self.unmapped_unit])
        )
        self.assertTrue(user_matches_structure_audience(member, [self.unmapped_unit]))
        self.assertFalse(
            user_matches_legacy_structure_audience(member, [self.unmapped_unit])
        )
        self.assertEqual(list(resolve_units_to_small_groups([self.unmapped_unit])), [])

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

    def test_user_matches_legacy_structure_audience_uses_profile_small_group(self):
        from accounts.structure_selectors import (
            user_matches_legacy_structure_audience,
        )

        self.create_membership(self.no_group_user, self.group_unit)

        self.assertFalse(
            user_matches_legacy_structure_audience(AnonymousUser(), [self.root_unit])
        )
        self.assertTrue(
            user_matches_legacy_structure_audience(self.no_group_user, [self.root_unit])
        )
        # Membership grants nothing through the legacy helper.
        self.assertFalse(
            user_matches_legacy_structure_audience(
                self.no_group_user, [self.group_unit]
            )
        )
        self.assertTrue(
            user_matches_legacy_structure_audience(self.group_user, [self.group_unit])
        )
        self.assertTrue(
            user_matches_legacy_structure_audience(self.group_user, [self.north_unit])
        )
        self.assertFalse(
            user_matches_legacy_structure_audience(
                self.sibling_user, [self.group_unit]
            )
        )
        self.assertFalse(
            user_matches_legacy_structure_audience(
                self.group_user, [self.unmapped_unit]
            )
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

    def test_studies_resolver_compatibility_wrapper_matches_selector(self):
        from accounts.structure_selectors import resolve_units_to_small_groups
        from studies.models import (
            resolve_units_to_small_groups as studies_resolve_units_to_small_groups,
        )

        units = [self.cm_unit, self.other_group_unit]

        self.assertEqual(
            set(studies_resolve_units_to_small_groups(units)),
            set(resolve_units_to_small_groups(units)),
        )


class ChurchStructureUnitSeedingCommandTests(TestCase):
    def run_seed_command(self, *args):
        output = StringIO()
        call_command("seed_church_structure_units", *args, stdout=output)
        return output.getvalue()

    def test_dry_run_creates_no_units_or_mappings(self):
        context = MinistryContext.objects.create(code="CM", name="Chinese Ministry")
        district = District.objects.create(name="District 1", ministry_context=context)
        group = SmallGroup.objects.create(name="Rainbow 4", district=district)

        output = self.run_seed_command("--dry-run")

        self.assertIn("Church structure unit seeding mode: DRY RUN", output)
        self.assertEqual(ChurchStructureUnit.objects.count(), 0)

        context.refresh_from_db()
        district.refresh_from_db()
        group.refresh_from_db()
        self.assertIsNone(context.church_structure_unit)
        self.assertIsNone(district.church_structure_unit)
        self.assertIsNone(group.church_structure_unit)

    def test_apply_creates_root_and_maps_current_structure(self):
        context = MinistryContext.objects.create(
            code="cm",
            name="中文事工",
            name_en="Chinese Ministry",
            description="中文事工说明",
            description_en="Chinese ministry description",
            sort_order=10,
        )
        district = District.objects.create(name="第一区", ministry_context=context)
        group = SmallGroup.objects.create(name="Rainbow 4", district=district)

        output = self.run_seed_command("--apply")

        self.assertIn("Church structure unit seeding mode: APPLY", output)

        root = ChurchStructureUnit.objects.get(
            parent__isnull=True,
            code="CHURCH",
        )
        self.assertEqual(root.unit_type, ChurchStructureUnit.UNIT_ROOT)
        self.assertEqual(root.name, "全教会")
        self.assertEqual(root.name_en, "Whole Church")

        context.refresh_from_db()
        district.refresh_from_db()
        group.refresh_from_db()

        self.assertEqual(context.church_structure_unit.parent, root)
        self.assertEqual(
            context.church_structure_unit.unit_type,
            ChurchStructureUnit.UNIT_MINISTRY_CONTEXT,
        )
        self.assertEqual(context.church_structure_unit.code, "CM")
        self.assertEqual(context.church_structure_unit.name, "中文事工")
        self.assertEqual(context.church_structure_unit.name_en, "Chinese Ministry")

        self.assertEqual(district.church_structure_unit.parent, context.church_structure_unit)
        self.assertEqual(district.church_structure_unit.code, f"DISTRICT-{district.id}")
        self.assertEqual(
            district.church_structure_unit.unit_type,
            ChurchStructureUnit.UNIT_DISTRICT,
        )

        self.assertEqual(group.church_structure_unit.parent, district.church_structure_unit)
        self.assertEqual(group.church_structure_unit.code, f"SMALLGROUP-{group.id}")
        self.assertEqual(
            group.church_structure_unit.unit_type,
            ChurchStructureUnit.UNIT_SMALL_GROUP,
        )

    def test_apply_handles_orphan_district_and_group_with_holding_units(self):
        district = District.objects.create(name="District without context")
        group = SmallGroup.objects.create(name="Group without district")

        dry_run_output = self.run_seed_command("--dry-run")

        self.assertEqual(
            dry_run_output.count("Would create holding unit UNASSIGNED-DISTRICTS"),
            1,
        )
        self.assertEqual(
            dry_run_output.count("Would create holding unit UNASSIGNED-GROUPS"),
            1,
        )

        self.run_seed_command("--apply")

        root = ChurchStructureUnit.objects.get(
            parent__isnull=True,
            code="CHURCH",
        )
        unassigned_districts = ChurchStructureUnit.objects.get(
            parent=root,
            code="UNASSIGNED-DISTRICTS",
        )
        unassigned_groups = ChurchStructureUnit.objects.get(
            parent=root,
            code="UNASSIGNED-GROUPS",
        )

        district.refresh_from_db()
        group.refresh_from_db()

        self.assertEqual(district.church_structure_unit.parent, unassigned_districts)
        self.assertEqual(group.church_structure_unit.parent, unassigned_groups)
        self.assertEqual(unassigned_districts.name_en, "Unassigned Districts")
        self.assertEqual(unassigned_groups.name_en, "Unassigned Groups")

    def test_apply_is_idempotent(self):
        context = MinistryContext.objects.create(code="CM", name="Chinese Ministry")
        district = District.objects.create(name="District 1", ministry_context=context)
        SmallGroup.objects.create(name="Rainbow 4", district=district)

        self.run_seed_command("--apply")
        first_unit_count = ChurchStructureUnit.objects.count()

        second_output = self.run_seed_command("--apply")
        dry_run_output = self.run_seed_command("--dry-run")

        self.assertEqual(ChurchStructureUnit.objects.count(), first_unit_count)
        self.assertIn("created: 0", second_output)
        self.assertIn("would created: 0", dry_run_output)
        self.assertIn("would linked: 0", dry_run_output)

    def test_apply_preserves_existing_runtime_behavior(self):
        context = MinistryContext.objects.create(code="CM", name="Chinese Ministry")
        district = District.objects.create(name="District 1", ministry_context=context)
        group = SmallGroup.objects.create(name="Rainbow 4", district=district)
        other_group = SmallGroup.objects.create(name="Rainbow 5")
        user = User.objects.create_user(
            username="seeded_member",
            password="TestPass123!",
        )
        other_user = User.objects.create_user(
            username="seeded_other_member",
            password="TestPass123!",
        )
        user.profile.small_group = group
        user.profile.save()
        other_user.profile.small_group = other_group
        other_user.profile.save()

        series = BibleStudySeries.objects.create(
            title="CM Bible Study",
            scope_type=BibleStudySeries.SCOPE_MINISTRY_CONTEXT,
            ministry_context=context,
        )
        event = ServiceEvent.objects.create(
            title="District Service",
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
            start_datetime=timezone.now(),
            scope_type=ServiceEvent.SCOPE_DISTRICT,
            district=district,
            status=ServiceEvent.STATUS_PUBLISHED,
        )

        self.run_seed_command("--apply")

        self.assertEqual(list(series.get_eligible_small_groups()), [group])
        self.assertEqual(user.profile.small_group, group)
        self.assertTrue(event.can_be_seen_by(user))
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

    def test_membership_does_not_change_profile_small_group(self):
        user = User.objects.create_user(username="profile_unchanged")
        group = SmallGroup.objects.create(name="Rainbow 4")
        unit = self.create_unit()

        ChurchStructureMembership.objects.create(
            user=user,
            unit=unit,
            status=ChurchStructureMembership.STATUS_ACTIVE,
            is_primary=True,
            start_date=timezone.localdate(),
        )

        user.profile.refresh_from_db()
        self.assertIsNone(user.profile.small_group)

        user.profile.small_group = group
        user.profile.save()

        user.profile.refresh_from_db()
        self.assertEqual(user.profile.small_group, group)

    def test_membership_does_not_change_bible_study_scope_behavior(self):
        context = MinistryContext.objects.create(code="CM", name="Chinese Ministry")
        district = District.objects.create(
            name="District 1",
            ministry_context=context,
        )
        group = SmallGroup.objects.create(name="Rainbow 4", district=district)
        unit = self.create_unit()
        user = User.objects.create_user(username="study_membership")
        ChurchStructureMembership.objects.create(
            user=user,
            unit=unit,
            status=ChurchStructureMembership.STATUS_ACTIVE,
            is_primary=True,
            start_date=timezone.localdate(),
        )
        series = BibleStudySeries.objects.create(
            title="CM Bible Study",
            scope_type=BibleStudySeries.SCOPE_MINISTRY_CONTEXT,
            ministry_context=context,
        )

        self.assertEqual(list(series.get_eligible_small_groups()), [group])

    def test_membership_does_not_change_service_event_visibility(self):
        district = District.objects.create(name="District 1")
        group = SmallGroup.objects.create(name="Rainbow 4", district=district)
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
            scope_type=ServiceEvent.SCOPE_DISTRICT,
            district=district,
            status=ServiceEvent.STATUS_PUBLISHED,
        )

        self.assertFalse(event.can_be_seen_by(user))

        user.profile.small_group = group
        user.profile.save()

        self.assertTrue(event.can_be_seen_by(user))


class ChurchStructureMembershipBackfillCommandTests(TestCase):
    def run_backfill_command(self, *args):
        output = StringIO()
        call_command(
            "backfill_church_structure_memberships",
            *args,
            stdout=output,
        )
        return output.getvalue()

    def create_mapped_group(self, group_name="Rainbow 4", unit_code="RAINBOW4"):
        unit = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code=unit_code,
            name=group_name,
        )
        group = SmallGroup.objects.create(
            name=group_name,
            church_structure_unit=unit,
        )
        return group, unit

    def assign_group(self, user, group):
        user.profile.small_group = group
        user.profile.save()

    def test_dry_run_creates_no_memberships(self):
        group, _unit = self.create_mapped_group()
        user = User.objects.create_user(username="dry_run_member")
        self.assign_group(user, group)

        output = self.run_backfill_command()

        self.assertIn("Church structure membership backfill mode: DRY RUN", output)
        self.assertIn("would_created: 1", output)
        self.assertEqual(ChurchStructureMembership.objects.count(), 0)

        user.profile.refresh_from_db()
        self.assertEqual(user.profile.small_group, group)

    def test_apply_creates_active_primary_membership_from_profile_small_group(self):
        group, unit = self.create_mapped_group()
        user = User.objects.create_user(username="apply_member")
        self.assign_group(user, group)

        output = self.run_backfill_command("--apply")

        self.assertIn("Church structure membership backfill mode: APPLY", output)
        self.assertIn("created: 1", output)

        membership = ChurchStructureMembership.objects.get(user=user)
        self.assertEqual(membership.unit, unit)
        self.assertEqual(
            membership.membership_type,
            ChurchStructureMembership.TYPE_SMALL_GROUP_MEMBER,
        )
        self.assertEqual(membership.status, ChurchStructureMembership.STATUS_ACTIVE)
        self.assertTrue(membership.is_primary)
        self.assertEqual(membership.start_date, timezone.localdate())
        self.assertIsNone(membership.approved_by)
        self.assertIsNone(membership.approved_at)
        self.assertIsNone(membership.requested_by)
        self.assertIn("Backfilled from Profile.small_group", membership.notes)

        user.profile.refresh_from_db()
        self.assertEqual(user.profile.small_group, group)

    def test_apply_skips_user_without_profile_small_group(self):
        User.objects.create_user(username="no_profile_group")

        output = self.run_backfill_command("--apply")

        self.assertIn("created: 0", output)
        self.assertIn("skipped_no_profile_group: 1", output)
        self.assertEqual(ChurchStructureMembership.objects.count(), 0)

    def test_apply_skips_and_warns_for_unmapped_profile_small_group(self):
        group = SmallGroup.objects.create(name="Unmapped Group")
        user = User.objects.create_user(username="unmapped_member")
        self.assign_group(user, group)

        output = self.run_backfill_command("--apply")

        self.assertIn("WARNING:", output)
        self.assertIn("skipped_unmapped_group: 1", output)
        self.assertIn("warnings: 1", output)
        self.assertEqual(ChurchStructureMembership.objects.count(), 0)

    def test_apply_skips_existing_active_primary_membership(self):
        group, _unit = self.create_mapped_group()
        existing_unit = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="EXISTING",
            name="Existing Group",
        )
        user = User.objects.create_user(username="existing_primary")
        self.assign_group(user, group)
        existing = ChurchStructureMembership.objects.create(
            user=user,
            unit=existing_unit,
            status=ChurchStructureMembership.STATUS_ACTIVE,
            is_primary=True,
            start_date=timezone.localdate(),
        )

        output = self.run_backfill_command("--apply")

        self.assertIn("created: 0", output)
        self.assertIn("skipped_existing_active_primary: 1", output)
        self.assertEqual(list(ChurchStructureMembership.objects.all()), [existing])

    def test_apply_and_second_dry_run_are_idempotent(self):
        group, _unit = self.create_mapped_group()
        user = User.objects.create_user(username="idempotent_member")
        self.assign_group(user, group)

        self.run_backfill_command("--apply")
        second_apply_output = self.run_backfill_command("--apply")
        dry_run_output = self.run_backfill_command("--dry-run")

        self.assertEqual(ChurchStructureMembership.objects.filter(user=user).count(), 1)
        self.assertIn("created: 0", second_apply_output)
        self.assertIn("would_created: 0", dry_run_output)
        self.assertIn("skipped_existing_active_primary: 1", dry_run_output)

    def test_requested_membership_does_not_block_backfill(self):
        group, unit = self.create_mapped_group()
        user = User.objects.create_user(username="requested_backfill")
        self.assign_group(user, group)
        ChurchStructureMembership.objects.create(
            user=user,
            unit=unit,
            status=ChurchStructureMembership.STATUS_REQUESTED,
            is_primary=True,
            start_date=timezone.localdate(),
            requested_by=user,
        )

        output = self.run_backfill_command("--apply")

        self.assertIn("created: 1", output)
        self.assertEqual(ChurchStructureMembership.objects.filter(user=user).count(), 2)
        self.assertTrue(
            ChurchStructureMembership.objects.filter(
                user=user,
                status=ChurchStructureMembership.STATUS_ACTIVE,
                is_primary=True,
            ).exists()
        )

    def test_backfill_command_preserves_bible_study_and_service_event_behavior(self):
        context = MinistryContext.objects.create(code="CM", name="Chinese Ministry")
        district = District.objects.create(
            name="District 1",
            ministry_context=context,
        )
        group, unit = self.create_mapped_group()
        group.district = district
        group.save()
        user = User.objects.create_user(username="runtime_profile_member")
        other_user = User.objects.create_user(username="runtime_no_profile_group")
        self.assign_group(user, group)
        ChurchStructureMembership.objects.create(
            user=other_user,
            unit=unit,
            status=ChurchStructureMembership.STATUS_ACTIVE,
            is_primary=True,
            start_date=timezone.localdate(),
        )
        series = BibleStudySeries.objects.create(
            title="CM Bible Study",
            scope_type=BibleStudySeries.SCOPE_MINISTRY_CONTEXT,
            ministry_context=context,
        )
        event = ServiceEvent.objects.create(
            title="District Service",
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
            start_datetime=timezone.now(),
            scope_type=ServiceEvent.SCOPE_DISTRICT,
            district=district,
            status=ServiceEvent.STATUS_PUBLISHED,
        )

        self.run_backfill_command("--apply")

        self.assertEqual(list(series.get_eligible_small_groups()), [group])
        self.assertTrue(event.can_be_seen_by(user))
        self.assertFalse(event.can_be_seen_by(other_user))

    def test_dry_run_and_apply_flags_cannot_be_combined(self):
        with self.assertRaises(CommandError):
            self.run_backfill_command("--dry-run", "--apply")


class ChurchStructureBelongingAuditCommandTests(TestCase):
    def run_audit_command(self, *args):
        output = StringIO()
        call_command("audit_structure_belonging", *args, stdout=output)
        return output.getvalue()

    def create_unit(self, code, name=None, unit_type=None):
        return ChurchStructureUnit.objects.create(
            unit_type=unit_type or ChurchStructureUnit.UNIT_SMALL_GROUP,
            code=code,
            name=name or code,
        )

    def create_mapped_group(self, name, unit=None):
        unit = unit or self.create_unit(name.upper().replace(" ", ""))
        group = SmallGroup.objects.create(name=name, church_structure_unit=unit)
        return group, unit

    def assign_group(self, user, group):
        user.profile.small_group = group
        user.profile.save()

    def create_active_primary(self, user, unit, **kwargs):
        defaults = {
            "user": user,
            "unit": unit,
            "status": ChurchStructureMembership.STATUS_ACTIVE,
            "is_primary": True,
            "start_date": timezone.localdate(),
        }
        defaults.update(kwargs)
        return ChurchStructureMembership.objects.create(**defaults)

    def assert_summary_count(self, output, category, count):
        self.assertIn(f"{category}: {count}", output)

    def test_summary_classifies_each_required_category(self):
        in_sync_group, in_sync_unit = self.create_mapped_group("Audit In Sync")
        _membership_without_group, membership_without_group_unit = (
            self.create_mapped_group("Audit Membership Only")
        )
        group_only_group, _group_only_unit = self.create_mapped_group(
            "Audit Group Only"
        )
        mismatch_group, _mismatch_group_unit = self.create_mapped_group(
            "Audit Mismatch Group"
        )
        mismatch_membership_unit = self.create_unit("AUDIT-MISMATCH-MEMBER")
        unmapped_group = SmallGroup.objects.create(name="Audit Unmapped Group")
        parent_unit = self.create_unit(
            "AUDIT-PARENT",
            unit_type=ChurchStructureUnit.UNIT_FELLOWSHIP,
        )
        multi_unit = self.create_unit("AUDIT-MULTI")
        SmallGroup.objects.create(
            name="Audit Multi 1",
            church_structure_unit=multi_unit,
        )
        SmallGroup.objects.create(
            name="Audit Multi 2",
            church_structure_unit=multi_unit,
        )

        in_sync = User.objects.create_user(
            username="audit_in_sync",
            first_name="In",
            last_name="Sync",
        )
        self.assign_group(in_sync, in_sync_group)
        self.create_active_primary(in_sync, in_sync_unit)

        membership_without_group = User.objects.create_user(
            username="audit_membership_without_group"
        )
        self.create_active_primary(
            membership_without_group,
            membership_without_group_unit,
        )

        group_without_membership = User.objects.create_user(
            username="audit_group_without_membership"
        )
        self.assign_group(group_without_membership, group_only_group)

        mismatch = User.objects.create_user(username="audit_mismatch")
        self.assign_group(mismatch, mismatch_group)
        self.create_active_primary(mismatch, mismatch_membership_unit)

        unmapped = User.objects.create_user(username="audit_unmapped_group")
        self.assign_group(unmapped, unmapped_group)

        parent_only = User.objects.create_user(username="audit_parent_only")
        self.create_active_primary(parent_only, parent_unit)

        multi_group = User.objects.create_user(username="audit_multi_group")
        self.create_active_primary(multi_group, multi_unit)

        User.objects.create_user(username="audit_no_group_no_membership")

        output = self.run_audit_command()

        self.assert_summary_count(output, "in_sync", 1)
        self.assert_summary_count(output, "membership_without_group", 1)
        self.assert_summary_count(output, "group_without_membership", 1)
        self.assert_summary_count(output, "mismatch", 1)
        self.assert_summary_count(output, "unmapped_group", 1)
        self.assert_summary_count(output, "parent_or_fellowship_only_membership", 2)
        self.assert_summary_count(output, "no_group_no_membership", 1)
        self.assert_summary_count(
            output,
            "multiple_active_primary_memberships",
            0,
        )
        self.assertIn("Audit only:", output)

    def test_inactive_membership_lifecycle_states_do_not_count(self):
        group, unit = self.create_mapped_group("Audit Lifecycle Group")
        today = timezone.localdate()
        users = [
            User.objects.create_user(username=f"audit_inactive_{index}")
            for index in range(6)
        ]
        for user in users:
            self.assign_group(user, group)

        requested, rejected, cancelled, ended, future, expired = users
        ChurchStructureMembership.objects.create(
            user=requested,
            unit=unit,
            status=ChurchStructureMembership.STATUS_REQUESTED,
            is_primary=True,
            start_date=today,
        )
        ChurchStructureMembership.objects.bulk_create(
            [
                ChurchStructureMembership(
                    user=rejected,
                    unit=unit,
                    status=ChurchStructureMembership.STATUS_REJECTED,
                    is_primary=True,
                    start_date=today - timedelta(days=10),
                ),
                ChurchStructureMembership(
                    user=cancelled,
                    unit=unit,
                    status=ChurchStructureMembership.STATUS_CANCELLED,
                    is_primary=True,
                    start_date=today - timedelta(days=10),
                ),
                ChurchStructureMembership(
                    user=expired,
                    unit=unit,
                    status=ChurchStructureMembership.STATUS_ACTIVE,
                    is_primary=True,
                    start_date=today - timedelta(days=10),
                    end_date=today - timedelta(days=1),
                ),
            ]
        )
        ChurchStructureMembership.objects.create(
            user=ended,
            unit=unit,
            status=ChurchStructureMembership.STATUS_ENDED,
            is_primary=True,
            start_date=today - timedelta(days=10),
            end_date=today - timedelta(days=1),
        )
        ChurchStructureMembership.objects.create(
            user=future,
            unit=unit,
            status=ChurchStructureMembership.STATUS_ACTIVE,
            is_primary=True,
            start_date=today + timedelta(days=1),
        )

        output = self.run_audit_command()

        self.assert_summary_count(output, "group_without_membership", 6)
        self.assertNotIn("in_sync: 1", output)
        self.assert_summary_count(
            output,
            "multiple_active_primary_memberships",
            0,
        )

    def test_verbose_output_has_details_but_excludes_private_notes(self):
        group, unit = self.create_mapped_group("Audit Private Notes")
        user = User.objects.create_user(
            username="audit_verbose",
            first_name="Verbose",
            last_name="Member",
        )
        self.assign_group(user, group)
        membership = self.create_active_primary(
            user,
            unit,
            notes="PRIVATE PASTORAL NOTE SHOULD NOT PRINT",
        )

        output = self.run_audit_command("--verbose")

        self.assertIn(f"user_id={user.id}", output)
        self.assertIn("username=audit_verbose", output)
        self.assertIn("display_name=Verbose Member", output)
        self.assertIn(f"profile_small_group=#{group.id} Audit Private Notes", output)
        self.assertIn(f"active_primary_membership_id={membership.id}", output)
        self.assertIn("classification=in_sync", output)
        self.assertNotIn("PRIVATE PASTORAL NOTE SHOULD NOT PRINT", output)

    def test_command_performs_zero_writes(self):
        group, unit = self.create_mapped_group("Audit Read Only")
        user = User.objects.create_user(username="audit_read_only")
        self.assign_group(user, group)
        membership = self.create_active_primary(user, unit)
        before_counts = {
            "memberships": ChurchStructureMembership.objects.count(),
            "groups": SmallGroup.objects.count(),
            "units": ChurchStructureUnit.objects.count(),
            "profiles": Profile.objects.count(),
            "contexts": MinistryContext.objects.count(),
            "districts": District.objects.count(),
            "roles": ChurchRoleAssignment.objects.count(),
        }

        with CaptureQueriesContext(connection) as queries:
            output = self.run_audit_command("--verbose")

        write_sql = [
            query["sql"]
            for query in queries
            if query["sql"].lstrip().upper().startswith(
                ("INSERT", "UPDATE", "DELETE")
            )
        ]
        self.assertEqual(write_sql, [])
        self.assertIn("in_sync: 1", output)
        self.assertEqual(
            before_counts,
            {
                "memberships": ChurchStructureMembership.objects.count(),
                "groups": SmallGroup.objects.count(),
                "units": ChurchStructureUnit.objects.count(),
                "profiles": Profile.objects.count(),
                "contexts": MinistryContext.objects.count(),
                "districts": District.objects.count(),
                "roles": ChurchRoleAssignment.objects.count(),
            },
        )
        membership.refresh_from_db()
        user.profile.refresh_from_db()
        self.assertEqual(membership.unit, unit)
        self.assertEqual(user.profile.small_group, group)

    def test_multiple_active_primary_memberships_warns_without_silent_pick(self):
        first_unit = self.create_unit("AUDIT-DUP-1")
        second_unit = self.create_unit("AUDIT-DUP-2")
        SmallGroup.objects.create(
            name="Audit Duplicate 1",
            church_structure_unit=first_unit,
        )
        SmallGroup.objects.create(
            name="Audit Duplicate 2",
            church_structure_unit=second_unit,
        )
        user = User.objects.create_user(username="audit_duplicate_primary")
        today = timezone.localdate()
        ChurchStructureMembership.objects.bulk_create(
            [
                ChurchStructureMembership(
                    user=user,
                    unit=first_unit,
                    status=ChurchStructureMembership.STATUS_ACTIVE,
                    is_primary=True,
                    start_date=today,
                ),
                ChurchStructureMembership(
                    user=user,
                    unit=second_unit,
                    status=ChurchStructureMembership.STATUS_ACTIVE,
                    is_primary=True,
                    start_date=today,
                ),
            ]
        )

        output = self.run_audit_command("--verbose")

        self.assert_summary_count(
            output,
            "multiple_active_primary_memberships",
            1,
        )
        self.assertIn("WARNING: User audit_duplicate_primary", output)
        self.assertIn("multiple_active_primary_membership_ids=", output)

    def test_fail_on_drift_passes_when_only_safe_categories_exist(self):
        group, unit = self.create_mapped_group("Audit Drift Clean")
        in_sync = User.objects.create_user(username="audit_drift_in_sync")
        self.assign_group(in_sync, group)
        self.create_active_primary(in_sync, unit)
        # no_group_no_membership users are consistent, not drifted.
        User.objects.create_user(username="audit_drift_nobody")

        output = self.run_audit_command("--fail-on-drift")

        self.assert_summary_count(output, "in_sync", 1)
        self.assert_summary_count(output, "no_group_no_membership", 1)

    def test_fail_on_drift_fails_on_mismatch(self):
        group, _unit = self.create_mapped_group("Audit Drift Mismatch Group")
        other_unit = self.create_unit("AUDIT-DRIFT-MISMATCH")
        SmallGroup.objects.create(
            name="Audit Drift Mismatch Other",
            church_structure_unit=other_unit,
        )
        user = User.objects.create_user(username="audit_drift_mismatch")
        self.assign_group(user, group)
        self.create_active_primary(user, other_unit)

        with self.assertRaisesMessage(CommandError, "mismatch=1"):
            self.run_audit_command("--fail-on-drift")

    def test_fail_on_drift_fails_on_unmapped_group(self):
        unmapped_group = SmallGroup.objects.create(name="Audit Drift Unmapped")
        user = User.objects.create_user(username="audit_drift_unmapped")
        self.assign_group(user, unmapped_group)

        with self.assertRaisesMessage(CommandError, "unmapped_group=1"):
            self.run_audit_command("--fail-on-drift")

    def test_fail_on_drift_fails_on_multiple_active_primary_memberships(self):
        first_group, first_unit = self.create_mapped_group("Audit Drift Multi 1")
        _second_group, second_unit = self.create_mapped_group("Audit Drift Multi 2")
        user = User.objects.create_user(username="audit_drift_multi")
        self.assign_group(user, first_group)
        today = timezone.localdate()
        ChurchStructureMembership.objects.bulk_create(
            [
                ChurchStructureMembership(
                    user=user,
                    unit=first_unit,
                    status=ChurchStructureMembership.STATUS_ACTIVE,
                    is_primary=True,
                    start_date=today,
                ),
                ChurchStructureMembership(
                    user=user,
                    unit=second_unit,
                    status=ChurchStructureMembership.STATUS_ACTIVE,
                    is_primary=True,
                    start_date=today,
                ),
            ]
        )

        with self.assertRaisesMessage(
            CommandError, "multiple_active_primary_memberships=1"
        ):
            self.run_audit_command("--fail-on-drift")

    def test_fail_on_drift_stays_read_only_and_default_run_still_passes(self):
        unmapped_group = SmallGroup.objects.create(name="Audit Drift Read Only")
        user = User.objects.create_user(username="audit_drift_read_only")
        self.assign_group(user, unmapped_group)
        before_memberships = ChurchStructureMembership.objects.count()
        before_groups = SmallGroup.objects.count()

        with CaptureQueriesContext(connection) as queries:
            with self.assertRaises(CommandError):
                self.run_audit_command("--fail-on-drift")

        write_sql = [
            query["sql"]
            for query in queries
            if query["sql"].lstrip().upper().startswith(
                ("INSERT", "UPDATE", "DELETE")
            )
        ]
        self.assertEqual(write_sql, [])
        self.assertEqual(
            ChurchStructureMembership.objects.count(), before_memberships
        )
        self.assertEqual(SmallGroup.objects.count(), before_groups)
        user.profile.refresh_from_db()
        self.assertEqual(user.profile.small_group, unmapped_group)

        # Without the flag the same drifted data still reports and exits
        # successfully, unchanged from CS-CORE.0B.1.
        output = self.run_audit_command()
        self.assert_summary_count(output, "unmapped_group", 1)
        self.assertIn("Audit only:", output)


class ChurchStructureAdminClarityTests(TestCase):
    def setUp(self):
        self.admin_user = User.objects.create_superuser(
            username="structure_admin",
            email="structure_admin@example.com",
            password="AdminPass123!",
        )
        self.client.login(username="structure_admin", password="AdminPass123!")

    def test_legacy_small_group_admin_explains_current_runtime_source(self):
        group = SmallGroup.objects.create(name="Rainbow 4")

        response = self.client.get(
            reverse("admin:accounts_smallgroup_change", args=[group.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Legacy Small Groups")
        self.assertContains(response, "旧小组")
        self.assertContains(response, "Bible Study generation and legacy BibleStudySession")
        self.assertContains(response, "ServiceEvent zero-row fallback")
        self.assertContains(response, "Profile.small_group")
        self.assertContains(
            response,
            "Bible Study v2 meeting visibility and role/worship pickers",
        )
        self.assertContains(response, "ServiceEvent audience rows also match")
        self.assertContains(response, "active primary ChurchStructureMembership")
        self.assertContains(response, "Bridge mapping status")

    def test_legacy_district_and_ministry_context_admin_labels_are_clear(self):
        context = MinistryContext.objects.create(code="CM", name="Chinese Ministry")
        district = District.objects.create(name="一区", ministry_context=context)

        context_response = self.client.get(
            reverse("admin:accounts_ministrycontext_change", args=[context.pk])
        )
        district_response = self.client.get(
            reverse("admin:accounts_district_change", args=[district.pk])
        )

        self.assertEqual(context_response.status_code, 200)
        self.assertContains(context_response, "Ministry Contexts")
        self.assertContains(context_response, "事工范围")
        self.assertContains(context_response, "Bible Study generation")
        self.assertContains(context_response, "ServiceEvent audience rows")

        self.assertEqual(district_response.status_code, 200)
        self.assertContains(district_response, "Legacy Districts")
        self.assertContains(district_response, "旧区")
        self.assertContains(district_response, "Bible Study")
        self.assertContains(district_response, "ServiceEvent zero-row fallback")

    def test_church_structure_unit_admin_explains_future_foundation_status(self):
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
        self.assertContains(response, "flexible structure foundation")
        self.assertContains(response, "ServiceEvent audience rows use selected units")
        self.assertContains(response, "Bible Study still resolves selected units")
        self.assertContains(response, "Path label")

    def test_church_structure_membership_admin_explains_future_belonging_status(self):
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
        self.assertContains(
            response,
            "runtime source for ServiceEvent audience-row matching after CS-CORE.2B-A "
            "and Bible Study v2 meeting member visibility after CS-CORE.2C-B",
        )
        self.assertContains(
            response,
            "Profile.small_group still drives reading/progress/privacy",
        )
        self.assertContains(
            response,
            "ServiceEvent zero-row legacy fallback",
        )
        self.assertContains(
            response,
            "Membership does not grant permissions, roles, or TeamAssignment/My Serving",
        )
        self.assertContains(response, "Notes must stay operational and non-sensitive")


class ChurchRolePermissionTests(TestCase):
    def setUp(self):
        self.district = District.objects.create(name="North")
        self.other_district = District.objects.create(name="South")
        # CS-CORE.2D-B: progress permission/access is now structure-aware, so the
        # legacy district/group rows are mapped to a ChurchStructureUnit hierarchy
        # (district unit -> small-group unit) for the role-scope fallback to resolve.
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
        self.district.church_structure_unit = self.district_unit
        self.district.save()
        self.other_district.church_structure_unit = self.other_district_unit
        self.other_district.save()
        self.group = SmallGroup.objects.create(
            name="Rainbow 4",
            district=self.district,
            church_structure_unit=self.group_unit,
        )
        self.other_group = SmallGroup.objects.create(
            name="Rainbow 5",
            district=self.other_district,
            church_structure_unit=self.other_group_unit,
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

    def test_district_can_be_created_and_assigned_to_small_group(self):
        self.assertEqual(str(self.district), "North")
        self.assertEqual(self.group.district, self.district)
        self.assertIn(self.group, self.district.small_groups.all())

    def test_global_scope_rejects_district_or_small_group(self):
        assignment = ChurchRoleAssignment(
            user=self.user,
            role=ChurchRoleAssignment.ROLE_PASTOR,
            scope_type=ChurchRoleAssignment.SCOPE_GLOBAL,
            district=self.district,
            small_group=self.group,
        )

        with self.assertRaises(ValidationError):
            assignment.full_clean()

    def test_district_scope_requires_district(self):
        assignment = ChurchRoleAssignment(
            user=self.user,
            role=ChurchRoleAssignment.ROLE_DISTRICT_LEADER,
            scope_type=ChurchRoleAssignment.SCOPE_DISTRICT,
        )

        with self.assertRaises(ValidationError):
            assignment.full_clean()

    def test_small_group_scope_requires_small_group(self):
        assignment = ChurchRoleAssignment(
            user=self.user,
            role=ChurchRoleAssignment.ROLE_GROUP_LEADER,
            scope_type=ChurchRoleAssignment.SCOPE_SMALL_GROUP,
        )

        with self.assertRaises(ValidationError):
            assignment.full_clean()

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
            district=self.district,
        )

        groups = list(get_accessible_progress_groups(self.user))

        self.assertIn(self.group, groups)
        self.assertNotIn(self.other_group, groups)

    def test_group_leader_gets_only_assigned_small_group(self):
        ChurchRoleAssignment.objects.create(
            user=self.user,
            role=ChurchRoleAssignment.ROLE_GROUP_LEADER,
            scope_type=ChurchRoleAssignment.SCOPE_SMALL_GROUP,
            small_group=self.group,
        )

        groups = list(get_accessible_progress_groups(self.user))

        self.assertEqual(groups, [self.group])

    def test_regular_user_gets_own_membership_group(self):
        # CS-CORE.2D-B: own-group progress access now comes from the active primary
        # ChurchStructureMembership mapped to a small group, not Profile.small_group.
        self.create_membership(self.user, self.group_unit)

        groups = list(get_accessible_progress_groups(self.user))

        self.assertEqual(groups, [self.group])

    def test_profile_only_user_no_longer_gets_progress_access(self):
        # CS-CORE.2D-B: Profile.small_group alone no longer grants progress access.
        self.user.profile.small_group = self.group
        self.user.profile.save()

        self.assertEqual(list(get_accessible_progress_groups(self.user)), [])


class StaffMembershipRequestListTests(TestCase):
    def setUp(self):
        self.group = SmallGroup.objects.create(name="Rainbow 4")
        self.user = User.objects.create_user(
            username="request_user",
            password="TestPass123!",
        )
        self.user.profile.small_group = self.group
        self.user.profile.save()
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
        self.assertContains(response, "当前小组")
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
        self.assertContains(response, "Current active group data")
        self.assertContains(response, "Current small group")
        self.assertContains(response, "Current group update target")
        self.assertContains(response, "Group membership after approval")
        self.assertContains(response, "Approval state")
        self.assertContains(
            response,
            "Approval creates the primary membership record.",
        )
        self.assertContains(response, "No single active current small group")
        self.assertContains(response, "No existing confirmed membership")
        self.assertNotContains(response, "future foundation")
        self.assertNotContains(response, "Future church-structure foundation")
        self.assertNotContains(response, "Current runtime data")
        self.assertNotContains(response, "legacy small group")
        self.assertContains(response, "Confirm and Sync by Rule")
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
        self.assertContains(response, "目前生效的小组资料")
        self.assertContains(response, "当前小组")
        self.assertContains(response, "确认后会更新到的小组")
        self.assertContains(response, "确认后的归属记录")
        self.assertContains(response, "现有已确认归属")
        self.assertContains(
            response,
            "确认后会建立主要归属记录；只有当申请的小组正好对应一个启用中的当前小组时，才会更新目前生效的小组资料。",
        )
        self.assertNotContains(response, "未来教会架构基础")
        self.assertNotContains(response, "当前运行资料")
        self.assertNotContains(response, "确认后可同步的旧小组")

    def test_detail_shows_transfer_warning_for_different_mapped_small_group(self):
        mapped_group = SmallGroup.objects.create(
            name="Mapped Rainbow 5",
            church_structure_unit=self.unit,
        )
        membership = self.create_membership()
        session = self.client.session
        session["language"] = "en"
        session.save()
        self.client.login(username="membership_staff", password="TestPass123!")

        response = self.client.get(
            reverse("staff_membership_request_detail", args=[membership.id]),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "confirming this request will update the current active group data",
        )
        self.assertContains(response, mapped_group.name)

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
        SmallGroup.objects.create(
            name="Post Only Mapped Rainbow 4",
            church_structure_unit=self.unit,
        )
        original_group = self.user.profile.small_group
        self.client.login(username="membership_staff", password="TestPass123!")

        response = self.client.get(
            reverse("staff_membership_request_approve", args=[membership.id]),
        )

        self.assertEqual(response.status_code, 302)
        membership.refresh_from_db()
        self.user.profile.refresh_from_db()
        self.assertEqual(membership.status, ChurchStructureMembership.STATUS_REQUESTED)
        self.assertEqual(self.user.profile.small_group, original_group)

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
        original_group = self.user.profile.small_group
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
        self.assertEqual(self.user.profile.small_group, original_group)

    def test_approve_mapped_unit_updates_profile_small_group(self):
        mapped_group = SmallGroup.objects.create(
            name="Mapped Rainbow 4",
            church_structure_unit=self.unit,
        )
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
        self.assertEqual(self.user.profile.small_group, mapped_group)

    def test_approve_inactive_mapped_small_group_does_not_update_profile_small_group(self):
        SmallGroup.objects.create(
            name="Inactive Mapped Rainbow 4",
            church_structure_unit=self.unit,
            is_active=False,
        )
        membership = self.create_membership()
        original_group = self.user.profile.small_group
        self.client.login(username="membership_staff", password="TestPass123!")

        response = self.client.post(
            reverse("staff_membership_request_approve", args=[membership.id]),
        )

        self.assertEqual(response.status_code, 302)
        membership.refresh_from_db()
        self.user.profile.refresh_from_db()
        self.assertEqual(membership.status, ChurchStructureMembership.STATUS_ACTIVE)
        self.assertEqual(self.user.profile.small_group, original_group)

    def test_approve_multi_mapped_unit_does_not_update_profile_small_group(self):
        SmallGroup.objects.create(
            name="Mapped Rainbow 4A",
            church_structure_unit=self.unit,
        )
        SmallGroup.objects.create(
            name="Mapped Rainbow 4B",
            church_structure_unit=self.unit,
        )
        membership = self.create_membership()
        original_group = self.user.profile.small_group
        self.client.login(username="membership_staff", password="TestPass123!")

        response = self.client.post(
            reverse("staff_membership_request_approve", args=[membership.id]),
        )

        self.assertEqual(response.status_code, 302)
        membership.refresh_from_db()
        self.user.profile.refresh_from_db()
        self.assertEqual(membership.status, ChurchStructureMembership.STATUS_ACTIVE)
        self.assertEqual(self.user.profile.small_group, original_group)

    def test_approve_blocks_existing_active_primary_membership(self):
        membership = self.create_membership()
        mapped_group = SmallGroup.objects.create(
            name="Blocked Mapped Rainbow 4",
            church_structure_unit=self.unit,
        )
        original_group = self.user.profile.small_group
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
        self.assertEqual(self.user.profile.small_group, original_group)
        self.assertNotEqual(self.user.profile.small_group, mapped_group)

    def test_reject_changes_requested_to_rejected_and_not_primary(self):
        membership = self.create_membership(is_primary=True)
        requested_by = membership.requested_by
        original_group = self.user.profile.small_group
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
        self.assertEqual(self.user.profile.small_group, original_group)

    def test_reject_mapped_unit_does_not_update_profile_small_group(self):
        mapped_group = SmallGroup.objects.create(
            name="Rejected Mapped Rainbow 4",
            church_structure_unit=self.unit,
        )
        membership = self.create_membership(is_primary=True)
        original_group = self.user.profile.small_group
        self.client.login(username="membership_staff", password="TestPass123!")

        response = self.client.post(
            reverse("staff_membership_request_reject", args=[membership.id]),
        )

        self.assertEqual(response.status_code, 302)
        membership.refresh_from_db()
        self.user.profile.refresh_from_db()
        self.assertEqual(membership.status, ChurchStructureMembership.STATUS_REJECTED)
        self.assertEqual(self.user.profile.small_group, original_group)
        self.assertNotEqual(self.user.profile.small_group, mapped_group)

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
        district = District.objects.create(name="District 1")
        group = SmallGroup.objects.create(
            name="District Group",
            district=district,
            church_structure_unit=self.unit,
        )
        self.create_membership(user=self.normal_user)
        event = ServiceEvent.objects.create(
            title="District Service",
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
            start_datetime=timezone.now(),
            scope_type=ServiceEvent.SCOPE_DISTRICT,
            district=district,
            status=ServiceEvent.STATUS_PUBLISHED,
        )

        self.assertFalse(event.can_be_seen_by(self.normal_user))

        self.normal_user.profile.small_group = group
        self.normal_user.profile.save()

        self.assertTrue(event.can_be_seen_by(self.normal_user))

    def test_unmapped_approved_membership_does_not_change_service_event_visibility(self):
        district = District.objects.create(name="District 1")
        group = SmallGroup.objects.create(name="District Group", district=district)
        membership = self.create_membership(user=self.normal_user)
        event = ServiceEvent.objects.create(
            title="District Service",
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
            start_datetime=timezone.now(),
            scope_type=ServiceEvent.SCOPE_DISTRICT,
            district=district,
            status=ServiceEvent.STATUS_PUBLISHED,
        )
        self.client.login(username="membership_staff", password="TestPass123!")

        self.client.post(
            reverse("staff_membership_request_approve", args=[membership.id]),
        )

        self.assertFalse(event.can_be_seen_by(self.normal_user))

        self.normal_user.profile.small_group = group
        self.normal_user.profile.save()

        self.assertTrue(event.can_be_seen_by(self.normal_user))

    def test_mapped_approval_changes_service_event_visibility_through_profile_small_group(self):
        district = District.objects.create(name="Mapped District 1")
        group = SmallGroup.objects.create(
            name="Mapped District Group",
            district=district,
            church_structure_unit=self.unit,
        )
        membership = self.create_membership(user=self.normal_user)
        event = ServiceEvent.objects.create(
            title="Mapped District Service",
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
            start_datetime=timezone.now(),
            scope_type=ServiceEvent.SCOPE_DISTRICT,
            district=district,
            status=ServiceEvent.STATUS_PUBLISHED,
        )

        self.assertFalse(event.can_be_seen_by(self.normal_user))

        self.client.login(username="membership_staff", password="TestPass123!")
        self.client.post(
            reverse("staff_membership_request_approve", args=[membership.id]),
        )
        self.normal_user.profile.refresh_from_db()

        self.assertEqual(self.normal_user.profile.small_group, group)
        self.assertTrue(event.can_be_seen_by(self.normal_user))

    def test_rejected_membership_does_not_change_service_event_visibility(self):
        district = District.objects.create(name="District 1")
        group = SmallGroup.objects.create(name="District Group", district=district)
        membership = self.create_membership(user=self.normal_user)
        event = ServiceEvent.objects.create(
            title="District Service",
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
            start_datetime=timezone.now(),
            scope_type=ServiceEvent.SCOPE_DISTRICT,
            district=district,
            status=ServiceEvent.STATUS_PUBLISHED,
        )
        self.client.login(username="membership_staff", password="TestPass123!")

        self.client.post(
            reverse("staff_membership_request_reject", args=[membership.id]),
        )

        self.assertFalse(event.can_be_seen_by(self.normal_user))

        self.normal_user.profile.small_group = group
        self.normal_user.profile.save()

        self.assertTrue(event.can_be_seen_by(self.normal_user))

    def test_approved_membership_does_not_change_bible_study_scope_behavior(self):
        context = MinistryContext.objects.create(code="CM", name="Chinese Ministry")
        district = District.objects.create(
            name="District 1",
            ministry_context=context,
        )
        group = SmallGroup.objects.create(name="District Group", district=district)
        membership = self.create_membership(user=self.normal_user)
        series = BibleStudySeries.objects.create(
            title="CM Bible Study",
            scope_type=BibleStudySeries.SCOPE_MINISTRY_CONTEXT,
            ministry_context=context,
        )
        self.client.login(username="membership_staff", password="TestPass123!")

        self.client.post(
            reverse("staff_membership_request_approve", args=[membership.id]),
        )

        self.assertEqual(list(series.get_eligible_small_groups()), [group])

    def test_mapped_approval_keeps_bible_study_scope_legacy_group_based(self):
        context = MinistryContext.objects.create(code="CM", name="Chinese Ministry")
        district = District.objects.create(
            name="Mapped District 2",
            ministry_context=context,
        )
        group = SmallGroup.objects.create(
            name="Mapped Bible Study Group",
            district=district,
            church_structure_unit=self.unit,
        )
        membership = self.create_membership(user=self.normal_user)
        series = BibleStudySeries.objects.create(
            title="Mapped CM Bible Study",
            scope_type=BibleStudySeries.SCOPE_MINISTRY_CONTEXT,
            ministry_context=context,
        )
        session = BibleStudySession.objects.create(
            series=series,
            title="Mapped Group Study",
            study_datetime=timezone.now(),
            scope_type=BibleStudySession.SCOPE_SMALL_GROUP,
            small_group=group,
            status=BibleStudySession.STATUS_PUBLISHED,
        )

        self.assertEqual(list(series.get_eligible_small_groups()), [group])
        self.assertIsNone(self.normal_user.profile.small_group)
        self.assertFalse(session.can_be_seen_by(self.normal_user))

        self.client.login(username="membership_staff", password="TestPass123!")
        self.client.post(
            reverse("staff_membership_request_approve", args=[membership.id]),
        )
        self.normal_user.profile.refresh_from_db()

        self.assertEqual(self.normal_user.profile.small_group, group)
        self.assertEqual(list(series.get_eligible_small_groups()), [group])
        self.assertTrue(session.can_be_seen_by(self.normal_user))


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
        self.group = SmallGroup.objects.create(name="Overview Group")
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
        BibleStudyMeeting.objects.create(
            lesson=upcoming_lesson,
            small_group=self.group,
            meeting_datetime=now + timedelta(days=2),
            status=BibleStudyMeeting.STATUS_DRAFT,
        )
        BibleStudyMeeting.objects.create(
            lesson=upcoming_lesson,
            small_group=SmallGroup.objects.create(name="Overview Group 2"),
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
        self.assertContains(response, "existing one-mapped-group rule")
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
        self.group = SmallGroup.objects.create(
            name="Structure Rainbow 4",
            church_structure_unit=self.group_unit,
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
        self.assertContains(response, "Structure Rainbow 4")
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
        self.assertContains(response, "当前资料对应")
        self.assertNotContains(response, "现有记录")
        self.assertContains(response, "全教会")
        self.assertContains(response, "中文部")

    def test_unmapped_active_legacy_rows_are_counted(self):
        self.build_tree()
        MinistryContext.objects.create(code="EMX", name="Unmapped Context")
        District.objects.create(name="Unmapped District")
        SmallGroup.objects.create(name="Unmapped Group")
        self.login_staff()

        response = self.client.get(self.url)
        indicators = response.context["indicators"]

        self.assertEqual(indicators["unmapped_ministry_contexts"], 1)
        self.assertEqual(indicators["unmapped_districts"], 1)
        # The mapped group from build_tree is not counted.
        self.assertEqual(indicators["unmapped_small_groups"], 1)

    def test_units_without_linked_records_at_or_beneath(self):
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

        # Only the custom unit is flagged: cm/district units have a mapped
        # descendant, the group unit is mapped itself, and the root is excluded.
        self.assertEqual(indicators["units_without_linked_records"], 1)
        flagged = [
            row["unit"].code
            for row in response.context["structure_rows"]
            if row["without_linked_records"]
        ]
        self.assertEqual(flagged, ["NEWMIN"])

    def test_units_under_holding_nodes_are_counted(self):
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

        # The holding node itself is not "under" a holding node; its child is.
        self.assertEqual(indicators["units_under_holding"], 1)

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

    def test_structure_map_uses_awaiting_placement_wording_en(self):
        # CS-UX.1B: staff-facing "holding/unassigned" wording is replaced with
        # clearer "awaiting placement" language. Internal codes are unchanged.
        self._build_tree_with_holding_child()
        self.set_language("en")
        self.login_staff()

        response = self.client.get(self.url)
        content = response.content.decode()

        self.assertIn("Units in awaiting-placement area", content)
        self.assertIn("Awaiting placement", content)
        self.assertNotIn("Unassigned holding", content)
        self.assertNotIn("unassigned holding nodes", content)
        self.assertNotIn("holding/unassigned", content)

    def test_structure_map_uses_awaiting_placement_wording_zh(self):
        self._build_tree_with_holding_child()
        self.set_language("zh")
        self.login_staff()

        response = self.client.get(self.url)
        content = response.content.decode()

        self.assertIn("待安排", content)
        self.assertIn("待安排区域", content)
        self.assertNotIn("未分配暂存", content)
        self.assertNotIn("未分配暂存节点", content)

    def test_users_in_unmapped_group_are_counted(self):
        self.build_tree()
        unmapped_group = SmallGroup.objects.create(name="Unmapped Member Group")
        profile = self.normal_user.profile
        profile.small_group = unmapped_group
        profile.save()
        self.login_staff()

        response = self.client.get(self.url)
        indicators = response.context["indicators"]

        self.assertEqual(indicators["users_in_unmapped_group"], 1)

    def test_membership_and_group_drift_categories_are_counted_separately(self):
        self.build_tree()
        member_only = User.objects.create_user(
            username="drift_member_only",
            password="DriftPass123!",
        )
        self.create_active_primary_membership(member_only, self.group_unit)

        group_only = User.objects.create_user(
            username="drift_group_only",
            password="DriftPass123!",
        )
        group_only_profile = group_only.profile
        group_only_profile.small_group = self.group
        group_only_profile.save()

        mismatch_user = User.objects.create_user(
            username="drift_mismatch",
            password="DriftPass123!",
        )
        mismatch_profile = mismatch_user.profile
        mismatch_profile.small_group = self.group
        mismatch_profile.save()
        self.create_active_primary_membership(mismatch_user, self.cm_unit)

        self.login_staff()

        response = self.client.get(self.url)
        indicators = response.context["indicators"]

        self.assertEqual(indicators["membership_without_group"], 1)
        self.assertEqual(indicators["group_without_membership"], 1)
        self.assertEqual(indicators["membership_group_mismatch"], 1)

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

    def test_structure_map_shows_current_data_mapping_label(self):
        self.build_tree()
        self.set_language("en")
        self.login_staff()

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Current data mapping")
        self.assertContains(response, "Structure Rainbow 4")

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

    def test_inactive_units_still_referenced_are_counted(self):
        self.build_tree()
        inactive_unit = ChurchStructureUnit.objects.create(
            parent=self.cm_unit,
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="RETIRED",
            name="Retired Unit",
            is_active=False,
        )
        SmallGroup.objects.create(
            name="Group Mapped To Retired Unit",
            church_structure_unit=inactive_unit,
        )
        self.login_staff()

        response = self.client.get(self.url)
        indicators = response.context["indicators"]

        self.assertEqual(indicators["inactive_units_still_referenced"], 1)

    def test_staff_overview_links_to_structure_map(self):
        self.set_language("en")
        self.login_staff()

        response = self.client.get(reverse("staff_overview"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.url)
        self.assertContains(response, "Structure & Setup Check")


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

    # --- view / edit mode ---------------------------------------------------

    def test_default_view_has_no_action_menus(self):
        self.set_language("en")
        self.login_admin()

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["edit_mode"])
        self.assertNotContains(response, "structure-row-actions")
        self.assertNotContains(response, "Edit mode:")
        # The entry point into edit mode is offered to admin users.
        self.assertContains(response, "Edit structure")

    def test_edit_mode_shows_banner_and_action_menus(self):
        self.set_language("en")
        self.login_admin()

        response = self.client.get(self.url, {"edit": "1"})

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["edit_mode"])
        self.assertContains(response, "Edit mode:")
        self.assertContains(response, "structure-row-actions")
        self.assertContains(response, "Exit edit mode")

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
        self.assertNotContains(forced, "structure-row-actions")

    def test_details_link_visible_only_for_admin(self):
        self.set_language("en")
        admin_change_url = reverse(
            "admin:accounts_churchstructureunit_change", args=[self.child.id]
        )

        self.login_admin()
        admin_resp = self.client.get(self.url, {"edit": "1"})
        self.assertContains(admin_resp, admin_change_url)

        self.client.logout()
        self.login_viewer()
        viewer_resp = self.client.get(self.url, {"edit": "1"})
        self.assertNotContains(viewer_resp, admin_change_url)

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
    """CS-SETUP.1C.1: read-only legacy -> structure mapping review page."""

    def setUp(self):
        # Superuser holds every change permission implicitly.
        self.admin = User.objects.create_user(
            username="mapping_admin",
            password="AdminPass123!",
            is_staff=True,
            is_superuser=True,
        )
        # Staff who can view the page but hold no model change permissions.
        self.viewer = User.objects.create_user(
            username="mapping_viewer",
            password="ViewerPass123!",
            is_staff=True,
        )
        self.normal_user = User.objects.create_user(
            username="mapping_plain",
            password="PlainPass123!",
        )
        self.url = reverse("staff_structure_mapping_review")

        self.root = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_ROOT,
            code="CHURCH",
            name="全教会",
            name_en="Whole Church",
        )
        self.active_unit = ChurchStructureUnit.objects.create(
            parent=self.root,
            unit_type=ChurchStructureUnit.UNIT_DISTRICT,
            code="D2",
            name="二区",
            name_en="District 2",
        )
        self.inactive_unit = ChurchStructureUnit.objects.create(
            parent=self.root,
            unit_type=ChurchStructureUnit.UNIT_DISTRICT,
            code="D9",
            name="旧区",
            name_en="Old District",
            is_active=False,
        )

    def set_language(self, language="en"):
        session = self.client.session
        session["language"] = language
        session.save()

    def login_admin(self):
        self.client.login(username="mapping_admin", password="AdminPass123!")

    def login_viewer(self):
        self.client.login(username="mapping_viewer", password="ViewerPass123!")

    # --- access control -----------------------------------------------------

    def test_anonymous_user_redirected_to_login(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response.url)

    def test_normal_user_denied(self):
        self.client.login(username="mapping_plain", password="PlainPass123!")

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response.url)

    def test_staff_user_allowed(self):
        self.login_viewer()

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)

    # --- sections / content -------------------------------------------------

    def test_page_renders_three_mapping_sections(self):
        self.set_language("en")
        self.login_viewer()

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Structure Mapping Review")
        self.assertContains(response, "Ministry Contexts")
        self.assertContains(response, "Districts")
        self.assertContains(response, "Small Groups")
        # Staff-facing column wording: "Current record" replaces the internal
        # "Legacy record" architecture label.
        self.assertContains(response, "Current record")
        self.assertNotContains(response, "Legacy record")
        # The page is no longer labelled read-only now that authorized staff
        # can edit one mapping at a time; the safety note scopes mapping edits.
        self.assertNotContains(response, "Read-only page")
        # CS-SETUP.1D.4: the safety copy no longer claims (too absolutely) that
        # mapping edits never change who can see content / visibility.
        self.assertNotContains(response, "who can see content (visibility)")
        self.assertNotContains(
            response, "Mapping edits update setup mapping only."
        )
        self.assertContains(
            response,
            "edit one setup mapping at a time",
        )
        # The boundary names the direct non-effects ...
        self.assertContains(
            response,
            "A mapping edit does not directly edit members, audience rows, serving schedules, or permissions.",
        )
        # ... and is honest about the post-CS-CORE.2B-A split: ServiceEvent
        # audience-row matching moved to membership, while Bible Study still
        # resolves through the mapping bridge.
        self.assertContains(
            response,
            "mapping edits no longer affect ServiceEvent structure-audience row matching",
        )
        self.assertContains(
            response,
            "ServiceEvent audience rows match by active primary ChurchStructureMembership",
        )
        self.assertContains(
            response,
            "Mapping edits can still affect Bible Study structure-audience resolution and generated legacy SmallGroup meetings.",
        )
        self.assertContains(
            response,
            "ServiceEvents with no audience rows still use legacy fallback via Profile.small_group",
        )
        self.assertNotContains(
            response,
            "Because structure-based ServiceEvent and Bible Study scopes use these links to match current groups",
        )
        self.assertNotContains(
            response,
            "may affect who matches those structure-based scopes",
        )

    def test_bilingual_labels_in_chinese(self):
        self.set_language("zh")
        self.login_viewer()

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "教会结构对应检查")
        self.assertContains(response, "事工范围")
        self.assertContains(response, "区")
        self.assertContains(response, "小组")
        self.assertContains(response, "现有记录")
        self.assertNotContains(response, "只读页面")
        # CS-CORE.2B-B: corrected, honest ZH safety copy.
        self.assertContains(
            response,
            "编辑对应关系不会直接编辑成员、适用范围记录、服事安排或权限",
        )
        self.assertContains(
            response,
            "ServiceEvent / 教会聚会中已经选择结构适用范围的记录，不再因为这里的对应关系改变而改变匹配",
        )
        self.assertContains(
            response,
            "按已生效的主要 ChurchStructureMembership / 教会结构归属来匹配",
        )
        self.assertContains(
            response,
            "对应关系改变仍可能影响查经安排解析和生成的小组查经聚会",
        )
        self.assertContains(
            response,
            "没有结构适用范围记录的旧版教会聚会仍按 Profile.small_group 的旧版 fallback 运作",
        )
        self.assertNotContains(
            response,
            "修改对应关系可能影响哪些人被匹配到这些结构适用范围",
        )
        self.assertContains(
            response,
            "有权限时可逐条编辑设置对应关系",
        )

    def test_mapping_review_uses_awaiting_placement_wording_en(self):
        # CS-UX.1B: replace "Mapped under holding/unassigned node" with the
        # clearer "Linked to awaiting-placement area" label. The internal
        # ?status=mapped_holding key is intentionally unchanged.
        self.set_language("en")
        self.login_viewer()

        response = self.client.get(self.url)

        self.assertContains(response, "Linked to awaiting-placement area")
        self.assertNotContains(response, "Mapped under holding/unassigned node")
        self.assertNotContains(response, "holding/unassigned")
        # Status key must keep working unchanged.
        self.assertContains(response, "?status=mapped_holding")

    def test_mapping_review_uses_awaiting_placement_wording_zh(self):
        self.set_language("zh")
        self.login_viewer()

        response = self.client.get(self.url)

        self.assertContains(response, "已对应到待安排区域")
        self.assertNotContains(response, "已对应到未分配暂存节点")
        self.assertNotContains(response, "未分配暂存")

    def test_mapped_active_row_display(self):
        self.set_language("en")
        SmallGroup.objects.create(
            name="Rainbow Active",
            church_structure_unit=self.active_unit,
        )
        self.login_viewer()

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Rainbow Active")
        # Path label of the mapped unit is shown.
        self.assertContains(response, "Whole Church &gt; District 2")
        self.assertContains(response, "Mapped to active unit")

    def test_unmapped_row_display(self):
        self.set_language("en")
        District.objects.create(name="Lonely District")
        self.login_viewer()

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Lonely District")
        self.assertContains(response, "Unmapped")

    def test_mapped_to_inactive_unit_display(self):
        self.set_language("en")
        SmallGroup.objects.create(
            name="Rainbow Stale",
            church_structure_unit=self.inactive_unit,
        )
        self.login_viewer()

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Rainbow Stale")
        self.assertContains(response, "Mapped to inactive unit")

    # --- admin link permission gating --------------------------------------

    def test_admin_links_visible_for_admin(self):
        self.set_language("en")
        group = SmallGroup.objects.create(
            name="Rainbow Linked",
            church_structure_unit=self.active_unit,
        )
        legacy_change_url = reverse(
            "admin:accounts_smallgroup_change", args=[group.id]
        )
        unit_change_url = reverse(
            "admin:accounts_churchstructureunit_change",
            args=[self.active_unit.id],
        )
        self.login_admin()

        response = self.client.get(self.url)

        self.assertContains(response, legacy_change_url)
        self.assertContains(response, unit_change_url)

    def test_admin_links_hidden_for_view_only_staff(self):
        self.set_language("en")
        group = SmallGroup.objects.create(
            name="Rainbow Linked",
            church_structure_unit=self.active_unit,
        )
        legacy_change_url = reverse(
            "admin:accounts_smallgroup_change", args=[group.id]
        )
        unit_change_url = reverse(
            "admin:accounts_churchstructureunit_change",
            args=[self.active_unit.id],
        )
        self.login_viewer()

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, legacy_change_url)
        self.assertNotContains(response, unit_change_url)

    # --- read-only enforcement ---------------------------------------------

    def test_page_rejects_post(self):
        self.login_admin()

        response = self.client.post(self.url)

        self.assertEqual(response.status_code, 405)

    def test_page_has_no_inline_edit_affordances(self):
        # Review-only: the page exposes no inline editing affordances. The
        # base chrome legitimately has language/logout forms, so we assert the
        # absence of mapping/rename edit controls rather than any <form> tag.
        self.set_language("en")
        SmallGroup.objects.create(
            name="Rainbow Linked",
            church_structure_unit=self.active_unit,
        )
        self.login_admin()

        response = self.client.get(self.url)

        # No rename form fields from the CS-SETUP.1B edit mode leak in here.
        self.assertNotContains(response, 'name="name_en"')
        # No in-app rename/write endpoint is targeted by this page.
        self.assertNotContains(
            response,
            reverse(
                "staff_structure_unit_rename", args=[self.active_unit.id]
            ),
        )
        # No Save control on this review page.
        self.assertNotContains(response, "保存")

    # --- link from structure map -------------------------------------------

    def test_structure_map_links_to_mapping_review(self):
        self.login_viewer()

        response = self.client.get(reverse("staff_structure_map"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.url)

    # --- CS-SETUP.1C.2: summary counts + status filters --------------------

    def _seed_one_of_each_status(self):
        """Create exactly one SmallGroup per mapping status for filter tests."""
        holding = ChurchStructureUnit.objects.create(
            parent=self.root,
            unit_type=ChurchStructureUnit.UNIT_DISTRICT,
            code="UNASSIGNED-GROUPS",
            name="未分配小组",
            name_en="Unassigned Groups",
        )
        return {
            "mapped_active": SmallGroup.objects.create(
                name="Filter Active",
                church_structure_unit=self.active_unit,
            ),
            "unmapped": SmallGroup.objects.create(name="Filter Unmapped"),
            "mapped_inactive": SmallGroup.objects.create(
                name="Filter Inactive",
                church_structure_unit=self.inactive_unit,
            ),
            "mapped_holding": SmallGroup.objects.create(
                name="Filter Holding",
                church_structure_unit=holding,
            ),
        }

    def test_summary_counts_render(self):
        self.set_language("en")
        self._seed_one_of_each_status()
        self.login_viewer()

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        counts = response.context["counts"]
        self.assertEqual(counts["all"], 4)
        self.assertEqual(counts["mapped_active"], 1)
        self.assertEqual(counts["unmapped"], 1)
        self.assertEqual(counts["mapped_inactive"], 1)
        self.assertEqual(counts["mapped_holding"], 1)
        # needs_review = unmapped + mapped_inactive + mapped_holding.
        self.assertEqual(counts["needs_review"], 3)
        self.assertContains(response, "Mapping status overview")

    def test_default_page_shows_all_rows(self):
        self.set_language("en")
        self._seed_one_of_each_status()
        self.login_viewer()

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["status"], "all")
        for name in (
            "Filter Active",
            "Filter Unmapped",
            "Filter Inactive",
            "Filter Holding",
        ):
            self.assertContains(response, name)

    def test_needs_review_filter_hides_mapped_active(self):
        self.set_language("en")
        self._seed_one_of_each_status()
        self.login_viewer()

        response = self.client.get(self.url, {"status": "needs_review"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["status"], "needs_review")
        # Attention rows are shown.
        self.assertContains(response, "Filter Unmapped")
        self.assertContains(response, "Filter Inactive")
        self.assertContains(response, "Filter Holding")
        # Mapped-active row is hidden.
        self.assertNotContains(response, "Filter Active")

    def test_individual_status_filters(self):
        self.set_language("en")
        self._seed_one_of_each_status()
        self.login_viewer()

        cases = {
            "mapped_active": (
                "Filter Active",
                ["Filter Unmapped", "Filter Inactive", "Filter Holding"],
            ),
            "unmapped": (
                "Filter Unmapped",
                ["Filter Active", "Filter Inactive", "Filter Holding"],
            ),
            "mapped_inactive": (
                "Filter Inactive",
                ["Filter Active", "Filter Unmapped", "Filter Holding"],
            ),
            "mapped_holding": (
                "Filter Holding",
                ["Filter Active", "Filter Unmapped", "Filter Inactive"],
            ),
        }
        for status, (shown, hidden_rows) in cases.items():
            with self.subTest(status=status):
                response = self.client.get(self.url, {"status": status})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.context["status"], status)
                self.assertContains(response, shown)
                for name in hidden_rows:
                    self.assertNotContains(response, name)

    def test_unknown_status_falls_back_to_all(self):
        self.set_language("en")
        self._seed_one_of_each_status()
        self.login_viewer()

        response = self.client.get(self.url, {"status": "bogus"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["status"], "all")
        self.assertContains(response, "Filter Active")

    def test_filter_links_present_and_read_only(self):
        self.set_language("en")
        self._seed_one_of_each_status()
        self.login_admin()

        response = self.client.get(self.url, {"status": "needs_review"})

        self.assertEqual(response.status_code, 200)
        # GET-only filter links are present.
        for href in (
            "?status=all",
            "?status=needs_review",
            "?status=mapped_active",
            "?status=unmapped",
            "?status=mapped_inactive",
            "?status=mapped_holding",
        ):
            self.assertContains(response, href)
        # Filtering exposes no write affordances even for a full admin.
        self.assertNotContains(response, 'name="name_en"')
        self.assertNotContains(response, "保存")

    def test_filtered_section_shows_empty_state(self):
        # Only an unmapped District exists; filtering to mapped_active leaves
        # every section empty and must show the filter empty state.
        self.set_language("en")
        District.objects.create(name="Filter Empty District")
        self.login_viewer()

        response = self.client.get(self.url, {"status": "mapped_active"})

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Filter Empty District")
        self.assertContains(response, "No records match this filter.")

    def test_filtered_post_remains_405(self):
        self.login_admin()

        response = self.client.post(self.url, {"status": "needs_review"})

        self.assertEqual(response.status_code, 405)

    def test_bilingual_status_filter_labels(self):
        self.set_language("zh")
        self._seed_one_of_each_status()
        self.login_viewer()

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "对应状态总览")
        self.assertContains(response, "需要检查")

    # --- CS-SETUP.1D.2: conflict overlays + scope copy ---------------------

    def test_scope_copy_names_direct_non_effects_and_scope_impact(self):
        # CS-CORE.2B-B: the page must name the direct non-effects (members,
        # audience rows, schedules, permissions) AND distinguish ServiceEvent
        # membership matching from Bible Study mapping-bridge resolution.
        self.set_language("en")
        self.login_viewer()

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "This page reviews and edits how current records link to church "
            "structure units.",
        )
        self.assertContains(
            response,
            "A mapping edit does not directly edit members, audience rows, "
            "serving schedules, or permissions.",
        )
        self.assertContains(
            response,
            "mapping edits no longer affect ServiceEvent structure-audience "
            "row matching",
        )
        self.assertContains(
            response,
            "ServiceEvent audience rows match by active primary "
            "ChurchStructureMembership",
        )
        self.assertContains(
            response,
            "Mapping edits can still affect Bible Study structure-audience "
            "resolution and generated legacy SmallGroup meetings.",
        )
        self.assertContains(
            response,
            "ServiceEvents with no audience rows still use legacy fallback via "
            "Profile.small_group",
        )
        self.assertNotContains(
            response,
            "structure-based ServiceEvent and Bible Study scopes",
        )
        self.assertNotContains(
            response,
            "may affect who matches those structure-based scopes",
        )
        self.assertNotContains(response, "legacy-record")

    def test_conflict_summary_cards_render(self):
        self.set_language("en")
        self.login_viewer()

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Conflicts / warnings (total)")
        self.assertContains(response, "Type mismatch")
        self.assertContains(response, "Duplicate active mapping")
        # The help text explains the conflict checks are display-only.
        self.assertContains(
            response, "Conflicts / warnings are data checks only"
        )

    def test_duplicate_active_mapping_flagged_and_counted(self):
        self.set_language("en")
        # Two active districts mapped to the same active district unit: a
        # detectable duplicate-active conflict (same legacy kind, same unit).
        District.objects.create(
            name="Dup District A", church_structure_unit=self.active_unit
        )
        District.objects.create(
            name="Dup District B", church_structure_unit=self.active_unit
        )
        self.login_viewer()

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        counts = response.context["counts"]
        self.assertEqual(counts["duplicate_active"], 2)
        self.assertEqual(counts["type_mismatch"], 0)
        self.assertEqual(counts["conflicts"], 2)
        self.assertContains(response, "Duplicate active mapping")

    def test_inactive_twin_is_not_a_duplicate_conflict(self):
        self.set_language("en")
        # Only one *active* row maps to the unit; an inactive twin must not
        # turn it into a duplicate-active conflict, matching the edit guard.
        District.objects.create(
            name="Active Solo", church_structure_unit=self.active_unit
        )
        District.objects.create(
            name="Inactive Twin",
            church_structure_unit=self.active_unit,
            is_active=False,
        )
        self.login_viewer()

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        counts = response.context["counts"]
        self.assertEqual(counts["duplicate_active"], 0)
        self.assertEqual(counts["conflicts"], 0)
        # No per-row conflict badge is rendered (summary-card labels still
        # mention the term, so target the danger-badge form specifically).
        self.assertNotContains(
            response, 'status-danger">Duplicate active mapping'
        )

    def test_type_mismatch_flagged_and_counted(self):
        self.set_language("en")
        # A SmallGroup mapped to a District-type unit is a detectable type
        # mismatch (constructible from current data / a direct Admin edit).
        SmallGroup.objects.create(
            name="Mistyped Group", church_structure_unit=self.active_unit
        )
        self.login_viewer()

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        counts = response.context["counts"]
        self.assertEqual(counts["type_mismatch"], 1)
        self.assertEqual(counts["duplicate_active"], 0)
        self.assertEqual(counts["conflicts"], 1)
        self.assertContains(response, "Type mismatch")

    def test_conflict_overlay_keeps_primary_status(self):
        # A duplicate active mapping is still counted under its primary
        # status_key (mapped_active); the overlay is additive, not replacing.
        self.set_language("en")
        District.objects.create(
            name="Dual A", church_structure_unit=self.active_unit
        )
        District.objects.create(
            name="Dual B", church_structure_unit=self.active_unit
        )
        self.login_viewer()

        response = self.client.get(self.url)

        counts = response.context["counts"]
        self.assertEqual(counts["mapped_active"], 2)
        self.assertEqual(counts["duplicate_active"], 2)

    # --- CS-SETUP.1D.3: display-only overlay (conflict) filters -------------

    def _seed_conflict_mix(self):
        """Seed one type-mismatch, two duplicate-active, and one clean row.

        Every row is primary status ``mapped_active``; the overlay filters must
        narrow by conflict flag, not by primary status_key. Returns the row
        labels keyed by intent so assertions stay readable.
        """
        clean_unit = ChurchStructureUnit.objects.create(
            parent=self.root,
            unit_type=ChurchStructureUnit.UNIT_DISTRICT,
            code="D3",
            name="三区",
            name_en="District 3",
        )
        # SmallGroup mapped to a District-type unit -> type mismatch only.
        SmallGroup.objects.create(
            name="TM Mismatch Group",
            church_structure_unit=self.active_unit,
        )
        # Two active Districts on the same unit -> duplicate-active (no
        # type mismatch, since District rows expect a District unit).
        District.objects.create(
            name="Dup Alpha District", church_structure_unit=self.active_unit
        )
        District.objects.create(
            name="Dup Beta District", church_structure_unit=self.active_unit
        )
        # A lone District on its own active unit -> clean, no overlay.
        District.objects.create(
            name="Clean Solo District", church_structure_unit=clean_unit
        )
        return {
            "type_mismatch": "TM Mismatch Group",
            "duplicate_active": ["Dup Alpha District", "Dup Beta District"],
            "clean": "Clean Solo District",
        }

    def test_overlay_filter_links_render_with_counts(self):
        self.set_language("en")
        self._seed_conflict_mix()
        self.login_viewer()

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        # The three overlay filter links are present alongside the primary set.
        for href in (
            "?status=conflicts",
            "?status=type_mismatch",
            "?status=duplicate_active",
        ):
            self.assertContains(response, href)
        counts = response.context["counts"]
        self.assertEqual(counts["type_mismatch"], 1)
        self.assertEqual(counts["duplicate_active"], 2)
        self.assertEqual(counts["conflicts"], 3)
        # Primary status totals stay true totals (all four rows mapped_active).
        self.assertEqual(counts["all"], 4)
        self.assertEqual(counts["mapped_active"], 4)

    def test_conflicts_filter_shows_either_overlay(self):
        self.set_language("en")
        labels = self._seed_conflict_mix()
        self.login_viewer()

        response = self.client.get(self.url, {"status": "conflicts"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["status"], "conflicts")
        # Both overlay kinds are shown.
        self.assertContains(response, labels["type_mismatch"])
        for name in labels["duplicate_active"]:
            self.assertContains(response, name)
        # The clean mapped_active row is hidden.
        self.assertNotContains(response, labels["clean"])

    def test_type_mismatch_filter_shows_only_type_mismatch(self):
        self.set_language("en")
        labels = self._seed_conflict_mix()
        self.login_viewer()

        response = self.client.get(self.url, {"status": "type_mismatch"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["status"], "type_mismatch")
        self.assertContains(response, labels["type_mismatch"])
        for name in labels["duplicate_active"]:
            self.assertNotContains(response, name)
        self.assertNotContains(response, labels["clean"])

    def test_duplicate_active_filter_shows_only_duplicates(self):
        self.set_language("en")
        labels = self._seed_conflict_mix()
        self.login_viewer()

        response = self.client.get(self.url, {"status": "duplicate_active"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["status"], "duplicate_active")
        for name in labels["duplicate_active"]:
            self.assertContains(response, name)
        self.assertNotContains(response, labels["type_mismatch"])
        self.assertNotContains(response, labels["clean"])

    def test_primary_filter_keeps_overlay_badges(self):
        # Filtering by a primary status must not strip the display-only overlay
        # badges from rows that carry them.
        self.set_language("en")
        self._seed_conflict_mix()
        self.login_viewer()

        response = self.client.get(self.url, {"status": "mapped_active"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["status"], "mapped_active")
        # Overlay badges survive a primary-status filter.
        self.assertContains(response, 'status-danger">Type mismatch')
        self.assertContains(response, 'status-danger">Duplicate active mapping')
        # Overlay counts remain true totals under a primary filter.
        counts = response.context["counts"]
        self.assertEqual(counts["type_mismatch"], 1)
        self.assertEqual(counts["duplicate_active"], 2)
        self.assertEqual(counts["conflicts"], 3)

    def test_unknown_status_with_conflicts_falls_back_to_all(self):
        self.set_language("en")
        labels = self._seed_conflict_mix()
        self.login_viewer()

        response = self.client.get(self.url, {"status": "not_a_status"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["status"], "all")
        # Every row is shown under the safe fallback.
        self.assertContains(response, labels["clean"])
        self.assertContains(response, labels["type_mismatch"])

    def test_overlay_filter_edit_links_preserve_status(self):
        # Edit links must round-trip the overlay status value so the return URL
        # lands back on the same filter.
        self.set_language("en")
        group = SmallGroup.objects.create(
            name="TM Mismatch Group",
            church_structure_unit=self.active_unit,
        )
        edit_url = reverse(
            "staff_structure_mapping_edit", args=["small-group", group.pk]
        )
        self.login_admin()

        response = self.client.get(self.url, {"status": "type_mismatch"})

        self.assertEqual(response.status_code, 200)
        # The per-row edit action carries the overlay status onward.
        self.assertContains(response, f"{edit_url}?status=type_mismatch")


class StaffStructureMappingEditTests(TestCase):
    """CS-SETUP.1D.1: one-row-at-a-time legacy -> structure mapping edit."""

    def setUp(self):
        # Superuser holds every change permission implicitly.
        self.admin = User.objects.create_user(
            username="map_edit_admin",
            password="AdminPass123!",
            is_staff=True,
            is_superuser=True,
        )
        # Staff who can view structure pages but hold no model change perms.
        self.viewer = User.objects.create_user(
            username="map_edit_viewer",
            password="ViewerPass123!",
            is_staff=True,
        )
        # Staff authorized for SmallGroup mappings only.
        self.sg_staff = User.objects.create_user(
            username="map_edit_sg",
            password="SgPass123!",
            is_staff=True,
        )
        from django.contrib.auth.models import Permission

        self.sg_staff.user_permissions.add(
            Permission.objects.get(
                codename="change_smallgroup",
                content_type__app_label="accounts",
            )
        )
        self.normal_user = User.objects.create_user(
            username="map_edit_plain",
            password="PlainPass123!",
        )

        self.root = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_ROOT,
            code="CHURCH",
            name="全教会",
            name_en="Whole Church",
        )
        self.sg_unit_1 = ChurchStructureUnit.objects.create(
            parent=self.root,
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="SGU1",
            name="彩虹单元",
            name_en="Rainbow Unit",
        )
        self.sg_unit_2 = ChurchStructureUnit.objects.create(
            parent=self.root,
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="SGU2",
            name="日出单元",
            name_en="Sunrise Unit",
        )
        self.sg_unit_inactive = ChurchStructureUnit.objects.create(
            parent=self.root,
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="SGU9",
            name="旧单元",
            name_en="Old Unit",
            is_active=False,
        )
        self.district_unit = ChurchStructureUnit.objects.create(
            parent=self.root,
            unit_type=ChurchStructureUnit.UNIT_DISTRICT,
            code="DU1",
            name="北区",
            name_en="North District",
        )

        self.group = SmallGroup.objects.create(name="Editable Group")

        self.review_url = reverse("staff_structure_mapping_review")

    def edit_url(self, legacy_type, pk):
        return reverse(
            "staff_structure_mapping_edit", args=[legacy_type, pk]
        )

    def set_language(self, language="en"):
        session = self.client.session
        session["language"] = language
        session.save()

    def login_admin(self):
        self.client.login(username="map_edit_admin", password="AdminPass123!")

    def login_viewer(self):
        self.client.login(
            username="map_edit_viewer", password="ViewerPass123!"
        )

    def login_sg_staff(self):
        self.client.login(username="map_edit_sg", password="SgPass123!")

    # --- entry point / action visibility ------------------------------------

    def test_unauthorized_staff_sees_no_edit_action(self):
        self.set_language("en")
        self.login_viewer()

        response = self.client.get(self.review_url)

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Edit Mapping")
        self.assertNotContains(
            response, self.edit_url("small-group", self.group.pk)
        )

    def test_authorized_staff_sees_edit_action_for_permitted_rows(self):
        self.set_language("en")
        District.objects.create(name="No-Perm District")
        self.login_sg_staff()

        response = self.client.get(self.review_url)

        self.assertEqual(response.status_code, 200)
        # SmallGroup rows expose the in-app edit action.
        self.assertContains(response, "Edit Mapping")
        self.assertContains(
            response, self.edit_url("small-group", self.group.pk)
        )
        # District rows do not, because this staff lacks change_district.
        self.assertNotContains(response, "/district/")

    # --- permission gating on the edit view ---------------------------------

    def test_normal_user_redirected(self):
        self.client.login(username="map_edit_plain", password="PlainPass123!")

        response = self.client.get(
            self.edit_url("small-group", self.group.pk)
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response.url)

    def test_view_only_staff_cannot_get_or_post(self):
        self.login_viewer()
        url = self.edit_url("small-group", self.group.pk)

        get_response = self.client.get(url)
        self.assertEqual(get_response.status_code, 403)

        post_response = self.client.post(
            url, {"church_structure_unit": self.sg_unit_1.pk}
        )
        self.assertEqual(post_response.status_code, 403)
        self.group.refresh_from_db()
        self.assertIsNone(self.group.church_structure_unit_id)

    def test_unknown_legacy_type_is_404(self):
        self.login_admin()

        response = self.client.get(self.edit_url("widget", self.group.pk))

        self.assertEqual(response.status_code, 404)

    # --- GET render ---------------------------------------------------------

    def test_get_edit_page_renders_expected_content(self):
        self.set_language("en")
        self.group.church_structure_unit = self.sg_unit_1
        self.group.save(update_fields=["church_structure_unit"])
        self.login_sg_staff()

        response = self.client.get(
            self.edit_url("small-group", self.group.pk)
        )

        self.assertEqual(response.status_code, 200)
        # Legacy object info + current mapping.
        self.assertContains(response, "Editable Group")
        self.assertContains(response, "Small Group")
        self.assertContains(response, "Whole Church &gt; Rainbow Unit")
        # Active matching-type choices, but not inactive / wrong-type units.
        self.assertContains(response, "Sunrise Unit")
        self.assertNotContains(response, "Old Unit")
        self.assertNotContains(response, "North District")
        # Warning copy (CS-CORE.2B-B) + acknowledgement + Save / Cancel.
        self.assertContains(
            response,
            "This updates how this current record links to a church structure unit.",
        )
        self.assertContains(
            response,
            "It does not directly edit members, audience rows, serving "
            "schedules, or permissions.",
        )
        self.assertContains(
            response,
            "saving a mapping edit no longer affects ServiceEvent "
            "structure-audience row matching",
        )
        self.assertContains(
            response,
            "ServiceEvent audience rows match by active primary "
            "ChurchStructureMembership",
        )
        self.assertContains(
            response,
            "Mapping edits can still affect Bible Study structure-audience "
            "resolution and generated legacy SmallGroup meetings.",
        )
        self.assertContains(
            response,
            "ServiceEvents with no audience rows still use legacy fallback via "
            "Profile.small_group",
        )
        self.assertNotContains(
            response,
            "saving this change may affect who matches existing "
            "structure-based event or Bible Study scopes",
        )
        # Required acknowledgement checkbox is present.
        self.assertContains(response, 'name="acknowledge_impact"')
        self.assertContains(
            response,
            "I understand this mapping change may affect Bible Study "
            "structure-audience resolution and generated legacy SmallGroup "
            "meetings.",
        )
        self.assertContains(response, "Save mapping")
        self.assertContains(response, "Cancel")

    def test_get_edit_page_unmapped_empty_state(self):
        self.set_language("en")
        self.login_sg_staff()

        response = self.client.get(
            self.edit_url("small-group", self.group.pk)
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No mapped structure unit yet")

    def test_bilingual_copy_renders(self):
        self.set_language("zh")
        self.login_sg_staff()

        response = self.client.get(
            self.edit_url("small-group", self.group.pk)
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "编辑对应关系")
        self.assertContains(response, "保存对应关系")
        self.assertContains(response, "取消")
        # CS-CORE.2B-B: corrected ZH warning + acknowledgement copy.
        self.assertContains(
            response,
            "这里会更新这条现有记录与教会结构单元的对应关系",
        )
        self.assertContains(
            response,
            "ServiceEvent / 教会聚会中已经选择结构适用范围的记录，不再因为这里的对应关系改变而改变匹配",
        )
        self.assertContains(
            response,
            "保存此更改仍可能影响查经安排解析和生成的小组查经聚会",
        )
        self.assertContains(
            response,
            "没有结构适用范围记录的旧版教会聚会仍按 Profile.small_group 的旧版 fallback 运作",
        )
        self.assertNotContains(
            response,
            "保存此更改可能影响哪些人被匹配到既有的结构适用范围",
        )
        self.assertContains(
            response,
            "我了解此对应关系更改仍可能影响查经安排解析和生成的小组查经聚会。",
        )
        self.assertContains(response, "尚未对应教会结构单元")
        self.assertNotContains(response, "尚未对应教会结构单位")

    # --- valid update -------------------------------------------------------

    def test_valid_update_changes_only_this_row(self):
        other = SmallGroup.objects.create(
            name="Untouched Group",
            church_structure_unit=self.sg_unit_2,
        )
        self.login_sg_staff()

        response = self.client.post(
            self.edit_url("small-group", self.group.pk),
            {
                "church_structure_unit": self.sg_unit_1.pk,
                "status": "unmapped",
                "acknowledge_impact": "1",
            },
        )

        self.assertRedirects(
            response, f"{self.review_url}?status=unmapped"
        )
        self.group.refresh_from_db()
        self.assertEqual(self.group.church_structure_unit_id, self.sg_unit_1.id)
        # The other row is untouched.
        other.refresh_from_db()
        self.assertEqual(other.church_structure_unit_id, self.sg_unit_2.id)

    def test_valid_update_preserves_overlay_filter_status(self):
        # CS-SETUP.1D.3: posting from an overlay filter round-trips that status
        # value back to the review list on a successful save.
        self.login_sg_staff()

        response = self.client.post(
            self.edit_url("small-group", self.group.pk),
            {
                "church_structure_unit": self.sg_unit_1.pk,
                "status": "type_mismatch",
                "acknowledge_impact": "1",
            },
        )

        self.assertRedirects(
            response, f"{self.review_url}?status=type_mismatch"
        )

    def test_get_edit_page_carries_overlay_status_in_form(self):
        # The edit form must echo the overlay status so the return/save path
        # keeps the staff on their conflict filter.
        self.login_sg_staff()

        response = self.client.get(
            self.edit_url("small-group", self.group.pk),
            {"status": "duplicate_active"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "duplicate_active")

    def test_valid_update_writes_logentry(self):
        from django.contrib.admin.models import LogEntry
        from django.contrib.contenttypes.models import ContentType

        self.login_sg_staff()
        self.client.post(
            self.edit_url("small-group", self.group.pk),
            {
                "church_structure_unit": self.sg_unit_1.pk,
                "acknowledge_impact": "1",
            },
        )

        ct = ContentType.objects.get_for_model(SmallGroup)
        entry = LogEntry.objects.filter(
            content_type=ct,
            object_id=str(self.group.id),
            user=self.sg_staff,
        ).first()
        self.assertIsNotNone(entry)
        # Before/after mapped-unit context is recorded.
        self.assertIn("None", entry.change_message)
        self.assertIn(str(self.sg_unit_1.pk), entry.change_message)

    def test_keeping_same_mapping_is_allowed(self):
        # Legacy drift: two active rows already map to the same unit. Editing
        # one row but keeping its current mapping must still be allowed.
        self.group.church_structure_unit = self.sg_unit_1
        self.group.save(update_fields=["church_structure_unit"])
        SmallGroup.objects.create(
            name="Drift Twin",
            church_structure_unit=self.sg_unit_1,
        )
        self.login_sg_staff()

        response = self.client.post(
            self.edit_url("small-group", self.group.pk),
            {
                "church_structure_unit": self.sg_unit_1.pk,
                "acknowledge_impact": "1",
            },
        )

        self.assertRedirects(response, self.review_url)
        self.group.refresh_from_db()
        self.assertEqual(self.group.church_structure_unit_id, self.sg_unit_1.id)

    # --- validation rejections ---------------------------------------------

    def test_inactive_target_rejected(self):
        self.set_language("en")
        self.login_sg_staff()

        response = self.client.post(
            self.edit_url("small-group", self.group.pk),
            {"church_structure_unit": self.sg_unit_inactive.pk},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "inactive")
        self.group.refresh_from_db()
        self.assertIsNone(self.group.church_structure_unit_id)

    def test_wrong_unit_type_rejected(self):
        self.set_language("en")
        self.login_sg_staff()

        response = self.client.post(
            self.edit_url("small-group", self.group.pk),
            {"church_structure_unit": self.district_unit.pk},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "does not match")
        self.group.refresh_from_db()
        self.assertIsNone(self.group.church_structure_unit_id)

    def test_missing_target_rejected(self):
        self.set_language("en")
        self.login_sg_staff()

        response = self.client.post(
            self.edit_url("small-group", self.group.pk),
            {"church_structure_unit": ""},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Please choose a structure unit.")
        self.group.refresh_from_db()
        self.assertIsNone(self.group.church_structure_unit_id)

    def test_duplicate_active_mapping_rejected(self):
        self.set_language("en")
        SmallGroup.objects.create(
            name="Existing Active",
            church_structure_unit=self.sg_unit_1,
        )
        self.login_sg_staff()

        response = self.client.post(
            self.edit_url("small-group", self.group.pk),
            {"church_structure_unit": self.sg_unit_1.pk},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Another active record is already mapped")
        self.group.refresh_from_db()
        self.assertIsNone(self.group.church_structure_unit_id)

    # --- POST-only / GET does not save -------------------------------------

    def test_get_with_query_does_not_save(self):
        self.login_sg_staff()

        response = self.client.get(
            self.edit_url("small-group", self.group.pk),
            {"church_structure_unit": self.sg_unit_1.pk},
        )

        self.assertEqual(response.status_code, 200)
        self.group.refresh_from_db()
        self.assertIsNone(self.group.church_structure_unit_id)

    # --- safety: no side effects on other systems --------------------------

    def test_update_does_not_change_audience_membership_or_profile(self):
        from events.models import ServiceEventAudienceScope
        from studies.models import BibleStudySeriesAudienceScope

        # A profile whose legacy small group is the row being remapped: its
        # Profile.small_group link must be untouched by a mapping edit.
        profile = self.normal_user.profile
        profile.small_group = self.group
        profile.save(update_fields=["small_group"])

        before = (
            ServiceEventAudienceScope.objects.count(),
            BibleStudySeriesAudienceScope.objects.count(),
            ChurchStructureMembership.objects.count(),
        )
        self.login_sg_staff()

        self.client.post(
            self.edit_url("small-group", self.group.pk),
            {
                "church_structure_unit": self.sg_unit_1.pk,
                "acknowledge_impact": "1",
            },
        )

        after = (
            ServiceEventAudienceScope.objects.count(),
            BibleStudySeriesAudienceScope.objects.count(),
            ChurchStructureMembership.objects.count(),
        )
        self.assertEqual(before, after)
        profile.refresh_from_db()
        self.assertEqual(profile.small_group_id, self.group.id)

    # --- CS-SETUP.1D.4: required impact acknowledgement --------------------

    def test_post_without_acknowledgement_does_not_update(self):
        # A valid target but no acknowledgement must leave the mapping
        # unchanged and surface the missing-acknowledgement error.
        self.set_language("en")
        self.login_sg_staff()

        response = self.client.post(
            self.edit_url("small-group", self.group.pk),
            {"church_structure_unit": self.sg_unit_1.pk},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Please confirm that you understand this mapping change may affect "
            "Bible Study structure-audience resolution and generated legacy "
            "SmallGroup meetings before saving.",
        )
        self.group.refresh_from_db()
        self.assertIsNone(self.group.church_structure_unit_id)

    def test_post_without_acknowledgement_zh_error(self):
        self.set_language("zh")
        self.login_sg_staff()

        response = self.client.post(
            self.edit_url("small-group", self.group.pk),
            {"church_structure_unit": self.sg_unit_1.pk},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "保存前请确认你了解此对应关系更改可能影响查经安排解析和生成的小组查经聚会。",
        )
        self.group.refresh_from_db()
        self.assertIsNone(self.group.church_structure_unit_id)

    def test_invalid_target_error_takes_precedence_over_acknowledgement(self):
        # An invalid target keeps its own validation message even when the
        # acknowledgement is also absent, so the surfaced error is predictable
        # and existing target validations remain authoritative.
        self.set_language("en")
        self.login_sg_staff()

        response = self.client.post(
            self.edit_url("small-group", self.group.pk),
            {"church_structure_unit": self.sg_unit_inactive.pk},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "inactive")
        self.assertNotContains(
            response, "structure-scope matching impact before saving"
        )
        self.group.refresh_from_db()
        self.assertIsNone(self.group.church_structure_unit_id)

    def test_acknowledged_save_redirects_and_roundtrips_status(self):
        # POST with acknowledgement performs the update and round-trips the
        # prior status filter back to the review list (filter behavior
        # unchanged by the new acknowledgement gate).
        self.login_sg_staff()

        response = self.client.post(
            self.edit_url("small-group", self.group.pk),
            {
                "church_structure_unit": self.sg_unit_1.pk,
                "status": "needs_review",
                "acknowledge_impact": "1",
            },
        )

        self.assertRedirects(
            response, f"{self.review_url}?status=needs_review"
        )
        self.group.refresh_from_db()
        self.assertEqual(self.group.church_structure_unit_id, self.sg_unit_1.id)

    # --- CS-SETUP.1D.4: documented runtime impact (reason for the warning) --

    def test_mapping_change_no_longer_affects_service_event_audience_match(self):
        # CS-CORE.2B-A updated the runtime impact this warning copy described:
        # ServiceEvent structure-audience rows now match by active primary
        # ChurchStructureMembership, so remapping a SmallGroup no longer
        # changes who matches an event scope. Bible Study unit resolution
        # (next test) still follows the mapping.
        from events.models import ServiceEvent, ServiceEventAudienceScope

        self.group.church_structure_unit = self.sg_unit_1
        self.group.save(update_fields=["church_structure_unit"])
        self.normal_user.profile.small_group = self.group
        self.normal_user.profile.save(update_fields=["small_group"])
        ChurchStructureMembership.objects.create(
            user=self.normal_user,
            unit=self.sg_unit_1,
            status=ChurchStructureMembership.STATUS_ACTIVE,
            is_primary=True,
            start_date=timezone.localdate() - timedelta(days=1),
        )

        event = ServiceEvent.objects.create(
            title="Structure-Scoped Service",
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
            start_datetime=timezone.now(),
            status=ServiceEvent.STATUS_PUBLISHED,
        )
        ServiceEventAudienceScope.objects.create(
            service_event=event, unit=self.sg_unit_1
        )

        # Before: the member's active primary membership unit is the scoped
        # unit, so they match.
        self.assertTrue(event.can_be_seen_by(self.normal_user))

        # Remap the group to a different unit via the staff edit workflow.
        self.login_sg_staff()
        self.client.post(
            self.edit_url("small-group", self.group.pk),
            {
                "church_structure_unit": self.sg_unit_2.pk,
                "acknowledge_impact": "1",
            },
        )
        self.group.refresh_from_db()
        self.assertEqual(self.group.church_structure_unit_id, self.sg_unit_2.id)

        # After: the membership did not move, so the member still matches;
        # group mapping edits no longer change ServiceEvent audience results.
        self.assertTrue(event.can_be_seen_by(self.normal_user))

    def test_mapping_change_affects_bible_study_unit_group_resolution(self):
        # Documents that the Bible Study resolver used by future schedule
        # helpers/generation reads the same mapping fields, so a mapping edit
        # changes which legacy groups a structure unit resolves to.
        from studies.models import resolve_units_to_small_groups

        self.group.church_structure_unit = self.sg_unit_1
        self.group.save(update_fields=["church_structure_unit"])

        self.assertIn(
            self.group,
            list(resolve_units_to_small_groups([self.sg_unit_1])),
        )

        self.login_sg_staff()
        self.client.post(
            self.edit_url("small-group", self.group.pk),
            {
                "church_structure_unit": self.sg_unit_2.pk,
                "acknowledge_impact": "1",
            },
        )

        self.assertNotIn(
            self.group,
            list(resolve_units_to_small_groups([self.sg_unit_1])),
        )
        self.assertIn(
            self.group,
            list(resolve_units_to_small_groups([self.sg_unit_2])),
        )


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
        self.group = SmallGroup.objects.create(name="Rainbow 4")

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

        self.user.profile.small_group = self.group
        self.user.profile.save()

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
        self.assertContains(response, "小组")
        self.assertContains(response, "语言")
        self.assertContains(response, "密码状态")
        self.assertContains(response, "操作")
        self.assertContains(response, "重置密码")
        self.assertContains(response, "正常")
        self.assertNotContains(response, "User Admin")
        self.assertNotContains(response, "Reset Password")

    def test_staff_can_search_user_list(self):
        self.client.login(username="staff", password="StaffPass123!")

        response = self.client.get(reverse("staff_user_list"), {"q": "Rainbow"})

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
        self.group = SmallGroup.objects.create(name="Rainbow 4")
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
        self.assertIsNone(user.profile.small_group)
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

        self.assertIsNone(user.profile.small_group)
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
        district = District.objects.create(name="District 1")
        group = SmallGroup.objects.create(
            name="District Group",
            district=district,
            church_structure_unit=self.unit,
        )
        event = ServiceEvent.objects.create(
            title="District Service",
            event_type=ServiceEvent.EVENT_SUNDAY_SERVICE,
            start_datetime=timezone.now(),
            scope_type=ServiceEvent.SCOPE_DISTRICT,
            district=district,
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
        self.assertIsNone(user.profile.small_group)
        self.assertFalse(event.can_be_seen_by(user))

        user.profile.small_group = group
        user.profile.save()

        self.assertTrue(event.can_be_seen_by(user))

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

    def test_legacy_small_group_scope_assignment_unchanged(self):
        group = SmallGroup.objects.create(name="Legacy SG")
        assignment = ChurchRoleAssignment.objects.create(
            user=self.user,
            role=ChurchRoleAssignment.ROLE_GROUP_LEADER,
            scope_type=ChurchRoleAssignment.SCOPE_SMALL_GROUP,
            small_group=group,
        )

        assignment.refresh_from_db()
        self.assertEqual(assignment.small_group_id, group.id)
        self.assertIsNone(assignment.structure_unit_id)

    def test_assignment_can_be_created_with_structure_unit(self):
        group = SmallGroup.objects.create(name="Mapped SG")
        assignment = ChurchRoleAssignment.objects.create(
            user=self.user,
            role=ChurchRoleAssignment.ROLE_GROUP_LEADER,
            scope_type=ChurchRoleAssignment.SCOPE_SMALL_GROUP,
            small_group=group,
            structure_unit=self.group_unit,
        )

        assignment.refresh_from_db()
        self.assertEqual(assignment.structure_unit_id, self.group_unit.id)

    def test_resolver_returns_explicit_structure_unit_first(self):
        group = SmallGroup.objects.create(
            name="Mapped SG2", church_structure_unit=self.sibling_group_unit
        )
        assignment = ChurchRoleAssignment.objects.create(
            user=self.user,
            role=ChurchRoleAssignment.ROLE_GROUP_LEADER,
            scope_type=ChurchRoleAssignment.SCOPE_SMALL_GROUP,
            small_group=group,
            structure_unit=self.group_unit,
        )

        self.assertEqual(
            get_role_assignment_structure_unit(assignment), self.group_unit
        )

    def test_resolver_falls_back_to_legacy_small_group_unit(self):
        group = SmallGroup.objects.create(
            name="Mapped SG3", church_structure_unit=self.group_unit
        )
        assignment = ChurchRoleAssignment.objects.create(
            user=self.user,
            role=ChurchRoleAssignment.ROLE_GROUP_LEADER,
            scope_type=ChurchRoleAssignment.SCOPE_SMALL_GROUP,
            small_group=group,
        )

        self.assertEqual(
            get_role_assignment_structure_unit(assignment), self.group_unit
        )

    def test_resolver_falls_back_to_legacy_district_unit(self):
        district = District.objects.create(
            name="Mapped District", church_structure_unit=self.district_unit
        )
        assignment = ChurchRoleAssignment.objects.create(
            user=self.user,
            role=ChurchRoleAssignment.ROLE_DISTRICT_LEADER,
            scope_type=ChurchRoleAssignment.SCOPE_DISTRICT,
            district=district,
        )

        self.assertEqual(
            get_role_assignment_structure_unit(assignment), self.district_unit
        )

    def test_resolver_returns_none_for_unmapped_legacy_scope(self):
        group = SmallGroup.objects.create(name="Unmapped SG")
        assignment = ChurchRoleAssignment.objects.create(
            user=self.user,
            role=ChurchRoleAssignment.ROLE_GROUP_LEADER,
            scope_type=ChurchRoleAssignment.SCOPE_SMALL_GROUP,
            small_group=group,
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
            small_group=SmallGroup.objects.create(name="Same SG"),
            structure_unit=self.group_unit,
        )

        self.assertTrue(
            assignment_scope_includes_unit(assignment, self.group_unit)
        )

    def test_scope_includes_descendant_small_group_under_district_unit(self):
        district = District.objects.create(
            name="Cover District", church_structure_unit=self.district_unit
        )
        assignment = ChurchRoleAssignment.objects.create(
            user=self.user,
            role=ChurchRoleAssignment.ROLE_DISTRICT_LEADER,
            scope_type=ChurchRoleAssignment.SCOPE_DISTRICT,
            district=district,
        )

        # group_unit is a child of district_unit, so a district-like scope covers it.
        self.assertTrue(
            assignment_scope_includes_unit(assignment, self.group_unit)
        )

    def test_scope_excludes_sibling_and_unrelated_units(self):
        assignment = ChurchRoleAssignment.objects.create(
            user=self.user,
            role=ChurchRoleAssignment.ROLE_GROUP_LEADER,
            scope_type=ChurchRoleAssignment.SCOPE_SMALL_GROUP,
            small_group=SmallGroup.objects.create(name="Excl SG"),
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
        unresolved = ChurchRoleAssignment.objects.create(
            user=self.user,
            role=ChurchRoleAssignment.ROLE_GROUP_LEADER,
            scope_type=ChurchRoleAssignment.SCOPE_SMALL_GROUP,
            small_group=SmallGroup.objects.create(name="NoUnit SG"),
        )

        # Missing target unit fails closed.
        self.assertFalse(
            assignment_scope_includes_unit(unresolved, None)
        )
        # Unresolved assignment scope (no explicit unit, unmapped legacy) fails closed.
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
        # CS-CORE.2D-B: a legacy SmallGroup-scoped role still grants progress access
        # through its mapped structure unit (transition fallback), while an unmapped
        # legacy scope fails closed.
        mapped_group = SmallGroup.objects.create(
            name="Mapped Perm SG", church_structure_unit=self.group_unit
        )
        ChurchRoleAssignment.objects.create(
            user=self.user,
            role=ChurchRoleAssignment.ROLE_GROUP_LEADER,
            scope_type=ChurchRoleAssignment.SCOPE_SMALL_GROUP,
            small_group=mapped_group,
        )
        self.assertEqual(
            list(get_accessible_progress_groups(self.user)), [mapped_group]
        )

        unmapped_user = User.objects.create_user(username="unmapped_perm_user")
        unmapped_group = SmallGroup.objects.create(name="Unmapped Perm SG")
        ChurchRoleAssignment.objects.create(
            user=unmapped_user,
            role=ChurchRoleAssignment.ROLE_GROUP_LEADER,
            scope_type=ChurchRoleAssignment.SCOPE_SMALL_GROUP,
            small_group=unmapped_group,
        )
        self.assertEqual(list(get_accessible_progress_groups(unmapped_user)), [])


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

    def test_command_is_read_only(self):
        unit = self.create_unit("AUDIT-RO")
        group = SmallGroup.objects.create(
            name="Audit RO SG", church_structure_unit=unit
        )
        ChurchRoleAssignment.objects.create(
            user=self.user,
            role=ChurchRoleAssignment.ROLE_GROUP_LEADER,
            scope_type=ChurchRoleAssignment.SCOPE_SMALL_GROUP,
            small_group=group,
        )
        before = {
            "assignments": ChurchRoleAssignment.objects.count(),
            "units": ChurchStructureUnit.objects.count(),
            "groups": SmallGroup.objects.count(),
            "districts": District.objects.count(),
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
                "groups": SmallGroup.objects.count(),
                "districts": District.objects.count(),
            },
        )

    def test_mapped_small_group_scope_is_ready(self):
        unit = self.create_unit("AUDIT-MAP-SG")
        group = SmallGroup.objects.create(
            name="Audit Mapped SG", church_structure_unit=unit
        )
        ChurchRoleAssignment.objects.create(
            user=self.user,
            role=ChurchRoleAssignment.ROLE_GROUP_LEADER,
            scope_type=ChurchRoleAssignment.SCOPE_SMALL_GROUP,
            small_group=group,
        )

        output = self.run_command()

        self.assert_summary_count(output, "assignments_checked", 1)
        self.assert_summary_count(output, "legacy_small_group_scope_mapped", 1)
        self.assert_summary_count(output, "legacy_small_group_scope_unmapped", 0)
        self.assert_summary_count(output, "assignments_ready_for_structure_scope", 1)
        self.assert_summary_count(
            output, "assignments_not_ready_for_structure_scope", 0
        )

    def test_unmapped_small_group_scope_is_not_ready(self):
        group = SmallGroup.objects.create(name="Audit Unmapped SG")
        ChurchRoleAssignment.objects.create(
            user=self.user,
            role=ChurchRoleAssignment.ROLE_GROUP_LEADER,
            scope_type=ChurchRoleAssignment.SCOPE_SMALL_GROUP,
            small_group=group,
        )

        output = self.run_command("--verbose")

        self.assert_summary_count(output, "legacy_small_group_scope_unmapped", 1)
        self.assert_summary_count(
            output, "assignments_not_ready_for_structure_scope", 1
        )
        self.assertIn("reason=legacy_small_group_scope_unmapped", output)

    def test_mapped_and_unmapped_district_scopes_counted(self):
        unit = self.create_unit("AUDIT-DIST", unit_type=ChurchStructureUnit.UNIT_DISTRICT)
        mapped_district = District.objects.create(
            name="Audit Mapped District", church_structure_unit=unit
        )
        unmapped_district = District.objects.create(name="Audit Unmapped District")
        ChurchRoleAssignment.objects.create(
            user=self.user,
            role=ChurchRoleAssignment.ROLE_DISTRICT_LEADER,
            scope_type=ChurchRoleAssignment.SCOPE_DISTRICT,
            district=mapped_district,
        )
        other = User.objects.create_user(username="audit_role_user2")
        ChurchRoleAssignment.objects.create(
            user=other,
            role=ChurchRoleAssignment.ROLE_DISTRICT_LEADER,
            scope_type=ChurchRoleAssignment.SCOPE_DISTRICT,
            district=unmapped_district,
        )

        output = self.run_command()

        self.assert_summary_count(output, "legacy_district_scope_mapped", 1)
        self.assert_summary_count(output, "legacy_district_scope_unmapped", 1)

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

    def test_mismatch_between_structure_unit_and_legacy_mapping(self):
        unit_a = self.create_unit("AUDIT-MIS-A")
        unit_b = self.create_unit("AUDIT-MIS-B")
        group = SmallGroup.objects.create(
            name="Audit Mismatch SG", church_structure_unit=unit_a
        )
        ChurchRoleAssignment.objects.create(
            user=self.user,
            role=ChurchRoleAssignment.ROLE_GROUP_LEADER,
            scope_type=ChurchRoleAssignment.SCOPE_SMALL_GROUP,
            small_group=group,
            structure_unit=unit_b,
        )

        output = self.run_command("--verbose")

        self.assert_summary_count(output, "legacy_scope_mismatch_structure_unit", 1)
        self.assert_summary_count(
            output, "assignments_not_ready_for_structure_scope", 1
        )
        self.assertIn("reason=legacy_scope_mismatch_structure_unit", output)

    def test_inactive_structure_unit_counted_and_not_ready(self):
        inactive_unit = self.create_unit("AUDIT-INACT", is_active=False)
        group = SmallGroup.objects.create(
            name="Audit Inactive SG", church_structure_unit=inactive_unit
        )
        ChurchRoleAssignment.objects.create(
            user=self.user,
            role=ChurchRoleAssignment.ROLE_GROUP_LEADER,
            scope_type=ChurchRoleAssignment.SCOPE_SMALL_GROUP,
            small_group=group,
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
        group = SmallGroup.objects.create(name="Audit WrongType SG")
        ChurchRoleAssignment.objects.create(
            user=self.user,
            role=ChurchRoleAssignment.ROLE_GROUP_LEADER,
            scope_type=ChurchRoleAssignment.SCOPE_SMALL_GROUP,
            small_group=group,
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
            group = SmallGroup.objects.create(name=f"Audit Limit SG {index}")
            user = User.objects.create_user(username=f"audit_limit_user_{index}")
            ChurchRoleAssignment.objects.create(
                user=user,
                role=ChurchRoleAssignment.ROLE_GROUP_LEADER,
                scope_type=ChurchRoleAssignment.SCOPE_SMALL_GROUP,
                small_group=group,
            )

        output = self.run_command("--verbose", "--limit", "1")

        self.assert_summary_count(output, "legacy_small_group_scope_unmapped", 3)
        self.assertIn("(stopped at --limit 1)", output)


class GroupProgressPermissionSourceSwitchTests(TestCase):
    """CS-CORE.2D-B: group-progress permission/access list is structure-aware.

    ``get_accessible_progress_groups`` / ``can_view_group_progress_for`` resolve
    scoped role access through ``ChurchRoleAssignment.structure_unit`` (or the legacy
    district/small_group mapped unit during transition) plus its descendants, and the
    ordinary own-group rule comes from the single active primary
    ``ChurchStructureMembership`` mapped to exactly one active legacy ``SmallGroup``.
    ``Profile.small_group`` no longer grants any progress access, and ordinary
    membership grants only its own mapped group (never a broad grant).
    """

    def setUp(self):
        # district_unit
        #   |- group_unit            -> self.group
        #   |- sibling_unit          -> self.sibling_group
        # other_district_unit
        #   |- other_group_unit      -> self.other_group
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

        self.district = District.objects.create(
            name="Perm2DB District", church_structure_unit=self.district_unit
        )
        self.other_district = District.objects.create(
            name="Perm2DB Other District",
            church_structure_unit=self.other_district_unit,
        )
        self.group = SmallGroup.objects.create(
            name="Perm2DB Group",
            district=self.district,
            church_structure_unit=self.group_unit,
        )
        self.sibling_group = SmallGroup.objects.create(
            name="Perm2DB Sibling Group",
            district=self.district,
            church_structure_unit=self.sibling_unit,
        )
        self.other_group = SmallGroup.objects.create(
            name="Perm2DB Other Group",
            district=self.other_district,
            church_structure_unit=self.other_group_unit,
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
        if group is not None:
            user.profile.small_group = group
            user.profile.save()
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
            get_user_membership_progress_own_group(user), self.group
        )
        self.assertEqual(self.accessible_ids(user), {self.group.id})
        self.assertTrue(can_view_group_progress_for(user, self.group))

    def test_profile_only_user_gets_no_own_group_access(self):
        user = self.create_user("perm2db_profile_only", group=self.group)

        self.assertIsNone(get_user_membership_progress_own_group(user))
        self.assertEqual(self.accessible_ids(user), set())
        self.assertFalse(can_view_group_progress_for(user, self.group))

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
        # Unmapped small-group unit (maps to no active SmallGroup).
        unmapped_user = self.create_user("perm2db_unmapped")
        self.create_membership(unmapped_user, self.create_unit("PERM2DB-UNMAPPED"))
        self.assertIsNone(get_user_membership_progress_own_group(unmapped_user))
        self.assertEqual(self.accessible_ids(unmapped_user), set())

        # Wrong-type unit (fellowship, not small_group).
        wrong_type_user = self.create_user("perm2db_wrong_type")
        fellowship_unit = self.create_unit(
            "PERM2DB-FEL", unit_type=ChurchStructureUnit.UNIT_FELLOWSHIP
        )
        SmallGroup.objects.create(
            name="Perm2DB Fellowship-mapped",
            church_structure_unit=fellowship_unit,
        )
        self.create_membership(wrong_type_user, fellowship_unit)
        self.assertIsNone(get_user_membership_progress_own_group(wrong_type_user))
        self.assertEqual(self.accessible_ids(wrong_type_user), set())

    def test_membership_unit_mapping_to_two_active_groups_fails_closed(self):
        user = self.create_user("perm2db_ambiguous_map")
        shared_unit = self.create_unit("PERM2DB-SHARED", parent=self.district_unit)
        SmallGroup.objects.create(
            name="Perm2DB Shared A", church_structure_unit=shared_unit
        )
        SmallGroup.objects.create(
            name="Perm2DB Shared B", church_structure_unit=shared_unit
        )
        self.create_membership(user, shared_unit)

        self.assertIsNone(get_user_membership_progress_own_group(user))
        self.assertEqual(self.accessible_ids(user), set())

    def test_ordinary_membership_grants_only_own_group_not_siblings(self):
        user = self.create_user("perm2db_own_only")
        self.create_membership(user, self.group_unit)

        self.assertEqual(self.accessible_ids(user), {self.group.id})
        self.assertTrue(can_view_group_progress_for(user, self.group))
        self.assertFalse(can_view_group_progress_for(user, self.sibling_group))
        self.assertFalse(can_view_group_progress_for(user, self.other_group))

    # --- structure-aware role scopes --------------------------------------------

    def test_group_leader_structure_unit_scope_grants_that_group(self):
        leader = self.create_user("perm2db_group_leader")
        ChurchRoleAssignment.objects.create(
            user=leader,
            role=ChurchRoleAssignment.ROLE_GROUP_LEADER,
            scope_type=ChurchRoleAssignment.SCOPE_SMALL_GROUP,
            small_group=self.group,
            structure_unit=self.group_unit,
        )

        self.assertEqual(self.accessible_ids(leader), {self.group.id})
        self.assertFalse(can_view_group_progress_for(leader, self.sibling_group))

    def test_district_leader_scope_includes_descendant_groups_only(self):
        leader = self.create_user("perm2db_district_leader")
        ChurchRoleAssignment.objects.create(
            user=leader,
            role=ChurchRoleAssignment.ROLE_DISTRICT_LEADER,
            scope_type=ChurchRoleAssignment.SCOPE_DISTRICT,
            district=self.district,
        )

        # district_unit covers its descendant small-group units (group + sibling),
        # but not a group under another district.
        self.assertEqual(
            self.accessible_ids(leader),
            {self.group.id, self.sibling_group.id},
        )
        self.assertTrue(can_view_group_progress_for(leader, self.group))
        self.assertTrue(can_view_group_progress_for(leader, self.sibling_group))
        self.assertFalse(can_view_group_progress_for(leader, self.other_group))

    def test_legacy_small_group_scope_resolves_through_mapping_fallback(self):
        leader = self.create_user("perm2db_legacy_group_leader")
        # No explicit structure_unit: resolved via small_group.church_structure_unit.
        ChurchRoleAssignment.objects.create(
            user=leader,
            role=ChurchRoleAssignment.ROLE_GROUP_LEADER,
            scope_type=ChurchRoleAssignment.SCOPE_SMALL_GROUP,
            small_group=self.group,
        )

        self.assertEqual(self.accessible_ids(leader), {self.group.id})

    def test_legacy_district_scope_resolves_through_mapping_fallback(self):
        leader = self.create_user("perm2db_legacy_district_leader")
        ChurchRoleAssignment.objects.create(
            user=leader,
            role=ChurchRoleAssignment.ROLE_DISTRICT_LEADER,
            scope_type=ChurchRoleAssignment.SCOPE_DISTRICT,
            district=self.district,
        )

        self.assertEqual(
            self.accessible_ids(leader),
            {self.group.id, self.sibling_group.id},
        )

    def test_unmapped_legacy_role_scope_fails_closed(self):
        leader = self.create_user("perm2db_unmapped_leader")
        unmapped_group = SmallGroup.objects.create(name="Perm2DB Unmapped Group")
        ChurchRoleAssignment.objects.create(
            user=leader,
            role=ChurchRoleAssignment.ROLE_GROUP_LEADER,
            scope_type=ChurchRoleAssignment.SCOPE_SMALL_GROUP,
            small_group=unmapped_group,
        )

        self.assertEqual(self.accessible_ids(leader), set())
        self.assertFalse(can_view_group_progress_for(leader, unmapped_group))

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

        all_active = {self.group.id, self.sibling_group.id, self.other_group.id}
        for viewer in (staff, superuser, pastor):
            self.assertEqual(self.accessible_ids(viewer), all_active)
            self.assertTrue(can_view_group_progress_for(viewer, self.other_group))

    def test_can_view_agrees_with_accessible_list_for_allowed_and_denied(self):
        leader = self.create_user("perm2db_agree")
        ChurchRoleAssignment.objects.create(
            user=leader,
            role=ChurchRoleAssignment.ROLE_GROUP_LEADER,
            scope_type=ChurchRoleAssignment.SCOPE_SMALL_GROUP,
            small_group=self.group,
        )

        accessible = self.accessible_ids(leader)
        for candidate in (self.group, self.sibling_group, self.other_group):
            self.assertEqual(
                can_view_group_progress_for(leader, candidate),
                candidate.id in accessible,
            )


class StructureRoleScopeBackfillCommandTests(TestCase):
    """CS-CORE.2D-C: backfill ChurchRoleAssignment.structure_unit from legacy scopes.

    Data-migration tooling. Dry-run by default; ``--apply`` writes only
    ``structure_unit`` on ready rows. Legacy district / small_group fields are
    never cleared, runtime permission behavior is unchanged, and ordinary
    ChurchStructureMembership is never read.
    """

    def setUp(self):
        self.user = User.objects.create_user(username="backfill_role_user")
        self.district_unit = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_DISTRICT,
            code="BF-DIST",
            name="Backfill District",
        )
        self.group_unit = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="BF-SG",
            name="Backfill Small Group",
            parent=self.district_unit,
        )
        self.other_unit = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="BF-SG-OTHER",
            name="Backfill Other Small Group",
        )

    def run_command(self, *args):
        output = StringIO()
        call_command("backfill_structure_role_scopes", *args, stdout=output)
        return output.getvalue()

    def assert_summary_count(self, output, key, count):
        self.assertIn(f"{key}: {count}", output)

    def make_group_assignment(self, group, *, structure_unit=None, user=None):
        return ChurchRoleAssignment.objects.create(
            user=user or self.user,
            role=ChurchRoleAssignment.ROLE_GROUP_LEADER,
            scope_type=ChurchRoleAssignment.SCOPE_SMALL_GROUP,
            small_group=group,
            structure_unit=structure_unit,
        )

    def make_district_assignment(self, district, *, structure_unit=None, user=None):
        return ChurchRoleAssignment.objects.create(
            user=user or self.user,
            role=ChurchRoleAssignment.ROLE_DISTRICT_LEADER,
            scope_type=ChurchRoleAssignment.SCOPE_DISTRICT,
            district=district,
            structure_unit=structure_unit,
        )

    # --- dry-run writes nothing -------------------------------------------------

    def test_dry_run_writes_nothing_for_ready_small_group_scope(self):
        group = SmallGroup.objects.create(
            name="BF Ready SG", church_structure_unit=self.group_unit
        )
        assignment = self.make_group_assignment(group)

        with CaptureQueriesContext(connection) as queries:
            output = self.run_command("--verbose")

        write_sql = [
            query["sql"]
            for query in queries
            if query["sql"].lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE"))
        ]
        self.assertEqual(write_sql, [])
        assignment.refresh_from_db()
        self.assertIsNone(assignment.structure_unit_id)
        self.assert_summary_count(output, "missing_structure_unit_ready", 1)
        self.assert_summary_count(output, "would_update", 1)
        self.assert_summary_count(output, "updated", 0)
        self.assert_summary_count(output, "dry_run", 1)
        self.assertIn("MODE: dry-run", output)

    def test_dry_run_writes_nothing_for_ready_district_scope(self):
        district = District.objects.create(
            name="BF Ready District", church_structure_unit=self.district_unit
        )
        assignment = self.make_district_assignment(district)

        before = assignment.structure_unit_id
        output = self.run_command()

        assignment.refresh_from_db()
        self.assertEqual(assignment.structure_unit_id, before)
        self.assertIsNone(assignment.structure_unit_id)
        self.assert_summary_count(output, "missing_structure_unit_ready", 1)
        self.assert_summary_count(output, "would_update", 1)
        self.assert_summary_count(output, "updated", 0)

    # --- apply writes ready rows -----------------------------------------------

    def test_apply_sets_structure_unit_for_ready_small_group_scope(self):
        group = SmallGroup.objects.create(
            name="BF Apply SG", church_structure_unit=self.group_unit
        )
        assignment = self.make_group_assignment(group)

        output = self.run_command("--apply")

        assignment.refresh_from_db()
        self.assertEqual(assignment.structure_unit_id, self.group_unit.id)
        # Legacy field is untouched.
        self.assertEqual(assignment.small_group_id, group.id)
        self.assert_summary_count(output, "updated", 1)
        self.assert_summary_count(output, "would_update", 0)
        self.assert_summary_count(output, "dry_run", 0)
        self.assertIn("MODE: apply", output)

    def test_apply_sets_structure_unit_for_ready_district_scope(self):
        district = District.objects.create(
            name="BF Apply District", church_structure_unit=self.district_unit
        )
        assignment = self.make_district_assignment(district)

        output = self.run_command("--apply")

        assignment.refresh_from_db()
        self.assertEqual(assignment.structure_unit_id, self.district_unit.id)
        self.assertEqual(assignment.district_id, district.id)
        self.assert_summary_count(output, "updated", 1)

    # --- existing structure_unit is never overwritten ---------------------------

    def test_existing_matching_structure_unit_not_updated(self):
        group = SmallGroup.objects.create(
            name="BF Match SG", church_structure_unit=self.group_unit
        )
        assignment = self.make_group_assignment(group, structure_unit=self.group_unit)

        with CaptureQueriesContext(connection) as queries:
            output = self.run_command("--apply")

        write_sql = [
            query["sql"]
            for query in queries
            if query["sql"].lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE"))
        ]
        self.assertEqual(write_sql, [])
        assignment.refresh_from_db()
        self.assertEqual(assignment.structure_unit_id, self.group_unit.id)
        self.assert_summary_count(output, "already_set_matching", 1)
        self.assert_summary_count(output, "updated", 0)

    def test_existing_mismatched_structure_unit_not_overwritten(self):
        group = SmallGroup.objects.create(
            name="BF Mismatch SG", church_structure_unit=self.group_unit
        )
        assignment = self.make_group_assignment(group, structure_unit=self.other_unit)

        output = self.run_command("--apply", "--verbose")

        assignment.refresh_from_db()
        self.assertEqual(assignment.structure_unit_id, self.other_unit.id)
        self.assert_summary_count(output, "mismatch_existing_structure_unit", 1)
        self.assert_summary_count(output, "updated", 0)
        self.assertIn("reason=mismatch_existing_structure_unit", output)

    def test_already_set_structure_unit_without_legacy_mapping(self):
        group = SmallGroup.objects.create(name="BF NoMap SG")  # unmapped legacy group
        assignment = self.make_group_assignment(group, structure_unit=self.group_unit)

        output = self.run_command("--apply")

        assignment.refresh_from_db()
        self.assertEqual(assignment.structure_unit_id, self.group_unit.id)
        self.assert_summary_count(output, "already_set_no_legacy_mapping", 1)
        self.assert_summary_count(output, "updated", 0)

    # --- global roles stay None -------------------------------------------------

    def test_global_assignment_remains_none(self):
        assignment = ChurchRoleAssignment.objects.create(
            user=self.user,
            role=ChurchRoleAssignment.ROLE_PASTOR,
            scope_type=ChurchRoleAssignment.SCOPE_GLOBAL,
        )

        output = self.run_command("--apply")

        assignment.refresh_from_db()
        self.assertIsNone(assignment.structure_unit_id)
        self.assert_summary_count(output, "global_assignments", 1)
        self.assert_summary_count(output, "updated", 0)

    # --- not-ready rows are skipped --------------------------------------------

    def test_unmapped_small_group_scope_skipped(self):
        group = SmallGroup.objects.create(name="BF Unmapped SG")
        assignment = self.make_group_assignment(group)

        output = self.run_command("--apply", "--verbose")

        assignment.refresh_from_db()
        self.assertIsNone(assignment.structure_unit_id)
        self.assert_summary_count(output, "legacy_small_group_scope_unmapped", 1)
        self.assert_summary_count(output, "skipped_not_ready", 1)
        self.assert_summary_count(output, "updated", 0)
        self.assertIn("reason=legacy_scope_unmapped", output)

    def test_unmapped_district_scope_skipped(self):
        district = District.objects.create(name="BF Unmapped District")
        assignment = self.make_district_assignment(district)

        output = self.run_command("--apply")

        assignment.refresh_from_db()
        self.assertIsNone(assignment.structure_unit_id)
        self.assert_summary_count(output, "legacy_district_scope_unmapped", 1)
        self.assert_summary_count(output, "skipped_not_ready", 1)
        self.assert_summary_count(output, "updated", 0)

    def test_inactive_mapped_unit_skipped(self):
        inactive_unit = ChurchStructureUnit.objects.create(
            unit_type=ChurchStructureUnit.UNIT_SMALL_GROUP,
            code="BF-INACT",
            name="Backfill Inactive",
            is_active=False,
        )
        group = SmallGroup.objects.create(
            name="BF Inactive SG", church_structure_unit=inactive_unit
        )
        assignment = self.make_group_assignment(group)

        output = self.run_command("--apply", "--verbose")

        assignment.refresh_from_db()
        self.assertIsNone(assignment.structure_unit_id)
        self.assert_summary_count(output, "legacy_scope_structure_unit_inactive", 1)
        self.assert_summary_count(output, "skipped_not_ready", 1)
        self.assert_summary_count(output, "updated", 0)
        self.assertIn("reason=legacy_scope_structure_unit_inactive", output)

    def test_wrong_type_mapped_unit_skipped_for_small_group_scope(self):
        # A district-type unit is too broad to back a small-group scope.
        group = SmallGroup.objects.create(
            name="BF WrongType SG", church_structure_unit=self.district_unit
        )
        assignment = self.make_group_assignment(group)

        output = self.run_command("--apply", "--verbose")

        assignment.refresh_from_db()
        self.assertIsNone(assignment.structure_unit_id)
        self.assert_summary_count(output, "legacy_scope_structure_unit_wrong_type", 1)
        self.assert_summary_count(output, "skipped_not_ready", 1)
        self.assert_summary_count(output, "updated", 0)
        self.assertIn("reason=legacy_scope_structure_unit_wrong_type", output)

    def test_wrong_type_mapped_unit_skipped_for_district_scope(self):
        # A small-group-type unit is too narrow to back a district scope.
        district = District.objects.create(
            name="BF WrongType District", church_structure_unit=self.group_unit
        )
        assignment = self.make_district_assignment(district)

        output = self.run_command("--apply")

        assignment.refresh_from_db()
        self.assertIsNone(assignment.structure_unit_id)
        self.assert_summary_count(output, "legacy_scope_structure_unit_wrong_type", 1)
        self.assert_summary_count(output, "skipped_not_ready", 1)
        self.assert_summary_count(output, "updated", 0)

    # --- idempotency ------------------------------------------------------------

    def test_apply_is_idempotent(self):
        group = SmallGroup.objects.create(
            name="BF Idempotent SG", church_structure_unit=self.group_unit
        )
        assignment = self.make_group_assignment(group)

        first = self.run_command("--apply")
        self.assert_summary_count(first, "updated", 1)
        assignment.refresh_from_db()
        self.assertEqual(assignment.structure_unit_id, self.group_unit.id)

        with CaptureQueriesContext(connection) as queries:
            second = self.run_command("--apply")

        write_sql = [
            query["sql"]
            for query in queries
            if query["sql"].lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE"))
        ]
        self.assertEqual(write_sql, [])
        self.assert_summary_count(second, "updated", 0)
        self.assert_summary_count(second, "already_set_matching", 1)

    def test_repeated_dry_run_changes_nothing(self):
        group = SmallGroup.objects.create(
            name="BF Repeat SG", church_structure_unit=self.group_unit
        )
        assignment = self.make_group_assignment(group)

        self.run_command()
        self.run_command()

        assignment.refresh_from_db()
        self.assertIsNone(assignment.structure_unit_id)

    # --- output distinguishes dry-run vs apply ----------------------------------

    def test_output_distinguishes_dry_run_and_apply(self):
        dry = self.run_command()
        applied = self.run_command("--apply")

        self.assertIn("MODE: dry-run", dry)
        self.assertIn("dry-run: nothing was written", dry)
        self.assertIn("MODE: apply", applied)
        self.assertIn("apply mode: only structure_unit was written", applied)

    def test_limit_caps_verbose_rows(self):
        for index in range(3):
            group = SmallGroup.objects.create(name=f"BF Limit SG {index}")
            user = User.objects.create_user(username=f"bf_limit_user_{index}")
            self.make_group_assignment(group, user=user)

        output = self.run_command("--verbose", "--limit", "1")

        self.assert_summary_count(output, "skipped_not_ready", 3)
        self.assertIn("(stopped at --limit 1)", output)
