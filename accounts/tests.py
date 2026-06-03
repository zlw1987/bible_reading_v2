import re
from datetime import timedelta
from io import StringIO
from pathlib import Path

from django.core.management import call_command, CommandError
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import (
    ChurchRoleAssignment,
    ChurchStructureMembership,
    ChurchStructureUnit,
    District,
    MinistryContext,
    SmallGroup,
)
from accounts.permissions import (
    CAP_MANAGE_CHURCH_MEMBERSHIPS,
    CAP_PUBLISH_READING_GUIDES,
    CAP_VIEW_ALL_GROUP_PROGRESS,
    CAP_VIEW_DISTRICT_PROGRESS,
    CAP_VIEW_GROUP_PROGRESS,
    get_accessible_progress_groups,
    has_capability,
)
from events.models import ServiceEvent
from studies.models import BibleStudySeries

class AccountProfileTests(TestCase):
    def setUp(self):
        self.group = SmallGroup.objects.create(name="Rainbow 4")
        self.other_group = SmallGroup.objects.create(name="Rainbow 5")

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

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "levin")
        self.assertContains(response, "Rainbow 4")

    def test_user_can_update_profile_without_email(self):
        self.client.login(username="levin", password="OldPass123!")

        response = self.client.post(
            reverse("profile"),
            {
                "email": "",
                "small_group": self.other_group.id,
                "preferred_language": "en",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("profile"))

        self.user.refresh_from_db()
        self.user.profile.refresh_from_db()

        self.assertEqual(self.user.email, "")
        self.assertEqual(self.user.profile.small_group, self.other_group)
        self.assertEqual(self.user.profile.preferred_language, "en")
        self.assertEqual(self.client.session["language"], "en")

    def test_user_can_update_email(self):
        self.client.login(username="levin", password="OldPass123!")

        response = self.client.post(
            reverse("profile"),
            {
                "email": "levin@example.com",
                "small_group": self.group.id,
                "preferred_language": "zh",
            },
        )

        self.assertEqual(response.status_code, 302)

        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "levin@example.com")

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
        self.assertIn("setDropdownPosition(menu)", content)
        self.assertNotIn("site-header--hidden", content)
        self.assertNotIn("mobileHeader", content)
        self.assertNotIn("updateHeaderVisibility", content)
        self.assertNotIn("requestHeaderVisibilityUpdate", content)
        self.assertNotIn('window.addEventListener("scroll"', content)
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
        self.assertContains(response, "Service Events")
        self.assertContains(response, "Ministry Teams")
        self.assertContains(response, "Team Assignments")
        self.assertContains(response, "Lighting Pilot Import")
        self.assertContains(response, "Users and Review")
        self.assertContains(response, "User Admin")
        self.assertContains(response, "Reflection Reports")
        self.assertContains(response, "Prayer Reports")
        self.assertContains(response, "Django Admin")

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
        self.assertNotIn("site-header--hidden", css)
        self.assertNotIn("translateY(calc(-100% - 1px))", css)
        self.assertNotIn("min-width: min(300px", css)

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
        self.assertContains(response, "聚会事件")
        self.assertContains(response, "事工团队")
        self.assertContains(response, "服事排班")
        self.assertContains(response, "灯光试点导入")
        self.assertContains(response, "用户与审核")
        self.assertContains(response, "用户管理")
        self.assertContains(response, "默想举报")
        self.assertContains(response, "代祷举报")

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
        self.assertContains(response, "current runtime still uses this model")
        self.assertContains(response, "Profile.small_group")
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
        self.assertContains(context_response, "current runtime still uses this")

        self.assertEqual(district_response.status_code, 200)
        self.assertContains(district_response, "Legacy Districts")
        self.assertContains(district_response, "旧区")
        self.assertContains(district_response, "current runtime still uses this model")

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
        self.assertContains(response, "future flexible structure foundation")
        self.assertContains(response, "does not drive runtime visibility yet")
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
        self.assertContains(response, "Runtime still uses Profile.small_group")
        self.assertContains(response, "Notes must stay operational and non-sensitive")


class ChurchRolePermissionTests(TestCase):
    def setUp(self):
        self.district = District.objects.create(name="North")
        self.other_district = District.objects.create(name="South")
        self.group = SmallGroup.objects.create(name="Rainbow 4", district=self.district)
        self.other_group = SmallGroup.objects.create(
            name="Rainbow 5",
            district=self.other_district,
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

    def test_regular_user_gets_own_profile_small_group(self):
        self.user.profile.small_group = self.group
        self.user.profile.save()

        groups = list(get_accessible_progress_groups(self.user))

        self.assertEqual(groups, [self.group])


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
        self.create_membership()
        session = self.client.session
        session["language"] = "en"
        session.save()
        self.client.login(username="membership_staff", password="TestPass123!")

        response = self.client.get(reverse("staff_membership_request_list"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Membership Requests")
        self.assertContains(response, "request_user")
        self.assertContains(response, "Rainbow 4")
        self.assertContains(response, "requester")
        self.assertContains(response, "I attend Rainbow 4.")
        self.assertContains(response, "Requested")
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
        self.assertContains(response, "会籍申请")
        self.assertContains(response, "申请单位")
        self.assertContains(response, "当前小组")
        self.assertContains(response, "备注必须只包含非敏感")

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
        group = SmallGroup.objects.create(name="District Group", district=district)
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

class AccountSignupLanguageTests(TestCase):
    def setUp(self):
        self.group = SmallGroup.objects.create(name="Rainbow 4")

    def test_signup_does_not_require_email(self):
        response = self.client.post(
            reverse("signup"),
            {
                "username": "elder_user",
                "email": "",
                "small_group": self.group.id,
                "password1": "StrongPass123!",
                "password2": "StrongPass123!",
            },
        )

        self.assertEqual(response.status_code, 302)

        user = User.objects.get(username="elder_user")
        self.assertEqual(user.email, "")
        self.assertEqual(user.profile.small_group, self.group)

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
        self.assertContains(response, "小组")

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
        self.assertContains(response, "Small group")
